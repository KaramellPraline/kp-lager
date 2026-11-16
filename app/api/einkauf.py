"""REST-API › Einkauf: Einkaufsliste, Lagerwert, Lieferanten, Einkäufe, Rechnungs-Import."""

from typing import Any

from fastapi import APIRouter
from pydantic import BaseModel

from app import invoice, purchases, repo, value
from app.api.common import Conn, Write, bad, find_item, find_node, item_detail, item_json
from app.repo import LagerError


class PurchaseNew(BaseModel):
    supplier: str = ""
    qty: int | None = None
    price: float | None = None
    bought_at: str = ""
    url: str = ""
    note: str = ""


class ImportText(BaseModel):
    text: str  # CSV oder Rechnungstext
    supplier: str = ""


class ImportRow(BaseModel):
    line: dict[str, Any]  # wie aus /purchases/import/preview
    target: str = "skip"  # "item:<id>" | "new" | "skip"


class ImportApply(BaseModel):
    rows: list[ImportRow]
    supplier: str = ""
    bought_at: str = ""
    book: bool = True


def register(router: APIRouter) -> None:
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

    @router.post("/purchases/import/preview")
    def import_preview(conn: Conn, body: ImportText) -> list[dict[str, Any]]:
        """Rechnungstext oder CSV -> erkannte Positionen mit Zuordnungsvorschlag (ändert nichts)."""
        try:
            return invoice.preview(conn, invoice.parse(body.text), body.supplier)
        except LagerError as exc:
            raise bad(exc) from None

    @router.post("/purchases/import", dependencies=[Write])
    def import_apply(conn: Conn, body: ImportApply) -> dict[str, int]:
        """Positionen übernehmen: target je Zeile "item:<id>" | "new" | "skip"."""
        try:
            return invoice.apply(conn, [r.model_dump() for r in body.rows], body.supplier,
                                 body.bought_at, body.book)  # fmt: skip
        except LagerError as exc:
            raise bad(exc) from None

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
