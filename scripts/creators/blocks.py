"""Creations: the shared file format and block schema of the creators (docs/item-creator.md, "The creation file").

Items: git-f3. Star swings, star pitches and hazards: git-95 (their blocks register here too). The window: git-b6.

A creation is one file, <name>.slgitem / .slgswing / .slgpitch / .slghazard:

    {"kind": "item", "format": 1, "name": "Bullet Bill", "from": "bullet-bill" | null,
     "files": ["bullet-bill-icon.png"],                   # our own files that travel with it (never game bytes)
     "blocks": {"<key>": {"type": "<block type>", <fields>}, ...}}

A block's key is its type, except where a kind allows two of one type (then any key, the type says which).
Every field has a Field: its type, range, unit and a plain-words label (the window shows them; nobody sees JSON),
and `src`, where the range comes from (docs/customization-inventory.md). problems(creation) lists what is wrong in
plain words (the window shows them); check(creation) raises Invalid with them (the build).

Registering a block (git-95): BLOCKS["cutin"] = Block("Cut-in", {...fields...}); KIND_BLOCKS["swing"] |= {"cutin"}.
Per-kind limits on shared values: ALLOWED[("effect", "kind")]["pitch"] = {...}. Kind-wide rules (e.g. which
blocks an item's chassis takes): RULES[kind].append(fn(creation) -> [problems]).
"""
import json
from pathlib import Path

FORMAT = 1
EXTENSIONS = {"item": ".slgitem", "swing": ".slgswing", "pitch": ".slgpitch", "hazard": ".slghazard"}
KINDS = tuple(EXTENSIONS)
PRESETS = Path(__file__).resolve().parent / "presets"


class Invalid(ValueError):
    """A creation the schema refuses; str() is the plain-words list of problems."""


class Field:
    """One value. type: "float", "int", "bool", "enum", "text", "color" ([r, g, b] or [r, g, b, a], 0..255),
    "list" (of `of`, `length` fixed or up to `max_len`), "group" (a dict of `fields`), "block" (a nested block
    of type `block`). optional: null is allowed (it means "the chassis's own" / "none")."""

    def __init__(self, type, label, unit="", lo=None, hi=None, choices=(), of=None, length=None, max_len=None,
                 fields=None, block=None, optional=False, default=None, src="", check=None, deprecated=None,
                 data=None):
        self.type, self.label, self.unit, self.lo, self.hi = type, label, unit, lo, hi
        self.choices, self.of, self.length, self.max_len = tuple(choices), of, length, max_len
        self.fields, self.block, self.optional, self.default, self.src = fields or {}, block, optional, default, src
        self.check = check                                   # fn(value) -> problem text or None
        self.deprecated = deprecated                         # why the window hides it (old files still load)
        self.data = data                                     # what it changes in the game's data (the window's "i")

    def problems(self, value, where):
        if value is None:
            return [] if self.optional else [f"{where}: {self.label} is missing"]
        t = self.type
        if t in ("float", "int"):
            if isinstance(value, bool) or not isinstance(value, (int, float)) or (t == "int" and not isinstance(value, int)):
                return [f"{where}: {self.label} must be {'a whole number' if t == 'int' else 'a number'}"]
            if (self.lo is not None and value < self.lo) or (self.hi is not None and value > self.hi):
                return [f"{where}: {self.label} {value} is outside {self.lo}..{self.hi}{' ' + self.unit if self.unit else ''}"]
            return []
        if t == "bool":
            return [] if isinstance(value, bool) else [f"{where}: {self.label} must be on or off"]
        if t == "enum":
            return [] if value in self.choices else [f"{where}: {self.label} {value!r} isn't one of {list(self.choices)}"]
        if t == "text":
            if not isinstance(value, str) or not value.strip():
                return [f"{where}: {self.label} must be some text"]
            if self.max_len and len(value) > self.max_len:
                return [f"{where}: {self.label} is longer than {self.max_len} letters"]
            bad = self.check(value) if self.check else None
            return [f"{where}: {bad}"] if bad else []
        if t == "color":
            ok = isinstance(value, list) and len(value) in (3, 4) and all(
                isinstance(c, int) and not isinstance(c, bool) and 0 <= c <= 255 for c in value)
            return [] if ok else [f"{where}: {self.label} must be 3 or 4 numbers 0..255"]
        if t == "list":
            if not isinstance(value, list):
                return [f"{where}: {self.label} must be a list"]
            if self.length is not None and len(value) != self.length:
                return [f"{where}: {self.label} needs exactly {self.length}"]
            if self.max_len is not None and len(value) > self.max_len:
                return [f"{where}: {self.label} takes at most {self.max_len}"]
            return [p for i, v in enumerate(value) for p in self.of.problems(v, f"{where} {i + 1}")]
        if t == "group":
            if not isinstance(value, dict):
                return [f"{where}: {self.label} must be a group of settings"]
            return fields_problems(self.fields, value, f"{where}, {self.label}")
        if t == "block":
            return block_problems(value, f"{where}, {self.label}", want=self.block)
        raise AssertionError(f"field type {t!r}")

    def describe(self):
        """The field for the window: JSON-able."""
        d = {"type": self.type, "label": self.label, "unit": self.unit, "optional": self.optional, "src": self.src}
        for k in ("lo", "hi", "length", "max_len", "default", "block", "deprecated", "data"):
            if getattr(self, k) is not None:
                d[k] = getattr(self, k)
        if self.choices:
            d["choices"] = list(self.choices)
        if self.of:
            d["of"] = self.of.describe()
        if self.fields:
            d["fields"] = {k: f.describe() for k, f in self.fields.items()}
        return d


class Block:
    def __init__(self, label, fields, data=None):
        self.label, self.fields, self.data = label, fields, data


def fields_problems(fields, value, where):
    out = [f"{where}: unknown setting {k!r}" for k in value if k not in fields and k != "type"]
    for k, f in fields.items():
        out += f.problems(value.get(k, None if k in value else f.default), where)
    return out


