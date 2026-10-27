from pathlib import Path

from fastapi.testclient import TestClient

from app import repo
from app.db import connect


def _setup(client: TestClient) -> None:
    client.post("/quickadd", data={"mode": "container", "text": "Werkbank", "kind": "workbench"})
    client.post("/quickadd", data={"mode": "container", "text": "Kiste A", "kind": "box"})


def test_batch_moves_existing_and_creates_new_art(client: TestClient, tmp_path: Path) -> None:
    _setup(client)
    conn = connect(tmp_path / "lager.db")
    nodes = {n["name"]: n for n in conn.execute("SELECT * FROM container").fetchall()}
    for name in ("Werkbank", "Kiste A"):
        client.post(f"/n/{nodes[name]['id']}/code")
    item_id = repo.add_item(conn, nodes["Kiste A"]["id"], "Lötzinn", code="ART-0001")
    r = client.post("/api/move-batch", json={"target": "WBA-001", "entries": [
        {"code": "art1"}, {"code": "BOX-001"}, {"code": "ART-0050", "name": "Seitenschneider"},
        {"code": "ART-0051"}, {"code": "EUR-009"}]})  # fmt: skip
    d = r.json()
    assert d["msg"] == "3 von 5 nach „Werkbank“ eingeräumt" and not d["ok"]
    assert [x["ok"] for x in d["results"]] == [True, True, True, False, False]
    wb_id = nodes["Werkbank"]["id"]
    assert repo.get_item(conn, item_id)["container_id"] == wb_id
    assert repo.get_container(conn, nodes["Kiste A"]["id"])["parent_id"] == wb_id
    new = repo.get_item_by_code(conn, "ART-0050")
    assert new is not None and new["name"] == "Seitenschneider" and new["container_id"] == wb_id
    assert (
        client.post("/api/move-batch", json={"target": "XYZ-1", "entries": []}).status_code == 404
    )


def test_unknown_code_reports_prefix_and_scan_page(client: TestClient) -> None:
    assert client.get("/api/code/ART-0099").json()["prefix"] == "ART"
    page = client.get("/scan").text
    assert "Sammelmodus" in page and "batch-ok" in page and "var BEEP = true" in page
    client.post("/settings", data={"app_name": "KP Lager"})  # Checkbox fehlt = aus
    assert "var BEEP = false" in client.get("/scan").text
