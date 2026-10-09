"""Level 6 CPU dives: dive only when a normal play can't make the catch / pickup and a dive can (Nick, 2026-09-27).
LEVEL 6 ONLY (level5.FLAG byte == 2, fielder level byte +0x2E == 0: the CPU side); levels 1-5 run the stock
instructions, and the level 5 data (cpu_perfect: attempt table 100%, gates 0x800E2750 / 0x800E25B8 widened) stays
in place at level 6: those gates only *request* a dive, the stub below decides. Applied by cpu_item_defense.apply.

How a CPU dive happens [C]: FUN_800E246C (the chaser only) writes ai+0xC8 = 2, the CPU pad slot 4 action press,
at 0x800E2648/264C (fly ball: frames-to-land game+0x2A46 < 20 and the run to the landing spot too short) and at
0x800E2808/280C (grounder / liner: the ball line F+0x144 outside the standing reach F+0x184). The press flags are
per-frame pulses (cleared in FUN_800CF554). FUN_8011F748 -> FUN_801222D0 -> FUN_801225DC then asks the dive planner
FUN_801232B0(f1 = dive reach, r3 = F, r4 = 0 / 1 Super Dive, r5 = &frame): scanning ball-path frames (path[i] =
game+0x42C + i*0x14, x / y / z / dist^2 / height; path[0] is the ball now, re-predicted every frame by 800B38C8 at
the tail of the ball update 800AC828) it returns 3 at the first frame the run alone reaches the ball point
(|ball - F| - run(i) <= 0, run(i) = FUN_80116734, the same run model the AI uses), 0 at the first frame a dive
reaches it (|ball - F| < reach + run(i) * 0x80625D38[mode*0x24 + type*0xC], 1.0 / 1.2 Super Dive), 2 for a dive
that falls short (within +50 / 60 more: a whiff), 1 for nothing. 801225DC dives on 0 (and whiffs on 2); on 3 it
does the ordinary reach catch (FUN_801201E0 state 7 + 80121830, as the standing predictor 80121520). So stock
dives (a) whenever the dive point comes on an earlier frame than the run point, though running would still have
got there, and (b) short, on result 2.

Level 6 (hook at both `li r0,2` sites, 0x800E2648 and 0x800E2808; r28 = ai, r30 = F, r31 = game): the press is
written only when DIVE_OK(F):
  0. the level 6 attack has priority (Nick: attack when a teammate is near and it will hit; dive only when there is
     no attack to make): no press while cpu_item_defense's attack is planned or in progress for this fielder, read
     from the debug block defense_dbg (FRAME within 1 of now = *(r13-0x1684)+2, PHASE 1..4, CHASER == F+0x21C).
     Within 1, not == now: the dive press (800E246C, CDefense vtable 0x80640608 +0x10) runs BEFORE the attack
     decision (800E2830, +0x14) in the same frame: 800E21EC calls them back to back for the chaser (bctrl 800E2438,
     then 800E244C) [C], so the block holds the previous frame's decision when this runs. Writes defense_dbg AUX1
     = (now << 16) | 1 when it suppresses the dive, (now << 16) otherwise (only when a level 6 CPU dive press came).
     Why it matters (both presses in one frame) [C order]: 800D5A38 runs per fielder 8010BCB0 then 8010B200.
     8010BCB0 -> 8011F748 (skips its whole catch block when +0x265 != 0) -> 801222D0 (slot +0xA8 set) -> 801225DC
     takes the dive first; the attack press ai+0xD4 is read later in 8010B200's mover (80125238 / 80125F8C ->
     80112BC4 -> 8011D5F4). So a same-frame dive wins; if 8011D5F4 still runs after it, it cancels the dive's
     committed catch (+0x2AC = 0) and starts +0x265 on top of a dive [I]. Once +0x265 is set, dive presses are dead.
  1. dive reach as 801225DC picks it: fielding ability (vtable +0x3C) 3..8 -> 0x80625DA8[ab-3] (6.0; stock also
     asks FUN_80180AD8(stars, cost 0x8062BD40[0] = 0), taken as passing [I]), else F+0x1A0; ability 1 -> mode 1.
  2. the planner must return 0 (a dive catches it, frame fd). 1, 2, 3, 4 -> no press.
  3. no frame f in [0, LIMIT) where the normal play gets it: ball height path[f].h <= F+0x190 (the standing catch's
     height reach, 80121050) and |ball - F| <= run(f) * chem + F+0x184 (the standing catch's horizontal reach;
     chem = the planner's slot multiplier ai+slot*0x20+0xC when +0x18 is this fielder). LIMIT = frames-to-land
     game+0x2A46 while the ball hasn't bounced (a catch must be in the air: a dive that catches beats a pickup),
     else fd + GRACE + 1 (a pickup that late is no slower than the dive).
"""
import struct
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
import defense_dbg as dbg  # noqa: E402
import level5  # noqa: E402
from ppc import Asm, branch, ha, lo  # noqa: E402

