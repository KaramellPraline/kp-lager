"""M42: Etikettenvorlagen je Typ, Sammeldruck je Box, Schnellaktionsmenü."""

from pathlib import Path

from fastapi.testclient import TestClient

from app import labels, typesettings
from app.db import connect


def _box(c: TestClient, name: str = "Kiste") -> int:
    r = c.post("/quickadd", data={"mode": "container", "text": name, "kind": "box"})
    return int(r.url.path.rsplit("/", 1)[1])


def test_fill_template() -> None:
    v = {"thread": "M3", "length": "10", "head": "Zylinderkopfschraube"}
    assert labels.fill("{thread}x{length}", v) == "M3x10"
    assert labels.fill("{thread}x{length} {finish}", v) == "M3x10"
    assert labels.fill("{head} L{length}mm", v) == "Zylinderkopfschraube L10mm"
    assert labels.fill("{thread}x{missing}", v) == ""


def test_type_template_used_for_item_labels(client: TestClient, tmp_path: Path) -> None:
    box = _box(client)
    client.post("/neu", data={"typ": "schraube", "f_head": "Zylinderkopfschraube", "f_thread": "M3",
                              "f_length": "10", "f_drive": "Innensechskant", "target": box})  # fmt: skip
    conn = connect(tmp_path / "lager.db")
    item = conn.execute("SELECT * FROM item WHERE ctype = 'schraube'").fetchone()
    assert labels.item_texts(conn, item) == ("Zylinderkopfschraube M3x10", "Kiste")
    client.post("/sortiment/schraube/einstellungen",
                data={"label_main": "{thread}x{length}", "label_extra": "{head} {drive}"})  # fmt: skip
    assert labels.item_texts(conn, item) == ("M3x10", "Zylinderkopfschraube Innensechskant")
    assert typesettings.get(conn, "schraube")["label_main"] == "{thread}x{length}"
    client.post(f"/labels/queue/item/{item['id']}")
    queue = client.get("/labels").text
    assert "M3x10" in queue
    assert client.get(f"/labels/img/{item['code']}.png").status_code == 200


def test_collect_unprinted_labels_of_box(client: TestClient, tmp_path: Path) -> None:
    outer = _box(client, "Regal")
    r = client.post("/quickadd", data={"mode": "container", "text": "Dose", "kind": "box",
                                       "target": outer, "d30_print": ""})  # fmt: skip
    inner = int(r.url.path.rsplit("/", 1)[1])
    client.post("/quickadd", data={"target": inner, "text": "Lötzinn, Flussmittel"})
    client.post(f"/n/{outer}/code")
    conn = connect(tmp_path / "lager.db")
    n_items = conn.execute("SELECT COUNT(*) FROM item WHERE code IS NOT NULL").fetchone()[0]
    rows = labels.unprinted_in(conn, "https://x.test", outer)
    assert len(rows) == n_items + 1  # Regal (Code vergeben) + Teile in der Dose
    r = client.post(f"/labels/sammel/{outer}")
    assert f"{len(rows)} ungedruckte Etiketten aus „Regal“ vorgemerkt" in r.text
    conn.execute("UPDATE item SET label_printed = 1")
    conn.execute("UPDATE container SET label_printed = 1")
    conn.commit()
    assert "schon gedruckt" in client.post(f"/labels/sammel/{outer}").text
    assert "Sammeldruck" in client.get(f"/n/{outer}").text


def test_quick_action_markup(client: TestClient) -> None:
    box = _box(client)
    client.post("/quickadd", data={"target": box, "text": "5 Muttern"})
    page = client.get(f"/n/{box}").text
    assert 'data-qa="' in page and 'class="qa-more icon-only"' in page
    js = client.get("/static/app.js").text
    for url in (
        "/items/{id}/take",
        "/carry/item/{id}",
        "/labels/queue/item/{id}",
        "/inventur/item/{id}",
    ):
        assert url in js