def block_problems(block, where, want=None, kind=None):
    if not isinstance(block, dict) or block.get("type") not in BLOCKS:
        return [f"{where}: not a known block (type {block.get('type') if isinstance(block, dict) else block!r})"]
    if want and block["type"] != want:
        return [f"{where}: must be a {BLOCKS[want].label} block, not {block['type']!r}"]
    out = fields_problems(BLOCKS[block["type"]].fields, block, where)
    for (btype, name), per_kind in ALLOWED.items():
        if btype == block["type"] and kind in per_kind and name in block:
            v = block[name]
            for x in (v if isinstance(v, list) else [v]):
                if x is not None and x not in per_kind[kind]:
                    out.append(f"{where}: {BLOCKS[btype].fields[name].label} {x!r} isn't possible for {_a(kind)} "
                               f"(possible: {sorted(per_kind[kind])})")
    return out


def _a(kind):
    return ("an " if kind[0] in "aeiou" else "a ") + kind


def _glyphs(text):
    import sys
    sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
    import abilities
    missing = abilities.missing_glyphs(text)
    return f"no letter for {missing} in the game's label font (renaming it is the way)" if missing else None


# ------------------------------------------------------------------------------------------------ shared blocks
# Ranges: docs/customization-inventory.md. [N] Nick's feedback in commits, [T] a test, [D] a docstring, [I] inferred.
ITEMS = ("shell", "fireball", "bobomb", "pow", "banana", "boo")      # stock items (icons to hue-turn)
MODELS = ("fireball", "pow", "star-bit", "ring", "circus-ball", "bullet-bill", "own")   # ours and the chassis's, by
#                                                                    name; "own": the player's .obj (look.obj)
DRAWN_ICONS = ("ice", "star-bits", "circus-ball", "ring", "bullet-bill")   # drawn by our code (bullet-bill: rendered
#                                                                           from the player's game)

_n = lambda label, lo, hi, unit="", src="", **kw: Field("float", label, unit, lo, hi, src=src, **kw)  # noqa: E731
_i = lambda label, lo, hi, unit="", src="", **kw: Field("int", label, unit, lo, hi, src=src, **kw)    # noqa: E731

