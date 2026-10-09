"""Ludwig's item (Nick, 2026-09-25): five Fireballs at once, recoloured (koopa_items LUDWIG, id 13).

The Fireball pool is 3 objects inline in COjyamaManager (+0xC0, 0x40 each; the POW follows at +0x180), so it
moves to ARR, 5 objects in our data section, for every throw (Plan A of the pool survey). Stock throws still
launch 3: pitch setup marks only balls 1..2 as followers, and the launch loop (koopa_items' FOLLOW stub) stops
after ball 2 unless the thrower is Ludwig, whose balls 3..4 it marks as followers first. The launch spreads
followers by the table at 0x80793060 (-1, +1, -2, +2 x 10 degrees), which already has four.

Every site that addressed manager+0xC0 (+ i*0x40) now addresses ARR (+ i*0x40); "3 balls" loop bounds become 5:
  ctor FUN_80454598       0x80454638 bl FUN_80622180 (build the pool): nop; ARR is built once per game after
                          the live manager is (BUILD hook 0x80454E18 in FUN_80454dd8), not for the replay
                          snapshot managers (FUN_8016dac0 builds one mid-game, which would reset live balls).
  teardown FUN_80454ce0   0x80454D60 bl FUN_80622278: nop (the Fire dtor with -1 does nothing).
  dispatch FUN_80455394   0x804554F4.. (i*0x40 + ARR), bound 0x80455508.
  pitch setup FUN_80455598 0x80455704.. (ball index +0x38, reset, waiting +0x3C), bound 0x80455728; the
                          follower mark 0x80455714..1C now marks i = 1..2 only (subi/cmplwi/bgt).
  models FUN_80455ac4     0x804561B0..0x80456214 (3 unrolled "first flying ball, count"): a 5-pass loop.
  use FUN_80456710        0x80456944.. (follower loop), bound 0x80456984 (FOLLOW stub caps it at 3 for others).
  lookup FUN_80456abc     0x80456B40 (stub: base), 0x80456B6C (result = r30), bound 0x80456B7C.
  script spawn FUN_804585bc 0x804586A4.. (bound stays 3: never Ludwig).
  clear FUN_804588f4      0x8045894C (stub: base), bound 0x80458964.
  fielder hit FUN_80117838 0x801178EC / 0x801178F8, bound 0x80117A60. ALL_BALLS_HIT: its three "missed" branches
                          (0x801179B4 / 0x801179C8 / 0x801179EC) went to the exit, so only the first flying ball
                          could hit; they continue to the next ball instead (Ludwig's five need it; stock's three
                          benefit too).
  CPU FUN_8011e250        0x8011E2C4 li r30,3 (fire count), 0x8011E358..; FUN_8011e4f0 0x8011E62C.., bound
                          0x8011E6C8; FUN_80176e6c 0x80176EB4 / 0x80176EC0, bound 0x80176F88; FUN_802dc244
                          0x802DC280 / 0x802DC28C, bound 0x802DC3A8; FUN_802dd474 0x802DD508 / 0x802DD514, bound
                          0x802DD554; FUN_802f3098 0x802F33FC / 0x802F3404, bound 0x802F3690.
  trail actors FUN_80292054 0x80292080 / 0x80292094 / 0x8029209C, 0x802920F4 / 0x802920FC; FUN_80292218
                          0x80292980 / 0x80292988.
  trail table 0x80707E08 (3 records of 0x14) -> TRAILS (5): init FUN_800fb7fc (stub: a 5-record loop), start
                          FUN_800fb890 (bound 0x800FB898, base), stop FUN_800fb8f0 (base), FUN_800fb960 (bases
                          0x800FB9A4/B0, 0x800FBA90/98; bounds 0x800FBA88, 0x800FBBC4).
Not handled: replays (FUN_801729b8 copies the manager; ARR isn't in it): a replayed play shows no Fireballs.
"""
import struct

from ppc import Asm, d_form, ha, lo

