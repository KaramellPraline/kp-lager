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


# --- Planung und Pflege (M36) -------------------------------------------------------------


@mcp.tool()
def overview() -> dict[str, Any]:
    """Lager auf einen Blick: Teile, Behälter, Wert, Nachkauf, Inventur fällig, offene Projekte."""
    return client().overview()


@mcp.tool()
def container_tree(depth: int = 4) -> list[dict[str, Any]]:
    """Behälterbaum (Räume, Regale, Boxen) mit Teilezahl – zum Orientieren vor dem Planen."""
    return client().tree(depth)


@mcp.tool()
def list_items(container: str = "", limit: int = 200, offset: int = 0,
               low_stock: bool = False) -> dict[str, Any]:  # fmt: skip
    """Teile seitenweise mit Menge, Preis, Specs, Karten, Einkäufen. container = Code/ID
    (inkl. Unterbehälter); low_stock = nur unter Mindestbestand."""
    return client().items(container, limit, offset, low_stock)


@mcp.tool()
def update_item(ref: str, fields: dict[str, Any]) -> dict[str, Any]:
    """Teil ändern (Schlüssel nötig). Felder: name, full_name, unit, notes, model, tags,
    order_url, qty (absolut), qty_delta (relativ), min_qty, order_qty, price (€/Stück),
    on_list (Einkaufsliste), archived."""
    return client().patch_item(ref, **fields)


@mcp.tool()
def remove_item(ref: str, hard: bool = False) -> dict[str, Any]:
    """Teil archivieren (rückholbar) oder mit hard=true endgültig löschen (Schlüssel nötig)."""
    return client().delete_item(ref, hard)


@mcp.tool()
def create_container(name: str, kind: str = "box", parent: str = "", notes: str = "",
                     dims: str = "") -> dict[str, Any]:  # fmt: skip
    """Behälter anlegen (Schlüssel nötig); kind = Art (siehe get_schema), parent = Code/ID."""
    return client().create_container(name, kind, parent, notes, dims)


@mcp.tool()
def update_container(ref: str, name: str | None = None, notes: str | None = None,
                     parent: str | None = None) -> dict[str, Any]:  # fmt: skip
    """Behälter umbenennen, Notiz ändern oder umlagern (parent = neuer Code/ID, '' = oben)."""
    fields = {
        k: v for k, v in {"name": name, "notes": notes, "parent": parent}.items() if v is not None
    }
    return client().patch_container(ref, **fields)


@mcp.tool()
def list_projects() -> list[dict[str, Any]]:
    """Projekte mit Zahl der Stücklistenzeilen."""
    return client().projects()


@mcp.tool()
def get_project(project_id: int) -> dict[str, Any]:
    """Projekt mit Stückliste, Bestandsabgleich (ok/teil/fehlt), Fehlmengen und Kosten."""
    return client().project(project_id)


@mcp.tool()
def plan_project(name: str, lines: list[dict[str, Any]], notes: str = "") -> dict[str, Any]:
    """Projekt mit Stückliste anlegen (Schlüssel nötig). lines: [{"item": "ART-0007", "qty": 5}]
    für vorhandene Teile oder [{"name": "BME280 Sensor", "qty": 1}] für Neues. Die Antwort zeigt
    sofort, was verfügbar ist und was fehlt."""
    return client().create_project(name, lines, notes)


@mcp.tool()
def add_project_lines(project_id: int, lines: list[dict[str, Any]]) -> dict[str, Any]:
    """Zeilen zu einem Projekt ergänzen (Schlüssel nötig), Format wie bei plan_project."""
    return client().project_add_lines(project_id, lines)


@mcp.tool()
def project_missing_to_shopping(project_id: int) -> dict[str, Any]:
    """Fehlmengen bekannter Teile des Projekts auf die Einkaufsliste setzen (Schlüssel nötig)."""
    return client().project_to_shopping(project_id)


@mcp.tool()
def list_suppliers() -> list[dict[str, Any]]:
    """Lieferanten mit Zahl der Einkäufe und Summe."""
    return client().suppliers()


@mcp.tool()
def record_purchase(ref: str, supplier: str = "", qty: int | None = None,
                    price: float | None = None, url: str = "", note: str = "",
                    bought_at: str = "") -> dict[str, Any]:  # fmt: skip
    """Einkauf zu einem Teil erfassen (Schlüssel nötig); price = Stückpreis in Euro."""
    return client().add_purchase(ref, supplier=supplier, qty=qty, price=price, url=url,
                                 note=note, bought_at=bought_at)  # fmt: skip


@mcp.tool()
def add_card(ref: str, title: str, body: str = "", kind: str = "note",
             container: bool = False) -> dict[str, Any]:  # fmt: skip
    """Notiz- oder Pinout-Karte an ein Teil (oder mit container=true an einen Behälter) hängen.
    kind 'pinout': eine Zeile je Pin, 'Pin; Funktion; Hinweis'."""
    return client().add_card(ref, title, body, kind, container)


@mcp.tool()
def inventory_due() -> list[dict[str, Any]]:
    """Behälter, deren Inventur fällig ist."""
    return client().inventory_due()


@mcp.tool()
def inventory_confirm(ref: str, counted_qty: int | None = None) -> dict[str, Any]:
    """Teil per Inventur bestätigen (Schlüssel nötig); counted_qty korrigiert die Menge."""
    return client().inventory_confirm(ref, counted_qty)


@mcp.tool()
def inventory_finish(container: str) -> dict[str, Any]:
    """Inventur eines Behälters abschließen (Schlüssel nötig)."""
    return client().inventory_done(container)


if __name__ == "__main__":
    mcp.run()
