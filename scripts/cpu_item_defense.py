"""Level 6 CPU item defense / fielding decisions (Nick, 2026-09-27). LEVEL 6 ONLY (level5.FLAG byte == 2); levels
1-5 run the stock instructions. Only the CPU fielding team is touched: every fielder stub also needs the fielder's
level byte +0x2E == 0, which at FLAG 2 only the CPU side has (level5.apply gives both sides level 4 -> 0, then
FUN_800C37D0 rewrites a human side's level word to 1 and its "CPU fields" byte S+0x1E to 0).
Background: docs/cpu-ai-weaknesses.md "## 2. Item defense", docs/cpu-ai.md 1a-1g, docs/buddy-jump.md, docs/items.md.

Stock: the chaser (defense ai +0x2D8) runs the obstacle hop FUN_800E2830 (CDefense vtable +0x14, CPU branch only,
from 800E21EC). Past its gates (ball live and not held game+0x2A72, not in the +0x265 action, not airborne +0x22E,
not busy 8012BA58, reaction delay +0x226 + 3 passed) it rolls the chemistry check 8011F4D0 (sets ai+0xD4 -> the
+0x265 "pass / block" action via 8011D5F4) or, near an item/wall/fielder, the hop (ai+0xC8 = 2, 8011C318).
r29 = ai (the defense object, same as the r13-0x1D14/-0x1D10/-0x1D18/-0x1D1C chain), r30 = the fielder F,
r31 = game (*(r13-0x1D94)); LR is saved in its frame, so the stubs may `bl`.

HOOKS
1. POW 0x800E28CC (FUN_800E2830 `lbz r0,0x2A72(r31)`, the first gate). Overrides everything, before any gate: when
   the active item (manager *(r13-0x354) +0x394) is the POW (3), its object (manager +0x180, inline) is in flight
   (+0x3A == 1) and it will hit the ground within POW_K frames (y + K*vy - g*K(K-1)/2 <= fielder ground +0xD8; the
   flight FUN_80458E80 moves by the old vy, then vy -= g, g = 0x806311EC[mode*0x60 + row*0x30], row = +0x34), the
   fielder (not already airborne) jumps: F+0x26A = 1 (the "allowed" flag 800E246C rolls), ai+0xC8 = 2, 8011C318(F),
   then out (0x800E2AD8). The burst (state 2) slips only grounded fielders (+0x22E == 0, 80117E34) for its timer
   (0x806311F4: 12 / 10 frames); a jump is airborne ~2*rise + hang (36+ frames), so it covers the whole quake.
2. DECIDE 0x800E2A18 (`or r3,r30,r30` before `bl 8011F4D0`; past all gates). Replaces the chemistry roll and the hop:
   How often [C]: every frame, for the chaser only (800C8384 -> 800E21EC -> vtable +0x14), while the ball is loose
   (game+0x2A4C < 0, +0x2A72 == 0, no pass target ai+0x320) and F is free: +0x265 == 0, not airborne +0x22E, not
   busy 8012BA58 (+0x23E/23F/240/242/243/24C/246), frames since contact >= reaction delay +0x226 + 3. No distance
   gate (the stock "near" flag r27 only feeds the roll). A committed catch (+0x2AC) does not block it [C].
   Frame order [C]: 801326FC runs the ball update 800AC784 (moves the ball; 800B38C8 re-predicts the path from the new
   position every frame the ball is loose: path[0] = the ball now, path[i] = i frames from now [C per the fly-jump
   fix; exact only while the prediction holds]) and then 800C8384: 800CF554 clears the presses (ai+0xCC..0xD4,
   800CF6F8..800CF738), 800E21EC (this hook) writes ai+0xD4, then 800D5A38 runs each fielder: 8010BCB0 (F+0x13C =
   |ball (800AC748) - F| on the ground, then 8011F748 when +0x2AC == 0 -> the hit test FUN_8011F2B0 while +0x265
   != 0; 80120278 counts a committed catch down instead) and 8010B200 (the state handler). The chaser's mover
   (80125238 / 80125F8C) ends in 80112BC4, which calls 8011D5F4 first: ai+0xD4 (slot 4 = ai+0xCC + 2*F+0x2C9, F =
   ai+0x200 = the chaser; needs F+0x266) -> +0x265 = 1, +0x20A = 0, only his facing +0xF8/+0xDC turned, any
   committed catch cancelled (+0x2AC = 0, speed +0xE4 = 0), and 80112BC4 returns before any position update. From
   then on the busy gate sends +0x265 != 0 to 8011ED4C (+0x20A += 1 per frame): no movement. So he stays exactly
   where this hook sees him (F+4/F+0xC), and the hit test runs at press + 1, + 2, ... with the ball at path[1],
   path[2], ...: no index offset, no slide. The press is only good the frame it is written (cleared next frame).
   Hit test FUN_8011F2B0 [C]: chemistry on (80131AA4), ai+0x36C clear, game+0x2A72 != 2, F not ai+0x320, F+0x269
   clear, +0x265 == 1, F+0x13C <= F+0x1C (radius) + game+0x420 (ball radius), ball y in [F+0xD4 - r, F+0xD4 +
   F+0x20]. No distance limit and no pair chemistry (FUN_8015C800 is only in the stock roll 8011F4D0): on a hit the
   ball goes to the nearest teammate (801148F4, any distance; ai+0x320, 8010D94C(mate, 0x1D)), and 800AFF64 throws
   it at 0.4/frame (mode 0; 0.6 mode 1) toward him, flight capped at 0x80625FF4 = 20.0: a mate past 20 gets a pass
   that comes down about 20 out and rolls on to him [C], not an in-air catch.
   Live window [C code]: 801401D8 (in 8011D5F4) arms the anim controller 8013F5A0 (ctrl +0xC6 = 1): +0x20A > 1 ->
   anim 0x9E (ctrl 2); then +0x265 = 2 once the current sequence is 27 with <= 1.0 left, or is not 27. +0x20A is 2
   at press + 2, so +0x265 is still 1 at path frames 1-3 whichever order the controller runs in [C]; to about frame
   16 if sequence 27 (15 frames for 62 of 63 characters, dt_na) plays at rate 1 from frame 2-3 [I, UNMEASURED].
   ATTACK SEQUENCE (Nick, 2026-09-27: "move to the spot to attack, then turn and face the ball and attack"; the
   earlier versions never stopped him: ROUTE's spot lost to the stock catch commits in 8011F748, see 6). Level 6 CPU
   chaser with the nearest teammate (801148F4) within ATK_MATE_D (20.0, the pass flight cap 0x80625FF4; or within
   ATK_HOME_D 50 with the pass heading within ATK_HOME_DEG 22.5 of home plate: toward_home), chemistry
   on, ai+0x36C clear, that teammate able to act (MATE_UNABLE below); every frame, from the path re-predicted that
   frame:
   - MOVE: S = B - u * ATK_BACK * reach (reach = F+0x1C + game+0x420): B = path[m], m = the stock meeting frame
     k = |F+0x1EC - now + 1| (a grounder: his pickup point), or for a ball in the air the landing L when later (the
     first path frame at or under his head, then down to the bottom of that fall); u = the ball's ground direction
     at B (path[m] - path[m-1]); S = B when the ball has no ground motion. n = (int)(|S - F| / F+0xEC) frames to get
     there (F+0xEC = his top run speed, 8010BCB0 sets it every frame from vtable +0x30 [C]; acceleration ignored [I]).
     Planned when some path frame t >= n + 3 (n = 0 when within AT_SPOT) passes the hit test from S. No frame from
     S at all -> REASON 11; only earlier than he can be there -> REASON 15; the ball never down to his height ->
     REASON 12: then no plan (the normal play below; the press from where he stands still applies).
     While planned (PHASE 1-3): ROUTE targets S. The mover then runs along the heading to S at +0xE4 and, when the
     rest is under one step, steps exactly onto the target and zeroes speed / +0x114 (80112BC4 tail) [C]: he stops on
     S, no overshoot; with the target on him (80125238: d == 0 -> +0xE4 = +0x114 = 0) he stands. The catch block of
     8011F748 is skipped (hook 6), so no standing catch / run-catch glide / dive gets committed [C].
   - STAND FIRST (Nick, 2026-09-27, the SS dump 17:07: the ball passed 0.47 m from him, reach 0.85, but he was sent
     to a spot 1.5 m back, the plan flipped to "can't reach" mid-run and the game's catch took over): before MOVE, the
     scan from where he stands; if the ball comes through his reach there, S = his spot (FLAGS bit 3): TURN / ATTACK
     below, no move. Only otherwise MOVE.
   - TURN: on S (within AT_SPOT): FACE = |angle to the ball now (path[0]) - F+0xDC| (wrapped). Over 0.78 (the game's
     own window 0x80625DC4): F+0xDC = F+0xF8 = atan2 (8053E1E4, radians: 80562614's result * 2pi/256), the two fields
     8011D5F4 writes on a press (PHASE 2); else PHASE 3 (set, waiting). Facing does NOT matter for the hit: 8011F2B0
     reads only F+0x13C, +0x1C, +0xD4, +0x20, +0x265, +0x269 and ids, and the knocked ball goes to the nearest
     teammate (801148F4), not where he faces [C]. It is what the swing looks like: at the press 8011D5F4 turns him to
     the first path frame (0..14, 0x806281D0) under his head within 10.0 (0x80625DC0), but only if that is within
     0.78 of his facing (8011D91C), else toward a wall / item / dizzy fielder or not at all [C]. A standing chaser is
     also turned to the ball every frame by 80115CFC (via 8012BE34 / 8012D354..) in the common case [C, flags not
     all traced]; TURN makes sure of it before the press.
   - ATTACK: t = the first path frame in [1, ATK_SCAN] that passes the hit test from where he stands now (T). t <=
     ATK_LAST (3, the sure live frames): press (ai+0xD4 = 1; PHASE 4, REASON 0). The ball comes closer every frame and
     DECIDE sees every frame, so the press lands on t = 3 (or less for a ball that jumps into reach). Planned and t
     later / none: wait (no jump, no catch). Not planned: when his committed catch lands next frame (F+0x2AC set,
     F+0x2A4 <= 1) press now if t <= ATK_MUST (8, the [I] part of the swing); else the normal play.
   - the press may also come while he is still running (t <= 3 from where he is): the press freezes him there, the
     hit test runs from that spot, so it connects all the same.
   Same-frame dive and attack presses: the dive request (800E246C, vtable +0x10) runs before 800E2830 (+0x14); the
   dive is consumed in 8010BCB0 -> 8011F748 -> 801222D0 before the mover's 8011D5F4 (8010B200) [C], so a dive
   would win; cpu_dive.py presses none while PHASE is 1-4 (last frame's block), and hook 6 skips 801222D0 too.
   Debug block (defense_dbg, every frame for the chaser; FRAME first): see defense_dbg.py for the fields and REASONs.
   History: "F+0x13C <= 3.0 and the ball below his head" (missed); then t in [1, 16]; then [1, 8]; then ATKSPOT in
   ROUTE with the press at t <= 3 (Nick: still not attacking: the stock catch commits and glides won).
   - fly ball (game+0x2A4E == 0 and game+0x29B4 > 5.0, the stock grounder/liner test of 800E246C) with no teammate
     nearby (or no connect): jump so the catch is at the peak. Jump type = 1 if the fielding ability (vtable +0x3C)
     is 2 (Super Jump), else 0; LEAD = rise + hang/2 frames and PEAK the rise height, both from the jump table
     0x80625BD8 (vy -= g, h += vy; normal 15 + 3 frames, 2.1 up; Super Jump 20 + 6, 3.8 up). Jump on the frame where
     the predicted ball height (path game+0x430 + i*0x14, i = frames from now) crosses F+0x20 + PEAK between
     i = LEAD-1 and LEAD, and only when the ball at i is within HALF his standing catch reach F+0x184 (Nick's 12:55
     dump: reach + 1.0 = 1.95 let the CF jump at a ball 1.9 m off with a 1.92 reach; he drifted and missed it by 0.1;
     the other half is the margin for his drift / the prediction) of where he will be then (his
     position + his heading (+0x94 / +0x98) x speed (+0xE4) x LEAD; standing: where he is). (Was: F+0x148 <= ARRIVE,
     taken as his distance to his target; it is the distance to the ball's first bounce [dem], and no fly-ball jump
     ever showed in Nick's dumps; Nick, 2026-09-29: "if it can't attack but can jump it should jump".) If that frame
     has passed (already below at now+LEAD-1): no jump, he stands and takes it. The outcome goes in dbg.JUMP.
   - ground ball / liner with no teammate nearby: nothing (was: the stock code). The stock roll after 8011F4D0 sets
     ai+0xD4 (the same +0x265 action) when F is within 2.0 of a wall / a dizzy fielder or 3.0 of an item and faces one
     (8011E0CC / 8011DC98 / 8011DD78), with no look at the ball: at level 6 that was an "attack" at nothing, and the
     stock hop fought ROUTE's run-around. Never the stock roll or hop at level 6.
3. RUN-CATCH SPOT 0x8012179C (FUN_80121520, the run-catch predictor: a moving fielder commits a catch 2..12 frames
   ahead, 801201E0 type 7, and 80124F10 glides him (spot - F) / i per frame to spot = F + (B - F)(|B - F| - reach)/
   |B - F|, B = the ball at path frame i, reach = 0x80625B60[F+0x221] = 0.95..1.4). The ball then passes 0.95-1.4 from
   his centre, outside the attack's body radius + ball radius (Nick: "not attacking balls when people are nearby
   that are easy attacks"). Level 6, F the chaser with the attack available (attack_ready: ai+0x36C clear, chemistry
   on, the nearest teammate within ATK_MATE_D and able to act): the spot is B itself when the whole run passes the predictor's own time test
   ((int)(|B - F| / (speed * 1.1)) + 1 <= i, 1.1 = 0x80625E64 as 0x8012173C reads it), so the glide stays on the
   ball's path and DECIDE can press on a frame whose frozen spot connects; without a press, the same catch at B.
   A fielder who is not the chaser never attacks (DECIDE is chaser-only) [C].
4. ROUTE 0x801257F8 (FUN_80125238, the chaser's mover, `lfs f2,0xC(r1)` right after the route call 8011A97C in its
   default branch: target = path[k] (+0.3 outward), k = |F+0x1EC - frames since contact + 1|, F+0x1EC = the frame he
   meets the ball; x/z at 0xC(r1) / 0x8(r1), F = r28) and 0x80125FFC (FUN_80125F8C, the wall play, same instruction
   and layout, F = r31).
   PLAN (80125238 only, first): while the attack is planned (debug block FRAME == now, CHASER him, PHASE 1-3) the
   target becomes S (SPOT_X / SPOT_Z, from DECIDE earlier this frame). A catch committed before the plan (F+0x2AC:
   80112BC4 would glide him with 80124F10 instead) is cancelled with the same field writes 8011D5F4 / 80112BC4 use on
   a press (FLAGS bit 1), unless that cancel would call 800AEC4C (+0x2C7 5 / 7 or +0x2C1) or it lands next frame:
   then REASON 14. Only the default branch of 80125238 has the hook: its wall-play branches (game+0x2A71) don't [C].
   AVOID (both movers, after PLAN, so an item in the way wins), for the chaser (ai+0x2D8 == F+0x21C) of a level 6
   CPU team: 8011E4F0(F, &item) (the stock item detection: nearest active item on the ground plane, the phases the
   hop reacts to) within RANGE; with d = item - F and u = target - F, the item is in the path when 0 < d.u < |u|^2
   and the side distance |d x u| / |u| < CLEAR. Then the target becomes a waypoint beside the item,
   W = item - sign(d x u) * OFFSET * (u.z, -u.x) / |u| (the side away from the item), until the item is behind him
   or off the line, when the stock target comes back by itself. 1/|u|: frsqrte + one Newton step.
5. BOO 0x80459C74 (the Boo update FUN_80459BB0, `bl 0x800E9D84`). The Boo's only effect on fielders is that call,
   every frame while active: FUN_800E9D84 puts every fielder not controlled by a pad slot (for a CPU team: all of
   them, slot 4 is not in its list) into state 0xC (stopped) via 8010D94C. The ball hiding (game+0x2A8A, read only
   by the landing marker, sounds and 80147DD0 [I]) and 800B866C stay. At level 6 with fielder 0 of the fielding
   side (0x80708D9C / 0x80708DC0 / 0x80708D78 chain, as 800E9D84 picks them) at level byte 0: the call is skipped.
   (boo_ball.py hooks 0x80459C20 and 0x8014863C in the same area: no overlap.)
   BOO BLUR (Nick, 2026-09-29: "make the boo add an epsilon to where the fielders think the ball is ... wide enough
   that they miss 40% of the time and make it normally distributed. Level 5 and 6"): the stock CPU fielders read the
   real ball while it is hidden (game+0x2A8A is read only by the marker / sounds [I]). On a Boo's first frame (the
   hook above, the CPU fielding) each fielder index 0..8 draws z = (z_x, z_z), two standard normals (each the sum of
   BLUR_N uniforms, minus BLUR_N / 2: Irwin-Hall, variance BLUR_N / 12 = 1; an xorshift32 stirred by the game's rand
   once per draw), and is a
   MISS when |z| > K (P = exp(-K^2 / 2) = BLUR_P for a 2-D standard normal: 40% -> K = sqrt(2 ln 2.5) = 1.354; its
   own K per level, the Boo Error Rate setting, read by FLAG).
   While the ball is hidden: the route hooks move his target by z * his catch reach (F+0x184) / BLUR_K, so the miss
   is exactly "the error is past his reach", and a MISS fielder's catch / run-catch / dive block (8011F748) is skipped
   (the game's catch tests read the real ball). The draw resets when the ball shows again.

6. CATCH BLOCK 0x8011FCD4 (FUN_8011F748, `or r3,r27,r27` before bl 80121050; r27 = F): the fielder update 8010BCB0
   calls 8011F748 every frame (+0x2AC == 0); with +0x265 == 0 it tries the standing catch 80121050 (commits a catch
   when a path frame comes within F+0x188 (0.6-1.2) of him, ahead of the attack's 0.7 reach), then the run-catch
   80121520, then the dive 801222D0. While the attack is planned or pressed this frame for him (PHASE 1-4) the whole
   block is skipped (out through its epilogue 0x8011FE54; FLAGS bit 0).
The header (POW hook, 0x800E28CC, before 800E2830's gates) writes FRAME / CHASER / the gate REASON every frame
800E2830 runs; FRAME stale = 800E2830 didn't run (ball held / not loose / no chaser / pass target set).

INFERRED / UNMEASURED: the swing past path frame 3 (ATK_MUST), ATK_BACK, AT_SPOT, the run-time estimate (top speed,
no acceleration), the path being exact frame for frame (bounces, walls), whether a skipped catch block has other
effects in play, how often a catch lands before the attack; the game's atan2 runs paired-single code the Unicorn
test can't execute (faked there); see the constants below and the test
(scripts/test_cpu_item_defense.py, which also runs the game's own FUN_8011F2B0 after every press).
"""
import math
import struct
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
import cpu_dive  # noqa: E402
import defense_dbg as dbg  # noqa: E402
import level5  # noqa: E402
from ppc import Asm, bc, branch, ha, lo, x_form  # noqa: E402

