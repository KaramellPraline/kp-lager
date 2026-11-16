"""Routen der Oberfläche, je Bereich der Navigation ein Modul mit `register(app, ctx)`.

Reihenfolge = Reihenfolge der Registrierung (bei gleichen Pfaden gewinnt die erste Route).
"""

from app.web.routes import (
    anbindungen,
    bestand,
    drucken,
    drucken_a4,
    einkauf,
    hinzufuegen,
    katalog,
    konto,
    scan,
    sortiment,
    system,
    teile,
    werkstatt,
)

ROUTES = (
    system,
    anbindungen,
    konto,
    bestand,
    teile,
    sortiment,
    hinzufuegen,
    katalog,
    konto,
    scan,
    drucken,
    drucken_a4,
    einkauf,
    werkstatt,
)
