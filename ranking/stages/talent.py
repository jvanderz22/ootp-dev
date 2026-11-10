"""The fitted talent layer (phases 3, 4 and 5a): batting, fielding, baserunning
and pitching read off the ratings by the fitted models, one batched call per
model (`Talent`). A player a model can't read (no batting ratings, a pitcher
without Stuff or Control) gets None there, and the value stage values that
side at replacement.

Since 2026-11-09 (plans/xgboost-phaseout-plan.md, step 3) nothing here goes
through legacy points: the value stage turns these reads into WAR directly.
"""
from typing import NamedTuple

import numpy as np

from models.game_players import SPLIT_SIDES
from ranking import fielding_talent, hitter_talent, pitcher_talent, running_talent
from ranking.ratings import RatingsView
from ranking.stages.base import BatchStage
from scoring.runtime_components import write_runtime_component


class FittedBatting(NamedTuple):
    wrc_plus: float
    platoon: bool = False   # scored on his vL / vR splits
    bats: str = None        # "R" / "L" / "S"; None when not exported
    wrc_vl: float = None    # vs left- / right-handed pitchers: his splits, or
    wrc_vr: float = None    # the expected ones for his hand (None without one)
    babip_implied: bool = False  # BABIP not exported: the one Contact and Avoid K imply


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
        events = self.model.events(ratings)
        hitters = [players[i] for i, _ in rated]
        bats = [self.ratings.bats(p) for p in hitters]
        real, side_wrc = self._sides(hitters, bats, ratings, events)
        wrc_plus = self.model.wrc_of(events)
        for j, ((i, _), wrc) in enumerate(zip(rated, wrc_plus)):
            write_runtime_component(players[i].id, "batting.talent.wrc_plus", float(wrc))
            vl, vr = (None if np.isnan(w[j]) else float(w[j]) for w in (side_wrc["vL"], side_wrc["vR"]))
            implied = getattr(players[i], self.ratings.attrs["babip"]) is None
            out[i] = FittedBatting(float(wrc), bool(real[j]), bats[j], vl, vr, implied)
        return out

    def _sides(self, hitters, bats, ratings, events):
        """Each hitter's vs-L / vs-R wRC+ (NaN without a batting hand): from his
        splits where they're there - whose blend then replaces his `events` -
        else from the expected splits for his hand. Returns (which are real
        splits, {side: wRC+})."""
        n = len(hitters)
        splits = [self.ratings.hitting_splits(p) for p in hitters]
        handed = np.array([b is not None for b in bats])
        real = handed & np.array([s is not None for s in splits])
        sides = {side: {name: np.full(n, np.nan) for name in hitter_talent.RATINGS} for side in SPLIT_SIDES}
        guess = np.flatnonzero(handed & ~real)
        if len(guess):
            expected = self.model.expected_sides({k: v[guess] for k, v in ratings.items()}, [bats[i] for i in guess])
            for side in SPLIT_SIDES:
                for name in hitter_talent.RATINGS:
                    sides[side][name][guess] = expected[side][name]
        for i in np.flatnonzero(real):
            for side in SPLIT_SIDES:
                for name in hitter_talent.RATINGS:
                    sides[side][name][i] = splits[i][side][name]
        side_wrc = {side: np.full(n, np.nan) for side in SPLIT_SIDES}
        rows = np.flatnonzero(handed)
        if not len(rows):
            return real, side_wrc
        side_events = {side: self.model.events({k: v[rows] for k, v in sides[side].items()}) for side in SPLIT_SIDES}
        for side in SPLIT_SIDES:
            side_wrc[side][rows] = self.model.wrc_of(side_events[side])
        # real splits: the season's events are the two sides blended
        share = self.model.lhp_share([bats[i] for i in rows])
        mine = real[rows]
        if mine.any():
            for name in events:
                blended = share * side_events["vL"][name] + (1 - share) * side_events["vR"][name]
                events[name] = np.asarray(events[name], dtype=float).copy()
                events[name][rows[mine]] = blended[mine]
        return real, side_wrc


