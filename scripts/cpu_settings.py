"""CPU level settings (Nick, 2026-09-28: "add all these to the patcher", knowing the CPU is still being tuned): the
values a player may set for the level 5 and level 6 CPU, one list (SETTINGS) that the build, the patcher's CPU levels
tab, the checks and the settings page all read. The patcher option "cpu-settings" holds only what a player changed:

    {key: {"5": value, "6": value}}   a per-level setting; either level may be left out (it keeps its default)
    {key: value}                  a level 5 only one (levels (5,)), or (an older file) one value for both levels of
                                  a setting the two shared until 2026-09-29 (split=True)

A value left out keeps today's default, which lives where it always did (cpu_perfect's tables, the cpu_* modules'
constants): retuning a default there changes the patcher and the page with no edit here, and a player who never
touched that setting gets the new default. Two kinds of setting:

  TABLE (Table): bytes the level 5 manager hook swaps in per match (cpu_perfect.GROUPS, level 6 over them from
      cpu_perfect.LEVEL6; level5.apply). Level 5 and level 6 each take their own value. Defaults are decoded from
      those tables, so they can't drift. swaps() turns the tables plus the edits into level5.apply's two lists.
  CONSTANT (Const): a cpu_* module constant read while its code / data is generated. configure() sets it for one build
      and gives back a restore (charbuild.build calls it around _build, as creators.swings.configure). Per-level only
      where the module already keeps a (level 5, level 6) pair (cpu_pitching.PARAMS); cpu_items' error roll is level 5
      only (level 6 has none). The rest (split=True; Nick, 2026-09-29: "EVERYTHING in level 5 should be changeable")
      were one value for both levels: the constant stays level 6's and level 5's goes in the module's AT5, and where
      the two differ the generated code picks this match's by the level flag (level5.pair / pick / pick_addr), so a
      build with no level 5 change is byte for byte today's.

  SWITCH (Switch): a CPU switch (a build feature) on or off per level (Nick: "per level switches, but make it easy
      to change both or one or the other"). Its value is {"5": bool, "6": bool}, both on when left out. A code switch's
      gates test FLAG & its mask (level5.gate, level5.LEVELS_ON; both levels = today's words); a table group
      (cpu-perfect-*) swaps its bytes in only at the levels it's on. Off at both levels: the patcher leaves the
      feature out of the build instead.

OURS (Nick, 2026-09-29: "which fields are our custom ones and which are originally in the game"): a Table is a value
the game's own CPU already rolls (its level 4 row; level 5 plays level 4 with these bytes swapped in), so it's the
game's; a Const is a constant of our own injected code (cpu_pitching, cpu_stars, cpu_rundown, cpu_items,
cpu_item_defense), so it's ours; a Switch is ours when it gates our code (gated), the game's when it only swaps a
cpu_perfect table group. fields()' "ours" carries it; the tab marks those "(ours)".

Every setting names the build feature it needs (a setting whose feature is off does nothing; check() says so).
Test: scripts/test_cpu_settings.py (every setting's site / constant exists and its default matches the tables and
modules; an edit changes the built code or the swapped bytes; no edits = today's bytes exactly; check / save / load).
"""
import json
import math
import struct
from pathlib import Path

KIND, EXTENSION, FORMAT, VERSION = "cpu", ".slgcpu", "sluggers-cpu", 1
FEATURE, OPTION = "cpu-settings", "cpu-settings"
LEVELS = (4, 5, 6)
TABLE_LEVELS = (4, 5, 6)


