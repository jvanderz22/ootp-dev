from modifiers.base_modifier import BaseModifier


class BatterInjuryModifier(BaseModifier):
    @classmethod
    def calculate_player_modifier(cls, player):
        modifier = 1
        injury_prone = player.injury_prone
        if injury_prone == "Durable":
            modifier *= 1.035
        elif injury_prone == "Fragile":
            modifier *= 0.8
        return modifier
