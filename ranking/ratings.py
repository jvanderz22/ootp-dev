"""Which of a player's ratings a profile reads.

A profile scores on current ("overall") or potential ratings; every fitted
stage asks the view instead of picking GamePlayer attributes itself, so no
stage can read the wrong side by accident.
"""
from ranking.hitter_talent import RATINGS as HITTING
from ranking.pitcher_talent import RATINGS as PITCHING

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
# Movement's parts; a class exported without them is scored on Movement
_MOVEMENT_PARTS = ("hra", "pbabip")


class RatingsView:
    def __init__(self, ratings: str):
        self.ratings = ratings
        self.attrs = _ATTRS[ratings]

    def hitting(self, player):
        """The base batting ratings, or None when any is missing (e.g. a class
        exported before BABIP was)."""
        values = {name: getattr(player, self.attrs[name]) for name in HITTING}
        if any(v is None for v in values.values()):
            return None
        return values

    def pitching(self, player):
        """The base pitching ratings, with `hra` / `pbabip` None when the class
        doesn't have them; None when Stuff, Control or Movement is missing
        (GamePlayer reads a blank one as 0)."""
        values = {name: getattr(player, self.attrs[name]) for name in PITCHING}
        if any(not values[name] for name in PITCHING if name not in _MOVEMENT_PARTS):
            return None
        if any(values[name] is None for name in _MOVEMENT_PARTS):
            values.update(dict.fromkeys(_MOVEMENT_PARTS))
        return values

    def stamina(self, player) -> int:
        return player.stamina

    def pitch_count(self, player) -> int:
        pitches = player.get_pitches() if self.ratings == "potential" else player.get_ovr_pitches()
        return len(pitches)
