"""CPU star moves (Nick, 2026-09-27): CPU batters with weak charge power star-swing more often, and the CPU pitcher
never throws a star pitch. Two features: "cpu-star-swings" and "cpu-no-star-pitches" (docs/cpu-ai.md 3.8, 4.5).
Level 5 only (level5.py: FLAG set and the CPU at its hardest tier, 3); every other level is stock.

STAR SWINGS. FUN_800C5778 is the CPU batter's star-swing decision (Bb::CBComBat, once per pitch from FUN_800C41D4).
After its gates (star skills, the option, the meter, level tier != 0: level 1 never star-swings) it rolls
rand(100) < 0x80624778[class * 5 + situation] + 0x80797210[tier * 2 + risp]. The sum is made at 0x800C5930
(`add r0,r25,r0`) and sign-extended into r25 at 0x800C5934 (`extsb r25,r0`), then compared with the roll at
0x800C593C (`cmpw r3,r25`). HOOK replaces the extsb with a branch to a stub that does the extsb, then adds
(100 - min(charge power, 100)) / 2 in a full register (a byte sum would wrap past 127) and branches back to 0x800C5938.
r29 is the batter (the function's `lha r27,0x28(r29)` reads its character id); its charge power is the u16 at +0xA6,
copied from the stats row (+0x12) in FUN_800B98AC, so stat edits and chemistry boosts carry through.
Stock charge power runs 1 (Waluigi, +49) to 98 (Bowser, +1); the median, 65, gets +17. A human batter never runs this.
ALWAYS (Nick, 2026-09-27): a level 5 CPU batter (tier +0x39 == 3, r26 = the batter AI) with charge power under
STAR_CP (60) whose team has at least 2 stars (STAR_METER) always star-swings (r25 = 100). The meter is the s16 at
*(r13-0x1540) + team*2 with team = FUN_801319BC()+0x2C, what FUN_800C5778 itself passes to FUN_80180AD8. The stub
calls FUN_801319BC (LR is saved in FUN_800C5778's frame) and then restores the rand arguments r3 = *(r13-0x1578) and
r4 = 100 that 0x800C5918 / 0x800C5920 loaded. (Replaces the earlier 5-star and under-40 / 75% rules.)

LEVEL 6 (Nick, 2026-09-27: "85 and higher should never do star swings, 75 and higher should very rarely, and the
whole probabilities should be based on charge power not class"): at FLAG 2, past the ALWAYS rule, the chance is
level6_chance(charge power) alone (no class, situation or level table): 0 at CP6_NEVER (85) and up, CP6_RARE_PCT
(2) from CP6_RARE (75) to 84, else CP6_TOP - charge power (70: 10, 60: 20, 40: 40). Level 5 keeps the bonus.
Nick, 2026-09-29 (Yellow Toad, charge power 65, star-swung ~half his at-bats at 15% a pitch): "get rid of that, let's
have charge people charge": CP6_NEVER and CP6_RARE 60 (= STAR_CP), so charge power 60+ never star-swings; under 60 as
before (2+ stars: always, else CP6_TOP - charge power).

NO STAR PITCHES. FUN_800C710C is the CPU pitcher's star-pitch decision (callers FUN_800C6780 and the tutorial's
FUN_800C795C); on 0 both call the normal pitch pick FUN_800C7378. Its first word branches to a stub: at level 5
(FLAG, brain r3 +0x1A == 3) `li r3,0; blr` before its stack frame, so nothing else in it runs (the rand call is
skipped); else the stock `stwu r1,-0x30(r1)` and back to 0x800C7110. It leaves the build alone when cpu_star_pitch.py
(the test mode that forces a star pitch every pitch) already patched it, and cpu_star_pitch.apply puts the first word
back if this ran first.
Test: scripts/test_cpu_stars.py.
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
import level5  # noqa: E402
from ppc import Asm, branch, ha, lo  # noqa: E402

HOOK, HOOK_ORIG = 0x800C5934, 0x7C190774           # extsb r25,r0
BACK = HOOK + 4
CHARGE_POWER = 0xA6                                # batter +0xA6, u16
MAX_BONUS = 50                                     # at charge power 0; 0 at 100 and above
STAR_METER, STAR_CP = 100, 60                      # 2+ stars and charge power under 60: always (Nick)
TEAM_OF, METER, RNG = 0x801319BC, -0x1540, -0x1578
CP6_NEVER, CP6_RARE, CP6_RARE_PCT, CP6_TOP = 60, 60, 2, 80   # level 6: by charge power alone (Nick)
AT4 = {}
AT5 = {}                                           # level 5's own values of the above (cpu_settings; level5.pair)
CP6 = ("CP6_NEVER", "CP6_RARE", "CP6_RARE_PCT", "CP6_TOP")

DECIDE = 0x800C710C
DECIDE_ORIG = (0x9421FFD0, 0x7C0802A6)             # stwu r1,-0x30(r1); mflr r0
FORCED_ROLL, NOP = 0x800C7330, 0x60000000          # cpu_star_pitch.FORCE's last write


def bonus(charge_power):
    """The points the stub adds for a charge power (what the assembly computes)."""
    return (100 - min(charge_power, 100)) * MAX_BONUS // 100


def level6_chance(charge_power):
    """The level 6 star-swing chance (%) past the ALWAYS rule (what the assembly computes)."""
    if charge_power >= CP6_NEVER:
        return 0
    if charge_power >= CP6_RARE:
        return CP6_RARE_PCT
    return CP6_TOP - charge_power


def swing_stub(at):
    assert MAX_BONUS == 50, "the stub halves (100 - charge power)"
    a = Asm(at)
    a.word(HOOK_ORIG)                              # extsb r25,r0: the stock chance
    level5.gate(a, 12, "back", "cpu-star-swings")                     # level 5 only (r0 and r12 are free after the extsb)
    a.lbz(0, 0x39, 26).cmpwi(0, 3).bne("back")    # at the hardest tier
    cp4, cp5, cp6 = level5.pair(sys.modules[__name__], "STAR_CP")
    a.lhz(0, CHARGE_POWER, 29)
    if cp4 == cp5 == cp6:
        a.cmplwi(0, STAR_CP).bge("bonus")
    else:                                          # level 5's own line (r12 is free here)
        level5.pick(a, 12, cp4, cp5, cp6).cmpw(0, 12).bge("bonus")
    a.bl(TEAM_OF)                                  # r3 = game state; +0x2C = batting team
    a.lbz(0, 0x2C, 3).slwi(0, 0, 1)
    a.lwz(12, METER, 13).add(12, 12, 0).lha(11, 0, 12)   # r11 = the batting team's meter
    a.lwz(3, RNG, 13).li(4, 100)                   # the rand arguments the call clobbered
    a.cmpwi(11, STAR_METER).blt("bonus")
    a.li(25, 100).b(BACK)                          # charge power under STAR_CP with 2+ stars: always
    a.label("bonus")
    a.lis(12, ha(level5.FLAG)).lbz(12, lo(level5.FLAG), 12).cmpwi(12, 0).beq("l5")   # levels 5 and 6: the level 6 rule
    four, five, six = zip(*(level5.pair(sys.modules[__name__], n) for n in CP6))
    
    if four != six or five != six:
        a.cmpwi(12, 4).beq("l6_4").cmpwi(12, 1).beq("l6_5")
    variants = [("", six)]
    if four != six:
        variants.append(("_4", four))
    if five != six:
        variants.append(("_5", five))
    for tag, (never, rare, rare_pct, top) in variants:
        a.label("l6" + tag)
        a.lhz(0, CHARGE_POWER, 29)
        a.cmplwi(0, never).blt("l6_a" + tag)
        a.li(25, 0).b(BACK)
        a.label("l6_a" + tag)
        a.cmplwi(0, rare).blt("l6_b" + tag)
        a.li(25, rare_pct).b(BACK)
        a.label("l6_b" + tag)
        a.li(12, top).subf(25, 0, 12).b(BACK)
    a.label("l5")
    a.lhz(0, CHARGE_POWER, 29)
    a.cmplwi(0, 100).ble("under")
    a.li(0, 100)
    a.label("under")
    a.li(12, 100).subf(0, 0, 12)                   # r0 = 100 - min(cp, 100)
    a.rlwinm(0, 0, 31, 1, 31)                      # / 2
    a.add(25, 25, 0)
    a.label("back")
    a.b(BACK)
    return a


def pitch_stub(at):
    a = Asm(at)
    level5.gate(a, 12, "stock", "cpu-no-star-pitches")   # (r0, r11, r12 and cr0 are free at a function's entry)
    a.lbz(12, 0x1A, 3).cmpwi(12, 3).bne("stock")  # brain tier 3
    a.li(3, 0).blr()                               # no star pitch
    a.label("stock")
    a.word(DECIDE_ORIG[0])                         # stwu r1,-0x30(r1)
    a.b(DECIDE + 4)
    return a


def apply_swings(dol, code):
    """Hook the CPU batter's star-swing chance; the stub goes in `code` (a charbuild Space). Returns log lines."""
    got = dol.u32(HOOK)
    assert got == HOOK_ORIG, f"0x{HOOK:08X}: 0x{got:08X}, expected 0x{HOOK_ORIG:08X}"
    at = code.here + (-code.here % 4)
    assert code.put(swing_stub(at).assemble(), align=4) == at
    dol.w32(HOOK, branch(HOOK, at))
    return [f"cpu star swings: + (100 - charge power) / 2 to the CPU batter's star-swing chance at level 5; charge power under {STAR_CP} "
            f"with 2+ stars: always (0x{HOOK:08X} -> 0x{at:08X}; Waluigi +{bonus(1)}, Bowser +{bonus(98)})"]


