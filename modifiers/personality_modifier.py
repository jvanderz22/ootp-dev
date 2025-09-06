from models.game_players import GamePlayer
from modifiers.base_modifier import BaseModifier

work_ethic_age_modifier_impact = {
    17: 1.4,
    18: 1.4,
    19: 1.3,
    20: 1.2,
    21: 1.1,
    22: 1.05,
}


class PersonalityModifier(BaseModifier):
    @classmethod
    def calculate_player_modifier(cls, player: GamePlayer, _model_score):
        modifier = 1

        if player.intelligence == "H":
            modifier *= 1.04
        elif player.intelligence == "L":
            modifier *= 0.93

        work_ethic_modifier = 1
        if player.work_ethic == "H":
            work_ethic_modifier = 1.05
        elif player.work_ethic == "L":
            work_ethic_modifier = 0.9

        if player.age <= 20:
            work_ethic_age_modifier = work_ethic_age_modifier_impact.get(player.age, 1)
            work_ethic_modifier = work_ethic_modifier**work_ethic_age_modifier

        modifier *= work_ethic_modifier
        return modifier
