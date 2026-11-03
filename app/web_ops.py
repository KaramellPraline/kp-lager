"""Routen für Betrieb & Material: Status, Trockner, Slicer, Massenbearbeitung, Foto-Erfassung.

Wird von web.create_app eingehängt und nutzt dessen Abhängigkeiten (Verbindung, Rendern, Redirect).
"""

import sqlite3
import zipfile
from collections.abc import Callable
from typing import Annotated, Any

from fastapi import FastAPI, File, Form, Request, UploadFile
from fastapi.responses import HTMLResponse, JSONResponse, RedirectResponse

from app import (
    backup,
    bulk,
    d30,
    dryer,
    itemtypes,
    kinds,
    prefs,
    repo,
    scheduler,
    search,
    slicer,
    status,
)
from app.config import Settings
from app.repo import LagerError

MAX_PHOTO = 12_000_000


def register(
    app: FastAPI,
    Conn: Any,
    render: Callable[..., HTMLResponse],
    redirect: Callable[..., RedirectResponse],
    settings: Settings,
) -> None:
    def safe_back(url: str, default: str) -> str:
        return url if url.startswith("/") and not url.startswith("//") else default

    # --- Status & Backup ---------------------------------------------------------

    @app.get("/status", response_class=HTMLResponse)
    def status_page(request: Request, conn: Conn) -> HTMLResponse:
        return render(request, conn, "status.html", s=status.collect(conn, settings.data_dir))

    @app.post("/status/backup/extern")
    def status_backup_extern(conn: Conn) -> RedirectResponse:
        files = backup.todays_files(settings.data_dir / "backups")
        if not files:  # noch nichts gesichert: erst lokal sichern
            backup.run(settings.data_dir, settings.data_dir / "backups",
                       prefs.number(conn, "backup_days"))  # fmt: skip
        return redirect("/status", scheduler.extern_tick(settings.data_dir, force=True))

    @app.post("/status/backup")
    def status_backup(conn: Conn) -> RedirectResponse:
        files = backup.run(settings.data_dir, settings.data_dir / "backups",
                           prefs.number(conn, "backup_days"))  # fmt: skip
        return redirect("/status", "Backup erstellt: " + ", ".join(f.name for f in files))

    # --- D30-Direktdruck -----------------------------------------------------------

    @app.get("/d30/status")
    def d30_status() -> JSONResponse:
        if not settings.d30:
            return JSONResponse(
                {"enabled": False, "available": False, "msg": "aus", "bridge": settings.d30_bridge}
            )
        ok, msg = d30.status()
        return JSONResponse({"enabled": True, "available": ok, "msg": msg})

    @app.post("/d30/print")
    def d30_print(
        conn: Conn, code: Annotated[list[str], Form()], back: Annotated[str, Form()] = "/"
    ) -> RedirectResponse:
        if settings.d30_bridge and not settings.d30:
            marker = f"\u27e6d30:{','.join(dict.fromkeys(code))}\u27e7"
            return redirect(safe_back(back, "/"), "Druck über PC-Bridge" + marker)
        if not settings.d30:
            raise LagerError("Direktdruck ist abgeschaltet (LAGER_D30=1)")
        n = d30.print_codes(conn, settings.base_url, code)
        return redirect(safe_back(back, "/"), f"{n} Etikett{'en' if n != 1 else ''} gedruckt")

    @app.post("/d30/printed")
    def d30_printed(conn: Conn, code: Annotated[list[str], Form()]) -> JSONResponse:
        """Die PC-Bridge meldet gedruckte Etiketten: als gedruckt buchen, Warteschlange leeren."""
        from app import codes as code_schema
        from app import labels

        norm = [c for raw in code if (c := code_schema.normalize(raw))]
        with conn:
            conn.executemany(
                "UPDATE container SET label_printed = 1 WHERE code = ?", [(c,) for c in norm]
            )
            conn.executemany(
                "UPDATE item SET label_printed = 1 WHERE code = ?", [(c,) for c in norm]
            )
        labels.dequeue(conn, norm)
        return JSONResponse({"ok": True, "count": len(norm)})

    # --- Trockner: Etikett scannen, dann Filament-Etiketten = getrocknet ---------------

    @app.get("/trockner/scan/{node_id}", response_class=HTMLResponse)
    def dryer_scan(request: Request, node_id: int, conn: Conn) -> HTMLResponse:
        node = repo.get_container(conn, node_id)
        if node is None or node["kind"] != "dryer":
            raise LagerError("Das ist kein Filamenttrockner")
        recent = conn.execute(
            "SELECT d.started_at, i.name, i.code, i.id FROM dry_log d"
            " JOIN item i ON i.id = d.item_id WHERE d.note LIKE ? ORDER BY d.id DESC LIMIT 8",
            (f"Trockner {node['name']} ({node['code'] or '–'})%",),
        ).fetchall()
        return render(request, conn, "trockner_scan.html", dryer_node=node, recent=recent)

    @app.post("/trockner/scan/{node_id}/ende")
    def dryer_scan_end(node_id: int) -> RedirectResponse:
        resp = redirect(f"/n/{node_id}", "Trockner-Modus beendet")
        resp.delete_cookie("dryer_wait")
        return resp

    # --- Trockner ----------------------------------------------------------------

    @app.get("/trockner", response_class=HTMLResponse)
    def dryer_page(request: Request, conn: Conn) -> HTMLResponse:
        spools = conn.execute(
            "SELECT id, name, code FROM item WHERE material = 'fil' AND archived = 0 ORDER BY name"
        ).fetchall()
        return render(
            request, conn, "trockner.html",
            programs=dryer.programs(conn), running=dryer.running(conn),
            history=dryer.history(conn), spools=spools,
        )  # fmt: skip

    @app.post("/trockner/start")
    def dryer_start(
        conn: Conn,
        item_id: Annotated[int, Form()],
        program_id: Annotated[int, Form()],
        note: Annotated[str, Form()] = "",
        back: Annotated[str, Form()] = "/trockner",
    ) -> RedirectResponse:
        dryer.start(conn, item_id, program_id, note)
        return redirect(safe_back(back, "/trockner"), "Trocknen gestartet")

    @app.post("/trockner/{log_id}/fertig")
    def dryer_finish(
        log_id: int, conn: Conn, back: Annotated[str, Form()] = "/trockner"
    ) -> RedirectResponse:
        dryer.finish(conn, log_id)
        return redirect(safe_back(back, "/trockner"), "Spule als getrocknet vermerkt")

    @app.post("/trockner/programme")
    def dryer_add_program(
        conn: Conn,
        name: Annotated[str, Form()],
        temp_c: Annotated[str, Form()],
        hours: Annotated[str, Form()],
        material: Annotated[str, Form()] = "",
        note: Annotated[str, Form()] = "",
    ) -> RedirectResponse:
        try:
            temp, dur = float(temp_c.replace(",", ".")), float(hours.replace(",", "."))
        except ValueError:
            raise LagerError("Temperatur und Stunden als Zahl eintragen") from None
        dryer.add_program(conn, name, material, temp, dur, note)
        return redirect("/trockner", f"Programm „{name.strip()}“ gespeichert")

    @app.post("/trockner/programme/{program_id}/loeschen")
    def dryer_delete_program(program_id: int, conn: Conn) -> RedirectResponse:
        dryer.delete_program(conn, program_id)
        return redirect("/trockner", "Programm gelöscht")

    # --- Slicer (Creality Print) -------------------------------------------------

    @app.get("/slicer", response_class=HTMLResponse)
    def slicer_page(request: Request, conn: Conn) -> HTMLResponse:
        spools = slicer.spools(conn)
        jobs = slicer.jobs(conn)
        for j in jobs:
            fils = j["filaments"]
            j["suggest"] = slicer.suggest(
                slicer.Job("", None, [slicer.Filament(0, f.get("type", "")) for f in fils]), spools
            )
        return render(
            request, conn, "slicer.html", jobs=jobs, spools=spools,
            folder=prefs.raw(conn, "slicer_dir"),
        )  # fmt: skip

    @app.post("/slicer/upload")
    async def slicer_upload(
        conn: Conn, files: Annotated[list[UploadFile], File()]
    ) -> RedirectResponse:
        added, errors = 0, []
        for f in files:
            if not f.filename:
                continue
            try:
                job = slicer.parse_bytes(await f.read(), f.filename)
                slicer.save_job(conn, job, f.filename)
                added += 1
            except (LagerError, zipfile.BadZipFile) as exc:
                errors.append(f"{f.filename}: {exc}")
        msg = f"{added} Druck(e) eingelesen" + (f" · {'; '.join(errors)}" if errors else "")
        return redirect("/slicer", msg)

    @app.post("/slicer/ordner")
    def slicer_scan(conn: Conn) -> RedirectResponse:
        added, errors = slicer.scan_folder(conn, prefs.raw(conn, "slicer_dir"))
        msg = f"{added} neue(r) Druck(e) im Ordner" + (
            f" · {'; '.join(errors[:3])}" if errors else ""
        )
        return redirect("/slicer", msg)

    @app.post("/slicer/{job_id}/buchen")
    async def slicer_book(job_id: int, request: Request, conn: Conn) -> RedirectResponse:
        form = await request.form()
        picks: list[int | None] = []
        i = 0
        while f"spool_{i}" in form:
            raw = str(form[f"spool_{i}"])
            picks.append(int(raw) if raw.isdigit() else None)
            i += 1
        return redirect("/slicer", slicer.book(conn, job_id, picks))

    @app.post("/slicer/{job_id}/loeschen")
    def slicer_delete(job_id: int, conn: Conn) -> RedirectResponse:
        with conn:
            conn.execute("DELETE FROM print_job WHERE id = ?", (job_id,))
        return redirect("/slicer", "Druckauftrag entfernt")

    # --- Massenbearbeitung ----------------------------------------------------------

    @app.get("/auswahl", response_class=HTMLResponse)
    def select_page(
        request: Request, conn: Conn, node: str = "", q: str = "", tag: str = "", src: str = ""
    ) -> HTMLResponse:
        items: list[Any] = []
        nodes: list[Any] = []
        title = "Alle Teile"
        if node.isdigit():
            parent = repo.get_container(conn, int(node))
            if parent is None:
                raise LagerError("Behälter nicht gefunden")
            items, nodes = repo.items_in(conn, parent["id"]), repo.children(conn, parent["id"])
            title = parent["name"]
        elif q.strip() or tag.isdigit():
            syn = repo.parse_synonyms(prefs.raw(conn, "synonyms"))
            found, _ = search.run(conn, q, syn, limit=200, tag=int(tag) if tag.isdigit() else None)
            items = [repo.get_item(conn, i["id"]) for i in found]
            title = f"Suche: {q}" if q else "Tag-Filter"
        elif src == "einkauf":
            items = [repo.get_item(conn, int(r["id"])) for r in repo.shopping_list(conn)]
            title = "Einkaufsliste"
        else:
            items = conn.execute(
                "SELECT * FROM item WHERE archived = 0 ORDER BY name LIMIT 500"
            ).fetchall()
        rows = [{"item": i, "path": repo.path_label(conn, i["container_id"])} for i in items]
        return render(
            request, conn, "auswahl.html", title=title, rows=rows, nodes=nodes,
            actions=bulk.ACTIONS, targets=repo.all_paths(conn),
            tags=itemtypes.all_types(conn), cats=kinds.ITEM_CATS,
            back=request.url.path + ("?" + request.url.query if request.url.query else ""),
        )  # fmt: skip

    @app.post("/bulk")
    async def bulk_apply(request: Request, conn: Conn) -> RedirectResponse:
        form = await request.form()
        refs = [str(v) for v in form.getlist("ref")]
        back = safe_back(str(form.get("back", "/auswahl")), "/auswahl")
        msg = bulk.apply(
            conn, refs, str(form.get("action", "")),
            value=str(form.get("value", "")), target=str(form.get("target", "")),
        )  # fmt: skip
        return redirect(back, msg)

    # --- Einkauf: bestellt / eingetroffen ----------------------------------------------

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


def _today() -> str:
    from datetime import date

    return date.today().isoformat()


__all__ = ["register", "sqlite3"]
