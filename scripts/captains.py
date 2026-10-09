"""Custom team captains on the exhibition captain-select screen (Select::CExhiCaptainTask, code
0x802C8AB8-0x802CF418, layout dt_na.dat dir 119 file 18) and wherever the game draws a team's captain logo.
Build step 9 of charbuild.py (build_chars.py; --no-captain leaves the stock 12).

NEW_CAPTAINS (Nick, 2026-09-24): King Bob-omb and King Boo take Wario's and Waluigi's slots (indices 8 and 9),
Rosalina (0x81) and Luma (the yellow Luma, 0x84) are added as indices 12 and 13: 14 captains.
A build has the ones whose character it builds (configure(), charbuild step 9; ALL_CAPTAINS is the full list): a
replacing captain left out leaves its slot to the stock one (Wario stays captain 8), added ones close up (Luma is 12
without Rosalina), and the lineup is respaced over the ones there.

Teams store a captain INDEX (team struct *(r13-0xB00) +0x14 / +0x15); index -> character through the
12-entry table 0x806318A8.

  a. Per-captain tables, each relocated and extended (their neighbours are live data):
     0x806318A8 captain -> character (u32), 0x8062C9F0 captain -> lineup position (u8, node of layout
     element 0x34), 0x80631D30 captain -> portrait sprite row (s16 pair, 2nd = P2 alternative, also
     used by the "OK?" screen FUN_80085b98), 0x80623428 / 0x80623440 preferred batting / fielding
     slots (u8 pair; an added captain copies its prefs_from, a replacing one keeps the slot's). Tables
     searched by unrolled 2 x 6 loops are padded to 18 entries with values that never match, and those
     loops run 3 x 6.
  b. Bounds 12 -> COUNT: lineup builder (count 11..0), draw-order sort, cursor left / right, random
     captain (0..11), "both sides picked the same one", portrait and name widgets.
  c. The captain-select task (0xA4 bytes) keeps its 12 captain widgets at +0x74..+0xA3; it grows by 4 per
     added captain.
  d. Index -> art that is computed: the lineup element (0x1E + index), the name plate row (0xA6 + index),
     the team logo rows in file 1 (big: 0x0C + index in FUN_80395c08, small emblem: index in FUN_80395ce0,
     both used by ~20 screens and the in-game HUD). Added indices are hooked to their own rows / element
     (0x1E + 12 = 0x2A is taken). Replaced indices keep the computed rows and element, which are edited
     in place to show the new art.
  e. Layout (patch_layouts): file 18 gets a 512x384 texture page per custom captain with the portrait,
     lineup figure, highlight glow and name plate, and their sprite rows. A replaced captain's element and
     name row are repointed at them; an added one gets its own element (a copy of COPY_ELEMENT) and a
     node in element 0x34 (its lineup position). All 14 lineup positions are respaced (LINEUP_ORDER). File 1 gets one page with every custom captain's big
     logo and emblem. Both files grow: each language's copy is appended to dt_na.dat and its index
     record repointed.

Art: captains/<art>/<art>_portrait.png (~300 x 370), <art>_lineup.png (~100 x 150), logo.png (153 x 54),
emblem.png (90 x 90). A captain without them (a stock non-captain, a recolor, an import: the "captains" option's) gets
them drawn from its own 3D model when the player patches (captain_art.model_art, model_render: its model block from
their game, a recolor's recoloured block, an import's own; nothing of the game's ships); only a character whose
model can't be read gets a labelled placeholder (captain_art.placeholder).

The "captains" option (git-a7, for the patcher: any character, stock or new, as a captain; Nick 2026-09-26):
  {"list": [{"character": "King Bob-omb", "replaces": "Wario"}, {"character": "Rosalina", "prefs_from": "Peach"}, ...],
   "positions": {"Rosalina": {"x": -60, "y": 376}, ...}, "remove": ["Wario", ...]}
  A stock captain keeps its index while there are 12 or more (challenge mode, the attract demo and saved teams store
  indices), so a new captain either replaces one (its index; the stock captain loses its captain flag and star moves:
  stat_edits) or is added (a removed captain's free index first, then 12..). "remove" takes stock captains off captain
  select (Nick 2026-09-29: 2 to 18 captains; they lose their star moves as a replaced one does); fewer than 12 are
  compacted to indices 0..COUNT-1 (COMPACT / MOVED / TAIL below: every per-captain table, element, row and node follows
  its captain). The order on screen is the x of each figure (the cursor goes to the nearest x) and the depth its y
  (the draw order sorts by y): positions, else the auto layout (lineup_x). plan() / check() / notes() read an option;
  configure(ids, option, chars) applies one. canvas(), figures(), default_positions(), candidates() are the
  captain editor's (git-f4); figures() gives each figure the box the game draws it in (FRAME: its sprite centred on its
  node, as test_captains measures against the game's layout), and a lineup nothing respaces stays on the game's nodes. No option: today's roster (ALL_CAPTAINS), byte for byte; DEFAULT_OPTION spells it out.
  Team logos (Nick 2026-09-28, "let us edit/add team logos"): a list entry's "logo" / "emblem" (a picture's path) is
  that captain's logo / emblem over its art folder's; "art": {"Mario": {"logo": path, "emblem": path}} gives a stock
  captain in its own slot a player's logo / emblem (file 1: new CI8 pages, its rows 0x0C + index / index repointed;
  the captain stays the game's otherwise). Paths are relative to the program folder (the "logos" folder there,
  save_image()) or absolute; a picture of any size is fitted keeping its shape (captain_art.fit_pad). team_art() is
  the editor's preview. Every screen that draws a team's logo reads those two rows (FUN_80395c08 / FUN_80395ce0),
  so a changed logo shows on all of them; Mario Stadium's own signs don't (see Not changed).

Not changed: challenge-mode setup and the attract demo (their 12-captain loops never meet indices 12+),
the stadium logo animation table 0x8062CD40 (Mario Stadium day / night, GmModel::CBbGimmickCtrlMario*::vf0C: its
signs' texture animation frame is the captain's CHARACTER's place in this 12-id table, -1-terminated; the frames are
the stadium model's own art, so a player's logo doesn't show there, and a new captain gets frame 12), the selector
table's captain byte (+4; stock captains 1), and the stats rows (captain flag +7: charbuild's star_swing_stats sets it
for King Boo; Rosalina's (star swing 12, Gravity Ball 13 in play), Luma's (star swing 1, Star Shower 15 in play) and King
Bob-omb's (captain 1, star pitch / swing 7, Wario's Phony ones, named "Kingly Kaboom") are in their definitions).
"""
import struct
from pathlib import Path

from PIL import Image

from ppc import Asm
import captain_art

ROOT = Path(__file__).resolve().parents[1]
STOCK = 12
NEW_CAPTAINS = [
    # index: a stock slot (8 Wario, 9 Waluigi) is replaced, 12.. are added. Added captains: prefs_from
    # (batting / fielding preferences), lineup x and dy, node_from (the lineup node copied and moved)
    dict(index=8, id=0x78, name="King Bob-omb", art="king-bobomb", replaces=0x0A),
    dict(index=9, id=0x25, name="King Boo", art="king-boo", replaces=0x0B),
    dict(index=12, id=0x81, name="Rosalina", art="rosalina", prefs_from=4, node_from=8, y=376),
    dict(index=13, id=0x84, name="Luma", art="luma", prefs_from=4, node_from=7, y=404),
]
# Lineup, left to right, by captain index. The widescreen view shows about -140..800 (the stock 12 only span
# 39..607), and the figures differ in width, so the positions come from each figure's VISIBLE extent: every
# neighbouring pair gets the same gap (a small equal overlap: 14 are wider than the screen), between DK's
# left edge and Bowser's right edge at LINEUP_SPAN. Even centres left some pairs apart and others
# overlapping; two rows were rejected (Nick, Dolphin 2026-09-24). Stock y (depth, draw order) is kept; an
# added captain's is its "y" (small Luma in front).
LINEUP_ORDER = [2, 3, 12, 8, 10, 5, 1, 0, 4, 6, 13, 9, 11, 7]   # DK, Diddy, Rosalina, King Bob-omb, Birdo,
STOCK_FRAMES = [0, 1, 11, 6, 4, 3, 5, 10, 8, 9, 2, 7]           # Daisy, Luigi, Mario, Peach, Yoshi, Luma,
LINEUP_SPAN = (-134, 788)                                       # King Boo, Bowser Jr., Bowser
# (left, right) of each figure's visible body relative to its position (layout units), measured from Nick's
# chars-68 screenshot at known positions (screen px = 312.6 + 2.036 * x). What shows counts: Bowser's body,
# not his hand behind Bowser Jr.; Diddy without his tail behind DK. (A first pass from chars-65 counted
# Bowser's hand and left a gap before him.)
VISIBLE = {2: (-79, 80), 3: (-23, 36), 12: (-19, 46), 8: (-60, 36), 10: (-48, 35), 5: (-22, 30), 1: (-43, 29),
           0: (-29, 20), 4: (-28, 31), 6: (-45, 56), 13: (-38, 38), 9: (-52, 28), 11: (-38, 36), 7: (-68, 93)}


# Nick's moves on top of that (chars-72 screenshot, 2026-09-24), layout units (~2 screen px each):
# dx by captain index, and dy (negative = up; King Boo stays below Bowser's 362 to draw in front of him)
LINEUP_NUDGE = {3: -10, 8: -5, 10: -20, 1: -10, 4: 10, 6: 10}   # Diddy, King Bob-omb, Birdo, Luigi, Peach, Yoshi
LINEUP_DY = {9: -4}                                             # King Boo


def lineup_x(order=None, visible=None, nudge=None):
    """{captain index: position x} with equal gaps between the figures' visible extents (this build's lineup, or a
    plan's order / visible / nudge)."""
    order = LINEUP_ORDER if order is None else order
    visible = VISIBLE if visible is None else visible
    nudge = LINEUP_NUDGE if nudge is None else nudge
    widths = [visible[c][1] - visible[c][0] for c in order]
    lo, hi = LINEUP_SPAN
    gap = (hi - lo - sum(widths)) / (len(order) - 1)
    if len(order) < STOCK:                  # fewer than the game's 12 (stock captains removed): the full roster's gap,
        full = [_FULL["visible"][c][1] - _FULL["visible"][c][0] for c in _FULL["order"]]   # the lineup centred
        gap = (hi - lo - sum(full)) / (len(full) - 1)
        lo = (lo + hi - sum(widths) - gap * (len(order) - 1)) / 2
    out, left = {}, lo
    for c, w in zip(order, widths):
        out[c] = round(left - visible[c][0]) + nudge.get(c, 0)
        left += w + gap
    return out
