"""Level 5 and 6 CPU rundowns (Nick, 2026-09-27, the "rundown redo" in docs/cpu-ai-weaknesses.md). Both levels run
the same body (level5.FLAG 1 or 2; levels 1-4 stock):
1. A runner going forward (a steal too) or stopped between bases: the NEXT base (runner +0x17E, dir 1 of
   FUN_800E0F98), thrown at once (the moment the holder has the ball; only a winning chase comes first). HALFWAY
   (Nick, 2026-09-28: "don't throw to the next base unless they are at least halfway there", then 3/8): an advancing
   runner under FORWARD_MIN (3/8) of the leg (+0xA8 < 0.375) is held (base + 10) instead. FUN_800E0F98
   times a throw to the cover fielder
   (c = ai+0x2EE[b], s16; its +0x1DC = his ETA, frames): ball time (flight + windup + catch) < ETA -> hold (b + 10), the
   holder's own run < ETA + 5 -> he carries it. +0x1DC is his remaining distance / current speed (huge while he
   accelerates, stale while he stands, -1 / 0 on the base), so with the catcher still getting back to the plate the
   plan waited and the throw came for a close play (Nick, 3rd -> home at level 5 / 6: he won it on running ability).
   Going forward / stopped, the call runs with c's +0x1DC = -1 (on the base; restored after): the plan throws to b with
   the margin ball - runner (no wait for the cover, no carry on a stale ETA, no hold), a carry only when the holder is
   within 4 frames of b (or stock's carry cases: no cover, the
   cover is the holder, the ball within 3.0 of b). The throw itself (FUN_800CABF0 -> FUN_800DDE5C) still reads c's
   real +0x1DC and slows the ball (x0.9, up to 5 times) while its flight is shorter, so it leads a late cover.
   (2026-09-28, ad514f1 also held a forward / stopped runner until EARLY_LEAD frames before he was committed to the
   next base, mirrored lead rule below; Nick: a human going to 2nd was held on and was SAFE at 2nd. Removed: going
   forward it throws at once again, as 47b72c8.)
   A runner heading back (+0x183 == 3): the out at the BASE
   BEHIND him (the base he came from, +0x17D, dir 0), with FUN_800E0F98's own throw / carry / hold choice (timed for
   the out). Never the stock chase-and-tag (carry 9). (Nick: "throw to the next base, then when I am running back time
   it to get the out at the previous base"; the first redo planned the base behind always and threw to 1st on a steal.)
   Heading back, the throw waits for the cover (the throw base b becomes b + 10, FUN_800E0F98's own "hold") until the
   runner can no longer get away by turning round when he sees the throw, re-planned every frame. History (Nick): no
   hold = "WAY too early", a fixed 8 frames = "a little too late", the catch timed up to v/(2a) + 1.0/v frames before
   him (17-28) = too early again: a CPU runner turned at the release and the rundown looped for ever.
   What a runner does when the ball is thrown [C] (docs/runners.md "When the ball is thrown"): FUN_801783a0 (the CPU
   runner's command, each frame) calls FUN_8017ed54 while the ball is in flight. For a runner heading back
   (+0x183 == 3) to the base the ball is thrown to (field+0x2FC == +0x17D):
   - inside 0.2 of the leg (+0xA8 < r2-0x703C, ball zone game+0x2A6B <= 3) he never turns: command 0;
   - else he keeps going back if +0x142 < the ball's frames left (game+0x2A42, - the class fudge 0x80624AE8, + 15
     inside 0.4 of the leg), and turns (command 1) if the ball beats him: at the release, not at the catch.
   Turning (FUN_8017a430): command 1 while +0x183 == 3 accelerates at +0xDC * +0x11C (0.005 m/frame^2 at every speed
   stat), so from v he still covers v^2 / 0.01 m (2.25 m from 0.15) before he stops. A human can turn at any time.
   So, heading back with the plan throwing to base b (0..3), at the release (W = the holder's windup,
   FUN_8011A66C: 6 / 12 frames, 0 with ability 12) it throws now when any of:
   - he is committed: u = -+0xC4 (his speed back, m/frame) > 0 and d_r - u^2 / (2 * +0xDC * +0x11C) <= 1.8 - 0.8
     (r2-0x7A58 - r2-0x7A9C: the tag reach from his safe line), d_r = +0x9C * +0xAC - u * W (metres past his safe
     line at the release). He can't stop short of the tag any more (and a human's reaction only makes it surer);
   - a CPU runner (settings *(r13-0x1D58) +0x24 + game(*(r13-0x163C))+0x2C != 0, the flag FUN_8017ed54 reads) with
     the ball zone <= 3 is inside FUN_8017ed54's no-turn line at the release: +0xA8 - u * W / +0xAC < 0.2;
   - the out is slipping away anyway: a CPU runner: m >= 0 (the ball doesn't beat his +0x142, so he won't turn); a
     human: m' = m + R - R * cap / (cap + +0x104) >= 0 (R = +0x142; a mashing runner, FUN_80179df4, goes up to
     +0x104 = 0.02 m/frame over the cap +0xE0 * +0x114).
   Else hold. No runner numbers: the human rule's m' is NaN -> throw.
   THE DEADLINE, EVERY THROW BACK (Nick, 2026-09-28: the 70% "needs to be so that if I kept going I would get out, it
   throws 20 frames before I would be safe"; the 30% never late): the last frame the ball (W + the planner's flight
   to b, FUN_800CA018(b's x, z), the same call FUN_800E0F98 makes) still reaches b TAG_BUFFER frames before the
   runner's best time there, d / v (d = +0x9C * +0xAC, metres to his safe line; v = cap + +0x104 for a human, a
   masher, and the cap for a CPU runner). The early roll (docstring 4) throws EARLY_LEAD (20) frames before it:
   W + flight + THROW_LAG + TAG_BUFFER + 1 + EARLY_LEAD > d / v, nothing about when he could still turn back (so if he keeps
   going he is out). The hold roll throws at the committed moment above (or the slip test) or at the deadline itself
   (W + flight + THROW_LAG + TAG_BUFFER + 1 > d / v), whichever comes first. Already past it when the holder gets the ball: thrown
   at once. No runner numbers (NaN): thrown. No holder: the hold roll's committed rule (nobody to throw anyway).
   TAG_BUFFER = 10 frames for the catch + tag, INFERRED: the planner's own catch animation (byte table 0x8062B678, 5
   per character, column 0 the plain catch: 7-15 frames, mostly 9 / 11) [C]; a tag is a distance test (+0x90 within
   1.8), no frame window [C]; how many frames after the catch the tag lands is not measured.
   Never going forward / stopped (thrown at once, above).
   History: ad514f1 L = 10 with the slip test on m + L; then (Nick, a human heading back safe almost every time) L =
   20 frames before the committed moment with this deadline on the early roll only; then (Nick, 2026-09-28, still
   safe) the rule above: the early roll off the deadline alone, the deadline on the hold roll too.
2. Chase (Nick: "Yeah we can add a chase"; his video: after the catch the runner stood 2-3 m off 3rd, outside the tag,
   and the fielder never went at him). First, for any runner this body plans (going forward, back or stopped): the
   holder chases and tags him (carry 9, the stock chase-and-tag FUN_80113370; throw -1) when he gets to him before
   the runner can reach safety, dashing if he has Ball Dash:
   - the runner's escape base E = the base he is heading for (below; until 2026-09-28 the one of his two bases farther
     from the ball, field+0x29BC[b]); his frames there R = +0x140 (E = to-base) / +0x142 (E = from-base), which count his
     braking / turning and top speed (FUN_80178c84), taken as the game estimates them (R' = R; until 2026-09-28 made worst-case for a masher, R * cap / (cap + mash));
   - the holder must be within the tag reach (1.8 m, r2-0x7A58) of him when he reaches his safe line: the point P on
     the leg (0.03 + 1.8 / leg) of the way from E to the other base O. Getting to P first means passing or reaching
     him. t = FUN_80114350(P, holder) (the game's own run-time estimate, with his acceleration) / k, k = the Ball
     Dash factor (1.3, or 1.15 when *(r13-0x94) != 0; 1 without the ability or with *(r13-0x644) != 0);
   - ANY HOLDER (Nick, 2026-09-28: "if the fielder can beat the batter to the base or the batter is stopped then run
     them down"; "anyone should follow those rules, it just matters the most for ball dash"): a runner stopped
     between bases (+0x183 == 2) in the rundown zone (ai+0x2D4[r], "in a rundown") is chased at once; otherwise E is
     the base he is HEADING FOR (to-base advancing,
     from-base heading back), and he is chased when t < R' (margin = (int)(t - R')), no slack. (Before: E the base
     farther from the ball, and t + CHASE_SLACK < R', CHASE_SLACK = 6 frames for the stock chase's
     turn / pick-up: a guess, not measured.) Else the plans below.
3. Heading back only (never a runner going forward / stopped): if the fielder holding the ball has Ball Dash
   (fielding ability 10), he carries the ball to that base himself when the dash gets him there before the runner.
4. Random throw-back timing (Nick: levels 5 and 6): a throw decision is one possession: the body tracks the ball
   holder (field+0x2A4C) and each time a different fielder has the ball (a caught throw) it counts a throw and rolls
   once with the game's RNG, rand(100) = FUN_80165C14(*(r13-0x1578), 100), as the stock CPU does: < EARLY_PCT (70;
   FIRST_PCT 90 for the first throw, throw 0: Nick, 2026-09-28 "90% of the time on the first throw then 70% for the
   next 9 throws")
   -> "early": heading back, EARLY_LEAD frames before the deadline (docstring 1); else the hold rule (committed at the
   release, never past the deadline). Going forward / stopped the roll changes nothing: thrown at once (docstring 1). The roll holds for that
   possession, so it is not re-rolled every frame. From the MAX_RANDOM-th (10th) throw of a rundown on it is always
   the hold rule, so a rundown can't loop for ever. A rundown = one play: the count resets when the play frame
   *(s16 *)*(r13-0x1684) goes back (a new play) or jumps more than NEW_RUNDOWN (120) frames past the last body run.
   The first holder (who fielded it) is throw 0. State: STATE words after the body (+0 the last play frame, +4 the
   last holder, +8 throws, +12 the roll: 1 early / 0 the hold rule). Chase and Ball Dash come first as before.

FUN_800E05E8 plans one non-forced runner between bases (docs/cpu-ai-weaknesses.md "## 3. Rundowns"): it writes
ai+0x29C[r] (throw base; base+10 = hold for the cover; -1 none), ai+0x28C[r] (carry base; 9 = chase and tag) and
ai+0x27C[r] (margin, frames: < 0 = the out is makeable). r27 = ai, r29 = 4 * r, r30 = the runner, r31 = the field
(*(r13-0x1D94)). Its two branches both start by reading the runner's direction +0x183:
- IN  0x800E06C8 `lbz r5,0x183(r30)`: the rundown zone (ball->to + ball->from < 32.0 and +0x185 == 0), after the
  zone byte ai+0x2D4[r] = 1 is written (kept at level 6).
- OUT 0x800E0990 `lbz r0,0x183(r30)`: everything else.
Each hook is a `b` to a stub: FLAG == 0 (levels 1-4) -> the stock instruction and `b` back (scratch r12 and cr0 only;
FUN_800E05E8 never reads r12 and both sites' next compare rewrites cr0 before any read); FLAG 1 / 2 -> the shared
level 5 / 6 body, which ends at the epilogue 0x800E0F60 (it restores r28-r31 and the FPRs, so the body may use r28 / r31).

Level 6 body:
- No plan (epilogue, nothing written, as stock) unless the runner is advancing (+0x183 == 1), retreating (3), or
  stopped between bases (2 with +0x138 < 0); stock writes nothing for the others either.
- FUN_800E0F98(ai, r, 0, &throw, &carry) -> m, as stock's own dir-0 calls do; commit throw / carry / m unchanged
  (stock commits the raw dir-0 plan the same way at 0x800E0A1C).
- Ball Dash: CONFIRMED passive. There is no button: FUN_8011B600 (the fielders' run speed, called every frame by
  the run states FUN_80112218 / FUN_80112BC4) multiplies the speed +0xE4 by 1.3 (r2-0x7430; 1.15 = r2-0x742C when
  *(r13-0x94) != 0) whenever the fielder is the ball holder (+0x21C == field+0x2A4C), his ability (vtable +0x3C,
  i.e. stats byte 10) is 10, and *(r13-0x644) == 0. It works for the CPU too, carrying or chasing. What the CPU
  lacks is planning for it: FUN_800E0F98's carry time FUN_80114350 uses the unboosted top speed +0xEC. So at level 6,
  when the holder has Ball Dash and the dash is on (*(r13-0x644) == 0): t = FUN_80114350(base behind, holder) / k
  (k = 1.3 or 1.15, read from the same constants so ability-edits apply); if t < the runner's mashing frames to that
  base (R' = R * cap / (cap + mash)): carry = the base behind, throw = -1, margin = (int)(t - R'). Else the plan above stands.
Holder = field+0x2A4C (s16, < 0 none) looked up like FUN_800E0F98: 0x80708D9C[i & 0xFF], else 0x80708DC0[i & 0xFF],
else 0x80708D78[i]. Base behind = +0x17D, 0 if > 3 (FUN_800E0F98's mask); its x / z at 0x80625798 + 8 * base.
Test: scripts/test_cpu_rundown.py.
"""
import struct
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
import level5  # noqa: E402
from ppc import Asm, branch, d_form, ha, lo  # noqa: E402

