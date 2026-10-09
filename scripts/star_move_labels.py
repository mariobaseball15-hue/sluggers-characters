"""Star pitch / star swing name labels: King Bob-omb's star moves are "Kingly Kaboom" (Nick). See docs/star-swings.md.

The status widget that shows a character's skills (character select FUN_8006E260, batting-order bubble
FUN_8007F0FC, and FUN_8031D81C) draws each skill's name as an image, not text: abilities.LABEL_TABLES
0x8063AB80 = u16 *[4] star pitch 0x806233C0, star swing 0x806233DC, fielding, baserunning; each entry is a row
of the select layout (dt_na dir 119 file 19), indexed by the stats byte (+8 star pitch, +9 star swing). The
game has no star-move name in its message text.

King Bob-omb (0x78) carries Wario's stock star moves (7: Phony Ball / Phony Swing, rows 0x1A7 / 0x1A8), and Wario
no longer has them (charbuild.STOCK_STAT_EDITS clears his +8 / +9), so id 7 is only ever his. Both tables'
slot 7 get our row, which shows "Kingly Kaboom" for his star pitch and his star swing. The stock Phony rows stay
as they are (the Challenge-mode list 0x80650E90 reads its own table and layout, dir 119 file 12).

The label is stock art, not a font: the pixels of each letter are the stock labels' own (page 125, CI4 with a
16-level IA8 white palette), cut from labels drawn at the same vertical sub-pixel phase (stems full from row 2,
nothing on row 12), so the result is palette indices of the stock page, drawn the way the stock labels are:

  K i  Killer Ball (the pair as drawn)     n g  Phony Swing          l  Killer Ball     y  Phony Swing
  K    Killer Ball (K alone)              a    Hammer Throw          b  Rainbow Ball (the only lowercase b;
  o o  Teleport                           m    Hammer Throw             its ascender top row is 11/15, not 15)

Letters abut (gap 0) the way the stock letters do, and the word gap is 4 columns (Phony Swing's). At the stock
x (21-22) the name is 2 px too wide for the 112-px cell, so it starts at x 20 (Anger Dive's start) and ends at
x 111. GRID is the composed label (one hex digit = one palette index per pixel), so the build does not need the
English copy: every language's copy of file 19 gets it painted into the free cell PAGE_CELL of page 125 (below
the last stock label; checked empty) and a new row pointing there (layout_bytes, run by charbuild on
char_names.add_name_art's output, so the row follows the name and new-ability rows). compose() rebuilds GRID from an English
file 19; test_star_move_labels.py checks the two agree on both bases.

Captain select draws the same labels from its own copy: FUN_802CA65C (Select::CExhiCaptainTask) reads u16 *[4] at
0x806A17B8 (star pitch 0x8062C9FC, star swing 0x8062CA18, ...), rows of the captain layout (dir 119 file 18, page 46,
pixels identical to file 19's). captain_layout_bytes / patch_captain_tables give it the same GRID and point its slot 7
at it (charbuild, after captains.patch_layouts' own file-18 rows).
"""
import struct

import layout

PITCH_LABELS, SWING_LABELS = 0x806233C0, 0x806233DC
LABEL_SLOTS = 14                          # 0 none, 1-12 stock, 13 padding (0)
STOCK_PITCH_ROWS = (0xFFFF, 0x197, 0x199, 0x19B, 0x19D, 0x19F, 0x1A1, 0x1A7, 0x1A9, 0x1A3, 0x1AB, 0x1A5, 0x1AD)
STOCK_SWING_ROWS = (0xFFFF, 0x198, 0x19A, 0x19C, 0x19E, 0x1A0, 0x1A2, 0x1A8, 0x1AA, 0x1A4, 0x1AC, 0x1A6, 0x1AE)
PHONY = 7
NAMES = {PHONY: "Kingly Kaboom"}          # star move id -> name (the star pitch and the star swing)
OWNER = 0x78                              # King Bob-omb: the only character with star move 7

LABEL_PAGE = 125                          # the stock labels' page (1024 x 1024 CI4, IA8 palette)
PAGE_CELL = (556, 1008, 668, 1023)        # free: under Graffiti Swing's column (x0, y0, x1, y1)
CELL = (112, 15)
ALPHAS = (0x00, 0x10, 0x20, 0x30, 0x40, 0x50, 0x65, 0x80, 0x90, 0xA0, 0xB0, 0xC0, 0xD0, 0xE0, 0xF0, 0xFF)   # IA8, per index
ALPHAS_ALT = ALPHAS[:6] + (0x64,) + ALPHAS[7:]   # file 18's third language copy (page 46): index 6 is 0x64

KILLER_BALL, PHONY_SWING, HAMMER_THROW, RAINBOW_BALL, TELEPORT = 0x1A5, 0x1A8, 0x1B5, 0x1A3, 0x1BE
START_X = 20
# (source row, x0, x1 (exclusive, cell columns), empty columns before): "Kingly Kaboom"
PIECES = ((KILLER_BALL, 22, 33, 0),       # Ki
          (PHONY_SWING, 90, 106, 0),      # ng
          (KILLER_BALL, 34, 37, 0),       # l
          (PHONY_SWING, 55, 63, 0),       # y
          (KILLER_BALL, 22, 30, 4),       # K (word gap)
          (HAMMER_THROW, 30, 38, 0),      # a
          (RAINBOW_BALL, 51, 58, 0),      # b
          (TELEPORT, 56, 65, 0),          # o
          (TELEPORT, 56, 65, 0),          # o
          (HAMMER_THROW, 38, 47, 0))      # m
SOURCE_TEXT = {KILLER_BALL: "Killer Ball", PHONY_SWING: "Phony Swing", HAMMER_THROW: "Hammer Throw",
               RAINBOW_BALL: "Rainbow Ball", TELEPORT: "Teleport"}

GRID = (
    "0000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000",
    "0000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000",
    "00000000000000000000ff001cf94ff00000000000000004fb000000000000ff001cf900000000bb00000000000000000000000000000000",
    "00000000000000000000ff01cfc14ff00000000000440004fb000000000000ff01cfc100000000ff00000000000000000000000000000000",
    "00000000000000000000ff0cfc101440001430003dffdfb4fb000000000000ff0cfc1000242000ff02300000044000000044000000200220",
    "00000000000000000000ff9fe1004fb4feeffb00dfb9ffb4fbcf600ff10000ff9fe1001bfffa00ffaffc1006effe60006effe60fddf77ff6",
    "00000000000000000000ffff80004fb4ffedff62fe106fb4fb6fd05fa00000ffff80002fe9ff30fff8ef904ff99ff404ff99ff4ffefffefb",
    "00000000000000000000fffff3004fb4fd31cf74fb004fb4fb0ef49f600000fffff300054bff40ff605fd48f9009f848f9009f8fd1bf63fb",
    "00000000000000000000ff3bfc104fb4fb007f71ff21cfb4fb08f9df100000ff3bfc101bfeef40ff001ff4bf7007fb4bf7007fbfb07f40fb",
    "00000000000000000000ff02ef804fb4fb007f709fedffb4fb02fefa000000ff02ef806fe1cf40ff105fd48f8008f848f8008f8fb07f40fb",
    "00000000000000000000ff006ff44fb4fb007f7017ba7fb4fb00aff6000000ff006ff47fcbffc1ffe7df914ff88ff414ff88ff4fb07f40fb",
    "00000000000000000000ff000afd5fb4fb007f7064219fa4fb005ff1000000ff000afd2efe9df0fcbffc1006ffff60006ffff60fb07f40fb",
    "0000000000000000000000000000000000000000afffff500002afa000000000000000024101300003400000144100000144100000000000",
    "000000000000000000000000000000000000000047ab7300006fff4000000000000000000000000000000000000000000000000000000000",
    "000000000000000000000000000000000000000000000000001b720000000000000000000000000000000000000000000000000000000000",
)


