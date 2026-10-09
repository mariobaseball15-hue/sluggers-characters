"""Level 6 CPU batter: judge ball / strike on the real zone, from the ball's flight, at the swing frame (Nick,
2026-09-27: "It also still occasionally takes strikes right on the outside of the zone").

ROOT CAUSE [C]. Stock takes on one number, pitcher +0xD4, judged once (FUN_800C5460 via vt+0x1C FUN_800C5424, called
from FUN_800C4FF4 at 0x800C5160..0x800C5190 when pitcher +0x110 == AI +0x3F: 7 frames before the batter at level 4):
- +0xD4 is not stale: FUN_8015DE4C runs every flight frame (prev position to +0x44/+0x48/+0x4C, the flight through
  0x80649CBC[+0x141], then FUN_801627E0), and FUN_801627E0 re-forecasts it each frame with FUN_80162FE8(pitcher,
  &+0xD4, 1, batter +0x40): the flight model run on (the current position +0x38, velocity +0x50, the per-frame
  sideways step +0x94 held constant) to the BATTER's z. +0x94 is rebuilt every frame by FUN_80161FB0: the break
  (FUN_800C6938) plus the steer (FUN_80162358: a human's, or cpu_pitching's level 6 charged curve, +0xE8). So
  tracking already follows the ball each frame; the open-question guess "locks tracking at release" was wrong (only the
  track roll +0x49 is at release).
- But the umpire (FUN_801627E0, 0x8016287C..0x801629D4) calls a strike when the ball's x, interpolated where it
  crosses z = 1.12 (0x80627A98) OR z = 0.32 (0x80627A9C), is inside [-0.55, +0.55] (0x80627A90 / 0x80627A94,
  inclusive; no ball radius, no height). The batter tests x at its own z (+0x40) against 0x80624818 (outside if
  x < -0.55 or x >= 0.55). A pitch still moving sideways differs between the planes: one breaking in -> out is inside
  at z = 1.12 (a strike) and outside at the batter (taken). That is most of the taken strikes.
- FUN_80162FE8's last step interpolates with the fraction mirrored: x_prev + (x - x_prev) * (z - P) / (z - z_prev)
  (0x801631B8..0x801631DC; the right weight is (z_prev - P) / (z_prev - z)), so +0xD4 is off by up to one frame's
  sideways motion (~0.02-0.05 m on a breaking pitch).
- The judgement is 7 frames out, 2 before the swing starts (FUN_800C51E4: the swing on flight frame +0x45 + 1, about 5
  frames before the batter at level 5/6's zero timing error). A late-breaking curve (the break starts at 13 / 14 m of
  travel, 0x80627AB4) or a steered one (the steer window ends at 15 m) is still bending then.
Model on 300 synthetic edge pitches (scripts/test_cpu_track.py): stock misjudges 23, 22 of them taken strikes; this
fix, 0.

FIX (level 6 only: level5.FLAG == 2, AI +0x39 == 3 (the hardest tier), AI vtable 0x806404D0 (Bb::CBComBat, not Toy /
Hanabi / training), pitch +0x141 == 0 (not a star pitch: their own paths and decoys stay stock)):
TAKE 0x800C5160 (`lbz r3,0x3F(r29)`; r29 = AI, r30 = flight frame, r31 = pitcher). The stock judgement at +0x3F is
     skipped. On the swing frame (frame == AI +0x45 + 1, +0x45 != 0), the latest frame a swing can still start:
     AI +0x37 set -> take (as FUN_800C5424); else FORECAST the ball to z = 1.12 and z = 0.32 and take (AI +0x32 = 1)
     unless either x is in [0x80627A90, 0x80627A94], the umpire's own test. Then on to 0x800C5194 (the swing check), so
     the swing frame is unchanged. Level 5 / 6's take table is [0, 100, 0, 0] (cpu_perfect: in the zone always swing,
     outside always take), so this is that rule on the real zone, with no rand call.
TRACK 0x800C4B9C (`lfs f3,0xD4(r30)` in FUN_800C4AB4; r28 = AI, r29 = batter, r30 = pitcher): the bat's x target is
     FORECAST to the batter's z (+0x40) instead of +0xD4: the same model, the interpolation corrected. r0 (the decoy
     byte loaded at 0x800C4B98) is reloaded on the way back.
FORECAST (leaf; r3 = pitcher, f1 = plane z -> f1 = x there, r3 = 1; r3 = 0 if it never crosses in 300 frames): the
     flight as FUN_80160938 / FUN_80162FE8 run it, one frame at a time from the current state: while z <= +0xAC,
     vz -= (+0xB4 + extra) * vz if that stays < -0.05 (r2-0x7120), then vx -= +0xB4 * vx; extra = +0x188 for a human
     pitcher (+0x34 == 0) unless +0x140 == 1; v *= r2-0x7338[Hz byte r13-0x1658]; x += +0x94 + vx; z += vz; the
     crossing interpolated the right way. A plane already passed: the line through the previous and current position.
All of it is what the ball visibly does now (its position, its velocity, its current sideways drift); nothing about
where the pitcher aimed or will steer.

UNMEASURED / [INFERRED]:
- Order in the frame of the batter AI vs FUN_8015DE4C: either way the state read is at most one frame old [I].
- A steer still changing after the swing frame (a charged curve short of its target, still bending until 15 m of
  travel) can't be foreseen (in a wider exploratory model, ~0.3% of steered edge pitches, out -> in curves taken).
- The batter's z (+0x40) is per character (0x806291E0/E4 bounds); the tests use 0.72 (the AI box-depth clamp and
  Nick's RAM dumps), 0.4 and 0.9. The flight model in the test (release z 18.3, drag +0xB4 0.002) is [I].
- The umpire judges the unbowed path (+0x38); the drawn ball adds the cosmetic bow +0xCC, near 0 by the plate [I].
- Not changed: the level 6 CPU pitcher (cpu_pitching.py) aims its plate x at s * (0.55 + e) at z +0x64; by the same
  two-plane rule its in -> out curves ending a little outside are strikes at z = 1.12.
LEVEL 5 MIND GAME (Nick, 2026-09-28: "make the hitting adaptive ... not just binary right wrong ... if it thinks charge
and it's changeup then it is likely to swing early, same with movement, ball strike. It should still hit the sweet
spot a lot"). Level 5 only (level5.FLAG == 1; level 6 reads every pitch). The batter predicts the pitch, plans for
the prediction, and adjusts to the real pitch DREACT frames after the release (rand DLO..DHI), sometimes too late:
- MEMORY (MIND: one block per batting team, zeroed at match start with the pitch model's state, via
  cpu_pitching.EXTRA_RESET): a ring of the last RING pitches it faced: where the ball crossed at its z (x, +0xD4
  mirrored for a lefty), the frames from the release to the plate T, and the count context (pitcher ahead / even /
  behind).
- PREDICT 0x800C44D4 (FUN_800C41D4's per-pitch set-up, after the stock guess; `lwz r31,0x2c(r1)`; r28 = AI): pick a
  remembered pitch, weighted M_DECAY^age, x KCTX when its count context differs from now; EPS% of the time any one at
  random (level 5's randomness). Empty memory: the middle, no timing plan, a strike. The pick is the plan: XHAT (the
  bat's x), THAT (the flight it times for), PSTRIKE (|x| <= EDGE: swing, else take). DREACT is drawn here.
- PRE-POSITION 0x800C4A7C (FUN_800C49EC's `bl 0x800C4DD8`, the bat mover; r3 = AI): before the release the bat's
  target (+0x14) is XHAT.
- TIME 0x800C53FC (FUN_800C51E4's exit, release frame 1; r31 = AI): the swing frame +0x45 = the stock base +0x4A
  (+0x110 + frame - 6) + (THAT - +0x110): timed for the predicted flight (a changeup it thinks is a charged pitch:
  early; a fast one it thinks is a changeup: late). REL = this frame, T0 = +0x110. A star pitch: no plan (stock).
- TRACK (above; level 5 tracks 79% of pitches, cpu_perfect's track roll, Nick 2026-09-29: ~72-79% sweet spots; an
  untracked pitch keeps the bat on XHAT, the guess): until DREACT frames after REL
  the bat target stays XHAT; on that frame it ADJUSTS: from then on the target is the ball's forecast (the bat moves at
  its stock max 0.03 / frame, so a far miss can't be fixed in time), and if the swing hasn't started the swing frame is
  re-timed on the real flight (+0x110 now). TACT = the flight measured then.
- TAKE (above): on the swing frame before the adjustment, swing if PSTRIKE, take if not; after it, the real zone.
- LEARN 0x800C4630 (FUN_800C4610, the end of a non-star pitch; r3 = AI, r6 = pitcher): remember x, T (TACT, else T0)
  and the context.
- HARD PITCHES (Nick: "harder pitches are harder for it to predict ... really high or a lot of curve or within a small
  number off the edge of the strike zone it will make a relevant mistake more often"), each its own mistake:
  - a lot of curve: on the adjustment frame, the ball's sideways step |+0x94| (the break and steer, per frame) past
    CURVE_T adds (|step| - CURVE_T) * CURVE_K frames to DREACT (once, capped at EXTRA_MAX): the bat is later to the
    break (off the sweet spot or the end of the bat);
  - really high: a changeup (+0x13C == 2, the pitch that floats) adds (arc - ARC0) * HIGH_K frames, arc = the
    pitcher's changeup arc (0x80628EB4 + id * 8: 10..40, 40 = the Magikoopas' floater): the timing is re-set later
    (early / late);
  - near the edge: at the swing frame (after the adjustment), when either umpire plane's forecast is within EDGE_BAND
    of the zone edge, P_EDGE% of the time the call is flipped (a chased ball or a taken strike).
  All UNMEASURED guesses to tune in play.
Tuned in a model (UNMEASURED: flights 27 / 33 / 47 frames, the bat at 0.03 / frame, the sweet window +-0.03): DREACT
0..6 gives ~86% sweet spots against a pitcher who mixes at random, ~91% against a predictable one.
Test: scripts/test_cpu_track.py.
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
import level5  # noqa: E402
from ppc import Asm, bc, branch, d_form, ha, lo, x_form  # noqa: E402

TAKE, TAKE_ORIG, TAKE_RET, SWING_CHECK = 0x800C5160, 0x887D003F, 0x800C5164, 0x800C5194   # lbz r3,0x3F(r29)
TRACK, TRACK_ORIG, TRACK_RET = 0x800C4B9C, 0xC07E00D4, 0x800C4BA0                         # lfs f3,0xD4(r30)
VTABLE = 0x806404D0                                # Bb::CBComBat
TIER, NO_SWING, SWING_AT, HOLD, DECOY = 0x39, 0x32, 0x45, 0x37, 0x38   # AI
STAR = 0x141                                       # pitcher u8: star pitch id
ZONE = 0x80627A90                                  # f32 lo, hi, plane z 1.12, plane z 0.32 (FUN_801627E0)
BATTER, BATTER_ALT = -0x1D78, -0x1D7C              # r13
HZ, DECAY, FLOOR, ZERO = -0x1658, -0x7338, -0x7120, -0x7150   # r13 byte; r2 f32[Hz], f32 -0.05, f32 0.0
MAX_FRAMES = 300
# ---- level 5 mind game (docstring LEVEL 5 MIND GAME)
RING, M_DECAY, KCTX, EPS, DLO, DHI, LEAD = 32, 0.9, 0.5, 10, 0, 6, 6
N, VALID, ADJ, PSTRIKE, CTX, REL_OK, EXT = 0, 4, 5, 6, 7, 8, 9  # block: u32 count, then u8 flags
XHAT, THAT, DREACT, REL, T0, TACT = 12, 16, 18, 20, 22, 24      # f32, then s16s
SCR = 32                                                         # 8 bytes: fctiwz scratch
RING_AT, ENTRY = 40, 8                                           # entries: f32 x, s16 T, u8 -, u8 context
EDGE_BAND, P_EDGE = 0.08, 35                       # hard pitches (docstring): near the edge -> P_EDGE% a flipped call
CURVE_T, CURVE_K, ARC0, HIGH_K, EXTRA_MAX = 0.004, 600.0, 15.0, 0.25, 10
CHANGEUP_ARC, CHAR_ID, KIND_ROW = 0x80628EB4, 0x2A, 0x13C
BLOCK = RING_AT + RING * ENTRY
MASK_BITS = 32 - (RING.bit_length() - 1)                         # clrlwi: & (RING - 1)
PREDICT, PREDICT_ORIG, PREDICT_RET = 0x800C44D4, 0x83E1002C, 0x800C44D8   # lwz r31,0x2c(r1)
PREPOS, MOVER = 0x800C4A7C, 0x800C4DD8                                    # bl 0x800C4DD8
TIME, TIME_ORIG, TIME_RET = 0x800C53FC, 0x80010014, 0x800C5400            # lwz r0,0x14(r1)
LEARN, LEARN_ORIG, LEARN_RET = 0x800C4630, 0xA8060112, 0x800C4634          # lha r0,0x112(r6)
PLAY, TICK = -0x1684, 4                            # r13: the play object; s16 frames since the release (< 0 before)
COUNT, STRIKES, BALLS, GAME, BAT_TEAM = -0x1D38, 7, 8, -0x163C, 0x2C
LEFTY = 0xB3                                       # batter u8
RAND, UNIFORM, RNG, ONE = 0x80165C14, 0x80165CFC, -0x1578, -0x7094   # rand(n), uniform(f1, f2); r2 f32 1.0
EDGE = 0.55
MIND = None                                        # the two blocks (apply)
KONST = None                                       # f32 M_DECAY, KCTX, EDGE, EDGE_BAND, CURVE_T, CURVE_K, ARC0, HIGH_K
FABS1 = (63 << 26) | (1 << 21) | (1 << 11) | (264 << 1)   # fabs f1,f1


def _fabs(a, t, b):
    return a.word((63 << 26) | (t << 21) | (b << 11) | (264 << 1))


def _fctiwz(a, t, b):
    return a.word((63 << 26) | (t << 21) | (b << 11) | (15 << 1))


def _stfd(a, fs, d, ra):
    return a.word((54 << 26) | (fs << 21) | (ra << 16) | (d & 0xFFFF))


def _lfsx(a, ft, ra, rb):
    return a.word(x_form(ft, ra, rb, 535))


def _bdnz(a, label):
    return a._emit(lambda pc: bc(pc, a.labels[label], 16, 0))


def forecast(a):
    """FORECAST (docstring): label "forecast"."""
    a.label("forecast")
    a.lfs(2, 0x38, 3).lfs(3, 0x40, 3)              # f2 = x, f3 = z
    a.fcmpo(3, 1).bge("sim")
    a.lfs(4, 0x44, 3).lfs(5, 0x4C, 3).b("cross")   # already past: the last frame's segment
    a.label("sim")
    a.lfs(6, 0x50, 3).lfs(7, 0x58, 3)              # f6 = vx, f7 = vz
    a.lfs(8, 0x94, 3).lfs(9, 0xB4, 3)              # f8 = sideways step, f9 = drag
    a.lfs(10, ZERO, 2)
    a.lwz(0, 0x34, 3).cmpwi(0, 0).bne("drag")
    a.lbz(0, 0x140, 3).cmplwi(0, 1).beq("drag")
    a.lfs(10, 0x188, 3)                            # a human pitcher's extra z drag
    a.label("drag")
    a.fadds(10, 9, 10)                             # f10 = z drag
    a.lfs(11, 0xAC, 3)                             # f11 = drag from this z
    a.lbz(0, HZ, 13).slwi(0, 0, 2).addi(4, 2, DECAY)
    _lfsx(a, 12, 4, 0)                             # f12 = decay
    a.lfs(13, FLOOR, 2)
    a.li(0, MAX_FRAMES).mtctr(0)
    a.label("frame")
    a.fcmpo(3, 11).bgt("free")
    a.fnmsubs(0, 10, 7, 7)                         # vz - drag * vz
    a.fcmpo(0, 13).bge("free")
    a.fmr(7, 0).fnmsubs(6, 9, 6, 6)                # vx -= drag * vx
    a.label("free")
    a.fmuls(6, 6, 12).fmuls(7, 7, 12)
    a.fmr(4, 2).fmr(5, 3)                          # f4, f5 = the previous x, z
    a.fadds(2, 2, 8).fadds(2, 2, 6).fadds(3, 3, 7)
    a.fcmpo(3, 1).blt("cross")
    _bdnz(a, "frame")
    a.li(3, 0).blr()
    a.label("cross")                               # x = px + (x - px) * (pz - P) / (pz - z)
    a.fsubs(0, 5, 3).lfs(9, ZERO, 2).fcmpo(0, 9).ble("never")
    a.fsubs(6, 5, 1).fdivs(6, 6, 0).fsubs(7, 2, 4)
    a.fmadds(1, 7, 6, 4)
    a.li(3, 1).blr()
    a.label("never")
    a.li(3, 0).blr()
    return a


def _gate(a, ai, pitcher, stock):
    level5.gate(a, 3, stock, "cpu-batter-track")   # levels 5 and 6
    a.lbz(0, TIER, ai).cmpwi(0, 3).bne(stock)
    a.lwz(3, 0, ai).load_addr(4, VTABLE).cmpw(3, 4).bne(stock)
    a.lbz(0, STAR, pitcher).cmpwi(0, 0).bne(stock)


def stubs(at):
    assert ha(ZONE) == ha(ZONE + 12)
    a = Asm(at)
    # TAKE
    a.label("take_stub")
    _gate(a, 29, 31, "take_stock")
    a.lbz(3, SWING_AT, 29).cmpwi(3, 0).beq("take_done")
    a.addi(3, 3, 1).cmpw(30, 3).bne("take_done")   # the swing frame only
    a.lbz(0, HOLD, 29).cmpwi(0, 0).bne("take")
    a.lis(12, ha(level5.FLAG)).lbz(12, lo(level5.FLAG), 12).cmpwi(12, 1).bne("take_real")   # level 5: the plan
    _block(a, 9, 10, "tk")
    a.lbz(0, VALID, 9).cmpwi(0, 0).beq("take_real")
    a.lbz(0, ADJ, 9).cmpwi(0, 0).bne("take_l5")                   # adjusted: the real zone (near-edge mistakes)
    a.lbz(0, PSTRIKE, 9).cmpwi(0, 0).bne("take_done").b("take")   # before it: the plan's swing / take
    a.label("take_l5")                                             # after it: the real zone, a near-edge call
    a.mr(10, 9).li(8, 0).li(9, 0)                                  # r10 = block, r8 = near the edge, r9 = a strike
    for plane in (8, 12):
        a.mr(3, 31).lis(4, ha(ZONE)).lfs(1, lo(ZONE + plane), 4).bl("forecast")
        a.cmpwi(3, 0).bne(f"l5_x{plane}")
        a.li(9, 1).b("l5_call")                                    # no crossing: swing, as it would
        a.label(f"l5_x{plane}")
        _fabs(a, 1, 1)
        a.load_addr(4, KONST).lfs(2, 8, 4).fcmpo(1, 2).bgt(f"l5_o{plane}").li(9, 1)
        a.label(f"l5_o{plane}")
        a.fsubs(1, 1, 2)
        _fabs(a, 1, 1)
        a.lfs(2, 12, 4).fcmpo(1, 2).bge(f"l5_n{plane}").li(8, 1)
        a.label(f"l5_n{plane}")
    a.label("l5_call")
    a.cmpwi(8, 0).beq("l5_go")
    a.stb(9, SCR, 10)                                              # (the call, over the rand call)
    a.lwz(3, RNG, 13).li(4, 100).bl(RAND)
    _block(a, 10, 11, "tk2")
    a.lbz(9, SCR, 10)
    a.cmpwi(3, P_EDGE).bge("l5_go").word(d_form(26, 9, 9, 1))     # xori r9,r9,1: the wrong call
    a.label("l5_go")
    a.cmpwi(9, 0).bne("take_done").b("take")
    a.label("take_real")
    for plane in (8, 12):
        a.mr(3, 31).lis(4, ha(ZONE)).lfs(1, lo(ZONE + plane), 4).bl("forecast")
        a.cmpwi(3, 0).beq("take_done")             # no crossing: swing, as it would
        a.lis(4, ha(ZONE)).lfs(2, lo(ZONE), 4).lfs(3, lo(ZONE + 4), 4)
        a.fcmpo(1, 2).blt(f"ball{plane}")
        a.fcmpo(1, 3).ble("take_done")             # a strike at this plane: swing
        a.label(f"ball{plane}")
    a.label("take")
    a.li(0, 1).stb(0, NO_SWING, 29)
    a.label("take_done")
    a.b(SWING_CHECK)
    a.label("take_stock")
    a.word(TAKE_ORIG)
    a.b(TAKE_RET)
    # TRACK
    a.label("track_stub")
    _gate(a, 28, 30, "track_stock")
    a.lwz(4, BATTER, 13).cmpwi(4, 0).bne("batter")
    a.lwz(4, BATTER_ALT, 13)
    a.label("batter")
    a.lis(12, ha(level5.FLAG)).lbz(12, lo(level5.FLAG), 12).cmpwi(12, 1).bne("tr_fore")   # level 5: the plan
    _block(a, 9, 10, "tr")
    a.lbz(0, VALID, 9).cmpwi(0, 0).beq("tr_fore")
    a.lbz(0, ADJ, 9).cmpwi(0, 0).bne("tr_fore")
    a.lwz(5, PLAY, 13).lha(5, TICK, 5).lha(6, REL, 9).subf(6, 6, 5)   # r5 = now, r6 = frames since the release
    a.lha(7, DREACT, 9).cmpw(6, 7).bge("tr_adj")
    a.label("tr_plan")
    a.lfs(3, XHAT, 9)                                              # still the plan: the predicted crossing
    _sign(a, 3, 7, "tr")
    a.lbz(0, DECOY, 28).b(TRACK_RET)
    a.label("tr_adj")                                              # hard pitches: a later adjustment, once
    a.lbz(0, EXT, 9).cmpwi(0, 0).bne("tr_now")
    a.li(0, 1).stb(0, EXT, 9)
    a.load_addr(10, KONST).lfs(1, ZERO, 2)                          # f1 = extra frames
    a.lfs(2, 0x94, 30)
    _fabs(a, 2, 2)
    a.lfs(3, 16, 10).fsubs(2, 2, 3).fcmpo(2, 1).ble("tr_high")     # a lot of curve
    a.lfs(3, 20, 10).fmuls(2, 2, 3).fadds(1, 1, 2)
    a.label("tr_high")
    a.lbz(0, KIND_ROW, 30).cmpwi(0, 2).bne("tr_ext")               # a changeup: by its float
    a.lha(8, CHAR_ID, 30).slwi(8, 8, 3).load_addr(7, CHANGEUP_ARC).add(7, 7, 8)
    a.lfs(2, 0, 7).lfs(3, 24, 10).fsubs(2, 2, 3).lfs(0, ZERO, 2).fcmpo(2, 0).ble("tr_ext")
    a.lfs(3, 28, 10).fmuls(2, 2, 3).fadds(1, 1, 2)
    a.label("tr_ext")
    _fctiwz(a, 1, 1)
    _stfd(a, 1, SCR, 9)
    a.lwz(8, SCR + 4, 9).cmpwi(8, 0).ble("tr_now")
    a.cmpwi(8, EXTRA_MAX).ble("tr_add").li(8, EXTRA_MAX)
    a.label("tr_add")
    a.lha(7, DREACT, 9).add(7, 7, 8).sth(7, DREACT, 9)
    a.cmpw(6, 7).blt("tr_plan")                                     # still the plan
    a.label("tr_now")                                              # the adjustment: from now on the ball
    a.li(0, 1).stb(0, ADJ, 9)
    a.lha(7, 0x110, 30).add(0, 6, 7).sth(0, TACT, 9)               # the flight, measured
    a.lbz(8, SWING_AT, 28).addi(8, 8, 1).cmpw(8, 5).ble("tr_fore")  # the swing has started: too late
    a.add(8, 7, 5).addi(8, 8, -LEAD)                               # re-timed on the real flight
    a.addi(0, 5, 1).cmpw(8, 0).bge("tr_lo").mr(8, 0)
    a.label("tr_lo")
    a.cmpwi(8, 250).ble("tr_hi").li(8, 250)
    a.label("tr_hi")
    a.stb(8, SWING_AT, 28)
    a.label("tr_fore")
    a.lwz(4, BATTER, 13).cmpwi(4, 0).bne("tr_b").lwz(4, BATTER_ALT, 13)
    a.label("tr_b")
    a.lfs(1, 0x40, 4).mr(3, 30).bl("forecast")
    a.cmpwi(3, 0).beq("track_stock")
    a.fmr(3, 1).lbz(0, DECOY, 28).b(TRACK_RET)
    a.label("track_stock")
    a.word(TRACK_ORIG)
    a.lbz(0, DECOY, 28).b(TRACK_RET)               # r0 as the site had it
    forecast(a)
    return a


def _lvl5(a, ai, skip):
    """Branch to `skip` unless level 5 (FLAG == 1) and the batter AI is the hardest-tier CBComBat. Uses r11, r12."""
    a.lis(12, ha(level5.FLAG)).lbz(12, lo(level5.FLAG), 12).cmpwi(12, 1).bne(skip)
    a.lbz(12, TIER, ai).cmpwi(12, 3).bne(skip)
    a.lwz(12, 0, ai).load_addr(11, VTABLE).cmpw(12, 11).bne(skip)


def _block(a, reg, tmp, tag):
    """reg = the batting team's mind block (G+0x2C & 1). Uses tmp."""
    a.load_addr(reg, MIND)
    a.lwz(tmp, GAME, 13).cmpwi(tmp, 0).beq(f"blk_{tag}")
    a.lbz(tmp, BAT_TEAM, tmp).andi_(tmp, tmp, 1).mulli(tmp, tmp, BLOCK).add(reg, reg, tmp)
    a.label(f"blk_{tag}")