BLOCKS = {
    "given": Block("Who gets it", {
        "roulette": Field("list", "Roulette weight", of=_i("weight", 0, 255), length=3,
                          default=[0, 0, 0], src="[T] starbits_roulette: 0..255 a row"),
        "characters": Field("list", "Always brings it", of=Field("text", "character"), default=[],
                            deprecated="a character's own \"batting_item\" (the item's name) now"),
        "always": Field("bool", "Given whatever the chemistry", default=False,
                        deprecated="a character's own \"always_item\" now"),
    }),
    "launch": Block("Throw", {
        "count": Field("enum", "Balls", choices=(1, 3, 4, 5, 6, 7, 8), default=3,
                       src="[D] ludwig_fire: a pool of up to MAX_BALLS (8); past 5 a longer spread table"),
        "speed": _n("Speed", 0.5, 3.0, "x stock", "[N] 2.75+ too fast skimming, 0.6 too slow homing", default=1.0),
        "level": Field("bool", "Leaves the hand level (no upward speed)", default=False),
        "gravity": _n("Gravity", 0.0, 0.2, "per frame", "[D] stock 0.02; skim 0.1; Bill 0", optional=True),
    }),
    "move": Block("Movement", {
        "path": Field("enum", "Path", choices=("straight", "bounce", "home", "skim", "ground"), default="straight"),
        "bounce": Field("group", "Bounce", optional=True, fields={
            "factor": _n("Bounce factor", 0.0, 1.0, "", "[D] stock 0.3; Lemmy 0.8"),
            "min_hop": _n("Smallest hop speed", 0.0, 1.0, "", "[D] stock 0.3; Lemmy 0.35")}),
        "home": Field("group", "Homing", optional=True, fields={
            "turn_deg": _n("Turn rate", 0.0, 3.0, "degrees a frame", "[N] 3.0 too good; 1.5"),
            "spawn_dist": _n("Appears this far short of its target", 0.0, 120.0, "m", "[N] 10 too close; 60; 0 = no jump"),
            "target": Field("enum", "Homes on", choices=("nearest", "P", "C", "1B", "2B", "3B", "SS", "LF", "CF", "RF"),
                            optional=True, default="nearest")}),
        "hop": Field("group", "Hops", optional=True, fields={
            "height": _n("Hop height", 0.0, 3.0, "m", "[I] bits 0.8, rings 0.7"),
            "frames": _n("Frames a hop", 1.0, 240.0, "frames", "[D] must be above 0")}),
        "wander": Field("group", "Wanders", optional=True, fields={
            "speed": _n("Speed", 0.0, 0.3, "m a frame", "[I] rings 0.09"),
            "range": _n("Range from where it landed", 1.0, 20.0, "m", "[I] rings 9"),
            "twist": _n("Turn at the edge", 0.0, 90.0, "degrees", "[I] rings 35")}),
        "orbit": Field("group", "Circles", optional=True, fields={
            "radius": _n("Circle size", 0.0, 3.0, "m", "[T] bits 0.6"),
            "frames": _n("Frames a circle", 1.0, 600.0, "frames", "[T] bits 150")}),
    }),
    "spawn": Block("Leaves behind", {
        "on": Field("enum", "When", choices=("landing", "contact", "timer"), default="landing"),
        "what": Field("enum", "What", choices=("rings", "bits", "item")),
        "count": _i("How many", 1, 36, "", "[A] bits pool 40 (4 thrown + 36 Star Shower); rings untested above 6"),
        "spread": _n("Spread", 0.0, 10.0, "m", "[I] bits 2.0", optional=True),
        "lifetime": _i("Stays for", 0, 32767, "frames", "[D] 0 = until the at-bat's items clear (bits) / "
                       "the half-inning (rings)", default=0),
        "move": Field("block", "Movement", block="move", optional=True),
        "hit": Field("block", "What it hits", block="hit", optional=True),
        "effect": Field("block", "What a hit does", block="effect", optional=True),
        "look": Field("block", "Look", block="look", optional=True),
        "item": Field("group", "Item", optional=True, fields={
            "name": Field("text", "Item creation")}),
    }),
    "hit": Block("What it hits", {
        "targets": Field("list", "Hits", of=Field("enum", "target", choices=("fielder", "ball", "runner")),
                         max_len=4, default=["fielder"]),
        "radius": _n("Hit radius", 0.1, 3.0, "m", "[I] rings 0.55; items: the chassis's own", optional=True),
        "dodge_height": _n("Jumped over from this high", 0.0, 2.0, "m", "[N] Bill 0.2", optional=True),
    }),
    "effect": Block("What a hit does", {
        "kind": Field("enum", "Effect", choices=("stun", "freeze", "knockdown", "slip", "quake", "meter", "spin")),
        "slide_speed": _n("Slide speed", 0.0, 3.0, "", "[N] Bill 0.3, Lemmy 2.0; 1.0 x 35 was crazy", optional=True),
        "slide_frames": _i("Slide length", 0, 120, "frames", "[N] Bill 15, Lemmy 50", optional=True),
        "delta": _i("Star meter change", -250, 250, "(50 = a star)", "[D] meter 0..250", optional=True),
        "spin_frames": _i("Spins for", 20, 300, "frames (60 a second)", "[I] spin_effect: the stun's timer, "
                          "default 90", optional=True),
        "freeze_frames": _i("Frozen for", 10, 600, "frames (60 a second)", "[D] stock 120 (the Ice Garden table "
                            "0x807979B8; 100 at 50 Hz)", optional=True),
        "quake_radius": _n("Quake reaches", 2.0, 40.0, "m", "[C] POW 20 (its table +0x08; item_params)", optional=True),
        "slip_frames": _i("Slips for", 20, 300, "frames (60 a second)", "[C] stock 90 (a Banana's slip, a POW "
                          "quake's)", optional=True),
    }),
    "peels": Block("Banana peels", {
        "count": _i("Peels", 1, 5, "", "[C] Banana 5 (the first + 4 scattered; the item keeps 5 banana objects)",
                    optional=True),
        "spread": _n("Scatter", 1.0, 15.0, "m", "[C] Banana 5 (its table +0x14)", optional=True),
    }),
    "boo": Block("Boo", {
        "frames": _i("Stays for", 30, 600, "frames (60 a second)", "[C] Boo 180 while the ball is in play (90 "
                     "otherwise, scaled with it)", optional=True),
    }),
    "blast": Block("Explosion", {
        "fuse_frames": _i("Fuse", 10, 300, "frames (60 a second)", "[C] Bob-omb 45 (its table +0x28)", optional=True),
        "radius": _n("Blast radius", 1.0, 15.0, "m", "[C] Bob-omb 6 (its table +0x0C)", optional=True),
        "height": _n("Blast height", 1.0, 15.0, "m", "[C] Bob-omb 6 (its table +0x10)", optional=True),
    }),
    "look": Block("Look", {
        "model": Field("enum", "Model", choices=MODELS, optional=True),
        "burn": Field("bool", "Burning look on a hit (a Fireball's; unset: on for a Fireball look, off for others)",
                      optional=True),
        "obj": Field("text", "Your own model (.obj, with its .mtl and textures in the files; up to about 300 "
                             "triangles with a 128 x 128 texture, 400 with 64 x 64)", optional=True),
        "scale": _n("Size", 0.25, 3.0, "x", "[N] Bill 0.5 barely visible", default=1.0),
        "height": _n("Drawn this far up", 0.0, 3.0, "m", "[N] Bill 0.9", optional=True),
        "colors": Field("list", "Colours", of=Field("color", "colour"), max_len=8, default=[]),
        "trail": Field("group", "Trail colour", optional=True, fields={
            "hue": _n("Hue turn from orange", 0.0, 1.0, "", "[D] Ice 0.52, Ludwig 0.56"),
            "lighten": _n("Lighten", 0.0, 1.0, "", "[D] Larry 0.3", default=0.0)}),
        "icon": Field("group", "HUD icon", optional=True, fields={
            "from": Field("enum", "Stock icon to recolour", choices=ITEMS, optional=True),
            "hue": _n("Hue turn", 0.0, 1.0, "", optional=True),
            "lighten": _n("Lighten", 0.0, 1.0, "", optional=True),
            "draw": Field("enum", "One of our drawn icons", choices=DRAWN_ICONS, optional=True),
            "png": Field("text", "Picture (27 x 29)", optional=True)}),
    }),
    "sound": Block("Sounds", {
        "launch": _i("Throw", 0, 0xFFFF, "stock sound id", optional=True),
        "launch_clip": Field("text", "Throw (your own .wav, up to 3 s)", optional=True),
        "hit_clip": Field("text", "Hit (your own .wav, up to 3 s)", optional=True),
        "land_clip": Field("text", "Landing (your own .wav, up to 3 s)", optional=True),
        "hit": _i("Hit", 0, 0xFFFF, "stock sound id", optional=True),
        "land": _i("Landing", 0, 0xFFFF, "stock sound id", optional=True),
    }),
    "label": Block("Name on the card", {
        "text": Field("text", "Name", max_len=24, check=_glyphs),
    }),
    "item": Block("Item", {
        "chassis": Field("enum", "Built on", choices=("thrown-ball", "lob", "lob-hazards", "shell", "bobomb",
                                                     "banana", "boo")),
    }),
}

KIND_BLOCKS = {
    "item": {"item", "given", "launch", "move", "spawn", "hit", "effect", "blast", "peels", "boo", "look", "sound",
             "label"},
    "swing": {"move", "spawn", "hit", "effect", "look", "sound", "label"},
    "pitch": {"move", "spawn", "hit", "effect", "look", "sound", "label"},
    "hazard": {"move", "spawn", "hit", "effect", "look", "sound"},
}
# Shared values a kind can't use (yet): item hits reach fielders, runners (the stock fall; runner_hits.py) and the
# ball (the batter isn't offered), and "meter" has no item path.
ALLOWED = {
    ("effect", "kind"): {"item": {"stun", "freeze", "knockdown", "slip", "quake", "spin"},
                         "hazard": {"stun", "freeze", "knockdown", "slip", "spin"}},
    ("hit", "targets"): {"item": {"fielder", "ball", "runner"}, "hazard": {"fielder", "ball"}},
    ("spawn", "what"): {"item": {"rings", "bits"}},
}

