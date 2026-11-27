"""Gemeinsames für alle Routenmodule der Oberfläche: Templates, Redirect, Cookies,
Formular-Hilfen, kleine Abfragen und der Kontext `Ctx` (Einstellungen, Rendern, Direktdruck).

Jedes Modul in `app/web/routes/` hat dieselbe Form: `register(app, ctx)`.
"""

import json
import sqlite3
from collections.abc import Callable
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Annotated, Any
from urllib.parse import quote

from fastapi import Depends, HTTPException, Request
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.templating import Jinja2Templates

from app import (
    auth,
    cables,
    cards,
    codes,
    d30,
    icons,
    kasten,
    kinds,
    labels,
    prefs,
    printmq,
    psus,
    quick,
    repo,
    value,
)
from app.config import Settings
from app.deps import Conn as Conn  # Verbindung je Request, für alle Routen
from app.repo import LagerError

APP_DIR = Path(__file__).parent.parent  # app/ (Templates, Static)
APP_NAME = "KP Lager"
CARRY_COOKIE = "carry"
ADD_TABS = ("/neu", "/neu/behaelter", "/neu/bin")
NL = chr(10)
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
templates.env.globals["CARD_KINDS"] = cards.KIND_INFO
templates.env.globals["icon"] = icons.icon
templates.env.globals["euro"] = value.euro
templates.env.globals["EURO_DIMS"] = kinds.EURO_DIMS


# --- Eingaben umwandeln -------------------------------------------------------------


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


async def spec_form(request: Request) -> dict[str, str]:
    """Alle Formularfelder spec_* (Auswahllisten für Filament/Harz beim Anlegen)."""
    form = await request.form()
    return {k: v for k, v in form.items() if k.startswith("spec_") and isinstance(v, str)}


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


FormDict = Annotated[dict[str, str], Depends(form_fields)]  # alle Felder als Text
FormLists = Annotated[dict[str, list[str]], Depends(form_lists)]  # mehrfache Felder als Listen


# --- Antworten, Rücksprung, Cookies -------------------------------------------------


def redirect(url: str, msg: str = "", undo: int | None = None) -> RedirectResponse:
    url, hash_, anchor = url.partition("#")  # Query muss vor den Anker
    if msg:
        url += ("&" if "?" in url else "?") + "msg=" + quote(msg)
    if undo:
        url += ("&" if "?" in url else "?") + f"undo={undo}"
    return RedirectResponse(url + hash_ + anchor, status_code=303)


def safe_back(url: str, default: str) -> str:
    """Nur relative Rücksprung-Adressen der eigenen Seite zulassen."""
    return url if url.startswith("/") and not url.startswith("//") else default


def node_url(container_id: int | None) -> str:
    return f"/n/{container_id}" if container_id else "/"


BRIDGE_MARK = "⟦d30:"  # in der Meldung: Codes, die die PC-Bridge drucken soll
BRIDGE_END = "⟧"
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


def last_target(request: Request) -> int | None:
    ids = recent_targets(request) or recent_ids(request)
    return ids[0] if ids else None


def recent_ids(request: Request) -> list[int]:
    return [int(x) for x in request.cookies.get(RECENT_COOKIE, "").split(",") if x.isdigit()]


# --- Kleine Abfragen, die mehrere Bereiche brauchen ---------------------------------


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


def content_holder(conn: sqlite3.Connection, dest: sqlite3.Row) -> sqlite3.Row | None:
    """Wohin das Inhaltsetikett gehört: der Bin, sonst das Fach im Sortierkasten."""
    if (b := kasten.bin_of(conn, dest["id"])) is not None:
        return b
    return dest if dest["kind"] == "compartment" else None


# --- Kontext für die Routenmodule ---------------------------------------------------


@dataclass(frozen=True)
class Ctx:
    """Was Routen außer der Verbindung (`Conn`) brauchen: Einstellungen und davon Abhängiges."""

    settings: Settings

    def d30_on(self, conn: sqlite3.Connection) -> bool:
        """Direktdruck möglich: Bluetooth am Server (LAGER_D30) oder MQTT-Druck-Agent."""
        return self.settings.d30 or printmq.config(conn) is not None

    def bridge_on(self, conn: sqlite3.Connection) -> bool:
        """PC-Bridge an: LAGER_D30_BRIDGE (Vorrang) oder Schalter unter Anbindungen › Druck."""
        if self.settings.d30_bridge:
            return True
        return not self.settings.d30_bridge_locked and prefs.flag(conn, "d30_bridge")

    def bridge_only(self, conn: sqlite3.Connection) -> bool:
        """Drucken läuft über die PC-Bridge im Browser (kein Direktdruck am Server)."""
        return self.bridge_on(conn) and not self.d30_on(conn)

    @property
    def photo_dir(self) -> Path:
        return self.settings.data_dir / "photos"

    @property
    def sheet_dir(self) -> Path:
        return self.settings.data_dir / "datasheets"

    def render(
        self, request: Request, conn: sqlite3.Connection, name: str, **ctx: Any
    ) -> HTMLResponse:
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
        ctx["D30"] = self.d30_on(conn) or self.bridge_on(conn)
        raw_msg, _, marker = str(ctx["msg"]).partition(BRIDGE_MARK)
        ctx["msg"] = raw_msg
        ctx["bridge_codes"] = marker.removesuffix(BRIDGE_END)
        # signierte Kurzlinks: die PC-Bridge holt die Etikettenbilder ohne Sitzungs-Cookie
        ctx["bridge_tokens"] = json.dumps(
            {c: auth.sign_label(conn, c) for c in ctx["bridge_codes"].split(",") if c}
        )
        ctx["USER"] = getattr(request.state, "user", None)
        ctx["AUTH"] = self.settings.auth
        ctx.setdefault("dims_opts", dims_options(conn))
        ctx.setdefault(
            "dims_kinds", [k for k, _, _ in kinds.ADD_KINDS if k not in ("machine", "dryer")]
        )
        if name in ("node.html", "index.html"):
            ctx["VAL"], ctx["UNPRICED"] = value.totals(conn)
        return templates.TemplateResponse(request, name, ctx)

    def direct_print(self, conn: sqlite3.Connection, codes_: list[str]) -> str:
        """Direktdruck nach dem Eintragen; ein Druckfehler lässt das Eintragen gelten."""
        settings = self.settings
        if self.bridge_only(conn) and codes_:
            return f" · Druck über PC-Bridge{BRIDGE_MARK}{','.join(codes_)}{BRIDGE_END}"
        if not (self.d30_on(conn) and codes_):
            return ""
        try:
            n = d30.print_codes(conn, settings.base_url, codes_)
        except LagerError as exc:
            return f" · nicht gedruckt: {exc}"
        return f" · {n} Etikett{'en' if n != 1 else ''} gedruckt"

    def print_or_queue(
        self, conn: sqlite3.Connection, code: str, text: str, extra: str, back: str
    ) -> RedirectResponse:
        """Druck-Symbol: sofort auf den D30, sonst (Fehler/kein D30) in die Warteschlange."""
        settings = self.settings
        if self.d30_on(conn):
            try:
                d30.print_codes(conn, settings.base_url, [code])
                return redirect(back, f"Etikett {code} gedruckt")
            except LagerError as exc:
                labels.enqueue(conn, code, text, extra)
                return redirect(back, f"Druck nicht möglich ({exc}) – {code} in der Warteschlange")
        labels.enqueue(conn, code, text, extra)
        return redirect(back, f"Etikett {code} in Warteschlange")
