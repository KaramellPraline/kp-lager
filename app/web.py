"""HTTP-Oberfläche: Seiten für Behälter (/n/{id}), QR-Einstieg (/c/{code}), Items und Umlagern."""

import sqlite3
from collections.abc import Callable, Iterator
from datetime import date, datetime
from pathlib import Path
from typing import Annotated, Any
from urllib.parse import quote

from fastapi import (
    Body,
    Depends,
    FastAPI,
    File,
    Form,
    HTTPException,
    Request,
    UploadFile,
)
from fastapi.responses import HTMLResponse, JSONResponse, RedirectResponse, Response
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates

from app import (
    __version__,
    api,
    apikeys,
    backup,
    cables,
    cards,
    catalog,
    choices,
    codes,
    d30,
    datasheets,
    dryer,
    icons,
    importer,
    inventory,
    itemtypes,
    kasten,
    kinds,
    labelimg,
    labels,
    materials,
    photos,
    prefs,
    projects,
    psus,
    purchases,
    quick,
    repo,
    scheduler,
    status,
    typesettings,
    value,
    web_extra,
    web_katalog,
    web_lab,
    web_ops,
    web_sortiment,
    withdrawals,
)
from app import search as finder  # Modul; „search“ ist der Name der Such-Route
from app.config import Settings
from app.db import connect
from app.repo import LagerError

APP_DIR = Path(__file__).parent
APP_NAME = "KP Lager"
CARRY_COOKIE = "carry"
ADD_TABS = ("/neu", "/neu/behaelter", "/neu/material", "/neu/bin")
KIND_LABELS = kinds.KIND_LABELS

templates = Jinja2Templates(directory=APP_DIR / "templates")
templates.env.globals["KIND_LABELS"] = KIND_LABELS
templates.env.globals["APP_NAME"] = APP_NAME
templates.env.globals["KIND_PREFIX"] = codes.KIND_PREFIX
templates.env.globals["KIND_GROUPS"] = kinds.KIND_GROUPS
templates.env.globals["SCHEMA_GROUPS"] = kinds.SCHEMA_GROUPS
templates.env.globals["ITEM_CATS"] = kinds.ITEM_CATS
templates.env.globals["ITEM_CATS_SHORT"] = kinds.ITEM_CATS_SHORT
templates.env.globals["PLUG_NAMES"] = cables.COMMON
# Versionsnummer für CSS/JS: neue Datei = neue URL, Browser laden sie sicher neu
templates.env.globals["ASSET_V"] = str(
    max(int((APP_DIR / "static" / f).stat().st_mtime) for f in ("style.css", "app.js"))
)
templates.env.globals["PSU_INPUTS"] = psus.INPUT_LABELS
templates.env.globals["PSU_PLUGS"] = ["DC 5,5x2,1", "DC 5,5x2,5", "DC 3,5x1,35", "USB-C", "USB-A",
                                      "USB-C PD", "Micro-USB", "DC 4,0x1,7", "DC 2,5x0,7",
                                      "DC 7,4x5,0", "MagSafe", "XT60", "KFZ", "Schraubklemmen",
                                      "Molex", "XLR"]  # fmt: skip
templates.env.globals["MODELS"] = kasten.MODELS
templates.env.globals["icon"] = icons.icon
templates.env.globals["euro"] = value.euro
templates.env.globals["EURO_DIMS"] = kinds.EURO_DIMS


def opt_int(value: str | None) -> int | None:
    value = (value or "").strip()
    if not value:
        return None
    try:
        return int(value)
    except ValueError:
        raise LagerError(f"'{value}' ist keine ganze Zahl") from None


def iso_date(value: str | None) -> str | None:
    """'2026-12-31' oder '31.12.2026' -> ISO-Datum; leer -> None."""
    value = (value or "").strip()
    if not value:
        return None
    for fmt in ("%Y-%m-%d", "%d.%m.%Y", "%d.%m.%y"):
        try:
            return datetime.strptime(value, fmt).date().isoformat()
        except ValueError:
            continue
    raise LagerError(f"'{value}' ist kein Datum (z. B. 31.12.2026)")


def pick_dims(dims: str, custom: str, other: str) -> str:
    """Eurobox-Auswahl, eigene Maße oder freies Maßfeld -> 'LxBxH' (mm)."""
    chosen = dims if dims not in ("", "neu") else (custom or other)
    return chosen.strip().lower().replace("×", "x").replace(" ", "")


def redirect(url: str, msg: str = "", undo: int | None = None) -> RedirectResponse:
    url, hash_, anchor = url.partition("#")  # Query muss vor den Anker
    if msg:
        url += ("&" if "?" in url else "?") + "msg=" + quote(msg)
    if undo:
        url += ("&" if "?" in url else "?") + f"undo={undo}"
    return RedirectResponse(url + hash_ + anchor, status_code=303)


