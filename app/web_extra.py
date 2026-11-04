"""Routen: Platz-Vorschlag, Einstellungen je Typ, Zählen per Waage, Ablauf-Erinnerung."""

from collections.abc import Callable
from typing import Annotated, Any

from fastapi import FastAPI, Form, Request
from fastapi.responses import HTMLResponse, JSONResponse, RedirectResponse

from app import cfs, expiry, labels, materials, placement, repo, sortiment, typesettings, weighing
from app.config import Settings
from app.repo import LagerError


def _int(raw: str) -> int | None:
    raw = raw.strip()
    if not raw:
        return None
    if not raw.isdigit():
        raise LagerError(f"„{raw}“ ist keine ganze Zahl")
    return int(raw)


def register(
    app: FastAPI,
    Conn: Any,
    render: Callable[..., HTMLResponse],
    redirect: Callable[..., RedirectResponse],
    settings: Settings,
) -> None:
    @app.get("/items/{item_id}/cfs", response_class=HTMLResponse)
    def cfs_page(request: Request, item_id: int, conn: Conn) -> HTMLResponse:
        """CFS-NFC-Platte: Werte für SpoolID, 3D-Modell, Ablauf."""
        item = repo.get_item(conn, item_id)
        s = cfs.spec(item)
        return render(
            request, conn, "cfs.html", item=item, s=s, text=cfs.handoff_text(s),
            stl=cfs.MODEL_STL, step=cfs.MODEL_STEP, play_url=cfs.PLAY_URL,
        )  # fmt: skip

    @app.get("/items/{item_id}/cfs.json")
    def cfs_json(item_id: int, conn: Conn) -> JSONResponse:
        return JSONResponse(cfs.for_item(conn, item_id))

    @app.get("/neu/platz")
    def place_suggestions(
        request: Request, conn: Conn, typ: str = "", cat: str = ""
    ) -> JSONResponse:
        """Wohin damit? Behälter mit ähnlichen Teilen, sonst leere Boxen."""
        values = {k[2:]: v for k, v in request.query_params.items() if k.startswith("f_") and v}
        material = materials.PREFIX_MATERIAL.get(cat.upper(), "") if not typ else ""
        return JSONResponse(placement.suggest(conn, typ, values, material))

    @app.post("/sortiment/{key}/einstellungen")
    def type_settings(
        key: str,
        conn: Conn,
        min_qty: Annotated[str, Form()] = "",
        shelf_months: Annotated[str, Form()] = "",
        label_main: Annotated[str, Form()] = "",
        label_extra: Annotated[str, Form()] = "",
    ) -> RedirectResponse:
        sortiment.kind(conn, key)  # existiert?
        typesettings.save(conn, key, _int(min_qty), _int(shelf_months), label_main, label_extra)
        return redirect(f"/sortiment/{key}#einstellungen", "Einstellungen für den Typ gespeichert")

    @app.post("/labels/sammel/{node_id}")
    def collect_labels(node_id: int, conn: Conn) -> RedirectResponse:
        """Sammeldruck: alle ungedruckten Etiketten der Box (inkl. Unterbehälter) vormerken."""
        node = repo.get_container(conn, node_id)
        if node is None:
            raise LagerError("Behälter nicht gefunden")
        rows = labels.unprinted_in(conn, settings.base_url, node_id)
        for r in rows:
            labels.enqueue(conn, r.code, r.text, r.extra)
        if not rows:
            return redirect(f"/n/{node_id}", "Alle Etiketten dieser Box sind schon gedruckt")
        msg = f"{len(rows)} ungedruckte Etiketten aus „{node['name']}“ vorgemerkt"
        return redirect("/labels", msg)

    # --- Zählen per Waage -------------------------------------------------------------------

    @app.post("/items/{item_id}/stueckgewicht")
    def unit_weight(
        item_id: int,
        conn: Conn,
        count: Annotated[str, Form()] = "",
        grams: Annotated[str, Form()] = "",
        tare: Annotated[str, Form()] = "",
    ) -> RedirectResponse:
        return redirect(
            f"/items/{item_id}#waage", weighing.calibrate(conn, item_id, count, grams, tare)
        )

    @app.post("/items/{item_id}/zaehlen")
    def count_by_weight(
        item_id: int, conn: Conn, gross: Annotated[str, Form()]
    ) -> RedirectResponse:
        return redirect(f"/items/{item_id}#waage", weighing.count(conn, item_id, gross))

    # --- Ablauf ---------------------------------------------------------------------------

    @app.get("/ablauf", response_class=HTMLResponse)
    def expiry_page(request: Request, conn: Conn) -> HTMLResponse:
        return render(request, conn, "ablauf.html", **expiry.due(conn))

    def back_to(raw: str, item_id: int) -> str:
        return raw if raw.startswith("/") and not raw.startswith("//") else f"/items/{item_id}"

    @app.post("/items/{item_id}/geoeffnet")
    def opened(item_id: int, conn: Conn, back: Annotated[str, Form()] = "") -> RedirectResponse:
        return redirect(back_to(back, item_id), expiry.opened_now(conn, item_id))

    @app.post("/items/{item_id}/verlaengern")
    def extend(
        item_id: int,
        conn: Conn,
        months: Annotated[int, Form()] = 1,
        back: Annotated[str, Form()] = "",
    ) -> RedirectResponse:
        return redirect(back_to(back, item_id), expiry.extend(conn, item_id, months))

    @app.post("/items/{item_id}/verbraucht")
    def used_up(item_id: int, conn: Conn, back: Annotated[str, Form()] = "") -> RedirectResponse:
        return redirect(back_to(back or "/ablauf", item_id), expiry.used_up(conn, item_id))
