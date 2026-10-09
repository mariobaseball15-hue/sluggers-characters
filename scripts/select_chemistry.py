"""Chemistry on the character select and team screens for new characters (Nick: Purple Mario and Pauline have
chemistry in play, but the select screen shows no marker between them).

In a match, chemistry goes through FUN_8015c800, which charbuild hooks at 0x8015C880 (new ids read the new character's
row, both-new pairs a new-by-new table). The select and team screens read it their own way: they copy a character's
0x8E-byte stats row to the stack (FUN_8046dd60) and index its 101 chemistry bytes (+0x28) with the other character's
id. For a new id (0x66 and up) that reads past the row, and FUN_80069b2c (good chemistry between two ids, used for the
CPU's picks and the batting order) turns away any id >= 0x65 before it looks.

Each read below becomes `bl` to a stub: a stock id reads as before (the original instruction); a new id reads the new
character's master row at the stock character's column, or the new-by-new table when both are new - the same answers
as the match's hook. FUN_80069b2c's id limits go up to the last new id. Built only with new characters (charbuild's
chemistry step), so a build without them is byte-identical.

  site        function        instruction          row + 0x28    other id   screen
  0x80184F78  FUN_80184d40    lbzx r0,r3,r0        r3            r0         team slots' chemistry marker (hovered)
  0x80185170  FUN_80184d40    lbzx r0,r3,r0        r3            r0         (the same, cursor on a slot)
  0x80187988  FUN_801875e4    lbz r0,0x28(r3)      r30 + 0x28    r0         team screen chemistry test
  0x801886D4  FUN_80188514    lbzx r0,r3,r0        r3            r0         next slot's chemistry
  0x80188A48  FUN_80188814    lbzx r0,r3,r0        r3            r0         chemistry test
  0x80069B80  FUN_80069b2c    lbzx r0,r3,r31       r3            r31        good chemistry between two ids
  0x80067978  FUN_8006785c    lbz r3,0x28(r26)     r26 - r25     r25        draft grid's note on each square (selchem-1)
  0x80064EA4  FUN_80064dd4    lbzx r3,r3,r29       r3            r29        team bar's note on each picked player
  0x80079500  FUN_80079304    lbz r3,0x28(r25)     r25 - r28     r28        the grid's note (FUN_8006785c's twin)
  0x8008952C  FUN_800893f8    lbzx r3,r3,r29       r3            r29        the team bar's note (FUN_80064dd4's twin)

The draft grid (selchem-1, Nick: "no chem shows for purple mario or pauline ever"): FUN_8006785c draws a square's note.
The hovered character is FUN_80077054's answer (the wheel member picked on the cursor's square, kept at the draft
object's +0x310 per player) and the square's character is vtable +8, FUN_8006e7d8 (that square's picked wheel member),
so both are already the colours picked; the read was the stock column past 0x64 (the last four rows above).
"""
from ppc import Asm

STOCK_IDS, ROW, CHEM_BASE, NEUTRAL = 0x65, 0x8E, 0x28, 1
# (address, the original instruction, how A's id is found (into r11), B's register[, the answer's register])
SITES = [
    (0x80184F78, lambda a: a.lbzx("r0", "r3", "r0"), lambda a: a.lhz("r11", -CHEM_BASE, "r3"), "r0"),
    (0x80185170, lambda a: a.lbzx("r0", "r3", "r0"), lambda a: a.lhz("r11", -CHEM_BASE, "r3"), "r0"),
    (0x80187988, lambda a: a.lbz("r0", CHEM_BASE, "r3"), lambda a: a.lhz("r11", 0, "r30"), "r0"),
    (0x801886D4, lambda a: a.lbzx("r0", "r3", "r0"), lambda a: a.lhz("r11", -CHEM_BASE, "r3"), "r0"),
    (0x80188A48, lambda a: a.lbzx("r0", "r3", "r0"), lambda a: a.lhz("r11", -CHEM_BASE, "r3"), "r0"),
    (0x80069B80, lambda a: a.lbzx("r0", "r3", "r31"), lambda a: a.lhz("r11", -CHEM_BASE, "r3"), "r31"),
    (0x80067978, lambda a: a.lbz("r3", CHEM_BASE, "r26"), lambda a: a.subf("r11", "r25", "r26").lhz("r11", 0, "r11"),
     "r25", "r3"),
    (0x80064EA4, lambda a: a.lbzx("r3", "r3", "r29"), lambda a: a.lhz("r11", -CHEM_BASE, "r3"), "r29", "r3"),
    (0x80079500, lambda a: a.lbz("r3", CHEM_BASE, "r25"), lambda a: a.subf("r11", "r28", "r25").lhz("r11", 0, "r11"),
     "r28", "r3"),
    (0x8008952C, lambda a: a.lbzx("r3", "r3", "r29"), lambda a: a.lhz("r11", -CHEM_BASE, "r3"), "r29", "r3"),
]
LIMITS = [(0x80069B50, 0x2C030065), (0x80069B60, 0x2C040065)]      # FUN_80069b2c: cmpwi r3 / r4, 0x65