LEVEL6 = 2                                         # level5.FLAG at level 6 (1 at level 5: the same body)
EPILOGUE = 0x800E0F60
PLAN_ONE, RUN_FRAMES = 0x800E0F98, 0x80114350      # FUN_800E0F98 (plan one base), FUN_80114350 (frames to x, z)
HOOK_IN, ORIG_IN = 0x800E06C8, 0x88BE0183          # lbz r5,0x183(r30)
HOOK_OUT, ORIG_OUT = 0x800E0990, 0x881E0183        # lbz r0,0x183(r30)
THROW, CARRY, MARGIN = 0x29C, 0x28C, 0x27C
HOLDER_TABLES = (0x80708D9C, 0x80708DC0, 0x80708D78)
BASE_XZ = 0x80625798
BALL_DASH = 10
# runner fields (docs/runners.md, FUN_80179df4 / FUN_8017cd2c / FUN_8017a430): top-speed cap = +0xE0 * +0x114
# (m/frame), the most mashing adds +0x104 over it, turning round accelerates at +0xDC * +0x11C; +0x142 frames back to
# his safe line; +0xC4 velocity (m/frame, + = to the next base), +0x9C leg fraction past his safe line, +0xA8 leg
# fraction, +0xAC leg length (m)
R_TOP, R_TOP_K, R_MASH, R_TURN, R_TURN_K, R_BACK = 0xE0, 0x114, 0x104, 0xDC, 0x11C, 0x142
R_VEL, R_PAST, R_FRAC, R_LEG = 0xC4, 0x9C, 0xA8, 0xAC
TAG_REACH, ON_BASE = -0x7A58, -0x7A9C              # r2: 1.8 (a tag: runner to ball), 0.8 (the holder / runner on base)
NO_TURN = -0x703C                                  # r2: 0.2, FUN_8017ed54: a CPU runner this near his base never turns
WINDUP = 0x8011A66C                                # FUN_8011A66C(fielder): his throw windup, frames (a byte)
GAME, SETTINGS = -0x163C, -0x1D58                  # r13: game (FUN_801319bc's), settings (S+0x24+team: CPU runners)
BALL_ZONE = 0x2A6B                                 # field byte: the ball's zone (FUN_8017ed54: <= 3 for the no-turn line)
R_ESC_TO, R_SAFE = 0x140, 0x94                     # runner: frames to his to-base; the safe fraction (0.03)
BALL_TO_BASE = 0x29BC                              # field: the ball's distance to base b (floats)
CHASE = 9                                          # the carry base for the stock chase-and-tag (FUN_80113370)
CHASE_SLACK = 6.0                                  # unused since 2026-09-28 (Nick: no slack); its scratch slot (+8)
FORWARD_MIN = 0.375                                # holds FORWARD_MIN: throw to the next base from 3/8 of the leg on
ONE = -0x7094                                      # r2: 1.0
SCRATCH_SIZE = 44                                  # after the body: +0 R', +4 k, +8 CHASE_SLACK, +12 COVER_ETA,
                                                   # +16 STATE, +32 R4, +36 DL
