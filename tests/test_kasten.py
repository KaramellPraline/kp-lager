import io
import re

import httpx
import pytest
from fastapi.testclient import TestClient
from openpyxl import load_workbook

from app import kasten
from app.repo import LagerError


def node_of(r: httpx.Response) -> str:
    return str(r.url.path).rsplit("/", 1)[1]


def norb(client: TestClient) -> str:
    r = client.post("/containers", data={"name": "Kleinteile", "kind": "sortierkasten",
                                          "code": "SOR-001", "model": "norb16"})  # fmt: skip
    return node_of(r)


def test_cells_and_place_checks() -> None:
    m = kasten.MODELS["norb16"]
    assert kasten.cells_of("B2", "2x1") == {"B2", "B3"}
    assert kasten.cells_of("A1", "1x2") == {"A1", "B1"}
    kasten.check_place(m, {}, "A4", "2x2")
    for pos, size, msg in [("A5", "2x1", "passt"), ("B1", "1x2", "Griff"), ("G1", "1x2", "passt")]:
        with pytest.raises(LagerError, match=msg):
            kasten.check_place(m, {}, pos, size)
    with pytest.raises(LagerError, match="belegt"):
        kasten.check_place(m, {"A2": 1}, "A1", "2x1")


def test_norb16_topview_place_and_fill(client: TestClient) -> None:
    k = norb(client)
    page = client.get(f"/n/{k}").text
    assert "Kistenberg NORB16 – Draufsicht" in page
    assert page.count('class="tv-free') == 32  # 35 Zellen − 3 Griff
    assert page.count('class="tv-blocked"') == 3
    r = client.post(f"/n/{k}/bins", data={"position": "A1", "size": "2x1", "div": "3x1"})
    assert "Einsatz BIN-001 (2x1) bei A1" in r.text
    assert r.text.count('class="tv-free') == 30
    assert r.text.count('class="tv-comp') == 3
    r = client.post(
        f"/n/{k}/bins", data={"position": "A2", "size": "1x1"}, headers={"referer": f"/n/{k}"}
    )
    assert "schon belegt" in r.text
    r = client.post(f"/n/{k}/fill")
    assert "30 Einsätze 1x1 angelegt" in r.text and "Kasten ist voll belegt" in r.text


def test_quickadd_puts_item_in_compartment_and_queues_bin_label(client: TestClient) -> None:
    k = norb(client)
    client.post(f"/n/{k}/bins", data={"position": "B2", "size": "2x1", "div": "2x1"})
    page = client.get(f"/n/{k}").text
    targets = re.findall(r'<option value="(\d+)">B2 · Fach (A\d)', page)
    assert [t[1] for t in targets] == ["A1", "A2"]
    r = client.post(
        f"/n/{k}/quickadd", data={"target": targets[1][0], "text": "50 M3 Muttern", "queue": "1"}
    )
    assert "„M3 Muttern“ → Fach A2" in r.text and "Inhaltsetikett BIN-001 vorgemerkt" in r.text
    assert "M3 Muttern" in r.text  # erscheint in der Draufsicht
    client.post(
        f"/n/{k}/quickadd", data={"target": targets[0][0], "text": "Dübel 6mm", "queue": "1"}
    )
    labels_page = client.get("/labels").text.split("Inhaltsetiketten (")[1].split("</section>")[0]
    assert labels_page.count("BIN-001 · ") == 1  # aktualisiert, nicht doppelt
    assert (
        "BIN-001 · M3 Muttern, Dübel 6mm" in labels_page
        or "BIN-001 · Dübel 6mm, M3 Muttern" in labels_page
    )
    client.post(f"/labels/queue/kasten/{k}")  # Bin-Tag oben: nur Kasten + Position
    queue = client.get("/labels/queue").text
    assert 'value="SOR-001 B2"' in queue and "M3 Muttern" not in queue


def test_queue_export_formats_and_clear(client: TestClient) -> None:
    k = norb(client)
    client.post(f"/n/{k}/bins", data={"position": "A1", "size": "1x1"})
    client.post(f"/n/{k}/bins", data={"position": "A2", "size": "1x1"})
    client.post(f"/labels/queue/kasten/{k}")
    fields = {"code": ["BIN-001", "BIN-002"], "text": ["Lötzinn", "Kabel"], "extra": ["", ""]}
    r = client.post("/labels/queue/remove?code=BIN-002", data=fields)
    assert "BIN-002 entfernt" in r.text and 'value="BIN-002"' not in r.text
    one = {"code": ["BIN-001"], "text": ["Lötzinn"], "extra": [""], "source": "queue"}
    a4 = client.post("/labels/export", data={**one, "fmt": "a4"})
    assert "grid-template-columns: repeat(5, 40mm)" in a4.text and "<b>BIN-001</b>" in a4.text
    assert 'value="BIN-001"' not in client.get("/labels/queue").text  # nach Export geleert
    client.post(f"/labels/queue/node/{k}")
    kasten_label = {"code": ["SOR-001"], "text": ["Kleinteile"], "extra": [""], "source": "queue"}
    x = client.post("/labels/export", data={**kasten_label, "fmt": "xlsx"})
    ws = load_workbook(io.BytesIO(x.content)).active
    assert ws is not None and ws["A2"].value == "SOR-001"


def test_bin_page_shows_cad_command_and_items_queue(client: TestClient) -> None:
    k = norb(client)
    r = client.post(f"/n/{k}/bins", data={"position": "C3", "size": "1x2", "div": "1x2"})
    m = re.search(r'<a href="/n/(\d+)">\s*<rect[^>]*class="tv-bin"', r.text)
    assert m
    bin_id = m.group(1)
    page = client.get(f"/n/{bin_id}").text
    assert "cad/norb_bins.py 1x2 --div 1x2" in page
    item = client.post(f"/n/{bin_id}/items", data={"name": "Zange"})
    item_id = re.findall(r'id="item-(\d+)"', item.text)[0]
    assert "in Warteschlange" in client.post(f"/labels/queue/item/{item_id}").text
