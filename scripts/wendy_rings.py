"""Wendy's rings (Nick, 2026-09-25): her item is a POW lob that lands as N_RINGS rings; they hop and wander
around where it landed (bouncing back, turned by TWIST, when they get WANDER m from it) for the rest of the
half-inning, and a grounded fielder who runs into one slips (FUN_8012a99c, the Banana's stun).

Stock clears every item before each pitch (FUN_80455598) and after each play (FUN_804588f4), and only the active
item's pool is updated, drawn and checked against fielders. So the rings are our own records (RINGS, not item
objects) with a live flag, and every hook works from that flag, never from the active item:

  LAND   0x80458F8C  li r0,2 (POW flight FUN_80458e80, its ray hit the ground in state 1; the Star Bits' LAND
                     stub at 0x80458F88 has run): for the WENDY variant: spawn the rings at the hit point
                     (sp+0x40), POW state (+0x3A) 0, then the POW's own tail (poof 0x19, store, return): no burst
                     (so no stun) and no sound 0xB1.
  TICK   0x801327FC  bl 0x80455394 (play state FUN_801326fc: the item manager's per-frame update): then the
                     rings move (tick).
  FIELD  0x8010C118  bl 0x8011703c (fielder update FUN_8010bcb0, r25 = fielder; result unused): then, with the
                     rings live, the same guards as FUN_8011703c (+0x270, +0x262, manager), on the ground (+0x22E),
                     not already down / stunned / knocked / frozen (+0x23F/+0x243/+0x23E/+0x240), not a floating
                     character (FUN_8015c95c), within its radius (+0x1C) + RING_R of a ring: FUN_8012a99c.
  DRAW   0x8045615C  lis r30,-0x7f8f (FUN_80455ac4, where every item case joins: r30 = model set, r31 = hide
                     all, r26-r28 and sp+0x14..0x34 free): model slot MODEL_SLOT, instance k at ring k (shown
                     while live), coloured per instance (RING_COLORS, the white "tint" model). While Wendy's
                     throw is the active item (variant WENDY, active POW), the POW model (slot 0x2C) is hidden
                     and instance N_RINGS (THROWN) is drawn at the POW object instead (Nick: not a POW), so a
                     ring flies the lob; the POW object goes to state 0 when it lands, and the thrown ring with it.
  LOAD   0x80457560  lmw r25,0x14(r1) (end of FUN_8045723c, after slot 0x2A's load): the ring block
                     (models/work/ring/prop.bin, stored at RING_OFF in item package slot 0x2A's unused tail by
                     starbits_model.apply) is loaded the same way as slot 0x2A (FUN_8037fd30 / FUN_8037fd40 /
                     FUN_80382154) as slot MODEL_SLOT (0x80: nothing else in model set 0 uses it) with N_RINGS
                     instances.
  FREE   0x80457590  or r3,r31,r31 (FUN_80457574 frees the item models): slot MODEL_SLOT first.
  HALF   0x801329FC  bl 0x80137554 (state 3, the half-inning change: sides swap, outs 0): rings off.
  NEW    0x80454E14  bl 0x80454598 (FUN_80454dd8 builds the item manager: a new game): rings off.

Not handled: the ball passes through rings; runners ignore them; CPU fielders don't avoid them; replays don't
rewind them. Not yet tested in Dolphin.
"""
import math
import struct

from ppc import Asm, ha, lo, x_form
from creators import items as _presets   # the one source of the tuning values below (scripts/creators/presets)

WENDY = 12
_SPAWN = _presets.block("wendy", "spawn")
N_RINGS = _SPAWN["count"]   # 6
MODEL_SLOT = 0x80
RING_OFF = 0x5A00             # in item package slot 0x2A (after the Star Bit block, 0x59A0 B)
SPEED = _SPAWN["move"]["wander"]["speed"]     # 0.09 m per frame (5.4 m/s)
WANDER = _SPAWN["move"]["wander"]["range"]    # 9 m from the landing point before a ring turns back
TWIST = _SPAWN["move"]["wander"]["twist"]     # 35 degrees added to the turn-around, so they don't retrace their path
HOP_HEIGHT, HOP_FRAMES = _SPAWN["move"]["hop"]["height"], _SPAWN["move"]["hop"]["frames"]   # 0.7, 32
RING_R = _SPAWN["hit"]["radius"]              # 0.55 m: ring radius for the fielder check (the model is 1.1 across)
MODEL_Y = _SPAWN["look"]["height"]            # 0.56: the model's origin is its centre; upright, its bottom 0.56 below
RING_COLORS = tuple(map(_presets.color, _SPAWN["look"]["colors"]))   # pink, gold (alternating)
REC = 0x28                    # x, y, z, vx, vz, cx, cz, phase, ground

