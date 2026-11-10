"""The value layer (phase 5b): talent -> WAR at a full-time role, shown as points.

Every player is valued at a full-time role, not his expected playing time
(decided 2026-11-08): an everyday hitter, a starter at the innings his stamina
carries, or a reliever. Per-run and per-inning values are StatsPlus's own,
taken apart by ranking.fitting.value:

    hitter    per batting run x batting runs (wRC+ over a full season's PA)
              + per defense run x (fielding value with its position adjustment
              + baserunning runs) + the position-player allowance
    starter   per run x runs saved against the league ERA + per nine innings,
              over starts x innings a start by stamina, at the matchups
              lineups give him (`matchup_tilt`); he needs
              STARTER_MIN_STAMINA and STARTER_MIN_PITCHES
    reliever  the same over a reliever's innings, his runs saved counted at
              LEVERAGE_WEIGHT of the leverage his talent earns him (an optimal
              manager gives the best reliever the biggest spots), and at the
              matchups you'd give him (`matchup_tilt`)

Matchups follow a pitcher's split (2026-11-08): none for an even split,
MATCHUP_TILT of the batters moved at FULL_TILT_SPLIT (runs index, about the
95th percentile of the snapshot's pitchers) and above, a straight ramp
between. A reliever is used the way you use him, so they move to his strong
side; a starter can't pick his batters and lineups stack his weak side, so
they move there. A big split costs a starter what it earns a reliever, by
the innings each pitches - a set cost by split, not a share of his value -
and the better of the two roles moves a big-split starter to the bullpen
when that's worth more.

Each talent read is calibrated against what MLB regulars actually did
(`calibration`, fit by ranking.fitting.value on the snapshot's season):
actual = a + b x predicted, for wRC+, baserunning runs, and each role's ERA
(against FIP, which StatsPlus's WAR runs on). Fielding is calibrated within
each position, apart from the position's adjustment (2026-11-08): fielding
runs against an average fielder there = the position's level + one pooled
stretch x predicted. The adjustments themselves aren't refit to StatsPlus's
WAR: they come from where managers play regulars (ranking/fielding_talent.py,
2026-11-09); one line shared by every position puts runs plus adjustment
where regulars' WAR does (it spreads them ~0.76x as wide), the same stretch
everywhere so each player's best position stays his best. The talent models rank well but their spread was off - baserunning too wide,
pitchers too narrow and starters too optimistic. A starter's innings per start come from his stamina and how
efficient he is - his walks, strikeouts and home runs per PA (walks drive
pitches per inning): a stingy starter goes deeper than his stamina says.

A pitcher's value above replacement is floored on Control (decided
2026-11-08, your pitcher rule 5 back as a floor like the position floors):
full from CONTROL_FLOOR + FLOOR_RAMP, half at CONTROL_FLOOR, nothing a step
below it. MLB pitchers at Control 30 or less were below replacement in 2042
(-0.8 WAR per 100 IP); 31-35 barely above (+0.3), 36-40 +0.5. A floor at 35
zeroed a Control-30 prospect (Henry MacGregor, #63 -> #492), too much for a
potential rating, so it sits at 30: half value there (#232).

No extra weight on pitchers against hitters (your call, 2026-11-08): with
the tables' tails continued and starters' depth from their efficiency, Andy
Spinner is the best pitcher in the league and #2 overall on current ratings.

A two-way player gets his better side plus a share of the other side's WAR
above replacement (`two_way_share`): none while the other side is only
marginal (TWO_WAY_FLOOR WAR or less - a back-end starter, a bench bat), the
full TWO_WAY_SHARE from TWO_WAY_FULL WAR (about a league-average full-time
starter), and a straight ramp between. A decent batter shouldn't outrank
better batters for being a decent AAA pitcher.

On current ratings (the profile's `league_replacement`), replacement is the
league's own (decided 2026-11-10). StatsPlus's WAR sets replacement the MLB
way, which this league's depth leaves far below what's freely available: it
pays a starter ~0.12 WAR a nine innings just for pitching them, so a
league-average starter is ~2 WAR, and dozens of them sit in free agency.
Instead every team has the same spots - LINEUP_FULL everyday bats, then
bats LINEUP_FULL+1 to LINEUP at the share of a season such bats get,
ROTATION starters, and BULLPEN relievers at the leverage each bullpen spot
pitches in (`Replacement`) - and each spot has a price: what the league's
next-best player would add there, from assigning the league's players to
its spots for the most WAR (ranking.fitting.replacement). A side is valued
at the spot he's furthest above its price ("league replacement" in the
ledger, after "playing time" for a part-time bat). Leverage belongs to the
spot, not the pitcher: lose your closer and the setup man closes, so a
closer only earns his edge over the next arm at closer leverage, credited at
the share of leverage StatsPlus's WAR credits. His matchups are the spot's
too: the late-inning spots pitch to whoever's due, so a reliever moves
RELIEF_TILT of his batters to his strong side by his spot
(`Replacement.tilts`), in place of MATCHUP_TILT. In 2042 the league's
managers moved ~1% in spots 1-2, 5% in 3-4 and 6% in 5-8 at a full split
(the fit's "bullpen_tilt"); you pick pockets better than the AI, so yours
are higher. The modifiers and two-way ramp still read StatsPlus-scale WAR,
as they were set on it; they scale what's above the league's price.

On screen, `points` = 50 + 10 x WAR (50 = replacement).
"""
import json
from functools import lru_cache
from pathlib import Path

