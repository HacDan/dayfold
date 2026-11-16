"""DAYFOLD_LANGUAGE picks the language of the server's own text (errors, labels, logs)."""

import json

from edition_helpers import add_article, epub_text, generate


def test_language_env_is_normalised(monkeypatch):
    from dayfold.config import Config

    monkeypatch.setenv("DAYFOLD_LANGUAGE", "EN")
    assert Config().language == "en"
    monkeypatch.setenv("DAYFOLD_LANGUAGE", "pt-BR")
    assert Config().language == "pt"
    monkeypatch.setenv("DAYFOLD_LANGUAGE", "xx")
    assert Config().language == "pt"  # unknown values keep the source language
    monkeypatch.delenv("DAYFOLD_LANGUAGE")
    assert Config().language == "pt"


def test_fresh_install_paper_follows_the_server_language(data_dir, monkeypatch):
    from fastapi.testclient import TestClient

    from dayfold.app import app
    from dayfold.config import config
    from dayfold.db import session_scope
    from dayfold.models import Setting

    # A fresh install has no newspaper row yet: the default is what gets written on first run.
    with session_scope() as s:
        s.delete(s.get(Setting, "newspaper"))

    monkeypatch.setattr(config, "language", "en")
    with TestClient(app) as c:
        paper = c.get("/api/settings").json()["values"]["newspaper"]
        assert paper["language"] == "en"
        # the tagline prints on the cover: it must not be Portuguese in an English paper
        assert paper["tagline"] == "The day's news, folded for an unhurried read."
        assert c.put("/api/settings/newspaper", json={**paper, "language": "pt"}).status_code == 200

    # An existing install keeps the language its operator chose.
    monkeypatch.setattr(config, "language", "en")
    with TestClient(app) as c:
        assert c.get("/api/settings").json()["values"]["newspaper"]["language"] == "pt"


def test_puzzles_and_their_titles_follow_the_paper_language():
    from dayfold.games.generators import seeded
    from dayfold.pipeline.generate import GAME_TITLES, make_game

    # "auto" (the default) follows the paper; an explicit per-game language is honoured.
    auto = make_game("wordle", {"language": "auto", "length": 5}, seeded("x", "wordle"), "en", [])
    plain = make_game("wordle", {"length": 5}, seeded("x", "wordle"), "en", [])
    assert auto == plain
    stored = make_game("wordle", {"language": "pt", "length": 5}, seeded("x", "wordle"), "en", [])
    explicit = make_game("wordle", {"language": "pt", "length": 5}, seeded("x", "wordle"), "pt", [])
    assert stored == explicit

    en = make_game("crossword", {}, seeded("y", "crossword"), "en", [])
    pt = make_game("crossword", {}, seeded("y", "crossword"), "pt", [])
    assert en != pt  # the puzzle really is built in the paper's language

    # Cover footer and job log use the same titles as the game page.
    assert GAME_TITLES["en"]["crossword"] == "Crossword"
    assert GAME_TITLES["pt"]["crossword"] == "Palavras Cruzadas"



def test_game_preview_and_themes_follow_the_paper_language(data_dir):
    from fastapi.testclient import TestClient
    from sqlalchemy import select

    from dayfold.app import app
    from dayfold.db import session_scope
    from dayfold.games.words import WORDLE
    from dayfold.models import Game
    from dayfold.settings import set_section

    with session_scope() as s:
        gid = s.scalar(select(Game.id).where(Game.kind == "wordle"))
        set_section(s, "newspaper", {"language": "en"})

    with TestClient(app) as c:
        # the seeded wordle config says "pt"; the paper decides what the preview shows
        preview = c.get(f"/api/games/{gid}/preview").json()
        assert preview["puzzle"]["language"] == "en"
        length = preview["puzzle"]["length"]
        assert preview["solution"]["answer"].lower() in WORDLE["en"][length]
        themes = c.get("/api/games").json()["schemas"]["wordsearch"]["theme"]
        assert themes[0] == "news"
        # every language's themes are offered: a game can be set to the other language
        assert {"animals", "animais"} <= set(themes)

    with session_scope() as s:
        set_section(s, "newspaper", {"language": "pt"})

    with TestClient(app) as c:
        assert c.get(f"/api/games/{gid}/preview").json()["puzzle"]["language"] == "pt"
        themes = c.get("/api/games").json()["schemas"]["wordsearch"]["theme"]
        assert "animais" in themes


