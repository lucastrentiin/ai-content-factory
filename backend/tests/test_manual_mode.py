"""Modo 'Claude pela assinatura (copiar e colar)': um único colar por vídeo e por geração de ideias."""
import json

import pytest
from sqlalchemy import select

from app.core.db import SessionLocal
from app.core.errors import AwaitingManualInput
from app.models import AgentRun, ManualRequest, ModelProvider, ProductionJob, Publication
from app.pipeline.orchestrator import advance, create_production
from app.providers import manual
from app.services.ideas import generate_ideas

SCRIPT = {
    "title": "O elevador do 13º andar", "synopsis": "Ana descobre um andar que não existe.", "full_story": "...",
    "hook": "Esse prédio não tem 13º andar.", "closing": "Você apertaria o botão?", "music_mood": "suspense",
    "characters": [{"name": "Ana", "role": "main", "appearance": {"gender": "female", "hair": "long", "outfit_color": "#22c55e"}},
                   {"name": "Lucas", "role": "secondary", "appearance": {"gender": "male", "hair": "short"}}],
    "locations": [{"name": "Corredor do prédio", "setting_type": "room", "time_of_day": "night"}],
    "scenes": [
        {"index": 0, "title": "Gancho", "location": "Corredor do prédio", "narration": "O elevador parou num andar que não existia.", "camera": "zoom_in"},
        {"index": 1, "title": "Diálogo", "location": "Corredor do prédio",
         "dialogue": [{"character": "Ana", "text": "Lucas, olha o painel.", "emotion": "scared"},
                      {"character": "Lucas", "text": "Treze? Isso não existe.", "emotion": "surprised"}]},
    ],
    "hashtags": ["misterio"], "publication": {"title": "O andar que não existe", "description": "Você apertaria? Comenta!", "hashtags": ["#misterio", "#terror"]},
}


@pytest.fixture()
def manual_on(db):
    rec = db.scalar(select(ModelProvider).where(ModelProvider.adapter == "manual_paste"))
    rec.is_enabled = True
    db.commit()
    yield
    rec.is_enabled = False
    db.commit()


def test_ideas_copy_paste(db, channel, manual_on):
    with pytest.raises(AwaitingManualInput) as exc:
        generate_ideas(db, channel_id=channel.id, engine_id=1, count=2)
    db.rollback()
    req = db.get(ManualRequest, exc.value.request_id)
    assert req.status == "pending" and "## TAREFA" in req.prompt and "JSON" in req.prompt
    manual.answer(db, req, "Claro! ```json\n" + json.dumps({"ideas": [
        {"title": "O porteiro que nunca dorme", "hook": "Ele está acordado há 30 anos.", "format": "narrated_story", "duration_s": 40,
         "attention": 0.9, "retention": 0.7, "shareability": 0.6, "originality": 0.8}]}) + "\n```")
    ideas = generate_ideas(db, **req.resume["params"])
    assert len(ideas) == 1 and ideas[0].scores["attention"] == 0.9 and not ideas[0].is_simulated
    db.refresh(req)
    assert req.status == "consumed"


def test_video_needs_exactly_one_paste(db, channel, manual_on):
    job = create_production(db, channel_id=channel.id, engine_id=1, title="Teste manual", autostart=False, target_duration_s=20)
    assert advance(job.id) == "awaiting_input"
    with SessionLocal() as s:
        req = s.scalar(select(ManualRequest).where(ManualRequest.production_job_id == job.id))
        assert req.status == "pending" and req.title == "Roteiro do vídeo"
        manual.answer(s, req, "isso não é json")
        s.get(ProductionJob, job.id).status = "queued"
        s.commit()
    assert advance(job.id) == "awaiting_input"  # resposta inválida reabre o pedido com explicação
    with SessionLocal() as s:
        req = s.scalar(select(ManualRequest).where(ManualRequest.production_job_id == job.id))
        assert req.status == "pending" and "formato esperado" in req.error
        manual.answer(s, req, json.dumps(SCRIPT))
        s.get(ProductionJob, job.id).status = "queued"
        s.commit()
    assert advance(job.id) == "awaiting_approval"
    with SessionLocal() as s:
        reqs = s.scalars(select(ManualRequest).where(ManualRequest.production_job_id == job.id)).all()
        assert len(reqs) == 1 and reqs[0].status == "consumed"
        j = s.get(ProductionJob, job.id)
        assert j.title == "O elevador do 13º andar" and j.qc_report["passed"] and not j.is_simulated
        pubs = s.scalars(select(Publication).where(Publication.production_job_id == job.id)).all()
        assert pubs and all(p.title == "O andar que não existe" and "#terror" in p.hashtags for p in pubs)
        runs = {r.agent: r.status for r in s.scalars(select(AgentRun).where(AgentRun.production_job_id == job.id))}
        assert all(v in ("succeeded", "skipped") for v in runs.values()), runs


