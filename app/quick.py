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


_NUM_WORD = r"(?:ein|eine|einen|eins|zwei|drei|vier|fünf|sechs|sieben|acht|neun|zehn|elf|zwölf|fünfzehn|zwanzig|dreißig|vierzig|fünfzig|hundert)\b"  # noqa: E501
_SPLIT = re.compile(r"\s*(?:,|;|\bund\b|\bsowie\b)\s*(?=\d|" + _NUM_WORD + ")", re.IGNORECASE)


def parse_many(text: str) -> list[tuple[int | None, str, str]]:
    """Diktat mit mehreren Teilen: '3 Rollen Lötzinn und 50 M3 Muttern' -> zwei Einträge.

    Getrennt wird nur, wenn nach 'und'/','/';' eine Zahl folgt
    ('Schrauben und Muttern' bleibt ein Teil).
    """
    parts = [p.strip(" .") for p in _SPLIT.split(text) if p.strip(" .")]
    return [parse(p) for p in parts] or [parse(text)]


NUMBER_WORDS = {
    "ein": 1, "eine": 1, "einen": 1, "eins": 1, "zwei": 2, "drei": 3, "vier": 4, "fünf": 5,
    "sechs": 6, "sieben": 7, "acht": 8, "neun": 9, "zehn": 10, "elf": 11, "zwölf": 12,
    "fünfzehn": 15, "zwanzig": 20, "dreißig": 30, "vierzig": 40, "fünfzig": 50, "hundert": 100,
}  # fmt: skip


def parse(text: str) -> tuple[int | None, str, str]:
    """(Menge, Einheit, Name). Ohne führende Zahl: (None, '', Text). Zahlwörter (drei) zählen."""
    first, _, rest = text.strip().partition(" ")
    if first.casefold() in NUMBER_WORDS and rest:
        text = f"{NUMBER_WORDS[first.casefold()]} {rest}"
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


def split_weiter(text: str) -> list[str]:
    """Dauer-Diktat: Abschnitte am gesprochenen Wort „weiter“ trennen (Satzzeichen egal)."""
    parts = re.split(r"[\s,.;:!?-]*\bweiter\b[\s,.;:!?-]*", text, flags=re.IGNORECASE)
    return [p.strip(" .,;:!?-") for p in parts if p.strip(" .,;:!?-")]
