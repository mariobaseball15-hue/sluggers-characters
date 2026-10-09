"""Level 5 and 6 CPU (Nick, 2026-09-27): CPU levels past level 4. Level 6 is what level 5 was built as; level 5 will
be nerfed from it later (every gate checks FLAG != 0 today, so both play the same until then). Level 5 plays as level 4 underneath, plus FLAG, and
every CPU change (cpu_stars, cpu_subs, cpu_pitching, cpu_perfect) runs only at level 5; levels 1-4 are vanilla.
The menu (level5_menu.py) stores settings+0x10 = 4 for its "Superstar Level" button (the game never writes 4).

MANAGER. FUN_800C364C builds the CPU manager at the start of a match: `lwz r7,-0xB00(r13)` (settings), then
`lwz r6,0x10(r7)` at 0x800C3678 is the level it copies to both sides (+8 / +0xC; FUN_800C37D0 then overwrites a human
side). HOOK makes that load `bl` a stub (LR is already saved at 0x800C3658; r0 (1), r3, r4, r5, r7 are live and
kept; the stub uses only r6, r8-r12, ctr and cr0): level 4 -> r6 = 0 (level 4) and FLAG = 1 + the byte at FLAG + 1 (the menu: 1 for its Level 6
button, 0 for Level 5), so FLAG is 1 at level 5 and 2 at level 6; else FLAG = 0. Then it writes every
SWAPS record's level 5 bytes (FLAG 1) or its stock bytes (FLAG 0) into place, with dcbst / sync / icbi / isync so
the two code words among them (cpu_perfect's dive gates) reach the instruction cache. So cpu_perfect's bytes are
stock in the DOL and are only swapped in for a level 5 match, and they are reset at every match's start.
TIERS: FUN_800A94EC maps settings+0x10 through the words 0x8063FB78 (3,2,1,0,0): index 4 -> 3 (the hardest), like 0.

LEVEL 6 OVERRIDES (Nick, 2026-09-27: no superhuman reactions at level 6): SWAPS6 records are written after SWAPS,
at level 6 only, over some of its bytes (their stock copy = SWAPS's level 5 bytes); any other match rewrites those
addresses from SWAPS, so they reset. A SWAPS record may keep the stock bytes at level 5 when a SWAPS6 record
overrides it (cpu_perfect's track roll 0x80797233: 85% at level 5, its sweet-spot nerf; 100% at level 6). The stub uses r4 / r5 as its pass and copy flags and gives back their live
values at the site (r4 = r1 + 8, r5 = 0).

CHALLENGE (Nick, 2026-09-28: "make challenge mode bowser play as level 5 ... and allow for 5 and 6 for the other
teams"). Challenge sets settings+0x10 itself (3 - its difficulty +0xF2, FUN_802D9978's r9) and its own code reads it
(coins: FUN_801E5378 / 801EF8DC / 80205E34), so it is never 4 there; the stub decides from two more bytes instead,
only while the Challenge object *(r13-0x1224) exists (FUN_801D6BCC makes it, FUN_801D7294 frees it and zeroes the
pointer, so it is 0 outside Challenge):
  - CHAL_MATCH (FLAG + 3) = 1 / 2: this match was started from Challenge's level dialog with its Level 5 / 6 button
    (level5_menu: the dialog's answer writes CHAL_PICK, FLAG + 2, and the settings init FUN_802D9978 copies it here
    when called from that dialog's setup FUN_801DCE08, else 0) -> FLAG = 1 / 2, level 4 underneath;
  - else the CPU team's captain (settings+0x14 + team, the team port 0 is not on, +0x18; GetCaptain's table
    0x806318A8) is Bowser -> FLAG = 1 (level 5), level 4 underneath, whatever the difficulty.
settings+0x10 itself is left alone, so Challenge's coins and tables see the difficulty it chose.

GATE. A level 5 behaviour needs FLAG != 0 AND the CPU's own level at the hardest (each stub keeps its level 4 check),
so a level changed from the pause menu during a level 5 match falls back to stock.
Test: scripts/test_level5.py.
"""
import struct
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
from ppc import Asm, bc, branch, d_form, ha, lo  # noqa: E402

