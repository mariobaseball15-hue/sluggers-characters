"""Fix a player's Gecko codes for a patched game (a player: "some gecko codes still work, others don't: all captains and
repeat characters work; the old unused characters code doesn't, neither does CPU vs CPU").

Why codes break: to add new character ids the build copies every per-character table (charbuild.TABLES: stats, the
color-wheel selector, hasmodel, ...; the grid heads, the dt_na directories, the captains' tables) into its own data
section, grows it and repoints the game's code (charbuild.relocate): a code writing the old address writes a copy the
game no longer reads. The build's code and data also sit where the stock game's heaps started, so the heaps (and
everything the game makes at run time: the controllers' state, the match settings) start higher: a code reading
0x81317BB0 for the buttons reads nothing there. And a code hooking (C2) or writing an instruction the build already
replaced fights with the patcher.

Every build writes relocations.json into the "<iso stem> (patch details)" folder beside the ISO (charbuild.gecko_map,
patch.run; older builds: <iso>.relocations.json beside it): the moved tables (old start, length -> new start, row size), the stock words it changed and which feature changed them, its features, and how far
the heaps moved (heap_shift). fix() reads the codes (a Dolphin GameSettings RMBE01.ini's [Gecko], or pasted code text)
and, per code:
  - points addresses inside a moved table at the same offset in the new one (the same row: the new tables keep the
    stock rows where they were): 00/02/04/06/08 writes, 20-2E ifs, 42/4A base / pointer sets and 40/48 pointer loads,
    82/84 register loads / stores, and C0/C2 asm's lis + addi / ori / load-store pairs;
  - moves run-time memory addresses (MEM1 past the stock arena) by heap_shift, the same way (a best guess past the
    first objects: see gecko_map);
  - flags a code that hooks or writes a word the build changed ("conflicts with the patcher's <feature>"): turned off;
  - flags codes for what the patcher has built in (CPU vs CPU): turned off when the build has it.
It never adds or removes lines (a code's goto / skip counts stay right). What it can't read it leaves as it is and says
so: a code with blanks to fill in (XX), an unknown code type, a base loaded from memory (the address is only known when
the game runs: pointer codes follow the game's own pointers, so they need nothing), an asm lis shared by addresses that
moved differently.

  python scripts/gecko_fix.py RMBE01.ini "my-game (patch details)/relocations.json" [--out fixed.ini]
The patcher's "Fix my Gecko codes..." window (patcher/gecko_window.py) does the same with a Save.
"""
import json
import os
import re
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
HEX = re.compile(r"^\s*([0-9A-Fa-f]{8})\s+([0-9A-Fa-f]{8})\s*$")
BLANK = re.compile(r"^\s*([0-9A-Za-z]{8})\s+([0-9A-Za-z]{8})\s*$")   # a code line with letters to fill in (XX)
# the heaps run from arena low up to arena high, which the build doesn't move (0x817FF460 in RAM dumps of patched games,
# analysis/ramdump-cpuvcpu: OS globals 0x80000034 / 0x80003110): an address the shift would take past it stays (codes
# use the free top of memory for their own asm: TNTkryzt's 0x817FED64)
ARENA_HI = 0x817FF460
DEFAULT_BASE = 0x80000000
# codes for what the patcher has built in: (feature, how the report names it, a test on the code). CPU vs CPU: C²'s
# "CPU vs CPU V2" hooks 0x80063D4C; LittleCoaks' writes the match settings' pad bytes (stock 0x811F76B0); any code
# named so.
BUILT_IN = [("cpu-vs-cpu", "CPU vs CPU",
             lambda code: bool(re.search(r"cpu\s*(vs\.?|v)\s*cpu|cpu player 1", code.name, re.I))
             or any(w0 & 0xFE000000 == 0xC2000000 and w0 & 0x01FFFFFF == 0x00063D4C for w0, _ in code.lines)
             or any(w0 & 0xEE000000 == 0x04000000 and w0 & 0x01FFFFFF == 0x011F76B0 for w0, _ in code.lines))]


def feature_titles():
    """{feature id: its title}, as the patcher window names them (patcher/features_text.json)."""
    try:
        return {k: v["title"] for k, v in json.loads((HERE / "patcher/features_text.json").read_text(
            encoding="utf8"))["features"].items()}
    except (OSError, ValueError, KeyError):
        return {}


