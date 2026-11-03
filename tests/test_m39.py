"""M39: Typen am Teil, Sortiment mit Filter/Raster, Dubletten, eigene Typen, Altbestand."""

from pathlib import Path

from fastapi.testclient import TestClient

from app import catalog, repo, sortiment
from app.db import connect


def _box(c: TestClient, name: str = "Kiste") -> int:
    r = c.post("/quickadd", data={"mode": "container", "text": name, "kind": "box"})
    return int(r.url.path.rsplit("/", 1)[1])


def _screw(
    c: TestClient, box: int, thread: str, length: str, qty: str = "10", **extra: str
) -> None:
    c.post("/neu", data={"typ": "schraube", "f_head": "Zylinderkopfschraube", "f_thread": thread,
                         "f_length": length, "qty": qty, "target": box, **extra})  # fmt: skip


def test_catalog_stores_type_and_fields(client: TestClient, tmp_path: Path) -> None:
    box = _box(client)
    _screw(client, box, "M3", "10")
    conn = connect(tmp_path / "lager.db")
    item = conn.execute("SELECT * FROM item WHERE ctype = 'schraube'").fetchone()
    assert catalog.values_of(item) == {
        "head": "Zylinderkopfschraube",
        "thread": "M3",
        "length": "10",
    }
    page = client.get(f"/items/{item['id']}").text
    assert 'id="typ"' in page and "Typ: <a" in page and "<dd>M3</dd>" in page
    r = client.post(f"/items/{item['id']}/typ", data={"typ": "schraube", "f_head": "Senkkopfschraube",
                    "f_thread": "M3", "f_length": "12", "rename": "1"})  # fmt: skip
    assert "Senkkopfschraube M3x12" in r.text
    assert repo.get_item(conn, item["id"])["name"] == "Senkkopfschraube M3x12"


def test_duplicate_warning_adds_quantity(client: TestClient, tmp_path: Path) -> None:
    box = _box(client)
    _screw(client, box, "M3", "10", qty="10")
    r = client.post("/neu", data={"typ": "schraube", "f_head": "zylinderkopfschraube", "f_thread": "m3",
                                  "f_length": "10", "qty": "5", "target": box})  # fmt: skip
    assert "gibt es schon" in r.text and 'name="force" value="1"' in r.text
    conn = connect(tmp_path / "lager.db")
    item = conn.execute("SELECT * FROM item WHERE ctype = 'schraube'").fetchone()
    r = client.post(f"/neu/dublette/{item['id']}", data={"qty": "5"})
    assert "+5 → 15" in r.text and repo.get_item(conn, item["id"])["qty"] == 15
    client.post("/neu", data={"typ": "schraube", "f_head": "Zylinderkopfschraube", "f_thread": "M3",
                              "f_length": "10", "qty": "5", "target": box, "force": "1"})  # fmt: skip
    assert conn.execute("SELECT COUNT(*) FROM item WHERE ctype = 'schraube'").fetchone()[0] == 2


def test_sortiment_filter_natural_sort_and_raster(client: TestClient) -> None:
    box = _box(client)
    for thread, length in (("M10", "20"), ("M3", "10"), ("M2.5", "8"), ("M3", "8")):
        _screw(client, box, thread, length)
    page = client.get("/sortiment").text
    assert "/sortiment/schraube" in page and "4 Teile" in page
    page = client.get("/sortiment/schraube").text
    names = [n for n in ("M2.5x8", "M3x8", "M3x10", "M10x20") if n in page]
    assert names == ["M2.5x8", "M3x8", "M3x10", "M10x20"]
    assert [page.index(n) for n in names] == sorted(page.index(n) for n in names)
    page = client.get("/sortiment/schraube", params={"f_thread": "M3"}).text
    assert "M3x8" in page and "M2.5x8" not in page.split('<ul class="list">')[1]
    grid = client.get(
        "/sortiment/schraube", params={"ansicht": "raster", "row": "thread", "col": "length"}
    ).text
    assert 'class="raster"' in grid and "<th>M2.5</th>" in grid and "<th>20</th>" in grid
    assert grid.count('class="has"') == 4 and 'class="empty"' in grid


def test_raster_for_material_profiles(client: TestClient) -> None:
    box = _box(client)
    for plug_b, length in (("USB-C", "1"), ("USB-C", "2"), ("Micro-USB", "1")):
        client.post("/quickadd", data={"mode": "item", "cat": "CBL", "target": box, "plug_a": "USB-A",
                                       "plug_b": plug_b, "length": length})  # fmt: skip
    grid = client.get(
        "/sortiment/mat:cbl", params={"ansicht": "raster", "row": "plug_b", "col": "length"}
    ).text
    assert "<th>USB-C</th>" in grid and grid.count('class="has"') == 3


