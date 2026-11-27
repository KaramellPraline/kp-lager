"""2.1: Teile per API/MCP nach Katalog-Typ anlegen (wie der Hinzufügen-Tab), neue DIY-Typen
und die Kategorie Elektrowerkzeug (PWT)."""

import sys
from collections.abc import Iterator
from pathlib import Path
from typing import Any

import pytest
from fastapi.testclient import TestClient

from app import apikeys, catalog, codes, kinds, materials, repo, typesettings
from app.config import Settings
from app.db import connect
from app.web import create_app

sys.path.insert(0, str(Path(__file__).parents[1] / "tools"))
from lager_client import LagerClient  # noqa: E402

NEW_TYPES = (
    "nagel", "klammer", "anker", "holzverbinder", "moebelbeschlag", "seil",
    "installationsleitung", "hammer", "schluessel", "elektrowerkzeug", "messgeraet", "spannen",
    "arbeitshilfe", "platte", "leiste", "bauchemie", "dichtband", "malerbedarf", "sanitaer",
)  # fmt: skip


@pytest.fixture
def setup(tmp_path: Path) -> Iterator[tuple[TestClient, str, Settings]]:
    s = Settings(data_dir=tmp_path, base_url="https://lager.test")
    with TestClient(create_app(s)) as c:
        conn = connect(s.db_path)
        repo.create_container(conn, "Schrauben", "eurobox", code="EUR-001")
        repo.create_container(conn, "Werkzeug", "eurobox", code="EUR-002")
        key = apikeys.create(conn, "test")
        conn.close()
        yield c, key, s


def post(c: TestClient, key: str, **body: Any) -> dict[str, Any]:
    r = c.post("/api/v1/items/catalog", json=body, headers={"X-API-Key": key})
    assert r.status_code == 200, r.text
    data: dict[str, Any] = r.json()
    return data


def test_new_types_are_complete() -> None:
    for key in NEW_TYPES:
        t = catalog.BY_KEY[key]
        assert t.group in catalog.GROUPS and t.cat in codes.ITEM_PREFIXES, key
        assert catalog.name(t, {f.key: (f.options or ("x",))[0] for f in t.fields}), key
    assert all(any(t.group == g for t in catalog.TYPES) for g in catalog.GROUPS)
    assert len(catalog.TYPES) == len(catalog.BY_KEY)  # keine doppelten Schlüssel
    assert "PWT" in codes.ITEM_PREFIXES and "PWT" in repo.INDIVIDUAL
    assert materials.PREFIX_MATERIAL["PWT"] == "pwt"
    assert "PWT" in {p for p, _ in kinds.ITEM_CATS}


def test_catalog_list_has_form_details(setup: tuple[TestClient, str, Settings]) -> None:
    c, _, _ = setup
    types = {t["key"]: t for t in c.get("/api/v1/types/catalog").json()}
    m = types["mutter"]
    assert m["area"] == "Befestigung" and m["template"] == "{kind} {thread}"
    f = {x["key"]: x for x in m["fields"]}
    assert "M3" in f["thread"]["options"] and f["strength"]["extra"] is True
    assert types["elektrowerkzeug"]["single"] and types["elektrowerkzeug"]["category"] == "PWT"
    assert types["elektrowerkzeug"]["area"] == "Werkzeug & Messen"


def test_add_like_the_form(setup: tuple[TestClient, str, Settings]) -> None:
    c, key, s = setup
    res = post(c, key, type="mutter", container="EUR-001", qty=50,
               fields={"kind": "Sechskantmutter", "thread": "M3", "finish": "Edelstahl"})  # fmt: skip
    assert res["status"] == "created"
    item = res["created"][0]
    assert item["name"] == "Sechskantmutter M3" and item["qty"] == 50
    assert item["code"].startswith("CNS-") and "Schrauben" in res["container"]
    conn = connect(s.db_path)
    row = repo.get_item(conn, item["id"])
    assert row["ctype"] == "mutter" and catalog.values_of(row)["finish"] == "Edelstahl"
    # gibt es schon: nichts anlegen, melden
    again = post(c, key, type="mutter", container="EUR-001", qty=20,
                 fields={"kind": "Sechskantmutter", "thread": "M3", "finish": "Edelstahl"})  # fmt: skip
    assert again["status"] == "duplicate" and not again["created"]
    assert again["planned"][0]["duplicates"][0]["code"] == item["code"]
    added = post(c, key, type="mutter", container="EUR-001", qty=20, on_duplicate="add",
                 fields={"kind": "Sechskantmutter", "thread": "M3", "finish": "Edelstahl"})  # fmt: skip
    assert added["status"] == "updated" and added["updated"][0]["qty"] == 70
    conn.close()


