"""Ice: an 8th batting item (id 7). It is the Fireball, except a hit fielder is frozen, as Peach Ice
Garden's hazard freezes them, instead of stunned (Nick, 2026-09-25).

Roulette and HUD: starbits_roulette.apply(..., extra=[EXTRA]) rolls id 7 (weights WEIGHTS, half the
Fireball's, "rare"), enables it whenever the Fireball is enabled, shows it in the rolling list and the
item slots (every "item 0..5" check becomes 0..7) with icon row ICON_ROW, drawn by patch_layout.

Behaviour: until it is used, id 7 is its own item. When it is used, it becomes the Fireball, so the
throw, the three balls, CPU and fielder AI and the camera are all the stock Fireball's:
  a. FUN_80456710 (use the item in slot r4) loads the slot's item at 0x80456734 (`lwz r4,0x338(r31)`)
     for the pool lookup, then copies it to the active item (+0x394). A stub rewrites a slot holding 7 to
     1 before both, and sets ICE_FLAG to (slot was 7).
  b. The Fireball's fielder hit (FUN_80117838) stuns with FUN_8012a140(player, 1) at 0x801179F8. With
     ICE_FLAG set it calls FUN_80129b18(player) instead: the freeze Peach Ice Garden's hazard uses
     (player +0x240 set, thaw timer +0x20C; FUN_800f5010, created for every stadium by FUN_800ea3b0 ->
     FUN_800f4be8 (Bb::CFreezeEffectEventThrower), plays the freeze sound 0x39 and ice effect, and on
     thaw sound 0x3A and ice_break). It skips fielders already down, stunned, frozen or acting on the ball.
The balls are blue (f.).

  c. Missing-effect guard. The freeze visual plays screen/field effect 0xC (FUN_800f4e78 ->
     FUN_8028a2d4(mgr, 0xC, 1)), which only Peach Ice Garden loads: elsewhere its slot's object is null and
     FUN_8028a2e4 read through it (Nick's crash, PC 0x8028A330, the first freeze outside the Ice Garden).
     `lwz r12,0(r3)` at 0x8028A330 goes to a stub: a null effect object returns the "no effect" handle
     0xFFFF (stored at 0x126(r31), as the function's own failure path does) through its epilogue.
  d. Sound and knock: b. calls FUN_80129d14(player, position), the hazard's full freeze: FUN_80129b18,
     then freeze sound 0xA8 at the player (FUN_80386dd8), the fielding / camera follow-up and a burst at
     the hit point. Position = the player's own (+4).
  e. The ice block. Field effects come in 17 sets, dt_na dir 160 file = set, chosen per stadium and
     day / night (table 0x80624B34, set id at effect manager +0x2C). A set file is u32 offsets for the
     effects it contains (index order, padded to 32 bytes), then their data; which effects a set has is
     the byte table 0x80672B08[effect * 0x11 + set] (FUN_8028c8e8 loads them). Effect 0xC (the ice
     block, 0x8B80 bytes, self-relative: identical in sets 0, 8, 9) is only in sets 0 (all effects) and
     8 / 9 (Peach Ice Garden day / night). add_freeze_effect() inserts it into every other set's file
     (appended copies, records repointed) and sets its table bytes.
  f. Blue balls. A thrown Fireball's trail is two particle lists per ball, built on each launch
     (FUN_800fb890 flags the ball, FUN_800fb960 builds them) from particle texture slots 6 (64x64
     RGB5A3) and 5 (64x64 CMPR) of the effect texture table. That table has 0x2D slots filled from a
     dt_na dir 161 file (26 files, one per stadium setup; u32 offsets padded to 0xC0, then entries of
     a 0xC0-byte header + pixels). add_blue_textures() appends blue copies (hue turned from orange to
     blue, brightness and alpha kept) of 6 and 5 to every file as slots 0x2D and 0x2E (two more
     offsets fit in the padding). The table grows to 0x2F slots (FUN_800ea3b0 0x800EA7DC / 0x800EA7EC /
     0x800EADE0, loader loop FUN_800eb82c 0x800EBA40), the loader's per-set presence check
     (0x800EB88C, table 0x806406D8) answers "present" for the new slots, and FUN_800fb960's
     li r4,6 / li r4,5 (0x800FB9D0 / 0x800FBA30) load 0x2D / 0x2E while ICE_FLAG is set.
"""
import struct

from ppc import Asm
from creators import items as _presets   # the one source of the tuning values below (scripts/creators/presets)

