"""Level 6 CPU items (Nick, 2026-09-27): at level 6 the CPU's item cursor plays its real item and times it on the
fielder who gets the ball. Base items only (Shell 0, Fireball 1, Bob-omb 2, POW 3, Banana 4, Boo 5; docs/items.md);
anything else (no item -1, custom ids 6+) is played as the Shell, as stock. One item per at-bat, used on the play.
Level 6 only: every stub checks level5.FLAG == 2 (level5.py: 1 = level 5, 2 = level 6) and the CPU at the hardest
row (COjyamaCom +0x26 == 3, level 4 underneath); anything else runs the stock instructions. No shared table is edited.

The CPU item AI is GmOjyama::COjyamaCom (docs/cpu-ai-weaknesses.md section 1; object at *(r13-0x350), vtable
0x806CC3B8): +0x0C item id, +0x10/+0x14 cursor (x, z), +0x18 timer, +0x24 slot, +0x25 target fielder, +0x26 level
row, +0x27 item column, +0x28 triggered, +0x2A aim-at-landing-point.

THE PLAY (Nick, 2026-09-27, after the 18:24 dump: "start over", one model for every play, only what a human
thrower can see: the ball's flight, each fielder's spot and run speed; his table of the model, approved):
FRAMES [C]: the ball path (game +0x42C + i * 0x14: x, y, z, dist, h) is re-predicted every frame by 800B38C8 from the
ball now: path[i] = i frames FROM NOW (flight, bounces, roll). The wall-crossing frame X (+0x2A4A, FUN_800B5974: the
first path index past the wall distance) is frames from now too. E = frames since contact (*(r13-0x1684)+2).
- THE MEET (meet(), the spec): the first frame K >= 1 (before X when X > 0) at which some fielder (0..8) can take the
  ball: it is at most his catch height (+0x190) + JUMP_REACH up, and his run to within reach of it takes <= K frames:
  max(distance - reach, 0) / speed (+0xEC; 0: 1.0, as FUN_801142B8) + the reaction left, max(+0x225 >> 1,
  HUMAN_REACT) - E (>= 0). The reach (the defense logs of Nick's dumps): CATCH_REACH 5.0 for a ball moving at most
  SLOW_BALL a frame on the ground (a catch, +0x2AC 1, starts 4.9 - 6.1 m out and draws the ball in over ~10 frames),
  else BODY_REACH 1.25 (a fast ball: a jump catch, +0x2AC 6, within 0.86 - 1.25 m). That fielder is the target, K
  the meet frame, M the ball then. Nobody (a home run over everyone): no item this frame (log type 3).
  T = K - MEET_LEAD (15, Nick: caught in the air or on the ground alike; >= 0; the Boo: K); P = where he is at T:
  running straight from where he is toward M, stopping at the reach (the logs: fielders stop 4.9 - 6 m from the ball
  and take it from there), at the rate of his run time e: F + (M - F) (1 - reach / d) min(T / e, 1). Log path 4.
  scripts/replay_meet.py runs meet() on every batted play in the dumps' defense logs (the ball's real flight).
- THE WALL (kept; a buddy-jump plan, FUN_80125238 plan 8: ball +0x2A71 set (to the wall), +0x2A79 clear, not bounced,
  and either +0x2A75 > 1 (the home-run call of FUN_800B5974) or ball height at the wall-crossing frame +0x2A4A > 3.5
  with the landing point past the wall distance +0x29D8): his spot J = the wall point W (+0x408/+0x40C) moved 5.0
  toward the ball (+0x2A75 > 1) or along the wall normal (+0x410/+0x414), then his radius (+0x1C) toward him, as
  FUN_80125238 does. The jumper = the outfielder (6..8) with the smallest FUN_801142B8 ETA to J. With a
  wall-crossing frame X > 0: K = the first frame before X the ball comes down to BUDDY_Y (25 m) within BUDDY_R
  (10 m) of J (a buddy catch possible; Nick's 19:14 dump: the jump starts ~40 frames before the catch, and a high
  ball is caught well before the wall), else X; T = max(K - HR_LEAD, 0) (52, Nick: before any buddy jump can start;
  45 until the LF's jump in his 19:30 dump started 46 frames before a 24 m catch); P = where he is running (his spot
  + his direction * speed * T, as the chaser's: stock's aim), not past J (Nick's 19:32 dump: the CPU fielder stood
  5.5 m from the plan's J; a human stands where he likes). No crossing frame:
  his jump = the first path index k >= 1 with the ball within 5.0 of J (800E246C), T = max(k - HR_LEAD, his ETA).
  Boo: T = X. No plan: the meet.
Release (the frame the fire flag is set = the throw; timer = T - lag, floored at 0) and aim point C per item, with
the item's row (manager slot +0x33D, 0/1) and 60/50 Hz values read from the stock item tables at build time:
- Shell / Fireball: C = P, lag = D / speed, D = |P - S|, S = ORIGFN(P): where the game launches it (its own camera
  projection, see OBJ_FN). They arrive at P at T. The shot list may put C up to EXT past P instead (higher up the
  screen: S follows the cursor, so a shorter flight and a later release)
- Bob-omb: C = P (centred: Nick's 20:11 dump, the CF 5.8 m past the predicted spot; the edge placement, 6.0 -
  EDGE_MARGIN toward the cursor, left 2.5 m on his far side), lag = lob
  frames + fuse + 1 (it explodes at T: FUN_8044f740 stops it and sets the fuse on landing, the state-2 update counts
  it down and blasts the frame after it reaches 0; no blast on contact).
- POW: the same with its burst radius 20.0; lag = lob frames (it bursts on landing, at T).
- Banana (Nick: "the one at 12:00 is the one we try to put on the target"): C = P - 5.0 BANANA12, so the 12:00
  banana lands on P; lag = lob frames + BANANA_EARLY (it lands a little before T and waits).
- Boo: C = where the cursor already is (it appears at the ball); lag = Boo frames - BOO_END_AFTER + BOO_EARLY (750 ms:
  45 / 38 frames at 60 / 50 Hz; Nick, 2026-09-28), so it is thrown 750 ms before the throw that would end its 90-frame
  effect just after T (it also ends when a fielder has the ball, as stock).
Tighter aim at level 6: no random aim offset and no timer jitter or lead table (the aim is the exact spot), and the
trigger runs from the first frame the slot is armed (the stock one waits until the ball falls, ball +0x384 vy < 0).
LATE THROWS on balls in the air (Nick): the release is the frame the timer hits 0 AND the cursor was within 3.0 of
C (0x80450A94) AND the slot's 10-frame countdown (+0x3A8, reloaded to 10 while unarmed, 0x804565BC) is 0. So at
level 6 the decision (1) measures T from now (E above; the old code took +0x2A46 as if decided at contact, one frame
late per frame of arming delay), (2) clears the countdown byte (manager + slot * 0xC + 0x3A8), and (3) sets the
cursor step to max(SPEED6, (|cursor - C| - 2.5) / max(timer, 1)) (SPEED6 = 2.0 / 2.4 at 50 Hz, stock level 4 0.7 /
0.84) so it is in the gate by the release. LATE (timer < 0, Nick: "throw for all too late cases"): it goes at once,
every item (the spot still has to be good).

HOOKS (each `b` to a stub; the stock instruction + branch back when the gate fails):
  RESET 0x8045584C lwz r4,-0x34C(r13)  (FUN_80455598 at-bat setup, right after COjyamaCom's reset FUN_8044FDF0 was
        called with the item forced to 0 by `li r5,0` at 0x80455838; r29 = the manager): clears ACTIVE; at level 6
        (and a COjyamaCom with a slot) sets COM +0x0C = the manager's item (+0x338; not 0..5 -> 0) and +0x27 its
        column (min(id, 4)). Done after the call instead of at 0x80455838 so the level row (+0x26, set inside the
        reset) can gate it; the snapshot copy at -0x34C right after copies the real id too.
  DECIDE 0x8045031C cmpwi r0,5  (FUN_80450208 update, the Boo check before the trigger; r30 = COM, r1 frame with
        the target at 8(r1)): at level 6 skips stock's Boo branch; triggered by the stock fallback -> 0x804505D4
        (the stock countdown); a level 6 decision (ACTIVE) is made again every frame until the item goes (Nick:
        re-pick the fielder each frame); slot not armed yet (manager + slot * 0xC + 0x33E, FUN_8045630c: items usable, INFERRED to be
        from contact) -> 0x804505EC and wait; else computes T, P, the timer and C (above), sets +0x18/+0x25/+0x28/+0x2A, 8(r1), AIM, ACTIVE
        and goes to 0x804505EC (the aim call). Calls FUN_800AC748, FUN_801142B8 (the wall), sqrt FUN_8053C74C, ORIGFN
        (LR is saved by FUN_80450208; r29 is the ball, as stock).
  AIM   0x80450A68 fsubs f30,f2,f1  (FUN_80450794 aim/move; f1/f0 = cursor, f31 = step factor): at level 6 with
        ACTIVE and +0x28 set, the cursor heads for C (no offset) at the step set by DECIDE; the 3.0 gate stays.
        A SPOT A HUMAN COULD AIM AT (Nick: a high-fly POW's cursor went off screen and it never threw; items
        can't be thrown past the walls): each frame, if FUN_804570C8 says C is bad (off screen, past the wall /
        in the stands, or by a base), C = the first good spot of C0 (the planned C) turned around P by TURNS,
        at RINGS of its distance, else P; kept while good. The Bob-omb / POW edge point (6 / 20 m from the
        fielder) keeps its distance when any direction works, so he stays just inside the blast. Up to 32
        checks in a frame, only while C is bad. Timing unchanged.
        FRIENDLY FIRE (Nick; Bob-omb, POW, Banana only): a spot is also bad if the blast + RUNNER_PAD (Banana: its
        5 m spread + BANANA_HIT + RUNNER_PAD) reaches one of our runners anywhere on his path to the base he runs to
        (or back to), the base included (Nick: bombed its runner on his way to 2nd). No good spot and P would hit him too: no throw that frame (r31 = 0, the fire flag).
        NOTHING ON SCREEN (Nick: on a home run the cursor went off the top of the screen): P is not throwable
        either -> the cursor steps toward P if the step stays ON SCREEN (ONSTEPFN: the camera projection only; the
        full check also refuses the bases), else it holds where it is (a human's cursor stops at the screen edge);
        a cursor left off screen (Nick's 19:21 dump: the camera turned to left field) heads toward the ball on the
        ground (path[0]; the camera follows the ball), not the target (his 20:17 dump: it followed an off-screen
        target out); no throw that frame.
        SHOT LIST (Nick, 2026-09-28, after his 15:04 dump: the middle Fireball, thrown at the CF 64 m out, hit the SS
        42 m short): a Shell / Fireball decision (DECIDE, SHOTS in its own section) scores up to NK candidate shots at
        T + OFF[k] along the target's path (k = 0: the plan's P; the rest led at max(speed, top speed), capped as
        before; the fly-ball landing and a plan without a fielder: P only). Each: S = ORIGFN(P), the travel L / speed,
        the release rel = t - fixed - travel, and the other fielders its path(s) meet (one Shell path; a Fireball's
        three: the middle one to P, and +-FIRE_SPREAD degrees (its table +0x14 = 10; the 15:04 dump's side fireballs
        flew ~10 degrees off), the side ones out to RANGE): fielder i (not the target, and not whoever will be within
        CATCH_R of P when it gets there) at his spot + his run (direction * speed) by the time it passes him is hit
        within HIT_R of the path. Pick: a release still ahead (rel >= 0) first; Shell: the most other fielders hit,
        then the fastest (the shortest travel: it waits longest); Fireball: only shots with nobody else hit, the
        fastest; all late: the least late. A Fireball with no clear shot holds (no throw; re-decided next frame).
        HIT_R, CATCH_R and a Shell going on after a hit are UNMEASURED.
        LINE (Nick: items keep going past the cursor): a bad spot for a Shell / Fireball (record speed > 0) first
        tries the spots on the
        line from the launch origin S to P, closest to P first; it passes through P at the planned time.
        NO WRONG-SPOT FALLBACKS (Nick, 2026-09-27, after the 16:18 dump: a home-run banana slid back toward where
        the fielder had been and went 2.7 s early; earlier the inward steps threw short): a spot is only ever one
        that still lands the item on him (C0, C0 turned around P at full / smaller radius, P; a Banana's other
        four banana positions; a Shell / Fireball's line to him). None good: the cursor heads there while it can
        stay on screen and holds, with no throw (r31 = 0) until a good spot comes on screen, then it throws at once.
        BANANA: a bad Banana spot first tries the cursor spots that land another of the five bananas on B (the
        12:00 banana's spot); then the search above.
  FLIGHT 0x80453764 lwz r12,0(r3)  (FUN_80453764, the per-object item update called by the dispatch FUN_80455394;
        LOG BUILDS ONLY): a type 6 log record per frame for each in-use (+0x37) Shell / Fireball object (active id,
        manager +0x394, 0 / 1) while it flies (+0x3C: 1 / 2): its position and velocity, so a dump shows where it
        really went and how fast; and on the first frame of a Bob-omb blast / POW burst a type 7 record (the burst
        centre) plus a type 8 record per fielder (his spot, height, airborne; FLOGFN, which the AIM stub also calls
        after each cursor step for the target fielder)
        (read_item_log.py: the step per frame and the closest pass to the target spot). Works with ludwig_fire's
        moved Fireball pool (the dispatch still calls FUN_80453764). Object positions are in field space, the
        fielders' and the ball's (the launch FUN_804539D4 flips the cursor's z; bullet_bill's log) [INFERRED].
Sizes: see apply()'s log. Test: scripts/test_cpu_items.py.

CONFIRMED (code + stock data): item ids; Shell speed 0.4 / 0.7 per frame (row 0/1; 50 Hz 0.48/0.84, 0x80631008 +8,
straight, normalised); Fireball speed 0.4 / 0.6 (0x8063129C); Bob-omb lob 60 / 30 frames (0x80631058 +0x34), fuse
45 (+0x28), blast radius 6.0 horizontal (+0x0C, FUN_80117408 state 3), blast 30 frames; POW lob 60 / 30
(0x806311D8 +0x2C), burst on landing, radius 20.0 + the fielder's radius (+0x08, FUN_80117E34 state 2), 12 frames;
Banana lob 60 / 30 (0x80631148 +0x20), 5 bananas, spread 5.0 (+0x14), leader +x; Boo 90 frames (60 Hz; 75 at 50 Hz,
0x807A1640). INFERRED: the item flies from S to the cursor (FUN_804539D4); the Fireball's ground speed is its table
speed (it arcs and bounces); followers at angles 72 * k degrees (cos x, sin z); the Bob-omb's fuse runs from
landing (CONFIRMED in code since); the jumper choice. (Wrong until 2026-09-27: that the path is indexed by E.)
UNMEASURED: EDGE_MARGIN, BOO_END_AFTER, SHOT_LAG (frames between the fire flag and the item's first step), HUMAN_REACT
and where a human fielder stops (the reach: measured on the CPU's fielders), the Shell / Fireball speeds in flight (the FLIGHT log records them: compare its step per frame with records()). Timing is to the frame model above (about +-1 frame), not measured.
"""
import math
import struct
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
import level5  # noqa: E402
from ppc import Asm, branch, d_form, ha, lo  # noqa: E402

LEVEL6 = 2                                          # level5.FLAG at level 6
HARDEST = 3                                         # COjyamaCom +0x26 row at level 4 (and 5 / 6)
COM_VTABLE = 0x806CC3B8

RESET, RESET_ORIG = 0x8045584C, 0x808DFCB4          # lwz r4,-0x34c(r13)
DECIDE, DECIDE_ORIG = 0x8045031C, 0x2C000005        # cmpwi r0,5
AIM, AIM_ORIG = 0x80450A68, 0xEFC20828              # fsubs f30,f2,f1
TRIGGERED, FALLBACK, AIM_CALL = 0x804505D4, 0x8045045C, 0x804505EC
AIM_BACK = 0x80450A78                               # after the speed load and fmuls f31
FLIGHT, FLIGHT_ORIG = 0x80453764, 0x81830000        # lwz r12,0(r3): FUN_80453764, the item object update (log builds)
CLASS_FN, BALLPOS_FN, CHASE_FN, SQRT_FN = 0x800B0BFC, 0x800AC748, 0x800CDBBC, 0x8053C74C
TEAMS = (-0x1D14, -0x1D10, -0x1D18, -0x1D1C)        # the first non-null is the fielding team (stock order)

R2 = 0x8079EDC0
ZERO, ONE, FLY_Y, EPS = 0x27C0, 0x27D0, 0x27CC, 0x27E0   # r2 offsets: 0.0, 1.0, 20.0, 1e-4
ORIGIN_X, ORIGIN_Z = 0x6090, 0x6094                 # r2 offsets, 0x807A4E50/54: NOT where items launch (Nick's 17:47
                                                    # dump: a constant 0, used only by FUN_804577B8's manager +0x39D
                                                    # == 0 branch); the launch start S is ORIGFN's (below)
# THE LAUNCH START S (Nick's 17:47 dump: a Shell launched from (-11.6, 11.3), not home plate; the manager keeps the
# last launch's start at +0x374 and its direction (= cursor - start) at +0x380): FUN_80456710 throws at the cursor C
# (field x / z) through FUN_80453824 -> FUN_804539D4 on obj = FUN_80456ABC(manager, item) (a free object of the item's
# pool; read-only: vtable +0x28 "in use"): h = obj vtable +0x3C(), FUN_804577B8(h, C.x, -C.z, &out, manager, 0)
# (manager +0x39D != 0: C on screen, unprojected at depth h by the camera), then FUN_80454090(C.x, -C.z, obj, &out)
# (off screen: pulled onto the screen edge); S = (out.x, out.z). So S depends on C and the camera, every frame.
OBJ_FN, START_FN, CLIP_FN = 0x80456ABC, 0x804577B8, 0x80454090
ORIGFN = None                                       # the launch-start subroutine, set by apply()
ROUTE_T, ROUTE_N, ROUTE_SZ = None, 9, 12            # defense_dbg.ROUTE (the fielders' move targets), set by apply()
# THE MOST FIELDERS IN A POW (Nick, 2026-09-28: "do the same thing for pows that we did for shells to maximize the
# cpus hit (and still hit the target)"): after the edge placement (C = P + D toward the cursor, D = 20 - EDGE_MARGIN),
# POWFN predicts every other fielder j at the burst (T frames from now): his own move target (defense_dbg.ROUTE, fresh)
# reached at max(+0xE4, +0xEC), else F + heading (+0x94 / +0x98) * +0xE4 * T; his reach R_j = D + his radius (+0x1C).
# Candidates, in order: the edge C, P, and per fielder j with |Q_j - P| = L <= D + R_j the point on P -> Q_j at
# a = (max(0, L - R_j) + min(D, L)) / 2 (inside both). The most j with |C - Q_j| <= R_j wins (the first on ties, so
# the edge C unless another catches more); the target is always within D of every candidate.
POWFN, POWB = None, None                            # set by apply()
PQX, PQZ, PRJ = 0, 36, 72                           # POWB: Q_j x, z, R_j (-1: not counted) for j 0..8
PD, PT, PTX, PTZ, PTR, PCX, PCZ, PBX, PBZ, PHALF, PBEST = (108 + 4 * i for i in range(11))
POWB_SIZE = PBEST + 4
# ON SCREEN ONLY (Nick's 19:21 dump: the Banana cursor sat by 2nd base all play, 60 m from its spot): the throwable
# check FUN_804570C8 is three tests: the camera projection (FUN_80251d00(0) camera, FUN_80252030(cam, (x, ground
# r2+0x2888, -z), out)) inside r2+0x288C..0x2890 on both axes, FUN_80457ff0, and FUN_804581bc (throwable ground, NOT
# near the four bases). The cursor's step only needs the first (a human's cursor crosses the bases; it just can't
# throw there): ONSTEPFN, the same projection and bounds.
CAM_FN, PROJ_FN = 0x80251D00, 0x80252030
ONSTEPFN = None                                     # set by apply()
FLIGHT_EVERY = 8                                    # log builds: a flight record every 8th frame (Nick's 17:47 dump:
                                                    # one Shell's 220 per-frame records pushed out every older play)
BALL, MANAGER, COM, HZ = -0x1D94, -0x354, -0x350, -0x1658
TEAMS = (-0x1D14, -0x1D10, -0x1D18, -0x1D1C)        # the first non-null is the fielding team (stock order)
PATH, PATH_STEP, PATH_MAX = 0x42C, 0x14, 0x1DF      # ball path x at +0x42C, z at +0x434, per frame
ARMED = 0x33E                                       # manager + slot * 0xC: the slot can throw (FUN_8045630c)

SHELL, FIRE, BOMB, POW, BANANA, BOO = range(6)
SPEED6 = (2.0, 2.4)                                 # cursor per frame at level 6 (60, 50 Hz); stock level 4 0.7, 0.84
EDGE_MARGIN = 2.5                                   # how far inside the blast edge the fielder is (m); Nick's dump
                                                    # (Bob-omb, 15:59): 0.5 missed him by a little (his real spot
                                                    # vs the predicted one)
BOO_END_AFTER = 1                                   # UNMEASURED: the Boo ends this many frames after T
BOO_EARLY_MS = 750                                  # Nick, 2026-09-28: the Boo thrown 750 ms earlier than that
BOO_EARLY = tuple(int(BOO_EARLY_MS * hz / 1000 + 0.5) for hz in (60, 50))   # frames: 45 at 60 Hz, 38 at 50 Hz
SHOT_LAG = 0                                        # UNMEASURED: frames from the fire flag to the item's first step
BOMB_FUSE_EXTRA = 1                                 # the fuse counter hits 0 one frame after `fuse` (FUN_8044f740 / state 2)
MEET_LEAD = 15                                      # Nick (2026-09-27): hit him 15 frames before he gets the ball,
                                                    # caught in the air or on the ground alike (45 at the wall: HR_LEAD)
KIND_AT, KIND_EDGE, KIND_BANANA, KIND_STAY = range(4)

# home runs (the buddy jump) and the release timing
FIELDERS = 0x80708D78                               # [i] (+0x24: 0x80708D9C, +0x48: 0x80708DC0 checked first, as stock)
OUTFIELD = (6, 7, 8)                                # LF, CF, RF
ETA_FN = 0x801142B8                                 # frames for fielder r3 to reach (f1, f2)
PLAYSTATE = -0x1684                                 # *(r13-0x1684)+2: frames since contact (the path's frame index)
SPOT_BACK = 5.0                                     # 0x80797834: the buddy spot is this far off the wall (FUN_80125238)
WALL_Y = 3.5                                        # 0x80625C74: ball height at the wall for a buddy plan
JUMP_D = 5.0                                        # 0x8079736C: the CPU jumps with the ball this close (800E246C)
BUDDY_Y, BUDDY_R = 25.0, 10.0                       # Nick's 19:14 dump (a Fireball on target but late): the CF's buddy
                                                    # jump started at 321, 39 frames before his catch at 360 (14 m up),
                                                    # ~60 before the crossing; every buddy catch in the dumps: 14 - 25 m
                                                    # up, the jump ~40 frames before. So the wall's frame is the first
                                                    # the ball comes down (descending) to BUDDY_Y within BUDDY_R of his
                                                    # spot J, before the crossing; none: the crossing
