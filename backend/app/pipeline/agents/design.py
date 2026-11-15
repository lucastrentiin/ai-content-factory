"""Agentes de design: Character Designer, Art Director e Scene Planner."""
from __future__ import annotations

import copy
import hashlib
import random

from sqlalchemy import func, select

from app.media.animation.backgrounds import background_png
from app.media.animation.preview import character_sheet_png
from app.models import Asset, Character, CharacterAsset, Location, Scene, Series
from app.pipeline.agents.writing import available_characters
from app.pipeline.context import StepContext
from app.services.assets import store_asset

HAIR_COLORS = ["#1f1410", "#3f2a1d", "#6b4423", "#a16207", "#111827", "#7c2d12", "#d4d4d8"]
STYLE_MAP = {"stickman": "stickman", "cartoon": "cartoon", "cinematic": "cartoon", "2d": "cartoon"}


def visual_spec_from_appearance(name: str, appearance: dict, style: str) -> dict:
    rng = random.Random(int(hashlib.md5(name.lower().encode()).hexdigest()[:8], 16))
    ap = appearance or {}
    age = ap.get("age_group", "adult")
    hair = ap.get("hair") or rng.choice(["short", "long", "spiky", "curly", "ponytail", "bun"])
    if ap.get("gender") == "male" and hair in ("bun", "ponytail") and "hair" not in ap:
        hair = "short"
    spec = {
        "style": STYLE_MAP.get(style, "cartoon"),
        "outfit_color": ap.get("outfit_color") or rng.choice(["#ef4444", "#3b82f6", "#22c55e", "#f59e0b", "#a855f7", "#14b8a6"]),
        "pants_color": rng.choice(["#1f2937", "#1e3a8a", "#374151", "#78350f"]),
        "skin_tone": ap.get("skin_tone") or rng.choice(["#f1c27d", "#e0ac69", "#c68642", "#8d5524", "#ffdbac"]),
        "hair": hair,
        "hair_color": ap.get("hair_color") or (rng.choice(HAIR_COLORS[-1:]) if age == "elder" else rng.choice(HAIR_COLORS[:-1])),
        "accessories": [a for a in (ap.get("accessories") or []) if a in ("glasses", "hat", "scarf", "backpack", "bow")],
        "height": {"child": 0.72, "teen": 0.9, "elder": 0.95}.get(age, 1.0),
        "build": round(rng.uniform(0.9, 1.15), 2),
        "seed": rng.randint(1, 10**9),
        "gender": ap.get("gender", "neutral"),
    }
    spec["prompt_anchor"] = (f"{name}: {ap.get('gender', '')} {age}, {hair} {spec['hair_color']} hair, wearing {spec['outfit_color']} top, "
                             f"skin {spec['skin_tone']}{', ' + ', '.join(spec['accessories']) if spec['accessories'] else ''}")
    return spec


def spec_hash(spec: dict) -> str:
    keys = sorted(k for k in spec if k not in ("prompt_anchor",))
    return hashlib.sha256("|".join(f"{k}={spec[k]}" for k in keys).encode()).hexdigest()[:16]


def ensure_character_preview(ctx_db, ch: Character) -> None:
    has = ctx_db.scalar(select(func.count()).select_from(CharacterAsset).where(CharacterAsset.character_id == ch.id,
                                                                                CharacterAsset.kind == "preview"))
    if has:
        return
    png = character_sheet_png(ch.visual_spec, ch.name)
    a = store_asset(ctx_db, kind="image", name=f"{ch.name}_sheet.png", data=png, mime="image/png", origin="procedural",
                    license="internal_generated", key_prefix=f"characters/{ch.id}", is_reusable=True, width=900, height=900,
                    tags=["character", "preview"])
    ctx_db.add(CharacterAsset(character_id=ch.id, asset_id=a.id, kind="preview", label="Folha de referência", is_primary=True))


