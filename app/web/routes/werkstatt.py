"""Werkstatt: Projekte (Stückliste, Reservieren), Entnahmen, Verliehen, Inventur,
Trockner, Slicer, Ablauf-Erinnerung und Zählen per Waage."""

import zipfile
from typing import Annotated, Any

from fastapi import FastAPI, File, Form, HTTPException, Request, UploadFile
from fastapi.responses import HTMLResponse, RedirectResponse

from app import (
    codes,
    dryer,
    expiry,
    inventory,
    prefs,
    projects,
    repo,
    slicer,
    weighing,
    withdrawals,
)
from app.repo import LagerError
from app.web.shared import Conn, Ctx, opt_int, redirect, safe_back, synonyms


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

    # --- Verliehen --------------------------------------------------------------------------

    @app.get("/verliehen", response_class=HTMLResponse)
    def lent_page(request: Request, conn: Conn) -> HTMLResponse:
        return render(request, conn, "list.html", title="Verliehen / in Benutzung",
                      rows=repo.lent_items(conn), kind="lent")  # fmt: skip

    @app.post("/items/{item_id}/lend")
    def lend(item_id: int, conn: Conn, to: Annotated[str, Form()] = "") -> RedirectResponse:
        repo.lend_item(conn, item_id, to)
        return redirect(f"/items/{item_id}", "Als verliehen markiert")

    @app.post("/items/{item_id}/return")
    def give_back(item_id: int, conn: Conn) -> RedirectResponse:
        repo.return_item(conn, item_id)
        return redirect(f"/items/{item_id}", "Zurück im Lager")

    # --- Entnahmen --------------------------------------------------------------------------

    @app.post("/items/{item_id}/take")
    def take_item(item_id: int, conn: Conn, qty: Annotated[int, Form()] = 1) -> RedirectResponse:
        withdrawals.take(conn, item_id, qty)
        return redirect(
            f"/items/{item_id}",
            f"Entnommen – bis zur Bestätigung in {withdrawals.DAYS} Tagen stornierbar",
        )

    @app.post("/withdrawals/{wid}/cancel")
    def cancel_withdrawal(request: Request, wid: int, conn: Conn) -> RedirectResponse:
        msg = withdrawals.cancel(conn, wid)
        return redirect(request.headers.get("referer", "/entnahmen").split("?")[0], msg)

    @app.get("/entnahmen", response_class=HTMLResponse)
    def withdrawals_page(request: Request, conn: Conn) -> HTMLResponse:
        return render(
            request, conn, "withdrawals.html", rows=withdrawals.recent(conn), days=withdrawals.DAYS
        )

    # --- Projekte ---------------------------------------------------------------------------

    @app.get("/projekte", response_class=HTMLResponse)
    def projects_page(request: Request, conn: Conn) -> HTMLResponse:
        return render(request, conn, "projects.html", projects=projects.all_projects(conn))

    @app.post("/projekte")
    def create_project(conn: Conn, name: Annotated[str, Form()]) -> RedirectResponse:
        pid = projects.create(conn, name)
        return redirect(f"/projekte/{pid}", "Projekt angelegt")

    @app.get("/projekte/{pid}", response_class=HTMLResponse)
    def project_page(request: Request, pid: int, conn: Conn, q: str = "") -> HTMLResponse:
        lines = projects.lines(conn, pid)
        found = repo.search_synonyms(conn, q, synonyms(conn), limit=12) if q.strip() else []
        return render(
            request,
            conn,
            "project.html",
            project=projects.get(conn, pid),
            lines=lines,
            bom=(bom := projects.compare(conn, pid)),
            bom_status={r["id"]: r for r in bom["lines"]},
            done=sum(1 for line in lines if line["gathered"]),
            found=found,
            pq=q,
        )

    @app.post("/projekte/{pid}/lines")
    def add_project_line(
        pid: int,
        conn: Conn,
        item_id: Annotated[str, Form()] = "",
        name: Annotated[str, Form()] = "",
        qty: Annotated[str, Form()] = "",
    ) -> RedirectResponse:
        projects.add_line(conn, pid, opt_int(item_id), name, opt_int(qty))
        return redirect(f"/projekte/{pid}", "Zur Liste hinzugefügt")

    @app.post("/projekte/lines/{line_id}/gather")
    def gather_line(request: Request, line_id: int, conn: Conn) -> RedirectResponse:
        msg = projects.gather(conn, line_id)
        return redirect(request.headers.get("referer", "/projekte").split("?")[0], msg)

    @app.post("/projekte/lines/{line_id}/delete")
    def delete_line(request: Request, line_id: int, conn: Conn) -> RedirectResponse:
        projects.remove_line(conn, line_id)
        return redirect(request.headers.get("referer", "/projekte").split("?")[0], "Entfernt")

    @app.post("/projekte/{pid}/done")
    def project_done(pid: int, conn: Conn) -> RedirectResponse:
        p = projects.get(conn, pid)
        projects.set_done(conn, pid, not p["done"])
        return redirect(
            f"/projekte/{pid}", "Wieder geöffnet" if p["done"] else "Als erledigt markiert"
        )

    # --- Inventur ---------------------------------------------------------------------------

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

        norm = codes.normalize(code) or code.strip()
        return redirect(f"/inventur/{node_id}", inventory.confirm_by_code(conn, node_id, norm))

    @app.post("/inventur/{node_id}/done")
    def inventory_done(node_id: int, conn: Conn) -> RedirectResponse:
        rest = inventory.finish(conn, node_id)
        extra = f" ({rest} Teile ohne einzelne Bestätigung)" if rest else ""
        return redirect("/inventur", f"Inventur abgeschlossen{extra}")

    @app.post("/projekte/{pid}/reservieren")
    def project_reserve(pid: int, conn: Conn) -> RedirectResponse:
        n = projects.reserve(conn, pid)
        return redirect(f"/projekte/{pid}", f"{n} Positionen reserviert")

    @app.post("/projekte/{pid}/freigeben")
    def project_release(pid: int, conn: Conn) -> RedirectResponse:
        projects.release(conn, pid)
        return redirect(f"/projekte/{pid}", "Reservierung aufgehoben")

    @app.post("/projekte/{pid}/einkauf")
    def project_to_shopping(pid: int, conn: Conn) -> RedirectResponse:
        n = projects.to_shopping(conn, pid)
        msg = f"{n} Teile auf der Einkaufsliste" if n else "Nichts nachzukaufen"
        return redirect(f"/projekte/{pid}", msg)

    # --- Trockner ---------------------------------------------------------------------------

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

    # --- Slicer (Creality Print) ------------------------------------------------------------

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

    # --- Ablauf-Erinnerung ------------------------------------------------------------------

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
