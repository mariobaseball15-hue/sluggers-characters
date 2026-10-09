"""The level 6 defense log (Nick, 2026-09-27: "I only want to do one dump so make sure you log everything you need"):
one fixed-size record per frame of the level 6 CPU fielders' attack play, in a ring in the data section, read from a
MEM1 dump by scripts/read_defense_log.py. Off (LOG_ENTRIES = 0: no hook, no data, nothing changes) in normal builds;
build_test_items.py turns it on. Same model as the item log (cpu_items.py LOG_ENTRIES / read_item_log.py).

HOOK 0x801327C0 (FUN_801326fc, the play state's per-frame update: `lwz r3,-0x15b4(r13)` right after `bl 0x800c8384`).
FUN_801326fc [C, decomp + listing] runs, unconditionally and in this order: the play tick (*(r13-0x1684)+0xC), the ball
update FUN_800AC784(game) (moves the ball, re-predicts the path), then FUN_800C8384(defense ai), which is the whole
fielding frame: 800CF554 clears the presses, 800E21EC decides (cpu_item_defense's DECIDE stub, the debug block
defense_dbg writes), 800D5A38 runs each fielder (8010BCB0: F+0x13C, the hit test FUN_8011F2B0 / the catch count;
8010B200: the state handler / mover, whose 80112BC4 -> 8011D5F4 turns a press into +0x265 = 1). Only after it
returns: the batting/running side (80155F1C), the item manager (80455394; wendy_rings hooks 0x801327FC), etc. So at
0x801327C0 the ball has moved and every fielder (chaser included) has run this frame: the record is the frame's end
state. There is no branch between the two calls: it runs once every frame FUN_801326fc runs (every frame of a play,
pitch included). Free here: r0, r3-r12, f0, cr0, ctr, LR (the function saved LR at 0x14(r1) and reloads it in its
epilogue, 0x8013284C) -- the stub may `bl`. r31 (param_1) is kept. The stub ends with the stock `lwz r3,-0x15b4(r13)`.

GATES: level 5 FLAG byte == 2 (level 6), fielder 0 of the fielding side (0x80708D9C / 0x80708DC0 / 0x80708D78 chain,
as cpu_item_defense's Boo stub) at level byte +0x2E == 0 (the level 6 CPU fields), the defense ai present (first
non-null of r13-0x1D14/-0x1D10/-0x1D18/-0x1D1C). Then one record per frame while the ball is loose (game+0x2A4C < 0:
pitch flight, batted ball, throws) and for TAIL more frames once someone holds it (the catch / the knocked pass taken).

HEADER (0x20 B): b"L6DL", u32 records written, u32 entries (a power of 2), u32 record size, u32 tail countdown, pad.
RECORD (REC = 0xC0 B, big-endian) at header + 0x20 + (seq % entries) * REC; the fields are the table FIELDS below
(the reader decodes from it). The chaser F = fielder ai+0x2D8 (s16, = F+0x21C) through the same 3-array chain;
chaser fields are 0 (mate -1) when there is none. The last 0x40 B are a copy of the defense_dbg block (its FRAME ==
the record's FRAME only when cpu_item_defense's decision stub ran this frame).
"""
import struct
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
import defense_dbg  # noqa: E402
import level5  # noqa: E402
from ppc import Asm, branch, d_form, ha, lo  # noqa: E402

LOG_ENTRIES = 0                   # 0 = off (normal builds); build_test_items.py sets it (a power of 2)
MAGIC, HDR, REC = b"L6DL", 0x20, 0xC0
TAILW = 0x10                      # header: the frames still logged after the ball got held
TAIL = 30
DBG_AT = 0x80                     # the defense_dbg copy inside a record

HOOK = 0x801327C0
ORIG = d_form(32, 3, 13, -0x15B4)  # lwz r3,-0x15b4(r13)
FIELDERS = (0x80708D9C, 0x80708DC0, 0x80708D78)   # 9 pointers each, by fielder id; first non-null wins (800E21EC)
DEFENSE = (-0x1D14, -0x1D10, -0x1D18, -0x1D1C)
GAME, TICK = -0x1D94, -0x1684
NEAREST_MATE = 0x801148F4          # leaf (r0, r3-r8, f0, f1, ctr): (F, float *d) -> nearest teammate id

