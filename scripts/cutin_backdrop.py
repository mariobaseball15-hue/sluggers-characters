"""Captain star cut-in backdrop for characters the game has no backdrop for (custom captains).

FUN_802C4364(mgr, character id, slot) loads the cut-in backdrop from dt_na dir 0x9F (file k for slot 0, k+12 for
slot 1) through a switch on the CHARACTER id with cases only for the stock captains (Mario 0, Luigi 1, DK 2,
Diddy 3, Peach 4, ..., Wario 6, Waluigi 7, Birdo 9, Bowser Jr. 0xB); any other id loads none, so a custom
captain's star cut-in has no background. HOOK 0x802C437C (`mr r27,r4`, r4 = the u16 character id): characters in
BACKDROP_FROM use that stock captain's case. Confirmed in Dolphin for Rosalina -> Peach (2026-09-24).

Own backdrops (OWN_BACKDROP, hooks(own=True) + backdrop_directory): a recolored copy of a stock captain's backdrop.
Each backdrop file is a model block (8 boxes, CI8 textures with RGB565 palettes, RGB565 / RGBA4 vertex colors); the
copy maps every palette entry, CMPR block endpoint and vertex color through a color function: a hue turn by the
given degrees (and BRIGHTEN), or the character's STYLE (King Bob-omb: black and grey with yellow highlights). The copies are appended to
dt_na.dat as dir 0x9F files 24 + 2i (slot 0) and 25 + 2i (slot 1), in a rebuilt, longer record block for the
directory (the loader FUN_802c5fd0 indexes records with no bound). DEFAULT 0x802C4500 (`li r30,-1`, the switch's
no-backdrop case, also taken for ids above 0x13): an own-backdrop character gets its file index instead. r27 keeps
the real id, so the loaded-backdrop cache (+0x1C, keyed by character id) tells it apart from the source captain.
PROPS 0x802C4964 (FUN_802C4938, `lha r0,0x1c(r3)`): when the cut-in starts/ends, that same +0x1C id picks the
captain's prop to move onto / off the cut-in draw layer (scene objects: Wario 0x0A -> 8, the bomb; Waluigi 0x0B ->
0xD (slot 0); DK 2 -> 10; Yoshi 6, Birdo 0x11, Daisy 5, Mario 0, Bowser Jr. 0x13, Bowser 9). An own-backdrop id has
no case, so King Bob-omb's bomb stayed hidden behind the backdrop (Dolphin, 2026-09-24): own ids read as their
source captain here. cr0 is live across the load (compares in cr1).
See docs/star-swings.md, "Captain star cut-in".
"""
import colorsys
import struct
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
from ppc import Asm  # noqa: E402
from mss_model import Model  # noqa: E402
import dtna_toc  # noqa: E402

