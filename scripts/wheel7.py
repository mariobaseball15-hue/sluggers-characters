"""Color wheels of up to MEMBERS (10) characters (Nick: 7 Yoshis to test, then 10, one per swatch color but
brown). The stock game stops at 6. 10 is the game's own ceiling: each family's member list in the roster
struct (FUN_8006ba6c: count at X+0x4D+family, ids at X+0x76+family*10) is 10 wide, the next family's list
right after it; an 11th needs those lists moved (about 7 functions read or write them).

1. Stack buffers (FRAMES). Every caller of the member-list builders FUN_80071bb0 / FUN_80430184 (one word per
   member), and of the popup fillers FUN_8006c044 / FUN_8042bd2c (which pass the caller's buffer on), keeps
   the list in a stack buffer of 6-9 words (found by scanning each call's buffer argument and the next r1
   offset the function uses). Each grows to hold at least MEMBERS: every r1-relative offset (D-form
   loads/stores, stmw/lmw, psq, addi/addic rX,r1,..) at or above the buffer's end moves up GROW bytes, with
   the stwu r1 prologue and the addi r1,r1 epilogue. A function with two buffers has two entries, the higher
   first. grow_frame() refuses any other use of r1 (X-form) and checks the prologue. (A 7th member
   overwrote saved r28 in FUN_8007569c.)
2. The popup layout (dt_na dir 119 file 19, element POPUP = 0xB3, shared by the wheel popups): nodes 0-5
   anchor the swatches (0xAD), 6 / 7 the end caps (0xB0 / 0xAF), 8 the background pane; its time is
   count - 2 (keys at 0..4, highest first). patch_layout() adds times 5..MEMBERS-2 (7..10 members) with the
   stock spacing continued: swatches 10 px apart and centred (member m at -5(n-1) + 10m), caps and pane
   half-width at 5(n-1) + 15 (stock: 20 at 2 .. 40 at 6), and one swatch node per member past 6 (nodes 9..),
   keyed from the count that shows it. The element's last time (sub-header +4) becomes MEMBERS - 2.
3. The member lists (LIST_CAPS): FUN_80071bb0's family path counts every available member but writes only the
   first 6 to out[] (`cmpwi cr1,r28,0x6` at 0x80071ECC) and returns the count: with 7 the caller read out[6]
   from uninitialised stack and drew the swatch of a garbage id (Dolphin, clean-1: invalid read at
   0x8006C4C4, `lbz r0,0x7(r4)` = selector[id] + 7). The cap becomes MEMBERS, in the other builder
   FUN_80430184 (`cmpwi cr1,r24,0x6` at 0x804303CC) too.
4. Member index -> node (NODE_SITES): the popups store the member index as the swatch widget's node
   (`stb r27,0x47(r4)` in FUN_8006c44c, `stb r27,0x5f(r4)` in FUN_8042c048). Index 6 would be the right
   cap's node; members 6.. use nodes 9.. (index >= 6: + 3).

Not handled: the screens behind FUN_801c32a0 and FUN_8018bed0 (their own count switch / style table and 6
widgets; they only scan stock ids 0..0x46 / 0..0x4C, so a new id doesn't appear there at all).
"""
import struct
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
from ppc import Asm, branch  # noqa: E402

MEMBERS = 10
GROW = 0x10
# (function start, last instruction, buffer start, buffer end = first offset that moves): capacity
# (end - start) / 4 before, + GROW / 4 after. Several entries for one function: the higher end first.
FRAMES = [(0x8007569C, 0x80075788, 0x08, 0x20),   # team-slot color cycling (saved r28 at 0x20)
          (0x800721A0, 0x800722E8, 0x08, 0x20),   # a second buffer at 0x20
          (0x80073958, 0x80075068, 0x48, 0x68),   # two buffers: 0x48 (8) ...
          (0x80073958, 0x80075068, 0x30, 0x48),   # ... and 0x30 (6)
          (0x80431DF0, 0x80431FDC, 0x08, 0x20),
          (0x8042C8A4, 0x8042EFD0, 0x28, 0x40),
          (0x8006C044, 0x8006C39C, 0x08, 0x24),   # the main popup's filler (its own list)
          (0x8006C44C, 0x8006C56C, 0x10, 0x2C),   # the main popup's swatch draw
          (0x8006D3C0, 0x8006DA10, 0x10, 0x34),
          (0x8006E7D8, 0x8006E85C, 0x08, 0x28),   # head -> displayed id
          (0x800751DC, 0x80075698, 0x08, 0x24),
          (0x8007578C, 0x80075C7C, 0x08, 0x2C),   # main-screen color cycling
          (0x80077054, 0x80077424, 0x20, 0x3C),
          (0x8042AF3C, 0x8042B404, 0x10, 0x2C),
          (0x8042BD2C, 0x8042BF98, 0x08, 0x28),   # the grid popup's filler
          (0x8042C048, 0x8042C168, 0x10, 0x2C),   # the grid popup's swatch draw
          (0x8042C180, 0x8042C200, 0x08, 0x28),
          (0x8042FEEC, 0x80430180, 0x08, 0x24),
          (0x804305E8, 0x8043081C, 0x08, 0x2C)]
