"""Etiketten: QR-Inhalt, XLSX für den D30-Etikettendrucker (40×12 mm) und A4-Bögen.

QR-Inhalt komplett in Großbuchstaben (HTTP://LAGER.HOME.LAN/C/EUR-001): Dann nutzt der QR den
Alphanumerik-Modus, wird eine Version kleiner und auf 10 mm besser scannbar. /C/ = /c/.
"""

import io
import sqlite3
from dataclasses import dataclass

import segno
from openpyxl import Workbook

from app import codes

TEXT_MAX = 24  # Zeichen, die auf 40×12 mm neben den QR passen


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


def short(text: str) -> str:
    return text if len(text) <= TEXT_MAX else text[: TEXT_MAX - 1] + "…"


def to_xlsx(rows: list[Label]) -> bytes:
    """Spalten für die D30-App: A Code, B QR-Inhalt, C Text, D Zusatz."""
    wb = Workbook()
    ws = wb.active
    assert ws is not None
    ws.title = "Etiketten"
    ws.append(["Code", "QR", "Text", "Zusatz"])
    for r in rows:
        ws.append([r.code, r.qr, short(r.text), r.extra])
    for col, width in zip("ABCD", (12, 40, 26, 14), strict=True):
        ws.column_dimensions[col].width = width
    buf = io.BytesIO()
    wb.save(buf)
    return buf.getvalue()


# --- Etikettenlisten ---------------------------------------------------------------


def blank(conn: sqlite3.Connection, base_url: str, prefix: str, count: int) -> list[Label]:
    """Vorrat: reserviert neue Codes; beim ersten Scan wird der Behälter angelegt."""
    return [
        Label(c, qr_content(base_url, c), codes.PREFIX_LABELS[prefix])
        for c in codes.reserve(conn, prefix, count)
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


def mark_printed(conn: sqlite3.Connection, rows: list[Label]) -> None:
    printed = [(r.code,) for r in rows]
    with conn:
        conn.executemany("UPDATE container SET label_printed = 1 WHERE code = ?", printed)
        conn.executemany("UPDATE item SET label_printed = 1 WHERE code = ?", printed)


@dataclass(frozen=True)
class Sheet:
    """A4-Bogen als Alternative zum D30. Standard: 4×10 à 48,5×25,4 mm."""

    cols: int = 4
    rows: int = 10
    width: float = 48.5
    height: float = 25.4
    top: float = 21.5
    left: float = 8.0

    @property
    def per_page(self) -> int:
        return self.cols * self.rows
