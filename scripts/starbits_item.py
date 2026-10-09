"""Star Bits (item id 6, the cut Thunder's slot): thrown like a POW, lands as four star bits that hop in place
and drift in small circles; each is a banana-like hazard (a fielder who runs into one slips, the ball knocks it
away) until the at-bat's items are cleared. Roulette/HUD: starbits_roulette.py. Model (slot 0x2A, 4 instances):
starbits_model.py. Item system map: docs/items.md.

Objects
- THROWER = the Thunder object (manager +0x2FC, 0x3C bytes, vtable THUNDER_VT). Pool lookup (FUN_80456abc case 6)
  and activation (FUN_80456710 -> FUN_80453824/80453900 -> vtable+0x48) already handle it. Its vtable's behavior
  slots are pointed at the POW's (THUNDER_TO_POW: launch 80458D00 = the POW lob, update 80458B7C = flight
  FUN_80458e80 + ball contact, hit 80458E28, reset 80458C64/80458C74, radius/height/table getters); the id
  getter (+0x38, returns 6) and the dtor stay Thunder's. +0x14 (scale) returns THROWER_SCALE.
- BITS = BIT_SLOTS objects of 0x40 bytes in our data section (a manager instance is embedded at object+0x62F8
  with the next member at +0x66D4, so the Thunder pool can't grow). Each has the Banana's layout and a copy of
  the Banana vtable (0x806CC2E0) with +0x40 (update) = bit_update and +0x48 (launch) = a no-op. Only BIT_COUNT
  (4) are used; the 5th stays state 0 so the Banana's five-slot loops can run over BITS unchanged.
  Fields: +4/+8/+0xC pos, +0x10/+0x18 drift velocity (also the knock direction when a fielder slips, as the
  Banana's leftover launch velocity is), +0x14 ground y (while state 3), +0x1C.. rotation, +0x28.. scale,
  +0x34 table row (0), +0x35 blink timer, +0x36 visible, +0x37 in use, +0x38 hop phase (frames, float),
  +0x3C frames left before it poofs (u16, 0 = no limit), +0x3E index, +0x3F state (0 off, 3 on the ground = hazard, 4 knocked away;
  Banana update 8044EBEC runs states 3/4: ball contact FUN_80453b40, knock flight FUN_80453e9c, poof).
  EXT holds each bit's orbit center (x, z), 8 bytes per bit.

Motion (state 3, bit_update, then the Banana update): semi-implicit Euler spring toward the orbit center,
v -= K * (p - c); p += v (x and z), which keeps each bit on a closed orbit of about ORBIT_RADIUS with period
ORBIT_FRAMES; hop y = ground + 4 * HOP_HEIGHT * t * (P - t) / P^2 with t = phase, P = HOP_FRAMES (a ballistic
hop every P frames, the four out of step). simulate() is the same math in Python (the tests compare them).

Hooks (each asserts the stock word):
- TICK 0x80455560 (FUN_80455394 per frame, id-6 case, `bl 0x80453764` on the Thunder object): `bl tick`:
  the thrower's update, then each in-use bit's.
- RESET 0x80455784 (FUN_80455598 at-bat setup, `bl 0x80453774` on the Thunder object): `bl reset`: the same
  reset (FUN_80453774) for the thrower and every bit.
- CLEAR 0x8045893C (FUN_804588f4 clear active item, `b 0x804589b4` = no case for 6): for 6, FUN_80453804 on
  the thrower and each in-use bit (a bit on the ground poofs, like the Banana).
- MODEL 0x80455B38 (FUN_80455ac4 item models, `b 0x8045615c` = no case for 6): for 6, model MODEL_SLOT: each
  instance k < BIT_COUNT is hidden, then shown at bit k (instance 0 = the thrower while it flies) as the
  Banana case does: position (z negated, y + MODEL_Y), rotation, scale, through the object's vtable; then
  its color: COLOR_MODE 0 (multiply), COLOR_ON 1, COLOR = BIT_COLORS[k] (the model's texture is white).
- LAND 0x80458F88 (POW flight FUN_80458e80, `lbz r4,-0x1658(r13)`, reached when the flight ray hits and the
  state is 1): for the thrower (vtable THUNDER_VT): spawn the bits at the hit point (sp+0x40), thrower state
  (+0x3A) 0 (hidden, like a spent POW; stays in use for the at-bat), then the POW's own tail: the poof effect
  0x19 at the hit point if LAND_PUFF, store the position, return. So no POW burst (FUN_800fd910) or sound 0xB1.
- REACT 0x801170D4 (fielder item reaction FUN_8011703c, id 6: `b 0x801181ec` Thunder's): `b 0x80117a98`, the
  Banana's reaction (slip FUN_8012a99c + knock, or the ball holder kicks it).
- REACT_BASE 0x80117AF8 (FUN_80117a98 loop, `addi r31,r3,0x1bc` = Banana i): when the active item
  (manager +0x394) is 6, r31 = BITS + i*0x40 instead (r0 = i*0x40 there). Also reached from FUN_80119140.
- Data: THUNDER_VT words (THUNDER_TO_POW, and +0x14).

apply(dol, code, data) -> log lines. code/data: Space-like allocators (.here, .blob, .put(bytes, align)); data
must be loaded with the DOL (the bits' vtable pointers are static). Returns nothing else; LAYOUT (a dict of
the addresses used) is filled in for the tests.

Not verified in Dolphin. Not handled: CPU fielders' banana avoidance (FUN_8011dd78/8011e250/8011e4f0 check
id 4 only), FUN_801729b8 (copies the manager's pools), the Thunder light callback FUN_803018e4 (only called by
an effect script; would read the thrower's position), a POW flight that hits a wall first (bits spawn at the
wall hit point, their ground y is that point's y).
"""
import math
import struct
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
from ppc import Asm, branch, d_form, ha, lo  # noqa: E402
from creators import items as _presets  # noqa: E402   the one source of the tuning values below
_SPAWN = _presets.block("star-bits", "spawn")