LUDWIG = 13
N_BALLS = 5
MAX_BALLS = 8                   # a new item's most (the pool grows to its count; the spread table with it)
STOCK_BALLS = 3
SPREAD_BASE, SPREAD_BASE_ORIG = 0x80456914, 0x3BA10010   # addi r29,r1,0x10: the followers' spread bytes (a stack
#                                                          copy of the 4 at 0x80793060: -1, +1, -2, +2 x the angle)
SPREAD_CAP, SPREAD_CAP_ORIG = 0x80456978, 0x28000004     # cmplwi r0,4: the most followers a throw launches
ALL_BALLS_HIT = True
FIRE_CTOR, FIRE_DTOR, ARRAY_CTOR = 0x8045311C, 0x80453164, 0x80622180
TRAIL_OLD, TRAIL_REC = 0x80707E08, 0x14
NOP = 0x60000000


def addis(rt, ra, imm):
    return d_form(15, rt, ra, imm)


def _w(dol, addr, want, new):
    got = dol.u32(addr)
    assert got == want, f"0x{addr:08X}: expected {want:08X}, found {got:08X}"
    dol.w32(addr, new)


def _one(addr, build):
    a = Asm(addr)
    build(a)
    return a.assemble_word()


def _put(code, a):
    at = code.put(a.assemble(), 4)
    assert at == a.base, f"assembled for 0x{a.base:08X}, placed at 0x{at:08X}"
    return at


def _at(code):
    return code.here + (-code.here % 4)


def _bound(dol, addr, n):
    w = dol.u32(addr)
    assert w & 0xFFFF == STOCK_BALLS and w >> 26 in (10, 11), f"0x{addr:08X}: {w:08X} is not a cmp(l)wi rX,3"
    dol.w32(addr, (w & ~0xFFFF) | n)


