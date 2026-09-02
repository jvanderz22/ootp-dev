import csv
import getopt
import os
import sys

import pandas as pd
from bs4 import BeautifulSoup

from context import DraftClassContext
from io_utils import atomic_write_json

DEFAULT_CONFIG = {"ranking_method": "draft_class", "print_method": "draft_prospects"}
VALID_RANKING_METHODS = ("draft_class", "potential", "overall")

# Columns without which the ranking pipeline can't produce anything meaningful.
REQUIRED_HEADERS = ("ID", "POS", "Name")

# Some OOTP exports label the pitcher-control columns so they collide with the
# batter "CON" column (and duplicate "CONT P"); the CSV writer then de-dupes
# them by suffixing "_1". Map those back to the names the ranking pipeline and
# models/game_players.py expect.
HEADER_ALIASES = {
    "CON_1": "CONT",
    "CONT P_1": "CONT P",
}


class DatasetFormatError(ValueError):
    """The uploaded file isn't a usable OOTP scouting export."""


def create_csv(file_path, draft_class_path):
    """Parse an OOTP HTML scouting report into the dataset CSV shape."""
    header = []
    data = []
    soup = BeautifulSoup(open(file_path), "html.parser")
    table = soup.find_all("table")[0].find_all("tr")[1].find("table")
    header_row = table.find("tr")

    for th in header_row.find_all("th"):
        try:
            header.append(th.get_text())
        except Exception:
            continue

    for table_row in table.find_all("tr")[1:]:
        row_data = []
        for td in table_row.find_all("td"):
            try:
                row_data.append(td.get_text())
            except Exception:
                continue
        data.append([cell.strip() for cell in row_data])

    pd.DataFrame(data=data, columns=header).to_csv(draft_class_path)


def _looks_like_html(path) -> bool:
    with open(path, "rb") as f:
        head = f.read(4096).lstrip().lower()
    return head.startswith(b"<") or b"<table" in head or b"<html" in head


def _normalize_headers(data_file) -> None:
    """Rewrite known aliased column names (see HEADER_ALIASES) to their canonical
    form, in place. Only renames when the canonical column isn't already present,
    so a well-formed export is left untouched."""
    with open(data_file, newline="") as f:
        rows = list(csv.reader(f))
    if not rows:
        return
    header = rows[0]
    present = {h.strip() for h in header}
    changed = False
    for i, col in enumerate(header):
        target = HEADER_ALIASES.get(col.strip())
        if target and target not in present:
            header[i] = target
            present.add(target)
            changed = True
    if not changed:
        return
    tmp = f"{data_file}.norm"
    with open(tmp, "w", newline="") as f:
        csv.writer(f).writerows(rows)
    os.replace(tmp, data_file)


def _validate_headers(data_file) -> None:
    with open(data_file, newline="") as f:
        header = next(csv.reader(f), [])
    present = {h.strip() for h in header}
    missing = [h for h in REQUIRED_HEADERS if h not in present]
    if missing:
        raise DatasetFormatError(
            "The upload is missing required column(s): "
            + ", ".join(missing)
            + ". Use an OOTP player/scouting export that includes the ratings grid."
        )


def create_dataset_from_upload(name, upload_path, ranking_method="draft_class", base_dir=None):
    """Build datasets/<name>.csv + processed_classes/<name>/config.json from an
    uploaded file - either an OOTP HTML report or an already-converted CSV."""
    if ranking_method not in VALID_RANKING_METHODS:
        raise ValueError(f"Unknown ranking_method: {ranking_method!r}")

    ctx = DraftClassContext(name, base_dir=base_dir) if base_dir else DraftClassContext(name)
    ctx.ensure_dirs()

    # write to a staging file first so a bad upload never leaves a half-made class
    staged = ctx.data_file.with_suffix(".csv.incoming")
    try:
        if _looks_like_html(upload_path):
            try:
                create_csv(upload_path, str(staged))
            except (IndexError, AttributeError, ValueError) as exc:
                raise DatasetFormatError(
                    "Could not parse this HTML file as an OOTP scouting report. "
                    "Export the draft class as an HTML report (or upload the "
                    "converted CSV)."
                ) from exc
        else:
            with open(upload_path, "rb") as src, open(staged, "wb") as dst:
                dst.write(src.read())

        _normalize_headers(staged)
        _validate_headers(staged)
        os.replace(staged, ctx.data_file)
    finally:
        if staged.exists():
            staged.unlink()

    config = dict(DEFAULT_CONFIG)
    if ctx.config_file.exists():
        try:
            config.update(ctx.load_config())
        except Exception:
            pass
    config["ranking_method"] = ranking_method
    atomic_write_json(ctx.config_file, config)
    return ctx


def create_dataset(file_path, class_name):
    """Legacy CLI helper: HTML file -> dataset + default config."""
    ctx = DraftClassContext(class_name)
    ctx.ensure_dirs()
    create_csv(file_path, str(ctx.data_file))
    if not ctx.config_file.exists():
        atomic_write_json(ctx.config_file, dict(DEFAULT_CONFIG))
        print(f'Created class at {ctx.data_file}.')
    else:
        print(f'Updated class at {ctx.data_file}.')
    print(f"Set DRAFT_CLASS_NAME = {class_name!r} in constants.py to process it.")
    print(f"Settings can be updated in {ctx.config_file}.")


if __name__ == "__main__":
    class_name = None
    file_name = None
    try:
        opts, args = getopt.getopt(sys.argv[1:], "f:c:")
    except getopt.GetoptError:
        print("Invalid Option!")
        sys.exit(2)
    for opt, arg in opts:
        if opt == "-f":
            file_name = arg
        if opt == "-c":
            class_name = arg
    if class_name is None:
        print("Class name (-c) not specified.")
        sys.exit(2)
    if file_name is None:
        print("File name (-f) not specified.")
        sys.exit(2)

    file_name = file_name.replace("%20", " ")
    create_dataset(file_name, class_name)
