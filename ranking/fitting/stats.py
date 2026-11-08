"""Season stats from `league_stats/` (see league_stats.py), as event counts, and
the run value of each event fit from the batting side."""
from pathlib import Path

import numpy as np
import pandas as pd

OVERALL_SPLIT = 1
# team-seasons with fewer PA (partial or short-season teams) are left out of
# the linear-weights fit
MIN_TEAM_PA = 3000
LEVEL_MLB = 1

# the events a PA ends in, as `ranking.hitter_talent.outcomes` names them
EVENTS = ("single", "double", "triple", "hr", "bb", "k", "out")


def _load(stats_dir, kind, years) -> pd.DataFrame:
    frames = []
    for year in years:
        path = Path(stats_dir) / kind / f"{year}.csv"
        if path.exists():
            frames.append(pd.read_csv(path))
    if not frames:
        raise FileNotFoundError(f"no {kind} stats for {list(years)} under {stats_dir}")
    stats = pd.concat(frames, ignore_index=True)
    return stats[stats.split_id == OVERALL_SPLIT].copy()


def load_batting(stats_dir, years) -> pd.DataFrame:
    """Every player-team stint of `years` at every level, overall split, with
    event counts added. Unintentional walks and HBP count as `bb`; intentional
    walks are left out, as the batter has no say in them."""
    bat = _load(stats_dir, "bat", years)
    bat["single"] = bat.h - bat.d - bat.t - bat.hr
    bat["double"] = bat.d
    bat["triple"] = bat.t
    bat["bb"] = bat.bb - bat.ibb + bat.hp
    bat["out"] = bat.ab - bat.h - bat.k
    # balls put in play or over the fence, and those that stayed in the park
    bat["contact"] = bat.pa - bat.k - bat.bb - bat.ibb
    bat["in_play"] = bat.contact - bat.hr
    bat["hits_in_play"] = bat.h - bat.hr
    bat["extra_base"] = bat.d + bat.t
    return bat


def load_pitching(stats_dir, years) -> pd.DataFrame:
    """The pitching side of the same events, per stint. StatsPlus has no
    doubles / triples allowed, so there's no extra-base split."""
    pit = _load(stats_dir, "pitch", years)
    pit["bb"] = pit.bb - pit.iw + pit.hp
    pit["contact"] = pit.bf - pit.k - pit.bb - pit.iw
    pit["hr"] = pit.hra
    pit["in_play"] = pit.contact - pit.hr
    pit["hits_in_play"] = pit.ha - pit.hra
    return pit


def fit_linear_weights(bat: pd.DataFrame) -> dict:
    """Runs per event from team-season totals: team runs ~ event counts, no
    intercept, every level pooled."""
    teams = bat.groupby(["year", "team_id"])[list(EVENTS) + ["r", "pa"]].sum()
    teams = teams[teams.pa >= MIN_TEAM_PA]
    coef, *_ = np.linalg.lstsq(teams[list(EVENTS)].to_numpy(float), teams.r.to_numpy(float), rcond=None)
    return {name: float(c) for name, c in zip(EVENTS, coef)}


def runs(frame: pd.DataFrame, weights: dict) -> pd.Series:
    return sum(frame[name] * weights[name] for name in EVENTS)


def extra_base_shares(bat: pd.DataFrame, years) -> tuple:
    """MLB (extra-base hits per non-HR hit, triples per extra-base hit) over
    `years` - what a pitcher's hits are split by, lacking his own."""
    mlb = bat[bat.year.isin(list(years)) & (bat.level_id == LEVEL_MLB)]
    extra = mlb.double.sum() + mlb.triple.sum()
    return float(extra / mlb.hits_in_play.sum()), float(mlb.triple.sum() / extra)


def mlb_era(stats_dir, year: int) -> float:
    pit = _load(stats_dir, "pitch", [year])
    mlb = pit[pit.level_id == LEVEL_MLB]
    return float(27 * mlb.er.sum() / mlb.outs.sum())


def mlb_events_per_pa(bat: pd.DataFrame, year: int) -> dict:
    """The MLB average PA as `outcomes` gives one: event -> share of PA."""
    mlb = bat[(bat.year == year) & (bat.level_id == LEVEL_MLB)]
    return {name: float(mlb[name].sum() / mlb.pa.sum()) for name in EVENTS}


def mlb_runs_per_pa(bat: pd.DataFrame, weights: dict, year: int) -> float:
    mlb = bat[(bat.year == year) & (bat.level_id == LEVEL_MLB)]
    return float(runs(mlb, weights).sum() / mlb.pa.sum())
