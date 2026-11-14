"""Routen der Oberfläche, je Bereich der Navigation ein Modul mit `register(app, ctx)`.

Reihenfolge = Reihenfolge der Registrierung (bei gleichen Pfaden gewinnt die erste Route).
"""

from app.web.routes import (
    bestand,
    drucken,
    drucken_a4,
    einkauf,
    hinzufuegen,
    katalog,
    scan,
    sortiment,
    system,
    teile,
    werkstatt,
)

ROUTES = (
    system,
    bestand,
    teile,
    sortiment,
    hinzufuegen,
    katalog,
    scan,
    drucken,
    drucken_a4,
    einkauf,
    werkstatt,
)
