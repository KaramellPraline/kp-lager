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
    de: str  # ein Name, kurz, ohne Schrägstrich (steht in Auswahllisten)
    en: str
    desc_de: str = ""  # Beschreibung nur auf der Codes-Seite
    desc_en: str = ""


GROUPS = {
    "loc": ("Standorte & Infrastruktur", "Locations & Infrastructure"),
    "box": ("Behälter & Aufbewahrung", "Containers, Cases & Storage"),
    "mat": ("Verbrauch & Rohmaterial", "Consumables & Materials"),
    "ppe": ("Sicherheit & Ausrüstung", "Safety & Equipment"),
    "mach": ("Maschinen & Geräte", "Machines & Devices"),
    "own": ("Eigene Arten", "Custom kinds"),
    "item": ("Gegenstände & Kategorien", "Items & System Classification"),
}
BUILTIN = (
    Kind("room", "RAU", "loc", "Raum", "Room", "Raum oder Bereich", "Room or area"),
    Kind("shelf", "REG", "loc", "Regal", "Shelf", "Regal, Schwerlastregal", "Shelf or racking"),
    Kind(
        "workbench",
        "WBA",
        "loc",
        "Werkbank",
        "Workbench",
        "Werkbank mit Ablagen",
        "Workbench with storage",
    ),
    Kind(
        "wall",
        "WAL",
        "loc",
        "Lochwand",
        "Pegboard",
        "Lochwand oder Werkzeugwand",
        "Wall or pegboard for tools",
    ),
    Kind(
        "drawer",
        "DRW",
        "loc",
        "Schubladenschrank",
        "Drawer Unit",
        "Schubladenelement oder Schrank",
        "Drawer unit or cabinet",
    ),
    Kind(
        "level",
        None,
        "loc",
        "Ebene",
        "Level",
        "Regalebene, ohne eigenen Code",
        "Shelf level, no own code",
    ),
    Kind(
        "toolbox",
        "TBX",
        "box",
        "Werkzeugbox",
        "Tool Box",
        "Werkzeugbox, z. B. Kistenberg Pro",
        "Tool box, e.g. Kistenberg Pro",
    ),
    Kind(
        "case",
        "MCF",
        "box",
        "Maschinenkoffer",
        "Machine Case",
        "Koffer einer Maschine",
        "Case of a power tool or machine",
    ),
    Kind(
        "module",
        "MOD",
        "box",
        "Modulbox",
        "Modular Box",
        "Modulbox oder Stapelbox",
        "Modular or stackable box",
    ),
    Kind(
        "sortingbox",
        "SOR",
        "box",
        "Sortierkasten",
        "Sorting Box",
        "Sortierkasten für Kleinteile, mit Fächern oder Einsätzen",
        "Sorting box for small parts, with compartments or bins",
    ),
    Kind(
        "eurobox",
        "EUR",
        "box",
        "Eurobox",
        "Eurobox",
        "Standardisierte Eurobox",
        "Standard Euro container",
    ),
    Kind("crate", "KIS", "box", "Kiste", "Crate", "Grobe oder große Kiste", "Crate or large box"),
    Kind("box", "BOX", "box", "Box", "Box", "Allgemeine Box", "General box"),
    Kind(
        "bin",
        "BIN",
        "box",
        "Einsatz",
        "Bin",
        "Kleiner Einsatz oder Sichtlagerbox",
        "Small insert or visible storage bin",
    ),
    Kind(
        "machine",
        "MAS",
        "mach",
        "Maschine",
        "Machine",
        "Maschine oder Gerät (3D-Drucker, Fräse, Laser) mit eigenem Etikett",
        "Machine or device (3D printer, mill, laser) with its own label",
    ),
    Kind(
        "dryer",
        "TRO",
        "mach",
        "Filamenttrockner",
        "Filament Dryer",
        "Trockner: Scan auf Trockner-Etikett, dann Filament-Etikett = getrocknet",
        "Dryer: scan the dryer tag, then a filament tag = dried",
    ),
    Kind(
        "compartment",
        None,
        "box",
        "Fach",
        "Compartment",
        "Fach im Sortierkasten, ohne eigenen Code",
        "Compartment of a sorting box, no own code",
    ),
)
# Teile-Präfixe: Präfix -> (Gruppe, Name DE, Name EN, Beschreibung DE, Beschreibung EN)
ITEM_LABELS = {
    "FIL": ("mat", "Filament", "Filament",
            "3D-Druck-Filament, eine Spule; Eigenschaften im Datenblatt",
            "3D printing filament, one spool; properties in the datasheet"),
    "RES": ("mat", "UV-Harz", "UV Resin",
            "UV-Harz für Resin-Druck, eine Flasche; Eigenschaften im Datenblatt",
            "UV resin for resin printing, one bottle; properties in the datasheet"),
    "CNS": ("mat", "Verbrauchsmaterial", "Consumables", "Schrauben, Dübel, Kleber, Tape",
            "Screws, anchors, glue, tape"),
    "RAW": ("mat", "Rohmaterial", "Raw Material", "Holzleisten, Metallprofile, Rohre",
            "Wood strips, metal profiles, pipes"),
    "CBL": ("mat", "Kabel", "Cables", "Kabel, Stecker, Kabelbinder",
            "Cables, connectors, cable ties"),
    "PSU": ("mat", "Netzteil", "Power Supply", "Netzteil mit Spannung, Strom und Stecker",
            "Power supply with voltage, current and plug"),
    "CMP": ("mat", "Elektronikbauteile", "Components", "Elektronikbauteile, Platinen, Sensoren",
            "Electronic components, boards, sensors"),
    "PPE": ("ppe", "Schutzausrüstung", "Protective Equipment",
            "Schutzbrille, Gehörschutz, Handschuhe, Masken",
            "Safety glasses, hearing protection, gloves, masks"),
    codes.ITEM_PREFIX: ("item",
        "Gegenstand", "Item", "Einzelner Gegenstand, der in keine andere Kategorie passt",
        "Single article that fits no other category"
    ),
    "TOL": ("item",
        "Werkzeug", "Tool", "Hand- und Elektrowerkzeug, Messgeräte, Akkus fürs Werkzeug",
        "Hand and power tools, measuring devices, tool batteries"
    ),
    codes.TYPE_PREFIX: ("item",
        "Tag", "Tag",
        "Schlagwort, immer kleingeschrieben, z. B. makita, handwerkzeug; in der Suche filterbar",
        "Keyword, always lowercase, e.g. makita, hand tool; filterable in search",
    ),
}  # fmt: skip
# Behälter, in die man direkt Teile legt (für „Freie Plätze“)
STORAGE = ("toolbox", "case", "module", "eurobox", "crate", "box", "drawer")
# Alte deutsche Schlüssel und Präfixe (Import älterer JSON-Dateien)
ALIASES = {"raum": "room", "regal": "shelf", "ebene": "level", "stapel": "toolbox",
           "kiste": "crate", "sortierkasten": "sortingbox", "einsatz": "bin", "fach": "compartment",
           "sonstiges": "box", "sta": "toolbox", "ein": "bin"}  # fmt: skip

