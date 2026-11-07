"""Which of a player's ratings a profile reads.

A profile scores on current ("overall") or potential ratings; every fitted
stage asks the view instead of picking GamePlayer attributes itself, so no
stage can read the wrong side by accident.
"""
from ranking.hitter_talent import RATINGS as HITTING

# rating -> GamePlayer attribute, per profile `ratings`
_ATTRS = {
    "overall": {
        "babip": "babip_ovr", "avoid_k": "avoid_k_ovr", "gap": "gap_ovr",
        "power": "power_ovr", "eye": "eye_ovr",
    },
    "potential": {
        "babip": "babip", "avoid_k": "avoid_k", "gap": "gap", "power": "power", "eye": "eye",
    },
}


class RatingsView:
    def __init__(self, ratings: str):
        self.attrs = _ATTRS[ratings]

    def hitting(self, player):
        """The base batting ratings, or None when any is missing (e.g. a class
        exported before BABIP was)."""
        values = {name: getattr(player, self.attrs[name]) for name in HITTING}
        if any(v is None for v in values.values()):
            return None
        return values
