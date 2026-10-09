"""Recolor tool: a recipe -> a recolored copy of a character (stock or added), as a new character on a color wheel.

  python scripts/recolor.py recolors/purple-yoshi.json [...] [--game extracted/clean] [--preview] [--dry-run]

A recipe (recolors/*.json) names a stock character and says which colors change; it holds no game art. The tool
reads the user's own game (--game: an extracted RMBE01 with sys/main.dol and files/dt_na.dat; default
extracted/clean) and writes:
  models/work/recolor/<slug>/high.bin, low.bin   the base's model blocks (dt_na dir id + 0x12, files 0 and 1)
                                                 with the rules applied to their textures, re-encoded in each
                                                 texture's own format and size (the blocks keep their length)
  models/work/recolor/<slug>/bat.bin             the base's bat (file 2) recolored (see "bat" below)
  models/work/icons/new/<slug>_side.png, _front.png
                                                 the base's own stock portraits (icon bank, dt_na dir 119 file 2:
                                                 its side / front source rows -> a cell of a CI8 atlas page),
                                                 recolored with the same rules, so they match the stock art
  characters/<id>_<slug>.json                    a character definition charbuild builds like any other: template
                                                 = base (stats, chemistry, voice, animations), its own model, icons
                                                 and bat, swatch = the recipe's, on the wheel of "wheel" (default
                                                 the base's). A recolor is a plain color variant, like the stock
                                                 ones: never a captain, no star pitch or star swing of its own
                                                 (stats +7 / +8 / +9 = 0; Nick: those are Captain Yoshi's only)
  models/work/recolor/<slug>/preview.png         with --preview: textures and portraits before / after

Recipe:
  {"name": "Purple Yoshi",            display name (also the slug: purple-yoshi)
   "base": "Green Yoshi",             character to copy (sluggers_data names or an id), or an added one (see below)
   "swatch": "purple",                wheel swatch: red blue yellow green purple black brown lightblue pink white orange
   "wheel": "Green Yoshi",            optional: whose color wheel it joins (default: the base's)
   "id": "0x7D",                      optional: character id (default: the next free one)
   "recolor": [rule, ...],            applied in order to every model texture and both portraits
   "bat": "follow" | "keep" | [rule, ...]}
                                      optional: the bat. "follow": the "recolor" rules applied to it too (their
                                      "textures" / "region" dropped: those index the body); "keep" (or []): the
                                      base's bat; rules: your own. Default (no "bat"): "follow" when the base's
                                      family gives each colour its own stock bat (Koopa Troopas, Paratroopas, Yoshis,
                                      Toads, Shy Guys, Nokis, the Bros), else "keep" (Magikoopas, Dry Bones, Piantas
                                      and Kritters share one bat), as the stock game does (Nick: "blue koopa troopa
                                      has a green bat").
Rule: {"hue": [lo, hi]                select pixels whose hue (degrees) is in [lo, hi] (wraps if lo > hi) ...
       "min_sat": 0.25,               ... with at least this saturation
       "to_hue": 280,                 new hue (degrees)
       "sat": 1.0, "val": 1.0,        saturation and brightness multipliers (black: low sat and val; white:
                                      low sat, val > 1, clamped)
       "textures": [0, 2],            optional: only these model texture indices (portraits: see "portraits")
       "region": [x0, y0, x1, y1],    optional: only inside this box, fractions of the texture (top-left origin)
       "portraits": true}             optional: false = the model only, not the portraits
A wheel holds up to wheel7.MEMBERS (10) characters; the tool refuses a recipe that would make it longer.

An added base (Nick: "allow recolors of custom added characters"): one of the build's new characters, found by name
or id in make()'s `defs` (the patcher passes its new and imported characters, asset paths absolute; default: every
characters/*.json). Its model textures come from its own "model_blocks" 0 and 1 (paths through charbuild.asset, or
bytes; a missing one: the template's file), its other model_blocks (e.g. 6-14, animation banks) are carried over
as they are, its portraits are its "icon" PNGs, and its bat is its own "bat" (a "file", or a "dir"'s file 2), else
the template's file 2. The definition is a colour variant of it: its template, voice, scale, stats (no captain,
star pitch or star swing), chemistry, table data and other plain keys, on its wheel ("wheel", else its template's).
The bat's default: "follow" when the base has its own bat, else as its template's family. A base that isn't in the
build is refused in plain words.
"""
import argparse
import json
import os
import re
import struct
import sys
from pathlib import Path

import numpy as np
from PIL import Image

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import dtna_toc  # noqa: E402
from build_model import encode_texture  # noqa: E402
from dol import Dol  # noqa: E402
from mss_model import Model  # noqa: E402
from recolor_block import ci8_palette, decode, encode_ci8, encode_ci8_palette  # noqa: E402
from sluggers_data import CHAR_NAMES, char_id as _char_id  # noqa: E402

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
MODEL_DIR_BASE, ICON_DIR, ICON_FILE = 0x12, 119, 2
SELECTOR, STOCK_IDS = 0x80631550, 0x65            # the clean game's selector table (8 bytes per id)
RES_ROW, SRC_HEADER, SRC_RECORD, TEX_BASE = 0x14, 0x28, 0x50, 0x20
VARIANT_STATS = {"captain": 0, "star pitch": 0, "star swing": 0}   # a color variant, as the stock ones
STARPITCH = 0x806288BC                          # charbuild.TABLES "starpitch": 1 byte per id, the star pitch type
SWATCHES = ("red", "blue", "yellow", "green", "purple", "black", "brown", "lightblue", "pink", "white", "orange")
# Character model-directory files 3 and 4 are the left and right fielding-glove models.
# Some characters do not request gloves at runtime; the editor simply leaves a side out when its file is not a readable model.
GLOVE_FILES = ((3, "left"), (4, "right"))


def char_id(ref):
    """A stock character's id from its name or id, with a readable error for an unknown name."""
    try:
        return _char_id(ref)
    except KeyError:
        import difflib
        near = difflib.get_close_matches(str(ref), [n.strip() for n in CHAR_NAMES if n.strip()], n=3, cutoff=0.5)
        raise AssertionError(f"unknown character {ref!r}" + (f"; did you mean {', '.join(near)}?" if near else "")) from None


def slug(name):
    return re.sub(r"[^a-z0-9]+", "-", name.lower()).strip("-")


# --- color rules -------------------------------------------------------------------------------------------

def apply_rule(rgba, rule):
    """One rule on an RGBA uint8 array (alpha kept). Hue / saturation / value math as render_icons.recolor."""
    h_, w_ = rgba.shape[:2]
    rgb = rgba[..., :3].astype(np.float32) / 255
    mx, mn = rgb.max(-1), rgb.min(-1)
    d = np.maximum(mx - mn, 1e-6)
    s = np.where(mx > 0, (mx - mn) / np.maximum(mx, 1e-6), 0)
    r, g, b = rgb[..., 0], rgb[..., 1], rgb[..., 2]
    h = np.where(mx == r, ((g - b) / d) % 6, np.where(mx == g, (b - r) / d + 2, (r - g) / d + 4)) * 60
    lo, hi = rule["hue"]
    sel = ((h >= lo) & (h <= hi)) if lo <= hi else ((h >= lo) | (h <= hi))
    sel &= s >= rule.get("min_sat", 0.25)
    if rule.get("region"):
        x0, y0, x1, y1 = rule["region"]
        box = np.zeros((h_, w_), bool)
        box[int(y0 * h_):int(y1 * h_), int(x0 * w_):int(x1 * w_)] = True
        sel &= box
    s2 = np.clip(s * rule.get("sat", 1.0), 0, 1)
    v2 = np.clip(mx * rule.get("val", 1.0), 0, 1)
    hh = (rule.get("to_hue", 0) % 360) / 60
    k = lambda n: (n + hh) % 6  # noqa: E731
    f = lambda n: v2 - v2 * s2 * np.clip(np.minimum(k(n), 4 - k(n)), 0, 1)  # noqa: E731
    new = np.stack([f(5), f(3), f(1)], -1)
    out = rgba.copy()
    out[..., :3][sel] = np.round(new[sel] * 255).astype(np.uint8)
    return out


