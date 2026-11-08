"""The rules suite: the general rules of your handcrafted grids, as checks a
fitted model has to pass before it ships (see plans/ranking-v2-technical-plan.md,
"Rules suite"). They test shapes, not exact values.

Two groups: rules, which a model that fails doesn't ship with, and hypotheses,
which are reported but never enforced - a grid rule the stats haven't backed
yet. A hypothesis is promoted to a rule only once the data supports it.

Hitting checks take `wrc(babip, avoid_k, gap, power, eye) -> wRC+`, pitching
checks `ra(stuff, control, movement, role)`, and each returns a
Result. The fit script records both groups in the artifact;
tests/test_model_rules.py holds the committed artifact to the rules.
"""
from typing import NamedTuple

from scipy.stats import spearmanr

BASE = 55  # the other ratings, for one-rating sweeps
RATINGS = ("babip", "avoid_k", "gap", "power", "eye")

# 1. rating -> where its steep drop starts (from batting_attribute_model.py)
FLOORS = {"babip": (40,), "eye": (40,), "avoid_k": (35,)}
# H. the Power floors: a hypothesis since 2026-11-07 - HR per contact rises
# smoothly through 30 and 40 in the 2041-42 stats
POWER_FLOORS = {"power": (40, 30)}
# H (was 2). Power 40 -> 60 with weak contact skills is worth at most this
# share of it with good ones ("much less")
POWER_WITHOUT_CONTACT = 0.75
# 3. the grid's archetype rows keep their order at least this well
ARCHETYPE_RHO = 0.9
# H (was 3). archetypes of equal quality land within this of each other on average
ARCHETYPE_SPREAD = 15

# Your grid's labelled archetypes (batting_attribute_model.py), in its own
# terms: (archetype, wRC+, Contact, Gap, Power, Eye, Avoid K).
ARCHETYPES = [
    ("balanced", 180, 70, 70, 70, 70, 70), ("balanced", 160, 65, 65, 65, 65, 65),
    ("balanced", 130, 60, 60, 60, 60, 60), ("balanced", 120, 60, 60, 60, 55, 55),
    ("balanced", 120, 65, 50, 55, 65, 55), ("balanced", 110, 65, 35, 60, 55, 55),
    ("balanced", 110, 65, 55, 60, 55, 35), ("balanced", 110, 65, 55, 60, 35, 55),
    ("balanced", 100, 55, 55, 55, 55, 55), ("balanced", 90, 50, 50, 50, 50, 50),
    ("balanced", 75, 45, 45, 45, 45, 45), ("balanced", 55, 40, 40, 40, 40, 40),
    ("balanced", 30, 35, 35, 35, 35, 35),
    ("power", 180, 65, 70, 80, 70, 55), ("power", 160, 55, 60, 75, 70, 50),
    ("power", 140, 50, 55, 70, 65, 45), ("power", 125, 45, 55, 70, 60, 45),
    ("power", 120, 45, 65, 70, 55, 40), ("power", 110, 45, 40, 65, 50, 45),
    ("power", 100, 45, 45, 70, 45, 35), ("power", 95, 40, 65, 70, 50, 35),
    ("power", 90, 40, 45, 70, 50, 35), ("power", 90, 45, 45, 70, 45, 30),
    ("power", 80, 45, 40, 70, 35, 35), ("power", 80, 45, 35, 65, 45, 40),
    ("power", 80, 40, 50, 60, 45, 45), ("power", 55, 40, 40, 70, 40, 30),
    ("power", 30, 30, 35, 65, 30, 30),
    ("contact", 180, 80, 80, 60, 80, 80), ("contact", 150, 80, 80, 40, 80, 80),
    ("contact", 150, 70, 70, 50, 75, 70), ("contact", 130, 75, 80, 35, 65, 75),
    ("contact", 120, 70, 75, 40, 55, 65), ("contact", 110, 75, 70, 40, 40, 80),
    ("contact", 110, 65, 60, 45, 60, 60), ("contact", 100, 65, 60, 30, 60, 65),
    ("contact", 95, 80, 60, 25, 25, 80), ("contact", 80, 60, 60, 30, 30, 60),
    ("contact", 65, 50, 45, 30, 45, 50), ("contact", 30, 45, 40, 20, 40, 45),
]


class Result(NamedTuple):
    rule: str
    passed: bool
    detail: str


def _result(rule, passed, detail) -> Result:
    return Result(rule, bool(passed), detail)


def babip_from_contact(contact, avoid_k):
    """Contact ~ (BABIP + Avoid K) / 2 (fit_contact.py), inverted."""
    return max(20, min(80, 2 * contact - avoid_k))


