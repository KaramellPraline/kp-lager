"""REST-API › System: Import, Schema (für CLI/MCP) und Home-Assistant-Sensoren."""

from typing import Any

from fastapi import APIRouter
from pydantic import BaseModel

from app import (
    __version__,
    bulk,
    codes,
    dryer,
    expiry,
    importer,
    inventory,
    itemtypes,
    kinds,
    labels,
    materials,
    prefs,
    repo,
    typesettings,
    value,
    withdrawals,
)
from app.api.common import Conn, Write, find_item


class ImportText(BaseModel):
    text: str  # JSON im Import-Format (Haiku/lokale KI)
    review: bool = False


def register(router: APIRouter) -> None:
    @router.post("/import", dependencies=[Write])
    def import_json(conn: Conn, body: ImportText) -> dict[str, Any]:
        report = importer.run(
            conn,
            body.text,
            commit=True,
            review=body.review,
        )
        return {
            "errors": report.errors,
            "warnings": report.warnings,
            "items_added": report.items_added,
            "containers_created": report.containers_created,
        }

    @router.get("/schema")
    def schema(conn: Conn) -> dict[str, Any]:
        """Kategorien (Präfix, Name, Felder), Behälterarten, Tags, Aktionen – immer aktuell."""
        kinds.sync(conn)
        cats = []
        for prefix, label in kinds.ITEM_CATS:
            profile = materials.PREFIX_MATERIAL.get(prefix)
            fields = [
                {"key": f.key, "label": f.de, "unit": f.unit, "hint": f.hint}
                for f in materials.FIELDS.get(profile or "", ())
            ]
            cats.append({"prefix": prefix, "name": label, "profile": profile, "fields": fields,
                         "single_piece": prefix in repo.INDIVIDUAL})  # fmt: skip
        return {
            "categories": cats,
            "container_kinds": [
                {"key": k, "name": kinds.KIND_LABELS[k], "prefix": p}
                for k, p in codes.KIND_PREFIX.items()
            ],
            "tags": itemtypes.names(conn),
            "eurobox_dims_mm": kinds.EURO_DIMS,
            "bulk_actions": {k: v[0] for k, v in bulk.ACTIONS.items()},
            "dryer_programs": [
                {"id": p["id"], "name": p["name"], "temp_c": p["temp_c"], "hours": p["hours"]}
                for p in dryer.programs(conn)
            ],
        }

    @router.get("/ha")
    def home_assistant(conn: Conn) -> dict[str, Any]:
        """Home-Assistant-REST-Sensor: state = Teile unter Mindestbestand, Rest als Attribute."""
        low = repo.shopping_list(conn)
        due = expiry.due(conn)
        amount, _ = value.total(conn)
        err = codes.get_setting(conn, "backup_error", "")
        return {
            "state": len(low),
            "attributes": {
                "to_buy": len(low),
                "to_buy_items": [f"{r['name']} ({r['need']}×)" for r in low[:20]],
                "to_buy_eur": round(sum(r["cost"] for r in low if r["cost"] is not None), 2),
                "expired": len(due["expired"]),
                "expiring": len(due["soon"]),
                "expiring_items": [
                    f"{r['name']} ({r['expires']})" for r in (due["expired"] + due["soon"])[:20]
                ],
                "unsorted": len(repo.items_in(conn, repo.inbox(conn))),
                "inventory_due": len(inventory.due(conn, prefs.number(conn, "inventory_days"))),
                "labels_waiting": labels.queue_count(conn),
                "open_withdrawals": withdrawals.open_count(conn),
                "open_projects": conn.execute(
                    "SELECT COUNT(*) FROM project WHERE done = 0"
                ).fetchone()[0],
                "items": conn.execute("SELECT COUNT(*) FROM item WHERE archived = 0").fetchone()[0],
                "value_eur": round(amount, 2),
                "last_backup": codes.get_setting(conn, "backup_last", ""),
                "backup_ok": not err,
                "version": __version__,
                "unit_of_measurement": "Teile",
                "friendly_name": "Lager: nachkaufen",
            },
        }

    @router.get("/ha/item/{ref}")
    def home_assistant_item(conn: Conn, ref: str) -> dict[str, Any]:
        """Bestand eines einzelnen Teils (z. B. Filament-Spulen) als eigener Sensor."""
        i = find_item(conn, ref)
        min_eff, _ = typesettings.effective_min(conn, i)
        return {
            "state": i["qty"] if i["qty"] is not None else "ungezählt",
            "attributes": {
                "name": i["name"], "code": i["code"], "unit": i["unit"], "min": min_eff,
                "low": i["qty"] is not None and min_eff is not None and i["qty"] < min_eff,
                "path": repo.path_label(conn, i["container_id"]), "expires": i["expires"],
            },
        }  # fmt: skip
