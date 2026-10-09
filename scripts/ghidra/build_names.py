"""Build a name list for the Ghidra project from what the DOL itself says.

Sources:
  - RTTI: every polymorphic class's name, bases, typeinfo and vtables.
  - Vtable slots: each virtual function goes to the class that introduces it (no base class has it).
    Slot names we know (e.g. ITask slot 0 = Update) are inherited by every override.
  - Destructors: vtable slots whose code is CodeWarrior's destructor shape.
  - Constructors: non-virtual functions that store exactly one class's vtable into their own `this`.
  - scripts/ghidra/dol_symbols.txt: every function's address and size, and every non-auto name (SDK/runtime
    names, names from the decomp), taken from decomp/config/RMBE01/symbols.txt (--make-seed remakes it).

Writes a TSV for ApplyNames.java (kind, address, namespace path (::-joined, may be empty), name; kind is fn,
method (a function taking `this`), label (data) or size (a class's size)), and/or a Dolphin symbol map.
The patcher's "Modder files..." writes both from the player's own game (scripts/modder_files.py).

  python scripts/ghidra/build_names.py <main.dol> [--tsv names.tsv] [--map RMBE01.map] [--symbols <symbols.txt>]
  python scripts/ghidra/build_names.py --make-seed decomp/config/RMBE01/symbols.txt
"""
import argparse, re, struct, sys
from pathlib import Path

SEED = Path(__file__).resolve().parent / "dol_symbols.txt"
from collections import defaultdict

# Slot names we know from the decomp. Key: (class, vtable byte offset of the slot, counting from the vtable start).
KNOWN_SLOTS = {
    ("NpLib::Task::ITask", 0x08): "Update",
    ("NpLib::Graphics::IColor", 0x28): "GetRgba4f",
    ("boost::detail::sp_counted_base", 0x0C): "dispose",
    ("boost::detail::sp_counted_base", 0x10): "destroy",
    ("boost::detail::sp_counted_base", 0x14): "get_deleter",
    ("Select::CExhiMemOrdTask", 0x10): "InitMembers",
    ("Select::CExhiMemOrdTask", 0x14): "ApplyToGame",
    ("Select::CExhiMemOrdTask", 0x18): "GetMode",
    ("Select::CExhiMemOrdTask", 0x1C): "OnOrderDone",
    ("Select::CExhiMemOrdTask", 0x20): "OnNotify",
}


class Dol:
    def __init__(self, path):
        d = open(path, "rb").read()
        offs = struct.unpack(">18I", d[0:0x48])
        addrs = struct.unpack(">18I", d[0x48:0x90])
        sizes = struct.unpack(">18I", d[0x90:0xD8])
        self.secs = [(a, d[o:o + s], i < 7) for i, (o, a, s) in enumerate(zip(offs, addrs, sizes)) if s]

    def find(self, x):
        for a, b, t in self.secs:
            if a <= x < a + len(b):
                return a, b, t

    def word(self, x):
        f = self.find(x)
        if f and x + 4 <= f[0] + len(f[1]):
            return struct.unpack_from(">I", f[1], x - f[0])[0]

    def istext(self, x):
        f = self.find(x)
        return bool(f and f[2])

    def cstr(self, x):
        f = self.find(x)
        if f:
            e = f[1].find(b"\x00", x - f[0])
            return f[1][x - f[0]:e] if e > 0 else None


def split_path(name):
    """Split A::B<C::D>::E at top-level ::, drop spaces (Ghidra names can't hold them)."""
    parts, depth, cur, i = [], 0, "", 0
    while i < len(name):
        c = name[i]
        if c == "<":
            depth += 1
        elif c == ">":
            depth -= 1
        if depth == 0 and name.startswith("::", i):
            parts.append(cur)
            cur = ""
            i += 2
            continue
        cur += c
        i += 1
    parts.append(cur)
    return [p.replace(" ", "") for p in parts]


