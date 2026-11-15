"""Estimativa de custo antes da produção, a partir dos provedores que seriam escolhidos."""
from __future__ import annotations

from sqlalchemy.orm import Session

from app.models import Channel, ContentEngine
from app.providers.router import ProviderRouter
from app.services.costs import CallContext


def estimate_production_cost(db: Session, channel: Channel, engine: ContentEngine, duration_s: int,
                             visual_style: str | None = None) -> dict:
    router = ProviderRouter(db, CallContext(channel_id=channel.id, engine_id=engine.id, strategy=channel.provider_strategy))
    cfg = engine.config or {}
    scenes = max(3, int(duration_s / 7))
    breakdown: dict[str, float] = {}

    def first(kind: str, allow_sim: bool = True):
        c = router.candidates(kind, allow_simulated=allow_sim)
        return c[0] if c else None

    llm = first("llm")
    if llm:
        calls = [(9000, 6000), (9000, 6000), (1500, 400), (1500, 400), (1500, 400)]
        if cfg.get("requires_fact_check"):
            calls.append((3000, 1500))
        breakdown["llm"] = sum(llm.provider.estimate_cost(prompt_chars=p, max_tokens=o, model=llm.model_key) for p, o in calls)
    tts = first("tts")
    if tts:
        chars = int(duration_s * 2.6 * 6)
        breakdown["tts"] = tts.provider.estimate_cost(chars=chars, model=tts.model_key)
    mode = cfg.get("default_visual_mode", "animation_2d")
    if visual_style == "cinematic":
        mode = "ai_image"
    img = first("image", allow_sim=False)
    if img and (mode == "ai_image" or cfg.get("ai_backgrounds")):
        n = scenes if mode == "ai_image" else 2
        breakdown["image"] = img.provider.estimate_cost(count=n, model=img.model_key)
    vid = first("video", allow_sim=False)
    if vid and cfg.get("ai_video_scenes"):
        breakdown["video"] = vid.provider.estimate_cost(duration_s=6 * len(cfg["ai_video_scenes"]), model=vid.model_key)
    total = round(sum(breakdown.values()), 4)
    return {"total_usd": total, "breakdown": {k: round(v, 4) for k, v in breakdown.items()}, "scenes_estimate": scenes,
            "visual_mode": mode, "providers": {k: c.rec.key for k, c in (("llm", llm), ("tts", tts)) if c}}
