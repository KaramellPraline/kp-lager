"""Client für die KP-Lager-REST-API (/api/v1) – genutzt von CLI und MCP-Server.

Umgebung: LAGER_URL (Standard https://lager.home.lan), LAGER_API_KEY (nur zum Schreiben),
LAGER_CA (Pfad zur eigenen CA, Standard data/certs/ca.crt im Repo, falls vorhanden).
"""

import os
import time
from pathlib import Path
from typing import Any

import httpx

REPO_CA = Path(__file__).parents[1] / "data" / "certs" / "ca.crt"


class LagerError(RuntimeError):
    pass


class LagerClient:
    def __init__(
        self,
        url: str | None = None,
        api_key: str | None = None,
        http: httpx.Client | None = None,
    ) -> None:
        self.url = (url or os.environ.get("LAGER_URL", "https://lager.home.lan")).rstrip("/")
        self.api_key = api_key if api_key is not None else os.environ.get("LAGER_API_KEY", "")
        if http is None:
            ca = os.environ.get("LAGER_CA") or (str(REPO_CA) if REPO_CA.exists() else None)
            http = httpx.Client(timeout=60, verify=ca if ca else True)
        self.http = http
        self._schema: tuple[float, dict[str, Any]] | None = None

    def _call(self, method: str, path: str, **kw: Any) -> Any:
        headers = {"X-API-Key": self.api_key} if self.api_key else {}
        try:
            resp = self.http.request(method, f"{self.url}/api/v1{path}", headers=headers, **kw)
        except httpx.HTTPError as exc:
            raise LagerError(f"Lager nicht erreichbar ({self.url}): {exc}") from None
        if resp.status_code >= 400:
            try:
                detail = resp.json().get("detail", resp.text)
            except ValueError:
                detail = resp.text
            raise LagerError(f"{resp.status_code}: {detail}")
        return resp.json()

    # Lesen (ohne Schlüssel)
    def search(self, q: str, limit: int = 30) -> dict[str, Any]:
        return dict(self._call("GET", "/search", params={"q": q, "limit": limit}))

    def item(self, ref: str) -> dict[str, Any]:
        return dict(self._call("GET", f"/items/{ref}"))

    def container(self, ref: str) -> dict[str, Any]:
        return dict(self._call("GET", f"/containers/{ref}"))

    def roots(self) -> list[dict[str, Any]]:
        return list(self._call("GET", "/containers"))

    def types(self) -> list[dict[str, Any]]:
        return list(self._call("GET", "/types"))

    def schema(self, fresh: bool = False) -> dict[str, Any]:
        """Kategorien, Behälterarten, Felder, Aktionen – 60 s zwischengespeichert, vom Server."""
        if fresh or self._schema is None or time.monotonic() - self._schema[0] > 60:
            self._schema = (time.monotonic(), dict(self._call("GET", "/schema")))
        return self._schema[1]

    def shopping(self) -> dict[str, Any]:
        return dict(self._call("GET", "/shopping"))

    def value(self, container: str = "") -> dict[str, Any]:
        return dict(self._call("GET", "/value", params={"container": container}))

    def dryer(self) -> dict[str, Any]:
        return dict(self._call("GET", "/dryer"))

    def print_jobs(self) -> list[dict[str, Any]]:
        return list(self._call("GET", "/print-jobs"))

    # Schreiben (mit Schlüssel)
    def add_typed(
        self, container: str, name: str, cat: str = "ART", qty: int | None = None,
        unit: str = "", count: int = 1, specs: dict[str, str] | None = None,
    ) -> list[dict[str, Any]]:  # fmt: skip
        body = {"container": container, "name": name, "cat": cat.upper(), "qty": qty, "unit": unit,
                "count": count, "specs": specs or {}}  # fmt: skip
        return list(self._call("POST", "/items/new", json=body))

    def bulk(self, refs: list[str], action: str, value: str = "", container: str = "") -> str:
        body = {"refs": refs, "action": action, "value": value, "container": container}
        return str(self._call("POST", "/bulk", json=body)["result"])

    def start_drying(self, item: str, program: str) -> dict[str, Any]:
        return dict(self._call("POST", "/dryer/start", json={"item": item, "program": program}))

    def add(self, container: str, text: str) -> list[dict[str, Any]]:
        return list(self._call("POST", "/items", json={"container": container, "text": text}))

    def take(self, ref: str, qty: int = 1) -> dict[str, Any]:
        return dict(self._call("POST", f"/items/{ref}/take", json={"qty": qty}))

    def move(self, ref: str, container: str) -> dict[str, Any]:
        return dict(self._call("POST", f"/items/{ref}/move", json={"container": container}))

    def import_json(self, text: str, review: bool = False) -> dict[str, Any]:
        return dict(self._call("POST", "/import", json={"text": text, "review": review}))

    # Erweiterung (M36): Überblick, Bearbeiten, Projekte, Einkäufe, Karten, Inventur
    def overview(self) -> dict[str, Any]:
        return dict(self._call("GET", "/overview"))

    def tree(self, depth: int = 4) -> list[dict[str, Any]]:
        return list(self._call("GET", "/tree", params={"depth": depth}))

    def items(self, container: str = "", limit: int = 200, offset: int = 0,
              low: bool = False) -> dict[str, Any]:  # fmt: skip
        params: dict[str, Any] = {"limit": limit, "offset": offset, "low": low}
        if container:
            params["container"] = container
        return dict(self._call("GET", "/items", params=params))

    def patch_item(self, ref: str, **fields: Any) -> dict[str, Any]:
        return dict(self._call("PATCH", f"/items/{ref}", json=fields))

    def delete_item(self, ref: str, hard: bool = False) -> dict[str, Any]:
        return dict(self._call("DELETE", f"/items/{ref}", params={"hard": hard}))

    def create_container(self, name: str, kind: str = "box", parent: str = "", notes: str = "",
                         dims: str = "") -> dict[str, Any]:  # fmt: skip
        body = {"name": name, "kind": kind, "parent": parent, "notes": notes, "dims": dims}
        return dict(self._call("POST", "/containers", json=body))

    def patch_container(self, ref: str, **fields: Any) -> dict[str, Any]:
        return dict(self._call("PATCH", f"/containers/{ref}", json=fields))

    def projects(self) -> list[dict[str, Any]]:
        return list(self._call("GET", "/projects"))

    def project(self, pid: int) -> dict[str, Any]:
        return dict(self._call("GET", f"/projects/{pid}"))

    def create_project(
        self, name: str, lines: list[dict[str, Any]], notes: str = ""
    ) -> dict[str, Any]:
        body = {"name": name, "notes": notes, "lines": lines}
        return dict(self._call("POST", "/projects", json=body))

    def project_add_lines(self, pid: int, lines: list[dict[str, Any]]) -> dict[str, Any]:
        return dict(self._call("POST", f"/projects/{pid}/lines", json=lines))

    def project_to_shopping(self, pid: int) -> dict[str, Any]:
        return dict(self._call("POST", f"/projects/{pid}/shopping"))

    def suppliers(self) -> list[dict[str, Any]]:
        return list(self._call("GET", "/suppliers"))

    def add_purchase(self, ref: str, **fields: Any) -> dict[str, Any]:
        return dict(self._call("POST", f"/items/{ref}/purchases", json=fields))

    def add_card(self, ref: str, title: str, body: str = "", kind: str = "note",
                 container: bool = False) -> dict[str, Any]:  # fmt: skip
        path = f"/containers/{ref}/cards" if container else f"/items/{ref}/cards"
        return dict(self._call("POST", path, json={"title": title, "body": body, "kind": kind}))

    def inventory_due(self) -> list[dict[str, Any]]:
        return list(self._call("GET", "/inventory/due"))

    def inventory_confirm(self, ref: str, qty: int | None = None) -> dict[str, Any]:
        return dict(self._call("POST", f"/inventory/items/{ref}", json={"qty": qty}))

    def inventory_done(self, container: str) -> dict[str, Any]:
        return dict(self._call("POST", f"/inventory/containers/{container}/done"))


def fmt_item(i: dict[str, Any]) -> str:
    if i.get("qty") is not None:
        qty = f"{i['qty']} {i['unit'] or ''}".strip()
    else:
        qty = i.get("qty_hint") or ""
    parts = (i.get("code"), qty, i.get("model"), i.get("type"))
    extra = " · ".join(x for x in parts if x)
    return f"{i['name']}  [{extra}]  @ {i['path']}"
