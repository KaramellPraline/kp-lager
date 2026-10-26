import re

import segno
from fastapi.testclient import TestClient

from app import labels


def test_format_and_qr_contains_url() -> None:
    assert labels.format_code(42) == "0042"
    svg = labels.qr_svg("https://lager.test/c/0042")
    assert svg.startswith("<svg") and 'width="' not in svg.split(">")[0]
    # URL passt in kleine QR-Version (gut scanbar auf 2 cm)
    assert segno.make("https://lager.home.lan/c/0042", error="m").version <= 3


def test_sheet_defaults_and_paging(client: TestClient) -> None:
    r = client.get("/labels")
    assert r.status_code == 200
    assert r.text.count('class="label"') == 40
    assert "<b>0001</b>" in r.text and "<b>0040</b>" in r.text
    r = client.get("/labels", params={"start": 5, "count": 45})
    assert r.text.count('class="sheet"') == 2
    assert "<b>0049</b>" in r.text


def test_next_free_after_printing_and_used_codes(client: TestClient) -> None:
    client.post("/labels/printed", data={"last": 40})
    assert "<b>0041</b>" in client.get("/labels", params={"count": 1}).text
    client.post("/containers", data={"name": "Box", "kind": "kiste", "code": "0100"})
    assert "<b>0101</b>" in client.get("/labels", params={"count": 1}).text
    client.post("/labels/printed", data={"last": 10})  # zurücksetzen nicht möglich
    assert "<b>0101</b>" in client.get("/labels", params={"count": 1}).text


def test_label_url_uses_base_url(client: TestClient) -> None:
    r = client.get("/labels", params={"start": 7, "count": 1})
    assert re.search(r"<b>0007</b>", r.text)
    expected = labels.qr_svg("https://lager.test/c/0007")
    assert expected in r.text
