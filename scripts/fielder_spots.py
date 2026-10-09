"""Fielder spots (docs/fielder-spots.md): drag a team's fielders (1B, 2B, 3B, SS, LF, CF, RF; never P or C) to
new default spots with the pointer, holding A+B, on the pre-game positions screen and, for the fielding team's
human, on the in-match "Change the defense" screen (a shift). Every place the game puts a fielder at his home
spot then uses the dragged spot instead.

Coordinates. The field diagram is not to scale (the infield is drawn large, and 1B / 3B sit below the pitcher), so
screen <-> field goes through a triangle mesh: the 8 stock spots (P and the 7 draggable positions) at their cells'
diagram positions, plus a hull (fair territory, >= 10 in front of the plate, short of the fences). Inside a
triangle the map is affine; a point outside the hull lands on its edge, then a point inside the arc (a circle on
the DIAGRAM, bowing up just above the pitcher's cell) moves radially out to it; the arc is drawn there. Spots are
kept in Mario-Stadium units and warped to the stadium at match time like stadium_dimensions' warp (past r 47,
scaled by the live CF spot), so a spot set before the stadium is picked still fits a smaller or bigger park.

Hooks (stock words asserted; none shared with bench.py):
  F1 FUN_8011595c entry (the home spot, docs/fielder-ai-state.md s5; its only callers are the pre-pitch
     FUN_80113820 and CField::vf10's per-play teleport): after the stock result, ids 2..8 of the fielding team
     (game+0x2B) that have a spot get it, but only when the stock result is the plain home spot (0x80627C90 or
     row 0 / column 0 of the infield table, preset 0 of the outfield one); holding a runner, bunt charge and steal
     cover stay stock
  F2 FUN_80088b2c entry (every field cell widget's per-frame setup, called by the Base / Sel / Kao / Hand / Star /
     Aishou draws of Shubi_local): cells 2..8 get their widget matrix translation (+0x3C / +0x4C) = the spot's
     diagram position - the stock cell position (0 without a spot)
  F3 COrderSelectTask::vf08 0x800804E4 (positions screen, per controller, after the pointer / cursor update and
     before the button tests): the drag; skips the stock button handling (to 0x80080A70) while it acts
  F4 FUN_8031e430 0x8031E694 (defense screen input, state 2, same point): the drag; skips to 0x8031E84C
  F5 CExhiMemOrdTask vtable +0x10 (InitMembers, 0x806A17A0): a new Exhibition setup clears the pre-game spots
  F6 CExhiMemOrdTask vtable +0x14 (ApplyToGame, 0x806A17A4): the pre-game spots become the match's (valid)
  F7 CGameMode::SetMember 0x8046DE08 (every mode's roster commit): the match spots are invalid until F6 again
  F8 FUN_80320158 entry (the defense task's constructor): a new defense-screen visit
  F9 FUN_803207c0 entry (the defense screen's OK apply; r3 = the visit, whose +8 is the team): the visit's spots
     replace the team's match spots
"""
import struct

from ppc import Asm, bc, x_form

SECTION = 0x2000

# ---------------- tunables ----------------
HOLD = 0x0C00          # KPAD A (0x800) + B (0x400): both held drags
SNAP = 2.5             # a spot dropped this close to the stock one is stock again (units: Mario Stadium, ~feet/4)
# The arc (Nick: "an arc a little bit behind the pitcher and not let them go in front of it"; showcase-17: "It needs
# to look like an arc"): a circle on the diagram (layout units, y down) centred (0, ARC_CY) below the pitcher's cell,
# its top ARC_APEX just above that cell (centre y 8, radius ~16); no dragged cell inside it. 1B / 3B / 2B / SS and the
# outfield cells are outside it; it ends where it meets the field's edge (the hull), beside 1B and 3B.
ARC_APEX, ARC_CY = -12.0, 50.0
ARC_R = ARC_CY - ARC_APEX
ARC_GAP = 3.5          # layout units between dashes along the arc (each is ~4.3 long: they overlap into a line)
DASH_SX, DASH_SY = 0.3, 1.2   # a dash = the text box's U+FF0D scaled (0.8 x 0.1 em of 18 units -> ~4.3 x ~2.2)
R0, CF_MARIO = 47.0, 76.0   # the warp: r <= R0 unchanged, beyond scaled by (CF z live - R0) / (CF_MARIO - R0)
K_MIN, K_MAX = 0.3, 1.6
CF_Z = 0x80628064      # outfield preset 0, CF z (stadium_dimensions rewrites the presets per match)
# The mesh: (name, field (x, z) in Mario units, +z to CF; diagram (x, y) in layout units, y down). The first 8 are
# the stock spots (P, then positions 2..8 at index pos - 1) at their cells (element 0xB frames via the position ->
# frame table 0x8063CAF0); the hull (with the arc, the allowed region): z >= 10 between the foul lines (|x| <= 0.95 z - 1, 1st
# base is (18.3, 19.25)), out to r 66 on the lines, 74 at 30 degrees, 81 at 15, 86 in centre (Mario's fences: 79 at
# the poles, 89.8 at 31.5, 95..97 at 19, 100.3 in centre; Bob-omb's poles 67.1 warp to 59.6).
VERTS = (
    ("P", (0.0, 18.6), (0, 8)),
    ("1B", (18.5, 22.0), (69, 38)),
    ("2B", (11.0, 36.0), (54, -17)),
    ("3B", (-18.5, 22.0), (-71, 38)),
    ("SS", (-11.0, 36.0), (-56, -17)),
    ("LF", (-34.0, 60.0), (-81, -72)),
    ("CF", (0.0, 76.0), (0, -73)),
    ("RF", (34.0, 60.0), (79, -73)),
    ("home left", (-8.5, 10.0), (-24, 52)),
    ("home right", (8.5, 10.0), (24, 52)),
    ("1B line", (19.9, 22.0), (84, 40)),
    ("3B line", (-19.9, 22.0), (-84, 40)),
    ("RF line", (44.9, 48.4), (92, -32)),
    ("LF line", (-44.9, 48.4), (-92, -32)),
    ("right 30", (37.0, 64.1), (92, -80)),
    ("left 30", (-37.0, 64.1), (-92, -80)),
    ("right 15", (21.0, 78.2), (48, -88)),
    ("left 15", (-21.0, 78.2), (-48, -88)),
    ("centre", (0.0, 86.0), (0, -90)),
)
# Delaunay of the field points (frozen); check_mesh() asserts every triangle keeps its orientation on the diagram
TRIS = ((7, 16, 6), (5, 4, 6), (4, 5, 13), (5, 15, 13), (14, 7, 12), (7, 14, 16), (9, 0, 8), (11, 4, 13),
        (17, 5, 6), (17, 15, 5), (0, 2, 4), (2, 7, 6), (4, 2, 6), (7, 2, 12), (3, 0, 4), (11, 3, 4), (0, 3, 8),
        (3, 11, 8), (16, 18, 6), (18, 17, 6), (1, 0, 9), (1, 2, 0), (10, 1, 9), (2, 10, 12), (1, 10, 2))
