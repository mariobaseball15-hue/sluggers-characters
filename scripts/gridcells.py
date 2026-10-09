"""The character-select grid sized to the build's squares: the 41 stock heads and one square per
charbuild.GRID_SQUARES entry that has a character in the build (0 to 19), and the team bars stretched
to match, on the screen with the two 9-player team rosters (FUN_800710b4; build step 7 of charbuild.py,
part of new-ids, on unless build_chars.py --no-grid-cell).

Stock: 40 squares in rows of 10 for 41 heads (the default square -> head map 0x80623458 leaves out
head 1, Luigi, and the constructor FUN_8006e9c4 swaps one captain's family square for him). With no new
square the grid stays stock. Otherwise (Nick, 2026-09-26: "the grid should adjust to the number of
characters") it is the smallest of SHAPES (cols x rows: 11x4, 12x4, 10x5, 11x5, 12x5) holding 41 + n
squares (shape()), square s at row s // cols, column s % cols, filled in reading order (the layout's
order: charbuild.GRID_LAYOUT, 12 x 5, with the squares this build has no character for left out; with
all 19 it is the layout itself, byte for byte as before). The last row's leftover cells (fewer than
cols) are empty (j). More than 60 squares does not fit: 12 columns already reach the screen's left
edge and 5 rows the team bars, so a 13th column or 6th row needs smaller squares (a new layout), and the
per-head arrays (SEL - FLAGS = 64 heads: 43 + 21) would have to move too.

  a. Layout (dt_na.dat dir 119 file 19, scripts/css_layout.py; an element is a list of nodes, each a
     list of keyframes {u16 flags, u16 time, u8 type (3 = element, 4 = sprite), u16 ref, s16 x, y ...}):
     - square positions are the nodes of element 0xBA (node = square), rebuilt with cols x rows nodes
       at the stock 49 px pitch, right edge at the stock column 9's x (12 columns: columns 1..10 are the
       stock columns moved one square left, column 0 one more square left, column 11 at column 9's x;
       11: one new column left of the stock ones); 4 rows keep the stock rows' y, 5 rows are
       re-spaced (ROW_Y0, ROW_PITCH) with the team bars moved apart;
     - the team bars are 0x9A / 0x9B (position, at x 9) holding 0x9C / 0x9D, a three-part sprite
       (39 px cap, a 60 px middle stretched by its x scale, cap). They move left and stretch to the
       grid's width; the 9 roster slots (0xB9 top, 0xB8 bottom, node = slot) spread evenly along them.
     - the whole roster screen moves screen_dx() right (SCREEN_DX at 12 columns, half at 11).
     The file grows, so each language's copy is appended to dt_na.dat and its index records repointed.
  b. Square count: FUN_80067ef4 builds 0x29 - (big == 0) squares and gives the cursor / face / star
     widgets that count (+0xDC). It becomes cols x rows on this screen (big == 0) and stays 41 on the other
     (FUN_8042efd4, big == 1).
  c. The grid widget's per-square arrays (bytes +0x40, words +0x6C / +0x110, pairs +0x1B4) hold 41 and
     are followed by its provider vtable (+0x2FC). They move to grid + GRID_ARRAYS (capacity CAP) in
     both screens' objects, which grow (this screen 0x67C -> OBJ_SIZE, the other 0x6CC -> OBJ_B_SIZE).
     The grid methods' square loops / bounds (0x29) become SQUARES and their init loop (8 squares per
     pass, plus one after it) covers at least SQUARES.
  d. Square -> head map (obj+0x238, 40 bytes) and the per-head flag / wheel-index arrays (obj+0x260,
     +0x289, 43 each) move to obj+MAP / FLAGS / SEL, filled by the constructor's copy loop from one
     table. The captain swap is disabled (every head has a square).
  e. Heads 43.. are the new squares' heads: the head list 0x80631878 (43 bytes, 20 references) is
     relocated and extended with their ids. FUN_80071bb0 (members of the wheel holding an id; this
     screen's only wheel builder) treats a square character as having no wheel (the stock
     single-member path) and leaves it out of its template's wheel; the grid provider's "head has
     members" answers yes for heads >= 43; the cursor-placement loop in FUN_80073958 finds a square
     character's own square. Other screens keep them on their template's wheel (charbuild step 3a).
  f. Cursor positions: 0..3 specials, 4..0x15 rosters, 0x16.. grid, then 10 Mii rows and 2 Mii-panel
     buttons. The grid grows by cols x rows - 40 (DELTA = 20 at 12 x 5), so every bound and position
     constant in POSITION_SITES moves.
  h. A pick's "decided" overlay (flag 1 forever in the stock game) is set to finish (flag 2), so the
     square shows the next skin, or goes dark once every skin is taken.
  g. D-pad: the up / down / left-right handlers and the roster -> grid helper compute
     row = (pos - 0x16) / 10 and column = % 10: the divide (mulhw by 0x66666667, >> 2; DIVIDE), the
     * 10, the column bound and wraps become cols; the down handler's row bound (4) and the roster ->
     grid helper's bottom row (3) become rows.
  j. The last row's leftover cells (cols x rows - 41 - n of them) are empty: each gets a head of its
     own past the squares' (heads 43.. are the new squares in GRID_SQUARES order, then one per empty
     cell), so "head >= first empty head" marks it. Its node in element 0xBA is moved off screen
     (HIDE_DX: no square, face or star drawn, and the pointer cannot reach it); the pointer hit test
     (FUN_8006887c at HIT_CALL) also answers "no square" for it; each D-pad move (DPAD_CALLS) that lands
     on it moves on in the same direction until it reaches a square or leaves the grid (at most
     HOLE_STEPS moves, else the cursor stays where it was). Random team / CPU picks walk only the
     squares' heads. A full grid (12 x 5 with all 19 squares) has none of this.
"""
import struct

from ppc import Asm, ha, lo

# The 19 new squares, each a wheel of up to 6 characters (ids or names from the build's character
# definitions; the first is the one shown), passed as add_grid_square(..., squares=[[...], ...]) in
# NEW_SQUARE_CELLS order (charbuild.GRID_SQUARES). COLS x ROWS is the largest grid (all 19).
N_NEW_SQUARES, WHEEL_MAX = 19, 6
STOCK_SQUARES, COLS, ROWS = 40, 12, 5
SQUARES = COLS * ROWS                 # 60
DELTA = SQUARES - STOCK_SQUARES       # cursor positions after the grid move up by this
STOCK_HEADS = 43
NEW_HEADS = tuple(range(STOCK_HEADS, STOCK_HEADS + N_NEW_SQUARES))
LUIGI_HEAD, LUIGI_CELL = 1, (4, 11)
# (cols, rows) the grid can take, smallest first (shape())
SHAPES = sorted(((c, r) for c in (10, 11, 12) for r in (4, 5) if (c, r) != (10, 4)), key=lambda s: (s[0] * s[1], s[1]))
# the column divide: cols -> (lis, addi, srawi) of the mulhw magic (signed; checked for -400..400 in the tests)
DIVIDE = {10: (0x6666, 0x6667, 2), 11: (0x2E8C, -0x5D17, 1), 12: (0x2AAB, -0x5555, 1)}
# j. empty cells (the last row's leftovers)
HIDE_DX = -2000                       # an empty cell's node: this far left, off screen
HIT_CALL, HIT_FN = 0x8006F4A0, 0x8006887C   # FUN_8006f184: bl FUN_8006887c (pointer -> square), r30 = obj
# FUN_8006f184's D-pad calls (r3 = r30 obj, r4 = r22 player; left / right: r5 = direction):
# (call, handler: up, down, left, right; direction or None)
DPAD_CALLS = ((0x80070184, 0x80075DA4, None), (0x800701DC, 0x8007627C, None),
              (0x80070238, 0x80076828, -1), (0x80070294, 0x80076828, 1))
