from fastapi.testclient import TestClient

from app import codes, kinds


def test_new_kind_from_start(client: TestClient) -> None:
    r = client.post(
        "/quickadd",
        data={
            "mode": "container",
            "text": "Werkbank links",
            "kind": "neu",
            "new_kind": "Schublade",
            "new_prefix": "sch",
        },
    )
    assert r.status_code == 200 and "Werkbank links" in r.text
    assert codes.KIND_PREFIX["schublade"] == "SCH" and codes.normalize("sch1") == "SCH-001"
    page = client.get("/labels").text
    assert "SCH</b>-001 · Schublade" in page
    assert "Schublade · SCH" in client.get("/").text
    # Code vergeben über die neue Art
    node_id = int(r.url.path.rsplit("/", 1)[1])
    assert "SCH-001" in client.post(f"/n/{node_id}/code").text


def test_kind_rules(client: TestClient) -> None:
    assert "schon vergeben" in client.post("/arten", data={"label": "Dose", "prefix": "EUR"}).text
    assert "3 Buchstaben" in client.post("/arten", data={"label": "Dose", "prefix": "D1"}).text
    assert "gibt es schon" in client.post("/arten", data={"label": "eurobox", "prefix": "EBX"}).text
    client.post("/arten", data={"label": "Dose", "prefix": "DOS"})
    assert "DOS" in codes.PREFIX_KIND
    client.post("/arten/dose/delete")
    assert "DOS" not in codes.PREFIX_KIND and "dose" not in kinds.KIND_LABELS


def test_start_tiles_without_bottom_bar_duplicates(client: TestClient) -> None:
    tiles = client.get("/").text.split('class="tiles"')[1].split("</nav>")[0]
    assert "/scan" not in tiles and "/sprache" not in tiles and "/labels" not in tiles
    assert "/einkauf" in tiles