BACKDROP_FROM = {
    0x81: 0x04,   # Rosalina -> Peach's (Daisy's: 0x05)
    0x78: 0x0A,   # King Bob-omb -> Wario's (his template; he has Wario's stats row, star swing 7)
    0x25: 0x0B,   # King Boo -> Waluigi's (his Boo Ball borrows Waluigi's cut-in)
    0x67: 0x09,   # Boom Boom -> Bowser's (his template): his star throw's backdrop (boom_boom_star_throw.py)
}
OWN_BACKDROP = {
    0x81: (0x04, -75),   # Rosalina: Peach's with the hue turned 75 degrees (purple/pink -> teal/cyan)
    0x25: (0x0B, -150),  # King Boo: Waluigi's (purple rings, nebula, lightning) -> ghostly green
    0x78: (0x0A, 0),     # King Bob-omb: Wario's (gold clouds, starbursts), in STYLE "bomb" (was -35: orange-red)
    0x84: (0x04, 135),   # Yellow Luma (Star Shower): Peach's turned 135 degrees (pink/purple -> yellow/gold; 90 was red)
}
BRIGHTEN = {0x84: 1.5}   # brightness gain with the turn: yellow at the nebula's low brightness reads as olive
# Nick (via git-5d): King Bob-omb's reads like a Bob-omb, a black body with a yellow fuse spark: every color to
# grey by its brightness, darkened, and only the brightest (the starburst cores) warmed to yellow.
BOMB_DARK = 0.42          # grey = brightness x this (charcoal / black; 0.55 read mid-grey)
BOMB_SPARK = (0.70, 0.86)  # brightness range over which the highlights blend into yellow
BOMB_YELLOW = (48, 0.85)   # hue (degrees), saturation of the highlights
STYLE = {0x78: "bomb"}
# Star move creations' backdrops (creators/backdrops.py): MOVES = {"swing" / "pitch": {move id: (source captain, hue,
# brightness, style)}} (the creators' configure sets it), and SLOTS = {character id: [(source, colour function or None:
# the bytes as they are) for slot 0, slot 1]} for the characters on those moves (add_created, from charbuild). New
# ones join OWN_BACKDROP at its end, so a build without any is today's.
MOVES = {"swing": {}, "pitch": {}}
SLOTS = {}
PICTURES = {}             # {(character id, slot): {texture index: png path}}: a creation's own pictures (backdrop_pictures)
BACKDROP_DIR, STOCK_FILES = 0x9F, 24
# FUN_802C4364's switch: character id -> slot 0 file (slot 1 is +12)
STOCK_FILE = {0x00: 0, 0x01: 1, 0x02: 2, 0x03: 3, 0x04: 4, 0x05: 5, 0x06: 8, 0x09: 10, 0x0A: 6, 0x0B: 7,
              0x11: 9, 0x13: 11}


def hook(base, own=()):
    a = Asm(base)
    a.mr(27, 4)                            # the replaced instruction: r27 = character id
    a.andi_(12, 4, 0xFFFF)
    for cid, src in BACKDROP_FROM.items():
        if cid in own:
            continue
        a.cmplwi(12, cid).bne(f"not{cid}")
        a.li(27, src).b("done")
        a.label(f"not{cid}")
    a.label("done")
    return a


def default_hook(base):
    """Replaces `li r30,-1`: r27 = character id, r28 = slot. cr0 is left alone (compares in cr1)."""
    a = Asm(base)
    a.li(30, -1)
    a.clrlwi(12, 27, 16)
    for i, cid in enumerate(OWN_BACKDROP):
        a.cmplwi(12, cid, cr=1).bne(f"not{cid}", cr=1)
        a.clrlwi(11, 28, 24).cmplwi(11, 0, cr=1)
        a.li(30, STOCK_FILES + 2 * i).beq("done", cr=1)
        a.li(30, STOCK_FILES + 2 * i + 1).b("done")
        a.label(f"not{cid}")
    a.label("done")
    return a


def props_hook(base):
    a = Asm(base)
    a.word(0xA803001C)                     # lha r0,0x1c(r3) (the replaced instruction)
    for cid, (src, _) in OWN_BACKDROP.items():
        a.cmpwi(0, cid, cr=1).bne(f"not{cid}", cr=1)
        a.li(0, src).b("done")
        a.label(f"not{cid}")
    a.label("done")
    return a


CASE, CASE_ORIG = 0x802C4504, 0x7FC00734          # extsh r0,r30: every path of the switch, r30 = the file


def case_hook(base):
    """Replaces `extsh r0,r30` after the switch: an own-backdrop STOCK captain (a creation's backdrop on Mario, ...;
    its case set r30, so DEFAULT never runs) gets its own file. Only built when there is one."""
    a = Asm(base)
    a.clrlwi(12, 27, 16)
    for i, cid in enumerate(OWN_BACKDROP):
        if cid not in STOCK_FILE:
            continue
        a.cmplwi(12, cid, cr=1).bne(f"not{cid}", cr=1)
        a.clrlwi(11, 28, 24).cmplwi(11, 0, cr=1)
        a.li(30, STOCK_FILES + 2 * i).beq("done", cr=1)
        a.li(30, STOCK_FILES + 2 * i + 1).b("done")
        a.label(f"not{cid}")
    a.label("done")
    a.word(CASE_ORIG)
    return a


