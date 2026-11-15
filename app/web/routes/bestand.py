"""Bestand: Startseite, Behälter-Seite, Suche, Baum, Zu sortieren, freie Plätze,
Favoriten, Umlagern, Sortierkasten-Einsätze und Auswahl/Massenbearbeitung."""

import sqlite3
from typing import Annotated, Any

from fastapi import FastAPI, Form, HTTPException, Request, UploadFile
from fastapi.responses import HTMLResponse, RedirectResponse, Response

from app import (
    bulk,
    cards,
    catalog,
    codes,
    inventory,
    itemtypes,
    kasten,
    kinds,
    labels,
    photos,
    prefs,
    repo,
    status,
    value,
    withdrawals,
)
from app import search as finder
from app.repo import LagerError
from app.web import formen
from app.web.shared import (
    CARRY_COOKIE,
    RECENT_COOKIE,
    Conn,
    Ctx,
    FormDict,
    carry_info,
    container_code,
    last_target,
    need_node,
    node_url,
    pick_dims,
    recent_ids,
    redirect,
    safe_back,
    synonyms,
    templates,
)


def register(app: FastAPI, ctx: Ctx) -> None:
    render = ctx.render
    photo_dir = ctx.photo_dir

    # --- Startseite -------------------------------------------------------------------------

    @app.get("/", response_class=HTMLResponse)
    def index(request: Request, conn: Conn) -> HTMLResponse:
        """Bestand durchstöbern – hinzufügen geschieht unter „Hinzufügen“ (/neu)."""
        inbox_n = len(repo.items_in(conn, repo.inbox(conn)))
        found = [
            ("/zu-sortieren", "content.inbox", "Zu sortieren", inbox_n),
            ("/einkauf", "content.shopping", "Nachkaufen", len(repo.shopping_list(conn))),
            ("/inventur", "select.check", "Inventur fällig",
             len(inventory.due(conn, prefs.number(conn, "inventory_days")))),
            ("/labels", "content.tag", "Etiketten wartend", labels.queue_count(conn)),
            ("/entnahmen", "action.take", "Entnahmen offen", withdrawals.open_count(conn)),
            ("/ablauf", "status.attention", "Läuft ab", len(status.expiring(conn))),
            ("/projekte", "content.project", "Offene Projekte",
             conn.execute("SELECT COUNT(*) FROM project WHERE done = 0").fetchone()[0]),
            ("/verliehen", "content.lent", "Verliehen", len(repo.lent_items(conn))),
        ]  # fmt: skip
        worth, _unpriced = value.total(conn)
        last = codes.get_setting(conn, "backup_last", "")
        err = codes.get_setting(conn, "backup_error", "")
        return render(
            request,
            conn,
            "index.html",
            roots=repo.children(conn, None),
            favorites=repo.favorites(conn),
            tasks=[t for t in found if t[3]],
            stats={
                "n_items": conn.execute("SELECT COUNT(*) FROM item WHERE archived = 0").fetchone()[
                    0
                ],
                "n_containers": conn.execute("SELECT COUNT(*) FROM container").fetchone()[0],
                "worth": value.euro(worth),
                "backup": last[:10] if last else "–",
                "backup_bad": bool(err),
            },
        )

    # --- Behälter-Seite ---------------------------------------------------------------------

    @app.get("/n/{node_id}", response_class=HTMLResponse)
    def node_page(request: Request, node_id: int, conn: Conn) -> HTMLResponse:
        node = need_node(conn, node_id)
        cols = int(node["grid"].split("x")[0]) if node["grid"] else 0
        path = repo.container_path(conn, node_id)[:-1]
        raw_rot = request.query_params.get("drehen") or request.cookies.get("tv_rot", "")
        rot = int(raw_rot) if raw_rot in ("0", "90", "180", "270") else kasten.DEFAULT_ROT
        resp = render(
            request,
            conn,
            "node.html",
            node=node,
            path=path,
            kids=repo.children(conn, node_id),
            items=repo.items_in(conn, node_id),
            cols=cols,
            topview=kasten.topview(conn, node, rot),
            targets=kasten.quick_targets(conn, node) if node["model"] else [],
            free=kasten.free_cells(conn, node),
            place=request.query_params.get("place", ""),
            sizes=kasten.SIZES,
            divs=kasten.DIVS,
            cad=kasten.cad_command(node) if node["kind"] == "bin" else "",
            cad_fields=kasten.CAD_FIELDS,
            cad_values=kasten.cad_params(node) if node["kind"] == "bin" else {},
            cards=cards.for_container(conn, node_id),
        )
        if request.query_params.get("drehen") in ("0", "90", "180", "270"):
            resp.set_cookie("tv_rot", str(rot), max_age=31_536_000, samesite="lax")
        recent = [node_id] + [i for i in recent_ids(request) if i != node_id]
        resp.set_cookie(
            RECENT_COOKIE, ",".join(map(str, recent[:20])), max_age=31_536_000, samesite="lax"
        )
        return resp

    @app.get("/n/{node_id}/inhalt", response_class=HTMLResponse)
    def node_peek(request: Request, node_id: int, conn: Conn) -> HTMLResponse:
        """Kleine Inhaltsliste für „Wohin?“ beim Hinzufügen."""
        node = need_node(conn, node_id)
        return templates.TemplateResponse(
            request,
            "_peek.html",
            {"kids": repo.children(conn, node_id), "items": repo.items_in(conn, node_id),
             "node": node, "icon": templates.env.globals.get("icon")},
        )  # fmt: skip

    # --- Suche ------------------------------------------------------------------------------

    @app.get("/suche", response_model=None)
    def search(request: Request, conn: Conn, q: str = "", tag: str = "") -> Response:
        q = q.strip()
        tag_id = int(tag) if tag.isdigit() else None
        code = codes.normalize(q) or q
        if q and (node := repo.get_container_by_code(conn, code)):
            return redirect(f"/n/{node['id']}")
        if q and (item := repo.get_item_by_code(conn, code)):
            return redirect(f"/items/{item['id']}")
        syn = synonyms(conn)
        items, corrected = finder.run(
            conn, q, syn, typo=prefs.flag(conn, "typo_correction"), tag=tag_id
        )
        return render(
            request,
            conn,
            "search.html",
            q=q,
            corrected=corrected,
            items=items,
            containers=[] if tag_id else finder.containers(conn, corrected or q, syn),
            tags=[t for t in itemtypes.all_types(conn) if t["n"]],
            tag=tag_id,
        )

    # --- Zu sortieren, freie Plätze, Favoriten ----------------------------------------------

    @app.get("/zu-sortieren", response_class=HTMLResponse)
    def inbox_page(request: Request, conn: Conn) -> HTMLResponse:
        inbox_id = repo.inbox(conn)
        return render(
            request,
            conn,
            "inbox.html",
            items=repo.items_in(conn, inbox_id),
            targets=[p for p in repo.all_paths(conn) if p["id"] != inbox_id],
            target=last_target(request),
        )

    @app.post("/zu-sortieren/{item_id}/move")
    def inbox_move(item_id: int, conn: Conn, target: Annotated[int, Form()]) -> RedirectResponse:
        repo.move_item(conn, item_id, need_node(conn, target)["id"])
        return redirect(
            "/zu-sortieren",
            f"Einsortiert nach {repo.path_label(conn, target)}",
            repo.last_event_id(conn),
        )

    @app.get("/platz", response_class=HTMLResponse)
    def free_page(request: Request, conn: Conn) -> HTMLResponse:
        return render(request, conn, "free.html", **repo.free_places(conn))

    @app.post("/n/{node_id}/favorite")
    def favorite(node_id: int, conn: Conn) -> RedirectResponse:
        node = need_node(conn, node_id)
        repo.set_favorite(conn, node_id, not node["favorite"])
        return redirect(
            f"/n/{node_id}", "Favorit entfernt" if node["favorite"] else "Als Favorit gemerkt"
        )

    # --- Sortierkasten-Einsätze (NORB16) ----------------------------------------------------

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

    @app.post("/n/{node_id}/bins/{bin_id}/move")
    def move_bin(
        node_id: int, bin_id: int, conn: Conn, cells: Annotated[str, Form()]
    ) -> RedirectResponse:
        """Drag & Drop in der Draufsicht: Einsatz auf neue Zellen setzen."""
        try:
            pos = kasten.move_bin(conn, bin_id, [c for c in cells.split(",") if c])
        except LagerError as exc:
            return redirect(f"/n/{node_id}", f"Verschieben nicht möglich: {exc}")
        return redirect(f"/n/{node_id}", f"Einsatz nach {pos} verschoben (Etikett neu drucken)")

    @app.post("/n/{node_id}/cad")
    async def save_bin_cad(node_id: int, request: Request, conn: Conn) -> RedirectResponse:
        form = await request.form()
        kasten.save_cad(conn, node_id, {k: str(v) for k, v in form.items()})
        return redirect(f"/n/{node_id}#cad", "Druck-Parameter gespeichert")

    @app.post("/n/{node_id}/fill")
    def fill_bins(node_id: int, conn: Conn) -> RedirectResponse:
        """Alle freien Zellen mit 1x1-Einsätzen belegen (schnelle Ersteinrichtung)."""
        node = need_node(conn, node_id)
        cells = kasten.free_cells(conn, node)
        for cell in cells:
            kasten.place_bin(conn, node_id, cell, "1x1")
        return redirect(f"/n/{node_id}", f"{len(cells)} Einsätze 1x1 angelegt")

    # --- Behälter bearbeiten, Code, Löschen, Foto -------------------------------------------

    @app.get("/n/{node_id}/bearbeiten", response_class=HTMLResponse)
    def node_edit_page(request: Request, node_id: int, conn: Conn, art: str = "") -> HTMLResponse:
        """Bearbeiten: dasselbe Formular wie Hinzufügen › Behälter, vorbefüllt."""
        node = need_node(conn, node_id)
        form = formen.behaelter(
            conn, request, node["kind"], node=node, art_url=f"/n/{node_id}/bearbeiten?art="
        )
        flat = [k for _, ks in form["groups"] for k in ks]
        chosen = kinds.resolve(art) if art else None
        if chosen in flat:
            form["art"] = chosen
        return render(
            request, conn, "node_edit.html", **form, form_action=f"/n/{node_id}/bearbeiten",
            path=repo.container_path(conn, node_id)[:-1],
        )  # fmt: skip

    @app.post("/n/{node_id}/bearbeiten")
    def node_edit_save(node_id: int, conn: Conn, form: FormDict) -> RedirectResponse:
        node = need_node(conn, node_id)
        name = form.get("name", "").strip()
        if not name:
            raise LagerError("Name fehlt")
        kind = form.get("kind", "") or node["kind"]
        dims = pick_dims(form.get("dims", ""), form.get("dims_custom", ""), "")
        repo.update_container(conn, node_id, name, form.get("notes", ""))
        repo.set_container_tare(conn, node_id, form.get("tare", ""))
        repo.update_container_shape(conn, node_id, kind, dims, bool(form.get("airtight")))
        new_code = container_code(form.get("code", ""))
        if new_code != node["code"]:
            repo.assign_code(conn, node_id, new_code)
        parent = form.get("parent_id", "")
        new_parent = int(parent) if parent.isdigit() else None
        if new_parent != node["parent_id"]:
            repo.move_container(conn, node_id, new_parent)
        return redirect(f"/n/{node_id}", "Gespeichert")

    @app.post("/n/{node_id}/edit")
    def edit_container(
        node_id: int,
        conn: Conn,
        name: Annotated[str, Form()],
        notes: Annotated[str, Form()] = "",
        code: Annotated[str, Form()] = "",
        tare: Annotated[str, Form()] = "",
    ) -> RedirectResponse:
        node = need_node(conn, node_id)
        repo.update_container(conn, node_id, name, notes)
        repo.set_container_tare(conn, node_id, tare)
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

    @app.post("/n/{node_id}/photo")
    async def container_photo(node_id: int, conn: Conn, photo: UploadFile) -> RedirectResponse:
        old = need_node(conn, node_id)["photo"]
        name = photos.save(await photo.read(), photo_dir)
        repo.set_container_photo(conn, node_id, name)
        photos.delete(old, photo_dir)
        return redirect(f"/n/{node_id}", "Foto gespeichert")

    # --- Umlagern: aufnehmen (Cookie), am Ziel-Behälter ablegen -----------------------------

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

    # --- Baum -------------------------------------------------------------------------------

    def branch(request: Request, conn: sqlite3.Connection, node_id: int | None) -> HTMLResponse:
        kids = repo.children(conn, node_id)
        items = repo.items_in(conn, node_id) if node_id else []
        return render(request, conn, "_branch.html", kids=kids, items=items)

    @app.get("/baum", response_class=HTMLResponse)
    def tree_page(request: Request, conn: Conn) -> HTMLResponse:
        return render(request, conn, "baum.html", kids=repo.children(conn, None))

    @app.get("/n/{node_id}/zweig", response_class=HTMLResponse)
    def tree_branch(request: Request, node_id: int, conn: Conn) -> HTMLResponse:
        return branch(request, conn, node_id)

    # --- Auswahl und Massenbearbeitung ------------------------------------------------------

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
            found, _ = finder.run(conn, q, syn, limit=200, tag=int(tag) if tag.isdigit() else None)
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
            field_opts=catalog.field_choices(),
            tags=itemtypes.all_types(conn), cats=kinds.ITEM_CATS,
            back=request.url.path + ("?" + request.url.query if request.url.query else ""),
        )  # fmt: skip

    @app.post("/bulk")
    async def bulk_apply(request: Request, conn: Conn) -> RedirectResponse:
        form = await request.form()
        refs = [str(v) for v in form.getlist("ref")]
        back = safe_back(str(form.get("back", "/auswahl")), "/auswahl")
        value = str(form.get("value", ""))
        if form.get("action") == "field":
            value = f"{form.get('field', '')}={value}"
        msg = bulk.apply(
            conn, refs, str(form.get("action", "")),
            value=value, target=str(form.get("target", "")),
        )  # fmt: skip
        return redirect(back, msg)
