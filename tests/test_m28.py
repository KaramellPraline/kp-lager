import json

import pytest
from fastapi.testclient import TestClient

from app import cables


@pytest.mark.parametrize(
    ("text", "name"),
    [
        ("Display Port 1.5m", "DP – DP 1,5m"),
        ("HDMI 1.8m", "HDMI – HDMI 1,8m"),
        ("LAN 2m", "RJ45 – RJ45 2m"),
        ("USB 2.0 Verlängerung 2m", "USB-A – USB-A Buchse 2m"),
        ("USB A-B 2m", "USB-A – USB-B 2m"),
        ("USB A-C 2.5", "USB-A – USB-C 2,5m"),
        ("USB A-Micro 0.9m", "USB-A – Micro-USB 0,9m"),
        ("USB C 1m", "USB-C – USB-C 1m"),
        ("USB C-C90 2.5", "USB-C – USB-C 90° 2,5m"),
        ("USB-C auf HDMI 2m", "USB-C – HDMI 2m"),
        ("Micro-USB 1m", "USB-A – Micro-USB 1m"),
        ("HDMI auf DVI 150cm", "HDMI – DVI 1,5m"),
        ("Kaltgerät 1,5m", "Schuko – C13 1,5m"),
        ("NYM-J 3x1,5", ""),  # kein Steckerkabel
        ("Toslink 1m", "Toslink – Toslink 1m"),
    ],
)
def test_parse_and_name(text: str, name: str) -> None:
    assert cables.name(cables.parse(text)) == name
    assert len(name) <= 24  # passt aufs 40×12-Etikett


def _shelf(c: TestClient) -> int:
    r = c.post("/quickadd", data={"mode": "container", "text": "Kabelbox", "kind": "box"})
    return int(r.url.path.rsplit("/", 1)[1])


def test_new_cable_from_start_and_edit(client: TestClient) -> None:
    box = _shelf(client)
    client.post(
        "/quickadd",
        data={"mode": "item", "text": "USB A-C 2m, 3 m HDMI", "target": box, "cat": "CBL"},
    )
    items = {i["code"]: i for i in client.get(f"/api/v1/containers/{box}").json()["items"]}
    assert items["CBL-001"]["name"] == "USB-A – USB-C 2m"
    assert items["CBL-002"]["name"] == "HDMI – HDMI 3m" and items["CBL-002"]["qty"] is None
    page = client.get(f"/items/{items['CBL-001']['id']}").text
    assert "Stecker Seite A" in page and "<dd>USB-A</dd>" in page and "<dd>2 m</dd>" in page
    assert "Kabel USB-A auf USB-C, 2 m" in page
    # Länge im Datenblatt ändern -> Name folgt, Etikett wieder offen
    r = client.post(f"/items/{items['CBL-001']['id']}/specs", data={
        "material": "cbl", "spec_plug_a": "USB-A", "spec_plug_b": "USB-C", "spec_length": "1"})  # fmt: skip
    assert "USB-A – USB-C 1m" in r.text and "Etikett offen" in r.text


def test_import_cable_from_specs_or_name(client: TestClient, tmp_path) -> None:  # type: ignore[no-untyped-def]
    from app import importer, repo
    from app.db import connect

    conn = connect(tmp_path / "lager.db")
    payload = json.dumps([{"code": None, "name": "Kabelkiste", "kind": "box", "items": [
        {"name": "Displayport Kabel", "cat": "CBL",
         "specs": {"plug_a": "DisplayPort", "plug_b": "HDMI", "length": "2"}},
        {"name": "LAN 5m", "cat": "CBL"}]}])  # fmt: skip
    report = importer.run(conn, payload, commit=True)
    assert not report.errors
    box = repo.get_container_by_code(conn, report.containers_created[0].split()[0])
    names = sorted(i["name"] for i in repo.items_in(conn, box["id"]))  # type: ignore[index]
    assert names == ["DP – HDMI 2m", "RJ45 – RJ45 5m"]
