"""PC-Bridge für den D30: lokaler Druckdienst (127.0.0.1), damit ein Server ohne Bluetooth
(Docker) trotzdem Etiketten drucken kann.

Ablauf: Der Server meldet dem Browser, welche Codes gedruckt werden sollen (Einstellung
LAGER_D30_BRIDGE=1); der Browser ruft die Bridge auf dem PC auf; die Bridge holt die Etikettenbilder
vom Server (`/labels/img/<CODE>.png`) und druckt sie per Bluetooth (`app.d30`). Danach meldet der
Browser dem Server „gedruckt“ (`/d30/printed`).

Sicherheit: nur auf 127.0.0.1, nur Anfragen der eingetragenen Server-Adresse (CORS/Origin),
Bilder werden nur von diesem Server geholt, höchstens `d30.MAX_LABELS` Codes je Auftrag.
"""

import io
import json
import re
from collections.abc import Callable
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from typing import Any
from urllib.parse import urlsplit

import httpx
from PIL import Image

from app import d30

DEFAULT_PORT = 8765
CODE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9-]{2,19}$")

Fetch = Callable[[str], Image.Image]
Printer = Callable[[list[Image.Image]], None]
Status = Callable[[], tuple[bool, str]]


def origin_of(url: str) -> str:
    parts = urlsplit(url)
    return f"{parts.scheme}://{parts.netloc}"


def http_fetch(server: str, verify: str | bool = True) -> Fetch:
    """Etikettenbild vom Server holen (eigene CA über `verify` = Pfad der CA-Datei)."""

    def fetch(code: str) -> Image.Image:
        resp = httpx.get(f"{server}/labels/img/{code}.png", verify=verify, timeout=15)
        resp.raise_for_status()
        return Image.open(io.BytesIO(resp.content)).convert("1")

    return fetch


def make_server(
    server_url: str,
    port: int = DEFAULT_PORT,
    host: str = "127.0.0.1",
    fetch: Fetch | None = None,
    printer: Printer | None = None,
    status: Status | None = None,
    verify: str | bool = True,
) -> ThreadingHTTPServer:
    server_url = server_url.rstrip("/")
    allowed = origin_of(server_url)
    get_image = fetch or http_fetch(server_url, verify)
    send = printer or d30.send
    state = status or (lambda: d30.status())

    class Handler(BaseHTTPRequestHandler):
        def log_message(self, format: str, *args: Any) -> None:  # leise
            return

        def _origin_ok(self) -> bool:
            origin = self.headers.get("Origin")
            return origin is None or origin == allowed

        def _reply(self, code: int, body: dict[str, Any]) -> None:
            data = json.dumps(body).encode()
            self.send_response(code)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(data)))
            origin = self.headers.get("Origin")
            if origin == allowed:
                self.send_header("Access-Control-Allow-Origin", origin)
                self.send_header("Access-Control-Allow-Private-Network", "true")
                self.send_header("Vary", "Origin")
            self.end_headers()
            self.wfile.write(data)

        def do_OPTIONS(self) -> None:
            if not self._origin_ok():
                return self._reply(403, {"error": "Origin nicht erlaubt"})
            self.send_response(204)
            self.send_header("Access-Control-Allow-Origin", allowed)
            self.send_header("Access-Control-Allow-Methods", "GET, POST, OPTIONS")
            self.send_header("Access-Control-Allow-Headers", "Content-Type")
            self.send_header("Access-Control-Allow-Private-Network", "true")
            self.send_header("Access-Control-Max-Age", "600")
            self.send_header("Vary", "Origin")
            self.end_headers()

        def do_GET(self) -> None:
            if not self._origin_ok():
                return self._reply(403, {"error": "Origin nicht erlaubt"})
            if self.path.split("?")[0] != "/status":
                return self._reply(404, {"error": "unbekannt"})
            ok, msg = state()
            self._reply(200, {"bridge": True, "server": allowed, "available": ok, "msg": msg})

        def do_POST(self) -> None:
            if not self._origin_ok():
                return self._reply(403, {"error": "Origin nicht erlaubt"})
            if self.path.split("?")[0] != "/print":
                return self._reply(404, {"error": "unbekannt"})
            try:
                length = int(self.headers.get("Content-Length", "0"))
                codes = json.loads(self.rfile.read(min(length, 10_000)) or b"{}").get("codes", [])
            except (ValueError, AttributeError):
                return self._reply(400, {"error": "Ungültige Anfrage"})
            codes = [str(c).upper() for c in dict.fromkeys(codes)]
            if not codes or any(not CODE.match(c) for c in codes):
                return self._reply(400, {"error": "Codes fehlen oder sind ungültig"})
            if len(codes) > d30.MAX_LABELS:
                return self._reply(400, {"error": f"Höchstens {d30.MAX_LABELS} Etiketten"})
            try:
                images = [get_image(c) for c in codes]
                send(images)
            except Exception as exc:  # Server/Drucker nicht erreichbar → Meldung statt Absturz
                return self._reply(502, {"ok": False, "error": str(exc)[:200]})
            self._reply(200, {"ok": True, "printed": len(images), "codes": codes})

    return ThreadingHTTPServer((host, port), Handler)
