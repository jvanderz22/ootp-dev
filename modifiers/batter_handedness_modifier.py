from modifiers.base_modifier import BaseModifier


batter_handedness_modifiers = {"Switch": 1.04, "Right": 1, "Left": 1.015}


class BatterHandednessModifier(BaseModifier):
    @classmethod
    def calculate_player_modifier(cls, player):
        return batter_handedness_modifiers[player.bat_hand]
