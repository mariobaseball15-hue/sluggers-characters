"""The character icon bank (dt_na dir 119 file 2) the icon steps build on, made from the player's own game.

charbuild's icon steps (extend_icon_bank, add_icon_art, lossless_icon_pages) were written against Extra Innings'
bank: the clean bank plus two private CMPR pages and a relocated set of source tables. The players of our patcher
don't have Extra Innings, so base_bank() makes the same layout from the clean bank, with our own blank pages and
no Extra Innings art (git-e2, for the patcher; replaces ei_characters.icon_bank()):

- Header +4 (end of the texture section) 0x93680 -> 0x113C80, so the container (the descriptor at ICON_DESCRIPTOR
  0x113C94) lands where charbuild expects it. Header +0x20 page count 0x92 -> 0x94.
- Page descriptors 0x92 (side) and 0x93 (front) at 0x1264 / 0x1284: CMPR 1024 x 256, images at texture-relative
  0x93880 / 0xD3A80 (ICON_PRIVATE_IMAGES), fully transparent (CMPR blocks 0000 0000 FFFFFFFF: colour 0 <= colour 1
  is the 3-colour mode, index 3 transparent). add_icon_art takes only transparent slots as free; zeros are opaque
  black and pushed every icon onto new rows. The descriptors run over page 0x86's palette (0x1280), as
  Extra Innings' do; lossless_icon_pages gives 0x86 a clean copy (OVERLAPPED_PALETTES).
- The three source tables (normal_a, side, front) move into the free rows of the texture section at 0x87520, back
  to back, with zeros after them for extend_icon_bank to grow into. Side and front gain keys for ids 0x47-0x4C
  (resource rows 152-157 and 158-163, slots 0-5 of the private pages); that's where STOCK_ICONS' 0x47 / 0x4C are
  redrawn in place. 0x48-0x4B show blank slots, and nothing on the clean base selects them.
- 14 resource rows appended (152-165: pages 0x92 then 0x93, slots 0-5, then slot 6 of each).

Everything else (every atlas pixel, the other rows and keys) is the clean bank's, so Extra Innings' stray strips
in the shared atlases (charbuild DAMAGED_TILES) are simply not there.
"""
import struct
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
import dtna_toc                     # noqa: E402
import game_source                  # noqa: E402
from dol import Dol                 # noqa: E402

ICON_DIR, ICON_FILE = 119, 2
CLEAN_TEX_END, TEX_END = 0x93680, 0x113C80
CONTAINER_HEAD = 0x14               # container header before the descriptor
TEX_BASE = 0x20                     # page image offsets count from here
PAGES = {0x92: 0x93880, 0x93: 0xD3A80}          # page -> texture-relative image offset
PAGE_W, PAGE_H = 1024, 256
CLEAR_BLOCK = bytes.fromhex("00000000ffffffff")    # one CMPR 4x4 block, all transparent
TABLES_AT = 0x87520                 # the relocated source tables (free atlas rows up to CLEAN_TEX_END)
SRC_HEADER, SRC_RECORD = 0x28, 0x50
RES_ROW = 0x14
NEW_IDS = range(0x47, 0x4D)         # side / front keys on the private pages (slots 0-5)
SLOT, ART_W, ART_H = 64, 48, 51


def clean_bank(game=None):
    root = Path(game) if game else game_source.root()
    off, length = dtna_toc.toc(Dol(root / "sys/main.dol"))[ICON_DIR][ICON_FILE]
    with open(root / "files/dt_na.dat", "rb") as f:
        f.seek(off)
        return f.read(length)


def _descriptor(img):
    return struct.pack(">IIHHIIIII", img, 0, PAGE_H, PAGE_W, 0x101, 0, 0x0E, 0, 0)


