"""Front page cover rendered with Pillow: a classic broadsheet in 16 gray levels.

The same PNG is the EPUB cover, the dashboard preview and the Kindle screensaver.
Layout is designed at 1236×1648 (Kindle Paperwhite 5) and scaled to the configured size.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path

from PIL import Image, ImageDraw, ImageFont, ImageOps

from ..config import FONTS_DIR
from ..settings import masthead_font_path
from .images import to_eink_png

REF_W, REF_H = 1236, 1648
INK = 0
GRAY = 85
PAPER = 255


@dataclass
class CoverData:
    title: str
    masthead_font: str
    tagline: str
    long_date: str
    number_label: str  # "Nº 12"
    year_label: str  # "Ano I"
    daily_label: str
    headline: str
    deck: str | None = None
    headline_source: str | None = None
    image_path: Path | None = None
    also_label: str = "Também nesta edição"
    secondary: list[tuple[str, str]] = field(default_factory=list)  # (section, title)
    lead_text: str | None = None
    weather: list[str] | None = None  # the front page's weather and sun lines
    footer: str = ""


def _font(name: str, size: int) -> ImageFont.FreeTypeFont:
    return ImageFont.truetype(str(FONTS_DIR / name), max(8, int(size)))


def _wrap(draw: ImageDraw.ImageDraw, text: str, font: ImageFont.FreeTypeFont, width: int) -> list[str]:
    words = text.split()
    lines: list[str] = []
    cur = ""
    for w in words:
        trial = f"{cur} {w}".strip()
        if draw.textlength(trial, font=font) <= width or not cur:
            cur = trial
        else:
            lines.append(cur)
            cur = w
    if cur:
        lines.append(cur)
    return lines


def _clamp_lines(draw, lines: list[str], font, width: int, max_lines: int) -> list[str]:
    if len(lines) <= max_lines:
        return lines
    kept = lines[:max_lines]
    last = kept[-1]
    while last and draw.textlength(last + "…", font=font) > width:
        last = last[:-1]
    kept[-1] = last.rstrip(" ,;:.") + "…"
    return kept


def _fit_block(draw, text: str, font_name: str, width: int, max_size: int, min_size: int,
               max_lines: int) -> tuple[ImageFont.FreeTypeFont, list[str]]:
    size = max_size
    while size > min_size:
        f = _font(font_name, size)
        lines = _wrap(draw, text, f, width)
        if len(lines) <= max_lines:
            return f, lines
        size -= 2
    f = _font(font_name, min_size)
    return f, _clamp_lines(draw, _wrap(draw, text, f, width), f, width, max_lines)


def _center(draw, y: int, text: str, font, W: int, fill: int = INK) -> None:
    w = draw.textlength(text, font=font)
    draw.text(((W - w) / 2, y), text, font=font, fill=fill)


def render_cover(data: CoverData, dest: Path, width: int = REF_W, height: int = REF_H) -> Path:
    img = Image.new("L", (REF_W, REF_H), PAPER)
    d = ImageDraw.Draw(img)
    W, H = REF_W, REF_H
    M = 64  # outer margin
    inner = W - 2 * M

    # top strip
    small = _font("OldStandard-Regular.ttf", 24)
    y = 46
    d.text((M, y), data.year_label.upper(), font=small, fill=INK)
    right = data.daily_label.upper()
    d.text((W - M - d.textlength(right, font=small), y), right, font=small, fill=INK)
    _center(d, y, data.number_label.upper(), small, W)
    y += 40

    # masthead, fitted to the width
    mpath = masthead_font_path(data.masthead_font)
    size = 230
    while size > 60:
        mf = ImageFont.truetype(mpath, size)
        if d.textlength(data.title, font=mf) <= inner * 0.94:
            break
        size -= 4
    bbox = d.textbbox((0, 0), data.title, font=mf)
    mh = bbox[3] - bbox[1]
    d.text(((W - (bbox[2] - bbox[0])) / 2 - bbox[0], y - bbox[1] + 6), data.title, font=mf, fill=INK)
    y += mh + 28

    if data.tagline:
        tf = _font("Literata-Italic.ttf", 27)
        _center(d, y, data.tagline, tf, W, fill=GRAY - 30)
        y += 46

    # dateline between rules
    d.rectangle([M, y, W - M, y + 5], fill=INK)
    y += 13
    df = _font("OldStandard-Bold.ttf", 27)
    _center(d, y, data.long_date.upper(), df, W)
    y += 42
    d.rectangle([M, y, W - M, y + 1], fill=INK)
    y += 34

    # weather and sun under the dateline, as on the front page
    if data.weather:
        for text in data.weather:
            wf, wlines = _fit_block(d, text, "OldStandard-Regular.ttf", inner, 25, 17, 1)
            _center(d, y, wlines[0].upper(), wf, W, fill=GRAY - 10)
            y += 35
        d.rectangle([M, y - 4, W - M, y - 3], fill=170)
        y += 26

    # headline
    hf, hlines = _fit_block(d, data.headline, "PlayfairDisplay-Black.ttf", inner, 88, 52, 3)
    lh = int(hf.size * 1.1)
    for line in hlines:
        _center(d, y, line, hf, W)
        y += lh
    y += 24  # the headline's descenders reach into its line box; keep the source clear of them

    if data.deck:
        ff, flines = _fit_block(d, data.deck, "Literata-Italic.ttf", inner - 80, 33, 26, 3)
        for line in flines:
            _center(d, y, line, ff, W, fill=34)
            y += int(ff.size * 1.35)
        y += 8
    if data.headline_source:
        sf = _font("OldStandard-Regular.ttf", 22)
        _center(d, y, data.headline_source.upper(), sf, W, fill=GRAY - 17)
        y += 40

    footer_h = 70
    has_image = bool(data.image_path and Path(data.image_path).exists())
    secondary = data.secondary[:3] if has_image else data.secondary[:6]
    rows = 1 if len(secondary) <= 3 else 2
    also_h = (46 + 235 * rows) if secondary else 0
    bottom = H - footer_h - 24 - also_h
    if has_image and bottom - y > 260:
        photo = Image.open(data.image_path).convert("L")
        ph = min(bottom - y - 10, int(inner * 0.6))
        photo = ImageOps.fit(photo, (inner, ph), Image.LANCZOS)
        img.paste(photo, (M, y))
        d.rectangle([M, y, M + inner - 1, y + photo.height - 1], outline=INK, width=2)
        y += photo.height + 26
    if data.lead_text and bottom - y > 120:
        cols, gap = 2, 40
        colw = (inner - gap) // cols
        bf = _font("Literata-Regular.ttf", 25)
        lh = 37
        lines = _wrap(d, data.lead_text, bf, colw)
        per_col = max(1, (bottom - y - 10) // lh)
        lines = _clamp_lines(d, lines, bf, colw, per_col * cols)
        for i in range(cols):
            chunk = lines[i * per_col : (i + 1) * per_col]
            x = M + i * (colw + gap)
            for j, line in enumerate(chunk):
                d.text((x, y + j * lh), line, font=bf, fill=20)
            if i and chunk:
                d.line([x - gap // 2, y, x - gap // 2, y + len(chunk) * lh], fill=170, width=1)
        used = min(len(lines), per_col) * lh
        y += used + 24
    y = max(y, bottom) if secondary else y

    # "also in this edition"
    if secondary:
        lf = _font("OldStandard-Bold.ttf", 22)
        label = data.also_label.upper()
        lw = d.textlength(label, font=lf)
        d.line([M, y + 13, (W - lw) / 2 - 18, y + 13], fill=INK, width=2)
        d.line([(W + lw) / 2 + 18, y + 13, W - M, y + 13], fill=INK, width=2)
        _center(d, y, label, lf, W)
        y += 46
        cols = 3
        gap = 34
        colw = (inner - gap * (cols - 1)) // cols
        kf = _font("OldStandard-Bold.ttf", 19)
        row_top = y
        bottom_limit = H - footer_h - 20
        for row in [secondary[i : i + cols] for i in range(0, len(secondary), cols)]:
            row_h = 0
            for i, (section, title) in enumerate(row):
                x = M + i * (colw + gap)
                yy = row_top
                d.text((x, yy), section.upper(), font=kf, fill=GRAY - 17)
                yy += 30
                tf, tlines = _fit_block(d, title, "PlayfairDisplay-Bold.ttf", colw, 31, 24, 5)
                for line in tlines:
                    if yy + tf.size > bottom_limit:
                        break
                    d.text((x, yy), line, font=tf, fill=INK)
                    yy += int(tf.size * 1.18)
                row_h = max(row_h, yy - row_top)
                if i:
                    d.line([x - gap // 2, row_top, x - gap // 2, row_top + 200], fill=170, width=1)
            row_top += row_h + 26
            if row_top > bottom_limit - 120:
                break

    # footer
    d.rectangle([M, H - footer_h, W - M, H - footer_h + 1], fill=INK)
    if data.footer:
        ff = _font("OldStandard-Italic.ttf", 23)
        _center(d, H - footer_h + 18, data.footer, ff, W)

    if (width, height) != (REF_W, REF_H):
        img = img.resize((width, height), Image.LANCZOS)
    dest.parent.mkdir(parents=True, exist_ok=True)
    return to_eink_png(img, dest)