def word(addr, emit):
    a = Asm(addr)
    emit(a)
    return a.assemble_word()


def stub(at, stock, a_id, b, rows, first_new, n_new, new_chem, out="r0"):
    """The stub for one site at address `at`: out = the chemistry of A (the copied row's character) with B."""
    a = Asm(at)
    a.cmplwi(b, STOCK_IDS - 1).bgt("new")
    stock(a)                                             # a stock B: the row's own column, as the game does
    a.blr()
    a.label("new")
    a.stwu("r1", -16, "r1").stw("r11", 8, "r1").stw("r12", 12, "r1")
    a_id(a)                                              # r11 = A (before r12: it may read B)
    a.mr("r12", b)                                       # B (b may be r0, which the answer overwrites)
    a.cmplwi("r11", STOCK_IDS - 1).bgt("both")
    a.mulli("r12", "r12", ROW).add("r12", "r12", "r11")  # stock A, new B: B's master row, column A
    a.load_addr("r11", rows).add("r12", "r12", "r11")
    a.lbz(out, CHEM_BASE, "r12").b("done")
    a.label("both")                                      # both new: new_chem[(A - first) * n + B - first]
    a.addi("r11", "r11", -first_new).cmplwi("r11", n_new - 1).bgt("unknown")
    a.addi("r12", "r12", -first_new).cmplwi("r12", n_new - 1).bgt("unknown")
    a.mulli("r11", "r11", n_new).add("r11", "r11", "r12")
    a.load_addr("r12", new_chem).lbzx(out, "r12", "r11").b("done")
    a.label("unknown")
    a.li(out, NEUTRAL)
    a.label("done")
    a.lwz("r11", 8, "r1").lwz("r12", 12, "r1").addi("r1", "r1", 16).blr()
    return a.assemble()


def apply(dol, code, rows, first_new, n_new, new_chem, max_id):
    """rows: the build's stats rows (the moved table + its header); new_chem: the new-by-new table (charbuild's
    chemistry step). Returns the log lines."""
    stubs = []
    for addr, stock, a_id, b, *out in SITES:
        want = word(addr, stock)
        got = dol.u32(addr)
        assert got == want, f"select chemistry: 0x{addr:08X} holds {got:08X}, not {want:08X}"
        at = code.here + (-code.here % 4)
        where = code.put(stub(at, stock, a_id, b, rows, first_new, n_new, new_chem, *out), 4)
        assert where == at, (hex(where), hex(at))
        dol.w32(addr, word(addr, lambda a, where=where: a.bl(where)))
        stubs.append(where)
    for addr, expect in LIMITS:
        got = dol.u32(addr)
        assert got == expect, f"select chemistry: 0x{addr:08X} holds {got:08X}, not {expect:08X}"
        dol.w32(addr, (expect & 0xFFFF0000) | (max_id + 1))
    return [f"select chemistry: {len(SITES)} reads -> stubs at " + ", ".join(f"0x{s:08X}" for s in stubs)
            + f"; FUN_80069b2c takes ids up to 0x{max_id:02X}"]
