import io

from fastapi.testclient import TestClient
from PIL import Image


def _jpeg() -> bytes:
    buf = io.BytesIO()
    Image.new("RGB", (40, 30), (200, 30, 40)).save(buf, "JPEG")
    return buf.getvalue()


def test_start_form_matrix_and_labels(client: TestClient) -> None:
    page = client.get("/neu/material").text
    form = page.split('id="schnell"')[1].split("</form>")[0]
    assert 'class="cats-grid"' in form and "pick-scroll cats" not in form
    cats = form.split('aria-label="Kategorie"')[1].split("</div>")[0]
    assert cats.count('class="cat-tile"') == 10  # ART, TOL, FIL, RES, CNS, RAW, CBL, PSU, CMP, PPE
    assert 'enctype="multipart/form-data"' in page and 'name="photo"' in form
    assert 'capture="environment"' in form and "photo-trigger" in form
    for text in (
        "Was?",
        "Kategorie",
        "Wohin?",
        "Zu sortieren (später einräumen)",
    ):
        assert text in form


def test_add_items_with_photo_and_default_inbox(client: TestClient, tmp_path) -> None:  # type: ignore[no-untyped-def]
    r = client.post(
        "/quickadd",
        data={
            "mode": "item",
            "text": "Seitenschneider, Abisolierzange",
            "cat": "TOL",
            "target": "",
        },
        files={"photo": ("bild.jpg", _jpeg(), "image/jpeg")},
    )
    assert "Zu sortieren" in r.text
    inbox = client.get("/api/v1/containers").json()
    box = next(c for c in inbox if c["name"] == "Zu sortieren")
    items = client.get(f"/api/v1/containers/{box['id']}").json()["items"]
    assert sorted(i["code"] for i in items) == ["TOL-001", "TOL-002"]
    for i in items:
        page = client.get(f"/items/{i['id']}").text
        assert 'class="photo-thumb"' in page
    assert len(list((tmp_path / "photos").glob("*"))) >= 2
    # Behälter mit Foto, ohne Foto-Feld geht weiter
    r = client.post("/quickadd", data={"mode": "container", "text": "Kiste rot", "kind": "box"},
                    files={"photo": ("k.jpg", _jpeg(), "image/jpeg")})  # fmt: skip
    assert "photo-thumb" in r.text or "/photos/" in r.text
    r = client.post("/quickadd", data={"mode": "container", "text": "Kiste grün", "kind": "box"})
    assert "Kiste grün" in r.text


def test_comma_always_splits() -> None:
    from app import quick

    assert [n for _, _, n in quick.parse_many("Zange, Hammer; Feile")] == [
        "Zange",
        "Hammer",
        "Feile",
    ]
    assert [n for _, _, n in quick.parse_many("NYM-J 3x1,5")] == ["NYM-J 3x1,5"]
    assert [n for _, _, n in quick.parse_many("Schrauben und Muttern Set")] == [
        "Schrauben und Muttern Set"
    ]
