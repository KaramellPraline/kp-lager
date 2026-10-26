import json
import sqlite3
from collections.abc import Iterator

import pytest
from fastapi.testclient import TestClient

from app import importer, repo
from app.db import connect

CHAT = """Hier ist das JSON:
```json
{"code":"RAU-001","name":"Keller","kind":"raum","parent":null,"items":[]}
```
und die nächste Box:
[{"code":"EUR-001","name":"Elektronik","kind":"eurobox","parent":"RAU-001",
  "items":[{"name":"Lötzinn","qty":2,"unit":"Rolle","tags":["löten","elektronik"]},
           {"name":"Kabelbinder","qty":null,"qty_hint":"viele"}]},
 {"code":"SOR-001","name":"Schrauben","kind":"sortierkasten","parent":"RAU-001","grid":"4x2",
  "items":[{"name":"Holzschrauben 4x40","qty_hint":"viele","slot":"b3"},
           {"name":"Dübel 6mm","slot":"Z9"}]}]
"""


@pytest.fixture
def conn() -> Iterator[sqlite3.Connection]:
    c = connect(":memory:")
    yield c
    c.close()


def test_parse_multiple_answers_with_fences() -> None:
    assert [c["code"] for c in importer.parse(CHAT)] == ["RAU-001", "EUR-001", "SOR-001"]
    assert importer.parse("kein json") == []


def test_preview_does_not_write(conn: sqlite3.Connection) -> None:
    r = importer.run(conn, CHAT, commit=False)
    assert not r.errors
    assert len(r.containers_created) == 3 and r.items_added == 4
    assert conn.execute("SELECT COUNT(*) FROM container").fetchone()[0] == 0


def test_commit_builds_tree_slots_and_is_idempotent(conn: sqlite3.Connection) -> None:
    importer.run(conn, CHAT, commit=True)
    loet = repo.search(conn, "lötzinn")[0]
    assert loet["path"] == "Keller › Elektronik" and loet["tags"] == "löten elektronik"
    assert repo.search(conn, "holzschrauben")[0]["path"] == "Keller › Schrauben › Fach B3"
    assert repo.search(conn, "dübel")[0]["path"] == "Keller › Schrauben › Fach Z9"
    assert repo.history(conn, int(loet["id"]))[0]["action"] == "import"  # type: ignore[call-overload]
    again = importer.run(conn, CHAT, commit=True)
    assert again.containers_created == [] and again.items_added == 0 and again.items_skipped == 4


def test_existing_parent_and_move(conn: sqlite3.Connection) -> None:
    keller = repo.create_container(conn, "Keller", "raum", code="RAU-001")
    repo.create_container(conn, "Dachboden", "raum", code="RAU-002")
    repo.create_container(conn, "Box", "kiste", code="KIS-050", parent_id=keller)
    r = importer.run(
        conn, '{"code":"KIS-050","name":"Box","kind":"kiste","parent":"RAU-002"}', True
    )
    assert r.containers_moved == ["KIS-050 Box"]
    node = repo.get_container_by_code(conn, "KIS-050")
    assert node is not None and repo.path_label(conn, node["id"]) == "Dachboden › Box"


@pytest.mark.parametrize(
    ("payload", "error"),
    [
        ('{"name":"X"}', "'code' fehlt"),
        ('{"code":"KIS-1"}', "'name' fehlt"),
        ('{"code":"KIS-1","name":"X","parent":"KIS-9"}', "unbekannt"),
        ('{"code":"KIS-1","name":"X","items":[{"name":"Y","qty":-1}]}', "ungültig"),
        ('[{"code":"KIS-1","name":"X"},{"code":"KIS-1","name":"Y"}]', "mehrfach"),
        (
            '[{"code":"KIS-1","name":"X","parent":"KIS-2"},{"code":"KIS-2","name":"Y","parent":"KIS-1"}]',
            "Zirkul",
        ),
    ],
)
def test_errors_leave_db_untouched(conn: sqlite3.Connection, payload: str, error: str) -> None:
    r = importer.run(conn, payload, commit=True)
    assert any(error in e for e in r.errors), r.errors
    assert conn.execute("SELECT COUNT(*) FROM container").fetchone()[0] == 0


def test_unknown_kind_warns(conn: sqlite3.Connection) -> None:
    r = importer.run(conn, '{"code":"KIS-1","name":"Schrank","kind":"schrank"}', commit=True)
    assert r.warnings and repo.get_container_by_code(conn, "KIS-001")["kind"] == "sonstiges"  # type: ignore[index]


def test_import_page_and_export(client: TestClient) -> None:
    r = client.post("/import", data={"text": CHAT, "action": "preview"})
    assert "Vorschau" in r.text and 'value="commit"' in r.text
    r = client.post("/import", data={"text": CHAT, "action": "commit"})
    assert "Übernommen" in r.text
    data = json.loads(client.get("/export.json").text)
    assert {c["code"] for c in data["container"]} >= {"RAU-001", "EUR-001", "SOR-001"}
    assert len(data["item"]) == 4 and len(data["event"]) >= 4