HOOKS = ((0x800E2648, "fly"), (0x800E2808, "ground"))   # li r0,0x2 (then stb r0,0xC8(r28))
ORIG = 0x38000002
OUT = 0x800E2810                                          # 800E246C's epilogue
PLANNER = 0x801232B0
RUN = 0x80116734
SPECIAL_REACH = 0x80625DA8                                # abilities 3..8
DEFENSE = (-0x1D14, -0x1D10, -0x1D18, -0x1D1C)
GAME = -0x1D94
TICK = -0x1684                                            # r13: *(..)+2 = frames since contact
GRACE = 15      # frames: the dive animation (record 0x82 -> sequence 19: 15 frames for 45 of 63 characters,
                # dt_na.dat file 6) before the get-up; INFERRED as the dive's minimum time cost, UNMEASURED in game

F_LEVEL, F_X, F_Z, F_ID, F_SLOT = 0x2E, 0x4, 0xC, 0x21C, 0x2C9
F_HREACH, F_VREACH, F_DIVE_REACH = 0x184, 0x190, 0x1A0
G_BOUNCED, G_LAND = 0x2A4E, 0x2A46
P_X, P_Z, P_H, STRIDE, LAST = 0x42C, 0x434, 0x43C, 0x14, 0x1DF

# frame: 0x8 planner frame, 0x10 chem, 0x14 dx, 0x18 dz, 0x1C/0x20/0x24 run outputs, 0x28 ONE (1.0)
SIZE = 0x50


def gate6(a, skip, reg=12):
    a.lis(reg, ha(level5.FLAG)).lbz(reg, lo(level5.FLAG), reg).cmpwi(reg, 0).beq(skip)   # levels 5 and 6


