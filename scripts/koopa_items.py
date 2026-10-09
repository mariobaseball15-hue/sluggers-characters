"""Koopaling items (Nick, 2026-09-25): each Koopaling always brings their own item, stronger than the
roulette's, when they are the on-deck batter (the item's user, batter_items.py), regardless of chemistry.
The roulette never rolls them (weight 0: starbits_roulette forced ids).

Like Ice (ice_item.py), each is its own item id until it is used; at use (ice_item's use stub) it turns into
the stock item it is built on and the variant byte (ice_item.LAYOUT["variant"]) says which one, for these hooks:

  LEMMY (8)  Fireball x3, recoloured. The balls bounce high (bounce factor / minimum hop speed, BOUNCE) and
             a hit fielder is knocked down and slides far (ice_item's knock case: FUN_80128b48 pushes away
             from the ball, then slide speed +0x130 = KNOCK_SPEED and slide time +0x206 = KNOCK_FRAMES; stock
             knockdown is 0.3 for 40 frames, about 8 m; this is about 60 m).
  BILL (9)   Roy, Morton: a Bullet Bill (bullet_bill.py): one Fireball, flying level (LAUNCH_VY 0, gravity 0)
             at BILL_MULT, homing on the fielder nearest the cursor when fired and appearing SPAWN_DIST (60 m) short of him (bullet_bill.aim_hook + homing), no trail, knockdown with the long slide (ice_item's knock), drawn
             as Bowser Jr. Playroom's Bullet Bill. (It was a POW that stunned every fielder; Nick found it a bit
             broken and asked for Bullet Bills instead, 2026-09-25.)
  IGGY (10), LARRY (11)  one Fireball, FAST_MULT times as fast, along the ground, recoloured: the follower
             loop in FUN_80456710 (0x8045693C) stops after the leader, the leader's launch speed (lfs f31,4(r4)
             at 0x804532C8) is multiplied, it leaves the hand with no upward speed (LAUNCH_VY), falls with
             FAST_GRAVITY (so it is down within a few frames of the throw), and on the ground its bounce is 0
             (BOUNCE stub) with no bounce puff (PUFF): the update's ground hit puts it on the surface each frame,
             so it skims along the ground (Nick: slightly slower than 4x, always on the ground, no bounce).

Sites (each asserts the stock word):
  FOLLOW 0x8045693C  rlwinm r3,r31,0,24,31 (use: fireball follower loop)       -> LEAD: leader only
  SPEED  0x804532C8  lfs f31,0x4(r4) (Fire launch FUN_8045327c)                 -> x FAST_MULT / BILL_MULT
  BOUNCE 0x804535E8  lfs f2,0x10(r3) + lfs f0,0x14(r3) (Fire update bounce)     -> LEMMY: BOUNCE; LEAD: 0, 0
  LAUNCH_VY 0x80453318 stfs f0,0x14(r31) (launch vertical speed = table +8)     -> LEAD: 0
  GRAVITY 0x80453564 lfs f1,0xc(r11) (update: gravity)                          -> FAST: FAST_GRAVITY; BILL: 0
  PUFF   0x8045363C  bl 0x801010e8 (bounce puff at the ground hit)              -> LEAD: none
  CPU    0x800C6288  cmpwi r4,-1 (CPU batter FUN_800c61f0 indexes 0x80624808 by the slot item, 8 per row):
                     ids 7.. read as the stock item they become (they read past the row before).

  WENDY (12)  the POW's lob, landing as rings that stay for the half-inning: wendy_rings.py.

  LUDWIG (13)  five Fireballs, purple: ludwig_fire.py (the pool moves to a 5-ball array; FOLLOW caps other
             throws at 3 and makes Ludwig's balls 3..4 followers).
"""
import struct

from ppc import Asm, ha, lo
from layout import stock_icon  # (a stock item icon -> RGBA; layout.py, shared with captains)
from creators import items as _presets   # the one source of the tuning values below (scripts/creators/presets)

LEMMY, BILL, IGGY, LARRY, WENDY, LUDWIG = 8, 9, 10, 11, 12, 13   # WENDY: wendy_rings.py, LUDWIG: ludwig_fire.py
FIREBALL, POW = 1, 3
VARIANTS = [(LEMMY, FIREBALL), (BILL, FIREBALL), (IGGY, FIREBALL), (LARRY, FIREBALL), (WENDY, POW),
            (LUDWIG, FIREBALL)]                                        # (id, stock item), ids 8..