def rtti(dol):
    words = defaultdict(list)
    for a, b, t in dol.secs:
        if not t:
            for i in range(0, len(b) - 3, 4):
                words[struct.unpack_from(">I", b, i)[0]].append(a + i)
    ident = re.compile(rb"[A-Za-z_][A-Za-z0-9_:<>, *&]{2,}$")
    classes = {}  # name -> {"ti", "bases": [(ti, off)], "vtables": [(addr, [fns])]}
    for a, b, t in dol.secs:
        if t:
            continue
        for i in range(0, len(b) - 7, 4):
            sp = struct.unpack_from(">I", b, i)[0]
            if not 0x80000000 <= sp < 0x81800000:
                continue
            s = dol.cstr(sp)
            if not s or not ident.match(s):
                continue
            ti = a + i
            vts = []
            for vt in words.get(ti, []):
                fns, p = [], vt + 8
                while True:
                    w = dol.word(p)
                    if w is None or not (dol.istext(w) or w == 0):
                        break
                    if w == 0 and not fns:
                        break
                    fns.append(w)
                    p += 4
                while fns and fns[-1] == 0:
                    fns.pop()
                if fns:
                    vts.append((vt, fns))
            if not vts:
                continue
            bases, bl = [], dol.word(ti + 4)
            if bl and 0x80000000 <= bl < 0x81800000:
                j = 0
                while True:
                    bt = dol.word(bl + j)
                    if not bt or not 0x80000000 <= bt < 0x81800000:
                        break
                    bases.append((bt, dol.word(bl + j + 4) or 0))
                    j += 8
            c = classes.setdefault(s.decode(), {"ti": ti, "bases": bases, "vtables": []})
            c["vtables"] += vts
    return classes


DELETE = 0x80521380  # operator delete(void*)


def is_dtor(dol, f, dtk_dtors):
    """CodeWarrior destructor: tests `this` up front and ends in operator delete (guarded by the delete flag)."""
    if f in dtk_dtors:
        return True
    head = [dol.word(f + 4 * i) for i in range(8)]
    if 0x2C030000 not in head:  # cmpwi r3, 0
        return False
    for i in range(400):
        w = dol.word(f + 4 * i)
        if w is None or w == 0x4E800020:  # blr
            return False
        if w >> 26 == 18 and w & 3 == 1:  # bl
            d = w & 0x03FFFFFC
            if d & 0x02000000:
                d -= 0x04000000
            if (f + 4 * i + d) & 0xFFFFFFFF == DELETE:
                return True
    return False


