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


def test_start_cable_fields(client: TestClient) -> None:
    page = client.get("/").text
    assert 'data-cat="CBL"' in page and '<select name="plug_a" data-reveal="plug-a-new">' in page
    assert page.index('class="cats-grid"') < page.index(
        'id="free-row"'
    )  # Kategorie vor der Eingabe
    assert "<option>USB-C 90°</option>" in page and '<option value="">wie A</option>' in page
    box = _shelf(client)
    r = client.post("/quickadd", data={"mode": "item", "cat": "CBL", "text": "", "target": box,
                                       "plug_a": "usb c", "plug_b": "DisplayPort", "length": "1,5"})  # fmt: skip
    assert "USB-C – DP 1,5m" in r.text
    item = client.get(f"/api/v1/containers/{box}").json()["items"][0]
    assert item["code"] == "CBL-001" and item["qty"] is None
    page = client.get(f"/items/{item['id']}").text
    assert "<dd>USB-C</dd>" in page and "<dd>DP</dd>" in page and "<dd>1.5 m</dd>" in page
    # nur Stecker A: gleicher Stecker beidseitig
    client.post(
        "/quickadd",
        data={"mode": "item", "cat": "CBL", "target": box, "plug_a": "HDMI", "length": "2"},
    )
    names = sorted(i["name"] for i in client.get(f"/api/v1/containers/{box}").json()["items"])
    assert names == ["HDMI – HDMI 2m", "USB-C – DP 1,5m"]
    # ohne Felder und ohne Text: Fehlermeldung
    r = client.post("/quickadd", data={"mode": "item", "cat": "CBL", "target": box, "text": ""})
    assert "Was soll eingetragen werden?" in r.text


@pytest.mark.parametrize(
    ("text", "name"),
    [
        ("Netzteil 12V 2A 5,5x2,1", "NT 12V 2A DC 5,5x2,1"),
        ("5V 3000mA USB-C", "Netzteil 5V 3A USB-C"),
        ("Steckernetzteil 9 V 1 A Hohlstecker", "Netzteil 9V 1A DC"),
        ("USB-C 20V 3,25A", "Netzteil 20V 3,25A USB-C"),
    ],
)
def test_psu_parse_and_name(text: str, name: str) -> None:
    from app import psus

    assert psus.name(psus.complete(psus.parse(text))) == name
    assert len(name) <= 24


def test_start_psu_fields_and_free_text(client: TestClient) -> None:
    page = client.get("/").text
    assert 'data-cat="PSU"' in page and 'name="volt"' in page and 'name="psu_plug"' in page
    assert "<option>DC 5,5x2,1</option>" in page
    box = _shelf(client)
    r = client.post("/quickadd", data={"mode": "item", "cat": "PSU", "target": box,
                                       "volt": "12", "amp": "2,5", "psu_plug": "5.5x2.1"})  # fmt: skip
    assert "Netzteil 12V 2,5A DC 5,5x2,1" in r.text or "NT 12V 2,5A DC 5,5x2,1" in r.text
    client.post(
        "/quickadd", data={"mode": "item", "cat": "PSU", "target": box, "text": "5V 2A USB-C"}
    )
    items = {i["code"]: i for i in client.get(f"/api/v1/containers/{box}").json()["items"]}
    assert items["PSU-002"]["name"] == "Netzteil 5V 2A USB-C" and items["PSU-002"]["qty"] is None
    page = client.get(f"/items/{items['PSU-001']['id']}").text
    assert "<dd>12 V</dd>" in page and "<dd>2.5 A</dd>" in page and "<dd>30 W</dd>" in page
    assert "Bitte die Spannung" in client.post("/quickadd", data={
        "mode": "item", "cat": "PSU", "target": box, "amp": "2"}).text  # fmt: skip


