"""Level 5 CPU charge timing (Nick, 2026-09-27): a level 5 CPU batter that charges is fully charged, mid-window,
on the frame it swings.

How a charge works (FUN_800BC698, every batter): batter +0xBF 1 = building; +0x94 (s16) counts charged frames while
building; +0x90 (60 for everyone, table 0x8062A00C) is full, +0x92 (60 + a per-character grace of 20..60) the last
full frame, after which the power factor +0x7C decays toward 0.5. The swing freezes it (+0xBF 2) and the hit power
uses +0x7C, so charged frames at the swing should be C = (+0x90 + +0x92) / 2, the middle of the full window.
Stock CPU (FUN_800C4FF4, while brain +0x3A == 1 "charge"): it starts when a target frame (the last pitch's timing, or
the windup + 110/130) comes, or when the pitcher's countdown +0x100 is under 8 (7 at 50 Hz), which is what usually
fires at levels 4 and 5: about 8 frames before release, so a 44-frame fastball meets a ~78% charge.

HOOK 0x800C5058 (`lbz r0,0x34(r3)`, the first instruction of that start block; r3 = r29 = the batter AI, r30 = the
batter, r31 = the pitcher; r0, r3, r4, r5 are free until 0x800C50F0 reloads them). At level 5 (level5.FLAG, AI
+0x39 == 3), instead of the stock block:
- not charging yet (+0xBF == 0): start now (+0xBF = +0xB6 = 1, as the stock block does);
- on flight frame 2 (f = *(s16 *)(*(r13-0x1684) + 4); FUN_800C51E4 set the swing frame AI +0x45 on frame 1), while
  building: +0x94 = max(0, C - E), E = AI +0x45 + 1 - f the frames left before the swing (FUN_800C4FF4 swings on
  f == +0x45 + 1). So the charge is exact whatever the pitch speed or how long a human held the pitch;
then on to 0x800C50F0. Otherwise the stock instruction and back to 0x800C505C.
A CPU batter's charge meter, if one is drawn, can drop once at flight frame 2 (not checked).
Test: scripts/test_cpu_charge.py.
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
import level5  # noqa: E402
from ppc import Asm, branch  # noqa: E402

HOOK, HOOK_ORIG = 0x800C5058, 0x88030034           # lbz r0,0x34(r3)
AFTER = 0x800C50F0                                 # past the stock start block
TICK, FRAME = -0x1684, 4                           # *(r13-0x1684) + 4: frames since release (s16)
SWING_AT = 0x45                                    # AI: the swing is on frame +0x45 + 1
CHARGE, SWING_TYPE, FRAMES, FULL, LAST = 0xBF, 0xB6, 0x94, 0x90, 0x92   # batter


def stub(at):
    a = Asm(at)
    level5.gate(a, 4, "stock", "cpu-charge-timing")
    a.lbz(0, 0x39, 29).cmpwi(0, 3).bne("stock")   # the hardest tier
    a.lbz(0, CHARGE, 30).cmpwi(0, 0).bne("fix")
    a.li(0, 1).stb(0, CHARGE, 30).stb(0, SWING_TYPE, 30)   # start at once
    a.label("fix")
    a.lbz(0, CHARGE, 30).cmpwi(0, 1).bne("out")   # still building
    a.lwz(3, TICK, 13).lha(4, FRAME, 3).cmpwi(4, 2).bne("out")
    a.lbz(5, SWING_AT, 29).cmpwi(5, 0).beq("out")
    a.addi(5, 5, 1).subf(5, 4, 5)                  # E = +0x45 + 1 - f
    a.lha(0, FULL, 30).lha(3, LAST, 30).add(0, 0, 3).rlwinm(0, 0, 31, 1, 31)   # C = (full + last) / 2
    a.subf(0, 5, 0).cmpwi(0, 0).bge("set")         # C - E
    a.li(0, 0)
    a.label("set")
    a.sth(0, FRAMES, 30)
    a.label("out")
    a.b(AFTER)
    a.label("stock")
    a.word(HOOK_ORIG)
    a.b(HOOK + 4)
    return a


def apply(dol, code):
    """Hook FUN_800C4FF4's charge start in `dol`; the stub goes in `code` (a charbuild Space). Returns log lines."""
    got = dol.u32(HOOK)
    assert got == HOOK_ORIG, f"0x{HOOK:08X}: 0x{got:08X}, expected 0x{HOOK_ORIG:08X}"
    at = code.here + (-code.here % 4)
    blob = stub(at).assemble()
    assert code.put(blob, align=4) == at
    dol.w32(HOOK, branch(HOOK, at))
    return [f"cpu charge timing (level 5): charge at once, then exactly mid-full-window at the swing "
            f"(0x{HOOK:08X} -> 0x{at:08X}, {len(blob)} bytes)"]
