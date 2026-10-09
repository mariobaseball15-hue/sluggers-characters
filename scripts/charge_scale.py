"""The charge effects' size per character, for new ids (Nick: "a lot of the custom characters are missing the purple
circles that indicate their charge when they are pitching").

Each frame of a charge effect sizes it for the character charging: FUN_800f33c8 (the pitcher's, the
CPitcherEnergyChargeEventThrower's effect; the pitcher is r13-0x1580, else r13-0x1584) and FUN_800f2e10 (the
batter's: r13-0x1d78, else r13-0x1d7c) copy a table of 101 floats (0x80624F30 / 0x80624D98, one scale per stock id)
to the stack and read the scale at the character's id (+0x2A). A new id reads past the 101 copied floats into
whatever is on the stack, so the effect is scaled to nothing, or to garbage.

charbuild extends both tables like its other per-id tables (TABLES "pitchchargescale" / "batchargescale": a new
character copies its template's scale), and each read's stack base, `addi r5,r1,0x14`, becomes a `bl` to a stub
that points r5 at the extended table instead (LR is already saved in both: they restore it from the stack). Built
only with new characters, so a build without them is byte-identical.

  site        function        table (TABLES)       effect
  0x800F3478  FUN_800f33c8    pitchchargescale     the pitcher's charge (Nick's purple circles)
  0x800F2EC0  FUN_800f2e10    batchargescale       the batter's charge
  0x800FB1E0  FUN_800fb084    effectscale_2b0      an effect's size (0x806252B0, 1.0 for every stock id; found by the
                                                   id-limit sweep, docs/char-limit-sites.md): `addi r3,r1,0x78`, then
                                                   `lfsx f1,r3,r0` (r0 = id * 4)
"""
from ppc import Asm

# (site, TABLES name, the stack copy's base: `addi rD,r1,off` there, rD)
SITES = [(0x800F3478, "pitchchargescale", 0x38A10014, "r5"),   # addi r5,r1,0x14
         (0x800F2EC0, "batchargescale", 0x38A10014, "r5"),
         (0x800FB1E0, "effectscale_2b0", 0x38610078, "r3")]    # addi r3,r1,0x78 (FUN_800fb084 saves LR)


def apply(dol, code, at):
    """at: charbuild's {table name: its extended copy}. Returns the log lines."""
    out = []
    for addr, table, original, reg in SITES:
        got = dol.u32(addr)
        assert got == original, f"charge scale: 0x{addr:08X} holds {got:08X}, not {original:08X}"
        stub_at = code.here + (-code.here % 4)
        a = Asm(stub_at)
        a.load_addr(reg, at[table]).blr()
        where = code.put(a.assemble(), 4)
        assert where == stub_at, (hex(where), hex(stub_at))
        b = Asm(addr)
        b.bl(where)
        dol.w32(addr, b.assemble_word())
        out.append(f"0x{addr:08X} -> 0x{at[table]:08X} (stub 0x{where:08X})")
    return ["charge scale: " + "; ".join(out)]
