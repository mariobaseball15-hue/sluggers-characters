"""Tiny PowerPC (Gekko) assembler for hook stubs: just the instructions we emit.

Build code with an Asm at a fixed address; labels resolve on assemble().
"""
import struct


def _r(x):
    return int(x[1:]) if isinstance(x, str) else x


def ha(v):
    return ((v + 0x8000) >> 16) & 0xFFFF


def lo(v):
    return v & 0xFFFF


def d_form(op, rt, ra, imm):
    return (op << 26) | (_r(rt) << 21) | (_r(ra) << 16) | (imm & 0xFFFF)


def x_form(rt, ra, rb, xo, rc=0):
    return (31 << 26) | (_r(rt) << 21) | (_r(ra) << 16) | (_r(rb) << 11) | (xo << 1) | rc


def branch(src, dst, link=False):
    off = dst - src
    assert -0x2000000 <= off < 0x2000000 and off % 4 == 0, f"b out of range {src:#x}->{dst:#x}"
    return (18 << 26) | (off & 0x03FFFFFC) | int(link)


def bc(src, dst, bo, bi):
    off = dst - src
    assert -0x8000 <= off < 0x8000 and off % 4 == 0
    return (16 << 26) | (bo << 21) | (bi << 16) | (off & 0xFFFC)


COND = {"beq": (12, 2), "bne": (4, 2), "blt": (12, 0), "bge": (4, 0), "bgt": (12, 1), "ble": (4, 1)}


