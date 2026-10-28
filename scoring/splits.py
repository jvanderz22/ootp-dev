"""Platoon-split overalls: the current-ratings model re-run on a player's vs-L
and vs-R ratings (see `GamePlayer.with_split`), for the detail card.

Fielding and running have no split, so a batter's split score moves only through
the batting model; a pitcher's moves through stuff / movement / control. The
modifiers are the current ranking's (`OverallRanker`) minus
`BatterHandednessModifier` - its platoon bump is exactly what a split already
measures. `combined` is scored the same way so the three are comparable.
"""
from models.game_players import SPLIT_SIDES, GamePlayer
from modifiers.batter_hit_profile_modifier import BatterHitProfileModifier
from modifiers.pitcher_velocity_modifier import PitcherVelocityModifier
from scoring.model_cache import get_pitcher_scorer, get_position_player_scorer
from scoring.runtime_components import runtime_components_scope

_BATTER_MODIFIERS = (BatterHitProfileModifier(True),)
_PITCHER_MODIFIERS = (PitcherVelocityModifier,)


def _modifier(modifiers, player, score) -> float:
    total = 1
    for modifier in modifiers:
        total *= modifier.calculate_player_modifier(player, score)
    return total


def _payload(player: GamePlayer, batting, pitching) -> dict:
    batter_score, batting_model = batting[0], batting[1]
    pitcher_score, starter, reliever = pitching
    return {
        "batter_score": round(batter_score * _modifier(_BATTER_MODIFIERS, player, batter_score), 2),
        "batting_model": round(batting_model, 2),
        "pitcher_score": round(pitcher_score * _modifier(_PITCHER_MODIFIERS, player, pitcher_score), 2),
        "starter_score": round(starter, 2),
        "reliever_score": round(reliever, 2),
        "contact": player.contact_ovr,
        "gap": player.gap_ovr,
        "power": player.power_ovr,
        "eye": player.eye_ovr,
        "avoid_k": player.avoid_k_ovr,
        "stuff": player.stuff_ovr,
        "movement": player.movement_ovr,
        "control": player.control_ovr,
    }


def score_splits(player: GamePlayer):
    """`{"combined", "vL", "vR"}` -> scores + the ratings they came from, or None
    when the player's row carries no split ratings."""
    variants = {side: player.with_split(side) for side in SPLIT_SIDES}
    if any(v is None for v in variants.values()):
        return None
    variants = {"combined": player, **variants}
    players = list(variants.values())
    # a private scope: the scorers' breakdown writes must not leak into a
    # concurrent ranking run's (or the shared fallback) store
    with runtime_components_scope():
        batting = get_position_player_scorer("overall").score_many(players)
        pitching = get_pitcher_scorer("overall").score_many(players)
    return {
        key: _payload(p, b, pt)
        for key, p, b, pt in zip(variants, players, batting, pitching)
    }