def test_series_preview_required_and_errors(setup: tuple[TestClient, str, Settings]) -> None:
    c, key, s = setup
    prev = post(c, key, type="schraube", dry_run=True, series_field="length",
                series=["10", "12"], fields={"head": "Zylinderkopfschraube", "thread": "M3"})  # fmt: skip
    assert prev["status"] == "preview"
    assert [p["name"] for p in prev["planned"]] == [
        "Zylinderkopfschraube M3x10",
        "Zylinderkopfschraube M3x12",
    ]
    assert c.get("/api/v1/overview").json()["items"] == 0
    made = post(c, key, type="schraube", series_field="length", series=["10", "12"], qty=10,
                fields={"head": "Zylinderkopfschraube", "thread": "M3"}, price="0,05")  # fmt: skip
    assert len(made["created"]) == 2 and made["container"].endswith("Zu sortieren")
    conn = connect(s.db_path)
    typesettings.save_required(conn, "scheibe", ["thread"])
    conn.close()
    r = c.post("/api/v1/items/catalog", headers={"X-API-Key": key},
               json={"type": "scheibe", "fields": {"kind": "Unterlegscheibe"}})  # fmt: skip
    assert r.status_code == 400 and "Pflichtfeld" in r.text
    r = c.post("/api/v1/items/catalog", headers={"X-API-Key": key},
               json={"type": "mutter", "fields": {"gewinde": "M3"}})  # fmt: skip
    assert r.status_code == 400 and "Unbekannte Felder" in r.text
    r = c.post("/api/v1/items/catalog", headers={"X-API-Key": key}, json={"type": "gibtsnicht"})
    assert r.status_code == 400


def test_power_tool_single_pieces(setup: tuple[TestClient, str, Settings]) -> None:
    c, key, s = setup
    res = post(c, key, type="elektrowerkzeug", container="EUR-002", count=2,
               fields={"kind": "Akkuschrauber", "brand": "Bosch", "model": "GSR 18V-55",
                       "power": "Akku", "volt": "18", "system": "Bosch 18V (PBA / ProCORE)",
                       "serial": "123"})  # fmt: skip
    codes_ = [i["code"] for i in res["created"]]
    assert len(set(codes_)) == 2 and all(x.startswith("PWT-") for x in codes_)
    assert res["created"][0]["name"] == "Akkuschrauber Bosch GSR 18V-55"
    conn = connect(s.db_path)
    row = repo.get_item(conn, res["created"][0]["id"])
    spec = materials.specs(row)
    assert row["material"] == "pwt" and spec["system"].startswith("Bosch") and spec["volt"] == "18"
    conn.close()


def test_mcp_add_item_by_type(
    setup: tuple[TestClient, str, Settings], monkeypatch: pytest.MonkeyPatch
) -> None:
    c, key, _ = setup
    import lager_mcp

    monkeypatch.setattr(lager_mcp, "_client", LagerClient("http://testserver", key, c))
    schema = lager_mcp.get_schema()
    areas = {a["area"]: a for a in schema["catalog"]}
    assert "Befestigung" in areas and schema["categories"]
    assert lager_mcp.get_schema("scheibe")["fields"][0]["key"] == "kind"
    got = lager_mcp.add_item(container="EUR-001", typ="Scheibe", qty=100,
                             fields={"kind": "Unterlegscheibe", "thread": "M4"})  # fmt: skip
    assert isinstance(got, dict) and got["created"][0]["name"].startswith("Unterlegscheibe M4")
    with pytest.raises(ValueError, match="Unbekannter Typ"):
        lager_mcp.get_schema("xyz")
