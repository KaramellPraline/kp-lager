"""D30-Direktdruck: Status-Anzeige, Drucken beim Eintragen und am Teil (Drucker simuliert)."""

from collections.abc import Iterator
from pathlib import Path

import pytest
from fastapi.testclient import TestClient
from PIL import Image

from app import d30
from app.config import Settings
from app.web import create_app


@pytest.fixture
def printer(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> Iterator[tuple[TestClient, list[int]]]:
    sent: list[int] = []
    monkeypatch.setattr(d30, "send", lambda imgs: sent.extend(i.size[0] for i in imgs))
    monkeypatch.setattr(d30, "status", lambda force=False: (True, ""))
    with TestClient(
        create_app(Settings(data_dir=tmp_path, base_url="https://x.test", d30=True))
    ) as c:
        yield c, sent


def _box(c: TestClient) -> int:
    r = c.post("/quickadd", data={"mode": "container", "text": "Kiste", "kind": "box"})
    return int(r.url.path.rsplit("/", 1)[1])


def test_status_and_checkbox(printer: tuple[TestClient, list[int]]) -> None:
    c, _ = printer
    assert c.get("/d30/status").json() == {"enabled": True, "available": True, "msg": ""}
    assert "d30_print" in c.get("/").text


def test_off_by_default(client: TestClient) -> None:
    assert client.get("/d30/status").json()["enabled"] is False
    assert "d30_print" not in client.get("/").text


def test_print_on_quickadd_marks_printed(printer: tuple[TestClient, list[int]]) -> None:
    c, sent = printer
    box = _box(c)
    r = c.post("/quickadd", data={"mode": "item", "cat": "CBL", "target": box, "plug_a": "USB-A",
                                  "plug_b": "USB-C", "length": "1", "count": "2", "d30_print": "1"})  # fmt: skip
    assert sent == [320, 320] and "2 Etiketten gedruckt" in r.text
    items = c.get(f"/api/v1/containers/{box}").json()["items"]
    assert all(c.get(f"/items/{i['id']}").text.count("Jetzt auf D30 drucken") == 0 for i in items)
    assert "Etikett offen" not in c.get(f"/items/{items[0]['id']}").text


def test_button_on_item_until_printed(printer: tuple[TestClient, list[int]]) -> None:
    c, sent = printer
    box = _box(c)
    c.post("/quickadd", data={"mode": "item", "cat": "ART", "target": box, "text": "Schraube"})
    item = c.get(f"/api/v1/containers/{box}").json()["items"][0]
    page = c.get(f"/items/{item['id']}").text
    assert "Jetzt auf D30 drucken" in page
    r = c.post("/d30/print", data={"code": item["code"], "back": f"/items/{item['id']}"})
    assert "1 Etikett gedruckt" in r.text and sent == [320]
    assert "Jetzt auf D30 drucken" not in c.get(f"/items/{item['id']}").text


def test_print_error_keeps_item(
    printer: tuple[TestClient, list[int]], monkeypatch: pytest.MonkeyPatch
) -> None:
    c, _ = printer
    from app.repo import LagerError

    def boom(imgs: list[Image.Image]) -> None:
        raise LagerError("D30 nicht gefunden")

    monkeypatch.setattr(d30, "send", boom)
    box = _box(c)
    r = c.post(
        "/quickadd",
        data={"mode": "item", "cat": "ART", "target": box, "text": "Mutter", "d30_print": "1"},
    )
    assert "nicht gedruckt: D30 nicht gefunden" in r.text
    assert c.get(f"/api/v1/containers/{box}").json()["items"][0]["name"] == "Mutter"
