"""Agentes de áudio: Voice Director (vozes/emoções) e Audio Generator (TTS, montagem, música)."""
from __future__ import annotations

import hashlib
import json
from pathlib import Path

import numpy as np
from sqlalchemy import select

from app.media import audio as A
from app.models import Asset, Character, Voice
from app.pipeline.context import StepContext
from app.providers.base import BaseProvider
from app.services.assets import fetch_to, store_asset

NARRATOR = "Narrador"


def _voice_rank(v: Voice, real_first: bool = True) -> tuple:
    return (1 if v.provider_key == "espeak" else 0) if real_first else 0, v.id


def _usable(ctx: StepContext, v: Voice) -> bool:
    return any(c.rec.key == v.provider_key for c in ctx.router.candidates("tts"))


def voice_director(ctx: StepContext) -> dict:
    lang = ctx.channel.language
    voices = [v for v in ctx.db.scalars(select(Voice).where(Voice.is_active.is_(True))).all()
              if v.language.lower().split("-")[0] == lang.lower().split("-")[0]]
    usable = [v for v in voices if _usable(ctx, v)] or voices
    if not usable:
        raise RuntimeError("Nenhuma voz ativa para o idioma do canal. Cadastre vozes em Vozes.")
    usable.sort(key=_voice_rank)
    settings = ctx.channel.settings or {}
    narrator = None
    for vid in (settings.get("narrator_voice_id"), (ctx.engine.config or {}).get("narrator_voice_id")):
        if vid:
            narrator = ctx.db.get(Voice, int(vid))
            if narrator and narrator.is_active:
                break
            narrator = None
    narrator = narrator or next((v for v in usable if v.gender == "male"), usable[0])
    used = {narrator.id}
    assignments = {NARRATOR: narrator.id}
    for sc in ctx.scenes():
        for d in sc.dialogue:
            name = d["character"]
            if name in assignments:
                continue
            if name.lower() in ("narrador", "narrator"):
                assignments[name] = narrator.id
                continue
            cid = next((c.get("character_id") for c in sc.characters if c["name"] == name), None)
            ch = ctx.db.get(Character, cid) if cid else None
            if ch and ch.voice_id and ctx.db.get(Voice, ch.voice_id):
                assignments[name] = ch.voice_id  # voz persistente do personagem (consistência entre episódios)
                used.add(ch.voice_id)
                continue
            gender = (ch.visual_spec or {}).get("gender") if ch else None
            cands = [v for v in usable if v.id not in used and (not gender or gender == "neutral" or v.gender == gender)] \
                or [v for v in usable if v.id not in used] or usable
            pick = cands[0]
            assignments[name] = pick.id
            used.add(pick.id)
            if ch:
                ch.voice_id = pick.id
    pace = float((ctx.engine.config or {}).get("speech_rate", 1.0))
    total_lines = 0
    for sc in ctx.scenes():
        lines = []
        if sc.narration:
            lines.append({"speaker": NARRATOR, "character_id": None, "voice_id": narrator.id, "text": sc.narration,
                          "emotion": sc.emotion if sc.emotion in A_EMOTIONS else "neutral", "speed": pace})
        for d in sc.dialogue:
            cid = next((c.get("character_id") for c in sc.characters if c["name"] == d["character"]), None)
            lines.append({"speaker": d["character"], "character_id": cid, "voice_id": assignments.get(d["character"], narrator.id),
                          "text": d["text"], "emotion": d.get("emotion", "neutral"), "speed": pace})
        sc.plan = {**(sc.plan or {}), "lines": lines}
        total_lines += len(lines)
    return {"narrator_voice_id": narrator.id, "assignments": assignments, "lines": total_lines}


A_EMOTIONS = {"neutral", "happy", "sad", "angry", "scared", "surprised", "fear", "dread"}


def _fallback_voice(p: BaseProvider, voice: Voice) -> str:
    dv = (p.config or {}).get("default_voices", {})
    return dv.get(voice.gender) or dv.get("neutral") or dv.get("male") or ""