def _sign(a, fr, tmp, tag):
    """fr = -fr for a left-handed batter (batter +0xB3). Uses tmp."""
    a.lwz(tmp, BATTER, 13).cmpwi(tmp, 0).bne(f"sg_{tag}").lwz(tmp, BATTER_ALT, 13)
    a.label(f"sg_{tag}")
    a.lbz(tmp, LEFTY, tmp).cmpwi(tmp, 0).beq(f"sn_{tag}")
    a.fneg(fr, fr)
    a.label(f"sn_{tag}")


def _entry(a):
    """Subroutine "entry": r7 = the ring entry k = r8 back from the newest of block r9. Uses r6."""
    a.label("entry")
    a.lwz(6, N, 9).subf(6, 8, 6).addi(6, 6, -1).clrlwi(6, 6, MASK_BITS)
    a.mulli(6, 6, ENTRY).add(7, 9, 6).addi(7, 7, RING_AT)
    a.blr()


def _weight(a, tag):
    """f4 = f2 (the age weight) x (KCTX if entry r7's context != block r9's). r10 = KONST. Uses r0, r5, f5."""
    a.fmr(4, 2).lbz(0, 7, 7).lbz(5, CTX, 9).cmpw(0, 5).beq(f"w_{tag}").lfs(5, 4, 10).fmuls(4, 4, 5)
    a.label(f"w_{tag}")


