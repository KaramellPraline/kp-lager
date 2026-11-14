"""App-Fabrik: Static-Mounts, REST-API, Fehlerbehandlung, Middleware und alle Routenmodule."""

import sqlite3
from typing import Any

from fastapi import FastAPI, Request
from fastapi.responses import RedirectResponse, Response
from fastapi.staticfiles import StaticFiles

from app import api, scheduler
from app.config import Settings
from app.db import connect
from app.deps import get_conn
from app.repo import LagerError
from app.web.routes import ROUTES
from app.web.shared import ADD_TABS, APP_DIR, APP_NAME, Ctx, redirect


def create_app(settings: Settings) -> FastAPI:
    app = FastAPI(title=APP_NAME)
    app.state.settings = settings  # für die Verbindung je Request (app.deps.get_conn)
    app.mount("/static", StaticFiles(directory=APP_DIR / "static"), name="static")
    connect(settings.db_path).close()  # Migrationen beim Start
    ctx = Ctx(settings)
    ctx.photo_dir.mkdir(parents=True, exist_ok=True)
    app.mount("/photos", StaticFiles(directory=ctx.photo_dir), name="photos")
    ctx.sheet_dir.mkdir(parents=True, exist_ok=True)
    app.mount("/datasheets", StaticFiles(directory=ctx.sheet_dir), name="datasheets")

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

    for module in ROUTES:
        module.register(app, ctx)

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

    return app
