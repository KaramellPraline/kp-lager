"""Etikett als Bild für den D30 (40×12 mm bei 203 dpi = 320×96 px), ohne Rahmen.

Links der QR, rechts oben der Name (mittig, Schrift passt sich an – nie Zeilenumbruch),
darunter die ID groß und mittig.
"""

import io

import segno
from PIL import Image, ImageDraw, ImageFont

from app.labels import Label

W, H = 320, 96
QR_BOX = 80  # maximale QR-Kantenlänge in px (10 mm)
GAP = 6
NAME_MAX, NAME_MIN = 28, 10
ID_MAX, ID_MIN = 40, 14

_FONTS = (
    "Roboto-Regular.ttf",
    "DejaVuSans.ttf",
    "arial.ttf",
    "C:/Windows/Fonts/arial.ttf",
    "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf",
    "/usr/share/fonts/truetype/liberation/LiberationSans-Regular.ttf",
)


def _font(size: int) -> "Font":
    for name in _FONTS:
        try:
            return ImageFont.truetype(name, size)
        except OSError:
            continue
    return ImageFont.load_default(size)


Font = ImageFont.FreeTypeFont | ImageFont.ImageFont


def fit(draw: ImageDraw.ImageDraw, text: str, width: int, biggest: int, smallest: int) -> Font:
    """Größte Schrift, bei der der Text einzeilig in die Breite passt."""
    for size in range(biggest, smallest - 1, -1):
        font = _font(size)
        if draw.textlength(text, font=font) <= width:
            return font
    return _font(smallest)


def _qr(content: str) -> Image.Image:
    qr = segno.make(content, error="m")
    buf = io.BytesIO()
    qr.save(buf, kind="png", scale=1, border=0)
    small = Image.open(buf).convert("1")
    scale = max(1, QR_BOX // small.width)  # ganze Pixel je Modul = scharf
    return small.resize((small.width * scale, small.height * scale), Image.Resampling.NEAREST)


def render(label: Label) -> Image.Image:
    img = Image.new("1", (W, H), 1)
    draw = ImageDraw.Draw(img)
    code = _qr(label.qr)
    img.paste(code, (4, (H - code.height) // 2))
    left = 4 + code.width + GAP
    area = W - left - 4
    cx = left + area // 2
    if label.text.strip():
        name = label.text.strip()
        nf = fit(draw, name, area, NAME_MAX, NAME_MIN)
        draw.text((cx, 26), name, font=nf, fill=0, anchor="mm")
        idf = fit(draw, label.code, area, ID_MAX, ID_MIN)
        draw.text((cx, 66), label.code, font=idf, fill=0, anchor="mm")
    else:
        idf = fit(draw, label.code, area, ID_MAX + 6, ID_MIN)
        draw.text((cx, H // 2), label.code, font=idf, fill=0, anchor="mm")
    return img


def png(label: Label) -> bytes:
    buf = io.BytesIO()
    render(label).save(buf, format="PNG")
    return buf.getvalue()


def d30_bytes(img: Image.Image) -> bytes:
    """Rohdaten für den D30 (Phomemo-Protokoll): Bild um 90° gedreht, 1 Bit je Pixel."""
    rot = img.rotate(90, expand=True)  # 96 breit × 320 hoch
    px = rot.load()
    assert px is not None
    out = bytearray.fromhex("1f1124001b401d7630000c004001")
    for y in range(rot.height):
        for bx in range(rot.width // 8):
            byte = 0
            for bit in range(8):
                if px[bx * 8 + bit, y] == 0:
                    byte |= 1 << (7 - bit)
            out.append(byte)
    return bytes(out)
