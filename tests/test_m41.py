"""M41: Projekt-Reservierung, Einkauf aus CSV, Rechnungstext und PDF."""

import json
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from app import invoice, projects, purchases, repo
from app.db import connect
from app.repo import LagerError


def _box(c: TestClient) -> int:
    r = c.post("/quickadd", data={"mode": "container", "text": "Kiste", "kind": "box"})
    return int(r.url.path.rsplit("/", 1)[1])


def _item(c: TestClient, box: int, text: str) -> int:
    c.post("/quickadd", data={"mode": "item", "text": text, "target": box, "cat": "CNS"})
    return int(max(i["id"] for i in c.get(f"/api/v1/containers/{box}").json()["items"]))


def _pdf(text: str) -> bytes:
    """Minimale PDF mit einer Textzeile je Zeile (Helvetica)."""
    lines = "".join(f"({t}) Tj 0 -16 Td " for t in text.splitlines())
    stream = f"BT /F1 11 Tf 50 750 Td {lines}ET".encode("latin-1")
    objs = [
        b"<< /Type /Catalog /Pages 2 0 R >>",
        b"<< /Type /Pages /Kids [3 0 R] /Count 1 >>",
        b"<< /Type /Page /Parent 2 0 R /MediaBox [0 0 612 792] /Contents 4 0 R"
        b" /Resources << /Font << /F1 5 0 R >> >> >>",
        b"<< /Length " + str(len(stream)).encode() + b" >>\nstream\n" + stream + b"\nendstream",
        b"<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica /Encoding /WinAnsiEncoding >>",
    ]
    out, offsets = b"%PDF-1.4\n", []
    for i, o in enumerate(objs, 1):
        offsets.append(len(out))
        out += f"{i} 0 obj\n".encode() + o + b"\nendobj\n"
    xref = len(out)
    out += f"xref\n0 {len(objs) + 1}\n0000000000 65535 f \n".encode()
    out += b"".join(f"{o:010d} 00000 n \n".encode() for o in offsets)
    out += f"trailer << /Size {len(objs) + 1} /Root 1 0 R >>\nstartxref\n{xref}\n%%EOF".encode()
    return out


def test_reservation_between_projects(client: TestClient, tmp_path: Path) -> None:
    box = _box(client)
    screws = _item(client, box, "20 M3 Schrauben")
    conn = connect(tmp_path / "lager.db")
    a = projects.create(conn, "Projekt A")
    b = projects.create(conn, "Projekt B")
    projects.add_line(conn, a, screws, qty=15)
    projects.add_line(conn, b, screws, qty=10)
    r = client.post(f"/projekte/{a}/reservieren")
    assert "1 Positionen reserviert" in r.text and "reserviert 15" in r.text
    bom_b = projects.compare(conn, b)
    assert bom_b["lines"][0]["free"] == 5 and bom_b["lines"][0]["short"] == 5
    assert bom_b["counts"]["teil"] == 1
    assert projects.reserve(conn, b) == 1  # B bekommt nur die freien 5
    assert projects.reserved_elsewhere(conn, screws) == 20
    page = client.get(f"/items/{screws}").text
    assert "15 für Projekt A" in page and "frei 0" in page
    line_a = projects.lines(conn, a)[0]
    projects.gather(conn, line_a["id"])  # Einsammeln hebt die Reservierung auf
    assert projects.reserved_elsewhere(conn, screws) == 5
    client.post(f"/projekte/{b}/freigeben")
    assert projects.reserved_elsewhere(conn, screws) == 0
    projects.reserve(conn, b)
    projects.set_done(conn, b, True)  # erledigt = frei
    assert projects.reserved_elsewhere(conn, screws) == 0


def test_parse_formats() -> None:
    rows = invoice.parse("Artikel;Menge;Einzelpreis;Artikelnummer;Datum\n"
                         "M3 Muttern;100;0,02;A-1;03.11.2026\nKabelbinder;2;\"1.234,50\";;")  # fmt: skip
    assert rows[0] == invoice.Line("M3 Muttern", 100, 0.02, "A-1", "", "2026-11-03", "")
    assert rows[1].price == 1234.5
    rows = invoice.parse("Name,Quantity,Item Total\nUSB-Kabel,2,9.98\n")
    assert rows[0].price == 4.99 and rows[0].qty == 2
    text = "Pos Art.-Nr. Bezeichnung Menge EP GP\n1 SKU-1234 Zylinderkopfschraube M3x10 50 0,08 4,00\n" \
           "3 x Lötzinn 0,5mm 9,90 € 29,70 €\nZwischensumme 33,70\nVersand 4,95"  # fmt: skip
    rows = invoice.parse(text)
    assert [(r.name, r.qty, r.price, r.sku) for r in rows] == [
        ("Zylinderkopfschraube M3x10", 50, 0.08, "SKU-1234"),
        ("Lötzinn 0,5mm", 3, 9.9, ""),
    ]
    with pytest.raises(LagerError):
        invoice.parse("Hallo, danke für die Bestellung")
    with pytest.raises(LagerError):
        invoice.parse("")
    assert invoice.money("1.234,56 €") == 1234.56 and invoice.money("3.99") == 3.99


