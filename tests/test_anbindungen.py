"""Einstellungen in Reitern und der Reiter „Anbindungen“ (API, MCP, Home Assistant, Druck,
Backup extern): Status, Speichern, Geheimnisse nie anzeigen, Umgebung hat Vorrang, Testen."""

import json
import socket
import threading
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from app import codes, importer, printmq
from app.config import Settings
from app.db import connect
from app.web import create_app

TABS = ("/settings", "/settings/bedienung", "/settings/anbindungen", "/settings/benutzer",
        "/settings/system")  # fmt: skip


def db(client: TestClient):  # type: ignore[no-untyped-def]
    return connect(client.app.state.settings.db_path)  # type: ignore[attr-defined]


def test_tabs_and_old_urls(client: TestClient) -> None:
    for url in TABS:
        page = client.get(url).text
        assert f'href="{url}" class="active"' in page, url
        for label in ("Allgemein", "Bedienung", "Anbindungen", "Benutzer", "System"):
            assert f">{label}</a>" in page
    r = client.get("/settings/admin?msg=Hallo")
    assert r.url.path == "/settings/system" and "Hallo" in r.text  # alte Adresse leitet weiter
    assert 'id="nummern"' in r.text and 'id="nodetypen"' in r.text and 'id="daten"' in r.text


def test_tab_save_only_touches_its_fields(client: TestClient) -> None:
    client.post("/settings", data={"_tab": "bedienung", "default_unit": "Stk"})
    conn = db(client)
    assert codes.get_setting(conn, "default_unit", "") == "Stk"
    assert codes.get_setting(conn, "auto_item_code", "") == "0"  # Checkbox fehlte = aus
    assert codes.get_setting(conn, "api_write_key", "1") == "1"  # anderer Reiter: unverändert
    assert codes.get_setting(conn, "home_rooms", "1") == "1"
    r = client.post("/settings", data={"_tab": "allgemein", "app_name": "Werkstatt"})
    assert r.url.path == "/settings" and ">Werkstatt</a>" in r.text


def test_cards_show_status(client: TestClient) -> None:
    page = client.get("/settings/anbindungen").text
    for anchor in ("api", "mcp", "ha", "druck", "backup"):
        assert f'id="{anchor}"' in page
    assert "https://lager.test/api/v1/ha" in page  # echte Adresse im YAML
    assert '"LAGER_URL": "https://lager.test"' in page.replace("&#34;", '"')
    assert "A4 nicht eingerichtet" in page and "MQTT nicht eingerichtet" in page
    assert "Backup extern" in page and "nicht eingerichtet" in page


def test_api_options_card(client: TestClient) -> None:
    client.post("/settings/anbindungen/api", data={"api_read_key": "1"})
    conn = db(client)
    assert codes.get_setting(conn, "api_read_key", "") == "1"
    assert codes.get_setting(conn, "api_write_key", "") == "0"
    assert "Schreiben ohne Schlüssel offen" in client.get("/settings/anbindungen").text
    assert client.get("/api/v1/overview").status_code == 401
    page = client.post("/settings/anbindungen/keys", data={"name": "HA", "scope": "read"}).text
    assert "kpl_" in page and "HA" in page


def test_mqtt_saved_password_never_shown(client: TestClient) -> None:
    r = client.post(
        "/settings/anbindungen/mqtt",
        data={"host": "192.168.1.10", "port": "1884", "user": "kp", "password": "SuperGeheim9",
              "topic": "druck/d30/"},
    )  # fmt: skip
    assert "MQTT-Druck gespeichert" in r.text and "SuperGeheim9" not in r.text
    page = client.get("/settings/anbindungen").text
    assert "SuperGeheim9" not in page and "gesetzt – leer lassen" in page
    assert 'value="192.168.1.10"' in page and 'value="druck/d30"' in page
    conn = db(client)
    cfg = printmq.config(conn)
    assert cfg and (cfg.host, cfg.port, cfg.user, cfg.password, cfg.source) == (
        "192.168.1.10", 1884, "kp", "SuperGeheim9", "db")  # fmt: skip
    assert cfg.t("queue") == "druck/d30/queue"
    # Passwort bleibt bei leerem Feld, nie im JSON-Export
    client.post("/settings/anbindungen/mqtt", data={"host": "192.168.1.10", "port": "1884"})
    assert printmq.config(conn).password == "SuperGeheim9"  # type: ignore[union-attr]
    assert "SuperGeheim9" not in json.dumps(importer.export(conn))
    client.post("/settings/anbindungen/mqtt",
                data={"host": "192.168.1.10", "password_clear": "1"})  # fmt: skip
    assert printmq.config(conn).password == ""  # type: ignore[union-attr]
    r = client.post("/settings/anbindungen/mqtt", data={"host": "mqtt://x:1"},
                    headers={"referer": "/settings/anbindungen"})  # fmt: skip
    assert "ohne Schema" in r.text
    client.post("/settings/anbindungen/mqtt", data={"host": ""})
    assert printmq.config(conn) is None


