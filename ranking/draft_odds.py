"""The draft odds - the chance he gets there (plans/draft-odds-plan.md): how
much of his ceiling a draftee like him realizes, fit on the league's past
classes (ranking/fitting/draft_odds.py).

So far this holds the judgment that stays on top of the odds. The stage that
applies them (step C) builds on it.

Velocity (decided 2026-11-10, open question 4): an upside, never a penalty.
Held out on the past classes, with the odds' mean held fixed, pitchers whose
range topped out at 96-97 realized about 16% more than predicted and at 98-99
about 59% (36 pitchers); slower arms realized at least what was predicted.
The steps take about half of that, by the bottom of his range, as legacy's
PitcherVelocityModifier reads it. Stuff gets no line: the low end beat the
odds and the high end added nothing, so its legacy cuts are dropped.
"""
import re

# (lowest bottom of his range, factor), checked from the top; below the last
# step he's x1.00
VELOCITY_STEPS = ((100, 1.15), (98, 1.12), (96, 1.10), (94, 1.05))
# the legacy modifiers the odds replace on the draft board (step C), and the
# two judgment lines replaced here: velocity by `velocity_factor`, Stuff by
# nothing
REPLACES = (
    "AgeModifier", "DraftBatterOverallModifier", "DraftPitcherOverallModifier",
    "DraftPitcherStuffModifier", "PitcherVelocityModifier",
)


def velocity_factor(velocity, knuckleball=False) -> float:
    """The upside his velocity range ("94-96") earns; 1 for a knuckleballer,
    or with no range exported."""
    found = re.search(r"\d+", str(velocity or ""))
    if knuckleball or not found:
        return 1.0
    bottom = int(found[0])
    return next((factor for low, factor in VELOCITY_STEPS if bottom >= low), 1.0)
