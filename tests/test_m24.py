import json
import re
from collections.abc import Iterator
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from app import ai
from app.config import Settings
from app.web import create_app

ANSWER: dict[str, object] = {}


@pytest.fixture
def kic(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Iterator[TestClient]:
    """App mit lokaler KI; die Antwort des Modells kommt aus ANSWER."""
    seen: list[str] = []

    def fake_chat(url: str, token: str, model: str, messages: list[dict[str, str]]) -> str:
        seen.append(model)
        ANSWER["_system"] = messages[0]["content"]
        return json.dumps({k: v for k, v in ANSWER.items() if not k.startswith("_")})

    monkeypatch.setattr(ai, "chat", fake_chat)
    s = Settings(data_dir=tmp_path, base_url="https://lager.test", whisper_url="http://gw")
    with TestClient(create_app(s)) as c:
        c.models = seen  # type: ignore[attr-defined]
        yield c


def _shelf(c: TestClient) -> int:
    r = c.post("/quickadd", data={"mode": "container", "text": "Regal", "kind": "shelf"})
    return int(r.url.path.rsplit("/", 1)[1])


def _item(c: TestClient, shelf: int, text: str, cat: str) -> int:
    c.post("/quickadd", data={"mode": "item", "text": text, "target": shelf, "cat": cat})
    items = c.get(f"/api/v1/containers/{shelf}").json()["items"]
    return int(next(i["id"] for i in items if i["name"] in text))


def test_weigh_filament_and_resin(client: TestClient) -> None:
    shelf = _shelf(client)
    fil = _item(client, shelf, "PLA weiß", "FIL")
    client.post(f"/items/{fil}/specs", data={"material": "fil", "spec_weight": "1000",
                                            "spec_spool_weight": "200", "spec_density": "1.24"})  # fmt: skip
    r = client.post(f"/items/{fil}/weigh", data={"gross": "840"})
    assert "Rest: 640 g ≈ 215 m" in r.text and "64 %" in r.text
    r = client.post(f"/items/{fil}/weigh", data={"gross": "300"})
    assert "fast leer" in r.text and "Einkaufsliste" in r.text
    assert "PLA weiß" in client.get("/einkauf").text
    res = _item(client, shelf, "Resin grau", "RES")
    r = client.post(f"/items/{res}/weigh", data={"gross": "620"})
    assert "Leergewicht 120 g angenommen" in r.text and "≈ 455 ml" in r.text
    assert "Rest" in client.get("/material").text
    assert "nur für Filament" in client.post(f"/items/{_item(client, shelf, 'Zange', 'ART')}/weigh",
                                             data={"gross": "5"}).text  # fmt: skip


def test_cmp_profile_and_enrich_fills_only_empty_specs(kic: TestClient) -> None:
    shelf = _shelf(kic)
    cmp_id = _item(kic, shelf, "BME280", "CMP")
    page = kic.get(f"/items/{cmp_id}").text
    assert "Bauform" in page and "Schnittstelle" in page and "Mit KI ausfüllen" in page
    kic.post(f"/items/{cmp_id}/specs", data={"material": "cmp", "spec_package": "LGA-8"})
    ANSWER.clear()
    ANSWER.update({"name": "BME280", "full_name": "Bosch BME280 Umweltsensor", "type": "Sensor",
                   "model": "BME280", "tags": ["sensor", "i2c"],
                   "specs": {"package": "Modul", "interface": "I2C, SPI", "voltage": "3.3", "xyz": "1"}})  # fmt: skip
    r = kic.post(f"/items/{cmp_id}/ai")
    assert "KI-Vorschlag übernommen" in r.text
    assert "interface = Schnittstelle" in str(ANSWER["_system"])
    assert kic.models == ["fast"]  # type: ignore[attr-defined]
    page = kic.get(f"/items/{cmp_id}").text
    assert "<dd>LGA-8</dd>" in page and "<dd>Modul</dd>" not in page  # eigene Eingabe bleibt
    assert "<dd>I2C, SPI</dd>" in page and "<dd>3.3 V</dd>" in page and "xyz" not in page
    # Ablehnen stellt auch die Eigenschaften wieder her
    kic.post(f"/freigaben/item/{cmp_id}/reject")
    assert "<dd>I2C, SPI</dd>" not in kic.get(f"/items/{cmp_id}").text


def test_ki_support_queue_and_inventory(kic: TestClient) -> None:
    shelf = _shelf(kic)
    a = _item(kic, shelf, "Akkuschrauber", "ART")
    b = _item(kic, shelf, "Bohrer Set", "ART")
    page = kic.get("/ki").text
    assert "Noch ungeprüft: <b>2</b>" in page and f'data-ids="{a},{b}"' in page
    assert "Akkuschrauber" in page.split('id="queue"')[1]
    kic.post(f"/ki/item/{a}/ok")  # Passt so
    page = kic.get("/ki").text
    assert "Noch ungeprüft: <b>1</b>" in page and "Bohrer Set" in page.split('id="queue"')[1]
    ANSWER.clear()
    ANSWER.update({"full_name": "Bohrer-Set HSS 1–10 mm", "tags": "bohrer hss metall"})
    d = kic.post(f"/api/ai/item/{b}").json()
    assert d["ok"] and "übernommen" in d["msg"]
    page = kic.get("/ki").text
    assert "KI-Vorschlag prüfen" in page and "1 warten auf Prüfung" in page
    kic.post(f"/ki/item/{b}/approve")
    assert "Nichts mehr zu prüfen" in kic.get("/ki").text
    assert "KI-Support" in kic.get("/mehr").text
    assert kic.get("/ki?skip=5").status_code == 200


def test_content_labels_for_bins_and_compartments(client: TestClient) -> None:
    r = client.post("/containers", data={"name": "Kleinteile", "kind": "sortingbox",
                                          "code": "SOR-001", "model": "norb16"})  # fmt: skip
    k = int(r.url.path.rsplit("/", 1)[1])
    client.post(f"/n/{k}/bins", data={"position": "A1", "size": "1x1"})
    page = client.get(f"/n/{k}").text
    target = re.findall(r'<option value="(\d+)">A1', page)[0]
    client.post(f"/n/{k}/quickadd", data={"target": target, "text": "M3 Muttern", "queue": "1"})
    labels_page = client.get("/labels").text
    assert "Inhaltsetiketten (1)" in labels_page and "BIN-001 · M3 Muttern" in labels_page
    a4 = client.get("/labels/content/a4").text
    assert "<b>BIN-001</b><span>M3 Muttern</span>" in a4
    x = client.get("/labels/content.xlsx")
    assert x.status_code == 200 and x.content[:2] == b"PK"
    assert "Inhaltsetiketten (0)" in client.get("/labels").text  # nach Export geleert
    bin_id = target
    r = client.post(f"/labels/content/node/{bin_id}")
    assert "vorgemerkt" in r.text