ADDED = [c for c in NEW_CAPTAINS if c["index"] >= STOCK]
REPLACED = [c for c in NEW_CAPTAINS if c["index"] < STOCK]
COUNT = STOCK + len(ADDED)
assert [c["index"] for c in ADDED] == list(range(STOCK, COUNT))
# The stock captain table (0x806318A8): Mario, Luigi, DK, Diddy, Peach, Daisy, Yoshi, Bowser, Wario, Waluigi, Birdo,
# Bowser Jr. (add_captain checks the game's)
STOCK_TABLE = (0x00, 0x01, 0x02, 0x03, 0x04, 0x05, 0x06, 0x09, 0x0A, 0x0B, 0x11, 0x13)
# Every custom captain and the full roster's lineup; configure() picks the ones in a build from these
ALL_CAPTAINS = NEW_CAPTAINS
_FULL = dict(order=LINEUP_ORDER, visible=VISIBLE, nudge=LINEUP_NUDGE, dy=LINEUP_DY)
# A stock captain that keeps its slot (the captain replacing it isn't in the build): its figure's visible extent,
# from its stock lineup art in file 18 (the alpha of its row, x its key's scale, centred on the position, as DK's and
# Mario's measured VISIBLE are): Wario row 50 (120 px, opaque 1..119), Waluigi row 51 (100 px, 2..97). Not measured
# on screen (VISIBLE's way) yet.
STOCK_VISIBLE = {8: (-59, 59), 9: (-48, 47)}
POSITIONS = {}                       # {captain index: (x or None, y or None)}: the option's positions (configure)
# Stock captains removed (the option's "remove"; Nick 2026-09-29: 2 to 18 captains). Fewer than 12 captains COMPACT the
# indices: captains 0..COUNT-1 are the ones shown, a stock captain can sit in another stock slot (MOVED: {slot: stock
# index}; that slot's element, rows, portrait, prefs, star gains and chance row are copied from its own), and the slots
# COUNT..11 keep the removed ones (TAIL) so the game's fixed 12-captain loops (challenge mode, the attract demo) still
# meet real captains. The lineup's node table is then 0..11 in order (the lineup builder draws nodes COUNT-1..0).
REMOVED = []                         # stock captain indices removed (configure)
MOVED = {}                           # {slot: stock index} (configure)
GEO = {}                             # {slot < 12: the stock slot whose element / node geometry it has} (configure)
TAIL = []                            # captain ids in slots COUNT..11 (configure)
COMPACT = False                      # COUNT < 12 (configure)
TABLE_SHOWN = None                   # the option's captain table (configure); None: table() builds it
STOCK_RENAMED = {}                   # {stock captain index: new name}: a renamed stock captain keeping its slot (configure)


# --- the "captains" option --------------------------------------------------------------------------------------------
MAX_CAPTAINS = 18                    # the captain lookups run 3 x 6 (4 x 6 would allow 24)
TESTED_CAPTAINS = 14                 # what has been played in Dolphin; more get a warning
STOCK_CAPTAIN_NAMES = ("Mario", "Luigi", "Donkey Kong", "Diddy Kong", "Peach", "Daisy", "Yoshi", "Bowser", "Wario",
                       "Waluigi", "Birdo", "Bowser Jr.")        # STOCK_TABLE's, by index
MIN_CAPTAINS = 2                     # captain select needs two to pick from
VIEW_X = (-140, 800)                 # lineup x that shows on a widescreen TV (layout units)
# The captain-select screen is file 18's 640 x 448 frame, in layout units, y down: a 4:3 TV shows all of it (x 0..640),
# a widescreen one VIEW_X. Element 0x34 is drawn in it as it is (no parent moves or scales it). A captain's figure is
# its element's sprite (0x1E + index, node 0, key 0: corners (-w/2, -h/2) about the key, sprite scale) scaled by its
# lineup node's scale and CENTRED on the node's first key (its resting place: the keys slide it 30 down on entry).
FRAME = (0, 0, 640, 448)
VIEW_Y = (FRAME[1], FRAME[3])        # the whole frame's height
STOCK_NODE_Y = (388, 377, 369, 366, 365, 381, 402, 394, 384, 367, 362, 360)   # element 0x34's nodes, first key's y
STOCK_NODE_X = (344, 291, 210, 253, 377, 429, 65, 533, 146, 494, 607, 39)     # ... and x
# by stock captain index: its node's scale (x, y) and its figure sprite's half size (|corner| x sprite scale), layout
# units (test_captains checks them against the game's file 18)
STOCK_NODE_SCALE = ((0.95, 0.95), (0.95, 0.95), (1.0, 1.0), (0.95, 0.95), (0.96, 0.96), (0.96, 0.96), (0.87, 0.9),
                    (1.0, 1.0), (1.0, 1.0), (0.98, 0.98), (0.87, 0.87), (0.98, 0.98))
STOCK_SPRITE_HALF = ((30, 63), (47, 68.4), (82.5, 91), (58, 58.5), (36, 75.6), (34, 75.6), (57, 72.9), (104.5, 95),
                     (60, 64.4), (50, 81), (55, 78.3), (50, 45))
UNITS_PER_PX = 0.8                   # layout units per pixel of a 100 x 150 lineup figure (Rosalina's, Luma's, King
#                                      Boo's measured VISIBLE / their art's alpha width: 0.79, 0.78, 0.82)


# The words that tell the player how to fix a captain problem: the full patcher's, or an edition's own
# (editions/*.json "captain_words"; the Characters Beta points at its character window, which has no Characters tab).
# {name} / {missing} are filled in.
WORDS = {"not_built": "{name} isn't in this build (add it to the new characters)",
         "no_swing": "{name} has no star swing of their own: as a captain they use the generic star swing and pitch "
                     "(give them one on the Characters tab)",
         "no_swing_short": "no star swing of their own (uses the generic one)",
         "no_art": "{name}: no captain art ({missing}): drawn from their 3D model when you patch (give a folder of "
                   "PNGs as \"art\" for your own)"}


def words():
    """WORDS with the edition's "captain_words" over them (the full patcher, or no edition module: WORDS)."""
    try:
        import edition
    except ImportError:
        return WORDS
    return dict(WORDS, **((edition.load() or {}).get("captain_words") or {}))


# What the Captains tab changes in the game's data (the patcher window's "i": git-f4's captain_editor.data_fields)
DATA = {
    "list": [
        dict(file="main.dol", where="the captain table, 0x806318A8 in the game (12 x u32, captain index -> character id), "
             "moved to a longer copy of up to 18 (the lookups that read it run 3 x 6 instead of 2 x 6)",
             field="a big-endian u32 per captain", notes="A stock captain keeps its index (challenge mode and saved "
             "teams store indices); a new captain replaces one or is added at 12 and up. Removing stock captains (2 to 18 "
             "in all) moves the ones left to indices 0 and up, the removed ones after them.", source="scripts/captains.py"),
        dict(file="main.dol", where="the per-captain tables, moved and extended the same way: lineup node 0x8062C9F0 (u8), "
             "portrait row 0x80631D30 (s16 pair), batting / fielding preferences 0x80623428 / 0x80623440 (u8 pair), "
             "star meter gains 0x8062BD50 (0x52-byte rows)", field="one entry per captain index",
             source="scripts/captains.py"),
        dict(file="dt_na.dat, dir 119 file 18 (captain select)", where="per custom captain: a 512 x 384 page with the "
             "portrait, standing figure, glow and name plate; a replacing captain's element 0x1E + index and name row "
             "0xA6 + index point at it, an added one gets its own element and a node in element 0x34",
             field="RGB5A3 texture pages and 0x14-byte rows", source="scripts/captains.py"),
        dict(file="dt_na.dat, dir 119 file 1 (menus)", where="team logo row 0x0C + index and emblem row index point at "
             "the captain's logo and emblem (CI8, a palette each); a stock captain given a player's logo / emblem (\"art\") "
             "gets its rows repointed the same way", field="rows", source="scripts/captains.py"),
    ],
    "positions": dict(file="dt_na.dat, dir 119 file 18 (captain select)",
                      where="element 0x34 (the lineup): one node per captain (stock captains: node 0x8062C9F0[index]); "
                            "a captain's position is its node's first key",
                      field="key +8: s16 x, +0xA: s16 y, in layout units (the other keys of the node move with it)",
                      notes="The cursor moves by x and the draw order sorts by y (a larger y is in front). The "
                            "widescreen view shows x about -140 to 800.", source="scripts/captains.py"),
}


def _full_table():
    t = list(STOCK_TABLE)
    for c in ALL_CAPTAINS:
        if c["index"] < STOCK:
            t[c["index"]] = c["id"]
    return t + [c["id"] for c in ALL_CAPTAINS if c["index"] >= STOCK]


_FULL_TABLE = _full_table()
KNOWN = {c["id"]: c for c in ALL_CAPTAINS}                     # our captains' art, prefs_from, node_from, y
ORDER_IDS = [_FULL_TABLE[i] for i in LINEUP_ORDER]             # the roster's lineup, by character
VISIBLE_IDS = {**{_FULL_TABLE[i]: v for i, v in VISIBLE.items()}, **{STOCK_TABLE[i]: v for i, v in STOCK_VISIBLE.items()}}
NUDGE_IDS = {_FULL_TABLE[i]: v for i, v in LINEUP_NUDGE.items()}
DY_IDS = {_FULL_TABLE[i]: v for i, v in LINEUP_DY.items()}
DEFAULT_OPTION = {"list": [dict(character=c["name"], **({"replaces": STOCK_CAPTAIN_NAMES[c["index"]]}
                                                         if c["index"] < STOCK else {})) for c in ALL_CAPTAINS]}
ENTRY_KEYS = {"character", "replaces", "prefs_from", "art", "name", "portrait", "lineup", "logo", "emblem"}
OPTION_KEYS = {"list", "positions", "art", "remove"}
TEAM_ART = ("logo", "emblem")        # a captain's team logo (153 x 54) and emblem (90 x 90), file 1
CAPTAIN_ART = ("portrait", "lineup")   # captain-select portrait and standing lineup figure, file 18
PLAYER_ART = CAPTAIN_ART + TEAM_ART
LOGOS_DIR = ROOT / "logos"           # the player's pictures, fitted (save_image; package.PLAYER_FOLDERS)
STOCK_ART = {}                       # {stock captain index: {"logo" / "emblem": Path}}: the option's "art" (configure)


def image_path(p):
    """A picture's path in the option: relative to the program folder, or absolute."""
    p = Path(p)
    return p if p.is_absolute() else ROOT / p


def player_image(path, key):
    """A player's picture fitted as a logo or emblem (captain_art.fit_pad)."""
    return captain_art.fit_pad(Image.open(image_path(path)), key)


def save_image(src, key, name, folder=None):
    """A player's picture (PNG / JPG, any size), fitted, saved as a PNG in the logos folder beside the program ->
    the path the option stores (relative to the program folder when it's in there). The name carries the picture's
    hash, so choosing another never overwrites one a saved profile still names."""
    import hashlib
    import io
    img = captain_art.fit_pad(Image.open(src), key)
    buf = io.BytesIO()
    img.save(buf, "PNG")
    slug = "-".join(_key(name).replace(".", "").replace("'", "").split()) or "captain"
    folder = Path(folder or LOGOS_DIR)
    folder.mkdir(parents=True, exist_ok=True)
    out = folder / f"{slug}_{key}_{hashlib.md5(buf.getvalue()).hexdigest()[:8]}.png"
    out.write_bytes(buf.getvalue())
    try:
        return out.resolve().relative_to(ROOT.resolve()).as_posix()
    except ValueError:
        return str(out)


def _key(s):
    return " ".join(str(s).lower().replace("_", " ").split())


def _cid(v):
    return int(v, 0) if isinstance(v, str) else int(v)


def _english(value):
    """A name or "rename" value (one string, or {"en", "es", "fr"}) -> the English name."""
    return value if isinstance(value, str) else (value.get("en") or next(iter(value.values())))


