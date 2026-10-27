"""Konfiguration aus Umgebungsvariablen (Docker: compose.yaml, lokal: tools/serve.ps1)."""

import os
from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True)
class Settings:
    data_dir: Path
    base_url: str
    whisper_url: str = ""  # OpenAI-kompatibler Dienst, z. B. KI-Gateway http://localhost:8765
    whisper_token: str = "local"  # Bearer-Token; auf dem Gateway-PC über localhost beliebig
    ai_url: str = ""  # Chat-Gateway (OpenAI-kompatibel); leer = wie whisper_url
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
        whisper_token=os.environ.get("LAGER_WHISPER_TOKEN", "local"),
        https_redirect=os.environ.get("LAGER_HTTPS_REDIRECT", "") == "1",
        ai_url=os.environ.get("LAGER_AI_URL", os.environ.get("LAGER_WHISPER_URL", "")).rstrip("/"),
    )
