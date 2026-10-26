"""Schnelleingabe: '3 Rollen Lötzinn' -> Menge 3, Einheit 'Rollen', Name 'Lötzinn'."""

import re

UNITS = (
    "stk", "stück", "st", "rolle", "rollen", "packung", "packungen", "pck", "pkg", "m", "meter",
    "cm", "paar", "set", "sets", "beutel", "karton", "kartons", "dose", "dosen", "flasche",
    "flaschen", "kg", "g", "l", "liter", "tube", "tuben", "box", "boxen",
)  # fmt: skip
_RE = re.compile(
    r"^\s*(\d{1,5})(?:\s*x)?\s+(?:(" + "|".join(UNITS) + r")\.?\s+)?(.+?)\s*$", re.IGNORECASE
)


_SPLIT = re.compile(r"\s*(?:,|;|\bund\b|\bsowie\b)\s*(?=\d)", re.IGNORECASE)


def parse_many(text: str) -> list[tuple[int | None, str, str]]:
    """Diktat mit mehreren Teilen: '3 Rollen Lötzinn und 50 M3 Muttern' -> zwei Einträge.

    Getrennt wird nur, wenn nach 'und'/','/';' eine Zahl folgt
    ('Schrauben und Muttern' bleibt ein Teil).
    """
    parts = [p.strip(" .") for p in _SPLIT.split(text) if p.strip(" .")]
    return [parse(p) for p in parts] or [parse(text)]


def parse(text: str) -> tuple[int | None, str, str]:
    """(Menge, Einheit, Name). Ohne führende Zahl: (None, '', Text)."""
    m = _RE.match(text)
    if not m:
        return None, "", text.strip()
    return int(m.group(1)), m.group(2) or "", m.group(3)


DEFAULT_SYNONYMS = """inbus = innensechskant = allen
kreuzschlitz = phillips = pozidriv
torx = tx
schraubendreher = schraubenzieher
schleifpapier = sandpapier
klebeband = tape = tesa
kabelbinder = kabelstrapse
dübel = anker"""
