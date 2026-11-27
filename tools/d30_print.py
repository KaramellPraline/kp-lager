"""Etiketten per Bluetooth direkt auf den D30 drucken (PC mit Bluetooth, Paket `bleak`).

    uv run --with bleak python tools/d30_print.py CBL-025 [CBL-026 ...]
    uv run --with bleak python tools/d30_print.py --png etikett.png

Holt das Bild von /labels/img/<CODE>.png des Servers (Standard https://lager.home.lan).
Mit Anmeldung am Server: API-Schlüssel (Lesen) per --key oder Umgebung LAGER_API_KEY.
"""

import argparse
import io
import os
import ssl
import sys
import urllib.request
from pathlib import Path

from PIL import Image

sys.path.insert(0, str(Path(__file__).parents[1]))
from app import d30  # noqa: E402


def fetch(url: str, code: str, key: str = "") -> Image.Image:
    ctx = ssl.create_default_context()
    ctx.check_hostname = False  # LAN mit eigener CA
    ctx.verify_mode = ssl.CERT_NONE
    req = urllib.request.Request(f"{url}/labels/img/{code}.png",
                                 headers={"X-API-Key": key} if key else {})  # fmt: skip
    with urllib.request.urlopen(req, context=ctx, timeout=10) as r:
        return Image.open(io.BytesIO(r.read())).convert("1")


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("codes", nargs="*")
    ap.add_argument("--png", help="fertiges Bild 320×96 statt Server")
    ap.add_argument("--url", default="https://lager.home.lan")
    ap.add_argument("--key", default=os.environ.get("LAGER_API_KEY", ""), help="API-Schlüssel")
    a = ap.parse_args()
    if a.png:
        images = [Image.open(a.png).convert("1")]
    elif a.codes:
        images = [fetch(a.url, c.upper(), a.key) for c in a.codes]
    else:
        ap.error("Code oder --png angeben")
    d30.send(images)
    print(f"{len(images)} Etikett(en) gesendet")


if __name__ == "__main__":
    main()
