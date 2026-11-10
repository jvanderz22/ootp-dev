"""The value stage (phase 5b): each side's talent (ranking/stages/talent.py) ->
WAR at a full-time role (ranking/value.py), the profile's modifiers, and the
two sides combined. The ledger is in display points, 50 + 10 x WAR, and its
counted lines sum to the value.

The profile's modifiers are the legacy ones, minus those v2 replaces (the
platoons replace the batter handedness modifier, and the development factors
the makeup and injury modifiers wherever potential ratings are read). The two
that weight themselves by the side's score read its WAR before them
(ranking/modifiers.py).

A hitter is platooned the way you use your roster (2026-11-08): against each
pitcher hand he starts in proportion to his WAR rate on that side next to an
average regular's - every start at average or better, none at replacement - so
a bat that's average only against right-handers becomes the strong side of a
platoon (~73% of PA) and one average only against left-handers the short side.
What he loses is the "platoon" ledger line; a hitter at least average on both
sides has none. A pitcher's split moves his matchups (`value.matchup_tilt`):
a reliever faces his strong side more, the way you'd use him, and a starter
his weak side, as lineups stack it - the "matchups" line.

The modifiers scale only WAR above replacement; where potential ratings are
read, the development factors (ranking/development.py) follow them, tapered
by the side's WAR. Below replacement only his personality counts, dividing
the deficit (`_modified`). A side a fitted talent model can't read (no
batting ratings, a pitcher without Stuff or Control) is valued at
replacement, with a ledger line saying so.
"""
import numpy as np

from ranking import development, fielding_talent, hitter_talent, pitcher_talent, value
from ranking.ledger import BATTING, DEVELOPMENT, MODEL, MODIFIERS, PITCHING, TWO_WAY, Ledger
from ranking.modifiers import in_war
from ranking.profiles import modifier_name
from ranking.ratings import RatingsView
from ranking.stages.base import BatchStage
from scoring.runtime_components import write_runtime_component

SCALE = value.DISPLAY_SCALE
# the legacy modifiers that are personality, so also count below replacement
# (the development factors replace PersonalityModifier wherever potential is read)
BELOW_REPLACEMENT = ("PersonalityModifier", "DraftSecondaryPersonalityModifier")


