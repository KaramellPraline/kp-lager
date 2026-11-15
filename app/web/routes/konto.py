"""Anmeldung und Benutzer: `/login`, `/einrichten` (erster Admin), `/logout`,
Einstellungen › Benutzer (eigenes Passwort, Benutzerverwaltung für Admins)."""

from typing import Annotated, Any

from fastapi import FastAPI, Form, Request
from fastapi.responses import HTMLResponse, RedirectResponse, Response

from app import auth, prefs
from app.repo import LagerError
from app.web.guard import client_ip, set_session_cookie
from app.web.shared import Conn, Ctx, redirect, templates


def register(app: FastAPI, ctx: Ctx) -> None:
    settings = ctx.settings
    render = ctx.render

    def page(request: Request, conn: Conn, template: str, **data: Any) -> HTMLResponse:
        """Eigenständige Seite ohne Navigation (Login, Einrichten)."""
        data.setdefault("error", "")
        data["APP_NAME"] = prefs.raw(conn, "app_name")
        data["THEME"] = prefs.raw(conn, "theme")
        resp = templates.TemplateResponse(request, template, data)
        resp.headers["Cache-Control"] = "no-store"  # nie als Offline-Fassung speichern
        resp.headers["X-Lager-Login"] = "1"
        return resp

    def logged_in(request: Request, conn: Conn, user_id: int, target: str) -> RedirectResponse:
        days = prefs.number(conn, "session_days")
        token = auth.new_session(
            conn, user_id, days, client_ip(request), request.headers.get("user-agent", "")
        )
        resp = RedirectResponse(auth.safe_next(target), status_code=303)
        set_session_cookie(resp, request, token, days)
        return resp

    # --- Login, Einrichten, Abmelden --------------------------------------------------------

    @app.get("/login", response_model=None)
    def login_page(request: Request, conn: Conn, next: str = "/") -> Response:
        if not settings.auth:
            return RedirectResponse("/", status_code=303)
        if not auth.has_users(conn):
            return RedirectResponse("/einrichten", status_code=303)
        return page(request, conn, "login.html", next=auth.safe_next(next), name="")

    @app.post("/login", response_model=None)
    def login(
        request: Request,
        conn: Conn,
        name: Annotated[str, Form()] = "",
        password: Annotated[str, Form()] = "",
        next: Annotated[str, Form()] = "/",
    ) -> Response:
        if not settings.auth:
            return RedirectResponse("/", status_code=303)
        try:
            user = auth.authenticate(conn, name, password, client_ip(request))
        except LagerError as exc:
            return page(
                request, conn, "login.html", next=auth.safe_next(next), name=name[:40],
                error=str(exc),
            )  # fmt: skip
        return logged_in(request, conn, user["id"], next)

    @app.get("/einrichten", response_model=None)
    def setup_page(request: Request, conn: Conn) -> Response:
        if auth.has_users(conn):
            return RedirectResponse("/login", status_code=303)
        return page(request, conn, "einrichten.html", name="", auth_on=settings.auth)

    @app.post("/einrichten", response_model=None)
    def setup(
        request: Request,
        conn: Conn,
        name: Annotated[str, Form()] = "",
        password: Annotated[str, Form()] = "",
        password2: Annotated[str, Form()] = "",
    ) -> Response:
        if auth.has_users(conn):  # nur beim allerersten Start
            return RedirectResponse("/login", status_code=303)
        try:
            if password != password2:
                raise LagerError("Die beiden Passwörter sind verschieden")
            user_id = auth.create_user(conn, name, password, "admin")
        except LagerError as exc:
            return page(
                request, conn, "einrichten.html", name=name[:40], error=str(exc),
                auth_on=settings.auth,
            )  # fmt: skip
        return logged_in(request, conn, user_id, "/")

    @app.post("/logout")
    def logout(request: Request, conn: Conn) -> RedirectResponse:
        auth.end_session(conn, request.cookies.get(auth.COOKIE, ""))
        resp = RedirectResponse("/login" if settings.auth else "/", status_code=303)
        resp.delete_cookie(auth.COOKIE, path="/")
        return resp

    # --- Einstellungen › Benutzer -----------------------------------------------------------

    def me(request: Request) -> dict[str, Any] | None:
        user: dict[str, Any] | None = getattr(request.state, "user", None)
        return user

    def is_admin(request: Request) -> bool:
        user = me(request)
        return not settings.auth or (user is not None and user["role"] == "admin")

    @app.get("/settings/benutzer", response_class=HTMLResponse)
    def users_page(request: Request, conn: Conn) -> HTMLResponse:
        admin = is_admin(request)
        return render(
            request,
            conn,
            "settings_benutzer.html",
            tab="benutzer",
            admin=admin,
            users=auth.users(conn) if admin else [],
            roles=auth.ROLES,
            groups=prefs.groups("benutzer") if admin else {},
            values=prefs.values(conn),
            auth_on=settings.auth,
            sessions=auth.sessions_of(conn, me(request)["id"]) if me(request) else 0,  # type: ignore[index]
        )

    @app.post("/settings/konto/passwort")
    def own_password(
        request: Request,
        conn: Conn,
        old: Annotated[str, Form()] = "",
        new: Annotated[str, Form()] = "",
        new2: Annotated[str, Form()] = "",
    ) -> RedirectResponse:
        user = me(request)
        if user is None:
            raise LagerError("Nur mit Anmeldung")
        if new != new2:
            raise LagerError("Die beiden neuen Passwörter sind verschieden")
        auth.change_own_password(conn, user["id"], old, new, request.cookies.get(auth.COOKIE, ""))
        return redirect("/settings/benutzer", "Passwort geändert – andere Geräte sind abgemeldet")

    @app.post("/settings/benutzer")
    def user_create(
        conn: Conn,
        name: Annotated[str, Form()] = "",
        password: Annotated[str, Form()] = "",
        role: Annotated[str, Form()] = "nutzer",
    ) -> RedirectResponse:
        auth.create_user(conn, name, password, role)
        return redirect("/settings/benutzer", f"Benutzer „{name.strip()}“ angelegt")

    @app.post("/settings/benutzer/{user_id}/rolle")
    def user_role(user_id: int, conn: Conn, role: Annotated[str, Form()]) -> RedirectResponse:
        auth.set_role(conn, user_id, role)
        return redirect("/settings/benutzer", f"Rolle: {auth.ROLES.get(role, role)}")

    @app.post("/settings/benutzer/{user_id}/passwort")
    def user_reset(
        user_id: int, conn: Conn, password: Annotated[str, Form()] = ""
    ) -> RedirectResponse:
        auth.set_password(conn, user_id, password)
        return redirect("/settings/benutzer", "Passwort gesetzt – der Benutzer ist abgemeldet")

    @app.post("/settings/benutzer/{user_id}/loeschen", response_model=None)
    def user_delete(request: Request, user_id: int, conn: Conn) -> Response:
        name = auth.delete_user(conn, user_id)
        resp = redirect("/settings/benutzer", f"Benutzer „{name}“ gelöscht")
        user = me(request)
        if user is not None and user["id"] == user_id:  # sich selbst gelöscht: abgemeldet
            resp = redirect("/login", f"Benutzer „{name}“ gelöscht")
            resp.delete_cookie(auth.COOKIE, path="/")
        return resp

    @app.post("/settings/benutzer/anmeldung")
    async def user_prefs(request: Request, conn: Conn) -> RedirectResponse:
        form = await request.form()
        prefs.save(conn, {k: str(v) for k, v in form.items()}, prefs.keys_of("benutzer"))
        return redirect("/settings/benutzer", "Einstellungen gespeichert")