# ------------------------------------------------------------------------------------------------ kind rules
# An item's chassis decides its blocks (docs/item-creator.md, "The item kind").
CHASSIS = {
    "thrown-ball": {"blocks": {"launch", "move", "hit", "effect", "look"}, "paths": {"straight", "bounce", "home", "skim"}},
    "lob": {"blocks": {"hit", "effect", "look"}, "paths": set()},
    "lob-hazards": {"blocks": {"spawn", "look"}, "paths": set()},
    # the stock items as they are: a renamed copy with its own icon, roulette weights and characters
    "shell": {"blocks": {"launch", "hit", "effect", "look"}, "paths": set()},
    "bobomb": {"blocks": {"hit", "blast", "look"}, "paths": set()},
    "banana": {"blocks": {"hit", "peels", "effect", "look"}, "paths": set()},
    "boo": {"blocks": {"boo", "look"}, "paths": set()},
}
STOCK_CHASSIS = ("shell", "bobomb", "banana", "boo")
# The chassis whose stock item knocks runners down (runner_hits.py: the stock runner checks). An item hits runners
# when its hit targets have "runner"; with no hit targets, as its chassis (DEFAULT_TARGETS)
RUNNER_CHASSIS = ("thrown-ball", "lob", "lob-hazards", "shell", "bobomb", "banana")
DEFAULT_TARGETS = {c: ["fielder", "runner"] if c in RUNNER_CHASSIS else ["fielder"] for c in CHASSIS}
# What each chassis lets you change, in plain words (the window shows it next to "Built on")
CHASSIS_NOTES = {
    "thrown-ball": "A Fireball throw: how many balls, speed, bounce, homing, gravity, trail colour, what a hit does "
                   "(stun, freeze, knockdown, spin), the model, the icon, who gets it.",
    "lob": "A POW lob that quakes where it lands: the icon and who gets it.",
    "lob-hazards": "A lob that leaves star bits or rings behind (Star Bits and Wendy's rings only, for now): how "
                   "many, how they hop and wander, colours, the icon, who gets it.",
    "shell": "A Shell: its speed, its size (a bigger Shell also hits a bigger area), what a hit does (knockdown with "
             "its own slide, stun, freeze, spin), its icon and who gets it.",
    "bobomb": "The Bob-omb as it is: its own name, icon, roulette weights and characters.",
    "banana": "The Bananas as they are: their own name, icon, roulette weights and characters.",
    "boo": "The Boo as it is: its own name, icon, roulette weights and characters.",
}
ALWAYS_ITEM = {"item", "given", "sound", "label"}


def _item_rules(c):
    b = c["blocks"]
    item = b.get("item")
    if not item:
        return ["an item needs its Item block"]
    ch = CHASSIS.get(item.get("chassis"))
    if not ch:
        return []                                            # the field check says why
    out = [f"{BLOCKS[t].label} doesn't apply to an item built on {item['chassis']}"
           for t in sorted({blk.get("type") for blk in b.values()} - ch["blocks"] - ALWAYS_ITEM) if t in BLOCKS]
    mv = b.get("move")
    if mv and mv.get("path") not in ch["paths"]:
        out.append(f"Movement path {mv.get('path')!r} doesn't apply to an item built on {item['chassis']}")
    if mv and mv.get("path") == "bounce" and not mv.get("bounce"):
        out.append("Movement: a bouncing path needs its Bounce settings")
    if mv and mv.get("path") == "home" and not mv.get("home"):
        out.append("Movement: a homing path needs its Homing settings")
    hit = b.get("hit") or {}
    if hit.get("targets") is not None and "fielder" not in hit["targets"]:
        out.append("What it hits: an item always hits fielders (tick Fielder)")
    if item["chassis"] != "thrown-ball" and hit.get("dodge_height") is not None:
        out.append(f"What it hits: only a thrown ball can be jumped over")
    if item["chassis"] in ("shell", "boo") and hit.get("radius") is not None:
        out.append("What it hits: a Shell's reach comes with its size (Look)" if item["chassis"] == "shell" else
                   "What it hits: a Boo hits no one")
    if (b.get("effect") or {}).get("quake_radius") is not None and item["chassis"] != "lob":
        out.append("What a hit does: only a lob quakes")
    if (b.get("effect") or {}).get("slip_frames") is not None and item["chassis"] not in ("banana", "lob"):
        out.append("What a hit does: only a Banana's slip or a lob's quake lasts a number of slip frames")
    if item["chassis"] == "banana" and b.get("effect") and b["effect"].get("kind") != "slip":
        out.append("What a hit does: a Banana makes fielders slip")
    sp_hit = (b.get("spawn") or {}).get("hit") or {}
    if "runner" in (sp_hit.get("targets") or ()):
        out.append("Leaves behind: what it leaves behind can't hit runners yet")
    eff = b.get("effect")
    if item["chassis"] == "lob" and eff and eff.get("kind") != "quake":
        out.append("an item built on lob can only quake (or do nothing)")
    if eff and eff.get("kind") == "knockdown" and (eff.get("slide_speed") is None or eff.get("slide_frames") is None):
        out.append("What a hit does: a knockdown needs its slide speed and length")
    sp = b.get("spawn")
    if item["chassis"] == "lob-hazards" and not sp:
        out.append("an item built on lob-hazards needs Leaves behind")
    if sp and sp.get("what") == "bits" and sp.get("count") != 4:
        out.append("Leaves behind: star bits come 4 at a time for now (the per-bit tables have 4 entries)")
    if sp and sp.get("move") and sp["move"].get("path") != "ground":
        out.append("Leaves behind: things left on the ground move along the ground (path 'ground')")
    look = b.get("look") or {}
    own = ("type", "icon", "scale") if item["chassis"] == "shell" else ("type", "icon")
    if item["chassis"] in STOCK_CHASSIS and any(look.get(k) not in (None, [], 1.0) for k in look if k not in own):
        out.append(f"Look: an item built on {item['chassis']} keeps its own look (only its "
                   f"{'size and ' if item['chassis'] == 'shell' else ''}icon can change)")
    launch = b.get("launch") or {}
    if item["chassis"] == "shell" and any(launch.get(k) not in (None, v) for k, v in
                                          (("count", 1), ("level", False), ("gravity", None))):
        out.append("Throw: a Shell is one shell along the ground (only its speed can change)")
    if item["chassis"] == "shell" and eff and eff.get("kind") not in ("stun", "freeze", "knockdown", "spin"):
        out.append("What a hit does: a Shell can knock down, stun, freeze or spin")
    icon = look.get("icon")
    if icon and sum(icon.get(k) is not None for k in ("from", "draw", "png")) != 1:
        out.append("HUD icon: pick one of a recoloured stock icon, one of our drawn icons, or a picture")
    return out


