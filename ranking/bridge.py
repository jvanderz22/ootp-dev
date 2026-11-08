"""Fitted talent -> the legacy model's 0-100 points, until the value layer puts
everything in WAR.

A bridge is a pair of matching percentiles - a talent measure's over the
league's players and the legacy score's over the same players - so the fitted
model reorders players without changing how the points are spread. That keeps
hitters vs pitchers and starters vs relievers where legacy has them until phase 5.
"""
import numpy as np

KNOTS = 101


def fit(talent, legacy, higher_is_better=True) -> dict:
    """Knots mapping `talent` onto `legacy`'s distribution, increasing in talent
    (a lower-is-better measure, like runs allowed, maps its low end to the top)."""
    q = np.linspace(0, 100, KNOTS)
    x = np.percentile(talent, q)
    y = np.percentile(legacy, q if higher_is_better else q[::-1])
    # equal knots (a floor of identical players) would make the map ambiguous
    keep = np.concatenate([[True], np.diff(x) > 1e-9])
    return {"talent": np.round(x[keep], 4).tolist(), "points": np.round(y[keep], 3).tolist()}


def points(value, bridge: dict):
    """`value` through `bridge`, extended past its ends along the end slopes and
    floored at 0."""
    x, y = np.asarray(bridge["talent"]), np.asarray(bridge["points"])
    out = np.interp(value, x, y)
    hi_slope = (y[-1] - y[-2]) / (x[-1] - x[-2])
    lo_slope = (y[1] - y[0]) / (x[1] - x[0])
    out = np.where(value > x[-1], y[-1] + (value - x[-1]) * hi_slope, out)
    out = np.where(value < x[0], y[0] + (value - x[0]) * lo_slope, out)
    return np.maximum(out, 0.0)