def mind_stubs(at):
    """The level 5 hooks (docstring LEVEL 5 MIND GAME): labels predict, prepos, time, learn."""
    a = Asm(at)
    # PREDICT (r28 = AI; FUN_800C41D4 saved LR in its own frame; ours: 0x8 block, 0xC m)
    a.label("predict")
    a.stwu(1, -0x20, 1).mflr(0).stw(0, 0x24, 1)
    _lvl5(a, 28, "p_out")
    _block(a, 9, 10, "p")
    a.stw(9, 8, 1)
    a.li(0, 0).stb(0, VALID, 9).stb(0, ADJ, 9).stb(0, REL_OK, 9).stb(0, EXT, 9)
    a.lwz(5, COUNT, 13).lbz(6, STRIKES, 5).lbz(7, BALLS, 5)       # context: 0 ahead, 1 even, 2 behind
    a.cmpw(6, 7).li(0, 1).beq("p_ctx").li(0, 0).bgt("p_ctx").li(0, 2)
    a.label("p_ctx")
    a.stb(0, CTX, 9)
    a.lwz(0, N, 9).cmpwi(0, 0).bne("p_mem")
    a.lfs(0, ZERO, 2).stfs(0, XHAT, 9).li(0, 0).sth(0, THAT, 9).li(0, 1).stb(0, PSTRIKE, 9).b("p_d")
    a.label("p_mem")
    a.cmplwi(0, RING).ble("p_m").li(0, RING)
    a.label("p_m")
    a.stw(0, 0xC, 1)                                               # m = min(N, RING)
    a.lwz(3, RNG, 13).li(4, 100).bl(RAND).cmpwi(3, EPS).bge("p_w")
    a.lwz(3, RNG, 13).lwz(4, 0xC, 1).bl(RAND).b("p_k")             # EPS%: any one at random
    a.label("p_w")                                                 # weighted: the sum, a uniform, the walk
    a.load_addr(10, KONST).lwz(9, 8, 1).li(8, 0).lfs(1, ZERO, 2).lfs(2, ONE, 2).lfs(3, 0, 10)
    a.label("p_sum")
    a.bl("entry")
    _weight(a, "s")
    a.fadds(1, 1, 4).fmuls(2, 2, 3)
    a.addi(8, 8, 1).lwz(0, 0xC, 1).cmpw(8, 0).blt("p_sum")
    a.fmr(2, 1).lfs(1, ZERO, 2).lwz(3, RNG, 13).bl(UNIFORM)         # f1 = r in [0, sum]
    a.load_addr(10, KONST).lwz(9, 8, 1).li(8, 0).lfs(2, ONE, 2).lfs(3, 0, 10)
    a.label("p_walk")
    a.bl("entry")
    _weight(a, "k")
    a.fsubs(1, 1, 4).lfs(0, ZERO, 2).fcmpo(1, 0).ble("p_got")
    a.fmuls(2, 2, 3).addi(8, 8, 1).lwz(0, 0xC, 1).cmpw(8, 0).blt("p_walk")
    a.addi(8, 8, -1)                                               # (rounding: the oldest)
    a.label("p_got")
    a.mr(3, 8)
    a.label("p_k")                                                 # r3 = k (0 = the newest)
    a.lwz(9, 8, 1).mr(8, 3).bl("entry")
    a.lfs(0, 0, 7).stfs(0, XHAT, 9).lha(0, 4, 7).sth(0, THAT, 9)
    a.lfs(1, 0, 7).word(FABS1)
    a.load_addr(10, KONST).lfs(2, 8, 10).li(0, 1).fcmpo(1, 2).ble("p_st").li(0, 0)
    a.label("p_st")
    a.stb(0, PSTRIKE, 9)
    a.label("p_d")
    a.lwz(3, RNG, 13).li(4, DHI - DLO + 1).bl(RAND).addi(3, 3, DLO)
    a.lwz(9, 8, 1).sth(3, DREACT, 9).li(0, 1).stb(0, VALID, 9)
    a.label("p_out")
    a.lwz(0, 0x24, 1).mtlr(0).addi(1, 1, 0x20)
    a.word(PREDICT_ORIG).b(PREDICT_RET)
    _entry(a)
    # PRE-POSITION (r3 = AI; r0, r4-r12, f0 free: the mover reloads them)
    a.label("prepos")
    _lvl5(a, 3, "pp_go")
    _block(a, 5, 6, "pp")
    a.lbz(0, VALID, 5).cmpwi(0, 0).beq("pp_go")
    a.lwz(4, PLAY, 13).cmpwi(4, 0).beq("pp_go")
    a.lha(0, TICK, 4).cmpwi(0, 0).bge("pp_go")
    a.lfs(0, XHAT, 5).stfs(0, 0x14, 3)
    a.label("pp_go")
    a.b(MOVER)
    # TIME (r31 = AI)
    a.label("time")
    _lvl5(a, 31, "t_out")
    _block(a, 9, 10, "t")
    a.lbz(0, VALID, 9).cmpwi(0, 0).beq("t_out")
    a.lwz(8, -0x1580, 13).cmpwi(8, 0).bne("t_p").lwz(8, -0x1584, 13)
    a.label("t_p")
    a.lbz(0, STAR, 8).cmpwi(0, 0).beq("t_ok")
    a.li(0, 0).stb(0, VALID, 9).b("t_out")                          # a star pitch: stock
    a.label("t_ok")
    a.lwz(4, PLAY, 13).lha(4, TICK, 4).sth(4, REL, 9)
    a.lha(5, 0x110, 8).sth(5, T0, 9).li(0, 1).stb(0, REL_OK, 9)
    a.lha(6, THAT, 9).cmpwi(6, 0).ble("t_out")                       # no timing plan
    a.lbz(7, 0x4A, 31).subf(6, 5, 6).add(7, 7, 6)                     # base + (THAT - T0)
    a.addi(6, 4, 1).cmpw(7, 6).bge("t_lo").mr(7, 6)
    a.label("t_lo")
    a.cmpwi(7, 250).ble("t_hi").li(7, 250)
    a.label("t_hi")
    a.stb(7, SWING_AT, 31)
    a.label("t_out")
    a.word(TIME_ORIG).b(TIME_RET)
    # LEARN (r3 = AI, r6 = pitcher; a leaf: r0, r4, r5, r7-r12, f0 free)
    a.label("learn")
    _lvl5(a, 3, "l_out")
    _block(a, 9, 10, "l")
    a.lbz(0, REL_OK, 9).cmpwi(0, 0).beq("l_out")
    a.li(0, 0).stb(0, REL_OK, 9)
    a.lwz(4, N, 9).clrlwi(5, 4, MASK_BITS).mulli(5, 5, ENTRY).add(5, 5, 9).addi(5, 5, RING_AT)
    a.lfs(0, 0xD4, 6)
    _sign(a, 0, 7, "l")
    a.stfs(0, 0, 5)
    a.lha(0, T0, 9).lbz(7, ADJ, 9).cmpwi(7, 0).beq("l_t").lha(0, TACT, 9)
    a.label("l_t")
    a.sth(0, 4, 5).li(0, 0).stb(0, 6, 5).lbz(0, CTX, 9).stb(0, 7, 5)
    a.addi(4, 4, 1).stw(4, N, 9)
    a.label("l_out")
    a.word(LEARN_ORIG).b(LEARN_RET)
    return a


