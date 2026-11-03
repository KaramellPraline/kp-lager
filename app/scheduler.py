"""Tägliches Backup im Hintergrund: beim Start und danach stündlich prüfen, ob heute eins fehlt.

Beide Server-Prozesse (80/443) laufen dasselbe; eine Sperrdatei sorgt dafür, dass nur einer sichert.
"""

import os
import sqlite3
import threading
import time
from datetime import date, datetime
from pathlib import Path

from app import backup, codes, prefs
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


def extern_target(conn: sqlite3.Connection) -> str:
    """Zielordner aus den Einstellungen, sonst aus $LAGER_BACKUP_EXTERN (Docker)."""
    return prefs.raw(conn, "backup_extern").strip() or os.environ.get("LAGER_BACKUP_EXTERN", "")


def extern_tick(data_dir: Path, today: date | None = None, force: bool = False) -> str:
    """Heutige Sicherung in den externen Ordner kopieren (Einstellung „Externes Backup“).

    Gibt eine Statusmeldung zurück; Fehler landen in `backup_extern_error`, nie im Serverabsturz.
    """
    today = today or date.today()
    conn = connect(data_dir / "lager.db")
    try:
        target = extern_target(conn)
        if not target:
            return "Kein externes Ziel eingestellt"
        stamp = today.isoformat()
        if not force and codes.get_setting(conn, "backup_extern_day", "") == stamp:
            return "Heute schon extern gesichert"
        files = backup.todays_files(data_dir / "backups", today)
        if not files:
            return "Noch kein lokales Backup für heute"
        try:
            days = int(codes.get_setting(conn, "backup_days", str(KEEP_DAYS)))
            backup.mirror(files, Path(target), days)
        except Exception as exc:  # NAS nicht erreichbar, Ordner schreibgeschützt …
            codes.set_setting(conn, "backup_extern_error", f"{datetime.now():%Y-%m-%d %H:%M} {exc}")
            return f"Externes Backup fehlgeschlagen: {exc}"
        codes.set_setting(conn, "backup_extern_day", stamp)
        codes.set_setting(conn, "backup_extern_last", f"{datetime.now():%Y-%m-%d %H:%M}")
        codes.set_setting(conn, "backup_extern_error", "")
        return f"Extern gesichert nach {target}"
    finally:
        conn.close()


def start(data_dir: Path) -> threading.Thread:
    def loop() -> None:
        while True:
            tick(data_dir)
            extern_tick(data_dir)
            time.sleep(CHECK_SECONDS)

    thread = threading.Thread(target=loop, name="lager-backup", daemon=True)
    thread.start()
    return thread
