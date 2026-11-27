"""Einstellungen › Anbindungen: alles Externe an einem Ort – API & Schlüssel, MCP, Home Assistant,
Druck (A4/IPP, MQTT-Druck-Agent, D30-PC-Bridge) und externes Backup, je mit Status und „Testen“.

Geheimnisse (MQTT-Passwort) werden nie wieder angezeigt, nur „gesetzt“; Umgebungsvariablen haben
Vorrang und erscheinen als „per Umgebung gesetzt“.
"""

import json
import os
import socket
import sqlite3
import tempfile
from pathlib import Path
from typing import Annotated, Any
from urllib.parse import urlparse

from fastapi import FastAPI, Form, Request
from fastapi.responses import HTMLResponse, RedirectResponse

from app import apikeys, codes, prefs, printmq, scheduler
from app.repo import LagerError
from app.web.shared import Conn, Ctx, FormDict, redirect

URL = "/settings/anbindungen"


def _status(ok: bool | None, text: str) -> dict[str, str]:
    """Status-Kennzeichen einer Karte: ok (grün), err (rot), sonst neutral."""
    return {"cls": "ok" if ok else ("err" if ok is False else ""), "text": text}


def mcp_config(base_url: str) -> str:
    return json.dumps(
        {
            "mcpServers": {
                "kp-lager": {
                    "command": "uv",
                    "args": ["run", "--directory", "C:/dev/kp-lager", "--group", "mcp",
                             "python", "tools/lager_mcp.py"],
                    "env": {"LAGER_URL": base_url, "LAGER_API_KEY": "kpl_…"},
                }
            }
        },
        indent=2,
        ensure_ascii=False,
    )  # fmt: skip


def ha_yaml(base_url: str) -> str:
    return f"""rest:
  - resource: {base_url}/api/v1/ha
    scan_interval: 300
    verify_ssl: false   # eigene CA: besser CA in HA hinterlegen und true lassen
    headers:
      X-API-Key: !secret kp_lager_key
    sensor:
      - name: "Lager nachkaufen"
        unique_id: kp_lager_nachkaufen
        value_template: "{{{{ value_json.state }}}}"
        unit_of_measurement: "Teile"
        json_attributes_path: "$.attributes"
        json_attributes: [to_buy_items, expired, expiring, inventory_due, value_eur, backup_ok]
"""


def ipp_reachable(url: str, timeout: float = 3.0) -> tuple[bool, str]:
    p = urlparse(url)
    if not p.hostname:
        return False, "Kein A4-Drucker eingetragen"
    port = p.port or (443 if p.scheme in ("ipps", "https") else 631)
    try:
        socket.create_connection((p.hostname, port), timeout=timeout).close()
    except OSError as exc:
        return False, f"Drucker nicht erreichbar ({p.hostname}:{port}): {exc}"[:160]
    return True, f"Drucker erreichbar ({p.hostname}:{port})"


def backup_writable(target: str) -> tuple[bool, str]:
    if not target:
        return False, "Kein Zielordner eingestellt"
    folder = Path(target)
    if not folder.is_dir():
        return False, f"Ordner {target} gibt es nicht (im Docker-Container als Volume einbinden)"
    try:
        with tempfile.NamedTemporaryFile(dir=folder, prefix=".kp-lager-test-"):
            pass
    except OSError as exc:
        return False, f"Ordner {target} nicht beschreibbar: {exc}"[:160]
    return True, f"Ordner {target} ist beschreibbar"


