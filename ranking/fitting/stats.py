"""Season stats from `league_stats/` (see league_stats.py), as event counts, and
the run value of each event fit from the batting side."""
from pathlib import Path

import numpy as np
import pandas as pd

OVERALL_SPLIT = 1
VS_LEFT_SPLIT, VS_RIGHT_SPLIT = 2, 3   # vs left- / right-handed opponents
# team-seasons with fewer PA (partial or short-season teams) are left out of
# the linear-weights fit
MIN_TEAM_PA = 3000
LEVEL_MLB = 1

# the events a PA ends in, as `ranking.hitter_talent.outcomes` names them
EVENTS = ("single", "double", "triple", "hr", "bb", "k", "out")


def _load(stats_dir, kind, years, split=OVERALL_SPLIT) -> pd.DataFrame:
    frames = []
    for year in years:
        path = Path(stats_dir) / kind / f"{year}.csv"
        if path.exists():
            frames.append(pd.read_csv(path))
    if not frames:
        raise FileNotFoundError(f"no {kind} stats for {list(years)} under {stats_dir}")
    stats = pd.concat(frames, ignore_index=True)
    return stats[stats.split_id == split].copy()


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


def batting_pa_by_side(stats_dir, years) -> pd.DataFrame:
    """Per batting stint: PA vs left (`pa_l`) and right (`pa_r`) -handed
    pitchers."""
    keys = ["player_id", "year", "team_id", "level_id", "stint"]
    out = None
    for split, name in ((VS_LEFT_SPLIT, "pa_l"), (VS_RIGHT_SPLIT, "pa_r")):
        side = _load(stats_dir, "bat", years, split)[keys + ["pa"]].rename(columns={"pa": name})
        out = side if out is None else out.merge(side, on=keys)
    return out


def pitching_bf_by_side(stats_dir, years) -> pd.DataFrame:
    """Per pitching stint: g, gs, and batters faced vs left (`bf_l`) and right
    (`bf_r`) -handed batters."""
    keys = ["player_id", "year", "team_id", "level_id", "stint"]
    out = _load(stats_dir, "pitch", years)[keys + ["g", "gs"]]
    for split, name in ((VS_LEFT_SPLIT, "bf_l"), (VS_RIGHT_SPLIT, "bf_r")):
        side = _load(stats_dir, "pitch", years, split)[keys + ["bf"]].rename(columns={"bf": name})
        out = out.merge(side, on=keys)
    return out


# StatsPlus field position number -> position
FIELD_POSITIONS = {2: "C", 3: "1B", 4: "2B", 5: "3B", 6: "SS", 7: "LF", 8: "CF", 9: "RF"}
# stolen base / caught stealing run values for baserunning runs (wSB-style)
SB_RUNS, CS_RUNS = 0.2, -0.4


def load_fielding(stats_dir, years) -> pd.DataFrame:
    """Fielding lines per stint and position, with `runs`: zone rating plus
    framing. Opportunity-driven counts are left out (decided 2026-11-08):
    StatsPlus's `arm` runs follow how many balls drop in front of an
    outfielder, not his arm (and are always 0 for catchers), and assists depend
    on chances. Arms come in through your position grids and floors."""
    frames = [pd.read_csv(Path(stats_dir) / "field" / f"{y}.csv")
              for y in years if (Path(stats_dir) / "field" / f"{y}.csv").exists()]
    field = pd.concat(frames, ignore_index=True)
    field = field[field.position.isin(list(FIELD_POSITIONS))].copy()
    field["position"] = field.position.map(FIELD_POSITIONS)
    field["runs"] = field.zr + field.framing
    return field


def baserunning_runs(bat: pd.DataFrame) -> pd.Series:
    return bat.ubr + SB_RUNS * bat.sb + CS_RUNS * bat.cs


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


SEASON_PA = 600
DH = "DH"


def hitter_seasons(stats_dir, years) -> pd.DataFrame:
    """MLB hitter seasons: PA, WAR, linear-weights runs (`lw`), the league's
    runs per PA, batting runs against it and baserunning runs."""
    bat = load_batting(stats_dir, years)
    weights = fit_linear_weights(bat)
    mlb = bat[bat.level_id == LEVEL_MLB].copy()
    mlb["lw"] = runs(mlb, weights)
    mlb["baserunning"] = baserunning_runs(mlb)
    league = mlb.groupby("year").apply(lambda g: g.lw.sum() / g.pa.sum()).rename("league")
    hitters = mlb.groupby(["player_id", "year"]).agg(
        pa=("pa", "sum"), lw=("lw", "sum"), war=("war", "sum"), baserunning=("baserunning", "sum"),
    ).reset_index().join(league, on="year")
    hitters["batting"] = hitters.lw - hitters.league * hitters.pa
    return hitters


def hitter_war(stats_dir, years) -> dict:
    """StatsPlus's MLB hitter WAR taken apart: WAR per batting run (linear
    weights against the league), per defense run (zone rating + framing + arm
    + baserunning, as StatsPlus counts them) and an allowance per SEASON_PA at
    the position he played most (DH when he never took the field)."""
    hitters = hitter_seasons(stats_dir, years)
    field = pd.concat(
        pd.read_csv(Path(stats_dir) / "field" / f"{y}.csv") for y in years
        if (Path(stats_dir) / "field" / f"{y}.csv").exists()
    )
    field = field[field.level_id == LEVEL_MLB]
    played = field.groupby(["player_id", "year"]).agg(
        fielding=("zr", "sum"), framing=("framing", "sum"), arm=("arm", "sum")).reset_index()
    main = field[field.position.isin(list(FIELD_POSITIONS))].sort_values("ip")
    main = main.groupby(["player_id", "year"]).tail(1)[["player_id", "year", "position"]]
    main["position"] = main.position.map(FIELD_POSITIONS)
    hitters = hitters.merge(played, on=["player_id", "year"], how="left").merge(
        main, on=["player_id", "year"], how="left")
    hitters = hitters[hitters.pa >= 100].fillna({"fielding": 0, "framing": 0, "arm": 0, "position": DH})
    # StatsPlus's WAR counts its arm runs, so the split has to as well
    hitters["defense"] = hitters.fielding + hitters.framing + hitters.arm + hitters.baserunning
    names = list(FIELD_POSITIONS.values()) + [DH]
    dummies = np.column_stack([(hitters.position == n) * hitters.pa for n in names])
    coef, *_ = np.linalg.lstsq(np.column_stack([hitters.batting, hitters.defense, dummies]), hitters.war, rcond=None)
    return {
        "per_batting_run": float(coef[0]),
        "per_defense_run": float(coef[1]),
        "allowance_600": {n: float(a * SEASON_PA) for n, a in zip(names, coef[2:])},
    }
