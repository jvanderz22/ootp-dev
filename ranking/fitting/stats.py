"""Season batting stats from `league_stats/` (see league_stats.py), as event
counts, and the run value of each event fit from them."""
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


def load_batting(stats_dir, years) -> pd.DataFrame:
    """Every player-team stint of `years` at every level, overall split, with
    event counts added. Unintentional walks and HBP count as `bb`; intentional
    walks are left out, as the batter has no say in them."""
    frames = []
    for year in years:
        path = Path(stats_dir) / "bat" / f"{year}.csv"
        if path.exists():
            frames.append(pd.read_csv(path))
    if not frames:
        raise FileNotFoundError(f"no batting stats for {list(years)} under {stats_dir}")
    bat = pd.concat(frames, ignore_index=True)
    bat = bat[bat.split_id == OVERALL_SPLIT].copy()
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


def fit_linear_weights(bat: pd.DataFrame) -> dict:
    """Runs per event from team-season totals: team runs ~ event counts, no
    intercept, every level pooled."""
    teams = bat.groupby(["year", "team_id"])[list(EVENTS) + ["r", "pa"]].sum()
    teams = teams[teams.pa >= MIN_TEAM_PA]
    coef, *_ = np.linalg.lstsq(teams[list(EVENTS)].to_numpy(float), teams.r.to_numpy(float), rcond=None)
    return {name: float(c) for name, c in zip(EVENTS, coef)}


def runs(frame: pd.DataFrame, weights: dict) -> pd.Series:
    return sum(frame[name] * weights[name] for name in EVENTS)


def mlb_runs_per_pa(bat: pd.DataFrame, weights: dict, year: int) -> float:
    mlb = bat[(bat.year == year) & (bat.level_id == LEVEL_MLB)]
    return float(runs(mlb, weights).sum() / mlb.pa.sum())
