from modifiers.base_modifier import BaseModifier
from modifiers.batter_handedness_modifier import BatterHandednessModifier
from modifiers.batter_hit_profile_modifier import BatterHitProfileModifier
from rankers.base_ranker import BaseRanker
from scoring.model_cache import get_pitcher_scorer, get_position_player_scorer


class OverallRanker(BaseRanker):
    def __init__(self):
        super().__init__(
            position_player_scorer=get_position_player_scorer("overall"),
            pitcher_scorer=get_pitcher_scorer("overall"),
        )

    # Class attributes, not properties, so `scoring/splits.py` can reuse them
    # without building a ranker.
    position_player_modifiers: list[BaseModifier] = [
        BatterHandednessModifier,
        BatterHitProfileModifier(True),
    ]

    # No PitcherVelocityModifier: on current ratings velo is already priced into
    # Stuff, which the SP / RP models score. It stays on the potential and draft
    # rankers, where it's its own read on how an arm develops.
    pitcher_modifiers: list[BaseModifier] = []

    two_way_player_threshold = 2.5
