from fastapi.testclient import TestClient

from app.main import app

client = TestClient(app)


def test_health() -> None:
    r = client.get("/health")
    assert r.status_code == 200
    assert r.json() == {"status": "ok"}


def test_index_loads_vendored_htmx() -> None:
    r = client.get("/")
    assert r.status_code == 200
    assert "/static/htmx.min.js" in r.text
    assert client.get("/static/htmx.min.js").status_code == 200
