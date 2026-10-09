"""Clamber solo buddy jump: a Clamber Jump fielder (fielding ability abilities.CLAMBER_JUMP, 14) on the wall
buddy-jumps when A is pressed, aimed at the point where the ball crosses the wall. See docs/buddy-jump.md.
Stock Clamber (9) is left as the game has it (Nick, 2026-09-26: two abilities, either one per character; it was every
Clamber fielder).

INIT_HOOK 0x8010B9B4, in the fielder init FUN_8010b7a4, replaces `cmplwi r0,9` (r0 = the fielding ability from the
fielder's getter; `bne` next skips `+0x222 = 3`, "can clamber"): equal for 9 or CLAMBER_JUMP, so a Clamber Jump
fielder climbs exactly as a Clamber one. It is the only place the game tests for Clamber: the A-button action reads
+0x222, and CPU fielders never clamber.

Two hooks, emitted as Gecko C2 codes (`gecko()`) or placed in a DOL section by build_buddy_clamber.py:

WALL_HOOK 0x8012B378, in FUN_8012b29c (Clamber state 2, on the wall), replaces `li r0,3`, the value
the next instruction `stb r0,0x24a(r25)` stores (3 = push off). r25 = fielder, r31 = fielding-control
block. A fielder whose ability (his getter, vtable +0x3C) isn't CLAMBER_JUMP, or who holds the ball
(game+0x2A4C): push off as before. Otherwise turn the wall height into a jump
height, leave Clamber, record the jumper as its own buddy (ctrl+0x32A = +0x32C = own id; the cut-in
reads it), call the buddy launch FUN_8011cf24, and leave r0 = 0.

AIM_HOOK 0x8011D00C, in FUN_8011cf24, replaces `bl FUN_8011d20c` (the launch solver; this is its only
caller). r30 = fielder. It runs the solver, then for a solo jump (ctrl+0x32A == +0x32C == own id):
  - finds the first ball-path frame f where the ball is as far from home as the fielder (it reaches the
    wall line; the air catch FUN_8012249c fails once the ball is over the stands),
  - sets horizontal velocity = (ball[f] - fielder) / f,
  - sets vertical velocity so the jump height at frame f = ball height - reach/2, using the jump
    physics of FUN_8011c770, h(f) = h0 + f*vy - g*f*(f+1)/2; if that would peak before f, it aims for
    f - (peak hold frames) instead, since FUN_8011c770 holds the peak that long; clamped to
    [0, the buddy + Super Jump launch speed (1.2)],
  - drops the into-wall part of the horizontal velocity, because the jump's move collision
    (FUN_8011688c) cancels all horizontal motion on any wall contact.
"""
import struct
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
from dol import Dol  # noqa: E402
from ppc import Asm  # noqa: E402

INIT_HOOK, INIT_ORIG = 0x8010B9B4, 0x28000009   # cmplwi r0,9
CLAMBER, CLAMBER_JUMP = 9, 14                   # abilities.CLAMBER / CLAMBER_JUMP
WALL_HOOK, WALL_ORIG = 0x8012B378, 0x38000003   # li r0,3
AIM_HOOK, AIM_ORIG = 0x8011D00C, 0x48000201     # bl 0x8011d20c
BUDDY_LAUNCH, SOLVER = 0x8011CF24, 0x8011D20C
JUMP_TABLE = 0x80625BD8
R2 = 0x8079EDC0                                  # _SDA2_BASE_ (set at 0x80004224)
R2_ZERO, R2_HALF, R2_ONE = -0x7600, -0x7F90, -0x7F94  # 0.0f, 0.5f, 1.0f


def init_hook(base):
    a = Asm(base)
    a.cmplwi(0, CLAMBER).beq("end")      # stock Clamber: eq
    a.cmplwi(0, CLAMBER_JUMP)            # Clamber Jump: eq too (else ne, as for any other ability)
    a.label("end")
    return a


