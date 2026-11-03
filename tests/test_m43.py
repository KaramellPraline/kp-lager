"""M43: Offline-fähige App (Service Worker, Manifest) und Home-Assistant-Sensor."""

from datetime import date
from pathlib import Path

from fastapi.testclient import TestClient

from app import codes, repo
from app.db import connect


def _box(c: TestClient) -> int:
    r = c.post("/quickadd", data={"mode": "container", "text": "Kiste", "kind": "box"})
    return int(r.url.path.rsplit("/", 1)[1])


def test_service_worker_and_manifest(client: TestClient) -> None:
    r = client.get("/sw.js")
    assert r.status_code == 200 and r.headers["service-worker-allowed"] == "/"
    assert r.headers["cache-control"] == "no-cache" and "__V__" not in r.text
    assert "kp-lager-offline" in r.text and "/items\\/\\d+\\/(take" in r.text
    m = client.get("/manifest.webmanifest").json()
    assert m["display"] == "standalone" and m["scope"] == "/" and m["id"] == "/"
    assert any(i.get("purpose") == "maskable" for i in m["icons"])
    assert {s["url"] for s in m["shortcuts"]} == {"/scan", "/neu/go", "/suche"}
    assert "Keine Verbindung" in client.get("/offline").text
    assert 'register("/sw.js")' in client.get("/static/app.js").text


def test_home_assistant_sensor(client: TestClient, tmp_path: Path) -> None:
    box = _box(client)
    client.post("/quickadd", data={"target": box, "text": "2 Rollen Lötzinn, 5 Muttern"})
    conn = connect(tmp_path / "lager.db")
    solder = conn.execute("SELECT * FROM item WHERE name = 'Lötzinn'").fetchone()
    repo.update_item(conn, solder["id"], min_qty=5, price=9.9, expires=date.today().isoformat())
    codes.set_setting(conn, "backup_last", "2026-11-04 03:00")
    ha = client.get("/api/v1/ha").json()
    assert ha["state"] == 1
    a = ha["attributes"]
    assert a["to_buy_items"] == ["Lötzinn (3×)"] and a["to_buy_eur"] == 29.7
    assert a["expiring"] == 1 and a["expired"] == 0 and a["items"] == 2 and a["backup_ok"] is True
    one = client.get(f"/api/v1/ha/item/{solder['code']}").json()
    assert one["state"] == 2 and one["attributes"]["low"] is True and one["attributes"]["min"] == 5
    assert client.get("/api/v1/ha/item/ART-9999").status_code == 404
