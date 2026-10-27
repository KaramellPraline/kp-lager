"""Behälter-Arten und Code-Schema: feste Arten (englische Schlüssel, Namen DE/EN) plus eigene
mit eigenem Präfix (Tabelle container_kind).

`sync` gleicht die Laufzeit-Tabellen (repo.KINDS, KIND_LABELS, codes.PREFIX_*) mit der DB und der
Spracheinstellung (`setting:lang`) ab; db.connect ruft es bei jeder Verbindung auf.
"""

import re
import sqlite3
import unicodedata
from typing import NamedTuple

from app import codes, repo
from app.repo import LagerError, Row


class Kind(NamedTuple):
    key: str
    prefix: str | None  # None = Strukturteil ohne eigenen Code (Ebene, Fach)
    group: str
    de: str
    en: str


GROUPS = {
    "loc": ("Standorte & Infrastruktur", "Locations & Infrastructure"),
    "box": ("Behälter & Aufbewahrung", "Containers, Cases & Storage"),
    "mat": ("Verbrauch & Rohmaterial", "Consumables & Materials"),
    "ppe": ("Sicherheit & Ausrüstung", "Safety & Equipment"),
    "own": ("Eigene Arten", "Custom kinds"),
    "item": ("Gegenstände & Kategorien", "Items & System Classification"),
}
BUILTIN = (
    Kind("room", "RAU", "loc", "Raum", "Room"),
    Kind("shelf", "REG", "loc", "Regal", "Shelf / Racking"),
    Kind("workbench", "WBA", "loc", "Werkbank", "Workbench"),
    Kind("wall", "WAL", "loc", "Lochwand / Werkzeugwand", "Wall / Pegboard"),
    Kind("drawer", "DRW", "loc", "Schubladenelement / Schrank", "Drawer Unit"),
    Kind("level", None, "loc", "Ebene", "Level"),
    Kind("toolbox", "TBX", "box", "Werkzeugbox / Kistenberg Pro", "Tool Box"),
    Kind("case", "MCF", "box", "Maschinenkoffer", "Machine Case"),
    Kind("module", "MOD", "box", "Modulbox / Stapelbox", "Modular Box"),
    Kind("sortingbox", "SOR", "box", "Sortierkasten", "Sorting Box"),
    Kind("eurobox", "EUR", "box", "Eurobox", "Eurobox"),
    Kind("crate", "KIS", "box", "Kiste (groß)", "Crate / Large Box"),
    Kind("box", "BOX", "box", "Box", "Box"),
    Kind("bin", "BIN", "box", "Einsatz / Sichtlagerbox", "Bin / Insert"),
    Kind("compartment", None, "box", "Fach", "Compartment"),
    Kind("consumables", "CNS", "mat", "Verbrauchsmaterial", "Consumables"),
    Kind("raw", "RAW", "mat", "Rohmaterial", "Raw Material"),
    Kind("cables", "CBL", "mat", "Kabel & Leitungen", "Cables & Wire"),
    Kind("components", "CMP", "mat", "Elektronikbauteile", "Electronic Components"),
    Kind("ppe", "PPE", "ppe", "Schutzausrüstung (PSA)", "Personal Protective Equipment"),
)
ITEM_LABELS = {
    codes.ITEM_PREFIX: ("Gegenstand / Werkzeug", "Article / Item"),
    codes.TYPE_PREFIX: ("Typ (immer klein, z. B. makita)", "Type (always lowercase, e.g. makita)"),
}
# Behälter, in die man direkt Teile legt (für „Freie Plätze“)
STORAGE = ("toolbox", "case", "module", "eurobox", "crate", "box", "consumables", "raw", "cables",
           "components", "ppe", "drawer")  # fmt: skip
