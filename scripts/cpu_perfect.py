"""Level 4 CPU at 100% (Nick, 2026-09-27): every "chance to succeed" the level 4 CPU rolls is set to always succeed,
and its random errors to zero. Levels 1-3 stay stock. Data writes only (plus two compare immediates for dives), in
four features: "cpu-perfect-batting", "cpu-perfect-pitching", "cpu-perfect-fielding", "cpu-perfect-running".
Tables, functions and indexing: docs/cpu-ai.md. Level 4 is index 3 in the batter / pitcher / runner / close-play
tables (they remap the level through 03 02 01 00 00) and index 0 in the fielder tables (raw level). Fielding and
running tables have a 60 Hz row and a 50 Hz row (the byte at 0x80794B68); both are written.
Left stock on purpose: star-swing chances (a choice, not a success; cpu_stars.py handles star swings),
star-pitch timing windows (skewed on purpose; 0 isn't known to be their best), steal attempts, the wild throw to a
bad-chemistry teammate (shared with humans). Test: scripts/test_cpu_perfect.py.
"""
import struct

F0 = struct.pack(">f", 0.0)

# (address, stock bytes, level 4 bytes, what)
BATTING = [
    (0x80797227, b"\x55", b"\x64", "pitch guess always right (85 -> 100%)"),
    (0x80797223, b"\x2d", b"\x64", "star-pitch guess always right (45 -> 100%)"),
    # Level 5 tracks 79% of pitches (Nick, 2026-09-29: level 5 "still too good at hitting"; 65% first, then 72% to stay
    # above stock level 4's ~66% for an average-contact hitter, then "5 more percentage points" of sweet spots: 79%): an
    # untracked pitch keeps the bat where its mind game (cpu_track.py) guessed. sweet ~ p * S + (1 - p) * g, S the
    # tracked swings' rate (0.86 modelled .. ~0.95 as played), g the guess alone (~0.2): 72-79% at 79.
    # Level 6 tracks every pitch (LEVEL6 below).
    (0x80797233, b"\x55", bytes([79]), "tracks 79% of pitches (85 -> 79%; level 6: 100%)"),
    (0x806248F4, struct.pack(">f", 0.05), F0, "no aim error when tracking (+-0.05 -> 0)"),
    (0x80624984, b"\x28\x5f\x05\x02", b"\x00\x64\x00\x00",
     "takes: first pitch 40 -> 0%, outside 95 -> 100%, strikes 5 / 2 -> 0%"),
    (0x8062490E, b"\xfe\x02", b"\x00\x00", "swing timing error, right guess (-2..+2 -> 0 frames)"),
    (0x80624916, b"\xfc\x04", b"\x00\x00", "swing timing error, wrong guess (-4..+4 -> 0 frames)"),
    (0x80797253, b"\x1e", b"\x00", "never fooled by the decoy ball (star pitch 8: 30 -> 0%)"),
    # charge-swing chance by class x (0-1 / 2 strikes), 0x80797218[class*2 + k] (Nick, 2026-09-27; stock Balance
    # 40/10, Power 90/40, Speed 30/10, Technique 40/10)
    (0x80797218, bytes([40, 10, 90, 40, 30, 10, 40, 10]), bytes([100, 90, 100, 100, 100, 80, 100, 80]),
     "charge swings: Power 100/100, Balance 100/90, Technique 100/80, Speed 100/80 (0-1 / 2 strikes)"),
]
PITCHING = [
    (0x8062475F, b"\x00\x14\x1e\x28\x0a", b"\x00\x00\x00\x00\x64", "charged fastball always perfect (10 -> 100%)"),
    (0x807971E7, b"\x0a", b"\x00", "never repeats the last location (10 -> 0%)"),
    (0x807971EB, b"\x55", b"\x64", "always curves a plain pitch (85 -> 100%)"),
    (0x807971EF, b"\x46", b"\x64", "curves always break late (70 -> 100%)"),
]
FIELDING = [
    *[(0x80624A14 + 5 * c, s, b"\x64", f"{n} fielders always try a dive / jump ({s[0]} -> 100%)")
      for c, (n, s) in enumerate([("Balance", b"\x5f"), ("Power", b"\x62"), ("Speed", b"\x5f"), ("Technique", b"\x63")])],
    *[(0x80624A28 + 5 * c, b"\x5a", b"\x64", f"class {c}: always jumps / dodges an obstacle (90 -> 100%)")
      for c in range(4)],
    (0x80624A68, b"\x3c", b"\x64", "reacts to a good-chemistry teammate (60 -> 100%)"),
    (0x80624A6D, b"\x50", b"\x64", "reacts to a good-chemistry teammate, near (80 -> 100%)"),
    (0x806249E8, b"\x0a", b"\x00", "no extra reaction delay (10 -> 0 frames)"),
    (0x806249ED, b"\x08", b"\x00", "no extra reaction delay, 50 Hz (8 -> 0 frames)"),
    (0x806249F4, b"\x02", b"\x00", "infield throws at once (2 -> 0 frames)"),
    (0x806249F9, b"\x02", b"\x00", "outfield throws at once (2 -> 0 frames)"),
    (0x806249FE, b"\x01", b"\x00", "infield throws at once, 50 Hz (1 -> 0 frames)"),
    (0x80624A03, b"\x01", b"\x00", "outfield throws at once, 50 Hz (1 -> 0 frames)"),
    (0x80624A08, b"\x06", b"\x01", "re-plans the chase after a deflection at once (6 -> 1 frame; 0 never fires)"),
    (0x80624A0D, b"\x05", b"\x01", "re-plans the chase after a deflection, 50 Hz (5 -> 1 frame)"),
    (0x80797258, b"\x5a", b"\x64", "always throws harder on a close play (90 -> 100%)"),
    # FUN_800E246C, CPU only: dives / jumps on grounders and liners (dementatino's 040E2750 28000006: ball ids 2-5)
    # and on fly balls (frames-to-land had to be under 20 and over 20: never)
    (0x800E2750, b"\x28\x00\x00\x03", b"\x28\x00\x00\x06", "dives / jumps for grounders and liners"),
    (0x800E25B8, b"\x2c\x04\x00\x14", b"\x2c\x04\x00\x00", "dives for fly balls"),
]
RUNNING = [
    (0x8079727F, b"\x1e", b"\x64", "always gets a good jump when stealing (30 -> 100%)"),
    (0x80624A7E, b"\x00\x5a", b"\x00\x64", "sprint taps always land (90 -> 100%)"),
    (0x80624AA6, b"\x00\x5a", b"\x00\x64", "sprint taps always land, 50 Hz (90 -> 100%)"),
    (0x80624B1E, b"\x00\x14", b"\x00\x06", "close play: presses after 6 frames (20)"),
    (0x80624B26, b"\x00\x10", b"\x00\x05", "close play: presses after 5 frames, 50 Hz (16)"),
    (0x80797280, b"\x63" * 4, b"\x64" * 4, "close play: always presses (99 -> 100%, every level: by class)"),
]
# Level 6 overrides (Nick, 2026-09-27: no cheating, nothing faster than a human could react): (address, level 6
# bytes) over the group's level 5 bytes above; written only in level 6 matches (level5.py SWAPS6)
LEVEL6 = {
    "cpu-perfect-batting": [
        (0x80797233, b"\x64", "tracks every pitch (level 5: 79%)"),
    ],
    "cpu-perfect-fielding": [
        (0x806249E8, bytes([0x0A]), "reaction delay as stock level 4 (10 frames)"),
        (0x806249ED, bytes([0x08]), "reaction delay as stock level 4 (8 frames, 50 Hz)"),
        (0x806249F4, bytes([0x02]), "infield throw hold as stock (2 frames)"),
        (0x806249F9, bytes([0x02]), "outfield throw hold as stock (2 frames)"),
        (0x806249FE, bytes([0x01]), "infield throw hold as stock (1 frame, 50 Hz)"),
        (0x80624A03, bytes([0x01]), "outfield throw hold as stock (1 frame, 50 Hz)"),
        (0x80624A08, bytes([0x06]), "re-plan after a deflection as stock (6 frames)"),
        (0x80624A0D, bytes([0x05]), "re-plan after a deflection as stock (5 frames, 50 Hz)"),
        (0x80797258, bytes([0x00]), "never the harder close-play throw (a CPU-only boost)"),
    ],
    "cpu-perfect-running": [
        (0x8079727F, bytes([0x1E]), "good steal jump as stock (30%)"),
        (0x80624B1E, bytes([0x00, 0x0C]), "close play: presses after 12 frames (a fast human; stock 20)"),
        (0x80624B26, bytes([0x00, 0x0A]), "close play: presses after 10 frames, 50 Hz (stock 16)"),
    ],
}