# THE CHASER (Nick's 19:34 dump: no POW; "nobody" for 195 frames, 85 of them after the bounce with the CF 9 m from
# the ball): stock's FUN_800CDBBC only counts fielders whose +0x21D is 1 / 10 / 11 (ready), fine for stock's one
# decision as the ball comes down, but a level 6 decision is made every frame and the chasers leave that state. So
# the level 6 chaser is its scan without that gate: each fielder, the path every CHASE_STEP frames from 1 below
# CHASE_MAX, the first point his FUN_801142B8 time < k + CHASE_SLACK; the smallest such time wins (stock's rule).
# A fly that won't be caught (catch class >= 4; stock waits for the bounce) counts only points at most CHASE_GROUND
# up: the fielder who picks it up after it drops in.
# OFF THE WALL (Nick, 2026-09-27: "time when the ball will hit the wall in the air ... instead of when the ball will
# get to the character. If the ball hit the ground then it should do what it does now"): a fly or ground play whose
# ball reaches the wall (the game's wall distance for it, ball +0x29D8, less WALL_IN) while still in the air (y >
# IN_AIR_Y at every path frame up to then) is timed to that frame, T = K_wall (every item); a ball on the ground
# before it: as before. (Home runs over the wall: the buddy-jump rule, unchanged.)
WALL_IN, IN_AIR_Y = 1.0, 0.5
CHASE_STEP, CHASE_MAX, CHASE_SLACK, CHASE_GROUND = 5, PATH_MAX + 1, 15, 2.0   # the whole path (stock: 120; Nick's
                                                    # 20:23 dump: a drop-in landing ~200 frames out found nobody)
# THE FIRST HOP (Nick's 20:40 dump: the RF hopped onto the CF 2 frames before the POW; across his dumps the hop came
# 41, 57 and 67 frames before the ball was in reach - it follows the teammate, not the ball): the RF left the ground
# the frame the CF came within ~3.7 m. So at the wall T is also at most the teammate's arrival: the runner-up
# outfielder (FUN_801142B8 to J), (his distance to J - HOP_D) / his speed as he runs now (+0xE4; at least +0xEC:
# the CF closed at 0.24 m/frame against +0xEC 0.122), less HOP_MARGIN.
HOP_D, HOP_MARGIN = 3.7, 5
# THE SHAKE DASH (FUN_8011B600 / FUN_800D5C34, researched 2026-09-27): a human fielder who shakes the remote runs at
# up to 1.4x his cap (+0xEC; 1 + 0.4 * level/50, level +10 a shake, ~5 frames to full, ends ~15 frames after the
# last shake); CPU fielders (pad slot +0x2C9 == 4) never do. An outfielder running to a good-chemistry buddy on an
# unbounced fly gets his cap doubled (x2.0, 0x80625C70), human or CPU: every buddy jump's teammate. So: a human
# chaser's FUN_801142B8 time is taken as if he shakes (x DASH_NUM / DASH_DEN = 1 / 1.4), and the buddy teammate
# runs at least BUDDY_CAP x +0xEC.
DASH_NUM, DASH_DEN, CPU_SLOT, BUDDY_CAP = 5, 7, 4, 2.0
# LEVEL 5 (Nick, 2026-09-27: "an item nerf, timing and position be off slightly"; "perfect items 75% of the time"):
# level 5 plays the level 6 items; at the first decision of each at-bat (ACTIVE still 0) it rolls, with the game's
# RNG (FUN_80165C14 on *(r13-0x1578), as stock's item AI): L5_PERFECT% of at-bats perfect, else a timing error of
# -L5_T..+L5_T frames and a position error of (-L5_K..+L5_K) * L5_STEP m on x and z, added to T and P for the whole
# at-bat. Level 6: none.
RAND_FN, RNG = 0x80165C14, -0x1578
L5_PERFECT, L5_T, L5_K, L5_STEP = 75, 30, 10, 0.25
# L5_T 30 frames = 500 ms at 60 Hz (Nick, 2026-09-28: "up to 500ms early or late"; was 6)
HR_LEAD = 65                                        # (Nick's 20:09 dump: before the FIRST jump, the hop onto
                                                    # his teammate, 41-57 frames before the ball is in reach)
                                                    # home run: the burst this many frames before the ball crosses
                                                    # the wall (Nick, 2026-09-27: before the earliest buddy jump
                                                    # that can still catch it; an airborne fielder shrugs off the
                                                    # POW). 45 until his 19:30 dump: the LF's jump started 46 frames
                                                    # before a catch 24 m up, 2 frames before the POW
GATE_IN = 2.5                                       # the cursor aims to be this close by release (stock fire gate 3.0)
ONSCREEN_FN = 0x804570C8                            # (f1 x, f2 -z, r3 manager) -> r3 != 0: a spot an item can go:
                                                    # on screen (camera projection in -1..1, FUN_80457ff0) and
                                                    # FUN_804581bc: a ray down hits a throwable ground surface
                                                    # (FUN_80182480; not the stands / past the wall) and it is not
                                                    # near the four spots 0x80625798 (radius 0x80630FCC[hz]); used
                                                    # by FUN_80450cc0 to pick a CPU target [INFERRED from code]
TURNS = (0, 45, -45, 90, -90, 135, -135, 180)       # a bad spot: try these turns of C0 around P (degrees) ...
RINGS = (1.0, 0.75, 0.5, 0.25)                      # ... at these fractions of |C0 - P|; none good: P
RUNNERS = 0x807098C8                                # [0..3] the batting team's runners (0 = batter-runner), or 0
BASES = 0x80625798                                  # [0..3] home, 1st, 2nd, 3rd (x, z) (the fielder spot table; its
                                                    # first four are the bases FUN_804581bc keeps items off)
R_ON, R_FROM, R_TO, R_DIR = 0x176, 0x17D, 0x17E, 0x183   # runner: on the field; from / to base; 1 on, 2 stop, 3 back
RUNNER_PAD = 1.5                                    # friendly fire (Nick): keep own runners this far outside the blast
AT4 = {}
AT5 = {}                                            # level 5's own MEET_LEAD / SPEED6 / RUNNER_PAD (cpu_settings;
                                                    # level5.pair): SPEED6 and RUNNER_PAD's go in the data block's L5K
                                                    # tail (only when they differ), MEET_LEAD in the code
L4K = None
L5K = None                                          # that tail's offset in the data block (data_block), or None
BANANA_HIT = 1.5                                    # UNMEASURED: a runner this close to a banana slips on it
BANANA_EARLY = 10                                   # the banana lands this many frames before T (it just waits there)
LINE_STEP, LINE_TRIES = 0.1, 9                      # Shell (Nick: it keeps going past the cursor): a bad spot ->
                                                    # the spots on the line from its launch origin S to P, from
                                                    # 0.9 of the way down to 0.1; the travel time to P is the same

# data block offsets
ACTIVE, AIMX, AIMZ, TSAVE, RECP, UX, UZ, SCR, SPEEDS = 0, 4, 8, 0xC, 0x10, 0x14, 0x18, 0x20, 0x28
ELAP, CSPEED, JX, JZ, BEST, BETA, LOOP, CAND = 0x30, 0x34, 0x38, 0x3C, 0x40, 0x44, 0x48, 0x4C
KSPOT, KWALLY, KJUMP, KGATE, MAGIC, JPTR = 0x50, 0x54, 0x58, 0x5C, 0x60, 0x68
PX, PZ, SI, SK, KBACK, C0X, C0Z, ROT, RAD = 0x70, 0x74, 0x78, 0x7C, 0x80, 0x84, 0x88, 0x8C, 0xCC
SUBLR, KFFE, KFFB, RI, KF, KR2, BAN5 = 0xE0, 0xE4, 0xE8, 0xEC, 0xF0, 0xF4, 0xF8
FX, FZ, BSI, TARR, BSK, KSTEP, KLINE = 0x120, 0x124, 0x128, 0x12C, 0x130, 0x144, 0x148
LOGP, LOGLR, DPATH, QRES, HELD, HRWHY = 0x150, 0x154, 0x158, 0x159, 0x15A, 0x15B
K12X, K12Z, FPTR = 0x160, 0x164, 0x168
SX, SZ, LASTOBJ, SF, LASTF, LAUNCHX = 0x170, 0x174, 0x178, 0x17C, 0x180, 0x184
KBUDY, KBUDR2, KGROUND, KWALLIN, KGROUNDY, BETA2, MPTR, KHOPD, KBUDCAP = (0x188, 0x18C, 0x190, 0x194, 0x198,
                                                                        0x19C, 0x1A0, 0x1A4, 0x1A8)
L5T, L5X, L5Z, KL5STEP, L5SAVE = 0x1AC, 0x1B0, 0x1B4, 0x1B8, 0x1BC   # level 5: this at-bat's errors (16 B)
KBCD, KBCY, KBCR2, KBCW, RECS = 0x1D0, 0x1D4, 0x1D8, 0x1DC, 0x1E0   # the Bob-omb's clearance (BOMB CLEAR, below)
# BOMB CLEAR (Nick, 2026-09-29: "The ball is hitting the bob omb, let's just keep it clear of the ball don't change
# anything else"): the Bob-omb is still centred on P, unless the ball's path, from now to the blast (T) and while it
# is low enough to touch it (y <= BCLEAR_Y), passes within BCLEAR_R of P: then P moved BCLEAR_D, to either side of
# the line from home plate through P, else past P, else short of it; the first that the path keeps clear of. None
# clear: P as before. (Direction by frsqrte alone, ~3%: fine for a 2.5 m step.) Nick's 12:48 dump: T is the release
# timer + the item's fixed frames (it looked 6 frames ahead and kept P until the release frame), and the game's path
# runs on through the wall while the ball comes back off it (it rolled back along the wall into the Bob-omb): the path
# is read only up to the wall, and when it gets there before the blast a spot within BCLEAR_WALL of the wall is bad;
# then also 2D and 3D short of P. Nick, 2026-09-29: the gap from the ball 1.5 -> 3.5 m (the steps stay 2.5 m, so a
# ball through P leaves only the short spots, and the side spots of a ball passing beside P).
BCLEAR_D, BCLEAR_Y, BCLEAR_R, BCLEAR_WALL = 2.5, 2.5, 3.5, 4.0
LATEFIX, LCX, LCZ = 0x15C, 0x16C, 0x1CC            # the late re-lead (below): done this decision; the lead's cap
KW = 0xDC                                           # the chaser: the first path frame at the wall (docstring)
# ---- the Shell / Fireball shot list (docstring SHOT LIST): its block (data), its code in its own section
OFF = (0, 10, 20, 30, 45, 60, 80, 100)              # candidates: T + OFF[k] frames along the target's path
HIT_R, RANGE, CATCH_R, FIRE_SPREAD = 1.2, 120.0, 3.0, 10.0   # m, m, m, degrees (the Fireball table +0x14)
SHOT_SECTION = 0x800
K_HIT, K_RANGE, K_CATCH, K_COS, K_SIN, K_OFF = 0, 4, 8, 12, 16, 20      # SHOTB: constants
SH_PTR = K_OFF + 4 * len(OFF)                                            # the SHOTS routine (0: not built)
CPX, CPZ, CSX, CSZ, CL, CREL, CTRAV, CHITS, CT = (SH_PTR + 4 + 4 * i for i in range(9))   # the candidate
BPX, BPZ, BSX, BSZ, BREL, BTRAV, BHITS, BT, BOK = (CT + 4 + 4 * i for i in range(9))      # the best so far
WX, WZ, WR, SSCR = BOK + 4, BOK + 8, BOK + 12, BOK + 16                                   # a path; 8 B scratch
# HIGHER UP THE SCREEN (Nick, 2026-09-28: "fire higher up on the screen (fastest to get there) that way we fire
# later"): the launch start S = ORIGFN(C) follows the cursor a little (the camera unprojects it: 0-18 m up the field
# across his dumps' cameras for a cursor 0-140 m out). So each candidate also tries the cursor EXT m past P along
# S -> P: C' = P + unit(P - S) * e, kept when C' is throwable (FUN_804570C8), S' = ORIGFN(C') is nearer P than S,
# and the line S' -> C' still passes P within EXT_MISS (the Shell / Fireball fly on past the cursor): a shorter
# flight, so a later release. The nearest S wins; the cursor goes to that C'.
EXT, EXT_MISS = (15.0, 30.0, 60.0), 0.5
K_EXT = SSCR + 8                                                                          # the EXT distances
K_MISS, EI, XCX, XCZ, XSX, XSZ, XL = (K_EXT + 4 * len(EXT) + 4 * i for i in range(7))
CAX, CAZ, BAX, BAZ = XL + 4, XL + 8, XL + 12, XL + 16                                     # the aim (C)
SHOTB_SIZE = BAZ + 4
SHOTB = None                                        # its address (apply)
# BUDDY_Y, BUDDY_R^2, CHASE_GROUND, WALL_IN, IN_AIR_Y; the teammate's run time to J and object; HOP_D
# SX / SZ: ORIGFN(P) this decision; log builds: LASTOBJ / LASTF the object / frame of the last logged burst (Nick's
# 17:47 dump: one Bob-omb blast logged 31 times), LAUNCHX the manager +0x374 of the last logged launch; SF scratch
# THE 12:00 BANANA (Nick, 2026-09-27: "the one at 12:00 is the one we try to put on the target"): the Banana launch
# FUN_8044ED58 lands the leader at the target + (spread, 0) and follower k = 1..4 at + spread * (cos a, sin a) in world
# x / z, a = 72 k degrees (0x8053E074 = cos: FUN_80562400 folds the angle with abs() and never restores the sign; 0x8053E068
# = sin: FUN_80562398 keeps it), and the item's world z is the cursor's -z (FUN_80456710 throws at (x, -z)). So in cursor
# space banana k sits at the cursor + spread * (cos a, -sin a); the one toward centre field (+z, the top of the screen
# behind home) is k = 4 (a = 288 degrees): (0.309, 0.951). The cursor goes to P - spread * BANANA12.
BANANA12 = (0.30901699, 0.95105652)
# why a ball wasn't a buddy-jump home run (the "decided" record's flags >> 4): 1 not heading for the wall (+0x2A71),
# 2 +0x2A79 set, 3 bounced, 4 no wall-height / landing-past-the-wall case, 5 no outfielder, 6 the ball never comes
# within JUMP_D of the spot, 7 nobody gets there before the jump
HR_WHY_CODES = (1, 2, 3, 4, 4, 4, 4, 5, 6, 7)

# IN-GAME LOG (Nick, 2026-09-27: stop guessing, read what happened from a RAM dump). Off (0) in normal builds;
# build_test_items.py sets LOG_ENTRIES. A ring in the data section: b"L6IL", u32 records written so far, u32 entries,
# u32 record size, then the records (LOG_REC bytes): u8 type, u8 item, s8 target (COM +0x25), u8 flags, s16 frames
# since contact, s16 timer (COM +0x18), f32 C x / z, f32 cursor x / z, f32 P x / z.
# Types: 1 decided (flags = path: 0 home run, 1 fly (the landing point), 2 ground, 3 fly, Shell / Fireball at the
# catcher), 3 fly nobody reaches: wait for the bounce, 4 the stock fallback's countdown, 5 the cursor step (flags:
# bit 0 fire flag r31, bit 1 held at the screen edge, bits 2-3 the last spot check: 0 not throwable, 1 good, 2 own
# runner), 6 the Shell / Fireball in flight (FLIGHT hook, every frame per object in use): u8 6, u8 item (manager
# +0x394), s8 target, u8 visible (+0x36), s16 frames since contact, u16 the object's address (low half: which
# Fireball), f32 position x / y / z (+4), f32 velocity x / y / z (+0x10); only while it flies (+0x3C: Shell 1,
# Fireball 2; Nick's 17:03 dump: 3 stopped Fireballs filled the ring for 340 frames), 7 a Bob-omb blast / POW burst
# (the first frame of Bob-omb +0x3B == 3 / POW +0x3A == 2, FLIGHT hook): the type 6 layout (position = the burst
# centre), followed by a type 8 record for each fielder 0..8; 8 a fielder (FLOGFN; after every type 5 record for the
# target COM +0x25, and at a burst): u8 8, u8 fielder, s8 target, u8 airborne (+0x22E), s16 frames since contact, u8
# why (0 the target during a cursor step, 1 at a burst), u8 0, f32 x (+4), y (+0xD4, his feet), z (+0xC), radius
# (+0x1C), f32 the decided target spot P x / z. scripts/read_item_log.py reads it.
LOG_ENTRIES = 0
LOG_REC, LOG_MAGIC = 32, b"L6IL"
LOGFN = None                                        # the log subroutine's address, set by apply()
FLOGFN = None                                       # the fielder record subroutine (log builds), set by apply()
REC = 16                                            # f32 speed (0: no travel term), s32 fixed lag, f32 dist, u32 kind
DATA = None                                         # set by apply()


def _f(dol, a):
    return struct.unpack(">f", dol.read(a, 4))[0]


def records(dol):
    """[(speed, fixed, dist, kind)] for Hz 0..1, row 0..1, item 0..5 (index (hz * 2 + row) * 6 + item), from the
    stock tables in `dol`."""
    out = []
    for hz in range(2):
        for row in range(2):
            shell = 0x80631008 + hz * 0x28 + row * 0x14
            fire = 0x8063129C + hz * 0x40 + row * 0x20
            bomb = 0x80631058 + hz * 0x78 + row * 0x3C
            pow_ = 0x806311D8 + hz * 0x60 + row * 0x30
            ban = 0x80631148 + hz * 0x48 + row * 0x24
            boo = struct.unpack(">h", dol.read(0x807A1640 + hz * 4, 2))[0]
            out += [(_f(dol, shell + 8), SHOT_LAG, 0.0, KIND_AT),
                    (_f(dol, fire), SHOT_LAG, 0.0, KIND_AT),
                    (0.0, int(_f(dol, bomb + 0x34)) + int(_f(dol, bomb + 0x28)) + BOMB_FUSE_EXTRA,
                     _f(dol, bomb + 0xC) - EDGE_MARGIN,
                     KIND_EDGE),
                    (0.0, int(_f(dol, pow_ + 0x2C)), _f(dol, pow_ + 8) - EDGE_MARGIN, KIND_EDGE),
                    (0.0, int(_f(dol, ban + 0x20)), _f(dol, ban + 0x14), KIND_BANANA),
                    (0.0, boo - BOO_END_AFTER + BOO_EARLY[hz], 0.0, KIND_STAY)]
    return out


def bomb_clear(a):
    """BOMB CLEAR's leaf "bclr" (docstring): r11 = the item record, r12 = the data block, r29 = the game (the path);
    AIMX / AIMZ = P in, C out. Uses r0, r5-r10, f0-f13, SCR."""
    a.label("bclr")
    a.lwz(5, TSAVE, 12).lwz(0, 4, 11).add(5, 5, 0)                 # T = the release timer + its fixed frames
    a.cmpwi(5, 1).bge("bc_t1").li(5, 60)                            # (none: 60)
    a.label("bc_t1")
    a.cmpwi(5, PATH_MAX).ble("bc_t2").li(5, PATH_MAX)
    a.label("bc_t2")
    # the wall: the game's path runs on through it, so stop at the first frame there (the ball comes back off it)
    a.li(6, 0)
    a.lfs(0, 0x29D8, 29).lfs(1, FLY_Y, 2).fcmpo(0, 1).ble("bc_nw")   # (no wall known: +0x29D8 <= 20 m)
    a.lfs(1, KBCW, 12).fsubs(1, 0, 1).fmuls(1, 1, 1).stfs(1, SCR, 12)  # (wall - BCLEAR_WALL)^2
    a.lfs(1, KWALLIN, 12).fsubs(13, 0, 1).fmuls(13, 13, 13)         # (wall - WALL_IN)^2
    a.li(7, 1).addi(8, 29, PATH_STEP)
    a.label("bc_w")
    a.cmpw(7, 5).bgt("bc_nw")
    a.lfs(11, PATH, 8).lfs(12, PATH + 8, 8).fmuls(11, 11, 11).fmadds(11, 12, 12, 11).fcmpo(11, 13).bge("bc_wall")
    a.addi(7, 7, 1).addi(8, 8, PATH_STEP).b("bc_w")
    a.label("bc_wall")
    a.addi(5, 7, -1).li(6, 1)                                       # scan to the frame before; near the wall is bad
    a.label("bc_nw")
    a.lfs(1, AIMX, 12).lfs(2, AIMZ, 12)
    a.fmuls(5, 1, 1).fmadds(5, 2, 2, 5).lfs(0, ONE, 2).fcmpo(5, 0).blt("bc_ret")   # P at home plate: as is
    a.frsqrte(5, 5).fmuls(6, 1, 5).fmuls(7, 2, 5)                   # u = P / |P| (home plate -> P)
    a.lfs(9, KBCY, 12).lfs(10, KBCR2, 12)
    a.li(10, -1)
    a.label("bc_c")
    a.lfs(8, KBCD, 12)
    a.fmr(3, 1).fmr(4, 2)
    a.cmpwi(10, 0).blt("bc_test").bne("bc_1")
    a.fnmsubs(3, 8, 7, 1).fmadds(4, 8, 6, 2).b("bc_test")          # P + D (-uz, ux)
    a.label("bc_1")
    a.cmpwi(10, 1).bne("bc_2")
    a.fmadds(3, 8, 7, 1).fnmsubs(4, 8, 6, 2).b("bc_test")          # P + D (uz, -ux)
    a.label("bc_2")
    a.cmpwi(10, 2).bne("bc_3")
    a.fmadds(3, 8, 6, 1).fmadds(4, 8, 7, 2).b("bc_test")           # past P
    a.label("bc_3")
    a.cmpwi(10, 4).blt("bc_s")
    a.fadds(8, 8, 8)                                                # 2D
    a.cmpwi(10, 5).blt("bc_s")
    a.lfs(0, KBCD, 12).fadds(8, 8, 0)                               # 3D
    a.label("bc_s")
    a.fnmsubs(3, 8, 6, 1).fnmsubs(4, 8, 7, 2)                      # short of P by D / 2D / 3D
    a.label("bc_test")
    a.cmpwi(6, 0).beq("bc_tp")                                      # the ball reaches the wall: not by the wall
    a.fmuls(11, 3, 3).fmadds(11, 4, 4, 11).lfs(12, SCR, 12).fcmpo(11, 12).bge("bc_bad")
    a.label("bc_tp")
    a.li(7, 1).addi(8, 29, PATH_STEP)                               # path[1]
    a.label("bc_k")
    a.cmpw(7, 5).bgt("bc_ok")
    a.lfs(11, PATH + 4, 8).fcmpo(11, 9).bgt("bc_n")                # high: can't touch it
    a.lfs(11, PATH, 8).fsubs(11, 11, 3).lfs(12, PATH + 8, 8).fsubs(12, 12, 4)
    a.fmuls(11, 11, 11).fmadds(11, 12, 12, 11).fcmpo(11, 10).blt("bc_bad")
    a.label("bc_n")
    a.addi(7, 7, 1).addi(8, 8, PATH_STEP).b("bc_k")
    a.label("bc_ok")
    a.stfs(3, AIMX, 12).stfs(4, AIMZ, 12)
    a.label("bc_ret")
    a.blr()
    a.label("bc_bad")
    a.addi(10, 10, 1).cmpwi(10, 6).blt("bc_c")
    a.blr()                                                         # none clear: P as it was