# the hull (the allowed region), counter-clockwise on the field; a pointer off it is moved to its nearest point
HULL = (8, 9, 10, 12, 14, 16, 18, 17, 15, 13, 11)
FRAME_TABLE = 0x8063CAF0
TEXT = 0x8043D62C            # FUN_8043d62c(str, -1, 1, 0, layout, +0xBC, 0, element; stack: mtx, colour, ...), as
TEXT_ELEMENT = 0x0E          # bench.py's DH / base labels draw (element 0x0E: a text box at (0, 0))
BASE_RET = 0x80088D70        # FUN_80088b2c's return address in CS2d_CharaBase::vf08 (the cell's disc)     # position -> element 0xB frame (4, 3, 0, 1, 2, 5, 6, 7, 8)
# element 0xB (dir 119 file 19) frame positions, checked against the layout by test_fielder_spots.py
FRAMES = ((69, 38), (54, -17), (-71, 38), (0, 66), (0, 8), (-56, -17), (-81, -72), (0, -73), (79, -73))

# ---------------- data (offsets from D) ----------------
VALID, PEND, MOK, C3 = 0, 1, 2, 3        # match spots valid; a defense visit to set up; its drags allowed; cell +0xC3
MTASK, MGROUND, MTEAM = 4, 8, 0xC        # the defense visit: task, its field group (task+0x30), its team
DRAG = 0x10                              # [3] x 0x20: positions screen p 0 / 1, the defense screen
D_ON, D_ENTRY, D_PX, D_PY, D_SX, D_SY, D_POS, D_IDX = 0, 4, 8, 0xC, 0x10, 0x14, 0x18, 0x1C
ENTRY = 0xC                              # {u32 set, f32 x, f32 z}
TEAM_SIZE = 7 * ENTRY
EDIT = 0x80                              # [2 teams][7]: the positions screen's
LIVE = EDIT + 2 * TEAM_SIZE              # [2][7]: the match's
MEDIT = LIVE + 2 * TEAM_SIZE             # [7]: the defense visit's (its team)
MAPS = MEDIT + TEAM_SIZE + 4             # map(): best {m, wa, wb, wc, triangle pointer}
CONST = (MAPS + 0x14 + 15) & ~15
CONSTS = ("zero", "one", "far", "big", "acy", "half", "onehalf", "arcin2", "snap2", "arcr", "arcr2", "eps", "r0", "r0sq", "inv", "kmin", "kmax")
WORLD = CONST + 4 * len(CONSTS)
SCREEN = WORLD + 8 * len(VERTS)
TRI = SCREEN + 8 * len(VERTS)
HULLS = TRI + 4 * len(TRIS)             # HULL reversed: counter-clockwise on the diagram (y down)
def _arc_count():
    import math
    return 1 + math.ceil(2 * _arc_half_angle() * ARC_R / ARC_GAP)


def _in_hull(q):
    pts = [VERTS[i][2] for i in reversed(HULL)]              # counter-clockwise on the diagram (y down)
    return all((b[0] - a[0]) * (q[1] - a[1]) - (b[1] - a[1]) * (q[0] - a[0]) >= 0
               for a, b in zip(pts, pts[1:] + pts[:1]))


def _arc_half_angle():
    """The arc's half-angle from its top: where it leaves the hull (the field's front / foul-line edges)."""
    import math
    lo, hi = 0.0, math.pi
    for _ in range(60):
        m = (lo + hi) / 2
        lo, hi = (m, hi) if _in_hull((ARC_R * math.sin(m), ARC_CY - ARC_R * math.cos(m))) else (lo, m)
    return lo


ARC_DOTS = _arc_count()
ARC = (HULLS + len(HULL) + 3) & ~3          # ARC_DOTS x {f32 x, y, then the dash's 2x2: a, b, c, d}
DASH = ARC + 0x18 * ARC_DOTS                 # U+FF0D fullwidth hyphen (UTF-16, 0-terminated): the arc's mark
DATA_SIZE = (DASH + 4 + 31) & ~31

# ---------------- stock ----------------
GAME = 0x801319BC            # -> the game flow (+0x2B fielding roster team)
SQRT = 0x8053C74C            # f1 = sqrt(f1)
SET_ENTRY = 0x8006345C       # CMemberSlot::Set(slot, id)
PAD_HELD, PAD_TRIG = 0x8045D408, 0x8045D41C   # (*(r13-0x2F8), ctrl) -> buttons
WIDE = 0x805CBAC0            # FUN_8008e478's widescreen test
HALF_WIDE, HALF_W, HALF_H, ASPECT = 0x80796E64, 0x80796E68, 0x80796E6C, 0x807A3C08   # 426.67, 320, 224, _gAspect
SOUND, SOUND_PAD, PAD_SPEAKER = 0x804B2714, 0x80547244, 0x80631FC0   # positions screen sounds (as the stock)
MATCH_SOUND = 0x80386D10     # defense screen sounds (f1 = [r2-0x5600], r3 = *(r13-0x7F4), id, ctrl, 1)
SND_GRAB, SND_DROP, SND_STOCK = 0x4F, 0x4E, 0x50
HOME_TABLE, INFIELD, OUTFIELD = 0x80627C90, 0x80627CD8, 0x80628058
INIT_MEMBERS, APPLY_TO_GAME = (0x806A17A0, 0x802C91E0), (0x806A17A4, 0x802C9280)   # (vtable slot, stock)

# hook sites: (address, stock word)
F1 = (0x8011595C, 0x9421FFD0)    # stwu r1,-0x30(r1)
F2 = (0x80088B2C, 0x9421FFF0)    # stwu r1,-0x10(r1)
F3 = (0x800804E4, 0x806DFD08)    # lwz r3,-0x2f8(r13)
F3_SKIP = 0x80080A70
F4 = (0x8031E694, 0x80BB0014)    # lwz r5,0x14(r27)
F4_SKIP = 0x8031E84C
F7 = (0x8046DE08, 0x88030A90)    # lbz r0,0xa90(r3)
F8 = (0x80320158, 0x9421FFE0)    # stwu r1,-0x20(r1)
F9 = (0x803207C0, 0x9421FFC0)    # stwu r1,-0x40(r1)


class A(Asm):
    def extsb(self, ra, rs): return self.word(x_form(rs, ra, 0, 954))

    def bdnz(self, t):
        tgt = self._target(t)
        return self._emit(lambda pc: bc(pc, tgt(), 16, 0))

    def enter(self, n, locals_=0x20):
        """A frame saving LR and r31..r(32-n); locals at 0x08..0x08+locals_."""
        f = (8 + locals_ + 4 * n + 15) & ~15
        self._frames = getattr(self, "_frames", [])
        self._frames.append((n, f))
        self.stwu("r1", -f, "r1").mflr("r0").stw("r0", f + 4, "r1")
        for i in range(n):
            self.stw(31 - i, f - 4 - 4 * i, "r1")
        return self

    def leave(self):
        n, f = self._frames.pop()
        for i in range(n):
            self.lwz(31 - i, f - 4 - 4 * i, "r1")
        return self.lwz("r0", f + 4, "r1").mtlr("r0").addi("r1", "r1", f).blr()

    def c(self, fr, name, dreg):
        """lfs fr = constant `name` (dreg = D)."""
        return self.lfs(fr, CONST + 4 * CONSTS.index(name), dreg)