def _table(bank, at, rows=None):
    """A source table's bytes; rows {id: resource row} adds keys (descending ids, the first with marker 0x0014,
    the rest 0x0114; header +0x08 length, +0x24 count, +0x18 last frame raised to the highest id)."""
    length = struct.unpack_from(">I", bank, at + 8)[0]
    count, stride = struct.unpack_from(">HH", bank, at + 0x24)
    assert stride == SRC_RECORD and length == SRC_HEADER + count * stride
    head = bytearray(bank[at:at + SRC_HEADER])
    recs = {struct.unpack_from(">H", bank, at + SRC_HEADER + i * SRC_RECORD + 2)[0]:
            bytearray(bank[at + SRC_HEADER + i * SRC_RECORD:at + SRC_HEADER + (i + 1) * SRC_RECORD]) for i in range(count)}
    for cid, row in (rows or {}).items():
        assert cid not in recs
        rec = bytearray(recs[max(k for k in recs if k < cid)])
        struct.pack_into(">HH", rec, 2, cid, 0x0400)
        struct.pack_into(">H", rec, 6, row)
        recs[cid] = rec
    out = [recs[k] for k in sorted(recs, reverse=True)]
    for i, rec in enumerate(out):
        struct.pack_into(">H", rec, 0, 0x0014 if i == 0 else 0x0114)
    if rows:
        out[0][0x26] &= 0x7F        # the first key's +0x26 flag is 0x02 (Extra Innings' first new key; others keep 0x82)
    struct.pack_into(">I", head, 8, SRC_HEADER + len(out) * SRC_RECORD)
    struct.pack_into(">H", head, 0x24, len(out))
    struct.pack_into(">H", head, 0x18, max(struct.unpack_from(">H", head, 0x18)[0], max(recs)))
    return bytes(head) + b"".join(out)


