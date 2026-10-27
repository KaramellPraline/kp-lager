"""Inventur-Prompts: kompakt für den Haiku-Chat (mit Datenbank-Kontext) und für lokale Modelle.

Der Kontext kommt aus der DB (`context`): Behälter-Arten, Teile-Kategorien, Tags, Eigenschaften
und alle vorhandenen Behälter mit Code – so kann Haiku gesprochene Namen den Codes zuordnen.
Antwort ist immer JSON im Import-Format (`/import`, app/importer.py).
"""

import sqlite3
from dataclasses import dataclass, field

from app import codes, itemtypes, kinds, materials, repo

SCHEMA = """{"code":"EUR-001","name":"Elektro","kind":"eurobox","parent":"REG-001","grid":null,
 "items":[{"name":"Holzschrauben 4x40","full_name":"Spanplattenschraube 4x40 Torx verzinkt",
   "cat":"CNS","tag":"mechanic","model":"","qty":200,"qty_hint":"","unit":"Stk","slot":null,
   "tags":"schrauben holz befestigung","specs":{}}]}"""
# Eigenschaften, die Haiku aus Diktat/Foto füllen darf (Auswahl: das, was man sagt/sieht)
SPEC_KEYS = {
    "fil": "material color diameter weight nozzle_min nozzle_max bed_min bed_max flow_max",
    "res": "material color volume exposure bottom_exposure",
    "cmp": "manufacturer function package value interface voltage",
}
MAX_CONTAINERS = 400  # Behälterliste im Prompt begrenzen (Tokens)


@dataclass
class Context:
    kinds: list[tuple[str, str, str]] = field(default_factory=list)  # (Schlüssel, Name, Präfix)
    cats: list[tuple[str, str]] = field(default_factory=list)  # (Präfix, Name)
    tags: list[str] = field(default_factory=list)
    containers: list[str] = field(default_factory=list)  # je Behälter eine Zeile
    inbox: str = ""


def context(conn: sqlite3.Connection) -> Context:
    """Aktueller Stand der Datenbank, kompakt für den Prompt."""
    kinds.sync(conn)
    ctx = Context(
        kinds=[(k, kinds.KIND_LABELS[k], p) for k, p in codes.KIND_PREFIX.items() if k != "bin"],
        cats=list(kinds.ITEM_CATS),
        tags=itemtypes.names(conn),
    )
    inbox = repo.get_container(conn, repo.inbox(conn))
    ctx.inbox = (inbox["code"] or "") if inbox else ""
    rows = conn.execute(
        "SELECT c.code, c.name, c.kind, c.position, p.code AS parent FROM container c"
        " LEFT JOIN container p ON p.id = c.parent_id"
        " WHERE c.code IS NOT NULL AND c.kind != 'compartment' ORDER BY c.code LIMIT ?",
        (MAX_CONTAINERS,),
    ).fetchall()
    for r in rows:
        where = f" in {r['parent']}" + (f" {r['position']}" if r["position"] else "")
        ctx.containers.append(
            f"{r['code']} {r['name']} · {r['kind']}{where if r['parent'] else ''}"
        )
    return ctx


def schema() -> str:
    return SCHEMA


def _types_line(types: list[str]) -> str:
    known = ", ".join(types) if types else "mechanic, electronic, smart-home, tbd"
    return f"tag = einer von: {known}. Passt keiner, einen neuen kurzen Tag (klein) vorschlagen."


def base_prompt(ctx: Context) -> str:
    """Prompt für den Haiku-Chat: Schema, Regeln, Kategorien und vorhandene Behälter."""
    kinds_line = ", ".join(f"{k}={label} ({p})" for k, label, p in ctx.kinds)
    cats_line = " | ".join(f"{p} {label}" for p, label in ctx.cats)
    specs_line = "; ".join(f"{materials.MATERIALS[m][2]}: {keys}" for m, keys in SPEC_KEYS.items())
    tags_line = ", ".join(ctx.tags) or "noch keine"
    boxes = "\n".join(ctx.containers) or "(noch keine)"
    inbox = (
        f"in den Behälter {ctx.inbox} (Zu sortieren)" if ctx.inbox
        else '{"code": null, "name": "Zu sortieren", "kind": "box"}'
    )  # fmt: skip
    return f"""Lagerinventur. Antworte NUR mit JSON (Array von Behältern), ohne Text drumherum:
[{SCHEMA}]

Behälter: code = Code aus der Liste unten oder vom Etikett ("eur1" -> "EUR-001"). Neuer Behälter
ohne Code: "code": null, das System vergibt einen. parent = Code des übergeordneten Behälters.
kind = {kinds_line}. grid "SpaltenxZeilen" nur bei Sortierkästen, sonst null.
Teile: name max. 24 Zeichen (Etikett), deutsch und suchbar; full_name mit Hersteller/Serie/Größe, sonst "".
cat = {cats_line}. tag = einer von: {tags_line}; passt keiner: neuer kurzer Tag, klein.
model = Teile-/Modellnummer (wichtig bei Elektronik), sonst "". qty nur bei genannter Zahl
(Zahlwörter als Ziffern), sonst null + qty_hint ("ca. 20", "viele"). slot = Fach im Sortierkasten (B3).
tags = 2-5 Suchwörter (Oberbegriff, Zweck). specs nur bei FIL/RES/CMP mit genannten oder sicher
bekannten Werten (Zahl ohne Einheit), Schlüssel: {specs_line}; sonst {{}}.
Gleiches zusammenfassen, nichts erfinden, Unsicheres mit "?" im Namen. Teile ohne erkennbaren
Behälter {inbox}. Schon vorhandene Teile nicht doppelt anlegen.

Vorhandene Behälter (Code Name · Art · in Eltern-Code):
{boxes}"""


