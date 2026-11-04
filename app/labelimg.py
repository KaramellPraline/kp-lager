"""Etikett als Bild für den D30 (40×12 mm bei 203 dpi = 320×96 px), ohne Rahmen.

Links der QR, rechts oben der Name (mittig, Schrift passt sich an – nie Zeilenumbruch),
darunter die ID groß und mittig.
"""

import io
from pathlib import Path

import segno
from PIL import Image, ImageDraw, ImageFont

from app.labels import Label

W, H = 320, 96
QR_BOX = 80  # maximale QR-Kantenlänge in px (10 mm)
GAP = 6
MARGIN = 8  # 1 mm Spaltmaß links und rechts (8 px bei 203 dpi)
NAME_MAX, NAME_MIN = 28, 10
ID_MAX, ID_MIN = 40, 14

BUNDLED_FONT = Path(__file__).parent / "static" / "fonts" / "Roboto-Regular.ttf"  # Apache 2.0
_FONTS = (
    str(BUNDLED_FONT),  # immer vorhanden, kennt Umlaute, ß, €, °, µ
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
        left, _, right, _ = draw.textbbox((0, 0), text, font=font)
        if max(right - left, draw.textlength(text, font=font)) <= width:
            return font
    return _font(smallest)


def clip(draw: ImageDraw.ImageDraw, text: str, font: Font, width: int) -> str:
    """Passt der Text auch in der kleinsten Schrift nicht, wird er mit „…“ gekürzt."""
    while len(text) > 1 and draw.textlength(text, font=font) > width:
        text = text[:-2].rstrip() + "…"
    return text


def _qr(content: str) -> Image.Image:
    qr = segno.make(content, error="m")
    buf = io.BytesIO()
    qr.save(buf, kind="png", scale=1, border=0)
    small = Image.open(buf).convert("1")
    scale = max(1, QR_BOX // small.width)  # ganze Pixel je Modul = scharf
    return small.resize((small.width * scale, small.height * scale), Image.Resampling.NEAREST)


PAD_Y = 3  # Luft oben/unten
LINE_MAX = 64


def fit_box(
    draw: ImageDraw.ImageDraw, text: str, width: int, height: int, smallest: int = 9
) -> Font:
    """Größte Schrift, die in das Feld (Breite × Höhe) passt – automatische Skalierung."""
    for size in range(min(LINE_MAX, height + 6), smallest - 1, -1):
        font = _font(size)
        try:
            ascent, descent = font.getmetrics()  # type: ignore[union-attr]
        except AttributeError:
            ascent, descent = size, 0
        if ascent + descent > height + 2:
            continue
        if draw.textlength(text, font=font) <= width:
            return font
    return _font(smallest)


def render_layout(label: Label) -> Image.Image:
    """Etikett nach Typ-Layout: QR links/rechts/ohne, Zeilen mit Höhenanteil und Ausrichtung;
    jede Zeile bekommt die größte Schrift, die in ihr Feld passt (Kürzen mit „…“ nur am Ende)."""
    img = Image.new("1", (W, H), 1)
    draw = ImageDraw.Draw(img)
    x0, x1 = MARGIN, W - MARGIN
    if label.qr_pos != "none":
        code = _qr(label.qr)
        top = (H - code.height) // 2
        if label.qr_pos == "right":
            img.paste(code, (W - MARGIN - code.width, top))
            x1 = W - MARGIN - code.width - GAP
        else:
            img.paste(code, (MARGIN, top))
            x0 = MARGIN + code.width + GAP
    room = x1 - x0 - 4
    total = sum(w for _, w, _ in label.lines) or 1
    avail = H - 2 * PAD_Y
    y = float(PAD_Y)
    for text, weight, align in label.lines:
        box = avail * weight / total
        font = fit_box(draw, text, room, int(box) - 2)
        shown = clip(draw, text, font, room)
        anchor = {"left": "lm", "center": "mm", "right": "rm"}[align]
        px = {"left": x0 + 2, "center": (x0 + x1) // 2, "right": x1 - 2}[align]
        draw.text((px, y + box / 2), shown, font=font, fill=0, anchor=anchor)
        y += box
    return img


def render(label: Label) -> Image.Image:
    if label.lines:
        return render_layout(label)
    img = Image.new("1", (W, H), 1)
    draw = ImageDraw.Draw(img)
    code = _qr(label.qr)
    img.paste(code, (MARGIN, (H - code.height) // 2))
    left = MARGIN + code.width + GAP
    area = W - left - MARGIN
    room = area - 4  # Luft für Glyphen-Überhang (je nach Schrift)
    cx = left + area // 2
    if label.text.strip():
        name = label.text.strip()
        nf = fit(draw, name, room, NAME_MAX, NAME_MIN)
        draw.text((cx, 26), clip(draw, name, nf, room), font=nf, fill=0, anchor="mm")
        idf = fit(draw, label.code, room, ID_MAX, ID_MIN)
        draw.text((cx, 66), label.code, font=idf, fill=0, anchor="mm")
    else:
        idf = fit(draw, label.code, room, ID_MAX + 6, ID_MIN)
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
