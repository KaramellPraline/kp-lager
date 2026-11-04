# ruff: noqa: E501
"""A4-Etiketten: Typen, Rendering (Pillow, 300 dpi, auch rot), Packen auf Seiten, PDF, IPP-Druck.

Etiketten landen nie automatisch auf Papier: Sie werden in die A4-Warteschlange (`a4_job`)
gelegt. Beim Drucken ordnet `pack` alle Etiketten platzsparend auf A4-Seiten an, daraus entsteht
ein PDF, das nach Bestätigung per IPP an den Netzwerkdrucker geht.
"""

import http.client
import io
import json
import sqlite3
import struct
from typing import Any
from urllib.parse import urlparse

import segno
from PIL import Image, ImageDraw

from app import labelimg, repo
from app.repo import LagerError

DPI = 300
PAGE_W, PAGE_H = 210.0, 297.0  # mm
MARGIN = 8.0
GAP = 2.0
COLORS = {"black": (0, 0, 0), "red": (200, 16, 46)}
COLOR_NAMES = {"black": "Schwarz", "red": "Rot"}

# Typ -> (Name, Beschreibung, Standardgröße mm)
TYPES: dict[str, tuple[str, str, tuple[float, float]]] = {
    "layout": ("Frei gestaltet", "Zeilen, QR, Rahmen und Farben selbst festlegen", (100.0, 60.0)),
    "tag": ("Etikett mit QR", "QR-Code, Name und Code (Teile, Behälter)", (50.0, 20.0)),
    "bin_side": (
        "Seitenetikett Bin",
        "Inhalt aller Fächer eines Einsatzes, Breite = Einsatz",
        (108.0, 22.0),
    ),
    "box": ("Box-Label", "Länge × Breite mit abgerundetem Rahmen", (100.0, 60.0)),
    "content": ("Inhaltsetikett", "Kennung und Text ohne QR", (60.0, 20.0)),
}


# Vorlagen im Formular „Neues Etikett“: Größe, QR, Rahmen und Zeilen (Text, Höhe, Ausrichtung, Farbe)
LAYOUT_PRESETS: dict[str, dict[str, Any]] = {
    "box": {"name": "Box-Label", "w": 100, "h": 60, "qrpos": "right", "frame": "round", "color": "red",
            "lines": [("{name}", 3, "center", "red"), ("{inhalt}", 2, "center", "black"), ("{code}", 1, "center", "red")]},
    "tag": {"name": "Etikett mit QR", "w": 50, "h": 20, "qrpos": "left", "frame": "none", "color": "red",
            "lines": [("{name}", 2, "left", "black"), ("{code}", 1, "left", "red")]},
    "content": {"name": "Inhaltsetikett", "w": 60, "h": 22, "qrpos": "none", "frame": "round", "color": "red",
                "lines": [("{code}", 1, "left", "red"), ("{inhalt}", 3, "center", "black")]},
    "schild": {"name": "Großes Schild", "w": 190, "h": 80, "qrpos": "left", "frame": "round", "color": "red",
               "lines": [("{name}", 3, "center", "red"), ("{ort}", 1, "center", "black"), ("{code}", 2, "center", "red")]},
}  # fmt: skip


def mm(value: float) -> int:
    return round(value * DPI / 25.4)


# --- Auftrag prüfen ------------------------------------------------------------------------


def clean_job(raw: dict[str, Any]) -> dict[str, Any]:
    kind = str(raw.get("type", ""))
    if kind not in TYPES:
        raise LagerError("Unbekannter Etikettentyp")
    dw, dh = TYPES[kind][2]

    def size(key: str, default: float, top: float) -> float:
        try:
            v = float(str(raw.get(key, default)).replace(",", "."))
        except ValueError:
            v = default
        return max(10.0, min(top, v))

    cells = []
    for c in raw.get("cells") or []:
        if isinstance(c, dict):
            lines = [str(x)[:60] for x in (c.get("lines") or []) if str(x).strip()][:8]
            cells.append({"title": str(c.get("title", ""))[:30], "lines": lines})
    cfg = []
    for c in raw.get("cfg") or []:
        if isinstance(c, dict) and str(c.get("t", "")).strip():
            try:
                weight = max(1, min(4, int(c.get("w", 1))))
            except (TypeError, ValueError):
                weight = 1
            cfg.append({
                "t": str(c["t"])[:80], "w": weight,
                "a": c.get("a") if c.get("a") in ("left", "center", "right") else "center",
                "c": c.get("c") if c.get("c") in COLORS else "black",
            })  # fmt: skip
    return {
        "type": kind,
        "cfg": cfg[:4],
        "frame": raw.get("frame") if raw.get("frame") in ("round", "square", "none") else "round",
        "qrpos": raw.get("qrpos") if raw.get("qrpos") in ("left", "right", "none") else "left",
        "w": size("w", dw, PAGE_W - 2 * MARGIN),
        "h": size("h", dh, PAGE_H - 2 * MARGIN),
        "color": raw.get("color") if raw.get("color") in COLORS else "black",
        "title": str(raw.get("title", ""))[:80],
        "code": str(raw.get("code", ""))[:20],
        "qr": str(raw.get("qr", ""))[:200],
        "lines": [str(x)[:80] for x in (raw.get("lines") or []) if str(x).strip()][:8],
        "cells": cells[:40],
        "cols": max(1, min(8, int(raw.get("cols") or 1))),
        "rows": max(1, min(8, int(raw.get("rows") or 1))),
    }


