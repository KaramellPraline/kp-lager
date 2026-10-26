import io
import re

import pytest
import segno
from fastapi.testclient import TestClient
from openpyxl import load_workbook

from app import codes, labels


def xlsx_rows(content: bytes) -> list[tuple[object, ...]]:
    ws = load_workbook(io.BytesIO(content)).active
    assert ws is not None
    return list(ws.iter_rows(values_only=True))


def node_of(r: object) -> str:
    return str(r.url.path).rsplit("/", 1)[1]  # type: ignore[attr-defined]


def test_qr_uppercase_is_alphanumeric_and_small() -> None:
    content = labels.qr_content("http://lager.home.lan", "ART-0001")
    assert content == "HTTP://LAGER.HOME.LAN/C/ART-0001"
    qr = segno.make(content, error="m")
    assert qr.mode == "alphanumeric" and qr.version <= 2  # 25×25 Module auf ~10 mm
    assert segno.make(content.lower(), error="m").version > qr.version


def test_uppercase_qr_url_resolves(client: TestClient) -> None:
    r = client.post("/containers", data={"name": "Box", "kind": "eurobox", "code": "eur1"})
    assert "Code EUR-001" in r.text
    assert node_of(client.get("/C/EUR-001")) == node_of(r)
    assert node_of(client.get("/c/eur001")) == node_of(r)


def test_blank_xlsx_reserves_codes(client: TestClient) -> None:
    r = client.post("/labels/blank.xlsx", data={"prefix": "EUR", "count": "3"})
    rows = xlsx_rows(r.content)
    assert rows[0] == ("Code", "QR", "Text", "Zusatz")
    assert [row[0] for row in rows[1:]] == ["EUR-001", "EUR-002", "EUR-003"]
    assert rows[1][1] == "HTTPS://LAGER.TEST/C/EUR-001"
    r = client.post("/labels/blank.xlsx", data={"prefix": "EUR", "count": "1"})
    assert xlsx_rows(r.content)[1][0] == "EUR-004"  # nie doppelt
    assert "EUR-005" in client.get("/labels").text


def test_scan_reserved_code_preselects_kind(client: TestClient) -> None:
    r = client.get("/C/SOR-007")
    assert "Etikett SOR-007 ist noch frei" in r.text
    assert re.search(r'value="sortierkasten"\s+selected', r.text)
    assert 'action="/items/new"' in client.get("/C/ART-0003").text
    assert client.get("/C/XYZ-001").status_code == 404


def test_create_item_from_scanned_code(client: TestClient) -> None:
    box = node_of(client.post("/containers", data={"name": "Box", "kind": "kiste"}))
    r = client.post("/items/new", data={"code": "art-7", "container_id": box, "name": "Bohrer"})
    assert "Code <b>ART-0007</b>" in r.text
    r = client.post(f"/n/{box}/items", data={"name": "Zange"})
    zange = re.findall(r'id="item-(\d+)"', r.text)[-1]
    assert "Code <b>ART-0008</b>" in client.get(f"/items/{zange}").text  # Zähler läuft weiter


def test_item_code_flow_and_pending(client: TestClient) -> None:
    box = node_of(client.post("/containers", data={"name": "Box", "kind": "kiste"}))
    r = client.post(f"/n/{box}/items", data={"name": "Akkuschrauber Makita DDF485", "qty": "1"})
    item = re.search(r'id="item-(\d+)"', r.text).group(1)  # type: ignore[union-attr]
    assert "Code <b>ART-0001</b>" in client.get(f"/items/{item}").text  # automatisch (Standard an)
    assert "ART-0001 · Akkuschrauber" in client.get("/labels").text
    rows = xlsx_rows(client.post("/labels/pending.xlsx").content)
    assert rows[1][0] == "ART-0001" and rows[1][2] == "Akkuschrauber Makita DD…"
    assert rows[1][3] == "Box"
    assert "Alles gedruckt" in client.get("/labels").text


def test_auto_code_toggle_and_button(client: TestClient) -> None:
    client.post("/settings", data={})
    box = node_of(client.post("/containers", data={"name": "Box", "kind": "kiste"}))
    r = client.post(f"/n/{box}/items", data={"name": "Kabel"})
    item = re.search(r'id="item-(\d+)"', r.text).group(1)  # type: ignore[union-attr]
    page = client.get(f"/items/{item}").text
    assert "Etikett vergeben" in page and "ART-" not in page
    assert "Code ART-0001 vergeben" in client.post(f"/items/{item}/code").text
    assert "Code entfernt" in client.post(f"/items/{item}/code", data={"remove": "1"}).text
    client.post("/settings", data={"auto_item_code": "1"})
    assert 'name="auto_item_code" value="1" checked' in client.get("/settings").text


def test_sortierkasten_labels_one_per_item(client: TestClient) -> None:
    client.post("/settings", data={})  # auto aus: Export vergibt fehlende Codes selbst
    r = client.post(
        "/containers", data={"name": "Schrauben", "kind": "sortierkasten", "grid": "2x2"}
    )
    kasten = node_of(r)
    faecher = re.findall(r'href="/n/(\d+)" class="cell', client.get(f"/n/{kasten}").text)
    client.post(f"/n/{faecher[2]}/items", data={"name": "Holzschrauben 4x40"})
    client.post(f"/n/{faecher[0]}/items", data={"name": "Dübel 6mm"})
    rows = xlsx_rows(client.post(f"/n/{kasten}/labels.xlsx").content)
    assert [(r[0], r[2], r[3]) for r in rows[1:]] == [
        ("ART-0001", "Dübel 6mm", "A1"),
        ("ART-0002", "Holzschrauben 4x40", "B1"),
    ]
    assert "Alles gedruckt" in client.get("/labels").text


def test_next_code_button_and_invalid_codes(client: TestClient) -> None:
    box = node_of(client.post("/containers", data={"name": "Box", "kind": "eurobox"}))
    assert "Code EUR-001 vergeben" in client.post(f"/n/{box}/code").text
    for code, msg in (("ART-0001", "für Gegenstände"), ("0042", "passt nicht zum Code-Schema")):
        r = client.post(
            "/containers",
            data={"name": "X", "kind": "kiste", "code": code},
            headers={"referer": "/"},
        )
        assert msg in r.text


def test_a4_sheet_and_printed_marker(client: TestClient) -> None:
    r = client.get("/labels/sheet", params={"prefix": "KIS", "count": 45})
    assert r.text.count('class="sheet"') == 2 and "<b>KIS-045</b>" in r.text
    client.post("/labels/sheet/printed", data={"prefix": "KIS", "last": 45})
    r = client.get("/labels/sheet", params={"prefix": "KIS", "count": 1})
    assert "<b>KIS-046</b>" in r.text


@pytest.mark.parametrize(
    ("raw", "expected"),
    [("eur1", "EUR-001"), ("EUR-0001", "EUR-001"), ("art-12", "ART-0012"), (" Sor007 ", "SOR-007"),
     ("EUR-000", None), ("XYZ-001", None), ("0042", None), ("EUR-", None)],
)  # fmt: skip
def test_normalize(raw: str, expected: str | None) -> None:
    assert codes.normalize(raw) == expected
