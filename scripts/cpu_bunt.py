"""Level 6 CPU never bunts (Nick, 2026-09-27).

FUN_800C4824 is the CPU batter's bunt decision (Bb::CBComBat; called from FUN_800C41D4 at an at-bat's start, after
the level tier +0x39 is set): it clears +0x31 (the at-bat-start flag) and +0x3B (the bunt: 1 sacrifice, 3 squeeze),
then rolls a sacrifice bunt (0x806249A8, class x level; the squeeze can't happen, docs/cpu-ai.md 3.9).
HOOK replaces its first word (`stwu r1,-0x20(r1)`) with a branch to a stub: at level 6 (level5.FLAG byte 2) with the
AI at the hardest tier (r3 +0x39 == 3) it clears +0x31 and +0x3B and returns before the frame (no bunt, no rand
call); else the stock `stwu` and back to 0x800C4828. r0, r12 and cr0 are free at a function's entry.
Test: scripts/test_cpu_bunt.py.
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
import level5  # noqa: E402
from ppc import Asm, branch, ha, lo  # noqa: E402

HOOK, HOOK_ORIG = 0x800C4824, 0x9421FFE0           # stwu r1,-0x20(r1)
START, BUNT, TIER = 0x31, 0x3B, 0x39               # AI (r3)


def stub(at):
    a = Asm(at)
    level5.gate(a, 12, "stock", "cpu-no-bunts")   # levels 5 and 6 (Nick: level 5 = level 6 but for its listed nerfs)
    a.lbz(12, TIER, 3).cmpwi(12, 3).bne("stock")
    a.li(0, 0).stb(0, START, 3).stb(0, BUNT, 3).blr()
    a.label("stock")
    a.word(HOOK_ORIG)
    a.b(HOOK + 4)
    return a


def apply(dol, code):
    """Hook FUN_800C4824 in `dol`; the stub goes in `code` (a charbuild Space). Returns log lines."""
    assert level5.FLAG is not None, "level5.alloc(data) first"
    got = dol.u32(HOOK)
    assert got == HOOK_ORIG, f"0x{HOOK:08X}: 0x{got:08X}, expected 0x{HOOK_ORIG:08X}"
    at = code.here + (-code.here % 4)
    blob = stub(at).assemble()
    assert code.put(blob, align=4) == at
    dol.w32(HOOK, branch(HOOK, at))
    return [f"cpu no bunts (level 6): FUN_{HOOK:08X} returns without a bunt (0x{HOOK:08X} -> 0x{at:08X}, {len(blob)} bytes)"]