def character_designer(ctx: StepContext) -> dict:
    v = ctx.script_version()
    content = copy.deepcopy(v.content)
    style = ctx.job.visual_style or ctx.channel.visual_style
    universe_id = None
    if ctx.job.series_id:
        s = ctx.db.get(Series, ctx.job.series_id)
        universe_id = s.universe_id if s else None
    pool = {c.name.lower(): c for c in available_characters(ctx, limit=200)}
    created, reused, mapping = [], [], {}
    for c in content["characters"]:
        if c["name"].lower() in ("narrador", "narrator"):
            continue
        ch = pool.get(c["name"].lower())
        if ch is None and c.get("character_id"):
            ch = ctx.db.get(Character, c["character_id"])
        if ch is None:
            ap = c.get("appearance") or {}
            ch = Character(name=c["name"], role_type=c.get("role", "secondary") if c.get("role") in ("main", "secondary", "temporary") else "secondary",
                           identity=c.get("description", ""), personality=c.get("personality", ""),
                           physical_description=", ".join(f"{k}: {v}" for k, v in ap.items() if not isinstance(v, list)),
                           art_style=style, visual_spec=visual_spec_from_appearance(c["name"], ap, style),
                           language=ctx.channel.language, channel_id=ctx.channel.id, universe_id=universe_id,
                           auto_created=True, expressions=["neutral", "happy", "sad", "angry", "scared", "surprised", "thinking"])
            ctx.db.add(ch)
            ctx.db.flush()
            created.append(ch.name)
        else:
            reused.append(ch.name)
        ensure_character_preview(ctx.db, ch)
        mapping[c["name"]] = ch.id
        c["character_id"] = ch.id
    v.content = content
    ctx.log("Personagens resolvidos", created=created, reused=reused)
    return {"created": created, "reused": reused, "mapping": mapping}


def art_director(ctx: StepContext) -> dict:
    v = ctx.script_version()
    content = copy.deepcopy(v.content)
    style = ctx.job.visual_style or ctx.channel.visual_style
    eng_cfg = ctx.engine.config or {}
    use_ai_bg = bool(eng_cfg.get("ai_backgrounds")) and ctx.router.has_real("image")
    mood = content.get("music_mood", "neutral")
    W, H = ctx.template["width"], ctx.template["height"]
    out_locs = []
    for loc in content["locations"]:
        rec = ctx.db.scalar(select(Location).where(Location.channel_id == ctx.channel.id, func.lower(Location.name) == loc["name"].lower()))
        if rec is None:
            rec = Location(channel_id=ctx.channel.id, name=loc["name"], description=loc.get("description", ""),
                           setting_type=loc["setting_type"], time_of_day=loc["time_of_day"],
                           visual_prompt=f"{loc['description'] or loc['name']}, {style} style, vertical 9:16, no people, no text")
            ctx.db.add(rec)
            ctx.db.flush()
        if not rec.background_asset_id:
            asset = None
            if use_ai_bg:
                try:
                    res, cand = ctx.router.call(
                        "image", "location_background",
                        lambda p, m, rec=rec: p.generate(prompt=rec.visual_prompt, width=W, height=H,
                                                         seed=int(hashlib.md5(rec.name.encode()).hexdigest()[:6], 16), model=m),
                        lambda p, m: p.estimate_cost(count=1, model=m))
                    asset = store_asset(ctx.db, kind="image", name=f"bg_{rec.id}.png", data=res.data, mime=res.mime,
                                        origin="generated", license="provider_commercial", provider_key=cand.rec.key,
                                        model=res.model, prompt=rec.visual_prompt, channel_id=ctx.channel.id, is_reusable=True,
                                        tags=["background", "location"], key_prefix=f"channels/{ctx.channel.id}/locations/{rec.id}")
                except Exception as e:  # noqa: BLE001 — cai para o gerador procedural
                    ctx.log("Fundo por IA indisponível; usando procedural", error=str(e)[:200])
            if asset is None:
                png = background_png(rec.setting_type, rec.time_of_day, int(W * 1.16), int(H * 1.16), f"loc{rec.id}",
                                     rec.palette or None, mood)
                asset = store_asset(ctx.db, kind="image", name=f"bg_{rec.id}.png", data=png, mime="image/png", origin="procedural",
                                    license="internal_generated", channel_id=ctx.channel.id, is_reusable=True,
                                    tags=["background", "location", rec.setting_type],
                                    key_prefix=f"channels/{ctx.channel.id}/locations/{rec.id}",
                                    width=int(W * 1.16), height=int(H * 1.16))
            rec.background_asset_id = asset.id
        rec.reuse_count = (rec.reuse_count or 0) + 1
        loc["location_id"] = rec.id
        out_locs.append({"name": rec.name, "id": rec.id, "background_asset_id": rec.background_asset_id})
    content["art_direction"] = {"visual_style": style, "mood": mood, "palette": eng_cfg.get("palette", {}),
                                "ai_backgrounds": use_ai_bg}
    v.content = content
    return {"visual_style": style, "locations": out_locs, "ai_backgrounds": use_ai_bg}


