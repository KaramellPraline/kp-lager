import io
import re

import httpx
from fastapi.testclient import TestClient
from openpyxl import load_workbook

from app import prefs


def node_of(r: httpx.Response) -> str:
    return str(r.url.path).rsplit("/", 1)[1]


def save(client: TestClient, **changes: str) -> None:
    """Einstellungsseite mit aktuellen Werten + Änderungen absenden (wie im Browser)."""
    page = client.get("/settings").text
    form: dict[str, str] = {}
    for p in prefs.PREFS:
        if p.kind == "bool":
            if re.search(rf'name="{p.key}" value="1" checked', page):
                form[p.key] = "1"
        elif p.kind == "textarea":
            form[p.key] = re.search(rf'name="{p.key}"[^>]*>([^<]*)<', page).group(1)  # type: ignore[union-attr]
        elif p.kind == "choice":
            m = re.search(rf'name="{p.key}">(.*?)</select>', page, re.S)
            sel = re.search(r'value="([^"]*)" selected', m.group(1)) if m else None
            form[p.key] = sel.group(1) if sel else p.default
        else:
            form[p.key] = re.search(rf'name="{p.key}" value="([^"]*)"', page).group(1)  # type: ignore[union-attr]
    for k, v in changes.items():
        if v == "":
            form.pop(k, None)
        else:
            form[k] = v
    assert "gespeichert" in client.post("/settings", data=form).text


def test_settings_page_lists_all_groups(client: TestClient) -> None:
    page = client.get("/settings").text
    for group in prefs.groups():
        assert f">{group}</h2>" in page
    assert "Zertifikat laden" in page and "Backup jetzt erstellen" in page


def test_name_theme_compact(client: TestClient) -> None:
    save(client, app_name="Werkstatt", theme="dark", compact="1")
    page = client.get("/").text
    assert 'data-theme="dark"' in page and 'class="compact"' in page and ">Werkstatt</a>" in page
    assert client.get("/manifest.webmanifest").json()["name"] == "Werkstatt"
    save(client, app_name="  ")
    assert ">KP Lager</a>" in client.get("/").text  # leer -> Standard


def test_quick_parse_off_and_default_unit(client: TestClient) -> None:
    box = node_of(client.post("/containers", data={"name": "Box", "kind": "kiste"}))
    save(client, default_unit="Stk")
    r = client.post(f"/n/{box}/items", data={"name": "Kabel", "qty": "4"})
    assert "4 Stk" in r.text
    save(client, quick_parse="")
    r = client.post(f"/n/{box}/items", data={"name": "3 Rollen Lötzinn"})
    assert "„3 Rollen Lötzinn“ eingelagert" in r.text


def test_label_text_max_and_typo_toggle(client: TestClient) -> None:
    save(client, label_text_max="10")
    fields = {"code": ["ART-0001"], "text": ["Akkuschrauber Makita"], "extra": [""], "fmt": "xlsx"}
    ws = load_workbook(io.BytesIO(client.post("/labels/export", data=fields).content)).active
    assert ws is not None and ws["C2"].value == "Akkuschra…"
    box = node_of(client.post("/containers", data={"name": "Box", "kind": "kiste"}))
    client.post(f"/n/{box}/items", data={"name": "Holzschrauben"})
    assert "Ergebnisse für" in client.get("/suche", params={"q": "holzschrabuen"}).text
    save(client, typo_correction="")
    assert "Nichts gefunden" in client.get("/suche", params={"q": "holzschrabuen"}).text


def test_invalid_values_fall_back(client: TestClient) -> None:
    save(client, label_text_max="abc", theme="neon", home_recent="999")
    page = client.get("/settings").text
    assert 'name="label_text_max" value="24"' in page and 'name="home_recent" value="20"' in page
    assert 'data-theme="auto"' in page


def test_backup_and_more_page(client: TestClient) -> None:
    r = client.post("/settings/backup")
    assert "Backup: lager-" in r.text
    assert "Einkaufsliste" in client.get("/mehr").text