def wall_hook(base, ability=CLAMBER_JUMP):
    """ability None: every Clamber fielder jumps (the old Gecko code)."""
    a = Asm(base)
    if ability is not None:              # only this ability jumps (r25, r31 survive the call; r0, r3-r12 don't)
        a.lwz(12, 0, 25).lwz(12, 0x3C, 12).mtctr(12).mr(3, 25).bctrl()
        a.clrlwi(0, 3, 24).cmplwi(0, ability).bne("dismount")
    a.lwz(4, -0x1D94, 13)                # game state
    a.lha(4, 0x2A4C, 4)                  # fielder id holding the ball (-1 = none)
    a.lbz(5, 0x21C, 25)                  # this fielder's id
    a.cmpw(4, 5).beq("dismount")
    a.lfs(0, 0x120, 25)                  # absolute clamber height
    a.lfs(1, 0xD8, 25)                   # ground height under the fielder
    a.fsubs(0, 0, 1).stfs(0, 0x12C, 25)  # jump height is relative to the ground
    a.li(0, 0)
    a.stb(0, 0x24B, 25)                  # wall-move direction
    a.sth(0, 0x1E6, 25)                  # clamber timer
    a.stb(0, 0x24A, 25)                  # leave clamber state
    a.sth(5, 0x32A, 31).sth(5, 0x32C, 31)  # buddy record: jumper = partner = self
    a.mr(3, 25)
    a.lis(12, BUDDY_LAUNCH >> 16).ori(12, 12, BUDDY_LAUNCH & 0xFFFF).mtctr(12).bctrl()
    a.li(0, 0)                           # the original stb then writes clamber state 0
    a.b("end")
    a.label("dismount")
    a.li(0, 3)                           # original push-off
    a.label("end")
    return a


def aim_hook(base):
    a = Asm(base)
    a.lis(12, SOLVER >> 16).ori(12, 12, SOLVER & 0xFFFF).mtctr(12).bctrl()  # original solver
    for off in (-0x1D14, -0x1D10, -0x1D18):   # fielding-control block: first non-null, as the game does
        a.lwz(3, off, 13).cmpwi(3, 0).bne("ctrl")
    a.lwz(3, -0x1D1C, 13)
    a.label("ctrl")
    a.lha(4, 0x32A, 3).lha(5, 0x32C, 3).cmpw(4, 5).bne("end")
    a.lbz(5, 0x21C, 30).cmpw(4, 5).bne("end")        # not a solo jump by this fielder
    # f1,f2 = fielder x,z; f3,f4 = wall normal, flipped if needed to point into the field (toward home)
    a.lfs(1, 0x4, 30).lfs(2, 0xC, 30).lfs(3, 0x118, 30).lfs(4, 0x11C, 30)
    a.lfs(0, R2_ZERO, 2)
    a.fmuls(5, 1, 3).fmadds(5, 2, 4, 5).fcmpo(5, 0).ble("n_ok")
    a.fneg(3, 3).fneg(4, 4)
    a.label("n_ok")
    a.fmuls(6, 1, 1).fmadds(6, 2, 2, 6)             # f6 = fielder distance^2 from home
    a.lfs(12, R2_ONE, 2).fmr(10, 12)                 # f10 = frame number as a float
    a.lwz(4, -0x1D94, 13).addi(4, 4, 0x42C + 0x14)   # &ballpath[1].x, 0x14 bytes per frame
    a.li(5, 1)
    a.label("scan")
    a.lfs(7, 0, 4).lfs(8, 8, 4)
    a.fmuls(9, 7, 7).fmadds(9, 8, 8, 9).fcmpo(9, 6).bge("cross")
    a.addi(4, 4, 0x14).addi(5, 5, 1).fadds(10, 10, 12)
    a.cmpwi(5, 0x1E0).blt("scan")
    a.b("slide")                                     # never reaches the wall: keep the solver's aim
    a.label("cross")
    a.fsubs(7, 7, 1).fsubs(8, 8, 2)
    a.fdivs(7, 7, 10).fdivs(8, 8, 10)
    a.stfs(7, 0x74, 30).stfs(8, 0x7C, 30)
    a.lbz(6, -0x1658, 13).slwi(6, 6, 6)              # mode * 0x40
    a.load_addr(8, JUMP_TABLE).add(8, 8, 6)          # r8 = this mode's rows
    a.lbz(7, 0x223, 30).slwi(7, 7, 4).add(7, 7, 8)   # r7 = row: launch vy, gravity, -, peak hold frames
    a.lfs(11, 4, 7).lfs(7, 0xC, 7)                   # f11 = gravity per frame, f7 = hold frames
    a.lfs(8, 4, 4)                                   # ball height at frame f
    a.lfs(9, 0x190, 30).lfs(13, R2_HALF, 2)
    a.fnmsubs(8, 9, 13, 8)                           # target = ball y - reach/2
    a.lfs(9, 0x12C, 30).fsubs(8, 8, 9)               # f8 = target - h0
    a.label("vy")
    a.fdivs(9, 8, 10)
    a.fadds(5, 10, 12).fmuls(5, 5, 11)               # g * (f + 1)
    a.fmadds(9, 5, 13, 9)                            # vy = (target - h0)/f + g(f+1)/2
    # If that peaks before frame f, the jump holds at the peak for the hold frames first, so aim
    # for f - hold instead (once: f7 = f afterwards makes the second test fail).
    a.fmuls(5, 11, 10).fcmpo(9, 5).bge("clamp")
    a.fcmpo(10, 7).ble("clamp")
    a.fsubs(10, 10, 7).fmr(7, 10).b("vy")
    a.label("clamp")
    a.fcmpo(9, 0).bge("lo_ok").fmr(9, 0)
    a.label("lo_ok")
    # cap at the buddy + Super Jump launch (row 3, 1.2 in mode 0): the plain buddy 1.0 fell ~3.7 short
    # of a Bowser home run in a Dolphin trace; gravity and hold still come from the jump's own row
    a.lfs(11, 3 * 0x10, 8).fcmpo(9, 11).ble("hi_ok").fmr(9, 11)
    a.label("hi_ok")
    a.stfs(9, 0x78, 30)
    a.label("slide")                                 # drop the into-wall part of (vx, vz)
    a.lfs(7, 0x74, 30).lfs(8, 0x7C, 30)
    a.fmuls(9, 7, 3).fmadds(9, 8, 4, 9).fcmpo(9, 0).bge("end")
    a.fnmsubs(7, 9, 3, 7).fnmsubs(8, 9, 4, 8)
    a.stfs(7, 0x74, 30).stfs(8, 0x7C, 30)
    a.label("end")
    return a


