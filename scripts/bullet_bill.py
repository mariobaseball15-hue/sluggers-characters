"""Roy and Morton shoot a Bullet Bill (Nick, 2026-09-25; replaces their quake POW).

Their item (koopa_items BILL) is one Fireball flying level (no gravity, no upward launch speed; koopa_items'
leader-only / level-flight stubs) at BILL_MULT, homing on the fielder nearest the cursor when fired (homing, below), with no
flame trail, knocking a hit fielder down and sliding (ice_item's knock). It looks like Bowser Jr.
Playroom's Bullet Bill: that stadium's model (dt_na dir 137 file 0xA2 `sta09_killer`, 0xB9E0 B; static, no
skin) is copied into item package slot 0x2A's unused tail at OFF and loaded as model-set slot SLOT (wendy_rings'
LOAD / FREE), and draw_code (in wendy_rings' DRAW stub) puts it on the first flying ball of ludwig_fire's pool
while the Bill is the active item: position (z negated), scale SCALE (the model is 2.7 m across its fins),
yaw = pi + atan2(-vx, vz) from the ball's velocity, the Playroom's own formula (FUN_802f67dc: yaw 0 faces +z in
field space; the model set takes radians, as its flight code's sin / cos of +0x24 shows).
"""
import struct

from ppc import ha, lo
from creators import items as _presets   # the one source of the tuning values below (scripts/creators/presets)
import ludwig_fire

SLOT, OFF = 0x82, 0x15800
SRC_DIR, SRC_FILE, SRC_LEN = 137, 0xA2, 0xB9E0
MODEL_Y = _presets.block("bullet-bill", "look")["height"]   # 0.9: drawn this far above the ball: the model is centred on its origin, 1.58 m tall (Nick: in the ground)
SCALE = _presets.block("bullet-bill", "look")["scale"]   # 1.0: the Playroom's own size (2.8 m long); at 0.5 it was barely visible from the overhead camera (Nick)
N_BALLS = ludwig_fire.N_BALLS   # the thrown-ball pool (one source)
GET_MODEL, MODEL_SHOW, MODEL_POS, MODEL_ROT, MODEL_SCALE = 0x8037FD48, 0x80381E3C, 0x80381CAC, 0x80381CC4, 0x80381CE4
ATAN2 = 0x8053E1E4                               # f1 = atan2(f1, f2)
MANAGER, ACTIVE, FIREBALL = -0x354, 0x394, 1


def block(dol, dat_path):
    """The Bullet Bill model block from a dt_na.dat (the player's clean game's: charbuild, draw_icon)."""
    import dtna_toc
    off, n = dtna_toc.toc(dol)[SRC_DIR][SRC_FILE]
    assert n == SRC_LEN, f"dir {SRC_DIR} file 0x{SRC_FILE:X} is 0x{n:X} B, expected 0x{SRC_LEN:X}"
    with open(dat_path, "rb") as f:
        f.seek(off)
        return f.read(n)


def consts():
    """SCALE, 0.0, pi, MODEL_Y (data for draw_code)."""
    import math
    return struct.pack(">4f", SCALE, 0.0, math.pi, MODEL_Y)


