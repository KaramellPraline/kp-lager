from fastapi.testclient import TestClient

from app import importer, repo
from app.db import connect


def _seed(client: TestClient) -> None:
    def make(data: dict[str, object]) -> int:
        nid = int(client.post("/quickadd", data=data).url.path.rsplit("/", 1)[1])
        client.post(f"/n/{nid}/code")
        return nid

    room = make({"mode": "container", "text": "Werkstatt", "kind": "room"})
    bench = make(
        {"mode": "all", "text": "Werkbank links", "choice": "kind:workbench", "target": room}
    )
    client.post(
        "/quickadd", data={"mode": "item", "text": "Akkuschrauber", "target": bench, "cat": "ART"}
    )
    item = client.get(f"/api/v1/containers/{bench}").json()["items"][0]["id"]
    client.post(
        f"/items/{item}/edit",
        data={"name": "Akkuschrauber", "type_id": "neu", "new_type": "Makita"},
    )


def test_import_new_container_categories_tags_specs(client: TestClient, tmp_path) -> None:  # type: ignore[no-untyped-def]
    _seed(client)
    conn = connect(tmp_path / "lager.db")
    payload = """[
      {"code": null, "name": "Filamentbox", "kind": "toolbox", "parent": "WBA-001",
       "items": [{"name": "PETG schwarz", "cat": "FIL", "tag": "Prusament", "qty": 2, "unit": "Spulen",
                  "specs": {"material": "PETG", "nozzle_min": "240", "flow_max": "150", "bogus": "1"}},
                 {"name": "NYM-J 3x1,5", "cat": "cbl", "qty": 10, "unit": "m"},
                 {"name": "Schutzbrille", "cat": "PPE"},
                 {"name": "Lötzinn", "cat": "XYZ"}]},
      {"code": null, "name": "Werkbank links", "kind": "workbench", "parent": "RAU-001",
       "items": [{"name": "Bitset", "type": "Makita"}]}
    ]"""
    report = importer.run(conn, payload, commit=True, review=True)
    assert not report.errors, report.errors
    assert report.containers_created == ["TBX-001 Filamentbox"]  # Werkbank links wiederverwendet
    box = repo.get_container_by_code(conn, "TBX-001")
    assert box is not None and box["review"] == 1
    items = {i["name"]: i for i in repo.items_in(conn, box["id"])}
    assert items["PETG schwarz"]["code"] == "FIL-001" and items["PETG schwarz"]["material"] == "fil"
    specs = items["PETG schwarz"]["specs"]
    assert '"nozzle_min": "240"' in specs and "flow_max" not in specs and "bogus" not in specs
    assert items["NYM-J 3x1,5"]["code"] == "CBL-001" and items["Schutzbrille"]["code"] == "PPE-001"
    assert items["Lötzinn"]["code"].startswith("ART-")
    tags = {r["name"] for r in conn.execute("SELECT name FROM item_type")}
    assert "prusament" in tags
    bench = repo.get_container_by_code(conn, "WBA-001")
    assert bench is not None and any(
        i["name"] == "Bitset" for i in repo.items_in(conn, bench["id"])
    )