def current_name(cid, chars=(), defaults=True):
    """A character's name in this build: a stock rename (renames()), a new character's definition name (the profile's
    rename merged into it), else our captain's name (KNOWN); None for a stock character with its own name."""
    new = renames(chars, defaults)
    if cid in new:
        return new[cid]
    for e in chars:
        if e.get("id") is not None and not e.get("stock") and _cid(e["id"]) == cid and e.get("name"):
            return _english(e["name"])
    return KNOWN[cid]["name"] if cid in KNOWN else None


def renames(chars=(), defaults=True):
    """{stock id: its name in this build}: our renames (char_names.STOCK_RENAMES: Captain Toad, the Toad Brigade,
    Mailtoad; with defaults) and stock entries' "rename" (the character editor's), in English."""
    import char_names
    out = char_names.stock_renames() if defaults else {}
    for e in chars:
        if e.get("stock") and e.get("rename") and e.get("id") is not None:
            out[_cid(e["id"])] = _english(e["rename"])
    return out


def _names(chars=(), defaults=True):
    """{name key: (id, name shown)}: the stock roster (sluggers_data), the stock captains' short names, our captains and
    chars (definitions, stock entries). A renamed stock character is known by its new name and its old one, and shown
    by its new one (renames(); grid_order does the same)."""
    from sluggers_data import CHAR_NAMES
    import charbuild
    out = {_key(n): (cid, n) for cid, n in enumerate(CHAR_NAMES[:charbuild.STOCK_IDS])}
    out.update({_key(n): (STOCK_TABLE[i], n) for i, n in enumerate(STOCK_CAPTAIN_NAMES)})
    out.update({_key(c["name"]): (c["id"], c["name"]) for c in ALL_CAPTAINS})
    for e in chars:
        if e.get("name") and e.get("id") is not None:
            out[_key(_english(e["name"]))] = (_cid(e["id"]), _english(e["name"]))
    new = renames(chars, defaults)
    out = {k: (cid, new.get(cid, n)) for k, (cid, n) in out.items()}
    out.update({_key(n): (cid, n) for cid, n in new.items()})
    return out


def _stock_captain_names(new):
    """STOCK_CAPTAIN_NAMES with this build's renames."""
    return tuple(new.get(cid, n) for cid, n in zip(STOCK_TABLE, STOCK_CAPTAIN_NAMES))


def _resolve(ref, names):
    """A character given by name or id -> (id, name), or None."""
    if isinstance(ref, int) and not isinstance(ref, bool) or isinstance(ref, str) and ref.strip().lower().startswith("0x"):
        try:
            cid = _cid(ref)
        except ValueError:
            return None
        return next(((i, n) for i, n in names.values() if i == cid), (cid, f"0x{cid:02X}"))
    return names.get(_key(ref)) if isinstance(ref, str) else None


def _swings_offered():
    """Whether our star swings can be built: the full patcher, or an edition offering custom-swings (the Characters
    Beta doesn't, so King Boo has no swing of ours there)."""
    try:
        import edition
    except ImportError:
        return True
    ed = edition.load()
    return ed is None or "custom-swings" in ed.get("features", ())


def _has_star_swing(cid, chars=(), defaults=True):
    """A captain needs the captain flag and a star swing (+7, +9): a stock captain, a custom swing's default character
    (King Boo), or a definition / stock entry with "star swing" (the flag comes with it: normalize, star_swing_stats)."""
    if cid in STOCK_TABLE:
        return True
    import custom_swings
    if defaults and _swings_offered() and any(cid in ids for ids in custom_swings.DEFAULT_CHARS.values()):
        return True
    for e in chars:
        if e.get("id") is not None and _cid(e["id"]) == cid:
            swing = e.get("star swing")             # (a setting: 0 is Captain star moves No, over the stats')
            if swing if swing is not None else (e.get("stats") or {}).get("star swing"):   # (normalized: top-level None)
                return True
    return False


def _art_of(e, cid, name):
    """{"art": folder name[, "art_dir": the player's folder]}: our captains' art, captains/<name>/, or the entry's
    "art" folder (portrait.png, lineup.png, logo.png, emblem.png or <folder>_portrait.png / _lineup.png)."""
    if e.get("art"):
        p = Path(e["art"])
        return {"art": p.name, "art_dir": p}
    if cid in KNOWN:
        return {"art": KNOWN[cid]["art"]}
    return {"art": "-".join(_key(name).replace(".", "").replace("'", "").split())}


def _art_files(c):
    folder = c.get("art_dir") or ROOT / "captains" / c["art"]
    out = {}
    for key in ("portrait", "lineup", "logo", "emblem"):
        names = ([f"{c['art']}_{key}.png"] if key in ("portrait", "lineup") else []) + [f"{key}.png"]
        out[key] = next((folder / n for n in names if (folder / n).exists()), None)
    for key in PLAYER_ART:                                   # the player's own per-part picture override
        if c.get(key + "_file") is not None:
            out[key] = c[key + "_file"]
    return out


GAME = None          # the player's game folder the editor passed (figures / team_art), for drawn art's stock models
_DRAWN = {}          # {(captain id, name, model, game): model_art images or None}: drawn once per build / editor


def _model_of(cid, chars=()):
    """Where a character's 3D model (its high-detail block, dt_na dir + 0x12 file 0) comes from, for art drawn from
    it: {"block": a definition's model_blocks 0 (a path or bytes)}, {"recolor": a recipe} (the editor's recolors,
    before the patch makes their blocks), {"stock": id} (the player's game: a stock character, or a new one without
    its own block: its template's); None: none known."""
    import charbuild
    d = next((e for e in chars if e.get("id") is not None and _cid(e["id"]) == cid and not e.get("stock")), None)
    if d is not None:
        own = d.get("model_blocks") or {}
        block = own.get("0", own.get(0))
        if block is not None:
            return {"block": block if isinstance(block, (bytes, bytearray)) else str(block)}
        if d.get("_recolor"):
            return {"recolor": d["_recolor"]}
        if d.get("template") is not None:
            try:
                import recolor
                return {"stock": recolor.char_id(d["template"])}
            except Exception:
                return None
        return None
    return {"stock": cid} if cid < charbuild.STOCK_IDS else None


def _model_block(model, game):
    import recolor
    if "block" in model:
        b = model["block"]
        if isinstance(b, (bytes, bytearray)):
            return bytes(b)
        p = Path(b)
        if not p.is_absolute():
            import charbuild
            p = charbuild.asset(b)
        return p.read_bytes()
    g = recolor.Game(str(game))
    if "stock" in model:
        return g.file(model["stock"] + recolor.MODEL_DIR_BASE, 0)
    r = model["recolor"]
    block, _ = recolor.recolor_block(recolor.base_of(g, r["base"], {}).block(0), r["recolor"])
    return block


def drawn_art(c, game=None):
    """{"portrait", "lineup", "logo", "emblem"} drawn from the captain's 3D model (captain_art.model_art), or None
    (no model known, or it can't be read: the placeholder stays). game: the player's game (default GAME, else the
    build's, game_source)."""
    import json
    model = c.get("model")
    if model is None:
        return None
    if game is None:
        import game_source
        game = GAME or game_source.root()
    key = (c["id"], c["name"], json.dumps(model, sort_keys=True, default=lambda b: f"{len(b)}:{hash(bytes(b))}"),
           str(game))
    if key not in _DRAWN:
        try:
            import model_render
            _DRAWN[key] = captain_art.model_art(model_render.mesh(_model_block(model, game)), c["name"])
        except (Exception, SystemExit):                     # (a model the renderer can't read: the placeholder)
            _DRAWN[key] = None
    return _DRAWN[key]


def _lineup_visible(c):
    """(left, right) of a figure we have no measurement for: its art's alpha width x UNITS_PER_PX, centred."""
    img = art(c)[0]["lineup"]
    box = img.getchannel("A").getbbox() or (0, 0, img.width, img.height)
    half = (box[2] - box[0]) * UNITS_PER_PX / 2
    return -round(half), round(half)


