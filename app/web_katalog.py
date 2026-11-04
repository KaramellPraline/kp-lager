"""Routen: Teile-Katalog („Anlegen“), Einsatz-Assistent (Sortierkasten) und Baumansicht."""

import re
import sqlite3
from collections import Counter
from collections.abc import Callable
from typing import Annotated, Any

from fastapi import Depends, FastAPI, Request
from fastapi.responses import HTMLResponse, JSONResponse, RedirectResponse, Response

from app import (
    cards,
    catalog,
    codes,
    d30,
    kasten,
    labelimg,
    labels,
    presets,
    repo,
    typesettings,
)
from app.config import Settings
from app.repo import LagerError

TARGET_COOKIE = "qa_targets"  # gleiche Liste wie die Schnelleingabe auf der Startseite
TYPE_COOKIE = "kat_typ"
# Druckmodus beim Anlegen: (Schlüssel, Name, Erklärung)
PRINT_MODES = {
    "aus": ("Aus", "nichts automatisch drucken"),
    "einzel": ("Einzeln", "jedes neue Teil sofort auf den D30 (40x12)"),
    "sammel": ("Sammeln", "neue Etiketten in die Warteschlange, später gemeinsam drucken"),
}
QTYS = ("10", "25", "50", "100", "200", "500")


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
    def targets_cookie(request: Request) -> list[int]:
        return [int(x) for x in request.cookies.get(TARGET_COOKIE, "").split(",") if x.isdigit()]

    def remember_target(resp: RedirectResponse, request: Request, target: int) -> None:
        ids = [target] + [i for i in targets_cookie(request) if i != target]
        resp.set_cookie(
            TARGET_COOKIE, ",".join(map(str, ids[:3])), max_age=31_536_000, samesite="lax"
        )

    def print_now(conn: sqlite3.Connection, codes_: list[str]) -> str:
        try:
            n = d30.print_codes(conn, settings.base_url, codes_)
        except (
            LagerError
        ) as exc:  # Druck gescheitert (Agent/MQTT/D30): automatisch in die Warteschlange
            return f" · Druck nicht möglich ({exc}) –" + print_set_queue(conn, codes_)
        return f" · {n} Etikett{'en' if n != 1 else ''} gedruckt"

    def print_set_queue(conn: sqlite3.Connection, codes_: list[str]) -> str:
        for code in codes_:
            item = repo.get_item_by_code(conn, code)
            if item is not None:
                lab = labels.item_label(conn, settings.base_url, item)
                labels.enqueue(conn, lab.code, lab.text, lab.extra)
        return f" · {len(codes_)} in der Druck-Warteschlange"

    def print_set(conn: sqlite3.Connection, codes_: list[str]) -> str:
        """Etikett-Satz: alle auf einmal auf den D30, bei Fehler alle in die Warteschlange."""
        if not settings.d30:
            return print_set_queue(conn, codes_)
        try:
            n = d30.print_codes(conn, settings.base_url, codes_)
        except LagerError as exc:
            return f" · Druck nicht möglich ({exc})" + print_set_queue(conn, codes_)
        return f" · {n} Etikett{'en' if n != 1 else ''} gedruckt"

    # --- Katalog ---------------------------------------------------------------------

    @app.get("/neu", response_class=HTMLResponse)
    def katalog_page(
        request: Request, conn: Conn, typ: str = "", vorlage: str = "", draft: str = ""
    ) -> HTMLResponse:
        key = typ or request.cookies.get(TYPE_COOKIE, "") or "schraube"
        current = catalog.lookup(conn, key) or catalog.BY_KEY["schraube"]
        kept = typesettings.kept_values(conn, current.key)
        required = typesettings.required_keys(conn, current.key)
        last_row = conn.execute(
            "SELECT * FROM item WHERE ctype = ? ORDER BY id DESC LIMIT 1", (current.key,)
        ).fetchone()
        last_vals = catalog.values_of(last_row) if last_row else {}
        base = repo.get_item(conn, int(vorlage)) if vorlage.isdigit() else None
        prefill = catalog.values_of(base) if base else dict(kept)
        last = targets_cookie(request)
        recent = conn.execute(
            "SELECT i.id, i.name, i.code, i.qty, c.name AS place FROM item i"
            " JOIN container c ON c.id = i.container_id ORDER BY i.id DESC LIMIT 6"
        ).fetchall()
        return render(
            request,
            conn,
            "katalog.html",
            groups=catalog.grouped(conn),
            favs=catalog.favorite_keys(conn),
            print_mode=print_mode(conn),
            print_modes=PRINT_MODES,
            ctype=current,
            prefill=prefill,
            kept=kept,
            last_vals=last_vals,
            required=required,
            sections={
                "required": catalog.field_rows([f for f in current.fields if f.key in required]),
                "optional": catalog.field_rows(
                    [f for f in current.fields if f.key not in required and not f.extra]
                ),
                "extra": catalog.field_rows(
                    [f for f in current.fields if f.key not in required and f.extra]
                ),
            },
            presets=presets.all_for(conn, current.key),
            opts={f.key: catalog.options_for(conn, f, current) for f in current.fields},
            draft=bool(draft),
            series_fields=[f for f in current.fields if catalog.options_for(conn, f, current)],
            targets=repo.all_paths(conn),
            target=last[0] if last else None,
            recent_targets=[
                {"id": p["id"], "label": repo.path_label(conn, p["id"])}
                for p in repo.containers_by_ids(conn, last)[:3]
            ],
            fav_targets=[
                {"id": f["id"], "label": repo.path_label(conn, f["id"])}
                for f in repo.favorites(conn)[:10]
            ],
            recent=recent,
        )

    @app.post("/neu/favorit")
    def katalog_favorite(conn: Conn, form: Form) -> RedirectResponse:
        key = form.get("typ", "")
        if catalog.lookup(conn, key):
            catalog.toggle_favorite(conn, key)
        return RedirectResponse(f"/neu?typ={key}", status_code=303)

    def print_mode(conn: Conn) -> str:
        mode = codes.get_setting(conn, "print_mode", "")
        if mode in PRINT_MODES:
            return mode
        return "einzel" if codes.get_setting(conn, "auto_print", "0") == "1" else "aus"

    @app.post("/neu/druckmodus")
    def katalog_print_mode(conn: Conn, form: Form) -> RedirectResponse:
        mode = form.get("mode", "aus")
        codes.set_setting(conn, "print_mode", mode if mode in PRINT_MODES else "aus")
        return RedirectResponse(form.get("back", "/neu"), status_code=303)

    @app.post("/neu/autodruck")  # alt: an/aus -> Einzel/Aus
    def katalog_auto_print(conn: Conn, form: Form) -> RedirectResponse:
        codes.set_setting(conn, "print_mode", "einzel" if form.get("on") == "1" else "aus")
        return RedirectResponse(form.get("back", "/neu"), status_code=303)

    @app.post("/neu/preset")
    def katalog_preset_save(conn: Conn, form: Form) -> RedirectResponse:
        t = catalog.lookup(conn, form.get("typ", ""))
        if t is None:
            raise LagerError("Bitte einen Teile-Typ wählen")
        values = {f.key: catalog.number(form.get(f"f_{f.key}", "")) for f in t.fields}
        presets.save(conn, t.key, form.get("preset_name", ""), values)
        catalog.remember_brand(conn, t, values.get("brand", ""))
        return redirect(
            f"/neu?typ={t.key}&draft=1", f"Preset „{form['preset_name'].strip()}“ gespeichert"
        )

    @app.post("/neu/preset/{preset_id}/loeschen")
    def katalog_preset_delete(preset_id: int, conn: Conn, form: Form) -> RedirectResponse:
        presets.delete(conn, preset_id)
        return redirect(f"/neu?typ={form.get('typ', '')}&draft=1", "Preset gelöscht")

    @app.post("/neu/pflicht")
    def katalog_required(conn: Conn, form: Form) -> RedirectResponse:
        t = catalog.lookup(conn, form.get("typ", ""))
        if t is None:
            raise LagerError("Bitte einen Teile-Typ wählen")
        keys = [f.key for f in t.fields if form.get(f"req_{f.key}")]
        typesettings.save_required(conn, t.key, keys)
        return redirect(f"/neu?typ={t.key}&draft=1", "Pflichtfelder gespeichert")

    @app.post("/neu/satz")
    def katalog_print_set(conn: Conn, form: Form) -> RedirectResponse:
        """Etikett-Satz: die zuletzt angelegten Teile gemeinsam drucken."""
        ids = [int(x) for x in form.get("ids", "").split(",") if x.isdigit()]
        found = [repo.get_item(conn, i) for i in ids]
        codes_ = [i["code"] for i in found if i["code"]]
        if not codes_:
            raise LagerError("Keine Etiketten zum Drucken")
        return redirect(f"/neu?typ={form.get('typ', '')}", "Satz" + print_set(conn, codes_))

    @app.get("/neu/etikett.png")
    def katalog_label_png(request: Request, typ: str, conn: Conn) -> Response:
        """Live-Vorschau des Etiketts aus den aktuellen Formularwerten (noch nicht angelegt)."""
        t = catalog.lookup(conn, typ)
        if t is None:
            raise LagerError("Unbekannter Teile-Typ")
        vals = {f.key: request.query_params.get(f"f_{f.key}", "").strip() for f in t.fields}
        vals = catalog.derive(t, vals)
        code = codes.format_code(t.cat, codes.next_number(conn, t.cat))
        vals.update({k: "" for k, _ in labels.EXTRA_FIELDS})
        vals.update({"name": catalog.name(t, vals) or t.label, "code": code, "ort": ""})
        stored = typesettings.get(conn, t.key).get("label_layout") or ""
        layout = labels.parse_layout(stored or catalog.default_label_layout(t))
        label = labels.Label(
            code, labels.qr_content(settings.base_url, code), vals["name"], "",
            labels.layout_lines(layout, vals), str(layout["qr"]),
        )  # fmt: skip
        return Response(labelimg.png(label), media_type="image/png",
                        headers={"Cache-Control": "no-store"})  # fmt: skip

    @app.post("/settings/admin/nodetypen")
    def admin_node_types(conn: Conn, form: Form) -> RedirectResponse:
        lines = [x.strip() for x in form.get("node_types", "").splitlines() if x.strip()]
        codes.set_setting(conn, "node_types", "\n".join(dict.fromkeys(lines)))
        return redirect("/settings/admin#nodetypen", "Node-Typen gespeichert")

    @app.get("/neu/vorschau")
    def katalog_preview(request: Request, typ: str, conn: Conn) -> JSONResponse:
        t = catalog.lookup(conn, typ)
        if t is None:
            return JSONResponse({"name": ""})
        values = {f.key: request.query_params.get(f"f_{f.key}", "") for f in t.fields}
        return JSONResponse({"name": catalog.name(t, values)})

    @app.post("/neu")
    def katalog_create(request: Request, conn: Conn, form: Form) -> Response:
        typ = form.get("typ", "")
        t = catalog.lookup(conn, typ)
        if t is None:
            raise LagerError("Bitte einen Teile-Typ wählen")
        target = int(form["target"]) if form.get("target", "").isdigit() else repo.inbox(conn)
        qty = int(form["qty"]) if form.get("qty", "").strip().isdigit() else None
        values = {f.key: catalog.number(form.get(f"f_{f.key}", "")) for f in t.fields}
        if form.get("keeps"):  # „merken“: diese Werte sind beim nächsten Mal vorbelegt
            typesettings.save_kept(
                conn, t.key,
                {f.key: values[f.key].strip() for f in t.fields if form.get(f"keep_{f.key}")},
            )  # fmt: skip
        series_key = form.get("series_field", "")
        series = [v.strip() for v in re.split(r"[,;\n]+", form.get("series_values", ""))]
        series = [v for v in series if v] if series_key in values else []
        required = typesettings.required_keys(conn, t.key)
        missing = [
            f.label for f in t.fields
            if f.key in required and not values[f.key].strip()
            and not (series and f.key == series_key)
        ]  # fmt: skip
        if missing:
            raise LagerError("Pflichtfeld fehlt: " + ", ".join(missing))
        single = t.single or bool(form.get("single"))  # Einzelteile: jedes Stück eigenes Teil
        copies = qty if single and qty and qty > 1 else 1
        if single:
            qty = 1
        mode = print_mode(conn)  # Regel: einzel = sofort 40x12, sammel = in die Warteschlange
        wants_print = bool(form.get("d30_print") or mode == "einzel") and bool(settings.d30)
        note = form.get("note", "").strip()

        def add_note(item_id: int) -> None:
            if note:  # optionale Karte: Links -> Linkkarte, sonst Notiz
                is_link = note.startswith(("http://", "https://"))
                cards.add(conn, "Links" if is_link else "Notiz", note,
                          "link" if is_link else "note", item_id=item_id)  # fmt: skip

        if series or copies > 1:  # Reihe/Einzelteile: je Stück ein Teil, Etiketten als Satz
            made_codes: list[str] = []
            names: list[str] = []
            for v in series or [""]:
                for _ in range(copies):
                    item_id = catalog.create(
                        conn, typ, {**values, series_key: v} if v else values, target, qty,
                        standalone=not form.get("no_label"),
                    )  # fmt: skip
                    add_note(item_id)
                    row = repo.get_item(conn, item_id)
                    names.append(row["name"])
                    if row["code"]:
                        made_codes.append(row["code"])
            counted = ", ".join(f"{n}× {x}" if n > 1 else x for x, n in Counter(names).items())
            msg = f"{len(names)} Teile angelegt: {counted}"
            if made_codes and wants_print:
                msg += print_set(conn, made_codes)
            elif made_codes and mode == "sammel":
                msg += print_set_queue(conn, made_codes)
            resp = redirect(f"/neu?typ={typ}", msg)
            resp.set_cookie(TYPE_COOKIE, typ, max_age=31_536_000, samesite="lax")
            remember_target(resp, request, target)
            return resp
        dupes = [] if form.get("force") or single else catalog.duplicates(conn, typ, values)
        if dupes:  # gibt es schon: Menge dort erhöhen statt doppelt anlegen
            return render(
                request, conn, "neu_dublette.html", ctype=t, form=form, qty=qty,
                dname=catalog.name(t, values),
                dupes=[
                    {**dict(d), "path": repo.path_label(conn, d["container_id"])} for d in dupes
                ],
            )  # fmt: skip
        item_id = catalog.create(
            conn, typ, values, target, qty, standalone=not form.get("no_label")
        )
        item = repo.get_item(conn, item_id)
        add_note(item_id)
        msg = f"„{item['name']}“ angelegt ({item['code'] or 'ohne Etikett'})"
        if item["code"]:
            if wants_print:
                msg += print_now(conn, [item["code"]])
            elif mode == "sammel":
                label = labels.item_label(conn, settings.base_url, item)
                labels.enqueue(conn, label.code, label.text, label.extra)
                msg += " · in der Druck-Warteschlange"
        # gleicher Typ nochmal, Felder zurückgesetzt (Ziel bleibt)
        resp = redirect(f"/neu?typ={typ}", msg)
        resp.set_cookie(TYPE_COOKIE, typ, max_age=31_536_000, samesite="lax")
        remember_target(resp, request, target)
        return resp

    @app.post("/neu/dublette/{item_id}")
    def katalog_add_to_existing(item_id: int, conn: Conn, form: Form) -> RedirectResponse:
        item = repo.get_item(conn, item_id)
        qty = int(form["qty"]) if form.get("qty", "").strip().isdigit() else 0
        if qty and item["qty"] is not None:
            repo.change_qty(conn, item_id, qty, note="Nachgelegt (Hinzufügen)")
            msg = f"„{item['name']}“: +{qty} → {item['qty'] + qty}"
        elif qty:
            repo.update_item(conn, item_id, qty=qty)
            msg = f"„{item['name']}“: jetzt {qty} gezählt"
        else:
            msg = f"„{item['name']}“ gibt es schon – nichts geändert"
        return redirect(
            f"/neu?typ={item['ctype'] or ''}", msg, repo.last_event_id(conn) if qty else None
        )

    # --- Einsatz-Assistent ----------------------------------------------------------------

    @app.get("/neu/bin", response_class=HTMLResponse)
    def bin_page(request: Request, conn: Conn, kasten_id: int = 0) -> HTMLResponse:
        boxes = conn.execute(
            "SELECT * FROM container WHERE kind = 'sortingbox' AND model IS NOT NULL ORDER BY name"
        ).fetchall()
        info = {}
        for b in boxes:
            model = kasten.model_of(b)
            info[b["id"]] = {
                "free": kasten.free_cells(conn, b),
                "cols": model.cols if model else 0,
                "rows": model.rows if model else 0,
            }
        cur = kasten_id or (boxes[0]["id"] if boxes else 0)
        return render(
            request,
            conn,
            "bin_assistent.html",
            boxes=boxes,
            info=info,
            kcur=cur,
            divs=kasten.DIVS,
            quick=catalog.quick_options(),
            sugg=catalog.suggestions(),
            qtys=QTYS,
        )

    @app.post("/neu/bin")
    def bin_create(request: Request, conn: Conn, form: Form) -> RedirectResponse:
        if not form.get("kasten", "").isdigit():
            raise LagerError("Bitte einen Sortierkasten wählen")
        kid = int(form["kasten"])
        size = f"{form.get('x', '1')}x{form.get('y', '1')}"
        div = form.get("div", "1x1")
        bin_id = kasten.place_bin(conn, kid, form.get("pos", ""), size, div)
        comps = conn.execute(
            "SELECT id FROM container WHERE parent_id = ? ORDER BY id", (bin_id,)
        ).fetchall()
        slots = [c["id"] for c in comps] or [bin_id]
        made = 0
        for i, slot in enumerate(slots):
            typ, _, art = form.get(f"r{i}_typ", "").partition("|")
            if not typ:
                continue
            qty_raw = form.get(f"r{i}_qty", "")
            catalog.create_quick(
                conn, typ, art, form.get(f"r{i}_var", "").strip(), slot,
                int(qty_raw) if qty_raw.isdigit() else None,
            )  # fmt: skip
            made += 1
        node = repo.get_container(conn, bin_id)
        assert node is not None
        if form.get("unprinted"):
            note = "Einsatz noch nicht gedruckt"
            notes = f"{node['notes']}\n{note}".strip()
            repo.update_container(conn, bin_id, node["name"], notes)
        if form.get("content"):
            labels.enqueue_content(conn, node)
        if form.get("queue"):
            labels.enqueue(conn, node["code"], *labels.container_label(conn, node))
        msg = (
            f"Einsatz {node['code']} bei {node['position']} ({size}, "
            f"{len(comps) or 1} {'Fächer' if len(comps) > 1 else 'Fach'}) angelegt, {made} Teile"
        )
        if form.get("d30_print") and settings.d30:
            msg += print_now(conn, [node["code"]])
        resp = redirect(f"/neu/bin?kasten_id={kid}", msg)
        return resp

    # --- Baumansicht ------------------------------------------------------------------------

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