def check_mesh():
    """Every triangle has the same, non-zero orientation on the field and on the diagram (y flipped), so the map
    is one to one; the stock vertices are the cells' frames."""
    def orient(p, q, r):
        return (q[0] - p[0]) * (r[1] - p[1]) - (r[0] - p[0]) * (q[1] - p[1])
    for t in TRIS:
        w = orient(*(VERTS[i][1] for i in t))
        s = orient(*((VERTS[i][2][0], -VERTS[i][2][1]) for i in t))
        assert w > 1e-6 and s > 1e-6, f"fielder_spots: triangle {[VERTS[i][0] for i in t]} folds"
    for pts in ([VERTS[i][1] for i in HULL], [VERTS[i][2] for i in reversed(HULL)]):   # convex, CCW
        for k in range(len(pts)):
            assert orient(pts[k - 2], pts[k - 1], pts[k]) > 1e-6, "fielder_spots: the hull is not convex"
    assert set(HULL) == set(range(8, len(VERTS))), "fielder_spots: the hull is the non-stock vertices"
    order = (4, 3, 0, 1, 2, 5, 6, 7, 8)
    for pos in (0,) + tuple(range(2, 9)):
        assert VERTS[0 if pos == 0 else pos - 1][2] == FRAMES[order[pos]], f"position {pos}: not at its cell"


def mesh_map(p, src, dst):
    """Python twin of map() for points inside the mesh: src / dst = 1 (field) or 2 (diagram)."""
    def orient(a, b, c):
        return (b[0] - a[0]) * (c[1] - a[1]) - (c[0] - a[0]) * (b[1] - a[1])
    best = None
    for t in TRIS:
        A, B, C = (VERTS[i][src] for i in t)
        d = orient(A, B, C)
        w = (orient(p, B, C) / d, orient(A, p, C) / d)
        w = (w[0], w[1], 1 - w[0] - w[1])
        if best is None or min(w) > min(best[1]):
            best = (t, w)
    t, w = best
    return tuple(sum(wi * VERTS[i][dst][k] for wi, i in zip(w, t)) for k in (0, 1))


def arc_points():
    """The arc's dashes: ([field points], [diagram points], [dash 2x2 {a, b, c, d}: along the arc]), evenly spaced
    from end to end (the field points are the diagram points through the mesh: where the clamp puts a cell)."""
    import math
    h = _arc_half_angle()
    diag, rot = [], []
    for k in range(ARC_DOTS):
        t = -h + 2 * h * k / (ARC_DOTS - 1)
        diag.append((ARC_R * math.sin(t), ARC_CY - ARC_R * math.cos(t)))
        c, s_ = math.cos(t), math.sin(t)             # the tangent (cos t, sin t), y down
        rot.append((DASH_SX * c, -DASH_SY * s_, DASH_SX * s_, DASH_SY * c))
    return [mesh_map(q, 2, 1) for q in diag], diag, rot


