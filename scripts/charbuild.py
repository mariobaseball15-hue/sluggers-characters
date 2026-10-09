"""Add character ids beyond the stock 0x00-0x64 to Mario Super Sluggers (on the clean game).

build(chars, out) takes a list of character definitions (see build_chars.py) and writes a patched
copy of the clean game (game=, default extracted/clean; game_source.py) to `out` (hardlinks + a new
sys/main.dol). Every added character is a definition with a new id, Extra Innings' Rosalina, Orange Toad, Larry
and Luma included (0x81-0x84, no stock slots; docs/stock-slot-migration.md):
  1. New code section at 0x807B7000 and data section at 0x807EE000 (above the Piranha Plants'
     fixed data and buffers, step 9; 0x807B6E80 is a stack top in FUN_80612d80, whose frame writes
     land just above it); OSInit arena low moves up to the end of our data on all three of its
     paths (Dolphin takes the debug-monitor one) so the heap never overlaps them.
  2. Per-id tables relocated and extended to the highest new id: selector (111 lis/lo pairs),
     stats+chemistry (FUN_8046dc2c), windup, star pitch, stamina, changeup, trajectory, catch
     range, hitbox, size/scale, has-own-model. New rows copy the template's, then a definition's
     "table_rows" (whole rows, hex), "table_stats" and the stat and chemistry overrides of the stats row.
  3. Roster build hook (end of FUN_8006ba6c) appends new ids to their family's wheel list; the
     always-available (Mii) range is widened in the wheel-list builders FUN_80430184 and FUN_80071abc.
  4. Chemistry hook (FUN_8015c800): pairs involving a new id read the new character's master stats
     row, so chemistry is defined once per new character and applies both ways; new-new pairs are 1.
  5. Select-screen portraits: at the five places the menus pick a portrait (resource id + 0x149,
     or the big preview FUN_80395db0), new ids pass the inline "normal character" test (0..0x4C;
     otherwise they fall to the "?" / Mii path) and are aliased to the template id. The model
     resolver FUN_80367060 aliases new id -> template id too (the template's model).
  6. Icon bank (dt_na.dat dir 119 file 2): its three source tables (normal_a, side, front) are
     step-keyed animation tracks, frame = character id -> icon resource id. Each gets a key for
     every new id (copied from the template: its portraits) and its last-frame field (+0x18) raised
     to cover the highest new id. The tables grow in place (back to back, into free space before
     the private icon images) in the output's own copy of dt_na.dat; main.dol's index is unchanged.
  0. Optional (poltergust=True): Luigi's dive is Suction Catch with the Poltergust 3000
     (build_poltergust.py, docs/dive-catch.md): the prop entry and Luigi's animation bank with his
     special catch playing the dive (dive_catch_bank) are appended to dt_na.dat and his dir 19 files
     5 and 6 point at them, plus three DOL edits
     (prop request words, catch-animation prop mask, fielding ability).
  8. Other sessions' finished features (git-ce, tested in Dolphin): Clamber solo buddy jump
     (buddy_clamber_code.apply), and mini-map decoys (pompom_decoys.apply) for the character whose
     definition sets "minimap_decoys": true (Pom Pom).
  7. Optional (grid_square=True): the team-roster select grid sized to the new squares (gridcells.py, up to 12x5).
  10. Custom voices (voices=True): characters whose definition sets "voice" get their own
     12-slot table from the clean archive's ids (models/work/sounds/clean/voice_tables.json, build_voices.py),
     routed by voice_hooks.py; the select-voice caller's "normal character" test (0x804A55D4) lets new
     ids through.
  11. Batter depth (batter_depth=True): human batters step up / back in the box with the Nunchuk
     stick (batter_depth.py).
  12. New stadium (stadium=stadiums/*.json, new_stadium.py): stadium id 10 as a copy of a stock
     stadium, on the select map in Toy Field's slot. Its directories go in before the directory table is
     relocated (12a); its tables, hooks and map patches before the plants (12b), and dino_piranhas is
     pointed at its longer object tables so the new stadium gets the template's plants.
  15. Its field dimensions by day / night (definition "dimensions", stadium_dimensions.py,
     docs/stadium-dimensions.md): a match-load hook in its own text section above the Bob-ombs'; the
     collision files are its archive files 3 / 4 (collision_files); the hazards build with the new fences.
  12. Star Bits (star_bits=True): a 7th batting item (id 6, the cut Thunder slot): roulette + HUD;
     with it Ice (id 7, ice_item.py): the Fireball, but a hit fielder freezes
     (starbits_roulette), POW-style throw landing as 4 hopping star bits that are banana hazards
     (starbits_item), Star Bit model in item slot 0x2A x4 (starbits_model).
  13. Character names (char_names.py): new characters' names in the name table (dt_na dir 121 file 5,
     index = id, every language), and the name widgets show them.
  9. Optional (dino_plants=True): Piranha Plants for the character whose definition sets
     "piranha_plants": true (Dino Piranha; dino_piranhas.apply, git-ce): code at DINO_CODE in our
     text section, its data at fixed addresses 0x807BC000.. in a second data section, its work
     buffers below DATA_BASE.
  16. Boom Boom's star throw, the Tantrum Toss fielding ability (abilities.py, docs/abilities.md): a
     definition's "stats": {"fielding ability": 13} (boom_boom_star_throw.py, docs/boom-boom-star-throw.md):
     fielding with the ball, A+B spends a star for a spin over his cut-in backdrop and the buddy throw. Its code
     and data go in their own section after 13-15 (merged with them), arena low above it. The ability's label
     (stock glyphs, the game's star after the text; the label widgets recoloured so it shows white) is a new
     row of the select layout, written into the fielding label table's padding.
  17. Item / special abilities (item_abilities.py, docs/abilities.md "Item abilities"): a definition's
     "item_ability": "<name>" (or "special_ability") shows as a fifth skill on the info cards (character
     select, batting-order bubble, third screen), with its own "?" block icon: the three status widgets
     append it after the stock skills (hooks + tables in the item section), and its icon and label rows go
     at the end of dir 119 file 19 (every language); the tables get the rows when the layout is written.
     A "hitting_ability" is a sixth (the bat icon, after the star swing). The cards show up to 4 lines (a
     4-line layout: new nodes of file 19 elements 0xC0 / 0x59), and captain select shows the same lines as
     the card (its own hooks, a 4th line in file 18 element 0x17, its rows at the end of file 18).
"""
import json, os, re, shutil, struct, sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
from dol import Dol
from ppc import Asm, ha, lo
from PIL import Image
import cmpr
import gridcells
import hilo_refs
import dtna_toc
import game_source
import abilities
import item_abilities
import star_move_labels
from sluggers_data import STAT_FIELDS, CHEM_BASE, NEUTRAL, char_id

ROOT = Path(__file__).resolve().parents[1]
# the build base: the clean game with our own voice routing (voice_hooks.py); docs/clean-base.md. Extra Innings'
# four characters are definitions with new ids (docs/stock-slot-migration.md); the icon bank is made from the clean
# game in Extra Innings' layout (icon_bank.base_bank). BASES["ei"] is a name only: building on it is retired (build()),
# and no build step reads it (model_files takes clean-game overlays only; bullet_bill.draw_icon reads the game).
BASES = {"ei": ROOT / "extracted/extra-innings", "clean": game_source.DEFAULT}
SRC = BASES["clean"]              # the default game only: the build reads game_source.root() (build(game=))
# The build's work folder (build(work=), default models/work): the files under it that are DERIVED FROM THE
# GAME, made ahead of time from the clean game by the scripts named here. They can't ship (they are Nintendo's
# files, changed), so the patcher makes them from the player's game into its own work folder, laid out as
# models/work. Everything else under models/work is our own (packs, props, drawn icons) and stays in the repo.
WORK = ROOT / "models/work"
DERIVED = ("sounds/clean/",         # MY2.brsar + voice_tables.json: build_voices.build(<game>/files/sound_NA/
                                    #   MY2.brsar, <work>/sounds/clean)
           "recolor/",              # recolor.py recipes (the patcher already uses recolor.make(work=))
           "bats/",                 # bat_recolors.py / make_bat.py: stock bats, recolored
           "ice-bro/blocks/",       # Fire Bro's model block, recolored (ice-bro-over-firebro)
           "rosalina/anim/",        # straighten_anim.py: Daisy's ANM banks (dir 23 = EI dir 90), straightened
           "lemmy/ride/anim/",      # lemmy_ride.py: Bowser Jr.'s ANM banks with the ball's bone keys
           "pauline_chance/")       # star_chance.png: pauline_chance_tuning.write_assets (render_banner of the
                                    #   stock HUD layout; when it is missing, patch_layout renders the same image)
_work = WORK


def derived(rel):
    """rel (relative to models/work, '/'-separated) is a game-derived file: in a DERIVED folder, or a recolor
    recipe's portrait (recolor.py writes icons/new/<recipe>_side.png / _front.png from the game's own)."""
    if rel.startswith(DERIVED):
        return True
    m = re.fullmatch(r"icons/new/(.+)_(side|front)\.png", rel)
    return bool(m) and (ROOT / "recolors" / f"{m.group(1)}.json").exists()


# the output's files the build rewrites: copied, never hard-linked, so replacing them never touches the source (a
# player's read-only or locked cache/game/files/dt_na.dat stopped the build with PermissionError on the unlink)
REWRITTEN = {"dt_na.dat", "main.dol", "MY2.brsar"}


def _link_or_copy(src, dst):
    """copytree's copy_function: a hard link (no 4 GB copy), a copy for REWRITTEN or where linking fails."""
    if os.path.basename(src) not in REWRITTEN:
        try:
            return os.link(src, dst)
        except OSError:                                             # another drive, FAT, no permission
            pass
    shutil.copyfile(src, dst)
    return dst


def _unlink(path):
    """Remove an output file even when Windows marks it read-only."""
    try:
        os.unlink(path)
    except PermissionError:
        os.chmod(path, 0o666)
        os.unlink(path)


def work_file(rel):
    """A models/work file by its path under models/work: a game-derived one from the build's work folder."""
    return (_work if derived(rel) else WORK) / rel


def asset(path):
    """A repo path from a definition or table (e.g. "models/work/bats/x.bin"): models/work files through
    work_file, anything else (or an absolute path, as recolor.make(work=) writes) as it is."""
    path = Path(path)
    if not path.is_absolute() and path.parts[:2] == ("models", "work"):
        return work_file("/".join(path.parts[2:]))
    return ROOT / path

# our code, then the Piranha Plants' code. DINO_CODE was 0x807B9000; our code outgrew those 8 KB (0x2018 B with
# the star swings, captains and stadium), so it moved up 4 KB: the plants' code (0x157C B) still ends before their
# data at 0x807BC000. 0x807BA000 -> 0x807BA800 when our code reached 0x2F30 of 12 KB (character names): the
# plants' code still ends at 0x807BBD7C, before their data (checked where it is placed).
# 0x807BA800 -> 0x807BA400 when the plants' code outgrew its 6 KB (0x177C B, 0x84 B left; the plant
# behaviour rework, now 0x17C8 B): ours is 0x2A00-0x2E40 (quick-game builds) of 13 KB.
CODE_BASE, DINO_CODE = 0x807B7000, 0x807BA400
# Our sections above dino_piranhas' fixed data and buffers (0x807EE3A0 with the new stadium's plants; they must end at
# ITEMS_BASE), each sized by what goes in it (Phase 1 of docs/mod-tables.md; they had fixed limits that were raised by
# hand as the data grew: 0x807FE000 .. 0x80818000):
#   ITEMS_BASE   the batting-item code (koopa_items and every later feature's stubs: the main code section is full),
#                ITEMS_SIZE long: its code is assembled at its address as the build goes, so it keeps a fixed budget
#                (0x2000 .. 0x5000 as the level 5 / 6 CPU and wendy_rings grew; 0x5000 -> 0x8000 when the
#                default build's reached 0x6618: cpu_items, cpu_item_defense, cpu_subs, cpu_rundown, cpu_track, ...).
#                A build whose item code doesn't fit (the player's own items: up to 8 of them, each with its
#                stubs) is built again with it ITEMS_GROW longer, up to ITEMS_MAX (build(): sized by content;
#                every build that fits keeps 0x8000, byte for byte), moving the data section and arena low up with it
#   DATA_BASE    the data section, right after it: the per-id tables at 256 rows, the new-by-new chemistry,
#                directories, ... It ends where its content does (nothing is put in it after it is placed);
#                DATA_LIMIT only caps it
#   then         the feature sections (Octoombas, Bob-ombs, dimensions, ...) from the data's end, and arena low
#                right after the last of them
ITEMS_BASE, ITEMS_SIZE = 0x807EF000, 0x8000
ITEMS_DEFAULT, ITEMS_GROW, ITEMS_MAX = ITEMS_SIZE, 0x2000, 0x10000
DATA_BASE = ITEMS_BASE + ITEMS_SIZE
DATA_SPAN = 0x40000                      # a cap, not a size: the most MEM1 the data section may take
DATA_LIMIT = DATA_BASE + DATA_SPAN


def items_layout(size):
    """The item section `size` long, the data section (and its cap) right after it (build(): an item code overflow)."""
    global ITEMS_SIZE, DATA_BASE, DATA_LIMIT
    ITEMS_SIZE = size
    DATA_BASE = ITEMS_BASE + ITEMS_SIZE
    DATA_LIMIT = DATA_BASE + DATA_SPAN
SECTION_ALIGN = 0x1000                   # the data section's end, rounded (the next section starts on a page, as before)
ARENA_LO = 0x807B6E80
# the highest arena low the game's MEM1 heaps fit under. The game makes one fixed-size 15 MB expanded heap (a 10 MB
# and a 5 MB child) at arena low + 0x4006C, whatever arena low is, so raising arena low moves its end up; above it,
# up to arena high (0x817FF420-0x817FF480 in the dumps), MEM1 is unused (zero). Six RAM dumps (analysis/heap-cal-1
# first-pitch / run-scored and ramdump-stadium-select at arena low 0x80866A00, ramdump-cpuvcpu / -cpuvcpu-2 /
# -selchem-1 at 0x8081B000): heap end = arena low + 0xF4006C every time, zeros up to arena high. So arena low may go
# up to 0x817FF420 - 0xF4006C = 0x808BF3B4 (docs/mod-tables.md "Memory layout").
ARENA_LO_MAX = 0x808BF000
STOCK_IDS = 0x65       # ids 0x00-0x64; 0x65 is the "no character" sentinel
# the id limit (docs/mod-tables.md, docs/char-limit-sites.md): the game's id bounds take every id up to ID_BOUND, so no
# bound depends on the build's characters; real ids end at MAX_ID (0xFF ends lists: gridcells, grid_order, quickboot)
ID_BOUND, MAX_ID = 0xFF, 0xFE
# Color-wheel swatch per character (selector byte 7): the time on the wheel popup's swatch elements
# 0xAD / 0xAE (dir 119 file 19), whose keys hold the color. 0-9 are stock; 10 was an unused white end
# key and gridcells recolors it orange. A definition's "color" picks its swatch (Nick: its primary color).
SWATCHES = {"red": 0, "blue": 1, "yellow": 2, "green": 3, "purple": 4, "black": 5, "brown": 6,
            "lightblue": 7, "pink": 8, "white": 9, "orange": 10}
STATS_HEADER, STATS_ROW = 8, 0x8E

# (name, address, row size, header bytes)
TABLES = [
    ("selector", 0x80631550, 8, 0),
    ("stats", 0x806CE9A0, STATS_ROW, STATS_HEADER),
    ("pitchwindup", 0x80628400, 12, 0),
    ("starpitch", 0x806288BC, 1, 0),
    ("stamina", 0x80628924, 2, 0),
    ("changeup", 0x80628EB0, 8, 0),
    ("traj", 0x8062A15C, 2, 0),
    ("catchrange", 0x8062A688, 40, 0),
    ("hitbox", 0x8062BA08, 8, 0),
    ("sizescale", 0x8062EB50, 8, 0),
    # freeze ice block scale per character id (FUN_800f4e78: FUN_800f1258(player) is the character id);
    # unextended, new characters' ice block read past the table and did not show (Nick's Ice item)
    ("icescale", 0x806250E8, 4, 0),
    ("hasmodel", 0x806B4970, 1, 0),
    # indexed by the player's character id (player +0x2A); found by a size scan (101 rows)
    ("charfloats", 0x806291D8, 0x24, 0),   # per-character floats (Extra Innings tunes Luma's row)
    ("perid2", 0x8062A00C, 2, 0),
    ("perid6", 0x8062A424, 6, 0),           # FUN_8013d070 / FUN_80174f40 -> FUN_804b9bd4
    ("perid4", 0x8062B874, 4, 0),           # FUN_801295ec -> FUN_804b9bd4
    # found by a sweep for player +0x2A times a stride (101 rows each, refs to the base only)
    ("throwfloats", 0x806289F0, 0xC, 0),    # float at +8 (FUN_80162358)
    ("perid5a", 0x8062A228, 5, 0),          # bytes (FUN_801799e8) -> FUN_804b9bd4
    ("throwvariant", 0x8062B678, 5, 0),     # throw per distance (FUN_800def08...) -> FUN_804b9bd4;
                                            # unextended, new ids never released the ball (git-e2)
    # the charge effects' scale per character (floats, copied to the stack and read at +0x2A: charge_scale);
    # unextended, new ids' pitch charge circles did not show (Nick)
    ("pitchchargescale", 0x80624F30, 4, 0),  # FUN_800f33c8, the pitcher's
    ("batchargescale", 0x80624D98, 4, 0),    # FUN_800f2e10, the batter's
    # two more effect sizes per character found by the id-limit sweep (docs/char-limit-sites.md): read at the
    # character's id (FUN_800f1258), unextended a new id read the next table
    ("effectscale_c00", 0x80624C00, 4, 0),   # FUN_800f6ab0 / FUN_800fd430 (Mario 1.3, DK 2.0, ...)
    ("effectscale_2b0", 0x806252B0, 4, 0),   # FUN_800fb084, from a stack copy (charge_scale); 1.0 for every stock id
]


class Overflow(AssertionError):
    """A Space ran past its limit ("section overflow"); base: that section's start (build() grows the item section)."""

    def __init__(self, base):
        super().__init__("section overflow")
        self.base = base


class Space:
    """Sequential allocator inside a new DOL section."""
    def __init__(self, base, limit):
        self.base, self.limit, self.blob = base, limit, bytearray()

    @property
    def here(self):
        return self.base + len(self.blob)

    def put(self, data, align=32):
        self.blob += b"\0" * (-len(self.blob) % align)
        addr = self.here
        self.blob += data
        if self.here > self.limit:
            raise Overflow(self.base)
        return addr


def normalize(chars):
    """Resolve names to ids and fill defaults. Each def: id, template, name, stats{}, chemistry{}.
    Chemistry keys are stock names/ids or another new character's name (new-new pairs: new_chemistry).
    Stock entries ({"stock": true}) in the list are left out: normalize_stock takes them."""
    out = []
    chars = [c for c in chars if not c.get("stock")]
    new_names = {}                      # every name a new character goes by (a renamed one: each language's)
    for c in chars:
        n = c.get("name", "")
        for v in (n.values() if isinstance(n, dict) else [n]):
            new_names[str(v).strip().lower()] = char_id(c["id"])
    new_ids = set(new_names.values())
    # every definition's name and id (characters/*.json, recolors/*.json): a chemistry key naming one that isn't in
    # this build (the patcher builds subsets) is skipped; a name that is no character at all is still an error
    known = {}
    for p in [*(ROOT / "characters").glob("*.json"), *(ROOT / "recolors").glob("*.json")]:
        try:
            d = json.loads(p.read_text(encoding="utf8"))
            known[str(d.get("name", "")).strip().lower()] = char_id(d["id"])
        except (ValueError, KeyError, TypeError):
            continue

    def chem_id(k):
        """A chemistry key's id, or None when it names a new character that is not in this build."""
        name = k.strip().lower() if isinstance(k, str) else None
        if name in new_names:
            return new_names[name]
        if name in known:
            return None
        try:
            cid = char_id(k)
        except KeyError:                # a player's character since renamed or deleted (a player's 1.0 build stopped
            return None                 # on "Model (5)"): skipped with the others, not a stop
        return None if cid > STOCK_IDS and cid not in new_ids else cid
    for c in chars:
        cid, tmpl = char_id(c["id"]), char_id(c["template"])
        assert cid > STOCK_IDS, f"new ids start at 0x{STOCK_IDS + 1:X} (0x65 is the 'none' sentinel)"
        assert cid <= MAX_ID, f"new ids end at 0x{MAX_ID:X} (0xFF ends the build's id lists)"
        assert tmpl < STOCK_IDS, "template must be a stock id"
        stats = dict(c.get("stats", {}))
        unknown = set(stats) - set(STAT_FIELDS)
        assert not unknown, f"unknown stat names: {sorted(unknown)} (see scripts/sluggers_data.py)"
        own_swing = {k: stats[k] for k in ("star swing", "captain") if k in stats}   # (degrade: custom-swings off)
        if c.get("star swing") is not None:        # per-character key (custom_swings.assign): its stand-in and flag
            import custom_swings
            swing, flag = custom_swings.stats_of(int(c["star swing"]), cid)
            stats.update({"star swing": swing, "captain": flag})
        if int(stats.get("star pitch", 0)) and "captain" not in c.get("stats", {}):
            stats["captain"] = 1                   # a star move needs the captain flag, as stock_rows does (git-b6)
        assert abilities.valid(int(stats.get("fielding ability", 0))), \
            f"{c.get('name')}: fielding ability {stats['fielding ability']} (stock 0-12 or abilities.NEW)"
        assert "star_throw" not in c, f"{c.get('name')}: \"star_throw\" is now the Tantrum Toss fielding ability " \
            f"(\"stats\": {{\"fielding ability\": {abilities.TANTRUM_TOSS}}})"
        chem = {chem_id(k): int(v) for k, v in c.get("chemistry", {}).items()}
        skipped = [str(k) for k in c.get("chemistry", {}) if chem_id(k) is None]
        chem.pop(None, None)
        # "chemistry_like": <base> (recolor.make; Nick: a recolor has its base's chemistry): every pair this
        # definition doesn't set takes the base's value, both ways (extended_rows, new_chemistry). A base that
        # isn't in this build: neutral, as before.
        # A character the player made (New character, a .sluggie; "made_by": "player") has its template's chemistry
        # the same way unless it says otherwise (Nick: "super dk doesn't have donkey kong's default chemistry").
        like_ref = c.get("chemistry_like", c["template"] if c.get("made_by") == "player" else None)
        like = chem_id(like_ref) if like_ref is not None else None
        color = c.get("color")
        wheel = char_id(c.get("wheel", c["template"]))
        assert wheel < STOCK_IDS, "wheel must be a stock character"
        assert color is None or color in SWATCHES, f"{c.get('name')}: color {color!r} is not one of {sorted(SWATCHES)}"
        icon = c.get("icon")
        if icon:
            assert set(icon) == {"side", "front"}, "icon needs side and front PNGs (48x51)"
            icon = {view: asset(path) for view, path in icon.items()}
            assert all(path.exists() for path in icon.values()), f"missing icon art: {icon}"
        out.append(dict(id=cid, template=tmpl, name=c.get("name", f"0x{cid:02X}"), stats=stats, chemistry=chem,
                        model_overlay=c.get("model_overlay") or (c["name"] if c.get("model_blocks") else None),
                        model_blocks=c.get("model_blocks"), bat=c.get("bat"), icon=icon,
                        minimap_decoys=bool(c.get("minimap_decoys")),
                        piranha_plants=bool(c.get("piranha_plants")), voice=c.get("voice"),
                        batting_item=c.get("batting_item"), always_item=bool(c.get("always_item")), scale=float(c.get("scale", 1)), color=color,
                        wheel=wheel, square=c.get("square"), own_square=bool(c.get("own_square")),
                        table_stats=_check_table_stats(c.get("table_stats", {}), c.get("name")),
                        table_rows=_check_table_rows(c.get("table_rows", {}), c.get("name")),
                        item_ability=item_abilities.of(c), hitting_ability=star_move_labels.hitting_of(c),
                        running_ability=star_move_labels.running_of(c), chemistry_skipped=skipped,
                        batter_star=c.get("batter_star"), own_swing=own_swing, chance_cheer=c.get("chance_cheer"),
                        chemistry_like=like if like != cid else None,
                        **{"star swing": c.get("star swing")}))
    return sorted(out, key=lambda c: c["id"])


# Stock entries (the patcher's per-character options on stock characters, docs/patcher.md): {"id", "name", "stock":
# true, <keys>} in the same chars list as the definitions. No new id, name, portrait or grid square: the keys go to the
# same per-character steps as a definition's, and "stats" / "star pitch" / "fielding ability" / "star swing" are
# written into the character's own stats row, in place.
STOCK_KEYS = ("piranha_plants", "minimap_decoys", "batter_star", "star swing", "star pitch", "fielding ability",
              "batting_item", "always_item", "stats", "chance_cheer", "item_ability", "special_ability",
              "hitting_ability", "running_ability", "table_stats", "chemistry", "rename")
# This mod's own stock entries, under the profile's (a profile entry for the same id adds its keys over them).
# build(char_defaults=False) leaves them out, with every helper's DEFAULT_CHARS (only the keys in the list count).
STOCK_DEFAULTS = [{"id": 0x25, "name": "King Boo", "stock": True, "star pitch": 16}]   # pitch_vanishing_ball.NEW_ID
# The Kongs' Clamber Jump (abilities.CLAMBER_JUMP; Nick, 2026-09-26: every Kong, so the default roster plays as before
# the split; stock Clamber for a profile without our defaults)
STOCK_DEFAULTS += [{"id": cid, "name": name, "stock": True, "fielding ability": 14}
                   for cid, name in ((0x02, "Donkey Kong"), (0x03, "Diddy Kong"), (0x27, "Dixie Kong"),
                                     (0x38, "Funky Kong"), (0x39, "Tiny Kong"), (0x41, "Baby DK"))]
STAR_PITCHES = 20                  # star pitch ids 0-12 stock, 13-16 ours (pitch-path, pitch-items, pitch-vanish),
#                                    17-20 new ones (pitch_new: star pitch creations with names of their own)


def normalize_stock(chars, defaults=True):
    """The stock entries of a chars list, normalized like normalize's definitions for the per-character steps and
    degrade: id (a stock id), template (its own id), name, stats (the "stats" overrides, with "star pitch" and
    "fielding ability" folded in), "star swing", and the other STOCK_KEYS as given (None when absent: a false value
    removes a character from a helper's defaults, so an absent key must stay None; e.g. "always_item").
    defaults: STOCK_DEFAULTS first. Entries for one id are merged (later keys win); in id order."""
    from sluggers_data import CHAR_NAMES
    merged = {}
    for e in [*(STOCK_DEFAULTS if defaults else ()), *(c for c in chars if c.get("stock"))]:
        cid = char_id(e["id"])
        assert 0 <= cid < STOCK_IDS, f"stock entry {e.get('name', e['id'])}: 0x{cid:02X} is not a stock id"
        bad = set(e) - set(STOCK_KEYS) - {"id", "name", "stock"}
        assert not bad, f"stock entry {e.get('name', e['id'])}: unknown keys {sorted(bad)} (STOCK_KEYS)"
        m = merged.setdefault(cid, {})
        m.update({k: v for k, v in e.items() if k != "stats"})
        m["stats"] = {**m.get("stats", {}), **e.get("stats", {})}
    out = []
    for cid, e in sorted(merged.items()):
        name = e.get("name") or CHAR_NAMES[cid].strip()
        stats = dict(e["stats"])
        unknown = set(stats) - set(STAT_FIELDS)
        assert not unknown, f"{name}: unknown stat names: {sorted(unknown)} (see scripts/sluggers_data.py)"
        for k in ("star pitch", "fielding ability"):
            if e.get(k) is not None:
                stats[k] = int(e[k])
        assert abilities.valid(int(stats.get("fielding ability", 0))), \
            f"{name}: fielding ability {stats['fielding ability']} (stock 0-12 or abilities.NEW)"
        assert 0 <= int(stats.get("star pitch", 0)) <= STAR_PITCHES, \
            f"{name}: star pitch {stats['star pitch']} (stock 0-12, ours 13-16, new ones 17-{STAR_PITCHES})"
        if e.get("star swing") is not None:
            import custom_swings
            custom_swings.stats_of(int(e["star swing"]), cid)        # asserts a known swing
        if e.get("batting_item") not in (None, False, "", "none"):
            import batter_items
            batter_items.item_id(e["batting_item"])                 # asserts a known item
        table = dict(e.get("table_stats") or {})
        unknown = set(table) - set(TABLE_STATS)
        assert not unknown, f"{name}: unknown table values {sorted(unknown)} (TABLE_STATS)"
        chem = {}
        for other, v in (e.get("chemistry") or {}).items():
            oid = char_id(other)
            assert 0 <= oid < STOCK_IDS, (f"{name}: chemistry with {other}: a stock character's chemistry names stock "
                                          f"characters (a new character's pairs go in its own definition)")
            assert int(v) in (0, 1, 2), f"{name}: chemistry with {other} {v} (0 bad, 1 neutral, 2 good)"
            chem[oid] = int(v)
        out.append(dict(id=cid, template=cid, name=name, stock=True, stats=stats, own_swing={},
                        piranha_plants=e.get("piranha_plants"), minimap_decoys=e.get("minimap_decoys"),
                        batter_star=e.get("batter_star"), batting_item=e.get("batting_item"),
                        always_item=e.get("always_item"), chance_cheer=e.get("chance_cheer"),
                        item_ability=item_abilities.of(e), hitting_ability=star_move_labels.hitting_of(e),
                        running_ability=star_move_labels.running_of(e), table_stats=table, chemistry=chem,
                        rename=e.get("rename"),
                        **{"star swing": e.get("star swing")}))
    return out


NAME_LANGUAGES = {"en": 0, "es": 1, "fr": 2}     # dir 121 file 5's three tables


def profile_names(stock, chars):
    """The character editor's names (docs/character-editor.md): ({stock id: name}: char_names.STOCK_RENAMES and the
    stock entries' "rename", {language: {id: name}}: the Spanish / French names of a "rename" or a new character's
    "names"). A name is one string (every language) or {"en", "es", "fr"} (a missing one is the English). The name
    plate and the banner are drawn once, from the English name."""
    import char_names
    renames, by_language = char_names.stock_renames(), {}

    def split(cid, value):
        names = {"en": value} if isinstance(value, str) else dict(value)
        bad = set(names) - set(NAME_LANGUAGES)
        assert not bad, f"0x{cid:02X}: name languages {sorted(bad)} (en, es, fr)"
        en = names.get("en") or next(iter(names.values()))
        for lang, text in names.items():
            if lang != "en" and text and text != en:
                by_language.setdefault(NAME_LANGUAGES[lang], {})[cid] = text
        return en
    for e in stock:
        if e.get("rename"):
            renames[e["id"]] = split(e["id"], e["rename"])
    for c in chars:
        if not c.get("stock") and c.get("names"):
            split(char_id(c["id"]), c["names"])
    return renames, by_language


def stock_rows(dol, stock):
    """Build step 0d: the stock entries' stats rows, in place (after stock_stat_edits, before the stats table is
    copied): "stats" by name, "star swing" (custom_swings.stats_of: +9 the stand-in, +7 its flag), and a nonzero
    "star pitch" (+8) sets the captain flag +7 (a star move needs it) unless "stats" sets "captain". Returns
    ({id: the row before}, log lines, {table: {id: its row before}}): new characters built on one of these copy the
    rows before (their template's own, not the profile's options). "chemistry" ({stock id: 0/1/2}) is written into
    both characters' rows; "table_stats" into the per-character tables (TABLE_STATS)."""
    import custom_swings
    before, out, table_before = {}, [], {}
    tables = {t[0]: t for t in TABLES}
    for e in stock:
        cid = e["id"]
        row = 0x806CE9A0 + STATS_HEADER + cid * STATS_ROW
        assert int.from_bytes(dol.read(row, 2), "big") == cid, f"stats row 0x{cid:02X}"
        buf = bytearray(dol.read(row, STATS_ROW))
        before[cid] = bytes(buf)
        for stat, value in e["stats"].items():
            _put_stat(buf, stat, value)
        cap = STAT_FIELDS["captain"][0]
        if e["star swing"] is not None:
            swing, flag = custom_swings.stats_of(int(e["star swing"]), cid)
            buf[STAT_FIELDS["star swing"][0]] = swing
            if "captain" not in e["stats"]:
                buf[cap] = flag
        if int(e["stats"].get("star pitch", 0)) and "captain" not in e["stats"]:
            buf[cap] = 1
        for oid, v in e.get("chemistry", {}).items():
            buf[CHEM_BASE + oid] = v
        if bytes(buf) != before[cid]:
            dol.write(row, bytes(buf))
            what = [f"{k} {v}" for k, v in e["stats"].items()] + (
                [f"star swing {e['star swing']}"] if e["star swing"] is not None else []) + (
                [f"chemistry with {len(e['chemistry'])}"] if e.get("chemistry") else [])
            out.append(f"0x{cid:02X} {e['name']}: " + ", ".join(what))
        for oid, v in e.get("chemistry", {}).items():             # the other character's row, the other way
            other = 0x806CE9A0 + STATS_HEADER + oid * STATS_ROW
            assert int.from_bytes(dol.read(other, 2), "big") == oid, f"stats row 0x{oid:02X}"
            dol.write(other + CHEM_BASE + cid, bytes([v]))
        for stat, value in e.get("table_stats", {}).items():
            table, off, kind = TABLE_STATS[stat]
            _, addr, size, header = tables[table]
            at = addr + header + cid * size
            rowbuf = bytearray(dol.read(at, size))
            table_before.setdefault(table, {}).setdefault(cid, bytes(rowbuf))
            _put_table_stat(rowbuf, off, kind, value, stat)
            dol.write(at, bytes(rowbuf))
        if e.get("table_stats"):
            out.append(f"0x{cid:02X} {e['name']}: " + ", ".join(f"{k} {v}" for k, v in e["table_stats"].items()))
    return before, (["stock rows   " + "; ".join(out)] if out else []), table_before


def dat_diff_ranges(a, b, limit, chunk=1 << 22):
    """Byte ranges [start, end) where files a and b differ within the first `limit` bytes."""
    ranges, off = [], 0
    with open(a, "rb") as fa, open(b, "rb") as fb:
        while off < limit:
            x, y = fa.read(chunk), fb.read(chunk)
            if not x or not y:
                break
            if x != y:
                n, i = min(len(x), len(y)), 0
                while i < n:
                    if x[i] != y[i]:
                        j = i
                        while j < n and x[j] != y[j]:
                            j += 1
                        if ranges and off + i - ranges[-1][1] < 0x1000:
                            ranges[-1][1] = off + j
                        else:
                            ranges.append([off + i, off + j])
                        i = j
                    else:
                        i += 1
            off += chunk
    return ranges


def model_files(c):
    """The character's model files for its template's dt_na.dat directory (18 + template id):
    {file index: bytes}. From "model_blocks" ({file index: block file}, e.g. build_model.py's
    pack/high.bin and low.bin) when the definition has it; otherwise diffed out of the
    model_overlay folder, a copy of the clean game with a model packed over the template. (Overlays made from an
    Extra Innings copy are refused: the build reads nothing of extracted/extra-innings; every definition has
    model_blocks.)"""
    if c.get("model_blocks"):
        return {int(i): asset(path).read_bytes() for i, path in c["model_blocks"].items()}
    other = ROOT / "extracted" / c["model_overlay"] / "files/dt_na.dat"
    base = game_source.root()
    assert os.path.getsize(base / "files/dt_na.dat") == os.path.getsize(other),         f"{c['model_overlay']}: dt_na.dat is not the clean game's size (an Extra Innings overlay: give it model_blocks)"
    base_dol = Dol(base / "sys/main.dol")
    changed = dtna_toc.locate(base_dol, dat_diff_ranges(base / "files/dt_na.dat", other, os.path.getsize(other)))
    model_dir = c["template"] + MODEL_DIR_BASE
    stray = sorted(k for k in changed if k[0] != model_dir)
    assert not stray, f"{c['model_overlay']}: changes outside dir {model_dir} (template's models): {stray}"
    out = {}
    with open(other, "rb") as f:
        for (_, index), (off, length) in sorted(changed.items()):
            f.seek(off)
            out[index] = f.read(length)
    return out


