"""Level 4 CPU defensive substitutions (Nick, 2026-09-27): the level 4 CPU brings in one of its best pitchers, never a
captain for being a captain, and then re-arranges its fielders for chemistry. Levels 1-3 stay stock. Research:
docs/cpu-ai-weaknesses.md section 4.

Level: ctl = *(r13-0x1D58) (0x80794468), the fielding side's u32 ctl+8+side*4; 0 is level 4 (the hardest). The side
is G+0x2D in FUN_800C3C88 and task+0x2D in FUN_80134BE8, the same index the stock code passes to the lineup calls.

PITCH 0x800C3E24 (`mulli r11,r31,0x4fe`), FUN_800C3C88 right after its two candidate passes (fresh: stamina >= 10 and
+0x366 == 0; else recovered: stamina >= 10), before the captain tier. Not level 4: the replaced mulli and back to
0x800C3E28 (stock; only r12 and cr0 are touched, both rewritten before use). Level 4: the stub replaces tiers 1-3 and
returns through the function's epilogue 0x800C3F70. On entry r3 = candidate count (low byte), the slots are bytes at
r1+0x20, r29 = ctl, r30 = G, r31 = roster team. Timing stays stock (stamina <= 0 at 0x800C3CBC).
  score = 16 * displayed pitching (+0x1C) + (charge speed (+0x22) - 100) / 4 + curve (+0x24) / 8, at least 1, times
  clamp(stamina / max stamina, 1/2, 1) (stamina u16 ST+0x358+rt*0x120+slot*0x20, ST = *(r13-0x1570); max
  FUN_8015C914). Roster records R = *(r13-0x2C8) + rt*0x4FE + slot*0x8E (runtime, so stat edits and bench subs count).
  The catcher (FUN_8015A96C position 1) is dropped unless he is the only candidate. Keep up to 3 by score among those
  >= best * 225/256 (within ~12%), pick one with FUN_80165C14(*(r13-0x1578), k), then as stock: ctl+0x18 =
  FUN_8015A96C(L, G+0x2D, slot), r3 = 1. Captain-class (+7) gets nothing.

FIELD 0x80134D04 (`li r0,3`), FUN_80134BE8 (defense state 0x1D) sub-state 2 right after the CPU's bl 0x8015AB50 (the
pitcher swap). FUN_8015AAE0 has already backed up the old positions, so extra FUN_8015AB50(L, side, a, b) swaps are
re-placed by FUN_801536CC in sub-state 6 like a human's multi-swap OK. r31 = the task is kept; r0 and r3-r12 are free
(li r0,3 / stb / b 0x80134EEC follow). Level 4 only; the stub saves LR and r14-r31 on its own frame.
  The 7 players at 1B..RF (positions 2..8; P 0 and C 1 stay) get a 7x7 weight matrix from FUN_8015C800(rt, a, b)
  (21 calls, symmetric): good (2) = 3, neutral (1 or other) = 1, bad (0) = 0, so in each tier more good pairs always
  win and, at equal good pairs, fewer bad ones. key = 64 * (CF-LF + CF-RF) + 8 * (2B-SS) + (SS-1B + 3B-1B).
  Search: every permutation (7! = 5040 leaves) as nested loops CF, LF, RF, 2B, SS, 1B, 3B, pruned when a partial
  key's upper bound is below the best (never on ties). Best = highest key, then fewest players moved; the current
  field starts as best, so a tie keeps it and nothing moves unless the key strictly improves. Bounded: at most 60k loop
  steps and 5040 leaves; the worst case (all-equal chemistry, nothing pruned) is 683k instructions in the test, about
  1 ms of a 16.7 ms frame on Broadway, once per CPU pitching change (sub-state 2 runs one frame). Apply: selection sort over positions 2..7, one
  FUN_8015AB50 swap per misplaced position (<= 6), both positions always in 2..8.
LEVEL 6 SCORE (Nick, 2026-09-27): at level 6 the score is the curve stat (+0x24, at least 1) instead of the
displayed-pitching formula, with the same stamina scaling and band.
LEVEL 6 (level5.FLAG byte == 2; FLAG 1 = level 5 is unchanged): with 2-3 candidates in the band, the pitch stub builds
slotOf[position] from the lineup (all of 0..8 filled, else level 5's pick), and for each candidate puts the old pitcher
at his position (as the stock FUN_8015AB50 swap does) and calls SEARCH, the field stub's search factored into a
subroutine (same weights, key, order and pruning), for the best key. Only the candidates with the highest key stay in
the pool; the RNG call is as before, over that tied set. Up to 3 searches: worst case ~2.05M instructions for the whole
FUN_800C3C88 in the test (~3.5 ms on Broadway), once per CPU pitching change. The field stub then runs as always.
Test: scripts/test_cpu_subs.py.
"""
import sys
from itertools import permutations
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
import level5  # noqa: E402
from ppc import Asm, branch, d_form, ha, lo, x_form  # noqa: E402