RULES = {"item": [_item_rules], "swing": [], "pitch": [], "hazard": []}


# ------------------------------------------------------------------------------------------------ files
def problems(c):
    """What is wrong with creation c, in plain words ([] = fine)."""
    if not isinstance(c, dict):
        return ["not a creation"]
    out = []
    if c.get("kind") not in KINDS:
        return [f"unknown kind {c.get('kind')!r} (one of {list(KINDS)})"]
    if c.get("format") != FORMAT:
        out.append(f"made by a different version (format {c.get('format')!r}, this is {FORMAT})")
    if not isinstance(c.get("name"), str) or not c["name"].strip():
        out.append("it needs a name")
    if c.get("from") is not None and not isinstance(c.get("from"), str):
        out.append("'from' must be a preset name or empty")
    files = c.get("files", [])
    if not isinstance(files, list) or not all(isinstance(f, str) and f and not Path(f).is_absolute() and ".." not in Path(f).parts
                                              for f in files):
        out.append("files must be names next to the creation (no folders above it)")
    unknown = set(c) - {"kind", "format", "name", "from", "files", "blocks"}
    out += [f"unknown setting {k!r}" for k in sorted(unknown)]
    blocks = c.get("blocks")
    if not isinstance(blocks, dict):
        return out + ["it has no blocks"]
    kind = c["kind"]
    for key, blk in blocks.items():
        t = blk.get("type") if isinstance(blk, dict) else None
        where = BLOCKS[t].label if t in BLOCKS else key
        if t in BLOCKS and t not in KIND_BLOCKS[kind]:
            out.append(f"{where} isn't part of {_a(kind)}")
            continue
        out += block_problems(blk, where, kind=kind)
    if not out:
        for rule in RULES[kind]:
            out += rule(c)
    return out


def check(c):
    """Raise Invalid (plain words) unless c is a valid creation; returns c."""
    p = problems(c)
    if p:
        raise Invalid(f"{c.get('name', 'creation') if isinstance(c, dict) else 'creation'}: " + "; ".join(p))
    return c


def load(path):
    """A creation file -> the checked creation (its kind must match the file's extension)."""
    path = Path(path)
    c = json.loads(path.read_text(encoding="utf8"))
    kind = next((k for k, ext in EXTENSIONS.items() if ext == path.suffix.lower()), None)
    if kind is None:
        raise Invalid(f"{path.name}: not a creation file ({', '.join(EXTENSIONS.values())})")
    if isinstance(c, dict) and c.get("kind") != kind:
        raise Invalid(f"{path.name}: says it's a {c.get('kind')!r}, but the file is a {kind}")
    return check(c)


def save(c, folder):
    """Write checked creation c to folder/<name><extension>; returns the path."""
    check(c)
    safe = "".join(ch if ch.isalnum() or ch in " -_" else "_" for ch in c["name"]).strip()
    path = Path(folder) / (safe + EXTENSIONS[c["kind"]])
    path.write_text(json.dumps(c, indent=1, ensure_ascii=False) + "\n", encoding="utf8")
    return path


def presets(kind):
    """{preset name (its file stem): creation} of one kind, from scripts/creators/presets/."""
    return {p.stem: load(p) for p in sorted(PRESETS.glob("*" + EXTENSIONS[kind]))}


def schema():
    """Everything the window needs, JSON-able: blocks, fields, ranges, units, labels, which kind takes which."""
    return {"format": FORMAT, "extensions": EXTENSIONS,
            "blocks": {t: {"label": b.label, "fields": {k: f.describe() for k, f in b.fields.items()},
                           **({"data": b.data} if b.data else {})} for t, b in BLOCKS.items()},
            "kind_blocks": {k: sorted(v) for k, v in KIND_BLOCKS.items()},
            "allowed": [{"block": b, "field": f, "per_kind": {k: sorted(v) for k, v in per.items()}}
                        for (b, f), per in ALLOWED.items()],
            "chassis": {k: {"blocks": sorted(v["blocks"]), "paths": sorted(v["paths"]), "notes": CHASSIS_NOTES[k],
                            "default_targets": DEFAULT_TARGETS[k]} for k, v in CHASSIS.items()}}


# ------------------------------------------------------------------------------------------------ what it changes
# The window's "i" (git-92 for Nick: "little i icons everywhere that explain what is changed in the data"): per block
# and field, what the build changes in the game's data. Stock addresses (the clean NTSC-U game); main.dol unless said.
# Items: git-f3. Shared blocks (effect, hit, look, move, sound, spawn, label): as items use them; swings, pitches and
# hazards reach the same fields through their own modules (git-95).
_USE = ("An item keeps its own id (7 and up) until it is used; at use, ice_item's stub at 0x80456734 (lwz r4,0x338(r31) "
        "in the use function FUN_80456710) turns it into its stock item and writes the item's id to the variant byte "
        "(our data), which every item hook below reads.")
