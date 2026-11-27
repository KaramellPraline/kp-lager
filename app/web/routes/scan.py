"""Scan: QR-Einstieg (/c/<code>), Scan-Modus und seine JSON-Endpunkte (Entnehmen,
Einräumen, Sammeln, Code-Abfrage)."""

from typing import Annotated, Any

from fastapi import Body, FastAPI, Form, HTTPException, Request
from fastapi.responses import HTMLResponse, JSONResponse, Response

from app import codes, dryer, itemtypes, materials, projects, repo, withdrawals
from app.repo import LagerError
from app.web.shared import DRYER_COOKIE, Conn, Ctx, redirect


def register(app: FastAPI, ctx: Ctx) -> None:
    render = ctx.render

    # --- QR-Einstieg ------------------------------------------------------------------------

    @app.get("/c/{code}", response_model=None)
    @app.get("/C/{code}", response_model=None)  # QR-Inhalt in Großbuchstaben
    def by_code(request: Request, code: str, conn: Conn) -> Response:
        code = codes.normalize(code) or code.strip()
        msg = request.query_params.get("msg", "")
        if node := repo.get_container_by_code(conn, code):
            if node["kind"] == "dryer":  # Trockner scannen → jetzt Filament-Etiketten scannen
                resp = redirect(f"/trockner/scan/{node['id']}", msg)
                resp.set_cookie(DRYER_COOKIE, str(node["id"]), max_age=600, samesite="lax")
                return resp
            return redirect(f"/n/{node['id']}", msg)
        if item := repo.get_item_by_code(conn, code):
            wait = request.cookies.get(DRYER_COOKIE, "")
            dryer_node = repo.get_container(conn, int(wait)) if wait.isdigit() else None
            if item["material"] == "fil" and dryer_node and dryer_node["kind"] == "dryer":
                done = dryer.mark_dried(conn, item["id"], dryer_node)
                resp = redirect(f"/trockner/scan/{dryer_node['id']}", done)
                resp.set_cookie(DRYER_COOKIE, str(dryer_node["id"]), max_age=600, samesite="lax")
                return resp
            return redirect(f"/items/{item['id']}", msg)
        if t := itemtypes.by_code(conn, code):
            return redirect(f"/typen/{t['id']}", msg)
        prefix = codes.prefix_of(code)
        if prefix == codes.TYPE_PREFIX:
            raise HTTPException(404, f"Tag {code} gibt es nicht")
        if prefix is None:
            raise HTTPException(404, f"'{code}' passt nicht zum Code-Schema (z. B. EUR-001)")
        template = "new_item_code.html" if prefix in codes.ITEM_PREFIXES else "new_code.html"
        return render(
            request,
            conn,
            template,
            code=code,
            default_kind=codes.PREFIX_KIND[prefix],
            paths=repo.all_paths(conn),
        )

    # --- Scan-Modus -------------------------------------------------------------------------

    @app.get("/scan", response_class=HTMLResponse)
    def scan_page(request: Request, conn: Conn, projekt: int = 0) -> HTMLResponse:
        project = projects.get(conn, projekt) if projekt else None
        return render(request, conn, "scan.html", project=project)

    @app.post("/api/take")
    def api_take(
        conn: Conn, code: Annotated[str, Form()], qty: Annotated[int, Form()] = 1
    ) -> JSONResponse:
        """Scan-Modus „Entnehmen“: Teil per Code entnehmen (7 Tage stornierbar)."""
        norm = codes.normalize(code) or code
        item = repo.get_item_by_code(conn, norm)
        if item is None:
            return JSONResponse(
                {"ok": False, "msg": f"{norm}: kein Teil (Behälter nicht entnehmbar)"}, 404
            )
        try:
            wid = withdrawals.take(conn, item["id"], qty)
        except LagerError as exc:
            return JSONResponse({"ok": False, "msg": str(exc)}, status_code=400)
        left = repo.get_item(conn, item["id"])["qty"]
        rest = f" · noch {left}" if left is not None else ""
        return JSONResponse({"ok": True, "msg": f"„{item['name']}“ entnommen{rest}", "cancel": wid})

    @app.post("/api/projects/{pid}/gather")
    def api_gather(pid: int, conn: Conn, code: Annotated[str, Form()]) -> JSONResponse:
        try:
            msg = projects.gather_by_code(conn, pid, codes.normalize(code) or code)
        except LagerError as exc:
            return JSONResponse({"ok": False, "msg": str(exc)}, status_code=400)
        lines = projects.lines(conn, pid)
        done = sum(1 for line in lines if line["gathered"])
        return JSONResponse({"ok": True, "msg": f"{msg} · {done} von {len(lines)}"})

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

    @app.post("/api/move-batch")
    def api_move_batch(conn: Conn, body: Annotated[dict[str, Any], Body()]) -> JSONResponse:
        """Sammelmodus beim Einräumen: alle gescannten Codes auf einmal ins Ziel.

        Noch nicht angelegte ART-Codes (vorgedruckte Etiketten) werden mit dem Namen neu angelegt.
        """
        target = str(body.get("target", ""))
        dest = repo.get_container_by_code(conn, codes.normalize(target) or target)
        if dest is None:
            return JSONResponse({"ok": False, "msg": f"Ziel {target} unbekannt"}, status_code=404)
        results = []
        for entry in body.get("entries", []):
            raw, name = str(entry.get("code", "")), " ".join(str(entry.get("name", "")).split())
            norm = codes.normalize(raw) or raw
            try:
                if item := repo.get_item_by_code(conn, norm):
                    repo.move_item(conn, item["id"], dest["id"])
                    msg = f"„{item['name']}“ eingeräumt"
                elif node := repo.get_container_by_code(conn, norm):
                    repo.move_container(conn, node["id"], dest["id"])
                    msg = f"„{node['name']}“ eingeräumt"
                elif (prefix := codes.prefix_of(norm)) in codes.ITEM_PREFIXES and name:
                    new_id = repo.add_item(conn, dest["id"], name, code=norm)
                    if material := materials.PREFIX_MATERIAL.get(prefix or ""):
                        materials.save_specs(conn, new_id, material, {})
                    msg = f"„{name}“ neu angelegt"
                else:
                    raise LagerError(f"{norm} ist noch nicht angelegt")
                results.append({"code": norm, "ok": True, "msg": msg})
            except LagerError as exc:
                results.append({"code": norm, "ok": False, "msg": str(exc)})
        done = sum(1 for r in results if r["ok"] is True)
        return JSONResponse({
            "ok": done == len(results),
            "msg": f"{done} von {len(results)} nach „{dest['name']}“ eingeräumt",
            "results": results,
        })  # fmt: skip

    @app.get("/api/code/{code}")
    def api_code(code: str, conn: Conn) -> JSONResponse:
        norm = codes.normalize(code) or code
        if node := repo.get_container_by_code(conn, norm):
            return JSONResponse({"type": "container", "code": norm, "name": node["name"]})
        if item := repo.get_item_by_code(conn, norm):
            return JSONResponse({"type": "item", "code": norm, "name": item["name"]})
        return JSONResponse(
            {"type": "unknown", "code": norm, "name": "", "prefix": codes.prefix_of(norm)}
        )
