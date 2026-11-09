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

from models.game_players import SPLIT_SIDES
from ranking import fielding_talent, hitter_talent, pitcher_talent, running_talent
from ranking.ratings import RatingsView
from scoring.pitcher_scorer import rp_stamina_modifier_map, sp_stamina_modifier_map
from scoring.position_player_scorer import utility_bonus
from scoring.runtime_components import write_runtime_component


class FittedBatting(NamedTuple):
    points: float
    label: str
    wrc_plus: float
    platoon: bool = False   # scored on his vL / vR splits
    bats: str = None        # "R" / "L" / "S"; None when not exported
    wrc_vl: float = None    # vs left- / right-handed pitchers: his splits, or
    wrc_vr: float = None    # the expected ones for his hand (None without one)


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
        points = self.model.points(wrc_plus)
        for j, ((i, _), wrc, pts) in enumerate(zip(rated, wrc_plus, points)):
            write_runtime_component(players[i].id, "batting.talent.wrc_plus", float(wrc))
            vl, vr = (None if np.isnan(w[j]) else float(w[j]) for w in (side_wrc["vL"], side_wrc["vR"]))
            out[i] = FittedBatting(float(pts), f"batting talent ({wrc:.0f} wRC+)", float(wrc), bool(real[j]),
                                   bats[j], vl, vr)
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
        events = {role: self.model.events({**ratings, "stuff": stuff[role]}, role) for role in pitcher_talent.ROLES}
        predicted = self._predicted_split(players, group)
        split = {role: predicted.copy() for role in pitcher_talent.ROLES}
        platoon = self._platoon(players, group, top, listed_sp, events, split)
        index = {role: self.model.index_of(events[role]) for role in pitcher_talent.ROLES}
        era = {role: self.model.era_of(events[role]) for role in pitcher_talent.ROLES}
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
                platoon=bool(platoon[j]),
                sp_split=float(split["sp"][j]),
                rp_split=float(split["rp"][j]),
                split_estimated=not platoon[j] and predicted[j] != 0,
                sp_rates={e: float(np.asarray(events["sp"][e])[j]) for e in ("k", "bb", "hr")},
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

    def _platoon(self, players, group, top, listed_sp, events, role_split) -> np.ndarray:
        """Puts each role's events against its batters, vL and vR scored apart,
        in `events` for the pitchers whose splits are there (and on the group's
        side of HRA / Movement), and each role's split in `role_split`; returns
        which ones."""
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
            index = {side: self.model.runs_index(r, role) for side, r in in_role.items()}
            lefty = np.array(throws) == "L"
            role_split[role][rows] = np.where(lefty, index["vR"] - index["vL"], index["vL"] - index["vR"])
            blended = self.model.platoon_events(in_role, role, self.model.lhb_share(role, throws))
            for name, value in blended.items():
                events[role][name] = np.asarray(events[role][name], dtype=float).copy()
                events[role][name][rows] = value
        return done


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