def textures_only(block, template):
    """True when a model block is its template's block with only texture pixels / palettes changed (a recolor,
    a texture pack): same length, same bytes everywhere else."""
    from mss_model import Model
    if len(block) != len(template):
        return False
    try:
        texs = Model(template).textures
    except Exception:
        return False
    a, b = bytearray(block), bytearray(template)
    for t in texs:
        spans = [(t.image, t.payload_size())] + ([(t.palette, 512)] if t.format == 9 and t.palette else [])
        for off, n in spans:
            a[off:off + n] = b[off:off + n] = bytes(n)
    return a == b


def own_squares(chars, squares, layout, placed=()):
    """(squares, layout, log lines): each character with "own_square" (a .sluggie model or a New character, git-92:
    Nick found "Daisy custom is in daisy's color wheel") gets a new square of its own, at the end of the layout (as
    wheel_overflow's extra squares), unless it's on a square already. With every new square used it stays on its
    template's wheel, and the log says so. placed: ids the grid-order put on a stock square's wheel (to_tables'
    "wheels"): they stay there, no square of their own too (a player's import moved onto Bowser's wheel was also
    at the end of the grid)."""
    import gridcells
    low = lambda v: str(v).strip().lower()  # noqa: E731
    present = {low(c["name"]) for c in chars} | {c["id"] for c in chars}
    key = lambda m: m if isinstance(m, int) else low(m)  # noqa: E731
    used = sum(1 for sq in squares if any(key(m) in present for m in sq))
    on = {key(m) for sq in squares for m in sq}
    if not any((c.get("own_square") or c.get("_pack")) and not c.get("stock") for c in chars):   # (_pack: an
        # imported pack's definition as the Select grid editor reads it, before materialize sets own_square)
        return squares, layout, []
    flat = bool(layout) and not isinstance(layout[0], (list, tuple))     # grid_order's tables: a flat list
    rows = [list(layout)] if flat else [list(row) for row in layout or []]
    out_sq, log = [list(sq) for sq in squares], []
    for c in sorted(chars, key=lambda c: c["id"]):
        if not (c.get("own_square") or c.get("_pack")) or c.get("stock") or low(c["name"]) in on or c["id"] in on \
                or c["id"] in placed:
            continue
        if used >= gridcells.N_NEW_SQUARES:
            log.append(f"own square   {c['name']}: every new square is used: on its template's wheel")
            continue
        free = next((k for k, sq in enumerate(out_sq) if sq and not any(key(m) in present for m in sq)), None)
        cell = None                                 # the layout cell it takes: an absent square's (the layout stays
        if free is not None:                        # 5 x 12), else a new row's (as wheel_overflow's)
            old = key(out_sq[free][0])
            cell = next(((i, j) for i, row in enumerate(rows) for j, n in enumerate(row) if key(n) == old), None)
        if len(out_sq) >= gridcells.N_NEW_SQUARES and free is not None:
            out_sq[free] = [c["name"]]              # a square none of whose characters is in this build: its slot
        else:
            out_sq.append([c["name"]])
        used += 1
        if layout is None:                          # (no layout: gridcells' own order)
            pass
        elif cell is not None:
            rows[cell[0]][cell[1]] = c["name"]
        elif flat:
            rows[0].append(c["name"])
        else:
            if not rows or len(rows[-1]) >= len(rows[0]):
                rows.append([])
            rows[-1].append(c["name"])
        log.append(f"own square   {c['name']}")
    return out_sq, layout if layout is None else rows[0] if flat else rows, log


class SquareFull(ValueError):
    pass


def join_squares(squares, chars):
    """squares (names or ids per square) with every character whose "square" names a character on one of them added
    to that square (git-92 / git-a3: a recolor of an added character, e.g. Rosalina's, goes on its base's square,
    as a stock recolor goes on its stock character's wheel). A character already on a square stays where it is; a
    "square" naming someone who isn't on a square in this grid is ignored (the character goes on its "wheel" /
    template's wheel). Raises SquareFull in plain words when the square would hold more than wheel7.MEMBERS."""
    import wheel7
    low = lambda v: str(v).strip().lower()  # noqa: E731
    by_id = {c["id"]: c["name"] for c in chars if "id" in c and "name" in c}
    names = lambda sq: [low(by_id.get(m, m)) for m in sq]  # noqa: E731
    joins = [c for c in chars if c.get("square") and not c.get("stock")]
    if not joins:
        return squares
    out = [list(sq) for sq in squares]
    for c in joins:
        if any(low(c["name"]) in names(sq) for sq in out):
            continue
        k = next((k for k, sq in enumerate(out) if low(c["square"]) in names(sq)), None)
        if k is None:
            continue
        if len(out[k]) >= wheel7.MEMBERS:
            raise SquareFull(f"{c['name']}: {c['square']}'s square is full ({wheel7.MEMBERS} characters); move one "
                             f"of them to another square, or leave {c['name']} out")
        out[k].append(c["name"])
    return out


def resolve_squares(chars, squares=None):
    """squares (default GRID_SQUARES) as character ids (definitions by name, else stock names; ids as they are),
    missing ones dropped."""
    by_name = {c["name"].lower(): c["id"] for c in chars}
    out, missing = [], []
    for square in GRID_SQUARES if squares is None else squares:
        ids = []
        for n in square:
            if isinstance(n, int):
                ids.append(n)
                continue
            if n.lower() in by_name:
                ids.append(by_name[n.lower()])
                continue
            try:
                cid = char_id(n)
            except (KeyError, ValueError):
                cid = None
            if cid is not None and cid < STOCK_IDS:
                ids.append(cid)
            else:
                missing.append(n)
        out.append(ids)
    return out, missing


# Per-character values that live outside the stats row (git-8a, Nick's review editor): name -> (TABLES
# name, byte offset in the row, "B" byte or "f" float). New characters set them in a definition's
# "table_stats"; stock characters in STOCK_TABLE_EDITS. Catch ranges are the raw values (hundredths, before
# the per-index floors and the size scale).
TABLE_STATS = {
    "star pitch type": ("starpitch", 0, "B"),       # 0 none, 1 breaking ball, 2 fastball, 3 change-up
    "changeup speed mult": ("changeup", 0, "f"),
    "changeup arc height": ("changeup", 4, "f"),
    "pitch steering": ("throwfloats", 8, "f"),
    "hit trajectory": ("traj", 0, "B"),             # 0 medium, 1 high, 2 low
    "hit curve": ("traj", 1, "B"),
    "catch normal": ("catchrange", 0, "f"),
    "catch any direction": ("catchrange", 4, "f"),
    "catch centered": ("catchrange", 8, "f"),
    "catch max height": ("catchrange", 12, "f"),
    "catch dive": ("catchrange", 24, "f"),
    # the body cylinder (Nick: "fielding and item hitbox"): radius / height in cm, copied to the player +0x1C / +0x20;
    # fielding and runner contacts (docs/hidden-stats.md), not hit-by-pitch (hit-by-pitch.md)
    "body radius": ("hitbox", 0, "f"),
    "body height": ("hitbox", 4, "f"),
    # the height every pitch crosses the plate at, in model units (x the size-scale row): FUN_800b97a0 -> CBat
    # +0x48 -> the pitch's target y (FUN_8015dc38). scripts/strike_zones.py writes it
    "strike zone height": ("charfloats", 0x1C, "f"),

    "stamina": ("stamina", 0, "h"),   # max stamina, s16 (FUN_80166858; docs/cpu-ai.md)
    # the pitcher's windup countdown in frames (float, 60 Hz; FUN_804b9bd4 converts it for 50 Hz) [C]: FUN_8015cd34
    # loads pitchwindup +0 into pitcher +0x102, which seeds the countdown +0x100; FUN_8015dc38 counts it down and the
    # ball leaves the hand below 0. The CPU batter (FUN_800c4ff4) starts its charge while +0x100 < 0x8062818C[hz]
    # (8 at 60 Hz), and +0x100 already holds this value before the windup moves, so 7 or less = "precharge" [C];
    # stock 5-33, precharge: Baby Luigi, Bowser, Dixie, Baby Peach, Baby Daisy 7, Toadette 5 (docs/cpu-ai.md 2.4).
    # A plain countdown, it indexes nothing
    "windup charge frames": ("pitchwindup", 0, "f"),
}


def _check_table_stats(ts, who):
    unknown = set(ts) - set(TABLE_STATS)
    assert not unknown, f"{who}: unknown table_stats {sorted(unknown)} (see TABLE_STATS)"
    return dict(ts)


def _check_table_rows(tr, who):
    """"table_rows": {TABLES name: the whole row as hex} for the per-id tables other than selector / stats /
    hasmodel (the build derives those). Written over the template's row, before "table_stats"."""
    sizes = {name: size for name, _, size, _ in TABLES}
    out = {}
    for name, value in tr.items():
        assert name in sizes and name not in ("selector", "stats", "hasmodel"), \
            f"{who}: table_rows {name!r} is not a TABLES name other than selector / stats / hasmodel"
        row = bytes.fromhex(value)
        assert len(row) == sizes[name], f"{who}: table_rows {name} is {len(row)} B, its rows are {sizes[name]} B"
        out[name] = row
    return out


# what a value can be at all once written (the patcher's stat_room): the field's own size, except a float the game
# turns into a halfword: the windup countdown goes into the pitcher's s16 +0x102 (FUN_8015cd34, docs/cpu-ai.md), so
# past -32768..32767 it would wrap in the game
KIND_ROOM = {"B": (0, 0xFF), "h": (-0x8000, 0x7FFF), "f": (-3.4e38, 3.4e38)}
TABLE_ROOM = {"windup charge frames": (-0x8000, 0x7FFF)}


def table_room(stat):
    return TABLE_ROOM.get(stat) or KIND_ROOM[TABLE_STATS[stat][2]]


def stat_row_room(stat):
    return 0, (1 << 8 * STAT_FIELDS[stat][1]) - 1


def _put_stat(buf, stat, value):
    """A stats-row value, refused (never wrapped) past what its byte / u16 holds."""
    off, width = STAT_FIELDS[stat]
    lo, hi = stat_row_room(stat)
    if not lo <= int(value) <= hi:
        raise ValueError(f"{stat} {value} doesn't fit: it holds {lo} to {hi}")
    buf[off:off + width] = int(value).to_bytes(width, "big")


def _put_table_stat(buf, off, kind, value, stat=None):
    lo, hi = TABLE_ROOM.get(stat) or KIND_ROOM[kind]
    if not lo <= value <= hi:                       # (never wrapped: a byte, s16 or float past its room is refused)
        raise ValueError(f"{stat or 'table value'} {value} doesn't fit: it holds {lo:g} to {hi:g}")
    if kind == "B":
        buf[off] = int(value)
    elif kind == "h":
        struct.pack_into(">h", buf, off, int(value))
    else:
        struct.pack_into(">f", buf, off, float(value))


def extended_rows(dol, name, addr, size, header, chars, n_rows, on_square=(), templates=None):
    """templates: {stock id: row} a new character copies instead of that id's row as it is in `dol` (stock_rows: a
    stock entry's own options stay its own)."""
    rows = [bytearray(dol.read(addr + header + i * size, size)) for i in range(STOCK_IDS)]
    rows.append(bytearray(dol.read(addr + header + STOCK_IDS * size, size)))  # sentinel row: old bytes
    by_id = {c["id"]: c for c in chars}
    if name == "selector":
        # Byte 0 is the color-wheel group; 0 means "no wheel". A host (the template, or the
        # definition's "wheel") without a wheel gets a new group (the next unused number, as Extra
        # Innings did with 0x0E for Mario) so it and its new variants share one.
        next_group = max(r[0] for r in rows[:STOCK_IDS]) + 1
        for c in chars:
            t = rows[c["wheel"]]
            if t[0] == 0:
                t[0] = next_group
                next_group += 1
    for new_id in range(STOCK_IDS + 1, n_rows):
        c = by_id.get(new_id)
        row = bytearray((templates or {}).get(c["template"], rows[c["template"]])) if c else bytearray(size)
        if not c and name == "stats":                        # an id with no character: "not present" (0 elsewhere:
            row[0:2] = struct.pack(">H", new_id)              # no wheel, no model, not selectable), its own id and
            row[CHEM_BASE:CHEM_BASE + STOCK_IDS] = bytes([NEUTRAL]) * STOCK_IDS   # neutral chemistry
        if c and name == "selector":
            # "wheel": join that character's color wheel (group, main id, family: bytes 0-2, as Extra
            # Innings moved Rosalina onto Mario's); the template still supplies model, stats, etc.
            row[0:3] = rows[c["wheel"]][0:3]
            family = row[2]
            earlier = [x for x in chars if x["id"] < new_id and rows[x["wheel"]][2] == family
                       and x["id"] not in on_square]
            if new_id in on_square:
                row[5] = 0          # on a grid square: that square is its wheel, not the template's
            else:
                # variant slot: after the family's shown stock members (byte 6, icon valid: Extra Innings'
                # hidden Black Yoshi row 0x47 is family 0x06 slot 6 but never on the wheel)
                row[5] = 1 + max([r[5] for r in rows[:STOCK_IDS] if r[2] == family and r[6]] or [-1]) + len(earlier)
                import wheel7
                assert row[5] < wheel7.MEMBERS, \
                    f"0x{new_id:02X}: color wheel for family 0x{family:02X} would exceed {wheel7.MEMBERS} entries (wheel7.py)"
            row[3] = 0  # a variant, never a second captain
            if c["color"]:
                row[7] = SWATCHES[c["color"]]
        if c and name in c["table_rows"]:                    # the definition's whole row (table_rows)
            row[:] = c["table_rows"][name]
        if c and name == "sizescale" and c["scale"] != 1:
            # the actor's model scale (FUN_80367080 -> FUN_80382558): skeleton and mesh together
            row[:] = struct.pack(">2f", *(v * c["scale"] for v in struct.unpack(">2f", row)))
        if c:
            for stat, value in c["table_stats"].items():
                table, off, kind = TABLE_STATS[stat]
                if table == name:
                    _put_table_stat(row, off, kind, value, stat)
        if c and name == "stats":
            row[0:2] = struct.pack(">H", new_id)
            for stat, value in c["stats"].items():
                _put_stat(row, stat, value)
            # the template's chemistry is its character's relationships, not the new one's: start neutral, or
            # from the base's row for "chemistry_like" (its stock row as this build has it, or an earlier new one's)
            like = c.get("chemistry_like")
            if like is not None and like < len(rows) and like != STOCK_IDS:
                row[CHEM_BASE:CHEM_BASE + STOCK_IDS] = rows[like][CHEM_BASE:CHEM_BASE + STOCK_IDS]
            else:
                row[CHEM_BASE:CHEM_BASE + STOCK_IDS] = bytes([NEUTRAL]) * STOCK_IDS
            for other, value in c["chemistry"].items():
                if other < STOCK_IDS:
                    row[CHEM_BASE + other] = value
        rows.append(row)
    head = bytearray(dol.read(addr, header))
    if name == "stats":
        head[0] = min(n_rows, 0xFF)     # (the stock row count 0x65; nothing in the game reads it, and 256 won't fit)
    return bytes(head) + b"".join(rows)


def new_chemistry(chars, row_chem=None):
    """(first new id, n, n*n bytes): chemistry between two new characters, NEUTRAL unless a definition names
    the other new character; set both ways (a later definition's value wins for a pair both define).
    "chemistry_like" (a recolor has its base's chemistry): a pair neither definition sets, with a "like" on either
    side, takes its bases' pair: two stock bases -> row_chem(a, b) (a's stats row, column b, as built); a stock and a
    new one -> the new one's row, column the stock one; two new ones -> their pair here."""
    first = STOCK_IDS + 1
    n = ID_BOUND - first + 1                                # every new id (0x66-0xFF): 154 x 154, whatever the build uses
    table = bytearray([NEUTRAL]) * (n * n)
    explicit = set()
    for c in chars:
        for other, value in c["chemistry"].items():
            if other > STOCK_IDS:
                table[(c["id"] - first) * n + other - first] = value
                table[(other - first) * n + c["id"] - first] = value
                explicit |= {(c["id"], other), (other, c["id"])}
    like = {c["id"]: c["chemistry_like"] for c in chars if c.get("chemistry_like") is not None}
    if not like or row_chem is None:
        return first, n, bytes(table)
    ids = {c["id"] for c in chars}

    def pair(a, b, depth=0):
        if (a, b) in explicit:
            return table[(a - first) * n + b - first]
        la, lb = like.get(a, a), like.get(b, b)
        if (la, lb) == (a, b) or depth > 8:
            return table[(a - first) * n + b - first] if a > STOCK_IDS and b > STOCK_IDS else NEUTRAL
        if la < STOCK_IDS and lb < STOCK_IDS:
            return row_chem(la, lb)
        if la < STOCK_IDS or lb < STOCK_IDS:                  # a stock one and a new one: the new one's row
            s, x = (la, lb) if la < STOCK_IDS else (lb, la)
            return row_chem(x, s) if x in ids else NEUTRAL
        return pair(la, lb, depth + 1) if la in ids and lb in ids else NEUTRAL
    for a in sorted(ids):
        for b in sorted(ids):
            if a != b and (a in like or b in like) and (a, b) not in explicit:
                table[(a - first) * n + b - first] = pair(a, b)
    return first, n, bytes(table)


# the tables this build moved, {old address: (old length, new address, name, row size)} (relocate; a later move of the
# same table wins), for the Gecko map (gecko_map): a player's code writing the old copy is pointed at the one the game
# reads
MOVES = {}
LAST_GECKO_MAP = None               # the last build's gecko_map (patch.py writes it beside the ISO)


def relocate(dol, pairs, old, old_len, new, name=None, row=None):
    """Rewrite every lis/low-half pair addressing [old, old+old_len) to the same offset from new. name / row: what the
    Gecko map calls the table and its row size (gecko_map)."""
    MOVES[old] = (old_len, new, name, row)
    sel = [p for p in pairs if old <= p[3] < old + old_len]
    lises = {}
    for lis_addr, use_addr, reg, ea, kind, ins in sel:
        new_ea = new + (ea - old)
        w = dol.u32(use_addr)
        if kind == "ori":
            dol.w32(use_addr, (w & 0xFFFF0000) | (new_ea & 0xFFFF))
            hi = new_ea >> 16
        else:
            dol.w32(use_addr, (w & 0xFFFF0000) | lo(new_ea))
            hi = ha(new_ea)
        assert lises.setdefault(lis_addr, hi) == hi, f"lis {lis_addr:#x} needs two high halves"
    for lis_addr, hi in lises.items():
        dol.w32(lis_addr, (dol.u32(lis_addr) & 0xFFFF0000) | hi)
    return len(sel)


def gecko_map(dol, clean, features, arena_lo):
    """What a player's Gecko codes need to know about this build (gecko_fix.py; patch.py writes it beside the ISO as
    relocations.json in "<name> (patch details)"): addresses depend on what's ticked, so every build has its own.
      "tables": [{"old", "length", "new", "name", "row", ("header", "per_character")}]: the tables we moved (MOVES):
                a code writing the old copy is pointed at the new one, same offset (same row; the new tables keep the
                stock rows where they were and add rows after).
      "changed": [{"start", "end", "kind" code/data, "who", "feature"}]: the stock DOL words we changed (outside the
                moved tables), coalesced by who wrote them (Dol.trace: the module, or charbuild's function) and the
                feature that step belongs to (charbuild's own lines: the on("...") guarding them; a module: the
                FEATURES steps naming it; else new-ids).
      "features": the build's features; "arena_lo": [stock, ours].
      "heap_shift": how far the game's run-time memory (MEM1 past the stock arena, 0x807B4E80..) moved: the heaps are
                made from arena low up, and the lowest of the three arena-low sites (0x80596014, stock 0x807B4E80) is
                the one they start from: the match settings (*(r13-0xB00), stock 0x811F7698) sat at +0x66180 in three
                RAM dumps of a build with arena low 0x8081B000 (analysis/ramdump-cpuvcpu*), = 0x8081B000 - 0x807B4E80.
                0 when arena low stays stock. Objects made after the build's own extra loads may sit further up."""
    ids = sorted(FEATURES) if features is None else sorted(features)
    mentions = {f: set(re.findall(r"[A-Za-z_][A-Za-z_0-9]*", " ".join(FEATURES[f].get("steps", []))))
                for f in ids if f in FEATURES}
    try:
        source = Path(__file__).read_text(encoding="utf8").splitlines()
    except OSError:                                                 # (a download without the source: by module)
        source = []

    def guard(line):
        """The feature of the innermost on("...") guarding charbuild's line (1-based): on its own line or a block
        header above it (a line indented less), or None."""
        indent = None
        for k in range(line, 0, -1):
            text = source[k - 1] if k - 1 < len(source) else ""
            if not text.strip() or text.lstrip().startswith("#"):
                continue
            depth = len(text) - len(text.lstrip())
            if indent is None or depth < indent:
                hit = re.search(r"""\bon\(["']([\w-]+)["']\)""", text)
                if hit and hit.group(1) in ids:                        # (one not in this build: further up)
                    return hit.group(1)
                if text.lstrip().startswith("def "):
                    return None
                indent = depth

    def feature(who):                                               # (new-ids last: its steps name many modules)
        name, _, line = who.split(".")[-1].partition(":")
        hit = guard(int(line)) if line else None
        hit = hit or next((f for f in sorted(ids, key=lambda f: f == "new-ids") if name in mentions.get(f, ())), None)
        return hit or ("new-ids" if "new-ids" in ids else None)
    moved = [(old, old + m[0]) for old, m in MOVES.items()]
    trace = dol.trace or {}
    changed = []
    for slot in range(18):
        start, size = clean.addrs[slot], clean.sizes[slot]
        if not size:
            continue
        kind = "code" if slot < 7 else "data"
        before = clean.read(start, size)
        try:
            after = dol.read(start, size)
        except KeyError:                                            # (a section we took out: every word changed)
            after = b""
        for off in range(0, size, 0x400):                           # blocks first: most of the DOL is as it was
            if before[off:off + 0x400] == after[off:off + 0x400]:
                continue
            for w in range(off, min(off + 0x400, size), 4):
                if before[w:w + 4] == after[w:w + 4]:
                    continue
                a = start + w
                if any(lo_ <= a < hi_ for lo_, hi_ in moved):
                    continue
                who = trace.get(a, "the patcher")
                last = changed[-1] if changed else None
                if last and last["end"] == a and last["who"] == who and last["kind"] == kind:
                    last["end"] = a + 4
                else:
                    changed.append({"start": a, "end": a + 4, "kind": kind, "who": who, "feature": feature(who)})
    per_id = {name: header for name, _, _, header in TABLES}        # rows by character id (after a header)
    site = ARENA_LO_SITES[2]                                        # (0x807B4E80 in the stock game)

    def site_value(d):
        return ((d.u32(site[0]) & 0xFFFF) << 16) + ((d.u32(site[1]) & 0xFFFF) ^ 0x8000) - 0x8000
    return {"game": "RMBE01", "features": ids, "arena_lo": [ARENA_LO, arena_lo],
            "heap_start": site_value(clean), "heap_shift": site_value(dol) - site_value(clean),
            "tables": [{"old": old, "length": n, "new": new, "name": name, "row": row,
                        **({"header": per_id[name], "per_character": True} if name in per_id else {})}
                       for old, (n, new, name, row) in sorted(MOVES.items())],
            "changed": changed}


# Icon bank = dt_na.dat dir 119 file 2 (Extra Innings relocated it to the end of the file). Its
# side/front source tables map character id -> icon resource row; the game searches them by id.
# Layout from Jaws-git/Sluggies-dat-tools (SluggiesTools/Icons/update_icon_source_tables.py).
ICON_RECORD = 0x80691D88          # main.dol dt_na index record for dir 119 file 2 (3 languages)
ICON_DESCRIPTOR = 0x113C94        # bank offset; +0x0C side, +0x10 front: signed offsets from here
SRC_HEADER, SRC_RECORD, SRC_FIRST_FLAG = 0x28, 0x50, 0x0100
ICON_PRIVATE_IMAGES = 0x93880    # first private CMPR page (Sluggies SIDE_IMAGE_OFFSET)
ICON_PAGES = {"side": 0x92, "front": 0x93}   # Extra Innings' private CMPR pages (1024x256)
ICON_SLOT, ICON_SLOT_H, ICON_ART = 64, 56, (48, 51)
# Page descriptor image (and palette) offsets count from bank +0x20, not the bank start (the same as
# the layout files, scripts/layout.py 6f6011c). Reading them as absolute put every page 32 bytes early,
# which the art placement hid by drawing 8 px into each slot; now art starts at the slot, as EI's does.
TEX_BASE = 0x20
RES_ROW = 0x14
MODEL_DIR_BASE = 0x12            # a model id's files are dt_na.dat directory id + 0x12
MODEL_HANDLES, MODEL_HANDLE_SIZE = 0x80709408, 0xC   # per-model-id runtime array (101 x {1, 2, 4})
# the rows the stock init code (0x80155624) writes differently from {1, 2, 4} (request bits: bat, glove L, glove R;
# docs/dive-catch.md): Monty Mole's gloves and Petey's whole row are left at 0, the Magikoopas' are 1
# (test_model_requests.py reads the init code's stores from the clean main.dol)
MODEL_REQUESTS = {0x12: (1, 0, 0), 0x21: (1, 1, 1), 0x22: (1, 1, 1), 0x23: (1, 1, 1), 0x24: (1, 1, 1), 0x26: (0, 0, 0)}
MODEL_DIR_SITES = ((0x8036625C, 26), (0x803664E8, 4), (0x80376480, 25),   # addi r4,rN,0x12
                   (0x804A519C, 28), (0x804A5224, 28))   # captain-select model (FUN_804a5018): anim 11, model


def _source_table(bank, off):
    length = struct.unpack_from(">I", bank, off + 0x08)[0]
    count, stride = struct.unpack_from(">HH", bank, off + 0x24)
    assert stride == SRC_RECORD and length == SRC_HEADER + count * stride, f"bad source table at 0x{off:X}"
    return bank[off:off + length], count


def _extend_source_table(table, count, chars, overrides=None):
    """A source table is a step-keyed animation track: frame = character id, key value = icon
    resource id. Keys are stored in descending id order (the first carries marker 0x0014, the rest
    0x0114) and may be sparse (stock tables skip ids). Header +0x18 is the track's last frame; the
    game cannot reach a key past it, so it must cover the highest new id. New ids copy their
    template's key (same portrait resource)."""
    records = [bytearray(table[SRC_HEADER + i * SRC_RECORD:SRC_HEADER + (i + 1) * SRC_RECORD]) for i in range(count)]
    by_id = {struct.unpack_from(">H", r, 2)[0]: r for r in records}
    for c in chars:
        if c["id"] in by_id:
            continue
        # the key in force at the template's frame (tables skip ids; a step key holds until the next)
        rec = bytearray(by_id[max(k for k in by_id if k <= c["template"])])
        struct.pack_into(">H", rec, 2, c["id"])
        records.append(rec)
        by_id[c["id"]] = rec
    # overrides {id: resource row}: that id's key shows this row; a step key holds up to the next key,
    # so the following id gets a key restoring what was in force there (unless it has its own)
    for cid, row in sorted((overrides or {}).items()):
        nxt = cid + 1
        if nxt not in by_id and any(k < nxt for k in by_id):
            rec = bytearray(by_id[max(k for k in by_id if k < nxt)])
            struct.pack_into(">H", rec, 2, nxt)
            records.append(rec)
            by_id[nxt] = rec
        if cid not in by_id:
            rec = bytearray(by_id[max(k for k in by_id if k < cid)])
            struct.pack_into(">H", rec, 2, cid)
            records.append(rec)
            by_id[cid] = rec
        struct.pack_into(">H", by_id[cid], 6, row)
    records.sort(key=lambda r: struct.unpack_from(">H", r, 2)[0], reverse=True)
    for i, r in enumerate(records):             # every record but the first carries the flag
        flags = struct.unpack_from(">H", r, 0)[0]
        struct.pack_into(">H", r, 0, flags & ~SRC_FIRST_FLAG if i == 0 else flags | SRC_FIRST_FLAG)
    out = bytearray(table[:SRC_HEADER]) + b"".join(records)
    struct.pack_into(">I", out, 0x08, len(out))
    last = struct.unpack_from(">H", out, 0x18)[0]
    struct.pack_into(">H", out, 0x18, max(last, max(c["id"] for c in chars)))
    struct.pack_into(">H", out, 0x24, len(records))
    return bytes(out)


def extend_icon_bank(dol, dat_path, chars):
    """Add keys for the new ids to the icon bank's three source tables (normal_a, side, front), in
    place. They sit back to back (descriptor +0x08, +0x0C, +0x10), followed by free space up to the
    private icon images: rebuild the run and repoint the descriptor fields.
    (Appending the tables past the icon block crashed the loader, FUN_805c4b34.)"""
    w = struct.unpack(">12I", dol.read(ICON_RECORD, 48))
    off, length = w[2], w[1]
    assert all(w[i] == length and w[i + 1] == off for i in (1, 5, 9)), "icon record languages disagree"
    with open(dat_path, "r+b") as f:
        f.seek(off)
        bank = bytearray(f.read(length))
        ptr = lambda field: ICON_DESCRIPTOR + struct.unpack_from(">i", bank, ICON_DESCRIPTOR + field)[0]
        fields = (0x08, 0x0C, 0x10)
        # every portrait we draw also becomes its normal_a view (0x08), which otherwise keeps the
        # template's or the stock character's: add_icon_art appends side rows, then front rows, in
        # `art` order after the existing rows, so the front row of art[i] is known in advance
        on_private, moved = stock_icon_split(bank, ptr)
        art = [c for c in chars if c["icon"]] + [
            {"id": cid, "icon": {v: ROOT / f"models/work/icons/new/{n}_{v}.png" for v in ICON_PAGES}}
            for cid, n in moved.items()]
        rows0 = struct.unpack_from(">I", bank, ptr(0x04))[0]
        normal = {c["id"]: rows0 + len(art) + i for i, c in enumerate(art)}
        start = pos = ptr(fields[0])
        run = b""
        for field in fields:
            assert ptr(field) == pos, "expected the source tables back to back"
            table, n = _source_table(bank, pos)
            pos += len(table)
            struct.pack_into(">i", bank, ICON_DESCRIPTOR + field, start + len(run) - ICON_DESCRIPTOR)
            run += _extend_source_table(table, n, chars, normal if field == 0x08 else None)
        end = start + len(run)
        assert not any(bank[pos:end]), "no free space after the source tables"
        assert end <= ICON_PRIVATE_IMAGES, "source tables would overlap the private icon images"
        bank[start:end] = run
        # (not restore_ei_damage: the "stray strip" in the shared atlases is EI's source tables, which live
        # in the atlas image's unused bottom rows; restoring it zeroed keys, e.g. Bowser's side portrait)
        # stock portraits: on the private pages, redrawn in place; elsewhere (the shared CI8 atlases),
        # moved to new private-page slots like a new character's (`art`, above)
        if on_private:
            bank = stock_icon_art(bank, ptr, on_private)
        if art:
            bank = add_icon_art(bank, art, ptr)
            assert all(c["icon_rows"]["front"] == normal[c["id"]] for c in art), "normal_a rows mispredicted"
        if LOSSLESS_ICONS:
            before = len(bank)
            bank = lossless_icon_pages(bank, art, ptr)
            sizes = ["x".join(str(v) for v in struct.unpack_from(">HH", bank, 0x24 + p * 0x20 + 8)[::-1])
                     for p in ICON_PAGES.values()]
            print(f"icon pages   0x92/0x93 -> RGB5A3 {' / '.join(sizes)}, inserted at the end of the texture section "
                  f"(+0x{len(bank) - before:x} B, bank 0x{len(bank):x} B)")
        if LOSSLESS_ICONS:                          # last edit to the bank: after it the container is no longer at
            import icon_bank                        # ICON_DESCRIPTOR (git-a3; Nick's crash at 0x80597944: the heap)
            before = len(bank)
            bank = icon_bank.shrink(bank)
            print(f"icon bank    shrunk 0x{before:x} -> 0x{len(bank):x} B (packed private pages, Extra Innings' old "
                  f"CMPR area dropped)")
            if CI8_ICONS:                           # after shrink(), and the last edit to the bank (git-a3)
                bank, rep = icon_bank.ci8_pages(bank, exact_only=CI8_ICONS == "exact")
                print(f"icon bank    CI8 pages: {rep['portraits']} portraits "
                      f"({'exact only' if CI8_ICONS == 'exact' else 'all'}), bank 0x{len(bank):x} B")
        if art or LOSSLESS_ICONS:
            f.seek(off + length)
            assert not any(f.read(max(0, len(bank) - length))), "data after the icon bank"   # (shrunk: shorter)
            for lang in range(3):                   # index record: {name, len, off, len} per language
                dol.w32(ICON_RECORD + 4 + 16 * lang, len(bank))
                dol.w32(ICON_RECORD + 12 + 16 * lang, len(bank))
        f.seek(off)
        f.write(bank)
    if STOCK_ICONS:
        print("stock icons  " + ", ".join(f"0x{k:02X} {v}" for k, v in STOCK_ICONS.items())
              + " (on the private pages: redrawn in place; on the shared atlases: moved to new private slots)")
    return off, len(bank), end - start


def clean_icon_bank():
    clean = Dol(game_source.root() / "sys/main.dol")
    off, length = dtna_toc.toc(clean)[119][2]
    with open(game_source.root() / "files/dt_na.dat", "rb") as f:
        f.seek(off)
        return f.read(length)


