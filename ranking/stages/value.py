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

from ranking import development, draft_odds, fielding_talent, hitter_talent, pitcher_talent, value
from ranking.ledger import BATTING, DEVELOPMENT, MODEL, MODIFIERS, PITCHING, TWO_WAY, Ledger
from ranking.modifiers import in_war
from ranking.profiles import modifier_name
from ranking.ratings import RatingsView
from ranking.stages.base import BatchStage
from scoring.runtime_components import write_runtime_component

SCALE = value.DISPLAY_SCALE
# a matchups effect smaller than this (display points: 0.01 WAR) rides on the
# pitching line instead of a line of its own
MATCHUPS_SHOWN = 0.1


def _hands(throws, split) -> tuple:
    """(the batters he's weak against, the ones he's strong against) for a
    pitcher throwing `throws` whose split is `split` (positive: better against
    his own hand)."""
    if throws not in ("L", "R"):
        return "his weak side", "his strong side"
    own, other = f"{throws}HB", f"{'R' if throws == 'L' else 'L'}HB"
    return (other, own) if split >= 0 else (own, other)
def _modifier_note(name, player) -> str:
    """The card's note for a judgment line the draft odds keep (only notes:
    the modifier reads the rating itself)."""
    if name == "ScoutingAccuracyModifier" and player.scouting_accuracy not in ("Very High", None):
        return player.scouting_accuracy
    if name == "DraftSecondaryPersonalityModifier":
        return {"H": "leadership H", "L": "leadership L"}.get(player.leadership)
    return None


# the legacy modifiers that are personality, so also count below replacement
# (the development factors replace PersonalityModifier wherever potential is read)
BELOW_REPLACEMENT = ("PersonalityModifier", "DraftSecondaryPersonalityModifier")