# (name, kind, source, offset in the record): source "t" = *(r13-0x1684), "g" = game, "a" = defense ai, "f" = chaser
FIELDS = [
    ("frame", "h", "t", 2, 0x00),       # frames since contact
    ("play", "h", "t", 0, 0x02),        # play frame counter
    ("pitch", "h", "t", 4, 0x04),       # pitch frame counter (zeroed at release)
    ("chaser", "b", "a", 0x2D9, 0x06),  # ai+0x2D8 (s16; low byte)
    ("g2A72", "B", "g", 0x2A72, 0x07),  # ball state: 2 = passed/knocked (8011F2B0 refuses at 2)
    ("holder", "h", "g", 0x2A4C, 0x08),  # < 0: loose
    ("landed", "h", "g", 0x2A4E, 0x0A),  # != 0: bounced
    ("pass_to", "h", "a", 0x320, 0x0C),  # ai+0x320: the pass target a hit sends the ball to
    ("mate", "b", None, None, 0x0E),     # 801148F4(F): nearest teammate id (-1: no chaser)
    ("aiD4", "B", "a", 0xD4, 0x0F),      # ai+0xD4 (slot 4 press) at frame end
    ("bx", "f", None, None, 0x10), ("by", "f", None, None, 0x14), ("bz", "f", None, None, 0x18),  # 800AC748(game)
    ("bheight", "f", "g", 0x29B4, 0x1C),  # game+0x29B4 (the fly / liner test: > 5.0 fly)
    ("fx", "f", "f", 0x4, 0x20), ("fy", "f", "f", 0xD4, 0x24), ("fz", "f", "f", 0xC, 0x28),
    ("face", "f", "f", 0xF8, 0x2C),       # facing (8011D5F4 writes both when it takes the press)
    ("face_dc", "f", "f", 0xDC, 0x30),
    ("speed", "f", "f", 0xE4, 0x34),
    ("ball_d", "f", "f", 0x13C, 0x38),    # ground distance to the ball (8010BCB0, this frame)
    ("target_d", "f", "f", 0x148, 0x3C),  # distance to his route target [I]
    ("mate_d", "f", None, None, 0x40),
    ("radius", "f", "f", 0x1C, 0x44),
    ("ball_r", "f", "g", 0x420, 0x48),
    ("height", "f", "f", 0x20, 0x4C),
    ("delay", "B", "f", 0x226, 0x50),    # reaction delay: a u8 (lbz in FUN_800E2830 / 800E246C / 8010BCB0); it was
                                         # logged as a halfword with +0x227 (0xFF in Nick's dumps) in its low byte:
                                         # 13055 = 0x32FF = 50. Byte 0x50 is the same in old dumps, so they read right
    ("f20A", "h", "f", 0x20A, 0x52),     # frames in the +0x265 action
    ("catch_left", "h", "f", 0x2A4, 0x54),
    ("meet", "h", "f", 0x1EC, 0x56),     # the frame the mover meets the ball
    ("f265", "B", "f", 0x265, 0x58),     # the attack (pass/block) action
    ("air", "B", "f", 0x22E, 0x59),
    ("catch", "B", "f", 0x2AC, 0x5A),    # committed catch type
    ("f266", "B", "f", 0x266, 0x5B),     # 8011D5F4 needs it set
    ("f269", "B", "f", 0x269, 0x5C),     # the hit test needs it clear
    ("slot", "B", "f", 0x2C9, 0x5D),     # his pad slot (press = ai+0xCC + 2*slot)
    ("press", "B", None, None, 0x5E),    # ai+0xCC+2*slot at frame end: 1 = written but not taken by 8011D5F4
    ("ai36C", "B", "a", 0x36C, 0x5F),    # the hit test needs it clear
    ("b23E", "B", "f", 0x23E, 0x60), ("b23F", "B", "f", 0x23F, 0x61), ("b240", "B", "f", 0x240, 0x62),
    ("b242", "B", "f", 0x242, 0x63), ("b243", "B", "f", 0x243, 0x64), ("b24C", "B", "f", 0x24C, 0x65),
    ("b246", "B", "f", 0x246, 0x66),     # the busy gate 8012BA58's inputs
    ("f268", "B", "f", 0x268, 0x67),     # 8011D5F4's "take without a press" flag
]
BUSY = ("b23E", "b23F", "b240", "b242", "b243", "b24C", "b246")
LOGP = None                        # the ring's address, set by apply()


def _copy(a, kind, src_reg, off, dst):
    if kind == "f":
        a.lfs(0, off, src_reg).stfs(0, dst, 9)
    elif kind == "h":
        a.lha(0, off, src_reg).sth(0, dst, 9)
    else:
        a.lbz(0, off, src_reg).stb(0, dst, 9)


def _fielder_sub(a):
    """Local subroutine "fld": r10 = the fielder with id*4 in r4 (the 3-array chain); cr0 eq when none. Uses r5."""
    a.label("fld")
    for arr in FIELDERS:
        a.load_addr(5, arr).lwzx(10, 5, 4).cmpwi(10, 0)
        a.word(0x4C820020)                                          # bnelr
    a.blr()