def code(base, D):
    a = A(base)
    L = a.label
    n = [0]

    def uniq(s):
        n[0] += 1
        return f"{s}_{n[0]}"

    def D_(reg):
        a.load_addr(reg, D)

    def fmin(dst, src):                      # dst = min(dst, src)
        k = uniq("min")
        a.fcmpo(src, dst).bge(k).fmr(dst, src)
        L(k)

    def fmax(dst, src):
        k = uniq("max")
        a.fcmpo(src, dst).ble(k).fmr(dst, src)
        L(k)

    # ---- map(src r3, dst r4, x f1, y f2) -> (f1, f2): the mesh, clamped to its hull (leaf; r5-r12, f0-f13)
    L("map")
    D_("r12")
    a.addi("r5", "r12", TRI).li("r6", len(TRIS)).c("f13", "far", "r12")
    L("map_loop")
    for reg, off in (("r8", 0), ("r9", 1), ("r10", 2)):
        a.lbz(reg, off, "r5").slwi(reg, reg, 3).add(reg, reg, "r3")
    a.lfs("f3", 0, "r8").lfs("f4", 4, "r8").lfs("f5", 0, "r9").lfs("f6", 4, "r9").lfs("f7", 0, "r10").lfs("f8", 4, "r10")
    a.fsubs("f9", "f5", "f3").fsubs("f10", "f8", "f4").fmuls("f9", "f9", "f10")
    a.fsubs("f10", "f7", "f3").fsubs("f11", "f6", "f4").fnmsubs("f9", "f10", "f11", "f9")        # d
    a.fsubs("f10", "f5", "f1").fsubs("f11", "f8", "f2").fmuls("f10", "f10", "f11")
    a.fsubs("f11", "f7", "f1").fsubs("f12", "f6", "f2").fnmsubs("f10", "f11", "f12", "f10").fdivs("f10", "f10", "f9")   # wa
    a.fsubs("f11", "f7", "f1").fsubs("f12", "f4", "f2").fmuls("f11", "f11", "f12")
    a.fsubs("f12", "f3", "f1").fsubs("f0", "f8", "f2").fnmsubs("f11", "f12", "f0", "f11").fdivs("f11", "f11", "f9")     # wb
    a.c("f12", "one", "r12").fsubs("f12", "f12", "f10").fsubs("f12", "f12", "f11")                     # wc
    a.fmr("f0", "f10")
    fmin("f0", "f11")
    fmin("f0", "f12")
    a.fcmpo("f0", "f13").ble("map_next")
    a.fmr("f13", "f0").stfs("f10", MAPS + 4, "r12").stfs("f11", MAPS + 8, "r12").stfs("f12", MAPS + 0xC, "r12")
    a.stw("r5", MAPS + 0x10, "r12")
    L("map_next")
    a.addi("r5", "r5", 4).addi("r6", "r6", -1).cmpwi("r6", 0).bne("map_loop")
    a.c("f0", "zero", "r12").lfs("f10", MAPS + 4, "r12").lfs("f11", MAPS + 8, "r12").lfs("f12", MAPS + 0xC, "r12")
    for fr in ("f10", "f11", "f12"):
        fmax(fr, "f0")
    a.fadds("f9", "f10", "f11").fadds("f9", "f9", "f12")
    for fr in ("f10", "f11", "f12"):
        a.fdivs(fr, fr, "f9")
    a.lwz("r5", MAPS + 0x10, "r12")
    for reg, off in (("r8", 0), ("r9", 1), ("r10", 2)):
        a.lbz(reg, off, "r5").slwi(reg, reg, 3).add(reg, reg, "r4")
    for out, o in (("f1", 0), ("f2", 4)):
        a.lfs("f3", o, "r8").fmuls(out, "f3", "f10")
        a.lfs("f3", o, "r9").fmadds(out, "f3", "f11", out)
        a.lfs("f3", o, "r10").fmadds(out, "f3", "f12", out)
    a.blr()

    # ---- clamp(hull r3, vertices r4, n r5, x f1, y f2) -> (f1, f2): the nearest point of the (convex, CCW) hull
    #      when outside it (leaf; r5-r12, f0, f3-f13)
    L("clamp")
    D_("r12")
    a.c("f13", "big", "r12").li("r11", 0).mtctr("r5")
    a.add("r6", "r3", "r5").lbz("r6", -1, "r6").slwi("r6", "r6", 3).add("r6", "r6", "r4")
    a.lfs("f3", 0, "r6").lfs("f4", 4, "r6")                                  # a = the last vertex
    L("cl_loop")
    a.lbz("r6", 0, "r3").slwi("r6", "r6", 3).add("r6", "r6", "r4").lfs("f5", 0, "r6").lfs("f6", 4, "r6")   # b
    a.fsubs("f7", "f5", "f3").fsubs("f8", "f6", "f4").fsubs("f9", "f1", "f3").fsubs("f10", "f2", "f4")
    a.fmuls("f0", "f7", "f10").fnmsubs("f0", "f8", "f9", "f0").c("f12", "zero", "r12").fcmpo("f0", "f12")
    a.bge("cl_in").li("r11", 1)
    L("cl_in")
    a.fmuls("f0", "f9", "f7").fmadds("f0", "f10", "f8", "f0")               # (p - a).(b - a)
    a.fmuls("f12", "f7", "f7").fmadds("f12", "f8", "f8", "f12").fdivs("f0", "f0", "f12")   # t
    a.c("f12", "zero", "r12")
    fmax("f0", "f12")
    a.c("f12", "one", "r12")
    fmin("f0", "f12")
    a.fmadds("f7", "f7", "f0", "f3").fmadds("f8", "f8", "f0", "f4")         # q = a + t (b - a)
    a.fsubs("f9", "f1", "f7").fsubs("f10", "f2", "f8").fmuls("f0", "f9", "f9").fmadds("f0", "f10", "f10", "f0")
    a.fcmpo("f0", "f13").bge("cl_next")
    a.fmr("f13", "f0").fmr("f11", "f7").stfs("f8", MAPS, "r12")
    L("cl_next")
    a.fmr("f3", "f5").fmr("f4", "f6").addi("r3", "r3", 1).bdnz("cl_loop")
    a.cmpwi("r11", 0).beq("cl_out").fmr("f1", "f11").lfs("f2", MAPS, "r12")
    L("cl_out")
    a.blr()

    # ---- to_screen(entry r3, pos r4) -> (f1, f2): the spot's diagram position (the cell's without a spot)
    L("to_screen")
    D_("r12")
    a.lwz("r0", 0, "r3").cmpwi("r0", 0).beq("ts_stock")
    a.lfs("f1", 4, "r3").lfs("f2", 8, "r3").addi("r3", "r12", WORLD).addi("r4", "r12", SCREEN).b("map")
    L("ts_stock")
    a.slwi("r4", "r4", 3).add("r4", "r4", "r12").lfs("f1", SCREEN - 8, "r4").lfs("f2", SCREEN - 4, "r4").blr()

    # ---- arc(f1, f2) -> (f1, f2): a diagram point inside the arc moves radially out to it (leaf)
    L("arc")
    D_("r12")
    a.c("f3", "acy", "r12").fsubs("f4", "f2", "f3")                       # dy
    a.fmuls("f7", "f1", "f1").fmadds("f7", "f4", "f4", "f7")
    a.c("f8", "arcr2", "r12").fcmpo("f7", "f8").bge("arc_out")
    a.c("f8", "eps", "r12").fcmpo("f7", "f8").bge("arc_norm")
    a.c("f1", "zero", "r12").c("f8", "arcr", "r12").fsubs("f2", "f3", "f8").blr()   # at the centre: the top
    L("arc_norm")
    a.frsqrte("f5", "f7")                         # 1/sqrt(d2), refined twice (Newton): y = y (1.5 - 0.5 d2 y^2)
    for _ in range(2):
        a.fmuls("f6", "f5", "f5").fmuls("f6", "f6", "f7").c("f8", "half", "r12").fmuls("f6", "f6", "f8")
        a.c("f8", "onehalf", "r12").fsubs("f6", "f8", "f6").fmuls("f5", "f5", "f6")
    a.c("f8", "arcr", "r12").fmuls("f5", "f5", "f8")                        # R / d
    a.fmuls("f1", "f1", "f5").fmadds("f2", "f4", "f5", "f3")
    L("arc_out")
    a.blr()

    # ---- arcdraw(Base widget r3 of cell 2): the arc's dashes on its field, with the field's matrix and the cell's
    #      alpha (the widget's +0x60 is last frame's: its +0x30 translation (ours) x the field x the cell's frame)
    MTX, COL, OX, FM, LF = 0x20, 0x50, 0x70, 0x78, 0xA0
    L("arcdraw")
    a.stwu("r1", -LF, "r1").mflr("r0").stw("r0", LF + 4, "r1").stw("r31", LF - 4, "r1").stw("r29", LF - 8, "r1")
    a.mr("r31", "r3")
    for i in range(0, 0x30, 4):
        a.lwz("r0", 0x60 + i, "r31").stw("r0", MTX + i, "r1")
    D_("r12")
    for o, t30, fr in ((0, 0x3C, SCREEN + 8), (4, 0x4C, SCREEN + 0xC)):   # the field's origin = t - ours - frame
        a.lfs("f1", MTX + 0xC + 4 * o, "r1").lfs("f2", t30, "r31").fsubs("f1", "f1", "f2")
        a.lfs("f2", fr, "r12").fsubs("f1", "f1", "f2").stfs("f1", OX + o, "r1")
    for i, o in enumerate((0, 4, 0x10, 0x14)):   # the field's 2x2 (x, y rows / columns), kept
        a.lfs("f1", MTX + o, "r1").stfs("f1", FM + 4 * i, "r1")
    a.lwz("r0", 0xA4, "r31").stw("r0", COL, "r1").lis("r0", 0x3F80)
    a.stw("r0", COL + 4, "r1").stw("r0", COL + 8, "r1").stw("r0", COL + 0xC, "r1")
    a.lwz("r0", 0xB4, "r31").stw("r0", COL + 0x10, "r1")
    a.li("r29", 0)
    L("ad_loop")
    a.cmpwi("r29", ARC_DOTS).bge("ad_out")
    D_("r12")
    a.mulli("r0", "r29", 0x18).add("r11", "r12", "r0")
    a.lfs("f5", ARC + 8, "r11").lfs("f6", ARC + 0xC, "r11").lfs("f7", ARC + 0x10, "r11").lfs("f8", ARC + 0x14, "r11")
    for row in range(2):                          # the dash's 2x2 = the field's x (a b / c d): along the arc
        a.lfs("f3", FM + 8 * row, "r1").lfs("f4", FM + 8 * row + 4, "r1")
        a.fmuls("f1", "f3", "f5").fmadds("f1", "f4", "f7", "f1").stfs("f1", MTX + 0x10 * row, "r1")
        a.fmuls("f1", "f3", "f6").fmadds("f1", "f4", "f8", "f1").stfs("f1", MTX + 0x10 * row + 4, "r1")
    a.lfs("f1", ARC, "r11").lfs("f2", OX, "r1").fadds("f1", "f1", "f2").stfs("f1", MTX + 0xC, "r1")
    a.lfs("f1", ARC + 4, "r11").lfs("f2", OX + 4, "r1").fadds("f1", "f1", "f2").stfs("f1", MTX + 0x1C, "r1")
    a.addi("r0", "r1", MTX).stw("r0", 8, "r1").addi("r0", "r1", COL).stw("r0", 0xC, "r1")
    a.li("r0", 0).stw("r0", 0x10, "r1").stw("r0", 0x1C, "r1").li("r0", -1).stw("r0", 0x14, "r1")
    a.lbz("r0", 0xC3, "r31").stw("r0", 0x18, "r1")
    a.addi("r3", "r12", DASH).li("r4", -1).li("r5", 1).li("r6", 0)
    a.lwz("r7", 0xB8, "r31").lwz("r8", 0xBC, "r31").li("r9", 0).li("r10", TEXT_ELEMENT).bl(TEXT)
    a.addi("r29", "r29", 1).b("ad_loop")
    L("ad_out")
    a.lwz("r31", LF - 4, "r1").lwz("r29", LF - 8, "r1").lwz("r0", LF + 4, "r1").mtlr("r0").addi("r1", "r1", LF).blr()

    # ---- warp(f1, f2) -> (f1, f2): Mario units -> this stadium (past R0, scaled by the live CF spot)
    L("warp")
    a.enter(0)
    a.stfs("f1", 8, "r1").stfs("f2", 0xC, "r1")
    D_("r12")
    a.fmuls("f3", "f1", "f1").fmadds("f3", "f2", "f2", "f3").c("f4", "r0sq", "r12").fcmpo("f3", "f4").ble("warp_out")
    a.fmr("f1", "f3").bl(SQRT).stfs("f1", 0x10, "r1")
    D_("r12")
    a.load_addr("r11", CF_Z).lfs("f5", 0, "r11").c("f6", "r0", "r12").fsubs("f5", "f5", "f6").c("f7", "inv", "r12")
    a.fmuls("f5", "f5", "f7")                                        # k
    a.c("f7", "kmin", "r12")
    fmax("f5", "f7")
    a.c("f7", "kmax", "r12")
    fmin("f5", "f7")
    a.lfs("f1", 0x10, "r1").fsubs("f3", "f1", "f6").fmadds("f3", "f3", "f5", "f6").fdivs("f3", "f3", "f1")
    a.lfs("f1", 8, "r1").fmuls("f1", "f1", "f3").lfs("f2", 0xC, "r1").fmuls("f2", "f2", "f3").b("warp_done")
    L("warp_out")
    a.lfs("f1", 8, "r1").lfs("f2", 0xC, "r1")
    L("warp_done")
    a.leave()

    # ---- ptr(ctrl r3) -> r3 on screen, (f1, f2) the pointer (-1..1)  (leaf)
    L("ptr")
    a.lwz("r4", -0x2BC, 13).slwi("r5", "r3", 2).add("r5", "r5", "r4").lwz("r0", 0x94, "r5")
    a.slwi("r5", "r3", 3).add("r5", "r5", "r4").lfs("f1", 0x34, "r5").lfs("f2", 0x38, "r5")
    a.rlwinm("r3", "r0", 31, 31, 31).blr()

    # ---- pscale() -> (f1, f2): layout units per pointer unit, as FUN_8008e478 maps the pointer
    L("pscale")
    a.enter(0)
    D_("r12")
    a.lbz("r0", C3, "r12").cmpwi("r0", 0).beq("ps_narrow")
    a.load_addr("r11", HALF_WIDE).lfs("f1", 0, "r11").b("ps_aspect")
    L("ps_narrow")
    a.bl(WIDE).clrlwi("r3", "r3", 24).load_addr("r11", HALF_W).lfs("f1", 0, "r11").cmplwi("r3", 1).bne("ps_y")
    L("ps_aspect")
    a.load_addr("r11", ASPECT).lfs("f0", 0, "r11").fmuls("f1", "f1", "f0")
    L("ps_y")
    a.load_addr("r11", HALF_H).lfs("f2", 0, "r11")
    a.leave()

    # ---- core(state r3, entry r4, pos r5 (-1: not draggable), held index* r6, held slot* r7, buttons held r8,
    #           pressed r9, ctrl r10) -> r3: 0 stock, 1 swallowed, 2 picked up, 3 dropped, 4 dropped on stock
    L("core")
    a.enter(8)
    for i, r in enumerate(("r3", "r4", "r5", "r6", "r7", "r8", "r9", "r10")):
        a.mr(31 - i, r)                  # r31 state, r30 entry, r29 pos, r28 held*, r27 slot*, r26 held, r25 pressed, r24 ctrl
    a.lbz("r0", D_ON, "r31").cmpwi("r0", 0).beq("core_idle")
    a.andi_("r0", "r26", HOLD).cmpwi("r0", HOLD).bne("core_drop")
    a.mr("r3", "r24").bl("ptr").cmpwi("r3", 0).beq("core_1")
    a.lfs("f3", D_PX, "r31").fsubs("f1", "f1", "f3").lfs("f3", D_PY, "r31").fsubs("f2", "f2", "f3")
    a.stfs("f1", 8, "r1").stfs("f2", 0xC, "r1")
    a.bl("pscale")
    a.lfs("f3", 8, "r1").lfs("f4", D_SX, "r31").fmadds("f1", "f3", "f1", "f4")
    a.lfs("f3", 0xC, "r1").lfs("f4", D_SY, "r31").fmadds("f2", "f3", "f2", "f4")
    D_("r12")
    a.addi("r3", "r12", HULLS).addi("r4", "r12", SCREEN).li("r5", len(HULL)).bl("clamp")
    a.bl("arc")                                  # not in front of the arc, on the diagram (then the hull again)
    D_("r12")
    a.addi("r3", "r12", HULLS).addi("r4", "r12", SCREEN).li("r5", len(HULL)).bl("clamp")
    D_("r12")                                    # pushed out past the field's front edge (below an end of the
    a.c("f3", "acy", "r12").fsubs("f4", "f2", "f3").fmuls("f4", "f4", "f4").fmadds("f4", "f1", "f1", "f4")   # arc):
    a.c("f5", "arcin2", "r12").fcmpo("f4", "f5").bge("core_onarc")                  # that end of the arc
    a.c("f5", "zero", "r12").fcmpo("f1", "f5").bge("core_right")
    a.lfs("f1", ARC, "r12").lfs("f2", ARC + 4, "r12").b("core_onarc")
    L("core_right")
    a.lfs("f1", ARC + 0x18 * (ARC_DOTS - 1), "r12").lfs("f2", ARC + 0x18 * (ARC_DOTS - 1) + 4, "r12")
    L("core_onarc")
    D_("r12")
    a.addi("r3", "r12", SCREEN).addi("r4", "r12", WORLD).bl("map")
    a.lwz("r3", D_ENTRY, "r31").li("r0", 1).stw("r0", 0, "r3").stfs("f1", 4, "r3").stfs("f2", 8, "r3")
    L("core_1")
    a.li("r3", 1).b("core_out")
    L("core_drop")                               # released: stock again if dropped on (or never left) its stock spot
    a.li("r0", 0).stb("r0", D_ON, "r31")
    a.lwz("r3", D_ENTRY, "r31").lwz("r0", 0, "r3").cmpwi("r0", 0).beq("core_4")
    D_("r12")
    a.lwz("r4", D_POS, "r31").slwi("r4", "r4", 3).add("r4", "r4", "r12")
    a.lfs("f1", 4, "r3").lfs("f3", WORLD - 8, "r4").fsubs("f1", "f1", "f3")
    a.lfs("f2", 8, "r3").lfs("f3", WORLD - 4, "r4").fsubs("f2", "f2", "f3")
    a.fmuls("f1", "f1", "f1").fmadds("f1", "f2", "f2", "f1").c("f3", "snap2", "r12").fcmpo("f1", "f3").bge("core_3")
    a.li("r0", 0).stw("r0", 0, "r3")
    L("core_4")
    a.li("r3", 4).b("core_out")
    L("core_3")
    a.li("r3", 3).b("core_out")
    L("core_idle")
    a.cmpwi("r29", 0).blt("core_0")
    a.andi_("r0", "r26", HOLD).cmpwi("r0", HOLD).bne("core_notboth")
    a.lwz("r0", 0, "r28").cmpwi("r0", 0).blt("core_free")
    a.lwz("r4", D_IDX, "r31").cmpw("r0", "r4").bne("core_0")     # holding someone else: stock
    a.li("r0", -1).stw("r0", 0, "r28").mr("r3", "r27").li("r4", -1).bl(SET_ENTRY)   # A picked him up: put back
    L("core_free")
    a.mr("r3", "r24").bl("ptr").cmpwi("r3", 0).beq("core_0")
    a.stfs("f1", D_PX, "r31").stfs("f2", D_PY, "r31")
    a.mr("r3", "r30").mr("r4", "r29").bl("to_screen").stfs("f1", D_SX, "r31").stfs("f2", D_SY, "r31")
    a.stw("r30", D_ENTRY, "r31").stw("r29", D_POS, "r31").li("r0", 1).stb("r0", D_ON, "r31")
    a.li("r3", 2).b("core_out")
    L("core_notboth")                            # B alone on a draggable cell with nothing held: not "back"
    a.andi_("r0", "r25", HOLD & 0x400).beq("core_0")
    a.andi_("r0", "r26", HOLD & 0x800).bne("core_0")
    a.lwz("r0", 0, "r28").cmpwi("r0", 0).blt("core_1")
    L("core_0")
    a.li("r3", 0)
    L("core_out")
    a.leave()

    def sound_id(dst, res, tmp):
        """dst = the sound for core's result res (2 grab, 3 drop, 4 back to stock); 0 none."""
        done = uniq("snd")
        a.li(dst, 0)
        for r_, s in ((2, SND_GRAB), (3, SND_DROP), (4, SND_STOCK)):
            k = uniq("snd")
            a.cmpwi(res, r_).bne(k).li(dst, s).b(done)
            L(k)
        L(done)

    # ---- positions screen (F3): p_drag(task r3, p r4, ctrl r5, pointer index r6) -> r3 non-zero: skip the stock
    L("p_drag")
    a.enter(8)
    a.mr("r31", "r3").mr("r30", "r4").mr("r29", "r5").mr("r28", "r6")
    a.lwz("r3", -0x2F8, 13).mr("r4", "r29").bl(PAD_HELD).mr("r27", "r3")
    a.lwz("r3", -0x2F8, 13).mr("r4", "r29").bl(PAD_TRIG).mr("r26", "r3")
    a.cmplwi("r30", 1).bgt("pd_0")
    D_("r25")
    a.slwi("r3", "r30", 5).add("r3", "r3", "r25").addi("r3", "r3", DRAG).stw("r28", D_IDX, "r3")
    a.li("r5", -1).li("r4", 0)                   # pos, entry
    a.cmpwi("r28", 0x16).blt("pd_core").cmpwi("r28", 0x28).bge("pd_core")
    a.li("r6", 0).addi("r5", "r28", -0x16).cmpwi("r5", 9).blt("pd_t")
    a.li("r6", 1).addi("r5", "r5", -9)
    L("pd_t")
    a.cmpwi("r5", 2).blt("pd_none")
    a.mulli("r6", "r6", TEAM_SIZE).mulli("r4", "r5", ENTRY).add("r4", "r4", "r6").add("r4", "r4", "r25")
    a.addi("r4", "r4", EDIT - 2 * ENTRY).b("pd_core")
    L("pd_none")
    a.li("r5", -1)
    L("pd_core")
    a.slwi("r6", "r30", 2).add("r6", "r6", "r31").addi("r6", "r6", 0x160)
    a.mulli("r7", "r30", 0x14).add("r7", "r7", "r31").addi("r7", "r7", 0x16C)
    a.mr("r8", "r27").mr("r9", "r26").mr("r10", "r29").bl("core")
    a.mr("r24", "r3")
    sound_id("r5", "r24", "r0")
    a.cmpwi("r5", 0).beq("pd_ret")
    a.lwz("r3", -0x158, 13).addi("r3", "r3", 0x33C).addi("r4", "r31", 0x1B0).mr("r6", "r29").bl(SOUND)
    a.lwz("r3", 0x1B0, "r31").cmpwi("r3", 0).beq("pd_ret")
    a.slwi("r4", "r29", 2).load_addr("r5", PAD_SPEAKER).lwzx("r4", "r5", "r4").bl(SOUND_PAD)
    L("pd_ret")
    a.mr("r3", "r24").b("pd_out")
    L("pd_0")
    a.li("r3", 0)
    L("pd_out")
    a.leave()

    L("f3")                                      # 0x800804E4 (r30 task, r22 team of this pad, 0xC(r1) ctrl, r21 pointer)
    a.mr("r3", "r30").mr("r4", "r22").lwz("r5", 0xC, "r1").mr("r6", "r21").bl("p_drag")
    a.cmpwi("r3", 0).bne("f3_skip")
    a.word(F3[1]).b(F3[0] + 4)
    L("f3_skip")
    a.b(F3_SKIP)

    # ---- defense screen (F4): minit(task r3): the visit's team, its spots, whether its human may drag
    L("minit")
    a.enter(2)
    a.mr("r31", "r3")
    D_("r30")
    a.li("r0", 0).stb("r0", PEND, "r30").stb("r0", MOK, "r30").stb("r0", DRAG + 2 * 0x20 + D_ON, "r30")
    a.stw("r31", MTASK, "r30").addi("r0", "r31", 0x30).stw("r0", MGROUND, "r30")
    a.lwz("r4", 0x10, "r31").stw("r4", MTEAM, "r30")       # the team (the visit's +8, FUN_8031e35c's r4; +8 is 0)
    a.addi("r5", "r30", MEDIT).li("r0", 0)
    for i in range(0, TEAM_SIZE, 4):
        a.stw("r0", i, "r5")
    a.cmplwi("r4", 1).bgt("mi_out")
    a.lbz("r0", VALID, "r30").cmpwi("r0", 0).beq("mi_out")
    a.mulli("r6", "r4", TEAM_SIZE).add("r6", "r6", "r30").addi("r6", "r6", LIVE)
    for i in range(0, TEAM_SIZE, 4):
        a.lwz("r0", i, "r6").stw("r0", i, "r5")
    a.bl(GAME).lbz("r0", 0x2B, "r3").lwz("r4", MTEAM, "r30").cmpw("r0", "r4").bne("mi_out")   # the fielding team
    a.lwz("r5", -0xB00, 13).add("r5", "r5", "r4").lbz("r0", 0x16, "r5").extsb("r0", "r0").cmpwi("r0", 0).blt("mi_out")
    a.li("r0", 1).stb("r0", MOK, "r30")                                                         # ... and a human's
    L("mi_out")
    a.leave()

    # m_drag(task r3, pointer index r4, held r5, pressed r6) -> r3 non-zero: skip the stock
    L("m_drag")
    a.enter(6)
    a.mr("r31", "r3").mr("r30", "r4").mr("r29", "r5").mr("r28", "r6")
    D_("r27")
    a.lbz("r0", PEND, "r27").cmpwi("r0", 0).bne("md_init")
    a.lwz("r0", MTASK, "r27").cmpw("r0", "r31").beq("md_go")
    L("md_init")
    a.mr("r3", "r31").bl("minit")
    L("md_go")
    a.lbz("r0", MOK, "r27").cmpwi("r0", 0).beq("md_0")
    a.addi("r3", "r27", DRAG + 2 * 0x20).stw("r30", D_IDX, "r3")
    a.li("r5", -1).li("r4", 0)
    a.cmpwi("r30", 4).blt("md_core").cmpwi("r30", 10).bgt("md_core")
    a.addi("r5", "r30", -2).addi("r4", "r30", -4).mulli("r4", "r4", ENTRY).add("r4", "r4", "r27").addi("r4", "r4", MEDIT)
    L("md_core")
    a.addi("r6", "r31", 0x8C).addi("r7", "r31", 0x94).mr("r8", "r29").mr("r9", "r28").lwz("r10", 0x14, "r31")
    a.bl("core").mr("r26", "r3")
    sound_id("r4", "r26", "r0")
    a.cmpwi("r4", 0).beq("md_ret")
    a.lwz("r3", -0x7F4, 13).lwz("r5", 0x14, "r31").li("r6", 1).lfs("f1", -0x5600, 2).bl(MATCH_SOUND)
    L("md_ret")
    a.mr("r3", "r26").b("md_out")
    L("md_0")
    a.li("r3", 0)
    L("md_out")
    a.leave()

    L("f4")                                      # 0x8031E694 (r27 task, r30 pointer index, r1+8: the pads' buttons)
    a.mr("r3", "r27").mr("r4", "r30").lwz("r7", 0x14, "r27").mulli("r7", "r7", 6).add("r7", "r7", "r1")
    a.lhz("r5", 8, "r7").lhz("r6", 0xA, "r7").bl("m_drag")
    a.cmpwi("r3", 0)
    a.word(F4[1])                                # lwz r5,0x14(r27) (cr0 kept)
    a.bne("f4_skip").b(F4[0] + 4)
    L("f4_skip")
    a.stw("r30", 0x80, "r27").b(F4_SKIP)         # the stock's "last pointer index" store we jumped over

    # ---- F2: the cells (r3 = widget)
    L("cell")
    a.enter(4)
    a.mr("r31", "r3").mr("r28", "r4")
    a.lwz("r30", 0xD4, "r31").cmpwi("r30", 2).blt("cell_out").cmpwi("r30", 8).bgt("cell_out")
    a.lwz("r12", 0xD8, 13).lwz("r12", 0x10, "r12").lwz("r12", 0, "r12")
    a.lbz("r11", 8, "r31").slwi("r11", "r11", 2).lwzx("r29", "r12", "r11").cmpwi("r29", 0).beq("cell_out")
    D_("r12")
    a.lbz("r0", 0xC3, "r31").stb("r0", C3, "r12")
    a.lbz("r0", 0xC, "r29").cmpwi("r0", 1).bne("cell_match")
    a.lbz("r3", 7, "r29").cmplwi("r3", 1).bgt("cell_out")                       # positions screen: its team's
    a.mulli("r3", "r3", TEAM_SIZE).add("r3", "r3", "r12").addi("r3", "r3", EDIT).b("cell_draw")
    L("cell_match")
    a.cmpwi("r0", 0).bne("cell_out")
    a.lbz("r0", PEND, "r12").cmpwi("r0", 0).beq("cell_chk")
    a.addi("r3", "r29", -0x30).bl("minit")                                      # first draw of a defense visit
    D_("r12")
    L("cell_chk")
    a.lwz("r0", MGROUND, "r12").cmpw("r0", "r29").bne("cell_out")
    a.addi("r3", "r12", MEDIT)
    a.lbz("r0", MOK, "r12").cmpwi("r0", 0).beq("cell_have")                    # the arc only where one can drag
    L("cell_draw")                               # the arc: once per field per frame, from cell 2's (1B's) disc,
    a.cmpwi("r30", 2).bne("cell_have")           # while the field is shown
    a.load_addr("r11", BASE_RET).cmpw("r28", "r11").bne("cell_have")
    a.lbz("r0", 0x2F, "r29").cmpwi("r0", 0).beq("cell_have")
    a.stw("r3", 8, "r1").mr("r3", "r31").bl("arcdraw").lwz("r3", 8, "r1")
    L("cell_have")
    a.addi("r4", "r30", -2).mulli("r4", "r4", ENTRY).add("r3", "r3", "r4").mr("r4", "r30").bl("to_screen")
    D_("r12")
    a.slwi("r4", "r30", 3).add("r4", "r4", "r12").lfs("f3", SCREEN - 8, "r4").lfs("f4", SCREEN - 4, "r4")
    a.fsubs("f1", "f1", "f3").fsubs("f2", "f2", "f4").stfs("f1", 0x3C, "r31").stfs("f2", 0x4C, "r31")
    L("cell_out")
    a.leave()

    L("f2")                                      # FUN_80088b2c entry
    a.stwu("r1", -0x20, "r1").mflr("r0").stw("r0", 0x24, "r1").stw("r3", 8, "r1")
    a.mr("r4", "r0").bl("cell")                  # r4 = who called (the disc draws the arc)
    a.lwz("r3", 8, "r1").lwz("r0", 0x24, "r1").mtlr("r0").addi("r1", "r1", 0x20)
    a.word(F2[1]).b(F2[0] + 4)

    # ---- F1: the home spot (FUN_8011595c(fielder, &x, &z))
    L("f1")
    a.enter(5)
    a.mr("r31", "r3").mr("r30", "r4").mr("r29", "r5")
    a.bl("f1_stock")
    D_("r28")
    a.lbz("r0", VALID, "r28").cmpwi("r0", 0).beq("f1_out")
    a.lbz("r27", 0x21C, "r31").cmplwi("r27", 2).blt("f1_out").cmplwi("r27", 8).bgt("f1_out")
    a.bl(GAME).lbz("r3", 0x2B, "r3").cmplwi("r3", 1).bgt("f1_out")
    a.mulli("r3", "r3", TEAM_SIZE).mulli("r4", "r27", ENTRY).add("r3", "r3", "r4").add("r3", "r3", "r28")
    a.addi("r3", "r3", LIVE - 2 * ENTRY).stw("r3", 8, "r1")
    a.lwz("r0", 0, "r3").cmpwi("r0", 0).beq("f1_out")
    a.lfs("f1", 0, "r30").lfs("f2", 0, "r29")
    a.load_addr("r5", HOME_TABLE).slwi("r6", "r27", 3).add("r5", "r5", "r6")
    a.lfs("f3", 0, "r5").lfs("f4", 4, "r5").fcmpo("f1", "f3").bne("f1_t1").fcmpo("f2", "f4").beq("f1_home")
    L("f1_t1")
    a.cmplwi("r27", 6).bge("f1_of")
    a.load_addr("r5", INFIELD).addi("r6", "r27", -2).mulli("r6", "r6", 0x18).add("r5", "r5", "r6").b("f1_cmp")
    L("f1_of")
    a.load_addr("r5", OUTFIELD).addi("r6", "r27", -6).slwi("r6", "r6", 3).add("r5", "r5", "r6")
    L("f1_cmp")
    a.lfs("f3", 0, "r5").lfs("f4", 4, "r5").fcmpo("f1", "f3").bne("f1_out").fcmpo("f2", "f4").bne("f1_out")
    L("f1_home")
    a.lwz("r3", 8, "r1").lfs("f1", 4, "r3").lfs("f2", 8, "r3").bl("warp")
    a.stfs("f1", 0, "r30").stfs("f2", 0, "r29")
    L("f1_out")
    a.leave()
    L("f1_stock")
    a.word(F1[1]).b(F1[0] + 4)

    # ---- F5 / F6 (vtable wrappers), F7, F8, F9
    L("f5")                                      # InitMembers(this): a new Exhibition setup
    a.enter(0)
    a.bl(INIT_MEMBERS[1])
    D_("r12")
    a.li("r0", 0)
    for i in range(0, 2 * TEAM_SIZE, 4):
        a.stw("r0", EDIT + i, "r12")
    for i in range(2):
        a.stb("r0", DRAG + 0x20 * i + D_ON, "r12")
    a.leave()

    L("f6")                                      # ApplyToGame(this): the positions screen's spots are the match's
    a.enter(0)
    a.bl(APPLY_TO_GAME[1])                       # (its SetMember calls clear VALID first: F7)
    D_("r12")
    for i in range(0, 2 * TEAM_SIZE, 4):
        a.lwz("r0", EDIT + i, "r12").stw("r0", LIVE + i, "r12")
    a.li("r0", 1).stb("r0", VALID, "r12")
    a.leave()

    L("f7")                                      # SetMember: any roster commit
    a.load_addr("r12", D).li("r11", 0).stb("r11", VALID, "r12")
    a.word(F7[1]).b(F7[0] + 4)

    L("f8")                                      # the defense task's constructor: a new visit
    a.load_addr("r12", D).li("r11", 1).stb("r11", PEND, "r12").li("r11", 0).stb("r11", MOK, "r12")
    a.stw("r11", MTASK, "r12").stw("r11", MGROUND, "r12").stb("r11", DRAG + 2 * 0x20 + D_ON, "r12")
    a.word(F8[1]).b(F8[0] + 4)

    L("f9")                                      # the defense screen's OK (r3 = the visit, FUN_80320158's object; not
    a.load_addr("r12", D).lbz("r0", MOK, "r12").cmpwi("r0", 0).beq("f9_o")    # the input task minit saw): the shift
    a.lwz("r0", 8, "r3").lwz("r11", MTEAM, "r12").cmpw("r0", "r11").bne("f9_o")   # is the team's (+8: its team)
    a.lwz("r11", MTEAM, "r12").mulli("r11", "r11", TEAM_SIZE).add("r11", "r11", "r12")
    for i in range(0, TEAM_SIZE, 4):
        a.lwz("r0", MEDIT + i, "r12").stw("r0", LIVE + i, "r11")
    L("f9_o")
    a.word(F9[1]).b(F9[0] + 4)
    return a


