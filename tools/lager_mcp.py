"""MCP-Server (stdio) für KP Lager: Suchen/Lesen offen, Schreiben nur mit LAGER_API_KEY.

Start: uv run --group mcp python tools/lager_mcp.py
Konfiguration für Claude Code: siehe docs/mcp.example.json.
"""

import sys
from pathlib import Path
from typing import Any

from mcp.server.fastmcp import FastMCP

sys.path.insert(0, str(Path(__file__).parent))
from lager_client import LagerClient  # noqa: E402

mcp = FastMCP("kp-lager")
_client: LagerClient | None = None


def categories_help() -> str:
    """Kategorien live vom Server, damit neue Kategorien/Felder sofort in den Tools stehen."""
    try:
        cats = client().schema()["categories"]
    except Exception:  # Server gerade nicht erreichbar: Tools trotzdem registrieren
        return "Kategorien: siehe get_schema."
    parts = []
    for c in cats:
        keys = ",".join(f["key"] for f in c["fields"])
        parts.append(
            f"{c['prefix']}={c['name']}"
            + (f" (specs: {keys})" if keys else "")
            + (" [Einzelstück]" if c["single_piece"] else "")
        )
    return "Kategorien: " + "; ".join(parts)


def client() -> LagerClient:
    global _client
    if _client is None:
        _client = LagerClient()
    return _client


@mcp.tool()
def search(query: str, limit: int = 30) -> dict[str, Any]:
    """Teile und Behälter im Lager suchen (tippfehlertolerant), mit Ort (path)."""
    return client().search(query, limit)


@mcp.tool()
def get_item(ref: str) -> dict[str, Any]:
    """Ein Teil per Code (z. B. ART-0007) oder ID lesen."""
    return client().item(ref)


@mcp.tool()
def get_container(ref: str) -> dict[str, Any]:
    """Einen Behälter per Code (z. B. EUR-003) oder ID mit Unterbehältern und Teilen lesen."""
    return client().container(ref)


@mcp.tool()
def list_rooms() -> list[dict[str, Any]]:
    """Oberste Ebene des Lagers (Räume/Standorte)."""
    return client().roots()


@mcp.tool()
def list_types() -> list[dict[str, Any]]:
    """Alle Tags (TAG-Codes) mit Anzahl."""
    return client().types()


@mcp.tool()
def get_schema() -> dict[str, Any]:
    """Aktuelle Kategorien (Präfix, Felder), Behälterarten, Tags, Aktionen, Trockner-Programme."""
    return client().schema(fresh=True)


@mcp.resource("lager://schema")
def schema_resource() -> dict[str, Any]:
    """Das Lager-Schema als Ressource (Kategorien, Arten, Felder)."""
    return client().schema(fresh=True)


@mcp.tool(
    description="Teil mit Kategorie und Eigenschaften anlegen (Schlüssel nötig). "
    "Kabel/Netzteile sind Einzelstücke: count = Anzahl, jedes bekommt ein eigenes Etikett. "
    + categories_help()
)
def add_item(
    container: str, name: str = "", cat: str = "ART", qty: int | None = None, unit: str = "",
    count: int = 1, specs: dict[str, str] | None = None,
) -> list[dict[str, Any]]:  # fmt: skip
    valid = {c["prefix"] for c in client().schema()["categories"]}
    if cat.upper() not in valid:
        raise ValueError(f"Unbekannte Kategorie {cat}. Gültig: {', '.join(sorted(valid))}")
    return client().add_typed(container, name, cat, qty, unit, count, specs)


@mcp.tool()
def bulk_edit(refs: list[str], action: str, value: str = "", container: str = "") -> str:
    """Viele Teile ('i12') / Behälter ('c5') auf einmal ändern (Schlüssel nötig).
    action: move (container = Ziel), tag, cat, min, unit, price, list_on, list_off, label,
    archive, delete – die aktuelle Liste steht in get_schema."""
    return client().bulk(refs, action, value, container)


@mcp.tool()
def shopping_list() -> dict[str, Any]:
    """Einkaufsliste: unter Mindestbestand oder markiert, mit Bedarf, Preis und Summe."""
    return client().shopping()


@mcp.tool()
def stock_value(container: str = "") -> dict[str, Any]:
    """Lagerwert (Menge × Preis) gesamt oder für einen Behälter inkl. Unterbehälter."""
    return client().value(container)


@mcp.tool()
def dryer_status() -> dict[str, Any]:
    """Filament-Trockner: laufende Trocknungen, Verlauf und Programme."""
    return client().dryer()


@mcp.tool()
def start_drying(item: str, program: str) -> dict[str, Any]:
    """Trocknung einer Filamentspule starten (Schlüssel nötig); program = Name oder ID."""
    return client().start_drying(item, program)


@mcp.tool()
def print_jobs() -> list[dict[str, Any]]:
    """Aus dem Slicer (Creality Print) eingelesene Drucke mit Filamentverbrauch."""
    return client().print_jobs()


@mcp.tool()
def add_items(container: str, text: str) -> list[dict[str, Any]]:
    """Teile eintragen (Schlüssel nötig), text z. B. '3 Rollen Lötzinn und 50 M3 Muttern'."""
    return client().add(container, text)


@mcp.tool()
def take_item(ref: str, qty: int = 1) -> dict[str, Any]:
    """Menge eines Teils entnehmen (Schlüssel nötig). Wird nach 7 Tagen automatisch bestätigt."""
    return client().take(ref, qty)


@mcp.tool()
def move_item(ref: str, container: str) -> dict[str, Any]:
    """Teil in einen anderen Behälter umlagern (Schlüssel nötig)."""
    return client().move(ref, container)


if __name__ == "__main__":
    mcp.run()
