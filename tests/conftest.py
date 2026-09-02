import os
import shutil
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parent.parent
SAMPLE_DATASET = REPO_ROOT / "datasets" / "yfmlb-2042-draft.csv"


@pytest.fixture
def data_dir(tmp_path, monkeypatch):
    """Isolated DATA_DIR so tests never touch the real datasets/ tree."""
    monkeypatch.setenv("DATA_DIR", str(tmp_path))
    # context.default_base_dir() reads the env each call, nothing to reload
    return tmp_path


@pytest.fixture
def sample_class(data_dir):
    if not SAMPLE_DATASET.exists():
        pytest.skip("sample dataset datasets/yfmlb-2042-draft.csv not present")
    name = "fixture"
    (data_dir / "datasets").mkdir(parents=True)
    (data_dir / "processed_classes" / name).mkdir(parents=True)
    shutil.copy(SAMPLE_DATASET, data_dir / "datasets" / f"{name}.csv")
    (data_dir / "processed_classes" / name / "config.json").write_text(
        '{"ranking_method": "draft_class"}'
    )
    return name


@pytest.fixture
def processed_class(sample_class):
    from context import DraftClassContext
    from pipeline import process_class

    ctx = DraftClassContext(sample_class)
    process_class(ctx)
    return ctx
