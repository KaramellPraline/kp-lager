"""REST-API v1: Lesen/Suchen offen, Schreiben nur mit API-Schlüssel (Header X-API-Key oder Bearer).

Grundlage für CLI (tools/lager_cli.py) und MCP-Server (tools/lager_mcp.py).
"""

import sqlite3
from collections.abc import Callable, Iterator
from typing import Annotated, Any

from fastapi import APIRouter, Depends, Header, HTTPException
from pydantic import BaseModel

from app import apikeys, codes, importer, itemtypes, prefs, quick, repo, search, withdrawals
from app.repo import LagerError, Row


def item_json(conn: sqlite3.Connection, i: Row | dict[str, Any]) -> dict[str, Any]:
    t = itemtypes.get(conn, int(i["type_id"])) if i["type_id"] else None
    return {
        "id": i["id"], "code": i["code"], "name": i["name"], "full_name": i["full_name"],
        "qty": i["qty"], "qty_hint": i["qty_hint"], "unit": i["unit"], "tags": i["tags"],
        "model": i["model"], "type": t["name"] if t else None,
        "container_id": i["container_id"], "path": repo.path_label(conn, i["container_id"]),
        "review": bool(i["review"]), "archived": bool(i["archived"]),
    }  # fmt: skip


def node_json(conn: sqlite3.Connection, c: Row | dict[str, Any]) -> dict[str, Any]:
    return {"id": c["id"], "code": c["code"], "name": c["name"], "kind": c["kind"],
            "position": c["position"], "path": repo.path_label(conn, c["id"])}  # fmt: skip


class NewItem(BaseModel):
    container: str  # Code oder ID des Behälters
    text: str  # Schnelleingabe, z. B. "3 Rollen Lötzinn und 50 M3 Muttern"


class Take(BaseModel):
    qty: int = 1


class Move(BaseModel):
    container: str


class ImportText(BaseModel):
    text: str  # JSON im Import-Format (Haiku/lokale KI)
    review: bool = True


def build_router(get_conn: Callable[[], Iterator[sqlite3.Connection]]) -> APIRouter:
    router = APIRouter(prefix="/api/v1", tags=["api"])
    Conn = Annotated[sqlite3.Connection, Depends(get_conn)]

    def require_key(
        conn: Conn,
        x_api_key: Annotated[str, Header()] = "",
        authorization: Annotated[str, Header()] = "",
    ) -> None:
        key = x_api_key or authorization.removeprefix("Bearer ").strip()
        if not apikeys.verify(conn, key):
            raise HTTPException(401, "API-Schlüssel fehlt oder ist ungültig (nur Schreiben)")

    Write = Depends(require_key)

    def find_node(conn: sqlite3.Connection, ref: str) -> Row:
        node = repo.get_container_by_code(conn, codes.normalize(ref) or ref)
        if node is None and ref.isdigit():
            node = repo.get_container(conn, int(ref))
        if node is None:
            raise HTTPException(404, f"Behälter {ref} nicht gefunden")
        return node

    def find_item(conn: sqlite3.Connection, ref: str) -> Row:
        item = repo.get_item_by_code(conn, codes.normalize(ref) or ref)
        if item is None and ref.isdigit():
            try:
                item = repo.get_item(conn, int(ref))
            except LagerError:
                item = None
        if item is None:
            raise HTTPException(404, f"Teil {ref} nicht gefunden")
        return item

    @router.get("/search")
    def search_items(conn: Conn, q: str = "", limit: int = 30, tag: str = "") -> dict[str, Any]:
        synonyms = repo.parse_synonyms(prefs.raw(conn, "synonyms"))
        t = (
            (itemtypes.by_code(conn, codes.normalize(tag) or tag) or itemtypes.by_name(conn, tag))
            if tag
            else None
        )
        if tag and t is None:
            raise HTTPException(404, f"Tag {tag} nicht gefunden")
        items, corrected = search.run(
            conn, q, synonyms, limit=max(1, min(limit, 100)), tag=t["id"] if t else None
        )
        nodes = search.containers(conn, corrected or q, synonyms)
        return {
            "corrected": corrected,
            "items": [item_json(conn, i) for i in items],
            "containers": [node_json(conn, c) for c in nodes],
        }

    @router.get("/items/{ref}")
    def get_item(conn: Conn, ref: str) -> dict[str, Any]:
        return item_json(conn, find_item(conn, ref))

    @router.get("/containers/{ref}")
    def get_container(conn: Conn, ref: str) -> dict[str, Any]:
        node = find_node(conn, ref)
        return {
            **node_json(conn, node),
            "children": [node_json(conn, c) for c in repo.children(conn, node["id"])],
            "items": [item_json(conn, i) for i in repo.items_in(conn, node["id"])],
        }

    @router.get("/containers")
    def roots(conn: Conn) -> list[dict[str, Any]]:
        return [node_json(conn, c) for c in repo.children(conn, None)]

    @router.get("/types")
    def types(conn: Conn) -> list[dict[str, Any]]:
        return [
            {"code": t["code"], "name": t["name"], "items": t["n"]}
            for t in itemtypes.all_types(conn)
        ]

    @router.post("/items", dependencies=[Write])
    def add_items(conn: Conn, body: NewItem) -> list[dict[str, Any]]:
        node = find_node(conn, body.container)
        out = []
        for amount, unit, name in quick.parse_many(body.text):
            item_id = repo.add_item(conn, node["id"], name, qty=amount, unit=unit,
                                    code=codes.new_item_code(conn))  # fmt: skip
            out.append(item_json(conn, repo.get_item(conn, item_id)))
        return out

    @router.post("/items/{ref}/take", dependencies=[Write])
    def take(conn: Conn, ref: str, body: Take) -> dict[str, Any]:
        item = find_item(conn, ref)
        try:
            wid = withdrawals.take(conn, item["id"], body.qty, note="API")
        except LagerError as exc:
            raise HTTPException(400, str(exc)) from None
        return {"withdrawal": wid, "item": item_json(conn, repo.get_item(conn, item["id"]))}

    @router.post("/items/{ref}/move", dependencies=[Write])
    def move(conn: Conn, ref: str, body: Move) -> dict[str, Any]:
        item = find_item(conn, ref)
        repo.move_item(conn, item["id"], find_node(conn, body.container)["id"])
        return item_json(conn, repo.get_item(conn, item["id"]))

    @router.post("/import", dependencies=[Write])
    def import_json(conn: Conn, body: ImportText) -> dict[str, Any]:
        report = importer.run(conn, body.text, commit=True, review=body.review)
        return {
            "errors": report.errors,
            "warnings": report.warnings,
            "items_added": report.items_added,
            "containers_created": report.containers_created,
        }

    return router
