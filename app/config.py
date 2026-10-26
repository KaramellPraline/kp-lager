"""Konfiguration aus Umgebungsvariablen (auf dem Server per systemd EnvironmentFile)."""

import os
from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True)
class Settings:
    data_dir: Path
    base_url: str

    @property
    def db_path(self) -> Path:
        return self.data_dir / "lager.db"


def load_settings() -> Settings:
    return Settings(
        data_dir=Path(os.environ.get("LAGER_DATA_DIR", "data")),
        base_url=os.environ.get("LAGER_BASE_URL", "http://localhost:8000").rstrip("/"),
    )