def initial_data():
    blob = bytearray(DATA_SIZE)
    consts = {"zero": 0.0, "one": 1.0, "far": -1e9, "big": 1e9, "acy": ARC_CY, "half": 0.5, "onehalf": 1.5, "arcin2": (ARC_R - 0.01) ** 2,
              "snap2": SNAP * SNAP, "arcr": ARC_R, "arcr2": ARC_R ** 2, "eps": 1e-4, "r0": R0, "r0sq": R0 * R0, "inv": 1 / (CF_MARIO - R0),
              "kmin": K_MIN, "kmax": K_MAX}
    for i, k in enumerate(CONSTS):
        struct.pack_into(">f", blob, CONST + 4 * i, consts[k])
    for i, (_, w, s) in enumerate(VERTS):
        struct.pack_into(">ff", blob, WORLD + 8 * i, *w)
        struct.pack_into(">ff", blob, SCREEN + 8 * i, *s)
    for i, t in enumerate(TRIS):
        blob[TRI + 4 * i:TRI + 4 * i + 3] = bytes(t)
    blob[HULLS:HULLS + len(HULL)] = bytes(reversed(HULL))
    _, diag, rot = arc_points()
    for i, (q, m) in enumerate(zip(diag, rot)):
        struct.pack_into(">6f", blob, ARC + 0x18 * i, *q, *m)
    struct.pack_into(">2H", blob, DASH, 0xFF0D, 0)
    return bytes(blob)


