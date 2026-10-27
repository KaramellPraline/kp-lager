import re
from pathlib import Path
from typing import Any

import httpx
import pytest
from fastapi.testclient import TestClient

from app import quick, web
from app.config import Settings
from app.web import create_app


def node_of(r: httpx.Response) -> str:
    return str(r.url.path).rsplit("/", 1)[1]


def box(client: TestClient, name: str = "Box", **form: str) -> str:
    return node_of(client.post("/containers", data={"name": name, "kind": "kiste", **form}))


def item_ids(html: str) -> list[str]:
    return re.findall(r'id="item-(\d+)"', html)


@pytest.mark.parametrize(
    ("text", "expected"),
    [("3 Rollen Lötzinn", (3, "Rollen", "Lötzinn")), ("2x Multimeter", (2, "", "Multimeter")),
     ("10 m Kabel rot", (10, "m", "Kabel rot")),
     ("4x40 Holzschrauben", (None, "", "4x40 Holzschrauben")),
     ("Lötzinn", (None, "", "Lötzinn")), ("M3 Muttern", (None, "", "M3 Muttern"))],
)  # fmt: skip
def test_quick_parse(text: str, expected: tuple[int | None, str, str]) -> None:
    assert quick.parse(text) == expected


def test_quick_add_and_undo(client: TestClient) -> None:
    b = box(client)
    r = client.post(f"/n/{b}/items", data={"name": "3 Rollen Lötzinn"})
    assert "„Lötzinn“ eingelagert" in r.text and "Rückgängig" in r.text
    assert "3 Rollen" in r.text
    undo = re.search(r'action="/undo/(\d+)"', r.text).group(1)  # type: ignore[union-attr]
    r = client.post(f"/undo/{undo}", headers={"referer": f"/n/{b}"})
    assert "wieder entfernt" in r.text and item_ids(r.text) == []
    r = client.post(f"/undo/{undo}", headers={"referer": f"/n/{b}"})
    assert "nicht (mehr)" in r.text


def test_undo_take_and_move(client: TestClient) -> None:
    a, b = box(client, "A"), box(client, "B")
    item = item_ids(client.post(f"/n/{a}/items", data={"name": "Akku", "qty": "2"}).text)[0]
    client.post(f"/items/{item}/qty", data={"delta": "-1"})
    client.post(f"/carry/item/{item}")
    client.post(f"/drop/{b}")
    hist = client.get("/verlauf").text
    assert "umgelagert" in hist and "entnommen -1" in hist
    undos = re.findall(r'action="/undo/(\d+)"', hist)
    client.post(f"/undo/{undos[0]}")  # Umlagern zurück
    client.post(f"/undo/{undos[1]}")  # Entnahme zurück
    page = client.get(f"/n/{a}").text
    assert "Akku" in page and ">2<" in page.replace(" ", "")
    assert 'class="item undone"' in client.get("/verlauf").text


def test_undo_container_move_back_to_top(client: TestClient) -> None:
    keller, kiste = box(client, "Keller"), box(client, "Kiste")

    def crumbs() -> str:
        return client.get(f"/n/{kiste}").text.split('class="crumbs"')[1].split("</nav>")[0]

    client.post(f"/carry/node/{kiste}")
    client.post(f"/drop/{keller}")
    assert f"/n/{keller}" in crumbs()
    undo = re.findall(r'action="/undo/(\d+)"', client.get("/verlauf").text)[0]
    client.post(f"/undo/{undo}")
    assert f"/n/{keller}" not in crumbs()


def test_lend_and_return(client: TestClient) -> None:
    b = box(client)
    item = item_ids(client.post(f"/n/{b}/items", data={"name": "Bohrmaschine"}).text)[0]
    r = client.post(f"/items/{item}/lend", data={"to": "Nachbar Tom"})
    assert "Verliehen an <b>Nachbar Tom</b>" in r.text
    assert "bei Nachbar Tom" in client.get(f"/n/{b}").text
    assert "Verliehen · <b>1</b>" in client.get("/mehr").text
    assert "Bohrmaschine" in client.get("/verliehen").text
    client.post(f"/items/{item}/return")
    assert "Bohrmaschine" not in client.get("/verliehen").text


