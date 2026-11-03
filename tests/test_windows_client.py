"""Windows-Launcher: Konfiguration und Argumente (ohne Fenster/Bluetooth)."""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parents[1] / "windows" / "client"))
import kp_client as lc  # noqa: E402


def test_normalize_url() -> None:
    assert lc.normalize_url("lager.home.lan") == "https://lager.home.lan"
    assert lc.normalize_url(" http://192.168.1.5:8000/ ") == "http://192.168.1.5:8000"
    assert lc.normalize_url("  ") == ""


def test_config_roundtrip_and_precedence(tmp_path: Path) -> None:
    path = tmp_path / "x" / "config.json"
    assert lc.load_config(path) == {}
    lc.save_config({"server": "https://a.lan", "ca": "c.crt"}, path)
    cfg = lc.load_config(path)
    assert lc.resolve(lc.parse([]), cfg) == {"server": "https://a.lan", "ca": "c.crt"}
    args = lc.parse(["--server", "b.lan", "--ca", "z.crt"])
    assert lc.resolve(args, cfg) == {"server": "https://b.lan", "ca": "z.crt"}
    path.write_text("kaputt", encoding="utf-8")
    assert lc.load_config(path) == {}


def test_client_flags() -> None:
    a = lc.parse(["--bridge-only", "--port", "9000", "--no-bridge", "--reset"])
    assert a.bridge_only and a.no_bridge and a.reset and a.port == 9000