def draw_code(a, flag, arr, c, bill):
    """Emitted inside wendy_rings' DRAW stub (r30 = model set, r31 = hide all; r26-r28, sp+0x14..0x34 free).
    c: consts() in data."""
    a.mr(3, 30).li(4, SLOT).bl(GET_MODEL).mr(27, 3)
    a.cmpwi(27, -1).beq("bb_done")
    a.mr(3, 30).mr(4, 27).li(5, 0).li(6, 0).bl(MODEL_SHOW)                   # hidden unless
    a.cmpwi(31, 0).bne("bb_done")
    a.lis(12, ha(flag)).lbz(12, lo(flag), 12)                                # the Bill
    if isinstance(bill, int):
        a.cmpwi(12, bill).bne("bb_done")
    else:                                                                      # + new items with this model
        for vid in bill:
            a.cmpwi(12, vid).beq("bb_mine")
        a.b("bb_done")
        a.label("bb_mine")
    a.lwz(28, MANAGER, 13).cmpwi(28, 0).beq("bb_done")
    a.lwz(0, ACTIVE, 28).cmpwi(0, FIREBALL).bne("bb_done")                   # is the active item
    a.load_addr(28, arr).li(26, N_BALLS)
    a.label("bb_find")
    a.lbz(0, 0x3C, 28).cmpwi(0, 2).beq("bb_fly")                             # and a ball is flying
    a.addi(28, 28, 0x40).addi(26, 26, -1).cmpwi(26, 0).bgt("bb_find")
    a.b("bb_done")
    a.label("bb_fly")
    a.mr(3, 30).mr(4, 27).li(5, 1).li(6, 0).bl(MODEL_SHOW)
    a.load_addr(11, c)
    a.lfs(0, 4, 28).stfs(0, 0x2C, 1)
    a.lfs(0, 8, 28).lfs(1, 0xC, 11).fadds(0, 0, 1).stfs(0, 0x30, 1)          # + MODEL_Y
    a.lfs(0, 0xC, 28).fneg(0, 0).stfs(0, 0x34, 1)
    a.lfs(0, 0, 11).stfs(0, 0x14, 1).stfs(0, 0x18, 1).stfs(0, 0x1C, 1)       # scale
    a.lfs(0, 4, 11).stfs(0, 0x20, 1).stfs(0, 0x28, 1)                       # no pitch / roll
    a.lfs(1, 0x10, 28).fneg(1, 1).lfs(2, 0x18, 28).bl(ATAN2)                 # atan2(-vx, vz)
    a.load_addr(11, c).lfs(0, 8, 11).fadds(1, 1, 0).stfs(1, 0x24, 1)          # + pi
    for fn, sp in ((MODEL_POS, 0x2C), (MODEL_ROT, 0x20), (MODEL_SCALE, 0x14)):
        a.mr(3, 30).mr(4, 27).addi(5, 1, sp).li(6, 0).bl(fn)
    a.label("bb_done")


