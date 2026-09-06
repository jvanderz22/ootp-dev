from dataclasses import dataclass, field


@dataclass
class ScoredPlayer:
    """One player's ranking result plus the handful of identity fields the output
    CSVs need. Deliberately lightweight: the batched ranker keeps a list of these
    for the whole pool while only ~`batch_size` `GamePlayer` objects are ever
    resident, so a 15k-player league can be scored without holding it all at once.
    """

    id: str
    name: str
    position: str
    age: int
    in_game_overall: int
    in_game_potential: int
    demand: str

    position_player_score: float
    fielding_score_component: float
    batting_score_component: float
    running_score_component: float
    pitcher_score: float
    starter_component: float
    reliever_component: float

    raw_overall_score: float
    # the fielding position the model scores this player highest at (None for
    # pitchers / anyone with no positive fielding score)
    best_position: str = None
    overall_score: float = None
    components: dict = field(default_factory=dict)