NODE_SITES = [(0x8006C4B4, 0x9B640047), (0x8006C51C, 0x9B640047),   # stb r27,0x47(r4)
              (0x8042C0B0, 0x9B64005F), (0x8042C118, 0x9B64005F)]   # stb r27,0x5f(r4)
POPUP, SEVENTH_NODE = 0xB3, 9
STOCK_LAST = 4                                      # POPUP's last time (6 members)
LIST_CAPS = [(0x80071ECC, 0x2C9C0006), (0x804303CC, 0x2C980006)]   # cmpwi cr1,r28 / r24,0x6 -> MEMBERS
D_FORM = set(range(32, 56)) | {14, 12, 13}         # loads/stores, lmw/stmw, fp; addi, addic, addic.
PSQ = {56, 57, 60, 61}                              # psq_l(u), psq_st(u): 12-bit offset


def grow_frame(dol, start, last, threshold, grow=GROW):
    """Shift r1-relative offsets >= threshold by `grow` in [start, last]; returns the number of words changed."""
    first = dol.u32(start)
    assert first >> 16 == 0x9421, f"0x{start:08X}: not stwu r1,-N(r1)"
    changed = 0
    for addr in range(start, last + 4, 4):
        w = dol.u32(addr)
        op, rd, ra = w >> 26, (w >> 21) & 31, (w >> 16) & 31
        new = None
        if addr == start:
            size = -((w & 0xFFFF) - 0x10000)
            new = (w & 0xFFFF0000) | ((-(size + grow)) & 0xFFFF)
        elif op in D_FORM and ra == 1:
            off = w & 0xFFFF
            off = off - 0x10000 if off & 0x8000 else off
            if off >= threshold:
                assert off + grow < 0x8000
                new = (w & 0xFFFF0000) | (off + grow)
        elif op in PSQ and ra == 1:
            off = w & 0xFFF
            off = off - 0x1000 if off & 0x800 else off
            if off >= threshold:
                assert off + grow < 0x800
                new = (w & 0xFFFFF000) | (off + grow)
        elif op == 31 and (ra == 1 or (w >> 11) & 31 == 1 or rd == 1):
            raise AssertionError(f"0x{addr:08X}: {w:08X} uses r1 in an X-form instruction")
        if new is not None and new != w:
            dol.w32(addr, new)
            changed += 1
    return changed


def node_stub(orig):
    """The replaced `stb r27,off(r4)`, with member index >= 6 sent to SEVENTH_NODE + (index - 6).
    r0 is free here (the next instruction loads it)."""
    off = orig & 0xFFFF

    def build(base):
        a = Asm(base)
        a.mr(0, 27).cmpwi(27, 6, cr=1).blt("store", cr=1)
        a.addi(0, 27, SEVENTH_NODE - 6)                    # (addi from r0 would read 0)
        a.label("store")
        a.stb(0, off, 4)
        return a
    return build


def apply(dol, code):
    """Stack frames, list caps and node remaps in `dol`; stubs in `code` (a Space: .here, .blob, .put)."""
    log = []
    for start, last, buf, threshold in FRAMES:
        assert (threshold - buf + GROW) // 4 >= MEMBERS
        n = grow_frame(dol, start, last, threshold)
        log.append(f"{start:08x}({n})")
    for cap, orig in LIST_CAPS:
        assert dol.u32(cap) == orig, f"0x{cap:08X}: {dol.u32(cap):08X}"
        dol.w32(cap, (orig & 0xFFFF0000) | MEMBERS)
    for site, orig in NODE_SITES:
        assert dol.u32(site) == orig, f"0x{site:08X}: {dol.u32(site):08X}, expected {orig:08X}"
        at = code.here + (-len(code.blob) % 4)
        body = node_stub(orig)(at).assemble()
        body += Asm(at + len(body)).b(site + 4).assemble()
        assert code.put(body, 4) == at
        dol.w32(site, branch(site, at))
    return [f"wheel7: color wheels of up to {MEMBERS}; member list caps {MEMBERS} ("
            + ", ".join(f"0x{c:08X}" for c, _ in LIST_CAPS) + f"); {len(FRAMES)} stack buffers +0x{GROW:x} "
            + "(function(words): " + " ".join(log) + f"); members 6.. -> nodes {SEVENTH_NODE}.. at "
            + ", ".join(f"0x{s:08X}" for s, _ in NODE_SITES)]


