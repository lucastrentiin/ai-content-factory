"""Fixtures: banco de testes real (PostgreSQL) com migrations, Celery síncrono, storage temporário."""
from __future__ import annotations

import os
import tempfile
from pathlib import Path

import pytest

_TMP = Path(tempfile.mkdtemp(prefix="cf_test_"))
os.environ.setdefault("TEST_DATABASE_URL", "postgresql+psycopg://postgres@localhost:5432/factory_test")
os.environ["DATABASE_URL"] = os.environ["TEST_DATABASE_URL"]
os.environ["CELERY_EAGER"] = "true"
os.environ["STORAGE_BACKEND"] = "local"
os.environ["STORAGE_LOCAL_PATH"] = str(_TMP / "storage")
os.environ["WORK_DIR"] = str(_TMP / "work")
os.environ["LOG_JSON"] = "false"
os.environ["LOG_LEVEL"] = "WARNING"
os.environ["API_RATE_LIMIT_PER_MINUTE"] = "100000"
os.environ["LOGIN_RATE_LIMIT_PER_MINUTE"] = "100000"
for k in ("ANTHROPIC_API_KEY", "OPENAI_API_KEY", "ELEVENLABS_API_KEY", "STABILITY_API_KEY", "REPLICATE_API_TOKEN", "YOUTUBE_API_KEY"):
    os.environ.pop(k, None)


@pytest.fixture(scope="session", autouse=True)
def database():
    from alembic.config import Config
    from sqlalchemy import text

    from alembic import command
    from app.core.db import engine

    with engine.begin() as conn:
        conn.execute(text("DROP SCHEMA public CASCADE; CREATE SCHEMA public;"))
    cfg = Config(str(Path(__file__).parents[1] / "alembic.ini"))
    cfg.set_main_option("script_location", str(Path(__file__).parents[1] / "alembic"))
    command.upgrade(cfg, "head")
    from app.core.db import SessionLocal
    from app.seeds import seed

    with SessionLocal() as db:
        seed(db)
        # renderização mais rápida nos testes
        from app.models import Template

        t = db.query(Template).filter_by(is_default=True).one()
        t.config = {"render_scale": 0.4, "crf": 30, "fps": 24}
        db.commit()
    yield


@pytest.fixture()
def db():
    from app.core.db import SessionLocal

    s = SessionLocal()
    try:
        yield s
    finally:
        s.rollback()
        s.close()


@pytest.fixture(scope="session")
def client():
    from fastapi.testclient import TestClient

    from app.main import app

    c = TestClient(app)
    r = c.post("/api/auth/login", json={"email": "admin@example.com", "password": "admin12345"})
    assert r.status_code == 200, r.text
    c.headers["Authorization"] = f"Bearer {r.json()['access_token']}"
    return c


@pytest.fixture()
def channel(db):
    import uuid

    from sqlalchemy import select

    from app.models import Channel, ChannelEngine, ContentEngine

    ch = Channel(name="Canal Teste", slug=f"teste-{uuid.uuid4().hex[:8]}", niche="histórias", visual_style="cartoon",
                 default_duration_s=25, preferred_hours=["10:00", "18:00"], videos_per_day=2, platforms=["youtube", "tiktok"])
    db.add(ch)
    db.flush()
    for e in db.scalars(select(ContentEngine)):
        db.add(ChannelEngine(channel_id=ch.id, engine_id=e.id))
    db.commit()
    return ch