# hue turn from orange (, lighten toward white), per the games (Super Mario Wiki: Iggy's green fireballs, Larry's
# "sky cyan" ones in NSMBU, Ludwig's blue ones in NSMBW / NSMBU; Nick asked for colours close to canon). Ludwig's is
# a deeper blue than Ice's (0.52). Lemmy: no trail (lemmy_balls)
HUES = {vid: _presets.hue(_presets.block(p, "look")["trail"]) for vid, p in ((IGGY, "iggy"), (LARRY, "larry"),
                                                                           (LUDWIG, "ludwig"))}
#                                 (0.25, (0.45, 0.3), 0.56) BILL: no trail (its grey smoke drew as a white blob)
LUDWIG_MULT = _presets.block("ludwig", "launch")["speed"]   # 1.25: Ludwig's five: launch speed x (Nick: a slight boost), leader and followers
FAST = (IGGY, LARRY)
assert _presets.block("iggy", "launch") == _presets.block("larry", "launch"), "Iggy's and Larry's throws share FAST's hooks"
LEAD = FAST + (BILL,)           # one ball, level launch, no bounce or puff
BILL_MULT = _presets.block("bullet-bill", "launch")["speed"]   # 0.8: the Bullet Bill's launch speed x (Nick: 1.1 with the 10 m spawn was way too overpowered;
#                                 before the spawn: it starts off screen at the on-deck side and at 0.6-0.8 rarely reached the camera; 1.5 was way too fast;
#                                 Nick). It homes on the fielder nearest the cursor when fired (bullet_bill)
FAST_MULT = _presets.block("iggy", "launch")["speed"]     # 2.4: launch speed x (stock 0.4 / 0.6 per frame: 0.96 / 1.44); 4.0, 3.25, 2.75 were too fast (Nick)
FAST_GRAVITY = _presets.block("iggy", "launch")["gravity"]   # 0.1 per frame (stock 0.02): from the hand to the ground in ~5 frames
BOUNCE = tuple(_presets.block("lemmy", "move")["bounce"][k] for k in ("factor", "min_hop"))   # (0.8, 0.35) Lemmy: bounce factor (stock 0.3), minimum hop speed (stock 0.3): ~3 m high hops
LEMMY_MULT = _presets.block("lemmy", "launch")["speed"]   # 0.8: Lemmy's launch speed x: with BOUNCE, ~11 m per hop (0.65: ~9 m; Nick: a little faster; 16 m was too long)
KNOCK_SPEED, KNOCK_FRAMES = (_presets.block("lemmy", "effect")[k] for k in ("slide_speed", "slide_frames"))   # 2.0, 50
BILL_KNOCK_SPEED, BILL_KNOCK_FRAMES = (_presets.block("bullet-bill", "effect")[k]
                                       for k in ("slide_speed", "slide_frames"))   # 0.3, 15: the Bill's light knock: stock slide speed, 15 frames (20 still a bit much) (Lemmy's was way too much, 1.0 x 35 still crazy; Nick)
KNOCK = [((LEMMY,), KNOCK_SPEED, KNOCK_FRAMES), ((BILL,), BILL_KNOCK_SPEED, BILL_KNOCK_FRAMES)]   # ice_item.apply(knock=...)
JUMP = ((BILL,), _presets.block("bullet-bill", "hit")["dodge_height"])   # 0.2: ice_item.apply(jump=...): a fielder 0.2 m or more above the Bill jumped it (Nick)
# who brings which (character name -> item); charbuild adds them to FIXED_ITEM and ALWAYS_ITEM
BY_NAME = {"Lemmy": LEMMY, "Roy": BILL, "Morton": BILL, "Iggy": IGGY, "Larry": LARRY, "Wendy": WENDY,
           "Ludwig": LUDWIG}
from batter_items import KOOPA_NAMES as NAMES, KOOPA_STOCK_FIXED as STOCK_FIXED  # noqa: F401  (values; stock
#                     characters' items (batter_items.fixed / always's defaults: kept there, the checks load no engine)
assert NAMES == {LEMMY: "lemmy", BILL: "bill", IGGY: "iggy", LARRY: "larry", WENDY: "wendy", LUDWIG: "ludwig"}