CURSOR = 0x2D8                        # obj + player * 4: the player's cursor position
HOLE_STEPS = 2 * (COLS + ROWS)
# (row, column) of each new square: column 0 top to bottom, column 11 rows 0..3, row 4 columns 1..10
NEW_SQUARE_CELLS = ([(r, 0) for r in range(ROWS)] + [(r, COLS - 1) for r in range(ROWS - 1)]
                    + [(ROWS - 1, c) for c in range(1, COLS - 1)])
assert len(NEW_SQUARE_CELLS) == N_NEW_SQUARES

MAP, FLAGS, SEL = 0x67C, 0x6BC, 0x6FC # screen object: square -> head (60), per-head flag, wheel index (64)
GRID_A, GRID_B = 0x338, 0x2A0         # grid widget offset in this screen's / the other screen's object
GRID_ARRAYS, CAP = 0x430, 72          # relocated per-square arrays: grid + GRID_ARRAYS, 72 squares
G_FLAGS, G_W6C, G_W110, G_PAIRS = (GRID_ARRAYS, GRID_ARRAYS + CAP, GRID_ARRAYS + 5 * CAP,
                                   GRID_ARRAYS + 9 * CAP)
OBJ_SIZE = GRID_A + G_PAIRS + 8 * CAP     # 0xC30
OBJ_B_SIZE = GRID_B + G_PAIRS + 8 * CAP   # 0xB98
INIT_PASSES = (SQUARES - 1 + 7) // 8      # FUN_80067c00 inits 8 squares per pass, plus one after the loop
assert SEL + 0x40 <= GRID_A + GRID_ARRAYS and 0x6CC <= GRID_B + GRID_ARRAYS
assert SQUARES <= 8 * INIT_PASSES + 1 <= CAP and NEW_HEADS[-1] < 0x40

OBJ_ALLOC = 0x802C8CFC                # li r3,0x67c before FUN_8006e9c4
OBJ_B_ALLOCS = (0x8038DF98, 0x80435E08, 0x804EA464)   # li r3,0x6cc before FUN_8042c424
STOCK_MAP = 0x80623458                # 40 heads, copied by FUN_8006e9c4
HEAD_LIST = 0x80631878                # head -> character id (43)

# Byte accesses to the square -> head map: 0x238(obj + square) or 0x222(obj + position).
MAP_SITES = (0x8006C240, 0x8006D6B0, 0x8006E7CC, 0x8006EB9C, 0x8006EBA8, 0x8006EBB0, 0x8006EBB8,
             0x8006EBC0, 0x8006EBC8, 0x8006EBD0, 0x8006EBDC, 0x8006EC38, 0x8006EC88, 0x80073C44,
             0x80073D7C, 0x800748F8, 0x800755A4, 0x80075BF8, 0x800771FC)
CAPTAIN_SWAP_STORE = 0x8006ECF4       # stb r0,0x238(r3): square nearest the centre := head 1
# Byte accesses to the per-head arrays: 0x260..0x288 flag, 0x289..0x2B0 wheel index.
HEAD_SITES = (0x8006C260, 0x8006D6CC, 0x8006D704, 0x8006E820, 0x8006E884, 0x8006EAB0, 0x8006ED10,
              0x8006ED14, 0x8006ED18, 0x8006ED1C, 0x8006ED20, 0x8006ED24, 0x8006ED28, 0x8006ED2C,
              0x8006ED30, 0x8006ED34, 0x8006ED38, 0x8006ED3C, 0x8006ED40, 0x8006ED44, 0x8006ED48,
              0x8006ED4C, 0x8006ED5C, 0x8006ED6C, 0x8007215C, 0x80073DA4, 0x80073E88, 0x80073ED0,
              0x80074920, 0x80074978, 0x80075634, 0x8007566C, 0x80075678, 0x80075C14, 0x80075C64,
              0x80077218)
# Grid methods' per-square array accesses (+0x40 bytes, +0x6C / +0x110 words, +0x1B4 pairs).
GRID_SITES = (0x800669F0, 0x80066A00, 0x80066A08, 0x80066A18, 0x80066A48, 0x80066A5C, 0x80066A64,
              0x80066A6C, 0x80066A7C, 0x80066A84, 0x80066B70, 0x80066C04, 0x80066CF0, 0x80066D3C,
              0x80066DF4, 0x80066EC0, 0x80066FFC, 0x800672A0, 0x800672B4, 0x800672C4, 0x800672F4,
              0x8006749C, 0x800674D0, 0x800675A8, 0x8006769C, 0x800676C8, 0x800678D8,
              # FUN_80067c00: zeroing, then the init loop (8 squares per pass) and the pass after it
              0x80067C60, 0x80067C64, 0x80067C68, 0x80067C6C, 0x80067C70, 0x80067C74, 0x80067C78,
              0x80067C7C, 0x80067C80, 0x80067C84, 0x80067C88,
              0x80067D24, 0x80067D28, 0x80067D2C, 0x80067D30, 0x80067D34, 0x80067D38, 0x80067D3C,
              0x80067D40, 0x80067D44, 0x80067D48, 0x80067D4C, 0x80067D50, 0x80067D54, 0x80067D58,
              0x80067D5C, 0x80067D60, 0x80067D64, 0x80067D68, 0x80067D6C, 0x80067D70, 0x80067D74,
              0x80067D78, 0x80067D7C, 0x80067D80, 0x80067D84, 0x80067D88, 0x80067D8C, 0x80067D90,
              0x80067D94, 0x80067D98, 0x80067D9C, 0x80067DA0, 0x80067DA4, 0x80067DA8, 0x80067DAC,
              0x80067DB0, 0x80067DB4, 0x80067DB8, 0x80067DC0, 0x80067DC4,
              0x80067DDC, 0x80067DE8, 0x80067DF4, 0x80067E00, 0x80067E04,
              # FUN_800688b4
              0x800688C0, 0x800688C8, 0x800688CC)
GRID_LOOPS = (0x80066990, 0x80066A28, 0x80067748, 0x80067B6C, 0x80067BE4)   # li / cmpwi 0x29
GRID_INIT_PASSES = 0x80067CDC         # li r0,5: 8 squares per pass, plus one after the loop

# FUN_80067ef4: r22 / r0 hold -(big != 0) ... see add_grid_square
COUNT_LOOP_A, COUNT_LOOP_B = 0x800680B0, 0x80068750
COUNT_DC = ((0x800681A0, 0x800681A8), (0x800682B4, 0x800682BC), (0x800683D8, 0x800683E0),
            (0x80068504, 0x8006850C), (0x80068624, 0x8006862C))

