"""Contexto compartilhado por um passo (agente) do pipeline de produção."""
from __future__ import annotations

import shutil
from dataclasses import dataclass, field
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.config import settings
from app.core.events import publish_event
from app.models import (
    AgentRun,
    Channel,
    ContentEngine,
    Platform,
    ProductionJob,
    Scene,
    Script,
    ScriptVersion,
    Template,
)
from app.providers.router import ProviderRouter
from app.services.costs import CallContext

DEFAULT_TEMPLATE: dict[str, Any] = {
    "width": 1080, "height": 1920, "fps": 30, "render_scale": 1.0, "crf": 20,
    "captions": {"font": "Inter", "size": 0.052, "color": "#FFFFFF", "highlight": "#FACC15", "outline": "#000000",
                 "position": "upper_middle", "uppercase": True, "karaoke": True, "words_per_caption": 3},
    "overlay_text": {"color": "#FFFFFF", "stroke": "#000000", "size": 0.055, "top": 0.08},
    "transitions": {"default": "cut", "fade_s": 0.25},
    "music": {"enabled": True, "volume": 0.16, "ducking": True},
    "sfx": {"enabled": True, "volume": 0.5},
    "audio": {"loudness_lufs": -14, "line_gap_s": 0.22, "scene_pad_s": 0.35},
    "watermark": {"text": "", "position": "top_right", "opacity": 0.55},
    "thumbnail": {"accent": "#FACC15"},
}


def deep_merge(a: dict, b: dict) -> dict:
    out = dict(a)
    for k, v in (b or {}).items():
        out[k] = deep_merge(out[k], v) if isinstance(v, dict) and isinstance(out.get(k), dict) else v
    return out


@dataclass
class StepContext:
    db: Session
    job: ProductionJob
    run: AgentRun
    channel: Channel
    engine: ContentEngine
    router: ProviderRouter
    workdir: Path
    template: dict[str, Any] = field(default_factory=dict)

    @classmethod
    def build(cls, db: Session, job: ProductionJob, run: AgentRun) -> StepContext:
        channel = db.get(Channel, job.channel_id)
        engine = db.get(ContentEngine, job.engine_id)
        tpl_row = db.get(Template, job.template_id) if job.template_id else None
        if tpl_row is None and channel and channel.default_template_id:
            tpl_row = db.get(Template, channel.default_template_id)
        if tpl_row is None:
            tpl_row = db.scalar(select(Template).where(Template.is_default.is_(True)))
        tpl = deep_merge(DEFAULT_TEMPLATE, tpl_row.config if tpl_row else {})
        tpl = deep_merge(tpl, (channel.settings or {}).get("template_overrides", {}))
        router = ProviderRouter(db, CallContext(production_job_id=job.id, channel_id=job.channel_id, engine_id=job.engine_id,
                                                agent_run_id=run.id, strategy=channel.provider_strategy if channel else "balanced"))
        wd = Path(settings.work_dir) / f"job_{job.id}"
        wd.mkdir(parents=True, exist_ok=True)
        return cls(db, job, run, channel, engine, router, wd, tpl)

    # ---- utilidades
    def log(self, message: str, **data: Any) -> None:
        ev = {"ts": datetime.now(UTC).isoformat(), "msg": message, **({"data": data} if data else {})}
        self.run.events = [*(self.run.events or []), ev][-200:]
        publish_event("agent.log", {"job_id": self.job.id, "agent": self.run.agent, "msg": message})

    def mark_simulated(self, part: str) -> None:
        parts = set(self.job.simulated_parts or [])
        if part not in parts:
            parts.add(part)
            self.job.simulated_parts = sorted(parts)
            self.job.is_simulated = True

    def script(self) -> Script:
        if not self.job.script_id:
            raise RuntimeError("Produção sem roteiro")
        return self.db.get(Script, self.job.script_id)

    def script_version(self) -> ScriptVersion:
        sc = self.script()
        return self.db.scalar(select(ScriptVersion).where(ScriptVersion.script_id == sc.id, ScriptVersion.version == sc.current_version))

    def scenes(self) -> list[Scene]:
        return list(self.db.scalars(select(Scene).where(Scene.production_job_id == self.job.id).order_by(Scene.index)))

    def platform_limits(self) -> dict[str, float]:
        keys = self.channel.platforms or ["youtube"]
        plats = self.db.scalars(select(Platform).where(Platform.key.in_(keys))).all()
        if not plats:
            return {"min": 3, "max": 60, "ideal": 45, "max_file_mb": 500}
        return {"min": max(p.min_duration_s for p in plats), "max": min(p.max_duration_s for p in plats),
                "ideal": sum(p.ideal_duration_s for p in plats) / len(plats), "max_file_mb": min(p.max_file_mb for p in plats)}

    def cleanup(self) -> None:
        shutil.rmtree(self.workdir, ignore_errors=True)
