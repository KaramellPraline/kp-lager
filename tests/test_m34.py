"""M34: API/CLI/MCP kennen Kategorien, Felder und Arten immer live (neue Kategorien automatisch)."""

import sys
from collections.abc import Iterator
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from app import apikeys, codes, kinds, repo
from app.config import Settings
from app.db import connect
from app.web import create_app

sys.path.insert(0, str(Path(__file__).parents[1] / "tools"))
import lager_cli  # noqa: E402
from lager_client import LagerClient, LagerError  # noqa: E402


@pytest.fixture
def setup(tmp_path: Path) -> Iterator[tuple[TestClient, str]]:
    s = Settings(data_dir=tmp_path, base_url="https://lager.test")
    with TestClient(create_app(s)) as c:
        conn = connect(s.db_path)
        repo.create_container(conn, "Kabelbox", "eurobox", code="EUR-001")
        repo.create_container(conn, "Ziel", "eurobox", code="EUR-002")
        key = apikeys.create(conn, "test")
        conn.close()
        yield c, key


def test_schema_lists_every_category_and_kind(setup: tuple[TestClient, str]) -> None:
    c, _ = setup
    data = c.get("/api/v1/schema").json()
    assert {x["prefix"] for x in data["categories"]} == {p for p, _ in kinds.ITEM_CATS}
    assert set(codes.ITEM_PREFIXES) >= {x["prefix"] for x in data["categories"]}
    cbl = next(x for x in data["categories"] if x["prefix"] == "CBL")
    assert cbl["single_piece"] and {f["key"] for f in cbl["fields"]} >= {
        "plug_a",
        "plug_b",
        "length",
    }
    assert {k["key"] for k in data["container_kinds"]} >= {"eurobox", "box", "shelf"}
    assert "move" in data["bulk_actions"] and "600x400x170" in data["eurobox_dims_mm"]


def test_new_container_kind_appears_without_code_change(setup: tuple[TestClient, str]) -> None:
    c, _ = setup
    c.post("/quickadd", data={"mode": "container", "text": "Fach A", "kind": "neu",
                              "new_kind": "Schublade", "new_prefix": "SCH"})  # fmt: skip
    kinds_ = {k["prefix"] for k in c.get("/api/v1/schema").json()["container_kinds"]}
    assert "SCH" in kinds_


def test_typed_add_via_client_and_cli(
    setup: tuple[TestClient, str], capsys: pytest.CaptureFixture[str]
) -> None:
    c, key = setup
    w = LagerClient(url="http://testserver", api_key=key, http=c)
    items = w.add_typed("EUR-001", "", "CBL", count=2,
                        specs={"plug_a": "USB-A", "plug_b": "USB-C", "length": "1"})  # fmt: skip
    assert [i["name"] for i in items] == ["USB-A – USB-C 1m"] * 2
    assert len({i["code"] for i in items}) == 2 and all(i["qty"] is None for i in items)
    assert lager_cli.main(["schema"], w) == 0
    out = capsys.readouterr().out
    assert "CBL" in out and "[Einzelstück]" in out and "Aktionen:" in out
    assert lager_cli.main(["teil-neu", "EUR-001", "XXX", "Test"], w) == 1
    assert "Unbekannte Kategorie" in capsys.readouterr().err
    assert lager_cli.main(["teil-neu", "EUR-001", "FIL", "PLA schwarz", "--menge", "2"], w) == 0
    refs = ",".join(f"i{i['id']}" for i in items)
    assert lager_cli.main(["massen", "move", refs, "--ziel", "EUR-002"], w) == 0
    assert "2 verschoben" in capsys.readouterr().out
    assert lager_cli.main(["einkauf"], w) == 0
    assert lager_cli.main(["wert", "EUR-002"], w) == 0
    assert lager_cli.main(["trockner"], w) == 0
    assert "Programme" in capsys.readouterr().out
    r = LagerClient(url="http://testserver", api_key="", http=c)
    with pytest.raises(LagerError):
        r.add_typed("EUR-001", "x")


def test_mcp_tools_follow_schema(
    setup: tuple[TestClient, str], monkeypatch: pytest.MonkeyPatch
) -> None:
    c, key = setup
    import lager_mcp

    monkeypatch.setattr(lager_mcp, "_client", LagerClient("http://testserver", key, c))
    helptext = lager_mcp.categories_help()
    assert all(f"{p}=" in helptext for p, _ in kinds.ITEM_CATS)
    got = lager_mcp.add_item("EUR-001", "", "psu", count=2, specs={"volt": "12", "amp": "2"})
    assert len(got) == 2 and got[0]["name"].startswith(("Netzteil", "NT"))
    with pytest.raises(ValueError, match="Unbekannte Kategorie"):
        lager_mcp.add_item("EUR-001", "x", "QQQ")
    assert lager_mcp.get_schema()["categories"]
    assert lager_mcp.bulk_edit([f"i{got[0]['id']}"], "min", "3") == "1 Teile geändert"
    assert "total_eur" in lager_mcp.shopping_list()


def test_import_spreads_single_pieces(setup: tuple[TestClient, str]) -> None:
    c, key = setup
    w = LagerClient(url="http://testserver", api_key=key, http=c)
    payload = (
        '[{"code":"EUR-001","name":"Kabelbox","items":[{"name":"USB-A auf USB-C 1m","cat":"CBL",'
        '"qty":3},{"name":"NYM-J 3x1,5","cat":"CBL","qty":10,"unit":"m"}]}]'
    )
    assert not w.import_json(payload)["errors"]
    box = c.get("/api/v1/containers/EUR-001").json()["items"]
    usb = [i for i in box if i["name"].startswith("USB-A")]
    assert len(usb) == 3 and len({i["code"] for i in usb}) == 3
    nym = next(i for i in box if i["name"].startswith("NYM"))
    assert nym["qty"] == 10
    queue = c.get("/labels").text
    assert all(i["code"] in queue for i in usb)
