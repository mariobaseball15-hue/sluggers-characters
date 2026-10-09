"""Star Bit item model: 4 instances in the item model set's spare slot 0x2A.

The item models come from the common package (archive group 0) = dt_na.dat dir 136 file 0, 1 or 2
(FUN_8012fc84: FUN_80398080(0x88, v, ...), v = 1 when FUN_8012e06c(*(r13-0x163C)) is 1 or 2, 2 when
settings(*(r13-0xB00))+4 == 1 and +0x5B == 0, else 0). A package is
    u32 n (0x30), u32 offset[n] (from the package start, 0 = empty slot), payload at 0xE0...
and slot i's payload is a raw model block (0x20-byte header: +4 GPL, +8 ACT, +0xC TEX). Its length is not
stored; the next non-zero offset (or the file end) bounds it. FUN_801303f8(archive, 0, i) returns the
payload pointer (FUN_80397db0: *(pkg + 0xC)[i]).

FUN_8045723c loads the items: file i of group 0 -> FUN_8037fd30(set, data, heap, instances, 0) ->
FUN_8037fd40(set, handle, slot i), set = *(*(r13-0x878)+4). Slots: 0x29 Shell, 0x2B Bob-omb, 0x2C POW,
0x2D Banana (5 instances), 0x2E/0x2F Boo, and 0x2A: a second copy of the Shell (all three packages carry
byte-identical Shell blocks in 0x29 and 0x2A) with 3 instances that nothing ever shows:
  - loaded at 0x80457510.. (li r6,3 at 0x80457528 = the instance count),
  - hidden at reset by FUN_80457e0c (instances 0..2, `cmpwi r30,3` at 0x80457F60),
  - freed by FUN_80457574,
and no other code in the item range (0x80440000..0x80470000) names 0x2A. The minigame code that fetches
slot 0x2A+i (FUN_80213038, FUN_80244f20, FUN_80247928, FUN_80248100) uses a different model set
(*(r13-0x1038), FUN_80223c48).

apply() makes slot 0x2A the Star Bit:
  1. dt_na.dat: the Star Bit block (models/work/starbit/prop.bin, scripts/build_prop.py with
     models/configs/starbit.json) is written over slot 0x2A's Shell in each of the three packages, in place
     (same offset; the rest of the old 0x25B40-byte Shell is zeroed). No TOC record or package offset
     changes, so the packages keep their lengths and every other slot's bytes.
  2. main.dol: 0x80457528 li r6,3 -> li r6,4 (four instances) and 0x80457F60 cmpwi r30,3 -> cmpwi r30,4
     (the reset hides all four).
No code or data section space is used.

Colors: the block is built from starbit_obj.py's white "tint" texture; starbits_item.py colors each instance
(per-instance material color, FUN_80381ef4 / 80381eec / 80381f04; see its header), so one model shows four
colors. For the item code: handle = FUN_8037fd48(set, 0x2A); per instance k (0..3)
FUN_80381e3c(set, handle, on (1) / off (0), k) shows / hides it (FUN_803828c4), and positioning is what
FUN_80455ac4 does for the Banana's five instances (slot 0x2D). The model's origin is its center (about
0.53 x 0.62 x 0.55), so an instance resting on the ground sits at y = +0.31.

  apply(dol, dat, block=BLOCK) -> (log, appended)
      dol: scripts/dol.Dol of the output main.dol (patched in place; its dt_na TOC gives the package
           offsets, so call it on a DOL whose dir 136 records still point at the stock packages).
      dat: path of the dt_na.dat those records address (read only; used to check each slot still holds
           the Shell and to take the old slot length).
      appended: [(dt_na.dat offset, bytes)], charbuild's `appended` format (in-place writes).

  python scripts/starbits_model.py        dry run against Extra Innings' main.dol / dt_na.dat
"""
import struct
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
import dtna_toc  # noqa: E402
import starbits_item  # noqa: E402