def scene_planner(ctx: StepContext) -> dict:
    v = ctx.script_version()
    content = v.content
    eng_cfg = ctx.engine.config or {}
    loc_ids = {loc["name"]: loc.get("location_id") for loc in content["locations"]}
    char_ids = {c["name"]: c.get("character_id") for c in content["characters"]}
    default_mode = eng_cfg.get("default_visual_mode", "animation_2d")
    if (ctx.job.visual_style or "") == "cinematic":
        default_mode = "ai_image"
    has_img, has_vid = ctx.router.has_real("image"), ctx.router.has_real("video")
    ai_video_scenes = set(eng_cfg.get("ai_video_scenes", []))  # ex.: [0] = abertura em vídeo de IA
    existing = {s.index: s for s in ctx.scenes()}
    keep = set()
    modes = {}
    for sc in content["scenes"]:
        i = sc["index"]
        mode = default_mode
        if i in ai_video_scenes and has_vid:
            mode = "ai_video"
        if mode in ("ai_image", "ai_video") and not has_img and mode != "ai_video":
            mode = "animation_2d"
        if mode == "ai_video" and not has_vid:
            mode = "ai_image" if has_img else "animation_2d"
        modes[i] = mode
        on = sc["characters"]
        n = len(on)
        placed = []
        for k, c in enumerate(on):
            pos = {"left": 0.32, "right": 0.68, "center": 0.5}.get(c.get("position"), 0.5)
            if n > 1 and all(x.get("position") == on[0].get("position") for x in on):
                pos = 0.25 + 0.5 * k / max(1, n - 1)
            facing = 1 if pos <= 0.5 else -1
            if n == 1:
                facing = 1 if k % 2 == 0 else -1
            walk_to = None
            if c["action"] in ("walk", "run"):
                walk_to = min(0.8, pos + 0.18) if facing > 0 else max(0.2, pos - 0.18)
            placed.append({"name": c["name"], "character_id": char_ids.get(c["name"]), "x": round(pos, 3), "facing": facing,
                           "action": c["action"], "expression": c["expression"], "walk_to": walk_to})
        plan = {"mode": mode, "characters": placed, "camera": sc["camera"], "transition": sc["transition"],
                "overlay_text": sc["on_screen_text"], "visual_prompt": sc["visual_description"], "sfx": sc["sfx"]}
        row = existing.get(i)
        fields = dict(title=sc["title"], duration_s=sc["duration_s"], narration=sc["narration"], dialogue=sc["dialogue"],
                      characters=placed, location_id=loc_ids.get(sc["location"]), location_name=sc["location"],
                      visual_description=sc["visual_description"], emotion=sc["emotion"], visual_mode=mode, camera=sc["camera"],
                      transition=sc["transition"], sfx=sc["sfx"], on_screen_text=sc["on_screen_text"], plan=plan)
        if row is None:
            row = Scene(production_job_id=ctx.job.id, index=i, **fields)
            ctx.db.add(row)
        else:
            changed = any(getattr(row, k) != val for k, val in fields.items() if k not in ("duration_s",))
            for k, val in fields.items():
                setattr(row, k, val)
            if changed:
                row.status = "pending"
        keep.add(i)
    for i, row in existing.items():
        if i not in keep:
            ctx.db.delete(row)
    ctx.db.flush()
    return {"scenes": len(keep), "modes": modes}


def background_asset_for(ctx: StepContext, scene: Scene) -> Asset | None:
    if scene.image_asset_id:
        return ctx.db.get(Asset, scene.image_asset_id)
    if scene.location_id:
        loc = ctx.db.get(Location, scene.location_id)
        if loc and loc.background_asset_id:
            return ctx.db.get(Asset, loc.background_asset_id)
    return None