def restore_ei_damage(bank):
    """Copy back from the clean game's icon bank the stock atlas tiles Extra Innings overwrote
    (DAMAGED_TILES; TEX_BASE-relative offsets, the same in both banks)."""
    cbank = clean_icon_bank()
    bank = bytearray(bank)
    for atlas, cols, (y0, y1) in DAMAGED_TILES:                  # CI8 tiles: 8 x 4 px, 32 B, 128 per row
        for tx in cols:
            for ty in range(y0, y1, 4):
                at = TEX_BASE + atlas + ((ty // 4) * 128 + tx // 8) * 32
                bank[at:at + 32] = cbank[at:at + 32]
    return bank


def stock_icon_split(bank, ptr):
    """STOCK_ICONS -> ({id: name} whose side and front rows are on the private pages, {id: name} not)."""
    res = ptr(0x04)
    count = struct.unpack_from(">I", bank, res)[0]
    pages = [struct.unpack_from(">H", bank, res + 8 + i * RES_ROW)[0] for i in range(count)]
    private, moved = {}, {}
    for cid, name in STOCK_ICONS.items():
        ok = True
        for view, field in (("side", 0x0C), ("front", 0x10)):
            table = ptr(field)
            n = struct.unpack_from(">H", bank, table + 0x24)[0]
            for i in range(n):
                rec = table + SRC_HEADER + i * SRC_RECORD
                if struct.unpack_from(">H", bank, rec + 2)[0] == cid:
                    ok &= pages[struct.unpack_from(">H", bank, rec + 6)[0]] == ICON_PAGES[view]
        (private if ok else moved)[cid] = name
    return private, moved


def stock_icon_art(bank, ptr, stock_icons=None):
    """Redraw stock characters' side / front portraits in place (STOCK_ICONS)."""
    stock_icons = STOCK_ICONS if stock_icons is None else stock_icons
    bank = bytearray(bank)
    res = ptr(0x04)
    count = struct.unpack_from(">I", bank, res)[0]
    rows = [struct.unpack_from(">HH4f", bank, res + 8 + i * RES_ROW) for i in range(count)]
    for view, field in (("side", 0x0C), ("front", 0x10)):
        table = ptr(field)
        n = struct.unpack_from(">H", bank, table + 0x24)[0]
        row_of, users = {}, {}
        for i in range(n):
            rec = table + SRC_HEADER + i * SRC_RECORD
            cid, row = struct.unpack_from(">H", bank, rec + 2)[0], struct.unpack_from(">H", bank, rec + 6)[0]
            row_of[cid] = row
            users.setdefault(row, set()).add(cid)
        for cid, name in stock_icons.items():
            row = row_of[cid]
            # shared only with new ids built on it (e.g. the Luma recolors without their own art): they
            # show the new portrait too; sharing with another stock character would be a mistake
            assert all(u == cid or u > STOCK_IDS for u in users[row]),                 f"0x{cid:02X} {view}: resource row {row} is shared with {sorted(users[row])}"
            page, _, v0, u0, _, _ = rows[row]
            assert page == ICON_PAGES[view], f"0x{cid:02X} {view}: not on the private page"
            desc = 0x24 + page * 0x20
            img_off = TEX_BASE + struct.unpack_from(">I", bank, desc)[0]
            h, w = struct.unpack_from(">HH", bank, desc + 8)
            assert bank[desc + 0x17] == 0x0E, "private icon page is not CMPR"
            x, y = round(u0 * w), round(v0 * h)
            assert x % ICON_SLOT == 0 and y % ICON_SLOT == 0, f"0x{cid:02X} {view}: slot not 64-aligned"
            art = Image.open(ROOT / f"models/work/icons/new/{name}_{view}.png").convert("RGBA")
            assert art.size == ICON_ART, f"{name}_{view}.png must be {ICON_ART[0]}x{ICON_ART[1]}"
            canvas = Image.new("RGBA", (ICON_SLOT, ICON_SLOT_H))
            canvas.paste(art, (0, 0))
            page_data = bytearray(bank[img_off:img_off + w * h // 2])
            cmpr.encode_region(page_data, w, canvas, x, y)
            bank[img_off:img_off + len(page_data)] = page_data
    return bank


def lossless_icon_pages(bank, chars, ptr, stock_icons=None):
    """Re-store Extra Innings' private icon pages (side 0x92, front 0x93) as RGB5A3 (16 bpp, visually
    lossless) instead of CMPR, whose 4x4 blocks turn 48-px faces blotchy (Nick: "still pretty bad").
    The existing art is decoded from the CMPR page; every portrait we draw (new ids, STOCK_ICONS) is
    pasted again from its PNG at its slot, so ours skip CMPR entirely. The page keeps its 64-px slot
    grid, cropped (or grown, up to ICON_PAGE_MAX_H) to the rows in use (1024 x 128 when every slot is in the
    first two rows; the resource rows' v coordinates are rescaled). The bigger image can't fit in place, so it is appended
    to the bank (32-byte aligned) and the page descriptor (+0 image offset, +8 height, +0x17 format)
    repointed."""
    stock_icons = STOCK_ICONS if stock_icons is None else stock_icons
    bank = bytearray(bank)
    res = ptr(0x04)
    count = struct.unpack_from(">I", bank, res)[0]
    rows = [list(struct.unpack_from(">HH4f", bank, res + 8 + i * RES_ROW)) for i in range(count)]
    sources = {}
    for view, field in (("side", 0x0C), ("front", 0x10)):
        table = ptr(field)
        n = struct.unpack_from(">H", bank, table + 0x24)[0]
        for i in range(n):
            rec = table + SRC_HEADER + i * SRC_RECORD
            sources[(view, struct.unpack_from(">H", bank, rec + 2)[0])] = struct.unpack_from(">H", bank, rec + 6)[0]
    pages = []                                           # (descriptor, new height, RGB5A3 bytes)
    arts = {}                                            # (view, row) -> PNG path
    for c in chars:
        for view in ICON_PAGES:
            arts[(view, c["icon_rows"][view])] = c["icon"][view]
    for cid, name in stock_icons.items():
        for view in ICON_PAGES:
            arts[(view, sources[(view, cid)])] = ROOT / f"models/work/icons/new/{name}_{view}.png"
    for view, page in ICON_PAGES.items():
        desc = 0x24 + page * 0x20
        img_off = TEX_BASE + struct.unpack_from(">I", bank, desc)[0]
        h, w = struct.unpack_from(">HH", bank, desc + 8)
        assert bank[desc + 0x17] == 0x0E, "private icon page is not CMPR"
        image = Image.new("RGBA", (w, ICON_PAGE_MAX_H))
        image.paste(cmpr.decode(bytes(bank[img_off:img_off + w * h // 2]), w, h), (0, 0))
        for (v, row), path in arts.items():
            if v != view:
                continue
            x, y = round(rows[row][3] * w), round(rows[row][2] * h)
            art = Image.open(path).convert("RGBA")
            assert art.size == ICON_ART, f"{path} must be {ICON_ART[0]}x{ICON_ART[1]}"
            canvas = Image.new("RGBA", (ICON_SLOT, ICON_SLOT_H))
            canvas.paste(art, (0, 0))
            image.paste(canvas, (x, y))
        used = max(round(r[4] * h) for r in rows if r[0] == page)
        new_h = -(-used // ICON_SLOT) * ICON_SLOT             # may be taller than the CMPR page (add_icon_art)
        assert new_h <= ICON_PAGE_MAX_H, f"icon page 0x{page:02X} would be {new_h} px tall"
        for r in rows:
            if r[0] == page:
                r[2], r[4] = r[2] * h / new_h, r[4] * h / new_h
        import captain_art
        pages.append((desc, new_h, captain_art.rgb5a3(image.crop((0, 0, w, new_h)))))
    for i, r in enumerate(rows):
        struct.pack_into(">HH4f", bank, res + 8 + i * RES_ROW, *r)
    # The page images must be inside the bank's texture section [header +0, header +4): the game
    # treats only that span as texture data (chars-80 appended them after the container and every
    # new portrait showed garbage). Insert them at its end, just before the container, and raise
    # header +4. The container moves back by the inserted size: its own references are relative to
    # it, except the descriptor's pointers back into the texture section (the source tables at
    # descriptor +8 / +0xC / +0x10, negative), which grow more negative by the same amount.
    tex_end = struct.unpack_from(">I", bank, 4)[0]
    container = ICON_DESCRIPTOR - 0x14
    assert tex_end == container and tex_end % 32 == 0, "expected the container right after the textures"
    insert = bytearray()
    cbank = clean_icon_bank()
    for page in OVERLAPPED_PALETTES:                     # clean palettes EI's descriptors sit on
        desc = 0x24 + page * 0x20
        assert bank[desc:desc + 0x20] == cbank[desc:desc + 0x20], f"page 0x{page:02X} descriptor differs"
        pal = TEX_BASE + struct.unpack_from(">I", cbank, desc + 4)[0]
        struct.pack_into(">I", bank, desc + 4, tex_end + len(insert) - TEX_BASE)
        insert += cbank[pal:pal + 512]
    for desc, new_h, blob in pages:
        struct.pack_into(">I", bank, desc, tex_end + len(insert) - TEX_BASE)
        struct.pack_into(">H", bank, desc + 8, new_h)
        bank[desc + 0x17] = 0x05
        insert += blob + bytes(-len(blob) % 32)
    for field in (0x08, 0x0C, 0x10):
        rel = struct.unpack_from(">i", bank, ICON_DESCRIPTOR + field)[0]
        assert ICON_DESCRIPTOR + rel < tex_end, "descriptor field does not point into the textures"
        struct.pack_into(">i", bank, ICON_DESCRIPTOR + field, rel - len(insert))
    struct.pack_into(">I", bank, 4, tex_end + len(insert))
    return bank[:tex_end] + insert + bank[tex_end:]


def add_icon_art(bank, chars, ptr):
    """Give each char its own side/front portrait: encode its art into the next free 64-px slot
    of Extra Innings' private CMPR pages (side 0x92, front 0x93; art at the slot start, like the
    existing ones), append a resource row per view (page + UV rect) and point the char's side and
    front track keys at them. The resource table is the last thing in the bank, so the bank grows
    (into the zero padding that follows it in dt_na.dat)."""
    bank = bytearray(bank)
    res = ptr(0x04)
    count, length = struct.unpack_from(">II", bank, res)
    assert length == 8 + count * RES_ROW, "unexpected resource table header"
    assert res + length <= len(bank) and not any(bank[res + length:]), "data after the resource table"
    rows = [struct.unpack_from(">HH4f", bank, res + 8 + i * RES_ROW) for i in range(count)]
    new_rows = []
    for view, page in ICON_PAGES.items():
        desc = 0x24 + page * 0x20
        img_off = TEX_BASE + struct.unpack_from(">I", bank, desc)[0]
        h, w = struct.unpack_from(">HH", bank, desc + 8)
        assert bank[desc + 0x17] == 0x0E, "private icon page is not CMPR"
        page_data = bytearray(bank[img_off:img_off + w * h // 2])
        used = {(round(r[3] * w) // ICON_SLOT, round(r[2] * h) // ICON_SLOT) for r in rows if r[0] == page}
        decoded = cmpr.decode(bytes(page_data), w, h)
        free = []                                   # 64x64 slots, row by row, unreferenced and blank
        for sy in range(h // ICON_SLOT):
            for sx in range(w // ICON_SLOT):
                box = (sx * ICON_SLOT, sy * ICON_SLOT, (sx + 1) * ICON_SLOT, sy * ICON_SLOT + ICON_SLOT_H)
                if (sx, sy) not in used and not any(decoded.crop(box).getchannel("A").getdata()):
                    free.append((sx * ICON_SLOT, sy * ICON_SLOT))
        if LOSSLESS_ICONS:                          # slots below the page: lossless_icon_pages makes it taller
            free += [(sx * ICON_SLOT, sy * ICON_SLOT) for sy in range(h // ICON_SLOT, ICON_PAGE_MAX_H // ICON_SLOT)
                     for sx in range(w // ICON_SLOT)]
        for c in chars:
            assert free, "private icon page is full"
            x, y = free.pop(0)
            art = Image.open(c["icon"][view]).convert("RGBA")
            assert art.size == ICON_ART, f"{c['icon'][view]} must be {ICON_ART[0]}x{ICON_ART[1]}"
            canvas = Image.new("RGBA", (ICON_SLOT, ICON_SLOT_H))
            canvas.paste(art, (0, 0))
            if y < h:                               # (below the page: pasted by lossless_icon_pages only)
                cmpr.encode_region(page_data, w, canvas, x, y)
            c.setdefault("icon_rows", {})[view] = count + len(new_rows)
            new_rows.append((page, 0, y / h, x / w, (y + ICON_ART[1]) / h, (x + ICON_ART[0]) / w))
        bank[img_off:img_off + len(page_data)] = page_data
    for view, field in (("side", 0x0C), ("front", 0x10)):
        table = ptr(field)
        n = struct.unpack_from(">H", bank, table + 0x24)[0]
        for i in range(n):
            rec = table + SRC_HEADER + i * SRC_RECORD
            cid = struct.unpack_from(">H", bank, rec + 2)[0]
            for c in chars:
                if c["id"] == cid:
                    struct.pack_into(">H", bank, rec + 6, c["icon_rows"][view])
    grow = len(new_rows) * RES_ROW
    bank[res + length:res + length] = b"".join(struct.pack(">HH4f", *r) for r in new_rows)
    struct.pack_into(">II", bank, res, count + len(new_rows), length + grow)
    container = ICON_DESCRIPTOR - 0x14                  # +0x10: end of its last subsection
    end = struct.unpack_from(">I", bank, container + 0x10)[0] + grow
    struct.pack_into(">I", bank, container + 0x10, end)
    assert container + end == res + length + grow, "container endpoint does not match the resource table"
    return bank


# Select-screen portrait sites (see build step 5a).
PORTRAIT_NORMAL_TESTS = (0x8006E640, 0x8007F4DC, 0x8042BBB4, 0x8006463C, 0x80088F5C,
                         0x8031DBFC)   # + the in-match defense screen's name (Nick: new characters showed "Mii")
# Team lists that keep only stock (0..0x4C) and Mii ids and leave a new id as "no character" (-1): the
# `bge cr1,+0x1C` after `cmpwi cr1,rN,0x4d` (step 5a''). (site, id register)
ID_LIST_TESTS = ((0x80320468, 3),)    # FUN_80320418: the in-match substitution screen's team (Nick: blank faces)


def id_list_stub(site, reg, base):
    """ID_LIST_TESTS: `bge cr1,+0x1C` replaced; cr1 = cmpwi rN,0x4d. Stock and new ids -> site + 4 (kept),
    Mii ids and the 0x65 sentinel -> site + 0x1C (the Mii path)."""
    a = Asm(base)
    a.blt("normal", cr=1)
    a.cmpwi(f"r{reg}", STOCK_IDS, cr=1).ble("other", cr=1)
    a.label("normal")
    a.b(site + 4)
    a.label("other")
    a.b(site + 0x1C)
    return a.assemble()
PORTRAIT_RESOURCE_ADDS = ((0x8006E660, 0x38040149), (0x8007F4FC, 0x38040149), (0x8042BBD8, 0x38640149),
                          (0x8031DC1C, 0x38040149))   # Gm2d_Bb FukidasiStatusName (FUN_8031db3c)
# The 7 new grid squares (gridcells: column 0 rows 0-3, column 11 rows 0-2; Luigi is column 11 row 3),
# each a wheel of 1-6 characters, the first one shown. Nick: every new character is on a square
# (Koopalings half and half, Pom Pom and Boom Boom sharing). Names not in this build are left out (logged).
# Luigi's special catch (seq 39) plays this file-6 sequence: 0 = the fielding stance most fielding
# records use (Nick: stand with the Poltergust so it can be seen; None = his dive, seq 19).
POLTERGUST_CATCH_SEQ = 0
# Nick's Poltergust test: Luigi's plain / super dive (record 0x82, seq 19) also plays that stance, and
# record 0x82's prop mask gets part bit 3 so the Poltergust shows (only Luigi loads a file 5 prop).
POLTERGUST_STAND_DIVE = True
DIVE_ANIM = 0x82
# The Poltergust (file 5, rigid) attaches to this body node instead of the right-hand locator (nodes
# 3 / 2 in FUN_8036629c's file-5 call: `li r8,3` / `li r9,2` at 0x8036640C / 0x80366410). Node = index
# in the skeleton's depth-first joint order (Luigi: 2 / 3 are the hand locators, 10 is his waist bone_6
# at y 0.913, whose frame is the model's: Y up, facing +Z). Nick: hold it centred, not on one side.
POLTERGUST_NODE = 10
# The 19 new grid squares (gridcells 12x5; Nick: every character its own square, alternates on its
# wheel), in gridcells.NEW_SQUARE_CELLS order: column 0 top to bottom (the Galaxy characters), column 11
# rows 0-3, then row 4 left to right (the Koopalings in their SMB3 order, then Pom Pom, Boom Boom and
# King Bob-omb). Luigi is column 11 row 4. Each square is a wheel whose first character is shown.
GRID_SQUARES = [["Rosalina"], ["Luma", "Blue Luma", "Green Luma", "Red Luma"], ["Lubba"], ["Honey Queen"],
                ["Penguru"],
                ["Gearmo", "Gold Gearmo"], ["Chimp"], ["Bouldergeist"], ["Pauline"],
                ["Larry"], ["Morton"], ["Wendy"], ["Iggy"], ["Roy"], ["Lemmy"], ["Ludwig"],
                ["Pom Pom"], ["Boom Boom"], ["King Bob-omb"]]
# Where every square goes (Nick, 2026-09-25: "the captains should all be on the top row ... make logical sense").
# 14 captains, 12 columns: row 0 is 12 of them (heroes left, villains right), the other two (King Boo, King
# Bob-omb) end row 1, under Bowser and Bowser Jr. Then the Mario family and Kongs, the Toads, Pauline and the
# Galaxy crew, Bowser's family and crew, and the other enemies. Each name is a stock square's main character or a
# new square's first character.
GRID_LAYOUT = [
    ["Mario", "Luigi", "Peach", "Daisy", "Green Yoshi", "Birdo", "Donkey Kong", "Diddy Kong", "Rosalina", "Luma",
     "Bowser", "Bowser Jr."],
    ["Baby Mario", "Baby Luigi", "Baby Peach", "Baby Daisy", "Baby DK", "Dixie Kong", "Tiny Kong", "Funky Kong",
     "Wario", "Waluigi", "King Boo", "King Bob-omb"],
    ["Red Toad", "Toadette", "Toadsworth", "Pauline", "Lubba", "Honey Queen", "Penguru", "Gearmo", "Chimp",
     "Blue Pianta", "Blue Noki", "Monty Mole"],
    ["Larry", "Morton", "Wendy", "Iggy", "Roy", "Lemmy", "Ludwig", "Pom Pom", "Boom Boom", "Hammer Bro",
     "Green Kritter", "King K. Rool"],
    ["Petey Piranha", "Boo", "Bouldergeist", "Blue Magikoopa", "Gray Dry Bones", "Green Koopa Troopa",
     "Red Koopa Paratroopa", "Goomba", "Paragoomba", "Red Shy Guy", "Wiggler", "Blooper"],
]
# Not on a square (Nick): Dry Bowser on Bowser's wheel (its template), Dino Piranha on Petey's ("wheel"),
# Ice Bro on the Hammer Bro wheel with Fire Bro (his template) and Boomerang Bro, the Purple, Black, White and
# Orange Yoshis on Green Yoshi's (its 7th-10th members, wheel7.py).
# Stock characters whose model files are replaced in their own directory. Each body model must be the
# same layout (and size) as the one it replaces; file 2 (the bat) may be any size. Extra Innings' Rosalina,
# Orange Toad, Larry and Luma are no longer stock slots: their models are their definitions' model_blocks
# (0x81-0x84, docs/stock-slot-migration.md).
STOCK_MODELS = {
                # Nick: the Toads become their Super Mario Galaxy counterparts (git-a3, 7add6fa)
                **{sid: {0: f"models/work/{n}/pack/high.bin", 1: f"models/work/{n}/pack/low.bin"}
                   for sid, n in ((0x0D, "captain-toad"), (0x1D, "brigade-blue"), (0x1E, "brigade-yellow"),
                                  (0x1F, "brigade-green"), (0x20, "mailtoad"))}}
# Stock characters whose portraits are redrawn in place (git-e2's finished-style art):
# models/work/icons/new/<name>_<view>.png is encoded over the slot their existing side / front resource row
# points at (EI's private pages 0x92 / 0x93, art at the 64-px slot start like add_icon_art). No rows or keys
# change. Rosalina, Orange Toad, Larry and Luma draw the same PNGs through their definitions' "icon" (new
# slots, add_icon_art). 0x47 / 0x4C are Extra Innings' Fire Mario / Mario stock-slot rows, which nothing on
# the clean base selects.
ALL_STOCK_ICONS = {0x47: "fire-mario", 0x4C: "mario",
               # Toad Brigade (git-a3): their stock rows are on the shared CI8 atlases, so instead of
               # being painted in place they get new slots and rows on our private pages (add_icon_art)
               0x0D: "captain-toad", 0x1D: "brigade-blue", 0x1E: "brigade-yellow", 0x1F: "brigade-green",
               0x20: "mailtoad"}
STOCK_ICONS = dict(ALL_STOCK_ICONS)     # this build's: the Toads' only with toad-brigade (build sets it)
# Stock icon pages Extra Innings damaged, restored from the clean bank (git-a3's inventory): a stray
# 16-px-wide strip at x 528-543, y 156-223 of the shared CI8 atlases at +0x53660 (Pink Yoshi 0x4E, ...)
# and +0x13660 (0x8F, ...). Page 0x86's palette (Brown Kritter front) isn't damaged data so much as
# overlapped: EI's two extra page descriptors (0x92 / 0x93, bank 0x1264-0x12A4) sit on top of the
# first palette (0x1280), entries 2-17. It can't be restored in place without breaking those pages, so
# lossless_icon_pages inserts a clean copy with the page images and repoints page 0x86's palette.
# WRONG, kept for the record: that strip is EI's source tables (0x87520.. sits inside the +0x53660
# atlas image, rows 156+); restoring it wiped table keys. restore_ei_damage is no longer called.
DAMAGED_TILES = ((0x53660, (528, 536), (156, 224)), (0x13660, (528, 536), (156, 224)))
OVERLAPPED_PALETTES = (0x86,)
LOSSLESS_ICONS = True             # private icon pages as RGB5A3 (lossless_icon_pages), not CMPR
CI8_ICONS = "exact"               # icon bank phase C (git-a3): portraits on CI8 pages. "exact": only those CI8 stores
                                  # exactly (every texel identical, c3aab35; git-92's default); True: all of them
                                  # (slightly quantizes 67 portraits: Nick's call); False: off
# the private pages' height limit (GX textures go to 1024): with LOSSLESS_ICONS the pages grow past their 256 px
# (4 rows of 16 slots) as needed; the 61 recolors (every stock color wheel at 10) need 7 rows
ICON_PAGE_MAX_H = 1024
VOICE_NORMAL_TESTS = (0x804A55D4,)     # FUN_804a5018: select voice (v13) only for 0 <= id < 0x4D
VOICE_BRSAR = ROOT / "models/work/sounds/MY2.brsar"
VOICE_TABLES = ROOT / "docs/voice-tables.json"


def voice_files():
    """The clean base's voice archive and its sound ids (build_voices.py writes both from the game's MY2.brsar):
    game-derived, so from the work folder (build(work=))."""
    return work_file("sounds/clean/MY2.brsar"), work_file("sounds/clean/voice_tables.json")


PORTRAIT_PREVIEW_CALLS = (0x80064664, 0x80088F84)


ARENA_LO_SITES = ((0x80595FC4, 0x80595FC8), (0x8059606C, 0x80596070), (0x80596014, 0x80596018))  # lis / addi
OCTOOMBA_SECTION = 0x10000      # step 13: its code + data + clean model copy (the work buffer follows)


def set_arena_low(dol, old, new):
    """Move arena low (step 1 set it to `old`) to `new` at its three lis/addi sites."""
    assert new <= ARENA_LO_MAX, (f"arena low 0x{new:08X} above 0x{ARENA_LO_MAX:08X}: the game's 15 MB MEM1 heap would "
                                 "run past arena high (ARENA_LO_MAX)")
    for lis_addr, addi_addr in ARENA_LO_SITES:
        assert dol.u32(lis_addr) & 0xFFFF == ha(old) and dol.u32(addi_addr) & 0xFFFF == lo(old),             f"arena low at 0x{lis_addr:08X} is not 0x{old:08X}"
        dol.w32(lis_addr, (dol.u32(lis_addr) & 0xFFFF0000) | ha(new))
        dol.w32(addi_addr, (dol.u32(addi_addr) & 0xFFFF0000) | lo(new))


# The Toy Field slot machine (Gm2d_Toy_Slot::CS2dToySlotFace FUN_804ac9dc, Amuse::CMarioR3SlotTask FUN_804b157c /
# FUN_804b1620): a reel entry below 0x65 is a character's face, anything else a symbol (the reel builders store
# symbols as 0x65). `cmpwi 0x65; bge symbol` -> `beq symbol`: a new id is a face too (docs/char-limit-sites.md).
TOY_SLOT_TESTS = (0x804ACC34, 0x804ACD38, 0x804ACE7C, 0x804B15B0, 0x804B1654)
# FUN_80431df0 (a random pick from the characters whose stats row is in a range, from FUN_80432148) gathers up to
# 0x65 ids into a heap buffer of 0xCA bytes (101 halfwords): up to 0x100 into 0x200 (its 41-head walk: gridcells)
ID_POOL_ALLOC, ID_POOL_BOUNDS = 0x80431E10, (0x80431EF8, 0x80431F84)


def id_limit_sites(dol):
    """The id-limit sites that don't depend on the build's characters (the sweep's, docs/char-limit-sites.md)."""
    for addr in TOY_SLOT_TESTS:
        w = dol.u32(addr)
        assert w & 0xFFFF0000 == 0x40800000, f"0x{addr:08X}: {w:08X}, not bge"
        patch_word(dol, addr, w, 0x41820000 | (w & 0xFFFF))                          # beq
    patch_word(dol, ID_POOL_ALLOC, 0x386000CA, 0x38600000 | 2 * (ID_BOUND + 1))    # li r3,0x200
    for addr in ID_POOL_BOUNDS:
        patch_word(dol, addr, 0x2C170065, 0x2C170000 | (ID_BOUND + 1))                # cmpwi r23,0x100
    return [f"id limits: Toy Field slot faces for every id ({len(TOY_SLOT_TESTS)} tests); FUN_80431df0's pool "
            f"0x{ID_BOUND + 1:X} ids"]


def patch_word(dol, addr, expect, new):
    got = dol.u32(addr)
    assert got == expect, f"0x{addr:08X}: expected {expect:08X}, found {got:08X}"
    dol.w32(addr, new)


def alias_r(a, reg, chars):
    """Emit: if reg holds a new id, replace it with its template id."""
    for c in chars:
        skip = f"alias_{reg}_{c['id']}_{a.pc:x}"
        a.cmpwi(reg, c["id"]).bne(skip).li(reg, c["template"])
        a.label(skip)


def poltergust_dol(dol):
    """Build step 0, main.dol part: applied before the tables are copied, so the relocated stats
    table carries Luigi's fielding ability."""
    import build_poltergust as bp
    for addr, stock, new in bp.REQ_SETUP:
        patch_word(dol, addr, stock, new)
    mask_at = bp.ANIM_TABLE + 12 * bp.CATCH_ANIM + 0xB
    assert dol.read(mask_at, 1) == b"\x06", "catch animation prop mask is not stock"
    dol.write(mask_at, b"\x0e")
    if POLTERGUST_NODE is not None:                                 # centred on his body, not in a hand
        for addr, reg in ((0x8036640C, 8), (0x80366410, 9)):
            stock = dol.u32(addr)
            assert stock & 0xFFFF0000 == 0x38000000 | (reg << 21), f"0x{addr:08X}: {stock:08X}"
            dol.w32(addr, 0x38000000 | (reg << 21) | POLTERGUST_NODE)
    if POLTERGUST_STAND_DIVE:                                       # the dive shows part 3 too
        dive_mask = bp.ANIM_TABLE + 12 * DIVE_ANIM + 0xB
        assert dol.read(dive_mask, 1) == b"\x06", "dive animation prop mask is not stock"
        dol.write(dive_mask, b"\x0e")
    row = bp.STATS + bp.LUIGI * 0x8E
    assert int.from_bytes(dol.read(row, 2), "big") == bp.LUIGI
    dol.write(row + 0xA, bytes([bp.SUCTION_CATCH]))
    return ["poltergust   Luigi: suction catch, prop request + catch mask patched"]


def voice_tables(dol, code, data, chars, n_rows):
    """Step 10: a 12-slot sound INFO table per voiced new id (the clean archive's ids, build_voices.py), routed
    by our own voice hooks (voice_hooks.py). A "voice" with no table yet keeps the template's voices."""
    tables = json.loads(voice_files()[1].read_text(encoding="utf8"))["tables"]
    import voice_hooks
    own = {c["id"]: tables[c["voice"]] for c in chars if c["voice"] in tables}
    missing = [c["name"] for c in chars if c["voice"] and c["voice"] not in tables]
    return voice_hooks.apply(dol, code, data, own, n_rows - 1) + \
        ([f"voices       no table yet (template's voices): {', '.join(missing)}"] if missing else [])


def move_backdrops(entries, swings_on, backdrops_on):
    """Star move creations' cut-in backdrops (creators/backdrops.py; the creators' configure put them in
    cutin_backdrop.MOVES): the characters on those moves get them (cutin_backdrop.add_created), a pitch's for
    pitching and a swing's for batting. Swings from custom_swings.SWINGS (after star_swing_stats) and the key
    "star swing"; pitches from "star pitch". Needs cutin-backdrops (left out, logged, without). Returns log lines."""
    import cutin_backdrop, custom_swings
    from creators import backdrops
    swing_of = {}
    if swings_on:
        swing_of = {cid: sid for sid, sw in custom_swings.SWINGS.items() for cid in sw["chars"]}
        swing_of.update({int(e["id"]): int(e["star swing"]) for e in entries if e.get("star swing") is not None})
    pitch_of = {int(e["id"]): int(e.get("stats", {}).get("star pitch", 0)) for e in entries}
    plan = backdrops.plan(cutin_backdrop.MOVES["swing"] if swings_on else {}, cutin_backdrop.MOVES["pitch"],
                          swing_of, pitch_of)
    if not plan:
        return []
    if not backdrops_on:
        return ["move backdrops: not in this build (cutin-backdrops off), left out: "
                + ", ".join(f"0x{c:02X}" for c in plan)]
    return ["move backdrops: " + line for line in cutin_backdrop.add_created(plan)]


def star_swing_stats(dol, entries=(), later=(), defaults=True, valid=None):
    """Characters with a custom star swing (git-d9's custom_swings.SWINGS, plus the per-character key
    "star swing": n on `entries`: custom_swings.assign): stats row +9 = the swing's stock stand-in id, +7 = 1
    (captain flag; without it the star swing never makes contact). Stock ids only (King Boo, stock entries);
    run before the stats table is copied and before stock_stat_edits. A new id's flag and stand-in swing are in
    its stats (normalize). A character that isn't a stock captain and has no backdrop gets the one of the captain
    whose cut-in its swing shows (cutin_backdrop.BACKDROP_FROM). later: stock ids whose rows stock_rows writes (stock
    entries with the key; after stock_stat_edits). defaults: custom_swings.assign's (False: only the keys).
    valid: the characters in this build (None: any); the swings' default characters that aren't are left out."""
    import custom_swings, cutin_backdrop
    row_of = lambda cid: 0x806CE9A0 + STATS_HEADER + cid * STATS_ROW  # noqa: E731
    captain_of = {dol.read(row_of(cid) + 9, 1)[0]: cid for cid in cutin_backdrop.STOCK_FILE
                  if dol.read(row_of(cid) + 7, 1)[0] and dol.read(row_of(cid) + 9, 1)[0]}   # stock swing -> captain
    keyed = custom_swings.assign(entries, defaults)
    out = []
    if valid is not None:                                           # (custom_swings.SWINGS' "chars": the hooks')
        for sid, sw in custom_swings.SWINGS.items():
            sw["chars"] = in_build(list(sw["chars"]), valid, f"star swing {sid}", out)
    swings = {cid: sid for sid, sw in custom_swings.SWINGS.items() for cid in sw["chars"]}
    swings.update({int(e["id"]): int(e["star swing"]) for e in entries if e.get("star swing") is not None})
    swung = []
    for cid, n in sorted(swings.items()):
        if n == 0 and cid not in keyed:
            continue
        name = custom_swings.SWINGS[n]["name"] if n in custom_swings.SWINGS else f"stock swing {n}"
        donor = captain_of.get(custom_swings.cutin_swing(n))
        if (n and donor is not None and cid not in cutin_backdrop.STOCK_FILE
                and cid not in cutin_backdrop.BACKDROP_FROM and cid not in cutin_backdrop.OWN_BACKDROP):
            cutin_backdrop.BACKDROP_FROM[cid] = donor
            name += f", 0x{donor:02X}'s backdrop"
        if cid < STOCK_IDS and cid not in later:
            row = row_of(cid)
            assert int.from_bytes(dol.read(row, 2), "big") == cid, f"stats row 0x{cid:02X}"
            swing, flag = keyed.get(cid) or custom_swings.stats_of(n, cid)
            dol.write(row + 7, bytes([flag]))
            dol.write(row + 9, bytes([swing]))
        swung.append(f"0x{cid:02X} {name} ({n})")
    return out + ["star swings  " + ", ".join(swung)]


STOCK_STAT_EDITS = [  # (stock id, row offset, value): byte below +0xC, else u16 (from build_buddy_clamber)
    (0x09, 0x12, 160),   # Bowser charge power (vanilla 98)
    (0x13, 0x12, 170),   # Bowser Jr. charge power (vanilla 70)
    # (Wario's and Waluigi's captain flag, star pitch and star swing: captains.stat_edits, with the captains that
    # replace them, not with the stock balance)
    # Balance pass Nick approved in the design doc (git-8a): speed nerfs (speed and displayed speed together),
    # babies' speed/slap power, Baby Luigi Enlarge instead of Super Jump, Toadsworth, Boo, Dixie, Petey.
    (0x00, 0x16, 40),   # Mario: speed -> 40 (speed nerf)
    (0x00, 0x1f, 4),   # Mario: dis speed -> 4 (displayed speed matches)
    (0x13, 0x16, 40),   # Bowser Jr.: speed -> 40 (speed nerf)
    (0x13, 0x1f, 4),   # Bowser Jr.: dis speed -> 4 (displayed speed matches)
    (0x0d, 0x16, 40),   # Red Toad: speed -> 40 (speed nerf)
    (0x0d, 0x1f, 4),   # Red Toad: dis speed -> 4 (displayed speed matches)
    (0x1d, 0x16, 40),   # Blue Toad: speed -> 40 (speed nerf)
    (0x1d, 0x1f, 4),   # Blue Toad: dis speed -> 4 (displayed speed matches)
    (0x1e, 0x16, 40),   # Yellow Toad: speed -> 40 (speed nerf)
    (0x1e, 0x1f, 4),   # Yellow Toad: dis speed -> 4 (displayed speed matches)
    (0x1f, 0x16, 40),   # Green Toad: speed -> 40 (speed nerf)
    (0x1f, 0x1f, 4),   # Green Toad: dis speed -> 4 (displayed speed matches)
    (0x20, 0x16, 40),   # Purple Toad: speed -> 40 (speed nerf)
    (0x20, 0x1f, 4),   # Purple Toad: dis speed -> 4 (displayed speed matches)
    (0x11, 0x16, 20),   # Birdo: speed -> 20 (speed nerf)
    (0x11, 0x1f, 2),   # Birdo: dis speed -> 2 (displayed speed matches)
    (0x3d, 0x16, 20),   # Brown Kritter: speed -> 20 (speed nerf)
    (0x3d, 0x1f, 2),   # Brown Kritter: dis speed -> 2 (displayed speed matches)
    (0x3a, 0x16, 15),   # Kritter: speed -> 15 (speed nerf)
    (0x3a, 0x1f, 1),   # Kritter: dis speed -> 1 (displayed speed matches)
    (0x3b, 0x16, 15),   # Blue Kritter: speed -> 15 (speed nerf)
    (0x3b, 0x1f, 1),   # Blue Kritter: dis speed -> 1 (displayed speed matches)
    (0x3c, 0x16, 15),   # Red Kritter: speed -> 15 (speed nerf)
    (0x3c, 0x1f, 1),   # Red Kritter: dis speed -> 1 (displayed speed matches)
    (0x1b, 0x16, 10),   # Hammer Bro: speed -> 10 (speed nerf)
    (0x1b, 0x1f, 1),   # Hammer Bro: dis speed -> 1 (displayed speed matches)
    (0x34, 0x16, 10),   # Fire Bro: speed -> 10 (speed nerf)
    (0x34, 0x1f, 1),   # Fire Bro: dis speed -> 1 (displayed speed matches)
    (0x35, 0x16, 10),   # Boomerang Bro: speed -> 10 (speed nerf)
    (0x35, 0x1f, 1),   # Boomerang Bro: dis speed -> 1 (displayed speed matches)
    (0x38, 0x16, 10),   # Funky Kong: speed -> 10 (speed nerf)
    (0x38, 0x1f, 1),   # Funky Kong: dis speed -> 1 (displayed speed matches)
    (0x09, 0x16, 10),   # Bowser: speed -> 10 (speed nerf)
    (0x09, 0x1f, 1),   # Bowser: dis speed -> 1 (displayed speed matches)
    (0x17, 0x16, 10),   # Yellow Pianta: speed -> 10 (speed nerf)
    (0x17, 0x1f, 1),   # Yellow Pianta: dis speed -> 1 (displayed speed matches)
    (0x02, 0x16, 10),   # Donkey Kong: speed -> 10 (speed nerf)
    (0x02, 0x1f, 1),   # Donkey Kong: dis speed -> 1 (displayed speed matches)
    (0x26, 0x16, 10),   # Petey Piranha: speed -> 10 (speed nerf)
    (0x26, 0x1f, 1),   # Petey Piranha: dis speed -> 1 (displayed speed matches)
    (0x15, 0x16, 10),   # Blue Pianta: speed -> 10 (speed nerf)
    (0x15, 0x1f, 1),   # Blue Pianta: dis speed -> 1 (displayed speed matches)
    (0x16, 0x16, 10),   # Red Pianta: speed -> 10 (speed nerf)
    (0x16, 0x1f, 1),   # Red Pianta: dis speed -> 1 (displayed speed matches)
    (0x07, 0x16, 100),   # Baby Mario: speed -> 100 (babies max speed)
    (0x07, 0x1f, 10),   # Baby Mario: dis speed -> 10 (displayed speed matches)
    (0x08, 0x16, 100),   # Baby Luigi: speed -> 100 (babies max speed)
    (0x08, 0x1f, 10),   # Baby Luigi: dis speed -> 10 (displayed speed matches)
    (0x3f, 0x16, 100),   # Baby Peach: speed -> 100 (babies max speed)
    (0x3f, 0x1f, 10),   # Baby Peach: dis speed -> 10 (displayed speed matches)
    (0x40, 0x16, 100),   # Baby Daisy: speed -> 100 (babies max speed)
    (0x40, 0x1f, 10),   # Baby Daisy: dis speed -> 10 (displayed speed matches)
    (0x41, 0x16, 100),   # Baby DK: speed -> 100 (babies max speed)
    (0x41, 0x1f, 10),   # Baby DK: dis speed -> 10 (displayed speed matches)
    (0x07, 0x10, 80),   # Baby Mario: slap power -> 80 (baby slap buff)
    (0x08, 0x10, 70),   # Baby Luigi: slap power -> 70 (baby slap buff)
    (0x3f, 0x10, 60),   # Baby Peach: slap power -> 60 (baby slap buff)
    (0x40, 0x10, 55),   # Baby Daisy: slap power -> 55 (baby slap buff)
    (0x08, 0x0a, 0),   # Baby Luigi: fielding ability -> 0 (Super Jump removed)
    (0x08, 0x0b, 7),   # Baby Luigi: baserunning ability -> 7 (Enlarge)
    (0x1c, 0x16, 45),   # Toadsworth: speed -> 45 (+10)
    (0x1c, 0x1f, 4),   # Toadsworth: dis speed -> 4 (displayed)
    (0x1c, 0x24, 180),   # Toadsworth: curve -> 180 (buff)
    (0x0e, 0x24, 70),   # Boo: curve -> 70 (nerf)
    (0x27, 0x24, 65),   # Dixie Kong: curve -> 65 (Daisy's value)
    (0x26, 0x12, 70),   # Petey Piranha: charge power -> 70 (nerf)
    (0x26, 0x1d, 7),   # Petey Piranha: displayed batting -> 7 (displayed batting matches charge)
]
STOCK_CHEM_EDITS = [  # (stock id A, stock id B, value): set in both rows (git-8a's balance pass, Nick)
    (0x07, 0x00, 2),   # Baby Mario <-> Mario = 2 (baby gets adult + adult partners)
    (0x07, 0x01, 2),   # Baby Mario <-> Luigi = 2 (baby gets adult + adult partners)
    (0x07, 0x04, 2),   # Baby Mario <-> Peach = 2 (baby gets adult + adult partners)
    (0x07, 0x15, 2),   # Baby Mario <-> Blue Pianta = 2 (baby gets adult + adult partners)
    (0x07, 0x16, 2),   # Baby Mario <-> Red Pianta = 2 (baby gets adult + adult partners)
    (0x07, 0x17, 2),   # Baby Mario <-> Yellow Pianta = 2 (baby gets adult + adult partners)
    (0x07, 0x18, 2),   # Baby Mario <-> Blue Noki = 2 (baby gets adult + adult partners)
    (0x07, 0x19, 2),   # Baby Mario <-> Red Noki = 2 (baby gets adult + adult partners)
    (0x07, 0x1a, 2),   # Baby Mario <-> Green Noki = 2 (baby gets adult + adult partners)
    (0x08, 0x01, 2),   # Baby Luigi <-> Luigi = 2 (baby gets adult + adult partners)
    (0x08, 0x00, 2),   # Baby Luigi <-> Mario = 2 (baby gets adult + adult partners)
    (0x08, 0x05, 2),   # Baby Luigi <-> Daisy = 2 (baby gets adult + adult partners)
    (0x3f, 0x04, 2),   # Baby Peach <-> Peach = 2 (baby gets adult + adult partners)
    (0x3f, 0x00, 2),   # Baby Peach <-> Mario = 2 (baby gets adult + adult partners)
    (0x3f, 0x05, 2),   # Baby Peach <-> Daisy = 2 (baby gets adult + adult partners)
    (0x3f, 0x0f, 2),   # Baby Peach <-> Toadette = 2 (baby gets adult + adult partners)
    (0x40, 0x05, 2),   # Baby Daisy <-> Daisy = 2 (baby gets adult + adult partners)
    (0x40, 0x01, 2),   # Baby Daisy <-> Luigi = 2 (baby gets adult + adult partners)
    (0x40, 0x04, 2),   # Baby Daisy <-> Peach = 2 (baby gets adult + adult partners)
    (0x40, 0x11, 2),   # Baby Daisy <-> Birdo = 2 (baby gets adult + adult partners)
    (0x41, 0x02, 2),   # Baby DK <-> Donkey Kong = 2 (baby gets adult + adult partners)
    (0x41, 0x03, 2),   # Baby DK <-> Diddy Kong = 2 (baby gets adult + adult partners)
    (0x26, 0x11, 1),   # Petey Piranha <-> Birdo = 1 (good chemistry removed)
    (0x34, 0x05, 0),   # Fire Bro <-> Daisy = 0 (the Bros share one chemistry tree, as Hammer Bro's)
    (0x35, 0x05, 0),   # Boomerang Bro <-> Daisy = 0 (same)
]
# New characters copy their template's row after these edits: King Bob-omb (template Wario) keeps swing 7
# through "stats" in his definition.
# A stock captain replaced in this build (Wario by King Bob-omb, Waluigi by King Boo, or the "captains" option's) loses
# its captain flag, star pitch and star swing (+7, +8, +9: captains.stat_edits); one that keeps its slot keeps them
# (Wario without King Bob-omb stays captain 8, and slot 7's labels stay "Phony": star_move_labels' Kingly Kaboom is
# King Bob-omb's), and a new character built on it copies them cleared (captains.kept_star_moves, star_move_edits).


def stock_stat_edits(dol):
    """Stock characters' stats rows; run before the stats table is copied."""
    out = []
    widths = {o: w for o, w in STAT_FIELDS.values()}   # the displayed stats (0x1C-0x1F) are bytes too
    for cid, off, value in STOCK_STAT_EDITS:
        row = 0x806CE9A0 + STATS_HEADER + cid * STATS_ROW
        assert int.from_bytes(dol.read(row, 2), "big") == cid, f"stats row 0x{cid:02X}"
        assert off in widths, f"0x{cid:02X}: +0x{off:X} is not a stat field"
        n = widths[off]
        dol.write(row + off, value.to_bytes(n, "big"))
        out.append(f"0x{cid:02X} +0x{off:X}={value}")
    for a, b, value in STOCK_CHEM_EDITS:
        for x, y in ((a, b), (b, a)):
            row = 0x806CE9A0 + STATS_HEADER + x * STATS_ROW
            assert int.from_bytes(dol.read(row, 2), "big") == x, f"stats row 0x{x:02X}"
            dol.write(row + CHEM_BASE + y, bytes([value]))
    tables = {t[0]: t for t in TABLES}
    for cid, stat, value in STOCK_TABLE_EDITS:
        table, off, kind = TABLE_STATS[stat]
        _, addr, size, header = tables[table]
        buf = bytearray(dol.read(addr + header + cid * size, size))
        _put_table_stat(buf, off, kind, value, stat)
        dol.write(addr + header + cid * size, bytes(buf))
    return ["stat edits   " + ", ".join(out), f"chem edits   {len(STOCK_CHEM_EDITS)} stock pairs (both ways)",
            f"table edits  {len(STOCK_TABLE_EDITS)} stock values"]


def star_move_edits(row, cid):
    """A stats row of stock captain `cid` that keeps its slot (captains.kept_star_moves) with its captain flag and
    star moves cleared (captains.STAR_MOVE_FIELDS): what a new character built on it copies."""
    import captains
    row = bytearray(row)
    for off in captains.STAR_MOVE_FIELDS:
        row[off] = 0
    return bytes(row)


# (stock id, TABLE_STATS name, value): Nick's review editor (git-8a). Empty since the stock-slot migration:
# Luma's catch radii and Larry's hit trajectory are their definitions' "table_stats" (0x84, 0x83).
STOCK_TABLE_EDITS = []


# --- Features (the patcher, docs/patcher.md) -------------------------------------------------------------------------
# build(..., features=set) runs a step only when its feature id is in the set; features=None is everything on, the
# same build as before features existed (byte-identical). Ids are the notes page's entry ids (wiki/index.html
# ENTRIES) where the page has one; "page": False marks ids the page doesn't have yet. "steps": what the id switches,
# in _build's order. "requires": other ids that must be on with it (check_features). "part_of": a page entry that
# is not a switch of its own (on with that one). "char_keys": definition keys that need the feature: with the feature
# off, a character's key is left out (degrade; it would reach code the build left out). "options": the feature's
# build() keyword arguments (the patcher profile's "options"; None: the default, a chars-N build's).
FEATURES = {
    # characters
    "new-ids": {"steps": ["per-id tables, roster / chemistry / portrait / model hooks, model directories, the icon "
                          "bank: every build with new characters, none without (a build with no characters leaves "
                          "new-ids and everything that needs it out, logged)",
                          "char_names.add_names / patch_code / rename_text (dir 121 file 5; \"names\" was its own "
                          "id until Nick folded it in)",
                          "the select grid, sized to the new squares (gridcells.plan: the stock grid with none, up to "
                          "12 x 5; name rows PORTRAIT_RESOURCE_ADDS, gridcells.add_grid_square, gridcells.patch_layout "
                          "+ char_names.add_name_art, patch_challenge_layout; \"select-grid\" was its own id until "
                          "Nick folded it in)",
                          "wheel7.apply + wheel7.layout_bytes (file 19) when a color wheel has more than 6 members "
                          "(\"bigger-color-wheel\" was its own id until Nick folded it in)",
                          "name_telop.patch_code / add_art (the pitching-change name banner: dir 119 file 1 name art "
                          "for the new ids)"],
                "doc": "Characters past the stock roster (the chars list), with their names in the name table and "
                       "the stock Toads' renames, a character-select grid with a square for each GRID_SQUARES entry "
                       "in the build, and color wheels of up to 10."},
    "recolor-tool": {"requires": ["new-ids"], "steps": [], "doc": "Recolors are character definitions (the profile's \"recolors\"): no "
                                         "build step of their own."},
    "toad-brigade": {"page": False, "steps": ["STOCK_MODELS (the Toads' model files)"],
                     "doc": "The stock Toads get the Super Mario Galaxy Toad Brigade models (git-a3). Their names "
                            "(char_names.STOCK_RENAMES) and portraits (STOCK_ICONS) come with it too (not with new-ids alone)."},
    "stock-balance": {"page": False, "steps": ["stock_stat_edits (STOCK_STAT_EDITS / STOCK_CHEM_EDITS / "
                                               "STOCK_TABLE_EDITS)"],
                      "doc": "Nick's balance pass on stock characters' stats and chemistry (git-8a)."},
    "immunities": {"page": False, "requires": ["new-ids"], "steps": ["immunities.apply"],
                   "doc": "Heart swing spares the new females (immunities.FEMALE_EXTRA: Pauline, Honey Queen, Pom "
                          "Pom, Wendy, Rosalina); POW and the Flower swing spare the new floaters (FLOATING_EXTRA: "
                          "Honey Queen and the four Lumas; Bouldergeist and Lubba float through their family)."},
    "voices": {"page": False, "requires": ["new-ids"],
               "steps": ["select-voice normal test (VOICE_NORMAL_TESTS)", "voice_tables", "MY2.brsar"],
               "doc": "New characters' own voices (a definition's \"voice\")."},
    "poltergust-dive": {"page": False, "steps": ["poltergust_dol", "the prop entry and Luigi's dive bank (dt_na)"],
                        "doc": "Luigi's dive is Suction Catch with the Poltergust 3000."},
    # captains & select screens
    "captains": {"requires": ["new-ids"], "steps": ["captains.configure(option=)", "captains.stat_edits",
                                                    "captains.add_captain", "captains.patch_layouts"],
                 "options": {"captains_option": "the captain roster {\"list\": [...], \"positions\": {...}} "
                                                "(captains.check); None: the default 14 (captains.DEFAULT_OPTION)"},
                 "doc": "The captains: any character, stock or new, up to 18, and where each stands (git-a7)."},
    "menu-color": {"steps": ["menu_purple.layout_for(color) (captains' file 1), else menu_purple.patch_layout"],
                   "options": {"menu_color": "a menu_purple preset name or \"#RRGGBB\"; None: purple"},
                   "doc": "The menu background's colour (git-5c)."},
    "bench": {"requires": ["new-ids"], "steps": ["bench.add_message", "bench.apply",
                                                 "bench.layout_bytes (after the select screen's rows)"],
              "doc": "Up to 5 bench players per team (bench.NB), subbed in from the pause menu (docs/bench.md)."},
    "fielder-spots": {"page": False, "steps": ["fielder_spots.apply"],
                      "doc": "Hold A+B and drag a team's fielders (not P or C) to new spots on the positions screen, "
                             "or shift the fielding team's on the Change the defense screen; clamped to the field "
                             "(docs/fielder-spots.md)."},
    # stadiums (the stadium JSON's keys; "octoombas" / "bobombs" / "dimensions" are dropped from it when off)
    "new-stadium": {"steps": ["new_stadium.add_directories, stadium_pregame", "new_stadium.apply, stadium_music"],
                    "doc": "Stadium id 10 (stadiums/stadium10.json)."},
    "day-night-scenes": {"part_of": "new-stadium", "requires": ["new-stadium"], "steps": [], "doc": "stadium JSON"},
    "select-map-day-night": {"part_of": "new-stadium", "requires": ["new-stadium"], "steps": [], "doc": "stadium JSON"},
    "moving-scenery": {"part_of": "new-stadium", "requires": ["new-stadium"], "steps": [], "doc": "stadium JSON"},
    "dimensions": {"requires": ["new-stadium"], "steps": ["stadium_dimensions.apply (and the hazards' fences)"],
                   "doc": "The stadium JSON's \"dimensions\"."},
    "mansion-day": {"steps": ["night_to_day.add_files", "night_to_day.tables / hooks", "night_to_day.nav"],
                    "doc": "Luigi's Mansion by day."},
    # hazards
    "walking-bobombs": {"requires": ["new-stadium"], "steps": ["bobomb_hazard.apply"], "doc": "stadium JSON \"bobombs\""},
    "octoombas": {"requires": ["new-stadium"], "steps": ["octoomba_hazard.apply"], "doc": "stadium JSON \"octoombas\""},
    "piranha-plants": {"steps": ["dino_piranhas.apply (dino_piranhas.ids)"], "char_keys": ["\"piranha_plants\""],
                       "doc": "For the characters with \"piranha_plants\": true (Dino Piranha's definition, a stock "
                              "entry such as Petey Piranha's)."},
    # items
    "fixed-items": {"steps": ["batter_items.HOOKS (FIXED_ITEM / ALWAYS_ITEM; items 6+ need new-roulette-item, 7 "
                              "item-variants, 8+ koopaling-items, else dropped)"],
                    "char_keys": ["\"batting_item\"", "\"always_item\""],
                    "doc": "Always the same batting item (batter_items.fixed / always: a definition's or stock entry's "
                           "\"batting_item\" / \"always_item\")."},
    "item-odds": {"steps": ["starbits_roulette.apply(odds=) (new-roulette-item on), else starbits_roulette.stock_odds "
                            "(the stock table in place)"],
                  "options": {"item_odds": "{item name or id: weight 0-255 or [3 weights]} (starbits_roulette.odds_ids); "
                                           "None: the roulette's own"},
                  "doc": "How often each batting item comes up in the roulette (git-a7)."},
    "ability-edits": {"steps": ["ability_edits.apply (the abilities' tables and constants, before the stats table)"],
                      "options": {"ability_edits": "{ability name: {field: value}} (ability_edits.check / fields); "
                                                   "None: the game's"},
                      "doc": "Fielding and baserunning abilities' numbers, for everyone with the ability (git-a7)."},
    "new-roulette-item": {"steps": ["starbits_model", "starbits_roulette.apply, starbits_item.apply",
                                    "starbits_roulette.patch_layout"],
                          "doc": "Star Bits, item id 6."},
    "item-variants": {"requires": ["new-roulette-item"],
                      "steps": ["ice_item.apply (Ice, id 7) + the roulette's extra id",
                                "ice_item.patch_layout / add_freeze_effect / add_blue_textures"],
                      "doc": "Ice: a Fireball variant with its own id, icon and ball colour, that freezes."},
    "freeze-on-hit": {"part_of": "item-variants", "requires": ["item-variants"], "steps": [], "doc": "Ice (ice_item)"},
    "item-engine": {"page": False, "requires": ["item-variants", "fixed-items"],
                    "steps": ["the item machinery of koopaling-items (variant ids 8+, ludwig_fire, koopa_items, "
                              "shell_item, item_sounds, wendy_rings' draw hooks, runner_hits), ids 8-13 unreachable "
                              "unless chosen"],
                    "doc": "Internal (git-92): what custom items need, without the Koopalings' six items in the "
                           "game. Ticked by any item creation; koopaling-items implies it. A creation of one of "
                           "ours (e.g. Iggy's) puts that one item back."},
    "koopaling-items": {"page": False, "requires": ["item-variants", "fixed-items"],
                        "steps": ["the Koopalings' model blocks in item slot 0x2A (starbits_model extra)",
                                  "ludwig_fire, koopa_items, wendy_rings, lemmy_balls, bullet_bill",
                                  "their icons (ice_item.patch_layout more=) and ball colours"],
                        "doc": "The Koopalings' items (ids 8-13): one switch until koopa_items is split per item."},
    "knockback": {"part_of": "koopaling-items", "requires": ["koopaling-items"], "steps": [], "doc": "koopa_items"},
    "item-flight": {"part_of": "koopaling-items", "requires": ["koopaling-items"], "steps": [], "doc": "koopa_items"},
    "multi-shot": {"part_of": "koopaling-items", "requires": ["koopaling-items"], "steps": [], "doc": "ludwig_fire"},
    "homing": {"part_of": "koopaling-items", "requires": ["koopaling-items"], "steps": [], "doc": "bullet_bill"},
    "reused-hazard-model": {"part_of": "koopaling-items", "requires": ["koopaling-items"], "steps": [],
                            "doc": "bullet_bill"},
    "field-hazard-items": {"part_of": "koopaling-items", "requires": ["koopaling-items"], "steps": [],
                           "doc": "wendy_rings"},
    "item-ability": {"requires": ["new-ids"],
                     "steps": ["item_abilities.apply + star_move_labels.apply (one card pointer table)",
                               "star_move_labels.patch_tables, SwingCard.patch",
                               "with captains: patch_captain_tables, SwingCard / Card.patch_captain, file 18 rows",
                               "file 19 rows (star_move_labels.layout_bytes, Card.layout_bytes)"],
                     "doc": "Item / hitting / running abilities on the cards and captain select (a definition's "
                            "item_ability, hitting_ability, running_ability). The label machinery under them "
                            "(Kingly Kaboom, custom swing and pitch names, 4 lines) is on whenever a card or captain "
                            "select can show a label past the stock ones (LABEL_USERS)."},
    # star swings & pitches
    "custom-swings": {"steps": ["star_swing_stats", "custom_swings / gravity_ball / boo_ball hooks"],
                      "char_keys": ["\"star swing\": a custom swing id (custom_swings.SWINGS)"],
                      "doc": "Star swings past the stock 12 (build flag star_swings)."},
    "swing-path": {"part_of": "custom-swings", "requires": ["custom-swings"], "steps": [], "doc": "gravity_ball"},
    "swing-items": {"requires": ["custom-swings", "new-roulette-item"], "steps": ["star_shower hooks"],
                    "doc": "Luma's Star Shower drops Star Bits."},
    "cutin-backdrops": {"steps": ["cutin_backdrop.backdrop_directory", "cutin_backdrop.hooks(own=True) (off: "
                                  "hooks(own=False), the stock backdrops new captains borrow)"],
                        "doc": "Captains' own cut-in backdrops."},
    "pitch-slots": {"steps": [], "doc": "Star pitches 13-16; each pitch below is its own switch and requires this."},
    "pitch-path": {"requires": ["pitch-slots"], "steps": ["pitch_launch_star (14)", "pitch_gravity_well (13)"],
                   "char_keys": ["stats \"star pitch\" 13 / 14"], "doc": "Launch Star, Cosmic Pull."},
    "pitch-vanish": {"requires": ["pitch-slots"], "steps": ["pitch_vanishing_ball.apply"],
                     "char_keys": ["\"star pitch\" 16 (King Boo's: STOCK_DEFAULTS)"],
                     "doc": "The Vanishing Ball (16; King Boo's by default; build flag star_swings)."},
    "pitch-items": {"requires": ["pitch-slots"], "steps": ["pitch_bobomb_drop (15)"],
                    "char_keys": ["stats \"star pitch\" 15"], "doc": "Bob-omb Drop."},
    # fielding
    "new-ability-slot": {"requires": ["new-ids"], "steps": ["abilities.patch_labels (also with star-solo-toss)"],
                         "doc": "Fielding abilities past 12: their label rows (the rows are in add_name_art)."},
    "clamber-solo-jump": {"steps": ["buddy_clamber_code.apply (a character with fielding ability 14)",
                                    "abilities.patch_labels (its label, as new-ability-slot)"],
                          "char_keys": ["\"fielding ability\" 14 (the Kongs' by default: STOCK_DEFAULTS; Chimp's)"],
                          "doc": "Clamber Jump (fielding ability 14): Clamber plus the solo buddy jump off the wall. "
                                 "Stock Clamber (9) is left as the game has it (git-a7; the id kept for old profiles)."},
    "star-solo-toss": {"steps": ["boom_boom_star_throw.apply (boom_boom_star_throw.ids)"],
                       "char_keys": ["\"fielding ability\" 13"],
                       "doc": "The Tantrum Toss (fielding ability 13; Boom Boom). Its spin plays over Bowser's "
                              "cut-in backdrop (cutin_backdrop.BACKDROP_FROM 0x67, on without cutin-backdrops too)."},
    # batting & gameplay
    "batter-depth": {"steps": ["batter_depth.apply"], "doc": "Step up or back in the box."},
    "level-5": {"steps": ["level5.alloc", "level5.apply (the CPU manager hook; cpu_perfect's bytes swapped per match)",
                          "level5_menu.add_message / apply / patch_layout (the 5th and 6th buttons on the exhibition popup and Challenge's level dialog; Challenge's Bowser games at level 5)"],
                "doc": "CPU levels 5 (\"Superstar\") and 6 (\"Legend\") past level 4: they play as level 4 plus "
                       "every CPU change below (the same for now); levels 1-4 are vanilla."},
    "cpu-star-swings": {"requires": ["level-5"], "steps": ["cpu_stars.apply_swings"],
                        "doc": "Level 5 CPU batters star-swing more the weaker their charge power: + (100 - charge power) / 2 "
                               "to the chance (Waluigi +49, Bowser +1)."},
    "cpu-no-star-pitches": {"requires": ["level-5"], "steps": ["cpu_stars.apply_no_pitches"],
                            "doc": "The level 5 CPU pitcher never throws a star pitch (the cpu_star_pitch.py test mode "
                                   "overrides it)."},
    "cpu-charge-timing": {"requires": ["level-5"], "steps": ["cpu_charge.apply"],
                          "doc": "Level 5 CPU batters start charging at once and are exactly mid full-charge on "
                                 "the frame they swing."},
    "cpu-no-bunts": {"requires": ["level-5"], "steps": ["cpu_bunt.apply"],
                     "doc": "The level 6 CPU never bunts."},
    "cpu-cursed-ball": {"requires": ["level-5"], "steps": ["cpu_cursed.apply"],
                        "doc": "Level 5 / 6: the CPU's charged pitches are cursed balls too (stock: human only). Off "
                               "by default (Nick, 2026-09-29: \"allow people to enable cpu cursed ball\")."},
    "cpu-batter-track": {"requires": ["level-5"], "steps": ["cpu_track.apply"],
                         "doc": "Level 6 CPU batters judge ball / strike on the umpire's real zone (x at z 1.12 or "
                                "0.32) from the ball's flight on the frame they start the swing, and aim the bat at "
                                "the ball's forecast crossing."},
    "cpu-rundown": {"requires": ["level-5"], "steps": ["cpu_rundown.apply", "cpu_rundown_log.apply_code"],
                    "doc": "Level 6 CPU rundowns: throw early to the base ahead, hold on the base behind."},
    "cpu-items": {"requires": ["level-5"], "steps": ["cpu_items.apply"],
                  "doc": "Level 6 CPU item use: its real base item, aimed and timed to the moment the fielder "
                         "fields the ball."},
    "cpu-item-defense": {"requires": ["level-5"], "steps": ["cpu_item_defense.apply", "cpu_defense_log.apply"],
                         "doc": "Level 6 CPU fielding vs items: jump POWs, pass when a teammate is near, peak-timed "
                                "fly-ball jumps, run around items, Boo ignored."},
    "cpu-subs": {"requires": ["level-5"], "steps": ["cpu_subs.apply"],
                 "doc": "Level 5 CPU pitching change: a random one of its top 3 pitchers (no captain preference, "
                        "not the catcher), then 1B..RF re-arranged for chemistry (CF-LF / CF-RF, then 2B-SS, "
                        "then SS-1B / 3B-1B). The timing stays stock."},
    "cpu-pitching": {"requires": ["level-5"], "steps": ["cpu_pitching.apply_data", "cpu_pitching.apply_code"],
                     "doc": "Level 5 CPU pitchers aim at the edge of the zone (curves break back in), fastballs "
                            "mostly from charge speed 150+, changeups by how high they float (30 / 10 / 4%)."},
    "cpu-settings": {"requires": ["level-5"],
                     "steps": ["cpu_settings.configure (the cpu_* constants, around _build)",
                               "cpu_settings.swaps (level5.apply's per-level bytes)"],
                     "options": {"cpu_settings": "{setting: value or {\"5\": v, \"6\": v}} (cpu_settings.check / "
                                                 "fields); None: today's defaults"},
                     "doc": "The patcher's CPU levels tab: a player's own level 5 / 6 CPU numbers (cpu_settings.py)."},
    "cpu-perfect-batting": {"requires": ["level-5"], "steps": ["cpu_perfect.BATTING (swapped in per match by level5.apply)"],
                            "doc": "Level 5 CPU batters: pitch guess always right, no aim or timing error, never "
                                   "take a strike or chase an outside ball; they track 85% of pitches (about 85% "
                                   "sweet spots), level 6 every pitch."},
    "cpu-perfect-pitching": {"requires": ["level-5"], "steps": ["cpu_perfect.PITCHING (swapped in per match by level5.apply)"],
                             "doc": "Level 5 CPU pitchers: every charged fastball perfect, always curve and break "
                                    "late, never the same spot twice."},
    "cpu-perfect-fielding": {"requires": ["level-5"], "steps": ["cpu_perfect.FIELDING (swapped in per match by level5.apply)"],
                             "doc": "Level 5 CPU fielders: always dive / jump (fly balls too), no reaction or "
                                    "throw delay."},
    "cpu-perfect-running": {"requires": ["level-5"], "steps": ["cpu_perfect.RUNNING (swapped in per match by level5.apply)"],
                            "doc": "Level 5 CPU runners: always a good steal jump, every sprint tap lands, close "
                                   "plays pressed in 6 frames."},
    "batter-star": {"steps": ["batter_star.HOOKS"], "char_keys": ["\"batter_star\""],
                    "doc": "A star when coming up to bat (batter_star.ids: STAR_CHARS and a definition's "
                           "\"batter_star\": true; off: the key is ignored)."},
    "chance-cheer": {"steps": ["pauline_chance / _fixes / _tuning / _hold (pauline_chance.ids)",
                               "pauline_chance_tuning.patch_layout"], "char_keys": ["\"chance_cheer\""],
                     "doc": "Pauline's chance cheer (id 0x66 in the build, and \"chance_cheer\": true on any character; "
                            "with voices, her own jingle, else Mario's)."},
    "minimap-decoys": {"requires": ["new-ids"], "steps": ["pompom_ring stand-in icon", "pompom_decoys / pompom_ring"],
                       "char_keys": ["\"minimap_decoys\""],
                       "doc": "For the characters with \"minimap_decoys\": true (Pom Pom's definition, a stock entry). "
                              "Needs new-ids: the ring is an icon-bank entry past the last id."},
    "no-replays": {"steps": ["replay_tweaks.apply"],
                   "doc": "No instant replays: the replay picker FUN_8016D42C returns at once (docs/replay.md)."},
    "replay-slow-motion": {"steps": ["replay_tweaks.apply"],
                           "options": {"speed": "the game runs 1/speed (1..8); None: 3",
                                       "frames": "how long, in frames (1..600); None: 90"},
                           "doc": "The stock slow-motion replay (a close play at the plate) plays slower or longer: "
                                  "its SPEED / WAIT words (stock 1/2 speed for 50 frames; docs/replay.md)."},
    "replay-camera": {"steps": ["replay_tweaks.apply"],
                      "options": {"camera": "\"tv\" (fixed TV cameras) or \"chase\"; None: tv"},
                      "doc": "After contact every replay takes the TV cameras, or the chase camera, instead of one at "
                             "random (the shared subroutine 8079FEF0; docs/replay.md)."},
    "contact-freeze": {"steps": ["replay_tweaks.apply"],
                       "options": {"percent": "the freeze on bat contact, % of stock (0..400; 0 = none); None: 200"},
                       "doc": "The models' freeze when the bat meets the ball, longer or shorter (0x806277B6 rows; "
                              "docs/replay.md)."},
    "inning-break-time": {"steps": ["inning_break.apply"],
                          "options": {"seconds": "how long the box score shows between innings (0.5..30), or "
                                                 "\"stock\"; None: stock (nothing built)"},
                          "doc": "The box score between half-innings shows for a set time (stock: one camera pass, "
                                 "3.4 to 7.7 s by stadium); A still skips it. The end-of-half fielder shot before it is "
                                 "skipped too. It can't close before the fielder reload is done (disc-bound, about "
                                 "7 s). Hooks the half-inning change "
                                 "FUN_80132860 (inning_break.py, docs/replay.md section 6)."},
    # testing
    "boot-captain-select": {"steps": ["quickboot.apply (mode captain)"],
                            "options": {"boot_captain": "{\"stadium\": 0, \"night\": false}: the stadium the "
                                                        "game after captain select plays in (quickboot.STADIUMS, "
                                                        "the times of day each has; there is no stadium select on "
                                                        "this path); None: Mario Stadium by day"},
                            "doc": "Power on to captain select. On in every chars-N build; the patcher's default "
                                   "is off. boot-game wins when both are on."},
    "boot-game": {"steps": ["quickboot.apply (mode game, boot_game_args)"],
                  "options": {"boot_game": "{\"captains\": [2 names or ids], \"teams\": [[up to 8], [up to 8]], "
                                           "\"stadium\": 0, \"night\": false, \"level\": 2} (boot_game_args; quickboot "
                                           "fills empty slots; quickboot.STADIUMS; level: the CPU level 1..4, 5 / 6 "
                                           "with level-5, quickboot.LEVELS; optional \"lineups\", "
                                           "\"positions\", and \"benches\" [[up to 5, the DH first], x2] with "
                                           "\"dr\" [who sits for the DH or null, x2]: bench.apply's preset, once "
                                           "per power-on, when the bench is in the build); None: "
                                           "Mario vs Bowser, filler teams"},
                  "doc": "Power on straight into an Exhibition game with the profile's captains and teams, once per "
                         "power-on (then the stock menus). Player 1 plays team 1; with cpu-vs-cpu both teams are CPU. "
                         "Only when the profile's features name it (never in a features=None build)."},
    "share-anim-banks": {"page": False, "steps": ["bank8_share.apply"],
                         "doc": "Players whose file 14 (animation bank 8) is byte-identical share one loaded copy "
                                "in a match instead of one each (git-f3; the recolors and same-template characters "
                                "on a team): up to about 1 MB more free memory. On by default since Nick's "
                                "bank8-1 / bank8-2 tests (2026-09-26)."},
    "cpu-vs-cpu": {"steps": ["cpu_vs_cpu.apply"],
                   "doc": "Exhibition matches are CPU vs CPU: pick captains, teams and the stadium as usual, then watch "
                          "(git-95). Only when the profile's features name it (off in chars-N builds)."},
    "football-fielder10": {"page": False, "steps": ["football_fielder10.apply (its own section, 19d)"],
                           "doc": "Football prototype: a real 10th fielder (fielder id 13, model actor 13), cast from "
                                  "the batting team, walked by our CPU brain through the stock movement, walls and "
                                  "knockdown; instant replay off (docs/fielder-count.md). Only when the profile's "
                                  "features name it."},
    "kicking-challenge": {"page": False, "steps": ["kicking_challenge.apply (its own section, 19e)",
                                                   "kick_art.patch_dtna (GOOD! / NO GOOD banners, no foul poles)"],
                          "doc": "Kicking challenge: the pitcher holds (a slow, straight, overhand toss), the batter "
                                 "kicks (a forgiving contact, the angle narrowed), a kick between the uprights and "
                                 "over the bar is GOOD! (posts you can doink), anything else NO GOOD (an out); the "
                                 "goal starts at 20 m and moves 5 m back after each good kick; the scoreboard shows "
                                 "the longest good kick and the streak; all back to the start every half-inning "
                                 "(docs/kicking-challenge.md). Only when the profile's features name it."},
    "cricket": {"page": False, "steps": ["cricket.apply (its own section, 19g)",
                                         "cricket_art.patch_dtna (FOUR! over the FOUL! banner)"],
                "doc": "Cricket MVP: two ends (home and a far end beside the mound), runners go back and forth and "
                       "each completed leg is a run; no foul ground; over the wall on the fly is SIX, a ball that "
                       "reaches the wall is FOUR (a dead ball); caught, run out, or bowled (one strike) is out; each "
                       "side bats 12 pitches or 3 outs, one inning (docs/cricket.md). Only when the profile's "
                       "features name it."},
    "captain-faceoff": {"steps": ["captain_faceoff.apply (its own section, 19f)"],
                        "doc": "Before the walkout, after the stadium flyover: the two captains face each other near "
                               "home plate and do their walkout point, one fixed camera shot of 2.5 s (a skip button "
                               "ends it), then the stock walkout. The batting captain is loaded for the shot into an "
                               "empty runner actor and freed after it (captain_faceoff.py). Off with quickboot's "
                               "skip_intro."},
    "match-seed": {"steps": ["match_seed.apply"],
                   "options": {"seed": "a number 0..0xFFFFFFFF: every match's RNG seeded with it, so a CPU vs CPU game "
                                       "replays; None: the console clock, a new game every match"},
                   "doc": "Pick the seed of the game's dice rolls: a number replays the same CPU vs CPU game (same "
                          "teams and stadium), blank gives a new one every match (docs/rng.md). Only when the "
                          "profile's features name it."},
}
# The page's entries that no charbuild step switches: test builds (build_test_game.py, build_test_pitch.py, their
# quickboot / cpu_star_pitch modes) and Gecko codes.
NOT_IN_BUILD = {"full-star-meter": "test builds / Gecko code", "infinite-outs": "quickboot infinite_outs",
                "all-items-on": "quickboot items", "cpu-star-pitch": "cpu_star_pitch.py (build_test_pitch.py)",
                # the notes page's editors: options the patcher window sets, not build switches (git-92)
                "character-editor": "an option set by the patcher window's Characters tab (profile key \"characters\")",
                "character-packs": "an option set by the patcher window's Import character... (profile key \"imported\")",
                "custom-fences": "an option set by the patcher window's Stadiums tab (profile key \"stadium\")",
                "grid-order": "an option set by the patcher window's Select grid tab (profile options \"grid-order\")",
                "hazard-creator": "an option set by the patcher window's Stadiums tab, Hazards (profile key \"creations\")",
                "item-creator": "an option set by the patcher window's Create tab (profile key \"creations\")",
                "select-map-looks": "an option set by the patcher window's Stadiums tab, Select map (profile key "
                                    "\"select_map\")",
                "stadium-builder": "an option set by the patcher window's Stadiums tab (profile keys \"stadium\", "
                                   "\"stadium_2\")",
                "swing-creator": "an option set by the patcher window's Create tab (profile key \"creations\")"}
# build flags -> the features they are (with features= given, a flag not passed defaults to its feature)
FLAG_FEATURES = {"grid_square": ("new-ids",), "poltergust": ("poltergust-dive",),
                 "dino_plants": ("piranha-plants",), "captain": ("captains",), "voices": ("voices",),
                 "batter_depth": ("batter-depth",), "star_swings": ("custom-swings", "pitch-vanish"),
                 "stadium": ("new-stadium",), "star_bits": ("new-roulette-item",), "bench": ("bench",)}
ALL_FEATURES = frozenset(FEATURES)


def _needs(f, g):
    return f == g or any(_needs(r, g) for r in FEATURES[f].get("requires", ()))


# the features a build with no new characters leaves out (new-ids and everything that needs it)
NEEDS_NEW_IDS = frozenset(f for f in FEATURES if _needs(f, "new-ids"))
# the features whose labels need the card / captain select label tables and rows (star_move_labels, item_abilities):
# with any of them on, the label machinery is built (a stats id past the stock labels without it showed garbage)
LABEL_USERS = ("item-ability", "captains", "custom-swings", "pitch-slots", "new-ability-slot", "star-solo-toss")
# what build() can do beyond features: "no-new-characters" (chars=[]) and "stock" (stock entries, STOCK_KEYS)
SUPPORTS = {"no-new-characters", "stock", "hazards", "swings", "items", "pitches"}


def boot_game_args(option, chars, cpu=False, level6_addr=None):
    """boot-game's option {"captains": [a, b], "teams": [[up to 8], [up to 8]], "stadium": 0, "night": false,
    "level": 2, optional "lineups": [[9 names, null = filled] or null, ...], "positions": [{name: "CF"}, {}],
    "benches": [[up to 5 names, the first the DH], [...]], "dr": [the name who sits or null, ...]} ->
    (quickboot.apply's keyword arguments, the plain log line; a set lineup or bench adds a line per team after a
    newline). A bench gives args "bench" (per team its ids: quickboot keeps them off the teams, and build() makes
    them bench.apply's preset) and "dh" (per team bench.DHSEL: dr left out or null = bench.DH_PITCHER, the DH bats for
    whoever plays P; the DH's own name = bench.DH_OFF, no DH; one of the captain + 8 named = his id; never a Mii).
    build() pops "dh" before quickboot.apply. Names as the patcher window shows them: stock
    (sluggers_data.CHAR_NAMES; the captain list's "Yoshi" too) or chars' (the build's new characters and recolors), or
    ids. None: Mario vs Bowser. stadium / night: a stock Exhibition stadium at a time of day it has
    (quickboot.STADIUMS; 0 by day when left out). The teams' empty slots are quickboot's filler (FILLER, then every stock player). skip_intro stays off:
    quickboot's intro skip is every game's, not only the first. cpu: both teams CPU (p1_team None), else player 1
    plays the first team. level: the CPU level (quickboot.LEVELS: 1 Rookie .. 4 All-Star; left out: Veteran, as captain
    select's default); 5 (Superstar) and 6 (Legend) only with the level-5 feature: level6_addr = level5.level6()."""
    from sluggers_data import CHAR_NAMES
    option = option or {}
    names = {n.strip().lower(): i for i, n in enumerate(CHAR_NAMES[:STOCK_IDS]) if n.strip()}
    names["yoshi"] = names["green yoshi"]                           # the captain list's name for id 6
    names.update({str(c["name"]).strip().lower(): c["id"] for c in chars if c.get("name")})
    shown = {}

    def cid(ref):
        if isinstance(ref, int) or re.fullmatch(r"\s*(0x[0-9a-fA-F]+|\d+)\s*", str(ref)):
            i = int(str(ref), 0)
        else:
            assert str(ref).strip().lower() in names, f"start in a game: no character {ref!r} in this build"
            i = names[str(ref).strip().lower()]
        shown.setdefault(i, f"0x{i:02X}" if isinstance(ref, int) else str(ref).strip())
        return i
    caps = [cid(c) for c in option.get("captains") or ("Mario", "Bowser")]
    teams = [[cid(c) for c in t if c not in (None, "")] for t in (option.get("teams") or ([], []))]
    assert len(caps) == 2 and len(teams) == 2, "start in a game: two captains and two teams"
    import quickboot                                                # (stock stadiums only: the window's list)
    stadium, night = option.get("stadium", 0), bool(option.get("night", False))
    assert isinstance(stadium, int) and quickboot.stadium_ok(stadium, night), \
        f"start in a game: no stadium {stadium!r} {'at night' if night else 'by day'} in an Exhibition (quickboot.STADIUMS)"
    level = option.get("level", quickboot.DEFAULT_LEVEL)
    assert isinstance(level, int) and not isinstance(level, bool) and level in quickboot.LEVELS, \
        f"start in a game: no CPU level {level!r} (1 Rookie .. 4 All-Star, 5 / 6 with the CPU levels)"
    assert level in quickboot.STOCK_LEVELS or level6_addr is not None, \
        f"start in a game: CPU level {level} ({quickboot.level_name(level)}) needs the CPU levels feature (level-5)"
    args = dict(mode="game", captains=tuple(caps), teams=teams, stadium=stadium, night=night,
                p1_team=None if cpu else 0, skip_intro=False)
    if "level" in option:                                           # (left out: quickboot's default, as before)
        args.update(level=level, level6_addr=level6_addr)
    lineups = (list(option.get("lineups") or []) + [None, None])[:2]   # the teams' batting orders (None: the game's)
    positions = (list(option.get("positions") or []) + [{}, {}])[:2]   # and positions {player: "CF"}
    set_up = []
    if any(lineups):
        args["lineup"] = tuple([None if c in (None, "") else cid(c) for c in (lu or [])] for lu in lineups)
    if any(positions):
        args["positions"] = tuple({cid(c): str(p).upper() for c, p in (ps or {}).items()} for ps in positions)
    benches = [[c for c in (b or []) if c not in (None, "")]           # each team's bench, the DH first
               for b in (list(option.get("benches") or []) + [[], []])[:2]]
    drs = (list(option.get("dr") or []) + [None, None])[:2]         # who sits: null = the pitcher, the DH = no DH
    import bench as bench_mod
    if any(benches):
        mii = lambda i: 0x4D <= i <= 0x64                           # noqa: E731 (bench.py: no Mii benched or sitting)
        ids = [[cid(c) for c in b] for b in benches]
        assert all(len(b) <= bench_mod.NB for b in ids), f"start in a game: up to {bench_mod.NB} bench players a team"
        assert not any(mii(i) for b in ids for i in b), "start in a game: a Mii can't be on the bench"
        roster = [[caps[t]] + teams[t] for t in range(2)]
        dh = []
        for t in range(2):
            d = drs[t] if ids[t] else None
            if d in (None, ""):
                dh.append(bench_mod.DH_PITCHER)
                continue
            i = cid(d)
            assert i == ids[t][0] or i in roster[t], \
                f"start in a game: team {t + 1}'s DR ({d}) is the DH or one of the team's players"
            assert not mii(i), "start in a game: a Mii can't sit for the DH"
            dh.append(bench_mod.DH_OFF if i == ids[t][0] else i)
        args["bench"] = tuple(ids)
        args["dh"] = tuple(dh)
    for t in range(2):
        bits = []
        if lineups[t]:
            bits.append("batting order " + ", ".join("(filled)" if c in (None, "") else str(c).strip()
                                                    for c in lineups[t]))
        if positions[t]:
            bits.append("positions " + ", ".join(f"{str(c).strip()} {str(p).upper()}" for c, p in positions[t].items()))
        if "bench" in args and benches[t]:
            sel = args["dh"][t]
            bits.append("bench " + ", ".join(str(c).strip() for c in benches[t]) + " (DH " + str(benches[t][0]).strip()
                        + (": bats for whoever plays P" if sel == bench_mod.DH_PITCHER else
                           ": he sits, no DH" if sel == bench_mod.DH_OFF else f": bats for {shown[sel]}") + ")")
        if bits:
            set_up.append(f"{shown[caps[t]]}'s team: " + "; ".join(bits))
    who = "the computer plays both teams" if cpu else "you play the first team"
    return args, (f"start in a game: {shown[caps[0]]}'s team vs {shown[caps[1]]}'s team at "
                  f"{quickboot.stadium_name(stadium, night)}, CPU level {quickboot.level_name(level)}, {who}; once "
                  f"per power-on, then the game's own menus"
                  + "".join(f"\nstart in a game: lineup set, {x}" for x in set_up))   # (own lines: an edition
                                                                    # hides the first, which names the stadium)


def check_features(features):
    """Refuse unknown ids and missing requirements (naming them). Returns the set; NOT_IN_BUILD ids (the test
    builds' and Gecko codes' entries) are accepted and left out."""
    features = set(features) - set(NOT_IN_BUILD)
    unknown = features - ALL_FEATURES
    assert not unknown, f"unknown feature ids: {sorted(unknown)} (charbuild.FEATURES; not built: {sorted(NOT_IN_BUILD)})"
    missing = sorted(f"{f} needs {r}" for f in features for r in FEATURES[f].get("requires", ()) if r not in features)
    assert not missing, "missing features: " + "; ".join(missing)
    return features


def own_swing_off(chars):
    """custom-swings off: a new character whose own swing is one of ours by default (custom_swings.SWINGS "chars":
    Rosalina's Gravity Ball) keeps only its stats' stand-in id, another captain's stock swing (Rosalina's 12 is
    Bowser Jr.'s), under her own cut-in backdrop (Nick: "a custom background but then did bowser jr's swing"). It
    gets its template's stock swing instead (the stats row is the template's copy, so the key is dropped) and the
    template's cut-in backdrop to match (a stock captain's; else none). A "star swing" key of its own is degrade's.
    Returns the log lines."""
    import custom_swings, cutin_backdrop
    own = {cid for sw in custom_swings.SWINGS.values() for cid in sw["chars"]}
    out = []
    for c in chars:
        if c["id"] not in own or c.get("star swing") is not None or "star swing" not in c["stats"]:
            continue
        del c["stats"]["star swing"]
        cutin_backdrop.OWN_BACKDROP.pop(c["id"], None)
        tpl = c.get("template")
        if tpl in cutin_backdrop.STOCK_FILE:
            cutin_backdrop.BACKDROP_FROM[c["id"]] = tpl
        else:
            cutin_backdrop.BACKDROP_FROM.pop(c["id"], None)
        out.append(f"star swing   {c['name']}: its template's (0x{tpl:02X}) and its backdrop (custom-swings off)")
    return out


def degrade(c, on):
    """A definition's keys whose feature is off: left out (logged) instead of refusing the definition. A star pitch
    13-16, fielding ability 13 or custom star swing falls back to the template's (the new stats row is the template's
    copy with the definition's stats over it; for a custom swing, the definition's own "star swing" / "captain"
    stats if it has them); the other keys are ignored (their steps are off). Returns the lines to log."""
    left = []
    pitch = int(c["stats"].get("star pitch", 0))
    if pitch > STOCK_STAR_PITCHES:                  # ours (13-16) and new ones (17+): no module of theirs (Nick:
        made = new_pitches_configured()             # a lean beta imports none; OUR_PITCHES)
        path = made[pitch][0] if pitch in made else pitch     # a new one needs its path's feature
        if pitch >= FIRST_NEW_PITCH and pitch not in made:
            del c["stats"]["star pitch"]
            left.append(f"star pitch {pitch} (no star pitch creation has that id)")
        for f, ids in OUR_PITCHES.items():
            if path in ids and not on(f) and "star pitch" in c["stats"]:
                del c["stats"]["star pitch"]
                left.append(f"star pitch {pitch} ({f})")
    if int(c["stats"].get("fielding ability", 0)) == abilities.TANTRUM_TOSS and not on("star-solo-toss"):
        del c["stats"]["fielding ability"]
        left.append(f"fielding ability {abilities.TANTRUM_TOSS} (star-solo-toss)")
    if int(c["stats"].get("fielding ability", 0)) == abilities.CLAMBER_JUMP and not on("clamber-solo-jump"):
        c["stats"]["fielding ability"] = abilities.CLAMBER          # Clamber Jump off: stock Clamber
        left.append(f"fielding ability {abilities.CLAMBER_JUMP} -> {abilities.CLAMBER} (clamber-solo-jump)")
    if "custom-swings" in char_features(c) and not on("custom-swings"):
        left.append(f"star swing {c['star swing']} (custom-swings)")
        for k in ("star swing", "captain"):
            if k in c["own_swing"]:
                c["stats"][k] = c["own_swing"][k]
            else:
                c["stats"].pop(k, None)
        c["star swing"] = None
    for key, f in (("piranha_plants", "piranha-plants"), ("minimap_decoys", "minimap-decoys"),
                   ("batting_item", "fixed-items"), ("always_item", "fixed-items"), ("voice", "voices"),
                   ("item_ability", "item-ability"), ("hitting_ability", "item-ability"),
                   ("running_ability", "item-ability"), ("batter_star", "batter-star"),
                   ("chance_cheer", "chance-cheer")):
        if c.get(key) and not on(f):
            left.append(f"{key} ({f})")
    if c["id"] == 0x66 and not on("chance-cheer"):
        left.append("chance cheer (chance-cheer)")
    return [f"left out    {c['name']}: " + ", ".join(left) + ": feature off"] if left else []


def in_build(ids, valid, what, log):
    """`ids` (a list / tuple, or a dict: its keys) without the ones that are no character in this build (`valid`),
    the others logged: a helper's defaults name this mod's characters (the Lumas, Lubba, Rosalina, ...), which a
    partial roster may not have. Same type back."""
    left = [i for i in ids if i not in valid]
    if left:
        log.append(f"{what}: not in this build, left out: " + ", ".join(f"0x{i:02X}" for i in left))
    if isinstance(ids, dict):
        return {k: v for k, v in ids.items() if k in valid}
    return type(ids)(i for i in ids if i in valid)


def check_ids(written, valid):
    """The stray-reference check: every character id a table we write lists is a character in this build. A new id
    that isn't has model directory 0 (dirmap), and dir 0's "files" are other directories' (Nick's test-1.iso:
    Rosalina 0x81 on captain select without Rosalina, whose select bank came from dir 0 file 11 = dir 5 file 0, a
    stadium model, relocated as an animation bank by FUN_804f4f50: invalid read 0x98B70574). written: {table: ids}."""
    bad = {what: sorted({i for i in ids if i not in valid}) for what, ids in written.items()}
    bad = {what: ids for what, ids in bad.items() if ids}
    assert not bad, "ids that are no character in this build: " + "; ".join(
        f"{what}: {', '.join(f'0x{i:02X}' for i in ids)}" for what, ids in bad.items())
    return [f"ids checked  {len(written)} tables list only characters in this build"]


STOCK_STAR_PITCHES = 12        # the game's star pitches 1-12; ours are 13-16, new ones 17+


def char_features(c):
    """The feature ids a normalized definition needs (FEATURES "char_keys"): left out without them (degrade)."""
    need = set()
    pitch = int(c["stats"].get("star pitch", 0))
    need |= {f for f, ids in OUR_PITCHES.items() if pitch in ids}   # (16: King Boo's, stock row)
    if int(c["stats"].get("fielding ability", 0)) == abilities.TANTRUM_TOSS:
        need.add("star-solo-toss")
    if int(c["stats"].get("fielding ability", 0)) == abilities.CLAMBER_JUMP:
        need.add("clamber-solo-jump")
    if c.get("star swing") is not None:                 # (custom_swings only then: the lean beta, git-92)
        import custom_swings
        if int(c["star swing"]) in custom_swings.SWINGS:   # a custom swing's id
            need.add("custom-swings")
    return need


def build(chars, out, base="clean", dry_run=False, features=None, game=None, work=None, **flags):
    """base: "clean" (extracted/clean, the only base). The Extra Innings base is retired: Extra Innings' four
    characters are definitions with new ids (0x81-0x84), which would duplicate its own stock-slot copies
    (docs/stock-slot-migration.md). dry_run: stop before the output folder (nothing is written; a path saves
    the DOL as it stands there) and return the log.
    features: None = every step on (the build flags as passed); a set of FEATURES ids = only their steps. With a
    set, a build flag that isn't passed is on when its feature is (FLAG_FEATURES; stadium: stadiums/stadium10.json),
    and one passed is on only when its feature is too.
    menu_color: menu-color's colour (a menu_purple preset or "#RRGGBB"); None = purple.
    item_odds: item-odds' {item name or id: weight} (starbits_roulette.odds_ids); None = the roulette's own weights.
    ability_edits: ability-edits' {ability name: {field: value}} (ability_edits.check); None = the game's numbers.
    captains_option: the captains' roster and positions (captains.plan / check); None = the default 14.
    boot_game: boot-game's {"captains", "teams", "stadium", "night", "level"} (boot_game_args); None = Mario vs Bowser,
    filler teams, Veteran.
    boot_captain: boot-captain-select's {"stadium": 0, "night": false} (the game after captain select); None = Mario
    Stadium by day.
    seed: match-seed's seed (match_seed.parse: 0..0xFFFFFFFF replays); None = the console clock.
    replay_speed, replay_frames, replay_camera, freeze_percent: replay-slow-motion's, replay-camera's and
    contact-freeze's options (replay_tweaks.check); None = replay_tweaks.DEFAULTS.
    inning_seconds: inning-break-time's seconds (inning_break.check: 0.5..30); None / "stock" = stock.
    cpu_settings: cpu-settings' {setting: value} (cpu_settings.check); None = today's CPU numbers.
    pitches: star pitch creations (creators/pitches.py: checked .slgpitch dicts): each replaces the one of ours with its
    name (13..16), its speed, path numbers, windows and menu name. None: ours (today's bytes).
    swings: star swing creations (creators/swings.py: checked .slgswing dicts) on ids 16.. after ours (13..15); a
    character's "star swing" names one by its id. None: ours only (today's bytes).
    items: item creations (.slgitem dicts, creators/items.customs), in their order; they need koopaling-items. One
    named like one of ours edits it (same id); the others are new items, ids 14.. . A character's "batting_item"
    can name a new one.
    hazards: hazard creations (creators/hazards.py: checked .slghazard dicts, at most one per chassis) that replace
    that chassis' preset; None or a chassis left out = our preset (today's values, byte-identical).
    chars may hold stock entries ({"id", "name", "stock": True, STOCK_KEYS}: normalize_stock, SUPPORTS "stock").
    char_defaults: False = only the per-character keys in chars count: STOCK_DEFAULTS (King Boo's star pitch 16) and
    every helper's defaults (batter_star.STAR_CHARS, custom_swings' roster, batter_items.FIXED_ITEM / ALWAYS_ITEM,
    ...) are left out (the patcher's profile-only roster). True (default) = those, with the keys over them.
    game: the player's clean game folder (sys/main.dol, files/...; game_source.py); None = extracted/clean.
    work: the folder the game-derived files are read from (DERIVED, laid out as models/work; the patcher makes them
    from the player's game); None = models/work. Given, nothing of the default game or those files is read."""
    assert base == "clean", (f"base {base!r}: only the clean base is built (the Extra Innings base is retired, "
                             "docs/stock-slot-migration.md)")
    if features is not None:
        features = check_features(features)
        for flag, ids in FLAG_FEATURES.items():
            on = any(f in features for f in ids)
            if flag == "stadium":
                flags[flag] = (flags.get(flag) or ROOT / "stadiums/stadium10.json") if on else None
            else:
                flags[flag] = flags.get(flag, True) and on
    global _work
    prev = _work
    _work = WORK if work is None else Path(work)
    import captains, cutin_backdrop
    backdrops = (dict(cutin_backdrop.BACKDROP_FROM), dict(cutin_backdrop.OWN_BACKDROP), dict(cutin_backdrop.SLOTS),
                 dict(cutin_backdrop.PICTURES))
    swings, pitches = flags.pop("swings", None) or (), flags.pop("pitches", None) or ()
    cpu_edits = flags.pop("cpu_settings", None) or {}
    restore_swings = restore_pitches = restore_cpu = lambda: None   # noqa: E731
    # the star move modules (ours 13-16 and the creations) only when a build can use them: with none of MOVE_FEATURES
    # and no creations every star pitch past 12 is left out (degrade) and no custom swing is on, so their values
    # (backdrops, sounds, trails, labels) are never read; a lean download (the Characters Beta) doesn't have them
    if features is None or swings or pitches or any(f in features for f in MOVE_FEATURES):
        import creators.swings, creators.pitches
        restore_swings = creators.swings.configure(swings, flags.get("items") or ())   # SWINGS
        restore_pitches = creators.pitches.configure(pitches)       # the pitch modules' values
    if cpu_edits and (features is None or "cpu-settings" in features):   # the CPU levels tab's numbers:
        import cpu_settings                                         # the cpu_* constants for this build, and
        restore_cpu = cpu_settings.configure(cpu_edits)             # the table edits for level5.apply's swaps
    import copy
    first = copy.deepcopy((chars, flags))                           # (a second try starts from the same inputs)
    try:
        with game_source.use(game):
            while True:
                try:
                    log = _build(chars, out, dry_run=dry_run, features=features, **flags)
                    if cpu_edits and (features is None or "cpu-settings" in features):
                        import cpu_settings
                        log += cpu_settings.describe(cpu_edits)       # the CPU levels tab's numbers, as built
                    if ITEMS_SIZE != ITEMS_DEFAULT:
                        log.append(f"item section: 0x{ITEMS_SIZE:x} B (0x{ITEMS_DEFAULT:x} is too small for this "
                                   f"build's item code), data from 0x{DATA_BASE:08X}")
                    return log
                except Overflow as e:                               # the item code didn't fit: a bigger item
                    if e.base != ITEMS_BASE or ITEMS_SIZE + ITEMS_GROW > ITEMS_MAX:   # section, everything after it
                        raise                                       # moved up (sized by content)
                    items_layout(ITEMS_SIZE + ITEMS_GROW)
                    captains.configure(None)
                    (cutin_backdrop.BACKDROP_FROM, cutin_backdrop.OWN_BACKDROP, cutin_backdrop.SLOTS,
                     cutin_backdrop.PICTURES) = (dict(b) for b in backdrops)
                    chars, flags = copy.deepcopy(first)
    finally:
        items_layout(ITEMS_DEFAULT)                                 # (the next build starts from the default)
        restore_cpu()
        restore_swings()
        restore_pitches()
        for m in ("wendy_rings", "starbits_item"):                  # an edit of Wendy's rings / Star Bits (_build;
            if m in sys.modules:                                    # loaded only by a build with the items)
                sys.modules[m].configure(None)
        _work = prev
        captains.configure(None)                                    # this build's captains / backdrops (_build)
        (cutin_backdrop.BACKDROP_FROM, cutin_backdrop.OWN_BACKDROP, cutin_backdrop.SLOTS,
         cutin_backdrop.PICTURES) = backdrops


HAZARD_FEATURES = {"walker": "walking-bobombs", "shooter": "octoombas", "plant": "piranha-plants", "ghost": "mansion-day"}
# the features that read the star move modules' configured values (build(): creators.swings / creators.pitches)
MOVE_FEATURES = ("custom-swings", "pitch-vanish", "pitch-path", "pitch-items")
# our star pitches by feature (degrade, char_features; the modules' NEW_ID, not imported: a lean download has none):
# pitch_gravity_well 13, pitch_launch_star 14, pitch_bobomb_drop 15, pitch_vanishing_ball 16; creations from 17
OUR_PITCHES = {"pitch-path": (13, 14), "pitch-items": (15,), "pitch-vanish": (16,)}
FIRST_NEW_PITCH = 17                                                # pitch_new.FIRST_NEW


def new_pitches_configured():
    """pitch_new.NEW (the star pitch creations' ids 17.. -> (path, speed, name)), {} when pitch_new isn't loaded:
    creators.pitches.configure (build()) is what fills it, and it loads pitch_new."""
    return sys.modules["pitch_new"].NEW if "pitch_new" in sys.modules else {}


def item_args(customs, skip=frozenset()):
    """ice_item.apply's (and add_blue_textures' hues / ice) with item specs (creators.items.customs: thrown balls and
    lobs, new or ours edited) after the Koopalings': their base items, knockdowns, trail colours, dodge heights and
    freezes. skip: our items edited (theirs come from their specs)."""
    import koopa_items
    ice = 7 not in skip
    variants = koopa_items.VARIANTS + [(s["id"], s["base"]) for s in customs]
    customs = [s for s in customs if s["base"] in (1, 3)]           # the Fireball's / POW's hooks (the Shell: its own)
    return dict(variants=variants,
                knock=[g for g in koopa_items.KNOCK if not set(g[0]) & skip]
                + [((s["id"],), *s["slide"]) for s in customs if s["slide"]],
                hues={**{k: v for k, v in koopa_items.HUES.items() if k not in skip},
                      **{s["id"]: s["trail"] for s in customs if s["trail"] not in (None, "stock")}},
                jump=[koopa_items.JUMP] * (koopa_items.BILL not in skip)
                + [((s["id"],), s["dodge"]) for s in customs if s["dodge"] is not None],
                freeze=[(s["id"], s["freeze_frames"]) if s.get("freeze_frames") else s["id"]
                        for s in customs if s["effect"] == "freeze"], **({} if ice else {"ice": False}),
                **({"spin": [(s["id"], s["spin_frames"]) for s in customs if s["effect"] == "spin"]}
                   if any(s["effect"] == "spin" for s in customs) else {}))


def ring_pool(s):
    """A new ring item's spec -> its wendy_rings pool."""
    import wendy_rings
    g = s["ground"]
    return {"id": s["id"], "count": g["count"], "speed": g["wander"]["speed"], "wander": g["wander"]["range"],
            "twist": g["wander"]["twist"], "hop": g["hop"]["height"], "frames": g["hop"]["frames"],
            "radius": wendy_rings.RING_R if g["radius"] is None else g["radius"], "colors": g["colors"]}


def shower_pools():
    """Star moves' ring showers (star_shower.SHOWERS rows with a "rings:<item>" drop, creators.items.star_spawn):
    one pool per drop key, as many rings as its biggest shower (one batted ball at a time)."""
    import star_shower
    pools = {}
    for row in (star_shower.SHOWERS or {}).values():
        if str(row.get("drop", "")).startswith("rings:"):
            key = row["drop"]
            n = max(len(row["spots"]), pools[key]["count"] if key in pools else 0)
            pools[key] = dict(row["pool"], count=n, drop=key)
    return list(pools.values())


def wearing(customs, model, preset, skip=frozenset()):
    """The variant ids drawn with one of our ball models: the preset's (unless it's edited: then its spec says), and
    the items wearing the model. Just the preset: its id (the draw gate as before)."""
    ids = ((preset,) if preset not in skip else ()) + tuple(s["id"] for s in customs if s["model"] == model)
    return preset if ids == (preset,) else ids


def hazard_creations(hazards):
    """{chassis: hazard creation}: our presets (creators/hazards.py), each replaced by the profile's creation of that
    chassis (at most one each: one set of hooks per chassis)."""
    import creators.hazards
    out = creators.hazards.presets()
    seen = set()
    for c in hazards or ():
        ch = creators.hazards.chassis_of(creators.hazards.check(c))
        assert ch not in seen, f"two {ch} hazards ({c['name']}): one of each kind per build"
        seen.add(ch)
        out[ch] = c
    return out


def walker_args(c, stadium_def):
    """bobomb_hazard.apply's settings: the stadium's fence and outer radius (at the creation's angle), then the
    creation's values (its own outer radius over the stadium's, when it gives one)."""
    import creators.hazards, stadium_dimensions
    over = creators.hazards.walker_params(c)
    return {**stadium_dimensions.bobomb_args(stadium_def, over["angle"], over["time"]), **over}


def shooter_args(c, stadium_def):
    """octoomba_hazard.apply's settings: where the shooters stand (a creation's own spots: inside the warning track),
    then the creation's values."""
    import math, creators.hazards, stadium_dimensions
    spots, time = creators.hazards.shooter_spots(c), c["blocks"]["where"]["time"]
    if spots[0] == "track":
        args = stadium_dimensions.octoomba_args(stadium_def, spots[1], spots[2], time)
    else:
        args = {k: v for k, v in stadium_dimensions.octoomba_args(stadium_def, time=time).items() if k == "fence"}
        args["shooters"] = spots[1]
        fence = args.get("fence", stadium_dimensions.STOCK_FENCE)
        far = [f"({x:g}, {z:g})" for (x, _, z), _ in spots[1] if math.hypot(x, z) > fence - 3.0]
        assert not far, (f"{c['name']}: {', '.join(far)} {'is' if len(far) == 1 else 'are'} on or past the warning track "
                     f"(the fence is {fence:.1f} m out)")
    return {**args, **creators.hazards.shooter_params(c)}


def ghost_stadiums(c):
    """night_to_day.STADIUMS with Luigi's Mansion's day ghosts from the creation."""
    import creators.hazards, night_to_day
    return {sid: (dict(opt, day_ghosts=creators.hazards.ghost_day(c, opt["day_ghosts"])) if "day_ghosts" in opt
                  else opt) for sid, opt in night_to_day.STADIUMS.items()}


def _build(chars, out, grid_square=False, poltergust=False, dino_plants=False, captain=False,
           voices=False, preview=None, batter_depth=False, star_swings=False, stadium=None, star_bits=False,
           bench=False, bench_preset=None, dry_run=False, features=None, menu_color=None, item_odds=None,
           char_defaults=True, grid_order=None, captains_option=None, hazards=None, select_map=None, items=None,
           ability_edits=None, boot_game=None, boot_captain=None, seed=None, bench_dh=True, replay_speed=None,
           replay_frames=None, replay_camera=None, freeze_percent=None, replay_showcase=False, inning_seconds=None):
    """stadium: a stadiums/*.json definition path: a new stadium id 10 on the select map (new_stadium.py).
    select_map: stadium_map.prepare's {stadium: map block}: "new-stadium"'s select-map look (None = its own) and
    the stock stadiums' logos and words (stadium_map.apply_stock).
    features: a FEATURES id set (build() has checked it and set the flags from it), None = every step.
    grid_order: the patcher's "grid-order" option (grid_order.py: every square in reading order, each its color
    wheel's characters); None = GRID_SQUARES / GRID_LAYOUT (today's bytes).
    menu_color, item_odds, char_defaults, captains_option, boot_game, boot_captain, seed, replay_*, freeze_percent,
    inning_seconds: see build().
    replay_showcase: a test build's replay after every hit, cycling the 11 replay scripts (replay_showcase.py;
    build_test_replays.py); never a patcher feature."""
    koopa_on = features is None or "koopaling-items" in features   # new items first: a character's "batting_item"
    customs = []                                                    # may name one (checked in normalize*)
    if items:                                                       # (creators.items only then: a lean download
        import creators.items                                       # has no Create tab)
        customs = creators.items.customs(items, keep_ours=not koopa_on)   # new items: ids 14..;
    if customs or "batter_items" in sys.modules:                    # (loaded: a batting_item's check reads it)
        import batter_items
        batter_items.CUSTOM = {s["name"].strip().lower(): s["id"] for s in customs if not s["replaces"]}
    stock = normalize_stock(chars, char_defaults)                   # stock entries (no new ids)
    haz = {}                                                        # {chassis: creation}: presets, then the profile's
    if hazards or stadium or features is None or any(f in features for f in HAZARD_FEATURES.values()):
        haz = hazard_creations(hazards)                             # (read by the hazard steps and a new stadium's)
    import char_names                                               # the Toad Brigade's names and portraits only
    char_names.TOADS = features is None or "toad-brigade" in features   # with its feature (Nick, git-92)
    STOCK_ICONS.clear()
    STOCK_ICONS.update({k: v for k, v in ALL_STOCK_ICONS.items() if char_names.TOADS or k not in char_names.STOCK_RENAMES})
    renames, by_language = profile_names(stock, chars)             # stock renames; names per language
    runner_off = []                                                 # item ids that skip the runners' fall
    burn_off = []                                                   # thrown balls hit without the burning look
    new = [s for s in customs if not s["replaces"]]                 # ours edited keep theirs
    balls = [s for s in customs if "ground" not in s]               # thrown balls and lobs: the hooks' specs
    edited = frozenset(s["id"] for s in balls if s["replaces"])     # ours now on those paths
    item_steps = star_bits or bool(customs) or features is None or "fixed-items" in features   # (dropped's readers)
    dropped = frozenset()                                           # item-engine without koopaling-items: the six
    if item_steps and not koopa_on:                                 # not chosen: unreachable, their
        import koopa_items as _ki                                   # preset branches, colours and models out
        dropped = frozenset(v for v, _ in _ki.VARIANTS) - {s["id"] for s in customs}
    skip = edited | dropped
    ground = {s["replaces"]: s for s in customs if "ground" in s and s["replaces"]}   # Star Bits / Wendy edited
    ring_items = [s for s in customs if "ground" in s and not s["replaces"]]   # new ring items: their own pools
    if star_bits or ground:                                         # (read by the Star Bits steps only)
        import wendy_rings, starbits_item
        wendy_rings.configure(ground["wendy"]["ground"] if "wendy" in ground else None)
        starbits_item.configure(ground["star-bits"]["ground"] if "star-bits" in ground else None)
    chars = normalize(chars)                                        # new characters
    log = [f"base: clean game ({game_source.root()})"]
    if not chars:                                                   # no new characters: new-ids and what needs it
        left = sorted((ALL_FEATURES if features is None else features) & NEEDS_NEW_IDS)   # are left out
        features = (ALL_FEATURES if features is None else frozenset(features)) - NEEDS_NEW_IDS
        grid_square = captain = voices = bench = False
        preview = None
        log.append("no new characters: " + (f"left out {', '.join(left)}" if left else "stock roster"))
    assert features is None or "new-ids" in features or not chars, \
        f"{len(chars)} new characters with new-ids off (a build with none: chars=[])"
    # the characters in this build: every table we write may list only these (check_ids, before the output)
    valid = frozenset(range(STOCK_IDS)) | {c["id"] for c in chars}
    import captains                                                 # 9. the captains whose character is built
    left = captains.configure(valid if captain else (),             # (captains.ALL_CAPTAINS or the option; a
                              captains_option if captain else None, stock + chars, char_defaults)   # replaced slot
    if left and captain:                                            # keeps its stock captain)
        log.append("captains: " + ", ".join(f"{c['index']} {c['name']}" for c in captains.NEW_CAPTAINS)
                   + "; not in this build: " + ", ".join(f"{c['name']} (0x{c['id']:02X})" for c in left))
    log += captains.logo_lines()                                    # the player's team logos
    written = {}                                                    # {table: character ids} for check_ids
    import cutin_backdrop                                           # own / borrowed cut-in backdrops of characters
    cutin_backdrop.BACKDROP_FROM = in_build(cutin_backdrop.BACKDROP_FROM, valid, "cut-in backdrops", log)
    cutin_backdrop.OWN_BACKDROP = in_build(cutin_backdrop.OWN_BACKDROP, valid, "own cut-in backdrops", log)
    on = (lambda f: True) if features is None else features.__contains__   # noqa: E731
    engine_on = on("koopaling-items") or on("item-engine")          # the item machinery (ids 8+)
    for ch, f in HAZARD_FEATURES.items():                           # a hazard's effect may need another feature
        if not on(f):                                               # (freeze: freeze-on-hit's ice block)
            continue
        import creators.hazards
        need = sorted(n for n in creators.hazards.needs(haz[ch]) if not on(n))
        assert not need, (f"{haz[ch]['name']}: its {haz[ch]['blocks']['effect']['kind']} needs "
                          f"{', '.join(need)} (Freeze on hit) turned on")
    for c in chars:                                                 # keys of a switched-off feature: left out
        log += degrade(c, on)
    custom_swings_on = star_swings and on("custom-swings")          # star_swings: both of these
    if not custom_swings_on:                                        # a character's own custom swing is off (the beta)
        log += own_swing_off(chars)                                 # its template's swing and backdrop, not the stand-in
    vanish_on = star_swings and on("pitch-vanish")
    for e in stock:                                                 # (and their build flag, for stock entries)
        log += degrade(e, lambda f: on(f) and (f not in ("custom-swings", "pitch-vanish") or star_swings))
    entries = chars + stock                                         # every per-character key: the steps' helpers
    #                                                                 (new characters first: Boom Boom's backdrop)
    pitches = {int(e["stats"].get("star pitch", 0)) for e in entries}   # 18-18d: the star pitches in this build
    new_pitches = {p: new_pitches_configured()[p] for p in pitches if p in new_pitches_configured()}   # a new one
    pitches |= {path for path, _, _ in new_pitches.values()}        # (17-20) flies one of ours: its module
    star_moves = custom_swings_on or any(p > STOCK_STAR_PITCHES for p in pitches)   # ours / creations in this build
    if star_moves:                                                  # (the steps below read pitch_new's layout)
        import pitch_new
    max_id = max([c["id"] for c in chars] + [STOCK_IDS])            # the highest id this build uses (names, art)
    n_rows = ID_BOUND + 1 if chars else STOCK_IDS + 1               # the per-id tables' rows: every id (Phase 1)
    game = game_source.root()                                       # the player's game (build(game=))
    dol = Dol(game / "sys/main.dol")
    dol.trace = {}                                                  # who wrote what (gecko_map)
    MOVES.clear()
    code, data = Space(CODE_BASE, DINO_CODE), Space(DATA_BASE, DATA_LIMIT)
    item_code = Space(ITEMS_BASE, ITEMS_BASE + ITEMS_SIZE)
    if features is not None:
        log.append(f"features: {len(features)} of {len(FEATURES)} (off: {', '.join(sorted(ALL_FEATURES - features))})")
    for c in chars:
        if c["chemistry_skipped"]:
            log.append(f"chemistry    {c['name']}: not in this build, skipped: {', '.join(c['chemistry_skipped'])}")
    voice_brsar, voice_ids = voice_files()
    for c in chars:                                                 # per-character table values
        if c["table_stats"]:
            log.append(f"table stats  0x{c['id']:02X} {c['name']}: " +
                       ", ".join(f"{k} {v}" for k, v in c["table_stats"].items()))
    if poltergust:                                                  # 0.
        log += poltergust_dol(dol)
    if custom_swings_on:                                            # 0b. custom star swings' stats
        log += star_swing_stats(dol, entries, later={e["id"] for e in stock if e["star swing"] is not None},
                                defaults=char_defaults, valid=valid)
    if star_moves:                                                  # 0b'. star move creations' backdrops (their
        log += move_backdrops(entries, custom_swings_on, on("cutin-backdrops"))   # swings' / pitches' 13..)
    _ice = None                                                     # extra particle slots: this build's requests
    if star_bits or star_moves or "ice_item" in sys.modules:        # only (git-95's trails ask before ice_item;
        import ice_item as _ice                                     # a build without either asks for none)
        _ice.reset_slots()
    trail_swings, trail_pitches = {}, {}                            # 0b''. star trail colours: slots asked for
    if star_moves:                                                  # before the items step (ice_item)
        import gravity_ball as _gb, pitch_gravity_well as _gw, custom_swings as _cs
        from creators import star_trail as _st
        trail_swings = {sid: hl for sid, hl in _gb.TRAIL_COLOURS.items() if custom_swings_on and sid in _cs.SWINGS}
        trail_pitches = {pid: hl for pid, hl in _gw.TRAIL_COLOURS.items() if pid in pitches or pid in new_pitches}
    for hl in list(trail_swings.values()) + list(trail_pitches.values()):
        _ice.request_slot(_st.key(hl), _st.STAR_SLOT, *hl)
    if trail_swings:                                                # a byte per coloured swing, filled below
        _gb.TRAIL_COLOURS, _gb.TRAIL_DATA = trail_swings, data.put(bytes(len(trail_swings)), 4)
    if captain:                                                     # 0c. replaced stock captains: no captain
        log += captains.stat_edits(dol)                             #     flag / star moves (with captains on)
    moves_kept = captains.kept_star_moves()                         # (the ones keeping their slot: new characters
    if on("stock-balance"):                                         #  built on them copy them cleared)
        log += stock_stat_edits(dol)                                # 0c. stock stat + chemistry edits
    if ability_edits and on("ability-edits"):                       # 0c'. the abilities' numbers (Nick, git-a7)
        import ability_edits as ability_edits_mod
        log += ability_edits_mod.apply(dol, ability_edits)
    elif ability_edits:
        log.append("ability edits left out (ability-edits off)")
    stock_templates, more, table_templates = stock_rows(dol, stock)  # 0d. stock entries' rows (King Boo's pitch 16)
    log += more
    for s in moves_kept:                                            # new characters on Wario: his row as edited
        stock_templates[s] = star_move_edits(stock_templates.get(s) or dol.read(
            0x806CE9A0 + STATS_HEADER + s * STATS_ROW, STATS_ROW), s)

    # 1. arena low: DATA_LIMIT until the data section is placed, then its end (everything we place sits below it);
    #    put back at the end when the build places nothing (no characters and no feature with code or data)
    new_lo = DATA_LIMIT
    stock_arena = {a: dol.u32(a) for site in ARENA_LO_SITES for a in site}
    for lis_addr, addi_addr, old_lo in ((0x80595FC4, 0x80595FC8, 0x6E80), (0x8059606C, 0x80596070, 0x6E80),
                                        (0x80596014, 0x80596018, 0x4E80)):
        assert dol.u32(addi_addr) & 0xFFFF == old_lo and dol.u32(lis_addr) & 0xFFFF == 0x807B
        dol.w32(lis_addr, (dol.u32(lis_addr) & 0xFFFF0000) | ha(new_lo))
        dol.w32(addi_addr, (dol.u32(addi_addr) & 0xFFFF0000) | lo(new_lo))

    # 1c. the select grid's order: GRID_SQUARES / GRID_LAYOUT, or the profile's grid-order (grid_order.to_tables:
    #     new squares, layout, the wheel host of each new character on a stock square, reordered stock wheels)
    grid_squares, grid_layout, family_order, force_grid, placed = GRID_SQUARES, GRID_LAYOUT, {}, False, {}
    if grid_order is not None and grid_square:
        import grid_order as grid_order_mod
        tables = grid_order_mod.to_tables(grid_order, dol, stock + chars)      # (stock entries: their renames)
        force_grid = tables["force_grid"]                                       # stock squares reordered, no new one
        grid_squares, grid_layout, family_order = tables["squares"], tables["layout"], tables["family_order"]
        placed = tables["wheels"]                                     # (on a stock square's wheel: own_squares)
        for c in chars:
            c["wheel"] = placed.get(c["id"], c["wheel"])
        log.append(f"grid order: {len(grid_squares)} new squares, {len(family_order)} reordered wheels (profile)")
        for c in sorted(chars, key=lambda c: c["id"]):             # (a player's Dry Bowser: one of Bowser's colors)
            if c["id"] in placed:
                log.append(f"grid order: {c['name']} (0x{c['id']:02X}) on "
                           f"{grid_order_mod.display_name(placed[c['id']], stock + chars)}'s color wheel")
    if grid_square and chars:                                       # "own_square": a square of its own (a .sluggie
        grid_squares, grid_layout, owns = own_squares(chars, grid_squares, grid_layout, placed)   # model, New char.)
        log += owns
    if grid_square and chars:                                       # a recolor of an added character: its base's
        grid_squares = join_squares(grid_squares, chars)            # square ("square", recolor.make)
    if grid_square and chars:                                       # a character whose template's wheel is full
        import wheel_overflow                                       # gets its own square, or with the grid full a
        extra, joins, notes = wheel_overflow.place(chars, grid_squares, dol)   # new square's wheel (git-a3);
        if joins:                                                   # WheelFull when those are full too
            grid_squares = [list(sq) for sq in grid_squares]
            for i, name in joins:
                grid_squares[i].append(name)
        if extra:
            grid_squares = [*grid_squares, *extra]
            grid_layout = [list(row) for row in grid_layout]
            for sq in extra:
                if len(grid_layout[-1]) >= len(grid_layout[0]):
                    grid_layout.append([])
                grid_layout[-1].append(sq[0])
        log += [f"wheel full   {n}" for n in notes]

    # 2. tables
    pairs = list(hilo_refs.pairs())
    at = {}
    squares, missing = resolve_squares(chars, grid_squares) if grid_square else ([], [])
    on_square = {cid for sq in squares for cid in sq if cid > STOCK_IDS}
    if missing:
        log.append("grid squares: not in this build: " + ", ".join(missing))
    grid = gridcells.plan(chars, grid_squares, force_grid) if grid_square else None   # 7. None: the stock grid
    if grid_square and not grid:
        log.append("grid squares: none in this build: the stock grid")
    for name, addr, size, header in (TABLES if chars else ()):     # (no characters: the stock tables stay)
        at[name] = data.put(extended_rows(dol, name, addr, size, header, chars, n_rows, on_square,
                                          stock_templates if name == "stats" else table_templates.get(name)))
        n = relocate(dol, pairs, addr, header + STOCK_IDS * size, at[name], name=name, row=size)
        log.append(f"{name:12} {n:3} refs -> 0x{at[name]:08X}")
    if chars:                                                       # the charge effects read the scale tables
        import charge_scale                                         # from a stack copy: point them at the new ones
        log += charge_scale.apply(dol, item_code, at)               # item section: the main code space is full
    # color wheels past 6 (the variant slot, selector byte 5, of a character not on a square) need wheel7
    big_wheels = bool(chars) and max(data.blob[at["selector"] - DATA_BASE + c["id"] * 8 + 5] for c in chars) >= 6
    big_wheels = big_wheels or any(len(sq) > gridcells.WHEEL_MAX for sq in squares)   # (a grid-order square past 6)
    # roster hook list (step 3a): characters on a grid square get their wheel from the square
    new_ids_list = chars and data.put(bytes(c["id"] for c in chars if c["id"] not in on_square) + bytes([STOCK_IDS]),
                                      align=4)                    # (ends with 0x65, never a character)
    written.update({"templates and color wheels": [i for c in chars for i in (c["template"], c["wheel"])],
                    "roster wheel list": [c["id"] for c in chars if c["id"] not in on_square],
                    "chemistry": [i for c in chars for i in c["chemistry"]],
                    "grid squares": sorted({cid for sq in squares for cid in sq})})

    # 2b. per-character models. The model manager loads model id M from dt_na.dat directory
    #     M + 0x12 into a free slot, so a new id with its own model needs (a) its own directory:
    #     a copy of the template's file records with the changed model files pointing at copies
    #     appended to dt_na.dat, added to a relocated, longer directory table; (b) the three
    #     `addi r4,rN,0x12` directory computations replaced by a lookup (stock ids keep id + 0x12);
    #     (c) the per-model-id runtime array at 0x80709408 (101 entries) relocated and extended.
    toc_ptrs = dtna_toc.dir_pointers(dol)
    dat_end = os.path.getsize(game / "files/dt_na.dat")
    cursor = dat_end + (-dat_end % 32)
    appended = []                                            # (dt_na offset, bytes)
    if poltergust:                                                  # 0. the prop entry
        import build_poltergust as bp
        entry = bp.ENTRY.read_bytes()
        rec = bp.toc_record(dol, bp.DIR, 5)
        for lang in range(3):                                # both length words and the offset
            dol.w32(rec + 16 * lang + 4, len(entry))
            dol.w32(rec + 16 * lang + 8, cursor)
            dol.w32(rec + 16 * lang + 12, len(entry))
        appended.append((cursor, entry))
        cursor += len(entry) + (-len(entry) % 32)
        # Luigi's animation bank with seq 39 (special catch) = his dive, on its own track copies
        # (a shared record would be relocated twice by the ANM loader); appended and repointed
        rec6 = bp.toc_record(dol, bp.DIR, 6)
        _, length, off, _ = struct.unpack(">4I", dol.read(rec6, 16))
        with open(game / "files/dt_na.dat", "rb") as f:
            f.seek(off)
            bank = bp.dive_catch_bank(f.read(length), POLTERGUST_CATCH_SEQ)
            if POLTERGUST_STAND_DIVE:                                    # his dive (seq 19) stands too
                bank = bp.dive_catch_bank(bank, POLTERGUST_CATCH_SEQ, target=bp.DIVE_SEQ)
        for lang in range(3):
            dol.w32(rec6 + 16 * lang + 4, len(bank))
            dol.w32(rec6 + 16 * lang + 8, cursor)
            dol.w32(rec6 + 16 * lang + 12, len(bank))
        appended.append((cursor, bank))
        cursor += len(bank) + (-len(bank) % 32)
    # the icon bank the icon steps build on: the game's own, with Extra Innings' layout (private pages 0x92 / 0x93,
    # relocated source tables; icon_bank.base_bank, git-a3), which the clean bank doesn't have (the output stage
    # moves it to the end)
    if chars:                                                       # (no characters: the stock bank stays)
        import icon_bank
        bank = icon_bank.base_bank(game)
        appended.append((cursor, bank))
        for lang in range(3):
            dol.write(ICON_RECORD + lang * 16 + 4, struct.pack(">III", len(bank), cursor, len(bank)))
        cursor += len(bank) + (-len(bank) % 32)
        log.append("icon bank (dir 119 file 2) from the clean game")
    dir_ptrs = list(toc_ptrs)
    # id -> directory, and directory -> the directory whose per-model data applies (revmap): halfwords, since the
    # 61 recolors that fill every stock color wheel took the directories past 255 (172 stock + one per own model;
    # the dt_na layer takes the directory as a word: FUN_80397f6c -> FUN_802c5fd0 `slwi r3,r3,2`)
    dirmap = [i + MODEL_DIR_BASE for i in range(STOCK_IDS)] + [0] * (n_rows - STOCK_IDS)
    own_f14 = {}                                                    # id -> its own directory's file 14
    for c in chars:
        dirmap[c["id"]] = c["template"] + MODEL_DIR_BASE
        if not c["model_overlay"]:
            assert not c["bat"], f"{c['name']}: a bat needs the character's own model directory"
            continue
        files = model_files(c)
        tdir = c["template"] + MODEL_DIR_BASE
        n_files = len(dtna_toc.toc(dol)[tdir])
        records = bytearray(dol.read(toc_ptrs[tdir], n_files * dtna_toc.FILE_RECORD))
        # Every file gets its own copy, not only the changed model files: no two playable
        # characters share a file offset in the stock game, and the loaders relocate some files in
        # place (ANM banks: FUN_804f4f50). Sharing the template's copies made same-template
        # characters invisible or misplaced when they were loaded together (Koopalings, Lumas).
        with open(game / "files/dt_na.dat", "rb") as f:
            # "bat": the character's own bat as file 2 ({"dir": N}: stock dir N's bat, copied;
            # {"file": path}: a bat entry such as make_bat.py's); it attaches at the template's nodes
            if c["bat"] and "dir" in c["bat"]:
                off, length = dtna_toc.toc(dol)[int(c["bat"]["dir"])][2]
                assert length and off + length <= dat_end, f"{c['name']}: bat dir {c['bat']['dir']}"
                f.seek(off)
                files[2] = f.read(length)
            elif c["bat"]:
                files[2] = asset(c["bat"]["file"]).read_bytes()
            for index, (off, length) in enumerate(dtna_toc.toc(dol)[tdir]):
                if index not in files and length:
                    assert off + length <= dat_end, f"{c['name']}: file {index} is appended by this build"
                    f.seek(off)
                    files[index] = f.read(length)
            # A new model on the template's low-detail block (file 1 left out: a .sluggie or texture pack of file 0,
            # Ice Bro; or kept stock by an import) draws the template wherever the game uses the far-away model:
            # fielders, TV cameras, a close play's cut (NSL's Characters Beta video). Its own detailed block stands
            # in, as the Lumas and Extra Innings' Luma ship. Not for new textures on the template's model (a recolor,
            # a texture pack): the template's low-detail block has no textures of its own (it draws with file 0's), and
            # two copies of a big detailed block overflow the actor's 850 KB model heap (fielder-count.md; Peach, Daisy,
            # Wario, the Kongs... crashed at load in 3.0).
            tmpl = []
            for off, length in dtna_toc.toc(dol)[tdir][:2]:
                f.seek(off)
                tmpl.append(f.read(length))
            if 0 in files and files[0] != tmpl[0] and files.get(1) == tmpl[1] \
                    and not textures_only(files[0], tmpl[0]):
                files[1] = files[0]
                log.append(f"{c['name']}: its far-away model (file 1) is its detailed one (the "
                           f"template's was left in)")
        for index, blob in sorted(files.items()):
            appended.append((cursor, blob))
            for lang in range(3):
                struct.pack_into(">III", records, index * dtna_toc.FILE_RECORD + lang * 16 + 4,
                                 len(blob), cursor, len(blob))
            cursor += len(blob) + (-len(blob) % 32)
        dirmap[c["id"]] = len(dir_ptrs)
        dir_ptrs.append(data.put(bytes(records), align=4))
        c["model_dir"] = dirmap[c["id"]]
        own_f14[c["id"]] = files.get(14)                            # (bank8_share: its file 14's bytes)
    for sid, blocks in (STOCK_MODELS if on("toad-brigade") else {}).items():   # replace stock ids' model files
        sdir = sid + MODEL_DIR_BASE
        stock_files = dtna_toc.toc(dol)[sdir]
        for index, path in blocks.items():
            blob = asset(path).read_bytes()
            assert index == 2 or len(blob) == stock_files[index][1],                 f"0x{sid:02X} file {index}: not the stock file's size"      # body models keep the layout
            appended.append((cursor, blob))
            for lang in range(3):
                dol.write(toc_ptrs[sdir] + index * dtna_toc.FILE_RECORD + lang * 16 + 4,
                          struct.pack(">III", len(blob), cursor, len(blob)))
            cursor += len(blob) + (-len(blob) % 32)
        log.append(f"stock model 0x{sid:02X}: files {sorted(blocks)} replaced (dir {sdir})")
    import cutin_backdrop                                           # 8. own cut-in backdrops (dir 0x9F files 24..)
    if on("cutin-backdrops"):
        records, extra, cursor = cutin_backdrop.backdrop_directory(dol, game / "files/dt_na.dat", cursor)
        appended += extra
        dir_ptrs[cutin_backdrop.BACKDROP_DIR] = data.put(records, align=4)
        log.append("own cut-in backdrops: " + ", ".join(f"0x{c:02X} (0x{s:02X}'s, hue {d:+d})"
                                                       for c, (s, d) in cutin_backdrop.OWN_BACKDROP.items()))
    if stadium:                                                     # 12a. new stadium: its directories
        import new_stadium                                          # (a list: a second new stadium, id 11, too)
        stadium_defs = [new_stadium.load_definition(p) for p in (stadium if isinstance(stadium, (list, tuple))
                                                                   else [stadium])]
        assert 1 <= len(stadium_defs) <= len(new_stadium.NEW_IDS), "one or two new stadiums"
        for i, d in enumerate(stadium_defs):                        # ids by position: 10, then 11
            d["id"] = new_stadium.NEW_IDS[i]
        if select_map is not None:                                  # the map look (stadium_map.prepare)
            import stadium_map
            stadium_defs[0] = stadium_map.merge(stadium_defs[0], select_map, log)
        own_haz = {}
        for d in stadium_defs:
            for e in d.get("hazards") or ():                        # the stadium's own hazards (creators/stadium.py
                import copy, creators.hazards                       # definition()): a file of its own or our preset,
                src = e["hazard"]                                   # at the times the stadium lists it
                h = copy.deepcopy(creators.hazards.load(ROOT / src if Path(src).suffix else src))
                h["blocks"]["where"]["time"] = e["time"]
                ch = creators.hazards.chassis_of(h)
                assert ch not in own_haz, (f"both new stadiums have their own {ch} hazard ({own_haz.get(ch)}, "
                                           f"{h['name']}): one of each kind per game for now")
                own_haz[ch] = h["name"]
                log.append(f"stadium: {ch} {h['name']} ({e['time']})" +
                           (f" in place of the profile's {haz[ch]['name']}" if any(x is not h and x is haz[ch]
                                                                                  for x in (hazards or ())) else ""))
                haz[ch] = h
        for i, d in enumerate(stadium_defs):
            for key, f in (("octoombas", "octoombas"), ("bobombs", "walking-bobombs"), ("dimensions", "dimensions")):
                if not on(f) and d.get(key):                        # its hazards / dimensions switched off
                    stadium_defs[i] = d = {k: v for k, v in d.items() if k != key}
                    log.append(f"stadium: {key} left out ({f} off)")
        import creators.hazards
        for h in hazards or ():                                     # a used walker / shooter with nowhere to go
            ch = creators.hazards.chassis_of(h)
            key = {"walker": "bobombs", "shooter": "octoombas"}.get(ch)
            if key and not any(d.get(key) for d in stadium_defs):
                names = " or ".join(str(d.get("name", "")).split(" (")[0] for d in stadium_defs)
                log.append(f"note: {h['name']} isn't in the game: your stadium {names} has no "
                           f"{'walkers' if ch == 'walker' else 'shooters'}. Tick one in the stadium's Hazards box, "
                           "or use our stadium.")
        for key in ("octoombas", "bobombs"):                        # one set of hooks per hazard kind
            assert sum(bool(d.get(key)) for d in stadium_defs) <= 1, \
                f"both new stadiums have {key}: only one of them can, for now"
        stadium_def = stadium_defs[0]
        more, extra, cursor = new_stadium.add_directories(dol, data, dir_ptrs,
                                                          stadium_defs if len(stadium_defs) > 1 else stadium_def,
                                                          game / "files/dt_na.dat", cursor)
        log += more
        appended += extra
        import stadium_pregame                                      # its own pre-game loading pictures
        for d in stadium_defs:
            more, extra, cursor = stadium_pregame.add_files(dol, data, dir_ptrs, d, game / "files/dt_na.dat", cursor)
            log += more
            appended += extra
    if select_map:                                                  # 12b. the stock stadiums' map looks
        import stadium_map
        more, extra, cursor = stadium_map.apply_stock(dol, data, dir_ptrs, select_map, game / "files/dt_na.dat",
                                                      cursor, appended, code, stadium_def if stadium else None)
        log += more
        appended += extra
    if on("mansion-day"):                                           # 12a. Luigi's Mansion's day archive, package
        import night_to_day
        more, extra, cursor = night_to_day.add_files(dol, dir_ptrs, cursor, data=data)
        log += more
        appended += extra
    import char_names                                               # 13. character names (dir 121 file 5)
    if on("new-ids"):                                               # (the names: part of new-ids)
        more, extra, cursor, _ = char_names.add_names(dol, data, dir_ptrs, chars, game / "files/dt_na.dat", cursor,
                                                      renames, by_language)
        log += more + char_names.patch_code(dol, code, max_id)
        appended += extra
        if char_names.TEXT_RENAMES:                                 # (none since Clamber Jump is its own ability)
            more, extra, cursor = char_names.rename_text(dol, data, dir_ptrs, game / "files/dt_na.dat", cursor,
                                                         appended)
            log += more
            appended += extra
    if bench:                                                       # 19a. the bench's "Substitute" pause option
        import bench as bench_mod
        assert grid_square, "the bench's roster slot is laid out on the 12x5 select screen (grid_square)"
        more, extra, cursor, bench_msg = bench_mod.add_message(dol, data, dir_ptrs, game / "files/dt_na.dat", cursor,
                                                               appended)
        log += more
        appended += extra
    if on("level-5"):                                               # 19b. "Superstar" / "Legend Level" lines
        import level5, level5_menu                                  # (dir 121 file 4, every language), and its
        level5.alloc(data)                                          # the flag (and the menu's Level 6 byte)
        more, extra, cursor, level5_msg, level6_msg = level5_menu.add_message(dol, data, dir_ptrs,
                                                                              game / "files/dt_na.dat", cursor, appended)
        log += more + level5_menu.apply(dol, code, level5_msg, level6_msg, level5.level6(),
                                                 level5.chal_pick(), level5.chal_match())   # 5th and 6th buttons
        appended += extra
    if chars or dir_ptrs != list(toc_ptrs):                         # (no directory added or replaced: stays)
        new_dirs = data.put(struct.pack(f">{len(dir_ptrs)}I", *dir_ptrs), align=4)
        n = relocate(dol, pairs, dtna_toc.DIR_TABLE, dtna_toc.N_DIRS * 4, new_dirs, name="dt_na directories", row=4)
        log.append(f"dt_na dirs   {n:3} refs -> 0x{new_dirs:08X} ({len(dir_ptrs)} directories)")
    if chars:                                                       # (no characters: none of this)
        dirmap_addr = data.put(struct.pack(f">{len(dirmap)}H", *dirmap), align=4)
        # dir -> the directory whose per-model data applies (a new directory -> its template's)
        revmap = list(range(len(dir_ptrs)))
        for c in chars:
            if c.get("model_dir"):
                revmap[c["model_dir"]] = c["template"] + MODEL_DIR_BASE
        revmap_addr = data.put(struct.pack(f">{len(revmap)}H", *revmap), align=4)
        # its rows as stock memory starts them (bss, 0): the stock init code (0x80155624) fills every stock row itself
        # but the ones it leaves at 0 (Petey: no bat, no gloves; Monty Mole: no gloves); a (1, 2, 4) prefill gave
        # Petey a bat in every build with new characters (Nick, fences-2). A new id gets what the init code gives its
        # template, and a bat of its own is requested (Honey Queen, on Petey's model, holds her honey dipper)
        rows = [(0, 0, 0)] * n_rows
        for c in chars:
            req = MODEL_REQUESTS.get(c["template"], (1, 2, 4))
            rows[c["id"]] = (1, 2, 4) if c.get("bat") and not req[0] else req
        handles = data.put(b"".join(struct.pack(">III", *r) for r in rows), align=4)
        n = relocate(dol, pairs, MODEL_HANDLES, STOCK_IDS * MODEL_HANDLE_SIZE, handles, name="model handles",
                     row=MODEL_HANDLE_SIZE)
        log.append(f"model handles {n:2} refs -> 0x{handles:08X}")
        # the winner scene (FUN_80152dd4) spills the table's high half to the stack (lis r0 at 0x80152E4C, stw 0x8C(r1),
        # lwz + subi at 0x80152EA4), so the pair scan misses it: it read past the stock 101 rows for new ids and
        # requested garbage props (the empty prop file: invalid read 0x8 at 0x804FF694 when a new character won, Nick)
        patch_word(dol, 0x80152E4C, 0x3C008071, Asm(0x80152E4C).lis("r0", ha(handles)).assemble_word())
        patch_word(dol, 0x80152EA4, 0x38849408, Asm(0x80152EA4).addi("r4", "r4", lo(handles)).assemble_word())
        log.append(f"model handles: winner scene 0x80152E4C / 0x80152EA4 -> 0x{handles:08X}")
        # ... and its size table the same way (lis r0 0x80152E6C, or r4,r0 / subi 0x80152EB4, stw 0x90(r1)): new ids
        # got a garbage scale past the stock 101 rows (Nick: a giant Koopaling in the winner scene)
        patch_word(dol, 0x80152E6C, 0x3C008063, Asm(0x80152E6C).lis("r0", ha(at["sizescale"])).assemble_word())
        patch_word(dol, 0x80152EB4, 0x3884EB50, Asm(0x80152EB4).addi("r4", "r4", lo(at["sizescale"])).assemble_word())
        log.append(f"sizescale: winner scene 0x80152E6C / 0x80152EB4 -> 0x{at['sizescale']:08X}")
    if star_bits:                                                   # 12a. Star Bit model, item slot 0x2A x4
        import starbits_model
        import wendy_rings                                          # + Wendy's ring block in the slot's tail
        import lemmy_balls, bullet_bill                             # + Lemmy's circus ball, the Bullet Bill after it
        ring_blob = (ROOT / "models/work/ring/prop.bin").read_bytes()
        assert wendy_rings.RING_OFF + len(ring_blob) <= lemmy_balls.OFF, "ring block runs into Lemmy's ball"
        import own_models                                           # + the players' own models after them
        own_placed = own_models.plan([s for s in customs if s.get("model") == "own"], game) if engine_on else []
        sb_log, sb_appended = starbits_model.apply(dol, game / "files/dt_na.dat", extra=[
            (wendy_rings.RING_OFF, ring_blob), (lemmy_balls.OFF, (ROOT / "models/work/lemmy_ball/prop.bin").read_bytes()),
            (bullet_bill.OFF, bullet_bill.block(dol, game / "files/dt_na.dat"))]   # Roy / Morton's Bullet Bill
            + [(off, blk) for _, _, off, blk in own_placed] if engine_on else [])
        log += [f"own model: {s['name']}: {len(blk)} B at slot 0x2A +0x{off:X}, model-set slot 0x{slot:X}"
                for s, slot, off, blk in own_placed]
        log += sb_log
        appended += sb_appended
    icon_bank_off = cursor

    decoys, ring = (), None                                         # (the mini-map decoys: 5c)
    if chars:                                                       # 3-5: new ids' hooks (none without)
        # 3a. roster build hook (replaces `mr r3,r31` at 0x8006BD58; r31 = roster struct X)
        a = Asm(code.here)
        a.load_addr("r6", new_ids_list)
        a.label("loop")
        a.lbz("r7", 0, "r6").cmplwi("r7", STOCK_IDS).beq("done")
        a.load_addr("r8", at["selector"]).slwi("r9", "r7", 3).add("r8", "r8", "r9")
        a.lbz("r0", 2, "r8")                                # model family
        a.add("r10", "r31", "r0").lbz("r4", 0x4D, "r10")    # X[0x4D+fam] = count
        a.cmplwi("r4", 10).bge("next")
        a.mulli("r5", "r0", 10).add("r5", "r31", "r5").add("r5", "r5", "r4")
        a.stb("r7", 0x76, "r5")                             # X[0x76+fam*10+count] = id
        a.addi("r4", "r4", 1).stb("r4", 0x4D, "r10")
        a.label("next")
        a.addi("r6", "r6", 1).b("loop")
        a.label("done")
        if family_order:                                            # grid-order's reordered stock wheels
            grid_order_mod.family_reorder(a, data.put(grid_order_mod.family_table(family_order), align=4),
                                          data.put(bytes(12), align=4))
        a.mr("r3", "r31").b(0x8006BD5C)
        patch_word(dol, 0x8006BD58, 0x7FE3FB78, Asm(0x8006BD58).b(code.put(a.assemble(), 4)).assemble_word())

        # 3b. availability (Mii) range upper bound 0x64 -> ID_BOUND in the two wheel-list builders
        for addr, expect in ((0x804302CC, 0x2C800064), (0x804304C0, 0x2C800064), (0x80071B90, 0x2C040064)):
            patch_word(dol, addr, expect, (expect & 0xFFFF0000) | ID_BOUND)

        # 3d. select-screen model task FUN_804a5018 (SelCharaMdl, captain select / preview) takes a new
        #     request only for 0 <= id < 0x65, so new ids never loaded a model (invisible). Accept
        #     ids up to ID_BOUND, still rejecting the 0x65 "no character" sentinel. Replaces
        #     `cmpwi cr1,r4,0x65` (the `bge cr1` after it is no longer reached).
        a = Asm(code.here)
        a.cmpwi("r4", STOCK_IDS, cr=1).beq("reject", cr=1)
        a.cmpwi("r4", ID_BOUND, cr=1).bgt("reject", cr=1)
        a.b(0x804A5094)
        a.label("reject")
        a.b(0x804A5794)
        patch_word(dol, 0x804A508C, 0x2C840065, Asm(0x804A508C).b(code.put(a.assemble(), 4)).assemble_word())

        # 4. chemistry: replaces `add r3,r0,r6` at 0x8015C880 (r0 = player A's record, r6 = B's id).
        #    A stock B: A's row, column B. Stock A, new B: B's row, column A. Both new: a row has no columns past
        #    0x65, so the new-by-new table (new_chemistry, both ways from the definitions) answers.
        stats_rows = at["stats"] + STATS_HEADER - DATA_BASE    # (in data, as built: "chemistry_like" pairs read it)
        first_new, n_new, new_table = new_chemistry(chars, lambda a, b: data.blob[
            stats_rows + a * STATS_ROW + CHEM_BASE + b])
        new_chem = data.put(new_table, 4)
        a = Asm(code.here)
        a.cmpwi("r6", STOCK_IDS).bge("new_b")
        a.add("r3", "r0", "r6").lbz("r3", CHEM_BASE, "r3").blr()
        a.label("new_b")
        a.mr("r12", "r0").lhz("r11", 0, "r12")             # A's id (r0 as a base register reads as 0)
        a.cmpwi("r11", STOCK_IDS).bge("neutral")
        a.load_addr("r12", at["stats"] + STATS_HEADER)
        a.mulli("r3", "r6", STATS_ROW).add("r12", "r12", "r3").add("r12", "r12", "r11")
        a.lbz("r3", CHEM_BASE, "r12").blr()                 # B's master row, column A
        a.label("neutral")                                   # both new: new_chem[(A - first) * n + B - first]
        a.addi("r11", "r11", -first_new).cmplwi("r11", n_new - 1).bgt("unknown")
        a.addi("r12", "r6", -first_new).cmplwi("r12", n_new - 1).bgt("unknown")
        a.mulli("r11", "r11", n_new).add("r11", "r11", "r12")
        a.load_addr("r12", new_chem).lbzx("r3", "r12", "r11").blr()
        a.label("unknown")
        a.li("r3", NEUTRAL).blr()
        log.append(f"chemistry    new-by-new table {n_new}x{n_new} at 0x{new_chem:08X}, "
                   f"{sum(b != NEUTRAL for b in new_table) // 2} pairs set")
        patch_word(dol, 0x8015C880, 0x7C603214, Asm(0x8015C880).b(code.put(a.assemble(), 4)).assemble_word())
        # 4b. the select and team screens read chemistry from stack copies of the rows, not through FUN_8015c800:
        #     the same answers for new ids there (select_chemistry; Nick: no marker between Purple Mario and Pauline)
        import select_chemistry
        log += select_chemistry.apply(dol, item_code, at["stats"] + STATS_HEADER, first_new, n_new, new_chem,
                                      ID_BOUND)                 # item section: the main code space is full
        log += id_limit_sites(dol)

        # 3c. FUN_80071bb0 (members of the wheel holding an id; the grid square calls it with the id it
        #     displays) returns 0 for any id >= 0x4D before reading the family lists. Send new ids down
        #     the family-list path: replaces `blt cr1,0x80071BE8` after `cmpwi cr1,r5,0x4d`.
        a = Asm(code.here)
        a.blt("family", cr=1)
        a.cmpwi("r5", STOCK_IDS, cr=1).ble("none", cr=1)
        a.label("family")
        a.b(0x80071BE8)       # blt cr1 -> family path for stock ids; for new ids cr1 is gt -> Mii test -> family path
        a.label("none")
        a.b(0x80071BE0)       # li r3,0
        patch_word(dol, 0x80071BDC, 0x4184000C, Asm(0x80071BDC).b(code.put(a.assemble(), 4)).assemble_word())

        # 5a. select-screen portraits. The menus classify an id inline as "normal" (0 <= id < 0x4D)
        #     or Mii (0x4D-0x64); a new id is neither and falls through to the "?" / Mii path. At each
        #     portrait site, let new ids pass the normal test (`cmpwi cr1,r0,0x4d; bge cr1,+8; li r3,1`)
        #     and alias the id to the template's right where the portrait is chosen: resource
        #     `id + 0x149` (grid / wheel portraits) or the big preview FUN_80395db0(_, id, ...).
        for site in PORTRAIT_NORMAL_TESTS + (VOICE_NORMAL_TESTS if voices else ()):
            patch_word(dol, site + 8, 0x38600001, 0x38600001)          # li r3,1 (normal)
            a = Asm(code.here)
            a.blt("normal", cr=1)
            a.cmpwi("r0", STOCK_IDS, cr=1).ble("other", cr=1)         # Mii range / sentinel: not normal
            a.label("normal")
            a.b(site + 8)
            a.label("other")
            a.b(site + 12)
            patch_word(dol, site + 4, 0x40840008, Asm(site + 4).b(code.put(a.assemble(), 4)).assemble_word())
        # 5a''. Team lists built with the same normal test (ID_LIST_TESTS): a new id is kept (the stock path,
        #     +4) instead of falling to the Mii path (+0x1C), which leaves it -1 (the change-defense diamond
        #     drew an empty circle for every new character).
        for site, reg in ID_LIST_TESTS:
            stub_at = code.here + (-len(code.blob) % 4)                 # (not `at`: the table addresses)
            assert code.put(id_list_stub(site, reg, stub_at), 4) == stub_at
            patch_word(dol, site, 0x4084001C, Asm(site).b(stub_at).assemble_word())
        # 5a'. `id + 0x149` at these three sites is the name label's resource row, not a portrait
        #      (Member_local::CS2d_StatusName, Order_local::CS2d_FukidasiStatusName): new characters get
        #      their own name rows (char_names step 3; the layout gets them in gridcells.patch_layout).
        #      Without the grid step (no name page in the layout) they keep the template's name.
        import char_names
        for site, ins in PORTRAIT_RESOURCE_ADDS:                        # addi rD,r4,0x149
            rd = (ins >> 21) & 31
            a = Asm(code.here)
            if grid_square:
                a.cmpwi("r4", char_names.FIRST_NEW).blt("stock")
                a.addi(f"r{rd}", "r4", char_names.NAME_ROW_BASE - char_names.FIRST_NEW).b(site + 4)
                a.label("stock")
            else:
                alias_r(a, "r4", chars)
            a.word(ins).b(site + 4)
            patch_word(dol, site, ins, Asm(site).b(code.put(a.assemble(), 4)).assemble_word())
        for site in PORTRAIT_PREVIEW_CALLS:                             # bl FUN_80395db0, r4 = id
            a = Asm(code.here)
            alias_r(a, "r4", [c for c in chars if not c["icon"]])
            a.b(0x80395DB0)
            patch_word(dol, site, Asm(site).bl(0x80395DB0).assemble_word(), Asm(site).bl(code.put(a.assemble(), 4)).assemble_word())

        # 5c. FUN_80395DB0(ctx, id, view, ...) is the shared portrait renderer (grid squares, previews):
        #     id < 0x4D plays the icon-bank tracks at frame = id, Mii ids draw a Mii face, anything else
        #     plays frame 0x4D (the "?" key). Alias new ids at entry: replaces `mr r24,r4`.
        #     Chars with their own icon art are not aliased: they take the normal branch instead
        #     (replaces `bge 0x80395EA8` after `cmpwi r24,0x4d`) and play frame = their own id, whose
        #     track keys point at their own resource rows.
        a = Asm(code.here)
        a.mr("r24", "r4")
        alias_r(a, "r24", [c for c in chars if not c["icon"]])
        a.b(0x80395DD4)
        patch_word(dol, 0x80395DD0, 0x7C982378, Asm(0x80395DD0).b(code.put(a.assemble(), 4)).assemble_word())
        # the Pom Pom mini-map ring (pompom_ring.py) is an icon of its own: a stand-in id past the last one
        decoys = ()
        if on("minimap-decoys"):
            import pompom_decoys
            decoys = in_build(pompom_decoys.ids(entries, char_defaults), valid, "mini-map decoys", log)
        ring = None
        if decoys:
            import pompom_ring                                      # (the first one's template, as its icon)
            first = next((e for e in entries if e["id"] == decoys[0]), {"id": decoys[0], "template": decoys[0]})
            ring = pompom_ring.stand_in(max_id, first)
        own = [c for c in chars if c["icon"]] + ([ring] if ring else [])
        if own:
            # every id past the stock ones reaching here has its own art (the others were aliased above), so one
            # range test instead of a compare per character (8 B each: 61 recolors overflowed the code section)
            assert all(c["id"] >= char_names.FIRST_NEW for c in own), "own portrait art below the new ids"
            a = Asm(code.here)
            a.blt("normal")
            a.cmpwi("r24", char_names.FIRST_NEW).bge("normal")
            a.b(0x80395EA8)
            a.label("normal")
            a.b(0x80395E20)
            patch_word(dol, 0x80395E1C, 0x4080008C, Asm(0x80395E1C).b(code.put(a.assemble(), 4)).assemble_word())

        # 5b. model resolver FUN_80367060 `return has_model[id] ? id : 4`: alias the returned id
        #     (new ids with their own model keep their id: it selects their directory, step 2b)
        a = Asm(code.here)
        a.mr("r3", "r4")
        alias_r(a, "r3", [c for c in chars if not c["model_overlay"]])
        a.blr()
        patch_word(dol, 0x80367078, 0x7C832378, Asm(0x80367078).b(code.put(a.assemble(), 4)).assemble_word())

        for site, reg in MODEL_DIR_SITES:                              # r4 = dirmap[rN] (halfwords)
            a = Asm(code.here)
            a.load_addr("r12", dirmap_addr).slwi("r4", f"r{reg}", 1).lhzx("r4", "r12", "r4")
            a.b(site + 4)
            expect = (14 << 26) | (4 << 21) | (reg << 16) | MODEL_DIR_BASE
            patch_word(dol, site, expect, Asm(site).b(code.put(a.assemble(), 4)).assemble_word())
        if on("share-anim-banks"):                                  # identical file 14s: one loaded copy
            import bank8_share
            clean_toc = dtna_toc.toc(Dol(game / "sys/main.dol"))
            blobs = []
            with open(game / "files/dt_na.dat", "rb") as f:
                for i, d in enumerate(dirmap):
                    if i in own_f14 or not d or d >= len(clean_toc) or len(clean_toc[d] or ()) <= 14:
                        blobs.append(own_f14.get(i))
                        continue
                    off, length = clean_toc[d][14]
                    f.seek(off)
                    blobs.append(f.read(length) if length else None)
            log += bank8_share.apply(dol, item_code, data, bank8_share.reps(blobs))

    if grid:                                                        # 7. (none: the stock grid)
        log += gridcells.add_grid_square(dol, code, data, chars, grid_squares, grid_layout, force_grid)
    if big_wheels:
        import wheel7                                               # 7a. color wheels of up to 10 (Yoshis)
        log += wheel7.apply(dol, code)
    if features is not None and on("cpu-vs-cpu"):                   # both teams CPU in Exhibition matches
        import cpu_vs_cpu                                           # (named only: never in a features=None build)
        log += cpu_vs_cpu.apply(dol, item_code)                     # item section: the main code space is full
        log.append("CPU vs CPU: the computer plays both teams in Exhibition games")   # (the plain line)
    if features is not None and on("match-seed"):                   # the match RNG's seed: picked, or the clock
        import match_seed                                           # (named only, as cpu-vs-cpu)
        log += match_seed.apply(dol, item_code, seed)               # item section, as cpu-vs-cpu
    replay_on = {f for f in ("no-replays", "replay-slow-motion", "replay-camera", "contact-freeze")
                 if features is not None and on(f)}                  # (named only: data words, docs/replay.md)
    if replay_on:
        import replay_tweaks
        log += replay_tweaks.apply(dol, replay_on, replay_speed, replay_frames, replay_camera, freeze_percent)
    if features is not None and on("inning-break-time"):            # the box score's time between innings
        import inning_break                                         # (named only; item section, as cpu-vs-cpu)
        log += inning_break.apply(dol, item_code, inning_seconds)
    if replay_showcase:                                             # test builds only (build_test_replays.py)
        import replay_showcase as showcase
        log += showcase.apply(dol, item_code)                       # item section, as cpu-vs-cpu
    if on("level-5"):                                               # level 5 / 6 CPU (Nick): every CPU change
        import level5                                               # below runs at levels 5 and 6 only (the flag
                                                                    # allocated with the menu, step 19b)
    if on("cpu-star-swings") or on("cpu-no-star-pitches"):          # CPU star moves (Nick): weak charge power
        import cpu_stars                                            # star-swings more; no CPU star pitches
        if on("cpu-star-swings"):
            log += cpu_stars.apply_swings(dol, item_code)           # item section, as cpu-vs-cpu
        if on("cpu-no-star-pitches"):
            log += cpu_stars.apply_no_pitches(dol, item_code)
    if on("cpu-charge-timing"):                                     # level 5 CPU charge: full at the swing
        import cpu_charge
        log += cpu_charge.apply(dol, item_code)
    if on("cpu-no-bunts"):                                          # level 6 CPU never bunts
        import cpu_bunt
        log += cpu_bunt.apply(dol, item_code)
    if on("cpu-cursed-ball"):                                       # level 5 / 6 CPU charged pitches: cursed
        import cpu_cursed
        log += cpu_cursed.apply(dol, item_code)
    if on("cpu-batter-track"):                                      # level 6 CPU batter: take / swing on the real
        import cpu_track                                            # zone from the ball's flight, at the swing frame
        log += cpu_track.apply(dol, item_code, data)              # (data: the level 5 mind game's memory)
    if on("cpu-rundown"):                                           # level 5 / 6 CPU rundowns
        import cpu_rundown
        log += cpu_rundown.apply(dol, item_code, data)              # (data: the rundown log's ring, test builds)
    if on("cpu-items"):                                             # level 6 CPU item use
        import cpu_items
        log += cpu_items.apply(dol, item_code, data)
    if on("cpu-item-defense"):                                      # level 6 CPU fielding against items
        import cpu_item_defense
        log += cpu_item_defense.apply(dol, item_code, data)
        import cpu_defense_log                                      # its per-frame log (LOG_ENTRIES: test builds)
        log += cpu_defense_log.apply(dol, item_code, data)
    if on("cpu-subs"):                                              # level 5 CPU pitching change: top pitchers,
        import cpu_subs                                             # no captain preference; field re-arranged
        log += cpu_subs.apply(dol, item_code)                       # for chemistry (item section)
    if on("cpu-pitching"):                                          # level 5 / 6 CPU pitch model: its tables here
        import cpu_pitching                                         # (data), its code in its own section (19b)

        def built(addr, n):                                         # tables as built: data section, else the DOL
            return bytes(data.blob[addr - DATA_BASE:addr - DATA_BASE + n]) if addr >= DATA_BASE else dol.read(addr, n)
        stats = cpu_pitching.read_stats(built, range(max_id + 1), at.get("stats", 0x806CE9A0) + STATS_HEADER,
                                        at.get("changeup", 0x80628EB0))
        cpu_pitching.apply_data(dol, data, stats)
    if on("level-5"):                                               # the manager hook: the flag, and the
        import cpu_perfect, cpu_settings                            # cpu_perfect's bytes swapped in per match
        groups = [f for f in cpu_perfect.GROUPS if on(f)]           # (cpu_settings: + the CPU levels tab's edits,
        swaps, swaps6, reset4 = cpu_settings.swaps(groups, dol.read)        # configured by build(); none: today's bytes)
        log += level5.apply(dol, item_code, data, swaps, swaps6, reset4)
    if new_pitches:                                                 # new star pitches 17-20: fly their path's
        saved_new, pitch_new.NEW = pitch_new.NEW, new_pitches       # pitch, own speed (item section)
        try:
            log += pitch_new.apply(dol, item_code)
        finally:
            pitch_new.NEW = saved_new
    sound_swings, sound_pitches = {}, {}                            # star moves' own cut-in sounds (item section;
    if star_moves:                                                  # ours / creations only)
        import move_sounds, custom_swings
        sound_swings = {sid: v for sid, v in move_sounds.SCRIPTS["swing"].items()
                        if custom_swings_on and sid in custom_swings.SWINGS}
        sound_pitches = {pid: v for pid, v in move_sounds.SCRIPTS["pitch"].items()
                         if pid in pitches or pid in new_pitches}
    if sound_swings or sound_pitches:
        from creators import cutin_sounds
        clip_ids = json.loads(voice_files()[1].read_text(encoding="utf8")).get("items", {}) \
            if any(k == "clip" for _, s in list(sound_swings.values()) + list(sound_pitches.values()) for k, _, _ in s) \
            else {}
        res = lambda kind, v: cutin_sounds.resolved(kind, v[0], v[1], clip_ids)  # noqa: E731
        log += move_sounds.apply(
            dol, item_code, {sid: res("swing", v) for sid, v in sound_swings.items()},
            {pid: res("pitch", v) for pid, v in sound_pitches.items() if pid < pitch_new.FIRST_NEW},
            {pid - pitch_new.FIRST_NEW: res("pitch", v) for pid, v in sound_pitches.items() if pid in new_pitches},
            pitch_new.LAYOUT.get("data") if new_pitches else None)
    boot_game_on = features is not None and on("boot-game")      # (named only, as cpu-vs-cpu)
    boot_bench = None                                               # Start in a game's benches (preset, DHSEL)
    if boot_game_on or on("boot-captain-select"):                   # boot-game wins over captain select
        import quickboot                                            # power on -> save 1 -> character select
        quickboot.BUILT = valid                                     # (a test build's teams and captains: these)
        try:
            if boot_game_on:                                        # ... -> a game with the profile's teams
                game_opt = boot_game
                if not bench and (boot_game or {}).get("benches"):   # (no bench in this build: the players only)
                    game_opt = {k: v for k, v in boot_game.items() if k not in ("benches", "dr")}
                    log.append("start in a game: the teams' bench players are left out (the bench isn't in this "
                               "build)")
                args, line = boot_game_args(game_opt, stock + chars, cpu=features is not None and on("cpu-vs-cpu"),
                                            level6_addr=level5.level6() if on("level-5") else None)
                boot_dh = args.pop("dh", None)                      # the teams' benches: step 19's preset
                if "bench" in args:
                    boot_bench = (args["bench"], boot_dh)
                gone = [c for c in args["captains"] if captain and c in (captains.STOCK_TABLE[i] for i in captains.REMOVED)]
                if gone:                                            # (a removed stock captain has no index here)
                    raise ValueError("start in a game: " + ", ".join(captains.STOCK_CAPTAIN_NAMES[
                        captains.STOCK_TABLE.index(c)] for c in gone) + " isn't a captain in this build (taken off "
                        "captain select): pick a captain who is on it")
                if captain and all(c in captains.table() for c in args["captains"]):   # this build's captains
                    args["captain_index"] = "captains"  # (step 9 writes their table: their own indices, no takeover)
                log += quickboot.apply(dol, item_code, **args)      # item section: the main code space is full
                log += line.split("\n")                            # (a set lineup: its own lines)
            else:
                where = boot_captain or {}                          # the game after captain select: its
                park, night = where.get("stadium", 0), bool(where.get("night"))   # stadium (there's no stadium
                park_name = quickboot.stadium_name(park, night)     # select on this path: the Exhibition entry
                if not quickboot.stadium_ok(park, night):           # writes setup +5..+7)
                    raise ValueError(f"start at captain select: the game has no {park_name}")
                log += quickboot.apply(dol, item_code, stadium=park, night=night)
                log.append("start at captain select: power on goes to captain select on save file 1, once per "
                           f"power-on; the game plays in {park_name}")
        finally:
            quickboot.BUILT = None
        written["quick boot teams"] = quickboot.LAST_IDS
    item_card = swing_card = None                                   # 17. item / special ability on the cards
    skills = lambda cid: data.blob[at["stats"] - DATA_BASE + STATS_HEADER + cid * STATS_ROW + 8:][:4]
    # a character with all four skills (star pitch, swing, fielding, baserunning: e.g. Mario given a fielding ability)
    # lists 4 lines, which only our 4-line panes draw: the stock ones had no 4th, and captain select read a missing
    # pane (Nick's 1.1 crash, invalid read 0x18 at 0x80506104 under FUN_802CA65C). So they come in on their own.
    four = (sorted(cid for cid in list(range(STOCK_IDS)) + [c["id"] for c in chars] if all(skills(cid)))
            if "stats" in at else [])                               # (no moved stats table: stock skills, no 4th)
    labels_on = grid_square and (captain or custom_swings_on or bool(four) or
                                 any(on(f) for f in LABEL_USERS if f != "captains"))
    captain_lines = captain or (bool(four) and labels_on)           # captain select's labels and 4-line panes
    if four and grid_square:
        log.append("4 skills listed for " + ", ".join(f"0x{cid:02X}" for cid in four) + ": the 4-line card and captain "
                   "select panes go in")
    if grid_square:                                                 # (its rows: at the end of file 19, below)
        import star_move_labels                                     # every star pitch / swing past the stock labels
        for cid in list(range(STOCK_IDS)) + [c["id"] for c in chars]:   # has its label, fielding ones theirs: never a
            pitch, swing, fielding = skills(cid)[:3]                # table slot pointing at a row that isn't there
            assert labels_on or (pitch < star_move_labels.STOCK_PITCH_SLOTS - 1 and swing < 13),                 f"0x{cid:02X}: star pitch {pitch} / swing {swing} without the label rows (LABEL_USERS)"
            assert fielding < abilities.STOCK_COUNT or on("new-ability-slot") or on("star-solo-toss")                 or on("clamber-solo-jump"),                 f"0x{cid:02X}: fielding ability {fielding} without its label row (new-ability-slot)"
    label_chars = sorted(chars + [e for e in stock if e["item_ability"] or e["hitting_ability"] or e["running_ability"]],
                         key=lambda c: c["id"])                     # + stock entries with a label key
    if not on("item-ability"):                                      # (degrade: the machinery without the abilities)
        label_chars = [dict(c, item_ability=None, hitting_ability=None, running_ability=None) for c in chars]
    if labels_on:
        more, item_card = item_abilities.apply(dol, item_code, label_chars, max_id, skills)
        log += more
        import star_move_labels                                     # (build() imports it locally below)
        more, swing_card = star_move_labels.apply(dol, item_code, label_chars, max_id, skills,
                                                  custom=custom_swings_on)
        log += more                                                 # 17a. custom swing / hitting names (star row)
    if captain:                                                     # 9. custom captains (captains.py)
        import captains
        log += captains.add_captain(dol, code, data, chars, preview)
        written["captain table"] = captains.table() + list(preview or ())
    # (9a, Luma's hand-node fix, is gone: the Lumas' template is Boo, whose pair is already (2, 3). 9c, the
    # Extra Innings hooks taken out, went with the Extra Innings base: the clean game has the stock words.)

    # 9b. Pauline's chance cheer (pauline_chance.py, git-e2; Nick): every Pauline at-bat starts the
    # scoring-position cheer with her own jingle, and the batter claps for the stars. Needs the jingle
    # in our MY2.brsar, so only with voices and a "pauline_chance" sound id in docs/voice-tables.json.
    pc_sound = json.loads(voice_ids.read_text(encoding="utf8")).get("pauline_chance") if voices else None
    cheer = ()                                                      # Pauline, and "chance_cheer" on any character
    if on("chance-cheer"):
        import pauline_chance
        cheer = pauline_chance.ids(entries)
    written["chance cheer"] = cheer
    chance_cheer = bool(cheer)
    if chance_cheer:
        if pc_sound is not None:
            log += pauline_chance.apply(dol, code, data, pc_sound, pauline=cheer)
        else:
            # Stand-in until her jingle is in the archive: Mario's stock chance jingle, its own tempo and
            # claps, so the forced cheer and the batter's clapping can be tested now (Nick).
            m = pauline_chance.unpack_row(dol.read(pauline_chance.TABLE + pauline_chance.MARIO_ROW
                                                   * pauline_chance.ROW, pauline_chance.ROW))
            log += pauline_chance.apply(dol, code, data, m["sound"], pauline=cheer, bpm=m["bpm"], beats=m["beats"],
                                        unit=m["unit"], patterns=m["patterns"])
            log.append("pauline chance: stand-in jingle (Mario's) until pauline_chance is in voice-tables.json")
        # her claps run past the solo intro scripts and a pad clap skipped the intro: pauline_chance_fixes
        import pauline_chance_fixes
        log += pauline_chance_fixes.apply(dol, code, data, *pauline_chance_fixes.locate(data))
        # one star, a tighter clap window and a random pick of 5 syncopated patterns (Nick)
        import pauline_chance_tuning
        log += pauline_chance_tuning.apply(dol, code, data, *pauline_chance_tuning.from_pauline_chance(dol, code))
        if pc_sound is not None:                                    # the intro's end waits for her whole jingle
            import pauline_chance_hold                              # (its length; Mario's stand-in is stock)
            log += pauline_chance_hold.apply(dol, code, data, pauline_chance_tuning.flag_from(dol, code))

    if chars:                                                       # (new directories only)
        # FUN_8036629c(mgr, dir, ...) also treats the directory as a model id: dir > 0x5E (Mii
        # models) selects format 7, and dir - 0x12 indexes the per-model prop tables 0x806B49D8 /
        # 0x806B4D00. Both use the template's directory for a new one (the files still load from it).
        a = Asm(code.here)
        a.load_addr("r12", revmap_addr).slwi("r0", "r27", 1).lhzx("r12", "r12", "r0")      # (r0 is dead here)
        a.cmplwi("r12", 0x5F).b(0x80366344)
        patch_word(dol, 0x80366340, 0x281B005F, Asm(0x80366340).b(code.put(a.assemble(), 4)).assemble_word())
        a = Asm(code.here)
        a.load_addr("r12", revmap_addr).slwi("r31", "r27", 1).lhzx("r31", "r12", "r31")   # (r0 is live: and. next)
        a.addi("r31", "r31", -MODEL_DIR_BASE).b(0x803663AC)
        patch_word(dol, 0x803663A8, 0x3BFBFFEE, Asm(0x803663A8).b(code.put(a.assemble(), 4)).assemble_word())

    fielding_of = ((lambda cid: skills(cid)[2]) if chars else   # the stats as built (no new characters: the
                   (lambda cid: dol.read(0x806CE9A0 + STATS_HEADER + cid * STATS_ROW + 10, 1)[0]))   # stock table)
    if ability_edits and on("ability-edits"):                       # 8. the abilities' code (the close play)
        import ability_edits as ability_edits_mod
        log += ability_edits_mod.apply_hooks(dol, code, ability_edits)
    jumpers = [cid for cid in list(range(STOCK_IDS)) + [c["id"] for c in chars]
               if fielding_of(cid) == abilities.CLAMBER_JUMP]
    if on("clamber-solo-jump") and jumpers:
        import buddy_clamber_code                                   # 8. Clamber Jump (fielding ability 14)
        base = code.here + (-len(code.blob) % 4)
        assert code.put(buddy_clamber_code.apply(dol, base), align=4) == base
        log.append(f"clamber jump hooks at 0x{base:08X}: " + ", ".join(f"0x{c:02X}" for c in jumpers))
    if on("fixed-items") or customs:                                # 8. batting items (git-d9 / git-ce; only then:
        import batter_items                                         # its hooks, a new item's characters)
        # "batting_item" (a definition's or stock entry's): that character always gets this item from the roulette, over
        # FIXED_ITEM and koopa_items.STOCK_FIXED; "always_item": an item whatever the chemistry (batter_items.fixed / always)
        fixed = in_build(batter_items.fixed(entries, char_defaults), valid, "fixed items", log)
        # items 6.. need the Star Bits roulette hooks; without them new characters' "always_item" is left out too
        always = in_build(batter_items.always(entries if star_bits else stock, char_defaults), valid, "always items", log)
        if customs:                                                     # new items: the Koopalings' machinery
            assert star_bits and on("item-variants") and engine_on, \
                "new items need the item engine (item-engine) and what it needs"
            names = {e["name"].strip().lower(): e["id"] for e in entries}
            always = list(always)                                       # (in_build may give a tuple)
            for s in customs:                                           # a new item's own "given": its characters
                for who in s["characters"]:
                    cid = names.get(who.strip().lower())
                    assert cid is not None, f"{s['name']}: no character {who!r} in this build"
                    fixed[cid] = s["id"]
                    if s["always"] and cid not in always:
                        always.append(cid)
            log.append("items: " + ", ".join(f"{s['name']} ({s['id']}{', ours edited' if s['replaces'] else ''})"
                                             for s in customs))
            ours = [s for s in customs if s["replaces"]]
            if ours:                                                    # an edit's values (the log shows them)
                log.append("items edited: " + "; ".join(f"{s['name']} ({s['id']}): {creators.items.values_text(s)}"
                                                        for s in ours))
            if any(s.get("slide") for s in customs):                # (a line the beta's quiet log keeps too)
                log.append("knockback: " + "; ".join(f"{s['name']} ({s['id']}) slides at {s['slide'][0]:g} for "
                                                      f"{s['slide'][1]} frames" for s in customs if s.get("slide")))
        written.update({"fixed items": fixed, "always items": always} if on("fixed-items") else {})
        for first, f in ((batter_items.STAR_BITS, None), (7, "item-variants"), (8, None)):
            if not (star_bits if first == batter_items.STAR_BITS else engine_on if first == 8 else on(f)):
                fixed = {k: v for k, v in fixed.items() if v < first}   # Star Bits (6), Ice (7), the engine's (8..)
        fixed = {k: v for k, v in fixed.items() if v not in dropped}    # the Koopalings' items not chosen
        for hook, orig, fn in (batter_items.HOOKS if on("fixed-items") else ()):   # Wario/Waluigi always get one;
            at = code.here + (-len(code.blob) % 4)                                 # fixed items
            body = fn(at, always if fn is batter_items.hook else fixed).assemble()
            body += Asm(at + len(body)).b(hook + 4).assemble()
            assert code.put(body, align=4) == at
            patch_word(dol, hook, orig, Asm(hook).b(at).assemble_word())
        if on("fixed-items"):
            log.append(f"batting items: always {len(always)}, fixed {len(fixed)}"
                       + "".join(f", {c['name']} {c['batting_item']}" for c in entries if c["batting_item"]))
    star_chars = ()                                                 # 8. Lumas and Lubba bring a star (git-d9)
    if on("batter-star"):
        import batter_star
        star_chars = in_build(batter_star.ids(entries, char_defaults), valid, "batter star", log)   # + "batter_star"
        written["batter star"] = star_chars
    for hook, orig, fn in (batter_star.HOOKS if on("batter-star") else ()):
        at = code.here + (-len(code.blob) % 4)
        body = fn(at, star_chars).assemble()
        body += Asm(at + len(body)).b(hook + 4).assemble()
        assert code.put(body, align=4) == at
        patch_word(dol, hook, orig, Asm(hook).b(at).assemble_word())
    if on("batter-star"):
        log.append("batter star: +1 star at bat for " + ", ".join(f"0x{c:02X}" for c in star_chars))
    import cutin_backdrop                                           # 8. captain star cut-in backdrop (git-d9)
    # with no new characters only stock ones can use a cut-in backdrop of another captain: King Boo's star swing
    # (custom-swings) or the own backdrops (King Boo's too); otherwise the hook would only test absent ids
    if chars or custom_swings_on or on("cutin-backdrops"):
        for hook, orig, fn in cutin_backdrop.hooks(own=on("cutin-backdrops")):   # custom captains: a stock captain's
            at = code.here + (-len(code.blob) % 4)
            body = fn(at).assemble()
            body += Asm(at + len(body)).b(hook + 4).assemble()
            assert code.put(body, align=4) == at
            patch_word(dol, hook, orig, Asm(hook).b(at).assemble_word())
        log.append("cut-in backdrop: " + ", ".join(f"0x{c:02X} -> 0x{s:02X}" for c, s in cutin_backdrop.BACKDROP_FROM.items()
                                                   if c not in cutin_backdrop.OWN_BACKDROP))
        written["cut-in backdrops"] = [i for c, s in cutin_backdrop.BACKDROP_FROM.items() for i in (c, s)] + [
            i for c, (s, _) in cutin_backdrop.OWN_BACKDROP.items() for i in (c, s)]
    if custom_swings_on:                                            # 8. custom star swings (git-d9)
        import custom_swings, gravity_ball, boo_ball
        written["custom star swings"] = [c for sw in custom_swings.SWINGS.values() for c in sw["chars"]]
        for hook, orig, fn in custom_swings.HOOKS + gravity_ball.HOOKS + boo_ball.HOOKS:   # at their addresses
            at = code.here + (-len(code.blob) % 4)
            body = fn(at).assemble()
            body += Asm(at + len(body)).b(hook + 4).assemble()
            assert code.put(body, align=4) == at
            patch_word(dol, hook, orig, Asm(hook).b(at).assemble_word())
        log.append(f"star swings: {len(custom_swings.HOOKS)} + {len(gravity_ball.HOOKS)} + {len(boo_ball.HOOKS)} hooks "
                   f"({', '.join(s['name'] for s in custom_swings.SWINGS.values())})")
    if on("immunities"):
        import immunities                                           # 8. female / floating immunities
        # Heart swing spares females, POW (and Daisy's Flower swing, ...) spares floaters; the stock checks
        # are an id list + model families. Bouldergeist and Lubba float through their family already; they
        # are listed too so a future template change can't drop it.
        female = in_build(list(immunities.FEMALE_EXTRA), valid, "immunities (female)", log)
        floating = in_build(sorted(set(immunities.FLOATING_EXTRA) | {0x6A, 0x6F}), valid, "immunities (floating)", log)
        log += immunities.apply(dol, code, data, female=female, floating=floating)
        written["immunities"] = female + floating
    if decoys:                                                      # 8. Pom Pom mini-map decoys (git-ce)
        base = code.here + (-len(code.blob) % 4)
        assert code.put(pompom_decoys.apply(dol, base, decoys), align=4) == base
        log.append(f"mini-map decoys for {', '.join(f'0x{c:02X}' for c in decoys)} at 0x{base:08X}")
        log += pompom_ring.apply(dol, code, decoys, ring["id"])

    if voices:                                                      # 10. custom voices (git-e2)
        log += voice_tables(dol, code, data, chars, n_rows)
        written["voices"] = [c["id"] for c in chars if c["voice"]]
    odds = item_odds if on("item-odds") else None                   # item-odds: the roulette's weights
    if item_odds and odds is None:
        log.append("item odds left out (item-odds off)")
    if not star_bits and odds:                                      # the stock roulette's table, in place
        import starbits_roulette
        log += starbits_roulette.stock_odds(dol, odds)
    if star_bits:                                                   # 12. Star Bits batting item (id 6)
        import starbits_roulette, starbits_item, ice_item, koopa_items
        variants = on("item-variants")
        koopas = variants and engine_on                             # (the engine; the six: koopa_on)
        forced = [(vid, ice_item.ICON_ROW + 1 + k) for k, (vid, _) in enumerate(koopa_items.VARIANTS)] if koopas else []
        forced += [(s["id"], ice_item.ICON_ROW + 1 + len(koopa_items.VARIANTS) + k, s["base"])
                   for k, s in enumerate(new)]                      # + new items (enabled with their base item)
        weighted = {s["id"]: s["roulette"] for s in customs if any(s["roulette"]) and s["id"] > ice_item.ICE}
        odds = {**(odds or {}), **weighted} if weighted else odds  # an item's own roulette weights
        ice_edit = next((s for s in balls if s["id"] == ice_item.ICE), None)
        extra = [(ice_item.ICE, tuple(ice_edit["roulette"]), ice_edit["base"], ice_item.ICON_ROW) if ice_edit
                 else ice_item.EXTRA]                               # Ice (rolled like the stock six)
        more = {"weights": list(ground["star-bits"]["roulette"])} if "star-bits" in ground else {}
        log += starbits_roulette.apply(dol, item_code, data, extra=extra if variants else [],
                                       forced=forced, odds=odds, **more)   # + Ice, Koopalings
        sb = (odds or {}).get("starbits", (odds or {}).get(6))   # (id 6)
        if sb:                                                      # (a line the beta's quiet log keeps too)
            log.append(f"Star Bits in the roulette: weight {'/'.join(map(str, sb)) if isinstance(sb, list) else sb}")
        log += starbits_item.apply(dol, code, data)
    if star_bits and variants:                                      # Ice (id 7), + the Koopalings' variants
        spins = koopas and any(s["effect"] == "spin" for s in balls)
        spin_balls = koopas and any(s["effect"] == "spin" and s["base"] in (1, 3) for s in balls)
        if spins:                                                   # spin-out: its hooks and routine (spin_effect)
            import spin_effect
            spin_fn = spin_effect.ensure(dol, item_code, data)
        import item_params                                          # items' own stock-table values
        param_specs = [(s["id"], s["base"], s.get("params") or {}) for s in balls]
        use_call = item_params.routine(dol, item_code, data, param_specs)
        log += item_params.log_lines(param_specs)
        log += ice_item.apply(dol, item_code, data, **(dict(variants=koopa_items.VARIANTS, knock=koopa_items.KNOCK,
                              hues=koopa_items.HUES, jump=koopa_items.JUMP)
                              if koopas and not balls + ring_items and not dropped else
                              item_args(balls + ring_items, skip) if koopas else {}),
                              **({"spin_fn": spin_fn} if spin_balls else {}), **({"use_call": use_call} if use_call else {}))
    if star_bits and koopas:
        import ludwig_fire                                          # the 5-ball Fireball pool (before koopa_items)
        n = max([ludwig_fire.N_BALLS] + [s["count"] for s in balls])   # a new item's more balls: a bigger pool
        log += ludwig_fire.apply(dol, item_code, data, ice_item.LAYOUT["variant"],
                                 **({"n": n} if n > ludwig_fire.N_BALLS else {}))
        log += koopa_items.apply(dol, item_code, data, ice_item.LAYOUT["variant"], ice_item.LAYOUT["base_tab"],
                                 forced[-1][0], customs=balls, skip=skip)
        import shell_item                                           # items built on the Shell: speed, size, hit
        log += shell_item.apply(dol, item_code, data, ice_item.LAYOUT["variant"],
                                [s for s in balls if s["chassis"] == "shell"], spin_fn=spin_fn if spins else None)
        import item_sounds                                          # items' own sounds (after the hit hooks)
        clip_ids = json.loads(voice_files()[1].read_text(encoding="utf8")).get("items", {}) \
            if any(kind == "clip" for s in customs for kind, _ in s["sounds"].values()) else {}
        per = {ev: {} for ev in ("launch", "hit", "land", "lob")}
        for s in customs:
            for ev, (kind, v) in s["sounds"].items():
                if kind == "clip":
                    assert ev in clip_ids.get(s["name"], {}), \
                        f"{s['name']}: its own {ev} sound wasn't added to the sound archive (patch through the patcher)"
                    v = clip_ids[s["name"]][ev]
                per["lob" if ev == "land" and s["chassis"] == "lob" else ev][s["id"]] = v
        log += item_sounds.apply(dol, item_code, ice_item.LAYOUT["variant"], throws=per["launch"], hits=per["hit"],
                                 lands=per["land"], lob_lands=per["lob"])
        log += item_params.peel_gate(dol, item_code, ice_item.LAYOUT["variant"],   # fewer Banana peels
                                     {s["id"]: s["peels"] for s in balls if s.get("peels")})
        log += item_params.slip_gate(dol, item_code, ice_item.LAYOUT["variant"],   # slips of their own length
                                     {s["id"]: s["slip_frames"] for s in balls if s.get("slip_frames")})
        log += item_params.boo_gate(dol, item_code, ice_item.LAYOUT["variant"],    # Boos that stay longer / shorter
                                    {s["id"]: s["boo_frames"] for s in balls if s.get("boo_frames")})
        import creators.items
        burn_off = [v for v in creators.items.burn_off(customs, edited) if v not in dropped]   # (placed last)
        runner_off = [v for v in creators.items.runners_off(customs, edited) if v not in dropped]   # (runner_hits:
                                                                                                         # last, below)
        import wendy_rings
        import lemmy_balls, bullet_bill                             # Lemmy's circus balls, the Bullet Bill: same stub
        lm_consts = data.put(struct.pack(">3f", lemmy_balls.MODEL_Y, 0.0, 1.0), 4)
        bb_consts = data.put(bullet_bill.consts(), 4)
        own_draw = []                                               # the players' own models (own_models)
        for s, slot, off, _ in own_placed:
            h = s["model_height"] if s.get("model_height") is not None else s["model_size"] / 2
            own_draw.append((s, slot, off, data.put(struct.pack(">3f", h, 0.0, 1.0), 4)))
        log += wendy_rings.apply(dol, item_code, data, ice_item.LAYOUT["variant"],     # Wendy's rings (id 12)
                                 more_models=[(lemmy_balls.SLOT, lemmy_balls.OFF, lemmy_balls.N),
                                              (bullet_bill.SLOT, bullet_bill.OFF, 1)]
                                 + [(slot, off, s["count"]) for s, slot, off, _ in own_draw],
                                 more_draw=[lambda a: lemmy_balls.draw_code(a, ice_item.LAYOUT["variant"],
                                            ludwig_fire.LAYOUT["arr"], lm_consts, wearing(balls, "circus-ball",
                                                                                          koopa_items.LEMMY, skip)),
                                            lambda a: bullet_bill.draw_code(a, ice_item.LAYOUT["variant"],
                                                      ludwig_fire.LAYOUT["arr"], bb_consts,
                                                      wearing(balls, "bullet-bill", koopa_items.BILL, skip))]
                                 + [lambda a, s=s, slot=slot, c=c: own_models.draw_code(
                                     a, ice_item.LAYOUT["variant"], ludwig_fire.LAYOUT["arr"], c, (s["id"],), slot,
                                     s["count"], f"own{slot:x}") for s, slot, _, c in own_draw],
                                 **({"pools": [ring_pool(s) for s in ring_items] + shower_pools()}
                                    if ring_items or shower_pools() else {}))
    if _ice is not None:                                            # extra particle slots without the item variants
        log += _ice.grow_only(dol, item_code)
    if trail_swings or trail_pitches:                               # 0b''. the star trail colours' slots
        extra = _ice.LAYOUT["extra"]
        for k, sid in enumerate(sorted(trail_swings)):
            data.blob[_gb.TRAIL_DATA - data.base + k] = extra[_st.key(trail_swings[sid])]
        _gw.TRAIL_PLAN = (extra[_st.key(trail_pitches[13])] if 13 in trail_pitches else None,
                          {pid - pitch_new.FIRST_NEW: extra[_st.key(hl)] for pid, hl in trail_pitches.items()
                           if pid in new_pitches}, pitch_new.LAYOUT.get("data"))
        log.append("star trail colours: " + ", ".join([f"swing {s} slot 0x{extra[_st.key(v)]:X}" for s, v in
                                                       sorted(trail_swings.items())] +
                                                      [f"pitch {p} slot 0x{extra[_st.key(v)]:X}" for p, v in
                                                       sorted(trail_pitches.items())]))
    if custom_swings_on and star_bits and on("swing-items"):        # 12. Luma's Star Shower drops star bits (git-d9)
        import star_shower
        for hook, orig, fn in star_shower.HOOKS:                    # after starbits_item: calls its `drop`
            at = code.here + (-len(code.blob) % 4)
            body = fn(at).assemble()
            body += Asm(at + len(body)).b(hook + 4).assemble()
            assert code.put(body, align=4) == at
            patch_word(dol, hook, orig, Asm(hook).b(at).assemble_word())
        log.append(f"star shower (swing 15): {star_shower.DROPS} star bits per hit")
    if batter_depth:                                                # 11. step up / back in the box
        import batter_depth as bd
        base = code.here + (-len(code.blob) % 4)
        assert code.put(bd.apply(dol, base, data), align=4) == base
        log.append(f"batter depth hook at 0x{base:08X} (Nunchuk stick up/down, +-{bd.RANGE} m)")
    if on("mansion-day"):                                           # 12b. Luigi's Mansion by day too:
        import night_to_day
        log += night_to_day.tables(dol)                             # before new_stadium relocates tables
        log += night_to_day.hooks(dol, code, ghost_stadiums(haz["ghost"]))
    if stadium:                                                     # 12b. new stadium: tables, hooks, map
        more, stadium_tables = new_stadium.apply(dol, code, data, pairs,
                                                 stadium_defs if len(stadium_defs) > 1 else stadium_def)
        log += more
        import stadium_music                                        # its own BGM (docs/stadium-music.md)
        for d in stadium_defs:                                      # (each new stadium's hook chains the last)
            log += stadium_music.apply(dol, code, data, d, stadium_tables, src=game)
    if on("mansion-day"):
        log += night_to_day.nav(dol)                                # after new_stadium's map links
    import name_telop                                               # 13b. new names in the name banner (code;
    telop_row = name_telop.patch_code(dol, code) if on("new-ids") and chars else None   # art: output stage)
    text = bytes(code.blob)
    # the data section goes in before the plants: dino_piranhas reads and edits the new stadium's object
    # tables, which live in it (nothing is put in `data` after this point)
    spins = [ch for ch, f in HAZARD_FEATURES.items() if on(f)]      # a spinning hazard: spin_effect's hooks and
    if spins:                                                       # routine
        import creators.hazards
        spins = [ch for ch in spins if creators.hazards.uses_spin(haz[ch])]
    if spins:
        import spin_effect                                          # (idempotent: items may have placed them)
        spin_effect.ensure(dol, item_code, data)
    if data.blob:                                                   # (empty: no characters, no feature data)
        dol.add_section("data", DATA_BASE, bytes(data.blob))
    data_end = DATA_BASE + len(data.blob) + (-len(data.blob) % SECTION_ALIGN)   # the next section, arena low
    set_arena_low(dol, new_lo, data_end)
    new_lo = data_end
    log.append(f"data: 0x{len(data.blob):x} B at 0x{DATA_BASE:08X}, arena low 0x{new_lo:08X}")
    plants = ()                                                     # 9. Dino Piranha's plants (git-ce)
    if dino_plants:
        import dino_piranhas
        plants = in_build(dino_piranhas.ids(entries, char_defaults), valid, "piranha plants", log)   # "piranha_plants"
        written["piranha plants"] = plants
    if dino_plants and plants:
        text += bytes(DINO_CODE - CODE_BASE - len(text))
        dino_stadiums = tuple(dino_piranhas.STADIUMS)
        import creators.hazards
        plant = creators.hazards.plant_settings(haz["plant"])          # its constants for this build only
        saved = {k: getattr(dino_piranhas, k) for k in ("LISTS", "LIST_COUNTS", "INST_TABLES", "BYTE_TABLES",
                                                         "BITE_RADIUS", "OFF", "SHOW_PIPES", "EFFECT", "SPIN_FRAMES",
                                                         "RUNNERS_ON")}
        for k in ("BITE_RADIUS", "OFF", "SHOW_PIPES", "EFFECT", "SPIN_FRAMES", "RUNNERS_ON"):
            setattr(dino_piranhas, k, plant[k])
        if stadium:   # its per-stadium edits go into the new stadium's (longer) object tables, and the new
            #           stadium gets the template's plants (it runs the template's controller class)
            for k, v in new_stadium.dino_tables(stadium_tables).items():
                setattr(dino_piranhas, k, v)
            d = stadium_defs[0]                                     # the first new stadium only: each stadium's
            tname = next(n for n, (i, _) in dino_piranhas.STADIUMS.items() if i == d["template"])   # plants take a
            dino_piranhas.STADIUMS["new_stadium"] = (d["id"], dino_piranhas.STADIUMS[tname][1])     # fixed buffer,
            dino_stadiums += ("new_stadium",)                       # and a second one's ran into our data section
            if len(stadium_defs) > 1:                               # (0x807EF440 > ITEMS_BASE 0x807EF000)
                log.append(f"piranha plants: not in stadium {stadium_defs[1]['id']} (the second new stadium: no room "
                           "for its plant buffers yet)")
        try:
            dcode, ddata, dend = dino_piranhas.apply(
                dol, DINO_CODE, plants=plant["plants"], stadiums=dino_stadiums,
                dat=game / "files/dt_na.dat", toc_dol=game / "sys/main.dol", dino=plants)
        finally:
            for k, v in saved.items():
                setattr(dino_piranhas, k, v)
            dino_piranhas.STADIUMS.pop("new_stadium", None)
        text += dcode
        lo_addr = min(a for a, _ in ddata)
        assert CODE_BASE + len(text) <= lo_addr and dend <= ITEMS_BASE, (
            f"Piranha Plants overlap our sections (code end 0x{CODE_BASE + len(text):08X}, "
            f"data 0x{lo_addr:08X}, buffers end 0x{dend:08X})")
        blob = bytearray(max(a + len(b) for a, b in ddata) - lo_addr)
        for a, b in ddata:
            blob[a - lo_addr:a - lo_addr + len(b)] = b
        dol.add_section("data", lo_addr, blob)
        log.append(f"piranha plants for {', '.join(f'0x{c:02X}' for c in plants)}: code 0x{len(dcode):x} B at 0x{DINO_CODE:08X}, "
                   f"data 0x{lo_addr:08X}-0x{lo_addr + len(blob):08X}, buffers to 0x{dend:08X}")
    if burn_off:                                                    # thrown balls that don't burn (not fire):
        import item_params                                          # last, so nothing placed moves
        log += item_params.burn_gate(dol, item_code, ice_item.LAYOUT["variant"], burn_off)
    if runner_off:                                                  # items that don't knock runners down (the
        import runner_hits                                          # Bill): last, so nothing placed moves
        log += runner_hits.apply(dol, item_code, ice_item.LAYOUT["variant"], runner_off)
    if item_code.blob:                                                  # the batting-item code section
        dol.add_section("text", ITEMS_BASE, bytes(item_code.blob))      # (below the data section: arena low is
        log.append(f"item code: 0x{len(item_code.blob):x} of 0x{ITEMS_SIZE:x} B at 0x{ITEMS_BASE:08X}")   # past both)
    stadium_slots = []                                              # 13-15 share one text section at the end
    if stadium:                                                     # the new stadium with each hazard (at most one)
        shooter_def = next((d for d in stadium_defs if d.get("octoombas")), stadium_def)
        walker_def = next((d for d in stadium_defs if d.get("bobombs")), stadium_def)
    if stadium and shooter_def.get("octoombas"):                    # 13. Octoombas in the new stadium
        # after the plants (it chains their loader stub and appends after their list records); its code,
        # data and the model's clean copy go in their own section at the data's end, the model's work buffer
        # right after it (runtime only), and arena low moves above both
        import octoomba_hazard
        dat, toc_dol = game / "files/dt_na.dat", game / "sys/main.dol"
        base = new_lo                                               # the data section's end
        work = base + OCTOOMBA_SECTION                              # the section must end below this
        work_end = work + len(octoomba_hazard.model_bytes(dat, toc_dol))
        region = Space(base, work)
        tables = dict(new_stadium.dino_tables(stadium_tables), FENCE=stadium_tables["fence"])
        import stadium_dimensions                                   # the night field's fence and shooters (15.)
        more, _ = octoomba_hazard.apply(dol, region, region, tables, dat, toc_dol, stadium=shooter_def["id"],
                                        work=work, **shooter_args(haz["shooter"], shooter_def))
        log += more
        stadium_slots.append(dol.add_section("text", base, bytes(region.blob)))
        arena = (work_end + 0xFFF) & ~0xFFF
        set_arena_low(dol, new_lo, arena)
        new_lo = arena
        log.append(f"octoombas: code+data 0x{len(region.blob):x} B at 0x{base:08X}, model work buffer "
                   f"0x{work:08X}-0x{work_end:08X}, arena low 0x{arena:08X}")
    if stadium and walker_def.get("bobombs"):                       # 14. Bob-ombs in the new stadium by day
        # the same layout above the Octoombas (or at the data's end without them): section, work buffers, arena
        import bobomb_hazard
        base = new_lo
        work = base + bobomb_hazard.BOBOMB_SECTION
        region = Space(base, work)
        tables = dict(new_stadium.dino_tables(stadium_tables), FENCE=stadium_tables["fence"])
        import stadium_dimensions                                   # the day field's fence (15.)
        more, work_end = bobomb_hazard.apply(dol, region, region, tables, stadium=walker_def["id"], work=work,
                                             **walker_args(haz["walker"], walker_def))
        log += more
        stadium_slots.append(dol.add_section("text", base, bytes(region.blob)))
        arena = (work_end + 0xFFF) & ~0xFFF
        set_arena_low(dol, new_lo, arena)
        new_lo = arena
        log.append(f"bob-ombs: code+data 0x{len(region.blob):x} B at 0x{base:08X}, work buffers "
                   f"0x{work:08X}-0x{work_end:08X}, arena low 0x{arena:08X}")
    fenced = [d for d in stadium_defs if d.get("dimensions")] if stadium else []
    if fenced:                                                      # 15. field dimensions by day / night
        # stadium_dimensions.py: the match-load hook and its stock / day / night blocks in their own section
        # (the last free text slot) above the Bob-ombs, arena low above it
        import stadium_dimensions
        base = new_lo
        region = Space(base, base + stadium_dimensions.SECTION)
        log += stadium_dimensions.apply(dol, region, fenced if len(fenced) > 1 else fenced[0], stadium_tables,
                                        stadium=fenced[0]["id"])
        stadium_slots.append(dol.add_section("text", base, bytes(region.blob)))
        set_arena_low(dol, new_lo, base + stadium_dimensions.SECTION)
        new_lo = base + stadium_dimensions.SECTION
        log.append(f"dimensions: 0x{len(region.blob):x} B at 0x{base:08X}, arena low 0x{new_lo:08X}")
    thrower = ()                                                    # 16. the Tantrum Toss (Boom Boom's star throw):
    if on("star-solo-toss"):                                        # "fielding ability" 13
        import boom_boom_star_throw
        thrower = in_build(boom_boom_star_throw.ids(entries, char_defaults), valid, "Tantrum Toss", log)
    written["Tantrum Toss"] = thrower
    if thrower:
        # boom_boom_star_throw.py: H1/H2 in the has-ball handler, the kind-9 pause wrapper and their data in
        # their own section above 13-15 (merged with them just below, so no extra text slot when they exist)
        base = new_lo
        region = Space(base, base + boom_boom_star_throw.SECTION)
        import ability_edits as ability_edits_mod                   # the ability gates it; the first one's backdrop;
        free = not ability_edits_mod.star("Tantrum Toss", ability_edits if on("ability-edits") else None)   # its star
        log += boom_boom_star_throw.apply(dol, region, thrower, star_cost=0 if free else boom_boom_star_throw.STAR_COST)
        names = {e["id"]: e["name"] for e in entries}
        log.append("Tantrum Toss (fielding ability 13): " + ", ".join(names.get(c, f"0x{c:02X}") for c in thrower))
        stadium_slots.append(dol.add_section("text", base, bytes(region.blob)))
        set_arena_low(dol, new_lo, base + boom_boom_star_throw.SECTION)
        new_lo = base + boom_boom_star_throw.SECTION
    if on("pitch-items") and 15 in pitches:                         # 18b. Bob-omb Drop (star pitch 15, NEW_ID): every
        import pitch_bobomb_drop                                    # build with +8 = 15 (a definition, a stock entry)
        base = new_lo                                               # its own section above 13-16, merged with them
        region = Space(base, base + pitch_bobomb_drop.SECTION)
        log += pitch_bobomb_drop.apply(dol, region)
        if len(stadium_slots) > 1:                                  # 7 text slots: merge 13-16 now to make room
            stadium_slots[:] = [dol.merge_sections(stadium_slots)]
        stadium_slots.append(dol.add_section("text", base, bytes(region.blob)))
        set_arena_low(dol, new_lo, base + pitch_bobomb_drop.SECTION)
        new_lo = base + pitch_bobomb_drop.SECTION
    if vanish_on and 16 in pitches:                                 # 18. the Vanishing Ball (star pitch 16; King Boo's
        import pitch_vanishing_ball                                 # by default, STOCK_DEFAULTS): its own section
        base = new_lo
        region = Space(base, base + pitch_vanishing_ball.SECTION)
        log += pitch_vanishing_ball.apply(dol, region)
        if len(stadium_slots) > 1:                                  # 7 text slots: merge 13-16 now to make room
            stadium_slots[:] = [dol.merge_sections(stadium_slots)]
        stadium_slots.append(dol.add_section("text", base, bytes(region.blob)))
        set_arena_low(dol, new_lo, base + pitch_vanishing_ball.SECTION)
        new_lo = base + pitch_vanishing_ball.SECTION
    if on("pitch-path") and 14 in pitches:                          # 18c. Luma's Launch Star (star pitch 14): every
        import pitch_launch_star                                    # build with +8 = 14
        base = new_lo                                               # its own section above 13-18, merged with them
        region = Space(base, base + pitch_launch_star.SECTION)
        log += pitch_launch_star.apply(dol, region)
        if len(stadium_slots) > 1:                                  # 7 text slots: merge 13-18 now to make room
            stadium_slots[:] = [dol.merge_sections(stadium_slots)]
        stadium_slots.append(dol.add_section("text", base, bytes(region.blob)))
        set_arena_low(dol, new_lo, base + pitch_launch_star.SECTION)
        new_lo = base + pitch_launch_star.SECTION
    if on("pitch-path") and 13 in pitches:                          # 18d. Rosalina's Gravity Well (star pitch 13):
        import pitch_gravity_well                                   # every build with it
        base = new_lo                                               # its own section above 13-18, merged with them
        region = Space(base, base + pitch_gravity_well.SECTION)
        log += pitch_gravity_well.apply(dol, region)
        if len(stadium_slots) > 1:                                  # 7 text slots: merge 13-18 now to make room
            stadium_slots[:] = [dol.merge_sections(stadium_slots)]
        stadium_slots.append(dol.add_section("text", base, bytes(region.blob)))
        set_arena_low(dol, new_lo, base + pitch_gravity_well.SECTION)
        new_lo = base + pitch_gravity_well.SECTION
    if bench:                                                       # 19. the bench player (bench.py, docs/bench.md)
        base = new_lo                                               # its own section above 13-18, merged with them
        region = Space(base, base + bench_mod.SECTION)
        no_dh = not bench_dh                                        # Game options: "Designated hitter" off: every new
        if boot_bench is not None and bench_preset is None:        # roster starts without a DH (DH_OFF), as a DR slot
            dh = boot_bench[1]                                      # with the DH himself in it would; players can still
            if no_dh:                                               # pick one on the positions screen
                dh = [bench_mod.DH_OFF if v == bench_mod.DH_PITCHER else v for v in dh]
            log += bench_mod.apply(dol, region, bench_msg, grid=bool(grid), preset=boot_bench[0], dh=dh, once=True)
        else:
            log += bench_mod.apply(dol, region, bench_msg, grid=bool(grid), preset=bench_preset,
                                   dh=(bench_mod.DH_OFF, bench_mod.DH_OFF) if no_dh else None)
        if no_dh:
            log.append("bench: no designated hitter by default (Game options)")
        if len(stadium_slots) > 1:                                  # 7 text slots: merge 13-18 now to make room
            stadium_slots[:] = [dol.merge_sections(stadium_slots)]
        stadium_slots.append(dol.add_section("text", base, bytes(region.blob)))
        set_arena_low(dol, new_lo, base + bench_mod.SECTION)
        new_lo = base + bench_mod.SECTION
    if on("cpu-pitching"):                                          # 19b. the level 5 / 6 pitch model's stubs
        import cpu_pitching                                         # (0x10F0 B: the item section overflowed with
        base = new_lo                                               # them in the quick-boot test builds): their
        region = Space(base, base + cpu_pitching.SECTION)           # own section above 13-19, merged with them
        log += cpu_pitching.apply_code(dol, region)
        if on("cpu-batter-track"):                                  # the level 5 batter's mind game: its stubs in
            import cpu_track                                        # this section too (its memory is zeroed by
            log += cpu_track.apply_mind(dol, region)                # the pitch model's match reset)
        if len(stadium_slots) > 1:                                  # 7 text slots: merge 13-19 now to make room
            stadium_slots[:] = [dol.merge_sections(stadium_slots)]
        stadium_slots.append(dol.add_section("text", base, bytes(region.blob)))
        set_arena_low(dol, new_lo, base + cpu_pitching.SECTION)
        new_lo = base + cpu_pitching.SECTION
        log.append(f"cpu pitching code: 0x{len(region.blob):x} of 0x{cpu_pitching.SECTION:x} B at 0x{base:08X}, "
                   f"arena low 0x{new_lo:08X}")
    if on("fielder-spots"):                                         # 19b+. dragged fielder spots (fielder_spots.py,
        import fielder_spots                                        # docs/fielder-spots.md): their own section, as 19
        base = new_lo
        region = Space(base, base + fielder_spots.SECTION)
        log += fielder_spots.apply(dol, region)
        if len(stadium_slots) > 1:                                  # 7 text slots: merge 13-19 now to make room
            stadium_slots[:] = [dol.merge_sections(stadium_slots)]
        stadium_slots.append(dol.add_section("text", base, bytes(region.blob)))
        set_arena_low(dol, new_lo, base + fielder_spots.SECTION)
        new_lo = base + fielder_spots.SECTION
    if on("cpu-items"):                                             # 19b2. the Shell / Fireball shot list's routine
        import cpu_items                                            # (its own section, as 19b: no room in the
        base = new_lo                                               # item section)
        region = Space(base, base + cpu_items.SHOT_SECTION)
        log += cpu_items.apply_shots(dol, region)
        if len(stadium_slots) > 1:
            stadium_slots[:] = [dol.merge_sections(stadium_slots)]
        stadium_slots.append(dol.add_section("text", base, bytes(region.blob)))
        set_arena_low(dol, new_lo, base + cpu_items.SHOT_SECTION)
        new_lo = base + cpu_items.SHOT_SECTION
        log.append(f"cpu items shot code: 0x{len(region.blob):x} of 0x{cpu_items.SHOT_SECTION:x} B at 0x{base:08X}, "
                   f"arena low 0x{new_lo:08X}")
    if on("cpu-rundown"):                                           # 19c. the rundown log's stubs (test builds:
        import cpu_rundown_log                                      # cpu_rundown_log.LOG_ENTRIES; the item section
        if cpu_rundown_log.LOG_ENTRIES:                             # has no room): their own section, as 19b; after
            base = new_lo                                           # the defense log, whose hook they chain
            region = Space(base, base + cpu_rundown_log.SECTION)
            log += cpu_rundown_log.apply_code(dol, region)
            if len(stadium_slots) > 1:
                stadium_slots[:] = [dol.merge_sections(stadium_slots)]
            stadium_slots.append(dol.add_section("text", base, bytes(region.blob)))
            set_arena_low(dol, new_lo, base + cpu_rundown_log.SECTION)
            new_lo = base + cpu_rundown_log.SECTION
            log.append(f"cpu rundown log code: 0x{len(region.blob):x} of 0x{cpu_rundown_log.SECTION:x} B at "
                       f"0x{base:08X}, arena low 0x{new_lo:08X}")
    if on("level-5"):                                               # 19e. our CPU state follows the replay's
        import replay_state                                         # snapshots (replay_state.py): own section
        regs = replay_state.regions(on)
        if regs:
            base = new_lo
            region = Space(base, base + replay_state.SECTION)
            log += replay_state.apply(dol, region, regs)
            if len(stadium_slots) > 1:
                stadium_slots[:] = [dol.merge_sections(stadium_slots)]
            stadium_slots.append(dol.add_section("text", base, bytes(region.blob)))
            set_arena_low(dol, new_lo, base + replay_state.SECTION)
            new_lo = base + replay_state.SECTION
    if features is not None and on("football-fielder10"):         # 19d. the football prototype's 10th fielder
        import football_fielder10                                   # (named only, as cpu-vs-cpu): its own section,
        base = new_lo                                               # as 19b
        region = Space(base, base + football_fielder10.SECTION)
        log += football_fielder10.apply(dol, region)
        if len(stadium_slots) > 1:
            stadium_slots[:] = [dol.merge_sections(stadium_slots)]
        stadium_slots.append(dol.add_section("text", base, bytes(region.blob)))
        set_arena_low(dol, new_lo, base + football_fielder10.SECTION)
        new_lo = base + football_fielder10.SECTION
        log.append(f"football fielder 10 code: 0x{len(region.blob):x} of 0x{football_fielder10.SECTION:x} B at "
                   f"0x{base:08X}, arena low 0x{new_lo:08X}")
    if features is not None and on("kicking-challenge"):          # 19e. the kicking challenge (named only): its
        import kicking_challenge                                    # own section, as 19b
        base = new_lo
        region = Space(base, base + kicking_challenge.SECTION)
        log += kicking_challenge.apply(dol, region, game / "files/dt_na.dat")
        if len(stadium_slots) > 1:
            stadium_slots[:] = [dol.merge_sections(stadium_slots)]
        stadium_slots.append(dol.add_section("text", base, bytes(region.blob)))
        set_arena_low(dol, new_lo, base + kicking_challenge.SECTION)
        new_lo = base + kicking_challenge.SECTION
        log.append(f"kicking challenge code: 0x{len(region.blob):x} of 0x{kicking_challenge.SECTION:x} B at "
                   f"0x{base:08X}, arena low 0x{new_lo:08X}")
    if features is not None and on("cricket"):                    # 19g. cricket (named only): its own section,
        import cricket                                              # as 19b
        base = new_lo
        region = Space(base, base + cricket.SECTION)
        log += cricket.apply(dol, region)
        if len(stadium_slots) > 1:
            stadium_slots[:] = [dol.merge_sections(stadium_slots)]
        stadium_slots.append(dol.add_section("text", base, bytes(region.blob)))
        set_arena_low(dol, new_lo, base + cricket.SECTION)
        new_lo = base + cricket.SECTION
        log.append(f"cricket code: 0x{len(region.blob):x} of 0x{cricket.SECTION:x} B at 0x{base:08X}, arena low "
                   f"0x{new_lo:08X}")
    if on("captain-faceoff"):                                       # 19f. the captain faceoff before the walkout
        import captain_faceoff                                      # (captain_faceoff.py): its own section, as 19b
        base = new_lo
        region = Space(base, base + captain_faceoff.SECTION)
        log += captain_faceoff.apply(dol, region)
        if region.blob:
            if len(stadium_slots) > 1:
                stadium_slots[:] = [dol.merge_sections(stadium_slots)]
            stadium_slots.append(dol.add_section("text", base, bytes(region.blob)))
            set_arena_low(dol, new_lo, base + captain_faceoff.SECTION)
            new_lo = base + captain_faceoff.SECTION
    if grid_square and (on("new-ability-slot") or on("star-solo-toss") or on("clamber-solo-jump")):   # new abilities'
        #                                                           labels (rows: add_name_art)
        log += abilities.patch_labels(dol, max_id)
    if labels_on:
        import star_move_labels                                     # King Bob-omb's star moves: "Kingly Kaboom"
        log += star_move_labels.patch_tables(dol, max_id, kaboom=0x78 in valid)   # (STAR_MOVES_TO)
        log += swing_card.patch(dol, item_card)                     # 17a. after Kingly Kaboom's slot 7
    if captain_lines and labels_on:                                 # captain select's label tables (DOL only, so
        import star_move_labels                                     # a dry run's DOL has them): "Kingly Kaboom",
        log += star_move_labels.patch_captain_tables(dol, kaboom=0x78 in valid)   # Clamber Jump; rows: patch_layouts
        if swing_card:
            log += swing_card.patch_captain(dol)                    # 17a. custom swing / pitch names on captain select
        if item_card:
            log += item_card.patch_captain(dol)                     # 17. hitting / item rows, 4th line on captain select
    if len(stadium_slots) > 1:                                      # the DOL has 7 text slots: 13-16 as one
        start = min(dol.addrs[i] for i in stadium_slots)
        slot = dol.merge_sections(stadium_slots)
        log.append(f"stadium sections 13-15 merged into one text section 0x{start:08X}-0x{start + dol.sizes[slot]:08X} "
                   f"(work buffers zero-filled), {len(stadium_slots) - 1} text slots freed")
    if text:
        dol.add_section("text", CODE_BASE, text)
    if not (text or data.blob or item_code.blob or stadium_slots):   # nothing placed: arena low stays stock
        for addr, word in stock_arena.items():
            dol.w32(addr, word)
        new_lo = ARENA_LO
        log.append("nothing placed above the stock arena: arena low stays 0x807B6E80 / 0x807B4E80")
    log.append("DOL text sections used: " + str(sum(1 for i in range(7) if dol.sizes[i])) + " of 7")
    written.update({"mini-map decoys": decoys, "card labels": [c["id"] for c in label_chars] if labels_on else []})
    log += check_ids(written, valid | ({ring["id"]} if ring else set()))   # (the Pom Pom ring's stand-in id)

    global LAST_GECKO_MAP                                           # the players' Gecko codes (gecko_fix.py): what
    LAST_GECKO_MAP = gecko_map(dol, Dol(game / "sys/main.dol"), features, new_lo)   # moved, what we changed
    if dry_run:                     # everything above ran; the output folder's steps (icon bank, layouts,
        if dry_run is not True:     # the voice archive) did not
            dol.save(dry_run)
        log.append(f"dry run: no output folder written (DOL {'saved to ' + str(dry_run) if dry_run is not True else 'not saved'})")
        return log
    out = Path(out)
    # never rebuild into an existing folder: Dolphin may be running it (Windows doesn't lock it, and a
    # rebuilt luigi-cf-4 crashed Nick's game with "The disc could not be read")
    assert not out.exists(), f"{out} already exists; build into a new folder"
    shutil.copytree(game, out, copy_function=_link_or_copy)
    if stadium:
        import stadium_music                                        # a new stream file, if the stadium has one
        for d in stadium_defs:
            log += stadium_music.add_files(out, d, src=game)
    # 6. icon source records live in dt_na.dat: give the output its own copy (the shared
    #    Extra Innings file must never change) and append the extended icon bank to it.
    dat = out / "files/dt_na.dat"
    _unlink(dat)
    shutil.copyfile(game / "files/dt_na.dat", dat)
    try:
        import base_textures
        log += base_textures.apply(game, dat)
    except Exception as e:
        log.append(f"base textures: skipped ({type(e).__name__}: {e})")
    with open(dat, "r+b") as f:
        for off, blob in appended:
            f.seek(off)
            f.write(blob)
        if chars:
            # the icon bank moves to the new end of the file, where it can grow
            w = struct.unpack(">12I", dol.read(ICON_RECORD, 48))
            f.seek(w[2])
            bank = f.read(w[1])
            f.seek(icon_bank_off)
            f.write(bank)
    if chars:                                                       # (no characters: the stock icon bank)
        for lang in range(3):
            dol.w32(ICON_RECORD + 8 + 16 * lang, icon_bank_off)
        for c in chars:
            if c["model_overlay"]:
                log.append(f"model {c['model_overlay']}: dir {c['model_dir']}")
        bank_off, bank_len, tables_len = extend_icon_bank(dol, dat, chars + ([ring] if ring else []))
        log.append(f"icon bank at dt_na.dat+0x{bank_off:x}: normal_a/side/front tables now 0x{tables_len:x} B "
                   "(in place)")
    if grid_square:
        import wheel7                                               # + the 7-member wheel popup frame
        import star_move_labels
        finish = item_card.layout_bytes if item_card else (lambda data: data)   # 17: after every other row
        if bench:                                                   # 19b. + the bench's roster slot and defense cell
            finish = (lambda f: lambda data: bench_mod.layout_bytes(f(data), screen_dx=gridcells.screen_dx(grid)))(finish)
        wheel = wheel7.layout_bytes if big_wheels else (lambda data: data)
        labels = ((lambda data: star_move_labels.layout_bytes(data, max_id, label_chars)) if labels_on
                  else (lambda data: data))
        log += gridcells.patch_layout(dol, dat, extra=lambda data: finish(wheel(
            labels(char_names.add_name_art(data, chars, renames)))), grid=grid)
        if item_card:
            log.append(f"item ability rows {item_card.first_row}.. (icon, then {len(item_abilities.labels(item_card.chars))} labels)")
        log += char_names.patch_challenge_layout(dol, dat)          # Clamber Jump in Challenge mode (dir 119 file 12)
        log.append(f"name labels  {len(chars)} names on a new page, rows {char_names.NAME_ROW_BASE}.."
                   f"{char_names.NAME_ROW_BASE + max_id - char_names.FIRST_NEW} (dir 119 file 19, every language)")
    elif big_wheels:
        import wheel7                                               # the wheel popup frames without the select screen
        log += gridcells.patch_layout(dol, dat, extra=wheel7.layout_bytes, grid=None)
    if captain_lines:
        import star_move_labels                                     # + "Kingly Kaboom" on captain select (file 18)
        import menu_purple                                          # + the purple menu background (file 1, Nick)
        cap18 = star_move_labels.captain_layout_bytes if labels_on else (lambda data: data)
        if item_card:                                               # + the hitting / item rows and the 4th line
            cap18 = (lambda f, g: lambda data: g(f(data)))(cap18, item_card.captain_layout_bytes)
        log += captains.patch_layouts(dol, dat, extra={captains.FILE_CAPTAIN: cap18, **(
            {captains.FILE_LOGO: menu_purple.layout_for(menu_color)} if on("menu-color") else {})})
    elif captains.STOCK_RENAMED:                                    # captains off: a renamed stock captain's plate
        log += captains.patch_layouts(dol, dat)
        if on("menu-color"):
            import menu_purple
            log += menu_purple.patch_layout(dol, dat, menu_color)
    elif on("menu-color"):                                          # the menu colour alone (no new characters needed)
        import menu_purple
        log += menu_purple.patch_layout(dol, dat, menu_color)
    if on("menu-color"):                                            # the plain line (an edition shows only this one)
        import menu_purple
        log.append(f"menu background color: {(menu_color or menu_purple.DEFAULT).strip()}")
    if on("level-5"):                                               # the "Level 5" button art (dir 119 file 4)
        log += level5_menu.patch_layout(dol, dat)
    if telop_row:                                                   # 13b. the name banner's art (file 1, after
        more, telop_base = name_telop.add_art(dol, dat, chars, renames)      # captains' and the menu colour's rows)
        log += more
        name_telop.set_rows(dol, telop_row, telop_base)
    if star_bits:                                                   # 12b. Star Bits HUD icon (dir 119 file 8)
        log += starbits_roulette.patch_layout(dol, dat, **({"png": koopa_items.icon_png(ground["star-bits"], dol, dat,
                                                                              Path(__import__("tempfile").gettempdir())
                                                                              / "sluggers-item-icons")}
                                                           if "star-bits" in ground else {}))
    if star_bits and variants:                                      # Ice + Koopaling icons (appended copies)
        ice_edit = next((s for s in balls if s["id"] == ice_item.ICE), None)
        log += ice_item.patch_layout(dol, dat, **(dict(more=koopa_items.all_icons(customs) if customs else
                                                       koopa_items.icons) if koopas else {}),
                                     **({"first": lambda blob: koopa_items.custom_icons(blob, [ice_edit])[ice_item.ICE]}
                                        if ice_edit else {}))
        log += ice_item.add_freeze_effect(dol, dat)                # the ice block in every stadium's effects
        colours = {k: v for k, v in item_args(balls, skip).items() if k in ("hues", "ice")} if balls or dropped \
            else dict(hues=koopa_items.HUES)
        log += ice_item.add_blue_textures(dol, dat, **(colours if koopas else {}))   # colours
    elif _ice is not None and _ice.SLOT_REQUESTS:                                                # extra particle slots alone (no trail colours)
        log += _ice.add_blue_textures(dol, dat, turns=())
    if chance_cheer:                                                # 12c. STAR CHANCE! banner for Pauline's cheer
        import pauline_chance_tuning                                # (after ice_item: it asserts the stock row count)
        log += pauline_chance_tuning.patch_layout(dol, dat, png=work_file("pauline_chance/star_chance.png"))
    if features is not None and on("kicking-challenge"):          # 19e. the kicking challenge's banners (GOOD! /
        import kick_art                                             # NO GOOD over HOME RUN! / FOUL!) and Mario
        log += kick_art.patch_dtna(dol, dat, game / "files/dt_na.dat")   # Stadium without its foul poles
    if features is not None and on("cricket"):                    # 19g. cricket's FOUR! banner over FOUL!
        import cricket_art
        log += cricket_art.patch_dtna(dol, dat, game / "files/dt_na.dat")
    if voices:
        brsar = out / "files/sound_NA/MY2.brsar"
        _unlink(brsar)                           # hardlink to the base's archive
        shutil.copyfile(voice_brsar, brsar)
        if chance_cheer and json.loads(voice_ids.read_text(encoding="utf8")).get("pauline_chance") is not None:
            import pauline_chance                # her jingle is an external stream file the archive points at
            log += pauline_chance.add_files(out)
    _unlink(out / "sys/main.dol")  # break the hardlink before writing
    dol.save(out / "sys/main.dol")
    log.append(f"code 0x{len(code.blob):x} B at 0x{CODE_BASE:08X}, data 0x{len(data.blob):x} B at 0x{DATA_BASE:08X}, "
               f"arena low 0x{new_lo:08X}")
    log.append("characters: " + ", ".join(f"0x{c['id']:02X} {c['name']} (template 0x{c['template']:02X})" for c in chars))
    log.append(f"wrote {out / 'sys/main.dol'}")
    return log
