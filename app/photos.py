"""Fotos: verkleinert als JPEG ablegen (max. 1600 px) plus Vorschaubild (400 px)."""

import io
import uuid
from pathlib import Path

from PIL import Image, ImageOps, UnidentifiedImageError

from app.repo import LagerError

MAX_BYTES = 30 * 1024 * 1024
FULL_PX, THUMB_PX = 1600, 400


def save(data: bytes, photo_dir: Path) -> str:
    """Speichert `<uuid>.jpg` und `thumb_<uuid>.jpg`, gibt den Dateinamen zurück."""
    if len(data) > MAX_BYTES:
        raise LagerError("Foto zu groß (max. 30 MB)")
    try:
        with Image.open(io.BytesIO(data)) as raw:
            img = ImageOps.exif_transpose(raw).convert("RGB")  # Handyfotos richtig drehen
    except (UnidentifiedImageError, OSError):
        raise LagerError("Datei ist kein lesbares Bild") from None
    photo_dir.mkdir(parents=True, exist_ok=True)
    name = f"{uuid.uuid4().hex}.jpg"
    for prefix, px in (("", FULL_PX), ("thumb_", THUMB_PX)):
        copy = img.copy()
        copy.thumbnail((px, px))
        copy.save(photo_dir / f"{prefix}{name}", "JPEG", quality=85, optimize=True)
    return name


def delete(name: str | None, photo_dir: Path) -> None:
    if name:
        for prefix in ("", "thumb_"):
            (photo_dir / f"{prefix}{name}").unlink(missing_ok=True)