ICE = 7
WEIGHTS = tuple(_presets.block("ice", "given")["roulette"])   # (10, 8, 8) per score-difference row; the Fireball's are 20 / 15 / 15
ENABLE_AS = 1                    # rolled when the Fireball is enabled in settings
USE_LOAD, USE_LOAD_ORIG = 0x80456734, 0x809F0338     # lwz r4,0x338(r31)
HIT_CALL = 0x801179F8                                # bl FUN_8012a140 (r3 player, r4 1)
STUN_FN, FREEZE_FN = 0x8012A140, 0x80129D14      # FREEZE_FN: the hazard's full freeze (see d.)
EFFECT_LOAD, EFFECT_LOAD_ORIG, EFFECT_EXIT = 0x8028A330, 0x8183_0000, 0x8028AB94   # lwz r12,0(r3); epilogue
LAYOUT_DIR, LAYOUT_FILE = 119, 8                     # in-game HUD layout (item icons are rows 0xF3..0xF9)
ICON_ROW = 537                                       # the stock file's row count: our row is appended
ICON_SIZE, ICON_PAGE = (27, 29), (32, 32)            # the stock item icons' cell size
GX_RGB5A3 = 5
EXTRA = (ICE, WEIGHTS, ENABLE_AS, ICON_ROW)          # for starbits_roulette.apply(extra=...)


LAYOUT = {}                      # addresses apply() placed (VARIANT: the used variant byte), for other modules