def bomb_clear_model(P, path, frames, wall=0.0):
    """BOMB CLEAR's spec: path(k) = the ball (x, y, z) k frames from now, frames = min(T or 60, PATH_MAX), wall = the
    game's wall distance (+0x29D8; <= 20: none). -> (C, moved). frsqrte's ~3% ignored (tests allow it)."""
    near_wall = False
    if wall > 20.0:
        for k in range(1, frames + 1):
            x, y, z = path(k)
            if x * x + z * z >= (wall - WALL_IN) ** 2:
                frames, near_wall = k - 1, True
                break

    def clear(cx, cz):
        if near_wall and cx * cx + cz * cz >= (wall - BCLEAR_WALL) ** 2:
            return False
        for k in range(1, frames + 1):
            x, y, z = path(k)
            if y <= BCLEAR_Y and (x - cx) ** 2 + (z - cz) ** 2 < BCLEAR_R ** 2:
                return False
        return True
    px, pz = P
    if px * px + pz * pz < 1.0 or clear(px, pz):
        return (px, pz), False
    n = math.hypot(px, pz)
    ux, uz = px / n, pz / n
    d = BCLEAR_D
    for dx, dz in ((-uz * d, ux * d), (uz * d, -ux * d), (ux * d, uz * d), (-ux * d, -uz * d), (-ux * 2 * d, -uz * 2 * d),
                   (-ux * 3 * d, -uz * 3 * d)):
        c = (px + dx, pz + dz)
        if clear(*c):
            return c, True
    return (px, pz), False


def data_block(dol, logp=0):
    blob = bytearray(RECS)
    struct.pack_into(">I", blob, LOGP, logp)
    struct.pack_into(">2f", blob, SPEEDS, *SPEED6)
    struct.pack_into(">4fQ", blob, KSPOT, SPOT_BACK, WALL_Y, JUMP_D, GATE_IN, 0x4330000080000000)
    for i, deg in enumerate(TURNS):
        struct.pack_into(">2f", blob, ROT + i * 8, math.cos(math.radians(deg)), math.sin(math.radians(deg)))
    struct.pack_into(f">{len(RINGS)}f", blob, RAD, *RINGS)
    struct.pack_into(">2f", blob, KFFE, EDGE_MARGIN + RUNNER_PAD, BANANA_HIT + RUNNER_PAD)
    struct.pack_into(">2f", blob, K12X, *BANANA12)
    struct.pack_into(">5f", blob, KBUDY, BUDDY_Y, BUDDY_R * BUDDY_R, CHASE_GROUND, WALL_IN, IN_AIR_Y)
    struct.pack_into(">2f", blob, KHOPD, HOP_D, BUDDY_CAP)
    struct.pack_into(">f", blob, KL5STEP, L5_STEP)
    struct.pack_into(">f", blob, KLINE, LINE_STEP)
    struct.pack_into(">4f", blob, KBCD, BCLEAR_D, BCLEAR_Y, BCLEAR_R * BCLEAR_R, BCLEAR_WALL)
    for k in range(5):                              # banana k lands at the cursor + spread * (cos, sin)(72 k)
        struct.pack_into(">2f", blob, BAN5 + k * 8, math.cos(math.radians(72 * k)), math.sin(math.radians(72 * k)))
    for s, fx, d, k in records(dol):
        blob += struct.pack(">fifI", s, fx, d, k)
    global L4K, L5K
    L4K = L5K = None
    me = sys.modules[__name__]
    (sp4, sp5, sp6), (pad4, pad5, pad6) = level5.pair(me, "SPEED6"), level5.pair(me, "RUNNER_PAD")
    if sp4 != sp6 or sp5 != sp6 or pad4 != pad6 or pad5 != pad6:
        L4K = len(blob)
        L5K = L4K + 16
        assert L5K + 16 < 0x8000
        blob += struct.pack(">4f", *sp4, EDGE_MARGIN + pad4, BANANA_HIT + pad4)
        blob += struct.pack(">4f", *sp5, EDGE_MARGIN + pad5, BANANA_HIT + pad5)
    return bytes(blob)


def _meet(a, rt, ra, scratch=None):
    """rt = ra - MEET_LEAD, this match's level's (level5.pair). Differing: via rt itself (rt != ra) or `scratch`
    (clobbered, with cr0)."""
    ml4, ml5, ml6 = level5.pair(sys.modules[__name__], "MEET_LEAD")
    if ml4 == ml5 == ml6:
        a.addi(rt, ra, -MEET_LEAD)
    elif rt != ra:
        level5.pick(a, rt, -ml4, -ml5, -ml6).add(rt, rt, ra)
    else:
        level5.pick(a, scratch, -ml4, -ml5, -ml6).add(rt, rt, scratch)


def _extsb(ra, rs):
    return (31 << 26) | (rs << 21) | (ra << 16) | (954 << 1)


FCTIWZ_F1 = (63 << 26) | (1 << 21) | (1 << 11) | (15 << 1)
FSUB_F2_F2_F3 = (63 << 26) | (2 << 21) | (2 << 16) | (3 << 11) | (20 << 1)   # double: int -> float
XORIS_R3 = d_form(27, 3, 3, 0x8000)


def _gate(a, reg, skip, cr=0):
    """Branch to `skip` unless level5.FLAG is 1 or 2 (level 5 or 6; Nick, 2026-09-27: level 5 plays the level 6 items,
    nerfed). Clobbers `reg` and crN."""
    assert cr == 0, "the gate sets cr0"
    level5.gate(a, reg, skip, "cpu-items")


def _data(a, reg):
    a.lis(reg, ha(DATA)).addi(reg, reg, lo(DATA))


def reset_stub(at):
    a = Asm(at)
    _data(a, 12)
    a.li(0, 0).stw(0, ACTIVE, 12)
    _gate(a, 12, "out")
    a.lwz(3, COM, 13).cmpwi(3, 0).beq("out")
    a.lwz(0, 0, 3).lis(12, ha(COM_VTABLE)).addi(12, 12, lo(COM_VTABLE)).cmpw(0, 12).bne("out")
    a.lbz(0, 0x24, 3).word(_extsb(0, 0)).cmpwi(0, 0).blt("out")
    a.lbz(0, 0x26, 3).cmpwi(0, HARDEST).bne("out")
    a.lwz(5, 0x338, 29).cmplwi(5, BOO).ble("id")         # the manager's item; -1 / 6+ -> Shell
    a.li(5, SHELL)
    a.label("id")
    a.stw(5, 0x0C, 3).cmpwi(5, 4).ble("col")
    a.li(5, 4)
    a.label("col")
    a.stb(5, 0x27, 3)
    a.label("out")
    a.word(RESET_ORIG)
    a.b(RESET + 4)
    return a


def _hr_block(a):
    """Home run (the buddy-jump plan, FUN_80125238 plan 8): r3 = T, r4 = the jumper, f1/f2 = his spot -> "common";
    anything else -> "fly" (the cases as before). r12 = the data block on entry."""
    a.lbz(0, 0x2A71, 29).cmpwi(0, 0).beq("hf0")           # heading for the wall
    a.lbz(0, 0x2A79, 29).cmpwi(0, 0).bne("hf1")
    a.lha(0, 0x2A4E, 29).cmpwi(0, 0).bne("hf2")           # not bounced
    a.lbz(0, 0x2A75, 29).cmplwi(0, 1).ble("hr_b")
    a.mr(3, 29).bl(BALLPOS_FN)                            # 2A75 > 1: W + 5 toward the ball
    _data(a, 12)
    a.lfs(1, 0, 3).lfs(2, 8, 3).lfs(3, 0x408, 29).lfs(4, 0x40C, 29)
    a.fsubs(1, 1, 3).fsubs(2, 2, 4).stfs(1, UX, 12).stfs(2, UZ, 12)
    a.fmuls(1, 1, 1).fmadds(1, 2, 2, 1)
    a.lfs(0, EPS, 2).fcmpo(1, 0).ble("hf3")
    a.bl(SQRT_FN)
    _data(a, 12)
    a.lfs(0, KSPOT, 12).fdivs(5, 0, 1).lfs(3, UX, 12).lfs(4, UZ, 12)
    a.b("hr_spot")
    a.label("hr_b")                                       # else: above 3.5 at the wall and landing past it
    a.lha(3, 0x2A4A, 29).cmpwi(3, 0).blt("hr_p8")
    a.cmpwi(3, PATH_MAX).ble("hr_f")
    a.li(3, PATH_MAX)
    a.label("hr_f")
    a.mulli(3, 3, PATH_STEP).add(3, 3, 29).lfs(1, PATH + 4, 3).lfs(0, KWALLY, 12).fcmpo(1, 0).ble("hr_p8")
    a.lfs(1, 0x400, 29).lfs(2, 0x404, 29).fmuls(1, 1, 1).fmadds(1, 2, 2, 1)
    a.lfs(2, 0x29D8, 29).fmuls(2, 2, 2).fcmpo(1, 2).ble("hr_p8")
    a.label("hr_wn")
    a.lfs(5, KSPOT, 12).lfs(3, 0x410, 29).lfs(4, 0x414, 29)   # W + 5 along the wall normal
    a.label("hr_spot")
    a.lfs(1, 0x408, 29).lfs(2, 0x40C, 29).fmadds(1, 3, 5, 1).fmadds(2, 4, 5, 2)
    a.stfs(1, JX, 12).stfs(2, JZ, 12)
    a.li(0, -1).stw(0, BEST, 12).li(0, 0x7FFF).stw(0, BETA, 12).li(0, OUTFIELD[0]).stw(0, LOOP, 12)
    a.li(0, 0x7FFF).stw(0, BETA2, 12).li(0, 0).stw(0, MPTR, 12)      # the runner-up: the teammate coming over
    a.label("hr_loop")                                    # the outfielder who gets to the spot first
    _data(a, 12)
    a.lwz(5, LOOP, 12).slwi(6, 5, 2).lis(7, ha(FIELDERS)).addi(7, 7, lo(FIELDERS)).add(7, 7, 6)
    a.lwz(3, 0x24, 7).cmpwi(3, 0).bne("hr_have")
    a.lwz(3, 0x48, 7).cmpwi(3, 0).bne("hr_have")
    a.lwz(3, 0, 7).cmpwi(3, 0).beq("hr_next")
    a.label("hr_have")
    a.stw(3, CAND, 12).lfs(1, JX, 12).lfs(2, JZ, 12).bl(ETA_FN)
    _data(a, 12)
    a.lwz(0, BETA, 12).cmpw(3, 0).bge("hr_2nd")
    a.lwz(0, BEST, 12).cmpwi(0, 0).blt("hr_1st")          # the old best becomes the runner-up
    a.lwz(0, BETA, 12).stw(0, BETA2, 12).lwz(0, JPTR, 12).stw(0, MPTR, 12)
    a.label("hr_1st")
    a.stw(3, BETA, 12).lwz(0, LOOP, 12).stw(0, BEST, 12).lwz(0, CAND, 12).stw(0, JPTR, 12)
    a.b("hr_next")
    a.label("hr_2nd")
    a.lwz(0, BETA2, 12).cmpw(3, 0).bge("hr_next")
    a.stw(3, BETA2, 12).lwz(0, CAND, 12).stw(0, MPTR, 12)
    a.label("hr_next")
    a.lwz(5, LOOP, 12).addi(5, 5, 1).stw(5, LOOP, 12).cmpwi(5, OUTFIELD[-1]).ble("hr_loop")
    a.lwz(0, BEST, 12).cmpwi(0, 0).blt("hf7")
    a.lwz(3, JPTR, 12).lfs(1, 4, 3).lfs(2, 0xC, 3).lfs(3, JX, 12).lfs(4, JZ, 12)   # his spot: radius toward him
    a.fsubs(1, 1, 3).fsubs(2, 2, 4).stfs(1, UX, 12).stfs(2, UZ, 12).fmuls(1, 1, 1).fmadds(1, 2, 2, 1)
    a.lfs(0, EPS, 2).fcmpo(1, 0).ble("hr_jf")
    a.bl(SQRT_FN)
    _data(a, 12)
    a.lwz(3, JPTR, 12).lfs(0, 0x1C, 3).fdivs(5, 0, 1).lfs(3, UX, 12).lfs(4, UZ, 12)
    a.lfs(1, JX, 12).lfs(2, JZ, 12).fmadds(1, 3, 5, 1).fmadds(2, 4, 5, 2).stfs(1, JX, 12).stfs(2, JZ, 12)
    a.label("hr_jf")
    # HIS OWN SPOT (Nick's 17:40 dump: a Bob-omb aimed at this estimate, 13 m short of the CF's real jump spot, burst
    # after he had run past it): the game's own move target for the jumper (defense_dbg.ROUTE, written by the level 6
    # route hooks every frame he's routed) when it's fresh (this frame or the last): J = that
    if ROUTE_T is not None:
        a.lwz(3, JPTR, 12).lbz(4, 0x21C, 3).cmplwi(4, ROUTE_N - 1).bgt("hr_jo")
        a.load_addr(5, ROUTE_T).mulli(4, 4, ROUTE_SZ).add(5, 5, 4)
        a.lwz(6, PLAYSTATE, 13).cmpwi(6, 0).beq("hr_jo")
        a.lha(6, 2, 6).lwz(7, 8, 5).subf(6, 7, 6).cmplwi(6, 1).bgt("hr_jo")   # now - written in 0..1
        a.lfs(1, 0, 5).stfs(1, JX, 12).lfs(2, 4, 5).stfs(2, JZ, 12)
        a.label("hr_jo")
    # Nick's dump (Bob-omb, 15:56): the 5.0 m jump rule below rejected a real buddy jump ("ball never near the
    # spot", then "nobody gets there first"). With a wall-crossing frame (+0x2A4A): the jump is around it, so
    # T = cross - HR_LEAD (below); no "gets there first" gate. +0x2A4A is an index
    # into the path, which 800B38C8 re-predicts every frame from the ball now (path[0] = now): frames from now, no E.
    # Nick (2026-09-27): T = cross - HR_LEAD (now if that has passed), before any buddy jump; not held for his ETA:
    # still on his way at T, P = where he is then on a straight run from F to J at the rate of his ETA e.
    a.lha(7, 0x2A4A, 29).cmpwi(7, 0).ble("hr_scan")
    # A SHELL / FIREBALL: the jump is the game's own trigger (800E246C: the ball's ground distance to him <= 5.0,
    # 0x8079736C, his partner touching): the first frame k < X the ball is within JUMP_D of J (Nick's 17:23 dump: the
    # BUDDY_Y / BUDDY_R guess below put a Fireball there 47 frames before the jump; his 17:19 dump: the jump 15-18
    # frames before the catch, the ball 15-17 m up); none: X
    a.lwz(0, 0x0C, 30).cmplwi(0, FIRE).bgt("hk_go")
    a.li(5, 1).addi(6, 29, PATH_STEP).lfs(3, JX, 12).lfs(4, JZ, 12).lfs(0, KJUMP, 12).fmuls(0, 0, 0)
    a.label("hj")
    a.cmpw(5, 7).bge("hk_x")
    a.cmpwi(5, PATH_MAX).bgt("hk_x")
    a.lfs(1, PATH, 6).fsubs(1, 1, 3).lfs(2, PATH + 8, 6).fsubs(2, 2, 4).fmuls(1, 1, 1).fmadds(1, 2, 2, 1)
    a.fcmpo(1, 0).ble("hk_y")
    a.addi(5, 5, 1).addi(6, 6, PATH_STEP).b("hj")
    a.label("hk_go")
    # the first frame k < X (k <= PATH_MAX) the ball comes down (y[k] < y[k-1]) to BUDDY_Y within BUDDY_R of J (a
    # buddy catch possible, the jump ~40 frames before it: Nick's 19:14 dump); none: X
    a.li(5, 1).addi(6, 29, PATH_STEP).lfs(3, JX, 12).lfs(4, JZ, 12)
    a.label("hk")
    a.cmpw(5, 7).bge("hk_x")
    a.cmpwi(5, PATH_MAX).bgt("hk_x")
    a.lfs(0, PATH + 4, 6).lfs(1, PATH + 4 - PATH_STEP, 6).fcmpo(0, 1).bge("hk_n")   # not coming down
    a.lfs(1, KBUDY, 12).fcmpo(0, 1).bgt("hk_n")                                    # too high to reach
    a.lfs(1, PATH, 6).fsubs(1, 1, 3).lfs(2, PATH + 8, 6).fsubs(2, 2, 4).fmuls(1, 1, 1).fmadds(1, 2, 2, 1)
    a.lfs(2, KBUDR2, 12).fcmpo(1, 2).ble("hk_y")
    a.label("hk_n")
    a.addi(5, 5, 1).addi(6, 6, PATH_STEP).b("hk")
    a.label("hk_y")
    a.mr(7, 5)
    a.label("hk_x")
    # A SHELL / FIREBALL AT THE WALL (Nick's 16:08 dump: a Shell timed 65 frames before the jump, then the first-hop
    # rule dropped the timer to 0 and it went ~85 frames before the ball got there): the jump itself, less MEET_LEAD,
    # no first-hop rule (that is for the lobbed items, so he doesn't hop out of the blast)
    a.lwz(0, 0x0C, 30).cmplwi(0, FIRE).bgt("hk_lob")
    _meet(a, 3, 7)
    a.b("hk_c")
    a.label("hk_lob")
    a.addi(3, 7, -HR_LEAD)
    _data(a, 12)
    # A BANANA AT THE WALL (Nick's 16:10 dump: timed 65 frames before the jump, it landed ~9 frames after the CF had
    # reached his jump spot and stopped, so he never ran onto it): his arrival at the spot (BETA), so it lands
    # BANANA_EARLY before he gets there; still before the teammate's first hop (below)
    a.lwz(0, 0x0C, 30).cmplwi(0, BANANA).bne("hk_nb")
    # (his arrival: |F - J| / max(+0xE4, +0xEC): his top run speed, or faster as he runs now (a buddy-run outfielder
    # goes up to 2 x +0xEC, the 16:10 dump: 0.236 against 0.122, and +0xE4 shows it once he's running). Not the 2x
    # floor (Nick's 17:15 dump: the RF ran 0.13-0.2, the CF 0.12, and both Bananas landed far too early: a level 6
    # fielder walks around a Banana already down, so an early one is avoided)
    a.lwz(4, JPTR, 12).lfs(1, 4, 4).lfs(3, JX, 12).fsubs(1, 1, 3).lfs(2, 0xC, 4).lfs(3, JZ, 12).fsubs(2, 2, 3)
    a.fmuls(1, 1, 1).fmadds(1, 2, 2, 1)
    a.lfs(0, EPS, 2).fcmpo(1, 0).bgt("hb_q")
    a.lfs(1, ZERO, 2).b("hb_d")
    a.label("hb_q")
    a.bl(SQRT_FN)
    a.label("hb_d")
    _data(a, 12)
    a.lwz(4, JPTR, 12).lfs(2, 0xE4, 4).lfs(3, 0xEC, 4).fcmpo(2, 3).bge("hb_v")
    a.fmr(2, 3)
    a.label("hb_v")
    a.lfs(0, ZERO, 2).fcmpo(2, 0).bgt("hb_s")
    a.lfs(2, -0x75FC, 2)                                  # (speed 0: 1.0, as FUN_801142B8)
    a.label("hb_s")
    a.fdivs(1, 1, 2)
    a.word(FCTIWZ_F1).word(d_form(54, 1, 12, SCR)).lwz(3, SCR + 4, 12)
    a.label("hk_nb")
    # the first hop: before the teammate gets within HOP_D
    a.lwz(4, MPTR, 12).cmpwi(4, 0).beq("hk_c")
    a.stw(3, SF, 12)                                      # (T so far)
    a.lfs(1, 4, 4).lfs(3, JX, 12).fsubs(1, 1, 3).lfs(2, 0xC, 4).lfs(3, JZ, 12).fsubs(2, 2, 3)
    a.fmuls(1, 1, 1).fmadds(1, 2, 2, 1)
    a.lfs(0, EPS, 2).fcmpo(1, 0).bgt("hk_q")
    a.lfs(1, ZERO, 2).b("hk_d")
    a.label("hk_q")
    a.bl(SQRT_FN)                                         # his distance to J
    a.label("hk_d")
    _data(a, 12)
    a.lwz(4, MPTR, 12).lfs(0, KHOPD, 12).fsubs(1, 1, 0)   # less HOP_D
    a.lfs(2, 0xE4, 4).lfs(3, 0xEC, 4).lfs(0, KBUDCAP, 12).fmuls(3, 3, 0).fcmpo(2, 3).bge("hk_v")   # his speed: as he
    a.fmr(2, 3)                                           # runs now, at least the buddy run's 2 x +0xEC (Nick's 20:40
    a.label("hk_v")                                       # dump: the CF closed at 0.24 m/frame, +0xEC 0.122)
    a.lfs(0, ZERO, 2).fcmpo(2, 0).bgt("hk_s")
    a.lfs(2, -0x75FC, 2)
    a.label("hk_s")
    a.fdivs(1, 1, 2)
    a.word(FCTIWZ_F1).word(d_form(54, 1, 12, SCR)).lwz(6, SCR + 4, 12)
    a.addi(6, 6, -HOP_MARGIN).lwz(3, SF, 12)
    a.cmpw(6, 3).bge("hk_c")
    a.mr(3, 6)
    a.label("hk_c")
    a.cmpwi(3, 0).bge("hr_c1")
    a.li(3, 0)
    a.label("hr_c1")
    a.b("hr_eta")
    a.label("hr_scan")                                    # no crossing frame: his jump = the first frame within 5.0
    a.li(5, 1).addi(6, 29, PATH_STEP)                     # from path[1], the next frame
    a.lfs(3, JX, 12).lfs(4, JZ, 12).lfs(0, KJUMP, 12).fmuls(0, 0, 0)
    a.label("hr_fl")
    a.cmpwi(5, PATH_MAX).bgt("hf8")
    a.lfs(1, PATH, 6).lfs(2, PATH + 8, 6).fsubs(1, 1, 3).fsubs(2, 2, 4).fmuls(1, 1, 1).fmadds(1, 2, 2, 1)
    a.fcmpo(1, 0).ble("hr_found")
    a.addi(5, 5, 1).addi(6, 6, PATH_STEP).b("hr_fl")
    a.label("hr_found")                                   # r5 = frames from now to the jump (the path index)
    a.lwz(0, BETA, 12).cmpw(0, 5).bgt("hf9")              # he can't get there first: as before
    a.addi(3, 5, -HR_LEAD)
    a.lwz(0, 0x0C, 30).cmplwi(0, FIRE).bgt("hr_lob")      # a Shell / Fireball: the jump itself, less MEET_LEAD
    _meet(a, 3, 5)
    a.label("hr_lob")
    a.lwz(0, 0x0C, 30).cmplwi(0, BANANA).bne("hr_nb")    # a Banana: his arrival (above)
    a.lwz(3, BETA, 12)
    a.label("hr_nb")
    a.lwz(0, BETA, 12).cmpw(3, 0).bge("hr_eta")           # not before he reaches the spot
    a.mr(3, 0)
    a.label("hr_eta")
    a.lwz(5, 0x0C, 30).cmpwi(5, BOO).bne("hr_go")         # Boo: T = the ball clears the wall
    a.lha(6, 0x2A4A, 29).cmpwi(6, 0).blt("hr_go")
    a.mr(3, 6)                                            # (frames from now, as above)
    a.label("hr_go")                                      # P (Nick's 19:32 dump: a Shell through the plan's spot J
    a.li(0, 0).stb(0, DPATH, 12)                          # missed the CF 5.5 m away): where he is running, as the
    a.lfs(1, JX, 12).stfs(1, UX, 12).lfs(2, JZ, 12).stfs(2, UZ, 12)   # chaser's (stock's aim), capped at J
    a.lwz(4, JPTR, 12).lfs(1, 4, 4).stfs(1, JX, 12).lfs(2, 0xC, 4).stfs(2, JZ, 12)
    a.mr(6, 3).mr(3, 4).b("ch_t0")
    # THE GAME'S OWN BUDDY PLAN (Nick's 17:19 dump: a Shell timed to the ball reaching the ground, ~354, while the LF
    # buddy-jumped off the CF at 313 and caught it at 331, 12.7 m up; our wall-height test said "not a home run"):
    # an outfielder with route plan +0x22C == 8 (FUN_80125238's buddy plan, 800E246C's jump gate) makes it a buddy
    # play at the wall whatever our tests say: W + 5 along the wall normal, as above
    a.label("hr_p8")
    for fid in OUTFIELD:
        a.load_addr(7, FIELDERS + 4 * fid)
        a.lwz(3, 0x24, 7).cmpwi(3, 0).bne(f"p8h{fid}")
        a.lwz(3, 0x48, 7).cmpwi(3, 0).bne(f"p8h{fid}")
        a.lwz(3, 0, 7).cmpwi(3, 0).beq(f"p8n{fid}")
        a.label(f"p8h{fid}")
        a.lbz(0, 0x22C, 3).cmpwi(0, 8).beq("hr_p8y")
        a.label(f"p8n{fid}")
    _data(a, 11)
    a.li(0, 4).stb(0, HRWHY, 11).b("fly")
    a.label("hr_p8y")
    _data(a, 12)
    a.b("hr_wn")
    for k, why in enumerate(HR_WHY_CODES):                # why no buddy-jump plan (the log)
        a.label(f"hf{k}")
        _data(a, 11)
        a.li(0, why).stb(0, HRWHY, 11).b("fly")


