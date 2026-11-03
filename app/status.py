"""Statusseite (Mehr › Status): Betrieb, Backups, Speicher, Haltbarkeit."""

import shutil
import sqlite3
import sys
import time
from datetime import date, datetime, timedelta
from pathlib import Path
from typing import Any

from app import codes, labels, repo, scheduler, value

STARTED = time.time()
EXPIRY_WARN_DAYS = 30


def _size(n: float) -> str:
    for unit in ("B", "KB", "MB", "GB"):
        if n < 1024 or unit == "GB":
            return f"{n:.0f} {unit}" if unit == "B" else f"{n:.1f} {unit}".replace(".", ",")
        n /= 1024
    return ""


def backups(data_dir: Path, limit: int = 10) -> list[dict[str, str]]:
    folder = data_dir / "backups"
    files = sorted(folder.glob("lager-*.db"), reverse=True) if folder.is_dir() else []
    return [
        {
            "name": f.name,
            "size": _size(f.stat().st_size),
            "when": datetime.fromtimestamp(f.stat().st_mtime).strftime("%d.%m.%Y %H:%M"),
        }
        for f in files[:limit]
    ]


def expiring(conn: sqlite3.Connection, today: date | None = None) -> list[dict[str, Any]]:
    """Teile mit Haltbarkeitsdatum, abgelaufen oder in 30 Tagen: (zuerst die dringendsten)."""
    today = today or date.today()
    limit = (today + timedelta(days=EXPIRY_WARN_DAYS)).isoformat()
    rows = conn.execute(
        "SELECT * FROM item WHERE expires IS NOT NULL AND expires != '' AND expires <= ?"
        " AND archived = 0 ORDER BY expires",
        (limit,),
    ).fetchall()
    out = []
    for r in rows:
        try:
            days = (date.fromisoformat(r["expires"]) - today).days
        except ValueError:
            continue
        out.append({"id": r["id"], "name": r["name"], "expires": r["expires"], "days": days,
                    "path": repo.path_label(conn, r["container_id"])})  # fmt: skip
    return out


def collect(conn: sqlite3.Connection, data_dir: Path) -> dict[str, Any]:
    photos = data_dir / "photos"
    photo_files = [p for p in photos.iterdir() if p.is_file()] if photos.is_dir() else []
    photo_size = _size(sum(p.stat().st_size for p in photo_files))
    db_file = data_dir / "lager.db"
    usage = shutil.disk_usage(data_dir)
    worth, unpriced = value.total(conn)
    up = int(time.time() - STARTED)
    one = conn.execute
    return {
        "db_version": one("PRAGMA user_version").fetchone()[0],
        "db_size": _size(db_file.stat().st_size) if db_file.exists() else "–",
        "photos": f"{len(photo_files)} Dateien · {photo_size}",
        "disk_free": _size(usage.free),
        "disk_total": _size(usage.total),
        "disk_low": usage.free < 2 * 1024**3,
        "backups": backups(data_dir),
        "backup_last": codes.get_setting(conn, "backup_last", ""),
        "backup_error": codes.get_setting(conn, "backup_error", ""),
        "extern_target": scheduler.extern_target(conn),
        "extern_last": codes.get_setting(conn, "backup_extern_last", ""),
        "extern_error": codes.get_setting(conn, "backup_extern_error", ""),
        "backup_days": codes.get_setting(conn, "backup_days", "30"),
        "n_items": one("SELECT COUNT(*) FROM item WHERE archived = 0").fetchone()[0],
        "n_containers": one("SELECT COUNT(*) FROM container").fetchone()[0],
        "n_cables": one("SELECT COUNT(*) FROM item WHERE code LIKE 'CBL-%'").fetchone()[0],
        "n_psus": one("SELECT COUNT(*) FROM item WHERE code LIKE 'PSU-%'").fetchone()[0],
        "n_low": len(repo.shopping_list(conn)),
        "n_queue": labels.queue_count(conn),
        "worth": value.euro(worth),
        "unpriced": unpriced,
        "expiring": expiring(conn),
        "uptime": f"{up // 86400} d {up % 86400 // 3600} h {up % 3600 // 60} min",
        "python": sys.version.split()[0],
        "now": datetime.now().strftime("%d.%m.%Y %H:%M"),
    }