def apply(dol, code, data, variants=(), knock=None, hues=None, jump=None, freeze=(), ice=True, spin=(), spin_fn=None,
          use_call=None):
    """variants: more (id, stock id) items used the way Ice is (koopa_items.VARIANTS), ids 8, 9, ...
    knock: (ids, slide speed, slide frames), or a list of them: those variants' Fireballs knock a hit fielder
    down and send them sliding (FUN_80128b48, then +0x130 / +0x206) instead of stunning. jump: (ids, clearance):
    those variants miss a fielder whose feet (+8) are more than clearance above the ball (jumping over it):
    FUN_80117838 goes on to its no-hit path (NO_HIT) and the ball keeps flying; or a list of them (each its own
    clearance). hues: {variant: hue turn} for trail recolours (default Ice's); texture slots 0x2D.. in that order
    (add_blue_textures gets the same). freeze: more variants that freeze a hit fielder, as Ice does (new items).
    ice: False when Ice itself is edited (creators.items): its freeze and colour then come from freeze / hues.
    A freeze entry may be (id, frames): that item's fielders stay frozen `frames` (at 60 Hz; 5/6 of it at 50 Hz)
    instead of the hazard's own 120 (freeze_code). spin: [(id, frames)]: those items spin a hit fielder
    (spin_effect: the routine at spin_fn). use_call: fn(flag) -> a routine the use stub calls with bl after the
    variant is set (r0 = variant, r4 = its stock item; item_params: the items' own table rows), placed before it."""
    bases = {ICE: 1, **dict(variants)}
    hues = trail_hues(hues, ice)
    flag = data.put(bytes(4), 4)
    LAYOUT["variant"] = flag
    LAYOUT["base_tab"] = base_tab = data.put(bytes(bases.get(i, i if i < ICE else 0) for i in range(max(bases) + 1)), 4)
    call = use_call(flag) if use_call else None
    a = Asm(code.here)                                   # a. use: variant -> its stock item, VARIANT = variant id
    a.lwz("r4", 0x338, "r31").li("r0", 0)
    a.cmpwi("r4", ICE).blt("store").cmpwi("r4", max(bases)).bgt("store")
    a.mr("r0", "r4").load_addr("r12", base_tab).lbzx("r4", "r12", "r4").stw("r4", 0x338, "r31")
    a.label("store")
    a.load_addr("r12", flag).stb("r0", 0, "r12")
    if call:
        a.bl(call)
    a.b(USE_LOAD + 4)
    assert dol.u32(USE_LOAD) == USE_LOAD_ORIG, f"0x{USE_LOAD:08X}: {dol.u32(USE_LOAD):08X}"
    dol.w32(USE_LOAD, Asm(USE_LOAD).b(code.put(a.assemble(), 4)).assemble_word())
    knocks = knock if isinstance(knock, list) else [knock] if knock else []
    knock_consts = [data.put(struct.pack(">fH2x", k[1], k[2]), 4) for k in knocks]
    jumps = jump if isinstance(jump, list) else [jump] if jump else []
    jump_cs = [code.put(struct.pack(">f", j[1]), 4) for j in jumps]
    timed = [f for f in freeze if isinstance(f, tuple)]  # (id, frames): their own freeze length
    tabs = [code.put(struct.pack(">2H", fr, round(fr * 5 / 6)), 4) for _, fr in timed]
    a = Asm(code.here)                                   # b. hit: freeze (Ice) / knock (knock ids) / stun
    a.load_addr("r12", flag).lbz("r0", 0, "r12")
    if jumps:                                            # r31 player, r30 ball; f0 / f1 free here
        for g, j in enumerate(jumps):
            for vid in j[0]:
                a.cmpwi("r0", vid).beq(f"jumpchk{g}")
        a.b("grounded")
        for g, c in enumerate(jump_cs):
            a.label(f"jumpchk{g}")
            a.lfs("f0", 8, "r31").lfs("f1", 8, "r30").fsubs("f0", "f0", "f1")
            a.load_addr("r12", c).lfs("f1", 0, "r12").fcmpo("f0", "f1").ble("grounded")
            a.b(NO_HIT)                                  # in the air: no hit, the ball flies on
        a.label("grounded")
    for k, (vid, _) in enumerate(timed):
        a.cmpwi("r0", vid).beq(f"frz{k}")
    assert not spin or spin_fn, "spin items need spin_effect.ensure's routine"
    for k, (vid, _) in enumerate(spin):
        a.cmpwi("r0", vid).beq(f"spin{k}")
    freeze = [f for f in freeze if not isinstance(f, tuple)]
    if freeze or not ice:                                # + new items that freeze (Ice's own unless edited)
        for vid in ((ICE,) if ice else ()) + tuple(freeze):
            a.cmpwi("r0", vid).beq("ice")
        a.b("notice")
        a.label("ice")
    else:
        a.cmpwi("r0", ICE).bne("notice")
    a.addi("r4", "r3", 4).b(FREEZE_FN)                   # (player, &player position); returns to 0x801179FC
    for k, (vid, frames) in enumerate(spin):             # spin-out: r3 = the fielder; the routine returns there too
        a.label(f"spin{k}")
        a.li("r4", frames).b(spin_fn)
    for k, tab in enumerate(tabs):
        a.label(f"frz{k}")
        freeze_code(a, tab, f"frz{k}_")
    a.label("notice")
    for i, k in enumerate(knocks):
        for vid in k[0]:
            a.cmpwi("r0", vid).beq(f"knock{i}")
    a.b(STUN_FN)
    for i, c in enumerate(knock_consts):                 # r12 = that group's slide speed / frames
        a.label(f"knock{i}")
        a.load_addr("r12", c).b("knock")
    if knocks:                                           # r31 player, r30 ball (FUN_80117838); LR = 0x801179FC
        a.label("knock")
        a.stwu("r1", -0x20, "r1").mflr("r0").stw("r0", 0x24, "r1").stw("r12", 0x10, "r1")
        a.lfs("f1", 4, "r31").lfs("f0", 4, "r30").fsubs("f1", "f1", "f0")
        a.lfs("f2", 0xC, "r31").lfs("f0", 0xC, "r30").fsubs("f2", "f2", "f0")
        a.bl(ANGLE_FN)                                   # push away from the ball, as the Bob-omb does
        a.word(EXTSH_R4_R3).mr("r3", "r31").li("r5", 1).bl(KNOCK_FN)
        a.cmpwi("r3", 0).beq("kout")                     # not knocked down (already down, etc.)
        a.lwz("r12", 0x10, "r1").lfs("f0", 0, "r12").stfs("f0", 0x130, "r31")
        a.lhz("r0", 4, "r12").sth("r0", 0x206, "r31")
        a.label("kout")
        a.lwz("r0", 0x24, "r1").mtlr("r0").addi("r1", "r1", 0x20).blr()
    want = Asm(HIT_CALL).bl(STUN_FN).assemble_word()
    assert dol.u32(HIT_CALL) == want, f"0x{HIT_CALL:08X}: {dol.u32(HIT_CALL):08X}"
    dol.w32(HIT_CALL, Asm(HIT_CALL).bl(code.put(a.assemble(), 4)).assemble_word())
    turns = unique_turns(hues)                           # items with the same colour share its two slots
    _grow(dol, code, TEX_STOCK + 2 * len(turns))
    for part, (site, stock_slot) in enumerate(TRAIL_SLOTS):   # f. trail textures: the variant's colour
        a = Asm(code.here)
        a.li("r4", stock_slot).load_addr("r12", flag).lbz("r0", 0, "r12")
        for k, (vid, turn) in enumerate(hues.items()):
            a.cmpwi("r0", vid).bne(f"n{k}").li("r4", TEX_STOCK + 2 * turns.index(turn) + part).b("go")
            a.label(f"n{k}")
        a.label("go")
        a.b(site + 4)
        assert dol.u32(site) == 0x38800000 | stock_slot, f"0x{site:08X}: {dol.u32(site):08X}"
        dol.w32(site, Asm(site).b(code.put(a.assemble(), 4)).assemble_word())
    a = Asm(code.here)                                   # c. missing-effect guard
    a.cmpwi("r3", 0).beq("none")
    a.lwz("r12", 0, "r3").b(EFFECT_LOAD + 4)
    a.label("none")
    a.sth("r7", 0x126, "r31").b(EFFECT_EXIT)              # r7 = 0xFFFF: no effect
    assert dol.u32(EFFECT_LOAD) == EFFECT_LOAD_ORIG, f"0x{EFFECT_LOAD:08X}: {dol.u32(EFFECT_LOAD):08X}"
    dol.w32(EFFECT_LOAD, Asm(EFFECT_LOAD).b(code.put(a.assemble(), 4)).assemble_word())
    return [f"ice item (id {ICE}): use stub at 0x{USE_LOAD:08X} (7 -> Fireball, flag 0x{flag:08X}), "
            f"Fireball hit 0x{HIT_CALL:08X} -> freeze FUN_80129d14 (sound 0xA8) when iced; missing-effect guard at 0x{EFFECT_LOAD:08X}"]


