"""The rules suite against every committed fitted artifact: a model that fails
a rule doesn't ship (plans/ranking-v2-technical-plan.md, "Rules suite").
Hypotheses are reported by the fit script and never enforced here."""
import json

import pytest

from ranking import hitter_talent, pitcher_talent
from ranking.fitting import rules


def _wrc(**ratings):
    return float(hitter_talent.load().wrc_plus(ratings))


HITTING = rules.check_hitting(_wrc)


@pytest.mark.parametrize("result", HITTING, ids=[r.rule for r in HITTING])
def test_hitter_talent_passes_the_rules(result):
    assert result.passed, result.detail


def test_artifact_records_the_rules_it_was_fit_under():
    path = hitter_talent.ARTIFACTS_DIR / f"{hitter_talent.ARTIFACT}.json"
    meta = json.loads(path.read_text())["meta"]
    assert set(meta["rules"]) == {r.rule for r in HITTING}
    assert all(r["passed"] for r in meta["rules"].values())
    assert set(meta["hypotheses"]) == {r.rule for r in rules.check_hitting_hypotheses(_wrc)}


def _ra(stuff, control, movement, role, **parts):
    ratings = {"stuff": stuff, "control": control, "hra": movement, "pbabip": movement, **parts}
    return float(pitcher_talent.load().runs_index(ratings, role))


PITCHING = rules.check_pitching(_ra)


@pytest.mark.parametrize("result", PITCHING, ids=[r.rule for r in PITCHING])
def test_pitcher_talent_passes_the_rules(result):
    assert result.passed, result.detail


def test_pitcher_artifact_records_the_rules_it_was_fit_under():
    path = pitcher_talent.ARTIFACTS_DIR / f"{pitcher_talent.ARTIFACT}.json"
    meta = json.loads(path.read_text())["meta"]
    assert set(meta["rules"]) == {r.rule for r in PITCHING}
    assert all(r["passed"] for r in meta["rules"].values())
    assert set(meta["hypotheses"]) == {r.rule for r in rules.check_pitching_hypotheses(_ra)}