# f. Every position bound / constant >= 0x3E, the grid's last-square bounds (cmplwi 0x27 after
#    `subi 0x16`, cmpwi 0x3D) and the 40-square loop in FUN_80073958 (li / cmpwi 0x28).
POSITION_SITES = (
    # FUN_8006c044
    0x8006C0C4, 0x8006C0CC, 0x8006C0E0, 0x8006C13C, 0x8006C150, 0x8006C158,
    # FUN_8006d0f8
    0x8006D190, 0x8006D198, 0x8006D1AC, 0x8006D214, 0x8006D228, 0x8006D230,
    # FUN_8006d3c0
    0x8006D480, 0x8006D488, 0x8006D49C, 0x8006D504, 0x8006D520, 0x8006D744, 0x8006D850, 0x8006D858,
    0x8006D86C, 0x8006D8D4, 0x8006D8F0,
    # FUN_8006f184
    0x8006F48C, 0x8006F598, 0x8006F5A0, 0x8006F5B4, 0x8006FCD0, 0x8006FCE8, 0x80070554, 0x80070568,
    0x800705CC, 0x800705D4, 0x800705E8, 0x80070774, 0x80070798, 0x800707F8, 0x8007080C, 0x80070870,
    0x80070878, 0x8007088C, 0x8007095C, 0x80070964, 0x8007096C, 0x80070984, 0x8007098C, 0x80070998,
    0x80070A08, 0x80070A1C, 0x80070A80, 0x80070A88, 0x80070A9C,
    # FUN_80073040
    0x80073094, 0x8007309C, 0x800730B0, 0x8007310C, 0x80073120, 0x80073154, 0x80073190, 0x80073198,
    0x8007355C, 0x80073564, 0x8007356C, 0x80073584, 0x8007358C, 0x800735DC, 0x800735E4, 0x800735F8,
    0x80073654, 0x80073668, 0x80073670,
    # FUN_80073958
    0x800739AC, 0x800739B4, 0x800739C8, 0x80073A2C, 0x80073A48, 0x80073C08, 0x80073C24, 0x80073C70,
    0x8007404C, 0x80074134, 0x800744D8, 0x800744E0, 0x800744F4, 0x80074558, 0x80074574, 0x80074A8C,
    # FUN_800751dc
    0x800752DC, 0x800752E4, 0x800752F8, 0x80075354, 0x80075368, 0x80075370, 0x8007540C, 0x80075414,
    0x80075428, 0x80075484, 0x80075498, 0x800754A0,
    # FUN_8007578c
    0x800757EC, 0x800757F4, 0x80075808, 0x8007586C, 0x80075888, 0x80075AC0, 0x80075AC8, 0x80075ADC,
    0x80075B40, 0x80075B5C,
    # FUN_80075c80
    0x80075CC0, 0x80075CD0, 0x80075CE0, 0x80075CF0, 0x80075D20,
    # FUN_80075da4
    0x80075DF8, 0x80075E00, 0x80075E14, 0x80075E70, 0x80075E84, 0x8007605C, 0x800760F4, 0x8007610C,
    0x80076118, 0x80076120, 0x8007623C, 0x8007624C,
    # FUN_8007627c
    0x800762D0, 0x800762D8, 0x800762EC, 0x80076348, 0x8007635C, 0x80076538, 0x800765D4, 0x800765EC,
    0x800765F8, 0x80076600, 0x80076724, 0x80076734,
    # FUN_80076828
    0x80076880, 0x80076888, 0x8007689C, 0x800768F8, 0x8007690C, 0x80076B00, 0x80076B3C, 0x80076B4C,
    0x80076B94, 0x80076BA4, 0x80076BB8, 0x80076BD4, 0x80076BE4, 0x80076C2C, 0x80076C3C, 0x80076C50,
    0x80076C68, 0x80076C74, 0x80076C8C, 0x80076C9C, 0x80076CB0, 0x80076CC0, 0x80076D1C, 0x80076D2C,
    0x80076D40, 0x80076D50, 0x80076D5C, 0x80076D98, 0x80076DA8, 0x80076DBC, 0x80076DCC, 0x80076DE0,
    0x80076DF0, 0x80076E04, 0x80076E14, 0x80076E60, 0x80076E70, 0x80076E98, 0x80076EBC, 0x80076ECC,
    0x80076EE0, 0x80076EF0, 0x80076F18, 0x80076F3C, 0x80076F4C, 0x80077014, 0x80077024,
    # FUN_80077054
    0x800770C4, 0x800770CC, 0x800770E0, 0x80077144, 0x80077160, 0x8007727C,
)
POSITION_IMMS = {0x27, 0x28} | set(range(0x3D, 0x4B))

# g. 11 columns. The divide by 10 is `lis 0x6666; addi 0x6667; mulhw; srawi 2 (twice)`; divide by 11
#    by 12 is 0x2AAAAAAB (lis 0x2AAB, addi -0x5555) with shift 1.
DIV_SITES = ((0x80075F90, 0x80075F98, 0x80075FA0, 0x80075FA4),     # up
             (0x80076468, 0x80076470, 0x80076478, 0x8007647C),     # down
             (0x800769B8, 0x800769C0, 0x800769C8, 0x800769D0))     # left / right
TIMES_10 = (0x80075FB8, 0x8007603C, 0x80076490, 0x80076518, 0x800769D8, 0x80076ACC, 0x80076AE0,
            0x80075D54, 0x80076F88)                               # mulli rX,rY,0xa
COLUMN_BOUNDS = (0x800769F0, 0x80076AC0)                           # cmpwi r25,0xa (column < 10)
LAST_COLUMN = (0x80076AB8, 0x80076F68)                             # li 9: left wrap / from specials
UP_WRAP = 0x80076030                                               # addi r0,r26,0x34: row 3
RANDOM_HEAD_BOUND = 0x800722CC     # FUN_800721a0 (Random team pool): cmpwi r22,0x29 (heads 0..40)
RANDOM_POOL_ALLOC = 0x80072310     # FUN_800722ec: li r3,0x52 (41 u16 pool entries)
POOL_HEAD_BOUNDS = ((0x80431F08, "r21", "r26", 0x2C150029), (0x80431F94, "r20", "r16", 0x2C140029))   # FUN_80431df0
ENTRY_BOTTOM_ROW = 0x80075D50       # FUN_80075c80: rlwinm r0,r0,0,30,31 (-(bottom) & 3 = row 3)
DOWN_ROWS = 0x80076498              # FUN_8007627c: cmpwi r0,4 (row + 1 < 4: stay in the grid)

# e. hooks
MEMBERS_FN = 0x80071BB0               # FUN_80071bb0(obj, player, id, keep_id, out[6]): the wheel holding id
AVAILABLE = 0x80071ABC                # FUN_80071abc(obj, handle): not on a team, not held, unlocked
MEMBER_TAKE = 0x80071EAC              # cmpwi cr1,r29,0: add family member r26 to the wheel?
MEMBER_NEXT = 0x80071EE0
HAS_MEMBERS = 0x8006E868              # lbz r3,0x5a(r3): provider "head has members", r4 = head
DECIDE_FN, DECIDE_CALL = 0x800688B4, 0x80073DF4   # this screen's pick -> FUN_800688b4
CURSOR_FAMILY = 0x80073C34            # lbz r3,0x2(r3): family of id (r4 = id * 8)

LAYOUT_DIR, LAYOUT_FILE, GRID_ELEMENT = 119, 19, 0xBA
FRAME = 4 + 3 * 0x3C                  # {u16 3, u16 0x3C, 3 children}
CHILD_XY = (0x08, 0x18, 0x1C)         # s16 x, s16 y pairs in a child record
SQUARE_W = 49
SHIFT = -SQUARE_W                     # one square to the left