def plan(option=None, chars=(), ids=None, defaults=True, swings=True):
    """The captains an option asks for -> {"captains": NEW_CAPTAINS-style dicts, "table", "order", "visible", "nudge",
    "dy", "positions", "errors", "warnings"}. option None = DEFAULT_OPTION. chars: definitions and stock entries (names,
    star swings); ids: the characters in the build (None: any); defaults: charbuild's char_defaults (King Boo's swing);
    swings: False leaves out the star-swing rule (the editor's views; check() and configure() keep it)."""
    option = DEFAULT_OPTION if option is None else option
    errors, warnings = [], []
    stock_names = _stock_captain_names(renames(chars, defaults))
    out = dict(captains=[], table=list(STOCK_TABLE), order=[], visible={}, nudge={}, dy={}, positions={},
               errors=errors, warnings=warnings, stock_names=stock_names)
    out["stock_art"] = {}
    if not isinstance(option, dict) or set(option) - OPTION_KEYS:
        errors.append('captains: {"list": [...], "positions": {...}, "art": {...}}')
        return out
    names = _names(chars, defaults)
    say = words()
    caps, replaced = [], {}
    for n, e in enumerate(option.get("list") or []):
        e = {"character": e} if isinstance(e, (str, int)) else e
        if not isinstance(e, dict) or "character" not in e:
            errors.append(f'captain {n + 1}: needs a "character"')
            continue
        if set(e) - ENTRY_KEYS:
            errors.append(f"captain {n + 1}: unknown {', '.join(sorted(set(e) - ENTRY_KEYS))} "
                          f"(a captain takes {', '.join(sorted(ENTRY_KEYS))})")
        r = _resolve(e["character"], names)
        if r is None:
            errors.append(f"{e['character']}: not a character (a stock character's name or a new character's)")
            continue
        cid, cname = r
        name = e.get("name") or current_name(cid, chars, defaults) or cname
        if ids is not None and cid not in ids:
            errors.append(say["not_built"].format(name=name))
            continue
        if cid in STOCK_TABLE:
            errors.append(f"{name} is already a captain")
            continue
        if any(c["id"] == cid for c in caps):
            errors.append(f"{name} is in the list twice")
            continue
        c = dict(index=None, id=cid, name=name, **_art_of(e, cid, name))
        model = _model_of(cid, chars)
        if model is not None:
            c["model"] = model
        if e.get("replaces") is not None:
            rr = _resolve(e["replaces"], names)
            if rr is None or rr[0] not in STOCK_TABLE:
                errors.append(f"{name}: {e['replaces']} isn't one of the 12 stock captains "
                              f"({', '.join(stock_names)})")
                continue
            if rr[0] in replaced:
                errors.append(f"{stock_names[STOCK_TABLE.index(rr[0])]} is replaced twice "
                              f"({replaced[rr[0]]} and {name})")
                continue
            replaced[rr[0]] = name
            c.update(index=STOCK_TABLE.index(rr[0]), replaces=rr[0])
        # (Nick: who is a captain and captain star moves are separate: anyone can be a captain; without star moves of
        # their own they use the generic star swing and pitch, as any non-captain does. A note, not a stop.)
        if swings and not _has_star_swing(cid, chars, defaults):
            warnings.append(say["no_swing"].format(name=name))
        known = KNOWN.get(cid, {})
        if e.get("prefs_from") is not None:
            pr = _resolve(e["prefs_from"], names)
            if pr is None or pr[0] not in STOCK_TABLE:
                errors.append(f"{name}: prefs_from {e['prefs_from']} isn't one of the 12 stock captains")
            else:
                c["prefs_from"] = STOCK_TABLE.index(pr[0])
        elif c["index"] is None:
            c["prefs_from"] = known.get("prefs_from", 4)             # Peach's, as Rosalina's and Luma's
        if c["index"] is None:
            c["node_from"] = known.get("node_from", 8)
            if "y" in known:
                c["y"] = known["y"]
        if c.get("art_dir") is not None and not Path(c["art_dir"]).is_dir():
            errors.append(f"{name}: art folder {c['art_dir']} not found")
        for key in PLAYER_ART:
            if e.get(key) and _image_ok(e[key], name, key, errors):
                c[key + "_file"] = image_path(e[key])
        missing = [k for k, p in _art_files(c).items() if p is None]
        if missing:
            warnings.append(say["no_art"].format(name=name, missing=", ".join(missing)))
        caps.append(c)
    removed = []                                             # stock captains taken off captain select
    for ref in option.get("remove") or []:
        rr = _resolve(ref, names)
        if rr is None or rr[0] not in STOCK_TABLE:
            errors.append(f"remove: {ref} isn't one of the 12 stock captains ({', '.join(stock_names)})")
            continue
        i = STOCK_TABLE.index(rr[0])
        if rr[0] in replaced:
            errors.append(f"{stock_names[i]} is both removed and replaced (by {replaced[rr[0]]}): pick one")
        elif i not in removed:
            removed.append(i)
    # slots: a stock captain in its own, a replacing one in the one it takes; a removed one's is a hole that an added
    # captain fills first (the others go at 12..). Fewer than 12 left: compacted (MOVED).
    slots = [("stock", i) for i in range(STOCK)]
    for c in caps:
        if c["index"] is not None:
            slots[c["index"]] = ("cap", c)
    for i in removed:
        slots[i] = None
    holes, filled = [i for i in range(STOCK) if slots[i] is None], set()
    for c in (c for c in caps if c["index"] is None):
        if holes:
            c["index"] = holes.pop(0)
            filled.add(c["index"])
            slots[c["index"]] = ("cap", c)
        else:
            c["index"] = len(slots)
            slots.append(("cap", c))
    count = len(slots) - len(holes)
    added = [c for c in caps if c["index"] >= STOCK]
    geo = {i: i for i in range(STOCK)}
    moved, tail = {}, []
    if count < STOCK:
        movers = [j for j in range(count, STOCK) if slots[j] is not None]
        for h, j in zip([h for h in holes if h < count], movers):
            slots[h], slots[j], geo[h] = slots[j], None, j
        spare = [j for j in range(count, STOCK) if slots[j] is None]
        for i in sorted(removed, key=lambda i: (i not in spare, i in filled, i)):   # own slot when in the tail
            if not spare:                    # (one whose slot a new captain took is out, as a replaced one)
                break
            j = i if i in spare else spare[0]
            slots[j], geo[j] = ("stock", i), i
            spare.remove(j)
        for j, (kind, v) in enumerate(slots):
            if kind == "cap":
                v["index"] = j
            elif v != j:
                moved[j] = v
        tail = [STOCK_TABLE[slots[j][1]] for j in range(count, STOCK)]
    if count > MAX_CAPTAINS:
        errors.append(f"{count} captains: at most {MAX_CAPTAINS} fit on captain select")
    elif count < MIN_CAPTAINS:
        errors.append(f"{count} captain{'s' if count != 1 else ''}: at least {MIN_CAPTAINS} (captain select needs two "
                      "to pick from)")
    elif count > TESTED_CAPTAINS:
        warnings.append(f"{count} captains: more than {TESTED_CAPTAINS} haven't been played in the game yet")
    table = out["table"] = [STOCK_TABLE[v] if kind == "stock" else v["id"] for kind, v in slots[:count]]
    out.update(removed=sorted(removed), moved=moved, geo=geo, tail=tail)
    src = {j: v for j, (kind, v) in enumerate(slots[:count]) if kind == "stock"}   # {slot: stock index}
    out["stock_slots"] = src
    by_index = {c["index"]: c for c in caps}
    rank = {i: ORDER_IDS.index(cid) if cid in ORDER_IDS else _FULL["order"].index(src[i]) if i in src
            else len(ORDER_IDS) + i for i, cid in enumerate(table)}
    out["order"] = sorted(range(count), key=lambda i: (rank[i], i))
    out["visible"] = {i: VISIBLE_IDS[cid] if cid in VISIBLE_IDS else _lineup_visible(by_index[i])
                      for i, cid in enumerate(table)} if not errors else {}
    out["nudge"] = {i: NUDGE_IDS[cid] for i, cid in enumerate(table) if cid in NUDGE_IDS}
    out["dy"] = {i: DY_IDS[cid] for i, cid in enumerate(table) if cid in DY_IDS}
    for ref, p in (option.get("positions") or {}).items():
        r = _resolve(ref, names)
        if r is None or r[0] not in table:
            errors.append(f"positions: {ref} isn't a captain here")
            continue
        if (not isinstance(p, dict) or not p or set(p) - {"x", "y"}
                or not all(isinstance(v, int) and not isinstance(v, bool) for v in p.values())):
            errors.append(f'positions: {ref}: {{"x": int, "y": int}} in layout units')
            continue
        out["positions"][table.index(r[0])] = (p.get("x"), p.get("y"))
        if p.get("x") is not None and not VIEW_X[0] <= p["x"] <= VIEW_X[1]:
            warnings.append(f"{r[1]} at x {p['x']} is off screen (the lineup shows {VIEW_X[0]}..{VIEW_X[1]})")
    for ref, a in (option.get("art") or {}).items():         # a stock captain's own logo / emblem
        r = _resolve(ref, names)
        if r is None or r[0] not in STOCK_TABLE:
            errors.append(f"art: {ref} isn't one of the 12 stock captains")
            continue
        i = STOCK_TABLE.index(r[0])
        if not isinstance(a, dict) or set(a) - set(TEAM_ART):
            errors.append(f'art: {ref}: {{"logo": picture, "emblem": picture}}')
            continue
        if r[0] not in table:
            warnings.append(f"{stock_names[i]} isn't a captain here ("
                            + (f"{replaced.get(r[0])} takes their place" if r[0] in replaced else "removed")
                            + "), so their logo isn't used")
            continue
        files = {k: image_path(v) for k, v in a.items() if v and _image_ok(v, stock_names[i], k, errors)}
        if files:
            out["stock_art"][table.index(r[0])] = files             # (by slot)
    out["captains"] = caps
    return out


def _image_ok(path, name, key, errors):
    """A logo / emblem picture that opens (else the problem, in words, to errors)."""
    p = image_path(path)
    if not p.is_file():
        errors.append(f"{name}: {key} picture {path} not found (a shared profile needs its pictures too)")
        return False
    try:
        with Image.open(p) as img:
            img.verify()
    except Exception:
        errors.append(f"{name}: {key} picture {path} isn't a PNG or JPG picture")
        return False
    return True


def _build_ids(chars):
    import charbuild
    return set(range(charbuild.STOCK_IDS)) | {_cid(e["id"]) for e in chars if e.get("id") is not None}


def check(option, chars=(), defaults=True):
    """The problems with a "captains" option, each in plain words ([] = it builds). chars: the build's definitions and
    stock entries (the new characters it builds are the ones there)."""
    return plan(option, chars, _build_ids(chars), defaults)["errors"]


def notes(option, chars=(), defaults=True):
    """Warnings for an option that builds: placeholder art, more than TESTED_CAPTAINS, a figure off screen."""
    return plan(option, chars, _build_ids(chars), defaults)["warnings"]


def candidates(option=None, chars=(), defaults=True):
    """For the editor's "add a captain" list: every character of the build with {"name", "id", "stock", "eligible",
    "stars", "why"} (why: what stops it, or "" / a note; stars: has captain star moves). Those with captain star moves
    come first (Nick: anyone can be a captain, "put the ones with captain star moves at the top")."""
    from sluggers_data import CHAR_NAMES
    import charbuild
    p = plan(option, chars, None, defaults, swings=False)
    listed = {c["id"] for c in p["captains"]}
    gone = {STOCK_TABLE[i] for i in p.get("removed", ())}          # removed stock captains: Add puts them back
    new = renames(chars, defaults)
    pool = [(cid, new.get(cid, CHAR_NAMES[cid]), True) for cid in range(charbuild.STOCK_IDS)]
    pool += [(_cid(e["id"]), e.get("name", ""), False) for e in chars if e.get("id") is not None and not e.get("stock")]
    out = []
    for cid, name, stock in pool:
        name = KNOWN[cid]["name"] if cid in KNOWN else name
        why = "" if cid in gone else "already a captain" if cid in STOCK_TABLE else "in the list" if cid in listed else ""
        stars = _has_star_swing(cid, chars, defaults)
        if why:
            note = why
        elif cid in gone:
            note = "removed: Add puts them back"
        elif not stars:
            note = words()["no_swing_short"]
        elif None in _art_files(dict(art=_art_of({}, cid, name)["art"])).values():
            note = "no captain art: drawn from their 3D model"
        else:
            note = ""
        out.append(dict(name=name, id=cid, stock=stock, eligible=not why, stars=stars, why=note, removed=cid in gone))
    return sorted(out, key=lambda c: not c["stars"])            # (stable: the build's order within each)


def canvas():
    """The captain-select lineup's coordinates, for an editor. Positions are layout units (the first key of a captain's
    node in element 0x34); a larger y draws in front (the draw order sorts by y) and the cursor moves by x. frame: the
    screen a 4:3 TV shows (x0, y0, x1, y1); view_x: what a widescreen one shows across."""
    return {"view_x": VIEW_X, "view_y": VIEW_Y, "frame": FRAME, "stock_y": (min(STOCK_NODE_Y), max(STOCK_NODE_Y)),
            "to_screen": (312.6, 2.036),        # screen px = 312.6 + 2.036 x in Nick's 1920-wide screenshots
            "max_captains": MAX_CAPTAINS, "min_captains": MIN_CAPTAINS, "tested": TESTED_CAPTAINS}


def _respaced(p):
    """Whether a build moves the lineup (lineup_x / lineup_y): a custom captain or a removed stock one. Without, the
    game's own nodes stay where they are (only the option's positions move figures: _captain_file)."""
    return bool(p["captains"] or p.get("removed"))


def lineup_y(p):
    """{captain index: y} of a plan: its node's y (an added captain: its "y", else node_from's node) + its dy."""
    ys = {}
    for i in range(len(p["table"])):
        c = next((c for c in p["captains"] if c["index"] == i), None)
        if c is not None and i >= STOCK:
            y0 = c["y"] if "y" in c else STOCK_NODE_Y[c["node_from"]]
        else:
            y0 = STOCK_NODE_Y[STOCK_FRAMES[p.get("geo", {}).get(i, i)]]
        ys[i] = y0 + p["dy"].get(i, 0)
    return ys


def _layout(p):
    """({index: x}, {index: y}) where a plan's build puts each captain before its positions: the auto layout, or the
    game's own nodes when nothing is respaced."""
    if not _respaced(p):
        n = len(p["table"])
        return ({i: STOCK_NODE_X[STOCK_FRAMES[i]] for i in range(n)}, {i: STOCK_NODE_Y[STOCK_FRAMES[i]] for i in range(n)})
    return lineup_x(p["order"], p["visible"], p["nudge"]), lineup_y(p)