def test_api_answer_validates_json(client, manual_on):
    with SessionLocal() as s:
        r = ManualRequest(operation="write_script", title="x", prompt="p")
        s.add(r)
        s.commit()
        rid = r.id
    assert client.post(f"/api/manual-requests/{rid}/answer", json={"response": "sem json aqui"}).status_code == 422
    d = client.get("/api/dashboard").json()
    assert d["manual_mode"] is True and any(x["id"] == rid for x in d["manual_pending"])
    assert client.post(f"/api/manual-requests/{rid}/cancel").json()["status"] == "cancelled"


def _curiosity_script(sources):
    return {"title": "3 fatos sobre polvos", "music_mood": "curious",
            "characters": [{"name": "Bia", "role": "main", "appearance": {"gender": "female"}}],
            "locations": [{"name": "Estúdio", "setting_type": "lab", "time_of_day": "day"}],
            "scenes": [{"index": 0, "title": "Gancho", "location": "Estúdio", "narration": "Polvos têm três corações."},
                       {"index": 1, "title": "Fato", "location": "Estúdio", "narration": "E o sangue deles é azul."}],
            "fact_claims": [{"claim": "Polvos têm três corações", "sources": sources, "confidence": 0.95},
                            {"claim": "O sangue do polvo é azul", "sources": sources, "confidence": 0.9}],
            "publication": {"title": "Polvos são estranhos", "description": "Sabia?", "hashtags": ["#curiosidades"]}}


@pytest.mark.parametrize("reachable,expected", [(True, "awaiting_approval"), (False, "needs_review")])
def test_curiosity_fact_check_is_automatic(db, channel, manual_on, monkeypatch, reachable, expected):
    from app.models import ContentEngine
    from app.services import factcheck

    checked = []
    monkeypatch.setattr(factcheck, "url_ok", lambda u: checked.append(u) or reachable)
    eng = db.scalar(select(ContentEngine).where(ContentEngine.key == "curiosity"))
    job = create_production(db, channel_id=channel.id, engine_id=eng.id, title="Curiosidade", autostart=False, target_duration_s=20)
    assert advance(job.id) == "awaiting_input"
    with SessionLocal() as s:
        req = s.scalar(select(ManualRequest).where(ManualRequest.production_job_id == job.id))
        assert "URL completa" in req.prompt
        manual.answer(s, req, json.dumps(_curiosity_script(["https://pt.wikipedia.org/wiki/Polvo"])))
        s.get(ProductionJob, job.id).status = "queued"
        s.commit()
    assert advance(job.id) == expected
    assert checked == ["https://pt.wikipedia.org/wiki/Polvo"]  # a fonte foi realmente consultada
    with SessionLocal() as s:
        j = s.get(ProductionJob, job.id)
        if not reachable:
            assert any("sem fonte acessível" in r for r in j.config["review_reasons"])


def test_trend_analysis_is_automatic_in_manual_mode(db, manual_on):
    from app.integrations.trends.sources import TrendItem
    from app.services import trends as tsvc

    items = [TrendItem(name="Flamengo vence clássico no Maracanã", popularity=200000),
             TrendItem(name="Acidente grave na rodovia deixa mortos", popularity=500000),
             TrendItem(name="Lenda do fantasma da escola viraliza", popularity=8000)]
    created = tsvc.upsert_items(db, None, items, region="BR", language="pt-BR")
    db.commit()
    out = tsvc.analyze(db, limit=100)
    assert out["method"] == "automatic_rules"
    by = {t.name: t for t in created}
    for t in created:
        db.refresh(t)
    assert by["Flamengo vence clássico no Maracanã"].analysis["category"] == "esporte"
    assert by["Acidente grave na rodovia deixa mortos"].analysis["sensitive"] and by["Acidente grave na rodovia deixa mortos"].score == 0
    assert "horror" in by["Lenda do fantasma da escola viraliza"].analysis["adaptable_formats"]