COVER_ETA = 12                                     # the cover's +0x1DC, kept over FUN_800E0F98's call (going forward)
COVER, ETA = 0x2EE, 0x1DC                          # ai: the cover fielder id of base b (s16 [b]); fielder: ETA, frames
R4 = 32                                            # the hook's r4 (the runner index PLAN_ONE reads) over
                                                   # _possession, whose rand() calls clobber it
DL = 36                                            # the CPU flag and W over the deadline's calls (2 words)
STATE = 16                                         # +0 last play frame, +4 last holder, +8 throws, +12 roll (1 early)
PRE, LOGFN = 44, 56                                # the rundown log only (cpu_rundown_log.LOG_ENTRIES, test builds):
LOG_SCRATCH = 16                                   # FUN_800E0F98's raw m / throw / carry; the log stub's address
RAND_FN, RNG, PLAY = 0x80165C14, -0x1578, -0x1684  # rand(n); r13: the match RNG; the play object (s16 frame at +0)
EARLY_PCT, MAX_RANDOM, NEW_RUNDOWN = 70, 10, 120   # % early; throws that roll; frames without a run = a new rundown
FIRST_PCT = 90                                     # % early for the first throw (throw 0; Nick, 2026-09-28)
EARLY_LEAD = 20                                    # frames: an early throw goes this long before the committed moment
TAG_BUFFER = 10                                    # frames the ball must beat his best time by (catch + tag; INFERRED)
AT4 = {}
AT5 = {}                                           # level 5's own values of the above (cpu_settings; level5.pair)
THROW_LAG = 18                                     # frames the real throw takes beyond the plan's W + flight, counted in
                                                   # the deadline (Nick's 21:57 / 22:39 dumps, 4 throws back to 1st:
                                                   # planned W 6 + flight 39 = 45; real: released 16 frames after the
                                                   # committed plan, caught 47 later = 63; the runner safe by 7 / 8)