FOLLOW, FOLLOW_ORIG, FOLLOW_EXIT = 0x8045693C, 0x57E3063E, 0x8045698C
SPEED, SPEED_ORIG = 0x804532C8, 0xC3E40004
BOUNCE_AT, BOUNCE_ORIG = 0x804535E8, (0xC0430010, 0xC0030014)
CPU, CPU_ORIG = 0x800C6288, 0x2C04FFFF
LAUNCH_VY, LAUNCH_VY_ORIG = 0x80453318, 0xD01F0014
GRAVITY, GRAVITY_ORIG = 0x80453564, 0xC02B000C
PUFF, PUFF_FN = 0x8045363C, 0x801010E8
FOLLOW_SPEED, FOLLOW_SPEED_ORIG = 0x80453484, 0xC0030004   # lfs f0,4(r3) (follower launch FUN_804533a8)
CUSTOM_REC = 0x10               # a new item's floats: speed x, gravity, bounce factor, minimum hop


def _check(dol, addr, want):
    got = dol.u32(addr)
    assert got == want, f"0x{addr:08X}: expected {want:08X}, found {got:08X}"


def _hook(dol, code, site, a, link=False):
    at = code.put(a.assemble(), 4)
    assert at == a.base, f"stub assembled for 0x{a.base:08X}, placed at 0x{at:08X}"
    w = Asm(site).bl(at) if link else Asm(site).b(at)
    dol.w32(site, w.assemble_word())


def _variant(a, flag, reg="r12"):
    """reg = the used variant byte."""
    return a.lis(reg, ha(flag)).lbz(reg, lo(flag), reg)


def _at(code):
    return code.here + (-code.here % 4)