def _px(page, w, x, y):
    b = page[((y // 8) * (w // 8) + x // 8) * 32 + (y % 8) * 4 + (x % 8) // 2]
    return b >> 4 if x % 2 == 0 else b & 15


def _set_px(page, w, x, y, v):
    i = ((y // 8) * (w // 8) + x // 8) * 32 + (y % 8) * 4 + (x % 8) // 2
    page[i] = (page[i] & 0x0F) | (v << 4) if x % 2 == 0 else (page[i] & 0xF0) | v


def _page(lay, p):
    """(offset of page p's image in lay.data, width, height). Checks the stock CI4 page: 16 IA8 entries, entry i at
    alpha ALPHAS[i] (or ALPHAS_ALT[i]; only the alphas: the index is what the label stores, whatever colour the palette gives it)."""
    desc = lay.descs[p]
    io, po, h, w = struct.unpack_from(">IIHH", desc, 0)
    assert desc[0x17] == 8 and desc[0x1A] == 0 and struct.unpack_from(">H", desc, 0x18)[0] == 16,         f"page {p}: not CI4 with 16 IA8 entries"
    new, new_pal = getattr(lay, "_new_images", {}), getattr(lay, "_new_palettes", {})
    pal = new_pal[p] if p in new else po + layout.TEX_BASE - lay.data_start      # a page added since the parse
    assert bytes(lay.data[pal:pal + 32:2]) in (bytes(ALPHAS), bytes(ALPHAS_ALT)), f"page {p}: unexpected palette alphas"
    return (new[p] if p in new else io + layout.TEX_BASE - lay.data_start), w, h


def _image(lay, p):
    """What page p samples: the stock files keep many pages over one image (file 19's pages 0-145 are one 1024 x
    1024 CI4 atlas, each with its own palette: page 92 draws the Next / Begin / OK buttons from it, page 125 the
    labels; file 18's pages 0-46 likewise), so a free cell must be free of every page's rows over that image."""
    new = getattr(lay, "_new_images", {})
    return ("new", p) if p in new else struct.unpack_from(">I", lay.descs[p], 0)[0]


def rows_over(lay, page, cell):
    """Rows of lay (on page or any page over the same image) whose rectangle overlaps cell (x0, y0, x1, y1)."""
    x0, y0, x1, y1 = cell
    img, out = _image(lay, page), []
    for r in range(len(lay.rows)):
        p, _, v1, u1, v2, u2 = struct.unpack(">HH4f", lay.rows[r])
        if _image(lay, p) != img:
            continue
        h, w = struct.unpack_from(">HH", lay.descs[p], 8)
        if u1 * w < x1 and x0 < u2 * w and v1 * h < y1 and y0 < v2 * h:
            out.append(r)
    return out


def row_cell(lay, r):
    """(page, x0, y0, x1, y1) of layout row r."""
    page, _, v1, u1, v2, u2 = struct.unpack(">HH4f", lay.rows[r])
    _, w, h = _page(lay, page)
    return page, round(u1 * w), round(v1 * h), round(u2 * w), round(v2 * h)


def cell_grid(lay, r):
    """Layout row r's cell as rows of palette indices."""
    page, x0, y0, x1, y1 = row_cell(lay, r)
    off, w, _ = _page(lay, page)
    img = lay.data[off:]
    return [[_px(img, w, x, y) for x in range(x0, x1)] for y in range(y0, y1)]


def compose(english_file19):
    """GRID from the English select layout (the source labels are English there)."""
    lay = layout.Layout(english_file19)
    out = [[0] * CELL[0] for _ in range(CELL[1])]
    x = START_X
    for row, x0, x1, gap in PIECES:
        src = cell_grid(lay, row)
        x += gap
        for y in range(CELL[1]):
            for k in range(x0, x1):
                if src[y][k]:
                    assert x + k - x0 < CELL[0], "label wider than its cell"
                    out[y][x + k - x0] = max(out[y][x + k - x0], src[y][k])
        x += x1 - x0
    return tuple("".join("0123456789abcdef"[v] for v in line) for line in out)


def row_number(max_id):
    """The new layout row: after char_names.add_name_art's name rows and abilities.NEW's rows."""
    import abilities
    import char_names
    return char_names.NAME_ROW_BASE + (max_id - char_names.FIRST_NEW + 1) + len(abilities.NEW)


def layout_bytes(data, max_id, chars=()):
    """One language's dir 119 file 19, after char_names.add_name_art: GRID painted into PAGE_CELL of page
    LABEL_PAGE and its row added (row_number(max_id)), then the custom swings' and chars' hitting abilities'
    labels (add_more_art, rows more_rows) and the custom star pitches' (add_pitch_art, rows pitch_rows), both on a
    page of their own (add_extra_page)."""
    lay = layout.Layout(data)
    add_art(lay, max_id)
    extra = add_extra_page(lay, size=extra_size())
    add_more_art(lay, max_id, chars, extra)
    add_pitch_art(lay, max_id, chars, extra)
    add_run_art(lay, max_id, chars, extra)      # + the running abilities' names (run_rows)
    return lay.to_bytes()


def extra_size():
    """EXTRA_SIZE, or twice as tall when a new star pitch's cell (17-20: PITCH_CELLS past 16 cells) is used."""
    last = max((PITCH_CELLS[p][3] for p in pitch_names()), default=0)
    return EXTRA_SIZE if last < EXTRA_SIZE[1] else (EXTRA_SIZE[0], 2 * EXTRA_SIZE[1])


def add_extra_page(lay, like=LABEL_PAGE, size=None):
    """A new CI4 page, EXTRA_SIZE, empty, with page LABEL_PAGE's palette (this language's copy): the custom swings',
    hitting abilities' and star pitches' labels (MORE_CELLS, PITCH_CELLS). Page 125's atlas has no room for them: it
    is 92 % under stock rows of its 146 pages, and the free-looking cells used before were blank parts of page 92's
    Next / Begin / OK buttons (rows 0xE5-0xE7), which then showed the labels. Returns the page. (like / size: another
    label page to copy, e.g. file 18's page 46 for item_abilities' captain labels, and another size.)"""
    pal, n = lay.palette(like)
    w, h = size or EXTRA_SIZE
    return lay.add_texture(bytes(w * h // 2), w, h, 8, template_page=like,
                           palette=bytes(lay.data[pal:pal + 2 * n]), palette_format=0)


def _paint(lay, page, cell, grid=GRID):
    """Paint grid (GRID) into cell (x0, y0, x1, y1) of page (checked empty, no row of any page over the same image
    over it) and add its row; returns the row."""
    off, w, h = _page(lay, page)
    x0, y0, x1, y1 = cell
    assert (x1 - x0, y1 - y0) == CELL and len(grid) == CELL[1] and all(len(g) == CELL[0] for g in grid)
    assert x1 <= w and y1 <= h, f"cell {cell} is outside page {page} ({w} x {h})"
    over = rows_over(lay, page, cell)
    assert not over, f"rows {[hex(r) for r in over]} overlap the star move label cell {cell} of page {page}"
    view = memoryview(lay.data)[off:off + w * h // 2]
    assert not any(_px(view, w, x, y) for x in range(x0, x1) for y in range(y0, y1)), "label cell not empty"
    for y, line in enumerate(grid):
        for x, v in enumerate(line):
            _set_px(view, w, x0 + x, y0 + y, int(v, 16))
    view.release()
    return lay.add_row(page, x0 / w, y0 / h, x1 / w, y1 / h)


def add_art(lay, max_id):
    """Paint GRID into PAGE_CELL of page LABEL_PAGE and add its row; returns the row."""
    assert len(lay.rows) == row_number(max_id), f"star move label: row {len(lay.rows)}, expected {row_number(max_id)}"
    for r in (STOCK_PITCH_ROWS[PHONY], STOCK_SWING_ROWS[PHONY]):
        assert row_cell(lay, r)[0] == LABEL_PAGE, f"row 0x{r:X} is not on page {LABEL_PAGE}"
    return _paint(lay, LABEL_PAGE, PAGE_CELL)


def patch_tables(dol, max_id, kaboom=True):
    """Point slot PHONY of the star pitch and star swing label tables at the new row. Returns log lines. kaboom False:
    King Bob-omb isn't built and Wario keeps his Phony moves (charbuild.STAR_MOVES_TO), so slot PHONY stays stock (the
    row is still added: later rows count on it)."""
    import abilities
    ptrs = struct.unpack(">4I", dol.read(abilities.LABEL_TABLES, 16))
    assert ptrs[:2] == (PITCH_LABELS, SWING_LABELS), "star move label tables moved"
    row = row_number(max_id)
    for table, stock in ((PITCH_LABELS, STOCK_PITCH_ROWS), (SWING_LABELS, STOCK_SWING_ROWS)):
        now = struct.unpack(f">{len(stock)}H", dol.read(table, 2 * len(stock)))
        assert now == stock, f"0x{table:08X}: unexpected rows {[hex(r) for r in now]}"
        if kaboom:
            dol.write(table + 2 * PHONY, struct.pack(">H", row))
    if not kaboom:
        return [f"star moves   pitch / swing label slot {PHONY} stays Phony (no King Bob-omb; row {row} unused)"]
    return [f"star moves   pitch / swing label slot {PHONY} -> row {row}: {NAMES[PHONY]!r} "
            f"(0x{PITCH_LABELS:08X} / 0x{SWING_LABELS:08X}; stock Phony rows 0x1A7 / 0x1A8 unchanged)"]


# --- captain select (Select::CExhiCaptainTask, layout dir 119 file 18) ---------------------------------------------
# FUN_802CA65C draws the hovered captain's skills from its own u16 *[4] at 0x806A17B8 (star pitch 0x8062C9FC, star
# swing 0x8062CA18, fielding 0x8062CA34, baserunning 0x8062CA50), rows of file 18, not file 19. Its labels are page
# 46 of file 18 (CI4, the same 16 IA8 alphas), 112 x 15 cells with pixels identical to file 19's (every star move,
# checked by the test), so GRID goes in unchanged, in the free cell right of Graffiti Swing's label (row 0x7B).
CAPTAIN_LABEL_TABLES = 0x806A17B8
CAPTAIN_PITCH_LABELS, CAPTAIN_SWING_LABELS = 0x8062C9FC, 0x8062CA18
CAPTAIN_STOCK_PITCH_ROWS = (0xFFFF, 0x66, 0x68, 0x6A, 0x6C, 0x6E, 0x70, 0x76, 0x78, 0x72, 0x7A, 0x74, 0x7C)
CAPTAIN_STOCK_SWING_ROWS = (0xFFFF, 0x67, 0x69, 0x6B, 0x6D, 0x6F, 0x71, 0x77, 0x79, 0x73, 0x7B, 0x75, 0x7D)
CAPTAIN_PAGE = 46
# captain select's fielding table 0x8062CA34 has 13 slots (0 none, 1-12; the next table follows), so a captain with a
# new fielding ability read past it: its pointer (0x806A17B8 [2]) goes to a CAPTAIN_FIELDING_SLOTS copy
# (patch_captain_fielding), the stock slots as they are, CAPTAIN_FIELDING_NAMES' ids pointing at their art (text_grid,
# free cells of page 46), 0xFFFF (no label) for the others. Clamber Jump (14) is its own ability (abilities.CLAMBER_JUMP;
# the Kongs, captains DK and Diddy included); stock Clamber (9) keeps its stock label.
CAPTAIN_FIELDING_LABELS = 0x8062CA34
CAPTAIN_STOCK_FIELDING_ROWS = (0xFFFF, 0x7F, 0x7E, 0x80, 0x81, 0x82, 0x83, 0x84, 0x85, 0x86, 0x87, 0x88, 0x89)
CAPTAIN_FIELDING_NAMES = {14: "Clamber Jump"}     # fielding ability -> name (abilities.NEW)
CAPTAIN_FIELDING_SLOTS = 16                       # as the cards' fielding table (abilities.FIELDING_SLOTS)
CAPTAIN_CELL = (113, 828, 225, 843)       # free: right of row 0x7B (Graffiti Swing), under row 0x90


def captain_row():
    """The new file-18 row: after captains.patch_layouts' rows (4 per custom captain)."""
    import captains
    return captains.STOCK_ROWS_18 + 4 * len(captains.NEW_CAPTAINS)


def captain_layout_bytes(data):
    """One language's dir 119 file 18, after captains' own edits: GRID painted into CAPTAIN_CELL of page
    CAPTAIN_PAGE and its row added (captain_row())."""
    lay = layout.Layout(data)
    assert len(lay.rows) == captain_row(), f"captain star move label: row {len(lay.rows)}, expected {captain_row()}"
    for r in (CAPTAIN_STOCK_PITCH_ROWS[PHONY], CAPTAIN_STOCK_SWING_ROWS[PHONY]):
        assert row_cell(lay, r)[0] == CAPTAIN_PAGE, f"file 18 row 0x{r:X} is not on page {CAPTAIN_PAGE}"
    _paint(lay, CAPTAIN_PAGE, CAPTAIN_CELL)
    add_captain_more_art(lay)                   # + the custom swings' names (captain_more_rows)
    add_captain_pitch_art(lay)                  # + the custom star pitches' names (captain_pitch_rows)
    add_captain_fielding_art(lay)               # + "Clamber Jump" (captain_fielding_rows)
    return lay.to_bytes()


def patch_captain_tables(dol, kaboom=True):
    """Point slot PHONY of captain select's star pitch and star swing tables at the new file-18 row (kaboom False:
    left stock, as patch_tables)."""
    ptrs = struct.unpack(">2I", dol.read(CAPTAIN_LABEL_TABLES, 8))
    assert ptrs == (CAPTAIN_PITCH_LABELS, CAPTAIN_SWING_LABELS), "captain select label tables moved"
    row = captain_row()
    for table, stock in ((CAPTAIN_PITCH_LABELS, CAPTAIN_STOCK_PITCH_ROWS), (CAPTAIN_SWING_LABELS, CAPTAIN_STOCK_SWING_ROWS)):
        now = struct.unpack(f">{len(stock)}H", dol.read(table, 2 * len(stock)))
        assert now == stock, f"0x{table:08X}: unexpected rows {[hex(r) for r in now]}"
        if kaboom:
            dol.write(table + 2 * PHONY, struct.pack(">H", row))
    return [f"star moves   captain select pitch / swing slot {PHONY} -> file 18 row {row}: {NAMES[PHONY]!r} "
            f"(0x{CAPTAIN_PITCH_LABELS:08X} / 0x{CAPTAIN_SWING_LABELS:08X}; stock rows 0x76 / 0x77 unchanged)"]


def patch_captain_fielding(dol, ext_at):
    """Captain select's fielding labels: the pointer 0x806A17B8 [2] -> a CAPTAIN_FIELDING_SLOTS copy at ext_at (stock
    slots 0-12, CAPTAIN_FIELDING_NAMES' rows, 0xFFFF). Returns a log line."""
    assert dol.u32(CAPTAIN_LABEL_TABLES + 8) == CAPTAIN_FIELDING_LABELS, "captain select fielding table moved"
    stock = struct.unpack(">13H", dol.read(CAPTAIN_FIELDING_LABELS, 26))
    assert stock == CAPTAIN_STOCK_FIELDING_ROWS, f"captain select fielding rows {[hex(r) for r in stock]}"
    ext = list(stock) + [0xFFFF] * (CAPTAIN_FIELDING_SLOTS - 13)
    rows = captain_fielding_rows()
    for a, r in rows.items():
        ext[a] = r
    dol.write(ext_at, struct.pack(f">{CAPTAIN_FIELDING_SLOTS}H", *ext))
    dol.w32(CAPTAIN_LABEL_TABLES + 8, ext_at)
    return (f"fielding row: captain select {CAPTAIN_FIELDING_SLOTS}-slot label table 0x{ext_at:08X}"
            + "".join(f", {a} {CAPTAIN_FIELDING_NAMES[a]!r} row {r}" for a, r in sorted(rows.items())))


def u16(dol, addr):
    return struct.unpack(">H", dol.read(addr, 2))[0]


# --- more star swing names: the custom swings (13-15) and hitting abilities (docs/star-swings.md) --------------------
# The card's star swing row shows LABEL_TABLES[1][stats +9], and a custom swing keeps its stock stand-in in +9
# (custom_swings "stats_swing": Rosalina 12 Graffiti, King Boo 8 Liar, Luma 1 Fire), so the card named the stock
# swing. A label SLOT is what the card shows in place of +9: a custom swing's own id (13..15). At the widget's read
# of its copied stats row (+0x74 of each status widget, `lbz r0,0x48(r1)`; the copy is at r1+0x40, +9 at r1+0x49) a
# stub stores OVERRIDE[id] (u8 per character id, 0 = keep) into the copy's +9. The stock code then lists it as
# skill (1, SLOT), with the star swing's bat icon (r2-0x7FC0 [1] = 0xD2). The stats row itself is untouched (the
# batting code still reads the stand-in; custom_swings' SETUP hook maps it). The label comes from a longer copy of
# the star swing table (the stock slots 0..12, copied after patch_tables so Kingly Kaboom's slot 7 is kept, then
# ours), which the cards' pointer table (item_abilities' 6 pointers) points to for category 1. The stock table
# stays: it has 14 slots, the 13th the only padding (ids 14.. would read the fielding table).
# A "hitting ability" (Lubba and the Lumas: "Star Get", a star when they come up to bat; Pauline's Showstopper,
# Dino Piranha's Piranha Patch) has slot FIRST_HITTING + k in the same long table, but it is not a star swing: it
# is its own row, item_abilities' category 5 (the bat icon, the long table as its label table), so a character
# with a real star swing shows both (Luma: Star Shower and Star Get).
# Captain select does the same with its own copies: FUN_802CA65C's `lbz r0,0x30(r1)` (0x802CA6F0; the stats copy at
# r1+0x28, whose first u16 is the character id, +9 at r1+0x31) and u16 *[4] 0x806A17B8 [1] -> a longer copy of
# 0x8062CA18 (the custom swings); its hitting and item rows are item_abilities.Card.patch_captain's.
# The labels: abilities.GLYPHS (stock letters at the stock spacing) as page-125 / page-46 palette indices, painted
# the way GRID is (file 19: on a page of their own with page 125's palette; file 18: free cells of page 46), so they
# show exactly like the stock labels.
import item_abilities as _ia   # noqa: E402

FIRST_HITTING = 16                        # label slots: 13-15 the custom swings, then the hitting abilities
WIDGET_READ, WIDGET_READ_WORD = 0x74, 0x88010048              # lbz r0,0x48(r1) in each item_abilities.WIDGETS
CAPTAIN_READ, CAPTAIN_READ_WORD = 0x802CA6F0, 0x88010030      # lbz r0,0x30(r1) in FUN_802CA65C
STOCK_SWING_SLOTS = 14                    # both swing tables: 0 none, 1-12, 13 padding
# File 19: 112 x 15 cells at a 16-px pitch on the page add_extra_page adds (EXTRA_SIZE: 16 cells), the labels only.
# (They were on page 125 until the Begin button showed them: see add_extra_page.) File 18: free cells of page 46
# (empty with a 1-px margin in every language on both bases, no row of any page over the atlas on them).
EXTRA_SIZE = (128, 256)


def extra_cell(k):
    return (0, 16 * k, CELL[0], 16 * k + CELL[1])


MORE_CELLS = tuple(extra_cell(k) for k in range(10))                                     # file 19, the extra page
CAPTAIN_MORE_CELLS = tuple((520, 920 + 16 * k, 632, 935 + 16 * k) for k in range(6))      # file 18, page 46


def custom_names():
    """{swing id: name} of custom_swings.SWINGS (13 Gravity Ball, 14 Boo Ball, 15 Star Shower)."""
    import custom_swings
    names = {sid: sw["name"] for sid, sw in custom_swings.SWINGS.items()}
    assert all(STOCK_SWING_SLOTS - 1 <= sid < FIRST_HITTING for sid in names), f"custom swing ids {sorted(names)}"
    return names


MIN_SQUEEZE = 0.8                         # text_grid squeezes a wide text to no less than this (Shadow Clone: 0.94)


def text_grid(text):
    """text as 15 rows of 112 page-125 palette indices (hex strings, like GRID): abilities.GLYPHS at the stock
    spacing (abilities.KERN / SPACE) from x abilities.TEXT_X; a text wider than the cell ("Piranha Patch", "Shadow
    Clone") squeezed to fit exactly as abilities.label_image squeezes the item labels (its alphas, as indices)."""
    import abilities
    alpha = abilities.text_alpha(text)                  # raises abilities.MissingGlyph (glyph_cells below too)
    room = CELL[0] - abilities.TEXT_X
    if alpha.size[0] > room:
        assert alpha.size[0] * MIN_SQUEEZE <= room, f"{text!r} is too wide to squeeze into the label ({alpha.size[0]} > {room})"
        img = abilities.label_image(text).getchannel("A")
        return tuple("".join("0123456789abcdef"[abilities.LABEL_ALPHA.index(img.getpixel((x, y)))]
                             for x in range(CELL[0])) for y in range(CELL[1]))
    out = [[0] * CELL[0] for _ in range(CELL[1])]
    x, prev = abilities.TEXT_X, None
    for ch in text:
        if ch == " ":
            x, prev = x + abilities.SPACE, None
            continue
        if prev:
            x += abilities.KERN.get((prev, ch), 1)
        g = abilities.glyph_cells(ch)
        assert x + len(g[0]) <= CELL[0], f"{text!r} is wider than the label ({x + len(g[0])} > {CELL[0]})"
        for y in range(CELL[1]):
            for k, v in enumerate(g[y]):
                out[y][x + k] = max(out[y][x + k], v)
        x, prev = x + len(g[0]), ch
    return tuple("".join("0123456789abcdef"[v] for v in line) for line in out)


def hitting_of(c):
    """normalize: a definition's "hitting_ability" (its own card row, bat icon: item_abilities category 5), or None."""
    name = c.get("hitting_ability")
    if name is None:
        return None
    assert isinstance(name, str) and name and name.strip() == name, f"{c.get('name')}: bad hitting ability {name!r}"
    text_grid(name)                       # asserts stock glyphs and the fit
    return name


def hitting_names(chars):
    """[name, ...] in the order of first use by id: slot FIRST_HITTING + k."""
    out = []
    for c in sorted(chars, key=lambda c: c["id"]):
        if c.get("hitting_ability") and c["hitting_ability"] not in out:
            out.append(c["hitting_ability"])
    return out


def more_names(chars=()):
    """{label slot: name}: the custom swings, then the hitting abilities."""
    names = dict(custom_names())
    names.update({FIRST_HITTING + k: n for k, n in enumerate(hitting_names(chars))})
    return names


def more_rows(max_id, chars=()):
    """{slot: dir 119 file 19 row}: right after the Kingly Kaboom row, in slot order."""
    return {s: row_number(max_id) + 1 + k for k, s in enumerate(sorted(more_names(chars)))}


def captain_more_rows():
    """{swing id: dir 119 file 18 row}: the custom swings, right after captain select's Kingly Kaboom row."""
    return {s: captain_row() + 1 + k for k, s in enumerate(sorted(custom_names()))}


def add_more_art(lay, max_id, chars, page):
    """Paint more_names into MORE_CELLS of page (add_extra_page's), one row each (more_rows)."""
    names, rows = more_names(chars), more_rows(max_id, chars)
    assert len(rows) <= len(MORE_CELLS), f"{len(rows)} labels, {len(MORE_CELLS)} free cells (MORE_CELLS)"
    for (slot, row), cell in zip(sorted(rows.items()), MORE_CELLS):
        assert len(lay.rows) == row, f"{names[slot]!r}: row {len(lay.rows)}, expected {row}"
        _paint(lay, page, cell, text_grid(names[slot]))


def add_captain_more_art(lay):
    names, rows = custom_names(), captain_more_rows()
    for (sid, row), cell in zip(sorted(rows.items()), CAPTAIN_MORE_CELLS):
        assert len(lay.rows) == row, f"captain {names[sid]!r}: row {len(lay.rows)}, expected {row}"
        _paint(lay, CAPTAIN_PAGE, cell, text_grid(names[sid]))


def _stub(space, id_at, row_at, table, max_id, back, run_table=None):
    """For a skill list's `lbz r0,row_at+8(r1)` (the copied stats row at r1+row_at): if OVERRIDE[id] (id = the s16
    at r1+id_at, 0..max_id) is nonzero, store it into the copy's +9 (and a nonzero RUN_OVERRIDE[id] into +11, with
    run_table); then the replaced load, and back."""
    from ppc import Asm
    a = Asm(space.here)
    a.lha("r3", id_at, "r1").cmpwi("r3", 0).blt("done")
    a.cmpwi("r3", max_id).bgt("done")
    a.load_addr("r12", table).lbzx("r12", "r12", "r3")
    a.cmpwi("r12", 0).beq("swing_kept")
    a.stb("r12", row_at + 9, "r1")
    a.label("swing_kept")
    if run_table is not None:
        a.load_addr("r12", run_table).lbzx("r12", "r12", "r3")
        a.cmpwi("r12", 0).beq("done")
        a.stb("r12", row_at + 11, "r1")
    a.label("done")
    a.lbz("r0", row_at + 8, "r1")
    a.b(back)
    return space.put(a.assemble(), 4)


class SwingCard:
    """What apply placed. patch (after patch_tables) and patch_captain (after patch_captain_tables) copy the stock
    slots, which are final by then, add ours, and write the hooks."""
    def __init__(self, max_id, chars, who, override, captain_override, ext, captain_ext, stubs, captain_stub,
                 pitch_ext=None, captain_pitch_ext=None, run_override=None, run_ext=None, captain_fielding_ext=None):
        self.max_id, self.chars, self.who = max_id, chars, who
        self.run_override, self.run_ext = run_override, run_ext
        self.override, self.captain_override, self.ext, self.captain_ext = override, captain_override, ext, captain_ext
        self.stubs, self.captain_stub = stubs, captain_stub
        self.pitch_ext, self.captain_pitch_ext = pitch_ext, captain_pitch_ext
        self.captain_fielding_ext = captain_fielding_ext

    def patch(self, dol, item_card):
        """Character select, the batting-order bubble and FUN_8031D81C: the long swing table, the three hooks."""
        from ppc import Asm
        assert item_card is not None, "the star swing row needs item_abilities' card pointer table"
        assert dol.u32(item_card.ptrs + 4) == SWING_LABELS, "card pointer table: the star swing entry moved"
        stock = struct.unpack(">13H", dol.read(SWING_LABELS, 26))
        rows = more_rows(self.max_id, self.chars)
        ext = list(stock) + [0xFFFF] * (max(rows) + 1 - 13)
        for slot, row in rows.items():
            ext[slot] = row
        dol.write(self.ext, struct.pack(f">{len(ext)}H", *ext))
        dol.w32(item_card.ptrs + 4, self.ext)
        assert dol.u32(item_card.ptrs + 4 * _ia.HIT_CATEGORY) == SWING_LABELS, "card pointer table: the hitting entry moved"
        dol.w32(item_card.ptrs + 4 * _ia.HIT_CATEGORY, self.ext)     # the hitting row's labels: the same long table
        for base, stub in zip(_ia.WIDGETS, self.stubs):
            assert dol.u32(base + WIDGET_READ) == WIDGET_READ_WORD, f"0x{base + WIDGET_READ:08X} is not stock"
            dol.w32(base + WIDGET_READ, Asm(base + WIDGET_READ).b(stub).assemble_word())
        names = more_names(self.chars)
        run = []
        if self.run_ext is not None:                            # the baserunning row: a longer copy for category 3
            assert dol.u32(item_card.ptrs + 12) == BASERUNNING_LABELS, "card pointer table: the baserunning entry moved"
            rrows = run_rows(self.max_id, self.chars)
            rext = list(struct.unpack(f">{STOCK_RUN_SLOTS}H", dol.read(BASERUNNING_LABELS, 2 * STOCK_RUN_SLOTS)))
            assert tuple(rext) == STOCK_RUN_ROWS, f"unexpected baserunning rows {[hex(r) for r in rext]}"
            rext += [0xFFFF] * (max(rrows) + 1 - STOCK_RUN_SLOTS)
            for slot, row in rrows.items():
                rext[slot] = row
            dol.write(self.run_ext, struct.pack(f">{len(rext)}H", *rext))
            dol.w32(item_card.ptrs + 12, self.run_ext)
            rnames = running_names(self.chars)
            run = [f"baserunning row: {len(rext)}-slot label table 0x{self.run_ext:08X}, slots "
                   + ", ".join(f"{s} {rnames[s]!r} row {r}" for s, r in sorted(rrows.items()))
                   + "; cards: " + ", ".join(f"{c['name']} {c['running_ability']!r}" for c in self.chars
                                             if c.get("running_ability"))]
        return run + [f"star swing row: {len(ext)}-slot label table 0x{self.ext:08X}, slots "
                + ", ".join(f"{s} {names[s]!r} row {r}" for s, r in sorted(rows.items()))
                + "; cards: " + ", ".join(f"{n} {names[s]!r}" for n, s in self.who),
                patch_pitch_table(dol, item_card.ptrs, PITCH_LABELS, self.pitch_ext, pitch_rows(self.max_id, self.chars),
                                  "star pitch row")]

    def patch_captain(self, dol):
        """Captain select: the long swing table (0x806A17B8 [1]) and the hook at 0x802CA6F0."""
        from ppc import Asm
        ptrs = struct.unpack(">2I", dol.read(CAPTAIN_LABEL_TABLES, 8))
        assert ptrs == (CAPTAIN_PITCH_LABELS, CAPTAIN_SWING_LABELS), "captain select label tables moved"
        stock = struct.unpack(">13H", dol.read(CAPTAIN_SWING_LABELS, 26))
        rows = captain_more_rows()
        ext = list(stock) + [0xFFFF] * (max(rows) + 1 - 13)
        for sid, row in rows.items():
            ext[sid] = row
        dol.write(self.captain_ext, struct.pack(f">{len(ext)}H", *ext))
        dol.w32(CAPTAIN_LABEL_TABLES + 4, self.captain_ext)
        assert dol.u32(CAPTAIN_READ) == CAPTAIN_READ_WORD, f"0x{CAPTAIN_READ:08X} is not stock"
        dol.w32(CAPTAIN_READ, Asm(CAPTAIN_READ).b(self.captain_stub).assemble_word())
        names = custom_names()
        return [f"star swing row: captain select {len(ext)}-slot table 0x{self.captain_ext:08X}, file 18 rows "
                + ", ".join(f"{s} {names[s]!r} row {r}" for s, r in sorted(rows.items())),
                patch_pitch_table(dol, CAPTAIN_LABEL_TABLES, CAPTAIN_PITCH_LABELS, self.captain_pitch_ext,
                                  captain_pitch_rows(), "star pitch row: captain select"),
                patch_captain_fielding(dol, self.captain_fielding_ext)]


def apply(dol, space, chars, max_id, skills, custom=True):
    """Override tables, the two long tables (filled later) and the stubs, in space (item_abilities' section).
    chars: normalized (c["hitting_ability"], c["item_ability"]); skills(id) -> the stats bytes +8..+11 as built;
    custom: the custom swings are on (charbuild star_swings). Refuses a card that would need more than
    item_abilities.MAX_SHOWN lines (with the hitting and item rows). Returns (log lines, SwingCard). A hitting ability
    is not written here (it is item_abilities' category 5, labelled from the long table), only named in the log."""
    import custom_swings
    names = more_names(chars)
    size = max_id + 1 + (-(max_id + 1) % 4)
    override, captain_override, who = bytearray(size), bytearray(size), []
    by_id = {c["id"]: c for c in chars}
    if custom:
        for sid, sw in custom_swings.SWINGS.items():
            for cid in sw["chars"]:
                if cid >= 0x65 and cid not in by_id:           # a new character this build leaves out
                    continue
                assert cid <= max_id and skills(cid)[1] == sw["stats_swing"], \
                    f"0x{cid:02X}: stats swing {skills(cid)[1]}, expected {sw['name']}'s stand-in {sw['stats_swing']}"
                override[cid] = captain_override[cid] = sid
                who.append((by_id.get(cid, {}).get("name", f"0x{cid:02X}"), sid))
    slot = {n: s for s, n in names.items() if s >= FIRST_HITTING}
    import captains
    captain_ids = {c["id"] for c in captains.NEW_CAPTAINS}
    for c in chars:
        assert not (c["id"] in captain_ids and c.get("running_ability")), \
            f"{c['name']}: a captain; captain select shows no running ability (its own tables)"
    rnames = running_names(chars)
    rslot = {n: s for s, n in rnames.items()}
    run_override = bytearray(size)
    for c in chars:
        if c.get("running_ability"):
            assert skills(c["id"])[3] == 0, (f"{c['name']}: a running ability goes on the baserunning row, but it has "
                                             f"baserunning ability {skills(c['id'])[3]}")
            run_override[c["id"]] = rslot[c["running_ability"]]
    for c in chars:
        if c.get("hitting_ability"):                            # its own row (item_abilities category 5)
            who.append((c["name"], slot[c["hitting_ability"]]))
    for c in chars:
        s = list(skills(c["id"]))
        assert s[0] < STOCK_PITCH_SLOTS - 1 or s[0] in PITCH_NAMES, \
            f"{c['name']}: star pitch {s[0]} has no name in PITCH_NAMES (its menu label)"
        s[1] = override[c["id"]] or s[1]
        s[3] = run_override[c["id"]] or s[3]
        shown = _ia.lines(s, c.get("item_ability"), c.get("hitting_ability"))
        assert shown <= _ia.MAX_SHOWN, (f"{c['name']}: the card would need {shown} lines (it has {_ia.MAX_SHOWN}): "
                                        f"skills {s}, hitting {c.get('hitting_ability')}, item {c.get('item_ability')}")
    at = space.put(bytes(override), 4)
    rat = space.put(bytes(run_override), 4) if rnames else None
    rext = space.put(bytes(2 * (max(rnames) + 1)), 4) if rnames else None
    cat = space.put(bytes(captain_override), 4)
    ext = space.put(bytes(2 * (max(names) + 1)), 4)
    cext = space.put(bytes(2 * (max(custom_names()) + 1)), 4)
    pext = space.put(bytes(2 * PITCH_SLOTS + 2), 4)            # (+2: the stubs below start 4-aligned)
    cpext = space.put(bytes(2 * PITCH_SLOTS + 2), 4)
    cfext = space.put(bytes(2 * CAPTAIN_FIELDING_SLOTS), 4)     # captain select's fielding labels (patch_captain)
    stubs = [_stub(space, 0x14, 0x40, at, max_id, base + WIDGET_READ + 4, rat) for base in _ia.WIDGETS]
    cstub = _stub(space, 0x28, 0x28, cat, max_id, CAPTAIN_READ + 4)
    return ([f"star swing row: overrides 0x{at:08X} (" + ", ".join(f"{n} -> {s}" for n, s in who) + ")"]
            + ([f"baserunning row: overrides 0x{rat:08X} (" + ", ".join(
                f"{c['name']} -> {rslot[c['running_ability']]}" for c in chars if c.get("running_ability")) + ")"]
               if rnames else []),
            SwingCard(max_id, chars, who, at, cat, ext, cext, stubs, cstub, pext, cpext, rat, rext, cfext))


# --- custom star pitch names (pitch ids 13-16) -----------------------------------------------------------------------
# A custom star pitch keeps its own id in the stats row (+8 = 13..16; the pitching code maps it to a stock pitch,
# e.g. pitch_gravity_well.py), so the cards and captain select index their star pitch label tables with it. Both
# stock tables have 14 slots (13 = padding, 14.. would read the next table), so both category-0 pointers are
# redirected to longer copies, PITCH_SLOTS long, as the star swing ones are (above): the cards' pointer table
# (item_abilities' 5 pointers) [0] and captain select's 0x806A17B8 [0]. The copies take the stock slots 0-12 after
# patch_tables / patch_captain_tables (Kingly Kaboom's slot 7 kept); slots 13-16 point at the PITCH_NAMES labels
# (0xFFFF where there is no name; apply refuses a character whose stats +8 is such an id). No stub: the stats byte
# itself is the id. The labels are text_grid (stock glyphs), painted into file 19's extra page (after the swings'
# cells) and free cells of page 46 (file 18); their rows follow the custom swing / hitting ability rows (pitch_rows)
# and captain select's custom swing rows (captain_pitch_rows).
# To add a pitch: its name in PITCH_NAMES (each id 13..16 has its cell reserved below), its stats +8 in the definition.
PITCH_NAMES = {13: "Cosmic Pull"}         # pitch id -> name: 13 Rosalina (pitch_gravity_well.py; Nick: was "Gravity Well",
                                          # no stock W); 14-16 reserved
PITCH_NAMES[16] = "Vanishing Ball"        # King Boo (pitch_vanishing_ball.py)
PITCH_NAMES[15] = "Bob-omb Drop"          # King Bob-omb (pitch_bobomb_drop.py; D and - in abilities.GLYPHS / DERIVED)
PITCH_NAMES[14] = "Launch Star"           # Luma (pitch_launch_star.py; L cut from Liar Ball, abilities.GLYPHS)
FIRST_CUSTOM_PITCH, PITCH_SLOTS = 13, 17  # label slots 0..16
STOCK_PITCH_SLOTS = 14                    # both stock star pitch tables: 0 none, 1-12, 13 padding
# one 112 x 15 cell per pitch id 13..16: file 19 on add_extra_page's page after MORE_CELLS; file 18 free cells of
# page 46 (empty with a 1-px margin in every language on both bases, no row of any page over the atlas on them:
# test_star_move_labels checks; y 910 was under rows 0xD / 0xF, pages 5 / 7)
PITCH_CELLS = {p: extra_cell(len(MORE_CELLS) + k) for k, p in enumerate(range(13, 21))}   # file 19, the extra page
CAPTAIN_PITCH_CELLS = {p: (4, 926 + 16 * k, 116, 941 + 16 * k) for k, p in enumerate(range(13, 17))}   # file 18, page 46
# the new star pitches 17-20 (pitch_new): free cells of page 46 found by a scan (empty with a 1-px margin in every
# language on both bases, stock and after captains' edits; no row of any page over the atlas): test_star_move_labels
CAPTAIN_PITCH_CELLS.update({17: (733, 465, 845, 480), 18: (849, 465, 961, 480), 19: (733, 497, 845, 512),
                            20: (849, 497, 961, 512)})


def pitch_names():
    """{pitch id: name} of PITCH_NAMES (checked: ids 13..16, stock glyphs that fit)."""
    assert all(FIRST_CUSTOM_PITCH <= p < PITCH_SLOTS for p in PITCH_NAMES), f"custom pitch ids {sorted(PITCH_NAMES)}"
    for name in PITCH_NAMES.values():
        text_grid(name)
    return dict(PITCH_NAMES)


def pitch_rows(max_id, chars=()):
    """{pitch id: dir 119 file 19 row}: right after the custom swing / hitting ability rows, in id order."""
    first = row_number(max_id) + 1 + len(more_names(chars))
    return {p: first + k for k, p in enumerate(sorted(pitch_names()))}


def captain_pitch_rows():
    """{pitch id: dir 119 file 18 row}: right after captain select's custom swing rows."""
    first = captain_row() + 1 + len(custom_names())
    return {p: first + k for k, p in enumerate(sorted(pitch_names()))}


def add_pitch_art(lay, max_id, chars, page):
    """Paint the PITCH_NAMES labels into PITCH_CELLS of page (add_extra_page's), one row each (pitch_rows)."""
    names = pitch_names()
    for p, row in sorted(pitch_rows(max_id, chars).items()):
        assert len(lay.rows) == row, f"pitch {names[p]!r}: row {len(lay.rows)}, expected {row}"
        _paint(lay, page, PITCH_CELLS[p], text_grid(names[p]))


def add_captain_pitch_art(lay):
    """Paint the PITCH_NAMES labels into CAPTAIN_PITCH_CELLS of page CAPTAIN_PAGE (captain_pitch_rows)."""
    names = pitch_names()
    for p, row in sorted(captain_pitch_rows().items()):
        assert len(lay.rows) == row, f"captain pitch {names[p]!r}: row {len(lay.rows)}, expected {row}"
        _paint(lay, CAPTAIN_PAGE, CAPTAIN_PITCH_CELLS[p], text_grid(names[p]))


def captain_fielding_rows():
    """{fielding ability: dir 119 file 18 row}: right after captain select's custom pitch rows."""
    first = captain_row() + 1 + len(custom_names()) + len(pitch_names())
    return {a: first + k for k, a in enumerate(sorted(CAPTAIN_FIELDING_NAMES))}


def add_captain_fielding_art(lay):
    """Paint CAPTAIN_FIELDING_NAMES into the CAPTAIN_MORE_CELLS after the custom swings' (captain_fielding_rows)."""
    cells = CAPTAIN_MORE_CELLS[len(custom_names()):]
    rows = captain_fielding_rows()
    assert len(rows) <= len(cells), "no free captain label cell"
    for (a, row), cell in zip(sorted(rows.items()), cells):
        assert len(lay.rows) == row, f"captain fielding {CAPTAIN_FIELDING_NAMES[a]!r}: row {len(lay.rows)}, expected {row}"
        _paint(lay, CAPTAIN_PAGE, cell, text_grid(CAPTAIN_FIELDING_NAMES[a]))


# --- running abilities: the baserunning row with the shoe icon (Pom Pom's "Shadow Clone") ----------------------------
# The same mechanism as the hitting abilities, one row down: a definition's "running_ability" shows on the card's
# baserunning row (category 3, the stock shoe icon r2-0x7FC0 [3] = 0xD4) for a character with no baserunning ability
# (+11 = 0). The stubs at the widgets' stats-copy read (_stub) also store RUN_OVERRIDE[id] (u8 per character id,
# 0 = keep) into the copy's +11, so the stock list builder lists it as skill (3, slot) in the stock order. The
# stock baserunning table 0x80623418 has 8 slots (0 none, 1-7 Scatter Dive .. Enlarge; the words after it are other
# data), so the cards' pointer table [3] points to a longer copy: stock slots 0-7, then FIRST_RUNNING + k per name.
# The labels: text_grid, painted into the MORE_CELLS (add_extra_page's page) the custom swing / hitting names leave
# free; their rows follow
# the custom pitch rows (run_rows). Cards only: captain select shows captains, and apply refuses a hitting or
# running ability on a captain.
BASERUNNING_LABELS, STOCK_RUN_SLOTS, FIRST_RUNNING = 0x80623418, 8, 8
STOCK_RUN_ROWS = (0xFFFF,) + tuple(range(0x1BB, 0x1C2))      # 1 Scatter Dive .. 7 Enlarge (file 19)


def running_of(c):
    """normalize: a definition's "running_ability" (shown on the baserunning row, shoe icon), or None."""
    name = c.get("running_ability")
    if name is None:
        return None
    assert isinstance(name, str) and name and name.strip() == name, f"{c.get('name')}: bad running ability {name!r}"
    text_grid(name)                       # asserts stock glyphs and the fit
    return name


def running_names(chars=()):
    """{baserunning label slot: name}: FIRST_RUNNING + k in the order of first use by id."""
    out = []
    for c in sorted(chars, key=lambda c: c["id"]):
        if c.get("running_ability") and c["running_ability"] not in out:
            out.append(c["running_ability"])
    return {FIRST_RUNNING + k: n for k, n in enumerate(out)}


def run_rows(max_id, chars=()):
    """{baserunning slot: dir 119 file 19 row}: right after the custom pitch rows."""
    first = row_number(max_id) + 1 + len(more_names(chars)) + len(pitch_names())
    return {s: first + k for k, s in enumerate(sorted(running_names(chars)))}


def add_run_art(lay, max_id, chars, page):
    """Paint running_names into the MORE_CELLS (of page, add_extra_page's) after more_names' (run_rows)."""
    names, rows = running_names(chars), run_rows(max_id, chars)
    cells = MORE_CELLS[len(more_names(chars)):]
    assert len(rows) <= len(cells), f"{len(rows)} running labels, {len(cells)} free cells left (MORE_CELLS)"
    for (slot, row), cell in zip(sorted(rows.items()), cells):
        assert len(lay.rows) == row, f"running {names[slot]!r}: row {len(lay.rows)}, expected {row}"
        _paint(lay, page, cell, text_grid(names[slot]))


def patch_pitch_table(dol, ptrs, stock_table, ext_at, rows, what):
    """Point the category-0 (star pitch) entry of the u32 table at ptrs, now stock_table, at a PITCH_SLOTS copy at
    ext_at: stock slots 0..12 as they stand, 13..16 = rows (0xFFFF where none). Returns a log line."""
    assert dol.u32(ptrs) == stock_table, f"0x{ptrs:08X}: the star pitch entry is not 0x{stock_table:08X}"
    ext = list(struct.unpack(">13H", dol.read(stock_table, 26))) + [0xFFFF] * (PITCH_SLOTS - 13)
    for p, row in rows.items():
        ext[p] = row
    dol.write(ext_at, struct.pack(f">{PITCH_SLOTS}H", *ext))
    dol.w32(ptrs, ext_at)
    names = pitch_names()
    return (f"{what}: {PITCH_SLOTS}-slot label table 0x{ext_at:08X}"
            + "".join(f", {p} {names[p]!r} row {r}" for p, r in sorted(rows.items())))


# --- every label drawn from abilities.GLYPHS ------------------------------------------------------------------------
def glyph_label_names(chars=()):
    """{name: [where]} of every label text the build draws from abilities.GLYPHS (text_grid / label_image): the new
    fielding abilities (abilities.NEW), the item abilities, the custom swings, the hitting and running abilities,
    the custom pitches and captain select's fielding names (Clamber Jump). Kingly Kaboom (GRID) and Challenge mode's
    Clamber Jump (char_names) are stock pixels cut whole, not glyphs. test_star_move_labels renders each one."""
    import abilities
    import item_abilities
    out = {}
    for where, names in (("fielding ability", abilities.NEW.values()), ("item ability", item_abilities.labels(item_abilities.with_stock(chars))),
                         ("custom swing", custom_names().values()), ("hitting ability", hitting_names(chars)),
                         ("running ability", running_names(chars).values()), ("star pitch", PITCH_NAMES.values()),
                         ("captain fielding", CAPTAIN_FIELDING_NAMES.values())):
        for n in names:
            out.setdefault(n, []).append(where)
    return out
