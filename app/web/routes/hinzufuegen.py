"""Hinzufügen: Reiter-Wahl, Behälter anlegen, Kabel/Netzteil/Material,
Schnelleingabe (Startseite und im Kasten) und Platz-Vorschlag."""

from typing import Annotated

from fastapi import Depends, FastAPI, File, Form, Request, UploadFile
from fastapi.responses import HTMLResponse, JSONResponse, RedirectResponse

from app import (
    cables,
    choices,
    codes,
    itemtypes,
    kasten,
    kinds,
    labels,
    materials,
    photos,
    placement,
    prefs,
    projects,
    psus,
    repo,
)
from app.repo import LagerError
from app.web.shared import (
    ADD_TABS,
    TARGET_COOKIE,
    Conn,
    Ctx,
    container_code,
    content_holder,
    entries,
    last_target,
    need_node,
    opt_int,
    ordered,
    pick_dims,
    recent_list,
    recent_targets,
    redirect,
    remember,
    spec_form,
)


def register(app: FastAPI, ctx: Ctx) -> None:
    render = ctx.render
    photo_dir = ctx.photo_dir
    direct_print = ctx.direct_print

    # --- Reiter -----------------------------------------------------------------------------

    @app.get("/neu/go")
    def add_last_tab(request: Request) -> RedirectResponse:
        """Hinzufügen-Tab: zuletzt benutzten Reiter öffnen."""
        tab = request.cookies.get("add_tab", "/neu")
        return RedirectResponse(tab if tab in ADD_TABS else "/neu", status_code=303)

    @app.get("/neu/material", response_class=HTMLResponse)
    def add_material_page(request: Request, conn: Conn) -> HTMLResponse:
        """Hinzufügen › Kabel · Netzteil · Material: Teil mit Kategorie und eigenen Feldern."""
        return render(
            request,
            conn,
            "neu_material.html",
            targets=repo.all_paths(conn),
            target=last_target(request),
            fav_targets=repo.favorites(conn)[:10],
            recent_targets=repo.containers_by_ids(conn, recent_targets(request))[:3],
            cats=[
                c
                for c in ordered(
                    kinds.ITEM_CATS_SHORT, recent_list(request, "qa_cats"), lambda c: c[0]
                )  # fmt: skip
                if c[0] not in ("CNS", "RAW", "CMP")  # nur noch über den Katalog (Typ + Tags)
            ],
            spec_forms=choices.forms(conn),
        )

    @app.get("/neu/behaelter", response_class=HTMLResponse)
    def add_container_page(request: Request, conn: Conn, art: str = "") -> HTMLResponse:
        """Hinzufügen › Behälter: wie der Teile-Katalog (Art links, Felder rechts)."""
        offered = [(g, [k for k in ks if k not in ("compartment", "bin", "level")])
                   for g, ks in kinds.KIND_GROUPS]  # fmt: skip
        flat = [k for _, ks in offered for k in ks]
        key = art if art == "neu" else (kinds.resolve(art) if art else None)
        if key != "neu" and key not in flat:
            recent = recent_list(request, "qa_kinds")
            key = next((k for k in recent if k in flat), "box" if "box" in flat else flat[0])
        recent_rows = conn.execute(
            "SELECT id, name, code, kind, parent_id FROM container ORDER BY id DESC LIMIT 6"
        ).fetchall()
        return render(
            request,
            conn,
            "neu_behaelter.html",
            groups=[(g, ks) for g, ks in offered if ks],
            art=key,
            targets=repo.all_paths(conn),
            target=last_target(request),
            recent=recent_rows,
        )

    # --- Schnelleingabe (Startseite) --------------------------------------------------------

    @app.post("/quickadd")
    def home_quick_add(
        request: Request,
        conn: Conn,
        text: Annotated[str, Form()] = "",
        target: Annotated[str, Form()] = "",
        mode: Annotated[str, Form()] = "item",
        kind: Annotated[str, Form()] = "box",
        new_kind: Annotated[str, Form()] = "",
        new_prefix: Annotated[str, Form()] = "",
        cat: Annotated[str, Form()] = "ART",
        plug_a: Annotated[str, Form()] = "",
        plug_b: Annotated[str, Form()] = "",
        length: Annotated[str, Form()] = "",
        volt: Annotated[str, Form()] = "",
        amp: Annotated[str, Form()] = "",
        psu_plug: Annotated[str, Form()] = "",
        plug_a_new: Annotated[str, Form()] = "",
        plug_b_new: Annotated[str, Form()] = "",
        psu_plug_new: Annotated[str, Form()] = "",
        psu_input: Annotated[str, Form()] = "",
        psu_input_new: Annotated[str, Form()] = "",
        choice: Annotated[str, Form()] = "",
        count: Annotated[str, Form()] = "",
        dims: Annotated[str, Form()] = "",
        dims_custom: Annotated[str, Form()] = "",
        dims_other: Annotated[str, Form()] = "",
        airtight: Annotated[str, Form()] = "",
        d30_print: Annotated[str, Form()] = "",
        back: Annotated[str, Form()] = "",
        specs: Annotated[dict[str, str] | None, Depends(spec_form)] = None,
        photo: Annotated[UploadFile | None, File()] = None,
    ) -> RedirectResponse:
        """„Hinzufügen“ auf der Startseite: Teil mit Kategorie, Behälter, oder „Alle“ (beides).

        Mit Foto: wird jedem neuen Teil bzw. dem neuen Behälter angehängt.
        """
        plug_a = plug_a_new if plug_a == "neu" else plug_a  # Auswahl „Anderer …“
        plug_b = plug_b_new if plug_b == "neu" else plug_b
        psu_plug = psu_plug_new if psu_plug == "neu" else psu_plug
        psu_input = psu_input_new if psu_input == "neu" else psu_input
        given: dict[str, str] = {}  # Werte aus den Kategorie-Feldern (Kabel/Netzteil)
        if mode == "item" and cat.upper() == "CBL" and plug_a.strip():
            # Kabel aus den drei Feldern: Name „USB-A – USB-C 2m“ (Freitext wird dann ignoriert)
            given = {
                "plug_a": cables.plug(plug_a),
                "plug_b": cables.plug(plug_b or plug_a),
                "length": length.replace(",", ".").removesuffix("m").strip(),
            }
            text = cables.name(given)
        if mode == "item" and cat.upper() == "PSU" and (volt.strip() or amp.strip()):
            # Netzteil aus den Feldern: „Netzteil 12V 2A DC 5,5x2,1“
            psu = {
                "volt": volt.replace(",", ".").rstrip("Vv ").strip(),
                "amp": amp.replace(",", ".").rstrip("Aa ").strip(),
                "plug": psus.plug(psu_plug) if psu_plug.strip() else "",
                "input": psus.normalize_input(psu_input) if psu_input.strip() else "",
            }
            text = psus.name(psu)
            if not text:
                raise LagerError("Bitte die Spannung angeben")
            given = {k: v for k, v in psu.items() if v}
        if mode == "item" and cat.upper() in choices.FORM:  # Filament/Harz aus den Auswahllisten
            fields = {f.key for f in materials.FIELDS[materials.PREFIX_MATERIAL[cat.upper()]]}
            raw = {k[5:]: v for k, v in (specs or {}).items() if not k.endswith("_new")}
            vals = {
                k: ((specs or {}).get(f"spec_{k}_new", "") if v == "neu" else v).strip()
                for k, v in raw.items()
                if k in fields
            }
            vals = {k: v for k, v in vals.items() if v}
            if any(vals.get(k) for k in ("brand", "material", "color")):
                given = vals
                text = choices.name(vals)
        if not text.strip():
            raise LagerError("Was soll eingetragen werden?")
        image = photo.file.read() if photo is not None and photo.filename else b""
        if mode == "all":  # choice = "kind:<art>" oder "item:<präfix>"
            what, _, value = choice.partition(":")
            if what == "kind":
                mode, kind = "container", value
            elif what == "item":
                mode, cat = "item", value
            else:
                raise LagerError("Bitte eine Kategorie wählen")
        if mode == "project":
            pid = projects.create(conn, text)
            return redirect(f"/projekte/{pid}", f"Projekt „{text.strip()}“ angelegt")
        if mode == "type":
            t = itemtypes.get(conn, itemtypes.create(conn, text))
            return redirect("/", f"Tag {t['code']} „{t['name']}“ angelegt")
        if mode == "container":
            if kind == "neu":
                kind = kinds.create(conn, new_kind, new_prefix)
            cid = repo.create_container(
                conn, text.strip(), kind, parent_id=opt_int(target),
                dims=pick_dims(dims, dims_custom, dims_other), airtight=bool(airtight),
            )  # fmt: skip
            if image:
                repo.set_container_photo(conn, cid, photos.save(image, photo_dir))
            created = repo.get_container(conn, cid)
            prefix = codes.KIND_PREFIX.get(kind)
            if created and prefix and (kind in ("machine", "dryer") or d30_print):
                new_code = codes.reserve(conn, prefix, 1)[0]  # Maschinen/Trockner: immer Etikett
                repo.assign_code(conn, cid, new_code)
                labels.enqueue(conn, new_code, *labels.container_label(conn, created))
            else:
                new_code = None
            printed = direct_print(conn, [new_code] if new_code and d30_print else [])
            resp = redirect(f"/n/{cid}", f"„{text.strip()}“ angelegt{printed}")
            remember(resp, request, "qa_kinds", kind)
            return resp
        dest = need_node(conn, int(target) if target else repo.inbox(conn))
        cat = cat.strip().upper()
        if cat not in codes.ITEM_PREFIXES:
            raise LagerError(f"Unbekannte Kategorie {cat}")
        names = []
        new_codes: list[str] = []
        # Aus den Kategorie-Feldern: genau ein Teil, Felder direkt übernehmen (nicht neu erkennen)
        parts: list[tuple[int | None, str, str]]
        if given and cat in choices.FORM:  # Spulen/Flaschen: Anzahl = Menge
            parts = [(opt_int(count) or 1, "", text.strip())]
        else:
            parts = [(None, "", text.strip())] if given else list(entries(conn, text))
        if cat in repo.INDIVIDUAL:  # Einzelstücke: jedes Stück ein Eintrag mit eigenem Etikett
            spread: list[tuple[int | None, str, str]] = []
            for amount, unit, name in parts:
                measure = unit.casefold() in ("m", "cm", "meter", "v", "volt")
                n = opt_int(count) or (amount if amount and not measure and not given else 1)
                spread += [(amount if measure else None, unit if measure else "", name)] * max(
                    1, min(n or 1, 50)
                )
            parts = spread
        for amount, unit, name in parts:
            code = (
                codes.new_item_code(conn) if cat == codes.ITEM_PREFIX
                else codes.reserve(conn, cat, 1)[0]
            )  # fmt: skip
            form: dict[str, str] = {}
            if cat == "CBL":  # „2 m HDMI“: Zahl vorne ist die Länge, nicht die Menge
                if amount is not None and unit.casefold() in ("m", "cm", "meter"):
                    name, amount, unit = f"{name} {amount}{unit}", None, ""
                form = {f"spec_{k}": v for k, v in given.items()} or materials.cable_specs(name)
            if cat == "PSU":  # „12V 2A“: Zahl vorne ist die Spannung, nicht die Menge
                if amount is not None and unit.casefold() in ("v", "volt"):
                    name, amount, unit = f"{amount}V {name}", None, ""
                form = {f"spec_{k}": v for k, v in given.items()} or materials.auto_specs(
                    "psu", name
                )
            if given and cat in choices.FORM:
                form = {f"spec_{k}": v for k, v in given.items()}
            new_id = repo.add_item(conn, dest["id"], name, qty=amount, unit=unit, code=code)
            if material := materials.PREFIX_MATERIAL.get(cat):
                materials.save_specs(conn, new_id, material, form)
                name = repo.get_item(conn, new_id)["name"]
            if image:
                repo.update_item(conn, new_id, photo=photos.save(image, photo_dir))
            names.append(name)
            new_codes.append(str(code))
        undo = repo.last_event_id(conn)
        if (holder := content_holder(conn, dest)) and prefs.flag(conn, "queue_on_quickadd"):
            labels.enqueue_content(conn, holder)
        msg = f"{', '.join(f'„{n}“' for n in names)} → {repo.path_label(conn, dest['id'])}"
        msg += direct_print(conn, new_codes if d30_print else [])
        home = back if back.startswith("/") and not back.startswith("//") else "/"
        resp = redirect(home, msg, undo)
        remember(resp, request, "qa_cats", cat)
        ids = [dest["id"]] + [i for i in recent_targets(request) if i != dest["id"]]
        resp.set_cookie(
            TARGET_COOKIE, ",".join(map(str, ids[:3])), max_age=31_536_000, samesite="lax"
        )
        return resp

    # --- Behälter anlegen -------------------------------------------------------------------

    @app.post("/containers")
    def create_container(
        request: Request,
        conn: Conn,
        name: Annotated[str, Form()],
        kind: Annotated[str, Form()],
        parent_id: Annotated[str, Form()] = "",
        code: Annotated[str, Form()] = "",
        grid: Annotated[str, Form()] = "",
        position: Annotated[str, Form()] = "",
        model: Annotated[str, Form()] = "",
        dims: Annotated[str, Form()] = "",
        dims_custom: Annotated[str, Form()] = "",
        dims_other: Annotated[str, Form()] = "",
        airtight: Annotated[str, Form()] = "",
        new_kind: Annotated[str, Form()] = "",
        new_prefix: Annotated[str, Form()] = "",
        queue: Annotated[str, Form()] = "",
        d30_print: Annotated[str, Form()] = "",
        back: Annotated[str, Form()] = "",
    ) -> RedirectResponse:
        if not name.strip():
            raise LagerError("Name fehlt")
        if kind == "neu":
            kind = kinds.create(conn, new_kind, new_prefix)
        kind = kinds.resolve(kind) or kind
        model_key = model if kind == "sortingbox" and model in kasten.MODELS else None
        cid = repo.create_container(
            conn,
            name.strip(),
            kind,
            parent_id=opt_int(parent_id),
            code=container_code(code),
            grid=None if model_key else (grid.strip() or None),
            position=position.strip() or None,
            model=model_key,
            dims=pick_dims(dims, dims_custom, dims_other),
            airtight=bool(airtight),
        )
        msg = f"„{name.strip()}“ angelegt"
        created = repo.get_container(conn, cid)
        prefix = codes.KIND_PREFIX.get(kind)
        if created and prefix and (queue or d30_print):
            new_code = created["code"] or codes.reserve(conn, prefix, 1)[0]
            if not created["code"]:
                repo.assign_code(conn, cid, new_code)
                created = repo.get_container(conn, cid)
            assert created is not None
            msg += f" ({new_code})"
            if queue:
                labels.enqueue(conn, new_code, *labels.container_label(conn, created))
            if d30_print:
                msg += direct_print(conn, [new_code])
        if back.startswith("/") and not back.startswith("//"):  # weiter im Hinzufügen-Reiter
            resp = redirect(back, msg)
            remember(resp, request, "qa_kinds", kind)
            if parent_id.isdigit():
                ids = [int(parent_id)] + [i for i in recent_targets(request) if i != int(parent_id)]
                resp.set_cookie(
                    TARGET_COOKIE, ",".join(map(str, ids[:3])), max_age=31_536_000, samesite="lax"
                )
            return resp
        return redirect(f"/n/{cid}")

    # --- Schnelleingabe im Kasten -----------------------------------------------------------

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
        if queue and (holder := content_holder(conn, dest)) is not None:
            labels.enqueue_content(conn, holder)
            msg += f" · Inhaltsetikett {labels.content_title(conn, holder)} vorgemerkt"
        return redirect(f"/n/{node_id}#schnell", msg, undo)

    # --- Platz-Vorschlag --------------------------------------------------------------------

    @app.get("/neu/platz")
    def place_suggestions(
        request: Request, conn: Conn, typ: str = "", cat: str = ""
    ) -> JSONResponse:
        """Wohin damit? Behälter mit ähnlichen Teilen, sonst leere Boxen."""
        values = {k[2:]: v for k, v in request.query_params.items() if k.startswith("f_") and v}
        material = materials.PREFIX_MATERIAL.get(cat.upper(), "") if not typ else ""
        return JSONResponse(placement.suggest(conn, typ, values, material))
