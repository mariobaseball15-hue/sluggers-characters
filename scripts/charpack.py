"""Character packs: one new character in a file a player can share (<slug>.slgchar), and the import that checks it
against the player's own game (docs/character-packs.md).

  python scripts/charpack.py export characters/0x6c_gearmo.json [...] [-o dir]
  python scripts/charpack.py export --all [-o dir]       # every definition; says why the others can't be packed
  python scripts/charpack.py check <pack>                # every check import makes, nothing written
  python scripts/charpack.py import <pack> [--dest dir]  # default: default_dest()

A pack is a zip (at most MAX_PACK bytes):
  pack.json        {"format": 1, "name", "author", "notes", "exported_from": commit, "template",
                    "template_sha1": {file index: sha1 of the template's stock dt_na file}, "files": {path: sha1}}
  character.json   the definition, asset paths pack-relative (ALLOWED keys only; "_" notes kept; no grid keys;
                   captain flag / captain-select data only as "captain_extras", which import keeps aside)
  models/<N>.slgd  each model_blocks entry as a delta.make() delta against the clean game (no game bytes)
  bat.slgd         the bat file as a delta (or bat.json: {"bat_recolors": recipe}, rebuilt from the player's game)
  icons/side.png, icons/front.png   48x51 RGBA
  voice/<slot>.wav 12 clips, slots v1 v3 v4 v5 v6 v7 v8 v10 v11 v12 v13 v14 (mono, 22050 Hz, 16-bit, <= 1.4 s)
  captain/*.png    optional captain-select art (captain_extras)

Imported characters live in default_dest() (per user, outside the patcher, so upgrades keep them):
  <dest>/characters/0xNN_<slug>.json   the definition, paths relative to its character folder
  <dest>/0xNN_<slug>/                   deltas, icons, voice, bat, pack.json
The pack and the import folder hold deltas only: import rebuilds each block in memory to check it, and
materialize(dest, game, work) rebuilds them into the patcher's work folder at patch time.
"""
import argparse, hashlib, io, json, mmap, os, re, shutil, subprocess, sys, wave, zipfile
from contextlib import contextmanager
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
sys.path.insert(0, str(HERE / "patcher"))
import abilities  # noqa: E402
import delta  # noqa: E402
import game_source  # noqa: E402
from sluggers_data import CHAR_NAMES, STAT_FIELDS, char_id  # noqa: E402

ROOT = HERE.parent
FORMAT = 1
SUFFIX = ".slgchar"
MAX_PACK = 64 << 20                 # the zip, and everything in it unpacked
MAX_FILE = 16 << 20                 # one rebuilt file (the largest stock model file is ~1.2 MB)
MODEL_DIR_BASE = 0x12               # a character's model files: dt_na dir template id + 0x12 (charbuild.MODEL_DIR_BASE)
STOCK_IDS = 0x65                    # 0x00-0x64 stock (charbuild.STOCK_IDS); 0x65 is "no character"
PLAYABLE = 0x47                     # stock ids 0x00-0x46 are the named characters a template may be
FIRST_ID = 0x66
# Highest id: charbuild.MAX_ID (0xFF ends the build's id lists). The name plates' page limits how many characters a
# build has (123 with the renamed stock Toads: char_names.add_name_art), not their ids.
MAX_ID = 0xFE
SLOTS = ["v1", "v3", "v4", "v5", "v6", "v7", "v8", "v10", "v11", "v12", "v13", "v14"]   # voice_sets.SLOTS
SLOTS_TEXT = "12 clips, slots " + " ".join(SLOTS)
RATE, MAX_SECONDS = 22050, 1.4      # voice_sets.RATE / MAX_S
ICON_SIZE = (48, 51)                # charbuild.ICON_ART
NAME_BOX = (115, 16)                # char_names.NAME_CELL: a name must fit at the smallest font size
NAME_MIN_SIZE = 9                                  # char_names.name_image shrinks to 9 (its font: char_names.name_font)
NAME_MAX_CHARS = 18                 # without the font (not Windows): a length that fits at 9 px

# character.json keys. BASE: the format's own. REGISTRY: the patcher's generic per-character keys
# (charbuild.STOCK_KEYS, less "stats" and the BESPOKE ones). DATA: plain per-id table data normalize checks
# (charbuild.TABLE_STATS / TABLES rows, a stock colour wheel) that needs no code of its own.
BASE = {"id", "name", "template", "scale", "color", "stats", "chemistry", "hitting_ability", "model_blocks", "bat",
        "icon", "voice", "captain_extras"}
DATA = {"table_stats", "table_rows", "wheel", "own_square"}
# keys whose feature is code written for one character (or its id): never in a pack
BESPOKE = {"piranha_plants": "the Piranha Plants (dino_piranhas)",
           "dino_plants": "the Piranha Plants (dino_piranhas)",
           "lemmy_ride": "Lemmy's ball ride (lemmy_ride)",
           "ride": "Lemmy's ball ride (lemmy_ride)",
           "model_overlay": "a model overlay folder instead of model_blocks",
           "star_throw": "the old star throw key (now the Tantrum Toss fielding ability)"}
# ids the build gives code of their own to (the helpers key it on the id, not a definition key)
BOUND_IDS = {0x78: "King Bob-omb's Bob-omb Drop and Kingly Kaboom labels (pitch_bobomb_drop / star_move_labels, id 0x78)",
             0x84: "the Launch Star's Luma (pitch_launch_star.LUMA, id 0x84)"}
# batting items ("batting_item" names, batter_items.item_id) whose code is keyed to one character's id, not the item:
# none today (the Koopaling items, ice and Star Bits are items of their own, by item id; FIXED_ITEM is stock ids' defaults)
ITEM_BOUND = {}
TOP_STATS = {"star pitch", "fielding ability"}      # registry keys that live under "stats" (patch.set_keys)
GRID = re.compile(r"grid|square", re.I)             # git-d9's grid order keys: a pack carries none
SWATCHES = {"red", "blue", "yellow", "green", "purple", "black", "brown", "lightblue", "pink", "white", "orange"}
# each stat's range: flags and enums from the stock rows (clean main.dol), ratings 0-100, speeds 0-255
STAT_RANGES = {"pitching arm": (0, 1), "batting arm": (0, 1), "character class": (0, 3), "???": (0, 2),
               "weight": (0, 4), "captain": (0, 1), "star pitch": (0, 16), "star swing": (0, 12),
               "fielding ability": (0, max(abilities.NEW)), "baserunning ability": (0, 7),   # ours: 13, 14
               **{k: (0, 100) for k in ("slap size", "charge size", "slap power", "charge power", "bunting", "speed",
                                        "outfield throwing", "fielding", "curve", "curse ball")},
               **{k: (0, 10) for k in ("displayed pitching", "displayed batting", "displayed fielding", "dis speed")},
               "curveball speed": (0, 255), "charge pitch speed": (0, 255)}
