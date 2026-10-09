"""CPU cursed ball (Nick, 2026-09-29: "can we allow people to enable cpu cursed ball?"): a switch, off by default.

FUN_800BA1B8 (the batter's hit power) scales it by the pitch-quality lerp (0x80627A78, docs/cpu-ai.md 2.3) only when
(pitcher +0x140 == 3 && pitcher +0x13B != 0) || pitcher +0x1BD == 3. +0x140 == 3 is written only on the human pitch
path, so a CPU charged pitch never gets it: a built-in CPU handicap. With the switch on, at the levels it plays at
(level5.gate), the +0x140 test is skipped: every charged pitch (+0x13B != 0) is cursed, the CPU's too, as the known
fix 0x800BA38C `bne` -> `nop` does for all levels. A human's charged pitch already passes the +0x140 test, so the
change is the CPU's pitches.
HOOK replaces 0x800BA38C (`bne 0x800BA39C`, after `lbz r0,0x140(r3); cmplwi r0,3`) with a branch to a stub: at the
level, on to 0x800BA390 (the +0x13B test); else the compare again (level5.gate clobbers cr0; r0 still holds +0x140)
and the stock bne. Uses r12 and cr0 (free: 0x800BA390 reloads r0 and compares).
Test: scripts/test_cpu_cursed.py.
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
import level5  # noqa: E402
from ppc import Asm, branch  # noqa: E402

HOOK, HOOK_ORIG = 0x800BA38C, 0x40820010           # bne 0x800BA39C
CHARGED, NOT_140 = 0x800BA390, 0x800BA39C          # the +0x13B test; the +0x1BD test


def stub(at):
    a = Asm(at)
    level5.gate(a, 12, "stock", "cpu-cursed-ball")
    a.b(CHARGED)                                   # at the level: any charged pitch
    a.label("stock")
    a.cmplwi(0, 3).bne("not")
    a.b(CHARGED)
    a.label("not")
    a.b(NOT_140)
    return a


def apply(dol, code):
    """Hook 0x800BA38C in `dol`; the stub goes in `code` (a charbuild Space). Returns log lines."""
    assert level5.FLAG is not None, "level5.alloc(data) first"
    got = dol.u32(HOOK)
    assert got == HOOK_ORIG, f"0x{HOOK:08X}: 0x{got:08X}, expected 0x{HOOK_ORIG:08X}"
    at = code.here + (-code.here % 4)
    blob = stub(at).assemble()
    assert code.put(blob, align=4) == at
    dol.w32(HOOK, branch(HOOK, at))
    return [f"cpu cursed ball (levels 5 / 6): every charged pitch gets the cursed-ball power multiplier, the CPU's too "
            f"(0x{HOOK:08X} -> 0x{at:08X}, {len(blob)} bytes)"]