def test_pdf_invoice() -> None:
    rows = invoice.parse(data=_pdf("Rechnung 4711\n2 x Kabelbinder 200mm 1,99 3,98\nSumme 3,98"),
                         filename="r.pdf")  # fmt: skip
    assert [(r.name, r.qty, r.price) for r in rows] == [("Kabelbinder 200mm", 2, 1.99)]
    with pytest.raises(LagerError):
        invoice.parse(data=b"%PDF-kaputt", filename="x.pdf")


def test_import_flow_books_and_learns_sku(client: TestClient, tmp_path: Path) -> None:
    box = _box(client)
    nuts = _item(client, box, "10 M3 Muttern")
    conn = connect(tmp_path / "lager.db")
    repo.update_item(conn, nuts, ordered_at="2026-11-01")
    csv_text = "Artikel;Menge;Einzelpreis;Artikelnummer\nM3 Muttern;100;0,02;R-77\nBME280 Sensor;1;4,50;R-88\n"
    r = client.post("/einkauf/import", data={"text": csv_text, "supplier": "Reichelt"})
    assert "2 Positionen erkannt" in r.text and f'value="item:{nuts}" selected' in r.text
    lines = invoice.preview(conn, invoice.parse(csv_text), "Reichelt")
    form = {"supplier": "Reichelt", "bought_at": "2026-11-03", "book": "1",
            "line_0": json.dumps(lines[0]["line"]), "target_0": f"item:{nuts}",
            "line_1": json.dumps(lines[1]["line"]), "target_1": "new"}  # fmt: skip
    r = client.post("/einkauf/import/uebernehmen", data=form)
    assert "1 Teile eingebucht, 1 neu" in r.text
    item = repo.get_item(conn, nuts)
    assert item["qty"] == 110 and item["price"] == 0.02 and item["ordered_at"] is None
    assert purchases.for_item(conn, nuts)[0]["supplier"] == "Reichelt"
    sensor = conn.execute("SELECT * FROM item WHERE name = 'BME280 Sensor'").fetchone()
    assert sensor["container_id"] == repo.inbox(conn) and sensor["qty"] == 1
    # Beim nächsten Import erkennt die Artikelnummer das Teil, auch unter anderem Namen
    m = invoice.match(conn, invoice.Line("Sechskantmutter DIN934 M3", 50, 0.02, "R-77"))
    assert m["item_id"] == nuts and m["how"] == "Artikelnummer"
    r = client.post("/einkauf/import/uebernehmen", data={"line_0": json.dumps(lines[0]["line"]),
                    "target_0": "skip", "code_0": "ART-9999"})  # fmt: skip
    assert "Kein Teil mit Code" in r.text
    assert "Rechnung/CSV importieren" in client.get("/einkauf").text


def test_api_import_and_reserve(tmp_path: Path) -> None:
    from app import apikeys
    from app.config import Settings
    from app.web import create_app

    with TestClient(create_app(Settings(data_dir=tmp_path, base_url="https://x.test"))) as c:
        conn = connect(tmp_path / "lager.db")
        w = {"X-API-Key": apikeys.create(conn, "w")}
        box = _box(c)
        nuts = _item(c, box, "10 M3 Muttern")
        prev = c.post(
            "/api/v1/purchases/import/preview", json={"text": "5 x M3 Muttern 0,02"}
        ).json()
        assert prev[0]["item"]["id"] == nuts
        res = c.post("/api/v1/purchases/import", headers=w, json={
            "rows": [{"line": prev[0]["line"], "target": f"item:{nuts}"}], "supplier": "X"}).json()  # fmt: skip
        assert res == {"booked": 1, "created": 0, "skipped": 0}
        p = c.post(
            "/api/v1/projects",
            headers=w,
            json={"name": "P", "lines": [{"item": str(nuts), "qty": 4}]},
        ).json()
        r = c.post(f"/api/v1/projects/{p['id']}/reserve", headers=w).json()
        assert r["lines"][0]["reserved"] == 4
        assert c.get(f"/api/v1/items/{nuts}").json()["reserved"][0]["qty"] == 4
        r = c.post(
            f"/api/v1/projects/{p['id']}/reserve", headers=w, params={"release": True}
        ).json()
        assert r["lines"][0]["reserved"] == 0