SCALE_RANGE = (0.3, 3.0)
CAPTAIN_ART = ("portrait", "lineup", "logo", "emblem")
FILE_RE = re.compile(r"(pack\.json|character\.json|models/\d{1,2}\.slgd|bat\.slgd|bat\.json|icons/(side|front)\.png|"
                     r"voice/(" + "|".join(SLOTS) + r")\.wav|captain/[A-Za-z0-9_-]+\.png)")


class PackError(Exception):
    """A pack that can't be exported or imported; the text is for the player."""


def default_dest(create=True):
    """Where imported characters live: per user, outside the patcher's folder (created on demand)."""
    if os.name == "nt":
        base = Path(os.environ.get("APPDATA") or Path.home() / "AppData/Roaming") / "Sluggers Patcher"
    else:
        base = Path(os.environ.get("XDG_DATA_HOME") or Path.home() / ".local/share") / "sluggers-patcher"
    out = base / "characters"
    if create:
        out.mkdir(parents=True, exist_ok=True)
    return out


def slug(name):
    s = re.sub(r"[^a-z0-9]+", "_", str(name).lower()).strip("_")
    return s or "character"


def sha1(data):
    return hashlib.sha1(data).hexdigest()


# ---- the player's game

@contextmanager
def sources(game=None):
    """The game's delta sources (delta.SOURCES order) as read-only mmaps."""
    game = Path(game or game_source.root())
    files = []
    try:
        for rel in delta.SOURCES:
            p = game / rel
            if not p.exists():
                raise PackError(f"{p} is missing: pick the extracted game folder (the one holding sys and files)")
            files.append(open(p, "rb"))
        maps = [mmap.mmap(f.fileno(), 0, access=mmap.ACCESS_READ) for f in files]
        try:
            yield maps
        finally:
            for m in maps:
                m.close()
    finally:
        for f in files:
            f.close()


_TOC = {}


def _toc(game, srcs):
    """dt_na table of contents of the game's main.dol ([[(offset, length)] per dir])."""
    key = str(Path(game).resolve())
    if key not in _TOC:
        import dtna_toc
        from dol import Dol
        _TOC[key] = dtna_toc.toc(Dol(Path(game) / "sys/main.dol"))
    return _TOC[key]


def stock_file(game, srcs, template, index):
    """The template's stock dt_na file `index` (bytes), or None."""
    files = _toc(game, srcs)[template + MODEL_DIR_BASE]
    if not 0 <= index < len(files) or not files[index][1]:
        return None
    off, length = files[index]
    return bytes(srcs[1][off:off + length])


_INDEX = {}


def index(game):
    """delta.Index over the game's sources, built once per game (~23M blocks) on its own mmaps, which stay open
    (delta.make reads the sources through the index)."""
    key = str(Path(game).resolve())
    if key not in _INDEX:
        _INDEX.clear()
        maps = []
        for rel in delta.SOURCES:
            with open(Path(game) / rel, "rb") as f:
                maps.append(mmap.mmap(f.fileno(), 0, access=mmap.ACCESS_READ))
        _INDEX[key] = delta.Index(maps)
    return _INDEX[key]


def rebuild(data, srcs, what):
    """A delta rebuilt from the player's game, or PackError."""
    try:
        n, _ = delta.info(data)
    except Exception:
        raise PackError(f"{what} is damaged (not a delta file)")
    if n > MAX_FILE:
        raise PackError(f"{what} would be {n} bytes, more than any character file")
    try:
        return delta.apply(data, srcs)
    except ValueError:
        import modded_game                      # a game with model / texture mods: which of its changes it needed
        why = modded_game.why_not_rebuilt(data)
        raise PackError(f"{what} doesn't rebuild from your game: " + (why or "the pack was made for a different copy "
                                                                            "of the game, or it is damaged"))
    except Exception:
        raise PackError(f"{what} is damaged")


VALIDATOR_MISSING = ("the full structural model check (Sluggies' BlockValidator) isn't in this copy; the model passed "
                     "our own crash checks")


def gate(block, donor, what, require_validator=False):
    """The model crash gate (check_models.check_block) on a high / low block against the template's stock one. The
    patcher's download has no refs/, so without Sluggies' BlockValidator only our own checks run (import adds
    VALIDATOR_MISSING to its warnings); export (require_validator) needs the full gate."""
    import check_models
    full = check_models.validator_available()
    if require_validator and not full:
        raise PackError("exporting needs the full model check (refs/Sluggies-dat-tools)")
    try:
        problems = check_models.check_block(block, len(donor), donor, validator=full)
    except Exception as e:                                  # a block too broken to parse
        problems = [f"can't be read ({type(e).__name__})"]
    if problems:
        raise PackError(f"{what} fails the model crash check (it would crash or break the game): "
                        + "; ".join(problems[:3]))


def gate_lod(block, game, srcs, template, index, require_validator=False):
    """gate() for model file 0 / 1 against the template's stock block it was built on: the same file, or the other LOD
    when the block is that one's size (the Lumas ship their high block as file 1 too, like Extra Innings' Luma)."""
    donors = [stock_file(game, srcs, template, i) for i in (0, 1)]
    donor = donors[index]
    if donor is not None and len(block) != len(donor) and donors[1 - index] is not None and             len(block) == len(donors[1 - index]):
        donor = donors[1 - index]
    gate(block, donor, f"model block {index}", require_validator)


# ---- checks shared by export and import

def _template(ref):
    try:
        tid = char_id(ref)
    except (KeyError, ValueError, TypeError):
        tid = None
    if tid is None or not 0 <= tid < PLAYABLE:
        raise PackError(f"the template {ref!r} isn't a stock character")
    return tid


def _known_names():
    """Every character name chemistry may use (lower case): stock, this repo's definitions and recolors."""
    out = {n.strip().lower() for n in CHAR_NAMES[:PLAYABLE]}
    for p in [*(ROOT / "characters").glob("*.json"), *(ROOT / "recolors").glob("*.json")]:
        try:
            out.add(str(json.loads(p.read_text(encoding="utf8"))["name"]).strip().lower())
        except (OSError, ValueError, KeyError, TypeError):
            continue
    return out