class Value(BatchStage):
    name = "value"

    def __init__(self, profile, model=None, league=None, replacement=None):
        self.ratings = RatingsView(profile.ratings)
        self.model = model or value.load()
        # the league's spots and their prices (value.Replacement); None values
        # him over StatsPlus's replacement, as the potential and draft boards do
        self.league = league
        self.league_replacement = profile.league_replacement
        if replacement is None and profile.league_replacement:
            replacement = value.replacement(league)
        self.replacement = replacement if profile.league_replacement else None
        self.hitting_model = hitter_talent.load()
        self.fielding_model = fielding_talent.load()
        self.pitching_model = pitcher_talent.load()
        # the draft odds (ranking/draft_odds.py) replace the development
        # factors and the modifiers they cover, wherever the profile has them
        self.odds = draft_odds.load() if profile.odds else None
        self.develops = profile.ratings == "potential" and profile.development and not self.odds
        drop = {*value.PLATOON_REPLACES, *(development.REPLACES if self.develops or self.odds else ()),
                *(draft_odds.REPLACES if self.odds else ())}
        self.modifiers = {
            side: [in_war(m, side) for m in profile.shared_modifiers + own if modifier_name(m) not in drop]
            for side, own in ((BATTING, profile.batting_modifiers), (PITCHING, profile.pitching_modifiers))
        }

    @property
    def artifacts(self) -> dict:
        out = {self.name: self.model.version}
        if self.league_replacement:
            out["replacement"] = f"{value.REPLACEMENT_ARTIFACT}:{self.league or value.DEFAULT_LEAGUE}"
        if self.odds:
            out["draft_odds"] = self.odds.version
        return out

    def _spot(self, side, spots, spot) -> list:
        """Value the side at `spot` of his `spots`: the ledger adjustments
        (label, WAR, stat, note) from his full-time WAR down to that spot's
        price, recorded on the side."""
        side.spots = spots
        price, full = self.replacement.prices[spot], spots.get("H", spots.get(spot))
        out = []
        if spot.startswith("H") and spot != "H":
            out.append(("playing time", spots[spot] - full, f"{self.replacement.share(spot):.0%} of a regular's PA",
                        value.Replacement.describe(spot)))
        out.append(("league replacement", -price, None, value.Replacement.describe(spot)))
        side.replacement = -sum(delta for _, delta, _, _ in out)
        return out

    def run(self, states, profile):
        for state in states:
            state.ledger = Ledger()
            state.ledger.add(MODEL, "replacement level", value.DISPLAY_OFFSET)
            hitting = self._hitting(state)
            pitching = self._pitching(state)
            self._combine(state, hitting, pitching)
            if self.odds:
                self._distribution(state)

    def _distribution(self, state):
        """The card's odds for the side he's judged on: his ceiling, the
        likely range, the chance he becomes a regular and the chance he
        outgrows his ceiling."""
        odds = (state.batting if state.ledger.side == BATTING else state.pitching).odds
        if odds is None:
            return
        out = self.odds.distribution(odds["columns"], odds["growth"], odds["ceiling"], odds["group"],
                                     odds["expected"], odds["scale"])
        state.odds = {"ceiling": odds["ceiling"], **out}

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
        fielding = float(self.model.fielding_value(runs, self.fielding_model.adjustment(position)))
        pa = self.model.hitter_pa
        batting_runs = (wrc / 100 - 1) * self.hitting_model.mlb_runs_per_pa * pa
        running = float(cal("baserunning", reads["baserunning"])) * pa / 600
        parts = {**self.model.hitting(batting_runs, fielding, running), "utility": reads["utility"]}
        platoon = self._platoon(sides, batting and batting.bats, parts, pa)
        ledger = state.ledger
        # batting over replacement: the allowance (a full-time regular's
        # credit, the same for every hitter) rides on the batting line
        if sides:
            # by side (the card's splits row): his splits, or the expected ones for his hand
            for s, w in sides.items():
                write_runtime_component(state.player.id, f"batting.value.wrc_{s.lower()}", w)
            write_runtime_component(state.player.id, "batting.value.splits_expected", not batting.platoon)
        how = [f"{batting_runs:+.1f} runs vs avg",
               "BABIP from Contact" if batting and batting.babip_implied else None]
        ledger.add(MODEL, "batting", SCALE * (parts["batting"] + parts["allowance"]), BATTING,
                   f"{wrc:.0f} wRC+", " · ".join(h for h in how if h))
        ledger.add(MODEL, "fielding", SCALE * parts["fielding"], BATTING,
                   position if position == fielding_talent.DH else f"{position} {runs:+.0f} runs", f"{fielding:+.0f} with position")
        if field.covers:
            ledger.add(MODEL, "utility", SCALE * parts["utility"], BATTING, f"covers {', '.join(field.covers)}")
        ledger.add(MODEL, "baserunning", SCALE * parts["running"], BATTING, f"{running:+.1f} runs")
        if platoon and not any(platoon[1].values()):
            # below replacement on both sides: no starts to credit, so he's
            # valued at his full-time WAR, which keeps the bottom ordered
            ledger.add(MODEL, "platoon", 0.0, BATTING, "no starts", "below replacement both sides")
        elif platoon:
            war_lost, starts = platoon
            ledger.add(MODEL, "platoon", SCALE * war_lost, BATTING,
                       f"{starts['vR']:.0%} vs RHP · {starts['vL']:.0%} vs LHP", "share of starts")
            parts["platoon"] = war_lost
        side.components = {
            "batting": SCALE * (parts["batting"] + parts["allowance"] + parts.get("platoon", 0.0)),
            "fielding": SCALE * (parts["fielding"] + parts["utility"]),
            "running": SCALE * parts["running"],
        }
        self._positions(state.player, field)
        side.best_position = side.role = field.best_position
        state.wrc_plus = wrc
        war = sum(parts.values())
        if self.odds:
            self._modifiers(state, side, BATTING, war)
            switch = development.switch_hitter(war) if batting and batting.bats == "S" else None
            return self._odds(state, side, BATTING, war, "hitter", switch=switch)
        developing = self._development(state, war)
        if self.develops and batting and batting.bats == "S":
            developing.append(development.switch_hitter(war))
        self._modifiers(state, side, BATTING, war)
        adjustments = []
        if self.replacement:
            spots = self.replacement.hitter_spots(war)
            spot = self.replacement.best(spots)
            if spots[spot] < self.replacement.prices[spot]:
                # below replacement at every spot: no part-time bat shrinks
                # that, so he's valued full-time, which keeps the bottom ordered
                spot = "H"
            adjustments = self._spot(side, spots, spot)
        return self._modified(state, side, war, BATTING, developing, adjustments=adjustments)

    def _positions(self, player, field):
        """Record his fielding at every position for the card, calibrated the
        way his best one is valued: runs there, the value with its adjustment
        (the ledger's "with position"), the floor factor where a floor bites,
        and whether utility credits it."""
        adjustment = self.fielding_model.position_adjustment
        for pos, (raw, floor) in (field.positions or {}).items():
            runs = float(self.model.fielding_runs(raw, pos))
            path = f"batting.positions.{pos}"
            write_runtime_component(player.id, f"{path}.runs", runs)
            write_runtime_component(player.id, f"{path}.value", self.model.fielding_value(runs, adjustment[pos]))
            if floor < 1:
                write_runtime_component(player.id, f"{path}.floor", floor)
            if pos in field.covers:
                write_runtime_component(player.id, f"{path}.covers", 1.0)

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
        sp_war = sum(starting.values()) if starting else None
        adjustments = []
        if self.replacement:
            # leverage is the bullpen spot's, credited as StatsPlus's WAR credits it
            # and so are his matchups: the spot's tilt to his strong side
            weight = self.model.pitcher["rp"]["statsplus_leverage_weight"]
            tilts = self.replacement.tilts(split["rp"])
            runs = []
            for t in tilts:
                index = rp_index - t * abs(split["rp"])
                runs.append(self.model.relieving(float(cal("era", rp_era * index / rp_index, "rp")), index)["runs"])
            spots = self.replacement.relief_spots(runs, relieving["innings"], weight)
            pen = self.replacement.best(spots)
            leverage, rp_tilt = self.replacement.leverage(pen), tilts[int(pen[2:]) - 1]
            normal = {**normal, "leverage": normal["runs"] * weight * (leverage - 1)}
            rp_war, how = spots[pen], value.Replacement.describe(pen)
            if starting:
                spots["SP"] = sp_war
            spot = self.replacement.best(spots)
            starts = spot == "SP"
            adjustments = self._spot(side, spots, spot)
        else:
            leverage, how, rp_tilt = float(self.model.leverage(rp_index)), None, tilt["rp"]
            rp_war = sum(relieving.values())
            starts = starting and sp_war >= rp_war
        side.components = {"starter": SCALE * sp_war if starting else 0.0, "reliever": SCALE * rp_war}
        ledger = state.ledger
        if starts:
            side.role, state.era = "SP", era["sp"]
            matchups = SCALE * (starting["runs"] - sp_normal["runs"])
            shown = tilt["sp"] > 0 and abs(matchups) >= MATCHUPS_SHOWN
            ledger.add(MODEL, "pitching", SCALE * sp_normal["runs"] + (0.0 if shown else matchups), PITCHING,
                       f"{era['sp']:.2f} ERA", self._pitching_detail(player, fitted, "sp"))
            if shown:
                # his ERA against each hand is the card's splits row
                weak, _ = _hands(self.ratings.throws(player), split["sp"])
                ledger.add(MODEL, "matchups", matchups, PITCHING, f"+{tilt['sp']:.0%} vs {weak}",
                           "lineups stack his weak side")
            ledger.add(MODEL, "innings", SCALE * starting["innings"], PITCHING,
                       f"{innings:.0f} IP", f"stamina {stamina}")
            war = sp_war
        else:
            side.role, state.era = "RP", era["rp"]
            matchups = SCALE * (rp_war - normal["runs"] - normal["leverage"] - normal["innings"])
            shown = rp_tilt > 0 and abs(matchups) >= MATCHUPS_SHOWN
            ledger.add(MODEL, "pitching", SCALE * normal["runs"] + (0.0 if shown else matchups), PITCHING,
                       f"{era['rp']:.2f} ERA", self._pitching_detail(player, fitted, "rp"))
            ledger.add(MODEL, "leverage", SCALE * normal["leverage"], PITCHING, f"LI {leverage:.2f}", how)
            if shown:
                _, strong = _hands(self.ratings.throws(player), split["rp"])
                ledger.add(MODEL, "matchups", matchups, PITCHING, f"+{rp_tilt:.0%} vs {strong}",
                           "how you'd use him")
            ledger.add(MODEL, "innings", SCALE * relieving["innings"], PITCHING,
                       f"{self.model.workloads['reliever_ip']:.0f} IP", "relief workload")
            war = rp_war
        write_runtime_component(player.id, "pitching.value.starter_war", sp_war if starting else 0.0)
        write_runtime_component(player.id, "pitching.value.reliever_war", rp_war)
        # each role's ERA, and the valued role's against each batting hand (the card)
        state.sp_era, state.rp_era = (era["sp"] if starting else None), era["rp"]
        state.innings = innings if side.role == "SP" else self.model.workloads["reliever_ip"]
        if starting:
            write_runtime_component(player.id, "pitching.value.starter_era", era["sp"])
        write_runtime_component(player.id, "pitching.value.reliever_era", era["rp"])
        role = side.role.lower()
        moved = era[f"{role} matched"] - era[role]
        gap = abs(moved) / tilt[role] if tilt[role] > 0 else None
        eras = self._side_eras(player, fitted, role, era[role], gap, split[role])
        if eras:
            for hand, e in eras.items():
                write_runtime_component(player.id, f"pitching.value.era_v{hand[0].lower()}", e)
            write_runtime_component(player.id, "pitching.value.splits_expected", estimated)
        control = self.ratings.control(player)
        floor = value.control_floor(control)
        floors = [("Control floor", floor, f"Control {control}")] if floor < 1 else []
        self._modifiers(state, side, PITCHING, war)
        if self.odds:
            return self._odds(state, side, PITCHING, war, side.role, floors)
        return self._modified(state, side, war, PITCHING, self._development(state, war), floors, adjustments)

    def _side_eras(self, player, fitted, role, role_era, gap, split):
        """{"LHB" | "RHB": his ERA in `role` against them}: his splits', or,
        from an estimated split (`gap` ERA between his sides), the two that
        blend to his ERA at the share of lefties his hand faces. None without
        either."""
        if fitted.side_era:
            return {f"{s[1]}HB": float(self.model.calibrated("era", e, role)) for s, e in fitted.side_era[role].items()}
        throws = self.ratings.throws(player)
        if not throws or not gap:
            return None
        weak, strong = _hands(throws, split)
        lefties = float(self.pitching_model.lhb_share(role, [throws])[0])
        weak_share = lefties if weak == "LHB" else 1 - lefties
        eras = {strong: role_era - weak_share * gap}
        eras[weak] = eras[strong] + gap
        return eras

    @staticmethod
    def _pitching_detail(player, fitted, role) -> str:
        """His Stuff when he's valued in a role he isn't listed in (the role
        shift moved it); None otherwise."""
        listed = "sp" if player.position == "SP" else "rp"
        if role == listed:
            return None
        return f"Stuff {fitted.sp_stuff if role == 'sp' else fitted.rp_stuff:.0f} as {role.upper()}"

    # -- both ------------------------------------------------------------------

    @staticmethod
    def _unrated(state, side, side_name, components, what) -> float:
        """A side no fitted model can read: valued at replacement."""
        state.ledger.add(MODEL, f"no {what} ratings", 0.0, side_name, note="valued at replacement")
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

    def _odds(self, state, side, side_name, war, group, floors=(), switch=None) -> float:
        """The draft odds for a side: his ceiling (the WAR after its floors),
        then the lines that take it to what he's expected to realize, then the
        judgment the odds keep - the profile's remaining modifiers, a
        pitcher's velocity upside and the hitter-pitcher balance. Never below
        replacement: the odds order the bottom of the board."""
        player, ledger = state.player, state.ledger
        ceiling = SCALE * war
        for name, factor, note in floors:
            ceiling = ledger.scale(MODEL, name, ceiling, factor, side_name, note)
        ceiling /= SCALE
        readiness = state.companions["readiness"].model
        pitches = self.ratings.pitch_count(player)
        growth = self.odds.growth_columns(player, ceiling, readiness, group, pitches)
        lines, expected = self.odds.reaching(player, ceiling, readiness, group, growth, switch)
        points = SCALE * ceiling
        for kind, label, amount, stat, note in lines:
            if kind == "add":
                ledger.add(DEVELOPMENT, label, SCALE * amount, side_name, stat, note)
                points += SCALE * amount
            else:
                points = ledger.scale(DEVELOPMENT, label, points, amount, side_name, note)
        for name, factor in side.modifiers:
            points = ledger.scale(MODIFIERS, name, points, factor, side_name, _modifier_note(name, player))
        if side_name == PITCHING:
            knuckleball = "knuckleball" in player.get_pitches()
            fast = draft_odds.velocity_factor(player.velocity, knuckleball)
            if fast != 1:
                points = ledger.scale(MODIFIERS, "velocity", points, fast, side_name, f"{player.velocity} mph")
            points = ledger.scale(MODIFIERS, "pitcher balance", points, self.odds.balance, side_name)
        modified = points / SCALE
        side.score = points
        side.odds = {"ceiling": ceiling, "group": group, "expected": expected / (switch[1] if switch else 1.0),
                     "scale": modified / expected * (switch[1] if switch else 1.0) if expected > 0 else 0.0,
                     "columns": self.odds.mean_columns(player, ceiling, readiness, group), "growth": growth}
        write_runtime_component(player.id, f"{side_name}.value.war", modified)
        return modified

    def _development(self, state, war) -> list:
        return development.factors(state.player, war) if self.develops else []

    @staticmethod
    def _modified(state, side, war, side_name, developing=(), floors=(), adjustments=()) -> float:
        """The side's WAR after its `adjustments` (label, WAR, stat, note: the
        league's replacement), then its floors, its modifiers and then its
        development factors, which scale the part above replacement. Below
        replacement only his personality counts (decided 2026-11-08), in
        reverse: the development factors and BELOW_REPLACEMENT modifiers
        divide the deficit, so good makeup shrinks it. Recorded as ledger
        lines and the side's score."""
        for label, delta, stat, note in adjustments:
            state.ledger.add(MODEL, label, SCALE * delta, side_name, stat, note)
            war += delta
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
        # the ramp is set in StatsPlus's WAR, so it reads the other side there;
        # the share is of what's above replacement
        share = value.two_way_share(other + (state.batting if secondary == BATTING else state.pitching).replacement)
        if share > 0 and other > 0:
            bonus = share * other
            role = "pitcher" if secondary == PITCHING else "hitter"
            state.ledger.add(TWO_WAY, "two-way", SCALE * bonus, stat=f"{share:.0%} of {other:.1f} WAR", note=f"as a {role}")
            war += bonus
        state.value = float(value.points(war))
