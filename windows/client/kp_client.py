"""KP Lager – Client für Windows: Fenster zum Lager-Server plus D30-PC-Bridge.

* zeigt den Server (Docker oder lokal) in einem eigenen Fenster (Edge WebView2 über pywebview);
  ohne pywebview wird der Standardbrowser geöffnet,
* startet die D30-Bridge auf 127.0.0.1:8765, damit Etiketten von einem Server ohne Bluetooth
  auf den D30 am PC gedruckt werden können (Server mit LAGER_D30_BRIDGE=1).

    lager-client.exe                          # fragt beim ersten Start nach der Server-Adresse
    lager-client.exe --server https://lager.home.lan
    lager-client.exe --bridge-only            # nur die Bridge, kein Fenster
    lager-client.exe --ca C:\\pfad\\ca.crt      # eigene CA des Servers (sonst Windows-Zertifikate)

Einstellungen: %APPDATA%\\KP Lager Client\\config.json
"""

import argparse
import json
import os
import sys
import threading
import webbrowser
from pathlib import Path
from typing import Any

DEFAULT_SERVER = "https://lager.home.lan"


def config_path() -> Path:
    base = os.environ.get("APPDATA") or str(Path.home() / ".config")
    return Path(base) / "KP Lager Client" / "config.json"


def normalize_url(raw: str) -> str:
    """„lager.home.lan“ -> https://lager.home.lan; Schrägstrich am Ende weg."""
    raw = raw.strip().rstrip("/")
    if not raw:
        return ""
    if "://" not in raw:
        raw = "https://" + raw
    return raw


def load_config(path: Path | None = None) -> dict[str, Any]:
    path = path or config_path()
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {}
    return data if isinstance(data, dict) else {}


def save_config(cfg: dict[str, Any], path: Path | None = None) -> None:
    path = path or config_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(cfg, indent=2, ensure_ascii=False), encoding="utf-8")


def parse(argv: list[str] | None = None) -> argparse.Namespace:
    p = argparse.ArgumentParser(prog="lager-client", description=__doc__.split("\n")[0])
    p.add_argument("--server", default="", help=f"Adresse des Lagers, z. B. {DEFAULT_SERVER}")
    p.add_argument("--ca", default="", help="Datei mit der eigenen CA des Servers (ca.crt)")
    p.add_argument("--port", type=int, default=8765, help="Port der D30-Bridge")
    p.add_argument("--bridge-only", action="store_true", help="nur D30-Bridge, kein Fenster")
    p.add_argument("--no-bridge", action="store_true", help="D30-Bridge nicht starten")
    p.add_argument("--reset", action="store_true", help="gespeicherte Einstellungen vergessen")
    return p.parse_args(argv)


def resolve(args: argparse.Namespace, cfg: dict[str, Any]) -> dict[str, Any]:
    """Kommandozeile > gespeicherte Einstellungen > Standard; Ergebnis wird gespeichert."""
    server = normalize_url(args.server) or normalize_url(str(cfg.get("server", "")))
    return {"server": server, "ca": args.ca or str(cfg.get("ca", ""))}


def ask_server() -> str:
    """Erster Start: Adresse abfragen (tkinter gehört zu Python und steckt im Installer)."""
    try:
        import tkinter
        from tkinter import simpledialog

        root = tkinter.Tk()
        root.withdraw()
        answer = simpledialog.askstring(
            "KP Lager", "Adresse des Lagers:", initialvalue=DEFAULT_SERVER, parent=root
        )
        root.destroy()
        return normalize_url(answer or "")
    except Exception:
        return DEFAULT_SERVER


def start_bridge(server: str, ca: str, port: int) -> threading.Thread | None:
    from app import d30_bridge

    try:
        srv = d30_bridge.make_server(server, port=port, verify=ca or True)
    except OSError as exc:  # Port belegt (zweiter Client läuft schon)
        print(f"D30-Bridge nicht gestartet: {exc}", file=sys.stderr)
        return None
    thread = threading.Thread(target=srv.serve_forever, name="d30-bridge", daemon=True)
    thread.start()
    print(f"D30-Bridge läuft auf http://127.0.0.1:{port} für {server}", flush=True)
    return thread


def open_window(server: str) -> None:
    try:
        import webview  # pywebview
    except ImportError:
        webbrowser.open(server)
        threading.Event().wait()  # Bridge am Leben halten, bis das Fenster/der Prozess endet
        return
    webview.create_window("KP Lager", server, width=1200, height=800, min_size=(420, 600))
    webview.start()


def main(argv: list[str] | None = None) -> int:
    args = parse(argv)
    cfg = {} if args.reset else load_config()
    chosen = resolve(args, cfg)
    if not chosen["server"]:
        chosen["server"] = ask_server()
    if not chosen["server"]:
        return 1
    save_config(chosen)
    if not args.no_bridge:
        start_bridge(chosen["server"], chosen["ca"], args.port)
    if args.bridge_only:
        threading.Event().wait()
        return 0
    open_window(chosen["server"])
    return 0


if __name__ == "__main__":
    sys.exit(main())
