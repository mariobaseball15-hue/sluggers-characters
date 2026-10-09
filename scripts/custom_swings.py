"""Custom star swing ids (13, 14, ...): who gets them and which stock swing lends each its tables.

The stock game knows star swings 1-12 and indexes several tables by the id with no bounds check. A custom
swing keeps a stock id (STATS_SWING) in the character's stats row, so menus that show the stats byte stay in
range, and gets its own id only on the batting batter (+0xB4 / +0xC1) and the ball (+0x2A82 / +0x2A83), where it
falls through every per-id behaviour check. Everything the batting code reads from an id-indexed table borrows
a stock swing's entry:

- SETUP 0x800B9A0C (FUN_800B98AC, `stb r3,0xB4(r28)`, r3 = stats row +9, character id at r28+0x2A): a
  character in `chars` whose stats swing is STATS_SWING gets the custom id. cr0 is live, so compares use cr1.
  The character also needs the captain flag (stats row +7 = 1) for the swing to make contact at all.
- ANGLE 0x800B9DE0 / SPEED 0x800BE8D4 (`subi` of the id before indexing the launch tables 0x80626BF0 /
  0x80627228): `launch`'s rows.
- ANGLE ADD 0x800B9E08 (FUN_800B9D64, `sth r4,0x8(r1)` right after the row's min r4 / max r0 are loaded; r26 =
  batter, swing id at +0xC1): a swing with `angle_add` raises both (angle units: tenths of a degree [I]).
- BANNER 0x80317350 (FUN_80317334, `lhax r31,r5,r0` from the cut-in layout table 0x8062CE3C): `cutin`'s entry
  (only 4, 5, 8 have one; the id past the table read 0, a stray layout). `layout` overrides it (-1 = none: 8's
  layout 73 is Waluigi's emblem, an "L", on King Boo's cut-in).
- CAMERA 0x8024FFBC / 0x8024FFD8 (FUN_8024FEC0, `lbz r0,0xB4(r29)`, the cut-in camera table 0x8065D960): `cutin`'s
  path (past the table was a static camera aimed away from the batter: a black screen).
- CUTIN 0x800BB668 / 0x800BB6B8 / 0x800BB6D8 (FUN_800BB55C, `lbz r3,0xB4(..)` before the swing effect timeline
  FUN_80108CE4 and its end FUN_80108D30): `cutin`'s captain cut-in effects.
- EMITTERS 0x80104CD4 / 0x80104D0C (`li r4,0x4c` in FUN_80104CB8 / FUN_80104CF0, the Heart cut-in's start and end,
  called only from swing timeline case 5): the cut-in queues particle emitter 0x4C (`heart_trace`, the hearts) at
  DAT_807086A4 and FUN_80104D98 spawns it in group 0x2A. A swing with `emitters` swaps it when the batter
  (*(r13-0x1D78), else *(r13-0x1D7C), the batter FUN_801314D8 passes to FUN_800BB55C) has that swing at +0xB4.
  Both sites swap, so the end removes the same id it queued.
The cut-in background is picked by character: scripts/cutin_backdrop.py. Ball behaviour: gravity_ball.py (13),
boo_ball.py (14), star_shower.py (15). See docs/star-swings.md.
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
from ppc import Asm  # noqa: E402

FIRE, TORNADO, BARREL, BANANA, HEART, FLOWER, PHONY, LIAR, EGG, CANNON, BREATH, GRAFFITI = range(1, 13)
ROSALINA, KING_BOO, LUMA = 0x81, 0x25, 0x84   # LUMA: the yellow Luma (new ids: the SETUP hook compares the u16 id)
HEART_TRACE, LANDING_STAR = 0x4C, 0x67    # grouped-particle emitter ids (their names: 0x8028ED54..0x8028FCA0)

SWINGS = {
    13: dict(name="Gravity Ball", chars=[ROSALINA], stats_swing=GRAFFITI, launch=LIAR, cutin=HEART,
             emitters={HEART_TRACE: LANDING_STAR}),    # stars instead of Peach's hearts
    14: dict(name="Boo Ball", chars=[KING_BOO], stats_swing=LIAR, launch=BANANA, cutin=LIAR,
             angle_add=60,                             # Banana's 200-250 -> 260-310: a little higher (Nick)
             layout=-1),                               # no Waluigi emblem
    15: dict(name="Star Shower", chars=[LUMA], stats_swing=FIRE, launch=GRAFFITI,   # Bowser Jr.'s path (Nick)
             angle_add=-300,                           # 60-65 -> 30-35 deg: a lot lower (Nick)
             cutin=HEART,
             emitters={HEART_TRACE: LANDING_STAR}),    # Peach's cut-in with stars, like Rosalina's
}


DEFAULT_CHARS = {sid: list(sw["chars"]) for sid, sw in SWINGS.items()}   # this mod's roster (Rosalina, King Boo, Luma)


def assign(entries, defaults=True):
    """The per-character key "star swing": n (patcher profiles, characters/*.json, stock entries), on any id:
    n in SWINGS puts the character on that custom swing, 1-12 gives it that stock swing, 0 none. A character
    with the key leaves the swing it had by default. defaults=False starts from no characters at all (a profile
    that names its own). Returns {id: (stats +9 stand-in, captain flag +7)} for every character with the key."""
    for sid, sw in SWINGS.items():
        sw["chars"] = list(DEFAULT_CHARS[sid]) if defaults else []
    out = {}
    for e in entries:
        n = e.get("star swing")
        if n is None:
            continue
        n, cid = int(n), int(e["id"])
        for sw in SWINGS.values():
            if cid in sw["chars"]:
                sw["chars"].remove(cid)
        if n in SWINGS:
            SWINGS[n]["chars"].append(cid)
        out[cid] = stats_of(n, cid)
    return out


def stats_of(n, cid=None):
    """Key "star swing": n -> (stats row +9, +7): a custom swing's stock stand-in with the star-swing flag (a
    star swing makes contact only with it), a stock swing with the flag, 0 without."""
    assert n in SWINGS or 0 <= n <= GRAFFITI,         f"{'' if cid is None else f'0x{cid:02X}: '}star swing {n} (stock 1-12 or one of {sorted(SWINGS)})"
    return (SWINGS[n]["stats_swing"] if n in SWINGS else n), int(n != 0)


def cutin_swing(n):
    """The stock swing whose captain's cut-in (and backdrop) swing n shows."""
    return SWINGS[n]["cutin"] if n in SWINGS else n


def setup_hook(base):
    a = Asm(base)
    for sid, sw in SWINGS.items():
        a.cmpwi(3, sw["stats_swing"], cr=1).bne(f"next{sid}", cr=1)
        a.lha(12, 0x2A, 28)                # character id
        for cid in sw["chars"]:
            a.cmpwi(12, cid, cr=1).beq(f"is{sid}", cr=1)
        a.label(f"next{sid}")
    a.b("done")
    for sid in SWINGS:
        a.label(f"is{sid}")
        a.li(3, sid).b("done")
    a.label("done")
    a.stb(3, 0xB4, 28)
    return a


def remap(a, reg, field, done="done"):
    """reg = SWINGS[reg][field] for a custom id in reg (cr0)."""
    for sid, sw in SWINGS.items():
        a.cmplwi(reg, sid).bne(f"not{sid}")
        a.li(reg, sw[field]).b(done)
        a.label(f"not{sid}")


def row_hook(reg, dst):
    """The launch-table index: dst = reg - 1, with a custom id using its `launch` swing's row."""
    def hook(base):
        a = Asm(base)
        for sid in SWINGS:                 # compare before writing dst: dst may be reg
            a.cmpwi(reg, sid).beq(f"is{sid}")
        a.addi(dst, reg, -1).b("done")
        for sid, sw in SWINGS.items():
            a.label(f"is{sid}")
            a.li(dst, sw["launch"] - 1).b("done")
        a.label("done")
        return a
    return hook


def angle_hook(base):
    a = Asm(base)
    a.lbz(12, 0xC1, 26)                    # swing id
    for sid, sw in SWINGS.items():
        if sw.get("angle_add"):
            a.cmpwi(12, sid).bne(f"not{sid}")
            a.addi(4, 4, sw["angle_add"])
            a.li(12, sw["angle_add"]).add(0, 0, 12).b("done")   # addi can't add to r0 (rA=0 means 0)
            a.label(f"not{sid}")
    a.label("done")
    a.sth(4, 0x8, 1)                       # the replaced instruction
    return a


def banner_hook(base):
    a = Asm(base)
    a.word(0x7FE502AE)                     # lhax r31,r5,r0 (the replaced instruction); r4 = swing id
    for sid, sw in SWINGS.items():
        a.cmpwi(4, sid).bne(f"not{sid}")
        if "layout" in sw:
            a.li(31, sw["layout"]).b("done")
        else:
            a.lha(31, 2 * sw["cutin"], 5).b("done")
        a.label(f"not{sid}")
    a.label("done")
    return a


def load_remap_hook(orig, reg, field):
    """The replaced `lbz reg,0xB4(..)`, then a custom id becomes its `field` swing."""
    def hook(base):
        a = Asm(base)
        a.word(orig)
        remap(a, reg, field)
        a.label("done")
        return a
    return hook


def emitter_hook(base):
    """Replaces `li r4,0x4c` (heart_trace): the batter's custom swing may swap it."""
    a = Asm(base)
    a.li(4, HEART_TRACE)
    a.lwz(12, -0x1D78, 13).cmpwi(12, 0).bne("batter")
    a.lwz(12, -0x1D7C, 13).cmpwi(12, 0).beq("done")
    a.label("batter")
    a.lbz(12, 0xB4, 12)
    for sid, sw in SWINGS.items():
        if HEART_TRACE in sw.get("emitters", {}):
            a.cmplwi(12, sid).bne(f"not{sid}")
            a.li(4, sw["emitters"][HEART_TRACE]).b("done")
            a.label(f"not{sid}")
    a.label("done")
    return a


HOOKS = [
    (0x800B9A0C, 0x987C00B4, setup_hook),                                   # stb r3,0xb4(r28)
    (0x800B9DE0, 0x3863FFFF, row_hook(3, 3)),                               # subi r3,r3,0x1
    (0x800BE8D4, 0x3806FFFF, row_hook(6, 0)),                               # subi r0,r6,0x1
    (0x800B9E08, 0xB0810008, angle_hook),                                   # sth r4,0x8(r1)
    (0x80317350, 0x7FE502AE, banner_hook),                                  # lhax r31,r5,r0
    (0x8024FFBC, 0x881D00B4, load_remap_hook(0x881D00B4, 0, "cutin")),      # lbz r0,0xb4(r29)
    (0x8024FFD8, 0x881D00B4, load_remap_hook(0x881D00B4, 0, "cutin")),      # lbz r0,0xb4(r29)
    (0x800BB668, 0x886300B4, load_remap_hook(0x886300B4, 3, "cutin")),      # lbz r3,0xb4(r3)
    (0x800BB6B8, 0x886300B4, load_remap_hook(0x886300B4, 3, "cutin")),      # lbz r3,0xb4(r3)
    (0x800BB6D8, 0x887D00B4, load_remap_hook(0x887D00B4, 3, "cutin")),      # lbz r3,0xb4(r29)
    (0x80104CD4, 0x3880004C, emitter_hook),                                 # li r4,0x4c
    (0x80104D0C, 0x3880004C, emitter_hook),                                 # li r4,0x4c
]
