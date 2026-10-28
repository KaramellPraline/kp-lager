"""Vorhandene Kabel aufs Schema Stecker A / Stecker B / Länge umstellen (einmalig, wiederholbar).

Betrifft alle Teile mit CBL-Code oder Profil „Kabel“ sowie alle Teile in Behältern mit „Kabel“
im Namen. Noch nicht gedruckte Nicht-CBL-Codes (z. B. ART-0001) bekommen einen CBL-Code.
Ohne --apply nur Vorschau.

  uv run python tools/kabel_umstellen.py            # Vorschau
  uv run python tools/kabel_umstellen.py --apply    # ändern (vorher Backup!)
"""

import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parents[1]))
from app import cables, codes, materials, repo  # noqa: E402
from app.db import connect  # noqa: E402


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--db", default="data/lager.db")
    ap.add_argument("--apply", action="store_true")
    args = ap.parse_args(argv)
    conn = connect(args.db)
    rows = conn.execute(
        "SELECT i.* FROM item i JOIN container c ON c.id = i.container_id"
        " WHERE i.archived = 0 AND (i.code LIKE 'CBL-%' OR i.material = 'cbl'"
        " OR c.name LIKE '%abel%') ORDER BY i.code"
    ).fetchall()
    for item in rows:
        found = materials.specs(item) if item["material"] == "cbl" else {}
        spec = {**cables.parse(item["name"]), **{k: v for k, v in found.items() if v}}
        new_name = cables.name(spec) or item["name"]
        code = item["code"]
        if code and not code.startswith("CBL-") and not item["label_printed"]:
            code = "(neuer CBL-Code)" if not args.apply else codes.reserve(conn, "CBL", 1)[0]
        print(f"{item['code'] or '-':9} {item['name']:28} -> {new_name:26} {code}")
        if not spec.get("plug_a"):
            print("          ! Stecker nicht erkannt – bitte im Datenblatt eintragen")
        if args.apply:
            if code != item["code"]:
                repo.set_item_code(conn, item["id"], code)
            materials.save_specs(conn, item["id"], "cbl", {f"spec_{k}": v for k, v in spec.items()})
    print(f"{len(rows)} Kabel {'umgestellt' if args.apply else '(Vorschau, --apply zum Ändern)'}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