def _i2f(a, src, fd):
    """fd = (double) (s32) r`src`, via SCR / MAGIC in the data block at r12. Uses r0, r11, f0."""
    a.word(d_form(27, src, 0, 0x8000))                  # xoris r0,src,0x8000
    a.lis(11, 0x4330).stw(11, SCR, 12).stw(0, SCR + 4, 12)
    a.word(d_form(50, fd, 12, SCR)).word(d_form(50, 0, 12, MAGIC))
    a.word((63 << 26) | (fd << 21) | (fd << 16) | (0 << 11) | (20 << 1))   # fsub fd,fd,f0


def _i2f4(a, src, fd):
    """fd = (double) (s32) r`src`, via SCR / MAGIC in the data block at r4. Uses r0, r11, f0."""
    a.word(d_form(27, src, 0, 0x8000))                  # xoris r0,src,0x8000
    a.lis(11, 0x4330).stw(11, SCR, 4).stw(0, SCR + 4, 4)
    a.word(d_form(50, fd, 4, SCR)).word(d_form(50, 0, 4, MAGIC))
    a.word((63 << 26) | (fd << 21) | (fd << 16) | (0 << 11) | (20 << 1))   # fsub fd,fd,f0


def _fielder_ptr(a, tag):
    """r3 = the fielder object for index r5 (+0x24, then +0x48, then the base table, as stock), or 0. Uses r6, r7."""
    a.slwi(6, 5, 2).lis(7, ha(FIELDERS)).addi(7, 7, lo(FIELDERS)).add(7, 7, 6)
    a.lwz(3, 0x24, 7).cmpwi(3, 0).bne(tag)
    a.lwz(3, 0x48, 7).cmpwi(3, 0).bne(tag)
    a.lwz(3, 0, 7)
    a.label(tag)


def decide_stub(at):
    a = Asm(at)
    _gate(a, 3, "stock")
    a.lbz(3, 0x26, 30).cmpwi(3, HARDEST).bne("stock")
    # Nick: re-pick the target every frame until it fires (the fielder who gets to the ball first changes after a
    # bounce): a level 6 decision (ACTIVE) is made again each frame; the stock fallback keeps its own countdown
    a.lbz(0, 0x28, 30).cmpwi(0, 0).beq("fresh")
    _data(a, 12)
    a.lwz(0, ACTIVE, 12).cmpwi(0, 0).beq("trig")
    a.label("fresh")
    _data(a, 11)
    a.li(0, 0).stb(0, HRWHY, 11).stb(0, LATEFIX, 11)
    a.lwz(5, MANAGER, 13).lbz(6, 0x24, 30).mulli(6, 6, 0xC).add(5, 5, 6)
    a.lbz(0, ARMED, 5).cmpwi(0, 0).beq("wait")            # not armed yet (no ball in play): wait, as stock
    a.lwz(29, BALL, 13)
    a.lwz(3, PLAYSTATE, 13).lha(0, 2, 3).cmpwi(0, 0).bge("elap")   # E = now, in path frames
    a.li(0, 0)
    a.label("elap")
    _data(a, 12)
    a.stw(0, ELAP, 12)
    _hr_block(a)
    # STOCK (Nick, 2026-09-27: "can you not find the original logic"; FUN_80450208 / FUN_80450794, docstring):
    # a catchable fly (not bounced, catch class < 4): the landing point, T = the landing - MEET_LEAD, no target;
    # else the stock chaser FUN_800CDBBC: T = his intercept - MEET_LEAD, P = where he is running, as stock's aim:
    # his spot + his direction (+0x94 / +0x98) * his speed (+0xE4) * T (stock: * the item's lead frames), not past
    # his pickup (path[his intercept]), his spot while he catches / throws (+0x251 1..9). The Boo: T + MEET_LEAD.
    # Nobody (a fly that isn't catchable, no chaser): no item this frame (stock: a random fielder, random timer).
    a.label("fly")
    a.lha(0, 0x2A4E, 29).cmpwi(0, 0).bne("chase")        # bounced: the chaser
    a.mr(3, 29).li(4, -1).bl(CLASS_FN).cmpwi(3, 4).bge("chase")   # won't be caught: the pickup after it drops
    _data(a, 12)
    a.li(0, 1).stb(0, DPATH, 12)
    a.lha(3, 0x2A44, 29).lwz(0, ELAP, 12).subf(3, 0, 3)  # frames to the landing
    a.lwz(0, 0x0C, 30).cmpwi(0, BOO).beq("fl_t")
    _meet(a, 3, 3, scratch=5)                            # (r5: wallk clobbers it next)
    a.label("fl_t")
    a.cmpwi(3, 0).bge("fl_t0")
    a.li(3, 0)
    a.label("fl_t0")
    a.stw(3, CAND, 12).bl("wallk").cmpwi(3, 0).bge("fl_w")    # off the wall in the air: T = that frame
    a.lwz(3, CAND, 12)
    a.label("fl_w")
    # A BANANA ON A FLY (Nick's 16:27 dump: it waited on the landing, then went late at a guess; "the CF caught the
    # ball on the side of the catch radius instead of the center"): the catcher = the fielder who reaches the landing L
    # first, |F - L| / max(+0xE4, BUDDY_CAP x +0xEC) (the fast case, as the wall's Banana); the spot
    # P = L + (F - L) * r / |F - L| (r = his radius +0x1C: the edge of his
    # reach on his side, where he takes it). T: the Shell's catch timing (the landing - MEET_LEAD), the Banana too
    # (Nick, 2026-09-29: "why isn't the banana like the shell timing": timed to his run to P it landed ~40 frames
    # early on a fly he jogged under, he slipped on arrival and still caught it; the game's fielder-vs-Banana test
    # FUN_80117A98 is a distance test on Bananas in the air or down, so one landing by a fielder who waits slips him
    # too), BANANA_EARLY before it as everywhere. Nobody: no item this frame (re-decided each frame)
    # Shell / Fireball / Banana (the edge of his reach; Bob-omb / POW: their blast covers it)
    a.stw(3, CAND, 12)                                    # T (the landing - MEET_LEAD, or the wall frame)
    a.lwz(0, 0x0C, 30).cmplwi(0, BANANA).beq("fb_go").cmplwi(0, FIRE).bgt("fl_nb")
    a.label("fb_go")
    a.li(0, -1).stw(0, BEST, 12).li(0, 0x7FFF).stw(0, BETA, 12).li(0, 0).stw(0, LOOP, 12)
    a.label("fb_l")
    _data(a, 12)
    a.lwz(5, LOOP, 12)
    _fielder_ptr(a, "fb_p")
    a.cmpwi(3, 0).beq("fb_n")
    _data(a, 12)
    a.stw(3, FPTR, 12)
    a.lfs(1, 4, 3).lfs(3, 0x400, 29).fsubs(1, 1, 3).lfs(2, 0xC, 3).lfs(3, 0x404, 29).fsubs(2, 2, 3)
    a.fmuls(1, 1, 1).fmadds(1, 2, 2, 1)
    a.lfs(0, EPS, 2).fcmpo(1, 0).bgt("fb_q")
    a.lfs(1, ZERO, 2).b("fb_d")
    a.label("fb_q")
    a.bl(SQRT_FN)
    a.label("fb_d")
    _data(a, 12)
    a.lwz(3, FPTR, 12).lfs(2, 0xE4, 3).lfs(3, 0xEC, 3).lfs(0, KBUDCAP, 12).fmuls(3, 3, 0).fcmpo(2, 3).bge("fb_v")
    a.fmr(2, 3)
    a.label("fb_v")
    a.lfs(0, ZERO, 2).fcmpo(2, 0).bgt("fb_s")
    a.lfs(2, -0x75FC, 2)                                  # (speed 0: 1.0, as FUN_801142B8)
    a.label("fb_s")
    a.fdivs(1, 1, 2)
    a.word(FCTIWZ_F1).word(d_form(54, 1, 12, SCR)).lwz(6, SCR + 4, 12)
    a.lwz(0, BETA, 12).cmpw(6, 0).bge("fb_n")             # the first to get there
    a.stw(6, BETA, 12).lwz(0, LOOP, 12).stw(0, BEST, 12).lwz(0, FPTR, 12).stw(0, JPTR, 12)
    a.label("fb_n")
    _data(a, 12)
    a.lwz(5, LOOP, 12).addi(5, 5, 1).stw(5, LOOP, 12).cmpwi(5, 8).ble("fb_l")
    a.lwz(4, BEST, 12).cmpwi(4, 0).blt("nomeet")          # nobody
    a.lwz(3, JPTR, 12).lfs(1, 4, 3).lfs(3, 0x400, 29).fsubs(1, 1, 3).lfs(2, 0xC, 3).lfs(3, 0x404, 29).fsubs(2, 2, 3)
    a.stfs(1, UX, 12).stfs(2, UZ, 12).fmuls(1, 1, 1).fmadds(1, 2, 2, 1)
    a.lfs(0, EPS, 2).fcmpo(1, 0).ble("nomeet")
    a.bl(SQRT_FN)                                         # f1 = |F - L|
    _data(a, 12)
    a.lwz(3, JPTR, 12).lfs(4, 0x1C, 3).fsubs(5, 1, 4)     # f5 = |F - P| = |F - L| - r
    a.fdivs(6, 4, 1)                                      # r / |F - L|
    a.lfs(7, 0xE4, 3).lfs(8, 0xEC, 3).fcmpo(7, 8).bge("fb_w")   # his run: max(+0xE4, +0xEC) (as the wall's Banana)
    a.fmr(7, 8)
    a.label("fb_w")
    a.lfs(0, ZERO, 2).fcmpo(7, 0).bgt("fb_x")
    a.lfs(7, -0x75FC, 2)
    a.label("fb_x")
    a.fdivs(5, 5, 7)
    a.word((63 << 26) | (5 << 21) | (5 << 11) | (15 << 1)).word(d_form(54, 5, 12, SCR)).lwz(3, SCR + 4, 12)   # T = his run to P
    a.lfs(1, 0x400, 29).lfs(7, UX, 12).fmadds(1, 7, 6, 1)
    a.lfs(2, 0x404, 29).lfs(7, UZ, 12).fmadds(2, 7, 6, 2)   # P = L + (F - L) * r / |F - L|
    a.stfs(1, LCX, 12).stfs(2, LCZ, 12)                   # (his cap)
    a.lwz(3, CAND, 12)                                    # the catch T (Shell / Fireball / Banana)
    a.label("fb_t")
    a.lwz(4, BEST, 12).li(0, 1).stb(0, 0x2A, 30).b("common")
    a.label("fl_nb")
    a.lfs(1, 0x400, 29).lfs(2, 0x404, 29)
    a.li(0, 1).stb(0, 0x2A, 30).li(4, -1).b("common")
    a.label("chase")                                      # stock's chaser scan without its ready gate (CHASE_STEP)
    _data(a, 12)
    # INSIDE THE PARK (Nick's POW dump: the ball's path runs on past the wall; the CF's pickup went to (35.6, 120),
    # the cursor sat there and it never threw): KW = the first path frame at the wall (|xz| >= +0x29D8 - WALL_IN, in
    # the air or not); the scan and the pickup use path[min(k, KW - 1)]: a ball at the wall is picked up there
    a.li(0, PATH_MAX + 1).stw(0, KW, 12)
    a.lfs(0, 0x29D8, 29).lfs(1, FLY_Y, 2).fcmpo(0, 1).ble("kw_x")    # (no wall known: +0x29D8 <= 20 m)
    a.lfs(1, KWALLIN, 12).fsubs(0, 0, 1).fmuls(0, 0, 0)
    a.li(5, 1).addi(6, 29, PATH_STEP)
    a.label("kw_l")
    a.cmpwi(5, PATH_MAX).bgt("kw_x")
    a.lfs(1, PATH, 6).lfs(2, PATH + 8, 6).fmuls(1, 1, 1).fmadds(1, 2, 2, 1).fcmpo(1, 0).bge("kw_y")
    a.addi(5, 5, 1).addi(6, 6, PATH_STEP).b("kw_l")
    a.label("kw_y")
    a.cmpwi(5, 2).bge("kw_s").li(5, 2)                    # (at least path[1])
    a.label("kw_s")
    a.stw(5, KW, 12)
    a.label("kw_x")
    a.li(0, 9999).stw(0, BETA, 12).li(0, -1).stw(0, BEST, 12).li(0, 0).stw(0, CAND, 12)
    a.label("cs_f")
    _data(a, 12)
    a.lwz(5, CAND, 12)
    _fielder_ptr(a, "cs_p")
    a.cmpwi(3, 0).beq("cs_nf")
    _data(a, 12)
    a.stw(3, FPTR, 12).li(0, 1).stw(0, LOOP, 12)
    a.label("cs_k")
    _data(a, 12)
    a.lwz(5, LOOP, 12).cmpwi(5, CHASE_MAX).bge("cs_nf")
    a.mr(6, 5).cmpwi(6, PATH_MAX).ble("cs_kk")
    a.li(6, PATH_MAX)
    a.label("cs_kk")
    a.lwz(7, KW, 12).addi(7, 7, -1).cmpw(6, 7).ble("cs_kw")   # not past the wall (r7: addi with r0 reads 0)
    a.mr(6, 7)
    a.label("cs_kw")
    a.mulli(6, 6, PATH_STEP).add(6, 6, 29)
    a.lha(0, 0x2A4E, 29).cmpwi(0, 0).bne("cs_any")        # not bounced (a drop-in): points near the ground only
    a.lfs(0, PATH + 4, 6).lfs(1, KGROUND, 12).fcmpo(0, 1).bgt("cs_next")
    a.label("cs_any")
    a.lwz(3, FPTR, 12).lfs(1, PATH, 6).lfs(2, PATH + 8, 6).bl(ETA_FN)
    _data(a, 12)
    a.lwz(4, FPTR, 12).lbz(0, 0x2C9, 4).cmplwi(0, CPU_SLOT).bge("cs_cpu")   # a human: he shakes (x 1 / 1.4)
    a.mulli(3, 3, DASH_NUM).li(0, DASH_DEN).divwu(3, 3, 0)
    a.label("cs_cpu")
    a.lwz(5, LOOP, 12).addi(0, 5, CHASE_SLACK).cmpw(3, 0).bge("cs_next")
    a.lwz(0, BETA, 12).cmpw(3, 0).bge("cs_nf")            # he gets there, not the soonest: the next fielder
    a.stw(3, BETA, 12).lwz(0, CAND, 12).stw(0, BEST, 12).b("cs_nf")
    a.label("cs_next")
    a.lwz(5, LOOP, 12).addi(5, 5, CHASE_STEP).stw(5, LOOP, 12).b("cs_k")
    a.label("cs_nf")
    _data(a, 12)
    a.lwz(5, CAND, 12).addi(5, 5, 1).stw(5, CAND, 12).cmpwi(5, 8).ble("cs_f")
    a.lwz(4, BEST, 12).cmpwi(4, 0).blt("nomeet")
    a.lwz(3, BETA, 12)
    a.li(0, 2).stb(0, DPATH, 12)
    a.stw(3, BETA, 12).stw(4, BEST, 12)                   # his intercept (frames from now), who
    a.mr(5, 3).cmpwi(5, 1).bge("ch_lo")
    a.li(5, 1)
    a.label("ch_lo")
    a.cmpwi(5, PATH_MAX).ble("ch_hi")
    a.li(5, PATH_MAX)
    a.label("ch_hi")
    a.lwz(7, KW, 12).addi(7, 7, -1).cmpw(5, 7).ble("ch_kw")   # his pickup: not past the wall
    a.mr(5, 7)
    a.label("ch_kw")
    a.mulli(5, 5, PATH_STEP).add(5, 5, 29).lfs(1, PATH, 5).lfs(2, PATH + 8, 5)
    a.stfs(1, UX, 12).stfs(2, UZ, 12)                     # his pickup: path[intercept]
    a.lwz(5, BEST, 12)
    _fielder_ptr(a, "ch_f")
    a.cmpwi(3, 0).beq("nomeet")
    _data(a, 12)
    a.stw(3, JPTR, 12).lfs(1, 4, 3).stfs(1, JX, 12).lfs(2, 0xC, 3).stfs(2, JZ, 12)
    a.lwz(6, BETA, 12).lwz(0, 0x0C, 30).cmpwi(0, BOO).beq("ch_t")
    _meet(a, 6, 6, scratch=5)                            # (r5: wallk clobbers it next)
    a.label("ch_t")
    a.stw(6, CAND, 12).bl("wallk").cmpwi(3, 0).blt("ch_nw")   # off the wall in the air: T = that frame
    a.stw(3, CAND, 12)
    a.label("ch_nw")
    a.lwz(6, CAND, 12).lwz(3, JPTR, 12)
    a.cmpwi(6, 0).bge("ch_t0")
    a.li(6, 0)
    a.label("ch_t0")
    a.lfs(0, UX, 12).stfs(0, LCX, 12).lfs(0, UZ, 12).stfs(0, LCZ, 12)   # the cap, for a late re-lead (the POW's
    a.stw(6, CAND, 12)                                    # T                   edge reuses UX / UZ)
    a.lfs(0, ZERO, 2)
    a.lbz(7, 0x251, 3).addi(7, 7, -1).cmplwi(7, 8).ble("ch_l")   # catching / throwing: no lead
    _i2f(a, 6, 4)
    a.lwz(3, JPTR, 12).lfs(3, 0xE4, 3)                   # lead = speed * T
    a.lbz(0, LATEFIX, 12).cmpwi(0, 0).beq("ch_sp")        # the late re-lead (100+ frames): he'll be at full speed
    a.lfs(5, 0xEC, 3).fcmpo(5, 3).ble("ch_sp")            # (Nick's 14:38 dump: the CF was still speeding up, 0.047)
    a.fmr(3, 5)
    a.label("ch_sp")
    a.fmuls(0, 3, 4)
    a.label("ch_l")
    a.stfs(0, SF, 12)
    a.lfs(1, UX, 12).lfs(3, JX, 12).fsubs(1, 1, 3)
    a.lfs(2, UZ, 12).lfs(4, JZ, 12).fsubs(2, 2, 4)
    a.fmuls(1, 1, 1).fmadds(1, 2, 2, 1)
    a.lfs(0, EPS, 2).fcmpo(1, 0).bgt("ch_sq")
    a.lfs(1, ZERO, 2).b("ch_d")
    a.label("ch_sq")
    a.bl(SQRT_FN)
    a.label("ch_d")
    _data(a, 12)
    a.lfs(0, SF, 12).fcmpo(0, 1).ble("ch_lead")           # not past his pickup
    a.lfs(1, UX, 12).lfs(2, UZ, 12).b("ch_go")
    a.label("ch_lead")
    # TOWARD WHERE HE'S GOING (Nick, 2026-09-28, his 16:27 dump: a fielder starting or curving his run pointed 4-5 m off
    # his real line): the lead runs along the line from him to his spot (UX / UZ: his pickup / jump spot), not his
    # heading (+0x94 / +0x98; kept when he's on the spot)
    a.lfs(5, EPS, 2).fcmpo(1, 5).ble("ch_hd")
    a.lfs(3, UX, 12).lfs(5, JX, 12).fsubs(3, 3, 5).fdivs(3, 3, 1)
    a.lfs(4, UZ, 12).lfs(5, JZ, 12).fsubs(4, 4, 5).fdivs(4, 4, 1).b("ch_dir")
    a.label("ch_hd")
    a.lwz(3, JPTR, 12).lfs(3, 0x94, 3).lfs(4, 0x98, 3)
    a.label("ch_dir")
    a.lfs(1, JX, 12).fmadds(1, 3, 0, 1).lfs(2, JZ, 12).fmadds(2, 4, 0, 2)
    a.label("ch_go")
    a.lwz(3, CAND, 12).lwz(4, BEST, 12)
    a.li(0, 0).stb(0, 0x2A, 30).b("common")
    a.label("wallk")                                      # r3 = the first path frame the ball reaches the wall in the
    a.li(3, -1)                                           # air, or -1 (on the ground first). Uses r5, r6, f0..f2
    a.lfs(0, 0x29D8, 29).lfs(1, KWALLIN, 12).fsubs(0, 0, 1).fmuls(0, 0, 0)
    a.li(5, 1).addi(6, 29, PATH_STEP)
    a.label("wk_l")
    a.cmpwi(5, PATH_MAX).bgt("wk_x")
    a.lfs(1, PATH + 4, 6).lfs(2, KGROUNDY, 12).fcmpo(1, 2).ble("wk_x")
    a.lfs(1, PATH, 6).lfs(2, PATH + 8, 6).fmuls(1, 1, 1).fmadds(1, 2, 2, 1).fcmpo(1, 0).bge("wk_y")
    a.addi(5, 5, 1).addi(6, 6, PATH_STEP).b("wk_l")
    a.label("wk_y")
    a.mr(3, 5)
    a.label("wk_x")
    a.blr()
    a.label("nomeet")                                     # nobody: no item this frame
    a.li(0, 0).stb(0, 0x28, 30)
    a.li(3, 3).li(4, 0).bl(LOGFN)
    a.b("wait")
    a.label("common")                                     # r3 = T, r4 = target, f1/f2 = P
    a.lis(11, ha(level5.FLAG)).lbz(11, lo(level5.FLAG), 11)
    a.cmpwi(11, 1).beq("c_err").cmpwi(11, 4).bne("c_go")
    a.label("c_err")
    _data(a, 12)
    a.stw(3, L5SAVE, 12).stw(4, L5SAVE + 4, 12).stfs(1, L5SAVE + 8, 12).stfs(2, L5SAVE + 12, 12)
    a.lwz(0, ACTIVE, 12).cmpwi(0, 0).bne("c_have")        # rolled at the at-bat's first decision
    a.li(0, 0).stw(0, L5T, 12).stw(0, L5X, 12).stw(0, L5Z, 12)
    perf4 = getattr(sys.modules[__name__], "AT4", {}).get("L5_PERFECT", L5_PERFECT)
    t4 = getattr(sys.modules[__name__], "AT4", {}).get("L5_T", L5_T)
    k4 = getattr(sys.modules[__name__], "AT4", {}).get("L5_K", L5_K)
    a.lwz(3, RNG, 13).li(4, 100).bl(RAND_FN)
    level5.pick(a, 11, perf4, L5_PERFECT, L5_PERFECT).cmpw(3, 11).blt("c_have")
    a.lwz(3, RNG, 13)
    level5.pick(a, 4, 2 * t4 + 1, 2 * L5_T + 1, 2 * L5_T + 1).bl(RAND_FN)
    _data(a, 12)
    level5.pick(a, 11, t4, L5_T, L5_T).subf(3, 11, 3).stw(3, L5T, 12)
    for off in (L5X, L5Z):
        a.lwz(3, RNG, 13)
        level5.pick(a, 4, 2 * k4 + 1, 2 * L5_K + 1, 2 * L5_K + 1).bl(RAND_FN)
        _data(a, 12)
        level5.pick(a, 11, k4, L5_K, L5_K).subf(3, 11, 3)
        _i2f(a, 3, 1)
        a.lfs(0, KL5STEP, 12).fmuls(1, 1, 0).stfs(1, off, 12)
    a.label("c_have")
    _data(a, 12)
    a.lwz(3, L5SAVE, 12).lwz(0, L5T, 12).add(3, 3, 0).lwz(4, L5SAVE + 4, 12)
    a.lfs(1, L5SAVE + 8, 12).lfs(0, L5X, 12).fadds(1, 1, 0)
    a.lfs(2, L5SAVE + 12, 12).lfs(0, L5Z, 12).fadds(2, 2, 0)
    a.label("c_go")
    a.stw(4, 8, 1).stb(4, 0x25, 30).li(0, 1).stb(0, 0x28, 30)
    _data(a, 12)
    a.stw(3, TARR, 12)                                    # T, for the Banana's slide in AIM
    a.stfs(1, AIMX, 12).stfs(2, AIMZ, 12).stfs(1, PX, 12).stfs(2, PZ, 12)
    a.lwz(5, 0x0C, 30).cmplwi(5, BOO).ble("item")
    a.li(5, SHELL)
    a.label("item")
    a.lbz(6, HZ, 13).cmplwi(6, 1).ble("hz")
    a.li(6, 1)
    a.label("hz")
    a.lwz(7, MANAGER, 13).lbz(8, 0x24, 30).word(_extsb(8, 8)).cmpwi(8, 0).bge("slot")
    a.li(8, 0)
    a.label("slot")
    a.mulli(8, 8, 0xC).add(7, 7, 8).lbz(7, 0x33D, 7).cmplwi(7, 1).ble("row")
    a.li(7, 1)
    a.label("row")
    a.slwi(6, 6, 1).add(6, 6, 7).mulli(6, 6, 6).add(6, 6, 5).slwi(6, 6, 4).addi(6, 6, RECS).add(11, 12, 6)
    a.stw(11, RECP, 12)
    a.lwz(0, 4, 11).subf(3, 0, 3).stw(3, TSAVE, 12)      # T - fixed
    a.lfs(3, 0, 11).lfs(0, ZERO, 2).fcmpo(3, 0).ble("aim")
    a.cmplwi(5, FIRE).bgt("one_shot")                     # (the Boo's slot row: SHELL; not a shot list)
    a.lwz(6, 0x0C, 30).cmplwi(6, FIRE).bgt("one_shot")
    a.lis(12, ha(SHOTB + SH_PTR)).lwz(12, lo(SHOTB + SH_PTR), 12).cmpwi(12, 0).beq("one_shot")
    a.mr(3, 5).lbz(4, 0x25, 30).word(_extsb(4, 4)).mtctr(12).word(0x4E800421)   # bctrl SHOTS(item, target)
    _data(a, 12)
    a.lwz(11, RECP, 12).cmpwi(3, 0).bne("aim")
    a.li(0, 0).stb(0, 0x28, 30)                           # a Fireball with no clear shot: hold (re-decided next frame)
    a.li(3, 3).li(4, 0).bl(LOGFN)
    a.b("wait")
    a.label("one_shot")
    _data(a, 12)
    a.lwz(11, RECP, 12).lwz(5, 0x0C, 30).cmplwi(5, BOO).ble("os_i").li(5, SHELL)
    a.label("os_i")
    a.mr(3, 5).li(4, 0).bl(ORIGFN)                        # travel: D / speed, D = |P - S|, S = ORIGFN(P)
    _data(a, 12)
    a.stfs(1, SX, 12).stfs(2, SZ, 12).lfs(4, PX, 12).lfs(5, PZ, 12)
    a.fsubs(4, 4, 1).fsubs(5, 5, 2).fmuls(4, 4, 4).fmadds(1, 5, 5, 4)
    a.bl(SQRT_FN)
    _data(a, 12)
    a.lwz(11, RECP, 12).lfs(3, 0, 11).fdivs(1, 1, 3)
    a.word(FCTIWZ_F1).word(d_form(54, 1, 12, SCR)).lwz(0, SCR + 4, 12)
    a.lwz(3, TSAVE, 12).subf(3, 0, 3).stw(3, TSAVE, 12)
    a.label("aim")
    a.lwz(0, 12, 11)
    a.cmpwi(0, KIND_EDGE).beq("edge")
    a.cmpwi(0, KIND_BANANA).beq("banana")
    a.cmpwi(0, KIND_STAY).beq("stay")
    a.b("timer")                                          # KIND_AT: C = P
    a.label("edge")                                       # C = P + dist * unit(cursor - P)
    a.lwz(0, 0x0C, 30).cmpwi(0, BOMB).beq("bomb")         # the Bob-omb: C = P (Nick's 20:11 dump: the CF stood 5.8 m
                                                          # past the predicted spot; the edge left 2.5 m, centred 6)
    a.lfs(1, AIMX, 12).lfs(2, AIMZ, 12).lfs(3, 0x10, 30).lfs(4, 0x14, 30)
    a.fsubs(3, 3, 1).fsubs(4, 4, 2).stfs(3, UX, 12).stfs(4, UZ, 12)
    a.fmuls(1, 3, 3).fmadds(1, 4, 4, 1)
    a.lfs(0, EPS, 2).fcmpo(1, 0).bgt("unit")
    a.lfs(0, ONE, 2).stfs(0, UX, 12).lfs(0, ZERO, 2).stfs(0, UZ, 12).lfs(1, ONE, 2)   # on P: along +x
    a.label("unit")
    a.bl(SQRT_FN)
    _data(a, 12)
    a.lwz(11, RECP, 12).lfs(5, 8, 11).fdivs(5, 5, 1)
    a.lfs(3, UX, 12).lfs(4, UZ, 12).lfs(1, AIMX, 12).lfs(2, AIMZ, 12)
    a.fmadds(1, 3, 5, 1).fmadds(2, 4, 5, 2).stfs(1, AIMX, 12).stfs(2, AIMZ, 12)
    a.lwz(0, 0x0C, 30).cmpwi(0, POW).bne("timer")          # a POW: the most fielders in reach (POWFN)
    a.lbz(3, 0x25, 30).word(_extsb(3, 3)).bl(POWFN)
    _data(a, 12)
    a.lwz(11, RECP, 12)
    a.b("timer")
    a.label("banana")                                     # the 12:00 banana on P (Nick): C = P - spread * BANANA12
    _data(a, 12)
    a.lwz(11, RECP, 12).lfs(5, 8, 11).lfs(3, K12X, 12).lfs(4, K12Z, 12)
    a.lfs(1, PX, 12).fnmsubs(1, 5, 3, 1).stfs(1, AIMX, 12)
    a.lfs(2, PZ, 12).fnmsubs(2, 5, 4, 2).stfs(2, AIMZ, 12)
    a.lwz(3, TSAVE, 12).addi(3, 3, -BANANA_EARLY).stw(3, TSAVE, 12)
    a.b("timer")
    a.label("stay")                                       # Boo: anywhere; stay put
    a.lfs(1, 0x10, 30).stfs(1, AIMX, 12).lfs(2, 0x14, 30).stfs(2, AIMZ, 12)
    a.b("timer")
    a.label("bomb")                                       # BOMB CLEAR: C = P, off the ball's low path
    a.bl("bclr")
    _data(a, 12)
    a.lwz(11, RECP, 12)
    a.b("timer")
    bomb_clear(a)
    a.label("timer")
    # LATE, LOBBED (Nick's 14:38 dump: a Bob-omb planned 14 frames out held 54 frames with its spot off screen, then
    # went at the old spot and burst 40 frames late, 18 m from the CF): a Bob-omb / POW / Banana past its release is
    # re-led for where he will be when it lands / bursts, now + its fixed frames (the lead again with T = those
    # frames, capped at the same spot), so the throw that finally goes (the AIM stub: only at a good spot, re-decided
    # every frame) goes where he'll be. Once a decision; not the fly-ball landing (he waits there) or the Boo.
    a.lwz(3, TSAVE, 12).cmpwi(3, 0).bge("tm_ok")
    # A LATE BANANA HOLDS (Nick, 2026-09-28: it went late at a guess and landed where he wasn't): it can't land
    # before he gets there, so no throw this frame (re-decided each frame: a later play may give it a run to land on)
    a.lwz(0, 0x0C, 30).cmplwi(0, BANANA).bne("tm_nb")
    a.li(0, 0).stb(0, 0x28, 30)
    a.li(3, 3).li(4, 0).bl(LOGFN)
    a.b("wait")
    a.label("tm_nb")
    a.lbz(0, LATEFIX, 12).cmpwi(0, 0).bne("tm_ok")
    a.lbz(0, DPATH, 12).cmpwi(0, 1).beq("tm_ok")
    a.lwz(0, 0x0C, 30).cmpwi(0, BOO).beq("tm_ok")
    a.lwz(11, RECP, 12).lfs(3, 0, 11).lfs(0, ZERO, 2).fcmpo(3, 0).bgt("tm_ok")   # thrown straight: its own timing
    a.li(0, 1).stb(0, LATEFIX, 12)
    a.lfs(1, LCX, 12).stfs(1, UX, 12).lfs(1, LCZ, 12).stfs(1, UZ, 12)
    a.lwz(6, 4, 11).lwz(0, 12, 11).cmpwi(0, KIND_BANANA).bne("tm_b")
    a.addi(6, 6, BANANA_EARLY)
    a.label("tm_b")
    a.lwz(3, JPTR, 12).b("ch_t0")
    a.label("tm_ok")
    a.lfs(1, AIMX, 12).stfs(1, C0X, 12).lfs(1, AIMZ, 12).stfs(1, C0Z, 12)   # C0: the planned C
    # TOO LATE (Nick's table: the item can't hit him in time -> no throw; his 17:47 dump: a Shell thrown with the
    # timer already 0): decide again next frame. The Boo is active over T from now on: it goes now.
    # LATE (Nick, 2026-09-27: "can we throw for all too late cases?"): the timer already past 0 -> throw now, every
    # item (was: no throw past T + LATE_OK); the spot still has to be good (the AIM stub)
    a.lwz(3, TSAVE, 12).cmpwi(3, 0).bge("set")
    a.li(3, 0)
    a.label("set")
    a.stw(3, 0x18, 30).li(0, 1).stw(0, ACTIVE, 12)
    a.lwz(5, MANAGER, 13).lbz(6, 0x24, 30).mulli(6, 6, 0xC).add(5, 5, 6)
    a.li(0, 0).stb(0, 0x3A8, 5)                           # no 10-frame throw countdown (0x804565BC) at level 6
    # cursor speed, in the 3.0 fire gate by the release: max(SPEED6, (|cursor - C| - GATE_IN) / max(timer, 1))
    a.lfs(1, AIMX, 12).lfs(2, AIMZ, 12).lfs(3, 0x10, 30).lfs(4, 0x14, 30)
    a.fsubs(1, 3, 1).fsubs(2, 4, 2).fmuls(1, 1, 1).fmadds(1, 2, 2, 1)
    a.bl(SQRT_FN)
    _data(a, 12)
    a.lfs(0, KGATE, 12).fsubs(1, 1, 0)
    a.lwz(3, 0x18, 30).cmpwi(3, 1).bge("t1")
    a.li(3, 1)
    a.label("t1")
    a.word(XORIS_R3).lis(0, 0x4330).stw(0, SCR, 12).stw(3, SCR + 4, 12)
    a.word(d_form(50, 2, 12, SCR)).word(d_form(50, 3, 12, MAGIC)).word(FSUB_F2_F2_F3).fdivs(1, 1, 2)
    a.lbz(0, HZ, 13).cmplwi(0, 1).ble("hz2")
    a.li(0, 1)
    a.label("hz2")
    a.slwi(0, 0, 2).add(4, 12, 0)
    sp4, sp5, sp6 = level5.pair(sys.modules[__name__], "SPEED6")
    if sp4 != sp6 or sp5 != sp6:                                        # level 5's own speeds, L5K's (r5 is loaded below)
        level5.pick(a, 5, L4K - SPEEDS, L5K - SPEEDS, 0).add(4, 4, 5)
    a.lfs(0, SPEEDS, 4).fcmpo(1, 0).bge("fast")
    a.fmr(1, 0)
    a.label("fast")
    a.stfs(1, CSPEED, 12)
    a.lbz(4, DPATH, 12).lbz(5, HRWHY, 12).slwi(5, 5, 4).add(4, 4, 5).li(3, 1).bl(LOGFN)
    a.b(AIM_CALL)
    a.label("trig")
    a.li(3, 4).li(4, 0).bl(LOGFN)
    a.b(TRIGGERED)
    a.label("wait")                                       # no throw this frame: the stock aim call fires when the timer
    a.li(0, 0x7FFF).stw(0, 0x18, 30)                      # (+0x18) <= 0 (0x804505EC; Nick's 19:32 dump: a "too late"
    a.b(AIM_CALL)                                         # Bob-omb went at a stale cursor 22 frames after the catch)
    a.label("stock")
    a.word(DECIDE_ORIG)
    a.b(DECIDE + 4)
    return a


