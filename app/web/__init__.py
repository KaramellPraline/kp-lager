"""HTTP-Oberfläche (Jinja2 + HTMX).

- `app.py`: App-Fabrik `create_app` (Mounts, API, Fehlerbehandlung, Middleware)
- `shared.py`: Templates, `redirect`, Cookies, Formular-Hilfen, Kontext `Ctx`
- `routes/`: Routen je Bereich der Navigation (Bestand, Teile, Sortiment, Hinzufügen, Katalog,
  Scan, Drucken, Drucken A4, Einkauf, Werkstatt, System)
"""

from app.web.app import create_app
from app.web.shared import APP_DIR, APP_NAME, redirect, templates

__all__ = ["APP_DIR", "APP_NAME", "create_app", "redirect", "templates"]
