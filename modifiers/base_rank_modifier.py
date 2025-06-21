from abc import ABC, abstractmethod


class BaseRankModifier(ABC):
    @classmethod
    def calculate_modified_score(cls, player, rank):
        return cls.calculate_player_modifier(player, rank)

    @abstractmethod
    def calculate_player_modifier(cls, player, rank):
        pass
