"""The character editor (git-b6): one character's stats, size, hitting / pitching / catching values, chemistry and
names, for stock characters, new characters and recolors. Every number is on one Stats page, grouped by what it
changes (a player: "It threw me off that 'Stats' and 'Hitting, pitching and catching' are separate areas"); the
star moves and abilities have their own page. Design: docs/character-editor.md (git-dc); the checks are
patch.check_character, the ranges patch.STAT_RANGES / TABLE_RANGES.

It opens from the Characters tab ("Edit stats, chemistry and names...", gui.py) on the player's own game, which it
reads for the stock values. Edits go into the profile's "characters" block through the window's app.extra_characters
(keyed by the character's name), and only the fields that differ from what the build would make anyway: an editor
left alone writes nothing (docs/character-editor.md, "Untouched editor = same game"). The star pitch, star swing and
fielding ability are kept in the Characters tab's store.
"""
import tkinter as tk
import style
from tkinter import ttk, messagebox

import patch
import widgets

EDITOR_KEYS = ("stats", "chemistry", "name", "table_stats", "scale")
ROWS, ROW = 0x806CE9A0 + 8, 0x8E                    # the stats table (charbuild.TABLES "stats")
FIRST_MII, LAST_MII = 0x4D, 0x64
CHOICES = {                                         # stats and table values shown as words
    "pitching arm": ["Right", "Left"], "batting arm": ["Right", "Left"],
    "character class": ["Balanced", "Power", "Speed", "Technique"],
    "captain": ["No", "Yes"],
    "baserunning ability": ["None", "Scatter Dive", "Ink Dive", "Angry Attack", "Teleport", "Spin Attack", "Burrow",
                            "Enlarge"],
    "hit trajectory": ["Medium", "High", "Low"],       # (docs/hidden-stats.md: traj byte 0)
    "hit curve": ["No", "Yes"],                        # (traj byte 1, a flag)
    "star pitch type": ["None", "Breaking ball", "Fastball", "Change-up"],
    "precharge": ["No", "Yes"]}                        # (a view of windup charge frames: PRECHARGE_MAX)
# Every number on one Stats page (stats row and per-character tables mixed: a field in patch.STAT_RANGES is the
# stats row's, the rest charbuild.TABLE_STATS'), grouped by what it changes; "precharge" is a Yes / No view of
# "windup charge frames", not a value of its own. Two stacks of boxes (STAT_COLUMNS), then Size.
STAT_GROUPS = [("Basics", ["pitching arm", "batting arm", "character class", "weight", "baserunning ability"]),
               ("Batting", ["slap size", "charge size", "slap power", "charge power", "bunting", "hit trajectory",
                            "hit curve"]),
               ("Pitching", ["curveball speed", "charge pitch speed", "curve", "curse ball", "changeup speed mult",
                             "changeup arc height", "pitch steering", "stamina", "windup charge frames", "precharge"]),
               ("Running and fielding", ["speed", "outfield throwing", "fielding"]),
               ("Catching reach", ["catch normal", "catch any direction", "catch centered", "catch max height",
                                   "catch dive"]),
               ("Body cylinder (Fielding and item hitbox)", ["body radius", "body height"]),
               ("Stats on the select card", ["displayed pitching", "displayed batting", "displayed fielding",
                                             "dis speed"]),
               ("Size and strike zone", ["strike zone height"])]    # (+ Size; the zone follows the size)
# the column each box stacks in; 2: one box across both, under them (the strike zone's row is too wide for a
# column beside Pitching once its stock value has four decimals)
STAT_COLUMNS = {"Basics": 0, "Pitching": 0, "Stats on the select card": 0, "Batting": 1, "Running and fielding": 1,
                "Catching reach": 1, "Body cylinder (Fielding and item hitbox)": 1, "Size and strike zone": 2}
TABLE_GROUPS = []                                   # (were on "Hitting, pitching and catching": now in STAT_GROUPS)
MOVES_PAGE = "Star moves and abilities"
# Precharge [C] (docs/cpu-ai.md 2.4): the CPU batter (FUN_800c4ff4) starts its charge while the pitcher's countdown
# +0x100 < 0x8062818C[hz] (8 at 60 Hz), and +0x100 already holds pitchwindup +0 (windup charge frames) before the
# windup moves, so a pitcher with 7 or fewer frames is charged against before he moves. Yes / No pick a stock value:
# the character's own when it already is one, else 7 (Baby Luigi, Bowser, Dixie, Baby Peach, Baby Daisy) / 9 (the
# lowest stock value that isn't precharge; the community "CPU Remove Precharge" code writes 8) [C values]
PRECHARGE_MAX, PRECHARGE_YES, PRECHARGE_NO = 7, 7, 9
TABLE_LABELS = {"hit trajectory": "Hit trajectory", "hit curve": "Hit curve", "strike zone height": "Strike zone height",
                "star pitch type": "Star pitch type", "changeup speed mult": "Change-up speed",
                "changeup arc height": "Change-up arc", "pitch steering": "Pitch steering", "stamina": "Stamina",
                "catch normal": "Normal", "catch any direction": "Any direction", "catch centered": "Centered",
                "catch max height": "Highest", "catch dive": "Diving",
                "body radius": "Radius", "body height": "Height", "windup charge frames": "Windup charge frames",
                "precharge": "Precharge"}
CHEM_WORDS = {0: "bad", 1: "neutral", 2: "good"}
# the stats' "captain" flag is only the captain's star pitch and swing, not captain select (Nick: "make it clear in the
# ui that captain means captain stars")
CAPTAIN_LABEL = "Captain star moves"
CAPTAIN_STARS = ("Gives them a captain's own star pitch and star swing. It doesn't put them on captain select (that's "
                 "the Captains tab).")
CAPTAIN_STARS_BETA = "Gives them a captain's own star pitch and star swing. It doesn't put them on captain select."
# (star pitch type, in Star moves) a non-captain's: never None. A captain template's is 0 (the 12 stock
# captains); made a non-captain it takes Breaking ball, the most common among the game's non-captains (19 of 42)
PLAIN_TYPE = 1
BETA_CAPTAIN_STEP = ("Star moves and abilities: Captain star moves Yes gives them one of the game's star pitches and "
                     "swings, No the kind of star pitch they throw. Their fielding ability is there too.")
# (the Characters Beta: no Special moves, Create or Captains tab)
HOWTO = dict(
    steps=["Every number is on Stats, grouped by what it changes (batting, pitching, running and fielding, catching "
           "reach, body, the select card); the grey number is the game's own, and Stock puts it back.",
           "Star moves and abilities: Captain star moves Yes gives them a star pitch and swing (the game's, ours or "
           "your own from Create), No the kind of star pitch they throw.",
           "Special moves, on the same page, has their fielding ability and item. Being on captain select, captain "
           "art and lineup are on the Captains tab.",
           "On Chemistry, pick one or more characters and press Good, Neutral or Bad. It counts both ways; changed "
           "ones go to the top.",
           "The names are the top line of Stats: type the new one. Untick \"Same in all\" to give Spanish and French "
           "their own.",
           "Press Save (or close the window) when you're done: your changes are kept with your choices (Save choices... keeps them in "
           "a file)."],
    share="Save choices... on the main window writes everything to a file; anyone can load it with Open choices....",
    refused="a number too big for the game's data (said in red under the box; one past the game's own limit is kept, "
            "with a warning in amber), a name too wide "
            "for the name plate, or something the line at the top says isn't in the patcher yet.")