HOOK, HOOK_ORIG = 0x800C3678, 0x80C70010          # lwz r6,0x10(r7)
LEVEL5 = 4                                         # settings+0x10 for the menu's fifth button
TIERS_4, TIERS_4_STOCK, TIERS_4_NEW = 0x8063FB88, 0, 3
FLAG = None                                        # the flag byte's address, set by alloc()
CHAL_OBJ = -0x1224                                 # r13 offset: the Challenge object (0 outside Challenge)
CAPTAINS, BOWSER = 0x806318A8, 0x09                # GetCaptain (FUN_802D9910): u32 character id per captain index
CAPTAIN_OFF, PORT0_TEAM = 0x14, 0x18               # settings: captain index per team, port 0's team

SYNC, ISYNC = 0x7C0004AC, 0x4C00012C


def _x(op2, ra, rb):
    return (31 << 26) | (ra << 16) | (rb << 11) | (op2 << 1)


def alloc(data):
    """The flag byte (a word, zero at boot) in `data` (a charbuild Space). Call before any gated stub is made."""
    global FLAG
    FLAG = data.put(bytes(4), align=4)
    return FLAG


def level6():
    """The byte the menu sets for its Level 6 button (1) and clears for Level 5 (0): FLAG + 1."""
    assert FLAG is not None, "level5.alloc(data) first"
    return FLAG + 1


def chal_pick():
    """Challenge's level dialog answer: 0 a stock level, 1 Level 5, 2 Level 6 (FLAG + 2; level5_menu writes it)."""
    assert FLAG is not None, "level5.alloc(data) first"
    return FLAG + 2


def chal_match():
    """This Challenge match's pick (FLAG + 3): CHAL_PICK when the dialog's setup started the match, else 0."""
    assert FLAG is not None, "level5.alloc(data) first"
    return FLAG + 3


# The levels each CPU switch plays at (Nick, 2026-09-28: "per level switches"): {feature id: mask}, bit 1 level 5,
# bit 2 level 6 (FLAG is 1 at level 5 and 2 at level 6, so FLAG & mask says whether it plays this match); a
# feature not named plays at both (3). Set for one build by cpu_settings.configure (the patcher's CPU levels tab).
LEVELS_ON = {}
BOTH = 3


def gate(a, reg, skip, feature=None):
    """Branch to `skip` unless this match is a level `feature` plays at (FLAG != 0 for a feature at both levels,
    FLAG & mask for one level: andi., the same length). Clobbers `reg` (not r0) and cr0."""
    assert FLAG is not None, "level5.alloc(data) first"
    assert reg != 0, "r0 can't be a base register"
    mask = LEVELS_ON.get(feature, BOTH)
    a.lis(reg, ha(FLAG)).lbz(reg, lo(FLAG), reg)
    
    
    a.andi_(reg, reg, mask).beq(skip)


# PER-LEVEL CONSTANTS (Nick, 2026-09-29: "EVERYTHING in level 5 should be changeable"): a cpu_* module constant both
# levels used to share keeps level 6's value in its own name and may carry a level 5 value in the module's AT5 dict
# (cpu_settings.configure sets it for one build). pair() reads both; where they differ the generated code picks this
# match's value by FLAG (1: level 5, else level 6's) with pick / pick_addr; equal (every default build) emits today's
# words exactly.

TRACE = None                                       # a list: pick / pick_addr log (start, end, reg, v5, v6) (tests)


def _trace(a, start, reg, v5, v6):
    if TRACE is not None:
        TRACE.append((start, a.pc, reg, v5, v6))


def pair(module, name):
    """(level 4, level 5, level 6) values of a custom CPU constant."""
    six = getattr(module, name)
    five = getattr(module, "AT5", {}).get(name, six)
    four = getattr(module, "AT4", {}).get(name, five)
    return four, five, six


def pick(a, reg, *values):
    """Load a per-level immediate. Accepts old (v5,v6) calls or new (v4,v5,v6) calls."""
    assert FLAG is not None, "level5.alloc(data) first"
    assert reg != 0, "r0 can't be a base register"
    if len(values) == 2:
        v5, v6 = values; v4 = v5
    elif len(values) == 3:
        v4, v5, v6 = values
    else:
        raise TypeError("pick needs v5,v6 or v4,v5,v6")
    if v4 == v5 == v6:
        return a.li(reg, v6)
    start = a.pc
    l4, l5, done = (f"pick4_{start:x}", f"pick5_{start:x}", f"pickdone_{start:x}")
    a.lis(reg, ha(FLAG)).lbz(reg, lo(FLAG), reg)
    a.cmpwi(reg, 4).beq(l4).cmpwi(reg, 1).beq(l5)
    a.li(reg, v6).b(done)
    a.label(l5)
    a.li(reg, v5).b(done)
    a.label(l4)
    a.li(reg, v4)
    a.label(done)
    _trace(a, start, reg, v5, v6)
    return a


