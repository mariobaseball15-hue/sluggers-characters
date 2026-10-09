"""New characters' names in the name banner (the "name telop"): the pitching-change banner shows the new pitcher's
name, as it does for stock characters.

The banner is Gm2d_Bb_local::CS2d_NameTelop_Name (FUN_80311fbc, made by Gm2d vt+0x60 = FUN_80316a00 from event 0xC's
script op 0x25A). It reads the player's id and draws, for
  - ids 0..0x4C: name art, FUN_80395fe4(id), which draws element 0x1A of dt_na dir 119 file 1 with key ref
    `id + 0x18`: a 230 x 32 chrome italic name (page 0.., CI4 with a 16-entry IA8 palette);
  - ids 0x4D..0x64 (Miis): the Mii's name as text;
  - anything else: nothing. So every new character's pitching change had no name (Nick, 2026-09-26).
FUN_80395fe4 is also called by FUN_801bfc64, FUN_801c4604 and FUN_80328888; they get the new names the same way.

  1. Art: each new character's name drawn in the stock style (Orbitron, OFL, scripts/fonts: heavy, extended,
     italic, chrome fill, black outline and drop shadow), quantized to the stock page's own palette (6 black alpha
     levels, 10 opaque greys). File 1 stays resident in a match (the MEM2 heap ran out at a rival VS at-bat: git-95,
     crash 0x80597944), so the names take as little as they can (git-a7): first the free 230 x 32 places of the stock
     names' own CI4 atlas (page 0's image, shared by pages 0-14: every pixel no row covers is index 0; 21 places),
     at no cost, then a CI4 page of file 1 PAGE_W wide and only as tall as the rest need (4 columns of 32-px rows;
     none when they all fit). The banner is the same (same cells, same palette). Rows ROW_BASE + (id - 0x66),
     ROW_BASE = the file's row count when the step runs (after captains' file 1 rows); an id with no character
     points at blank pixels. The renamed
     stock characters (char_names.STOCK_RENAMES: Captain Toad, the Toad Brigade, Mailtoad) get their new names
     there too, their stock rows repointed (the stock art said Red Toad, Blue Toad...).
  2. Code: the two `cmpwi rX,0x4d` range tests (the banner's, 0x803120A0, and FUN_80395fe4's, 0x80396018) set "less
     than" for ids >= 0x66 (char_names' name-widget stub), and FUN_80395fe4's `addi r0,r24,0x18` (0x80396060) uses
     `id - 0x66 + ROW_BASE` for them.
"""
import struct

import dtna_toc
from ppc import Asm

DIR, FILE = 119, 1
FIRST_NEW = 0x66
RANGE_TESTS = (0x803120A0, 0x80396018)            # cmpwi r31,0x4d (banner) / cmpwi r4,0x4d (FUN_80395fe4), then bge
ROW_ADD, ROW_ADD_WORD = 0x80396060, 0x38180018   # addi r0,r24,0x18
STOCK_ROW = 0x18                                  # stock id i: row i + 0x18
STOCK_PAGE = 0                                    # the stock names' page (its palette is reused)
CELL, PAGE_W, COLS = (230, 32), 1024, 4
ATLAS_STEP = (2, 8)                               # the free-place scan: x, y steps in the stock atlas
FONT = __file__.replace("name_telop.py", "fonts/Orbitron[wght].ttf")
WEIGHT, SHEAR, WIDEN, CAP = 900, 0.3, 1.18, 20   # the stock face: heavy, italic, extended, ~20 px capitals
K = 4                                             # drawn at 4x, then reduced
PAL_ALPHA = (0x00, 0x2E, 0x5C, 0x87, 0xBF, 0xE1)                           # entries 0-5: black, these alphas
PAL_GREY = (0x02, 0x3B, 0x7E, 0xAB, 0xBD, 0xCB, 0xDB, 0xE8, 0xF4, 0xFD)     # entries 6-15: opaque greys
GX_CI4, TL_IA8 = 8, 0


