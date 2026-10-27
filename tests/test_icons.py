import re
from pathlib import Path

from app import icons

TEMPLATES = Path(__file__).parents[1] / "app" / "templates"


def test_every_icon_role_in_templates_exists() -> None:
    used = set()
    for path in TEMPLATES.glob("*.html"):
        used |= set(re.findall(r"icon\('([a-z]+\.[a-z-]+)'", path.read_text(encoding="utf-8")))
    assert used, "keine Icons gefunden"
    assert sorted(used - icons.ROLES.keys()) == []


def test_no_emoji_or_pictograms_in_ui() -> None:
    pictos = re.compile(r"[\U0001F300-\U0001FAFF☀-➿←-↑↓-⇿＋☰]")
    files = [*TEMPLATES.glob("*.html"), TEMPLATES.parent / "static" / "app.js"]
    hits = [f"{p.name}: {m}" for p in files for m in pictos.findall(p.read_text(encoding="utf-8"))]
    assert hits == []


def test_icon_markup_and_label() -> None:
    assert 'aria-hidden="true">home<' in icons.icon("nav.home")
    assert 'aria-label="Start"' in icons.icon("nav.home", label="Start")
