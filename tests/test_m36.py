"""M36: API-Schlüssel mit Rechten (lesen/schreiben) und vollständige Bestandsanbindung."""

from collections.abc import Iterator
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from app import apikeys, codes, repo
from app.config import Settings
from app.db import connect
from app.web import create_app


@pytest.fixture
def api(tmp_path: Path) -> Iterator[tuple[TestClient, dict[str, str], dict[str, str]]]:
    s = Settings(data_dir=tmp_path, base_url="https://lager.test")
    with TestClient(create_app(s)) as c:
        conn = connect(s.db_path)
        repo.create_container(conn, "Kabelbox", "eurobox", code="EUR-001")
        w = {"X-API-Key": apikeys.create(conn, "pflege", "write")}
        r = {"X-API-Key": apikeys.create(conn, "planer", "read")}
        conn.close()
        yield c, w, r


def test_read_key_cannot_write_and_read_gate(api) -> None:  # type: ignore[no-untyped-def]
    c, w, r = api
    body = {"container": "EUR-001", "text": "5 Kabelbinder"}
    assert c.post("/api/v1/items", json=body).status_code == 401
    assert c.post("/api/v1/items", json=body, headers=r).status_code == 403  # nur lesen
    assert c.post("/api/v1/items", json=body, headers=w).status_code == 200
    assert c.get("/api/v1/overview").status_code == 200  # Lesen offen (Standard)


def test_read_only_with_key_when_setting_on(api, tmp_path: Path) -> None:  # type: ignore[no-untyped-def]
    c, w, r = api
    conn = connect(tmp_path / "lager.db")
    codes.set_setting(conn, "api_read_key", "1")
    assert c.get("/api/v1/overview").status_code == 401
    assert c.get("/api/v1/overview", headers={"X-API-Key": "kpl_falsch"}).status_code == 401
    assert c.get("/api/v1/overview", headers=r).status_code == 200  # Lese-Schlüssel genügt
    assert (
        c.get("/api/v1/overview", headers={"Authorization": "Bearer " + w["X-API-Key"]}).status_code
        == 200
    )
    assert apikeys.verify(conn, r["X-API-Key"]) is False and apikeys.verify(
        conn, r["X-API-Key"], "read"
    )
    assert "Lesen" in c.get("/settings/admin").text


def test_admin_creates_keys_with_scope(api) -> None:  # type: ignore[no-untyped-def]
    c, _, _ = api
    page = c.post("/settings/admin/keys", data={"name": "Nur-Lesen", "scope": "read"}).text
    assert "kpl_" in page and "Nur-Lesen" in page and ">Lesen<" in page
    assert "Rechte" in c.post("/settings/admin/keys", data={"name": "x", "scope": "root"}).text


def test_overview_tree_and_item_listing(api) -> None:  # type: ignore[no-untyped-def]
    c, w, _ = api
    c.post(
        "/api/v1/items", json={"container": "EUR-001", "text": "5 Kabelbinder, 2 Zangen"}, headers=w
    )
    ov = c.get("/api/v1/overview").json()
    assert ov["items"] == 2 and ov["containers"] >= 1 and ov["open_projects"] == 0
    tree = c.get("/api/v1/tree").json()
    assert tree[0]["code"] == "EUR-001" and tree[0]["items"] == 2
    page = c.get("/api/v1/items", params={"container": "EUR-001", "limit": 1}).json()
    assert page["total"] == 2 and len(page["items"]) == 1 and "specs" in page["items"][0]
    assert c.get("/api/v1/items", params={"low": True}).json()["total"] == 0


def test_patch_item_qty_price_and_list(api) -> None:  # type: ignore[no-untyped-def]
    c, w, _ = api
    item = c.post(
        "/api/v1/items", json={"container": "EUR-001", "text": "10 Schrauben"}, headers=w
    ).json()[0]
    ref = item["code"]
    r = c.patch(
        f"/api/v1/items/{ref}",
        json={"qty": 4, "price": 0.1, "min_qty": 8, "notes": "M3"},
        headers=w,
    ).json()
    assert r["qty"] == 4 and r["price"] == 0.1 and r["min_qty"] == 8 and r["notes"] == "M3"
    assert c.patch(f"/api/v1/items/{ref}", json={"qty_delta": 6}, headers=w).json()["qty"] == 10
    assert (
        c.patch(f"/api/v1/items/{ref}", json={"on_list": True}, headers=w).json()["on_list"] is True
    )
    assert c.get("/api/v1/shopping").json()["items"][0]["code"] == ref
    assert c.patch(f"/api/v1/items/{ref}", json={"qty": 2}).status_code == 401
    assert c.delete(f"/api/v1/items/{ref}", headers=w).json()["result"].endswith("archiviert")
    assert c.get(f"/api/v1/items/{ref}").json()["archived"] is True
    assert c.delete(f"/api/v1/items/{ref}", params={"hard": True}, headers=w).status_code == 200
    assert c.get(f"/api/v1/items/{ref}").status_code == 404