def apply_rules(img, rules, texture=None, portrait=False):
    """PIL RGBA -> recolored PIL RGBA (rules that apply to this texture index / to portraits)."""
    arr = np.asarray(img.convert("RGBA")).copy()
    for rule in rules:
        if portrait and not rule.get("portraits", True):
            continue
        if not portrait and rule.get("textures") is not None and texture not in rule["textures"]:
            continue
        arr = apply_rule(arr, rule if not portrait else {k: v for k, v in rule.items() if k != "region"})
    return Image.fromarray(arr, "RGBA")


def bat_block(entry):
    """A stock bat (file 2) wraps its model: the model block starts at the u32 at +4 (as bat_recolors.build)."""
    return int.from_bytes(entry[4:8], "big")


def recolor_bat(entry, rules, overrides=None):
    """The bat entry with color rules and/or explicit PNG texture replacements applied."""
    member = bat_block(entry)
    block, pairs = recolor_block(bytes(entry[member:]), rules, overrides)
    return bytes(entry[:member]) + block, pairs


def own_bats(game, base):
    """True when the base's colour family gives its members their own stock bats (most shown members' file 2 differ),
    as Koopa Troopas, Yoshis, Toads, Shy Guys, Nokis and the Bros do; False when they share one."""
    import hashlib
    fam = game.selector(base)[2]
    members = [i for i in range(STOCK_IDS) if game.selector(i)[2] == fam and game.selector(i)[6]]
    # most members have their own (Dry Bones: Gray, Green and Blue share one, only Dark Bones differs -> shared)
    return len({hashlib.sha1(game.file(i + MODEL_DIR_BASE, 2)).digest() for i in members}) > len(members) / 2


def bat_rules(r, game, base):
    """The rules a recipe applies to the bat ([]: the base's bat): see the recipe's "bat" in the module doc. base: a
    stock id, or a Base (an added base with its own bat follows by default)."""
    if "bat" in r:
        choice = r["bat"]
    else:
        choice = "follow" if (base.own_bats() if isinstance(base, Base) else own_bats(game, base)) else "keep"
    if choice == "follow":
        return [{k: v for k, v in rule.items() if k not in ("textures", "region", "portraits")} for rule in r["recolor"]]
    if choice == "keep" or not choice:
        return []
    return list(choice)


def _open_override(value):
    p = Path(value)
    if not p.is_absolute():
        p = Path(ROOT) / "recolors" / p
    return Image.open(p).convert("RGBA")

def _named_override_images(recipe, key):
    """{texture index: RGBA image} for one ordinary explicit PNG replacement map in a recipe."""
    out = {}
    for k, value in (recipe.get(key) or {}).items():
        try:
            out[int(k)] = _open_override(value)
        except (OSError, ValueError, TypeError):
            continue
    return out

def _model_override_images(recipe, block_index):
    """Direct body-model replacements for one model file.

    Upgrade 5 accepts scoped keys such as ``0:3`` / ``1:3`` so high- and low-detail files can expose every
    texture independently. Old recipes whose keys are just ``3`` keep their old meaning and apply to both files.
    """
    out = {}
    for k, value in (recipe.get("texture_overrides") or {}).items():
        try:
            key = str(k)
            if ":" in key:
                file_s, tex_s = key.split(":", 1)
                if int(file_s) != int(block_index):
                    continue
                tex = int(tex_s)
            else:
                tex = int(key)
            out[tex] = _open_override(value)
        except (OSError, ValueError, TypeError):
            continue
    return out

def _override_images(recipe):
    """Legacy/high-detail view of direct model replacements."""
    return _model_override_images(recipe, 0)

def _bat_override_images(recipe):
    """Direct bat texture replacements. Only explicitly selected PNGs are read."""
    return _named_override_images(recipe, "bat_texture_overrides")

def _glove_override_images(recipe, file_index):
    """Direct fielding-glove texture replacements for model-directory file 3 (left) or 4 (right)."""
    out = {}
    for k, value in (recipe.get("glove_texture_overrides") or {}).items():
        try:
            side_s, tex_s = str(k).split(":", 1)
            if int(side_s) != int(file_index):
                continue
            out[int(tex_s)] = _open_override(value)
        except (OSError, ValueError, TypeError):
            continue
    return out


def _portrait_override_images(recipe):
    """Explicit side/front portrait PNG replacements in a recipe."""
    out = {}
    for view, value in (recipe.get("portrait_overrides") or {}).items():
        if view not in ("side", "front"):
            continue
        try:
            p = Path(value)
            if not p.is_absolute():
                p = Path(ROOT) / "recolors" / p
            out[view] = Image.open(p).convert("RGBA")
        except (OSError, ValueError, TypeError):
            continue
    return out


def recolor_block(block, rules, overrides=None):
    """A model or bat block with the rules applied to its textures -> (new block, [(before, after)]).

    overrides is an optional {texture index: PIL image}; it replaces that whole texture after ordinary recolor rules.
    """
    block = bytearray(block)
    pairs = []
    overrides = overrides or {}
    for i, tex in enumerate(Model(bytes(block)).textures):
        before = decode(bytes(block), tex).convert("RGBA")
        after = apply_rules(before, rules, texture=i)
        if i in overrides:
            custom = overrides[i].convert("RGBA")
            if custom.size != before.size:
                custom = custom.resize(before.size, Image.Resampling.LANCZOS)
            after = custom
        if np.array_equal(np.asarray(before), np.asarray(after)):
            continue
        if tex.format == 9 and i in overrides:      # CI8 (DK's, Baby DK's fur): a whole new picture, its own palette
            data, pal = encode_ci8(after)
            block[tex.image:tex.image + len(data)] = data
            block[tex.palette:tex.palette + len(pal)] = pal
            after = decode(bytes(block), tex)
        elif tex.format == 9:           # CI8, rules only: recolor the palette, the indices stay (exact; a region can't
            pal = apply_rules(ci8_palette(bytes(block), tex), [{k: v for k, v in r.items() if k != "region"}
                                                               for r in rules], texture=i)      # split a color)
            block[tex.palette:tex.palette + 512] = encode_ci8_palette(pal)
            after = decode(bytes(block), tex)
        else:
            data = encode_texture(after, tex.format, tex.payload_size())
            block[tex.image:tex.image + len(data)] = data
        pairs.append((before, after))
    return bytes(block), pairs


# --- the user's game ------------------------------------------------------------------------------------

