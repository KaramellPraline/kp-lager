"""Gemeinsames der REST-API: JSON-Form von Teilen/Behältern, Schlüssel-Prüfung (`read_gate`,
`Write`), Nachschlagen per Code oder ID, ausführliche Teil-Ansicht."""

import sqlite3
from typing import Annotated, Any

from fastapi import Depends, Header, HTTPException, Request

from app import (
    apikeys,
    cards,
    catalog,
    codes,
    itemtypes,
    materials,
    prefs,
    projects,
    purchases,
    repo,
)
from app.deps import Conn as Conn  # Verbindung je Request
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


def presented(x_api_key: str, authorization: str) -> str:
    return x_api_key or authorization.removeprefix("Bearer ").strip()


def read_gate(
    request: Request,
    conn: Conn,
    x_api_key: Annotated[str, Header()] = "",
    authorization: Annotated[str, Header()] = "",
) -> None:
    """Lesen ist offen – außer die Einstellung „auch Lesen nur mit Schlüssel“ ist an."""
    if (
        request.method == "GET"
        and prefs.flag(conn, "api_read_key")
        and not apikeys.verify(conn, presented(x_api_key, authorization), need="read")
    ):
        raise HTTPException(401, "API-Schlüssel fehlt oder ist ungültig (auch zum Lesen)")


def require_key(
    conn: Conn,
    x_api_key: Annotated[str, Header()] = "",
    authorization: Annotated[str, Header()] = "",
) -> None:
    if not prefs.flag(conn, "api_write_key"):  # Debug-Modus: Schreiben ohne Schlüssel
        return
    key = presented(x_api_key, authorization)
    scope = apikeys.scope_of(conn, key)
    if scope is None:
        raise HTTPException(401, "API-Schlüssel fehlt oder ist ungültig (nur Schreiben)")
    if scope != "write":
        raise HTTPException(403, "Dieser Schlüssel darf nur lesen")


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


def bad(exc: LagerError) -> HTTPException:
    return HTTPException(400, str(exc))


def item_detail(conn: sqlite3.Connection, i: Row) -> dict[str, Any]:
    """Teil mit allem, was zum Planen nützlich ist (Preis, Mindestbestand, Karten, Einkäufe)."""
    out = item_json(conn, i)
    out.update(
        {
            "notes": i["notes"], "price": i["price"], "min_qty": i["min_qty"],
            "order_qty": i["order_qty"], "on_list": bool(i["on_list"]),
            "order_url": i["order_url"], "lent_to": i["lent_to"], "expires": i["expires"],
            "specs": materials.specs(i), "checked_at": i["checked_at"],
            "ctype": i["ctype"], "fields": catalog.values_of(i),
            "reserved": [{"project": r["name"], "project_id": r["id"], "qty": r["reserved"]}
                         for r in projects.reservations(conn, i["id"])],
            "last_supplier": purchases.last_supplier(conn, i["id"]),
            "cards": [
                {"id": c["id"], "kind": c["kind"], "title": c["title"], "body": c["body"]}
                for c in cards.for_item(conn, i["id"])
            ],
            "purchases": [
                {k: p[k] for k in ("bought_at", "supplier", "qty", "price", "url", "note")}
                for p in purchases.for_item(conn, i["id"])
            ],
        }
    )  # fmt: skip
    return out
