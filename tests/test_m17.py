import sys
from collections.abc import Iterator
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from app import apikeys, repo
from app.config import Settings
from app.db import connect
from app.web import create_app

sys.path.insert(0, str(Path(__file__).parents[1] / "tools"))
import lager_cli  # noqa: E402
from lager_client import LagerClient, LagerError  # noqa: E402


@pytest.fixture
def setup(tmp_path: Path) -> Iterator[tuple[TestClient, str]]:
    s = Settings(data_dir=tmp_path, base_url="https://lager.test")
    with TestClient(create_app(s)) as c:
        conn = connect(s.db_path)
        box = repo.create_container(conn, "Werkstattkiste", "eurobox", code="EUR-001")
        repo.add_item(conn, box, "Lötzinn", qty=3, unit="Rollen", code="ART-0001")
        repo.create_container(conn, "Regal", "regal", code="REG-001")
        key = apikeys.create(conn, "test")
        conn.close()
        yield c, key


def test_read_is_open(setup: tuple[TestClient, str]) -> None:
    c, _ = setup
    hits = c.get("/api/v1/search", params={"q": "lötzinn"}).json()
    assert hits["items"][0]["code"] == "ART-0001"
    assert c.get("/api/v1/items/art-0001").json()["qty"] == 3
    box = c.get("/api/v1/containers/EUR-001").json()
    assert box["items"][0]["name"] == "Lötzinn"
    assert c.get("/api/v1/items/ART-9999").status_code == 404
    assert {t["code"] for t in c.get("/api/v1/types").json()} >= {"TYP-001"}


def test_write_needs_key(setup: tuple[TestClient, str]) -> None:
    c, key = setup
    body = {"container": "EUR-001", "text": "50 M3 Muttern"}
    assert c.post("/api/v1/items", json=body).status_code == 401
    assert (
        c.post("/api/v1/items", json=body, headers={"X-API-Key": "kpl_falsch"}).status_code == 401
    )
    r = c.post("/api/v1/items", json=body, headers={"Authorization": f"Bearer {key}"})
    assert r.status_code == 200 and r.json()[0]["qty"] == 50
    r = c.post("/api/v1/items/ART-0001/take", json={"qty": 2}, headers={"X-API-Key": key})
    assert r.json()["item"]["qty"] == 1
    r = c.post(
        "/api/v1/items/ART-0001/move", json={"container": "REG-001"}, headers={"X-API-Key": key}
    )
    assert r.json()["container_id"] == c.get("/api/v1/containers/REG-001").json()["id"]


def test_admin_keys(client: TestClient) -> None:
    page = client.post("/settings/admin/keys", data={"name": "Werkbank-PC"}).text
    assert "kpl_" in page and "Werkbank-PC" in page
    kid = int(page.split("/settings/admin/keys/")[1].split("/")[0])
    assert (
        "Werkbank-PC"
        not in client.post(f"/settings/admin/keys/{kid}/delete").text.split('id="api"')[1]
    )


def test_cli_and_client(setup: tuple[TestClient, str], capsys: pytest.CaptureFixture[str]) -> None:
    c, key = setup
    reader = LagerClient(url="http://testserver", api_key="", http=c)
    assert lager_cli.main(["suche", "lötzinn"], reader) == 0
    assert "ART-0001" in capsys.readouterr().out
    assert lager_cli.main(["entnehmen", "ART-0001"], reader) == 1
    assert "401" in capsys.readouterr().err
    writer = LagerClient(url="http://testserver", api_key=key, http=c)
    assert lager_cli.main(["neu", "EUR-001", "2 Multimeter"], writer) == 0
    assert "Multimeter" in capsys.readouterr().out
    with pytest.raises(LagerError):
        reader.move("ART-0001", "REG-001")


def test_mcp_tools(setup: tuple[TestClient, str], monkeypatch: pytest.MonkeyPatch) -> None:
    pytest.importorskip("mcp")
    import lager_mcp

    c, key = setup
    monkeypatch.setattr(
        lager_mcp, "_client", LagerClient(url="http://testserver", api_key=key, http=c)
    )
    assert lager_mcp.search("lötzinn")["items"][0]["code"] == "ART-0001"
    assert lager_mcp.take_item("ART-0001", 1)["item"]["qty"] == 2