FLIGHT = 0x800CA018                                # FUN_800CA018(x, z): the planner's ball flight to x, z (frames)
DASH_OFF, DASH_ALT = -0x644, -0x94                 # r13 words: dash disabled when != 0; != 0 -> the 1.15 factor
HALF = -0x757C                                     # r2: 0.5 (FUN_8011B600 reads it)
K_MAIN, K_ALT, ZERO, MAGIC = -0x7430, -0x742C, -0x7600, -0x7AB0   # r2: 1.3, 1.15, 0.0, double 0x4330000080000000


def _lfd(a, ft, d, ra): a.word(d_form(50, ft, ra, d))
def _stfd(a, fs, d, ra): a.word(d_form(54, fs, ra, d))
def _xoris(a, ra, rs, imm): a.word(d_form(27, rs, ra, imm))
def _fctiwz(a, t, b): a.word((63 << 26) | (t << 21) | (b << 11) | (15 << 1))


def _to_float(a, ft, r):
    """ft = (float) r (s32); uses r1+0x10 (FUN_800E05E8's own int/float temp), r0, f2 = the magic double."""
    _xoris(a, r, r, 0x8000)
    a.stw(r, 0x14, 1).lis(0, 0x4330).stw(0, 0x10, 1)
    _lfd(a, ft, 0x10, 1)
    _lfd(a, 2, MAGIC, 2)
    a.fsubs(ft, ft, 2)


def _speeds(a):
    """f4 = the runner's top-speed cap, f5 = v = the cap + the most mashing adds (r30 = the runner)."""
    a.lfs(4, R_TOP, 30).lfs(5, R_TOP_K, 30).fmuls(4, 4, 5)
    a.lfs(5, R_MASH, 30).fadds(5, 4, 5)


def _holder(a, none, got):
    """r3 = the ball holder (field+0x2A4C looked up like FUN_800E0F98), at label `got`; `none` if there is none.
    Uses r3-r5; r31 = the field."""
    a.lha(4, 0x2A4C, 31)
    _fielder(a, none, got)


def _fielder(a, none, got):
    """r3 = fielder id r4 (s16; < 0 none) looked up like FUN_800E0F98, at label `got`; `none` if there is none.
    Uses r3-r5."""
    a.cmpwi(4, 0).blt(none)
    a.clrlwi(5, 4, 24).slwi(5, 5, 2)
    a.lis(3, ha(HOLDER_TABLES[0])).addi(3, 3, lo(HOLDER_TABLES[0])).lwzx(3, 3, 5).cmpwi(3, 0).bne(got)
    a.lis(3, ha(HOLDER_TABLES[1])).addi(3, 3, lo(HOLDER_TABLES[1])).lwzx(3, 3, 5).cmpwi(3, 0).bne(got)
    a.slwi(5, 4, 2)
    a.lis(3, ha(HOLDER_TABLES[2])).addi(3, 3, lo(HOLDER_TABLES[2])).lwzx(3, 3, 5).cmpwi(3, 0).beq(none)
    a.label(got)


def _scratch(a, r, scratch):
    a.lis(r, ha(scratch)).addi(r, r, lo(scratch))


