"""Lemmy's balls look like his circus ball (Nick: yellow with orange stars), not fireballs.

His item is still the Fireball (koopa_items LEMMY: high bounces, knockback), but:
  - no flame trail: koopa_items' FOLLOW stub skips the trail start (bl FUN_800fb890 at 0x80456940) for LEMMY;
  - a ball model (models/work/lemmy_ball/prop.bin, scripts/lemmy_ball_obj.py + build_prop, 1.0 m across,
    origin at its centre) is drawn at each flying ball (state +0x3C == 2 in ludwig_fire's pool): model-set
    slot SLOT with N instances, loaded from item package slot 0x2A's unused tail at OFF (wendy_rings' LOAD /
    FREE handle every extra model), drawn from wendy_rings' DRAW stub (draw_code), centre MODEL_Y above the
    ball's position (a bouncing ball rests 0.001 above the ground).
"""
from ppc import ha, lo
from creators import items as _presets   # the one source of the tuning values below (scripts/creators/presets)

SLOT, OFF = 0x81, 0xAF00
N = _presets.block("lemmy", "launch")["count"]   # 3: one model per ball Lemmy throws
MODEL_Y = _presets.block("lemmy", "look")["height"]   # 0.5
GET_MODEL, MODEL_SHOW, MODEL_POS, MODEL_ROT, MODEL_SCALE = 0x8037FD48, 0x80381E3C, 0x80381CAC, 0x80381CC4, 0x80381CE4
MANAGER, ACTIVE, FIREBALL = -0x354, 0x394, 1


def draw_code(a, flag, arr, consts, lemmy):
    """Emitted inside wendy_rings' DRAW stub (r30 = model set, r31 = hide all; r26-r28 free). consts: 3 floats
    MODEL_Y, 0.0, 1.0 (data)."""
    a.mr(3, 30).li(4, SLOT).bl(GET_MODEL).mr(27, 3)
    a.cmpwi(27, -1).beq("lm_done")
    a.li(26, 0)
    a.label("lm_loop")
    a.mr(3, 30).mr(4, 27).li(5, 0).mr(6, 26).bl(MODEL_SHOW)                  # hide
    a.cmpwi(31, 0).bne("lm_next")
    a.lis(12, ha(flag)).lbz(12, lo(flag), 12)
    if isinstance(lemmy, int):
        a.cmpwi(12, lemmy).bne("lm_next")
    else:                                                                      # + new items with this model
        for k, vid in enumerate(lemmy):
            a.cmpwi(12, vid).beq("lm_mine")
        a.b("lm_next")
        a.label("lm_mine")
    a.lwz(28, MANAGER, 13).cmpwi(28, 0).beq("lm_next")
    a.lwz(0, ACTIVE, 28).cmpwi(0, FIREBALL).bne("lm_next")
    a.load_addr(28, arr).slwi(0, 26, 6).add(28, 28, 0)
    a.lbz(0, 0x3C, 28).cmpwi(0, 2).bne("lm_next")                             # flying
    a.bl("lm_place")
    a.label("lm_next")
    a.addi(26, 26, 1).cmpwi(26, N).blt("lm_loop")
    a.b("lm_done")
    a.label("lm_place")                                                      # own frame
    a.stwu(1, -0x40, 1).mflr(0).stw(0, 0x44, 1)
    a.mr(3, 30).mr(4, 27).li(5, 1).mr(6, 26).bl(MODEL_SHOW)
    a.load_addr(11, consts)
    a.lfs(0, 4, 28).stfs(0, 0x2C, 1)
    a.lfs(0, 8, 28).lfs(1, 0, 11).fadds(0, 0, 1).stfs(0, 0x30, 1)
    a.lfs(0, 0xC, 28).fneg(0, 0).stfs(0, 0x34, 1)
    a.lfs(0, 4, 11).stfs(0, 0x20, 1).stfs(0, 0x24, 1).stfs(0, 0x28, 1)
    a.lfs(0, 8, 11).stfs(0, 0x14, 1).stfs(0, 0x18, 1).stfs(0, 0x1C, 1)
    for fn, sp in ((MODEL_POS, 0x2C), (MODEL_ROT, 0x20), (MODEL_SCALE, 0x14)):
        a.mr(3, 30).mr(4, 27).addi(5, 1, sp).mr(6, 26).bl(fn)
    a.lwz(0, 0x44, 1).mtlr(0).addi(1, 1, 0x40).blr()
    a.label("lm_done")


def draw_icon(scale=8):
    """Yellow ball with orange stars and a dark outline (27 x 29). -> RGBA image."""
    import math
    from PIL import Image, ImageDraw
    W, H = 27 * scale, 29 * scale
    img = Image.new("RGBA", (W, H), (0, 0, 0, 0))
    d = ImageDraw.Draw(img)
    cx, cy, r = W / 2, H / 2 + 0.5 * scale, 11.5 * scale
    d.ellipse((cx - r - 1.5 * scale, cy - r - 1.5 * scale, cx + r + 1.5 * scale, cy + r + 1.5 * scale), fill=(90, 50, 0, 255))
    d.ellipse((cx - r, cy - r, cx + r, cy + r), fill=(255, 214, 40, 255))

    def star(x, y, rr):
        d.polygon([(x + (rr if k % 2 == 0 else rr * 0.45) * math.cos(math.pi * k / 5 - math.pi / 2),
                    y + (rr if k % 2 == 0 else rr * 0.45) * math.sin(math.pi * k / 5 - math.pi / 2)) for k in range(10)],
                  fill=(255, 130, 20, 255))
    star(cx, cy + 0.1 * r, r * 0.55)
    star(cx - r * 0.62, cy - r * 0.45, r * 0.22)
    star(cx + r * 0.6, cy - r * 0.5, r * 0.2)
    d.ellipse((cx - r * 0.6, cy - r * 0.75, cx - r * 0.25, cy - r * 0.5), fill=(255, 250, 215, 255))
    return img.convert("RGBa").resize((27, 29), Image.LANCZOS).convert("RGBA")
