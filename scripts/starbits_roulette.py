"""Star Bits (item id 6, the cut Thunder slot) in the batting-item roulette and its HUD.

Another module writes what the item does; this one lets the roulette roll id 6 and makes the HUD show it.

a. Roulette FUN_804583c4 (only caller 0x80455674): its first word becomes a branch to PICK, a 7-item
   version of the same logic. Row = score-difference bucket as stock (d = byte *(r13-0x1544)+0x8E minus
   word +0: row 2 if d < 3, 1 if 3..5, 0 if >= 6), weights from a new 3 x 7 u8 table (the stock 6 columns
   of 0x80630FB0 plus WEIGHTS for id 6), an item's weight counts only if FUN_8045453c(i) says it is
   enabled (the same challenge-list / settings flags the stock loop reads inline), r = FUN_80165c14(rng
   *(r13-0x1578), total) in [0, total), and the pick is the first i with r < (running sum). Stock quirk
   dropped: stock compared r <= w, so r = 0 gave a Shell even with Shells switched off and every item
   got its weight except Shell +1 / last enabled item -1; now each item gets exactly its weight. With
   everything off (total 0) it still returns 0 (Shell), as stock. No extsb, so the total may exceed 127.
b. Enable flag FUN_8045453c(id): its first word branches to ENABLE, which answers 1 for id 6 (when any
   row gives it weight) and runs the stock body otherwise. Save data and challenge lists are untouched;
   callers besides the roulette and the rolling list (0x803CC440 / 0x803CC608 / 0x804AEB3C) map their
   own indices through FUN_804ac354 and never ask for 6.
c. Rolling list CS2d_Player_NextItem (ctor FUN_8033280c, update FUN_80332940): the enabled-id list was
   6 words at +0xCC with the count at +0xE4, so a 7th entry would land on the count. The object grows
   0xF4 -> 0x110 (allocation 0x80337DAC) and the list moves to +0xF4 (7 words): the ctor's store and its
   loop bound, and the two reads in the update. The update's `cmpwi r28,6` at 0x80332D08 / 0x80332E54
   are retry counters for "pick a different random entry", not item bounds, and stay.
d. "Valid item" checks: every inlined `slot item (manager+0x338 + slot*0xC) in 0..5` check becomes 0..6
   (VALID_SITES, 28 cmpwi words; found by scanning for lwz 0x338 followed by cmpwi 6).
e. Icon: the per-id sprite-row table 0x8062CE10 (u16, 7 entries, lhax) has 0 for id 6; it becomes 0xF9.
   Row 0xF9 of the in-game HUD layout (dt_na.dat dir 119 file 8; rows 0xF3..0xF8 are the six item
   icons in 0x8062CE10's order) is Thunder's unused lightning icon: a 27 x 29 cell at (29, 964) of a
   1024 x 1024 CI8 atlas shared by 75 texture pages, with its own 256-entry RGB5A3 palette (page 216,
   used by no other row; no other row samples that cell). patch_layout() redraws the cell's indices and
   rewrites that palette with the Star Bits icon (ICON_PNG, drawn by draw_icon()) in each language's copy,
   in place (sizes do not change, so the index records stay as they are).
   Texture descriptor offsets (image, palette) in these files count from +0x20 (the u32 at +0), not
   from the file start: decoding at +0 gives cells shifted one 8-px tile and garbled palettes.
"""
import hashlib
import struct
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
from ppc import Asm  # noqa: E402
from creators import items as _presets  # noqa: E402

ROOT = Path(__file__).resolve().parent.parent
STAR_BITS = 6

PICK_FN, PICK_FN_ORIG = 0x804583C4, 0x9421FFE0          # stwu r1,-0x20(r1)
STOCK_WEIGHTS, STOCK_ROW_LEN = 0x80630FB0, 6
STOCK_TABLE_WORDS = [(0x80458408, 0x3C608063), (0x80458414, 0x38630FB0), (0x8045840C, 0x1C800006)]
ENABLED_FN, ENABLED_FN_ORIG = 0x8045453C, 0x808DF180     # lwz r4,-0xe80(r13)
RNG_FN = 0x80165C14                                      # FUN_80165c14(rng, n) -> |rand % n|, 0 if n <= 1
N_ITEMS = 7
DEFAULT_WEIGHT = _presets.block("star-bits", "given")["roulette"][0]   # 15; stock columns are 10..20 per row