def pick4(a, reg, scratch, v4, v5, v6):
    """Load a level 4/5/6 immediate, using scratch (not r0/reg) for the flag."""
    assert FLAG is not None and scratch not in (0, reg)
    if v4 == v5 == v6:
        return a.li(reg, v6)
    a.lis(scratch, ha(FLAG)).lbz(scratch, lo(FLAG), scratch).li(reg, v6)
    a.cmpwi(scratch, 1).bne(a.pc + 8).li(reg, v5)
    a.cmpwi(scratch, 4).bne(a.pc + 8).li(reg, v4)
    return a


def pick_addr(a, reg, *values):
    """Load a level 4/5/6 address. Old (at5,at6) calls are also accepted."""
    assert FLAG is not None and reg != 0
    if len(values) == 2:
        at5, at6 = values; at4 = at5
    elif len(values) == 3:
        at4, at5, at6 = values
    else:
        raise TypeError("pick_addr needs 2 or 3 values")
    if at4 == at5 == at6:
        return a.load_addr(reg, at6)
    start = a.pc
    l4, l5, done = (f"picka4_{start:x}", f"picka5_{start:x}", f"pickadone_{start:x}")
    a.lis(reg, ha(FLAG)).lbz(reg, lo(FLAG), reg)
    a.cmpwi(reg, 4).beq(l4).cmpwi(reg, 1).beq(l5)
    a.load_addr(reg, at6).b(done)
    a.label(l5)
    a.load_addr(reg, at5).b(done)
    a.label(l4)
    a.load_addr(reg, at4)
    a.label(done)
    _trace(a, start, reg, at5, at6)
    return a


def swap_table(swaps, reset4=None):
    """SWAPS records: u32 address, u32 length, the bytes restored for a stock/level-4 match, then the level 5 bytes.
    reset4 may replace the first copy while apply still validates against the clean game's original bytes."""
    reset4 = reset4 or {}
    out = bytearray()
    for at, stock, new in swaps:
        base = reset4.get(at, stock)
        assert len(stock) == len(new) == len(base)
        pad = -len(stock) % 4
        out += struct.pack(">II", at, len(stock)) + base + bytes(pad) + new + bytes(pad)
    return bytes(out + bytes(4))


def manager_stub(at, table, table6):
    a = Asm(at)
    a.lwz(6, 0x10, 7)                              # the stock load
    a.lis(9, ha(FLAG)).addi(9, 9, lo(FLAG))
    a.li(8, 0).cmpwi(6, LEVEL5).bne("maybe4")
    a.li(6, 0).lbz(8, 1, 9).addi(8, 8, 1)          
    a.b("flag")
    a.label("maybe4")
    a.cmpwi(6, 0).bne("chal")
    a.li(8, 4)                                     
    a.label("chal")                                
    a.lwz(10, CHAL_OBJ, 13).cmpwi(10, 0).beq("flag")
    a.lbz(8, 3, 9).cmpwi(8, 0).bne("chal_on")      # CHAL_MATCH 1 / 2
    a.lbz(10, PORT0_TEAM, 7).li(11, CAPTAIN_OFF + 1).cmpwi(10, 1).bne("cpu_team")
    a.li(11, CAPTAIN_OFF)                          # port 0 on team 1: the CPU is team 0
    a.label("cpu_team")
    a.lbzx(10, 7, 11).cmplwi(10, 15).bgt("flag")   # the CPU team's captain index
    a.slwi(10, 10, 2).lis(11, ha(CAPTAINS)).addi(11, 11, lo(CAPTAINS)).lwzx(10, 11, 10)
    a.cmpwi(10, BOWSER).bne("flag")
    a.li(8, 1)                                     # Bowser: level 5
    a.label("chal_on")
    a.li(6, 0)
    a.label("flag")
    a.stb(8, 0, 9)
    a.li(4, 0)                                     # pass 0: SWAPS; pass 1 (level 6 only): SWAPS6
    a.lis(10, ha(table)).addi(10, 10, lo(table))
    a.li(5, 0).cmpwi(8, 1).beq("take_new").cmpwi(8, 2).bne("record")
    a.label("take_new")
    a.li(5, 1)                  
    a.label("record")
    a.lwz(11, 0, 10).cmpwi(11, 0).beq("table_done")   # r11 = address
    a.lwz(12, 4, 10).addi(9, 10, 8)                # r12 = length, r9 = the first copy
    a.cmpwi(5, 0).beq("copy")
    a.addi(6, 12, 3).rlwinm(6, 6, 0, 0, 29).add(9, 9, 6)   # the second copy
    a.label("copy")
    a.mtctr(12)
    a.addi(9, 9, -1).addi(12, 11, -1)
    a.label("byte")
    a.word(d_form(35, 6, 9, 1))                    # lbzu r6,1(r9)
    a.word(d_form(39, 6, 12, 1))                   # stbu r6,1(r12)
    a._emit(lambda pc: bc(pc, a.labels["byte"], 16, 0))   # bdnz
    a.word(_x(54, 0, 11)).word(_x(54, 0, 12))      # dcbst 0,r11 / dcbst 0,r12 (first and last byte's lines)
    a.word(SYNC)
    a.word(_x(982, 0, 11)).word(_x(982, 0, 12))    # icbi 0,r11 / icbi 0,r12
    a.word(ISYNC)
    a.lwz(12, 4, 10).addi(6, 12, 3).rlwinm(6, 6, 0, 0, 29)
    a.add(10, 10, 6).add(10, 10, 6).addi(10, 10, 8)   # next record: 8 + 2 * padded length
    a.b("record")
    a.label("table_done")
    a.cmpwi(4, 0).bne("done")
    a.cmpwi(8, 2).bne("done")
    a.li(4, 1).li(5, 1)                            # level 6: SWAPS6's level 6 bytes over SWAPS's
    a.lis(10, ha(table6)).addi(10, 10, lo(table6))
    a.b("record")
    a.label("done")
    a.lis(9, ha(FLAG)).lbz(8, lo(FLAG), 9)
    a.lwz(6, 0x10, 7)                              # the level again (r6 was the copy's scratch)
    a.cmpwi(8, 0).beq("out")
    a.li(6, 0)                                     # level 5 / 6 (the menu's 4, or Challenge's): level 4
    a.label("out")
    a.li(5, 0).addi(4, 1, 8)                       # the live r4 (r1 + 8) and r5 (0) the stub used
    a.blr()
    return a


