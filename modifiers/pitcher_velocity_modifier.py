import re

from modifiers.base_modifier import BaseModifier


class PitcherVelocityModifier(BaseModifier):
    @classmethod
    def calculate_player_modifier(cls, player):
        modifier = 1
        if len(player.velocity) == 1:
            return modifier
        lower_velo = int(re.search(r"\d+", player.velocity)[0])

        has_knuckleball = "knuckleball" in player.get_pitches()
        if has_knuckleball:
            return modifier

        if lower_velo <= 87:
            modifier *= 0.88
        elif lower_velo <= 90:
            modifier *= 0.93
        elif lower_velo <= 91:
            modifier *= 0.95
        elif lower_velo <= 92:
            modifier *= 0.965
        elif lower_velo <= 93:
            modifier *= 0.98
        elif lower_velo <= 95:
            modifier *= 1
        elif lower_velo <= 97:
            modifier *= 1.02
        elif lower_velo <= 99:
            modifier *= 1.05
        elif lower_velo <= 102:
            modifier *= 1.07
        elif lower_velo <= 110:
            modifier *= 1.08

        return modifier