# Alte deutsche Schlüssel und Präfixe (Import älterer JSON-Dateien)
ALIASES = {"raum": "room", "regal": "shelf", "ebene": "level", "stapel": "toolbox",
           "kiste": "crate", "sortierkasten": "sortingbox", "einsatz": "bin", "fach": "compartment",
           "sonstiges": "box", "sta": "toolbox", "ein": "bin"}  # fmt: skip

KIND_LABELS: dict[str, str] = {}
KIND_GROUPS: list[tuple[str, list[str]]] = []  # (Gruppenname, Schlüssel) für Auswahllisten
SCHEMA_GROUPS: list[tuple[str, list[str]]] = []  # (Gruppenname, Präfixe) fürs Code-Schema


def lang(conn: sqlite3.Connection) -> str:
    row = conn.execute("SELECT value FROM meta WHERE key = 'setting:lang'").fetchone()
    return "en" if row and row["value"] == "en" else "de"


def custom(conn: sqlite3.Connection) -> list[Row]:
    return conn.execute(
        "SELECT k.*, (SELECT COUNT(*) FROM container c WHERE c.kind = k.kind) AS n"
        " FROM container_kind k ORDER BY k.label COLLATE NOCASE"
    ).fetchall()


def sync(conn: sqlite3.Connection) -> None:
    rows = conn.execute("SELECT kind, label, prefix FROM container_kind").fetchall()
    _apply(rows, lang(conn) == "en")


def _apply(rows: list[Row], en: bool) -> None:
    for d in (KIND_LABELS, codes.PREFIX_KIND, codes.PREFIX_LABELS, codes.KIND_PREFIX):
        d.clear()
    groups: dict[str, list[str]] = {}
    prefixes: dict[str, list[str]] = {}
    for k in BUILTIN:
        KIND_LABELS[k.key] = k.en if en else k.de
        groups.setdefault(k.group, []).append(k.key)
        if k.prefix:
            codes.PREFIX_KIND[k.prefix] = k.key
            codes.PREFIX_LABELS[k.prefix] = KIND_LABELS[k.key]
            codes.KIND_PREFIX[k.key] = k.prefix
            prefixes.setdefault(k.group, []).append(k.prefix)
    for r in rows:
        if r["prefix"] in codes.PREFIX_KIND or r["kind"] in KIND_LABELS:
            continue  # feste Art hat Vorrang
        KIND_LABELS[r["kind"]] = r["label"]
        groups.setdefault("own", []).append(r["kind"])
        codes.PREFIX_KIND[r["prefix"]] = r["kind"]
        codes.PREFIX_LABELS[r["prefix"]] = r["label"]
        codes.KIND_PREFIX[r["kind"]] = r["prefix"]
        prefixes.setdefault("own", []).append(r["prefix"])
    for p, (de, en_label) in ITEM_LABELS.items():
        codes.PREFIX_KIND[p] = None
        codes.PREFIX_LABELS[p] = en_label if en else de
        prefixes.setdefault("item", []).append(p)
    i = 1 if en else 0
    KIND_GROUPS[:] = [(GROUPS[g][i], groups[g]) for g in GROUPS if g in groups]
    SCHEMA_GROUPS[:] = [(GROUPS[g][i], prefixes[g]) for g in GROUPS if g in prefixes]
    repo.KINDS[:] = list(KIND_LABELS)


def resolve(raw: str) -> str | None:
    """Schlüssel, Präfix, alter Schlüssel oder Name (DE/EN) -> Schlüssel der Art."""
    s = raw.strip()
    if s in KIND_LABELS:
        return s
    low = s.casefold()
    if low in ALIASES:
        return ALIASES[low]
    if kind := codes.PREFIX_KIND.get(s.upper()):
        return kind
    for k in BUILTIN:
        if low in (k.de.casefold(), k.en.casefold()):
            return k.key
    for key, label in KIND_LABELS.items():
        if label.casefold() == low:
            return key
    return None


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
    if not kind or kind in KIND_LABELS or resolve(label) is not None:
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


_apply([], en=False)  # feste Arten gelten auch ohne DB-Verbindung
