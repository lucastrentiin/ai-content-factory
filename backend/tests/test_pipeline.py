"""Fluxo completo: ideia → roteiro → personagens → cenas → voz → vídeo → QC → publicação (sem chaves de API)."""
from sqlalchemy import select

from app.core.db import SessionLocal
from app.media.ffmpeg import probe
from app.models import AgentRun, Asset, Character, ProductionJob, Publication, Scene
from app.pipeline.orchestrator import advance, approve, create_production, rerender_scene, rerun_from
from app.services.ideas import generate_ideas
from app.storage import get_storage


def _video_path(db, job):
    return get_storage().local_path(db.get(Asset, job.output_asset_id).storage_key)


def test_end_to_end_production_and_reprocessing(db, channel):
    from app.models import ContentEngine

    eng = db.scalar(select(ContentEngine).where(ContentEngine.key == "comedy"))
    ideas = generate_ideas(db, channel_id=channel.id, engine_id=eng.id, count=2)
    assert ideas and all(i.total_score > 0 and i.is_simulated for i in ideas)
    job = create_production(db, channel_id=channel.id, idea_id=ideas[0].id, autostart=False)
    jid = job.id
    assert advance(jid) == "awaiting_approval"

    with SessionLocal() as s:
        job = s.get(ProductionJob, jid)
        runs = {r.agent: r.status for r in s.scalars(select(AgentRun).where(AgentRun.production_job_id == jid))}
        assert all(v in ("succeeded", "skipped") for v in runs.values()), runs
        assert job.qc_report["passed"], job.qc_report
        assert job.is_simulated and "llm" in job.simulated_parts
        info = probe(_video_path(s, job))
        v = next(x for x in info["streams"] if x["codec_type"] == "video")
        assert (v["width"], v["height"]) == (1080, 1920)
        assert any(x["codec_type"] == "audio" for x in info["streams"])
        scenes = s.scalars(select(Scene).where(Scene.production_job_id == jid)).all()
        assert scenes and all(sc.clip_asset_id and sc.audio_asset_id for sc in scenes)
        # personagens persistentes com ficha visual e voz atribuída
        chars = s.scalars(select(Character).where(Character.channel_id == channel.id)).all()
        assert chars and all(c.visual_spec.get("style") == "cartoon" and c.voice_id for c in chars)
        pubs = s.scalars(select(Publication).where(Publication.production_job_id == jid)).all()
        assert {p.platform_key for p in pubs} == {"youtube", "tiktok"} and all(p.status == "draft" for p in pubs)
        first_output = job.output_asset_id

    # reprocessar apenas a montagem: todas as cenas vêm do cache
    with SessionLocal() as s:
        rerun_from(s, jid, "video_editor", start=False)
    assert advance(jid) == "awaiting_approval"
    with SessionLocal() as s:
        ve = s.scalar(select(AgentRun).where(AgentRun.production_job_id == jid, AgentRun.agent == "video_editor"))
        assert ve.output["rendered_scenes"] == [] and len(ve.output["cached_scenes"]) == len(scenes)
        assert s.get(ProductionJob, jid).output_asset_id != first_output

    # substituir só uma cena
    with SessionLocal() as s:
        rerender_scene(s, jid, 1)
    assert advance(jid) == "awaiting_approval"
    with SessionLocal() as s:
        ve = s.scalar(select(AgentRun).where(AgentRun.production_job_id == jid, AgentRun.agent == "video_editor"))
        assert ve.output["rendered_scenes"] == [1]
        # aprovação agenda as publicações nos horários preferenciais
        approve(s, jid)
        pubs = s.scalars(select(Publication).where(Publication.production_job_id == jid)).all()
        assert all(p.status == "scheduled" and p.scheduled_at for p in pubs)


def test_curiosity_engine_requires_human_review(db, channel):
    from app.models import ContentEngine

    eng = db.scalar(select(ContentEngine).where(ContentEngine.key == "curiosity"))
    job = create_production(db, channel_id=channel.id, engine_id=eng.id, title="Curiosidade", autostart=False,
                            target_duration_s=20)
    assert advance(job.id) == "needs_review"
    with SessionLocal() as s:
        j = s.get(ProductionJob, job.id)
        assert any("revisão humana" in r for r in j.config["review_reasons"])


def test_manual_mode_pauses_between_steps(db, channel):
    channel.autonomy_mode = "manual"
    db.commit()
    script = {"title": "Manual", "scenes": [{"narration": "Uma cena curta."}, {"narration": "Fim."}]}
    job = create_production(db, channel_id=channel.id, engine_id=1, manual_script=script, autostart=False)
    assert advance(job.id) == "paused"
    with SessionLocal() as s:
        assert s.scalar(select(AgentRun).where(AgentRun.production_job_id == job.id, AgentRun.agent == "story_writer")).status == "succeeded"
        assert s.scalar(select(AgentRun).where(AgentRun.production_job_id == job.id, AgentRun.agent == "script_editor")).status == "pending"
