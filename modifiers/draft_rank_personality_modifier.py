from modifiers.base_rank_modifier import BaseRankModifier
from utils.rank_graditated_model import RankGradiatedModel


class DraftRankPersonalityModifier(BaseRankModifier):
    modifier_model = RankGradiatedModel(
        [10, 25, 50, 75, 100, 150, 200, 300, 350, 650],
        [0.02, 0.05, 0.1, 0.2, 0.3, 0.5, 0.7, 0.9, 1, 1.15],
    )
    high_leadership_modifier_model = RankGradiatedModel(
        [100, 150, 300, 500, 700], [0, 0.2, 0.4, 0.8, 1]
    )
    low_leadership_modifier_model = RankGradiatedModel([250, 350, 600], [0, 0.5, 1])
    bad_personality_modifier_model = RankGradiatedModel([0, 350, 600], [1, 1, 1.5])

    @classmethod
    def calculate_player_modifier(cls, player, rank):
        personality_modifier = 1
        modifier_weight = cls.modifier_model.rank(rank)

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
            rank
        )
        if bad_personalities > 5:
            personality_modifier *= 0.5**bad_personalities_modifier_weight
        elif bad_personalities > 4:
            personality_modifier *= 0.7**bad_personalities_modifier_weight
        elif bad_personalities > 3:
            personality_modifier *= 0.92**bad_personalities_modifier_weight

        if player.leadership == "H":
            leadership_modifier = 1.2 ** cls.high_leadership_modifier_model.rank(rank)
            personality_modifier *= leadership_modifier
        elif player.leadership == "L":
            low_leadership_modifier = 0.85 ** cls.low_leadership_modifier_model.rank(
                rank
            )
            personality_modifier *= low_leadership_modifier
        if player.work_ethic == "H" and player.intelligence == "H":
            personality_modifier *= 1.2

        total_modifier = personality_modifier**modifier_weight
        return total_modifier
