"""DAYFOLD_LANGUAGE picks the language of the server's own text (errors, labels, logs)."""


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
        assert paper["tagline"] == "Today's news, folded to read at your own pace."
        assert c.put("/api/settings/newspaper", json={**paper, "language": "pt"}).status_code == 200

    # An existing install keeps the language its operator chose.
    monkeypatch.setattr(config, "language", "en")
    with TestClient(app) as c:
        assert c.get("/api/settings").json()["values"]["newspaper"]["language"] == "pt"


def test_puzzles_and_their_titles_follow_the_paper_language():
    from dayfold.games.generators import seeded
    from dayfold.pipeline.generate import game_name, make_game

    # A per-game language stored in the dashboard must not leak into the paper.
    stored = make_game("wordle", {"language": "pt", "length": 5}, seeded("x", "wordle"), "en", [])
    plain = make_game("wordle", {"length": 5}, seeded("x", "wordle"), "en", [])
    assert stored == plain

    en = make_game("crossword", {}, seeded("y", "crossword"), "en", [])
    pt = make_game("crossword", {}, seeded("y", "crossword"), "pt", [])
    assert en != pt  # the puzzle really is built in the paper's language

    # Cover footer and job log use the same titles as the game page.
    assert game_name("en", "crossword", "Palavras Cruzadas") == "Crossword"
    assert game_name("pt", "crossword", "Palavras Cruzadas") == "Palavras Cruzadas"


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
        assert "animals" in themes and "animais" not in themes

    with session_scope() as s:
        set_section(s, "newspaper", {"language": "pt"})

    with TestClient(app) as c:
        assert c.get(f"/api/games/{gid}/preview").json()["puzzle"]["language"] == "pt"
        themes = c.get("/api/games").json()["schemas"]["wordsearch"]["theme"]
        assert "animais" in themes and "animals" not in themes


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


def test_saving_a_game_drops_retired_options_and_foreign_themes(data_dir):
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
        wordle.config = {**wordle.config, "language": "pt"}    # retired option
        search.config = {**search.config, "theme": "animais"}  # a Portuguese theme

    with TestClient(app) as c:
        games = {g["kind"]: g for g in c.get("/api/games").json()["games"]}
        assert "language" not in games["wordle"]["config"]
        assert games["wordsearch"]["config"]["theme"] == "news"

        r = c.put(f"/api/games/{wordle_id}", json={"enabled": True,
                                                    "config": {"length": 5, "attempts": 6}})
        assert r.status_code == 200, r.text
        assert r.json()["config"] == {"length": 5, "attempts": 6}

        # saving without a theme resets the one that belonged to the other language
        r = c.put(f"/api/games/{search_id}", json={"enabled": True,
                                                    "config": {"size": 12, "words": 10,
                                                               "difficulty": "medium"}})
        assert r.json()["config"]["theme"] == "news"

        # an English theme is accepted and stored
        r = c.put(f"/api/games/{search_id}", json={"enabled": True,
                                                    "config": {"size": 12, "words": 10,
                                                               "theme": "animals",
                                                               "difficulty": "medium"}})
        assert r.json()["config"]["theme"] == "animals"

    with session_scope() as s:
        assert "language" not in s.get(Game, wordle_id).config
        assert s.get(Game, search_id).config["theme"] == "animals"


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
