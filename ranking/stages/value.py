"""The value stage (phase 5b): each side's talent -> WAR at a full-time role
(ranking/value.py), the profile's modifiers, and the two sides combined.

It runs after LegacyModel and LegacyModifiers, which still compute what the
legacy modifiers need (their factors are weighted by the legacy score), and
replaces their points with WAR: the ledger is rewritten in display points,
50 + 10 x WAR, and its counted lines sum to the value.

The modifiers scale only WAR above replacement, so a factor below 1 can't
lift a below-replacement player; where potential ratings are read, the
development factors (ranking/development.py) follow them, tapered by the
side's WAR. A player a fitted talent model couldn't
score (an export without BABIP, a pitcher without Stuff) is priced from his
legacy points, read back through the talent model's points bridge.
"""
import numpy as np

from ranking import bridge, development, fielding_talent, hitter_talent, pitcher_talent, value
from ranking.ledger import BATTING, DEVELOPMENT, MODEL, MODIFIERS, PITCHING, TWO_WAY, Ledger
from ranking.ratings import RatingsView
from ranking.stages.base import BatchStage
from scoring.runtime_components import get_runtime_components, write_runtime_component

SCALE = value.DISPLAY_SCALE


class Value(BatchStage):
    name = "value"

    def __init__(self, profile, model=None):
        self.ratings = RatingsView(profile.ratings)
        self.model = model or value.load()
        self.hitting_model = hitter_talent.load()
        self.fielding_model = fielding_talent.load()
        self.pitching_model = pitcher_talent.load()
        self.develops = profile.ratings == "potential"

    @property
    def artifacts(self) -> dict:
        return {self.name: self.model.version}

    def run(self, states, profile):
        for state in states:
            state.ledger = Ledger()
            state.ledger.add(MODEL, "replacement level", value.DISPLAY_OFFSET)
            hitting = self._hitting(state)
            pitching = self._pitching(state)
            self._combine(state, hitting, pitching)

    # -- hitters ---------------------------------------------------------------

    def _hitting(self, state) -> float:
        fitted, side = state.fitted, state.batting
        wrc = fitted["batting"].wrc_plus if fitted["batting"] else float(
            bridge.talent(side.components["batting"], self.hitting_model.bridge))
        pa = self.model.hitter_pa
        batting_runs = (wrc / 100 - 1) * self.hitting_model.mlb_runs_per_pa * pa
        field = fitted["fielding"]
        # legacy's utility bonus, in runs: what it adds through the fielding bridge
        utility = float(bridge.talent(field.points + field.utility, self.fielding_model.bridge)
                        - bridge.talent(field.points, self.fielding_model.bridge))
        running = fitted["running"].runs * pa / 600
        parts = self.model.hitting(batting_runs, field.value + utility, running)
        utility_war = self.model.hitter["per_defense_run"] * utility
        ledger = state.ledger
        ledger.add(MODEL, f"batting talent ({wrc:.0f} wRC+, {batting_runs:+.1f} runs)", SCALE * parts["batting"], BATTING)
        ledger.add(MODEL, f"fielding ({field.best_position}, {field.runs:+.0f} runs, {field.value:+.0f} with position)",
                   SCALE * (parts["fielding"] - utility_war), BATTING)
        ledger.add(MODEL, f"utility ({utility:+.1f} runs)", SCALE * utility_war, BATTING)
        ledger.add(MODEL, f"baserunning ({running:+.1f} runs)", SCALE * parts["running"], BATTING)
        ledger.add(MODEL, f"position player allowance ({pa:.0f} PA)", SCALE * parts["allowance"], BATTING)
        side.components = {
            "batting": SCALE * (parts["batting"] + parts["allowance"]),
            "fielding": SCALE * parts["fielding"],
            "running": SCALE * parts["running"],
        }
        side.best_position = field.best_position
        state.wrc_plus = wrc
        war = sum(parts.values())
        return self._modified(state, side, war, BATTING, self._development(state, war))

    # -- pitchers --------------------------------------------------------------

    def _pitching(self, state) -> float:
        player, side, fitted = state.player, state.pitching, state.fitted["pitching"]
        if fitted:
            sp_era, rp_era, rp_index = fitted.sp_era, fitted.rp_era, fitted.rp_index
            stuff = {"sp": f"Stuff {fitted.sp_stuff:.0f} as SP, ", "rp": f"Stuff {fitted.rp_stuff:.0f} as RP, "}
            splits = " on his vL / vR splits" if fitted.platoon else ""
        else:
            sp_era, rp_era, rp_index = self._legacy_eras(player)
            stuff, splits = {"sp": "", "rp": ""}, ""
        stamina, pitches = self.ratings.stamina(player), self.ratings.pitch_count(player)
        innings = self.model.starter_innings(stamina, pitches)
        starting = self.model.starting(sp_era, innings) if innings else None
        relieving = self.model.relieving(rp_era, rp_index)
        sp_war = sum(starting.values()) if starting else None
        rp_war = sum(relieving.values())
        side.components = {"starter": SCALE * sp_war if starting else 0.0, "reliever": SCALE * rp_war}
        ledger = state.ledger
        if starting and sp_war >= rp_war:
            state.era = sp_era
            ledger.add(MODEL, f"SP talent ({stuff['sp']}{sp_era:.2f} ERA{splits})", SCALE * starting["runs"], PITCHING)
            ledger.add(MODEL, f"SP innings (stamina {stamina}, {innings:.0f} IP)", SCALE * starting["innings"], PITCHING)
            war = sp_war
        else:
            state.era = rp_era
            leverage = float(self.model.leverage(rp_index))
            ledger.add(MODEL, f"RP talent ({stuff['rp']}{rp_era:.2f} ERA{splits})", SCALE * relieving["runs"], PITCHING)
            ledger.add(MODEL, f"RP leverage (LI {leverage:.2f})", SCALE * relieving["leverage"], PITCHING)
            ledger.add(MODEL, f"RP innings ({self.model.workloads['reliever_ip']:.0f} IP)",
                       SCALE * relieving["innings"], PITCHING)
            war = rp_war
        write_runtime_component(player.id, "pitching.value.starter_war", sp_war if starting else 0.0)
        write_runtime_component(player.id, "pitching.value.reliever_war", rp_war)
        return self._modified(state, side, war, PITCHING, self._development(state, war))

    def _legacy_eras(self, player):
        """(SP ERA, RP ERA, RP runs index) from the legacy scorer's role points,
        through the fitted model's bridges; ERA scales with the index."""
        recorded = (get_runtime_components(player.id) or {}).get(PITCHING, {})
        index = {
            role: float(bridge.talent(recorded.get(name, {}).get("model", 0.0), self.pitching_model.bridges[role]))
            for role, name in (("sp", "starter"), ("rp", "reliever"))
        }
        era = self.model.pitcher["league_era"]
        return era * index["sp"] / 100, era * index["rp"] / 100, index["rp"]

    # -- both ------------------------------------------------------------------

    def _development(self, state, war) -> list:
        return development.factors(state.player, war) if self.develops else []

    @staticmethod
    def _modified(state, side, war, side_name, developing=()) -> float:
        """The side's WAR after its modifiers and then its development factors,
        which scale only the part above replacement; recorded as ledger lines
        and the side's score."""
        above = SCALE * max(war, 0.0)
        for name, factor in side.modifiers:
            above = state.ledger.scale(MODIFIERS, name, above, factor, side_name)
        for name, factor in developing:
            above = state.ledger.scale(DEVELOPMENT, name, above, factor, side_name)
        modified = min(war, 0.0) + above / SCALE
        side.score = SCALE * modified
        write_runtime_component(state.player.id, f"{side_name}.value.war", modified)
        return modified

    @staticmethod
    def _combine(state, hitting, pitching):
        primary, secondary = (BATTING, PITCHING) if hitting >= pitching else (PITCHING, BATTING)
        state.ledger.side = primary
        war = max(hitting, pitching)
        other = min(hitting, pitching)
        share = value.two_way_share(other)
        if share > 0:
            bonus = share * other
            role = "pitcher" if secondary == PITCHING else "hitter"
            state.ledger.add(TWO_WAY, f"two-way ({share:.0%} of {other:.1f} WAR as a {role})", SCALE * bonus)
            war += bonus
        state.value = float(value.points(war))
