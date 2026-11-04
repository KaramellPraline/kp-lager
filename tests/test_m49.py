"""M49: Zuletzt-Vorlage, Varianten-Reihe, Pflichtfelder, Merken, Live-Etikett, Sammel-Feld, Node-Liste."""

from pathlib import Path

from fastapi.testclient import TestClient

from app import catalog, labels, typesettings
from app.db import connect


def _box(c: TestClient) -> int:
    r = c.post("/containers", data={"name": "Regal", "kind": "toolbox"}, follow_redirects=False)
    return int(r.headers["location"].rsplit("/", 1)[1].split("?")[0])


def test_every_type_has_code_line_and_optional_fields() -> None:
    for t in catalog.TYPES:
        lay = labels.parse_layout(catalog.default_label_layout(t))
        assert lay["lines"][-1]["t"] == "{code}", t.key
        assert len(lay["lines"]) >= 2, t.key
        assert any(f.extra for f in t.fields), t.key  # jeder Typ hat Weitere Angaben
    assert {f.key for f in catalog.BY_KEY["schraube"].fields} >= {"strength", "standard", "coating"}


def test_series_creates_one_item_per_value(client: TestClient, tmp_path: Path) -> None:
    box = _box(client)
    r = client.post("/neu", data={"typ": "schraube", "f_head": "Zylinderkopfschraube",
                                  "f_thread": "M3", "series_field": "length",
                                  "series_values": "6, 8; 10", "target": str(box)})  # fmt: skip
    assert "3 Teile angelegt" in r.text
    conn = connect(tmp_path / "lager.db")
    names = [x["name"] for x in conn.execute("SELECT name FROM item WHERE ctype='schraube'")]
    assert sorted(names) == ["Zylinderkopfschraube M3x10", "Zylinderkopfschraube M3x6",
                             "Zylinderkopfschraube M3x8"]  # fmt: skip


def test_required_fields_and_keep(client: TestClient, tmp_path: Path) -> None:
    box = _box(client)
    client.post("/neu/pflicht", data={"typ": "schraube", "req_length": "1"})
    page = client.get("/neu?typ=schraube").text
    assert 'title="Pflichtfeld"' in page
    r = client.post("/neu", data={"typ": "schraube", "f_thread": "M3", "target": str(box)})
    assert "Pflichtfeld fehlt: Länge" in r.text
    r = client.post("/neu", data={"typ": "schraube", "f_thread": "M3", "f_length": "8",
                                  "f_strength": "8.8", "keeps": "1", "keep_strength": "1",
                                  "target": str(box)})  # fmt: skip
    assert "angelegt" in r.text
    conn = connect(tmp_path / "lager.db")
    assert typesettings.kept_values(conn, "schraube") == {"strength": "8.8"}
    assert 'value="8.8"' in client.get("/neu?typ=schraube").text  # vorbelegt


def test_live_label_png_and_designer_back(client: TestClient) -> None:
    r = client.get("/neu/etikett.png", params={"typ": "insert", "f_kind": "Heat-Set Insert",
                                              "f_thread": "M3", "f_length": "3", "f_od": "4.2"})  # fmt: skip
    assert r.status_code == 200 and r.content[:4] == b"\x89PNG"
    page = client.get("/neu?typ=insert").text
    assert 'id="label-live"' in page and "/etiketten/typ/insert?back=" in page
    designer = client.get("/etiketten/typ/insert?back=/neu?typ=insert%26draft=1").text
    assert 'name="back"' in designer
    r = client.post("/etiketten/typ/insert", data={"qr": "left", "t_0": "{kind}", "w_0": "2",
                                                  "back": "/neu?typ=insert&draft=1"},
                    follow_redirects=False)  # fmt: skip
    assert r.headers["location"].startswith("/neu?typ=insert&draft=1")


def test_last_template_and_duplicate_link(client: TestClient, tmp_path: Path) -> None:
    box = _box(client)
    client.post("/neu", data={"typ": "mutter", "f_kind": "Sechskantmutter", "f_thread": "M4",
                              "target": str(box)})  # fmt: skip
    assert 'id="use-last"' in client.get("/neu?typ=mutter").text
    conn = connect(tmp_path / "lager.db")
    item = conn.execute("SELECT id FROM item WHERE ctype='mutter'").fetchone()
    assert f"/neu?typ=mutter&vorlage={item['id']}" in client.get(f"/items/{item['id']}").text
    assert 'value="M4"' in client.get(f"/neu?typ=mutter&vorlage={item['id']}").text


def test_bulk_set_type_field_and_node_types(client: TestClient, tmp_path: Path) -> None:
    box = _box(client)
    client.post("/neu", data={"typ": "insert", "f_kind": "Aluinsert", "f_thread": "M3",
                              "target": str(box)})  # fmt: skip
    conn = connect(tmp_path / "lager.db")
    item = conn.execute("SELECT id FROM item WHERE ctype='insert'").fetchone()
    client.post("/settings/admin/nodetypen", data={"node_types": "Nut 6\nMein Node"})
    assert catalog.node_types(conn) == ["Nut 6", "Mein Node"]
    assert "Mein Node" in client.get("/neu?typ=insert").text
    r = client.post("/bulk", data={"ref": f"i{item['id']}", "action": "field", "field": "node",
                                   "value": "Mein Node"})  # fmt: skip
    assert "1 Teile" in r.text
    got = conn.execute("SELECT cfields FROM item WHERE id=?", (item["id"],)).fetchone()
    assert '"node": "Mein Node"' in got["cfields"]


def test_print_set_queues_without_d30(client: TestClient) -> None:
    box = _box(client)
    for n in ("M3", "M4"):
        client.post("/neu", data={"typ": "mutter", "f_thread": n, "target": str(box)})
    page = client.get("/neu?typ=mutter").text
    assert "Etiketten drucken (Satz)" in page
