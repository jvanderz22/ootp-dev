from models.game_players import GamePlayer
from modifiers.base_modifier import BaseModifier
from utils.rank_graditated_model import RankGradiatedModel


class PitcherInjuryModifier(BaseModifier):
    modifier_weight_model = RankGradiatedModel(
        [0, 38, 60, 80, 130],
        [1, 1, 0.4, 0.3, 0.2],
    )

    @classmethod
    def calculate_player_modifier(cls, player: GamePlayer, model_score):
        modifier = 1
        modifier_weight = cls.modifier_weight_model.rank(model_score)
        injury_prone = player.injury_prone

        if injury_prone == "Durable":
            base_durable_modifier = 1.11
            modifier = base_durable_modifier**modifier_weight
        elif injury_prone == "Fragile":
            base_fragile_modifier = 0.6
            modifier = base_fragile_modifier**modifier_weight
        return modifier