def draw_icon(scale=8):
    """An ice ball: a pale blue sphere with a dark outline, a snowflake and a gloss, like the stock
    item icons (27 x 29). -> RGBA image."""
    import math
    from PIL import Image, ImageDraw
    W, H = ICON_SIZE[0] * scale, ICON_SIZE[1] * scale
    img = Image.new("RGBA", (W, H), (0, 0, 0, 0))
    d = ImageDraw.Draw(img)
    cx, cy, r = W / 2, H / 2 + 0.5 * scale, 11.5 * scale
    d.ellipse((cx - r - 1.6 * scale, cy - r - 1.6 * scale, cx + r + 1.6 * scale, cy + r + 1.6 * scale),
              fill=(16, 40, 90, 255))                                        # outline
    d.ellipse((cx - r, cy - r, cx + r, cy + r), fill=(90, 190, 255, 255))
    d.ellipse((cx - r * 0.8, cy - r * 0.75, cx + r * 0.85, cy + r * 0.9), fill=(150, 225, 255, 255))
    for k in range(3):                                                       # snowflake
        t = math.pi * k / 3
        dx, dy = math.cos(t) * r * 0.62, math.sin(t) * r * 0.62
        d.line((cx - dx, cy - dy, cx + dx, cy + dy), fill=(255, 255, 255, 255), width=int(1.6 * scale))
        for sgn in (1, -1):
            bx, by = cx + sgn * dx * 0.6, cy + sgn * dy * 0.6
            for tw in (0.6, -0.6):
                ex = bx + math.cos(t + math.pi / 2 + tw) * r * 0.18 * sgn
                ey = by + math.sin(t + math.pi / 2 + tw) * r * 0.18 * sgn
                d.line((bx, by, ex, ey), fill=(255, 255, 255, 255), width=int(1.1 * scale))
    d.ellipse((cx - r * 0.62, cy - r * 0.72, cx - r * 0.22, cy - r * 0.4), fill=(240, 252, 255, 255))   # gloss
    return img.convert("RGBa").resize(ICON_SIZE, Image.LANCZOS).convert("RGBA")


def add_icon(data, more=(), first=None):
    """One language's dir 119 file 8 -> with the ice icon on a new page, row ICON_ROW, and each of
    `more` (27 x 29 RGBA images) on its own page, rows ICON_ROW + 1, ..."""
    from PIL import Image
    import layout
    from captain_art import rgb5a3
    if callable(more):                                   # e.g. koopa_items.icons (reads the stock icons)
        more = list(more(data).values())
    lay = layout.Layout(data)
    assert len(lay.rows) == ICON_ROW, f"HUD layout has {len(lay.rows)} rows, expected {ICON_ROW}"
    page_img = Image.new("RGBA", ICON_PAGE, (0, 0, 0, 0))
    page_img.paste(first or draw_icon(), (0, 0))         # first: an edited Ice's own icon
    page = lay.add_texture(rgb5a3(page_img), *ICON_PAGE, GX_RGB5A3, template_page=0)
    row = lay.add_row(page, 0.0, 0.0, ICON_SIZE[0] / ICON_PAGE[0], ICON_SIZE[1] / ICON_PAGE[1])
    assert row == ICON_ROW
    for k, img in enumerate(more):
        assert img.size == ICON_SIZE, f"icon {k}: {img.size}"
        page_img = Image.new("RGBA", ICON_PAGE, (0, 0, 0, 0))
        page_img.paste(img, (0, 0))
        page = lay.add_texture(rgb5a3(page_img), *ICON_PAGE, GX_RGB5A3, template_page=0)
        row = lay.add_row(page, 0.0, 0.0, ICON_SIZE[0] / ICON_PAGE[0], ICON_SIZE[1] / ICON_PAGE[1])
        assert row == ICON_ROW + 1 + k
    return lay.to_bytes()