def ha(a):
    return ((a >> 16) + ((a >> 15) & 1)) & 0xFFFF


def lo(a):
    return a & 0xFFFF


def sext(v):
    return v - 0x10000 if v & 0x8000 else v


# --- the build's map

class Map:
    """A build's relocations.json (charbuild.gecko_map)."""

    def __init__(self, data):
        self.data = data
        self.tables = [(t["old"], t["old"] + t["length"], t["new"], t.get("name") or f"0x{t['old']:08X}",
                        t.get("row"), t.get("header") if t.get("per_character") else None)
                       for t in data.get("tables", [])]
        self.changed = [(c["start"], c["end"], c) for c in data.get("changed", [])]
        self.features = set(data.get("features", []))
        self.heap_start = data.get("heap_start", 0x807B4E80)
        self.heap_shift = data.get("heap_shift", 0)

    @classmethod
    def load(cls, path):
        return cls(json.loads(Path(path).read_text(encoding="utf8")))

    def table(self, addr):
        return next((t for t in self.tables if t[0] <= addr < t[1]), None)

    def move(self, addr, n=1):
        """(new address, why) for [addr, addr+n): a moved table's copy, the shifted heap, or (addr, None)."""
        t = self.table(addr)
        if t:
            old, end, new, name, row, header = t
            why = f"{name} table"
            if row and header is not None and addr >= old + header:     # a per-character table: rows are ids
                why += f", character 0x{(addr - old - header) // row:02X}"
            elif row:
                why += f", row {(addr - old) // row}"
            if addr + n > end:
                why += " (it runs past the old table's end: the rest follows it)"
            return new + (addr - old), why
        if self.heap_shift and self.heap_start <= addr and addr + n + self.heap_shift <= ARENA_HI:
            return addr + self.heap_shift, "run-time memory"
        return addr, None

    def conflict(self, addr, n=4):
        """The changed-words entry [addr, addr+n) touches, or None."""
        return next((c for s, e, c in self.changed if s < addr + n and addr < e), None)


# --- reading codes

class Code:
    def __init__(self, name):
        self.name, self.lines, self.notes, self.blank = name, [], [], False
        self.status, self.messages, self.new_lines = "fine", [], None

    @property
    def title(self):
        return self.name.lstrip("$").strip() or "(no name)"


def parse(text):
    """([Code], ini or None). ini: a Dolphin GameSettings file's lines, [Gecko]'s codes read; other text: pasted
    codes: a line that isn't a code line starts a new code (its name), "*" lines are notes."""
    lines = text.splitlines()
    ini = any(l.strip().lower() == "[gecko]" for l in lines)
    codes, cur, section = [], None, None
    for l in lines:
        s = l.strip()
        if ini and s.startswith("[") and s.endswith("]"):
            section, cur = s.lower(), None
            continue
        if ini and section != "[gecko]":
            continue
        if not s:
            continue
        if not ini and s.startswith("(") and cur is not None:     # "(In order Toad, ...)": a note on the name above
            cur.notes.append("*" + s)
        elif s.startswith("$") or (not ini and not BLANK.match(s) and not s.startswith("*")):
            cur = Code(s)
            codes.append(cur)
        elif s.startswith("*"):
            if cur is not None:
                cur.notes.append(s)
        elif cur is not None:
            m = HEX.match(s)
            if m:
                cur.lines.append((int(m.group(1), 16), int(m.group(2), 16)))
            else:
                m = BLANK.match(s)
                if m:
                    cur.blank = True
                    cur.lines.append((m.group(1), m.group(2)))
    return [c for c in codes if c.lines], (lines if ini else None)


# --- fixing one code