DATA = {
    ("item", None): {"file": "main.dol", "where": "the item manager COjyamaManager (r13-0x354): item +0x338 per slot, "
                     "the active item +0x394", "hook": _USE, "notes": "item-creator", "source": "scripts/ice_item.py"},
    ("item", "chassis"): {"file": "main.dol", "where": "ice_item's base table (our data): item id -> the stock item it "
                          "becomes (0 Shell, 1 Fireball, 2 Bob-omb, 3 POW, 4 Banana, 5 Boo)",
                          "field": "one byte per item id", "hook": _USE, "source": "scripts/ice_item.py, scripts/creators/items.py"},
    ("given", None): {"file": "main.dol", "where": "the item roulette FUN_804583c4 and the item checks FUN_8045453c",
                      "notes": "item-creator", "source": "scripts/starbits_roulette.py"},
    ("given", "roulette"): {"file": "main.dol", "where": "the roulette weights: stock at 0x80630FB0, 3 rows (the batting "
                            "team behind by 6 or more, 3 to 5, 0 to 2 or ahead) of 6 bytes (items 0-5); our copy in our "
                            "data holds every item",
                            "field": "a byte 0-255 per row: the item's weight", "hook": "FUN_804583c4 (the pick) and "
                            "FUN_8045453c (enabled?) branch to our copies", "source": "scripts/starbits_roulette.py"},
    ("launch", None): {"file": "main.dol", "where": "the Fireball's launch FUN_8045327c and its followers FUN_804533a8",
                       "source": "scripts/koopa_items.py, scripts/ludwig_fire.py, scripts/shell_item.py"},
    ("launch", "count"): {"file": "main.dol", "where": "the Fireball follower loop in the use function (0x8045693C "
                          "rlwinm r3,r31,...; the spread bytes at 0x80456914, the cap cmplwi r0,4 at 0x80456978)",
                          "field": "how many Fireball objects one throw launches (stock 3; the pool grows to 8)",
                          "hook": "koopa_items FOLLOW, ludwig_fire", "source": "scripts/ludwig_fire.py"},
    ("launch", "speed"): {"file": "main.dol", "where": "the Fireball table 0x80631298 +4 (0.4 / 0.6 per frame), read by "
                          "lfs f31,4(r4) at 0x804532C8; the Shell's by lfs at 0x80459478",
                          "field": "a multiplier on the stock launch speed", "hook": "koopa_items SPEED, shell_item LAUNCH",
                          "source": "scripts/koopa_items.py, scripts/shell_item.py"},
    ("launch", "level"): {"file": "main.dol", "where": "the launch's upward speed: stfs f0,0x14(r31) at 0x80453318",
                          "field": "on: 0 (the ball leaves the hand level)", "hook": "koopa_items LAUNCH_VY",
                          "source": "scripts/koopa_items.py"},
    ("launch", "gravity"): {"file": "main.dol", "where": "the Fireball table 0x80631298 +0xC (0.02 a frame), read by lfs "
                            "f1,0xc(r11) at 0x80453564 in the update FUN_804534c4",
                            "field": "a float, per frame", "hook": "koopa_items GRAVITY", "source": "scripts/koopa_items.py"},
    ("blast", None): {"file": "main.dol", "where": "the Bob-omb's table 0x80631058: 2 rows x 60 / 50 Hz of 0x3C bytes",
                      "hook": "at use our routine copies the item's rows over the stock ones (item_params)",
                      "source": "scripts/item_params.py"},
    ("blast", "fuse_frames"): {"file": "main.dol", "where": "the Bob-omb's table 0x80631058 +0x28",
                               "field": "a float, frames (stock 45; 38 at 50 Hz): the timer FUN_8044fb40 arms when it "
                               "touches a fielder", "source": "scripts/item_params.py"},
    ("blast", "radius"): {"file": "main.dol", "where": "the Bob-omb's table 0x80631058 +0x0C",
                          "field": "a float, metres (stock 6): the explosion's reach (FUN_8044faf0: the fielder check in "
                          "FUN_80117408, the runners' in FUN_80176d30)", "source": "scripts/item_params.py"},
    ("blast", "height"): {"file": "main.dol", "where": "the Bob-omb's table 0x80631058 +0x10",
                          "field": "a float, metres (stock 6): the explosion's height (FUN_8044fb18)",
                          "source": "scripts/item_params.py"},
    ("peels", None): {"file": "main.dol", "where": "the Banana's scatter FUN_8044ed58 and its table 0x80631148",
                      "source": "scripts/item_params.py"},
    ("peels", "count"): {"file": "main.dol", "where": "the scatter loop's bound cmplwi r31,4 at 0x8044EEA4 (4 more peels "
                         "after the first, over the item manager's 5 banana objects at +0x1BC)",
                         "field": "fewer peels for this item", "hook": "item_params.peel_gate", "source": "scripts/item_params.py"},
    ("peels", "spread"): {"file": "main.dol", "where": "the Banana's table 0x80631148 +0x14",
                          "field": "a float, metres (stock 5): how far each extra peel lands from the first",
                          "source": "scripts/item_params.py"},
    ("boo", None): {"file": "main.dol", "where": "the Boo (COjyamaTeresa) at use, FUN_80459a58",
                    "source": "scripts/item_params.py"},
    ("boo", "frames"): {"file": "main.dol", "where": "DAT_807A1640 + mode * 4: +2 while the ball is live, +0 otherwise; "
                        "stored to the Boo's +0x38 at 0x80459B4C / 0x80459B14",
                        "field": "a s16, frames (stock 180 / 90; 150 / 75 at 50 Hz)", "hook": "item_params.boo_gate",
                        "source": "scripts/item_params.py"},
    ("effect", None): {"file": "main.dol", "where": "the Fireball's hit on a fielder FUN_80117838 (the stun call at "
                       "0x801179F8), the Shell's FUN_8011703c", "source": "scripts/ice_item.py, scripts/shell_item.py"},
    ("effect", "kind"): {"file": "main.dol", "where": "the hit call at 0x801179F8 (bl FUN_8012a140, the stun)",
                         "field": "stun FUN_8012a140, freeze FUN_80129d14, knockdown FUN_80128b48, spin (the stun, "
                         "spinning in place), slip FUN_8012a99c, quake (the POW's)", "hook": "ice_item's hit stub",
                         "source": "scripts/ice_item.py, scripts/spin_effect.py"},
    ("effect", "slide_speed"): {"file": "main.dol", "where": "the knocked-down fielder's slide: +0x130",
                                "field": "a float (stock 0.3)", "source": "scripts/ice_item.py"},
    ("effect", "slide_frames"): {"file": "main.dol", "where": "the knocked-down fielder's slide time: +0x206",
                                 "field": "a s16, frames (stock 40)", "source": "scripts/ice_item.py"},
    ("effect", "delta"): "The batting team's star meter (*(r13-0x1540), 50 a star) changes by this on a hit (swings and "
                         "pitches; git-95's).",
    ("effect", "spin_frames"): {"file": "main.dol", "where": "the stunned fielder's timer +0x200; while it runs "
                                "FUN_8012a5c0 turns him 0x1000 a frame (lha r0,0x44(r3) at 0x8012A630) and doesn't walk",
                                "field": "frames (5/6 of it at 50 Hz)", "source": "scripts/spin_effect.py"},
    ("effect", "freeze_frames"): {"file": "main.dol", "where": "the frozen fielder's thaw timer +0x20C (stock from "
                                  "0x807979B8: 120, 100 at 50 Hz)", "field": "frames", "source": "scripts/ice_item.py"},
    ("effect", "quake_radius"): {"file": "main.dol", "where": "the POW's table 0x806311D8 +0x08",
                                 "field": "a float, metres (stock 20): who the quake reaches (FUN_8045905c)",
                                 "source": "scripts/item_params.py"},
    ("effect", "slip_frames"): {"file": "main.dol", "where": "the slipping fielder's +0x214, from the table 0x80625F20 "
                                "+ mode * 0x68 + 0x4A; stored at 0x8012ACA4", "field": "a s16, frames (stock 90, 75 at "
                                "50 Hz)", "hook": "item_params.slip_gate", "source": "scripts/item_params.py"},
    ("hit", None): {"file": "main.dol", "where": "each item's fielder check in FUN_8011703c's dispatch (FUN_80117838 "
                    "Fireball, FUN_80117408 Bob-omb, FUN_80117e34 POW, FUN_80117a98 Banana) and the runners' "
                    "(FUN_8015830c)", "source": "scripts/ice_item.py, scripts/runner_hits.py"},
    ("hit", "targets"): {"file": "main.dol", "where": "runners: the six calls to FUN_8017726c (the runner's fall) in the "
                         "runner checks, 0x80176D0C .. 0x80177240", "field": "unticked Runner: those calls skip the fall "
                         "for this item", "hook": "runner_hits", "source": "scripts/runner_hits.py"},
    ("hit", "radius"): {"file": "main.dol", "where": "the item's table row +0 (Fireball 0x80631298, Bob-omb 0x80631058, "
                        "POW 0x806311D8, Banana 0x80631148), read by its vtable +0x1C getter",
                        "field": "a float, metres (stock 1.0; the Banana 0.8)", "source": "scripts/item_params.py"},
    ("hit", "dodge_height"): {"file": "main.dol", "where": "the Fireball's fielder check FUN_80117838: a fielder whose "
                              "feet (+8) are this far above the ball misses it (goes on at 0x80117A54)",
                              "field": "metres", "source": "scripts/ice_item.py"},
    ("look", None): {"file": "dt_na.dat dir 119 file 8 (the HUD's item icons), dir 161 (trail textures), dir 136 "
                     "(the item model package)", "source": "scripts/ice_item.py, scripts/koopa_items.py"},
    ("look", "model"): {"file": "dt_na.dat dir 136 files 0-2 (the item package), slot 0x2A's spare tail",
                        "where": "a model block drawn at each flying ball (the item models' draw, 0x8045615C)",
                        "field": "fireball (none: the flame), the circus ball, the Bullet Bill, or your own",
                        "source": "scripts/lemmy_balls.py, scripts/bullet_bill.py, scripts/own_models.py"},
    ("look", "burn"): {"file": "main.dol", "where": "li r5,0x1 at 0x80117A44: the Fireball's hit tells the player-state "
                       "object (r13-0x110, vt+0x28) the fielder was burnt", "field": "off: 0 for this item",
                       "hook": "item_params.burn_gate", "source": "scripts/item_params.py"},
    ("look", "obj"): {"file": "dt_na.dat dir 136 files 0-2, slot 0x2A from +0x21200",
                      "where": "your .obj packed as a prop block on the Shell item model's (build_prop); model-set key "
                      "0x83+, one instance per ball", "field": "about 300 triangles with a 128 px texture, 18 KB for all",
                      "source": "scripts/own_models.py"},
    ("look", "scale"): {"file": "main.dol / dt_na.dat", "where": "the Shell: its radius (table 0x80631008 via 0x8045967C) "
                        "and model scale; an own model: its largest side in metres", "source": "scripts/shell_item.py"},
    ("look", "height"): "How far above the ball's position the model is drawn (our draw code's constant, metres).",
    ("look", "colors"): "The rings' or bits' colours: per-instance colour words in our data, set on the model each frame.",
    ("look", "trail"): {"file": "dt_na.dat dir 161 (each stadium's particle file)",
                        "where": "two textures per trail colour appended, the Fireball trail's texture slots pointed at "
                        "them per item", "field": "a hue turn from the stock orange (about 10 KB of match memory each)",
                        "source": "scripts/ice_item.py"},
    ("look", "icon"): {"file": "dt_na.dat dir 119 file 8 (every language's copy)",
                       "where": "a 27 x 29 icon row appended; the roulette's icon table (stock 0x8062CE10) moved to our "
                       "data with a row per item", "source": "scripts/ice_item.py, scripts/koopa_items.py"},
    ("move", None): {"file": "main.dol", "where": "the Fireball's update FUN_804534c4", "source": "scripts/koopa_items.py"},
    ("move", "path"): {"file": "main.dol", "where": "straight (stock), bounce (0x804535E8), skim (bounce 0, no puff at "
                       "0x8045363C), home (bullet_bill's homing, called from the gravity stub 0x80453564)",
                       "source": "scripts/koopa_items.py, scripts/bullet_bill.py"},
    ("move", "bounce"): {"file": "main.dol", "where": "the Fireball's bounce: lfs f2,0x10(r3) / lfs f0,0x14(r3) at "
                         "0x804535E8 (the table's bounce factor 0.3 and minimum hop 0.3)", "field": "two floats per item",
                         "source": "scripts/koopa_items.py"},
    ("move", "home"): {"file": "main.dol", "where": "bullet_bill's homing routine per item: locks the fielder nearest "
                       "the aim point (or the chosen position's slot 0-8) on its first frame, turns the velocity "
                       "(+0x10 / +0x18) toward him each frame", "field": "degrees a frame, a jump in metres, a position",
                       "source": "scripts/bullet_bill.py"},
    ("move", "hop"): "Ring and bit hops (our pools' records in our data): height and frames per hop.",
    ("move", "wander"): "Rings' wandering (wendy_rings' per-pool values in our data): speed, range, twist.",
    ("move", "orbit"): "An orbit around the landing point (the Star Bits' per-bit tables, starbits_item).",
    ("sound", None): {"file": "main.dol, sound_NA/MY2.brsar", "source": "scripts/item_sounds.py, scripts/build_voices.py"},
    ("sound", "launch"): {"file": "main.dol", "where": "li r4,0xAE at 0x80456A98 (every item's throw sound)",
                          "field": "a sound id per item", "hook": "item_sounds THROW", "source": "scripts/item_sounds.py"},
    ("sound", "launch_clip"): {"file": "sound_NA/MY2.brsar", "where": "your .wav added to the item family (bb_ojitem_shot) "
                               "at patch time; its id replaces 0xAE for this item", "source": "scripts/build_voices.py"},
    ("sound", "hit_clip"): {"file": "sound_NA/MY2.brsar", "where": "your .wav added at patch time; played at the hit "
                            "call (0x801179F8 / 0x80117338)", "source": "scripts/build_voices.py, scripts/item_sounds.py"},
    ("sound", "land_clip"): {"file": "sound_NA/MY2.brsar", "where": "your .wav added at patch time; played where the "
                             "Fireball fizzles out (0x80453388) or the POW bursts (0x80458FA0)",
                             "source": "scripts/build_voices.py, scripts/item_sounds.py"},
    ("sound", "hit"): {"file": "main.dol", "where": "before the hit call (0x801179F8, 0x80117338 / 0x80117390): "
                       "FUN_80454008(item, id, 1)", "field": "a sound id", "source": "scripts/item_sounds.py"},
    ("sound", "land"): {"file": "main.dol", "where": "li r4,0x3AC at 0x80453388 / 0x804535B0 (the Fireball's fizzle), "
                        "li r4,0xB1 at 0x80458FA0 (the POW's burst)", "field": "a sound id", "source": "scripts/item_sounds.py"},
    ("spawn", None): {"file": "main.dol", "where": "the POW's landing (0x80458F8C) spawns our pools (rings, star bits) "
                      "kept in our data", "source": "scripts/wendy_rings.py, scripts/starbits_item.py"},
    ("spawn", "on"): "When the pool is spawned: at the lob's landing (0x80458F8C).",
    ("spawn", "what"): "Which pool: rings (wendy_rings, model-set key 0x80) or star bits (starbits_item, the item "
                       "package's slot 0x2A).",
    ("spawn", "count"): "How many records the pool keeps (our data) and model instances it loads.",
    ("spawn", "spread"): "How far from the landing point each one starts (our pool's constants).",
    ("spawn", "lifetime"): "Frames until they go (bits), or the half-inning (rings: cleared at 0x801329FC).",
    ("spawn", "move"): "How they move on the ground (our pool's per-frame tick at 0x801327FC).",
    ("spawn", "hit"): "Who they catch: each fielder's check (our hook at 0x8010C118 in the fielder update).",
    ("spawn", "effect"): "What they do to a fielder: the slip FUN_8012a99c (rings), the Banana's contact (bits).",
    ("spawn", "look"): "The pool's model (ring / star bit) and colours.",
    ("spawn", "item"): "The item creation whose pool a star move's shower uses (rings:<item>).",
    ("label", None): {"file": "dt_na.dat dir 119 files 18 / 19 (the cards' label pages)",
                      "source": "scripts/item_abilities.py, scripts/star_move_labels.py"},
    ("label", "text"): {"file": "dt_na.dat dir 119 file 19 (and 18 with captains)",
                        "where": "a label row drawn in the game's own label font on a page of ours",
                        "field": "up to 24 letters the font has", "source": "scripts/item_abilities.py"},
}


def _attach(data):
    for (t, k), d in data.items():
        if t in BLOCKS and (k is None or k in BLOCKS[t].fields):
            if k is None:
                BLOCKS[t].data = BLOCKS[t].data or d
            elif BLOCKS[t].fields[k].data is None:
                BLOCKS[t].fields[k].data = d


_attach(DATA)


def _kinds_offered():
    """The creation kinds this download's edition offers (editions/*.json "creators": the Characters Beta's items
    only), or None for every kind (the full patcher, or no edition module: a script of ours)."""
    try:
        import edition
    except ImportError:
        return None
    ed = edition.load()
    return None if not ed else set(ed.get("creators", ()))


_OFFERED = _kinds_offered()
if _OFFERED is None or "hazard" in _OFFERED:            # the kinds register their own blocks when imported: a bare
    try:                                                # blocks user reads every kind's files (git-95); an edition
        from creators import hazards as _hazards  # noqa: E402,F401   imports only its own (no hazard or star move
    except ImportError:                                 # code in the Characters Beta)
        pass
if _OFFERED is None or "swing" in _OFFERED:
    try:
        from creators import swings as _swings  # noqa: E402,F401
    except ImportError:
        pass
