"""End-to-end processing for one draft class, importable and context-driven.

    process_class(ctx)
      -> normalise the dataset CSV headers
      -> load GamePlayer rows
      -> rank with the class's method and store the run (results_store)
"""
import csv

import results_store
from context import DraftClassContext
from draft_class_files import get_draft_class_data_file
from models.game_players import GamePlayer
from rankers.get_ranker import get_ranker


# The pitching-control columns collide with the batting "CON" / "CON P" headers
# in an OOTP export. Older exports reuse those headers verbatim; newer ones
# duplicate them and the CSV writer de-dupes the second copy to "CON_1" /
# "CONT P_1". Either way we want them as "CONT" (current) and "CONT P" (potential).
_CONTROL_ALIASES = {
    "CON_1": "CONT",
    "CON P_1": "CONT P",
    "CONT P_1": "CONT P",
}


def normalise_dataset(ctx) -> None:
    """Rewrite the header row so the pitching-control columns read as
    "CONT" / "CONT P", regardless of which collision form the export used."""
    path = get_draft_class_data_file(ctx)
    with open(path, newline="") as f:
        rows = list(csv.reader(f))
    if not rows:
        return
    header = rows[0]
    original = list(header)

    def present():
        return {h.strip() for h in header}

    # Explicit de-duped aliases: "CON_1" -> "CONT", "CONT P_1" -> "CONT P", ...
    for i, col in enumerate(header):
        target = _CONTROL_ALIASES.get(col.strip())
        if target and target not in present():
            header[i] = target

    # Older form: the pitching block is STU, MOV, CON, STU P, MOV P, CON P - the
    # control columns sit right after MOV / MOV P and are still literally "CON".
    for anchor, target in (("MOV", "CONT"), ("MOV P", "CONT P")):
        if target in present():
            continue
        try:
            j = header.index(anchor) + 1
        except ValueError:
            continue
        if j < len(header) and header[j].strip() in ("CON", "CON P"):
            header[j] = target

    if header != original:
        with open(path, "w", newline="") as f:
            csv.writer(f).writerows(rows)


def load_player_data(ctx):
    """Yield GamePlayers lazily so the ranker can score in batches. The CSV rows
    are read up front (cheap) and the file closed; only GamePlayer construction
    is deferred."""
    with open(get_draft_class_data_file(ctx), newline="") as csvfile:
        rows = list(csv.DictReader(csvfile))
    return (GamePlayer(row) for row in rows)


def write_player_scores(ctx, players) -> None:
    from scoring.model_cache import HEAVY_SCORING_LOCK

    with HEAVY_SCORING_LOCK:
        _write_player_scores(ctx, players)


def _write_player_scores(ctx, players) -> None:
    scored = get_ranker(ctx).rank(players)
    results_store.save_run(
        results_store.CLASS,
        ctx.name,
        ctx.ranking_method,
        ctx.data_version,
        [results_store.result_from_scored(s) for s in scored],
    )


def process_class(ctx) -> None:
    ctx.ensure_dirs()
    normalise_dataset(ctx)
    players = load_player_data(ctx)
    write_player_scores(ctx, players)


if __name__ == "__main__":
    from constants import DRAFT_CLASS_NAME

    ctx = DraftClassContext(DRAFT_CLASS_NAME)
    print(f"Running evals for {DRAFT_CLASS_NAME}!")
    process_class(ctx)