def test_other_plug_camera_and_asset_version(client: TestClient) -> None:
    page = client.get("/").text
    assert 'class="mic photo-trigger"' not in page and 'class="photo-trigger"' in page
    assert "/static/app.js?v=" in page and "/static/style.css?v=" in page
    box = _shelf(client)
    r = client.post("/quickadd", data={"mode": "item", "cat": "CBL", "target": box, "plug_a": "neu",
                                       "plug_a_new": "usb c", "plug_b": "", "length": "0,5"})  # fmt: skip
    assert "USB-C – USB-C 0,5m" in r.text
    r = client.post("/quickadd", data={"mode": "item", "cat": "PSU", "target": box, "volt": "19",
                                       "amp": "3.42", "psu_plug": "neu", "psu_plug_new": "4.0x1.7"})  # fmt: skip
    assert "19V 3,42A DC 4,0x1,7" in r.text


def test_unknown_plug_kept_as_typed(client: TestClient) -> None:
    assert cables.name(cables.parse("USB-A – Hohlstecker 1,5m")) == "USB-A – Hohlstecker 1,5m"
    box = _shelf(client)
    r = client.post("/quickadd", data={"mode": "item", "cat": "CBL", "target": box, "plug_a": "USB-A",
                                       "plug_b": "neu", "plug_b_new": "Hohlstecker", "length": "1,5"})  # fmt: skip
    assert "USB-A – Hohlstecker 1,5m" in r.text


@pytest.mark.parametrize(
    ("text", "inp"),
    [
        ("12V 2A 5,5x2,1 Kaltgerätestecker", "Kaltgerät C14"),
        ("5V 3A USB-C Steckernetzteil 230V", "Direkt in Steckdose"),
        ("19V 3,42A Euro Stecker ohne Erdung", "Euro-Stecker (ohne Erdung)"),
        ("12V 1A Schuko 100-240V", "Schuko (geerdet)"),
        ("9V 1A C8", "Kaltgerät C8"),
        ("19V 4,7A Mickey Mouse", "Kaltgerät C6"),
        ("12V 2A Wechselaufsatz", "Direkt, Wechselaufsatz"),
        ("24V 5A Hutschiene", "Hutschiene"),
        ("12V 5A Schraubklemmen", "Schraubklemmen 230 V"),
    ],
)
def test_psu_input_recognised(text: str, inp: str) -> None:
    from app import psus

    found = psus.parse(text)
    assert found["input"] == inp
    assert found["volt"] in {"5", "9", "12", "19", "24"}  # 230 V ist nie die Ausgangsspannung


def test_start_psu_input_select_and_datasheet(client: TestClient) -> None:
    page = client.get("/").text
    sel = page.split('name="psu_input"')[1].split("</select>")[0]
    for label in ("Kaltgerät C14", "Euro-Stecker (ohne Erdung)", "Schuko (geerdet)", "Direkt in Steckdose",
                  "Hutschiene", "Festes Netzkabel", "Anderer …"):  # fmt: skip
        assert label in sel
    assert (
        'name="psu_input_new"' in page
        and "Kaltgeräte C14" not in page.split('name="psu_plug"')[1][:900]
    )
    box = _shelf(client)
    client.post("/quickadd", data={"mode": "item", "cat": "PSU", "target": box, "volt": "12", "amp": "2",
                                   "psu_plug": "DC 5,5x2,1", "psu_input": "Kaltgerät C14"})  # fmt: skip
    client.post("/quickadd", data={"mode": "item", "cat": "PSU", "target": box, "volt": "5", "amp": "1",
                                   "psu_input": "neu", "psu_input_new": "ohne erdung"})  # fmt: skip
    client.post(
        "/quickadd",
        data={"mode": "item", "cat": "PSU", "target": box, "text": "9V 1A Steckernetzteil"},
    )
    items = {i["code"]: i for i in client.get(f"/api/v1/containers/{box}").json()["items"]}
    p1 = client.get(f"/items/{items['PSU-001']['id']}").text
    assert "Eingang (Netzseite)" in p1 and "<dd>Kaltgerät C14</dd>" in p1
    assert "Eingang Kaltgerät C14" in p1  # vollständiger Name
    assert (
        "<dd>Euro-Stecker (ohne Erdung)</dd>" in client.get(f"/items/{items['PSU-002']['id']}").text
    )
    assert "<dd>Direkt in Steckdose</dd>" in client.get(f"/items/{items['PSU-003']['id']}").text