# c. rolling list
LIST_ALLOC = (0x80337DAC, 0x386000F4, 0x38600110)        # li r3,0xF4 -> 0x110 (FUN_80521224 size)
NEW_LIST = 0xF4
LIST_SITES = [
    (0x803328F0, 0x93C300CC, 0x93C30000 | NEW_LIST),      # ctor: stw r30,0xcc(r3)
    (0x80332904, 0x2C1E0006, 0x2C1E0007),                 # ctor: cmpwi r30,6 (ids 0..5 -> 0..6)
    (0x80332CFC, 0x80C300CC, 0x80C30000 | NEW_LIST),      # update state 1: lwz r6,0xcc(r3)
    (0x80332E04, 0x80C300CC, 0x80C30000 | NEW_LIST),      # update state 3: lwz r6,0xcc(r3)
]

# d. `cmpwi rX,6` in the inlined "manager+0x338 slot item is 0..5" checks (function, register)
VALID_SITES = [
    (0x80312BE8, 0x2C1E0006),                                                          # FUN_80312aac
    (0x80323758, 0x2C030006), (0x80323774, 0x2C030006),
    (0x8032D304, 0x2C000006), (0x8032D320, 0x2C000006),
    (0x8032EE34, 0x2C000006), (0x8032EE50, 0x2C000006),
    (0x8032EF68, 0x2C000006), (0x8032EF84, 0x2C000006),
    (0x8032F0F8, 0x2C000006), (0x8032F114, 0x2C000006),
    (0x80332140, 0x2C030006), (0x8033215C, 0x2C030006),
    (0x80332418, 0x2C030006), (0x80332434, 0x2C030006),
    (0x80332724, 0x2C030006), (0x80332740, 0x2C030006),
    (0x80332BB4, 0x2C030006), (0x80332BD0, 0x2C030006),                               # FUN_80332940
    (0x80332C9C, 0x2C030006), (0x80332CB8, 0x2C030006),
    (0x80332E3C, 0x2C000006),
    (0x80332F28, 0x2C000006),
    (0x80333310, 0x2C030006), (0x8033332C, 0x2C030006),                               # FUN_803330a4
    (0x803333B0, 0x2C000006),
    (0x8033393C, 0x2C030006), (0x80333958, 0x2C030006),
]

# e. icon
ICON_TABLE_ID6 = (0x8062CE1C, 0x00000000, 0x00F90000)    # u16 id 6 = row 0xF9, then 2 pad bytes
ICON_TABLE = 0x8062CE10
# f. the icon table's readers, each `lis rX,0x8063` + `subi rX,rX,0x31F0` (= 0x8062CE10), for a longer
# table (forced items, ids 8..). NextItem state 5 (0x80332F58) also reads entry -1 for an empty slot, so the
# new table keeps a zero halfword before entry 0.
ICON_READERS = [(0x80312C04, 0x3C608063, 0x80312C14, 0x3863CE10), (0x80332D14, 0x3CA08063, 0x80332D24, 0x38A5CE10),
                (0x80332D88, 0x3C608063, 0x80332D98, 0x3863CE10), (0x80332E60, 0x3CA08063, 0x80332E70, 0x38A5CE10),
                (0x80332ED4, 0x3C608063, 0x80332EE4, 0x3863CE10), (0x80332F3C, 0x3CA08063, 0x80332F48, 0x38A5CE10),
                (0x803333CC, 0x3C608063, 0x803333DC, 0x3863CE10), (0x80349AB4, 0x3C608063, 0x80349AC4, 0x3863CE10)]
LAYOUT_DIR, LAYOUT_FILE, ICON_ROW = 119, 8, 0xF9
CELL = (29, 964, 56, 993)                                # x0, y0, x1, y1 (exclusive) in the atlas
ICON_PNG = ROOT / "captains/starbits_icon.png"          # 27 x 29 RGBA, made by draw_icon()
# sha1 of the stock cell's 27 x 29 indices + its 512-byte palette (all three languages agree)
STOCK_CELL_SHA1 = "678a81354b953512a342d8088d8ff6028283ac81"