def synthesize_line(ctx: StepContext, line: dict, voice: Voice, workdir: Path) -> tuple[np.ndarray, list | None, Asset]:
    vs = voice.settings or {}
    speed = float(vs.get("speed", 1.0)) * float(line.get("speed", 1.0))
    key = hashlib.sha256(json.dumps([line["text"], voice.provider_key, voice.provider_voice_id, vs, line.get("emotion"), speed],
                                    sort_keys=True).encode()).hexdigest()[:24]
    cached = ctx.db.scalar(select(Asset).where(Asset.production_job_id == ctx.job.id, Asset.kind == "audio",
                                               Asset.meta["line_hash"].astext == key))
    if cached:
        wav = fetch_to(cached, workdir)
        return A.read_wav(wav), (cached.meta or {}).get("word_timings"), cached

    def call(p: BaseProvider, model: str):
        vid = voice.provider_voice_id if p.key == voice.provider_key else _fallback_voice(p, voice)
        return p.synthesize(text=line["text"], voice_id=vid, language=voice.language, speed=speed,
                            pitch=float(vs.get("pitch", 0)), emotion=line.get("emotion"), settings=vs, model=model)

    res, cand = ctx.router.call("tts", "synthesize_line", call, lambda p, m: p.estimate_cost(chars=len(line["text"]), model=m),
                                preferred=voice.provider_key)
    ext = ".mp3" if res.mime == "audio/mpeg" else ".wav"
    raw = workdir / f"raw_{key}{ext}"
    raw.write_bytes(res.data)
    wav = A.normalize_to_wav(raw, workdir / f"line_{key}.wav")
    arr = A.peak_normalize(A.trim_silence(A.read_wav(wav)))
    A.write_wav(wav, arr)
    timings = res.word_timings
    if timings:  # ajuste por remoção do silêncio inicial
        shift = timings[0]["start"] or 0
        timings = [{**w, "start": max(0.0, (w["start"] or 0) - shift), "end": max(0.0, (w["end"] or 0) - shift)} for w in timings]
    asset = store_asset(ctx.db, kind="audio", name=f"line_{key}.wav", path=wav, mime="audio/wav", origin="generated",
                        license="provider_commercial" if cand.rec.key != "espeak" else "internal_generated",
                        provider_key=cand.rec.key, model=res.model, prompt=line["text"], channel_id=ctx.channel.id,
                        production_job_id=ctx.job.id, duration_s=len(arr) / A.SR,
                        meta={"line_hash": key, "voice_id": voice.id, "word_timings": timings, "used_fallback_voice": cand.rec.key != voice.provider_key})
    if cand.rec.key != voice.provider_key:
        ctx.log("Voz substituída por fallback", voice=voice.name, provider=cand.rec.key)
    return arr, timings, asset


def audio_generator(ctx: StepContext) -> dict:
    tpl = ctx.template["audio"]
    gap, pad = float(tpl["line_gap_s"]), float(tpl["scene_pad_s"])
    wd = ctx.workdir / "audio"
    wd.mkdir(exist_ok=True)
    total = 0.0
    lines_done = 0
    for sc in ctx.scenes():
        track = np.zeros(int(A.SR * 0.5), dtype=np.float32)
        t = pad
        timeline = []
        for line in (sc.plan or {}).get("lines", []):
            voice = ctx.db.get(Voice, line["voice_id"])
            arr, timings, asset = synthesize_line(ctx, line, voice, wd)
            track = A.place(track, arr, t)
            dur = len(arr) / A.SR
            timeline.append({"start": round(t, 3), "end": round(t + dur, 3), "speaker": line["speaker"],
                             "character_id": line.get("character_id"), "text": line["text"], "emotion": line.get("emotion"),
                             "asset_id": asset.id, "word_timings": timings})
            t += dur + gap
            lines_done += 1
        duration = max(2.0, t - gap + pad)
        track = np.concatenate([track, np.zeros(max(0, int(duration * A.SR) - len(track)), dtype=np.float32)])[: int(duration * A.SR)]
        path = A.write_wav(wd / f"scene_{sc.index}.wav", track)
        asset = store_asset(ctx.db, kind="audio", name=f"scene_{sc.index}.wav", path=path, mime="audio/wav", origin="generated",
                            license="internal_generated", channel_id=ctx.channel.id, production_job_id=ctx.job.id,
                            duration_s=duration, meta={"scene_index": sc.index})
        sc.audio_asset_id = asset.id
        sc.audio_timeline = timeline
        sc.duration_s = round(duration, 3)
        total += duration
    music_info = None
    if ctx.template["music"]["enabled"]:
        mood = ctx.script_version().content.get("music_mood", "neutral")
        res, cand = ctx.router.call("music", "background_music",
                                    lambda p, m: p.generate(mood=mood, duration_s=total + 1, seed=ctx.job.id, model=m),
                                    lambda p, m: p.estimate_cost(duration_s=total, model=m))
        masset = store_asset(ctx.db, kind="music", name=f"music_{mood}.wav", data=res.data, mime=res.mime, origin="generated",
                             license=res.license, provider_key=cand.rec.key, model=res.model, channel_id=ctx.channel.id,
                             production_job_id=ctx.job.id, duration_s=total + 1, meta={"mood": mood})
        ctx.job.config = {**(ctx.job.config or {}), "music_asset_id": masset.id}
        music_info = {"asset_id": masset.id, "mood": mood, "provider": cand.rec.key}
    return {"total_duration_s": round(total, 2), "lines": lines_done, "music": music_info}
