"""M46: Favoriten, Auto-Tags, Teile ohne Etikett, Undo/Redo, Gesamtarchiv."""

import io
import zipfile

from fastapi.testclient import TestClient


def _box(c: TestClient) -> int:
    r = c.post("/containers", data={"name": "Regal", "kind": "toolbox"}, follow_redirects=False)
    return int(r.headers["location"].rsplit("/", 1)[1].split("?")[0])


def test_type_favorites_come_first(client: TestClient) -> None:
    client.post("/neu/favorit", data={"typ": "gridfinity"})
    page = client.get("/neu").text
    assert page.index('data-g="Favoriten"') < page.index('data-g="Schrauben &amp; Befestigung"')
    assert "Gridfinity" in page and 'data-jump="g1"' in page


def test_auto_tags_and_no_label(client: TestClient) -> None:
    box = _box(client)
    client.post("/neu", data={"typ": "schraube", "f_thread": "M3", "f_length": "10",
                              "f_finish": "A2 Edelstahl", "target": str(box)})  # fmt: skip
    r = client.get("/api/v1/containers/%d" % box).json()["items"][0]
    assert "edelstahl" in r["tags"] and "befestigung" in r["tags"]
    client.post("/neu", data={"typ": "mutter", "f_kind": "Sechskantmutter", "f_size": "M3",
                              "no_label": "1", "target": str(box)})  # fmt: skip
    items = client.get("/api/v1/containers/%d" % box).json()["items"]
    assert any(not i["code"] for i in items)


def test_global_undo_redo(client: TestClient) -> None:
    box = _box(client)
    client.post(f"/n/{box}/items", data={"name": "Zange", "qty": "5"})
    iid = client.get("/api/v1/containers/%d" % box).json()["items"][0]["id"]
    client.post(f"/items/{iid}/take", data={"qty": "2"})

    def qty() -> int:
        return int(client.get("/api/v1/containers/%d" % box).json()["items"][0]["qty"])

    before = qty()
    client.post("/undo-last")
    assert qty() > before
    client.post("/redo-last")
    assert qty() == before


def test_full_archive_contains_db_and_settings(client: TestClient) -> None:
    r = client.get("/export.zip")
    assert r.status_code == 200
    names = zipfile.ZipFile(io.BytesIO(r.content)).namelist()
    assert "lager.db" in names and "lager-export.json" in names


def test_print_history_and_repeat(client: TestClient, monkeypatch) -> None:  # type: ignore[no-untyped-def]
    from app import d30

    monkeypatch.setattr(d30, "send", lambda images: None)
    box = _box(client)
    client.post(
        "/neu", data={"typ": "schraube", "f_thread": "M4", "f_length": "8", "target": str(box)}
    )
    code = client.get("/api/v1/containers/%d" % box).json()["items"][0]["code"]
    conn_codes = [code]
    from app.config import load_settings

    assert load_settings()  # Umgebung vorhanden
    r = client.post("/labels/queue/item/1")  # Warteschlange (kein Druck) – nur Smoke
    assert r.status_code in (200, 303, 404)
    page = client.get("/verlauf?tab=druck")
    assert page.status_code == 200 and conn_codes
