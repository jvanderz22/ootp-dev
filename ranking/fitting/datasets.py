"""Training rows: a season's ratings snapshot joined to that season's stats.

Ratings come from the season archive (`league_snapshots/<league>/archive/
<season>.csv.gz`, see league_snapshot.archive_season_snapshot), or any
snapshot CSV named for a season. Only snapshots that carry BABIP are usable.

One row per player, season and level: a player's stints at one level are
summed, and his levels kept apart, because the level is part of what produced
the line.
"""
from pathlib import Path

import pandas as pd

from ranking.fitting.stats import load_batting

PITCHER_POSITIONS = ("SP", "RP", "CL")
# snapshot column -> talent rating, current ratings
HITTING_COLUMNS = {"BABIP": "babip", "K's": "avoid_k", "GAP": "gap", "POW": "power", "EYE": "eye"}
# A veteran's ratings barely move in a year, so a snapshot also stands in for
# his season before.
VETERAN_AGE = 29
# Younger players improve during a season, so their stats came from lower
# ratings than the snapshot shows - which flattens the low end of every curve.
# Season-start snapshots (archived from in-game April 8) will shrink this.
MIN_AGE = 24
MIN_PA = 50

COUNTS = ("pa", "k", "bb", "contact", "hr", "in_play", "hits_in_play", "extra_base", "single",
          "double", "triple", "out")


def season_snapshots(snapshot_dir, extra=None) -> dict:
    """{season: path} for the archived snapshots under `snapshot_dir` that have
    BABIP, plus `extra` ({season: path}), which wins."""
    found = {}
    for path in sorted((Path(snapshot_dir) / "archive").glob("*.csv.gz")):
        header = pd.read_csv(path, nrows=0).columns
        if "BABIP" in header:
            found[int(path.name.split(".")[0])] = path
    found.update({int(s): Path(p) for s, p in (extra or {}).items()})
    return found


def read_hitters(path) -> pd.DataFrame:
    snap = pd.read_csv(path, low_memory=False)
    snap = snap[~snap.POS.isin(PITCHER_POSITIONS)]
    snap = snap.rename(columns={**HITTING_COLUMNS, "ID": "player_id", "Age": "age"})
    snap = snap.dropna(subset=list(HITTING_COLUMNS.values()))
    return snap[["player_id", "age", *HITTING_COLUMNS.values()]].astype(int)


def hitter_rows(snapshots: dict, stats_dir, min_age=MIN_AGE, min_pa=MIN_PA) -> pd.DataFrame:
    """Rating <-> stats rows for every snapshot season (and its season before,
    for veterans). `age` is the snapshot's age."""
    seasons = sorted({s for season in snapshots for s in (season, season - 1)})
    bat = load_batting(stats_dir, seasons)
    lines = bat.groupby(["player_id", "year", "level_id"])[list(COUNTS)].sum().reset_index()
    frames = []
    for season, path in snapshots.items():
        hitters = read_hitters(path)
        # the season before only when it has no snapshot of its own
        years = (season,) if season - 1 in snapshots else (season, season - 1)
        for year in years:
            rows = lines[lines.year == year].merge(hitters, on="player_id")
            if year < season:
                rows = rows[rows.age >= VETERAN_AGE]
            frames.append(rows.assign(season=season))
    rows = pd.concat(frames, ignore_index=True)
    rows = rows[(rows.age >= min_age) & (rows.pa >= min_pa)]
    return rows.reset_index(drop=True)