ITEM_ID = 6
MODEL_SLOT = 0x2A             # item model set slot with BIT_COUNT instances (starbits_model.py)
BIT_COUNT = _SPAWN["count"]   # 4 star bits per throw (bits 0..3; the per-bit tables below have 4 entries)
BIT_TOTAL = 40                # model instances and bit objects: BIT_COUNT..BIT_TOTAL-1 are Luma's star swing's
                              # drops (star_shower.py, through `drop`)
BIT_SLOTS = BIT_TOTAL         # storage; the reaction loop (FUN_80117a98) walks all of them for id 6 (REACT_COUNT)
EXT_SIZE = 16                 # per bit: orbit center x, z; fall height above the hop, fall speed
FALL_G = 0.012                # m/frame^2: a dropped bit's fall (v += FALL_G; h -= v each frame, until h = 0)
BIT_SCALE = _SPAWN["look"]["scale"]   # 1.5: model scale (the Star Bit model is ~0.55 m across at 1.0, origin at its center)
THROWER_SCALE = _presets.block("star-bits", "look")["scale"]   # 1.5: the thrown star bit's scale
MODEL_Y = 0.31 * BIT_SCALE    # model lift: its origin is its center, 0.31 above its bottom at scale 1
LAND_PUFF = True              # the POW's vanish poof (effect 0x19) where the throw lands, as the bits appear
# Per-bit color (R, G, B, A), multiplied into the model's material color per instance (instance 0 = the thrown
# bit, then bit 0). The Star Bit model is white (starbit_obj.py "tint"), so these are the colors seen.
BIT_COLORS = tuple(map(_presets.color, _SPAWN["look"]["colors"]))   # yellow, blue, green, pink/purple
INSTANCE_COLORS = tuple(BIT_COLORS[k % len(BIT_COLORS)] for k in range(BIT_TOTAL))

HOP_HEIGHT = _SPAWN["move"]["hop"]["height"]   # 0.8 m, top of each hop above the ground
HOP_FRAMES = _SPAWN["move"]["hop"]["frames"]   # 36 frames per hop (0.6 s)
SPREAD = _SPAWN["spread"]    # 2.0 m, orbit centers from the landing point (the Banana spreads ~5 m)
SPREAD_JITTER = (1.0, 0.8, 1.15, 0.9)   # per bit x SPREAD, so they don't land in a perfect square
ANGLES = (40, 135, 220, 310)            # degrees, direction of each bit's orbit center
ORBIT_RADIUS = _SPAWN["move"]["orbit"]["radius"]   # 0.6 m, how far each bit drifts around its center
ORBIT_FRAMES = int(_SPAWN["move"]["orbit"]["frames"])   # 150 frames per lap (2.5 s); even bits turn one way, odd the other
PHASES = (0, 13, 22, 31)      # hop phase (frames) at landing, so the four hop out of step
SPIN = 0.0                    # added to rotation y per frame while hopping (0: no code; units unverified)
LIFETIME = _SPAWN["lifetime"]   # 0: frames a thrown bit lasts (0: like the Banana, until cleared). Each bit's +0x3C
                              # counts down while it is out and it poofs at 0; 0 = no countdown. Luma's star
                              # swing sets its bits' (star_shower.EXPIRE) when the ball lands

