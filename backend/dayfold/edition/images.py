"""Image preparation for e-ink: grayscale, resized, contrast stretched, compact JPEG."""

from __future__ import annotations

import io
from pathlib import Path

from PIL import Image, ImageEnhance, ImageFilter, ImageOps

from .. import net


def prepare_photo(url: str, dest: Path, max_width: int) -> Path | None:
    try:
        data = net.fetch(url, max_bytes=30 * 1024 * 1024).content
        img = Image.open(io.BytesIO(data))
        img.draft("L", (max_width * 2, max_width * 2))
        img.load()
    except Exception:  # noqa: BLE001  any broken or unsupported image is skipped
        return None
    if img.width < 240 or img.height < 160:
        return None
    img = ImageOps.exif_transpose(img).convert("L")
    if img.width > max_width:
        img = img.resize((max_width, round(img.height * max_width / img.width)), Image.LANCZOS)
    img = ImageOps.autocontrast(img, cutoff=1)
    img = ImageEnhance.Contrast(img).enhance(1.08)
    img = img.filter(ImageFilter.UnsharpMask(radius=1.2, percent=60, threshold=2))
    dest.parent.mkdir(parents=True, exist_ok=True)
    img.save(dest, "JPEG", quality=78, optimize=True, progressive=False)
    return dest


def to_eink_png(img: Image.Image, dest: Path) -> Path:
    """Quantize a grayscale image to the 16 gray levels of e-ink panels."""
    g = img.convert("L")
    g = g.point(lambda v: round(v / 17) * 17)
    g.save(dest, "PNG", optimize=True)
    return dest