def alloc(data):
    """The level 5 mind game's data (two blocks, zeroed at match start by cpu_pitching's reset) and constants."""
    import struct
    import cpu_pitching
    global MIND, KONST
    MIND = data.put(bytes(2 * BLOCK), align=32)
    KONST = data.put(struct.pack(">8f", M_DECAY, KCTX, EDGE, EDGE_BAND, CURVE_T, CURVE_K, ARC0, HIGH_K), align=4)
    cpu_pitching.EXTRA_RESET[:] = [(MIND, 2 * BLOCK)]           # (this build's only extra; a rebuild replaces it)
    return MIND


def apply(dol, code, data=None):
    """Hook FUN_800C4FF4's take judgement and FUN_800C4AB4's bat target in `dol`, and (with `data`) the level 5 mind
    game's four more sites; the stubs go in `code` (a charbuild Space). Returns log lines."""
    assert level5.FLAG is not None, "level5.alloc(data) first"
    global MIND, KONST
    if data is not None:
        alloc(data)
    elif MIND is None:                              # (tests without a data section: a scratch address, never run)
        MIND, KONST = 0x80000000, 0x80000000
    for site, orig in ((TAKE, TAKE_ORIG), (TRACK, TRACK_ORIG)):
        got = dol.u32(site)
        assert got == orig, f"0x{site:08X}: 0x{got:08X}, expected 0x{orig:08X}"
    at = code.here + (-code.here % 4)
    a = stubs(at)
    blob = a.assemble()
    assert code.put(blob, align=4) == at
    dol.w32(TAKE, branch(TAKE, a.labels["take_stub"]))
    dol.w32(TRACK, branch(TRACK, a.labels["track_stub"]))

    return [f"cpu batter tracking (level 6): ball / strike on the umpire's two planes from the ball's flight, judged "
            f"on the swing frame (0x{TAKE:08X} -> 0x{a.labels['take_stub']:08X}); bat target forecast with the "
            f"crossing interpolated right (0x{TRACK:08X} -> 0x{a.labels['track_stub']:08X}); {len(blob)} bytes"]


