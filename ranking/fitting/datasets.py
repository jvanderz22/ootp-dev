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

from ranking.fitting.stats import baserunning_runs, load_batting, load_fielding, load_pitching

PITCHER_POSITIONS = ("SP", "RP", "CL")
# snapshot column -> talent rating, current ratings
HITTING_COLUMNS = {"BABIP": "babip", "K's": "avoid_k", "GAP": "gap", "POW": "power", "EYE": "eye"}
PITCHING_COLUMNS = {"STU": "stuff", "CONT": "control", "HRA": "hra", "PBABIP": "pbabip", "MOV": "movement"}
# named as GamePlayer names them (one value each: there's no potential side)
FIELDING_COLUMNS = {
    "C ARM": "c_arm", "C ABI": "c_blocking", "C FRM": "c_framing",
    "IF RNG": "if_range", "IF ARM": "if_arm", "IF ERR": "if_error", "TDP": "turn_dp",
    "OF RNG": "of_range", "OF ARM": "of_arm", "OF ERR": "of_error",
}
RUNNING_COLUMNS = {"SPE": "speed", "STE": "steal", "RUN": "running_ability"}
MIN_INNINGS = 50
# A veteran's ratings barely move in a year, so a snapshot also stands in for
# his season before.
VETERAN_AGE = 29
# Younger players improve during a season, so their stats came from lower
# ratings than the snapshot shows - which flattens the low end of every curve.
# Season-start snapshots (archived from in-game April 8) will shrink this.
MIN_AGE = 24
MIN_PA = 50
# a pitcher's line at a level is a starter's if he started at least this share
# of his games there
STARTER_SHARE = 0.5

COUNTS = ("pa", "k", "bb", "contact", "hr", "in_play", "hits_in_play", "extra_base", "single",
          "double", "triple", "out")
PITCHING_COUNTS = ("bf", "k", "bb", "contact", "hr", "in_play", "hits_in_play", "g", "gs", "r")


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


def _read(path, pitchers, columns) -> pd.DataFrame:
    snap = pd.read_csv(path, low_memory=False)
    snap = snap[snap.POS.isin(PITCHER_POSITIONS) == pitchers]
    snap = snap.rename(columns={**columns, "ID": "player_id", "Age": "age"})
    snap = snap.dropna(subset=list(columns.values()))
    return snap[["player_id", "age", *columns.values()]].astype(int)


def read_hitters(path) -> pd.DataFrame:
    return _read(path, False, HITTING_COLUMNS)


def read_pitchers(path) -> pd.DataFrame:
    return _read(path, True, PITCHING_COLUMNS)


def read_fielders(path) -> pd.DataFrame:
    return _read(path, False, {**FIELDING_COLUMNS, **RUNNING_COLUMNS})


def _join(snapshots, lines, read, min_age, min_count, count) -> pd.DataFrame:
    """Each snapshot's players joined to their lines that season (and the
    season before, for veterans, when it has no snapshot of its own)."""
    frames = []
    for season, path in snapshots.items():
        players = read(path)
        years = (season,) if season - 1 in snapshots else (season, season - 1)
        for year in years:
            rows = lines[lines.year == year].merge(players, on="player_id")
            if year < season:
                rows = rows[rows.age >= VETERAN_AGE]
            frames.append(rows.assign(season=season))
    rows = pd.concat(frames, ignore_index=True)
    rows = rows[(rows.age >= min_age) & (rows[count] >= min_count)]
    return rows.reset_index(drop=True)


def _seasons(snapshots):
    return sorted({s for season in snapshots for s in (season, season - 1)})


def hitter_rows(snapshots: dict, stats_dir, min_age=MIN_AGE, min_pa=MIN_PA) -> pd.DataFrame:
    """Rating <-> stats rows for every snapshot season (and its season before,
    for veterans). `age` is the snapshot's age."""
    bat = load_batting(stats_dir, _seasons(snapshots))
    lines = bat.groupby(["player_id", "year", "level_id"])[list(COUNTS)].sum().reset_index()
    return _join(snapshots, lines, read_hitters, min_age, min_pa, "pa")


def pitcher_rows(snapshots: dict, stats_dir, min_age=MIN_AGE, min_bf=MIN_PA) -> pd.DataFrame:
    """The same for pitchers, with `sp` 1 for a starter's line, 0 a reliever's."""
    pit = load_pitching(stats_dir, _seasons(snapshots))
    lines = pit.groupby(["player_id", "year", "level_id"])[list(PITCHING_COUNTS)].sum().reset_index()
    lines["sp"] = (lines.gs >= STARTER_SHARE * lines.g).astype(int)
    return _join(snapshots, lines, read_pitchers, min_age, min_bf, "bf")


def fielding_rows(snapshots: dict, stats_dir, min_age=MIN_AGE, min_innings=MIN_INNINGS) -> pd.DataFrame:
    """Fielding runs (ranking.fitting.stats.load_fielding) per player, season,
    level and position, joined to the snapshot's fielding ratings."""
    field = load_fielding(stats_dir, _seasons(snapshots))
    lines = field.groupby(["player_id", "year", "level_id", "position"])[
        ["ip", "runs", "zr", "framing", "a", "e", "tc"]
    ].sum().reset_index()
    return _join(snapshots, lines, read_fielders, min_age, min_innings, "ip")


def running_rows(snapshots: dict, stats_dir, min_age=MIN_AGE, min_pa=MIN_PA) -> pd.DataFrame:
    """Baserunning runs (UBR plus steals) per player, season and level, joined
    to the snapshot's running ratings."""
    bat = load_batting(stats_dir, _seasons(snapshots))
    bat["baserunning"] = baserunning_runs(bat)
    lines = bat.groupby(["player_id", "year", "level_id"])[
        ["pa", "baserunning", "ubr", "sb", "cs", "single", "bb"]
    ].sum().reset_index()
    return _join(snapshots, lines, read_fielders, min_age, min_pa, "pa")
