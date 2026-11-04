"""M44: Etiketten-Layout je Typ mit automatischer Schriftgröße."""

import json
from pathlib import Path

from fastapi.testclient import TestClient
from PIL import Image, ImageDraw

from app import labelimg, labels, typesettings
from app.db import connect


def _box(c: TestClient) -> int:
    r = c.post("/quickadd", data={"mode": "container", "text": "Kiste", "kind": "box"})
    return int(r.url.path.rsplit("/", 1)[1])


def _screw(c: TestClient, box: int) -> None:
    c.post("/neu", data={"typ": "schraube", "f_head": "Zylinderkopfschraube", "f_thread": "M3",
                         "f_length": "10", "f_drive": "Innensechskant", "target": box})  # fmt: skip


def test_parse_layout_cleans_input() -> None:
    assert labels.parse_layout("") == labels.default_layout()
    assert labels.parse_layout("kaputt{") == labels.default_layout()
    lay = labels.parse_layout({"qr": "mitte", "lines": [
        {"t": "  {thread}x{length}  ", "w": 9, "a": "x"}, {"t": " ", "w": 1}, {"t": "{code}"},
        *({"t": f"z{i}"} for i in range(6))]})  # fmt: skip
    assert lay["qr"] == "left" and len(lay["lines"]) == labels.MAX_LINES
    assert lay["lines"][0] == {"t": "{thread}x{length}", "w": 4, "a": "center"}
    assert lay["lines"][1] == {"t": "{code}", "w": 1, "a": "center"}


def test_layout_lines_drop_empty() -> None:
    lay = labels.parse_layout({"lines": [{"t": "{a}x{b}"}, {"t": "{c}"}, {"t": "{code}", "w": 2}]})
    assert labels.layout_lines(lay, {"a": "M3", "b": "10", "code": "ART-1"}) == (
        ("M3x10", 1, "center"), ("ART-1", 2, "center"))  # fmt: skip


def test_auto_font_scales_into_field() -> None:
    draw = ImageDraw.Draw(Image.new("1", (320, 96)))
    short = labelimg.fit_box(draw, "M3", 200, 40)
    long = labelimg.fit_box(draw, "Zylinderkopfschraube M3x10 Innensechskant", 200, 40)
    flat = labelimg.fit_box(draw, "M3", 200, 12)
    assert short.size > long.size >= 9  # längerer Text -> kleinere Schrift
    assert short.size > flat.size  # niedrigeres Feld -> kleinere Schrift
    for font, text in ((short, "M3"), (long, "Zylinderkopfschraube M3x10 Innensechskant")):
        assert draw.textlength(text, font=font) <= 200 or font.size == 9


def test_render_layout_variants() -> None:
    base = dict(code="ART-0001", qr="HTTPS://LAGER.HOME.LAN/C/ART-0001")
    for pos in ("left", "right", "none"):
        img = labelimg.render(labels.Label(**base, lines=(("M3x10", 2, "center"), ("ART-0001", 1, "left")),
                                           qr_pos=pos))  # fmt: skip
        assert img.size == (320, 96) and img.getextrema()[0] == 0
    left = labelimg.render(labels.Label(**base, lines=(("X", 1, "center"),), qr_pos="left"))
    none = labelimg.render(labels.Label(**base, lines=(("X", 1, "center"),), qr_pos="none"))
    assert left.crop((0, 0, 90, 96)).getextrema()[0] == 0  # QR links vorhanden
    assert none.crop((0, 0, 90, 96)).getextrema()[0] == 1  # ohne QR: links leer


def test_designer_saves_and_applies_to_labels(client: TestClient, tmp_path: Path) -> None:
    box = _box(client)
    _screw(client, box)
    page = client.get("/etiketten/typ/schraube").text
    assert "Etikett: Schraube" in page and 'name="t_0"' in page and "vorschau.png" in page
    assert "Gewinde" in page and 'data-token="{thread}"' in page
    r = client.post("/etiketten/typ/schraube", data={
        "qr": "right", "t_0": "{thread}x{length}", "w_0": "3", "a_0": "center",
        "t_1": "{head} {drive}", "w_1": "1", "a_1": "left", "t_2": "{code}", "w_2": "1"})  # fmt: skip
    assert "Layout gespeichert" in r.text
    conn = connect(tmp_path / "lager.db")
    saved = json.loads(typesettings.get(conn, "schraube")["label_layout"])
    assert saved["qr"] == "right" and saved["lines"][0] == {
        "t": "{thread}x{length}",
        "w": 3,
        "a": "center",
    }
    item = conn.execute("SELECT * FROM item WHERE ctype = 'schraube'").fetchone()
    label = labels.item_label(conn, "https://lager.home.lan", item)
    assert label.qr_pos == "right" and label.text == "M3x10"
    assert [t for t, _, _ in label.lines][:2] == ["M3x10", "Zylinderkopfschraube Innensechskant"]
    client.post(
        f"/labels/queue/item/{item['id']}"
    )  # aus der Warteschlange wird das Layout wieder angewendet
    queued = labels.queue(conn, "https://lager.home.lan")[0]
    assert queued.qr_pos == "right" and queued.lines[0][0] == "M3x10"
    png = client.get(f"/labels/img/{item['code']}.png")
    assert png.status_code == 200 and png.headers["content-type"] == "image/png"
    prev = client.get("/etiketten/typ/schraube/vorschau.png",
                      params={"qr": "none", "t_0": "{thread}x{length}", "w_0": "2"})  # fmt: skip
    assert prev.status_code == 200 and prev.content[:4] == b"\x89PNG"
    r = client.post("/etiketten/typ/schraube", data={"reset": "1"})
    assert "Standard-Layout" in r.text
    assert typesettings.get(conn, "schraube")["label_layout"] == ""
    lines = labels.item_label(conn, "https://x.test", item).lines  # Standard: dreizeilig
    assert len(lines) == 3 and lines[-1][0] == item["code"]


def test_designer_preview_without_items_and_overview(client: TestClient) -> None:
    assert (
        client.get("/etiketten/typ/mutter/vorschau.png", params={"t_0": "{thread}"}).status_code
        == 200
    )
    page = client.get("/etiketten/typ").text
    assert "/etiketten/typ/schraube" in page and "/etiketten/typ/mat:cbl" in page
    assert (
        "Layout je Typ" in client.get("/labels").text
        and "/etiketten/typ" in client.get("/mehr").text
    )