def apply(dol, code, data, flag, n=N_BALLS):
    """flag: the used-variant byte. n: the pool's balls (N_BALLS; more for a new item that throws up to MAX_BALLS:
    spread_code). Returns log lines; LAYOUT gets ARR / TRAILS / n."""
    # the field offsets are ARR's signed low half + up to 0x40 * n: an ARR ending past a 0x8000 low-half boundary
    # can't be reached that way, so it then starts on that boundary (low half -0x8000) instead (the data section
    # moving 0x3000 up put it at 0x....7F00 in the no-new-characters builds)
    here = data.here + (-data.here % 0x100)
    if 0x8000 - 0x40 * n <= here & 0xFFFF < 0x8000:
        data.put(bytes(0x8000 - (here & 0xFFFF)), 1)
    arr = data.put(bytes(0x40 * n), 0x100)
    trails = data.put(bytes(TRAIL_REC * n), 4)
    H, L = ha(arr), lo(arr)
    Ls = L - 0x10000 if L & 0x8000 else L
    assert -0x8000 <= Ls and Ls + 0x40 * n < 0x8000, "ARR's low half must leave room for the field offsets"
    off = lambda d: (Ls + d - 0xC0) & 0xFFFF                              # manager+d -> ARR+(d-0xC0)
    LAYOUT.update(arr=arr, trails=trails, n=n)

    _w(dol, 0x80454638, Asm(0x80454638).bl(ARRAY_CTOR).assemble_word(), NOP)    # ctor: no inline pool
    _w(dol, 0x80454D60, Asm(0x80454D60).bl(0x80622278).assemble_word(), NOP)    # teardown
    a = Asm(_at(code))                                                           # BUILD 0x80454E18 (r3 = manager)
    a.mr(31, 3).cmpwi(3, 0).beq("skip")
    a.load_addr(3, arr).lis(4, ha(FIRE_CTOR)).addi(4, 4, lo(FIRE_CTOR))
    a.lis(5, ha(FIRE_DTOR)).addi(5, 5, lo(FIRE_DTOR)).li(6, 0x40).li(7, n).bl(ARRAY_CTOR)
    a.mr(3, 31)
    a.label("skip")
    a.word(0x3FE08071).b(0x80454E1C)                                             # lis r31,-0x7f8f
    _w(dol, 0x80454E18, 0x3FE08071, Asm(0x80454E18).b(_put(code, a)).assemble_word())

    # dispatch: rlwinm r0,r29,6 / add r3,r31,r0 / addi r3,r3,0xc0
    _w(dol, 0x804554F4, 0x57A034B2, _one(0x804554F4, lambda a: a.rlwinm(3, 29, 6, 18, 25)))
    _w(dol, 0x804554F8, 0x7C7F0214, addis(3, 3, H))
    _w(dol, 0x804554FC, 0x386300C0, d_form(14, 3, 3, L))
    _bound(dol, 0x80455508, n)
    # pitch setup: r3 = i<<6 / add r28,r29,r3 / stw r0,0xf8(r28) / addi r3,r28,0xc0 / .. / stb r31,0xfc(r28)
    _w(dol, 0x80455704, 0x7F9D1A14, addis(28, 3, H))
    _w(dol, 0x80455708, 0x901C00F8, d_form(36, 0, 28, off(0xF8)))
    _w(dol, 0x8045570C, 0x387C00C0, d_form(14, 3, 28, L))
    _w(dol, 0x80455714, 0x5760063E, d_form(14, 0, 27, -1))                      # subi r0,r27,1
    _w(dol, 0x8045571C, 0x41800008, _one(0x8045571C, lambda a: a.bgt(0x80455724)))   # cmplwi r0,1: mark i=1..2
    _w(dol, 0x80455720, 0x9BFC00FC, d_form(38, 31, 28, off(0xFC)))
    _bound(dol, 0x80455728, n)
    # models: first flying ball (r3) and count (r5) over the 5
    a = Asm(0x804561B0)
    a.lis(4, H).addi(4, 4, L).li(3, 0).li(5, 0).li(6, n).mtctr(6)
    a.label("loop")
    a.lbz(0, 0x3C, 4).cmplwi(0, 2).bne("next").cmpwi(3, 0).addi(5, 5, 1).bne("next").mr(3, 4)
    a.label("next")
    a.addi(4, 4, 0x40)
    loop_at, bdnz_at = 0x804561B0 + 4 * 6, 0x804561B0 + 4 * len(a.items)
    a.word(0x42000000 | ((loop_at - bdnz_at) & 0xFFFC))                          # bdnz loop
    words = list(struct.unpack(f">{len(a.items)}I", a.assemble()))
    assert len(words) <= 26
    words += [NOP] * (26 - len(words))
    assert dol.u32(0x804561B0) == 0x881D00FC and dol.u32(0x80456214) == 0x7C832378, "models: stock words"
    dol.write(0x804561B0, struct.pack(">26I", *words))
    # use: follower loop
    _w(dol, 0x80456944, 0x57E034B2, _one(0x80456944, lambda a: a.rlwinm(3, 31, 6, 18, 25)))
    _w(dol, 0x80456948, 0x7C7B0214, addis(3, 3, H))
    _w(dol, 0x8045694C, 0x880300FC, d_form(34, 0, 3, off(0xFC)))
    _w(dol, 0x80456964, 0x386300C0, d_form(14, 3, 3, L))
    _bound(dol, 0x80456984, n)
    # lookup: base stub, result = r30
    a = Asm(_at(code))
    a.lis(30, H).addi(30, 30, L).li(31, 0).b(0x80456B48)
    _w(dol, 0x80456B40, 0x3BC300C0, Asm(0x80456B40).b(_put(code, a)).assemble_word())
    _w(dol, 0x80456B6C, 0x380300C0, _one(0x80456B6C, lambda a: a.mr(0, 30)))
    _bound(dol, 0x80456B7C, n)
    # script spawn (3 balls)
    _w(dol, 0x804586A4, 0x578034B2, _one(0x804586A4, lambda a: a.rlwinm(3, 28, 6, 18, 25)))
    _w(dol, 0x804586A8, 0x7C7F0214, addis(3, 3, H))
    _w(dol, 0x804586AC, 0x880300FC, d_form(34, 0, 3, off(0xFC)))
    _w(dol, 0x804586C4, 0x386300C0, d_form(14, 3, 3, L))
    # clear: base stub
    a = Asm(_at(code))
    a.lis(31, H).addi(31, 31, L).li(30, 0).b(0x80458954)
    _w(dol, 0x8045894C, 0x3BE300C0, Asm(0x8045894C).b(_put(code, a)).assemble_word())
    _bound(dol, 0x80458964, n)
    # fielder hit
    _w(dol, 0x801178EC, 0x806DFCAC, d_form(15, 3, 0, H))
    _w(dol, 0x801178F8, 0x3BC300C0, d_form(14, 30, 3, L))
    _bound(dol, 0x80117A60, n)
    if ALL_BALLS_HIT:                                                            # a miss checks the next ball
        for site, stock in ((0x801179B4, 0x408100A0), (0x801179C8, 0x4081008C), (0x801179EC, 0x40800068)):
            _w(dol, site, stock, (stock & 0xFFFF0000) | ((0x80117A5C - site) & 0xFFFC))
    # CPU / camera loops
    _w(dol, 0x8011E2C4, 0x3BC00003, 0x3BC00000 | n)
    for rl, add_, addi_, i_reg, m_reg, dst in ((0x8011E358, 0x8011E35C, 0x8011E360, 29, 31, 26),
                                                (0x8011E62C, 0x8011E630, 0x8011E634, 27, 29, 28)):
        _w(dol, rl, _one(rl, lambda a: a.rlwinm(0, i_reg, 6, 18, 25)), _one(rl, lambda a: a.rlwinm(3, i_reg, 6, 18, 25)))
        _w(dol, add_, _one(add_, lambda a: a.add(3, m_reg, 0)), addis(3, 3, H))
        _w(dol, addi_, d_form(14, dst, 3, 0xC0), d_form(14, dst, 3, L))
    _bound(dol, 0x8011E6C8, n)
    for lwz_, addi_, bound, dst in ((0x80176EB4, 0x80176EC0, 0x80176F88, 30), (0x802DC280, 0x802DC28C, 0x802DC3A8, 30),
                                    (0x802DD508, 0x802DD514, 0x802DD554, 30), (0x802F33FC, 0x802F3404, 0x802F3690, 3)):
        _w(dol, lwz_, 0x806DFCAC, d_form(15, 3, 0, H))
        _w(dol, addi_, d_form(14, dst, 3, 0xC0), d_form(14, dst, 3, L))
        _bound(dol, bound, n)
    # trail actors
    _w(dol, 0x80292080, 0x808DFCAC, d_form(15, 4, 0, H))
    _w(dol, 0x80292094, 0x818400C0, d_form(32, 12, 4, L))
    _w(dol, 0x8029209C, 0x386400C0, d_form(14, 3, 4, L))
    for lwz_, lwzu in ((0x802920F4, 0x802920FC), (0x80292980, 0x80292988)):
        _w(dol, lwz_, 0x806DFCAC, d_form(15, 3, 0, H))
        _w(dol, lwzu, 0x858300C0, d_form(33, 12, 3, L))
    # trail table: init stub (5 records), then every base and bound
    a = Asm(_at(code))
    a.load_addr(3, trails).li(5, 0).lfs(0, -0x7788, 2).li(0, -1).li(6, n)
    a.label("loop")
    a.stw(5, 0, 3).stw(5, 4, 3).stfs(0, 8, 3).stb(5, 0xE, 3).stb(5, 0xF, 3).stb(5, 0x10, 3).sth(0, 0xC, 3)
    a.addi(3, 3, TRAIL_REC).addi(6, 6, -1).cmpwi(6, 0).bgt("loop")
    a.b(0x800FB880)
    _w(dol, 0x800FB818, 0x3C808070, Asm(0x800FB818).b(_put(code, a)).assemble_word())
    _bound(dol, 0x800FB898, n)
    for lis_, addi_, reg, src in ((0x800FB8A8, 0x800FB8AC, 3, 3), (0x800FB900, 0x800FB904, 31, 31),
                                  (0x800FB9A4, 0x800FB9B0, 3, 26), (0x800FBA90, 0x800FBA98, 25, 25)):
        _w(dol, lis_, d_form(15, reg, 0, 0x8070), d_form(15, reg, 0, ha(trails)))
        _w(dol, addi_, d_form(14, src, reg, 0x7E08), d_form(14, src, reg, lo(trails)))
    _bound(dol, 0x800FBA88, n)
    _bound(dol, 0x800FBBC4, n)
    if n > N_BALLS:                                      # more than 5: a longer spread table, a higher cap
        log_more = spread_code(dol, code, data, n)
    else:
        log_more = []
    return [f"ludwig: Fireball pool -> 0x{arr:08X} ({n} balls; stock throws 3), trail table -> 0x{trails:08X}"
            + (", every flying ball can hit" if ALL_BALLS_HIT else "")] + log_more


