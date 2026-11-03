"""M37: D30-PC-Bridge (lokaler Druckdienst) und Bridge-Modus des Servers."""

import threading
from collections.abc import Iterator
from pathlib import Path

import httpx
import pytest
from fastapi.testclient import TestClient
from PIL import Image

from app import d30_bridge
from app.config import Settings
from app.web import create_app

SERVER = "https://lager.test"


@pytest.fixture
def bridge() -> Iterator[tuple[str, list[int], list[str]]]:
    printed: list[int] = []
    fetched: list[str] = []

    def fetch(code: str) -> Image.Image:
        fetched.append(code)
        return Image.new("1", (320, 96), 1)

    srv = d30_bridge.make_server(
        SERVER, port=0, fetch=fetch,
        printer=lambda imgs: printed.extend(i.size[0] for i in imgs),
        status=lambda: (True, ""),
    )  # fmt: skip
    t = threading.Thread(target=srv.serve_forever, daemon=True)
    t.start()
    yield f"http://127.0.0.1:{srv.server_address[1]}", printed, fetched
    srv.shutdown()
    srv.server_close()


def test_bridge_status_and_print(bridge: tuple[str, list[int], list[str]]) -> None:
    url, printed, fetched = bridge
    h = {"Origin": SERVER}
    r = httpx.get(f"{url}/status", headers=h)
    assert r.json() == {"bridge": True, "server": SERVER, "available": True, "msg": ""}
    assert r.headers["access-control-allow-origin"] == SERVER
    assert r.headers["access-control-allow-private-network"] == "true"
    r = httpx.post(f"{url}/print", headers=h, json={"codes": ["cbl-001", "CBL-002", "cbl-001"]})
    assert r.json() == {"ok": True, "printed": 2, "codes": ["CBL-001", "CBL-002"]}
    assert printed == [320, 320] and fetched == ["CBL-001", "CBL-002"]


def test_bridge_rejects_foreign_origin_and_bad_codes(
    bridge: tuple[str, list[int], list[str]],
) -> None:
    url, printed, _ = bridge
    assert httpx.get(f"{url}/status", headers={"Origin": "https://evil.example"}).status_code == 403
    pre = httpx.options(f"{url}/print", headers={"Origin": SERVER})
    assert pre.status_code == 204 and pre.headers["access-control-allow-private-network"] == "true"
    bad = httpx.options(f"{url}/print", headers={"Origin": "https://evil.example"})
    assert bad.status_code == 403
    for body in (
        {"codes": []},
        {"codes": ["../etc"]},
        {"codes": ["x"]},
        {"codes": ["ART-001"] * 0},
    ):
        assert httpx.post(f"{url}/print", headers={"Origin": SERVER}, json=body).status_code == 400
    many = [f"ART-{n:03d}" for n in range(31)]
    assert (
        httpx.post(f"{url}/print", headers={"Origin": SERVER}, json={"codes": many}).status_code
        == 400
    )
    assert httpx.get(f"{url}/nix", headers={"Origin": SERVER}).status_code == 404
    assert printed == []


def test_bridge_reports_printer_errors() -> None:
    def boom(_imgs: list[Image.Image]) -> None:
        raise RuntimeError("D30 nicht gefunden")

    srv = d30_bridge.make_server(
        SERVER, port=0, fetch=lambda c: Image.new("1", (320, 96)), printer=boom
    )
    threading.Thread(target=srv.serve_forever, daemon=True).start()
    try:
        r = httpx.post(
            f"http://127.0.0.1:{srv.server_address[1]}/print", json={"codes": ["ART-001"]}
        )
        assert r.status_code == 502 and "D30 nicht gefunden" in r.json()["error"]
    finally:
        srv.shutdown()
        srv.server_close()


@pytest.fixture
def bridged(tmp_path: Path) -> Iterator[TestClient]:
    s = Settings(data_dir=tmp_path, base_url=SERVER, d30=False, d30_bridge=True)
    with TestClient(create_app(s)) as c:
        yield c


def test_server_in_bridge_mode_hands_codes_to_browser(bridged: TestClient) -> None:
    c = bridged
    assert c.get("/d30/status").json() == {"enabled": False, "available": False,
                                           "msg": "aus", "bridge": True}  # fmt: skip
    assert "d30_print" in c.get("/neu/material").text  # Schalter sichtbar
    r = c.post("/quickadd", data={"mode": "container", "text": "Kiste", "kind": "box"})
    box = int(r.url.path.rsplit("/", 1)[1])
    r = c.post("/quickadd", data={"mode": "item", "cat": "CBL", "target": box, "plug_a": "USB-A",
                                  "plug_b": "USB-C", "length": "1", "count": "2", "d30_print": "1"})  # fmt: skip
    assert 'data-d30-codes="CBL-001,CBL-002"' in r.text
    assert "⟦" not in r.text and "Druck über PC-Bridge" in r.text
    assert c.get("/labels/img/CBL-001.png").status_code == 200  # Bridge kann das Bild holen
    r = c.post("/d30/printed", data={"code": ["CBL-001", "cbl-002"]}).json()
    assert r == {"ok": True, "count": 2}
    item = c.get(f"/api/v1/containers/{box}").json()["items"][0]
    assert "Jetzt auf D30 drucken" not in c.get(f"/items/{item['id']}").text  # als gedruckt gebucht
    r = c.post("/d30/print", data={"code": ["CBL-001"], "back": "/"})
    assert 'data-d30-codes="CBL-001"' in r.text


def test_server_without_bridge_unchanged(client: TestClient) -> None:
    assert client.get("/d30/status").json()["enabled"] is False
    assert "data-d30-codes" not in client.get("/").text