def _glyphs(text, size, widen):
    from PIL import Image, ImageDraw, ImageFont
    font = ImageFont.truetype(FONT, size)
    font.set_variation_by_axes([WEIGHT])
    x0, y0, x1, y1 = ImageDraw.Draw(Image.new("L", (1, 1))).textbbox((0, 0), text, font=font)
    m = Image.new("L", (x1 - x0 + 8 * K, y1 - y0 + 8 * K))
    ImageDraw.Draw(m).text((4 * K - x0, 4 * K - y0), text, font=font, fill=255)
    m = m.resize((max(1, int(m.width * widen)), m.height), Image.LANCZOS)
    w, h = m.size
    return m.transform((w + int(h * SHEAR), h), Image.AFFINE, (1, SHEAR, -h * SHEAR, 0, 1, 0), Image.BICUBIC)


def name_image(text):
    """A CELL-sized "LA" image: the name centred, in the stock banner style; long names are condensed to fit."""
    from PIL import Image, ImageChops, ImageFilter
    w, h = CELL[0] * K, CELL[1] * K
    size = int(CAP * K * 1.28)
    m = _glyphs(text, size, WIDEN)
    if m.width > w - 6 * K:
        m = _glyphs(text, size, WIDEN * (w - 6 * K) / m.width)
    ox, oy = (w - m.width) // 2, (h - m.height) // 2
    glyph = Image.new("L", (w, h))
    glyph.paste(m, (ox, oy))
    outline = glyph.filter(ImageFilter.MaxFilter(2 * int(1.25 * K) + 1))
    shadow = ImageChops.offset(outline, 2 * K, 2 * K)
    top, bottom = oy + 4 * K, oy + m.height - 4 * K
    ramp = Image.new("L", (1, h))
    for y in range(h):                            # chrome: bright top, a grey band below the middle, bright bottom
        t = min(1.0, max(0.0, (y - top) / max(1, bottom - top)))
        ramp.putpixel((0, y), int(253 - 40 * t / 0.42 if t < 0.42 else 150 if t < 0.55 else
                                  245 - 60 * (t - 0.55) / 0.45))
    fill = Image.merge("LA", (ramp.resize((w, h)), Image.new("L", (w, h), 255)))
    black = Image.new("LA", (w, h), (0, 255))
    out = Image.composite(black, Image.new("LA", (w, h), (0, 0)), shadow.point(lambda v: int(v * 0.7)))
    out = Image.composite(black, out, outline)
    out = Image.composite(fill, out, glyph.filter(ImageFilter.MinFilter(3)))
    return out.resize(CELL, Image.LANCZOS)


def _index(l, a):
    if a < 0xF0:
        return min(range(6), key=lambda i: abs(PAL_ALPHA[i] - a))
    return 6 + min(range(10), key=lambda i: abs(PAL_GREY[i] - l))


def cell_indices(img):
    """A CELL-sized LA image -> its palette indices (row-major bytes)."""
    return bytes(_index(l, a) for l, a in img.getdata())


def page_ci4(cells, size):
    """{(x, y): CELL indices} -> a CI4 image of `size` (8x8 tiles, high nibble first)."""
    w, h = size
    idx = bytearray(w * h)
    for (x0, y0), cell in cells.items():
        for y in range(CELL[1]):
            idx[(y0 + y) * w + x0:(y0 + y) * w + x0 + CELL[0]] = cell[y * CELL[0]:(y + 1) * CELL[0]]
    return tile_ci4(idx, w, h)


def tile_ci4(idx, w, h):
    out = bytearray()
    for ty in range(0, h, 8):
        for tx in range(0, w, 8):
            for y in range(ty, ty + 8):
                r = y * w + tx
                out += bytes(idx[r + x] << 4 | idx[r + x + 1] for x in range(0, 8, 2))
    return bytes(out)


