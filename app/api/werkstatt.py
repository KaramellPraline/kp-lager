"""REST-API › Werkstatt: Projekte/Stückliste, Inventur, Trockner, Druckaufträge (Slicer)."""

import sqlite3
from typing import Any

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from app import dryer, inventory, prefs, projects, repo, slicer
from app.api.common import Conn, Write, bad, find_item, find_node, item_json
from app.repo import LagerError


class DryStart(BaseModel):
    item: str
    program: str  # Name oder ID des Programms


class ProjectLine(BaseModel):
    item: str = ""  # Teil (Code/ID) – oder freier Name
    name: str = ""
    qty: int | None = None


class ProjectNew(BaseModel):
    name: str
    notes: str = ""
    lines: list[ProjectLine] = []


class Count(BaseModel):
    qty: int | None = None  # gezählte Menge (leer = nur bestätigen)


def register(router: APIRouter) -> None:
    @router.get("/dryer")
    def dryer_state(conn: Conn) -> dict[str, Any]:
        return {"running": dryer.running(conn), "history": dryer.history(conn, limit=20),
                "programs": [dict(p) for p in dryer.programs(conn)]}  # fmt: skip

    @router.get("/print-jobs")
    def print_jobs(conn: Conn) -> list[dict[str, Any]]:
        return slicer.jobs(conn)

    @router.post("/dryer/start", dependencies=[Write])
    def dryer_start(conn: Conn, body: DryStart) -> dict[str, Any]:
        item = find_item(conn, body.item)
        wanted = body.program.casefold()
        prog = next(
            (p for p in dryer.programs(conn) if wanted in (str(p["id"]), p["name"].casefold())),
            None,
        )
        if prog is None:
            raise HTTPException(404, f"Programm {body.program} nicht gefunden")
        try:
            return {"log": dryer.start(conn, item["id"], prog["id"], "API")}
        except LagerError as exc:
            raise HTTPException(400, str(exc)) from None

    def project_json(conn: sqlite3.Connection, pid: int) -> dict[str, Any]:
        p = projects.get(conn, pid)
        bom = projects.compare(conn, pid)
        return {
            "id": p["id"], "name": p["name"], "notes": p["notes"], "done": bool(p["done"]),
            "complete": bom["complete"], "counts": bom["counts"],
            "missing_cost_eur": round(bom["cost"], 2),
            "lines": [
                {"id": r["id"], "item": r["code"], "name": r["name"], "qty": r["qty"],
                 "stock": r["stock"], "free": r["free"], "reserved": r["reserved"],
                 "status": r["status"], "short": r["short"],
                 "path": r["path"], "gathered": bool(r["gathered"])}
                for r in bom["lines"]
            ],
        }  # fmt: skip

    def add_lines(conn: sqlite3.Connection, pid: int, lines: list[ProjectLine]) -> None:
        for line in lines:
            item_id = find_item(conn, line.item)["id"] if line.item else None
            try:
                projects.add_line(conn, pid, item_id, line.name, line.qty)
            except LagerError as exc:
                raise bad(exc) from None

    @router.get("/projects")
    def list_projects(conn: Conn) -> list[dict[str, Any]]:
        return [
            {"id": p["id"], "name": p["name"], "done": bool(p["done"]), "lines": p["total"]}
            for p in projects.all_projects(conn)
        ]

    @router.get("/projects/{pid}")
    def get_project(conn: Conn, pid: int) -> dict[str, Any]:
        try:
            return project_json(conn, pid)
        except LagerError as exc:
            raise HTTPException(404, str(exc)) from None

    @router.post("/projects", dependencies=[Write])
    def create_project(conn: Conn, body: ProjectNew) -> dict[str, Any]:
        try:
            pid = projects.create(conn, body.name, body.notes)
        except LagerError as exc:
            raise bad(exc) from None
        add_lines(conn, pid, body.lines)
        return project_json(conn, pid)

    @router.post("/projects/{pid}/lines", dependencies=[Write])
    def project_lines(conn: Conn, pid: int, lines: list[ProjectLine]) -> dict[str, Any]:
        try:
            projects.get(conn, pid)
        except LagerError as exc:
            raise HTTPException(404, str(exc)) from None
        add_lines(conn, pid, lines)
        return project_json(conn, pid)

    @router.post("/projects/{pid}/reserve", dependencies=[Write])
    def project_reserve(conn: Conn, pid: int, release: bool = False) -> dict[str, Any]:
        """Verfügbares für das Projekt reservieren (`release=true` hebt die Reservierung auf)."""
        try:
            projects.get(conn, pid)
        except LagerError as exc:
            raise HTTPException(404, str(exc)) from None
        if release:
            projects.release(conn, pid)
        else:
            projects.reserve(conn, pid)
        return project_json(conn, pid)

    @router.post("/projects/{pid}/shopping", dependencies=[Write])
    def project_shopping(conn: Conn, pid: int) -> dict[str, Any]:
        """Fehlmengen bekannter Teile auf die Einkaufsliste setzen."""
        try:
            n = projects.to_shopping(conn, pid)
        except LagerError as exc:
            raise HTTPException(404, str(exc)) from None
        return {"on_shopping_list": n, "project": project_json(conn, pid)}

    @router.get("/inventory/due")
    def inventory_due(conn: Conn) -> list[dict[str, Any]]:
        days = prefs.number(conn, "inventory_days")
        return [
            {"id": r["id"], "code": r["code"], "name": r["name"], "path": r["path"],
             "items": r["n"], "last_checked": r["checked_at"]}
            for r in inventory.due(conn, days)
        ]  # fmt: skip

    @router.post("/inventory/items/{ref}", dependencies=[Write])
    def inventory_confirm(conn: Conn, ref: str, body: Count | None = None) -> dict[str, Any]:
        item = find_item(conn, ref)
        try:
            msg = inventory.confirm_item(conn, item["id"], body.qty if body else None)
        except LagerError as exc:
            raise bad(exc) from None
        return {"result": msg, "item": item_json(conn, repo.get_item(conn, item["id"]))}

    @router.post("/inventory/containers/{ref}/done", dependencies=[Write])
    def inventory_done(conn: Conn, ref: str) -> dict[str, int]:
        node = find_node(conn, ref)
        return {"unconfirmed": inventory.finish(conn, node["id"])}