MANAGER = -0x354
LAND, LAND_ORIG, LAND_BACK, LAND_TAIL = 0x80458F8C, 0x38000002, 0x80458F90, 0x80459008
TICK, MGR_UPDATE = 0x801327FC, 0x80455394
FIELD, FIELD_FN = 0x8010C118, 0x8011703C
DRAW, DRAW_ORIG = 0x8045615C, 0x3FC08071
LOAD, LOAD_ORIG = 0x80457560, 0xBB210014
FREE, FREE_ORIG = 0x80457590, 0x7FE3FB78
HALF, HALF_FN = 0x801329FC, 0x80137554
NEW, NEW_FN = 0x80454E14, 0x80454598
FLOATS, SLIP = 0x8015C95C, 0x8012A99C
PKG_DATA, MODEL_LOAD, MODEL_REG, MODEL_SETUP = 0x801303F8, 0x8037FD30, 0x8037FD40, 0x80382154
GET_MODEL, MODEL_SHOW, MODEL_POS, MODEL_ROT, MODEL_SCALE = 0x8037FD48, 0x80381E3C, 0x80381CAC, 0x80381CC4, 0x80381CE4
MODEL_FREE = 0x80381C90
THROWN = N_RINGS              # model instance for the ring in flight (the POW object's lob)
_PRESET = None


def configure(g=None):
    """An edit of Wendy's rings for one build (creators.items.customs spec["ground"]); None: the preset's values
    (charbuild calls it at the start of a build and again at its end)."""
    global N_RINGS, SPEED, WANDER, TWIST, HOP_HEIGHT, HOP_FRAMES, RING_R, MODEL_Y, RING_COLORS, THROWN, _PRESET
    if _PRESET is None:
        _PRESET = (N_RINGS, SPEED, WANDER, TWIST, HOP_HEIGHT, HOP_FRAMES, RING_R, MODEL_Y, RING_COLORS)
    (N_RINGS, SPEED, WANDER, TWIST, HOP_HEIGHT, HOP_FRAMES, RING_R, MODEL_Y, RING_COLORS) = _PRESET
    if g:
        N_RINGS = g["count"]
        SPEED, WANDER, TWIST = (g["wander"][k] for k in ("speed", "range", "twist"))
        HOP_HEIGHT, HOP_FRAMES = g["hop"]["height"], g["hop"]["frames"]
        RING_R = RING_R if g["radius"] is None else g["radius"]
        MODEL_Y = MODEL_Y if g["height"] is None else g["height"]
        RING_COLORS = tuple(tuple(c) for c in g["colors"])
    THROWN = N_RINGS
POW_SLOT, POW_OBJ, ACTIVE, POW_ID = 0x2C, 0x180, 0x394, 3
COLOR_ON, COLOR, COLOR_MODE = 0x80381EEC, 0x80381EF4, 0x80381F04
# consts (floats): offsets
C_W2, C_COS, C_SIN, C_ONE, C_P, C_C, C_RR, C_MY, C_ZERO = (4 * k for k in range(9))


def wendy_pool():
    """Wendy's own pool (the module values; configure() for an edit)."""
    return {"id": WENDY, "count": N_RINGS, "speed": SPEED, "wander": WANDER, "twist": TWIST, "hop": HOP_HEIGHT,
            "frames": HOP_FRAMES, "radius": RING_R, "colors": RING_COLORS}


def consts(p=None):
    p = p or wendy_pool()
    t = math.radians(p["twist"])
    return struct.pack(">12f", p["wander"] ** 2, math.cos(t), math.sin(t), 1.0, p["frames"],
                       4 * p["hop"] / p["frames"] ** 2, p["radius"], MODEL_Y, 0.0, 1.0, 1.0, 1.0)   # +0x24: scale 1,1,1