def _patch(dol, addr, expect, new):
    got = dol.u32(addr)
    assert got == expect, f"0x{addr:08X}: expected {expect:08X}, found {got:08X}"
    dol.w32(addr, new)


def _imm(dol, addr, old, new):
    """Replace the 16-bit immediate of the instruction at addr (asserted to be old)."""
    w = dol.u32(addr)
    assert w & 0xFFFF == old & 0xFFFF, f"0x{addr:08X}: {w:08X}, expected immediate {old & 0xFFFF:#x}"
    dol.w32(addr, (w & 0xFFFF0000) | (new & 0xFFFF))


def _remap(dol, sites, ranges):
    """Rewrite each load / store's displacement d in [start, end) to base + (d - start)."""
    for addr in sites:
        w = dol.u32(addr)
        d = w & 0xFFFF
        new = [base + d - start for start, end, base in ranges if start <= d < end]
        assert len(new) == 1 and w >> 26 in (32, 34, 36, 38), f"0x{addr:08X}: {w:08X}"
        dol.w32(addr, (w & 0xFFFF0000) | new[0])


def _char(m, chars):
    """A square member (id, or a definition's / stock character's name) -> id, or None if it is a new
    character this build leaves out (chars: the build's definitions; stock ids are always there)."""
    from sluggers_data import char_id
    if isinstance(m, str):
        hit = [c["id"] for c in chars if c["name"].strip().lower() == m.strip().lower()]
        if hit:
            return hit[0]
    try:
        cid = char_id(m)
    except (KeyError, ValueError):
        return None                                      # a new character's name, not in this build
    return None if chars and cid > 0x64 and cid not in {c["id"] for c in chars} else cid


def _resolve_squares(squares, chars):
    """[[id, ...] x 19]: names match the build's character definitions (case-insensitive), else stock
    names. Members this build leaves out are dropped (a partial roster), so a square may be empty (j)."""
    import wheel7
    out = [[cid for cid in (_char(m, chars) for m in sq) if cid is not None] for sq in squares]
    assert len(out) <= N_NEW_SQUARES, f"at most {N_NEW_SQUARES} new squares"
    assert all(len(sq) <= wheel7.MEMBERS for sq in out), f"at most {wheel7.MEMBERS} characters per square"
    flat = [c for sq in out for c in sq]
    assert len(set(flat)) == len(flat), "a character is on two squares"
    return out


def shape(n):
    """(cols, rows) for the 41 stock heads and n new squares: the smallest of SHAPES, None for n = 0 (the
    stock grid)."""
    assert 0 <= n <= N_NEW_SQUARES, f"{n} new squares (at most {N_NEW_SQUARES})"
    return next(((c, r) for c, r in SHAPES if c * r >= 41 + n), None) if n else None


def plan(chars, squares, force=False):
    """(cols, rows, empty cells) of this build's grid (squares: charbuild.GRID_SQUARES), or None when no
    square has a character (the stock grid). force: our grid even with no new square (grid_order: the stock squares
    in another order): the smallest shape for the 41 heads (11 x 4)."""
    n = sum(1 for sq in _resolve_squares(squares, chars) if sq)
    if not n and force:
        cols, rows = next((c, r) for c, r in SHAPES if c * r >= 41)
        return cols, rows, tuple(range(41, cols * rows))
    if not n:
        return None
    cols, rows = shape(n)
    return cols, rows, tuple(range(41 + n, cols * rows))


FULL = (COLS, ROWS, ())                   # every square has a character


def screen_dx(grid):
    """The roster screen's shift right for a plan() (None: the stock grid, 0)."""
    return SCREEN_DX * (grid[0] - 10) // 2 if grid else 0


def _order(dol, squares, chars, layout=None):
    """The 41 stock heads and the new squares in reading order, as ("stock", head) / ("square", k):
    the layout's names (ROWS x COLS, or one flat list in reading order: grid_order.py; each a stock head's main
    character or a new square's first member as listed, so a square keeps its place when its first character is
    left out), or the default 12 x 5 (stock grid in columns 1..10, the squares in NEW_SQUARE_CELLS, Luigi at
    LUIGI_CELL)."""
    stock = list(dol.read(HEAD_LIST, 41))
    if not layout:
        grid = [None] * (COLS * ROWS)
        heads = dol.read(STOCK_MAP, STOCK_SQUARES)
        for row in range(4):
            for col in range(10):
                grid[row * COLS + 1 + col] = ("stock", heads[row * 10 + col])
        for k, (row, col) in enumerate(NEW_SQUARE_CELLS):
            grid[row * COLS + col] = ("square", k)
        grid[LUIGI_CELL[0] * COLS + LUIGI_CELL[1]] = ("stock", LUIGI_HEAD)
        return grid
    nested = isinstance(layout[0], (list, tuple))
    assert not nested or (len(layout) == ROWS and all(len(r) == COLS for r in layout)), \
        f"layout is {ROWS} rows of {COLS}, or a flat list"
    key = lambda m: m.strip().lower() if isinstance(m, str) else m
    firsts = [{key(sq[0]), _char(sq[0], chars)} - {None} for sq in squares]
    out = []
    for name in ((n for r in layout for n in r) if nested else layout):
        hit = [k for k, f in enumerate(firsts) if {key(name), _char(name, chars)} & f]
        if hit:
            out.append(("square", hit[0]))
        else:
            cid = _char(name, chars)
            assert cid in stock, f"layout: {name!r} is neither a stock square nor a new square's first character"
            out.append(("stock", stock.index(cid)))
    return out


def _is_square_char(a, reg, target, ids):
    for cid in ids:
        a.cmpwi(reg, cid).beq(target)


