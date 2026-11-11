"""The draft odds on the draft board (ranking/draft_odds.py)."""
import csv
import io

import numpy as np
import pandas as pd
import pytest

from models.game_players import GamePlayer
from ranking import draft_odds, get_ranker, value
from ranking.fitting import draft_odds as fit
from ranking.ledger import DEMAND, DEVELOPMENT, MODIFIERS
from ranking.ratings import RatingsView
from tests.e2e_fixtures import make_draft_class_csv


@pytest.fixture(scope="module")
def rows():
    return list(csv.DictReader(io.StringIO(make_draft_class_csv(n=120, seed=11))))


@pytest.fixture(scope="module")
def ranked(rows):
    return get_ranker("draft_class").rank([GamePlayer(dict(r)) for r in rows], batch_size=50)


@pytest.mark.parametrize("velocity, factor", [
    ("93-95", 1.0), ("94-96", 1.05), ("96-98", 1.10), ("98-100", 1.12), ("101-103", 1.15), ("", 1.0), (None, 1.0),
])
def test_velocity_is_an_upside_never_a_penalty(velocity, factor):
    assert draft_odds.velocity_factor(velocity) == factor
    assert draft_odds.velocity_factor("99-101", knuckleball=True) == 1.0


def test_the_board_reads_the_columns_the_fit_was_fit_on(rows):
    # the runtime's columns are the fit's design matrices, row for row
    odds, view = draft_odds.load(), RatingsView("potential")
    rng = np.random.default_rng(0)
    players = [GamePlayer(dict(r)) for r in rows]
    frame = pd.DataFrame([{
        "war_pot": float(rng.uniform(-0.5, 7)), "readiness": float(rng.uniform(-5, 4)),
        "group": rng.choice(["hitter", "SP", "RP"]), "draft_age": float(rng.uniform(16.5, 23.5)),
        "we": p.work_ethic, "int": p.intelligence,
        "prone": p.injury_prone, "ad": p.adaptibility, "velo": r.get("VT"), "stuff": r.get("STU P"),
        "pitches": view.pitch_count(p), "years": fit.REFERENCE_YEARS,
    } for p, r in zip(players, rows)])
    mean, growth = fit.design(frame), fit.growth_design(frame)
    for i, (player, row) in enumerate(zip(players, frame.itertuples())):
        runtime = odds.mean_columns(player, row.war_pot, row.readiness, row.group, row.draft_age)
        assert runtime == pytest.approx(mean.iloc[i].to_dict()), player.name
        runtime = odds.growth_columns(player, row.war_pot, row.readiness, row.group, row.pitches, row.draft_age)
        assert runtime == pytest.approx(growth.iloc[i].to_dict()), player.name


def test_the_odds_replace_the_development_factors_and_their_modifiers(ranked):
    replaced = {*draft_odds.REPLACES, "PersonalityModifier", "BatterInjuryModifier", "PitcherInjuryModifier"}
    assert not [l for r in ranked for l in r.ledger.lines if l.stage == MODIFIERS and l.label in replaced]
    assert not [l for r in ranked for l in r.ledger.lines if l.label.startswith(("work ethic", "durability"))]
    assert get_ranker("draft_class").manifest()["artifact_versions"]["draft_odds"] == draft_odds.ARTIFACT


def test_the_lines_take_his_ceiling_to_what_hes_expected_to_realize(ranked):
    for r in ranked:
        lines = [l for l in r.ledger.lines if r.ledger.counted(l)]
        labels = [l.label for l in lines if l.stage == DEVELOPMENT]
        assert labels[0] == "Base rate" and labels[-1] == "Breakout"
        before_demand = sum(l.delta for l in lines if l.stage != DEMAND)
        assert before_demand == pytest.approx(r.pre_demand_score)
        # never below replacement: the odds order the bottom of the board
        assert r.pre_demand_score >= value.DISPLAY_OFFSET


def test_the_card_gets_the_ceiling_the_range_and_the_chances(ranked):
    for r in ranked:
        assert r.ceiling_war is not None
        assert 0 <= r.war_low <= r.war_high
        assert 0 <= r.p_regular <= 1 and 0 < r.p_outgrows < 1
    # a higher ceiling raises the chance he becomes a regular, on average
    top = sorted(ranked, key=lambda r: -r.ceiling_war)
    assert np.mean([r.p_regular for r in top[:20]]) > np.mean([r.p_regular for r in top[-20:]])


def test_pitchers_carry_the_balance_and_their_velocity(ranked):
    pitchers = [r for r in ranked if r.ledger.side == "pitching"]
    assert pitchers and all(any(l.label == "pitcher balance" for l in r.ledger.lines) for r in pitchers)
    hitters = [r for r in ranked if r.ledger.side == "batting"]
    assert not any(l.label == "pitcher balance" and r.ledger.counted(l) for r in hitters for l in r.ledger.lines)


def test_a_reliever_realizes_less_of_his_ceiling_than_a_starter():
    # the reliever factor is refit on the exports that rate draftee relievers
    # like today's (2026-11-10): the fit's own classes overrated them ~3x
    odds = draft_odds.load().a
    assert odds["role"]["RP"] < odds["role"]["SP"] < 1
    assert odds["check"]["reliever"]["fit"] > odds["role"]["RP"]


