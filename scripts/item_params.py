"""Items' own values in their stock item's parameter table (creators/items.py: hit.radius, blast, effect.quake_radius).

Each stock item reads its numbers from one table in data: 2 modes (60 / 50 Hz: frames x5/6, speeds x1.2) x 2 rows
(the item's +0x34), rows of floats, indexed `table + mode * 2 * row + item[+0x34] * row` (e.g. FUN_8044fcd4, the
Bob-omb's radius getter). Fields found so far ([C] read in code):

  Fireball 0x80631298, row 0x20: +0x00 hit radius (vt+0x1C, the hit checks) [C]
  Bob-omb  0x80631058, row 0x3C: +0x00 hit radius [C]; +0x0C blast radius, +0x10 blast height (FUN_8044faf0 /
           FUN_8044fb18: the exploding bomb's fielder check in FUN_80117408, the runners' in FUN_80176d30) [C];
           +0x28 fuse, frames (FUN_8044fb40: the armed timer when it touches a fielder) [C]
  POW      0x806311D8, row 0x30: +0x00 hit radius [C]; +0x08 quake radius (FUN_8045905c: the quake's fielder check
           in FUN_80117e34, the runners' in FUN_801770f4) [C]
  Banana   0x80631148, row 0x24: +0x00 hit radius [C]; +0x14 how far the extra peels scatter (FUN_8044ed58: each
           peel at cos / sin of its angle x this, around the first) [C]
The Banana's peel COUNT isn't in the table: FUN_8044ed58 scatters 4 more peels (`cmplwi r31,4` at PEEL_LOOP, over
the item manager's 5 banana objects at +0x1BC); peel_gate() gives an item fewer (its own loop bound).
(The Shell's table, 0x80631008, has its own radius hook: shell_item.)

An item sets a field as its value in row 0 at 60 Hz; the other rows and the 50 Hz ones scale by the same ratio (the
stock game's own spread). At use (ice_item's use stub, after the variant byte is set: r0 = variant, r4 = the stock
item), ROUTINE copies the item's rows over its stock item's table, or the stock rows back for any other item built
on that stock item: one item flies at a time. Emitted only when some item sets a field.
"""
import struct

from ppc import Asm, ha, lo

TABLES = {1: (0x80631298, 0x20), 2: (0x80631058, 0x3C), 3: (0x806311D8, 0x30), 4: (0x80631148, 0x24)}   # stock id
FIELDS = {"radius": 0x00, "blast_radius": 0x0C, "blast_height": 0x10, "fuse_frames": 0x28, "quake_radius": 0x08,
          "peel_spread": 0x14}
FIELD_BASES = {"radius": (1, 2, 3, 4), "blast_radius": (2,), "blast_height": (2,), "fuse_frames": (2,),
               "quake_radius": (3,), "peel_spread": (4,)}
PEEL_LOOP, PEEL_LOOP_ORIG, PEEL_BACK = 0x8044EEA4, 0x281F0004, 0x8044EEA8   # cmplwi r31,4 (then blt the loop)
# The slip (FUN_8012a99c: the Banana's, the POW quake's, our rings' and bits'): the fielder's +0x214 countdown, from
# the fielder table 0x80625F20 + mode * 0x68 + 0x4A (90 frames; 75 at 50 Hz) [C: FUN_8010ed78 ends it at 0]
SLIP_STORE, SLIP_STORE_ORIG, SLIP_FRAMES = 0x8012ACA4, 0xB01E0214, (90, 75)     # sth r0,0x214(r30)
# The Boo (COjyamaTeresa, FUN_80459a58 at use): its time (+0x38) from DAT_807A1640 + mode * 4: +2 while the ball is
# live (state 3: 180 frames, 150 at 50 Hz), +0 otherwise (states 1 / 2: 90, 75) [C]; both stores sth r0,0x38(r31)
BOO_STORES = ((0x80459B4C, 0xB01F0038, (180, 150)), (0x80459B14, 0xB01F0038, (90, 75)))
PEELS = 5                                            # the first peel + 4 scattered
LAYOUT = {}


