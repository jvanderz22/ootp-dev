"""What a v2 ranking returns per player."""
from dataclasses import dataclass, fields

from models.scored_player import ScoredPlayer
from ranking.ledger import Ledger

SCORED_PLAYER_FIELDS = tuple(f.name for f in fields(ScoredPlayer))


@dataclass
class RankedResult(ScoredPlayer):
    """Every `ScoredPlayer` field (so existing consumers keep working), plus the
    value and rank before the demand step as first-class fields, the final rank
    and the ledger."""

    pre_demand_score: float = None
    pre_demand_rank: int = None
    rank: int = None
    ledger: Ledger = None

    def scored_player_fields(self) -> dict:
        return {name: getattr(self, name) for name in SCORED_PLAYER_FIELDS}
