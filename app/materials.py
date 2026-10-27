"""3D-Druck-Material: Filament (FIL-Codes) und UV-Harz (RES-Codes) als Teile mit Eigenschaftsblatt.

Eigenschaften liegen als JSON in `item.specs` (Schlüssel -> Text); welche Felder es gibt, legt
FIELDS fest. Bestell-Link und Preis (`item.order_url`, `item.price`) gelten für alle Teile.
"""

import json
import sqlite3
from typing import NamedTuple

from app.repo import LagerError, Row


class Field(NamedTuple):
    key: str
    group: str  # Abschnitt im Datenblatt
    de: str
    en: str
    unit: str = ""
    hint: str = ""  # Platzhalter im Formular


MATERIALS = {"fil": ("Filament", "Filament", "FIL"), "res": ("UV-Harz", "UV Resin", "RES")}
PREFIX_MATERIAL = {prefix: key for key, (_, _, prefix) in MATERIALS.items()}
GROUPS = {
    "base": ("Allgemein", "General"),
    "print": ("Druck", "Printing"),
    "post": ("Trocknen & Nachbehandlung", "Drying & post-processing"),
    "mech": ("Mechanische Eigenschaften", "Mechanical properties"),
}
_MECH = (
    Field("tensile", "mech", "Zugfestigkeit", "Tensile strength", "MPa"),
    Field("elongation", "mech", "Bruchdehnung", "Elongation at break", "%"),
    Field("flex_modulus", "mech", "Biegemodul", "Flexural modulus", "MPa"),
    Field("impact", "mech", "Schlagzähigkeit", "Impact strength", "kJ/m²"),
    Field("hdt", "mech", "Wärmeformbeständigkeit (HDT)", "Heat deflection (HDT)", "°C"),
    Field("shore", "mech", "Shore-Härte", "Shore hardness", "", "z. B. 85A, 80D"),
)
FIELDS: dict[str, tuple[Field, ...]] = {
    "fil": (
        Field("material", "base", "Werkstoff", "Material", "", "PLA, PETG, ABS, ASA, TPU …"),
        Field("color", "base", "Farbe", "Color"),
        Field("diameter", "base", "Durchmesser", "Diameter", "mm", "1.75"),
        Field("weight", "base", "Netto-Gewicht je Spule", "Net weight per spool", "g", "1000"),
        Field("density", "base", "Dichte", "Density", "g/cm³", "1.24"),
        Field("nozzle_min", "print", "Düsentemperatur min", "Nozzle temp min", "°C"),
        Field("nozzle_max", "print", "Düsentemperatur max", "Nozzle temp max", "°C"),
        Field("bed_min", "print", "Betttemperatur min", "Bed temp min", "°C"),
        Field("bed_max", "print", "Betttemperatur max", "Bed temp max", "°C"),
        Field("chamber", "print", "Bauraumtemperatur", "Chamber temp", "°C", "leer = offen"),
        Field("flow_max", "print", "Max. Volumenfluss", "Max volumetric flow", "mm³/s"),
        Field("speed_max", "print", "Max. Druckgeschwindigkeit", "Max print speed", "mm/s"),
        Field("fan", "print", "Bauteillüfter", "Part cooling fan", "%"),
        Field("retraction", "print", "Retract", "Retraction", "mm"),
        Field("dry_temp", "post", "Trocknen Temperatur", "Drying temp", "°C"),
        Field("dry_hours", "post", "Trocknen Dauer", "Drying time", "h"),
        *_MECH,
    ),
    "res": (
        Field("material", "base", "Harztyp", "Resin type", "", "Standard, ABS-like, Tough, Flex …"),
        Field("color", "base", "Farbe", "Color"),
        Field("volume", "base", "Inhalt je Flasche", "Volume per bottle", "ml", "1000"),
        Field("density", "base", "Dichte", "Density", "g/cm³"),
        Field("viscosity", "base", "Viskosität", "Viscosity", "mPa·s"),
        Field("wavelength", "print", "Wellenlänge", "Wavelength", "nm", "405"),
        Field("layer", "print", "Schichthöhe", "Layer height", "mm", "0.05"),
        Field("exposure", "print", "Belichtung", "Exposure", "s"),
        Field("bottom_exposure", "print", "Bodenbelichtung", "Bottom exposure", "s"),
        Field("bottom_layers", "print", "Bodenschichten", "Bottom layers"),
        Field("temp_min", "print", "Drucktemperatur min", "Print temp min", "°C"),
        Field("temp_max", "print", "Drucktemperatur max", "Print temp max", "°C"),
        Field("wash", "post", "Waschen", "Washing", "", "IPA oder Wasser"),
        Field("cure", "post", "Nachhärten", "Post-cure", "min"),
        *_MECH,
    ),
}


def specs(item: Row) -> dict[str, str]:
    try:
        data = json.loads(item["specs"] or "{}")
    except ValueError:
        return {}
    return {str(k): str(v) for k, v in data.items()} if isinstance(data, dict) else {}


def sheet(item: Row, en: bool = False) -> list[tuple[str, list[tuple[str, str]]]]:
    """Ausgefüllte Eigenschaften gruppiert: [(Abschnitt, [(Bezeichnung, Wert mit Einheit)])]."""
    mat, values = item["material"], specs(item)
    if mat not in FIELDS:
        return []
    out: dict[str, list[tuple[str, str]]] = {}
    for f in FIELDS[mat]:
        if v := values.get(f.key, "").strip():
            out.setdefault(f.group, []).append((f.en if en else f.de, f"{v} {f.unit}".strip()))
    return [(GROUPS[g][1 if en else 0], rows) for g, rows in out.items()]


def unit_price(item: Row) -> str:
    """Preis je kg (Filament) bzw. je Liter (Harz), wenn Preis und Menge je Gebinde bekannt."""
    values, price = specs(item), item["price"]
    amount_key, label = {"fil": ("weight", "kg"), "res": ("volume", "l")}.get(
        item["material"] or "", ("", "")
    )
    try:
        amount = float(values.get(amount_key, "").replace(",", "."))
    except ValueError:
        return ""
    if not price or amount <= 0:
        return ""
    return f"{price / amount * 1000:.2f} €/{label}".replace(".", ",")


def parse_price(raw: str) -> float | None:
    raw = raw.strip().replace("€", "").replace(",", ".").strip()
    if not raw:
        return None
    try:
        value = float(raw)
    except ValueError:
        raise LagerError(f"Preis '{raw}' ist keine Zahl") from None
    if value < 0:
        raise LagerError("Preis darf nicht negativ sein")
    return round(value, 2)


def save_specs(conn: sqlite3.Connection, item_id: int, material: str, form: dict[str, str]) -> None:
    """Material setzen und Eigenschaften aus dem Formular (Felder spec_<key>) speichern."""
    if material and material not in MATERIALS:
        raise LagerError(f"Unbekanntes Material '{material}'")
    values = {
        f.key: form[f"spec_{f.key}"].strip()
        for f in FIELDS.get(material, ())
        if form.get(f"spec_{f.key}", "").strip()
    }
    with conn:
        conn.execute(
            "UPDATE item SET material = ?, specs = ?, updated_at = datetime('now') WHERE id = ?",
            (material or None, json.dumps(values, ensure_ascii=False), item_id),
        )


def all_materials(conn: sqlite3.Connection) -> list[Row]:
    return conn.execute(
        "SELECT * FROM item WHERE material IS NOT NULL AND archived = 0"
        " ORDER BY material, name COLLATE NOCASE"
    ).fetchall()
