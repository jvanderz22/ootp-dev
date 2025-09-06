

from models.game_players import GamePlayer
from modifiers.base_modifier import BaseModifier
from modifiers.base_rank_modifier import BaseRankModifier

from utils.rank_graditated_model import RankGradiatedModel

# theory:
# prefer players with remaining dev runway, especially with lower model scores

age_modifiers = {
    16: 1.15,
    17: 1.15,
    18: 1.12,
    19: 1.09,
    20: 1.06,
    21: 1.035,
    22: 1.02,
    23: 1.01,
}

class AgeModifier(BaseModifier):
    modifier_weight_model = RankGradiatedModel(
        [0, 35, 55, 100, 130],
        [1, 1, 0.5, 0.2, 0],
    )

    @classmethod
    def calculate_player_modifier(cls, player: GamePlayer, model_score: float):
        modifier_weight = cls.modifier_weight_model.rank(model_score)
        base_age_modifier = age_modifiers.get(player.age, 1)

        total_modifier = base_age_modifier**modifier_weight
        return total_modifier