def _name_width(name):
    try:
        from PIL import Image, ImageDraw
        import char_names
        font = char_names.name_font(NAME_MIN_SIZE)
    except OSError:
        return None
    return ImageDraw.Draw(Image.new("RGBA", NAME_BOX)).textbbox((0, 0), name, font=font)[2]


def name_fits(name):
    """The name fits the select screens' name box (char_names.name_image, shrunk to its smallest size)."""
    w = _name_width(name)
    return len(name) <= NAME_MAX_CHARS if w is None else w <= NAME_BOX[0] - 2


def check_name(name):
    if not isinstance(name, str) or not name.strip() or name != name.strip():
        raise PackError(f"the name {name!r} isn't usable")
    if any(not (0x20 <= ord(ch) < 0x7F) for ch in name):
        raise PackError(f"the name {name!r} has letters the game's font doesn't have (plain English letters only)")
    if not name_fits(name):
        raise PackError(f"the name {name!r} is too long for the name box")


def check_keys(d, exporting=False):
    """The definition's keys: ALLOWED, else PackError naming the key."""
    import charbuild
    registry = set(charbuild.STOCK_KEYS) - {"stats"} - set(BESPOKE)
    allowed = BASE | DATA | registry
    for k in d:
        if k.startswith("_") or GRID.search(k):
            continue
        if k not in allowed:
            if exporting:
                why = BESPOKE.get(k, "a key the pack format doesn't carry")
                raise PackError(f"it uses {k!r}: {why}")
            raise PackError(f"This pack uses {k!r}, which this patcher can't build for an imported character.")


def check_values(d, extra_names=()):
    """Everything in the definition that can be checked without files: PackError on the first problem."""
    import charbuild
    check_name(d.get("name"))
    _template(d.get("template"))
    try:
        if "scale" in d and not SCALE_RANGE[0] <= float(d["scale"]) <= SCALE_RANGE[1]:
            raise PackError(f"scale {d['scale']} is outside {SCALE_RANGE[0]}-{SCALE_RANGE[1]}")
    except (TypeError, ValueError):
        raise PackError(f"scale {d['scale']!r} isn't a number")
    if d.get("color") is not None and d["color"] not in SWATCHES:
        raise PackError(f"colour {d['color']!r} isn't one of {', '.join(sorted(SWATCHES))}")
    stats = d.get("stats", {})
    if not isinstance(stats, dict):
        raise PackError("stats isn't a list of stats")
    for k, v in stats.items():
        if k not in STAT_FIELDS:
            raise PackError(f"unknown stat {k!r}")
        lo, hi = STAT_RANGES[k]
        if not isinstance(v, int) or isinstance(v, bool) or not lo <= v <= hi:
            raise PackError(f"stat {k!r} is {v!r}; it goes from {lo} to {hi}")
    import abilities
    if not abilities.valid(int(stats.get("fielding ability", 0))):
        raise PackError(f"fielding ability {stats['fielding ability']} doesn't exist")
    chem = d.get("chemistry", {})
    if not isinstance(chem, dict):
        raise PackError("chemistry isn't a list of characters")
    known = _known_names() | {n.strip().lower() for n in extra_names}
    for k, v in chem.items():
        if not isinstance(k, str) or k.strip().lower() not in known:
            raise PackError(f"chemistry names {k!r}, which isn't a character this patcher knows")
        if v not in (0, 1, 2):
            raise PackError(f"chemistry with {k} is {v!r}; it is 0 (bad), 1 (neutral) or 2 (good)")
    try:
        charbuild._check_table_stats(d.get("table_stats", {}), d.get("name"))
        charbuild._check_table_rows(d.get("table_rows", {}), d.get("name"))
        if "wheel" in d and not 0 <= char_id(d["wheel"]) < STOCK_IDS:
            raise PackError(f"wheel {d['wheel']!r} isn't a stock character")
        import item_abilities, star_move_labels
        item_abilities.of(d)
        star_move_labels.hitting_of(d)
        star_move_labels.running_of(d)
        item = d.get("batting_item")
        if item not in (None, False, "", "none"):
            import batter_items
            if isinstance(item, bool) or not isinstance(item, (str, int)):
                raise PackError(f"batting item {item!r} isn't an item")
            try:
                iid = batter_items.item_id(item)
            except AssertionError:
                raise PackError(f"This pack's batting item {item!r} isn't an item this patcher knows.")
            if iid in ITEM_BOUND:
                raise PackError(f"batting item {item!r}: {ITEM_BOUND[iid]}")
        for k in ("always_item", "chance_cheer", "batter_star", "minimap_decoys"):
            if k in d and not isinstance(d[k], bool):
                raise PackError(f"{k} is {d[k]!r}; it is true or false")
        if d.get("star swing") is not None:
            import custom_swings
            custom_swings.stats_of(int(d["star swing"]))
    except PackError:
        raise
    except (AssertionError, KeyError, ValueError, TypeError) as e:
        raise PackError(f"{str(e) or type(e).__name__}")
    bat = d.get("bat")
    if bat is not None:
        if not isinstance(bat, dict) or len({"dir", "file", "recolor"} & set(bat)) != 1:
            raise PackError("bat needs one of dir, file or recolor")
        if "dir" in bat and not (isinstance(bat["dir"], int) and MODEL_DIR_BASE <= bat["dir"] < MODEL_DIR_BASE + PLAYABLE):
            raise PackError(f"bat dir {bat['dir']!r} isn't a stock character's")
    icon = d.get("icon")
    if icon is not None and (not isinstance(icon, dict) or set(icon) != {"side", "front"}):
        raise PackError("icon needs a side and a front picture")


def check_icon(data, what):
    from PIL import Image
    try:
        im = Image.open(io.BytesIO(data))
        im.load()
    except Exception:
        raise PackError(f"{what} isn't a picture")
    if im.format != "PNG" or im.size != ICON_SIZE or im.mode != "RGBA":
        raise PackError(f"{what} must be a {ICON_SIZE[0]}x{ICON_SIZE[1]} RGBA PNG (it is {im.size[0]}x{im.size[1]} "
                        f"{im.mode} {im.format})")