def test_filtered_reasons_follow_the_language(monkeypatch):
    from dayfold.config import config
    from dayfold.pipeline.curate import skip_label

    monkeypatch.setattr(config, "language", "en")
    assert [skip_label(k) for k in ("language", "blocked", "no_section")] == \
        ["language", "blocked keyword", "no section"]
    assert skip_label("something_new") == "something_new"  # unknown keys stay readable

    monkeypatch.setattr(config, "language", "pt")
    assert [skip_label(k) for k in ("language", "blocked", "no_section")] == \
        ["idioma", "palavra bloqueada", "sem seção"]


def test_scraper_worker_runs_in_the_server_language(monkeypatch):
    from dayfold.config import config
    from dayfold.sources import runner

    monkeypatch.setattr(config, "language", "en")
    refused = runner.run_isolated("not-a-strategy", {})
    assert refused.ok is False and refused.error == "strategy not allowed: not-a-strategy"

    seen = {}

    def fake_run(cmd, **kwargs):
        seen.update(kwargs)
        raise runner.subprocess.TimeoutExpired(cmd, 1)

    monkeypatch.setattr(runner.subprocess, "run", fake_run)
    timed_out = runner.run_isolated("rss", {"feed_url": "https://example.test/feed"}, timeout=30)
    assert timed_out.error == "timed out (30s)"
    assert seen["env"]["DAYFOLD_LANGUAGE"] == "en"


def test_wordsearch_theme_label_follows_the_paper_language():
    from dayfold.games.generators import seeded, wordsearch

    # With headlines: the label names today's news in the paper's language.
    en, _ = wordsearch(seeded("w", "ws"), "en", 12, "news", 10,
                       ["Security officials testify following the Wisconsin election"])
    pt, _ = wordsearch(seeded("w", "ws"), "pt", 12, "news", 10,
                       ["Autoridades depõem sobre a eleição no Wisconsin"])
    assert en["theme"] == "Today's news"
    assert pt["theme"] == "Notícias do dia"

    # Without headlines a theme is drawn from the paper's own list, and labelled in its language.
    empty_en, _ = wordsearch(seeded("w", "ws"), "en", 12, "news", 10, [])
    empty_pt, _ = wordsearch(seeded("w", "ws"), "pt", 12, "news", 10, [])
    assert empty_en["theme"] in {"Animals", "Nature", "Space", "City", "Kitchen"}
    assert empty_pt["theme"] in {"Animais", "Natureza", "Espaço", "Cidade", "Cozinha"}


def test_games_list_survives_an_unknown_kind(data_dir):
    from fastapi.testclient import TestClient

    from dayfold.app import app
    from dayfold.db import session_scope
    from dayfold.models import Game

    with session_scope() as s:
        s.add(Game(kind="cryptogram", name="Criptograma", enabled=False, position=9,
                   config={"language": "pt"}))

    with TestClient(app) as c:
        r = c.get("/api/games")
        assert r.status_code == 200, r.text
        unknown = next(g for g in r.json()["games"] if g["kind"] == "cryptogram")
        assert unknown["config"] == {"language": "pt"}  # nothing to validate against: as stored

        # and saving one is a bad request, not a crash
        r = c.put(f"/api/games/{unknown['id']}", json={"enabled": True, "config": {}})
        assert r.status_code == 400, r.text
        assert "cryptogram" in r.json()["detail"]


def test_saving_a_game_keeps_its_options_and_ignores_unknown_ones(data_dir):
    from fastapi.testclient import TestClient
    from sqlalchemy import select

    from dayfold.app import app
    from dayfold.db import session_scope
    from dayfold.models import Game
    from dayfold.settings import set_section

    with session_scope() as s:
        set_section(s, "newspaper", {"language": "en"})
        wordle = s.scalar(select(Game).where(Game.kind == "wordle"))
        search = s.scalar(select(Game).where(Game.kind == "wordsearch"))
        wordle_id, search_id = wordle.id, search.id
        wordle.config = {**wordle.config, "language": "pt"}  # chosen on the Games page

    with TestClient(app) as c:
        # an explicit language survives a save that does not mention it
        r = c.put(f"/api/games/{wordle_id}", json={"enabled": True,
                                                    "config": {"length": 5, "attempts": 6}})
        assert r.status_code == 200, r.text
        cfg = r.json()["config"]
        assert (cfg["language"], cfg["length"], cfg["attempts"]) == ("pt", 5, 6)

        # an option this version does not know is dropped instead of stored
        r = c.put(f"/api/games/{search_id}", json={"enabled": True,
                                                    "config": {"size": 12, "words": 10,
                                                               "theme": "animals",
                                                               "difficulty": "medium", "bogus": 1}})
        cfg = r.json()["config"]
        assert (cfg["size"], cfg["words"], cfg["theme"], cfg["difficulty"]) == (12, 10, "animals", "medium")
        assert "bogus" not in cfg

    with session_scope() as s:
        assert s.get(Game, wordle_id).config["language"] == "pt"
        assert "bogus" not in s.get(Game, search_id).config


