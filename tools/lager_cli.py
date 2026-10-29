"""KP Lager auf der Kommandozeile. Lesen ohne Schlüssel, Schreiben mit LAGER_API_KEY.

Beispiele:
  uv run python tools/lager_cli.py suche lötzinn
  uv run python tools/lager_cli.py teil ART-0007
  uv run python tools/lager_cli.py box EUR-003
  uv run python tools/lager_cli.py typen
  LAGER_API_KEY=… uv run python tools/lager_cli.py neu KIS-001 "3 Rollen Lötzinn und 50 M3 Muttern"
  LAGER_API_KEY=… uv run python tools/lager_cli.py entnehmen ART-0007 --menge 2
  LAGER_API_KEY=… uv run python tools/lager_cli.py umlagern ART-0007 EUR-003
  uv run python tools/lager_cli.py schema     # Kategorien, Felder, Arten (immer aktuell)
  LAGER_API_KEY=… uv run python tools/lager_cli.py teil-neu BOX-001 CBL --anzahl 2 \
      --spec plug_a=USB-A --spec plug_b=USB-C --spec length=1
  uv run python tools/lager_cli.py einkauf | wert [BOX] | trockner | drucke
  LAGER_API_KEY=… uv run python tools/lager_cli.py massen move c5,i12 --ziel EUR-003
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
    sub.add_parser("schema", help="Kategorien, Felder, Arten (live vom Server)")
    sub.add_parser("einkauf", help="Einkaufsliste mit Bedarf und Summe")
    sub.add_parser("wert", help="Lagerwert (optional Behälter)").add_argument(
        "box", nargs="?", default=""
    )
    sub.add_parser("trockner", help="Filament-Trockner")
    sub.add_parser("drucke", help="Eingelesene Slicer-Drucke")
    p = sub.add_parser("teil-neu", help="Teil mit Kategorie anlegen (Schlüssel nötig)")
    p.add_argument("box")
    p.add_argument("kat", help="Präfix, z. B. CBL – gültige Werte: lager schema")
    p.add_argument("name", nargs="*", default=[])
    p.add_argument("--anzahl", type=int, default=1)
    p.add_argument("--menge", type=int)
    p.add_argument("--spec", action="append", default=[], metavar="KEY=WERT")
    p = sub.add_parser("massen", help="Viele Teile/Behälter ändern (Schlüssel nötig)")
    p.add_argument("aktion", help="move, tag, cat, min, unit, price, list_on, list_off, label, ...")
    p.add_argument("refs", help="Komma-getrennt: i12 (Teil), c5 (Behälter)")
    p.add_argument("--wert", default="")
    p.add_argument("--ziel", default="")
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
        elif args.cmd == "schema":
            data = c.schema(fresh=True)
        elif args.cmd == "einkauf":
            data = c.shopping()
        elif args.cmd == "wert":
            data = c.value(args.box)
        elif args.cmd == "trockner":
            data = c.dryer()
        elif args.cmd == "drucke":
            data = c.print_jobs()
        elif args.cmd == "teil-neu":
            valid = {x["prefix"] for x in c.schema()["categories"]}
            if args.kat.upper() not in valid:
                raise LagerError(
                    f"Unbekannte Kategorie {args.kat}. Gültig: {', '.join(sorted(valid))}"
                )
            specs = dict(s.split("=", 1) for s in args.spec if "=" in s)
            name = " ".join(args.name)
            data = c.add_typed(args.box, name, args.kat, args.menge, "", args.anzahl, specs)
        elif args.cmd == "massen":
            data = {"result": c.bulk(args.refs.split(","), args.aktion, args.wert, args.ziel)}
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
    if cmd == "schema" and isinstance(data, dict):
        for cat in data["categories"]:
            keys = ", ".join(f["key"] for f in cat["fields"])
            single = " [Einzelstück]" if cat["single_piece"] else ""
            print(
                f"{cat['prefix']}  {cat['name']}{single}" + (f"   Felder: {keys}" if keys else "")
            )
        print(
            "Arten: "
            + ", ".join(f"{k['key']}={k['prefix'] or '-'}" for k in data["container_kinds"])
        )
        print("Aktionen: " + ", ".join(data["bulk_actions"]))
        return
    if cmd == "einkauf" and isinstance(data, dict):
        for i in data["items"]:
            print(f"{i['need']}x {fmt_item(i)}" + (f"  = {i['cost']:.2f} EUR" if i["cost"] else ""))
        print(f"Summe: {data['total_eur']:.2f} EUR")
        return
    if cmd in ("wert", "massen") and isinstance(data, dict):
        print(" · ".join(f"{k}: {v}" for k, v in data.items()))
        return
    if cmd == "trockner" and isinstance(data, dict):
        for r in data["running"]:
            print(f"läuft: {r['item_name']} {r['program']} fertig {r['ends_at']}")
        print(f"{len(data['running'])} laufend, {len(data['programs'])} Programme")
        return
    if cmd == "drucke" and isinstance(data, list):
        for j in data:
            print(f"{j['name']}  {j['total_g']:.1f} g  {'gebucht' if j['booked_at'] else 'offen'}")
        return
    if cmd == "teil-neu" and isinstance(data, list):
        for i in data:
            print("angelegt: " + fmt_item(i))
        return
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