def add_grid_square(dol, code, data, chars=(), squares=None, layout=None, force=False):
    """squares: up to 19 lists of 1-10 characters (ids or names), the wheel on each new square; the first is
    shown. Characters not in this build are left out, and so is a square left with none; at least one
    square must have a character (else the grid stays stock: plan() is None), unless force (plan(force=): the
    stock squares in the layout's order, grid_order). layout: optional ROWS x COLS names, or a flat list, ordering
    every square (see _order)."""
    assert squares is not None, "squares: charbuild.GRID_SQUARES"
    assert squares or (force and layout), "no new square: force needs a layout"
    order = _order(dol, squares, chars, layout)
    named = squares
    squares = _resolve_squares(squares, chars)
    cols, rows, empty = plan(chars, named, force)
    SQUARES = cols * rows                                # (this build's; the module's SQUARES is the largest)
    DELTA = SQUARES - STOCK_SQUARES
    used = [k for k, sq in enumerate(squares) if sq]     # heads 43.. in GRID_SQUARES order, then the empty cells
    square_heads = dict(zip(used, NEW_HEADS))
    first_empty = STOCK_HEADS + len(used)
    squares = [squares[k] for k in used]
    square_ids = [c for sq in squares for c in sq]
    import wheel7                                        # squares past 6 (grid_order): wheel7's 10; else the stock 6,
    cap = WHEEL_MAX if all(len(sq) <= WHEEL_MAX for sq in squares) else wheel7.MEMBERS   # so today's bytes stay
    # b. square counts in FUN_80067ef4. r22 = -(big == 0): `srawi r3,r22,31` -> `mulli r3,r22,-extra`
    #    (extra or 0), so `addi r0,r3,0x29` counts SQUARES here and 41 on the other screen. The widgets'
    #    +0xDC count is `rlwinm rX,r0,1,31,31` (big != 0) then `addi _,rX,0x28` with r0 = -(big != 0):
    #    `mulli rX,r0,extra` and SQUARES give SQUARES / 41.
    extra = SQUARES - 0x29                                              # 19 at 12 x 5
    _patch(dol, COUNT_LOOP_A, 0x7EC3FE70, (7 << 26) | (3 << 21) | (22 << 16) | (-extra & 0xFFFF))
    _patch(dol, COUNT_LOOP_B, 0x38030029, 0x38000000 | SQUARES)       # li r0,SQUARES (big == 0 only)
    for rl, add in COUNT_DC:
        w = dol.u32(rl)
        assert w & 0xFFE0FFFF == 0x54000FFE, f"0x{rl:08X}: {w:08X}"
        rx = (w >> 16) & 0x1F
        dol.w32(rl, (7 << 26) | (rx << 21) | extra)                    # mulli rX,r0,extra
        _imm(dol, add, 0x28, SQUARES)

    # c. grid widget per-square arrays -> grid + GRID_ARRAYS; both screens' objects grow
    _remap(dol, GRID_SITES, ((0x40, 0x6C, G_FLAGS), (0x6C, 0x110, G_W6C), (0x110, 0x1B4, G_W110),
                             (0x1B4, 0x2FC, G_PAIRS)))
    for addr in GRID_LOOPS:
        _imm(dol, addr, 0x29, SQUARES)
    passes = (SQUARES - 1 + 7) // 8
    assert SQUARES <= 8 * passes + 1 <= CAP
    _patch(dol, GRID_INIT_PASSES, 0x38000005, 0x38000000 | passes)  # 12 x 5: 8 passes + 1 = 65 <= CAP
    _patch(dol, OBJ_ALLOC, 0x3860067C, 0x38600000 | OBJ_SIZE)
    for addr in OBJ_B_ALLOCS:
        _patch(dol, addr, 0x386006CC, 0x38600000 | OBJ_B_SIZE)

    # d. square -> head map and per-head arrays
    _remap(dol, MAP_SITES, ((0x222, 0x223, MAP - 0x16), (0x238, 0x240, MAP)))
    _remap(dol, HEAD_SITES, ((0x260, 0x289, FLAGS), (0x289, 0x2B1, SEL)))
    heads = bytearray(h if kind == "stock" else square_heads[h] for kind, h in order
                      if kind == "stock" or h in square_heads)            # reading order, the squares with characters
    assert len(heads) == 41 + len(used) and len(set(heads)) == len(heads), "a head has two squares"
    heads += bytes(range(first_empty, first_empty + len(empty)))          # j. the last row's leftover cells
    assert len(heads) == SQUARES
    table = bytes(heads) + b"\xFF" * (FLAGS - MAP - SQUARES) + bytes(SEL + 0x40 - FLAGS)
    at = data.put(table, align=4)
    _patch(dol, 0x8006EB74, 0x3C608062, 0x3C600000 | ha(at))           # lis r3,
    _patch(dol, 0x8006EB80, 0x38633458, 0x38630000 | lo(at))           # addi r3,r3,
    _patch(dol, 0x8006EB78, 0x38000005, 0x38000000 | len(table) // 8)  # li r0,5 (8 bytes per pass)
    w = dol.u32(CAPTAIN_SWAP_STORE)
    assert w >> 26 == 38 and w & 0xFFFF == 0x238, f"captain swap store: {w:08X}"
    dol.w32(CAPTAIN_SWAP_STORE, 0x60000000)

    # d2. A pick marks its square "decided" (FUN_800688b4: flag 1, player, id), and the decided widget
    #     draws the picked face over the square at animation step 6 for as long as the flag is 1.
    #     Nothing in the game ever moves the flag on to 2 (animate to step 11, then clear), so picked
    #     squares kept showing their pick instead of the next skin or the empty (dark) square. This
    #     screen's call gets a copy that sets 2; the other screen keeps FUN_800688b4.
    a = Asm(code.here)                                   # (grid, square, player, id)
    a.add("r7", "r3", "r4").li("r0", 2).stb("r0", G_FLAGS, "r7")
    a.slwi("r4", "r4", 2).add("r3", "r3", "r4")
    a.stw("r5", G_W6C, "r3").stw("r6", G_W110, "r3").blr()
    _patch(dol, DECIDE_CALL, Asm(DECIDE_CALL).bl(DECIDE_FN).assemble_word(),
           Asm(DECIDE_CALL).bl(code.put(a.assemble(), 4)).assemble_word())

    # e. the new heads' wheels. The head list gets each square's first character (what the square
    #    shows and what FUN_8006e7d8 asks FUN_80071bb0 about). FUN_80071bb0 is replaced for square
    #    characters: it lists that square's members that FUN_80071abc calls available (plus the asked id
    #    when keep_id is set), up to 6 in out[], and returns the count, as the stock family path does.
    assert NEW_HEADS[-1] < SEL - FLAGS, "per-head arrays too small"
    import hilo_refs
    from charbuild import relocate
    stock_heads = dol.read(HEAD_LIST, STOCK_HEADS)       # (empty cells' heads: head 0's character)
    head_list = data.put(stock_heads + bytes(sq[0] for sq in squares) + stock_heads[:1] * len(empty), align=4)
    n_refs = relocate(dol, list(hilo_refs.pairs()), HEAD_LIST, STOCK_HEADS, head_list, name="grid heads", row=1)
    lists = data.put(b"".join(bytes(sq) + b"\xFF" * (cap + 2 - len(sq)) for sq in squares), align=4)
    a = Asm(code.here)
    for k, sq in enumerate(squares):                     # r8 = the square's member list, or the stock path
        for cid in sq:
            a.cmpwi("r5", cid).beq(f"sq{k}")
    a.word(0x9421FF80).b(MEMBERS_FN + 4)                 # stwu r1,-0x80(r1): stock
    for k in range(len(squares)):
        a.label(f"sq{k}")
        a.load_addr("r8", lists + k * (cap + 2)).b("wheel")
    a.label("wheel")
    a.stwu("r1", -0x40, "r1").mflr("r0").stw("r0", 0x44, "r1")
    for r in range(25, 32):
        a.stw(f"r{r}", 0x20 + 4 * (r - 25), "r1")
    a.mr("r31", "r3").mr("r30", "r5").mr("r29", "r6").mr("r28", "r7").mr("r27", "r8").li("r26", 0)
    a.label("member")
    a.lbz("r25", 0, "r27").cmplwi("r25", 0xFF).beq("done")
    a.sth("r25", 8, "r1").li("r0", 0).stw("r0", 0xC, "r1").stw("r0", 0x10, "r1")   # handle {id, 0, 0}
    a.mr("r3", "r31").addi("r4", "r1", 8).bl(AVAILABLE)
    a.cmpwi("r3", 0).bne("take")
    a.cmpw("r25", "r30").bne("next").cmpwi("r29", 0).beq("next")
    a.label("take")
    a.cmpwi("r28", 0).beq("count").cmpwi("r26", cap).bge("count")
    a.slwi("r0", "r26", 2).word((31 << 26) | (25 << 21) | (28 << 16) | (0 << 11) | (151 << 1))   # stwx r25,r28,r0
    a.label("count")
    a.addi("r26", "r26", 1)
    a.label("next")
    a.addi("r27", "r27", 1).b("member")
    a.label("done")
    a.mr("r3", "r26")
    for r in range(25, 32):
        a.lwz(f"r{r}", 0x20 + 4 * (r - 25), "r1")
    a.lwz("r0", 0x44, "r1").mtlr("r0").addi("r1", "r1", 0x40).blr()
    _patch(dol, MEMBERS_FN, 0x9421FF80, Asm(MEMBERS_FN).b(code.put(a.assemble(), 4)).assemble_word())
    a = Asm(code.here)                                   # square characters are not on their template's wheel
    _is_square_char(a, "r26", "skip", square_ids)
    a.cmpwi("r29", 0, cr=1).b(MEMBER_TAKE + 4)
    a.label("skip")
    a.b(MEMBER_NEXT)
    _patch(dol, MEMBER_TAKE, 0x2C9D0000, Asm(MEMBER_TAKE).b(code.put(a.assemble(), 4)).assemble_word())
    a = Asm(code.here)                                   # heads >= 43 have members
    a.cmpwi("r4", STOCK_HEADS).bge("single")
    a.lbz("r3", 0x5A, "r3").b(HAS_MEMBERS + 4)
    a.label("single")
    a.li("r3", 1).b(HAS_MEMBERS + 4)
    _patch(dol, HAS_MEMBERS, 0x8863005A, Asm(HAS_MEMBERS).b(code.put(a.assemble(), 4)).assemble_word())
    a = Asm(code.here)                                   # cursor goes to a square character's square
    a.lbz("r3", 2, "r3")
    for sq, head in zip(squares, NEW_HEADS):             # (the squares with characters: heads 43.. in order)
        for cid in sq:
            a.cmpwi("r4", cid * 8).bne(f"not_{cid}").li("r3", head)
            a.label(f"not_{cid}")
    a.b(CURSOR_FAMILY + 4)
    _patch(dol, CURSOR_FAMILY, 0x88630002, Asm(CURSOR_FAMILY).b(code.put(a.assemble(), 4)).assemble_word())

    # f. cursor positions
    for addr in POSITION_SITES:
        w = dol.u32(addr)
        imm = w & 0xFFFF
        imm = imm - 0x10000 if imm & 0x8000 else imm
        assert abs(imm) in POSITION_IMMS, f"0x{addr:08X}: {w:08X}"
        new = imm - DELTA if imm < 0 else imm + DELTA              # subi: raise the magnitude
        dol.w32(addr, (w & 0xFFFF0000) | (new & 0xFFFF))

    # g. cols columns, rows rows
    hi, lo_, shift = DIVIDE[cols]
    for lis_, addi, sr1, sr2 in DIV_SITES:
        _imm(dol, lis_, 0x6666, hi)
        _imm(dol, addi, 0x6667, lo_)
        for sr in (sr1, sr2):
            w = dol.u32(sr)
            assert w & 0xFC0007FE == 0x7C000670 and (w >> 11) & 31 == 2, f"0x{sr:08X}: {w:08X}"
            dol.w32(sr, (w & ~(31 << 11)) | (shift << 11))           # srawi _,_,shift
    for addr in TIMES_10:
        _imm(dol, addr, 10, cols)
    for addr in COLUMN_BOUNDS:
        _imm(dol, addr, 10, cols)
    for addr in LAST_COLUMN:
        _imm(dol, addr, 9, cols - 1)
    _imm(dol, UP_WRAP, 0x16 + 30, 0x16 + (rows - 1) * cols)
    # 5 rows: the roster -> grid helper's bottom row -(bottom) & 3 -> -(bottom) * -(rows - 1) (then
    # `mulli r0,r0,cols`); the down handler stays in the grid while row + 1 < rows
    if rows != 4:
        _patch(dol, ENTRY_BOTTOM_ROW, 0x540007BE, (7 << 26) | (0 << 21) | (0 << 16) | (-(rows - 1) & 0xFFFF))
    _imm(dol, DOWN_ROWS, 4, rows)

    # i. Random team (FUN_800722ec) draws from a pool FUN_800721a0 builds by walking heads 0..40
    #    (r22, head list pointer r29), one available member of each head's wheel. It also walks the new
    #    heads 43.. (skipping the Mii groups 41, 42), and the pool buffer holds them all.
    a = Asm(code.here)
    a.cmpwi("r22", 41).bne("bound")
    a.li("r22", STOCK_HEADS).addi("r29", "r29", STOCK_HEADS - 41)
    a.label("bound")
    a.cmpwi("r22", first_empty).b(RANDOM_HEAD_BOUND + 4)                      # then blt: next head
    _patch(dol, RANDOM_HEAD_BOUND, 0x2C160029, Asm(RANDOM_HEAD_BOUND).b(code.put(a.assemble(), 4)).assemble_word())
    _patch(dol, RANDOM_POOL_ALLOC, 0x38600052, 0x38600000 | (2 * (41 + len(squares)) + 7) & ~7)
    # ... and FUN_80431df0 (charbuild.ID_POOL_ALLOC: a random pick by stats range) walks heads 0..40 twice the same
    #     way (counter, head list pointer): new heads 43.. too
    for site, count, ptr, word in POOL_HEAD_BOUNDS:
        a = Asm(code.here)
        a.cmpwi(count, 41).bne("bound")
        a.li(count, STOCK_HEADS).addi(ptr, ptr, STOCK_HEADS - 41)
        a.label("bound")
        a.cmpwi(count, first_empty).b(site + 4)                                   # then blt: next head
        _patch(dol, site, word, Asm(site).b(code.put(a.assemble(), 4)).assemble_word())

    desc = " | ".join(",".join(f"0x{c:02X}" for c in sq) for sq in squares)
    log = [f"grid: {cols}x{rows} squares, heads {NEW_HEADS[0]}-{first_empty - 1} ({desc}) + Luigi; "
           f"head list ({n_refs} refs) -> 0x{head_list:08X}; "
           f"objects 0x{OBJ_SIZE:X} / 0x{OBJ_B_SIZE:X} B; {len(POSITION_SITES)} position constants +{DELTA}"]
    if empty:
        _skip_empty(dol, code, first_empty, SQUARES)
        log.append(f"grid: cells {empty[0]}-{empty[-1]} empty (heads {first_empty}..): hidden, skipped by the "
                   f"D-pad and the pointer")
    return log


def _skip_empty(dol, code, first_empty, squares):
    """j. The cursor never stops on an empty cell (a head >= first_empty in the square -> head map)."""
    def empty_square(a, pos, out):                        # pos: a cursor position; branch to out unless empty
        a.addi(pos, pos, -0x16).cmplwi(pos, squares).bge(out)
        a.add(pos, pos, "r30").lbz(pos, MAP, pos).cmplwi(pos, first_empty).blt(out)

    # pointer: FUN_8006887c(f1, f2, grid) -> square or -1; an empty square is -1
    assert dol.u32(HIT_CALL - 8) == 0x387E0338, "pointer call: r3 = r30 + 0x338"
    a = Asm(code.here)
    a.stwu("r1", -0x10, "r1").mflr("r0").stw("r0", 0x14, "r1")
    a.bl(HIT_FN)
    a.cmpwi("r3", 0).blt("out")
    a.addi("r12", "r3", 0x16)
    empty_square(a, "r12", "out")
    a.li("r3", -1)
    a.label("out")
    a.lwz("r0", 0x14, "r1").mtlr("r0").addi("r1", "r1", 0x10).blr()
    _patch(dol, HIT_CALL, Asm(HIT_CALL).bl(HIT_FN).assemble_word(),
           Asm(HIT_CALL).bl(code.put(a.assemble(), 4)).assemble_word())

    # D-pad: call the handler again from the empty square (same direction) until the cursor is off
    # the empty squares; after HOLE_STEPS the cursor goes back where it was. Returns the last result.
    for call, fn, step in DPAD_CALLS:
        setup = (0x7FC3F378, 0x7EC4B378) + (() if step is None else (0x38A00000 | (step & 0xFFFF),))
        got = tuple(dol.u32(call - 4 * len(setup) + 4 * i) for i in range(len(setup)))
        assert got == setup, f"0x{call:08X}: not (r3 = r30, r4 = r22{', r5 = direction' if step else ''})"
        a = Asm(code.here)
        a.stwu("r1", -0x20, "r1").mflr("r0").stw("r0", 0x24, "r1").stw("r31", 0x1C, "r1")
        a.slwi("r31", "r22", 2).add("r31", "r31", "r30")               # r31 = obj + player * 4
        a.lwz("r0", CURSOR, "r31").stw("r0", 8, "r1")                  # where the cursor was
        a.li("r0", HOLE_STEPS).stw("r0", 0xC, "r1")
        a.label("move")
        a.mr("r3", "r30").mr("r4", "r22")
        if step is not None:
            a.li("r5", step)
        a.bl(fn)
        a.cmpwi("r3", 0).beq("out")
        a.lwz("r12", CURSOR, "r31")
        empty_square(a, "r12", "out")
        a.lwz("r12", 0xC, "r1").addi("r12", "r12", -1).stw("r12", 0xC, "r1")
        a.cmpwi("r12", 0).bgt("move")
        a.lwz("r0", 8, "r1").stw("r0", CURSOR, "r31")                  # (a row / column always has a square)
        a.label("out")
        a.lwz("r31", 0x1C, "r1").lwz("r0", 0x24, "r1").mtlr("r0").addi("r1", "r1", 0x20).blr()
        _patch(dol, call, Asm(call).bl(fn).assemble_word(), Asm(call).bl(code.put(a.assemble(), 4)).assemble_word())


def _moved(frame, dx):
    frame = bytearray(frame)
    for k in range(3):
        child = 4 + k * 0x3C
        x, = {struct.unpack_from(">h", frame, child + o)[0] for o in CHILD_XY}   # all three agree
        for o in CHILD_XY:
            struct.pack_into(">h", frame, child + o, x + dx)
    return bytes(frame)


# 5 rows at a 48 px pitch between the team bars (stock: 4 rows at 52, centres 135..291). The squares
# (0xA2, ~46 px tall, drawn centred on the node) span 82..320; the top team's bar, roster slots, stats
# card and marker move up TOP_DY (bar from y 31 to 3) and the bottom team's down BOTTOM_DY (bar from
# 320 to 323; the help bar starts right under it), leaving ~3 px above and below the grid.
ROW_Y0, ROW_PITCH = 105, 48
TOP_GROUP, TOP_DY = (0x9A, 0xB9, 0xBD, 0xB5), -28
BOTTOM_GROUP, BOTTOM_DY = (0x9B, 0xB8, 0xBE, 0xB4), 3
CHILD_Y = (0x0A, 0x1A, 0x1E)


def _at_y(frame, y):
    frame = bytearray(frame)
    for k in range(3):
        for o in CHILD_Y:
            struct.pack_into(">h", frame, 4 + k * 0x3C + o, y)
    return bytes(frame)


def _move_rows(data):
    """5 rows: the top team's bar, slots, card and marker up TOP_DY, the bottom team's down BOTTOM_DY."""
    data = bytearray(data)
    for group, dy in ((TOP_GROUP, TOP_DY), (BOTTOM_GROUP, BOTTOM_DY)):
        for k in group:
            for node in _keys(data, k):
                for key, _ in node:
                    for o in CHILD_Y:
                        y = struct.unpack_from(">h", data, key + o)[0]
                        struct.pack_into(">h", data, key + o, y + dy)
    return bytes(data)


def _rebuild_element(data, hidden=(), cols=COLS, rows=ROWS):
    """Element 0xBA with cols x rows nodes (square = row * cols + column); the hidden cells' nodes (j)
    HIDE_DX off screen. The container grows, so later elements, the resource rows and the container end
    move up."""
    data = bytearray(data)
    c = struct.unpack_from(">I", data, 4)[0]
    base = c + 0x14
    count = struct.unpack_from(">I", data, base)[0]
    offs = list(struct.unpack_from(f">{count}I", data, c + 0x1C))
    e = base + offs[GRID_ELEMENT]
    flags, n, size = struct.unpack_from(">III", data, e)
    fo = struct.unpack_from(f">{n}I", data, e + 12)
    sub = bytes(data[e + fo[0]:e + fo[0] + 0x10])
    stock = [bytes(data[e + f:e + f + FRAME]) for f in fo[1:]]
    assert all(struct.unpack_from(">HH", f) == (3, 0x3C) for f in stock), "unexpected frame layout"
    frames = []
    first = (cols - 9) // 2              # the stock columns' first (12: 1, 11: 1, 10: 0); new ones around them
    for row in range(rows):
        src = min(row, 3) * 10                                                # row 4 copies row 3
        line = []
        for col in range(cols):          # right edge at the stock column 9's x, 49 px apart
            k = min(max(col - first, 0), 9)
            dx = ((9 - k) - (cols - 1 - col)) * SQUARE_W
            line.append(_moved(stock[src + k], dx) if dx else stock[src + k])
        frames += [_at_y(f, ROW_Y0 + row * ROW_PITCH) for f in line] if rows == 5 else line
    frames = [_moved(f, HIDE_DX) if i in hidden else f for i, f in enumerate(frames)]
    head = 12 + 4 * (1 + len(frames))
    new_offs = [head] + [head + 0x10 + i * FRAME for i in range(len(frames))]
    elem = struct.pack(">III", flags, len(new_offs), head + 0x10 + len(frames) * FRAME)
    elem += struct.pack(f">{len(new_offs)}I", *new_offs) + sub + b"".join(frames)
    grow = len(elem) - size
    assert grow > 0 and grow % 4 == 0
    old_e = offs[GRID_ELEMENT]
    offs = [o + grow if o > old_e else o for o in offs]
    struct.pack_into(f">{count}I", data, c + 0x1C, *offs)
    rows_rel, = struct.unpack_from(">I", data, c + 0x18)
    assert rows_rel > old_e
    struct.pack_into(">I", data, c + 0x18, rows_rel + grow)
    for field in (0x0C, 0x10):                        # resource rows, end (from the container)
        v, = struct.unpack_from(">I", data, c + field)
        struct.pack_into(">I", data, c + field, v + grow)
    data[e:e + size] = elem
    return bytes(data)


# Team 0's vertical logo banner (element 0xA0, stock x 62, scale 1.8). A +/-90 degree banner is drawn
# 63..152 px (at scale 1.8) beside its x, away from the screen centre: stock -90..-1, now under the
# grid (left edge ~ -77). Measured in Dolphin, the visible screen starts at ~ -154, leaving 77 px: at
# scale 1.5 it spans ~ -153..-79 at x -26.
BANNER, BANNER_X, BANNER_SCALE = 0xA0, -26, 1.5
BARS = ((0x9A, 0x9C, 0xB9), (0x9B, 0x9D, 0xB8))   # (position, three-part bar, roster slots): top, bottom
BAR_MIDDLE_PX = 60                    # unscaled width of the bar's middle piece
BAR_GROW = -2 * SHIFT                 # the grid gained a column and moved one: bars reach 2 squares further left
SLOT_FIRST, SLOT_LAST = 47, 471       # stock slot x (9 slots, 53 px apart)


def _keys(data, k):
    """[[(key offset, stride), ...] per node] of element k."""
    c = struct.unpack_from(">I", data, 4)[0]
    e = c + 0x14 + struct.unpack_from(">I", data, c + 0x1C + 4 * k)[0]
    n = struct.unpack_from(">I", data, e + 4)[0]
    nodes = []
    for fo in struct.unpack_from(f">{n}I", data, e + 12)[1:]:
        cnt, stride = struct.unpack_from(">HH", data, e + fo)
        nodes.append([(e + fo + 4 + j * stride, stride) for j in range(cnt)])
    return nodes


def _move_key(data, key, dx):
    for o in CHILD_XY:
        x = struct.unpack_from(">h", data, key + o)[0]
        struct.pack_into(">h", data, key + o, x + dx)


def _stretch_bars(data, grow=BAR_GROW):
    """Bars start grow px further left and keep their right end; slots spread along them."""
    data = bytearray(data)
    for pos, bar, slots in BARS:
        refs = [(struct.unpack_from(">H", data, key + 6)[0], key) for node in _keys(data, pos) for key, _ in node
                if data[key + 4] == 3]
        assert refs and all(r == bar for r, _ in refs), f"0x{pos:X} does not place 0x{bar:X}"
        for _, key in refs:
            _move_key(data, key, -grow)
        middle, right_cap, left_cap = _keys(data, bar)
        for key, _ in middle:
            sx = struct.unpack_from(">f", data, key + 0x38)[0]
            struct.pack_into(">f", data, key + 0x38, sx + grow / BAR_MIDDLE_PX)
        for key, _ in right_cap:
            _move_key(data, key, grow)
        first = SLOT_FIRST - grow
        for i, node in enumerate(_keys(data, slots)):
            x = round(first + i * (SLOT_LAST - first) / 8)
            dx = x - struct.unpack_from(">h", data, node[0][0] + 8)[0]
            for key, _ in node:
                _move_key(data, key, dx)
    for node in _keys(data, BANNER):                   # banner: between the screen edge and the grid
        for key, _ in node:
            _move_key(data, key, BANNER_X - struct.unpack_from(">h", data, key + 8)[0])
            struct.pack_into(">ff", data, key + 0x34, BANNER_SCALE, BANNER_SCALE)
    return bytes(data)


# Nick: the whole roster screen a touch to the right (the 12-column grid left team 0's banner cut off
# at the screen's left edge and ~60 units free on the right). Every top-level element this screen
# places moves by SCREEN_DX: the grid, team bars and roster slots, both banners, both stats cards and
# the right-hand button column (Random / Next ...). The cursor, faces and pointer hit-testing follow
# the grid's nodes. Elements of other screens that share this file (single-player grid 0x97, the
# left/right pairs 0x3D/0x3F, 0x46/0x47) stay put.
SCREEN_DX = 40      # 24 -> 40 (Nick, 2026-09-25: everything but the stat card a little right; bench.py follows it)
SCREEN_ELEMENTS = (GRID_ELEMENT, 0x9A, 0x9B, 0xB8, 0xB9, 0xA0, 0xA1, 0xBD, 0xBE,
                   0x1A, 0x69, 0xB4, 0xB5, 0xB6, 0xBB, 0xBC)


def _shift_screen(data, dx=SCREEN_DX):
    data = bytearray(data)
    for k in SCREEN_ELEMENTS:
        for node in _keys(data, k):
            for key, _ in node:
                _move_key(data, key, dx)
    return bytes(data)


# Color-wheel swatches: elements 0xAD (unselected) / 0xAE (selected) have one key per swatch, time =
# selector byte 7, each key's four vertex colors (RGBA at +0x40) giving the color. Times 0-9 are the
# stock colors; 10 is an unused white end key, recolored orange (charbuild SWATCHES "orange").
SWATCH_ELEMENTS, SWATCH_ORANGE, ORANGE = (0xAD, 0xAE), 10, bytes.fromhex("ff8000ff")


def _orange_swatch(data):
    data = bytearray(data)
    for k in SWATCH_ELEMENTS:
        keys = [key for node in _keys(data, k) for key, stride in node
                if stride >= 0x50 and data[key + 4] == 4 and struct.unpack_from(">H", data, key + 2)[0] == SWATCH_ORANGE]
        assert len(keys) == 1, f"swatch element 0x{k:X}: {len(keys)} keys at time {SWATCH_ORANGE}"
        data[keys[0] + 0x40:keys[0] + 0x50] = ORANGE * 4
    return bytes(data)


def patch_layout(dol, dat_path, extra=None, grid=FULL):
    """a. Rebuild element 0xBA and stretch the team bars in each language's copy of dir 119 file 19;
    append the copies to dt_na.dat (the file grows) and repoint the index records. extra(data) -> data
    is applied to each copy last (charbuild: char_names.add_name_art). grid: plan() (cols, rows, empty
    cells, moved off screen); None: the stock grid (no square has a character), only the orange swatch and
    extra (the name rows, wheel7's popup frames, ...)."""
    import os
    import dtna_toc
    rec = dtna_toc.dir_pointers(dol)[LAYOUT_DIR] + LAYOUT_FILE * dtna_toc.FILE_RECORD
    w = list(struct.unpack(">12I", dol.read(rec, 48)))
    placed = {}
    with open(dat_path, "r+b") as f:
        for lang in range(3):
            off, length = w[2 + 4 * lang], w[1 + 4 * lang]
            if off not in placed:
                f.seek(off)
                new = f.read(length)
                if grid:
                    cols, rows, hidden = grid
                    new = _rebuild_element(new, hidden, cols, rows)
                    if cols > 10:
                        new = _stretch_bars(new, (cols - 10) * SQUARE_W)
                    if rows == 5:
                        new = _move_rows(new)
                    if screen_dx(grid):
                        new = _shift_screen(new, screen_dx(grid))
                new = _orange_swatch(new)
                if extra:
                    new = extra(new)
                end = os.path.getsize(dat_path)
                at = end + (-end % 32)
                f.seek(at)
                f.write(new)
                placed[off] = (at, len(new))
            at, n = placed[off]
            w[1 + 4 * lang], w[2 + 4 * lang], w[3 + 4 * lang] = n, at, n
    dol.write(rec, struct.pack(">12I", *w))
    what = (f"element 0x{GRID_ELEMENT:X} rebuilt with {grid[0]}x{grid[1]} squares"
            + (f" ({len(grid[2])} empty, off screen)" if grid[2] else "")
            + f", team bars {(grid[0] - 10) * SQUARE_W} px wider, screen {screen_dx(grid):+d} px"
            if grid else "stock grid")
    return [f"grid layout: {what}, swatch {SWATCH_ORANGE} orange; "
            f"{len(placed)} copies of dir {LAYOUT_DIR} file {LAYOUT_FILE} appended to dt_na.dat"]
