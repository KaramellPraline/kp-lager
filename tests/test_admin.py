import re

import httpx
from fastapi.testclient import TestClient


def node_of(r: httpx.Response) -> str:
    return str(r.url.path).rsplit("/", 1)[1]


def test_admin_tab_lists_all_prefixes(client: TestClient) -> None:
    page = client.get("/settings/admin").text
    for p in ("RAU", "REG", "WBA", "TBX", "EUR", "KIS", "SOR", "BIN", "PPE", "ART"):
        assert f">{p} · " in page
    assert 'href="/settings/admin" class="active"' in page
    assert 'href="/settings/admin"' in client.get("/settings").text


def test_set_next_number_and_guard_against_used(client: TestClient) -> None:
    client.post("/containers", data={"name": "Box", "kind": "eurobox", "code": "EUR-005"})
    r = client.post("/settings/admin/next", data={"prefix": "EUR", "number": "50"})
    assert "nächster Code ist jetzt EUR-050" in r.text
    assert "nächster EUR-050" in r.text
    r = client.post("/settings/admin/next", data={"prefix": "EUR", "number": "3"},
                    headers={"referer": "/settings/admin"})  # fmt: skip
    assert "mindestens 6" in r.text
    r = client.post("/settings/admin/next", data={"prefix": "EUR", "number": "6"})
    assert "EUR-006" in r.text  # zurück auf niedrigeren, freien Wert erlaubt


def test_reset_releases_reserved_numbers(client: TestClient) -> None:
    fields = {
        "code": ["KIS-001", "KIS-002", "KIS-003"],
        "text": ["", "", ""],
        "extra": ["", "", ""],
    }
    client.post("/labels/export", data={**fields, "fmt": "xlsx"})  # Vorrat reserviert bis KIS-003
    assert "nächster KIS-004" in client.get("/settings/admin").text
    r = client.post("/settings/admin/reset", data={"prefix": "KIS"})
    assert "KIS zurückgesetzt – nächster Code KIS-001" in r.text


def test_remove_single_codes(client: TestClient) -> None:
    box = node_of(
        client.post("/containers", data={"name": "Box", "kind": "kiste", "code": "KIS-007"})
    )
    r = client.post(f"/n/{box}/items", data={"name": "Zange"})  # bekommt ART-0001
    item = re.findall(r'id="item-(\d+)"', r.text)[0]
    client.post(f"/labels/queue/item/{item}")
    r = client.post("/settings/admin/remove", data={"code": "ART-0001"})
    assert "ART-0001 von „Zange“ entfernt" in r.text
    assert "chip code" not in client.get(f"/items/{item}").text.split("</h1>")[1].split("</div>")[0]
    assert 'value="ART-0001"' not in client.get("/labels/queue").text  # aus Warteschlange
    r = client.post("/settings/admin/remove", data={"code": "KIS-007"})
    assert "KIS-007 von „Box“ entfernt" in r.text
    assert client.get(f"/n/{box}").status_code == 200  # Behälter bleibt
    r = client.post(
        "/settings/admin/remove", data={"code": "KIS-999"}, headers={"referer": "/settings/admin"}
    )
    assert "nicht vergeben" in r.text
