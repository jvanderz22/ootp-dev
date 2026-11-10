"""Platoon splits for the detail card: a live-league player's vs-L and vs-R
ratings (see `GamePlayer.with_split`), and for a hitter engine v2's wRC+ on
each side next to his combined one, calibrated as the value stage reads it
(ranking/stages/value.py). A pitcher's ERA on each side is on the card's
value build instead (the matchups line).

The combined wRC+ is his two sides blended at his batting hand's mix, as the
value stage blends them.
"""
from models.game_players import SPLIT_SIDES, GamePlayer
from ranking import value
from ranking.profiles import CURRENT
from ranking.stages.talent import HitterTalent
from scoring.runtime_components import runtime_components_scope


def _ratings(player: GamePlayer) -> dict:
    return {
        "contact": player.contact_ovr,
        "gap": player.gap_ovr,
        "power": player.power_ovr,
        "eye": player.eye_ovr,
        "avoid_k": player.avoid_k_ovr,
        "babip": player.babip_ovr,
        "stuff": player.stuff_ovr,
        "movement": player.movement_ovr,
        "control": player.control_ovr,
        "hra": player.hr_allowed_ovr,
        "pbabip": player.pbabip_ovr,
    }


def _wrc_plus(player: GamePlayer) -> dict:
    """{"combined" | "vL" | "vR": wRC+}, or {} without a fit on his splits."""
    stage = HitterTalent(CURRENT)
    (fit,) = stage.score([player])
    if fit is None or not fit.platoon:
        return {}
    vs_lhp = stage.model.platoon_mix[fit.bats]
    raw = {"vL": fit.wrc_vl, "vR": fit.wrc_vr}
    raw["combined"] = vs_lhp * raw["vL"] + (1 - vs_lhp) * raw["vR"]
    return {side: round(float(value.load().calibrated("wrc_plus", w))) for side, w in raw.items()}


def score_splits(player: GamePlayer):
    """`{"combined", "vL", "vR"}` -> the ratings on that side plus v2's wRC+
    there, or None when the player's row carries no split ratings."""
    variants = {side: player.with_split(side) for side in SPLIT_SIDES}
    if any(v is None for v in variants.values()):
        return None
    variants = {"combined": player, **variants}
    # a private scope: the talent stages' breakdown writes must not leak into a
    # concurrent ranking run's (or the shared fallback) store
    with runtime_components_scope():
        wrc = _wrc_plus(player)
    return {side: {**_ratings(p), "wrc_plus": wrc.get(side)} for side, p in variants.items()}
