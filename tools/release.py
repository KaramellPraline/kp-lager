"""Release-Hilfe: Version prüfen, hochzählen, Release-Text aus CHANGELOG.md holen.

    uv run python tools/release.py show             # aktuelle Version
    uv run python tools/release.py bump 0.3.0       # Version setzen, Changelog-Kopf anlegen
    uv run python tools/release.py check v0.3.0     # Tag == Version? (läuft im Release-Workflow)
    uv run python tools/release.py notes 0.3.0      # Text dieses Abschnitts aus CHANGELOG.md

Danach: committen, `git tag v0.3.0`, `git push origin v0.3.0` – der Workflow veröffentlicht.
"""

import re
import sys
from datetime import date
from pathlib import Path

ROOT = Path(__file__).parents[1]
INIT = ROOT / "app" / "__init__.py"
PYPROJECT = ROOT / "pyproject.toml"
CHANGELOG = ROOT / "CHANGELOG.md"
SEMVER = re.compile(r"^\d+\.\d+\.\d+$")


def current(root: Path = ROOT) -> str:
    m = re.search(r'__version__ = "([^"]+)"', (root / "app" / "__init__.py").read_text("utf-8"))
    if not m:
        raise SystemExit("Keine __version__ in app/__init__.py")
    return m.group(1)


def pyproject_version(root: Path = ROOT) -> str:
    m = re.search(r'^version = "([^"]+)"', (root / "pyproject.toml").read_text("utf-8"), re.M)
    if not m:
        raise SystemExit("Keine version in pyproject.toml")
    return m.group(1)


def bump(new: str, root: Path = ROOT, today: date | None = None) -> None:
    if not SEMVER.match(new):
        raise SystemExit(f"„{new}“ ist keine Version der Form 1.2.3")
    old = current(root)
    if tuple(map(int, new.split("."))) <= tuple(map(int, old.split("."))):
        raise SystemExit(f"Neue Version {new} muss größer sein als {old}")
    init = root / "app" / "__init__.py"
    init.write_text(
        re.sub(r'__version__ = "[^"]+"', f'__version__ = "{new}"', init.read_text("utf-8")), "utf-8"
    )
    proj = root / "pyproject.toml"
    proj.write_text(
        re.sub(
            r'^version = "[^"]+"',
            f'version = "{new}"',
            proj.read_text("utf-8"),
            count=1,
            flags=re.M,
        ),
        "utf-8",
    )
    log = root / "CHANGELOG.md"
    text = log.read_text("utf-8") if log.exists() else "# Änderungen\n\n"
    stamp = (today or date.today()).isoformat()
    head = f"## [{new}] – {stamp}\n\n- \n\n"
    marker = "## ["
    i = text.find(marker)
    text = text[:i] + head + text[i:] if i >= 0 else text.rstrip("\n") + "\n\n" + head
    log.write_text(text, "utf-8")


def check(tag: str, root: Path = ROOT) -> str:
    version = tag.removeprefix("v")
    if not SEMVER.match(version):
        raise SystemExit(f"Tag „{tag}“ hat nicht die Form v1.2.3")
    if version != current(root) or version != pyproject_version(root):
        raise SystemExit(
            f"Tag {tag} passt nicht zur Version im Code "
            f"(app/__init__.py: {current(root)}, pyproject.toml: {pyproject_version(root)})"
        )
    return version


def notes(version: str, root: Path = ROOT) -> str:
    text = (root / "CHANGELOG.md").read_text("utf-8")
    m = re.search(rf"^## \[{re.escape(version)}\].*?\n(.*?)(?=^## \[|\Z)", text, re.M | re.S)
    body = m.group(1).strip() if m else ""
    if not body or body == "-":
        raise SystemExit(f"CHANGELOG.md hat keinen Text für {version}")
    return body


def main(argv: list[str]) -> int:
    cmd, *args = argv or ["show"]
    if cmd == "show":
        print(current())
    elif cmd == "bump" and args:
        bump(args[0])
        print(
            f"Version {args[0]} gesetzt. CHANGELOG.md ausfüllen, committen, Tag v{args[0]} pushen."
        )
    elif cmd == "check" and args:
        print(check(args[0]))
    elif cmd == "notes" and args:
        print(notes(args[0].removeprefix("v")))
    else:
        print(__doc__)
        return 2
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