def _shot_i2f(a, src, fd):
    """fd = (double) (s32) r`src` via DATA's SCR / MAGIC at r30. Uses r0, r11, f0."""
    a.word(d_form(27, src, 0, 0x8000))                  # xoris r0,src,0x8000
    a.lis(11, 0x4330).stw(11, SCR, 30).stw(0, SCR + 4, 30)
    a.word(d_form(50, fd, 30, SCR)).word(d_form(50, 0, 30, MAGIC))
    a.word((63 << 26) | (fd << 21) | (fd << 16) | (0 << 11) | (20 << 1))   # fsub fd,fd,f0


def shots_sub(at):
    """SHOTS(r3 = item: Shell / Fireball, r4 = the target index or -1) -> r3 = 1 (PX / PZ / AIMX / AIMZ / SX / SZ /
    TSAVE / TARR set to the pick) or 0 (a Fireball with no clear shot). Docstring SHOT LIST. A normal call: clobbers
    r0, r3..r12, f0..f13, cr; keeps r14..r31 (r25..r31 saved), f14..f31."""
    a = Asm(at)
    a.stwu(1, -0x40, 1).mflr(0).stw(0, 0x44, 1)
    for k, r in enumerate(range(25, 32)):
        a.stw(r, 0x20 + 4 * k, 1)
    a.load_addr(31, SHOTB)
    _data(a, 30)
    a.mr(29, 3).mr(28, 4)
    a.li(0, 0).stw(0, BOK, 31)
    a.li(26, len(OFF))                                   # candidates: all, or P only (the fly landing, no fielder)
    a.lbz(0, DPATH, 30).cmpwi(0, 1).beq("s_one")
    a.lwz(0, JPTR, 30).cmpwi(0, 0).bne("s_go")
    a.label("s_one")
    a.li(26, 1)
    a.label("s_go")
    a.li(27, 0)
    a.label("s_k")                                       # ---- candidate k = r27
    a.slwi(5, 27, 2).addi(5, 5, K_OFF).lwzx(5, 31, 5).lwz(0, TARR, 30).add(25, 0, 5)   # r25 = t
    a.cmpwi(25, 1).blt("s_next")
    a.cmpwi(27, 0).bne("s_lead")
    a.lfs(1, PX, 30).lfs(2, PZ, 30).b("s_p")             # k = 0: the plan's P
    a.label("s_lead")                                    # his lead for t at max(speed, top), capped at LCX / LCZ
    a.lwz(3, JPTR, 30)
    a.lfs(1, JX, 30).lfs(2, JZ, 30)
    a.lbz(7, 0x251, 3).addi(7, 7, -1).cmplwi(7, 8).ble("s_p")      # catching / throwing: where he is
    a.lfs(3, 0xE4, 3).lfs(4, 0xEC, 3).fcmpo(4, 3).ble("s_sp").fmr(3, 4)
    a.label("s_sp")
    _shot_i2f(a, 25, 4)
    a.fmuls(3, 3, 4)                                     # f3 = lead
    a.lfs(5, LCX, 30).fsubs(5, 5, 1).lfs(6, LCZ, 30).fsubs(6, 6, 2)
    a.fmuls(7, 5, 5).fmadds(7, 6, 6, 7).fmuls(8, 3, 3).fcmpo(8, 7).ble("s_in")
    a.lfs(1, LCX, 30).lfs(2, LCZ, 30).b("s_p")           # past the cap: the cap
    a.label("s_in")                                      # toward his spot (the cap), as the lead code (ch_lead)
    a.stfs(3, WR, 31).stfs(1, CPX, 31).stfs(2, CPZ, 31)  # lead, F
    a.fmr(1, 7).lfs(0, EPS, 2).fcmpo(1, 0).bgt("s_sq2")
    a.lfs(1, CPX, 31).lfs(2, CPZ, 31).b("s_p")          # on the spot: F
    a.label("s_sq2")
    a.bl(SQRT_FN)                                        # f1 = |cap - F|
    a.lfs(3, WR, 31).fdivs(3, 3, 1)                      # lead / |cap - F|
    a.lfs(5, LCX, 30).lfs(1, CPX, 31).fsubs(5, 5, 1).fmadds(1, 5, 3, 1)
    a.lfs(6, LCZ, 30).lfs(2, CPZ, 31).fsubs(6, 6, 2).fmadds(2, 6, 3, 2)
    a.label("s_p")
    a.stfs(1, CPX, 31).stfs(2, CPZ, 31)
    a.mr(3, 29).li(4, 0).bl(ORIGFN)                      # S
    a.stfs(1, CSX, 31).stfs(2, CSZ, 31)
    a.lfs(3, CPX, 31).fsubs(3, 3, 1).lfs(4, CPZ, 31).fsubs(4, 4, 2)
    a.fmuls(1, 3, 3).fmadds(1, 4, 4, 1)
    a.lfs(0, EPS, 2).fcmpo(1, 0).bgt("s_sq").lfs(1, ZERO, 2).b("s_l")
    a.label("s_sq")
    a.bl(SQRT_FN)
    a.label("s_l")
    a.stfs(1, CL, 31)
    # ---- higher up the screen (EXT above): C' = P + unit(P - S) * e, the nearest S' wins
    a.lfs(0, CPX, 31).stfs(0, CAX, 31).lfs(0, CPZ, 31).stfs(0, CAZ, 31)
    a.lfs(0, EPS, 2).fcmpo(1, 0).ble("x_done")
    a.li(0, 0).stw(0, EI, 31)
    a.label("x_k")
    a.lwz(5, EI, 31).slwi(5, 5, 2).add(5, 5, 31).lfs(5, K_EXT, 5)          # f5 = e
    a.lfs(1, CPX, 31).lfs(3, CSX, 31).fsubs(3, 1, 3).lfs(2, CPZ, 31).lfs(4, CSZ, 31).fsubs(4, 2, 4)
    a.lfs(0, CL, 31).fdivs(3, 3, 0).fdivs(4, 4, 0)
    a.fmadds(1, 3, 5, 1).fmadds(2, 4, 5, 2).stfs(1, XCX, 31).stfs(2, XCZ, 31)   # C'
    a.fneg(2, 2).lwz(3, MANAGER, 13).bl(ONSCREEN_FN)
    a.clrlwi(3, 3, 24).cmpwi(3, 0).beq("x_n")                                  # not throwable there
    a.lfs(1, XCX, 31).lfs(2, XCZ, 31).mr(3, 29).li(4, 0).bl(ORIGFN)
    a.stfs(1, XSX, 31).stfs(2, XSZ, 31)                                        # S'
    a.lfs(3, CPX, 31).fsubs(3, 3, 1).lfs(4, CPZ, 31).fsubs(4, 4, 2).fmuls(1, 3, 3).fmadds(1, 4, 4, 1)
    a.lfs(0, EPS, 2).fcmpo(1, 0).ble("x_n")
    a.bl(SQRT_FN)
    a.lfs(0, CL, 31).fcmpo(1, 0).bge("x_n")                                    # not nearer
    a.stfs(1, XL, 31)
    a.lfs(5, XSX, 31).lfs(6, XSZ, 31)
    a.lfs(3, CPX, 31).fsubs(3, 3, 5).lfs(4, CPZ, 31).fsubs(4, 4, 6)            # P - S'
    a.lfs(7, XCX, 31).fsubs(7, 7, 5).lfs(8, XCZ, 31).fsubs(8, 8, 6)            # C' - S'
    a.fmuls(9, 3, 8).fnmsubs(9, 4, 7, 9).fmuls(9, 9, 9)                        # cross^2
    a.fmuls(10, 7, 7).fmadds(10, 8, 8, 10)
    a.lfs(0, K_MISS, 31).fmuls(0, 0, 0).fmuls(0, 0, 10).fcmpo(9, 0).bgt("x_n")   # passes P within EXT_MISS
    for src, dst in ((XSX, CSX), (XSZ, CSZ), (XL, CL), (XCX, CAX), (XCZ, CAZ)):
        a.lwz(0, src, 31).stw(0, dst, 31)
    a.label("x_n")
    a.lwz(5, EI, 31).addi(5, 5, 1).stw(5, EI, 31).cmpwi(5, len(EXT)).blt("x_k")
    a.label("x_done")
    a.lfs(1, CL, 31)
    a.lwz(11, RECP, 30).lfs(3, 0, 11).fdivs(1, 1, 3)
    a.word(FCTIWZ_F1).word(d_form(54, 1, 31, SSCR)).lwz(3, SSCR + 4, 31).stw(3, CTRAV, 31)   # travel frames
    a.lwz(0, 4, 11).subf(0, 0, 25).subf(0, 3, 0).stw(0, CREL, 31).stw(25, CT, 31)   # rel = t - fixed - travel
    a.bl("s_eval").stw(3, CHITS, 31)
    a.cmplwi(29, FIRE).bne("s_cmp")
    a.cmpwi(3, 0).bne("s_next")                          # a Fireball: nobody else hit
    a.label("s_cmp")                                     # better than the best? (valid first, then by item)
    a.lwz(0, BOK, 31).cmpwi(0, 0).beq("s_take")
    a.lwz(3, CREL, 31).lwz(4, BREL, 31)
    a.li(5, 0).cmpwi(3, 0).blt("s_v1").li(5, 1)          # r5 = the candidate is on time
    a.label("s_v1")
    a.li(6, 0).cmpwi(4, 0).blt("s_v2").li(6, 1)          # r6 = the best is
    a.label("s_v2")
    a.cmpw(5, 6).bgt("s_take").blt("s_next")
    a.cmpwi(5, 0).bne("s_both")
    a.cmpw(3, 4).bgt("s_take").b("s_next")               # both late: the least late
    a.label("s_both")
    a.cmplwi(29, FIRE).beq("s_fast")
    a.lwz(3, CHITS, 31).lwz(4, BHITS, 31).cmpw(3, 4).bgt("s_take").blt("s_next")   # Shell: the most hit
    a.label("s_fast")
    a.lwz(3, CTRAV, 31).lwz(4, BTRAV, 31).cmpw(3, 4).bge("s_next")   # the fastest
    a.label("s_take")
    for c_, b_ in ((CPX, BPX), (CPZ, BPZ), (CSX, BSX), (CSZ, BSZ), (CREL, BREL), (CTRAV, BTRAV), (CHITS, BHITS),
                   (CT, BT), (CAX, BAX), (CAZ, BAZ)):
        a.lwz(0, c_, 31).stw(0, b_, 31)
    a.li(0, 1).stw(0, BOK, 31)
    a.label("s_next")
    a.addi(27, 27, 1).cmpw(27, 26).blt("s_k")
    a.li(3, 0).lwz(0, BOK, 31).cmpwi(0, 0).beq("s_out")  # none (a Fireball with no clear shot)
    a.lfs(1, BPX, 31).stfs(1, PX, 30).lfs(2, BPZ, 31).stfs(2, PZ, 30)
    a.lfs(1, BAX, 31).stfs(1, AIMX, 30).lfs(2, BAZ, 31).stfs(2, AIMZ, 30)   # the cursor: C (P, or up the screen)
    a.lfs(1, BSX, 31).stfs(1, SX, 30).lfs(1, BSZ, 31).stfs(1, SZ, 30)
    a.lwz(0, BREL, 31).stw(0, TSAVE, 30).lwz(0, BT, 31).stw(0, TARR, 30)
    a.li(3, 1)
    a.label("s_out")
    for k, r in enumerate(range(25, 32)):
        a.lwz(r, 0x20 + 4 * k, 1)
    a.lwz(0, 0x44, 1).mtlr(0).addi(1, 1, 0x40).blr()
    # ---- s_eval: r3 = how many fielders other than the target the candidate's path(s) meet (a leaf: no calls
    # except _fielder_ptr's inline code; r4..r12, f0..f13 scratch; r25 = t)
    a.label("s_eval")
    a.li(3, 0)
    a.lfs(1, CL, 31).lfs(0, EPS, 2).fcmpo(1, 0).bgt("e_ok").blr()
    a.label("e_ok")
    a.mr(12, 3)                                          # r12 = hits
    a.lwz(11, RECP, 30).lfs(13, 0, 11)                   # f13 = speed
    a.lwz(0, CREL, 31).cmpwi(0, 0).bge("e_rel").li(0, 0)
    a.label("e_rel")
    _shot_i2f(a, 0, 12)                                  # f12 = the release, frames from now (>= 0)
    a.lfs(1, CPX, 31).lfs(2, CSX, 31).fsubs(1, 1, 2).lfs(3, CL, 31).fdivs(1, 1, 3)
    a.lfs(2, CPZ, 31).lfs(4, CSZ, 31).fsubs(2, 2, 4).fdivs(2, 2, 3)   # f1, f2 = u
    a.stfs(1, WX, 31).stfs(2, WZ, 31)
    a.li(10, 0)                                          # r10 = fielder i
    a.label("e_i")
    a.cmpw(10, 28).beq("e_inext")
    a.mr(5, 10)
    _fielder_ptr(a, "e_fp")
    a.cmpwi(3, 0).beq("e_inext")
    a.mr(9, 3)                                           # r9 = him
    # his run: V = direction * speed (+0x94 / +0x98, +0xE4); at the arrival (rel + L / speed) near P: the catcher
    a.lfs(5, 0x94, 9).lfs(6, 0x98, 9).lfs(0, 0xE4, 9).fmuls(5, 5, 0).fmuls(6, 6, 0)   # f5, f6 = V
    a.lfs(0, CL, 31).fdivs(0, 0, 13).fadds(0, 0, 12)     # f0 = arrival
    a.lfs(7, 4, 9).fmadds(7, 5, 0, 7).lfs(8, CPX, 31).fsubs(7, 7, 8)
    a.lfs(8, 0xC, 9).fmadds(8, 6, 0, 8).lfs(9, CPZ, 31).fsubs(8, 8, 9)
    a.fmuls(7, 7, 7).fmadds(7, 8, 8, 7).lfs(8, K_CATCH, 31).fmuls(8, 8, 8).fcmpo(7, 8).blt("e_inext")
    a.li(8, 0)                                           # r8 = path 0 .. (3 for a Fireball, 1 for a Shell)
    a.label("e_p")
    a.lfs(1, WX, 31).lfs(2, WZ, 31).lfs(11, K_RANGE, 31)
    a.cmpwi(8, 0).bne("e_side")
    a.cmplwi(29, FIRE).bne("e_path")
    a.lfs(11, CL, 31).b("e_path")                        # the middle Fireball stops at the target
    a.label("e_side")                                    # u turned +-FIRE_SPREAD
    a.lfs(3, K_COS, 31).lfs(4, K_SIN, 31)
    a.cmpwi(8, 2).bne("e_rot").fneg(4, 4)
    a.label("e_rot")
    a.fmuls(9, 1, 3).fnmsubs(9, 2, 4, 9).fmuls(10, 1, 4).fmadds(10, 2, 3, 10)   # (ux c - uz s, ux s + uz c)
    a.fmr(1, 9).fmr(2, 10)
    a.label("e_path")                                    # f1, f2 = w; f11 = its range
    a.lfs(3, 4, 9).lfs(4, CSX, 31).fsubs(3, 3, 4).lfs(4, 0xC, 9).lfs(0, CSZ, 31).fsubs(4, 4, 0)   # F - S
    a.fmuls(0, 3, 1).fmadds(0, 4, 2, 0)                  # s0 = (F - S) . w
    a.fdivs(0, 0, 13).fadds(0, 0, 12)                    # tau: when it passes him
    a.fmadds(3, 5, 0, 3).fmadds(4, 6, 0, 4)              # (F + V tau) - S
    a.fmuls(0, 3, 1).fmadds(0, 4, 2, 0)                  # s
    a.lfs(9, ZERO, 2).fcmpo(0, 9).ble("e_pnext").fcmpo(0, 11).bge("e_pnext")
    a.fmuls(0, 3, 2).fnmsubs(0, 4, 1, 0)                 # d = (x wz - z wx)
    a.word((63 << 26) | (0 << 21) | (0 << 11) | (264 << 1))   # fabs f0
    a.lfs(9, K_HIT, 31).fcmpo(0, 9).bge("e_pnext")
    a.addi(12, 12, 1).b("e_inext")                       # hit (once per fielder)
    a.label("e_pnext")
    a.addi(8, 8, 1)
    a.cmplwi(29, FIRE).bne("e_inext")
    a.cmpwi(8, 3).blt("e_p")
    a.label("e_inext")
    a.addi(10, 10, 1).cmpwi(10, 9).blt("e_i")
    a.mr(3, 12).blr()
    return a