def name_cell(slot):
    """Place `slot` on the names page: COLS across, then down."""
    return (slot % COLS) * CELL[0], (slot // COLS) * CELL[1]


def page_height(n):
    return -(-n // COLS) * CELL[1]


def _atlas(lay):
    """The stock names' CI4 image: (its pages, offset in lay.data, width, height)."""
    from layout import TEX_BASE
    img = struct.unpack_from(">I", lay.descs[STOCK_PAGE], 0)[0]
    h, w = struct.unpack_from(">HH", lay.descs[STOCK_PAGE], 8)
    assert lay.descs[STOCK_PAGE][0x17] == GX_CI4
    pages = [p for p, d in enumerate(lay.descs) if struct.unpack_from(">I", d, 0)[0] == img and d[0x17] == GX_CI4]
    return pages, TEX_BASE + img - lay.data_start, w, h


def atlas_used(lay):
    """numpy bool (h, w): the stock names' atlas pixels any row on its pages covers, 1 px around."""
    import numpy as np
    pages, _, w, h = _atlas(lay)
    used = np.zeros((h, w), bool)
    for row in lay.rows:
        page, _, v1, u1, v2, u2 = struct.unpack(">HH4f", row)
        if page in pages:
            x0, x1 = sorted((round(u1 * w), round(u2 * w)))
            y0, y1 = sorted((round(v1 * h), round(v2 * h)))
            used[max(0, y0 - 1):y1 + 1, max(0, x0 - 1):x1 + 1] = True
    return used


def free_places(lay, n=None):
    """Up to n free CELL places (x, y) in the stock names' atlas, scanned top to bottom, left to right."""
    import numpy as np
    used = atlas_used(lay)
    h, w = used.shape
    ii = np.pad(used.astype(np.int32).cumsum(0).cumsum(1), ((1, 0), (1, 0)))
    cw, ch = CELL
    out = []
    for y in range(0, h - ch + 1, ATLAS_STEP[1]):
        x = 0
        while x + cw <= w and (n is None or len(out) < n):
            if ii[y + ch, x + cw] - ii[y, x + cw] - ii[y + ch, x] + ii[y, x] == 0:
                out.append((x, y))
                used[y:y + ch, x:x + cw] = True
                ii = np.pad(used.astype(np.int32).cumsum(0).cumsum(1), ((1, 0), (1, 0)))
                x += cw
            else:
                x += ATLAS_STEP[0]
    return out


def _atlas_put(lay, x0, y0, cell):
    """Write a cell's indices into the stock atlas (CI4 tiles) at (x0, y0); the place must be blank."""
    _, at, w, _ = _atlas(lay)
    for y in range(CELL[1]):
        for x in range(CELL[0]):
            px, py = x0 + x, y0 + y
            o = at + ((py // 8) * (w // 8) + px // 8) * 32 + (py % 8) * 4 + (px % 8) // 2
            v = cell[y * CELL[0] + x]
            if px % 2 == 0:
                assert lay.data[o] >> 4 == 0, f"atlas ({px}, {py}) isn't blank"
                lay.data[o] = (lay.data[o] & 0x0F) | v << 4
            else:
                assert lay.data[o] & 0x0F == 0, f"atlas ({px}, {py}) isn't blank"
                lay.data[o] = (lay.data[o] & 0xF0) | v


def _blank_uv(lay):
    """uv of an 8 x 8 block of the stock atlas no row covers (all index 0: transparent)."""
    import numpy as np
    used = atlas_used(lay)
    h, w = used.shape
    for y in range(0, h - 8, 8):
        for x in range(0, w - 8, 8):
            if not used[y:y + 8, x:x + 8].any():
                return (x + 1) / w, (y + 1) / h, (x + 7) / w, (y + 7) / h
    raise AssertionError("no blank block in the stock names' atlas")


def add_art_bytes(data, chars, rows_out, renames=None):
    """One language's dir 119 file 1 -> with the names page: rows ROW_BASE + (id - 0x66) for the new ids, and the
    renamed stock characters' rows (id + 0x18) repointed to their new names (cells after the new ids').
    rows_out gets ROW_BASE."""
    import char_names, layout
    lay = layout.Layout(data)
    slots = max(c["id"] for c in chars) - FIRST_NEW + 1
    renames = sorted((char_names.stock_renames() if renames is None else renames).items())
    pal_at, n = lay.palette(STOCK_PAGE)
    assert n == 16, f"file 1 page {STOCK_PAGE}: {n} palette entries"
    names = [(c["id"], c["name"]) for c in sorted(chars, key=lambda c: c["id"])] + renames   # new ids, then renames
    blank = _blank_uv(lay)
    _, _, aw, ah = _atlas(lay)
    places = free_places(lay, len(names))                  # the stock atlas first: no bytes
    where = {}                                             # name index -> (page, uv)
    for k, (x, y) in enumerate(places):
        _atlas_put(lay, x, y, cell_indices(name_image(names[k][1])))
        where[k] = (STOCK_PAGE, ((x + 1) / aw, (y + 1) / ah, (x + CELL[0] - 1) / aw, (y + CELL[1] - 1) / ah))
    rest = list(range(len(places), len(names)))
    if rest:                                               # the others: a page as tall as they need
        size = (PAGE_W, page_height(len(rest)))
        cells = {name_cell(j): cell_indices(name_image(names[k][1])) for j, k in enumerate(rest)}
        page = lay.add_texture(page_ci4(cells, size), *size, GX_CI4, template_page=STOCK_PAGE,
                               palette=bytes(lay.data[pal_at:pal_at + 32]), palette_format=TL_IA8)
        for j, k in enumerate(rest):
            x, y = name_cell(j)
            where[k] = (page, ((x + 1) / size[0], (y + 1) / size[1], (x + CELL[0] - 1) / size[0],
                               (y + CELL[1] - 1) / size[1]))
    by_id = {cid: where[k] for k, (cid, _) in enumerate(names[:len(names) - len(renames)])}
    base = len(lay.rows)
    for k in range(slots):
        page, uv = by_id.get(FIRST_NEW + k, (STOCK_PAGE, blank))   # an id with no character: blank
        lay.add_row(page, *uv)
    for k, (cid, _) in enumerate(renames):
        page, (u1, v1, u2, v2) = where[len(names) - len(renames) + k]
        lay.rows[STOCK_ROW + cid][:] = struct.pack(">HH4f", page, 0, v1, u1, v2, u2)
    rows_out.append(base)
    return lay.to_bytes()


def patch_code(dol, code):
    """Step 2, before charbuild commits the code: the range tests and the row stub. The stub's new-id `addi` is a
    placeholder (returned) that set_rows fills in once the art has its rows."""
    for site in RANGE_TESTS:
        w = dol.u32(site)
        assert w >> 26 == 11 and w & 0xFFFF == 0x4D, f"0x{site:08X}: {w:08X}"
        cr, reg = (w >> 23) & 7, (w >> 16) & 31
        a = Asm(code.here)
        a.cmpwi(reg, 0x4D, cr=cr).blt("back", cr=cr)      # stock names
        a.cmpwi(reg, FIRST_NEW, cr=cr).blt("back_ge", cr=cr)
        a.cmpwi(reg, 0x7FFF, cr=cr).b("back")             # new ids: "less than" -> the name art
        a.label("back_ge")
        a.cmpwi(reg, 0x4D, cr=cr)                         # Miis / none: the stock result
        a.label("back")
        a.b(site + 4)
        dol.w32(site, Asm(site).b(code.put(a.assemble(), 4)).assemble_word())
    assert dol.u32(ROW_ADD) == ROW_ADD_WORD, f"0x{ROW_ADD:08X}: {dol.u32(ROW_ADD):08X}"
    at = code.here + (-len(code.blob) % 4)
    a = Asm(at)
    a.cmpwi("r24", FIRST_NEW).blt("stock")
    a.label("new")
    a.word(ROW_ADD_WORD).b(ROW_ADD + 4)                   # -> addi r0,r24,ROW_BASE - 0x66 (set_rows)
    a.label("stock")
    a.word(ROW_ADD_WORD).b(ROW_ADD + 4)
    assert code.put(a.assemble(), 4) == at
    dol.w32(ROW_ADD, Asm(ROW_ADD).b(at).assemble_word())
    return at + 8


def add_art(dol, dat_path, chars, renames=None):
    """Step 1, in the output stage after any other file-1 step: every language's file 1. -> (log, ROW_BASE)."""
    bases = []
    n = dtna_toc.rebuild_file(dol, dat_path, DIR, FILE, lambda data: add_art_bytes(data, chars, bases, renames))
    assert len(set(bases)) == 1, f"file 1 copies disagree on the row count: {bases}"
    top = bases[0] + max(c["id"] for c in chars) - FIRST_NEW
    return [f"name telop: {len(chars)} names, dir {DIR} file {FILE} rows {bases[0]}..{top} ({n} copies appended); "
            f"the banner and FUN_80395fe4 show ids >= 0x{FIRST_NEW:X}"], bases[0]


def set_rows(dol, placeholder, base):
    assert dol.u32(placeholder) == ROW_ADD_WORD, f"0x{placeholder:08X}: {dol.u32(placeholder):08X}"
    dol.w32(placeholder, Asm(placeholder).addi("r0", "r24", base - FIRST_NEW).assemble_word())
