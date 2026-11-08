"""The fitted talent layer (phases 3 and 4). `LegacyModel` asks it for each
batch's batting and pitching scores: it scores every player whose base ratings
are there, and the legacy models score the rest (old class formats without
BABIP).

Until the value layer turns everything into WAR, fitted talent is put on the
legacy models' 0-100 scales through the artifacts' points bridges, so the
fielding and running components, the modifiers and the two-way rule still see
the scale they were tuned for.
"""
from typing import NamedTuple

import numpy as np

from ranking import hitter_talent, pitcher_talent
from ranking.ratings import RatingsView
from scoring.pitcher_scorer import rp_stamina_modifier_map, sp_stamina_modifier_map
from scoring.runtime_components import write_runtime_component


class FittedBatting(NamedTuple):
    points: float
    label: str


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
            out[i] = FittedBatting(float(pts), f"batting talent ({wrc:.0f} wRC+)")
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
        index = {role: self.model.runs_index(ratings, role) for role in pitcher_talent.ROLES}
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
            )
            write_runtime_component(player.id, "pitching.talent.sp_runs_index", out[i].sp_index)
            write_runtime_component(player.id, "pitching.talent.rp_runs_index", out[i].rp_index)