def scan_asm(words, fix):
    """C0 / C2 bodies: every lis rX + (addi / ori / load-store with base rX) pair; fix(ea) -> (new ea, why).
    Returns (new words, [what moved], [problems])."""
    words = list(words)
    track, pairs = {}, []                                   # reg -> index of its lis
    for i, w in enumerate(words):
        op, rd, ra = w >> 26, (w >> 21) & 31, (w >> 16) & 31
        if op == 15 and ra == 0:                            # lis rd, imm
            track[rd] = i
            continue
        if op == 14 and ra in track:                        # addi rd, ra, imm
            pairs.append((track[ra], i, "addi", (words[track[ra]] & 0xFFFF) << 16))
            if rd == ra:
                del track[ra]
        elif op == 24 and rd in track:                      # ori ra, rs(=rd field), imm
            pairs.append((track[rd], i, "ori", (words[track[rd]] & 0xFFFF) << 16))
            if ra == rd:
                del track[rd]
        elif 32 <= op <= 55 and ra in track:                # loads / stores: d(ra)
            pairs.append((track[ra], i, "d", (words[track[ra]] & 0xFFFF) << 16))
            if op & 1 or (op in (32, 34, 40, 42, 46) and rd == ra):   # update forms / the base loaded over
                del track[ra]
        elif op in (18, 19) and w & 1:                      # a call: r0, r3-r12 are gone
            track = {r: k for r, k in track.items() if r not in (0, *range(3, 13))}
        elif rd in track and op not in (36, 37, 38, 39, 44, 45, 47, 52, 53, 54, 55, 10, 11, 16, 18, 19):
            del track[rd]                                   # (most other instructions write rD)
    need, moved, problems = {}, [], []                      # lis index -> the high half its pairs need
    for lis_i, use_i, kind, hi in pairs:
        low = words[use_i] & 0xFFFF
        ea = (hi | low) if kind == "ori" else (hi + sext(low)) & 0xFFFFFFFF
        new, why = fix(ea)
        need.setdefault(lis_i, []).append((use_i, kind, ea, new, why))
    for lis_i, uses in need.items():
        highs = {(u[3] >> 16) if u[1] == "ori" else ha(u[3]) for u in uses}
        if not any(u[4] for u in uses):
            continue
        if len(highs) > 1:
            problems.append(f"its asm loads 0x{uses[0][2]:08X} and more with one lis, and they moved differently: "
                            "left as it is")
            continue
        for use_i, kind, ea, new, why in uses:
            words[use_i] = (words[use_i] & 0xFFFF0000) | lo(new)
            if why:
                moved.append((ea, new, why))
        words[lis_i] = (words[lis_i] & 0xFFFF0000) | highs.pop()
    return words, moved, problems


