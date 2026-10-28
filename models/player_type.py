"""Hitter / Pitcher / Two-way - which side(s) of the model a player is judged on.

Every player is run through both the position-player and the pitcher scorer;
this decides which of those results matter for him. The score breakdown keeps
only the relevant side(s) (`prune_breakdown`), and the web layer shows it as
the player's `type`. Mirrors printers/draft_prospect_printer.py.
"""

HITTER = "Hitter"
PITCHER = "Pitcher"
TWO_WAY = "Two-way"


def classify(position_player_score, pitcher_score) -> str:
    pp = position_player_score or 0
    pit = pitcher_score or 0
    hi, lo = max(pp, pit), min(pp, pit)
    if hi > 0 and lo * 2 > hi:
        return TWO_WAY
    return PITCHER if pit >= pp else HITTER


def prune_breakdown(breakdown: dict, player_type: str) -> dict:
    """Drop the side of a score breakdown that doesn't apply to `player_type`."""
    drop = {HITTER: "pitching", PITCHER: "batting"}.get(player_type)
    return {k: v for k, v in breakdown.items() if k != drop}
