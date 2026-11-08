"""What produced a ranking: two runs with the same manifest are interchangeable."""
import hashlib
from functools import lru_cache
from pathlib import Path

# The legacy attribute models train from these at first use, relative to the
# working directory (see attribute_models/*.py).
TRAINING_DATA_DIR = Path("training_data")

ROOT = Path(__file__).resolve().parent.parent
# Everything that decides a score: the scoring packages' code (the fitting
# scripts aside), the fitted artifacts and the legacy grids. A stored run made
# with a different version is stale and gets re-scored on its next read, so a
# deploy that changes the model shows up without reprocessing anything.
MODEL_PACKAGES = ("attribute_models", "modifiers", "models", "rankers", "ranking", "scoring", "utils")
MODEL_DATA = ("ranking/artifacts/*.json", "training_data/*.csv")


@lru_cache(maxsize=None)
def _hash_dir(path: str) -> str:
    digest = hashlib.sha256()
    for file in sorted(Path(path).glob("*.csv")):
        digest.update(file.name.encode())
        digest.update(file.read_bytes())
    return digest.hexdigest()[:12]


@lru_cache(maxsize=None)
def model_version() -> str:
    files = [
        f for package in MODEL_PACKAGES for f in (ROOT / package).rglob("*.py")
        if "__pycache__" not in f.parts and "fitting" not in f.relative_to(ROOT).parts
    ]
    files += [f for pattern in MODEL_DATA for f in ROOT.glob(pattern)]
    digest = hashlib.sha256()
    for file in sorted(files):
        digest.update(str(file.relative_to(ROOT)).encode())
        digest.update(file.read_bytes())
    return digest.hexdigest()[:12]


def build_manifest(engine: str, pipeline: str, profile, unit: str, source_version=None, artifacts=None) -> dict:
    return {
        "engine": engine,
        "pipeline": pipeline,
        "profile": profile.name,
        "config_hash": profile.config_hash(),
        "unit": unit,
        "training_data_hash": _hash_dir(str(TRAINING_DATA_DIR)),
        # stage -> the fitted artifact (ranking/artifacts/) it scored with
        "artifact_versions": artifacts or {},
        "source_version": source_version,
    }
