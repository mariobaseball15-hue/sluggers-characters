"""Level 5 / 6 CPU pitching: a per-game LEARNING pitch model (Nick, 2026-09-28; docs/pitch-model.md), on top of the
level 5 policy (Nick, 2026-09-27; docs/cpu-ai-weaknesses.md 5.4): edge-of-zone locations, curves that end on the edge,
fastballs mostly from the hardest throwers, changeups by how high the changeup floats, charged curves steered like a
human's. Levels 1-4 (brain +0x1A 0..2, level 4 without level5.FLAG) and the tutorial brain (*(r13-0x1D3C) != 0) run
the stock code, and the same RNG calls. Brain = CBComPitch (r3 / r30 in its methods); pitcher = *(r13-0x1580), or
*(r13-0x1584) when that is 0; rand(n) = FUN_80165C14(*(r13-0x1578), n); uniform(lo, hi) = FUN_80165CFC(f1 lo, f2 hi,
r3 rng) = lo + 0.001 * rand(1000*(hi-lo)+1) (both leaves: r0 r3-r7 f0 f2 f3 cr0).

THE MODEL (docs/pitch-model.md has the numbers). Additive scores, learned online during one game and zeroed at every
match start (RESET). One state block per batting team (G+0x2A; so in CPU vs CPU each CPU pitcher learns the other
side, and a human pitching never writes the block the CPU reads), each with a score set per batter handedness (batter
+0xB3): 13 factor scores = pitch type (fastball / changeup / plain curve / charged curve), zone band measured from
the ACTUAL plate crossing (deep in / edge in / just off / far off), curve direction relative to the batter (toward /
away), break size measured from the actual pitch (small / medium / large). The scores are deltas from the prior: a
choice among options is a softmax pick(prior_i * 2^(score_i / T)), so with every score 0 it IS the prior. The priors
are the policy built before: the type mix (FB / CU tables, PLAIN6 15%, the rest charged curves), strikes deep / edge
50 / 50 (the old e band), balls far off (the ball band; just off only BALL_JUST%), charged curves at their full planned
bend (BRK_PRI), curve direction 50 / 50, and the ball / strike prior of the old adaptive rules (P_FIRST, P_TAKEN,
P_CHASE, the plain band). pick draws uniform(0, 1) with the game RNG, so the model always keeps randomness.
LEARNING. After a pitch, reward r (the batter's side only, nothing about where the ball went): strikeout +R_K,
swinging miss +R_MISS, taken strike +R_TAKEN, foul +R_FOUL, contact -(W_T * timing accuracy + W_S * sweet-spot
accuracy) (a perfect-timed sweet spot -6), a taken ball R_BALL (-1.5), walk R_WALK (-25), a hit batter R_HBP (-100,
unclamped, MEAN kept; HIT BATTERS below); the strikeout value and the contact
cost are multiplied by the situation (the batter's charge power band x the runners / outs). delta = r - MEAN -
(sum of the used factors' scores), clamped to +-DCLAMP; each used factor += ALPHA * delta (so older pitches fade by
(1 - ALPHA) per update: recency weighted); MEAN (a running baseline) += ALPHA * (r - MEAN).
BALLS. Separate opponent stats (per team, both hands): chase rate c = (swings at balls + C0 * N0) / (balls + N0)
and chase-strikeout rate q = (strikeouts swinging at a 2-strike ball + Q0 * N0) / (2-strike balls + N0). A ball's
advantage over a strike: dV = c * V_chase - c * Vs - (1 - c) * cost(balls) (a taken ball only delays the strike, so
the strike's value Vs = S0[strikes] + S[strikes], learned from the rewards of strikes, counts only through the chase;
c * V_chase = strikes 2 ? q * R_K * mult : c * R_MISS); the pick uses dV - dV0, dV at the prior stats (C0, Q0, S0).
cost = COST_B[balls], 3 balls: the walk cost WALK x the NEXT batter's charge band multiplier (a stronger next batter
makes a walk dearer); SLUGGER EXCEPTION: runners in scoring position AND this batter's charge power >= 60 AND the next
batter truly weak (charge power < 60, no star swing of his own (stats +9 == 0), not the loopy star swing: hit-curve
flag == 1 AND slap power < LOOPY_SLAP) -> W_CAREFUL. ball or strike = pick([1 - P0, P0], [0, dV - dV0], TB).
With 0-1 balls a FLOOR% roll forces a ball first. With 3
balls a rand(100) < CAP3[strikes] gate: under it the pick above decides (FORCE3 0), so at most 5% balls (>= 95%
strikes as before), both levels. (FORCE3 1, a fixed stock level 4 rate 13 / 13 / 6% under the gate, was level 5's
until Nick, 2026-09-28: level 5 walked too many; the code path stays for the setting.)
PITCHING CHANGE (pitcher +0x2A differs from the last decision's): the 26 scores x FADE and the temperatures x (1 +
HOT / HOT_N) for the next HOT_N pitches; the opponent stats and S carry over.
GLIDE (Nick, 2026-09-29: "fix the pitcher's movement on the mound before they pitch so it isn't so sudden ... make
them start moving to their spot right away and then start charging or throwing as soon as they are in the spot"). Stock
walks the aim cursor (pitcher +0x8C, the pitcher on the mound with it) toward brain +4 at 0.03 a frame (FUN_800C6E3C)
from frame 30 and decides at a random frame 60-75 (brain +0x18); the aim below used to write its final aim straight
into +0x8C at the decision, a jump just before the windup. At levels 5 / 6 now:
  - MOVE 0x800C6E58 (`cmpwi r0,0x1E`, the mover's frame-30 wait): from frame 1.
  - WAIT 0x800C67C8 (`lha r0,0x18(r30)`, the random wait): no wait; the decision runs as soon as stock's own
    readiness gates pass (brain +0x28, the batter's +0xDA). The decision (AIM, below) sets only the target brain +4
    and latches (GLIDE +0), returning 0; each later frame, once the cursor is on the target (the mover snaps the last
    step, so exactly equal) and the gates still pass, the pitch goes (1). If the batter's box x moved more than
    BOX_EPS since the decision (the HBP side test used it), it decides again (at most REDECIDE_MAX times a pitch).
    Frame 1 clears the latch (a new pitch) and stays stock's (location, the learning update), so the decision runs
    from frame 2. Star pitches and training decide the same way.
  A far target (a side switch for the HBP margin) walks ~1.1 / 0.03 ~ 37 frames; a typical final nudge 3-13.
HBP. A pitch on the batter's side must pass his hit box (docs/hit-by-pitch.md) with MARGIN: |X| + (a curve breaking
toward the centre: its planned break) + MARGIN <= |box_x + F4| - reach - 0.01 at his LIVE box_x (batter +0x44),
else the pitch goes to the other side. HBPs are recorded (hook) and scored R_HBP; each also adds HBP_STEP (0.25 m, up
to HBP_CAP 1.0) to MARGIN for that batting team and hand for the rest of the game (HMARG in its state block).
LEVELS. Level 5 (FLAG 1) PARAMS[0], level 6 (FLAG 2) PARAMS[1] (docs/pitch-model.md); today they differ only in
ALPHA (level 5 learns half as fast) and the far-off band top FAR_HI (level 5's misses go a little wider). Stock level 4's 3-ball ball rate was measured in
Unicorn (the stock decision, then the real flight with the stock plain-curve break, classified at the umpire planes;
fresh pitchers, release z 18.3 / plate z 0.72): only plain curves breaking outward leave the zone.

HOOKS (each with its stock word checked in apply):
TYPE 0x800C73A4 (FUN_800C7378, `lwz r3,-0x1D38(r13)`; r30 brain, r31 pitcher): pick over the 4 types with the prior
     PRI[id] (FB, CU, PLAIN6, the rest; ids past the tables: plain as before) -> r0 = 1 / 2 / 0 at 0x800C7420, a
     charged curve r0 = 1 and pitcher MARK = 1 (the stock charge-amount / changeup code follows).
LOCATION 0x800C6BA8 (FUN_800C6B70 on the decision's frame 1, `lwz r28,-0x1580(r13)`; r28-r31 restored by its
     epilogue 0x800C6E1C): brain +4 = +-EDGE by rand(2) (the side), then the LEARNING UPDATE for the last pitch (if
     it was ours: PEND), the latch cleared, the pitching-change check and this pitch's temperatures (TEMP / TEMPB).
AIM 0x800C691C (FUN_800C6780's `li r3,1`, every decision path ends here): not training, not a star pitch: count,
     situation multiplier (PMULT), ball / strike, band (then |X| = uniform in the band), curve direction and (charged
     curves) break size by pick; the side from LOCATION, moved away when HBP-unsafe; then the aim as before: a plain
     curve CURVE_DIR = toward the centre (4 if the pitch is on +x else 5) from B wide, or flipped (away from the
     centre) from B inside; a charged curve K_TARGET = X, no bow, started Bc[id] * BRK_SCALE wide / inside for STEER;
     straight pitches aim X. PEND and the pitch's factors are stored for the update.
CLAMP 0x8015DCE4 (FUN_8015DC38, windup frame 1: `bl 0x804B9ACC` remap): aims inside [-0.4, 0.4] go through the stock
     remap bit-exact; outside, unclamped (only our aims reach there).
STEER 0x80162394 (FUN_80162358's CPU branch): a marked charged curve is steered closed loop onto K_TARGET by at most
     a human's full input a frame inside the human steer window (docstring of steer_stub).
PLANE 1 / 2 0x8016291C / 0x801629D0 (FUN_801627E0, `li r0,1` / `li r0,2` as the ball passes z 1.12 / 0.32; r29
     pitcher; bl a shared stub): SEEN = 1, ZONE = pitcher +0xEE (the umpire's strike so far), SWUNG |= batter +0xCE
     (a swing started this pitch), XACT = ball x +0x38 and XAIM = the plate aim +0x5C (break = |XACT - XAIM|).
CONTACT 0x800BD408 (FUN_800bd2f0 right after `bl FUN_800BD938`, `lwz r3,-0x1580(r13)`; r29 batter): CONTACT = 1,
     CZONE = +0xBA (the contact zone: 2 = sweet spot), CF = +0x60 (the contact score 0..200, 100 = centre), CFRAME
     = +0x84 (the swing frame at contact, max 15), CTYPE = +0xB6 (0 slap, 1 charge, 2 star, 3 bunt, max 3).
     Timing accuracy = TIMING[CTYPE][CFRAME]: 1 - |frame - p| / D, p = the frame where the stick-neutral direction
     row (0x80626628) crosses straight away, D = the farthest active frame (0x80626570); 0 for bunts. Sweet-spot
     accuracy = 1 in zone 2, else max(0, 1 - |CF - 100| / 100).
HBP 0x80163630 (FUN_801634B8, `stb r0,0xD1(r31)`; bl): the stock store, then HBP = 1.
RESET 0x800C3684 (FUN_800C364C, the CPU manager built at every match start, `stb r5,0x1A(r3)`; bl): both state
     blocks zeroed (r8-r10, ctr), then the stock store.
Outcome at the next frame 1: HBP -> walk; contact and the at-bat continues (count not 0-0) -> foul, else in play
(contact cost); no contact: a swing -> miss (strikes 2: strikeout), ZONE -> taken strike (strikes 2: strikeout),
else a ball (3 balls: walk). Nothing latched (a star pitch, training): no update.

TABLES (the build's data, per character id 0..max): PRI[id] = (FB, CU, PLAIN6, the rest) / 100: FB[id] = 35 if charge
pitch speed >= 150, 3 below, 0 when the charge speed <= the curveball speed; CU[id] by the changeup's peak score
arc * 10000 / (curveball speed * changeup mult)^2: >= 40 -> 30, >= 27 or mult > 1.3 -> 10, else 4 (0 for an empty
row). PERID[id] (+ a default row at n): f32 E0 = |F4| - (reach + 1) / 100 (so the hit-box edge = E0 - box_x), u8
charge power band (< 40, < 60, < 80, else), u8 weak (the slugger exception's next batter). Read through the game's own
lis / addi pairs for the tables charbuild relocates (charfloats 0x800BDA1C, trajectory 0x800BAEAC, selector
0x8015C944, throwfloats 0x8016250C), so stat edits and new ids land in their tier. B (plain curve break) is the
doc's UNMEASURED estimate (5.1: 0.20 / 0.25 / 0.30 by tertile, x1.3 late); the break band the model learns is
measured in flight (XACT - XAIM). Bc[id] = BEND_MARGIN of the modelled fresh max bend at a perfect charge (capped at
BEND_CAP).
cpu_perfect interaction: always-perfect fastballs, always-curve and always-late stay useful; never-repeat goes dead.
Tests: scripts/test_cpu_pitching.py (hooks, placement, flight), scripts/test_pitch_model.py (learning).
"""
import struct
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
import level5  # noqa: E402
from ppc import Asm, bc, branch, d_form, ha, lo, x_form  # noqa: E402
from sluggers_data import STAT_FIELDS  # noqa: E402