ROOT = Path(__file__).resolve().parents[1]
BLOCK = ROOT / "models/work/starbit/prop.bin"
PACKAGE_DIR, PACKAGES = 0x88, (0, 1, 2)
SLOT, SHELL_SLOT = 0x2A, 0x29
INSTANCES = starbits_item.BIT_TOTAL   # 40: 4 thrown + 36 for Luma's star swing (one source)
LOAD_COUNT, LOAD_COUNT_ORIG = 0x80457528, 0x38C00003      # li r6,0x3 (FUN_8045723c, slot 0x2A instances)
HIDE_LOOP, HIDE_LOOP_ORIG = 0x80457F60, 0x2C1E0003        # cmpwi r30,0x3 (FUN_80457e0c, reset hide loop)


def slot_span(pkg, i):
    """(start, end) of slot i's payload inside a package (end = next non-zero offset or package end)."""
    n = struct.unpack_from(">I", pkg, 0)[0]
    offs = struct.unpack_from(f">{n}I", pkg, 4)
    start = offs[i]
    assert start, f"slot {i:#x} is empty"
    later = [o for o in offs if o > start]
    return start, min(later) if later else len(pkg)


def apply(dol, dat, block=BLOCK, extra=()):
    """extra: [(offset in the slot, bytes)] more blocks stored in slot 0x2A's unused tail after the Star Bit
    (Wendy's ring, wendy_rings.RING_OFF; its own model-set slot loads it from there)."""
    blob = Path(block).read_bytes()
    assert len(blob) % 32 == 0
    for addr, orig, new in ((LOAD_COUNT, LOAD_COUNT_ORIG, LOAD_COUNT_ORIG & ~0xFFFF | INSTANCES),
                            (HIDE_LOOP, HIDE_LOOP_ORIG, HIDE_LOOP_ORIG & ~0xFFFF | INSTANCES)):
        assert dol.u32(addr) == orig, f"{addr:08X}: {dol.u32(addr):08X}, expected {orig:08X}"
        dol.w32(addr, new)
    files = dtna_toc.toc(dol)[PACKAGE_DIR]
    appended, log = [], []
    with open(dat, "rb") as f:
        for p in PACKAGES:
            off, length = files[p]
            f.seek(off)
            pkg = f.read(length)
            start, end = slot_span(pkg, SLOT)
            s0, s1 = slot_span(pkg, SHELL_SLOT)
            assert pkg[start:end] == pkg[s0:s1], f"package {p}: slot 0x2A no longer holds the Shell copy"
            assert len(blob) <= end - start, f"package {p}: Star Bit block 0x{len(blob):x} > slot 0x{end - start:x}"
            body = bytearray(blob + bytes(end - start - len(blob)))
            for at, more in extra:
                assert at % 32 == 0 and at >= len(blob) and at + len(more) <= end - start, f"extra block at 0x{at:x}"
                assert not any(body[at:at + len(more)]), f"extra block at 0x{at:x} overlaps another"
                body[at:at + len(more)] = more
            appended.append((off + start, bytes(body)))
            log.append(f"star bits: dt_na dir {PACKAGE_DIR} file {p} slot 0x2A (dt_na+0x{off + start:x}) = "
                       f"Star Bit block 0x{len(blob):x} B (was the Shell, 0x{end - start:x} B)"
                       + "".join(f", + 0x{len(m):x} B at +0x{at:x}" for at, m in extra))
    log.append(f"star bits: item model slot 0x2A loads {INSTANCES} instances (0x{LOAD_COUNT:08X}), "
               f"reset hides {INSTANCES} (0x{HIDE_LOOP:08X})")
    return log, appended


if __name__ == "__main__":
    from dol import Dol
    src = ROOT / "extracted/extra-innings"
    log, appended = apply(Dol(src / "sys/main.dol"), src / "files/dt_na.dat")
    print("\n".join(log))
    print(f"dry run: {len(appended)} in-place dt_na.dat writes, {sum(len(b) for _, b in appended)} bytes")
