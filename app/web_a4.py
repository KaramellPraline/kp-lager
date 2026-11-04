# ruff: noqa: E501
"""Routen: A4-Etikettendruck (Warteschlange, Vorschau, PDF, Netzwerkdrucker), Bin-Etikett-Editor
und die Bin-Druckdatei (Parameter für den 3D-Generator)."""

import json
import sqlite3
from collections.abc import Callable
from typing import Annotated, Any
from urllib.parse import urlparse

from fastapi import Depends, FastAPI, HTTPException, Request
from fastapi.responses import HTMLResponse, JSONResponse, RedirectResponse, Response

from app import a4, codes, kasten, labels, repo
from app.config import Settings
from app.repo import LagerError


async def form_fields(request: Request) -> dict[str, str]:
    form = await request.form()
    return {k: v for k, v in form.items() if isinstance(v, str)}


Form = Annotated[dict[str, str], Depends(form_fields)]


def register(
    app: FastAPI,
    Conn: Any,
    render: Callable[..., HTMLResponse],
    redirect: Callable[..., RedirectResponse],
    settings: Settings,
) -> None:
    def printer(conn: sqlite3.Connection) -> str:
        return codes.get_setting(conn, "a4_printer", "")

    def jobs_of(conn: sqlite3.Connection) -> list[dict[str, Any]]:
        return [q["job"] for q in a4.queue(conn)]

    def back_of(request: Request, default: str) -> str:
        ref = request.headers.get("referer", "")
        path = "/" + ref.split("://", 1)[-1].partition("/")[2] if ref else ""
        return (
            path
            if path.startswith("/") and not path.startswith("//") and len(path) > 1
            else default
        )

    def container_choices(conn: sqlite3.Connection) -> list[dict[str, Any]]:
        """Alle Behälter mit Name und Code – Auswahl übernimmt beides ins Etikett."""
        out = []
        for p in repo.all_paths(conn):
            node = repo.get_container(conn, p["id"])
            if node is not None:
                out.append({"id": node["id"], "label": p["label"], "name": node["name"],
                            "code": node["code"] or ""})  # fmt: skip
        return out

    def layout_job(conn: sqlite3.Connection, f: dict[str, str] | Any) -> dict[str, Any]:
        """Frei gestaltetes Etikett aus dem Formular; {name} {code} {inhalt} {ort} kommen aus dem Behälter."""
        ctx = {"name": "", "code": codes.normalize(f.get("code", "")) or "" if f.get("code", "").strip() else "",
               "inhalt": "", "ort": ""}  # fmt: skip
        if str(f.get("container", "")).isdigit():
            node = repo.get_container(conn, int(f["container"]))
            if node is None:
                raise LagerError("Behälter nicht gefunden")
            names = list(dict.fromkeys(i["name"] for i in repo.items_in(conn, node["id"])))
            ctx.update({"name": node["name"], "code": ctx["code"] or node["code"] or "",
                        "inhalt": ", ".join(names[:8]), "ort": repo.path_label(conn, node["id"])})  # fmt: skip
        cfg = []
        for i in range(4):
            text = f.get(f"t_{i}", "")
            for key, val in ctx.items():
                text = text.replace("{" + key + "}", val)
            if text.strip():
                cfg.append({"t": text.strip(), "w": f.get(f"w_{i}", "1"), "a": f.get(f"a_{i}", "center"),
                            "c": f.get(f"c_{i}", "black")})  # fmt: skip
        if not cfg:
            raise LagerError("Bitte einen Behälter wählen oder Text eintragen")
        qrpos = f.get("qrpos", "left")
        return {
            "type": "layout", "w": f.get("w", ""), "h": f.get("h", ""), "color": f.get("color", "red"),
            "frame": f.get("frame", "round"), "qrpos": qrpos, "cfg": cfg,
            "title": cfg[0]["t"], "code": ctx["code"],
            "qr": labels.qr_content(settings.base_url, ctx["code"]) if ctx["code"] and qrpos != "none" else "",
        }  # fmt: skip

    @app.get("/a4/layout.png")
    def a4_layout_png(request: Request, conn: Conn) -> Response:
        """Live-Vorschau des Formulars (noch nicht in der Warteschlange)."""
        try:
            job = layout_job(conn, request.query_params)
        except LagerError:
            job = {"type": "layout", "w": request.query_params.get("w", ""), "h": request.query_params.get("h", ""),
                   "cfg": [{"t": "Behälter wählen oder Text eintragen", "w": 1, "a": "center", "c": "red"}],
                   "frame": request.query_params.get("frame", "round")}  # fmt: skip
        return Response(
            a4.png(a4.render(job)), media_type="image/png", headers={"Cache-Control": "no-store"}
        )

    # --- Warteschlange ------------------------------------------------------------------------

    @app.get("/a4", response_class=HTMLResponse)
    def a4_page(request: Request, conn: Conn) -> HTMLResponse:
        queue = a4.queue(conn)
        try:
            n_pages = len(a4.pack([(q["job"]["w"], q["job"]["h"]) for q in queue])) if queue else 0
        except LagerError:
            n_pages = 0
        return render(
            request, conn, "a4.html", queue=queue, pages=n_pages, printer=printer(conn),
            types=a4.TYPES, colors=a4.COLOR_NAMES, containers=container_choices(conn),
            presets=a4.LAYOUT_PRESETS, max_lines=4,
        )  # fmt: skip

    @app.post("/a4/add")
    def a4_add(conn: Conn, form: Form) -> RedirectResponse:
        """Etikett in die Warteschlange: frei gestaltet (t_0 …) oder klassisch (title/lines)."""
        if "t_0" in form:
            a4.enqueue(conn, layout_job(conn, form))
            return redirect("/a4", "Etikett in der A4-Warteschlange")
        code = codes.normalize(form.get("code", "")) if form.get("code", "").strip() else ""
        lines = [x.strip() for x in form.get("lines", "").splitlines() if x.strip()]
        title = form.get("title", "").strip()
        if form.get("container", "").isdigit():  # aus einem vorhandenen Behälter
            node = repo.get_container(conn, int(form["container"]))
            if node is None:
                raise LagerError("Behälter nicht gefunden")
            title = title or node["name"]
            code = code or node["code"] or ""
            if form.get("contents"):
                names = list(dict.fromkeys(i["name"] for i in repo.items_in(conn, node["id"])))
                lines = lines + names[:6]
        if not title:
            raise LagerError("Bitte einen Titel eintragen oder einen Behälter wählen")
        a4.enqueue(conn, {
            "type": form.get("type", "box"), "title": title,
            "code": code or "", "lines": lines, "w": form.get("w", ""), "h": form.get("h", ""),
            "color": form.get("color", "black"),
            "qr": labels.qr_content(settings.base_url, code) if code and form.get("qr") else "",
        })  # fmt: skip
        return redirect("/a4", "Etikett in der A4-Warteschlange")

    @app.post("/a4/{job_id}/remove")
    def a4_remove(job_id: int, conn: Conn) -> RedirectResponse:
        a4.remove(conn, job_id)
        return redirect("/a4", "Entfernt")

    @app.post("/a4/clear")
    def a4_clear(conn: Conn) -> RedirectResponse:
        a4.clear(conn)
        return redirect("/a4", "A4-Warteschlange geleert")

    @app.get("/a4/vorschau/{job_id}.png")
    def a4_label_png(job_id: int, conn: Conn) -> Response:
        row = next((q for q in a4.queue(conn) if q["id"] == job_id), None)
        if row is None:
            raise HTTPException(404, "Kein solches Etikett")
        return Response(a4.png(a4.render(row["job"])), media_type="image/png",
                        headers={"Cache-Control": "no-store"})  # fmt: skip

    @app.get("/a4/seite/{n}.png")
    def a4_page_png(n: int, conn: Conn) -> Response:
        pages = a4.pages_of(jobs_of(conn))
        if not 1 <= n <= len(pages):
            raise HTTPException(404, "Keine solche Seite")
        return Response(a4.png(pages[n - 1], 900), media_type="image/png",
                        headers={"Cache-Control": "no-store"})  # fmt: skip

    @app.get("/a4/queue.pdf")
    def a4_pdf(conn: Conn) -> Response:
        return Response(a4.pdf(jobs_of(conn)), media_type="application/pdf",
                        headers={"Content-Disposition": 'inline; filename="etiketten.pdf"'})  # fmt: skip

    @app.post("/a4/drucken")
    def a4_print(conn: Conn, form: Form) -> RedirectResponse:
        """Nur nach ausdrücklicher Bestätigung: PDF an den Netzwerkdrucker, danach Queue leeren."""
        if form.get("confirm") != "1":
            raise LagerError("Druck nicht bestätigt")
        queue = a4.queue(conn)
        if not queue:
            raise LagerError("Keine Etiketten in der A4-Warteschlange")
        pages = len(a4.pack([(q["job"]["w"], q["job"]["h"]) for q in queue]))
        a4.ipp_print(
            printer(conn), a4.pdf([q["job"] for q in queue]), f"KP Lager {len(queue)} Etiketten"
        )
        a4.clear(conn)
        return redirect(
            "/a4", f"{len(queue)} Etiketten auf {pages} Seite{'n' if pages != 1 else ''} gedruckt"
        )

    # --- Etiketten aus Teilen und Behältern in die A4-Warteschlange ------------------------------

    @app.post("/a4/queue/item/{item_id}")
    def a4_queue_item(request: Request, item_id: int, conn: Conn, form: Form) -> RedirectResponse:
        item = repo.get_item(conn, item_id)
        if not item["code"]:
            raise LagerError("Teil hat noch keinen Code")
        a4.enqueue(conn, a4.job_item(conn, settings.base_url, item, form.get("color", "black")))
        return redirect(
            back_of(request, f"/items/{item_id}"), f"{item['code']} in der A4-Warteschlange"
        )

    @app.post("/a4/queue/node/{node_id}")
    def a4_queue_node(request: Request, node_id: int, conn: Conn, form: Form) -> RedirectResponse:
        node = repo.get_container(conn, node_id)
        if node is None:
            raise HTTPException(404, "Behälter nicht gefunden")
        if node["kind"] == "bin":
            job = a4.job_bin_side(conn, node, form.get("color", "red"))
        elif node["code"]:
            job = a4.job_container(conn, settings.base_url, node, form.get("color", "black"))
        else:
            raise LagerError("Behälter hat noch keinen Code")
        a4.enqueue(conn, job)
        return redirect(back_of(request, f"/n/{node_id}"), "In der A4-Warteschlange")

    # --- Bin-Etikett-Editor -----------------------------------------------------------------------

    def bin_or_404(conn: sqlite3.Connection, node_id: int) -> sqlite3.Row:
        node = repo.get_container(conn, node_id)
        if node is None or node["kind"] != "bin":
            raise HTTPException(404, "Kein Einsatz")
        return node

    @app.get("/n/{node_id}/etikett", response_class=HTMLResponse)
    def bin_label_page(request: Request, node_id: int, conn: Conn) -> HTMLResponse:
        node = bin_or_404(conn, node_id)
        slots = repo.children(conn, node_id) or [node]
        # Namen aus Teilen ohne eigenes Etikett (nur Tags): als Schnellwahl für die Fächer
        tags = [
            r["name"] for r in conn.execute(
                "SELECT DISTINCT name FROM item WHERE standalone = 0 AND archived = 0"
                " ORDER BY name COLLATE NOCASE LIMIT 80"
            )
        ]  # fmt: skip
        return render(
            request, conn, "bin_etikett.html", node=node, tags=tags,
            slots=[{"id": s["id"], "pos": s["position"] or s["name"], "own": s["label_text"] or "",
                    "text": "\n".join(a4.compartment_text(conn, s))} for s in slots],
            colors=a4.COLOR_NAMES, path=repo.container_path(conn, node_id)[:-1],
        )  # fmt: skip

    @app.get("/n/{node_id}/etikett.png")
    def bin_label_png(node_id: int, conn: Conn, color: str = "red") -> Response:
        node = bin_or_404(conn, node_id)
        return Response(a4.png(a4.render(a4.job_bin_side(conn, node, color))), media_type="image/png",
                        headers={"Cache-Control": "no-store"})  # fmt: skip

    @app.post("/n/{node_id}/etikett")
    def bin_label_save(node_id: int, conn: Conn, form: Form) -> RedirectResponse:
        node = bin_or_404(conn, node_id)
        slots = repo.children(conn, node_id) or [node]
        with conn:
            for s in slots:
                text = "\n".join(
                    x.strip() for x in form.get(f"t_{s['id']}", "").splitlines() if x.strip()
                )
                conn.execute(
                    "UPDATE container SET label_text = ? WHERE id = ?", (text or None, s["id"])
                )
        if form.get("queue"):
            a4.enqueue(
                conn,
                a4.job_bin_side(conn, node, form.get("color", "red")),
            )
            return redirect(f"/n/{node_id}/etikett", "Seitenetikett in der A4-Warteschlange")
        return redirect(f"/n/{node_id}/etikett", "Etikett-Texte gespeichert")

    # --- Bin-Druckdatei -------------------------------------------------------------------------------

    @app.get("/labels/bins.json")
    def bins_file(conn: Conn) -> JSONResponse:
        """Alle Sortierkästen/Einsätze samt Parametern als eine Datei (3D-Generator)."""
        data = kasten.print_file(conn)
        out = settings.data_dir / "druck"
        out.mkdir(parents=True, exist_ok=True)
        (out / "bins.json").write_text(
            json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8"
        )
        return JSONResponse(
            data, headers={"Content-Disposition": 'attachment; filename="bins.json"'}
        )

    @app.post("/settings/admin/a4drucker")
    def admin_a4_printer(conn: Conn, form: Form) -> RedirectResponse:
        url = form.get("a4_printer", "").strip()
        if url:
            p = urlparse(url)
            if p.scheme not in ("ipp", "ipps", "http", "https") or not p.hostname:
                raise LagerError("Drucker-Adresse ungültig, z. B. ipp://192.168.1.50/ipp/print")
        codes.set_setting(conn, "a4_printer", url)
        return redirect("/settings/admin#a4drucker", "A4-Drucker gespeichert")
