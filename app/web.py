"""HTTP-Oberfläche: Seiten für Behälter (/n/{id}), QR-Einstieg (/c/{code}), Items und Umlagern."""

import sqlite3
from collections.abc import Iterator
from pathlib import Path
from typing import Annotated, Any
from urllib.parse import quote

from fastapi import Depends, FastAPI, Form, HTTPException, Request, UploadFile
from fastapi.responses import HTMLResponse, JSONResponse, RedirectResponse, Response
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates

from app import codes, importer, labels, photos, repo
from app.config import Settings
from app.db import connect
from app.repo import LagerError

APP_DIR = Path(__file__).parent
APP_NAME = "KP Lager"
CARRY_COOKIE = "carry"
KIND_LABELS = {
    "raum": "Raum", "regal": "Regal", "ebene": "Ebene", "stapel": "Stapel/Kistenberg",
    "eurobox": "Eurobox", "kiste": "Kiste", "sortierkasten": "Sortierkasten", "fach": "Fach",
    "sonstiges": "Sonstiges",
}  # fmt: skip

templates = Jinja2Templates(directory=APP_DIR / "templates")
templates.env.globals["KIND_LABELS"] = KIND_LABELS
templates.env.globals["APP_NAME"] = APP_NAME
templates.env.globals["KIND_PREFIX"] = codes.KIND_PREFIX


def opt_int(value: str | None) -> int | None:
    value = (value or "").strip()
    if not value:
        return None
    try:
        return int(value)
    except ValueError:
        raise LagerError(f"'{value}' ist keine ganze Zahl") from None


def redirect(url: str, msg: str = "") -> RedirectResponse:
    if msg:
        url += ("&" if "?" in url else "?") + "msg=" + quote(msg)
    return RedirectResponse(url, status_code=303)


def container_code(raw: str) -> str | None:
    """Leer -> None; Schema-Code normalisieren; ART-Codes gehören zu Gegenständen."""
    raw = raw.strip()
    if not raw:
        return None
    norm = codes.normalize(raw)
    if norm is None:
        raise LagerError(f"'{raw}' passt nicht zum Code-Schema (z. B. EUR-001)")
    if norm.startswith(codes.ITEM_PREFIX):
        raise LagerError("ART-Codes sind für Gegenstände, nicht für Behälter")
    return norm


def node_url(container_id: int | None) -> str:
    return f"/n/{container_id}" if container_id else "/"