def _chase(a, scratch):
    """The chase check (docstring 2): falls through to "no_chase", or sets throw -1 / carry 9 / r28 and goes to commit.
    r28 = m, r30 = the runner, r31 = the field; scratch: +0 R', +4 k, +8 CHASE_SLACK."""
    _scratch(a, 9, scratch)
    a.lfs(1, ONE, 2).stfs(1, 4, 9)                                       # k = 1
    a.lwz(0, DASH_OFF, 13).cmpwi(0, 0).bne("ch_k")
    _holder(a, "no_chase", "ch_h1")
    a.lwz(12, 0, 3).lwz(12, 0x3C, 12).mtctr(12).bctrl()                  # his fielding ability
    a.clrlwi(3, 3, 24).cmplwi(3, BALL_DASH).bne("ch_k")
    a.lfs(1, K_MAIN, 2).lwz(0, DASH_ALT, 13).cmpwi(0, 0).beq("ch_k1")
    a.lfs(1, K_ALT, 2)
    a.label("ch_k1")
    _scratch(a, 9, scratch)
    a.stfs(1, 4, 9)                                                      # k = the dash factor
    a.label("ch_k")
    a.lfs(13, R_LEG, 30).lfs(0, ZERO, 2).fcmpo(13, 0).ble("no_chase")    # no leg: no chase
    a.lbz(4, 0x17D, 30).cmplwi(4, 3).ble("ch_f").li(4, 0)
    a.label("ch_f")
    a.lbz(5, 0x17E, 30).clrlwi(5, 5, 30)                                 # r4 = from, r5 = to
    # ANY HOLDER (Nick, 2026-09-28: "In a rundown if the fielder can beat the batter to the base or the batter is
    # stopped then run them down"; "anyone should follow those rules, it just matters the most for ball dash"): a
    # runner stopped between bases (+0x183 == 2): chase now. Else E = the base he is heading for (+0x17E advancing,
    # +0x17D heading back), R its frames (+0x140 / +0x142), no slack: chase when the holder (dashing: / k) gets to E's
    # tag point first
    a.lbz(0, 0x183, 30).cmplwi(0, 2).bne("ch_go")                       # stopped (+0x183 2) IN a rundown (the
    a.rlwinm(6, 29, 30, 2, 31).add(6, 6, 27).lbz(6, 0x2D4, 6).cmpwi(6, 0).bne("ch_now")   # zone byte ai+0x2D4[r]): chase now
    a.label("ch_go")
    a.lbz(0, 0x183, 30)
    a.cmplwi(0, 3).beq("ch_dback")
    a.mr(6, 4).mr(4, 5).mr(5, 6).lha(7, R_ESC_TO, 30).b("ch_e")          # advancing: E = to
    a.label("ch_dback")
    a.lha(7, R_BACK, 30).b("ch_e")                                        # heading back: E = from
    a.label("ch_now")                                                    # stopped: run him down now
    a.li(28, -1).li(0, -1).stw(0, 0xC, 1).li(0, CHASE).stw(0, 0x8, 1).b("commit")
    a.label("ch_e")                                                      # r4 = E, r5 = O, r7 = R
    _to_float(a, 6, 7)
    # R' = R: the game's own estimate (Nick, 2026-09-28: "the nokis can run people down from experience"; the
    # worst-case masher, R * cap / (cap + mash), about 13% less, left a Ball Dash holder almost never chasing)
    _scratch(a, 9, scratch)
    a.stfs(6, 0, 9)
    a.slwi(4, 4, 3).lis(3, ha(BASE_XZ)).addi(3, 3, lo(BASE_XZ)).add(4, 3, 4)
    a.slwi(5, 5, 3).add(5, 3, 5)
    a.lfs(7, 0, 4).lfs(8, 4, 4).lfs(9, 0, 5).lfs(10, 4, 5)               # E, O
    a.lfs(11, R_SAFE, 30).lfs(12, TAG_REACH, 2).lfs(13, R_LEG, 30).fdivs(12, 12, 13).fadds(11, 11, 12)
    a.fsubs(9, 9, 7).fmadds(1, 9, 11, 7)                                 # P = E + (O - E) * (0.03 + 1.8 / leg)
    a.fsubs(10, 10, 8).fmadds(2, 10, 11, 8)
    _holder(a, "no_chase", "ch_h2")
    a.bl(RUN_FRAMES)                                                     # his frames to P, undashed
    _to_float(a, 1, 3)
    _scratch(a, 9, scratch)
    a.lfs(3, 4, 9).fdivs(1, 1, 3)                                        # t = frames / k
    a.lfs(0, 0, 9).fsubs(1, 1, 0)                                        # t - R'
    a.fmr(3, 1).lfs(0, ZERO, 2).fcmpo(3, 0).bge("no_chase")               # t - R' >= 0 (NaN too): no chase
    _fctiwz(a, 1, 1)
    _stfd(a, 1, 0x10, 1)
    a.lwz(28, 0x14, 1)
    a.li(0, -1).stw(0, 0xC, 1).li(0, CHASE).stw(0, 0x8, 1).b("commit")
    a.label("no_chase")


def _possession(a, scratch):
    """Docstring 4: new play / rundown -> reset; a new holder -> count a throw and roll. Uses r0, r3-r9, cr0."""
    st = scratch + STATE
    a.lwz(3, PLAY, 13).cmpwi(3, 0).beq("st_done")
    a.lha(3, 0, 3)                                                       # the play frame
    _scratch(a, 9, st)
    a.lwz(4, 0, 9).stw(3, 0, 9)
    a.cmpw(3, 4).blt("st_new")                                           # went back: a new play
    a.addi(4, 4, NEW_RUNDOWN).cmpw(3, 4).ble("st_same")                  # a long gap: a new rundown
    a.label("st_new")
    a.li(0, -1).stw(0, 4, 9).stw(0, 8, 9)                                # the first holder will be throw 0
    a.label("st_same")
    a.lha(5, 0x2A4C, 31).cmpwi(5, 0).blt("st_done")                      # in flight: nothing
    a.lwz(6, 4, 9).cmpw(5, 6).beq("st_done")                             # same holder: keep his roll
    a.stw(5, 4, 9).lwz(6, 8, 9).addi(6, 6, 1).stw(6, 8, 9)               # a new holder: a throw
    a.lwz(3, RNG, 13).li(4, 100).bl(RAND_FN)
    _scratch(a, 9, st)
    me = sys.modules[__name__]
    (e4, e5, e6), (f4, f5, f6) = level5.pair(me, "EARLY_PCT"), level5.pair(me, "FIRST_PCT")
    if (e4, f4) == (e5, f5) == (e6, f6):
        a.lwz(6, 8, 9).li(4, EARLY_PCT).cmpwi(6, 0).bne("st_pct").li(4, FIRST_PCT)   # the first throw: FIRST_PCT
    else:                                                                # level 5's own rates (r4 only; cr0 set after)
        a.lwz(6, 8, 9)
        level5.pick(a, 4, e4, e5, e6).cmpwi(6, 0).bne("st_pct")
        level5.pick(a, 4, f4, f5, f6)
    a.label("st_pct")
    a.li(0, 1).cmpw(3, 4).blt("st_roll").li(0, 0)
    a.label("st_roll")
    _scratch(a, 9, st)
    a.stw(0, 12, 9)
    a.label("st_done")


