"""CPU vs CPU (Nick, via git-92, 2026-09-26): in an Exhibition, both teams are played by the CPU, so a player picks the
captains, the teams and the stadium as usual and then watches. Feature "cpu-vs-cpu" (Testing); off by default.

The match settings (setup = *(r13-0xB00)) say who controls what: +0x16 / +0x17 the controller leading each team,
+0x18..+0x1B the team of controller 0..3; 0xFF (-1) means the CPU / not playing. Exhibition captain select
(CExhiCaptainTask, FUN_802cb688 case 4) writes them when the players commit; the draft (the roster screen) and the
match read them live. quickboot's CPU-vs-CPU builds (heap-cal-1, bank8-1) had all six 0xFF, and those matches ran CPU
vs CPU.

The Exhibition task (Select::CExhiMainTask, FUN_802cec18, state byte +0x18) runs 5 captain select, 7/8 the roster
screen (the draft), 9 on to the match. In state 8 the roster screen's result +0x1C == 1 (confirmed) sets task +0x1C = 1
and state 9; 2 goes back to captain select (5).
  CONFIRM 0x802CEE64 (`li r0,9`, the confirmed branch only): the six bytes are saved (SAVE) and become 0xFF; then
          the replaced instruction. r3 (1, stored next) is kept; r11 / r12 are free.
  REOPEN  0x802CED3C (`li r3,3`, state 5's first instruction: captain select opens again, the next Exhibition): the
          saved bytes go back, so the players' controllers work in the menus as before; captain select then writes its
          own. r0 / r11 / r12 and cr0 are free (a call follows).
So the menus (captain select, the draft) are stock, and only the match that follows a confirmed draft is CPU vs CPU.
Tested in game: Nick's isos/cpuvcpu-4.iso passed (2026-09-26, via git-92).

History: v1 hooked the match controller's init (0x80133C38), which runs before captain select commits
(analysis/ramdump-cpuvcpu); v2 the at-bat setup, gated on setup +0x10 == 2, which is not an Exhibition flag (2 in one
of Nick's Exhibitions, 0 in the next: analysis/ramdump-cpuvcpu-2); v3 FUN_80063cd0, a method of the 2D controller-icon
objects (Dajun_local::CS2d_*), which also runs on the character select screen, so the draft lost its controller.
C²'s community code "CPU vs CPU V2" (refs/GECKO_CODES_AND_MODS_LIST.txt) writes +0x18 there only while a button combo
is held at "Begin" for the same reason.
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
from ppc import Asm, branch  # noqa: E402

CONFIRM, CONFIRM_ORIG = 0x802CEE64, 0x38000009     # li r0,9
REOPEN, REOPEN_ORIG = 0x802CED3C, 0x38600003       # li r3,3
SETUP = -0xB00                                     # r13: the match settings
LEADERS, PADS = 0x16, 0x18                         # u8 x2: each team's leading controller; u8 x4: each pad's team
SAVE_SIZE = 12                                     # +0 leaders (u16), +4 pads (u32), +8 saved flag (u8)
LAYOUT = {}                                        # "save": its address (tests)


def confirm_stub(base, save):
    a = Asm(base)
    a.lwz(12, SETUP, 13).load_addr(11, save)
    a.lhz(0, LEADERS, 12).sth(0, 0, 11).lwz(0, PADS, 12).stw(0, 4, 11)
    a.li(0, 1).stb(0, 8, 11)
    a.li(0, -1).sth(0, LEADERS, 12).stw(0, PADS, 12)
    a.word(CONFIRM_ORIG)                           # li r0,9
    a.b(CONFIRM + 4)
    return a


def reopen_stub(base, save):
    a = Asm(base)
    a.load_addr(11, save).lbz(0, 8, 11).cmpwi(0, 0).beq("back")
    a.lwz(12, SETUP, 13)
    a.lhz(0, 0, 11).sth(0, LEADERS, 12).lwz(0, 4, 11).stw(0, PADS, 12)
    a.li(0, 0).stb(0, 8, 11)
    a.label("back")
    a.word(REOPEN_ORIG)                            # li r3,3
    a.b(REOPEN + 4)
    return a


def apply(dol, code):
    """Hook the Exhibition task in `dol`; the stubs and SAVE go in `code` (charbuild's item section)."""
    for site, orig in ((CONFIRM, CONFIRM_ORIG), (REOPEN, REOPEN_ORIG)):
        got = dol.u32(site)
        assert got == orig, f"0x{site:08X}: 0x{got:08X}, expected 0x{orig:08X}"
    save = LAYOUT["save"] = code.put(bytes(SAVE_SIZE), align=4)
    out = []
    for site, fn in ((CONFIRM, confirm_stub), (REOPEN, reopen_stub)):
        at = code.here + (-code.here % 4)
        assert code.put(fn(at, save).assemble(), align=4) == at
        dol.w32(site, branch(site, at))
        out.append(f"0x{site:08X} -> 0x{at:08X}")
    return [f"cpu vs cpu: an Exhibition's match after a confirmed draft is CPU vs CPU; the menus stay stock "
            f"({', '.join(out)})"]
