"""REST-API v1: Lesen/Suchen offen, Schreiben nur mit API-Schlüssel (Header X-API-Key oder Bearer).

Grundlage für CLI (tools/lager_cli.py) und MCP-Server (tools/lager_mcp.py).

- `common.py`: JSON-Form, Schlüssel-Prüfung (`read_gate`, `Write`), Nachschlagen per Code/ID
- `bestand.py`, `werkstatt.py`, `einkauf.py`, `system.py`: Endpunkte je Bereich, `register(router)`
"""

from fastapi import APIRouter, Depends

from app.api import bestand, einkauf, system, werkstatt
from app.api.common import item_json, node_json, read_gate

__all__ = ["build_router", "item_json", "node_json"]


def build_router() -> APIRouter:
    router = APIRouter(prefix="/api/v1", tags=["api"], dependencies=[Depends(read_gate)])
    for module in (bestand, werkstatt, einkauf, system):
        module.register(router)
    return router