HOOKS = [(INIT_HOOK, INIT_ORIG, init_hook), (WALL_HOOK, WALL_ORIG, wall_hook), (AIM_HOOK, AIM_ORIG, aim_hook)]


def words(asm):
    blob = asm.assemble()
    return [int.from_bytes(blob[i:i + 4], "big") for i in range(0, len(blob), 4)]


def gecko():
    out = []
    for hook, _, fn in HOOKS:
        w = words(fn(0))
        w += [0] if len(w) % 2 else [0x60000000, 0]
        out.append(f"C2{hook & 0x1FFFFFF:06X} {len(w) // 2:08X}")
        out += [f"{w[i]:08X} {w[i + 1]:08X}" for i in range(0, len(w), 2)]
    return "\n".join(out)


# Each encoder checked against the same instruction in main.dol: address -> (emit, text there).
REFERENCE = {
    0x8012B378: (lambda a: a.li(0, 3), "li r0,0x3"),
    0x8012B37C: (lambda a: a.stb(0, 0x24A, 25), "stb r0,0x24a(r25)"),
    0x8012B35C: (lambda a: a.mr(3, 31), "or r3,r31,r31"),
    0x8012B304: (lambda a: a.lfs(30, 0x120, 3), "lfs f30,0x120(r3)"),
    0x8012B4A8: (lambda a: a.stfs(30, 0x120, 25), "stfs f30,0x120(r25)"),
    0x8012B2C8: (lambda a: a.lwz(4, -0x1D94, 13), "lwz r4,-0x1d94(r13)"),
    0x8012B3F8: (lambda a: a.fsubs(30, 30, 0), "fsubs f30,f30,f0"),
    0x80063090: (lambda a: a.cmpw(20, 0), "cmpw r20,r0"),
    0x800634E4: (lambda a: a.mtctr(12), "mtctr r12"),
    0x800634E8: (lambda a: a.bctrl(), "bctrl"),
    0x800ACFEC: (lambda a: a.lha(0, 0x2A4C, 30), "lha r0,0x2a4c(r30)"),
    0x800C95E8: (lambda a: a.sth(29, 0x32A, 31), "sth r29,0x32a(r31)"),
    0x80582F94: (lambda a: a.ori(12, 12, 1), "ori r12,r12,0x1"),
    0x805A38E0: (lambda a: a.fmadds(8, 2, 12, 5), "fmadds f8,f2,f12,f5"),
    0x80562388: (lambda a: a.fnmsubs(4, 4, 1, 3), "fnmsubs f4,f4,f1,f3"),
    0x80063450: (lambda a: a.fmuls(0, 1, 0), "fmuls f0,f1,f0"),
    0x8008F1F4: (lambda a: a.fcmpo(1, 0), "fcmpo cr0,f1,f0"),
    0x8011CF94: (lambda a: a.lbz(3, 0x4, 3), "lbz r3,0x4(r3)"),
    0x8011D034: (lambda a: a.slwi(0, 4, 6), "rlwinm r0,r4,0x6,0x0,0x19"),
    0x8011D01C: (lambda a: a.slwi(5, 28, 4), "rlwinm r5,r28,0x4,0x0,0x1b"),
    0x8011D03C: (lambda a: a.add(0, 5, 0), "add r0,r5,r0"),
    0x8011D050: (lambda a: a.fadds(2, 2, 3), "fadds f2,f2,f3"),
    0x8011D048: (lambda a: a.fsubs(3, 3, 1), "fsubs f3,f3,f1"),
}
# Encoders with no instance picked above; verify() finds one by text in analysis/listing.tsv.
BY_TEXT = {
    "fdivs": lambda a, t, x, y: a.fdivs(t, x, y),
    "fneg": lambda a, t, x: a.fneg(t, x),
    "fmr": lambda a, t, x: a.fmr(t, x),
    "cmpwi": lambda a, r, i: a.cmpwi(r, i),
    "lha": lambda a, t, d, r: a.lha(t, d, r),
}