def build(dol_path, syms_path=SEED):
    """The rows: (kind, address, namespace path, name)."""
    dol = Dol(dol_path)
    classes = rtti(dol)
    ti2name = {c["ti"]: n for n, c in classes.items()}

    def ancestors(n, seen=None):
        seen = set() if seen is None else seen
        for bt, _ in classes.get(n, {}).get("bases", []):
            bn = ti2name.get(bt)
            if bn and bn not in seen:
                seen.add(bn)
                ancestors(bn, seen)
        return seen

    # function -> classes whose primary vtable holds it at a given slot offset
    holders = defaultdict(set)
    for n, c in classes.items():
        for vt, fns in c["vtables"][:1]:
            for i, f in enumerate(fns):
                if f:
                    holders[f].add((n, 8 + 4 * i))
    # propagate known slot names down the hierarchy
    slotname = dict(KNOWN_SLOTS)
    changed = True
    while changed:
        changed = False
        for n in classes:
            for anc in ancestors(n):
                for (cn, off), nm in list(slotname.items()):
                    if cn == anc and (n, off) not in slotname:
                        slotname[(n, off)] = nm
                        changed = True

    dtk_dtors = set()
    for line in open(syms_path, encoding="utf-8"):
        m = re.match(r"dtor_([0-9A-F]{8}) = ", line)
        if m:
            dtk_dtors.add(int(m[1], 16))
    rows = []
    named_fn = set()
    for f, hs in holders.items():
        names = {n for n, _ in hs}
        owners = [n for n in names if not (ancestors(n) & names)]
        if len(owners) != 1:
            continue  # shared by unrelated classes (folded code, pure-virtual stub): leave it
        owner = owners[0]
        off = min(o for n, o in hs if n == owner)
        if is_dtor(dol, f, dtk_dtors):
            name = "~" + split_path(owner)[-1]
        else:
            name = slotname.get((owner, off), "vf%02X" % off)
        rows.append(("method", f, owner, name))
        named_fn.add(f)

    # vtable and typeinfo labels
    vt2class = {}
    for n, c in classes.items():
        rows.append(("label", c["ti"], n, "__RTTI"))
        for k, (vt, fns) in enumerate(c["vtables"]):
            rows.append(("label", vt, n, "__vtable" if k == 0 else "__vtable%d" % k))
            vt2class[vt] = n

    # constructors: lis/addi of one class vtable, stored through r3 (or a copy of r3), not through r1
    text = [(a, b) for a, b, t in dol.secs if t]
    ctor_hits = defaultdict(set)
    for a, b in text:
        for i in range(0, len(b) - 12, 4):
            w1 = struct.unpack_from(">I", b, i)[0]
            if w1 >> 26 != 15:  # lis
                continue
            rt = (w1 >> 21) & 31
            hi = (w1 & 0xFFFF) << 16
            for j in range(i + 4, min(i + 40, len(b) - 4), 4):
                w2 = struct.unpack_from(">I", b, j)[0]
                if w2 >> 26 == 14 and (w2 >> 16) & 31 == rt:  # addi rX, rt, lo
                    lo = w2 & 0xFFFF
                    addr = (hi + (lo - 0x10000 if lo & 0x8000 else lo)) & 0xFFFFFFFF
                    if addr in vt2class:
                        rx = (w2 >> 21) & 31
                        for k in range(j + 4, min(j + 40, len(b) - 4), 4):
                            w3 = struct.unpack_from(">I", b, k)[0]
                            if w3 >> 26 == 36 and (w3 >> 21) & 31 == rx:  # stw rx, d(ra)
                                ra = (w3 >> 16) & 31
                                if ra != 1:
                                    ctor_hits[a + i].add(vt2class[addr])
                                break
                    break
    # map each hit to its function: nearest preceding function start from symbols.txt / vtables
    fstarts = set(holders)
    sym_rows = []
    for line in open(syms_path, encoding="utf-8"):
        m = re.match(r"(\S+) = (\S+):0x([0-9A-F]+); // type:(\w+)", line)
        if not m:
            continue
        nm, sec, addr, typ = m[1], m[2], int(m[3], 16), m[4]
        if typ == "function":
            fstarts.add(addr)
        if re.match(r"^(fn|lbl|dtor|jumptable|gap|switch)_[0-9A-F]{8}$|^@|^\$", nm):
            continue
        sym_rows.append((nm, sec, addr, typ))
    fstarts = sorted(fstarts)
    import bisect
    per_fn = defaultdict(set)
    for hit, cls in ctor_hits.items():
        k = bisect.bisect_right(fstarts, hit) - 1
        if k >= 0:
            per_fn[fstarts[k]] |= cls
    for f, cls in per_fn.items():
        if f in named_fn or len(cls) == 0:
            continue
        # a ctor may store its bases' vtables too; the most-derived one is the class
        derived = [c for c in cls if not any(c in ancestors(o) for o in cls if o != c)]
        if len(derived) == 1 and len(cls) <= 1 + len(ancestors(derived[0])):
            rows.append(("method", f, derived[0], split_path(derived[0])[-1]))
            named_fn.add(f)

    # names from symbols.txt
    for nm, sec, addr, typ in sym_rows:
        path, name = demangle(nm)
        if typ == "function":
            if addr in named_fn and not path:
                continue
            kind = "method" if path and not name.startswith("__sinit") and path_is_class(path, classes, nm) else "fn"
            rows = [r for r in rows if not (r[1] == addr and r[0] != "label")]
            rows.append((kind, addr, path, name))
        else:
            rows.append(("label", addr, path, name))

    # class sizes from allocation sites: li r3, SIZE ... bl operator new ... bl <ctor of C>
    ctor_of = {r[1]: r[2] for r in rows if r[0] == "method" and r[3] == split_path(r[2])[-1]}
    news = {0x80521224}
    for nm, sec, addr, typ in sym_rows:
        if nm.startswith("__nw__"):
            news.add(addr)
    sizes = defaultdict(set)
    for a, b in text:
        n = len(b) // 4
        ws = struct.unpack_from(">%dI" % n, b)

        def bl_target(i):
            w = ws[i]
            if w >> 26 == 18 and w & 3 == 1:
                d = w & 0x03FFFFFC
                if d & 0x02000000:
                    d -= 0x04000000
                return (a + 4 * i + d) & 0xFFFFFFFF

        for i in range(n):
            if ws[i] >> 16 != 0x3860:  # li r3, imm
                continue
            size = ws[i] & 0xFFFF
            for j in range(i + 1, min(i + 6, n)):
                if bl_target(j) is not None and bl_target(j) not in news:
                    break
                if bl_target(j) in news:
                    for k in range(j + 1, min(j + 24, n)):
                        t = bl_target(k)
                        if t in ctor_of:
                            sizes[ctor_of[t]].add(size)
                            break
                        if t is not None:
                            break
                    break
    for cls, ss in sizes.items():
        if len(ss) == 1:
            rows.append(("size", 0, cls, str(ss.pop())))

    return rows


def write_tsv(rows, path):
    with open(path, "w", encoding="utf-8", newline="\n") as w:
        for kind, a, p, name in rows:
            w.write(f"{kind}\t{a:08X}\t{'::'.join(split_path(p)) if p else ''}\t{name}\n")


