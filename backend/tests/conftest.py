import os
import tempfile

import pytest

os.environ.setdefault("DAYFOLD_DISABLE_SCHEDULER", "1")


@pytest.fixture()
def data_dir(monkeypatch):
    from pathlib import Path

    from dayfold import db
    from dayfold.config import config

    with tempfile.TemporaryDirectory() as tmp:
        monkeypatch.setattr(config, "data_dir", Path(tmp))
        db.reset_engine()
        from dayfold.bootstrap import bootstrap

        bootstrap()
        yield Path(tmp)
        db.reset_engine()
