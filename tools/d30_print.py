"""Etiketten per Bluetooth direkt auf den D30 drucken (PC mit Bluetooth, Paket `bleak`).

    uv run --with bleak python tools/d30_print.py CBL-025 [CBL-026 ...]
    uv run --with bleak python tools/d30_print.py --png etikett.png

Holt das Bild von /labels/img/<CODE>.png des Servers (Standard https://lager.home.lan).
"""

import argparse
import asyncio
import io
import ssl
import sys
import urllib.request
from pathlib import Path

from PIL import Image

sys.path.insert(0, str(Path(__file__).parents[1]))
from app import labelimg  # noqa: E402

WRITE = "0000ff02-0000-1000-8000-00805f9b34fb"
INIT = ["1f1138", "1f11121f1113", "1f1109", "1f1111", "1f1119", "1f1107", "1f110a1f110202"]


def fetch(url: str, code: str) -> Image.Image:
    ctx = ssl.create_default_context()
    ctx.check_hostname = False  # LAN mit eigener CA
    ctx.verify_mode = ssl.CERT_NONE
    with urllib.request.urlopen(f"{url}/labels/img/{code}.png", context=ctx, timeout=10) as r:
        return Image.open(io.BytesIO(r.read())).convert("1")


async def send(images: list[Image.Image]) -> None:
    from bleak import BleakClient, BleakScanner

    dev = await BleakScanner.find_device_by_filter(
        lambda d, _: bool(d.name) and "D30" in d.name.upper(), 10
    )
    if dev is None:
        sys.exit("D30 nicht gefunden (eingeschaltet? Bluetooth an?)")
    async with BleakClient(dev, timeout=15) as c:
        for img in images:
            for p in INIT:
                await c.write_gatt_char(WRITE, bytes.fromhex(p), response=False)
                await asyncio.sleep(0.05)
            data = labelimg.d30_bytes(img)
            for i in range(0, len(data), 100):
                await c.write_gatt_char(WRITE, data[i : i + 100], response=False)
                await asyncio.sleep(0.03)
            await asyncio.sleep(2.5)  # Drucker braucht Zeit je Etikett
    print(f"{len(images)} Etikett(en) gesendet")


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("codes", nargs="*")
    ap.add_argument("--png", help="fertiges Bild 320×96 statt Server")
    ap.add_argument("--url", default="https://lager.home.lan")
    a = ap.parse_args()
    if a.png:
        images = [Image.open(a.png).convert("1")]
    elif a.codes:
        images = [fetch(a.url, c.upper()) for c in a.codes]
    else:
        ap.error("Code oder --png angeben")
    asyncio.run(send(images))


if __name__ == "__main__":
    main()