PITCH, PITCH_ORIG = 0x800C3E24, 0x1D7F04FE        # mulli r11,r31,0x4fe
PITCH_BACK, PITCH_RET = 0x800C3E28, 0x800C3F70    # stock tiers; the epilogue (lwz r0,0x44(r1))
PITCH_RET_ORIG = 0x80010044
FIELD, FIELD_ORIG = 0x80134D04, 0x38000003        # li r0,3
FIELD_BACK = FIELD + 4
FIELD_SWAP = 0x80134D00                           # bl 0x8015AB50: the CPU's pitcher swap

GAME = 0x801319BC                                 # G
POS_OF = 0x8015A96C                               # (L, side, slot) -> position
SWAP = 0x8015AB50                                 # (L, side, posA, posB)
CHEM = 0x8015C800                                 # (rt, slotA, slotB) -> 0 bad, 1 neutral, 2 good
MAX_STAMINA = 0x8015C914                          # (rt, slot)
RAND = 0x80165C14                                 # (*(r13-0x1578), n) -> 0..n-1
CTL, LINEUP, RECORDS, STAMINA, RNG = -0x1D58, -0x15A8, -0x2C8, -0x1570, -0x1578
LEVEL = 8                                         # u32 ctl+8+side*4; 0 = level 4

TOP, BAND = 3, 225                                # up to 3, within best * 225/256
LEVELS = (7, 6, 8, 3, 5, 2, 4)                    # search order: CF LF RF 2B SS 1B 3B
WEIGHT = {0: 0, 1: 1, 2: 3}                       # chemistry -> tier weight (other values: neutral)


def stmw(rs, d, ra): return d_form(47, rs, ra, d)
def lmw(rt, d, ra): return d_form(46, rt, ra, d)
def stwx(rs, ra, rb): return x_form(rs, ra, rb, 151)


