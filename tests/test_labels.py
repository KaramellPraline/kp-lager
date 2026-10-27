import html
import io
import re

import pytest
import segno
from fastapi.testclient import TestClient
from httpx import Response
from openpyxl import load_workbook

from app import codes, labels


def xlsx_rows(content: bytes) -> list[tuple[object, ...]]:
    ws = load_workbook(io.BytesIO(content)).active
    assert ws is not None
    return list(ws.iter_rows(values_only=True))


def node_of(r: Response) -> str:
    return str(r.url.path).rsplit("/", 1)[1]


def preview(client: TestClient, **form: str) -> dict[str, list[str]]:
    """Vorschau öffnen und die Tabellenfelder auslesen."""
    page = client.post("/labels/preview", data=form).text
    fields: dict[str, list[str]] = {"code": [], "text": [], "extra": []}
    for name, value in re.findall(r'name="(code|text|extra)" value="([^"]*)"', page):
        fields[name].append(html.unescape(value))
    return fields


def export(
    client: TestClient, fields: dict[str, list[str]], fmt: str = "xlsx", **extra: str
) -> Response:
    return client.post("/labels/export", data={**fields, "fmt": fmt, **extra})


def test_qr_uppercase_is_alphanumeric_and_small() -> None:
    content = labels.qr_content("http://lager.home.lan", "ART-0001")
    assert content == "HTTP://LAGER.HOME.LAN/C/ART-0001"
    qr = segno.make(content, error="m")
    assert qr.mode == "alphanumeric" and qr.version <= 2  # 25×25 Module auf ~10 mm
    assert segno.make(content.lower(), error="m").version > qr.version


def test_uppercase_qr_url_resolves(client: TestClient) -> None:
    r = client.post("/containers", data={"name": "Box", "kind": "eurobox", "code": "eur1"})
    assert 'chip code">EUR-001' in r.text
    assert node_of(client.get("/C/EUR-001")) == node_of(r)
    assert node_of(client.get("/c/eur001")) == node_of(r)


def test_blank_preview_reserves_only_on_export(client: TestClient) -> None:
    fields = preview(client, source="blank", prefix="EUR", count="3")
    assert fields["code"] == ["EUR-001", "EUR-002", "EUR-003"]
    assert preview(client, source="blank", prefix="EUR", count="1")["code"] == ["EUR-001"]
    fields["text"][0] = "Elektronik"
    rows = xlsx_rows(export(client, fields).content)
    assert rows[0] == ("Code", "QR", "Text")
    assert rows[1] == ("EUR-001", "HTTPS://LAGER.TEST/C/EUR-001", "Elektronik")
    assert preview(client, source="blank", prefix="EUR", count="1")["code"] == ["EUR-004"]


def test_edit_names_and_optionally_save(client: TestClient) -> None:
    box = node_of(client.post("/containers", data={"name": "Box", "kind": "kiste"}))
    client.post(f"/n/{box}/items", data={"name": "Akkuschrauber Makita DDF485 18V"})
    fields = preview(client, source="pending")
    assert fields["code"] == ["ART-0001"] and fields["extra"] == ["Box"]
    fields["text"] = ["Akkuschrauber kurz"]
    rows = xlsx_rows(export(client, fields).content)
    assert rows[1][2] == "Akkuschrauber kurz"
    assert "Akkuschrauber Makita DDF485 18V" in client.get(f"/n/{box}").text  # nicht gespeichert
    assert "Alles gedruckt" in client.get("/labels").text
    export(client, fields, save_names="1")
    assert "Akkuschrauber kurz" in client.get(f"/n/{box}").text


def test_long_text_cut_in_xlsx_only(client: TestClient) -> None:
    fields = {
        "code": ["ART-0005"],
        "text": ["Ein wirklich sehr langer Gegenstandsname"],
        "extra": [""],
    }
    assert xlsx_rows(export(client, fields).content)[1][2] == "Ein wirklich sehr lange…"
    a8 = export(client, fields, fmt="a8").text
    assert "Ein wirklich sehr langer Gegenstandsname" in a8


def test_a8_sheet_layout(client: TestClient) -> None:
    fields = preview(client, source="blank", prefix="KIS", count="17")
    r = export(client, fields, fmt="a8")
    assert "size: A4 landscape" in r.text
    assert r.text.count('class="sheet"') == 2
    assert r.text.count('<div class="a8">') == 32  # 17 Etiketten + 15 leere Felder
    first = r.text.index('<div class="a8">')
    assert (
        r.text.index("<svg", first)
        < r.text.index('class="name"', first)
        < r.text.index("KIS-001", first)
    )
    assert "KIS-018" in preview(client, source="blank", prefix="KIS", count="1")["code"]


def test_scan_reserved_code_preselects_kind(client: TestClient) -> None:
    r = client.get("/C/SOR-007")
    assert "Etikett SOR-007 ist noch frei" in r.text
    assert re.search(r'value="sortingbox"\s+selected', r.text)
    assert 'action="/items/new"' in client.get("/C/ART-0003").text
    assert client.get("/C/XYZ-001").status_code == 404