def apply_no_pitches(dol, code):
    """The level 5 CPU pitcher never star-pitches; the stub goes in `code`. Returns log lines."""
    if dol.u32(FORCED_ROLL) == NOP:
        return ["cpu no star pitches: skipped, this build forces CPU star pitches (cpu_star_pitch.py)"]
    got = (dol.u32(DECIDE), dol.u32(DECIDE + 4))
    assert got == DECIDE_ORIG, f"0x{DECIDE:08X}: {got[0]:08X} {got[1]:08X}, expected stock"
    at = code.here + (-code.here % 4)
    assert code.put(pitch_stub(at).assemble(), align=4) == at
    dol.w32(DECIDE, branch(DECIDE, at))
    return [f"cpu no star pitches: level 5 FUN_{DECIDE:08X} returns 0 (0x{DECIDE:08X} -> 0x{at:08X})"]


def allow_pitches(dol):
    """Undo apply_no_pitches (for cpu_star_pitch.apply). True if it had run."""
    word = dol.u32(DECIDE)
    if word == DECIDE_ORIG[0]:
        return False
    assert word >> 26 == 18 and dol.u32(DECIDE + 4) == DECIDE_ORIG[1], f"0x{DECIDE:08X}: 0x{word:08X}"
    dol.w32(DECIDE, DECIDE_ORIG[0])
    return True
