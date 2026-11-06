"""One declared config per ranking purpose (see plans/ranking-architecture-plan.md).

Everything that differs between the current, potential and draft-class rankings
lives here, instead of across scorer `type` branches, ranker subclasses,
constructor arguments and overridden methods. The profiles below reproduce the
legacy rankers in `rankers/` exactly; the parity test holds them to that.
"""
import hashlib
import inspect
import json
from dataclasses import dataclass, replace

from modifiers.age_modifier import AgeModifier
from modifiers.batter_handedness_modifier import BatterHandednessModifier
from modifiers.batter_hit_profile_modifier import BatterHitProfileModifier
from modifiers.batter_injury_modifier import BatterInjuryModifier
from modifiers.draft_batter_overall_modifier import DraftBatterOverallModifier
from modifiers.draft_demand_modifier import DraftDemandModifier
from modifiers.draft_pitcher_overall_modifier import DraftPitcherOverallModifier
from modifiers.draft_pitcher_stuff_modifier import DraftPitcherStuffModifier
from modifiers.draft_secondary_personality_modifier import DraftSecondaryPersonalityModifier
from modifiers.personality_modifier import PersonalityModifier
from modifiers.pitcher_injury_modifier import PitcherInjuryModifier
from modifiers.pitcher_velocity_modifier import PitcherVelocityModifier
from modifiers.scouting_accuracy_modifier import ScoutingAccuracyModifier
from scoring.pitcher_scorer import RP_OVERALL_MODIFIER


def modifier_name(modifier) -> str:
    """A modifier's name - modifiers are classes, or instances when configured."""
    return modifier.__name__ if inspect.isclass(modifier) else modifier.__class__.__name__


def _describe_modifier(modifier) -> str:
    if inspect.isclass(modifier):
        return modifier.__name__
    return f"{modifier_name(modifier)}({json.dumps(vars(modifier), sort_keys=True)})"


@dataclass(frozen=True)
class ScoringProfile:
    name: str
    # which ratings the scorers read: "overall" (current) or "potential" - the
    # scorers' own `type` values
    ratings: str
    # the reliever score is scaled by this so it competes with the starter score
    rp_multiplier: float = RP_OVERALL_MODIFIER
    # multiplicative modifiers; `shared` apply to both sides, ahead of the side's own
    shared_modifiers: tuple = ()
    batting_modifiers: tuple = ()
    pitching_modifiers: tuple = ()
    # rank-adjusted modifiers (signability), run last on the pre-demand order
    demand_modifiers: tuple = ()
    # a two-way bonus of `two_way_bonus` x the weaker side is added when the
    # sides are within `high / two_way_threshold` of each other
    two_way_threshold: float = 1.8
    two_way_bonus: float = 0.15

    def without(self, *modifiers) -> "ScoringProfile":
        """This profile minus `modifiers` (matched by name) on every side."""
        drop = {modifier_name(m) for m in modifiers}

        def keep(mods):
            return tuple(m for m in mods if modifier_name(m) not in drop)

        return replace(
            self,
            shared_modifiers=keep(self.shared_modifiers),
            batting_modifiers=keep(self.batting_modifiers),
            pitching_modifiers=keep(self.pitching_modifiers),
            demand_modifiers=keep(self.demand_modifiers),
        )

    def describe(self) -> dict:
        """Every setting, by name - what the run manifest hashes."""
        return {
            "name": self.name,
            "ratings": self.ratings,
            "rp_multiplier": self.rp_multiplier,
            "shared_modifiers": [_describe_modifier(m) for m in self.shared_modifiers],
            "batting_modifiers": [_describe_modifier(m) for m in self.batting_modifiers],
            "pitching_modifiers": [_describe_modifier(m) for m in self.pitching_modifiers],
            "demand_modifiers": [_describe_modifier(m) for m in self.demand_modifiers],
            "two_way_threshold": self.two_way_threshold,
            "two_way_bonus": self.two_way_bonus,
        }

    def config_hash(self) -> str:
        return hashlib.sha256(json.dumps(self.describe(), sort_keys=True).encode()).hexdigest()[:12]


# Current ratings (legacy OverallRanker).
CURRENT = ScoringProfile(
    name="overall",
    ratings="overall",
    batting_modifiers=(BatterHandednessModifier, BatterHitProfileModifier(True)),
    two_way_threshold=2.5,
)

# Potential ratings for the league's rookies (legacy OverallPotentialRanker).
POTENTIAL = ScoringProfile(
    name="potential",
    ratings="potential",
    shared_modifiers=(ScoutingAccuracyModifier, PersonalityModifier, AgeModifier),
    batting_modifiers=(
        DraftBatterOverallModifier,
        BatterHandednessModifier,
        BatterHitProfileModifier(),
        BatterInjuryModifier,
    ),
    pitching_modifiers=(
        DraftPitcherOverallModifier,
        DraftPitcherStuffModifier,
        PitcherVelocityModifier,
        PitcherInjuryModifier,
    ),
)

# A draft class (legacy DraftClassRanker).
DRAFT = ScoringProfile(
    name="draft_class",
    ratings="potential",
    rp_multiplier=RP_OVERALL_MODIFIER - 0.1,
    shared_modifiers=(
        AgeModifier,
        ScoutingAccuracyModifier,
        PersonalityModifier,
        DraftSecondaryPersonalityModifier,
    ),
    batting_modifiers=POTENTIAL.batting_modifiers,
    pitching_modifiers=POTENTIAL.pitching_modifiers,
    demand_modifiers=(DraftDemandModifier,),
    two_way_threshold=2.2,
)

# keyed by ranking method, as `rankers.get_ranker.RANKERS` is
PROFILES = {p.name: p for p in (CURRENT, POTENTIAL, DRAFT)}
