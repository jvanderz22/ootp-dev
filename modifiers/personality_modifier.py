from modifiers.base_modifier import BaseModifier


class PersonalityModifier(BaseModifier):
    @classmethod
    def calculate_player_modifier(cls, player):
        modifier = 1

        if player.intelligence == "High":
            modifier *= 1.05
        elif player.intelligence == "Low":
            modifier *= 0.9

        if player.work_ethic == "High":
            modifier *= 1.05
        elif player.work_ethic == "Low":
            modifier *= 0.9
        return modifier
