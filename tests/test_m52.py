"""M52: Umlaute/ß (mitgelieferte Schrift) und frei gestaltbare A4-Etiketten aus Behältern."""

from pathlib import Path

from fastapi.testclient import TestClient
from PIL import ImageFont

from app import a4, labelimg
from app.db import connect


def box(client: TestClient, name: str = "Werkstatt-Regal") -> int:
    r = client.post("/containers", data={"name": name, "kind": "toolbox"}, follow_redirects=False)
    return int(r.headers["location"].rsplit("/", 1)[1].split("?")[0])


def test_bundled_font_has_umlauts_and_eszett() -> None:
    assert labelimg.BUNDLED_FONT.exists()  # im Docker-Image gibt es sonst keine Schrift
    font = ImageFont.truetype(str(labelimg.BUNDLED_FONT), 40)
    missing = font.getmask("").getbbox()  # Zeichen, das die Schrift nicht kennt
    for ch in "äöüÄÖÜß€°µ":
        assert font.getmask(ch).getbbox() != missing, ch
    assert labelimg._font(20).getmask("ß").getbbox() != missing  # genau diese Schrift wird gewählt


def test_special_characters_render_on_a4_and_d30() -> None:
    from app.labels import Label

    job = {
        "type": "layout",
        "w": 100,
        "h": 40,
        "cfg": [{"t": "Größe Äpfel Öl Übung ß", "w": 1, "a": "center", "c": "red"}],
    }
    img = a4.render(job)
    assert any(px != (255, 255, 255) for px in img.getdata())
    assert labelimg.render(Label("ART-1", "HTTPS://X/C/ART-1", "Größe ß", "Müsli")).size == (
        320,
        96,
    )


def test_a4_layout_from_container_takes_name_and_code(client: TestClient, tmp_path: Path) -> None:
    b = box(client)
    client.post(f"/n/{b}/code")
    client.post(f"/n/{b}/items", data={"name": "Fräser 3 mm"})
    page = client.get("/a4").text
    assert 'data-name="Werkstatt-Regal"' in page and 'id="a4-live"' in page and "Box-Label" in page
    form = {"container": str(b), "w": "100", "h": "60", "qrpos": "right", "frame": "round", "color": "red",
            "t_0": "{name}", "w_0": "3", "a_0": "center", "c_0": "red",
            "t_1": "{inhalt}", "w_1": "2", "a_1": "left", "c_1": "black",
            "t_2": "{code}", "w_2": "1", "a_2": "right", "c_2": "red"}  # fmt: skip
    assert client.get("/a4/layout.png", params=form).content[:4] == b"\x89PNG"
    r = client.post("/a4/add", data=form)
    assert "A4-Warteschlange (1)" in r.text
    job = a4.queue(connect(tmp_path / "lager.db"))[0]["job"]
    assert (
        job["type"] == "layout"
        and job["title"] == "Werkstatt-Regal"
        and job["code"].startswith("TBX-")
    )
    assert [c["t"] for c in job["cfg"]][:2] == ["Werkstatt-Regal", "Fräser 3 mm"]
    assert [c["c"] for c in job["cfg"]] == ["red", "black", "red"] and job["cfg"][1]["a"] == "left"
    assert job["qr"].endswith(job["code"]) and job["frame"] == "round" and job["qrpos"] == "right"
    img = a4.render(job)
    assert any(px[0] > 150 and px[1] < 80 for px in img.getdata())  # rot
    assert any(px[0] < 60 and px[1] < 60 and px[2] < 60 for px in img.getdata())  # schwarz


def test_a4_layout_without_text_is_rejected_and_free_text_works(client: TestClient) -> None:
    assert (
        "Behälter wählen oder Text"
        in client.post("/a4/add", data={"t_0": "{name}", "w": "100"}).text
    )
    r = client.post("/a4/add", data={"t_0": "Sägeblätter groß", "c_0": "red", "t_1": "Größe M", "w": "80", "h": "30",
                                     "qrpos": "none", "frame": "square"})  # fmt: skip
    assert "A4-Warteschlange (1)" in r.text and "Sägeblätter groß" in r.text
