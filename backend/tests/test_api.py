"""API: autenticação, permissões, CRUDs, proteção de credenciais, validação."""
from app.core.db import SessionLocal
from app.core.security import hash_password
from app.models import User


def test_requires_auth():
    from fastapi.testclient import TestClient

    from app.main import app

    c = TestClient(app)
    assert c.get("/api/channels").status_code == 401
    assert c.post("/api/auth/login", json={"email": "admin@example.com", "password": "errada"}).status_code == 401
    assert c.get("/api/health").json()["status"] == "ok"


def test_viewer_cannot_write(client):
    with SessionLocal() as db:
        if not db.query(User).filter_by(email="viewer@example.com").first():
            db.add(User(email="viewer@example.com", name="V", role="viewer", password_hash=hash_password("viewer123")))
            db.commit()
    from fastapi.testclient import TestClient

    from app.main import app

    c = TestClient(app)
    tok = c.post("/api/auth/login", json={"email": "viewer@example.com", "password": "viewer123"}).json()["access_token"]
    h = {"Authorization": f"Bearer {tok}"}
    assert c.get("/api/channels", headers=h).status_code == 200
    assert c.post("/api/channels", json={"name": "X"}, headers=h).status_code == 403
    assert c.get("/api/users", headers=h).status_code == 403


def test_channel_crud_and_validation(client):
    r = client.post("/api/channels", json={"name": "Histórias de Terror BR", "preferred_hours": ["25:00"]})
    assert r.status_code == 422
    r = client.post("/api/channels", json={"name": "Histórias de Terror BR", "visual_style": "stickman", "autonomy_mode": "automatic"})
    assert r.status_code == 201, r.text
    ch = r.json()
    assert ch["slug"] == "historias-de-terror-br" and len(ch["engines"]) == 6
    r = client.patch(f"/api/channels/{ch['id']}", json={"videos_per_day": 3, "settings": {"watermark": "@terror"}})
    assert r.json()["videos_per_day"] == 3 and r.json()["settings"]["watermark"] == "@terror"
    eng = ch["engines"][0]["engine_id"]
    r = client.put(f"/api/channels/{ch['id']}/engines", json=[{"engine_id": eng, "weight": 2.0}])
    assert len(r.json()["engines"]) == 1
    assert client.delete(f"/api/channels/{ch['id']}").status_code == 204


def test_provider_credentials_never_returned(client):
    provs = client.get("/api/providers").json()
    anth = next(p for p in provs if p["key"] == "anthropic")
    assert anth["status"] == "missing_credentials"
    r = client.put(f"/api/providers/{anth['id']}/credentials", json={"credentials": {"api_key": "sk-ant-segredo-123456789"}})
    body = r.json()
    assert "segredo" not in r.text
    assert body["credentials"]["api_key"]["configured"] and body["credentials"]["api_key"]["masked"].endswith("6789")
    assert body["status"] == "configured"
    client.put(f"/api/providers/{anth['id']}/credentials", json={"credentials": {"api_key": None}})
    with SessionLocal() as db:
        from app.models import ModelProvider

        assert db.get(ModelProvider, anth["id"]).credentials_encrypted is None


def test_manual_idea_and_trend_import(client, channel):
    r = client.post("/api/trends/import", json={"items": [{"name": "Desafio do espelho", "popularity": 5000}]})
    assert r.json()["imported"] == 1
    trends = client.get("/api/trends", params={"q": "espelho"}).json()["items"]
    assert trends and trends[0]["name"] == "Desafio do espelho"
    r = client.post("/api/ideas", json={"title": "O espelho que respondia", "channel_id": channel.id, "engine_id": 1,
                                        "trend_ids": [trends[0]["id"]]})
    assert r.status_code == 201, r.text
    idea = r.json()
    assert idea["status"] == "approved" and idea["total_score"] > 0 and idea["trends"][0]["name"] == "Desafio do espelho"


def test_settings_validation_and_dashboard(client):
    assert client.put("/api/settings/automation", json={"inexistente": 1}).status_code == 422
    assert client.put("/api/settings/automation", json={"ideas_per_run": "x"}).status_code == 422
    assert client.put("/api/settings/automation", json={"ideas_per_run": 5}).json()["ideas_per_run"] == 5
    d = client.get("/api/dashboard").json()
    assert "overview" in d and "Gerador de modelos (SIMULADO)" in d["simulated_providers_enabled"]


def test_api_token_auth(client):
    tok = client.post("/api/api-tokens", json={"name": "n8n"}).json()
    assert tok["token"].startswith("cf_")
    from fastapi.testclient import TestClient

    from app.main import app

    c = TestClient(app)
    assert c.get("/api/engines", headers={"Authorization": f"Bearer {tok['token']}"}).status_code == 200
    client.delete(f"/api/api-tokens/{tok['id']}")
    assert c.get("/api/engines", headers={"Authorization": f"Bearer {tok['token']}"}).status_code == 401
