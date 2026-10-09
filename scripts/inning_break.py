"""Box score time between innings (Nick, 2026-09-28: "make it so we can set the time between innings where the box
score shows up"). Feature "inning-break-time" (Game options); option "seconds": 0.5..30, or "stock" / None (nothing
built). docs/replay.md section 6.

The half-inning change is the match state FUN_80132860 (state byte match +0x33; the state table 0x80643B18; it swaps
the sides with FUN_80137554 and reloads the fielders, FUN_80152a30). Its cases:
  0 fade to black, the end-of-half director script (mode 0x10 + match +0xA0);  1 until A or the director is done;
  2 (black) swap sides, open the box score (Gm2d vf70 -> CGm2d_bb_ScoreBdTask, FUN_8032b9b0), director mode 3 (the
    stadium's camera sweep, 0x806B5DA0[stadium*3 + time]), fade from black;
  3 reload the fielders; when done, stock sets D+0x9C = 1 (0x80132AD0; D = the director *(r13-0x85C));
  4 until the 2D is ready;  5 until A (FUN_8012e0b8(match, 0, 0): any controller's A, or 2 on a sideways Remote) or
    the director script has ended (D+0x58 == 0);  6-7 fade to black;  8 close the box score (vf74), director mode 0,
    on to state 0x16.
The mode 3 scripts (0x8079C128..0x8079D044) loop random camera clips `CAM_CLIP n / WAIT_CAMFRAME 0 / ... /
IF_FLAG9C 0 loop` while D+0x9C is 0, and end after the clip that's playing once it is set. So the stock box score
stays for the fielders' reload plus the end of the camera clip playing then: one clip (201..461 frames of the MAF,
dt_na dir 0x7C: 3.4 to 7.7 s by stadium) when the reload is quick, and A skips it. No CPU check: CPU vs CPU waits
the same, and a human's A still skips it.

With a time (all three from the clean words, asserted):
  COUNT  0x80132888 `lbz r0,0x33(r31)` (the state load before the switch) -> stub: the frames in states 3..5 counted
         (reset while in state 2, the box score opening), then the load, back. r11 / r12 free; r3 (the Gm2d) kept.
  LOOP   0x80132AD0 `stb r0,0x9c(r28)` -> nop: the camera sweep keeps looping its clips (the director's end no longer
         ends the box score).
  LEAVE  0x80132B10 `or r3,r31,r31` (case 5's first) -> stub: at N seconds (60 frames a second; 50 at 50 Hz,
         r13-0x1658) set D+0x9C = 1 and state 6, as A does (and return); else the stock case 5 (A still skips).
  SKIP   0x80643CB4 (the switch's jump table, case 1: 0x80132950) -> 0x80132974, case 1's "A pressed" path: the
         end-of-half shot (the camera on a fielder, 2.2 s; mode 0x10) is skipped from its first frame, as A does.
Measured in Dolphin (Wario City night, CPU vs CPU, docs/replay.md section 6): the box score can't close before the
fielder reload FUN_80152a30 is done, and that reload is disc-bound (the new fielding team's 9 models and the
pitcher's and batter's cut-in backdrops, ~13 MB of dt_na reads: 7.3 s there), so the break is about 10 s at 0.5 s.
"""
import struct

COUNT, COUNT_ORIG = 0x80132888, 0x881F0033      # lbz r0,0x33(r31)
LOOP, LOOP_ORIG = 0x80132AD0, 0x981C009C        # stb r0,0x9c(r28)
LEAVE, LEAVE_ORIG = 0x80132B10, 0x7FE3FB78      # or r3,r31,r31
SKIP, SKIP_ORIG = 0x80643CB4, 0x80132950        # the switch's jump table, case 1 (until A or the script's fade)
SKIP_TO = 0x80132974                            # case 1's "A pressed" path: fade to black, on to case 2
BACK_COUNT, BACK_LEAVE, RETURN = 0x8013288C, 0x80132B14, 0x80132C24
NOP = 0x60000000
HZ50 = -0x1658                                  # r13: nonzero at 50 Hz (spin_effect)
STATE, D_FLAG = 0x33, 0x9C
LIMITS = (0.5, 30.0)
STOCK = "stock"
STOCK_WORDS = "one camera pass, about 3.4 to 7.7 seconds by stadium; A skips it"
DEFAULTS = {"seconds": STOCK}
LAYOUT = {}                                     # "count", "stub_count", "stub_leave" (tests)


