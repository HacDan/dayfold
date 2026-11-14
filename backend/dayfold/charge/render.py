"""Structured cartoon renderer.

The AI writes a small script (characters, poses, props, speech) and this module draws it
as clean black line art. Rendering is deterministic and controlled, so the cartoon always
fits the newspaper style and e-ink, and the AI never produces pixels.
"""

from __future__ import annotations

import math
from pathlib import Path
from typing import Literal

from PIL import Image, ImageDraw, ImageFont
from pydantic import BaseModel, Field

from ..config import FONTS_DIR
from ..edition.images import to_eink_png

Pose = Literal["standing", "pointing", "arms_up", "thinking", "shrugging", "sitting", "running"]
PropKind = Literal["sign", "desk", "globe", "computer", "rocket", "cloud", "sun", "building",
                   "chart_up", "chart_down", "tree", "ballot_box", "microphone", "book", "planet"]


class Character(BaseModel):
    name: str = Field("", max_length=40)
    x: float = Field(0.5, ge=0.05, le=0.95)
    pose: Pose = "standing"
    facing: Literal["left", "right"] = "right"
    speech: str | None = Field(None, max_length=160)
    hat: Literal["none", "top", "cap", "crown", "helmet"] = "none"
    size: Literal["small", "normal", "large"] = "normal"


class Prop(BaseModel):
    kind: PropKind
    label: str | None = Field(None, max_length=40)
    x: float = Field(0.5, ge=0.0, le=1.0)


class ChargeScript(BaseModel):
    title: str = Field(max_length=80)
    caption: str = Field(max_length=200)
    setting: str | None = Field(None, max_length=60)
    characters: list[Character] = Field(min_length=1, max_length=3)
    props: list[Prop] = Field(default_factory=list, max_length=4)


W, H = 1200, 1000
PANEL = (40, 110, W - 40, 860)
GROUND = 700
INK = 0
LINE = 5


def _font(name: str, size: int) -> ImageFont.FreeTypeFont:
    return ImageFont.truetype(str(FONTS_DIR / name), size)


def _wrap(d: ImageDraw.ImageDraw, text: str, font, width: int) -> list[str]:
    out, cur = [], ""
    for w in text.split():
        t = f"{cur} {w}".strip()
        if d.textlength(t, font=font) <= width or not cur:
            cur = t
        else:
            out.append(cur)
            cur = w
    if cur:
        out.append(cur)
    return out


def _hatch(d: ImageDraw.ImageDraw, box: tuple[int, int, int, int], step: int = 12) -> None:
    x0, y0, x1, y1 = box
    for k in range(x0 - (y1 - y0), x1, step):
        a = (max(k, x0), y0 + max(0, x0 - k))
        b = (min(k + (y1 - y0), x1), y0 + min(y1 - y0, x1 - k))
        if a[0] < b[0]:
            d.line([a, b], fill=INK, width=1)


