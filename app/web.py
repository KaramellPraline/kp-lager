"""HTTP-Oberfläche: Seiten für Behälter (/n/{id}), QR-Einstieg (/c/{code}), Items und Umlagern."""

import sqlite3
from collections.abc import Iterator
from pathlib import Path
from typing import Annotated, Any
from urllib.parse import quote

import httpx
from fastapi import Depends, FastAPI, Form, HTTPException, Request, UploadFile
from fastapi.responses import HTMLResponse, JSONResponse, RedirectResponse, Response
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates

from app import backup, codes, importer, kasten, labels, photos, prefs, prompt, quick, repo
from app.config import Settings
from app.db import connect
from app.repo import LagerError

APP_DIR = Path(__file__).parent
APP_NAME = "KP Lager"
CARRY_COOKIE = "carry"
KIND_LABELS = {
    "raum": "Raum", "regal": "Regal", "ebene": "Ebene", "stapel": "Stapel/Kistenberg",
    "eurobox": "Eurobox", "kiste": "Kiste", "sortierkasten": "Sortierkasten",
    "einsatz": "Einsatz", "fach": "Fach", "sonstiges": "Sonstiges",
}  # fmt: skip

templates = Jinja2Templates(directory=APP_DIR / "templates")
templates.env.globals["KIND_LABELS"] = KIND_LABELS
templates.env.globals["APP_NAME"] = APP_NAME
templates.env.globals["KIND_PREFIX"] = codes.KIND_PREFIX
templates.env.globals["MODELS"] = kasten.MODELS


def opt_int(value: str | None) -> int | None:
    value = (value or "").strip()
    if not value:
        return None
    try:
        return int(value)
    except ValueError:
        raise LagerError(f"'{value}' ist keine ganze Zahl") from None


def redirect(url: str, msg: str = "", undo: int | None = None) -> RedirectResponse:
    url, hash_, anchor = url.partition("#")  # Query muss vor den Anker
    if msg:
        url += ("&" if "?" in url else "?") + "msg=" + quote(msg)
    if undo:
        url += ("&" if "?" in url else "?") + f"undo={undo}"
    return RedirectResponse(url + hash_ + anchor, status_code=303)


RECENT_COOKIE = "recent"
TARGET_COOKIE = "qa_targets"  # zuletzt gewählte Ziele der Schnelleingabe (neueste zuerst)


def recent_targets(request: Request) -> list[int]:
    return [int(x) for x in request.cookies.get(TARGET_COOKIE, "").split(",") if x.isdigit()]


def last_target(request: Request) -> int | None:
    ids = recent_targets(request) or recent_ids(request)
    return ids[0] if ids else None


