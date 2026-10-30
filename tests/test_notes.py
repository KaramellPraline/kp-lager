import re
from collections.abc import Iterator
from pathlib import Path
from typing import Any

import httpx
import pytest
from fastapi.testclient import TestClient

from app import web
from app.config import Settings
from app.web import create_app

STATE: dict[str, Any] = {"fail": False}


@pytest.fixture
def voice(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Iterator[TestClient]:
    def handler(request: httpx.Request) -> httpx.Response:
        if STATE["fail"]:
            return httpx.Response(500, text="Dienst startet")
        return httpx.Response(200, json={"text": "EUR-003: zwei Rollen Lötzinn und ein Multimeter"})

    real = httpx.AsyncClient
    monkeypatch.setattr(
        web.httpx, "AsyncClient", lambda **kw: real(transport=httpx.MockTransport(handler), **kw)
    )
    STATE["fail"] = False
    s = Settings(data_dir=tmp_path, base_url="https://lager.test", whisper_url="http://gw")
    with TestClient(create_app(s)) as c:
        yield c


def upload(c: TestClient) -> dict[str, Any]:
    r = c.post(
        "/api/notes",
        files={"audio": ("d.webm", b"OPUSDATA", "audio/webm")},
        data={"duration": "151"},
    )
    return dict(r.json())


def test_note_becomes_haiku_prompt_with_timestamp(voice: TestClient, tmp_path: Path) -> None:
    d = upload(voice)
    assert d["ok"] and d["msg"] == "Aufnahme gespeichert"
    page = voice.get("/sprache").text
    assert "Aufnahmen (1)" in page and "2:31 min" in page
    assert re.search(r"<b>\d{2}\.\d{2}\.\d{4} \d{2}:\d{2}</b>", page)
    assert (
        "Diktat vom" in page
        and "EUR-003: zwei Rollen Lötzinn" in page
        and "Prompt kopieren" in page
    )
    r = voice.get(f"/notes/{d['id']}.txt")
    assert r.headers["content-type"].startswith("text/plain")
    assert re.search(
        r'filename="haiku-diktat_\d{4}-\d{2}-\d{2}_\d{4}\.txt"', r.headers["content-disposition"]
    )
    assert r.text.startswith("Lagerinventur. Antworte NUR mit JSON") and "--- Diktat ---" in r.text
    assert len(list((tmp_path / "notes").iterdir())) == 1  # Audio gesichert


def test_failed_transcription_keeps_audio_and_retries(voice: TestClient, tmp_path: Path) -> None:
    STATE["fail"] = True
    d = upload(voice)
    assert d["ok"]  # Audio ist gesichert, Text folgt getrennt
    page = voice.get("/sprache").text
    assert "Text konnte nicht erkannt werden" in page and "Transkribieren" in page
    STATE["fail"] = False
    r = voice.post(f"/notes/{d['id']}/retry")
    assert "Text erkannt" in r.text and "Prompt kopieren" in r.text
    r = voice.post(f"/notes/{d['id']}/delete")
    assert "Aufnahme gelöscht" in r.text and list((tmp_path / "notes").iterdir()) == []


def test_empty_upload_rejected(voice: TestClient) -> None:
    r = voice.post("/api/notes", files={"audio": ("d.webm", b"", "audio/webm")})
    assert r.status_code == 400 and r.json()["msg"] == "Aufnahme ist leer"


def test_header_icons_and_bottom_bar(voice: TestClient) -> None:
    page = voice.get("/").text
    header = page.split('<header class="topbar">')[1].split("</header>")[0]
    assert 'href="/mehr"' in header and 'href="/verlauf"' in header and 'id="top-search"' in header
    assert 'id="note-rec"' not in header  # langes Diktat: Sprache-Tab
    bottom = page.split('class="bottomnav')[1].split("</nav>")[0]
    assert 'href="/mehr"' not in bottom and bottom.count("<a ") == 5
    for href in ("/einkauf", "/scan", "/sprache", "/labels"):
        assert f'href="{href}"' in bottom
    assert 'href="/platz"' not in bottom
    assert 'href="/suche"' not in bottom
