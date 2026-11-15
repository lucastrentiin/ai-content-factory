"""Agentes de produção: Visual Generator, Video Editor, Quality Controller e Publisher (preparação)."""
from __future__ import annotations

import hashlib
import json
from datetime import UTC, datetime

import numpy as np
from sqlalchemy import delete, func, select

from app.media import audio as A
from app.media.animation.backgrounds import render_background
from app.media.animation.scene_renderer import CharacterTrack, SceneRenderSpec, load_image, render_scene
from app.media.compose import concat_clips, extract_frame, make_thumbnail, normalize_clip
from app.media.ffmpeg import MediaError
from app.media.qc import Check, summarize, technical_checks
from app.media.subtitles import build_ass, chunk_segment
from app.models import (
    Asset,
    Character,
    CharacterAppearance,
    Location,
    Platform,
    Publication,
    RenderJob,
    Scene,
    SocialAccount,
)
from app.models.enums import SAFE_LICENSES
from app.pipeline import prompts
from app.pipeline.agents.design import background_asset_for, spec_hash
from app.pipeline.context import StepContext
from app.providers.router import llm_json
from app.services.assets import fetch_to, read_asset, store_asset


class RedoSteps(Exception):
    """Sinaliza ao orquestrador que etapas anteriores devem ser reexecutadas (autocorreção)."""

    def __init__(self, steps: list[str], reason: str):
        super().__init__(reason)
        self.steps = steps
        self.reason = reason


# ------------------------------------------------------------------------------------------- visual generator
def _scene_prompt(ctx: StepContext, sc: Scene) -> str:
    style = ctx.job.visual_style or ctx.channel.visual_style
    anchors = []
    for c in sc.characters:
        ch = ctx.db.get(Character, c["character_id"]) if c.get("character_id") else None
        if ch:
            anchors.append((ch.visual_spec or {}).get("prompt_anchor") or ch.name)
    loc = ctx.db.get(Location, sc.location_id) if sc.location_id else None
    return (f"{style} style vertical 9:16 frame. {sc.visual_description or sc.title}. "
            f"Setting: {loc.visual_prompt if loc else sc.location_name}. "
            + (f"Characters (keep consistent appearance): {'; '.join(anchors)}. " if anchors else "")
            + f"Mood: {sc.emotion}. No text, no watermark, no logos, no real people.")


def visual_generator(ctx: StepContext) -> dict:
    W, H = ctx.template["width"], ctx.template["height"]
    generated, fallbacks = [], []
    for sc in ctx.scenes():
        if sc.visual_mode not in ("ai_image", "ai_video"):
            continue
        prompt = _scene_prompt(ctx, sc)
        ph = hashlib.sha256(prompt.encode()).hexdigest()[:16]
        try:
            img_asset = ctx.db.get(Asset, sc.image_asset_id) if sc.image_asset_id else None
            if not img_asset or (img_asset.meta or {}).get("prompt_hash") != ph:
                seed = int(hashlib.md5(f"{ctx.job.id}-{sc.index}".encode()).hexdigest()[:6], 16)
                res, cand = ctx.router.call("image", "scene_image",
                                            lambda p, m: p.generate(prompt=prompt, width=W, height=H, seed=seed, model=m),
                                            lambda p, m: p.estimate_cost(count=1, model=m), allow_simulated=False)
                img_asset = store_asset(ctx.db, kind="image", name=f"scene_{sc.index}.png", data=res.data, mime=res.mime,
                                        origin="generated", license="provider_commercial", provider_key=cand.rec.key,
                                        model=res.model, prompt=prompt, channel_id=ctx.channel.id, production_job_id=ctx.job.id,
                                        meta={"prompt_hash": ph, "seed": seed})
                sc.image_asset_id = img_asset.id
                generated.append({"scene": sc.index, "kind": "image", "provider": cand.rec.key})
            if sc.visual_mode == "ai_video":
                vid = ctx.db.get(Asset, sc.video_asset_id) if sc.video_asset_id else None
                if not vid or (vid.meta or {}).get("prompt_hash") != ph:
                    first = read_asset(img_asset)
                    res, cand = ctx.router.call("video", "scene_video",
                                                lambda p, m: p.generate(prompt=prompt, duration_s=min(10.0, sc.duration_s), image=first, model=m),
                                                lambda p, m: p.estimate_cost(duration_s=min(10.0, sc.duration_s), model=m),
                                                allow_simulated=False)
                    vid = store_asset(ctx.db, kind="video", name=f"scene_{sc.index}_ai.mp4", data=res.data, mime=res.mime,
                                      origin="generated", license="provider_commercial", provider_key=cand.rec.key, model=res.model,
                                      prompt=prompt, channel_id=ctx.channel.id, production_job_id=ctx.job.id, meta={"prompt_hash": ph})
                    sc.video_asset_id = vid.id
                    generated.append({"scene": sc.index, "kind": "video", "provider": cand.rec.key})
        except Exception as e:  # noqa: BLE001 — fallback para animação própria (custo zero, consistência)
            ctx.log("Geração por IA falhou; cena usará animação 2D", scene=sc.index, error=str(e)[:300])
            sc.visual_mode = "animation_2d"
            sc.plan = {**(sc.plan or {}), "mode": "animation_2d", "fallback_reason": str(e)[:300]}
            fallbacks.append(sc.index)
    return {"generated": generated, "fallback_to_animation": fallbacks}


