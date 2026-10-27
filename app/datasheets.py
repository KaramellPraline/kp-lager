"""Datenblätter: PDF von einer URL herunterladen und lokal ablegen (data/datasheets/)."""

import re
from pathlib import Path
from urllib.parse import quote_plus

import httpx

from app.repo import LagerError

MAX_BYTES = 40 * 1024 * 1024


def search_url(model: str) -> str:
    """Such-Link, wenn noch keine Datenblatt-URL bekannt ist."""
    return f"https://duckduckgo.com/?q={quote_plus(model + ' datasheet pdf')}"


def _slug(text: str) -> str:
    return re.sub(r"[^A-Za-z0-9._-]+", "-", text).strip("-")[:60] or "datenblatt"


def download(url: str, folder: Path, stem: str) -> str:
    """Lädt die PDF und gibt den Dateinamen zurück; wirft LagerError bei Fehlern."""
    if not re.match(r"^https?://", url.strip(), re.IGNORECASE):
        raise LagerError("Datenblatt-URL muss mit http(s):// beginnen")
    try:
        with httpx.Client(timeout=60, follow_redirects=True) as client:
            resp = client.get(url.strip(), headers={"User-Agent": "Mozilla/5.0 KP-Lager"})
            resp.raise_for_status()
    except httpx.HTTPError as exc:
        raise LagerError(f"Datenblatt nicht ladbar: {exc}") from None
    data = resp.content
    if len(data) > MAX_BYTES:
        raise LagerError("Datenblatt zu groß (max. 40 MB)")
    if not data.startswith(b"%PDF"):
        raise LagerError("Unter der URL liegt keine PDF-Datei")
    folder.mkdir(parents=True, exist_ok=True)
    name = f"{_slug(stem)}.pdf"
    (folder / name).write_bytes(data)
    return name
