"""New items built on the Shell (creators/items.py chassis "shell"; docs/item-creator.md): its own speed, size and
hit. Like the Fireball's variants (koopa_items), each item is its own id until it's used, then the Shell (ice_item's
use stub) with the variant byte (ice_item.LAYOUT["variant"]) saying which; these hooks read it.

The Shell's table row (0x80631008 + mode * 0x28 + row * 0x14): +0 hit radius (vtable +0x1C getter), +4 height, +8
speed (per frame: its velocity is normalised at the throw, PSVECNormalize, and each frame's step is velocity x +0x38),
+0xC spin, +0x10 size (+0x28..+0x30, the draw scale).

  LAUNCH  0x80459478  lfs f0,0x10(r3) / lfs f1,0x8(r3)  (the throw FUN_80459428)  -> size x, speed x
  RADIUS  0x8045967C  lfsx f1,r3,r0 (the hit radius getter, then blr)          -> radius x size
  HIT     0x80117338, 0x80117390  bl FUN_80128b48 (fielder, angle, 1): the Shell's knockdown in the fielder check
          FUN_8011703c (r30 = the fielder, r31 = the Shell)                     -> the item's own hit
Every hook is emitted only for Shell items that change something; with none, nothing is patched.
"""
import struct

from ppc import Asm, ha, lo

SHELL = 0
LAUNCH, LAUNCH_ORIG = 0x80459478, (0xC0030010, 0xC0230008)
RADIUS, RADIUS_ORIG = 0x8045967C, 0x7C23042E
HITS = (0x80117338, 0x80117390)
KNOCK_FN, STUN_FN, FREEZE_FN = 0x80128B48, 0x8012A140, 0x80129D14
REC = 0x10                                        # per item: f32 speed x, f32 size x, f32 slide speed, u16 slide


def _variant(a, flag):
    return a.lis("r12", ha(flag)).lbz("r12", lo(flag), "r12")


def _hook(dol, code, site, a, orig, link=False):
    got = dol.u32(site)
    assert got == orig, f"0x{site:08X}: {got:08X} (expected {orig:08X})"
    at = code.put(a.assemble(), 4)
    assert at == a.base, f"assembled for 0x{a.base:08X}, placed at 0x{at:08X}"
    dol.w32(site, (Asm(site).bl(at) if link else Asm(site).b(at)).assemble_word())


def _at(code):
    return code.here + (-code.here % 4)


def apply(dol, code, data, flag, shells, spin_fn=None):
    """shells: creators.items.customs specs of chassis "shell". Returns log lines."""
    moved = [s for s in shells if s.get("speed", 1.0) != 1.0 or s.get("size", 1.0) != 1.0]
    hits = [s for s in shells if s.get("effect") not in (None, "knockdown") or s.get("slide")]
    if not moved and not hits:
        return []
    recs = code.put(b"".join(struct.pack(">3fH2x", s.get("speed", 1.0), s.get("size", 1.0),
                                         (s.get("slide") or (0.0, 0))[0], (s.get("slide") or (0.0, 0))[1])
                             for s in shells), 4)
    rec = {s["id"]: recs + REC * k for k, s in enumerate(shells)}
    log = []
    if moved:
        a = Asm(_at(code))                                   # LAUNCH: r3 = the row; f0 size, f1 speed; f2 free
        a.word(LAUNCH_ORIG[0]).word(LAUNCH_ORIG[1])
        _variant(a, flag)
        for s in moved:
            a.cmpwi("r12", s["id"]).beq(f"c{s['id']}")
        a.b(LAUNCH + 8)
        for s in moved:
            a.label(f"c{s['id']}")
            a.load_addr("r12", rec[s["id"]]).lfs("f2", 0, "r12").fmuls("f1", "f1", "f2")
            a.lfs("f2", 4, "r12").fmuls("f0", "f0", "f2").b(LAUNCH + 8)
        assert dol.u32(LAUNCH + 4) == LAUNCH_ORIG[1], f"0x{LAUNCH + 4:08X}: {dol.u32(LAUNCH + 4):08X}"
        _hook(dol, code, LAUNCH, a, LAUNCH_ORIG[0])
        sized = [s for s in moved if s.get("size", 1.0) != 1.0]
        if sized:
            a = Asm(_at(code))                               # RADIUS getter: f1 = the radius, then return
            a.word(RADIUS_ORIG)
            _variant(a, flag)
            for s in sized:
                a.cmpwi("r12", s["id"]).beq(f"c{s['id']}")
            a.blr()
            for s in sized:
                a.label(f"c{s['id']}")
                a.load_addr("r12", rec[s["id"]]).lfs("f0", 4, "r12").fmuls("f1", "f1", "f0").blr()
            _hook(dol, code, RADIUS, a, RADIUS_ORIG)
        log.append("shell items: " + ", ".join(f"{s['name']} ({s['id']}) speed x{s.get('speed', 1.0)}, size "
                                                f"x{s.get('size', 1.0)}" for s in moved))
    if hits:
        import ice_item
        effect = {}
        for s in hits:                                       # one routine per item: r3 = fielder, r4 = angle, r5 = 1
            a = Asm(_at(code))
            a.stwu("r1", -0x20, "r1").mflr("r0").stw("r0", 0x24, "r1").stw("r31", 0x1C, "r1").mr("r31", "r3")
            kind = s["effect"]
            if kind == "knockdown":                          # the stock knockdown, then its own slide
                a.bl(KNOCK_FN).cmpwi("r3", 0).beq("out")
                a.load_addr("r12", rec[s["id"]]).lfs("f0", 8, "r12").stfs("f0", 0x130, "r31")
                a.lhz("r0", 0xC, "r12").sth("r0", 0x206, "r31")
            elif kind == "stun":
                a.li("r4", 1).bl(STUN_FN)
            elif kind == "spin":
                assert spin_fn, "spin needs spin_effect.ensure's routine"
                a.li("r4", s["spin_frames"]).bl(spin_fn)
            elif kind == "freeze" and s.get("freeze_frames"):
                tab = code.put(struct.pack(">2H", s["freeze_frames"], round(s["freeze_frames"] * 5 / 6)), 4)
                a = Asm(_at(code))                           # (the table first, then the routine)
                a.stwu("r1", -0x20, "r1").mflr("r0").stw("r0", 0x24, "r1").stw("r31", 0x1C, "r1").mr("r31", "r3")
                a.bl("frz").b("out")
                a.label("frz")
                ice_item.freeze_code(a, tab, "f_")           # r3 = r31 = the fielder
            elif kind == "freeze":
                a.addi("r4", "r3", 4).bl(FREEZE_FN)
            else:
                raise AssertionError(f"{s['name']}: a shell can't {kind}")
            a.label("out")
            a.lwz("r31", 0x1C, "r1").lwz("r0", 0x24, "r1").mtlr("r0").addi("r1", "r1", 0x20).blr()
            effect[s["id"]] = code.put(a.assemble(), 4)
        for site in HITS:                                    # bl'd: our own hit, or the stock knockdown (tail)
            a = Asm(_at(code))
            _variant(a, flag)
            for s in hits:
                a.cmpwi("r12", s["id"]).beq(f"c{s['id']}")
            a.b(KNOCK_FN)
            for s in hits:
                a.label(f"c{s['id']}")
                a.b(effect[s["id"]])
            _hook(dol, code, site, a, Asm(site).bl(KNOCK_FN).assemble_word(), link=True)
        log.append("shell items' hits: " + ", ".join(f"{s['name']} {s['effect']}" for s in hits))
    return log