def default_positions(option=None, chars=(), defaults=True):
    """{name: (x, y)}: where an option's captains stand without its positions: the editor's reset."""
    p = plan(dict(option or DEFAULT_OPTION, positions={}), chars, None, defaults, swings=False)
    assert not p["errors"], "; ".join(p["errors"])
    xs, ys = _layout(p)
    return {_display(p, i): (xs[i], ys[i]) for i in range(len(p["table"]))}


def _display(p, i):
    c = next((c for c in p["captains"] if c["index"] == i), None)
    return c["name"] if c else p["stock_names"][p.get("stock_slots", {}).get(i, i)]


def figure_half(p, i):
    """(node scale x, y, sprite half width, half height) of captain i of a plan: a slot's stock element and node (a moved
    stock captain brings its own; an added captain has COPY_ELEMENT's sprite and its node_from's node)."""
    c = next((c for c in p["captains"] if c["index"] == i), None)
    if i >= STOCK:
        g, node = COPY_ELEMENT - 0x1E, c["node_from"]
        return (*STOCK_NODE_SCALE[STOCK_FRAMES.index(node)], *STOCK_SPRITE_HALF[g])
    g = p.get("geo", {}).get(i, i)
    return (*STOCK_NODE_SCALE[g], *STOCK_SPRITE_HALF[g])


def figures(option=None, chars=(), game=None, defaults=True):
    """The lineup as the game will show it, for an editor: per captain {"name", "index", "x", "y", "visible": (left,
    right) of the body relative to x (the auto layout's), "image": RGBA figure (its whole sprite), "box": (x0, y0, x1,
    y1) the layout units the game stretches the image over (centred on x, y: canvas()'s frame), "scale" / "anchor":
    layout units per image px across and the image px at (x, y), "kind": "stock" (the game's art: read from `game`,
    the player's clean game folder; a placeholder without it), "new" (our or the player's art), "drawn" (drawn from
    its 3D model) or "placeholder" (none)}, left to right in the auto layout's order. The option's positions are
    applied."""
    import captain_art
    global GAME
    GAME = game if game is not None else GAME
    p = plan(option, chars, None, defaults, swings=False)
    assert not p["errors"], "; ".join(p["errors"])
    xs, ys = _layout(p)
    for i, (x, y) in p["positions"].items():
        xs[i], ys[i] = x if x is not None else xs[i], y if y is not None else ys[i]
    stock_file = _stock_file18(game) if game is not None else None
    out = []
    for i in p["order"]:
        c = next((c for c in p["captains"] if c["index"] == i), None)
        name = _display(p, i)
        if c is None:
            kind = "stock"
            src = p.get("stock_slots", {}).get(i, i)
            img = _stock_figure(stock_file, src) if stock_file else captain_art.placeholder(name, "lineup")
        else:
            images, missing = art(c)
            img, kind = images["lineup"], ("placeholder" if "lineup" in missing else "drawn" if "lineup" in
                                           drawn_keys(c) else "new")
        nsx, nsy, hw, hh = figure_half(p, i)
        w, h = 2 * hw * nsx, 2 * hh * nsy
        box = (xs[i] - w / 2, ys[i] - h / 2, xs[i] + w / 2, ys[i] + h / 2)
        out.append(dict(name=name, index=i, x=xs[i], y=ys[i], visible=p["visible"][i], image=img, box=box,
                        scale=w / img.width, anchor=(img.width / 2, img.height / 2), kind=kind))
    return out


def _stock_file18(game):
    return _stock_file(str(game), FILE_CAPTAIN)


_GAME_FILES = {}


def _stock_file(game, index):
    """Dir 119 file `index` of the player's clean game (kept: the editor asks again on every redraw)."""
    if (game, index) not in _GAME_FILES:
        import dtna_toc
        from dol import Dol
        off, n = dtna_toc.toc(Dol(Path(game) / "sys/main.dol"))[119][index]
        with open(Path(game) / "files/dt_na.dat", "rb") as f:
            f.seek(off)
            _GAME_FILES[game, index] = f.read(n)
    return _GAME_FILES[game, index]


def team_art(option=None, chars=(), name=None, game=None, defaults=True):
    """A captain's team logo and emblem as the game will show them, for the editor: {"name", "index", "stock": a
    stock captain in its own slot, "logo" / "emblem": RGBA at 153 x 54 / 90 x 90, "kinds": {"logo" / "emblem":
    "game" (read from `game`, the player's clean game), "yours" (the option's picture), "ours" (our art), "drawn"
    (drawn from its 3D model) or "stand-in"
    (the placeholder, also a stock one's without `game`)}}. name: as figures() shows it; None if it isn't a captain."""
    global GAME
    GAME = game if game is not None else GAME
    p = plan(option, chars, None, defaults, swings=False)
    assert not p["errors"], "; ".join(p["errors"])
    i = next((i for i in range(len(p["table"])) if _display(p, i) == name), None)
    if i is None:
        return None
    c = next((c for c in p["captains"] if c["index"] == i), None)
    out = dict(name=name, index=i, stock=c is None, kinds={})
    if c is not None:
        images, missing = art(c)
        drawn = drawn_keys(c)
        for key in TEAM_ART:
            out[key] = images[key]
            out["kinds"][key] = ("yours" if c.get(key + "_file") is not None else "stand-in" if key in missing
                                 else "drawn" if key in drawn else "ours")
        return out
    own = p["stock_art"].get(i, {})
    src = out["stock_index"] = p.get("stock_slots", {}).get(i, i)   # (a moved stock captain: its own rows)
    blob = _stock_file(str(game), FILE_LOGO) if game is not None else None
    for key, row in (("logo", 0x0C + src), ("emblem", src)):
        if key in own:
            out[key], out["kinds"][key] = player_image(own[key], key), "yours"
        elif blob is not None:
            from item_abilities import row_image
            out[key], out["kinds"][key] = row_image(blob, row), "game"
        else:
            out[key], out["kinds"][key] = captain_art.placeholder(name, key), "stand-in"
    return out


def _stock_figure(blob, index):
    """A stock captain's lineup figure from the game's file 18 (its element 0x1E + index's figure row, CI8)."""
    import layout
    from layout import stock_icon
    L = layout.Layout(blob)
    return stock_icon(blob, L.key_ref(0x1E + index, L.nodes(0x1E + index)[0][0]))


STAR_MOVE_FIELDS = (0x07, 0x08, 0x09)   # stats row: captain flag, star pitch, star swing


def demoted():
    """{stock captain id: the captain in its slot, or None} for this build's replaced slots and removed captains."""
    out = {c["replaces"]: c["id"] for c in REPLACED if c.get("replaces") is not None}
    out.update({STOCK_TABLE[i]: None for i in REMOVED})
    return out


def stat_edits(dol):
    """A stock captain replaced in this build is no captain any more: its captain flag, star pitch and star swing
    (+7 / +8 / +9) are 0 (Nick: Wario and Waluigi, 2026-09-24; any slot now). One not replaced keeps them. Runs where
    charbuild's stock stat edits run (before the stats table is copied), whenever captains is on. Returns log lines."""
    import charbuild
    out = []
    for sid, cid in demoted().items():
        row = 0x806CE9A0 + charbuild.STATS_HEADER + sid * charbuild.STATS_ROW
        assert int.from_bytes(dol.read(row, 2), "big") == sid, f"stats row 0x{sid:02X}"
        for off in STAR_MOVE_FIELDS:
            dol.write(row + off, b"\0")
        out.append(f"0x{sid:02X} (removed)" if cid is None else f"0x{sid:02X} (0x{cid:02X} took slot {STOCK_TABLE.index(sid)})")
    return ["captains: no longer captains (+7/+8/+9 = 0): " + ", ".join(out)] if out else []


def kept_star_moves():
    """Stock captains our roster replaces by default who keep their slot in this build (its captain isn't built, or
    captains is off): they keep their star moves, but a new character built on one copies them cleared (charbuild
    star_move_edits), as a new character built on a replaced one copies the cleared row."""
    return sorted({c["replaces"] for c in ALL_CAPTAINS if c["index"] < STOCK} - set(demoted()))


def configure(ids=None, option=None, chars=(), defaults=True):
    """The custom captains of this build: ALL_CAPTAINS whose character id is in `ids` (charbuild: the stock ids and
    the new characters built; () with captains off), None = all of them (a full roster; the module's own state).
    option: the "captains" option (plan(); chars / defaults as there) instead of ALL_CAPTAINS: its captains, order
    and positions; a problem (check()) raises ValueError.
    A replacing captain that is left out leaves its slot to the stock captain (Wario stays captain 8); added ones
    left out close up (Luma is index 12 without Rosalina). Rebinds NEW_CAPTAINS, ADDED, REPLACED, COUNT, IMMS and
    the lineup (LINEUP_ORDER, VISIBLE, LINEUP_NUDGE, LINEUP_DY), which add_captain / patch_layouts,
    star_move_labels, item_abilities and pauline_chance read. Returns the captains left out (their dicts)."""
    global NEW_CAPTAINS, ADDED, REPLACED, COUNT, IMMS, LINEUP_ORDER, VISIBLE, LINEUP_NUDGE, LINEUP_DY, POSITIONS
    global STOCK_RENAMED, STOCK_ART, REMOVED, MOVED, GEO, TAIL, COMPACT, TABLE_SHOWN
    new_names = renames(chars, defaults)
    STOCK_ART = {}
    REMOVED, MOVED, GEO, TAIL, COMPACT, TABLE_SHOWN = [], {}, {i: i for i in range(STOCK)}, [], False, None
    if option is not None:
        p = plan(option, chars, ids, defaults)
        if p["errors"]:
            raise ValueError("captains: " + "; ".join(p["errors"]))
        NEW_CAPTAINS = p["captains"]
        ADDED = [c for c in NEW_CAPTAINS if c["index"] >= STOCK]
        REPLACED = [c for c in NEW_CAPTAINS if c["index"] < STOCK]
        COUNT = len(p["table"])
        LINEUP_ORDER, VISIBLE, LINEUP_NUDGE, LINEUP_DY = p["order"], p["visible"], p["nudge"], p["dy"]
        POSITIONS = p["positions"]
        STOCK_ART = p["stock_art"]
        REMOVED, MOVED, GEO, TAIL = p["removed"], p["moved"], p["geo"], p["tail"]
        COMPACT, TABLE_SHOWN = COUNT < STOCK, list(p["table"])
        IMMS = imms()
        STOCK_RENAMED = _stock_renamed(new_names, p["stock_slots"])
        return []
    POSITIONS = {}
    keep = [c for c in ALL_CAPTAINS if ids is None or c["id"] in ids]
    index = {i: i for i in range(STOCK)}                    # full-roster index -> this build's
    for k, c in enumerate(c for c in keep if c["index"] >= STOCK):
        index[c["index"]] = STOCK + k
    NEW_CAPTAINS = [c if index[c["index"]] == c["index"] else dict(c, index=index[c["index"]]) for c in keep]
    NEW_CAPTAINS = [c if (current_name(c["id"], chars, defaults) or c["name"]) == c["name"]   # renamed: its name
                    else dict(c, name=current_name(c["id"], chars, defaults)) for c in NEW_CAPTAINS]
    ADDED = [c for c in NEW_CAPTAINS if c["index"] >= STOCK]
    REPLACED = [c for c in NEW_CAPTAINS if c["index"] < STOCK]
    COUNT = STOCK + len(ADDED)
    stock_kept = {c["index"] for c in ALL_CAPTAINS if c["index"] < STOCK} - {c["index"] for c in REPLACED}
    LINEUP_ORDER = [index[i] for i in _FULL["order"] if i in index]
    VISIBLE = {index[i]: STOCK_VISIBLE[i] if i in stock_kept else v for i, v in _FULL["visible"].items() if i in index}
    LINEUP_NUDGE = {index[i]: v for i, v in _FULL["nudge"].items() if i in index and i not in stock_kept}
    LINEUP_DY = {index[i]: v for i, v in _FULL["dy"].items() if i in index and i not in stock_kept}
    IMMS = imms()
    STOCK_RENAMED = _stock_renamed(new_names)
    return [c for c in ALL_CAPTAINS if c["id"] not in {k["id"] for k in keep}]