BRIDGE_MARK = "\u27e6d30:"  # in der Meldung: Codes, die die PC-Bridge drucken soll
BRIDGE_END = "\u27e7"
RECENT_COOKIE = "recent"
DRYER_COOKIE = "dryer_wait"  # gescannter Trockner wartet 10 min auf Filament-Etiketten
TARGET_COOKIE = "qa_targets"  # zuletzt gewählte Ziele der Schnelleingabe (neueste zuerst)


def recent_targets(request: Request) -> list[int]:
    return [int(x) for x in request.cookies.get(TARGET_COOKIE, "").split(",") if x.isdigit()]


def recent_list(request: Request, name: str) -> list[str]:
    return [x for x in request.cookies.get(name, "").split(",") if x]


def ordered[T](rows: list[T], recents: list[str], key: Callable[[T], str]) -> list[T]:
    """Zuletzt verwendete zuerst (in der Reihenfolge der Nutzung), der Rest wie bisher."""
    first = [r for name in recents for r in rows if key(r) == name]
    return first + [r for r in rows if r not in first]


def remember(resp: RedirectResponse, request: Request, name: str, value: str) -> None:
    names = [value] + [x for x in recent_list(request, name) if x != value]
    resp.set_cookie(name, ",".join(names[:12]), max_age=31_536_000, samesite="lax")


async def spec_form(request: Request) -> dict[str, str]:
    """Alle Formularfelder spec_* (Auswahllisten für Filament/Harz beim Anlegen)."""
    form = await request.form()
    return {k: v for k, v in form.items() if k.startswith("spec_") and isinstance(v, str)}


def last_target(request: Request) -> int | None:
    ids = recent_targets(request) or recent_ids(request)
    return ids[0] if ids else None


def recent_ids(request: Request) -> list[int]:
    return [int(x) for x in request.cookies.get(RECENT_COOKIE, "").split(",") if x.isdigit()]


def container_code(raw: str) -> str | None:
    """Leer -> None; Schema-Code normalisieren; ART-Codes gehören zu Gegenständen."""
    raw = raw.strip()
    if not raw:
        return None
    norm = codes.normalize(raw)
    if norm is None:
        raise LagerError(f"'{raw}' passt nicht zum Code-Schema (z. B. EUR-001)")
    if norm[:3] in codes.ITEM_PREFIXES:
        raise LagerError(f"{norm[:3]}-Codes sind für Teile, nicht für Behälter")
    return norm


def node_url(container_id: int | None) -> str:
    return f"/n/{container_id}" if container_id else "/"


