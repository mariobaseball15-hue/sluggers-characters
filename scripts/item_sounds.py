"""Items' own sounds (creators/items.py, block "sound"; docs/item-creator.md): a game sound id or the player's clip
(added to MY2.brsar at patch time: build_voices, voice_tables.json "items"), per event. Each hook is emitted only
when an item has a sound for its event; the use stub (ice_item) has set the variant byte, which they read.

  throw  0x80456A98  li r4,0xAE (the use function FUN_80456710: every item's throw, then FUN_80386d10)
  land   0x80453388, 0x804535B0  li r4,0x3AC (the Fireball's fizzle as a ball ends, FUN_8045335c / FUN_804534c4):
         thrown balls' "landing"; 0x80458FA0 li r4,0xB1 (the POW's burst where it lands, FUN_80458e80): lobs'
  hit    the item hit calls: the Fireball's 0x801179F8 (FUN_80117838: r30 = the ball) and the Shell's 0x80117338 /
         0x80117390 (FUN_8011703c: r31 = the Shell), whatever they call now (our hit stubs or the stock reaction).
         A pre-step plays FUN_80454008(item, id, 1) (the item objects' own positional sound, as their own code
         plays theirs), then goes on to that call with its arguments as they were.
"""
from ppc import Asm, ha, lo

THROW, THROW_ORIG = 0x80456A98, 0x388000AE        # li r4,0xAE
FIZZLE, FIZZLE_ORIG = (0x80453388, 0x804535B0), 0x388003AC   # li r4,0x3AC
BURST, BURST_ORIG = 0x80458FA0, 0x388000B1                     # li r4,0xB1: the POW burst, a lob landing
HITS = ((0x801179F8, "r30"), (0x80117338, "r31"), (0x80117390, "r31"))   # (bl site, the item's register)
ITEM_SOUND = 0x80454008                           # FUN_80454008(item, sound id, 1): at the item's position
STOCK_SOUNDS = 1050                               # sound ids 0..1049 are the game's own (our voices come after)


def _at(code):
    return code.here + (-code.here % 4)


def _put(dol, code, site, a, link=False):
    at = code.put(a.assemble(), 4)
    assert at == a.base
    dol.w32(site, (Asm(site).bl(at) if link else Asm(site).b(at)).assemble_word())


def _swap_li(dol, code, flag, site, orig, sounds):
    """`li r4, stock` at site -> each item's own id (the variant chain), else the stock one."""
    got = dol.u32(site)
    assert got == orig, f"0x{site:08X}: {got:08X} (expected {orig:08X})"
    a = Asm(_at(code))
    a.lis("r12", ha(flag)).lbz("r12", lo(flag), "r12")
    for vid in sounds:
        a.cmpwi("r12", vid).beq(f"s{vid}")
    a.word(orig).b(site + 4)
    for vid, se in sounds.items():
        a.label(f"s{vid}")
        a.li("r4", se).b(site + 4)
    _put(dol, code, site, a)


def _target(dol, site):
    w = dol.u32(site)
    assert w >> 26 == 18 and w & 1, f"0x{site:08X}: {w:08X} isn't a bl"
    off = w & 0x03FFFFFC
    return (site + (off - 0x04000000 if off & 0x02000000 else off)) & 0xFFFFFFFF


def apply(dol, code, flag, throws=None, hits=None, lands=None, lob_lands=None):
    """throws / hits / lands (thrown balls) / lob_lands (lobs): {item id: sound id}. Call after every hook the hit sites may already go to (ice_item,
    shell_item). Returns log lines."""
    log = []
    if throws:
        _swap_li(dol, code, flag, THROW, THROW_ORIG, throws)
        log.append("item sounds: throw " + ", ".join(f"item {v} -> {s}" for v, s in throws.items()))
    if lands:
        for site in FIZZLE:
            _swap_li(dol, code, flag, site, FIZZLE_ORIG, lands)
        log.append("item sounds: landing " + ", ".join(f"item {v} -> {s}" for v, s in lands.items()))
    if lob_lands:
        _swap_li(dol, code, flag, BURST, BURST_ORIG, lob_lands)
        log.append("item sounds: a lob's landing " + ", ".join(f"item {v} -> {s}" for v, s in lob_lands.items()))
    if hits:
        for site, obj in HITS:
            then = _target(dol, site)                        # what the site calls now
            a = Asm(_at(code))
            a.stwu("r1", -0x20, "r1").mflr("r0").stw("r0", 0x24, "r1")
            a.stw("r3", 0x8, "r1").stw("r4", 0xC, "r1").stw("r5", 0x10, "r1")
            a.lis("r12", ha(flag)).lbz("r12", lo(flag), "r12")
            for vid in hits:
                a.cmpwi("r12", vid).beq(f"h{vid}")
            a.b("go")
            for vid, se in hits.items():
                a.label(f"h{vid}")
                a.mr("r3", obj).li("r4", se).li("r5", 1).bl(ITEM_SOUND).b("go")
            a.label("go")
            a.lwz("r3", 0x8, "r1").lwz("r4", 0xC, "r1").lwz("r5", 0x10, "r1")
            a.lwz("r0", 0x24, "r1").mtlr("r0").addi("r1", "r1", 0x20).b(then)
            _put(dol, code, site, a, link=True)
        log.append("item sounds: hit " + ", ".join(f"item {v} -> {s}" for v, s in hits.items()))
    return log