# The spring constant for which semi-implicit Euler circles in exactly ORBIT_FRAMES frames
K = 2 * (1 - math.cos(2 * math.pi / ORBIT_FRAMES))
OMEGA = 2 * math.pi / ORBIT_FRAMES
HOP_C = 4 * HOP_HEIGHT / HOP_FRAMES ** 2
_PRESET = None


def configure(g=None):
    """An edit of Star Bits for one build (creators.items.customs spec["ground"]; still 4 bits); None: the preset's
    values (charbuild calls it at the start of a build and again at its end). Luma's Star Shower bits hop and circle
    with the same values."""
    global HOP_HEIGHT, HOP_FRAMES, SPREAD, ORBIT_RADIUS, ORBIT_FRAMES, LIFETIME, BIT_SCALE, THROWER_SCALE, BIT_COLORS
    global MODEL_Y, INSTANCE_COLORS, K, OMEGA, HOP_C, _PRESET
    if _PRESET is None:
        _PRESET = (HOP_HEIGHT, HOP_FRAMES, SPREAD, ORBIT_RADIUS, ORBIT_FRAMES, LIFETIME, BIT_SCALE, THROWER_SCALE,
                   BIT_COLORS)
    (HOP_HEIGHT, HOP_FRAMES, SPREAD, ORBIT_RADIUS, ORBIT_FRAMES, LIFETIME, BIT_SCALE, THROWER_SCALE,
     BIT_COLORS) = _PRESET
    if g:
        assert g["count"] == BIT_COUNT and len(g["colors"]) == BIT_COUNT, "star bits come 4 at a time"
        HOP_HEIGHT, HOP_FRAMES = g["hop"]["height"], g["hop"]["frames"]
        ORBIT_RADIUS, ORBIT_FRAMES = g["orbit"]["radius"], int(g["orbit"]["frames"])
        SPREAD = SPREAD if g["spread"] is None else g["spread"]
        LIFETIME = g["lifetime"]
        BIT_SCALE = BIT_SCALE if g["scale"] is None else g["scale"]
        THROWER_SCALE = THROWER_SCALE if g["thrower_scale"] is None else g["thrower_scale"]
        BIT_COLORS = tuple(tuple(c) for c in g["colors"])
    MODEL_Y = 0.31 * BIT_SCALE
    INSTANCE_COLORS = tuple(BIT_COLORS[k % len(BIT_COLORS)] for k in range(BIT_TOTAL))
    K = 2 * (1 - math.cos(2 * math.pi / ORBIT_FRAMES))
    OMEGA = 2 * math.pi / ORBIT_FRAMES
    HOP_C = 4 * HOP_HEIGHT / HOP_FRAMES ** 2

# Game addresses
MANAGER = -0x354              # r13 offset: COjyamaManager*
ACTIVE = 0x394                # manager: active item id
THROWER_OFF = 0x2FC           # manager: Thunder object
MODE = -0x1658                # r13 offset: video mode byte (table index)
BLINK = 0x80791638            # byte[mode*2]: initial +0x35 (FUN_80453900)
BANANA_VT, THUNDER_VT, POW_VT = 0x806CC2E0, 0x806CC7E8, 0x806CC638
BANANA_UPDATE = 0x8044EBEC
OBJ_UPDATE, OBJ_RESET, OBJ_DEACTIVATE = 0x80453764, 0x80453774, 0x80453804
BANANA_REACT, THUNDER_REACT = 0x80117A98, 0x801181EC
GET_MODEL, MODEL_SHOW, MODEL_POS, MODEL_ROT, MODEL_SCALE = 0x8037FD48, 0x80381E3C, 0x80381CAC, 0x80381CC4, 0x80381CE4
# Per-instance color (model set wrappers -> the instance's draw object, *(rec+0x1C)[k*0x54]+0x14):
# COLOR_ON(set, handle, on, k) +0x4C (FUN_80375a8c), COLOR(set, handle, r, g, b, a, k) +0x28..0x2B
# (FUN_80375cdc), COLOR_MODE(set, handle, mode, k) +0x2C (FUN_80375e9c). Drawn by FUN_8037a93c ->
# FUN_8052cbf8: mode 0 multiplies the material color by it (FUN_800a5388) -> GXSetChanMatColor(COLOR0A0).
COLOR_ON, COLOR, COLOR_MODE = 0x80381EEC, 0x80381EF4, 0x80381F04