def _log_on():
    import cpu_rundown_log
    return cpu_rundown_log.LOG_ENTRIES > 0


def body(at, scratch, log=None):
    """log: the rundown log's two changes (None: cpu_rundown_log.LOG_ENTRIES != 0): the raw plan kept after
    FUN_800E0F98, and the exit through the log stub (the pointer word at scratch + LOGFN) instead of `b EPILOGUE`."""
    log = _log_on() if log is None else log
    a = Asm(at)
    _scratch(a, 9, scratch + R4)
    a.stw(4, 0, 9)                                                       # keep r4 (the runner index) for PLAN_ONE
    _possession(a, scratch)
    a.lbz(0, 0x183, 30)
    a.cmplwi(0, 1).beq("plan").cmplwi(0, 3).beq("plan")
    a.cmplwi(0, 2).bne("out")
    a.lha(0, 0x138, 30).cmpwi(0, 0).bge("out")
    a.label("plan")
    # going forward / stopped: the cover of the next base (ai+0x2EE[+0x17E]) counts as on it for the plan (docstring 1)
    a.li(28, 0).lbz(0, 0x183, 30).cmplwi(0, 3).beq("call")
    a.lbz(4, 0x17E, 30).slwi(4, 4, 1).add(4, 4, 27).lha(4, COVER, 4)
    _fielder(a, "call", "cv_got")
    a.mr(28, 3)                                                          # the cover
    _scratch(a, 9, scratch + COVER_ETA)
    a.lha(0, ETA, 28).stw(0, 0, 9).li(0, -1).sth(0, ETA, 28)             # his ETA, -1 = on the base for the call
    a.label("call")
    a.li(5, 1).lbz(0, 0x183, 30).cmplwi(0, 3).bne("dir")                # going forward / stopped: the next base
    a.li(5, 0)                                                           # heading back: the base behind (dir 0)
    a.label("dir")
    _scratch(a, 9, scratch + R4)
    a.lwz(4, 0, 9)                                                       # the runner index, from the hook
    a.mr(3, 27).addi(6, 1, 0xC).addi(7, 1, 0x8).bl(PLAN_ONE)
    a.cmpwi(28, 0).beq("m")
    _scratch(a, 9, scratch + COVER_ETA)
    a.lwz(0, 0, 9).sth(0, ETA, 28)                                       # the cover's ETA back
    a.label("m")
    if log:                                                              # the raw plan, for the log
        _scratch(a, 9, scratch + PRE)
        a.stw(3, 0, 9).lwz(0, 0xC, 1).stw(0, 4, 9).lwz(0, 0x8, 1).stw(0, 8, 9)
    a.mr(28, 3)                                                          # m
    _chase(a, scratch)                                                   # a chase that wins comes first
    # FORWARD_MIN (Nick, 2026-09-28: "don't throw to the next base unless they are at least halfway there", then "at
    # least 3/8 of the way there"): a runner advancing (+0x183 == 1) still under FORWARD_MIN (+0xA8 < 0.375) of the
    # leg: hold (base + 10) instead of the throw
    a.lbz(0, 0x183, 30).cmplwi(0, 1).bne("fw_ok")
    _scratch(a, 9, scratch)
    a.lfs(1, R_FRAC, 30).lfs(0, 8, 9).fcmpo(1, 0).bge("fw_ok")          # scratch +8: FORWARD_MIN
    a.lwz(5, 0xC, 1).cmplwi(5, 3).bgt("fw_ok")
    a.addi(5, 5, 10).stw(5, 0xC, 1).b("commit")
    a.label("fw_ok")
    a.lbz(0, 0x183, 30).cmplwi(0, 3).bne("commit")                      # forward / stopped: the plan, thrown at
    # once (no hold, no Ball Dash). Heading back: hold for the cover (base + 10, the plan's own hold) until EARLY_LEAD
    # frames before he can't turn his way out at the release or the TAG_BUFFER deadline (an "early" roll), or until
    # that moment itself or the slip test (the hold roll) (docstring 1, 4)
    a.lwz(5, 0xC, 1).cmplwi(5, 3).bgt("hb_ok")                          # a throw to a base (0..3)
    a.li(8, 0)                                                           # W = 0 without a holder
    _holder(a, "hb_w", "hb_got")
    a.bl(WINDUP).clrlwi(8, 3, 24)                                        # W: the holder's windup
    a.label("hb_w")
    a.li(7, 0).lwz(3, GAME, 13).cmpwi(3, 0).beq("hb_who")                # r7 = CPU runner (the batting team's
    a.lbz(4, 0x2C, 3).lwz(3, SETTINGS, 13).cmpwi(3, 0).beq("hb_who")    # S+0x24 flag, as FUN_8017ed54)
    a.add(3, 3, 4).lbz(7, 0x24, 3)
    a.label("hb_who")
    # THE DEADLINE, EVERY THROW BACK (Nick, 2026-09-28: the 70% "needs to be so that if I kept going I would get out,
    # it throws 20 frames before I would be safe"; and the 30% never late): the last frame the ball still reaches b
    # TAG_BUFFER frames before his best time there. An early roll (docstring 4) throws EARLY_LEAD frames before it
    # (nothing about when he could turn back); the hold roll waits for the committed moment (hb_rule) but never past it
    _scratch(a, 9, scratch + DL)                                         # keep the CPU flag and W over the calls
    a.stw(7, 0, 9).stw(8, 4, 9)
    _holder(a, "hb_rule", "dl_got")                                      # no holder: the committed rule
    a.lwz(4, 0xC, 1).slwi(4, 4, 3).lis(3, ha(BASE_XZ)).addi(3, 3, lo(BASE_XZ)).add(3, 3, 4)
    a.lfs(1, 0, 3).lfs(2, 4, 3).bl(FLIGHT)                               # r3 = the planner's flight to base b
    _scratch(a, 9, scratch + DL)
    a.lwz(7, 0, 9).lwz(8, 4, 9)
    me = sys.modules[__name__]
    (t4, t5, t6), (m4, m5, m6), (l4, l5, l6) = (level5.pair(me, n) for n in ("TAG_BUFFER", "MAX_RANDOM", "EARLY_LEAD"))
    a.add(3, 3, 8)
    if t4 == t5 == t6:
        a.addi(3, 3, TAG_BUFFER + THROW_LAG + 1)                         # W + flight + THROW_LAG + TAG_BUFFER + 1
    else:                                                                # level 5's own (r10 is set just below)
        level5.pick(a, 10, t4 + THROW_LAG + 1, t5 + THROW_LAG + 1, t6 + THROW_LAG + 1).add(3, 3, 10)
    _scratch(a, 9, scratch + STATE)
    if m4 == m5 == m6:
        a.li(10, 0).lwz(0, 8, 9).cmpwi(0, MAX_RANDOM).bge("dl_x")       # from the 10th throw: the hold roll
    else:
        a.lwz(0, 8, 9)
        level5.pick(a, 10, m4, m5, m6).cmpw(0, 10).li(10, 0).bge("dl_x")    # (li keeps cr0)
    a.lwz(10, 12, 9).cmpwi(10, 0).beq("dl_x")                           # r10 = the roll (1 early)
    if l4 == l5 == l6:
        a.addi(3, 3, EARLY_LEAD)                                         # early: EARLY_LEAD frames before it
    else:                                                                # (r4 is dead: the flight call clobbered it)
        level5.pick(a, 4, l4, l5, l6).add(3, 3, 4)
    a.label("dl_x")
    _to_float(a, 1, 3)
    a.lfs(6, R_PAST, 30).lfs(3, R_LEG, 30).fmuls(6, 6, 3)                # d: metres past his safe line
    _speeds(a)                                                           # f4 = cap, f5 = cap + mash
    a.cmpwi(7, 0).beq("dl_v").fmr(5, 4)                                  # a CPU runner: his cap
    a.label("dl_v")
    a.fdivs(6, 6, 5)                                                     # his best frames to his safe line
    a.fcmpo(1, 6).blt("dl_no").beq("dl_no")                              # at the line (NaN too): throw now
    a.b("hb_ok")
    a.label("dl_no")
    a.cmpwi(10, 0).bne("hb_hold")                                        # early: not yet
    a.label("hb_rule")                                                   # the hold roll: at the committed moment
    a.cmpwi(7, 0).beq("hb_human")
    a.cmpwi(28, 0).bge("hb_ok").b("hb_line")                             # CPU: m >= 0, slipping: throw
    a.label("hb_human")
    a.mr(6, 28)
    _to_float(a, 1, 6)                                                   # f1 = m
    a.lha(6, R_BACK, 30)
    _to_float(a, 6, 6)                                                   # f6 = R
    _speeds(a)                                                           # f4 = cap, f5 = cap + mash
    a.fadds(1, 1, 6).fmuls(7, 6, 4).fdivs(7, 7, 5).fsubs(1, 1, 7)       # m' = m + R - R * cap / (cap + mash)
    a.lfs(0, ZERO, 2).fcmpo(1, 0).bge("hb_ok")                           # slipping against a masher (NaN: throw)
    a.label("hb_line")
    _to_float(a, 4, 8)                                                   # f4 = T
    a.lfs(3, R_VEL, 30).fneg(3, 3)                                       # f3 = u, his speed back
    a.lfs(9, R_FRAC, 30).lfs(7, R_PAST, 30)                              # f9 = +0xA8, f7 = +0x9C (past its safe line)
    a.lfs(5, R_LEG, 30).fmuls(8, 3, 4)                                   # f5 = leg, f8 = u * T
    a.cmpwi(7, 0).beq("hb_phys")                                         # CPU: FUN_8017ed54's no-turn line
    a.lbz(0, BALL_ZONE, 31).cmplwi(0, 3).bgt("hb_phys")
    a.fdivs(10, 8, 5).fsubs(9, 9, 10)                                    # his fraction at the release
    a.lfs(10, NO_TURN, 2).fcmpo(9, 10).blt("hb_ok")
    a.label("hb_phys")
    a.lfs(0, ZERO, 2).fcmpo(3, 0).ble("hb_hold")                         # not coming back yet
    a.fmuls(7, 7, 5).fsubs(7, 7, 8)                                      # d_r: metres past his safe line
    a.lfs(9, R_TURN, 30).lfs(10, R_TURN_K, 30).fmuls(9, 9, 10).fadds(9, 9, 9)
    a.fmuls(10, 3, 3).fdivs(10, 10, 9).fsubs(7, 7, 10)                   # - u^2 / 2b: where he'd stop
    a.lfs(10, TAG_REACH, 2).lfs(11, ON_BASE, 2).fsubs(10, 10, 11)
    a.fcmpo(7, 10).ble("hb_ok")                                          # inside the tag reach: committed
    a.label("hb_hold")
    a.lwz(5, 0xC, 1).addi(5, 5, 10).stw(5, 0xC, 1)
    a.label("hb_ok")                                                     # Ball Dash: heading back only (above)
    # Ball Dash: holder, ability, dash on
    a.lwz(0, DASH_OFF, 13).cmpwi(0, 0).bne("commit")
    _holder(a, "commit", "got")
    a.mr(31, 3)                                                          # the holder (the field isn't needed now)
    a.lwz(12, 0, 31).lwz(12, 0x3C, 12).mtctr(12).bctrl()                 # his fielding ability
    a.clrlwi(3, 3, 24).cmplwi(3, BALL_DASH).bne("commit")
    a.lbz(4, 0x17D, 30).cmplwi(4, 3).ble("base").li(4, 0)
    a.label("base")
    a.slwi(4, 4, 3).lis(3, ha(BASE_XZ)).addi(3, 3, lo(BASE_XZ)).add(3, 3, 4)
    a.lfs(1, 0, 3).lfs(2, 4, 3)
    a.mr(3, 31).bl(RUN_FRAMES)                                           # r3 = his frames there, unboosted
    _to_float(a, 1, 3)
    a.lfs(3, K_MAIN, 2).lwz(0, DASH_ALT, 13).cmpwi(0, 0).beq("k")
    a.lfs(3, K_ALT, 2)
    a.label("k")
    a.fdivs(1, 1, 3)                                                     # dashing
    a.lha(3, R_BACK, 30)
    _to_float(a, 0, 3)                                                   # the runner's frames back to that base
    _speeds(a)
    a.fmuls(0, 0, 4).fdivs(0, 0, 5)                                      # mashing: R' = R * cap / v
    a.fsubs(1, 1, 0).lfs(0, ZERO, 2).fcmpo(1, 0).bge("commit")
    _fctiwz(a, 1, 1)
    _stfd(a, 1, 0x10, 1)
    a.lwz(28, 0x14, 1)
    a.li(0, -1).stw(0, 0xC, 1)                                           # no throw
    a.lbz(0, 0x17D, 30).cmplwi(0, 3).ble("carry").li(0, 0)
    a.label("carry")
    a.stw(0, 0x8, 1)                                                     # carry it to the base behind
    a.label("commit")
    a.add(4, 27, 29).stw(28, MARGIN, 4)
    a.lwz(0, 0xC, 1).stw(0, THROW, 4).lwz(0, 0x8, 1).stw(0, CARRY, 4)
    a.label("out")
    if log:                                                              # the log stub, which ends `b EPILOGUE`
        a.lis(12, ha(scratch + LOGFN)).lwz(12, lo(scratch + LOGFN), 12).mtctr(12).word(0x4E800420)   # bctr
    else:
        a.b(EPILOGUE)
    return a


