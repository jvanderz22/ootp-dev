"""The fitted talent layer (phases 3, 4 and 5a). `LegacyModel` asks it for each
batch's batting, fielding, baserunning and pitching scores: it scores every
player whose base ratings are there, and the legacy models score the rest (old
class formats without BABIP).

Until the value layer turns everything into WAR, fitted talent is put on the
legacy models' 0-100 scales through the artifacts' points bridges, so the
fielding and running components, the modifiers and the two-way rule still see
the scale they were tuned for.
"""
from typing import NamedTuple

import numpy as np

from ranking import fielding_talent, hitter_talent, pitcher_talent, running_talent
from ranking.ratings import RatingsView
from scoring.pitcher_scorer import rp_stamina_modifier_map, sp_stamina_modifier_map
from scoring.position_player_scorer import utility_bonus
from scoring.runtime_components import write_runtime_component


class FittedBatting(NamedTuple):
    points: float
    label: str
    wrc_plus: float


class HitterTalent:
    name = "hitter-talent"

    def __init__(self, profile, model=None):
        self.ratings = RatingsView(profile.ratings)
        self.model = model or hitter_talent.load()

    @property
    def artifact(self) -> str:
        return self.model.version

    def score(self, players) -> list:
        """A FittedBatting per player, or None where the ratings aren't there."""
        out = [None] * len(players)
        rated = [(i, r) for i, p in enumerate(players) if (r := self.ratings.hitting(p)) is not None]
        if not rated:
            return out
        ratings = {name: np.array([r[name] for _, r in rated]) for name in hitter_talent.RATINGS}
        wrc_plus = self.model.wrc_plus(ratings)
        points = self.model.points(wrc_plus)
        for (i, _), wrc, pts in zip(rated, wrc_plus, points):
            write_runtime_component(players[i].id, "batting.talent.wrc_plus", float(wrc))
            out[i] = FittedBatting(float(pts), f"batting talent ({wrc:.0f} wRC+)", float(wrc))
        return out


# Role viability - can he hold a starter's workload, does he have the pitches to
# turn a lineup over - is playing time, which the value layer (phase 5) will
# model. Until then it keeps the legacy values: stamina, and the pitch-count
# part of the legacy pitch-mix maps (the grades are Stuff, already in talent).
SP_ROLE_FLOOR = 0.45


def _grade(table, value):
    return table[min(max(int(round(value / 5)) * 5, 20), 80)]


def sp_role_factor(stamina, pitches) -> float:
    if pitches < 1:
        return 0.0
    count = (0.8 if pitches <= 2 else 1) * (0.35 if pitches < 3 else 1) * (0.92 if pitches < 4 else 1)
    return max(SP_ROLE_FLOOR, _grade(sp_stamina_modifier_map, stamina) * count)


def rp_role_factor(stamina, pitches) -> float:
    if pitches < 1:
        return 0.0
    return _grade(rp_stamina_modifier_map, stamina) * (0.8 if pitches < 2 else 1)


class FittedPitching(NamedTuple):
    starter: float
    reliever: float
    starter_talent: float
    reliever_talent: float
    sp_index: float
    rp_index: float
    sp_era: float
    rp_era: float
    sp_stuff: float         # Stuff in each role: displayed is the listed role's
    rp_stuff: float