def dirs(p=None):
    """Per ring: (vx, vz, starting hop phase)."""
    p = p or wendy_pool()
    out, n = b"", p["count"]
    for k in range(n):
        a = math.radians(15 + 360 * k / n)
        out += struct.pack(">3f", p["speed"] * math.cos(a), p["speed"] * math.sin(a), (k * p["frames"] / n) % p["frames"])
    return out


def _check(dol, addr, want):
    got = dol.u32(addr)
    assert got == want, f"0x{addr:08X}: expected {want:08X}, found {got:08X}"


def _put(code, a):
    at = code.put(a.assemble(), 4)
    assert at == a.base, f"assembled for 0x{a.base:08X}, placed at 0x{at:08X}"
    return at


def _at(code):
    return code.here + (-code.here % 4)


MAX_POOLS, MAX_RINGS = 4, 24      # all pools together (records in our data, instances of the one ring model)


def apply(dol, code, data, flag, more_models=(), more_draw=(), pools=()):
    """flag: the used-variant byte (ice_item.LAYOUT["variant"]). more_models: [(model-set slot, offset in
    package slot 0x2A, instances)] also loaded / freed with the ring (lemmy_balls); more_draw: [fn(a)] emitting
    more model code into the DRAW stub (r30 set, r31 hide all, r26-r28 free; unique labels).
    pools: more ring pools after Wendy's: [{"id": the item (its lob lands them), "count", "speed", "wander", "twist",
    "hop", "frames", "radius", "colors"}] (new ring items, creators.items). Each has its own records, live flag,
    values and colours; with none, every hook is as before (one pool). A pool with "drop": a star move's key
    (creators.items.star_spawn "rings:<item>") instead of an "id" is a shower pool: no lob lands it; its drop routine
    (LAYOUT["pools"][k]["drop_fn"], star_shower's shape: r3 = starbits_item.BIT_COUNT + n, f1 / f2 / f3 = x, y, z,
    f4 = ground) puts ring n down there, the first drop parking the rest far off the field until theirs."""
    pools = [wendy_pool()] + list(pools)
    assert len(pools) <= MAX_POOLS and sum(p["count"] for p in pools) <= MAX_RINGS, \
        f"at most {MAX_POOLS} ring pools of {MAX_RINGS} rings together"
    total = sum(p["count"] for p in pools)
    thrown = total                                        # the model instance of a ring in flight
    base = 0
    for p in pools:
        p["base"], base = base, base + p["count"]
    models = [(MODEL_SLOT, RING_OFF, total + 1)] + list(more_models)   # + the thrown ring
    for k, p in enumerate(pools):
        p["live"] = data.put(bytes(4), 4)
        p["rings"] = data.put(bytes(REC * p["count"]), 4)
        p["c"] = data.put(consts(p if k else None), 4)
        p["d"] = data.put(dirs(p if k else None), 4)
        if k == 0:
            colors = data.put(b"".join(bytes(pools[0]["colors"][i % len(pools[0]["colors"])])
                                       for i in range(pools[0]["count"] + (len(pools) == 1))) +
                              b"".join(bytes(q["colors"][i % len(q["colors"])]) for q in pools[1:]
                                       for i in range(q["count"])) +
                              (bytes(pools[0]["colors"][0]) if len(pools) > 1 else b""), 4)
    c = pools[0]["c"]                                     # place(): the ring model's lift and scale (all pools)

    for p in pools:
        n, rings, d, live = p["count"], p["rings"], p["d"], p["live"]
        a = Asm(_at(code))                               # spawn(r3 = landing point): leaf
        a.lfs(1, 0, 3).lfs(2, 4, 3).lfs(3, 8, 3)
        a.load_addr(11, rings).load_addr(10, d).li(9, n)
        a.label("loop")
        a.stfs(1, 0, 11).stfs(2, 4, 11).stfs(3, 8, 11)
        a.lfs(4, 0, 10).stfs(4, 0xC, 11).lfs(4, 4, 10).stfs(4, 0x10, 11)
        a.stfs(1, 0x14, 11).stfs(3, 0x18, 11)
        a.lfs(4, 8, 10).stfs(4, 0x1C, 11).stfs(2, 0x20, 11)
        a.addi(10, 10, 12).addi(11, 11, REC).addi(9, 9, -1).cmpwi(9, 0).bgt("loop")
        a.li(0, 1).load_addr(12, live).stb(0, 0, 12)
        a.blr()
        p["spawn"] = _put(code, a)

        a = Asm(_at(code))                               # tick: leaf
        a.load_addr(12, live).lbz(12, 0, 12).cmpwi(12, 0).beq("out")
        a.load_addr(11, rings).load_addr(10, p["c"]).li(9, n)
        a.label("loop")
        a.lfs(1, 0, 11).lfs(2, 0xC, 11).fadds(1, 1, 2).stfs(1, 0, 11)            # x += vx
        a.lfs(3, 8, 11).lfs(4, 0x10, 11).fadds(3, 3, 4).stfs(3, 8, 11)           # z += vz
        a.lfs(5, 0x14, 11).fsubs(5, 1, 5).lfs(6, 0x18, 11).fsubs(6, 3, 6)
        a.fmuls(5, 5, 5).fmadds(5, 6, 6, 5)                                      # dx^2 + dz^2
        a.lfs(0, C_W2, 10).fcmpo(5, 0).ble("inside")
        a.lfs(7, C_COS, 10).lfs(8, C_SIN, 10)                                    # v = -R(TWIST) v
        a.fmuls(9, 2, 7).fmuls(10, 4, 8).fsubs(9, 9, 10).fneg(9, 9).stfs(9, 0xC, 11)
        a.fmuls(9, 2, 8).fmuls(10, 4, 7).fadds(9, 9, 10).fneg(9, 9).stfs(9, 0x10, 11)
        a.label("inside")
        a.lfs(1, 0x1C, 11).lfs(0, C_ONE, 10).fadds(1, 1, 0)                      # phase + 1, wrapped
        a.lfs(2, C_P, 10).fcmpo(1, 2).blt("in").fsubs(1, 1, 2)
        a.label("in")
        a.stfs(1, 0x1C, 11)
        a.fsubs(3, 2, 1).fmuls(3, 3, 1).lfs(0, C_C, 10).fmuls(3, 3, 0)            # hop
        a.lfs(0, 0x20, 11).fadds(3, 3, 0).stfs(3, 4, 11)
        a.addi(11, 11, REC).addi(9, 9, -1).cmpwi(9, 0).bgt("loop")
        a.label("out")
        a.blr()
        p["tick"] = _put(code, a)
        if len(pools) == 1:
            break                                        # (one pool: spawn and tick as they always were)
        if p.get("drop"):                                # a star move's shower: drop(r3 = 4 + n, f1..f4)
            far = data.put(struct.pack(">3f", 9999.0, -100.0, 0.0), 4)
            a = Asm(_at(code))
            a.load_addr(12, live).lbz(0, 0, 12).cmpwi(0, 0).bne("ready")
            a.load_addr(11, rings).load_addr(10, far).li(9, n)          # first drop: the rest parked, still
            a.lfs(5, 0, 10).lfs(6, 4, 10).lfs(7, 8, 10)
            a.label("park")
            a.stfs(5, 0, 11).stfs(6, 4, 11).stfs(5, 8, 11).stfs(7, 0xC, 11).stfs(7, 0x10, 11)
            a.stfs(5, 0x14, 11).stfs(5, 0x18, 11).stfs(7, 0x1C, 11).stfs(6, 0x20, 11)
            a.addi(11, 11, REC).addi(9, 9, -1).cmpwi(9, 0).bgt("park")
            a.label("ready")
            a.addi(3, 3, -4).mulli(11, 3, REC).load_addr(12, rings).add(11, 12, 11)
            a.mulli(10, 3, 12).load_addr(12, d).add(10, 12, 10)
            a.stfs(1, 0, 11).stfs(4, 4, 11).stfs(3, 8, 11)
            a.lfs(5, 0, 10).stfs(5, 0xC, 11).lfs(5, 4, 10).stfs(5, 0x10, 11)
            a.stfs(1, 0x14, 11).stfs(3, 0x18, 11)
            a.lfs(5, 8, 10).stfs(5, 0x1C, 11).stfs(4, 0x20, 11)
            a.li(0, 1).load_addr(12, live).stb(0, 0, 12)
            a.blr()
            p["drop_fn"] = _put(code, a)

    log = []
    _check(dol, LAND, LAND_ORIG)                         # LAND: each ring item's lob lands as its pool
    a = Asm(_at(code))
    a.lis(12, ha(flag)).lbz(12, lo(flag), 12)
    for k, p in enumerate(pools):
        if p.get("id") is not None:
            a.cmpwi(12, p["id"]).beq(f"ours{k}")
    a.word(LAND_ORIG).b(LAND_BACK)
    for k, p in enumerate(pools):
        if p.get("id") is None:
            continue
        a.label(f"ours{k}")
        a.addi(3, 1, 0x40).bl(p["spawn"])
        a.li(0, 0).stb(0, 0x3A, 30).b(LAND_TAIL)
    dol.w32(LAND, Asm(LAND).b(_put(code, a)).assemble_word())

    _check(dol, TICK, Asm(TICK).bl(MGR_UPDATE).assemble_word())   # TICK
    a = Asm(_at(code))
    a.stwu(1, -0x10, 1).mflr(0).stw(0, 0x14, 1)
    a.bl(MGR_UPDATE)
    for p in pools:
        a.bl(p["tick"])
    a.lwz(0, 0x14, 1).mtlr(0).addi(1, 1, 0x10).blr()
    dol.w32(TICK, Asm(TICK).bl(_put(code, a)).assemble_word())

    _check(dol, FIELD, Asm(FIELD).bl(FIELD_FN).assemble_word())   # FIELD (r25 = fielder)
    a = Asm(_at(code))
    a.stwu(1, -0x20, 1).mflr(0).stw(0, 0x24, 1).stw(31, 0x1C, 1).stw(30, 0x18, 1)
    a.bl(FIELD_FN)
    if len(pools) == 1:
        a.load_addr(12, pools[0]["live"]).lbz(0, 0, 12).cmpwi(0, 0).beq("out")
    else:                                                # any pool live
        a.li(0, 0)
        for p in pools:
            a.load_addr(12, p["live"]).lbz(11, 0, 12).word(x_form(0, 0, 11, 444))   # or r0,r0,r11
        a.cmpwi(0, 0).beq("out")
    a.lwz(0, MANAGER, 13).cmpwi(0, 0).beq("out")
    for off in (0x270, 0x262):
        a.lbz(0, off, 25).cmpwi(0, 0).beq("out")
    for off in (0x22E, 0x23F, 0x243, 0x23E, 0x240):
        a.lbz(0, off, 25).cmpwi(0, 0).bne("out")
    a.mr(3, 25).bl(FLOATS).cmpwi(3, 0).bne("out")
    for k, p in enumerate(pools):
        if len(pools) > 1:
            a.load_addr(12, p["live"]).lbz(0, 0, 12).cmpwi(0, 0).beq(f"skip{k}")
        a.load_addr(12, p["c"]).lfs(7, 0x1C, 25).lfs(0, C_RR, 12).fadds(7, 7, 0).fmuls(7, 7, 7)
        a.load_addr(31, p["rings"]).li(30, p["count"])
        a.label(f"loop{k}")
        a.lfs(1, 4, 25).lfs(2, 0, 31).fsubs(1, 1, 2)
        a.lfs(3, 0xC, 25).lfs(4, 8, 31).fsubs(3, 3, 4)
        a.fmuls(1, 1, 1).fmadds(1, 3, 3, 1).fcmpo(1, 7).bge(f"next{k}")
        a.mr(3, 25).bl(SLIP).b("out")
        a.label(f"next{k}")
        a.addi(31, 31, REC).addi(30, 30, -1).cmpwi(30, 0).bgt(f"loop{k}")
        a.label(f"skip{k}")
    a.label("out")
    a.lwz(30, 0x18, 1).lwz(31, 0x1C, 1).lwz(0, 0x24, 1).mtlr(0).addi(1, 1, 0x20).blr()
    dol.w32(FIELD, Asm(FIELD).bl(_put(code, a)).assemble_word())

    _check(dol, DRAW, DRAW_ORIG)                         # DRAW (r30 = model set, r31 = hide all)
    a = Asm(_at(code))
    a.mr(3, 30).li(4, MODEL_SLOT).bl(GET_MODEL).mr(27, 3)
    a.cmpwi(27, -1).beq("done")
    for k, p in enumerate(pools):                        # pool k: instances base .. base + count - 1
        a.li(26, p["base"])
        a.label(f"loop{k}")
        a.mr(3, 30).mr(4, 27).li(5, 0).mr(6, 26).bl(MODEL_SHOW)            # hide
        a.cmpwi(31, 0).bne(f"next{k}")
        a.load_addr(12, p["live"]).lbz(0, 0, 12).cmpwi(0, 0).beq(f"next{k}")
        if p["base"]:
            a.addi(0, 26, -p["base"]).mulli(0, 0, REC)
            a.load_addr(28, p["rings"]).add(28, 28, 0)
        else:
            a.load_addr(28, p["rings"]).mulli(0, 26, REC).add(28, 28, 0)
        a.bl("place")
        a.label(f"next{k}")
        a.addi(26, 26, 1).cmpwi(26, p["base"] + p["count"]).blt(f"loop{k}")
    a.mr(3, 30).mr(4, 27).li(5, 0).li(6, thrown).bl(MODEL_SHOW)             # the thrown ring: hidden, unless
    a.cmpwi(31, 0).bne("done")
    a.lis(12, ha(flag)).lbz(12, lo(flag), 12)
    if len(pools) == 1:
        a.cmpwi(12, WENDY).bne("done")                                       # Wendy's throw
    else:
        for p in pools:
            if p.get("id") is not None:
                a.cmpwi(12, p["id"]).beq("thrown")                           # a ring item's throw
        a.b("done")
        a.label("thrown")
    a.lwz(28, MANAGER, 13).cmpwi(28, 0).beq("done")
    a.lwz(0, ACTIVE, 28).cmpwi(0, POW_ID).bne("done")                        # is the active item
    a.mr(3, 30).li(4, POW_SLOT).bl(GET_MODEL).cmpwi(3, -1).beq("nopow")      # no POW model for it
    a.mr(4, 3).mr(3, 30).li(5, 0).li(6, 0).bl(MODEL_SHOW)
    a.label("nopow")
    a.addi(28, 28, POW_OBJ).lbz(0, 0x3A, 28).cmpwi(0, 1).bne("done")        # flying: a ring there
    a.addi(28, 28, 4).li(26, thrown).bl("place")
    a.b("done")
    # place: show instance r26 at the position r28 points to (x, y, z; y lifted by MODEL_Y, z negated)
    a.label("place")                                     # own frame: sp+0x14..0x34 are its vectors
    a.stwu(1, -0x40, 1).mflr(0).stw(0, 0x44, 1)
    a.mr(3, 30).mr(4, 27).li(5, 1).mr(6, 26).bl(MODEL_SHOW)
    a.load_addr(11, c)
    a.lfs(0, 0, 28).stfs(0, 0x2C, 1)
    a.lfs(0, 4, 28).lfs(1, C_MY, 11).fadds(0, 0, 1).stfs(0, 0x30, 1)
    a.lfs(0, 8, 28).fneg(0, 0).stfs(0, 0x34, 1)
    a.lfs(0, C_ZERO, 11).stfs(0, 0x20, 1).stfs(0, 0x24, 1).stfs(0, 0x28, 1)  # rotation 0: faces home
    a.lfs(0, C_ZERO + 4, 11).stfs(0, 0x14, 1).stfs(0, 0x18, 1).stfs(0, 0x1C, 1)   # scale 1
    for fn, sp in ((MODEL_POS, 0x2C), (MODEL_ROT, 0x20), (MODEL_SCALE, 0x14)):
        a.mr(3, 30).mr(4, 27).addi(5, 1, sp).mr(6, 26).bl(fn)
    a.mr(3, 30).mr(4, 27).li(5, 0).mr(6, 26).bl(COLOR_MODE)
    a.mr(3, 30).mr(4, 27).li(5, 1).mr(6, 26).bl(COLOR_ON)
    a.load_addr(11, colors).slwi(0, 26, 2).add(11, 11, 0)
    a.lbz(5, 0, 11).lbz(6, 1, 11).lbz(7, 2, 11).lbz(8, 3, 11)
    a.mr(3, 30).mr(4, 27).mr(9, 26).bl(COLOR)
    a.lwz(0, 0x44, 1).mtlr(0).addi(1, 1, 0x40).blr()
    a.label("done")
    for fn in more_draw:
        fn(a)
    a.word(DRAW_ORIG).b(DRAW + 4)
    dol.w32(DRAW, Asm(DRAW).b(_put(code, a)).assemble_word())

    _check(dol, LOAD, LOAD_ORIG)                         # LOAD (as slot 0x2A: r27 archive, r29 set, r26/r25/r30)
    a = Asm(_at(code))
    for slot, off, count in models:
        a.mr(3, 27).li(4, 0).li(5, 0x2A).bl(PKG_DATA)
        a.word(0x3C830000 | ha(off)).addi(4, 4, lo(off))       # addis r4,r3,ha / addi: off may pass 0x7FFF
        #  (a lone addi sign-extended Lemmy's 0xAF00 to -0x5100: freed memory, Nick's crash in koopa-items-8)
        a.mr(3, 29).mr(5, 26).li(6, count).li(7, 0).bl(MODEL_LOAD).mr(31, 3)
        a.mr(3, 29).mr(4, 31).li(5, slot).bl(MODEL_REG)
        a.mr(3, 29).mr(4, 31).mr(5, 25).rlwinm(6, 30, 0, 16, 31).li(7, 0).bl(MODEL_SETUP)
    a.word(LOAD_ORIG).b(LOAD + 4)
    dol.w32(LOAD, Asm(LOAD).b(_put(code, a)).assemble_word())

    _check(dol, FREE, FREE_ORIG)                         # FREE (r31 = model set, LR saved; r4 = 0x29 after)
    a = Asm(_at(code))
    for k, (slot, _, _) in enumerate(models):
        a.mr(3, 31).li(4, slot).bl(GET_MODEL).cmpwi(3, -1).beq(f"none{k}")
        a.mr(4, 3).mr(3, 31).bl(MODEL_FREE)
        a.label(f"none{k}")
    a.li(4, 0x29).word(FREE_ORIG).b(FREE + 4)
    dol.w32(FREE, Asm(FREE).b(_put(code, a)).assemble_word())

    for site, fn in ((HALF, HALF_FN), (NEW, NEW_FN)):    # HALF / NEW: rings off, then the call
        _check(dol, site, Asm(site).bl(fn).assemble_word())
        a = Asm(_at(code))
        a.li(0, 0)
        for p in pools:
            a.load_addr(12, p["live"]).stb(0, 0, 12)
        a.b(fn)
        dol.w32(site, Asm(site).bl(_put(code, a)).assemble_word())
    LAYOUT.update(pools=pools)
    return [f"wendy rings: {N_RINGS} rings (model slot 0x{MODEL_SLOT:X} from package slot 0x2A +0x{RING_OFF:X}), "
            f"live flag 0x{pools[0]['live']:08X}, speed {SPEED}, wander {WANDER} m, hop {HOP_HEIGHT} m / {HOP_FRAMES:g} f; "
            f"cleared at the half-inning and a new game"] + \
        [f"ring pool for {'item ' + str(p['id']) if p.get('id') is not None else p['drop']}: {p['count']} rings, "
         f"speed {p['speed']}, wander {p['wander']} m" for p in pools[1:]]