def check_clip(data, what):
    try:
        with wave.open(io.BytesIO(data)) as w:
            ch, width, rate, frames = w.getnchannels(), w.getsampwidth(), w.getframerate(), w.getnframes()
    except Exception:
        raise PackError(f"{what} isn't a WAV file")
    if ch != 1 or width != 2 or rate != RATE:
        raise PackError(f"{what} must be mono, {RATE} Hz, 16-bit (it is {ch} channel, {rate} Hz, {8 * width}-bit)")
    if frames > MAX_SECONDS * RATE + 64:                    # (a few samples of rounding)
        raise PackError(f"{what} is {frames / RATE:.2f} s; clips are at most {MAX_SECONDS} s")


def check_voice(names, what="the voice", partial=False):
    """names: the slot names present (e.g. from voice/<slot>.wav). partial: any of the 12 (git-92 for Nick: a shared
    file carries only the clips the player chose; the others play the base's sounds, never stock audio in a file)."""
    got = set(names)
    if partial and got and got <= set(SLOTS) and len(names) == len(got):
        return
    if got != set(SLOTS) or len(names) != len(SLOTS):
        missing, extra = [s for s in SLOTS if s not in got], sorted(got - set(SLOTS))
        raise PackError(f"{what} needs {SLOTS_TEXT}; it has {len(names)}"
                        + (f" (missing {' '.join(missing)})" if missing else "")
                        + (f" (not a slot: {' '.join(extra)})" if extra else ""))


# ---- export

def _repo_path(p):
    """A definition's asset path -> the file (charbuild.asset: game-derived files from the work folder)."""
    import charbuild
    return charbuild.asset(p)


def _is_derived(p):
    import charbuild
    parts = Path(p).parts
    return not Path(p).is_absolute() and parts[:2] == ("models", "work") and charbuild.derived("/".join(parts[2:]))


def _git_commit():
    try:
        r = subprocess.run(["git", "-C", str(ROOT), "rev-parse", "--short", "HEAD"], capture_output=True, text=True,
                           timeout=20)
        return r.stdout.strip() or "unknown"
    except (OSError, subprocess.SubprocessError):
        return "unknown"


def _bound_defaults(cid, d):
    """Keys this character only has through a helper's id defaults (custom_swings, batter_star, ...): made explicit,
    since an imported character gets another id."""
    out = {}
    try:
        import custom_swings
        for sid, ids in custom_swings.DEFAULT_CHARS.items():
            if cid in ids and d.get("star swing") is None:
                out["star swing"] = sid
        import batter_star
        if cid in batter_star.STAR_CHARS and d.get("batter_star") is None:
            out["batter_star"] = True
        import pauline_chance
        if cid == pauline_chance.PAULINE and d.get("chance_cheer") is None:
            out["chance_cheer"] = True
        import pompom_decoys
        if cid in pompom_decoys.DEFAULT_CHARS and d.get("minimap_decoys") is None:
            out["minimap_decoys"] = True
    except ImportError:
        pass
    return out


def plan_export(definition_path):
    """(definition, id) if the definition can be packed, else PackError with the reason."""
    p = Path(definition_path)
    d = json.loads(p.read_text(encoding="utf8"))
    if str(d.get("_why", "")).startswith("Recolor tool") or (ROOT / "recolors" / f"{slug(d.get('name', '')).replace('_', '-')}.json").exists():
        raise PackError("recolor: shared as a recipe, not a pack (the recolor tool makes its art from the game: recolors/*.json)")
    cid = char_id(d["id"])
    if cid in BOUND_IDS:
        raise PackError(f"the build gives it bespoke code by its id: {BOUND_IDS[cid]}")
    if d.get("model_overlay") and not d.get("model_blocks"):
        raise PackError("it uses 'model_overlay': " + BESPOKE["model_overlay"])
    check_keys({k: v for k, v in d.items() if k != "model_overlay"}, exporting=True)
    if not d.get("model_blocks"):
        raise PackError("it has no model_blocks (a pack carries the character's own model)")
    for view, path in (d.get("icon") or {}).items():
        if _is_derived(path):
            raise PackError(f"its {view} icon is made from the game's own art")
    return d, cid


def export_pack(definition_path, out_dir, game=None, author="", notes=""):
    """Pack a characters/*.json definition into <out_dir>/<slug>.slgchar (made against the clean game `game`,
    default game_source.root()). Checks the pack like an import would. Returns the pack's path; PackError if the
    character can't be packed (the reason)."""
    game = Path(game or game_source.root())
    d, cid = plan_export(definition_path)
    name = d["name"]
    tid = _template(d["template"])
    files, pd = {}, {}
    for k, v in d.items():
        if k == "model_overlay" or GRID.search(k) and not k.startswith("_"):
            continue
        pd[k] = v
    pd.update(_bound_defaults(cid, d))
    stats = dict(pd.get("stats", {}))
    extras = dict(pd.pop("captain_extras", {}) or {})
    if stats.get("captain"):
        extras["captain"] = stats.pop("captain")
    if "stats" in pd:
        pd["stats"] = stats
    for k in TOP_STATS & set(pd):                           # patch.set_keys: they live under stats
        pd.setdefault("stats", {})[k] = pd.pop(k)
    chem = {}
    for k, v in pd.get("chemistry", {}).items():            # chemistry by name
        ck = char_id(k) if not isinstance(k, str) or re.fullmatch(r"0x[0-9a-fA-F]+|\d+", k.strip()) else None
        chem[CHAR_NAMES[ck].strip() if ck is not None and ck < STOCK_IDS else k] = v
    if "chemistry" in pd:
        pd["chemistry"] = chem
    template_sha1 = {}
    with sources(game) as srcs:
        idx = index(game)
        blocks = {}
        for i, path in d["model_blocks"].items():
            data = _repo_path(path).read_bytes()
            stock = stock_file(game, srcs, tid, int(i))
            if stock is None:
                raise PackError(f"model block {i}: the template has no file {i}")
            if int(i) in (0, 1):
                gate_lod(data, game, srcs, tid, int(i), require_validator=True)
            template_sha1[str(int(i))] = sha1(stock)
            blocks[f"models/{int(i)}.slgd"] = delta.make(data, idx)[0]
        for i in (0, 1):                                    # the crash gate's donors (gate_lod)
            stock = stock_file(game, srcs, tid, i)
            if stock is not None:
                template_sha1.setdefault(str(i), sha1(stock))
        files.update(blocks)
        pd["model_blocks"] = {str(int(i)): f"models/{int(i)}.slgd" for i in d["model_blocks"]}
        bat = pd.get("bat")
        if bat and "file" in bat:
            files["bat.slgd"] = delta.make(_repo_path(bat["file"]).read_bytes(), idx)[0]
            pd["bat"] = dict(bat, file="bat.slgd")
    if d.get("icon"):
        for view in ("side", "front"):
            data = _repo_path(d["icon"][view]).read_bytes()
            check_icon(data, f"the {view} icon")
            files[f"icons/{view}.png"] = data
        pd["icon"] = {"side": "icons/side.png", "front": "icons/front.png"}
    if d.get("voice"):
        folder = ROOT / "models/work/sounds/sets" / d["voice"]
        have = sorted(p.stem for p in folder.glob("v*.wav")) if folder.is_dir() else []
        check_voice([s for s in have if s in SLOTS], f"the voice set {d['voice']!r}")
        for s in SLOTS:
            data = (folder / f"{s}.wav").read_bytes()
            check_clip(data, f"voice clip {s}")
            files[f"voice/{s}.wav"] = data
        pd["voice"] = "voice"
    try:
        import captains
        cap = next((c for c in captains.ALL_CAPTAINS if c["id"] == cid), None)
    except ImportError:
        cap = None
    if cap:
        # a captains.py entry (git-a7, 05143be: ENTRY_KEYS) minus "character" (filled in at import) and "replaces"
        # (the profile decides): {"prefs_from"?, "art": "captain"}; the art folder holds portrait.png,
        # lineup.png, logo.png and emblem.png, the names captains._art_files reads from an entry's own folder
        entry = {"prefs_from": cap["prefs_from"]} if "prefs_from" in cap else {}
        for key in CAPTAIN_ART:
            names = ([f"{cap['art']}_{key}.png"] if key in ("portrait", "lineup") else []) + [f"{key}.png"]
            src = next((ROOT / "captains" / cap["art"] / n for n in names if (ROOT / "captains" / cap["art"] / n).exists()), None)
            if src:
                files[f"captain/{key}.png"] = src.read_bytes()
        if any(n.startswith("captain/") for n in files):
            entry["art"] = "captain"
        extras["entry"] = entry
    if extras:
        pd["captain_extras"] = extras
    check_values(pd)
    files["character.json"] = json.dumps(pd, indent=1, ensure_ascii=False).encode("utf8")
    meta = {"format": FORMAT, "name": name, "author": author, "notes": notes, "exported_from": _git_commit(),
            "template": CHAR_NAMES[tid].strip(), "template_sha1": template_sha1,
            "files": {k: sha1(v) for k, v in sorted(files.items())}}
    out = Path(out_dir) / f"{slug(name)}{SUFFIX}"
    out.parent.mkdir(parents=True, exist_ok=True)
    write_zip(out, {"pack.json": json.dumps(meta, indent=1, ensure_ascii=False).encode("utf8"), **files})
    with sources(game) as srcs:
        _validate(out, game, srcs)                          # what an import would say
    return out