def hook_stub(at, hook, orig, level6):
    a = Asm(at)
    level5.gate(a, 12, "stock", "cpu-rundown")
    a.b(level6)
    a.label("stock")
    a.word(orig).b(hook + 4)
    return a


HOOKS = ((HOOK_IN, ORIG_IN, "in the rundown zone"), (HOOK_OUT, ORIG_OUT, "out of the zone"))
LAYOUT = {}                                                             # "scratch": the body's scratch (apply)


def apply(dol, code, data=None):
    """Hook FUN_800E05E8's rundown plans in `dol` (level 6 only); the stubs go in `code` (a charbuild Space).
    Needs level5.alloc(data) first. With the rundown log on (cpu_rundown_log.LOG_ENTRIES), its ring goes in `data`
    and its stubs come later (cpu_rundown_log.apply_code, charbuild step 19c). Returns log lines."""
    assert level5.FLAG is not None, "level5.alloc(data) first"
    import cpu_rundown_log
    log_on = _log_on()
    cpu_rundown_log.LOGP = cpu_rundown_log.PTR = None                   # (set below for this build when on)
    assert not log_on or data is not None, "the rundown log needs the data section"
    for at, orig, _ in HOOKS:
        got = dol.u32(at)
        assert got == orig, f"0x{at:08X}: 0x{got:08X}, expected 0x{orig:08X}"
    where = code.here + (-code.here % 4)
    size = len(body(where, where).assemble())
    blob = body(where, where + size).assemble()
    assert len(blob) == size
    blob += struct.pack(">fffi", 0.0, 1.0, FORWARD_MIN, 0) + struct.pack(">iiiiiii", 0x7FFFFFFF, -1, -1, 0, 0, 0, 0)
    assert len(blob) == size + SCRATCH_SIZE
    if log_on:                                                           # PRE (m, throw, carry), LOGFN: the epilogue
        blob += struct.pack(">iiiI", 0, -1, -1, EPILOGUE)                # until apply_code sets it
        assert SCRATCH_SIZE == PRE and len(blob) == size + SCRATCH_SIZE + LOG_SCRATCH
    assert code.put(blob, align=4) == where
    LAYOUT["scratch"] = where + size                                     # (replay_state: its STATE persists)
    level6 = where
    if log_on:
        cpu_rundown_log.alloc(data, where + size)
        cpu_rundown_log.PTR = where + size + LOGFN
    log = [f"cpu rundown (levels 5 / 6): chase when it wins, next base going forward, base behind heading back + Ball Dash carry (body 0x{level6:08X}, {len(blob)} bytes)"]
    for at, orig, why in HOOKS:
        where = code.here + (-code.here % 4)
        blob = hook_stub(where, at, orig, level6).assemble()
        assert code.put(blob, align=4) == where
        dol.w32(at, branch(at, where))
        log.append(f"cpu rundown (levels 5 / 6): {why} (0x{at:08X} -> 0x{where:08X}, {len(blob)} bytes)")
    return log
