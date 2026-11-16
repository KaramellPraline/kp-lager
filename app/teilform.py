"""Gemeinsames Teile-Formular: dieselben Felder beim Anlegen (/neu) und Bearbeiten
(/items/<id>/bearbeiten). Hier liegt die Speicher-Logik für Stammdaten, Typ-Felder und
Eigenschafts-Profile (Datenblatt in `item.specs`); die Oberfläche steht in `_teil_form.html`."""

import sqlite3
from datetime import date

from app import catalog, itemtypes, materials, repo, typesettings
from app.catalog import Type
from app.repo import LagerError

Form = dict[str, str]


def _int(raw: str) -> int | None:
    raw = raw.strip()
    if not raw:
        return None
    if not raw.lstrip("-").isdigit():
        raise LagerError(f"„{raw}“ ist keine ganze Zahl")
    return int(raw)


def _date(raw: str) -> str | None:
    raw = raw.strip()
    if not raw:
        return None
    try:
        return date.fromisoformat(raw).isoformat()
    except ValueError:
        raise LagerError(f"„{raw}“ ist kein Datum (JJJJ-MM-TT)") from None


def type_values(t: Type, form: Form) -> dict[str, str]:
    """Typ-Felder aus dem Formular (f_<key>), Dezimalzahlen mit Punkt, abgeleitete Werte."""
    raw = {f.key: catalog.number(form.get(f"f_{f.key}", "")).strip() for f in t.fields}
    return catalog.derive(t, raw)


def check_required(conn: sqlite3.Connection, t: Type, values: dict[str, str]) -> None:
    required = typesettings.required_keys(conn, t.key)
    missing = [f.label for f in t.fields if f.key in required and not values.get(f.key, "")]
    if missing:
        raise LagerError("Pflichtfeld fehlt: " + ", ".join(missing))


def profile(t: Type | None, form: Form) -> str:
    """Eigenschafts-Profil: vom Typ festgelegt, sonst die Auswahl im Formular."""
    fixed = catalog.profile_of(t)
    chosen = form.get("material", "").strip()
    return fixed or (chosen if chosen in materials.MATERIALS else "")


def spec_values(t: Type | None, clean: dict[str, str], form: Form, prof: str) -> Form:
    """spec_*-Werte: Profilfelder aus dem Formular, Werte der Typ-Felder haben Vorrang."""
    keys = {f.key for f in materials.FIELDS.get(prof, ())}
    own = {k: v for k, v in form.items() if k.startswith("spec_") and k[5:] in keys}
    if t is None:
        return own
    tprof, derived = catalog.type_specs(t, clean)
    if tprof != prof:
        return own
    if "spec_function" in derived and own.get("spec_function", "").strip():
        derived.pop("spec_function")  # selbst eingetragene Funktion bleibt
    covered = {f"spec_{k}" for k in catalog.spec_keys(t)}
    return {**{k: v for k, v in own.items() if k not in covered}, **derived}


def stammdaten(conn: sqlite3.Connection, form: Form, t: Type | None) -> dict[str, object]:
    """Gemeinsame Felder (Menge, Einheit, Mindestbestand, Preis, Links, Notizen …)."""
    out: dict[str, object] = {
        "full_name": form.get("full_name", "").strip(),
        "model": form.get("model", "").strip(),
        "datasheet_url": form.get("datasheet_url", "").strip(),
        "order_url": form.get("order_url", "").strip(),
        "qty_hint": form.get("qty_hint", "").strip(),
        "notes": form.get("notes", ""),
        "min_qty": _int(form.get("min_qty", "")),
        "order_qty": _int(form.get("order_qty", "")),
        "expires": _date(form.get("expires", "")),
        "opened": _date(form.get("opened", "")),
        "type_id": itemtypes.resolve(conn, form.get("type_id", ""), form.get("new_type", "")),
    }
    if form.get("unit", "").strip():
        out["unit"] = form["unit"].strip()
    has_price_field = t is not None and any(f.key == "price" for f in t.fields)
    raw_price = form.get("f_price", "") if has_price_field else form.get("price", "")
    out["price"] = materials.parse_price(raw_price)
    return out


def after_create(conn: sqlite3.Connection, item_id: int, t: Type, form: Form) -> None:
    """Nach `catalog.create`: die übrigen Felder des gemeinsamen Formulars übernehmen."""
    item = repo.get_item(conn, item_id)
    data = stammdaten(conn, form, t)
    # leere Angaben beim Anlegen nicht schreiben (Preis aus dem Typ, Einheit-Standard bleiben)
    fields = {k: v for k, v in data.items() if v not in (None, "")}
    extra = form.get("tags", "").strip()
    if extra:
        fields["tags"] = " ".join(dict.fromkeys(f"{item['tags']} {extra}".split()))
    name = form.get("name", "").strip()
    if name and not form.get("series_values", "").strip():
        fields["name"] = name
    if fields:
        repo.update_item(conn, item_id, **fields)  # type: ignore[arg-type]
    prof = profile(t, form)
    own = {k: v for k, v in form.items() if k.startswith("spec_") and v.strip()}
    if prof and (own or prof != catalog.profile_of(t)):
        clean = catalog.values_of(repo.get_item(conn, item_id))
        values = spec_values(t, catalog.derive(t, clean), form, prof)
        materials.save_specs(conn, item_id, prof, {**materials_form(item_id, conn), **values})


def materials_form(item_id: int, conn: sqlite3.Connection) -> Form:
    """Bisherige Datenblatt-Werte als spec_*-Formular (damit nichts verloren geht)."""
    return {f"spec_{k}": v for k, v in materials.specs(repo.get_item(conn, item_id)).items()}


def save(conn: sqlite3.Connection, item_id: int, form: Form) -> str:
    """Bearbeiten: das bestehende Teil mit allen Formularwerten ändern. Liefert die Meldung."""
    before = repo.get_item(conn, item_id)
    key = form.get("typ", "").strip()
    t = catalog.lookup(conn, key) if key else None
    if key and t is None:
        raise LagerError("Unbekannter Teile-Typ")
    clean: dict[str, str] = {}
    auto = ""
    if t is not None:
        clean = type_values(t, form)
        check_required(conn, t, clean)
        auto = catalog.name(t, clean)
    name = form.get("name", "").strip() or auto
    if not name:
        raise LagerError(
            "Name fehlt" if t is None else f"Bitte mindestens ein Feld für „{t.label}“ ausfüllen"
        )
    fields = stammdaten(conn, form, t)
    fields["name"] = name
    fields["qty"] = _int(form.get("qty", ""))
    fields["unit"] = form.get("unit", "").strip()
    tags = form.get("tags", "").strip()
    if t is not None and (key != (before["ctype"] or "") or not tags):
        tags = catalog.auto_tags(t, clean)  # neuer Typ: Tags passend zum Typ neu bilden
    fields["tags"] = tags
    if t is not None:
        catalog.store(conn, item_id, t.key, clean)
        catalog.remember_brand(conn, t, clean.get("brand", ""))
    elif before["ctype"]:
        with conn:
            conn.execute("UPDATE item SET ctype = NULL WHERE id = ?", (item_id,))
    repo.update_item(conn, item_id, **fields)  # type: ignore[arg-type]
    prof = profile(t, form)
    if prof or before["material"]:
        values = spec_values(t, clean, form, prof) if prof else {}
        materials.save_specs(conn, item_id, prof, values)
    target = form.get("target", "")
    if target.isdigit() and int(target) != before["container_id"]:
        repo.move_item(conn, item_id, int(target))
    return "Gespeichert"