def check(value):
    """seconds: a number 0.5..30 (float), or None for stock ("stock", blank, None). ValueError in plain words."""
    if value is None or str(value).strip().lower() in ("", STOCK):
        return None
    try:
        v = float(str(value).strip())
    except ValueError:
        raise ValueError(f"box score time: {value!r} isn't a number of seconds") from None
    lo, hi = LIMITS
    if not lo <= v <= hi:
        raise ValueError(f"box score time: {v:g} seconds is outside {lo:g} to {hi:g}")
    return v


def frames(seconds, hz=60):
    return max(1, int(round(seconds * hz)))


def apply(dol, code, seconds=None):
    """Hook the half-inning change so the box score stays `seconds` (check()); None: stock (nothing written)."""
    seconds = check(seconds)
    if seconds is None:
        return ["Box score between innings: stock (" + STOCK_WORDS + ")"]
    from ppc import Asm, branch
    for a, w in ((COUNT, COUNT_ORIG), (LOOP, LOOP_ORIG), (LEAVE, LEAVE_ORIG), (SKIP, SKIP_ORIG)):
        got = dol.u32(a)
        assert got == w, f"0x{a:08X}: 0x{got:08X}, expected the clean 0x{w:08X}"
    count = LAYOUT["count"] = code.put(bytes(4), align=4)

    at = code.here + (-code.here % 4)
    a = Asm(at)
    a.word(COUNT_ORIG).load_addr("r12", count)
    a.cmplwi("r0", 2).bne("not2").li("r11", 0).stw("r11", 0, "r12").b(BACK_COUNT)
    a.label("not2")
    a.cmplwi("r0", 3).blt("back").cmplwi("r0", 5).bgt("back")
    a.lwz("r11", 0, "r12").addi("r11", "r11", 1).stw("r11", 0, "r12")
    a.label("back")
    a.b(BACK_COUNT)
    LAYOUT["stub_count"] = at
    assert code.put(a.assemble(), align=4) == at

    at = code.here + (-code.here % 4)
    a = Asm(at)
    a.load_addr("r12", count).lwz("r11", 0, "r12")
    a.lbz("r4", HZ50, "r13").cmpwi("r4", 0).li("r5", frames(seconds, 60)).beq("cmp").li("r5", frames(seconds, 50))
    a.label("cmp")
    a.cmpw("r11", "r5").blt("stock")
    a.li("r0", 1).stb("r0", D_FLAG, "r28").li("r0", 6).stb("r0", STATE, "r31").b(RETURN)
    a.label("stock")
    a.word(LEAVE_ORIG).b(BACK_LEAVE)
    LAYOUT["stub_leave"] = at
    assert code.put(a.assemble(), align=4) == at

    dol.w32(COUNT, branch(COUNT, LAYOUT["stub_count"]))
    dol.w32(LOOP, NOP)
    dol.w32(LEAVE, branch(LEAVE, LAYOUT["stub_leave"]))
    dol.w32(SKIP, SKIP_TO)
    return [f"Box score between innings: {seconds:g} seconds ({frames(seconds, 60)} frames; "
            f"{frames(seconds, 50)} at 50 Hz), A still skips it (0x{COUNT:08X} / 0x{LEAVE:08X} -> "
            f"0x{LAYOUT['stub_count']:08X} / 0x{LAYOUT['stub_leave']:08X}, 0x{LOOP:08X} nop); "
            f"the end-of-half fielder shot skipped (0x{SKIP:08X} -> 0x{SKIP_TO:08X})"]
