"""Spin-out: a hit fielder spins in place for a while (Nick, 2026-09-26: the first new hit effect; items and hazards).

It is the stock stun (FUN_8012a140(fielder, 1): +0x23E stunned, +0x200 frames left), shown differently. Each frame
of a stun, FUN_8012a5c0 turns the fielder's heading (+0x202, s16, 0x10000 a turn) by DAT_80625F20[mode]+0x44 and walks
him at DAT_80625DE0[mode]+0x90 that way: the dizzy stagger. For a spinning fielder (SPIN[his slot +0x21C] set) the
turn is STEP (1/16 turn a frame, about 4 turns a second) and the walk 0: he spins on the spot.

  TURN  0x8012A630  lha r0,0x44(r3)     (the turn step)          -> STEP when he spins
  WALK  0x8012A668  lfs f0,0x90(r6)     (the stagger speed)      -> 0.0 when he spins
  END   0x8012A5F4  stb r0,0x23e(r3)    (the stun is over)       -> and his SPIN flag cleared
  (r11 / r12 are unused in FUN_8012a5c0; at TURN r3 is dead after the load, at WALK r6.)

ensure(dol, code, data) patches them once per build and returns the spin routine: r3 = the fielder, r4 = frames (at
60 Hz; 5/6 of it at 50 Hz). It stuns him (skipped if he's already stunned, or the stun doesn't take: down, frozen,
...), then sets his stun timer to the frames and his SPIN flag. Callers: ice_item's hit stub (items, effect "spin"),
hazard_effects.emit (hazards).
"""
import struct

from ppc import Asm, ha, lo

STUN_FN = 0x8012A140
TURN, TURN_ORIG = 0x8012A630, 0xA8030044          # lha r0,0x44(r3)
WALK, WALK_ORIG = 0x8012A668, 0xC0060090          # lfs f0,0x90(r6)
END, END_ORIG = 0x8012A5F4, 0x9803023E            # stb r0,0x23e(r3)
STEP = 0x1000                                     # heading per frame: 1/16 turn
SLOTS = 16                                        # fielder slots (+0x21C: 0..8 in the fielder arrays)
DEFAULT_FRAMES = 90
LAYOUT = {}


def _patch(dol, site, orig, target):
    got = dol.u32(site)
    assert got == orig, f"0x{site:08X}: {got:08X} (expected {orig:08X})"
    dol.w32(site, Asm(site).b(target).assemble_word())


def _flag(a, slot_reg, flags, into="r12"):
    """into = &SPIN[fielder's slot]'s byte (slot byte already in slot_reg; r11 clobbered)."""
    a.andi_("r12", slot_reg, SLOTS - 1).load_addr("r11", flags).add(into, "r11", "r12")


def ensure(dol, code, data):
    """The spin routine's address; the hooks and the flags are placed on the first call for this dol."""
    if LAYOUT.get("dol") is dol:
        return LAYOUT["fn"]
    flags = data.put(bytes(SLOTS), 4)
    zero = code.put(struct.pack(">f", 0.0), 4)

    a = Asm(code.here + (-code.here % 4))                    # TURN: r31 = the fielder
    a.word(TURN_ORIG).lbz("r12", 0x21C, "r31")
    _flag(a, "r12", flags)
    a.lbz("r12", 0, "r12").cmpwi("r12", 0).beq("back").li("r0", STEP)
    a.label("back")
    a.b(TURN + 4)
    _patch(dol, TURN, TURN_ORIG, code.put(a.assemble(), 4))

    a = Asm(code.here + (-code.here % 4))                    # WALK: r31 = the fielder
    a.word(WALK_ORIG).lbz("r12", 0x21C, "r31")
    _flag(a, "r12", flags)
    a.lbz("r12", 0, "r12").cmpwi("r12", 0).beq("back").load_addr("r11", zero).lfs("f0", 0, "r11")
    a.label("back")
    a.b(WALK + 4)
    _patch(dol, WALK, WALK_ORIG, code.put(a.assemble(), 4))

    a = Asm(code.here + (-code.here % 4))                    # END: r3 = the fielder, r0 = 0
    a.word(END_ORIG).lbz("r12", 0x21C, "r3")
    _flag(a, "r12", flags)
    a.stb("r0", 0, "r12").b(END + 4)
    _patch(dol, END, END_ORIG, code.put(a.assemble(), 4))

    a = Asm(code.here + (-code.here % 4))                    # the spin routine
    a.stwu("r1", -0x20, "r1").mflr("r0").stw("r0", 0x24, "r1").stw("r31", 0x1C, "r1").stw("r30", 0x18, "r1")
    a.mr("r31", "r3").mr("r30", "r4")
    a.lbz("r0", 0x23E, "r31").cmpwi("r0", 0).bne("out")     # already stunned: leave him
    a.li("r4", 1).bl(STUN_FN)
    a.lbz("r0", 0x23E, "r31").cmpwi("r0", 0).beq("out")     # the stun didn't take
    a.lbz("r0", -0x1658, "r13").cmpwi("r0", 0).beq("hz60")
    a.mulli("r30", "r30", 5).li("r0", 6).divwu("r30", "r30", "r0")
    a.label("hz60")
    a.sth("r30", 0x200, "r31")
    a.lbz("r12", 0x21C, "r31")
    _flag(a, "r12", flags)
    a.li("r0", 1).stb("r0", 0, "r12")
    a.label("out")
    a.lwz("r30", 0x18, "r1").lwz("r31", 0x1C, "r1").lwz("r0", 0x24, "r1").mtlr("r0").addi("r1", "r1", 0x20).blr()
    fn = code.put(a.assemble(), 4)
    LAYOUT.clear()
    LAYOUT.update(dol=dol, fn=fn, flags=flags)
    return fn
