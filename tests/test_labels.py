import html
import re

import pytest
import segno
from fastapi.testclient import TestClient
from httpx import Response

from app import codes, labels


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
    client: TestClient, fields: dict[str, list[str]], fmt: str = "a4q", **extra: str
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
    page = export(client, fields).text  # landet in der A4-Warteschlange (nie automatisch gedruckt)
    assert "Elektronik" in page and "EUR-003" in page
    assert preview(client, source="blank", prefix="EUR", count="1")["code"] == ["EUR-004"]


def test_edit_names_and_optionally_save(client: TestClient) -> None:
    box = node_of(client.post("/containers", data={"name": "Box", "kind": "kiste"}))
    client.post(f"/n/{box}/items", data={"name": "Akkuschrauber Makita DDF485 18V"})
    fields = preview(client, source="pending")
    assert fields["code"] == ["ART-0001"] and fields["extra"] == ["Box"]
    fields["text"] = ["Akkuschrauber kurz"]
    assert "Akkuschrauber kurz" in export(client, fields).text
    assert "Akkuschrauber Makita DDF485 18V" in client.get(f"/n/{box}").text  # nicht gespeichert
    export(client, fields, save_names="1")
    assert "Akkuschrauber kurz" in client.get(f"/n/{box}").text


def test_a4_packing_and_pdf() -> None:
    from app import a4

    sizes = [(50.0, 20.0)] * 40 + [(100.0, 60.0)] * 3 + [(194.0, 30.0)]
    pages = a4.pack(sizes)
    placed = [p for page in pages for p in page]
    assert len(placed) == len(sizes) and len(pages) >= 2
    for page in pages:  # nichts außerhalb des Randes, nichts überlappt
        boxes = [(x, y, x + sizes[i][0], y + sizes[i][1]) for i, x, y in page]
        for x0, y0, x1, y1 in boxes:
            assert x0 >= a4.MARGIN and y0 >= a4.MARGIN
            assert x1 <= a4.PAGE_W - a4.MARGIN + 1e-6 and y1 <= a4.PAGE_H - a4.MARGIN + 1e-6
        for i, a in enumerate(boxes):
            for b in boxes[i + 1 :]:
                assert a[2] <= b[0] or b[2] <= a[0] or a[3] <= b[1] or b[3] <= a[1]
    jobs = [{"type": "box", "title": "Schrauben", "w": 100, "h": 60, "color": "red",
             "code": "EUR-001", "qr": "HTTPS://X/C/EUR-001"},
            {"type": "tag", "title": "Zange", "code": "ART-0001", "qr": "HTTPS://X/C/ART-0001"}]  # fmt: skip
    assert a4.pdf(jobs)[:5] == b"%PDF-"
    img = a4.render(jobs[0])
    assert img.size == (a4.mm(100), a4.mm(60))
    assert any(px[0] > 150 and px[1] < 80 for px in img.getdata())  # rote Pixel vorhanden


def test_a4_queue_never_prints_without_confirmation(client: TestClient) -> None:
    box = node_of(
        client.post("/containers", data={"name": "Werkzeug", "kind": "kiste", "code": "KIS-001"})
    )
    client.post(f"/n/{box}/items", data={"name": "Zange"})
    r = client.post("/a4/queue/item/1")
    assert "in der A4-Warteschlange" in r.text and "Zange" in client.get("/a4").text
    client.post("/a4/add", data={"type": "box", "title": "Werkstatt", "w": "120", "h": "50",
                                 "color": "red"})  # fmt: skip
    page = client.get("/a4").text
    assert "A4-Warteschlange (2)" in page and "Box-Label" in page and "rot" in page
    assert client.get("/a4/seite/1.png").content[:4] == b"\x89PNG"
    assert client.get("/a4/queue.pdf").content[:5] == b"%PDF-"
    assert "nicht bestätigt" in client.post("/a4/drucken", data={}).text
    assert "Kein A4-Netzwerkdrucker" in client.post("/a4/drucken", data={"confirm": "1"}).text
    assert "A4-Warteschlange (2)" in client.get("/a4").text  # nichts verloren


def test_a4_ipp_print_sends_pdf_and_clears(client: TestClient) -> None:
    import threading
    from http.server import BaseHTTPRequestHandler, HTTPServer

    seen: dict[str, bytes] = {}

    class Fake(BaseHTTPRequestHandler):
        def do_POST(self) -> None:
            seen["body"] = self.rfile.read(int(self.headers["Content-Length"]))
            seen["ctype"] = self.headers["Content-Type"].encode()
            self.send_response(200)
            self.send_header("Content-Type", "application/ipp")
            self.end_headers()
            self.wfile.write(b"\x02\x00\x00\x00\x00\x00\x00\x01\x03")

        def log_message(self, *args: object) -> None:
            pass

    srv = HTTPServer(("127.0.0.1", 0), Fake)
    threading.Thread(target=srv.handle_request, daemon=True).start()
    client.post("/a4/add", data={"type": "box", "title": "Werkstatt", "w": "120", "h": "50"})
    url = f"ipp://127.0.0.1:{srv.server_port}/ipp/print"
    client.post("/settings/admin/a4drucker", data={"a4_printer": url})
    r = client.post("/a4/drucken", data={"confirm": "1"})
    assert "1 Etiketten auf 1 Seite gedruckt" in r.text
    assert seen["ctype"] == b"application/ipp" and b"%PDF-" in seen["body"]
    assert b"application/pdf" in seen["body"]
    assert "A4-Warteschlange (0)" in client.get("/a4").text
    srv.server_close()


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
    for code, msg in (
        ("ART-0001", "für Teile, nicht für Behälter"),
        ("0042", "passt nicht zum Code-Schema"),
    ):
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


def test_preview_offers_a4_queue_not_xlsx(client: TestClient) -> None:
    page = client.post(
        "/labels/preview", data={"source": "blank", "prefix": "EUR", "count": "2"}
    ).text
    assert 'value="a4q"' in page and "xlsx" not in page.lower() and 'value="a8"' not in page