def stock_rows(dol, base):
    addr, row = TABLES[base]
    return dol.read(addr, 4 * row)


def rows(dol, base, values):
    """The table's 4 rows with {field: row-0 60 Hz value}: every row scaled by value / stock row 0."""
    addr, row = TABLES[base]
    blob = bytearray(stock_rows(dol, base))
    for name, v in values.items():
        assert base in FIELD_BASES[name], f"{name} isn't a field of stock item {base}"
        off = FIELDS[name]
        s0 = struct.unpack_from(">f", blob, off)[0]
        for r in range(4):
            s = struct.unpack_from(">f", blob, r * row + off)[0]
            struct.pack_into(">f", blob, r * row + off, float(v) * s / s0 if s0 else float(v))
    return bytes(blob)


def routine(dol, code, data, specs):
    """specs: [(variant id, stock id, {field: value})] -> a use_call for ice_item.apply (None: nothing to do)."""
    specs = [(v, b, vals) for v, b, vals in specs if vals]
    if not specs:
        return None

    def place(flag):
        bases = sorted({b for _, b, _ in specs})
        backup = {b: data.put(stock_rows(dol, b), 4) for b in bases}
        own = {v: data.put(rows(dol, b, vals), 4) for v, b, vals in specs}
        a = Asm(code.here + (-code.here % 4))
        a.stwu("r1", -0x20, "r1").stw("r3", 8, "r1").stw("r5", 0xC, "r1").stw("r6", 0x10, "r1")
        for b in bases:
            addr, row = TABLES[b]
            a.cmpwi("r4", b).bne(f"next{b}")
            for v, vb, _ in specs:
                if vb == b:
                    a.cmpwi("r0", v).beq(f"own{v}")
            a.lis("r3", ha(backup[b] - 4)).addi("r3", "r3", lo(backup[b] - 4)).b(f"copy{b}")
            for v, vb, _ in specs:
                if vb == b:
                    a.label(f"own{v}")
                    a.lis("r3", ha(own[v] - 4)).addi("r3", "r3", lo(own[v] - 4)).b(f"copy{b}")
            a.label(f"copy{b}")
            a.lis("r5", ha(addr - 4)).addi("r5", "r5", lo(addr - 4)).li("r6", row)   # 4 rows = row words
            a.label(f"loop{b}")
            a.lwz("r12", 4, "r3").addi("r3", "r3", 4).stw("r12", 4, "r5").addi("r5", "r5", 4)
            a.addi("r6", "r6", -1).cmpwi("r6", 0).bne(f"loop{b}")
            a.b("done")
            a.label(f"next{b}")
        a.label("done")
        a.lwz("r3", 8, "r1").lwz("r5", 0xC, "r1").lwz("r6", 0x10, "r1").addi("r1", "r1", 0x20).blr()
        at = code.put(a.assemble(), 4)
        assert at == a.base
        LAYOUT.update(routine=at, backup=backup, own=own)
        return at
    return place


def peel_gate(dol, code, flag, counts):
    """counts: {variant: peels (1..PEELS)}: fewer peels for those items (the scatter loop's bound). Returns log lines."""
    counts = {v: n for v, n in counts.items() if n < PEELS}
    if not counts:
        return []
    assert dol.u32(PEEL_LOOP) == PEEL_LOOP_ORIG, f"0x{PEEL_LOOP:08X}: {dol.u32(PEEL_LOOP):08X}"
    a = Asm(code.here + (-code.here % 4))            # r12 free here (r0 is reloaded after the loop)
    a.lis("r12", ha(flag)).lbz("r12", lo(flag), "r12")
    for v in counts:
        a.cmpwi("r12", v).beq(f"n{v}")
    a.word(PEEL_LOOP_ORIG).b(PEEL_BACK)
    for v, n in counts.items():
        a.label(f"n{v}")
        a.cmplwi("r31", n - 1).b(PEEL_BACK)
    at = code.put(a.assemble(), 4)
    assert at == a.base
    dol.w32(PEEL_LOOP, Asm(PEEL_LOOP).b(at).assemble_word())
    return [f"banana peels: item {v}: {n}" for v, n in counts.items()]


