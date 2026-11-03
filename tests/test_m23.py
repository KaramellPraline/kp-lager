from fastapi.testclient import TestClient

from app import codes, search


def _shelf(client: TestClient) -> int:
    r = client.post("/quickadd", data={"mode": "container", "text": "Regal", "kind": "shelf"})
    return int(r.url.path.rsplit("/", 1)[1])


def test_item_categories_on_start(client: TestClient) -> None:
    page = client.get("/neu/material").text
    for p in ("ART", "TOL", "FIL", "RES", "CNS", "RAW", "CBL", "CMP", "PPE"):
        assert f'name="cat" value="{p}"' in page
    assert "Projekt" not in page
    kind_page = client.get("/neu/behaelter").text
    assert "art=toolbox" in kind_page and "art=machine" in kind_page
    assert "art=compartment" not in kind_page and "art=bin" not in kind_page
    shelf = _shelf(client)
    client.post(
        "/quickadd", data={"mode": "item", "text": "5 m NYM-J Kabel", "target": shelf, "cat": "CBL"}
    )
    client.post(
        "/quickadd", data={"mode": "item", "text": "PLA weiß", "target": shelf, "cat": "fil"}
    )
    items = {i["code"]: i for i in client.get(f"/api/v1/containers/{shelf}").json()["items"]}
    # Kabel: Zahl vorne ist die Länge (Name + Eigenschaft), nicht die Menge
    assert items["CBL-001"]["qty"] is None and items["CBL-001"]["name"] == "NYM-J Kabel 5m"
    assert "Max. Volumenfluss" in client.get(f"/items/{items['FIL-001']['id']}").text
    assert codes.normalize("cbl1") == "CBL-001"


def test_all_mode_creates_location_or_item(client: TestClient) -> None:
    r = client.post(
        "/quickadd", data={"mode": "all", "text": "Werkbank links", "choice": "kind:workbench"}
    )
    assert "Werkbank links" in r.text and "Werkbank" in r.text
    shelf = _shelf(client)
    client.post(
        "/quickadd",
        data={"mode": "all", "text": "Schutzbrille", "choice": "item:PPE", "target": shelf},
    )
    items = client.get(f"/api/v1/containers/{shelf}").json()["items"]
    assert [i["code"] for i in items] == ["PPE-001"]
    assert (
        "Kategorie"
        in client.post("/quickadd", data={"mode": "all", "text": "x", "choice": ""}).text
    )


def test_search_typos_synonyms_translation(client: TestClient) -> None:
    shelf = _shelf(client)
    for text in ("Holzschraube 4x40", "Seitenschneider Knipex", "Lötzinn bleifrei"):
        client.post("/quickadd", data={"mode": "item", "text": text, "target": shelf, "cat": "ART"})
    found = lambda q: client.get("/suche", params={"q": q}).text  # noqa: E731
    assert "Holzschraube" in found("screw")  # Englisch -> Deutsch
    assert "Holzschraube" in found("schrauben")  # Plural
    assert "Seitenschneider" in found("side cutter")  # Mehrwort-Übersetzung
    page = found("seitenschnieder")  # Tippfehler
    assert "Seitenschneider" in page and "seitenschneider" in page
    assert "Lötzinn" in found("solder")
    api = client.get("/api/v1/search", params={"q": "scerw"}).json()
    assert api["items"] and api["corrected"] == "screw"
    assert "schraube" in search.expand("screw", {}) and "schraube" in search.stems("schrauben")


def test_tag_prefix_and_search_filter(client: TestClient) -> None:
    assert codes.normalize("typ1") == "TAG-001" and codes.normalize("tag-002") == "TAG-002"
    assert "<b>TAG</b>-001 · Tag" in client.get("/codes").text
    shelf = _shelf(client)
    for text in ("Akkuschrauber 18V", "Handkreissäge 18V", "Holzschraube 5x60"):
        client.post("/quickadd", data={"mode": "item", "text": text, "target": shelf, "cat": "ART"})
    items = {i["name"]: i["id"] for i in client.get(f"/api/v1/containers/{shelf}").json()["items"]}
    for name in ("Akkuschrauber 18V", "Handkreissäge 18V"):
        client.post(
            f"/items/{items[name]}/edit",
            data={"name": name, "type_id": "neu", "new_type": "Makita"},
        )
    tags = {t["name"]: t for t in client.get("/api/v1/types").json()}
    assert "makita" in tags and tags["makita"]["code"].startswith("TAG-")
    page = client.get("/suche", params={"q": "18v"}).text
    assert 'class="pick-scroll tag-filter"' in page and "makita" in page
    tag_id = client.get("/suche").text.split("&amp;tag=")[1].split('"')[0]
    only = client.get("/suche", params={"tag": tag_id}).text
    assert "Akkuschrauber" in only and "Handkreissäge" in only and "Holzschraube" not in only
    assert (
        "Akkuschrauber" not in client.get("/suche", params={"q": "kreissäge", "tag": tag_id}).text
    )
    api = client.get("/api/v1/search", params={"tag": "makita"}).json()
    assert sorted(i["name"] for i in api["items"]) == ["Akkuschrauber 18V", "Handkreissäge 18V"]
    assert client.get("/api/v1/search", params={"tag": "gibtsnicht"}).status_code == 404
    assert "/typen/" in client.get(f"/C/{tags['makita']['code'].replace('TAG', 'TYP')}").url.path


def test_tool_category(client: TestClient) -> None:
    shelf = _shelf(client)
    client.post(
        "/quickadd",
        data={"mode": "item", "text": "Akkuschrauber 18V", "target": shelf, "cat": "TOL"},
    )
    items = client.get(f"/api/v1/containers/{shelf}").json()["items"]
    assert items[0]["code"] == "TOL-001" and codes.normalize("tol1") == "TOL-001"
    assert "<b>TOL</b>-001 · Werkzeug" in client.get("/codes").text
    assert (
        "TOL-Codes sind für Teile"
        in client.post(f"/n/{shelf}/edit", data={"name": "Regal", "code": "TOL-002"}).text
    )
