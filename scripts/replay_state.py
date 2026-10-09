"""Our level 5 / 6 CPU state follows the instant replay's snapshots (Nick, 2026-09-28: "the cpu 5-6 does different
things for the replay vs in game"). docs/replay.md §1: a replay re-runs the play from a snapshot of the game's own
state; our CPU modules keep learning / aim / memory blocks of their own that the snapshot doesn't hold, so the replay
chose differently, and the pitch model's learning update (frame 1 of a pitch) ran a second time in the replay and
carried into the real game.

  SAVE     0x8016E39C, FUN_8016E39C(snapshot)'s first instruction (the game saving a snapshot: the play's start,
           FUN_8016D9E8; the live game before a replay, FUN_8016DAC0): copy every REGION into the buffer that goes with
           that snapshot (A: R+0x135600's, the play's start; B: any other, the live game).
  RESTORE  0x8017498C, FUN_8017498C(snapshot)'s first instruction (a replay starting from the play's start; the live
           game coming back after it): copy the snapshot's buffer back into the regions.
Both functions are called only by the replay code, with r3 = the snapshot; r0 and r4..r12 are free at their entry.
The copies are word by word (every region is a whole number of words). Own section (SECTION), charbuild step 19e.

REGIONS (the modules' mutable blocks, found by the build; constants and code are left alone):
  cpu_pitching  LAYOUT["state"] (2 x SIZE, one per batting team) and the K_TARGET word of LAYOUT["consts"]
  cpu_track     MIND (2 x BLOCK)
  cpu_items     DATA's header (RECS bytes: aim, shots, level 5 errors) and SHOTB (SHOTB_SIZE)
  cpu_item_defense  defense_dbg.ADDR (SIZE: PHASE / FLAGS / AUX1 are read back)
  cpu_rundown   LAYOUT["scratch"] (SCRATCH_SIZE: its STATE persists between frames)
Fields our code adds inside game structs (pitcher +0x18C, batter +0x94 / +0xB6 / +0xBF, batter AI +0x31 / +0x3B /
+0x45, ai +0xD4) are the game snapshot's business when it copies those structs; not covered here.
"""
import struct
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
from ppc import Asm, branch  # noqa: E402

SAVE, SAVE_ORIG = 0x8016E39C, 0x9421FFE0                # stwu r1,-0x20(r1)
RESTORE, RESTORE_ORIG = 0x8017498C, 0x9421FFE0          # stwu r1,-0x20(r1)
RECORD = 0x80794C5C                                     # *R: the replay record
SNAP_A = 0x135600                                       # R+: the play's-start snapshot
SECTION = 0x1000
LAYOUT = {}


def regions(on):
    """[(address, size, name)] of this build's CPU state (on: the feature test charbuild uses)."""
    out = []
    if on("cpu-pitching"):
        import cpu_pitching as p
        out += [(p.LAYOUT["state"], 2 * p.SIZE, "pitch model"), (p.LAYOUT["consts"] + p.K_TARGET, 4, "curve target")]
    if on("cpu-batter-track"):
        import cpu_track as t
        out.append((t.MIND, 2 * t.BLOCK, "level 5 mind game"))
    if on("cpu-items"):
        import cpu_items as i
        out += [(i.DATA, i.RECS, "item aim"), (i.SHOTB, i.SHOTB_SIZE, "shot list")]
    if on("cpu-item-defense"):
        import defense_dbg as d
        out.append((d.ADDR, d.SIZE, "item defense"))
    if on("cpu-rundown"):
        import cpu_rundown as r
        out.append((r.LAYOUT["scratch"], r.SCRATCH_SIZE, "rundown"))
    for a, n, name in out:
        assert a and a % 4 == 0 and n % 4 == 0, f"{name}: 0x{a or 0:08X} +0x{n:X} isn't whole words"
    return out


def copier(a, table, to_buffer):
    """r6 = the buffer; copy each (address, size) of `table` (ends with 0) between it and the regions."""
    a.load_addr(7, table)
    a.label("region")
    a.lwz(8, 0, 7).cmpwi(8, 0).beq("done").lwz(9, 4, 7)
    a.label("word")
    if to_buffer:
        a.lwz(10, 0, 8).stw(10, 0, 6)
    else:
        a.lwz(10, 0, 6).stw(10, 0, 8)
    a.addi(8, 8, 4).addi(6, 6, 4).addi(9, 9, -4).cmpwi(9, 0).bgt("word")
    a.addi(7, 7, 8).b("region")
    a.label("done")


def stub(base, site, orig, table, buf_a, buf_b, to_buffer):
    a = Asm(base)
    a.load_addr(4, RECORD).lwz(4, 0, 4).cmpwi(4, 0).beq("back")
    a.lis(5, SNAP_A >> 16).ori(5, 5, SNAP_A & 0xFFFF).add(4, 4, 5).lwz(5, 0, 4)   # r5 = snapshot A
    a.load_addr(6, buf_a).cmpw(3, 5).beq("copy").load_addr(6, buf_b)
    a.label("copy")
    copier(a, table, to_buffer)
    a.label("back")
    a.word(orig)
    a.b(site + 4)
    return a


def apply(dol, region, regs):
    """Hook `dol`; the table, the two buffers and the stubs go in `region` (a Space of SECTION bytes)."""
    for site, orig in ((SAVE, SAVE_ORIG), (RESTORE, RESTORE_ORIG)):
        got = dol.u32(site)
        assert got == orig, f"0x{site:08X}: 0x{got:08X}, expected 0x{orig:08X}"
    total = sum(n for _, n, _ in regs)
    table = LAYOUT["table"] = region.put(b"".join(struct.pack(">II", a, n) for a, n, _ in regs) + bytes(8), align=4)
    buf_a = LAYOUT["a"] = region.put(bytes(total), align=32)
    buf_b = LAYOUT["b"] = region.put(bytes(total), align=32)
    for site, orig, to_buffer in ((SAVE, SAVE_ORIG, True), (RESTORE, RESTORE_ORIG, False)):
        at = region.here + (-region.here % 4)
        assert region.put(stub(at, site, orig, table, buf_a, buf_b, to_buffer).assemble(), align=4) == at
        dol.w32(site, branch(site, at))
    return [f"replay state: {len(regs)} CPU blocks (0x{total:x} B: " + ", ".join(n for _, _, n in regs)
            + ") saved with the replay's snapshots and put back with them"]