def body(a, one):
    """DIVE_OK(r3 = F) -> r3 = 1 press the dive (also: not level 6), 0 don't. Own frame; saves r28-r31."""
    a.stwu(1, -SIZE, 1).mflr(0).stw(0, SIZE + 4, 1)
    a.stw(31, SIZE - 4, 1).stw(30, SIZE - 8, 1).stw(29, SIZE - 0xC, 1).stw(28, SIZE - 0x10, 1)
    a.mr(31, 3).li(3, 1)
    gate6(a, "ret")
    a.lbz(0, F_LEVEL, 31).cmpwi(0, 0).bne("ret")
    # 0. the attack has priority (the block holds the previous frame's decision, see the docstring)
    a.load_addr(6, dbg.ADDR).lwz(4, TICK, 13).lha(4, 2, 4).slwi(5, 4, 16)
    a.lha(0, dbg.FRAME, 6).subf(0, 0, 4).cmplwi(0, 1).bgt("free")      # now - FRAME in {0, 1}
    a.lbz(3, dbg.PHASE, 6).addi(3, 3, -1).cmplwi(3, 3).bgt("free")    # PHASE 1..4
    a.lbz(0, dbg.CHASER, 6).lbz(3, F_ID, 31).cmpw(0, 3).bne("free")
    a.ori(5, 5, 1).stw(5, dbg.AUX1, 6).li(3, 0).b("ret")
    a.label("free")
    a.stw(5, dbg.AUX1, 6)
    # 1. dive reach / planner mode, as 801225DC
    a.lwz(12, 0, 31).lwz(12, 0x3C, 12).mtctr(12).mr(3, 31).bctrl()
    a.lfs(1, F_DIVE_REACH, 31).li(4, 0)
    a.cmpwi(3, 1).bne("notsd").li(4, 1).b("plan")
    a.label("notsd")
    a.addi(0, 3, -3).cmplwi(0, 5).bgt("plan")
    a.slwi(0, 0, 2).load_addr(5, SPECIAL_REACH).add(5, 5, 0).lfs(1, 0, 5)
    a.label("plan")
    a.mr(3, 31).addi(5, 1, 0x8).bl(PLANNER)
    a.clrlwi(3, 3, 24).cmpwi(3, 0).li(3, 0).bne("ret")               # 2. only "a dive catches it"
    # 3. the normal play's window
    a.lwz(29, GAME, 13).lwz(30, 0x8, 1)                              # r30 = fd
    a.lha(0, G_BOUNCED, 29).cmpwi(0, 0).bne("bounced")
    a.lha(28, G_LAND, 29).cmpwi(28, 0).bgt("lim")
    a.label("bounced")
    a.addi(28, 30, GRACE + 1)
    a.label("lim")
    a.cmpwi(28, LAST + 1).ble("lim2").li(28, LAST + 1)
    a.label("lim2")
    a.load_addr(5, one).lfs(0, 0, 5).stfs(0, 0x10, 1)               # chem = 1.0 unless the slot boosts him
    for off in DEFENSE:
        a.lwz(4, off, 13).cmpwi(4, 0).bne("ai")
    a.b("scan")
    a.label("ai")
    a.lbz(5, F_SLOT, 31).slwi(5, 5, 5).add(4, 4, 5)
    a.lha(0, 0x18, 4).lbz(5, F_ID, 31).cmpw(0, 5).bne("scan")
    a.lfs(0, 0xC, 4).stfs(0, 0x10, 1)
    a.label("scan")
    a.li(30, 0)
    a.label("loop")
    a.cmpw(30, 28).bge("dive")
    a.mulli(0, 30, STRIDE).add(4, 29, 0)
    a.lfs(0, P_H, 4).lfs(1, F_VREACH, 31).fcmpo(0, 1).bgt("next")   # over his head: not a normal play
    a.lfs(1, P_X, 4).lfs(0, F_X, 31).fsubs(1, 1, 0).stfs(1, 0x14, 1)
    a.lfs(2, P_Z, 4).lfs(0, F_Z, 31).fsubs(2, 2, 0).stfs(2, 0x18, 1)
    a.mr(3, 31).mr(4, 30).addi(5, 1, 0x1C).addi(6, 1, 0x20).addi(7, 1, 0x24).bl(RUN)
    a.lfs(1, 0x14, 1).lfs(2, 0x18, 1).fmuls(3, 1, 1).fmadds(3, 2, 2, 3)          # d^2
    a.lfs(0, 0x24, 1).lfs(4, 0x10, 1).fmuls(0, 0, 4)
    a.lfs(4, F_HREACH, 31).fadds(0, 0, 4).fmuls(0, 0, 0)                          # (run*chem + reach)^2
    a.fcmpo(3, 0).ble("normal")
    a.label("next")
    a.addi(30, 30, 1).b("loop")
    a.label("normal")
    a.li(3, 0).b("ret")
    a.label("dive")
    a.li(3, 1)
    a.label("ret")
    a.lwz(0, SIZE + 4, 1).mtlr(0)
    a.lwz(31, SIZE - 4, 1).lwz(30, SIZE - 8, 1).lwz(29, SIZE - 0xC, 1).lwz(28, SIZE - 0x10, 1)
    a.addi(1, 1, SIZE).blr()


def stubs(at, one):
    """Two entries (one per hook), then the shared body. Returns (asm, [entry addresses])."""
    a = Asm(at)
    entries = []
    for i, (hook, _) in enumerate(HOOKS):
        entries.append(a.pc)
        a.mr(3, 30).bl("body").cmpwi(3, 0).bne(f"press{i}").b(OUT)
        a.label(f"press{i}")
        a.word(ORIG).b(hook + 4)
    a.label("body")
    body(a, one)
    return a, entries


def apply(dol, code, data):
    """Hook both dive presses of 800E246C; code in `code`, the 1.0 constant (and defense_dbg's block) in `data`. Needs
    level5.alloc first."""
    assert level5.FLAG is not None, "level5.alloc(data) first"
    for hook, _ in HOOKS:
        got = dol.u32(hook)
        assert got == ORIG, f"0x{hook:08X}: 0x{got:08X}, expected 0x{ORIG:08X}"
    dbg.alloc(data)                                       # the attack's debug block (idempotent)
    one = data.put(struct.pack(">f", 1.0), align=4)
    at = code.here + (-code.here % 4)
    a, entries = stubs(at, one)
    blob = a.assemble()
    assert code.put(blob, align=4) == at
    for (hook, _), e in zip(HOOKS, entries):
        dol.w32(hook, branch(hook, e))
    return [f"cpu dive (level 6): no dive while the attack is planned; else dive only when the run can't get it and a dive can: 0x{HOOKS[0][0]:08X}, "
            f"0x{HOOKS[1][0]:08X} -> 0x{at:08X} ({len(blob)} bytes code, 4 bytes data)"]