TICK, RESET, CLEAR, MODEL, LAND = 0x80455560, 0x80455784, 0x8045893C, 0x80455B38, 0x80458F88
REACT, REACT_BASE, REACT_COUNT = 0x801170D4, 0x80117AF8, 0x80117DF8
CLEAR_DONE, MODEL_DONE, LAND_BACK = 0x804589B4, 0x8045615C, 0x80458F8C
LAND_PUFF_AT, LAND_STORE = 0x80459008, 0x8045902C
STOCK = {
    TICK: branch(TICK, OBJ_UPDATE, True),                 # bl 0x80453764
    RESET: branch(RESET, OBJ_RESET, True),                # bl 0x80453774
    CLEAR: branch(CLEAR, CLEAR_DONE),                     # b 0x804589b4
    MODEL: branch(MODEL, MODEL_DONE),                     # b 0x8045615c
    LAND: d_form(34, 4, 13, MODE),                        # lbz r4,-0x1658(r13)
    REACT: branch(REACT, THUNDER_REACT),                  # b 0x801181ec
    REACT_BASE: d_form(14, 31, 3, 0x1BC),                 # addi r31,r3,0x1bc
    REACT_COUNT: 0x28190005,                              # cmplwi r25,0x5
}
# Thunder vtable slot -> (stock Thunder method, POW method)
THUNDER_TO_POW = {
    0x1C: (0x80117830, 0x804591B0),   # radius
    0x20: (0x801177FC, 0x804591D4),   # height
    0x3C: (0x804536A0, 0x80459188),   # table value
    0x40: (0x80459D74, 0x80458B7C),   # update
    0x44: (0x80459DA4, 0x80458C64),   # reset
    0x48: (0x80459DB8, 0x80458D00),   # launch
    0x4C: (0x80459DB4, 0x80458C74),   # remove
    0x50: (0x80459E38, 0x80458E28),   # hit
}
THUNDER_SCALE_GETTER = (0x14, 0x8044F278)
VT_WORDS = 22
BANANA_VT_STOCK = {0x0C: 0x800FB580, 0x14: 0x8044F278, 0x2C: 0x8044F224, 0x30: 0x80117E2C, 0x34: 0x80453968,
                   0x40: BANANA_UPDATE, 0x44: 0x8044ECB4, 0x48: 0x8044ED58, 0x4C: 0x8044ECC0, 0x50: 0x8044F00C}

LAYOUT = {}


def f32(x):
    return struct.unpack(">I", struct.pack(">f", x))[0]


def r32(x):
    """Round to single precision."""
    return struct.unpack(">f", struct.pack(">f", x))[0]


def params():
    """Per bit (start dx, dz, center dx, dz, vx, vz, phase) relative to the landing point."""
    rows = []
    for i in range(BIT_COUNT):
        a = math.radians(ANGLES[i])
        ux, uz = math.cos(a), math.sin(a)
        r = SPREAD * SPREAD_JITTER[i]
        cx, cz = r * ux, r * uz
        turn = 1 if i % 2 == 0 else -1
        v = ORBIT_RADIUS * math.sin(OMEGA)          # the discrete orbit's speed for this radius
        rows.append((cx + ORBIT_RADIUS * ux, cz + ORBIT_RADIUS * uz, cx, cz,
                     -uz * v * turn, ux * v * turn, float(PHASES[i] % HOP_FRAMES)))
    return rows


def step(bit):
    """One frame of bit_update's motion on a dict {x, z, cx, cz, vx, vz, phase, ground} -> y (float32 math)."""
    for p, c, v in (("x", "cx", "vx"), ("z", "cz", "vz")):
        e = r32(bit[p] - bit[c])
        bit[v] = r32(bit[v] - r32(K) * e)
        bit[p] = r32(bit[p] + bit[v])
    t = r32(bit["phase"] + 1.0)
    if not t < HOP_FRAMES:
        t = r32(t - HOP_FRAMES)
    bit["phase"] = t
    return r32(r32(r32(r32(HOP_FRAMES - t) * t) * r32(HOP_C)) + bit["ground"])


def simulate(land, frames):
    """Positions of each bit over `frames` updates after landing at `land` (x, y, z): [[(x, y, z), ...], ...]."""
    out = []
    for row in params():
        b = dict(x=r32(land[0] + r32(row[0])), z=r32(land[2] + r32(row[1])), cx=r32(land[0] + r32(row[2])),
                 cz=r32(land[2] + r32(row[3])), vx=r32(row[4]), vz=r32(row[5]), phase=r32(row[6]), ground=land[1])
        track = []
        for _ in range(frames):
            y = step(b)
            track.append((b["x"], y, b["z"]))
        out.append(track)
    return out


def vcall(a, off):
    """Call the virtual method at vtable+off of the object in r3."""
    a.lwz(12, 0, 3).lwz(12, off, 12).mtctr(12).bctrl()


