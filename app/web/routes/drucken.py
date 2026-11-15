"""Drucken: Etiketten-Übersicht, Vorschau/Export, Warteschlange, Inhaltsetiketten,
Schnelldruck, D30-Direktdruck/PC-Bridge, Druck wiederholen und Etikett-Layout je Typ."""

from typing import Annotated, Any

from fastapi import FastAPI, Form, HTTPException, Request
from fastapi.responses import HTMLResponse, JSONResponse, RedirectResponse, Response

from app import a4, codes, d30, kasten, labelimg, labels, prefs, repo, sortiment, typesettings
from app.repo import LagerError
from app.web.shared import (
    BRIDGE_END,
    BRIDGE_MARK,
    Conn,
    Ctx,
    FormDict,
    need_node,
    redirect,
    safe_back,
)


def register(app: FastAPI, ctx: Ctx) -> None:
    settings = ctx.settings
    render = ctx.render
    print_or_queue = ctx.print_or_queue

    # --- Etiketten: Übersicht, Vorschau, Export ---------------------------------------------

    @app.get("/labels/img/{code}.png")
    def label_image(code: str, conn: Conn) -> Response:
        """Etikett 40×12 mm als Bild (320×96 px) – für den Direktdruck und zum Prüfen."""
        label = labels.find(conn, settings.base_url, code)
        if label is None:
            raise HTTPException(404, "Kein Etikett mit diesem Code")
        return Response(labelimg.png(label), media_type="image/png")

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
            content=labels.content_queue(conn),
            a4_count=a4.count(conn),
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
        entries_ = list(zip(code, text, extra, strict=True))
        bridge = fmt == "d30" and ctx.bridge_only(conn)
        if fmt == "d30" and not bridge:  # erst drucken – nur Gedrucktes wird als gedruckt gebucht
            if not ctx.d30_on(conn):
                raise LagerError("Direktdruck ist abgeschaltet (LAGER_D30=1)")
            try:
                d30.print_labels(
                    [
                        labels.Label(
                            c, labels.qr_content(settings.base_url, c), t.strip(), e.strip()
                        )
                        for raw, t, e in entries_
                        if (c := codes.normalize(raw))
                    ]
                )
            except LagerError as exc:  # Druck gescheitert: automatisch in die Warteschlange
                queued = [
                    (c, t.strip(), e.strip())
                    for raw, t, e in entries_
                    if (c := codes.normalize(raw))
                ]
                for c, t, e in queued:
                    labels.enqueue(conn, c, t, e)
                return redirect(
                    "/labels",
                    f"Druck nicht möglich ({exc}) – {len(queued)} Etikett(en) in der Warteschlange",
                )
        rows = labels.finalize(conn, settings.base_url, entries_, bool(save_names))
        if not rows:
            raise LagerError("Keine gültigen Codes")
        if fmt == "queue":  # nur merken (z. B. für später oder den XLSX-Export)
            for r in rows:
                labels.enqueue(conn, r.code, r.text, r.extra)
            with conn:
                conn.executemany(
                    "UPDATE container SET label_printed = 0 WHERE code = ?",
                    [(r.code,) for r in rows],
                )
                conn.executemany(
                    "UPDATE item SET label_printed = 0 WHERE code = ?", [(r.code,) for r in rows]
                )
            return redirect("/labels", f"{len(rows)} Etikett(en) in der Warteschlange")
        if source == "queue":
            labels.dequeue(conn, [r.code for r in rows])
        if bridge:
            marker = f"{BRIDGE_MARK}{','.join(r.code for r in rows)}{BRIDGE_END}"
            return redirect("/labels", f"{len(rows)} Etikett(en) an die PC-Bridge gesendet{marker}")
        if fmt == "d30":
            return redirect("/labels", f"{len(rows)} Etikett(en) auf dem D30 gedruckt")
        if fmt == "a4q":  # A4 nie automatisch: in die A4-Warteschlange legen
            for r in rows:
                tag = {"type": "tag", "title": r.text, "code": r.code, "qr": r.qr}
                a4.enqueue(conn, {**tag, "lines": [r.extra] if r.extra else []})
            return redirect("/a4", f"{len(rows)} Etikett(en) in der A4-Warteschlange")
        raise LagerError(
            "Bitte „Auf D30 drucken“, „In Warteschlange“ oder „A4-Warteschlange“ wählen"
        )

    # --- Druck wiederholen (Verlauf) --------------------------------------------------------

    @app.post("/druck/wiederholen")
    async def print_repeat(request: Request, conn: Conn) -> RedirectResponse:
        """Druckaufträge aus dem Verlauf erneut drucken (ein Auftrag oder mehrere als Batch)."""
        form = await request.form()
        ids = [int(v) for v in form.getlist("job") if isinstance(v, str) and v.isdigit()]
        marks = ",".join("?" * len(ids))
        rows = conn.execute(f"SELECT codes FROM label_job WHERE id IN ({marks})", ids).fetchall()
        wanted = list(dict.fromkeys(c for r in rows for c in r["codes"].split()))
        if not wanted:
            raise LagerError("Keinen Auftrag gewählt")
        n = d30.print_codes(conn, settings.base_url, wanted)
        return redirect(
            "/verlauf?tab=druck", f"{n} Etikett{'en' if n != 1 else ''} erneut gedruckt"
        )

    # --- Warteschlange und Inhaltsetiketten -------------------------------------------------

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
            labels.enqueue_content(conn, b)
            n += 1
        return redirect(f"/n/{node_id}", f"{n} Bin-Tags + Inhaltsetiketten vorgemerkt")

    @app.post("/labels/content/node/{node_id}")
    def content_node(request: Request, node_id: int, conn: Conn) -> RedirectResponse:
        node = need_node(conn, node_id)
        labels.enqueue_content(conn, node)
        back = request.headers.get("referer", f"/n/{node_id}").split("?")[0]
        return redirect(back, f"Inhaltsetikett {labels.content_title(conn, node)} vorgemerkt")

    @app.post("/labels/content/a4q")
    def content_to_a4(conn: Conn) -> RedirectResponse:
        """Inhaltsetiketten (Bins/Fächer) als Seitenetiketten in die A4-Warteschlange."""
        n = 0
        for row in labels.content_queue(conn):
            node = repo.get_container(conn, int(row["id"]))  # type: ignore[call-overload]
            if node is None:
                continue
            if node["kind"] == "bin":
                a4.enqueue(conn, a4.job_bin_side(conn, node))
            else:
                job = {"type": "content", "title": row["title"], "color": "red"}
                a4.enqueue(conn, {**job, "lines": [str(row["text"])]})
            n += 1
        labels.clear_content(conn)
        return redirect("/a4", f"{n} Seitenetiketten in der A4-Warteschlange")

    @app.post("/labels/content/clear")
    def content_clear(conn: Conn) -> RedirectResponse:
        labels.clear_content(conn)
        return redirect("/labels", "Inhaltsetiketten geleert")

    # --- Schnelldruck -----------------------------------------------------------------------

    @app.post("/labels/quick/node/{node_id}")
    def quick_print_node(node_id: int, conn: Conn) -> RedirectResponse:
        node = need_node(conn, node_id)
        if not node["code"]:
            raise LagerError("Behälter hat noch keinen Code")
        return print_or_queue(
            conn, node["code"], *labels.container_label(conn, node), f"/n/{node_id}"
        )

    @app.post("/labels/quick/item/{item_id}")
    def quick_print_item(item_id: int, conn: Conn) -> RedirectResponse:
        item = repo.get_item(conn, item_id)
        if not item["code"]:
            raise LagerError("Teil hat noch keinen Code")
        lab = labels.item_label(conn, settings.base_url, item)
        return print_or_queue(conn, lab.code, lab.text, lab.extra, f"/items/{item_id}")

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

    # --- Sammeletikett ----------------------------------------------------------------------

    @app.post("/labels/sammel/{node_id}")
    def collect_labels(node_id: int, conn: Conn) -> RedirectResponse:
        """Sammeldruck: alle ungedruckten Etiketten der Box (inkl. Unterbehälter) vormerken."""
        node = repo.get_container(conn, node_id)
        if node is None:
            raise LagerError("Behälter nicht gefunden")
        rows = labels.unprinted_in(conn, settings.base_url, node_id)
        for r in rows:
            labels.enqueue(conn, r.code, r.text, r.extra)
        if not rows:
            return redirect(f"/n/{node_id}", "Alle Etiketten dieser Box sind schon gedruckt")
        msg = f"{len(rows)} ungedruckte Etiketten aus „{node['name']}“ vorgemerkt"
        return redirect("/labels", msg)

    # --- D30-Direktdruck und PC-Bridge ------------------------------------------------------

    @app.get("/d30/status")
    def d30_status(conn: Conn) -> JSONResponse:
        if not ctx.d30_on(conn):
            return JSONResponse(
                {"enabled": False, "available": False, "msg": "aus", "bridge": ctx.bridge_on(conn)}
            )
        ok, msg = d30.status()
        return JSONResponse({"enabled": True, "available": ok, "msg": msg})

    @app.post("/d30/print")
    def d30_print(
        conn: Conn, code: Annotated[list[str], Form()], back: Annotated[str, Form()] = "/"
    ) -> RedirectResponse:
        if ctx.bridge_only(conn):
            marker = f"\u27e6d30:{','.join(dict.fromkeys(code))}\u27e7"
            return redirect(safe_back(back, "/"), "Druck über PC-Bridge" + marker)
        if not ctx.d30_on(conn):
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

    # --- Etikett-Layout je Typ --------------------------------------------------------------

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
        """Etiketten-Layout je Typ, gegliedert wie das Sortiment: Bereich › Gruppe › Typ."""
        all_kinds = sortiment.kinds(conn)
        custom = {k.key for k in all_kinds if typesettings.get(conn, k.key).get("label_layout")}
        areas = sortiment.tree(all_kinds, sortiment.counts(conn))
        return render(request, conn, "etiketten_typen.html", areas=areas, custom=custom)

    @app.get("/etiketten/typ/{key}", response_class=HTMLResponse)
    def label_designer(request: Request, key: str, conn: Conn) -> HTMLResponse:
        k = sortiment.kind(conn, key)
        stored = typesettings.get(conn, key).get("label_layout") or ""
        layout = labels.parse_layout(stored) if stored else labels.default_for(conn, key)
        layout = layout or labels.default_layout()
        values, code = sample(conn, k)
        fields = [(f"{{{f}}}", lb) for f, lb, _ in k.fields]
        have = {f for f, _, _ in k.fields}
        fields += [(f"{{{f}}}", lb) for f, lb in labels.EXTRA_FIELDS if f not in have]
        return render(
            request, conn, "etiketten_layout.html", kind=k, layout=layout, custom=bool(stored),
            back=request.query_params.get("back", ""),
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
            stored = typesettings.get(conn, key).get("label_layout") or ""
            fallback = labels.default_for(conn, key) or labels.default_layout()
            layout = labels.parse_layout(stored) if stored else fallback
        values, code = sample(conn, k)
        label = labels.Label(
            code, labels.qr_content(settings.base_url, code), values.get("name", ""), "",
            labels.layout_lines(layout, values), str(layout["qr"]),
        )  # fmt: skip
        return Response(labelimg.png(label), media_type="image/png",
                        headers={"Cache-Control": "no-store"})  # fmt: skip

    @app.post("/etiketten/typ/{key}")
    def label_layout_save(key: str, conn: Conn, form: FormDict) -> RedirectResponse:
        sortiment.kind(conn, key)
        back = form.get("back", "")  # Rücksprung ins Anlegen-Formular
        back = back if back.startswith("/neu") else ""
        if form.get("reset"):
            typesettings.save_layout(conn, key, None)
            return redirect(back or f"/etiketten/typ/{key}", "Standard-Layout wiederhergestellt")
        if form.get("all"):
            lay = layout_from(form)
            for k in sortiment.kinds(conn):
                typesettings.save_layout(conn, k.key, lay)
            return redirect(back or f"/etiketten/typ/{key}", "Layout für alle Typen übernommen")
        typesettings.save_layout(conn, key, layout_from(form))
        return redirect(
            back or f"/etiketten/typ/{key}",
            "Layout gespeichert – gilt für neue Etiketten dieses Typs",
        )
