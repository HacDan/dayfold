import zipfile
from pathlib import Path

from dayfold.edition.cover import CoverData, render_cover
from dayfold.edition.epub import EditionDoc, build_epub
from dayfold.games.generators import seeded, sudoku, wordle, wordsearch


def test_cover_and_epub(tmp_path: Path):
    cover = render_cover(CoverData(title="Dayfold", masthead_font="chomsky", tagline="t", long_date="Hoje",
                                   number_label="Nº 1", year_label="Ano I", daily_label="Diária",
                                   headline="Manchete de teste", secondary=[("Mundo", "Outra")]),
                         tmp_path / "cover.png")
    games = []
    for kind, fn in (("sudoku", lambda r: sudoku(r)), ("wordle", lambda r: wordle(r)), ("wordsearch", lambda r: wordsearch(r))):
        p, s = fn(seeded("t", kind))
        games.append({"kind": kind, "title": kind, "puzzle": p, "solution": s})
    art = {"id": 1, "title": "Manchete", "subtitle": None, "author": "A", "date_label": "hoje", "provider": "P",
           "url": "https://x.org", "url_short": "x.org", "paragraphs": ["Um", "Dois"], "excerpt": None,
           "section_name": "Brasil"}
    doc = EditionDoc(identifier="dayfold-test", lang="pt", title="Dayfold", tagline="t", long_date="Hoje",
                     short_date="hoje", iso_date="2026-01-01", number_label="Nº 1", year_label="Ano I",
                     masthead_font="chomsky", typography={"masthead": 3, "headline": 2, "title": 1.4, "subtitle": 1,
                                                          "body": 1, "line_height": 1.5},
                     cover_path=cover, headline=art,
                     sections=[{"slug": "mundo", "name": "Mundo", "file": "sec_mundo.xhtml",
                                "articles": [dict(art, id=2, excerpt="Excerto", paragraphs=[])]}],
                     games=games)
    path = build_epub(doc, tmp_path / "e.epub")
    with zipfile.ZipFile(path) as z:
        names = z.namelist()
        assert "EPUB/front.xhtml" in names and "EPUB/solutions.xhtml" in names
        assert any(n.endswith("Chomsky.otf") for n in names)
        assert "dayfold://game/0" in z.read("EPUB/game_0.xhtml").decode()