# hooks: (address, stock word)
POW_HOOK, POW_ORIG = 0x800E28CC, 0x881F2A72          # lbz r0,0x2A72(r31)
DECIDE_HOOK, DECIDE_ORIG = 0x800E2A18, 0x7FC3F378    # or r3,r30,r30
ROUTE_HOOKS = ((0x801257F8, 28), (0x80125FFC, 31))    # lfs f2,0xC(r1); F in r28 / r31
ROUTE_ORIG = 0xC041000C
MOVER_HOOK, MOVER_ORIG = 0x80113318, 0xEC412028      # FUN_80112BC4 (the shared mover): fsubs f2,f1,f4 (the re-aim)
BOO_HOOK, BOO_ORIG = 0x80459C74, None                 # bl 0x800E9D84 (checked with branch())
STAR_HOOK = 0x802FEC84                                # FUN_802FEAF4 (the Peach Garden night star): the same bl 0x800E9D84
CATCH_HOOK, CATCH_ORIG = 0x8012179C, 0xEC3BF824      # FUN_80121520: fdivs f1,f27,f31 (the run-catch spot scale)
BLOCK_HOOK, BLOCK_ORIG = 0x8011FCD4, 0x7F63DB78      # FUN_8011F748: or r3,r27,r27 before bl 80121050 (catch block)
BLOCK_SKIP = 0x8011FE54                               # FUN_8011F748's epilogue (past the catch / run-catch / dive block)
OUT = 0x800E2AD8                                      # FUN_800E2830's epilogue

# game functions / tables
FREEZE = 0x800E9D84            # Boo: stop the uncontrolled fielders
JUMP = 0x8011C318              # fielder jump (reads ai slot flag +0xC8)
NEAREST_MATE = 0x801148F4      # (F, float *d) -> nearest teammate id, d
ITEM_NEAR = 0x8011E4F0         # (F, item **out) -> f1 distance to the nearest active item
BUSY = 0x8012BA58              # (F) -> nonzero when +0x23E/23F/240/242/243/24C/246 is set (pure)
ATAN2 = 0x8053E1E4             # (f1 = dz, f2 = dx) -> f1 radians, the game's facing angle (8011D91C, 80125238)
RUN_SLACK = 0x80625E64         # + mode*0xA0: 1.1, the run-catch predictor's speed factor (80121520)
JUMP_TABLE = 0x80625BD8        # [vy, g, horiz, hang] per type, 4 types per mode
POW_GRAVITY = 0x806311EC       # + mode*0x60 + row*0x30
MATE_NEAR = 0x80625FF4         # + mode*0x2C: 20.0 (stock; also the pass flight's cap, 800AFF64)
BALL_NEAR = 0x80797260         # 3.0
FIELDERS = (0x80708D9C, 0x80708DC0, 0x80708D78)
# BOO BLUR (docstring): BLUR block: u8 drawn, u8 miss[9], pad, u32 xorshift state 0xC, f32 z[9][2] at 0x10, u32
# scratch 0x58, f32 consts from 0x5C
BLUR_P, BLUR_N = (0.40, 0.40, 0.40), 12              # BLUR_P: the Boo Error Rate at levels 5, 6 (cpu_settings "boo_error_rate")


def blur_k(p):
    """K with P(|z| > K) = p for a 2-D standard normal: sqrt(2 ln(1 / p)) (0.40: 1.3537); p clamped to (0, 1)."""
    p = min(max(p, 1e-6), 1 - 1e-6)
    return (2 * math.log(1 / p)) ** 0.5


BLUR_K = blur_k(BLUR_P[2])                     # (level 6's; the tests)
# the block's level rows (FLAG 1 / 2): f32 1 / K, K^2 at B_KROW + (FLAG - 1) * 8
B_DRAWN, B_MISS, B_STATE, B_Z, B_SCR, B_OFF, B_ONE, B_ZERO, B_KROW = 0, 1, 0xC, 0x10, 0x58, 0x64, 0x68, 0x6C, 0x70
B_KINV, B_K2 = 0, 4                            # within a level row
B_SIZE = 0x70
BLUR = None                                    # the block's address (apply)
F_HREACH = 0x184                               # his standing catch's horizontal reach (cpu_dive.F_HREACH)
G_HIDDEN = 0x2A8A                              # game u8: the ball hidden (Boo / the Peach Garden star)
RAND, RNG = 0x80165C14, -0x1578                # rand(r3 = *(r13-0x1578), r4 n) -> r3 (seeds the draw's xorshift)
DEFENSE = (-0x1D14, -0x1D10, -0x1D18, -0x1D1C)
MODE = -0x1658                 # r13: mode byte
TICK = -0x1684                 # r13: *(..)+2 = frames since contact
ITEMS = -0x354                 # r13: item manager
LINER_HEIGHT = -0x7A54         # r2: 5.0
ZERO = -0x7600                 # r2: 0.0

# fielder / ai / game fields
F_LEVEL, F_AIR, F_ALLOW, F_ID, F_HEIGHT, F_GROUND = 0x2E, 0x22E, 0x26A, 0x21C, 0x20, 0xD8
F_BALL_DIST, F_TARGET_DIST, F_X, F_Z = 0x13C, 0x148, 0x4, 0xC
F_DIRX, F_DIRZ, F_SPEED = 0x94, 0x98, 0xE4    # his heading (unit x, z) and current run speed (cpu_items' lead)
F_MEET = 0x1EC                 # the frame (since contact) the mover meets the ball: route target = path[F+0x1EC - now + 1]
F_CATCH, F_CATCH_LEFT = 0x2AC, 0x2A4   # committed catch type (801201E0), frames left (80120278 counts it down)
F_ACTION, F_DELAY, F_RUN = 0x265, 0x226, 0xEC   # the +0x265 action, reaction delay, top run speed (8010BCB0, per frame)
F_FACE, F_HEADING = 0xDC, 0xF8  # facing (what 8011D91C compares, 80115CFC sets) / run heading; 8011D5F4 writes both
GAME_PTR = -0x1D94             # r13: the game object
AI_JUMP, AI_PASS, AI_CHASER = 0xC8, 0xD4, 0x2D8
G_LANDED, G_HEIGHT, G_BALL_Y, G_PATH_Y = 0x2A4E, 0x29B4, 0x450, 0x430
G_HELD = 0x2A72                # 800E2830's first gate: ball held / not live
PATH_LAST, PATH_STRIDE = 0x1DF, 0x14
POW_ID, POW_POOL, POW_STATE, POW_ROW, POW_Y, POW_VY = 3, 0x180, 0x3A, 0x34, 0x8, 0x14
# NO ATTACK WITH A POW PENDING (Nick, 2026-09-28: "not attack if the opponent is still holding a pow (or it has not hit
# the ground yet)"): the attack plan is off (REASON 17, the normal play) while the batting slot holds an unused POW or
# a POW is in flight. The manager's 5 slot entries (+0x338, 0xC apart; the dumps of 2026-09-28): u32 item, +4 used
# (1 once thrown), +6 armed (can throw), +7 the active batting slot (the others repeat the id with no flags)
SLOTS, SLOT_SIZE, SLOT_N, SLOT_USED, SLOT_ACTIVE = 0x338, 0xC, 5, 4, 7
POW_PENDING = 17
# NO ATTACK TOWARD A TEAMMATE WHO CAN'T ACT (Nick's dump, 2026-09-28: after a POW burst a fielder attacked toward a
# teammate the POW had knocked down; the action was wasted). On a connect the game's hit test FUN_8011F2B0 sends the
# ball to 801148F4's nearest teammate (0x8011F47C: no look at his state, no next-nearest) [C], so when that teammate
# is busy (BUSY 8012BA58: stunned / knocked down / ...) or airborne (+0x22E, the header's gate) the attack is off
# (REASON 18, the normal play). His object: FIELDERS[k][id] (+0x24 table, then +0x48, then 0x80708D78, as stock);
# none found -> off too.
MATE_UNABLE = 18
# the pass / attack (+0x265) connect test FUN_8011F2B0 [C]
CHEM_ON = 0x80131AA4           # chemistry on (8011F2B0 returns 0 without it)
AI_ATK_OFF = 0x36C             # ai byte: 8011F2B0 returns 0 when set
F_RADIUS, F_Y = 0x1C, 0xD4     # fielder radius, world y of the feet
G_BALL_R, G_PATH_X, G_PATH_Z = 0x420, 0x42C, 0x434
ATK_FIRST = 1                  # the first path frame the hit test sees after a press [C]
ATK_LAST = 3                   # press when the first connecting path frame is <= this: +0x265 is still 1 at path
                               # frames 1-3 whichever order the anim controller 8013F5A0 runs in [C code]
