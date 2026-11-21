"""The playing-time factor, shared by the draft and prospect odds
(plans/draft-glove-plan.md, 2026-11-21).

How much bat a hitter needs to get on the field depends on his glove and his
speed: a good glove or good speed gets a weaker bat into the lineup, and a 1B
or DH needs more bat than a shortstop. Each board fits the chance he plays -
a logistic of his share of a regular's season, on its own columns
(ranking/fitting/playing_time.py) - and his value takes

    (P(he plays) / P(the same hitter with an average glove and run)) ^ STRENGTH

at most CAP. The comparison holds his bat, so the factor never counts the
bat twice. Catchers get none until they're revisited (2026-11-21: a
catcher's glove carries the catcher adjustment, so the factor lifted
catchers, who realize less than predicted).

An artifact's "plays" block: the logistic's intercept and coef by column
name, the reference glove and run, the strength and the cap. A board builds
the columns; this reads them.
"""
import numpy as np

# judgment (2026-11-21): the square root ranked best held out on MLB WAR to
# 26 - in full it over-rewarded gloves (45%+ glove ceilings realized 0.65 of
# predicted) and pulled the top 25 toward hitters
STRENGTH = 0.5
# its most: about its 95th percentile among draftees. Past that it's elite
# speed or glove on a weak bat, where the fit extrapolates (Maruri x2.32,
# Bernier x2.07) and glove-first ceilings already realize less than predicted
CAP = 1.5
# the columns the reference swaps (to the block's average) or clears
GLOVE, RUN, CATCHER = "glove", "run", "C"


def _chance(z) -> float:
    return float(1 / (1 + np.exp(-z)))


class PlayingTime:
    def __init__(self, block: dict):
        self.block = block

    @classmethod
    def of(cls, artifact: dict):
        """The artifact's playing-time model, or None without one."""
        return cls(artifact["plays"]) if artifact.get("plays") else None

    def logit(self, cols: dict) -> float:
        """The chance he plays' log-odds; a column the fit has that `cols`
        lacks counts as 0."""
        b = self.block
        return b["intercept"] + sum(c * cols.get(name, 0.0) for name, c in b["coef"].items())

    def factor(self, cols: dict, catcher: bool = False) -> float:
        """His playing-time factor, `cols` his columns (CATCHER among them
        for a catcher): his chance over the same hitter's with the reference
        glove and run, not a catcher, to the strength, at most the cap; 1 for
        a catcher."""
        if catcher:
            return 1.0
        b = self.block
        ref = {**cols, **{k: b["reference"][k] for k in (GLOVE, RUN)}, CATCHER: 0.0}
        factor = (_chance(self.logit(cols)) / _chance(self.logit(ref))) ** b["strength"]
        return float(min(factor, b["cap"]))
