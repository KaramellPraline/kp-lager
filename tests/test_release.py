"""Versionsnummer und Release-Werkzeug."""

import shutil
import sys
from datetime import date
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from app import __version__

sys.path.insert(0, str(Path(__file__).parents[1] / "tools"))
import release  # noqa: E402

ROOT = Path(__file__).parents[1]


def _copy(tmp: Path) -> Path:
    (tmp / "app").mkdir()
    for f in ("app/__init__.py", "pyproject.toml", "CHANGELOG.md"):
        shutil.copy(ROOT / f, tmp / f)
    return tmp


def test_versions_in_code_are_consistent() -> None:
    assert release.current() == release.pyproject_version() == __version__
    assert release.check(f"v{__version__}") == __version__
    assert release.notes(__version__)  # Changelog-Text für die aktuelle Version vorhanden


def test_version_visible_in_app(client: TestClient) -> None:
    assert client.get("/health").json() == {"status": "ok", "version": __version__}
    assert f"Version <b>{__version__}</b>" in client.get("/status").text
    assert client.get("/api/v1/overview").json()["version"] == __version__


def test_bump_updates_all_places(tmp_path: Path) -> None:
    root = _copy(tmp_path)
    release.bump("0.3.0", root, today=date(2026, 12, 1))
    assert release.current(root) == release.pyproject_version(root) == "0.3.0"
    log = (root / "CHANGELOG.md").read_text("utf-8")
    assert log.index("## [0.3.0] – 2026-12-01") < log.index("## [0.2.0]")
    with pytest.raises(SystemExit):  # leerer Changelog-Text darf nicht veröffentlicht werden
        release.notes("0.3.0", root)
    assert release.check("v0.3.0", root) == "0.3.0"
    with pytest.raises(SystemExit):
        release.check("v0.2.0", root)  # Tag passt nicht zur Version im Code


@pytest.mark.parametrize("bad", ["1.2", "v1.2.3", "0.1.0", "0.2.0", "x"])
def test_bump_rejects_bad_or_lower_versions(bad: str, tmp_path: Path) -> None:
    with pytest.raises(SystemExit):
        release.bump(bad, _copy(tmp_path))


def test_check_rejects_malformed_tags() -> None:
    for tag in ("0.2", "release-1", "v1.2.3.4"):
        with pytest.raises(SystemExit):
            release.check(tag)