def for_container(
    code: str, kind: str, name: str, parent_code: str | None, grid: str | None,
    ctx: Context | None = None,
) -> str:  # fmt: skip
    """Prompt + Kopfzeile für genau diesen Behälter – Foto dazu in den Chat, Antwort in /import."""
    head = f"Behälter: code={code}, kind={kind}, name={name}, parent={parent_code or 'null'}" + (
        f", grid={grid}" if grid else ""
    )
    return (
        f"{base_prompt(ctx or Context())}\n\n{head}\n"
        "Inhalt: (Foto anhängen und/oder hier beschreiben)"
    )


def for_dictation(transcript: str, stamp: str, duration: str, ctx: Context | None = None) -> str:
    """Freies Diktat (mehrere Behälter am Stück) als fertiger Haiku-Prompt."""
    return (
        f"{base_prompt(ctx or Context())}\n\nDiktat vom {stamp} (Dauer {duration}): ich beschreibe "
        "einen oder mehrere Behälter und ihren Inhalt. Ordne gesprochene Namen den vorhandenen "
        "Behältern zu (Name, Ort, Code). Ein Objekt je Behälter, alle als ein JSON-Array.\n\n"
        f"--- Diktat ---\n{transcript.strip() or '(kein Text erkannt)'}\n--- Ende ---"
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


# Richtwerte als Anker für kleine Modelle (übliche Herstellerangaben)
SPEC_HINTS = (
    " Richtwerte Filament: PLA Düse 190-220, Bett 50-60, Dichte 1.24; PETG Düse 230-250, Bett 70-85, "
    "Dichte 1.27; ABS/ASA Düse 240-260, Bett 90-110, Dichte 1.05; TPU Düse 210-230, Bett 40-60. "
    "Volumenfluss üblich 8-25 mm³/s (High-Flow bis 40). Spule netto meist 1000 g, Leerspule 150-260 g."
)


def local_enrich(
    item: dict[str, object], types: list[str], spec_fields: dict[str, str] | None = None
) -> list[dict[str, str]]:
    """Messages, um ein einzelnes Teil zu vervollständigen (optional mit Eigenschaften)."""
    known = {k: item.get(k) or "" for k in ("name", "full_name", "model", "tags", "notes", "unit")}
    specs_rule = ""
    if spec_fields:
        known["specs"] = item.get("specs") or "{}"
        specs_rule = (
            ' Zusätzlich "specs": ein Objekt mit diesen Schlüsseln (Zahl ohne Einheit in der genannten '
            "Einheit, sonst kurzer Text): "
            + "; ".join(f"{k} = {label}" for k, label in spec_fields.items())
            + ". Nur Werte eintragen, die du für genau dieses Produkt oder den Werkstoff sicher "
            "kennst; sonst leer lassen. Lieber leer als geraten." + SPEC_HINTS
        )
    return [
        {"role": "system", "content": (
            "Du ergänzt Lagerdaten zu einem Teil. Antworte nur mit einem JSON-Objekt mit den Feldern "
            '{"name","full_name","type","model","tags","datasheet_url"}. Deutsch. '
            "name max. 24 Zeichen (Anzeigename). full_name vollständig mit Hersteller/Serie, falls bekannt. "
            f"{_types_line(types)} model = Teile-/Modellnummer, auch wenn sie im Namen steckt. "
            "tags = ein String mit 3-6 Suchwörtern, durch Leerzeichen getrennt. "
            "datasheet_url nur, wenn du die direkte Hersteller-PDF sicher kennst, sonst leer. Erfinde nichts."
            + specs_rule)},
        {"role": "user", "content": f"Bekannte Daten: {known}"},
    ]  # fmt: skip