def write_zip(path, files):
    tmp = Path(str(path) + ".part")
    with zipfile.ZipFile(tmp, "w", zipfile.ZIP_DEFLATED) as z:
        for name, data in files.items():
            z.writestr(zipfile.ZipInfo(name, (2026, 1, 1, 0, 0, 0)), data,
                       zipfile.ZIP_STORED if name.endswith((".slgd", ".png")) else zipfile.ZIP_DEFLATED)
    if tmp.stat().st_size > MAX_PACK:
        tmp.unlink()
        raise PackError(f"the pack would be over {MAX_PACK >> 20} MB")
    os.replace(tmp, path)


# ---- reading a pack

def _safe_name(n):
    return not (n.startswith(("/", "\\")) or "\\" in n or ":" in n or ".." in n.split("/") or "" in n.split("/")
                or "." in n.split("/"))


def read_pack(pack_path):
    """{name: bytes} of a pack whose zip is safe (size, paths, sha1 of each listed file, format), else PackError."""
    p = Path(pack_path)
    if not p.is_file():
        raise PackError(f"{p} isn't a file")
    if p.stat().st_size > MAX_PACK:
        raise PackError(f"the pack is over {MAX_PACK >> 20} MB")
    try:
        z = zipfile.ZipFile(p)
    except (zipfile.BadZipFile, OSError):
        raise PackError("this isn't a character pack (not a zip file)")
    with z:
        infos = z.infolist()
        seen = set()
        for info in infos:
            n = info.filename
            if not _safe_name(n):
                raise PackError(f"the pack has a file with an unsafe path ({n!r}); it won't be opened")
            if n.lower() in seen:
                raise PackError(f"the pack has two files named {n!r}")
            seen.add(n.lower())
            if not FILE_RE.fullmatch(n):
                raise PackError(f"the pack has a file that doesn't belong in a character pack ({n!r})")
        if sum(i.file_size for i in infos) > MAX_PACK:
            raise PackError(f"the pack unpacks to over {MAX_PACK >> 20} MB")
        files = {}
        for info in infos:
            try:
                files[info.filename] = z.read(info)
            except Exception:
                raise PackError(f"{info.filename} in the pack is damaged")
    try:
        meta = json.loads(files["pack.json"])
    except KeyError:
        raise PackError("this isn't a character pack (no pack.json)")
    except ValueError:
        raise PackError("pack.json is damaged")
    if not isinstance(meta, dict) or meta.get("format") != FORMAT:
        raise PackError(f"this pack is format {meta.get('format') if isinstance(meta, dict) else '?'}; this patcher "
                        f"reads format {FORMAT} (a newer patcher may read it)")
    listed = meta.get("files")
    if not isinstance(listed, dict):
        raise PackError("pack.json doesn't list the pack's files")
    for n, want in listed.items():
        if n not in files:
            raise PackError(f"the pack is missing {n}")
        if sha1(files[n]) != want:
            raise PackError(f"{n} in the pack is damaged (its checksum doesn't match)")
    extra = sorted(set(files) - set(listed) - {"pack.json"})
    if extra:
        raise PackError(f"the pack has files pack.json doesn't list: {', '.join(extra)}")
    if "character.json" not in files:
        raise PackError("the pack has no character.json")
    return meta, files