import numpy as np

from ranking.hitter_talent import ARTIFACTS_DIR

ARTIFACT = "value_v1"
# judgment (2026-11-08)
LEVERAGE_WEIGHT = 1.0   # full leverage, the most the stats support
TWO_WAY_SHARE = 0.2
TWO_WAY_FLOOR, TWO_WAY_FULL = 1.75, 2.5   # the other side's WAR
MATCHUP_TILT, FULL_TILT_SPLIT = 0.20, 20.0
CONTROL_FLOOR, FLOOR_RAMP = 30, 5
STARTER_MIN_STAMINA = 35   # borderline, at the bottom of the innings curve
STARTER_MIN_PITCHES = 3
DISPLAY_OFFSET, DISPLAY_SCALE = 50.0, 10.0
REPLACEMENT_ARTIFACT = "replacement_v1"
# judgment (2026-11-10): a team's spots - 7 everyday bats and 5 part-time
# ones, 5 starters, 8 relievers
LINEUP_FULL, LINEUP = 7, 12
ROTATION, BULLPEN = 5, 8
# judgment (2026-11-10): the share of a reliever's batters moved to his strong
# side at FULL_TILT_SPLIT, by bullpen spot - about twice what the league's
# managers got in the late innings, more where the matchups can be picked
RELIEF_TILT = (0.024, 0.024, 0.08, 0.08, 0.14, 0.14, 0.14, 0.14)
# the league the talent and value artifacts are fit on, for a class with none
DEFAULT_LEAGUE = "yfmlb"
# legacy modifiers the hitter platoons (ranking/stages/value.py) replace
PLATOON_REPLACES = ("BatterHandednessModifier",)


def points(war):
    return DISPLAY_OFFSET + DISPLAY_SCALE * np.asarray(war)


def control_floor(control) -> float:
    """The share of a pitcher's value above replacement his Control keeps."""
    ramp = (control - (CONTROL_FLOOR - FLOOR_RAMP)) / (2 * FLOOR_RAMP)
    return float(np.clip(ramp, 0.0, 1.0))


def two_way_share(other_war) -> float:
    """The share of his other side's WAR a two-way player is credited."""
    ramp = (other_war - TWO_WAY_FLOOR) / (TWO_WAY_FULL - TWO_WAY_FLOOR)
    return TWO_WAY_SHARE * float(np.clip(ramp, 0.0, 1.0))