def _sweep(wrc, rating, value, base=BASE):
    ratings = dict.fromkeys(RATINGS, base)
    ratings[rating] = value
    return wrc(**ratings)


def skill_floors(wrc, floors_by_rating=FLOORS):
    """1. Steep drop below skill floors: losing the 5 points below a floor costs
    more per point than the 55 -> 65 range gains."""
    out = []
    for rating, floors in floors_by_rating.items():
        normal = (_sweep(wrc, rating, 65) - _sweep(wrc, rating, 55)) / 10
        for floor in floors:
            below = (_sweep(wrc, rating, floor) - _sweep(wrc, rating, floor - 5)) / 5
            out.append(_result(
                f"floor: {rating} {floor}",
                below > normal,
                f"{below:.2f} wRC+/pt below {floor} vs {normal:.2f} at 55-65",
            ))
    return out


def avoid_k_carried(wrc):
    """1. ... while Avoid K 40 can be carried by other elite skills."""
    value = wrc(babip=70, avoid_k=40, gap=70, power=70, eye=70)
    return [_result("avoid K 40 carried by elite skills", value >= 100, f"{value:.0f} wRC+")]


def power_floors(wrc):
    """H. Steep drops below Power 40 and again below 30, regardless of other skills."""
    return skill_floors(wrc, POWER_FLOORS)


def power_needs_contact(wrc):
    """H (was rule 2). Power without contact is discounted. The 2041-42 stats
    show only a small discount: Power 60+ hitters with weak contact still hit
    115 wRC+ in MLB / AAA, against 134 with good contact."""
    def gain(contact):
        lo = wrc(babip=contact, avoid_k=contact, gap=BASE, power=40, eye=BASE)
        hi = wrc(babip=contact, avoid_k=contact, gap=BASE, power=60, eye=BASE)
        return hi - lo
    weak, good = gain(40), gain(60)
    share = weak / good if good else float("inf")
    return [_result(
        "power without contact discounted",
        share <= POWER_WITHOUT_CONTACT,
        f"Power 40->60: +{weak:.0f} at BABIP/Avoid K 40 vs +{good:.0f} at 60"
        f" ({share:.0%}, needs <= {POWER_WITHOUT_CONTACT:.0%})",
    )]


def archetypes_ordered(wrc):
    """3. The grid's labelled archetype rows keep their order."""
    labels, values = _archetype_values(wrc)
    rho = spearmanr(labels, values).correlation
    return [_result("archetypes keep the grid's order", rho >= ARCHETYPE_RHO,
                    f"spearman {rho:.2f} vs the grid's wRC+ labels")]


def _archetype_values(wrc):
    labels, values = [], []
    for _, label, contact, gap, power, eye, avoid_k in ARCHETYPES:
        labels.append(label)
        values.append(wrc(babip=babip_from_contact(contact, avoid_k), avoid_k=avoid_k,
                          gap=gap, power=power, eye=eye))
    return labels, values


def archetypes_comparable(wrc):
    """H (was rule 3). Balanced, power and contact archetypes of equal quality
    land at similar values: no archetype sits more than ARCHETYPE_SPREAD above
    or below the others on average. The stats put the grid's weak-contact power
    rows about 20 wRC+ higher than it does."""
    labels, values = _archetype_values(wrc)
    gaps = {}
    for (archetype, *_), label, value in zip(ARCHETYPES, labels, values):
        gaps.setdefault(archetype, []).append(value - label)
    means = {a: sum(g) / len(g) for a, g in gaps.items()}
    spread = max(means.values()) - min(means.values())
    offsets = ", ".join(f"{a} {m:+.0f}" for a, m in means.items())
    return [_result("archetypes comparable", spread <= ARCHETYPE_SPREAD,
                    f"mean vs grid label: {offsets} (spread {spread:.0f}, needs <= {ARCHETYPE_SPREAD})")]


def one_weak_tool(wrc):
    """4. One weak tool costs less than two: a single 35 next to 65s still rates
    above average, and two 35s rate below either one alone."""
    def with_35s(*weak):
        return wrc(**{r: 35 if r in weak else 65 for r in RATINGS})
    out = []
    singles = {r: with_35s(r) for r in RATINGS}
    worst = min(singles, key=singles.get)
    out.append(_result("one 35 among 65s is above average", singles[worst] > 100,
                      f"lowest: {worst} 35 -> {singles[worst]:.0f} wRC+"))
    pairs = [(a, b) for i, a in enumerate(RATINGS) for b in RATINGS[i + 1:]]
    bad = [(a, b) for a, b in pairs if with_35s(a, b) >= min(singles[a], singles[b])]
    out.append(_result("two 35s cost more than one", not bad,
                      "every pair" if not bad else f"not for {bad}"))
    return out