def hooks(own=False):
    """own=True: OWN_BACKDROP characters load their own files (the build must add them: backdrop_directory)."""
    ids = tuple(OWN_BACKDROP) if own else ()
    out = [(0x802C437C, 0x7C9B2378, lambda base: hook(base, ids))]     # mr r27,r4
    if own:
        out.append((0x802C4500, 0x3BC0FFFF, default_hook))             # li r30,-1
        out.append((0x802C4964, 0xA803001C, props_hook))               # lha r0,0x1c(r3)
        if any(cid in STOCK_FILE for cid in OWN_BACKDROP):
            out.append((CASE, CASE_ORIG, case_hook))
    return out


def _colour(hue, brightness, style):
    """The colour function, or None when it changes nothing (hue 0, x1: the pictures / the stock bytes as they are)."""
    if style != "bomb" and hue == 0 and brightness == 1.0:
        return None
    return bomb if style == "bomb" else turn(hue, brightness)


def _current(cid):
    """(source, colour function or None) of the backdrop character `cid` shows now (before add_created), or None."""
    if cid in SLOTS:
        return SLOTS[cid][1]
    if cid in OWN_BACKDROP:
        return OWN_BACKDROP[cid][0], color_fn(cid)
    if cid in BACKDROP_FROM:
        return BACKDROP_FROM[cid], None
    if cid in STOCK_FILE:
        return cid, None
    return None


def add_created(plan):
    """plan: {character id: {slot: (source, hue, brightness, style)}} (creators.backdrops.plan) -> SLOTS, and each
    character in OWN_BACKDROP (new ones at its end). A slot the plan leaves out keeps the character's backdrop
    (_current), or with none shows the plan's other one. The cut-in props follow the batting backdrop's captain.
    Returns log lines."""
    log = []
    for cid, slots in plan.items():
        keep = _current(cid)
        pair = []
        for s in (0, 1):
            src, hue, bright, style, *pics = slots[s] if s in slots else slots[1 - s]
            pair.append((src, _colour(hue, bright, style)) if s in slots or not keep else keep)
            if pics and pics[0] and (s in slots or not keep):
                PICTURES[(cid, s)] = dict(pics[0])
        SLOTS[cid] = pair
        props = pair[1][0]                              # the batting backdrop's captain (star swing props)
        OWN_BACKDROP[cid] = (props, OWN_BACKDROP.get(cid, (props, 0))[1])
        said = []
        for s, (src, hue, bright, style, *pics) in sorted(slots.items()):
            how = "bomb style" if style == "bomb" else f"hue {hue:+d}, x{bright:g}"
            if pics and pics[0]:
                how += f", own pictures {', '.join(str(k) for k, _ in pics[0])}"
            said.append(f"{'pitching' if s == 0 else 'batting'} 0x{src:02X}'s ({how})")
        log.append(f"0x{cid:02X}: " + ", ".join(said))
    return log


def sources(cid):
    """[(source captain, colour function or None)] for slot 0 and slot 1 of OWN_BACKDROP character `cid`."""
    if cid in SLOTS:
        return SLOTS[cid]
    return [(OWN_BACKDROP[cid][0], color_fn(cid))] * 2


HOOKS = hooks()


def turn(degrees, value=1.0):
    """Color function: hue turned by `degrees`, value x `value` (0..255 floats in and out)."""
    def fn(r, g, b):
        h, s, v = colorsys.rgb_to_hsv(r / 255, g / 255, b / 255)
        r, g, b = colorsys.hsv_to_rgb((h + degrees / 360) % 1.0, s, min(1.0, v * value))
        return r * 255, g * 255, b * 255
    return fn


