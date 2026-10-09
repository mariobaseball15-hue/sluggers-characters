"""The level 5 / 6 rundown log (Nick, 2026-09-28: a human heading back is SAFE every time, the throw arriving after
him, on a build with db6e1fb; "we need evidence from the real game"). One ring in the data section, two kinds of
fixed-size records, read from a MEM1 dump by scripts/read_rundown_log.py. Off (LOG_ENTRIES = 0: no data, no code, the
rundown body byte for byte as before) in normal builds; build_test_items.py turns it on. Same model as the item log
(cpu_items.py LOG_ENTRIES / read_item_log.py) and the defense log (cpu_defense_log.py / read_defense_log.py).

WHERE IT RUNS
- BODY records (kind 1 / 2): the level 5 / 6 rundown body (cpu_rundown.body) with the log on keeps FUN_800E0F98's raw
  plan (throw, carry, margin: "pre") in its scratch right after the call, and leaves through this stub instead of
  `b 0x800E0F60` (a `bctr` through a pointer word in its scratch; the stub ends with `b 0x800E0F60`). So one record
  per body run, after the commit: the committed plan ("post", ai+0x29C / +0x28C / +0x27C [r]) next to the raw one.
  Logged when the runner is heading back (+0x183 == 3) or stopped between bases (2 and +0x138 < 0) (kind 1, always),
  or for any other runner while a rundown is being watched (the frame stub's tail > 0; kind 1 going forward, kind 2
  = the body ran but plans nothing, as stock). The stub recomputes nothing the body decides with: it logs the body's
  inputs (runner, W = FUN_8011A66C(holder), the planner's flight FUN_800CA018 to the plan's base, the roll and throw
  count from the body's STATE), and read_rundown_log.py replays the body's heading-back rule on them in float32 (it
  reports the rule that fired and flags a record whose committed plan differs from the replay).
  Registers in the stub: r27 = ai, r29 = 4 * r, r30 = the runner (FUN_800E05E8's); free r0, r3-r12, f0-f13, cr0, LR
  (the epilogue reloads it). The field is reloaded from *(r13-0x1D94) (the body's Ball Dash leaves the holder in r31).
- FRAME records (kind 3): the per-frame hook 0x801327C0 (FUN_801326fc after FUN_800C8384, the whole fielding frame:
  cpu_defense_log.py's docstring; the throw planner FUN_800CC3B0 -> FUN_800DF7D0 -> FUN_800E05E8 runs inside it [I:
  through the ai's vtable +0xC]). Chained: the stub ends with whatever the hook word was (the defense log's `b`, or the
  stock `lwz r3,-0x15b4(r13)` + `b` back). At levels 5 / 6 (level5.FLAG != 0), while any runner on the field (+0x176)
  is heading back or stopped between bases, and TAIL (90) frames after: one record with the ball (holder, thrown /
  state +0x2A72, frames left +0x2A42, the holder's base +0x2A56), the throw planner's gates and outputs (frames holding
  the ball *(r13-0x1684)+0xA and the stock hold threshold T = 0x806249F4 (infield) / 0x806249F9 [mode * 10 + the
  holder's +0x2E], ai+0x2FC throw target, +0x308 pending throw, +0x2AC runner mask, +0x2B4, the picked runners
  +0x2BC..+0x2C8, +0x33D, game +0x2A65 / +0x2A74 / +0x2A4E), the outs (*(r13-0x1D38)+9), and per runner slot
  (0x807098C8[i]): on the field, direction, from / to, +0x14A (forced), +0x18D, +0x1A9, +0x138, leg fraction +0xA8, and
  the planner's bin / throw / carry for him (ai+0x26C / +0x29C / +0x28C [i]).
  Why: FUN_800DF7D0 sends a runner to FUN_800E05E8 (our body) only when +0x176 == 1, +0x1A9 != 2, (+0x138 == -1 or
  +0x14A > 0), +0x18D == 0 and +0x14A != 1 (a forced runner goes to FUN_800E01C4, +0x1A9 == 2 to FUN_800DFA6C); and
  FUN_800CC3B0 plans nothing at all while the holder has held the ball fewer than T frames (and with outs > 2,
  +0x2A4E == -1, +0x2A74 or ai+0x33D). The frame records show which, when a heading-back runner has no body record.

HEADER (0x20 B): b"L6RL", u32 records written, u32 entries (a power of 2), u32 record size, u32 tail countdown,
u32 the record being written (the body stub reloads it over its calls), pad.
RECORDS (REC = 0x60 B, big-endian) at header + 0x20 + (seq % entries) * REC; byte 0 = the kind; the fields are
BODY_FIELDS / FRAME_FIELDS / RUNNER_FIELDS below (the reader decodes from them).
Outcome: the release (holder -> none, +0x2A72), the catch (none -> a holder, +0x2A56 his base), the runner's leg
fraction reaching his safe line (0.03 of the leg) and the outs count come from the frame records. NOT logged: the
function that calls the out / safe itself (not found, docs/runners.md), the ball's position, a human's inputs.
"""
import struct
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
import level5  # noqa: E402
from ppc import Asm, branch, d_form, ha, lo  # noqa: E402