def patch_layout(dol, dat_path, more=(), first=None):
    """Append each language's copy of dir 119 file 8 with the icon (and `more`, see add_icon) added;
    repoint the records."""
    import os
    import dtna_toc
    rec = dtna_toc.dir_pointers(dol)[LAYOUT_DIR] + LAYOUT_FILE * dtna_toc.FILE_RECORD
    w = list(struct.unpack(">12I", dol.read(rec, 48)))
    placed = {}
    with open(dat_path, "r+b") as f:
        for lang in range(3):
            off, length = w[2 + 4 * lang], w[1 + 4 * lang]
            if off not in placed:
                f.seek(off)
                blob = f.read(length)
                new = add_icon(blob, more, first(blob) if callable(first) else first)
                end = os.path.getsize(dat_path)
                at = end + (-end % 32)
                f.seek(at)
                f.write(new)
                placed[off] = (at, len(new))
            at, n = placed[off]
            w[1 + 4 * lang], w[2 + 4 * lang], w[3 + 4 * lang] = n, at, n
    dol.write(rec, struct.pack(">12I", *w))
    return [f"ice icon: row 0x{ICON_ROW:X} (+ Koopaling icons) in {len(placed)} copies of dir {LAYOUT_DIR} file {LAYOUT_FILE} (appended)"]


TEX_DIR, TEX_STOCK = 161, 0x2D
TABLE_SIZE_SITES = (0x800EA7DC, 0x800EA7EC, 0x800EADE0, 0x800EBA40)  # the 0x2D slot count
PRESENCE_CHECK, PRESENCE_CHECK_ORIG = 0x800EB88C, 0x7C0300AE          # lbzx r0,r3,r0
TRAIL_SLOTS = ((0x800FB9D0, 6), (0x800FBA30, 5))                      # (li r4,slot site, stock slot): part 0, 1
HUE_TURN = _presets.hue(_presets.block("ice", "look")["trail"])       # 0.52: orange (~0.08) -> blue (~0.6)
NO_HIT = 0x80117A54                              # FUN_80117838: this item missed (its height / reach checks)
ANGLE_FN, KNOCK_FN = 0x80181738, 0x80128B48       # angle(f1 dx, f2 dz); knockdown(player, angle, 1)
EXTSH_R4_R3 = 0x7C640734                          # extsh r4,r3


def _grow(dol, code, first_extra):
    """f. The texture table 0x2D -> first_extra + the requested extra slots (SLOT_REQUESTS), and every new slot present in
    every set. LAYOUT["extra"]: {request key: slot}."""
    slots = first_extra + len(SLOT_REQUESTS)
    LAYOUT["extra"] = {key: first_extra + k for k, key in enumerate(SLOT_REQUESTS)}
    for addr in TABLE_SIZE_SITES:                        # texture table 0x2D -> slots
        w = dol.u32(addr)                                # (subi = addi with -0x2D)
        sign = -1 if w & 0xFFFF == -TEX_STOCK & 0xFFFF else 1
        assert w & 0xFFFF == sign * TEX_STOCK & 0xFFFF, f"0x{addr:08X}: {w:08X}"
        dol.w32(addr, (w & 0xFFFF0000) | (sign * slots & 0xFFFF))
    a = Asm(code.here)                                   # new slots are in every set
    a.cmplwi("r25", TEX_STOCK).blt("stock").li("r0", 1).b(PRESENCE_CHECK + 4)
    a.label("stock")
    a.word(PRESENCE_CHECK_ORIG).b(PRESENCE_CHECK + 4)
    assert dol.u32(PRESENCE_CHECK) == PRESENCE_CHECK_ORIG, f"0x{PRESENCE_CHECK:08X}: {dol.u32(PRESENCE_CHECK):08X}"
    dol.w32(PRESENCE_CHECK, Asm(PRESENCE_CHECK).b(code.put(a.assemble(), 4)).assemble_word())


# Extra particle slots other modules ask for (git-95: recoloured star-swing / pitch trails): recoloured copies of a
# stock slot, after the trail recolours, in the same table growth and the same pass over the dir 161 files.
SLOT_REQUESTS = {}                                   # request key -> (stock slot, hue turn, lighten), in order
PRESENCE_TABLE, SETS = 0x806406D8, 0x1A              # the loader's presence bytes: slot * SETS + set (file i = set i)


