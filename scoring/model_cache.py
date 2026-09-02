"""Process-wide cache of scorer instances.

The attribute models train lazily from training_data/*.csv on first use and then
cache on the scorer instance. Building a fresh scorer per web request would
retrain ~13 XGBoost models every time, so hand out memoized instances keyed by
their constructor arguments. `warm()` is called at server startup to pay the
training cost once, up front.
"""
from functools import lru_cache

from scoring.pitcher_scorer import RP_OVERALL_MODIFIER, PitcherScorer
from scoring.position_player_scorer import PositionPlayerScorer


@lru_cache(maxsize=None)
def get_position_player_scorer(score_type: str = "potential") -> PositionPlayerScorer:
    return PositionPlayerScorer(score_type)


@lru_cache(maxsize=None)
def get_pitcher_scorer(
    score_type: str = "potential", rp_multiplier: float = RP_OVERALL_MODIFIER
) -> PitcherScorer:
    return PitcherScorer(type=score_type, rp_multiplier=rp_multiplier)


def warm() -> None:
    """Train and cache every scorer/model combination the rankers use."""
    from models.game_players import GamePlayers

    # A single synthetic player is enough to force every lazy model to train.
    sample = GamePlayers([_SAMPLE_ROW]).game_players[0]
    for score_type in ("potential", "overall"):
        get_position_player_scorer(score_type).score(sample)
    for score_type in ("potential", "overall"):
        for rp_multiplier in (RP_OVERALL_MODIFIER, RP_OVERALL_MODIFIER - 0.1):
            get_pitcher_scorer(score_type, rp_multiplier).score(sample)


# Minimal row covering the fields the scorers read; values are mid-scale ratings.
_SAMPLE_ROW = {
    "ID": "0", "POS": "SP", "Name": "Warm Up", "Age": "20", "ORG": "-", "Lev": "-",
    "OVR": "40", "POT": "50", "DEM": "$1.0m", "Sign": "Easy", "SctAcc": "Average",
    "T": "Right", "B": "Right", "Prone": "Normal", "AD": "N", "LOY": "N", "FIN": "N",
    "INT": "N", "WE": "N", "LEA": "N",
    "CON P": "40", "GAP P": "40", "POW P": "40", "EYE P": "40", "K P": "40",
    "CON": "40", "GAP": "40", "POW": "40", "EYE": "40", "K's": "40",
    "BBT": "Normal", "GBT": "Normal", "FBT": "Normal",
    "SPE": "40", "STE": "40", "RUN": "40",
    "C ARM": "40", "C ABI": "40", "C FRM": "40",
    "IF RNG": "40", "IF ARM": "40", "IF ERR": "40", "TDP": "40",
    "OF RNG": "40", "OF ARM": "40", "OF ERR": "40",
    "STU P": "40", "MOV P": "40", "CONT P": "40",
    "STU": "40", "MOV": "40", "CONT": "40",
    "STM": "45", "VT": "92-94", "G/F": "NEU",
    "FBP": "45", "CHP": "40", "CBP": "40", "SLP": "40", "SIP": "-", "SPP": "-",
    "CTP": "-", "FOP": "-", "CCP": "-", "SCP": "-", "KNP": "-", "KCP": "-",
}