def matchup_tilt(split) -> float:
    """The share of a pitcher's batters moved to his strong side (relieving) or
    his weak side (starting), for a split of `split` runs index (either
    direction)."""
    return MATCHUP_TILT * float(np.clip(abs(split) / FULL_TILT_SPLIT, 0.0, 1.0))


class ValueModel:
    def __init__(self, artifact: dict):
        self.version = artifact["version"]
        self.hitter = artifact["hitter"]
        self.pitcher = artifact["pitcher"]
        self.workloads = artifact["workloads"]
        self.leverage_map = artifact["leverage"]
        # {"wrc_plus" | "baserunning": [a, b], "era": {role: [a, b]},
        #  "fielding": {"per_run": b, "by_position": {position: a}, "value": [a, b]}}
        self.calibration = artifact.get("calibration")

    @classmethod
    def from_file(cls, path) -> "ValueModel":
        return cls(json.loads(Path(path).read_text()))

    @property
    def hitter_pa(self) -> float:
        return self.workloads["hitter_pa"]

    def hitting(self, batting_runs, fielding_value, baserunning_runs) -> dict:
        """WAR parts for a full season: batting runs over hitter_pa, fielding
        value a season with its position adjustment, baserunning runs over
        hitter_pa."""
        h, share = self.hitter, self.hitter_pa / 600
        return {
            "batting": h["per_batting_run"] * batting_runs,
            "fielding": h["per_defense_run"] * fielding_value,
            "running": h["per_defense_run"] * baserunning_runs,
            "allowance": h["allowance_600"] * share,
        }

    def calibrated(self, name, predicted, role=None):
        """`predicted` (wRC+, baserunning runs, or `role`'s ERA) on the scale
        MLB regulars actually played at."""
        fit = (self.calibration or {}).get(name)
        if fit is None:
            return predicted
        a, b = fit[role] if role else fit
        return a + b * np.asarray(predicted)

    def fielding_runs(self, runs, position) -> float:
        """Fielding runs against an average fielder at `position`, as MLB
        fielders there actually played to them."""
        fit = (self.calibration or {}).get("fielding")
        if fit is None:
            return runs
        return fit["by_position"][position] + fit["per_run"] * runs

    def fielding_value(self, runs, adjustment) -> float:
        """Calibrated fielding runs plus the position's adjustment, on the line
        MLB regulars' WAR puts them (the same stretch at every position)."""
        fit = ((self.calibration or {}).get("fielding") or {}).get("value")
        if fit is None:
            return runs + adjustment
        return fit[0] + fit[1] * (runs + adjustment)

    def starter_innings(self, stamina, pitches, rates=None) -> float:
        """A full-time starter's innings, from his stamina and his starter
        `rates` ({"k" | "bb" | "hr": per PA}; league-typical when None), or 0
        when he can't start."""
        if stamina < STARTER_MIN_STAMINA or pitches < STARTER_MIN_PITCHES:
            return 0.0
        per_start = self.workloads["ip_per_start"]
        ip = per_start["intercept"] + per_start["per_stamina"] * stamina
        for event, per in per_start.get("per_rate", {}).items():
            ip += per * ((rates or per_start["rates_at"])[event] - per_start["rates_at"][event])
        return self.workloads["starts"] * ip

    def leverage(self, rp_index):
        m = self.leverage_map
        return np.interp(rp_index, m["runs_index"], m["leverage"])

    def starting(self, era, innings) -> dict:
        p = self.pitcher["sp"]
        return {
            "runs": p["per_run"] * (self.pitcher["league_era"] - era) * innings / 9,
            "innings": p["per_nine"] * innings / 9,
        }

    def relieving(self, era, rp_index) -> dict:
        p, innings = self.pitcher["rp"], self.workloads["reliever_ip"]
        runs = p["per_run"] * (self.pitcher["league_era"] - era) * innings / 9
        return {
            "runs": runs,
            "leverage": runs * LEVERAGE_WEIGHT * (self.leverage(rp_index) - 1),
            "innings": p["per_nine"] * innings / 9,
        }


