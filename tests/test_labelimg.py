"""D30-Etikettenbild: 320×96, ohne Rahmen, Name passt immer einzeilig."""

import io

from fastapi.testclient import TestClient
from PIL import Image, ImageDraw

from app import labelimg
from app.labels import Label


def _label(text: str) -> Label:
    return Label("CBL-025", "HTTPS://LAGER.HOME.LAN/C/CBL-025", text)


def test_size_and_no_frame() -> None:
    img = labelimg.render(_label("USB-A – USB-A Buchse 3m"))
    assert img.size == (320, 96)
    px = img.load()
    assert px is not None
    edge = [px[x, 0] for x in range(320)] + [px[x, 95] for x in range(320)]
    edge += [px[319, y] for y in range(96)]
    assert all(v == 1 for v in edge)  # weiß – kein Rahmen
    assert any(px[x, y] == 0 for x in range(8, 88) for y in range(96))  # QR links


def test_name_shrinks_to_fit() -> None:
    draw = ImageDraw.Draw(Image.new("1", (10, 10)))
    short = labelimg.fit(draw, "USB-C", 210, 28, 10)
    long_ = labelimg.fit(draw, "USB-A – USB-A Buchse 3m extra lang", 210, 28, 10)
    assert getattr(long_, "size", 0) < getattr(short, "size", 0)
    assert draw.textlength("USB-A – USB-A Buchse 3m extra lang", font=long_) <= 210


def test_d30_bytes_length() -> None:
    data = labelimg.d30_bytes(labelimg.render(_label("x")))
    assert len(data) == 14 + 12 * 320


def test_png_route(client: TestClient) -> None:
    r = client.post("/quickadd", data={"mode": "container", "text": "Kiste", "kind": "box"})
    box = int(r.url.path.rsplit("/", 1)[1])
    client.post("/quickadd", data={"mode": "item", "cat": "CBL", "target": box,
                                   "plug_a": "USB-A", "plug_b": "USB-C", "length": "1"})  # fmt: skip
    code = client.get(f"/api/v1/containers/{box}").json()["items"][0]["code"]
    r = client.get(f"/labels/img/{code}.png")
    assert r.status_code == 200 and Image.open(io.BytesIO(r.content)).size == (320, 96)
    assert client.get("/labels/img/XXX-999.png").status_code == 404


def test_one_mm_margin_left_and_right() -> None:
    img = labelimg.render(_label("USB-A – USB-A Buchse 3m extra lang extra lang"))
    px = img.load()
    assert px is not None
    black = [x for x in range(320) for y in range(96) if px[x, y] == 0]
    assert min(black) >= 8 and max(black) <= 319 - 8  # 1 mm = 8 px