def _row_weights(weights, what):
    w = [weights] * 3 if isinstance(weights, int) else list(weights)
    assert len(w) == 3 and all(0 <= x <= 255 for x in w), f"{what} weight: an int or 3 ints 0..255"
    return w


def odds_ids(odds, n=None):
    """The patcher option "item-odds" ({item: weight}) -> {item id: [3 row weights]}. An item is a
    batter_items.NAMES name ("shell", ..., "starbits", "ice") or its id; a weight is an int (every
    score-difference row) or 3 ints (rows 0..2, as the stock table), 0 = never rolled. n: the items this build
    can roll (ids 0..n-1: the rolled ones and apply's forced ones, e.g. the Koopalings' items 8..13); an item
    past them isn't in its roulette (its feature is off)."""
    import batter_items
    out = {}
    for item, w in (odds or {}).items():
        iid = batter_items.item_id(item)
        assert n is None or 0 <= iid < n,             f"item-odds: {item!r} isn't rolled in this build (rolled: ids 0..{n - 1})"
        out[iid] = _row_weights(w, f"item-odds {item!r}")
    return out


def weight_table(weights=DEFAULT_WEIGHT, dol=None, extra=(), odds=None, forced=()):
    """3 rows x (7 + len(extra)) u8: the stock 6 columns (read from the DOL when given), id 6's weight,
    then each extra item's (ids 7..) per row. odds: the "item-odds" option (odds_ids), replacing those
    items' columns. forced: apply's forced ids; when odds gives one of them a weight, the table runs through
    every forced id (0 unless given), so they are rolled like the others."""
    cols = [_row_weights(weights, "Star Bits")] + [_row_weights(e[1], f"item {e[0]}") for e in extra]
    if dol is not None:
        stock = dol.read(STOCK_WEIGHTS, 3 * STOCK_ROW_LEN)
    else:
        stock = bytes.fromhex("1414140a140a" "140f140f0f0f" "140f0f140f0f")
    n = N_ITEMS + len(extra)
    ids = odds_ids(odds, n + len(forced))
    m = n + len(forced) if any(i >= n and any(w) for i, w in ids.items()) else n
    table = bytearray(b"".join(stock[r * 6:r * 6 + 6] + bytes(c[r] for c in cols) + bytes(m - n) for r in range(3)))
    for iid, w in ids.items():
        if iid < m:                                                      # (a forced id at 0: not rolled)
            for r in range(3):
                table[r * m + iid] = w[r]
    return bytes(table)


STOCK_MAX_TOTAL = 127      # the stock pick sign-extends the roll (extsb r3 at 0x80458530): a row may total 127


def stock_odds(dol, odds):
    """The "item-odds" option for a build without this roulette (no new-roulette-item): the stock table
    0x80630FB0 (ids 0..5) edited in place. The stock pick keeps its quirk (r <= w: Shell one more, the last
    enabled item one less) and each row may total at most STOCK_MAX_TOTAL. Returns log lines."""
    ids = odds_ids(odds, STOCK_ROW_LEN)
    if not ids:
        return []
    for addr, word in STOCK_TABLE_WORDS:
        assert dol.u32(addr) == word, f"0x{addr:08X}: stock roulette table load changed"
    table = bytearray(dol.read(STOCK_WEIGHTS, 3 * STOCK_ROW_LEN))
    for iid, w in ids.items():
        for r in range(3):
            table[r * STOCK_ROW_LEN + iid] = w[r]
    for r in range(3):
        total = sum(table[r * STOCK_ROW_LEN:(r + 1) * STOCK_ROW_LEN])
        assert total <= STOCK_MAX_TOTAL, f"item-odds: row {r} totals {total} (the stock roulette takes {STOCK_MAX_TOTAL})"
    dol.write(STOCK_WEIGHTS, bytes(table))
    rows = " / ".join(" ".join(str(b) for b in table[r * 6:r * 6 + 6]) for r in range(3))
    return [f"item odds (stock roulette 0x{STOCK_WEIGHTS:08X}): {rows}"]


