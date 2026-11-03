"""KP Lager – Server für Windows (Debug/Entwicklung oder kleiner Heimbetrieb).

Startet die App lokal mit uvicorn. Daten: %LOCALAPPDATA%\\KP Lager Server\\data (Standard).
Gedacht für das Debuggen auf dem PC; der Dauerbetrieb läuft als Docker-Container (deploy/).

    lager-server.exe                      # http://127.0.0.1:8000
    lager-server.exe --port 8080 --host 0.0.0.0 --data D:\\lager-daten
    lager-server.exe --no-browser

Umgebungsvariablen (LAGER_*) gelten wie in docs/CONFIG.md; Kommandozeile hat Vorrang.
"""

import argparse
import os
import sys
import threading
import webbrowser
from pathlib import Path


def default_data_dir() -> Path:
    base = os.environ.get("LOCALAPPDATA") or str(Path.home() / ".local" / "share")
    return Path(base) / "KP Lager Server" / "data"


def parse(argv: list[str] | None = None) -> argparse.Namespace:
    p = argparse.ArgumentParser(prog="lager-server", description=__doc__.split("\n")[0])
    p.add_argument("--host", default="127.0.0.1", help="127.0.0.1 = nur dieser PC, 0.0.0.0 = LAN")
    p.add_argument("--port", type=int, default=8000)
    p.add_argument("--data", type=Path, default=None, help="Datenordner (SQLite, Fotos, Backups)")
    p.add_argument("--no-browser", action="store_true", help="Browser nicht automatisch öffnen")
    p.add_argument("--no-d30", action="store_true", help="D30-Direktdruck (Bluetooth) abschalten")
    return p.parse_args(argv)


def configure(args: argparse.Namespace) -> Path:
    data = args.data or Path(os.environ.get("LAGER_DATA_DIR") or default_data_dir())
    data.mkdir(parents=True, exist_ok=True)
    os.environ["LAGER_DATA_DIR"] = str(data)
    shown = "localhost" if args.host in ("127.0.0.1", "0.0.0.0") else args.host
    os.environ.setdefault("LAGER_BASE_URL", f"http://{shown}:{args.port}")
    os.environ.setdefault("LAGER_AUTO_BACKUP", "1")
    os.environ["LAGER_D30"] = "0" if args.no_d30 else os.environ.get("LAGER_D30", "1")
    return data


def main(argv: list[str] | None = None) -> None:
    args = parse(argv)
    data = configure(args)
    url = f"http://localhost:{args.port}"
    print(f"KP Lager Server · Daten: {data}\n{url}  (Strg+C beendet)", flush=True)
    if not args.no_browser:
        threading.Timer(1.5, lambda: webbrowser.open(url)).start()
    import uvicorn

    from app.main import app

    uvicorn.run(app, host=args.host, port=args.port, log_level="info")


if __name__ == "__main__":
    main(sys.argv[1:])
