import json

from edition_helpers import epub_text, generate

ARTICLES = [("nasa", "Telescope maps the edge of the solar system"),
            ("agencia-brasil", "Libraries open on Saturdays"),
            ("who-news", "Vaccination campaign reaches remote villages")]


def test_new_install_prints_an_english_edition(data_dir, monkeypatch):
    epub = generate(monkeypatch, ARTICLES, games_per_edition=3)
    text = epub_text(epub)
    assert "The day's news, folded for an unhurried read." in text
    assert "Space" in text and "Espaço" not in text
    assert "Brazil" in text
    for pt in ("Edição", "Passatempos", "Fim da edição", "Fontes desta edição", "Palavras Cruzadas"):
        assert pt not in text, pt
    games = json.loads(epub.with_name(epub.name.replace(".epub", ".games.json")).read_text())
    assert games["language"] == "en"
    for g in games["games"]:
        if "language" in g["puzzle"]:
            assert g["puzzle"]["language"] == "en", g["kind"]


def test_portuguese_edition_keeps_portuguese(data_dir, monkeypatch):
    epub = generate(monkeypatch, ARTICLES, language="pt", games_per_edition=3)
    text = epub_text(epub)
    assert "Notícias do dia, dobradas para ler com calma." in text
    assert "Espaço" in text and "Passatempos" in text
    games = json.loads(epub.with_name(epub.name.replace(".epub", ".games.json")).read_text())
    assert all(g["puzzle"].get("language", "pt") == "pt" for g in games["games"])


def test_custom_names_are_kept(data_dir, monkeypatch):
    from sqlalchemy import select

    from dayfold.db import session_scope
    from dayfold.models import Topic

    with session_scope() as s:
        s.scalar(select(Topic).where(Topic.slug == "espaco")).name = "Cosmos"
    text = epub_text(generate(monkeypatch, ARTICLES, tagline="Mine"))
    assert "Cosmos" in text and "Mine" in text


def test_old_portuguese_games_follow_the_edition(data_dir):
    from dayfold.db import session_scope
    from dayfold.models import Game, Setting
    from dayfold.seed import seed

    with session_scope() as s:
        s.delete(s.get(Setting, "migrations"))
        for g in s.query(Game):
            if "language" in g.config:
                g.config = {**g.config, "language": "pt"}
    with session_scope() as s:
        seed(s)
    with session_scope() as s:
        langs = {g.kind: g.config.get("language") for g in s.query(Game)}
        assert langs == {"sudoku": None, "wordle": "auto", "wordsearch": "auto", "crossword": "auto"}
        # runs once: an explicit choice made later is kept
        s.query(Game).filter(Game.kind == "wordle").one().config = {"language": "pt", "length": 5}
    with session_scope() as s:
        seed(s)
    with session_scope() as s:
        assert s.query(Game).filter(Game.kind == "wordle").one().config["language"] == "pt"


def test_word_search_theme_follows_language():
    from dayfold.games.generators import seeded, wordsearch

    puzzle, _ = wordsearch(seeded("x", "ws"), "en", 12, "animais", 8)
    assert puzzle["theme"] == "Animals"
