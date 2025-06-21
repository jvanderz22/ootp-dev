from abc import ABC, abstractmethod


class BaseModifier(ABC):
    @abstractmethod
    def calculate_player_modifier(cls, player):
        pass