def test_the_board_reads_on_a_fixed_1_to_100_scale(ranked):
    # the display only (2026-11-10): the curve keeps the order and the anchors
    # sit at the 2033-42 classes' best, so nobody there passes 100
    from web.service import _draft_scores
    assert value.draft_score(None) is None
    assert value.draft_score(-1.0) == value.draft_score(0.0) == 1
    assert value.draft_score(value.DRAFT_SCALE["value"]) == value.draft_score(9.0) == 100
    assert value.draft_score(value.DRAFT_SCALE["ceiling"] / 4, "ceiling") == 50
    for r in ranked:
        payload = {"model_score": r.overall_score, "war": (r.pre_demand_score - value.DISPLAY_OFFSET) / value.DISPLAY_SCALE,
                   "ceiling_war": r.ceiling_war, "war_low": r.war_low, "war_high": r.war_high}
        s = _draft_scores(payload)
        assert 1 <= s["value_score"] <= 100
        assert 1 <= s["ceiling_score"] <= 100
    scores = [_draft_scores({"model_score": r.overall_score, "war": 0, "ceiling_war": 0, "war_low": 0,
                             "war_high": 0})["score"] for r in sorted(ranked, key=lambda r: -r.overall_score)]
    assert scores == sorted(scores, reverse=True)
    assert _draft_scores({"model_score": 60.0, "war": 1.0, "ceiling_war": 2.0, "war_low": None,
                          "war_high": None}) == dict.fromkeys(s)


def test_the_draft_age_is_on_may_1_of_the_year_the_export_was_pulled():
    def player(born, age):
        return GamePlayer({"DOB": born, "Age": str(age)})
    # the export's Age runs a year ahead for whoever's birthday passed before
    # it was pulled; the January and February births give the year away
    export = [player("01/15/2021", 21), player("02/03/2020", 22), player("05/02/2020", 22), player("09/30/2020", 21)]
    assert draft_odds.draft_year(export) == 2042
    assert draft_odds.draft_age(export[2], 2042) == pytest.approx(21.997, abs=0.001)
    assert draft_odds.draft_age(export[3], 2042) == pytest.approx(21.58, abs=0.01)
    # no date of birth: the export's Age, halfway through the year
    assert draft_odds.draft_age(player("", 21), 2042) == 21.5
    assert draft_odds.draft_year([player("", 21)]) is None


def test_a_draft_age_reads_between_the_knots(rows):
    # a draftee nearly 22 reads mostly as a 22, one just 21 as a 21; no cliff
    # at the birthday, and nobody gets cheaper by being younger past 21
    odds = draft_odds.load()

    def ev(age):
        player = GamePlayer(dict(rows[0]))
        return odds.expected(odds.mean_columns(player, 4.0, -1.5, "hitter", age), age)
    assert ev(21.99) == pytest.approx(ev(22.01), rel=0.03)   # the ramp, not a cliff
    assert ev(21.0) > ev(21.5) > ev(21.9) > ev(22.0)
    assert odds.ages(21.75) == pytest.approx({"18": 0.0, "22": 0.75})
    assert odds.ages(19.5) == pytest.approx({"18": 0.5, "22": 0.0})


def test_a_draftee_near_mlb_ready_keeps_half_his_age_penalty_from_21_5(rows):
    # judgment (2026-11-11): half the penalty of his age from 21.5 to 22 eased
    # - none at -1 WAR now, half from 0 up - from a draft age of 20, in full
    # from 21; the Regular chance eases with it
    odds = draft_odds.load()

    def lines(age, readiness):
        player = GamePlayer(dict(rows[0]))
        growth = odds.growth_columns(player, 4.0, readiness, "hitter", 0, age)
        return dict((label, value) for _, label, value, _, _ in
                    odds.reaching(player, 4.0, readiness, "hitter", growth, age)[0])

    full, part, none = lines(22.0, 0.5), lines(22.0, -0.5), lines(22.0, -1.5)
    assert full["Age 22.0"] < 1
    # 21.5 to 22 is half the age line's drop from 21 to 22, on the logit
    assert full["Polish"] == pytest.approx(full["Age 22.0"] ** -0.25)
    assert part["Polish"] == pytest.approx(full["Age 22.0"] ** -0.125)
    assert lines(20.5, 0.5)["Polish"] == pytest.approx(part["Polish"])
    assert lines(21.0, 0.5)["Polish"] == pytest.approx(full["Polish"])
    assert "Polish" not in none and "Polish" not in lines(19.9, 1.0)

    def regular(age, readiness):
        player = GamePlayer(dict(rows[0]))
        cols = odds.mean_columns(player, 4.0, readiness, "hitter", age)
        growth = odds.growth_columns(player, 4.0, readiness, "hitter", 0, age)
        return odds.distribution(cols, growth, 4.0, "hitter", odds.expected(cols, age), 1.0, age)["regular"]
    assert regular(22.0, 0.0) > regular(22.0, -1.0) and regular(21.0, 0.0) > regular(21.0, -1.0)
