"""Star Shower: star swing 15 (the yellow Luma, 0x84). Bowser Jr.'s path (Graffiti's launch rows,
normal flight), and right after contact DROPS (36) star bits fall around where the ball will land, so the fielder
has to catch it among them. Each bit hops in place as a Banana-like hazard (a fielder who runs into one slips)
until the play's items are cleared. Who gets 15, its launch and its cut-in (Peach's, stars): custom_swings.py.
Background: cutin_backdrop.py. The star trail and sparkle cloud: gravity_ball.py (STAR_IDS). The bits are the
Star Bits item's (starbits_item.py: `drop`, bits BIT_COUNT.. of BIT_TOTAL; model: starbits_model.py).

- SHOWER 0x800ACE28 (FUN_800AC828, `bl 0x800B38C8` = the fielders' landing/catch forecast, r3 = ball = r31,
  r4 = 1; volatile registers are dead after it: the next instruction reloads r3): the forecast runs first, as
  stock; it leaves the predicted landing point at ball +0x400 (x) / +0x404 (z), the point the landing marker
  (FUN_80148518) shows and the CPU fielders run to [C: FUN_800B38C8 0x800B3BD8, stored from its x/z steps].
  Then for ball 15 until it lands (+0x2A4E), from frame DROP_START one bit every DROP_EVERY frames (count in
  FLAG +0x2CB5, cleared at launch by gravity_ball's BALL hook): the item manager (*(r13-0x354); none: no
  bits) is switched to Star Bits if it isn't (FUN_804588F4 clears the at-bat's active item, as the end of a
  play does; then manager +0x394 = 6, so its per-frame update, model and fielder reactions run the bits, and
  the play's cleanup removes them), then drop(BIT_COUNT + count, landing + SPOTS[count], ground + HEIGHT,
  ground) with ground = ball +0x420. Frame = *(*(r13-0x1684)+2) [I: counts from contact].
  Once the ball has landed (+0x2A4E) or a fielder has it (+0x2A66), once per hit (FLAG bit 7): every swing
  bit still out gets EXPIRE frames (+0x3C, counted down by starbits_item's bit update, which poofs it at 0).
Replaces the Warp Star (Nick, 2026-09-24). v1-v4 (Daisy's launch, then a slowed, drag-free launch with sways,
random ranges, late drifts, bits spread over the outfield) didn't play well in Dolphin; Nick: "just make it
like Bowser Jr.'s where it has a distinct path and then 12 star bits appear where it will land".
"""
import math
import struct
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
from ppc import Asm, ha, lo  # noqa: E402
import starbits_item  # noqa: E402

NEW_ID = 15
FLAG = 0x2CB5                 # shared with gravity_ball: cleared at launch for its FLAG_IDS
LANDING = 0x400               # forecast landing point x, +4 z
DROPS = starbits_item.BIT_TOTAL - starbits_item.BIT_COUNT   # 36
DROP_START = 10               # frame of the first bit
DROP_EVERY = 1                # frames between bits
EXPIRE = 120                  # frames the bits stay after the ball lands (Nick: 2 s)
EXPIRED = 0x80                # FLAG bit: EXPIRE set
HEIGHT = 12.0                 # m above the ground where each appears (falls in ~45 frames)
# (x, z) m from the landing point: a tight ring of 12 and an outer ring of 24 (Nick; v5: 4 and 8)
SPOTS = [(r * math.cos(math.radians(a)), r * math.sin(math.radians(a))) for r, a in
         [(3.0, 15 + 30 * k) for k in range(12)] + [(6.5, 15 * k) for k in range(24)]]
MANAGER, ACTIVE, STAR_BITS = -0x354, 0x394, starbits_item.ITEM_ID
CLEAR_ITEM, FORECAST = 0x804588F4, 0x800B38C8
# Swing creations (creators/swings.py, step 2): None = only ours (NEW_ID, the constants above: today's code); else
# {swing id: dict(spots=[(x, z), ...], height, start, every, stay)} for every showering swing, each with its own row.
# Then the drop count is FLAG's low 6 bits (at most 36 drops: the shared pool of BIT_TOTAL - BIT_COUNT, safe since
# one batted ball flies at a time), bit 0x40 is gravity_ball's POPPED and bit 0x80 EXPIRED, so a swing may pop too.
SHOWERS = None
COUNT_MASK = 0x3F