ATK_MUST = 8                   # ... or, when a committed catch completes next frame (F+0x2AC set, F+0x2A4 <= 1), when it
                               # is <= this: +0x265 stays 1 to about frame 16 (anim 0x9E, sequence 27, 15 frames for 62
                               # of 63 characters, from path frame 2-3) [I, playback UNMEASURED]; 8 = half, a margin
ATK_SCAN = 60                  # path frames scanned for a future connect (a fly ball: wait for it instead of jumping)
ATK_MATE_D = 20.0              # level 6 "teammate nearby" (Nick: 20 m, the game caps the pass flight at 0x80625FF4 = 20.0)
AT4 = {}
AT5 = {}                       # level 5's own ATK_MATE_D (cpu_settings; level5.pair): a float after consts(), C_MATE5
ATK_HOME_DEG = 22.5            # Nick, 2026-09-28: "also have it attack if the angle the attack would go is within 22.5
                               # degrees of towards home plate": a teammate past ATK_MATE_D still counts when the pass
                               # (F -> him, where the hit test sends the ball) heads within this of home plate (0, 0)
ATK_HOME_D = 50.0              # ... and he is within this (Nick: "for the 22.5 degree rule do 50m")
ATK_BACK = 0.8                 # the attack spot: this fraction of the reach (F+0x1C + ball radius) back up the ball's
                               # ground track from the landing / pickup point ("just under" the reach; UNMEASURED)
AT_SPOT = 0.3                  # within this of the attack spot = there: turn / wait / press (UNMEASURED; the mover
                               # steps exactly onto its target anyway, 80112BC4 [C])
FACE_TOL = 0x80625DC4          # 0.78 rad: 8011D91C (the press's own facing pick) turns him to the ball only within this
                               # of his facing, so TURN writes the facing when he is off by more [C]

# tuning (all UNMEASURED in game unless noted)
POW_K = 2           # jump when the POW lands within this many frames ("right before"); INFERRED safe: airborne 36+
ARRIVE = 1.0        # (unused since Nick's 12:55 dump; the peak jump's reach is half his catch reach F+0x184)
JUMP_LATE = 6       # the peak jump still goes up to this many frames after the crossing (Nick's 12:26 dump: the crossing
                    # frame fell in an attack plan cancelled 2 frames later, "too late" for a 1-frame window)
RANGE = 8.0         # only items within this (ground distance) are avoided
CLEAR = 2.0         # an item closer than this to his line is in the path
OFFSET = 2.5        # waypoint distance beside the item

# CONST block layout (in data)
C_LEAD0, C_PEAK0, C_LEAD1, C_PEAK1, C_ARRIVE, C_POWK, C_POWKK = 0, 4, 8, 0xC, 0x10, 0x14, 0x18
C_RANGE, C_CLEAR2, C_OFFSET, C_HALF, C_3HALF, C_ITEM, C_ONE = 0x1C, 0x20, 0x24, 0x28, 0x2C, 0x30, 0x34
C_MATE, C_BACK, C_TINY = 0x38, 0x3C, 0x40
C_ATSPOT, C_FACETOL, C_PI, C_2PI, C_BIG, C_HOME2, C_HOMED = 0x44, 0x48, 0x4C, 0x50, 0x54, 0x58, 0x5C
C_LEADF = 0x60                      # f32 LEAD row 0, pad, row 1 (+8: the same row step as C_LEAD0 / C_LEAD1)
C_MATE4, C_MATE5 = 0x6C, 0x70         


def f32(dol, addr):
    return struct.unpack(">f", struct.pack(">I", dol.u32(addr)))[0]


def jump_profile(dol, jtype):
    """(LEAD frames to the middle of the peak hang, PEAK height) of jump type 0/1, from the table (mode 0; mode 1
    rows are asserted equal)."""
    rows = [[f32(dol, JUMP_TABLE + mode * 0x40 + jtype * 0x10 + i * 4) for i in range(4)] for mode in (0, 1)]
    assert rows[0] == rows[1], rows
    vy, g, _, hang = rows[0]
    h, n = 0.0, 0
    while vy - g > -1e-6:                   # vy -= g; h += vy (8011C770), up to vy 0
        vy -= g
        h += max(vy, 0.0)
        n += 1
    return n + int(hang) // 2, h


def consts(dol):
    lead0, peak0 = jump_profile(dol, 0)
    lead1, peak1 = jump_profile(dol, 1)
    kk = POW_K * (POW_K - 1) / 2
    base = (struct.pack(">IfIf", lead0, peak0, lead1, peak1)
            + struct.pack(">ffffffff", ARRIVE, POW_K, kk, RANGE, CLEAR * CLEAR, OFFSET, 0.5, 1.5)
            + bytes(4) + struct.pack(">ffff", 1.0, ATK_MATE_D, ATK_BACK, 1e-6)
            + struct.pack(">fffff", AT_SPOT, f32(dol, FACE_TOL), 3.14159265, 6.28318531, 1e30)
            + struct.pack(">ff", math.cos(math.radians(ATK_HOME_DEG)) ** 2, ATK_HOME_D)
            + struct.pack(">fff", lead0, 0.0, lead1))
    assert len(base) == C_MATE4
    m4, m5, m6 = _mates()
    return base + (struct.pack(">2f", m4, m5) if (m4 != m6 or m5 != m6) else b"")


def _mates():
    return level5.pair(sys.modules[__name__], "ATK_MATE_D")


def gate6(a, skip, reg=12):
    """Branch to `skip` unless the level 5 FLAG byte is 2 (level 6). Clobbers `reg` and cr0."""
    level5.gate(a, reg, skip, "cpu-item-defense")   # levels 5 and 6 (each as the CPU levels tab has it)


def do_jump(a):
    """F = r30, ai = r29: the stock hop's jump (ai+0xC8 = 2, 8011C318), with the 'allowed' flag set."""
    a.li(0, 1).stb(0, F_ALLOW, 30).li(0, 2).stb(0, AI_JUMP, 29).mr(3, 30).bl(JUMP)


def rsqrt_newton(a, y, x, t, u):
    """y ~ 1/sqrt(x), frsqrte (good to 1/32) + two Newton steps. Needs the CONST base in r27."""
    a.frsqrte(y, x)
    for _ in range(2):
        a.fmuls(t, y, y).fmuls(t, t, x).lfs(u, C_HALF, 27).fmuls(t, t, u)
        a.lfs(u, C_3HALF, 27).fsubs(t, u, t).fmuls(y, y, t)


def sqrt(a, x, y, t, u):
    """x = sqrt(x + C_TINY) (x >= 0; the tiny bias makes 0 safe). Clobbers y, t, u. Needs the CONST base in r27."""
    a.lfs(t, C_TINY, 27).fadds(x, x, t)
    rsqrt_newton(a, y, x, t, u)
    a.fmuls(x, x, y)


def header(a, fr, reg):
    """The debug block header for the chaser F (register `fr`), block base into `reg`: FRAME first, then CHASER.
    Clobbers r0, r11."""
    a.load_addr(reg, dbg.ADDR)
    a.lwz(11, TICK, 13).lha(11, 2, 11).sth(11, dbg.FRAME, reg)          # (r0 as a base reads address 0)
    a.lbz(0, F_ID, fr).stb(0, dbg.CHASER, reg)


def pow_stub(at, cbase):
    """0x800E28CC, the top of FUN_800E2830 before its gates (every frame 800E21EC calls it: ball loose, a chaser).
    Level 6 CPU chaser: the debug block header (FRAME, CHASER; PHASE / PRESS / FLAGS 0, T / T_SPOT -1; REASON = the
    first of 800E2830's own gates below that stops it: 5 ball held game+0x2A72, 13 in the action +0x265 (PHASE 4),
    2 airborne, 3 busy 8012BA58, 4 reaction delay; else 255, which DECIDE overwrites), then the POW jump (REASON 16).
    f0-f2 (F's position, stored to the stack right after the hook) are reloaded before going back."""
    a = Asm(at)
    gate6(a, "stock")
    a.lbz(0, F_LEVEL, 30).cmpwi(0, 0).bne("stock")
    header(a, 30, 12)
    a.li(0, 0).stb(0, dbg.PHASE, 12).stb(0, dbg.PRESS, 12).stb(0, dbg.FLAGS, 12).stb(0, dbg.JUMP, 12)
    a.li(0, -1).stb(0, dbg.T, 12).stb(0, dbg.T_SPOT, 12)
    a.li(0, 5).lbz(4, G_HELD, 31).cmpwi(4, 0).bne("hdr")
    a.li(0, 13).lbz(4, F_ACTION, 30).cmpwi(4, 0).beq("g_air")
    a.li(4, 4).stb(4, dbg.PHASE, 12).b("hdr")                       # in the action: attacking
    a.label("g_air")
    a.li(0, 2).lbz(4, F_AIR, 30).cmpwi(4, 0).bne("hdr")
    a.mr(3, 30).bl(BUSY).cmpwi(3, 0).load_addr(12, dbg.ADDR).li(0, 3).bne("hdr")
    a.li(0, 4).lwz(4, TICK, 13).lha(4, 2, 4).lbz(5, F_DELAY, 30).addi(5, 5, 3).cmpw(4, 5).blt("hdr")
    a.li(0, 0xFF)
    a.label("hdr")
    a.stb(0, dbg.REASON, 12)
    a.lbz(0, F_AIR, 30).cmpwi(0, 0).bne("stock")
    a.lwz(3, ITEMS, 13).cmpwi(3, 0).beq("stock")
    a.lwz(0, 0x394, 3).cmpwi(0, POW_ID).bne("stock")
    a.addi(3, 3, POW_POOL)
    a.lbz(0, POW_STATE, 3).cmpwi(0, 1).bne("stock")                 # in flight
    a.lbz(4, POW_ROW, 3).mulli(4, 4, 0x30).lbz(0, MODE, 13).mulli(0, 0, 0x60).add(4, 4, 0)
    a.load_addr(5, POW_GRAVITY).add(5, 5, 4).lfs(3, 0, 5)           # f3 = g
    a.load_addr(6, cbase).lfs(4, C_POWK, 6).lfs(5, C_POWKK, 6)
    a.lfs(1, POW_Y, 3).lfs(2, POW_VY, 3)
    a.fmadds(1, 2, 4, 1).fnmsubs(1, 3, 5, 1)                        # y + K*vy - g*K(K-1)/2
    a.lfs(0, F_GROUND, 30).fcmpo(1, 0).bgt("stock")
    a.load_addr(12, dbg.ADDR).li(0, 16).stb(0, dbg.REASON, 12)
    do_jump(a)
    a.b(OUT)
    a.label("stock")
    a.lfs(2, F_X, 30).lfs(1, 8, 30).lfs(0, F_Z, 30)                 # F's position, as 800E28B4..C0 loaded it
    a.word(POW_ORIG)
    a.b(POW_HOOK + 4)
    return a