# ------------------------------------------------------------------------------------------- video editor
def _scene_spec_hash(ctx: StepContext, sc: Scene, bg_id: int | None) -> tuple[str, dict]:
    char_hashes = {}
    for c in sc.characters:
        ch = ctx.db.get(Character, c["character_id"]) if c.get("character_id") else None
        if ch:
            char_hashes[str(ch.id)] = spec_hash(ch.visual_spec or {})
    t = ctx.template
    payload = {"plan": sc.plan, "chars": char_hashes, "bg": bg_id, "img": sc.image_asset_id, "vid": sc.video_asset_id,
               "audio": [(x["start"], x["end"], x["asset_id"], x.get("character_id")) for x in sc.audio_timeline or []],
               "dur": sc.duration_s, "mode": sc.visual_mode, "w": t["width"], "h": t["height"], "fps": t["fps"],
               "ov": t["overlay_text"], "scale": t["render_scale"], "v": 3}
    return hashlib.sha256(json.dumps(payload, sort_keys=True, default=str).encode()).hexdigest()[:24], char_hashes


def _render_clip(ctx: StepContext, sc: Scene, n_scenes: int) -> tuple[Asset, bool]:
    t = ctx.template
    W, H, fps = t["width"], t["height"], t["fps"]
    bg_asset = background_asset_for(ctx, sc)
    h, char_hashes = _scene_spec_hash(ctx, sc, bg_asset.id if bg_asset else None)
    current = ctx.db.get(Asset, sc.clip_asset_id) if sc.clip_asset_id else None
    rj = RenderJob(production_job_id=ctx.job.id, scene_id=sc.id, kind="scene_clip", status="running",
                   started_at=datetime.now(UTC), params={"spec_hash": h, "mode": sc.visual_mode})
    ctx.db.add(rj)
    if current and (current.meta or {}).get("spec_hash") == h and not sc.needs_rerender:
        rj.status, rj.cached, rj.output_asset_id, rj.finished_at, rj.progress = "succeeded", True, current.id, datetime.now(UTC), 1.0
        return current, True
    frames = max(1, round(sc.duration_s * fps))
    duration = frames / fps
    out = ctx.workdir / f"clip_{sc.index}_{h[:8]}.mp4"
    try:
        if sc.visual_mode == "ai_video" and sc.video_asset_id:
            src = fetch_to(ctx.db.get(Asset, sc.video_asset_id), ctx.workdir / "src")
            normalize_clip(src, out, width=W, height=H, fps=fps, duration=duration, crf=t["crf"])
        else:
            if bg_asset:
                bg = load_image(read_asset(bg_asset))
            else:
                bg = render_background("abstract", "day", int(W * 1.16), int(H * 1.16), f"job{ctx.job.id}")
            tracks = []
            if sc.visual_mode == "animation_2d":
                for k, c in enumerate(sc.characters):
                    ch = ctx.db.get(Character, c["character_id"]) if c.get("character_id") else None
                    spec = (ch.visual_spec if ch else {}) or {}
                    speaking, env = [], np.zeros(frames, dtype=np.float32)
                    for line in sc.audio_timeline or []:
                        if ch and line.get("character_id") == ch.id:
                            speaking.append((line["start"], line["end"], line.get("emotion") or "neutral"))
                            arr = A.read_wav(fetch_to(ctx.db.get(Asset, line["asset_id"]), ctx.workdir / "audio"))
                            env = np.maximum(env, A.envelope(arr, fps, frames, line["start"]))
                    tracks.append(CharacterTrack(spec=spec, x=c["x"], action=c["action"], expression=c["expression"],
                                                 facing=c["facing"], walk_to=c.get("walk_to"), speaking=speaking,
                                                 envelope=env if speaking else None, phase=k * 1.3))
            fade = float(t["transitions"].get("fade_s", 0.25))
            spec = SceneRenderSpec(width=W, height=H, fps=fps, duration_s=duration, background=bg, characters=tracks,
                                   camera=sc.camera if sc.visual_mode == "animation_2d" else (sc.camera if sc.camera != "static" else "slow_zoom"),
                                   overlay_text=sc.on_screen_text, text_style=t["overlay_text"],
                                   fade_in=fade if (sc.index == 0 or sc.transition == "fade") else 0,
                                   fade_out=fade if (sc.index == n_scenes - 1 or sc.transition == "fade") else 0, seed=sc.index)
            render_scene(spec, out, render_scale=float(t["render_scale"]), crf=int(t["crf"]))
    except Exception as e:
        rj.status, rj.error, rj.finished_at = "failed", str(e)[:1000], datetime.now(UTC)
        sc.status, sc.error = "failed", str(e)[:1000]
        raise
    asset = store_asset(ctx.db, kind="video", name=out.name, path=out, mime="video/mp4", origin="procedural",
                        license="internal_generated", channel_id=ctx.channel.id, production_job_id=ctx.job.id,
                        width=W, height=H, duration_s=duration, meta={"spec_hash": h, "scene_index": sc.index, "char_hashes": char_hashes})
    sc.clip_asset_id = asset.id
    sc.status, sc.error, sc.needs_rerender, sc.spec_hash = "rendered", None, False, h
    rj.status, rj.output_asset_id, rj.finished_at, rj.progress = "succeeded", asset.id, datetime.now(UTC), 1.0
    rj.duration_ms = int((rj.finished_at - rj.started_at).total_seconds() * 1000)
    return asset, False


