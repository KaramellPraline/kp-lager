"""API-Erweiterung: Überblick, Baum, Bearbeiten, Projekte/Stückliste, Einkäufe, Karten, Inventur.

Wird von `api.build_router` eingehängt; Lesen folgt den Regeln des Routers, Schreiben braucht
einen Schreib-Schlüssel (`Write`).
"""

import sqlite3
from collections.abc import Callable
from typing import Any

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from app import (
    __version__,
    cards,
    catalog,
    codes,
    inventory,
    kinds,
    materials,
    prefs,
    projects,
    purchases,
    repo,
    scheduler,
    sortiment,
    value,
)
from app.repo import LagerError, Row

JsonFn = Callable[..., dict[str, Any]]
FindFn = Callable[[sqlite3.Connection, str], Row]


class ItemPatch(BaseModel):
    name: str | None = None
    full_name: str | None = None
    unit: str | None = None
    notes: str | None = None
    model: str | None = None
    tags: str | None = None
    order_url: str | None = None
    qty: int | None = None  # absolut setzen (wird als Buchung mit Notiz „API“ erfasst)
    qty_delta: int | None = None  # oder relativ ändern
    min_qty: int | None = None
    order_qty: int | None = None
    price: float | None = None  # Stückpreis in Euro
    on_list: bool | None = None  # auf die Einkaufsliste
    archived: bool | None = None
    ctype: str | None = None  # Typ-Schlüssel (GET /types/catalog), "" = Typ entfernen
    fields: dict[str, str] | None = None  # Felder des Typs; mit rename=true Name neu bilden
    rename: bool = False


class ContainerNew(BaseModel):
    name: str
    kind: str = "box"  # Schlüssel oder Präfix, siehe GET /schema
    parent: str = ""  # Code oder ID; leer = oberste Ebene
    notes: str = ""
    dims: str = ""  # z. B. 400x300x170


class ContainerPatch(BaseModel):
    name: str | None = None
    notes: str | None = None
    parent: str | None = None  # umlagern; "" = nach oben


class ProjectLine(BaseModel):
    item: str = ""  # Teil (Code/ID) – oder freier Name
    name: str = ""
    qty: int | None = None


class ProjectNew(BaseModel):
    name: str
    notes: str = ""
    lines: list[ProjectLine] = []


class PurchaseNew(BaseModel):
    supplier: str = ""
    qty: int | None = None
    price: float | None = None
    bought_at: str = ""
    url: str = ""
    note: str = ""


class CardNew(BaseModel):
    title: str
    body: str = ""
    kind: str = "note"  # note | pinout


class Count(BaseModel):
    qty: int | None = None  # gezählte Menge (leer = nur bestätigen)


