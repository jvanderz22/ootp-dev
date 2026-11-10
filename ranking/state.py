"""Per-player working state while a batch flows through the batch stages.

Discarded once the batch is turned into results - only what `RankedResult`
keeps outlives it, so a 15k-player league is never resident at once.
"""
from dataclasses import dataclass, field

from models.game_players import GamePlayer
from ranking.ledger import Ledger


@dataclass(slots=True)
class SideState:
    model_score: float = 0.0   # before the side's modifiers
    score: float = 0.0         # after them
    # batting: batting / fielding / running; pitching: starter / reliever
    components: dict = field(default_factory=dict)
    best_position: str = None
    # where the side is valued: his best position, or SP / RP
    role: str = None
    # the profile's modifiers as (name, factor), for the value layer to replay
    modifiers: list = field(default_factory=list)


@dataclass(slots=True)
class PlayerState:
    player: GamePlayer
    batting: SideState = field(default_factory=SideState)
    pitching: SideState = field(default_factory=SideState)
    ledger: Ledger = field(default_factory=Ledger)
    value: float = 0.0         # sides combined, before demand
    # the fitted talent layers' modeled line: wRC+, and ERA in the role the
    # pitching side is judged in (None where a legacy model scored the side)
    wrc_plus: float = None
    era: float = None
    # the fitted talent layers' outputs by side ("batting", "fielding",
    # "running", "pitching"; None where a legacy model scored it)
    fitted: dict = None