L4 = 3                                             # brain +0x1A: level tier (3 = level 4)
LEVEL, TRAINING, KIND, AIM = 0x1A, 0x21, 0x1B, 4   # brain fields; KIND 0 plain, 1 fastball, 2 star, 3 changeup
PITCHER, PITCHER_ALT, RNG, TUTORIAL = -0x1580, -0x1584, -0x1578, -0x1D3C   # r13
CHAR_ID, CURVE_DIR, TERTILE, LATE, CURSOR = 0x2A, 0x140, 0x137, 0x190, 0x8C  # pitcher fields
RAND, UNIFORM, REMAP = 0x80165C14, 0x80165CFC, 0x804B9ACC

TYPE, TYPE_ORIG, TYPE_PICKED = 0x800C73A4, 0x806DE2C8, 0x800C7420     # lwz r3,-0x1D38(r13); cmplwi r0,1
LOC, LOC_ORIG, LOC_DONE = 0x800C6BA8, 0x838DEA80, 0x800C6E1C          # lwz r28,-0x1580(r13); epilogue
DECIDE, DECIDE_ORIG = 0x800C691C, 0x38600001                          # li r3,1
MOVE_AT, MOVE_ORIG, MOVE_RET = 0x800C6E58, 0x2C00001E, 0x800C6E5C     # cmpwi r0,0x1E (FUN_800C6E3C: from frame 30)
WAIT_AT, WAIT_ORIG, WAIT_RET = 0x800C67C8, 0xA81E0018, 0x800C67CC     # lha r0,0x18(r30) (the 60-75 frame wait)
WAIT_GO, BRAIN_RET = 0x800C67DC, 0x800C6920                            # the readiness gates; FUN_800C6780's epilogue
READY, BATTER_BUSY = 0x28, 0xDA                    # brain u8 (stock: 0 -> no pitch); batter u8 (stock: != 0 -> no pitch)
BOX_EPS, REDECIDE_MAX = 0.02, 3                    # GLIDE: re-decide when the batter's box x moved more (docstring)
GLIDE = None                                       # u8 latch, u8 re-decisions, f32 box x at the decision, f32 BOX_EPS
CLAMP, CLAMP_ORIG = 0x8015DCE4, branch(0x8015DCE4, REMAP, link=True)  # bl 0x804B9ACC
CONTACT_AT, CONTACT_ORIG = 0x800BD408, 0x806DEA80                     # lwz r3,-0x1580(r13) (after bl FUN_800BD938)
HBP_AT, HBP_ORIG = 0x80163630, 0x981F00D1                             # stb r0,0xD1(r31)
RESET_AT, RESET_ORIG = 0x800C3684, 0x98A3001A                         # stb r5,0x1A(r3)

EDGE = 0.55                                        # the zone's edge |x| (umpire 0x80627A90 / 94); LOCATION's side
E_LO, E_HI, E_HI5 = -0.12, 0.08, 0.12              # the old e band (strikes EDGE + [E_LO, 0]; kept for the docs)
B_TERTILE, B_LATE = (0.20, 0.25, 0.30), 1.3        # UNMEASURED plain-curve break estimate (docstring)
B = [b * m for b in B_TERTILE for m in (1.0, B_LATE)]   # index tertile*2 + late

FB_CUT, FB_TOP, FB_LOW = 150, 35, 3                # charge pitch speed >= 150: 35%, else 3%; 0 if not faster
CU_TIERS = ((40, 30), (27, 10))                    # peak score >= 40: 30%, >= 27: 10%
CU_FAST_MULT, CU_BASE = 1.3, 4                     # mult > 1.3 (a surprise fast "changeup"): the 10% tier; else 4%
PLAIN6 = 15                                        # levels 5 and 6: plain (uncharged) curves 15%, after FB and CU

STATS_ROWS = 0x806CE9A0 + 8                        # 8-byte header, then 0x8E-byte rows by id
STATS_ROW = 0x8E
CHANGEUP = 0x80628EB0                              # 8 per id: f32 speed mult, f32 arc height
STOCK_MAX = 0x46                                   # stock_stats: ids 0..0x46
COUNT, STRIKES, BALLS, OUTS = -0x1D38, 7, 8, 9     # *(r13-0x1D38): +7 strikes, +8 balls, +9 outs

# ---- the ball band (Nick, 2026-09-27, option 1): balls end past the sweet spot ~0.65, out to the ~0.85 reach
BALL_LO, BALL_HI, BALL_HI5 = 0.75, 0.90, 0.94      # the "far off" band (level 5 a little wider)

# ---- where the model's bands put a pitch (|x| at the plate) and how an actual crossing is banded
BAND_LO = (0.43, 0.49, 0.58, BALL_LO)             # deep in, edge in, just off, far off (top: BAND_HI, far: level's)
BAND_HI = (0.49, 0.545, 0.72, BALL_HI)
BAND_T = (0.49, 0.5501, 0.74)                      # measured: |XACT| >= each threshold -> the next band
BRK_T = (0.18, 0.32)                               # measured break |XACT - XAIM|: small / medium / large
BRK_SCALE = (0.40, 0.70, 1.00)                     # a charged curve's planned bend for small / medium / large
BRK_PRI = (0.05, 0.15, 0.80)                       # prior: the full bend as before, mostly
DIR_PRI = (0.5, 0.5)                               # toward / away from the batter (the old 50 / 50)
DEEP_PRI = (0.5, 0.5)                              # strikes: deep / edge (the old uniform e in [-0.12, 0])
P_FIRST, P_TAKEN, P_CHASE = 40, 75, 20             # prior % in the zone: first pitch, after a taken strike, a chase
MARGIN = 0.15                                      # HBP margin (m) past the hit box edge
# level 5's own values of FB_CUT / FB_TOP / FB_LOW / PLAIN6 / P_FIRST / P_TAKEN / P_CHASE / MARGIN (cpu_settings;
# level5.pair; the constants are level 6's): its own PRI table, and P0_* / MARGIN in a tail after the consts block
# (K5), only when they differ (a default build: today's bytes)
AT4 = {}
AT5 = {}
MIX = ("FB_CUT", "FB_TOP", "FB_LOW", "PLAIN6")
K5_NAMES = ("P_FIRST", "P_TAKEN", "P_CHASE", "MARGIN")    # the tail: P0_FIRST, P0_TAKEN, P0_CHASE, MARGIN (level 5)
K4 = None
K5 = None                                          
BEND_MARGIN, BEND_CAP = 0.85, 1.0                  # plan 85% of the modelled fresh max bend; cap (garbage rows)
LOOPY_SLAP = 40                                    # Nick 2026-09-28: the loopy star swing counts only below this
                                                   # slap power (King Boo / Baby DK, slap 50, are not loopy threats)

# ---- rewards and model constants (docs/pitch-model.md)
R_K, R_MISS, R_TAKEN, R_FOUL, R_BALL, R_WALK = 10.0, 2.0, 1.0, 0.5, -1.5, -25.0
# HIT BATTERS (Nick, 2026-09-28: "they throw way too many bean balls and don't learn from them. Let's jack that
# penalty way up"): an HBP scores R_HBP, not clamped by DCLAMP and not moving MEAN (was R_WALK, clamped to -12: about
# -1 per used score at level 6); and each HBP widens that batting team's inside margin for that hand by HBP_STEP (up
# to HBP_CAP) for the rest of the game: the model's factors have no inside / outside, so this is how it learns where
R_HBP, HBP_STEP, HBP_CAP = -100.0, 0.25, 1.0   # R_BALL: -1 until Nick, 2026-09-28
                                                    # ("a slightly harsher penalty for throwing a taken ball")
W_T, W_S = 2.0, 4.0                                # contact cost: timing, sweet spot (twice as punishing)
CP_MULT = (0.8, 1.0, 1.4, 1.8)                     # batter charge power < 40, 40-59, 60-79, 80+
RUN_MULT = (1.0, 1.3, 1.5, 1.7)                    # bases empty / 1st only; RISP 2 outs; RISP 0-1 outs; 3rd 0-1 outs
C0, Q0 = 0.30, 0.15                                # chase rate prior; P(strikeout | a 2-strike ball) prior
COST_B = (1.0, 1.5, 3.0)                           # the cost of a ball taken at 0 / 1 / 2 balls
WALK, W_CAREFUL = 25.0, 12.0                       # the walk cost (x the next batter's CP_MULT); slugger exception
S0 = (-0.2, -0.2, 2.5)                             # prior value of a strike at 0 / 1 / 2 strikes
DCLAMP, FADE, HOT_N = 12.0, 0.5, 10.0              # update clamp; pitching change: scores x FADE, HOT_N hot pitches
T_MIN = 0.05                                       # pick's temperature floor
# per level (index 0: level 5, 1: level 6)
# Nick, 2026-09-28 (level 5 walked too many): "Level 5 should just have a slightly wider radius and a slower learning
# rate the rest should be the same": the wider outside miss (FAR_HI: BALL_HI5) and half the learning rate (ALPHA);
# everything else level 6's (the temperatures T / TB, N0, the floor, the 3-ball gate: no fixed level-4 3-ball rate).
PARAMS = {"ALPHA": (0.04, 0.04, 0.08), "T": (1.0, 1.0, 1.0), "TB": (0.25, 0.25, 0.25), "N0": (4.0, 4.0, 4.0), "P0_PLAIN": (0.40, 0.40, 0.40),
          "FAR_HI": (BALL_HI5, BALL_HI5, BALL_HI), "PRI_JUST": (0.05, 0.05, 0.05), "PRI_FAR": (0.95, 0.95, 0.95),
          "FLOOR": (5, 5, 5), "CAP3": (5, 5, 5), "CAP3_1": (5, 5, 5), "CAP3_2": (5, 5, 5), "FORCE3": (0, 0, 0)}
# (% ints) FLOOR: the ball floor at 0-1 balls. CAP3 / CAP3_1 / CAP3_2: with 3 balls and 0 / 1 / 2 strikes, the rand(100)
# gate: roll >= it -> a strike. FORCE3 0 (level 6): under it the ball / strike pick decides (so CAP3 is a maximum);
# FORCE3 1 (level 5): under it a ball, so the 3-ball ball rate IS CAP3 by strikes, fixed, as stock level 4 (Nick,
# 2026-09-28: "level 5 should be the same as level 4" with 3 balls). 13 / 13 / 6 = stock level 4 measured in Unicorn
# (docs/pitch-model.md "3 balls: stock level 4"): 12.9% / 13.0% / 5.8% at 3-0 / 3-1 / 3-2, fresh pitchers.
L4_3BALL = (0.129, 0.130, 0.058)                   # the measured stock level 4 ball rates at 3-0 / 3-1 / 3-2 (tests)
SECTION = 0x1800                                   # charbuild: the stubs' own text section (0x10F0 B of code today;
                                                   # the item section overflowed with them in the test builds)
PARAM_NAMES = list(PARAMS)
PSIZE = 4 * len(PARAMS)
P_ = {n: 4 * i for i, n in enumerate(PARAM_NAMES)}
INT_PARAMS = {"FLOOR", "CAP3", "CAP3_1", "CAP3_2", "FORCE3"}
assert P_["CAP3_1"] == P_["CAP3"] + 4 and P_["CAP3_2"] == P_["CAP3"] + 8   # indexed by strikes in the aim stub