def bit_update(base, L):
    a = Asm(base)
    a.lbz(0, 0x3F, 3).cmpwi(0, 3).bne("tail")
    a.lhz(4, 0x3C, 3).cmpwi(4, 0).beq("move")                          # no limit
    a.addi(4, 4, -1).sth(4, 0x3C, 3).cmpwi(4, 0).bne("move")
    a.b(OBJ_DEACTIVATE)                                                # clears +0x36/+0x37, Banana remove: poof, state 0
    a.label("move")
    a.load_addr(4, L["bits"]).subf(6, 4, 3).rlwinm(6, 6, 30, 2, 31)   # (bit - BITS) / 4 = index * EXT_SIZE
    a.load_addr(4, L["ext"]).add(4, 4, 6)
    a.load_addr(5, L["consts"])
    a.lfs(0, 0, 5)                                                     # K
    for pos, ctr, vel in ((0x4, 0, 0x10), (0xC, 4, 0x18)):
        a.lfs(1, pos, 3).lfs(2, ctr, 4).fsubs(2, 1, 2)                # offset from the orbit center
        a.lfs(3, vel, 3).fnmsubs(3, 0, 2, 3).stfs(3, vel, 3)          # v -= K * offset
        a.fadds(1, 1, 3).stfs(1, pos, 3)                               # p += v
    a.lfs(1, 0x38, 3).lfs(2, 16, 5).fadds(1, 1, 2)                     # phase + 1
    a.lfs(2, 4, 5).fcmpo(1, 2).blt("in")
    a.fsubs(1, 1, 2)                                                   # wrap at HOP_FRAMES
    a.label("in")
    a.stfs(1, 0x38, 3)
    a.fsubs(3, 2, 1).fmuls(3, 3, 1).lfs(4, 8, 5).fmuls(3, 3, 4)       # (P - t) * t * C
    a.lfs(4, 0x14, 3).fadds(3, 3, 4)                                   # + ground
    a.lfs(5, 8, 4).lfs(4, 24, 5).fcmpo(5, 4).ble("landed")             # + the fall height while dropping
    a.lfs(6, 12, 4).lfs(4, 44, 5).fadds(6, 6, 4).fsubs(5, 5, 6)        # v += G; h -= v
    a.lfs(4, 24, 5).fcmpo(5, 4).bgt("falling")
    a.fmr(5, 4).fmr(6, 4)                                              # down: h = v = 0
    a.label("falling")
    a.stfs(5, 8, 4).stfs(6, 12, 4).fadds(3, 3, 5)
    a.label("landed")
    a.stfs(3, 0x8, 3)
    if SPIN:
        a.lfs(1, 0x20, 3).lfs(2, 12, 5).fadds(1, 1, 2).stfs(1, 0x20, 3)
    a.label("tail")
    a.b(BANANA_UPDATE)                                                 # ball contact / knock flight / poof
    return a


def noop(base, L):
    return Asm(base).blr()


def thrower_scale(base, L):
    return Asm(base).load_addr(3, L["consts"] + 32).blr()


def spawn(base, L):
    """r3 = thrower, r4 = landing point. Leaf: puts the bits down around it."""
    a = Asm(base)
    a.lfs(1, 0, 4).lfs(2, 4, 4).lfs(3, 8, 4)
    a.load_addr(9, L["consts"]).lfs(4, 20, 9).lfs(5, 24, 9)            # scale, 0
    a.lbz(9, MODE, 13).slwi(9, 9, 1).load_addr(10, BLINK).lbzx(9, 10, 9)
    a.load_addr(5, L["bits"]).load_addr(6, L["params"]).load_addr(7, L["ext"]).li(8, 0)
    a.load_addr(11, L["bit_vt"])
    a.label("loop")
    a.stw(11, 0, 5)
    a.lfs(6, 0, 6).fadds(6, 1, 6).stfs(6, 0x4, 5)
    a.stfs(2, 0x8, 5).stfs(2, 0x14, 5)                                 # y, ground y
    a.lfs(6, 4, 6).fadds(6, 3, 6).stfs(6, 0xC, 5)
    a.lfs(6, 8, 6).fadds(6, 1, 6).stfs(6, 0, 7)                        # orbit center
    a.lfs(6, 12, 6).fadds(6, 3, 6).stfs(6, 4, 7)
    a.lfs(6, 16, 6).stfs(6, 0x10, 5).lfs(6, 20, 6).stfs(6, 0x18, 5)   # drift velocity
    a.lfs(6, 24, 6).stfs(6, 0x38, 5)                                   # hop phase
    a.stfs(5, 8, 7).stfs(5, 12, 7)                                     # no fall
    for off in (0x1C, 0x20, 0x24):
        a.stfs(5, off, 5)
    for off in (0x28, 0x2C, 0x30):
        a.stfs(4, off, 5)
    a.li(10, 0).stb(10, 0x34, 5).li(10, LIFETIME).sth(10, 0x3C, 5).stb(9, 0x35, 5)
    a.li(10, 1).stb(10, 0x36, 5).stb(10, 0x37, 5)
    a.stb(8, 0x3E, 5).li(10, 3).stb(10, 0x3F, 5)
    a.addi(5, 5, 0x40).addi(6, 6, 28).addi(7, 7, EXT_SIZE).addi(8, 8, 1)
    a.cmpwi(8, BIT_COUNT).blt("loop")
    a.blr()
    return a


