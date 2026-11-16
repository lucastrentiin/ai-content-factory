"""Normalização/validação do formato estruturado de roteiro (usado por agentes e pelo editor manual)."""
from __future__ import annotations

from typing import Any

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.models import Script, ScriptVersion

ACTIONS = {"idle", "talk", "walk", "run", "wave", "point", "jump", "shrug", "cower", "think", "dance", "sit"}
EXPRESSIONS = {"neutral", "happy", "sad", "angry", "scared", "surprised", "thinking", "fear", "dread"}
CAMERAS = {"static", "zoom_in", "zoom_out", "slow_zoom", "pan_left", "pan_right", "shake"}
SETTINGS = {"room", "kitchen", "office", "school", "street", "city", "park", "forest", "beach", "abandoned", "lab", "space", "abstract"}
WORDS_PER_SECOND = 2.6


def _s(v: Any, default: str = "") -> str:
    return str(v).strip() if v is not None else default


def normalize_script(data: dict) -> dict:
    if not isinstance(data, dict):
        raise ValueError("roteiro deve ser um objeto")
    scenes_in = data.get("scenes") or []
    if not isinstance(scenes_in, list) or not scenes_in:
        raise ValueError("roteiro sem cenas")
    chars, seen = [], set()
    for c in data.get("characters") or []:
        name = _s(c.get("name"))
        if not name or name.lower() in seen:
            continue
        seen.add(name.lower())
        ap = c.get("appearance") or {}
        chars.append({"name": name, "role": _s(c.get("role"), "secondary"), "description": _s(c.get("description")),
                      "personality": _s(c.get("personality")), "appearance": ap if isinstance(ap, dict) else {},
                      **({"character_id": c["character_id"]} if c.get("character_id") else {})})
    locs, lseen = [], set()
    for loc in data.get("locations") or []:
        name = _s(loc.get("name"))
        if not name or name.lower() in lseen:
            continue
        lseen.add(name.lower())
        st = _s(loc.get("setting_type"), "room")
        locs.append({"name": name, "setting_type": st if st in SETTINGS else "room",
                     "time_of_day": _s(loc.get("time_of_day"), "day") if _s(loc.get("time_of_day")) in ("day", "sunset", "night") else "day",
                     "description": _s(loc.get("description"))})
    if not locs:
        locs = [{"name": "Cenário principal", "setting_type": "room", "time_of_day": "day", "description": ""}]
    scenes = []
    for i, sc in enumerate(scenes_in):
        dialogue = []
        for d in sc.get("dialogue") or []:
            text = _s(d.get("text"))
            if not text:
                continue
            speaker = _s(d.get("character"), "Narrador")
            emo = _s(d.get("emotion"), "neutral")
            dialogue.append({"character": speaker, "text": text, "emotion": emo if emo in EXPRESSIONS else "neutral"})
            if speaker.lower() not in seen and speaker.lower() not in ("narrador", "narrator"):
                seen.add(speaker.lower())
                chars.append({"name": speaker, "role": "temporary", "description": "", "personality": "", "appearance": {}})
        on_scene = []
        for c in sc.get("characters") or []:
            name = _s(c.get("name"))
            if not name:
                continue
            act, ex = _s(c.get("action"), "idle"), _s(c.get("expression"), "neutral")
            on_scene.append({"name": name, "action": act if act in ACTIONS else "idle",
                             "expression": ex if ex in EXPRESSIONS else "neutral",
                             "position": _s(c.get("position"), "center")})
        # garante que quem fala aparece em cena
        for d in dialogue:
            if d["character"].lower() not in ("narrador", "narrator") and not any(c["name"] == d["character"] for c in on_scene):
                on_scene.append({"name": d["character"], "action": "talk", "expression": d["emotion"], "position": "center"})
        narration = _s(sc.get("narration"))
        words = len(narration.split()) + sum(len(d["text"].split()) for d in dialogue)
        est = max(2.0, words / WORDS_PER_SECOND + 0.6)
        cam = _s(sc.get("camera"), "static")
        loc_name = _s(sc.get("location")) or locs[0]["name"]
        if loc_name.lower() not in lseen:
            loc_name = locs[min(i * len(locs) // max(1, len(scenes_in)), len(locs) - 1)]["name"]
        try:
            planned = float(sc.get("duration_s") or est)
        except (TypeError, ValueError):
            planned = est
        scenes.append({
            "index": i, "title": _s(sc.get("title"), f"Cena {i + 1}"), "location": loc_name,
            "duration_s": round(max(planned, est), 2), "narration": narration, "dialogue": dialogue, "characters": on_scene,
            "visual_description": _s(sc.get("visual_description")), "emotion": _s(sc.get("emotion"), "neutral"),
            "camera": cam if cam in CAMERAS else "static", "transition": "fade" if _s(sc.get("transition")) == "fade" else "cut",
            "sfx": [s for s in (sc.get("sfx") or []) if isinstance(s, str)][:3], "on_screen_text": _s(sc.get("on_screen_text"))[:80],
        })
        if not narration and not dialogue:
            raise ValueError(f"cena {i} sem narração nem diálogo")
    mood = _s(data.get("music_mood"), "neutral")
    return {
        "title": _s(data.get("title"), "Sem título")[:200], "synopsis": _s(data.get("synopsis")),
        "full_story": _s(data.get("full_story")), "hook": _s(data.get("hook")) or (scenes[0]["narration"] or scenes[0]["dialogue"][0]["text"] if scenes[0]["dialogue"] or scenes[0]["narration"] else ""),
        "closing": _s(data.get("closing")), "music_mood": mood, "characters": chars, "locations": locs, "scenes": scenes,
        "fact_claims": [c for c in (data.get("fact_claims") or []) if isinstance(c, dict) and c.get("claim")],
        "hashtags": [str(h).lstrip("#") for h in (data.get("hashtags") or [])][:10],
        "next_episode_hook": _s(data.get("next_episode_hook")),
        "publication": data.get("publication") if isinstance(data.get("publication"), dict) else {},
    }


def estimated_duration(content: dict) -> float:
    return round(sum(float(s.get("duration_s", 0)) for s in content.get("scenes", [])), 1)


def add_version(db: Session, script: Script, content: dict, *, created_by: str, provider: str | None = None,
                simulated: bool = False, notes: str = "", review: dict | None = None, target_s: int | None = None) -> ScriptVersion:
    nxt = (db.scalar(select(func.max(ScriptVersion.version)).where(ScriptVersion.script_id == script.id)) or 0) + 1
    v = ScriptVersion(script_id=script.id, version=nxt, title=content["title"], synopsis=content.get("synopsis", ""),
                      full_story=content.get("full_story", ""), hook=content.get("hook", ""), closing=content.get("closing", ""),
                      target_duration_s=target_s or int(estimated_duration(content)), content=content, created_by=created_by,
                      provider=provider, is_simulated=simulated, notes=notes, review=review or {})
    db.add(v)
    script.current_version = nxt
    script.title = content["title"]
    db.flush()
    return v
