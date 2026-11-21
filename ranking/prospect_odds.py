"""The prospect odds - the chance he gets there, for the league's prospects
(plans/prospect-odds-plan.md): how much of his ceiling a prospect like him
realizes, fit on the league's prospect exports
(ranking/fitting/prospect_odds.py).

His ceiling is his potential ratings' WAR in a full-time role, and his WAR now
his current ratings' (the readiness companion), both as the draft odds read
them. What he's expected to realize is in two parts, each with its own odds:

    E = keep x his WAR now + close x (ceiling - his WAR now)

his WAR now floored at replacement. Prospects often end below what they're
worth now, so keep is fit too: on his age and his WAR now. close reads how
developed he is - a hitter's bat WAR now alone, since his glove and legs have
no potential ratings and are at their ceiling already; a pitcher's WAR now -
with his ceiling, role and personality (tapered by the ceiling), at 21, and
one smooth age curve takes it to his age (2026-11-12, you). Both are read
three years on, as the fit has them. The parts stay visible: the card's lines
are his WAR now and what he keeps of it, then the gap and what he closes of
it.

The board ranks on more than that expectation: what he's expected to add by
developing counts UPSIDE times (2026-11-11, you: upside over present
production), on its own ledger line. Judgment also holds two of the closing
odds' columns (the artifact's close judgment): the share of the gap he closes
doesn't fall as his ceiling rises, and a starter's penalty sets the board's
pitcher mix. A teen: no export settles one, and a teen in the minors is
closer to a draftee than to a 21-year-old pro, so below the bridge's first
age he's valued on the draft odds' expectation, as a draftee of his age and
as developed (a hitter on his bat), blended linearly into these by its
second.

The legacy modifiers the odds replace are the draft odds'; the lines they keep
(scouting accuracy, the hit profile, a switch hitter, a pitcher's velocity
upside) stay on top, as on the draft board.
"""
import json
from functools import lru_cache

import numpy as np

from ranking import development, draft_odds
from ranking.hitter_talent import ARTIFACTS_DIR

ARTIFACT = "prospect_odds_v1"
REPLACES = draft_odds.REPLACES
# the closing odds' personality: the draft odds' makeup, and adaptability
MAKEUP = {**draft_odds.MAKEUP, "AD H": ("adaptibility", ("H",)), "AD L": ("adaptibility", ("L",))}


def _sigmoid(z) -> float:
    return float(1 / (1 + np.exp(-z)))