def test_shopping_list_min_qty_and_manual(client: TestClient) -> None:
    b = box(client)
    ids = item_ids(client.post(f"/n/{b}/items", data={"name": "Kabelbinder", "qty": "5"}).text)
    client.post(f"/items/{ids[0]}/edit", data={"name": "Kabelbinder", "qty": "5", "min_qty": "10"})
    assert "nachkaufen" in client.get(f"/n/{b}").text
    lst = client.get("/einkauf").text
    assert "Kabelbinder" in lst and "5 / min. 10" in lst
    before = set(item_ids(client.get(f"/n/{b}").text))
    after = item_ids(client.post(f"/n/{b}/items", data={"name": "Klebeband"}).text)
    klebeband = next(i for i in after if i not in before)
    client.post(f"/items/{klebeband}/list")
    assert "Klebeband" in client.get("/einkauf").text
    client.post(f"/items/{klebeband}/list")
    assert "Klebeband" not in client.get("/einkauf").text


def test_free_places(client: TestClient) -> None:
    box(client, "Leere Kiste")
    voll = box(client, "Volle Kiste")
    client.post(f"/n/{voll}/items", data={"name": "X"})
    kasten = node_of(
        client.post("/containers", data={"name": "Kasten", "kind": "sortierkasten", "grid": "2x1"})
    )
    fach = re.findall(r'href="/n/(\d+)" class="cell', client.get(f"/n/{kasten}").text)[0]
    client.post(f"/n/{fach}/items", data={"name": "Dübel"})
    page = client.get("/platz").text
    assert "Leere Kiste" in page and "Volle Kiste" not in page
    assert "1 von 2 frei" in page and "A2" in page


def test_favorites_and_recent(client: TestClient) -> None:
    b = box(client, "Werkzeugkiste")
    assert "Werkzeugkiste" in client.get("/verlauf?tab=gesehen").text  # Besuch beim Anlegen
    assert "Zuletzt angesehen</h2>" not in client.get("/").text
    r = client.post(f"/n/{b}/favorite")
    assert "Als Favorit gemerkt" in r.text and 'class="star on"' in r.text
    assert ">Favoriten</h2>" in client.get("/").text


def test_search_synonyms_and_typos(client: TestClient) -> None:
    b = box(client)
    client.post(f"/n/{b}/items", data={"name": "Innensechskant Schlüsselsatz"})
    client.post(f"/n/{b}/items", data={"name": "Holzschrauben 4x40"})
    assert "Innensechskant" in client.get("/suche", params={"q": "inbus"}).text
    r = client.get("/suche", params={"q": "holzschrabuen"})
    assert "Ergebnisse für" in r.text and "Holzschrauben 4x40" in r.text
    client.post("/settings", data={"synonyms": "werkzeug = schlüsselsatz"})
    assert "Innensechskant" in client.get("/suche", params={"q": "werkzeug"}).text
    assert "Innensechskant" not in client.get("/suche", params={"q": "inbus"}).text


def test_scan_api(client: TestClient) -> None:
    b = box(client, "Ziel", code="KIS-001")
    a = box(client, "Quelle")
    client.post(f"/n/{a}/items", data={"name": "Zange"})  # bekommt ART-0001
    assert client.get("/api/code/kis1").json() == {
        "type": "container",
        "code": "KIS-001",
        "name": "Ziel",
    }
    assert client.get("/api/code/ART-0009").json()["type"] == "unknown"
    r = client.post("/api/move", data={"code": ["HTTPS://X/C", "ART-0001"][1], "target": "KIS-001"})
    assert r.json()["ok"] and "„Zange“ → Ziel" in r.json()["msg"]
    assert "Zange" in client.get(f"/n/{b}").text
    client.post(f"/undo/{r.json()['undo']}")
    assert "Zange" in client.get(f"/n/{a}").text
    assert (
        client.post("/api/move", data={"code": "ART-0001", "target": "EUR-999"}).status_code == 404
    )
    assert "Scannen" in client.get("/scan").text


