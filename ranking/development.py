"""The development layer (phase 6), first part: how much of his potential a
prospect is likely to realize, from his makeup and durability.

Fit on the 2033-2036 draft classes (ranking/fitting/development.py): a
draftee's outcome - the value of his ratings in the 2042 snapshot, current
ones at 25+ and potential before, 0 once he's gone - against his draft-day
potential WAR. Work ethic, intelligence and injury proneness move what he
realizes far more than the legacy modifiers did, and both outcomes tried
(value now, career MLB WAR) agree on the direction.

The factors are your judgment on top of that fit (2026-11-08): the
conservative end of it, and tapered by the player's own potential WAR - full
weight up to FULL_WEIGHT_WAR, falling to TAPERED_WEIGHT at TAPERED_WAR and
above - so an otherwise mediocre prospect with maxed makeup can't climb over
a generational talent with ordinary makeup. The fit shows the same taper:
among 4+ WAR prospects makeup matters about half as much as among 1-4 WAR
ones.

Each factor scales the side's WAR above replacement, like a modifier, and is
its own ledger line. They replace the legacy personality and injury
modifiers (REPLACES) in the profiles that read potential ratings; age,
scouting accuracy, secondary personality (leadership) and the draft-day
current-ratings modifiers stay as legacy judgment until the ratings archive
can measure peak value.
"""
import numpy as np

# label -> (GamePlayer attribute, {value: factor}); values not listed are 1
FACTORS = {
    "work ethic": ("work_ethic", {"H": 1.25, "L": 0.75}),
    "intelligence": ("intelligence", {"H": 1.15, "L": 0.95}),
    "durability": ("injury_prone", {"Iron Man": 1.05, "Durable": 1.03, "Fragile": 0.75, "Wrecked": 0.6}),
}
FULL_WEIGHT_WAR, TAPERED_WAR, TAPERED_WEIGHT = 2.5, 5.0, 0.35
# judgment (2026-11-08): a switch-hitting prospect gives you lineup flexibility
# the platoons don't price - your legacy bonus, on the batting side, tapered
# like the factors above. Current ratings don't need it: real splits carry it.
SWITCH_HITTER = 1.07
REPLACES = ("PersonalityModifier", "BatterInjuryModifier", "PitcherInjuryModifier")


def weight(war) -> float:
    """How much of each factor applies to a side worth `war` at potential."""
    ramp = (war - FULL_WEIGHT_WAR) / (TAPERED_WAR - FULL_WEIGHT_WAR)
    return float(1 - (1 - TAPERED_WEIGHT) * np.clip(ramp, 0.0, 1.0))


def _note(base, w) -> str:
    """The ledger note for a factor of `base` at weight `w`."""
    return f"x{base:g}" + (f" at {w:.0%} weight" if w < 1 else "")


def switch_hitter(war) -> tuple:
    """(ledger label, factor, note) for a switch-hitting prospect's batting side."""
    w = weight(war)
    return "switch hitter", SWITCH_HITTER ** w, _note(SWITCH_HITTER, w)


def factors(player, war) -> list:
    """[(ledger label, factor, note)] for `player`'s side worth `war`; only
    the factors that move him."""
    w = weight(war)
    out = []
    for label, (attr, table) in FACTORS.items():
        value = getattr(player, attr)
        base = table.get(value)
        if base is None:
            continue
        out.append((f"{label} {value}", base ** w, _note(base, w)))
    return out
