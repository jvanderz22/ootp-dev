"""DraftClassContext - the explicit replacement for the constants.DRAFT_CLASS_NAME global.

A class is a row in the `draft_classes` table (ranking method, league pin,
custom order, ...) plus its uploaded dataset file; its scored rankings live in
`results_store`:

    ctx = DraftClassContext("yfmlb-2042-draft")
    ctx.data_file          -> <base>/datasets/yfmlb-2042-draft.csv
    ctx.upload_players_file-> <base>/processed_classes/yfmlb-2042-draft/upload_ranked_players.csv
    ctx.ranking_method     -> draft_classes.ranking_method

Everything lives under $DATA_DIR (set in the container to the mounted volume),
otherwise the repo root, so the CLI keeps working unchanged. There is no per-
context override: the files and the database rows must stay in one place.
"""
import os
from dataclasses import dataclass
from pathlib import Path

import db

_REPO_ROOT = Path(__file__).resolve().parent

DEFAULT_RANKING_METHOD = "draft_class"
# the `draft_classes` columns a class config dict maps onto
_CONFIG_KEYS = ("ranking_method", "print_method", "league_id")


def default_base_dir() -> Path:
    env = os.environ.get("DATA_DIR")
    return Path(env) if env else _REPO_ROOT


class ClassNotRegistered(LookupError):
    pass


@dataclass
class DraftClassContext:
    name: str

    @property
    def base_dir(self) -> Path:
        return default_base_dir()

    # --- directories -------------------------------------------------------
    @property
    def datasets_dir(self) -> Path:
        return self.base_dir / "datasets"

    @property
    def processed_dir(self) -> Path:
        return self.base_dir / "processed_classes" / self.name

    # --- files -----------------------------------------------------------
    @property
    def data_file(self) -> Path:
        return self.datasets_dir / f"{self.name}.csv"

    @property
    def upload_players_file(self) -> Path:
        """The C+ preference-list export the CLI writes (ranking_csv.py)."""
        return self.processed_dir / "upload_ranked_players.csv"

    # --- config (the draft_classes row) ----------------------------------
    def load_config(self) -> dict:
        row = db.query_one(
            "SELECT ranking_method, print_method, league_id FROM draft_classes WHERE name = ?",
            (self.name,),
        )
        if row is None:
            raise ClassNotRegistered(f"Draft class {self.name!r} is not registered.")
        return dict(row)

    def save_config(self, config: dict) -> None:
        """Update the config columns present in `config` (others are kept)."""
        updates = {k: config[k] for k in _CONFIG_KEYS if k in config}
        if not updates:
            return
        sets = ", ".join(f"{k} = ?" for k in updates)
        with db.transaction() as conn:
            cur = conn.execute(
                f"UPDATE draft_classes SET {sets}, revision = revision + 1 WHERE name = ?",
                (*updates.values(), self.name),
            )
            if cur.rowcount == 0:
                raise ClassNotRegistered(f"Draft class {self.name!r} is not registered.")

    @property
    def config(self) -> dict:
        return self.load_config()

    @property
    def ranking_method(self) -> str:
        return self.load_config().get("ranking_method") or DEFAULT_RANKING_METHOD

    @property
    def data_version(self) -> int:
        """Bumped each time the dataset is (re)uploaded - a stored ranking is
        current only if it was scored from this version."""
        row = db.query_one("SELECT data_version FROM draft_classes WHERE name = ?", (self.name,))
        return row["data_version"] if row else 0

    @property
    def revision(self) -> int:
        """Bumped by every change to the class (config, data, custom order,
        drafted picks) - the cache key for anything built from it."""
        row = db.query_one("SELECT revision FROM draft_classes WHERE name = ?", (self.name,))
        return row["revision"] if row else 0

    def register(self, ranking_method=None) -> None:
        """Create the class row, or - for an existing class whose dataset was just
        replaced - bump its data version. `ranking_method`, if given, is set."""
        with db.transaction() as conn:
            conn.execute(
                "INSERT INTO draft_classes (name, ranking_method) VALUES (?, ?) "
                "ON CONFLICT(name) DO UPDATE SET data_version = data_version + 1, "
                "revision = revision + 1",
                (self.name, ranking_method or DEFAULT_RANKING_METHOD),
            )
            if ranking_method:
                conn.execute(
                    "UPDATE draft_classes SET ranking_method = ? WHERE name = ?",
                    (ranking_method, self.name),
                )

    def bump_revision(self) -> None:
        db.execute(
            "UPDATE draft_classes SET revision = revision + 1 WHERE name = ?", (self.name,)
        )

    def unregister(self) -> None:
        db.execute("DELETE FROM draft_classes WHERE name = ?", (self.name,))

    # --- helpers -----------------------------------------------------
    def exists(self) -> bool:
        return (
            db.query_one("SELECT 1 FROM draft_classes WHERE name = ?", (self.name,)) is not None
            and self.data_file.exists()
        )

    def ensure_dirs(self) -> None:
        self.datasets_dir.mkdir(parents=True, exist_ok=True)
        self.processed_dir.mkdir(parents=True, exist_ok=True)

    @classmethod
    def list_classes(cls) -> list[str]:
        return [row["name"] for row in db.query("SELECT name FROM draft_classes ORDER BY name")]