def drop(base, L):
    """r3 = bit index, f1/f2/f3 = where it appears (x, y, z), f4 = the ground y there. Leaf: the bit falls from
    there (fall height f2 - f4), then hops on a small orbit around (x, z) like a thrown one (row k % 4's)."""
    a = Asm(base)
    a.load_addr(5, L["bits"]).slwi(6, 3, 6).add(5, 5, 6)
    a.load_addr(7, L["ext"]).slwi(6, 3, 4).add(7, 7, 6)
    a.load_addr(6, L["params"]).rlwinm(8, 3, 0, 30, 31).mulli(8, 8, 28).add(6, 6, 8)
    a.load_addr(9, L["consts"]).lfs(5, 20, 9).lfs(6, 24, 9)            # scale, 0
    a.lbz(9, MODE, 13).slwi(9, 9, 1).load_addr(10, BLINK).lbzx(9, 10, 9)
    a.load_addr(10, L["bit_vt"]).stw(10, 0, 5)
    a.stfs(1, 0, 7).stfs(3, 4, 7)                                      # orbit center = where it drops
    a.lfs(0, 0, 6).lfs(7, 8, 6).fsubs(0, 0, 7).fadds(0, 1, 0).stfs(0, 0x4, 5)   # start on the orbit
    a.lfs(0, 4, 6).lfs(7, 12, 6).fsubs(0, 0, 7).fadds(0, 3, 0).stfs(0, 0xC, 5)
    a.stfs(2, 0x8, 5).stfs(4, 0x14, 5)                                 # y, ground y
    a.fsubs(0, 2, 4).stfs(0, 8, 7).stfs(6, 12, 7)                      # fall height, fall speed 0
    a.lfs(0, 16, 6).stfs(0, 0x10, 5).lfs(0, 20, 6).stfs(0, 0x18, 5)   # drift velocity
    a.lfs(0, 24, 6).stfs(0, 0x38, 5)                                   # hop phase
    for off in (0x1C, 0x20, 0x24):
        a.stfs(6, off, 5)
    for off in (0x28, 0x2C, 0x30):
        a.stfs(5, off, 5)
    a.li(10, 0).stb(10, 0x34, 5).sth(10, 0x3C, 5).stb(9, 0x35, 5)
    a.li(10, 1).stb(10, 0x36, 5).stb(10, 0x37, 5)
    a.stb(3, 0x3E, 5).li(10, 3).stb(10, 0x3F, 5)
    a.blr()
    return a


def each_bit(a, fn, count, in_use_only):
    """Call fn(bit) for bits 0..count-1 (r31 = bit, r30 = index; both must be saved by the caller)."""
    a.load_addr(31, LAYOUT["bits"]).li(30, 0)
    a.label("each")
    if in_use_only:
        a.lbz(0, 0x37, 31).cmpwi(0, 0).beq("next")
    a.mr(3, 31).bl(fn)
    a.label("next")
    a.addi(31, 31, 0x40).addi(30, 30, 1).cmpwi(30, count).blt("each")


def all_objects(fn, count, in_use_only):
    """A function: fn(r3 = thrower), then fn on the bits."""
    def build(base, L):
        a = Asm(base)
        a.stwu(1, -0x10, 1).mflr(0).stw(0, 0x14, 1).stw(31, 0xC, 1).stw(30, 0x8, 1)
        a.bl(fn)
        each_bit(a, fn, count, in_use_only)
        a.lwz(0, 0x14, 1).lwz(31, 0xC, 1).lwz(30, 0x8, 1).mtlr(0).addi(1, 1, 0x10).blr()
        return a
    return build


def clear_stub(base, L):
    """FUN_804588f4 (r3 = manager, r0 = active id; r30/r31 saved by it, LR too)."""
    a = Asm(base)
    a.cmpwi(0, ITEM_ID).beq("ours").b(CLEAR_DONE)
    a.label("ours")
    a.addi(3, 3, THROWER_OFF).bl(OBJ_DEACTIVATE)
    each_bit(a, OBJ_DEACTIVATE, BIT_TOTAL, True)
    a.b(CLEAR_DONE)
    return a