MIND_SITES = ((PREDICT, PREDICT_ORIG), (TIME, TIME_ORIG), (LEARN, LEARN_ORIG), (PREPOS, branch(PREPOS, MOVER, True)))


def apply_mind(dol, code):
    """The level 5 mind game's four hooks, their stubs in `code` (charbuild puts them in the pitch model's own
    section, 19b: the item section has no room in the test builds). Needs apply(dol, item_code, data) first (its
    TAKE / TRACK stubs hold the level 5 plan branches; alloc'd the memory). Returns log lines."""
    assert MIND is not None and MIND != 0x80000000, "cpu_track.apply(dol, code, data) first"
    for site, orig in MIND_SITES:
        got = dol.u32(site)
        assert got == orig, f"0x{site:08X}: 0x{got:08X}, expected 0x{orig:08X}"
    at = code.here + (-code.here % 4)
    m = mind_stubs(at)
    blob = m.assemble()
    assert code.put(blob, align=4) == at
    dol.w32(PREDICT, branch(PREDICT, m.labels["predict"]))
    dol.w32(TIME, branch(TIME, m.labels["time"]))
    dol.w32(LEARN, branch(LEARN, m.labels["learn"]))
    dol.w32(PREPOS, branch(PREPOS, m.labels["prepos"], True))
    return [f"cpu batter mind game (level 5): predict 0x{PREDICT:08X}, pre-position 0x{PREPOS:08X}, time 0x{TIME:08X}, "
            f"learn 0x{LEARN:08X} -> 0x{at:08X} ({len(blob)} B); memory 2 x {BLOCK} B at 0x{MIND:08X}"]