@lru_cache(maxsize=None)
def load(name: str = ARTIFACT) -> ValueModel:
    return ValueModel.from_file(ARTIFACTS_DIR / f"{name}.json")


def spot_slots(teams) -> dict:
    """{spot: how many the league has}: "H" the everyday bats, "H8".."H12"
    the part-time ones, "SP", and bullpen spots "RP1".."RP8" (most leverage
    first)."""
    return {"H": LINEUP_FULL * teams, **{f"H{k}": teams for k in range(LINEUP_FULL + 1, LINEUP + 1)},
            "SP": ROTATION * teams, **{f"RP{k}": teams for k in range(1, BULLPEN + 1)}}


class Replacement:
    """A league's spots and their prices (WAR). `spots`: "lineup_shares", the
    share of a full season bats LINEUP_FULL+1..LINEUP get, "bullpen_leverage",
    and the leverage of bullpen spots 1..BULLPEN; `prices` {spot: WAR}, all 0
    while they're being fit."""

    def __init__(self, spots: dict, prices: dict = None):
        self.shares = spots["lineup_shares"]
        self.bullpen = spots["bullpen_leverage"]
        self.prices = prices or dict.fromkeys(spot_slots(1), 0.0)

    def hitter_spots(self, war) -> dict:
        """{spot: his WAR there} for a hitter worth `war` full-time."""
        part = {f"H{LINEUP_FULL + 1 + i}": share * war for i, share in enumerate(self.shares)}
        return {"H": war, **part}

    def tilts(self, split) -> list:
        """The share of his batters a reliever with `split` (either direction)
        moves to his strong side, by bullpen spot."""
        ramp = float(np.clip(abs(split) / FULL_TILT_SPLIT, 0.0, 1.0))
        return [t * ramp for t in RELIEF_TILT]

    def relief_spots(self, runs, innings, weight) -> dict:
        """{spot: his WAR there} for a reliever saving `runs` (one figure, or
        one a spot) at average leverage over `innings` credit, leverage
        credited at `weight`."""
        runs = np.broadcast_to(np.asarray(runs, dtype=float), len(self.bullpen))
        return {f"RP{k + 1}": float(r * (1 + weight * (li - 1)) + innings)
                for k, (r, li) in enumerate(zip(runs, self.bullpen))}

    def leverage(self, spot) -> float:
        return self.bullpen[int(spot[2:]) - 1]

    def share(self, spot) -> float:
        return 1.0 if spot == "H" else self.shares[int(spot[1:]) - LINEUP_FULL - 1]

    def best(self, spots) -> str:
        """The spot he's furthest above its price."""
        return max(spots, key=lambda s: spots[s] - self.prices[s])

    @staticmethod
    def describe(spot) -> str:
        """The spot as the card names his role."""
        if spot == "H":
            return "an everyday regular"
        if spot == "SP":
            return "a rotation starter"
        if spot.startswith("RP"):
            k = int(spot[2:])
            return f"a {'high' if k <= 2 else 'mid' if k <= 4 else 'low'}-leverage reliever"
        return "a platoon bat" if int(spot[1:]) <= LINEUP_FULL + 2 else "a bench bat"


@lru_cache(maxsize=None)
def _replacement_artifact() -> dict:
    path = ARTIFACTS_DIR / f"{REPLACEMENT_ARTIFACT}.json"
    return json.loads(path.read_text()) if path.exists() else None


def replacement(league=None):
    """`league`'s Replacement (DEFAULT_LEAGUE's for a league it has none
    for), or None before it's fit."""
    artifact = _replacement_artifact()
    if artifact is None:
        return None
    found = artifact["leagues"].get(league) or artifact["leagues"].get(DEFAULT_LEAGUE)
    return Replacement(artifact["spots"], found["prices"]) if found else None