LOG_ENTRIES = 0                   # 0 = off (normal builds); build_test_items.py sets it (a power of 2)
MAGIC, HDR, REC = b"L6RL", 0x20, 0x60
W_TAIL, W_CUR = 0x10, 0x14        # header words: the frames still logged; the record being written
TAIL = 90                         # frames logged after the last heading-back / stopped runner
SECTION = 0x1000                  # charbuild step 19c: the stubs' own text section (test builds only; 0x86C B)
KIND_PLAN, KIND_NOPLAN, KIND_FRAME = 1, 2, 3

HOOK = 0x801327C0
ORIG = d_form(32, 3, 13, -0x15B4)  # lwz r3,-0x15b4(r13)
RUNNERS = 0x807098C8               # 4 runner pointers (slot 0 the batter-runner)
DEFENSE = (-0x1D14, -0x1D10, -0x1D18, -0x1D1C)   # the defense ai: the first non-null (as cpu_defense_log)
GAME, TICK, OUTS, MODE = -0x1D94, -0x1684, -0x1D38, -0x1658
HOLD_T = 0x806249F4                # FUN_800CC3B0's hold threshold bytes: [mode * 10 + level], outfield (id >= 6) +5
BCTR = 0x4E800420

# (name, kind, offset): kind "b" s8, "B" u8, "h" s16, "f" f32, "I" u32
BODY_FIELDS = [
    ("kind", "B", 0x00), ("r", "B", 0x01), ("dir", "B", 0x02), ("from", "B", 0x03), ("to", "B", 0x04),
    ("flags", "B", 0x05),            # 1 CPU runner (S+0x24+team), 2 early roll (STATE+12), 4 ai+0x2D4[r] (zone byte)
    ("W", "B", 0x06),                # FUN_8011A66C(holder); 0xFF: no holder (W, flight not logged)
    ("throws", "b", 0x07),           # STATE+8: throws this rundown (0 = the fielder who fielded it)
    ("play", "h", 0x08), ("holder", "h", 0x0A),
    ("base138", "h", 0x0C), ("to_frames", "h", 0x0E), ("back_frames", "h", 0x10),   # +0x138, +0x140, +0x142
    ("flight", "h", 0x12),           # FUN_800CA018(base b's x, z): the planner's flight, frames; -1 none
    ("pre_throw", "b", 0x14), ("pre_carry", "b", 0x15),     # FUN_800E0F98's raw plan (before the chase / rules)
    ("post_throw", "b", 0x16), ("post_carry", "b", 0x17),   # committed (ai+0x29C / +0x28C [r])
    ("pre_m", "h", 0x18), ("post_m", "h", 0x1A),
    ("frac", "f", 0x1C), ("vel", "f", 0x20), ("past", "f", 0x24), ("leg", "f", 0x28),   # +0xA8 +0xC4 +0x9C +0xAC
    ("cap", "f", 0x2C), ("mash", "f", 0x30), ("turn", "f", 0x34),   # +0xE0*+0x114, +0x104, +0xDC*+0x11C
    ("cover", "h", 0x38), ("cover_eta", "h", 0x3A),        # ai+0x2EE[b], his +0x1DC (0x7FFF: none)
    ("zone", "B", 0x3C), ("r185", "B", 0x3D), ("zone_byte", "B", 0x3E),   # game+0x2A6B, +0x185, ai+0x2D4[r]
    ("b", "B", 0x3F),                # the base the flight / cover are for: the raw plan's (b or b+10), else
                                     # the base behind (heading back) / ahead
    ("held", "h", 0x40),             # *(r13-0x1684)+0xA: frames the holder has had the ball
    ("ball_from", "f", 0x44), ("ball_to", "f", 0x48),      # game+0x29BC[from / to]: the ball's distance to them
    ("ball_d", "f", 0x4C),           # +0x90: the runner's distance to the ball
]
FRAME_FIELDS = [
    ("kind", "B", 0x00), ("ball_state", "B", 0x01), ("zone", "B", 0x02), ("outs", "B", 0x03),   # +0x2A72 +0x2A6B
    ("play", "h", 0x04), ("held", "h", 0x06), ("holder", "h", 0x08), ("ball_left", "h", 0x0A),  # +0x2A42
    ("target", "h", 0x0C), ("pending", "h", 0x0E),         # ai+0x2FC, ai+0x308
    ("mask", "I", 0x10),                                     # ai+0x2AC
    ("pick0", "b", 0x14), ("pick1", "b", 0x15), ("pick2", "b", 0x16), ("pick3", "b", 0x17),   # ai+0x2BC..+0x2C8
    ("ai2B4", "B", 0x18), ("ai33D", "B", 0x19), ("g2A65", "B", 0x1A), ("g2A74", "B", 0x1B),
    ("g2A4E", "b", 0x1C), ("hbase", "b", 0x1D),             # +0x2A4E (low byte), +0x2A56 the holder's base
    ("hlevel", "B", 0x1E), ("hold_t", "B", 0x1F),            # holder +0x2E, T (0xFF: no holder)
]
RUNNER_AT, RUNNER_SIZE = 0x20, 0x10
RUNNER_FIELDS = [
    ("on", "B", 0x0), ("dir", "B", 0x1), ("from", "B", 0x2), ("to", "B", 0x3),   # +0x176 +0x183 +0x17D +0x17E
    ("forced", "B", 0x4), ("r18D", "B", 0x5), ("r1A9", "B", 0x6),              # +0x14A (low byte) +0x18D +0x1A9
    ("bin", "b", 0x7), ("throw", "b", 0x8), ("carry", "b", 0x9),              # ai+0x26C / +0x29C / +0x28C [i]
    ("base138", "h", 0xA), ("frac", "f", 0xC),                                  # +0x138, +0xA8
]
LOGP = None                        # the ring's address (alloc)
SCRATCH = None                     # the body's scratch (cpu_rundown.apply)
PTR = None                         # the body's pointer word to the body stub