def _validate(pack_path, game, srcs, extra_names=()):
    """Every check of an import (nothing written). Returns (meta, files, definition, warnings)."""
    meta, files = read_pack(pack_path)
    try:
        d = json.loads(files["character.json"])
    except ValueError:
        raise PackError("character.json is damaged")
    if not isinstance(d, dict):
        raise PackError("character.json is damaged")
    warnings = []
    grid = [k for k in d if GRID.search(k) and not k.startswith("_")]
    if grid:
        warnings.append(f"left out the grid position ({', '.join(grid)}): the patcher places imported characters")
        d = {k: v for k, v in d.items() if k not in grid}
    check_keys(d)
    check_values(d, extra_names)
    tid = _template(d["template"])
    # 2. the template's stock files are the ones the deltas were made against
    want = meta.get("template_sha1")
    if not isinstance(want, dict) or not want:
        raise PackError("pack.json doesn't say which game files the character was made against")
    if _template(meta.get("template", d["template"])) != tid:
        raise PackError("pack.json and character.json name different templates")
    for i, h in want.items():
        stock = stock_file(game, srcs, tid, int(i))
        if stock is None or sha1(stock) != h:
            raise PackError(f"This pack was made for a different copy of the game: {CHAR_NAMES[tid].strip()}'s "
                            f"file {i} doesn't match.")
    # 4. every delta rebuilds (in memory, then dropped), the high / low blocks pass the crash gate
    mb = d.get("model_blocks")
    if not isinstance(mb, dict) or not mb:
        raise PackError("the pack has no model")
    for i, path in mb.items():
        if not re.fullmatch(r"\d{1,2}", str(i)) or path != f"models/{int(i)}.slgd" or path not in files:
            raise PackError(f"model block {i} is missing from the pack")
        if str(int(i)) not in want:
            raise PackError(f"model block {i}: pack.json doesn't record the game file it was made against")
        block = rebuild(files[path], srcs, f"model block {i}")
        stock = stock_file(game, srcs, tid, int(i))
        if int(i) in (0, 1):
            gate_lod(block, game, srcs, tid, int(i))
            import check_models
            if not check_models.validator_available() and VALIDATOR_MISSING not in warnings:
                warnings.append(VALIDATOR_MISSING)
        elif len(block) != len(stock) and len(block) > MAX_FILE:
            raise PackError(f"model block {i} is too big")
        del block
    stray = sorted(n for n in files if n.startswith("models/") and n not in mb.values())
    if stray:
        raise PackError(f"the pack has model files character.json doesn't use: {', '.join(stray)}")
    bat = d.get("bat")
    if bat and "file" in bat:
        if bat["file"] != "bat.slgd" or "bat.slgd" not in files:
            raise PackError("the bat is missing from the pack")
        rebuild(files["bat.slgd"], srcs, "the bat")
    elif bat and "recolor" in bat:
        if bat["recolor"] != "bat.json" or "bat.json" not in files:
            raise PackError("the bat's recipe is missing from the pack")
        _bat_rule(files["bat.json"])
    # 5. icons and voice
    if d.get("icon"):
        for view in ("side", "front"):
            if d["icon"][view] != f"icons/{view}.png" or f"icons/{view}.png" not in files:
                raise PackError(f"the {view} icon is missing from the pack")
            check_icon(files[f"icons/{view}.png"], f"the {view} icon")
    clips = [n[6:-4] for n in files if n.startswith("voice/")]
    if d.get("voice") is not None or clips:
        if d.get("voice") != "voice":
            raise PackError("the voice is missing from the pack")
        check_voice(clips, partial=True)
        for s in clips:
            check_clip(files[f"voice/{s}.wav"], f"voice clip {s}")
    extras = d.get("captain_extras")
    if extras is not None and not isinstance(extras, dict):
        raise PackError("captain_extras is damaged")
    entry = (extras or {}).get("entry", {})
    if not isinstance(entry, dict) or set(entry) - {"prefs_from", "art", "name"} or             entry.get("art") not in (None, "captain"):
        raise PackError("the pack's captain data isn't a captain entry this patcher knows")
    for n in files:
        if n.startswith("captain/"):
            check_picture(files[n], n)
    return meta, files, d, warnings


def check_picture(data, what):
    from PIL import Image
    try:
        Image.open(io.BytesIO(data)).load()
    except Exception:
        raise PackError(f"{what} isn't a picture")


def _bat_rule(data):
    """bat.json: {"bat_recolors": recipe name} (a bat_recolors.RECIPES recipe, rebuilt from the player's game)."""
    try:
        rule = json.loads(data)
        name = rule["bat_recolors"]
    except (ValueError, KeyError, TypeError):
        raise PackError("bat.json is damaged")
    import bat_recolors
    if name not in bat_recolors.RECIPES:
        raise PackError(f"This pack's bat uses the recolor recipe {name!r}, which this patcher doesn't have.")
    return name


def bat_from_rule(name, game, srcs):
    """bat_recolors.build(name) made from the player's game, in memory (bat_recolors.build reads extracted/clean and
    writes models/work/bats)."""
    import bat_recolors
    from build_model import encode_texture
    from mss_model import Model
    from recolor_block import decode
    src_dir, recipe = bat_recolors.RECIPES[name]
    off, length = _toc(game, srcs)[src_dir][2]
    entry = bytearray(srcs[1][off:off + length])
    member = int.from_bytes(entry[4:8], "big")
    block = bytearray(entry[member:])
    if name in bat_recolors.SCALES:
        bat_recolors.scale_positions(block, bat_recolors.SCALES[name])
    textures = Model(bytes(block)).textures
    for i, fn in (recipe if isinstance(recipe, dict) else {0: recipe}).items():
        tex = textures[i]
        img = decode(bytes(block), tex)
        fn(img)
        block[tex.image:tex.image + tex.payload_size()] = encode_texture(img, tex.format, tex.payload_size())
    entry[member:] = block
    return bytes(entry)


def check(pack_path, game=None, dest=None):
    """Dry run of an import: every check, nothing written. {"ok", "error", "name", "author", "notes", "template",
    "id", "exported_from", "voice", "icons", "blocks", "bat", "captain_extras", "warnings"}."""
    game = Path(game or game_source.root())
    report = {"ok": False, "error": None, "pack": str(pack_path), "warnings": []}
    try:
        with sources(game) as srcs:
            meta, files, d, warnings = _validate(pack_path, game, srcs, [c["name"] for c in list_imported_quiet(dest)])
    except PackError as e:
        report["error"] = str(e)
        return report
    report.update(ok=True, name=d["name"], author=meta.get("author", ""), notes=meta.get("notes", ""),
                  template=CHAR_NAMES[_template(d["template"])].strip(), id=d.get("id"),
                  exported_from=meta.get("exported_from"), voice=bool(d.get("voice")), icons=bool(d.get("icon")),
                  blocks=sorted(int(i) for i in d["model_blocks"]),
                  bat=("rule" if "recolor" in d["bat"] else "file" if "file" in d["bat"] else "stock")
                  if d.get("bat") else None,
                  captain_extras=bool(d.get("captain_extras")), warnings=warnings)
    return report