def create_app(settings: Settings) -> FastAPI:
    app = FastAPI(title=APP_NAME)
    app.mount("/static", StaticFiles(directory=APP_DIR / "static"), name="static")
    connect(settings.db_path).close()  # Migrationen beim Start
    photo_dir = settings.data_dir / "photos"
    photo_dir.mkdir(parents=True, exist_ok=True)
    app.mount("/photos", StaticFiles(directory=photo_dir), name="photos")
    sheet_dir = settings.data_dir / "datasheets"
    sheet_dir.mkdir(parents=True, exist_ok=True)
    app.mount("/datasheets", StaticFiles(directory=sheet_dir), name="datasheets")

    def get_conn() -> Iterator[sqlite3.Connection]:
        conn = connect(settings.db_path)
        withdrawals.confirm_due(conn)  # fällige Entnahmen (7 Tage) bestätigen
        try:
            yield conn
        finally:
            conn.close()

    Conn = Annotated[sqlite3.Connection, Depends(get_conn)]
    app.include_router(api.build_router(get_conn))
    if settings.auto_backup:
        scheduler.start(settings.data_dir)

    @app.exception_handler(LagerError)
    def lager_error(request: Request, exc: LagerError) -> RedirectResponse:
        back = request.headers.get("referer", "/").split("?")[0]
        return redirect(back, str(exc))

    @app.exception_handler(sqlite3.IntegrityError)
    def integrity_error(request: Request, exc: sqlite3.IntegrityError) -> RedirectResponse:
        back = request.headers.get("referer", "/").split("?")[0]
        msg = "Code ist schon vergeben" if "code" in str(exc) else "Konflikt mit bestehenden Daten"
        return redirect(back, msg)

    def carry_info(request: Request, conn: sqlite3.Connection) -> dict[str, Any] | None:
        raw = request.cookies.get(CARRY_COOKIE, "")
        kind, _, sid = raw.partition(":")
        if kind not in ("item", "node") or not sid.isdigit():
            return None
        row = (
            conn.execute("SELECT name FROM item WHERE id = ?", (int(sid),)).fetchone()
            if kind == "item"
            else repo.get_container(conn, int(sid))
        )
        return {"kind": kind, "id": int(sid), "name": row["name"]} if row else None

    def render(request: Request, conn: sqlite3.Connection, name: str, **ctx: Any) -> HTMLResponse:
        ctx.setdefault("node", None)
        ctx["carry"] = carry_info(request, conn)
        ctx["msg"] = request.query_params.get("msg", "")
        undo = request.query_params.get("undo", "")
        ctx["undo"] = int(undo) if undo.isdigit() else None
        ctx["APP_NAME"] = prefs.raw(conn, "app_name")
        ctx["THEME"] = prefs.raw(conn, "theme")
        ctx["COMPACT"] = prefs.flag(conn, "compact")
        ctx["NQUEUE"] = labels.queue_count(conn)
        ctx["P"] = prefs.values(conn)
        ctx["D30"] = settings.d30 or settings.d30_bridge
        raw_msg, _, marker = str(ctx["msg"]).partition(BRIDGE_MARK)
        ctx["msg"] = raw_msg
        ctx["bridge_codes"] = marker.removesuffix(BRIDGE_END)
        ctx.setdefault("dims_opts", dims_options(conn))
        ctx.setdefault(
            "dims_kinds", [k for k, _, _ in kinds.ADD_KINDS if k not in ("machine", "dryer")]
        )
        if name in ("node.html", "index.html"):
            ctx["VAL"], ctx["UNPRICED"] = value.totals(conn)
        return templates.TemplateResponse(request, name, ctx)

    def entries(conn: sqlite3.Connection, text: str) -> list[tuple[int | None, str, str]]:
        """Eingabe -> (Menge, Einheit, Name) je Teil, gemäß Einstellungen."""
        if not prefs.flag(conn, "quick_parse"):
            return [(None, "", text.strip())]
        unit = prefs.raw(conn, "default_unit")
        return [(a, u or (unit if a is not None else ""), n) for a, u, n in quick.parse_many(text)]

    def synonyms(conn: sqlite3.Connection) -> dict[str, list[str]]:
        return repo.parse_synonyms(prefs.raw(conn, "synonyms"))

    def need_node(conn: sqlite3.Connection, node_id: int) -> repo.Row:
        node = repo.get_container(conn, node_id)
        if node is None:
            raise HTTPException(404, "Behälter nicht gefunden")
        return node

    # --- Seiten --------------------------------------------------------------

    web_ops.register(app, Conn, render, redirect, settings)
    web_katalog.register(app, Conn, render, redirect, settings)
    web_lab.register(app, Conn, render, redirect, settings)
    web_sortiment.register(app, Conn, render, redirect, settings)
    web_extra.register(app, Conn, render, redirect, settings)

    @app.middleware("http")
    async def force_https(request: Request, call_next: Any) -> Response:
        """HTTP-Instanz (Port 80): nur /ca.crt und /health ausliefern, sonst auf HTTPS."""
        if settings.https_redirect and request.url.path not in ("/ca.crt", "/health"):
            target = request.url.replace(scheme="https", port=None)
            return RedirectResponse(str(target), status_code=308)
        resp: Response = await call_next(request)
        return resp

    @app.middleware("http")
    async def remember_add_tab(request: Request, call_next: Any) -> Response:
        resp: Response = await call_next(request)
        if request.method == "GET" and request.url.path in ADD_TABS and resp.status_code == 200:
            resp.set_cookie("add_tab", request.url.path, max_age=31_536_000, samesite="lax")
        return resp

    @app.get("/health")
    def health() -> dict[str, str]:
        return {"status": "ok", "version": __version__}

    @app.get("/ca.crt")
    def ca_cert() -> Response:
        """Root-Zertifikat zum Installieren auf dem Handy (für HTTPS ohne Warnung)."""
        if not settings.ca_cert.exists():
            raise HTTPException(404, "Kein Zertifikat – tools/devcert.py ausführen")
        return Response(
            settings.ca_cert.read_bytes(),
            media_type="application/x-x509-ca-cert",
            headers={"Content-Disposition": 'attachment; filename="kp-lager-ca.crt"'},
        )

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
            cats=ordered(kinds.ITEM_CATS_SHORT, recent_list(request, "qa_cats"), lambda c: c[0]),
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

    def dims_options(conn: sqlite3.Connection) -> dict[str, list[str]]:
        """Maße je Art: Euro-Normen, dazu alles, was bei Behältern schon vorkommt."""
        used: dict[str, list[str]] = {"*": []}
        for r in conn.execute(
            "SELECT kind, dims, COUNT(*) n FROM container WHERE dims != ''"
            " GROUP BY kind, dims ORDER BY n DESC, dims"
        ):
            used.setdefault(r["kind"], []).append(r["dims"])
            if r["dims"] not in used["*"]:
                used["*"].append(r["dims"])
        out = {k: v for k, v in used.items() if k != "*"}
        out["eurobox"] = used.get("eurobox", []) + [
            d for d in kinds.EURO_DIMS if d not in used.get("eurobox", [])
        ]
        for kind in kinds.BOXY:
            out.setdefault(kind, [])
        out["*"] = used["*"]
        return out

    def direct_print(conn: sqlite3.Connection, codes_: list[str]) -> str:
        """Direktdruck nach dem Eintragen; ein Druckfehler lässt das Eintragen gelten."""
        if settings.d30_bridge and not settings.d30 and codes_:
            return f" · Druck über PC-Bridge{BRIDGE_MARK}{','.join(codes_)}{BRIDGE_END}"
        if not (settings.d30 and codes_):
            return ""
        try:
            n = d30.print_codes(conn, settings.base_url, codes_)
        except LagerError as exc:
            return f" · nicht gedruckt: {exc}"
        return f" · {n} Etikett{'en' if n != 1 else ''} gedruckt"

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

    @app.get("/n/{node_id}", response_class=HTMLResponse)
    def node_page(request: Request, node_id: int, conn: Conn) -> HTMLResponse:
        node = need_node(conn, node_id)
        cols = int(node["grid"].split("x")[0]) if node["grid"] else 0
        path = repo.container_path(conn, node_id)[:-1]
        resp = render(
            request,
            conn,
            "node.html",
            node=node,
            path=path,
            kids=repo.children(conn, node_id),
            items=repo.items_in(conn, node_id),
            cols=cols,
            topview=kasten.topview(conn, node),
            targets=kasten.quick_targets(conn, node) if node["model"] else [],
            free=kasten.free_cells(conn, node),
            place=request.query_params.get("place", ""),
            sizes=kasten.SIZES,
            divs=kasten.DIVS,
            cad=kasten.cad_command(node) if node["kind"] == "bin" else "",
            cards=cards.for_container(conn, node_id),
        )
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

    @app.get("/material", response_class=HTMLResponse)
    def material_page(request: Request, conn: Conn) -> HTMLResponse:
        rows = [
            {"item": i, "specs": materials.specs(i), "unit_price": materials.unit_price(i),
             "rest": materials.remaining(i),
             "path": repo.path_label(conn, i["container_id"])}
            for i in materials.all_materials(conn)
        ]  # fmt: skip
        names = {k: v for k, v in materials.MATERIALS.items() if k in materials.PRINTING}
        return render(request, conn, "material.html", rows=rows, names=names)

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

    # --- Import / Export ------------------------------------------------------

    @app.get("/import", response_class=HTMLResponse)
    def import_page(request: Request, conn: Conn) -> HTMLResponse:
        return render(request, conn, "import.html", report=None, text="", done=False)

    @app.post("/import", response_class=HTMLResponse)
    def import_run(
        request: Request,
        conn: Conn,
        text: Annotated[str, Form()] = "",
        action: Annotated[str, Form()] = "preview",
    ) -> HTMLResponse:
        commit = action == "commit"
        report = importer.run(conn, text, commit=commit)
        done = commit and not report.errors
        return render(request, conn, "import.html", report=report, text=text, done=done)

    @app.get("/export.json")
    def export(conn: Conn) -> JSONResponse:
        return JSONResponse(
            importer.export(conn),
            headers={"Content-Disposition": 'attachment; filename="lager-export.json"'},
        )

    # --- Etiketten: Vorschau (Namen bearbeiten) → XLSX für D30 oder A8-Bogen -------

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
        )

    @app.get("/codes", response_class=HTMLResponse)
    def codes_page(request: Request, conn: Conn) -> HTMLResponse:
        return render(
            request,
            conn,
            "codes.html",
            prefixes=codes.PREFIX_LABELS,
            desc=kinds.PREFIX_DESC,
            custom_kinds={k["prefix"]: k for k in kinds.custom(conn)},
        )

    @app.post("/lang")
    def set_lang(
        conn: Conn, lang: Annotated[str, Form()], back: Annotated[str, Form()] = "/mehr"
    ) -> RedirectResponse:
        kinds.set_lang(conn, lang)
        target = back if back.startswith("/") and not back.startswith("//") else "/mehr"
        return redirect(target, "Sprache: English" if lang == "en" else "Sprache: Deutsch")

    @app.post("/arten")
    def kind_create(
        conn: Conn,
        label: Annotated[str, Form()],
        prefix: Annotated[str, Form()],
        description: Annotated[str, Form()] = "",
    ) -> RedirectResponse:
        kinds.create(conn, label, prefix, description)
        return redirect(
            "/labels#schema", f"Art „{label.strip()}“ mit {prefix.upper()}-001 angelegt"
        )

    @app.post("/arten/{kind}/delete")
    def kind_delete(kind: str, conn: Conn) -> RedirectResponse:
        kinds.delete(conn, kind)
        return redirect("/codes", "Art gelöscht")

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

    @app.get("/labels/a4", response_class=HTMLResponse)
    def labels_a4_page(request: Request, conn: Conn, q: str = "") -> HTMLResponse:
        rows = labels.all_coded(conn, settings.base_url)
        if q.strip():
            needle = q.casefold()
            rows = [r for r in rows if needle in f"{r.code} {r.text} {r.extra}".casefold()]
        return render(request, conn, "labels_a4_select.html", rows=rows, aq=q)

    @app.post("/labels/a4", response_model=None)
    def labels_a4_print(
        request: Request,
        conn: Conn,
        code: Annotated[list[str], Form()] = [],  # noqa: B006
        fmt: Annotated[str, Form()] = "a4",
    ) -> Response:
        """Ausgewählte Etiketten auf A4 drucken (40×12-Bogen oder A8)."""
        chosen = set(code)
        rows = [r for r in labels.all_coded(conn, settings.base_url) if r.code in chosen]
        if not rows:
            raise LagerError("Nichts ausgewählt")
        rows = labels.finalize(
            conn, settings.base_url, [(r.code, r.text, r.extra) for r in rows], False
        )
        cells = [(r, labels.qr_svg(r.qr)) for r in rows]
        if fmt == "a8":
            per = labels.A8_PER_PAGE
            pages = [cells[i : i + per] for i in range(0, len(cells), per)]
            return templates.TemplateResponse(
                request, "labels_a8.html", {"pages": pages, "rows": rows}
            )
        per = labels.A4_COLS * labels.A4_ROWS
        pages = [cells[i : i + per] for i in range(0, len(cells), per)]
        return templates.TemplateResponse(
            request, "labels_a4.html", {"pages": pages, "rows": rows, "per": per}
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
        bridge = fmt == "d30" and settings.d30_bridge and not settings.d30
        if fmt == "d30" and not bridge:  # erst drucken – nur Gedrucktes wird als gedruckt gebucht
            if not settings.d30:
                raise LagerError("Direktdruck ist abgeschaltet (LAGER_D30=1)")
            d30.print_labels(
                [
                    labels.Label(c, labels.qr_content(settings.base_url, c), t.strip(), e.strip())
                    for raw, t, e in entries_
                    if (c := codes.normalize(raw))
                ]
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
        if fmt == "a4":
            cells = [(r, labels.qr_svg(r.qr)) for r in rows]
            per = labels.A4_COLS * labels.A4_ROWS
            pages = [cells[i : i + per] for i in range(0, len(cells), per)]
            return templates.TemplateResponse(
                request, "labels_a4.html", {"pages": pages, "rows": rows, "per": per}
            )
        if fmt == "a8":
            cells = [(r, labels.qr_svg(r.qr)) for r in rows]
            pages = [
                cells[i : i + labels.A8_PER_PAGE] for i in range(0, len(cells), labels.A8_PER_PAGE)
            ]
            return templates.TemplateResponse(
                request, "labels_a8.html", {"pages": pages, "rows": rows}
            )
        name = rows[0].code if len(rows) == 1 else f"{rows[0].code}_bis_{rows[-1].code}"
        return Response(
            labels.to_xlsx(rows, prefs.number(conn, "label_text_max")),
            media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
            headers={"Content-Disposition": f'attachment; filename="{name}.xlsx"'},
        )

    # --- Einstellungen ----------------------------------------------------------

    @app.get("/settings", response_class=HTMLResponse)
    def settings_page(request: Request, conn: Conn) -> HTMLResponse:
        return render(
            request,
            conn,
            "settings.html",
            groups=prefs.groups(),
            values=prefs.values(conn),
            next_codes={
                p: codes.format_code(p, codes.next_number(conn, p)) for p in codes.PREFIX_LABELS
            },
            prefixes=codes.PREFIX_LABELS,
            base_url=settings.base_url,
            has_ca=settings.ca_cert.exists(),
        )

    @app.post("/settings")
    async def settings_save(request: Request, conn: Conn) -> RedirectResponse:
        form = await request.form()
        prefs.save(conn, {k: str(v) for k, v in form.items()})
        return redirect("/settings", "Einstellungen gespeichert")

    # --- Admin: Code-Zähler je Präfix ----------------------------------------------

    @app.get("/settings/admin", response_class=HTMLResponse)
    def admin_page(request: Request, conn: Conn) -> HTMLResponse:
        return render_admin(request, conn, new_key=None)

    def render_admin(
        request: Request, conn: sqlite3.Connection, new_key: str | None
    ) -> HTMLResponse:
        counters = [
            {
                "prefix": p,
                "label": label,
                "highest": codes.highest_used(conn, p),
                "next": codes.next_number(conn, p),
                "next_code": codes.format_code(p, codes.next_number(conn, p)),
                "used": codes.used_codes(conn, p),
            }
            for p, label in codes.PREFIX_LABELS.items()
        ]
        return render(
            request,
            conn,
            "settings_admin.html",
            counters=counters,
            keys=apikeys.all_keys(conn),
            new_key=new_key,
        )

    @app.post("/settings/admin/keys", response_class=HTMLResponse)
    def admin_create_key(
        request: Request,
        conn: Conn,
        name: Annotated[str, Form()],
        scope: Annotated[str, Form()] = "write",
    ) -> HTMLResponse:
        """Neuen API-Schlüssel erzeugen und genau einmal anzeigen (nie in der URL)."""
        return render_admin(request, conn, new_key=apikeys.create(conn, name, scope))

    @app.post("/settings/admin/keys/{key_id}/delete")
    def admin_delete_key(key_id: int, conn: Conn) -> RedirectResponse:
        apikeys.delete(conn, key_id)
        return redirect("/settings/admin#api", "Schlüssel gelöscht")

    @app.post("/settings/admin/next")
    def admin_set_next(
        conn: Conn, prefix: Annotated[str, Form()], number: Annotated[int, Form()]
    ) -> RedirectResponse:
        try:
            codes.set_next(conn, prefix, number)
        except ValueError as exc:
            raise LagerError(str(exc)) from None
        nxt = codes.format_code(prefix, number)
        return redirect("/settings/admin", f"{prefix}: nächster Code ist jetzt {nxt}")

    @app.post("/settings/admin/reset")
    def admin_reset(conn: Conn, prefix: Annotated[str, Form()]) -> RedirectResponse:
        if prefix not in codes.PREFIX_KIND:
            raise LagerError(f"Unbekanntes Präfix {prefix}")
        nxt = codes.format_code(prefix, codes.reset_counter(conn, prefix))
        return redirect("/settings/admin", f"{prefix} zurückgesetzt – nächster Code {nxt}")

    @app.post("/settings/admin/remove")
    def admin_remove_code(conn: Conn, code: Annotated[str, Form()]) -> RedirectResponse:
        """Code von seinem Behälter/Gegenstand lösen (Objekt bleibt erhalten)."""
        if node := repo.get_container_by_code(conn, code):
            repo.assign_code(conn, node["id"], None)
            name = node["name"]
        elif item := repo.get_item_by_code(conn, code):
            repo.set_item_code(conn, item["id"], None)
            name = item["name"]
        elif t := itemtypes.by_code(conn, code):
            with conn:
                conn.execute("UPDATE item_type SET code = NULL WHERE id = ?", (t["id"],))
            name = t["name"]
        else:
            raise LagerError(f"{code} ist nicht vergeben")
        labels.dequeue(conn, [code])
        return redirect("/settings/admin", f"{code} von „{name}“ entfernt")

    @app.post("/settings/backup")
    def settings_backup(conn: Conn) -> RedirectResponse:
        files = backup.run(settings.data_dir, settings.data_dir / "backups")
        return redirect("/settings", "Backup: " + ", ".join(f.name for f in files))

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

    @app.get("/mehr", response_class=HTMLResponse)
    def more_page(request: Request, conn: Conn) -> HTMLResponse:
        return render(
            request,
            conn,
            "more.html",
            n_lent=len(repo.lent_items(conn)),
            n_shopping=len(repo.shopping_list(conn)),
        )

    # --- Alltag: Rückgängig, Verlauf, Verliehen, Einkauf, Platz -------------------

    @app.post("/undo/{event_id}")
    def undo(request: Request, event_id: int, conn: Conn) -> RedirectResponse:
        msg = repo.undo(conn, event_id)
        back = request.headers.get("referer", "/").split("?")[0]
        return redirect(back, msg)

    @app.get("/verlauf", response_class=HTMLResponse)
    def history_page(request: Request, conn: Conn, tab: str = "aktionen") -> HTMLResponse:
        recent = repo.containers_by_ids(conn, recent_ids(request))
        return render(
            request,
            conn,
            "history.html",
            tab="gesehen" if tab == "gesehen" else "aktionen",
            events=repo.recent_events(conn),
            undoable=repo.UNDOABLE,
            recent=recent[: prefs.number(conn, "home_recent")],
        )

    @app.get("/verliehen", response_class=HTMLResponse)
    def lent_page(request: Request, conn: Conn) -> HTMLResponse:
        return render(request, conn, "list.html", title="Verliehen / in Benutzung",
                      rows=repo.lent_items(conn), kind="lent")  # fmt: skip

    @app.get("/einkauf", response_class=HTMLResponse)
    def shopping_page(request: Request, conn: Conn) -> HTMLResponse:
        rows = repo.shopping_list(conn)
        total = sum(float(r["cost"]) for r in rows if r["cost"] is not None)
        return render(request, conn, "list.html", title="Einkaufsliste", rows=rows,
                      kind="shopping", total=total)  # fmt: skip

    @app.get("/platz", response_class=HTMLResponse)
    def free_page(request: Request, conn: Conn) -> HTMLResponse:
        return render(request, conn, "free.html", **repo.free_places(conn))

    @app.post("/items/{item_id}/lend")
    def lend(item_id: int, conn: Conn, to: Annotated[str, Form()] = "") -> RedirectResponse:
        repo.lend_item(conn, item_id, to)
        return redirect(f"/items/{item_id}", "Als verliehen markiert")

    @app.post("/items/{item_id}/return")
    def give_back(item_id: int, conn: Conn) -> RedirectResponse:
        repo.return_item(conn, item_id)
        return redirect(f"/items/{item_id}", "Zurück im Lager")

    @app.post("/items/{item_id}/list")
    def toggle_list(request: Request, item_id: int, conn: Conn) -> RedirectResponse:
        item = repo.get_item(conn, item_id)
        repo.update_item(conn, item_id, on_list=0 if item["on_list"] else 1)
        back = request.headers.get("referer", f"/items/{item_id}").split("?")[0]
        return redirect(
            back, "Von Einkaufsliste genommen" if item["on_list"] else "Auf Einkaufsliste"
        )

    @app.post("/n/{node_id}/favorite")
    def favorite(node_id: int, conn: Conn) -> RedirectResponse:
        node = need_node(conn, node_id)
        repo.set_favorite(conn, node_id, not node["favorite"])
        return redirect(
            f"/n/{node_id}", "Favorit entfernt" if node["favorite"] else "Als Favorit gemerkt"
        )

    # --- Scan-Modus & Sprache (brauchen HTTPS für Kamera/Mikrofon) ---------------

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

    # --- Entnahmen ---------------------------------------------------------------

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

    # --- Projekte ------------------------------------------------------------------

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

    @app.get("/sw.js")
    def service_worker() -> Response:
        """Service Worker im Wurzelpfad (Geltungsbereich „/“); Version = Stand von CSS/JS."""
        js = (APP_DIR / "static" / "sw.js").read_text(encoding="utf-8")
        return Response(
            js.replace("__V__", str(templates.env.globals["ASSET_V"])),
            media_type="text/javascript",
            headers={"Cache-Control": "no-cache", "Service-Worker-Allowed": "/"},
        )

    @app.get("/offline", response_class=HTMLResponse)
    def offline_page(request: Request, conn: Conn) -> HTMLResponse:
        return render(request, conn, "offline.html")

    @app.get("/manifest.webmanifest")
    def manifest(conn: Conn) -> JSONResponse:
        return JSONResponse(
            {
                "id": "/",
                "name": prefs.raw(conn, "app_name"),
                "short_name": prefs.raw(conn, "app_name"),
                "description": "Lager mit QR-Codes: suchen, einlagern, entnehmen – auch offline.",
                "lang": "de",
                "start_url": "/",
                "scope": "/",
                "display": "standalone",
                "orientation": "portrait",
                "background_color": "#0B0306",
                "theme_color": "#0B0306",
                "icons": [
                    {"src": "/static/icon-192.png", "sizes": "192x192", "type": "image/png"},
                    {"src": "/static/icon-512.png", "sizes": "512x512", "type": "image/png"},
                    {
                        "src": "/static/icon-512.png",
                        "sizes": "512x512",
                        "type": "image/png",
                        "purpose": "maskable",
                    },
                ],
                "shortcuts": [
                    {"name": "Scannen", "url": "/scan"},
                    {"name": "Hinzufügen", "url": "/neu/go"},
                    {"name": "Suche", "url": "/suche"},
                ],
            },
            media_type="application/manifest+json",
        )

    # --- Behälter -------------------------------------------------------------

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

    # --- Sortierkasten mit Einsätzen (NORB16) ----------------------------------------

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

    @app.post("/n/{node_id}/fill")
    def fill_bins(node_id: int, conn: Conn) -> RedirectResponse:
        """Alle freien Zellen mit 1x1-Einsätzen belegen (schnelle Ersteinrichtung)."""
        node = need_node(conn, node_id)
        cells = kasten.free_cells(conn, node)
        for cell in cells:
            kasten.place_bin(conn, node_id, cell, "1x1")
        return redirect(f"/n/{node_id}", f"{len(cells)} Einsätze 1x1 angelegt")

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

    # --- Etiketten-Warteschlange ------------------------------------------------------

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

    def content_holder(conn: sqlite3.Connection, dest: sqlite3.Row) -> sqlite3.Row | None:
        """Wohin das Inhaltsetikett gehört: der Bin, sonst das Fach im Sortierkasten."""
        if (b := kasten.bin_of(conn, dest["id"])) is not None:
            return b
        return dest if dest["kind"] == "compartment" else None

    @app.post("/labels/content/node/{node_id}")
    def content_node(request: Request, node_id: int, conn: Conn) -> RedirectResponse:
        node = need_node(conn, node_id)
        labels.enqueue_content(conn, node)
        back = request.headers.get("referer", f"/n/{node_id}").split("?")[0]
        return redirect(back, f"Inhaltsetikett {labels.content_title(conn, node)} vorgemerkt")

    @app.get("/labels/content.xlsx", response_model=None)
    def content_export(conn: Conn) -> Response:
        rows = labels.content_queue(conn)
        if not rows:
            raise LagerError("Keine Inhaltsetiketten vorgemerkt")
        data = labels.content_xlsx(rows, prefs.number(conn, "label_text_max") * 2)
        labels.clear_content(conn)
        return Response(
            data,
            media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
            headers={"Content-Disposition": 'attachment; filename="inhaltsetiketten.xlsx"'},
        )

    @app.get("/labels/content/a4", response_class=HTMLResponse)
    def content_a4(request: Request, conn: Conn) -> HTMLResponse:
        rows = labels.content_queue(conn)
        pages = [rows[i : i + labels.A4_COLS * labels.A4_ROWS]
                 for i in range(0, len(rows), labels.A4_COLS * labels.A4_ROWS)]  # fmt: skip
        return render(request, conn, "labels_content_a4.html", rows=rows, pages=pages)

    @app.post("/labels/content/clear")
    def content_clear(conn: Conn) -> RedirectResponse:
        labels.clear_content(conn)
        return redirect("/labels", "Inhaltsetiketten geleert")

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

    @app.post("/n/{node_id}/edit")
    def edit_container(
        node_id: int,
        conn: Conn,
        name: Annotated[str, Form()],
        notes: Annotated[str, Form()] = "",
        code: Annotated[str, Form()] = "",
    ) -> RedirectResponse:
        node = need_node(conn, node_id)
        repo.update_container(conn, node_id, name, notes)
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

    # --- Items ----------------------------------------------------------------

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

    # --- Tags (TAG-001 …) --------------------------------------------------------

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

    @app.post("/items/{item_id}/delete")
    def delete_item(item_id: int, conn: Conn) -> RedirectResponse:
        item = repo.get_item(conn, item_id)
        repo.delete_item(conn, item_id)
        photos.delete(item["photo"], photo_dir)
        return redirect(f"/n/{item['container_id']}", f"„{item['name']}“ entfernt")

    # --- Fotos -----------------------------------------------------------------

    @app.post("/n/{node_id}/photo")
    async def container_photo(node_id: int, conn: Conn, photo: UploadFile) -> RedirectResponse:
        old = need_node(conn, node_id)["photo"]
        name = photos.save(await photo.read(), photo_dir)
        repo.set_container_photo(conn, node_id, name)
        photos.delete(old, photo_dir)
        return redirect(f"/n/{node_id}", "Foto gespeichert")

    @app.post("/items/{item_id}/photo")
    async def item_photo(item_id: int, conn: Conn, photo: UploadFile) -> RedirectResponse:
        old = repo.get_item(conn, item_id)["photo"]
        name = photos.save(await photo.read(), photo_dir)
        repo.update_item(conn, item_id, photo=name)
        photos.delete(old, photo_dir)
        return redirect(f"/items/{item_id}", "Foto gespeichert")

    # --- Umlagern: aufnehmen (Cookie), am Ziel-Behälter ablegen ------------------

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

    return app