def _store(a, kind, src, off, reg, dst):
    if kind == "f":
        a.lfs(0, off, reg).stfs(0, dst, 9)
    elif kind == "h":
        a.lha(0, off, reg).sth(0, dst, 9)
    else:
        a.lbz(0, off, reg).stb(0, dst, 9)


def _new_record(a, logp):
    """r8 = the header, r9 = the next record (cleared), counted; W_CUR = r9. Uses r0, r5-r7."""
    a.load_addr(8, logp)
    a.lwz(5, 4, 8).addi(0, 5, 1).stw(0, 4, 8)
    a.lwz(6, 8, 8).addi(6, 6, -1).word((31 << 26) | (5 << 21) | (6 << 16) | (6 << 11) | (28 << 1))  # and r6,r5,r6
    a.mulli(6, 6, REC).add(9, 8, 6).addi(9, 9, HDR)
    a.stw(9, W_CUR, 8)
    a.li(0, 0).mr(6, 9).addi(7, 9, REC)
    a.label("clr")
    a.stw(0, 0, 6).addi(6, 6, 4).cmpw(6, 7).blt("clr")


def body_stub(at, logp, scratch):
    """The body's exit with the log on (see the docstring). Ends with `b EPILOGUE`."""
    import cpu_rundown as c
    a = Asm(at)
    a.load_addr(8, logp)
    a.lbz(0, 0x183, 30).li(10, KIND_PLAN)
    a.cmplwi(0, 3).beq("go")                                          # heading back: always
    a.cmplwi(0, 2).bne("fwd")
    a.lha(3, 0x138, 30).cmpwi(3, 0).blt("go")                          # stopped between bases: always
    a.li(10, KIND_NOPLAN).b("tail")
    a.label("fwd")
    a.cmplwi(0, 1).beq("tail")
    a.li(10, KIND_NOPLAN)
    a.label("tail")
    a.lwz(3, W_TAIL, 8).cmpwi(3, 0).ble("out")                        # others: while a rundown is watched
    a.label("go")
    _new_record(a, logp)
    a.stb(10, 0, 9)
    a.load_addr(11, scratch)
    a.lwz(4, c.R4, 11).stb(4, 1, 9)                                    # the runner index (the hook's r4)
    for off, dst in ((0x183, 2), (0x17D, 3), (0x17E, 4), (0x185, 0x3D)):
        a.lbz(0, off, 30).stb(0, dst, 9)
    a.li(3, 0)                                                         # flags
    a.lwz(5, c.GAME, 13).cmpwi(5, 0).beq("f1")                         # a CPU runner: S+0x24+team (as the body)
    a.lbz(5, 0x2C, 5).lwz(6, c.SETTINGS, 13).cmpwi(6, 0).beq("f1")
    a.add(6, 6, 5).lbz(0, 0x24, 6).cmpwi(0, 0).beq("f1").ori(3, 3, 1)
    a.label("f1")
    a.lwz(0, c.STATE + 12, 11).cmpwi(0, 0).beq("f2").ori(3, 3, 2)    # the early roll
    a.label("f2")
    a.add(5, 27, 4).lbz(0, 0x2D4, 5).stb(0, 0x3E, 9).cmpwi(0, 0).beq("f3").ori(3, 3, 4)
    a.label("f3")
    a.stb(3, 5, 9)
    a.lwz(0, c.STATE + 8, 11).stb(0, 7, 9)
    a.li(0, -1).stb(0, 6, 9).sth(0, 0x12, 9)                          # W, flight: none until found
    a.lwz(5, TICK, 13).cmpwi(5, 0).beq("np")
    a.lha(0, 0, 5).sth(0, 8, 9).lha(0, 0xA, 5).sth(0, 0x40, 9)
    a.label("np")
    a.lwz(12, GAME, 13)                                                # the field
    a.lha(0, 0x2A4C, 12).sth(0, 0xA, 9)
    for off, dst in ((0x138, 0xC), (0x140, 0xE), (0x142, 0x10)):
        a.lha(0, off, 30).sth(0, dst, 9)
    a.lwz(0, c.PRE + 4, 11).stb(0, 0x14, 9).lwz(0, c.PRE + 8, 11).stb(0, 0x15, 9)
    a.lwz(0, c.PRE, 11).sth(0, 0x18, 9)
    a.add(5, 27, 29)                                                   # committed
    a.lwz(0, c.THROW, 5).stb(0, 0x16, 9).lwz(0, c.CARRY, 5).stb(0, 0x17, 9).lwz(0, c.MARGIN, 5).sth(0, 0x1A, 9)
    for off, dst in ((0xA8, 0x1C), (0xC4, 0x20), (0x9C, 0x24), (0xAC, 0x28), (0x104, 0x30), (0x90, 0x4C)):
        a.lfs(0, off, 30).stfs(0, dst, 9)
    a.lfs(0, c.R_TOP, 30).lfs(1, c.R_TOP_K, 30).fmuls(0, 0, 1).stfs(0, 0x2C, 9)
    a.lfs(0, c.R_TURN, 30).lfs(1, c.R_TURN_K, 30).fmuls(0, 0, 1).stfs(0, 0x34, 9)
    a.lbz(0, c.BALL_ZONE, 12).stb(0, 0x3C, 9)
    a.lbz(5, 0x17D, 30).cmplwi(5, 3).ble("bd").li(5, 0)
    a.label("bd")
    a.slwi(5, 5, 2).add(5, 5, 12).lfs(0, c.BALL_TO_BASE, 5).stfs(0, 0x44, 9)
    a.lbz(5, 0x17E, 30).clrlwi(5, 5, 30).slwi(5, 5, 2).add(5, 5, 12).lfs(0, c.BALL_TO_BASE, 5).stfs(0, 0x48, 9)
    a.lwz(5, c.PRE + 4, 11)                                            # b: the raw plan's base (b, or b + 10)
    a.cmplwi(5, 3).ble("b_ok")
    a.addi(5, 5, -10).cmplwi(5, 3).ble("b_ok")
    a.lbz(0, 0x183, 30).cmplwi(0, 3).bne("b_to")                       # none: behind / ahead
    a.lbz(5, 0x17D, 30).cmplwi(5, 3).ble("b_ok").li(5, 0).b("b_ok")
    a.label("b_to")
    a.lbz(5, 0x17E, 30).clrlwi(5, 5, 30)
    a.label("b_ok")
    a.stb(5, 0x3F, 9)
    a.li(0, 0x7FFF).sth(0, 0x3A, 9)
    a.slwi(6, 5, 1).add(6, 6, 27).lha(4, c.COVER, 6).sth(4, 0x38, 9)   # the cover of b and his ETA
    c._fielder(a, "no_cv", "cv")
    a.lha(0, c.ETA, 3).sth(0, 0x3A, 9)
    a.label("no_cv")
    a.lha(4, 0x2A4C, 12)
    c._fielder(a, "out", "hw")                                         # the holder: W, and the flight to b
    a.bl(c.WINDUP)
    a.load_addr(8, logp).lwz(9, W_CUR, 8).stb(3, 6, 9)
    a.lbz(4, 0x3F, 9).slwi(4, 4, 3).load_addr(3, c.BASE_XZ).add(3, 3, 4)
    a.lfs(1, 0, 3).lfs(2, 4, 3).bl(c.FLIGHT)
    a.load_addr(8, logp).lwz(9, W_CUR, 8).sth(3, 0x12, 9)
    a.label("out")
    a.b(c.EPILOGUE)
    return a