def model_stub(base, L):
    """FUN_80455ac4 (r5 = active id, r29 = manager, r30 = model set, r31 = hide all; r26-r28, f31 and the
    stack words 0x14..0x34 are free, as the Banana case uses them)."""
    a = Asm(base)
    a.cmpwi(5, ITEM_ID).beq("ours").b(MODEL_DONE)
    a.label("ours")
    a.mr(3, 30).li(4, MODEL_SLOT).bl(GET_MODEL).mr(27, 3)
    a.li(26, 0)
    a.label("loop")
    a.mr(3, 30).mr(4, 27).li(5, 0).mr(6, 26).bl(MODEL_SHOW)           # hide
    a.cmpwi(31, 0).bne("next")
    a.cmpwi(26, 0).bne("bit")
    a.addi(28, 29, THROWER_OFF).mr(3, 28)                              # instance 0: the thrower while it flies
    vcall(a, 0x2C)
    a.cmpwi(3, 0).bne("show")
    a.label("bit")
    a.load_addr(28, L["bits"]).slwi(0, 26, 6).add(28, 28, 0).mr(3, 28)
    vcall(a, 0x2C)                                                     # visible: state != 0 and +0x36
    a.cmpwi(3, 0).beq("next")
    a.label("show")
    a.mr(3, 30).mr(4, 27).li(5, 1).mr(6, 26).bl(MODEL_SHOW)
    a.mr(3, 28)
    vcall(a, 0x0C)                                                     # position
    a.load_addr(11, L["consts"])
    a.lfs(0, 0, 3).stfs(0, 0x2C, 1)
    a.lfs(0, 4, 3).lfs(1, 28, 11).fadds(0, 0, 1).stfs(0, 0x30, 1)
    a.lfs(0, 8, 3).fneg(0, 0).stfs(0, 0x34, 1)
    for off, sp in ((0x10, 0x20), (0x14, 0x14)):                       # rotation, scale
        a.mr(3, 28)
        vcall(a, off)
        for k in range(3):
            a.lfs(0, 4 * k, 3).stfs(0, sp + 4 * k, 1)
    for fn, sp in ((MODEL_POS, 0x2C), (MODEL_ROT, 0x20), (MODEL_SCALE, 0x14)):
        a.mr(3, 30).mr(4, 27).addi(5, 1, sp).mr(6, 26).bl(fn)
    # per-instance color: mode 0 (multiply), color on, RGBA = BIT_COLORS[k]
    a.mr(3, 30).mr(4, 27).li(5, 0).mr(6, 26).bl(COLOR_MODE)
    a.mr(3, 30).mr(4, 27).li(5, 1).mr(6, 26).bl(COLOR_ON)
    a.load_addr(11, L["colors"]).slwi(0, 26, 2).add(11, 11, 0)
    a.lbz(5, 0, 11).lbz(6, 1, 11).lbz(7, 2, 11).lbz(8, 3, 11)
    a.mr(3, 30).mr(4, 27).mr(9, 26).bl(COLOR)
    a.label("next")
    a.addi(26, 26, 1).cmpwi(26, BIT_TOTAL).blt("loop")
    a.b(MODEL_DONE)
    return a


def land_stub(base, L):
    """POW flight FUN_80458e80 after its ray hit (r30 = object, sp+0x40 = hit point, LR saved by it)."""
    a = Asm(base)
    a.lwz(12, 0, 30).load_addr(11, THUNDER_VT).cmpw(12, 11).beq("ours")
    a.word(STOCK[LAND]).b(LAND_BACK)
    a.label("ours")
    a.mr(3, 30).addi(4, 1, 0x40).bl(L["spawn"])
    a.li(0, 0).stb(0, 0x3A, 30)                                        # thrower spent (hidden, still in use)
    a.b(LAND_PUFF_AT if LAND_PUFF else LAND_STORE)
    return a


def react_base_stub(base, L):
    """FUN_80117a98 loop: r3 = manager + i*0x40, r0 = i*0x40."""
    a = Asm(base)
    a.lwz(12, MANAGER, 13).lwz(12, ACTIVE, 12).cmpwi(12, ITEM_ID).beq("ours")
    a.word(STOCK[REACT_BASE]).b(REACT_BASE + 4)
    a.label("ours")
    a.load_addr(31, L["bits"]).add(31, 31, 0).b(REACT_BASE + 4)
    return a


def react_count_stub(base, L):
    """FUN_80117a98 loop end (r25 = next index): id 6 walks all BIT_TOTAL bits, other items the stock 5."""
    a = Asm(base)
    a.lwz(12, MANAGER, 13).lwz(12, ACTIVE, 12).cmpwi(12, ITEM_ID).beq("ours")
    a.word(STOCK[REACT_COUNT]).b(REACT_COUNT + 4)
    a.label("ours")
    a.cmplwi(25, BIT_TOTAL).b(REACT_COUNT + 4)
    return a


