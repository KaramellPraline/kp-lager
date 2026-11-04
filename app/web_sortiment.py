"""Routen: Sortiment nach Typ (Filter, Variantenraster), eigene Typen, Altbestand zuordnen,
Typ-Datenblatt am Teil."""

import json
from collections.abc import Callable
from typing import Annotated, Any

from fastapi import Depends, FastAPI, Request
from fastapi.responses import HTMLResponse, RedirectResponse, Response

from app import catalog, kinds, labelimg, labels, repo, sortiment, typesettings
from app.config import Settings


async def form_fields(request: Request) -> dict[str, str]:
    form = await request.form()
    return {k: v for k, v in form.items() if isinstance(v, str)}


async def form_lists(request: Request) -> dict[str, list[str]]:
    form = await request.form()
    out: dict[str, list[str]] = {}
    for k, v in form.multi_items():
        if isinstance(v, str):
            out.setdefault(k, []).append(v)
    return out


Form = Annotated[dict[str, str], Depends(form_fields)]
Lists = Annotated[dict[str, list[str]], Depends(form_lists)]


def register(
    app: FastAPI,
    Conn: Any,
    render: Callable[..., HTMLResponse],
    redirect: Callable[..., RedirectResponse],
    settings: Settings,
) -> None:
    # --- Übersicht und Typ-Seite ---------------------------------------------------------

    @app.get("/sortiment", response_class=HTMLResponse)
    def sortiment_page(request: Request, conn: Conn) -> HTMLResponse:
        n = sortiment.counts(conn)
        groups: dict[str, list[tuple[sortiment.Kind, int]]] = {}
        for k in sortiment.kinds(conn):
            groups.setdefault(k.group, []).append((k, n.get(k.key, 0)))
        return render(
            request, conn, "sortiment.html",
            groups=list(groups.items()), n_untyped=sortiment.count_untyped(conn),
        )  # fmt: skip

    @app.get("/sortiment/eigene", response_class=HTMLResponse)
    def custom_page(request: Request, conn: Conn, key: str = "") -> HTMLResponse:
        current = catalog.lookup(conn, key) if key else None
        return render(
            request, conn, "sortiment_eigene.html",
            types=catalog.custom_types(conn), current=current,
            lines=catalog.field_lines(current) if current else "",
            cats=kinds.ITEM_CATS, counts=sortiment.counts(conn),
        )  # fmt: skip

    @app.post("/sortiment/eigene")
    def custom_save(conn: Conn, form: Form) -> RedirectResponse:
        key = catalog.save_custom(
            conn, form.get("label", ""), form.get("fields", ""), form.get("cat", "ART"),
            form.get("group", ""), form.get("name_tpl", ""), form.get("key", ""),
        )  # fmt: skip
        return redirect(f"/neu?typ={key}", "Typ gespeichert – hier gleich ein Teil anlegen")

    @app.post("/sortiment/eigene/{key}/delete")
    def custom_delete(key: str, conn: Conn) -> RedirectResponse:
        n = catalog.delete_custom(conn, key)
        return redirect("/sortiment/eigene", f"Typ gelöscht ({n} Teile ohne Typ)")

    @app.get("/sortiment/zuordnen", response_class=HTMLResponse)
    def assign_page(request: Request, conn: Conn) -> HTMLResponse:
        rows = sortiment.untyped(conn)
        return render(
            request, conn, "sortiment_zuordnen.html",
            rows=rows, total=sortiment.count_untyped(conn), groups=catalog.grouped(conn),
            label={t.key: t.label for _, ts in catalog.grouped(conn) for t in ts},
        )  # fmt: skip

    @app.post("/sortiment/zuordnen")
    def assign_apply(conn: Conn, lists: Lists) -> RedirectResponse:
        rename = bool(lists.get("rename"))
        done = 0
        for raw in lists.get("sel", []):
            if not raw.isdigit():
                continue
            key = (lists.get(f"typ_{raw}") or [""])[0]
            if not key:
                continue
            try:
                vals = json.loads((lists.get(f"vals_{raw}") or ["{}"])[0])
            except ValueError:
                vals = {}
            catalog.set_fields(conn, int(raw), key, vals if isinstance(vals, dict) else {}, rename)
            done += 1
        return redirect("/sortiment/zuordnen", f"{done} Teile zugeordnet")

    @app.get("/sortiment/{key}", response_class=HTMLResponse)
    def kind_page(request: Request, key: str, conn: Conn) -> HTMLResponse:
        k = sortiment.kind(conn, key)
        q = request.query_params
        filters = {f: q.get(f"f_{f}", "") for f, _, _ in k.fields if q.get(f"f_{f}")}
        all_rows = sortiment.items(conn, k)
        rows = sortiment.items(conn, k, filters) if filters else all_rows
        row_f, col_f = sortiment.default_axes(k, rows)
        row_f = q.get("row") or row_f
        col_f = q.get("col", col_f)
        grid = sortiment.raster(rows, row_f, col_f) if q.get("ansicht") == "raster" else None
        return render(
            request, conn, "sortiment_typ.html",
            kind=k, rows=rows, facets=sortiment.facets(k, all_rows), filters=filters,
            grid=grid, row_f=row_f, col_f=col_f, labels={f: lb for f, lb, _ in k.fields},
            custom=key.startswith("c_"), tset=typesettings.get(conn, key),
        )  # fmt: skip

    # --- Etiketten-Layout je Typ -----------------------------------------------------------

    def sample(conn: Any, k: sortiment.Kind) -> tuple[dict[str, str], str]:
        """Beispielwerte für die Vorschau: ein echtes Teil dieses Typs, sonst Platzhalter."""
        rows = sortiment.items(conn, k)
        if rows:
            item = repo.get_item(conn, rows[0]["id"])
            return labels.item_values(conn, item), item["code"] or "ART-0001"
        values = {key: label for key, label, _ in k.fields}
        values.update({"name": k.label, "code": "ART-0001", "ort": "Kiste 1"})
        for f, lb in labels.EXTRA_FIELDS:
            values.setdefault(f, lb)
        return values, "ART-0001"

    def layout_from(raw: dict[str, str] | Any) -> labels.Layout:
        lines = []
        for i in range(labels.MAX_LINES):
            if raw.get(f"t_{i}", "").strip():
                lines.append({"t": raw.get(f"t_{i}", ""), "w": raw.get(f"w_{i}", "1"),
                              "a": raw.get(f"a_{i}", "center")})  # fmt: skip
        return labels.parse_layout({"qr": raw.get("qr", "left"), "lines": lines})

    @app.get("/etiketten/typ", response_class=HTMLResponse)
    def label_types(request: Request, conn: Conn) -> HTMLResponse:
        n = sortiment.counts(conn)
        groups: dict[str, list[tuple[sortiment.Kind, int, bool]]] = {}
        for k in sortiment.kinds(conn):
            custom = bool(typesettings.get(conn, k.key).get("label_layout"))
            groups.setdefault(k.group, []).append((k, n.get(k.key, 0), custom))
        return render(request, conn, "etiketten_typen.html", groups=list(groups.items()))

    @app.get("/etiketten/typ/{key}", response_class=HTMLResponse)
    def label_designer(request: Request, key: str, conn: Conn) -> HTMLResponse:
        k = sortiment.kind(conn, key)
        stored = typesettings.get(conn, key).get("label_layout") or ""
        layout = labels.parse_layout(stored)
        values, code = sample(conn, k)
        fields = [(f"{{{f}}}", lb) for f, lb, _ in k.fields]
        have = {f for f, _, _ in k.fields}
        fields += [(f"{{{f}}}", lb) for f, lb in labels.EXTRA_FIELDS if f not in have]
        return render(
            request, conn, "etiketten_layout.html", kind=k, layout=layout, custom=bool(stored),
            fields=fields, max_lines=labels.MAX_LINES, sample_code=code, presets=labels.PRESETS,
            preview=[(t, w, a) for t, w, a in labels.layout_lines(layout, values)],
        )  # fmt: skip

    @app.get("/etiketten/typ/{key}/vorschau.png")
    def label_preview(request: Request, key: str, conn: Conn) -> Response:
        k = sortiment.kind(conn, key)
        params = request.query_params
        if "qr" in params or any(p.startswith("t_") for p in params):
            layout = layout_from(params)
        else:  # Seite frisch geladen (z. B. nach dem Speichern): gespeichertes Layout zeigen
            layout = labels.parse_layout(typesettings.get(conn, key).get("label_layout") or "")
        values, code = sample(conn, k)
        label = labels.Label(
            code, labels.qr_content(settings.base_url, code), values.get("name", ""), "",
            labels.layout_lines(layout, values), str(layout["qr"]),
        )  # fmt: skip
        return Response(labelimg.png(label), media_type="image/png",
                        headers={"Cache-Control": "no-store"})  # fmt: skip

    @app.post("/etiketten/typ/{key}")
    def label_layout_save(key: str, conn: Conn, form: Form) -> RedirectResponse:
        sortiment.kind(conn, key)
        if form.get("reset"):
            typesettings.save_layout(conn, key, None)
            return redirect(f"/etiketten/typ/{key}", "Standard-Layout wiederhergestellt")
        if form.get("all"):
            lay = layout_from(form)
            for k in sortiment.kinds(conn):
                typesettings.save_layout(conn, k.key, lay)
            return redirect(f"/etiketten/typ/{key}", "Layout für alle Typen übernommen")
        typesettings.save_layout(conn, key, layout_from(form))
        return redirect(
            f"/etiketten/typ/{key}", "Layout gespeichert – gilt für neue Etiketten dieses Typs"
        )

    # --- Typ am Teil ---------------------------------------------------------------------

    @app.post("/items/{item_id}/typ")
    def item_type(item_id: int, conn: Conn, form: Form) -> RedirectResponse:
        repo.get_item(conn, item_id)
        key = form.get("typ", "")
        values = {k[2:]: v for k, v in form.items() if k.startswith("f_")}
        if not key:
            with conn:
                conn.execute("UPDATE item SET ctype = NULL WHERE id = ?", (item_id,))
            return redirect(f"/items/{item_id}#typ", "Typ entfernt")
        new_name = catalog.set_fields(conn, item_id, key, values, bool(form.get("rename")))
        msg = f"Typ gespeichert{' · Name: ' + new_name if form.get('rename') and new_name else ''}"
        return redirect(f"/items/{item_id}#typ", msg)