def pick_code(base, table, n_items=N_ITEMS):
    """PICK: r3 = rolled item 0..n_items-1 (see a.)."""
    a = Asm(base)
    a.stwu(1, -0x30, 1).mflr(0).stw(0, 0x34, 1)
    a.stw(31, 0x2C, 1).stw(30, 0x28, 1).stw(29, 0x24, 1)
    a.lwz(4, -0x1544, 13).lwz(3, 0, 4).lbz(0, 0x8E, 4).subf(0, 3, 0)    # d = byte +0x8E - word +0
    a.li(3, 2).cmpwi(0, 3).blt("row")
    a.li(3, 1).cmpwi(0, 6).blt("row")
    a.li(3, 0)
    a.label("row")
    a.mulli(3, 3, n_items).load_addr(31, table).add(31, 31, 3)          # r31 = this row's weights
    a.li(30, 0).li(29, 0)                                                # r30 = i, r29 = total
    a.label("weigh")
    a.mr(3, 30).bl(ENABLED_FN)
    a.li(0, 0).cmpwi(3, 0).beq("off")
    a.lbzx(0, 31, 30)
    a.label("off")
    a.addi(4, 1, 8).stbx(0, 4, 30)                                       # w[i] at r1+8+i
    a.add(29, 29, 0)
    a.addi(30, 30, 1).cmpwi(30, n_items).blt("weigh")
    a.lwz(3, -0x1578, 13).mr(4, 29).bl(RNG_FN)                           # r3 = r in [0, total)
    a.li(30, 0).addi(5, 1, 8)
    a.label("pick")
    a.lbzx(0, 5, 30).cmpw(3, 0).blt("done")                              # r < w[i]: item i
    a.subf(3, 0, 3)
    a.addi(30, 30, 1).cmpwi(30, n_items).blt("pick")
    a.li(30, 0)                                                          # total 0: Shell, as stock
    a.label("done")
    a.mr(3, 30)
    a.lwz(29, 0x24, 1).lwz(30, 0x28, 1).lwz(31, 0x2C, 1)
    a.lwz(0, 0x34, 1).mtlr(0).addi(1, 1, 0x30).blr()
    return a


def enable_code(base, star_on=True, extra=(), first_forced=None, rolled=(), extra_on=None):
    """ENABLE: FUN_8045453c(id) with id 6 answering star_on, and each extra item (id, weights,
    enable_as, icon row) answering whatever the stock body says for id enable_as (0 when extra_on says it has
    no weight, so the rolling list leaves it out). rolled: [(forced id, enable_as)] that item-odds gives a
    weight, enabled like the extra items; every other forced id (first_forced..) answers 0."""
    a = Asm(base)
    a.cmpwi(3, STAR_BITS).bne("extra")
    a.li(3, int(bool(star_on))).blr()
    a.label("extra")
    for k, (item, enable_as) in enumerate(rolled):
        a.cmpwi(3, item).bne(f"f{k}").li(3, enable_as).b("stock")
        a.label(f"f{k}")
    if first_forced is not None:                                         # forced-only ids: never enabled
        a.cmpwi(3, first_forced).blt("rolled").li(3, 0).blr()
        a.label("rolled")
    for k, (item, _, enable_as, _) in enumerate(extra):
        if extra_on is not None and not extra_on[k]:
            a.cmpwi(3, item).bne(f"x{k}").li(3, 0).blr()                # weight 0 everywhere: off
        else:
            a.cmpwi(3, item).bne(f"x{k}").li(3, enable_as).b("stock")
        a.label(f"x{k}")
    a.label("stock")
    a.word(ENABLED_FN_ORIG).b(ENABLED_FN + 4)
    return a


def _patch(dol, addr, expect, new):
    got = dol.u32(addr)
    assert got == expect, f"0x{addr:08X}: expected {expect:08X}, found {got:08X}"
    dol.w32(addr, new)


def _place(space, build):
    """Assemble build(addr) at the next 4-aligned address of space; -> addr."""
    at = space.here + (-space.here % 4)
    blob = build(at).assemble()
    got = space.put(blob, 4)
    assert got == at, f"code placed at 0x{got:08X}, assembled for 0x{at:08X}"
    return at


def _branch(src, dst):
    return Asm(src).b(dst).assemble_word()


def _enable_as(f):
    """A forced entry (id, icon row[, enable_as]) -> the stock item whose settings switch enables it when rolled
    (default: the item it is built on, koopa_items.VARIANTS)."""
    if len(f) > 2:
        return f[2]
    import koopa_items
    base = dict(koopa_items.VARIANTS).get(f[0])
    assert base is not None, f"forced id {f[0]}: no stock item to enable it as (pass (id, icon row, enable_as))"
    return base