def test_manifest_icons_and_chat_prompt(client: TestClient) -> None:
    m = client.get("/manifest.webmanifest").json()
    assert m["name"] == "KP Lager" and m["display"] == "standalone"
    assert client.get("/static/icon-192.png").headers["content-type"] == "image/png"
    b = box(client, "Elektronik", code="KIS-002")
    page = client.get(f"/n/{b}").text
    assert "Behälter: code=KIS-002, kind=kiste, name=Elektronik" in page
    assert 'class="mic"' not in page  # ohne Whisper kein Mikrofon-Knopf


def test_transcribe_without_and_with_whisper(
    client: TestClient, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    assert (
        client.post("/api/transcribe", files={"audio": ("a.webm", b"x", "audio/webm")}).status_code
        == 503
    )

    def handler(request: httpx.Request) -> httpx.Response:
        assert request.url.path == "/v1/audio/transcriptions"
        return httpx.Response(200, json={"text": " 3 Rollen Lötzinn "})

    real = httpx.AsyncClient

    def fake_client(**kw: Any) -> httpx.AsyncClient:
        return real(transport=httpx.MockTransport(handler), **kw)

    monkeypatch.setattr(web.httpx, "AsyncClient", fake_client)
    settings = Settings(
        data_dir=tmp_path / "w", base_url="https://lager.test", whisper_url="http://whisper"
    )
    with TestClient(create_app(settings)) as c:
        r = c.post("/api/transcribe", files={"audio": ("a.webm", b"x", "audio/webm")})
        assert r.json() == {"text": "3 Rollen Lötzinn"}
        b = node_of(
            c.post("/containers", data={"name": "B", "kind": "kiste"}, follow_redirects=True)
        )
        assert 'class="mic"' in c.get(f"/n/{b}").text


def test_backup_copies_db_and_photos(tmp_path: Path) -> None:
    import os
    import sqlite3

    from app import backup
    from app.db import connect

    data = tmp_path / "data"
    connect(data / "lager.db").close()
    (data / "photos").mkdir()
    (data / "photos" / "a.jpg").write_bytes(b"x")
    target = tmp_path / "bak"
    old = target / "lager-2000-01-01.db"
    target.mkdir()
    old.write_bytes(b"alt")
    os.utime(old, (0, 0))
    written = backup.run(data, target, keep_days=30)
    assert [p.name.split("-")[0] for p in written] == ["lager", "photos"]
    assert sqlite3.connect(written[0]).execute("PRAGMA user_version").fetchone()[0] >= 5
    assert not old.exists()


@pytest.mark.parametrize(
    ("text", "expected"),
    [("3 Rollen Lötzinn und 50 M3 Muttern", [(3, "Rollen", "Lötzinn"), (50, "", "M3 Muttern")]),
     ("Schrauben und Muttern", [(None, "", "Schrauben und Muttern")]),
     ("2 Zangen, 1 Seitenschneider; 4 m Kabel.", [(2, "", "Zangen"), (1, "", "Seitenschneider"),
                                                  (4, "m", "Kabel")]),
     ("Grund 5 Platten", [(None, "", "Grund 5 Platten")])],
)  # fmt: skip
def test_parse_many(text: str, expected: list[tuple[int | None, str, str]]) -> None:
    assert quick.parse_many(text) == expected


def test_dictation_adds_several_items(client: TestClient) -> None:
    b = box(client)
    r = client.post(f"/n/{b}/items", data={"name": "3 Rollen Lötzinn und 50 M3 Muttern"})
    assert "„Lötzinn“, „M3 Muttern“ eingelagert" in r.text
    assert len(item_ids(r.text)) == 2


def test_transcribe_uses_model_pref_and_token(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    seen: dict[str, str] = {}

    def handler(request: httpx.Request) -> httpx.Response:
        seen["auth"] = request.headers["authorization"]
        seen["body"] = request.content.decode(errors="ignore")
        return httpx.Response(200, json={"text": "50 M3 Muttern"})

    real = httpx.AsyncClient
    monkeypatch.setattr(
        web.httpx, "AsyncClient", lambda **kw: real(transport=httpx.MockTransport(handler), **kw)
    )
    s = Settings(
        data_dir=tmp_path,
        base_url="https://lager.test",
        whisper_url="http://gw",
        whisper_token="t0k",
    )
    with TestClient(create_app(s)) as c:
        assert c.post(
            "/api/transcribe", files={"audio": ("a.webm", b"x", "audio/webm")}
        ).json() == {"text": "50 M3 Muttern"}
    assert seen["auth"] == "Bearer t0k" and 'name="model"\r\n\r\nparakeet' in seen["body"]


def test_home_quick_add_remembers_target(client: TestClient) -> None:
    keller = box(client, "Keller")
    werk = box(client, "Werkstatt")
    page = client.get("/").text
    assert (
        'action="/quickadd"' in page
        and ">Verliehen" not in page.split("</nav>")[1].split("schnell")[0]
    )
    r = client.post("/quickadd", data={"target": keller, "text": "2 Zangen und 5 m Kabel"})
    assert "„Zangen“, „Kabel“ → Keller" in r.text and "Rückgängig" in r.text
    assert re.search(rf'<option value="{keller}" selected>', r.text)  # Ziel gemerkt
    assert (
        "Zangen" in client.get(f"/n/{keller}").text
        and "Zangen" not in client.get(f"/n/{werk}").text
    )
    r = client.post("/quickadd", data={"target": werk, "text": " "}, headers={"referer": "/"})
    assert "Was soll eingetragen werden?" in r.text


def test_home_where_favorites_and_last_three(client: TestClient) -> None:
    ids = [box(client, f"Box {n}") for n in range(12)]
    for i in ids[:11]:
        client.post(f"/n/{i}/favorite")
    for i in ids[:4]:
        client.post("/quickadd", data={"target": i, "text": "Teil"})
    page = client.get("/").text
    favs = re.findall(r'class="pick fav" data-id="(\d+)"', page)
    assert len(favs) == 10  # max. 10 Favoriten zum Wischen
    recent = re.findall(r'class="pick" data-id="(\d+)"', page)
    assert recent == [ids[3], ids[2], ids[1]]  # letzte drei, neueste zuerst
    assert re.search(rf'<option value="{ids[3]}" selected>', page)


def test_add_anything_container_type_and_item(client: TestClient) -> None:
    r = client.post(
        "/quickadd", data={"mode": "container", "text": "Werkstatt", "kind": "raum", "target": ""}
    )
    assert "„Werkstatt“ angelegt" in r.text
    werk = node_of(r)
    r = client.post(
        "/quickadd", data={"mode": "container", "text": "Kiste A", "kind": "kiste", "target": werk}
    )
    assert "Werkstatt" in r.text.split('class="crumbs"')[1].split("</nav>")[0]
    r = client.post("/quickadd", data={"mode": "type", "text": "pneumatic"})
    assert "Typ TYP-005 „pneumatic“ angelegt" in r.text
    r = client.post("/quickadd", data={"mode": "item", "text": "2 Zangen", "target": werk})
    assert "„Zangen“ → Werkstatt" in r.text
    r = client.post(
        "/quickadd", data={"mode": "item", "text": "Zange", "target": ""}, headers={"referer": "/"}
    )
    assert "Erst einen Ort wählen" in r.text


def test_home_sections_configurable(client: TestClient) -> None:
    box(client, "Werkstatt")
    page = client.get("/").text
    assert 'class="tiles"' in page and "Räume und Orte" in page
    form = {
        p: "1"
        for p in (
            "auto_item_code",
            "quick_parse",
            "queue_on_quickadd",
            "queue_on_place",
            "typo_correction",
        )
    }
    client.post("/settings", data={**form, "home_tiles": "", "home_rooms": ""})
    page = client.get("/").text
    assert 'class="tiles"' not in page and "Räume und Orte" not in page
