"""The signal inventory: which parts of a profile's pipeline read each rating.

A rating read in several places on the side a player is judged on counts
several times - Avoid K in the batting model and again inside Contact, say.
That's what this report surfaces. It's a report, never a failure.

Reads are measured, not declared: while a profile ranks some players, every
rating read off a `GamePlayer` (or a field copied onto its result, like the
demand) is attributed to the model, scorer or modifier whose code read it. So
the inventory can't drift from the code, but a branch the players never reach
isn't seen - run it on a whole pool.
"""
import contextlib
import io
import os
import sys
from dataclasses import dataclass, field

from models.game_players import PLAYER_FIELDS, GamePlayer
from models.scored_player import ScoredPlayer
from ranking.profiles import modifier_name

_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
_DIRS = {
    os.path.join(_ROOT, name) + os.sep: name
    for name in ("attribute_models", "modifiers", "scoring")
}

# identity and bookkeeping, not signals
_IGNORED = {"ID", "Name", "POS", "ORG", "Lev"}
_PITCH_GRADES = {False: "pitch grades (P)", True: "pitch grades"}

# what a result carries over from its player, read by the pool stages
_RESULT_LOOKUP = {"demand": "DEM", "age": "Age", "in_game_overall": "OVR", "in_game_potential": "POT"}

# OOTP composites (see plans/ranking-architecture-plan.md): reading one of these
# and one of its parts on the same side counts the part twice.
COMPOSITES = {
    "CON": ("BABIP", "K's"),
    "CON P": ("HT P", "K P"),
    "MOV": ("PBABIP", "HRA"),
    "MOV P": ("PBABIP P", "HRA P"),
}
# summaries of every rating
SUMMARIES = {"OVR", "POT"}

# Readers are named by what they score. Attribute models that are alternatives
# for one player (only the best position / role counts) are one reader.
_MODELS = {
    "BattingAttributeModel": ("batting model", "batting"),
    "RunningAttributeModel": ("running model", "batting"),
    "StartingPitcherAttributeModel": ("pitching models", "pitching"),
    "ReliefPitcherAttributeModel": ("pitching models", "pitching"),
}
_FIELDING = ("fielding models", "batting")
_SCORERS = {
    "position_player_scorer": ("batting scorer", "batting"),
    "pitcher_scorer": ("pitcher scorer (role adjustments)", "pitching"),
}
# the fitted layers read through ranking/ratings.py: RatingsView method -> reader
_RATINGS_FILE = os.path.join(_ROOT, "ranking", "ratings.py")
_VIEWS = {"hitting": ("batting talent", "batting")}
_READER_SIDES = {
    name: side for name, side in (*_MODELS.values(), _FIELDING, *_SCORERS.values(), *_VIEWS.values())
}
# functions that read a rating only to copy it onto a what-if player (the
# SP / RP Stuff shift), which are then read where they're scored
_PASS_THROUGH = {"__sp_estimate_player", "__rp_estimate_player"}
# potential ratings - the ones with a current counterpart
POTENTIAL_RATINGS = {
    column for attr, column in PLAYER_FIELDS.items()
    if f"{attr}_ovr" in PLAYER_FIELDS and attr not in GamePlayer({}).pitch_fields
} | {_PITCH_GRADES[False]}


def _player_lookup():
    """GamePlayer attribute -> the rating it reads, under its public and `_`
    backing names (derived properties read the backing ones). The pitch grades
    are one rating each for potential and current."""
    probe = GamePlayer({})
    pitches = {a: _PITCH_GRADES[False] for a in probe.pitch_fields}
    pitches.update({a: _PITCH_GRADES[True] for a in probe.pitch_ovr_fields})
    lookup = {"_pitches": _PITCH_GRADES[False], "_ovr_pitches": _PITCH_GRADES[True]}
    for attr, column in PLAYER_FIELDS.items():
        if column not in _IGNORED:
            lookup[attr] = lookup[f"_{attr}"] = pitches.get(attr, column)
    return lookup


