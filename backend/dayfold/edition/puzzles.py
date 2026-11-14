"""Puzzle grids rendered as crisp PNG images for the EPUB (consistent in every reader)."""

from __future__ import annotations

import io

from PIL import Image, ImageDraw, ImageFont

from ..config import FONTS_DIR


def sudoku_png(grid: list[int], givens: list[int] | None = None, size: int = 900) -> bytes:
    cell = size // 9
    size = cell * 9
    pad = 6
    img = Image.new("L", (size + 2 * pad, size + 2 * pad), 255)
    d = ImageDraw.Draw(img)
    bold = ImageFont.truetype(str(FONTS_DIR / "Literata-Bold.ttf"), int(cell * 0.58))
    light = ImageFont.truetype(str(FONTS_DIR / "Literata-Regular.ttf"), int(cell * 0.55))
    for i, v in enumerate(grid):
        if not v:
            continue
        r, c = divmod(i, 9)
        is_given = givens is None or bool(givens[i])
        font = bold if is_given else light
        text = str(v)
        box = d.textbbox((0, 0), text, font=font)
        x = pad + c * cell + (cell - (box[2] - box[0])) / 2 - box[0]
        y = pad + r * cell + (cell - (box[3] - box[1])) / 2 - box[1]
        d.text((x, y), text, font=font, fill=0 if is_given else 85)
    for k in sorted(range(10), key=lambda k: k % 3 == 0):  # thin rules first, thick on top
        w = 6 if k % 3 == 0 else 2
        color = 0 if k % 3 == 0 else 120
        p = pad + k * cell
        d.rectangle([p - w // 2, pad - 3, p + (w - 1) // 2, pad + size + 3], fill=color)
        d.rectangle([pad - 3, p - w // 2, pad + size + 3, p + (w - 1) // 2], fill=color)
    out = io.BytesIO()
    img.save(out, "PNG", optimize=True)
    return out.getvalue()
