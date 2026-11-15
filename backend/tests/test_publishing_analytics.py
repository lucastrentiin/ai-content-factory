"""Agendamento, publicação assistida, exportação, métricas e aprendizado com amostra mínima."""
import io
import zipfile
from datetime import UTC, datetime, timedelta

from sqlalchemy import select

from app.models import (
    ChannelEngine,
    ContentEngine,
    Experiment,
    ExperimentVariant,
    ProductionJob,
    Publication,
    PublicationMetric,
)
from app.services import analytics as an
from app.services.publishing import export_package, next_slots, publish_publication


def _job(db, channel, engine_key="storytelling", **strategy):
    eng = db.scalar(select(ContentEngine).where(ContentEngine.key == engine_key))
    j = ProductionJob(channel_id=channel.id, engine_id=eng.id, title="t", status="completed",
                      strategy={"engine": engine_key, "visual_style": "cartoon", "format": "pov", "duration_bucket": "<=30s", **strategy})
    db.add(j)
    db.flush()
    return j


def test_next_slots_respect_hours_and_daily_quota(db, channel):
    slots = next_slots(db, channel, 5, "youtube")
    assert len(slots) == 5
    days = {}
    for s in slots:
        local = s.astimezone(__import__("zoneinfo").ZoneInfo(channel.timezone))
        assert local.strftime("%H:%M") in ("10:00", "18:00")
        days[local.date()] = days.get(local.date(), 0) + 1
    assert max(days.values()) <= channel.videos_per_day
    assert slots == sorted(slots) and slots[0] > datetime.now(UTC)


def test_assisted_publication_flow(db, channel):
    j = _job(db, channel)
    p = Publication(production_job_id=j.id, channel_id=channel.id, platform_key="tiktok", title="Título", description="Desc",
                    hashtags=["#a"], status="scheduled", mode="assisted", scheduled_at=datetime.now(UTC))
    db.add(p)
    db.commit()
    p = publish_publication(db, p.id)
    assert p.status == "awaiting_manual"
    z = zipfile.ZipFile(io.BytesIO(export_package(db, p)))
    assert {"metadados.json", "legenda.txt"} <= set(z.namelist())


def test_learning_requires_minimum_sample(db, channel):
    now = datetime.now(UTC) - timedelta(days=5)
    # motor A muito melhor que B, mas só 3 amostras → sem decisão
    for k in range(3):
        for eng, views in (("storytelling", 50000), ("comedy", 300)):
            j = _job(db, channel, eng)
            p = Publication(production_job_id=j.id, channel_id=channel.id, platform_key="youtube", title="x", status="published",
                            published_at=now, mode="api")
            db.add(p)
            db.flush()
            db.add(PublicationMetric(publication_id=p.id, captured_at=now, views=views + k * 10, likes=views // 20, shares=views // 100))
    db.commit()
    an.update_strategy_arms(db, channel.id)
    dec = an.optimize_channel(db, channel.id, apply=True)
    assert "insuficientes" in dec.rationale["decision"] and dec.proposed == dec.previous
    # com amostra suficiente o peso migra para o motor melhor (com limite de variação e piso de exploração)
    for k in range(6):
        for eng, views in (("storytelling", 50000), ("comedy", 300)):
            j = _job(db, channel, eng)
            p = Publication(production_job_id=j.id, channel_id=channel.id, platform_key="youtube", title="x", status="published",
                            published_at=now, mode="api")
            db.add(p)
            db.flush()
            db.add(PublicationMetric(publication_id=p.id, captured_at=now, views=views + k * 7, likes=views // 20, shares=views // 100))
    db.commit()
    an.update_strategy_arms(db, channel.id)
    dec = an.optimize_channel(db, channel.id, apply=True)
    assert dec.applied and dec.proposed["storytelling"] > dec.previous["storytelling"] / sum(dec.previous.values())
    assert dec.proposed["comedy"] > 0  # nunca zera (piso/min_share)
    links = {db.get(ContentEngine, link.engine_id).key: link.weight for link in db.scalars(select(ChannelEngine).where(ChannelEngine.channel_id == channel.id))}
    assert links["storytelling"] > links["comedy"]
    rows = an.breakdown(db, "engine", channel.id)
    assert rows[0]["key"] == "storytelling" and rows[0]["n"] >= 9


def test_ab_test_declares_winner_only_when_significant(db, channel):
    exp = Experiment(channel_id=channel.id, name="ganchos", dimension="hook", metric="views", min_samples_per_variant=5, confidence=0.95)
    db.add(exp)
    db.flush()
    va, vb = ExperimentVariant(experiment_id=exp.id, label="A"), ExperimentVariant(experiment_id=exp.id, label="B")
    db.add_all([va, vb])
    db.flush()
    now = datetime.now(UTC) - timedelta(days=3)
    for k in range(8):
        for v, base in ((va, 1000), (vb, 3000)):
            j = _job(db, channel)
            p = Publication(production_job_id=j.id, channel_id=channel.id, platform_key="youtube", title="x", status="published",
                            published_at=now, experiment_variant_id=v.id)
            db.add(p)
            db.flush()
            db.add(PublicationMetric(publication_id=p.id, captured_at=now, views=base + k * 13))
    db.commit()
    res = an.evaluate_experiment(db, exp)
    assert exp.status == "completed" and exp.winner_variant_id == vb.id, res
