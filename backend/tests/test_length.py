from types import SimpleNamespace as NS

from edition_helpers import epub_text, generate

from dayfold.edition.length import Limits, cap, resolve

PARAS = [
    "One two three four five six seven eight nine ten.",          # 10 words
    "First sentence has five words. Second sentence is here too. Third one closes it.",  # 14
    "Last paragraph with a few more words in it.",                # 9
]


def test_no_limit_keeps_everything():
    assert cap(PARAS, Limits()) == (PARAS, False)
    assert cap(PARAS, Limits(words=1000, paragraphs=10)) == (PARAS, False)


def test_paragraph_limit():
    assert cap(PARAS, Limits(paragraphs=2)) == (PARAS[:2], True)


def test_word_limit_keeps_whole_paragraphs_and_skips_tiny_tails():
    out, cut = cap(PARAS, Limits(words=24))
    assert out == PARAS[:2] and cut  # 24 words: two paragraphs, 0 left for the third


def test_word_limit_cuts_the_first_paragraph_at_a_sentence():
    out, cut = cap(PARAS[1:], Limits(words=11))
    assert out == ["First sentence has five words. Second sentence is here too."] and cut


def test_word_limit_without_sentence_end_uses_ellipsis():
    out, cut = cap(["alpha beta gamma delta epsilon"], Limits(words=3))
    assert out == ["alpha beta gamma…"] and cut


def test_partial_paragraph_when_enough_budget_is_left():
    long = " ".join(f"Sentence {i} has exactly six words." for i in range(10))  # 60 words
    out, cut = cap(["Intro of four words.", long], Limits(words=40))
    assert len(out) == 2 and cut
    assert len(out[1].split()) == 36 and out[1].endswith(".")


def test_most_specific_limit_wins_per_kind():
    paper = NS(article_max_words=800, article_max_paragraphs=12)
    section = NS(max_words=None, max_paragraphs=6)
    provider = NS(max_words=300, max_paragraphs=None)
    assert resolve(provider, section, paper) == Limits(300, 6)
    assert resolve(None, None, paper) == Limits(800, 12)
    assert resolve(NS(max_words=None, max_paragraphs=None), None, NS(article_max_words=None,
                                                                   article_max_paragraphs=None)) == Limits()


def test_edition_caps_stories_and_links_the_rest(data_dir, monkeypatch):
    from sqlalchemy import select

    from dayfold.db import session_scope
    from dayfold.models import Provider

    with session_scope() as s:
        s.scalar(select(Provider).where(Provider.slug == "nasa")).max_paragraphs = 2
    text = epub_text(generate(monkeypatch, [("nasa", "Long mission story"), ("who-news", "Full story")],
                              article_max_words=5000, language="en"))  # English labels below
    assert "Paragraph 2 of the long story" in text
    assert "Paragraph 3 of the long story" in text  # the WHO story is not capped
    assert text.count("The story continues online") == 1
    assert text.count("Read the full story at the source") == 1


def test_api_keeps_caps_when_a_client_does_not_send_them(data_dir):
    from fastapi.testclient import TestClient

    from dayfold.app import app

    c = TestClient(app)
    tp = c.get("/api/topics").json()[0]
    body = {k: tp[k] for k in ("slug", "name", "keywords", "weight", "enabled", "max_articles")}
    assert c.put(f"/api/topics/{tp['id']}", json={**body, "max_words": 400}).json()["max_words"] == 400
    assert c.put(f"/api/topics/{tp['id']}", json=body).json()["max_words"] == 400
    assert c.put(f"/api/topics/{tp['id']}", json={**body, "max_words": None}).json()["max_words"] is None
    p = c.get("/api/providers").json()[0]
    pbody = {k: p[k] for k in ("name", "base_url", "categories", "language", "usage_mode", "license_name",
                               "license_url", "license_note", "enabled", "max_items")}
    assert c.put(f"/api/providers/{p['id']}", json={**pbody, "max_paragraphs": 5}).json()["max_paragraphs"] == 5
    assert c.put(f"/api/providers/{p['id']}", json=pbody).json()["max_paragraphs"] == 5
    assert c.put("/api/settings/newspaper", json={"article_max_words": 600}).status_code == 200
    assert c.get("/api/settings").json()["values"]["newspaper"]["article_max_words"] == 600