def draw_icon(size=(27, 29), ss=8, yaw=-1.25, pitch=0.25):
    """The HUD icon: the game's own Bullet Bill model (dir 137 file 0xA2) rendered with its texture, nose to
    the right, three-quarter view, simple light (Nick: the hand-drawn one looked like MS Paint). -> RGBA.
    The model is the player's clean game's (game_source.root()); Extra Innings' copy, read before, is byte-identical
    (and so is the icon: checked 2026-09-26)."""
    import numpy as np
    from PIL import Image
    from dol import Dol
    from mss_model import Model
    from recolor_block import decode
    import game_source
    src = game_source.root()
    blk = block(Dol(src / "sys/main.dol"), src / "files/dt_na.dat")
    m = Model(blk)
    sub = m.submeshes[0]
    pos = np.array(sub.position.values(m.b)).reshape(-1, 3)
    uv = np.array(sub.uvs[0].values(m.b)).reshape(-1, 2)
    nrm = np.array(sub.normal.values(m.b)).reshape(-1, 3)
    tex = np.asarray(decode(blk, m.textures[0]).convert("RGBA"), dtype=float)
    th, tw = tex.shape[:2]
    cy, sy, cp, sp = np.cos(yaw), np.sin(yaw), np.cos(pitch), np.sin(pitch)
    rot = np.array([[1, 0, 0], [0, cp, -sp], [0, sp, cp]]) @ np.array([[cy, 0, sy], [0, 1, 0], [-sy, 0, cy]])
    p = pos @ rot.T
    n = nrm @ rot.T
    n /= np.maximum(np.linalg.norm(n, axis=1, keepdims=True), 1e-9)
    W, H = size[0] * ss, size[1] * ss
    lo_, hi_ = p[:, :2].min(0), p[:, :2].max(0)
    k = 0.88 * min(W / (hi_[0] - lo_[0]), H / (hi_[1] - lo_[1]))
    sx = (p[:, 0] - (lo_[0] + hi_[0]) / 2) * k + W / 2
    sy_ = H / 2 - (p[:, 1] - (lo_[1] + hi_[1]) / 2) * k
    img = np.zeros((H, W, 4))
    zb = np.full((H, W), -1e9)
    light = np.array([-0.4, 0.6, 0.7]) / np.linalg.norm([-0.4, 0.6, 0.7])
    for *_, tris in sub.groups(m.b):
        for t in tris:
            pi_ = [c["position"] for c in t]
            ti = [c["tex0"] for c in t]
            ni = [c["normal"] for c in t]
            xs, ys, zs = sx[pi_], sy_[pi_], p[pi_, 2]
            x0, x1 = int(max(0, np.floor(xs.min()))), int(min(W - 1, np.ceil(xs.max())))
            y0, y1 = int(max(0, np.floor(ys.min()))), int(min(H - 1, np.ceil(ys.max())))
            den = (ys[1] - ys[2]) * (xs[0] - xs[2]) + (xs[2] - xs[1]) * (ys[0] - ys[2])
            if abs(den) < 1e-9 or x1 < x0 or y1 < y0:
                continue
            gx, gy = np.meshgrid(np.arange(x0, x1 + 1) + 0.5, np.arange(y0, y1 + 1) + 0.5)
            a = ((ys[1] - ys[2]) * (gx - xs[2]) + (xs[2] - xs[1]) * (gy - ys[2])) / den
            b = ((ys[2] - ys[0]) * (gx - xs[2]) + (xs[0] - xs[2]) * (gy - ys[2])) / den
            c = 1 - a - b
            inside = (a >= 0) & (b >= 0) & (c >= 0)
            if not inside.any():
                continue
            z = a * zs[0] + b * zs[1] + c * zs[2]
            win = zb[y0:y1 + 1, x0:x1 + 1]
            draw = inside & (z > win)
            u = a * uv[ti[0], 0] + b * uv[ti[1], 0] + c * uv[ti[2], 0]
            v = a * uv[ti[0], 1] + b * uv[ti[1], 1] + c * uv[ti[2], 1]
            col = tex[(np.mod(v, 1) * th).astype(int).clip(0, th - 1), (np.mod(u, 1) * tw).astype(int).clip(0, tw - 1)]
            nn = a[..., None] * n[ni[0]] + b[..., None] * n[ni[1]] + c[..., None] * n[ni[2]]
            shade = 0.75 + 0.7 * np.clip(nn @ light, 0, 1)                   # bright: it reads at 27 x 29
            col = col.copy()
            col[..., :3] *= shade[..., None]
            col[..., 3] = 255
            win[draw] = z[draw]
            img[y0:y1 + 1, x0:x1 + 1][draw] = col[draw]
    out = Image.fromarray(img.clip(0, 255).astype(np.uint8), "RGBA")
    out = out.convert("RGBa").resize(size, Image.LANCZOS).convert("RGBA")
    from PIL import ImageFilter                                              # a light outline, as the stock
    ring = out.getchannel("A").point(lambda v: 255 if v > 60 else 0).filter(ImageFilter.MaxFilter(3))   # icons have
    edge = Image.new("RGBA", size, (235, 235, 240, 255))
    edge.putalpha(ring)
    edge.alpha_composite(out)
    return edge


# --- homing: the fielder nearest the cursor when it's fired (Nick) ----------------------------------
FIELDER_ARRAYS = (0x80708D9C, 0x80708DC0, 0x80708D78)   # 9 player pointers each (octoomba_hazard's fallback order)
TURN_DEG = _presets.block("bullet-bill", "move")["home"]["turn_deg"]      # 1.5 per frame toward the target (3.0 was too good; Nick)
SPAWN_DIST = _presets.block("bullet-bill", "move")["home"]["spawn_dist"]  # 60 m: it appears this far short of its target (10 was too close; Nick: it
#                                                         came from the on-deck side, off screen, too hard to use)
LAUNCH, LAUNCH_ORIG = 0x80453824, 0x9421FFD0            # FUN_80453824(obj, &aim point, ...): stwu r1,-0x30(r1)




def homing_consts(turn_deg=None, spawn_dist=None, target=None):
    """homing()'s constants: TURN_DEG / SPAWN_DIST, or a new item's own; + its target slot (homing(target=))."""
    import math
    turn_deg = TURN_DEG if turn_deg is None else turn_deg
    spawn_dist = SPAWN_DIST if spawn_dist is None else spawn_dist
    t = math.radians(turn_deg)
    return struct.pack(">9f", 1.0e9, math.cos(t), math.sin(t), 0.0, spawn_dist, spawn_dist ** 2, 0.5, 1.5, 1.0) + \
        (struct.pack(">i", target) if target is not None else b"")


