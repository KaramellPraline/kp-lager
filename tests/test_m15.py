import json
import re
from collections.abc import Iterator
from pathlib import Path
from typing import Any

import httpx
import pytest
from fastapi.testclient import TestClient

from app import ai
from app.config import Settings
from app.web import create_app

ANSWERS: dict[str, Any] = {}


def fake_chat(request: httpx.Request) -> httpx.Response:
    body = json.loads(request.content)
    ANSWERS["last_model"] = body["model"]
    ANSWERS["last_system"] = body["messages"][0]["content"]
    content = (
        ANSWERS["enrich"] if "ergänzt Lagerdaten" in ANSWERS["last_system"] else ANSWERS["import"]
    )
    return httpx.Response(200, json={"choices": [{"message": {"content": content}}]})


@pytest.fixture
def aiclient(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Iterator[TestClient]:
    real = httpx.Client
    monkeypatch.setattr(
        ai.httpx, "Client", lambda **kw: real(transport=httpx.MockTransport(fake_chat), **kw)
    )
    s = Settings(data_dir=tmp_path, base_url="https://lager.test", ai_url="http://gw")
    with TestClient(create_app(s)) as c:
        yield c


def node_of(r: httpx.Response) -> str:
    return str(r.url.path).rsplit("/", 1)[1]


def test_send_description_to_local_ai_creates_review_items(aiclient: TestClient) -> None:
    box = node_of(
        aiclient.post(
            "/containers", data={"name": "Elektronik", "kind": "kiste", "code": "KIS-001"}
        )
    )
    aiclient.post("/typen", data={"name": "pneumatic"})
    ANSWERS["import"] = (
        '<think>…</think>```json\n[{"code":"KIS-001","name":"Elektronik","kind":"kiste","items":[{"name":"ESP32","model":"ESP32","type":"electronic","qty":3}]}]\n```'
    )
    r = aiclient.post(f"/ai/node/{box}", data={"text": "drei ESP32"})
    assert "KI: 1 Teile, 0 Behälter angelegt" in r.text
    assert "pneumatic" in ANSWERS["last_system"]  # neu angelegte Typen im Prompt
    assert ANSWERS["last_model"] == "mid"
    page = aiclient.get("/freigaben").text
    assert "ESP32" in page and ">neu<" in page
    assert '<b class="count">1</b>' in aiclient.get("/").text  # Freigaben-Zähler in der Navigation
    item = re.search(r"/freigaben/item/(\d+)/approve", page).group(1)  # type: ignore[union-attr]
    aiclient.post(f"/freigaben/item/{item}/approve")
    assert "Nichts zu prüfen" in aiclient.get("/freigaben").text


def test_enrich_item_backup_and_reject(aiclient: TestClient) -> None:
    box = node_of(aiclient.post("/containers", data={"name": "Box", "kind": "kiste"}))
    r = aiclient.post(f"/n/{box}/items", data={"name": "Board"})
    item = re.findall(r'id="item-(\d+)"', r.text)[0]
    ANSWERS["enrich"] = (
        '{"name":"ESP32 DevKit","full_name":"Espressif ESP32-DevKitC","type":"microcontroller","model":"ESP32-WROOM-32E","tags":["esp32","wlan"],"datasheet_url":""}'
    )
    r = aiclient.post(f"/items/{item}/ai")
    assert (
        "KI-Vorschlag übernommen" in r.text
        and "Zu prüfen" in r.text
        and "ESP32-WROOM-32E" in r.text
    )
    page = aiclient.get("/freigaben").text
    assert ">ergänzt<" in page and "Vorher: Board" in page and "Suchbegriffe: esp32 wlan" in page
    r = aiclient.post(f"/freigaben/item/{item}/reject")
    assert "Alter Stand von „Board“ wiederhergestellt" in r.text
    item_page = aiclient.get(f"/items/{item}").text
    assert (
        "<h1>Board</h1>" in item_page
        and 'name="model" value=""' in item_page
        and "Zu prüfen" not in item_page
    )
    assert "microcontroller" in aiclient.get("/typen").text  # neuer Typ bleibt


def test_reject_new_item_deletes_and_approve_all(aiclient: TestClient) -> None:
    aiclient.post("/containers", data={"name": "Box", "kind": "kiste", "code": "KIS-002"})
    ANSWERS["import"] = (
        '[{"code":"KIS-002","name":"Box","kind":"kiste","items":[{"name":"Zange"},{"name":"Feile"}]}]'
    )
    box = node_of(aiclient.get("/C/KIS-002"))
    aiclient.post(f"/ai/node/{box}", data={"text": "Zange und Feile"})
    page = aiclient.get("/freigaben").text
    zange = re.search(r'/items/(\d+)"><b>Zange', page).group(1)  # type: ignore[union-attr]
    assert "„Zange“ verworfen" in aiclient.post(f"/freigaben/item/{zange}/reject").text
    assert "1 Einträge freigegeben" in aiclient.post("/freigaben/all").text


def test_no_ai_buttons_without_gateway(client: TestClient) -> None:
    box = node_of(
        client.post("/containers", data={"name": "Box", "kind": "kiste", "code": "KIS-003"})
    )
    assert "An lokale KI senden" not in client.get(f"/n/{box}").text