# --- the reference model (what the stubs compute) ---
def pitch_score(disp, charge, curve, stamina, max_stamina, level6=False):
    base = max(curve if level6 else 16 * disp + (charge >> 2) + (curve >> 3) - 25, 1)   # level 6: curve (Nick)
    f = 256 if max_stamina <= 0 else max(min((stamina << 8) // max_stamina, 256), 128)
    return (base * f) >> 8


def pitch_pool(scores):
    """scores: per candidate (None = dropped catcher). The indices the random pick chooses from, in pick order."""
    s = [-1 if v is None else v for v in scores]
    best = max(s)
    pool = []
    while len(pool) < TOP:
        m = max((v for i, v in enumerate(s) if i not in pool), default=-1)
        if m < 0 or m < (best * BAND) >> 8:
            break
        pool.append(next(i for i, v in enumerate(s) if v == m and i not in pool))
    return pool


def field_key(w, at):
    """at[pos - 2] = player index (0..6 = the player first at 1B..RF)."""
    p = {pos: at[pos - 2] for pos in range(2, 9)}
    return 64 * (w[p[7]][p[6]] + w[p[7]][p[8]]) + 8 * w[p[3]][p[5]] + w[p[5]][p[2]] + w[p[4]][p[2]]


def arrange(chem):
    """chem[i][j] for players 0..6 (the ones at positions 2..8). Returns (at, key, moves), at[pos - 2] = player."""
    w = [[WEIGHT.get(chem[i][j], 1) if i != j else 0 for j in range(7)] for i in range(7)]
    best, key, moves = tuple(range(7)), field_key(w, range(7)), 0
    for perm in permutations(range(7)):          # perm[d] = the player at LEVELS[d], in the stub's loop order
        at = [0] * 7
        for d, pos in enumerate(LEVELS):
            at[pos - 2] = perm[d]
        k, m = field_key(w, at), sum(at[i] != i for i in range(7))
        if k > key or (k == key and m < moves):
            best, key, moves = tuple(at), k, m
    return best, key, moves


def swaps(at):
    """The FUN_8015AB50 position pairs the stub issues to reach `at` (at[pos - 2] = player)."""
    cur, out = list(range(7)), []
    for i in range(6):
        j = cur.index(at[i], i)
        if j != i:
            out.append((i + 2, j + 2))
            cur[i], cur[j] = cur[j], cur[i]
    return out


def level6_key(slot_at, cand, cand_pos, chem):
    """The best field key the field search reaches if slot `cand` (at position cand_pos) pitches: his position goes
    to the old pitcher (slot_at[0]). slot_at: position -> slot; chem(a, b) for slots."""
    s = dict(slot_at)
    if 0 <= cand_pos <= 8:
        s[cand_pos] = slot_at[0]
    players = [s[p] for p in range(2, 9)]
    return arrange([[chem(a, b) for b in players] for a in players])[1]


def level6_pool(pool, keys):
    """Level 6: the pool entries whose chemistry key is the highest, in pool order (a pool of 1 is not evaluated)."""
    if len(pool) < 2:
        return list(pool)
    return [p for p, k in zip(pool, keys) if k == max(keys)]


# --- stubs ---
PF = 0xA0          # pitch stub frame: scores 0x08, pool 0x30, slotOf 0x34, tmp 0x40, keys 0x50, best 0x60, r20-r31 0x70
PSO, PTMP, PKEYS, PBEST, PREGS = 0x34, 0x40, 0x50, 0x60, 0x70


def pitch_stub(at, search):
    a = Asm(at)
    level5.gate(a, 12, "stock", "cpu-subs")                    # level 5 only (r12 and cr0 are free here)
    a.lbz(12, 0x2D, 30).slwi(12, 12, 2).add(12, 12, 29).lwz(12, LEVEL, 12)
    a.cmpwi(12, 0).beq("l4")
    a.label("stock")
    a.word(PITCH_ORIG)                             # stock: mulli r11,r31,0x4fe
    a.b(PITCH_BACK)
    a.label("l4")
    a.stwu(1, -PF, 1).word(stmw(20, PREGS, 1))
    a.clrlwi(20, 3, 24)                            # r20 = n
    a.li(3, 0).cmpwi(20, 0).beq("ret")
    a.addi(21, 1, PF + 0x20)                       # candidate slots
    a.lwz(22, LINEUP, 13).lbz(23, 0x2D, 30)        # L, side
    a.mulli(24, 31, 0x4FE).lwz(0, RECORDS, 13).add(24, 24, 0)
    a.mulli(25, 31, 0x120).lwz(0, STAMINA, 13).add(25, 25, 0)
    a.li(26, 0)
    a.label("score")
    a.lbzx(27, 21, 26)                             # slot
    a.cmpwi(20, 1).beq("rate")                     # the only candidate: even a catcher
    a.mr(3, 22).mr(4, 23).mr(5, 27).bl(POS_OF)
    a.cmpwi(3, 1).bne("rate")
    a.li(28, -1).b("store")                        # the catcher: dropped
    a.label("rate")
    a.lis(3, ha(level5.FLAG)).lbz(3, lo(level5.FLAG), 3).cmpwi(3, 0)   # cr0: level 5 / 6 (kept across the R add)
    a.mulli(3, 27, 0x8E).add(3, 3, 24)             # R
    a.beq("rate5")
    a.lhz(28, 0x24, 3).b("rated")                  # levels 5 / 6: the curve stat (Nick)
    a.label("rate5")
    a.lbz(28, 0x1C, 3).slwi(28, 28, 4)
    a.lhz(0, 0x22, 3).rlwinm(0, 0, 30, 2, 31).add(28, 28, 0)
    a.lhz(0, 0x24, 3).rlwinm(0, 0, 29, 3, 31).add(28, 28, 0)
    a.addi(28, 28, -25)
    a.label("rated")
    a.cmpwi(28, 1).bge("pos").li(28, 1)
    a.label("pos")
    a.mr(3, 31).mr(4, 27).bl(MAX_STAMINA)          # r3 = max stamina
    a.slwi(0, 27, 5).add(4, 25, 0).lhz(4, 0x358, 4)
    a.li(0, 256)
    a.cmpwi(3, 0).ble("scale")
    a.slwi(4, 4, 8).divwu(0, 4, 3)
    a.cmplwi(0, 256).ble("capped").li(0, 256)
    a.label("capped")
    a.cmplwi(0, 128).bge("scale").li(0, 128)
    a.label("scale")
    a.mullw(28, 28, 0).rlwinm(28, 28, 24, 8, 31)   # >> 8
    a.label("store")
    a.slwi(0, 26, 2).addi(3, 1, 8).word(stwx(28, 3, 0))
    a.addi(26, 26, 1).cmpw(26, 20).blt("score")
    a.li(27, 0)                                    # k
    a.label("pick")
    a.li(3, -1).li(4, -1).li(5, 0).addi(6, 1, 8)
    a.label("max")
    a.slwi(0, 5, 2).lwzx(0, 6, 0)
    a.cmpw(0, 3).ble("next")
    a.mr(3, 0).mr(4, 5)
    a.label("next")
    a.addi(5, 5, 1).cmpw(5, 20).blt("max")
    a.cmpwi(4, 0).blt("chosen")
    a.cmpwi(27, 0).bne("band")
    a.mulli(26, 3, BAND).rlwinm(26, 26, 24, 8, 31)  # threshold = best * 225 >> 8
    a.label("band")
    a.cmpw(3, 26).blt("chosen")
    a.lbzx(0, 21, 4).addi(5, 1, 0x30).stbx(0, 5, 27).addi(27, 27, 1)
    a.slwi(0, 4, 2).li(5, -1).word(stwx(5, 6, 0))
    a.cmpwi(27, TOP).blt("pick")
    a.label("chosen")
    a.li(3, 0).cmpwi(27, 0).beq("ret")
    # level 6 (FLAG == 2): keep only the pool entries whose pitching change reaches the best field chemistry
    a.cmpwi(27, 2).blt("roll")
    a.lis(12, ha(level5.FLAG)).lbz(12, lo(level5.FLAG), 12).cmpwi(12, 0).beq("roll")   # levels 5 and 6
    a.li(0, -1).stw(0, PSO, 1).stw(0, PSO + 4, 1).stb(0, PSO + 8, 1)
    a.mulli(6, 23, 0x28).add(6, 6, 22).addi(7, 1, PSO).li(3, 0)
    a.label("entry")                               # slotOf[pos] = slot, lineup entries {s16 slot, s16 pos} at +0xC
    a.slwi(4, 3, 2).add(4, 4, 6).lha(5, 0xE, 4).lhz(0, 0xC, 4)
    a.cmplwi(5, 8).bgt("eskip").stbx(0, 7, 5)
    a.label("eskip")
    a.addi(3, 3, 1).cmpwi(3, 9).blt("entry")
    for pos in range(9):                           # a full field or no chemistry (level 5's pick)
        a.lbz(0, PSO + pos, 1).cmplwi(0, 9).bge("roll")
    a.li(26, 0)                                    # i
    a.label("cand")
    a.lwz(0, PSO, 1).stw(0, PTMP, 1).lwz(0, PSO + 4, 1).stw(0, PTMP + 4, 1).lbz(0, PSO + 8, 1).stb(0, PTMP + 8, 1)
    a.addi(5, 1, 0x30).lbzx(5, 5, 26).mr(3, 22).mr(4, 23).bl(POS_OF)
    a.cmplwi(3, 8).bgt("nopos")                    # his position goes to the old pitcher
    a.lbz(0, PTMP, 1).addi(4, 1, PTMP).stbx(0, 4, 3)
    a.label("nopos")
    a.addi(3, 1, PTMP + 2).mr(4, 31).addi(5, 1, PBEST).bl(search)
    a.slwi(0, 26, 2).addi(4, 1, PKEYS).word(stwx(3, 4, 0))
    a.addi(26, 26, 1).cmpw(26, 27).blt("cand")
    a.li(3, -1).li(5, 0).addi(4, 1, PKEYS)
    a.label("kmax")
    a.slwi(0, 5, 2).lwzx(0, 4, 0).cmpw(0, 3).ble("knext").mr(3, 0)
    a.label("knext")
    a.addi(5, 5, 1).cmpw(5, 27).blt("kmax")
    a.li(5, 0).li(6, 0).addi(7, 1, 0x30)
    a.label("keep")
    a.slwi(0, 5, 2).lwzx(0, 4, 0).cmpw(0, 3).bne("drop")
    a.lbzx(0, 7, 5).stbx(0, 7, 6).addi(6, 6, 1)
    a.label("drop")
    a.addi(5, 5, 1).cmpw(5, 27).blt("keep")
    a.mr(27, 6)
    a.label("roll")
    a.lwz(3, RNG, 13).mr(4, 27).bl(RAND)
    a.addi(5, 1, 0x30).lbzx(5, 5, 3)
    a.mr(3, 22).mr(4, 23).bl(POS_OF)
    a.sth(3, 0x18, 29).li(3, 1)
    a.label("ret")
    a.word(lmw(20, PREGS, 1)).addi(1, 1, PF)
    a.b(PITCH_RET)
    return a


FF = 0xB0                  # field stub frame: slotOf 0x08, used 0x14, best 0x1C, at 0x24, W 0x30, r14-r31 0x68
SLOTS, USED, BEST, AT, W = 0x08, 0x14, 0x1C, 0x24, 0x30


def search_sub(at):
    """SEARCH(r3 = the 7 slots at 1B..RF, r4 = roster team, r5 = out: the best field, 7 bytes in LEVELS order) ->
    r3 = best key, r4 = its moves. Saves LR and r14-r31 on its own frame; r0, r3-r12, ctr, cr are clobbered."""
    a = Asm(at)
    a.stwu(1, -FF, 1).mflr(0).stw(0, FF + 4, 1).word(stmw(14, 0x68, 1))
    a.mr(28, 4).mr(27, 5).li(6, 0)
    a.label("copy")
    a.lbzx(0, 3, 6).addi(7, 6, SLOTS + 2).stbx(0, 1, 7).addi(6, 6, 1).cmpwi(6, 7).blt("copy")
    a.li(20, 0)                                    # W[i][j], i < j, both ways
    a.label("wi")
    a.addi(21, 20, 1)
    a.label("wj")
    a.addi(4, 1, SLOTS + 2).lbzx(5, 4, 21).lbzx(4, 4, 20).mr(3, 28).bl(CHEM)
    a.cmpwi(3, 2).bne("notgood").li(3, 3).b("wset")
    a.label("notgood")
    a.cmpwi(3, 0).beq("wset").li(3, 1)
    a.label("wset")
    a.addi(6, 1, W).slwi(0, 20, 3).add(0, 0, 21).stbx(3, 6, 0).slwi(0, 21, 3).add(0, 0, 20).stbx(3, 6, 0)
    a.addi(21, 21, 1).cmpwi(21, 7).blt("wj")
    a.addi(20, 20, 1).cmpwi(20, 6).blt("wi")
    a.li(0, 0).stw(0, USED, 1).sth(0, USED + 4, 1).stb(0, USED + 6, 1)
    for d, pos in enumerate(LEVELS):
        a.li(0, pos - 2).stb(0, BEST + d, 1)       # best = the current field
    wat = lambda i, j: W + i * 8 + j               # noqa: E731
    a.lbz(3, wat(5, 4), 1).lbz(0, wat(5, 6), 1).add(3, 3, 0).slwi(23, 3, 6)          # CF-LF + CF-RF
    a.lbz(3, wat(1, 3), 1).slwi(3, 3, 3).add(23, 23, 3)                              # 2B-SS
    a.lbz(3, wat(3, 0), 1).add(23, 23, 3).lbz(3, wat(2, 0), 1).add(23, 23, 3)        # SS-1B + 3B-1B
    a.li(24, 0)                                    # best moves
    a.addi(21, 1, W).addi(22, 1, USED)

    def w(rt, ri, rj):                             # rt = W[ri][rj]
        a.slwi(0, ri, 3).add(0, 0, rj).lbzx(rt, 21, 0)

    def level(d):
        rc = 14 + d
        a.li(rc, 0)
        a.label(f"loop{d}")
        a.cmpwi(rc, 7).bge(f"end{d}")
        a.lbzx(0, 22, rc).cmpwi(0, 0).bne(f"next{d}")
        if d == 6:                                 # leaf: 3B chosen
            w(3, 18, 19)
            w(4, 20, 19)
            a.add(3, 3, 4).add(3, 3, 26)           # key
            a.cmpw(3, 23).blt(f"next{d}")
            a.li(4, 0)
            for dd, pos in enumerate(LEVELS):      # moves (cr1: cr0 holds key vs best)
                a.cmpwi(14 + dd, pos - 2, cr=1).beq(f"same{dd}", cr=1).addi(4, 4, 1)
                a.label(f"same{dd}")
            a.bgt("accept")
            a.cmpw(4, 24).bge(f"next{d}")
            a.label("accept")
            a.mr(23, 3).mr(24, 4)
            for dd in range(7):
                a.stb(14 + dd, BEST + dd, 1)
        else:
            if d == 2:                             # CF, LF, RF chosen: tier 1
                w(25, 14, 15)
                w(3, 14, 16)
                a.add(25, 25, 3).slwi(26, 25, 6)
                a.addi(3, 26, 63).cmpw(3, 23).blt(f"next{d}")
            if d == 4:                             # 2B, SS chosen: tier 2
                w(3, 17, 18)
                a.slwi(3, 3, 3).slwi(26, 25, 6).add(26, 26, 3)
                a.addi(3, 26, 7).cmpw(3, 23).blt(f"next{d}")
            a.li(0, 1).stbx(0, 22, rc)
            level(d + 1)
            a.li(0, 0).stbx(0, 22, rc)
        a.label(f"next{d}")
        a.addi(rc, rc, 1).b(f"loop{d}")
        a.label(f"end{d}")

    level(0)
    for d in range(7):
        a.lbz(0, BEST + d, 1).stb(0, d, 27)
    a.mr(3, 23).mr(4, 24)
    a.word(lmw(14, 0x68, 1)).lwz(0, FF + 4, 1).mtlr(0).addi(1, 1, FF)
    a.blr()
    return a


def field_stub(at, search):
    a = Asm(at)
    level5.gate(a, 3, "stock", "cpu-subs")                     # level 5 only (r3 and cr0 are free here)
    a.lwz(3, CTL, 13).lbz(4, 0x2D, 31).slwi(4, 4, 2).add(3, 3, 4).lwz(3, LEVEL, 3)
    a.cmpwi(3, 0).beq("l4")
    a.label("stock")
    a.word(FIELD_ORIG).b(FIELD_BACK)               # stock: li r0,3
    a.label("l4")
    a.stwu(1, -FF, 1).mflr(0).stw(0, FF + 4, 1).word(stmw(14, 0x68, 1))
    a.lbz(30, 0x2D, 31).lwz(29, LINEUP, 13)        # side, L
    a.bl(GAME).lbz(28, 0x2B, 3)                    # roster team
    a.li(0, -1).stw(0, SLOTS, 1).stw(0, SLOTS + 4, 1).stb(0, SLOTS + 8, 1)
    a.mulli(27, 30, 0x28).add(27, 27, 29)          # L + side*0x28: entries {s16 slot, s16 pos} at +0xC
    a.addi(26, 1, SLOTS).li(3, 0)
    a.label("entry")
    a.slwi(4, 3, 2).add(4, 4, 27).lha(5, 0xE, 4).lhz(6, 0xC, 4)
    a.cmplwi(5, 8).bgt("skip").stbx(6, 26, 5)
    a.label("skip")
    a.addi(3, 3, 1).cmpwi(3, 9).blt("entry")
    for pos in range(2, 9):                        # every movable position filled by a roster slot
        a.lbz(0, SLOTS + pos, 1).cmplwi(0, 9).bge("out")
    a.addi(3, 1, SLOTS + 2).mr(4, 28).addi(5, 1, BEST).bl(search)
    a.mr(24, 4)
    a.cmpwi(24, 0).beq("out")
    a.li(0, 0x0001).sth(0, AT, 1).li(0, 0x0203).sth(0, AT + 2, 1)   # at[i] = i
    a.li(0, 0x0405).sth(0, AT + 4, 1).li(0, 6).stb(0, AT + 6, 1)
    for i in range(6):                             # position i + 2
        pos = i + 2
        a.lbz(15, BEST + LEVELS.index(pos), 1)     # the player it wants
        a.li(14, i).addi(16, 1, AT)
        a.label(f"find{i}")
        a.lbzx(0, 16, 14).cmpw(0, 15).beq(f"found{i}")
        a.addi(14, 14, 1).cmpwi(14, 7).blt(f"find{i}")
        a.b("out")                                 # (can't happen: at[] is a permutation)
        a.label(f"found{i}")
        a.cmpwi(14, i).beq(f"placed{i}")
        a.mr(3, 29).mr(4, 30).li(5, pos).addi(6, 14, 2).bl(SWAP)
        a.lbz(0, AT + i, 1).stbx(0, 16, 14).stb(15, AT + i, 1)
        a.label(f"placed{i}")
    a.label("out")
    a.word(lmw(14, 0x68, 1)).lwz(0, FF + 4, 1).mtlr(0).addi(1, 1, FF)
    a.word(FIELD_ORIG).b(FIELD_BACK)               # li r0,3
    return a


def apply(dol, code):
    """Hook the CPU pitching change and its defense state in `dol`; the stubs go in `code` (a charbuild Space).
    Returns log lines."""
    for site, orig in ((PITCH, PITCH_ORIG), (PITCH_RET, PITCH_RET_ORIG), (FIELD, FIELD_ORIG),
                       (FIELD_SWAP, branch(FIELD_SWAP, SWAP, link=True))):
        got = dol.u32(site)
        assert got == orig, f"0x{site:08X}: 0x{got:08X}, expected 0x{orig:08X}"
    out = []
    base = code.here + (-code.here % 4)            # pitch stub, field stub, then SEARCH (sizes don't move)
    n_pitch = len(pitch_stub(base, base).assemble())
    n_field = len(field_stub(base, base).assemble())
    search = base + n_pitch + n_field
    for site, fn in ((PITCH, pitch_stub), (FIELD, field_stub), (None, None)):
        at = code.here + (-code.here % 4)
        blob = fn(at, search).assemble() if fn else search_sub(at).assemble()
        assert code.put(blob, align=4) == at
        if site:
            dol.w32(site, branch(site, at))
            out.append(f"0x{site:08X} -> 0x{at:08X} ({len(blob)} bytes)")
        else:
            assert at == search
            out.append(f"search 0x{at:08X} ({len(blob)} bytes)")
    return [f"cpu subs: level 5 CPU picks among its top {TOP} pitchers by pitching and stamina (no captain "
            f"preference; level 6: the one reaching the best field chemistry), then re-arranges 1B..RF for "
            f"chemistry ({', '.join(out)})"]
