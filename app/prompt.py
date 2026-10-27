"""Inventur-Prompts: ausführlich für den Haiku-Chat, kompakt für lokale Modelle.

Beide nehmen die aktuellen Typen (inkl. unterwegs angelegter) dynamisch auf. Antwort ist immer
JSON im Import-Format (`/import`, app/importer.py).
"""

from app import codes

SCHEMA = """{"code":"EUR-001","name":"kurzer Name","kind":"KINDS",
 "parent":"REG-001 oder null","grid":"6x8 oder null",
 "items":[{"name":"Holzschrauben 4x40","full_name":"Spanplattenschrauben 4x40 Torx, verzinkt",
           "type":"mechanical","model":"","qty":null,"qty_hint":"viele","unit":"Stk",
           "slot":"B3 oder null","tags":"schrauben holz befestigung"}]}"""


def schema() -> str:
    """Import-Schema mit den aktuellen Arten (feste + eigene, englische Schlüssel)."""
    return SCHEMA.replace("KINDS", "|".join(k for k in codes.KIND_PREFIX if k != "bin"))


def _types_line(types: list[str]) -> str:
    known = ", ".join(types) if types else "mechanical, electronic, smart-home, TBD"
    return f"type = einer von: {known}. Passt keiner, einen neuen kurzen Typ (englisch, klein) vorschlagen."


def base_prompt(types: list[str]) -> str:
    """Ausführlicher Prompt für den Haiku-Chat."""
    return f"""Du hilfst mir bei einer Lagerinventur. Ich schicke pro Behälter: Code, Behältertyp,
übergeordneten Behälter, ein Foto und/oder eine Notiz. Antworte NUR mit JSON nach diesem Schema,
ohne Erklärtext:

{schema()}

Regeln: Deutsche, suchbare Bezeichnungen. name = Anzeigename, kurz (max. 24 Zeichen, passt aufs Etikett).
full_name = vollständige Bezeichnung (Hersteller, Serie, Größe), sonst leer.
{_types_line(types)}
model = Modell-/Teilenummer, wenn erkennbar (wichtig bei Elektronik), sonst leer.
Gleichartiges zusammenfassen. qty nur bei genannter oder eindeutig zählbarer Zahl, sonst qty_hint ("ca. 20", "viele").
slot = Fach im Sortierkasten (Zeile als Buchstabe, Spalte als Zahl, z. B. B3).
tags = 2-5 Suchbegriffe inkl. Oberbegriff und Verwendungszweck. Nichts erfinden; Unsicheres
mit "?" im Namen markieren. Wenn ich "alle" sage, gib alle bisherigen Behälter als JSON-Array aus."""


def for_container(
    code: str, kind: str, name: str, parent_code: str | None, grid: str | None,
    types: list[str] | None = None,
) -> str:  # fmt: skip
    """Prompt + Kopfzeile für genau diesen Behälter – Foto dazu in den Chat, Antwort in /import."""
    head = f"Behälter: code={code}, kind={kind}, name={name}, parent={parent_code or 'null'}" + (
        f", grid={grid}" if grid else ""
    )
    return (
        f"{base_prompt(types or [])}\n\n{head}\nInhalt: (Foto anhängen und/oder hier beschreiben)"
    )


def for_dictation(
    transcript: str, stamp: str, duration: str, types: list[str] | None = None
) -> str:
    """Freies Diktat (mehrere Behälter am Stück) als fertiger Haiku-Prompt."""
    return (
        f"{base_prompt(types or [])}\n\nDiktat vom {stamp} (Dauer {duration}). Darin beschreibe ich einen oder "
        "mehrere Behälter mit Code und Inhalt. Erzeuge für jeden genannten Behälter ein Objekt "
        "und gib alle als JSON-Array aus. Behälter ohne erkennbaren Code lässt du im JSON weg "
        'und nennst sie danach in einer Zeile "Ohne Code: …".\n\n--- Diktat ---\n'
        f"{transcript.strip() or '(kein Text erkannt)'}\n--- Ende ---"
    )


# --- Kompakt für lokale Modelle (kleiner Kontext, strikte Ausgabe) ------------------------


def local_system(types: list[str]) -> str:
    return (
        "Du wandelst Lager-Notizen in JSON um. Antworte ausschließlich mit gültigem JSON, "
        "ohne Markdown, ohne Erklärung. Deutsch. Erfinde nichts.\n"
        f"Schema (Array von Behältern):\n[{schema()}]\n"
        "name max. 24 Zeichen. Zahlwörter als Ziffern (zwei -> qty 2). qty nur bei genannter Zahl, "
        "sonst null und qty_hint. "
        f"{_types_line(types)} model = Teile-/Modellnummer, auch wenn sie im Namen steckt "
        "(z. B. BME280, ESP32-WROOM-32, UT61E), sonst leer. tags = ein String mit 2-5 Suchwörtern."
    )


def local_for_text(text: str, code: str | None = None, name: str = "", kind: str = "") -> str:
    """Nutzerteil für Diktat oder Behälternotiz. Ohne Code: Behälter mit code null weglassen."""
    head = f"Behälter: code={code}, kind={kind}, name={name}. " if code else ""
    return f"{head}Notiz:\n{text.strip()}\nGib das JSON-Array aus."


def local_enrich(item: dict[str, object], types: list[str]) -> list[dict[str, str]]:
    """Messages, um ein einzelnes Teil zu vervollständigen."""
    known = {k: item.get(k) or "" for k in ("name", "full_name", "model", "tags", "notes", "unit")}
    return [
        {"role": "system", "content": (
            "Du ergänzt Lagerdaten zu einem Teil. Antworte nur mit einem JSON-Objekt mit den Feldern "
            '{"name","full_name","type","model","tags","datasheet_url"}. Deutsch. '
            "name max. 24 Zeichen (Anzeigename). full_name vollständig mit Hersteller/Serie, falls bekannt. "
            f"{_types_line(types)} model = Teile-/Modellnummer, auch wenn sie im Namen steckt. "
            "tags = ein String mit 3-6 Suchwörtern, durch Leerzeichen getrennt. "
            "datasheet_url nur, wenn du die direkte Hersteller-PDF sicher kennst, sonst leer. Erfinde nichts.")},
        {"role": "user", "content": f"Bekannte Daten: {known}"},
    ]  # fmt: skip
