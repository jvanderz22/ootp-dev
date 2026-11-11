"""Which of a player's ratings a profile reads.

A profile scores on current ("overall") or potential ratings; every fitted
stage asks the view instead of picking GamePlayer attributes itself, so no
stage can read the wrong side by accident.
"""
import numpy as np

from models.game_players import SPLIT_SIDES
from ranking.fielding_talent import LEFTY, lefty
from ranking.fielding_talent import RATINGS as FIELDING
from ranking.hitter_talent import HIGH, LOW
from ranking.hitter_talent import RATINGS as HITTING
from ranking.running_talent import RATINGS as RUNNING
from ranking.pitcher_talent import RATINGS as PITCHING
from ranking.pitcher_talent import SPLIT_PITCHES, top_pitches

# rating -> GamePlayer attribute, per profile `ratings`
_ATTRS = {
    "overall": {
        "babip": "babip_ovr", "avoid_k": "avoid_k_ovr", "gap": "gap_ovr",
        "power": "power_ovr", "eye": "eye_ovr",
        "stuff": "stuff_ovr", "control": "control_ovr", "movement": "movement_ovr",
        "hra": "hr_allowed_ovr", "pbabip": "pbabip_ovr",
    },
    "potential": {
        "babip": "babip", "avoid_k": "avoid_k", "gap": "gap", "power": "power", "eye": "eye",
        "stuff": "stuff", "control": "control", "movement": "movement",
        "hra": "hr_allowed", "pbabip": "pbabip",
    },
}
# OOTP's Contact is about half BABIP and half Avoid K, so an export without
# BABIP (every draft-class export) is scored on the BABIP those two imply:
# 2 x Contact - Avoid K is within 5 of the real one for 95-99% of hitters
_CONTACT = {"overall": "contact_ovr", "potential": "contact"}
# Movement's parts; a class exported without them is scored on Movement
_MOVEMENT_PARTS = ("hra", "pbabip")
# arm slot as exported (a league snapshot's names, a class's codes)
_SLOTS = {
    "normal": "normal", "3/4": "normal",
    "over the top": "over the top", "ott": "over the top",
    "sidearm": "sidearm", "side": "sidearm", "submarine": "sidearm", "sub": "sidearm",
}


class RatingsView:
    def __init__(self, ratings: str):
        self.ratings = ratings
        self.attrs = _ATTRS[ratings]

    def hitting(self, player):
        """The base batting ratings, or None when any is missing. BABIP, when
        it isn't exported, is the one Contact and Avoid K imply."""
        values = {name: getattr(player, self.attrs[name]) for name in HITTING}
        if values["babip"] is None:
            values["babip"] = self.implied_babip(player)
        if any(v is None for v in values.values()):
            return None
        return values

    def implied_babip(self, player):
        """2 x Contact - Avoid K on the scale, or None without both."""
        contact, avoid_k = getattr(player, _CONTACT[self.ratings]), getattr(player, self.attrs["avoid_k"])
        if not contact or not avoid_k:
            return None
        return int(np.clip(2 * contact - avoid_k, LOW, HIGH))

    def pitching(self, player):
        """The base pitching ratings. Movement is read only when its parts (HRA,
        PBABIP) aren't there, and they're None then; None when Stuff, Control or
        the Movement side is missing (GamePlayer reads a blank one as 0)."""
        values = {name: getattr(player, self.attrs[name]) for name in ("stuff", "control", *_MOVEMENT_PARTS)}
        if any(values[name] is None for name in _MOVEMENT_PARTS):
            values.update(dict.fromkeys(_MOVEMENT_PARTS), movement=getattr(player, self.attrs["movement"]))
        else:
            values["movement"] = None
        if not values["stuff"] or not values["control"] or not (values["movement"] or values["hra"]):
            return None
        return values

    def hitting_splits(self, player):
        """{"vL" | "vR": base batting ratings} from his platoon splits (vs left-
        / right-handed pitchers), or None: only current ratings have splits,
        and only a league snapshot's rows."""
        if self.ratings != "overall":
            return None
        sides = {}
        for side in SPLIT_SIDES:
            split = player.with_split(side)
            sides[side] = self.hitting(split) if split is not None else None
            if sides[side] is None:
                return None
        return sides

    @staticmethod
    def bats(player):
        """"R" / "L" / "S", or None when not exported."""
        hand = (player.bat_hand or "").strip()[:1].upper()
        return {"B": "S"}.get(hand, hand) if hand in ("R", "L", "S", "B") else None

    def pitching_splits(self, player):
        """{"vL" | "vR": base pitching ratings} from his platoon splits, or None:
        only current ratings have splits, and only a league snapshot's rows."""
        if self.ratings != "overall":
            return None
        sides = {}
        for side in SPLIT_SIDES:
            split = player.with_split(side)
            sides[side] = self.pitching(split) if split is not None else None
            if sides[side] is None:
                return None
        return sides

    @staticmethod
    def throws(player):
        """"R" / "L", or None (a switch pitcher, or not exported)."""
        hand = (player.throw_hand or "").strip()[:1].upper()
        return hand if hand in ("R", "L") else None

    def fielding(self, players) -> dict:
        """{rating: array} of the fielding ratings (one value each: no potential
        side), and whether each throws left."""
        return {**{r: np.array([getattr(p, r) for p in players]) for r in FIELDING}, LEFTY: lefty(players)}

    def running(self, players) -> dict:
        return {r: np.array([getattr(p, r) for p in players]) for r in RUNNING}

    def stamina(self, player) -> int:
        return player.stamina

    def control(self, player) -> int:
        """Control on the profile's side (0 when not exported)."""
        return getattr(player, self.attrs["control"]) or 0

    def pitch_grades(self, player) -> list:
        """His best pitch grades, best first (ranking.pitcher_talent.top_pitches)."""
        pitches = player.get_pitches() if self.ratings == "potential" else player.get_ovr_pitches()
        return top_pitches([getattr(player, p) for p in pitches])

    def pitch_mix(self, player) -> dict:
        """{pitch: grade} of the pitches he throws, named as SPLIT_PITCHES."""
        suffix = "" if self.ratings == "potential" else "_ovr"
        return {p: g for p in SPLIT_PITCHES if (g := getattr(player, p + suffix))}

    @staticmethod
    def arm_slot(player) -> str:
        """"normal" / "over the top" / "sidearm" (submarine counts as sidearm);
        normal when not exported."""
        return _SLOTS.get((player.arm_slot or "").strip().lower(), "normal")

    def pitch_count(self, player) -> int:
        pitches = player.get_pitches() if self.ratings == "potential" else player.get_ovr_pitches()
        return len(pitches)