# --- layout ---------------------------------------------------------------------------------------------

def _key(blob, j, stride):
    return bytearray(blob[4 + j * stride:4 + (j + 1) * stride])


def _set_x(key, x):
    for o in (0x08, 0x18, 0x1C):
        struct.pack_into(">h", key, o, x)


def _time_key(model, t):
    """A copy of key `model` at time t (the time is also at +0x28 in an element key)."""
    key = bytearray(model)
    struct.pack_into(">H", key, 2, t)
    if len(key) == 0x3C:
        assert struct.unpack_from(">H", key, 0x28)[0] == STOCK_LAST, "unexpected element key"
        struct.pack_into(">H", key, 0x28, t)
    return key


def swatch_x(n, m):
    """x of member m's swatch with n members (the stock spacing: 10 px, centred)."""
    return -5 * (n - 1) + 10 * m


def edge(n):
    """End caps' x and the pane's half-width with n members (stock: 20 at 2 .. 40 at 6)."""
    return 5 * (n - 1) + 15


def popup_nodes(blobs):
    """Node blobs of POPUP -> with keys for 7..MEMBERS members on every node, and nodes 9.. (members 6..)."""
    assert len(blobs) == 9, "POPUP should have 9 nodes"
    new_times = list(range(MEMBERS - 2, STOCK_LAST, -1))           # highest first
    out = []
    for i, blob in enumerate(blobs):
        cnt, stride = struct.unpack_from(">HH", blob, 0)
        keys = [_key(blob, j, stride) for j in range(cnt)]
        assert struct.unpack_from(">H", keys[0], 2)[0] == STOCK_LAST and not keys[0][0] & 1, f"node {i}: first key"
        new = []
        for t in new_times:
            n = t + 2
            key = _time_key(keys[0], t)
            if i < 6:
                _set_x(key, swatch_x(n, i))
            elif i in (6, 7):
                _set_x(key, edge(n) if i == 6 else -edge(n))
            else:                                                   # the pane: its quad's half-width
                assert stride == 0x58
                for o in range(0x28, 0x48, 4):
                    v = struct.unpack_from(">f", key, o)[0]
                    if abs(v) == 40.0:
                        struct.pack_into(">f", key, o, float(edge(n)) if v > 0 else -float(edge(n)))
            key[0] |= 1
            new.append(key)
        new[0][0] &= ~1                                             # the new first key
        keys[0][0] |= 1
        out.append(struct.pack(">HH", cnt + len(new), stride) + b"".join(bytes(k) for k in new + keys))
    cnt, stride = struct.unpack_from(">HH", blobs[5], 0)
    model = _key(blobs[5], 0, stride)                               # node 5's only key (time 4)
    for m in range(6, MEMBERS):                                     # nodes 9..: members 6..
        keys = []
        for t in range(MEMBERS - 2, m - 2, -1):                     # counts m + 1 .. MEMBERS
            key = _time_key(model, t)
            _set_x(key, swatch_x(t + 2, m))
            key[0] |= 1
            keys.append(key)
        keys[0][0] &= ~1
        out.append(struct.pack(">HH", len(keys), stride) + b"".join(bytes(k) for k in keys))
    return out


def patch_layout(lay):
    """layout.Layout of dir 119 file 19: POPUP gets its frames for 7..MEMBERS. Returns a log line."""
    blobs = lay.node_blobs(POPUP)
    lay.set_nodes(POPUP, popup_nodes(blobs))
    e = lay.elements[POPUP]
    sub = struct.unpack_from(">I", e, 12)[0]
    assert struct.unpack_from(">H", e, sub + 4)[0] == STOCK_LAST, "POPUP's last time"
    struct.pack_into(">H", e, sub + 4, MEMBERS - 2)
    return f"wheel7: layout element 0x{POPUP:X} gets times {STOCK_LAST + 1}..{MEMBERS - 2} and nodes {SEVENTH_NODE}.."


def layout_bytes(data):
    """One language's dir 119 file 19 bytes -> with patch_layout applied (for gridcells.patch_layout's extra)."""
    import layout
    lay = layout.Layout(data)
    patch_layout(lay)
    return lay.to_bytes()
