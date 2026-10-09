"""Character names for new characters (charbuild step 13).

The game's character names are dt_na dir 121 file 5, a message table per language (u8 1, u8 1, u16
count, u32 offset[count] in u16 units from the text after them, plain UTF-16 strings): message i is
character id i's name (0 Mario .. 70 Pink Yoshi, 71-76 "#N/A", 77-100 "Mii"), then 101-103 are
formatting codes, not names (101 and 102 `<F022><F000>`, 103 `<F022><F00C>`). The menus read a name
inline as table[id] wherever they show one (lineups, results, HUD).

  1. Names: the renamed stock Toads (STOCK_RENAMES) replace theirs, and
     the table is extended to the highest new id with each new character's name at index = id. New ids
     0x66 / 0x67 land on the code entries 102 / 103, so those two codes move to the end of the table
     (CODE_102 / CODE_103 = max id + 1 / + 2) and the only readers of them are repointed:
     FUN_80486da0 (`lwz r0,0x198(r3)` x2) and FUN_8047c368 (`lwz r5,0x19c(r5)` x2).
     Each language's table is appended to dt_na.dat and the dir 121 records repointed (dir_ptrs).
  2. The name widgets FUN_80486da0, FUN_80489e60 and FUN_804922e8 take the name path only for
     0 <= id < 0x4D (0x4D..0x64 are Miis; anything else showed no name). Their `cmpwi rX,0x4d` goes to a
     stub that also sets "less than" for ids >= 0x66, so new characters take the name path.
"""
import struct

import dtna_toc
from ppc import Asm

NAME_DIR, NAME_FILE = 121, 5
# Stock ids with a name of their own. Empty since Extra Innings' Rosalina, Orange Toad, Larry and Luma became
# definitions (0x81-0x84, docs/stock-slot-migration.md): their names come from the definitions.
STOCK_NAMES = {}
# Stock characters renamed (Nick, 2026-09-25: the Toads are Super Mario Galaxy's Toad Brigade; only
# Captain Toad and Mailtoad are official names, the Brigade colours are the wiki's)
STOCK_RENAMES = {0x0D: "Captain Toad", 0x1D: "Brigade Blue", 0x1E: "Brigade Yellow", 0x1F: "Brigade Green",
                 0x20: "Mailtoad"}
FIRST_NEW, CODE_ENTRIES = 0x66, (102, 103)
CODE_READS = {102: ((0x80486E68, 0x80486E88), 0x80030198),     # lwz r0,0x198(r3)
              103: ((0x8047C4C0, 0x8047C4D8), 0x80A5019C)}     # lwz r5,0x19c(r5)
RANGE_TESTS = (0x80486EAC, 0x80489F94, 0x804923C0)            # cmpwi crN,rX,0x4d (then bge: no name)


def messages(table):
    """[raw UTF-16 bytes of each message, without its terminator]."""
    assert table[:2] == b"\1\1", "not a message table"
    n = struct.unpack_from(">H", table, 2)[0]
    offs = struct.unpack_from(f">{n}I", table, 4)
    text = 4 + 4 * n
    out = []
    for o in offs:
        p = start = text + 2 * o
        while table[p:p + 2] != b"\0\0":
            p += 2
        out.append(bytes(table[start:p]))
    return out