def _stock_renamed(new_names, slots=None):
    """{slot: new name} for the stock captains on captain select (slots: {slot: stock index}; None: each in its own
    slot, the replaced ones left out) that are renamed."""
    if slots is None:
        taken = {c["index"] for c in REPLACED}
        slots = {i: i for i in range(STOCK) if i not in taken}
    return {j: new_names[STOCK_TABLE[i]] for j, i in slots.items() if STOCK_TABLE[i] in new_names}


def src(slot):
    """The stock slot whose art, tables and lineup node slot `slot` starts from (GEO: a moved stock captain's own, a
    moved new captain's first slot; else its own)."""
    return GEO.get(slot, slot)


def table():
    """This build's captain table: captain index -> character id (STOCK_TABLE with the configured captains; the ones
    on captain select, not TAIL)."""
    if TABLE_SHOWN is not None:
        return list(TABLE_SHOWN)
    out = list(STOCK_TABLE)
    for c in REPLACED:
        out[c["index"]] = c["id"]
    return out + [c["id"] for c in ADDED]


def index_of(cid):
    """A character's captain index in this build (quickboot's captain_index="captains")."""
    t = table()
    assert cid in t, f"0x{cid:02X} is not a captain in this build (captains: {', '.join(f'0x{c:02X}' for c in t)})"
    return t.index(cid)


COPY_ELEMENT = 0x22                  # captain 4's element: node 0 = figure keys, node 1 = glow keys

FILE_CAPTAIN, FILE_LOGO = 18, 1
POS_ELEMENT = 0x34
STOCK_ELEMENTS, STOCK_ROWS_18, STOCK_ROWS_1 = 77, 181, 128
PAGE_W, PAGE_H = 512, 384


def rows_18(k):
    """(portrait, lineup, glow, name) rows of NEW_CAPTAINS[k] in file 18."""
    return tuple(range(STOCK_ROWS_18 + 4 * k, STOCK_ROWS_18 + 4 * k + 4))


def rows_1(k):
    """(logo, emblem) rows of NEW_CAPTAINS[k] in file 1."""
    return STOCK_ROWS_1 + 2 * k, STOCK_ROWS_1 + 2 * k + 1


def element(c):
    """The lineup element an added captain gets (replaced ones keep 0x1E + index)."""
    return STOCK_ELEMENTS + ADDED.index(c)


CAPTAINS, FRAMES, PORTRAITS = 0x806318A8, 0x8062C9F0, 0x80631D30
STAR_GAINS, STAR_ROW = 0x8062BD50, 0x52   # per-captain star meter gains (s16 per event), one lis/subi at 0x80180880
PREF_BAT, PREF_FIELD = 0x80623428, 0x80623440
CHANCE, CHANCE_ROW = 0x8062E6A0, 0x38     # per-captain chance rows (pauline_chance.TABLE / ROW)

def imms():
    """(address, old immediate, new) for COUNT / ADDED."""
    return (
        (0x802CDF94, 0x0B, COUNT - 1),   # lineup builder: captains 11..0
        (0x802CDFB0, 2, 3),         # ... reverse lookup in FRAMES, 2 x 6
        (0x802CE1FC, 0x0C, COUNT), (0x802CE288, 0x0C, COUNT), (0x802CE2B8, 0x0C, COUNT),   # draw-order sort
        (0x802C95DC, 0x0C, COUNT), (0x802C9764, 0x0C, COUNT),   # cursor to the nearest captain left / right
        (0x802CBBB0, 0x0B, COUNT - 1), (0x802CC7B8, 0x0B, COUNT - 1),   # random captain 0..11
        (0x802CBD70, 0x0C, COUNT),   # nearest free captain when both sides pick one
        (0x802C9A78, 0x0C, COUNT), (0x802C9B48, 0x0C, COUNT),   # portrait widget
        (0x802C9F9C, 0x0C, COUNT), (0x802CA018, 0x0C, COUNT),   # name widget
        (0x80069F38, 2, 3),         # auto batting order: captain lookup 2 x 6
        (0x8006B29C, 2, 3),         # auto fielding: captain lookup 2 x 6
        (0x802CED48, 0xA4, 0xA4 + 4 * len(ADDED)),   # captain-select task allocation
    )


IMMS = imms()
assert COUNT <= 18, "the 2 x 6 lookups run 3 x 6"
# (site, reg, captain index register, stock offset, row of NEW_CAPTAINS[k] or None for the element):
# `addi reg, idx, offset` -> an added captain's own row / element
ADDI_HOOKS = ((0x802CE088, "r0", "r3", 0x1E, None),
              (0x802C9FA4, "r0", "r3", 0xA6, lambda k: rows_18(k)[3]),
              (0x802CA020, "r0", "r3", 0xA6, lambda k: rows_18(k)[3]),
              (0x80395C74, "r3", "r23", 0x0C, lambda k: rows_1(k)[0]))
EMBLEM_STORE = 0x80395D4C            # sth r23,-0x88(r31): emblem row = captain index


# The draw-order sort (FUN_802CE1E8) keeps its COUNT (index, in front) pairs on its stack at r1+0x68 and the merge
# sort's scratch (FUN_802CE2E4, COUNT x 8 bytes) at r1+0x8, in a 0xE0 frame sized for 12. From 13 the scratch runs into
# the pairs, from 14 the pairs into the saved r29..r31, and from 16 into the saved LR: 18 captains jumped to 0 as
# captain select opened (captain-art-1, 2026-09-29: "Attempted to fetch instruction from invalid address 0x0", LR 0,
# r29 0). With more than 12 the frame grows to SORT_FRAME: scratch 0x8..0x98, pairs 0x98..0x128, r29..r31 and LR above.
SORT_FUNC, SORT_FRAME, SORT_PAIRS = 0x802CE1E8, 0x140, 0x98


def sort_frame_edits():
    """(address, old word, new word) growing the draw-order sort's stack frame (see SORT_FRAME)."""
    from ppc import d_form
    F, P = SORT_FRAME, SORT_PAIRS
    stwu, stw, lwz, addi = 37, 36, 32, 14
    return ((0x802CE1E8, d_form(stwu, 1, 1, -0xE0), d_form(stwu, 1, 1, -F)),
            (0x802CE1F8, d_form(stw, 0, 1, 0xE4), d_form(stw, 0, 1, F + 4)),
            (0x802CE200, d_form(addi, 6, 1, 0x68), d_form(addi, 6, 1, P)),
            (0x802CE208, d_form(stw, 31, 1, 0xDC), d_form(stw, 31, 1, F - 4)),
            (0x802CE20C, d_form(stw, 30, 1, 0xD8), d_form(stw, 30, 1, F - 8)),
            (0x802CE210, d_form(stw, 29, 1, 0xD4), d_form(stw, 29, 1, F - 12)),
            (0x802CE278, d_form(addi, 3, 1, 0x68), d_form(addi, 3, 1, P)),
            (0x802CE290, d_form(addi, 31, 1, 0x68), d_form(addi, 31, 1, P)),
            (0x802CE2C0, d_form(lwz, 0, 1, 0xE4), d_form(lwz, 0, 1, F + 4)),
            (0x802CE2C4, d_form(lwz, 31, 1, 0xDC), d_form(lwz, 31, 1, F - 4)),
            (0x802CE2C8, d_form(lwz, 30, 1, 0xD8), d_form(lwz, 30, 1, F - 8)),
            (0x802CE2CC, d_form(lwz, 29, 1, 0xD4), d_form(lwz, 29, 1, F - 12)),
            (0x802CE2D4, d_form(addi, 1, 1, 0xE0), d_form(addi, 1, 1, F)))


assert 0x8 + 8 * 18 <= SORT_PAIRS and SORT_PAIRS + 8 * 18 <= SORT_FRAME - 12


def _imm(dol, addr, old, new):
    w = dol.u32(addr)
    assert w & 0xFFFF == old, f"0x{addr:08X}: {w:08X}, expected immediate {old:#x}"
    dol.w32(addr, (w & 0xFFFF0000) | new)


def _addi(rt, ra, imm):
    return Asm(0).addi(rt, ra, imm).assemble_word()


