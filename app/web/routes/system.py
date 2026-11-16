"""System: Einstellungen (Reiter Allgemein, Bedienung, System mit Code-Zählern und Node-Typen;
Anbindungen in `anbindungen.py`, Benutzer in `konto.py`),
Status/Backup, Import/Export, Code-Schema und Arten, Verlauf/Rückgängig, Mehr-Seite,
Sprache sowie Health, Zertifikat, Manifest, Service Worker und Offline-Seite."""

import io
import json
import sqlite3
import tempfile
import zipfile
from pathlib import Path
from typing import Annotated

from fastapi import FastAPI, File, Form, HTTPException, Request, UploadFile
from fastapi.responses import HTMLResponse, JSONResponse, RedirectResponse, Response

from app import (
    __version__,
    backup,
    catalog,
    codes,
    d30,
    importer,
    itemtypes,
    kinds,
    labels,
    prefs,
    repo,
    scheduler,
    status,
)
from app.repo import LagerError
from app.web.shared import APP_DIR, NL, Conn, Ctx, FormDict, recent_ids, redirect, templates


def register(app: FastAPI, ctx: Ctx) -> None:
    settings = ctx.settings
    render = ctx.render

    # --- Health und Zertifikat --------------------------------------------------------------

    @app.get("/health")
    def health() -> dict[str, str]:
        return {"status": "ok", "version": __version__}

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

    # --- Import / Export --------------------------------------------------------------------

    @app.get("/import", response_class=HTMLResponse)
    def import_page(request: Request, conn: Conn) -> HTMLResponse:
        return render(request, conn, "import.html", report=None, text="", done=False)

    @app.post("/import", response_class=HTMLResponse)
    async def import_run(
        request: Request,
        conn: Conn,
        text: Annotated[str, Form()] = "",
        action: Annotated[str, Form()] = "preview",
        file: Annotated[UploadFile | None, File()] = None,
    ) -> HTMLResponse:
        commit = action == "commit"
        if file is not None and file.filename:
            text = (await file.read()).decode("utf-8-sig", errors="replace")
        report = importer.run(conn, text, commit=commit)
        done = commit and not report.errors
        return render(request, conn, "import.html", report=report, text=text, done=done)

    @app.get("/export.zip")
    def export_archive(conn: Conn) -> Response:
        """Gesamtarchiv: JSON-Export, Datenbank-Kopie (inkl. Einstellungen) und Fotos."""

        buf = io.BytesIO()
        with (
            tempfile.TemporaryDirectory() as tmp,
            zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as z,
        ):
            copy = Path(tmp) / "lager.db"
            dst = sqlite3.connect(copy)
            with dst:
                conn.backup(dst)
            dst.close()
            z.write(copy, "lager.db")
            z.writestr("lager-export.json", json.dumps(importer.export(conn), ensure_ascii=False))
            for folder in ("photos", "datasheets"):
                for f in (settings.data_dir / folder).glob("**/*"):
                    if f.is_file():
                        z.write(f, f"{folder}/{f.relative_to(settings.data_dir / folder)}")
        return Response(
            buf.getvalue(), media_type="application/zip",
            headers={"Content-Disposition": 'attachment; filename="lager-archiv.zip"'},
        )  # fmt: skip

    @app.get("/export.json")
    def export(conn: Conn) -> JSONResponse:
        return JSONResponse(
            importer.export(conn),
            headers={"Content-Disposition": 'attachment; filename="lager-export.json"'},
        )

    # --- Code-Schema, Arten, Sprache --------------------------------------------------------

    @app.get("/codes", response_class=HTMLResponse)
    def codes_page(request: Request, conn: Conn) -> HTMLResponse:
        return render(
            request,
            conn,
            "codes.html",
            prefixes=codes.PREFIX_LABELS,
            desc=kinds.PREFIX_DESC,
            custom_kinds={k["prefix"]: k for k in kinds.custom(conn)},
        )

    @app.post("/lang")
    def set_lang(
        conn: Conn, lang: Annotated[str, Form()], back: Annotated[str, Form()] = "/mehr"
    ) -> RedirectResponse:
        kinds.set_lang(conn, lang)
        target = back if back.startswith("/") and not back.startswith("//") else "/mehr"
        return redirect(target, "Sprache: English" if lang == "en" else "Sprache: Deutsch")

    @app.post("/arten")
    def kind_create(
        conn: Conn,
        label: Annotated[str, Form()],
        prefix: Annotated[str, Form()],
        description: Annotated[str, Form()] = "",
    ) -> RedirectResponse:
        kinds.create(conn, label, prefix, description)
        return redirect(
            "/labels#schema", f"Art „{label.strip()}“ mit {prefix.upper()}-001 angelegt"
        )

    @app.post("/arten/{kind}/delete")
    def kind_delete(kind: str, conn: Conn) -> RedirectResponse:
        kinds.delete(conn, kind)
        return redirect("/codes", "Art gelöscht")

    # --- Einstellungen: Reiter Allgemein · Bedienung · Anbindungen · Benutzer · System ------

    tab_url = {
        "allgemein": "/settings",
        "bedienung": "/settings/bedienung",
        "anbindungen": "/settings/anbindungen",
        "benutzer": "/settings/benutzer",
        "system": "/settings/system",
    }

    def prefs_tab(request: Request, conn: sqlite3.Connection, tab: str) -> HTMLResponse:
        return render(
            request,
            conn,
            "settings.html",
            tab=tab,
            groups=prefs.groups(tab),
            values=prefs.values(conn),
            base_url=settings.base_url,
            has_ca=settings.ca_cert.exists(),
        )

    @app.get("/settings", response_class=HTMLResponse)
    def settings_page(request: Request, conn: Conn) -> HTMLResponse:
        return prefs_tab(request, conn, "allgemein")

    @app.get("/settings/bedienung", response_class=HTMLResponse)
    def settings_bedienung(request: Request, conn: Conn) -> HTMLResponse:
        return prefs_tab(request, conn, "bedienung")

    @app.post("/settings")
    async def settings_save(request: Request, conn: Conn) -> RedirectResponse:
        """Einstellungen speichern: mit `_tab` nur die Felder dieses Reiters, sonst alle."""
        form = {k: str(v) for k, v in (await request.form()).items()}
        tab = form.get("_tab", "")
        if tab in prefs.TABS:
            prefs.save(conn, form, prefs.keys_of(tab))
            return redirect(tab_url[tab], "Einstellungen gespeichert")
        prefs.save(conn, form)
        return redirect("/settings", "Einstellungen gespeichert")

    # --- System: Betrieb, Daten, Nummernvergabe, Node-Typen ---------------------------------

    @app.get("/settings/admin")
    def admin_old(request: Request) -> RedirectResponse:
        """Alte Adresse (bis 1.3): Admin heißt jetzt System (Meldung ?msg= bleibt erhalten)."""
        query = f"?{request.url.query}" if request.url.query else ""
        return RedirectResponse(f"/settings/system{query}", status_code=308)

    @app.get("/settings/system", response_class=HTMLResponse)
    def system_page(request: Request, conn: Conn) -> HTMLResponse:
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
        return render(
            request,
            conn,
            "settings_system.html",
            tab="system",
            counters=counters,
            groups=prefs.groups("system"),
            values=prefs.values(conn),
            node_types=NL.join(catalog.node_types(conn)),
        )

    @app.post("/settings/admin/next")
    def admin_set_next(
        conn: Conn, prefix: Annotated[str, Form()], number: Annotated[int, Form()]
    ) -> RedirectResponse:
        try:
            codes.set_next(conn, prefix, number)
        except ValueError as exc:
            raise LagerError(str(exc)) from None
        nxt = codes.format_code(prefix, number)
        return redirect("/settings/system", f"{prefix}: nächster Code ist jetzt {nxt}")

    @app.post("/settings/admin/reset")
    def admin_reset(conn: Conn, prefix: Annotated[str, Form()]) -> RedirectResponse:
        if prefix not in codes.PREFIX_KIND:
            raise LagerError(f"Unbekanntes Präfix {prefix}")
        nxt = codes.format_code(prefix, codes.reset_counter(conn, prefix))
        return redirect("/settings/system", f"{prefix} zurückgesetzt – nächster Code {nxt}")

    @app.post("/settings/admin/remove")
    def admin_remove_code(conn: Conn, code: Annotated[str, Form()]) -> RedirectResponse:
        """Code von seinem Behälter/Gegenstand lösen (Objekt bleibt erhalten)."""
        if node := repo.get_container_by_code(conn, code):
            repo.assign_code(conn, node["id"], None)
            name = node["name"]
        elif item := repo.get_item_by_code(conn, code):
            repo.set_item_code(conn, item["id"], None)
            name = item["name"]
        elif t := itemtypes.by_code(conn, code):
            with conn:
                conn.execute("UPDATE item_type SET code = NULL WHERE id = ?", (t["id"],))
            name = t["name"]
        else:
            raise LagerError(f"{code} ist nicht vergeben")
        labels.dequeue(conn, [code])
        return redirect("/settings/system", f"{code} von „{name}“ entfernt")

    @app.post("/settings/admin/nodetypen")
    def admin_node_types(conn: Conn, form: FormDict) -> RedirectResponse:
        lines = [x.strip() for x in form.get("node_types", "").splitlines() if x.strip()]
        codes.set_setting(conn, "node_types", "\n".join(dict.fromkeys(lines)))
        return redirect("/settings/system#nodetypen", "Node-Typen gespeichert")

    # --- Backup und Status ------------------------------------------------------------------

    @app.post("/settings/backup")
    def settings_backup(conn: Conn) -> RedirectResponse:
        files = backup.run(settings.data_dir, settings.data_dir / "backups")
        return redirect("/settings/system#daten", "Backup: " + ", ".join(f.name for f in files))

    # --- Mehr -------------------------------------------------------------------------------

    @app.get("/mehr", response_class=HTMLResponse)
    def more_page(request: Request, conn: Conn) -> HTMLResponse:
        return render(
            request,
            conn,
            "more.html",
            n_lent=len(repo.lent_items(conn)),
            n_shopping=len(repo.shopping_list(conn)),
        )

    # --- Rückgängig und Verlauf -------------------------------------------------------------

    @app.post("/undo/{event_id}")
    def undo(request: Request, event_id: int, conn: Conn) -> RedirectResponse:
        msg = repo.undo(conn, event_id)
        back = request.headers.get("referer", "/").split("?")[0]
        return redirect(back, msg)

    @app.post("/undo-last")
    def undo_last(request: Request, conn: Conn) -> RedirectResponse:
        back = request.headers.get("referer", "/").split("?")[0]
        return redirect(back, repo.undo_last(conn))

    @app.post("/redo-last")
    def redo_last(request: Request, conn: Conn) -> RedirectResponse:
        back = request.headers.get("referer", "/").split("?")[0]
        return redirect(back, repo.redo_last(conn))

    @app.get("/verlauf", response_class=HTMLResponse)
    def history_page(request: Request, conn: Conn, tab: str = "aktionen") -> HTMLResponse:
        recent = repo.containers_by_ids(conn, recent_ids(request))
        return render(
            request,
            conn,
            "history.html",
            tab=tab if tab in ("gesehen", "druck") else "aktionen",
            jobs=d30.history(conn) if tab == "druck" else [],
            events=repo.recent_events(conn),
            undoable=repo.UNDOABLE,
            recent=recent[: prefs.number(conn, "home_recent")],
        )

    # --- Offline-App: Service Worker, Manifest ----------------------------------------------

    @app.get("/sw.js")
    def service_worker() -> Response:
        """Service Worker im Wurzelpfad (Geltungsbereich „/“); Version = Stand von CSS/JS."""
        js = (APP_DIR / "static" / "sw.js").read_text(encoding="utf-8")
        return Response(
            js.replace("__V__", str(templates.env.globals["ASSET_V"])),
            media_type="text/javascript",
            headers={"Cache-Control": "no-cache", "Service-Worker-Allowed": "/"},
        )

    @app.get("/offline", response_class=HTMLResponse)
    def offline_page(request: Request, conn: Conn) -> HTMLResponse:
        return render(request, conn, "offline.html")

    @app.get("/manifest.webmanifest")
    def manifest(conn: Conn) -> JSONResponse:
        return JSONResponse(
            {
                "id": "/",
                "name": prefs.raw(conn, "app_name"),
                "short_name": prefs.raw(conn, "app_name"),
                "description": "Lager mit QR-Codes: suchen, einlagern, entnehmen – auch offline.",
                "lang": "de",
                "start_url": "/",
                "scope": "/",
                "display": "standalone",
                "orientation": "portrait",
                "background_color": "#0B0306",
                "theme_color": "#0B0306",
                "icons": [
                    {"src": "/static/icon-192.png", "sizes": "192x192", "type": "image/png"},
                    {"src": "/static/icon-512.png", "sizes": "512x512", "type": "image/png"},
                    {
                        "src": "/static/icon-512.png",
                        "sizes": "512x512",
                        "type": "image/png",
                        "purpose": "maskable",
                    },
                ],
                "shortcuts": [
                    {"name": "Scannen", "url": "/scan"},
                    {"name": "Hinzufügen", "url": "/neu/go"},
                    {"name": "Suche", "url": "/suche"},
                ],
            },
            media_type="application/manifest+json",
        )

    # --- Status und Backup ------------------------------------------------------------------

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