TIPS = {   # what a value does in the game (hover); the ranges show beside each box. From the docs (docs/hidden-stats.md,
    # cpu-ai.md 2.2-2.5, cpu-ai-weaknesses.md 8, star-swings.md); where play isn't traced, the tip says so
    "pitching arm": "The hand they pitch with. Left-handed pitching can glitch some animations (stat editor note).",
    "batting arm": "The side of the plate they bat from.",
    "character class": "Balanced, Power, Speed or Technique, as shown on the select card. The CPU picks its pitches "
                       "and charge swings by class.",
    "weight": "0 is the lightest, 4 the heaviest. Not on the card; it changes how far they reach for catches and to "
              "cover a base.",
    "captain": CAPTAIN_STARS,
    "baserunning ability": "Their special move when running the bases (None for no move).",
    "slap size": "How big the sweet spot is on a normal swing (easier good contact). More than 150 does nothing.",
    "charge size": "How big the sweet spot is on a charged swing (easier good contact). More than 150 does nothing.",
    "slap power": "How far a normal swing sends the ball (also a non-captain's star swing). More than 150 does "
                  "nothing.",
    "charge power": "How far a charged swing sends the ball. More than 150 does nothing.",
    "bunting": "How well they bunt. What it does in play isn't known yet.",
    "speed": "How fast they run, on the bases and in the field.",
    "outfield throwing": "How hard and far they throw from the field.",
    "fielding": "Their fielding stat (the CPU counts it when it sets its outfield). What else it does in play isn't "
                "known yet.",
    "displayed pitching": "The pitching stat shown on the select card, 0 to 10. It doesn't change how they pitch, "
                          "but the CPU prefers relief pitchers above 6.",
    "displayed batting": "The batting stat shown on the select card, 0 to 10. Only what the card shows; it doesn't "
                         "change how they play.",
    "displayed fielding": "The fielding stat shown on the select card, 0 to 10. Only what the card shows; it doesn't "
                          "change how they play.",
    "dis speed": "The speed stat shown on the select card, 0 to 10. Only what the card shows; it doesn't change how "
                 "they play.",
    "curveball speed": "How fast their normal pitch is (a change-up is a share of it).",
    "charge pitch speed": "How fast a fully charged pitch is (a perfect charge is 1.2 times it).",
    "curve": "How much their pitches bend.",
    "curse ball": "Makes hits off their charged pitches weaker unless the batter hits the sweet spot; higher is "
                  "stronger (community finding, matches the game's code; the stock CPU's pitches never use it).",
    "hit trajectory": "The flight of their star swing when they aren't a captain: Medium or High a deep fly, Low a "
                      "line drive. What it does to normal hits isn't known yet.",
    "hit curve": "Yes: a non-captain's star swing is a slow, high hit that bends toward the foul line, and their "
                 "normal hits bend a little more.",
    "strike zone height": "The height every pitch crosses the plate at for this batter (it follows their size). It "
                          "moves where you swing, not what counts as a strike.",
    "star pitch type": "What kind of star pitch they throw when they aren't a captain.",
    "changeup speed mult": "A change-up's speed as a share of their normal pitch (1 = no slower).",
    "changeup arc height": "How high a change-up lobs mid-flight. It changes the timing, not the strike call.",
    "pitch steering": "How far a player can bend their charged pitch with the stick while it flies.",
    "stamina": "Their most stamina as a pitcher. It drains as they pitch; tired pitches are slower and bend less.",
    "windup charge frames": "Frames the windup counts down before the ball leaves their hand (60 a second). 7 or "
                            "fewer is precharge.",
    "precharge": "Yes: a CPU batter starts charging before this pitcher even moves (their windup is 7 frames or "
                 "fewer).",
    "catch normal": "How far they reach for a catch, in centimetres (before their size).",
    "catch any direction": "How far they reach for a catch in any direction, in centimetres.",
    "catch centered": "How far they reach for a catch right in front of them, in centimetres.",
    "catch max height": "How high they reach for a standing catch, in centimetres (times their size).",
    "catch dive": "How far a diving catch reaches, in centimetres.",
    "body radius": "How wide their body is for fielding contacts and items hitting them, in centimetres (not "
                   "hit-by-pitch).",
    "body height": "How tall their body is for fielding contacts and items hitting them, in centimetres (not "
                   "hit-by-pitch).",
    "scale": "How big they are. 1 is their normal size; the strike zone and catch height follow it.",
}


def per_language_names():
    """True when the patcher takes a different name per language (patch._definition_keys refuses them until the build
    does them)."""
    try:
        patch._definition_keys({"name": {"en": "A", "es": "B"}})
        return True
    except SystemExit:
        return False


def stock_size():
    """True when the build takes a stock character's size."""
    import charbuild
    return "scale" in getattr(charbuild, "STOCK_KEYS", ())


STOCK_MOVES = ["Fire", "Tornado", "Barrel", "Banana", "Heart", "Flower", "Phony", "Liar", "Egg", "Cannon", "Breath",
               "Graffiti"]                              # star moves 1-12 (gecko_export.SWING_NAMES)
FIELDING_GROUPS = [("Dive or jump", ["Super Dive", "Super Jump", "Clamber", "Clamber Jump"]),
                   ("Catch", ["Tongue Catch", "Suction Catch", "Magical Catch", "Piranha Catch", "Keeper Catch"]),
                   ("Throw", ["Hammer Throw", "Quick Throw", "Tantrum Toss"]),
                   ("Other", ["Ball Dash", "Laser Beam"])]
MOVE_TIPS = {
    "star swing": "A captain's special hit. Ours need Custom star swings; your own come from Create > Star swings (used "
                  "there) and need it too.",
    "star pitch": "A captain's special pitch. Cosmic Pull and Launch Star need Star pitch paths, Bob-omb Drop needs "
                  "Star pitch items, Vanishing Ball needs Vanishing Ball.",
    "fielding ability": "What they do on a fielding star move: dives, jumps, catches and throws. Tantrum Toss needs Star "
                        "Solo Toss; Clamber Jump needs Clamber Solo Jump.",
    "batting_item": "The item this character brings: the teammate batting just before them gets it (when this "
                    "character is on deck, as with the game's own item carriers). Your items come from Create > Items.",
    "always_item": "The batter gets it from this character even without good chemistry between them.",
    "captain": CAPTAIN_STARS}
# the Characters Beta's (in Star moves): the game's own twelve and Clamber Jump (its edition's "follow_settings":
# on only for a character given it), with a line under the list saying what Clamber Jump is (Nick)
BETA_FIELDING_TIP = "What they do on a fielding star move: a dive, a jump, a catch or a throw."
# the beta's item rows (its edition's fixed-items / item-ability; items_window.py has the items themselves)
BETA_TIPS = {"fielding ability": BETA_FIELDING_TIP,
             "batting_item": "The item this character brings: the teammate batting just before them gets it (when "
                             "this character is on deck). Your own items come from Items... on the main page.",
             "item_ability": "The item ability shown on their card (up to 24 letters). Empty: as they are."}
BETA_ITEMS = ("none", "shell", "fireball", "bobomb", "pow", "banana", "boo")   # + the Ice ball with item-variants
BETA_CLAMBER_NOTE = ("Clamber Jump: allows a fielder to do a solo buddy jump by clambering on the wall and pressing A "
                     "(an idea to help rebalance the Kongs).")


def create_page(app, which):
    """A Create page (items, swings, pitches): the Create tab's, or the beta's items (items_window.ItemsPart)."""
    create = next((pt for pt in getattr(app, "parts", []) if type(pt).__name__ in ("CreateTab", "ItemsPart")
                   and getattr(pt, which, None) is not None), None)
    return getattr(create, which, None)


def saved(page):
    """[(name, path)]: the player's saved creations on a Create page (all of them, used or not)."""
    out = []
    for path in page.list.own() if page is not None else []:
        try:
            out.append((page.read(path).get("name") or path.stem, path))
        except (OSError, ValueError):
            pass
    return out


def swing_choices(app, stock=False):
    """[(label, value, file or None)]: none, the stock swings, ours (13-15) and every swing the player has saved on
    Create > Star swings (by name, git-95; picking one uses it). stock: none and the stock ones only (the beta: no
    custom_swings import, git-92's lean Beta 3.6)."""
    out = [("None", 0, None)] + [(f"{n} Swing", i, None) for i, n in enumerate(STOCK_MOVES, 1)]
    if stock:
        return out
    import custom_swings
    out += [(f"{sw['name']} (ours)", i, None) for i, sw in sorted(custom_swings.SWINGS.items())]
    return out + [(f"{name} (yours)", name, path) for name, path in saved(create_page(app, "swings"))]


def pitch_choices(app=None, stock=False):
    """[(label, value, file or None)]: none, the stock pitches, our four, the player's edited copies of ours on
    Create > Star pitches (named like ours: they replace ours) and their brand-new pitches (by name, git-95 e26e1a0);
    picking one of theirs uses it. stock: none and the stock ones only."""
    out = [("None", 0, None)] + [("Fireball" if n == "Fire" else f"{n} Ball", i, None)
                                 for i, n in enumerate(STOCK_MOVES, 1)]
    if stock:
        return out
    import star_move_labels
    out += [(f"{n} (ours)", i, None) for i, n in sorted(star_move_labels.PITCH_NAMES.items())]
    ids = {n: i for i, n in star_move_labels.PITCH_NAMES.items()}
    mine = saved(create_page(app, "pitches"))
    out += [(f"{name} (yours, edited)", ids[name], path) for name, path in mine if name in ids]
    return out + [(f"{name} (yours)", name, path) for name, path in mine if name not in ids]   # new: by name (git-95)