def _hz50(v):
    """A 60 Hz frame count's 50 Hz row, as the game's own rows (10 -> 8, 20 -> 16, 12 -> 10, 6 -> 5, 2 -> 1)."""
    return int(v * 5 // 6)


class Table:
    """A byte site (or several) in cpu_perfect's per-match tables. enc: "u8" (each site a byte), "u16" (each a
    big-endian u16), "f32", "pair" (s8 -v, +v: a +-frames window), "frames" / "frames16" (u8 / u16: sites (60 Hz,
    50 Hz), the 50 Hz one _hz50), "fastball" (the 5 charge weights, the value the perfect-charge %)."""
    kind, ours = "table", False                    # the game's own CPU value (see OURS)

    def __init__(self, key, group, section, label, unit, lo, hi, enc, sites, stock, tip, step=1, integer=True):
        self.key, self.group, self.section, self.label, self.unit = key, group, section, label, unit
        self.lo, self.hi, self.enc, self.sites, self.stock, self.tip = lo, hi, enc, tuple(sites), stock, tip
        self.step, self.integer, self.levels, self.shared, self.feature = step, integer, TABLE_LEVELS, False, group

    def size(self):
        return {"u8": 1, "frames": 1, "u16": 2, "frames16": 2, "f32": 4, "pair": 2, "fastball": 5}[self.enc]

    def encode(self, v, stock_bytes):
        """{address: bytes} for value v (stock_bytes: {address: the game's bytes}, for the fastball row)."""
        e, out = self.enc, {}
        if e == "u8":
            return {a: bytes([int(v)]) for a in self.sites}
        if e == "u16":
            return {a: struct.pack(">H", int(v)) for a in self.sites}
        if e == "f32":
            return {a: struct.pack(">f", float(v)) for a in self.sites}
        if e == "pair":
            return {a: struct.pack(">bb", -int(v), int(v)) for a in self.sites}
        if e in ("frames", "frames16"):
            fmt = ">B" if e == "frames" else ">H"
            a60, a50 = self.sites
            return {a60: struct.pack(fmt, int(v)), a50: struct.pack(fmt, _hz50(int(v)))}
        if e == "fastball":                        # the other four keep the game's proportions, summing to 100 - v
            a = self.sites[0]
            base = list(stock_bytes[a][:4])
            rest, total = 100 - int(v), sum(base)
            w = [rest * b // total for b in base]
            w[w.index(max(w))] += rest - sum(w)
            return {a: bytes(w + [int(v)])}
        raise ValueError(e)

    def decode(self, get):
        """The value in the bytes get(address, n) (the first site; the others follow it)."""
        a, e = self.sites[0], self.enc
        if e in ("u8", "frames"):
            return get(a, 1)[0]
        if e in ("u16", "frames16"):
            return struct.unpack(">H", get(a, 2))[0]
        if e == "f32":
            return round(struct.unpack(">f", get(a, 4))[0], 4)
        if e == "pair":
            return struct.unpack(">bb", get(a, 2))[1]
        if e == "fastball":
            w = get(a, 5)
            return round(100 * w[4] / sum(w))
        raise ValueError(e)


class Const:
    """A cpu_* module constant. get(module, level) reads today's value; put(module, value by level) sets it for one
    build; saves: the module attributes put() touches (restored after the build). levels: (5, 6) with a value each,
    (5,) level 5 only, or shared (one value, both levels)."""
    kind, ours = "constant", True                  # our own CPU code's constant (see OURS)

    def __init__(self, key, feature, module, section, label, unit, lo, hi, tip, get, put, saves, levels=LEVELS,
                 shared=False, step=1, integer=True, boolean=False, split=False):
        self.key, self.feature, self.module, self.section, self.label, self.unit = key, feature, module, section, label, unit
        self.lo, self.hi, self.tip, self.get, self.put, self.saves = lo, hi, tip, get, put, tuple(saves)
        self.levels, self.shared, self.step, self.integer, self.boolean = levels, shared, step, integer, boolean
        self.split = split                         # one value both levels shared until 2026-09-29: a plain value
                                                   # (an older profile / file) still means both levels
        self.stock = None                          # no stock level 4 value (our own CPU code)


# ---- constant setters

def _param(name):
    """cpu_pitching.PARAMS[name]: level 4 / 5 / 6 values."""
    def get(m, lvl):
        vals = m.PARAMS[name]
        return vals[{4:0, 5:1, 6:2}[lvl]]

    def put(m, by):
        vals = list(m.PARAMS[name])
        for lvl, value in by.items():
            vals[{4:0, 5:1, 6:2}[lvl]] = value
        m.PARAMS = dict(m.PARAMS, **{name: tuple(vals)})
    return get, put, ("PARAMS",)


def _split(name, conv=None, consts=None):
    """A formerly-shared custom constant, now independently editable at levels 4, 5 and 6.
    Level 6 stays in the original module constant; AT5 and AT4 carry the lower-level overrides used by level5.pair3.
    """
    def get(m, lvl):
        if lvl == 4:
            return getattr(m, "AT4", {}).get(name, getattr(m, "AT5", {}).get(name, getattr(m, name)))
        if lvl == 5:
            return getattr(m, "AT5", {}).get(name, getattr(m, name))
        return getattr(m, name)

    def put(m, by):
        base = getattr(m, name)
        if 4 in by:
            m.AT4 = dict(getattr(m, "AT4", {}), **{name: conv(by[4]) if conv else by[4]})
        if 5 in by:
            m.AT5 = dict(getattr(m, "AT5", {}), **{name: conv(by[5]) if conv else by[5]})
        if 6 in by:
            v = by[6]
            setattr(m, name, conv(v) if conv else v)
            if consts:
                fix = dict((n, f(v)) for n, f in consts)
                m.CONSTS = [(n, fix.get(n, x)) for n, x in m.CONSTS]
    return get, put, (name, "AT4", "AT5") + (("CONSTS",) if consts else ())


def _pct_levels(name):
    """A module level 4 / 5 / 6 tuple of fractions, shown as percentages."""
    def get(m, lvl):
        return round(getattr(m, name)[{4:0, 5:1, 6:2}[lvl]] * 100)

    def put(m, by):
        vals = [x * 100 for x in getattr(m, name)]
        for lvl, value in by.items():
            vals[{4:0, 5:1, 6:2}[lvl]] = value
        setattr(m, name, tuple(v / 100 for v in vals))
    return get, put, (name,)


def _l5(name):
    """A custom item constant used by levels 4 and 5 (level 6 intentionally has none)."""
    def get(m, lvl):
        if lvl == 4:
            return getattr(m, "AT4", {}).get(name, getattr(m, name))
        return getattr(m, name)

    def put(m, by):
        if 4 in by:
            m.AT4 = dict(getattr(m, "AT4", {}), **{name: by[4]})
        if 5 in by:
            setattr(m, name, by[5])
    return get, put, (name, "AT4")


def _speed():
    """cpu_items cursor speed, independently editable at levels 4/5/6."""
    def get(m, lvl):
        if lvl == 4:
            return getattr(m, "AT4", {}).get("SPEED6", getattr(m, "AT5", {}).get("SPEED6", m.SPEED6))[0]
        if lvl == 5:
            return getattr(m, "AT5", {}).get("SPEED6", m.SPEED6)[0]
        return m.SPEED6[0]

    def put(m, by):
        for lvl, v in by.items():
            pair = (float(v), round(float(v) * 1.2, 4))
            if lvl == 6:
                m.SPEED6 = pair
            elif lvl == 5:
                m.AT5 = dict(getattr(m, "AT5", {}), SPEED6=pair)
            else:
                m.AT4 = dict(getattr(m, "AT4", {}), SPEED6=pair)
    return get, put, ("SPEED6", "AT4", "AT5")


CAPS3 = ("CAP3", "CAP3_1", "CAP3_2")


def _never_walk():
    def get(m, lvl):
        i = {4:0, 5:1, 6:2}[lvl]
        return int(all(m.PARAMS[c][i] == 0 for c in CAPS3))

    def put(m, by):
        p = dict(m.PARAMS)
        for lvl, on in by.items():
            if on:
                i = {4:0, 5:1, 6:2}[lvl]
                for c in CAPS3:
                    vals = list(p[c]); vals[i] = 0; p[c] = tuple(vals)
        m.PARAMS = p
    return get, put, ("PARAMS",)


# a setting that, while on at a level, holds others at a value there (the tab shows them greyed at it)
LOCKS = {"never_walk": (("cap3_0", "cap3_1", "cap3_2"), 0)}
# settings taken out (a profile / file that still has one: dropped with a note, not refused)
RETIRED = {"force3": "3 balls: throw that rate exactly (replaced by Never walk the batter)"}


def _aim():
    """Item aim error for levels 4 and 5; level 4 is stored in AT4 until code generation."""
    def get(m, lvl):
        if lvl == 4:
            return getattr(m, "AT4", {}).get("L5_K", m.L5_K) * m.L5_STEP
        return round(m.L5_K * m.L5_STEP, 3)

    def put(m, by):
        if 4 in by:
            m.AT4 = dict(getattr(m, "AT4", {}), L5_K=int(round(by[4] / m.L5_STEP)))
        if 5 in by:
            m.L5_K = int(round(by[5] / m.L5_STEP))
    return get, put, ("L5_K", "AT4")


class Switch:
    """A CPU switch per level: key = its build feature. gated: its code tests level5.gate (else a cpu_perfect group)."""
    kind, lo, hi, step, integer, boolean, shared, unit, section = "switch", 0, 1, 1, True, True, False, "", "Switches"
    levels, stock = LEVELS, None

    def __init__(self, feature, label, tip, gated=True):
        self.key = self.feature = feature
        self.label, self.gated, self.tip = label, gated, tip
        self.ours = gated                          # our code (a gate) vs the game's tables (a cpu_perfect group)


# (Nick, 2026-09-29: "most of these don't make any sense. 'CPU Batting' is nothing": each named for what it does in a
# game, one line under it; the same words in both patchers and features_text.json)
SWITCHES = [Switch("cpu-perfect-batting", "Batters read your pitches",
                   "Batters read the pitch type, track the ball and lay off balls (the Batting settings).", gated=False),
            Switch("cpu-perfect-pitching", "Pitchers charge, curve and move the ball",
                   "Perfect-charge fastballs, curves that break late, rarely the same spot twice (the Pitching "
                   "settings).", gated=False),
            Switch("cpu-perfect-fielding", "Fielders dive, jump and react",
                   "Fielders go for dives and jump catches, clear obstacles and react to teammates (the Fielding "
                   "settings).", gated=False),
            Switch("cpu-perfect-running", "Runners tap and press fast",
                   "Runners land their sprint taps and press quickly in close plays (the Running settings).",
                   gated=False),
            Switch("cpu-pitching", "Pitchers learn each batter",
                   "Pitchers work the edges of the zone and learn during the game what gets each batter out."),
            Switch("cpu-charge-timing", "Batters swing fully charged",
                   "Batters start charging at once and are at full charge when they swing."),
            Switch("cpu-batter-track", "Batters see where the pitch really crosses",
                   "Batters judge ball or strike where the pitch crosses the plate, so breaking balls don't fool "
                   "them."),
            Switch("cpu-no-bunts", "Never bunts", "The CPU never bunts."),
            Switch("cpu-cursed-ball", "Charged pitches weaken your hits",
                   "The CPU's charged pitches are cursed balls, like yours: they cut the batter's hit power."),
            Switch("cpu-star-swings", "Star swings by hitter strength",
                   "Weak hitters always star-swing with 2 or more stars; strong hitters rarely or never."),
            Switch("cpu-no-star-pitches", "Never throws star pitches", "The CPU pitcher never throws a star pitch."),
            Switch("cpu-rundown", "Smart rundown throws",
                   "In a rundown it throws ahead at once and times throws behind the runner to get the out."),
            Switch("cpu-items", "Aims batting items at fielders",
                   "Uses its batting item, aimed and timed to hit the fielder about to get the ball."),
            Switch("cpu-item-defense", "Fielders handle items",
                   "Fielders jump POWs, pass when a teammate is near, run around items and ignore Boo."),
            Switch("cpu-subs", "Brings in its best relief pitchers",
                   "When it changes pitchers it picks from its best, then moves fielders for better chemistry.")]


def mask(edits, feature):
    """Levels a CPU switch plays at: bit 4 = level 4, bit 1 = level 5, bit 2 = level 6.
    Custom CPU systems stay off on stock level 4 unless the player explicitly enables them; 5/6 keep their old defaults.
    Game-table switches also use bit 4 to opt level 4 into the tuned table before any row-specific level-4 edits.
    """
    v = (edits or {}).get(feature) or {}
    return (4 if v.get("4", False) else 0) | (1 if v.get("5", True) else 0) | (2 if v.get("6", True) else 0)


BAT, PITCH, FIELD, RUN = "cpu-perfect-batting", "cpu-perfect-pitching", "cpu-perfect-fielding", "cpu-perfect-running"
CLASSES = (("Balance", 0), ("Power", 1), ("Speed", 2), ("Technique", 3))

SETTINGS = [
    # --- batting (cpu_perfect.BATTING)
    Table("pitch_read", BAT, "Batting", "Pitch read", "%", 0, 100, "u8", [0x80797227], 85,
          "Chance the batter reads the pitch type right. A wrong read widens its timing error."),
    Table("star_pitch_read", BAT, "Batting", "Star-pitch read", "%", 0, 100, "u8", [0x80797223], 45,
          "The same, against star pitches."),
    Table("track", BAT, "Batting", "Tracks the ball", "%", 0, 100, "u8", [0x80797233], 85,
          "Chance the bat follows the ball. When it doesn't, the batter swings where it guessed the pitch would go, "
          "usually a whiff. This is the main sweet-spot rate."),
    Table("aim_error", BAT, "Batting", "Aim error", "plate widths", 0, 0.3, "f32", [0x806248F4], 0.05,
          "How far off the bat's aim can be while tracking.", step=0.01, integer=False),
    Table("timing_right", BAT, "Batting", "Timing error, right read", "± frames", 0, 10, "pair", [0x8062490E], 2,
          "Random early or late swing after a right read."),
    Table("timing_wrong", BAT, "Batting", "Timing error, wrong read", "± frames", 0, 20, "pair", [0x80624916], 4,
          "Random early or late swing after a wrong read."),
    Table("takes_first", BAT, "Batting", "Takes the first pitch", "%", 0, 100, "u8", [0x80624984], 40,
          "Chance of taking an at-bat's first pitch, wherever it is."),
    Table("lays_off", BAT, "Batting", "Lays off balls", "%", 0, 100, "u8", [0x80624985], 95,
          "Chance of taking a pitch outside the zone."),
    Table("takes_strike", BAT, "Batting", "Takes a strike (0-1 strikes)", "%", 0, 100, "u8", [0x80624986], 5,
          "Chance of taking a hittable strike with 0 or 1 strikes."),
    Table("takes_strike2", BAT, "Batting", "Takes a strike (2 strikes)", "%", 0, 100, "u8", [0x80624987], 2,
          "Chance of taking a hittable strike with 2 strikes."),
    Table("decoy", BAT, "Batting", "Fooled by the Wario decoy", "%", 0, 100, "u8", [0x80797253], 30,
          "Chance a decoy star pitch makes the batter track the fake ball."),
    *[Table(f"charge_{n.lower()}{k}", BAT, "Batting", f"Charge swings: {n}, {'0-1' if not k else '2'} strikes", "%",
            0, 100, "u8", [0x80797218 + c * 2 + k], s,
            f"Chance a {n} hitter charges the swing with {'0 or 1 strikes' if not k else '2 strikes'}.")
      for n, c in CLASSES for k, s in ((0, (40, 90, 30, 40)[c]), (1, (10, 40, 10, 10)[c]))],
    # --- pitching (cpu_perfect.PITCHING)
    Table("perfect_fastball", PITCH, "Pitching", "Perfect-charge fastball", "%", 0, 100, "fastball", [0x8062475F], 10,
          "Chance a charged fastball gets a perfect charge (the game's own perfect charge). The rest keep the game's "
          "mix of 50 / 70 / 100% charges."),
    Table("repeat_location", PITCH, "Pitching", "Repeats a location", "%", 0, 100, "u8", [0x807971E7], 10,
          "Chance of throwing to the same spot as the last pitch."),
    Table("curve", PITCH, "Pitching", "Curves a plain pitch", "%", 0, 100, "u8", [0x807971EB], 85,
          "Chance a plain pitch curves."),
    Table("late_break", PITCH, "Pitching", "Late break", "%", 0, 100, "u8", [0x807971EF], 70,
          "Chance a curve breaks late."),
    # --- fielding (cpu_perfect.FIELDING)
    Table("dive_try", FIELD, "Fielding", "Tries a dive or jump", "%", 0, 100, "u8",
          [0x80624A14 + 5 * c for c in range(4)], 95,
          "Chance a fielder goes for a dive or jump catch (the game's is 95-99% by class; one value for all)."),
    Table("obstacle", FIELD, "Fielding", "Clears obstacles", "%", 0, 100, "u8",
          [0x80624A28 + 5 * c for c in range(4)], 90, "Chance a fielder jumps over or dodges an obstacle in its path."),
    Table("chem_far", FIELD, "Fielding", "Chemistry reaction (far)", "%", 0, 100, "u8", [0x80624A68], 60,
          "Chance a fielder reacts to a good-chemistry teammate."),
    Table("chem_near", FIELD, "Fielding", "Chemistry reaction (near)", "%", 0, 100, "u8", [0x80624A6D], 80,
          "The same, with the teammate close."),
    Table("reaction_delay", FIELD, "Fielding", "Reaction delay", "frames", 0, 30, "frames", [0x806249E8, 0x806249ED], 10,
          "Extra frames before a fielder starts moving after contact."),
    Table("throw_hold_in", FIELD, "Fielding", "Throw hold (infield)", "frames", 0, 10, "frames", [0x806249F4, 0x806249FE], 2,
          "Frames an infielder holds the ball before throwing."),
    Table("throw_hold_out", FIELD, "Fielding", "Throw hold (outfield)", "frames", 0, 10, "frames", [0x806249F9, 0x80624A03], 2,
          "Frames an outfielder holds the ball before throwing."),
    Table("replan", FIELD, "Fielding", "Recover from a deflection", "frames", 1, 30, "frames", [0x80624A08, 0x80624A0D], 6,
          "Frames before a fielder re-plans its chase after the ball bounces off someone (at least 1: 0 never fires)."),
    Table("hard_throw", FIELD, "Fielding", "Hard throw on close plays", "%", 0, 100, "u8", [0x80797258], 90,
          "Chance of the CPU-only harder throw on a close play."),
    # --- running (cpu_perfect.RUNNING)
    Table("steal_jump", RUN, "Running", "Good steal jump", "%", 0, 100, "u8", [0x8079727F], 30,
          "Chance a stealing runner gets a good jump."),
    Table("sprint_taps", RUN, "Running", "Sprint taps land", "%", 0, 100, "u16", [0x80624A7E, 0x80624AA6], 90,
          "Chance the runner's sprint taps count."),
    Table("press_delay", RUN, "Running", "Close-play press delay", "frames", 0, 40, "frames16", [0x80624B1E, 0x80624B26], 20,
          "Frames before the runner presses in a close-play contest."),
    Table("always_presses", RUN, "Running", "Presses in a close play", "%", 0, 100, "u8",
          [0x80797280 + i for i in range(4)], 99, "Chance the runner presses at all in a close play."),
    # --- the pitch model (cpu_pitching.PARAMS: a value per level)
    Const("model_learning", "cpu-pitching", "cpu_pitching", "Pitch model", "Learning speed", "", 0.0, 0.5,
          "How fast the pitcher learns what beats this batter (0: never learns).", *_param("ALPHA"),
          step=0.01, integer=False),
    Const("model_randomness", "cpu-pitching", "cpu_pitching", "Pitch model", "Randomness: pitch choice", "", 0.05, 5.0,
          "How random its pitch type, location and break are (higher: more random, harder to read).", *_param("T"),
          step=0.05, integer=False),
    Const("model_randomness_bs", "cpu-pitching", "cpu_pitching", "Pitch model", "Randomness: ball or strike", "", 0.05,
          5.0, "How random its ball-or-strike choice is.", *_param("TB"), step=0.05, integer=False),
    Const("model_patience", "cpu-pitching", "cpu_pitching", "Pitch model", "Reads the batter over", "pitches", 1.0,
          50.0, "How many pitches its read of the batter's habits (chasing, taking) is averaged over: higher changes "
          "its mind slower.", *_param("N0"), step=1, integer=False),
    Const("model_floor", "cpu-pitching", "cpu_pitching", "Pitch model", "Balls at 0-1 balls, at least", "%", 0, 50,
          "A ball this often first, before the model picks, with 0 or 1 balls.", *_param("FLOOR")),
    Const("never_walk", "cpu-pitching", "cpu_pitching", "Pitch model", "Never walk the batter", "", 0, 1,
          "On: with 3 balls every pitch is a strike, so it never walks a batter (the 3-ball rates below are held at "
          "0).", *_never_walk(), boolean=True),
    Const("cap3_0", "cpu-pitching", "cpu_pitching", "Pitch model", "Balls at 3-0", "%", 0, 100,
          "With 3 balls and 0 strikes: the ball rate (exact or at most, below).", *_param("CAP3")),
    Const("cap3_1", "cpu-pitching", "cpu_pitching", "Pitch model", "Balls at 3-1", "%", 0, 100,
          "With 3 balls and 1 strike.", *_param("CAP3_1")),
    Const("cap3_2", "cpu-pitching", "cpu_pitching", "Pitch model", "Balls at 3-2", "%", 0, 100,
          "With 3 balls and 2 strikes.", *_param("CAP3_2")),
    Const("far_ball", "cpu-pitching", "cpu_pitching", "Pitch model",
          "How far outside and inside the strike zone it throws", "plate widths",
          0.76, 1.2, "The outside edge of the band its balls land in (the band starts at 0.75, past the sweet spot).",
          *_param("FAR_HI"), step=0.01, integer=False),
    # --- the pitch model's starting beliefs and pitch mix (one value for both levels)
    Const("fastball_speed", "cpu-pitching", "cpu_pitching", "Pitch mix", "Fast pitcher charge pitch threshold", "",
          0, 300, "Pitchers with at least this charge pitch speed start out throwing fastballs more.",
          *_split("FB_CUT"), split=True),
    Const("fastball_top", "cpu-pitching", "cpu_pitching", "Pitch mix", "Fastballs (fast pitchers)", "%", 0, 70,
          "Starting fastball share for those pitchers (at most 70: changeups can take up to 30).", *_split("FB_TOP"), split=True),
    Const("fastball_low", "cpu-pitching", "cpu_pitching", "Pitch mix", "Fastballs (the others)", "%", 0, 70,
          "Starting fastball share for everyone else (at most 70, as above).", *_split("FB_LOW"), split=True),
    Const("plain_curves", "cpu-pitching", "cpu_pitching", "Pitch mix", "Plain curves", "%", 0, 100,
          "Starting share of plain curves; the rest after fastballs and changeups are charged curves it steers onto "
          "the edge.", *_split("PLAIN6"), split=True),
    Const("zone_first", "cpu-pitching", "cpu_pitching", "Pitch mix", "First pitch in the zone", "%", 0, 100,
          "Before it learns: chance an at-bat's first pitch goes in the zone.",
          *_split("P_FIRST", consts=[("P0_FIRST", lambda v: 1 - v / 100)]), split=True),
    Const("zone_after_take", "cpu-pitching", "cpu_pitching", "Pitch mix", "In the zone after a taken strike", "%", 0,
          100, "Before it learns: chance of a strike after the batter took one.",
          *_split("P_TAKEN", consts=[("P0_TAKEN", lambda v: 1 - v / 100)]), split=True),
    Const("zone_after_chase", "cpu-pitching", "cpu_pitching", "Pitch mix", "In the zone after a chase", "%", 0, 100,
          "Before it learns: chance of a strike after the batter chased a ball.",
          *_split("P_CHASE", consts=[("P0_CHASE", lambda v: 1 - v / 100)]), split=True),
    Const("hbp_margin", "cpu-pitching", "cpu_pitching", "Pitch mix", "Hit-by-pitch margin", "m", 0.0, 0.5,
          "How far clear of the batter's hit box a pitch on his side must stay.",
          *_split("MARGIN", consts=[("MARGIN", lambda v: v)]), split=True, step=0.01, integer=False),
    # --- star swings (cpu_stars)
    Const("star_always", "cpu-star-swings", "cpu_stars", "Star swings", "Always star-swing below charge power", "", 0,
          150, "A batter with charge power under this always star-swings when the team has 2 or more stars.",
          *_split("STAR_CP"), split=True),
    Const("star_never", "cpu-star-swings", "cpu_stars", "Star swings", "Never at charge power", "", 0, 150,
          "Charge power at or above this never star-swings.", *_split("CP6_NEVER"), split=True),
    Const("star_rare", "cpu-star-swings", "cpu_stars", "Star swings", "Rarely from charge power", "", 0, 150,
          "From this charge power up to the \"never\" line, only at the rare rate.", *_split("CP6_RARE"), split=True),
    Const("star_rare_pct", "cpu-star-swings", "cpu_stars", "Star swings", "The rare rate", "%", 0, 100,
          "The chance in that range.", *_split("CP6_RARE_PCT"), split=True),
    Const("star_top", "cpu-star-swings", "cpu_stars", "Star swings", "Below that: this minus charge power", "", 0,
          200, "Below the rare line the chance is this number minus charge power (80: charge power 60 gets 20%).",
          *_split("CP6_TOP"), split=True),
    # --- rundowns (cpu_rundown)
    Const("rundown_first", "cpu-rundown", "cpu_rundown", "Rundowns", "Early throw, first throw", "%", 0, 100,
          "Chance the first throw to the base behind a runner heading back goes early.", *_split("FIRST_PCT"), split=True),
    Const("rundown_early", "cpu-rundown", "cpu_rundown", "Rundowns", "Early throw, other throws", "%", 0, 100,
          "Chance a later throw to the base behind a runner heading back goes early.", *_split("EARLY_PCT"), split=True),
    Const("rundown_lead", "cpu-rundown", "cpu_rundown", "Rundowns", "Early throw lead", "frames", 0, 60,
          "How many frames before the deadline (the last moment the throw still gets him out) an early throw goes.",
          *_split("EARLY_LEAD"), split=True),
    Const("rundown_buffer", "cpu-rundown", "cpu_rundown", "Rundowns", "Throw deadline margin", "frames", 0, 60,
          "The ball must reach the base this many frames ahead of the runner's best time.", *_split("TAG_BUFFER"), split=True),
    Const("rundown_rolled", "cpu-rundown", "cpu_rundown", "Rundowns", "Max early throws", "", 0, 50,
          "How many throws of one rundown may go early; after that each goes at the deadline.",
          *_split("MAX_RANDOM"), split=True),
    # --- items (cpu_items, cpu_item_defense)
    Const("items_error_free", "cpu-items", "cpu_items", "Items", "Error-free item at-bats", "%", 0, 100,
          "Share of at-bats with no added item error; the others roll the error below once for the whole at-bat. "
          "Level 6 adds none.", *_l5("L5_PERFECT"), levels=(4, 5)),
    Const("items_timing_error", "cpu-items", "cpu_items", "Items", "Item timing error", "± frames", 0, 30,
          "Frames early or late, in an at-bat with added error.", *_l5("L5_T"), levels=(4, 5)),
    Const("items_aim_error", "cpu-items", "cpu_items", "Items", "Item aim error", "± m", 0.0, 10.0,
          "Metres off target on each axis, in an at-bat with added error (steps of 0.25 m).", *_aim(), levels=(4, 5),
          step=0.25, integer=False),
    Const("items_lead", "cpu-items", "cpu_items", "Items", "Hit before the catch", "frames", 0, 60,
          "The item lands this many frames before the fielder reaches the ball.", *_split("MEET_LEAD"), split=True),
    Const("items_cursor", "cpu-items", "cpu_items", "Items", "Cursor speed", "m / frame", 0.5, 5.0,
          "How fast the item cursor moves (the game's level 4: 0.7).", *_speed(), split=True, step=0.1, integer=False),
    Const("items_runner_pad", "cpu-items", "cpu_items", "Items", "Keep clear of own runners", "m", 0.0, 10.0,
          "How far outside a blast its own runners must stay.", *_split("RUNNER_PAD"), split=True, step=0.25,
          integer=False),
    Const("items_pass", "cpu-item-defense", "cpu_item_defense", "Items", "Pass distance vs items", "m", 0.0, 20.0,
          "A fielder facing an item passes to a teammate within this many metres (the game's pass flight tops out at "
          "20).", *_split("ATK_MATE_D"), split=True, step=0.5, integer=False),
    Const("boo_error_rate", "cpu-item-defense", "cpu_item_defense", "Items", "Boo Error Rate", "%", 0, 100,
          "While a Boo hides the ball, each fielder misjudges where it is by a random (normally distributed) amount; "
          "this share of fielders are off by more than their catch reach and aren't likely to make the play.",
          *_pct_levels("BLUR_P")),
]
SETTINGS = SWITCHES + SETTINGS
BY_KEY = {s.key: s for s in SETTINGS}
assert len(BY_KEY) == len(SETTINGS), "a setting key is used twice"
SECTIONS = list(dict.fromkeys(s.section for s in SETTINGS))


def _module(name):
    import importlib
    return importlib.import_module(name)


# ---- defaults

def _maps():
    """{address: byte} of the level 5 and level 6 swaps as cpu_perfect has them today (every group)."""
    import cpu_perfect
    five, six = {}, {}
    for f, recs in cpu_perfect.GROUPS.items():
        for at, _, new, _ in recs:
            for i, b in enumerate(new):
                five[at + i] = six[at + i] = b
        for at, b6, _ in cpu_perfect.LEVEL6.get(f, ()):
            for i, b in enumerate(b6):
                six[at + i] = b
    return five, six


def default(s, level, stock_get=None):
    """Today's value of setting s at a level. Game-native table settings expose level 4 as the stock game's value;
    level 5/6 come from cpu_perfect's tables. Custom injected constants still belong to levels 5/6 only."""
    if s.kind == "switch":
        return False if level == 4 else True
    if s.kind == "table":
        if level == 4:
            return s.decode(stock_get) if stock_get else s.stock
        m = _maps()[0 if level == 5 else 1]
        if all(a + i in m for a in s.sites[:1] for i in range(s.size())):
            return s.decode(lambda a, n: bytes(m[a + i] for i in range(n)))
        return s.decode(stock_get) if stock_get else s.stock
    return s.get(_module(s.module), level)


def fields():
    """[{key, section, label, unit, min, max, step, integer, boolean, levels, shared, feature, game, ours, default:
    {5: v, 6: v}, tip}] for the patcher tab and the page, in SETTINGS order."""
    out = []
    for s in SETTINGS:
        out.append({"key": s.key, "kind": s.kind, "section": s.section, "label": s.label, "unit": s.unit, "min": s.lo, "max": s.hi,
                    "step": s.step, "integer": s.integer, "boolean": getattr(s, "boolean", False),
                    "levels": list(s.levels), "shared": s.shared, "split": getattr(s, "split", False), "feature": s.feature, "game": s.stock, "ours": s.ours,
                    "default": {lvl: default(s, lvl) for lvl in s.levels}, "tip": s.tip})
    return out


# ---- the option

def by_level(s, v):
    """An option value -> {5: x, 6: y} / {5: x} / {"both": x}; ValueError in plain words."""
    if s.shared:
        if isinstance(v, dict):
            raise ValueError(f"{s.label}: one value for both levels, not {v!r}")
        return {"both": v}
    if not isinstance(v, dict):
        if s.levels in ((5,), (4, 5)):
            return {5: v}
        if getattr(s, "split", False):
            return {5: v, 6: v}
        raise ValueError(f"{s.label}: give it per level, {{\"5\": ..., \"6\": ...}}")
    out = {}
    for k, x in v.items():
        if str(k) not in {str(lvl) for lvl in s.levels}:
            raise ValueError(f"{s.label}: level {k} isn't one of {', '.join(map(str, s.levels))}")
        out[int(k)] = x
    return out


def check(edits, features=None):
    """Plain-words problems with {key: value} (the option), [] if none. features: the build's feature ids (None: any)."""
    found = []
    if not isinstance(edits, dict):
        return ["the CPU settings must be {setting: value}"]
    for key, v in edits.items():
        s = BY_KEY.get(key)
        if s is None:
            found.append(f"{key}: not a CPU setting (renamed or removed?)")
            continue
        try:
            vals = by_level(s, v)
        except ValueError as e:
            found.append(str(e))
            continue
        for lvl, x in vals.items():
            where = "" if lvl == "both" else f" (level {lvl})"
            if getattr(s, "boolean", False) and isinstance(x, bool):
                continue                           # an on / off setting: true / false as well as 1 / 0
            if isinstance(x, bool) or not isinstance(x, (int, float)) or (isinstance(x, float) and math.isnan(x)):
                found.append(f"{s.label}{where}: {x!r} isn't a number")
            elif not s.lo <= x <= s.hi:
                found.append(f"{s.label}{where}: {x} is outside {s.lo}..{s.hi}")
            elif s.integer and x != int(x):
                found.append(f"{s.label}{where}: {x} must be a whole number")
        if features is not None and s.feature not in features:
            found.append(f"{s.label}: needs \"{s.feature}\" on")
    if "star_rare" in edits or "star_never" in edits:
        for lvl in LEVELS:
            rare, never = _value("star_rare", edits, lvl), _value("star_never", edits, lvl)
            if rare is not None and never is not None and rare > never:
                found.append(f"Star swings (level {lvl}): \"Rarely from\" must not be above \"Never at\"")
    return found


def _value(key, edits, lvl):
    s = BY_KEY[key]
    try:
        v = by_level(s, edits[key]).get(lvl) if key in edits else None
    except ValueError:
        return None
    return v if v is not None else default(s, lvl)


def only_levels(edits, levels):
    """(edits, dropped): the option with only what changes the given levels (an edition's "cpu_levels_editable", the
    Characters Beta's [5]); every other level keeps today's values. A per-level value loses its other levels; a shared
    setting (one value that both levels read) is left out, since it would change the other level too; a switch keeps
    its default (on) at the other levels. dropped: plain words for what was left out ("Plain curves (level 6)").
    A key or value this can't read is kept as it is, for check() to name."""
    levels = {int(x) for x in levels}
    out, dropped = {}, []
    for key, v in (edits or {}).items():
        s = BY_KEY.get(key)
        if s is None:
            out[key] = v
            continue
        other = [lvl for lvl in s.levels if lvl not in levels]
        if getattr(s, "split", False) and not isinstance(v, dict):
            v = {str(lvl): v for lvl in s.levels}          # (an older file's one value: both levels)
        if not other:
            out[key] = v
        elif s.kind == "switch":
            if not isinstance(v, dict):
                out[key] = v
                continue
            keep = {k: x for k, x in v.items() if str(k) not in {str(lvl) for lvl in other}}
            dropped += [f"{s.label} (level {k})" for k, x in v.items() if str(k) in {str(lvl) for lvl in other}
                        and not x]
            keep.update({str(lvl): True for lvl in other})
            if not all(keep.values()):
                out[key] = keep
        elif s.shared:
            dropped.append(f"{s.label} (shared with level {', '.join(map(str, other))})")
        elif isinstance(v, dict):
            keep = {k: x for k, x in v.items() if str(k) not in {str(lvl) for lvl in other}}
            dropped += [f"{s.label} (level {k})" for k in v if str(k) in {str(lvl) for lvl in other}]
            if keep:
                out[key] = keep
        elif not set(s.levels) & levels:
            dropped.append(f"{s.label} (level {', '.join(map(str, s.levels))})")
        else:
            out[key] = v
    return out, dropped


# ---- the build

_current = {}


def configure(edits):
    """Set the constants for one build (charbuild.build) and remember the edits for swaps(); returns the restore."""
    global _current
    edits = dict(edits or {})
    problems = check(edits)
    assert not problems, "cpu settings: " + "; ".join(problems)
    import level5
    saved = [(level5, "LEVELS_ON", dict(level5.LEVELS_ON), True)]
    level5.LEVELS_ON = {sw.feature: mask(edits, sw.feature) for sw in SWITCHES if sw.gated and sw.feature in edits}
    for key, v in sorted(edits.items(), key=lambda kv: kv[0] in LOCKS):   # a lock after what it holds
        s = BY_KEY[key]
        if s.kind != "constant":
            continue
        m = _module(s.module)
        for a in s.saves:
            saved.append((m, a, getattr(m, a, None), hasattr(m, a)))
        s.put(m, by_level(s, v))
    prev, _current = _current, edits

    def restore():
        global _current
        for rec in reversed(saved):
            if len(rec) == 3:
                m, a, x = rec; existed = True
            else:
                m, a, x, existed = rec
            if existed:
                setattr(m, a, x)
            elif hasattr(m, a):
                delattr(m, a)
        _current = prev
    return restore


def describe(edits):
    """The build's log lines: each changed value in plain words ("cpu setting: Early throw, first throw 50% (level
    5)"), one line each (an edition's quiet filter drops a line naming what it doesn't show, not all of them)."""
    out = []
    for key, v in (edits or {}).items():
        s = BY_KEY.get(key)
        if s is None:
            continue
        for lvl, x in sorted(by_level(s, v).items(), key=lambda kv: str(kv[0])):
            if s.kind == "switch" or getattr(s, "boolean", False):
                x = "on" if x else "off"
            where = "" if lvl == "both" else f" (level {lvl})"
            unit = "%" if s.unit == "%" else f" {s.unit}" if s.unit else ""
            out.append(f"cpu setting: {s.label} {x}{unit}{where}")
    return out


def swaps(groups, stock_get, edits=None):
    """level5.apply's (swaps, swaps6, reset4) for the cpu_perfect groups that are on. reset4 maps each live run's
    address to the bytes level 4 should restore at match start; unchanged runs use the original game's bytes.
    Level 4 edits are only for the game's native table settings; custom injected settings remain level 5/6."""
    import cpu_perfect
    edits = _current if edits is None else edits
    stock, four, five, six = {}, {}, {}, {}

    def put(m, at, b):
        for i, x in enumerate(b):
            m[at + i] = x
            if at + i not in stock:
                stock[at + i] = stock_get(at + i, 1)[0]

    on = {f: mask(edits, f) for f in groups}
    for f in groups:
        for at, st, new, _ in cpu_perfect.GROUPS[f]:
            # Level 4 starts from the game's own bytes. Level 5/6 use the mod's tuned rows as before.
            for i, b in enumerate(st):
                four[at + i] = b
                stock.setdefault(at + i, stock_get(at + i, 1)[0])
            if on[f] & 4:
                put(four, at, new)
            if on[f] & 1:
                put(five, at, new)
            if on[f] & 2:
                put(six, at, new)
        for at, b6, _ in cpu_perfect.LEVEL6.get(f, ()):
            if on[f] & 2:
                put(six, at, b6)

    for key, v in edits.items():
        s = BY_KEY.get(key)
        if s is None or s.kind != "table" or s.group not in groups:
            continue
        sb = {a: stock_get(a, s.size()) for a in s.sites}
        for lvl, x in by_level(s, v).items():
            bit = {4: 4, 5: 1, 6: 2}[lvl]
            if not mask(edits, s.group) & bit and lvl != 4:
                continue
            target = four if lvl == 4 else five if lvl == 5 else six
            for at, b in s.encode(x, sb).items():
                put(target, at, b)

    # Any byte touched by one level gets explicit values for every level.
    for a in list(four) + list(five) + list(six):
        four.setdefault(a, stock[a])
        five.setdefault(a, stock[a])
        six.setdefault(a, stock[a])
    live = sorted(a for a in set(four) | set(five) | set(six)
                  if four.get(a, stock[a]) != stock[a] or five.get(a, stock[a]) != stock[a] or six.get(a, stock[a]) != stock[a])
    out, out6, reset4, run = [], [], {}, []
    for a in live + [None]:
        if run and (a is None or a != run[-1] + 1):
            st, b4, b5, b6 = (bytes(m[x] for x in run) for m in (stock, four, five, six))
            out.append((run[0], st, b5))
            reset4[run[0]] = b4
            if b6 != b5:
                out6.append((run[0], b5, b6))
            run = []
        if a is not None:
            run.append(a)
    return out, out6, reset4


# ---- files

def save(edits, name, folder):
    path = Path(folder) / (name + EXTENSION)
    path.write_text(json.dumps({"format": FORMAT, "version": VERSION, "name": name, "settings": edits}, indent=2),
                    encoding="utf-8")
    return path


def load(path):
    """(name, edits) from a .slgcpu file; ValueError in plain words. Settings this patcher doesn't know are dropped
    (a newer or older file) and named in the name's place's list: (name, edits, dropped)."""
    try:
        d = json.loads(Path(path).read_text(encoding="utf-8"))
    except (OSError, ValueError):
        raise ValueError(f"{Path(path).name} isn't a CPU settings file")
    if not isinstance(d, dict) or d.get("format") != FORMAT or not isinstance(d.get("settings"), dict):
        raise ValueError(f"{Path(path).name} isn't a CPU settings file")
    edits = {k: v for k, v in d["settings"].items() if k in BY_KEY}
    problems = check(edits)
    if problems:
        raise ValueError(f"{Path(path).name}: " + "; ".join(problems))
    return d.get("name") or Path(path).stem, edits, sorted(set(d["settings"]) - set(edits))
