"""Routen für Lieferanten/Einkäufe, Notiz- und Pinout-Karten, Inventur und Stückliste-Abgleich."""

import json
from collections.abc import Callable
from typing import Annotated, Any

from fastapi import FastAPI, File, Form, HTTPException, Request, UploadFile
from fastapi.responses import HTMLResponse, RedirectResponse

from app import cards, codes, inventory, invoice, prefs, projects, purchases, repo
from app.config import Settings
from app.repo import LagerError


def _num(raw: str, kind: type = float) -> Any:
    raw = raw.strip().replace(",", ".")
    if not raw:
        return None
    try:
        return kind(raw)
    except ValueError:
        raise LagerError(f"„{raw}“ ist keine Zahl") from None


def register(
    app: FastAPI,
    Conn: Any,
    render: Callable[..., HTMLResponse],
    redirect: Callable[..., RedirectResponse],
    settings: Settings,
) -> None:
    def back(url: str, default: str) -> str:
        return url if url.startswith("/") and not url.startswith("//") else default

    # --- Einkäufe & Lieferanten -----------------------------------------------------

    @app.post("/items/{item_id}/purchases")
    def purchase_add(
        item_id: int,
        conn: Conn,
        supplier: Annotated[str, Form()] = "",
        qty: Annotated[str, Form()] = "",
        price: Annotated[str, Form()] = "",
        bought_at: Annotated[str, Form()] = "",
        url: Annotated[str, Form()] = "",
        note: Annotated[str, Form()] = "",
    ) -> RedirectResponse:
        purchases.add(
            conn, item_id, supplier, _num(qty, int), _num(price), bought_at.strip(), url, note
        )
        return redirect(f"/items/{item_id}#einkaeufe", "Einkauf erfasst")

    @app.post("/purchases/{purchase_id}/delete")
    def purchase_delete(
        purchase_id: int, conn: Conn, to: Annotated[str, Form()] = "/lieferanten"
    ) -> RedirectResponse:
        purchases.delete(conn, purchase_id)
        return redirect(back(to, "/lieferanten"), "Einkauf gelöscht")

    @app.get("/lieferanten", response_class=HTMLResponse)
    def suppliers_page(request: Request, conn: Conn) -> HTMLResponse:
        return render(request, conn, "suppliers.html", suppliers=purchases.suppliers(conn))

    @app.get("/lieferanten/{sid}", response_class=HTMLResponse)
    def supplier_page(request: Request, sid: int, conn: Conn) -> HTMLResponse:
        sup, rows = purchases.of_supplier(conn, sid)
        total = sum((r["price"] or 0) * (r["qty"] or 1) for r in rows)
        return render(request, conn, "supplier.html", sup=sup, rows=rows, total=total)

    @app.post("/lieferanten/{sid}")
    def supplier_save(
        sid: int,
        conn: Conn,
        url: Annotated[str, Form()] = "",
        note: Annotated[str, Form()] = "",
    ) -> RedirectResponse:
        purchases.update_supplier(conn, sid, url, note)
        return redirect(f"/lieferanten/{sid}", "Gespeichert")

    # --- Karten ---------------------------------------------------------------------

    @app.post("/items/{item_id}/cards")
    def item_card_add(
        item_id: int,
        conn: Conn,
        title: Annotated[str, Form()],
        body: Annotated[str, Form()] = "",
        kind: Annotated[str, Form()] = "note",
    ) -> RedirectResponse:
        repo.get_item(conn, item_id)
        cards.add(conn, title, body, kind, item_id=item_id)
        return redirect(f"/items/{item_id}#karten", "Karte angelegt")

    @app.post("/n/{node_id}/cards")
    def node_card_add(
        node_id: int,
        conn: Conn,
        title: Annotated[str, Form()],
        body: Annotated[str, Form()] = "",
        kind: Annotated[str, Form()] = "note",
    ) -> RedirectResponse:
        if repo.get_container(conn, node_id) is None:
            raise HTTPException(404, "Behälter nicht gefunden")
        cards.add(conn, title, body, kind, container_id=node_id)
        return redirect(f"/n/{node_id}#karten", "Karte angelegt")

    def card_home(card: repo.Row) -> str:
        return (
            f"/items/{card['item_id']}#karten"
            if card["item_id"]
            else f"/n/{card['container_id']}#karten"
        )

    @app.post("/cards/{card_id}/edit")
    def card_edit(
        card_id: int,
        conn: Conn,
        title: Annotated[str, Form()],
        body: Annotated[str, Form()] = "",
    ) -> RedirectResponse:
        card = cards.get(conn, card_id)
        cards.update(conn, card_id, title, body)
        return redirect(card_home(card), "Karte gespeichert")

    @app.post("/cards/{card_id}/delete")
    def card_delete(card_id: int, conn: Conn) -> RedirectResponse:
        card = cards.get(conn, card_id)
        cards.delete(conn, card_id)
        return redirect(card_home(card), "Karte gelöscht")

    # --- Inventur -------------------------------------------------------------------

    @app.get("/inventur", response_class=HTMLResponse)
    def inventory_page(request: Request, conn: Conn) -> HTMLResponse:
        days = prefs.number(conn, "inventory_days")
        return render(request, conn, "inventory.html", rows=inventory.due(conn, days), days=days)

    @app.get("/inventur/{node_id}", response_class=HTMLResponse)
    def inventory_node(request: Request, node_id: int, conn: Conn) -> HTMLResponse:
        node = repo.get_container(conn, node_id)
        if node is None:
            raise HTTPException(404, "Behälter nicht gefunden")
        rows = inventory.items(conn, node_id)
        return render(
            request,
            conn,
            "inventory_node.html",
            node=node,
            path=repo.path_label(conn, node_id),
            rows=rows,
            open_n=sum(1 for r in rows if not r["checked"]),
        )

    @app.post("/inventur/item/{item_id}")
    def inventory_item(
        item_id: int, conn: Conn, qty: Annotated[str, Form()] = ""
    ) -> RedirectResponse:
        item = repo.get_item(conn, item_id)
        msg = inventory.confirm_item(conn, item_id, _num(qty, int))
        return redirect(f"/inventur/{item['container_id']}", msg)

    @app.post("/inventur/{node_id}/scan")
    def inventory_scan(node_id: int, conn: Conn, code: Annotated[str, Form()]) -> RedirectResponse:
        from app import codes

        norm = codes.normalize(code) or code.strip()
        return redirect(f"/inventur/{node_id}", inventory.confirm_by_code(conn, node_id, norm))

    @app.post("/inventur/{node_id}/done")
    def inventory_done(node_id: int, conn: Conn) -> RedirectResponse:
        rest = inventory.finish(conn, node_id)
        extra = f" ({rest} Teile ohne einzelne Bestätigung)" if rest else ""
        return redirect("/inventur", f"Inventur abgeschlossen{extra}")

    # --- Stückliste: Abgleich -----------------------------------------------------------

    @app.post("/projekte/{pid}/reservieren")
    def project_reserve(pid: int, conn: Conn) -> RedirectResponse:
        n = projects.reserve(conn, pid)
        return redirect(f"/projekte/{pid}", f"{n} Positionen reserviert")

    @app.post("/projekte/{pid}/freigeben")
    def project_release(pid: int, conn: Conn) -> RedirectResponse:
        projects.release(conn, pid)
        return redirect(f"/projekte/{pid}", "Reservierung aufgehoben")

    # --- Einkauf aus Rechnung / CSV ------------------------------------------------------

    @app.get("/einkauf/import", response_class=HTMLResponse)
    def purchase_import_page(request: Request, conn: Conn) -> HTMLResponse:
        return render(
            request, conn, "einkauf_import.html", rows=None, suppliers=purchases.names(conn)
        )

    @app.post("/einkauf/import", response_class=HTMLResponse)
    async def purchase_import_preview(
        request: Request,
        conn: Conn,
        text: Annotated[str, Form()] = "",
        supplier: Annotated[str, Form()] = "",
        bought_at: Annotated[str, Form()] = "",
        file: Annotated[UploadFile | None, File()] = None,
    ) -> HTMLResponse:
        data = await file.read() if file is not None and file.filename else b""
        lines = invoice.parse(text, data, (file.filename or "") if file else "")
        return render(
            request, conn, "einkauf_import.html",
            rows=invoice.preview(conn, lines, supplier), supplier=supplier, bought_at=bought_at,
            suppliers=purchases.names(conn),
        )  # fmt: skip

    @app.post("/einkauf/import/uebernehmen")
    async def purchase_import_apply(request: Request, conn: Conn) -> RedirectResponse:
        form = await request.form()
        rows = []
        for key, raw in form.multi_items():
            if not key.startswith("line_") or not isinstance(raw, str):
                continue
            idx = key[5:]
            try:
                line = json.loads(raw)
            except ValueError:
                continue
            target = str(form.get(f"target_{idx}", "skip"))
            code = str(form.get(f"code_{idx}", "")).strip()
            if code:  # Code von Hand: hat Vorrang
                item = repo.get_item_by_code(conn, codes.normalize(code) or code)
                if item is None:
                    raise LagerError(f"Kein Teil mit Code {code}")
                target = f"item:{item['id']}"
            qty_raw = str(form.get(f"qty_{idx}", "")).strip()
            if qty_raw.isdigit():
                line["qty"] = int(qty_raw)
            rows.append({"line": line, "target": target})
        done = invoice.apply(
            conn, rows, str(form.get("supplier", "")), str(form.get("bought_at", "")),
            book=bool(form.get("book")),
        )  # fmt: skip
        msg = (
            f"{done['booked']} Teile eingebucht, {done['created']} neu (Zu sortieren),"
            f" {done['skipped']} übersprungen"
        )
        return redirect("/einkauf", msg)

    @app.post("/projekte/{pid}/einkauf")
    def project_to_shopping(pid: int, conn: Conn) -> RedirectResponse:
        n = projects.to_shopping(conn, pid)
        msg = f"{n} Teile auf der Einkaufsliste" if n else "Nichts nachzukaufen"
        return redirect(f"/projekte/{pid}", msg)
