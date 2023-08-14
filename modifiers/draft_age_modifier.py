from modifiers.base_modifier import BaseModifier


age_modifiers = {17: 1.1, 18: 1.07, 19: 1.02, 20: 1, 21: 1, 22: 0.97, 23: 0.93}


class DraftAgeModifier(BaseModifier):
    @classmethod
    def calculate_player_modifier(cls, player):
        modifier = age_modifiers.get(player.age, 0.9)
        return modifier