def shot_block():
    blob = bytearray(SHOTB_SIZE)
    struct.pack_into(">5f", blob, K_HIT, HIT_R, RANGE, CATCH_R, math.cos(math.radians(FIRE_SPREAD)),
                     math.sin(math.radians(FIRE_SPREAD)))
    struct.pack_into(f">{len(OFF)}i", blob, K_OFF, *OFF)
    struct.pack_into(f">{len(EXT)}f", blob, K_EXT, *EXT)
    struct.pack_into(">f", blob, K_MISS, EXT_MISS)
    return bytes(blob)


def apply_shots(dol, code):
    """The SHOTS routine in `code` (charbuild: its own section) and its pointer in SHOTB. Needs apply() first."""
    assert SHOTB is not None, "cpu_items.apply first"
    at = code.here + (-code.here % 4)
    blob = shots_sub(at).assemble()
    assert code.put(blob, align=4) == at
    try:                                                   # (charbuild: the data section is in the DOL by now;
        cur = dol.u32(SHOTB + SH_PTR)                      # a test maps its own data and writes the pointer)
    except KeyError:
        cur = None
    if cur is not None:
        assert cur == 0, f"SHOTB pointer already 0x{cur:08X}"
        dol.w32(SHOTB + SH_PTR, at)
    return [f"cpu items shot list (Shell / Fireball): SHOTS 0x{at:08X} ({len(blob)} B), block 0x{SHOTB:08X}"]


def pow_sub(at):
    """POWFN(r3 = the target index or -1): AIMX / AIMZ = the POW's burst centre with the most other fielders in reach
    (docstring THE MOST FIELDERS IN A POW), starting from the edge C already in AIMX / AIMZ. A normal call: clobbers
    r0, r3..r12, f0..f13, cr; keeps r14..r31 (r26..r31 saved), f14..f31."""
    a = Asm(at)
    a.stwu(1, -0x40, 1).mflr(0).stw(0, 0x44, 1)
    for k, r in enumerate(range(26, 32)):
        a.stw(r, 0x20 + 4 * k, 1)
    a.load_addr(31, POWB)
    _data(a, 30)
    a.mr(29, 3)
    a.lwz(11, RECP, 30).lfs(0, 8, 11).stfs(0, PD, 31)                  # D
    a.lwz(3, TARR, 30).cmpwi(3, 0).bge("p_t").li(3, 0)
    a.label("p_t")
    a.mr(12, 30)
    _i2f(a, 3, 1)
    a.stfs(1, PT, 31)                                                  # T (frames from now)
    a.li(28, 0)
    a.label("j_loop")                                                  # ---- Q_j, R_j
    a.cmpw(28, 29).beq("j_skip")
    a.mr(5, 28)
    _fielder_ptr(a, "pj_fp")
    a.cmpwi(3, 0).beq("j_skip")
    a.mr(27, 3)
    a.lbz(4, 0x21C, 27).cmplwi(4, ROUTE_N - 1).bgt("j_head")          # his own move target, fresh?
    a.load_addr(5, ROUTE_T).mulli(4, 4, ROUTE_SZ).add(5, 5, 4)
    a.lwz(6, PLAYSTATE, 13).cmpwi(6, 0).beq("j_head")
    a.lha(6, 2, 6).lwz(7, 8, 5).subf(6, 7, 6).cmplwi(6, 1).bgt("j_head")
    a.lfs(1, 0, 5).lfs(3, 4, 27).fsubs(1, 1, 3).stfs(1, PTX, 31)
    a.lfs(2, 4, 5).lfs(3, 0xC, 27).fsubs(2, 2, 3).stfs(2, PTZ, 31)
    a.fmuls(1, 1, 1).fmadds(1, 2, 2, 1).lfs(0, EPS, 2).fcmpo(1, 0).ble("j_at")
    a.bl(SQRT_FN)                                                      # f1 = d, to his target
    a.lfs(3, 0xE4, 27).lfs(4, 0xEC, 27).fcmpo(4, 3).ble("j_s").fmr(3, 4)
    a.label("j_s")
    a.lfs(0, PT, 31).fmuls(3, 3, 0).fcmpo(3, 1).bge("j_arr")          # s = max(E4, EC) * T; there by T
    a.fdivs(3, 3, 1)
    a.lfs(1, PTX, 31).lfs(4, 4, 27).fmadds(1, 1, 3, 4).lfs(2, PTZ, 31).lfs(5, 0xC, 27).fmadds(2, 2, 3, 5)
    a.b("j_store")
    a.label("j_arr")
    a.lfs(1, PTX, 31).lfs(3, 4, 27).fadds(1, 1, 3).lfs(2, PTZ, 31).lfs(3, 0xC, 27).fadds(2, 2, 3)
    a.b("j_store")
    a.label("j_at")
    a.lfs(1, 4, 27).lfs(2, 0xC, 27).b("j_store")
    a.label("j_head")                                                  # no target: his heading at +0xE4
    a.lfs(0, 0xE4, 27).lfs(3, PT, 31).fmuls(0, 0, 3)
    a.lfs(1, 0x94, 27).lfs(4, 4, 27).fmadds(1, 1, 0, 4).lfs(2, 0x98, 27).lfs(5, 0xC, 27).fmadds(2, 2, 0, 5)
    a.label("j_store")
    a.slwi(6, 28, 2).add(6, 6, 31).stfs(1, PQX, 6).stfs(2, PQZ, 6)
    a.lfs(0, PD, 31).lfs(3, 0x1C, 27).fadds(0, 0, 3).stfs(0, PRJ, 6).b("j_next")
    a.label("j_skip")
    a.slwi(6, 28, 2).add(6, 6, 31).lfs(0, ONE, 2).fneg(0, 0).stfs(0, PRJ, 6)
    a.label("j_next")
    a.addi(28, 28, 1).cmpwi(28, 9).blt("j_loop")
    # ---- the candidates: the edge C (AIMX / AIMZ), P, then one per fielder
    a.lfs(1, AIMX, 30).lfs(2, AIMZ, 30).stfs(1, PBX, 31).stfs(2, PBZ, 31).bl("p_cnt").mr(26, 3)
    a.lfs(1, PX, 30).lfs(2, PZ, 30).bl("p_cnt").cmpw(3, 26).ble("c_j")
    a.mr(26, 3).lfs(1, PX, 30).stfs(1, PBX, 31).lfs(2, PZ, 30).stfs(2, PBZ, 31)
    a.label("c_j")
    a.li(28, 0)
    a.label("cj_loop")
    a.slwi(6, 28, 2).add(6, 6, 31).lfs(0, PRJ, 6).lfs(3, ZERO, 2).fcmpo(0, 3).blt("cj_next")
    a.stfs(0, PTR, 31)
    a.lfs(1, PQX, 6).lfs(3, PX, 30).fsubs(1, 1, 3).stfs(1, PTX, 31)
    a.lfs(2, PQZ, 6).lfs(3, PZ, 30).fsubs(2, 2, 3).stfs(2, PTZ, 31)
    a.fmuls(1, 1, 1).fmadds(1, 2, 2, 1).lfs(0, EPS, 2).fcmpo(1, 0).ble("cj_next")   # on P: P's candidate
    a.bl(SQRT_FN)                                                      # f1 = L
    a.lfs(0, PD, 31).lfs(3, PTR, 31).fadds(4, 0, 3).fcmpo(1, 4).bgt("cj_next")   # too far for both
    a.fsubs(5, 1, 3).lfs(6, ZERO, 2).fcmpo(5, 6).bge("cj_lo").fmr(5, 6)
    a.label("cj_lo")                                                   # f5 = max(0, L - R_j)
    a.fmr(7, 1).fcmpo(0, 7).bge("cj_hi").fmr(7, 0)
    a.label("cj_hi")                                                   # f7 = min(D, L)
    a.fadds(5, 5, 7).lfs(6, PHALF, 31).fmuls(5, 5, 6).fdivs(5, 5, 1)  # a / L
    a.lfs(1, PTX, 31).lfs(3, PX, 30).fmadds(1, 1, 5, 3).lfs(2, PTZ, 31).lfs(3, PZ, 30).fmadds(2, 2, 5, 3)
    a.stfs(1, PCX, 31).stfs(2, PCZ, 31)
    a.bl("p_cnt").cmpw(3, 26).ble("cj_next")
    a.mr(26, 3).lfs(1, PCX, 31).stfs(1, PBX, 31).lfs(2, PCZ, 31).stfs(2, PBZ, 31)
    a.label("cj_next")
    a.addi(28, 28, 1).cmpwi(28, 9).blt("cj_loop")
    a.lfs(1, PBX, 31).stfs(1, AIMX, 30).lfs(2, PBZ, 31).stfs(2, AIMZ, 30).stw(26, PBEST, 31)
    for k, r in enumerate(range(26, 32)):
        a.lwz(r, 0x20 + 4 * k, 1)
    a.lwz(0, 0x44, 1).mtlr(0).addi(1, 1, 0x40).blr()
    # ---- p_cnt: f1, f2 = C -> r3 = how many j (R_j >= 0) have |C - Q_j| <= R_j (a leaf: r4, r5, f0, f3, f4)
    a.label("p_cnt")
    a.li(3, 0).li(4, 0).mr(5, 31)
    a.label("pc_l")
    a.lfs(0, PRJ, 5).lfs(3, ZERO, 2).fcmpo(0, 3).blt("pc_n")
    a.lfs(3, PQX, 5).fsubs(3, 1, 3).lfs(4, PQZ, 5).fsubs(4, 2, 4).fmuls(3, 3, 3).fmadds(3, 4, 4, 3)
    a.fmuls(0, 0, 0).fcmpo(3, 0).bgt("pc_n")
    a.addi(3, 3, 1)
    a.label("pc_n")
    a.addi(5, 5, 4).addi(4, 4, 1).cmpwi(4, 9).blt("pc_l")
    a.blr()
    return a


def pow_best(P, D, edge, T, fielders, target, route=None):
    """The spec for POWFN: fielders {j: (x, z, radius, heading x, heading z, E4, EC)}; route {j: (x, z)} fresh move
    targets. -> (C, count). f32 as the stub."""
    F = f32
    q = {}
    t = F(max(T, 0))
    for j, (x, z, r, hx, hz, e4, ec) in fielders.items():
        if j == target:
            continue
        if route and j in route:
            tx, tz = F(route[j][0] - x), F(route[j][1] - z)
            d2 = F(F(tx * tx) + F(tz * tz))
            if d2 <= 1e-4:
                Q = (x, z)
            else:
                d = F(math.sqrt(d2))
                s = F(F(max(e4, ec)) * t)
                Q = (F(x + tx), F(z + tz)) if s >= d else (F(tx * F(s / d) + x), F(tz * F(s / d) + z))
        else:
            m = F(e4 * t)
            Q = (F(hx * m + x), F(hz * m + z))
        q[j] = (Q, F(D + r))

    def count(c):
        return sum(1 for Q, R in q.values() if F(F((c[0] - Q[0]) ** 2) + F((c[1] - Q[1]) ** 2)) <= F(R * R))
    best, n = edge, count(edge)
    if count(P) > n:
        best, n = P, count(P)
    for j in range(9):
        if j not in q:
            continue
        Q, R = q[j]
        lx, lz = F(Q[0] - P[0]), F(Q[1] - P[1])
        l2 = F(F(lx * lx) + F(lz * lz))
        if l2 <= 1e-4:
            continue
        L = F(math.sqrt(l2))
        if L > F(D + R):
            continue
        a = F(F(F(max(F(L - R), 0.0)) + F(min(D, L))) * 0.5)
        k = F(a / L)
        c = (F(lx * k + P[0]), F(lz * k + P[1]))
        if count(c) > n:
            best, n = c, count(c)
    return best, n


