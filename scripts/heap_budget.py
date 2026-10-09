"""MEM2 game-heap budget of a patched build, from its file sizes (no Dolphin).

The game heap (heap 3: the MEM expanded heap 0x900AE64C..0x930AE5FC) runs out in a match when too much of it is taken
by files the build enlarges and that stay resident (dir 119: the icon bank, captain / menu art, layouts, HUD icons; the
stadium's particle file). Three dumps pin it down (analysis/, 2026-09-26):
  hazards-1 (ramdump-crash-80597944): a rival VS at-bat takes two 640 x 448 x 2 screen captures; the second didn't
      fit and the stock code zeroed its null buffer.
  map-test-2 (ramdump-maptest2-80373504): 0 KB left right after a run scored; the run-scored display failed.
  heap-cal-1 (heap-cal-1/first-pitch, /run-scored; the release code at 668e2e3, Yoshi Park by day): the calibration.
What a match puts on top of the resident files:
  file 14 banks  each FIELDER's and the BATTER's model directory file 14, loaded during an at-bat (10 at the first
                 pitch; none between at-bats). A new character's directory is its template's, so its file 14 is its
                 template's size. With git-f3's share-anim-banks in the build (bank8_share), players whose file 14
                 is byte-identical share one loaded copy: each group counts once (its ids from the build's own table).
  an event       a run scored (and the VS moment) allocates about EVENT more (heap-cal-1: +86 KB used right after its
                 run although 1,120 KB of banks had just been freed). In map-test-2 it came while the banks were in.
  the VS capture two 640 x 448 x 2 screen captures.
The estimate: heap-cal-1's free space at its first pitch without the banks (CAL_FREE), plus what each resident file is
smaller in the build checked (or less what it is bigger); less the worst moment: a run scored (the worst ten banks the
roster can bring, + EVENT) or a VS at-bat (two captures + EVENT). It keeps MARGIN left. Against the three: heap-cal-1
with its own teams ~1.4 MB left; hazards-1 and map-test-2 below the margin, as they crashed (test_heap_budget).

  python scripts/heap_budget.py <patched game folder (sys/main.dol)> [--extra KB]

--extra: other heap use the file sizes don't show, in KB.
"""
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
ROOT = Path(__file__).resolve().parents[1]

CAPTURE = 640 * 448 * 2                 # 0x8C000: one VS capture
NEED = 2 * CAPTURE                      # the VS capture: two
MARGIN = 512 * 1024                     # fragmentation and what else a match allocates late
EVENT = 1206 * 1024                     # what a run scored allocates besides (heap-cal-1 run-scored)
BANKS = 10                              # file 14 banks at once: nine fielders and the batter
# heap-cal-1's heap 3 at its first pitch: 2,638 KB free with its ten banks in (1,307 KB), so 3,945 KB without them
CAL_FREE = (2638 + 1307) * 1024
# (dir, file): its size in heap-cal-1. Resident through a match (the dumps' blocks). (161, LARGEST): the stadium's
# particle file (trail colours are appended to every one; which one is resident depends on the stadium, git-f3).
LARGEST = "largest"
RESIDENT = {(119, 1): 1238044, (119, 2): 1924824, (119, 3): 667608, (119, 8): 1999912, (161, LARGEST): 288864}
NAMES = {(119, 1): "captain / menu art", (119, 2): "icon bank", (119, 3): "menu layouts", (119, 8): "HUD icons",
         (161, LARGEST): "particle file (trail colours)"}
MODEL_DIR_BASE, STOCK_IDS = 18, 101     # charbuild: stock character i's model directory is 18 + i
# bank8_share's hook site and the stock word there (`or r25,r4,r4`): kept here, so that a build without
# share-anim-banks never loads bank8_share (a lean download, the Characters Beta, doesn't have it)
SHARE_SITE, SHARE_WORD = 0x80376398, 0x7C992378


def sizes(game):
    """{(dir, file): length} of the resident files, and "banks": the file 14 size of each stock character's model
    directory, from the build's main.dol dt_na index."""
    import dtna_toc
    from dol import Dol
    toc = dtna_toc.toc(Dol(Path(game) / "sys/main.dol"))
    out = {k: max(n for _, n in toc[k[0]]) if k[1] == LARGEST else toc[k[0]][k[1]][1] for k in RESIDENT}
    out["banks"] = [toc[MODEL_DIR_BASE + i][14][1] for i in range(STOCK_IDS)]
    out["rep"] = shared(Dol(Path(game) / "sys/main.dol").read)
    return out