def apply(dol, code, data, weights=DEFAULT_WEIGHT, extra=(), forced=(), odds=None):
    """Patch main.dol (a..e). code / data: Space-like allocators (.here, .put(bytes, align) -> addr).
    weights: Star Bits' roulette weight, an int or one per score-difference row (0 = never rolled).
    extra: more items after id 6, [(id, weights, enable_as, icon row)] with ids 7, 8, ... (only one
    fits the icon table's pad halfword, id 7): rolled like the others, enabled whenever item enable_as
    is, shown with that icon row. Their behaviour is another module's (e.g. ice_item.py).
    forced: [(id, icon row[, enable_as])] for ids after the extra ones that are not rolled by default (weight 0,
    not in the rolling list, FUN_8045453c says off) but can be given (batter_items FIXED_ITEM) and shown: the item
    checks accept them (d. bound) and the icon table moves to our data with their rows (f.).
    odds: the patcher option "item-odds" ({item name or id: weight}, odds_ids), over the other weights; no
    option, no change. A forced id it gives a weight is rolled: the pick and the rolling list run through every
    forced id, and FUN_8045453c enables it whenever its stock item (enable_as, default koopa_items.VARIANTS) is. Returns log lines. The icon art itself is patch_layout(dol, dat_path)."""
    assert [e[0] for e in extra] == list(range(N_ITEMS, N_ITEMS + len(extra))), "extra ids must be 7, 8, ..."
    assert len(extra) <= 1, "the icon table has room for id 7 only"
    n = N_ITEMS + len(extra)
    assert [f[0] for f in forced] == list(range(n, n + len(forced))), f"forced ids must be {n}, {n + 1}, ..."
    n_all = n + len(forced)
    for addr, word in STOCK_TABLE_WORDS:
        assert dol.u32(addr) == word, f"0x{addr:08X}: stock roulette table load changed"
    table_bytes = weight_table(weights, dol, extra, odds, forced)
    table = data.put(table_bytes, 4)
    m = len(table_bytes) // 3                                            # rolled: n, or n_all (a forced id weighted)
    has = lambda i: any(table_bytes[r * m + i] for r in range(3))
    star_on = has(STAR_BITS)
    rolled = [(f[0], _enable_as(f)) for f in forced if f[0] < m and has(f[0])]
    pick = _place(code, lambda at: pick_code(at, table, m))
    enable = _place(code, lambda at: enable_code(at, star_on, extra, n if forced else None, rolled,
                                                 [has(e[0]) for e in extra]))

    _patch(dol, PICK_FN, PICK_FN_ORIG, _branch(PICK_FN, pick))
    _patch(dol, ENABLED_FN, ENABLED_FN_ORIG, _branch(ENABLED_FN, enable))
    size = NEW_LIST + 4 * m                                              # 0x110 for 7 items
    _patch(dol, LIST_ALLOC[0], LIST_ALLOC[1], (LIST_ALLOC[1] & ~0xFFFF) | size)
    for addr, stock, new in LIST_SITES:
        _patch(dol, addr, stock, (new & ~0xFFFF) | m if new >> 16 == 0x2C1E else new)
    for addr, word in VALID_SITES:
        _patch(dol, addr, word, (word & ~0xFFFF) | n_all)
    icon7 = extra[0][3] if extra else 0
    _patch(dol, ICON_TABLE_ID6[0], ICON_TABLE_ID6[1], ICON_TABLE_ID6[2] | icon7)
    if forced:                                                           # f. a longer icon table
        rows = list(struct.unpack(">8H", dol.read(ICON_TABLE, 16))) + [f[1] for f in forced]
        at = data.put(struct.pack(f">{1 + len(rows)}H", 0, *rows), 4) + 2
        for lis_at, lis_w, add_at, add_w in ICON_READERS:
            _patch(dol, lis_at, lis_w, (lis_w & ~0xFFFF) | (((at + 0x8000) >> 16) & 0xFFFF))
            _patch(dol, add_at, add_w, (add_w & ~0xFFFF) | (at & 0xFFFF))
    rows = " / ".join(" ".join(f"{b}" for b in table_bytes[r * m:r * m + m]) for r in range(3))
    return [f"star bits roulette: FUN_804583c4 -> 0x{pick:08X} ({m} items, weights {rows} at 0x{table:08X}), "
            f"FUN_8045453c(6) -> 0x{enable:08X} ({int(star_on)})"
            + "".join(f", id {e[0]} enabled as {e[2]}, icon row 0x{e[3]:X}" for e in extra)
            + f", NextItem list +0xCC -> +0x{NEW_LIST:X} (object 0xF4 -> 0x{size:X}), {len(VALID_SITES)} item "
            f"checks 0..5 -> 0..{n_all - 1}, icon row 0xF9 for id 6"
            + (f", forced ids {n}..{n_all - 1} (icon rows {[f[1] for f in forced]}, table moved)" if forced else "")
            + (f", rolled by item-odds: {[r[0] for r in rolled]}" if rolled else "")]