def _figure(d: ImageDraw.ImageDraw, c: Character, cx: int) -> tuple[int, int]:
    s = {"small": 0.8, "normal": 1.0, "large": 1.2}[c.size]
    head_r = int(34 * s)
    body = int(150 * s)
    leg = int(130 * s)
    foot_y = GROUND
    sitting = c.pose == "sitting"
    hip_y = foot_y - (leg // 2 if sitting else leg)
    neck_y = hip_y - body
    head_c = (cx, neck_y - head_r)
    f = 1 if c.facing == "right" else -1
    # legs
    if sitting:
        knee = (cx + f * int(leg * 0.55), hip_y)
        d.line([(cx, hip_y), knee, (knee[0], foot_y)], fill=INK, width=LINE, joint="curve")
        d.line([(knee[0], foot_y), (knee[0] + f * 22, foot_y)], fill=INK, width=LINE)
        seat_y = hip_y + 10
        back_x = cx - f * 44
        d.rectangle([min(back_x, cx + f * 40), seat_y, max(back_x, cx + f * 40), seat_y + 10], fill=INK)
        d.line([(back_x, seat_y), (back_x, seat_y - int(body * 0.75))], fill=INK, width=LINE)
        d.line([(back_x, seat_y + 10), (back_x, foot_y)], fill=INK, width=4)
        d.line([(cx + f * 36, seat_y + 10), (cx + f * 36, foot_y)], fill=INK, width=4)
    elif c.pose == "running":
        d.line([(cx, hip_y), (cx + f * 55, hip_y + leg // 2), (cx + f * 20, foot_y)], fill=INK, width=LINE)
        d.line([(cx, hip_y), (cx - f * 45, hip_y + leg // 2 + 10), (cx - f * 90, foot_y - 20)], fill=INK, width=LINE)
    else:
        d.line([(cx, hip_y), (cx - 28, foot_y)], fill=INK, width=LINE)
        d.line([(cx, hip_y), (cx + 28, foot_y)], fill=INK, width=LINE)
        d.line([(cx - 28, foot_y), (cx - 28 - 18 * f * -1, foot_y)], fill=INK, width=LINE)
        d.line([(cx + 28, foot_y), (cx + 28 + 18 * f, foot_y)], fill=INK, width=LINE)
    # torso as a jacket
    d.polygon([(cx - 34 * s, neck_y + 8), (cx + 34 * s, neck_y + 8), (cx + 28 * s, hip_y),
               (cx - 28 * s, hip_y)], outline=INK, fill=255, width=LINE)
    d.line([(cx, neck_y + 8), (cx, hip_y)], fill=INK, width=2)
    d.polygon([(cx - 8, neck_y + 8), (cx + 8, neck_y + 8), (cx, neck_y + 40)], fill=INK)
    # arms
    sh = (cx + f * 30 * s, neck_y + 22)
    sh2 = (cx - f * 30 * s, neck_y + 22)
    arm = 105 * s
    if c.pose == "pointing":
        a1 = [(sh[0], sh[1]), (sh[0] + f * arm, sh[1] - 25)]
        a2 = [sh2, (sh2[0] - f * 20, sh2[1] + arm * 0.9)]
    elif c.pose == "arms_up":
        a1 = [sh, (sh[0] + f * 45, sh[1] - arm * 0.6), (sh[0] + f * 60, sh[1] - arm)]
        a2 = [sh2, (sh2[0] - f * 45, sh2[1] - arm * 0.6), (sh2[0] - f * 60, sh2[1] - arm)]
    elif c.pose == "thinking":
        a1 = [sh, (sh[0] + f * 35, sh[1] + 60), (head_c[0] + f * 22, head_c[1] + head_r + 6)]
        a2 = [sh2, (sh2[0] - f * 10, sh2[1] + arm * 0.9)]
    elif c.pose == "shrugging":
        a1 = [sh, (sh[0] + f * 50, sh[1] + 45), (sh[0] + f * 85, sh[1] + 5)]
        a2 = [sh2, (sh2[0] - f * 50, sh2[1] + 45), (sh2[0] - f * 85, sh2[1] + 5)]
    elif c.pose == "running":
        a1 = [sh, (sh[0] + f * 55, sh[1] + 30), (sh[0] + f * 80, sh[1] - 15)]
        a2 = [sh2, (sh2[0] - f * 50, sh2[1] + 55)]
    else:
        a1 = [sh, (sh[0] + f * 12, sh[1] + arm * 0.9)]
        a2 = [sh2, (sh2[0] - f * 12, sh2[1] + arm * 0.9)]
    d.line(a1, fill=INK, width=LINE, joint="curve")
    d.line(a2, fill=INK, width=LINE, joint="curve")
    # head
    hx, hy = head_c
    d.ellipse([hx - head_r, hy - head_r, hx + head_r, hy + head_r], outline=INK, fill=255, width=LINE)
    d.ellipse([hx + f * 10 - 4, hy - 8, hx + f * 10 + 4, hy], fill=INK)  # eye
    d.line([(hx + f * head_r, hy + 2), (hx + f * (head_r + 9), hy + 10), (hx + f * head_r, hy + 14)],
           fill=INK, width=3)  # nose
    mouth = "shrug" if c.pose == "shrugging" else "o" if c.pose == "arms_up" else "line"
    if mouth == "o":
        d.ellipse([hx + f * 14 - 6, hy + 14, hx + f * 14 + 6, hy + 26], outline=INK, width=3)
    else:
        d.line([(hx + f * 4, hy + 20), (hx + f * 20, hy + 18)], fill=INK, width=3)
    # hats
    top = hy - head_r
    if c.hat == "top":
        d.rectangle([hx - 40, top - 4, hx + 40, top + 4], fill=INK)
        d.rectangle([hx - 24, top - 60, hx + 24, top - 4], fill=INK)
    elif c.hat == "cap":
        d.chord([hx - head_r, top - 10, hx + head_r, top + 40], 180, 360, fill=INK)
        d.rectangle([hx + (0 if f > 0 else -55), top + 12, hx + (55 if f > 0 else 0), top + 18], fill=INK)
    elif c.hat == "crown":
        pts = [(hx - 30, top + 6), (hx - 30, top - 30), (hx - 15, top - 12), (hx, top - 36),
               (hx + 15, top - 12), (hx + 30, top - 30), (hx + 30, top + 6)]
        d.polygon(pts, outline=INK, fill=255, width=4)
    elif c.hat == "helmet":
        d.chord([hx - head_r - 6, top - 10, hx + head_r + 6, top + 50], 180, 360, outline=INK, fill=255, width=LINE)
        _hatch(d, (int(hx - head_r), int(top - 4), int(hx + head_r), int(top + 18)), 8)
    # name tag
    if c.name:
        nf = _font("OldStandard-Bold.ttf", 24)
        tw = d.textlength(c.name.upper(), font=nf)
        d.text((cx - tw / 2, foot_y + 16), c.name.upper(), font=nf, fill=INK)
    return int(hx), int(hy - head_r - (60 if c.hat == "top" else 30 if c.hat != "none" else 0))


def _prop(d: ImageDraw.ImageDraw, p: Prop, x: int) -> None:
    lf = _font("OldStandard-Bold.ttf", 22)
    k = p.kind
    if k == "sign":
        d.line([(x, GROUND), (x, GROUND - 230)], fill=INK, width=LINE)
        d.rectangle([x - 110, GROUND - 330, x + 110, GROUND - 230], outline=INK, fill=255, width=LINE)
    elif k == "desk":
        d.rectangle([x - 130, GROUND - 120, x + 130, GROUND - 100], fill=INK)
        d.rectangle([x - 120, GROUND - 100, x - 100, GROUND], fill=INK)
        d.rectangle([x + 100, GROUND - 100, x + 120, GROUND], fill=INK)
    elif k == "globe" or k == "planet":
        d.ellipse([x - 80, GROUND - 260, x + 80, GROUND - 100], outline=INK, fill=255, width=LINE)
        d.arc([x - 80, GROUND - 220, x + 80, GROUND - 140], 0, 180, fill=INK, width=3)
        d.line([(x, GROUND - 100), (x, GROUND)], fill=INK, width=LINE)
        if k == "planet":
            d.ellipse([x - 120, GROUND - 200, x + 120, GROUND - 160], outline=INK, width=3)
    elif k == "computer":
        d.rectangle([x - 90, GROUND - 260, x + 90, GROUND - 130], outline=INK, fill=255, width=LINE)
        _hatch(d, (x - 80, GROUND - 250, x + 80, GROUND - 140), 14)
        d.rectangle([x - 20, GROUND - 130, x + 20, GROUND - 100], fill=INK)
        d.rectangle([x - 70, GROUND - 100, x + 70, GROUND - 90], fill=INK)
    elif k == "rocket":
        d.polygon([(x, GROUND - 420), (x + 50, GROUND - 330), (x + 50, GROUND - 120),
                   (x - 50, GROUND - 120), (x - 50, GROUND - 330)], outline=INK, fill=255, width=LINE)
        d.ellipse([x - 22, GROUND - 320, x + 22, GROUND - 276], outline=INK, width=4)
        d.polygon([(x - 50, GROUND - 200), (x - 95, GROUND - 110), (x - 50, GROUND - 130)], fill=INK)
        d.polygon([(x + 50, GROUND - 200), (x + 95, GROUND - 110), (x + 50, GROUND - 130)], fill=INK)
        for i in range(3):
            d.line([(x - 25 + 25 * i, GROUND - 115), (x - 30 + 25 * i, GROUND - 60)], fill=INK, width=3)
    elif k == "cloud":
        y = 400
        for dx, r in ((-60, 45), (0, 62), (60, 45), (-25, 40), (30, 42)):
            d.ellipse([x + dx - r, y - r, x + dx + r, y + r], fill=255, outline=INK, width=4)
        d.rectangle([x - 100, y, x + 100, y + 44], fill=255)
        d.line([(x - 104, y + 44), (x + 104, y + 44)], fill=INK, width=4)
    elif k == "sun":
        y = 400
        d.ellipse([x - 45, y - 45, x + 45, y + 45], outline=INK, width=LINE)
        for i in range(12):
            a = i * math.pi / 6
            d.line([(x + 60 * math.cos(a), y + 60 * math.sin(a)),
                    (x + 85 * math.cos(a), y + 85 * math.sin(a))], fill=INK, width=4)
    elif k == "building":
        d.polygon([(x - 140, GROUND - 300), (x, GROUND - 380), (x + 140, GROUND - 300)], outline=INK,
                  fill=255, width=LINE)
        d.rectangle([x - 130, GROUND - 300, x + 130, GROUND - 280], outline=INK, width=4)
        for i in range(5):
            cx = x - 104 + i * 52
            d.rectangle([cx - 10, GROUND - 280, cx + 10, GROUND - 20], outline=INK, width=4)
        d.rectangle([x - 150, GROUND - 20, x + 150, GROUND], fill=INK)
    elif k in ("chart_up", "chart_down"):
        d.rectangle([x - 120, GROUND - 330, x + 120, GROUND - 110], outline=INK, fill=255, width=LINE)
        pts = [(-100, 60), (-50, 120), (0, 90), (50, 150), (100, 190)]
        if k == "chart_down":
            pts = [(px, 250 - py) for px, py in pts]
        poly = [(x + px, GROUND - 120 - py) for px, py in pts]
        d.line(poly, fill=INK, width=LINE)
        tip = poly[-1]
        sign = -1 if k == "chart_up" else 1
        d.polygon([tip, (tip[0] - 26, tip[1] + 4 * -sign), (tip[0] - 6, tip[1] + 26 * -sign)], fill=INK)
        d.line([(x, GROUND - 110), (x, GROUND)], fill=INK, width=LINE)
    elif k == "tree":
        d.rectangle([x - 14, GROUND - 160, x + 14, GROUND], fill=INK)
        d.ellipse([x - 90, GROUND - 330, x + 90, GROUND - 140], outline=INK, fill=255, width=LINE)
        _hatch(d, (x - 50, GROUND - 260, x + 50, GROUND - 190), 16)
    elif k == "ballot_box":
        d.rectangle([x - 80, GROUND - 160, x + 80, GROUND], outline=INK, fill=255, width=LINE)
        d.rectangle([x - 40, GROUND - 168, x + 40, GROUND - 156], fill=INK)
        d.rectangle([x - 25, GROUND - 220, x + 25, GROUND - 160], outline=INK, fill=255, width=4)
    elif k == "microphone":
        d.line([(x, GROUND), (x, GROUND - 300)], fill=INK, width=LINE)
        d.ellipse([x - 22, GROUND - 350, x + 22, GROUND - 290], fill=INK)
        d.line([(x - 50, GROUND), (x + 50, GROUND)], fill=INK, width=LINE)
    elif k == "book":
        d.polygon([(x - 90, GROUND - 60), (x, GROUND - 40), (x + 90, GROUND - 60), (x + 90, GROUND - 10),
                   (x, GROUND + 0), (x - 90, GROUND - 10)], outline=INK, fill=255, width=LINE)
        d.line([(x, GROUND - 40), (x, GROUND)], fill=INK, width=3)
    if p.label:
        label = p.label.upper()
        if k == "sign":
            lines = _wrap(d, label, lf, 200)[:3]
            for i, line in enumerate(lines):
                tw = d.textlength(line, font=lf)
                d.text((x - tw / 2, GROUND - 320 + i * 30), line, font=lf, fill=INK)
        else:
            tw = d.textlength(label, font=lf)
            ty = 500 if k in ("cloud", "sun") else GROUND + 16
            d.text((x - tw / 2, ty), label, font=lf, fill=INK)


def _balloon(d: ImageDraw.ImageDraw, text: str, anchor: tuple[int, int], slot: int, slots: int) -> None:
    f = _font("Literata-Regular.ttf", 28)
    maxw = min(420, (PANEL[2] - PANEL[0]) // max(1, slots) - 30)
    lines = _wrap(d, text, f, maxw)[:5]
    tw = max(d.textlength(line, font=f) for line in lines)
    bw, bh = int(tw + 50), int(len(lines) * 36 + 30)
    zone = (PANEL[2] - PANEL[0]) / slots
    bx = int(PANEL[0] + zone * slot + (zone - bw) / 2)
    bx = max(PANEL[0] + 14, min(bx, PANEL[2] - bw - 14))
    by = PANEL[1] + 24
    d.rounded_rectangle([bx, by, bx + bw, by + bh], radius=26, outline=INK, fill=255, width=4)
    tail_x = max(bx + 30, min(anchor[0], bx + bw - 30))
    d.polygon([(tail_x - 14, by + bh - 2), (tail_x + 14, by + bh - 2), (anchor[0], anchor[1] - 12)],
              fill=255, outline=None)
    d.line([(tail_x - 14, by + bh), (anchor[0], anchor[1] - 12), (tail_x + 14, by + bh)], fill=INK, width=4)
    for i, line in enumerate(lines):
        lw = d.textlength(line, font=f)
        d.text((bx + (bw - lw) / 2, by + 15 + i * 36), line, font=f, fill=INK)


def render_charge(script: ChargeScript, dest: Path) -> Path:
    img = Image.new("L", (W, H), 255)
    d = ImageDraw.Draw(img)
    tf = _font("PlayfairDisplay-Black.ttf", 52)
    tw = d.textlength(script.title, font=tf)
    d.text(((W - tw) / 2, 28), script.title, font=tf, fill=INK)
    d.rectangle(PANEL, outline=INK, width=6)
    d.line([(PANEL[0], GROUND), (PANEL[2], GROUND)], fill=INK, width=4)
    for gx in range(PANEL[0] + 10, PANEL[2] - 10, 26):
        d.line([(gx, GROUND + 8), (gx - 12, GROUND + 20)], fill=120, width=1)
    if script.setting:
        sf = _font("OldStandard-Italic.ttf", 24)
        d.text((PANEL[0] + 18, PANEL[3] - 40), script.setting, font=sf, fill=60)
    inner_w = PANEL[2] - PANEL[0]
    # keep objects apart from each other and from the characters
    taken = [c.x for c in script.characters]
    props = sorted(script.props, key=lambda p: p.x)
    for p in props:
        for _ in range(12):
            if all(abs(p.x - t) >= 0.2 for t in taken):
                break
            p.x = min(0.95, p.x + 0.07) if p.x < 0.5 else max(0.05, p.x - 0.07)
        taken.append(p.x)
    for p in props:
        _prop(d, p, int(PANEL[0] + 60 + p.x * (inner_w - 120)))
    chars = sorted(script.characters, key=lambda c: c.x)
    heads = []
    for c in chars:
        cx = int(PANEL[0] + 80 + c.x * (inner_w - 160))
        heads.append(_figure(d, c, cx))
    speakers = [(c, h) for c, h in zip(chars, heads, strict=True) if c.speech]
    for i, (c, h) in enumerate(speakers):
        _balloon(d, c.speech or "", h, i, len(speakers))
    cf = _font("Literata-Italic.ttf", 32)
    lines = _wrap(d, script.caption, cf, W - 140)[:3]
    for i, line in enumerate(lines):
        lw = d.textlength(line, font=cf)
        d.text(((W - lw) / 2, PANEL[3] + 22 + i * 42), line, font=cf, fill=INK)
    return to_eink_png(img, dest)
