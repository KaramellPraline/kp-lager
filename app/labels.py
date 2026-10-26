"""Etiketten: QR-Inhalt, XLSX für den D30-Etikettendrucker (40×12 mm) und A8-Bögen (A4 quer).

QR-Inhalt komplett in Großbuchstaben (HTTP://LAGER.HOME.LAN/C/EUR-001): Dann nutzt der QR den
Alphanumerik-Modus, wird eine Version kleiner und auf 10 mm besser scannbar. /C/ = /c/.
"""

import io
import sqlite3
from dataclasses import dataclass

import segno
from openpyxl import Workbook

from app import codes, repo

TEXT_MAX = 24  # Zeichen, die auf 40×12 mm neben den QR passen
A8_PER_PAGE = 16  # A4 quer = 4×4 A8 quer (74×52 mm)


@dataclass(frozen=True)
class Label:
    code: str
    qr: str
    text: str = ""
    extra: str = ""


def qr_content(base_url: str, code: str) -> str:
    return f"{base_url}/C/{code}".upper()


def qr_svg(content: str) -> str:
    """Inline-SVG ohne feste Größe (skaliert per CSS)."""
    svg: str = segno.make(content, error="m").svg_inline(border=0, omitsize=True)
    return svg


def short(text: str, limit: int = TEXT_MAX) -> str:
    return text if len(text) <= limit else text[: limit - 1] + "…"


def to_xlsx(rows: list[Label], text_max: int = TEXT_MAX) -> bytes:
    """Spalten für die D30-App: A Code, B QR-Inhalt, C Text, D Zusatz."""
    wb = Workbook()
    ws = wb.active
    assert ws is not None
    ws.title = "Etiketten"
    ws.append(["Code", "QR", "Text", "Zusatz"])
    for r in rows:
        ws.append([r.code, r.qr, short(r.text, text_max), r.extra])
    for col, width in zip("ABCD", (12, 40, 26, 14), strict=True):
        ws.column_dimensions[col].width = width
    buf = io.BytesIO()
    wb.save(buf)
    return buf.getvalue()


# --- Etikettenlisten ---------------------------------------------------------------


def blank(conn: sqlite3.Connection, base_url: str, prefix: str, count: int) -> list[Label]:
    """Vorrat: die nächsten freien Codes (reserviert erst beim Export)."""
    start = codes.next_number(conn, prefix)
    return [
        Label(c, qr_content(base_url, c), codes.PREFIX_LABELS[prefix])
        for c in (codes.format_code(prefix, n) for n in range(start, start + count))
    ]


def item_label(conn: sqlite3.Connection, base_url: str, item: sqlite3.Row) -> Label:
    holder = conn.execute(
        "SELECT kind, name, position FROM container WHERE id = ?", (item["container_id"],)
    ).fetchone()
    extra = holder["position"] if holder["kind"] == "fach" else holder["name"]
    return Label(item["code"], qr_content(base_url, item["code"]), item["name"], extra or "")


def pending(conn: sqlite3.Connection, base_url: str) -> list[Label]:
    """Alle Behälter und Gegenstände mit Code, deren Etikett noch nicht gedruckt ist."""
    rows = [
        Label(c["code"], qr_content(base_url, c["code"]), c["name"], c["kind"])
        for c in conn.execute(
            "SELECT * FROM container WHERE code IS NOT NULL AND label_printed = 0 ORDER BY code"
        )
    ]
    rows += [
        item_label(conn, base_url, i)
        for i in conn.execute(
            "SELECT * FROM item WHERE code IS NOT NULL AND label_printed = 0 ORDER BY code"
        )
    ]
    return rows


