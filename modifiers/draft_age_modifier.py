from modifiers.base_rank_modifier import BaseRankModifier

age_modifiers = {
    17: 1.2,
    18: 1.15,
    19: 1.05,
    20: 1.02,
    21: 0.99,
    22: 0.96,
    23: 0.93,
    24: 0.86,
}
from utils.rank_graditated_model import RankGradiatedModel


class DraftAgeModifier(BaseRankModifier):
    modifier_weight_model = RankGradiatedModel(
        [10, 25, 50, 75, 100, 150, 200, 250, 300, 700],
        [0.02, 0.05, 0.1, 0.15, 0.2, 0.4, 0.5, 0.62, 0.75, 1.2],
    )

    @classmethod
    def calculate_player_modifier(cls, player, rank):
        modifier_weight = cls.modifier_weight_model.rank(rank)
        base_age_modifier = age_modifiers.get(player.age, 0.86)

        total_modifier = base_age_modifier**modifier_weight
        return total_modifier