# --- Rendering -----------------------------------------------------------------------------


def _qr(content: str, size: int) -> Image.Image:
    buf = io.BytesIO()
    segno.make(content, error="m").save(buf, kind="png", scale=1, border=0)
    buf.seek(0)
    return Image.open(buf).convert("RGB").resize((size, size), Image.Resampling.NEAREST)


def _text(
    draw: ImageDraw.ImageDraw, box: tuple[int, int, int, int], text: str, color: Any,
    align: str = "center", biggest: int | None = None,
) -> None:  # fmt: skip
    """Text einzeilig in die Box: größte passende Schrift, sonst mit „…“ gekürzt."""
    x0, y0, x1, y1 = box
    if not text.strip() or x1 - x0 < 8 or y1 - y0 < 8:
        return
    width = x1 - x0 - 2
    font = labelimg.fit(draw, text, width, min(biggest or 400, int((y1 - y0) * 0.95)), 7)
    shown = labelimg.clip(draw, text, font, width)
    anchor = {"left": "lm", "center": "mm", "right": "rm"}[align]
    px = {"left": x0 + 1, "center": (x0 + x1) // 2, "right": x1 - 1}[align]
    draw.text((px, (y0 + y1) // 2), shown, font=font, fill=color, anchor=anchor)


def _stack(
    draw: ImageDraw.ImageDraw, box: tuple[int, int, int, int], lines: list[str], color: Any,
    align: str = "center", weights: list[int] | None = None,
) -> None:  # fmt: skip
    """Zeilen untereinander; die erste bekommt mehr Höhe (weights)."""
    if not lines:
        return
    x0, y0, x1, y1 = box
    w = weights or [3] + [2] * (len(lines) - 1)
    total = float(sum(w[: len(lines)]))
    y = float(y0)
    for text, weight in zip(lines, w, strict=False):
        h = (y1 - y0) * weight / total
        _text(draw, (x0, round(y), x1, round(y + h)), text, color, align)
        y += h


def _rounded(
    draw: ImageDraw.ImageDraw, w: int, h: int, color: Any, radius_mm: float, line_mm: float
) -> None:
    draw.rounded_rectangle(
        (0, 0, w - 1, h - 1), radius=mm(radius_mm), outline=color, width=max(1, mm(line_mm))
    )


def _render_layout(img: Image.Image, draw: ImageDraw.ImageDraw, j: dict[str, Any]) -> None:
    """Frei gestaltetes Etikett: Rahmen, QR links/rechts, bis 4 Zeilen mit Höhe, Ausrichtung, Farbe."""
    w, h = img.size
    color = COLORS[j["color"]]
    if j["frame"] == "round":
        _rounded(draw, w, h, color, 4.0 if min(w, h) > mm(30) else 2.5, 0.6)
    elif j["frame"] == "square":
        draw.rectangle((0, 0, w - 1, h - 1), outline=color, width=max(1, mm(0.6)))
    pad = mm(3.0) if j["frame"] != "none" else mm(1.2)
    x0, x1 = pad, w - pad
    if j["qr"] and j["qrpos"] != "none":
        side = min(h - 2 * pad, round(w * 0.42))
        top = (h - side) // 2
        if j["qrpos"] == "right":
            img.paste(_qr(j["qr"], side), (w - pad - side, top))
            x1 = w - pad - side - mm(2)
        else:
            img.paste(_qr(j["qr"], side), (pad, top))
            x0 = pad + side + mm(2)
    cfg = j["cfg"]
    total = float(sum(c["w"] for c in cfg)) or 1.0
    y = float(pad)
    avail = h - 2 * pad
    for c in cfg:
        band = avail * c["w"] / total
        _text(draw, (x0, round(y), x1, round(y + band)), c["t"], COLORS[c["c"]], c["a"])
        y += band


def render(job: dict[str, Any]) -> Image.Image:
    """Ein Etikett als RGB-Bild (300 dpi)."""
    j = clean_job(job)
    w, h = mm(j["w"]), mm(j["h"])
    img = Image.new("RGB", (w, h), (255, 255, 255))
    draw = ImageDraw.Draw(img)
    color = COLORS[j["color"]]
    pad = mm(1.6)
    kind = j["type"]
    if kind == "layout":
        _render_layout(img, draw, j)
    elif kind == "tag":
        qr_side = h - 2 * pad
        if j["qr"]:
            img.paste(_qr(j["qr"], qr_side), (pad, pad))
        x0 = pad + (qr_side + pad if j["qr"] else 0)
        rows = [j["title"], *j["lines"][:1]] if j["title"] else j["lines"][:2]
        rows = [r for r in rows if r]
        _stack(draw, (x0, pad, w - pad, h - pad - (mm(5) if j["code"] else 0)), rows, (0, 0, 0))
        if j["code"]:
            _text(draw, (x0, h - pad - mm(5), w - pad, h - pad), j["code"], color, biggest=mm(4.5))
    elif kind == "box":
        _rounded(draw, w, h, color, 4.0, 0.7)
        inner = mm(3.5)
        qr_side = min(h // 2, mm(22)) if j["qr"] else 0
        right = w - inner - (qr_side + inner if qr_side else 0)
        _text(
            draw,
            (inner, inner, right, inner + round((h - 2 * inner) * 0.45)),
            j["title"],
            color,
            biggest=mm(14),
        )
        _stack(draw, (inner, inner + round((h - 2 * inner) * 0.5), right, h - inner - (mm(6) if j["code"] else 0)),
               j["lines"][:3], (0, 0, 0), weights=[2, 2, 2])  # fmt: skip
        if j["code"]:
            _text(
                draw, (inner, h - inner - mm(6), right, h - inner), j["code"], color, biggest=mm(5)
            )
        if qr_side:
            img.paste(_qr(j["qr"], qr_side), (w - inner - qr_side, (h - qr_side) // 2))
    else:  # bin_side, content
        _rounded(draw, w, h, color, 2.5, 0.5)
        head = mm(4.5) if j["title"] else 0
        if head:
            _text(
                draw,
                (pad, mm(0.8), w - pad, mm(0.8) + head),
                j["title"],
                color,
                align="left",
                biggest=mm(3.6),
            )
        cells = j["cells"] or [{"title": "", "lines": j["lines"]}]
        cols, rows = (j["cols"], j["rows"]) if j["cells"] else (1, 1)
        top = head + mm(0.8)
        cw, ch = (w - 2 * mm(1)) / cols, (h - top - mm(1)) / rows
        for i, c in enumerate(cells[: cols * rows]):
            r, k = divmod(i, cols)
            cx0, cy0 = float(mm(1)) + k * cw, float(top) + r * ch
            if k:
                draw.line(
                    (cx0, cy0 + mm(1), cx0, cy0 + ch - mm(1)), fill=color, width=max(1, mm(0.4))
                )
            if r:
                draw.line(
                    (cx0 + mm(1), cy0, cx0 + cw - mm(1), cy0), fill=color, width=max(1, mm(0.4))
                )
            box = (
                round(cx0 + mm(1.2)),
                round(cy0 + mm(0.8)),
                round(cx0 + cw - mm(1.2)),
                round(cy0 + ch - mm(0.8)),
            )
            lines = ([c["title"]] if c["title"] else []) + c["lines"]
            _stack(
                draw,
                box,
                lines,
                (0, 0, 0),
                weights=[2] + [3] * (len(lines) - 1) if c["title"] else None,
            )
    return img


# --- Anordnen auf A4 ----------------------------------------------------------------------------


def pack(sizes: list[tuple[float, float]]) -> list[list[tuple[int, float, float]]]:
    """Regalpackung: hohe Etiketten zuerst, nebeneinander, neue Reihe/Seite wenn voll.
    Ergebnis je Seite: [(Index, x_mm, y_mm)]."""
    uw, uh = PAGE_W - 2 * MARGIN, PAGE_H - 2 * MARGIN
    order = sorted(range(len(sizes)), key=lambda i: (-sizes[i][1], -sizes[i][0]))
    pages: list[list[tuple[int, float, float]]] = []
    cur: list[tuple[int, float, float]] = []
    x = y = shelf = 0.0
    for i in order:
        w, h = sizes[i]
        if w > uw or h > uh:
            raise LagerError(f"Etikett {w:g}×{h:g} mm passt nicht auf A4")
        if x > 0 and x + w > uw:
            y += shelf + GAP
            x = shelf = 0.0
        if y + h > uh:
            pages.append(cur)
            cur, x, y, shelf = [], 0.0, 0.0, 0.0
        cur.append((i, MARGIN + x, MARGIN + y))
        x += w + GAP
        shelf = max(shelf, h)
    if cur:
        pages.append(cur)
    return pages


def pages_of(jobs: list[dict[str, Any]]) -> list[Image.Image]:
    """Alle Etiketten angeordnet auf A4-Seiten (RGB, 300 dpi)."""
    cleaned = [clean_job(j) for j in jobs]
    layout = pack([(j["w"], j["h"]) for j in cleaned])
    out = []
    for page in layout:
        img = Image.new("RGB", (mm(PAGE_W), mm(PAGE_H)), (255, 255, 255))
        draw = ImageDraw.Draw(img)
        for idx, x, y in page:
            px, py = mm(x), mm(y)
            label = render(cleaned[idx])
            img.paste(label, (px, py))
            draw.rectangle(
                (px - 1, py - 1, px + label.width, py + label.height), outline=(205, 205, 205)
            )
        out.append(img)
    return out


def pdf(jobs: list[dict[str, Any]]) -> bytes:
    pages = pages_of(jobs)
    if not pages:
        raise LagerError("Keine Etiketten in der A4-Warteschlange")
    buf = io.BytesIO()
    pages[0].save(buf, "PDF", save_all=True, append_images=pages[1:], resolution=float(DPI))
    return buf.getvalue()


def png(img: Image.Image, max_width: int | None = None) -> bytes:
    if max_width and img.width > max_width:
        img = img.resize(
            (max_width, round(img.height * max_width / img.width)), Image.Resampling.LANCZOS
        )
    buf = io.BytesIO()
    img.save(buf, "PNG")
    return buf.getvalue()


# --- Warteschlange (DB) ---------------------------------------------------------------------------


def enqueue(conn: sqlite3.Connection, job: dict[str, Any]) -> int:
    j = clean_job(job)
    with conn:
        cur = conn.execute(
            "INSERT INTO a4_job (kind, title, payload) VALUES (?, ?, ?)",
            (j["type"], j["title"] or j["code"], json.dumps(j, ensure_ascii=False)),
        )
    return int(cur.lastrowid or 0)


def queue(conn: sqlite3.Connection) -> list[dict[str, Any]]:
    out = []
    for r in conn.execute("SELECT * FROM a4_job ORDER BY id"):
        job = json.loads(r["payload"])
        out.append({"id": r["id"], "kind": r["kind"], "title": r["title"], "job": job})
    return out


def remove(conn: sqlite3.Connection, job_id: int) -> None:
    with conn:
        conn.execute("DELETE FROM a4_job WHERE id = ?", (job_id,))


def clear(conn: sqlite3.Connection) -> None:
    with conn:
        conn.execute("DELETE FROM a4_job")


def count(conn: sqlite3.Connection) -> int:
    return int(conn.execute("SELECT COUNT(*) FROM a4_job").fetchone()[0])


# --- Aufträge aus Teilen und Behältern -----------------------------------------------------------


def job_item(
    conn: sqlite3.Connection, base_url: str, item: sqlite3.Row, color: str = "black"
) -> dict[str, Any]:
    from app import labels

    lab = labels.item_label(conn, base_url, item)
    return clean_job({
        "type": "tag", "title": lab.text or item["name"], "lines": [lab.extra] if lab.extra else [],
        "code": lab.code, "qr": lab.qr, "color": color,
    })  # fmt: skip


def job_container(
    conn: sqlite3.Connection, base_url: str, node: sqlite3.Row, color: str = "black"
) -> dict[str, Any]:
    from app import labels

    text, extra = labels.container_label(conn, node)
    return clean_job({
        "type": "tag", "title": text, "lines": [extra] if extra else [], "code": node["code"] or "",
        "qr": labels.qr_content(base_url, node["code"]) if node["code"] else "", "color": color,
    })  # fmt: skip


def compartment_text(conn: sqlite3.Connection, comp: sqlite3.Row) -> list[str]:
    """Etikettentext eines Fachs: eigener Text (Tags) oder die Namen der Teile darin."""
    own = (comp["label_text"] or "").strip()
    if own:
        return [x.strip() for x in own.splitlines() if x.strip()]
    return list(dict.fromkeys(i["name"] for i in repo.items_in(conn, comp["id"])))


def job_bin_side(
    conn: sqlite3.Connection, bin_row: sqlite3.Row, color: str = "red"
) -> dict[str, Any]:
    """Seitenetikett: alle Fächer des Einsatzes als Raster, Breite = Einsatzbreite."""
    from app import kasten

    long_units, short_units = (int(p) for p in str(bin_row["size"] or "1x1").lower().split("x"))
    width = max(30.0, long_units * 54.77 - 3.0)
    faecher = repo.children(conn, bin_row["id"])
    cells: list[dict[str, Any]] = []
    cols = rows = 1
    if faecher and bin_row["grid"]:
        cols, rows = (int(p) for p in bin_row["grid"].split("x"))
        pos = {kasten.parse_cell(f["position"]): f for f in faecher}
        for r in range(rows):
            for c in range(cols):
                f = pos.get((r, c))
                cells.append({"title": "", "lines": compartment_text(conn, f) if f else []})
    else:
        cells.append({"title": "", "lines": compartment_text(conn, bin_row)})
    height = max(20.0, 12.0 * rows + 6.0)
    return clean_job({
        "type": "bin_side", "w": min(width, PAGE_W - 2 * MARGIN), "h": height, "color": color,
        "title": bin_row["code"] or bin_row["name"], "cells": cells, "cols": cols, "rows": rows,
    })  # fmt: skip


# --- Netzwerkdrucker (IPP) -------------------------------------------------------------------------


def _attr(tag: int, name: str, value: str) -> bytes:
    n, v = name.encode(), value.encode()
    return struct.pack(">BH", tag, len(n)) + n + struct.pack(">H", len(v)) + v


def ipp_request(printer_uri: str, data: bytes, title: str) -> bytes:
    """Minimale IPP-2.0-Anfrage „Print-Job“ mit PDF-Dokument."""
    head = struct.pack(">BBHI", 2, 0, 0x0002, 1) + b"\x01"
    head += _attr(0x47, "attributes-charset", "utf-8")
    head += _attr(0x48, "attributes-natural-language", "de")
    head += _attr(0x45, "printer-uri", printer_uri)
    head += _attr(0x42, "requesting-user-name", "kp-lager")
    head += _attr(0x42, "job-name", title[:100])
    head += _attr(0x49, "document-format", "application/pdf")
    return head + b"\x03" + data


def ipp_print(
    url: str, data: bytes, title: str = "KP Lager Etiketten", timeout: float = 30.0
) -> None:
    """PDF per IPP an den Drucker (ipp://host[:port]/pfad oder http://…). Fehler -> LagerError."""
    if not url.strip():
        raise LagerError("Kein A4-Netzwerkdrucker eingetragen (Admin → A4-Drucker)")
    p = urlparse(url.strip())
    if p.scheme not in ("ipp", "ipps", "http", "https") or not p.hostname:
        raise LagerError("Drucker-Adresse ungültig, z. B. ipp://192.168.1.50/ipp/print")
    secure = p.scheme in ("ipps", "https")
    port = p.port or (443 if secure else 631)
    path = p.path or "/ipp/print"
    uri = f"{'ipps' if secure else 'ipp'}://{p.hostname}:{port}{path}"
    cls = http.client.HTTPSConnection if secure else http.client.HTTPConnection
    try:
        conn = cls(p.hostname, port, timeout=timeout)
        conn.request(
            "POST",
            path,
            body=ipp_request(uri, data, title),
            headers={"Content-Type": "application/ipp"},
        )
        resp = conn.getresponse()
        body = resp.read()
        conn.close()
    except OSError as exc:
        raise LagerError(f"Drucker nicht erreichbar: {exc}") from None
    if resp.status != 200 or len(body) < 4:
        raise LagerError(f"Drucker antwortet mit HTTP {resp.status}")
    status = struct.unpack(">H", body[2:4])[0]
    if status >= 0x0100:
        raise LagerError(f"Drucker lehnt den Auftrag ab (IPP-Status 0x{status:04x})")
