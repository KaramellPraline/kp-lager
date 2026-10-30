"""Auswahllisten fürs schnelle Anlegen (Filament, UV-Harz): Standardwerte plus alles, was im
Lager schon verwendet wird (häufigste zuerst) – so wächst die Liste von selbst mit."""

import json
import sqlite3
from collections import Counter

from app import materials

# Felder im Anlege-Formular je Kategorie (Reihenfolge = Reihenfolge im Formular)
FORM = {
    "FIL": ("brand", "material", "color", "diameter", "weight"),
    "RES": ("brand", "material", "color", "volume"),
}
DEFAULTS: dict[str, dict[str, tuple[str, ...]]] = {
    "FIL": {
        "brand": ("Prusament", "eSun", "Sunlu", "Bambu Lab", "Creality", "Polymaker", "Elegoo"),
        "material": ("PLA", "PLA+", "PETG", "ABS", "ASA", "TPU", "PA", "PC", "PVA", "PLA-CF",
                     "PETG-CF", "PA-CF"),
        "color": ("Schwarz", "Weiß", "Grau", "Rot", "Blau", "Grün", "Gelb", "Orange",
                  "Transparent", "Natur"),
        "diameter": ("1.75", "2.85"),
        "weight": ("250", "500", "750", "1000", "2000", "3000"),
    },
    "RES": {
        "brand": ("Elegoo", "Anycubic", "Siraya Tech", "Phrozen", "Formlabs"),
        "material": ("Standard", "ABS-like", "Tough", "Flexibel", "Wasserwaschbar",
                     "Hochtemperatur", "Castable", "Dental"),
        "color": ("Grau", "Schwarz", "Weiß", "Transparent", "Klar", "Rot", "Blau", "Grün"),
        "volume": ("250", "500", "1000", "2000"),
    },
}  # fmt: skip


def _used(conn: sqlite3.Connection, material: str, key: str) -> list[str]:
    counts: Counter[str] = Counter()
    for row in conn.execute(
        "SELECT specs FROM item WHERE material = ? AND specs IS NOT NULL", (material,)
    ):
        try:
            value = str(json.loads(row["specs"]).get(key, "")).strip()
        except ValueError:
            continue
        if value:
            counts[value] += 1
    return [v for v, _ in counts.most_common()]


def forms(conn: sqlite3.Connection) -> dict[str, list[dict[str, object]]]:
    """{Präfix: [{key, label, unit, options}]} für die Anlege-Formulare."""
    out: dict[str, list[dict[str, object]]] = {}
    for prefix, keys in FORM.items():
        material = materials.PREFIX_MATERIAL[prefix]
        fields = {f.key: f for f in materials.FIELDS[material]}
        rows: list[dict[str, object]] = []
        for key in keys:
            seen = _used(conn, material, key)
            fixed = [v for v in DEFAULTS[prefix].get(key, ()) if v.casefold() not in
                     {s.casefold() for s in seen}]  # fmt: skip
            rows.append(
                {
                    "key": key,
                    "label": fields[key].de,
                    "unit": fields[key].unit,
                    "options": seen + fixed,
                }  # fmt: skip
            )
        out[prefix] = rows
    return out


def name(values: dict[str, str]) -> str:
    """Name aus den Feldern: „Sunlu PETG Weiß“."""
    parts = (values.get(k, "").strip() for k in ("brand", "material", "color"))
    return " ".join(p for p in parts if p)