class Value(BatchStage):
    name = "value"

    def __init__(self, profile, model=None):
        self.ratings = RatingsView(profile.ratings)
        self.model = model or value.load()
        self.hitting_model = hitter_talent.load()
        self.fielding_model = fielding_talent.load()
        self.pitching_model = pitcher_talent.load()
        self.develops = profile.ratings == "potential"
        drop = {*value.PLATOON_REPLACES, *(development.REPLACES if self.develops else ())}
        self.modifiers = {
            side: [in_war(m, side) for m in profile.shared_modifiers + own if modifier_name(m) not in drop]
            for side, own in ((BATTING, profile.batting_modifiers), (PITCHING, profile.pitching_modifiers))
        }

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
        (and each side's, when known), fielding runs at his best position
        (against an average fielder there), the utility WAR, and baserunning
        runs per 600 PA. None without a batting fit."""
        fitted, side = state.fitted, state.batting
        batting = fitted["batting"]
        if batting is None:
            return None
        sides = None
        if batting.wrc_vl is not None:
            # the season his two sides make (his blended splits, or the
            # expected ones), so the platoon line adds up with it
            sides = {"vL": batting.wrc_vl, "vR": batting.wrc_vr}
            vs_lhp = self.hitting_model.platoon_mix[batting.bats]
            wrc = vs_lhp * batting.wrc_vl + (1 - vs_lhp) * batting.wrc_vr
        else:
            wrc = batting.wrc_plus
        field = fitted["fielding"]
        return {"wrc": wrc, "sides": sides, "fielding": field.runs, "position": field.best_position,
                "utility": field.utility_war, "baserunning": fitted["running"].runs}

    def _hitting(self, state) -> float:
        fitted, side = state.fitted, state.batting
        batting, field = fitted["batting"], fitted["fielding"]
        reads, cal = self.hitter_reads(state), self.model.calibrated
        if reads is None:
            side.best_position = side.role = field.best_position
            return self._unrated(state, side, BATTING, ("batting", "fielding", "running"), "batting")
        wrc = float(cal("wrc_plus", reads["wrc"]))
        sides = reads["sides"] and {s: float(cal("wrc_plus", w)) for s, w in reads["sides"].items()}
        position = reads["position"]
        runs = float(self.model.fielding_runs(reads["fielding"], position))
        fielding = float(self.model.fielding_value(runs, self.fielding_model.position_adjustment[position]))
        pa = self.model.hitter_pa
        batting_runs = (wrc / 100 - 1) * self.hitting_model.mlb_runs_per_pa * pa
        running = float(cal("baserunning", reads["baserunning"])) * pa / 600
        parts = {**self.model.hitting(batting_runs, fielding, running), "utility": reads["utility"]}
        platoon = self._platoon(sides, batting and batting.bats, parts, pa)
        ledger = state.ledger
        how = [f"vL {sides['vL']:.0f} / vR {sides['vR']:.0f}" if sides else None,
               f"{batting_runs:+.1f} runs",
               "on his splits" if batting and batting.platoon else None,
               "BABIP from Contact" if batting and batting.babip_implied else None]
        ledger.add(MODEL, "batting", SCALE * parts["batting"], BATTING,
                   f"{wrc:.0f} wRC+", ", ".join(h for h in how if h))
        ledger.add(MODEL, "fielding", SCALE * parts["fielding"], BATTING,
                   f"{position} {runs:+.0f} runs", f"{fielding:+.0f} with the {position} adjustment")
        if field.covers:
            ledger.add(MODEL, "utility", SCALE * parts["utility"], BATTING, f"covers {', '.join(field.covers)}")
        ledger.add(MODEL, "baserunning", SCALE * parts["running"], BATTING, f"{running:+.1f} runs")
        ledger.add(MODEL, "playing time", SCALE * parts["allowance"], BATTING,
                   f"{pa:.0f} PA", "a full-time regular's credit over replacement")
        if platoon and not any(platoon[1].values()):
            # below replacement on both sides: no starts to credit, so he's
            # valued at his full-time WAR, which keeps the bottom ordered
            ledger.add(MODEL, "platoon", 0.0, BATTING, "no starts", "below replacement on both sides")
        elif platoon:
            war_lost, starts = platoon
            ledger.add(MODEL, "platoon", SCALE * war_lost, BATTING,
                       f"{starts['vR']:.0%} vs RHP, {starts['vL']:.0%} vs LHP", "his share of starts")
            parts["platoon"] = war_lost
        side.components = {
            "batting": SCALE * (parts["batting"] + parts["allowance"] + parts.get("platoon", 0.0)),
            "fielding": SCALE * (parts["fielding"] + parts["utility"]),
            "running": SCALE * parts["running"],
        }
        side.best_position = side.role = field.best_position
        state.wrc_plus = wrc
        war = sum(parts.values())
        developing = self._development(state, war)
        if self.develops and batting and batting.bats == "S":
            developing.append(development.switch_hitter(war))
        self._modifiers(state, side, BATTING, war)
        return self._modified(state, side, war, BATTING, developing)

    def _platoon(self, sides, bats, parts, pa):
        """(WAR the platoon takes off, {side: share of starts}) for a hitter
        whose vs-L / vs-R wRC+ (`sides`) are known, or None when nothing
        changes. A side's WAR rate is his season at that side's wRC+; he
        starts it in proportion to that rate over an average regular's (the
        allowance)."""
        if sides is None:
            return None
        rest = parts["fielding"] + parts["utility"] + parts["running"] + parts["allowance"]
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
        reads him, before calibration; None without a fit."""
        fitted = state.fitted["pitching"]
        if fitted is None:
            return None
        return {"sp": fitted.sp_era, "rp": fitted.rp_era, "rates": fitted.sp_rates}

    def _pitching(self, state) -> float:
        player, side, fitted = state.player, state.pitching, state.fitted["pitching"]
        if fitted is None:
            return self._unrated(state, side, PITCHING, ("starter", "reliever"), "pitching")
        sp_era, rp_era, rp_index, sp_index = fitted.sp_era, fitted.rp_era, fitted.rp_index, fitted.sp_index
        stuff = {"sp": f"Stuff {fitted.sp_stuff:.0f} as SP", "rp": f"Stuff {fitted.rp_stuff:.0f} as RP"}
        splits = ", on his splits" if fitted.platoon else ""
        split = {"sp": fitted.sp_split, "rp": fitted.rp_split}
        estimated = fitted.split_estimated
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
        innings = self.model.starter_innings(stamina, pitches, fitted.sp_rates)
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
            side.role, state.era = "SP", era["sp"]
            ledger.add(MODEL, "pitching", SCALE * sp_normal["runs"], PITCHING,
                       f"{era['sp']:.2f} ERA", stuff["sp"] + splits)
            if tilt["sp"] > 0:
                gap = (era["sp matched"] - era["sp"]) / tilt["sp"]
                ledger.add(MODEL, "matchups", SCALE * (starting["runs"] - sp_normal["runs"]), PITCHING,
                           f"+{tilt['sp']:.0%} on his weak side", f"{gap:.2f} ERA split, {how}")
            ledger.add(MODEL, "innings", SCALE * starting["innings"], PITCHING,
                       f"{innings:.0f} IP", f"stamina {stamina}")
            war = sp_war
        else:
            side.role, state.era = "RP", era["rp"]
            leverage = float(self.model.leverage(rp_index))
            ledger.add(MODEL, "pitching", SCALE * normal["runs"], PITCHING,
                       f"{era['rp']:.2f} ERA", stuff["rp"] + splits)
            ledger.add(MODEL, "leverage", SCALE * normal["leverage"], PITCHING, f"LI {leverage:.2f}")
            if tilt["rp"] > 0:
                gap = (era["rp"] - era["rp matched"]) / tilt["rp"]
                ledger.add(MODEL, "matchups", SCALE * (rp_war - normal["runs"] - normal["leverage"] - normal["innings"]),
                           PITCHING, f"+{tilt['rp']:.0%} on his strong side", f"{gap:.2f} ERA split, {how}")
            ledger.add(MODEL, "innings", SCALE * relieving["innings"], PITCHING,
                       f"{self.model.workloads['reliever_ip']:.0f} IP", "a reliever's workload")
            war = rp_war
        write_runtime_component(player.id, "pitching.value.starter_war", sp_war if starting else 0.0)
        write_runtime_component(player.id, "pitching.value.reliever_war", rp_war)
        control = self.ratings.control(player)
        floor = value.control_floor(control)
        floors = [("Control floor", floor, f"Control {control}")] if floor < 1 else []
        self._modifiers(state, side, PITCHING, war)
        return self._modified(state, side, war, PITCHING, self._development(state, war), floors)

    # -- both ------------------------------------------------------------------

    @staticmethod
    def _unrated(state, side, side_name, components, what) -> float:
        """A side no fitted model can read: valued at replacement."""
        state.ledger.add(MODEL, f"no {what} ratings", 0.0, side_name, note="none the model can read: valued at replacement")
        side.components = dict.fromkeys(components, 0.0)
        side.score = 0.0
        write_runtime_component(state.player.id, f"{side_name}.value.war", 0.0)
        return 0.0

    def _modifiers(self, state, side, side_name, war):
        """The profile's modifiers for the side, fed its WAR before them, into
        `side.modifiers` as (name, factor); recorded for the card."""
        player, product = state.player, 1.0
        for modifier in self.modifiers[side_name]:
            factor = modifier.calculate_player_modifier(player, war)
            name = modifier_name(modifier)
            write_runtime_component(player.id, f"{side_name}.modifiers.{name}", factor)
            side.modifiers.append((name, factor))
            product *= factor
        write_runtime_component(player.id, f"{side_name}.modifier_total", product)

    def _development(self, state, war) -> list:
        return development.factors(state.player, war) if self.develops else []

    @staticmethod
    def _modified(state, side, war, side_name, developing=(), floors=()) -> float:
        """The side's WAR after its floors, its modifiers and then its
        development factors, which scale the part above replacement. Below
        replacement only his personality counts (decided 2026-11-08), in
        reverse: the development factors and BELOW_REPLACEMENT modifiers
        divide the deficit, so good makeup shrinks it. Recorded as ledger
        lines and the side's score."""
        if war < 0:
            below = SCALE * war
            personality = [(MODIFIERS, n, f, None) for n, f in side.modifiers if n in BELOW_REPLACEMENT]
            for stage, name, factor, note in personality + [(DEVELOPMENT, *d) for d in developing]:
                if factor > 0:
                    below = state.ledger.scale(stage, name, below, 1 / factor, side_name, note)
            modified = below / SCALE
            side.score = SCALE * modified
            write_runtime_component(state.player.id, f"{side_name}.value.war", modified)
            return modified
        above = SCALE * war
        for name, factor, note in floors:
            above = state.ledger.scale(MODEL, name, above, factor, side_name, note)
        for name, factor in side.modifiers:
            above = state.ledger.scale(MODIFIERS, name, above, factor, side_name)
        for name, factor, note in developing:
            above = state.ledger.scale(DEVELOPMENT, name, above, factor, side_name, note)
        modified = above / SCALE
        side.score = SCALE * modified
        write_runtime_component(state.player.id, f"{side_name}.value.war", modified)
        return modified

    @staticmethod
    def _combine(state, hitting, pitching):
        primary, secondary = (BATTING, PITCHING) if hitting >= pitching else (PITCHING, BATTING)
        state.ledger.side = primary
        state.ledger.role = (state.batting if primary == BATTING else state.pitching).role
        war = max(hitting, pitching)
        other = min(hitting, pitching)
        share = value.two_way_share(other)
        if share > 0:
            bonus = share * other
            role = "pitcher" if secondary == PITCHING else "hitter"
            state.ledger.add(TWO_WAY, "two-way", SCALE * bonus, stat=f"{share:.0%} of {other:.1f} WAR", note=f"as a {role}")
            war += bonus
        state.value = float(value.points(war))
