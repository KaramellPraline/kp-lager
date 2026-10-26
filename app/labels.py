"""QR-Etiketten: fortlaufende Codes (0001, 0002, …) als SVG, Bogen-Layout in mm."""

import sqlite3
from dataclasses import dataclass

import segno

CODE_DIGITS = 4


def format_code(n: int) -> str:
    return f"{n:0{CODE_DIGITS}d}"


def qr_svg(url: str) -> str:
    """Inline-SVG ohne feste Größe (skaliert per CSS)."""
    svg: str = segno.make(url, error="m").svg_inline(border=0, omitsize=True)
    return svg


def next_free_number(conn: sqlite3.Connection) -> int:
    """Erste Nummer nach allen vergebenen und bereits gedruckten Codes."""
    row = conn.execute("SELECT value FROM meta WHERE key = 'next_label'").fetchone()
    printed = int(row["value"]) if row else 1
    used = conn.execute(
        "SELECT MAX(CAST(code AS INTEGER)) FROM container WHERE code GLOB '[0-9]*'"
    ).fetchone()[0]
    return max(printed, (used or 0) + 1)


def mark_printed(conn: sqlite3.Connection, last_number: int) -> None:
    with conn:
        conn.execute(
            "INSERT INTO meta (key, value) VALUES ('next_label', ?)"
            " ON CONFLICT(key) DO UPDATE SET value = MAX(CAST(value AS INTEGER), excluded.value)",
            (str(last_number + 1),),
        )


@dataclass(frozen=True)
class Sheet:
    """Etikettenbogen A4. Standard: 4×10 à 48,5×25,4 mm (z. B. Zweckform 3657)."""

    cols: int = 4
    rows: int = 10
    width: float = 48.5
    height: float = 25.4
    top: float = 21.5
    left: float = 8.0

    @property
    def per_page(self) -> int:
        return self.cols * self.rows
