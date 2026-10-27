"""Behälter-Arten: feste Arten plus eigene mit eigenem Code-Präfix (Tabelle container_kind).

`sync` gleicht die Laufzeit-Tabellen (repo.KINDS, KIND_LABELS, codes.PREFIX_*) mit der DB ab;
db.connect ruft es bei jeder Verbindung auf, damit neue Arten sofort überall gelten.
"""

import re
import sqlite3
import unicodedata

from app import codes, repo
from app.repo import LagerError, Row

BUILTIN_LABELS = {
    "raum": "Raum", "regal": "Regal", "ebene": "Ebene", "stapel": "Stapel/Kistenberg",
    "eurobox": "Eurobox", "kiste": "Kiste", "sortierkasten": "Sortierkasten",
    "einsatz": "Einsatz", "fach": "Fach", "sonstiges": "Sonstiges",
}  # fmt: skip
KIND_LABELS: dict[str, str] = dict(BUILTIN_LABELS)
_BUILTIN_PREFIX_KIND = dict(codes.PREFIX_KIND)
_BUILTIN_PREFIX_LABELS = dict(codes.PREFIX_LABELS)
_BUILTIN_KIND_PREFIX = dict(codes.KIND_PREFIX)


def custom(conn: sqlite3.Connection) -> list[Row]:
    return conn.execute(
        "SELECT k.*, (SELECT COUNT(*) FROM container c WHERE c.kind = k.kind) AS n"
        " FROM container_kind k ORDER BY k.label COLLATE NOCASE"
    ).fetchall()


def sync(conn: sqlite3.Connection) -> None:
    rows = conn.execute("SELECT kind, label, prefix FROM container_kind").fetchall()
    for target, base in (
        (KIND_LABELS, BUILTIN_LABELS),
        (codes.PREFIX_KIND, _BUILTIN_PREFIX_KIND),
        (codes.PREFIX_LABELS, _BUILTIN_PREFIX_LABELS),
        (codes.KIND_PREFIX, _BUILTIN_KIND_PREFIX),
    ):
        target.clear()
        target.update(base)  # type: ignore[arg-type]
    for r in rows:
        KIND_LABELS[r["kind"]] = r["label"]
        codes.PREFIX_KIND[r["prefix"]] = r["kind"]
        codes.PREFIX_LABELS[r["prefix"]] = r["label"]
        codes.KIND_PREFIX[r["kind"]] = r["prefix"]
    repo.KINDS[:] = list(KIND_LABELS)


def _slug(label: str) -> str:
    s = label.casefold().replace("ä", "ae").replace("ö", "oe").replace("ü", "ue").replace("ß", "ss")
    s = unicodedata.normalize("NFKD", s).encode("ascii", "ignore").decode()
    return re.sub(r"[^a-z0-9]+", "-", s).strip("-")


def create(conn: sqlite3.Connection, label: str, prefix: str) -> str:
    """Neue Art anlegen; gibt den internen Schlüssel zurück."""
    label, prefix = label.strip(), prefix.strip().upper()
    if not label:
        raise LagerError("Name der Art fehlt")
    if not re.fullmatch(r"[A-Z]{3}", prefix):
        raise LagerError("Präfix muss aus genau 3 Buchstaben bestehen, z. B. SCH")
    sync(conn)
    if prefix in codes.PREFIX_KIND:
        raise LagerError(f"Präfix {prefix} ist schon vergeben ({codes.PREFIX_LABELS[prefix]})")
    kind = _slug(label)
    if (
        not kind
        or kind in KIND_LABELS
        or any(v.casefold() == label.casefold() for v in KIND_LABELS.values())
    ):
        raise LagerError(f"Art „{label}“ gibt es schon")
    with conn:
        conn.execute(
            "INSERT INTO container_kind (kind, label, prefix) VALUES (?, ?, ?)",
            (kind, label, prefix),
        )
    sync(conn)
    return kind


def delete(conn: sqlite3.Connection, kind: str) -> None:
    """Nur unbenutzte eigene Arten löschen."""
    if conn.execute("SELECT 1 FROM container WHERE kind = ? LIMIT 1", (kind,)).fetchone():
        raise LagerError("Art wird noch verwendet – erst die Behälter umstellen")
    with conn:
        conn.execute("DELETE FROM container_kind WHERE kind = ?", (kind,))
    sync(conn)
