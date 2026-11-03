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
    page = client.get("/codes").text
    assert "SCH</b>-001 · Schublade" in page
    assert "art=schublade" in client.get("/neu/behaelter").text
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


def test_start_without_tiles(client: TestClient) -> None:
    assert 'class="tiles"' not in client.get("/").text  # Einkauf/Plätze in der unteren Leiste


def test_new_schema_groups_and_language(client: TestClient) -> None:
    page = client.get("/codes").text
    for p in (
        "WBA",
        "WAL",
        "DRW",
        "TBX",
        "MCF",
        "MOD",
        "BOX",
        "BIN",
        "CNS",
        "RAW",
        "CBL",
        "CMP",
        "PPE",
    ):
        assert f"<b>{p}</b>-001" in page
    assert "<b>STA</b>" not in page and "<b>EIN</b>" not in page
    assert "Verbrauch &amp; Rohmaterial" in page and "Werkzeugbox, z. B. Kistenberg Pro" in page
    assert "<b>TBX</b>" not in client.get("/labels").text
    start = client.get("/neu/behaelter").text
    assert (
        'Werkzeugbox <span class="meta">TBX</span>' in start and "Kistenberg" not in start
    )  # Beschreibung nicht in der Auswahl
    assert all("/" not in k.de and "/" not in k.en for k in kinds.BUILTIN)
    r = client.post("/lang", data={"lang": "en", "back": "/codes"})
    assert "Consumables &amp; Materials" in r.text and "Safety glasses" in r.text
    assert "Machine Case" in client.get("/neu/behaelter").text
    assert 'value="en" class="active"' in client.get("/mehr").text
    assert client.post("/lang", data={"lang": "de", "back": "//evil"}).url.path == "/mehr"


def test_custom_kind_description_only_on_codes_page(client: TestClient) -> None:
    assert (
        "Schrägstrich" in client.post("/arten", data={"label": "Dose/Glas", "prefix": "DOS"}).text
    )
    client.post(
        "/arten", data={"label": "Dose", "prefix": "DOS", "description": "Blechdose im Regal"}
    )
    assert "Blechdose im Regal" in client.get("/codes").text
    assert "Blechdose" not in client.get("/").text


def test_types_lowercase_and_old_kind_keys(client: TestClient) -> None:
    client.post("/quickadd", data={"mode": "type", "text": "Makita"})
    assert "makita" in client.get("/typen").text and ">Makita<" not in client.get("/typen").text
    assert kinds.resolve("sortierkasten") == "sortingbox" and kinds.resolve("TBX") == "toolbox"
    assert kinds.resolve("Werkbank") == "workbench" and kinds.resolve("quatsch") is None