# ---- import

def _definitions(dest):
    folder = Path(dest) / "characters"
    out = []
    for p in sorted(folder.glob("0x*.json")) if folder.is_dir() else []:
        try:
            out.append((p, json.loads(p.read_text(encoding="utf8"))))
        except (OSError, ValueError):
            continue
    return out


def list_imported(dest=None):
    """[{"id", "name", "template", "author", "definition", "folder"[, "captain_entry"]}] of the imported characters,
    by id. "captain_entry" (packs with captain data): a captains.py list entry ({"character", "prefs_from"?,
    "art": the character's captain folder}) the profile's "captains" option may use; importing never adds it."""
    dest = Path(dest) if dest else default_dest()
    out = []
    for p, d in _definitions(dest):
        meta = d.get("_pack", {})
        item = {"id": char_id(d["id"]), "name": d["name"], "template": d.get("template"),
                "author": meta.get("author", ""), "definition": p, "folder": dest / p.stem}
        extras_p = dest / p.stem / "captain_extras.json"
        if extras_p.exists():            # a captains.py list entry the profile MAY use; import never makes one
            entry = dict(json.loads(extras_p.read_text(encoding="utf8")).get("entry") or {}, character=d["name"])
            if entry.get("art"):
                entry["art"] = str(dest / p.stem / entry["art"])
            item["captain_entry"] = entry
        out.append(item)
    return sorted(out, key=lambda c: c["id"])


def list_imported_quiet(dest=None):
    """list_imported without creating the default folder."""
    try:
        return list_imported(dest or default_dest(create=False))
    except OSError:
        return []


def reserved_ids():
    """Ids a new import never takes: this repo's definitions and recolors (a helper may key code or defaults on
    them, e.g. the captains) and BOUND_IDS."""
    out = set(BOUND_IDS)
    for p in [*(ROOT / "characters").glob("*.json"), *(ROOT / "recolors").glob("*.json")]:
        try:
            out.add(char_id(json.loads(p.read_text(encoding="utf8"))["id"]))
        except (OSError, ValueError, KeyError, TypeError):
            continue
    return out


def free_id(hint, taken):
    """The hint if free, else the next free id from FIRST_ID up (to MAX_ID)."""
    if hint is not None and FIRST_ID <= hint <= MAX_ID and hint not in taken:
        return hint
    for cid in range(FIRST_ID, MAX_ID + 1):
        if cid not in taken:
            return cid
    raise PackError(f"there's no free character id left (ids 0x{FIRST_ID:X}-0x{MAX_ID:X} are all used): remove an "
                    f"imported character first")


def free_name(name, taken):
    """name, or name + " (2)", " (3)"... (the base cut so the whole name fits the name box) when it's taken."""
    taken = {n.strip().lower() for n in taken}
    if name.lower() not in taken:
        return name
    for k in range(2, 100):
        suffix = f" ({k})"
        base = name
        while base and not name_fits(base.rstrip() + suffix):
            base = base[:-1]
        cand = base.rstrip() + suffix
        if base.strip() and cand.lower() not in taken:
            return cand
    raise PackError(f"the name {name!r} is taken")


def import_pack(pack_path, game=None, dest=None, taken_ids=(), taken_names=(), name=None, cid=None):
    """Check the pack against the player's game and unpack it into dest (default_dest()). taken_ids / taken_names: the
    ids and names the patch already has (its own characters); imported ones are added. name / cid: use exactly these
    when they're free (the import dialog's Replace keeps the replaced one's, git-f3: recolors find a base by name),
    else the usual choice with a warning. Returns {"definition": path, "id", "name", "warnings"}; PackError (plain
    English) if the pack can't be imported."""
    want_name, want_id = name, cid
    game = Path(game or game_source.root())
    dest = Path(dest) if dest else default_dest()
    have = list_imported(dest)
    with sources(game) as srcs:
        meta, files, d, warnings = _validate(pack_path, game, srcs, [c["name"] for c in have] + list(taken_names))
    hint = None
    try:
        hint = char_id(d["id"]) if "id" in d else None
    except (KeyError, ValueError, TypeError):
        pass
    taken = set(taken_ids) | {c["id"] for c in have} | reserved_ids()
    if want_id is not None:
        wid = char_id(want_id)
        if FIRST_ID <= wid <= MAX_ID and wid not in taken:
            hint = wid
        else:
            warnings.append(f"id 0x{wid:02X} is taken: a new one is picked")
            hint = None                                     # (one warning, not also the pack's own id's)
    cid = free_id(hint, taken)
    if hint is not None and cid != hint:
        warnings.append(f"id 0x{hint:02X} is taken: it is 0x{cid:02X}")
    names_taken = [*taken_names, *(c["name"] for c in have)]
    if want_name and str(want_name).strip().lower() not in {n.strip().lower() for n in names_taken}:
        d["name"] = str(want_name).strip()              # (it fit the name box before: the replaced one had it)
    elif want_name:
        warnings.append(f"the name {want_name} is taken: a new one is picked")
    name = free_name(d["name"], names_taken)
    if name != d["name"]:
        warnings.append(f"there's already a {d['name']}: this one is {name}")
    # never a captain: the flag is cleared, captain data kept aside
    extras = dict(d.pop("captain_extras", None) or {})
    stats = dict(d.get("stats", {}))
    if stats.get("captain"):
        extras["captain"] = stats["captain"]
    stats["captain"] = 0
    d["stats"] = stats
    if extras:
        warnings.append("the pack's captain data is kept aside: imported characters aren't captains")
    stem = f"0x{cid:02x}_{slug(name)}"
    folder, defn = dest / stem, dest / "characters" / f"{stem}.json"
    tmp = dest / f".{stem}.part"
    shutil.rmtree(tmp, ignore_errors=True)
    for n, data in files.items():
        if n == "character.json":
            continue
        (tmp / n).parent.mkdir(parents=True, exist_ok=True)
        (tmp / n).write_bytes(data)
    if extras:
        (tmp / "captain_extras.json").write_text(json.dumps(extras, indent=1), encoding="utf8")
    d.update(id=f"0x{cid:02x}", name=name, own_square=True)       # its own square (charbuild.own_squares)
    d["_pack"] = {"name": meta.get("name"), "author": meta.get("author", ""), "notes": meta.get("notes", ""),
                  "exported_from": meta.get("exported_from"), "sha1": sha1(Path(pack_path).read_bytes()),
                  "folder": stem}
    shutil.rmtree(folder, ignore_errors=True)
    os.replace(tmp, folder)
    defn.parent.mkdir(parents=True, exist_ok=True)
    defn.write_text(json.dumps(d, indent=1, ensure_ascii=False), encoding="utf8")
    return {"definition": defn, "id": cid, "name": name, "warnings": warnings}


