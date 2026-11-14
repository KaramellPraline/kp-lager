"""Teile: Teil-Seite und ihre Aktionen (Bearbeiten, Code, Menge, Datenblatt, Foto,
Typ, Löschen), Einlagern in einen Behälter, Tags (/typen) und Notiz-/Pinout-Karten."""

import sqlite3
from datetime import date
from typing import Annotated

from fastapi import FastAPI, Form, HTTPException, Request, UploadFile
from fastapi.responses import HTMLResponse, RedirectResponse

from app import (
    cards,
    catalog,
    codes,
    datasheets,
    dryer,
    itemtypes,
    kinds,
    materials,
    photos,
    prefs,
    projects,
    purchases,
    repo,
    typesettings,
    withdrawals,
)
from app.repo import LagerError
from app.web.shared import (
    Conn,
    Ctx,
    FormDict,
    entries,
    iso_date,
    need_node,
    opt_int,
    redirect,
    templates,
)


def register(app: FastAPI, ctx: Ctx) -> None:
    render = ctx.render
    photo_dir = ctx.photo_dir
    sheet_dir = ctx.sheet_dir

    # --- Teil-Seite und Eigenschaften -------------------------------------------------------

    @app.get("/items/{item_id}", response_class=HTMLResponse)
    def item_page(request: Request, item_id: int, conn: Conn) -> HTMLResponse:
        item = repo.get_item(conn, item_id)
        return render(
            request,
            conn,
            "item.html",
            item=item,
            path=repo.container_path(conn, item["container_id"]),
            events=repo.history(conn, item_id)[:30],
            types=itemtypes.all_types(conn),
            open_takes=withdrawals.open_for_item(conn, item_id),
            item_type=itemtypes.get(conn, item["type_id"]) if item["type_id"] else None,
            sheet_search=datasheets.search_url(item["model"]) if item["model"] else "",
            spec_sheet=materials.sheet(item, kinds.lang(conn) == "en"),
            unit_price=materials.unit_price(item),
            specs=materials.specs(item),
            spec_fields=materials.FIELDS.get(item["material"] or "", ()),
            spec_groups=materials.GROUPS,
            rest=materials.remaining(item),
            dry_programs=dryer.programs(conn) if item["material"] == "fil" else [],
            dry_history=dryer.history(conn, item_id, 8) if item["material"] == "fil" else [],
            individual=bool(item["code"]) and item["code"][:3] in repo.INDIVIDUAL,
            today=date.today().isoformat(),
            cards=cards.for_item(conn, item_id),
            ctype=catalog.lookup(conn, item["ctype"]) if item["ctype"] else None,
            cvalues=catalog.values_of(item),
            type_groups=catalog.grouped(conn) if not item["material"] else [],
            tset=typesettings.get(conn, typesettings.key_of(item)),
            reservations=projects.reservations(conn, item_id),
            buys=purchases.for_item(conn, item_id),
            supplier_names=purchases.names(conn),
        )

    @app.post("/items/{item_id}/weigh")
    def item_weigh(item_id: int, conn: Conn, gross: Annotated[str, Form()]) -> RedirectResponse:
        return redirect(f"/items/{item_id}#rest", materials.weigh(conn, item_id, gross))

    @app.post("/items/{item_id}/specs")
    async def item_specs(request: Request, item_id: int, conn: Conn) -> RedirectResponse:
        form = {k: str(v) for k, v in (await request.form()).items()}
        repo.get_item(conn, item_id)
        materials.save_specs(conn, item_id, form.get("material", ""), form)
        return redirect(f"/items/{item_id}#datenblatt", "Eigenschaften gespeichert")

    # --- Einlagern in einen Behälter --------------------------------------------------------

    @app.post("/n/{node_id}/items")
    def add_item(
        node_id: int,
        conn: Conn,
        name: Annotated[str, Form()],
        qty: Annotated[str, Form()] = "",
        unit: Annotated[str, Form()] = "",
        tags: Annotated[str, Form()] = "",
    ) -> RedirectResponse:
        need_node(conn, node_id)
        if not name.strip():
            raise LagerError("Name fehlt")
        amount = opt_int(qty)
        if amount is not None:  # Menge ausdrücklich angegeben -> genau ein Teil
            todo: list[tuple[int | None, str, str]] = [
                (amount, unit.strip() or prefs.raw(conn, "default_unit"), name.strip())
            ]
        else:  # "3 Rollen Lötzinn und 50 M3 Muttern" -> mehrere Teile
            todo = [(a, unit.strip() or u, n) for a, u, n in entries(conn, name)]
        for a, u, n in todo:
            repo.add_item(conn, node_id, n, qty=a, unit=u, tags=tags.strip(),
                          code=codes.new_item_code(conn))  # fmt: skip
        names = ", ".join(f"„{n}“" for _, _, n in todo)
        return redirect(f"/n/{node_id}", f"{names} eingelagert", repo.last_event_id(conn))

    @app.post("/items/new")
    def add_item_with_code(
        conn: Conn,
        code: Annotated[str, Form()],
        container_id: Annotated[int, Form()],
        name: Annotated[str, Form()],
        qty: Annotated[str, Form()] = "",
    ) -> RedirectResponse:
        norm = codes.normalize(code)
        if norm is None or norm[:3] not in codes.ITEM_PREFIXES:
            raise LagerError(f"'{code}' ist kein Teile-Code (ART-0001, FIL-001, RES-001)")
        if not name.strip():
            raise LagerError("Name fehlt")
        need_node(conn, container_id)
        item_id = repo.add_item(conn, container_id, name, qty=opt_int(qty), code=norm)
        codes.mark_used_until(conn, norm[:3], int(norm[4:]))
        if material := materials.PREFIX_MATERIAL.get(norm[:3]):
            materials.save_specs(conn, item_id, material, {})
        return redirect(f"/items/{item_id}", f"„{name.strip()}“ angelegt")

    # --- Teil bearbeiten: Code, Menge, Stammdaten, Datenblatt -------------------------------

    @app.post("/items/{item_id}/code")
    def item_code(
        item_id: int, conn: Conn, remove: Annotated[str, Form()] = ""
    ) -> RedirectResponse:
        if remove:
            repo.set_item_code(conn, item_id, None)
            return redirect(f"/items/{item_id}", "Code entfernt")
        material = repo.get_item(conn, item_id)["material"]
        prefix = materials.MATERIALS[material][2] if material else codes.ITEM_PREFIX
        code = codes.reserve(conn, prefix, 1)[0]
        repo.set_item_code(conn, item_id, code)
        return redirect(f"/items/{item_id}", f"Code {code} vergeben")

    @app.post("/items/{item_id}/qty", response_class=HTMLResponse)
    def change_qty(
        request: Request, item_id: int, conn: Conn, delta: Annotated[int, Form()]
    ) -> HTMLResponse:
        repo.change_qty(conn, item_id, delta)
        return templates.TemplateResponse(
            request, "_item.html", {"i": repo.get_item(conn, item_id)}
        )

    @app.post("/items/{item_id}/edit")
    def edit_item(
        item_id: int,
        conn: Conn,
        name: Annotated[str, Form()],
        qty: Annotated[str, Form()] = "",
        qty_hint: Annotated[str, Form()] = "",
        unit: Annotated[str, Form()] = "",
        tags: Annotated[str, Form()] = "",
        notes: Annotated[str, Form()] = "",
        min_qty: Annotated[str, Form()] = "",
        full_name: Annotated[str, Form()] = "",
        type_id: Annotated[str, Form()] = "",
        new_type: Annotated[str, Form()] = "",
        model: Annotated[str, Form()] = "",
        datasheet_url: Annotated[str, Form()] = "",
        order_url: Annotated[str, Form()] = "",
        price: Annotated[str, Form()] = "",
        material: Annotated[str, Form()] = "",
        expires: Annotated[str, Form()] = "",
        opened: Annotated[str, Form()] = "",
        order_qty: Annotated[str, Form()] = "",
    ) -> RedirectResponse:
        before = repo.get_item(conn, item_id)
        if material != (before["material"] or ""):
            materials.save_specs(conn, item_id, material, {
                f"spec_{k}": v for k, v in materials.specs(before).items()
            })  # fmt: skip
        repo.update_item(
            conn,
            item_id,
            name=name.strip(),
            full_name=full_name.strip(),
            type_id=itemtypes.resolve(conn, type_id, new_type),
            model=model.strip(),
            datasheet_url=datasheet_url.strip(),
            order_url=order_url.strip(),
            price=materials.parse_price(price),
            qty=opt_int(qty),
            qty_hint=qty_hint.strip(),
            unit=unit.strip(),
            tags=tags.strip(),
            notes=notes,
            min_qty=opt_int(min_qty),
            expires=iso_date(expires),
            opened=iso_date(opened),
            order_qty=opt_int(order_qty),
        )
        msg = "Gespeichert"
        url = datasheet_url.strip()
        if url and (url != before["datasheet_url"] or not before["datasheet"]):
            msg = fetch_datasheet(conn, item_id)
        return redirect(f"/items/{item_id}", msg)

    def fetch_datasheet(conn: sqlite3.Connection, item_id: int) -> str:
        """Datenblatt-PDF der Item-URL lokal speichern; Rückmeldung als Text."""
        item = repo.get_item(conn, item_id)
        stem = f"{item['code'] or item_id}-{item['model'] or item['name']}"
        try:
            name = datasheets.download(item["datasheet_url"], sheet_dir, stem)
        except LagerError as exc:
            return f"Gespeichert – {exc}"
        if item["datasheet"] and item["datasheet"] != name:
            (sheet_dir / item["datasheet"]).unlink(missing_ok=True)
        repo.update_item(conn, item_id, datasheet=name)
        return "Gespeichert – Datenblatt heruntergeladen"

    @app.post("/items/{item_id}/datasheet")
    def refresh_datasheet(item_id: int, conn: Conn) -> RedirectResponse:
        if not repo.get_item(conn, item_id)["datasheet_url"]:
            raise LagerError("Keine Datenblatt-URL hinterlegt")
        return redirect(
            f"/items/{item_id}", fetch_datasheet(conn, item_id).replace("Gespeichert – ", "")
        )

    # --- Tags (TAG-001 …) -------------------------------------------------------------------

    @app.get("/typen", response_class=HTMLResponse)
    def types_page(request: Request, conn: Conn) -> HTMLResponse:
        return render(request, conn, "types.html", types=itemtypes.all_types(conn))

    @app.post("/typen")
    def create_type(conn: Conn, name: Annotated[str, Form()]) -> RedirectResponse:
        t = itemtypes.get(conn, itemtypes.create(conn, name))
        return redirect("/typen", f"Tag {t['code']} „{t['name']}“ angelegt")

    @app.get("/typen/{type_id}", response_class=HTMLResponse)
    def type_page(request: Request, type_id: int, conn: Conn) -> HTMLResponse:
        t = itemtypes.get(conn, type_id)
        rows = [{**dict(i), "path": repo.path_label(conn, i["container_id"])}
                for i in itemtypes.items_of(conn, type_id)]  # fmt: skip
        return render(request, conn, "type.html", t=t, items=rows)

    @app.post("/typen/{type_id}/rename")
    def rename_type(type_id: int, conn: Conn, name: Annotated[str, Form()]) -> RedirectResponse:
        itemtypes.rename(conn, type_id, name)
        return redirect(f"/typen/{type_id}", "Umbenannt")

    @app.post("/typen/{type_id}/delete")
    def delete_type(type_id: int, conn: Conn) -> RedirectResponse:
        itemtypes.delete(conn, type_id)
        return redirect("/typen", "Tag gelöscht")

    # --- Löschen und Foto -------------------------------------------------------------------

    @app.post("/items/{item_id}/delete")
    def delete_item(item_id: int, conn: Conn) -> RedirectResponse:
        item = repo.get_item(conn, item_id)
        repo.delete_item(conn, item_id)
        photos.delete(item["photo"], photo_dir)
        return redirect(f"/n/{item['container_id']}", f"„{item['name']}“ entfernt")

    @app.post("/items/{item_id}/photo")
    async def item_photo(item_id: int, conn: Conn, photo: UploadFile) -> RedirectResponse:
        old = repo.get_item(conn, item_id)["photo"]
        name = photos.save(await photo.read(), photo_dir)
        repo.update_item(conn, item_id, photo=name)
        photos.delete(old, photo_dir)
        return redirect(f"/items/{item_id}", "Foto gespeichert")

    # --- Typ am Teil ------------------------------------------------------------------------

    @app.post("/items/{item_id}/typ")
    def item_type(item_id: int, conn: Conn, form: FormDict) -> RedirectResponse:
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

    # --- Notiz- und Pinout-Karten -----------------------------------------------------------

    @app.post("/items/{item_id}/cards")
    def item_card_add(
        item_id: int,
        conn: Conn,
        title: Annotated[str, Form()],
        body: Annotated[str, Form()] = "",
        kind: Annotated[str, Form()] = "note",
    ) -> RedirectResponse:
        repo.get_item(conn, item_id)
        cards.add(conn, title, body, kind, item_id=item_id)
        return redirect(f"/items/{item_id}#karten", "Karte angelegt")

    @app.post("/n/{node_id}/cards")
    def node_card_add(
        node_id: int,
        conn: Conn,
        title: Annotated[str, Form()],
        body: Annotated[str, Form()] = "",
        kind: Annotated[str, Form()] = "note",
    ) -> RedirectResponse:
        if repo.get_container(conn, node_id) is None:
            raise HTTPException(404, "Behälter nicht gefunden")
        cards.add(conn, title, body, kind, container_id=node_id)
        return redirect(f"/n/{node_id}#karten", "Karte angelegt")

    def card_home(card: repo.Row) -> str:
        return (
            f"/items/{card['item_id']}#karten"
            if card["item_id"]
            else f"/n/{card['container_id']}#karten"
        )

    @app.post("/cards/{card_id}/edit")
    def card_edit(
        card_id: int,
        conn: Conn,
        title: Annotated[str, Form()],
        body: Annotated[str, Form()] = "",
    ) -> RedirectResponse:
        card = cards.get(conn, card_id)
        cards.update(conn, card_id, title, body)
        return redirect(card_home(card), "Karte gespeichert")

    @app.post("/cards/{card_id}/delete")
    def card_delete(card_id: int, conn: Conn) -> RedirectResponse:
        card = cards.get(conn, card_id)
        cards.delete(conn, card_id)
        return redirect(card_home(card), "Karte gelöscht")
