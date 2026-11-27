"""Einstellungen: Register (Schlüssel, Typ, Standard, Gruppe) -> Einstellungsseite generiert.

Werte liegen in `meta` als `setting:<key>` (siehe codes.get_setting/set_setting).
"""

import sqlite3
from collections.abc import Mapping
from dataclasses import dataclass, field

from app import codes, kasten, quick


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
    Pref("label_text_max", "Max. Zeichen Text auf 40×12 (D30)", "int", "24", "Etiketten",
         min=8, max=60),
    Pref("queue_on_quickadd", "Schnelleingabe legt Bin-Etikett in die Warteschlange", "bool",
         "1", "Etiketten"),
    Pref("queue_on_place", "Neuer Einsatz → Etikett in die Warteschlange", "bool", "1",
         "Etiketten"),
    Pref("default_model", "Standard-Modell für neue Sortierkästen", "choice", "norb16",
         "Sortierkästen",
         choices=(("", "Eigenes Raster"), *((k, m.name) for k, m in kasten.MODELS.items()))),
    Pref("backup_days", "Tägliche Backups aufbewahren (Tage)", "int", "30", "Betrieb",
         "Das Backup läuft automatisch einmal am Tag (Datenbank + Fotos) in data/backups.",
         min=3, max=365),
    Pref("backup_extern", "Externes Backup: Zielordner", "text", "", "Backup extern",
         "NAS-Freigabe, USB oder Sync-Ordner. Leer = aus. Die tägliche Sicherung wird zusätzlich "
         "dorthin kopiert. Im Docker-Container den Ordner als Volume einbinden und den Pfad "
         "im Container eintragen (oder LAGER_BACKUP_EXTERN setzen)."),
    Pref("api_write_key", "API: Schreiben nur mit Schlüssel", "bool", "1", "API",
         "An (Standard): Schreiben per API/CLI/MCP braucht einen Schreib-Schlüssel. Aus: im LAN "
         "ohne Schlüssel schreiben – nur zum Testen/Debuggen, danach wieder einschalten."),
    Pref("api_read_key", "API: auch Lesen nur mit Schlüssel", "bool", "0", "API",
         "Aus: Lesen im LAN offen, Schreiben nur mit Schlüssel. An: jede API-Anfrage braucht "
         "einen (Lese- oder Schreib-)Schlüssel – sinnvoll bei Zugriff von außen."),
    Pref("inventory_days", "Inventur fällig nach (Tagen)", "int", "180", "Betrieb",
         min=7, max=3650),
    Pref("slicer_dir", "Ordner mit exportiertem G-Code (Creality Print)", "text", "", "Betrieb",
         "Unter Mehr › Slicer wird dieser Ordner eingelesen (Exportordner von Creality Print)."),
    Pref("session_days", "Angemeldet bleiben (Tage ohne Nutzung)", "int", "30", "Anmeldung",
         "Gleitend: jede Nutzung verlängert die Sitzung. Abmelden beendet sie sofort.",
         min=1, max=365),
    Pref("d30_bridge", "D30 über die PC-Bridge (Windows-Client) drucken", "bool", "0", "Druck",
         "Für einen Server ohne Bluetooth (Docker). LAGER_D30_BRIDGE hat Vorrang."),
    Pref("typo_correction", "Tippfehler-Korrektur in der Suche", "bool", "1", "Suche"),
    Pref("synonyms", "Synonyme (eine Gruppe pro Zeile, mit „=“ getrennt)", "textarea",
         quick.DEFAULT_SYNONYMS, "Suche"),
)  # fmt: skip
BY_KEY = {p.key: p for p in PREFS}

# Reiter der Einstellungen: welche Gruppen dort als Formular erscheinen (Reihenfolge = Anzeige).
# „API“, „Backup extern“, „Druck“: Karten unter Anbindungen; „Anmeldung“: unter Benutzer.
TABS: dict[str, tuple[str, ...]] = {
    "allgemein": ("Allgemein", "Startseite"),
    "bedienung": ("Erfassung", "Etiketten", "Sortierkästen", "Suche"),
    "anbindungen": ("API", "Backup extern", "Druck"),
    "benutzer": ("Anmeldung",),
    "system": ("Betrieb",),
}


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


def groups(tab: str = "") -> dict[str, list[Pref]]:
    """Gruppen mit ihren Einstellungen; mit `tab` nur die Gruppen dieses Reiters."""
    out: dict[str, list[Pref]] = {g: [] for g in TABS.get(tab, ())}
    for p in PREFS:
        if not tab or p.group in out:
            out.setdefault(p.group, []).append(p)
    return out


def keys_of(*tab_or_groups: str) -> set[str]:
    """Schlüssel der Einstellungen in den genannten Reitern bzw. Gruppen."""
    names = {g for t in tab_or_groups for g in TABS.get(t, (t,))}
    return {p.key for p in PREFS if p.group in names}


def save(conn: sqlite3.Connection, form: Mapping[str, str], only: set[str] | None = None) -> None:
    """Formular speichern (fehlende Checkbox = aus); `only`: nur diese Schlüssel (ein Reiter)."""
    for p in PREFS:
        if only is not None and p.key not in only:
            continue
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
