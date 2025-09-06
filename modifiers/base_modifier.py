from abc import ABC, abstractmethod

from models.game_players import GamePlayer


class BaseModifier(ABC):
    @abstractmethod
    def calculate_player_modifier(cls, player: GamePlayer):
        pass