def bomb(r, g, b):
    """Color function: grey by brightness (Rec. 601 luma), x BOMB_DARK; the brightest blend into warm yellow."""
    y = (0.299 * r + 0.587 * g + 0.114 * b) / 255
    grey = y * BOMB_DARK
    lo, hi = BOMB_SPARK
    t = min(1.0, max(0.0, (y - lo) / (hi - lo)))
    t = t * t * (3 - 2 * t)                                  # smoothstep
    yr, yg, yb = colorsys.hsv_to_rgb(BOMB_YELLOW[0] / 360, BOMB_YELLOW[1], min(1.0, y * 1.05))
    return tuple(255 * (grey * (1 - t) + c * t) for c in (yr, yg, yb))


def color_fn(cid):
    """The color function of OWN_BACKDROP character `cid`."""
    if STYLE.get(cid) == "bomb":
        return bomb
    return turn(OWN_BACKDROP[cid][1], BRIGHTEN.get(cid, 1.0))


def _turn565(v, fn):
    r, g, b = fn((v >> 11 & 31) * 255 / 31, (v >> 5 & 63) * 255 / 63, (v & 31) * 255 / 31)
    return round(r * 31 / 255) << 11 | round(g * 63 / 255) << 5 | round(b * 31 / 255)


def _turn4444(v, fn):
    r, g, b = fn((v >> 12 & 15) * 17, (v >> 8 & 15) * 17, (v >> 4 & 15) * 17)
    return round(r / 17) << 12 | round(g / 17) << 8 | round(b / 17) << 4 | (v & 15)


def _turn_cmpr(b, start, size, fn):
    """Map every CMPR block's two RGB565 endpoints in place. The block's mode is c0 > c1 (4 colors) or
    c0 <= c1 (3 colors + transparent), so when the turn flips their order the endpoints swap and the indices
    are remapped to the same colors (4-color: 0<->1, 2<->3; 3-color: 0<->1)."""
    for o in range(start, start + size, 8):
        c0, c1, idx = struct.unpack_from(">HHI", b, o)
        n0, n1 = _turn565(c0, fn), _turn565(c1, fn)
        four = c0 > c1
        if four and n0 < n1 or not four and n0 > n1:
            n0, n1 = n1, n0
            swap = (1, 0, 3, 2) if four else (1, 0, 2, 3)
            idx = sum(swap[idx >> 2 * k & 3] << 2 * k for k in range(16))
        if four and n0 == n1:              # would become 3-color: index 3 would turn transparent
            idx = 0
        struct.pack_into(">HHI", b, o, n0, n1, idx)


def recolor(block, fn):
    """A backdrop block with every palette entry (RGB565), CMPR endpoint and vertex color (RGB565 / RGBA4)
    mapped through the color function `fn`."""
    b = bytearray(block)
    m = Model(bytes(block))
    for t in m.textures:
        if t.format == 14:
            _turn_cmpr(b, t.image, t.payload_size(), fn)
            continue
        assert t.format in (8, 9) and t.palette, f"texture format {t.format} (CI4/CI8/CMPR handled)"
        n, pfmt = struct.unpack_from(">HB", b, t.off + 0x18)
        assert pfmt == 1, f"palette format {pfmt} (only RGB565 handled)"
        for k in range(n):
            o = t.palette + 2 * k
            struct.pack_into(">H", b, o, _turn565(struct.unpack_from(">H", b, o)[0], fn))
    for s in m.submeshes:
        c = s.color
        if not c:
            continue
        kind = c.quant >> 4
        assert c.element_size() == 2 and kind in (0, 3), f"{s.name}: vertex color format {c.quant:#x}"
        conv = _turn565 if kind == 0 else _turn4444
        for k in range(c.count):
            o = c.ptr + 2 * k
            struct.pack_into(">H", b, o, conv(struct.unpack_from(">H", b, o)[0], fn))
    return bytes(b)