def add_captain(dol, code, data, chars=(), preview=None):
    """preview: character ids to put in captain slots 0.. (a model-testing build: confirming a captain
    loads its character's 3D model; the 2D art stays the slot's own)."""
    import hilo_refs
    from charbuild import relocate
    pairs = list(hilo_refs.pairs())
    log = []

    def move(old, old_len, blob, name):
        new = data.put(blob, align=4)
        n = relocate(dol, pairs, old, old_len, new, name=f"captain {name}")
        log.append(f"captain {name}: {n} refs -> 0x{new:08X}")

    table = list(struct.unpack(f">{STOCK}i", dol.read(CAPTAINS, 4 * STOCK)))
    portraits = list(struct.unpack(f">{2 * STOCK}h", dol.read(PORTRAITS, 4 * STOCK)))
    assert tuple(table) == STOCK_TABLE, "the captain table is not stock"
    table = [table[src(j)] for j in range(STOCK)]                  # (MOVED: a stock captain in another slot)
    portraits = [v for j in range(STOCK) for v in portraits[2 * src(j):2 * src(j) + 2]]
    for k, c in enumerate(NEW_CAPTAINS):
        assert c["id"] not in STOCK_TABLE or c.get("replaces") == c["id"], f"0x{c['id']:02X} is a captain"
        if c in REPLACED:
            assert c.get("replaces") is None or COMPACT or table[c["index"]] == c["replaces"], \
                f"slot {c['index']} is 0x{table[c['index']]:02X}"
            table[c["index"]] = c["id"]
            portraits[2 * c["index"]:2 * c["index"] + 2] = [rows_18(k)[0], -1]
        else:
            table.append(c["id"])
            portraits += [rows_18(k)[0], -1]
    if preview:
        assert len(preview) <= len(table), f"at most {len(table)} preview characters"
        table[:len(preview)] = preview
        log.append("captain preview: " + ", ".join(f"slot {i} = 0x{c:02X}" for i, c in enumerate(preview)))
    move(CAPTAINS, 4 * STOCK, struct.pack(">18i", *(table + [-1] * (18 - len(table)))), "table")
    frames = dol.read(FRAMES, STOCK)
    assert list(frames) == STOCK_FRAMES, "captain -> lineup node table is not stock"
    if COMPACT:                          # the lineup builder draws nodes COUNT-1..0: captain j stands on node j
        frames = bytes(range(STOCK))     # (_captain_file puts each slot's node there)
    move(FRAMES, STOCK, frames + bytes(range(STOCK, COUNT)) + b"\xFE" * (18 - max(COUNT, STOCK)), "lineup frames")
    move(PORTRAITS, 4 * STOCK, struct.pack(f">{len(portraits)}h", *portraits), "portraits")
    own = [c for c in REPLACED if "prefs_from" in c]                   # a replacing captain given its own prefs
    for addr, name in ((PREF_BAT, "batting prefs"), (PREF_FIELD, "fielding prefs")):
        stock = dol.read(addr, 2 * STOCK)
        prefs = bytearray(b"".join(stock[2 * src(j):2 * src(j) + 2] for j in range(STOCK)))
        for c in own:
            prefs[2 * c["index"]:2 * c["index"] + 2] = stock[2 * c["prefs_from"]:2 * c["prefs_from"] + 2]
        prefs = bytes(prefs)
        move(addr, 2 * STOCK, prefs + b"".join(stock[2 * c["prefs_from"]:2 * c["prefs_from"] + 2] for c in ADDED), name)
    # star gains (FUN_80180820: the meter's gain for an event is row[captain index] of 0x52-byte rows, stock 12 rows
    # up to 0x8062C128). Added indices read past it into the float table there, so every gain was huge and a
    # Rosalina or Luma team sat at 5 stars (Nick). Their rows copy their prefs_from captain's.
    stock = dol.read(STAR_GAINS, STAR_ROW * STOCK)
    gains = bytearray(b"".join(stock[STAR_ROW * src(j):STAR_ROW * (src(j) + 1)] for j in range(STOCK)))
    for c in own:
        gains[STAR_ROW * c["index"]:STAR_ROW * (c["index"] + 1)] = stock[STAR_ROW * c["prefs_from"]:STAR_ROW * (c["prefs_from"] + 1)]
    gains = bytes(gains)
    move(STAR_GAINS, STAR_ROW * STOCK, gains + b"".join(
        stock[STAR_ROW * c["prefs_from"]:STAR_ROW * (c["prefs_from"] + 1)] for c in ADDED), "star gains")
    if COMPACT:                          # the team chance table (pauline_chance.TABLE, 12 rows of 0x38, read by captain
        rows = [dol.read(CHANCE + CHANCE_ROW * i, CHANCE_ROW) for i in range(STOCK)]   # index), in place
        for j in range(STOCK):
            dol.write(CHANCE + CHANCE_ROW * j, rows[src(j)])
    if COMPACT:
        log.append(f"captains: {COUNT} on captain select" + "".join(
            f", slot {j} <- {STOCK_CAPTAIN_NAMES[i]}" for j, i in sorted(MOVED.items()))
            + "; removed (kept after them for the game's 12-captain loops): "
            + ", ".join(STOCK_CAPTAIN_NAMES[STOCK_TABLE.index(c)] for c in TAIL))

    for addr, old, new in IMMS:
        _imm(dol, addr, old, new)
    if COUNT > STOCK:                    # the draw-order sort's stack frame (SORT_FRAME)
        for addr, was, now in sort_frame_edits():
            assert dol.u32(addr) == was, f"0x{addr:08X}: {dol.u32(addr):08X}, expected {was:08X}"
            dol.w32(addr, now)

    for site, rt, ra, off, row in ADDI_HOOKS:
        a = Asm(code.here)
        for c in ADDED:
            k = NEW_CAPTAINS.index(c)
            a.cmpwi(ra, c["index"]).bne(f"not{k}").li(rt, element(c) if row is None else row(k)).b(site + 4)
            a.label(f"not{k}")
        a.addi(rt, ra, off).b(site + 4)
        assert dol.u32(site) == _addi(rt, ra, off), f"0x{site:08X}"
        dol.w32(site, Asm(site).b(code.put(a.assemble(), 4)).assemble_word())
    a = Asm(code.here)
    for c in ADDED:
        k = NEW_CAPTAINS.index(c)
        a.cmpwi("r23", c["index"]).bne(f"not{k}").li("r12", rows_1(k)[1]).sth("r12", -0x88, "r31").b(EMBLEM_STORE + 4)
        a.label(f"not{k}")
    a.sth("r23", -0x88, "r31").b(EMBLEM_STORE + 4)
    assert dol.u32(EMBLEM_STORE) == Asm(0).sth("r23", -0x88, "r31").assemble_word()
    dol.w32(EMBLEM_STORE, Asm(EMBLEM_STORE).b(code.put(a.assemble(), 4)).assemble_word())
    names = ", ".join(f"{c['index']} {c['name']}" for c in NEW_CAPTAINS)
    log.append(f"captains: {COUNT} ({names}), {len(IMMS)} bounds, {len(ADDI_HOOKS) + 1} hooks"
               + (f", draw-order sort frame 0x{SORT_FRAME:X}" if COUNT > STOCK else ""))
    return log


def art(c, game=None):
    """({"portrait", "lineup", "logo", "emblem"} images for a captain, [keys that are placeholders]): its art files,
    and where one is missing the art drawn from its 3D model (drawn_art), else a placeholder."""
    out, missing = {}, []
    for key, p in _art_files(c).items():
        if c.get(key + "_file") is not None:
            out[key] = player_image(p, key)                  # the player's: fitted keeping its shape
        elif p is not None:
            out[key] = captain_art.fit(Image.open(p).convert("RGBA"), key)
        elif (drawn := drawn_art(c, game)) is not None:
            out[key] = drawn[key]
        else:
            out[key] = captain_art.placeholder(c["name"], key)
            missing.append(key)
    return out, missing


def drawn_keys(c):
    """The art a captain gets drawn from its model: the files it has none of (when its model can be drawn)."""
    if drawn_art(c) is None:
        return []
    return [k for k, p in _art_files(c).items() if p is None]


def _uv(page_size, rect):
    w, h = page_size
    x0, y0, x1, y1 = rect
    return x0 / w, y0 / h, x1 / w, y1 / h


def _set_row(L, row, page, uv):
    u1, v1, u2, v2 = uv
    L.rows[row][:] = struct.pack(">HH4f", page, 0, v1, u1, v2, u2)


def _renamed_plates(L, data):
    """Renamed stock captains (STOCK_RENAMED): each one's name plate drawn in its own stock colours (plate_style of its
    stock row 0xA6 + index) on one page added to file 18, and that row repointed. Nothing else changes."""
    if not STOCK_RENAMED:
        return
    from item_abilities import row_image
    w, h = captain_art.NAME_SIZE
    pw, ph = w + (-w % 4), 32
    order = sorted(STOCK_RENAMED)
    page_img = Image.new("RGBA", (pw, ph * len(order)), (0, 0, 0, 0))
    for k, i in enumerate(order):
        style = captain_art.plate_style(row_image(data, 0xA6 + src(i)))
        page_img.paste(captain_art.name_plate(STOCK_RENAMED[i], style), (0, ph * k))
    size = page_img.size
    page = L.add_texture(captain_art.rgb5a3(page_img), *size, captain_art.GX_RGB5A3)
    for k, i in enumerate(order):
        _set_row(L, 0xA6 + i, page, _uv(size, (0, ph * k, w, ph * k + h)))


def _captain_file(data):
    import layout
    L = layout.Layout(data)
    assert len(L.elements) == STOCK_ELEMENTS and len(L.rows) == STOCK_ROWS_18, "file 18 is not stock"
    if not NEW_CAPTAINS and not COMPACT:                     # no custom captain (captains off, or the vanilla "list":
        _renamed_plates(L, data)                             # []): renamed stock captains' plates, and the option's
        for cap, (px, py) in sorted(POSITIONS.items()):     # positions move just those figures (the others stay
            keys = L.nodes(POS_ELEMENT)[STOCK_FRAMES[cap]]   # where the game has them: no respacing)
            x0, y0 = struct.unpack_from(">hh", L.elements[POS_ELEMENT], keys[0] + 8)
            for key in keys:
                L.move_key(POS_ELEMENT, key, 0 if px is None else px - x0, 0 if py is None else py - y0)
        return L.to_bytes()
    stock_pos = L.node_blobs(POS_ELEMENT)
    assert len(stock_pos) == STOCK
    pos = list(stock_pos)
    if COMPACT:          # slot j: its source slot's element, name plate and node (on node j: add_captain's frames 0..11)
        els, plates = [bytes(L.elements[0x1E + i]) for i in range(STOCK)], [bytes(L.rows[0xA6 + i]) for i in range(STOCK)]
        for j in range(STOCK):
            L.elements[0x1E + j] = bytearray(els[src(j)])
            L.rows[0xA6 + j][:] = plates[src(j)]
        pos = [stock_pos[STOCK_FRAMES[src(j)]] for j in range(STOCK)]
    size = (PAGE_W, PAGE_H)
    for k, c in enumerate(NEW_CAPTAINS):
        images, _ = art(c)
        image, rects, _ = captain_art.build_page(images["portrait"], images["lineup"], c["name"], size)
        page = L.add_texture(image, PAGE_W, PAGE_H, captain_art.GX_RGB5A3)
        r_portrait, r_lineup, r_glow, r_name = rows_18(k)
        for row, key in zip(rows_18(k), ("portrait", "lineup", "glow", "name")):
            assert L.add_row(page, *_uv(size, rects[key])) == row
        if c in REPLACED:
            el = 0x1E + c["index"]                           # the slot's element and name row, repointed
            _set_row(L, 0xA6 + c["index"], page, _uv(size, rects["name"]))
        else:
            assert L.add_element(bytes(L.elements[COPY_ELEMENT])) == element(c)
            el = element(c)
        figure, glow = L.nodes(el)[:2]
        for key in figure:
            L.set_key_ref(el, key, r_lineup)
        for key in glow:
            L.set_key_ref(el, key, r_glow)
        if c in ADDED:                                       # its lineup position: node index of element 0x34
            pos.append(stock_pos[c["node_from"]])
    L.set_nodes(POS_ELEMENT, pos)
    if COMPACT:
        for j in range(STOCK):
            for key in L.nodes(POS_ELEMENT)[j]:
                L.set_key_ref(POS_ELEMENT, key, 0x1E + j)
    for c in ADDED:
        for key in L.nodes(POS_ELEMENT)[c["index"]]:
            L.set_key_ref(POS_ELEMENT, key, element(c))
    # respace: node of captain i is STOCK_FRAMES[i] (added captains: their index); keys keep their offsets
    assert sorted(LINEUP_ORDER) == list(range(COUNT))
    ys = {c["index"]: c["y"] for c in ADDED if "y" in c}
    xs = lineup_x()
    for n, cap in enumerate(LINEUP_ORDER):
        node = cap if COMPACT or cap >= STOCK else STOCK_FRAMES[cap]
        keys = L.nodes(POS_ELEMENT)[node]
        x0, y0 = struct.unpack_from(">hh", L.elements[POS_ELEMENT], keys[0] + 8)
        x = xs[cap]
        dy = (ys[cap] - y0 if cap in ys else 0) + LINEUP_DY.get(cap, 0)
        px, py = POSITIONS.get(cap, (None, None))                      # the option's positions: where it stands
        x, dy = (x if px is None else px), (dy if py is None else py - y0)
        for key in keys:
            L.move_key(POS_ELEMENT, key, x - x0, dy)
    _renamed_plates(L, data)                                 # (its page last: the others keep their numbers)
    return L.to_bytes()