def decide_stub(at, cbase):
    """DECIDE at 0x800E2A18, past 800E2830's gates. The level 6 path always leaves through OUT, whose epilogue
    restores r27 / r28 / f29-f31 (saved by the prologue; the GPR save area is 0x4C..0x5F(r1)), so they are free here
    and 0x8..0x4B(r1) is dead scratch. r27 = CONST, r28 = the debug block, f31 = his reach, f30 = the angle to the
    ball. See the docstring (DECIDE: MOVE / TURN / ATTACK)."""
    a = Asm(at)
    gate6(a, "stock")
    a.lbz(0, F_LEVEL, 30).cmpwi(0, 0).bne("stock")
    header(a, 30, 28)
    a.li(0, 0).stb(0, dbg.PHASE, 28).stb(0, dbg.PRESS, 28)
    a.li(0, -1).stw(0, dbg.AUX0, 28).sth(0, dbg.M_FRAME, 28).stb(0, dbg.T, 28).stb(0, dbg.T_SPOT, 28)
    a.load_addr(27, cbase)
    a.lfs(0, F_RADIUS, 30).lfs(1, G_BALL_R, 31).fadds(31, 0, 1).stfs(31, dbg.REACH, 28)   # reach
    a.mr(3, 30).addi(4, 1, 0xC).bl(NEAREST_MATE)                    # 0xC(r1): dead scratch
    a.stb(3, dbg.MATE_ID, 28).lfs(1, 0xC, 1).stfs(1, dbg.MATE_D, 28)
    if _mates()[0] == _mates()[1] == _mates()[2]:
        a.lfs(0, C_MATE, 27)
    else:                                                           # level 5's own (r4: the call clobbered it)
        level5.pick(a, 4, C_MATE4, C_MATE5, C_MATE).add(4, 4, 27).lfs(0, 0, 4)
    a.fcmpo(1, 0).ble("near")                                       # within ATK_MATE_D
    toward_home(a, 30, 27, "why7", "th")                            # past it: only a pass toward home plate
    a.label("near")
    mate_unable(a, "why_n", "mu")                                   # r3 = his id: can't act -> no attack (REASON 18)
    a.bl(CHEM_ON).cmpwi(3, 0).li(0, 6).beq("why_n")                 # the action can't connect: no attack
    a.lbz(3, AI_ATK_OFF, 29).cmpwi(3, 0).bne("why_n")
    # ---- NO ATTACK WITH A POW PENDING (above): held unused by the batting slot, or in flight ----
    pow_pending(a, "why_n", "pw")
    # ---- STAND (Nick, 2026-09-27: the SS "did not need to move back at all ... see ball and attack"): the ball comes
    # through his reach from where he stands -> S = here: no move, face it, attack (FLAGS bit 3) ----
    a.lfs(10, F_X, 30).lfs(11, F_Z, 30).li(9, ATK_FIRST).bl("scan")
    a.cmpwi(6, 0).blt("mv")
    a.stfs(10, dbg.SPOT_X, 28).stfs(11, dbg.SPOT_Z, 28).lfs(0, ZERO, 2).stfs(0, dbg.SPOT_D, 28).stb(6, dbg.T_SPOT, 28)
    a.lbz(0, dbg.FLAGS, 28).ori(0, 0, 8).stb(0, dbg.FLAGS, 28)
    a.b("there")
    a.label("mv")
    # ---- MOVE: the attack spot S = B - u * ATK_BACK * reach (B = path[m], u = the ball's ground direction at B) ----
    a.lha(5, F_MEET, 30).lwz(6, TICK, 13).lha(6, 2, 6).subf(5, 6, 5).addi(5, 5, 1)    # k = F+0x1EC - now + 1
    a.cmpwi(5, 0).bge("kpos").li(0, 0).subf(5, 5, 0)                                 # |k| (as 80125238)
    a.label("kpos")
    a.cmpwi(5, PATH_LAST).ble("kin").li(5, PATH_LAST)
    a.label("kin")
    a.lha(0, G_LANDED, 31).cmpwi(0, 0).bne("m")                     # on the ground: B = his pickup point
    a.lfs(7, F_Y, 30).lfs(0, F_HEIGHT, 30).fadds(7, 7, 0)           # his head
    a.li(6, 1).addi(7, 31, PATH_STRIDE)
    a.label("e")                                                    # the first frame down at his height
    a.cmpwi(6, PATH_LAST).li(0, 12).bgt("why")                      # never: no spot
    a.lfs(1, G_PATH_Y, 7).fcmpo(1, 7).ble("bot")
    a.addi(6, 6, 1).addi(7, 7, PATH_STRIDE).b("e")
    a.label("bot")                                                  # then down to the bottom of that fall
    a.cmpwi(6, PATH_LAST).bge("land")
    a.lfs(1, G_PATH_Y, 7).lfs(2, G_PATH_Y + PATH_STRIDE, 7).fcmpo(2, 1).bge("land")
    a.addi(6, 6, 1).addi(7, 7, PATH_STRIDE).b("bot")
    a.label("land")
    a.cmpw(5, 6).bge("m").mr(5, 6)                                  # m = max(k, L)
    a.label("m")
    a.cmpwi(5, 1).bge("m1").li(5, 1)
    a.label("m1")
    a.sth(5, dbg.M_FRAME, 28)
    a.mulli(7, 5, PATH_STRIDE).add(7, 7, 31)
    a.lfs(1, G_PATH_X, 7).lfs(2, G_PATH_Z, 7)                       # B
    a.lfs(3, G_PATH_X - PATH_STRIDE, 7).fsubs(3, 1, 3)              # d = B - path[m-1]
    a.lfs(4, G_PATH_Z - PATH_STRIDE, 7).fsubs(4, 2, 4)
    a.fmuls(5, 3, 3).fmadds(5, 4, 4, 5)                             # |d|^2
    a.lfs(0, C_TINY, 27).fcmpo(5, 0).ble("spot")                    # straight down / still: S = B
    rsqrt_newton(a, 6, 5, 0, 9)
    a.lfs(9, C_BACK, 27).fmuls(0, 31, 9).fmuls(6, 6, 0)             # s = ATK_BACK * reach / |d|
    a.fnmsubs(1, 3, 6, 1).fnmsubs(2, 4, 6, 2)                       # S = B - s*d
    a.label("spot")
    a.stfs(1, dbg.SPOT_X, 28).stfs(2, dbg.SPOT_Z, 28).fmr(10, 1).fmr(11, 2)
    a.lfs(0, F_X, 30).fsubs(1, 1, 0).lfs(0, F_Z, 30).fsubs(2, 2, 0)
    a.fmuls(1, 1, 1).fmadds(1, 2, 2, 1)
    sqrt(a, 1, 3, 0, 9)
    a.stfs(1, dbg.SPOT_D, 28)                                       # his distance to S
    a.li(3, 0).lfs(0, C_ATSPOT, 27).fcmpo(1, 0).ble("n")            # there: n = 0
    a.li(3, 999).lfs(0, F_RUN, 30).lfs(2, C_TINY, 27).fcmpo(0, 2).ble("n")   # no run speed: never
    a.fdivs(1, 1, 0).fctiwz(1, 1).stfd(1, 0x20, 1).lwz(3, 0x24, 1)  # n = frames to S at his top speed
    a.cmpwi(3, 999).ble("n").li(3, 999)
    a.label("n")
    a.stw(3, dbg.AUX0, 28)
    a.addi(9, 3, ATK_LAST).cmpwi(3, 0).bne("s").li(9, ATK_FIRST)    # he must be on S 3 frames before the connect
    a.label("s")
    a.bl("scan").stb(5, dbg.T_SPOT, 28)                             # t_S: the first connect from S he can be there for
    a.cmpwi(6, 0).li(0, 11).blt("why")                              # the ball never comes through S's reach
    a.cmpwi(5, 0).li(0, 15).blt("why")                              # only before he can get there: no plan
    a.cmpwi(3, 0).beq("there")
    a.li(0, 1).stb(0, dbg.PHASE, 28).li(0, 8).b("why")              # planned: moving to S (ROUTE targets it)
    a.label("there")
    # ---- TURN: face the ball (path[0], the ball now, as 80115CFC faces a standing chaser) ----
    a.li(0, 0).stw(0, dbg.AUX0, 28)
    a.lfs(1, G_PATH_Z, 31).lfs(0, F_Z, 30).fsubs(1, 1, 0)
    a.lfs(2, G_PATH_X, 31).lfs(0, F_X, 30).fsubs(2, 2, 0)
    a.bl(ATAN2).fmr(30, 1)                                          # f30 = the angle to the ball
    a.lfs(0, F_FACE, 30).fsubs(2, 30, 0)                            # facing error, wrapped into [-pi, pi]
    a.lfs(3, C_PI, 27).lfs(4, C_2PI, 27)
    a.fcmpo(2, 3).ble("w1").fsubs(2, 2, 4)
    a.label("w1")
    a.fneg(3, 3).fcmpo(2, 3).bge("w2").fadds(2, 2, 4)
    a.label("w2")
    a.lfs(0, ZERO, 2).fcmpo(2, 0).bge("w3").fneg(2, 2)
    a.label("w3")
    a.stfs(2, dbg.FACE, 28)
    a.li(3, 3).li(0, 10)                                            # set, waiting
    a.lfs(1, C_FACETOL, 27).fcmpo(2, 1).ble("set")
    a.stfs(30, F_FACE, 30).stfs(30, F_HEADING, 30)                  # turn: both fields, as 8011D5F4 writes them
    a.lbz(0, dbg.FLAGS, 28).ori(0, 0, 4).stb(0, dbg.FLAGS, 28)
    a.li(3, 2).li(0, 9)                                             # turning
    a.label("set")
    a.stb(3, dbg.PHASE, 28)
    a.label("why")
    a.stb(0, dbg.REASON, 28)
    # ---- ATTACK: t = the first connect from where he stands now (the press freezes him there) ----
    a.lfs(10, F_X, 30).lfs(11, F_Z, 30).li(9, ATK_FIRST).bl("scan").stb(6, dbg.T, 28)
    a.lbz(3, dbg.PHASE, 28)
    a.cmpwi(6, 0).blt("miss")
    a.cmpwi(6, ATK_LAST).ble("press")                               # inside the sure live frames: now
    a.cmpwi(3, 0).bne("out")                                        # planned: wait (no jump, no catch)
    a.lbz(0, F_CATCH, 30).cmpwi(0, 0).beq("normal")                 # not planned: his committed catch lands next
    a.lha(0, F_CATCH_LEFT, 30).cmpwi(0, 1).bgt("normal")            # frame and t is still in the swing: press now
    a.cmpwi(6, ATK_MUST).bgt("normal")
    a.label("press")
    a.li(0, 1).stb(0, AI_PASS, 29).stb(0, dbg.PRESS, 28)
    a.li(0, 4).stb(0, dbg.PHASE, 28).li(0, 0).stb(0, dbg.REASON, 28).b("out")
    a.label("miss")
    a.cmpwi(3, 0).bne("out")                                        # planned: not in reach from here yet
    a.b("normal")
    a.label("why7")
    a.li(0, 7)                                                      # no teammate within ATK_MATE_D (or toward home)
    a.label("why_n")
    a.stb(0, dbg.REASON, 28)
    a.label("normal")                                               # the normal play: fly ball -> the peak jump;
    a.li(0, 2).stb(0, dbg.JUMP, 28)
    a.lha(0, G_LANDED, 31).cmpwi(0, 0).bne("out")                   # ground ball / liner -> nothing (never the
    a.lfs(1, G_HEIGHT, 31).lfs(0, LINER_HEIGHT, 2).fcmpo(1, 0).ble("out")   # stock roll's ball-blind action)
    a.lwz(12, 0, 30).lwz(12, 0x3C, 12).mtctr(12).mr(3, 30).bctrl()  # fielding ability
    a.mr(4, 27).cmpwi(3, 2).bne("t0").addi(4, 4, 8)                 # Super Jump: row 1
    a.label("t0")
    a.lwz(5, 0, 4).lfs(2, 4, 4).lfs(0, F_HEIGHT, 30).fadds(2, 2, 0)  # r5 = LEAD, f2 = reach at the peak
    a.mr(6, 5)                                                      # i = LEAD (path[0] is the ball now)
    a.cmpwi(6, PATH_LAST).ble("in").li(6, PATH_LAST)
    a.label("in")
    a.mulli(7, 6, PATH_STRIDE).add(7, 7, 31)
    a.lfs(5, C_LEADF, 4)                                            # f5 = LEAD (float, the same row)
    a.lfs(3, F_SPEED, 30).fmuls(5, 5, 3)                            # f5 = his run in LEAD frames
    a.lfs(3, F_DIRX, 30).lfs(4, F_X, 30).fmadds(3, 3, 5, 4)         # where he will be then
    a.lfs(4, G_PATH_X, 7).fsubs(3, 4, 3)
    a.lfs(4, F_DIRZ, 30).lfs(6, F_Z, 30).fmadds(4, 4, 5, 6)
    a.lfs(6, G_PATH_Z, 7).fsubs(4, 6, 4)
    a.fmuls(3, 3, 3).fmadds(3, 4, 4, 3)                             # d^2 to the ball at i
    a.stfs(3, dbg.JUMP_D, 28)
    a.li(0, 4).stb(0, dbg.JUMP, 28)                                 # (the crossing first: path[i] is where the
    a.lfs(1, G_PATH_Y, 7).fcmpo(1, 2).bgt("out")                    # ball is at the peak only on the crossing
    a.li(0, 5).stb(0, dbg.JUMP, 28)                                 # frame; Nick's 11:59 dump: "out of reach" 4.7 m
    a.lfs(1, G_PATH_Y - JUMP_LATE * PATH_STRIDE, 7).fcmpo(1, 2).ble("out")   # while it was still coming down on him;
                                                                    # crossed more than JUMP_LATE frames ago: too late)
    a.lfs(4, F_HREACH, 30).lfs(0, C_HALF, 27).fmuls(4, 4, 0).fmuls(4, 4, 4)   # (half his standing catch reach)^2
    a.li(0, 3).stb(0, dbg.JUMP, 28)
    a.fcmpo(3, 4).bgt("out")                                        # the ball out of his reach at the peak
    a.li(0, 1).stb(0, dbg.JUMP, 28)
    do_jump(a)                                                      # crossed between i-1 and i: now
    a.label("out")
    a.b(OUT)
    # scan(f10 = x, f11 = z, r9 = start) -> r6 = the first path frame t in [ATK_FIRST, ATK_SCAN] that passes
    # FUN_8011F2B0's test from (x, z) with his feet / head / reach (ball within reach on the ground, y in
    # [F.y - r_ball, F.y + F+0x20]), r5 = the first such t >= start; -1 none. BEST_D / BEST_Y = the closest ground
    # pass over the whole window and its height. Leaf; keeps r3.
    a.label("scan")
    a.fmuls(3, 31, 31)                                              # reach^2
    a.lfs(4, F_Y, 30).lfs(0, G_BALL_R, 31).fsubs(5, 4, 0).lfs(6, F_HEIGHT, 30).fadds(6, 4, 6)   # y window
    a.lfs(12, C_BIG, 27).fmr(13, 12)
    a.li(6, -1).li(5, -1).li(8, ATK_FIRST).addi(7, 31, ATK_FIRST * PATH_STRIDE)
    a.label("sc")
    a.cmpwi(8, ATK_SCAN).bgt("scd")
    a.lfs(1, G_PATH_X, 7).fsubs(1, 1, 10).lfs(2, G_PATH_Z, 7).fsubs(2, 2, 11)
    a.fmuls(1, 1, 1).fmadds(1, 2, 2, 1).lfs(2, G_PATH_Y, 7)         # d^2, y
    a.fcmpo(1, 12).bge("scb").fmr(12, 1).fmr(13, 2)
    a.label("scb")
    a.cmpwi(5, 0).bge("scn")
    a.fcmpo(2, 5).blt("scn").fcmpo(2, 6).bgt("scn").fcmpo(1, 3).bgt("scn")
    a.cmpwi(6, 0).bge("sc2").mr(6, 8)
    a.label("sc2")
    a.cmpw(8, 9).blt("scn").mr(5, 8)
    a.label("scn")
    a.addi(8, 8, 1).addi(7, 7, PATH_STRIDE).b("sc")
    a.label("scd")
    sqrt(a, 12, 1, 0, 9)
    a.stfs(12, dbg.BEST_D, 28).stfs(13, dbg.BEST_Y, 28).blr()
    a.label("stock")
    a.word(DECIDE_ORIG)
    a.b(DECIDE_HOOK + 4)
    return a


