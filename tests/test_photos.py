import io
from pathlib import Path

import pytest
from fastapi.testclient import TestClient
from PIL import Image

from app import photos
from app.repo import LagerError


def jpeg(width: int, height: int, orientation: int | None = None) -> bytes:
    img = Image.new("RGB", (width, height), "red")
    exif = img.getexif()
    if orientation:
        exif[0x0112] = orientation
    buf = io.BytesIO()
    img.save(buf, "JPEG", exif=exif)
    return buf.getvalue()


def test_save_resizes_rotates_and_thumbs(tmp_path: Path) -> None:
    name = photos.save(jpeg(4000, 2000, orientation=6), tmp_path)
    with Image.open(tmp_path / name) as full, Image.open(tmp_path / f"thumb_{name}") as thumb:
        assert full.size == (800, 1600)  # hochkant gedreht und verkleinert
        assert max(thumb.size) == 400
    photos.delete(name, tmp_path)
    assert list(tmp_path.iterdir()) == []


def test_rejects_non_images(tmp_path: Path) -> None:
    with pytest.raises(LagerError):
        photos.save(b"kein bild", tmp_path)


def test_upload_replaces_and_delete_removes(client: TestClient, tmp_path: Path) -> None:
    r = client.post("/containers", data={"name": "Box", "kind": "kiste"})
    box = r.url.path.rsplit("/", 1)[1]
    r = client.post(f"/n/{box}/photo", files={"photo": ("a.jpg", jpeg(100, 100), "image/jpeg")})
    assert "Foto gespeichert" in r.text and "/photos/thumb_" in r.text
    r = client.post(f"/n/{box}/photo", files={"photo": ("b.jpg", jpeg(100, 100), "image/jpeg")})
    assert len(list((tmp_path / "photos").iterdir())) == 2  # altes Foto entfernt
    src = r.text.split('src="/photos/')[1].split('"')[0]
    assert client.get(f"/photos/{src}").headers["content-type"] == "image/jpeg"

    client.post(f"/n/{box}/items", data={"name": "Teil"})
    item = client.get(f"/n/{box}").text.split('id="item-')[1].split('"')[0]
    client.post(f"/items/{item}/photo", files={"photo": ("c.jpg", jpeg(50, 50), "image/jpeg")})
    assert len(list((tmp_path / "photos").iterdir())) == 4
    client.post(f"/items/{item}/delete")
    client.post(f"/n/{box}/delete")
    assert list((tmp_path / "photos").iterdir()) == []


def test_upload_garbage_shows_message(client: TestClient) -> None:
    r = client.post("/containers", data={"name": "Box", "kind": "kiste"})
    box = r.url.path.rsplit("/", 1)[1]
    r = client.post(
        f"/n/{box}/photo",
        files={"photo": ("x.txt", b"hallo", "text/plain")},
        headers={"referer": f"/n/{box}"},
    )
    assert "kein lesbares Bild" in r.text
