"""Our own custom-voice routing (clean-base step 5, docs/clean-base.md): each voiced character id plays its own
12-slot table of sound INFO ids instead of its voice family's. Used on the clean base; on the Extra Innings
base charbuild still routes through EI's dispatcher (voice_tables).

The method is the one Jbiscuit's guide describes (refs/Custom_Character_Sounds_Pipeline_-_Rosalina_Luma_Larry.txt),
written as our own code: the exact character travels as a token id * 8 (the selector-table offset the callers
already compute) to the common voice wrapper FUN_804b2898, which picks the table; the final INFO lookup reads it.

  A. WRAPPER 0x804B2898 (`stwu r1,-0x40(r1)`, b): ACTIVE = 0, then the owner token:
       return address 0x8038710C (the family search FUN_80387028, whose r0 is the first family member,
         not the actor): OWNER, published by B / C; consumed (OWNER = 0);
       return addresses DIRECT (the callers that load the actor's id and `slwi r0,r0,3` right before the
         call: 0x80386FA8, 0x80388698, 0x804A5630): r0;
       any other caller (0x80233644 leaves r0 unset): none, stock voices.
     A token id * 8 with id <= the highest id and a table: ACTIVE = that table. r10-r12 and CR are
     preserved; LR and r0 are only read.
  B. OWNER 0x80142078 (`bl 0x80387028`, bl): the caller still has the actor's token in r0: OWNER = r0 around
     the family search, 0 after it.
  C. RESOLVER 0x8036C674 (`bl 0x8036B4E0`, bl), the scripted actor resolver (mound entrance, strikeout
     celebration): RESOLVING = 1, OWNER = 0 around it; OWNER is kept for the voice that follows.
     CAPTURE at its five `rlwinm r0,r0,3,0,28` (id -> token; bl): the shift, then OWNER = r0 while RESOLVING.
     r11, r12 and cr0 are written before they are read after each of the five (checked in the clean DOL).
  D. LOOKUP 0x804B2910 (`lwzx r5,r5,r0`, b; r5 = slot * 4, r0 = the family's stock row): with ACTIVE,
     r5 = ACTIVE[slot] and ACTIVE = 0; otherwise the stock load.

charbuild: apply(dol, code, data, tables, max_id) with tables = {character id: 12 INFO ids}.
Test: python scripts/test_voice_hooks.py
"""
import struct
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
from ppc import Asm

WRAPPER, WRAPPER_WORD = 0x804B2898, 0x9421FFC0            # stwu r1,-0x40(r1)
LOOKUP, LOOKUP_WORD = 0x804B2910, 0x7CA5002E              # lwzx r5,r5,r0
OWNER_CALL, SEARCH = 0x80142078, 0x80387028               # bl FUN_80387028
RESOLVER_CALL, RESOLVER = 0x8036C674, 0x8036B4E0          # bl FUN_8036b4e0
CAPTURES, CAPTURE_WORD = (0x8036B5C0, 0x8036B600, 0x8036B674, 0x8036B6AC, 0x8036B6E4), 0x54001838
SEARCH_RETURN = 0x8038710C
DIRECT_RETURNS = (0x80386FAC, 0x8038869C, 0x804A5634)
SLOTS = 12
OWNER, RESOLVING, ACTIVE = 0, 4, 8                        # state words


def _mfcr(a, rt):
    return a.word(0x7C000026 | (int(rt[1:]) << 21))


def _mtcrf_all(a, rs):
    return a.word(0x7C000120 | (int(rs[1:]) << 21) | (0xFF << 12))


def _patch(dol, addr, expect, word):
    got = dol.u32(addr)
    assert got == expect, f"0x{addr:08X}: expected {expect:08X}, found {got:08X}"
    dol.w32(addr, word)


