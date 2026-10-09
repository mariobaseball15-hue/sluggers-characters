"""Map Dolphin IOS_DI read offsets to dt_na.dat table-of-contents entries.

Reads the dt_na.dat index from main.dol (172 directories of file records), infers where dt_na.dat starts on Dolphin's virtual disc by
matching logged reads to entry offsets, then lists which entries each read touched.
  python scripts/dtna_reads.py <dolphin.log> [--since MM:SS] [--dol extracted/extra-innings/sys/main.dol]
"""
import argparse, collections, re, struct
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def dol_reader(path):
    d = Path(path).read_bytes()
    offs = struct.unpack(">18I", d[0:0x48]); addrs = struct.unpack(">18I", d[0x48:0x90])
    sizes = struct.unpack(">18I", d[0x90:0xD8])
    def rd(a, n):
        for o, s, z in zip(offs, addrs, sizes):
            if z and s <= a < s + z:
                return d[o + a - s:o + a - s + n]
    return rd


def toc(dol):
    """dt_na.dat index in main.dol (format from LlamaTrauma/MSS-dat-tools): a pointer array at
    file offset 0x69C828..0x69CAD8 (172 directories); each directory is a run of 48-byte records
    {name_ptr=0x8067F658, len_en, off_en, ?, ?, len_sp, off_sp, ?, ?, len_fr, off_fr, ?}."""
    d = Path(dol).read_bytes()
    word = lambda o: struct.unpack(">I", d[o:o + 4])[0]
    ptrs = [word(o) - 0x80003F00 for o in range(0x69C828, 0x69CAD8, 4)]
    entries = []
    for di, fp in enumerate(ptrs):
        others = set(ptrs[:di] + ptrs[di + 1:])
        fi = 0
        while fp not in others and fp + 48 <= len(d):
            w = struct.unpack(">12I", d[fp:fp + 48])
            if w[0] != 0x8067F658:
                break
            entries.append((di, fi, w[2], w[1]))
            fp += 48; fi += 1
    return entries


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("log"); ap.add_argument("--since"); ap.add_argument("--dol", default=str(ROOT / "extracted/extra-innings/sys/main.dol"))
    a = ap.parse_args()
    reads = []
    for line in open(a.log, encoding="utf8", errors="ignore"):
        m = re.match(r"(\d+:\d+):\d+ .*DVDLowRead: offset \w+ \(byte 0x([0-9a-f]+)\), length 0x([0-9a-f]+)", line)
        if m:
            reads.append((m.group(1), int(m.group(2), 16), int(m.group(3), 16)))
    ents = toc(a.dol)
    starts = {off for _, _, off, _ in ents}
    diff = collections.Counter(b - f for _, b, _ in reads for f in starts if b >= f)
    base, votes = diff.most_common(1)[0]
    print(f"dt_na.dat starts at virtual disc byte 0x{base:x} ({votes} reads line up with entry starts)")
    for t, b, n in reads:
        if a.since and t < a.since:
            continue
        rel = b - base
        hit = [(g, e, off, size) for g, e, off, size in ents if off <= rel < off + size]
        tag = ", ".join(f"dir{g}/file{e}(0x{off:x}+0x{size:x})" for g, e, off, size in hit[:3]) or "-"
        print(f"{t}  dat+0x{rel:09x} len 0x{n:06x}  {tag}")


if __name__ == "__main__":
    main()
