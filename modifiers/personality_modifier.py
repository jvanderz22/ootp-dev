from models.game_players import GamePlayer
from modifiers.base_modifier import BaseModifier
from utils.rank_graditated_model import RankGradiatedModel


class PersonalityModifier(BaseModifier):
    modifier_weight_model = RankGradiatedModel(
        [0, 35, 45, 50, 80, 100, 130],
        [2, 2, 1.2, 1, 0.8, 0.5, 0.3],
    )

    age_modifier_impact = {
        16: 1.38,
        17: 1.34,
        18: 1.3,
        19: 1.2,
        20: 1.1,
        21: 1,
        22: 0.8,
        23: 0.75,
        24: 0.7,
    }

    @classmethod
    def calculate_player_modifier(cls, player: GamePlayer, model_score: float):
        int_modifier = 1

        if player.intelligence == "H":
            int_modifier = 1.03
        elif player.intelligence == "L":
            int_modifier = 0.97

        work_ethic_modifier = 1
        if player.work_ethic == "H":
            work_ethic_modifier = 1.05
        elif player.work_ethic == "L":
            work_ethic_modifier = 0.9

        # i.e H INT / H WE: 30 model score + 18 y/o: 1.23
        # i.e H/H: 30 model score + 22 y/o: 1.14
        # i.e H/H 70 model score + 18 y/o: 1.09
        # i.e H/H 70 model score + 22 y/o: 1.06

        # i.e M/L 30 model score + 18 y/o: 0.76
        # i.e M/L 30 model score + 22 y/o: 0.84
        # i.e M/L 70 model score + 18 y/o: 0.89
        # i.e M/L 70 model score + 22 y/o: 0.93

        modifier = work_ethic_modifier * int_modifier
        age_modifier_weight = cls.age_modifier_impact.get(player.age, 0.6)
        model_modifier_weight = cls.modifier_weight_model.rank(model_score)
        total_modifier = (modifier**age_modifier_weight) ** model_modifier_weight

        return total_modifier