def remove(cid, dest=None):
    """Delete an imported character (its definition and folder). Returns True if there was one."""
    dest = Path(dest) if dest else default_dest()
    cid = char_id(cid)
    for c in list_imported(dest):
        if c["id"] == cid:
            c["definition"].unlink()
            shutil.rmtree(c["folder"], ignore_errors=True)
            return True
    return False


def voice_name(cid):
    """The voice set name materialize gives an imported character (build_voices tags sounds zz<name>_vN)."""
    return f"imp{cid:02x}"


def materialize(dest, game, work, taken_ids=(), taken_names=()):
    """The imported characters as charbuild definitions, at patch time: each model block and bat rebuilt from the
    player's game into <work>/imported/<0xNN_slug>/, asset paths absolute (charbuild.asset takes them). A voiced one
    gets "voice": voice_name(id) and "voice_dir": its clips (<folder>/voice, 12 clips, slots v1 v3 v4 v5 v6 v7 v8
    v10 v11 v12 v13 v14): build_voices needs to add that set (see docs/character-packs.md). taken_ids / taken_names:
    the patch's own characters; an imported one that clashes gets another id / name here (the "_note" says so)."""
    dest = Path(dest) if dest else default_dest()
    game, work = Path(game), Path(work)
    out = []
    ids = set(taken_ids)
    names = {n.lower() for n in taken_names}
    with sources(game) as srcs:
        for p, d in _definitions(dest):
            folder = dest / p.stem
            d = json.loads(json.dumps(d))
            cid = char_id(d["id"])
            notes = []
            if cid in ids:
                new = free_id(None, ids | reserved_ids())
                notes.append(f"id 0x{cid:02X} is taken in this patch: built as 0x{new:02X}")
                cid = new
            if d["name"].lower() in names:
                new = free_name(d["name"], names)
                notes.append(f"there's already a {d['name']} in this patch: built as {new}")
                d["name"] = new
            ids.add(cid)
            names.add(d["name"].lower())
            d["id"] = f"0x{cid:02x}"
            d["stats"] = dict(d.get("stats", {}), captain=0)
            d["own_square"] = True                  # an imported character: a square of its own, never its
            d.pop("captain_extras", None)           # template's wheel (Nick: an imported Luma joined Boo's)
            out_dir = work / "imported" / p.stem
            out_dir.mkdir(parents=True, exist_ok=True)
            what = f"{d['name']} (imported)"
            blocks = {}
            for i, rel in d["model_blocks"].items():
                data = rebuild((folder / rel).read_bytes(), srcs, f"{what}: model block {i}")
                target = out_dir / f"{int(i)}.bin"
                target.write_bytes(data)
                blocks[str(int(i))] = str(target)
            d["model_blocks"] = blocks
            bat = d.get("bat")
            if bat and "file" in bat:
                target = out_dir / "bat.bin"
                target.write_bytes(rebuild((folder / bat["file"]).read_bytes(), srcs, f"{what}: the bat"))
                d["bat"] = dict(bat, file=str(target))
            elif bat and "recolor" in bat:
                target = out_dir / "bat.bin"
                target.write_bytes(bat_from_rule(_bat_rule((folder / bat["recolor"]).read_bytes()), game, srcs))
                d["bat"] = {k: v for k, v in bat.items() if k != "recolor"} | {"file": str(target)}
            if d.get("icon"):
                d["icon"] = {view: str(folder / rel) for view, rel in d["icon"].items()}
            if d.get("voice"):
                have = {s: folder / d["voice"] / f"{s}.wav" for s in SLOTS if (folder / d["voice"] / f"{s}.wav").is_file()}
                if len(have) == len(SLOTS):
                    d["voice_dir"] = str(folder / d["voice"])
                    d["voice"] = voice_name(cid)
                else:                               # some slots: voice_clips.prepare gives it a set of its own,
                    d.pop("voice")                  # the base's sounds for the rest (git-10's Voice page route)
                    d.setdefault("voice_clips", {s: str(p) for s, p in have.items()})
            if notes:
                d["_note"] = "; ".join(notes)
            out.append(d)
    return out


# ---- command line

def _repo_definitions():
    return sorted((ROOT / "characters").glob("*.json"))


def main(argv=None):
    ap = argparse.ArgumentParser(description="Character packs (.slgchar): export, check, import")
    sub = ap.add_subparsers(dest="cmd", required=True)
    e = sub.add_parser("export")
    e.add_argument("definitions", nargs="*")
    e.add_argument("--all", action="store_true")
    e.add_argument("-o", "--out", default=".")
    e.add_argument("--author", default="")
    e.add_argument("--game")
    c = sub.add_parser("check")
    c.add_argument("pack")
    c.add_argument("--game")
    i = sub.add_parser("import")
    i.add_argument("pack")
    i.add_argument("--dest")
    i.add_argument("--game")
    args = ap.parse_args(argv)
    if args.cmd == "export":
        defs = _repo_definitions() if args.all else [Path(p) for p in args.definitions]
        if not defs:
            ap.error("give definitions or --all")
        failed = 0
        for p in defs:
            try:
                out = export_pack(p, args.out, game=args.game, author=args.author)
                print(f"exported  {p.name:32} -> {out} ({out.stat().st_size // 1024} KB)", flush=True)
            except PackError as err:
                failed += 1
                print(f"can't     {p.name:32} {err}", flush=True)
        return 0 if args.all or not failed else 1
    if args.cmd == "check":
        r = check(args.pack, args.game)
        if not r["ok"]:
            print(f"can't import: {r['error']}")
            return 1
        print(f"ok: {r['name']} on {r['template']} by {r['author'] or 'unknown'}; blocks {r['blocks']}, bat {r['bat']}, "
              f"icons {r['icons']}, voice {r['voice']}")
        for w in r["warnings"]:
            print("note: " + w)
        return 0
    try:
        r = import_pack(args.pack, args.game, args.dest)
    except PackError as err:
        print(f"can't import: {err}")
        return 1
    print(f"imported {r['name']} as 0x{r['id']:02X}: {r['definition']}")
    for w in r["warnings"]:
        print("note: " + w)
    return 0


if __name__ == "__main__":
    sys.exit(main())
