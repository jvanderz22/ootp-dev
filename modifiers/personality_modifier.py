from modifiers.base_modifier import BaseModifier


class PersonalityModifier(BaseModifier):
    @classmethod
    def calculate_player_modifier(cls, player):
        modifier = 1

        if player.intelligence == "H":
            modifier *= 1.05
        elif player.intelligence == "L":
            modifier *= 0.9

        if player.work_ethic == "H":
            modifier *= 1.05
        elif player.work_ethic == "L":
            modifier *= 0.9
        return modifier
