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
    """Alle Teile-Typen (TYP-Codes) mit Anzahl."""
    return client().types()


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