def aim_hook(dol, code, flag, state, bill):
    """Every item launch goes through FUN_80453824 (r4 = the aim point, the ball's coordinates). For the Bill,
    keep the aim point (state +0..+8) and unlock the target (state +0xC = 0); homing locks it on its first
    frame. r0, r12 and f0 are free at its first instruction. bill: its variant id, or a tuple (with new homing
    items)."""
    from ppc import Asm
    got = dol.u32(LAUNCH)
    assert got == LAUNCH_ORIG, f"0x{LAUNCH:08X}: {got:08X}"
    at = code.here + (-code.here % 4)
    a = Asm(at)
    a.lis(12, ha(flag)).lbz(12, lo(flag), 12)
    if isinstance(bill, int):
        a.cmpwi(12, bill).bne("out")
    else:
        for vid in bill:
            a.cmpwi(12, vid).beq("keep")
        a.b("out")
        a.label("keep")
    # The aim point's z is the other way round from the fielders' and the ball's (koopa-items-23's log: aimed
    # at the right fielder at (43.7, 54.0), r4 held (51.1, 0, -54.0)); homing picks the sign on its first frame
    # from the ball's own heading. (r5 / r6 aren't the throw and its direction: r6 was (9.0, 0, -0.8).)
    a.lfs(1, 0, 4).lfs(2, 8, 4)
    a.load_addr(12, state)
    a.stfs(1, 0, 12).lfs(0, 4, 4).stfs(0, 4, 12).stfs(2, 8, 12)
    a.li(0, 0).stw(0, 0xC, 12)
    a.label("out")
    a.word(LAUNCH_ORIG).b(LAUNCH + 4)
    assert code.put(a.assemble(), 4) == at
    dol.w32(LAUNCH, Asm(LAUNCH).b(at).assemble_word())


