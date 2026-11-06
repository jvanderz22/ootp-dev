"""The two kinds of stage a profile's pipeline is built from."""
from abc import ABC, abstractmethod


class BatchStage(ABC):
    """Runs per batch on player-local state (`ranking.state.PlayerState`)."""

    name = ""
    # the ratings this stage reads, for the signal inventory report
    reads = frozenset()

    @abstractmethod
    def run(self, states: list, profile) -> None: ...


class PoolStage(ABC):
    """Runs once over every result, after the pre-demand ordering is known."""

    name = ""
    reads = frozenset()

    @abstractmethod
    def run(self, results: list, profile) -> None: ...
