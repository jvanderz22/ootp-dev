"""The prospect odds on the prospect board (ranking/prospect_odds.py)."""
import csv
import io

import numpy as np
import pandas as pd
import pytest

from league_snapshot import join_rows
from models.game_players import GamePlayer
from ranking import draft_odds, get_ranker, prospect_odds, value
from ranking.fitting import prospect_odds as fit
from ranking.ledger import DEMAND, DEVELOPMENT, MODIFIERS
from tests.e2e_fixtures import make_draft_class_csv
from tests.test_league_snapshot import make_snapshot_csvs


@pytest.fixture(scope="module")
def ranked():
    return get_ranker("potential").rank([GamePlayer(dict(r)) for r in join_rows(*make_snapshot_csvs())])


@pytest.fixture(scope="module")
def players():
    return [GamePlayer(dict(r)) for r in csv.DictReader(io.StringIO(make_draft_class_csv(n=60, seed=5)))]


def test_the_board_reads_the_columns_the_fit_was_fit_on(players):
    odds, rng = prospect_odds.load(), np.random.default_rng(0)
    frame = pd.DataFrame([{
        "war_pot": float(rng.uniform(-0.5, 7)), "readiness": float(rng.uniform(-5, 4)),
        "group": rng.choice(["hitter", "SP", "RP"]), "age_exact": float(rng.uniform(16.5, 30)),
        "we": p.work_ethic, "int": p.intelligence, "prone": p.injury_prone, "years": fit.REFERENCE_YEARS,
    } for p in players])
    close, keep = fit.design(frame), fit.keep_design(frame)
    for i, (player, row) in enumerate(zip(players, frame.itertuples())):
        runtime = odds.close_columns(player, row.war_pot, row.readiness, row.group, row.age_exact)
        assert runtime == pytest.approx(close.iloc[i].to_dict()), player.name
        assert odds.keep_columns(row.readiness, row.age_exact) == pytest.approx(keep.iloc[i].to_dict())


def test_the_odds_replace_the_development_factors_and_their_modifiers(ranked):
    replaced = {*prospect_odds.REPLACES, "PersonalityModifier", "BatterInjuryModifier", "PitcherInjuryModifier"}
    assert not [l for r in ranked for l in r.ledger.lines if l.stage == MODIFIERS and l.label in replaced]
    assert not [l for r in ranked for l in r.ledger.lines if l.label.startswith(("work ethic", "durability"))]
    versions = get_ranker("potential").manifest()["artifact_versions"]
    assert versions["prospect_odds"] == prospect_odds.ARTIFACT and versions["draft_odds"] == draft_odds.ARTIFACT


def test_the_lines_take_his_ceiling_to_what_hes_expected_to_realize(ranked):
    for r in ranked:
        lines = [l for l in r.ledger.lines if r.ledger.counted(l)]
        labels = {l.label for l in lines if l.stage == DEVELOPMENT}
        assert labels <= {"Past his ceiling", "WAR now", "Gap", "Runway", "Upside", "Switch hitter"}
        assert sum(l.delta for l in lines if l.stage != DEMAND) == pytest.approx(r.pre_demand_score)
        assert r.pre_demand_score >= value.DISPLAY_OFFSET
        # no distribution yet: the ceiling, but no range
        assert r.ceiling_war is not None and r.war_low is None


def test_a_teen_is_valued_as_a_draftee_blended_in_by_22(players):
    odds, player = prospect_odds.load(), players[0]

    def expected(age):
        parts = odds.parts(player, 4.0, -1.5, "hitter", age)
        return parts, odds.expected(parts)
    parts, e = expected(19.0)
    assert parts["bridged"] == 1 and e == pytest.approx(parts["draft"])
    parts, e = expected(21.0)
    assert e == pytest.approx((parts["draft"] + parts["prospect"]) / 2)
    # past the bridge, once he's well above replacement (a raw 22-year-old is
    # on schedule, read as 21.5)
    parts = odds.parts(player, 4.0, 1.5, "hitter", 22.5)
    assert parts["draft"] is None and odds.expected(parts) == parts["prospect"]


def test_development_ends_at_27(players):
    odds, player = prospect_odds.load(), players[0]
    young, mid, old = (odds.parts(player, 4.0, 1.0, "hitter", age) for age in (24.5, 26.0, 27.5))
    assert young["close"] > 0 and mid["close"] < young["close"] and old["close"] == 0
    assert odds.expected(old) == pytest.approx(old["keep"] * 1.0)


def test_he_never_realizes_more_than_his_ceiling_or_his_war_now(players):
    # keep and close are odds, so the expectation stays within the larger of
    # his ceiling and his WAR now (past the bridge)
    odds = prospect_odds.load()
    for player in players:
        for ceiling, readiness in ((5.0, 3.0), (2.0, 2.5), (6.0, -2.0)):
            parts = odds.parts(player, ceiling, readiness, "SP", 23.0)
            assert 0 <= odds.expected(parts) <= max(ceiling, readiness)


def test_the_board_weighs_upside_over_present_production(players):
    # what he's expected to add by developing counts `upside` times (2026-11-11)
    odds, player = prospect_odds.load(), players[0]
    gamma = odds.a["upside"]
    assert gamma > 1
    for ceiling, readiness, age in ((5.0, 1.0, 23.0), (6.5, -0.5, 21.0), (3.0, 3.5, 24.0)):
        lines, value, parts = odds.reaching(player, ceiling, readiness, "hitter", age)
        held, expected = parts["held"], odds.expected(parts)
        assert value == pytest.approx(held + gamma * max(expected - held, 0) if expected > held else expected)
        upside = [amount for kind, label, amount, _, _ in lines if label == "Upside"]
        assert sum(upside) == pytest.approx(value - expected)


def test_a_raw_22_or_23_year_old_is_on_schedule():
    # the board reads the fit's on-track age (2026-11-11): flat from 21.5 to
    # 23.5 near replacement, back to his own by 24.5, none from 1 WAR now
    odds = prospect_odds.load()
    for age in (20.5, 21.5, 22.5, 23.5, 24.0, 24.5, 26.0):
        for readiness in (-1.0, 0.0, 0.5, 1.0, 2.0):
            assert odds.on_track_age(age, readiness) == pytest.approx(float(fit.on_track_age(age, readiness)))
    assert odds.on_track_age(22.5, -0.4) == 21.5 and odds.on_track_age(23.5, 0.0) == 21.5
    assert odds.on_track_age(22.5, 1.0) == 22.5 and odds.on_track_age(24.5, -1.0) == 24.5
