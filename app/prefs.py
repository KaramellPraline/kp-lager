"""Einstellungen: Register (Schlüssel, Typ, Standard, Gruppe) -> Einstellungsseite generiert.

Werte liegen in `meta` als `setting:<key>` (siehe codes.get_setting/set_setting).
"""

import sqlite3
from collections.abc import Mapping
from dataclasses import dataclass, field

from app import codes, quick


@dataclass(frozen=True)
class Pref:
    key: str
    label: str
    kind: str  # bool | int | choice | text | textarea
    default: str
    group: str
    help: str = ""
    choices: tuple[tuple[str, str], ...] = field(default_factory=tuple)
    min: int = 0
    max: int = 999


PREFS = (
    Pref("app_name", "Name der App", "text", "KP Lager", "Allgemein"),
    Pref("theme", "Darstellung", "choice", "night", "Allgemein",
         "Crimson Night ist das Designsystem; Hell nur als Ausweichlösung.",
         choices=(("night", "Crimson Night"), ("light", "Hell"))),
    Pref("lang", "Sprache der Namen (Arten, Code-Schema)", "choice", "de", "Allgemein",
         "Schlüssel und Codes sind englisch/neutral; nur die Anzeige wechselt.",
         choices=(("de", "Deutsch"), ("en", "English"))),
    Pref("compact", "Kompakte Listen (mehr Zeilen pro Bildschirm)", "bool", "0", "Allgemein"),
    Pref("home_recent", "Anzahl „Zuletzt angesehen“ im Verlauf", "int", "12", "Allgemein",
         min=0, max=20),
    Pref("home_favorites", "Startseite: Favoriten", "bool", "1", "Startseite"),
    Pref("home_rooms", "Startseite: Räume und Orte", "bool", "1", "Startseite"),
    Pref("auto_item_code", "Neue Teile bekommen automatisch einen ART-Code", "bool", "1",
         "Erfassung", "Aus: Code nur per Knopf „Etikett vergeben“."),
    Pref("scan_beep", "Piepton, wenn ein Code erkannt und erfasst wurde", "bool", "1", "Erfassung",
         "Hoher Ton = erfasst, zwei tiefe Töne = Fehler."),
    Pref("quick_parse", "Schnelleingabe erkennen („3 Rollen Lötzinn“ → Menge, Einheit, Name)",
         "bool", "1", "Erfassung"),
    Pref("default_unit", "Standard-Einheit, wenn eine Menge ohne Einheit kommt", "text", "",
         "Erfassung", "z. B. Stk – leer lassen für keine"),
    Pref("voice_model", "Modell für Spracheingabe", "choice", "parakeet", "Erfassung",
         "parakeet: schneller, im Test genauer; whisper-1: Alternative.",
         choices=(("parakeet", "parakeet"), ("whisper-1", "whisper-1"))),
    Pref("ai_model", "Modell der lokalen KI", "choice", "mid", "Lokale KI",
         "fast: schnell · mid: Allrounder · best: genauer, langsam",
         choices=(("fast", "fast"), ("mid", "mid"), ("best", "best"))),
    Pref("ai_model_enrich", "Modell für Tags & Eigenschaften (Vervollständigen, KI-Support)",
         "choice", "fast", "Lokale KI", "fast reicht meist und ist deutlich schneller.",
         choices=(("fast", "fast"), ("mid", "mid"), ("best", "best"))),
    Pref("label_text_max", "Max. Zeichen Text auf 40×12 (D30)", "int", "24", "Etiketten",
         min=8, max=60),
    Pref("queue_on_quickadd", "Schnelleingabe legt Bin-Etikett in die Warteschlange", "bool",
         "1", "Etiketten"),
    Pref("queue_on_place", "Neuer Einsatz → Etikett in die Warteschlange", "bool", "1",
         "Etiketten"),
    Pref("default_model", "Standard-Modell für neue Sortierkästen", "choice", "norb16",
         "Sortierkästen", choices=(("", "Eigenes Raster"), ("norb16", "Kistenberg NORB16"))),
    Pref("typo_correction", "Tippfehler-Korrektur in der Suche", "bool", "1", "Suche"),
    Pref("synonyms", "Synonyme (eine Gruppe pro Zeile, mit „=“ getrennt)", "textarea",
         quick.DEFAULT_SYNONYMS, "Suche"),
)  # fmt: skip
BY_KEY = {p.key: p for p in PREFS}


def raw(conn: sqlite3.Connection, key: str) -> str:
    return codes.get_setting(conn, key, BY_KEY[key].default)


def flag(conn: sqlite3.Connection, key: str) -> bool:
    return raw(conn, key) == "1"


def number(conn: sqlite3.Connection, key: str) -> int:
    pref = BY_KEY[key]
    try:
        return max(pref.min, min(pref.max, int(raw(conn, key))))
    except ValueError:
        return int(pref.default)


def values(conn: sqlite3.Connection) -> dict[str, str]:
    return {p.key: raw(conn, p.key) for p in PREFS}


def groups() -> dict[str, list[Pref]]:
    out: dict[str, list[Pref]] = {}
    for p in PREFS:
        out.setdefault(p.group, []).append(p)
    return out


def save(conn: sqlite3.Connection, form: Mapping[str, str]) -> None:
    """Formular der Einstellungsseite speichern (fehlende Checkbox = aus)."""
    for p in PREFS:
        if p.kind == "bool":
            value = "1" if form.get(p.key) else "0"
        elif p.kind == "int":
            try:
                value = str(max(p.min, min(p.max, int(form.get(p.key, p.default)))))
            except ValueError:
                value = p.default
        elif p.kind == "choice":
            value = form.get(p.key, p.default)
            if value not in {c for c, _ in p.choices}:
                value = p.default
        else:
            value = str(form.get(p.key, p.default)).strip()
            if p.key == "app_name" and not value:
                value = p.default
        codes.set_setting(conn, p.key, value)