def pow_pending(a, no, tag):
    """Branch to `no` with r0 = POW_PENDING while a POW is pending (above): the active item is the POW in flight
    (state 1), or the active batting slot holds a POW not used yet. Clobbers r0, r3, cr0."""
    a.lwz(3, ITEMS, 13).cmpwi(3, 0).beq(f"{tag}_ok")
    a.lwz(0, 0x394, 3).cmpwi(0, POW_ID).bne(f"{tag}_held")
    a.lbz(0, POW_POOL + POW_STATE, 3).cmpwi(0, 1).li(0, POW_PENDING).beq(no)        # in flight
    a.label(f"{tag}_held")
    for k in range(SLOT_N):
        e = SLOTS + k * SLOT_SIZE
        a.lwz(0, e, 3).cmpwi(0, POW_ID).bne(f"{tag}_n{k}")
        a.lbz(0, e + SLOT_ACTIVE, 3).cmpwi(0, 0).beq(f"{tag}_n{k}")
        a.lbz(0, e + SLOT_USED, 3).cmpwi(0, 0).li(0, POW_PENDING).beq(no)          # held, not used
        a.label(f"{tag}_n{k}")
    a.label(f"{tag}_ok")


def mate_unable(a, no, tag):
    """r3 = a teammate id (801148F4's result). Branch to `no` with r0 = MATE_UNABLE when he can't act: no fielder
    object for the id (FIELDERS order, as stock), airborne (+0x22E) or busy (BUSY 8012BA58, a leaf: r0 / r3 only).
    Clobbers r0, r3-r5, cr0, LR (the caller's frame must hold it)."""
    a.clrlwi(4, 3, 24).slwi(4, 4, 2)
    for t in FIELDERS:
        a.lis(5, ha(t)).addi(5, 5, lo(t)).lwzx(5, 5, 4).cmpwi(5, 0).bne(f"{tag}_got")
    a.li(0, MATE_UNABLE).b(no)
    a.label(f"{tag}_got")
    a.lbz(0, F_AIR, 5).cmpwi(0, 0).li(0, MATE_UNABLE).bne(no)
    a.mr(3, 5).bl(BUSY).cmpwi(3, 0).li(0, MATE_UNABLE).bne(no)


def toward_home(a, fr, kreg, no, tag):
    """r3 = the nearest teammate's id (kept), f1 = his distance. Falls through when he is within ATK_HOME_D (C_HOMED)
    and the pass from F (register `fr`) to him heads within ATK_HOME_DEG of home plate (0, 0): (M - F) . (H - F) > 0 and its square >= cos^2 * |M - F|^2 * |H - F|^2
    (C_HOME2 at the CONST base in `kreg`); else (or no fielder object for him) branch to `no`. Clobbers r4, r5,
    f0, f2-f6, cr0."""
    a.lfs(0, C_HOMED, kreg).fcmpo(1, 0).bgt(no)                                                   # past 50 m
    a.clrlwi(4, 3, 24).slwi(4, 4, 2)
    for t in FIELDERS:
        a.lis(5, ha(t)).addi(5, 5, lo(t)).lwzx(5, 5, 4).cmpwi(5, 0).bne(f"{tag}_got")
    a.b(no)
    a.label(f"{tag}_got")
    a.lfs(2, F_X, 5).lfs(0, F_X, fr).fsubs(2, 2, 0).lfs(3, F_Z, 5).lfs(0, F_Z, fr).fsubs(3, 3, 0)   # M - F
    a.lfs(4, F_X, fr).fneg(4, 4).lfs(5, F_Z, fr).fneg(5, 5)                                        # H - F
    a.fmuls(6, 2, 4).fmadds(6, 3, 5, 6)
    a.lfs(0, ZERO, 2).fcmpo(6, 0).ble(no)                                                          # away from home
    a.fmuls(6, 6, 6).fmuls(2, 2, 2).fmadds(2, 3, 3, 2).fmuls(4, 4, 4).fmadds(4, 5, 5, 4)
    a.fmuls(2, 2, 4).lfs(0, C_HOME2, kreg).fmuls(2, 2, 0).fcmpo(6, 2).blt(no)


def attack_ready(a, fr, no, cbase):
    """Branch to `no` unless F (register `fr`) is a level 6 CPU chaser with the attack available: level gate, level
    byte 0, the chaser (ai+0x2D8), ai+0x36C clear, chemistry on (80131AA4), the nearest teammate within ATK_MATE_D and
    able to act (mate_unable). Uses 0x8(r1) (the caller's scratch) for the teammate distance. Clobbers r0, r3-r12,
    f0-f13, cr0; the caller's frame must hold LR."""
    gate6(a, no)
    a.lbz(0, F_LEVEL, fr).cmpwi(0, 0).bne(no)
    for off in DEFENSE:                                             # the defense object
        a.lwz(12, off, 13).cmpwi(12, 0).bne("ar_def")
    a.b(no)
    a.label("ar_def")
    a.lha(0, AI_CHASER, 12).lbz(4, F_ID, fr).cmpw(0, 4).bne(no)
    a.lbz(0, AI_ATK_OFF, 12).cmpwi(0, 0).bne(no)
    pow_pending(a, no, "ar_pw")
    a.bl(CHEM_ON).cmpwi(3, 0).beq(no)
    a.mr(3, fr).addi(4, 1, 8).bl(NEAREST_MATE)                     # r3 = his id (kept for mate_unable)
    if _mates()[0] == _mates()[1] == _mates()[2]:
        a.load_addr(5, cbase)
    else:                                                           # level 5's own
        level5.pick_addr(a, 5, cbase + C_MATE4 - C_MATE, cbase + C_MATE5 - C_MATE, cbase)
    a.lfs(0, C_MATE, 5)
    a.lfs(1, 8, 1).fcmpo(1, 0).ble("ar_near")
    a.load_addr(6, cbase)
    toward_home(a, fr, 6, no, "ar_th")                             # past ATK_MATE_D: only a pass toward home plate
    a.label("ar_near")
    mate_unable(a, no, "ar_mu")


def catch_stub(at, cbase):
    """FUN_80121520 (the run-catch predictor, 2..12 frames ahead) at 0x8012179C: r28 = F, r29 = the catch frame i,
    f31 = |B - F| (B = the ball at path frame i), f27 = f31 - the reach 0x80625B60[F+0x221], f30 = his run speed (with
    the slot multiplier). Stock: f1 = f27 / f31, so he glides (80124F10: (spot - F) / i per frame) to a spot 0.95-1.4
    short of the ball, and the ball passes that far from his body: the attack (body radius + ball radius) can't reach
    it. Level 6, attack available (attack_ready): f1 = 1.0, the spot on the ball's path, when the whole run passes the
    predictor's own time test ((int)(f31 / (f30 * 1.1)) + 1 <= i, as 0x80121740..60 does for f27); else stock."""
    a = Asm(at)
    attack_ready(a, 28, "stock", cbase)
    a.lbz(0, MODE, 13).mulli(0, 0, 0xA0).load_addr(3, RUN_SLACK).add(3, 3, 0).lfs(0, 0, 3)
    a.fmuls(0, 30, 0).fdivs(0, 31, 0).fctiwz(0, 0).stfd(0, 8, 1).lwz(3, 0xC, 1)
    a.addi(0, 3, 1).cmpw(0, 29).bgt("stock")                        # can't get to the ball point by frame i
    a.load_addr(3, cbase).lfs(1, C_ONE, 3)
    a.b(CATCH_HOOK + 4)
    a.label("stock")
    a.word(CATCH_ORIG)
    a.b(CATCH_HOOK + 4)
    return a


def avoid_body(a, cbase):
    """AVOID(r3 = F, r4 = the mover's sp): may rewrite the target at 0xC(sp) / 0x8(sp). Own frame."""
    a.stwu(1, -0x20, 1).mflr(0).stw(0, 0x24, 1).stw(31, 0x1C, 1).stw(30, 0x18, 1)
    a.mr(31, 3).mr(30, 4)
    gate6(a, "ret")
    a.lbz(0, F_LEVEL, 31).cmpwi(0, 0).bne("ret")
    a.lwz(3, ITEMS, 13).cmpwi(3, 0).beq("ret")
    for i, off in enumerate(DEFENSE):                               # the defense object
        a.lwz(3, off, 13).cmpwi(3, 0).bne("def")
    a.b("ret")
    a.label("def")
    a.lha(0, AI_CHASER, 3).lbz(4, F_ID, 31).cmpw(0, 4).bne("ret")   # the chaser only
    a.mr(3, 31).load_addr(4, cbase + C_ITEM).bl(ITEM_NEAR)
    a.load_addr(5, cbase).lfs(0, C_RANGE, 5).fcmpo(1, 0).bgt("ret")
    a.lwz(6, C_ITEM, 5).cmpwi(6, 0).beq("ret")
    a.lfs(2, F_X, 31).lfs(3, F_Z, 31)
    a.lfs(4, 4, 6).fsubs(4, 4, 2).lfs(5, 0xC, 6).fsubs(5, 5, 3)     # d = item - F
    a.lfs(6, 0xC, 30).fsubs(6, 6, 2).lfs(7, 8, 30).fsubs(7, 7, 3)   # u = target - F
    a.fmuls(8, 4, 6).fmadds(8, 5, 7, 8)                             # d.u
    a.fmuls(9, 6, 6).fmadds(9, 7, 7, 9)                             # |u|^2
    a.lfs(0, ZERO, 2).fcmpo(8, 0).ble("ret")                        # behind him
    a.fcmpo(8, 9).bge("ret")                                        # past the target
    a.fmuls(10, 4, 7).fnmsubs(10, 5, 6, 10)                         # c = d x u
    a.fmuls(11, 10, 10).lfs(0, C_CLEAR2, 5).fmuls(12, 0, 9).fcmpo(11, 12).bge("ret")   # off the line
    a.frsqrte(12, 9)                                                # 1/|u|, one Newton step
    a.fmuls(0, 12, 12).fmuls(0, 0, 9).lfs(13, C_HALF, 5).fmuls(0, 0, 13)
    a.lfs(13, C_3HALF, 5).fsubs(0, 13, 0).fmuls(12, 12, 0)
    a.lfs(0, C_OFFSET, 5).fmuls(12, 12, 0)                          # s = OFFSET / |u|
    a.lfs(0, ZERO, 2).fcmpo(10, 0).ble("side").fneg(12, 12)         # item on the +n side: go to -n
    a.label("side")
    a.lfs(0, 4, 6).fmadds(0, 12, 7, 0).stfs(0, 0xC, 30)             # W.x = item.x + s*u.z
    a.lfs(0, 0xC, 6).fnmsubs(0, 12, 6, 0).stfs(0, 8, 30)            # W.z = item.z - s*u.x
    a.label("ret")
    a.lwz(0, 0x24, 1).lwz(31, 0x1C, 1).lwz(30, 0x18, 1).mtlr(0).addi(1, 1, 0x20).blr()


