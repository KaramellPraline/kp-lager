"""REST-API v1: Lesen/Suchen offen, Schreiben nur mit API-Schlüssel (Header X-API-Key oder Bearer).

Grundlage für CLI (tools/lager_cli.py) und MCP-Server (tools/lager_mcp.py).
"""

import sqlite3
from collections.abc import Callable, Iterator
from typing import Annotated, Any

from fastapi import APIRouter, Depends, Header, HTTPException
from pydantic import BaseModel

from app import (
    apikeys,
    bulk,
    codes,
    creation,
    dryer,
    importer,
    itemtypes,
    kinds,
    materials,
    prefs,
    quick,
    repo,
    search,
    slicer,
    value,
    withdrawals,
)
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


class NewTyped(BaseModel):
    container: str
    name: str = ""
    cat: str = "ART"  # Präfix, siehe GET /schema
    qty: int | None = None
    unit: str = ""
    count: int = 1  # Kabel/Netzteile: so viele Einzelstücke
    specs: dict[str, str] = {}  # Schlüssel siehe GET /schema (fields je Kategorie)


class BulkBody(BaseModel):
    refs: list[str]  # "i12" (Teil) oder "c5" (Behälter)
    action: str  # siehe GET /schema (bulk_actions)
    value: str = ""
    container: str = ""  # Ziel bei action=move


class DryStart(BaseModel):
    item: str
    program: str  # Name oder ID des Programms


class Take(BaseModel):
    qty: int = 1


class Move(BaseModel):
    container: str


class ImportText(BaseModel):
    text: str  # JSON im Import-Format (Haiku/lokale KI)
    review: bool = False


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
        report = importer.run(
            conn,
            body.text,
            commit=True,
            review=body.review,
        )
        return {
            "errors": report.errors,
            "warnings": report.warnings,
            "items_added": report.items_added,
            "containers_created": report.containers_created,
        }

    # --- Schema: damit CLI/MCP neue Kategorien, Arten und Felder ohne Codeänderung kennen --------

    @router.get("/schema")
    def schema(conn: Conn) -> dict[str, Any]:
        """Kategorien (Präfix, Name, Felder), Behälterarten, Tags, Aktionen – immer aktuell."""
        kinds.sync(conn)
        cats = []
        for prefix, label in kinds.ITEM_CATS:
            profile = materials.PREFIX_MATERIAL.get(prefix)
            fields = [
                {"key": f.key, "label": f.de, "unit": f.unit, "hint": f.hint}
                for f in materials.FIELDS.get(profile or "", ())
            ]
            cats.append({"prefix": prefix, "name": label, "profile": profile, "fields": fields,
                         "single_piece": prefix in repo.INDIVIDUAL})  # fmt: skip
        return {
            "categories": cats,
            "container_kinds": [
                {"key": k, "name": kinds.KIND_LABELS[k], "prefix": p}
                for k, p in codes.KIND_PREFIX.items()
            ],
            "tags": itemtypes.names(conn),
            "eurobox_dims_mm": kinds.EURO_DIMS,
            "bulk_actions": {k: v[0] for k, v in bulk.ACTIONS.items()},
            "dryer_programs": [
                {"id": p["id"], "name": p["name"], "temp_c": p["temp_c"], "hours": p["hours"]}
                for p in dryer.programs(conn)
            ],
        }

    @router.get("/shopping")
    def shopping(conn: Conn) -> dict[str, Any]:
        rows = repo.shopping_list(conn)
        return {
            "total_eur": round(sum(r["cost"] for r in rows if r["cost"] is not None), 2),
            "items": [
                {**item_json(conn, r), "need": r["need"], "cost": r["cost"],
                 "ordered_at": r["ordered_at"], "order_url": r["order_url"]}
                for r in rows
            ],
        }  # fmt: skip

    @router.get("/value")
    def worth(conn: Conn, container: str = "") -> dict[str, Any]:
        if container:
            node = find_node(conn, container)
            amount, unpriced = value.of_container(conn, node["id"])
        else:
            amount, unpriced = value.total(conn)
        return {"value_eur": round(amount, 2), "items_without_price": unpriced}

    @router.get("/dryer")
    def dryer_state(conn: Conn) -> dict[str, Any]:
        return {"running": dryer.running(conn), "history": dryer.history(conn, limit=20),
                "programs": [dict(p) for p in dryer.programs(conn)]}  # fmt: skip

    @router.get("/print-jobs")
    def print_jobs(conn: Conn) -> list[dict[str, Any]]:
        return slicer.jobs(conn)

    @router.post("/items/new", dependencies=[Write])
    def add_typed(conn: Conn, body: NewTyped) -> list[dict[str, Any]]:
        """Teil mit Kategorie und Eigenschaften anlegen (Kabel/Netzteile: je Stück ein Eintrag)."""
        node = find_node(conn, body.container)
        try:
            ids = creation.add(conn, node["id"], body.name, body.cat, body.qty, body.unit,
                               body.specs, body.count)  # fmt: skip
        except LagerError as exc:
            raise HTTPException(400, str(exc)) from None
        return [item_json(conn, repo.get_item(conn, i)) for i in ids]

    @router.post("/bulk", dependencies=[Write])
    def bulk_apply(conn: Conn, body: BulkBody) -> dict[str, str]:
        target = str(find_node(conn, body.container)["id"]) if body.container else ""
        try:
            return {"result": bulk.apply(conn, body.refs, body.action, body.value, target)}
        except LagerError as exc:
            raise HTTPException(400, str(exc)) from None

    @router.post("/dryer/start", dependencies=[Write])
    def dryer_start(conn: Conn, body: DryStart) -> dict[str, Any]:
        item = find_item(conn, body.item)
        wanted = body.program.casefold()
        prog = next(
            (p for p in dryer.programs(conn) if wanted in (str(p["id"]), p["name"].casefold())),
            None,
        )
        if prog is None:
            raise HTTPException(404, f"Programm {body.program} nicht gefunden")
        try:
            return {"log": dryer.start(conn, item["id"], prog["id"], "API")}
        except LagerError as exc:
            raise HTTPException(400, str(exc)) from None

    return router