def aim_stub(at):
    a = Asm(at)
    _gate(a, 4, "stock")
    a.lbz(4, 0x26, 30).cmpwi(4, HARDEST).bne("stock")
    a.lbz(4, 0x28, 30).cmpwi(4, 0).beq("stock")
    _data(a, 4)
    a.lwz(0, ACTIVE, 4).cmpwi(0, 0).beq("stock")
    a.li(0, 0).stb(0, HELD, 4)
    # a human's cursor can't go off screen or past the walls: C bad -> the first good spot of C0 turned around P by
    # TURNS at RINGS of its distance (kept while good), else P. Only r30 / r31 / f29..f31 / the frame are live here
    # (0x80450A6C on reloads); LR is in FUN_80450794's frame.
    a.bl("goodq").cmpwi(3, 1).beq("on")
    # a Shell keeps going past the cursor (Nick): any good spot on the line S -> P sends it through P at the same
    # time (Nick's dump: at a home run the wall was off screen, the item was thrown at a spot 10 m short)
    _data(a, 4)                                           # items that travel in a line (the Shell, the Fireball:
    a.lwz(11, RECP, 4).lfs(1, 0, 11).lfs(0, ZERO, 2).fcmpo(1, 0).ble("sh_no")   # record speed > 0)
    a.li(0, 1).stw(0, SI, 4)
    a.label("sh_loop")
    _data(a, 4)
    a.lwz(6, SI, 4)
    _i2f4(a, 6, 5)
    a.lfs(0, KLINE, 4).fmuls(5, 5, 0).stfs(5, SF, 4)      # f = j * LINE_STEP of the way from P back to S
    a.lfs(1, PX, 4).lfs(2, PZ, 4).lfs(3, SX, 4).lfs(4, SZ, 4)   # S = ORIGFN(P) (DECIDE, this frame)
    a.fsubs(6, 3, 1).fmadds(1, 6, 5, 1).fsubs(7, 4, 2).fmadds(2, 7, 5, 2)
    a.lwz(3, 0x0C, 30).cmplwi(3, BOO).ble("sh_it")        # the start moves with the spot: S' = ORIGFN(that spot),
    a.li(3, SHELL)                                        # the spot again on S' -> P
    a.label("sh_it")
    a.li(4, 0).bl(ORIGFN)
    _data(a, 4)
    a.lfs(5, SF, 4).lfs(3, PX, 4).lfs(4, PZ, 4)
    a.fsubs(6, 1, 3).fmadds(1, 6, 5, 3).fsubs(7, 2, 4).fmadds(2, 7, 5, 4).stfs(1, AIMX, 4).stfs(2, AIMZ, 4)
    a.bl("goodq").cmpwi(3, 1).beq("on")
    _data(a, 4)
    a.lwz(6, SI, 4).addi(6, 6, 1).stw(6, SI, 4).cmpwi(6, LINE_TRIES).ble("sh_loop")
    a.label("sh_no")
    # a Banana (Nick: missed on a home run): turning the cursor around P moves the leader off B. First try the
    # cursor spots that land banana k = 1..4 on B instead: B - spread * (cos, sin)(72 k), B = C0 + (spread, 0).
    _data(a, 4)
    a.lwz(11, RECP, 4).lwz(0, 12, 11).cmpwi(0, KIND_BANANA).bne("ring0")
    a.li(0, 0).stw(0, SI, 4)
    a.label("bn5")
    _data(a, 4)
    a.lwz(6, SI, 4).slwi(6, 6, 3).add(6, 4, 6).lfs(6, BAN5, 6).lfs(7, BAN5 + 4, 6)
    a.lwz(11, RECP, 4).lfs(5, 8, 11)
    a.lfs(3, K12X, 4).lfs(1, C0X, 4).fmadds(1, 5, 3, 1).lfs(3, K12Z, 4).lfs(2, C0Z, 4).fmadds(2, 5, 3, 2)   # B
    a.fnmsubs(1, 5, 6, 1).fnmsubs(2, 5, 7, 2).stfs(1, AIMX, 4).stfs(2, AIMZ, 4)
    a.bl("goodq").cmpwi(3, 1).beq("on")
    _data(a, 4)
    a.lwz(6, SI, 4).addi(6, 6, 1).stw(6, SI, 4).cmpwi(6, 5).blt("bn5")
    a.b("hold")                                           # Nick's dump (banana, 16:18): the slide threw
                                                          # 2.7 s early where he had been; hold instead
    a.label("ring0")
    _data(a, 4)
    a.li(0, 0).stw(0, SK, 4)
    a.label("ring")
    a.li(0, 0).stw(0, SI, 4)
    a.label("dir")
    _data(a, 4)
    a.lwz(5, SK, 4).slwi(5, 5, 2).add(5, 4, 5).lfs(5, RAD, 5)
    a.lwz(6, SI, 4).slwi(6, 6, 3).add(6, 4, 6).lfs(6, ROT, 6).lfs(7, ROT + 4, 6)
    a.lfs(1, C0X, 4).lfs(3, PX, 4).fsubs(1, 1, 3).lfs(2, C0Z, 4).lfs(4, PZ, 4).fsubs(2, 2, 4)
    a.lwz(0, 0x0C, 30).cmpwi(0, BOMB).bne("r_nb")         # the Bob-omb, centred (C0 = P): the ring at its reach
    a.lwz(11, RECP, 4).lfs(1, 8, 11).lfs(2, ZERO, 2)      # (6 - EDGE_MARGIN; Nick's 20:23 dump: only P was tried)
    a.label("r_nb")
    a.fmuls(8, 1, 6).fnmsubs(8, 2, 7, 8)                  # dx cos - dz sin
    a.fmuls(9, 1, 7).fmadds(9, 2, 6, 9)                   # dx sin + dz cos
    a.fmadds(1, 8, 5, 3).fmadds(2, 9, 5, 4).stfs(1, AIMX, 4).stfs(2, AIMZ, 4)
    a.bl("goodq").cmpwi(3, 1).beq("on")
    _data(a, 4)
    a.lwz(6, SI, 4).addi(6, 6, 1).stw(6, SI, 4).cmpwi(6, len(TURNS)).blt("dir")
    a.lwz(5, SK, 4).addi(5, 5, 1).stw(5, SK, 4).cmpwi(5, len(RINGS)).blt("ring")
    a.label("in_no")
    _data(a, 4)
    a.lfs(1, PX, 4).stfs(1, AIMX, 4).lfs(1, PZ, 4).stfs(1, AIMZ, 4)
    a.bl("goodq").cmpwi(3, 1).beq("on")
    a.cmpwi(3, 2).bne("n_scr")
    a.li(31, 0).b("on")                                   # P would hit our own runner too: no throw this frame
    a.label("hold")                                       # a Banana with no good spot: head for C0, hold
    _data(a, 4)
    a.lfs(1, C0X, 4).stfs(1, AIMX, 4).lfs(1, C0Z, 4).stfs(1, AIMZ, 4)
    a.label("n_scr")                                      # the spot off screen (Nick: a home run, off the top): the cursor
    _data(a, 4)                                           # steps toward it only while it stays on screen, else holds;
    a.li(31, 0)                                           # never a throw at a spot that isn't good (Nick's dumps)
    a.lfs(1, AIMX, 4).lfs(3, 0x10, 30).fsubs(1, 1, 3).stfs(1, UX, 4)
    a.lfs(2, AIMZ, 4).lfs(3, 0x14, 30).fsubs(2, 2, 3).stfs(2, UZ, 4)
    a.fmuls(1, 1, 1).fmadds(1, 2, 2, 1).lfs(0, EPS, 2).fcmpo(1, 0).ble("on")
    a.bl(SQRT_FN)
    _data(a, 4)
    a.lfs(0, CSPEED, 4).fcmpo(1, 0).bge("n_d")            # step = min(speed, distance)
    a.fmr(0, 1)
    a.label("n_d")
    a.fdivs(5, 0, 1).lfs(3, UX, 4).lfs(4, UZ, 4).lfs(1, 0x10, 30).lfs(2, 0x14, 30)
    a.fmadds(1, 3, 5, 1).fmadds(2, 4, 5, 2).fneg(2, 2).bl(ONSTEPFN)   # the step: on screen only (Nick's 19:21
    a.cmpwi(3, 0).bne("on")                               # dump: the bases aren't throwable, the cursor crosses them)
    a.lfs(1, 0x10, 30).lfs(2, 0x14, 30).fneg(2, 2).bl(ONSTEPFN)   # the cursor itself off screen (the camera moved
    a.cmpwi(3, 0).beq("back_in")                          # away: Nick's 19:21 dump, stranded by 2nd): back in
    _data(a, 4)
    a.li(31, 0).li(0, 1).stb(0, HELD, 4)                 # hold at the edge, no throw this frame
    a.lfs(2, 0x10, 30).lfs(3, 0x14, 30).b("tgt")
    a.label("back_in")                                    # toward the ball on the ground (the camera follows it), not
    a.lwz(3, BALL, 13).lfs(2, PATH, 3).lfs(3, PATH + 8, 3)   # the target (Nick's 20:17 dump: the Bob-omb cursor followed
    _data(a, 4)                                           # its off-screen target out and sat there)
    a.li(31, 0).b("tgt")                                  # (no throw this frame)
    a.label("on")
    _data(a, 4)
    a.lfs(2, AIMX, 4).lfs(3, AIMZ, 4)
    a.label("tgt")                                        # f2 / f3 = where the cursor heads this frame
    a.lfs(1, 0x10, 30).lfs(0, 0x14, 30)                   # the cursor again (the calls took f0 / f1)
    a.fsubs(30, 2, 1).fsubs(29, 3, 0)
    a.lfs(1, CSPEED, 4)                                   # set at the decision
    a.fmuls(31, 31, 1)
    a.lbz(5, HELD, 4).lbz(6, QRES, 4).slwi(5, 5, 1).slwi(6, 6, 2).clrlwi(4, 31, 31).add(4, 4, 5).add(4, 4, 6)
    a.li(3, 5).bl(LOGFN)                                  # (the log keeps f29..f31, r30, r31)
    if LOG_ENTRIES:                                       # the target fielder's real spot this frame (type 8)
        a.lbz(5, 0x25, 30).cmplwi(5, 8).bgt("nof").li(4, 0).bl(FLOGFN)
        a.label("nof")
    a.b(AIM_BACK)
    a.label("stock")
    a.word(AIM_ORIG)
    a.b(AIM + 4)
    _goodq(a)
    return a


def _goodq(a):
    """Subroutine "goodq": is C (AIMX / AIMZ) a good spot? r3 = 1 good, 0 not throwable (FUN_804570C8), 2 a Bob-omb /
    POW / Banana there would reach one of our runners on the field (+0x176) anywhere on his path: from where he is
    to his to-base (+0x17E) when advancing (+0x183 1), to his from-base (+0x17D) when retreating (3), or where he
    stands. Returns r4 = the data block; uses r0, r3, r5..r7, r11, f0..f13 and the SUBLR slot."""
    a.label("goodq")
    a.mflr(0)
    _data(a, 4)
    a.stw(0, SUBLR, 4)
    a.lfs(1, AIMX, 4).lfs(2, AIMZ, 4).fneg(2, 2).lwz(3, MANAGER, 13).bl(ONSCREEN_FN)
    a.clrlwi(3, 3, 24).cmpwi(3, 0).beq("q0")
    _data(a, 4)
    a.lwz(11, RECP, 4).lwz(0, 12, 11)
    pad4, pad5, pad6 = level5.pair(sys.modules[__name__], "RUNNER_PAD")
    kb = 4
    if pad4 != pad6 or pad5 != pad6:                                      # level 5's own pads, L5K's (r3 is loaded after q_r)
        level5.pick(a, 3, L4K + 8 - KFFE, L5K + 8 - KFFE, 0).add(3, 3, 4)
        kb = 3
    a.cmpwi(0, KIND_EDGE).bne("q_nb")
    a.lfs(5, KFFE, kb).b("q_r")
    a.label("q_nb")
    a.cmpwi(0, KIND_BANANA).bne("q1")
    a.lfs(5, KFFB, kb)
    a.label("q_r")                                        # (reach + pad)^2
    a.lfs(0, 8, 11).fadds(5, 5, 0).fmuls(5, 5, 5).stfs(5, KR2, 4)
    a.lwz(3, 0x18, 30).lwz(0, 4, 11).add(3, 3, 0).cmpwi(3, 0).bge("q_k")   # frames until it goes off
    a.li(3, 0)
    a.label("q_k")
    a.word(XORIS_R3).lis(0, 0x4330).stw(0, SCR, 4).stw(3, SCR + 4, 4)
    a.word(d_form(50, 2, 4, SCR)).word(d_form(50, 3, 4, MAGIC)).word(FSUB_F2_F2_F3).stfs(2, KF, 4)
    a.li(0, 0).stw(0, RI, 4)
    a.label("q_loop")
    _data(a, 4)
    a.lwz(5, RI, 4).slwi(6, 5, 2).lis(7, ha(RUNNERS)).addi(7, 7, lo(RUNNERS)).add(7, 7, 6).lwz(3, 0, 7)
    a.cmpwi(3, 0).beq("q_next")
    a.lbz(0, R_ON, 3).cmpwi(0, 0).beq("q_next")          # not on the field
    # Nick: bombed its own runner on his way to 2nd (a straight-line guess ran him past the base). His path now: from
    # where he is to the base he runs to (advancing) or back to (retreating); stopped: where he is.
    a.lfs(1, 4, 3).lfs(2, 0xC, 3).fmr(3, 1).fmr(4, 2)
    a.lbz(0, R_DIR, 3).cmpwi(0, 1).beq("q_to")
    a.cmpwi(0, 3).bne("q_seg")
    a.lbz(6, R_FROM, 3).b("q_base")
    a.label("q_to")
    a.lbz(6, R_TO, 3)
    a.label("q_base")
    a.cmplwi(6, 3).ble("q_bi")
    a.li(6, 0)                                            # 4 = home again
    a.label("q_bi")
    a.slwi(6, 6, 3).lis(7, ha(BASES)).addi(7, 7, lo(BASES)).add(7, 7, 6).lfs(3, 0, 7).lfs(4, 4, 7)
    a.label("q_seg")                                      # d^2 from C to the segment R..B
    a.lfs(5, AIMX, 4).lfs(6, AIMZ, 4)
    a.fsubs(7, 3, 1).fsubs(8, 4, 2).fsubs(9, 5, 1).fsubs(10, 6, 2)
    a.fmuls(11, 7, 7).fmadds(11, 8, 8, 11).fmuls(12, 9, 7).fmadds(12, 10, 8, 12)
    a.lfs(0, ZERO, 2).lfs(13, EPS, 2).fcmpo(11, 13).ble("q_t0")
    a.fdivs(13, 12, 11).fcmpo(13, 0).blt("q_t0")
    a.lfs(0, ONE, 2).fcmpo(13, 0).bgt("q_t")
    a.fmr(0, 13).b("q_t")
    a.label("q_t0")
    a.lfs(0, ZERO, 2)
    a.label("q_t")                                        # f0 = t in 0..1
    a.fmadds(1, 7, 0, 1).fmadds(2, 8, 0, 2)
    a.fsubs(1, 5, 1).fsubs(2, 6, 2).fmuls(1, 1, 1).fmadds(1, 2, 2, 1)
    a.lfs(0, KR2, 4).fcmpo(1, 0).ble("q2")
    a.label("q_next")
    a.lwz(5, RI, 4).addi(5, 5, 1).stw(5, RI, 4).cmpwi(5, 3).ble("q_loop")
    a.label("q1")
    a.li(3, 1).b("q_out")
    a.label("q2")
    a.li(3, 2).b("q_out")
    a.label("q0")
    a.li(3, 0)
    a.label("q_out")
    _data(a, 4)
    a.stb(3, QRES, 4)
    a.lwz(0, SUBLR, 4).mtlr(0).blr()


def log_sub(at):
    """The log subroutine: r3 = type, r4 = flags, r30 = COM; appends one record when LOGP is set. Uses r0, r5..r7,
    r11, r12 (= the data block on return) and f0; keeps everything else."""
    a = Asm(at)
    a.mflr(0)
    _data(a, 12)
    a.stw(0, LOGLR, 12)
    a.lwz(11, LOGP, 12).cmpwi(11, 0).beq("out")
    _slot(a, 5)
    a.stb(3, 0, 6).lwz(0, 0x0C, 30).stb(0, 1, 6).lbz(0, 0x25, 30).stb(0, 2, 6).stb(4, 3, 6)
    a.lwz(7, PLAYSTATE, 13).lha(0, 2, 7).sth(0, 4, 6).lwz(0, 0x18, 30).sth(0, 6, 6)
    a.lfs(0, AIMX, 12).stfs(0, 8, 6).lfs(0, AIMZ, 12).stfs(0, 12, 6)
    a.lfs(0, 0x10, 30).stfs(0, 16, 6).lfs(0, 0x14, 30).stfs(0, 20, 6)
    a.lfs(0, PX, 12).stfs(0, 24, 6).lfs(0, PZ, 12).stfs(0, 28, 6)
    a.label("out")
    a.lwz(0, LOGLR, 12).mtlr(0).blr()
    return a


def _slot(a, rc):
    """r6 = the next log record (r11 = the log); counts it. Uses r0, r6 and rc (the count)."""
    a.lwz(rc, 4, 11).addi(0, rc, 1).stw(0, 4, 11)
    a.lwz(6, 8, 11).addi(6, 6, -1).word((31 << 26) | (rc << 21) | (6 << 16) | (6 << 11) | (28 << 1))  # and r6,rc,r6
    a.slwi(6, 6, 5).add(6, 6, 11).addi(6, 6, 16)          # index & (entries - 1), LOG_REC 32


def _target_frame(a):
    """Record bytes 2 (target, COM +0x25, -1 without a COM) and 4..5 (frames since contact). Uses r0, r7."""
    a.li(0, -1).lwz(7, COM, 13).cmpwi(7, 0).beq("tg")
    a.lbz(0, 0x25, 7)
    a.label("tg")
    a.stb(0, 2, 6)
    a.li(0, 0).lwz(7, PLAYSTATE, 13).cmpwi(7, 0).beq("fr")
    a.lha(0, 2, 7)
    a.label("fr")
    a.sth(0, 4, 6)


def flog_sub(at):
    """FLOGFN (log builds): one type 8 record for fielder r5 (0..8; the chain +0x24 / +0x48 / base table, as
    _fielder_ptr), r4 = why. None there: nothing. Uses r0, r6..r8, r11, r12 (= the data block); keeps r3..r5, r9,
    r10 and every FPR."""
    a = Asm(at)
    _data(a, 12)
    a.lwz(11, LOGP, 12).cmpwi(11, 0).beq("out")
    a.slwi(6, 5, 2).lis(7, ha(FIELDERS)).addi(7, 7, lo(FIELDERS)).add(7, 7, 6)
    a.lwz(8, 0x24, 7).cmpwi(8, 0).bne("have")
    a.lwz(8, 0x48, 7).cmpwi(8, 0).bne("have")
    a.lwz(8, 0, 7).cmpwi(8, 0).beq("out")
    a.label("have")
    _slot(a, 7)
    a.li(0, 8).stb(0, 0, 6).stb(5, 1, 6).lbz(0, 0x22E, 8).stb(0, 3, 6).stb(4, 6, 6).li(0, 0).stb(0, 7, 6)
    _target_frame(a)
    for k, off in enumerate((4, 0xD4, 0xC, 0x1C)):        # x, y (feet), z, radius
        a.lwz(0, off, 8).stw(0, 8 + 4 * k, 6)
    a.lwz(0, PX, 12).stw(0, 24, 6).lwz(0, PZ, 12).stw(0, 28, 6)
    a.label("out")
    a.blr()
    return a


def orig_sub(at):
    """ORIGFN: the launch start S for a throw at the cursor (f1, f2) (field x / z), as the game computes it (see
    OBJ_FN): r4 = the item object, or 0: r3 = the item (0..5), its pool's free object (none, or no manager: S = (0, 0),
    and the throw couldn't happen anyway). Returns f1, f2 = S. A normal call: clobbers r0, r3..r12, f0..f13, ctr, cr;
    keeps r14..r31, f14..f31."""
    a = Asm(at)
    a.stwu(1, -0x40, 1).mflr(0).stw(0, 0x44, 1)
    a.stfs(1, 0x20, 1).fneg(2, 2).stfs(2, 0x24, 1)        # C.x, -C.z (FUN_80456710 passes -z)
    a.lfs(0, ZERO, 2).stfs(0, 0x08, 1).stfs(0, 0x10, 1)
    a.cmpwi(4, 0).bne("obj")
    a.mr(4, 3).lwz(3, MANAGER, 13).cmpwi(3, 0).beq("out")
    a.bl(OBJ_FN).cmpwi(3, 0).beq("out")
    a.b("have")
    a.label("obj")
    a.mr(3, 4)
    a.label("have")
    a.stw(3, 0x28, 1)
    a.lwz(12, 0, 3).lwz(12, 0x3C, 12).mtctr(12).bctrl()   # f1 = h
    a.lfs(2, 0x20, 1).lfs(3, 0x24, 1).addi(3, 1, 8).lwz(4, MANAGER, 13).li(5, 0).bl(START_FN)
    a.lfs(1, 0x20, 1).lfs(2, 0x24, 1).lwz(3, 0x28, 1).addi(4, 1, 8).bl(CLIP_FN)
    a.label("out")
    a.lfs(1, 0x08, 1).lfs(2, 0x10, 1)
    a.lwz(0, 0x44, 1).mtlr(0).addi(1, 1, 0x40).blr()
    return a


def onstep_sub(at):
    """ONSTEPFN: is (f1 x, f2 -z) on screen? r3 = 1 / 0: FUN_804570C8's camera projection and bounds only (not its
    ground / base test). A normal call: clobbers r0, r3..r12, f0..f13, ctr, cr."""
    a = Asm(at)
    a.stwu(1, -0x30, 1).mflr(0).stw(0, 0x34, 1)
    a.stfs(1, 0x10, 1).lfs(0, 0x2888, 2).stfs(0, 0x14, 1).stfs(2, 0x18, 1)
    a.li(3, 0).bl(CAM_FN)
    a.addi(4, 1, 0x10).addi(5, 1, 0x1C).bl(PROJ_FN)
    a.lfs(0, 0x288C, 2).lfs(1, 0x2890, 2).lfs(2, 0x1C, 1).lfs(3, 0x20, 1).li(3, 0)
    a.fcmpo(2, 0).ble("out").fcmpo(2, 1).bge("out").fcmpo(3, 0).ble("out").fcmpo(3, 1).bge("out")
    a.li(3, 1)
    a.label("out")
    a.lwz(0, 0x34, 1).mtlr(0).addi(1, 1, 0x30).blr()
    return a


def flight_stub(at):
    """FLIGHT (log builds only): FUN_80453764, the per-object item update the dispatch FUN_80455394 calls for each
    object of the active item (r3 = the object; tail-calls vtable +0x40). Shell / Fireball (manager +0x394) in use
    (+0x37, set by the launch FUN_80453824) and flying (+0x3C: Shell 1 (FUN_804592cc), Fireball 2 (FUN_804531bc)):
    one type-6 record, its position (+4) and velocity (+0x10). Bob-omb / POW: on the first frame of the burst state
    (Bob-omb +0x3B == 3, the blast FUN_80117408 uses; POW +0x3A == 2, FUN_80117E34's burst; LASTST holds last
    frame's state), a type-7 record (same layout) and a type-8 record for each fielder 0..8. A call site: r0,
    r4..r12, f0.. are free; r3 is kept.
    Nick's 17:47 dump: flight records only every FLIGHT_EVERY frames (frames since contact); a burst once per object
    (LASTOBJ, until it leaves the burst state or 64 frames on); and LAUNCH, a type-9 record when the manager's last
    launch start (+0x374) changes: the real start, ORIGFN's for the cursor that throw used (start + direction +0x380,
    this object), and that cursor."""
    a = Asm(at)
    a.stwu(1, -0x20, 1).mflr(0).stw(0, 0x24, 1).stw(3, 0x08, 1)
    a.lwz(12, MANAGER, 13).cmpwi(12, 0).beq("out")
    _data(a, 11)
    a.lwz(0, 0x374, 12).lwz(5, LAUNCHX, 11).cmpw(0, 5).beq("fly")
    a.stw(0, LAUNCHX, 11)
    a.lfs(1, 0x374, 12).lfs(0, 0x380, 12).fadds(1, 1, 0).stfs(1, 0x10, 1)   # the cursor that throw used
    a.lfs(2, 0x37C, 12).lfs(0, 0x388, 12).fadds(2, 2, 0).stfs(2, 0x14, 1)
    a.mr(4, 3).bl(ORIGFN)
    _data(a, 12)
    a.lwz(11, LOGP, 12).cmpwi(11, 0).beq("fly")
    _slot(a, 5)
    a.li(0, 9).stb(0, 0, 6).lwz(7, MANAGER, 13).lwz(0, 0x394, 7).stb(0, 1, 6).li(0, 0).stb(0, 3, 6).sth(0, 6, 6)
    _target_frame(a)
    a.lwz(7, MANAGER, 13).lwz(0, 0x374, 7).stw(0, 8, 6).lwz(0, 0x37C, 7).stw(0, 12, 6)
    a.stfs(1, 16, 6).stfs(2, 20, 6).lwz(0, 0x10, 1).stw(0, 24, 6).lwz(0, 0x14, 1).stw(0, 28, 6)
    a.label("fly")
    a.lwz(3, 0x08, 1).lwz(12, MANAGER, 13)
    a.lwz(4, 0x394, 12).cmplwi(4, FIRE).bgt("burst")
    a.lbz(0, 0x37, 3).cmpwi(0, 0).beq("out")
    a.lbz(0, 0x3C, 3).addi(5, 4, 1).cmpw(0, 5).bne("out")   # not flying (stopped, hit, gone): no record
    a.lwz(7, PLAYSTATE, 13).lhz(0, 2, 7).andi_(0, 0, FLIGHT_EVERY - 1).bne("out")
    a.li(9, 6).b("rec")
    a.label("burst")
    a.cmplwi(4, POW).bgt("out")
    a.li(5, 3).lbz(0, 0x3B, 3).cmpwi(4, BOMB).beq("bs")
    a.li(5, 2).lbz(0, 0x3A, 3)
    a.label("bs")
    _data(a, 12)
    a.lwz(6, PLAYSTATE, 13).lha(6, 2, 6)
    a.cmpw(0, 5).beq("in_b")
    a.lwz(0, LASTOBJ, 12).cmpw(0, 3).bne("out")           # ours left the burst: the next one logs again
    a.li(0, 0).stw(0, LASTOBJ, 12).b("out")
    a.label("in_b")
    a.lwz(0, LASTOBJ, 12).cmpw(0, 3).bne("new_b")
    a.lwz(0, LASTF, 12).subf(0, 0, 6).cmplwi(0, 64).blt("out")   # the same burst (frame back: a new play)
    a.label("new_b")
    a.stw(3, LASTOBJ, 12).stw(6, LASTF, 12)
    a.li(9, 7)
    a.label("rec")
    _data(a, 12)
    a.lwz(11, LOGP, 12)
    _slot(a, 5)
    a.stb(9, 0, 6).stb(4, 1, 6).lbz(0, 0x36, 3).stb(0, 3, 6)   # type, item, visible (+0x36)
    _target_frame(a)
    a.sth(3, 6, 6)                                        # the object's address (low half)
    for k in range(6):                                    # position, velocity
        a.lwz(0, 4 + 4 * k, 3).stw(0, 8 + 4 * k, 6)
    a.cmpwi(9, 7).bne("out")
    a.li(9, 0)                                            # a burst: every fielder (keeps r3)
    a.label("fl")
    a.mr(5, 9).li(4, 1).bl(FLOGFN).addi(9, 9, 1).cmplwi(9, 8).ble("fl")
    a.label("out")
    a.lwz(3, 0x08, 1).lwz(0, 0x24, 1).mtlr(0).addi(1, 1, 0x20)
    a.word(FLIGHT_ORIG)
    a.b(FLIGHT + 4)
    return a


