"""DraftClassContext - the explicit replacement for the constants.DRAFT_CLASS_NAME global.

Every path the pipeline reads or writes is derived from a context instance:

    ctx = DraftClassContext("yfmlb-2042-draft")
    ctx.data_file          -> <base>/datasets/yfmlb-2042-draft.csv
    ctx.processed_dir      -> <base>/processed_classes/yfmlb-2042-draft
    ctx.eval_model_file(r) -> <base>/processed_classes/yfmlb-2042-draft/<Ranker>/eval_model.csv

`base_dir` defaults to $DATA_DIR (set in the container to the mounted volume) and
otherwise to the repo root, so the CLI keeps working unchanged.
"""
import json
import os
from dataclasses import dataclass, field
from pathlib import Path

from io_utils import atomic_write_json

_REPO_ROOT = Path(__file__).resolve().parent


def default_base_dir() -> Path:
    env = os.environ.get("DATA_DIR")
    return Path(env) if env else _REPO_ROOT


@dataclass
class DraftClassContext:
    name: str
    base_dir: Path = field(default_factory=default_base_dir)

    def __post_init__(self) -> None:
        self.base_dir = Path(self.base_dir)

    # --- directories -------------------------------------------------------
    @property
    def datasets_dir(self) -> Path:
        return self.base_dir / "datasets"

    @property
    def processed_dir(self) -> Path:
        return self.base_dir / "processed_classes" / self.name

    def ranker_dir(self, ranker) -> Path:
        ranker_name = ranker if isinstance(ranker, str) else ranker.__class__.__name__
        folder = self.processed_dir / ranker_name
        folder.mkdir(parents=True, exist_ok=True)
        return folder

    # --- files -----------------------------------------------------------
    @property
    def data_file(self) -> Path:
        return self.datasets_dir / f"{self.name}.csv"

    @property
    def config_file(self) -> Path:
        return self.processed_dir / "config.json"

    @property
    def upload_players_file(self) -> Path:
        return self.processed_dir / "upload_ranked_players.csv"

    @property
    def drafted_players_file(self) -> Path:
        return self.processed_dir / "drafted_players.csv"

    @property
    def custom_ranking_file(self) -> Path:
        return self.processed_dir / "custom_ranking.json"

    def eval_model_file(self, ranker) -> Path:
        return self.ranker_dir(ranker) / "eval_model.csv"

    def ranked_players_file(self, ranker) -> Path:
        return self.ranker_dir(ranker) / "ranked_players.csv"

    # --- config --------------------------------------------------------
    def load_config(self) -> dict:
        with open(self.config_file) as f:
            return json.load(f)

    def save_config(self, config: dict) -> None:
        atomic_write_json(self.config_file, config)

    @property
    def config(self) -> dict:
        return self.load_config()

    @property
    def ranking_method(self) -> str:
        return self.load_config().get("ranking_method", "draft_class")

    # --- helpers -----------------------------------------------------
    def exists(self) -> bool:
        return self.data_file.exists()

    def ensure_dirs(self) -> None:
        self.datasets_dir.mkdir(parents=True, exist_ok=True)
        self.processed_dir.mkdir(parents=True, exist_ok=True)

    @classmethod
    def list_classes(cls, base_dir=None) -> list[str]:
        base = Path(base_dir) if base_dir else default_base_dir()
        datasets = base / "datasets"
        if not datasets.is_dir():
            return []
        return sorted(p.stem for p in datasets.glob("*.csv"))
