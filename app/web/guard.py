"""Zugangsschutz der Oberfläche als Middleware: Herkunftsprüfung (CSRF) für schreibende
Anfragen, Anmeldung (Sitzungs-Cookie) und Rollen. Modell: docs/SICHERHEIT.md.

Reihenfolge je Anfrage:
1. Schreibende Methode (POST/PUT/PATCH/DELETE) außerhalb von `/api/v1`: `Origin` muss zum
   eigenen Host passen, sonst 403 – auch mit `LAGER_AUTH=0` (eine fremde Webseite soll den Browser
   im LAN nicht fernsteuern können).
2. `LAGER_AUTH=0`: fertig. Freie Pfade (`OPEN`): fertig.
3. Noch kein Benutzer: alles auf `/einrichten`.
4. Gültige Sitzung → `request.state.user`; Nutzer (nicht Admin) kommen nicht in Admin-Bereiche.
5. Sonst: Seiten → `/login?next=…`, HTMX → 401 mit `HX-Redirect`, alles andere → 401.
"""

import re
import sqlite3
from typing import Any
from urllib.parse import quote, urlsplit

from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse, PlainTextResponse, RedirectResponse, Response

from app import apikeys, auth, prefs
from app.config import Settings

UNSAFE = ("POST", "PUT", "PATCH", "DELETE")
OPEN = {
    "/health", "/ca.crt", "/sw.js", "/manifest.webmanifest", "/offline", "/login",
    "/einrichten", "/favicon.ico",
}  # fmt: skip
OPEN_PREFIXES = ("/static/", "/api/v1/")
LABEL_IMG = re.compile(r"^/labels/img/([A-Za-z0-9-]{1,30})\.png$")
# Nur für Admins: Einstellungen (außer dem eigenen Konto), Import/Wiederherstellung, Gesamtarchiv
OWN_ACCOUNT = ("/settings/benutzer", "/settings/konto/")
ADMIN_PREFIXES = ("/settings", "/import", "/export.zip")


def admin_only(path: str, method: str = "GET") -> bool:
    """Admin-Bereich? Die Benutzer-Seite selbst (Ansehen) und /settings/konto/* sind für alle."""
    if (path == OWN_ACCOUNT[0] and method in ("GET", "HEAD")) or path.startswith(OWN_ACCOUNT[1]):
        return False
    return any(path == p or path.startswith(p + "/") for p in ADMIN_PREFIXES)


def is_open(path: str) -> bool:
    return path in OPEN or path == "/api/v1" or path.startswith(OPEN_PREFIXES)


def client_ip(request: Request) -> str:
    """Adresse des Geräts (hinter Caddy setzt uvicorn --proxy-headers sie aus X-Forwarded-For)."""
    return request.client.host if request.client else ""


def is_https(request: Request) -> bool:
    proto = request.headers.get("x-forwarded-proto", "").split(",")[0].strip().lower()
    return request.url.scheme == "https" or proto == "https"


def set_session_cookie(resp: Response, request: Request, token: str, days: int) -> None:
    resp.set_cookie(
        auth.COOKIE, token, max_age=days * 86400, httponly=True, samesite="lax",
        secure=is_https(request), path="/",
    )  # fmt: skip


def login_target(request: Request) -> str:
    """Wohin nach dem Login: die angefragte Seite (GET) bzw. die Seite, von der das Formular kam."""
    if request.method in ("GET", "HEAD"):
        target = request.url.path + (f"?{request.url.query}" if request.url.query else "")
    else:
        current = request.headers.get("hx-current-url") or request.headers.get("referer") or "/"
        parts = urlsplit(current)
        target = parts.path + (f"?{parts.query}" if parts.query else "")
    return auth.safe_next(target)


def _deny(request: Request, status: int, text: str, location: str = "") -> Response:
    """Antwort passend zur Art der Anfrage (Seite, HTMX, fetch/Service Worker)."""
    if request.headers.get("hx-request"):
        headers = {"HX-Redirect": location} if location else {}
        return PlainTextResponse(text, status_code=status, headers=headers)
    navigate = request.headers.get("sec-fetch-mode", "navigate") == "navigate"
    wants_json = "application/json" in request.headers.get("accept", "")
    if location and navigate and not wants_json:
        return RedirectResponse(location, status_code=303)
    return JSONResponse({"ok": False, "error": text, "login": location or None}, status_code=status)


def _connect(settings: Settings) -> sqlite3.Connection:
    """Leichte Verbindung nur für die Prüfung (Schema ist beim Start migriert)."""
    conn = sqlite3.connect(settings.db_path, check_same_thread=False)
    conn.row_factory = sqlite3.Row
    return conn


def install(app: FastAPI, settings: Settings) -> None:
    @app.middleware("http")
    async def guard(request: Request, call_next: Any) -> Response:
        path = request.url.path
        request.state.user = None
        if (
            request.method in UNSAFE
            and not path.startswith("/api/v1")
            and not auth.same_origin(request.headers)
        ):
            return PlainTextResponse(
                "Abgelehnt: Anfrage kam nicht von dieser Seite (Schutz gegen fremde Formulare).",
                status_code=403,
            )
        if not settings.auth or is_open(path):
            resp: Response = await call_next(request)
            return resp

        conn = _connect(settings)
        try:
            if not auth.has_users(conn):
                return _deny(request, 401, "Erst einrichten", "/einrichten")
            token = request.cookies.get(auth.COOKIE, "")
            days = prefs.number(conn, "session_days")
            user, refresh = auth.session_user(conn, token, days)
            if user is None:
                if (m := LABEL_IMG.match(path)) and _label_access(conn, request, m.group(1)):
                    resp = await call_next(request)
                    return resp
                target = login_target(request)
                return _deny(
                    request, 401, "Anmeldung nötig", "/login?next=" + quote(target, safe="/")
                )
        finally:
            conn.close()

        request.state.user = {"id": user["id"], "name": user["name"], "role": user["role"]}
        if user["role"] != "admin" and admin_only(path, request.method):
            return _deny(request, 403, "Nur für Admins")
        resp = await call_next(request)
        if refresh:
            set_session_cookie(resp, request, token, days)
        return resp


def _label_access(conn: sqlite3.Connection, request: Request, code: str) -> bool:
    """Etikettenbild ohne Sitzung: signierter Kurzlink (PC-Bridge) oder API-Schlüssel."""
    token = request.query_params.get("t", "")
    if token and auth.check_label(conn, code, token):
        return True
    key = request.headers.get("x-api-key", "")
    bearer = request.headers.get("authorization", "")
    if not key and bearer.lower().startswith("bearer "):
        key = bearer[7:].strip()
    return bool(key) and apikeys.verify(conn, key, "read")