def apply(dol, code, data, flag, base_tab, max_id, customs=(), skip=()):
    """flag: ice_item.LAYOUT["variant"]; base_tab: ice_item.LAYOUT["base_tab"] (id -> stock item bytes).
    customs: new items (creators.items.customs specs): each thrown ball joins the hooks' compare chains with its own
    values (CUSTOM_REC floats each, after the presets' consts). With none, every stub is as before.
    skip: our items edited in place (their ids are in customs): left out of the presets' branches."""
    kept = lambda ids: tuple(i for i in ids if i not in skip)  # noqa: E731
    lemmy, bill, ludwig = (v not in skip for v in (LEMMY, BILL, LUDWIG))
    consts = code.put(struct.pack(">9f", FAST_MULT, *BOUNCE, FAST_GRAVITY, 0.0, 0.0, LUDWIG_MULT, BILL_MULT, LEMMY_MULT), 4)   # read-only: in the item code section (data is full)
    balls = [s for s in customs if s["base"] == FIREBALL]
    cc = code.put(b"".join(struct.pack(">4f", s["speed"], s["gravity"] or 0.0, *(s["bounce"] or (0.0, 0.0)))
                           for s in balls), 4) if balls else None
    rec = {s["id"]: cc + CUSTOM_REC * k for k, s in enumerate(balls)}   # +0 speed, +4 gravity, +8 / +0xC bounce
    one = [s["id"] for s in balls if s["count"] == 1]
    five = [(s["id"], s["count"]) if s["count"] != 5 else s["id"] for s in balls if s["count"] > 3]   # 4..8 balls
    lead = [s["id"] for s in balls if s["level"]]                 # level launch
    skim = [s["id"] for s in balls if s["skim"]]                  # no bounce, no puff
    notrail = [s["id"] for s in balls if s["trail"] is None]
    speed = [s for s in balls if s["speed"] != 1.0]
    home = [s for s in balls if s["home"]]
    grav = [s for s in balls if s["gravity"] is not None or s["home"]]
    #                   +0x10/+0x14: LEAD bounce (+0x14: the Bill's gravity 0); +0x18: Ludwig's speed; +0x1C: the Bill's

    _check(dol, FOLLOW, FOLLOW_ORIG)                     # LEAD: the leader only; Ludwig: 5
    a = Asm(_at(code))
    _variant(a, flag)
    for vid in kept(LEAD) + tuple(one):
        a.cmpwi("r12", vid).beq("fast")
    import ludwig_fire
    assert not five or ludwig_fire.LAYOUT, "items of more than 3 balls need ludwig_fire's pool"
    if ludwig_fire.LAYOUT:                               # the pool holds 5: others stop after 3
        ludwig_fire.follow_code(a, FOLLOW_EXIT, "cont", more=five, ludwig=ludwig)
    a.b("cont")
    a.label("fast")
    a.cmplwi("r31", 0).beq("cont").b(FOLLOW_EXIT)
    a.label("cont")
    a.word(FOLLOW_ORIG)
    for vid in kept((LEMMY, BILL)):                      # Lemmy's balls, the Bill: no flame trail
        a.cmpwi("r12", vid).beq("notrail")
    for vid in notrail:
        a.cmpwi("r12", vid).beq("notrail")
    a.b(FOLLOW + 4)
    a.label("notrail")
    a.b(FOLLOW + 8)
    _hook(dol, code, FOLLOW, a)

    _check(dol, SPEED, SPEED_ORIG)                       # IGGY / LARRY: faster launch
    a = Asm(_at(code))
    a.word(SPEED_ORIG)
    _variant(a, flag)
    for vid in kept(FAST):
        a.cmpwi("r12", vid).beq("fast")
    for vid, label in ((LUDWIG, "lud"), (BILL, "bill"), (LEMMY, "lemmy")):
        if vid not in skip:
            a.cmpwi("r12", vid).beq(label)
    for s in speed:
        a.cmpwi("r12", s["id"]).beq(f"c{s['id']}")
    a.b(SPEED + 4)
    a.label("lemmy")
    a.load_addr("r12", consts).lfs("f0", 0x20, "r12").fmuls("f31", "f31", "f0").b(SPEED + 4)
    a.label("bill")
    a.load_addr("r12", consts).lfs("f0", 0x1C, "r12").fmuls("f31", "f31", "f0").b(SPEED + 4)
    a.label("fast")
    a.load_addr("r12", consts).lfs("f0", 0, "r12").fmuls("f31", "f31", "f0").b(SPEED + 4)
    a.label("lud")
    a.load_addr("r12", consts).lfs("f0", 0x18, "r12").fmuls("f31", "f31", "f0").b(SPEED + 4)
    for s in speed:
        a.label(f"c{s['id']}")
        a.load_addr("r12", rec[s["id"]]).lfs("f0", 0, "r12").fmuls("f31", "f31", "f0").b(SPEED + 4)
    _hook(dol, code, SPEED, a)

    _check(dol, FOLLOW_SPEED, FOLLOW_SPEED_ORIG)         # LUDWIG: followers as fast as the leader
    a = Asm(_at(code))
    a.word(FOLLOW_SPEED_ORIG)
    _variant(a, flag)
    if ludwig:
        a.cmpwi("r12", LUDWIG).beq("lud")
    fspeed = [s for s in speed if s["count"] > 1]        # the followers go as fast as the leader
    for s in fspeed:
        a.cmpwi("r12", s["id"]).beq(f"c{s['id']}")
    if lemmy:
        a.cmpwi("r12", LEMMY).bne("out")
        a.load_addr("r12", consts).lfs("f3", 0x20, "r12").fmuls("f0", "f0", "f3").b("out")
    else:
        a.b("out")
    a.label("lud")
    a.load_addr("r12", consts).lfs("f3", 0x18, "r12").fmuls("f0", "f0", "f3")
    a.label("out")
    a.b(FOLLOW_SPEED + 4)
    for s in fspeed:
        a.label(f"c{s['id']}")
        a.load_addr("r12", rec[s["id"]]).lfs("f3", 0, "r12").fmuls("f0", "f0", "f3").b(FOLLOW_SPEED + 4)
    _hook(dol, code, FOLLOW_SPEED, a)

    _check(dol, BOUNCE_AT, BOUNCE_ORIG[0])               # LEMMY: high bounces
    _check(dol, BOUNCE_AT + 4, BOUNCE_ORIG[1])
    a = Asm(_at(code))
    a.word(BOUNCE_ORIG[0]).word(BOUNCE_ORIG[1])
    _variant(a, flag)
    if lemmy:
        a.cmpwi("r12", LEMMY).beq("lemmy")
    bounce = [s for s in balls if s["bounce"]]
    for vid in kept(LEAD) + tuple(skim):
        a.cmpwi("r12", vid).beq("fast")
    for s in bounce:
        a.cmpwi("r12", s["id"]).beq(f"c{s['id']}")
    a.b(BOUNCE_AT + 8)
    a.label("lemmy")
    a.load_addr("r12", consts).lfs("f2", 4, "r12").lfs("f0", 8, "r12").b(BOUNCE_AT + 8)
    a.label("fast")
    a.load_addr("r12", consts).lfs("f2", 0x10, "r12").lfs("f0", 0x14, "r12").b(BOUNCE_AT + 8)
    for s in bounce:
        a.label(f"c{s['id']}")
        a.load_addr("r12", rec[s["id"]]).lfs("f2", 8, "r12").lfs("f0", 0xC, "r12").b(BOUNCE_AT + 8)
    _hook(dol, code, BOUNCE_AT, a)

    _check(dol, LAUNCH_VY, LAUNCH_VY_ORIG)               # FAST: no upward speed at the throw
    a = Asm(_at(code))
    a.word(LAUNCH_VY_ORIG)
    _variant(a, flag)                                    # (r0, r3, r4 are live here: r12 only)
    for vid in kept(LEAD) + tuple(lead):
        a.cmpwi("r12", vid).beq("fast")
    a.b(LAUNCH_VY + 4)
    a.label("fast")
    a.li("r12", 0).stw("r12", 0x14, "r31").b(LAUNCH_VY + 4)
    _hook(dol, code, LAUNCH_VY, a)

    import bullet_bill
    bb_state = data.put(bytes(16), 4)                    # aim point, locked target
    aims = kept((BILL,)) + tuple(s["id"] for s in home)
    bullet_bill.aim_hook(dol, code, flag, bb_state, BILL if aims == (BILL,) else aims)
    home_fn = bullet_bill.homing(code, code.put(bullet_bill.homing_consts(), 4), bb_state)
    homes = {s["id"]: bullet_bill.homing(code, code.put(bullet_bill.homing_consts(*s["home"][:2], *s["home"][2:3]), 4),
                                         bb_state, target=s["home"][2] if len(s["home"]) > 2 else None)
             for s in home}                              # each homing item: its own turn rate, jump and target
    _check(dol, GRAVITY, GRAVITY_ORIG)                   # FAST: down to the ground quickly
    a = Asm(_at(code))
    a.word(GRAVITY_ORIG)
    _variant(a, flag)
    for vid in kept(FAST):
        a.cmpwi("r12", vid).beq("fast")
    if bill:
        a.cmpwi("r12", BILL).beq("bill")
    for s in grav:
        a.cmpwi("r12", s["id"]).beq(f"c{s['id']}")
    a.b(GRAVITY + 4)
    a.label("fast")
    a.load_addr("r12", consts).lfs("f1", 0xC, "r12").b(GRAVITY + 4)
    a.label("bill")                                      # level flight, homing (bullet_bill.homing)
    a.bl(home_fn).load_addr("r12", consts).lfs("f1", 0x14, "r12").b(GRAVITY + 4)
    for s in grav:                                       # homing (its own), then its gravity (else the stock one)
        a.label(f"c{s['id']}")
        if s["home"]:
            a.bl(homes[s["id"]])
        if s["gravity"] is not None:
            a.load_addr("r12", rec[s["id"]]).lfs("f1", 4, "r12")
        a.b(GRAVITY + 4)
    _hook(dol, code, GRAVITY, a)

    _check(dol, PUFF, Asm(PUFF).bl(PUFF_FN).assemble_word())   # FAST: no bounce puff every frame
    a = Asm(_at(code))
    _variant(a, flag)
    for vid in kept(LEAD) + tuple(skim):
        a.cmpwi("r12", vid).beq("fast")
    a.b(PUFF_FN)                                         # tail call: returns to 0x80453640
    a.label("fast")
    a.blr()
    _hook(dol, code, PUFF, a, link=True)

    _check(dol, CPU, CPU_ORIG)                           # CPU batter table: variants as their stock item
    a = Asm(_at(code))
    a.cmpwi("r4", 7).blt("orig").cmpwi("r4", max_id).bgt("orig")
    a.load_addr("r12", base_tab).lbzx("r4", "r12", "r4")
    a.label("orig")
    a.word(CPU_ORIG).b(CPU + 4)
    _hook(dol, code, CPU, a)
    return [f"koopa items: Lemmy {LEMMY} (bounce {BOUNCE}, knock {KNOCK_SPEED} x {KNOCK_FRAMES}f), Bullet Bill {BILL} "
            f"(x{BILL_MULT}, level, homing {bullet_bill.TURN_DEG} deg/frame, knock {BILL_KNOCK_SPEED} x {BILL_KNOCK_FRAMES}f), fast {FAST} (x{FAST_MULT}, leader only, on the ground: gravity "
            f"{FAST_GRAVITY}, no bounce or puff); CPU table stub"]


