"""The prospect odds - the chance he gets there, for the league's prospects
(plans/prospect-odds-plan.md): how much of his ceiling a prospect like him
realizes, fit on the league's prospect exports
(ranking/fitting/prospect_odds.py).

His ceiling is his potential ratings' WAR in a full-time role, and his WAR now
his current ratings' (the readiness companion), both as the draft odds read
them. What he's expected to realize is in two parts, each with its own odds:

    E = keep x his WAR now + close x (ceiling - his WAR now)

his WAR now floored at replacement. Prospects often end below what they're
worth now, so keep is fit too: on his age and his WAR now. close is the draft
odds' shape (ceiling, readiness by age, role, makeup tapered by the ceiling).
Both are read three years on, as the fit has them. The parts stay visible:
the card's lines are his WAR now and what he keeps of it, then the gap and
what he closes of it.

The board ranks on more than that expectation: what he's expected to add by
developing counts UPSIDE times (2026-11-11, you: upside over present
production), on its own ledger line. Judgment also holds two of the closing
odds' columns (the artifact's close judgment): the share of the gap he closes
doesn't fall as his ceiling rises, and a starter's penalty is set so the
board carries about 5 pitchers in its top 25.

Two more judgments (2026-11-11), on top of the fit:
- a teen: no export settles one, and a teen in the minors is closer to a
  draftee than to a 21-year-old pro, so below the bridge's first age he's
  valued on the draft odds' expectation, as a draftee of his age, blended
  linearly into these by its second
- past 25 much more development is hard to get, even short of his potential:
  the closing odds taper to none at 27, and from there he's valued at the WAR
  now he holds

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


def _sigmoid(z) -> float:
    return float(1 / (1 + np.exp(-z)))


class ProspectOdds:
    def __init__(self, artifact: dict, draft: draft_odds.DraftOdds):
        self.version = artifact["version"]
        self.a = artifact
        self.balance = artifact["pitcher_balance"]
        self.draft = draft

    # -- the fit's columns ------------------------------------------------------

    def ages(self, age) -> dict:
        """{label: weight} of his age on the fit's knots, the reference left out."""
        a = self.a["age"]
        weights = draft_odds.knot_weights(age, a["knots"])
        return {f"{k:g}": float(weights[k]) for k in a["knots"] if k != a["reference"]}

    def close_columns(self, player, ceiling, readiness, group, age) -> dict:
        """The closing odds' columns (ranking/fitting/prospect_odds.py's
        `design`), read three years on."""
        a = self.a
        lp = float(np.log(max(ceiling, a["log_floor"]) / a["reference_war"]))
        cols = {"log potential": lp, "readiness": float(np.clip(readiness, *a["close"]["readiness_clip"])),
                "SP": float(group == "SP"), "RP": float(group == "RP")}
        ages = self.ages(age)
        for label, w in ages.items():
            cols[f"age {label}"] = w
        for label, w in ages.items():
            cols[f"age {label} x potential"] = lp * w
        for label, w in ages.items():
            cols[f"readiness x age {label}"] = cols["readiness"] * w
        taper = development.weight(ceiling)
        for label, (attr, values) in draft_odds.MAKEUP.items():
            cols[label] = float(getattr(player, attr) in values) * taper
        cols["years"] = 0.0
        return cols

    def keep_columns(self, readiness, age) -> dict:
        """The holding odds' columns (`keep_design`)."""
        knots, ref = self.a["age"]["knots"], self.a["age"]["reference"]
        return {"age": float(np.clip(age, knots[0], knots[-1]) - ref), "years": 0.0,
                "now": float(min(max(readiness, 0.0), self.a["keep"]["now_clip"]))}

    # -- what he's expected to realize -----------------------------------------

    def _odds(self, part, cols) -> float:
        p = self.a[part]
        return _sigmoid(p["intercept"] + sum(c * cols[n] for n, c in p["coef"].items()))

    def development_left(self, age) -> float:
        """The share of his closing odds left at `age`."""
        start, end = self.a["development_end"]
        return float(np.clip((end - age) / (end - start), 0.0, 1.0))

    def on_track_age(self, age, readiness) -> float:
        """The age his closing odds and the bridge read: near replacement, up
        to two years less from 21.5 to 23.5 - a raw 22- or 23-year-old is on
        schedule - back to his own by 24.5."""
        lo, top, end = self.a["on_track"]["ages"]
        full, none = self.a["on_track"]["now"]
        relief = np.clip(age - lo, 0, top - lo) if age <= top else (top - lo) * np.clip((end - age) / (end - top), 0, 1)
        return float(age - np.clip((none - readiness) / (none - full), 0, 1) * relief)

    def bridged(self, age) -> float:
        """The draft odds' share of his expectation at `age`."""
        lo, hi = self.a["bridge"]["ages"]
        return float(np.clip((hi - age) / (hi - lo), 0.0, 1.0))

    def parts(self, player, ceiling, readiness, group, age) -> dict:
        """The expectation's parts: his WAR now and the odds he keeps it, the
        gap and the odds he closes it, this fit's expectation, and the draft
        odds' share and theirs (the teen bridge). The closing odds and the
        bridge read his on-track age (`read_age`)."""
        now = max(readiness, 0.0)
        gap = max(ceiling - now, 0.0)
        read = self.on_track_age(age, readiness)
        keep = self._odds("keep", self.keep_columns(readiness, age))
        close = self._odds("close", self.close_columns(player, ceiling, readiness, group, read)) * self.development_left(age)
        out = {"now": now, "keep": keep, "gap": gap, "close": close, "prospect": keep * now + close * gap,
               "held": keep * now, "read_age": read, "bridged": self.bridged(read), "draft": None}
        if out["bridged"] > 0:
            cols = self.draft.mean_columns(player, ceiling, readiness, group, read)
            out["draft"] = self.draft.expected(cols, read)
        return out

    @staticmethod
    def expected(parts) -> float:
        w = parts["bridged"]
        return parts["prospect"] if not w else w * parts["draft"] + (1 - w) * parts["prospect"]

    def upside(self, parts) -> float:
        """What the board adds for upside: (UPSIDE - 1) x what he's expected
        to add to the WAR now he keeps, never below none."""
        return (self.a["upside"] - 1) * max(self.expected(parts) - parts["held"], 0.0)

    def reaching(self, player, ceiling, readiness, group, age, switch=None) -> tuple:
        """(ledger lines, value, parts) for one side: lines are (kind, label,
        value, stat, note), kind "add" (value in WAR) or "scale" (value a
        factor), from his ceiling to what he's expected to realize, then the
        upside the board adds on top. `switch` is the switch hitter's (label,
        factor, note), applied last."""
        parts = self.parts(player, ceiling, readiness, group, age)
        now, gap = parts["now"], parts["gap"]
        lines = []
        if now > ceiling:
            lines.append(("add", "Past his ceiling", now - ceiling, None, None))
        if now > 0:
            lines.append(("add", "WAR now", (parts["keep"] - 1) * now, f"keeps {parts['keep']:.0%}", f"{now:.1f} WAR"))
        on_schedule = parts["read_age"] < age - 0.25
        if gap > 0:
            note = f"{gap:.1f} WAR" + (" · on schedule" if on_schedule else "")
            lines.append(("add", "Gap", (parts["close"] - 1) * gap, f"closes {parts['close']:.0%}", note))
        expected = self.expected(parts)
        if parts["bridged"]:
            lines.append(("add", "Runway", expected - parts["prospect"], f"age {parts['read_age']:.1f}", None))
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
