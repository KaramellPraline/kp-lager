"""SQLite-Verbindung und Migrations-Runner (Version in PRAGMA user_version)."""

import sqlite3
from pathlib import Path

MIGRATIONS_DIR = Path(__file__).parent / "migrations"


def connect(path: Path | str) -> sqlite3.Connection:
    if str(path) != ":memory:":
        Path(path).parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(path, check_same_thread=False)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    conn.execute("PRAGMA journal_mode = WAL")
    # SQLites lower()/LIKE falten nur ASCII; fold() kann auch Umlaute.
    conn.create_function("fold", 1, lambda s: s.casefold() if s else s, deterministic=True)
    migrate(conn)
    return conn


def migrate(conn: sqlite3.Connection) -> int:
    """Spielt alle Migrationen NNN_*.sql mit NNN > user_version ein; gibt neue Version zurück."""
    version: int = conn.execute("PRAGMA user_version").fetchone()[0]
    for file in sorted(MIGRATIONS_DIR.glob("[0-9][0-9][0-9]_*.sql")):
        number = int(file.name[:3])
        if number <= version:
            continue
        conn.executescript(
            f"BEGIN;\n{file.read_text(encoding='utf-8')}\nPRAGMA user_version = {number};\nCOMMIT;"
        )
        version = number
    return version