def video_editor(ctx: StepContext) -> dict:
    t = ctx.template
    W, H, fps = t["width"], t["height"], t["fps"]
    scenes = ctx.scenes()
    clips, rendered, cached = [], [], []
    for sc in scenes:
        asset, was_cached = _render_clip(ctx, sc, len(scenes))
        (cached if was_cached else rendered).append(sc.index)
        clips.append(fetch_to(asset, ctx.workdir / "clips"))
        ctx.job.progress = round(0.6 + 0.25 * (sc.index + 1) / len(scenes), 3)
        ctx.db.commit()  # progresso visível e cache persistido mesmo se uma cena posterior falhar
    final_rj = RenderJob(production_job_id=ctx.job.id, kind="final", status="running", started_at=datetime.now(UTC))
    ctx.db.add(final_rj)
    wd = ctx.workdir
    video = concat_clips(clips, wd / "video_concat.mp4")
    voice = np.zeros(0, dtype=np.float32)
    fx = np.zeros(0, dtype=np.float32)
    captions = []
    offset = 0.0
    wpc = int(t["captions"].get("words_per_caption", 3))
    for sc in scenes:
        dur = max(1, round(sc.duration_s * fps)) / fps
        arr = A.read_wav(fetch_to(ctx.db.get(Asset, sc.audio_asset_id), wd / "audio"))
        n = int(round(dur * A.SR))
        arr = np.concatenate([arr, np.zeros(max(0, n - len(arr)), dtype=np.float32)])[:n]
        voice = np.concatenate([voice, arr])
        if t["sfx"]["enabled"]:
            for k, name in enumerate(sc.sfx or []):
                if name in A.SFX_NAMES:
                    fx = A.place(fx, A.sfx(name, seed=sc.index), offset + 0.15 + k * 0.6, float(t["sfx"]["volume"]))
        for line in sc.audio_timeline or []:
            captions += chunk_segment(line["text"], offset + line["start"], offset + line["end"], wpc, line.get("word_timings"))
        offset += dur
    voice_p = A.write_wav(wd / "voice.wav", voice)
    fx_p = None
    if len(fx):
        fx = np.concatenate([fx, np.zeros(max(0, len(voice) - len(fx)), dtype=np.float32)])[: len(voice)]
        fx_p = A.write_wav(wd / "sfx.wav", fx)
    music_p = None
    mid = (ctx.job.config or {}).get("music_asset_id")
    if mid and t["music"]["enabled"]:
        music_p = fetch_to(ctx.db.get(Asset, mid), wd / "music")
    wm = dict(t.get("watermark") or {})
    if not wm.get("text") and (ctx.channel.settings or {}).get("watermark"):
        wm["text"] = ctx.channel.settings["watermark"]
    subs = build_ass(captions, wd / "subs.ass", width=W, height=H, style=t["captions"], watermark=wm)
    final = A.mix_final(video, voice_p, music_p, fx_p, wd / "final.mp4", subtitles=subs,
                        music_volume=float(t["music"]["volume"]), ducking=bool(t["music"]["ducking"]),
                        loudness_lufs=float(t["audio"]["loudness_lufs"]), fps=fps, crf=int(t["crf"]))
    out = store_asset(ctx.db, kind="video", name=f"producao_{ctx.job.id}.mp4", path=final, mime="video/mp4", origin="generated",
                      license="internal_generated", channel_id=ctx.channel.id, series_id=ctx.job.series_id,
                      production_job_id=ctx.job.id, width=W, height=H, duration_s=offset, is_simulated=ctx.job.is_simulated,
                      meta={"final": True, "scenes": len(scenes)})
    sub_asset = store_asset(ctx.db, kind="subtitle", name="legendas.ass", path=subs, mime="text/x-ssa", origin="generated",
                            license="internal_generated", channel_id=ctx.channel.id, production_job_id=ctx.job.id)
    # capa: quadro do meio da primeira cena + título
    first_mid = max(0.3, min(scenes[0].duration_s * 0.6, offset - 0.1))
    frame = extract_frame(video, first_mid, wd / "thumb_frame.png")
    thumb = make_thumbnail(frame, ctx.job.title, wd / "thumb.jpg", accent=t["thumbnail"]["accent"], width=W, height=H)
    th = store_asset(ctx.db, kind="thumbnail", name="capa.jpg", path=thumb, mime="image/jpeg", origin="generated",
                     license="internal_generated", channel_id=ctx.channel.id, production_job_id=ctx.job.id, width=W, height=H)
    ctx.job.output_asset_id, ctx.job.thumbnail_asset_id = out.id, th.id
    ctx.job.config = {**(ctx.job.config or {}), "subtitle_asset_id": sub_asset.id}
    final_rj.status, final_rj.output_asset_id, final_rj.finished_at = "succeeded", out.id, datetime.now(UTC)
    final_rj.duration_ms = int((final_rj.finished_at - final_rj.started_at).total_seconds() * 1000)
    # histórico de aparições
    ctx.db.execute(delete(CharacterAppearance).where(CharacterAppearance.production_job_id == ctx.job.id))
    counts: dict[int, list[int]] = {}
    for sc in scenes:
        for c in sc.characters:
            if c.get("character_id"):
                counts.setdefault(c["character_id"], [0, 0])[0] += 1
        for line in sc.audio_timeline or []:
            if line.get("character_id"):
                counts.setdefault(line["character_id"], [0, 0])[1] += 1
    for cid, (n_sc, n_lines) in counts.items():
        ctx.db.add(CharacterAppearance(character_id=cid, production_job_id=ctx.job.id, episode_id=ctx.job.episode_id,
                                       scene_count=n_sc, lines_count=n_lines))
    ctx.db.flush()
    for cid in counts:
        ch = ctx.db.get(Character, cid)
        ch.appearance_count = ctx.db.scalar(select(func.count(func.distinct(CharacterAppearance.production_job_id)))
                                            .where(CharacterAppearance.character_id == cid))
    return {"duration_s": round(offset, 2), "rendered_scenes": rendered, "cached_scenes": cached, "output_asset_id": out.id,
            "captions": len(captions)}