class FittedPitching(NamedTuple):
    sp_index: float
    rp_index: float
    sp_era: float
    rp_era: float
    sp_stuff: float         # Stuff in each role: displayed is the listed role's
    rp_stuff: float
    platoon: bool           # scored on his vL / vR splits
    # runs index he's better by in each role against same-handed batters than
    # opposite-handed ones (negative: a reverse split), from his splits or
    # else predicted from hand, slot and pitch mix (`split_estimated`; the
    # relief split stands in for both roles)
    sp_split: float = 0.0
    rp_split: float = 0.0
    split_estimated: bool = False
    # his strikeouts, walks and home runs per PA as a starter: how efficient
    # he is, which sets how deep he goes (ranking/value.py starter_innings)
    sp_rates: dict = None
    # {"sp" | "rp": {"vL" | "vR": ERA}} against left- / right-handed batters,
    # on his splits (None without them)
    side_era: dict = None


class PitcherTalent:
    name = "pitcher-talent"

    def __init__(self, profile, model=None):
        self.ratings = RatingsView(profile.ratings)
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
        events = {role: self.model.events({**ratings, "stuff": stuff[role]}, role) for role in pitcher_talent.ROLES}
        predicted = self._predicted_split(players, group)
        split = {role: predicted.copy() for role in pitcher_talent.ROLES}
        side_era = {role: {side: np.full(len(group), np.nan) for side in SPLIT_SIDES} for role in pitcher_talent.ROLES}
        platoon = self._platoon(players, group, top, listed_sp, events, split, side_era)
        index = {role: self.model.index_of(events[role]) for role in pitcher_talent.ROLES}
        era = {role: self.model.era_of(events[role]) for role in pitcher_talent.ROLES}
        for j, (i, _) in enumerate(group):
            player = players[i]
            out[i] = FittedPitching(
                sp_index=float(index["sp"][j]),
                rp_index=float(index["rp"][j]),
                sp_era=float(era["sp"][j]),
                rp_era=float(era["rp"][j]),
                sp_stuff=float(stuff["sp"][j]),
                rp_stuff=float(stuff["rp"][j]),
                platoon=bool(platoon[j]),
                sp_split=float(split["sp"][j]),
                rp_split=float(split["rp"][j]),
                split_estimated=not platoon[j] and predicted[j] != 0,
                sp_rates={e: float(np.asarray(events["sp"][e])[j]) for e in ("k", "bb", "hr")},
                side_era={role: {side: float(e[j]) for side, e in by_side.items()} for role, by_side in side_era.items()}
                if platoon[j] else None,
            )
            write_runtime_component(player.id, "pitching.talent.sp_runs_index", out[i].sp_index)
            write_runtime_component(player.id, "pitching.talent.rp_runs_index", out[i].rp_index)

    def _predicted_split(self, players, group) -> np.ndarray:
        """Each pitcher's relief split as predicted from his hand, slot and pitch
        mix; 0 without a throwing hand (or a predictor)."""
        out = np.zeros(len(group))
        hands = [(j, self.ratings.throws(players[i])) for j, (i, _) in enumerate(group)]
        hands = [(j, hand) for j, hand in hands if hand]
        if hands and self.model.split_fit:
            features = [
                pitcher_talent.split_features(hand, self.ratings.arm_slot(players[group[j][0]]),
                                              self.ratings.pitch_mix(players[group[j][0]]))
                for j, hand in hands
            ]
            out[[j for j, _ in hands]] = self.model.predicted_split(features)
        return out

    def _platoon(self, players, group, top, listed_sp, events, role_split, side_era) -> np.ndarray:
        """Puts each role's events against its batters, vL and vR scored apart,
        in `events` for the pitchers whose splits are there (and on the group's
        side of HRA / Movement), each role's split in `role_split` and each
        side's ERA in `side_era`; returns which ones."""
        hra = group[0][1]["hra"] is not None
        rows, sides, throws = [], [], []
        for j, (i, _) in enumerate(group):
            split, hand = self.ratings.pitching_splits(players[i]), self.ratings.throws(players[i])
            if split and hand and all((split[side]["hra"] is not None) == hra for side in split):
                rows.append(j)
                sides.append(split)
                throws.append(hand)
        done = np.zeros(len(group), dtype=bool)
        if not rows:
            return done
        done[rows] = True
        by_side = {
            side: {name: (np.array([s[side][name] for s in sides]) if sides[0][side][name] is not None else None)
                   for name in pitcher_talent.RATINGS}
            for side in SPLIT_SIDES
        }
        # each side's displayed Stuff is the listed role's too
        stuff = {side: self.model.role_stuff(r["stuff"], top[rows], listed_sp[rows], self.ratings.ratings)
                 for side, r in by_side.items()}
        for role in pitcher_talent.ROLES:
            in_role = {side: {**r, "stuff": stuff[side][role]} for side, r in by_side.items()}
            side_events = {side: self.model.events(r, role) for side, r in in_role.items()}
            index = {side: self.model.index_of(e) for side, e in side_events.items()}
            for side, e in side_events.items():
                side_era[role][side][rows] = self.model.era_of(e)
            lefty = np.array(throws) == "L"
            role_split[role][rows] = np.where(lefty, index["vR"] - index["vL"], index["vL"] - index["vR"])
            blended = self.model.platoon_events(in_role, role, self.model.lhb_share(role, throws))
            for name, value in blended.items():
                events[role][name] = np.asarray(events[role][name], dtype=float).copy()
                events[role][name][rows] = value
        return done


