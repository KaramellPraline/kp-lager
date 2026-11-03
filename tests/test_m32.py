"""M32: mehr Stecker für Kabel (Netz, Drehstrom, Power Delivery, Gleichstrom)."""

from app import cables


def test_netz_und_drehstrom() -> None:
    assert cables.plug("Eurostecker") == "Euro-Stecker"
    assert cables.plug("Drehstrom") == "CEE 16A 5p"
    assert cables.plug("CEE 32") == "CEE 32A 5p"
    assert cables.plug("cee blau") == "CEE 16A 3p"
    assert cables.plug("c14") == "C14"
    assert cables.plug("Perilex") == "Perilex"


def test_power_delivery_und_dc() -> None:
    assert cables.plug("USB PD") == "USB-C PD"
    assert cables.plug("power delivery") == "USB-C PD"
    assert cables.plug("XT60") == "XT60"
    assert cables.plug("dc 5.5x2.1") == "DC 5,5x2,1"


def test_parse_netzkabel() -> None:
    assert cables.parse("Euro-Stecker - C7 1,5m") == {
        "length": "1.5",
        "plug_a": "Euro-Stecker",
        "plug_b": "C7",
    }
    assert cables.parse("C5 2m")["plug_a"] == "Schuko"
    assert cables.parse("CEE 16A 5p - Schuko 5m") == {
        "length": "5",
        "plug_a": "CEE 16A 5p",
        "plug_b": "Schuko",
    }
    assert cables.name({"plug_a": "USB-C PD", "plug_b": "USB-C PD", "length": "1"}).endswith("1m")


def test_auswahl_ist_vollstaendig(client) -> None:  # type: ignore[no-untyped-def]
    page = client.get("/neu/material").text
    for p in ("Euro-Stecker", "CEE 16A 5p", "USB-C PD", "XT60", "C20", "Perilex"):
        assert f"<option>{p}</option>" in page
    assert len(set(cables.COMMON)) == len(cables.COMMON)