def register(app: FastAPI, ctx: Ctx) -> None:
    settings = ctx.settings
    render = ctx.render

    def page(request: Request, conn: sqlite3.Connection, new_key: str | None = None) -> Any:
        keys = apikeys.all_keys(conn)
        read_open = not prefs.flag(conn, "api_read_key")
        write_open = not prefs.flag(conn, "api_write_key")
        if write_open:
            api = _status(False, "Schreiben ohne Schlüssel offen")
        elif read_open and settings.auth:
            api = _status(None, "Lesen ohne Schlüssel offen")
        else:
            api = (
                _status(True, f"{len(keys)} Schlüssel") if keys else _status(None, "kein Schlüssel")
            )
        read_keys = [k for k in keys if k["last_used"]]
        a4_url = codes.get_setting(conn, "a4_printer", "")
        mq = printmq.config(conn)
        mq_db = printmq.from_db(conn)
        bridge_env = settings.d30_bridge_locked
        target = scheduler.extern_target(conn)
        ext_error = codes.get_setting(conn, "backup_extern_error", "")
        ext_last = codes.get_setting(conn, "backup_extern_last", "")
        if not target:
            backup = _status(None, "nicht eingerichtet")
        elif ext_error:
            backup = _status(False, "Fehler")
        else:
            backup = _status(
                True if ext_last else None, "gesichert" if ext_last else "eingerichtet"
            )
        printing = [
            _status(True, "A4 eingerichtet") if a4_url else _status(None, "A4 nicht eingerichtet"),
            _status(True, "MQTT eingerichtet") if mq else _status(None, "MQTT nicht eingerichtet"),
        ]
        return render(
            request,
            conn,
            "settings_anbindungen.html",
            tab="anbindungen",
            base_url=settings.base_url,
            keys=keys,
            new_key=new_key,
            groups=prefs.groups("anbindungen"),
            values=prefs.values(conn),
            api=api,
            read_open=read_open,
            mcp_json=mcp_config(settings.base_url),
            ha_yaml=ha_yaml(settings.base_url),
            ha=_status(True, "Schlüssel benutzt")
            if read_keys
            else _status(None, "bereit" if read_open else "Lese-Schlüssel nötig"),
            a4_url=a4_url,
            mq=mq,
            mq_env=printmq.env_set(),
            mq_form={
                "host": mq_db.host if mq_db else "",
                "port": str(mq_db.port) if mq_db else "1883",
                "user": mq_db.user if mq_db else "",
                "topic": mq_db.topic if mq_db else printmq.BASE,
                "password_set": bool(codes.get_secret(conn, "mqtt_password")),
            },
            printing=printing,
            d30_server=settings.d30,
            bridge_on=ctx.bridge_on(conn),
            bridge_env=bridge_env,
            target=target,
            target_env=not prefs.raw(conn, "backup_extern").strip()
            and bool(os.environ.get("LAGER_BACKUP_EXTERN", "")),
            ext_last=ext_last,
            ext_error=ext_error,
            backup=backup,
        )

    @app.get(URL, response_class=HTMLResponse)
    def anbindungen_page(request: Request, conn: Conn) -> HTMLResponse:
        result: HTMLResponse = page(request, conn)
        return result

    # --- API & Schlüssel (alte Pfade unter /settings/admin bleiben gültig) ------------------

    @app.post("/settings/admin/keys", response_class=HTMLResponse)
    @app.post(f"{URL}/keys", response_class=HTMLResponse)
    def create_key(
        request: Request,
        conn: Conn,
        name: Annotated[str, Form()],
        scope: Annotated[str, Form()] = "write",
    ) -> HTMLResponse:
        """Neuen API-Schlüssel erzeugen und genau einmal anzeigen (nie in der URL)."""
        result: HTMLResponse = page(request, conn, new_key=apikeys.create(conn, name, scope))
        return result

    @app.post("/settings/admin/keys/{key_id}/delete")
    @app.post(URL + "/keys/{key_id}/delete")
    def delete_key(key_id: int, conn: Conn) -> RedirectResponse:
        apikeys.delete(conn, key_id)
        return redirect(f"{URL}#api", "Schlüssel gelöscht")

    @app.post(f"{URL}/api")
    async def save_api(request: Request, conn: Conn) -> RedirectResponse:
        form = await request.form()
        prefs.save(conn, {k: str(v) for k, v in form.items()}, prefs.keys_of("API"))
        return redirect(f"{URL}#api", "API-Einstellungen gespeichert")

    # --- Druck ------------------------------------------------------------------------------

    @app.post("/settings/admin/a4drucker")
    @app.post(f"{URL}/a4")
    def save_a4(conn: Conn, form: FormDict) -> RedirectResponse:
        url = form.get("a4_printer", "").strip()
        if url:
            p = urlparse(url)
            if p.scheme not in ("ipp", "ipps", "http", "https") or not p.hostname:
                raise LagerError("Drucker-Adresse ungültig, z. B. ipp://192.168.1.50/ipp/print")
        codes.set_setting(conn, "a4_printer", url)
        return redirect(f"{URL}#druck", "A4-Drucker gespeichert")

    @app.post(f"{URL}/mqtt")
    def save_mqtt(conn: Conn, form: FormDict) -> RedirectResponse:
        if printmq.env_set():
            raise LagerError("MQTT ist per Umgebung gesetzt (LAGER_PRINT_MQTT) – dort ändern")
        host = form.get("host", "").strip()
        port = form.get("port", "").strip() or "1883"
        if host and (not port.isdigit() or not 0 < int(port) < 65536):
            raise LagerError("Port: Zahl von 1 bis 65535 (Standard 1883)")
        if any(c in host for c in "/ :@") and host:
            raise LagerError("Host ohne Schema und Port eintragen, z. B. 192.168.1.10")
        codes.set_setting(conn, "mqtt_host", host)
        codes.set_setting(conn, "mqtt_port", port)
        codes.set_setting(conn, "mqtt_user", form.get("user", "").strip())
        codes.set_setting(conn, "mqtt_topic", form.get("topic", "").strip().strip("/"))
        if form.get("password_clear"):
            codes.set_secret(conn, "mqtt_password", "")
        elif form.get("password", ""):  # leer = bisheriges Passwort behalten
            codes.set_secret(conn, "mqtt_password", form["password"])
        return redirect(f"{URL}#druck", "MQTT-Druck gespeichert" if host else "MQTT-Druck aus")

    @app.post(f"{URL}/bridge")
    def save_bridge(conn: Conn, form: FormDict) -> RedirectResponse:
        if settings.d30_bridge_locked:
            raise LagerError("D30-Bridge ist per Umgebung gesetzt (LAGER_D30_BRIDGE)")
        prefs.save(conn, {"d30_bridge": form.get("d30_bridge", "")}, {"d30_bridge"})
        return redirect(f"{URL}#druck", "D30-Bridge " + ("an" if form.get("d30_bridge") else "aus"))

    # --- Backup extern ----------------------------------------------------------------------

    @app.post(f"{URL}/backup")
    def save_backup(conn: Conn, form: FormDict) -> RedirectResponse:
        prefs.save(conn, form, {"backup_extern"})
        return redirect(f"{URL}#backup", "Backup-Ziel gespeichert")

    # --- Testen -----------------------------------------------------------------------------

    @app.post(URL + "/test/{what}")
    def test(what: str, conn: Conn) -> RedirectResponse:
        if what == "mqtt":
            cfg = printmq.config(conn)
            ok, msg = printmq.test_connection(cfg) if cfg else (False, "MQTT nicht eingerichtet")
            anchor = "druck"
        elif what == "ipp":
            ok, msg = ipp_reachable(codes.get_setting(conn, "a4_printer", ""))
            anchor = "druck"
        elif what == "backup":
            ok, msg = backup_writable(scheduler.extern_target(conn))
            anchor = "backup"
        else:
            raise LagerError("Unbekannter Test")
        return redirect(f"{URL}#{anchor}", ("Test ok: " if ok else "Test fehlgeschlagen: ") + msg)
