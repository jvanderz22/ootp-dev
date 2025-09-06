from models.game_players import GamePlayer
from modifiers.base_modifier import BaseModifier


class PitcherInjuryModifier(BaseModifier):
    @classmethod
    def calculate_player_modifier(cls, player: GamePlayer, _model_score):
        modifier = 1
        injury_prone = player.injury_prone
        is_sp = player.position == "SP"

        if injury_prone == "Durable":
            modifier *= 1.07 if is_sp else 1.04
        elif injury_prone == "Fragile":
            modifier *= 0.6 if is_sp else 0.7
        return modifier