def item_choices(app):
    """[(label, value, file or None)]: no item, the game's items and ours (by name), and every item the player has
    saved on Create > Items (by name, git-dc; picking one uses it)."""
    out = [(label, name, None) for label, name in app.items.items()]
    return out + [(f"{name} (yours)", name, path) for name, path in saved(create_page(app, "items"))]


def _has_glyph(abilities, ch):
    try:
        abilities.text_alpha(ch)
        return True
    except AssertionError:
        return False


def beta_item_choices(app, now=None):
    """[(label, value, file or None)]: the Characters Beta's Brings list: no item, the game's six, the Ice ball (when the
    edition has item-variants), our ready-made six (koopaling-items: named by what they are, items_window.TITLES), Star
    Bits (new-roulette-item; Rosalina's by default), the player's saved items (items_window's part, "(yours)"), and the
    character's own item when it's none of those."""
    import items_window as iw
    keep = BETA_ITEMS + (("ice",) if "item-variants" in app.reg else ()) + (
        iw.KOOPA if iw.KOOPA_FEATURE in app.reg else ()) + ((iw.STARBITS,) if "new-roulette-item" in app.reg else ())
    names = {name: label for label, name in app.items.items()}
    out = [(iw.TITLES.get(name, names[name]), name, None) for name in keep if name in names]
    import creators.items as it                 # (an edit of our Ice is the Ice ball itself: not "yours")
    out += [(f"{name} (yours)", name, path) for name, path in saved(create_page(app, "items"))
            if not it.preset_of(name)]
    if now not in (None, False, "") and not any(c[1] == now for c in out):
        import gui
        out.append((gui.ITEM_TITLES.get(now, str(now)), now, None))
    return out


def fielding_choices(stock=False, also=()):
    """[(label, value, None)]: none and the fielding abilities by kind, ours marked. stock: none and the game's own
    twelve, by name, and the ids of ours in also (the Characters Beta: Clamber Jump, after Clamber)."""
    import abilities
    if stock:
        ids = {n: i for i, n in enumerate(abilities.NAMES)} | {n: i for i, n in abilities.NEW.items() if i in also}
        return [("None", 0, None)] + [(n, ids[n], None) for _, names in FIELDING_GROUPS for n in names if n in ids]
    ids = {n: i for i, n in enumerate(abilities.NAMES)} | {n: i for i, n in abilities.NEW.items()}
    out = [("None", 0, None)]
    for group, names in FIELDING_GROUPS:
        out += [(f"{group}: {n}" + (" (ours)" if ids[n] > 12 else ""), ids[n], None) for n in names if n in ids]
    return out


SELECTOR = 0x80631550                               # charbuild.TABLES "selector": 8 bytes per id, +2 family


def family_order(app, dol, entries):
    """The roster entries (name, kind, definition, id) in the select grid's order, every family together (a player:
    "the four Magikoopas are together, but the three Bros aren't"): the stock grid's squares in reading order
    (grid_order.stock_sequence), each square's colour-wheel family (selector byte 2) in id order; a new or imported
    character after its wheel's (or template's) family, a recolor right after its base; the Miis and anything else
    last."""
    import grid_order
    import gridcells
    from sluggers_data import char_id
    sel = [dol.read(SELECTOR + i * 8, 8) for i in range(grid_order.STOCK_IDS)]
    heads = list(dol.read(gridcells.HEAD_LIST, grid_order.STOCK_HEAD_COUNT))
    rank = {}
    for n, h in enumerate(grid_order.stock_sequence(dol)):
        rank.setdefault(sel[heads[h]][2], n)
    by_name = {e[0]: e for e in entries}

    def stock_key(cid):
        if cid is None or not 0 <= cid < grid_order.STOCK_IDS or FIRST_MII <= cid <= LAST_MII:
            return (10000, 0, cid if isinstance(cid, int) else 0xFFFF)
        return (rank.get(sel[cid][2], 1000 + sel[cid][2]), 0, cid)

    def ref_id(ref):
        try:
            return char_id(ref) if ref is not None else None
        except (KeyError, ValueError):
            return None

    def key(e, depth=0):
        name, kind, d, cid = e
        d = d or {}
        if kind == "stock":
            return stock_key(cid) + (0, "")
        if kind == "recolor":
            base = by_name.get(app.char_name(d.get("base")) or "")
            if base is not None and base is not e and depth < 4:
                return key(base, depth + 1)[:3] + (1, name)
            return stock_key(ref_id(recolor_template(d.get("base")))) + (1, name)
        fam = stock_key(ref_id(d.get("wheel", d.get("template"))))       # new, imported: after its family's stock
        return fam[:1] + (1, cid if isinstance(cid, int) else 0xFFFF, 0, "")
    return sorted(entries, key=key)


CARD = {"displayed pitching": "Pitching stat", "displayed batting": "Batting stat", "displayed fielding":
        "Fielding stat", "dis speed": "Speed stat"}          # the select card's numbers: "stats", not "stars" (Nick)


def label(field):
    if field in CARD:
        return CARD[field]
    if field == "captain":
        return CAPTAIN_LABEL
    return patch.STAT_RANGES[field][2].capitalize() if field in patch.STAT_RANGES else TABLE_LABELS[field]


class Stock:
    """What the player's game has: a stock character's stats row, chemistry and table values (charbuild's layouts)."""

    def __init__(self, dol):
        import charbuild
        from sluggers_data import STAT_FIELDS, CHEM_BASE
        self.dol, self.fields, self.chem_base = dol, STAT_FIELDS, CHEM_BASE
        self.tables = {t[0]: t for t in charbuild.TABLES}
        self.table_stats = charbuild.TABLE_STATS

    def row(self, cid):
        return self.dol.read(ROWS + cid * ROW, ROW)

    def stats(self, cid):
        row = self.row(cid)
        return {f: int.from_bytes(row[o:o + w], "big") for f, (o, w) in self.fields.items() if f in patch.STAT_RANGES}

    def chemistry(self, a, b):
        return self.row(a)[self.chem_base + b]

    def table(self, cid):
        import struct
        out = {}
        for field, (name, off, kind) in self.table_stats.items():
            if field not in patch.TABLE_RANGES:
                continue
            _, addr, size, header = self.tables[name]
            raw = self.dol.read(addr + header + cid * size + off, 4 if kind == "f" else 2 if kind == "h" else 1)
            out[field] = (raw[0] if kind == "B" else struct.unpack(">h", raw)[0] if kind == "h"
                          else round(struct.unpack(">f", raw)[0], 4))
            if kind == "f" and patch.TABLE_RANGES[field][2] is int:     # (a float of whole frames: windup)
                out[field] = int(round(out[field]))
        return out


def stock_id(ref):
    from sluggers_data import char_id
    return char_id(ref)


def recolor_template(base):
    """A recolor's base as its stock template (an added base, e.g. Rosalina: her definition's template)."""
    import recolor
    return recolor.template_of(base) if base is not None else base