# STADIUM HAZARDS (Nick, 2026-09-29: "can we just do the cheep cheeps, the train, and the ice in peach's?"): after
# AVOID, each level 5 / 6 CPU fielder on the two route movers steers around the loaded stadium's hazards the same way
# (a waypoint beside the first one on his line, HZ_MARGIN outside its circle + his radius +0x1C). The stadium: its
# gimmick controller ctrl = *(*(r13-0x163C) + 0x44) by its vtable; nothing while ctrl+8 (u8, hidden) is set. [C]
# - Peach Ice Garden (CBbGimmickCtrlPeach 0x806A4BB0): 5 ice blocks, radius 2.2, at the base spots (table 0x8070B768:
#   x, field z = (20, 50) (-20, 50) (35, 75) (-35, 75) (0, 95)) + the shared sway ctrl+0x50 (f32, +-10 m over 600
#   frames) on x; only intact ones (u8 (*(ctrl+0x2C))[i] == 0). A touch freezes him 120 frames (FUN_80119140).
# - Daisy Cruiser at night (CBbGimmickCtrlDaisy 0x806A3264, ctrl+0xC != 0): Cheep Cheeps fish = *(ctrl+0x34+4i),
#   i < u8 ctrl+0x44 (4), flopping (u8 fish+0x10 == 1): each hops within 3.0 of its home (fish+0x48, field z =
#   -(fish+0x50)); the circle there, 3.0 + its radius 0.8. A touch knocks him down 40 frames.
# - Yoshi Park (CBbGimmickCtrlYoshi 0x806A5790): the train = *(ctrl+0x14) (state u8 +0x10 1..3 = on the field) and its
#   cars *(ctrl+0x18)[i], i < u16 ctrl+0x1C: position (+0, field z = -(+8)), velocity per frame (engine +0x24 / +0x2C,
#   cars +0x30 / +0x38; z negated), radius 5.0 / 4.0. Moving, so each is tested where it will be when he gets level
#   with it (his run to that point at max(+0xE4, +0xEC)): a train that will have passed is no obstacle.
# - Wario City (CBbGimmickCtrlWario 0x806A515C; Nick, 2026-09-29: "avoid the fountain when it is up"): fountains
#   *(*(ctrl+0x18) + 4i), i < u16 ctrl+0x10 (5): each while spouting (u8 +0x10: 2 start, 3 rising, 4 up, 5 falling; 8
#   the scripted countdown just before 2), a circle radius 3.9 (file 0x47) at (+0, field z = -(+8)). Its knockdown
#   (FUN_80301A50 via FUN_802DCDCC) tests exactly that circle in states 3-5. [C]
# An obstacle whose circle holds his target is skipped (he has to go there: the ball first). Cheep Cheeps' other
# blocker (ctrl+0x30) and Peach's frozen teammates are not included.
# THE SHARED MOVER (Nick's 12:56 ice dump: the LF ran straight into a block chasing a grounder; his ROUTE row stopped
# at frame 64, so that chase went through neither route mover): FUN_80112BC4 (every AI state's walk to F+0x38 / +0x40)
# steps along the heading F+0xF8, then re-aims it at the target (0x80113318: atan2(target - the new spot)). The hook
# there runs HAZARD on the target from the new spot and aims at the waypoint instead; F+0x38 / +0x40 stay (the states
# test arrival against them). While he is steered, F+0x114 (the distance left: under one step it snaps him onto the
# target, 801131D4) is set to the true distance from the new spot, so the detour never ends in a snap through the
# block. A fielder the route movers steered (their entries set H_ROUTED[id]) is skipped once: they write the waypoint
# into F+0x38 and re-aim every frame themselves. [C]
PEACH_VT, DAISY_VT, YOSHI_VT, WARIO_VT = 0x806A4BB0, 0x806A3264, 0x806A5790, 0x806A515C
ICE_BASE = ((20.0, 50.0), (-20.0, 50.0), (35.0, 75.0), (-35.0, 75.0), (0.0, 95.0))
R_ICE, R_FISH, R_ENGINE, R_CAR, HZ_MARGIN, HZ_MINV, R_FOUNTAIN = 2.2, 3.8, 5.0, 4.0, 1.0, 0.05, 3.9
HZ_MAX = 10
H_N, H_OBS, H_OSIZE = 0, 4, 20                         # u32 count; obstacles (x, z, r, vx, vz)
H_ICE = H_OBS + HZ_MAX * H_OSIZE                       # f32 x, z per ice block
H_K = H_ICE + 8 * len(ICE_BASE)                        # f32 R_ICE, R_FISH, R_ENGINE, R_CAR, MARGIN, MINV, 0.5, 1.5, 0, big,
                                                        # R_FOUNTAIN
H_BS, H_BX, H_BZ, H_BCL, H_BC = (H_K + 44 + 4 * i for i in range(5))   # the best: s, x, z, clearance, cross
H_ROUTED = H_BC + 4                                     # u8 per fielder id 0-8: the route movers steered him
H_SIZE = H_ROUTED + 12
HZ = None                                               # the block (apply)


def _hz_add(a, fx, fz, fr, fvx, fvz, tag):
    """Append (fx, fz, fr, fvx, fvz) to the obstacle list (r29 = HZ), unless it is full. Uses r0, r9, r10."""
    a.lwz(9, H_N, 29).cmplwi(9, HZ_MAX).bge(f"hz_full_{tag}")
    a.mulli(10, 9, H_OSIZE).add(10, 10, 29)
    a.stfs(fx, H_OBS, 10).stfs(fz, H_OBS + 4, 10).stfs(fr, H_OBS + 8, 10).stfs(fvx, H_OBS + 12, 10)
    a.stfs(fvz, H_OBS + 16, 10)
    a.addi(9, 9, 1).stw(9, H_N, 29)
    a.label(f"hz_full_{tag}")


def hazard_body(a):
    """HAZARD(r3 = F, r4 = the mover's sp): may rewrite the target at 0xC(sp) / 0x8(sp). Own frame (docstring)."""
    K = lambda i: H_K + 4 * i                               # noqa: E731
    a.label("hazard")
    a.stwu(1, -0x30, 1).mflr(0).stw(0, 0x34, 1)
    a.stw(31, 0x2C, 1).stw(30, 0x28, 1).stw(29, 0x24, 1).stw(28, 0x20, 1).stw(27, 0x1C, 1)
    a.mr(31, 3).mr(30, 4)
    gate6(a, "hz_ret", reg=12)
    a.lbz(0, F_LEVEL, 31).cmpwi(0, 0).bne("hz_ret")
    a.load_addr(29, HZ).li(0, 0).stw(0, H_N, 29)
    a.lwz(3, -0x163C, 13).cmpwi(3, 0).beq("hz_ret")
    a.lwz(28, 0x44, 3).cmpwi(28, 0).beq("hz_ret")
    a.lbz(0, 8, 28).cmpwi(0, 0).bne("hz_ret")
    a.lwz(3, 0, 28)
    a.lfs(5, K(8), 29)                                      # f5 = 0.0 (a still obstacle's velocity)
    # ---- Peach: the ice blocks
    a.load_addr(4, PEACH_VT).cmpw(3, 4).bne("hz_daisy")
    a.lwz(27, 0x2C, 28).cmpwi(27, 0).beq("hz_go")
    a.lfs(1, 0x50, 28).li(6, 0)
    a.label("hz_ice")
    a.lbzx(0, 27, 6).cmpwi(0, 0).bne("hz_ice_n")
    a.slwi(7, 6, 3).add(7, 7, 29)
    a.lfs(2, H_ICE, 7).fadds(2, 2, 1).lfs(3, H_ICE + 4, 7).lfs(4, K(0), 29)
    _hz_add(a, 2, 3, 4, 5, 5, "ice")
    a.label("hz_ice_n")
    a.addi(6, 6, 1).cmpwi(6, len(ICE_BASE)).blt("hz_ice")
    a.b("hz_go")
    # ---- Daisy (night): the Cheep Cheeps' homes
    a.label("hz_daisy")
    a.load_addr(4, DAISY_VT).cmpw(3, 4).bne("hz_yoshi")
    a.lwz(0, 0xC, 28).cmpwi(0, 0).beq("hz_go")
    a.lbz(27, 0x44, 28).cmplwi(27, 4).ble("hz_fn").li(27, 4)
    a.label("hz_fn")
    a.li(6, 0)
    a.label("hz_fish")
    a.cmpw(6, 27).bge("hz_go")
    a.slwi(7, 6, 2).add(7, 7, 28).lwz(7, 0x34, 7).cmpwi(7, 0).beq("hz_fish_n")
    a.lbz(0, 0x10, 7).cmpwi(0, 1).bne("hz_fish_n")
    a.lfs(2, 0x48, 7).lfs(3, 0x50, 7).fneg(3, 3).lfs(4, K(1), 29)
    _hz_add(a, 2, 3, 4, 5, 5, "fish")
    a.label("hz_fish_n")
    a.addi(6, 6, 1).b("hz_fish")
    # ---- Yoshi: the train and its cars
    a.label("hz_yoshi")
    a.load_addr(4, YOSHI_VT).cmpw(3, 4).bne("hz_wario")
    a.lwz(7, 0x14, 28).cmpwi(7, 0).beq("hz_go")
    a.lbz(6, 0x10, 7).addi(6, 6, -1).cmplwi(6, 2).bgt("hz_go")    # states 1..3: on the field
    a.lfs(2, 0, 7).lfs(3, 8, 7).fneg(3, 3).lfs(4, K(2), 29)
    a.lfs(6, 0x24, 7).lfs(8, 0x2C, 7).fneg(8, 8)
    _hz_add(a, 2, 3, 4, 6, 8, "eng")
    a.lwz(27, 0x18, 28).cmpwi(27, 0).beq("hz_go")
    a.lhz(6, 0x1C, 28).cmplwi(6, 4).ble("hz_cn").li(6, 4)
    a.label("hz_cn")
    a.mtctr(6).cmpwi(6, 0).beq("hz_go")
    a.label("hz_car")
    a.lwz(7, 0, 27).cmpwi(7, 0).beq("hz_car_n")
    a.lfs(2, 0, 7).lfs(3, 8, 7).fneg(3, 3).lfs(4, K(3), 29)
    a.lfs(6, 0x30, 7).lfs(8, 0x38, 7).fneg(8, 8)
    _hz_add(a, 2, 3, 4, 6, 8, "car")
    a.label("hz_car_n")
    a.addi(27, 27, 4)
    a._emit(lambda pc: bc(pc, a.labels["hz_car"], 16, 0))       # bdnz
    a.b("hz_go")
    # ---- Wario City: the fountains while spouting
    a.label("hz_wario")
    a.load_addr(4, WARIO_VT).cmpw(3, 4).bne("hz_ret")
    a.lwz(27, 0x18, 28).cmpwi(27, 0).beq("hz_go")
    a.lhz(6, 0x10, 28).cmplwi(6, 5).ble("hz_wn").li(6, 5)
    a.label("hz_wn")
    a.mtctr(6).cmpwi(6, 0).beq("hz_go")
    a.label("hz_ftn")
    a.lwz(7, 0, 27).cmpwi(7, 0).beq("hz_ftn_n")
    a.lbz(6, 0x10, 7).cmpwi(6, 8).beq("hz_ftn_on")
    a.addi(6, 6, -2).cmplwi(6, 3).bgt("hz_ftn_n")                   # states 2..5
    a.label("hz_ftn_on")
    a.lfs(2, 0, 7).lfs(3, 8, 7).fneg(3, 3).lfs(4, H_K + 40, 29)
    _hz_add(a, 2, 3, 4, 5, 5, "ftn")
    a.label("hz_ftn_n")
    a.addi(27, 27, 4)
    a._emit(lambda pc: bc(pc, a.labels["hz_ftn"], 16, 0))       # bdnz
    # ---- the first obstacle on his line (the AVOID geometry, time-aligned for moving ones)
    a.label("hz_go")
    a.lwz(27, H_N, 29).cmpwi(27, 0).beq("hz_ret")
    a.lfs(10, F_X, 31).lfs(11, F_Z, 31)
    a.lfs(6, 0xC, 30).fsubs(6, 6, 10).lfs(7, 8, 30).fsubs(7, 7, 11)      # u = target - F
    a.fmuls(8, 6, 6).fmadds(8, 7, 7, 8)                                # |u|^2
    a.lfs(0, K(5), 29).fcmpo(8, 0).blt("hz_ret")                       # (at the target)
    a.frsqrte(9, 8)                                                    # 1/|u|, one Newton step
    a.fmuls(0, 9, 9).fmuls(0, 0, 8).lfs(1, K(6), 29).fmuls(0, 0, 1)
    a.lfs(1, K(7), 29).fsubs(0, 1, 0).fmuls(9, 9, 0)
    a.lfs(12, 0xE4, 31).lfs(0, 0xEC, 31).fcmpo(12, 0).bge("hz_v").fmr(12, 0)
    a.label("hz_v")
    a.lfs(0, K(5), 29).fcmpo(12, 0).bge("hz_v2").fmr(12, 0)            # his run speed, at least MINV
    a.label("hz_v2")
    a.lfs(0, K(9), 29).stfs(0, H_BS, 29)                               # best s = big
    a.li(5, 0).addi(28, 29, H_OBS)
    a.label("hz_o")
    a.cmpw(5, 27).bge("hz_pick")
    a.lfs(1, 0, 28).fsubs(1, 1, 10).lfs(2, 4, 28).fsubs(2, 2, 11)      # d = o - F
    a.fmuls(3, 1, 6).fmadds(3, 2, 7, 3)                                # s = d.u
    a.fmuls(3, 3, 9).fdivs(3, 3, 12)                                   # t: frames till he is level with it
    a.lfs(4, 12, 28).fmadds(1, 4, 3, 1).lfs(4, 16, 28).fmadds(2, 4, 3, 2)   # d' = d + v_o t
    a.fmuls(3, 1, 6).fmadds(3, 2, 7, 3)                                # s' = d'.u
    a.lfs(0, K(8), 29).fcmpo(3, 0).ble("hz_on")                        # behind him
    a.fcmpo(3, 8).bge("hz_on")                                         # past the target
    a.lfs(4, 8, 28).lfs(0, 0x1C, 31).fadds(4, 4, 0)                    # r + his radius
    a.fsubs(13, 6, 1).fmuls(13, 13, 13)                                # |t - o'|^2 = |u - d'|^2
    a.fsubs(0, 7, 2).fmadds(13, 0, 0, 13)
    a.fmuls(0, 4, 4).fcmpo(13, 0).blt("hz_on")                         # the target inside it: skip
    a.lfs(0, K(4), 29).fadds(4, 4, 0)                                  # clearance = r + his radius + MARGIN
    a.fmuls(13, 1, 7).fnmsubs(13, 2, 6, 13)                            # c = d' x u
    a.stfs(12, 0x8, 1)                                                 # (keep his speed)
    a.fmuls(0, 13, 13).fmuls(12, 4, 4).fmuls(12, 12, 8).fcmpo(0, 12)   # c^2 vs clear^2 |u|^2
    a.lfs(12, 0x8, 1)
    a.bge("hz_on")                                                     # off the line
    a.lfs(0, H_BS, 29).fcmpo(3, 0).bge("hz_on")                        # not the first on his line
    a.stfs(3, H_BS, 29).stfs(4, H_BCL, 29).stfs(13, H_BC, 29)
    a.fadds(0, 1, 10).stfs(0, H_BX, 29).fadds(0, 2, 11).stfs(0, H_BZ, 29)   # o' = F + d'
    a.label("hz_on")
    a.addi(5, 5, 1).addi(28, 28, H_OSIZE).b("hz_o")
    a.label("hz_pick")
    a.lfs(1, H_BS, 29).lfs(0, K(9), 29).fcmpo(1, 0).bge("hz_ret")    # nothing on his line
    a.lfs(4, H_BCL, 29).fmuls(4, 4, 9)                                 # s = clearance / |u|
    a.lfs(13, H_BC, 29).lfs(0, K(8), 29).fcmpo(13, 0).ble("hz_side").fneg(4, 4)   # on the +n side: go to -n
    a.label("hz_side")
    a.lfs(0, H_BX, 29).fmadds(0, 4, 7, 0).stfs(0, 0xC, 30)            # W.x = o.x + s u.z
    a.lfs(0, H_BZ, 29).fnmsubs(0, 4, 6, 0).stfs(0, 8, 30)             # W.z = o.z - s u.x
    a.label("hz_ret")
    a.lwz(27, 0x1C, 1).lwz(28, 0x20, 1).lwz(29, 0x24, 1).lwz(30, 0x28, 1).lwz(31, 0x2C, 1)
    a.lwz(0, 0x34, 1).mtlr(0).addi(1, 1, 0x30).blr()