def f32(x):
    return struct.unpack(">I", struct.pack(">f", x))[0]


def shower_hook(base):
    if SHOWERS is not None:
        return _shower_many(base)
    drop = starbits_item.LAYOUT["drop"]                 # starbits_item.apply runs first
    a = Asm(base)
    data = base + 4
    a.b("code").word(f32(HEIGHT))                       # +0
    for x, z in SPOTS:                                  # +4
        a.word(f32(x)).word(f32(z))
    a.label("code")
    a.bl(FORECAST)                                                  # the replaced call (r3, r4 already set)
    a.lbz(12, 0x2A82, 31).cmpwi(12, NEW_ID).bne("done")
    a.lha(12, 0x2A4E, 31).cmpwi(12, 0).bne("landed")
    a.lbz(12, 0x2A66, 31).cmpwi(12, 0).bne("landed")               # caught before it landed
    a.lwz(11, -0x1684, 13).lha(11, 2, 11)                           # frame
    a.lbz(10, FLAG, 31).cmpwi(10, DROPS).bge("done")                # all down
    a.mulli(10, 10, DROP_EVERY).addi(10, 10, DROP_START)
    a.cmpw(11, 10).blt("done")                                      # not yet
    a.lwz(3, MANAGER, 13).cmpwi(3, 0).beq("done")                   # no items
    a.lwz(10, ACTIVE, 3).cmpwi(10, STAR_BITS).beq("dropping")
    a.bl(CLEAR_ITEM)                                                # the at-bat's item goes
    a.lwz(3, MANAGER, 13).li(10, STAR_BITS).stw(10, ACTIVE, 3)
    a.label("dropping")
    a.lbz(3, FLAG, 31).addi(10, 3, 1).stb(10, FLAG, 31)
    a.lis(12, ha(data)).addi(12, 12, lo(data))
    a.slwi(10, 3, 3).add(10, 12, 10)
    a.lfs(1, LANDING, 31).lfs(0, 4, 10).fadds(1, 1, 0)             # x
    a.lfs(3, LANDING + 4, 31).lfs(0, 8, 10).fadds(3, 3, 0)         # z
    a.lfs(4, 0x420, 31).lfs(0, 0, 12).fadds(2, 4, 0)               # y = ground + HEIGHT
    a.addi(3, 3, starbits_item.BIT_COUNT)                           # bit index
    a.bl(drop)
    a.b("done")
    a.label("landed")                                               # the bits go EXPIRE frames from now
    a.lbz(10, FLAG, 31).rlwinm(11, 10, 0, 24, 24).cmpwi(11, 0).bne("done")
    a.ori(10, 10, EXPIRED).stb(10, FLAG, 31)
    bits = starbits_item.LAYOUT["bits"] + 0x40 * starbits_item.BIT_COUNT
    a.lis(9, ha(bits)).addi(9, 9, lo(bits)).li(8, DROPS).li(10, EXPIRE)
    a.label("each")
    a.lbz(11, 0x37, 9).cmpwi(11, 0).beq("next")                    # not out
    a.sth(10, 0x3C, 9)
    a.label("next")
    a.addi(9, 9, 0x40).addi(8, 8, -1).cmpwi(8, 0).bne("each")
    a.label("done")
    return a


ROW = 28                      # a SHOWERS row: f32 height, u32 start, every, drops, stay, drop routine, bits (1: star
                              # bits, which get the stay; 0: a ring pool's, which last the half-inning); then (x, z)


def rows():
    """[(swing id, row bytes)] in id order."""
    out = []
    for sid in sorted(SHOWERS):
        sh = SHOWERS[sid]
        assert 1 <= len(sh["spots"]) <= DROPS, f"swing {sid}: {len(sh['spots'])} bits (1..{DROPS})"
        from creators import items                      # the row's drop routine: git-f3's pools (star_spawn)
        drop = sh.get("drop", "star-bits")
        blob = struct.pack(">f6I", sh["height"], sh["start"], sh["every"], len(sh["spots"]), sh["stay"],
                           items.drop_address(drop), int(drop == "star-bits"))
        blob += b"".join(struct.pack(">2f", x, z) for x, z in sh["spots"])
        out.append((sid, blob))
    return out


