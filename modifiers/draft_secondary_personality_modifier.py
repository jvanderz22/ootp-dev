from modifiers.base_modifier import BaseModifier
from utils.rank_graditated_model import RankGradiatedModel


class DraftSecondaryPersonalityModifier(BaseModifier):
    bad_personality_modifier_model = RankGradiatedModel(
        [0, 10, 35, 50, 75, 100],
        [1, 1, 0.8, 0.4, 0.1, 0.1],
    )
    high_leadership_modifier_model = RankGradiatedModel(
        [0, 25, 32, 40, 45], [1, 1, 0.8, 0.1, 0]
    )
    low_leadership_modifier_model = RankGradiatedModel([0, 30, 38], [1, 1, 0])

    @classmethod
    def calculate_player_modifier(cls, player, model_weight):
        personality_modifier = 1

        bad_personalities = 0
        if player.work_ethic == "L":
            bad_personalities += 1
        if player.intelligence == "L":
            bad_personalities += 1
        if player.adaptibility == "L":
            bad_personalities += 1
        if player.loyalty == "L":
            bad_personalities += 1
        if player.leadership == "L":
            bad_personalities += 1
        if player.greed == "H":
            bad_personalities += 1

        bad_personalities_modifier_weight = cls.bad_personality_modifier_model.rank(
            model_weight
        )
        if bad_personalities > 5:
            personality_modifier *= 0.5**bad_personalities_modifier_weight
        elif bad_personalities > 4:
            personality_modifier *= 0.7**bad_personalities_modifier_weight
        elif bad_personalities > 3:
            personality_modifier *= 0.92**bad_personalities_modifier_weight

        if player.leadership == "H":
            leadership_modifier = 1.2 ** cls.high_leadership_modifier_model.rank(
                model_weight
            )
            personality_modifier *= leadership_modifier
        elif player.leadership == "L":
            low_leadership_modifier = 0.85 ** cls.low_leadership_modifier_model.rank(
                model_weight
            )
            personality_modifier *= low_leadership_modifier

        total_modifier = personality_modifier
        return total_modifier