class ProspectOdds:
    def __init__(self, artifact: dict, draft: draft_odds.DraftOdds):
        self.version = artifact["version"]
        self.a = artifact
        self.balance = artifact["pitcher_balance"]
        self.draft = draft

    # -- the fit's columns ------------------------------------------------------

    def close_columns(self, player, ceiling, developed, group) -> dict:
        """The closing odds' columns at 21 (ranking/fitting/prospect_odds.py's
        `design`), read three years on; `developed` is a hitter's bat WAR now,
        a pitcher's WAR now."""
        a = self.a
        cols = {"log potential": float(np.log(max(ceiling, a["log_floor"]) / a["reference_war"])),
                "developed": float(np.clip(developed, *a["close"]["developed_clip"])),
                "SP": float(group == "SP"), "RP": float(group == "RP")}
        taper = development.weight(ceiling)
        for label, (attr, values) in MAKEUP.items():
            cols[label] = float(getattr(player, attr) in values) * taper
        cols["years"] = 0.0
        return cols

    def keep_columns(self, readiness, age) -> dict:
        """The holding odds' columns (`keep_design`)."""
        a = self.a
        return {"age": float(np.clip(age, *a["keep_ages"]) - a["age_reference"]), "years": 0.0,
                "now": float(min(max(readiness, 0.0), a["keep"]["now_clip"]))}

    # -- what he's expected to realize -----------------------------------------

    def _odds(self, part, cols) -> float:
        p = self.a[part]
        return _sigmoid(p["intercept"] + sum(c * cols[n] for n, c in p["coef"].items()))

    def age_curve(self, age) -> float:
        """The share of the gap he closes at `age`, x 21's."""
        ages, values = zip(*self.a["age_curve"])
        return float(np.interp(age, ages, values))

    def bridged(self, age) -> float:
        """The draft odds' share of his expectation at `age`."""
        lo, hi = self.a["bridge"]["ages"]
        return float(np.clip((hi - age) / (hi - lo), 0.0, 1.0))

    def parts(self, player, ceiling, readiness, developed, group, age, hitter=None) -> dict:
        """The expectation's parts: his WAR now and the odds he keeps it, the
        gap and the odds he closes it (at 21, then at his age), this fit's
        expectation, and the draft odds' share and theirs (the teen bridge,
        reading him as developed as this fit does, and as the draft board
        values him: `bridge_value`). `hitter` is a hitter's (bat, glove, run)
        WAR at potential and whether he's a catcher."""
        now = max(readiness, 0.0)
        gap = max(ceiling - now, 0.0)
        keep = self._odds("keep", self.keep_columns(readiness, age))
        at_21 = self._odds("close", self.close_columns(player, ceiling, developed, group))
        close = at_21 * self.age_curve(age)
        out = {"now": now, "keep": keep, "gap": gap, "close_21": at_21, "close": close,
               "prospect": keep * now + close * gap, "held": keep * now, "bridged": self.bridged(age), "draft": None}
        if out["bridged"] > 0:
            out["draft"] = self.bridge_value(player, ceiling, developed, group, age, hitter)
        return out

    def bridge_value(self, player, ceiling, developed, group, age, hitter=None) -> float:
        """The draft board's value of him (2026-11-21, plans/draft-glove-plan.md),
        before the lines both boards keep on top and its ranking judgments:
        the odds on his ceiling with a hitter's glove at GLOVE_WEIGHT, the
        draft playing-time factor and the share cap - so a teen reads the same
        on both boards."""
        odds_ceiling = ceiling
        if hitter is not None:
            bat, glove, run, catcher = hitter
            odds_ceiling = ceiling - (1 - draft_odds.GLOVE_WEIGHT) * max(glove, 0.0)
        cols = self.draft.mean_columns(player, odds_ceiling, developed, group, age)
        value = self.draft.expected(cols, age)
        if hitter is not None:
            value *= self.draft.playing(bat, developed, glove, run, age, catcher)
        return draft_odds.realistic(value, ceiling)

    @staticmethod
    def expected(parts) -> float:
        w = parts["bridged"]
        return parts["prospect"] if not w else w * parts["draft"] + (1 - w) * parts["prospect"]

    def upside(self, parts) -> float:
        """What the board adds for upside: (UPSIDE - 1) x what he's expected
        to add to the WAR now he keeps, never below none."""
        return (self.a["upside"] - 1) * max(self.expected(parts) - parts["held"], 0.0)

    def reaching(self, player, ceiling, readiness, developed, group, age, switch=None, hitter=None) -> tuple:
        """(ledger lines, value, parts) for one side: lines are (kind, label,
        value, stat, note), kind "add" (value in WAR) or "scale" (value a
        factor), from his ceiling to what he's expected to realize, then the
        upside the board adds on top. `switch` is the switch hitter's (label,
        factor, note), applied last."""
        parts = self.parts(player, ceiling, readiness, developed, group, age, hitter)
        now, gap = parts["now"], parts["gap"]
        lines = []
        if now > ceiling:
            lines.append(("add", "Past his ceiling", now - ceiling, None, None))
        if now > 0:
            lines.append(("add", "WAR now", (parts["keep"] - 1) * now, f"keeps {parts['keep']:.0%}", f"{now:.1f} WAR"))
        if gap > 0:
            lines.append(("add", "Gap", (parts["close"] - 1) * gap, f"closes {parts['close']:.0%}", f"{gap:.1f} WAR"))
        expected = self.expected(parts)
        if parts["bridged"]:
            lines.append(("add", "Runway", expected - parts["prospect"], f"age {age:.1f}", None))
        upside = self.upside(parts)
        if upside:
            lines.append(("add", "Upside", upside, f"x{self.a['upside']:g}", None))
        factor = 1.0
        if switch:
            lines.append(("scale", "Switch hitter", switch[1], None, None))
            factor = switch[1]
        return lines, (expected + upside) * factor, parts


@lru_cache(maxsize=None)
def load(name: str = ARTIFACT) -> ProspectOdds:
    artifact = json.loads((ARTIFACTS_DIR / f"{name}.json").read_text())
    return ProspectOdds(artifact, draft_odds.load(artifact["bridge"]["draft_odds"]))