def full_name(path, name):
    return "::".join(split_path(path) + [name]) if path else name


def function_sizes(syms_path=SEED):
    sizes = {}
    for line in open(syms_path, encoding="utf-8"):
        m = re.match(r"\S+ = \.\w+:0x([0-9A-F]+); // type:function size:0x([0-9A-F]+)", line)
        if m:
            sizes[int(m[1], 16)] = int(m[2], 16)
    return sizes


def write_map(rows, path, syms_path=SEED):
    """A Dolphin symbol map, in Dolphin's own format (address, size, virtual address, alignment, name). A function
    the seed has no size for gets the distance to the next known function."""
    import bisect
    sizes = function_sizes(syms_path)
    funcs = {a: full_name(p, n) for k, a, p, n in rows if k in ("fn", "method")}
    starts = sorted(set(sizes) | set(funcs))
    lines = [".text section layout"]
    for a in sorted(funcs):
        size = sizes.get(a)
        if not size:
            k = bisect.bisect_right(starts, a)
            size = starts[k] - a if k < len(starts) else 4
        lines.append(f"{a:08x} {size:08x} {a:08x} 0 {funcs[a]}")
    labels = sorted((a, full_name(p, n)) for k, a, p, n in rows if k == "label")
    lines += ["", ".data section layout"]
    lines += [f"{a:08x} 00000004 {a:08x} 0 {n}" for a, n in labels]
    Path(path).write_text("\n".join(lines) + "\n", encoding="utf-8")
    return len(funcs), len(labels)


def make_seed(symbols_txt, out=SEED):
    """Every function (address, size, name) and every non-auto name from the decomp's symbols.txt."""
    keep = []
    for line in open(symbols_txt, encoding="utf-8"):
        m = re.match(r"(\S+) = (\S+):0x([0-9A-F]+); // type:(\w+)(?: size:0x([0-9A-F]+))?", line)
        if not m:
            continue
        nm, sec, addr, typ, size = m.groups()
        auto = re.match(r"^(fn|lbl|jumptable|gap|switch)_[0-9A-F]{8}$|^@|^\$", nm)
        if typ == "function" or not auto:
            keep.append(f"{nm} = {sec}:0x{addr}; // type:{typ}" + (f" size:0x{size}" if size else ""))
    Path(out).write_text("\n".join(keep) + "\n", encoding="utf-8")
    return len(keep)


def main():
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("dol", nargs="?")
    ap.add_argument("--symbols", default=str(SEED))
    ap.add_argument("--tsv")
    ap.add_argument("--map")
    ap.add_argument("--make-seed", metavar="SYMBOLS_TXT")
    args = ap.parse_args()
    if args.make_seed:
        print(f"{make_seed(args.make_seed)} symbols -> {SEED}")
        return
    if not args.dol or not (args.tsv or args.map):
        ap.error("give main.dol and --tsv and/or --map")
    rows = build(args.dol, args.symbols)
    kinds = defaultdict(int)
    for r in rows:
        kinds[r[0]] += 1
    print(dict(kinds))
    if args.tsv:
        write_tsv(rows, args.tsv)
    if args.map:
        print("map: %d functions, %d labels" % write_map(rows, args.map, args.symbols))


def path_is_class(path, classes, mangled):
    """A qualified name is a method when its last qualifier is a known class or looks like one (CFoo, IFoo)."""
    return path in classes or re.match(r"^[CIT][A-Z]", split_path(path)[-1]) is not None


def demangle(nm):
    """CodeWarrior mangling, names only: Update__Q26Select13CExhiMainTaskFv -> (Select::CExhiMainTask, Update)."""
    m = re.match(r"^(.+?)__(Q\d|\d)(.*)$", nm)
    if not m or nm.startswith("__sinit"):
        return "", nm
    base, rest = m[1], m[2] + m[3]
    parts = []
    if rest[0] == "Q":
        n, rest = int(rest[1]), rest[2:]
    else:
        n = 1
    for _ in range(n):
        mm = re.match(r"^(\d+)", rest)
        if not mm:
            return "", nm
        ln = int(mm[1])
        rest = rest[len(mm[1]):]
        parts.append(rest[:ln])
        rest = rest[ln:]
    if not rest.startswith("F") and rest != "":
        return "", nm
    if base == "__ct":
        base = parts[-1]
    elif base == "__dt":
        base = "~" + parts[-1]
    return "::".join(parts), base


if __name__ == "__main__":
    main()