# --- icon art ---------------------------------------------------------------------------------------

def draw_icon(size=(CELL[2] - CELL[0], CELL[3] - CELL[1]), scale=8):
    """A Galaxy-style Star Bit: a chunky five-point candy star (dark outline, glossy highlight), with two
    small ones behind it, drawn at `scale` x and reduced to the cell size. -> RGBA image."""
    import math
    from PIL import Image, ImageDraw
    W, H = size[0] * scale, size[1] * scale
    img = Image.new("RGBA", (W, H), (0, 0, 0, 0))
    d = ImageDraw.Draw(img)

    def star(cx, cy, r, rot=0.0, inner=0.55):
        pts = []
        for k in range(10):
            rr = r if k % 2 == 0 else r * inner
            t = rot + math.pi * k / 5 - math.pi / 2
            pts.append((cx + rr * math.cos(t), cy + rr * math.sin(t)))
        return pts

    def bit(cx, cy, r, rot, fill, light, dark, outline=(20, 20, 40, 255)):
        d.polygon(star(cx, cy, r + 2.2 * scale, rot, 0.58), fill=outline)          # outline
        d.polygon(star(cx, cy, r, rot, 0.55), fill=fill)
        d.polygon(star(cx + 0.12 * r, cy + 0.14 * r, r * 0.62, rot, 0.55), fill=dark)   # shaded lower facet
        d.polygon(star(cx - 0.06 * r, cy - 0.06 * r, r * 0.55, rot, 0.55), fill=fill)
        d.ellipse((cx - 0.42 * r, cy - 0.5 * r, cx - 0.08 * r, cy - 0.2 * r), fill=light)  # gloss

    s = scale
    bit(W * 0.76, H * 0.27, 5.6 * s, 0.35, (255, 120, 190, 255), (255, 225, 240, 255), (205, 60, 140, 255))
    bit(W * 0.25, H * 0.24, 5.0 * s, -0.3, (255, 220, 40, 255), (255, 250, 210, 255), (215, 160, 0, 255))
    bit(W * 0.50, H * 0.60, 10.0 * s, 0.0, (70, 170, 255, 255), (220, 245, 255, 255), (30, 100, 210, 255))
    small = img.convert("RGBa").resize(size, Image.LANCZOS).convert("RGBA")
    return small


def _rgb5a3(r, g, b, a):
    if a >= 0xE0:
        return 0x8000 | (r >> 3) << 10 | (g >> 3) << 5 | b >> 3
    return (a >> 5) << 12 | (r >> 4) << 8 | (g >> 4) << 4 | b >> 4


