"""Items that don't hit runners (creators/items.py, item block "runners"; docs/runners.md).

The stock game knocks runners down with its items: FUN_8015830c's runner loop runs, for each runner on the field,
one check per live item object (r13-0x354: +4 Shell, +0xC0 Fireball, +0x44 Bob-omb, +0x180 POW, +0x1BC Banana),
and a hit calls FUN_8017726c(runner): the stock fall (down flag +0x1B2, the state bytes, an effect, SE 0xA1, the
runner's voice). Our items become their stock item at use (ice_item's use stub, which also sets the variant byte),
so they hit runners as that item does. An item whose "runners" is off (the Bullet Bill's preset) skips the fall:
its six calls in the checks go through a stub that returns for its variant, else goes on to FUN_8017726c.

Emitted only when some item has it off. Hazards (git-95's) call FUN_8017726c themselves and aren't gated here.
"""
from ppc import Asm, ha, lo

FALL = 0x8017726C                                  # FUN_8017726c(runner): the stock runner hit reaction
SITES = (0x80176D0C, 0x80176E40, 0x80176F64, 0x801770AC, 0x8017720C, 0x80177240)   # bl FUN_8017726c in the checks


def _at(code):
    return code.here + (-code.here % 4)


def apply(dol, code, flag, off):
    """off: item ids (variants) that don't hit runners. Returns log lines."""
    off = sorted(set(off))
    if not off:
        return []
    for site in SITES:
        assert dol.u32(site) == Asm(site).bl(FALL).assemble_word(), f"0x{site:08X}: {dol.u32(site):08X}"
    a = Asm(_at(code))                             # r3 = the runner; r12 is free at a call
    a.lis("r12", ha(flag)).lbz("r12", lo(flag), "r12")
    for vid in off:
        a.cmpwi("r12", vid).beq("skip")
    a.b(FALL)                                      # the stock fall (returns to the check)
    a.label("skip")
    a.blr()
    at = code.put(a.assemble(), 4)
    assert at == a.base
    for site in SITES:
        dol.w32(site, Asm(site).bl(at).assemble_word())
    return [f"runner hits: off for item {', '.join(str(v) for v in off)} (the stock runner checks skip the fall)"]