# ------------------------------------------------------------------------------------------- quality controller
def quality_controller(ctx: StepContext) -> dict:
    t = ctx.template
    limits = ctx.platform_limits()
    from app.services.common import get_setting

    qcfg = get_setting(ctx.db, "quality")
    out_asset = ctx.db.get(Asset, ctx.job.output_asset_id) if ctx.job.output_asset_id else None
    if not out_asset:
        raise RedoSteps(["video_editor", "quality_controller"], "Vídeo final ausente")
    video = fetch_to(out_asset, ctx.workdir / "qc")
    sub_id = (ctx.job.config or {}).get("subtitle_asset_id")
    subs = fetch_to(ctx.db.get(Asset, sub_id), ctx.workdir / "qc") if sub_id else None
    checks = technical_checks(video, width=t["width"], height=t["height"], fps=t["fps"],
                              target_duration=ctx.job.target_duration_s, min_duration=limits["min"], max_duration=limits["max"],
                              max_file_mb=int(limits["max_file_mb"]),
                              loudness_range=(qcfg["min_loudness_lufs"], qcfg["max_loudness_lufs"]),
                              max_black_ratio=qcfg["max_black_ratio"], subtitles_path=subs)
    scenes = ctx.scenes()
    content = ctx.script_version().content
    missing = [s.index for s in scenes if not s.clip_asset_id or not s.audio_asset_id]
    checks.append(Check("scenes_complete", "fail" if missing else "ok",
                        f"Cenas sem clipe/áudio: {missing}" if missing else f"{len(scenes)} cenas completas",
                        f"rerender_scene:{missing[0]}" if missing else None))
    checks.append(Check("script_coherence", "ok" if len(scenes) == len(content["scenes"]) else "fail",
                        f"{len(scenes)} cenas no vídeo / {len(content['scenes'])} no roteiro", None if len(scenes) == len(content["scenes"]) else "manual"))
    expected = sum((1 if s.narration else 0) + len(s.dialogue or []) for s in scenes)
    got = sum(len(s.audio_timeline or []) for s in scenes)
    checks.append(Check("speech_sync", "ok" if expected == got else "fail", f"{got}/{expected} falas com áudio sincronizado",
                        None if expected == got else "manual"))
    # continuidade visual dos personagens (spec usado no render == ficha atual)
    drift = []
    for s in scenes:
        clip = ctx.db.get(Asset, s.clip_asset_id) if s.clip_asset_id else None
        for cid, h in ((clip.meta or {}).get("char_hashes", {}) if clip else {}).items():
            ch = ctx.db.get(Character, int(cid))
            if ch and spec_hash(ch.visual_spec or {}) != h:
                drift.append((s.index, ch.name))
    checks.append(Check("character_continuity", "ok" if not drift else "fail",
                        "Aparência consistente com as fichas" if not drift else f"Divergência: {drift}",
                        f"rerender_scene:{drift[0][0]}" if drift else None))
    used = ctx.db.scalars(select(Asset).where(Asset.production_job_id == ctx.job.id)).all()
    bg_ids = {background_asset_for(ctx, s).id for s in scenes if background_asset_for(ctx, s)}
    used = list(used) + [ctx.db.get(Asset, i) for i in bg_ids]
    bad = [a.name for a in used if a and a.license not in {x.value for x in SAFE_LICENSES}]
    checks.append(Check("licenses", "ok" if not bad else "fail", "Todos os materiais com direitos adequados" if not bad
                        else f"Materiais sem licença confirmada: {bad[:5]}", None if not bad else "manual"))
    broken = []
    for s in scenes:
        if s.image_asset_id:
            try:
                load_image(read_asset(ctx.db.get(Asset, s.image_asset_id)))
            except (MediaError, Exception):  # noqa: BLE001
                broken.append(s.index)
    checks.append(Check("images_valid", "ok" if not broken else "fail", f"Imagens corrompidas nas cenas {broken}" if broken else "Imagens válidas",
                        f"rerender_scene:{broken[0]}" if broken else None))
    if ctx.job.simulated_parts:
        checks.append(Check("simulated_content", "warn", f"Partes geradas por provedores simulados: {ctx.job.simulated_parts}"))
    for r in (ctx.job.config or {}).get("review_reasons", []):
        checks.append(Check("editorial_review", "warn", r, "manual"))
    report = summarize(checks)
    fixable = [c for c in checks if c.status == "fail" and c.fix and c.fix != "manual"]
    attempts = int((ctx.job.config or {}).get("qc_fix_attempts", 0))
    if fixable and attempts < 2:
        ctx.job.config = {**(ctx.job.config or {}), "qc_fix_attempts": attempts + 1}
        for c in fixable:
            if c.fix.startswith("rerender_scene:"):
                idx = int(c.fix.split(":")[1])
                sc = next((s for s in scenes if s.index == idx), None)
                if sc:
                    sc.needs_rerender = True
                    if sc.image_asset_id and c.key == "images_valid":
                        sc.image_asset_id = None
        ctx.job.qc_report = report
        raise RedoSteps(["visual_generator", "video_editor", "quality_controller"],
                        "Autocorreção: " + "; ".join(f"{c.key}: {c.detail}" for c in fixable))
    if not report["passed"]:
        ctx.job.config = {**(ctx.job.config or {}), "force_review": True,
                          "review_reasons": [*(ctx.job.config or {}).get("review_reasons", []), "Falhou no controle de qualidade"]}
    report["checked_at"] = datetime.now(UTC).isoformat()
    ctx.job.qc_report = report
    return {"passed": report["passed"], "fails": report["fail_count"], "warns": report["warn_count"]}


