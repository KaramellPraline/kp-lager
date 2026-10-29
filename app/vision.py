"""Foto-Erfassung: ein Foto (Teile, Verpackung, Etikett) -> Name, Kategorie, Menge, Eigenschaften.

Nutzt das Vision-Modell des lokalen KI-Gateways. Die Antwort ist nur ein Vorschlag für das
Startformular; angelegt wird erst, wenn der Mensch auf „Hinzufügen“ drückt.
"""

import base64
import json
import re
from typing import Any

from app import ai, kinds, materials
from app.repo import LagerError


def prompt() -> str:
    cats = " | ".join(f"{p} {label}" for p, label in kinds.ITEM_CATS)
    specs = "; ".join(
        f"{materials.MATERIALS[m][2]}: " + " ".join(f.key for f in materials.FIELDS[m][:8])
        for m in ("fil", "cbl", "psu")
    )
    return (
        "Du siehst ein Foto von Lagerteilen, Verpackung oder einem Etikett. Antworte NUR mit JSON: "
        '{"items":[{"name":"kurzer deutscher Name (max. 24 Zeichen)","full_name":"mit Hersteller/'
        'Größe","cat":"Präfix","qty":Zahl oder null,"unit":"","model":"Typ-/Modellnummer",'
        '"specs":{}}]}. '
        f"cat = {cats}. specs nur mit sicher lesbaren Werten (Zahl ohne Einheit), Schlüssel: "
        f'{specs}. Gleiche Teile zusammenfassen, nichts erfinden, Unsicheres mit "?" im Namen.'
    )


def identify(
    url: str, token: str, model: str, data: bytes, mime: str = "image/jpeg"
) -> list[dict[str, Any]]:
    if not url:
        raise LagerError("Keine lokale KI eingerichtet (LAGER_AI_URL)")
    b64 = base64.b64encode(data).decode()
    messages: list[dict[str, Any]] = [
        {"role": "system", "content": prompt()},
        {"role": "user", "content": [
            {"type": "text", "text": "Welche Teile sind auf dem Foto?"},
            {"type": "image_url", "image_url": {"url": f"data:{mime};base64,{b64}"}},
        ]},
    ]  # fmt: skip
    return parse(ai.chat(url, token, model, messages))


def parse(answer: str) -> list[dict[str, Any]]:
    """Modellantwort -> Liste bereinigter Vorschläge."""
    m = re.search(r"\{.*\}|\[.*\]", answer, flags=re.S)
    if not m:
        raise LagerError("Die KI hat nichts Erkennbares geantwortet")
    try:
        data = json.loads(m.group(0))
    except json.JSONDecodeError:
        raise LagerError("Antwort der KI war kein gültiges JSON") from None
    raw = data.get("items", []) if isinstance(data, dict) else data
    valid = {p for p, _ in kinds.ITEM_CATS}
    out = []
    for r in raw if isinstance(raw, list) else []:
        if not isinstance(r, dict) or not str(r.get("name", "")).strip():
            continue
        cat = str(r.get("cat", "")).upper()
        qty = r.get("qty")
        specs = r.get("specs")
        out.append({
            "name": str(r["name"]).strip()[:60],
            "full_name": str(r.get("full_name") or "").strip(),
            "cat": cat if cat in valid else "ART",
            "qty": qty if isinstance(qty, int) and qty > 0 else None,
            "unit": str(r.get("unit") or "").strip(),
            "model": str(r.get("model") or "").strip(),
            "specs": {str(k): str(v) for k, v in specs.items()} if isinstance(specs, dict) else {},
        })  # fmt: skip
    if not out:
        raise LagerError("Auf dem Foto wurde nichts erkannt")
    return out