KIND_LABELS: dict[str, str] = {}
KIND_GROUPS: list[tuple[str, list[str]]] = []  # (Gruppenname, Schlüssel) für Auswahllisten
SCHEMA_GROUPS: list[tuple[str, list[str]]] = []  # (Gruppenname, Präfixe) fürs Code-Schema
PREFIX_DESC: dict[str, str] = {}  # Präfix -> Beschreibung (nur Codes-Seite)
# Teile-Kategorien für die Auswahl beim Hinzufügen: [(Präfix, Name)], ART zuerst
# Eurobox-Normmaße L×B×H in mm (Stapelbehälter 600×400, 400×300, 300×200)
EURO_DIMS = [
    f"{lb}x{h}" for lb, heights in (("600x400", (120, 170, 220, 270, 320)),
                                    ("400x300", (120, 170, 220, 270, 320)),
                                    ("300x200", (120, 170, 220)))
    for h in heights
]  # fmt: skip
ITEM_CATS: list[tuple[str, str]] = []
CAT_ORDER = ("ART", "TOL", "FIL", "RES", "CNS", "RAW", "CBL", "PSU", "CMP", "PPE")
# Kurznamen für die Kategorie-Kacheln auf Start (DE, EN)
CAT_SHORT = {"ART": ("Gegenstand", "Item"), "CNS": ("Verbrauch", "Consumables"),
             "CMP": ("Elektronik", "Electronics"), "PPE": ("Schutz", "Safety"),
             "RES": ("UV-Harz", "Resin"), "RAW": ("Rohmaterial", "Raw")}  # fmt: skip
