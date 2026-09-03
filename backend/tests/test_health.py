from fastapi.testclient import TestClient

from app.main import app

client = TestClient(app)


def test_root_ok():
    r = client.get("/")
    assert r.status_code == 200
    body = r.json()
    assert body["name"] == "Warden"
    assert "health" in body


def test_liveness_is_ok_regardless_of_db():
    r = client.get("/health/live")
    assert r.status_code == 200
    assert r.json()["status"] == "ok"


def test_readiness_reports_db_status():
    # DB may or may not be reachable in a test environment; the endpoint must
    # respond 200 and always include a checks.database block.
    r = client.get("/health/ready")
    assert r.status_code == 200
    body = r.json()
    assert body["service"] == "warden-backend"
    assert body["status"] in {"ok", "degraded"}
    assert "database" in body["checks"]
    assert isinstance(body["checks"]["database"]["ok"], bool)