def homing(code, c, state, target=None):
    """Leaf, bl'd from koopa_items' GRAVITY stub for the Bill (r3 = the ball, in FUN_804534c4 where r0, r4-r10,
    f0 and f2-f4 are live: it saves what it touches and uses f5-f13 only, except the jump, which moves f4 / f3 on purpose). On its first frame it locks onto the
    fielder who isn't down (+0x23F) nearest to the aim point (state +0..; aim_hook) and keeps him (state +0xC;
    -1 = nobody). Each frame the ball's heading turns TURN_DEG toward him (velocity +0x10 / +0x18 rotated, speed
    kept); once he's down it flies straight. c: homing_consts() in data. target: a fielder slot (0..8: P, C, 1B,
    2B, 3B, SS, LF, CF, RF; c +0x24): only he can be locked (none if he's down: it flies straight). -> address."""
    from ppc import Asm
    at = code.here + (-code.here % 4)
    a = Asm(at)
    a.stwu(1, -0x20, 1).stw(0, 8, 1).stw(4, 0xC, 1).stw(5, 0x10, 1).stw(8, 0x14, 1)
    a.load_addr(11, state).lwz(5, 0xC, 11).cmpwi(5, 0).bne("locked")
    a.lfs(5, 0, 11).lfs(6, 8, 11)                                             # the aim point, its z
    a.lfs(7, 4, 3).fsubs(7, 5, 7).lfs(8, 0x10, 3).fmuls(7, 7, 8)              # the way the ball is heading:
    a.lfs(8, 0xC, 3).fsubs(9, 6, 8).fneg(10, 6).fsubs(10, 10, 8)              # (ax - bx) vx + (+-az - bz) vz
    a.lfs(11, 0x18, 3).fmadds(9, 9, 11, 7).fmadds(10, 10, 11, 7)
    a.fcmpo(10, 9).ble("aimz").fneg(6, 6)
    a.label("aimz")
    a.load_addr(11, c).lfs(13, 0, 11)
    a.li(8, -1).li(4, 0)
    a.label("loop")
    a.slwi(0, 4, 2)
    for k, arr in enumerate(FIELDER_ARRAYS):
        a.load_addr(12, arr).lwzx(5, 12, 0).cmpwi(5, 0)
        a.bne("have") if k < len(FIELDER_ARRAYS) - 1 else a.beq("skip")
    a.label("have")
    if target is not None:                                                    # its own target: that slot only
        a.cmpwi(4, target).bne("skip")
    a.lbz(0, 0x23F, 5).cmpwi(0, 0).bne("skip")                               # knocked down: not a target
    a.lfs(7, 4, 5).fsubs(7, 7, 5).lfs(8, 0xC, 5).fsubs(8, 8, 6)
    a.fmuls(9, 7, 7).fmadds(9, 8, 8, 9).fcmpo(9, 13).bge("skip")
    a.fmr(13, 9).mr(8, 5)
    a.label("skip")
    a.addi(4, 4, 1).cmpwi(4, 9).blt("loop")
    a.load_addr(11, state).stw(8, 0xC, 11).mr(5, 8)
    a.cmpwi(8, -1).beq("locked")
    a.lfs(10, 4, 8).lfs(7, 4, 3).fsubs(10, 10, 7)                             # dx, dz to him
    a.lfs(11, 0xC, 8).lfs(7, 0xC, 3).fsubs(11, 11, 7)
    a.fmuls(9, 10, 10).fmadds(9, 11, 11, 9)                                   # d^2
    a.load_addr(11, c).lfs(12, 0x14, 11).fcmpo(9, 12).ble("locked")           # already close
    a.frsqrte(13, 9)                                                          # 1/d, one Newton step:
    a.fmuls(12, 13, 13).fmuls(12, 12, 9).lfs(7, 0x18, 11).fmuls(12, 12, 7)    # y (1.5 - 0.5 d^2 y^2)
    a.lfs(7, 0x1C, 11).fsubs(12, 7, 12).fmuls(13, 13, 12)
    a.lfs(12, 0x10, 11).lfs(7, 0x20, 11).fnmsubs(12, 12, 13, 7)               # k = 1 - SPAWN_DIST / d
    # pos += k (dx, dz). FUN_804534c4 already has this frame's step in its own frame (sp+0x40 / +0x48 = pos +
    # velocity, written back to the ball after its ground ray; the ray starts at f4 / f3 = x / z): move those
    # (the caller's sp is ours + 0x20), or the jump is undone (koopa-items-28: the Bill never came on screen)
    a.lfs(7, 4, 3).fmadds(7, 10, 12, 7).stfs(7, 4, 3).fmr(4, 7)
    a.lfs(8, 0x10, 3).fadds(8, 7, 8).stfs(8, 0x60, 1)
    a.lfs(7, 0xC, 3).fmadds(7, 11, 12, 7).stfs(7, 0xC, 3).fmr(3, 7)
    a.lfs(8, 0x18, 3).fadds(8, 7, 8).stfs(8, 0x68, 1)
    a.label("locked")
    a.cmpwi(5, -1).beq("done")                                                # nobody to chase
    a.lbz(0, 0x23F, 5).cmpwi(0, 0).bne("done")                               # he's down: straight on
    a.lfs(10, 4, 5).lfs(7, 4, 3).fsubs(10, 10, 7)                             # dx, dz from the ball
    a.lfs(11, 0xC, 5).lfs(7, 0xC, 3).fsubs(11, 11, 7)
    a.lfs(7, 0x10, 3).lfs(8, 0x18, 3)
    a.fmuls(9, 7, 11).fmuls(12, 8, 10).fsubs(9, 9, 12)                        # vx*dz - vz*dx
    a.load_addr(11, c).lfs(12, 8, 11).lfs(6, 0xC, 11)                         # sin; 0 (f0 is live)
    a.fcmpo(9, 6).bge("ccw").fneg(12, 12)                                     # turn toward him
    a.label("ccw")
    a.lfs(13, 4, 11)                                                          # cos
    a.fmuls(9, 7, 13).fnmsubs(9, 8, 12, 9)                                    # vx c - vz s
    a.fmuls(10, 7, 12).fmadds(10, 8, 13, 10)                                  # vx s + vz c
    a.stfs(9, 0x10, 3).stfs(10, 0x18, 3)
    a.label("done")
    a.lwz(0, 8, 1).lwz(4, 0xC, 1).lwz(5, 0x10, 1).lwz(8, 0x14, 1).addi(1, 1, 0x20).blr()
    got = code.put(a.assemble(), 4)
    assert got == at
    return at