# ---- the state block per batting team (zeroed at match start)
SEEN, ZONE, SWUNG, CONTACT, HBP, CZONE, CFRAME, CTYPE = range(8)   # the latch (hooks), cleared at frame 1
XACT, XAIM, CF = 0x08, 0x0C, 0x10
PEND, PB, PK, PTYPE, PDIR, PHAND, PBAND, PBRK = range(0x14, 0x1C)   # the pitch in flight (AIM)
PMULT, LASTP, PREV = 0x1C, 0x20, 0x22
HOT, BT, SW, B2, K2, S_, MEAN, TEMP, TEMPB = 0x24, 0x28, 0x2C, 0x30, 0x34, 0x38, 0x44, 0x48, 0x4C
SC = 0x50                                          # scores [hand][13]: type 0-3, band 4-7, dir 8-9, break 10-12
N_SC, HAND = 13, 13 * 4
SC_TYPE, SC_BAND, SC_DIR, SC_BRK = 0, 4, 8, 10
SC_END = SC + 2 * HAND
WCOST = SC_END                                     # f32: the cost of a ball taken at the last decision (tests, docs)
HMARG = WCOST + 4                                  # f32 [hand]: the extra inside margin after HBPs (HBP_STEP each)
SIZE = HMARG + 8                                   # 0xC4
TEAM, G_PTR = 0x2A, -0x163C                        # G+0x2A: batting roster team; G = *(r13-0x163C)
LINEUP, ROSTER, RUNNERS = -0x15A8, -0x2C8, 0x807098C8
PERID_ROW = 8

# ---- constants block
MARK = 0x18C                                       # pitcher s16: a human's steer sum (FUN_80163C50), 0 at every pitch
                                                   # (FUN_8015CD34), never written for a CPU pitcher; 1 = our curve
STEER, STEER_ORIG = 0x80162394, 0xC0228EB0         # FUN_80162358's CPU branch: lfs f1,-0x7150(r2) (0.0)
STEER_RET, STEER_TAIL = 0x80162568, 0x80162538     # its epilogue; its tail (|+0xE8| >= 0.01 -> +0xF8; f0 = 0.0)
OPEN, CLOSE = 0x80627AC4, 0x80627AAC               # 0x80627AB4[4] = 8 m, 15 m: the human steer window (travel)
STEER_RANGE = 0x806279E0                           # [kind] f32 lo, hi: g before the per-character factor
STAT_RANGE = 0x806318E0 + 3 * 0xC                  # u16 min, max of the curve stat (0, 150)
TF_REF = (0x8016250C, 0x80162514)                  # lis r3 / addi r3 in FUN_80162358: the per-character "pitch
TF_STEER = 8                                       # steering" table (charbuild "throwfloats", 0xC per id), f32 +8
CHARFLOATS_REF = (0x800BDA1C, 0x800BDA20)          # FUN_800BD938: charbuild "charfloats" (0x24 per id, F4 at +0x10)
TRAJ_REF = (0x800BAEAC, 0x800BAEB0)                # FUN_800BADB4: "traj" (2 per id, hit curve at +1)
SELECTOR_REF = (0x8015C944, 0x8015C948)            # FUN_8015C940: "selector" (8 per id, model family at +2)
HBP_BOX = 0x8062A0D8                               # per family: u8 z top, reach toward the plate, away (cm)
DIRS, ACTIVE = 0x80626628, 0x80626570              # swing direction rows (stick 0) / active swing frames
MAGIC = -0x7140                                    # r2: the double 2^52 (u32 -> float)
CURVE_NOW, KIND_ROW, SPEED_DIV = 0x126, 0x134, -0x7340   # pitcher u16 curve now (fatigue in), u8 kind; r2 f32[Hz]
Z_RELEASE, Z_PLATE = 17.5, 0.4                     # INFERRED flight geometry of the model (as test_pitch_launch_star)
ZONE_FLAG, SWING_FLAG = 0xEE, 0xCE                 # pitcher u8: the umpire's strike (either plane); batter u8: a
BATTER, BATTER_ALT = -0x1D78, -0x1D7C              # swing started this pitch (FUN_800BB344); r13 batter pointers
PLANE1, PLANE2 = 0x8016291C, 0x801629D0            # FUN_801627E0: li r0,1 / li r0,2 before stb r0,0x13A(r29)
PLANE1_ORIG, PLANE2_ORIG = 0x38000001, 0x38000002
LEFTY, BOX_X = 0xB3, 0x44                          # batter: left-handed; box_x (plate-x units)
BIG = 2.0 ** 23

CONSTS = [("EDGE", EDGE), ("ZERO", 0.0), ("ONE", 1.0), ("TARGET", 0.0), ("SMIN", 0.0), ("SMAX", 0.0),
          ("X2P23", BIG), ("XBIAS", 127 * BIG), ("XMAX", 30.0), ("ALMOST", 0.9999), ("TMIN", T_MIN),
          ("HUNDRED", 100.0), ("CENT", 0.01), ("R_K", R_K), ("R_MISS", R_MISS), ("R_TAKEN", R_TAKEN),
          ("R_FOUL", R_FOUL), ("R_BALL", R_BALL), ("R_WALK", R_WALK), ("W_T", W_T), ("W_S", W_S),
          ("R_HBP", R_HBP), ("HBP_STEP", HBP_STEP), ("HBP_CAP", HBP_CAP),
          ("C0", C0), ("Q0", Q0), ("WALK", WALK), ("W_CAREFUL", W_CAREFUL), ("DCLAMP", DCLAMP), ("FADE", FADE),
          ("HOT_N", HOT_N), ("HOT_GAIN", 1.0 / HOT_N), ("MARGIN", MARGIN),
          ("P0_FIRST", 1 - P_FIRST / 100), ("P0_TAKEN", 1 - P_TAKEN / 100), ("P0_CHASE", 1 - P_CHASE / 100),
          *((f"CP{i}", v) for i, v in enumerate(CP_MULT)), *((f"RUN{i}", v) for i, v in enumerate(RUN_MULT)),
          *((f"COSTB{i}", v) for i, v in enumerate(COST_B)), *((f"S0_{i}", v) for i, v in enumerate(S0)),
          *((f"BLO{i}", v) for i, v in enumerate(BAND_LO)), *((f"BHI{i}", v) for i, v in enumerate(BAND_HI)),
          *((f"BANDT{i}", v) for i, v in enumerate(BAND_T)), *((f"BRKT{i}", v) for i, v in enumerate(BRK_T)),
          *((f"BRKS{i}", v) for i, v in enumerate(BRK_SCALE)), *((f"BRKP{i}", v) for i, v in enumerate(BRK_PRI)),
          *((f"DEEP{i}", v) for i, v in enumerate(DEEP_PRI)), *((f"DIR{i}", v) for i, v in enumerate(DIR_PRI)), *((f"B{i}", v) for i, v in enumerate(B))]
K = {n: 4 * i for i, (n, _) in enumerate(CONSTS)}
K_TIMING = 4 * len(CONSTS)                         # then TIMING: 4 swing types x 16 frames (f32)
K_TARGET = K["TARGET"]                             # a level 5 / 6 charged curve's plate x, written per pitch
LAYOUT = {}                                        # addresses of the last apply (tests)


def mix(level=6):
    """{FB_CUT, FB_TOP, FB_LOW, PLAIN6} at a level (level5.pair)."""
    me = sys.modules[__name__]
    return {n: level5.pair(me, n)[level - 4] for n in MIX}


def fb_chance(charge, curve_speed, m=None):
    m = m or mix()
    if charge <= curve_speed:
        return 0
    return m["FB_TOP"] if charge >= m["FB_CUT"] else m["FB_LOW"]


def peak(curve_speed, cu_mult, cu_arc):
    """The changeup's relative peak height: arc * 10000 / changeup speed^2 (0 for an empty row)."""
    speed = curve_speed * cu_mult
    return cu_arc * 10000 / speed ** 2 if speed > 0 else 0.0


def cu_chance(curve_speed, cu_mult, cu_arc):
    if curve_speed <= 0:
        return 0
    p = peak(curve_speed, cu_mult, cu_arc)
    (top_cut, top), (mid_cut, mid) = CU_TIERS
    if p >= top_cut:
        return top
    if p >= mid_cut or cu_mult > CU_FAST_MULT:
        return mid
    return CU_BASE


def tables(stats, m=None):
    """stats {id: dict(charge, curve_speed, cu_mult, cu_arc)} -> (FB bytes, CU bytes), ids 0..max (0 if missing).
    m: mix(level) (None: level 6's)."""
    n = max(stats) + 1 if stats else 0
    fb, cu = bytearray(n), bytearray(n)
    for cid, s in stats.items():
        fb[cid] = fb_chance(s["charge"], s["curve_speed"], m)
        cu[cid] = cu_chance(s["curve_speed"], s["cu_mult"], s["cu_arc"])
        assert fb[cid] + cu[cid] <= 100, cid
    return bytes(fb), bytes(cu)


def type_priors(fb, cu, plain=None):
    """PRI[id]: (fastball, changeup, plain curve, charged curve) / 100 (the old type roll's thresholds)."""
    out = []
    for f, u in zip(fb, cu):
        p = min(PLAIN6 if plain is None else plain, 100 - f - u)
        out.append((f / 100, u / 100, p / 100, max(0, 100 - f - u - p) / 100))
    return out


def table_at(read, ref):
    """A table's address from the game's own lis / addi (or subi) pair (charbuild repoints them for new ids)."""
    hi, low = (struct.unpack(">I", read(a, 4))[0] for a in ref)
    assert hi >> 26 == 15 and low >> 26 == 14, f"0x{ref[0]:08X}: not lis / addi ({hi:08X} {low:08X})"
    return (((hi & 0xFFFF) << 16) + ((low & 0xFFFF) ^ 0x8000) - 0x8000) & 0xFFFFFFFF


def throwfloats(read):
    """The per-character steering table's address (FUN_80162358's lis / addi)."""
    return table_at(read, TF_REF)


def read_stats(read, ids, stats_rows=STATS_ROWS, changeup=CHANGEUP):
    """The table inputs for `ids` through read(address, n) -> bytes (the DOL, or the build's data section)."""
    def u16(addr):
        return struct.unpack(">H", read(addr, 2))[0]
    field = {k: STAT_FIELDS[k][0] for k in ("curveball speed", "charge pitch speed", "curve", "charge power",
                                            "slap power", "star swing")}
    tf, cf, traj, sel = (table_at(read, r) for r in (TF_REF, CHARFLOATS_REF, TRAJ_REF, SELECTOR_REF))
    out = {}
    for cid in ids:
        row = stats_rows + cid * STATS_ROW
        mult, arc = struct.unpack(">ff", read(changeup + cid * 8, 8))
        steer = struct.unpack(">f", read(tf + cid * 0xC + TF_STEER, 4))[0]
        f4 = struct.unpack(">f", read(cf + cid * 0x24 + 0x10, 4))[0]
        family = read(sel + cid * 8 + 2, 1)[0]
        reach = read(HBP_BOX + 3 * family + 1, 1)[0]
        out[cid] = dict(charge=u16(row + field["charge pitch speed"]), curve_speed=u16(row + field["curveball speed"]),
                        cu_mult=mult, cu_arc=arc, curve=u16(row + field["curve"]), steer=steer,
                        charge_power=u16(row + field["charge power"]), slap_power=u16(row + field["slap power"]),
                        star_swing=read(row + field["star swing"], 1)[0], hit_curve=read(traj + cid * 2 + 1, 1)[0],
                        f4=f4, reach=reach)
    return out


def stock_stats(dol):
    return read_stats(dol.read, range(STOCK_MAX + 1))


def cp_band(cp):
    return 0 if cp < 40 else 1 if cp < 60 else 2 if cp < 80 else 3


def loopy(s):
    """The loopy star-swing threat (docs/star-swings.md): hit-curve flag 1 AND slap power < LOOPY_SLAP."""
    return s.get("hit_curve", 0) == 1 and s.get("slap_power", 0) < LOOPY_SLAP


def weak_next(s):
    """A truly weak next batter (the slugger exception): charge power < 60, no star swing, not the loopy swing."""
    return s.get("charge_power", 0) < 60 and s.get("star_swing", 0) == 0 and not loopy(s)


def hbp_edge0(s):
    """E0: the hit box edge |x| at box_x 0 (edge = E0 - box_x): |F4| - (reach + 1) / 100 (docs/hit-by-pitch.md)."""
    return abs(s.get("f4", -9.0)) - (s.get("reach", 0) + 1) / 100


