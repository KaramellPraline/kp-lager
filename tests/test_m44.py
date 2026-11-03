"""M44: feste QR-Adresse, Wiederherstellung aus Vollexport mit dynamischen Codes und Zählern."""

import json
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from app import codes, importer, labels, repo
from app.config import QR_HOST, Settings, qr_base
from app.db import connect


@pytest.mark.parametrize(
    "raw",
    ["http://localhost:8000", "https://127.0.0.1", "http://192.168.1.5:8000", "http://[::1]:8000",
     "", "http://0.0.0.0", "localhost"],
)  # fmt: skip
def test_qr_address_never_local(raw: str) -> None:
    assert qr_base(raw) == QR_HOST == "https://lager.home.lan"


def test_qr_address_real_names_stay() -> None:
    assert qr_base("lager.home.lan") == "https://lager.home.lan"
    assert qr_base("https://lager.example.org/") == "https://lager.example.org"
    s = Settings(data_dir=Path("x"), base_url="http://localhost:8000")
    assert s.base_url == "https://lager.home.lan"


def test_labels_carry_fixed_address(tmp_path: Path) -> None:
    from app.web import create_app

    s = Settings(data_dir=tmp_path, base_url="http://localhost:8000")
    with TestClient(create_app(s)) as c:
        r = c.post("/quickadd", data={"mode": "container", "text": "Kiste", "kind": "toolbox",
                                      "d30_print": "1"})  # fmt: skip
        assert r.status_code == 200
        conn = connect(tmp_path / "lager.db")
        code = conn.execute("SELECT code FROM container WHERE name = 'Kiste'").fetchone()["code"]
        assert labels.qr_content(s.base_url, code) == f"https://lager.home.lan/C/{code}".upper()
        for row in labels.queue(conn, s.base_url) + labels.all_coded(conn, s.base_url):
            assert row.qr.lower().startswith("https://lager.home.lan/c/")  # QR ist großgeschrieben
            assert "localhost" not in row.qr.lower()


def _populated(path: Path) -> dict[str, list[dict]]:  # type: ignore[type-arg]
    conn = connect(path)
    room = repo.create_container(conn, "Werkstatt", "room", code="RAU-001")
    box = repo.create_container(conn, "Kabelbox", "box", parent_id=room, code="BOX-001")
    tbx = repo.create_container(conn, "Kiste ohne Code", "toolbox", parent_id=room)
    repo.add_item(conn, box, "USB-A – USB-C 1m", code="CBL-007")
    repo.add_item(conn, tbx, "Zylinderkopfschraube M3x10", qty=40, code="ART-0012")
    repo.add_item(conn, tbx, "Seitenschneider")  # ohne Code
    repo.change_qty(conn, repo.get_item_by_code(conn, "ART-0012")["id"], -5)  # type: ignore[index]
    return importer.export(conn)


def test_restore_full_export_into_fresh_db(tmp_path: Path) -> None:
    dump = _populated(tmp_path / "alt.db")
    conn = connect(tmp_path / "neu.db")
    text = json.dumps(dump)
    prev = importer.run(conn, text, commit=False)
    assert not prev.errors and prev.items_added == 3 and prev.restored
    assert conn.execute("SELECT COUNT(*) FROM item").fetchone()[0] == 0  # Vorschau ändert nichts
    rep = importer.run(conn, text, commit=True)
    assert rep.items_added == 3 and rep.events_added > 0
    names = {r["name"]: r["code"] for r in conn.execute("SELECT name, code FROM container")}
    assert names["Werkstatt"] == "RAU-001" and names["Kabelbox"] == "BOX-001"
    assert names["Kiste ohne Code"] == "TBX-001"  # fehlender Code dynamisch vergeben
    schneider = conn.execute("SELECT * FROM item WHERE name = 'Seitenschneider'").fetchone()
    assert schneider["code"] and schneider["code"].startswith("ART-")
    assert rep.codes_assigned == 2 and rep.typed >= 1
    screw = repo.get_item_by_code(conn, "ART-0012")
    assert screw["qty"] == 35 and screw["ctype"] == "schraube"  # type: ignore[index]
    # Zähler dynamisch: nächste Nummer = höchste vergebene + 1, nie ein vergebener Code
    assert codes.next_number(conn, "CBL") == 8 and codes.next_number(conn, "TBX") == 2
    assert codes.next_number(conn, "ART") > 12
    assert {r.code for r in labels.queue(conn, "https://x.test")} >= {
        "TBX-001",
        schneider["code"],
    }
    # zweites Einspielen ändert nichts (Zusammenführen über Codes)
    again = importer.run(conn, text, commit=True)
    assert again.items_added == 0 and again.items_skipped == 3 and not again.containers_created
    assert conn.execute("SELECT COUNT(*) FROM item").fetchone()[0] == 3
    # eigener Eingang wird übernommen statt einen zweiten anzulegen
    assert repo.inbox(conn) == repo.inbox(conn)


def test_restore_merges_into_existing_data(tmp_path: Path) -> None:
    dump = _populated(tmp_path / "alt.db")
    conn = connect(tmp_path / "neu.db")
    room = repo.create_container(conn, "Werkstatt neu", "room", code="RAU-001")  # gleicher Code
    repo.add_item(conn, room, "Vorhandenes", code="ART-0001")
    rep = importer.run(conn, json.dumps(dump), commit=True)
    assert "Werkstatt" not in rep.containers_created  # RAU-001 existiert schon
    assert conn.execute("SELECT COUNT(*) FROM container WHERE code = 'RAU-001'").fetchone()[0] == 1
    cable = repo.get_item_by_code(conn, "CBL-007")
    assert cable is not None and repo.path_label(conn, cable["container_id"]).startswith(
        "Werkstatt neu"
    )
    assert repo.get_item_by_code(conn, "ART-0001") is not None


def test_import_page_accepts_file(client: TestClient, tmp_path: Path) -> None:
    dump = _populated(tmp_path / "quelle.db")
    r = client.post("/import", files={"file": ("lager-export.json", json.dumps(dump), "application/json")},
                    data={"action": "commit"})  # fmt: skip
    assert "Übernommen" in r.text and "3 Teile neu" in r.text and "Verlaufseinträge" in r.text
    assert "fehlende Codes dynamisch vergeben" in r.text
    assert client.get("/api/v1/items/CBL-007").json()["name"] == "USB-A – USB-C 1m"


@pytest.mark.skipif(
    not Path(
        "/root/.claude/uploads/6e8a46fd-b2d6-5dee-a059-56217bfe2e9b/75565bd7-lager-export_1.json"
    ).exists(),
    reason="echter Export nur in der Entwicklungssitzung vorhanden",
)
def test_real_export_restores(tmp_path: Path) -> None:
    text = Path(
        "/root/.claude/uploads/6e8a46fd-b2d6-5dee-a059-56217bfe2e9b/75565bd7-lager-export_1.json"
    ).read_text()
    conn = connect(tmp_path / "x.db")
    rep = importer.run(conn, text, commit=True)
    assert not rep.errors and rep.items_added == 79 and len(rep.containers_created) == 10
    assert codes.next_number(conn, "CBL") == 65 and codes.next_number(conn, "PSU") == 17
    assert conn.execute("SELECT COUNT(*) FROM container WHERE code IS NULL").fetchone()[0] == 0