def build_table(msgs):
    offs, text = [], bytearray()
    for m in msgs:
        offs.append(len(text) // 2)
        text += m + b"\0\0"
    return b"\1\1" + struct.pack(f">H{len(msgs)}I", len(msgs), *offs) + bytes(text)


def names_table(table, names, max_id):
    """names: {id: name}. Returns the new table (entries 0..max_id + 2)."""
    msgs = messages(table)
    assert len(msgs) == 104 and msgs[CODE_ENTRIES[0]].decode("utf-16-be").startswith(""), \
        "unexpected name table"
    codes = [msgs[i] for i in CODE_ENTRIES]
    na = msgs[0x47]                                      # "#N/A"
    out = msgs[:101] + [msgs[101]] + [na] * (max_id - 101)
    for cid, name in names.items():
        out[cid] = name.encode("utf-16-be")
    return build_table(out + codes)


def _records(dol, data, ptr, n):
    if data.base <= ptr < data.here:                     # already moved into our data section
        return bytearray(data.blob[ptr - data.base:ptr - data.base + n])
    return bytearray(dol.read(ptr, n))


def add_names(dol, data, dir_ptrs, chars, dat, cursor, renames=None, by_language=None):
    """Step 1 (dt_na side). renames: {stock id: name} (default STOCK_RENAMES; charbuild adds the profile's);
    by_language: {language 0 en / 1 es / 2 fr: {id: name}} over the rest for that language only. Returns (log,
    [(dt_na offset, bytes)], cursor, max_id)."""
    max_id = max(c["id"] for c in chars)
    names = dict(STOCK_NAMES)
    names.update(stock_renames() if renames is None else renames)
    names.update({c["id"]: c["name"] for c in chars})
    by_language = by_language or {}
    n_files = len(dtna_toc.toc(dol)[NAME_DIR])
    recs = _records(dol, data, dir_ptrs[NAME_DIR], n_files * dtna_toc.FILE_RECORD)
    appended, placed = [], {}
    for lang in range(3):
        at = NAME_FILE * dtna_toc.FILE_RECORD + lang * 16
        _, length, off, _ = struct.unpack_from(">4I", recs, at)
        own = {**names, **by_language.get(lang, {})}
        key = (off, tuple(sorted(own.items())))            # languages sharing a table share it while their names agree
        if key not in placed:
            with open(dat, "rb") as fh:
                fh.seek(off)
                table = names_table(fh.read(length), own, max_id)
            appended.append((cursor, table))
            placed[key] = (cursor, len(table))
            cursor += len(table) + (-len(table) % 32)
        new_off, new_len = placed[key]
        struct.pack_into(">III", recs, at + 4, new_len, new_off, new_len)
    dir_ptrs[NAME_DIR] = data.put(bytes(recs), align=4)
    shown = ", ".join(f"0x{c:02X} {n}" for c, n in sorted(names.items()))
    return ([f"names        dir {NAME_DIR} file {NAME_FILE}: {len(placed)} tables, entries 0..0x{max_id + 2:X} "
             f"(codes 102/103 -> {max_id + 1}/{max_id + 2}): {shown}"], appended, cursor, max_id)


def patch_code(dol, code, max_id):
    """Steps 1 (code-entry readers) and 2 (name widgets)."""
    for k, (entry, (sites, stock)) in enumerate(CODE_READS.items()):
        new = max_id + 1 + k
        for site in sites:
            assert dol.u32(site) == stock, f"0x{site:08X}: {dol.u32(site):08X}"
            dol.w32(site, (stock & 0xFFFF0000) | (4 * new))
    for site in RANGE_TESTS:
        w = dol.u32(site)
        assert w >> 26 == 11 and w & 0xFFFF == 0x4D, f"0x{site:08X}: {w:08X}"
        cr, reg = (w >> 23) & 7, (w >> 16) & 31
        a = Asm(code.here)
        a.cmpwi(reg, 0x4D, cr=cr).blt("back", cr=cr)      # stock names
        a.cmpwi(reg, FIRST_NEW, cr=cr).blt("back_ge", cr=cr)
        a.cmpwi(reg, 0x7FFF, cr=cr).b("back")             # new ids: "less than" -> the name path
        a.label("back_ge")
        a.cmpwi(reg, 0x4D, cr=cr)                         # Miis / sentinel: stock result
        a.label("back")
        a.b(site + 4)
        dol.w32(site, Asm(site).b(code.put(a.assemble(), 4)).assemble_word())
    return [f"names        code entries 102/103 -> {max_id + 1}/{max_id + 2} ({sum(len(s) for s, _ in CODE_READS.values())} "
            f"reads); {len(RANGE_TESTS)} name widgets show ids >= 0x{FIRST_NEW:X}"]


# 3. Name images. The select screens' name labels (Member_local::CS2d_StatusName FUN_8006e580, the
#    batting-order bubble Order_local::CS2d_FukidasiStatusName FUN_8007f41c, and FUN_8042bb3c) are
#    not text: they draw resource row `id + 0x149` of the select-screen layout (dt_na dir 119 file 19),
#    a 115 x 16 white name on page 124 (CI4); 0x196 is "?". Rows past 0x196 belong to other art, so the
#    new characters' names are drawn onto one new RGB5A3 page (NAME_PAGE), id i at slot i - 0x66, with
#    rows NAME_ROW_BASE (the stock file's 483 rows) + slot; charbuild's stubs at those three sites use
#    `row = id - 0x66 + NAME_ROW_BASE` for ids >= 0x66 (they used to alias the id to the template's,
#    which showed the template's name).
NAME_ROW_BASE = 483
# Extra Innings' own name plates (rows id + 0x149 on page 124, drawn in the English copy only) are
# replaced by ours: these ids are drawn onto the same page (second column), and their stock rows
# repointed there in every language (the code is unchanged for ids < 0x66).
# Stock characters with our own plate (the renamed Toads; STOCK_NAMES is empty): drawn in the page's
# second column, their stock rows id + 0x149 repointed there.
EI_NAMES = {**STOCK_NAMES, **STOCK_RENAMES}
# the Toad Brigade's names (STOCK_RENAMES) and portraits are in this build: charbuild.build sets it from "toad-brigade",
# the window from its tick (Nick, git-92: the Characters Beta never shows Captain Toad, the Brigade or Mailtoad)
TOADS = True


def stock_renames():
    """Our stock renames in this build: STOCK_RENAMES with the Toad Brigade (TOADS), else none."""
    return dict(STOCK_RENAMES) if TOADS else {}
NAME_CELL = (115, 16)
# column 0: the new characters in id order (cells, not ids: an id with no character shares one blank cell); column 1:
# EI_NAMES, then the new characters past column 0 (name_cell). 512 -> 1024 tall for the 61 recolors that fill every
# stock color wheel; 123 cells (122 characters and the blank) fit, at any ids up to charbuild.MAX_ID
NAME_PAGE = (256, 1024)
# The card names are drawn on the player's PC at patch time, so the font is one we ship (scripts/fonts, with its OFL
# licence; package.py ships the folder): Open Sans at weight 800 (ExtraBold), the closest open font to the stock
# names (their cap tops and baselines line up at NAME_DY -2). It was Arial Bold, Monotype's, from C:/Windows/Fonts.
NAME_FONT = __file__.replace("char_names.py", "fonts/OpenSans[wdth,wght].ttf")
NAME_WEIGHT, NAME_SIZE, NAME_DY = 800, 14, -2


def name_font(size):
    """The card names' font at a size (charpack's fit check uses it too)."""
    from PIL import ImageFont
    font = ImageFont.truetype(NAME_FONT, size)
    font.set_variation_by_axes([NAME_WEIGHT, 100])      # weight, width 100 (normal)
    return font
GX_RGB5A3, GX_CI8, GX_TL_IA8 = 5, 9, 0




def name_image(text):
    from PIL import Image, ImageDraw, ImageFont
    img = Image.new("RGBA", NAME_CELL, (255, 255, 255, 0))
    draw = ImageDraw.Draw(img)
    size = NAME_SIZE
    while size > 9 and draw.textbbox((0, 0), text, font=name_font(size))[2] > NAME_CELL[0] - 2:
        size -= 1                                        # shrink long names to fit the label
    font = name_font(size)
    x0, _, x1, _ = draw.textbbox((0, 0), text, font=font)
    draw.text(((NAME_CELL[0] - (x1 - x0)) // 2 - x0, NAME_DY + (NAME_SIZE - size) // 2), text, font=font,
              fill=(255, 255, 255, 255))
    return img


def name_cell(slot, n_renamed=None):
    """A name cell (add_name_art: the new characters in id order, then the blank) -> its top-left on NAME_PAGE:
    column 0 top to bottom, then column 1 below the renamed stock characters' plates (n_renamed; default
    len(EI_NAMES))."""
    per_col = NAME_PAGE[1] // NAME_CELL[1]
    if slot < per_col:
        return 0, slot * NAME_CELL[1]
    return NAME_PAGE[0] // 2, ((len(EI_NAMES) if n_renamed is None else n_renamed) + slot - per_col) * NAME_CELL[1]


def add_name_art(data, chars, renames=None):
    """One language's dir 119 file 19 -> with the name page, rows NAME_ROW_BASE + (id - 0x66) for the new
    characters, EI_NAMES' name rows repointed to our drawings, and the ability-label page (Clamber
    Jump's row repointed, a row per abilities.NEW, the label widgets recoloured). renames: {stock id: name}
    (default STOCK_RENAMES) drawn over those stock characters' plates."""
    ei_names = {**STOCK_NAMES, **(stock_renames() if renames is None else renames)}
    from PIL import Image
    import layout
    from captain_art import rgb5a3
    lay = layout.Layout(data)
    assert len(lay.rows) == NAME_ROW_BASE, f"select layout has {len(lay.rows)} rows, expected {NAME_ROW_BASE}"
    w, h = NAME_PAGE
    slots = max(c["id"] for c in chars) - FIRST_NEW + 1                   # rows: one per id 0x66 .. the highest
    cell = {cid: k for k, cid in enumerate(sorted(c["id"] for c in chars))}   # cells: one per character
    blank = len(cell)                                                     # and one blank for the ids between
    per_col = h // NAME_CELL[1]
    import abilities
    assert blank + 1 + len(ei_names) <= 2 * per_col, "name page full"
    page_img = Image.new("RGBA", NAME_PAGE, (255, 255, 255, 0))
    for c in chars:
        page_img.paste(name_image(c["name"]), name_cell(cell[c["id"]], len(ei_names)))
    ei = sorted(ei_names.items())
    for k, (_, name) in enumerate(ei):
        page_img.paste(name_image(name), (w // 2, k * NAME_CELL[1]))
    page = lay.add_texture(rgb5a3(page_img), w, h, GX_RGB5A3, template_page=124)
    for k in range(slots):
        x, y = name_cell(cell.get(FIRST_NEW + k, blank), len(ei_names))
        lay.add_row(page, x / w, y / h, (x + NAME_CELL[0]) / w, (y + NAME_CELL[1]) / h)
    for k, (cid, _) in enumerate(ei):
        y = k * NAME_CELL[1]
        lay.rows[0x149 + cid][:] = struct.pack(">HH4f", page, 0, y / h, (w // 2) / w, (y + NAME_CELL[1]) / h,
                                               (w // 2 + NAME_CELL[0]) / w)
    # Ability labels (ABILITY_LABELS, then abilities.NEW): their own CI8 page with an IA8 palette (the stock
    # labels' format), one row per 16 lines; the label widgets are recoloured to show texel colours
    # (abilities.recolour_labels), so these labels are black text, the stock labels unchanged.
    abilities.recolour_labels(lay)
    new_abilities = sorted(abilities.NEW)
    labels = [abilities.label_image(ABILITY_LABELS[r]) for r in sorted(ABILITY_LABELS)]   # stock glyphs (bold)
    labels += [abilities.label_image(abilities.NEW[a], a in abilities.STAR) for a in new_abilities]
    image, palette, lw, lh = abilities.label_page(labels)
    label_page = lay.add_texture(image, lw, lh, GX_CI8, template_page=abilities.LABEL_PAGE, palette=palette,
                                 palette_format=GX_TL_IA8)

    def cell(k):
        y = 16 * k
        return 0, y / lh, abilities.CELL[0] / lw, (y + abilities.CELL[1]) / lh
    rows = abilities.label_rows(FIRST_NEW + slots - 1)
    for k, a in enumerate(new_abilities, len(ABILITY_LABELS)):   # rows right after the name rows (label_rows)
        assert len(lay.rows) == rows[a], f"ability {a}: row {len(lay.rows)}, expected {rows[a]}"
        u1, v1, u2, v2 = cell(k)
        lay.add_row(label_page, u1, v1, u2, v2)
    for k, row in enumerate(sorted(ABILITY_LABELS)):
        u1, v1, u2, v2 = cell(k)
        lay.rows[row][:] = struct.pack(">HH4f", label_page, 0, v1, u1, v2, u2)
    return lay.to_bytes()


# 4. Renamed ability (Nick, 2026-09-25): "Clamber" -> "Clamber Jump" everywhere it shows.
#    a. The ability label is an image, row 0x1B7 of dir 119 file 19 (112 x 15, text left-aligned at
#       x 21 on page 125, like the other fielding abilities 0x1AF..0x1C1): abilities.label_image, the stock
#       labels' own glyphs (J cut from Super Jump; it was Arial Bold, thin next to the stock labels, Nick),
#       goes on the ability-label page and the row is repointed (add_name_art). The widget's glove icon is
#       drawn over x 0-18 as before. Captain select (file 18) gets the same art: star_move_labels
#       (captain fielding slot 9). Challenge mode (file 12): patch_challenge_layout below.
#    b. The text: dt_na message tables (TEXT_FILES, every language) have "clamber" in Baby Mario's
#       description and the "Select a character who can clamber." prompt; every occurrence becomes
#       "clamber jump", case kept, in the message's own encoding (full-width or plain).
# Since 2026-09-26 Clamber Jump is its own fielding ability (abilities.CLAMBER_JUMP, 14; Nick: either one per
# character), so stock Clamber keeps its label and the text its word: nothing is renamed (the machinery stays, empty).
ABILITY_LABELS = {}
TEXT_RENAMES = ()
TEXT_FILES = ((121, 0), (121, 4), (146, 0))


# 4c. Challenge mode draws its own labels (dir 119 file 12, FUN_801C0014; the u16 fielding list at 0x80650E90,
#     slot 9 = row 0x1BF, 200 x 27 on page 141: CI4, 16 IA8 levels of white, alpha 0x11 * index, the same in all
#     three languages). The stock characters with Clamber (DK, Diddy, Dixie, Funky, Baby DK) show there, and its
#     prompt says "clamber jump" (4b). The label is stock pixels: the English "Clamber" (row 0x1BF) and the
#     "Jump" of Super Jump (row 0x1B7, x 84-148, after its 7-column word gap), painted over row 0x1BF's cell in
#     every language's copy (the other rows and pages unchanged; nothing else draws from that cell).
CHALLENGE_FILE, CHALLENGE_PAGE, CHALLENGE_LIST = 12, 141, 0x80650E90
CHALLENGE_CLAMBER, CHALLENGE_SUPER_JUMP = 0x1BF, 0x1B7
CHALLENGE_JUMP, CHALLENGE_GAP = (84, 149), 7            # "Jump" columns in Super Jump's cell; its word gap
CHALLENGE_PAL = tuple(0x11 * i << 8 | 0xFF for i in range(16))


def _challenge_cell(lay, row):
    """(image offset in lay.data, page width, height, (x0, y0, x1, y1)) of a file-12 row on CHALLENGE_PAGE (checked)."""
    page, _, v1, u1, v2, u2 = struct.unpack(">HH4f", lay.rows[row])
    assert page == CHALLENGE_PAGE, f"file 12 row 0x{row:X} is on page {page}, not {CHALLENGE_PAGE}"
    desc = lay.descs[page]
    import layout
    io, po, h, w = struct.unpack_from(">IIHH", desc, 0)
    assert desc[0x17] == 8 and desc[0x1A] == 0 and struct.unpack_from(">H", desc, 0x18)[0] == 16, "page 141 format"
    pal = po + layout.TEX_BASE - lay.data_start
    assert struct.unpack_from(">16H", lay.data, pal) == CHALLENGE_PAL, "page 141 palette"
    return io + layout.TEX_BASE - lay.data_start, w, h, (round(u1 * w), round(v1 * h), round(u2 * w), round(v2 * h))


def _challenge_grid(lay, row, cols=None):
    from star_move_labels import _px
    off, w, h, (x0, y0, x1, y1) = _challenge_cell(lay, row)
    img = bytes(lay.data[off:off + w * h // 2])
    xs = range(x0, x1) if cols is None else range(x0 + cols[0], x0 + cols[1])
    return [[_px(img, w, x, y) for x in xs] for y in range(y0, y1)]


def challenge_grid(english):
    """Challenge mode's "Clamber Jump" (page-141 indices, row 0x1BF's cell) from the English dir 119 file 12."""
    import layout
    lay = layout.Layout(english)
    out = _challenge_grid(lay, CHALLENGE_CLAMBER)
    ink = [x for x in range(len(out[0])) if any(line[x] for line in out)]
    jump = _challenge_grid(lay, CHALLENGE_SUPER_JUMP, CHALLENGE_JUMP)
    at = ink[-1] + 1 + CHALLENGE_GAP
    assert at + len(jump[0]) <= len(out[0]) and len(jump) == len(out), "Clamber Jump does not fit the cell"
    for y, line in enumerate(jump):
        out[y][at:at + len(line)] = line
    return out


CHALLENGE_SLOT = 14                                     # abilities.CLAMBER_JUMP: list slot (13-15 are 0 padding)


def challenge_layout_bytes(data, grid, rows_out, row=None):
    """One language's dir 119 file 12 with grid (challenge_grid) on a page of its own (CI4, page 141's palette) and a
    row for it (rows_out gets its number). Row 0x1BF (Clamber) and every other row stay as they are. row: the number
    it must have (the one list slot serves every language, and the stock copies have different row counts: 476, 476,
    477); blank filler rows (the page's empty bottom) come first up to it. None: the next row."""
    import layout
    from name_telop import tile_ci4
    lay = layout.Layout(data)
    _challenge_cell(lay, CHALLENGE_CLAMBER)                             # (checks page 141's format and palette)
    gw, gh = len(grid[0]), len(grid)
    w, h = gw + (-gw % 8), gh + (-gh % 8)
    idx = bytearray(w * h)
    for y, line in enumerate(grid):
        idx[y * w:y * w + gw] = bytes(line)
    pal_at, n = lay.palette(CHALLENGE_PAGE)
    page = lay.add_texture(tile_ci4(idx, w, h), w, h, 8, template_page=CHALLENGE_PAGE,
                           palette=bytes(lay.data[pal_at:pal_at + 2 * n]), palette_format=0)
    row = len(lay.rows) if row is None else row
    assert row >= len(lay.rows), f"file 12 has {len(lay.rows)} rows, past {row}"
    assert h - gh >= 1, "no blank line for the filler rows"
    while len(lay.rows) < row:
        lay.add_row(page, 0.0, gh / h, 8 / w, 1.0)                     # blank (never shown: no slot points here)
    rows_out.append(lay.add_row(page, 0.0, 0.0, gw / w, gh / h))
    return lay.to_bytes()


def patch_challenge_layout(dol, dat_path):
    """Challenge mode's "Clamber Jump" (fielding ability 14) in every language's copy of dir 119 file 12 (appended to
    dt_na.dat, records repointed, as captains.patch_layouts does): its own row, list slot CHALLENGE_SLOT (padding)."""
    import os
    assert struct.unpack(">H", dol.read(CHALLENGE_LIST + 2 * 9, 2))[0] == CHALLENGE_CLAMBER, "challenge list slot 9"
    assert dol.read(CHALLENGE_LIST + 2 * CHALLENGE_SLOT, 2) == b"\0\0", f"challenge list slot {CHALLENGE_SLOT} is used"
    rows = []
    rec = dtna_toc.dir_pointers(dol)[119] + CHALLENGE_FILE * dtna_toc.FILE_RECORD
    w = list(struct.unpack(">12I", dol.read(rec, 48)))
    placed = {}
    with open(dat_path, "r+b") as f:
        f.seek(w[2])
        grid = challenge_grid(f.read(w[1]))
        import layout
        counts = []                                                     # the copies' row counts: the new row goes
        for lang in range(3):                                           # after the longest, the same in each
            f.seek(w[2 + 4 * lang])
            counts.append(len(layout.Layout(f.read(w[1 + 4 * lang])).rows))
        for lang in range(3):
            off, length = w[2 + 4 * lang], w[1 + 4 * lang]
            if off not in placed:
                f.seek(off)
                new = challenge_layout_bytes(f.read(length), grid, rows, max(counts))
                end = os.path.getsize(dat_path)
                at = end + (-end % 32)
                f.seek(at)
                f.write(new)
                placed[off] = (at, len(new))
            at, n = placed[off]
            w[1 + 4 * lang], w[2 + 4 * lang], w[3 + 4 * lang] = n, at, n
    dol.write(rec, struct.pack(">12I", *w))
    assert len(set(rows)) == 1, f"file 12 copies disagree on the row: {rows}"
    dol.write(CHALLENGE_LIST + 2 * CHALLENGE_SLOT, struct.pack(">H", rows[0]))
    return [f"clamber jump challenge mode label: dir 119 file 12 row 0x{rows[0]:X}, list slot {CHALLENGE_SLOT} "
            f"({len(placed)} copies appended; Clamber's row 0x{CHALLENGE_CLAMBER:X} stock)"]


def _units(raw):
    return list(struct.unpack(f">{len(raw) // 2}H", raw))


def rename_in_message(raw, old, new):
    """Replace old with new (case-insensitive; a capitalised match gets title case, an all-caps one
    upper case; full-width style kept)."""
    units = _units(raw)
    plain = "".join(chr(u - 0xFEE0) if 0xFF01 <= u <= 0xFF5E else (chr(u) if u < 0xE000 else "\0") for u in units)
    out, i, low = [], 0, plain.lower()
    while True:
        j = low.find(old, i)
        if j < 0:
            out += units[i:]
            break
        out += units[i:j]
        wide = 0xFF01 <= units[j] <= 0xFF5E
        text = new.title() if plain[j].isupper() else new       # "Clamber" -> "Clamber Jump"
        if text[len(old):] and plain[j + 1:j + len(old)].isupper():
            text = text.upper()
        out += [ord(c) + 0xFEE0 if wide and "!" <= c <= "~" else ord(c) for c in text]
        i = j + len(old)
    return struct.pack(f">{len(out)}H", *out)


def rename_text(dol, data, dir_ptrs, dat, cursor, pending):
    """Step 4b. pending: charbuild's [(dt_na offset, bytes)] not yet written (files other steps moved).
    Returns (log, [(dt_na offset, bytes)], cursor)."""
    def read(off, length):
        for at, blob in pending:
            if at <= off < at + len(blob):
                return blob[off - at:off - at + length]
        with open(dat, "rb") as fh:
            fh.seek(off)
            return fh.read(length)
    toc = dtna_toc.toc(dol)
    appended, log, changed = [], [], 0
    for d in sorted({d for d, _ in TEXT_FILES}):
        recs = _records(dol, data, dir_ptrs[d], len(toc[d]) * dtna_toc.FILE_RECORD)
        placed = {}
        for f in (f for dd, f in TEXT_FILES if dd == d):
            for lang in range(3):
                at = f * dtna_toc.FILE_RECORD + lang * 16
                _, length, off, _ = struct.unpack_from(">4I", recs, at)
                if off not in placed:
                    msgs = messages(read(off, length))
                    new = []
                    for m in msgs:
                        for old, rep in TEXT_RENAMES:
                            m2 = rename_in_message(m, old, rep)
                            changed += m2 != m
                            m = m2
                        new.append(m)
                    if new == msgs:
                        placed[off] = (off, length)
                    else:
                        table = build_table(new)
                        appended.append((cursor, table))
                        placed[off] = (cursor, len(table))
                        cursor += len(table) + (-len(table) % 32)
                new_off, new_len = placed[off]
                struct.pack_into(">III", recs, at + 4, new_len, new_off, new_len)
        dir_ptrs[d] = data.put(bytes(recs), align=4)
    log.append(f"text renames {', '.join(f'{o!r} -> {n!r}' for o, n in TEXT_RENAMES)}: {changed} messages "
               f"(dt_na {', '.join(f'{d}/{f}' for d, f in TEXT_FILES)}, every language)")
    return log, appended, cursor