def perid(stats, n):
    """PERID rows 0..n (n: the default row for an unknown id: never HBP-unsafe, CP band 1, not weak)."""
    out = bytearray()
    for cid in range(n):
        s = stats.get(cid, {})
        out += struct.pack(">fBBxx", hbp_edge0(s), cp_band(s.get("charge_power", 50)), int(weak_next(s)) if s else 0)
    return bytes(out + struct.pack(">fBBxx", 9.0, 1, 0))


def f32at(dol, addr):
    return struct.unpack(">f", dol.read(addr, 4))[0]


def timing_table(read):
    """TIMING[type][frame] (4 x 16 f32): the timing accuracy of a contact on that swing frame (docstring)."""
    out = []
    for t in range(4):
        row = [0.0] * 16
        if t < 3:
            act = struct.unpack(">15h", read(ACTIVE + (t != 0) * 0x1E, 30))
            dirs = struct.unpack(">30h", read(DIRS + t * 0x3C, 0x3C))
            mids = [(dirs[2 * f] + dirs[2 * f + 1]) / 2 for f in range(15)]
            frames = [f for f in range(15) if act[f]]
            p = frames[0]
            for f0, f1 in zip(frames, frames[1:]):
                if mids[f0] <= 0 <= mids[f1]:
                    p = f0 + (0 - mids[f0]) / (mids[f1] - mids[f0]) if mids[f1] != mids[f0] else f0
                    break
            d = max(abs(f - p) for f in frames)
            for f in frames:
                row[f] = max(0.0, 1 - abs(f - p) / d)
        out += row
    return out


def flight_consts(dol, hz=0):
    """The game's numbers the bend model uses (Hz byte 0, 60 Hz)."""
    r2 = 0x8079EDC0
    row = struct.unpack(">7h", dol.read(0x806277DC + 1 * 0xE + hz * 0xEE, 14))      # kind 1: every normal pitch
    smin, smax = struct.unpack(">HH", dol.read(STAT_RANGE, 4))
    return dict(div=f32at(dol, r2 + SPEED_DIV + hz * 4), decay=f32at(dol, r2 - 0x7338 + hz * 4),
                plate=f32at(dol, 0x8079794C), accel=row[3] * 0.001, drag_at=row[4], open=f32at(dol, OPEN),
                close=f32at(dol, CLOSE), lo=f32at(dol, STEER_RANGE + 8), hi=f32at(dol, STEER_RANGE + 12),
                smin=smin, smax=smax, perfect=f32at(dol, 0x80627BA8))


def steer_per_frame(curve, steer, k):
    """g: the most a human's steer input (+-1) moves +0xE8 in one frame (FUN_80162358)."""
    span = k["smax"] - k["smin"]
    t = min(max((curve - k["smin"]) / span, 0.0), 1.0) if span else 1.0
    return (k["lo"] + (k["hi"] - k["lo"]) * t) * steer


def max_bend(g, speed, k, z0=Z_RELEASE, zp=Z_PLATE):
    """The sideways bend at the plate of a pitch at `speed` steered one way by g every frame of the window
    (FUN_80160938's order each frame: drag, steer, decay, move; the plate crossing interpolated)."""
    if speed <= 0:
        return 0.0
    v, z, e, d = -speed / k["div"], z0, 0.0, 0.0
    thr = (100 - k["drag_at"]) * k["plate"] / 100
    while True:
        if z <= thr and v - v * k["accel"] < -0.05:
            v -= v * k["accel"]
        if k["open"] <= z0 - z <= k["close"]:
            e += g
        v *= k["decay"]
        zn = z + v
        if zn <= zp:
            return d + e * (z - zp) / (z - zn)
        d, z = d + e, zn


def perfect_speed(charge, k):
    """FUN_8015EFE0 with +0x13B == 3: (int)(charge pitch speed * 1.2f) & 0xFF."""
    return int(struct.unpack(">f", struct.pack(">f", charge * k["perfect"]))[0]) & 0xFF


def bends(stats, k):
    """Bc[id]: the planned charged-curve bend (m), BEND_MARGIN of the fresh max at a perfect charge (<= BEND_CAP)."""
    n = max(stats) + 1 if stats else 0
    out = [0.0] * n
    for cid, s in stats.items():
        if s.get("curve") and s.get("steer"):
            g = steer_per_frame(s["curve"] & 0xFF, s["steer"], k)
            out[cid] = min(BEND_CAP, BEND_MARGIN * max_bend(g, perfect_speed(s["charge"], k), k))
    return out


# ---------------------------------------------------------------------------------------------------- assembly
def _or(a, ra, rs, rb):
    return a.word(x_form(rs, ra, rb, 444))


def _lfd(a, ft, d, ra):
    return a.word(d_form(50, ft, ra, d))


def _lfsx(a, ft, ra, rb):
    return a.word(x_form(ft, ra, rb, 535))


def _stfsx(a, fs, ra, rb):
    return a.word(x_form(fs, ra, rb, 663))


def _fabs(a, t, b):
    return a.word((63 << 26) | (t << 21) | (b << 11) | (264 << 1))


def _fmadd(a, t, fa, fc, fb):
    """Double precision t = fa * fc + fb."""
    return a.word((63 << 26) | (t << 21) | (fa << 16) | (fb << 11) | (fc << 6) | (29 << 1))


def _xori(a, ra, rs, imm):
    return a.word(d_form(26, rs, ra, imm))


def _gate(a, stock, reg):
    """Branch to `stock` unless level 5 (level5.FLAG) at level 4 with the normal brain (r30 = brain). Uses r0, `reg`
    (free at the site: its stock instruction writes it) and cr0."""
    level5.gate(a, reg, stock, "cpu-pitching")
    a.lbz(0, LEVEL, 30).cmplwi(0, L4).bne(stock)
    a.lwz(0, TUTORIAL, 13).cmpwi(0, 0).bne(stock)


def _slot(a, rd, rt, state, tag):
    """rd = the state block of the batting team (G+0x2A; team 0 without G). Uses rt (r0 allowed) and cr0."""
    a.lwz(rd, G_PTR, 13).li(rt, 0).cmpwi(rd, 0).beq(tag)
    a.lbz(rt, TEAM, rd)
    a.label(tag)
    a.andi_(rt, rt, 1).mulli(rt, rt, SIZE)
    a.load_addr(rd, state).add(rd, rd, rt)


def _params(a, rd, rt, params, tag):
    """rd = PARAMS[level]: FLAG 4 -> block 0, FLAG 1 -> block 1, FLAG 2 -> block 2."""
    a.load_addr(rd, params)
    a.lis(rt, ha(level5.FLAG)).lbz(rt, lo(level5.FLAG), rt)
    a.cmpwi(rt, 1).bne(tag + "_not5")
    a.addi(rd, rd, PSIZE).b(tag)
    a.label(tag + "_not5")
    a.cmpwi(rt, 2).bne(tag)
    a.addi(rd, rd, PSIZE * 2)
    a.label(tag)


def _batter(a, rd, tag):
    a.lwz(rd, BATTER, 13).cmpwi(rd, 0).bne(tag)
    a.lwz(rd, BATTER_ALT, 13)
    a.label(tag)


def _hand(a, rd, rb, tag):
    """rd = the hand block offset in a state block (SC + hand * HAND); rb = the batter (may be 0). Uses cr0."""
    a.li(rd, 0).cmpwi(rb, 0).beq(tag)
    a.lbz(rd, LEFTY, rb).andi_(rd, rd, 1).mulli(rd, rd, HAND)
    a.label(tag)
    a.addi(rd, rd, SC)


def _count_above(a, rd, fv, kbase, rk, n, tag):
    """rd = how many of the n thresholds consts[kbase + 4i] (rk = consts) fv is at or above. Uses r3, f3, cr0."""
    a.li(rd, 0).li(3, kbase)
    a.label(tag)
    _lfsx(a, 3, rk, 3).fcmpo(fv, 3).blt(tag + "_x")
    a.addi(rd, rd, 1).addi(3, 3, 4).cmpwi(rd, n).blt(tag)
    a.label(tag + "_x")


def pick_fn(at, consts):
    """pick(r3 scores f32[n], r4 priors f32[n] (overwritten: the weights), r5 n, f1 T) -> r3 the index drawn with
    P ~ prior * 2^(score / T) (2^x: the float exponent trick, x clamped to +-30). Uses r0 r3-r10, f0-f6; LR saved;
    uniform(0, 1) (the game RNG) once."""
    a = Asm(at)
    a.stwu(1, -0x20, 1).mflr(0).stw(0, 0x24, 1)
    a.mr(8, 3).mr(9, 4).slwi(10, 5, 2)
    a.load_addr(7, consts)
    a.lfs(0, K["TMIN"], 7).fcmpo(1, 0).bge("t_ok").fmr(1, 0)
    a.label("t_ok")
    a.lfs(4, K["ONE"], 7).fdivs(4, 4, 1)                   # f4 = 1 / T
    a.lfs(5, K["ZERO"], 7)                                  # f5 = W
    a.li(6, 0)
    a.label("w")
    _lfsx(a, 1, 8, 6).fmuls(1, 1, 4)
    a.lfs(2, K["XMAX"], 7).fcmpo(1, 2).ble("w_hi").fmr(1, 2)
    a.label("w_hi")
    a.fneg(2, 2).fcmpo(1, 2).bge("w_lo").fmr(1, 2)
    a.label("w_lo")
    a.lfs(2, K["X2P23"], 7).lfs(3, K["XBIAS"], 7)
    _fmadd(a, 1, 1, 2, 3)
    a.fctiwz(1, 1).stfd(1, 8, 1).lwz(0, 0xC, 1).stw(0, 8, 1).lfs(1, 8, 1)   # 2^x
    _lfsx(a, 2, 9, 6).fmuls(1, 1, 2)
    _stfsx(a, 1, 9, 6).fadds(5, 5, 1)
    a.addi(6, 6, 4).cmpw(6, 10).blt("w")
    a.lfs(6, K["ALMOST"], 7).fmuls(5, 5, 6)                 # target < W: always inside a bucket
    a.lfs(1, K["ZERO"], 7).lfs(2, K["ONE"], 7)
    a.lwz(3, RNG, 13).bl(UNIFORM)
    a.fmuls(1, 1, 5)
    a.fsubs(6, 6, 6).li(3, 0).li(6, 0)
    a.label("c")
    _lfsx(a, 2, 9, 6).fadds(6, 6, 2).fcmpo(1, 6).blt("out")
    a.addi(6, 6, 4).addi(3, 3, 1).cmpw(6, 10).blt("c")
    a.addi(3, 3, -1)
    a.label("out")
    a.lwz(0, 0x24, 1).mtlr(0).addi(1, 1, 0x20).blr()
    return a


def type_stub(at, pri, n, state, pick, pri4=None, pri5=None):
    a = Asm(at)
    _gate(a, "stock", 3)
    a.lha(4, CHAR_ID, 31).li(0, 0).cmplwi(4, n).bge("picked")   # (unsigned: a negative id too) plain
    a.stwu(1, -0x20, 1)
    a.slwi(4, 4, 4)
    pri4 = pri if pri4 is None else pri4
    pri5 = pri if pri5 is None else pri5
    if pri4 == pri5 == pri:
        a.load_addr(5, pri)
    else:
        level5.pick_addr(a, 5, pri4, pri5, pri)
    a.add(4, 4, 5)
    for i in range(4):
        a.lwz(0, 4 * i, 4).stw(0, 8 + 4 * i, 1)                  # the prior mix (pick overwrites it)
    _slot(a, 3, 0, state, "slot")
    _batter(a, 7, "bat")
    _hand(a, 6, 7, "hand")
    a.lfs(1, TEMP, 3).add(3, 3, 6)                              # r3 = the type scores (SC_TYPE 0)
    a.addi(4, 1, 8).li(5, 4).bl(pick)
    a.addi(1, 1, 0x20)
    a.cmpwi(3, 0).li(0, 1).beq("picked")                        # fastball
    a.cmpwi(3, 1).li(0, 2).beq("picked")                        # changeup
    a.cmpwi(3, 2).li(0, 0).beq("picked")                        # plain curve
    a.li(0, 1).li(5, 1).sth(5, MARK, 31)                        # a charged pitch, marked a charged curve
    a.label("picked")
    a.b(TYPE_PICKED)
    a.label("stock")
    a.word(TYPE_ORIG)                                           # lwz r3,-0x1D38(r13)
    a.b(TYPE + 4)
    return a


