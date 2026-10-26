"""Backup: konsistente SQLite-Kopie + Foto-Archiv, alte Stände aufräumen.

Aufruf: python -m app.backup [ZIELORDNER] [TAGE]  (Standard: $LAGER_DATA_DIR/backups, 30)
"""

import sqlite3
import sys
import tarfile
import time
from datetime import date
from pathlib import Path

from app.config import load_settings


def run(data_dir: Path, target: Path, keep_days: int = 30) -> list[Path]:
    target.mkdir(parents=True, exist_ok=True)
    stamp = date.today().isoformat()
    db_copy = target / f"lager-{stamp}.db"
    src = sqlite3.connect(data_dir / "lager.db")
    dst = sqlite3.connect(db_copy)
    with dst:
        src.backup(dst)  # funktioniert auch bei laufendem Betrieb
    ok = dst.execute("PRAGMA integrity_check").fetchone()[0]
    src.close()
    dst.close()
    if ok != "ok":
        raise RuntimeError(f"Backup defekt: {ok}")
    written = [db_copy]
    photos = data_dir / "photos"
    if photos.is_dir():
        archive = target / f"photos-{stamp}.tar.gz"
        with tarfile.open(archive, "w:gz") as tar:
            tar.add(photos, arcname="photos")
        written.append(archive)
    cutoff = time.time() - keep_days * 86400
    for old in [*target.glob("lager-*.db"), *target.glob("photos-*.tar.gz")]:
        if old.stat().st_mtime < cutoff:
            old.unlink()
    return written


if __name__ == "__main__":
    settings = load_settings()
    dest = Path(sys.argv[1]) if len(sys.argv) > 1 else settings.data_dir / "backups"
    days = int(sys.argv[2]) if len(sys.argv) > 2 else 30
    for path in run(settings.data_dir, dest, days):
        print(f"Backup: {path}")