def apply(dol, code, data, tables, max_id):
    """Install the hooks; tables {id: [12 INFO ids]}. Returns log lines."""
    assert all(len(t) == SLOTS for t in tables.values())
    assert max(tables, default=0) <= max_id
    state = data.put(bytes(12), align=4)
    ptrs = [0] * (max_id + 1)
    for cid, ids in sorted(tables.items()):
        ptrs[cid] = data.put(struct.pack(f">{SLOTS}I", *ids), align=4)
    ptr_table = data.put(struct.pack(f">{len(ptrs)}I", *ptrs), align=4)

    # A. wrapper entry
    a = Asm(code.here)
    a.stwu("r1", -0x20, "r1").stw("r10", 8, "r1").stw("r11", 0xC, "r1").stw("r12", 0x10, "r1")
    _mfcr(a, "r12")
    a.stw("r12", 0x14, "r1")
    a.load_addr("r12", state).li("r11", 0).stw("r11", ACTIVE, "r12")
    a.mflr("r11")
    a.load_addr("r10", SEARCH_RETURN).cmpw("r11", "r10").beq("family")
    for ret in DIRECT_RETURNS:
        a.load_addr("r10", ret).cmpw("r11", "r10").beq("direct")
    a.b("done")
    a.label("family")
    a.lwz("r10", OWNER, "r12").li("r11", 0).stw("r11", OWNER, "r12").b("token")
    a.label("direct")
    a.mr("r10", "r0")
    a.label("token")                                     # r10 = id * 8
    a.andi_("r11", "r10", 7).bne("done")
    a.rlwinm("r11", "r10", 29, 3, 31).cmplwi("r11", max_id).bgt("done")
    a.slwi("r11", "r11", 2).load_addr("r10", ptr_table).lwzx("r11", "r10", "r11")
    a.stw("r11", ACTIVE, "r12")
    a.label("done")
    a.lwz("r12", 0x14, "r1")
    _mtcrf_all(a, "r12")
    a.lwz("r12", 0x10, "r1").lwz("r11", 0xC, "r1").lwz("r10", 8, "r1").addi("r1", "r1", 0x20)
    a.stwu("r1", -0x40, "r1").b(WRAPPER + 4)                 # the displaced instruction
    at = code.put(a.assemble(), 4)
    _patch(dol, WRAPPER, WRAPPER_WORD, Asm(WRAPPER).b(at).assemble_word())

    # B. owner around the family search
    a = Asm(code.here)
    a.stwu("r1", -0x10, "r1").mflr("r12").stw("r12", 8, "r1")
    a.load_addr("r12", state).stw("r0", OWNER, "r12")
    a.bl(SEARCH)
    a.load_addr("r12", state).li("r11", 0).stw("r11", OWNER, "r12")
    a.lwz("r12", 8, "r1").mtlr("r12").addi("r1", "r1", 0x10).blr()
    at = code.put(a.assemble(), 4)
    _patch(dol, OWNER_CALL, Asm(OWNER_CALL).bl(SEARCH).assemble_word(), Asm(OWNER_CALL).bl(at).assemble_word())

    # C. scripted resolver and its five id -> token conversions
    a = Asm(code.here)
    a.stwu("r1", -0x10, "r1").mflr("r12").stw("r12", 8, "r1")
    a.load_addr("r12", state).li("r11", 1).stw("r11", RESOLVING, "r12").li("r11", 0).stw("r11", OWNER, "r12")
    a.bl(RESOLVER)
    a.load_addr("r12", state).li("r11", 0).stw("r11", RESOLVING, "r12")
    a.lwz("r12", 8, "r1").mtlr("r12").addi("r1", "r1", 0x10).blr()
    at = code.put(a.assemble(), 4)
    _patch(dol, RESOLVER_CALL, Asm(RESOLVER_CALL).bl(RESOLVER).assemble_word(),
           Asm(RESOLVER_CALL).bl(at).assemble_word())
    a = Asm(code.here)
    a.word(CAPTURE_WORD)                                     # slwi r0,r0,3
    a.load_addr("r12", state).lwz("r11", RESOLVING, "r12").cmpwi("r11", 0).beq("out")
    a.stw("r0", OWNER, "r12")
    a.label("out")
    a.blr()
    at = code.put(a.assemble(), 4)
    for site in CAPTURES:
        _patch(dol, site, CAPTURE_WORD, Asm(site).bl(at).assemble_word())

    # D. final INFO lookup
    a = Asm(code.here)
    a.load_addr("r12", state).lwz("r11", ACTIVE, "r12").cmpwi("r11", 0).beq("stock")
    a.lwzx("r5", "r5", "r11").li("r11", 0).stw("r11", ACTIVE, "r12").b(LOOKUP + 4)
    a.label("stock")
    a.word(LOOKUP_WORD).b(LOOKUP + 4)
    at = code.put(a.assemble(), 4)
    _patch(dol, LOOKUP, LOOKUP_WORD, Asm(LOOKUP).b(at).assemble_word())
    return [f"voice hooks: own routing (wrapper, owner, resolver + 5 captures, lookup), {len(tables)} tables "
            f"({', '.join(f'0x{c:02X}' for c in sorted(tables))}), state 0x{state:08X}, pointers 0x{ptr_table:08X}"]