def _frames_gate(dol, code, flag, site, orig, stock, frames):
    """At `site` (a store of r0 = the stock frame count), variants in `frames` ({variant: frames at 60 Hz}) store
    theirs instead (x stock[1] / stock[0] at 50 Hz: the stock game's own ratio). r12 free at the site."""
    assert dol.u32(site) == orig, f"0x{site:08X}: {dol.u32(site):08X}"
    a = Asm(code.here + (-code.here % 4))
    a.lis("r12", ha(flag)).lbz("r12", lo(flag), "r12")
    for v in frames:
        a.cmpwi("r12", v).beq(f"s{v}")
    a.b("store")
    for v, n in frames.items():
        a.label(f"s{v}")
        a.lbz("r12", -0x1658, "r13").cmpwi("r12", 0).li("r0", n).beq("store")
        a.li("r0", round(n * stock[1] / stock[0])).b("store")
    a.label("store")
    a.word(orig).b(site + 4)
    at = code.put(a.assemble(), 4)
    assert at == a.base
    dol.w32(site, Asm(site).b(at).assemble_word())


def slip_gate(dol, code, flag, frames):
    """frames: {variant: slip length at 60 Hz}: those items' slips last that long (5/6 of it at 50 Hz, as stock).
    Returns log lines."""
    frames = {v: n for v, n in frames.items() if n and n != SLIP_FRAMES[0]}
    if not frames:
        return []
    _frames_gate(dol, code, flag, SLIP_STORE, SLIP_STORE_ORIG, SLIP_FRAMES, frames)
    return [f"slip length: item {v}: {n} frames" for v, n in frames.items()]


def boo_gate(dol, code, flag, frames):
    """frames: {variant: frames the Boo stays while the ball is live, at 60 Hz (stock 180)}: its other state scales
    by the same ratio (stock 90), 50 Hz as stock. Returns log lines."""
    frames = {v: n for v, n in frames.items() if n and n != BOO_STORES[0][2][0]}
    if not frames:
        return []
    for site, orig, stock in BOO_STORES:
        _frames_gate(dol, code, flag, site, orig, stock,
                     {v: round(n * stock[0] / BOO_STORES[0][2][0]) for v, n in frames.items()})
    return [f"Boo: item {v}: {n} frames while the ball is live" for v, n in frames.items()]


# The burn look: after the Fireball's stun (0x801179F8), FUN_80117838 tells the player-state object (r13-0x110,
# vt+0x28) the hit fielder was hit with r5 = 1 (li r5,0x1 at BURN_ARG): the burning look; the Shell's hit
# (FUN_8011703c) passes 0 [C]. Items with it off pass 0.
BURN_ARG, BURN_ARG_ORIG = 0x80117A44, 0x38A00001


def burn_gate(dol, code, flag, off):
    """off: variants hit without the burning look. Returns log lines."""
    off = sorted(set(off))
    if not off:
        return []
    assert dol.u32(BURN_ARG) == BURN_ARG_ORIG, f"0x{BURN_ARG:08X}: {dol.u32(BURN_ARG):08X}"
    a = Asm(code.here + (-code.here % 4))            # r12 free (reloaded right after)
    a.lis("r12", ha(flag)).lbz("r12", lo(flag), "r12")
    for v in off:
        a.cmpwi("r12", v).beq("off")
    a.word(BURN_ARG_ORIG).b(BURN_ARG + 4)
    a.label("off")
    a.li("r5", 0).b(BURN_ARG + 4)
    at = code.put(a.assemble(), 4)
    assert at == a.base
    dol.w32(BURN_ARG, Asm(BURN_ARG).b(at).assemble_word())
    return [f"burn look off for item {', '.join(map(str, off))}"]


def log_lines(specs):
    return [f"item params: item {v} (on stock item {b}): " + ", ".join(f"{k} {x:g}" for k, x in vals.items())
            for v, b, vals in specs if vals]