def for_container(conn: sqlite3.Connection, base_url: str, container_id: int) -> list[Label]:
    """Alle Gegenstände im Behälter inkl. Fächern; fehlende ART-Codes werden vergeben."""
    items = conn.execute(
        """
        WITH RECURSIVE down(id) AS (
            SELECT id FROM container WHERE id = ?
            UNION ALL SELECT c.id FROM container c JOIN down ON c.parent_id = down.id
        )
        SELECT item.id, item.code FROM item JOIN down ON item.container_id = down.id
        JOIN container ON container.id = item.container_id
        ORDER BY container.id, item.name
        """,
        (container_id,),
    ).fetchall()
    missing = [i["id"] for i in items if not i["code"]]
    with conn:
        for item_id, code in zip(
            missing, codes.reserve(conn, codes.ITEM_PREFIX, len(missing)), strict=True
        ):
            conn.execute("UPDATE item SET code = ? WHERE id = ?", (code, item_id))
    return [
        item_label(
            conn, base_url, conn.execute("SELECT * FROM item WHERE id = ?", (i["id"],)).fetchone()
        )
        for i in items
    ]


def finalize(
    conn: sqlite3.Connection,
    base_url: str,
    entries: list[tuple[str, str, str]],
    save_names: bool,
) -> list[Label]:
    """Export aus der Vorschau: (Code, Text, Zusatz) prüfen, ggf. Namen speichern,
    als gedruckt markieren und Zähler je Präfix nachziehen (reserviert Vorrats-Codes)."""
    rows: list[Label] = []
    for raw, text, extra in entries:
        code = codes.normalize(raw)
        if code is None:
            continue
        text = text.strip()
        if save_names and text:
            item = conn.execute("SELECT id, name FROM item WHERE code = ?", (code,)).fetchone()
            if item and item["name"] != text:
                repo.update_item(conn, item["id"], name=text)
            with conn:
                conn.execute(
                    "UPDATE container SET name = ?, updated_at = datetime('now')"
                    " WHERE code = ? AND name != ?",
                    (text, code, text),
                )
        rows.append(Label(code, qr_content(base_url, code), text, extra.strip()))
    printed = [(r.code,) for r in rows]
    with conn:
        conn.executemany("UPDATE container SET label_printed = 1 WHERE code = ?", printed)
        conn.executemany("UPDATE item SET label_printed = 1 WHERE code = ?", printed)
    for prefix in {r.code[:3] for r in rows}:
        last = max(int(r.code[4:]) for r in rows if r.code.startswith(prefix))
        codes.mark_used_until(conn, prefix, last)
    return rows


# --- Warteschlange: Etiketten sammeln, später als Batch exportieren -------------------

A4_COLS, A4_ROWS = 5, 22  # 40×12 mm auf A4 hoch (200 × 264 mm), Schnittlinien


def enqueue(conn: sqlite3.Connection, code: str, text: str, extra: str = "") -> None:
    """Gleicher Code nochmal = Text aktualisieren (z. B. Bin-Inhalt geändert)."""
    with conn:
        conn.execute(
            "INSERT INTO label_queue (code, text, extra) VALUES (?, ?, ?) ON CONFLICT(code)"
            " DO UPDATE SET text = excluded.text, extra = excluded.extra",
            (code, text, extra),
        )


def queue(conn: sqlite3.Connection, base_url: str) -> list[Label]:
    return [
        Label(r["code"], qr_content(base_url, r["code"]), r["text"], r["extra"])
        for r in conn.execute("SELECT * FROM label_queue ORDER BY added_at, code")
    ]


def queue_count(conn: sqlite3.Connection) -> int:
    return int(conn.execute("SELECT COUNT(*) FROM label_queue").fetchone()[0])


def dequeue(conn: sqlite3.Connection, codes_: list[str]) -> None:
    with conn:
        conn.executemany("DELETE FROM label_queue WHERE code = ?", [(c,) for c in codes_])


def container_label(conn: sqlite3.Connection, node: sqlite3.Row) -> tuple[str, str]:
    """(Text, Zusatz) für ein Behälter-Etikett; Einsatz: Inhalt + Kasten/Position."""
    if node["kind"] == "einsatz":
        from app import kasten  # zirkulärer Import vermeiden

        parent = repo.get_container(conn, node["parent_id"]) if node["parent_id"] else None
        where = (parent["code"] or parent["name"]) if parent else ""
        return kasten.bin_label_text(conn, node), f"{where} {node['position']}".strip()
    return node["name"], node["kind"]
