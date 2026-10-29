"""Tägliches Backup im Hintergrund: beim Start und danach stündlich prüfen, ob heute eins fehlt.

Beide Server-Prozesse (80/443) laufen dasselbe; eine Sperrdatei sorgt dafür, dass nur einer sichert.
"""

import os
import threading
import time
from datetime import date, datetime
from pathlib import Path

from app import backup, codes
from app.db import connect

CHECK_SECONDS = 3600
LOCK_STALE = 1800  # Sperrdatei älter als 30 min gilt als Überbleibsel eines Absturzes
KEEP_DAYS = 30


def tick(data_dir: Path, today: date | None = None) -> list[Path] | None:
    """Sichert, falls für heute noch kein Backup existiert. None = nichts zu tun."""
    today = today or date.today()
    stamp = today.isoformat()
    target = data_dir / "backups"
    target.mkdir(parents=True, exist_ok=True)
    if (target / f"lager-{stamp}.db").exists():
        return None
    lock = target / f".lock-{stamp}"
    if lock.exists() and time.time() - lock.stat().st_mtime > LOCK_STALE:
        lock.unlink(missing_ok=True)
    try:
        os.close(os.open(lock, os.O_CREAT | os.O_EXCL | os.O_WRONLY))
    except FileExistsError:
        return None
    conn = connect(data_dir / "lager.db")
    try:
        try:
            days = int(codes.get_setting(conn, "backup_days", str(KEEP_DAYS)))
            files = backup.run(data_dir, target, days, today)
        except Exception as exc:  # Fehler nur melden, nie den Server beenden
            codes.set_setting(conn, "backup_error", f"{datetime.now():%Y-%m-%d %H:%M} {exc}")
            return None
        codes.set_setting(conn, "backup_last", f"{datetime.now():%Y-%m-%d %H:%M}")
        codes.set_setting(conn, "backup_error", "")
        return files
    finally:
        conn.close()
        lock.unlink(missing_ok=True)


def start(data_dir: Path) -> threading.Thread:
    def loop() -> None:
        while True:
            tick(data_dir)
            time.sleep(CHECK_SECONDS)

    thread = threading.Thread(target=loop, name="lager-backup", daemon=True)
    thread.start()
    return thread