def _by_text(root, dol):
    import re
    ok = True
    listing = (root / "analysis/listing.tsv").read_text(encoding="utf8").splitlines()
    for name, fn in BY_TEXT.items():
        for line in listing:
            addr, _, _, text = line.split("\t", 3)
            if not text.startswith(name + " "):
                continue
            args = [int(x, 0) for x in re.findall(r"-?0x[0-9a-f]+|-?\d+", text[len(name):])]
            enc = words(fn(Asm(int(addr, 16)), *args))[0]
            real = dol.u32(int(addr, 16))
            ok &= real == enc
            print(f"{'ok ' if real == enc else 'BAD'} {addr} {text:28s} ours {enc:08X} dol {real:08X}")
            break
    return ok


def verify(root):
    import game_source
    dol = Dol(game_source.root() / "sys/main.dol")
    ok = True
    for addr, (fn, text) in REFERENCE.items():
        enc = words(fn(Asm(addr)))[0]
        real = dol.u32(addr)
        ok &= real == enc
        print(f"{'ok ' if real == enc else 'BAD'} {addr:08X} {text:28s} ours {enc:08X} dol {real:08X}")
    ok &= _by_text(root, dol)
    for off, want in ((R2_ZERO, 0.0), (R2_HALF, 0.5), (R2_ONE, 1.0)):
        got = struct.unpack(">f", dol.read(R2 + off, 4))[0]
        ok &= got == want
        print(f"{'ok ' if got == want else 'BAD'} r2{off:+#x} = {got}")
    for hook, orig, _ in HOOKS:
        ok &= dol.u32(hook) == orig
        print(f"{'ok ' if dol.u32(hook) == orig else 'BAD'} hook {hook:08X} holds {orig:08X}")
    return ok


if __name__ == "__main__":
    root = Path(__file__).resolve().parent.parent
    good = verify(root)
    print()
    print(gecko())
    sys.exit(0 if good else 1)


def apply(dol, base):
    """Patch both hooks into `dol` (a scripts/dol.Dol) with their bodies at `base`, and return the code
    bytes to place there (the caller adds them as a text section, or appends them to its own code block
    at `base`). Each body is followed by a branch back to the instruction after its hook."""
    code = b""
    for hook, orig, fn in HOOKS:
        at = base + len(code)
        got = dol.u32(hook)
        assert got == orig, f"0x{hook:08X}: expected {orig:08X}, found {got:08X}"
        dol.w32(hook, 0x48000000 | ((at - hook) & 0x3FFFFFC))
        body = fn(at).assemble()
        ret = at + len(body)
        code += body + (0x48000000 | ((hook + 4 - ret) & 0x3FFFFFC)).to_bytes(4, "big")
    return code
