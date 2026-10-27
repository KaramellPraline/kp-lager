import re
import sqlite3
from collections.abc import Iterator

import pytest
from fastapi.testclient import TestClient

from app import repo, withdrawals
from app.db import connect
from app.repo import LagerError


@pytest.fixture
def conn() -> Iterator[sqlite3.Connection]:
    c = connect(":memory:")
    yield c
    c.close()


def test_take_counted_cancel_and_confirm(conn: sqlite3.Connection) -> None:
    box = repo.create_container(conn, "Box", "kiste")
    item = repo.add_item(conn, box, "Lötzinn", qty=5)
    w = withdrawals.take(conn, item, 2)
    assert repo.get_item(conn, item)["qty"] == 3
    assert withdrawals.open_for_item(conn, item)[0]["days_left"] == 7
    assert "storniert" in withdrawals.cancel(conn, w)
    assert repo.get_item(conn, item)["qty"] == 5
    with pytest.raises(LagerError, match="nicht mehr offen"):
        withdrawals.cancel(conn, w)
    with pytest.raises(LagerError, match="Nur 5"):
        withdrawals.take(conn, item, 6)
    withdrawals.take(conn, item, 1)
    conn.execute("UPDATE withdrawal SET confirm_at = datetime('now', '-1 minute')")
    conn.commit()
    assert withdrawals.confirm_due(conn, force=True) == 1
    assert repo.get_item(conn, item)["qty"] == 4 and withdrawals.open_count(conn) == 0


def test_uncounted_item_archived_after_seven_days(conn: sqlite3.Connection) -> None:
    box = repo.create_container(conn, "Box", "kiste")
    item = repo.add_item(conn, box, "Kabelbinder", qty_hint="viele")
    withdrawals.take(conn, item)
    assert repo.items_in(conn, box)  # bis zur Bestätigung sichtbar
    conn.execute("UPDATE withdrawal SET confirm_at = datetime('now', '-1 day')")
    conn.commit()
    withdrawals.confirm_due(conn, force=True)
    assert repo.items_in(conn, box) == [] and repo.get_item(conn, item)["archived"] == 1


def test_take_via_item_page_and_scan(client: TestClient) -> None:
    r = client.post("/containers", data={"name": "Box", "kind": "kiste"})
    box = str(r.url.path).rsplit("/", 1)[1]
    r = client.post(f"/n/{box}/items", data={"name": "Akku", "qty": "3"})  # ART-0001
    item = re.findall(r'id="item-(\d+)"', r.text)[0]
    r = client.post(f"/items/{item}/take", data={"qty": "1"})
    assert (
        "Entnommen" in r.text
        and "Offene Entnahmen" in r.text
        and "Bestätigung in 7 Tagen" in r.text
    )
    d = client.post("/api/take", data={"code": "art1", "qty": "2"}).json()
    assert d["ok"] and d["msg"] == "„Akku“ entnommen · noch 0" and d["cancel"]
    assert client.post("/api/take", data={"code": "ART-0001"}).json()["msg"] == "Nur 0 vorhanden"
    assert not client.post("/api/take", data={"code": "KIS-001"}).json()["ok"]
    client.post(f"/withdrawals/{d['cancel']}/cancel")
    page = client.get("/entnahmen").text
    assert "storniert" in page and "offen, noch 7 Tage" in page


def test_project_gathering_flow(client: TestClient, conn: sqlite3.Connection) -> None:
    r = client.post("/containers", data={"name": "Regal", "kind": "regal"})
    regal = str(r.url.path).rsplit("/", 1)[1]
    r = client.post(f"/n/{regal}/items", data={"name": "ESP32", "qty": "4"})  # ART-0001
    esp = re.findall(r'id="item-(\d+)"', r.text)[0]
    client.post(f"/n/{regal}/items", data={"name": "Sensor BME280", "qty": "2"})  # ART-0002
    r = client.post("/quickadd", data={"mode": "project", "text": "Wetterstation"})
    assert "Projekt „Wetterstation“ angelegt" in r.text
    pid = str(r.url.path).rsplit("/", 1)[1]
    assert "Sensor BME280" in client.get(f"/projekte/{pid}", params={"q": "bme"}).text
    client.post(f"/projekte/{pid}/lines", data={"item_id": esp, "qty": "2"})
    client.post(f"/projekte/{pid}/lines", data={"name": "Gehäuse IP65"})
    page = client.get(f"/projekte/{pid}").text
    assert "0 von 2" in page and "nicht im Lager" in page and "Regal" in page
    d = client.post(f"/api/projects/{pid}/gather", data={"code": "ART-0001"}).json()
    assert d["ok"] and d["msg"] == "„ESP32“ eingesammelt · 1 von 2"
    assert "Bestand 2" in client.get(f"/projekte/{pid}").text  # 2 entnommen
    d = client.post(f"/api/projects/{pid}/gather", data={"code": "ART-0002"}).json()
    assert d["msg"].endswith("2 von 3")  # nicht geplant -> ergänzt und eingesammelt
    assert "Einsammeln per Scan" in page
    assert 'data-mode="project"' in client.get(f"/scan?projekt={pid}").text
    assert "Wetterstation" in client.get("/projekte").text
