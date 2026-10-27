import re
from collections.abc import Iterator
from pathlib import Path

import httpx
import pytest
from fastapi.testclient import TestClient

from app import quick, web
from app.config import Settings
from app.web import create_app

SPOKEN = {"text": ""}


@pytest.fixture
def voice(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Iterator[TestClient]:
    real = httpx.AsyncClient
    monkeypatch.setattr(
        web.httpx, "AsyncClient",
        lambda **kw: real(transport=httpx.MockTransport(lambda r: httpx.Response(200, json={"text": SPOKEN["text"]})), **kw),
    )  # fmt: skip
    s = Settings(data_dir=tmp_path, base_url="https://lager.test", whisper_url="http://gw")
    with TestClient(create_app(s)) as c:
        yield c


@pytest.mark.parametrize(
    ("text", "parts"),
    [("Drei Rollen Lötzinn. Weiter. Ein Multimeter, weiter, 50 M3 Muttern weiter", ["Drei Rollen Lötzinn", "Ein Multimeter", "50 M3 Muttern"]),
     ("Weiterleitung Kabel", ["Weiterleitung Kabel"]), ("weiter weiter", [])],
)  # fmt: skip
def test_split_weiter(text: str, parts: list[str]) -> None:
    assert quick.split_weiter(text) == parts


def test_number_words() -> None:
    assert quick.parse("Drei Rollen Lötzinn") == (3, "Rollen", "Lötzinn")
    assert quick.parse("ein Multimeter") == (1, "", "Multimeter")
    assert quick.parse("Einschmelzmutter M3") == (None, "", "Einschmelzmutter M3")
    assert quick.parse_many("zwei Zangen und fünf Meter Kabel") == [
        (2, "", "Zangen"),
        (5, "Meter", "Kabel"),
    ]


def test_segment_fills_inbox_and_sort(voice: TestClient) -> None:
    SPOKEN["text"] = "Drei Rollen Lötzinn, weiter. Ein Multimeter und zwei Zangen weiter"
    d = voice.post("/api/sprache/segment", files={"audio": ("t.webm", b"x", "audio/webm")}).json()
    assert d["ok"] and d["items"] == ["3 Rollen Lötzinn", "1 Multimeter", "2 Zangen"]
    page = voice.get("/zu-sortieren").text
    assert all(n in page for n in ("Lötzinn", "Multimeter", "Zangen"))
    assert "Zu sortieren · 3" in voice.get("/sprache").text
    r = voice.post("/containers", data={"name": "Werkstatt", "kind": "raum"})
    werk = str(r.url.path).rsplit("/", 1)[1]
    item = re.search(r"/zu-sortieren/(\d+)/move", page).group(1)  # type: ignore[union-attr]
    r = voice.post(f"/zu-sortieren/{item}/move", data={"target": werk})
    assert "Einsortiert nach Werkstatt" in r.text
    assert len(re.findall(r"/zu-sortieren/\d+/move", r.text)) == 2
    # Eingang selbst ist kein Ziel in der Auswahl
    assert ">Zu sortieren</option>" not in r.text


def test_empty_segment_ok(voice: TestClient) -> None:
    assert (
        voice.post("/api/sprache/segment", files={"audio": ("t.webm", b"", "audio/webm")}).json()[
            "items"
        ]
        == []
    )