def level6_swaps(features):
    """[(address, level 5 bytes, level 6 bytes)] for the enabled groups, for level5.apply's swaps6."""
    new = {at: n for f in features for at, _, n, _ in GROUPS[f]}
    return [(at, new[at], six) for f in features for at, six, _ in LEVEL6.get(f, ())]


# Nick, 2026-09-28: level 5 is level 6 but for its listed nerfs (sweet spot 85%, items, the wider outside miss, the
# 3-ball rate), so the no-cheating level 6 values of fielding and running are both levels' bytes: folded into the
# groups here (an entry whose level 6 bytes are stock is dropped: stock at both levels). Only batting's track roll
# stays a level 6 override (85% at level 5: the sweet-spot nerf).
BOTH_LEVELS = ("cpu-perfect-fielding", "cpu-perfect-running")


def _fold(group, overrides):
    six = {at: b for at, b, _ in overrides}
    return [(at, stock, six.get(at, new), what) for at, stock, new, what in group if six.get(at, new) != stock]


FIELDING = _fold(FIELDING, LEVEL6.pop("cpu-perfect-fielding"))
RUNNING = _fold(RUNNING, LEVEL6.pop("cpu-perfect-running"))
GROUPS = {"cpu-perfect-batting": BATTING, "cpu-perfect-pitching": PITCHING, "cpu-perfect-fielding": FIELDING,
          "cpu-perfect-running": RUNNING}


def apply(dol, feature):
    """Write one feature's bytes into `dol` (stock checked first). Returns log lines."""
    writes = GROUPS[feature]
    for at, stock, new, what in writes:
        assert len(stock) == len(new), what
        got = dol.read(at, len(stock))
        assert got == stock, f"{feature}: 0x{at:08X} is {got.hex()}, expected {stock.hex()} ({what})"
    for at, stock, new, what in writes:
        dol.write(at, new)
    return [f"{feature}: level 4 CPU, {len(writes)} writes (" + "; ".join(w[3] for w in writes) + ")"]