def register(
    router: APIRouter,
    Conn: Any,
    Write: Any,
    find_node: FindFn,
    find_item: FindFn,
    item_json: JsonFn,
    node_json: JsonFn,
) -> JsonFn:
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

    # --- Überblick für Planung -------------------------------------------------------

    @router.get("/overview")
    def overview(conn: Conn) -> dict[str, Any]:
        amount, unpriced = value.total(conn)
        one = conn.execute
        return {
            "version": __version__,
            "items": one("SELECT COUNT(*) FROM item WHERE archived = 0").fetchone()[0],
            "containers": one("SELECT COUNT(*) FROM container").fetchone()[0],
            "value_eur": round(amount, 2),
            "items_without_price": unpriced,
            "to_buy": len(repo.shopping_list(conn)),
            "unsorted": len(repo.items_in(conn, repo.inbox(conn))),
            "inventory_due": len(inventory.due(conn, prefs.number(conn, "inventory_days"))),
            "open_projects": one("SELECT COUNT(*) FROM project WHERE done = 0").fetchone()[0],
            "last_backup": codes.get_setting(conn, "backup_last", ""),
            "extern_backup": scheduler.extern_target(conn) != "",
        }

    @router.get("/tree")
    def tree(conn: Conn, depth: int = 4) -> list[dict[str, Any]]:
        """Behälterbaum (ohne Teile) mit Teilezahl je Behälter."""
        depth = max(1, min(depth, 10))

        def walk(node: Row, d: int) -> dict[str, Any]:
            n = conn.execute(
                "SELECT COUNT(*) FROM item WHERE container_id = ? AND archived = 0", (node["id"],)
            ).fetchone()[0]
            return {
                **node_json(conn, node), "items": n,
                "children": [walk(c, d + 1) for c in repo.children(conn, node["id"])]
                if d < depth else [],
            }  # fmt: skip

        return [walk(c, 1) for c in repo.children(conn, None)]

    @router.get("/types/catalog")
    def catalog_types(conn: Conn) -> list[dict[str, Any]]:
        """Alle Typen (Katalog + eigene) mit Feldern und Auswahlwerten, plus Anzahl Teile."""
        n = sortiment.counts(conn)
        return [
            {"key": t.key, "label": t.label, "group": g, "category": t.cat,
             "items": n.get(t.key, 0),
             "fields": [{"key": f.key, "label": f.label, "unit": f.unit, "options": list(f.options)}
                        for f in t.fields]}
            for g, ts in catalog.grouped(conn) for t in ts
        ]  # fmt: skip

    @router.get("/types/catalog/{key}/items")
    def type_items(conn: Conn, key: str) -> list[dict[str, Any]]:
        """Teile eines Typs (auch mat:fil, mat:cbl …) mit Feldwerten, natürlich sortiert."""
        try:
            k = sortiment.kind(conn, key)
        except LagerError as exc:
            raise HTTPException(404, str(exc)) from None
        return [
            {"code": r["code"], "name": r["name"], "qty": r["qty"], "unit": r["unit"],
             "path": r["path"], "fields": r["values"]}
            for r in sortiment.items(conn, k)
        ]  # fmt: skip

    @router.get("/items")
    def list_items(
        conn: Conn, container: str = "", limit: int = 200, offset: int = 0, low: bool = False
    ) -> dict[str, Any]:
        """Alle Teile seitenweise, optional nur in einem Behälter (samt Unterbehältern) / knapp."""
        limit = max(1, min(limit, 500))
        where, args = "i.archived = 0", []
        if container:
            node = find_node(conn, container)
            ids = [node["id"]]
            for cid in ids:
                ids += [c["id"] for c in repo.children(conn, cid)]
            where += f" AND i.container_id IN ({','.join('?' * len(ids))})"
            args += ids
        if low:
            where += (
                " AND i.qty IS NOT NULL AND i.qty < COALESCE(i.min_qty, (SELECT ts.min_qty"
                " FROM type_setting ts WHERE ts.key = COALESCE(i.ctype, 'mat:' || i.material)))"
            )
        total = conn.execute(f"SELECT COUNT(*) FROM item i WHERE {where}", args).fetchone()[0]
        rows = conn.execute(
            f"SELECT i.* FROM item i WHERE {where} ORDER BY i.id LIMIT ? OFFSET ?",
            (*args, limit, max(0, offset)),
        ).fetchall()
        return {"total": total, "offset": offset, "items": [item_detail(conn, r) for r in rows]}

    # --- Bearbeiten --------------------------------------------------------------------

    @router.patch("/items/{ref}", dependencies=[Write])
    def patch_item(conn: Conn, ref: str, body: ItemPatch) -> dict[str, Any]:
        item = find_item(conn, ref)
        data = body.model_dump(exclude_none=True)
        qty, delta = data.pop("qty", None), data.pop("qty_delta", None)
        ctype, fields, rename = (
            data.pop("ctype", None),
            data.pop("fields", None),
            data.pop("rename"),
        )
        for flag in ("on_list", "archived"):
            if flag in data:
                data[flag] = int(data[flag])
        try:
            if data:
                repo.update_item(conn, item["id"], **data)
            if ctype == "":
                with conn:
                    conn.execute("UPDATE item SET ctype = NULL WHERE id = ?", (item["id"],))
            elif ctype or fields is not None:
                key = ctype or item["ctype"]
                if not key:
                    raise LagerError("Teil hat keinen Typ – ctype angeben")
                current = catalog.values_of(item) if key == item["ctype"] else {}
                catalog.set_fields(conn, item["id"], key, {**current, **(fields or {})}, rename)
            if qty is not None or delta is not None:
                if item["qty"] is None and qty is None:
                    raise LagerError("Teil ist ungezählt – bitte qty setzen")
                change = (qty - (item["qty"] or 0)) if qty is not None else delta
                if item["qty"] is None:
                    repo.update_item(conn, item["id"], qty=qty)
                elif change:
                    repo.change_qty(conn, item["id"], change, note="API")
        except LagerError as exc:
            raise bad(exc) from None
        return item_detail(conn, repo.get_item(conn, item["id"]))

    @router.delete("/items/{ref}", dependencies=[Write])
    def delete_item(conn: Conn, ref: str, hard: bool = False) -> dict[str, str]:
        """Archiviert das Teil (rückholbar); `hard=true` löscht endgültig."""
        item = find_item(conn, ref)
        if hard:
            repo.delete_item(conn, item["id"])
            return {"result": f"„{item['name']}“ gelöscht"}
        repo.update_item(conn, item["id"], archived=1)
        return {"result": f"„{item['name']}“ archiviert"}

    @router.post("/containers", dependencies=[Write])
    def create_container(conn: Conn, body: ContainerNew) -> dict[str, Any]:
        parent = find_node(conn, body.parent)["id"] if body.parent else None
        try:
            cid = repo.create_container(
                conn, body.name.strip(), body.kind, parent_id=parent, notes=body.notes,
                dims=body.dims,
            )  # fmt: skip
        except LagerError as exc:
            raise bad(exc) from None
        prefix = codes.KIND_PREFIX.get(kinds.resolve(body.kind) or body.kind)
        if prefix:
            repo.assign_code(conn, cid, codes.reserve(conn, prefix, 1)[0])
        node = repo.get_container(conn, cid)
        assert node is not None
        return node_json(conn, node)

    @router.patch("/containers/{ref}", dependencies=[Write])
    def patch_container(conn: Conn, ref: str, body: ContainerPatch) -> dict[str, Any]:
        node = find_node(conn, ref)
        try:
            if body.name is not None or body.notes is not None:
                repo.update_container(
                    conn, node["id"],
                    body.name if body.name is not None else node["name"],
                    body.notes if body.notes is not None else node["notes"],
                )  # fmt: skip
            if body.parent is not None:
                parent = find_node(conn, body.parent)["id"] if body.parent else None
                repo.move_container(conn, node["id"], parent)
        except LagerError as exc:
            raise bad(exc) from None
        fresh = repo.get_container(conn, node["id"])
        assert fresh is not None
        return node_json(conn, fresh)

    # --- Projekte / Stückliste -----------------------------------------------------------

    def project_json(conn: sqlite3.Connection, pid: int) -> dict[str, Any]:
        p = projects.get(conn, pid)
        bom = projects.compare(conn, pid)
        return {
            "id": p["id"], "name": p["name"], "notes": p["notes"], "done": bool(p["done"]),
            "complete": bom["complete"], "counts": bom["counts"],
            "missing_cost_eur": round(bom["cost"], 2),
            "lines": [
                {"id": r["id"], "item": r["code"], "name": r["name"], "qty": r["qty"],
                 "stock": r["stock"], "status": r["status"], "short": r["short"],
                 "path": r["path"], "gathered": bool(r["gathered"])}
                for r in bom["lines"]
            ],
        }  # fmt: skip

    def add_lines(conn: sqlite3.Connection, pid: int, lines: list[ProjectLine]) -> None:
        for line in lines:
            item_id = find_item(conn, line.item)["id"] if line.item else None
            try:
                projects.add_line(conn, pid, item_id, line.name, line.qty)
            except LagerError as exc:
                raise bad(exc) from None

    @router.get("/projects")
    def list_projects(conn: Conn) -> list[dict[str, Any]]:
        return [
            {"id": p["id"], "name": p["name"], "done": bool(p["done"]), "lines": p["total"]}
            for p in projects.all_projects(conn)
        ]

    @router.get("/projects/{pid}")
    def get_project(conn: Conn, pid: int) -> dict[str, Any]:
        try:
            return project_json(conn, pid)
        except LagerError as exc:
            raise HTTPException(404, str(exc)) from None

    @router.post("/projects", dependencies=[Write])
    def create_project(conn: Conn, body: ProjectNew) -> dict[str, Any]:
        try:
            pid = projects.create(conn, body.name, body.notes)
        except LagerError as exc:
            raise bad(exc) from None
        add_lines(conn, pid, body.lines)
        return project_json(conn, pid)

    @router.post("/projects/{pid}/lines", dependencies=[Write])
    def project_lines(conn: Conn, pid: int, lines: list[ProjectLine]) -> dict[str, Any]:
        try:
            projects.get(conn, pid)
        except LagerError as exc:
            raise HTTPException(404, str(exc)) from None
        add_lines(conn, pid, lines)
        return project_json(conn, pid)

    @router.post("/projects/{pid}/shopping", dependencies=[Write])
    def project_shopping(conn: Conn, pid: int) -> dict[str, Any]:
        """Fehlmengen bekannter Teile auf die Einkaufsliste setzen."""
        try:
            n = projects.to_shopping(conn, pid)
        except LagerError as exc:
            raise HTTPException(404, str(exc)) from None
        return {"on_shopping_list": n, "project": project_json(conn, pid)}

    # --- Einkäufe, Lieferanten, Karten ----------------------------------------------------------

    @router.get("/suppliers")
    def suppliers(conn: Conn) -> list[dict[str, Any]]:
        return purchases.suppliers(conn)

    @router.post("/items/{ref}/purchases", dependencies=[Write])
    def add_purchase(conn: Conn, ref: str, body: PurchaseNew) -> dict[str, Any]:
        item = find_item(conn, ref)
        try:
            purchases.add(conn, item["id"], **body.model_dump())
        except LagerError as exc:
            raise bad(exc) from None
        return item_detail(conn, repo.get_item(conn, item["id"]))

    @router.post("/items/{ref}/cards", dependencies=[Write])
    def add_item_card(conn: Conn, ref: str, body: CardNew) -> dict[str, Any]:
        item = find_item(conn, ref)
        try:
            cards.add(conn, body.title, body.body, body.kind, item_id=item["id"])
        except LagerError as exc:
            raise bad(exc) from None
        return item_detail(conn, repo.get_item(conn, item["id"]))

    @router.post("/containers/{ref}/cards", dependencies=[Write])
    def add_node_card(conn: Conn, ref: str, body: CardNew) -> dict[str, Any]:
        node = find_node(conn, ref)
        try:
            cards.add(conn, body.title, body.body, body.kind, container_id=node["id"])
        except LagerError as exc:
            raise bad(exc) from None
        return {
            **node_json(conn, node),
            "cards": [{"kind": c["kind"], "title": c["title"], "body": c["body"]}
                      for c in cards.for_container(conn, node["id"])],
        }  # fmt: skip

    # --- Inventur ------------------------------------------------------------------------------

    @router.get("/inventory/due")
    def inventory_due(conn: Conn) -> list[dict[str, Any]]:
        days = prefs.number(conn, "inventory_days")
        return [
            {"id": r["id"], "code": r["code"], "name": r["name"], "path": r["path"],
             "items": r["n"], "last_checked": r["checked_at"]}
            for r in inventory.due(conn, days)
        ]  # fmt: skip

    @router.post("/inventory/items/{ref}", dependencies=[Write])
    def inventory_confirm(conn: Conn, ref: str, body: Count | None = None) -> dict[str, Any]:
        item = find_item(conn, ref)
        try:
            msg = inventory.confirm_item(conn, item["id"], body.qty if body else None)
        except LagerError as exc:
            raise bad(exc) from None
        return {"result": msg, "item": item_json(conn, repo.get_item(conn, item["id"]))}

    @router.post("/inventory/containers/{ref}/done", dependencies=[Write])
    def inventory_done(conn: Conn, ref: str) -> dict[str, int]:
        node = find_node(conn, ref)
        return {"unconfirmed": inventory.finish(conn, node["id"])}

    return item_detail
