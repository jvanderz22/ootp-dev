"""Small filesystem helpers shared by the web layer and the CLI pipeline.

The app uses the filesystem as its datastore, so writes that a reader might
observe mid-flight (config.json, custom_ranking.json) go through an atomic
write-then-rename.
"""
import json
import os
import tempfile
from pathlib import Path


def atomic_write_text(path, text: str) -> None:
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, tmp = tempfile.mkstemp(dir=str(path.parent), prefix=f".{path.name}.", suffix=".tmp")
    try:
        with os.fdopen(fd, "w", newline="") as f:
            f.write(text)
        os.replace(tmp, str(path))
    except BaseException:
        try:
            os.unlink(tmp)
        except OSError:
            pass
        raise


def atomic_write_json(path, data) -> None:
    atomic_write_text(path, json.dumps(data, indent=4))