class Character:
    """One roster entry (gui.App.roster: name, kind, definition or recipe, id) and what the build makes of it
    without this editor: its stats, table values, size, name, and chemistry with anyone."""

    def __init__(self, app, stock, entry):
        self.app, self.stock = app, stock
        self.name, self.kind, self.d, self.id = entry
        self.d = self.d or {}
        if self.kind == "stock":
            self.template = self.id
        else:
            self.template = stock_id(self.d.get("template") if self.kind in ("new", "imported") else
                                     recolor_template(self.d.get("base")))     # (imported: a template, as new)
        self.stats = stock.stats(self.template)
        self.table = stock.table(self.template)
        self.base = self.base_entry() if self.kind == "recolor" else None
        # whose chemistry this one has where it sets none, both ways (charbuild "chemistry_like"): a recolor's base; a
        # character the player made (New character, a .sluggie) its template's unless it names another
        like = self.d.get("chemistry_like", self.d.get("template") if self.d.get("made_by") == "player" else None)
        self.chem_base = self.base if self.kind == "recolor" else (
            self.base_entry(like) if self.kind in ("new", "imported") and like is not None else None)
        if self.base and self.base[1] != "stock":       # a recolor of an added character: its stats, not its template's
            bd = self.base[2] or {}
            self.stats.update({k: v for k, v in (bd.get("stats") or {}).items() if k in self.stats})
            for k, v in (bd.get("table_stats") or {}).items():
                if k in self.table:
                    self.table[k] = CHOICES[k].index(v.capitalize()) if isinstance(v, str) and k in CHOICES else v
        if self.kind == "recolor":                      # as recolor.make builds it (Nick: the base's stats), a colour
            self.stats.update(captain=0, **{"star pitch": 0, "star swing": 0})   # variant: no captain star moves,
            if not self.table.get("star pitch type"):   # and a captain base's pitch type 0 becomes Breaking ball
                self.table["star pitch type"] = PLAIN_TYPE
        if self.kind != "stock":
            self.stats.update({k: v for k, v in (self.d.get("stats") or {}).items() if k in self.stats})
            for k, v in (self.d.get("table_stats") or {}).items():
                if k in self.table:
                    self.table[k] = CHOICES[k].index(v.capitalize()) if isinstance(v, str) and k in CHOICES else v
        self.scale = float(self.d.get("scale", 1.0))
        self.mii = self.kind == "stock" and FIRST_MII <= self.id <= LAST_MII

    def chem_of(self, other):
        """The build's chemistry between this character and another roster entry, 0 bad / 1 neutral / 2 good."""
        _, okind, od, oid = other
        if self.kind == "stock" and okind == "stock":
            return self.stock.chemistry(self.id, oid)
        for d, them in ((self.d if self.kind != "stock" else None, other[0]), (od if okind != "stock" else None,
                                                                              self.name)):
            for ref, v in ((d or {}).get("chemistry") or {}).items():
                if self.app.char_name(ref) == them:
                    return patch.CHEMISTRY.get(v, v)
        # a recolor has its base's chemistry, both ways (recolor.make "chemistry_like", charbuild): ask the bases
        if self.chem_base:
            return Character(self.app, self.stock, self.chem_base).chem_of(other)
        if okind in ("recolor", "new", "imported"):
            ob = Character(self.app, self.stock, other).chem_base
            if ob:
                return self.chem_of(ob)
        return 1                        # a new character starts neutral with everyone (charbuild)

    def base_entry(self, ref=None):
        """A recolor's base as a roster entry (name, kind, definition, id): an added character from the roster, or
        a stock one; None when it isn't found (then neutral, as the build does for a base it doesn't have). ref: another
        character to look up the same way (a player-made character's chemistry base)."""
        ref = self.d.get("base") if ref is None else ref
        if ref is None:
            return None
        name = self.app.char_name(ref)
        for e in self.app.roster():
            if e[0] == name and e[1] in ("stock", "new", "imported"):
                return e
        try:
            cid = stock_id(ref)
        except (AssertionError, KeyError, ValueError):
            return None
        return (name, "stock", None, cid) if cid is not None else None


def gui_as_is():
    import gui
    return gui.AS_IS


def fit_label(parent, text):
    import fit
    fit.label(parent, text, grey=True).pack(fill="x", pady=(6, 0))


class ChoiceField(ttk.Frame):
    """A value shown as words: a read-only list, the stock value in grey."""

    def __init__(self, parent, text, choices, stock, on_change, width=14, label_width=None):
        super().__init__(parent)
        self.choices, self.on_change = choices, on_change
        ttk.Label(self, text=text + ":").grid(row=0, column=0, sticky="w")
        if label_width:                     # (px: a column of them lines up)
            self.columnconfigure(0, minsize=label_width)
        self.var = tk.StringVar(value=choices[stock])
        self.box = ttk.Combobox(self, textvariable=self.var, values=choices, state="readonly", width=width)
        self.box.grid(row=0, column=1, padx=4)
        self.box.bind("<<ComboboxSelected>>", lambda e: on_change(self.get()))
        ttk.Label(self, text=f"stock {choices[stock]}", style="Small.TLabel").grid(row=0, column=2, padx=4)

    def get(self):
        return self.choices.index(self.var.get())

    def set(self, v):
        self.var.set(self.choices[v])