def request_slot(key, src_slot, hue, lighten=0.0):
    """Ask for a recoloured copy of stock particle slot src_slot (e.g. 0x1A, the yellow star) as a slot of its own;
    its number is LAYOUT["extra"][key] once apply() (or grow_only()) has run. Same key twice: one slot. Call
    before apply(); charbuild clears SLOT_REQUESTS at the start of a build (reset_slots)."""
    assert 0 <= src_slot < TEX_STOCK, f"slot 0x{src_slot:X} isn't a stock slot"
    SLOT_REQUESTS.setdefault(key, (src_slot, float(hue), float(lighten)))


def reset_slots():
    SLOT_REQUESTS.clear()
    LAYOUT.pop("extra", None)


def grow_only(dol, code):
    """A build without the item variants (no apply()): the table grows for SLOT_REQUESTS alone (slots from 0x2D)."""
    if SLOT_REQUESTS and "extra" not in LAYOUT:
        _grow(dol, code, TEX_STOCK)
        return [f"particle slots: {len(SLOT_REQUESTS)} extra from 0x{TEX_STOCK:X} ({', '.join(map(str, SLOT_REQUESTS))})"]
    return []


def trail_hues(hues=None, ice=True):
    """{variant id: hue turn}, Ice first (its slots stay 0x2D / 0x2E); ice False (Ice edited): hues as given."""
    if not ice:
        return dict(hues or {})
    return {ICE: HUE_TURN, **{k: v for k, v in (hues or {}).items() if k != ICE}}


def blue(img, turn=HUE_TURN):
    """Fire colours -> ice blue: hue turned by HUE_TURN; saturation, brightness and alpha kept.
    turn may be (hue turn, lighten): saturation is then cut by that fraction (e.g. light blue). Not a blend toward
    white: the trail textures are drawn additively on black, and whitening the black made them squares (Nick)."""
    turn, light = turn if isinstance(turn, tuple) else (turn, 0.0)
    import colorsys
    from PIL import Image
    out = Image.new("RGBA", img.size)
    src, dst = img.convert("RGBA").load(), out.load()
    for y in range(img.height):
        for x in range(img.width):
            r, g, b, a = src[x, y]
            h, sat, v = colorsys.rgb_to_hsv(r / 255, g / 255, b / 255)
            r, g, b = colorsys.hsv_to_rgb((h + turn) % 1, sat * (1 - light), v)
            dst[x, y] = (round(r * 255), round(g * 255), round(b * 255), a)
    return out