LAYOUT = {}


def draw_icon(scale=8):
    """A pink ring with a gold rim (27 x 29, like the stock item icons). -> RGBA image."""
    from PIL import Image, ImageDraw
    W, H = 27 * scale, 29 * scale
    img = Image.new("RGBA", (W, H), (0, 0, 0, 0))
    d = ImageDraw.Draw(img)
    cx, cy, r = W / 2, H / 2 + 0.5 * scale, 11.5 * scale
    d.ellipse((cx - r - 1.5 * scale, cy - r - 1.5 * scale, cx + r + 1.5 * scale, cy + r + 1.5 * scale), fill=(80, 20, 50, 255))
    d.ellipse((cx - r, cy - r, cx + r, cy + r), fill=(255, 105, 180, 255))
    d.ellipse((cx - r * 0.78, cy - r * 0.78, cx + r * 0.78, cy + r * 0.78), fill=(255, 205, 60, 255))
    ri = r * 0.5
    d.ellipse((cx - ri - 1.5 * scale, cy - ri - 1.5 * scale, cx + ri + 1.5 * scale, cy + ri + 1.5 * scale), fill=(80, 20, 50, 255))
    d.ellipse((cx - ri, cy - ri, cx + ri, cy + ri), fill=(0, 0, 0, 0))
    d.arc((cx - r * 0.9, cy - r * 0.9, cx + r * 0.9, cy + r * 0.9), 200, 260, fill=(255, 240, 250, 255), width=int(1.6 * scale))
    return img.convert("RGBa").resize((27, 29), Image.LANCZOS).convert("RGBA")