def create_app(settings: Settings) -> FastAPI:
    app = FastAPI(title=APP_NAME)
    app.mount("/static", StaticFiles(directory=APP_DIR / "static"), name="static")
    connect(settings.db_path).close()  # Migrationen beim Start
    photo_dir = settings.data_dir / "photos"
    photo_dir.mkdir(parents=True, exist_ok=True)
    app.mount("/photos", StaticFiles(directory=photo_dir), name="photos")

    def get_conn() -> Iterator[sqlite3.Connection]:
        conn = connect(settings.db_path)
        try:
            yield conn
        finally:
            conn.close()

    Conn = Annotated[sqlite3.Connection, Depends(get_conn)]

    @app.exception_handler(LagerError)
    def lager_error(request: Request, exc: LagerError) -> RedirectResponse:
        back = request.headers.get("referer", "/").split("?")[0]
        return redirect(back, str(exc))

    @app.exception_handler(sqlite3.IntegrityError)
    def integrity_error(request: Request, exc: sqlite3.IntegrityError) -> RedirectResponse:
        back = request.headers.get("referer", "/").split("?")[0]
        msg = "Code ist schon vergeben" if "code" in str(exc) else "Konflikt mit bestehenden Daten"
        return redirect(back, msg)

    def carry_info(request: Request, conn: sqlite3.Connection) -> dict[str, Any] | None:
        raw = request.cookies.get(CARRY_COOKIE, "")
        kind, _, sid = raw.partition(":")
        if kind not in ("item", "node") or not sid.isdigit():
            return None
        row = (
            conn.execute("SELECT name FROM item WHERE id = ?", (int(sid),)).fetchone()
            if kind == "item"
            else repo.get_container(conn, int(sid))
        )
        return {"kind": kind, "id": int(sid), "name": row["name"]} if row else None

    def render(request: Request, conn: sqlite3.Connection, name: str, **ctx: Any) -> HTMLResponse:
        ctx.setdefault("node", None)
        ctx["carry"] = carry_info(request, conn)
        ctx["msg"] = request.query_params.get("msg", "")
        return templates.TemplateResponse(request, name, ctx)

    def need_node(conn: sqlite3.Connection, node_id: int) -> repo.Row:
        node = repo.get_container(conn, node_id)
        if node is None:
            raise HTTPException(404, "Behälter nicht gefunden")
        return node

    # --- Seiten --------------------------------------------------------------

    @app.get("/health")
    def health() -> dict[str, str]:
        return {"status": "ok"}

    @app.get("/", response_class=HTMLResponse)
    def index(request: Request, conn: Conn) -> HTMLResponse:
        return render(request, conn, "index.html", roots=repo.children(conn, None))

    @app.get("/c/{code}", response_model=None)
    @app.get("/C/{code}", response_model=None)  # QR-Inhalt in Großbuchstaben
    def by_code(request: Request, code: str, conn: Conn) -> Response:
        code = codes.normalize(code) or code.strip()
        msg = request.query_params.get("msg", "")
        if node := repo.get_container_by_code(conn, code):
            return redirect(f"/n/{node['id']}", msg)
        if item := repo.get_item_by_code(conn, code):
            return redirect(f"/items/{item['id']}", msg)
        prefix = codes.prefix_of(code)
        if prefix is None:
            raise HTTPException(404, f"'{code}' passt nicht zum Code-Schema (z. B. EUR-001)")
        template = "new_item_code.html" if prefix == codes.ITEM_PREFIX else "new_code.html"
        return render(
            request,
            conn,
            template,
            code=code,
            default_kind=codes.PREFIX_KIND[prefix],
            paths=repo.all_paths(conn),
        )

    @app.get("/n/{node_id}", response_class=HTMLResponse)
    def node_page(request: Request, node_id: int, conn: Conn) -> HTMLResponse:
        node = need_node(conn, node_id)
        cols = int(node["grid"].split("x")[0]) if node["grid"] else 0
        return render(
            request,
            conn,
            "node.html",
            node=node,
            path=repo.container_path(conn, node_id)[:-1],
            kids=repo.children(conn, node_id),
            items=repo.items_in(conn, node_id),
            cols=cols,
        )

    @app.get("/items/{item_id}", response_class=HTMLResponse)
    def item_page(request: Request, item_id: int, conn: Conn) -> HTMLResponse:
        item = repo.get_item(conn, item_id)
        return render(
            request,
            conn,
            "item.html",
            item=item,
            path=repo.container_path(conn, item["container_id"]),
            events=repo.history(conn, item_id)[:30],
        )

    @app.get("/suche", response_model=None)
    def search(request: Request, conn: Conn, q: str = "") -> Response:
        q = q.strip()
        code = codes.normalize(q) or q
        if q and (node := repo.get_container_by_code(conn, code)):
            return redirect(f"/n/{node['id']}")
        if q and (item := repo.get_item_by_code(conn, code)):
            return redirect(f"/items/{item['id']}")
        return render(
            request,
            conn,
            "search.html",
            q=q,
            items=repo.search(conn, q),
            containers=repo.search_containers(conn, q),
        )

    # --- Import / Export ------------------------------------------------------

    @app.get("/import", response_class=HTMLResponse)
    def import_page(request: Request, conn: Conn) -> HTMLResponse:
        return render(request, conn, "import.html", report=None, text="", done=False)

    @app.post("/import", response_class=HTMLResponse)
    def import_run(
        request: Request,
        conn: Conn,
        text: Annotated[str, Form()] = "",
        action: Annotated[str, Form()] = "preview",
    ) -> HTMLResponse:
        commit = action == "commit"
        report = importer.run(conn, text, commit=commit)
        done = commit and not report.errors
        return render(request, conn, "import.html", report=report, text=text, done=done)

    @app.get("/export.json")
    def export(conn: Conn) -> JSONResponse:
        return JSONResponse(
            importer.export(conn),
            headers={"Content-Disposition": 'attachment; filename="lager-export.json"'},
        )

    # --- Etiketten (D30-XLSX, A4) ---------------------------------------------

    def xlsx_response(rows: list[labels.Label], name: str) -> Response:
        return Response(
            labels.to_xlsx(rows),
            media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
            headers={"Content-Disposition": f'attachment; filename="{name}.xlsx"'},
        )

    @app.get("/labels", response_class=HTMLResponse)
    def labels_page(request: Request, conn: Conn) -> HTMLResponse:
        return render(
            request,
            conn,
            "labels.html",
            prefixes=codes.PREFIX_LABELS,
            next_codes={
                p: codes.format_code(p, codes.next_number(conn, p)) for p in codes.PREFIX_LABELS
            },
            pending=labels.pending(conn, settings.base_url),
        )

    @app.post("/labels/blank.xlsx")
    def labels_blank(
        conn: Conn, prefix: Annotated[str, Form()], count: Annotated[int, Form()]
    ) -> Response:
        if prefix not in codes.PREFIX_KIND:
            raise LagerError(f"Unbekanntes Präfix {prefix}")
        rows = labels.blank(conn, settings.base_url, prefix, max(1, min(count, 500)))
        return xlsx_response(rows, f"{rows[0].code}_bis_{rows[-1].code}")

    @app.post("/labels/pending.xlsx")
    def labels_pending(conn: Conn) -> Response:
        rows = labels.pending(conn, settings.base_url)
        if not rows:
            raise LagerError("Keine ungedruckten Etiketten")
        labels.mark_printed(conn, rows)
        return xlsx_response(rows, "etiketten_neu")

    @app.post("/n/{node_id}/labels.xlsx")
    def labels_container(node_id: int, conn: Conn) -> Response:
        node = need_node(conn, node_id)
        rows = labels.for_container(conn, settings.base_url, node_id)
        if not rows:
            raise LagerError("Keine Gegenstände in diesem Behälter")
        labels.mark_printed(conn, rows)
        return xlsx_response(rows, f"etiketten_{node['code'] or node_id}")

    @app.get("/items/{item_id}/label.xlsx")
    def label_item(item_id: int, conn: Conn) -> Response:
        item = repo.get_item(conn, item_id)
        if not item["code"]:
            raise LagerError("Teil hat noch keinen Code")
        rows = [labels.item_label(conn, settings.base_url, item)]
        labels.mark_printed(conn, rows)
        return xlsx_response(rows, item["code"])

    @app.get("/labels/sheet", response_class=HTMLResponse)
    def label_sheet(
        request: Request,
        conn: Conn,
        prefix: str = "EUR",
        count: int = 40,
        cols: int = labels.Sheet.cols,
        rows: int = labels.Sheet.rows,
        width: float = labels.Sheet.width,
        height: float = labels.Sheet.height,
        top: float = labels.Sheet.top,
        left: float = labels.Sheet.left,
    ) -> HTMLResponse:
        if prefix not in codes.PREFIX_KIND:
            raise HTTPException(404, "Unbekanntes Präfix")
        sheet = labels.Sheet(cols, rows, width, height, top, left)
        start = codes.next_number(conn, prefix)
        count = max(1, min(count, 400))
        cells = [
            (code, labels.qr_svg(labels.qr_content(settings.base_url, code)))
            for code in (codes.format_code(prefix, n) for n in range(start, start + count))
        ]
        pages = [cells[i : i + sheet.per_page] for i in range(0, len(cells), sheet.per_page)]
        return templates.TemplateResponse(
            request,
            "labels_sheet.html",
            {
                "s": sheet,
                "prefix": prefix,
                "count": count,
                "last": start + count - 1,
                "codes": [c for c, _ in cells],
                "pages": pages,
            },
        )

    @app.post("/labels/sheet/printed")
    def sheet_printed(
        conn: Conn, prefix: Annotated[str, Form()], last: Annotated[int, Form()]
    ) -> RedirectResponse:
        codes.mark_used_until(conn, prefix, last)
        return redirect("/labels", f"Gemerkt – nächster Code {codes.format_code(prefix, last + 1)}")

    # --- Einstellungen ----------------------------------------------------------

    @app.get("/settings", response_class=HTMLResponse)
    def settings_page(request: Request, conn: Conn) -> HTMLResponse:
        return render(
            request,
            conn,
            "settings.html",
            auto_item_code=codes.auto_item_code(conn),
            prefixes=codes.PREFIX_LABELS,
        )

    @app.post("/settings")
    def settings_save(conn: Conn, auto_item_code: Annotated[str, Form()] = "") -> RedirectResponse:
        codes.set_setting(conn, "auto_item_code", "1" if auto_item_code else "0")
        return redirect("/settings", "Gespeichert")

    # --- Behälter -------------------------------------------------------------

    @app.post("/containers")
    def create_container(
        conn: Conn,
        name: Annotated[str, Form()],
        kind: Annotated[str, Form()],
        parent_id: Annotated[str, Form()] = "",
        code: Annotated[str, Form()] = "",
        grid: Annotated[str, Form()] = "",
        position: Annotated[str, Form()] = "",
    ) -> RedirectResponse:
        if not name.strip():
            raise LagerError("Name fehlt")
        cid = repo.create_container(
            conn,
            name.strip(),
            kind,
            parent_id=opt_int(parent_id),
            code=container_code(code),
            grid=grid.strip() or None,
            position=position.strip() or None,
        )
        return redirect(f"/n/{cid}")

    @app.post("/n/{node_id}/edit")
    def edit_container(
        node_id: int,
        conn: Conn,
        name: Annotated[str, Form()],
        notes: Annotated[str, Form()] = "",
        code: Annotated[str, Form()] = "",
    ) -> RedirectResponse:
        node = need_node(conn, node_id)
        repo.update_container(conn, node_id, name, notes)
        new_code = container_code(code)
        if new_code != node["code"]:
            repo.assign_code(conn, node_id, new_code)
        return redirect(f"/n/{node_id}", "Gespeichert")

    @app.post("/n/{node_id}/code")
    def container_next_code(node_id: int, conn: Conn) -> RedirectResponse:
        node = need_node(conn, node_id)
        prefix = codes.KIND_PREFIX.get(node["kind"])
        if prefix is None:
            raise LagerError("Für diese Art gibt es kein Präfix – Code von Hand eintragen")
        code = codes.reserve(conn, prefix, 1)[0]
        repo.assign_code(conn, node_id, code)
        return redirect(f"/n/{node_id}", f"Code {code} vergeben")

    @app.post("/n/{node_id}/delete")
    def delete_container(node_id: int, conn: Conn) -> RedirectResponse:
        photo = need_node(conn, node_id)["photo"]
        parent = repo.delete_container(conn, node_id)
        photos.delete(photo, photo_dir)
        return redirect(node_url(parent), "Behälter gelöscht")

    # --- Items ----------------------------------------------------------------

    @app.post("/n/{node_id}/items")
    def add_item(
        node_id: int,
        conn: Conn,
        name: Annotated[str, Form()],
        qty: Annotated[str, Form()] = "",
        unit: Annotated[str, Form()] = "",
        tags: Annotated[str, Form()] = "",
    ) -> RedirectResponse:
        need_node(conn, node_id)
        if not name.strip():
            raise LagerError("Name fehlt")
        repo.add_item(
            conn,
            node_id,
            name,
            qty=opt_int(qty),
            unit=unit.strip(),
            tags=tags.strip(),
            code=codes.new_item_code(conn),
        )
        return redirect(f"/n/{node_id}", f"„{name.strip()}“ eingelagert")

    @app.post("/items/new")
    def add_item_with_code(
        conn: Conn,
        code: Annotated[str, Form()],
        container_id: Annotated[int, Form()],
        name: Annotated[str, Form()],
        qty: Annotated[str, Form()] = "",
    ) -> RedirectResponse:
        norm = codes.normalize(code)
        if norm is None or not norm.startswith(codes.ITEM_PREFIX):
            raise LagerError(f"'{code}' ist kein Gegenstands-Code (ART-0001)")
        if not name.strip():
            raise LagerError("Name fehlt")
        need_node(conn, container_id)
        item_id = repo.add_item(conn, container_id, name, qty=opt_int(qty), code=norm)
        codes.mark_used_until(conn, codes.ITEM_PREFIX, int(norm[4:]))
        return redirect(f"/items/{item_id}", f"„{name.strip()}“ angelegt")

    @app.post("/items/{item_id}/code")
    def item_code(
        item_id: int, conn: Conn, remove: Annotated[str, Form()] = ""
    ) -> RedirectResponse:
        if remove:
            repo.set_item_code(conn, item_id, None)
            return redirect(f"/items/{item_id}", "Code entfernt")
        code = codes.reserve(conn, codes.ITEM_PREFIX, 1)[0]
        repo.set_item_code(conn, item_id, code)
        return redirect(f"/items/{item_id}", f"Code {code} vergeben")

    @app.post("/items/{item_id}/qty", response_class=HTMLResponse)
    def change_qty(
        request: Request, item_id: int, conn: Conn, delta: Annotated[int, Form()]
    ) -> HTMLResponse:
        repo.change_qty(conn, item_id, delta)
        return templates.TemplateResponse(
            request, "_item.html", {"i": repo.get_item(conn, item_id)}
        )

    @app.post("/items/{item_id}/edit")
    def edit_item(
        item_id: int,
        conn: Conn,
        name: Annotated[str, Form()],
        qty: Annotated[str, Form()] = "",
        qty_hint: Annotated[str, Form()] = "",
        unit: Annotated[str, Form()] = "",
        tags: Annotated[str, Form()] = "",
        notes: Annotated[str, Form()] = "",
    ) -> RedirectResponse:
        repo.update_item(
            conn,
            item_id,
            name=name.strip(),
            qty=opt_int(qty),
            qty_hint=qty_hint.strip(),
            unit=unit.strip(),
            tags=tags.strip(),
            notes=notes,
        )
        return redirect(f"/items/{item_id}", "Gespeichert")

    @app.post("/items/{item_id}/delete")
    def delete_item(item_id: int, conn: Conn) -> RedirectResponse:
        item = repo.get_item(conn, item_id)
        repo.delete_item(conn, item_id)
        photos.delete(item["photo"], photo_dir)
        return redirect(f"/n/{item['container_id']}", f"„{item['name']}“ entfernt")

    # --- Fotos -----------------------------------------------------------------

    @app.post("/n/{node_id}/photo")
    async def container_photo(node_id: int, conn: Conn, photo: UploadFile) -> RedirectResponse:
        old = need_node(conn, node_id)["photo"]
        name = photos.save(await photo.read(), photo_dir)
        repo.set_container_photo(conn, node_id, name)
        photos.delete(old, photo_dir)
        return redirect(f"/n/{node_id}", "Foto gespeichert")

    @app.post("/items/{item_id}/photo")
    async def item_photo(item_id: int, conn: Conn, photo: UploadFile) -> RedirectResponse:
        old = repo.get_item(conn, item_id)["photo"]
        name = photos.save(await photo.read(), photo_dir)
        repo.update_item(conn, item_id, photo=name)
        photos.delete(old, photo_dir)
        return redirect(f"/items/{item_id}", "Foto gespeichert")

    # --- Umlagern: aufnehmen (Cookie), am Ziel-Behälter ablegen ------------------

    @app.post("/carry/{kind}/{obj_id}")
    def carry(kind: str, obj_id: int, conn: Conn) -> RedirectResponse:
        if kind == "item":
            back = node_url(repo.get_item(conn, obj_id)["container_id"])
        elif kind == "node":
            back = node_url(need_node(conn, obj_id)["parent_id"])
        else:
            raise HTTPException(404)
        resp = redirect(back, "Aufgenommen – Ziel-Behälter scannen und „Hier ablegen“ tippen")
        resp.set_cookie(CARRY_COOKIE, f"{kind}:{obj_id}", max_age=3600, samesite="lax")
        return resp

    @app.post("/drop/{node_id}")
    def drop(request: Request, node_id: int, conn: Conn) -> RedirectResponse:
        need_node(conn, node_id)
        c = carry_info(request, conn)
        if c is None:
            raise LagerError("Nichts aufgenommen")
        if c["kind"] == "item":
            repo.move_item(conn, c["id"], node_id)
        else:
            repo.move_container(conn, c["id"], node_id)
        resp = redirect(f"/n/{node_id}", f"„{c['name']}“ abgelegt")
        resp.delete_cookie(CARRY_COOKIE)
        return resp

    @app.post("/carry/cancel")
    def carry_cancel(request: Request) -> RedirectResponse:
        resp = redirect(request.headers.get("referer", "/").split("?")[0])
        resp.delete_cookie(CARRY_COOKIE)
        return resp

    return app