class Asm:
    def __init__(self, base):
        self.base, self.items, self.labels = base, [], {}

    @property
    def pc(self):
        return self.base + 4 * len(self.items)

    def label(self, name):
        self.labels[name] = self.pc

    def _emit(self, fn):
        self.items.append(fn)
        return self

    def word(self, w):
        return self._emit(lambda pc: w)

    # arithmetic / loads / stores
    def lis(self, rt, imm): return self.word(d_form(15, rt, 0, imm))
    def addi(self, rt, ra, imm): return self.word(d_form(14, rt, ra, imm))
    def li(self, rt, imm): return self.addi(rt, 0, imm)
    def mulli(self, rt, ra, imm): return self.word(d_form(7, rt, ra, imm))
    def lbz(self, rt, d, ra): return self.word(d_form(34, rt, ra, d))
    def lhz(self, rt, d, ra): return self.word(d_form(40, rt, ra, d))
    def lwz(self, rt, d, ra): return self.word(d_form(32, rt, ra, d))
    def stb(self, rs, d, ra): return self.word(d_form(38, rs, ra, d))
    def sth(self, rs, d, ra): return self.word(d_form(44, rs, ra, d))
    def stw(self, rs, d, ra): return self.word(d_form(36, rs, ra, d))
    def cmplwi(self, ra, imm, cr=0): return self.word((10 << 26) | (cr << 23) | (_r(ra) << 16) | (imm & 0xFFFF))
    def cmpwi(self, ra, imm, cr=0): return self.word((11 << 26) | (cr << 23) | (_r(ra) << 16) | (imm & 0xFFFF))
    def add(self, rt, ra, rb): return self.word(x_form(rt, ra, rb, 266))
    def lbzx(self, rt, ra, rb): return self.word(x_form(rt, ra, rb, 87))
    def lwzx(self, rt, ra, rb): return self.word(x_form(rt, ra, rb, 23))
    def lhzx(self, rt, ra, rb): return self.word(x_form(rt, ra, rb, 279))
    def stbx(self, rs, ra, rb): return self.word(x_form(rs, ra, rb, 215))
    def mr(self, ra, rs): return self.word(x_form(rs, ra, rs, 444))  # or ra,rs,rs
    def slwi(self, ra, rs, n): return self.word((21 << 26) | (_r(rs) << 21) | (_r(ra) << 16) | (n << 11) | (0 << 6) | ((31 - n) << 1))

    def ori(self, ra, rs, imm): return self.word(d_form(24, rs, ra, imm))
    def andi_(self, ra, rs, imm): return self.word(d_form(28, rs, ra, imm))  # andi. (sets cr0)
    def stwu(self, rs, d, ra): return self.word(d_form(37, rs, ra, d))
    def mflr(self, rt): return self.word(0x7C0802A6 | (_r(rt) << 21))
    def mtlr(self, rs): return self.word(0x7C0803A6 | (_r(rs) << 21))
    def divwu(self, rt, ra, rb): return self.word(x_form(rt, ra, rb, 459))
    def mullw(self, rt, ra, rb): return self.word(x_form(rt, ra, rb, 235))
    def subf(self, rt, ra, rb): return self.word(x_form(rt, ra, rb, 40))   # rt = rb - ra
    def rlwinm(self, ra, rs, sh, mb, me):
        return self.word((21 << 26) | (_r(rs) << 21) | (_r(ra) << 16) | (sh << 11) | (mb << 6) | (me << 1))
    def clrlwi(self, ra, rs, n): return self.rlwinm(ra, rs, 0, n, 31)
    def lha(self, rt, d, ra): return self.word(d_form(42, rt, ra, d))
    def cmpw(self, ra, rb, cr=0): return self.word((31 << 26) | (cr << 23) | (_r(ra) << 16) | (_r(rb) << 11))
    def mtctr(self, rs): return self.word(x_form(rs, 0, 0, 467) | (0x120 << 11))
    def mflr(self, rt): return self.word(x_form(rt, 0, 0, 339) | (0x100 << 11))
    def mtlr(self, rs): return self.word(x_form(rs, 0, 0, 467) | (0x100 << 11))
    def stwu(self, rs, d, ra): return self.word(d_form(37, rs, ra, d))
    def nop(self): return self.word(0x60000000)
    def bctrl(self): return self.word(0x4E800421)

    # floating point (registers as "f3" or 3)
    def lfs(self, ft, d, ra): return self.word(d_form(48, ft, ra, d))
    def stfs(self, fs, d, ra): return self.word(d_form(52, fs, ra, d))
    def _a(self, xo, t, a, b, c):
        return self.word((59 << 26) | (_r(t) << 21) | (_r(a) << 16) | (_r(b) << 11) | (_r(c) << 6) | (xo << 1))
    def fdivs(self, t, a, b): return self._a(18, t, a, b, 0)
    def fsubs(self, t, a, b): return self._a(20, t, a, b, 0)
    def fadds(self, t, a, b): return self._a(21, t, a, b, 0)
    def fmuls(self, t, a, c): return self._a(25, t, a, 0, c)
    def fmadds(self, t, a, c, b): return self._a(29, t, a, b, c)   # t = a*c + b
    def fnmsubs(self, t, a, c, b): return self._a(30, t, a, b, c)  # t = b - a*c
    def fneg(self, t, b): return self.word((63 << 26) | (_r(t) << 21) | (_r(b) << 11) | (40 << 1))
    def frsqrte(self, t, b): return self.word((63 << 26) | (_r(t) << 21) | (_r(b) << 11) | (26 << 1))   # ~1/sqrt(b), 1/32 exact
    def fctiwz(self, t, b): return self.word((63 << 26) | (_r(t) << 21) | (_r(b) << 11) | (15 << 1))
    def stfd(self, fs, d, ra): return self.word(d_form(54, fs, ra, d))
    def fmr(self, t, b): return self.word((63 << 26) | (_r(t) << 21) | (_r(b) << 11) | (72 << 1))
    def fcmpo(self, a, b, cr=0):
        return self.word((63 << 26) | (cr << 23) | (_r(a) << 16) | (_r(b) << 11) | (32 << 1))

    def load_addr(self, rt, addr):
        return self.lis(rt, ha(addr)).addi(rt, rt, lo(addr))

    # control flow (targets are addresses or label names)
    def _target(self, t):
        return (lambda: self.labels[t]) if isinstance(t, str) else (lambda: t)

    def b(self, t, link=False):
        tgt = self._target(t)
        return self._emit(lambda pc: branch(pc, tgt(), link))

    def bl(self, t): return self.b(t, link=True)
    def blr(self): return self.word(0x4E800020)

    def __getattr__(self, name):
        if name in COND:
            bo, bi = COND[name]
            def cond(t, cr=0):
                tgt = self._target(t)
                return self._emit(lambda pc: bc(pc, tgt(), bo, bi + 4 * cr))
            return cond
        raise AttributeError(name)

    def assemble_word(self):
        (w,) = struct.unpack(">I", self.assemble())
        return w

    def assemble(self):
        return b"".join(struct.pack(">I", fn(self.base + 4 * i) & 0xFFFFFFFF) for i, fn in enumerate(self.items))
