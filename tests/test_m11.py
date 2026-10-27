import re
import sqlite3
from collections.abc import Iterator
from typing import Any

import httpx
import pytest
from fastapi.testclient import TestClient

from app import datasheets, importer, itemtypes, repo
from app.db import connect
from app.repo import LagerError


@pytest.fixture
def conn() -> Iterator[sqlite3.Connection]:
    c = connect(":memory:")
    yield c
    c.close()


def item_of(client: TestClient, name: str = "ESP32 Board") -> tuple[str, str]:
    r = client.post("/containers", data={"name": "Box", "kind": "kiste"})
    box = str(r.url.path).rsplit("/", 1)[1]
    r = client.post(f"/n/{box}/items", data={"name": name})
    return box, re.findall(r'id="item-(\d+)"', r.text)[0]


def test_default_types_and_codes(conn: sqlite3.Connection) -> None:
    rows = itemtypes.all_types(conn)
    assert [(t["code"], t["name"]) for t in rows] == [
        ("TYP-002", "electronic"), ("TYP-001", "mechanical"), ("TYP-003", "smart-home"), ("TYP-004", "TBD")
    ]  # fmt: skip
    new = itemtypes.create(conn, "  pneumatic  ")
    assert itemtypes.get(conn, new)["code"] == "TYP-005"
    assert itemtypes.create(conn, "Pneumatic") == new  # kein Duplikat
    assert itemtypes.resolve(conn, "neu", "hydraulic") != new
    assert itemtypes.resolve(conn, "", "") is None
    with pytest.raises(LagerError, match="gibt es schon"):
        itemtypes.rename(conn, new, "electronic")


def test_type_in_use_cannot_be_deleted(conn: sqlite3.Connection) -> None:
    box = repo.create_container(conn, "Box", "kiste")
    t = itemtypes.create(conn, "pneumatic")
    item = repo.add_item(conn, box, "Ventil")
    repo.update_item(conn, item, type_id=t)
    with pytest.raises(LagerError, match="verwendet"):
        itemtypes.delete(conn, t)


def test_search_full_name_model_and_archive(conn: sqlite3.Connection) -> None:
    box = repo.create_container(conn, "Box", "kiste")
    item = repo.add_item(conn, box, "Board")
    repo.update_item(conn, item, full_name="Espressif Entwicklungsboard", model="ESP32-WROOM-32E")
    assert [r["name"] for r in repo.search(conn, "wroom")] == ["Board"]
    assert [r["name"] for r in repo.search(conn, "espressif")] == ["Board"]
    repo.update_item(conn, item, archived=1)
    assert repo.search(conn, "wroom") == [] and repo.items_in(conn, box) == []


def test_edit_item_with_new_type_names_and_model(client: TestClient) -> None:
    _, item = item_of(client)
    r = client.post(f"/items/{item}/edit", data={
        "name": "ESP32", "full_name": "Espressif ESP32 DevKit", "type_id": "neu",
        "new_type": "Mikrocontroller", "model": "ESP32-WROOM-32E"})  # fmt: skip
    assert "Gespeichert" in r.text and "Espressif ESP32 DevKit" in r.text
    assert "Mikrocontroller" in r.text and "ESP32-WROOM-32E" in r.text
    assert "duckduckgo.com" in r.text  # Datenblatt-Suche über Modellnummer
    types_page = client.get("/typen").text
    assert "Mikrocontroller" in types_page and "TYP-005" in types_page
    t_id = re.search(r'href="/typen/(\d+)"><span>Mikrocontroller', types_page).group(1)  # type: ignore[union-attr]
    assert "ESP32" in client.get(f"/typen/{t_id}").text
    assert str(client.get("/C/TYP-005").url.path) == f"/typen/{t_id}"


def test_datasheet_download(client: TestClient, monkeypatch: pytest.MonkeyPatch) -> None:
    responses: dict[str, Any] = {"body": b"%PDF-1.7 Datenblatt"}

    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, content=responses["body"])

    real = httpx.Client
    monkeypatch.setattr(
        datasheets.httpx, "Client", lambda **kw: real(transport=httpx.MockTransport(handler), **kw)
    )
    _, item = item_of(client)
    r = client.post(f"/items/{item}/edit", data={"name": "ESP32", "model": "ESP32-WROOM",
                                                 "datasheet_url": "https://example.com/esp32.pdf"})  # fmt: skip
    assert "Datenblatt heruntergeladen" in r.text
    link = re.search(r'href="(/datasheets/[^"]+\.pdf)"', r.text).group(1)  # type: ignore[union-attr]
    assert client.get(link).content.startswith(b"%PDF")
    responses["body"] = b"<html>keine pdf</html>"
    r = client.post(
        f"/items/{item}/edit", data={"name": "ESP32", "datasheet_url": "https://example.com/x"}
    )
    assert "keine PDF-Datei" in r.text
    r = client.post(f"/items/{item}/edit", data={"name": "ESP32", "datasheet_url": "ftp://x"})
    assert "http(s)" in r.text


def test_import_type_model_and_review_flag(conn: sqlite3.Connection) -> None:
    text = ('{"code":"KIS-001","name":"Elektronik","kind":"kiste","items":[{"name":"ESP32",'
            '"full_name":"Espressif ESP32","model":"ESP32-S3","type":"Mikrocontroller"}]}')  # fmt: skip
    report = importer.run(conn, text, commit=True, review=True)
    assert not report.errors
    item = repo.search(conn, "esp32-s3")[0]
    assert item["full_name"] == "Espressif ESP32" and item["review"] == 1
    assert itemtypes.get(conn, int(item["type_id"]))["name"] == "Mikrocontroller"  # type: ignore[arg-type]
    node = repo.get_container_by_code(conn, "KIS-001")
    assert node is not None and node["review"] == 1