LAYOUT = {}


def follow_code(a, exit_, cont, more=(), ludwig=True):
    """For koopa_items' FOLLOW stub (loop head, r31 = i; r12 = the variant byte; r0 / r11 free): others stop
    after ball STOCK_BALLS - 1; Ludwig's balls 3..4 become followers (+0x3C = 1) at i = 0. more: new items that
    throw more than 3: an id (5 balls) or (id, count), count 4..MAX_BALLS: their balls 3..count-1 (ludwig: Ludwig's
    own, unless he's edited: then he's in more)."""
    arr = LAYOUT["arr"]
    groups = {N_BALLS: [LUDWIG] if ludwig else []}
    for m in more:
        vid, count = m if isinstance(m, tuple) else (m, N_BALLS)
        assert STOCK_BALLS < count <= LAYOUT.get("n", N_BALLS), f"item {vid}: {count} balls (pool {LAYOUT.get('n')})"
        groups.setdefault(count, []).append(vid)
    for count, ids in groups.items():
        for vid in ids:
            a.cmpwi(12, vid).beq(f"lud{count}")
    a.cmplwi(31, STOCK_BALLS).blt(cont).b(exit_)
    for count, ids in groups.items():
        a.label(f"lud{count}")
        a.cmplwi(31, 0).bne(cont)
        a.li(0, 1).load_addr(11, arr)
        for k in range(STOCK_BALLS, count):
            a.stb(0, 0x40 * k + 0x3C, 11)
        a.b(cont)


def spread_code(dol, code, data, n):
    """More than 5 balls: the followers' spread comes from SPREAD (our data: the stock -1, +1, -2, +2, then -3, +3,
    ...; r29 pointed at it instead of the stack copy, which nothing else reads), and a throw launches up to n - 1."""
    stock = list(struct.unpack(">4b", dol.read(0x80793060, 4)))
    table = stock + [(k // 2 + 1) * (-1 if k % 2 == 0 else 1) for k in range(4, n - 1)]
    spread = data.put(struct.pack(f">{len(table)}b", *table), 4)
    a = Asm(_at(code))
    a.lis(29, ha(spread)).addi(29, 29, lo(spread)).b(SPREAD_BASE + 4)
    _w(dol, SPREAD_BASE, SPREAD_BASE_ORIG, Asm(SPREAD_BASE).b(_put(code, a)).assemble_word())
    _w(dol, SPREAD_CAP, SPREAD_CAP_ORIG, (SPREAD_CAP_ORIG & ~0xFFFF) | (n - 1))
    LAYOUT["spread"] = spread
    return [f"ludwig: {n}-ball pool: follower spread {table} at 0x{spread:08X}, up to {n - 1} followers"]