def test_create_and_move_containers(api) -> None:  # type: ignore[no-untyped-def]
    c, w, _ = api
    n = c.post("/api/v1/containers", json={"name": "Regal oben", "kind": "shelf"}, headers=w).json()
    assert n["code"] and n["name"] == "Regal oben"
    kid = c.post(
        "/api/v1/containers", json={"name": "Dose", "kind": "box", "parent": n["code"]}, headers=w
    ).json()
    assert kid["path"].startswith("Regal oben")
    moved = c.patch(
        f"/api/v1/containers/{kid['code']}", json={"name": "Dose 2", "parent": "EUR-001"}, headers=w
    ).json()
    assert moved["name"] == "Dose 2" and "Kabelbox" in moved["path"]
    assert (
        c.post(
            "/api/v1/containers", json={"name": "X", "kind": "gibtsnicht"}, headers=w
        ).status_code
        == 400
    )


def test_projects_bom_purchases_cards_inventory(api) -> None:  # type: ignore[no-untyped-def]
    c, w, _ = api
    item = c.post(
        "/api/v1/items", json={"container": "EUR-001", "text": "10 M3 Schrauben"}, headers=w
    ).json()[0]
    proj = c.post(
        "/api/v1/projects",
        headers=w,
        json={
            "name": "Wetterstation",
            "lines": [{"item": item["code"], "qty": 25}, {"name": "BME280", "qty": 1}],
        },
    ).json()
    assert proj["counts"]["teil"] == 1 and proj["counts"]["fehlt"] == 1 and not proj["complete"]
    assert proj["lines"][0]["short"] == 15
    assert c.get(f"/api/v1/projects/{proj['id']}").json()["name"] == "Wetterstation"
    assert [p["name"] for p in c.get("/api/v1/projects").json()] == ["Wetterstation"]
    shop = c.post(f"/api/v1/projects/{proj['id']}/shopping", headers=w).json()
    assert shop["on_shopping_list"] == 1
    d = c.post(
        f"/api/v1/items/{item['code']}/purchases",
        headers=w,
        json={"supplier": "Reichelt", "qty": 100, "price": 0.02},
    ).json()
    assert d["last_supplier"] == "Reichelt" and d["purchases"][0]["price"] == 0.02
    assert c.get("/api/v1/suppliers").json()[0]["name"] == "Reichelt"
    d = c.post(
        f"/api/v1/items/{item['code']}/cards",
        headers=w,
        json={"title": "Maße", "body": "Kopf 5,5 mm", "kind": "note"},
    ).json()
    assert d["cards"][0]["title"] == "Maße"
    n = c.post(
        "/api/v1/containers/EUR-001/cards", headers=w, json={"title": "Hinweis", "body": "x"}
    ).json()
    assert n["cards"][0]["title"] == "Hinweis"
    assert (
        c.post(f"/api/v1/items/{item['code']}/cards", headers=w, json={"title": " "}).status_code
        == 400
    )
    due = c.get("/api/v1/inventory/due").json()
    assert due[0]["code"] == "EUR-001" and due[0]["items"] == 1
    ok = c.post(f"/api/v1/inventory/items/{item['code']}", headers=w, json={"qty": 9}).json()
    assert "Menge 10 → 9" in ok["result"] and ok["item"]["qty"] == 9
    assert c.post("/api/v1/inventory/containers/EUR-001/done", headers=w).json() == {
        "unconfirmed": 0
    }
    assert c.get("/api/v1/inventory/due").json() == []


def test_client_methods_roundtrip(api) -> None:  # type: ignore[no-untyped-def]
    import sys

    sys.path.insert(0, str(Path(__file__).parents[1] / "tools"))
    from lager_client import LagerClient

    c, w, r = api
    lc = LagerClient(url="http://testserver", api_key=w["X-API-Key"], http=c)
    item = lc.add("EUR-001", "4 Muttern")[0]
    assert lc.patch_item(item["code"], qty=7, price=0.05)["qty"] == 7
    proj = lc.create_project("Test", [{"item": item["code"], "qty": 10}])
    assert proj["lines"][0]["short"] == 3
    assert lc.project_to_shopping(proj["id"])["on_shopping_list"] == 1
    assert lc.overview()["to_buy"] == 1 and lc.tree()[0]["code"] == "EUR-001"
    assert lc.items(low=False)["total"] == 1 and lc.projects()[0]["name"] == "Test"
    ro = LagerClient(url="http://testserver", api_key=r["X-API-Key"], http=c)
    assert ro.overview()["items"] == 1
    try:
        ro.patch_item(item["code"], qty=1)
        raise AssertionError("Lese-Schlüssel darf nicht schreiben")
    except Exception as exc:
        assert "403" in str(exc)