def apply(dol, code, data, swaps, swaps6=(), reset4=None):
    """Hook the CPU manager in `dol`: the stub in `code`, the swap tables in `data` (charbuild Spaces). `swaps`:
    [(address, stock bytes, level 5 / 6 bytes)], checked against the DOL. `swaps6`: [(address, level 5 bytes, level 6
    bytes)], written over SWAPS at level 6 only; every address must be in `swaps` (so any other match resets it).
    Returns log lines."""
    assert FLAG is not None, "level5.alloc(data) first"
    got = dol.u32(HOOK)
    assert got == HOOK_ORIG, f"0x{HOOK:08X}: 0x{got:08X}, expected 0x{HOOK_ORIG:08X}"
    got = dol.u32(TIERS_4)
    assert got == TIERS_4_STOCK, f"0x{TIERS_4:08X}: 0x{got:08X}, expected 0"
    reset4 = reset4 or {}
    for at, stock, new in swaps:
        assert dol.read(at, len(stock)) == stock, f"0x{at:08X} is not stock"
        if at in reset4:
            assert len(reset4[at]) == len(stock), f"0x{at:08X}: bad level 4 reset length"
    level5_bytes = {at: new for at, stock, new in swaps}
    for at, five, six in swaps6:
        assert level5_bytes.get(at) == five, f"0x{at:08X}: a level 6 override must match a SWAPS record's level 5 bytes"
    overridden = {at for at, _, _ in swaps6}
    for at, stock, new in swaps:
        assert stock != new or at in overridden or reset4.get(at, stock) != stock, \
            f"0x{at:08X}: level 5 bytes = stock, level 4 unchanged and no level 6 override (a no-op)"
    table = data.put(swap_table(swaps, reset4), align=4)
    table6 = data.put(swap_table(swaps6), align=4)
    at = code.here + (-code.here % 4)
    assert code.put(manager_stub(at, table, table6).assemble(), align=4) == at
    dol.w32(HOOK, branch(HOOK, at, link=True))
    dol.w32(TIERS_4, TIERS_4_NEW)
    return [f"level 5: settings level 4 plays as level 4 with the flag at 0x{FLAG:08X} (0x{HOOK:08X} -> 0x{at:08X}); "
            f"{len(swaps)} byte swaps at match start (table 0x{table:08X}), {len(swaps6)} more at level 6 (0x{table6:08X}); "
            f"0x{TIERS_4:08X} tier 0 -> 3"]