def _chained(prev):
    """Where the frame stub goes on: None = the stock word (run it, then back); else the target of the hook's `b`."""
    if prev == ORIG:
        return None
    assert prev >> 26 == 18 and prev & 3 == 0, f"0x{HOOK:08X}: 0x{prev:08X}, not the stock word or a b"
    off = prev & 0x03FFFFFC
    off -= (1 << 26) if off & 0x02000000 else 0
    return HOOK + off


def frame_stub(at, logp, prev):
    import cpu_rundown as c
    a = Asm(at)
    level5.gate(a, 12, "out", "cpu-rundown")    # (the log runs where the rundowns do)
    a.lwz(11, GAME, 13).cmpwi(11, 0).beq("out")
    for off in DEFENSE:
        a.lwz(12, off, 13).cmpwi(12, 0).bne("ai")
    a.b("out")
    a.label("ai")
    a.load_addr(8, logp)
    a.li(7, 0).lis(10, ha(RUNNERS))                                    # r7: a rundown is on
    for i in range(4):
        a.lwz(5, lo(RUNNERS) + 4 * i, 10).cmpwi(5, 0).beq(f"nx{i}")
        a.lbz(0, 0x176, 5).cmpwi(0, 0).beq(f"nx{i}")
        a.lbz(0, 0x183, 5).cmplwi(0, 3).beq(f"act{i}")
        a.cmplwi(0, 2).bne(f"nx{i}")
        a.lha(0, 0x138, 5).cmpwi(0, 0).bge(f"nx{i}")
        a.label(f"act{i}")
        a.li(7, 1)
        a.label(f"nx{i}")
    a.cmpwi(7, 0).beq("idle")
    a.li(0, TAIL).stw(0, W_TAIL, 8).b("rec")
    a.label("idle")
    a.lwz(3, W_TAIL, 8).cmpwi(3, 0).ble("out")
    a.addi(3, 3, -1).stw(3, W_TAIL, 8)
    a.label("rec")
    _new_record(a, logp)
    a.li(0, KIND_FRAME).stb(0, 0, 9)
    a.lbz(0, 0x2A72, 11).stb(0, 1, 9).lbz(0, 0x2A6B, 11).stb(0, 2, 9)
    a.li(0, -1).stb(0, 3, 9).stb(0, 0x1E, 9).stb(0, 0x1F, 9)
    a.lwz(5, OUTS, 13).cmpwi(5, 0).beq("no_outs").lbz(0, 9, 5).stb(0, 3, 9)
    a.label("no_outs")
    a.lwz(5, TICK, 13).cmpwi(5, 0).beq("np").lha(0, 0, 5).sth(0, 4, 9).lha(0, 0xA, 5).sth(0, 6, 9)
    a.label("np")
    a.lha(0, 0x2A4C, 11).sth(0, 8, 9).lha(0, 0x2A42, 11).sth(0, 0xA, 9)
    a.lha(0, 0x2FC, 12).sth(0, 0xC, 9).lha(0, 0x308, 12).sth(0, 0xE, 9)
    a.lwz(0, 0x2AC, 12).stw(0, 0x10, 9)
    for off, dst in ((0x2BF, 0x14), (0x2C3, 0x15), (0x2C7, 0x16), (0x2CB, 0x17), (0x2B7, 0x18), (0x33D, 0x19)):
        a.lbz(0, off, 12).stb(0, dst, 9)
    for off, dst in ((0x2A65, 0x1A), (0x2A74, 0x1B), (0x2A4F, 0x1C), (0x2A57, 0x1D)):
        a.lbz(0, off, 11).stb(0, dst, 9)
    for i in range(4):
        r = RUNNER_AT + RUNNER_SIZE * i
        a.lbz(0, 0x26F + 4 * i, 12).stb(0, r + 7, 9)                   # the planner's bin / throw / carry for him
        a.lbz(0, 0x29F + 4 * i, 12).stb(0, r + 8, 9)
        a.lbz(0, 0x28F + 4 * i, 12).stb(0, r + 9, 9)
        a.lwz(5, lo(RUNNERS) + 4 * i, 10).cmpwi(5, 0).beq(f"no{i}")
        for off, d in ((0x176, 0), (0x183, 1), (0x17D, 2), (0x17E, 3), (0x14B, 4), (0x18D, 5), (0x1A9, 6)):
            a.lbz(0, off, 5).stb(0, r + d, 9)
        a.lha(0, 0x138, 5).sth(0, r + 0xA, 9)
        a.lfs(0, 0xA8, 5).stfs(0, r + 0xC, 9)
        a.label(f"no{i}")
    a.lha(4, 0x2A4C, 11)                                               # the holder's level and hold threshold
    c._fielder(a, "out", "hg")
    a.lbz(6, 0x2E, 3).stb(6, 0x1E, 9)
    a.lha(4, 0x2A4C, 11).load_addr(5, HOLD_T).cmpwi(4, 6).blt("t_in").addi(5, 5, 5)
    a.label("t_in")
    a.lbz(0, MODE, 13).mulli(0, 0, 10).add(5, 5, 0).add(5, 5, 6).lbz(0, 0, 5).stb(0, 0x1F, 9)
    a.label("out")
    target = _chained(prev)
    if target is None:
        a.word(ORIG).b(HOOK + 4)
    else:
        a.b(target)
    return a


