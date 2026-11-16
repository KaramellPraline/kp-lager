"""REST-API › Bestand: Suche, Teile und Behälter lesen/anlegen/ändern, Entnehmen,
Umlagern, Massenaktionen, Typen, Baum, Überblick und Notiz-/Pinout-Karten."""

from typing import Any

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from app import (
    __version__,
    bulk,
    cards,
    catalog,
    codes,
    creation,
    inventory,
    itemtypes,
    kinds,
    prefs,
    quick,
    repo,
    scheduler,
    search,
    sortiment,
    value,
    withdrawals,
)
from app.api.common import Conn, Write, bad, find_item, find_node, item_detail, item_json, node_json
from app.repo import LagerError, Row


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


class Take(BaseModel):
    qty: int = 1


class Move(BaseModel):
    container: str


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


class CardNew(BaseModel):
    title: str
    body: str = ""
    kind: str = "note"  # note | pinout


def register(router: APIRouter) -> None:
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
        out: dict[str, Any] = item_detail(conn, find_item(conn, ref))
        return out

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
            {"key": t.key, "label": t.label, "group": g, "area": catalog.area_of(t),
             "category": t.cat,
             "items": n.get(t.key, 0),
             "fields": [{"key": f.key, "label": f.label, "unit": f.unit, "options": list(f.options)}
                        for f in t.fields]}
            for g, ts in catalog.grouped(conn) if g != catalog.FAVORITES for t in ts
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