def test_create_item_from_scanned_code(client: TestClient) -> None:
    box = node_of(client.post("/containers", data={"name": "Box", "kind": "kiste"}))
    r = client.post("/items/new", data={"code": "art-7", "container_id": box, "name": "Bohrer"})
    assert 'chip code">ART-0007' in r.text
    r = client.post(f"/n/{box}/items", data={"name": "Zange"})
    zange = re.findall(r'id="item-(\d+)"', r.text)[-1]
    assert 'chip code">ART-0008' in client.get(f"/items/{zange}").text  # Zähler läuft weiter
    fields = preview(client, source="item", item_id=zange)
    assert fields["code"] == ["ART-0008"]


def test_auto_code_toggle_and_button(client: TestClient) -> None:
    client.post("/settings", data={})
    box = node_of(client.post("/containers", data={"name": "Box", "kind": "kiste"}))
    r = client.post(f"/n/{box}/items", data={"name": "Kabel"})
    item = re.findall(r'id="item-(\d+)"', r.text)[0]
    page = client.get(f"/items/{item}").text
    assert "Etikett vergeben" in page and "ART-" not in page
    assert "Code ART-0001 vergeben" in client.post(f"/items/{item}/code").text
    assert "Code entfernt" in client.post(f"/items/{item}/code", data={"remove": "1"}).text
    client.post("/settings", data={"auto_item_code": "1"})
    assert 'name="auto_item_code" value="1" checked' in client.get("/settings").text


def test_sortierkasten_labels_one_per_item(client: TestClient) -> None:
    client.post("/settings", data={})  # auto aus: Vorschau vergibt fehlende Codes selbst
    r = client.post(
        "/containers", data={"name": "Schrauben", "kind": "sortierkasten", "grid": "2x2"}
    )
    kasten = node_of(r)
    faecher = re.findall(r'href="/n/(\d+)" class="cell', client.get(f"/n/{kasten}").text)
    client.post(f"/n/{faecher[2]}/items", data={"name": "Holzschrauben 4x40"})
    client.post(f"/n/{faecher[0]}/items", data={"name": "Dübel 6mm"})
    fields = preview(client, source="container", node_id=kasten)
    assert list(zip(fields["code"], fields["text"], fields["extra"], strict=True)) == [
        ("ART-0001", "Dübel 6mm", "A1"),
        ("ART-0002", "Holzschrauben 4x40", "B1"),
    ]
    export(client, fields)
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


@pytest.mark.parametrize(
    ("raw", "expected"),
    [("eur1", "EUR-001"), ("EUR-0001", "EUR-001"), ("art-12", "ART-0012"), (" Sor007 ", "SOR-007"),
     ("EUR-000", None), ("XYZ-001", None), ("0042", None), ("EUR-", None)],
)  # fmt: skip
def test_normalize(raw: str, expected: str | None) -> None:
    assert codes.normalize(raw) == expected


def test_default_qr_uses_schema_and_dns_name(monkeypatch: pytest.MonkeyPatch) -> None:
    from app.config import load_settings

    monkeypatch.delenv("LAGER_BASE_URL", raising=False)
    base = load_settings().base_url
    assert base == "https://lager.home.lan"
    assert (
        labels.qr_content(base, codes.format_code("EUR", 21)) == "HTTPS://LAGER.HOME.LAN/C/EUR-021"
    )


def test_preview_exports_only_xlsx(client: TestClient) -> None:
    page = client.post(
        "/labels/preview", data={"source": "blank", "prefix": "EUR", "count": "2"}
    ).text
    assert 'value="xlsx"' in page and 'value="a8"' not in page and 'value="a4"' not in page
    assert 'href="/labels/a4"' in page


def test_a4_selection_and_print(client: TestClient) -> None:
    box = node_of(
        client.post("/containers", data={"name": "Werkzeug", "kind": "kiste", "code": "KIS-001"})
    )
    client.post(f"/n/{box}/items", data={"name": "Zange"})  # ART-0001
    client.post(f"/n/{box}/items", data={"name": "Feile"})  # ART-0002
    page = client.get("/labels/a4").text
    assert all(f'value="{c}"' in page for c in ("KIS-001", "ART-0001", "ART-0002"))
    assert 'value="ART-0002"' not in client.get("/labels/a4", params={"q": "zange"}).text
    r = client.post("/labels/a4", data={"code": ["ART-0001", "KIS-001"], "fmt": "a4"})
    assert (
        "grid-template-columns: repeat(5, 40mm)" in r.text
        and "<b>ART-0001</b>" in r.text
        and "ART-0002" not in r.text
    )
    r = client.post("/labels/a4", data={"code": ["ART-0002"], "fmt": "a8"})
    assert "size: A4 landscape" in r.text and "Feile" in r.text
    r = client.post("/labels/a4", data={"fmt": "a4"}, headers={"referer": "/labels/a4"})
    assert "Nichts ausgewählt" in r.text
