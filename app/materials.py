"""3D-Druck-Material: Filament (FIL-Codes) und UV-Harz (RES-Codes) als Teile mit Eigenschaftsblatt.

Eigenschaften liegen als JSON in `item.specs` (Schlüssel -> Text); welche Felder es gibt, legt
FIELDS fest. Bestell-Link und Preis (`item.order_url`, `item.price`) gelten für alle Teile.
"""

import json
import sqlite3
from datetime import date
from typing import NamedTuple

from app import cables, psus
from app.repo import LagerError, Row


class Field(NamedTuple):
    key: str
    group: str  # Abschnitt im Datenblatt
    de: str
    en: str
    unit: str = ""
    hint: str = ""  # Platzhalter im Formular


# Eigenschafts-Profile: Schlüssel -> (Name DE, Name EN, Code-Präfix)
MATERIALS = {
    "fil": ("Filament", "Filament", "FIL"),
    "res": ("UV-Harz", "UV Resin", "RES"),
    "cmp": ("Elektronikbauteil", "Electronic component", "CMP"),
    "cbl": ("Kabel", "Cable", "CBL"),
    "psu": ("Netzteil", "Power supply", "PSU"),
}
PRINTING = ("fil", "res")  # 3D-Druck-Material (Übersicht, Restmenge)
PREFIX_MATERIAL = {prefix: key for key, (_, _, prefix) in MATERIALS.items()}
GROUPS = {
    "base": ("Allgemein", "General"),
    "print": ("Druck", "Printing"),
    "post": ("Trocknen & Nachbehandlung", "Drying & post-processing"),
    "mech": ("Mechanische Eigenschaften", "Mechanical properties"),
    "elec": ("Elektrische Daten", "Electrical data"),
    "rest": ("Restmenge", "Remaining"),
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
        Field("spool_weight", "base", "Leerspule", "Empty spool", "g", "250"),
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
        Field("bottle_weight", "base", "Leerflasche", "Empty bottle", "g", "120"),
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
    "cmp": (
        Field("manufacturer", "base", "Hersteller", "Manufacturer"),
        Field("function", "base", "Funktion", "Function", "", "z. B. Temperatursensor, MOSFET"),
        Field("package", "base", "Bauform", "Package", "", "SOT-23, DIP-8, 0805, Modul"),
        Field("value", "base", "Wert", "Value", "", "10k, 100nF, 3,3 V"),
        Field("pins", "base", "Pins", "Pins"),
        Field("interface", "elec", "Schnittstelle", "Interface", "", "I2C, SPI, UART, GPIO"),
        Field("voltage", "elec", "Versorgungsspannung", "Supply voltage", "V", "3,3–5"),
        Field("current", "elec", "Max. Strom", "Max current", "A"),
        Field("power", "elec", "Leistung", "Power", "W"),
        Field("tolerance", "elec", "Toleranz", "Tolerance", "%"),
        Field("frequency", "elec", "Frequenz", "Frequency", "MHz"),
        Field("temp_range", "elec", "Temperaturbereich", "Temperature range", "°C", "-40–85"),
    ),
    "cbl": (  # Name wird daraus gebildet: „USB-A – USB-C 2m“ (app/cables.py)
        Field("plug_a", "base", "Stecker Seite A", "Plug side A", "", "USB-A, HDMI, RJ45, DP"),
        Field("plug_b", "base", "Stecker Seite B", "Plug side B", "", "USB-C, Micro-USB, DVI"),
        Field("length", "base", "Länge", "Length", "m", "2"),
        Field("standard", "base", "Standard", "Standard", "", "USB 2.0, DP 1.4, Cat6"),
    ),
    "psu": (  # Name: „Netzteil 12V 2A DC 5,5x2,1“ (app/psus.py)
        Field("volt", "base", "Spannung", "Voltage", "V", "12"),
        Field("amp", "base", "Strom", "Current", "A", "2"),
        Field("plug", "base", "Stecker", "Plug", "", "DC 5,5x2,1, USB-C"),
        Field("watt", "base", "Leistung", "Power", "W", "aus V × A"),
        Field("polarity", "base", "Polarität", "Polarity", "", "Mitte +"),
    ),
}
# Plausible Bereiche für Zahlenwerte der KI; außerhalb -> verworfen (lieber leer als falsch)
PLAUSIBLE: dict[str, tuple[float, float]] = {
    "diameter": (1.0, 3.5), "weight": (100, 10000), "spool_weight": (20, 1000),
    "density": (0.8, 2.5), "nozzle_min": (150, 450), "nozzle_max": (160, 500),
    "bed_min": (0, 150), "bed_max": (0, 160), "chamber": (0, 120), "flow_max": (1, 80),
    "speed_max": (10, 1000), "fan": (0, 100), "retraction": (0, 10), "dry_temp": (30, 120),
    "dry_hours": (1, 48), "tensile": (1, 200), "elongation": (0.5, 900), "flex_modulus": (5, 15000),
    "impact": (0.5, 200), "hdt": (30, 300), "volume": (50, 10000), "bottle_weight": (20, 1000),
    "viscosity": (10, 10000), "wavelength": (350, 420), "layer": (0.01, 0.3), "exposure": (0.5, 60),
    "bottom_exposure": (5, 300), "bottom_layers": (1, 20), "temp_min": (10, 60),
    "temp_max": (15, 80), "cure": (1, 120), "length": (0.05, 100), "volt": (1, 400),
    "amp": (0.01, 100), "watt": (0.1, 5000),
}  # fmt: skip
# Werte in kg statt g (z. B. "1.2" bei Spulengewicht) werden umgerechnet
GRAM_FIELDS = ("weight", "spool_weight", "bottle_weight")


