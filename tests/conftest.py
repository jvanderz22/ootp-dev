import os
import shutil
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parent.parent
SAMPLE_DATASET = REPO_ROOT / "datasets" / "yfmlb-2042-draft.csv"


@pytest.fixture(autouse=True, scope="session")
def _never_the_repo_data_dir(tmp_path_factory):
    """Backstop: without DATA_DIR the app falls back to the repo root, so a test
    that forgets `data_dir` (or undoes its monkeypatch) would read and write the
    developer's real app.db. Point the whole session at a scratch directory."""
    previous = os.environ.get("DATA_DIR")
    os.environ["DATA_DIR"] = str(tmp_path_factory.mktemp("session-data"))
    yield
    if previous is None:
        os.environ.pop("DATA_DIR", None)
    else:
        os.environ["DATA_DIR"] = previous


@pytest.fixture
def data_dir(tmp_path, monkeypatch):
    """Isolated DATA_DIR (files + app.db) so tests never touch the real data."""
    monkeypatch.setenv("DATA_DIR", str(tmp_path))
    # context.default_base_dir() reads the env each call, nothing to reload
    _reset_process_state()
    yield tmp_path
    import db

    db.close_all()


def _reset_process_state():
    """Drop the in-process caches so one test's data can't leak into the next
    one's (they key on class / league names that tests reuse)."""
    from web import class_index, service

    class_index._cache.clear()
    service._league_payload_cache.clear()


@pytest.fixture
def sample_class(data_dir):
    if not SAMPLE_DATASET.exists():
        pytest.skip("sample dataset datasets/yfmlb-2042-draft.csv not present")
    name = "fixture"
    (data_dir / "datasets").mkdir(parents=True)
    (data_dir / "processed_classes" / name).mkdir(parents=True)
    shutil.copy(SAMPLE_DATASET, data_dir / "datasets" / f"{name}.csv")
    from context import DraftClassContext

    DraftClassContext(name).register("draft_class")
    return name


@pytest.fixture
def processed_class(sample_class):
    from context import DraftClassContext
    from pipeline import process_class

    ctx = DraftClassContext(sample_class)
    process_class(ctx)
    return ctx