def shared(read):
    """The build's file 14 sharing table (bank8_share: id -> the lowest id with identical bytes), or None when the
    build doesn't share. read(addr, n): bytes of the patched main.dol's memory. The table's address and length are
    read back from the hook: `cmplwi r4,len` and the `lis` / `addi` pair of r12."""
    import struct
    u32 = lambda a: struct.unpack(">I", read(a, 4))[0]
    w = u32(SHARE_SITE)
    if w == SHARE_WORD:
        return None
    assert w >> 26 == 18 and not w & 3, f"0x{SHARE_SITE:08X}: 0x{w:08X}, not a branch"
    stub = (SHARE_SITE + ((w & 0x03FFFFFC) ^ 0x02000000) - 0x02000000) & 0xFFFFFFFF
    n = hi = lo = None
    for k in range(8):
        i = u32(stub + 4 * k)
        op, rd, ra, imm = i >> 26, (i >> 21) & 31, (i >> 16) & 31, i & 0xFFFF
        if op == 10 and ra == 4:                    # cmplwi r4,len
            n = imm
        elif op == 15 and rd == 12 and ra == 0:     # lis r12,hi
            hi = imm
        elif op == 14 and rd == 12 and ra == 12:    # addi r12,r12,lo
            lo = imm - 0x10000 if imm & 0x8000 else imm
    assert None not in (n, hi, lo), f"bank8_share's hook at 0x{stub:08X} isn't the expected one"
    return list(struct.unpack(f">{n}H", read(((hi << 16) + lo) & 0xFFFFFFFF, 2 * n)))


def roster(stock_banks, root=ROOT, rep=None):
    """The file 14 size of every character a build can field: each stock character, and each of our characters and
    recolors at its template's (characters/*.json "template", recolors/*.json "base"). rep (the build shares, shared()):
    one size per group of identical copies instead, each id in its group rep[id] (an id past the table: its own)."""
    from sluggers_data import CHAR_NAMES
    index = {n: i for i, n in enumerate(CHAR_NAMES)}

    def of(t):
        try:
            return int(str(t), 0)
        except ValueError:
            return index.get(t)
    out = list(stock_banks)
    ids = list(range(len(stock_banks)))
    for folder, key in (("characters", "template"), ("recolors", "base")):
        for p in sorted((Path(root) / folder).glob("*.json")):
            try:
                d = json.loads(p.read_text(encoding="utf-8"))
                t, cid = of(d.get(key)), of(d.get("id"))
            except (ValueError, OSError, TypeError):
                continue
            if t is not None and 0 <= t < STOCK_IDS:
                out.append(stock_banks[t])
                ids.append(cid)
    if rep is None:
        return out
    group = {}
    for i, size in zip(ids, out):
        g = rep[i] if i is not None and 0 <= i < len(rep) else ("own", i)
        group[g] = max(group.get(g, 0), size)
    return list(group.values())


def worst_banks(banks):
    """The most the fielders and the batter can load at once: the BANKS largest (each character plays once)."""
    return sum(sorted(banks, reverse=True)[:BANKS])


def estimate(sz, extra=0, banks=None):
    """(estimated free bytes left at the worst moment, the margin it must keep, {file: bytes over / under heap-cal-1},
    the at-bat free bytes without banks, {moment: bytes}). banks: the file 14 sizes of the characters the build fields
    (None: every character, roster())."""
    delta = {k: sz[k] - RESIDENT[k] for k in RESIDENT}
    at_bat = CAL_FREE - sum(delta.values()) - extra
    bank = worst_banks(roster(sz["banks"], rep=sz.get("rep")) if banks is None else banks)
    pk = {"a run scored": bank + EVENT, "a VS at-bat": NEED + EVENT}
    return at_bat - max(pk.values()), MARGIN, delta, at_bat, pk


def report(game, extra=0, banks=None):
    """Plain-words lines and whether the build is within budget."""
    sz = sizes(game)
    free, need, delta, at_bat, pk = estimate(sz, extra, banks)
    ok = free >= need
    worst = max(pk, key=pk.get)
    lines = [f"heap budget: about {at_bat // 1024} KB free at an at-bat before the players' banks; the worst moment is "
             f"{worst} ({pk[worst] // 1024} KB), leaving {free // 1024} KB, {need // 1024} KB margin needed: "
             f"{'ok' if ok else 'TOO LITTLE'}",
             f"    a run scored: the fielders' and batter's file 14 banks (the worst {BANKS} of the roster"
             f"{', identical copies shared' if sz.get('rep') else ''}) + "
             f"{EVENT // 1024} KB; a VS at-bat: 2 screen captures of {CAPTURE // 1024} KB + {EVENT // 1024} KB"]
    for k, d in sorted(delta.items(), key=lambda kv: -kv[1]):
        lines.append(f"    {NAMES[k]} (dir {k[0]}, {'the largest file' if k[1] == LARGEST else f'file {k[1]}'}): "
                     f"{(RESIDENT[k] + d) // 1024} KB ({'+' if d >= 0 else ''}{d // 1024} KB vs heap-cal-1)")
    return lines, ok


WARNING = ("Your game has so many new characters and recolors that it may crash during a match. "
           "Untick some and patch again.")


def check(game, extra=0, banks=None):
    """(estimated free KB left at the worst moment of a match, ok (at least MARGIN), the sentence for the player:
    "" when ok, else WARNING). For patch.py ("== Checking memory") and package.py --check (git-dc)."""
    free, need = estimate(sizes(game), extra, banks)[:2]
    return free // 1024, free >= need, "" if free >= need else WARNING


if __name__ == "__main__":
    args = sys.argv[1:]
    extra = int(args[args.index("--extra") + 1]) * 1024 if "--extra" in args else 0
    assert args and not args[0].startswith("-"), __doc__
    lines, ok = report(args[0], extra)
    print("\n".join(lines))
    sys.exit(0 if ok else 1)