def plausible(key: str, value: str) -> str | None:
    """KI-Wert prüfen: Zahlenfelder nur im plausiblen Bereich, kg -> g; sonst None."""
    if key not in PLAUSIBLE:
        return value
    num = _num(value.split("–")[0].split("-")[0] if value.count("-") <= 1 else value)
    if num is None:
        return None
    if key in GRAM_FIELDS and 0 < num < 10:
        num *= 1000
    low, high = PLAUSIBLE[key]
    if not low <= num <= high:
        return None
    return f"{num:g}"


# Leergewicht, wenn nichts eingetragen ist (typische Werte)
DEFAULT_TARE = {"fil": 250.0, "res": 120.0}
LOW_SHARE = 0.15  # darunter: „fast leer“ und auf die Einkaufsliste


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
    row = conn.execute("SELECT * FROM item WHERE id = ?", (item_id,)).fetchone()
    keys = {f.key for f in FIELDS.get(material, ())}
    # Werte außerhalb des Formulars (z. B. Restmenge aus der Wägung) bleiben erhalten
    kept = {
        k: v
        for k, v in (specs(row) if row else {}).items()
        if k not in keys and k.startswith("rest")
    }
    values = {
        f.key: form[f"spec_{f.key}"].strip()
        for f in FIELDS.get(material, ())
        if form.get(f"spec_{f.key}", "").strip()
    }
    if material == "psu":  # Stecker vereinheitlichen, Leistung aus V × A
        if "plug" in values:
            values["plug"] = psus.plug(values["plug"])
        for key in ("volt", "amp", "watt"):
            if key in values:
                values[key] = values[key].replace(",", ".").rstrip("VvAaWw ").strip()
        values = psus.complete(values)
    if material == "cbl":  # einheitliche Steckernamen: 'DisplayPort' -> 'DP', 'usb c' -> 'USB-C'
        for side in ("plug_a", "plug_b"):
            if side in values:
                values[side] = cables.plug(values[side])
        if "length" in values:
            values["length"] = values["length"].replace(",", ".").removesuffix("m").strip()
    with conn:
        conn.execute(
            "UPDATE item SET material = ?, specs = ?, updated_at = datetime('now') WHERE id = ?",
            (material or None, json.dumps({**kept, **values}, ensure_ascii=False), item_id),
        )
    if material in ("cbl", "psu") and row is not None:
        _auto_name(conn, row, material, values)


def _auto_name(conn: sqlite3.Connection, row: Row, material: str, values: dict[str, str]) -> None:
    """Kabel/Netzteil: Name aus den Feldern; geänderter Name -> Etikett wieder offen."""
    naming = cables if material == "cbl" else psus
    new = naming.name(values)
    if not new or new == row["name"]:
        return
    full = row["full_name"] or naming.full_name(values)
    with conn:
        conn.execute(
            "UPDATE item SET name = ?, full_name = ?, label_printed = 0 WHERE id = ?",
            (new, full, row["id"]),
        )