HITTING_RULES = (skill_floors, avoid_k_carried, archetypes_ordered, one_weak_tool)
# demoted from rules on 2026-11-07, when the stats disagreed
HITTING_HYPOTHESES = (power_floors, power_needs_contact, archetypes_comparable)

# Your grids' scale anchors: sanity checks, reported, never enforced.
BALANCED_ANCHORS = {55: 100, 60: 130, 65: 160, 70: 180}


def check_hitting(wrc) -> list:
    return [result for rule in HITTING_RULES for result in rule(wrc)]


def check_hitting_hypotheses(wrc) -> list:
    return [result for rule in HITTING_HYPOTHESES for result in rule(wrc)]


def anchors(wrc) -> dict:
    return {v: round(float(_sweep(wrc, "babip", v, base=v)), 1) for v in BALANCED_ANCHORS}


# Pitching. Checks take `ra(stuff, control, movement, role) -> runs allowed
# index` (100 = MLB average, lower is better; Movement sets HRA and PBABIP).
PITCHING_FLOOR = 30
PITCHING_ELITE = 70
# "emergency or no value": no better than an all-40s arm in the same role
EMERGENCY = 40


def pitching_floors(ra):
    """H (was rule 5). All three need to clear a floor: Stuff, Movement or
    Control at 30 means emergency or no value, whatever the others. The stats
    can barely test it (2026-11-07): about 5 MLB / AAA pitchers had one of them
    at 30 or below with the other two at 55+, none for Movement, and they
    weren't worthless (charged-runs index 90-115)."""
    out = []
    for role in ("sp", "rp"):
        emergency = ra(EMERGENCY, EMERGENCY, EMERGENCY, role)
        for rating in ("stuff", "control", "movement"):
            ratings = dict.fromkeys(("stuff", "control", "movement"), PITCHING_ELITE)
            ratings[rating] = PITCHING_FLOOR
            value = ra(**ratings, role=role)
            out.append(_result(
                f"floor: {rating} {PITCHING_FLOOR} ({role.upper()})",
                value >= emergency,
                f"{value:.0f} with the others at {PITCHING_ELITE}, vs {emergency:.0f} for an all-40s arm",
            ))
    return out


def command_carries_weak_stuff(ra):
    """H1. Elite Movement + Control can carry weak Stuff as a starter (35 / 80 /
    80 ~ a #2-3 starter), but elite Control alone can't (40 / 40 / 80 ~ little
    value)."""
    carried = ra(stuff=35, control=80, movement=80, role="sp")
    alone = ra(stuff=40, control=80, movement=40, role="sp")
    return [
        _result("H1 Movement + Control carry weak Stuff (SP)", carried <= 90,
                f"35 / 80 / 80 -> {carried:.0f} (a #2-3 starter: <= 90)"),
        _result("H1 Control alone doesn't (SP)", alone >= 100,
                f"40 / 80 / 40 -> {alone:.0f} (little value: >= 100)"),
    ]


def stuff_alone(ra):
    """H2. Elite Stuff alone isn't enough as a starter (80 / 40 / 40 ~ a spot
    starter) but is probably a good reliever."""
    sp = ra(stuff=80, control=40, movement=40, role="sp")
    rp = ra(stuff=80, control=40, movement=40, role="rp")
    return [
        _result("H2 Stuff alone isn't a starter", sp >= 100, f"80 / 40 / 40 as SP -> {sp:.0f} (>= 100)"),
        _result("H2 Stuff alone is a good reliever", rp <= 90, f"as RP -> {rp:.0f} (<= 90)"),
    ]


def relievers_lean_on_stuff(ra):
    """H3. Relievers lean more on Stuff than starters do."""
    gains = {role: ra(50, 50, 50, role) - ra(70, 50, 50, role) for role in ("sp", "rp")}
    return [_result("H3 Stuff 50 -> 70 is worth more in relief", gains["rp"] > gains["sp"],
                    f"-{gains['rp']:.1f} as RP vs -{gains['sp']:.1f} as SP")]


# rule 5 became a hypothesis on 2026-11-07, which leaves no pitching rule yet
PITCHING_RULES = ()
PITCHING_HYPOTHESES = (pitching_floors, command_carries_weak_stuff, stuff_alone, relievers_lean_on_stuff)


def check_pitching(ra) -> list:
    return [result for rule in PITCHING_RULES for result in rule(ra)]


def check_pitching_hypotheses(ra) -> list:
    return [result for rule in PITCHING_HYPOTHESES for result in rule(ra)]
