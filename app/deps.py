"""Gemeinsame FastAPI-Abhängigkeiten für Oberfläche (app/web) und REST-API (app/api).

Die Einstellungen liegen in `app.state.settings` (gesetzt von `create_app`).
"""

import sqlite3
from collections.abc import Iterator
from typing import Annotated

from fastapi import Depends, Request

from app import withdrawals
from app.config import Settings
from app.db import connect


def get_conn(request: Request) -> Iterator[sqlite3.Connection]:
    """Eine Verbindung pro Request; fällige Entnahmen (7 Tage) werden dabei bestätigt."""
    settings: Settings = request.app.state.settings
    conn = connect(settings.db_path)
    withdrawals.confirm_due(conn)  # fällige Entnahmen (7 Tage) bestätigen
    try:
        yield conn
    finally:
        conn.close()


Conn = Annotated[sqlite3.Connection, Depends(get_conn)]