# ------------------------------------------------------------------------------------------- publisher (preparação)
def publisher(ctx: StepContext) -> dict:
    v = ctx.script_version()
    content = v.content
    created = []
    for key in ctx.channel.platforms or []:
        plat = ctx.db.scalar(select(Platform).where(Platform.key == key))
        if not plat:
            continue
        data, cand, simulated = llm_json(
            ctx.router, operation="publication_metadata", system=prompts.system_for("publisher", language=ctx.channel.language),
            prompt=prompts.metadata_prompt(title=v.title, synopsis=v.synopsis, platform=plat.name, max_title=plat.max_title_len,
                                           max_hashtags=plat.max_hashtags, language=ctx.channel.language, hashtags=content.get("hashtags", [])),
            task={"type": "metadata", "title": v.title, "synopsis": v.synopsis, "platform": key, "hashtags": content.get("hashtags", [])},
            max_tokens=2000)
        tags = [("#" + str(h).lstrip("#")).replace(" ", "") for h in (data.get("hashtags") or [])][: plat.max_hashtags]
        base_tags = [("#" + h.lstrip("#")) for h in (ctx.channel.settings or {}).get("hashtags_base", [])]
        tags = list(dict.fromkeys(tags + base_tags))[: plat.max_hashtags]
        acc = ctx.db.scalar(select(SocialAccount).where(SocialAccount.channel_id == ctx.channel.id, SocialAccount.platform_key == key)
                            .order_by((SocialAccount.status == "connected").desc()).limit(1))
        mode = "api" if acc and acc.status == "connected" and acc.publish_mode == "api" and plat.supports_api_publish else "assisted"
        idem = f"job{ctx.job.id}:{key}"
        pub = ctx.db.scalar(select(Publication).where(Publication.idempotency_key == idem))
        if pub and pub.status in ("published", "publishing", "processing"):
            continue
        if pub is None:
            pub = Publication(production_job_id=ctx.job.id, channel_id=ctx.channel.id, platform_key=key, idempotency_key=idem,
                              title="", status="draft")
            ctx.db.add(pub)
        pub.title = (data.get("title") or v.title)[: plat.max_title_len]
        pub.description = (data.get("description") or v.synopsis)[: plat.max_description_len]
        pub.hashtags = tags
        pub.social_account_id = acc.id if acc else None
        pub.mode = mode
        pub.video_asset_id = ctx.job.output_asset_id
        pub.cover_asset_id = ctx.job.thumbnail_asset_id
        pub.experiment_variant_id = ctx.job.experiment_variant_id
        pub.privacy = (acc.config or {}).get("privacy", "public") if acc else "public"
        if pub.status not in ("scheduled",):
            pub.status = "draft"
        created.append({"platform": key, "mode": mode, "simulated_metadata": simulated})
    ctx.db.flush()
    return {"publications": created}