def _select(a, tag, miss, table):
    """r12 = this ball's (r31) SHOWERS row, or branch to miss."""
    a.lbz(12, 0x2A82, 31)
    for sid in table:
        a.cmpwi(12, sid).beq(f"{tag}{sid}")
    a.b(miss)
    for sid, addr in table.items():
        a.label(f"{tag}{sid}")
        a.lis(12, ha(addr)).addi(12, 12, lo(addr)).b(f"{tag}go")
    a.label(f"{tag}go")


def _shower_many(base):
    """shower_hook for SHOWERS: each showering swing drops its own spots from its own height and timing, into the
    shared swing pool (bits BIT_COUNT..), and gives them its own stay once the ball lands."""
    a = Asm(base)
    a.b("code")
    table, at = {}, base + 4
    for sid, blob in rows():
        table[sid] = at
        for k in range(0, len(blob), 4):
            a.word(struct.unpack_from(">I", blob, k)[0])
        at += len(blob)
    a.label("code")
    a.bl(FORECAST)                                                  # the replaced call (r3, r4 already set)
    _select(a, "a", "done", table)
    a.lha(11, 0x2A4E, 31).cmpwi(11, 0).bne("landed")
    a.lbz(11, 0x2A66, 31).cmpwi(11, 0).bne("landed")               # caught before it landed
    a.lbz(10, FLAG, 31).rlwinm(10, 10, 0, 26, 31)                  # drops so far
    a.lwz(9, 12, 12).cmpw(10, 9).bge("done")                        # all down
    a.lwz(9, 8, 12).mullw(10, 10, 9).lwz(9, 4, 12).add(10, 10, 9)
    a.lwz(11, -0x1684, 13).lha(11, 2, 11)                           # frame
    a.cmpw(11, 10).blt("done")                                      # not yet
    a.lwz(3, MANAGER, 13).cmpwi(3, 0).beq("done")                   # no items
    a.lwz(10, ACTIVE, 3).cmpwi(10, STAR_BITS).beq("dropping")
    a.bl(CLEAR_ITEM)                                                # the at-bat's item goes
    a.lwz(3, MANAGER, 13).li(10, STAR_BITS).stw(10, ACTIVE, 3)
    a.label("dropping")
    _select(a, "b", "done", table)                                  # (the calls above clobber r12)
    a.lbz(3, FLAG, 31).addi(10, 3, 1).stb(10, FLAG, 31).rlwinm(3, 3, 0, 26, 31)
    a.slwi(10, 3, 3).add(10, 12, 10)
    a.lfs(1, LANDING, 31).lfs(0, ROW, 10).fadds(1, 1, 0)           # x
    a.lfs(3, LANDING + 4, 31).lfs(0, ROW + 4, 10).fadds(3, 3, 0)   # z
    a.lfs(4, 0x420, 31).lfs(0, 0, 12).fadds(2, 4, 0)               # y = ground + height
    a.addi(3, 3, starbits_item.BIT_COUNT)                           # bit index
    a.lwz(0, 20, 12).mtctr(0).bctrl()                               # the swing's drop routine
    a.b("done")
    a.label("landed")                                               # the bits go `stay` frames from now
    a.lbz(10, FLAG, 31).rlwinm(11, 10, 0, 24, 24).cmpwi(11, 0).bne("done")
    a.ori(10, 10, EXPIRED).stb(10, FLAG, 31)
    a.lwz(11, 24, 12).cmpwi(11, 0).beq("done")                     # rings: no stay (they last the half-inning)
    bits = starbits_item.LAYOUT["bits"] + 0x40 * starbits_item.BIT_COUNT
    a.lis(9, ha(bits)).addi(9, 9, lo(bits)).lwz(8, 12, 12).lwz(10, 16, 12)
    a.label("each")
    a.lbz(11, 0x37, 9).cmpwi(11, 0).beq("next")                    # not out
    a.sth(10, 0x3C, 9)
    a.label("next")
    a.addi(9, 9, 0x40).addi(8, 8, -1).cmpwi(8, 0).bne("each")
    a.label("done")
    return a


HOOKS = [(0x800ACE28, 0x48006AA1, shower_hook)]   # bl 0x800b38c8
