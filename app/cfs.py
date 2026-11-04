"""CFS-NFC-Platte (Creality Filament System): Daten fürs Filament und Übergabe an die App SpoolID.

Der Tag (MIFARE Classic 1K) wird nicht vom Lager beschrieben, sondern mit der Android-App „SpoolID“
(`dngsoftware.spoolid`). Das Lager liefert die Werte zum Eintragen, kopiert sie auf Wunsch in die
Zwischenablage (Android-App) und stellt das 3D-Modell der Träger-Platte bereit (`cad/cfs_tag.py`).
"""

import math
import re
import sqlite3

from app import materials
from app.repo import LagerError, Row

SPOOLID_PACKAGE = "dngsoftware.spoolid"
PLAY_URL = f"https://play.google.com/store/apps/details?id={SPOOLID_PACKAGE}"
MODEL_STL = "/static/cad/cfs-platte.stl"
MODEL_STEP = "/static/cad/cfs-platte.step"

_HEX = re.compile(r"^#?([0-9a-fA-F]{6})$")
# Farbwörter -> Hex, falls kein Hex-Wert eingetragen ist
_COLORS = {
    "weiß": "FFFFFF", "weiss": "FFFFFF", "white": "FFFFFF", "schwarz": "000000", "black": "000000",
    "rot": "FF0000", "red": "FF0000", "blau": "0000FF", "blue": "0000FF", "grün": "008000",
    "gruen": "008000", "green": "008000", "gelb": "FFFF00", "yellow": "FFFF00", "orange": "FFA500",
    "grau": "808080", "gray": "808080", "grey": "808080", "silber": "C0C0C0", "silver": "C0C0C0",
    "gold": "FFD700", "braun": "8B4513", "brown": "8B4513", "lila": "800080", "purple": "800080",
    "rosa": "FFC0CB", "pink": "FFC0CB", "transparent": "F5F5F5", "natur": "F5F5DC",
}  # fmt: skip


def color_hex(values: dict[str, str]) -> str | None:
    """Hex-Farbe ohne # (großgeschrieben): erst Feld „Farbe (Hex)“, dann bekannte Farbwörter."""
    m = _HEX.match(values.get("color_hex", "").strip())
    if m:
        return m.group(1).upper()
    word = values.get("color", "").strip().lower()
    return _COLORS.get(word.split()[0]) if word else None


def length_m(values: dict[str, str]) -> int | None:
    """Fadenlänge in Metern aus Gewicht, Durchmesser und Dichte (Standard 1,75 mm / 1,24 g/cm³)."""
    weight = materials._num(values.get("weight", ""))
    if not weight or weight <= 0:
        return None
    dia = materials._num(values.get("diameter", "")) or 1.75
    dens = materials._num(values.get("density", "")) or 1.24
    area_cm2 = math.pi * (dia / 20) ** 2
    return round(weight / dens / area_cm2 / 100)


def serial(code: str | None, item_id: int) -> str:
    """6-stellige Seriennummer aus dem Lager-Code (FIL-007 → 000007)."""
    digits = re.sub(r"\D", "", code or "") or str(item_id)
    return digits[-6:].zfill(6)


def spec(item: Row) -> dict[str, str | int | None]:
    """Alle Werte, die in SpoolID einzutragen sind."""
    if item["material"] != "fil":
        raise LagerError("CFS-Platten gibt es nur für Filament")
    values = materials.specs(item)
    weight = materials._num(values.get("weight", ""))
    return {
        "code": item["code"],
        "name": item["name"],
        "brand": values.get("brand", ""),
        "material": values.get("material", ""),
        "color": values.get("color", ""),
        "color_hex": color_hex(values),
        "weight_g": round(weight) if weight else None,
        "length_m": length_m(values),
        "serial": serial(item["code"], item["id"]),
    }


def handoff_text(s: dict[str, str | int | None]) -> str:
    """Text für die Zwischenablage / Teilen-Dialog."""
    rows = [
        ("Filament", s["name"]),
        ("Hersteller", s["brand"]),
        ("Material", s["material"]),
        ("Farbe", f"#{s['color_hex']}" if s["color_hex"] else s["color"]),
        ("Gewicht", f"{s['weight_g']} g" if s["weight_g"] else ""),
        ("Länge", f"{s['length_m']} m" if s["length_m"] else ""),
        ("Seriennummer", s["serial"]),
    ]
    return "\n".join(f"{k}: {v}" for k, v in rows if v)


def for_item(conn: sqlite3.Connection, item_id: int) -> dict[str, str | int | None]:
    from app import repo

    return spec(repo.get_item(conn, item_id))
