"""Pair every `lis` with the instructions that use it as an address base, from analysis/listing.tsv.

The build reads the pairs from scripts/hilo_pairs.tsv (addresses only), not the listing, so a build needs neither
Ghidra's listing nor anything else made from the game's code (the patcher ships the table). The listing is a fixed
disassembly of the clean game, so the table never changes; `python scripts/hilo_refs.py --table` remakes it.

Linear scan per function: `lis rX,hi` sets rX; any later instruction with a signed 16-bit
displacement off rX (addi/addic/ori or a d(rX) load/store) is a use with effective address
(hi<<16)+lo; a different write to rX ends the pairing. Used to decide which table references can be
relocated by rewriting a lis/lo pair and which share a lis with other data.
"""
import re, collections
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
DISP = re.compile(r"^(\w+\.?) (r\d+|f\d+),(-?0x[0-9a-f]+|\d+)\((r\d+)\)$")
IMM = re.compile(r"^(addi|addic|subi|ori) (r\d+),(r\d+),(-?0x[0-9a-f]+|\d+)$")
LIS = re.compile(r"^lis (r\d+),(-?0x[0-9a-f]+|\d+)$")
WRITE = re.compile(r"^\w+\.? (r\d+),")
ADD = re.compile(r"^add\.? (r\d+),(r\d+),(r\d+)$")


def load():
    funcs = collections.OrderedDict()
    for line in open(ROOT / "analysis/listing.tsv", encoding="utf8"):
        a, fe, fn, ins = line.rstrip("\n").split("\t")
        funcs.setdefault(fe, []).append((int(a, 16), ins))
    return funcs


TABLE = ROOT / "scripts/hilo_pairs.tsv"


def pairs():
    """Yield (lis_addr, use_addr, reg, ea, kind, ins) from TABLE (ins is "": nothing uses it)."""
    for line in open(TABLE, encoding="utf8"):
        la, use, reg, ea, kind = line.split()
        yield int(la, 16), int(use, 16), reg, int(ea, 16), kind, ""


def listing_pairs():
    """pairs() worked out from analysis/listing.tsv (for --table)."""
    for fe, body in load().items():
        live = {}  # reg -> (lis_addr, hi)
        for addr, ins in body:
            m = LIS.match(ins)
            if m:
                live[m.group(1)] = (addr, int(m.group(2), 16) & 0xFFFF)
                continue
            m = IMM.match(ins)
            if m and m.group(3) in live:
                la, hi = live[m.group(3)]
                lo = int(m.group(4), 16)
                if m.group(1) == "subi":
                    lo = -lo
                if m.group(1) == "ori":
                    ea = (hi << 16) | (lo & 0xFFFF)
                else:
                    ea = ((hi << 16) + lo) & 0xFFFFFFFF
                yield la, addr, m.group(3), ea, m.group(1), ins
                live.pop(m.group(2), None)  # rD now holds a full address (or something else)
                continue
            m = IMM.match(ins) or None
            if m:
                live.pop(m.group(2), None)
                continue
            m = DISP.match(ins)
            if m and not m.group(1).startswith("st") and m.group(4) not in live:
                live.pop(m.group(2), None)
                continue
            if m and m.group(4) in live:
                la, hi = live[m.group(4)]
                ea = ((hi << 16) + int(m.group(3), 16)) & 0xFFFFFFFF
                yield la, addr, m.group(4), ea, "disp", ins
                if m.group(1).rstrip(".").endswith("u"):
                    live.pop(m.group(4), None)  # update form: the base now holds the full address
                if not m.group(1).startswith("st") and m.group(2).startswith("r"):
                    live.pop(m.group(2), None)  # a load overwrites its target register
                continue
            m = ADD.match(ins)
            if m and (m.group(2) in live) != (m.group(3) in live):
                # base + index keeps the high half: later d(rD) uses still address the table
                live[m.group(1)] = live[m.group(2) if m.group(2) in live else m.group(3)]
                continue
            m = WRITE.match(ins)
            if m and not ins.startswith(("st", "cmp")):
                live.pop(m.group(1), None)


if __name__ == "__main__":
    import sys
    if "--table" in sys.argv:
        rows = [f"{la:08X} {use:08X} {reg} {ea:08X} {kind}" for la, use, reg, ea, kind, _ in listing_pairs()]
        TABLE.write_text("\n".join(rows) + "\n", encoding="utf8")
        print(f"{TABLE}: {len(rows)} pairs")
