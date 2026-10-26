"""Konfiguration aus Umgebungsvariablen (auf dem Server per systemd EnvironmentFile)."""

import os
from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True)
class Settings:
    data_dir: Path
    base_url: str
    whisper_url: str = ""  # OpenAI-kompatibler Whisper-Dienst, z. B. http://kp-proxmox:8001
    whisper_model: str = "Systran/faster-whisper-small"

    @property
    def db_path(self) -> Path:
        return self.data_dir / "lager.db"


def load_settings() -> Settings:
    return Settings(
        data_dir=Path(os.environ.get("LAGER_DATA_DIR", "data")),
        base_url=os.environ.get("LAGER_BASE_URL", "https://lager.home.lan").rstrip("/"),
        whisper_url=os.environ.get("LAGER_WHISPER_URL", "").rstrip("/"),
        whisper_model=os.environ.get("LAGER_WHISPER_MODEL", "Systran/faster-whisper-small"),
    )