def _hook(dol, code, site, orig, make):
    got = dol.u32(site)
    assert got == orig, f"0x{site:08X}: 0x{got:08X}, expected 0x{orig:08X}"
    at = code.here + (-code.here % 4)
    blob = make(at).assemble()
    assert code.put(blob, align=4) == at
    dol.w32(site, branch(site, at))
    return at, len(blob)


def apply(dol, code, data):
    """Level 6 CPU item use in `dol`: stubs in `code`, the state + per-item records in `data` (charbuild Spaces).
    Needs level5.alloc(data) first (the flag). Returns log lines."""
    global DATA, LOGFN, FLOGFN, ORIGFN, ONSTEPFN
    assert level5.FLAG is not None, "level5.alloc(data) first"
    assert LOG_ENTRIES & (LOG_ENTRIES - 1) == 0, "LOG_ENTRIES: 0 or a power of 2"
    for site, orig in ((RESET, RESET_ORIG), (DECIDE, DECIDE_ORIG), (AIM, AIM_ORIG)):
        got = dol.u32(site)
        assert got == orig, f"0x{site:08X}: 0x{got:08X}, expected 0x{orig:08X}"
    assert dol.u32(0x80455838) == 0x38A00000, "0x80455838 is not `li r5,0`"
    logp = 0
    if LOG_ENTRIES:
        logp = data.put(LOG_MAGIC + struct.pack(">3I", 0, LOG_ENTRIES, LOG_REC) + bytes(LOG_ENTRIES * LOG_REC))
    blob = data_block(dol, logp)
    DATA = data.put(blob, align=32)
    global SHOTB, ROUTE_T
    SHOTB = data.put(shot_block(), align=4)                # the shot list's block (SHOTS: apply_shots)
    import defense_dbg                                     # the fielders' move targets (cpu_item_defense writes them)
    ROUTE_T = defense_dbg.alloc_route(data)
    assert (defense_dbg.ROUTE_N, defense_dbg.ROUTE_SIZE) == (ROUTE_N, ROUTE_SZ)
    LOGFN = code.here + (-code.here % 4)
    assert code.put(log_sub(LOGFN).assemble(), align=4) == LOGFN
    ORIGFN = code.here + (-code.here % 4)
    assert code.put(orig_sub(ORIGFN).assemble(), align=4) == ORIGFN
    ONSTEPFN = code.here + (-code.here % 4)
    assert code.put(onstep_sub(ONSTEPFN).assemble(), align=4) == ONSTEPFN
    global POWFN, POWB
    POWB = data.put(bytes(PHALF) + struct.pack(">f", 0.5) + bytes(POWB_SIZE - PHALF - 4), align=4)
    POWFN = code.here + (-code.here % 4)
    assert code.put(pow_sub(POWFN).assemble(), align=4) == POWFN
    if LOG_ENTRIES:                                       # the fielder records (log builds only)
        FLOGFN = code.here + (-code.here % 4)
        assert code.put(flog_sub(FLOGFN).assemble(), align=4) == FLOGFN
    sizes = []
    for site, orig, make in ((RESET, RESET_ORIG, reset_stub), (DECIDE, DECIDE_ORIG, decide_stub),
                             (AIM, AIM_ORIG, aim_stub)):
        at, n = _hook(dol, code, site, orig, make)
        sizes.append((site, at, n))
    if LOG_ENTRIES:                                       # the item's flight (log builds only)
        sizes.append((FLIGHT, *_hook(dol, code, FLIGHT, FLIGHT_ORIG, flight_stub)))
    if LOG_ENTRIES:
        sizes.append((0, FLOGFN, len(flog_sub(FLOGFN).assemble())))
    sizes.append((0, ORIGFN, len(orig_sub(ORIGFN).assemble())))
    sizes.append((0, ONSTEPFN, len(onstep_sub(ONSTEPFN).assemble())))
    total = sum(n for *_, n in sizes)
    return [f"cpu items (level 6): real item, timed on the fielder who gets the ball, exact aim, cursor "
            f"{SPEED6[0]}/frame; " + ", ".join((f"0x{s:08X} -> " if s else "FLOGFN ") + f"0x{at:08X} ({n} B)"
                                               for s, at, n in sizes)
            + f"; code {total} B (0x{total:X}), data {len(blob)} B at 0x{DATA:08X}"
            + (f"; LOG: {LOG_ENTRIES} records at 0x{logp:08X} (scripts/read_item_log.py)" if logp else "")]


# ---- the reference model (the spec), used by the test ----

def runner_path_end(x, z, direction, frm, to, bases):
    """Where a runner's path ends: his to-base advancing (1), his from-base retreating (3), else where he is."""
    if direction in (1, 3):
        b = to if direction == 1 else frm
        return bases[b if b <= 3 else 0]
    return x, z


def runner_safe(spot, item_rec, runners, bases):
    """The friendly-fire rule for one spot: runners = [(x, z, direction, from, to)]; item_rec = (speed, fixed, dist,
    kind); bases = [(x, z)] home, 1st, 2nd, 3rd."""
    _, _, d, kind = item_rec
    if kind == KIND_EDGE:
        reach = d + EDGE_MARGIN + RUNNER_PAD
    elif kind == KIND_BANANA:
        reach = d + BANANA_HIT + RUNNER_PAD
    else:
        return True
    for x, z, direction, frm, to in runners:
        bx, bz = runner_path_end(x, z, direction, frm, to, bases)
        dx, dz, wx, wz = bx - x, bz - z, spot[0] - x, spot[1] - z
        n = dx * dx + dz * dz
        t = 0.0 if n <= 1e-4 else min(max((wx * dx + wz * dz) / n, 0.0), 1.0)
        if (spot[0] - x - t * dx) ** 2 + (spot[1] - z - t * dz) ** 2 <= reach * reach:
            return False
    return True


def shell_line(P, S):
    """The Shell's first tries when C is bad: P moved j * LINE_STEP of the way back toward S, j = 1..LINE_TRIES."""
    return [(P[0] + (S[0] - P[0]) * j * LINE_STEP, P[1] + (S[1] - P[1]) * j * LINE_STEP) for j in range(1, LINE_TRIES + 1)]


def banana_centers(C0, d):
    """The Banana's tries when C0 is bad: the cursor spots that land one of the five bananas on B = C0 + d BANANA12
    (the 12:00 banana's target), k = 0..4 in the stub's order."""
    b = (C0[0] + d * BANANA12[0], C0[1] + d * BANANA12[1])
    return [(b[0] - d * math.cos(math.radians(72 * k)), b[1] - d * math.sin(math.radians(72 * k))) for k in range(5)]


def banana_lands(C, d):
    """Where the five bananas land for cursor C (cursor space: + d (cos a, -sin a), a = 72 k; k = 4 is 12:00)."""
    return [(C[0] + d * math.cos(math.radians(72 * k)), C[1] - d * math.sin(math.radians(72 * k))) for k in range(5)]


def good_spot(C, C0, P, good, base=None):
    """The AIM stub's spot choice (the spec): C if good(C), else the first good of C0 turned around P by TURNS at
    RINGS of its distance (rings outer), else P."""
    if good(C):
        return C
    dx, dz = (C0[0] - P[0], C0[1] - P[1]) if base is None else (base, 0.0)   # base: the Bob-omb's ring radius
    for k in RINGS:
        for deg in TURNS:
            cs, sn = math.cos(math.radians(deg)), math.sin(math.radians(deg))
            q = (P[0] + (dx * cs - dz * sn) * k, P[1] + (dx * sn + dz * cs) * k)
            if good(q):
                return q
    return P


def wall_k(path, wall_d):
    """The OFF THE WALL frame (the spec): the first k in 1..PATH_MAX with |xz| >= wall_d - WALL_IN while the ball is
    above IN_AIR_Y at every frame 1..k; None if it is on the ground first (or never reaches the wall)."""
    lim = f32(f32(wall_d) - f32(WALL_IN)) ** 2
    for k in range(1, PATH_MAX + 1):
        x, y, z = path(k)
        if y <= f32(IN_AIR_Y):
            return None
        if x * x + z * z >= lim:
            return k
    return None


def stock_fly(frames_to_land, item):
    """A catchable fly (stock): (T, the landing point is P, no target): T = the landing - MEET_LEAD (the Boo: the
    landing), >= 0."""
    return max(frames_to_land - (0 if item == BOO else MEET_LEAD), 0)


def chaser(path, etas, bounced, humans=()):
    """The level 6 chaser (the spec): stock FUN_800CDBBC's scan without its ready gate. path(k) = the ball k frames
    from now (x, y, z); etas {fielder: f(x, z) -> frames}; not bounced: only points at most CHASE_GROUND up.
    -> (fielder, his time) with the smallest time, or None."""
    best = None
    for i in sorted(etas):
        for k in range(1, CHASE_MAX, CHASE_STEP):
            x, y, z = path(min(k, PATH_MAX))
            if not bounced and y > f32(CHASE_GROUND):
                continue
            e = etas[i](x, z)
            if i in humans:                          # he shakes: x 1 / 1.4
                e = e * DASH_NUM // DASH_DEN
            if e < k + CHASE_SLACK:
                if best is None or e < best[1]:
                    best = (i, e)
                break
    return best


def stock_chase(t_int, F, direction, speed, pickup, item, busy=False):
    """The stock chaser (FUN_800CDBBC) intercepting in t_int frames: (T, P). T = t_int - MEET_LEAD (the Boo: t_int),
    >= 0; P = F + direction * speed * T (stock's aim, FUN_80450794), not past the pickup point (then the pickup);
    F while he is catching / throwing (+0x251 1..9)."""
    T = max(t_int - (0 if item == BOO else MEET_LEAD), 0)
    lead = 0.0 if busy else speed * T
    D = math.hypot(pickup[0] - F[0], pickup[1] - F[1])
    if lead > D:
        return T, pickup
    if D > 1e-2:                                      # toward his spot (Nick, 2026-09-28), not his heading
        direction = ((pickup[0] - F[0]) / D, (pickup[1] - F[1]) / D)
    return T, (F[0] + direction[0] * lead, F[1] + direction[1] * lead)


def shots_model(item, T, P, rec, S_of, fielders, target, lead=None, throwable=None):
    """The shot list (docstring SHOT LIST), the spec for SHOTS: rec = (speed, fixed); S_of(C) -> S (the launch start
    for the cursor C); fielders {i: (x, z, dir x, dir z, speed)}; lead(t) -> the target's P at t (None: P only);
    throwable(C) -> bool (FUN_804570C8; None: always). -> (k, P, S, rel, travel, hits, C) of the pick (C: the cursor,
    P or up the screen: EXT), or None (a Fireball with no clear shot)."""
    sp, fx = rec
    best = None
    for k, off in enumerate(OFF if lead is not None else OFF[:1]):
        t = T + off
        if t < 1:
            continue
        p = P if k == 0 else lead(t)
        s = S_of(p)
        L = f32(math.hypot(p[0] - s[0], p[1] - s[1]))
        aim = p
        if L > 1e-4:
            ux, uz = f32(f32(p[0] - s[0]) / L), f32(f32(p[1] - s[1]) / L)
            for e in EXT:                            # higher up the screen: the nearest S wins
                cx, cz = f32(p[0] + ux * e), f32(p[1] + uz * e)
                if throwable is not None and not throwable((cx, cz)):
                    continue
                s2 = S_of((cx, cz))
                L2 = f32(math.hypot(p[0] - s2[0], p[1] - s2[1]))
                if L2 <= 1e-4 or L2 >= L:
                    continue
                ax, az, bx, bz = p[0] - s2[0], p[1] - s2[1], cx - s2[0], cz - s2[1]
                if (ax * bz - az * bx) ** 2 > EXT_MISS ** 2 * (bx * bx + bz * bz):
                    continue
                s, L, aim = s2, L2, (cx, cz)
        trav = int(L / sp)
        rel = t - fx - trav
        hits = _shot_hits(item, p, s, L, max(rel, 0), sp, fielders, target)
        if item == FIRE and hits:
            continue
        cand = (k, p, s, rel, trav, hits, aim)
        if best is None:
            best = cand
            continue
        cv, bv = rel >= 0, best[3] >= 0
        if cv != bv:
            best = cand if cv else best
        elif not cv:
            best = cand if rel > best[3] else best
        elif item == SHELL and hits != best[5]:
            best = cand if hits > best[5] else best
        elif trav < best[4]:
            best = cand
    return best


def _shot_hits(item, p, s, L, rel, sp, fielders, target):
    if L <= 1e-4:
        return 0
    ux, uz = (p[0] - s[0]) / L, (p[1] - s[1]) / L
    c, n = math.cos(math.radians(FIRE_SPREAD)), math.sin(math.radians(FIRE_SPREAD))
    paths = [(ux, uz, L if item == FIRE else RANGE)]
    if item == FIRE:
        paths += [(ux * c - uz * n, ux * n + uz * c, RANGE), (ux * c + uz * n, -ux * n + uz * c, RANGE)]
    hits = 0
    for i, (fx, fz, dx, dz, fsp) in fielders.items():
        if i == target:
            continue
        vx, vz = dx * fsp, dz * fsp
        arr = rel + L / sp
        if math.hypot(fx + vx * arr - p[0], fz + vz * arr - p[1]) < CATCH_R:
            continue
        for wx, wz, rng in paths:
            s0 = (fx - s[0]) * wx + (fz - s[1]) * wz
            tau = rel + s0 / sp
            x, z = fx + vx * tau - s[0], fz + vz * tau - s[1]
            along = x * wx + z * wz
            if 0 < along < rng and abs(x * wz - z * wx) < HIT_R:
                hits += 1
                break
    return hits


def fly_catcher(item, T, land, fielders):
    """The fly-ball catcher spot for a Banana / Shell / Fireball (DECIDE "fl_w"): (T, P, i) or None: the catcher (the
    least |F - L| / max(E4, 2 EC), the first on ties), P = L + (F - L) * r / |F - L|, their catch T kept (the Banana
    too since Nick, 2026-09-29: "like the shell timing")."""
    best, bt = None, 0x7FFF
    for i in sorted(fielders):
        x, z, e4, ec, r = fielders[i]
        sp = f32(max(e4, f32(f32(ec) * f32(BUDDY_CAP)))) or 1.0
        t = int(f32(f32(math.hypot(x - land[0], z - land[1])) / sp))
        if t < bt:
            best, bt = i, t
    if best is None:
        return None
    x, z, _, _, r = fielders[best]
    d = math.hypot(x - land[0], z - land[1])
    if d <= 1e-4:
        return None
    k = r / d
    return T, (land[0] + (x - land[0]) * k, land[1] + (z - land[1]) * k), best


def late_relead(dol, item, T, P, F, direction, speed, cap, busy=False, hz=0, row=0, top=0.0):
    """The late re-lead (DECIDE "timer", Nick's 14:38 dump): a lobbed item (record speed 0: Bob-omb, POW, Banana; not
    the Boo) whose release is already past (T - its fixed frames < 0, the Banana's BANANA_EARLY too) is led again for
    T' = the fixed frames (+ BANANA_EARLY): P' = F + direction * max(speed, top) * T', not past `cap` (then the cap),
    F while busy. Else (T, P). Chaser / wall plans only (not the fly-ball landing)."""
    sp, fx, _, kind = records(dol)[(hz * 2 + row) * 6 + item]
    early = BANANA_EARLY if kind == KIND_BANANA else 0
    if sp > 0 or item == BOO or kind == KIND_BANANA or T - fx - early >= 0:   # (a late Banana holds: model None)
        return T, P
    T2 = fx + early
    lead = 0.0 if busy else max(speed, top) * T2
    D = math.hypot(cap[0] - F[0], cap[1] - F[1])
    if lead > D:
        return T2, cap
    if D > 1e-2:                                      # toward his spot (as stock_chase)
        direction = ((cap[0] - F[0]) / D, (cap[1] - F[1]) / D)
    return T2, (F[0] + direction[0] * lead, F[1] + direction[1] * lead)


def model(dol, item, T, P, cursor, S, hz=0, row=0, fielder=None):
    """What level 6 should do: (timer, C). Written from the spec with the physics values, not from the stub.
    fielder: unused (kept for callers)."""
    sp, fx, d, kind = records(dol)[(hz * 2 + row) * 6 + item]
    t = T - fx
    if sp > 0:
        t -= int(math.hypot(P[0] - S[0], P[1] - S[1]) / sp)
    if kind == KIND_AT:
        c = P
    elif kind == KIND_EDGE and item == BOMB:
        c = P                                        # centred (Nick's 20:11 dump): 6 m of room every way
    elif kind == KIND_EDGE:
        ux, uz = cursor[0] - P[0], cursor[1] - P[1]
        n = math.hypot(ux, uz)
        ux, uz, n = (ux, uz, n) if n * n > 1e-4 else (1.0, 0.0, 1.0)
        c = (P[0] + ux * d / n, P[1] + uz * d / n)
    elif kind == KIND_BANANA:
        c = (P[0] - d * BANANA12[0], P[1] - d * BANANA12[1])
        t -= BANANA_EARLY
    else:
        c = cursor
    if kind == KIND_BANANA and t < 0:                # a late Banana holds (Nick, 2026-09-28): it can't land before him
        return None
    return max(t, 0), c                              # late: now (Nick: throw in every too-late case)


def cursor_speed(timer, cursor, c, hz=0):
    """The level 6 cursor step: fast enough to be in the 3.0 fire gate by the release frame, never below SPEED6."""
    return max(SPEED6[hz], (math.hypot(cursor[0] - c[0], cursor[1] - c[1]) - GATE_IN) / max(timer, 1))


def f32(v):
    return struct.unpack(">f", struct.pack(">f", v))[0]


def _lead(f, t, cap):
    """The wall's P (Nick's 19:32 dump): where the jumper is running, as stock's aim: his spot + his direction *
    speed * t (fielder tuple (x, z, radius, eta, [dir x, dir z, speed +0xE4, busy])), not past his wall spot cap."""
    fx, fz = f[0], f[1]
    dx, dz, sp, busy = (tuple(f[4:8]) + (0.0, 0.0, 0.0, False))[:4] if len(f) > 4 else (0.0, 0.0, 0.0, False)
    T, P = stock_chase(t, (fx, fz), (dx, dz), sp, cap, SHELL, busy)
    return P


def buddy_spot(ball, fielders, item=None):
    """The spec for a home run: (T, spot, jumper, T_boo) or None (no buddy plan / nobody gets there: as before).
    ball: dict with the game fields (+0x2A71 'to_wall', +0x2A79 'x79', 'bounced', +0x2A75 'hr', W +0x408, N +0x410,
    +0x2A4A 'cross', +0x29D8 'wall_d', 'land', 'pos' (FUN_800AC748 x, z), 'path' f(k) -> (x, y, z));
    fielders: {idx: (x, z, radius, eta_fn)}; 'route': {idx: (x, z)} the game's own move target this frame (J = the
    jumper's, the cpu_item_defense route hooks' table); 'plan8': an outfielder's route plan +0x22C is 8 (the game's buddy plan:
    a buddy play at W + 5 along the normal even when the wall-height tests fail). As in the game, 'path' and 'cross' are frames from NOW (800B38C8
    re-predicts the path from the ball every frame: path(0) = the ball now; +0x2A4A indexes it); T is from now too."""
    global BUDDY_J
    if not ball["to_wall"] or ball["x79"] or ball["bounced"]:
        return None
    wx, wz = ball["W"]
    if ball["hr"] > 1:
        ux, uz = ball["pos"][0] - wx, ball["pos"][1] - wz
        n = math.hypot(ux, uz)
        if n * n <= 1e-4:
            return None
        jx, jz = wx + ux * SPOT_BACK / n, wz + uz * SPOT_BACK / n
    else:
        f = ball["cross"]
        if not ball.get("plan8"):
            if f < 0 or ball["path"](min(f, PATH_MAX))[1] <= WALL_Y:
                return None
            if math.hypot(*ball["land"]) <= ball["wall_d"]:
                return None
        jx, jz = wx + ball["N"][0] * SPOT_BACK, wz + ball["N"][1] * SPOT_BACK
    best, eta, mate, eta2 = None, 0x7FFF, None, 0x7FFF
    for i in OUTFIELD:
        if i in fielders:
            e = fielders[i][3](jx, jz)
            if e < eta:
                if best is not None:
                    mate, eta2 = best, eta
                best, eta = i, e
            elif e < eta2:
                mate, eta2 = i, e
    if best is None:
        return None
    fx, fz, r, _ = fielders[best]
    d = math.hypot(fx - jx, fz - jz)
    if d * d > 1e-4:
        jx, jz = jx + (fx - jx) * r / d, jz + (fz - jz) * r / d
    if best in ball.get("route", {}):                # his own move target (Nick's 17:40 dump)
        jx, jz = ball["route"][best]
    if ball["cross"] > 0:                            # the wall: the first frame a buddy catch is possible, else X
        x = kj = ball["cross"]
        for k in range(1, min(x, PATH_MAX + 1)):
            px, py, pz = ball["path"](k)
            if item in (SHELL, FIRE):                # the game's jump trigger: the ball within JUMP_D of J
                if (px - jx) ** 2 + (pz - jz) ** 2 <= f32(f32(JUMP_D) * f32(JUMP_D)):
                    kj = k
                    break
                continue
            if (py < ball["path"](k - 1)[1] and py <= f32(BUDDY_Y)
                    and (px - jx) ** 2 + (pz - jz) ** 2 <= f32(BUDDY_R * BUDDY_R)):
                kj = k
                break
        straight = item in (SHELL, FIRE)             # a Shell / Fireball: the jump - MEET_LEAD, no first-hop rule
        t = kj - (MEET_LEAD if straight else HR_LEAD)
        if item == BANANA:                           # a Banana: his arrival at the spot (lands BANANA_EARLY before):
            f = fielders[best]                       # |F - J| / max(+0xE4, +0xEC), +0xEC 0.122 (the tests)
            sp = max(f[8] if len(f) > 8 else 0.0, f32(0.122))
            t = int(f32(f32(math.hypot(f[0] - jx, f[1] - jz)) / f32(sp)))
        if mate is not None and not straight:        # the first hop: before the teammate gets within HOP_D
            mx, mz = fielders[mate][0], fielders[mate][1]
            sp = max(fielders[mate][8] if len(fielders[mate]) > 8 else 0.0, f32(f32(0.122) * f32(BUDDY_CAP)))   # +0xE4
                                                     # now, at least the buddy run's 2 x +0xEC
            d = f32(math.hypot(mx - jx, mz - jz))
            t = min(t, int(f32(f32(d - f32(HOP_D)) / f32(sp))) - HOP_MARGIN)
        t = max(t, 0)
        BUDDY_J = (jx, jz)                           # (the jump spot: the tests' late re-lead cap)
        return t, _lead(fielders[best], t, (jx, jz)), best, x
    for k in range(1, PATH_MAX + 1):
        x, _, z = ball["path"](k)
        if (x - jx) ** 2 + (z - jz) ** 2 <= JUMP_D * JUMP_D:
            break
    else:
        return None
    if eta > k:
        return None
    t = max(k - (MEET_LEAD if item in (SHELL, FIRE) else HR_LEAD), eta)
    if item == BANANA:
        t = eta
    BUDDY_J = (jx, jz)
    t_boo = ball["cross"] if ball["cross"] >= 0 else t
    return t, _lead(fielders[best], t, (jx, jz)), best, t_boo