def icon_ci8(img):
    """-> (27 x 29 CI8 indices row-major, 256 RGB5A3 palette words). Index 0 stays transparent black:
    the stock cell's 1-px border ring outside CELL uses it."""
    from PIL import Image
    assert img.size == (CELL[2] - CELL[0], CELL[3] - CELL[1]), f"icon must be {CELL[2] - CELL[0]}x{CELL[3] - CELL[1]}"
    img = img.convert("RGBA")
    q = img.quantize(colors=255, method=Image.Quantize.FASTOCTREE)
    pal = q.getpalette("RGBA") or []
    words = [0x0000]
    for i in range(len(pal) // 4):
        words.append(_rgb5a3(*pal[4 * i:4 * i + 4]))
    words = (words + [0] * 256)[:256]
    alpha = img.getchannel("A")
    idx = bytearray()
    for y in range(img.height):
        for x in range(img.width):
            idx.append(0 if alpha.getpixel((x, y)) < 8 else q.getpixel((x, y)) + 1)
    return bytes(idx), words


from layout import ci8_cell as _cell  # noqa: E402  (file offset of CI8 pixel (x, y); layout.py)


def _locate(blob):
    """-> (image offset, palette offset) (both descriptor values, +0x20 base) for row ICON_ROW."""
    from layout import Layout
    lay = Layout(blob)
    page, _, v1, u1, v2, u2 = struct.unpack(">HH4f", lay.rows[ICON_ROW])
    box = tuple(round(v * 1024) for v in (u1, v1, u2, v2))
    assert box == CELL, f"row 0x{ICON_ROW:X} samples {box}, expected {CELL}"
    desc = lay.descs[page]
    img, pal = struct.unpack_from(">II", desc, 0)
    h, w = struct.unpack_from(">HH", desc, 8)
    assert (w, h, desc[0x17], struct.unpack_from(">H", desc, 0x18)[0], desc[0x1A]) == (1024, 1024, 9, 256, 2), \
        "row 0xF9 is not a 1024x1024 CI8 page with a 256-entry RGB5A3 palette"
    users = [r for r in range(len(lay.rows)) if struct.unpack_from(">H", lay.rows[r], 0)[0] == page]
    assert users == [ICON_ROW], f"page {page} is shared by rows {users}"
    assert [i for i, dsc in enumerate(lay.descs) if struct.unpack_from(">I", dsc, 4)[0] == pal] == [page], \
        "palette shared with another page"
    return img, pal


def _cell_bytes(blob, img, pal):
    x0, y0, x1, y1 = CELL
    idx = bytes(blob[_cell(blob, img, x, y)] for y in range(y0, y1) for x in range(x0, x1))
    return idx + bytes(blob[0x20 + pal:0x20 + pal + 512])


def patch_layout(dol, dat_path, png=ICON_PNG):
    """e. Draw the Star Bits icon over Thunder's in row 0xF9 of dt_na.dat dir 119 file 8, in each language's
    copy, in place. dat_path must be the output's own copy of dt_na.dat (never an extracted/ source)."""
    import dtna_toc
    from PIL import Image
    dat_path = Path(dat_path)
    for src in ("clean", "extra-innings"):
        assert dat_path.resolve() != (ROOT / "extracted" / src / "files/dt_na.dat").resolve(),             "patch the output's copy of dt_na.dat, not a source"
    icon = Image.open(png) if Path(png).exists() else draw_icon()
    idx, words = icon_ci8(icon)
    rec = dtna_toc.dir_pointers(dol)[LAYOUT_DIR] + LAYOUT_FILE * dtna_toc.FILE_RECORD
    w = struct.unpack(">12I", dol.read(rec, 48))
    done = set()
    with open(dat_path, "r+b") as f:
        for lang in range(3):
            off, length = w[2 + 4 * lang], w[1 + 4 * lang]
            if off in done:
                continue
            f.seek(off)
            blob = bytearray(f.read(length))
            img, pal = _locate(blob)
            got = hashlib.sha1(_cell_bytes(blob, img, pal)).hexdigest()
            assert got == STOCK_CELL_SHA1, f"dir 119 file 8 @0x{off:X}: row 0xF9's cell is not the stock Thunder icon ({got})"
            x0, y0, x1, y1 = CELL
            k = 0
            for y in range(y0, y1):
                for x in range(x0, x1):
                    blob[_cell(blob, img, x, y)] = idx[k]
                    k += 1
            blob[0x20 + pal:0x20 + pal + 512] = struct.pack(">256H", *words)
            f.seek(off)
            f.write(blob)
            done.add(off)
    return [f"star bits icon: row 0xF9 cell + palette redrawn in {len(done)} copies of dir {LAYOUT_DIR} file {LAYOUT_FILE} (in place)"]


if __name__ == "__main__":
    ICON_PNG.parent.mkdir(parents=True, exist_ok=True)
    draw_icon().save(ICON_PNG)
    print("wrote", ICON_PNG)
