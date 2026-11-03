"""Konfiguration aus Umgebungsvariablen (Docker: deploy/compose.yaml)."""

import os
import re
from dataclasses import dataclass
from pathlib import Path
from urllib.parse import urlsplit

QR_HOST = "https://lager.home.lan"  # fest: so steht es auf jedem gedruckten Etikett
_LOCAL = re.compile(r"^(localhost|0\.0\.0\.0|\[?::1?\]?|127\..*|\d{1,3}(\.\d{1,3}){3})$", re.I)


def qr_base(url: str) -> str:
    """Adresse für QR-Codes: nie localhost oder eine IP – dann gilt der feste Standard.

    Erlaubt bleiben echte Namen (z. B. lager.home.lan oder lager.example.org), damit Etiketten
    auf jedem Gerät funktionieren, egal wie die App gerade aufgerufen wird.
    """
    url = (url or "").strip().rstrip("/")
    host = urlsplit(url if "://" in url else "https://" + url).hostname or ""
    if not url or not host or _LOCAL.match(host):
        return QR_HOST
    return url if "://" in url else "https://" + url


@dataclass(frozen=True)
class Settings:
    data_dir: Path
    base_url: str
    auto_backup: bool = False  # tägliches Backup im Hintergrund (Server-Betrieb)
    d30: bool = False  # Direktdruck per Bluetooth (Server-PC mit Bluetooth + D30)
    d30_bridge: bool = (
        False  # Drucken über die PC-Bridge des Windows-Clients (Server ohne Bluetooth)
    )
    https_redirect: bool = False  # HTTP-Instanz: alles außer /ca.crt auf HTTPS umleiten

    def __post_init__(self) -> None:
        object.__setattr__(self, "base_url", qr_base(self.base_url))

    @property
    def db_path(self) -> Path:
        return self.data_dir / "lager.db"

    @property
    def ca_cert(self) -> Path:
        return self.data_dir / "certs" / "ca.crt"


def load_settings() -> Settings:
    return Settings(
        data_dir=Path(os.environ.get("LAGER_DATA_DIR", "data")),
        base_url=os.environ.get("LAGER_BASE_URL", QR_HOST),
        auto_backup=os.environ.get("LAGER_AUTO_BACKUP", "1") == "1",
        d30=os.environ.get("LAGER_D30", "1") == "1",
        d30_bridge=os.environ.get("LAGER_D30_BRIDGE", "") == "1",
        https_redirect=os.environ.get("LAGER_HTTPS_REDIRECT", "") == "1",
    )
