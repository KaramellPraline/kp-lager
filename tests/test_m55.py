"""M55: CFS-NFC-Platte – Werte für SpoolID, Modell-Download, Android-Brücke."""

from pathlib import Path

from fastapi.testclient import TestClient

from app import cfs

ROOT = Path(__file__).parents[1]


def _filament(c: TestClient, **spec: str) -> int:
    r = c.post("/quickadd", data={"mode": "container", "text": "Regal", "kind": "box"})
    box = int(r.url.path.rsplit("/", 1)[1])
    c.post("/quickadd", data={"mode": "item", "cat": "FIL", "target": box, "text": "PLA weiß"})
    item_id = c.get(f"/api/v1/containers/{box}").json()["items"][0]["id"]
    c.post(
        f"/items/{item_id}/specs",
        data={"material": "fil", **{f"spec_{k}": v for k, v in spec.items()}},
    )
    return int(item_id)


def test_length_color_serial() -> None:
    assert cfs.length_m({"weight": "1000"}) == 335  # 1 kg PLA 1,75 mm ≈ 335 m
    assert cfs.length_m({"weight": "1000", "diameter": "2.85", "density": "1.24"}) == 126
    assert cfs.length_m({}) is None
    assert cfs.color_hex({"color_hex": "#ff8800"}) == "FF8800"
    assert cfs.color_hex({"color": "Weiß matt"}) == "FFFFFF"
    assert cfs.color_hex({"color": "Tannengrün-Blau"}) is None
    assert cfs.serial("FIL-007", 3) == "000007" and cfs.serial(None, 12) == "000012"


def test_cfs_page_and_json(client: TestClient) -> None:
    item_id = _filament(
        client, material="PLA", brand="eSun", color="Weiß", color_hex="#FFFFFF", weight="1000"
    )
    page = client.get(f"/items/{item_id}/cfs").text
    assert "CFS-NFC-Platte" in page and "SpoolID" in page and "#FFFFFF" in page
    assert "/static/cad/cfs-platte.stl" in page and "KPLager.openSpoolId" in page
    data = client.get(f"/items/{item_id}/cfs.json").json()
    assert data["material"] == "PLA" and data["weight_g"] == 1000 and data["length_m"] == 335
    assert data["color_hex"] == "FFFFFF" and data["serial"].isdigit()
    assert "Gewicht: 1000 g" in cfs.handoff_text(data)
    assert "Platte &amp; Tag vorbereiten" in client.get(f"/items/{item_id}").text


def test_cfs_only_for_filament(client: TestClient) -> None:
    r = client.post("/quickadd", data={"mode": "container", "text": "Kiste", "kind": "box"})
    box = int(r.url.path.rsplit("/", 1)[1])
    client.post("/quickadd", data={"mode": "item", "cat": "ART", "target": box, "text": "Schraube"})
    item_id = client.get(f"/api/v1/containers/{box}").json()["items"][0]["id"]
    assert "nur für Filament" in client.get(f"/items/{item_id}/cfs").text


def test_model_files_are_served(client: TestClient) -> None:
    stl = client.get(cfs.MODEL_STL)
    assert stl.status_code == 200 and len(stl.content) > 1000
    assert client.get(cfs.MODEL_STEP).status_code == 200


def test_android_bridge_and_manifest() -> None:
    java = (ROOT / "android/app/src/main/java/de/kplager/app/MainActivity.java").read_text(
        encoding="utf-8"
    )
    assert 'addJavascriptInterface(new Bridge(), "KPLager")' in java
    assert "openSpoolId" in java and f'"{cfs.SPOOLID_PACKAGE}"' in java
    manifest = (ROOT / "android/app/src/main/AndroidManifest.xml").read_text(encoding="utf-8")
    assert f'<package android:name="{cfs.SPOOLID_PACKAGE}"' in manifest