def test_backend_strings_follow_the_language(data_dir, monkeypatch):
    from fastapi.testclient import TestClient

    from dayfold.app import app
    from dayfold.config import config

    # Only the queued log line matters here: keep the worker from running a real generation
    # (and reaching the network) during the test.
    monkeypatch.setattr("dayfold.app.start_worker", lambda: None)
    monkeypatch.setattr("dayfold.app.stop_worker", lambda: None)

    monkeypatch.setattr(config, "language", "en")
    with TestClient(app) as c:
        assert c.get("/api/editions/999").json()["detail"] == "edition not found"
        # the dashboard starts in this language when the operator never picked one
        assert c.get("/api/auth/status").json()["language"] == "en"
        job_id = c.post("/api/generate").json()["job_id"]
        assert c.get(f"/api/jobs/{job_id}").json()["log"][0] == "Generation requested (manual)."
        assert c.get("/api/scraper-jobs/999999").json()["detail"] == "job not found"
        fonts = c.get("/api/settings").json()["meta"]["masthead_fonts"]
        assert fonts[0]["label"] == "Chomsky (classic blackletter)"

    monkeypatch.setattr(config, "language", "pt")
    with TestClient(app) as c:
        assert c.get("/api/editions/999").json()["detail"] == "edição não encontrada"
        assert c.get("/api/auth/status").json()["language"] == "pt"
        fonts = c.get("/api/settings").json()["meta"]["masthead_fonts"]
        assert fonts[0]["label"] == "Chomsky (blackletter clássico)"

ARTICLES = [("nasa", "Telescope maps the edge of the solar system"),
            ("agencia-brasil", "Libraries open on Saturdays"),
            ("who-news", "Vaccination campaign reaches remote villages")]


def test_new_install_prints_an_english_edition(data_dir, monkeypatch):
    epub = generate(monkeypatch, ARTICLES, games_per_edition=3, language="en")
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


def test_language_filter_names_the_provider_it_dropped(data_dir):
    """A provider marked with the wrong language empties the paper; the log must say which one."""
    from sqlalchemy import select

    from dayfold.db import session_scope
    from dayfold.models import Article, Provider
    from dayfold.pipeline.curate import candidates, skip_label
    from dayfold.settings import get_section, set_section

    with session_scope() as s:
        set_section(s, "curation", {"languages": ["en"]})
        add_article(s, "nasa", "Rocket launch to the Moon with astronauts")
        provider = s.scalar(select(Provider).where(Provider.slug == "nasa"))
        assert provider is not None
        provider.language = "pt"  # an English feed marked Portuguese
        for article in s.scalars(select(Article)):
            article.language = "pt"

    logs: list[str] = []
    with session_scope() as s:
        assert candidates(s, get_section(s, "curation"), logs.append) == []
    assert any(skip_label("language") in line and "NASA" in line for line in logs), logs


def test_disabling_a_provider_removes_its_stored_stories(data_dir):
    """A source switched off must not keep printing from what it collected earlier."""
    from sqlalchemy import select

    from dayfold.db import session_scope
    from dayfold.models import Provider
    from dayfold.pipeline.curate import candidates
    from dayfold.settings import get_section

    with session_scope() as s:
        add_article(s, "nasa", "Rocket launch to the Moon with astronauts")
    with session_scope() as s:
        assert len(candidates(s, get_section(s, "curation"), lambda m: None)) == 1
        s.scalar(select(Provider).where(Provider.slug == "nasa")).enabled = False
    with session_scope() as s:
        assert candidates(s, get_section(s, "curation"), lambda m: None) == []
