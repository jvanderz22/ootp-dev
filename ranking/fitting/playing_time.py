"""Fitting the playing-time factor (ranking/playing_time.py), shared by the
draft and prospect fits.

A board brings its design (a DataFrame of columns, the logistic's names,
with GLOVE, RUN and CATCHER among them) and its outcome (each hitter's share
of a regular's season over its window); this fits the logistic, reads the
factor the way the board does, and writes the artifact's "plays" block.
"""
import numpy as np
import pandas as pd
from scipy import optimize

from ranking.playing_time import CAP, CATCHER, GLOVE, RUN, STRENGTH

REGULAR_PA = 600                    # a regular's season
PRIOR_SD = 3.0                      # a weak prior: the fits are on hundreds


def map_logistic(x, y, mean, sd, offset=0.0) -> np.ndarray:
    """[intercept, coefficients] of a logistic fit, each coefficient with a
    normal prior (`mean`, `sd`); the intercept is free. `y` may be a share."""
    def loss(w):
        z = w[0] + x @ w[1:] + offset
        p = 1 / (1 + np.exp(-z))
        r = (w[1:] - mean) / sd
        value = -np.sum(y * z - np.logaddexp(0, z)) + 0.5 * np.sum(r ** 2)
        grad = np.concatenate([[np.sum(p - y)], x.T @ (p - y) + r / sd])
        return value, grad
    return optimize.minimize(loss, np.concatenate([[0.0], mean]), jac=True, method="L-BFGS-B").x


def season_share(pa: dict, seasons) -> float:
    """His share of a regular's season over `seasons`, each capped at one."""
    seasons = list(seasons)
    return float(np.mean([min(pa.get(s, 0) / REGULAR_PA, 1.0) for s in seasons])) if seasons else 0.0


def fit(x: pd.DataFrame, share) -> np.ndarray:
    """[intercept, coefficients] of the chance he plays, on design `x`."""
    return map_logistic(x.values, np.asarray(share, float), np.zeros(x.shape[1]), np.full(x.shape[1], PRIOR_SD))


def chance(w, x: pd.DataFrame) -> np.ndarray:
    return 1 / (1 + np.exp(-(w[0] + x.values @ w[1:])))


def reference(glove, run) -> dict:
    """The average glove and run the factor compares a hitter to."""
    return {GLOVE: float(np.mean(glove)), RUN: float(np.mean(run))}


def factor(w, x: pd.DataFrame, ref: dict, applies) -> np.ndarray:
    """The factor on design `x`, as ranking/playing_time.py reads it: his
    chance over the same hitter's with `ref`'s glove and run, not a catcher,
    to STRENGTH, at most CAP - where `applies` (hitters), and never for a
    catcher; 1 elsewhere."""
    base = x.assign(**{GLOVE: ref[GLOVE], RUN: ref[RUN], CATCHER: 0.0})
    out = np.minimum((chance(w, x) / chance(w, base)) ** STRENGTH, CAP)
    return np.where(np.asarray(applies) & (x[CATCHER].values == 0), out, 1.0)


def block(w, names, ref: dict, **extra) -> dict:
    """The artifact's "plays" block."""
    return {"intercept": round(float(w[0]), 4), "coef": {n: round(float(c), 4) for n, c in zip(names, w[1:])},
            "reference": {k: round(v, 4) for k, v in ref.items()}, "strength": STRENGTH, "cap": CAP, **extra}
