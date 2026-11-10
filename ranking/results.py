"""What a v2 ranking returns per player."""
from dataclasses import dataclass, fields

from models.scored_player import ScoredPlayer
from ranking.ledger import Ledger

SCORED_PLAYER_FIELDS = tuple(f.name for f in fields(ScoredPlayer))


@dataclass
class RankedResult(ScoredPlayer):
    """Every `ScoredPlayer` field (so existing consumers keep working), plus the
    value and rank before the demand step as first-class fields, the final rank,
    the ledger, the fitted talent layers' modeled wRC+ and ERA, and the role
    he's valued in (his best position, or SP / RP)."""

    pre_demand_score: float = None
    pre_demand_rank: int = None
    rank: int = None
    ledger: Ledger = None
    wrc_plus: float = None
    era: float = None
    role: str = None
    # v2 pitching: ERA as a starter / reliever, and the innings of his role
    sp_era: float = None
    rp_era: float = None
    ip: float = None
    # v2 on current ratings: the WAR the league's replacement takes off (his
    # spot's price), so his WAR on StatsPlus's scale is his value plus this;
    # None where the profile values him over StatsPlus's replacement
    replacement: float = None
    # his potential ratings' WAR in a full-time role (ranking.profiles.CEILING);
    # None where the profile doesn't score it
    ceiling_war: float = None
    # current ratings: his WAR and role in a full-time role, before the roster
    # sets his spot (ranking.profiles.FULL_TIME); None elsewhere
    full_time_war: float = None
    full_time_role: str = None

    def scored_player_fields(self) -> dict:
        return {name: getattr(self, name) for name in SCORED_PLAYER_FIELDS}