class Game:
    def __init__(self, path):
        self.path = path
        self.dol = Dol(os.path.join(path, "sys/main.dol"))
        self.toc = dtna_toc.toc(self.dol)
        self.dat = os.path.join(path, "files/dt_na.dat")

    def file(self, d, i):
        off, length = self.toc[d][i]
        with open(self.dat, "rb") as f:
            f.seek(off)
            return f.read(length)

    def selector(self, cid):
        return self.dol.read(SELECTOR + cid * 8, 8)

    def portrait(self, cid, view):
        """A stock character's side / front portrait from the icon bank -> RGBA (CI8 atlas cell)."""
        bank = self.file(ICON_DIR, ICON_FILE)
        desc = struct.unpack_from(">I", bank, 4)[0] + 0x14          # the layout container + 0x14
        ptr = lambda field: desc + struct.unpack_from(">i", bank, desc + field)[0]  # noqa: E731
        table = ptr({"side": 0x0C, "front": 0x10}[view])
        n = struct.unpack_from(">H", bank, table + 0x24)[0]
        rows = [struct.unpack_from(">H", bank, table + SRC_HEADER + i * SRC_RECORD + 6)[0] for i in range(n)
                if struct.unpack_from(">H", bank, table + SRC_HEADER + i * SRC_RECORD + 2)[0] == cid]
        assert rows, f"no {view} portrait row for 0x{cid:02X}"
        page, _, v1, u1, v2, u2 = struct.unpack_from(">HH4f", bank, ptr(0x04) + 8 + rows[0] * RES_ROW)
        d = 0x24 + page * 0x20
        img_off, pal_off = struct.unpack_from(">II", bank, d)
        h, w = struct.unpack_from(">HH", bank, d + 8)
        x0, y0, x1, y1 = round(u1 * w), round(v1 * h), round(u2 * w), round(v2 * h)
        if bank[d + 0x17] == 14:                                     # a CMPR page (Extra Innings' own portraits,
            import cmpr                                              # e.g. its Luma's: model_import)
            return cmpr.decode(bank[TEX_BASE + img_off:TEX_BASE + img_off + w * h // 2], w, h).crop((x0, y0, x1, y1))
        assert bank[d + 0x17] == 9, f"0x{cid:02X} {view}: page {page:#x} is not CI8 or CMPR"
        pal_fmt = bank[d + 0x1A]
        pal = struct.unpack_from(">256H", bank, TEX_BASE + pal_off)
        x0, y0, x1, y1 = round(u1 * w), round(v1 * h), round(u2 * w), round(v2 * h)

        def rgba(v):
            if pal_fmt == 2:                                         # RGB5A3
                if v & 0x8000:
                    return ((v >> 10 & 31) * 255 // 31, (v >> 5 & 31) * 255 // 31, (v & 31) * 255 // 31, 255)
                return ((v >> 8 & 15) * 17, (v >> 4 & 15) * 17, (v & 15) * 17, (v >> 12 & 7) * 255 // 7)
            if pal_fmt == 1:                                         # RGB565
                return ((v >> 11 & 31) * 255 // 31, (v >> 5 & 63) * 255 // 63, (v & 31) * 255 // 31, 255)
            return (v & 255, v & 255, v & 255, v >> 8)               # IA8
        out = Image.new("RGBA", (x1 - x0, y1 - y0))
        px = out.load()
        for y in range(y0, y1):
            for x in range(x0, x1):
                tile = (y // 4) * (w // 8) + x // 8
                px[x - x0, y - y0] = rgba(pal[bank[TEX_BASE + img_off + tile * 32 + (y % 4) * 8 + x % 8]])
        return out


# keys of an added base's definition its recolor doesn't take: its own identity and art, captain / star moves (a
# colour variant never has them), and features written for one character's id (charpack.BESPOKE)
NOT_COPIED = {"id", "name", "template", "color", "model_blocks", "model_overlay", "icon", "bat", "wheel", "stats",
              "voice_dir", "captain_extras", "star swing", "star pitch", "piranha_plants", "dino_plants",
              "lemmy_ride", "ride", "star_throw"}


def _read_asset(path):
    """A definition's asset: bytes as they are, or a path (absolute, or repo-relative through charbuild.asset)."""
    if isinstance(path, (bytes, bytearray)):
        return bytes(path)
    if os.path.isabs(str(path)):
        return open(path, "rb").read()
    import charbuild
    return charbuild.asset(path).read_bytes()


class Base:
    """A recolor's base: a stock character (d None), or an added one (d: its definition, from the build's defs)."""

    def __init__(self, game, cid, name, d=None):
        self.game, self.id, self.name, self.d = game, cid, name, d
        self.template = cid if d is None else char_id(d["template"])
        self.wheel = cid if d is None else char_id(d.get("wheel", d["template"]))   # its colour wheel's host
        self.key = cid if d is None else (cid, name, json.dumps(d.get("model_blocks"), sort_keys=True, default=str))

    @property
    def added(self):
        return self.d is not None

    def block(self, i):
        """Model file i (0 high, 1 low): its own, else the template's."""
        own = (self.d or {}).get("model_blocks") or {}
        if str(i) in own or i in own:
            return _read_asset(own.get(str(i), own.get(i)))
        return self.game.file(self.template + MODEL_DIR_BASE, i)

    def portrait(self, view):
        icon = (self.d or {}).get("icon")
        if icon:
            import io
            return Image.open(io.BytesIO(_read_asset(icon[view]))).convert("RGBA")
        return self.game.portrait(self.template, view)

    def bat_entry(self):
        """The bat (a stock-style file 2 entry): its own ("file", or a "dir"'s file 2), else the template's."""
        bat = (self.d or {}).get("bat")
        if bat and bat.get("file"):
            return _read_asset(bat["file"])
        if bat and "dir" in bat:
            return self.game.file(int(str(bat["dir"]), 0), 2)
        return self.game.file(self.template + MODEL_DIR_BASE, 2)

    def own_bats(self):
        """The automatic bat choice: follow the recolor (True) or keep the base's bat. Stock: as its family's stock
        colours do; added: follow when it has a bat of its own, else as its template's family."""
        if self.added and (self.d.get("bat") or {}).get("file") or self.added and "dir" in (self.d.get("bat") or {}):
            return True
        return own_bats(self.game, self.template)


def base_of(game, ref, defs=None):
    """The Base a recipe's "base" names: a stock character on the select screen, or one of the build's added
    characters (defs: {id: (file or None, definition)}; default: every characters/*.json) by name or id. Refuses
    in plain words (AssertionError) a character that doesn't exist or isn't in this build."""
    if isinstance(ref, Base):
        return ref
    try:
        cid = char_id(ref)
    except AssertionError:
        cid = None
    if cid is not None and cid < STOCK_IDS:
        return Base(game, cid, CHAR_NAMES[cid].strip())
    defs = definitions() if defs is None else defs
    want = str(ref).strip().lower()
    for pool in (defs, imported_definitions()):               # the build's, then the player's imports (Nick: a
        for i, (_, d) in sorted(pool.items()):                  # recolor of an imported "Luma (5)")
            if str(d.get("name", "")).strip().lower() == want or i == cid and pool is defs:
                return Base(game, i, d["name"], d)
    import difflib
    names = [n.strip() for n in CHAR_NAMES if n.strip()] + [d.get("name", "") for _, d in defs.values()]
    near = difflib.get_close_matches(str(ref), names, n=3, cutoff=0.5)
    raise AssertionError(f"there's no character called {ref!r} in this build (an added character must be in the "
                         f"build: was it removed?)" + (f"; did you mean {', '.join(near)}?" if near else ""))


def template_of(ref, defs=None):
    """A recipe base's stock template, by name (no game needed): a stock base is its own; an added one its
    definition's "template"; an unknown one as it is (the pages that show a recolor before it's made)."""
    try:
        cid = char_id(ref)
        if cid < STOCK_IDS:
            return CHAR_NAMES[cid].strip()
    except AssertionError:
        cid = None
    want = str(ref).strip().lower()
    build = definitions() if defs is None else defs
    for pool in (build, imported_definitions()):                # (an import by name: its id can change)
        for i, (_, d) in pool.items():
            if str(d.get("name", "")).strip().lower() == want or pool is build and i == cid:
                return d["template"]
    return ref


# --- recipes --------------------------------------------------------------------------------------------

def load_recipe(path):
    """A recipe from its JSON file, or a recipe dict (the patcher's editor) as it is."""
    r = dict(path) if isinstance(path, dict) else json.load(open(path, encoding="utf8"))
    path = "recipe" if isinstance(path, dict) else path
    for key in ("name", "base", "swatch", "recolor"):
        assert key in r, f"{path}: missing \"{key}\""
    assert r["swatch"] in SWATCHES, f"{path}: swatch {r['swatch']!r} is not one of {', '.join(SWATCHES)}"
    bat = r.get("bat")
    for rule in r["recolor"] + (list(bat) if isinstance(bat, list) else []):   # "follow" / "keep": no rules here
        assert "hue" in rule and len(rule["hue"]) == 2, f"{path}: every rule needs \"hue\": [lo, hi]"
    return r


IMPORTED_DEST = None        # the player's imported characters (None: patch.IMPORTED_DEST if the patcher is loaded,
                            # else charpack.default_dest())


def imported_definitions():
    """{id: (None, definition)} of the player's imported characters (charpack's import folder, read as they are:
    names, templates, stats, chemistry; their model files are materialized for a build). By name is how a recipe
    finds one: import names are unique in the folder (" (2)", " (3)"...), ids can change at patch time."""
    import sys
    dest = IMPORTED_DEST or getattr(sys.modules.get("patch"), "IMPORTED_DEST", None)
    try:
        import charpack
        items = charpack.list_imported(dest) if dest else charpack.list_imported_quiet()
        return {c["id"]: (None, json.load(open(c["definition"], encoding="utf8"))) for c in items}
    except (ImportError, OSError, ValueError, KeyError):
        return {}


def definitions():
    out = {}
    for p in sorted(os.listdir(os.path.join(ROOT, "characters"))):
        if p.endswith(".json"):
            d = json.load(open(os.path.join(ROOT, "characters", p), encoding="utf8"))
            out[int(d["id"], 16) if isinstance(d["id"], str) else d["id"]] = (p, d)
    return out


def wheel_count(game, wheel, defs, skip_id):
    """Characters on `wheel`'s color wheel: its shown stock members, plus definitions on it (not on a grid square)."""
    import charbuild
    family = game.selector(wheel)[2]
    stock = sum(1 for i in range(STOCK_IDS) if game.selector(i)[2] == family and game.selector(i)[6])
    squares = {n.lower() for sq in charbuild.GRID_SQUARES for n in sq}
    new = 0
    for cid, (_, d) in defs.items():
        if cid == skip_id or d.get("name", "").lower() in squares:
            continue
        on = char_id(d.get("wheel", d["template"]))
        if game.selector(on)[2] == family:
            new += 1
    return stock + new


def _source(recipe):
    if isinstance(recipe, dict):
        return f"recipe {slug(recipe.get('name', ''))} from the patcher"
    return os.path.relpath(recipe, ROOT).replace(os.sep, "/")


def make(recipe_path, game, preview=False, dry_run=False, work=None, defs=None):
    """work: a folder to write into instead of the repo (the patcher, docs/patcher.md): the blocks and portraits go
    under work/recolor/<slug>/, the definition to work/characters/, with absolute paths in it. defs: {id: (file,
    definition)} of the characters the build has (default: every characters/*.json)."""
    r = load_recipe(recipe_path)
    name, s = r["name"], slug(r["name"])
    defs = definitions() if defs is None else defs
    b = base_of(game, r["base"], defs)                  # a stock character, or one of the build's added ones
    base = b.id
    wheel = char_id(r["wheel"]) if "wheel" in r else b.wheel
    wheel_name = r.get("wheel", r["base"] if not b.added else CHAR_NAMES[b.wheel].strip())
    mine = [cid for cid, (_, d) in defs.items() if d.get("name", "").lower() == name.lower()]
    cid = int(r["id"], 16) if isinstance(r.get("id"), str) else r.get("id") or (mine[0] if mine else max(defs) + 1)
    assert cid not in defs or cid in mine, f"id 0x{cid:02X} is {defs[cid][1]['name']}"
    import wheel7
    place = placement(game, b, defs, r, cid)             # an added base: its own square (charbuild.join_squares)
    square = b.name if place["square"] else None
    count = place["count"] + 1
    if square:
        assert count <= wheel7.MEMBERS, (f"{name}: {b.name}'s square would hold {count} characters (at most "
                                         f"{wheel7.MEMBERS}); move one of them to another square first")
        wheel_name = f"{b.name}'s square"
    else:
        assert count <= wheel7.MEMBERS, f"{name}: {wheel_name}'s wheel would hold {count} (at most {wheel7.MEMBERS})"

    home = ROOT if work is None else os.path.abspath(work)
    rel = {"out": f"models/work/recolor/{s}", "icon": "models/work/icons/new"} if work is None else         {k: os.path.join(home, v).replace(os.sep, "/") for k, v in (("out", f"recolor/{s}"), ("icon", "recolor/icons"))}
    out_dir = os.path.join(home, rel["out"])
    icons = {v: os.path.join(home, f"{rel['icon']}/{s}_{v}.png") for v in ("side", "front")}
    log, sheet = [], []
    blocks, extra = {}, {}
    for i, part in ((0, "high"), (1, "low")):
        overrides = _model_override_images(r, i)
        block, pairs = recolor_block(b.block(i), r["recolor"], overrides)
        blocks[part] = block
        sheet += pairs
        log.append(f"{part}: {len(pairs)} texture(s) changed")
    glove_blocks = {}
    for file_index, side in GLOVE_FILES:
        overrides = _glove_override_images(r, file_index)
        if not overrides:
            continue
        try:
            block, pairs = recolor_block(b.block(file_index), [], overrides)
        except Exception as e:
            log.append(f"{side} glove: kept as it is ({type(e).__name__})")
            continue
        if pairs:
            glove_blocks[file_index] = block
            sheet += pairs
            log.append(f"{side} glove: {len(pairs)} texture(s) changed")
    bat = None
    rules = bat_rules(r, game, b if b.added else base)
    bat_overrides = _bat_override_images(r)
    why = bat_problem(game, b) if (rules or bat_overrides) else None
    if why:
        log.append(f"bat: kept as it is ({why})")
    elif rules or bat_overrides:
        bat, pairs = recolor_bat(b.bat_entry(), rules, bat_overrides)
        sheet += pairs
        log.append(f"bat: {len(pairs)} texture(s) changed")
        if not pairs:
            bat = None
    portraits = {}
    portrait_overrides = _portrait_override_images(r)
    for view in ("side", "front"):
        before = b.portrait(view)
        after = apply_rules(before, r["recolor"], portrait=True)
        if view in portrait_overrides:
            custom = portrait_overrides[view].convert("RGBA")
            if custom.size != before.size:
                custom = custom.resize(before.size, Image.Resampling.LANCZOS)
            after = custom
        portraits[view] = after
        sheet.append((before, after))
    definition = {"id": f"0x{cid:02X}", "name": name, "template": r["base"], "color": r["swatch"],
                  "_why": f"Recolor tool (python scripts/recolor.py {_source(recipe_path)}): "
                          f"{r['base']} recolored; stats, chemistry, voice and animations are {r['base']}'s.",
                  "model_blocks": {"0": f"{rel['out']}/high.bin", "1": f"{rel['out']}/low.bin"},
                  "icon": {v: f"{rel['icon']}/{s}_{v}.png" for v in ("side", "front")},
                  "stats": dict(VARIANT_STATS),
                  # Nick: a recolor has its base's stats and chemistry; the stats row is the template's already,
                  # the chemistry follows the base both ways (charbuild "chemistry_like"); captain / star moves stay 0
                  "chemistry_like": r["base"]}
    # a captain base's star pitch type is 0 (none); made a non-captain it takes Breaking ball (1), as the character
    # window's PLAIN_TYPE does: a non-captain's type is never none (git-f4). Every stock-colour base has one already.
    if not b.added and game.dol.read(STARPITCH + b.template, 1)[0] == 0:
        definition["table_stats"] = {"star pitch type": 1}
    if b.added:                                             # a colour variant of an added character
        d = b.d
        definition["template"] = d["template"]
        definition["_why"] = (f"Recolor tool (python scripts/recolor.py {_source(recipe_path)}): {b.name} (added) "
                              f"recolored; stats, chemistry, voice and animations are {b.name}'s.")
        definition["stats"] = dict(d.get("stats") or {}, **VARIANT_STATS)
        definition["chemistry_like"] = r["base"]
        for k, v in d.items():
            if k not in NOT_COPIED and not k.startswith("_"):
                definition[k] = v
        for k, v in sorted((d.get("model_blocks") or {}).items(), key=lambda kv: int(kv[0])):
            if int(k) in (0, 1):
                continue
            if isinstance(v, (bytes, bytearray)):           # a block given as bytes (not a file): written beside
                extra[str(int(k))] = bytes(v)
                v = f"{rel['out']}/file{int(k)}.bin"
            definition["model_blocks"][str(int(k))] = v     # the same file as the base's (e.g. animation banks)
        if d.get("wheel") and "wheel" not in r:
            definition["wheel"] = d["wheel"]
        if square:                                          # on the base's square (charbuild.join_squares); the
            definition["square"] = square                   # wheel stays the fallback where it has none
    # Explicit glove PNG edits become the recolor's own file 3 / 4 blocks. They override an added base's carried copy.
    for file_index, block in glove_blocks.items():
        definition["model_blocks"][str(file_index)] = f"{rel['out']}/glove{file_index}.bin"
    if "wheel" in r:
        definition["wheel"] = r["wheel"]
    if bat is not None:
        definition["bat"] = {"file": f"{rel['out']}/bat.bin",
                             "_why": f"the base's bat, recolored (recipe \"bat\": {r.get('bat', 'default')})"}
    def_path = os.path.join(home, "characters", mine and defs[mine[0]][0] or f"0x{cid:02x}_{s.replace('-', '_')}.json")
    if not dry_run:
        os.makedirs(out_dir, exist_ok=True)
        os.makedirs(os.path.dirname(icons["side"]), exist_ok=True)
        os.makedirs(os.path.dirname(def_path), exist_ok=True)
        for part, block in blocks.items():
            open(os.path.join(out_dir, f"{part}.bin"), "wb").write(block)
        for file_index, block in glove_blocks.items():
            open(os.path.join(out_dir, f"glove{file_index}.bin"), "wb").write(block)
        if bat is not None:
            open(os.path.join(out_dir, "bat.bin"), "wb").write(bat)
        for k, data in extra.items():
            open(os.path.join(out_dir, f"file{k}.bin"), "wb").write(data)
        for view, img in portraits.items():
            img.save(icons[view])
        if not mine or defs[mine[0]][1].get("_why", "").startswith("Recolor tool"):
            open(def_path, "w", encoding="utf8").write(json.dumps(definition, indent=1) + "\n")
        else:
            log.append(f"{os.path.basename(def_path)} kept (not written by this tool)")
    if preview and sheet:
        cell = 96
        img = Image.new("RGBA", (cell * 2 + 12, (cell + 6) * len(sheet)), (40, 40, 48, 255))
        for n, (a, b) in enumerate(sheet):
            for k, im in enumerate((a, b)):
                t = im.copy()
                t.thumbnail((cell, cell))
                img.alpha_composite(t, (k * (cell + 12), n * (cell + 6)))
        os.makedirs(out_dir, exist_ok=True)
        img.save(os.path.join(out_dir, "preview.png"))
        log.append(f"preview: {os.path.join(out_dir, 'preview.png')}")
    return [f"{name} (0x{cid:02X}, {r['base']} on {wheel_name if square else wheel_name + chr(39) + 's wheel'}, "
            f"{count} there, swatch "
            f"{r['swatch']}): " + "; ".join(log) + ("" if not dry_run else " [dry run: nothing written]")]


# --- the editor API (the patcher window's recolor editor, git-f4): no recipe file, nothing written ---------------

# Each swatch's color on the color wheel: the stock keys of the popup's swatch element (dt_na dir 119 file 19,
# element 0xAD, key time = swatch index, vertex color at +0x40); orange is gridcells' recolored end key.
SWATCH_RGB = {"red": (0xCB, 0x0D, 0x0D), "blue": (0x00, 0x90, 0xF4), "yellow": (0xE4, 0xCC, 0x00),
              "green": (0x15, 0xB2, 0x11), "purple": (0x9C, 0x00, 0xE4), "black": (0x41, 0x41, 0x41),
              "brown": (0x88, 0x5D, 0x3B), "lightblue": (0x46, 0xE7, 0xFF), "pink": (0xFF, 0x9A, 0xE4),
              "white": (0xF0, 0xF0, 0xF0), "orange": (0xFF, 0x80, 0x00)}
_TEXTURES = {}


def _textures_for_block(game, base, block_index=0, defs=None):
    """[(texture index, RGBA PIL image)] for any readable model-directory file, cached per base and file."""
    b = base_of(game, base, defs) if not isinstance(base, int) or base >= STOCK_IDS else Base(game, base, "")
    key = (os.path.abspath(game.path), b.key, int(block_index))
    if key not in _TEXTURES:
        block = b.block(block_index)
        _TEXTURES[key] = [(i, decode(block, t).convert("RGBA")) for i, t in enumerate(Model(block).textures)]
    return _TEXTURES[key]

def _textures(game, base, defs=None):
    """High-detail body textures (file 0), kept as the colour-analysis API used by older code."""
    return _textures_for_block(game, base, 0, defs)


def _hsv(arr):
    rgb = arr[..., :3].astype(np.float32) / 255
    mx, mn = rgb.max(-1), rgb.min(-1)
    d = np.maximum(mx - mn, 1e-6)
    s = np.where(mx > 0, (mx - mn) / np.maximum(mx, 1e-6), 0)
    r, g, b = rgb[..., 0], rgb[..., 1], rgb[..., 2]
    h = np.where(mx == r, ((g - b) / d) % 6, np.where(mx == g, (b - r) / d + 2, (r - g) / d + 4)) * 60
    return h, s, mx


def nearest_swatch(rgb):
    """The SWATCH_RGB name closest to an (r, g, b) color."""
    return min(SWATCH_RGB, key=lambda k: sum((a - b) ** 2 for a, b in zip(SWATCH_RGB[k], rgb)))


def base_colors(game, base, n=6, min_share=0.01, defs=None):
    """The base character's main colors over its model textures, largest first:
    [{"hue": [lo, hi], "min_sat": x, "rgb": (r, g, b), "share": 0-1, "textures": [i, ...]}]. share is of all opaque
    texels; hue, min_sat and textures drop straight into a rule (textures: the ones the color is in, so a rule leaves
    the others alone, e.g. eye textures with a stray pixel of it). Greys and whites aren't colors here (no hue to
    select); a color is a peak of the hue histogram (5-degree bins) out to the valleys on either side. base: a stock
    character, or an added one (defs: as make's)."""
    tex = [(i, np.asarray(img)) for i, img in _textures(game, base, defs)]
    hs, ss, vs, ids, rgbs = [], [], [], [], []
    for i, a in tex:
        opaque = a[..., 3] > 0
        h, s_, v = _hsv(a)
        hs.append(h[opaque]); ss.append(s_[opaque]); vs.append(v[opaque]); ids.append(np.full(opaque.sum(), i))
        rgbs.append(a[..., :3][opaque].astype(np.float64))
    h, sat, val, tid, rgb = (np.concatenate(x) for x in (hs, ss, vs, ids, rgbs))
    total = max(len(h), 1)
    colored = (sat >= 0.2) & (val >= 0.12)
    bins = np.bincount((h[colored] // 5).astype(int) % 72, minlength=72).astype(float)
    smooth = sum(np.roll(bins, k) for k in (-1, 0, 1)) / 3
    peaks = [b for b in range(72) if smooth[b] > 0 and smooth[b] >= smooth[b - 1] and smooth[b] > smooth[(b + 1) % 72]]
    out = []
    for pk in peaks:
        lo = hi = pk
        for step, side in ((-1, "lo"), (1, "hi")):              # out to the valley or 3 % of the peak
            b = pk
            for _ in range(35):
                nb = (b + step) % 72
                if smooth[nb] < smooth[pk] * 0.03 or smooth[nb] > smooth[b] * 1.05:
                    break
                b = nb
            lo, hi = (b, hi) if side == "lo" else (lo, b)
        lo_deg, hi_deg = lo * 5, (hi * 5 + 5) % 360 or 360
        in_hue = ((h >= lo_deg) & (h < hi_deg)) if lo_deg < hi_deg else ((h >= lo_deg) | (h < hi_deg))
        sel = in_hue & colored
        if sel.sum() / total < min_share:
            continue
        med = float(np.median(sat[sel]))
        min_sat = round(min(0.4, max(0.15, med * 0.5)), 2)
        sel = in_hue & (sat >= min_sat) & (val >= 0.12)
        mean = rgb[sel].mean(0) if sel.any() else np.zeros(3)
        count = int(sel.sum())
        per_tex = [i for i, a in tex if (tid[sel] == i).sum() >= max(1, 0.02 * (a[..., 3] > 0).sum())]
        out.append({"hue": [lo_deg, hi_deg % 360 if hi_deg != 360 else 360], "min_sat": min_sat,
                    "rgb": tuple(int(round(m)) for m in mean), "share": round(count / total, 4),
                    "textures": per_tex})
    out.sort(key=lambda c: -c["share"])
    return out[:n]


def color_in(game, base, hue, min_sat=0.25, textures=None, defs=None):
    """A colour of the base's model textures picked by a hue range (a hand-made rule, or a row added in the editor):
    {"hue", "min_sat", "rgb": its mean colour, "share": 0-1 of all opaque texels, "textures"?} as base_colors gives.
    textures: only these texture indices (None: all). No texel in range: rgb is the range's middle hue."""
    import colorsys
    lo, hi = hue
    rgb_sum, count, total = np.zeros(3), 0, 0
    for i, img in _textures(game, base, defs):
        a = np.asarray(img)
        opaque = a[..., 3] > 0
        total += int(opaque.sum())
        if textures is not None and i not in textures:
            continue
        h, s_, _ = _hsv(a)
        sel = (((h >= lo) & (h <= hi)) if lo <= hi else ((h >= lo) | (h <= hi))) & (s_ >= min_sat) & opaque
        if sel.any():
            rgb_sum += a[..., :3][sel].astype(np.float64).sum(0)
            count += int(sel.sum())
    if count:
        rgb = tuple(int(round(c)) for c in rgb_sum / count)
    else:
        mid = ((lo + ((hi - lo) % 360) / 2) % 360) / 360
        rgb = tuple(round(c * 255) for c in colorsys.hsv_to_rgb(mid, 0.7, 0.7))
    out = {"hue": [lo, hi], "min_sat": min_sat, "rgb": rgb, "share": round(count / max(total, 1), 4)}
    if textures is not None:
        out["textures"] = list(textures)
    return out


def rule_to(color, rgb):
    """A rule that turns `color` (a base_colors entry) into `rgb`: its hue, and saturation / brightness scaled
    toward target / source. Shading is kept: every texel keeps its brightness relative to the color's. For a
    colorful target the scale is the ratio's square root (a swatch's bright UI color at full ratio turned Yoshi's
    green neon); black, white and greys (target saturation < 0.25 or brightness < 0.35) take the full ratio, as
    black-yoshi / white-yoshi (low saturation, brightness down / up, clamped at white)."""
    import colorsys
    th, ts, tv = colorsys.rgb_to_hsv(*(c / 255 for c in rgb))
    _, cs, cv = colorsys.rgb_to_hsv(*(c / 255 for c in color["rgb"]))
    k = 1.0 if ts < 0.25 or tv < 0.35 else 0.5
    rule = {"hue": list(color["hue"]), "min_sat": color["min_sat"], "to_hue": round(th * 360),
            "sat": round((ts / max(cs, 1e-3)) ** k, 3), "val": round((tv / max(cv, 1e-3)) ** k, 3)}
    if color.get("textures"):
        rule["textures"] = list(color["textures"])
    return rule


def target_of(color, rule):
    """The colour a rule turns `color` (a base_colors / color_in entry) toward: rule_to undone, so
    rule_to(color, target_of(color, rule)) gives the rule's to_hue, sat and val back (to rounding)."""
    import colorsys
    _, cs, cv = colorsys.rgb_to_hsv(*(c / 255 for c in color["rgb"]))
    sat, val = float(rule.get("sat", 1.0)), float(rule.get("val", 1.0))
    ts, tv = cs * sat ** 2, cv * val ** 2                   # a colourful target: rule_to took the square root
    if ts < 0.25 or tv < 0.35:
        ts, tv = cs * sat, cv * val                         # black, white, greys: the full ratio
    ts, tv = min(max(ts, 0.0), 1.0), min(max(tv, 0.0), 1.0)
    return tuple(round(c * 255) for c in colorsys.hsv_to_rgb((rule.get("to_hue", 0) % 360) / 360, ts, tv))


def color_name(rgb):
    """A plain name for a colour: red, orange, tan, brown, yellow, green, teal, blue, purple, pink, black, grey,
    white."""
    import colorsys
    h, s, v = colorsys.rgb_to_hsv(*(c / 255 for c in rgb))
    h *= 360
    if v < 0.18:
        return "black"
    if s < 0.18:
        return "white" if v > 0.8 else "grey"
    if h < 15 or h >= 340:
        return "red"
    if h < 45:
        return "brown" if v < 0.55 else "tan" if s < 0.6 else "orange"
    if h < 70:
        return "yellow"
    if h < 165:
        return "green"
    if h < 195:
        return "teal"
    if h < 255:
        return "blue"
    if h < 290:
        return "purple"
    return "pink"


def preview_pairs(recipe, game, bat=False, defs=None):
    """[(label, before, after)] of a recipe dict: every model texture the rules change, both portraits, and with
    bat=True the bat's textures its rules change (a bat that can't be recolored is left out). Writes nothing; fast
    after the first call for a base (textures are cached)."""
    r = load_recipe(recipe)
    b = base_of(game, r["base"], defs)
    pairs = []
    # Show every texture from both body model files. File 1 can contain textures that file 0 does not (including
    # small face/eye assets on some characters), so the editor must not derive its list from high-detail only.
    for block_index, label in ((0, "high"), (1, "low")):
        try:
            textures = _textures_for_block(game, b, block_index, defs)
        except Exception:
            textures = []
        overrides = _model_override_images(r, block_index)
        for i, img in textures:
            after = apply_rules(img, r["recolor"], texture=i)
            if i in overrides:
                custom = overrides[i].convert("RGBA")
                if custom.size != img.size:
                    custom = custom.resize(img.size, Image.Resampling.LANCZOS)
                after = custom
            pairs.append((f"{label} texture {i}", img, after))
    # Fielding gloves are separate model files (3/4), not body textures. Show them too when readable.
    for file_index, side in GLOVE_FILES:
        try:
            textures = _textures_for_block(game, b, file_index, defs)
        except Exception:
            textures = []
        overrides = _glove_override_images(r, file_index)
        for i, img in textures:
            after = img
            if i in overrides:
                custom = overrides[i].convert("RGBA")
                if custom.size != img.size:
                    custom = custom.resize(img.size, Image.Resampling.LANCZOS)
                after = custom
            pairs.append((f"{side} glove {i}", img, after))
    portrait_overrides = _portrait_override_images(r)
    for view in ("side", "front"):
        img = b.portrait(view)
        after = apply_rules(img, r["recolor"], portrait=True)
        if view in portrait_overrides:
            custom = portrait_overrides[view].convert("RGBA")
            if custom.size != img.size:
                custom = custom.resize(img.size, Image.Resampling.LANCZOS)
            after = custom
        pairs.append((f"{view} portrait", img, after))
    if bat and not bat_problem(game, b):
        rules = bat_rules(r, game, b if b.added else b.id)
        bat_overrides = _bat_override_images(r)
        try:
            entry = b.bat_entry()
            member = bat_block(entry)
            block = bytes(entry[member:])
            for i, tex in enumerate(Model(block).textures):
                before = decode(block, tex).convert("RGBA")
                after = apply_rules(before, rules, texture=i)
                if i in bat_overrides:
                    custom = bat_overrides[i].convert("RGBA")
                    if custom.size != before.size:
                        custom = custom.resize(before.size, Image.Resampling.LANCZOS)
                    after = custom
                pairs.append((f"bat texture {i}", before, after))
        except Exception:
            pass
    return pairs


def preview_images(recipe, game, cell=96, defs=None):
    """(before, after) PIL RGBA images of a recipe dict: every model texture the rules change and both portraits,
    in one column (cell px squares). Writes nothing; fast after the first call for a base (textures are cached)."""
    pairs = [(b, a) for _, b, a in preview_pairs(recipe, game, defs=defs)]
    sheets = []
    for k in (0, 1):
        sheet = Image.new("RGBA", (cell, (cell + 4) * len(pairs)), (40, 40, 48, 255))
        for n_, pair in enumerate(pairs):
            t = pair[k].copy()
            t.thumbnail((cell, cell))
            sheet.alpha_composite(t, ((cell - t.width) // 2, n_ * (cell + 4)))
        sheets.append(sheet)
    return tuple(sheets)


def bases(game, defs=None):
    """The characters a recolor can start from and the wheel it joins: every stock one the select screen shows, then
    the added ones in defs (default: characters/*.json, less the recolor tool's own): [{"id", "name", "wheel":
    [members, limit], "added": bool}]."""
    all_defs = definitions() if defs is None else defs
    out = [{"id": i, "name": CHAR_NAMES[i].strip(), "wheel": list(wheel_size(game, i, all_defs)), "added": False}
           for i in range(STOCK_IDS) if game.selector(i)[6]]
    for i, (_, d) in sorted(all_defs.items()):
        if str(d.get("_why", "")).startswith("Recolor tool") or not d.get("name"):
            continue
        try:
            b = Base(game, i, d["name"], d)
            out.append({"id": i, "name": d["name"], "wheel": list(wheel_size(game, b.wheel, all_defs)),
                        "added": True})
        except (AssertionError, KeyError, ValueError, TypeError):
            continue                    # a definition this tool can't read: not offered
    return out


def placement(game, base, defs=None, recipe=None, skip_id=None):
    """Where a recolor of `base` goes and how full it is, for make(), validate() and the editor's wheel line (git-a3):
    {"label": "Rosalina's square" | "Green Yoshi's wheel", "count": characters there now (not this recolor: skip_id /
    the recipe's name), "max": wheel7.MEMBERS, "square": True for an added base's own square (charbuild.join_squares;
    its GRID_SQUARES square, else just the base), False for a color wheel (the recipe's "wheel", else the base's)}.
    base: a Base, or a name / id (resolved in defs)."""
    import wheel7
    import charbuild
    defs = definitions() if defs is None else defs
    r = recipe or {}
    b = base if isinstance(base, Base) else base_of(game, base, defs)
    name = str(r.get("name", "")).strip().lower()
    if b.added and "wheel" not in r:
        on = next((sq for sq in charbuild.GRID_SQUARES if b.name.lower() in (n.lower() for n in sq)), [b.name])
        mates = [n for n in on if n.lower() != name]
        count = len(mates) + sum(1 for i, (_, d) in defs.items()
                                 if i != skip_id and str(d.get("square", "")).lower() == b.name.lower()
                                 and d.get("name", "").strip().lower() not in {m.lower() for m in mates} | {name})
        return {"label": f"{b.name}'s square", "count": count, "max": wheel7.MEMBERS, "square": True}
    wheel = r.get("wheel", b.name if not b.added else CHAR_NAMES[b.wheel].strip())
    count = wheel_count(game, char_id(wheel), defs, skip_id)
    return {"label": f"{wheel}'s wheel", "count": count, "max": wheel7.MEMBERS, "square": False}


def wheel_size(game, wheel, defs=None):
    """(characters on `wheel`'s color wheel, the most it can hold), e.g. (5, 10)."""
    import wheel7
    return wheel_count(game, char_id(wheel), definitions() if defs is None else defs, None), wheel7.MEMBERS


def bat_problem(game, base, defs=None):
    """Why the base's bat can't be recolored, in a few plain words, or None when it can. Never a reason to refuse a
    recipe: make() keeps the base's bat instead. base: a stock id or name, or a Base."""
    try:
        b = base_of(game, base, defs) if not isinstance(base, int) else Base(game, base, "")
        entry = b.bat_entry()
    except Exception as e:
        return f"its bat file can't be read ({type(e).__name__})"
    try:
        member = bat_block(entry)
        assert 8 <= member < len(entry), "no model inside"
        Model(bytes(entry[member:]))
    except Exception:
        return "it isn't a model the tool reads"
    return None


def validate(recipe, game, defs=None, warnings=None):
    """Problems with a recipe dict, in plain words ([] = fine): missing fields, unknown base or one that isn't in the
    build (with suggestions), a full wheel (with its count), a bad swatch, bad rules, an id or name already taken. A
    bat that can't be recolored is never a problem (make keeps the base's bat): it goes into `warnings` (a list)
    when one is given."""
    import wheel7
    r = dict(recipe)
    out = []
    for key, what in (("name", "a name"), ("base", "a character to start from"), ("swatch", "a wheel color")):
        if not r.get(key):
            out.append(f"It needs {what}.")
    if not r.get("recolor") and not r.get("texture_overrides") and not r.get("bat_texture_overrides") and not r.get("glove_texture_overrides") and not r.get("portrait_overrides"):
        out.append("It needs at least one color change or direct model/bat/glove texture or portrait PNG replacement.")
    defs = definitions() if defs is None else defs
    base = None
    if r.get("base") is not None:
        try:
            base = base_of(game, r["base"], defs)
            if not base.added and not game.selector(base.id)[6]:
                out.append(f"{r['base']} can't be recolored: start from a character on the select screen.")
                base = None
        except AssertionError as e:
            msg = str(e).replace("unknown character", "There's no character called")
            msg = msg[0].upper() + msg[1:]
            out.append(msg if msg.endswith("?") else msg + ".")
    if r.get("swatch") and r["swatch"] not in SWATCHES:
        out.append(f"{r['swatch']!r} isn't a wheel color. Use one of: {', '.join(SWATCHES)}.")
    bat = r.get("bat")
    if bat is not None and not isinstance(bat, (list, str)) or isinstance(bat, str) and bat not in ("follow", "keep"):
        out.append('The bat must be "follow", "keep" or a list of color changes.')
        bat = None
    for k, rule in enumerate(list(r.get("recolor") or []) + (list(bat) if isinstance(bat, list) else [])):
        hue = rule.get("hue")
        if not (isinstance(hue, (list, tuple)) and len(hue) == 2 and all(0 <= v <= 360 for v in hue)):
            out.append(f"Color change {k + 1} needs a hue range (two numbers from 0 to 360).")
    name = str(r.get("name") or "").strip().lower()
    mine = [cid for cid, (_, d) in defs.items() if d.get("name", "").strip().lower() == name]
    if mine and not defs[mine[0]][1].get("_why", "").startswith("Recolor tool"):
        out.append(f"{defs[mine[0]][1]['name']} is already a character: pick another name.")
    cid = r.get("id")
    if cid is not None:
        cid = int(cid, 16) if isinstance(cid, str) else int(cid)
        if cid in defs and cid not in mine:
            out.append(f"Id 0x{cid:02X} is already {defs[cid][1]['name']}.")
    if base is not None:
        try:
            place = placement(game, base, defs, r, mine[0] if mine else None)
            if place["count"] + 1 > place["max"]:
                out.append(f"{place['label'][:-len(chr(39) + 's square')]}'s square is full: it has {place['count']} "
                           f"of {place['max']}. Move one of them to another square first." if place["square"] else
                           f"{place['label'][:-len(chr(39) + 's wheel')]}'s color wheel is full: it has "
                           f"{place['count']} of {place['max']}.")
        except AssertionError as e:
            out.append(str(e) + ".")
        if warnings is not None and bat_problem(game, base):
            try:
                recolors_bat = bool(bat_rules(dict(r, recolor=list(r.get("recolor") or []), **(
                    {"bat": bat} if bat is not None else {})), game, base if base.added else base.id))
            except Exception:
                recolors_bat = True
            if recolors_bat:
                warnings.append(f"{base.name}'s bat stays as it is: {bat_problem(game, base)}.")
    return out


# What each part of the editor changes in the game's data (the patcher's "i" icons; git-92's modder layer).
DATA = {
    "base": {"file": "files/dt_na.dat",
             "where": "a stock base's model directory (dt_na dir = character id + 0x12): files 0 (high detail), 1 "
                      "(low detail), 2 (the bat), 3/4 (left/right gloves when present), and its side and front portraits in the icon bank (dir 119 file "
                      "2); an added base's own model_blocks, icon PNGs and bat",
             "text": "The new character is a copy of this one: the definition's \"template\" (stats, chemistry, voice "
                     "and animations are the base's) and the art that gets recolored.",
             "source": "scripts/recolor.py (recipe \"base\")"},
    "name": {"text": "The new character's name on the select screen (the definition's \"name\"); also the recipe's "
                     "file name, recolors/<name>.json.",
             "source": "scripts/recolor.py (recipe \"name\")"},
    "swatch": {"file": "sys/main.dol",
               "where": "the character-select table at 0x80631550, 8 bytes per character id",
               "field": "byte 7: which colour dot the colour wheel shows for the new character (the definition's "
                        "\"color\")",
               "notes": "The dots' colours are the swatch element's keys in dt_na dir 119 file 19 (element 0xAD).",
               "source": "scripts/charbuild.py; scripts/recolor.py (recipe \"swatch\")"},
    "colors": {"file": "files/dt_na.dat",
               "where": "the model textures of files 0 and 1 in the base's model directory (id + 0x12), and its two "
                        "portraits in the icon bank (dir 119 file 2), written as the new character's own copies",
               "field": "texels whose hue is in the row's range, with at least its colourfulness, get the new hue; "
                        "colourfulness and brightness scale toward the new colour, shading kept. Each texture is "
                        "re-encoded in its own format and size.",
               "text": "One rule per ticked row in the recipe's \"recolor\": {\"hue\": [lo, hi], \"min_sat\", "
                       "\"to_hue\", \"sat\", \"val\", \"textures\"}, applied in order.",
               "source": "scripts/recolor.py (apply_rule, recolor_block)"},
    "bat": {"file": "files/dt_na.dat",
            "where": "file 2 of the base's model directory (id + 0x12): the bat; its model starts at the u32 at +4",
            "field": "the bat model's textures, recolored and written as the new character's bat.bin (the "
                     "definition's \"bat\")",
            "text": "The recipe's \"bat\": \"follow\" (the colour rows' rules), \"keep\" (the base's bat) or rules of "
                    "its own. Without one it does what the base's stock colours do (their own bats, or one shared). "
                    "A bat the tool can't read stays as it is and never stops a recolor.",
            "source": "scripts/recolor.py (bat_rules, recolor_bat)"},
}


def main():
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("recipes", nargs="+")
    ap.add_argument("--game", default=os.path.join(ROOT, "extracted/clean"))
    ap.add_argument("--preview", action="store_true")
    ap.add_argument("--dry-run", action="store_true")
    args = ap.parse_args()
    game = Game(args.game)
    for path in args.recipes:
        print("\n".join(make(path, game, args.preview, args.dry_run)))


if __name__ == "__main__":
    main()
