import string

PLAYER_FIELDS = {
    "position": "POS",
    "id": "ID",
    "name": "Name",
    "age": "Age",
    "org": "ORG",
    "level": "Lev",
    "overall": "OVR",
    "potential": "POT",
    "demand": "DEM",
    "signability": "Sign",
    "throw_hand": "T",
    "bat_hand": "B",
    "injury_prone": "Prone",
    "scouting_accuracy": "SctAcc",
    "adaptibility": "AD",
    "loyalty": "LOY",
    "greed": "FIN",
    "intelligence": "INT",
    "work_ethic": "WE",
    "leadership": "LEA",
    "contact": "CON P",
    "gap": "GAP P",
    "power": "POW P",
    "eye": "EYE P",
    "avoid_k": "K P",
    "contact_ovr": "CON",
    "gap_ovr": "GAP",
    "power_ovr": "POW",
    "eye_ovr": "EYE",
    "avoid_k_ovr": "K's",
    "speed": "SPE",
    "steal": "STE",
    "running_ability": "RUN",
    "c_arm": "C ARM",
    "c_ability": "C ABI",
    "if_range": "IF RNG",
    "if_arm": "IF ARM",
    "if_error": "IF ERR",
    "turn_dp": "TDP",
    "of_range": "OF RNG",
    "of_arm": "OF ARM",
    "of_error": "OF ERR",
    "stuff": "STU P",
    "movement": "MOV P",
    "control": "CONT P",
    "stuff_ovr": "STU",
    "movement_ovr": "MOV",
    "control_ovr": "CONT",
    "stamina": "STM",
    "groundball_type": "G/F",
    "fastball": "FBP",
    "changeup": "CHP",
    "curveball": "CBP",
    "slider": "SLP",
    "sinker": "SIP",
    "splitter": "SPP",
    "cutter": "CTP",
    "forkball": "FOP",
    "circlechange": "CCP",
    "screwball": "SCP",
    "knuckleball": "KNP",
    "knucklecurve": "KCP",
    "fastball_ovr": "FBP",
    "changeup_ovr": "CHP",
    "curveball_ovr": "CBP",
    "slider_ovr": "SLP",
    "sinker_ovr": "SIP",
    "splitter_ovr": "SPP",
    "cutter_ovr": "CTP",
    "forkball_ovr": "FOP",
    "circlechange_ovr": "CCP",
    "screwball_ovr": "SCP",
    "knuckleball_ovr": "KNP",
    "knucklecurve_ovr": "KCP",
}


class GamePlayers:
    def __init__(self, player_dicts):
        self.game_players = [GamePlayer(player_dict) for player_dict in player_dicts]
        self.game_players_by_id = {
            game_player.id: game_player for game_player in self.game_players
        }

    def get_player(self, player_id):
        return self.game_players_by_id[player_id]


