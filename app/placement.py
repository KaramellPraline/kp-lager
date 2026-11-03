"""Platz-Vorschlag beim Einlagern: wo liegt schon Ähnliches, sonst wo ist frei."""

import sqlite3
from typing import Any

from app import catalog, repo


def suggest(
    conn: sqlite3.Connection,
    key: str = "",
    values: dict[str, str] | None = None,
    material: str = "",
    limit: int = 4,
) -> list[dict[str, Any]]:
    """Behälter mit Teilen desselben Typs (mehr gleiche Felder = besser), danach freie Plätze.

    Gibt [{id, label, reason}] zurück, beste zuerst.
    """
    want = {k: v.strip().casefold() for k, v in (values or {}).items() if v and v.strip()}
    if key:
        rows = conn.execute(
            "SELECT * FROM item WHERE ctype = ? AND archived = 0", (key,)
        ).fetchall()
    elif material:
        rows = conn.execute(
            "SELECT * FROM item WHERE material = ? AND archived = 0", (material,)
        ).fetchall()
    else:
        rows = []
    inbox = repo.inbox(conn)
    score: dict[int, tuple[int, int]] = {}  # Behälter -> (gleiche Felder max, Anzahl Teile)
    for r in rows:
        if r["container_id"] == inbox:
            continue
        have = {k: v.casefold() for k, v in catalog.values_of(r).items()}
        same = sum(1 for k, v in want.items() if have.get(k) == v)
        best, n = score.get(r["container_id"], (0, 0))
        score[r["container_id"]] = (max(best, same), n + 1)
    ranked = sorted(score.items(), key=lambda kv: (-kv[1][0], -kv[1][1]))
    out = []
    for cid, (same, n) in ranked[:limit]:
        reason = f"{n} ähnliche Teile" if not same else f"{n} ähnliche, {same} gleiche Angaben"
        out.append({"id": cid, "label": repo.path_label(conn, cid), "reason": reason})
    if len(out) < limit:  # freie Fächer/Boxen auffüllen
        for f in repo.free_places(conn)["empty"]:
            if f["id"] not in {o["id"] for o in out}:
                out.append({"id": f["id"], "label": f["path"], "reason": "leer"})
            if len(out) >= limit:
                break
    return out