class PitcherTalent:
    name = "pitcher-talent"

    def __init__(self, profile, model=None):
        self.ratings = RatingsView(profile.ratings)
        self.rp_multiplier = profile.rp_multiplier
        self.model = model or pitcher_talent.load()

    @property
    def artifact(self) -> str:
        return self.model.version

    def score(self, players) -> list:
        """A FittedPitching per player, or None where the ratings aren't there."""
        out = [None] * len(players)
        rated = [(i, r) for i, p in enumerate(players) if (r := self.ratings.pitching(p)) is not None]
        # players with HRA / PBABIP and those on Movement go through separately
        for use_parts in (True, False):
            group = [(i, r) for i, r in rated if (r["hra"] is not None) == use_parts]
            if group:
                self._score_group(players, group, out)
        return out

    def _score_group(self, players, group, out):
        ratings = {
            name: (np.array([r[name] for _, r in group]) if group[0][1][name] is not None else None)
            for name in pitcher_talent.RATINGS
        }
        # displayed Stuff is the listed role's; each role is scored at its own
        top = np.array([self.ratings.pitch_grades(players[i]) for i, _ in group])
        listed_sp = np.array([players[i].position == "SP" for i, _ in group])
        stuff = self.model.role_stuff(ratings["stuff"], top, listed_sp, self.ratings.ratings)
        in_role = {role: {**ratings, "stuff": stuff[role]} for role in pitcher_talent.ROLES}
        index = {role: self.model.runs_index(in_role[role], role) for role in pitcher_talent.ROLES}
        era = {role: self.model.era(in_role[role], role) for role in pitcher_talent.ROLES}
        talent = {role: self.model.points(index[role], role) for role in pitcher_talent.ROLES}
        for j, (i, _) in enumerate(group):
            player = players[i]
            pitches, stamina = self.ratings.pitch_count(player), self.ratings.stamina(player)
            sp, rp = float(talent["sp"][j]), float(talent["rp"][j])
            out[i] = FittedPitching(
                starter=sp * sp_role_factor(stamina, pitches),
                reliever=rp * rp_role_factor(stamina, pitches) * self.rp_multiplier,
                starter_talent=sp,
                reliever_talent=rp,
                sp_index=float(index["sp"][j]),
                rp_index=float(index["rp"][j]),
                sp_era=float(era["sp"][j]),
                rp_era=float(era["rp"][j]),
                sp_stuff=float(stuff["sp"][j]),
                rp_stuff=float(stuff["rp"][j]),
            )
            write_runtime_component(player.id, "pitching.talent.sp_runs_index", out[i].sp_index)
            write_runtime_component(player.id, "pitching.talent.rp_runs_index", out[i].rp_index)


class FittedFielding(NamedTuple):
    points: float           # best position, on legacy's best-position scale
    utility: float          # legacy's utility bonus, on the floored grids
    best_position: str
    runs: float             # fielding runs per season at the best position
    value: float            # those plus the position's adjustment


class FieldingTalent:
    name = "fielding-talent"

    def __init__(self, profile, model=None):
        self.ratings = RatingsView(profile.ratings)
        self.model = model or fielding_talent.load()

    @property
    def artifact(self) -> str:
        return self.model.version

    def score(self, players) -> list:
        """A FittedFielding per player (every player has fielding ratings)."""
        if not players:
            return []
        floored = fielding_talent.floored_grids(fielding_talent.grid_scores(players), self.ratings.fielding(players))
        value, best, runs = self.model.best(floored)
        points = self.model.points(value)
        out = []
        for j, player in enumerate(players):
            scores = {pos: float(floored[pos][j]) for pos in fielding_talent.POSITIONS}
            out.append(FittedFielding(
                float(points[j]), float(utility_bonus(scores)), best[j], float(runs[j]), float(value[j]),
            ))
            write_runtime_component(player.id, "batting.talent.fielding_runs", float(runs[j]))
        return out


class FittedRunning(NamedTuple):
    points: float
    runs: float             # baserunning runs per 600 PA


class RunningTalent:
    name = "running-talent"

    def __init__(self, profile, model=None):
        self.ratings = RatingsView(profile.ratings)
        self.model = model or running_talent.load()

    @property
    def artifact(self) -> str:
        return self.model.version

    def score(self, players) -> list:
        if not players:
            return []
        runs = self.model.runs(self.ratings.running(players))
        points = self.model.points(runs)
        for player, r in zip(players, runs):
            write_runtime_component(player.id, "batting.talent.baserunning_runs", float(r))
        return [FittedRunning(float(p), float(r)) for p, r in zip(points, runs)]