def patch_word(dol, addr, expect, new):
    got = dol.u32(addr)
    assert got == expect, f"0x{addr:08X}: expected {expect:08X}, found {got:08X}"
    dol.w32(addr, new)


def _emit(space, build):
    at = space.here + (-len(space.blob) % 4)
    blob = build(at, LAYOUT).assemble()
    assert space.put(blob, align=4) == at
    return at


def _fill(space, addr, blob):
    space.blob[addr - space.base:addr - space.base + len(blob)] = blob


def apply(dol, code, data):
    for off, want in BANANA_VT_STOCK.items():
        assert dol.u32(BANANA_VT + off) == want, f"Banana vtable +0x{off:X} changed"
    assert len(BIT_COLORS) == BIT_COUNT and BIT_SLOTS >= 5
    for fn, target in ((COLOR_ON, 0x80383118), (COLOR, 0x80383158), (COLOR_MODE, 0x803831F0)):
        assert (dol.u32(fn), dol.u32(fn + 4)) == (0x80630004, branch(fn + 4, target)), f"0x{fn:08X} changed"
    L = LAYOUT
    L.clear()
    L["bit_vt"] = data.put(bytes(4 * VT_WORDS), 8)
    L["bits"] = data.put(bytes(0x40 * BIT_SLOTS), 32)
    L["ext"] = data.put(bytes(EXT_SIZE * BIT_TOTAL), 8)
    L["params"] = data.put(b"".join(struct.pack(">7f", *row) for row in params()), 8)
    L["colors"] = data.put(bytes(c for rgba in INSTANCE_COLORS for c in rgba), 4)
    L["consts"] = data.put(struct.pack(">12f", K, HOP_FRAMES, HOP_C, SPIN, 1.0, BIT_SCALE, 0.0, MODEL_Y,
                                       THROWER_SCALE, THROWER_SCALE, THROWER_SCALE, FALL_G), 8)
    for name, build in (("bit_update", bit_update), ("noop", noop), ("thrower_scale", thrower_scale),
                        ("spawn", spawn), ("drop", drop), ("tick", all_objects(OBJ_UPDATE, BIT_TOTAL, True)),
                        ("reset", all_objects(OBJ_RESET, BIT_SLOTS, False)), ("clear", clear_stub),
                        ("model", model_stub), ("land", land_stub), ("react_base", react_base_stub),
                        ("react_count", react_count_stub)):
        L[name] = _emit(code, build)
    vt = [dol.u32(BANANA_VT + 4 * i) for i in range(VT_WORDS)]
    vt[0x40 // 4], vt[0x48 // 4] = L["bit_update"], L["noop"]
    _fill(data, L["bit_vt"], struct.pack(f">{VT_WORDS}I", *vt))
    for k in range(BIT_SLOTS):                                         # static: reset runs before any spawn
        _fill(data, L["bits"] + 0x40 * k, struct.pack(">I", L["bit_vt"]))

    patch_word(dol, TICK, STOCK[TICK], branch(TICK, L["tick"], True))
    patch_word(dol, RESET, STOCK[RESET], branch(RESET, L["reset"], True))
    patch_word(dol, CLEAR, STOCK[CLEAR], branch(CLEAR, L["clear"]))
    patch_word(dol, MODEL, STOCK[MODEL], branch(MODEL, L["model"]))
    patch_word(dol, LAND, STOCK[LAND], branch(LAND, L["land"]))
    patch_word(dol, REACT, STOCK[REACT], branch(REACT, BANANA_REACT))
    patch_word(dol, REACT_BASE, STOCK[REACT_BASE], branch(REACT_BASE, L["react_base"]))
    patch_word(dol, REACT_COUNT, STOCK[REACT_COUNT], branch(REACT_COUNT, L["react_count"]))
    for off, (thunder, pow_) in THUNDER_TO_POW.items():
        assert dol.u32(POW_VT + off) == pow_, f"POW vtable +0x{off:X} changed"
        patch_word(dol, THUNDER_VT + off, thunder, pow_)
    off, stock = THUNDER_SCALE_GETTER
    patch_word(dol, THUNDER_VT + off, stock, L["thrower_scale"])
    return [f"star bits (item {ITEM_ID}): thrower = Thunder object with POW methods, {BIT_COUNT} bits at "
            f"0x{L['bits']:08X} (vtable 0x{L['bit_vt']:08X}), code 0x{L['bit_update']:08X}-0x{code.here:08X}, "
            f"model slot 0x{MODEL_SLOT:02X} x{BIT_TOTAL}; 8 hooks + {len(THUNDER_TO_POW) + 1} Thunder vtable words"]