class CharEditor:
    def __init__(self, win, app, entry, dol, embedded=False, head=None):
        """win: its own Toplevel, or (embedded, git-10's one-page Characters Beta window) a frame the host packed,
        which has its own header and Done: no title, size, name header or Close / Everything back to stock; .tabs is
        the notebook the host may add a page to; problems() and reset_all() are for the host; head: the host's title
        row, where the intro and How to go (a line less: Stats fits the host's 820 x 600 without scrolling); the
        problems line only shows when there are problems."""
        self.win, self.app, self.embedded = win, app, embedded
        self.char = Character(app, Stock(dol), entry)
        self.name = self.char.name
        self.adopt_refs()
        if not embedded:
            style.title(win, f"{self.name}: stats, chemistry and names")
            win.geometry("760x600")            # inside Nick's 860 x 620; the tabs scroll
            kind = {"stock": "", "new": " (new character)", "recolor": " (recolor)"}[self.char.kind]
        if head is None:
            head = ttk.Frame(win, padding=(8, 6 if not embedded else 0, 8, 0))  # one line: Stats fits 760 x 600 (Nick)
            head.pack(fill="x")
        if not embedded:
            ttk.Label(head, text=self.name + kind, font="SluggersHeading").pack(side="left")
        import gui
        # an edition without the character settings (the Characters Beta: no captains, items, star moves or
        # abilities; editions/*.json "hide_character_settings") shows nothing that needs them
        self.beta = bool((getattr(gui, "EDITION", None) or {}).get("hide_character_settings"))
        limits = [] if self.char.kind != "stock" or stock_size() else ["a stock character's size"]
        limits += [] if per_language_names() else ["a different name in each language"]
        intro = ttk.Label(head, foreground=widgets.GREY, padding=(8 if not embedded else 12, 0, 0, 0),
                          text=("" if embedded else ": ") + "stats, chemistry and names. Anything left alone stays as "
                               "in the game.")
        intro.pack(side="left")
        widgets.tip(intro, "Changes this character's stats, size, hitting, pitching and catching, chemistry and names "
                           "in the game, as you make them: every number is on Stats. A captain's star pitch and swing "
                           f"are on {MOVES_PAGE}" +
                           (", with their fielding ability." if self.beta else
                            ", with their fielding ability and item.") +
                           (f" Not in the patcher yet: {' or '.join(limits)}." if limits else ""))
        line = widgets.credit("Characters")               # git-10's credits: one line, the whole of it on hover
        if line:
            short = line if len(line) <= 110 else line[:107].rsplit(" ", 1)[0] + "..."
            credit = ttk.Label(win, text=short, foreground=widgets.GREY, padding=(8, 0))
            credit.pack(anchor="w")
            widgets.tip(credit, line)
        howto = dict(HOWTO)
        if self.beta:
            howto["steps"] = [BETA_CAPTAIN_STEP if s.startswith("Star moves") else s for s in HOWTO["steps"]
                              if not s.startswith("Special moves")]
        self.howto = widgets.HowTo(head, key="character editor", body_in=win, **howto)
        self.howto.pack(side="right")
        self.tabs = ttk.Notebook(win)
        self.tabs.pack(fill="both", expand=True, padx=8, pady=6 if not embedded else (2, 4))
        self.howto.before = self.tabs                     # (its steps open above the tabs)
        self.fields, self.moves = {}, {}       # (every number on Stats; the moves on Star moves and abilities)
        self.build_stats()
        self.build_moves_page()
        self.build_chemistry()
        self.info_panel = widgets.InfoPanel(win)          # what an "i" says (git-92), inside the window
        if embedded:                                      # the host has its own Save (git-10); this line packs
            bottom = ttk.Frame(win, padding=(8, 0, 8, 4))    # only while there are problems (show_problems)
        else:                                             # Save: the changes are kept as they're made; it closes
            bottom = widgets.save_bar(win, win.destroy, padding=(8, 0, 8, 8))
            ttk.Button(bottom, text="Everything back to stock", command=self.reset_all).pack(side="right", padx=(0, 6))
        self.problem_label = ttk.Label(bottom, text="", wraplength=560, justify="left")
        self.problem_label.pack(side="left", fill="x", expand=True)
        self.show_problems()

    def problems(self):
        """The character's problems as plain text, "" when there are none (the host's Done asks)."""
        found = patch.check_character(self.name, {**self.app.settings.get(self.name, {}), **self.entry()},
                                      want=self.app.picked())
        return "\n".join(found)

    # --- the profile entry (app.extra_characters[name]: only what differs from the build's own)

    def adopt_refs(self):
        """A loaded profile may name the character by id or another spelling: its editor keys move to the name."""
        extra = self.app.extra_characters
        for ref in [r for r in extra if r != self.name and self.app.char_name(r) == self.name]:
            keys = extra.pop(ref)
            extra.setdefault(self.name, {}).update(keys)

    def entry(self, name=None):
        return self.app.extra_characters.get(name or self.name, {})

    def put(self, key, field, value, base, name=None):
        """One field of a dict key ("stats", "table_stats", "chemistry"), or a top-level key when field is None: kept
        only when it differs from base."""
        name = name or self.name
        e = self.app.extra_characters.setdefault(name, {})
        if field is None:
            if value == base:
                e.pop(key, None)
            else:
                e[key] = value
        else:
            sub = e.setdefault(key, {})
            if value == base:
                sub.pop(field, None)
            else:
                sub[field] = value
            if not sub:
                del e[key]
        if not e:
            del self.app.extra_characters[name]
        self.show_problems()

    def show_problems(self):
        keys = {**self.app.settings.get(self.name, {}), **self.entry()}   # the moves live in the tab's store
        found = patch.check_character(self.name, keys, want=self.app.picked())
        self.problem_label.configure(text="\n".join(found) if found else "No problems.",
                                foreground=widgets.RED if found else widgets.GREY)
        if self.embedded:
            row = self.problem_label.master
            if found and not row.winfo_manager():
                row.pack(side="bottom", fill="x", before=self.tabs)
            elif not found and row.winfo_manager():
                row.pack_forget()

    def reset_all(self):
        e = self.app.extra_characters.get(self.name, {})
        for k in EDITOR_KEYS:
            e.pop(k, None)
        for other, oe in list(self.app.extra_characters.items()):   # pairs kept on the other character
            chem = oe.get("chemistry") or {}
            for ref in [r for r in chem if self.app.char_name(r) == self.name]:
                self.put("chemistry", ref, None, None, name=other)
        if not e:
            self.app.extra_characters.pop(self.name, None)
        self.fill()

    def fill(self):
        """Every field from the entry (or the build's own value)."""
        stats, table = self.entry().get("stats", {}), self.entry().get("table_stats", {})
        for field, w in self.fields.items():
            if field == "scale":
                w.set(self.entry().get("scale", self.char.scale))
            elif field == "precharge":
                continue                                    # (shown from windup charge frames: show_precharge)
            elif field in patch.STAT_RANGES:
                w.set(stats.get(field, self.char.stats[field]))
            else:
                w.set(table.get(field, self.char.table[field]))
        self.show_precharge()
        for key, (var, choices) in self.moves.items():
            now, _ = self.move_now(key)
            var.set(next((c[0] for c in choices if c[1] == now), str(now)))
        self.show_captain(self.captain_now())
        self.refresh_chemistry()
        self.fill_names()
        self.show_problems()

    # --- stats and size

    def scrolled_page(self, title):
        """A tab whose content scrolls when it's taller than the window (the wheel too: Nick)."""
        outer = widgets.Scrolled(self.tabs, height=200)
        self.tabs.add(outer, text=title)
        page = ttk.Frame(outer.inner, padding=6)
        page.pack(fill="both", expand=True)
        return page

    def build_stats(self):
        page = self.scrolled_page("Stats")
        cols = [ttk.Frame(page), ttk.Frame(page), ttk.Frame(page)]    # two stacks of boxes, heights balanced, and
        for i, c in enumerate(cols[:2]):                                # one across both under them (724 px wide;
            c.grid(row=1, column=i, sticky="nsew")                      # the page scrolls down)
        cols[2].grid(row=2, column=0, columnspan=2, sticky="nsew")
        self.build_names(page)                          # the top line (Nick: "move names to the first page")
        self.groups(page, STAT_GROUPS, columns=2, stacks=(cols, STAT_COLUMNS))   # every number, by what it changes
        size = self.boxes["Size and strike zone"]
        f = widgets.NumberField(size, "Size", 0.75, 1.7, stock=self.char.scale, kind=float, step=0.01, unit="x",
                                on_change=lambda v: self.put("scale", None, v, self.char.scale))
        f.pack(anchor="w", before=size.winfo_children()[0])
        can = self.char.kind != "stock" or stock_size()
        ttk.Label(size, foreground=widgets.GREY, text="The strike zone follows the size." if can else
                  "A stock character's size isn't in the patcher yet.").pack(anchor="w")
        f.set(self.entry().get("scale", self.char.scale))
        widgets.tip(f, TIPS["scale"])
        if not can:
            widgets.set_enabled(f, False)
        self.fields["scale"] = f

    # --- precharge: a Yes / No view of windup charge frames (PRECHARGE_MAX)

    def frames_now(self):
        return self.entry().get("table_stats", {}).get("windup charge frames", self.char.table["windup charge frames"])

    def show_precharge(self):
        w = self.fields.get("precharge")
        if w is not None:
            w.set(int(self.frames_now() <= PRECHARGE_MAX))

    def precharge_picked(self, v):
        """Yes: frames <= PRECHARGE_MAX; No: more. The character's own stock value when it already is one, else a
        stock value that is (PRECHARGE_YES / PRECHARGE_NO); frames already on that side stay as they are."""
        base, now = self.char.table["windup charge frames"], self.frames_now()
        if (now <= PRECHARGE_MAX) == bool(v):
            return
        want = (base if base <= PRECHARGE_MAX else PRECHARGE_YES) if v else (base if base > PRECHARGE_MAX
                                                                             else PRECHARGE_NO)
        self.put("table_stats", "windup charge frames", want, base)
        self.fields["windup charge frames"].set(want)

    # --- the star moves (git-92 for Nick), on Star moves and abilities: Captain star moves Yes shows the star pitch and
    # swing, No the kind of pitch instead

    def build_moves_page(self):
        """Star moves and abilities: the Star moves box (captain star moves, star pitch and swing or the kind of star
        pitch; the beta's fielding ability), then (the full patcher) Special moves: fielding ability and item."""
        page = self.scrolled_page(MOVES_PAGE)
        self.build_captain(page)
        if not self.beta:
            self.build_moves(page)

    def build_captain(self, page):
        import gui
        items = {"fixed-items", "item-ability"} & set((getattr(gui, "EDITION", None) or {}).get("features", ()))
        box = ttk.LabelFrame(page, text=("Star moves, fielding and item" if items else "Star moves and fielding")
                             if self.beta else "Star moves", padding=6)
        box.pack(fill="x", padx=4, pady=4)
        cap = ChoiceField(box, label("captain"), CHOICES["captain"], self.char.stats["captain"], self.captain_picked,
                          width=5)          # (Yes / No: half the tab, 724 px wide)
        cap.pack(anchor="w", pady=1)
        cap.set(self.captain_now())
        stars = CAPTAIN_STARS_BETA if self.beta else CAPTAIN_STARS
        widgets.tip(cap, stars)
        self.info_icon(cap, "captain", CAPTAIN_LABEL, notes=stars)
        self.fields["captain"] = cap
        self.move_note = widgets.status(ttk.Label(box, text="", foreground=widgets.GREY))
        self.move_note.pack(anchor="w")
        self.after_moves = self.move_note               # (the star pitch and swing, or the kind of pitch, go above)
        if self.beta:                                   # the fielding ability, any character's (the full patcher's is
            self.after_moves = ttk.Frame(box)           # on Special moves): the game's twelve, and Clamber Jump when
            self.after_moves.pack(anchor="w", fill="x", before=self.move_note)   # the edition builds it
            import abilities
            import gui
            ed = getattr(gui, "EDITION", None) or {}
            also = (abilities.CLAMBER_JUMP,) if "clamber-solo-jump" in ed.get("features", ()) else ()
            self.move_row(self.after_moves, "fielding ability", "Fielding", fielding_choices(stock=True, also=also),
                          narrow=True)
            if also:                                    # what it is, in grey under the list (Nick)
                import fit
                fit.label(self.after_moves, BETA_CLAMBER_NOTE, grey=True).pack(fill="x", pady=(0, 2))
            feats = set(ed.get("features", ()))
            if "fixed-items" in feats:                  # the character's item, as the full patcher's Special moves
                self.move_row(self.after_moves, "batting_item", "Always brings",
                              beta_item_choices(self.app, self.move_now("batting_item")[0]), narrow=True)
                self.always = tk.BooleanVar(value=bool(self.move_now("always_item")[0]))
                always = ttk.Checkbutton(self.after_moves, text="Even without good chemistry", variable=self.always,
                                         command=self.always_picked)
                always.pack(anchor="w", padx=(4, 0))
                widgets.tip(always, MOVE_TIPS["always_item"])
            if "item-ability" in feats:                 # and its item ability on the card (the Characters tab's)
                self.label_row(self.after_moves, "item_ability", "On the card")
        self.as_captain = ttk.Frame(box)
        for key, title in (("star pitch", "Star pitch"), ("star swing", "Star swing")):
            self.move_row(self.as_captain, key, title, self.star_choices(key), narrow=True)
        self.not_captain = ttk.Frame(box)
        base = self.char.table["star pitch type"]
        t = ChoiceField(self.not_captain, TABLE_LABELS["star pitch type"], CHOICES["star pitch type"], base,
                        lambda v: self.put("table_stats", "star pitch type", v, base), width=12)
        t.box.configure(values=CHOICES["star pitch type"][1:])      # a non-captain's pitch is always one of them
        t.pack(anchor="w", pady=1)
        t.set(self.entry().get("table_stats", {}).get("star pitch type", base))
        widgets.tip(t, TIPS.get("star pitch type"))
        self.info_icon(t, "star pitch type", TABLE_LABELS["star pitch type"])
        self.fields["star pitch type"] = t
        self.show_captain(self.captain_now())

    def star_choices(self, key):
        """The star pitch / swing list: the game's, ours and the player's own; the game's only in an edition without
        the character settings (the Characters Beta)."""
        fn = swing_choices if key == "star swing" else pitch_choices
        out = [c for c in fn(self.app, stock=bool(self.beta)) if c[1] != 0]                # (Nick: no None with Yes; No is how they have none)
        if self.beta:
            out = [c for c in out if c[2] is None and isinstance(c[1], int) and c[1] <= len(STOCK_MOVES)]
        return out

    def captain_now(self):
        return self.entry().get("stats", {}).get("captain", self.char.stats["captain"])

    def show_captain(self, on):
        if not hasattr(self, "as_captain"):
            return
        show, hide = (self.as_captain, self.not_captain) if on else (self.not_captain, self.as_captain)
        hide.pack_forget()
        show.pack(anchor="w", fill="x", before=self.after_moves)

    def captain_picked(self, v):
        """No: no star pitch or swing (0, the game's non-captain value) and the template's kind of pitch (never None);
        Yes: the template's own star moves and kind of pitch back."""
        was = self.captain_now()
        self.put("stats", "captain", v, self.char.stats["captain"])
        base = self.char.table["star pitch type"]
        if was and not v:
            for key in ("star pitch", "star swing"):
                self.set_move(key, 0)
            kind = base or PLAIN_TYPE
            self.put("table_stats", "star pitch type", kind, base)
            self.fields["star pitch type"].set(kind)
            self.move_note.configure(text=f"{self.name} has no captain star moves now: no star pitch or swing, and "
                                          f"their pitch counts as a {CHOICES['star pitch type'][kind].lower()}.")
        elif v and not was:
            first = []
            for key in ("star pitch", "star swing"):
                if not self.move_base(key):     # a non-captain template has none: the first stock one, never captain
                    first.append(next(c[0] for c in self.moves[key][1] if c[1] == 1))   # with no move
                self.set_move(key, self.move_base(key) or 1)
            self.put("table_stats", "star pitch type", base, base)
            self.fields["star pitch type"].set(base)
            self.move_note.configure(text=f"{self.name} starts with {' and '.join(first)}: pick theirs above."
                                     if first else "")
        self.show_captain(v)

    def set_move(self, key, value):
        """A star move without a pick (Captain Yes / No): the Characters tab's store and the list."""
        self.app.set_setting([self.name], key, gui_as_is() if value == self.move_base(key) else value)
        var, choices = self.moves[key]
        var.set(next((c[0] for c in choices if c[1] == value and c[2] is None), str(value)))

    def info_icon(self, w, field, title, notes=None):
        """Which table and byte a field writes (git-92's "i", patch.FIELD_DATA); notes: the editor's own words."""
        data = getattr(patch, "FIELD_DATA", {}).get(field)
        if data and notes:
            data = {**data, "notes": notes}
        icon = widgets.info(w, title, data)
        if icon is not None:
            if w.grid_slaves():                 # (a ChoiceField: its row is a grid)
                icon.grid(row=0, column=9, padx=4)
            else:
                icon.pack(side="left", padx=4)

    # --- special moves: through the Characters tab's store (app.settings, set_setting), captain in the stats

    def move_now(self, key):
        """(the value the patch will use, whether it's set here): the Characters tab's setting (or a loaded
        profile's), else what the character has."""
        for store in (self.app.settings, self.app.extra_characters):
            v = store.get(self.name, {}).get(key, gui_as_is())
            if v != gui_as_is():
                return v, True
        return self.move_base(key), False

    def move_base(self, key):
        b, _ = self.app.builtin(self.name, key)
        if key == "batting_item":               # no item of their own: the list's "No item"
            return b or "none"
        if b is None:
            b = self.char.stats.get(key, 0)
        if self.beta and key == "fielding ability":
            import abilities                # as the beta builds it: the Kongs' default Clamber Jump stays theirs
            import gui                          # when the edition offers it (patch.edition_follow; Nick: "Default
            ed = getattr(gui, "EDITION", None) or {}     # the kongs to have clamber jump"), else the game's Clamber;
            if b == abilities.CLAMBER_JUMP:     # Tantrum Toss the template's own
                return b if "clamber-solo-jump" in ed.get("features", ()) else abilities.CLAMBER
            if not 0 <= b < abilities.STOCK_COUNT:
                return self.char.stats.get(key, 0) if 0 <= self.char.stats.get(key, 0) < abilities.STOCK_COUNT else 0
        return b

    def build_moves(self, page):
        box = ttk.LabelFrame(page, text="Special moves", padding=6)
        box.pack(fill="x", padx=4, pady=4)
        go = ttk.Button(box, text="Captain art and where they stand: the Captains tab", style="Toolbutton",
                        command=self.to_captains)
        go.pack(anchor="w", pady=(0, 6))
        for key, title, choices in (("fielding ability", "Fielding ability", fielding_choices()),
                                    ("batting_item", "Always brings", item_choices(self.app))):
            self.move_row(box, key, title, choices)
        self.always = tk.BooleanVar(value=bool(self.move_now("always_item")[0]))
        always = ttk.Checkbutton(box, text="Even without good chemistry", variable=self.always,
                                 command=self.always_picked)
        always.pack(anchor="w", padx=(4, 0))
        widgets.tip(always, MOVE_TIPS["always_item"])
        fit_label(page, "Make new star swings, pitches and items, or change ours, on the Create tab: the ones you save "
                        "there are in these lists. A move picked here ticks what it needs; the Characters tab shows "
                        "the same choices.")

    def move_row(self, parent, key, title, choices, narrow=False):
        """One move's list (the Characters tab's store): what the game has in grey, and its "i"."""
        row = ttk.Frame(parent)
        row.pack(anchor="w", fill="x", pady=1)
        ttk.Label(row, text=title + ":", width=11 if narrow else 16).pack(side="left")   # narrow: half the tab
        var = tk.StringVar()
        wide = max([15] + [len(c[0]) for c in choices]) if key == "batting_item" and self.beta else 15   # (the
        cb = ttk.Combobox(row, textvariable=var, values=[c[0] for c in choices], state="readonly",   # items' names)
                          width=min(wide, 22) if narrow else 30)
        cb.pack(side="left", padx=4)
        base = self.move_base(key)
        game = next((c[0] for c in choices if c[1] == base and c[2] is None), str(base))
        ttk.Label(row, text=f"now: {game}", foreground=widgets.GREY).pack(side="left", padx=4)
        cb.bind("<<ComboboxSelected>>", lambda e, key=key: self.move_picked(key))
        if key == "fielding ability" and not self.beta and getattr(self.app, "abilities", None) is not None:
            ttk.Button(row, text="Edit this ability...", style="Toolbutton",
                       command=lambda var=var: self.edit_ability(var.get())).pack(side="left")
        widgets.tip(row, BETA_TIPS[key] if self.beta and key in BETA_TIPS else MOVE_TIPS[key])
        self.info_icon(row, key, title)
        self.moves[key] = (var, choices)
        now, _ = self.move_now(key)
        var.set(next((c[0] for c in choices if c[1] == now), str(now)))

    def label_row(self, parent, key, title):
        """A card label (the beta's item ability): typed or one of the labels in use, empty = as the character is."""
        row = ttk.Frame(parent)
        row.pack(anchor="w", fill="x", pady=1)
        ttk.Label(row, text=title + ":", width=11).pack(side="left")
        var = tk.StringVar()
        cb = ttk.Combobox(row, textvariable=var, values=self.app.known_labels(), width=24)
        cb.pack(side="left", padx=4)
        base = self.move_base(key)
        ttk.Label(row, text=f"now: {base or 'none'}", foreground=widgets.GREY).pack(side="left", padx=4)
        now, _ = self.move_now(key)
        var.set(now or "")
        for event in ("<<ComboboxSelected>>", "<Return>", "<FocusOut>"):
            cb.bind(event, lambda e, key=key: self.label_picked(key))
        widgets.tip(row, BETA_TIPS.get(key, ""))
        self.labels = getattr(self, "labels", {})
        self.labels[key] = (var, cb)

    def label_picked(self, key):
        """A card label typed or picked: the game's font must have its letters; a card shows an item ability or a
        special one, not both (the Characters tab's rules, gui.App.setting_changed)."""
        import gui
        var, _ = self.labels[key]
        text = var.get().strip()[:24]
        base = self.move_base(key)
        value = gui.AS_IS if text in ("", base or "") else text
        now, set_here = self.move_now(key)
        if (value == gui.AS_IS and not set_here) or (value != gui.AS_IS and value == now):
            return
        if value != gui.AS_IS:
            import abilities
            missing = [ch for ch in dict.fromkeys(text) if not _has_glyph(abilities, ch)]
            if missing:
                self.problem_label.configure(text=f"The game's card font has no {' '.join(missing)}, so it can't "
                                                  f"show {text!r}. Try other letters.")
                return
            other = gui.ONE_OF.get(key)
            if other and (self.app.builtin(self.name, other)[0]
                          or self.app.settings.get(self.name, {}).get(other) not in (None, gui.AS_IS)):
                self.app.settings.setdefault(self.name, {})[other] = None
        self.app.set_setting([self.name], key, value)
        self.items_changed()

    def items_changed(self):
        """The beta: the item features exactly as the characters' items and labels need them (items_window.sync)."""
        if self.beta:
            import items_window
            items_window.sync(self.app)
        self.show_problems()

    def move_picked(self, key):
        var, choices = self.moves[key]
        label, value, path = next(c for c in choices if c[0] == var.get())
        if path is not None and not self.use_creation(key, path):
            now, _ = self.move_now(key)             # its page refused it (said why): back to what it was
            var.set(next((c[0] for c in choices if c[1] == now and c[2] is None), str(now)))
            return
        base = self.move_base(key)
        self.app.set_setting([self.name], key, gui_as_is() if value == base and path is None else value)
        captain = self.entry().get("stats", {}).get("captain", self.char.stats["captain"])
        if key in ("star swing", "star pitch") and value not in (0, None) and not captain:
            self.put("stats", "captain", 1, self.char.stats["captain"])   # a star move needs a captain (the game;
            self.fields["captain"].set(1)                                  # a definition's own "captain": 0 would win)
            self.show_captain(1)
            self.move_note.configure(text=f"{self.name} now has captain star moves: a star swing or pitch needs "
                                          "them.")
        if key == "batting_item":
            self.items_changed()
        self.show_problems()

    def edit_ability(self, label):
        """The Abilities tab on this ability (the list's label: "Catch: Tongue Catch (ours)" -> "Tongue Catch")."""
        name = label.split(": ", 1)[-1].replace(" (ours)", "")
        self.app.abilities.show(name)
        if not self.embedded:
            self.win.lower()

    def always_picked(self):
        base = bool(self.move_base("always_item"))
        on = self.always.get()
        self.app.set_setting([self.name], "always_item", gui_as_is() if on == base else on)
        self.items_changed()

    def use_creation(self, key, path):
        """A player's swing / pitch picked here goes in the game: its Create page's "Use in my game", through the
        page's own checks (how many, what works yet). True when it's used."""
        page = create_page(self.app, {"star swing": "swings", "star pitch": "pitches", "batting_item": "items"}[key])
        if page is None:
            return False
        import creation_editor as ce
        if ce.rel(path) in page.used:
            return True
        page.list.refresh(select=path)
        page.use_var.set(True)
        page.use_toggled()
        return ce.rel(path) in page.used

    def to_captains(self):
        tab = getattr(self.app, "captains_tab", None)
        frame = getattr(tab, "frame", None)
        if frame is not None:
            self.app.tabs.select(frame)

    def groups(self, page, groups, columns, first_row=0, stacks=None):
        """Boxes of fields: a stats-row field (patch.STAT_RANGES) goes in "stats", any other in "table_stats";
        "precharge" is the Yes / No view of windup charge frames. stacks: (column frames, {title: column}) to stack
        the boxes in columns instead of a grid."""
        self.boxes = getattr(self, "boxes", {})
        for i, (title, fields) in enumerate(groups):
            box = self.boxes[title] = ttk.LabelFrame(page, text=title, padding=(2, 4))    # (two columns in 724 px)
            import tkinter.font as tkfont                                              # (one label column)
            lw = max([tkfont.nametofont("TkDefaultFont").measure(label(f) + ":") for f in fields] or [0]) or None
            if stacks:
                box.pack(in_=stacks[0][stacks[1][title]], fill="x", padx=4, pady=3)
            else:
                box.grid(row=first_row + i // columns, column=i % columns, sticky="nsew", padx=2, pady=3)
            for field in fields:
                if field == "precharge":
                    if "windup charge frames" not in self.fields:
                        continue
                    w = ChoiceField(box, label(field), CHOICES[field], int(self.char.table["windup charge frames"]
                                                                          <= PRECHARGE_MAX), self.precharge_picked)
                    w.pack(anchor="w", pady=1)
                    widgets.tip(w, TIPS[field])
                    self.info_icon(w, field, label(field))
                    self.fields[field] = w
                    self.show_precharge()
                    continue
                key, base = ("stats", self.char.stats) if field in patch.STAT_RANGES else ("table_stats",
                                                                                           self.char.table)
                if field not in base:
                    continue
                now = self.entry().get(key, {})
                change = (lambda v, field=field, key=key, base=base: self.put(key, field, v, base[field]))
                if field == "windup charge frames":         # (its Precharge line follows it)
                    change = (lambda v, c=change: (c(v), self.show_precharge()))
                edit_button = None
                if field in CHOICES:
                    w = ChoiceField(box, label(field), CHOICES[field], base[field], change, label_width=lw)
                    if field == "baserunning ability" and getattr(self.app, "abilities", None) is not None:
                        edit_button = ttk.Button(box, text="Edit this ability...", style="Toolbutton",   # its own row:
                                                 command=lambda w=w: self.edit_ability(w.var.get()))   # Stats 724 wide
                else:                   # any value its field holds; past the game's own range, kept with an amber
                    lo, hi, kind = patch.STAT_RANGES[field] if field in patch.STAT_RANGES else                         patch.TABLE_RANGES[field]           # warning (Nick); patch.HARD_LIMITS stay the game's
                    kind = int if field in patch.STAT_RANGES else kind
                    room = patch.stat_room(field)
                    limit = None if room == (lo, hi) else (lo, hi, (lambda t: t[0].upper() + t[1:])(patch.past_limit_note(field)))
                    w = widgets.NumberField(box, label(field), *room, stock=base[field], kind=kind,
                                            step=1 if kind is int else round((hi - lo) / 100, 3), on_change=change,
                                            width=4, short=True, limit=limit, label_width=lw)
                w.pack(anchor="w", pady=1)
                if edit_button is not None:
                    edit_button.pack(anchor="e", pady=(0, 1))
                w.set(now.get(field, base[field]))
                widgets.tip(w, TIPS.get(field))
                icon = widgets.info(w, label(field), getattr(patch, "FIELD_DATA", {}).get(field))   # git-dc's data
                if icon is not None:
                    icon.pack(side="right") if not w.grid_slaves() else icon.grid(row=0, column=9, padx=4)
                self.fields[field] = w
        for c in range(columns):
            page.columnconfigure(c, weight=1)

    # --- chemistry: one value per pair, the same both ways

    def build_chemistry(self):
        page = ttk.Frame(self.tabs, padding=6)
        self.tabs.add(page, text="Chemistry")
        ttk.Label(page, foreground=widgets.GREY, wraplength=700,
                  text=f"Chemistry is the same both ways: what you set here for {self.name} and someone else counts "
                       f"for them too. Click rows to pick several (click again to drop one; Shift-click for a range, or Select all), then Good, Neutral or Bad."
                  ).pack(anchor="w")
        top = ttk.Frame(page)
        top.pack(fill="x", pady=4)
        ttk.Label(top, text="Find:").pack(side="left")
        self.chem_filter = tk.StringVar()
        ttk.Entry(top, textvariable=self.chem_filter, width=20).pack(side="left", padx=4)
        self.chem_filter.trace_add("write", lambda *a: self.refresh_chemistry())
        self.changed_only = tk.BooleanVar()
        ttk.Checkbutton(top, text="Changed only", variable=self.changed_only,
                        command=self.refresh_chemistry).pack(side="left", padx=8)
        body = ttk.Frame(page)
        body.pack(fill="both", expand=True)
        self.chem = ttk.Treeview(body, columns=("now", "stock"), selectmode="extended", height=12)   # (all of it at 760 x 600)
        self.chem.heading("#0", text="With")
        self.chem.heading("now", text="Chemistry")
        self.chem.heading("stock", text="Stock")
        self.chem.column("#0", width=260)
        self.chem.column("now", width=120)
        self.chem.column("stock", width=120)
        self.chem.tag_configure("changed", font="SluggersSection")
        bar = ttk.Scrollbar(body, orient="vertical", command=self.chem.yview)
        self.chem.configure(yscrollcommand=bar.set)
        self.chem.pack(side="left", fill="both", expand=True)
        self.chem.bind("<Button-1>", self.chem_click)   # a plain click adds or drops a row (Nick); Shift: a range
        self.chem_anchor = None
        bar.pack(side="left", fill="y")
        buttons = ttk.Frame(page)
        buttons.pack(fill="x", pady=4)
        for word in ("good", "neutral", "bad"):
            ttk.Button(buttons, text=word.capitalize(), command=lambda w=word: self.set_chemistry(w)).pack(side="left")
        ttk.Button(buttons, text="Stock", command=lambda: self.set_chemistry(None)).pack(side="left", padx=8)
        ttk.Button(buttons, text="Select all", command=lambda: self.chem.selection_set(self.chem.get_children())
                   ).pack(side="right")         # the rows shown: with Find and Changed only (Nick)
        ttk.Button(buttons, text="Deselect all", command=lambda: self.chem.selection_set(())).pack(side="right",
                                                                                                    padx=4)
        others = [e for e in self.app.roster() if e[0] != self.name]
        try:                                    # every family together, as on the select grid (family_order)
            others = family_order(self.app, self.char.stock.dol, others)
        except (KeyError, ValueError, IndexError):
            pass                                # (a game without the stock grid tables: the roster's order)
        self.others = {e[0]: e for e in others}
        self.refresh_chemistry()

    def chem_click(self, ev):
        """A click toggles its row; Shift-click picks every row from the last clicked one to this one."""
        row = self.chem.identify_row(ev.y)
        if not row or self.chem.identify_region(ev.x, ev.y) not in ("tree", "cell"):
            return None
        if ev.state & 0x0001 and self.chem_anchor and self.chem.exists(self.chem_anchor):   # Shift
            rows = list(self.chem.get_children())
            a, b = sorted((rows.index(self.chem_anchor), rows.index(row)))
            self.chem.selection_add(rows[a:b + 1])
        elif row in self.chem.selection():
            self.chem.selection_remove(row)
        else:
            self.chem.selection_add(row)
        if not ev.state & 0x0001:
            self.chem_anchor = row
        self.chem.focus(row)
        return "break"

    def chem_now(self, other):
        """(the pair's value as a word, where it's kept: this name or the other's, or None for the build's own)."""
        for holder, them in ((self.name, other), (other, self.name)):
            for ref, v in (self.entry(holder).get("chemistry") or {}).items():
                if v is not None and self.app.char_name(ref) == them:
                    return (CHEM_WORDS.get(v, v) if isinstance(v, int) else v), holder
        return CHEM_WORDS[self.char.chem_of(self.others[other])], None

    def refresh_chemistry(self):
        if not hasattr(self, "chem"):
            return
        keep = set(self.chem.selection())
        self.chem.delete(*self.chem.get_children())
        f = self.chem_filter.get().strip().lower()
        rows = []
        for name in self.others:
            now, held = self.chem_now(name)
            if (f and f not in name.lower()) or (self.changed_only.get() and held is None):
                continue
            rows.append((held is None, name, now))
        for i, (same, name, now) in enumerate(sorted(rows, key=lambda r: r[0])):   # changed first, roster order kept
            stock = CHEM_WORDS[self.char.chem_of(self.others[name])]
            self.chem.insert("", "end", iid=name, text=name, values=(now.capitalize(), stock.capitalize()),
                             tags=() if same else ("changed",))
        self.chem.selection_set([n for n in keep if self.chem.exists(n)])

    def set_chemistry(self, word):
        names = list(self.chem.selection())
        if not names:
            messagebox.showinfo("Chemistry", "Pick one or more characters in the list first.", parent=self.win)
            return
        for other in names:
            base = CHEM_WORDS[self.char.chem_of(self.others[other])]
            for ref in [r for r in (self.entry(other).get("chemistry") or {}) if self.app.char_name(r) == self.name]:
                self.put("chemistry", ref, None, None, name=other)      # one value per pair, kept here
            for ref in [r for r in (self.entry().get("chemistry") or {}) if self.app.char_name(r) == other]:
                self.put("chemistry", ref, None, None)
            self.put("chemistry", other, word or base, base)
        self.refresh_chemistry()

    # --- names

    def build_names(self, page):
        """One line at the top of Stats (Nick): English, Spanish and French side by side, Same in all, whether the
        English one fits the name plate, and Stock."""
        row = ttk.Frame(page)
        row.grid(row=0, column=0, columnspan=2, sticky="ew", padx=4, pady=(0, 3))
        self.name_vars = {}
        if self.char.mii:
            ttk.Label(row, text="Names: Miis can't be renamed.").pack(side="left")
            return
        widgets.tip(row, "The name on the select screen's name plate and the pitching-change banner is the English "
                         "one; the other languages show in the game's menus in that language.")
        for lang, title in patch.LANGUAGES.items():
            ttk.Label(row, text=title + ":").pack(side="left", padx=(0 if lang == "en" else 6, 2))
            v = tk.StringVar()
            e = ttk.Entry(row, textvariable=v, width=13)
            e.pack(side="left")
            e.bind("<KeyRelease>", lambda ev: self.name_changed())
            e.bind("<FocusOut>", lambda ev: self.name_changed())
            self.name_vars[lang] = (v, e)
            if lang == "en":
                self.name_note = ttk.Label(row, text="", foreground=widgets.GREY)   # (the English one's fit)
                self.name_note.pack(side="left", padx=(2, 0))
        self.same_name = tk.BooleanVar(value=True)
        same = ttk.Checkbutton(row, text="Same in all", variable=self.same_name, command=self.name_changed)
        same.pack(side="left", padx=(6, 0))
        widgets.tip(same, "The same name in every language." + ("" if per_language_names() else
                    " A different name in each language isn't in the patcher yet: keep this ticked for now."))
        stock = ttk.Button(row, text="Stock", width=5, command=self.reset_name)
        stock.pack(side="left", padx=(6, 0))
        widgets.tip(stock, "Back to the stock name")
        self.fill_names()

    def names(self):
        """{language: name} as the build will have it."""
        nm = self.entry().get("name", self.name)
        return {lang: (nm if isinstance(nm, str) else nm.get(lang) or nm.get("en") or self.name)
                for lang in patch.LANGUAGES}

    def fill_names(self):
        if not self.name_vars:
            return
        names = self.names()
        self.same_name.set(len(set(names.values())) == 1)
        for lang, (v, _) in self.name_vars.items():
            v.set(names[lang])
        self.name_state()

    def name_state(self):
        same = self.same_name.get()
        for lang, (_, e) in self.name_vars.items():
            e.state(["disabled"] if same and lang != "en" else ["!disabled"])
        en = self.name_vars["en"][0].get().strip()
        self.name_note.configure(text="" if not en else "fits" if patch.name_fits(en) else "too wide",
                                 foreground=widgets.GREY if not en or patch.name_fits(en) else widgets.RED)

    def name_changed(self):
        if self.same_name.get():
            en = self.name_vars["en"][0].get()
            for lang, (v, _) in self.name_vars.items():
                if lang != "en":
                    v.set(en)
        texts = {lang: v.get().strip() for lang, (v, _) in self.name_vars.items()}
        self.name_state()
        if not texts["en"]:
            self.problem_label.configure(text="Type a name, or press Stock beside the names.", foreground=widgets.RED)
            return
        value = texts["en"] if len(set(texts.values())) == 1 else texts
        self.put("name", None, value, self.name)

    def reset_name(self):
        self.put("name", None, self.name, self.name)
        self.fill_names()


def open_for(app, names):
    """The Characters tab's button: the editor on the one picked character, on the player's game (for an ISO, once
    it's read: app.last_char_editor)."""
    if len(names) != 1:
        messagebox.showinfo("Edit a character", "Pick one character on the left, then Edit stats, chemistry and "
                                                "names.")
        return None
    entry = next((e for e in app.roster() if e[0] == names[0]), None)
    if entry is None:
        return None

    def show(game):
        win = tk.Toplevel(app.root)
        win.transient(app.root)
        app.last_char_editor = CharEditor(win, app, entry, game.dol)
        return app.last_char_editor
    return app.recolor_game(show, what="The character editor shows each character's stats, chemistry and names as "
                                        "they are in your game.")