class FittedFielding(NamedTuple):
    best_position: str
    runs: float             # fielding runs per season at the best position
    utility_war: float = 0.0    # roster flexibility (fielding_talent.utility)
    covers: tuple = ()          # the other positions credited for it
    # {position: (runs there after its floors, floor factor)}: the card's
    # position table, so you can see why the best one won
    positions: dict = None


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
        ratings = {r: np.asarray(v, float) for r, v in self.ratings.fielding(players).items()}
        _, best, runs = self.model.best(ratings)
        covers = self.model.covers(ratings)
        by_position = self.model.runs(ratings)
        floors = {pos: fielding_talent.floor_factor(pos, ratings) for pos in fielding_talent.POSITIONS}
        out = []
        for j, player in enumerate(players):
            war, credited = fielding_talent.utility({p for p, c in covers.items() if c[j]}, best[j])
            positions = {pos: (float(by_position[pos][j]), float(floors[pos][j]))
                         for pos in fielding_talent.POSITIONS}
            out.append(FittedFielding(best[j], float(runs[j]), war, tuple(credited), positions))
            write_runtime_component(player.id, "batting.talent.fielding_runs", float(runs[j]))
        return out


class FittedRunning(NamedTuple):
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
        for player, r in zip(players, runs):
            write_runtime_component(player.id, "batting.talent.baserunning_runs", float(r))
        return [FittedRunning(float(r)) for r in runs]


class Talent(BatchStage):
    """Every fitted talent model, one batched call each: `state.fitted` by
    side ("batting", "fielding", "running", "pitching"), None where a model
    can't read the player."""

    name = "talent"

    def __init__(self, profile):
        self.models = {
            "batting": HitterTalent(profile),
            "fielding": FieldingTalent(profile),
            "running": RunningTalent(profile),
            "pitching": PitcherTalent(profile),
        }

    @property
    def artifacts(self) -> dict:
        return {m.name: m.artifact for m in self.models.values()}

    def run(self, states, profile):
        players = [s.player for s in states]
        scored = {side: model.score(players) for side, model in self.models.items()}
        for j, state in enumerate(states):
            state.fitted = {side: fits[j] for side, fits in scored.items()}