def _decode_rgb5a3(pix, w, h):
    from PIL import Image
    img = Image.new("RGBA", (w, h))
    px, k = img.load(), 0
    for ty in range(0, h, 4):
        for tx in range(0, w, 4):
            for y in range(ty, ty + 4):
                for x in range(tx, tx + 4):
                    v = struct.unpack_from(">H", pix, k)[0]
                    k += 2
                    if v & 0x8000:
                        px[x, y] = ((v >> 10 & 31) * 255 // 31, (v >> 5 & 31) * 255 // 31, (v & 31) * 255 // 31, 255)
                    else:
                        px[x, y] = ((v >> 8 & 15) * 17, (v >> 4 & 15) * 17, (v & 15) * 17, (v >> 12 & 7) * 255 // 7)
    return img


def _tex_entry_blue(entry, turn=HUE_TURN):
    """A dir 161 entry (0xC0 header, then pixels) -> the same entry with its hue turned (blue by default)."""
    import cmpr
    from captain_art import rgb5a3
    fmt = struct.unpack_from(">I", entry, 0x98)[0]
    h, w = struct.unpack_from(">HH", entry, 0x8C)
    pix = entry[0xC0:]
    if fmt in (0x08, 0x09):                                           # CI4 / CI8: the palette (at +0xC0)
        from PIL import Image
        from captains import rgb5a3_rgba, rgb5a3_value
        n, pal_fmt = struct.unpack_from(">H", entry, 0x9C)[0], entry[0x9E]
        assert pal_fmt == 2, f"palette format {pal_fmt} (RGB5A3 only)"
        vals = struct.unpack_from(f">{n}H", pix, 0)
        img = Image.new("RGBA", (n, 1))
        img.putdata([rgb5a3_rgba(v) for v in vals])
        new = struct.pack(f">{n}H", *(rgb5a3_value(*p) for p in blue(img, turn).getdata()))
    elif fmt == 0x0E:                                                 # CMPR
        img = blue(cmpr.decode(pix, w, h), turn)
        new = bytearray(w * h // 2)
        cmpr.encode_region(new, w, img, 0, 0)
    else:
        assert fmt == 0x05, f"texture format 0x{fmt:X}"               # RGB5A3
        new = rgb5a3(blue(_decode_rgb5a3(pix, w, h), turn))
    return bytes(entry[:0xC0]) + bytes(new) + bytes(entry[0xC0 + len(new):])


def freeze_code(a, tab, p):
    """The freeze with its own length (r3 = r31 = the fielder; LR = the hit's return): FREEZE_FN, then, if he wasn't
    frozen before and is now (+0x240), his thaw timer +0x20C = tab's u16 for the video mode (byte r13-0x1658: 0 =
    60 Hz, 1 = 50 Hz), where FUN_80129b18 put the hazard's DAT_807979B8 value."""
    a.stwu("r1", -0x20, "r1").mflr("r0").stw("r0", 0x24, "r1")
    a.lbz("r0", 0x240, "r3").stw("r0", 0x10, "r1")      # frozen already?
    a.addi("r4", "r3", 4).bl(FREEZE_FN)
    a.lwz("r0", 0x10, "r1").cmpwi("r0", 0).bne(p + "out")
    a.lbz("r0", 0x240, "r31").cmpwi("r0", 0).beq(p + "out")   # not frozen (down, stunned, cooling down, ...)
    a.lbz("r0", -0x1658, "r13").slwi("r0", "r0", 1).load_addr("r12", tab).lhzx("r0", "r12", "r0")
    a.sth("r0", 0x20C, "r31")
    a.label(p + "out")
    a.lwz("r0", 0x24, "r1").mtlr("r0").addi("r1", "r1", 0x20).blr()


def unique_turns(hues):
    """The distinct hue turns of {variant: turn}, in first-use order: one pair of texture slots each."""
    out = []
    for turn in hues.values():
        if turn not in out:
            out.append(turn)
    return out


def blue_texture_file(data, turns=(HUE_TURN,), extras=(), present=None):
    """A dir 161 file -> with recoloured copies of slots 6 and 5 appended, two per hue turn (Ice's blue
    first: slots 0x2D and 0x2E, then 0x2F / 0x30, ...).

    The offset list is packed: one offset per slot present in the file's set (41 in most files, 45
    in one), then zero padding up to the first entry. The loader (FUN_800eb82c) takes the next
    offset for each present slot, so the new offsets go right after the existing ones (writing
    them at 0x2D/0x2E left the loader reading padding, offset 0, and crashing in FUN_80466644).
    Slots 0..11 are present in every set, so slots 5 and 6 are entries 5 and 6. When the new offsets
    don't fit in the padding, the header grows (to the next 32 bytes) and every entry moves by the
    same amount: the entries are self-relative (the Ice copies load at any offset). extras: [(stock slot, hue,
    lighten)] appended after the trail pairs; present: this file's set's presence bytes (0x2D), to find a slot
    past 11 (the entries are packed: one per present slot)."""
    first = struct.unpack_from(">I", data, 0)[0]
    offs = []
    while 4 * len(offs) < first and struct.unpack_from(">I", data, 4 * len(offs))[0]:
        offs.append(struct.unpack_from(">I", data, 4 * len(offs))[0])
    ends = offs[1:] + [len(data)]
    head = max(first, (4 * (len(offs) + 2 * len(turns) + len(extras)) + 31) & ~31)
    out = bytearray(head) + bytearray(data[first:])
    out += bytes(-len(out) % 32)
    offs = [o + head - first for o in offs]
    n_stock = len(offs)
    for turn in turns:
        for src in (6, 5):
            e = _tex_entry_blue(data[offs[src] - head + first:ends[src]], turn)
            offs.append(len(out))
            out += e + bytes(-len(e) % 32)
    for slot, hue, light in extras:
        k = sum(present[:slot]) if present is not None else slot
        assert present is None or present[slot], f"slot 0x{slot:X} isn't in this file's set"
        assert k < n_stock
        e = _tex_entry_blue(data[offs[k] - head + first:ends[k]], (hue, light) if light else hue)
        offs.append(len(out))
        out += e + bytes(-len(e) % 32)
    struct.pack_into(f">{len(offs)}I", out, 0, *offs)
    return bytes(out)


def add_blue_textures(dol, dat_path, hues=None, ice=True, turns=None):
    """f. Every dir 161 file gets the recoloured trail textures (appended copies, records repointed), then the
    requested extra slots (SLOT_REQUESTS). hues: as apply()'s; turns=(): no trails (a build without the item variants)."""
    turns = tuple(unique_turns(trail_hues(hues, ice))) if turns is None else tuple(turns)
    extras = list(SLOT_REQUESTS.values())
    import os
    import dtna_toc
    ptr = dtna_toc.dir_pointers(dol)[TEX_DIR]
    n_files = len(dtna_toc.toc(dol)[TEX_DIR])
    placed = {}
    with open(dat_path, "r+b") as f:
        for i in range(n_files):
            rec = ptr + i * dtna_toc.FILE_RECORD
            w = list(struct.unpack(">12I", dol.read(rec, 48)))
            for lang in range(3):
                key = (w[2 + 4 * lang], w[1 + 4 * lang])
                if key not in placed:
                    f.seek(key[0])
                    present = [dol.read(PRESENCE_TABLE + s * SETS + i, 1)[0] for s in range(TEX_STOCK)] \
                        if extras else None
                    new = blue_texture_file(f.read(key[1]), turns, extras, present)
                    end = os.path.getsize(dat_path)
                    at = end + (-end % 32)
                    f.seek(at)
                    f.write(new)
                    placed[key] = (at, len(new))
                at, n = placed[key]
                w[1 + 4 * lang], w[2 + 4 * lang], w[3 + 4 * lang] = n, at, n
            dol.write(rec, struct.pack(">12I", *w))
    return [f"coloured balls: {len(turns)} trail recolours as slots 0x2D..0x{TEX_STOCK + 2 * len(turns) - 1:X} in "
            f"{len(placed)} files of dt_na dir {TEX_DIR}"] + \
        ([f"particle slots: {', '.join(f'{k} = 0x{s:X}' for k, s in LAYOUT.get('extra', {}).items())} (recoloured "
          f"copies of stock slots)"] if extras else [])


FREEZE_EFFECT, EFFECT_SETS, SET_DIR = 0xC, 0x11, 160
PRESENCE, N_EFFECTS = 0x80672B08, 0x66


def _set_effects(dol, s):
    table = dol.read(PRESENCE, N_EFFECTS * EFFECT_SETS)
    return [e for e in range(N_EFFECTS) if table[e * EFFECT_SETS + s]]


def split_set(data, effects):
    """A set file -> {effect: its data}."""
    offs = struct.unpack(f">{len(effects)}I", data[:4 * len(effects)])
    assert list(offs) == sorted(offs), "set offsets out of order"
    ends = list(offs[1:]) + [len(data)]
    return {e: data[o:end] for e, o, end in zip(effects, offs, ends)}


def build_set(blobs):
    """{effect: data} -> a set file (effects in index order, each 32-aligned)."""
    order = sorted(blobs)
    head = (4 * len(order) + 31) & ~31
    offs, body = [], bytearray()
    for e in order:
        offs.append(head + len(body))
        body += blobs[e] + bytes(-len(blobs[e]) % 32)
    return struct.pack(f">{len(order)}I", *offs) + bytes(head - 4 * len(order)) + bytes(body)


def add_freeze_effect(dol, dat_path):
    """e. Every set gets effect 0xC (DOL table + dir 160 files, appended to dat_path)."""
    import os
    import dtna_toc
    ptr = dtna_toc.dir_pointers(dol)[SET_DIR]
    rec = lambda s: ptr + s * dtna_toc.FILE_RECORD
    have = [s for s in range(EFFECT_SETS) if FREEZE_EFFECT in _set_effects(dol, s)]
    assert have, "no effect set has the ice block"
    with open(dat_path, "r+b") as f:
        w = struct.unpack(">12I", dol.read(rec(have[0]), 48))
        f.seek(w[2])
        ice = split_set(f.read(w[1]), _set_effects(dol, have[0]))[FREEZE_EFFECT]
        placed, done = {}, []
        for s in range(EFFECT_SETS):
            if s in have:
                continue
            w = list(struct.unpack(">12I", dol.read(rec(s), 48)))
            for lang in range(3):
                off, length = w[2 + 4 * lang], w[1 + 4 * lang]
                key = (off, length)
                if key not in placed:
                    f.seek(off)
                    blobs = split_set(f.read(length), _set_effects(dol, s))
                    blobs[FREEZE_EFFECT] = ice
                    new = build_set(blobs)
                    end = os.path.getsize(dat_path)
                    at = end + (-end % 32)
                    f.seek(at)
                    f.write(new)
                    placed[key] = (at, len(new))
                at, n = placed[key]
                w[1 + 4 * lang], w[2 + 4 * lang], w[3 + 4 * lang] = n, at, n
            dol.write(rec(s), struct.pack(">12I", *w))
            done.append(s)
        for s in done:
            dol.write(PRESENCE + FREEZE_EFFECT * EFFECT_SETS + s, b"")
    return [f"ice block: effect 0x{FREEZE_EFFECT:X} (0x{len(ice):X} B) added to effect sets {done} "
            f"({len(placed)} files of dt_na dir {SET_DIR} appended)"]
