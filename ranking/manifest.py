"""What produced a ranking: two runs with the same manifest are interchangeable."""
import hashlib
from functools import lru_cache
from pathlib import Path

# The legacy attribute models train from these at first use, relative to the
# working directory (see attribute_models/*.py).
TRAINING_DATA_DIR = Path("training_data")


@lru_cache(maxsize=None)
def _hash_dir(path: str) -> str:
    digest = hashlib.sha256()
    for file in sorted(Path(path).glob("*.csv")):
        digest.update(file.name.encode())
        digest.update(file.read_bytes())
    return digest.hexdigest()[:12]


def build_manifest(engine: str, profile, unit: str, source_version=None) -> dict:
    return {
        "engine": engine,
        "profile": profile.name,
        "config_hash": profile.config_hash(),
        "unit": unit,
        "training_data_hash": _hash_dir(str(TRAINING_DATA_DIR)),
        # fitted artifacts (ranking/artifacts/) arrive with the first fitted stage
        "artifact_versions": {},
        "source_version": source_version,
    }