def _patch(dol, addr, expect, new):
    got = dol.u32(addr)
    assert got == expect, f"fielder_spots: 0x{addr:08X} expected {expect:08X}, found {got:08X}"
    dol.w32(addr, new)


def apply(dol, region):
    """Patch `dol`; data and code go into `region` (charbuild Space)."""
    check_mesh()
    assert bytes(dol.read(FRAME_TABLE, 9)) == bytes((4, 3, 0, 1, 2, 5, 6, 7, 8)), "position -> frame table"
    D = region.here + (-len(region.blob) % 32)
    base = D + DATA_SIZE
    a = code(base, D)
    text = a.assemble()
    assert region.put(initial_data() + text) == D
    labels = a.labels
    br = lambda site, lab: Asm(site).b(labels[lab]).assemble_word()   # noqa: E731
    for (site, word), lab in ((F1, "f1"), (F2, "f2"), (F3, "f3"), (F4, "f4"), (F7, "f7"), (F8, "f8"), (F9, "f9")):
        _patch(dol, site, word, br(site, lab))
    for (slot, fn), lab in ((INIT_MEMBERS, "f5"), (APPLY_TO_GAME, "f6")):
        _patch(dol, slot, fn, labels[lab])
    return [f"fielder spots: A+B drag on the positions and defense screens, code+data 0x{DATA_SIZE + len(text):x} B "
            f"at 0x{D:08X} (data) / 0x{base:08X} (code)"]
