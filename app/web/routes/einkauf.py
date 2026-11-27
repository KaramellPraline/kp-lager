"""Einkauf: Einkaufsliste, bestellt/eingetroffen, Mindestbestand, Einkäufe je Teil,
Lieferanten und Rechnungs-Import."""

import json
from datetime import date
from typing import Annotated, Any

from fastapi import FastAPI, File, Form, Request, UploadFile
from fastapi.responses import HTMLResponse, RedirectResponse

from app import codes, invoice, purchases, repo
from app.repo import LagerError
from app.web.shared import Conn, Ctx, redirect, safe_back


def _today() -> str:

    return date.today().isoformat()


def _num(raw: str, kind: type = float) -> Any:
    raw = raw.strip().replace(",", ".")
    if not raw:
        return None
    try:
        return kind(raw)
    except ValueError:
        raise LagerError(f"„{raw}“ ist keine Zahl") from None


def register(app: FastAPI, ctx: Ctx) -> None:
    render = ctx.render

    # --- Einkaufsliste ----------------------------------------------------------------------

    @app.get("/einkauf", response_class=HTMLResponse)
    def shopping_page(request: Request, conn: Conn) -> HTMLResponse:
        rows = repo.shopping_list(conn)
        total = sum(float(r["cost"]) for r in rows if r["cost"] is not None)
        return render(request, conn, "list.html", title="Einkaufsliste", rows=rows,
                      kind="shopping", total=total)  # fmt: skip

    @app.post("/items/{item_id}/list")
    def toggle_list(request: Request, item_id: int, conn: Conn) -> RedirectResponse:
        item = repo.get_item(conn, item_id)
        repo.update_item(conn, item_id, on_list=0 if item["on_list"] else 1)
        back = request.headers.get("referer", f"/items/{item_id}").split("?")[0]
        return redirect(
            back, "Von Einkaufsliste genommen" if item["on_list"] else "Auf Einkaufsliste"
        )

    # --- Bestellt / eingetroffen / Mindestbestand -------------------------------------------

    @app.post("/items/{item_id}/bestellt")
    def ordered(
        item_id: int, conn: Conn, back: Annotated[str, Form()] = "/einkauf"
    ) -> RedirectResponse:
        item = repo.get_item(conn, item_id)
        if item["ordered_at"]:
            repo.update_item(conn, item_id, ordered_at=None)
            msg = "Bestellung zurückgenommen"
        else:
            repo.update_item(conn, item_id, ordered_at=_today())
            msg = "Als bestellt markiert"
        return redirect(safe_back(back, "/einkauf"), msg)

    @app.post("/items/{item_id}/eingetroffen")
    def received(
        item_id: int, conn: Conn, back: Annotated[str, Form()] = "/einkauf"
    ) -> RedirectResponse:
        item = repo.get_item(conn, item_id)
        row = next((r for r in repo.shopping_list(conn) if r["id"] == item_id), None)
        need = int(row["need"]) if row else 1
        if item["qty"] is not None:
            repo.change_qty(conn, item_id, need, note="Nachkauf eingetroffen")
        repo.update_item(conn, item_id, ordered_at=None, on_list=0)
        return redirect(
            safe_back(back, "/einkauf"),
            f"Eingelagert: +{need}" if item["qty"] is not None else "Eingetroffen",
        )

    @app.post("/items/{item_id}/mindestbestand")
    def set_min(
        item_id: int, conn: Conn,
        min_qty: Annotated[str, Form()] = "", order_qty: Annotated[str, Form()] = "",
        back: Annotated[str, Form()] = "/einkauf",
    ) -> RedirectResponse:  # fmt: skip
        def num(raw: str) -> int | None:
            raw = raw.strip()
            if raw and not raw.isdigit():
                raise LagerError("Bitte ganze Zahlen eintragen")
            return int(raw) if raw else None

        repo.update_item(conn, item_id, min_qty=num(min_qty), order_qty=num(order_qty))
        return redirect(safe_back(back, "/einkauf"), "Gespeichert")

    def back(url: str, default: str) -> str:
        return url if url.startswith("/") and not url.startswith("//") else default

    # --- Einkäufe und Lieferanten -----------------------------------------------------------

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

    # --- Rechnungs-Import -------------------------------------------------------------------

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
