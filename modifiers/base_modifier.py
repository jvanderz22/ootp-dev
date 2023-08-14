from abc import ABC, abstractclassmethod


class BaseModifier(ABC):
    @classmethod
    def calculate_modified_score(cls, player, score):
        modifier = cls.calculate_modified_score(player)
        return score * modifier

    @abstractclassmethod
    def calculate_player_modifier(cls, player):
        pass