def _add1(a, off, rbase, fone):
    a.lfs(2, off, rbase).fadds(2, 2, fone).stfs(2, off, rbase)


def loc_stub(at, consts, state, params):
    """Frame 1: the side, then the learning update for the last pitch, the pitching change and the temperatures.
    r31 = state, r29 = params, r28 = consts (restored by the epilogue); a 0x20 frame (8..11: the used factors)."""
    a = Asm(at)
    _gate(a, "stock", 28)
    a.lwz(3, RNG, 13).li(4, 2).bl(RAND)                        # s: 0 -> left, 1 -> right
    a.load_addr(28, consts).lfs(0, K["EDGE"], 28)
    a.cmpwi(3, 0).bne("side").fneg(0, 0)
    a.label("side")
    a.stfs(0, AIM, 30)
    a.stwu(1, -0x20, 1)
    _slot(a, 31, 3, state, "slot")
    _params(a, 29, 3, params, "lvl")
    a.lbz(0, PEND, 31).cmpwi(0, 0).beq("clear")
    # ---- the reward (f1); f13 = the pitch's situation multiplier; r6 != 0: the at-bat goes on
    a.lwz(5, COUNT, 13).lbz(6, STRIKES, 5).lbz(7, BALLS, 5)
    _or(a, 6, 6, 7)
    a.lfs(13, PMULT, 31)
    a.lbz(0, HBP, 31).cmpwi(0, 0).beq("no_hbp")
    a.lbz(7, PHAND, 31).slwi(7, 7, 2).addi(7, 7, HMARG).add(7, 7, 31)   # this hand's inside margin += HBP_STEP
    a.lfs(0, 0, 7).lfs(1, K["HBP_STEP"], 28).fadds(0, 0, 1)
    a.lfs(1, K["HBP_CAP"], 28).fcmpo(0, 1).ble("hm_ok").fmr(0, 1)
    a.label("hm_ok")
    a.stfs(0, 0, 7)
    a.lfs(1, K["R_HBP"], 28).b("have_r")                        # a hit batter: R_HBP (unclamped, below)
    a.label("no_hbp")
    a.lbz(0, CONTACT, 31).cmpwi(0, 0).beq("no_contact")
    a.cmpwi(6, 0).beq("in_play")
    a.lfs(1, K["R_FOUL"], 28).b("have_r")                       # contact, the at-bat goes on: a foul
    a.label("in_play")
    a.lbz(3, CTYPE, 31).lbz(4, CFRAME, 31).slwi(3, 3, 4).add(3, 3, 4).slwi(3, 3, 2).addi(3, 3, K_TIMING)
    _lfsx(a, 2, 28, 3)                                          # f2 = timing accuracy
    a.lfs(3, K["ONE"], 28).lbz(0, CZONE, 31).cmpwi(0, 2).beq("sweet")
    a.lfs(0, CF, 31).lfs(4, K["HUNDRED"], 28).fsubs(0, 0, 4)
    _fabs(a, 0, 0)
    a.lfs(4, K["CENT"], 28).fnmsubs(3, 0, 4, 3)                 # 1 - |f - 100| / 100
    a.lfs(0, K["ZERO"], 28).fcmpo(3, 0).bge("sweet").fmr(3, 0)
    a.label("sweet")                                            # f3 = sweet-spot accuracy
    a.lfs(4, K["W_T"], 28).fmuls(2, 2, 4).lfs(4, K["W_S"], 28).fmadds(1, 3, 4, 2)
    a.fmuls(1, 1, 13).fneg(1, 1).b("have_r")
    a.label("no_contact")
    a.lbz(0, SEEN, 31).cmpwi(0, 0).beq("clear")                 # nothing seen: nothing learned
    a.lbz(0, SWUNG, 31).cmpwi(0, 0).bne("swing")
    a.lbz(0, ZONE, 31).cmpwi(0, 0).bne("taken")
    a.lfs(1, K["R_BALL"], 28)
    a.lbz(0, PB, 31).cmpwi(0, 3).bne("have_r")
    a.lfs(1, K["R_WALK"], 28).b("have_r")                       # ball four
    a.label("swing")
    a.lfs(1, K["R_MISS"], 28).b("k2")
    a.label("taken")
    a.lfs(1, K["R_TAKEN"], 28)
    a.label("k2")
    a.lbz(0, PK, 31).cmpwi(0, 2).bne("have_r")
    a.lfs(1, K["R_K"], 28).fmuls(1, 1, 13)                      # strike three
    a.label("have_r")
    # ---- strike? (r10), the band (r9) and break (r8) as measured, else as intended (nothing latched)
    a.lbz(0, SEEN, 31).cmpwi(0, 0).bne("measured")
    a.lbz(9, PBAND, 31).lbz(8, PBRK, 31)
    a.li(10, 0).cmplwi(9, 1).bgt("classified").li(10, 1).b("classified")
    a.label("measured")
    a.lbz(10, ZONE, 31)
    a.lfs(2, XACT, 31)
    _fabs(a, 2, 2)
    _count_above(a, 9, 2, K["BANDT0"], 28, 3, "band")
    a.lfs(2, XACT, 31).lfs(3, XAIM, 31).fsubs(2, 2, 3)
    _fabs(a, 2, 2)
    _count_above(a, 8, 2, K["BRKT0"], 28, 2, "brk")
    a.label("classified")
    # ---- opponent stats and PREV (1 taken strike, 2 chased ball)
    a.lbz(3, SWUNG, 31).lbz(4, CONTACT, 31)
    _or(a, 5, 3, 4)                                             # r5: he swung
    a.li(7, 0).lfs(12, K["ONE"], 28)
    a.cmpwi(10, 0).bne("strike_side")
    _add1(a, BT, 31, 12)
    a.cmpwi(5, 0).beq("no_chase")
    _add1(a, SW, 31, 12)
    a.li(7, 2)
    a.label("no_chase")
    a.lbz(0, PK, 31).cmpwi(0, 2).bne("prev")
    _add1(a, B2, 31, 12)
    a.cmpwi(3, 0).beq("prev").cmpwi(4, 0).bne("prev")
    _add1(a, K2, 31, 12)                                        # a 2-strike ball swung through: strikeout chasing
    a.b("prev")
    a.label("strike_side")
    a.cmpwi(5, 0).bne("s_value").li(7, 1)
    a.label("s_value")                                          # S[PK] += ALPHA (r - S0[PK] - S[PK])
    a.lbz(3, PK, 31).slwi(3, 3, 2).addi(4, 3, S_)
    _lfsx(a, 2, 31, 4)
    a.addi(3, 3, K["S0_0"])
    _lfsx(a, 3, 28, 3)
    a.fsubs(3, 1, 3).fsubs(3, 3, 2).lfs(4, P_["ALPHA"], 29).fmadds(2, 3, 4, 2)
    _stfsx(a, 2, 31, 4)
    a.label("prev")
    a.stb(7, PREV, 31)
    # ---- the factor update: used = type, band (+ direction, break for a curve)
    a.lbz(3, PHAND, 31).mulli(3, 3, HAND).addi(3, 3, SC)
    a.lbz(0, PTYPE, 31).stb(0, 8, 1).addi(0, 9, SC_BAND).stb(0, 9, 1).li(6, 2)
    a.lbz(7, PDIR, 31).cmplwi(7, 1).bgt("n_used")
    a.addi(0, 7, SC_DIR).stb(0, 10, 1).addi(0, 8, SC_BRK).stb(0, 11, 1).li(6, 4)
    a.label("n_used")
    for phase in (0, 1):
        if phase:
            a.lfs(3, MEAN, 31).fsubs(4, 1, 3).fsubs(4, 4, 2)       # delta = r - MEAN - v, clamped
            a.lbz(0, HBP, 31).cmpwi(0, 0).bne("c_hbp")             # a hit batter: no clamp, MEAN kept
            a.lfs(5, K["DCLAMP"], 28).fcmpo(4, 5).ble("c_hi").fmr(4, 5)
            a.label("c_hi")
            a.fneg(5, 5).fcmpo(4, 5).bge("c_lo").fmr(4, 5)
            a.label("c_lo")
            a.lfs(5, P_["ALPHA"], 29).fsubs(6, 1, 3).fmadds(3, 6, 5, 3).stfs(3, MEAN, 31)
            a.b("c_go")
            a.label("c_hbp")
            a.lfs(5, P_["ALPHA"], 29)
            a.label("c_go")
            a.fmuls(4, 4, 5)                                        # ALPHA * delta
        else:
            a.lfs(2, K["ZERO"], 28)                                 # v = the sum of the used scores
        a.li(7, 0)
        a.label(f"f{phase}")
        a.addi(4, 1, 8).lbzx(4, 4, 7).slwi(4, 4, 2).add(4, 4, 3)
        _lfsx(a, 5, 31, 4)
        if phase:
            a.fadds(5, 5, 4)
            _stfsx(a, 5, 31, 4)
        else:
            a.fadds(2, 2, 5)
        a.addi(7, 7, 1).cmpw(7, 6).blt(f"f{phase}")
    a.label("clear")                                            # the latch and PEND
    a.li(0, 0)
    for off in range(0, PEND + 1, 4):
        a.stw(0, off, 31)
    # ---- a pitching change: fade the scores, raise the temperatures for HOT_N pitches
    a.lwz(4, PITCHER, 13).cmpwi(4, 0).bne("p_have").lwz(4, PITCHER_ALT, 13)
    a.label("p_have")
    a.lha(5, CHAR_ID, 4).addi(5, 5, 1).lha(6, LASTP, 31).cmpw(5, 6).beq("temps")
    a.sth(5, LASTP, 31).cmpwi(6, 0).beq("temps")                # (the first pitch of the match: no change)
    a.lfs(2, K["FADE"], 28).li(7, SC)
    a.label("fade")
    _lfsx(a, 3, 31, 7).fmuls(3, 3, 2)
    _stfsx(a, 3, 31, 7)
    a.addi(7, 7, 4).cmpwi(7, SC_END).blt("fade")
    a.lfs(2, K["HOT_N"], 28).stfs(2, HOT, 31)
    a.label("temps")                                            # T x (1 + HOT / HOT_N); HOT counts down
    a.lfs(2, HOT, 31).lfs(3, K["HOT_GAIN"], 28).lfs(4, K["ONE"], 28).fmadds(3, 2, 3, 4)
    a.lfs(5, P_["T"], 29).fmuls(5, 5, 3).stfs(5, TEMP, 31)
    a.lfs(5, P_["TB"], 29).fmuls(5, 5, 3).stfs(5, TEMPB, 31)
    a.fsubs(2, 2, 4).lfs(5, K["ZERO"], 28).fcmpo(2, 5).bge("hot").fmr(2, 5)
    a.label("hot")
    a.stfs(2, HOT, 31)
    a.addi(1, 1, 0x20)
    a.b(LOC_DONE)
    a.label("stock")
    a.word(LOC_ORIG)                                           # lwz r28,-0x1580(r13)
    a.b(LOC + 4)
    return a


def _pick2(a, pick, scores_reg, scores_off, temp_off, n=2):
    """r3 = pick(scores_reg + scores_off, r1 + 0x10 (the priors), n, [r31 + temp_off])."""
    a.addi(3, scores_reg, scores_off).addi(4, 1, 0x10).li(5, n).lfs(1, temp_off, 31).bl(pick)


