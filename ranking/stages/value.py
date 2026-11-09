"""The value stage (phase 5b): each side's talent -> WAR at a full-time role
(ranking/value.py), the profile's modifiers, and the two sides combined.

It runs after LegacyModel and LegacyModifiers, which still compute what the
legacy modifiers need (their factors are weighted by the legacy score), and
replaces their points with WAR: the ledger is rewritten in display points,
50 + 10 x WAR, and its counted lines sum to the value.

A hitter is platooned the way you use your roster (2026-11-08): against each
pitcher hand he starts in proportion to his WAR rate on that side next to an
average regular's - every start at average or better, none at replacement - so
a bat that's average only against right-handers becomes the strong side of a
platoon (~73% of PA) and one average only against left-handers the short side.
What he loses is the "platoon" ledger line; a hitter at least average on both
sides has none. A pitcher's split moves his matchups (`value.matchup_tilt`):
a reliever faces his strong side more, the way you'd use him, and a starter
his weak side, as lineups stack it - the "RP / SP matchups" lines.

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

    def hitter_reads(self, state) -> dict:
        """His talent as the fitted models read it, before calibration: wRC+
        (and each side's, when known), fielding value at his best position
        (runs with the position), legacy's utility bonus in runs, and
        baserunning runs per 600 PA."""
        fitted, side = state.fitted, state.batting
        batting = fitted["batting"]
        sides = None
        if batting and batting.wrc_vl is not None:
            # the season his two sides make (his blended splits, or the
            # expected ones), so the platoon line adds up with it
            sides = {"vL": batting.wrc_vl, "vR": batting.wrc_vr}
            vs_lhp = self.hitting_model.platoon_mix[batting.bats]
            wrc = vs_lhp * batting.wrc_vl + (1 - vs_lhp) * batting.wrc_vr
        elif batting:
            wrc = batting.wrc_plus
        else:
            wrc = float(bridge.talent(side.components["batting"], self.hitting_model.bridge))
        field = fitted["fielding"]
        # legacy's utility bonus, in runs: what it adds through the fielding bridge
        utility = float(bridge.talent(field.points + field.utility, self.fielding_model.bridge)
                        - bridge.talent(field.points, self.fielding_model.bridge))
        return {"wrc": wrc, "sides": sides, "fielding": field.value, "utility": utility,
                "baserunning": fitted["running"].runs}

    def _hitting(self, state) -> float:
        fitted, side = state.fitted, state.batting
        batting, field = fitted["batting"], fitted["fielding"]
        reads, cal = self.hitter_reads(state), self.model.calibrated
        wrc = float(cal("wrc_plus", reads["wrc"]))
        sides = reads["sides"] and {s: float(cal("wrc_plus", w)) for s, w in reads["sides"].items()}
        fielding = float(cal("fielding", reads["fielding"]))
        utility = float(cal("fielding", reads["fielding"] + reads["utility"])) - fielding
        pa = self.model.hitter_pa
        batting_runs = (wrc / 100 - 1) * self.hitting_model.mlb_runs_per_pa * pa
        running = float(cal("baserunning", reads["baserunning"])) * pa / 600
        parts = self.model.hitting(batting_runs, fielding + utility, running)
        platoon = self._platoon(sides, batting and batting.bats, parts, pa)
        utility_war = self.model.hitter["per_defense_run"] * utility
        runs = fielding - self.fielding_model.position_adjustment[field.best_position]
        ledger = state.ledger
        splits = " on his vL / vR splits" if batting and batting.platoon else ""
        ledger.add(MODEL, f"batting talent ({wrc:.0f} wRC+{splits}, {batting_runs:+.1f} runs)",
                   SCALE * parts["batting"], BATTING)
        ledger.add(MODEL, f"fielding ({field.best_position}, {runs:+.0f} runs, {fielding:+.0f} with position)",
                   SCALE * (parts["fielding"] - utility_war), BATTING)
        ledger.add(MODEL, f"utility ({utility:+.1f} runs)", SCALE * utility_war, BATTING)
        ledger.add(MODEL, f"baserunning ({running:+.1f} runs)", SCALE * parts["running"], BATTING)
        ledger.add(MODEL, f"position player allowance ({pa:.0f} PA)", SCALE * parts["allowance"], BATTING)
        if platoon:
            war_lost, starts = platoon
            ledger.add(MODEL, f"platoon (starts {starts['vR']:.0%} vs RHP, {starts['vL']:.0%} vs LHP)",
                       SCALE * war_lost, BATTING)
            parts["platoon"] = war_lost
        side.components = {
            "batting": SCALE * (parts["batting"] + parts["allowance"] + parts.get("platoon", 0.0)),
            "fielding": SCALE * parts["fielding"],
            "running": SCALE * parts["running"],
        }
        side.best_position = field.best_position
        state.wrc_plus = wrc
        war = sum(parts.values())
        developing = self._development(state, war)
        if self.develops and batting and batting.bats == "S":
            developing.append(development.switch_hitter(war))
        return self._modified(state, side, war, BATTING, developing)

    def _platoon(self, sides, bats, parts, pa):
        """(WAR the platoon takes off, {side: share of starts}) for a hitter
        whose vs-L / vs-R wRC+ (`sides`) are known, or None when nothing
        changes. A side's WAR rate is his season at that side's wRC+; he
        starts it in proportion to that rate over an average regular's (the
        allowance)."""
        if sides is None:
            return None
        rest = parts["fielding"] + parts["running"] + parts["allowance"]
        per_run = self.model.hitter["per_batting_run"] * self.hitting_model.mlb_runs_per_pa * pa
        rate = {s: per_run * (w / 100 - 1) + rest for s, w in sides.items()}
        starts = {s: float(np.clip(w / parts["allowance"], 0.0, 1.0)) for s, w in rate.items()}
        share = {"vL": self.hitting_model.platoon_mix[bats]}
        share["vR"] = 1 - share["vL"]
        lost = -sum(share[s] * (1 - starts[s]) * rate[s] for s in rate)
        return (lost, starts) if abs(lost) > 1e-9 else None

    # -- pitchers --------------------------------------------------------------

    def pitcher_reads(self, state) -> dict:
        """{"sp" | "rp": ERA, "rates": his starter rates} as the fitted model
        reads him (or the legacy scorer through the bridges, without rates),
        before calibration."""
        fitted = state.fitted["pitching"]
        if fitted:
            return {"sp": fitted.sp_era, "rp": fitted.rp_era, "rates": fitted.sp_rates}
        sp_era, rp_era, _ = self._legacy_eras(state.player)
        return {"sp": sp_era, "rp": rp_era, "rates": None}

    def _pitching(self, state) -> float:
        player, side, fitted = state.player, state.pitching, state.fitted["pitching"]
        if fitted:
            sp_era, rp_era, rp_index = fitted.sp_era, fitted.rp_era, fitted.rp_index
            stuff = {"sp": f"Stuff {fitted.sp_stuff:.0f} as SP, ", "rp": f"Stuff {fitted.rp_stuff:.0f} as RP, "}
            splits = " on his vL / vR splits" if fitted.platoon else ""
            split = {"sp": fitted.sp_split, "rp": fitted.rp_split}
            estimated = fitted.split_estimated
        else:
            sp_era, rp_era, rp_index = self._legacy_eras(player)
            stuff, splits, split, estimated = {"sp": "", "rp": ""}, "", {"sp": 0.0, "rp": 0.0}, False
        sp_index = fitted.sp_index if fitted else 100.0   # no split without a fit: unused
        stamina, pitches = self.ratings.stamina(player), self.ratings.pitch_count(player)
        # his matchups: index is linear in the events, so moving `tilt` of his
        # batters to one side moves it by tilt x split; ERA in step. Leverage
        # reads the talent-scale index (its map is by talent percentile); runs
        # saved read the calibrated ERA.
        tilt = {role: value.matchup_tilt(split[role]) for role in split}
        sp_matched = sp_index + tilt["sp"] * abs(split["sp"])
        rp_matched = rp_index - tilt["rp"] * abs(split["rp"])
        cal = self.model.calibrated
        era = {
            "sp": float(cal("era", sp_era, "sp")), "rp": float(cal("era", rp_era, "rp")),
            "sp matched": float(cal("era", sp_era * sp_matched / sp_index, "sp")),
            "rp matched": float(cal("era", rp_era * rp_matched / rp_index, "rp")),
        }
        innings = self.model.starter_innings(stamina, pitches, fitted and fitted.sp_rates)
        starting = self.model.starting(era["sp matched"], innings) if innings else None
        sp_normal = self.model.starting(era["sp"], innings) if innings else None
        normal = self.model.relieving(era["rp"], rp_index)
        relieving = self.model.relieving(era["rp matched"], rp_matched)
        how = "estimated from slot and pitches" if estimated else "on his splits"
        sp_war = sum(starting.values()) if starting else None
        rp_war = sum(relieving.values())
        side.components = {"starter": SCALE * sp_war if starting else 0.0, "reliever": SCALE * rp_war}
        ledger = state.ledger
        if starting and sp_war >= rp_war:
            state.era = era["sp"]
            ledger.add(MODEL, f"SP talent ({stuff['sp']}{era['sp']:.2f} ERA{splits})", SCALE * sp_normal["runs"], PITCHING)
            if tilt["sp"] > 0:
                gap = (era["sp matched"] - era["sp"]) / tilt["sp"]
                ledger.add(MODEL, f"SP matchups (+{tilt['sp']:.0%} of batters on his weak side, {gap:.2f} ERA split {how})",
                           SCALE * (starting["runs"] - sp_normal["runs"]), PITCHING)
            ledger.add(MODEL, f"SP innings (stamina {stamina}, {innings:.0f} IP)", SCALE * starting["innings"], PITCHING)
            war = sp_war
        else:
            state.era = era["rp"]
            leverage = float(self.model.leverage(rp_index))
            ledger.add(MODEL, f"RP talent ({stuff['rp']}{era['rp']:.2f} ERA{splits})", SCALE * normal["runs"], PITCHING)
            ledger.add(MODEL, f"RP leverage (LI {leverage:.2f})", SCALE * normal["leverage"], PITCHING)
            if tilt["rp"] > 0:
                gap = (era["rp"] - era["rp matched"]) / tilt["rp"]
                ledger.add(MODEL, f"RP matchups (+{tilt['rp']:.0%} of batters on his strong side, {gap:.2f} ERA split {how})",
                           SCALE * (rp_war - normal["runs"] - normal["leverage"] - normal["innings"]), PITCHING)
            ledger.add(MODEL, f"RP innings ({self.model.workloads['reliever_ip']:.0f} IP)",
                       SCALE * relieving["innings"], PITCHING)
            war = rp_war
        write_runtime_component(player.id, "pitching.value.starter_war", sp_war if starting else 0.0)
        write_runtime_component(player.id, "pitching.value.reliever_war", rp_war)
        control = self.ratings.control(player)
        floor = value.control_floor(control)
        floors = [(f"Control floor (Control {control}, x{floor:.2f})", floor)] if floor < 1 else []
        return self._modified(state, side, war, PITCHING, self._development(state, war), floors)

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
    def _modified(state, side, war, side_name, developing=(), floors=()) -> float:
        """The side's WAR after its floors, its modifiers and then its
        development factors, which scale only the part above replacement;
        recorded as ledger lines and the side's score."""
        above = SCALE * max(war, 0.0)
        for name, factor in floors:
            above = state.ledger.scale(MODEL, name, above, factor, side_name)
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
