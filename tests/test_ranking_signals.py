"""The signal inventory (ranking/signals.py): reads are measured by tracing
what each model, scorer and modifier reads while a profile ranks."""
import csv
import io

from models.game_players import GamePlayer
from models.scored_player import ScoredPlayer
from ranking import get_ranker
from ranking.signals import inventory
from tests.e2e_fixtures import make_draft_class_csv


def _players():
    rows = csv.DictReader(io.StringIO(make_draft_class_csv(n=160, seed=7)))
    return [GamePlayer(r) for r in rows]


def test_draft_reads_are_attributed_to_their_readers():
    inv = inventory(get_ranker("draft_class"), _players())
    assert inv.players == 160
    assert inv.reads["DraftDemandModifier"] == {"DEM"}  # read off the result
    assert inv.reads["AgeModifier"] == {"Age"}
    assert {"CON P", "K P", "POW P"} <= inv.reads["batting model"]
    assert "SctAcc" in inv.reads["ScoutingAccuracyModifier"]
    # the SP / RP what-if copies read both Stuffs only to shift them
    assert not {"STU", "STU P"} & inv.reads["pitcher scorer (role adjustments)"]


def test_flags_composites_and_repeat_reads_by_side():
    inv = inventory(get_ranker("draft_class"), _players())
    batting, pitching = inv.flags("batting"), inv.flags("pitching")
    # Contact is half Avoid K, and the batting model reads both
    assert any("K P" in note for note in batting["CON P"])
    assert batting["K P"]
    assert "4 readers" not in str(batting)  # no batting rating is read 4 times here
    assert "3 readers" in pitching["STU P"] or "4 readers" in pitching["STU P"]
    # a batting-only modifier doesn't feed the pitching side
    assert inv.sides("BatterHitProfileModifier") == {"batting"}
    assert "BatterHitProfileModifier" not in str(inv.by_rating("pitching"))
    # shared modifiers feed both
    assert inv.sides("AgeModifier") == {"batting", "pitching"}


def test_flags_potential_reads_in_a_current_profile():
    inv = inventory(get_ranker("overall"), _players())
    # the HR-risk modifier keys off Movement's potential, even on current ratings
    assert "a potential rating in a current-ratings profile" in inv.flags("pitching")["MOV P"]


def test_tracing_is_removed_afterwards():
    inventory(get_ranker("overall"), _players()[:20])
    assert "__getattribute__" not in vars(GamePlayer)
    assert "__getattribute__" not in vars(ScoredPlayer)