def aim_stub(at, consts, state, params, bend, perid_tab, n, pick):
    """The pitch frame's placement. r31 = state (restored by the epilogue), r11 = params, r12 = consts; a 0x40
    frame: 0x08 scores, 0x10 priors, 0x20 hand block offset, 0x24 the batter's PERID row, 0x28 RISP, 0x2C the
    pitcher, 0x30 the side (1: +x), 0x34 curving (0 no, 1 plain, 2 charged), 0x38 dir. f13 = mult, f12 = |X|,
    f11 = the planned break."""
    a = Asm(at)
    _gate(a, "stock", 3)
    a.lbz(0, TRAINING, 30).cmpwi(0, 0).bne("done")
    a.lbz(0, KIND, 30).cmplwi(0, 2).beq("done")                # star pitch: its own path (not learned)
    a.stwu(1, -0x40, 1)
    _slot(a, 31, 3, state, "slot")
    _params(a, 11, 3, params, "lvl")
    a.load_addr(12, consts)
    # ---- the batter: hand, PERID row
    _batter(a, 7, "bat")
    _hand(a, 6, 7, "hand")
    a.stw(6, 0x20, 1)
    a.addi(0, 6, -SC).li(6, HAND)
    a.word(x_form(3, 0, 6, 459))                                # divwu r3,r0,r6 -> the hand (0 / 1)
    a.stb(3, PHAND, 31)
    a.li(4, n).cmpwi(7, 0).beq("row")
    a.lha(4, CHAR_ID, 7).cmplwi(4, n).ble("row").li(4, n)
    a.label("row")
    a.slwi(4, 4, 3).load_addr(5, perid_tab).add(4, 4, 5).stw(4, 0x24, 1)
    # ---- the count, the situation multiplier
    a.lwz(5, COUNT, 13).lbz(6, STRIKES, 5).lbz(7, BALLS, 5).lbz(8, OUTS, 5)
    a.stb(6, PK, 31).stb(7, PB, 31)
    a.lbz(3, 4, 4).slwi(3, 3, 2).addi(3, 3, K["CP0"])
    _lfsx(a, 13, 12, 3)                                         # f13 = CP_MULT[band]
    a.load_addr(3, RUNNERS).li(9, 0)                            # r9: bit 0 2nd, bit 1 3rd
    for base, bit in ((2, 1), (3, 2)):
        a.lwz(4, 4 * base, 3).cmpwi(4, 0).beq(f"r{base}")
        a.lbz(4, 0x176, 4).cmpwi(4, 0).beq(f"r{base}").ori(9, 9, bit)
        a.label(f"r{base}")
    a.li(4, 0).stw(9, 0x28, 1).cmpwi(9, 0).beq("runm")         # index: 0 none / 1st only
    a.li(4, 1).cmpwi(8, 2).bge("runm")                          # RISP, 2 outs
    a.li(4, 2).cmpwi(9, 2).blt("runm").li(4, 3)                 # RISP 0-1 outs; 3rd 0-1 outs
    a.label("runm")
    a.slwi(4, 4, 2).addi(4, 4, K["RUN0"])
    _lfsx(a, 0, 12, 4)
    a.fmuls(13, 13, 0).stfs(13, PMULT, 31)
    # ---- ball or strike: dVb against dVs = S[strikes]
    a.lfs(2, P_["N0"], 11).lfs(3, K["C0"], 12).lfs(4, SW, 31).fmadds(4, 3, 2, 4)
    a.lfs(5, BT, 31).fadds(5, 5, 2).fdivs(9, 4, 5).fsubs(4, 9, 3)   # f9 = c, f4 = c - C0
    a.cmpwi(7, 3).bge("walk_cost")
    a.slwi(3, 7, 2).addi(3, 3, K["COSTB0"])
    _lfsx(a, 5, 12, 3)
    a.b("have_cost")
    a.label("walk_cost")                                        # the next batter: L + 0xC + T*0x28 + (idx % 9)*4
    a.load_addr(9, perid_tab + PERID_ROW * n)                   # default: the unknown-id row
    a.lwz(3, LINEUP, 13).cmpwi(3, 0).beq("next")
    a.lwz(4, G_PTR, 13).cmpwi(4, 0).beq("next")
    a.lbz(5, 0x2C, 4).add(6, 3, 5).lbz(6, 0x80, 6).cmplwi(6, 9).blt("idx").li(6, 0)
    a.label("idx")
    a.mulli(5, 5, 0x28).add(3, 3, 5).slwi(6, 6, 2).add(3, 3, 6).lha(6, 0xC, 3)
    a.lwz(3, ROSTER, 13).cmpwi(3, 0).beq("next")
    a.lbz(5, TEAM, 4).mulli(5, 5, 0x4FE).add(3, 3, 5).mulli(6, 6, STATS_ROW).add(3, 3, 6).lhz(6, 0, 3)
    a.cmplwi(6, n).bge("next")
    a.slwi(6, 6, 3).load_addr(9, perid_tab).add(9, 9, 6)
    a.label("next")
    a.lbz(3, 4, 9).slwi(3, 3, 2).addi(3, 3, K["CP0"])
    _lfsx(a, 5, 12, 3)
    a.lfs(0, K["WALK"], 12).fmuls(5, 5, 0)                      # WALK x the next batter's multiplier
    a.lbz(0, 5, 9).cmpwi(0, 0).beq("have_cost")                 # slugger exception: next truly weak,
    a.lwz(0, 0x28, 1).cmpwi(0, 0).beq("have_cost")              # runners in scoring position,
    a.lwz(3, 0x24, 1).lbz(0, 4, 3).cmplwi(0, 2).blt("have_cost")   # this batter's charge power >= 60
    a.lfs(5, K["W_CAREFUL"], 12)
    a.label("have_cost")                                        # f5 = cost of a ball taken now
    a.stfs(5, WCOST, 31)
    a.lbz(0, PK, 31).cmpwi(0, 2).bne("dvb0")
    a.lfs(3, K["Q0"], 12).lfs(6, K2, 31).fmadds(6, 3, 2, 6)
    a.lfs(0, B2, 31).fadds(0, 0, 2).fdivs(6, 6, 0).fsubs(6, 6, 3)
    a.lfs(0, K["R_K"], 12).fmuls(6, 6, 0).fmuls(6, 6, 13).b("dvb")
    a.label("dvb0")
    a.lfs(6, K["R_MISS"], 12).fmuls(6, 6, 4)
    a.label("dvb")
    a.fmadds(6, 4, 5, 6)                                        # + (c - C0) * cost
    a.lbz(3, PK, 31).slwi(3, 3, 2).addi(4, 3, S_).addi(3, 3, K["S0_0"])
    _lfsx(a, 7, 12, 3)
    _lfsx(a, 8, 31, 4)
    a.fadds(8, 7, 8)                                            # Vs = S0[k] + S[k]
    a.fnmsubs(6, 9, 8, 6).lfs(3, K["C0"], 12).fmadds(6, 3, 7, 6)   # - c * Vs + C0 * S0[k]
    a.stfs(6, 0xC, 1).lfs(0, K["ZERO"], 12).stfs(0, 8, 1)      # the ball's advantage over its prior; strike 0
    # the prior P0 (a ball): 0-0 first pitch / after a taken strike / after a chase (< 3 balls) / plain
    kb = 12
    if K5 is not None:                                          # level 5's own P0_* (r5: RAND clobbers it below)
        level5.pick(a, 5, K4 - K["P0_FIRST"], K5 - K["P0_FIRST"], 0).add(5, 5, 12)
        kb = 5
    a.lbz(3, PB, 31).lbz(4, PK, 31)
    _or(a, 0, 3, 4)
    a.lfs(2, K["P0_FIRST"], kb).cmpwi(0, 0).beq("p0")
    a.lbz(0, PREV, 31)
    a.lfs(2, K["P0_TAKEN"], kb).cmpwi(0, 1).beq("p0")
    a.lfs(2, K["P0_CHASE"], kb).cmpwi(0, 2).bne("p0_plain").cmpwi(3, 3).blt("p0")
    a.label("p0_plain")
    a.lfs(2, P_["P0_PLAIN"], 11)
    a.label("p0")
    a.lfs(0, K["ONE"], 12).fsubs(0, 0, 2).stfs(0, 0x10, 1).stfs(2, 0x14, 1)
    a.lwz(3, RNG, 13).li(4, 100).bl(RAND)                       # the floor / cap roll
    a.lbz(4, PB, 31).cmpwi(4, 1).bgt("cap")
    a.lwz(0, P_["FLOOR"], 11).cmpw(3, 0).blt("ball")
    a.b("bs")
    a.label("cap")
    a.cmpwi(4, 3).bne("bs")
    a.lbz(5, PK, 31).cmplwi(5, 2).ble("capk").li(5, 2)         # 3 balls: CAP3[strikes]
    a.label("capk")
    a.slwi(5, 5, 2).add(5, 5, 11)
    a.lwz(0, P_["CAP3"], 5).cmpw(3, 0).bge("strike")
    a.lwz(0, P_["FORCE3"], 11).cmpwi(0, 0).bne("ball")          # level 5: a fixed rate (stock level 4's)
    a.label("bs")
    a.addi(3, 1, 8).addi(4, 1, 0x10).li(5, 2).lfs(1, TEMPB, 31).bl(pick)
    a.cmpwi(3, 0).beq("strike")
    a.label("ball")
    a.lfs(0, P_["PRI_JUST"], 11).stfs(0, 0x10, 1).lfs(0, P_["PRI_FAR"], 11).stfs(0, 0x14, 1)
    a.lwz(6, 0x20, 1).add(6, 6, 31)
    _pick2(a, pick, 6, 4 * (SC_BAND + 2), TEMP)
    a.addi(3, 3, 2).b("band")
    a.label("strike")
    a.lfs(0, K["DEEP0"], 12).stfs(0, 0x10, 1).lfs(0, K["DEEP1"], 12).stfs(0, 0x14, 1)
    a.lwz(6, 0x20, 1).add(6, 6, 31)
    _pick2(a, pick, 6, 4 * SC_BAND, TEMP)
    a.label("band")
    a.stb(3, PBAND, 31)
    a.slwi(3, 3, 2).addi(4, 3, K["BLO0"])
    _lfsx(a, 1, 12, 4)
    a.addi(4, 3, K["BHI0"])
    _lfsx(a, 2, 12, 4)
    a.cmpwi(3, 12).bne("uni").lfs(2, P_["FAR_HI"], 11)
    a.label("uni")
    a.lwz(3, RNG, 13).bl(UNIFORM).fmr(12, 1)                    # f12 = |X|
    # ---- the type (PTYPE) and whether it curves
    a.lwz(4, PITCHER, 13).cmpwi(4, 0).bne("p_have").lwz(4, PITCHER_ALT, 13)
    a.label("p_have")
    a.stw(4, 0x2C, 1)
    a.lbz(0, KIND, 30).lha(5, MARK, 4).li(6, 0)                 # r6: curving
    a.li(3, 1).cmpwi(0, 3).beq("type")                          # changeup
    a.li(3, 2).cmpwi(0, 0).bne("fb")
    a.lbz(0, CURVE_DIR, 4).cmplwi(0, 4).beq("pc").cmplwi(0, 5).bne("type")
    a.label("pc")
    a.li(6, 1).b("type")                                        # a plain curve that curves
    a.label("fb")
    a.li(3, 0).cmpwi(5, 0).beq("type").li(3, 3).li(6, 2)        # fastball / charged curve
    a.label("type")
    a.stb(3, PTYPE, 31).stw(6, 0x34, 1)
    a.li(0, 0xFF).stb(0, PDIR, 31).stb(0, PBRK, 31)
    a.lfs(11, K["ZERO"], 12)
    a.cmpwi(6, 0).beq("side")
    # ---- direction (toward / away from the batter)
    a.lfs(0, K["DIR0"], 12).stfs(0, 0x10, 1).lfs(0, K["DIR1"], 12).stfs(0, 0x14, 1)
    a.lwz(6, 0x20, 1).add(6, 6, 31)
    _pick2(a, pick, 6, 4 * SC_DIR, TEMP)
    a.stb(3, PDIR, 31)
    a.lwz(0, 0x34, 1).cmpwi(0, 2).beq("charged")
    a.lwz(4, 0x2C, 1)                                           # a plain curve: B by tertile / late
    a.lbz(5, TERTILE, 4).cmplwi(5, 2).ble("tertile").li(5, 2)
    a.label("tertile")
    a.slwi(5, 5, 3)
    a.lbz(0, LATE, 4).cmpwi(0, 0).beq("early").addi(5, 5, 4)
    a.label("early")
    a.addi(5, 5, K["B0"])
    _lfsx(a, 11, 12, 5)
    _count_above(a, 7, 11, K["BRKT0"], 12, 2, "pbrk")
    a.stb(7, PBRK, 31).b("side")
    a.label("charged")                                          # break size: Bc[id] x BRK_SCALE
    for i in range(3):
        a.lfs(0, K[f"BRKP{i}"], 12).stfs(0, 0x10 + 4 * i, 1)
    a.lwz(6, 0x20, 1).add(6, 6, 31)
    _pick2(a, pick, 6, 4 * SC_BRK, TEMP, n=3)
    a.stb(3, PBRK, 31)
    a.slwi(3, 3, 2).addi(3, 3, K["BRKS0"])
    _lfsx(a, 0, 12, 3)
    a.lwz(4, 0x2C, 1).lha(5, CHAR_ID, 4).slwi(5, 5, 2).load_addr(6, bend)   # (the type stub marks ids < n only)
    _lfsx(a, 11, 6, 5)
    a.fmuls(11, 11, 0)
    # ---- the side (from LOCATION), moved away when the pitch could hit him
    a.label("side")
    a.lfs(0, AIM, 30).lfs(1, K["ZERO"], 12).li(5, 1).fcmpo(0, 1).bge("s").li(5, 0)
    a.label("s")
    a.lbz(0, PHAND, 31)
    a.word(x_form(5, 3, 0, 316))                                # xor r3,r5,r0 -> 0: inside (RH at -x, LH at +x)
    a.lbz(4, PDIR, 31)
    a.cmpwi(3, 0).bne("safe")
    a.fmr(2, 12)
    a.lwz(0, 0x34, 1).cmpwi(0, 0).beq("need")
    a.cmpwi(4, 0).beq("need")                                   # inside + toward him: breaks out from inside
    a.fadds(2, 2, 11)                                           # inside + away: starts B further in
    a.label("need")
    if K5 is None:
        a.lfs(0, K["MARGIN"], 12)
    else:                                                       # level 5's own (r7 is loaded next)
        level5.pick(a, 7, K4 + 12, K5 + 12, K["MARGIN"]).add(7, 7, 12).lfs(0, 0, 7)
    a.fadds(2, 2, 0)
    a.lbz(7, PHAND, 31).slwi(7, 7, 2).addi(7, 7, HMARG)        # + this team / hand's extra after HBPs
    _lfsx(a, 0, 31, 7)
    a.fadds(2, 2, 0)
    a.lwz(6, 0x24, 1).lfs(0, 0, 6)                              # E0
    a.lwz(6, BATTER, 13).cmpwi(6, 0).bne("bx").lwz(6, BATTER_ALT, 13).cmpwi(6, 0).beq("safe")
    a.label("bx")
    a.lfs(1, BOX_X, 6).fsubs(0, 0, 1)                           # edge = E0 - box_x
    a.fcmpo(2, 0).ble("safe")
    _xori(a, 5, 5, 1)
    a.li(3, 1)                                                  # the other side
    a.label("safe")
    a.stw(5, 0x30, 1)
    # out (breaks away from the centre) = toward him XNOR inside: (dir XOR inside') where inside' = (r3 == 0)
    a.word(x_form(4, 6, 3, 316))                                # xor r6,r4,r3: 1 -> breaks toward the centre
    # ---- the aim
    a.fmr(1, 12)
    a.lwz(4, 0x2C, 1).lwz(0, 0x34, 1).cmpwi(0, 0).beq("sign")
    a.cmpwi(0, 2).beq("c_aim")
    a.li(7, 5).cmpwi(5, 0).beq("cd").li(7, 4)                   # toward the centre: +x -> 4, -x -> 5
    a.label("cd")
    a.cmpwi(6, 0).bne("cd_in")
    _xori(a, 7, 7, 1)                                           # away from the centre
    a.label("cd_in")
    a.stb(7, CURVE_DIR, 4).b("bmag")
    a.label("c_aim")
    a.fmr(3, 12).cmpwi(5, 0).bne("tgt").fneg(3, 3)
    a.label("tgt")
    a.stfs(3, K_TARGET, 12)                                     # X, where STEER ends the pitch
    a.li(0, 0).stb(0, CURVE_DIR, 4)                             # no bow (a human's charged pitch has none)
    a.label("bmag")
    a.cmpwi(6, 0).beq("b_in")
    a.fadds(1, 1, 11).b("sign")                                 # toward the centre: start B wide
    a.label("b_in")
    a.fsubs(1, 1, 11)                                           # away from it: start B inside
    a.label("sign")
    a.cmpwi(5, 0).bne("store").fneg(1, 1)
    a.label("store")
    a.stfs(1, AIM, 30)                                          # the target: the mover walks the cursor there (GLIDE)
    a.li(0, 1).stb(0, PEND, 31)
    a.addi(1, 1, 0x40)
    a.label("done")                                             # GLIDE: latch, hold until he is on the spot (WAIT)
    a.load_addr(12, GLIDE)
    a.li(0, 1).stb(0, 0, 12)
    a.lwz(6, BATTER, 13).cmpwi(6, 0).bne("g_bx").lwz(6, BATTER_ALT, 13).cmpwi(6, 0).beq("g_nb")
    a.label("g_bx")
    a.lfs(0, BOX_X, 6).stfs(0, 4, 12)                           # his box x now (the HBP side test's)
    a.label("g_nb")
    a.li(3, 0).b(DECIDE + 4)
    a.label("stock")
    a.word(DECIDE_ORIG)                                         # li r3,1
    a.b(DECIDE + 4)
    return a