def recent_ids(request: Request) -> list[int]:
    return [int(x) for x in request.cookies.get(RECENT_COOKIE, "").split(",") if x.isdigit()]


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
        undo = request.query_params.get("undo", "")
        ctx["undo"] = int(undo) if undo.isdigit() else None
        ctx["APP_NAME"] = prefs.raw(conn, "app_name")
        ctx["THEME"] = prefs.raw(conn, "theme")
        ctx["COMPACT"] = prefs.flag(conn, "compact")
        ctx["NQUEUE"] = labels.queue_count(conn)
        ctx["P"] = prefs.values(conn)
        return templates.TemplateResponse(request, name, ctx)

    def entries(conn: sqlite3.Connection, text: str) -> list[tuple[int | None, str, str]]:
        """Eingabe -> (Menge, Einheit, Name) je Teil, gemäß Einstellungen."""
        if not prefs.flag(conn, "quick_parse"):
            return [(None, "", text.strip())]
        unit = prefs.raw(conn, "default_unit")
        return [(a, u or (unit if a is not None else ""), n) for a, u, n in quick.parse_many(text)]

    def synonyms(conn: sqlite3.Connection) -> dict[str, list[str]]:
        return repo.parse_synonyms(prefs.raw(conn, "synonyms"))

    def need_node(conn: sqlite3.Connection, node_id: int) -> repo.Row:
        node = repo.get_container(conn, node_id)
        if node is None:
            raise HTTPException(404, "Behälter nicht gefunden")
        return node

    # --- Seiten --------------------------------------------------------------

    @app.middleware("http")
    async def force_https(request: Request, call_next: Any) -> Response:
        """HTTP-Instanz (Port 80): nur /ca.crt und /health ausliefern, sonst auf HTTPS."""
        if settings.https_redirect and request.url.path not in ("/ca.crt", "/health"):
            target = request.url.replace(scheme="https", port=None)
            return RedirectResponse(str(target), status_code=308)
        resp: Response = await call_next(request)
        return resp

    @app.get("/health")
    def health() -> dict[str, str]:
        return {"status": "ok"}

    @app.get("/ca.crt")
    def ca_cert() -> Response:
        """Root-Zertifikat zum Installieren auf dem Handy (für HTTPS ohne Warnung)."""
        if not settings.ca_cert.exists():
            raise HTTPException(404, "Kein Zertifikat – tools/devcert.py ausführen")
        return Response(
            settings.ca_cert.read_bytes(),
            media_type="application/x-x509-ca-cert",
            headers={"Content-Disposition": 'attachment; filename="kp-lager-ca.crt"'},
        )

    @app.get("/", response_class=HTMLResponse)
    def index(request: Request, conn: Conn) -> HTMLResponse:
        return render(
            request,
            conn,
            "index.html",
            roots=repo.children(conn, None),
            favorites=repo.favorites(conn),
            recent=repo.containers_by_ids(conn, recent_ids(request))[
                : prefs.number(conn, "home_recent")
            ],
            n_lent=len(repo.lent_items(conn)),
            n_shopping=len(repo.shopping_list(conn)),
            n_queue=labels.queue_count(conn),
            targets=repo.all_paths(conn),
            target=last_target(request),
            fav_targets=repo.favorites(conn)[:10],
            recent_targets=repo.containers_by_ids(conn, recent_targets(request))[:3],
            voice=bool(settings.whisper_url),
        )

    @app.post("/quickadd")
    def home_quick_add(
        request: Request,
        conn: Conn,
        target: Annotated[int, Form()],
        text: Annotated[str, Form()],
    ) -> RedirectResponse:
        """Schnell eintragen von der Startseite (getippt oder diktiert), Ziel wird gemerkt."""
        dest = need_node(conn, target)
        if not text.strip():
            raise LagerError("Was soll eingetragen werden?")
        names = []
        for amount, unit, name in entries(conn, text):
            repo.add_item(conn, dest["id"], name, qty=amount, unit=unit,
                          code=codes.new_item_code(conn))  # fmt: skip
            names.append(name)
        undo = repo.last_event_id(conn)
        b = kasten.bin_of(conn, dest["id"])
        if b is not None and b["code"] and prefs.flag(conn, "queue_on_quickadd"):
            labels.enqueue(conn, b["code"], *labels.container_label(conn, b))
        msg = f"{', '.join(f'„{n}“' for n in names)} → {repo.path_label(conn, dest['id'])}"
        resp = redirect("/", msg, undo)
        ids = [dest["id"]] + [i for i in recent_targets(request) if i != dest["id"]]
        resp.set_cookie(
            TARGET_COOKIE, ",".join(map(str, ids[:3])), max_age=31_536_000, samesite="lax"
        )
        return resp

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
        path = repo.container_path(conn, node_id)[:-1]
        parent_code = next((p["code"] for p in reversed(path) if p["code"]), None)
        resp = render(
            request,
            conn,
            "node.html",
            node=node,
            path=path,
            kids=repo.children(conn, node_id),
            items=repo.items_in(conn, node_id),
            cols=cols,
            chat_prompt=prompt.for_container(
                node["code"] or "(Code)", node["kind"], node["name"], parent_code, node["grid"]
            ),
            voice=bool(settings.whisper_url),
            topview=kasten.topview(conn, node),
            targets=kasten.quick_targets(conn, node) if node["model"] else [],
            free=kasten.free_cells(conn, node),
            place=request.query_params.get("place", ""),
            sizes=kasten.SIZES,
            divs=kasten.DIVS,
            cad=kasten.cad_command(node) if node["kind"] == "einsatz" else "",
        )
        recent = [node_id] + [i for i in recent_ids(request) if i != node_id]
        resp.set_cookie(
            RECENT_COOKIE, ",".join(map(str, recent[:20])), max_age=31_536_000, samesite="lax"
        )
        return resp

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
        items = repo.search_synonyms(conn, q, synonyms(conn))
        corrected = None
        typo = prefs.flag(conn, "typo_correction")
        if q and not items and typo and (fixed := repo.suggest(conn, q)):
            items, corrected = repo.search_synonyms(conn, fixed, synonyms(conn)), fixed
        return render(
            request,
            conn,
            "search.html",
            q=q,
            corrected=corrected,
            items=items,
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

    # --- Etiketten: Vorschau (Namen bearbeiten) → XLSX für D30 oder A8-Bogen -------

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
            queue=labels.queue(conn, settings.base_url),
        )

    @app.post("/labels/preview", response_class=HTMLResponse)
    def labels_preview(
        request: Request,
        conn: Conn,
        source: Annotated[str, Form()],
        prefix: Annotated[str, Form()] = "",
        count: Annotated[int, Form()] = 0,
        node_id: Annotated[int, Form()] = 0,
        item_id: Annotated[int, Form()] = 0,
    ) -> HTMLResponse:
        if source == "blank":
            if prefix not in codes.PREFIX_KIND:
                raise LagerError(f"Unbekanntes Präfix {prefix}")
            rows = labels.blank(conn, settings.base_url, prefix, max(1, min(count, 500)))
        elif source == "pending":
            rows = labels.pending(conn, settings.base_url)
        elif source == "container":
            need_node(conn, node_id)
            rows = labels.for_container(conn, settings.base_url, node_id)
        elif source == "item":
            item = repo.get_item(conn, item_id)
            if not item["code"]:
                raise LagerError("Teil hat noch keinen Code")
            rows = [labels.item_label(conn, settings.base_url, item)]
        else:
            raise HTTPException(400, "Unbekannte Quelle")
        if not rows:
            raise LagerError("Keine Etiketten zum Drucken")
        return render(
            request,
            conn,
            "labels_preview.html",
            rows=rows,
            source=source,
            text_max=prefs.number(conn, "label_text_max"),
        )

    @app.post("/labels/export", response_model=None)
    def labels_export(
        request: Request,
        conn: Conn,
        fmt: Annotated[str, Form()],
        code: Annotated[list[str], Form()],
        text: Annotated[list[str], Form()],
        extra: Annotated[list[str], Form()],
        save_names: Annotated[str, Form()] = "",
        source: Annotated[str, Form()] = "",
    ) -> Response:
        if not (len(code) == len(text) == len(extra)):
            raise HTTPException(400, "Tabelle unvollständig")
        rows = labels.finalize(
            conn, settings.base_url, list(zip(code, text, extra, strict=True)), bool(save_names)
        )
        if not rows:
            raise LagerError("Keine gültigen Codes")
        if source == "queue":
            labels.dequeue(conn, [r.code for r in rows])
        if fmt == "a4":
            cells = [(r, labels.qr_svg(r.qr)) for r in rows]
            per = labels.A4_COLS * labels.A4_ROWS
            pages = [cells[i : i + per] for i in range(0, len(cells), per)]
            return templates.TemplateResponse(
                request, "labels_a4.html", {"pages": pages, "rows": rows, "per": per}
            )
        if fmt == "a8":
            cells = [(r, labels.qr_svg(r.qr)) for r in rows]
            pages = [
                cells[i : i + labels.A8_PER_PAGE] for i in range(0, len(cells), labels.A8_PER_PAGE)
            ]
            return templates.TemplateResponse(
                request, "labels_a8.html", {"pages": pages, "rows": rows}
            )
        name = rows[0].code if len(rows) == 1 else f"{rows[0].code}_bis_{rows[-1].code}"
        return Response(
            labels.to_xlsx(rows, prefs.number(conn, "label_text_max")),
            media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
            headers={"Content-Disposition": f'attachment; filename="{name}.xlsx"'},
        )

    # --- Einstellungen ----------------------------------------------------------

    @app.get("/settings", response_class=HTMLResponse)
    def settings_page(request: Request, conn: Conn) -> HTMLResponse:
        return render(
            request,
            conn,
            "settings.html",
            groups=prefs.groups(),
            values=prefs.values(conn),
            next_codes={
                p: codes.format_code(p, codes.next_number(conn, p)) for p in codes.PREFIX_LABELS
            },
            prefixes=codes.PREFIX_LABELS,
            base_url=settings.base_url,
            whisper_url=settings.whisper_url,
            has_ca=settings.ca_cert.exists(),
        )

    @app.post("/settings")
    async def settings_save(request: Request, conn: Conn) -> RedirectResponse:
        form = await request.form()
        prefs.save(conn, {k: str(v) for k, v in form.items()})
        return redirect("/settings", "Einstellungen gespeichert")

    # --- Admin: Code-Zähler je Präfix ----------------------------------------------

    @app.get("/settings/admin", response_class=HTMLResponse)
    def admin_page(request: Request, conn: Conn) -> HTMLResponse:
        counters = [
            {
                "prefix": p,
                "label": label,
                "highest": codes.highest_used(conn, p),
                "next": codes.next_number(conn, p),
                "next_code": codes.format_code(p, codes.next_number(conn, p)),
                "used": codes.used_codes(conn, p),
            }
            for p, label in codes.PREFIX_LABELS.items()
        ]
        return render(request, conn, "settings_admin.html", counters=counters)

    @app.post("/settings/admin/next")
    def admin_set_next(
        conn: Conn, prefix: Annotated[str, Form()], number: Annotated[int, Form()]
    ) -> RedirectResponse:
        try:
            codes.set_next(conn, prefix, number)
        except ValueError as exc:
            raise LagerError(str(exc)) from None
        nxt = codes.format_code(prefix, number)
        return redirect("/settings/admin", f"{prefix}: nächster Code ist jetzt {nxt}")

    @app.post("/settings/admin/reset")
    def admin_reset(conn: Conn, prefix: Annotated[str, Form()]) -> RedirectResponse:
        if prefix not in codes.PREFIX_KIND:
            raise LagerError(f"Unbekanntes Präfix {prefix}")
        nxt = codes.format_code(prefix, codes.reset_counter(conn, prefix))
        return redirect("/settings/admin", f"{prefix} zurückgesetzt – nächster Code {nxt}")

    @app.post("/settings/admin/remove")
    def admin_remove_code(conn: Conn, code: Annotated[str, Form()]) -> RedirectResponse:
        """Code von seinem Behälter/Gegenstand lösen (Objekt bleibt erhalten)."""
        if node := repo.get_container_by_code(conn, code):
            repo.assign_code(conn, node["id"], None)
            name = node["name"]
        elif item := repo.get_item_by_code(conn, code):
            repo.set_item_code(conn, item["id"], None)
            name = item["name"]
        else:
            raise LagerError(f"{code} ist nicht vergeben")
        labels.dequeue(conn, [code])
        return redirect("/settings/admin", f"{code} von „{name}“ entfernt")

    @app.post("/settings/backup")
    def settings_backup(conn: Conn) -> RedirectResponse:
        files = backup.run(settings.data_dir, settings.data_dir / "backups")
        return redirect("/settings", "Backup: " + ", ".join(f.name for f in files))

    @app.get("/mehr", response_class=HTMLResponse)
    def more_page(request: Request, conn: Conn) -> HTMLResponse:
        return render(
            request,
            conn,
            "more.html",
            n_lent=len(repo.lent_items(conn)),
            n_shopping=len(repo.shopping_list(conn)),
        )

    # --- Alltag: Rückgängig, Verlauf, Verliehen, Einkauf, Platz -------------------

    @app.post("/undo/{event_id}")
    def undo(request: Request, event_id: int, conn: Conn) -> RedirectResponse:
        msg = repo.undo(conn, event_id)
        back = request.headers.get("referer", "/").split("?")[0]
        return redirect(back, msg)

    @app.get("/verlauf", response_class=HTMLResponse)
    def history_page(request: Request, conn: Conn) -> HTMLResponse:
        return render(
            request, conn, "history.html", events=repo.recent_events(conn), undoable=repo.UNDOABLE
        )

    @app.get("/verliehen", response_class=HTMLResponse)
    def lent_page(request: Request, conn: Conn) -> HTMLResponse:
        return render(request, conn, "list.html", title="Verliehen / in Benutzung",
                      rows=repo.lent_items(conn), kind="lent")  # fmt: skip

    @app.get("/einkauf", response_class=HTMLResponse)
    def shopping_page(request: Request, conn: Conn) -> HTMLResponse:
        return render(request, conn, "list.html", title="Einkaufsliste",
                      rows=repo.shopping_list(conn), kind="shopping")  # fmt: skip

    @app.get("/platz", response_class=HTMLResponse)
    def free_page(request: Request, conn: Conn) -> HTMLResponse:
        return render(request, conn, "free.html", **repo.free_places(conn))

    @app.post("/items/{item_id}/lend")
    def lend(item_id: int, conn: Conn, to: Annotated[str, Form()] = "") -> RedirectResponse:
        repo.lend_item(conn, item_id, to)
        return redirect(f"/items/{item_id}", "Als verliehen markiert")

    @app.post("/items/{item_id}/return")
    def give_back(item_id: int, conn: Conn) -> RedirectResponse:
        repo.return_item(conn, item_id)
        return redirect(f"/items/{item_id}", "Zurück im Lager")

    @app.post("/items/{item_id}/list")
    def toggle_list(request: Request, item_id: int, conn: Conn) -> RedirectResponse:
        item = repo.get_item(conn, item_id)
        repo.update_item(conn, item_id, on_list=0 if item["on_list"] else 1)
        back = request.headers.get("referer", f"/items/{item_id}").split("?")[0]
        return redirect(
            back, "Von Einkaufsliste genommen" if item["on_list"] else "Auf Einkaufsliste"
        )

    @app.post("/n/{node_id}/favorite")
    def favorite(node_id: int, conn: Conn) -> RedirectResponse:
        node = need_node(conn, node_id)
        repo.set_favorite(conn, node_id, not node["favorite"])
        return redirect(
            f"/n/{node_id}", "Favorit entfernt" if node["favorite"] else "Als Favorit gemerkt"
        )

    # --- Scan-Modus & Sprache (brauchen HTTPS für Kamera/Mikrofon) ---------------

    @app.get("/scan", response_class=HTMLResponse)
    def scan_page(request: Request, conn: Conn) -> HTMLResponse:
        return render(request, conn, "scan.html")

    @app.post("/api/move")
    def api_move(
        conn: Conn, code: Annotated[str, Form()], target: Annotated[str, Form()]
    ) -> JSONResponse:
        """Scan-Modus 'Einräumen': gescanntes Teil/Behälter in den Ziel-Behälter."""
        dest = repo.get_container_by_code(conn, codes.normalize(target) or target)
        if dest is None:
            return JSONResponse({"ok": False, "msg": f"Ziel {target} unbekannt"}, status_code=404)
        norm = codes.normalize(code) or code
        try:
            if item := repo.get_item_by_code(conn, norm):
                repo.move_item(conn, item["id"], dest["id"])
                name = item["name"]
            elif node := repo.get_container_by_code(conn, norm):
                repo.move_container(conn, node["id"], dest["id"])
                name = node["name"]
            else:
                return JSONResponse({"ok": False, "msg": f"{norm} ist noch nicht angelegt"}, 404)
        except LagerError as exc:
            return JSONResponse({"ok": False, "msg": str(exc)}, status_code=400)
        return JSONResponse(
            {"ok": True, "msg": f"„{name}“ → {dest['name']}", "undo": repo.last_event_id(conn)}
        )

    @app.get("/api/code/{code}")
    def api_code(code: str, conn: Conn) -> JSONResponse:
        norm = codes.normalize(code) or code
        if node := repo.get_container_by_code(conn, norm):
            return JSONResponse({"type": "container", "code": norm, "name": node["name"]})
        if item := repo.get_item_by_code(conn, norm):
            return JSONResponse({"type": "item", "code": norm, "name": item["name"]})
        return JSONResponse({"type": "unknown", "code": norm, "name": ""})

    @app.post("/api/transcribe")
    async def transcribe(audio: UploadFile, conn: Conn) -> JSONResponse:
        """Leitet die Sprachaufnahme an den KI-Dienst (OpenAI-kompatibel) weiter."""
        if not settings.whisper_url:
            return JSONResponse({"error": "Kein Sprachdienst konfiguriert"}, status_code=503)
        data = await audio.read()
        try:  # Dienste starten bei Bedarf -> großzügiges Timeout
            async with httpx.AsyncClient(timeout=300) as client:
                resp = await client.post(
                    f"{settings.whisper_url}/v1/audio/transcriptions",
                    headers={"Authorization": f"Bearer {settings.whisper_token}"},
                    files={"file": (audio.filename or "aufnahme.webm", data, audio.content_type)},
                    data={"model": prefs.raw(conn, "voice_model"), "language": "de"},
                )
                resp.raise_for_status()
        except httpx.HTTPError as exc:
            return JSONResponse({"error": f"Whisper nicht erreichbar: {exc}"}, status_code=502)
        return JSONResponse({"text": str(resp.json().get("text", "")).strip()})

    @app.get("/manifest.webmanifest")
    def manifest(conn: Conn) -> JSONResponse:
        return JSONResponse(
            {
                "name": prefs.raw(conn, "app_name"),
                "short_name": prefs.raw(conn, "app_name"),
                "start_url": "/",
                "display": "standalone",
                "background_color": "#ffffff",
                "theme_color": "#2563eb",
                "icons": [
                    {"src": "/static/icon-192.png", "sizes": "192x192", "type": "image/png"},
                    {"src": "/static/icon-512.png", "sizes": "512x512", "type": "image/png"},
                ],
            },
            media_type="application/manifest+json",
        )

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
        model: Annotated[str, Form()] = "",
    ) -> RedirectResponse:
        if not name.strip():
            raise LagerError("Name fehlt")
        model_key = model if kind == "sortierkasten" and model in kasten.MODELS else None
        cid = repo.create_container(
            conn,
            name.strip(),
            kind,
            parent_id=opt_int(parent_id),
            code=container_code(code),
            grid=None if model_key else (grid.strip() or None),
            position=position.strip() or None,
            model=model_key,
        )
        return redirect(f"/n/{cid}")

    # --- Sortierkasten mit Einsätzen (NORB16) ----------------------------------------

    @app.post("/n/{node_id}/bins")
    def place_bin(
        node_id: int,
        conn: Conn,
        position: Annotated[str, Form()],
        size: Annotated[str, Form()] = "1x1",
        div: Annotated[str, Form()] = "1x1",
        queue: Annotated[str, Form()] = "",
    ) -> RedirectResponse:
        bin_id = kasten.place_bin(conn, node_id, position, size, div)
        node = need_node(conn, bin_id)
        if queue:
            labels.enqueue(conn, node["code"], *labels.container_label(conn, node))
        return redirect(f"/n/{node_id}", f"Einsatz {node['code']} ({size}) bei {node['position']}")

    @app.post("/n/{node_id}/fill")
    def fill_bins(node_id: int, conn: Conn) -> RedirectResponse:
        """Alle freien Zellen mit 1x1-Einsätzen belegen (schnelle Ersteinrichtung)."""
        node = need_node(conn, node_id)
        cells = kasten.free_cells(conn, node)
        for cell in cells:
            kasten.place_bin(conn, node_id, cell, "1x1")
        return redirect(f"/n/{node_id}", f"{len(cells)} Einsätze 1x1 angelegt")

    @app.post("/n/{node_id}/quickadd")
    def quick_add(
        node_id: int,
        conn: Conn,
        target: Annotated[int, Form()],
        text: Annotated[str, Form()],
        queue: Annotated[str, Form()] = "",
    ) -> RedirectResponse:
        """Schnelleingabe im Kasten: Teil ins gewählte Fach, Bin-Etikett in die Warteschlange."""
        dest = need_node(conn, target)
        if not text.strip():
            raise LagerError("Was soll rein?")
        names = []
        for amount, unit, name in entries(conn, text):
            repo.add_item(conn, dest["id"], name, qty=amount, unit=unit,
                          code=codes.new_item_code(conn))  # fmt: skip
            names.append(name)
        undo = repo.last_event_id(conn)
        msg = f"{', '.join(f'„{n}“' for n in names)} → {dest['name']}"
        if queue and (b := kasten.bin_of(conn, dest["id"])) is not None and b["code"]:
            labels.enqueue(conn, b["code"], *labels.container_label(conn, b))
            msg += f" · Etikett {b['code']} in Warteschlange"
        return redirect(f"/n/{node_id}#schnell", msg, undo)

    # --- Etiketten-Warteschlange ------------------------------------------------------

    @app.post("/labels/queue/node/{node_id}")
    def queue_node(request: Request, node_id: int, conn: Conn) -> RedirectResponse:
        node = need_node(conn, node_id)
        if not node["code"]:
            raise LagerError("Behälter hat noch keinen Code")
        labels.enqueue(conn, node["code"], *labels.container_label(conn, node))
        back = request.headers.get("referer", f"/n/{node_id}").split("?")[0]
        return redirect(back, f"Etikett {node['code']} in Warteschlange")

    @app.post("/labels/queue/kasten/{node_id}")
    def queue_kasten(request: Request, node_id: int, conn: Conn) -> RedirectResponse:
        """Alle Einsätze eines Kastens in die Warteschlange."""
        n = 0
        for b in kasten.bins(conn, node_id):
            labels.enqueue(conn, b["code"], *labels.container_label(conn, b))
            n += 1
        return redirect(f"/n/{node_id}", f"{n} Einsatz-Etiketten in Warteschlange")

    @app.post("/labels/queue/item/{item_id}")
    def queue_item(request: Request, item_id: int, conn: Conn) -> RedirectResponse:
        item = repo.get_item(conn, item_id)
        if not item["code"]:
            raise LagerError("Teil hat noch keinen Code")
        lab = labels.item_label(conn, settings.base_url, item)
        labels.enqueue(conn, lab.code, lab.text, lab.extra)
        return redirect(f"/items/{item_id}", f"Etikett {lab.code} in Warteschlange")

    @app.get("/labels/queue", response_class=HTMLResponse)
    def queue_page(request: Request, conn: Conn) -> HTMLResponse:
        return render(
            request,
            conn,
            "labels_preview.html",
            rows=labels.queue(conn, settings.base_url),
            source="queue",
            text_max=prefs.number(conn, "label_text_max"),
        )

    @app.post("/labels/queue/remove")
    def queue_remove(conn: Conn, code: str) -> RedirectResponse:
        labels.dequeue(conn, [code])
        return redirect("/labels/queue", f"{code} entfernt")

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
        amount = opt_int(qty)
        if amount is not None:  # Menge ausdrücklich angegeben -> genau ein Teil
            todo: list[tuple[int | None, str, str]] = [
                (amount, unit.strip() or prefs.raw(conn, "default_unit"), name.strip())
            ]
        else:  # "3 Rollen Lötzinn und 50 M3 Muttern" -> mehrere Teile
            todo = [(a, unit.strip() or u, n) for a, u, n in entries(conn, name)]
        for a, u, n in todo:
            repo.add_item(conn, node_id, n, qty=a, unit=u, tags=tags.strip(),
                          code=codes.new_item_code(conn))  # fmt: skip
        names = ", ".join(f"„{n}“" for _, _, n in todo)
        return redirect(f"/n/{node_id}", f"{names} eingelagert", repo.last_event_id(conn))

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
        min_qty: Annotated[str, Form()] = "",
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
            min_qty=opt_int(min_qty),
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
        resp = redirect(f"/n/{node_id}", f"„{c['name']}“ abgelegt", repo.last_event_id(conn))
        resp.delete_cookie(CARRY_COOKIE)
        return resp

    @app.post("/carry/cancel")
    def carry_cancel(request: Request) -> RedirectResponse:
        resp = redirect(request.headers.get("referer", "/").split("?")[0])
        resp.delete_cookie(CARRY_COOKIE)
        return resp

    return app
