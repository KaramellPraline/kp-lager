"""M54: Kamera-Scanner scannt nur ein Quadrat und stellt per Tippen scharf."""

from fastapi.testclient import TestClient


def test_scan_page_has_square_crop_and_tap_focus(client: TestClient) -> None:
    page = client.get("/scan").text
    assert 'id="cam-box"' in page and 'class="cam-frame"' in page and 'id="cam-ring"' in page
    # nur das mittlere Quadrat des Kamerabilds wird erkannt (Ausschnitt = sichtbares Quadrat)
    assert "Math.min(vw, vh)" in page and "ctx.drawImage(video, (vw - side) / 2" in page
    assert "detector.detect(canvas)" in page and "jsQR(img.data, out, out" in page
    # Tippen aufs Bild setzt den Fokuspunkt (Koordinaten im vollen Kamerabild)
    assert (
        "pointsOfInterest" in page
        and "focusMode" in page
        and 'addEventListener("click", focusAt)' in page
    )
    assert "tippen = dorthin scharfstellen" in page


def test_scan_square_css(client: TestClient) -> None:
    css = client.get("/static/style.css").text
    assert ".cam-box" in css and "aspect-ratio: 1 / 1" in css and ".cam-ring" in css