def move_stub(at):
    """MOVE (docstring GLIDE): the mover from frame 1 at levels 5 / 6. r0 = the frame; r30 = the brain (the caller's)."""
    a = Asm(at)
    a.mr(5, 0)
    _gate(a, "m_stock", 6)
    a.cmpwi(5, 1).b(MOVE_RET)
    a.label("m_stock")
    a.cmpwi(5, 0x1E).b(MOVE_RET)
    return a


def wait_stub(at):
    """WAIT (docstring GLIDE). r31 = the frame, r30 = the brain; r0, r3, r4, r12, f0, f1 free (the stock path rewrites
    r0 / r3 / r4 before any read)."""
    a = Asm(at)
    _gate(a, "w_stock", 4)
    a.load_addr(12, GLIDE)
    a.cmpwi(31, 1).bne("w_latch")
    a.li(0, 0).stb(0, 0, 12).stb(0, 1, 12)                      # a new pitch: frame 1 is stock's (location, learning)
    a.b("w_hold")
    a.label("w_latch")
    a.lbz(0, 0, 12).cmpwi(0, 0).beq("w_decide")                 # not decided yet: decide now (no random wait)
    a.lwz(4, PITCHER, 13).cmpwi(4, 0).bne("w_p").lwz(4, PITCHER_ALT, 13)
    a.label("w_p")
    a.lfs(0, CURSOR, 4).lfs(1, AIM, 30).fcmpo(0, 1).bne("w_hold")   # not on the spot yet
    a.lbz(0, READY, 30).cmpwi(0, 0).beq("w_hold")
    a.lwz(3, BATTER, 13).cmpwi(3, 0).bne("w_b").lwz(3, BATTER_ALT, 13).cmpwi(3, 0).beq("w_go")
    a.label("w_b")
    a.lbz(0, BATTER_BUSY, 3).cmpwi(0, 0).bne("w_hold")
    a.lfs(0, BOX_X, 3).lfs(1, 4, 12).fsubs(0, 0, 1)
    _fabs(a, 0, 0)
    a.lfs(1, 8, 12).fcmpo(0, 1).ble("w_go")                     # he hasn't moved: pitch
    a.lbz(0, 1, 12).cmplwi(0, REDECIDE_MAX).bge("w_go")
    a.addi(0, 0, 1).stb(0, 1, 12).li(0, 0).stb(0, 0, 12)        # he moved: decide again
    a.b("w_decide")
    a.label("w_go")
    a.li(0, 0).stb(0, 0, 12).li(3, 1).b(BRAIN_RET)
    a.label("w_hold")
    a.li(3, 0).b(BRAIN_RET)
    a.label("w_decide")
    a.b(WAIT_GO)
    a.label("w_stock")
    a.word(WAIT_ORIG).b(WAIT_RET)
    return a


def clamp_stub(at):
    """Called in place of the remap (f1 aim, f2 / f3 = -0.4 / 0.4 input range, LR = 0x8015DCE8)."""
    a = Asm(at)
    a.fcmpo(1, 2).blt("out")
    a.fcmpo(1, 3).bgt("out")
    a.b(REMAP)                                                  # inside (or NaN): the stock remap, bit for bit
    a.label("out")
    a.blr()                                                     # outside: unclamped
    return a


def steer_stub(at, consts, tf):
    """FUN_80162358's CPU branch (r31 = pitcher; its frame: LR at 0x54, 0x43300000 at 0x28 / 0x30, f31 saved).
    Unmarked: 0.0, as stock. A level 5 / 6 charged curve: the human steer (+0xE8, added to the ball x every frame), driven
    closed loop: inside the window, E = (X - x) * -vz / (z - zp) - vx is the +0xE8 that ends the pitch on X from here;
    +0xE8 moves toward it by at most g (a human's full input) a frame. Outside the window, +0xE8 as it is."""
    a = Asm(at)
    a.lha(0, MARK, 31).cmpwi(0, 0).beq("stock")
    a.lfs(1, 0x70, 31).lfs(0, 0x40, 31).fsubs(6, 1, 0)           # f6 = travel
    a.lis(3, ha(OPEN)).lfs(0, lo(OPEN), 3).fcmpo(6, 0).blt("held")
    a.lis(3, ha(CLOSE)).lfs(0, lo(CLOSE), 3).fcmpo(6, 0).bgt("held")
    a.lhz(0, CURVE_NOW, 31).stw(0, 0x2C, 1)
    _lfd(a, 1, 0x28, 1)
    _lfd(a, 0, MAGIC, 2)
    a.fsubs(1, 1, 0)                                             # f1 = the curve now
    a.load_addr(5, consts).lfs(2, K["SMIN"], 5).lfs(3, K["SMAX"], 5)
    a.lbz(0, KIND_ROW, 31).slwi(0, 0, 3).load_addr(3, STEER_RANGE).add(3, 3, 0)
    a.lfs(4, 0, 3).lfs(5, 4, 3)
    a.bl(REMAP)                                                  # (a leaf: f0-f5 only; LR is reloaded at 0x54)
    a.lha(0, CHAR_ID, 31).mulli(0, 0, 0xC).load_addr(3, tf + TF_STEER)
    _lfsx(a, 0, 3, 0)
    a.fmuls(7, 1, 0)                                             # f7 = g
    a.lfs(2, 0x40, 31).lfs(0, 0x64, 31).fsubs(2, 2, 0)           # f2 = z - zp
    a.lfs(0, -0x7150, 2).fcmpo(2, 0).ble("held")
    a.lfs(1, K_TARGET, 5).lfs(0, 0x38, 31).fsubs(1, 1, 0)        # X - x
    a.lfs(0, 0x58, 31).fmuls(1, 1, 0).fneg(1, 1).fdivs(1, 1, 2)  # * -vz / (z - zp)
    a.lfs(0, 0x50, 31).fsubs(1, 1, 0)                            # - vx: the E that ends on X
    a.lfs(0, 0xE8, 31).fsubs(1, 1, 0)                            # the step, capped to +-g
    a.fcmpo(1, 7).ble("up").fmr(1, 7)
    a.label("up")
    a.fneg(2, 7).fcmpo(1, 2).bge("down").fmr(1, 2)
    a.label("down")
    a.fadds(1, 0, 1).stfs(1, 0xE8, 31)
    a.lfs(0, -0x7150, 2)
    a.b(STEER_TAIL)                                              # stock tail: +0xF8 if |E| >= 0.01, return E
    a.label("held")
    a.lfs(1, 0xE8, 31).b(STEER_RET)
    a.label("stock")
    a.word(STEER_ORIG)                                           # lfs f1,-0x7150(r2)
    a.b(STEER_RET)
    return a