def fix_code(code, m, titles=None, offered=None, where=None):
    """Fix one Code against Map m, in place: code.new_lines, code.status (fine / fixed / conflict / built-in / blank /
    unsure), code.messages (plain words). offered: {feature id} the patcher offers (built-in hints), where: where the
    player turns those on ("Game options")."""
    titles = titles if titles is not None else feature_titles()
    if code.blank:
        code.status = "blank"
        code.messages.append("It has blanks to fill in (like XX): fill them in and run this again.")
        code.new_lines = list(code.lines)
        return code
    for fid, label, test in BUILT_IN:
        if test(code):
            if fid in m.features:
                code.status = "built-in"
                code.messages.append(f"Your patched game already has {label} built in. Leave this code off: the "
                                     "two would fight.")
                code.new_lines = list(code.lines)
                return code
            if offered is None or fid in offered:
                code.messages.append(f"The patcher has {label} built in" + (f" ({where})" if where else "") +
                                     ": turn it on there and patch again instead of using this code.")
    out = list(code.lines)
    moved, conflicts, notes = [], [], []
    ba = po = (DEFAULT_BASE, DEFAULT_BASE)                  # (old base, new base); None: known only in game

    def conflict(addr, n, what):
        c = m.conflict(addr, n)
        if c:
            name = titles.get(c.get("feature"), c.get("feature") or "own changes")
            conflicts.append(f"{what} 0x{addr:08X}, which the patcher's {name} already changes")

    def relocate_line(i, base, off_bits, n, kind):
        """A ba/po-relative line at out[i]: point it at the moved address; returns the address it reads/writes."""
        w0 = out[i][0]
        if base is None:                                    # (a pointer the game keeps: it follows the game)
            return None
        old_base, new_base = base
        off = w0 & off_bits
        addr = (old_base + off) & 0xFFFFFFFF
        new, why = m.move(addr, n)
        if why is None:
            new = addr
        new_off = new - new_base
        if not 0 <= new_off <= 0x01FFFFFF:
            if why:
                notes.append(f"line {i + 1}: 0x{addr:08X} ({why}) is out of this code's reach: left as it is")
            return addr
        if why or new_base != old_base:
            out[i] = ((w0 & ~0x01FFFFFF & 0xFFFFFFFF) | (new_off & off_bits) | (w0 & 0x01FFFFFF & ~off_bits),
                      out[i][1])
            if why:
                moved.append((addr, new, why))
        return addr

    i, lines = 0, code.lines
    while i < len(lines):
        w0, w1 = lines[i]
        t = w0 >> 24
        base = po if t & 0x10 else ba
        if t < 0x20:                                        # writes
            sub = t & 0x0E
            if sub in (0x00, 0x02):
                n = ((w1 >> 16) + 1) * (1 if sub == 0 else 2)
                addr = relocate_line(i, base, 0x01FFFFFF, n, "write")
                if addr is not None:
                    conflict(addr, n, "It writes")
                i += 1
            elif sub == 0x04:
                addr = relocate_line(i, base, 0x01FFFFFF, 4, "write")
                if addr is not None:
                    conflict(addr, 4, "It writes")
                    tv = m.table(w1)
                    if tv and not m.table(addr):            # a pointer into a moved table, written as a value
                        new, why = m.move(w1)
                        out[i] = (out[i][0], new)
                        moved.append((w1, new, why + " (the address it writes)"))
                i += 1
            elif sub == 0x06:
                n = w1
                addr = base and (base[0] + (w0 & 0x01FFFFFF)) & 0xFFFFFFFF
                if addr and m.move(addr, n)[1] == "run-time memory":   # its own asm in free memory (a branch to
                    i += 1 + (n + 7) // 8                   # it follows): left where it is
                    continue
                addr = relocate_line(i, base, 0x01FFFFFF, n, "write")
                if addr is not None:
                    conflict(addr, n, "It writes")
                i += 1 + (n + 7) // 8
            elif sub == 0x08:
                if i + 1 >= len(lines):
                    notes.append("its last serial write is cut short: left as it is")
                    break
                x0 = lines[i + 1][0]
                size = (1, 2, 4)[min(x0 >> 28, 2)]
                count, step = ((x0 >> 16) & 0xFFF) + 1, x0 & 0xFFFF
                n = (count - 1) * step + size
                addr = relocate_line(i, base, 0x01FFFFFF, n, "write")
                if addr is not None:
                    conflict(addr, n, "It writes")
                i += 2
            else:
                notes.append(f"line {i + 1}: code type {t:02X} isn't one this reads: the rest is left as it is")
                break
        elif t < 0x40:                                      # ifs: 20-27 32-bit, 28-2F 16-bit; bit 0 = endif first
            n = 4 if (t & 0x0E) < 0x08 else 2
            addr = relocate_line(i, base, 0x01FFFFFE, n, "check")
            if addr is not None and m.conflict(addr, n):
                c = m.conflict(addr, n)
                name = titles.get(c.get("feature"), c.get("feature") or "own changes")
                notes.append(f"it checks 0x{addr:08X}, which the patcher's {name} changes: that check may never "
                             "match now")
            i += 1
        elif t < 0x60:                                      # base / pointer: 40 load ba, 42 set, 44 store, 46 here
            op = t & 0x4E
            plain = (w0 & 0x00FFFFFF) == 0 and not t & 0x10
            target = "ba" if op < 0x48 else "po"
            if op in (0x40, 0x48) and plain:                # load from [w1]
                new, why = m.move(w1)
                if why:
                    out[i] = (w0, new)
                    moved.append((w1, new, why + " (the pointer it loads)"))
                val = None
            elif op in (0x42, 0x4A) and plain:              # set to w1
                new, why = m.move(w1)
                val = (w1, new)
                if why:
                    out[i] = (w0, new)
                    moved.append((w1, new, why))
            elif op in (0x44, 0x4C):                        # store: the base goes to memory, unchanged
                if plain:
                    new, why = m.move(w1)
                    if why:
                        out[i] = (w0, new)
                        moved.append((w1, new, why))
                i += 1
                continue
            else:                                           # relative / from po / the code's own address
                val = None
            if target == "ba":
                ba = val
            else:
                po = val
            i += 1
        elif t < 0x80:                                      # repeat / goto / gosub / return: line counts only
            i += 1
        elif t < 0xA0:                                      # gecko registers: 82 load, 84 store at [w1]
            op = t & 0xFE
            if op in (0x82, 0x84) and not (w0 >> 16) & 0xF and not t & 0x10:   # (82UY: Y 0 = absolute)
                new, why = m.move(w1)
                if why:
                    out[i] = (w0, new)
                    moved.append((w1, new, why))
                if op == 0x84:
                    conflict(w1, 4, "It writes")
            elif op in (0x8A, 0x8C):
                notes.append(f"line {i + 1} copies memory by register: left as it is")
            i += 1
        elif t < 0xC0:                                      # register / counter ifs
            i += 1
        elif t & 0xEE in (0xC0, 0xC2):                      # C0 execute / C2 insert asm (D2: po-based)
            n = w1
            body = [w for a, b in lines[i + 1:i + 1 + n] for w in (a, b)]
            if (t & 0xEE) == 0xC2:
                if base is None:
                    notes.append("its hook address is loaded while the game runs: not checked")
                else:
                    hook = (base[0] + (w0 & 0x01FFFFFF)) & 0xFFFFFFFF
                    conflict(hook, 4, "It hooks")
            words, mv, probs = scan_asm(body, lambda a: m.move(a))
            moved += mv
            notes += probs
            for k in range(n):
                if i + 1 + k < len(out):
                    out[i + 1 + k] = (words[2 * k], words[2 * k + 1])
            i += 1 + n
        elif t & 0xEE == 0xC6:                              # C6: a branch written at an address
            if base is not None:
                conflict((base[0] + (w0 & 0x01FFFFFF)) & 0xFFFFFFFF, 4, "It hooks")
            i += 1
        elif t & 0xEE in (0xCC, 0xCE):                      # on/off switch, address range check
            i += 1
        elif t == 0xE0:                                     # full terminator: ba / po from w1 (0x80008000)
            ba = ((w1 & 0xFFFF0000) or DEFAULT_BASE,) * 2
            po = (((w1 & 0xFFFF) << 16) or DEFAULT_BASE,) * 2
            i += 1
        elif t == 0xE2:                                     # endif (w1: ba / po when nonzero)
            if w1 & 0xFFFF0000:
                ba = (w1 & 0xFFFF0000,) * 2
            if w1 & 0xFFFF:
                po = ((w1 & 0xFFFF) << 16,) * 2
            i += 1
        elif t == 0xF0:
            i += 1
        else:
            notes.append(f"line {i + 1}: code type {t:02X} isn't one this reads: the rest is left as it is")
            break
    code.new_lines = out
    heap = [x for x in moved if x[2] == "run-time memory" or x[2].startswith("run-time memory")]
    tables = [x for x in moved if x not in heap]
    if conflicts:
        code.status = "conflict"
        feats = sorted({re.search(r"patcher's (.+?) already", c).group(1) for c in conflicts})
        code.messages.insert(0, f"It conflicts with the patcher's {', '.join(feats)}: leave it off.")
        code.messages += conflicts[:4] + ([f"(and {len(conflicts) - 4} more)"] if len(conflicts) > 4 else [])
        code.new_lines = list(code.lines)
        return code
    if tables:
        code.status = "fixed"
        code.messages.append("Fixed: it wrote tables the patcher moved; now it writes the ones the game reads.")
        seen = set()
        for old, new, why in tables:
            if (old, new) not in seen:
                seen.add((old, new))
                code.messages.append(f"0x{old:08X} -> 0x{new:08X} ({why})")
    if heap:
        code.status = "fixed" if tables else "unsure"
        code.messages.append(
            f"Moved {len(heap)} address{'es' if len(heap) > 1 else ''} in the game's run-time memory by "
            f"0x{m.heap_shift:X}: the patched game uses more memory, so what the game makes as it runs sits higher. "
            "Right for the controllers and the match settings; if it still does nothing, the thing it looks for "
            "moved further.")
        for old, new, _ in heap[:4]:
            code.messages.append(f"0x{old:08X} -> 0x{new:08X}")
    code.messages += notes
    if not (tables or heap or notes or code.messages):
        code.messages.append("Nothing to change: it should work as it is.")
    return code