def hazard_block():
    """HZ's initial bytes: the ice base spots and the constants."""
    blob = bytearray(H_SIZE)
    for i, (x, z) in enumerate(ICE_BASE):
        struct.pack_into(">2f", blob, H_ICE + 8 * i, x, z)
    struct.pack_into(">11f", blob, H_K, R_ICE, R_FISH, R_ENGINE, R_CAR, HZ_MARGIN, HZ_MINV, 0.5, 1.5, 0.0, 1e30,
                     R_FOUNTAIN)
    return bytes(blob)


def planned(a, fr, no):
    """Branch to `no` unless the attack is planned for F (register `fr`) this frame: level gate, level byte 0, and the
    debug block says FRAME == now, CHASER == F+0x21C,. Leaves the block base in r12. Clobbers r0,
    r11, r12, cr0."""
    gate6(a, no)
    a.lbz(0, F_LEVEL, fr).cmpwi(0, 0).bne(no)
    a.load_addr(12, dbg.ADDR)
    a.lwz(11, TICK, 13).lha(11, 2, 11).lha(0, dbg.FRAME, 12).cmpw(0, 11).bne(no)
    a.lbz(0, dbg.CHASER, 12).lbz(11, F_ID, fr).cmpw(0, 11).bne(no)


def plan_body(a):
    """PLAN(r3 = F, r4 = the mover's sp), leaf: while the attack is planned for him and not yet pressed (PHASE 1-3),
    the target at 0xC(sp) / 0x8(sp) becomes the attack spot S (SPOT_X / SPOT_Z, from DECIDE earlier this frame). The
    mover (80125238 after the hook -> 80112BC4) runs at his speed along the heading to it and, when the rest is under
    one step, steps exactly onto it and stops (speed +0xE4 = 0, +0x114 = 0) [C]: no overshoot, and while S stays put
    he stands. A committed catch (F+0x2AC; 80112BC4 would glide him with 80124F10 instead) is cancelled the way
    8011D5F4 / 80112BC4 cancel it on a press (FLAGS bit 1), except when that cancel would also call 800AEC4C (+0x2C7
    5 / 7 or +0x2C1 set) or the catch lands next frame (+0x2A4 <= 1): then REASON 14, the catch goes on."""
    planned(a, 3, "pl_ret")
    a.lbz(11, dbg.PHASE, 12).addi(11, 11, -1).cmplwi(11, 2).bgt("pl_ret")    # PHASE 1..3
    a.lfs(0, dbg.SPOT_X, 12).stfs(0, 0xC, 4).lfs(0, dbg.SPOT_Z, 12).stfs(0, 8, 4)
    a.lbz(0, F_CATCH, 3).cmpwi(0, 0).beq("pl_ret")
    a.lbz(0, 0x2C7, 3).cmpwi(0, 5).beq("pl_keep").cmpwi(0, 7).beq("pl_keep")
    a.lbz(0, 0x2C1, 3).cmpwi(0, 0).bne("pl_keep")
    a.lha(0, F_CATCH_LEFT, 3).cmpwi(0, 1).ble("pl_keep")
    a.li(0, 0)
    for off in (F_CATCH, 0x253, 0x24D, 0x24A, 0x2B9, 0x2C7, 0x2C1, 0x2C3):
        a.stb(0, off, 3)
    a.sth(0, 0x1F8, 3).stw(0, 0xE4, 3)                              # speed 0.0
    a.lbz(0, dbg.FLAGS, 12).ori(0, 0, 2).stb(0, dbg.FLAGS, 12).blr()
    a.label("pl_keep")
    a.li(0, 14).stb(0, dbg.REASON, 12)
    a.label("pl_ret")
    a.blr()


def block_stub(at):
    """0x8011FCD4 in FUN_8011F748 (r27 = F; `or r3,r27,r27` before bl 80121050): while the attack is planned or
    pressed for him this frame (PHASE 1-4), skip the whole catch block: the standing catch 80121050, the run-catch
    80121520 (its glide 80124F10 would override the route) and the dive 801222D0 / 801225DC. Out through the
    function's epilogue 0x8011FE54 (FLAGS bit 0). Else stock."""
    a = Asm(at)
    if BLUR is not None:                                            # BOO BLUR: a MISS can't catch while hidden
        gate6(a, "b_plan", reg=11)
        a.lwz(11, GAME_PTR, 13).cmpwi(11, 0).beq("b_plan")
        a.lbz(0, G_HIDDEN, 11).cmpwi(0, 0).beq("b_plan")
        a.lbz(0, F_LEVEL, 27).cmpwi(0, 0).bne("b_plan")
        a.load_addr(11, BLUR).lbz(0, B_DRAWN, 11).cmpwi(0, 0).beq("b_plan")
        a.lbz(12, F_ID, 27).cmplwi(12, 8).bgt("b_plan")
        a.add(11, 11, 12).lbz(0, B_MISS, 11).cmpwi(0, 0).beq("b_plan")
        a.b(BLOCK_SKIP)
        a.label("b_plan")
    planned(a, 27, "stock")
    a.lbz(11, dbg.PHASE, 12).addi(11, 11, -1).cmplwi(11, 3).bgt("stock")   # PHASE 1..4
    a.lbz(0, dbg.FLAGS, 12).ori(0, 0, 1).stb(0, dbg.FLAGS, 12)
    a.b(BLOCK_SKIP)
    a.label("stock")
    a.word(BLOCK_ORIG)
    a.b(BLOCK_HOOK + 4)
    return a


def route_stubs(at, cbase):
    """Two entries (one per mover), then the shared AVOID body and PLAN (80125238's entry only: 80125F8C is the wall
    play). PLAN runs first, so AVOID's waypoint wins while an item is in the way. Returns (asm, [entries])."""
    a = Asm(at)
    entries = []
    for i, (hook, freg) in enumerate(ROUTE_HOOKS):
        entries.append(a.pc)
        if dbg.ROUTE is not None:                                   # record his stock target (defense_dbg.ROUTE)
            a.lbz(4, F_ID, freg).cmplwi(4, dbg.ROUTE_N - 1).bgt(f"rt_x{i}")
            a.load_addr(3, dbg.ROUTE).mulli(4, 4, dbg.ROUTE_SIZE).add(3, 3, 4)
            a.lwz(4, 0xC, 1).stw(4, 0, 3).lwz(4, 8, 1).stw(4, 4, 3)          # x, z (GPRs: no FPR touched)
            a.lwz(4, TICK, 13).cmpwi(4, 0).beq(f"rt_x{i}")
            a.lha(4, 2, 4).stw(4, 8, 3)
            a.label(f"rt_x{i}")
        if i == 0:                                                  # the chase (80125238): the attack spot first
            a.mr(3, freg).mr(4, 1).bl("plan")
        if BLUR is not None:
            a.mr(3, freg).mr(4, 1).bl("blur")                       # BOO BLUR: where he thinks the ball is
        a.mr(3, freg).mr(4, 1).bl("avoid")
        if HZ is not None:
            a.mr(3, freg).mr(4, 1).bl("hazard")                     # STADIUM HAZARDS (after items: an item wins)
            a.lbz(4, F_ID, freg).cmplwi(4, 8).bgt(f"rt_h{i}")       # (the shared mover: already steered)
            a.load_addr(3, HZ + H_ROUTED).li(0, 1).stbx(0, 3, 4)
            a.label(f"rt_h{i}")
        a.word(ROUTE_ORIG).b(hook + 4)
    if HZ is not None:
        entries.append(a.pc)
        mover_entry(a)
    if BLUR is not None:
        blur_body(a)
    if HZ is not None:
        hazard_body(a)
    a.label("avoid")
    avoid_body(a, cbase)
    a.label("plan")
    plan_body(a)
    return a, entries


def mover_entry(a):
    """THE SHARED MOVER's hook (0x80113318, FUN_80112BC4; docstring above): r30 = F, f4 / f3 = his new x / z (not yet
    stored), f1 / f0 = the target x / z. Out: f1 / f0 = the waypoint (or the target), then the stock fsubs."""
    K = lambda i: H_K + 4 * i                               # noqa: E731
    a.stwu(1, -0x40, 1).mflr(0).stw(0, 0x44, 1)
    a.stfs(4, 0x20, 1).stfs(3, 0x24, 1)
    a.stfs(1, 0x1C, 1).stfs(0, 0x18, 1)                             # the target, as a mover's sp (+0xC x, +8 z)
    a.stfs(1, 0x28, 1).stfs(0, 0x2C, 1)                             # (and kept)
    a.lbz(4, F_ID, 30).cmplwi(4, 8).bgt("mv_out")
    a.load_addr(5, HZ + H_ROUTED).lbzx(0, 5, 4).cmpwi(0, 0).beq("mv_go")
    a.li(0, 0).stbx(0, 5, 4).b("mv_out")                            # the route movers steered him: as is
    a.label("mv_go")
    a.stfs(4, F_X, 30).stfs(3, F_Z, 30)                             # (the stock stores, early: HAZARD from here)
    a.mr(3, 30).addi(4, 1, 0x10).bl("hazard")
    a.lfs(1, 0x1C, 1).lfs(2, 0x28, 1).fcmpo(1, 2).bne("mv_st")
    a.lfs(1, 0x18, 1).lfs(2, 0x2C, 1).fcmpo(1, 2).beq("mv_out")
    a.label("mv_st")                                                # steered: F+0x114 = |target - here|
    a.lfs(1, 0x28, 1).lfs(2, 0x20, 1).fsubs(1, 1, 2)
    a.lfs(2, 0x2C, 1).lfs(3, 0x24, 1).fsubs(2, 2, 3)
    a.fmuls(1, 1, 1).fmadds(1, 2, 2, 1)
    a.load_addr(5, HZ).lfs(0, K(5), 5).fcmpo(1, 0).blt("mv_out")
    a.frsqrte(2, 1)
    for _ in range(2):                                              # 1/sqrt, two Newton steps
        a.fmuls(0, 2, 2).fmuls(0, 0, 1).lfs(3, K(6), 5).fmuls(0, 0, 3)
        a.lfs(3, K(7), 5).fsubs(0, 3, 0).fmuls(2, 2, 0)
    a.fmuls(1, 1, 2).stfs(1, 0x114, 30)
    a.label("mv_out")
    a.lfs(1, 0x1C, 1).lfs(0, 0x18, 1).lfs(4, 0x20, 1).lfs(3, 0x24, 1)
    a.lwz(0, 0x44, 1).mtlr(0).addi(1, 1, 0x40)
    a.word(MOVER_ORIG).b(MOVER_HOOK + 4)


