"""Client für die KP-Lager-REST-API (/api/v1) – genutzt von CLI und MCP-Server.

Umgebung: LAGER_URL (Standard https://lager.home.lan), LAGER_API_KEY (nur zum Schreiben),
LAGER_CA (Pfad zur eigenen CA, Standard data/certs/ca.crt im Repo, falls vorhanden).
"""

import os
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

    # Schreiben (mit Schlüssel)
    def add(self, container: str, text: str) -> list[dict[str, Any]]:
        return list(self._call("POST", "/items", json={"container": container, "text": text}))

    def take(self, ref: str, qty: int = 1) -> dict[str, Any]:
        return dict(self._call("POST", f"/items/{ref}/take", json={"qty": qty}))

    def move(self, ref: str, container: str) -> dict[str, Any]:
        return dict(self._call("POST", f"/items/{ref}/move", json={"container": container}))

    def import_json(self, text: str, review: bool = True) -> dict[str, Any]:
        return dict(self._call("POST", "/import", json={"text": text, "review": review}))


def fmt_item(i: dict[str, Any]) -> str:
    if i.get("qty") is not None:
        qty = f"{i['qty']} {i['unit'] or ''}".strip()
    else:
        qty = i.get("qty_hint") or ""
    parts = (i.get("code"), qty, i.get("model"), i.get("type"))
    extra = " · ".join(x for x in parts if x)
    return f"{i['name']}  [{extra}]  @ {i['path']}"
