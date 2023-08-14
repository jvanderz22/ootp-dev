from abc import ABC, abstractclassmethod


class BaseRankModifier(ABC):
    @classmethod
    def calculate_modified_score(cls, player, rank, score):
        modifier = cls.calculate_player_modifier(player, rank)
        return score * modifier

    @abstractclassmethod
    def calculate_player_modifier(cls, player, rank):
        pass