# --- icons ------------------------------------------------------------------------------------------

FIRE_ROW, POW_ROW = 0xF5, 0xF7
ICON_HUES = {vid: _presets.hue(_presets.block(p, "look")["icon"]) for vid, p in ((IGGY, "iggy"), (LARRY, "larry"),
                                                                                 (LUDWIG, "ludwig"))}


def icons(blob):
    """{id: 27 x 29 RGBA} from one language's stock dir 119 file 8: recoloured Fireball / POW icons."""
    from ice_item import blue
    import wendy_rings
    fire, pow_ = stock_icon(blob, FIRE_ROW), stock_icon(blob, POW_ROW)
    import lemmy_balls, bullet_bill
    own = {WENDY: wendy_rings.draw_icon, LEMMY: lemmy_balls.draw_icon, BILL: bullet_bill.draw_icon}
    return {vid: own[vid]() if vid in own else blue(fire, ICON_HUES[vid]) for vid, _ in VARIANTS}


def custom_icons(blob, customs):
    """{id: 27 x 29 RGBA} for new items (creators.items.customs specs), after the Koopalings' rows: a hue-turned
    stock icon (read from this copy of the player's HUD layout), one of our drawn icons, or the player's picture."""
    from ice_item import blue, draw_icon as ice_icon
    from PIL import Image
    import wendy_rings, lemmy_balls, bullet_bill, starbits_roulette
    from creators.items import ICON_ROWS
    drawn = {"ice": ice_icon, "star-bits": starbits_roulette.draw_icon, "circus-ball": lemmy_balls.draw_icon,
             "ring": wendy_rings.draw_icon, "bullet-bill": bullet_bill.draw_icon}
    out = {}
    for s in customs:
        icon = s["icon"]
        if icon.get("draw"):
            img = drawn[icon["draw"]]()
        elif icon.get("png"):
            img = Image.open(icon["png"]).convert("RGBA")
            assert img.size == (27, 29), f"{s['name']}: its icon picture is {img.size[0]} x {img.size[1]}, not 27 x 29"
        else:
            img = stock_icon(blob, ICON_ROWS[icon.get("from") or "fireball"])
            if icon.get("hue") or icon.get("lighten"):
                img = blue(img, (icon.get("hue") or 0.0, icon["lighten"]) if icon.get("lighten") else icon["hue"])
        out[s["id"]] = img
    return out


def all_icons(customs):
    """ice_item.patch_layout's `more`: the Koopalings' icons (an edited one's own icon in its place), then the new
    items'. (Ice's row is ice_item's `first`; Star Bits' is starbits_roulette's.)"""
    mine = [s for s in customs if s["id"] >= 8]
    return lambda blob: {**icons(blob), **custom_icons(blob, mine)}


def icon_png(spec, dol, dat_path, folder):
    """An item spec's icon as a 27 x 29 PNG in folder (for starbits_roulette.patch_layout's png): drawn, the player's
    picture, or a stock icon hue-turned, read from dat_path's first copy of the HUD layout (dir 119 file 8)."""
    import dtna_toc
    from pathlib import Path
    rec = dtna_toc.dir_pointers(dol)[119] + 8 * dtna_toc.FILE_RECORD
    length, off = struct.unpack(">2I", dol.read(rec + 4, 8))
    with open(dat_path, "rb") as f:
        f.seek(off)
        blob = f.read(length)
    Path(folder).mkdir(parents=True, exist_ok=True)
    out = Path(folder) / f"icon-{spec['id']}.png"
    custom_icons(blob, [spec])[spec["id"]].save(out)
    return out

