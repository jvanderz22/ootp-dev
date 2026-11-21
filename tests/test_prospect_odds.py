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
    groups = rng.choice(["hitter", "SP", "RP"], len(players))
    frame = pd.DataFrame([{
        "war_pot": float(rng.uniform(-0.5, 7)), "readiness": float(rng.uniform(-5, 4)),
        "bat": float(rng.uniform(-6, 4)), "group": g, "side": "batting" if g == "hitter" else "pitching",
        "age_exact": float(rng.uniform(16.5, 30)), "we": p.work_ethic, "int": p.intelligence,
        "prone": p.injury_prone, "ad": p.adaptibility, "years": fit.REFERENCE_YEARS,
    } for p, g in zip(players, groups)])
    close, keep = fit.design(frame), fit.keep_design(frame)
    for i, (player, row) in enumerate(zip(players, frame.itertuples())):
        # a hitter's developed is his bat, a pitcher's his WAR now
        developed = row.bat if row.group == "hitter" else row.readiness
        runtime = odds.close_columns(player, row.war_pot, developed, row.group)
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
        parts = odds.parts(player, 4.0, -1.5, -2.5, "hitter", age)
        return parts, odds.expected(parts)
    parts, e = expected(19.0)
    assert parts["bridged"] == 1 and e == pytest.approx(parts["draft"])
    parts, e = expected(21.0)
    assert e == pytest.approx((parts["draft"] + parts["prospect"]) / 2)
    parts, e = expected(22.5)
    assert parts["draft"] is None and e == parts["prospect"]


def test_the_bridge_reads_a_hitter_on_his_bat(players):
    # a glove and legs at their ceiling already don't count toward how
    # developed a teen is (2026-11-12)
    odds, player = prospect_odds.load(), players[0]
    parts = odds.parts(player, 4.0, 0.5, -2.0, "hitter", 19.0)
    on_bat = odds.draft.expected(odds.draft.mean_columns(player, 4.0, -2.0, "hitter", 19.0), 19.0)
    assert parts["draft"] == pytest.approx(on_bat)
    assert parts["draft"] < odds.parts(player, 4.0, 0.5, 0.5, "hitter", 19.0)["draft"]


def test_the_share_he_closes_follows_the_age_curve(players):
    # judgment (2026-11-12): one smooth curve from 21, the runtime's the fit's
    odds, player = prospect_odds.load(), players[0]
    assert [list(x) for x in fit.AGE_CURVE] == odds.a["age_curve"]
    ages = (19.0, 21.0, 22.5, 24.0, 25.5, 27.0, 29.0)
    for age in ages:
        assert odds.age_curve(age) == pytest.approx(float(fit.age_curve(age)))
    closes = [odds.parts(player, 4.0, 1.0, 1.0, "hitter", age)["close"] for age in ages]
    assert closes[0] == closes[1] and all(a > b for a, b in zip(closes[1:], closes[2:])) and closes[-1] > 0
    parts = odds.parts(player, 4.0, 1.0, 1.0, "hitter", 24.0)
    assert parts["close"] == pytest.approx(parts["close_21"] * 0.73)


def test_he_never_realizes_more_than_his_ceiling_or_his_war_now(players):
    # keep and close are odds, so the expectation stays within the larger of
    # his ceiling and his WAR now (past the bridge)
    odds = prospect_odds.load()
    for player in players:
        for ceiling, readiness in ((5.0, 3.0), (2.0, 2.5), (6.0, -2.0)):
            parts = odds.parts(player, ceiling, readiness, readiness, "SP", 23.0)
            assert 0 <= odds.expected(parts) <= max(ceiling, readiness)


def test_the_board_weighs_upside_over_present_production(players):
    # what he's expected to add by developing counts `upside` times (2026-11-11)
    odds, player = prospect_odds.load(), players[0]
    gamma = odds.a["upside"]
    assert gamma > 1
    for ceiling, readiness, age in ((5.0, 1.0, 23.0), (6.5, -0.5, 21.0), (3.0, 3.5, 24.0)):
        lines, value, parts = odds.reaching(player, ceiling, readiness, readiness - 1, "hitter", age)
        held, expected = parts["held"], odds.expected(parts)
        assert value == pytest.approx(held + gamma * max(expected - held, 0) if expected > held else expected)
        upside = [amount for kind, label, amount, _, _ in lines if label == "Upside"]
        assert sum(upside) == pytest.approx(value - expected)