class GamePlayer:
    def __init__(self, player_dict):
        self._dict = player_dict
        self.pitch_fields = [
            "fastball",
            "changeup",
            "curveball",
            "slider",
            "sinker",
            "splitter",
            "cutter",
            "forkball",
            "circlechange",
            "screwball",
            "knuckleball",
            "knucklecurve",
        ]
        self.pitch_ovr_fields = [
            "fastball_ovr",
            "changeup_ovr",
            "curveball_ovr",
            "slider_ovr",
            "sinker_ovr",
            "splitter_ovr",
            "cutter_ovr",
            "forkball_ovr",
            "circlechange_ovr",
            "screwball_ovr",
            "knuckleball_ovr",
            "knucklecurve_ovr",
        ]
        for attr, dict_attr in PLAYER_FIELDS.items():
            setattr(self, f"_{attr}", player_dict[dict_attr])

    @property
    def id(self):
        return self._id

    @property
    def position(self):
        return self._position

    @property
    def name(self):
        return string.capwords(self._name)

    @property
    def org(self):
        return self._org

    @property
    def level(self):
        return self._level

    @property
    def overall(self):
        return int(self._overall)

    @property
    def potential(self):
        return int(self._potential)

    @property
    def demand(self):
        return self._demand

    @property
    def signability(self):
        return self._signability

    @property
    def age(self):
        return int(self._age)

    @property
    def throw_hand(self):
        return self._throw_hand

    @property
    def bat_hand(self):
        return self._bat_hand

    @property
    def scouting_accuracy(self):
        return self._scouting_accuracy

    @property
    def injury_prone(self):
        return self._injury_prone

    @property
    def intelligence(self):
        return self._intelligence

    @property
    def work_ethic(self):
        return self._work_ethic

    @property
    def leadership(self):
        return self._leadership

    @property
    def adaptibility(self):
        return self._adaptibility

    @property
    def greed(self):
        return self._greed

    @property
    def loyalty(self):
        return self._loyalty

    @property
    def contact(self):
        return int(self._contact)

    @property
    def gap(self):
        return int(self._gap)

    @property
    def power(self):
        return int(self._power)

    @property
    def eye(self):
        return int(self._eye)

    @property
    def avoid_k(self):
        return int(self._avoid_k)

    @property
    def contact_ovr(self):
        return int(self._contact_ovr)

    @property
    def gap_ovr(self):
        return int(self._gap_ovr)

    @property
    def power_ovr(self):
        return int(self._power_ovr)

    @property
    def eye_ovr(self):
        return int(self._eye_ovr)

    @property
    def avoid_k(self):
        return int(self._avoid_k)

    @property
    def avoid_k_ovr(self):
        return int(self._avoid_k_ovr)

    @property
    def speed(self):
        return int(self._speed)

    @property
    def steal(self):
        return int(self._steal)

    @property
    def running_ability(self):
        return int(self._running_ability)

    @property
    def c_arm(self):
        return int(self._c_arm)

    @property
    def c_ability(self):
        return int(self._c_ability)

    @property
    def if_range(self):
        return int(self._if_range)

    @property
    def if_arm(self):
        return int(self._if_arm)

    @property
    def if_error(self):
        return int(self._if_error)

    @property
    def turn_dp(self):
        return int(self._turn_dp)

    @property
    def of_range(self):
        return int(self._of_range)

    @property
    def of_arm(self):
        return int(self._of_arm)

    @property
    def of_error(self):
        return int(self._of_error)

    @property
    def stuff(self):
        return int(self._stuff)

    @property
    def movement(self):
        return int(self._movement)

    @property
    def control(self):
        return int(self._control)

    @property
    def stuff_ovr(self):
        return int(self._stuff_ovr)

    @property
    def movement_ovr(self):
        return int(self._movement_ovr)

    @property
    def control_ovr(self):
        return int(self._control_ovr)

    @property
    def stamina(self):
        return int(self._stamina)

    @property
    def groundball_type(self):
        return self._groundball_type

    @property
    def fastball(self):
        try:
            return int(self._fastball)
        except ValueError:
            return None

    @property
    def changeup(self):
        try:
            return int(self._changeup)
        except ValueError:
            return None

    @property
    def curveball(self):
        try:
            return int(self._curveball)
        except ValueError:
            return None

    @property
    def slider(self):
        try:
            return int(self._slider)
        except ValueError:
            return None

    @property
    def sinker(self):
        try:
            return int(self._sinker)
        except ValueError:
            return None

    @property
    def splitter(self):
        try:
            return int(self._splitter)
        except ValueError:
            return None

    @property
    def cutter(self):
        try:
            return int(self._cutter)
        except ValueError:
            return None

    @property
    def forkball(self):
        try:
            return int(self._forkball)
        except ValueError:
            return None

    @property
    def circlechange(self):
        try:
            return int(self._circlechange)
        except ValueError:
            return None

    @property
    def screwball(self):
        try:
            return int(self._screwball)
        except ValueError:
            return None

    @property
    def knuckleball(self):
        try:
            return int(self._knuckleball)
        except ValueError:
            return None

    @property
    def knucklecurve(self):
        try:
            return int(self._knucklecurve)
        except ValueError:
            return None

    @property
    def fastball_ovr(self):
        try:
            return int(self._fastball_ovr)
        except ValueError:
            return None

    @property
    def changeup_ovr(self):
        try:
            return int(self._changeup_ovr)
        except ValueError:
            return None

    @property
    def curveball_ovr(self):
        try:
            return int(self._curveball_ovr)
        except ValueError:
            return None

    @property
    def slider_ovr(self):
        try:
            return int(self._slider_ovr)
        except ValueError:
            return None

    @property
    def sinker_ovr(self):
        try:
            return int(self._sinker_ovr)
        except ValueError:
            return None

    @property
    def splitter_ovr(self):
        try:
            return int(self._splitter_ovr)
        except ValueError:
            return None

    @property
    def cutter_ovr(self):
        try:
            return int(self._cutter_ovr)
        except ValueError:
            return None

    @property
    def forkball_ovr(self):
        try:
            return int(self._forkball_ovr)
        except ValueError:
            return None

    @property
    def circlechange_ovr(self):
        try:
            return int(self._circlechange_ovr)
        except ValueError:
            return None

    @property
    def screwball_ovr(self):
        try:
            return int(self._screwball_ovr)
        except ValueError:
            return None

    @property
    def knuckleball_ovr(self):
        try:
            return int(self._knuckleball_ovr)
        except ValueError:
            return None

    @property
    def knucklecurve_ovr(self):
        try:
            return int(self._knucklecurve_ovr)
        except ValueError:
            return None

    def get_pitches(self):
        pitches = []
        for field in self.pitch_fields:
            pitch_attr = getattr(self, field)
            if pitch_attr is not None:
                pitches.append(field)
        return sorted(pitches, key=lambda p: getattr(self, p), reverse=True)

    def get_ovr_pitches(self):
        pitches = []
        for field in self.pitch_ovr_fields:
            pitch_attr = getattr(self, field)
            if pitch_attr is not None:
                pitches.append(field)
        return sorted(pitches, key=lambda p: getattr(self, p), reverse=True)