def base_bank(game=None):
    """The icon bank charbuild's icon steps start from, made from `game` (default: game_source.root())."""
    cl = clean_bank(game)
    assert struct.unpack_from(">I", cl, 4)[0] == CLEAN_TEX_END, "not the clean icon bank"
    assert struct.unpack_from(">H", cl, 0x20)[0] == 0x92, "not the clean icon bank (page count)"
    d_old = CLEAN_TEX_END + CONTAINER_HEAD
    ptr = lambda f: d_old + struct.unpack_from(">i", cl, d_old + f)[0]
    res = ptr(0x04)
    n_rows, res_len = struct.unpack_from(">II", cl, res)
    assert res_len == 8 + n_rows * RES_ROW and n_rows == 152

    tex = bytearray(cl[:CLEAN_TEX_END]) + bytes(TEX_END - CLEAN_TEX_END)
    struct.pack_into(">I", tex, 4, TEX_END)
    struct.pack_into(">H", tex, 0x20, 0x94)
    for page, img in PAGES.items():
        tex[0x24 + page * 0x20:0x44 + page * 0x20] = _descriptor(img)
        at = TEX_BASE + img
        tex[at:at + PAGE_W * PAGE_H // 2] = CLEAR_BLOCK * (PAGE_W * PAGE_H // 16)
    # source tables, back to back in free atlas rows
    side = {cid: n_rows + i for i, cid in enumerate(NEW_IDS)}
    front = {cid: n_rows + len(NEW_IDS) + i for i, cid in enumerate(NEW_IDS)}
    tables = [_table(cl, ptr(0x08)), _table(cl, ptr(0x0C), side), _table(cl, ptr(0x10), front)]
    free = cl[TABLES_AT:CLEAN_TEX_END]
    assert not any(free), "the table area is not free in this game's bank"
    pos, starts = TABLES_AT, []
    for t in tables:
        tex[pos:pos + len(t)] = t
        starts.append(pos)
        pos += len(t)
    # container: the clean one moved to TEX_END, tables repointed, 14 rows appended
    cont = bytearray(cl[CLEAN_TEX_END:res + res_len])
    desc_end = CONTAINER_HEAD + 0x14                # the old tables' place in the container: zeroed
    cont[desc_end:res - CLEAN_TEX_END] = bytes(res - CLEAN_TEX_END - desc_end)
    tail = bytes(len(cl) - res - res_len)           # the clean bank's 8-byte tail ends in 0x08; Extra Innings' is zero
    d_new = TEX_END + CONTAINER_HEAD
    for field, at in zip((0x08, 0x0C, 0x10), starts):
        struct.pack_into(">i", cont, CONTAINER_HEAD + field, at - d_new)
    rows = []
    for page in PAGES:
        rows += [(page, 0, 0.0, s * SLOT / PAGE_W, ART_H / PAGE_H, (s * SLOT + ART_W) / PAGE_W) for s in range(6)]
    rows += [(page, 0, 0.0, 6 * SLOT / PAGE_W, ART_H / PAGE_H, (6 * SLOT + ART_W) / PAGE_W) for page in PAGES]
    rel = res - CLEAN_TEX_END
    struct.pack_into(">II", cont, rel, n_rows + len(rows), 8 + (n_rows + len(rows)) * RES_ROW)
    cont += b"".join(struct.pack(">HH4f", *r) for r in rows)
    size = struct.unpack_from(">I", cont, 0x10)[0]
    struct.pack_into(">I", cont, 0x10, size + len(rows) * RES_ROW)
    return bytes(tex + cont + tail)


if __name__ == "__main__":
    b = base_bank(sys.argv[1] if len(sys.argv) > 1 else None)
    print(f"icon bank: dir {ICON_DIR} file {ICON_FILE}, {len(b)} B (clean layout + private pages 0x92/0x93)")


# --- shrinking the finished bank (git-92, 2026-09-26: the bank stays resident in the MEM2 game heap during a match,
# and at 2.9 MB it left 473 KB free at a rival VS at-bat, which needs 2 x 560 KB: Nick's crash at 0x80597944;
# scripts/heap_budget.py). shrink() runs after charbuild's icon steps (lossless_icon_pages last): same pixels.
PAGE_FMT_RGB5A3 = 0x05
CELL_GAP = (2, 3)                   # transparent texels between packed portraits (x, y): no filtering bleed


def _pages(bank):
    return struct.unpack_from(">H", bank, 0x20)[0]


def _splice(bank, start, old_len, new):
    """bank with [start, start + old_len) of its texture section replaced by `new`, and every offset past it fixed:
    header +4 (end of the textures), the page descriptors' image / palette offsets, and the container descriptor's
    table fields (+0x08 / +0x0C / +0x10: relative to the descriptor, which moves; the tables before `start` don't).
    Nothing may point inside the replaced range except the caller's own page descriptor (updated by the caller)."""
    tex_end = struct.unpack_from(">I", bank, 4)[0]
    end, delta = start + old_len, len(new) - old_len
    assert delta % 32 == 0 and end <= tex_end, "splice outside the textures, or it would break 32-byte alignment"
    bank = bytearray(bank)
    for p in range(_pages(bank)):
        desc = 0x24 + p * 0x20
        for field in (0, 4):
            v = struct.unpack_from(">I", bank, desc + field)[0]
            if v and TEX_BASE + v >= end:
                struct.pack_into(">I", bank, desc + field, v + delta)
    d = tex_end + CONTAINER_HEAD
    for field in (0x08, 0x0C, 0x10):
        rel = struct.unpack_from(">i", bank, d + field)[0]
        if d + rel < start:                                 # before the splice: the descriptor moves, it doesn't
            struct.pack_into(">i", bank, d + field, rel - delta)
        else:                                               # after it: both move by delta
            assert d + rel >= end, "a source table inside the spliced range"
    struct.pack_into(">I", bank, 4, tex_end + delta)
    return bytes(bank[:start] + new + bank[end:])


def _refs_inside(bank, lo, hi):
    """Page descriptors whose image or palette lies in [lo, hi)."""
    return [(p, f) for p in range(_pages(bank)) for f in (0, 4)
            if lo <= TEX_BASE + struct.unpack_from(">I", bank, 0x24 + p * 0x20 + f)[0] < hi
            and struct.unpack_from(">I", bank, 0x24 + p * 0x20 + f)[0]]


def compact(bank):
    """Drop the dead area base_bank reserved for Extra Innings' CMPR pages ([CLEAN_TEX_END, TEX_END): 513 KB), which
    nothing uses once lossless_icon_pages has re-stored the private pages as RGB5A3 after it."""
    assert not _refs_inside(bank, CLEAN_TEX_END, TEX_END), "the old CMPR page area is still in use"
    return _splice(bank, CLEAN_TEX_END, TEX_END - CLEAN_TEX_END, b"")


def _untile(blob, w, h):
    import numpy as np
    t = np.frombuffer(blob[:w * h * 2], ">u2").reshape(h // 4, w // 4, 4, 4)
    return t.transpose(0, 2, 1, 3).reshape(h, w).copy()


def _tile(a):
    h, w = a.shape
    return a.reshape(h // 4, 4, w // 4, 4).transpose(0, 2, 1, 3).astype(">u2").tobytes()


def _rows(bank):
    tex_end = struct.unpack_from(">I", bank, 4)[0]
    d = tex_end + CONTAINER_HEAD
    res = d + struct.unpack_from(">i", bank, d + 4)[0]
    n = struct.unpack_from(">I", bank, res)[0]
    return res, [list(struct.unpack_from(">HH4f", bank, res + 8 + i * RES_ROW)) for i in range(n)]


def repack(bank, width=1024, gap=CELL_GAP):
    """Pack the RGB5A3 private pages (0x92 / 0x93) tightly: each distinct portrait rect (from the resource rows)
    into cells of its size + `gap`, row by row, copied texel for texel (no re-encode), then the rows' UVs and the
    page descriptor (height, width) rewritten and the image spliced in place. Was a 64 x 64 slot grid for 48 x 51."""
    import numpy as np
    for page in PAGES:
        desc = 0x24 + page * 0x20
        assert bank[desc + 0x17] == PAGE_FMT_RGB5A3, f"page 0x{page:02X} isn't RGB5A3 (run after lossless_icon_pages)"
        img = TEX_BASE + struct.unpack_from(">I", bank, desc)[0]
        h, w = struct.unpack_from(">HH", bank, desc + 8)
        old_len = w * h * 2 + (-(w * h * 2) % 32)
        src = _untile(bank[img:img + w * h * 2], w, h)
        res, rows = _rows(bank)
        rects, content = [], {}                             # distinct portraits by pixels (git-f3: 28 of 210 were
        for r in rows:                                      # exact duplicates), first use first; rect -> content key
            if r[0] == page:
                x, y = round(r[3] * w), round(r[2] * h)
                rect = (x, y, round(r[5] * w) - x, round(r[4] * h) - y)
                key = (rect[2], rect[3], src[y:y + rect[3], x:x + rect[2]].tobytes())
                if key not in content.values():
                    rects.append(rect)
                content[rect] = key
        if not rects:                                       # every portrait left this page (ci8_pages): a 4 x 4 blank
            bank = bytearray(bank)
            struct.pack_into(">HH", bank, desc + 8, 4, 4)
            bank = _splice(bytes(bank), img, old_len, bytes(32))
            continue
        cw, ch = max(r[2] for r in rects) + gap[0], max(r[3] for r in rects) + gap[1]

        def size(per):                                      # a page of `per` cells a row, rounded to whole tiles
            return per * cw + (-(per * cw) % 4), -(-len(rects) // per) * ch + (-(-(-len(rects) // per) * ch) % 4)
        fits = [per for per in range(1, width // cw + 1) if max(size(per)) <= 1024]    # GX textures go to 1024
        per_row = min(fits, key=lambda per: (size(per)[0] * size(per)[1], -per))
        nw, nh = size(per_row)
        assert nw <= 1024 and nh <= 1024, f"page 0x{page:02X} would be {nw}x{nh} (GX textures go to 1024)"
        dst = np.zeros((nh, nw), np.uint16)                 # 0x0000: RGB5A3 alpha 0
        where = {}
        for k, (x, y, rw, rh) in enumerate(rects):
            nx, ny = (k % per_row) * cw + gap[0] // 2, (k // per_row) * ch + gap[1] // 2
            dst[ny:ny + rh, nx:nx + rw] = src[y:y + rh, x:x + rw]
            where[content[(x, y, rw, rh)]] = (nx, ny)
        bank = bytearray(bank)
        for i, r in enumerate(rows):
            if r[0] == page:
                x, y = round(r[3] * w), round(r[2] * h)
                rect = (x, y, round(r[5] * w) - x, round(r[4] * h) - y)
                nx, ny = where[content[rect]]
                r[2], r[3], r[4], r[5] = ny / nh, nx / nw, (ny + rect[3]) / nh, (nx + rect[2]) / nw
                struct.pack_into(">HH4f", bank, res + 8 + i * RES_ROW, *r)
        struct.pack_into(">HH", bank, desc + 8, nh, nw)
        blob = _tile(dst)
        bank = _splice(bytes(bank), img, old_len, blob + bytes(-len(blob) % 32))
    return bank


def shrink(bank):
    """repack() then compact(): the finished bank's in-match size without changing a pixel on screen."""
    return compact(repack(bank))


# --- phase C (git-92, 2026-09-26; OFF unless charbuild asks): portraits as CI8 textures with their own palette --------
def rgb5a3_to_rgba(v):
    """uint16 RGB5A3 array -> uint8 RGBA (..., 4), as the GPU expands it."""
    import numpy as np
    v = np.asarray(v, np.uint32)
    op = (v & 0x8000) != 0
    r = np.where(op, ((v >> 10) & 31) * 255 // 31, ((v >> 8) & 15) * 17)
    g = np.where(op, ((v >> 5) & 31) * 255 // 31, ((v >> 4) & 15) * 17)
    b = np.where(op, (v & 31) * 255 // 31, (v & 15) * 17)
    a = np.where(op, 255, ((v >> 12) & 7) * 255 // 7)
    return np.stack([r, g, b, a], -1).astype(np.uint8)


def rgba_to_rgb5a3(c):
    """uint8 RGBA (..., 4) -> uint16 RGB5A3 (opaque form when alpha >= 0xE0, as captain_art.rgb5a3)."""
    import numpy as np
    c = np.asarray(c, np.uint32)
    r, g, b, a = c[..., 0], c[..., 1], c[..., 2], c[..., 3]
    opaque = 0x8000 | ((r >> 3) << 10) | ((g >> 3) << 5) | (b >> 3)
    trans = ((a >> 5) << 12) | ((r >> 4) << 8) | ((g >> 4) << 4) | (b >> 4)
    return np.where(a >= 0xE0, opaque, trans).astype(np.uint16)


def ci8(tex, colors=256, rounds=24):
    """A portrait's RGB5A3 texels (uint16 h x w) -> (uint8 indices h x w, uint16 palette[colors], exact). Exact
    (the same texels back) when it has <= `colors` distinct values; else a weighted k-means over its distinct
    colours (alpha counted like a colour channel), the fully transparent texels kept as one exact entry, every texel
    mapped to its nearest palette colour as the GPU will show it. Deterministic."""
    import numpy as np
    uniq, inv, cnt = np.unique(tex.ravel(), return_inverse=True, return_counts=True)
    if len(uniq) <= colors:
        pal = np.zeros(colors, np.uint16)
        pal[:len(uniq)] = uniq
        return inv.reshape(tex.shape).astype(np.uint8), pal, True
    rgba = rgb5a3_to_rgba(uniq).astype(np.float64)
    clear = rgba[:, 3] == 0
    pts, w = rgba[~clear], cnt[~clear].astype(np.float64)
    k = colors - (1 if clear.any() else 0)
    # k-means++ seeding (weighted, deterministic), then Lloyd rounds
    rng = np.random.default_rng(0x5106)
    cent = [pts[np.argmax(w)]]
    d2 = ((pts - cent[0]) ** 2).sum(1)
    for _ in range(1, k):
        p = d2 * w
        cent.append(pts[rng.choice(len(pts), p=p / p.sum())] if p.sum() > 0 else pts[0])
        d2 = np.minimum(d2, ((pts - cent[-1]) ** 2).sum(1))
    cent = np.array(cent)
    for _ in range(rounds):
        lab = ((pts[:, None, :] - cent[None]) ** 2).sum(2).argmin(1)
        for j in range(k):
            m = lab == j
            if m.any():
                cent[j] = (pts[m] * w[m, None]).sum(0) / w[m].sum()
    pal16 = rgba_to_rgb5a3(np.clip(np.rint(cent), 0, 255))
    shown = rgb5a3_to_rgba(pal16).astype(np.float64)
    lab = np.zeros(len(uniq), np.int64)
    lab[~clear] = ((pts[:, None, :] - shown[None]) ** 2).sum(2).argmin(1)
    pal = np.zeros(colors, np.uint16)
    pal[:k] = pal16
    if clear.any():
        pal[k] = 0x0000
        lab[clear] = k
    return lab[inv].reshape(tex.shape).astype(np.uint8), pal, False


def _tile_ci8(idx):
    """uint8 h x w indices -> GX CI8 (8 x 4 tiles)."""
    h, w = idx.shape
    return idx.reshape(h // 4, 4, w // 8, 8).transpose(0, 2, 1, 3).tobytes()


def _untile_ci8(blob, w, h):
    import numpy as np
    return np.frombuffer(blob[:w * h], np.uint8).reshape(h // 4, w // 8, 4, 8).transpose(0, 2, 1, 3).reshape(h, w).copy()


CI8_DESC = bytes.fromhex("00000000" "00000000" "00000000" "00000101" "00000000" "00000009" "01000200" "00000000")
# (a stock CI8 page's descriptor, image / palette / size filled in: +0x17 format 9, +0x18 256 entries, palette RGB5A3)


def ci8_pages(bank, exact_only=False):
    """Phase C (OFF unless charbuild asks; git-92: waits on the page-count cap check and Nick's look at the quantized
    portraits): every portrait on the RGB5A3 private pages becomes its own CI8 page with its own 256-colour palette
    (ci8(): exact for 143 of 210 today). The new page descriptors go at the end of the descriptor table (everything
    after it moves by their size; _splice fixes the offsets), images and palettes at the end of the textures, each row
    points at its portrait's page (UV the art's part of it), and 0x92 / 0x93 keep a 4 x 4 blank. Run after shrink().
    exact_only (git-f3's no-visible-change cut): only the portraits CI8 stores exactly (<= 256 RGB5A3 values; the
    palette is RGB5A3 too, so partial alpha is exact) get their own page; the rest stay RGB5A3, repacked onto 0x92 /
    0x93. Every texel then stays bit-identical. -> (bank, {"portraits", "exact", "pages"})."""
    import numpy as np
    res, rows = _rows(bank)
    portraits, where, row_of = [], {}, {}
    for page in PAGES:
        desc = 0x24 + page * 0x20
        assert bank[desc + 0x17] == PAGE_FMT_RGB5A3, "run after lossless_icon_pages / shrink"
        img = TEX_BASE + struct.unpack_from(">I", bank, desc)[0]
        h, w = struct.unpack_from(">HH", bank, desc + 8)
        src = _untile(bank[img:img + w * h * 2], w, h)
        for i, r in enumerate(rows):
            if r[0] == page:
                x0, y0, x1, y1 = round(r[3] * w), round(r[2] * h), round(r[5] * w), round(r[4] * h)
                t = src[y0:y1, x0:x1]
                key = (t.shape, t.tobytes())                   # duplicates (same pixels) share a page
                if key not in where:
                    q = ci8(t)
                    if exact_only and not q[2]:
                        continue                               # stays RGB5A3 on its page
                    where[key] = len(portraits)
                    portraits.append((t, q))
                row_of[i] = where[key]
    n0, k = _pages(bank), len(portraits)
    # 1. room for k descriptors after the table; the page count covers them from here on
    bank = bytearray(_splice(bank, 0x24 + n0 * 0x20, 0, bytes(k * 0x20)))
    struct.pack_into(">H", bank, 0x20, n0 + k)
    # 2. the RGB5A3 pages leave the textures: a 4 x 4 blank each (32 B; exact_only: repacked at the end instead)
    for page in (() if exact_only else PAGES):
        desc = 0x24 + page * 0x20
        img = TEX_BASE + struct.unpack_from(">I", bank, desc)[0]
        h, w = struct.unpack_from(">HH", bank, desc + 8)
        struct.pack_into(">HH", bank, desc + 8, 4, 4)
        bank = bytearray(_splice(bytes(bank), img, w * h * 2 + (-(w * h * 2) % 32), bytes(32)))
    # 3. each portrait's image + palette at the end of the textures, its descriptor, its rows
    tex_end = struct.unpack_from(">I", bank, 4)[0]
    blob, exact, sizes, descs = bytearray(), 0, [], []
    for j, (t, (idx, pal, ok)) in enumerate(portraits):
        exact += ok
        rh, rw = t.shape
        ph, pw = rh + (-rh % 4), rw + (-rw % 8)
        clear = np.where(pal == 0)[0]
        full = np.full((ph, pw), clear[0] if len(clear) else 0, np.uint8)
        full[:rh, :rw] = idx
        img_at = tex_end + len(blob)
        blob += _tile_ci8(full)
        blob += bytes(-len(blob) % 32)
        pal_at = tex_end + len(blob)
        blob += pal.astype(">u2").tobytes()
        d = bytearray(CI8_DESC)
        struct.pack_into(">IIHH", d, 0, img_at - TEX_BASE, pal_at - TEX_BASE, ph, pw)
        descs.append(bytes(d))
        sizes.append((rh, rw, ph, pw))
    # the blob first (the new descriptors are still zero, so the splice leaves them alone), then the descriptors
    bank = bytearray(_splice(bytes(bank), tex_end, 0, bytes(blob)))
    for j, d in enumerate(descs):
        bank[0x24 + (n0 + j) * 0x20:0x24 + (n0 + j + 1) * 0x20] = d
    res, rows = _rows(bank)
    for i, j in row_of.items():
        rh, rw, ph, pw = sizes[j]
        struct.pack_into(">HH4f", bank, res + 8 + i * RES_ROW, n0 + j, 0, 0.0, 0.0, rh / ph, rw / pw)
    if exact_only:                                             # the rest, packed onto 0x92 / 0x93 without the gaps
        bank = repack(bytes(bank))
    return bytes(bank), {"portraits": k, "exact": exact, "pages": (n0, n0 + k)}