LOGO_BAND = (256, 90)                # file 1: per captain, the logo (153 x 54) at x 0 and the emblem (90 x 90) at x 160
LOGO_RECTS = ((0, 0, 153, 54), (160, 0, 250, 90))
GX_CI8, TL_RGB5A3 = 9, 2


def logo_band(c):
    """A captain's file-1 band (RGBA, LOGO_BAND): logo and emblem at their stock sizes."""
    images, _ = art(c)
    logo = images["logo"].resize((153, 54)) if images["logo"].size != (153, 54) else images["logo"]
    emblem = images["emblem"].resize((90, 90)) if images["emblem"].size != (90, 90) else images["emblem"]
    band = Image.new("RGBA", LOGO_BAND, (0, 0, 0, 0))
    band.paste(logo, (0, 0))
    band.paste(emblem, (160, 0))
    return band


def rgb5a3_value(r, g, b, a):
    """One pixel as GX RGB5A3 (captain_art.rgb5a3's rounding)."""
    if a >= 0xE0:
        return 0x8000 | (r >> 3) << 10 | (g >> 3) << 5 | b >> 3
    return (a >> 5) << 12 | (r >> 4) << 8 | (g >> 4) << 4 | b >> 4


def rgb5a3_rgba(v):
    if v & 0x8000:
        return ((v >> 10 & 31) * 255 // 31, (v >> 5 & 31) * 255 // 31, (v & 31) * 255 // 31, 255)
    return ((v >> 8 & 15) * 17, (v >> 4 & 15) * 17, (v & 15) * 17, (v >> 12 & 7) * 255 // 7)


def visible(rgba):
    """Colour as it shows (premultiplied by alpha) and alpha: the space palettes are fitted in."""
    import numpy as np
    a = rgba[:, 3:4] / 255.0
    return np.hstack([rgba[:, :3] * a, rgba[:, 3:4]])


def ci8_palette(vals, k=255, iters=30):
    """RGB5A3 values (0: transparent) -> ({value: index 1..k}, 256 RGB5A3 entries, entry 0 transparent). Values that
    fit go in as they are; more are fitted by k-means in visible() space, weighted by how often each occurs, from a
    fixed farthest-point start (so a build is repeatable), then snapped to RGB5A3."""
    import numpy as np
    colours, counts = np.unique(np.array([v for v in vals if v] or [0], np.int64), return_counts=True)
    colours, counts = colours[colours != 0], counts[colours != 0]
    if len(colours) <= k:
        pal = [int(v) for v in colours]
        mapping = {v: i + 1 for i, v in enumerate(pal)}
    else:
        X = visible(np.array([rgb5a3_rgba(int(v)) for v in colours], float))
        w = counts.astype(float)
        cent, d = [X[np.argmax(w)]], None
        d = ((X - cent[0]) ** 2).sum(1)
        while len(cent) < k:
            i = int(np.argmax(d * np.sqrt(w)))
            cent.append(X[i])
            d = np.minimum(d, ((X - X[i]) ** 2).sum(1))
        C = np.array(cent)
        for _ in range(iters):
            lab = ((X[:, None, :] - C[None]) ** 2).sum(2).argmin(1)
            for j in range(k):
                m = lab == j
                if m.any():
                    C[j] = (X[m] * w[m, None]).sum(0) / w[m].sum()
        a = np.clip(C[:, 3], 0, 255)
        rgb = np.where(a[:, None] > 0, C[:, :3] / np.maximum(a[:, None] / 255.0, 1e-6), 0)
        pal = [rgb5a3_value(*(int(round(min(255.0, max(0.0, x)))) for x in (*rgb[j], a[j]))) for j in range(k)]
        P = visible(np.array([rgb5a3_rgba(v) for v in pal], float))
        lab = ((X[:, None, :] - P[None]) ** 2).sum(2).argmin(1)
        mapping = {int(v): int(j) + 1 for v, j in zip(colours, lab)}
    return mapping, [0] + pal + [0] * (255 - len(pal))


def band_values(band):
    """A band's pixels as RGB5A3 values, row-major (0: transparent)."""
    return [rgb5a3_value(*p) if p[3] else 0 for p in band.getdata()]


def part_values(vals, part):
    """The values of LOGO_RECTS[part] of a band's values."""
    x0, y0, x1, y1 = LOGO_RECTS[part]
    return [vals[y * LOGO_BAND[0] + x] for y in range(y0, y1) for x in range(x0, x1)]


def tile_ci8(idx, w, h):
    """Row-major indices -> GX CI8 (8 x 4 tiles)."""
    out = bytearray()
    for ty in range(0, h, 4):
        for tx in range(0, w, 8):
            for y in range(ty, ty + 4):
                out += idx[y * w + tx:y * w + tx + 8]
    return bytes(out)


def _logo_file(data):
    """File 1: every custom captain's logo and emblem, CI8 like the stock ones: one image of LOGO_BAND bands, a page
    (palette) per logo and per emblem over it (ci8_palette; 23.5 KB a captain, the RGB5A3 page was 48). File 1 stays
    resident in a match (the MEM2 heap: git-95's heap_budget.py)."""
    import layout
    if not NEW_CAPTAINS and not STOCK_ART and not COMPACT:   # no custom captain (an empty "list"): nothing to add
        return data
    L = layout.Layout(data)
    assert len(L.rows) == STOCK_ROWS_1, "file 1 is not stock"
    if COMPACT:                                              # slot j: its source's logo 0x0C + j and emblem j
        logos, emblems = [bytes(L.rows[0x0C + i]) for i in range(STOCK)], [bytes(L.rows[i]) for i in range(STOCK)]
        for j in range(STOCK):
            L.rows[0x0C + j][:], L.rows[j][:] = logos[src(j)], emblems[src(j)]
    if not NEW_CAPTAINS and not STOCK_ART:
        return L.to_bytes()
    bw, bh = LOGO_BAND
    stock = sorted(STOCK_ART)                                # stock captains' own logos: bands after the new ones
    bands = [logo_band(c) for c in NEW_CAPTAINS] + [_stock_band(STOCK_ART[i]) for i in stock]
    size = (bw, bh * len(bands))
    idx, pals, rects = bytearray(bw * size[1]), [], []
    for k, band in enumerate(bands):
        vals, y = band_values(band), bh * k
        for part, (x0, y0, x1, y1) in enumerate(LOGO_RECTS):
            mapping, pal = ci8_palette(part_values(vals, part))
            pals.append(struct.pack(">256H", *pal))
            for yy in range(y0, y1):
                row = (y + yy) * bw
                idx[row + x0:row + x1] = bytes(mapping.get(v, 0) for v in vals[yy * bw + x0:yy * bw + x1])
        rects.append(tuple((x0, y + y0, x1, y + y1) for x0, y0, x1, y1 in LOGO_RECTS))
    template = struct.unpack(">H", L.rows[0x0C][:2])[0]      # a stock logo page (CI8, RGB5A3 palette)
    pages = [L.add_texture(tile_ci8(bytes(idx), *size), *size, GX_CI8, template_page=template, palette=pals[0],
                           palette_format=TL_RGB5A3)]
    pages += [L.add_palette_page(pages[0], p, TL_RGB5A3) for p in pals[1:]]
    for k, c in enumerate(NEW_CAPTAINS):
        logo_page, emblem_page = pages[2 * k], pages[2 * k + 1]
        logo_row, emblem_row = rows_1(k)
        assert L.add_row(logo_page, *_uv(size, rects[k][0])) == logo_row
        assert L.add_row(emblem_page, *_uv(size, rects[k][1])) == emblem_row
        if c in REPLACED:                                    # the slot's computed rows show the new art
            _set_row(L, 0x0C + c["index"], logo_page, _uv(size, rects[k][0]))
            _set_row(L, c["index"], emblem_page, _uv(size, rects[k][1]))
    for n, i in enumerate(stock):                            # a stock captain's rows: just the parts given
        k = len(NEW_CAPTAINS) + n
        if "logo" in STOCK_ART[i]:
            _set_row(L, 0x0C + i, pages[2 * k], _uv(size, rects[k][0]))
        if "emblem" in STOCK_ART[i]:
            _set_row(L, i, pages[2 * k + 1], _uv(size, rects[k][1]))
    return L.to_bytes()


def logo_lines():
    """This build's player logos / emblems (charbuild logs them after configure, a dry run too)."""
    out = []
    for c in NEW_CAPTAINS:
        own = [k for k in TEAM_ART if c.get(k + "_file") is not None]
        if own:
            out.append(f"team logo: {c['name']}'s " + ", ".join(f"{k} {c[k + '_file']}" for k in own))
    for i, files in sorted(STOCK_ART.items()):
        out.append(f"team logo: {STOCK_CAPTAIN_NAMES[src(i)]}'s " + ", ".join(f"{k} {p}" for k, p in files.items())
                   + " (in the game's own logo rows)")
    return out


def _stock_band(files):
    """A stock captain's band of the player's logo / emblem (a part not given stays empty: its row isn't moved)."""
    band = Image.new("RGBA", LOGO_BAND, (0, 0, 0, 0))
    for part, key in enumerate(TEAM_ART):
        if key in files:
            band.paste(player_image(files[key], key), LOGO_RECTS[part][:2])
    return band


def patch_layouts(dol, dat_path, extra=None):
    """extra: {file index: bytes -> bytes} run on each rebuilt copy (charbuild: star_move_labels' file-18 row)."""
    import dtna_toc
    log = []
    extra = extra or {}
    # a file is rebuilt when something changes it: custom captains (both), a renamed stock captain's plate (file 18),
    # or another step's edit riding along (extra: captain select's labels, the menu colour). No custom captain (captains
    # off, or on with an empty "list": the stock 12) leaves the rest alone (Nick's Patcher 10 crash: file 1 with no
    # captains indexed an empty palette list).
    files = [(i, own) for i, own in ((FILE_CAPTAIN, _captain_file), (FILE_LOGO, _logo_file))
             if NEW_CAPTAINS or COMPACT or i in extra or (i == FILE_CAPTAIN and (STOCK_RENAMED or POSITIONS))
             or (i == FILE_LOGO and STOCK_ART)]
    for index, own in files:
        rebuild = (lambda data, own=own, more=extra[index]: more(own(data))) if index in extra else own
        n = dtna_toc.rebuild_file(dol, dat_path, 119, index, rebuild)
        log.append(f"captain layout: dir 119 file {index} rebuilt ({n} copies appended)")
    missing = {c["name"]: art(c)[1] for c in NEW_CAPTAINS}
    missing = {n: m for n, m in missing.items() if m}
    if missing:
        log.append("captain art placeholders: " + "; ".join(f"{n}: {', '.join(m)}" for n, m in missing.items()))
    drawn = {c["name"]: drawn_keys(c) for c in NEW_CAPTAINS}
    drawn = {n: k for n, k in drawn.items() if k}
    if drawn:
        log.append("captain art drawn from the 3D model: " + "; ".join(f"{n}: {', '.join(k)}" for n, k in drawn.items()))
    if STOCK_RENAMED:
        log.append("captain select name plates redrawn: " + ", ".join(
            f"{STOCK_CAPTAIN_NAMES[src(i)]} -> {n}" for i, n in sorted(STOCK_RENAMED.items())))
    return log