def test_mqtt_env_wins(client: TestClient, monkeypatch: pytest.MonkeyPatch) -> None:
    client.post("/settings/anbindungen/mqtt", data={"host": "10.0.0.1"})
    monkeypatch.setenv("LAGER_PRINT_MQTT", "broker.lan:1885")
    monkeypatch.setenv("LAGER_PRINT_MQTT_PASSWORD", "EnvGeheim7")
    page = client.get("/settings/anbindungen").text
    assert "Per Umgebung gesetzt" in page and "broker.lan:1885" in page
    assert "EnvGeheim7" not in page and 'name="host"' not in page
    cfg = printmq.config(db(client))
    assert cfg and cfg.source == "env" and cfg.host == "broker.lan"
    r = client.post("/settings/anbindungen/mqtt", data={"host": "x"},
                    headers={"referer": "/settings/anbindungen"})  # fmt: skip
    assert "per Umgebung gesetzt" in r.text


def test_mqtt_test_button_reports_unreachable(client: TestClient) -> None:
    sock = socket.socket()
    sock.bind(("127.0.0.1", 0))
    port = sock.getsockname()[1]
    sock.close()  # Port frei: niemand hört zu
    client.post("/settings/anbindungen/mqtt", data={"host": "127.0.0.1", "port": str(port)})
    r = client.post("/settings/anbindungen/test/mqtt")
    assert "Test fehlgeschlagen: Broker nicht erreichbar" in r.text


def test_ipp_test_button(client: TestClient) -> None:
    srv = socket.socket()
    srv.bind(("127.0.0.1", 0))
    srv.listen(1)
    port = srv.getsockname()[1]
    threading.Thread(target=lambda: srv.accept()[0].close(), daemon=True).start()
    client.post("/settings/anbindungen/a4", data={"a4_printer": f"ipp://127.0.0.1:{port}/ipp"})
    page = client.get("/settings/anbindungen").text
    assert "A4 eingerichtet" in page
    assert "Test ok: Drucker erreichbar" in client.post("/settings/anbindungen/test/ipp").text
    srv.close()


def test_backup_target_and_test(client: TestClient, tmp_path: Path) -> None:
    target = tmp_path / "nas"
    r = client.post("/settings/anbindungen/test/backup")
    assert "Kein Zielordner" in r.text
    client.post("/settings/anbindungen/backup", data={"backup_extern": str(target)})
    assert "gibt es nicht" in client.post("/settings/anbindungen/test/backup").text
    target.mkdir()
    assert "ist beschreibbar" in client.post("/settings/anbindungen/test/backup").text
    assert not list(target.iterdir())  # Testdatei wieder weg
    assert str(target) in client.get("/settings/anbindungen").text


def test_bridge_switch_and_env_lock(tmp_path: Path) -> None:
    with TestClient(create_app(Settings(data_dir=tmp_path / "a", base_url="https://x.test"))) as c:
        assert c.get("/d30/status").json()["bridge"] is False
        c.post("/settings/anbindungen/bridge", data={"d30_bridge": "1"})
        assert c.get("/d30/status").json()["bridge"] is True
        c.post("/containers", data={"name": "Box", "kind": "kiste", "code": "KIS-001"})
        page = c.post("/d30/print", data={"code": "KIS-001", "back": "/labels"}).text
        assert 'data-d30-codes="KIS-001"' in page
    locked = Settings(data_dir=tmp_path / "b", base_url="https://x.test", d30_bridge_locked=True)
    with TestClient(create_app(locked)) as c:
        c.post("/settings/anbindungen/bridge", data={"d30_bridge": "1"},
               headers={"referer": "/settings/anbindungen"})  # fmt: skip
        assert c.get("/d30/status").json()["bridge"] is False
        assert "Per Umgebung gesetzt" in c.get("/settings/anbindungen").text