def cable_specs(text: str, given: dict[str, str] | None = None) -> dict[str, str]:
    """Formularwerte (spec_*) für ein Kabel: angegebene Werte, Rest aus dem Text erkannt."""
    found = {**cables.parse(text), **{k: v for k, v in (given or {}).items() if v}}
    return {f"spec_{k}": v for k, v in found.items()}


def auto_specs(profile: str, text: str, given: dict[str, str] | None = None) -> dict[str, str]:
    """Kabel/Netzteil: Formularwerte aus angegebenen Feldern, Rest aus dem Text erkannt."""
    if profile == "cbl":
        return cable_specs(text, given)
    found = {**psus.parse(text), **{k: v for k, v in (given or {}).items() if v}}
    return {f"spec_{k}": v for k, v in found.items()}


def all_materials(conn: sqlite3.Connection) -> list[Row]:
    return conn.execute(
        "SELECT * FROM item WHERE material IN ('fil', 'res') AND archived = 0"
        " ORDER BY material, name COLLATE NOCASE"
    ).fetchall()


def _num(raw: str) -> float | None:
    try:
        return float(raw.replace(",", ".").strip())
    except (ValueError, AttributeError):
        return None


def remaining(item: Row) -> dict[str, object] | None:
    """Restmenge aus der letzten Wägung: Gramm, Meter (Filament) bzw. ml (Harz), Anteil."""
    if item["material"] not in PRINTING:
        return None
    s = specs(item)
    rest = _num(s.get("rest_g", ""))
    if rest is None:
        return None
    net = _num(s.get("weight" if item["material"] == "fil" else "volume", ""))
    density = _num(s.get("density", "")) or (1.24 if item["material"] == "fil" else 1.1)
    if item["material"] == "fil":
        diameter = _num(s.get("diameter", "")) or 1.75
        meters = rest / density / (3.14159 * (diameter / 2) ** 2)  # g / (g/cm³) = cm³ -> m
        amount = f"≈ {meters:.0f} m"
        full = net
    else:
        amount = f"≈ {rest / density:.0f} ml"
        full = net * density if net else None
    share = rest / full if full else None
    return {
        "grams": rest, "text": f"{rest:.0f} g {amount}", "date": s.get("rest_date", ""),
        "share": share, "low": share is not None and share < LOW_SHARE,
    }  # fmt: skip


def weigh(conn: sqlite3.Connection, item_id: int, gross_raw: str) -> str:
    """Brutto wiegen -> Rest = Brutto - Leergewicht (Spule/Flasche); fast leer -> Einkaufsliste."""
    item = conn.execute("SELECT * FROM item WHERE id = ?", (item_id,)).fetchone()
    if item is None or item["material"] not in PRINTING:
        raise LagerError("Wiegen gibt es nur für Filament und Harz")
    gross = _num(gross_raw)
    if gross is None or gross <= 0:
        raise LagerError("Bitte das Gewicht in Gramm eintragen")
    s = specs(item)
    tare_key = "spool_weight" if item["material"] == "fil" else "bottle_weight"
    tare = _num(s.get(tare_key, ""))
    assumed = tare is None
    tare = DEFAULT_TARE[item["material"]] if tare is None else tare
    rest = max(0.0, gross - tare)
    s["rest_g"] = f"{rest:.0f}"
    s["rest_date"] = date.today().isoformat()
    with conn:
        conn.execute(
            "UPDATE item SET specs = ?, updated_at = datetime('now') WHERE id = ?",
            (json.dumps(s, ensure_ascii=False), item_id),
        )
    info = remaining(conn.execute("SELECT * FROM item WHERE id = ?", (item_id,)).fetchone())
    msg = f"Rest: {info['text'] if info else f'{rest:.0f} g'}"
    if assumed:
        msg += f" (Leergewicht {tare:.0f} g angenommen – im Datenblatt eintragen)"
    if info and info["low"]:
        with conn:
            conn.execute("UPDATE item SET on_list = 1 WHERE id = ?", (item_id,))
        msg += " · fast leer, auf die Einkaufsliste gesetzt"
    return msg
