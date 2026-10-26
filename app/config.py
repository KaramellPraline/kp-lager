"""Konfiguration aus Umgebungsvariablen (Docker: compose.yaml, lokal: tools/serve.ps1)."""

import os
from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True)
class Settings:
    data_dir: Path
    base_url: str
    whisper_url: str = ""  # OpenAI-kompatibler Whisper-Dienst, z. B. http://kp-proxmox:8001
    whisper_model: str = "Systran/faster-whisper-small"
    https_redirect: bool = False  # HTTP-Instanz: alles außer /ca.crt auf HTTPS umleiten

    @property
    def db_path(self) -> Path:
        return self.data_dir / "lager.db"

    @property
    def ca_cert(self) -> Path:
        return self.data_dir / "certs" / "ca.crt"


def load_settings() -> Settings:
    return Settings(
        data_dir=Path(os.environ.get("LAGER_DATA_DIR", "data")),
        base_url=os.environ.get("LAGER_BASE_URL", "https://lager.home.lan").rstrip("/"),
        whisper_url=os.environ.get("LAGER_WHISPER_URL", "").rstrip("/"),
        whisper_model=os.environ.get("LAGER_WHISPER_MODEL", "Systran/faster-whisper-small"),
        https_redirect=os.environ.get("LAGER_HTTPS_REDIRECT", "") == "1",
    )