def log_stub(at, logp, dbg):
    """r8 = header, r9 = record, r10 = F (fielder 0, then the chaser), r11 = game, r12 = ai."""
    a = Asm(at)
    a.lis(12, ha(level5.FLAG)).lbz(12, lo(level5.FLAG), 12).cmpwi(12, 2).bne("out")
    a.lwz(11, GAME, 13).cmpwi(11, 0).beq("out")
    a.li(4, 0).bl("fld").beq("out")                                 # fielder 0 of the fielding side
    a.lbz(0, 0x2E, 10).cmpwi(0, 0).bne("out")                       # the level 6 CPU fields
    for off in DEFENSE:
        a.lwz(12, off, 13).cmpwi(12, 0).bne("ai")
    a.b("out")
    a.label("ai")
    a.load_addr(8, logp)
    a.lha(0, 0x2A4C, 11).cmpwi(0, 0).blt("live")
    a.lwz(3, TAILW, 8).cmpwi(3, 0).ble("out")                       # held: TAIL more frames, then stop
    a.addi(3, 3, -1).stw(3, TAILW, 8).b("rec")
    a.label("live")
    a.li(0, TAIL).stw(0, TAILW, 8)
    a.label("rec")
    a.lwz(5, 4, 8).addi(0, 5, 1).stw(0, 4, 8)
    a.lwz(6, 8, 8).addi(6, 6, -1).word((31 << 26) | (5 << 21) | (6 << 16) | (6 << 11) | (28 << 1))  # and r6,r5,r6
    a.mulli(6, 6, REC).add(9, 8, 6).addi(9, 9, HDR)
    a.li(0, 0).mr(6, 9).addi(7, 9, DBG_AT)                          # clear the own part (the ring is reused)
    a.label("clr")
    a.stw(0, 0, 6).addi(6, 6, 4).cmpw(6, 7).blt("clr")
    a.lwz(3, TICK, 13)
    regs = {"t": 3, "g": 11, "a": 12}
    for name, kind, src, off, dst in FIELDS:
        if src in regs:
            _copy(a, kind, regs[src], off, dst)
    a.lwz(3, 0x9C, 11).cmpwi(3, 0).beq("bown")                      # the ball position (FUN_800AC748)
    a.lbz(0, 0x2C, 3).cmpwi(0, 0).beq("bown")
    a.addi(3, 3, 0x18).b("bpos")
    a.label("bown")
    a.addi(3, 11, 0xA4)
    a.label("bpos")
    for i in range(3):
        a.lfs(0, 4 * i, 3).stfs(0, 0x10 + 4 * i, 9)
    a.li(0, -1).stb(0, 0x0E, 9)
    a.lha(4, 0x2D8, 12).cmplwi(4, 8).bgt("dbg")                     # the chaser
    a.slwi(4, 4, 2).bl("fld").beq("dbg")
    for name, kind, src, off, dst in FIELDS:
        if src == "f":
            _copy(a, kind, 10, off, dst)
    a.lbz(4, 0x2C9, 10).slwi(4, 4, 1).add(4, 4, 12).lbz(0, 0xCC, 4).stb(0, 0x5E, 9)   # his press slot
    a.mr(3, 10).addi(4, 9, 0x40).bl(NEAREST_MATE).stb(3, 0x0E, 9)   # (leaf: keeps r9-r12)
    a.label("dbg")
    a.load_addr(5, dbg).addi(7, 5, defense_dbg.SIZE).mr(6, 9)
    a.label("cp")
    a.lwz(0, 0, 5).stw(0, DBG_AT, 6).addi(5, 5, 4).addi(6, 6, 4).cmpw(5, 7).blt("cp")
    a.label("out")
    a.word(ORIG)
    a.b(HOOK + 4)
    _fielder_sub(a)
    return a


def apply(dol, code, data):
    """With LOG_ENTRIES: the ring in `data`, the stub in `code` (charbuild Spaces), hook 0x801327C0. Needs
    level5.alloc(data) first. LOG_ENTRIES = 0: nothing. Returns log lines."""
    global LOGP
    if not LOG_ENTRIES:
        LOGP = None
        return []
    assert LOG_ENTRIES & (LOG_ENTRIES - 1) == 0, "LOG_ENTRIES: a power of 2"
    assert level5.FLAG is not None, "level5.alloc(data) first"
    assert REC >= DBG_AT + defense_dbg.SIZE
    got = dol.u32(HOOK)
    assert got == ORIG, f"0x{HOOK:08X}: 0x{got:08X}, expected 0x{ORIG:08X}"
    dbg = defense_dbg.alloc(data)
    LOGP = data.put(MAGIC + struct.pack(">3I", 0, LOG_ENTRIES, REC) + bytes(HDR - 16 + LOG_ENTRIES * REC), align=32)
    at = code.here + (-code.here % 4)
    blob = log_stub(at, LOGP, dbg).assemble()
    assert code.put(blob, align=4) == at
    dol.w32(HOOK, branch(HOOK, at))
    return [f"cpu defense log (level 6): 0x{HOOK:08X} -> 0x{at:08X} ({len(blob)} B code); {LOG_ENTRIES} x {REC} B "
            f"records at 0x{LOGP:08X} ({HDR + LOG_ENTRIES * REC} B data; scripts/read_defense_log.py)"]
