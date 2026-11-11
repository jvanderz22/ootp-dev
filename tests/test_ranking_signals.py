"""The signal inventory (ranking/signals.py): reads are measured by tracing
what each model, scorer and modifier reads while a profile ranks."""
import csv
import io

from models.game_players import GamePlayer
from models.scored_player import ScoredPlayer
from ranking import PROFILES, get_ranker
from ranking.signals import POTENTIAL_RATINGS, Inventory, inventory
from tests.e2e_fixtures import make_draft_class_csv


def _players():
    rows = csv.DictReader(io.StringIO(make_draft_class_csv(n=160, seed=7)))
    return [GamePlayer(r) for r in rows]


def test_draft_reads_are_attributed_to_their_readers():
    inv = inventory(get_ranker("draft_class"), _players())
    assert inv.players == 160
    assert inv.reads["DraftDemandModifier"] == {"DEM"}  # read off the result
    # the draft odds read his age and makeup, and a pitcher's velocity and Stuff
    assert {"Age", "WE", "INT", "Prone", "AD", "VT", "STU P"} == inv.reads["draft odds"]
    assert {"K P", "POW P"} <= inv.reads["batting talent"]
    # a class without BABIP is read through Contact, so the legacy batting grid never runs
    assert "batting model" not in inv.reads
    assert "SctAcc" in inv.reads["ScoutingAccuracyModifier"]
    # the fitted talent layers read the profile's side only
    assert {"STU P", "MOV P", "CONT P", "STM"} <= inv.reads["pitching talent"]
    assert not {"STU", "MOV", "CONT"} & inv.reads["pitching talent"]
    # every pitcher is scored by the fitted model, so the legacy pitcher scorer never runs
    assert "pitcher scorer (role adjustments)" not in inv.reads


def test_v2_reads_nothing_through_the_legacy_scorers():
    legacy = {"batting model", "running model", "pitching models", "batting scorer",
              "pitcher scorer (role adjustments)"}
    for method in PROFILES:
        assert not legacy & set(inventory(get_ranker(method), _players()).reads), method


def test_flags_composites_and_repeat_reads_by_side():
    inv = inventory(get_ranker("draft_class"), _players())
    batting, pitching = inv.flags("batting"), inv.flags("pitching")
    # Contact is half Avoid K, and the batting model reads both
    assert any("K P" in note for note in batting["CON P"])
    assert batting["K P"]
    assert "4 readers" not in str(batting)  # no batting rating is read 4 times here
    assert "2 readers" in pitching["STU P"]   # the pitching talent and the draft odds' growth
    # a batting-only modifier doesn't feed the pitching side
    assert inv.sides("BatterHitProfileModifier") == {"batting"}
    assert "BatterHitProfileModifier" not in str(inv.by_rating("pitching"))
    # shared modifiers feed both, and so do the odds
    assert inv.sides("ScoutingAccuracyModifier") == {"batting", "pitching"}
    assert inv.sides("draft odds") == {"batting", "pitching"}


def test_flags_potential_reads_in_a_current_profile():
    inv = Inventory(PROFILES["overall"], 1, {"pitching models": {"MOV P", "STU"}})
    assert inv.flags("pitching") == {"MOV P": ["a potential rating in a current-ratings profile"]}


def test_current_scoring_reads_no_potential_ratings():
    # the HR-risk and knuckleball checks used potential Movement / pitches
    inv = inventory(get_ranker("overall"), _players())
    for side in ("batting", "pitching"):
        assert not set(inv.by_rating(side)) & POTENTIAL_RATINGS


def test_tracing_is_removed_afterwards():
    inventory(get_ranker("overall"), _players()[:20])
    assert "__getattribute__" not in vars(GamePlayer)
    assert "__getattribute__" not in vars(ScoredPlayer)
