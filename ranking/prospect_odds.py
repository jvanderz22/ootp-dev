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

from typing import NamedTuple

from ranking import development, draft_odds, playing_time
from ranking.hitter_talent import ARTIFACTS_DIR

ARTIFACT = "prospect_odds_v1"
REPLACES = draft_odds.REPLACES
# the closing odds' personality: the draft odds' makeup, and adaptability
MAKEUP = {**draft_odds.MAKEUP, "AD H": ("adaptibility", ("H",)), "AD L": ("adaptibility", ("L",))}


class Hitter(NamedTuple):
    """A hitter's parts the prospect odds read (WAR): his bat, glove and run
    at potential, his glove now, whether he's a catcher and his level."""
    bat: float
    glove: float
    run: float
    catcher: bool = False
    glove_now: float = 0.0
    level: str = None


def _sigmoid(z) -> float:
    return float(1 / (1 + np.exp(-z)))


class ProspectOdds:
    def __init__(self, artifact: dict, draft: draft_odds.DraftOdds):
        self.version = artifact["version"]
        self.a = artifact
        self.balance = artifact["pitcher_balance"]
        self.draft = draft
        self.plays = playing_time.PlayingTime.of(artifact)

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
        values him: `bridge_value`). `hitter` is a hitter's parts (Hitter):
        his glove counts at GLOVE_WEIGHT in his ceiling and his WAR now, and
        this fit's expectation takes the playing-time factor (2026-11-21,
        as on the draft board)."""
        cut = cut_now = 0.0
        if hitter is not None:
            cut = (1 - draft_odds.GLOVE_WEIGHT) * max(hitter.glove, 0.0)
            cut_now = (1 - draft_odds.GLOVE_WEIGHT) * max(hitter.glove_now, 0.0)
        odds_ceiling, odds_now = ceiling - cut, readiness - cut_now
        now = max(odds_now, 0.0)
        gap = max(odds_ceiling - now, 0.0)
        keep = self._odds("keep", self.keep_columns(odds_now, age))
        at_21 = self._odds("close", self.close_columns(player, odds_ceiling, developed, group))
        close = at_21 * self.age_curve(age)
        plays = self.playing(hitter, developed, age)
        out = {"now": now, "keep": keep, "gap": gap, "close_21": at_21, "close": close, "glove": cut,
               "odds_ceiling": odds_ceiling, "plays": plays, "raw": keep * now + close * gap,
               "prospect": (keep * now + close * gap) * plays, "held": keep * now * plays,
               "bridged": self.bridged(age), "draft": None}
        if out["bridged"] > 0:
            out["draft"] = self.bridge_value(player, ceiling, developed, group, age, hitter)
        return out

    def playing(self, hitter, developed, age) -> float:
        """The prospect playing-time factor (ranking/playing_time.py): on his
        bat's ceiling and WAR now and his glove and run at potential, at the
        fit's reference age and level. 1 for a pitcher, without the fit, and
        for a catcher."""
        if hitter is None or self.plays is None:
            return 1.0
        # read at the fit's reference age and level (age and level 0): at his
        # own, an older player in AAA has so small a chance that any glove or
        # speed is a big ratio
        b = self.plays.block
        cols = {"bat": hitter.bat, "bat now": float(np.clip(developed, *b["clip"])), "glove": hitter.glove,
                "run": hitter.run, playing_time.CATCHER: float(hitter.catcher)}
        return self.plays.factor(cols, hitter.catcher)

    def bridge_value(self, player, ceiling, developed, group, age, hitter=None) -> float:
        """The draft board's value of him (2026-11-21, plans/draft-glove-plan.md),
        before the lines both boards keep on top and its ranking judgments:
        the odds on his ceiling with a hitter's glove at GLOVE_WEIGHT, the
        draft playing-time factor and the share cap - so a teen reads the same
        on both boards."""
        odds_ceiling = ceiling
        if hitter is not None:
            odds_ceiling = ceiling - (1 - draft_odds.GLOVE_WEIGHT) * max(hitter.glove, 0.0)
        cols = self.draft.mean_columns(player, odds_ceiling, developed, group, age)
        value = self.draft.expected(cols, age)
        if hitter is not None:
            value *= self.draft.playing(hitter.bat, developed, hitter.glove, hitter.run, age, hitter.catcher)
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
        now, gap, ceiling = parts["now"], parts["gap"], parts["odds_ceiling"]
        lines = []
        if parts["glove"] > 0:
            lines.append(("add", "Glove", -parts["glove"], f"counts {draft_odds.GLOVE_WEIGHT:.0%}",
                          f"{hitter.glove:.1f} WAR"))
        if now > ceiling:
            lines.append(("add", "Past his ceiling", now - ceiling, None, None))
        if now > 0:
            lines.append(("add", "WAR now", (parts["keep"] - 1) * now, f"keeps {parts['keep']:.0%}", f"{now:.1f} WAR"))
        if gap > 0:
            lines.append(("add", "Gap", (parts["close"] - 1) * gap, f"closes {parts['close']:.0%}", f"{gap:.1f} WAR"))
        if parts["plays"] != 1:
            lines.append(("scale", "Playing time", parts["plays"], None, None))
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