def own_blocks(dol, dat_path):
    """[(slot 0 block, slot 1 block)] per OWN_BACKDROP entry, in order. dol: a DOL with the stock dt_na index."""
    files = dtna_toc.toc(dol)[BACKDROP_DIR]
    assert len(files) == STOCK_FILES
    out = []
    with open(dat_path, "rb") as f:
        for cid in OWN_BACKDROP:
            pair = []
            for slot, (src, fn) in enumerate(sources(cid)):
                off, length = files[STOCK_FILE[src] + 12 * slot]
                f.seek(off)
                blob = f.read(length)
                if PICTURES.get((cid, slot)):           # the player's own pictures first, then the colour turn
                    import backdrop_pictures
                    blob = backdrop_pictures.apply(blob, PICTURES[(cid, slot)])
                pair.append(recolor(blob, fn) if fn else blob)
            out.append(tuple(pair))
    return out


def backdrop_directory(dol, dat_path, cursor):
    """Dir 0x9F's records with the own backdrops appended as files 24.. (their data at `cursor` onward in dt_na.dat).
    Returns (records, [(dt_na offset, bytes)], new cursor). The caller places the records in memory and points
    directory 0x9F at them. dol: a DOL with the stock dt_na index."""
    ptr = dtna_toc.dir_pointers(dol)[BACKDROP_DIR]
    records = bytearray(dol.read(ptr, STOCK_FILES * dtna_toc.FILE_RECORD))
    appended = []
    for i, (cid, pair) in enumerate(zip(OWN_BACKDROP, own_blocks(dol, dat_path))):
        for slot, blob in enumerate(pair):
            k = STOCK_FILE[sources(cid)[slot][0]] + 12 * slot
            rec = bytearray(records[k * dtna_toc.FILE_RECORD:(k + 1) * dtna_toc.FILE_RECORD])  # source's name ptr
            for lang in range(3):
                struct.pack_into(">III", rec, lang * 16 + 4, len(blob), cursor, len(blob))
            assert len(records) == (STOCK_FILES + 2 * i + slot) * dtna_toc.FILE_RECORD
            records += rec
            appended.append((cursor, blob))
            cursor += len(blob) + (-len(blob) % 32)
    return bytes(records), appended, cursor


if __name__ == "__main__":
    # python scripts/cutin_backdrop.py <out_dir>: preview PNGs of the own backdrops' textures (stock vs recolored)
    import particle_textures as P
    from PIL import Image
    from dol import Dol
    root = Path(__file__).resolve().parents[1]
    out = Path(sys.argv[1] if len(sys.argv) > 1 else root / "models/work/backdrops")
    out.mkdir(parents=True, exist_ok=True)
    import game_source
    dol = Dol(game_source.root() / "sys/main.dol")
    dat = game_source.root() / "files/dt_na.dat"
    files = dtna_toc.toc(dol)[BACKDROP_DIR]
    for (cid, (src, _)), (new, _) in zip(OWN_BACKDROP.items(), own_blocks(dol, dat)):
        off, length = files[STOCK_FILE[src]]
        with open(dat, "rb") as f:
            f.seek(off)
            old = f.read(length)
        rows = []
        for blk in (old, new):
            m = Model(blk)
            ims = []
            for t in m.textures:
                pal = [P.rgb565(struct.unpack_from(">H", blk, t.palette + 2 * k)[0]) for k in range(256)]                     if t.palette else None
                ims.append(P.decode(t.format, t.width, t.height, blk[t.image:t.image + t.payload_size()], pal))
            rows.append(ims)
        sheet = Image.new("RGBA", (266 * len(rows[0]), 266 * 2), (40, 40, 40, 255))
        for y, ims in enumerate(rows):
            for x, im in enumerate(ims):
                sheet.paste(im, (266 * x, 266 * y))
        sheet.save(out / f"backdrop_{cid:02x}.png")
        print(out / f"backdrop_{cid:02x}.png")
