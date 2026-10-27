"""KP Lager auf der Kommandozeile. Lesen ohne Schlüssel, Schreiben mit LAGER_API_KEY.

Beispiele:
  uv run python tools/lager_cli.py suche lötzinn
  uv run python tools/lager_cli.py teil ART-0007
  uv run python tools/lager_cli.py box EUR-003
  uv run python tools/lager_cli.py typen
  LAGER_API_KEY=… uv run python tools/lager_cli.py neu KIS-001 "3 Rollen Lötzinn und 50 M3 Muttern"
  LAGER_API_KEY=… uv run python tools/lager_cli.py entnehmen ART-0007 --menge 2
  LAGER_API_KEY=… uv run python tools/lager_cli.py umlagern ART-0007 EUR-003
"""

import argparse
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
from lager_client import LagerClient, LagerError, fmt_item  # noqa: E402


def main(argv: list[str] | None = None, client: LagerClient | None = None) -> int:
    ap = argparse.ArgumentParser(prog="lager", description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)  # fmt: skip
    ap.add_argument("--json", action="store_true", help="Rohdaten als JSON ausgeben")
    sub = ap.add_subparsers(dest="cmd", required=True)
    sub.add_parser("suche", help="Teile und Behälter suchen").add_argument("q", nargs="+")
    sub.add_parser("teil", help="Teil per Code/ID").add_argument("ref")
    sub.add_parser("box", help="Behälter per Code/ID mit Inhalt").add_argument("ref")
    sub.add_parser("orte", help="Oberste Ebene (Räume)")
    sub.add_parser("typen", help="Typen")
    p = sub.add_parser("neu", help="Teile eintragen (Schlüssel nötig)")
    p.add_argument("box")
    p.add_argument("text", nargs="+")
    p = sub.add_parser("entnehmen", help="Teil entnehmen (Schlüssel nötig)")
    p.add_argument("ref")
    p.add_argument("--menge", type=int, default=1)
    p = sub.add_parser("umlagern", help="Teil in anderen Behälter (Schlüssel nötig)")
    p.add_argument("ref")
    p.add_argument("box")
    args = ap.parse_args(argv)
    c = client or LagerClient()
    try:
        if args.cmd == "suche":
            data: object = c.search(" ".join(args.q))
        elif args.cmd == "teil":
            data = c.item(args.ref)
        elif args.cmd == "box":
            data = c.container(args.ref)
        elif args.cmd == "orte":
            data = c.roots()
        elif args.cmd == "typen":
            data = c.types()
        elif args.cmd == "neu":
            data = c.add(args.box, " ".join(args.text))
        elif args.cmd == "entnehmen":
            data = c.take(args.ref, args.menge)
        else:
            data = c.move(args.ref, args.box)
    except LagerError as exc:
        print(f"Fehler: {exc}", file=sys.stderr)
        return 1
    if args.json:
        print(json.dumps(data, ensure_ascii=False, indent=2))
        return 0
    print_human(args.cmd, data)
    return 0


def print_human(cmd: str, data: object) -> None:
    if cmd == "suche" and isinstance(data, dict):
        for i in data["items"]:
            print(fmt_item(i))
        for b in data["containers"]:
            print(f"[Behälter] {b['name']} {b['code'] or ''} @ {b['path']}")
        if not data["items"] and not data["containers"]:
            print("Nichts gefunden.")
    elif cmd == "box" and isinstance(data, dict):
        print(f"{data['name']} {data['code'] or ''} @ {data['path']}")
        for b in data["children"]:
            print(f"  [Behälter] {b['name']} {b['code'] or ''}")
        for i in data["items"]:
            print("  " + fmt_item(i))
    elif cmd == "teil" and isinstance(data, dict):
        print(fmt_item(data))
    elif cmd in ("neu",) and isinstance(data, list):
        for i in data:
            print("eingetragen: " + fmt_item(i))
    elif cmd == "entnehmen" and isinstance(data, dict):
        print(f"entnommen (Entnahme #{data['withdrawal']}): " + fmt_item(data["item"]))
    elif cmd == "umlagern" and isinstance(data, dict):
        print("umgelagert: " + fmt_item(data))
    elif isinstance(data, list):
        for row in data:
            print(" · ".join(str(v) for v in row.values() if v is not None))


if __name__ == "__main__":
    raise SystemExit(main())
