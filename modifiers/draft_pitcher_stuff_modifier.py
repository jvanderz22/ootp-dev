from modifiers.base_modifier import BaseModifier


class DraftPitcherStuffModifier(BaseModifier):
    @classmethod
    def calculate_player_modifier(cls, player):
        modifier = 1
        if player.position == "SP":
            if player.stuff <= 40:
                modifier *= 0.88
            elif player.stuff <= 45:
                modifier *= 0.93
            elif player.stuff <= 50:
                modifier *= 0.96
            elif player.stuff <= 55:
                modifier *= 0.985
        else:
            if player.stuff <= 45:
                modifier *= 0.88
            elif player.stuff <= 50:
                modifier *= 0.93
            elif player.stuff <= 55:
                modifier *= 0.96
            elif player.stuff <= 60:
                modifier *= 0.985
        return modifier
