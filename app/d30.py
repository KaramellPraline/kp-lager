"""D30-Direktdruck per Bluetooth LE (der Server-PC braucht Bluetooth; Paket `bleak`).

Protokoll (Phomemo, Service FF00 / Schreib-Characteristic FF02) nach polskafan/phomemo_d30.
`status()` meldet, ob der Drucker gerade erreichbar ist (kurzer Scan, 20 s zwischengespeichert).
"""

import asyncio
import os
import sqlite3
import threading
import time

from PIL import Image

from app import labelimg, labels, printmq
from app.repo import LagerError

WRITE = "0000ff02-0000-1000-8000-00805f9b34fb"
INIT = ["1f1138", "1f11121f1113", "1f1109", "1f1111", "1f1119", "1f1107", "1f110a1f110202"]
STATUS_TTL = 20.0
MAX_LABELS = 30

_lock = threading.Lock()
_cache: tuple[float, bool, str] = (0.0, False, "")


def _is_d30(device: object, _adv: object) -> bool:
    name = getattr(device, "name", None)
    return bool(name) and "D30" in str(name).upper()


async def _scan(timeout: float) -> bool:
    from bleak import BleakScanner

    return await BleakScanner.find_device_by_filter(_is_d30, timeout) is not None


def status(force: bool = False) -> tuple[bool, str]:
    """(erreichbar, Hinweis)."""
    global _cache
    if printmq.configured():  # Druck läuft über den MQTT-Druck-Agenten auf dem PC
        return printmq.agent_status()
    if _lock.locked():
        return True, "druckt gerade"
    at, ok, msg = _cache
    if not force and time.monotonic() - at < STATUS_TTL:
        return ok, msg
    try:
        ok, msg = asyncio.run(_scan(4.0)), ""
        if not ok:
            msg = "D30 nicht gefunden – einschalten, Handy-App schließen"
    except ImportError:
        ok, msg = False, "Paket bleak fehlt"
    except Exception as exc:  # Bluetooth aus / kein Adapter
        ok, msg = False, f"Bluetooth: {exc}"[:120]
    _cache = (time.monotonic(), ok, msg)
    return ok, msg


async def _send(images: list[Image.Image]) -> None:
    from bleak import BleakClient, BleakScanner

    dev = await BleakScanner.find_device_by_filter(_is_d30, 8.0)
    if dev is None:
        raise LagerError("D30 nicht gefunden – einschalten und Handy-App schließen")
    async with BleakClient(dev, timeout=15) as client:
        for img in images:
            for packet in INIT:
                await client.write_gatt_char(WRITE, bytes.fromhex(packet), response=False)
                await asyncio.sleep(0.05)
            data = labelimg.d30_bytes(img)
            for i in range(0, len(data), 100):
                await client.write_gatt_char(WRITE, data[i : i + 100], response=False)
                await asyncio.sleep(0.03)
            await asyncio.sleep(2.5)  # Drucker braucht Zeit je Etikett


def spp_port() -> str | None:
    """Bluetooth-Seriell-Port (COMx) des gekoppelten D30, falls Windows ihn anlegt.

    LAGER_D30_PORT erzwingt einen Port. Sonst: der ausgehende Bluetooth-Port (Adresse ≠ 0);
    gibt es mehrere, entscheidet LAGER_D30_ADDR (z. B. E2B733D33FE0)."""
    if forced := os.environ.get("LAGER_D30_PORT", ""):
        return forced
    try:
        from serial.tools import list_ports  # type: ignore[import-untyped]
    except ImportError:
        return None
    ports = [
        (p.device, p.hwid or "")
        for p in list_ports.comports()
        if "BTHENUM" in (p.hwid or "") and "000000000000" not in (p.hwid or "")
    ]
    addr = os.environ.get("LAGER_D30_ADDR", "").replace(":", "").upper()
    if addr:
        ports = [x for x in ports if addr in x[1].upper()]
    return ports[0][0] if len(ports) == 1 else None


def _via_serial(port: str, images: list[Image.Image]) -> None:
    import serial  # type: ignore[import-untyped]

    with serial.Serial(port, 115200, timeout=3, write_timeout=15) as ser:
        for img in images:
            for packet in INIT:
                ser.write(bytes.fromhex(packet))
                ser.flush()
                time.sleep(0.05)
            data = labelimg.d30_bytes(img)
            for i in range(0, len(data), 512):
                ser.write(data[i : i + 512])
                ser.flush()
            time.sleep(2.5)  # Drucker braucht Zeit je Etikett


def _transmit(images: list[Image.Image]) -> None:
    """Zuerst Bluetooth-Seriell (COM, braucht keinen Scan), bei Fehler Bluetooth LE."""
    port = spp_port()
    if port:
        try:
            _via_serial(port, images)
            return
        except Exception:  # Port weg, Drucker aus/außer Reichweite → LE versuchen
            pass
    asyncio.run(_send(images))


def send(images: list[Image.Image]) -> None:
    """Bilder (320×96) nacheinander drucken; immer nur ein Druckauftrag gleichzeitig."""
    global _cache
    if printmq.configured():
        printmq.submit(images)
        return
    if not _lock.acquire(blocking=False):
        raise LagerError("Der D30 druckt gerade – gleich nochmal versuchen")
    try:
        _transmit(images)
        _cache = (time.monotonic(), True, "")
    except LagerError:
        raise
    except ImportError as exc:
        raise LagerError("Paket bleak fehlt (uv add bleak)") from exc
    except Exception as exc:
        _cache = (0.0, False, "")
        raise LagerError(f"Druck fehlgeschlagen: {exc}"[:160]) from exc
    finally:
        _lock.release()


def print_labels(rows: list[labels.Label]) -> int:
    """Etiketten (nach Code-Text, noch ohne Buchführung) drucken."""
    if not rows:
        raise LagerError("Kein Etikett zum Drucken")
    if len(rows) > MAX_LABELS:
        raise LagerError(f"Höchstens {MAX_LABELS} Etiketten auf einmal")
    send([labelimg.render(r) for r in rows])
    return len(rows)


def print_codes(conn: sqlite3.Connection, base_url: str, codes_: list[str]) -> int:
    """Etiketten dieser Codes drucken, als gedruckt markieren und aus der Warteschlange nehmen."""
    rows = []
    for code in dict.fromkeys(codes_):
        if label := labels.find(conn, base_url, code):
            rows.append(label)
    print_labels(rows)
    done = [(r.code,) for r in rows]
    with conn:
        conn.executemany("UPDATE container SET label_printed = 1 WHERE code = ?", done)
        conn.executemany("UPDATE item SET label_printed = 1 WHERE code = ?", done)
    labels.dequeue(conn, [r.code for r in rows])
    return len(rows)