ITEM_CATS_SHORT: list[tuple[str, str]] = []
# Arten fürs „Behälter anlegen“ (Schlüssel, Präfix, Name); Maße/Airtight nur bei Boxen
ADD_KINDS: list[tuple[str, str, str]] = []
BOXY = ("toolbox", "case", "module", "sortingbox", "eurobox", "crate", "box")


def set_lang(conn: sqlite3.Connection, value: str) -> None:
    with conn:
        conn.execute(
            "INSERT INTO meta (key, value) VALUES ('setting:lang', ?)"
            " ON CONFLICT(key) DO UPDATE SET value = excluded.value",
            ("en" if value == "en" else "de",),
        )
    sync(conn)


def lang(conn: sqlite3.Connection) -> str:
    row = conn.execute("SELECT value FROM meta WHERE key = 'setting:lang'").fetchone()
    return "en" if row and row["value"] == "en" else "de"


def custom(conn: sqlite3.Connection) -> list[Row]:
    return conn.execute(
        "SELECT k.*, (SELECT COUNT(*) FROM container c WHERE c.kind = k.kind) AS n"
        " FROM container_kind k ORDER BY k.label COLLATE NOCASE"
    ).fetchall()


def sync(conn: sqlite3.Connection) -> None:
    rows = conn.execute("SELECT kind, label, prefix, description FROM container_kind").fetchall()
    _apply(rows, lang(conn) == "en")


def _apply(rows: list[Row], en: bool) -> None:
    for d in (KIND_LABELS, codes.PREFIX_KIND, codes.PREFIX_LABELS, codes.KIND_PREFIX, PREFIX_DESC):
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
            PREFIX_DESC[k.prefix] = k.desc_en if en else k.desc_de
            prefixes.setdefault(k.group, []).append(k.prefix)
    for r in rows:
        if r["prefix"] in codes.PREFIX_KIND or r["kind"] in KIND_LABELS:
            continue  # feste Art hat Vorrang
        KIND_LABELS[r["kind"]] = r["label"]
        groups.setdefault("own", []).append(r["kind"])
        codes.PREFIX_KIND[r["prefix"]] = r["kind"]
        codes.PREFIX_LABELS[r["prefix"]] = r["label"]
        codes.KIND_PREFIX[r["kind"]] = r["prefix"]
        PREFIX_DESC[r["prefix"]] = r["description"]
        prefixes.setdefault("own", []).append(r["prefix"])
    for p, (group, de, en_label, desc_de, desc_en) in ITEM_LABELS.items():
        codes.PREFIX_KIND[p] = None
        codes.PREFIX_LABELS[p] = en_label if en else de
        PREFIX_DESC[p] = desc_en if en else desc_de
        prefixes.setdefault(group, []).append(p)
    ITEM_CATS[:] = [(p, codes.PREFIX_LABELS[p]) for p in CAT_ORDER if p in codes.PREFIX_LABELS]
    ITEM_CATS_SHORT[:] = [
        (p, CAT_SHORT[p][1 if en else 0] if p in CAT_SHORT else label) for p, label in ITEM_CATS
    ]
    ADD_KINDS[:] = [
        (key, codes.KIND_PREFIX[key], KIND_LABELS[key])
        for g in ("box", "mach", "own")
        for key in groups.get(g, [])
        if key not in ("compartment", "bin")
    ]
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


def create(conn: sqlite3.Connection, label: str, prefix: str, description: str = "") -> str:
    """Neue Art anlegen; gibt den internen Schlüssel zurück."""
    label, prefix = label.strip(), prefix.strip().upper()
    if "/" in label:
        raise LagerError("Bitte ein Name ohne Schrägstrich; Details gehören in die Beschreibung")
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
            "INSERT INTO container_kind (kind, label, prefix, description) VALUES (?, ?, ?, ?)",
            (kind, label, prefix, description.strip()),
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