def fix(text, m, offered=None, where=None):
    """[Code] fixed against Map m, and the lines of the fixed file (fixed_text)."""
    codes, _ = parse(text)
    titles = feature_titles()
    for c in codes:
        fix_code(c, m, titles, offered, where)
    return codes


OFF = ("conflict", "built-in")                              # turned off in the fixed ini


def fmt(w):
    return w if isinstance(w, str) else f"{w:08X}"


def fixed_text(text, codes):
    """The file with the codes' lines replaced (same names, same notes), and the conflicting / built-in ones taken
    out of [Gecko_Enabled]. Pasted text (no [Gecko]): a [Gecko] section of the codes, the fixed ones enabled."""
    _, ini = parse(text)
    by_name = {}
    for c in codes:
        by_name.setdefault(c.name, []).append(c)
    if ini is None:
        out = ["[Gecko]"]
        for c in codes:
            out.append(c.name if c.name.startswith("$") else "$" + c.name)
            out += [f"{fmt(a)} {fmt(b)}" for a, b in c.new_lines]
            out += c.notes
        out += ["[Gecko_Enabled]"] + [(c.name if c.name.startswith("$") else "$" + c.name)
                                      for c in codes if c.status not in OFF + ("blank",)]
        return "\n".join(out) + "\n"
    off = {c.name.strip() for c in codes if c.status in OFF}
    out, section, cur, k = [], None, None, 0
    for l in ini:
        s = l.strip()
        if s.startswith("[") and s.endswith("]"):
            section, cur = s.lower(), None
            out.append(l)
            continue
        if section == "[gecko]":
            if s.startswith("$"):
                cur = by_name.get(s, [None]).pop(0) if by_name.get(s) else None
                k = 0
            elif cur is not None and (HEX.match(s) or BLANK.match(s)):
                a, b = cur.new_lines[k]
                out.append(f"{fmt(a)} {fmt(b)}")
                k += 1
                continue
        elif section == "[gecko_enabled]" and s in off:
            continue
        out.append(l)
    return "\n".join(out) + ("\n" if text.endswith("\n") else "")


