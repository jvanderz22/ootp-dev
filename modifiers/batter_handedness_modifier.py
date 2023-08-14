from modifiers.base_modifier import BaseModifier


class BatterHandednessModifier(BaseModifier):
    @classmethod
    def calculate_player_modifier(cls, player):
        modifier = 1
        if player.bat_hand == "Switch":
            modifier *= 1.03
        return modifier