def _owner(frame, directory):
    """The class whose method `frame` is in, walking out through comprehensions
    and module-level helpers in the same directory."""
    while frame is not None and frame.f_code.co_filename.startswith(directory):
        local = frame.f_locals
        owner = local.get("self", local.get("cls"))
        if owner is not None:
            return owner if isinstance(owner, type) else type(owner)
        frame = frame.f_back
    return None


def _reader(frame):
    """The model / scorer / modifier whose code `frame` (or a caller) is in."""
    while frame is not None:
        filename = frame.f_code.co_filename
        if filename == _RATINGS_FILE:
            view = frame
            while view is not None and view.f_code.co_name not in _VIEWS:
                view = view.f_back
            return _VIEWS[view.f_code.co_name][0] if view else None
        for directory, kind in _DIRS.items():
            if not filename.startswith(directory):
                continue
            if frame.f_code.co_name in _PASS_THROUGH:
                return None
            if kind == "scoring":
                stem = os.path.splitext(os.path.basename(filename))[0]
                return _SCORERS.get(stem, (stem, None))[0]
            owner = _owner(frame, directory)
            name = owner.__name__ if owner else os.path.basename(filename)
            if kind == "attribute_models":
                return _MODELS.get(name, _FIELDING)[0]
            return name
        frame = frame.f_back
    return None


@dataclass
class Inventory:
    profile: object
    players: int
    # reader -> ratings it read
    reads: dict = field(default_factory=dict)

    def sides(self, reader) -> set:
        """The side(s) a reader feeds: models and scorers by what they score, a
        modifier by the profile list it's on."""
        if reader in _READER_SIDES:
            return {_READER_SIDES[reader]}
        p = self.profile

        def on(mods):
            return reader in {modifier_name(m) for m in mods}

        if on(p.shared_modifiers) or on(p.demand_modifiers):
            return {"batting", "pitching"}
        sides = {s for s, mods in (("batting", p.batting_modifiers), ("pitching", p.pitching_modifiers)) if on(mods)}
        return sides or {"batting", "pitching"}

    def by_rating(self, side) -> dict:
        """rating -> the readers on `side` that read it."""
        out = {}
        for reader, ratings in self.reads.items():
            if side in self.sides(reader):
                for rating in ratings:
                    out.setdefault(rating, []).append(reader)
        return {r: sorted(readers) for r, readers in out.items()}

    def flags(self, side) -> dict:
        """rating -> why it may count more than once on `side`."""
        by = self.by_rating(side)
        out = {}
        for rating, readers in by.items():
            notes = []
            if len(readers) > 1:
                notes.append(f"{len(readers)} readers")
            if rating in COMPOSITES:
                parts = [p for p in COMPOSITES[rating] if p in by]
                if parts:
                    notes.append(f"= {' + '.join(COMPOSITES[rating])}, and {', '.join(parts)} is read too")
            notes += [f"also inside {c}, which is read too" for c, parts in COMPOSITES.items() if rating in parts and c in by]
            if rating in SUMMARIES:
                notes.append("summarises every rating")
            if rating in POTENTIAL_RATINGS and self.profile.ratings == "overall":
                notes.append("a potential rating in a current-ratings profile")
            if notes:
                out[rating] = notes
        return out


@contextlib.contextmanager
def _tracing(reads):
    """Record, while active, every rating read off a GamePlayer / ScoredPlayer
    into `reads[reader]`."""
    get = object.__getattribute__

    def traced(lookup):
        def __getattribute__(self, name):
            rating = lookup.get(name)
            if rating is not None:
                reader = _reader(sys._getframe(1))
                if reader is not None:
                    reads.setdefault(reader, set()).add(rating)
            return get(self, name)

        return __getattribute__

    patched = ((GamePlayer, _player_lookup()), (ScoredPlayer, _RESULT_LOOKUP))
    for cls, lookup in patched:
        cls.__getattribute__ = traced(lookup)
    try:
        yield
    finally:
        for cls, _ in patched:
            del cls.__getattribute__


def inventory(ranker, players) -> Inventory:
    """Rank `players` (GamePlayers) with `ranker`, recording what each part read."""
    players = list(players)
    inv = Inventory(ranker.profile, len(players))
    with _tracing(inv.reads), contextlib.redirect_stdout(io.StringIO()):
        ranker.rank(players, batch_size=max(len(players), 1))
    return inv