def alloc(data, scratch):
    """With LOG_ENTRIES: the ring in `data`; `scratch` = the body's scratch (cpu_rundown.apply). Returns the ring."""
    global LOGP, SCRATCH
    assert LOG_ENTRIES & (LOG_ENTRIES - 1) == 0, "LOG_ENTRIES: a power of 2"
    LOGP = data.put(MAGIC + struct.pack(">3I", 0, LOG_ENTRIES, REC) + bytes(HDR - 16 + LOG_ENTRIES * REC), align=32)
    SCRATCH = scratch
    return LOGP


def apply_code(dol, code):
    """With LOG_ENTRIES (after cpu_rundown.apply, which allocated the ring and the pointer word, and after
    cpu_defense_log.apply, whose hook this chains): both stubs in `code`, the body's pointer word set, the frame hook.
    Returns log lines."""
    if not LOG_ENTRIES:
        return []
    assert LOGP is not None and PTR is not None, "cpu_rundown.apply(dol, code, data) with the log on first"
    import cpu_rundown as c
    at = code.here + (-code.here % 4)
    blob = body_stub(at, LOGP, SCRATCH).assemble()
    assert code.put(blob, align=4) == at
    assert dol.u32(PTR) == c.EPILOGUE, f"the body's log pointer 0x{PTR:08X}: 0x{dol.u32(PTR):08X}"
    dol.w32(PTR, at)
    body_at, body_len = at, len(blob)
    prev = dol.u32(HOOK)
    at = code.here + (-code.here % 4)
    blob = frame_stub(at, LOGP, prev).assemble()
    assert code.put(blob, align=4) == at
    dol.w32(HOOK, branch(HOOK, at))
    target = _chained(prev)
    chained = "the stock word" if target is None else f"b 0x{target:08X}"
    return [f"cpu rundown log (levels 5 / 6): body exit -> 0x{body_at:08X} ({body_len} B), frame 0x{HOOK:08X} -> "
            f"0x{at:08X} ({len(blob)} B, then {chained}); {LOG_ENTRIES} x {REC} B records at 0x{LOGP:08X} "
            f"({HDR + LOG_ENTRIES * REC} B data; scripts/read_rundown_log.py)"]
