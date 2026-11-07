"""The two kinds of stage a profile's pipeline is built from."""
from abc import ABC, abstractmethod


class BatchStage(ABC):
    """Runs per batch on player-local state (`ranking.state.PlayerState`)."""

    name = ""

    @abstractmethod
    def run(self, states: list, profile) -> None: ...


class PoolStage(ABC):
    """Runs once over every result, after the pre-demand ordering is known."""

    name = ""

    @abstractmethod
    def run(self, results: list, profile) -> None: ...