HEADS = {"fine": "Works as it is", "fixed": "Fixed", "unsure": "Fixed (best guess)", "conflict": "Turned off",
         "built-in": "Turned off (built in)", "blank": "Not changed"}


def report(codes):
    """Plain words, one block per code."""
    out = []
    for c in codes:
        out.append(f"{c.title}: {HEADS.get(c.status, c.status)}")
        out += ["  " + msg for msg in c.messages]
        out.append("")
    return "\n".join(out).rstrip() + "\n"


def dolphin_inis():
    """Where Dolphin keeps RMBE01.ini (the ones that exist): %APPDATA%, Documents, and a portable User folder next to
    a Dolphin in the usual places."""
    home = Path.home()
    spots = [Path(os.environ.get("APPDATA", home / "AppData/Roaming")) / "Dolphin Emulator",
             home / "Documents/Dolphin Emulator", home / "OneDrive/Documents/Dolphin Emulator"]
    return [p / "GameSettings/RMBE01.ini" for p in spots if (p / "GameSettings/RMBE01.ini").exists()]


DETAILS = " (patch details)"     # the folder beside a patched ISO holding log.txt, choices.json, relocations.json


def details_dir(iso):
    """The patch details folder of an ISO path: "<iso stem> (patch details)" beside it (Nick opened the old
    <name>.relocations.json in Dolphin: with extensions hidden the side files looked like the ISO)."""
    iso = Path(iso)
    return iso.with_name(iso.stem + DETAILS)


def relocation_file(iso):
    """The relocations file of an ISO path (its patch details folder's relocations.json, or the older
    <name>.relocations.json beside it), or the newest one in its folder; None."""
    if not iso:
        return None
    iso = Path(iso)
    for own in (details_dir(iso) / "relocations.json", iso.with_suffix(".relocations.json")):
        if own.exists():
            return own
    folder = iso if iso.is_dir() else iso.parent
    found = (list(folder.glob("*.relocations.json")) + list(folder.glob("*" + DETAILS + "/relocations.json"))
             if folder.is_dir() else [])
    found.sort(key=lambda p: p.stat().st_mtime)
    return found[-1] if found else None


def main():
    import argparse
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("codes", help="Dolphin's RMBE01.ini, or a text file of codes")
    ap.add_argument("relocations", help="the patched ISO's relocations.json (in its \"(patch details)\" folder)")
    ap.add_argument("--out", help="write the fixed codes here (never over the codes file)")
    a = ap.parse_args()
    text = Path(a.codes).read_text(encoding="utf-8-sig", errors="replace")
    codes = fix(text, Map.load(a.relocations))
    sys.stdout.write(report(codes))
    if a.out:
        assert Path(a.out).resolve() != Path(a.codes).resolve(), "--out must be a new file"
        Path(a.out).write_text(fixed_text(text, codes), encoding="utf8")


if __name__ == "__main__":
    main()
