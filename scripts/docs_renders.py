"""Regenerate the README's page renders from one edition EPUB.

    cd backend && uv run python ../scripts/docs_renders.py path/to/dayfold-2026-11-16.epub

Writes into docs/screenshots/:

* kindle-cover.png: the edition's own cover image, at the Kindle Paperwhite size of 1236x1648;
* kindle-reading-flow.png: the five-page strip, holding the cover, the first section, the first
  comic, the first game page and the masthead, rendered from the EPUB at the same size.

Needs Pillow and a Chrome/Chromium binary; point CHROME at it when it is not in a usual place.
These are renders, not device captures: the book's stylesheet leaves page margins to the reader,
so the pages come out edge to edge.
"""

from __future__ import annotations

import argparse
import base64
import io
import os
import re
import shutil
import subprocess
import sys
import tempfile
import zipfile
from pathlib import Path
from xml.etree import ElementTree

from PIL import Image, ImageDraw, ImageFont

DEVICE = (1236, 1648)
PANEL = (300, 400)
GAP, CAPTION = 20, 52
# The pages the strip shows, in reading order, and the caption each one gets.
KINDS = (("sec_", "Seções"), ("comic_", "Quadrinhos"), ("game_", "Passatempos"), ("colophon", "Expediente"))


def find_chrome() -> str:
    if os.environ.get("CHROME"):
        return os.environ["CHROME"]
    found = shutil.which("google-chrome") or shutil.which("chromium") or shutil.which("chromium-browser")
    if found:
        return found
    mac = "/Applications/Google Chrome.app/Contents/MacOS/Google Chrome"
    if Path(mac).exists():
        return mac
    sys.exit("doc renders: no Chrome found, set CHROME=/path/to/chrome")


def spine_pages(z: zipfile.ZipFile) -> list[str]:
    """The EPUB's pages in reading order. ebooklib writes the package document, so read it as XML
    rather than matching its serialization."""
    ns = {"opf": "http://www.idpf.org/2007/opf"}
    package = ElementTree.fromstring(z.read("EPUB/content.opf"))
    manifest = {item.get("id"): item.get("href")
                for item in package.find("opf:manifest", ns).findall("opf:item", ns)}
    return [f"EPUB/{manifest[ref.get('idref')]}"
            for ref in package.find("opf:spine", ns).findall("opf:itemref", ns)
            if manifest[ref.get("idref")].endswith(".xhtml")]


def strip_pages(z: zipfile.ZipFile) -> list[tuple[str, str]]:
    pages = spine_pages(z)
    picked = []
    for prefix, label in KINDS:
        match = [page for page in pages if Path(page).name.startswith(prefix)]
        if not match:
            sys.exit(f"doc renders: no {prefix}* page in this EPUB")
        picked.append((match[0], label))
    return picked


def stylesheet(z: zipfile.ZipFile) -> str:
    """The edition CSS with its fonts embedded, so a bare browser renders it like the reader does."""
    css = z.read("EPUB/style/edition.css").decode()

    def font(match):
        name = match.group(1).split("fonts/")[-1]
        mime = "font/otf" if name.endswith(".otf") else "font/ttf"
        return f'url("data:{mime};base64,{base64.b64encode(z.read(f"EPUB/fonts/{name}")).decode()}")'

    return re.sub(r'url\(["\']?([^"\')]*fonts/[^"\')]+)["\']?\)', font, css)


def page_html(z: zipfile.ZipFile, page: str, css: str) -> str:
    """One self-contained page. Served as .html: the HTML parser ignores the epub: namespace
    attributes, while an .xhtml file would be parsed as XML and fail without them."""
    html = z.read(page).decode()

    def image(match):
        src = match.group(1)
        mime = "image/png" if src.endswith(".png") else "image/jpeg"
        data = base64.b64encode(z.read("EPUB/" + src)).decode()
        return f'src="data:{mime};base64,{data}"'

    html = re.sub(r'src="(images/[^"]+)"', image, html)
    html, linked = re.subn(r'<link[^>]*href="[^"]*edition\.css"[^>]*>',
                           lambda _: f'<meta charset="utf-8"/><style>\n{css}\n</style>', html)
    if not linked:
        sys.exit(f"doc renders: {page} does not link the edition stylesheet")
    return html.replace("<?xml version='1.0' encoding='utf-8'?>", "")


def render(chrome: str, profile: Path, html: Path, dest: Path) -> None:
    result = subprocess.run(
        [chrome, "--headless=new", f"--user-data-dir={profile}", "--disable-gpu", "--hide-scrollbars",
         "--force-device-scale-factor=1", f"--window-size={DEVICE[0]},{DEVICE[1]}",
         "--virtual-time-budget=4000", f"--screenshot={dest}", html.as_uri()],
        check=False, capture_output=True, text=True,
    )
    if result.returncode or not dest.exists():
        sys.exit(f"doc renders: Chrome produced no screenshot for {html.name}\n{result.stderr.strip()}".rstrip())


def caption_font(z: zipfile.ZipFile) -> ImageFont.FreeTypeFont:
    return ImageFont.truetype(io.BytesIO(z.read("EPUB/fonts/Literata-Bold.ttf")), 28)


def strip(panels: list[tuple[Path, str]], font: ImageFont.FreeTypeFont, dest: Path) -> None:
    width, height = PANEL
    sheet = Image.new("RGB", (len(panels) * width + (len(panels) - 1) * GAP, height + CAPTION), "white")
    draw = ImageDraw.Draw(sheet)
    for i, (path, label) in enumerate(panels):
        x = i * (width + GAP)
        caption = f"{i + 1}. {label}"
        sheet.paste(Image.open(path).convert("RGB").resize(PANEL, Image.LANCZOS), (x, 0))
        draw.rectangle([x, 0, x + width - 1, height - 1], outline=(190, 190, 190), width=1)
        draw.text((x + (width - draw.textlength(caption, font=font)) / 2, height + 10), caption,
                  font=font, fill=(20, 20, 20))
    sheet.save(dest)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("epub", type=Path, help="edition EPUB, as served to the Kindle")
    parser.add_argument("--out", type=Path, help="where the PNGs go (default: docs/screenshots)")
    args = parser.parse_args()

    chrome = find_chrome()
    out = args.out or Path(__file__).resolve().parents[1] / "docs" / "screenshots"
    out.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(prefix="dayfold-renders-") as tmp, zipfile.ZipFile(args.epub) as z:
        workdir = Path(tmp)
        cover = out / "kindle-cover.png"
        Image.open(z.open("EPUB/images/cover.png")).convert("RGB").save(cover)
        css = stylesheet(z)
        panels = [(cover, "Capa")]
        for page, label in strip_pages(z):
            html = workdir / f"{Path(page).stem}.html"
            html.write_text(page_html(z, page, css))
            shot = workdir / f"{Path(page).stem}.png"
            render(chrome, workdir / "chrome", html, shot)
            panels.append((shot, label))
        strip(panels, caption_font(z), out / "kindle-reading-flow.png")

    print(f"{out / 'kindle-cover.png'} ({DEVICE[0]}x{DEVICE[1]})")
    print(f"{out / 'kindle-reading-flow.png'} ({len(panels)} pages: {', '.join(label for _, label in panels)})")


if __name__ == "__main__":
    main()