def boo_stub(at, hook=BOO_HOOK):
    """The Boo's (or the star's, hook STAR_HOOK) freeze call: skipped for level 6 CPU fielders."""
    a = Asm(at)
    gate6(a, "stock", reg=4)
    a.lis(4, ha(FIELDERS[0])).lwz(4, lo(FIELDERS[0]), 4).cmpwi(4, 0).bne("got")
    a.lis(4, ha(FIELDERS[1])).lwz(4, lo(FIELDERS[1]), 4).cmpwi(4, 0).bne("got")
    a.lis(4, ha(FIELDERS[2])).lwz(4, lo(FIELDERS[2]), 4).cmpwi(4, 0).beq("stock")
    a.label("got")
    a.lbz(0, F_LEVEL, 4).cmpwi(0, 0).bne("stock")
    if hook == BOO_HOOK and BLUR is not None:
        a.bl("draw")                                                # BOO BLUR: the first frame draws z
    a.b(hook + 4)                                                   # level 6 CPU fielders: no freeze
    a.label("stock")
    a.bl(FREEZE)
    a.b(hook + 4)
    if hook == BOO_HOOK and BLUR is not None:
        blur_draw(a)
    return a


def blur_draw(a):
    """BOO BLUR's draw (label "draw"; the Boo hook's site was a bl: LR and the volatile registers are free): once per
    hidden spell (B_DRAWN), 18 standard normals into B_Z (Irwin-Hall: BLUR_N uniforms each, minus BLUR_N / 2) and
    MISS[i] = |z_i| > K. The uniforms come from an xorshift32 (B_STATE) stirred once per draw by the game's rand
    (FUN_80165C14): the game's own generator, called 216 times in one frame, mixes in the frame counter and gave
    correlated values (kurtosis 8, 18% misses in the test)."""
    a.label("draw")
    a.load_addr(11, BLUR).lbz(0, B_DRAWN, 11).cmpwi(0, 0).bne("d_ret")
    a.stwu(1, -0x10, 1).mflr(0).stw(0, 0x14, 1)
    a.lwz(3, RNG, 13).li(4, 0x7FFF).bl(RAND)
    a.lwz(0, 0x14, 1).mtlr(0).addi(1, 1, 0x10)
    a.load_addr(11, BLUR).lwz(5, B_STATE, 11)
    a.word(x_form(5, 5, 3, 316))                                    # xor r5,r5,r3
    a.rlwinm(3, 3, 16, 0, 31).word(x_form(5, 5, 3, 316))          # and rotated
    a.lis(8, 0x9E37).ori(8, 8, 0x79B9).mullw(5, 5, 8)             # spread a small seed over all 32 bits
    a.cmpwi(5, 0).bne("d_seed").li(5, 1)
    a.label("d_seed")
    a.li(7, 8)                                                      # discard xorshift's first 8 outputs
    a.label("d_w")
    a.slwi(8, 5, 13).word(x_form(5, 5, 8, 316)).rlwinm(8, 5, 15, 17, 31).word(x_form(5, 5, 8, 316))
    a.slwi(8, 5, 5).word(x_form(5, 5, 8, 316))
    a.addi(7, 7, -1).cmpwi(7, 0).bne("d_w")
    a.li(6, 0)
    a.label("d_s")
    a.li(7, BLUR_N).lfs(0, B_ZERO, 11)
    a.label("d_u")
    a.slwi(8, 5, 13).word(x_form(5, 5, 8, 316))                    # x ^= x << 13
    a.rlwinm(8, 5, 15, 17, 31).word(x_form(5, 5, 8, 316))          # x ^= x >> 17
    a.slwi(8, 5, 5).word(x_form(5, 5, 8, 316))                     # x ^= x << 5
    a.rlwinm(8, 5, 23, 9, 31).lis(9, 0x3F80).word(x_form(8, 8, 9, 444))   # 1.mantissa: [1, 2)
    a.stw(8, B_SCR, 11).lfs(1, B_SCR, 11).fadds(0, 0, 1)
    a.addi(7, 7, -1).cmpwi(7, 0).bne("d_u")
    a.lfs(1, B_OFF, 11).fsubs(0, 0, 1)                             # sum (1 + u) - BLUR_N - BLUR_N / 2
    a.slwi(3, 6, 2).add(3, 3, 11).stfs(0, B_Z, 3)
    a.addi(6, 6, 1).cmpwi(6, 18).blt("d_s")
    a.stw(5, B_STATE, 11)
    _krow(a, 10, 11)
    a.li(6, 0)
    a.label("d_m")
    a.slwi(3, 6, 3).add(3, 3, 11).lfs(1, B_Z, 3).lfs(2, B_Z + 4, 3)
    a.fmuls(1, 1, 1).fmadds(1, 2, 2, 1).lfs(2, B_K2, 10)          # this level's K^2 (r10: its row)
    a.li(0, 0).fcmpo(1, 2).ble("d_mk").li(0, 1)                     # |z|^2 > K^2: a miss
    a.label("d_mk")
    a.add(4, 6, 11).stb(0, B_MISS, 4)
    a.addi(6, 6, 1).cmpwi(6, 9).blt("d_m")
    a.li(0, 1).stb(0, B_DRAWN, 11)
    a.label("d_ret")
    a.blr()


def _krow(a, rd, rb):
    """rd = BLUR + the level 4/5/6 K row. FLAG is 4 / 1 / 2 respectively."""
    l4, l5, done = f"kr4_{rd}", f"kr5_{rd}", f"krx_{rd}"
    a.lis(rd, ha(level5.FLAG)).lbz(rd, lo(level5.FLAG), rd)
    a.cmpwi(rd, 4).beq(l4).cmpwi(rd, 1).beq(l5)
    a.li(rd, 2).b(done)
    a.label(l5)
    a.li(rd, 1).b(done)
    a.label(l4)
    a.li(rd, 0)
    a.label(done)
    a.slwi(rd, rd, 3).add(rd, rb, rd).addi(rd, rd, B_KROW)


def blur_body(a):
    """BLUR(r3 = F, r4 = the mover's sp; target x 0xC(r4), z 8(r4)), leaf: while the ball is hidden, a drawn CPU
    fielder's target moves by z * F+0x184 / K; the ball shown: the draw resets. Uses r0, r5-r7, f0-f3, cr0."""
    a.label("blur")
    gate6(a, "bl_x", reg=5)
    a.load_addr(6, BLUR)
    a.lwz(5, GAME_PTR, 13).cmpwi(5, 0).beq("bl_x")
    a.lbz(0, G_HIDDEN, 5).cmpwi(0, 0).bne("bl_on")
    a.li(0, 0).stb(0, B_DRAWN, 6).blr()                             # shown: a new draw next time
    a.label("bl_on")
    a.lbz(0, B_DRAWN, 6).cmpwi(0, 0).beq("bl_x")
    a.lbz(0, F_LEVEL, 3).cmpwi(0, 0).bne("bl_x")                    # CPU fielders (level byte 0), as the Boo hook
    a.lbz(7, F_ID, 3).cmplwi(7, 8).bgt("bl_x")
    _krow(a, 5, 6)
    a.lfs(0, F_HREACH, 3).lfs(1, B_KINV, 5).fmuls(0, 0, 1)          # sigma = his reach / K (this level's)
    a.slwi(7, 7, 3).add(7, 7, 6)
    a.lfs(1, B_Z, 7).lfs(2, 0xC, 4).fmadds(2, 1, 0, 2).stfs(2, 0xC, 4)
    a.lfs(1, B_Z + 4, 7).lfs(2, 8, 4).fmadds(2, 1, 0, 2).stfs(2, 8, 4)
    a.label("bl_x")
    a.blr()


def _put(code, asm_fn):
    at = code.here + (-code.here % 4)
    made = asm_fn(at)
    a = made[0] if isinstance(made, tuple) else made
    blob = a.assemble()
    assert code.put(blob, align=4) == at
    return at, blob, made


def apply(dol, code, data):
    """Hook the six sites (seven addresses) in `dol`; stubs in `code`, constants and the debug block (defense_dbg) in
    `data` (charbuild Spaces). Needs level5.alloc first. Returns log lines."""
    assert level5.FLAG is not None, "level5.alloc(data) first"
    for hook, want in ((POW_HOOK, POW_ORIG), (DECIDE_HOOK, DECIDE_ORIG), (CATCH_HOOK, CATCH_ORIG),
                       (BLOCK_HOOK, BLOCK_ORIG),
                       (ROUTE_HOOKS[0][0], ROUTE_ORIG), (ROUTE_HOOKS[1][0], ROUTE_ORIG), (MOVER_HOOK, MOVER_ORIG),
                       (BOO_HOOK, branch(BOO_HOOK, FREEZE, link=True)),
                       (STAR_HOOK, branch(STAR_HOOK, FREEZE, link=True)),
                       *((h, cpu_dive.ORIG) for h, _ in cpu_dive.HOOKS)):
        got = dol.u32(hook)
        assert got == want, f"0x{hook:08X}: 0x{got:08X}, expected 0x{want:08X}"
    global BLUR, BLUR_K, HZ
    HZ = data.put(hazard_block(), align=4)
    k4, k5, k6 = (blur_k(p) for p in BLUR_P)                # (the build's Boo Error Rate per level, cpu_settings)
    BLUR_K = k6
    BLUR = data.put(bytes(B_OFF) + struct.pack(">3f", BLUR_N * 1.5, 1.0, 0.0)
                    + struct.pack(">6f", 1 / k4, k4 * k4, 1 / k5, k5 * k5, 1 / k6, k6 * k6), align=4)
    dbg.alloc(data)                                       # the attack's debug block (the stubs write it every frame)
    dbg.alloc_route(data)                                 # the fielders' move targets (the route hooks write them)
    cbase = data.put(consts(dol), align=4)
    log, total = [], 0
    for name, hook, fn in (("POW jump", POW_HOOK, lambda at: pow_stub(at, cbase)),
                           ("decide", DECIDE_HOOK, lambda at: decide_stub(at, cbase)),
                           ("run-catch spot", CATCH_HOOK, lambda at: catch_stub(at, cbase)),
                           ("catch block skip", BLOCK_HOOK, block_stub)):
        at, blob, _ = _put(code, fn)
        dol.w32(hook, branch(hook, at))
        total += len(blob)
        log.append(f"  {name}: 0x{hook:08X} -> 0x{at:08X} ({len(blob)} bytes)")
    at, blob, (_, entries) = _put(code, lambda at: route_stubs(at, cbase))
    for (hook, _), e in zip(ROUTE_HOOKS, entries):
        dol.w32(hook, branch(hook, e))
    dol.w32(MOVER_HOOK, branch(MOVER_HOOK, entries[2]))
    total += len(blob)
    log.append(f"  route: 0x{ROUTE_HOOKS[0][0]:08X}, 0x{ROUTE_HOOKS[1][0]:08X}, shared mover 0x{MOVER_HOOK:08X} -> "
               f"0x{at:08X} ({len(blob)} bytes)")
    at, blob, _ = _put(code, boo_stub)
    dol.w32(BOO_HOOK, branch(BOO_HOOK, at))
    total += len(blob)
    log.append(f"  Boo: 0x{BOO_HOOK:08X} -> 0x{at:08X} ({len(blob)} bytes)")
    at, blob, _ = _put(code, lambda at: boo_stub(at, STAR_HOOK))      # (Nick, 2026-09-28: "skip it like the boo")
    dol.w32(STAR_HOOK, branch(STAR_HOOK, at))
    total += len(blob)
    log.append(f"  Peach Garden night star: 0x{STAR_HOOK:08X} -> 0x{at:08X} ({len(blob)} bytes)")
    log += ["  " + x for x in cpu_dive.apply(dol, code, data)]
    lead0, peak0 = jump_profile(dol, 0)
    lead1, peak1 = jump_profile(dol, 1)
    return ([f"cpu item defense (level 6): POW jump, attack: run to the spot on the ball's track, stop, face the ball, "
             f"press when it will connect "
             f"(teammate within {ATK_MATE_D}), fly-ball peak jump "
             f"(lead {lead0}/{lead1} frames, peak {peak0:.2f}/{peak1:.2f}), route around items, Boo and the Peach Garden star ignored "
             f"({total} bytes code, {len(consts(dol))} bytes data at 0x{cbase:08X}, debug block 0x{dbg.ADDR:08X})"]
            + log)
