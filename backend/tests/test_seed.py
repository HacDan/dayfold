"""Defaults are installed once per database; after that the lists the operator has curated win.

Deleting every section used to re-install the Portuguese defaults on the next restart, which
looked like the section names were hardcoded.
"""

from sqlalchemy import delete, func, select


def _count(session, model) -> int:
    return session.scalar(select(func.count(model.id))) or 0


def test_defaults_installed_on_first_run(data_dir):
    from dayfold.db import session_scope
    from dayfold.models import Setting, Topic
    from dayfold.seed import DEFAULT_TOPICS, SEED_KEY

    with session_scope() as s:
        assert _count(s, Topic) == len(DEFAULT_TOPICS)
        assert s.get(Setting, SEED_KEY).value["topics"] is True


def test_deleted_sections_stay_deleted(data_dir):
    from dayfold.db import session_scope
    from dayfold.models import Topic
    from dayfold.seed import seed

    with session_scope() as s:
        assert _count(s, Topic) > 0
        s.execute(delete(Topic))
    with session_scope() as s:
        seed(s)
        assert _count(s, Topic) == 0


def test_renamed_section_survives_reseed(data_dir):
    from dayfold.db import session_scope
    from dayfold.models import Topic
    from dayfold.seed import seed

    with session_scope() as s:
        topic = s.scalars(select(Topic).order_by(Topic.position)).first()
        slug, total = topic.slug, _count(s, Topic)
        topic.name = "Vermont"
    with session_scope() as s:
        seed(s)
        assert _count(s, Topic) == total
        assert s.scalars(select(Topic).where(Topic.slug == slug)).one().name == "Vermont"


def test_upgrade_marks_without_duplicating(data_dir):
    """A database that already has sections but no marker (older install) must not grow."""
    from dayfold.db import session_scope
    from dayfold.models import Setting, Topic
    from dayfold.seed import SEED_KEY, seed

    with session_scope() as s:
        s.execute(delete(Setting).where(Setting.key == SEED_KEY))
    with session_scope() as s:
        total = _count(s, Topic)
        seed(s)
        assert _count(s, Topic) == total
        assert s.get(Setting, SEED_KEY).value["topics"] is True
