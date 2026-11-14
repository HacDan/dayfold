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


def crossword_png(grid: list[str], numbers: list[list[int]], solution: list[str] | None = None,
                  width: int = 1000) -> bytes:
    """Free-form crossword: boxes only where letters go, clue numbers in the corner and,
    for the solution page, the letters filled in."""
    rows, cols = len(grid), len(grid[0])
    cell = min(width // cols, 110)
    pad = 6
    img = Image.new("L", (cols * cell + 2 * pad, rows * cell + 2 * pad), 255)
    d = ImageDraw.Draw(img)
    num_font = ImageFont.truetype(str(FONTS_DIR / "Literata-Regular.ttf"), max(12, int(cell * 0.26)))
    letter_font = ImageFont.truetype(str(FONTS_DIR / "Literata-Bold.ttf"), int(cell * 0.55))
    for r, row in enumerate(grid):
        for c, ch in enumerate(row):
            if ch == "#":
                continue
            x, y = pad + c * cell, pad + r * cell
            d.rectangle([x, y, x + cell, y + cell], outline=0, width=3)
            if solution:
                text = solution[r][c]
                box = d.textbbox((0, 0), text, font=letter_font)
                d.text((x + (cell - (box[2] - box[0])) / 2 - box[0],
                        y + cell * 0.12 + (cell - (box[3] - box[1])) / 2 - box[1]), text, font=letter_font, fill=0)
    for r, c, n in numbers:
        d.text((pad + c * cell + 6, pad + r * cell + 3), str(n), font=num_font, fill=0)
    out = io.BytesIO()
    img.save(out, "PNG", optimize=True)
    return out.getvalue()
