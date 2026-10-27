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
        if number > version:
            apply(conn, file, number)
            version = number
    return version


def apply(conn: sqlite3.Connection, file: Path, number: int) -> bool:
    """Migration unter Schreibsperre einspielen; False, wenn ein anderer Prozess schneller war."""
    sql = file.read_text(encoding="utf-8")
    # Tabellen-Neuaufbau (z. B. CHECK ändern) geht nur ohne FK-Prüfung; danach prüfen.
    rebuild = "-- foreign_keys: off" in sql
    if rebuild:
        conn.execute("PRAGMA foreign_keys = OFF")
    conn.execute("BEGIN IMMEDIATE")  # Sperre vor dem erneuten Lesen der Version
    try:
        if conn.execute("PRAGMA user_version").fetchone()[0] >= number:
            conn.rollback()
            return False
        stmt = ""
        for line in sql.splitlines(keepends=True):
            stmt += line
            if sqlite3.complete_statement(stmt):
                conn.execute(stmt)
                stmt = ""
        conn.execute(f"PRAGMA user_version = {number}")
        conn.commit()
    except BaseException:
        conn.rollback()
        raise
    finally:
        if rebuild:
            conn.execute("PRAGMA foreign_keys = ON")
    if rebuild and conn.execute("PRAGMA foreign_key_check").fetchone():
        raise RuntimeError(f"Fremdschlüssel nach {file.name} verletzt")
    return True