def test_custom_types(client: TestClient, tmp_path: Path) -> None:
    r = client.post("/sortiment/eigene", data={
        "label": "Zahnriemen", "cat": "CNS", "fields": "Profil | GT2, GT3\nBreite | 6, 9 | mm",
        "name_tpl": "Zahnriemen {profil} {breite}mm"})  # fmt: skip
    assert "Typ gespeichert" in r.text and "Zahnriemen" in r.text and "GT2" in r.text
    box = _box(client)
    client.post(
        "/neu", data={"typ": "c_zahnriemen", "f_profil": "GT2", "f_breite": "6", "target": box}
    )
    conn = connect(tmp_path / "lager.db")
    item = conn.execute("SELECT * FROM item WHERE ctype = 'c_zahnriemen'").fetchone()
    assert item["name"] == "Zahnriemen GT2 6mm" and item["code"].startswith("CNS-")
    assert "Zahnriemen" in client.get("/sortiment").text
    assert "Feld" in client.post("/sortiment/eigene", data={"label": "X", "fields": "  "}).text
    assert (
        "unbekanntes Feld"
        in client.post(
            "/sortiment/eigene", data={"label": "Y", "fields": "A", "name_tpl": "{b}"}
        ).text
    )
    r = client.post("/sortiment/eigene/c_zahnriemen/delete")
    assert "1 Teile ohne Typ" in r.text and repo.get_item(conn, item["id"])["ctype"] is None


def test_guess_and_assign_old_items(client: TestClient, tmp_path: Path) -> None:
    box = _box(client)
    client.post(
        "/quickadd",
        data={
            "target": box,
            "text": "Zylinderkopfschraube M4x16, Sechskantmutter M4, Akkuschrauber",
        },
    )
    assert catalog.guess(None, "Widerstand 10k")[0] == "passiv"  # type: ignore[index]
    page = client.get("/sortiment/zuordnen").text
    assert "3 Teile haben noch keinen Typ" in page and "thread=M4" in page
    conn = connect(tmp_path / "lager.db")
    rows = {r["name"]: r for r in sortiment.untyped(conn)}
    screw, nut = rows["Zylinderkopfschraube M4x16"], rows["Sechskantmutter M4"]
    assert rows["Akkuschrauber"]["guess"] is None
    r = client.post("/sortiment/zuordnen", data={
        "sel": [str(screw["id"]), str(nut["id"])],
        f"typ_{screw['id']}": "schraube", f"vals_{screw['id']}": '{"thread": "M4", "length": "16"}',
        f"typ_{nut['id']}": "mutter", f"vals_{nut['id']}": '{"thread": "M4"}'})  # fmt: skip
    assert "2 Teile zugeordnet" in r.text
    assert repo.get_item(conn, screw["id"])["ctype"] == "schraube"
    assert sortiment.count_untyped(conn) == 1


def test_api_types(tmp_path: Path) -> None:
    from app import apikeys
    from app.config import Settings
    from app.web import create_app

    with TestClient(create_app(Settings(data_dir=tmp_path, base_url="https://x.test"))) as c:
        conn = connect(tmp_path / "lager.db")
        w = {"X-API-Key": apikeys.create(conn, "w")}
        box = _box(c)
        _screw(c, box, "M3", "10")
        types = c.get("/api/v1/types/catalog").json()
        screw = next(t for t in types if t["key"] == "schraube")
        assert screw["items"] == 1 and "M3" in screw["fields"][1]["options"]
        items = c.get("/api/v1/types/catalog/schraube/items").json()
        assert items[0]["fields"]["thread"] == "M3"
        ref = items[0]["code"]
        d = c.patch(
            f"/api/v1/items/{ref}", headers=w, json={"fields": {"length": "12"}, "rename": True}
        ).json()
        assert (
            d["name"] == "Zylinderkopfschraube M3x12"
            and d["fields"]["length"] == "12"
            and d["ctype"] == "schraube"
        )
        assert (
            c.patch(f"/api/v1/items/{ref}", headers=w, json={"ctype": ""}).json()["ctype"] is None
        )
        assert c.get("/api/v1/types/catalog/gibtsnicht/items").status_code == 404
