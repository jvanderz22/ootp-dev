"""The image copies its backend packages one by one - a new package left out of
the Dockerfile only shows up in prod, as a ModuleNotFoundError."""
import re
from pathlib import Path

ROOT = Path(__file__).parent.parent
NOT_SHIPPED = {"tests"}


def test_every_backend_package_is_copied_into_the_image():
    copied = set(re.findall(r"^COPY (\w+)/ \./\1/$", (ROOT / "Dockerfile").read_text(), re.M))
    packages = {p.parent.name for p in ROOT.glob("*/*.py") if not p.parent.name.startswith(("activate", "."))}
    assert packages - NOT_SHIPPED - copied == set()