def plane_stub(at, state):
    """Called in place of FUN_801627E0's `li r0,plane` at either umpire plane (r29 = pitcher; r0, r3, r4 and cr0 are
    dead there, LR was saved by its prologue). Every level and pitcher: it writes only the batting team's latch
    (docstring PLANE), then li r0,1 or 2 by the caller (LR)."""
    a = Asm(at)
    _slot(a, 3, 0, state, "slot")
    a.lbz(0, ZONE_FLAG, 29).stb(0, ZONE, 3)
    a.li(0, 1).stb(0, SEEN, 3)
    a.lwz(0, 0x38, 29).stw(0, XACT, 3).lwz(0, 0x5C, 29).stw(0, XAIM, 3)
    _batter(a, 4, "have")
    a.cmpwi(4, 0).beq("end")
    a.lbz(0, SWING_FLAG, 4).lbz(4, SWUNG, 3)
    _or(a, 0, 0, 4).stb(0, SWUNG, 3)
    a.label("end")
    a.mflr(3).load_addr(4, PLANE1 + 4).cmpw(3, 4)
    a.li(0, 2).bne("r").li(0, 1)
    a.label("r")
    a.blr()
    return a


def contact_stub(at, state):
    """Called in place of FUN_800bd2f0's `lwz r3,-0x1580(r13)` after the contact score (r29 = batter; r0 and r3-r12
    are dead right after the bl it follows). Records the contact (docstring CONTACT), then the stock load."""
    a = Asm(at)
    _slot(a, 3, 4, state, "slot")
    a.li(0, 1).stb(0, CONTACT, 3)
    a.lbz(0, 0xBA, 29).stb(0, CZONE, 3)
    a.lha(0, 0x84, 29).cmplwi(0, 15).ble("f").li(0, 15)            # (unsigned: a negative frame too)
    a.label("f")
    a.stb(0, CFRAME, 3)
    a.lbz(0, 0xB6, 29).cmplwi(0, 3).ble("t").li(0, 3)
    a.label("t")
    a.stb(0, CTYPE, 3)
    a.lwz(0, 0x60, 29).stw(0, CF, 3)
    a.word(CONTACT_ORIG)                                           # lwz r3,-0x1580(r13)
    a.blr()
    return a


def hbp_stub(at, state):
    """Called in place of FUN_801634B8's `stb r0,0xD1(r31)` (r0 = 1; r3 is loaded next, r0 reloaded before use)."""
    a = Asm(at)
    a.word(HBP_ORIG)                                               # stb r0,0xD1(r31)
    _slot(a, 3, 4, state, "slot")
    a.li(0, 1).stb(0, HBP, 3)
    a.blr()
    return a


EXTRA_RESET = []   # [(address, size)]: more per-match state zeroed with the model's (cpu_track's level 5 mind game)


def reset_stub(at, state):
    """Called in place of FUN_800C364C's `stb r5,0x1A(r3)` (the CPU manager at a match start; r8-r10 and ctr are
    free, as the level 5 stub before it): zero both state blocks (and EXTRA_RESET), then the stock store."""
    a = Asm(at)
    for k, (addr, size) in enumerate([(state, 2 * SIZE)] + EXTRA_RESET):
        assert addr % 4 == 0 and size % 4 == 0
        a.load_addr(9, addr - 4).li(8, size // 4).mtctr(8).li(8, 0)
        a.label(f"z{k}")
        a.stwu(8, 4, 9)
        a._emit(lambda pc, k=k: bc(pc, a.labels[f"z{k}"], 16, 0))   # bdnz
    a.word(RESET_ORIG)
    a.blr()
    return a


SITES = ((TYPE, TYPE_ORIG), (LOC, LOC_ORIG), (DECIDE, DECIDE_ORIG), (CLAMP, CLAMP_ORIG), (STEER, STEER_ORIG),
         (PLANE1, PLANE1_ORIG), (PLANE2, PLANE2_ORIG), (CONTACT_AT, CONTACT_ORIG), (HBP_AT, HBP_ORIG),
         (RESET_AT, RESET_ORIG), (MOVE_AT, MOVE_ORIG), (WAIT_AT, WAIT_ORIG))
LINKED = (CLAMP, PLANE1, PLANE2, CONTACT_AT, HBP_AT, RESET_AT)   # hooked with bl (the stub returns)


def ball_map(top, hi):
    """(scale, off): e in (0, top] -> EDGE + e * scale + off in (BALL_LO, hi] (the old ball band; docs only)."""
    return (hi - BALL_LO) / top, BALL_LO - EDGE


def params_blob():
    out = b""
    for lvl in (0, 1, 2):
        for name in PARAM_NAMES:
            v = PARAMS[name][lvl]
            out += struct.pack(">i", v) if name in INT_PARAMS else struct.pack(">f", v)
    return out


def apply(dol, code, data, stats):
    """Tables and constants into `data`, stubs into `code` (charbuild Spaces), hooks into `dol`. Returns log lines."""
    apply_data(dol, data, stats)
    return apply_code(dol, code)


def apply_data(dol, data, stats):
    """The build's first half (charbuild's data phase): the stock words checked, tables, constants and the state
    blocks into `data`; their addresses in LAYOUT. apply_code places the stubs later (their own section)."""
    for site, orig in SITES:
        got = dol.u32(site)
        assert got == orig, f"0x{site:08X}: 0x{got:08X}, expected 0x{orig:08X}"
    for addr, want in ((OPEN, 8.0), (CLOSE, 15.0), (STEER_RANGE + 8, 0.0008), (STEER_RANGE + 12, 0.002)):
        got = f32at(dol, addr)
        assert abs(got - want) < 1e-6, f"0x{addr:08X}: {got}, expected {want}"
    k = flight_consts(dol)
    tf = throwfloats(dol.read)
    fb_bytes, cu_bytes = tables(stats)
    n = len(fb_bytes)
    bend_floats = bends(stats, k)
    timing = timing_table(dol.read)
    vals = {name: v for name, v in CONSTS}
    vals.update(SMIN=float(k["smin"]), SMAX=float(k["smax"]))
    global K4, K5
    me = sys.modules[__name__]
    kvals = [level5.pair(me, name) for name in K5_NAMES]
    base_tail = 4 * len(CONSTS) + 4 * len(timing)
    
    
    need_tail = any(v4 != v6 or v5 != v6 for v4, v5, v6 in kvals)
    tail = b""
    K4 = K5 = None
    if need_tail:
        K4, K5 = base_tail, base_tail + 16
        f4, f5, f6 = kvals[0]; t4, t5, t6 = kvals[1]; c4, c5, c6 = kvals[2]; m4, m5, m6 = kvals[3]
        tail = (struct.pack(">4f", 1 - f4 / 100, 1 - t4 / 100, 1 - c4 / 100, m4) +
                struct.pack(">4f", 1 - f5 / 100, 1 - t5 / 100, 1 - c5 / 100, m5))
    consts = data.put(b"".join(struct.pack(">f", vals[name]) for name, _ in CONSTS)
                      + struct.pack(f">{len(timing)}f", *timing) + tail, align=4)
    params = data.put(params_blob(), align=4)
    pri = data.put(b"".join(struct.pack(">4f", *p) for p in type_priors(fb_bytes, cu_bytes)), align=4)
    perid_tab = data.put(perid(stats, n), align=4)
    bend = data.put(struct.pack(f">{n}f", *bend_floats), align=4)
    state = data.put(bytes(2 * SIZE), align=4)
    global GLIDE
    GLIDE = data.put(bytes(8) + struct.pack(">f", BOX_EPS), align=4)
    pri4 = pri5 = pri
    if mix(4) != mix(6):
        fb4, cu4 = tables(stats, mix(4))
        pri4 = data.put(b"".join(struct.pack(">4f", *p) for p in type_priors(fb4, cu4, mix(4)["PLAIN6"])), align=4)
    if mix(5) != mix(6):
        fb5, cu5 = tables(stats, mix(5))
        pri5 = data.put(b"".join(struct.pack(">4f", *p) for p in type_priors(fb5, cu5, mix(5)["PLAIN6"])), align=4)
    LAYOUT.update(pri4=pri4, pri5=pri5)
    LAYOUT.update(glide=GLIDE, consts=consts, params=params, pri=pri, perid=perid_tab, state=state, n=n, bend=bend,
                  bends=bend_floats, flight=k, throwfloats=tf, timing=timing, fb=fb_bytes, cu=cu_bytes)


def apply_code(dol, code):
    """The second half: the stubs into `code` (charbuild: a Space of SECTION bytes of its own, above the data
    section) and the hooks into `dol`, on apply_data's LAYOUT. Returns log lines (the code size and the headroom)."""
    consts, params, pri, perid_tab, state, n, bend, tf = (LAYOUT[x] for x in ("consts", "params", "pri", "perid",
                                                                             "state", "n", "bend", "throwfloats"))
    pri4 = LAYOUT.get("pri4", pri)
    pri5 = LAYOUT.get("pri5", pri)
    bend_floats, fb_bytes, cu_bytes = LAYOUT["bends"], LAYOUT["fb"], LAYOUT["cu"]
    start = code.here
    out = []
    at = code.here + (-code.here % 4)
    blob = pick_fn(at, consts).assemble()
    assert code.put(blob, align=4) == at
    LAYOUT["pick"] = pick = at
    out.append(f"pick 0x{at:08X} ({len(blob) // 4} words)")
    total = len(blob)
    for name, sites, make in (("type", (TYPE,), lambda at: type_stub(at, pri, n, state, pick, pri4, pri5)),
                              ("location", (LOC,), lambda at: loc_stub(at, consts, state, params)),
                              ("aim", (DECIDE,), lambda at: aim_stub(at, consts, state, params, bend, perid_tab, n,
                                                                     pick)),
                              ("clamp", (CLAMP,), clamp_stub),
                              ("steer", (STEER,), lambda at: steer_stub(at, consts, tf)),
                              ("planes", (PLANE1, PLANE2), lambda at: plane_stub(at, state)),
                              ("contact", (CONTACT_AT,), lambda at: contact_stub(at, state)),
                              ("hbp", (HBP_AT,), lambda at: hbp_stub(at, state)),
                              ("reset", (RESET_AT,), lambda at: reset_stub(at, state)),
                              ("move", (MOVE_AT,), move_stub), ("wait", (WAIT_AT,), wait_stub)):
        at = code.here + (-code.here % 4)
        blob = make(at).assemble()
        assert code.put(blob, align=4) == at
        for site in sites:
            dol.w32(site, branch(site, at, link=site in LINKED))
        LAYOUT[name] = at
        total += len(blob)
        out.append(f"{name} {'/'.join(f'0x{s:08X}' for s in sites)} -> 0x{at:08X} ({len(blob) // 4} words)")
    fast = sum(1 for v in fb_bytes if v == FB_TOP)
    cu30 = sum(1 for v in cu_bytes if v == 30)
    cu10 = sum(1 for v in cu_bytes if v == 10)
    return [f"cpu pitching (levels 5 / 6): a per-game learning pitch model (type, zone band, curve direction, break "
            f"size; scores per batting team and hand, zeroed at match start; learning rate {PARAMS['ALPHA'][0]} / "
            f"{PARAMS['ALPHA'][1]}, temperature {PARAMS['T'][0]} / {PARAMS['T'][1]} (level 5 / 6)); priors: "
            f"fastballs {FB_TOP}% for {fast} ids (charge >= {FB_CUT}), changeups 30% for {cu30} ids, 10% for {cu10}, "
            f"plain curves {PLAIN6}%, the rest charged curves steered onto the target (planned bend "
            f"{min((b for b in bend_floats if b), default=0):.2f}..{max(bend_floats, default=0):.2f} m); balls far off "
            f"at |x| {BALL_LO}..{BALL_HI} ({BALL_HI5} at level 5); ball / strike by the chase stats (floor "
            f"{PARAMS['FLOOR'][1]}% / {PARAMS['FLOOR'][0]}%; 3 balls: level 6 at most {PARAMS['CAP3'][1]}% balls, level "
            f"5 {PARAMS['CAP3'][0]} / {PARAMS['CAP3_1'][0]} / {PARAMS['CAP3_2'][0]}% at 3-0 / 3-1 / 3-2 as stock level 4); HBP margin {MARGIN} m at the batter's live box; "
            f"ids 0..0x{n - 1:X}, state 0x{state:08X} (2 x 0x{SIZE:X}), code {total} B "
            f"(0x{code.here - start:X} B from 0x{start:08X}, 0x{code.limit - code.here:X} B left in its space); "
            + ", ".join(out)]
