"""A fifth "Level 5" and a sixth "Level 6" button on the exhibition captain select's CPU level popup (dialog 0x71).

Research: the popup (popup_menu::CMenuPopUpTask) takes its buttons from the dialog table 0x806D2D30 (one 0x38-byte
entry per dialog 0x5E..0x7D: u32 style, s32 cancel, 6 x {s32 choice, s32 message}, -1 = empty). Dialog 0x71 ("CPU
Level", 0x806D3158) uses 4 slots: choices 0x12..0x15, messages 0xAE..0xB1. Its 5th slot, 0x806D3180, is empty. The
constructor (FUN_804745c0, run inside the open call FUN_80471864) copies the slots into the popup object, so the
table is read only while the popup is being opened (later code reads only the entry's style and cancel words). Its
6th slot, 0x806D3188, is empty too. The layout already has 5- and 6-button rows (dir 119 file 4 element 0x28), input
wraps on the count, and a button's picture is resource row choice + 0x22.

What this module does:
  D1 exhibition open (FUN_802cb688 case 5): the `bl FUN_80471864` at 0x802CCC30 goes through a stub that fills the
     5th slot with {0x46, "Superstar Level"} and the 6th with {0x47, "Legend Level"}, opens the popup, and empties
     both slots again. Every other opener of dialog 0x71 (the minigame character select FUN_8042c8a4 case 0x15, the
     pause menu's dead 0x6E branch, anything not found) still sees the stock 4 buttons, so none of their answer
     handlers can meet 0x46 / 0x47. (Like 0x46, 0x47 is no dialog's choice; the `cmpwi r4,0x47` in FUN_80471864
     compares a dialog id.)
  D2 exhibition answer (case 6): `bge cr1,0x802CCCEC` at 0x802CCCA8 (ids >= 0x16 leave the level alone) goes to a
     stub: 0x46 -> byte LEVEL6 = 0, 0x47 -> byte LEVEL6 = 1, and both -> settings(r13-0xB00)+0x10 = 4 (the stock
     stores' register and offset), then the stock 0x802CCCEC; other ids exactly as stock (they leave LEVEL6 alone:
     it matters only when settings+0x10 == 4). The stub uses only r0, r4 (both reloaded at 0x802CCCEC) and cr1.
     settings+0x10 = 4 is the "Level 5" marker another module turns into level 4 + a flag at match start; the game
     never sees a 5 (FUN_800A94EC's word table 0x8063FB78 has 5 entries). LEVEL6 (level5.FLAG + 1, a byte in our
     data section, passed in by the caller) tells Level 6 from Level 5.
  T  dir 121 file 4 (the popup messages, every language): "Superstar Level" then "Legend Level" appended
     (add_message, bench.py's shape); their indexes go into D1's slots.
  A  dir 119 file 4 (every language copy): a "Level 5" picture as row 0x68 (= 0x46 + 0x22) and a "Level 6" picture
     as row 0x69 (= 0x47 + 0x22), each on its own new CI8 page (Level 5's added first, byte for byte as when it was
     alone), made at build time from the player's own file: the Level 4 cell (row 0x37) with its "4" erased and the
     gold "5" / "6" drawn in the level digits' own style (level5 below).

CHALLENGE (Nick, 2026-09-28: "allow for 5 and 6 for the other teams"): Challenge's own level dialog 0x74 (opened by
FUN_801E762C case 4 before a game against a team, enable mask 0xF, no cancel; the answer is mapped in FUN_801E6458
to the difficulty +0xF2 = 0..3 of the Challenge object, then case 5's setup FUN_801DCE08 turns it into settings+0x10
= 3 - difficulty through the settings init FUN_802D9978) gets the same two buttons (same choices, pictures and lines):
  C1 open (0x801E77D8 bl FUN_80471864): a stub fills dialog 0x74's 5th / 6th slots around the call, as D1, and clears
     CHAL_PICK (level5.chal_pick()); the enable mask `li r0,0xF` at 0x801E77AC -> 0x3F (6 buttons on).
  C2 answer (0x801E67C8, `b 0x801E67F8`, taken by ids that aren't 0x12..0x15 while +0xF2 is -1): 0x46 -> CHAL_PICK 1,
     0x47 -> 2, and both -> difficulty 3 (All-Star: its coins and tables), then 0x801E67F8 (it reloads r3; r0 free).
  C3 latch (FUN_802D9978's first word, `stwu r1,-0x10(r1)`, a leaf, so LR is still its caller's): CHAL_MATCH
     (level5.chal_match()) = CHAL_PICK when LR = 0x801DD060 (called from FUN_801DCE08, the dialog's setup), else 0
     (Challenge's other setups: FUN_801DC5B4 / 801DCA30 / 801DD0DC, with fixed or scripted difficulties). r0 / r11 /
     r12 are set by the function before any use. The CPU manager (level5.py) reads CHAL_MATCH, and also makes a
     Bowser-captained CPU team level 5 in any Challenge game.

No unlock mask or per-level save exists on the exhibition path: case 5 opens the popup with flags 4 only (default by
choice id, 0x13 = Level 2), so the constructor's enable-mask branch (flag 1) never runs.
"""
import struct

from ppc import Asm, ha, lo

CHOICE = 0x46                       # the Level 5 button's choice id; its art row = CHOICE + ROW_BASE
CHOICE6 = 0x47                      # the Level 6 button's
ROW_BASE = 0x22                     # FUN_80473da4: the ButtonPic frame = choice + 0x22
ART_ROW = CHOICE + ROW_BASE         # 0x68, the row after the stock 0x00..0x67
ART_ROW6 = CHOICE6 + ROW_BASE       # 0x69
MARKER = 4                          # settings+0x10 value for Level 5 and Level 6 (stock writes 0..3 only)

DIALOG_TABLE, DIALOG_FIRST, DIALOG_SIZE = 0x806D2D30, 0x5E, 0x38
DIALOG = 0x71
ENTRY = DIALOG_TABLE + (DIALOG - DIALOG_FIRST) * DIALOG_SIZE          # 0x806D3158
SLOT5 = ENTRY + 8 + 4 * 8                                             # 0x806D3180
SLOT6 = ENTRY + 8 + 5 * 8                                             # 0x806D3188
ENTRY_STOCK = (3, 0x2E, 0x12, 0xAE, 0x13, 0xAF, 0x14, 0xB0, 0x15, 0xB1, -1, 0, -1, 0)

POPUP_OPEN = 0x80471864             # FUN_80471864(mgr, dialog, layer, default, flags byte, params*)
OPEN_SITE = 0x802CCC30              # FUN_802cb688 case 5: bl POPUP_OPEN (r4 = 0x71 at 0x802CCC20)
OPEN_DIALOG = (0x802CCC20, 0x38800071)                                # li r4,0x71
ANSWER_SITE = (0x802CCCA8, 0x4084_0044)                               # bge cr1,0x802CCCEC
ANSWER_LOW = 0x802CCCAC             # stock fall-through for ids 0x14 < id < 0x16 (b 0x802CCCE0: 0x15 -> 0)
ANSWER_DONE = 0x802CCCEC            # +0x1C = 1, state 7
SETTINGS_R13, LEVEL_OFF = -0xB00, 0x10
# the stock stores this module mirrors (lwz r4,-0xB00(r13); li r0,N; stw r0,0x10(r4)), 0x12 -> 3 .. 0x15 -> 0
STOCK_STORES = {0x802CCCB0: 3, 0x802CCCC0: 2, 0x802CCCD0: 1, 0x802CCCE0: 0}
# The minigame character select's dialog 0x71 answer (FUN_8042c8a4 case 0x16), left stock: D1 keeps 0x46 from it
MINIGAME_OPEN = (0x8042EA60, 0x38800071)
MINIGAME_ANSWER = (0x8042EADC, 0x40840044)                            # bge cr1,0x8042EB20

# Challenge (C1-C3)
CH_DIALOG = 0x74
CH_ENTRY = DIALOG_TABLE + (CH_DIALOG - DIALOG_FIRST) * DIALOG_SIZE    # 0x806D3200
CH_SLOT5 = CH_ENTRY + 8 + 4 * 8
CH_ENTRY_STOCK = (3, -1, 0x12, 0xBA, 0x13, 0xBB, 0x14, 0xBC, 0x15, 0xBD, -1, 0, -1, 0)
CH_OPEN_SITE = 0x801E77D8           # FUN_801E762C case 4: bl POPUP_OPEN
CH_OPEN_DIALOG = (0x801E77B8, 0x38800074)                             # li r4,0x74
CH_MASK = (0x801E77AC, 0x3800000F, 0x3800003F)                        # li r0,0xF -> li r0,0x3F
CH_DIFF = 0xF2                      # the Challenge object's difficulty byte (r27 in FUN_801E6458)
CH_ANSWER_SITE = 0x801E67C8         # b 0x801E67F8 (ids not 0x12..0x15)
CH_ANSWER_DONE = 0x801E67F8
CH_INIT = (0x802D9978, 0x9421FFF0)  # FUN_802D9978: stwu r1,-0x10(r1)
CH_INIT_FROM = 0x801DD060           # the return address of FUN_801DCE08's call (0x801DD05C)

MSG_DIR, MSG_FILE = 121, 4
STOCK_MSGS = (0xAE, 0xAF, 0xB0, 0xB1)   # Rookie / Veteran / Pro / All-Star Level
# per language (picked by the language of the copy's All-Star line); FR / ES in the stock lines' "difficulty  level"
# form, no longer than the longest stock line (26)
TEXTS = {"en": "Superstar Level", "fr": "Extrême!  Niveau Superstar", "es": "Épico  Nivel superestrella"}
TEXTS6 = {"en": "Legend Level", "fr": "Ultime!  Niveau Légende", "es": "Mítico  Nivel leyenda"}

ART_DIR, ART_FILE = 119, 4
LEVEL_ROWS = (0x34, 0x35, 0x36, 0x37)   # Level 1..4 pictures
DIGIT5_ROW = 0x07                       # the gold "5" (coin counter digits 0..9 = rows 0x02..0x0B)
DIGIT6_ROW = 0x08                       # the gold "6"
GX_CI8, PAL_RGB5A3 = 9, 2


def _patch(dol, addr, expect, new):
    got = dol.u32(addr)
    assert got == expect, f"level5_menu: 0x{addr:08X} expected {expect:08X}, found {got:08X}"
    dol.w32(addr, new)


def _store_words(value):
    a = Asm(0)
    a.lwz("r4", SETTINGS_R13, 13).li("r0", value).stw("r0", LEVEL_OFF, "r4")
    return struct.unpack(">3I", a.assemble())


def check_stock(dol):
    """Assert every stock word and table entry this module relies on."""
    entry = struct.unpack(">14i", dol.read(ENTRY, DIALOG_SIZE))
    assert entry == ENTRY_STOCK, f"level5_menu: dialog 0x71 entry changed: {entry}"
    assert dol.u32(OPEN_DIALOG[0]) == OPEN_DIALOG[1], "level5_menu: exhibition case 5 does not open dialog 0x71"
    assert dol.u32(OPEN_SITE) == Asm(OPEN_SITE).bl(POPUP_OPEN).assemble_word(), "level5_menu: open call moved"
    assert dol.u32(ANSWER_SITE[0]) == ANSWER_SITE[1], "level5_menu: exhibition answer compare changed"
    for addr, value in STOCK_STORES.items():
        got = struct.unpack(">3I", dol.read(addr, 12))
        assert got == _store_words(value), f"level5_menu: stock level store at 0x{addr:08X} changed"
    assert dol.u32(MINIGAME_OPEN[0]) == MINIGAME_OPEN[1] and dol.u32(MINIGAME_ANSWER[0]) == MINIGAME_ANSWER[1], \
        "level5_menu: minigame dialog 0x71 path changed"
    entry = struct.unpack(">14i", dol.read(CH_ENTRY, DIALOG_SIZE))
    assert entry == CH_ENTRY_STOCK, f"level5_menu: dialog 0x74 entry changed: {entry}"
    assert dol.u32(CH_OPEN_DIALOG[0]) == CH_OPEN_DIALOG[1], "level5_menu: Challenge does not open dialog 0x74 there"
    assert dol.u32(CH_OPEN_SITE) == Asm(CH_OPEN_SITE).bl(POPUP_OPEN).assemble_word(), "level5_menu: 0x74 open moved"
    assert dol.u32(CH_MASK[0]) == CH_MASK[1], "level5_menu: dialog 0x74's enable mask changed"
    assert dol.u32(CH_ANSWER_SITE) == Asm(CH_ANSWER_SITE).b(CH_ANSWER_DONE).assemble_word(), \
        "level5_menu: Challenge's difficulty answer changed"
    assert dol.u32(CH_INIT[0]) == CH_INIT[1], "level5_menu: FUN_802D9978 changed"
    assert dol.u32(CH_INIT_FROM - 4) == Asm(CH_INIT_FROM - 4).bl(CH_INIT[0]).assemble_word(), \
        "level5_menu: FUN_801DCE08's settings init call moved"


def _slots(a, slot5, msg, msg6, on):
    """Dialog slots 5 and 6 at `slot5` on ({0x46, msg}, {0x47, msg6}) or off (-1, 0); uses r11 / r12."""
    hi = (slot5 + 0x8000) >> 16
    lo0, lo1, lo2, lo3 = (slot5 + k - (hi << 16) for k in (0, 4, 8, 12))
    assert -0x8000 <= lo0 and lo3 < 0x8000
    a.lis("r12", hi)
    if on:
        a.li("r11", CHOICE).stw("r11", lo0, "r12").li("r11", msg).stw("r11", lo1, "r12")
        a.li("r11", CHOICE6).stw("r11", lo2, "r12").li("r11", msg6).stw("r11", lo3, "r12")
    else:
        a.li("r11", -1).stw("r11", lo0, "r12").stw("r11", lo2, "r12")
        a.li("r11", 0).stw("r11", lo1, "r12").stw("r11", lo3, "r12")


def challenge_stubs(a, msg, msg6, pick, match):
    """C1 open_ch, C2 answer_ch, C3 latch_ch, appended to `a`."""
    L = a.label
    L("open_ch")                                # C1: CHAL_PICK = 0, slots 5 and 6 on, open, off
    a.stwu("r1", -0x10, "r1").mflr("r0").stw("r0", 0x14, "r1")
    a.lis("r12", ha(pick)).li("r11", 0).stb("r11", lo(pick), "r12")
    _slots(a, CH_SLOT5, msg, msg6, True)
    a.bl(POPUP_OPEN)
    _slots(a, CH_SLOT5, msg, msg6, False)
    a.lwz("r0", 0x14, "r1").mtlr("r0").addi("r1", "r1", 0x10).blr()

    L("answer_ch")                              # C2: r3 = the choice, r27 = the Challenge object; r0 free
    a.cmpwi("r3", CHOICE).li("r0", 1).beq("ach_set")
    a.cmpwi("r3", CHOICE6).li("r0", 2).bne("ach_out")
    L("ach_set")
    a.lis("r3", ha(pick)).stb("r0", lo(pick), "r3")
    a.li("r0", 3).stb("r0", CH_DIFF, "r27")     # All-Star underneath (coins, Challenge's tables)
    L("ach_out")
    a.b(CH_ANSWER_DONE)

    L("latch_ch")                               # C3: FUN_802D9978's entry (LR = its caller's return address)
    a.mflr("r11").lis("r12", ha(CH_INIT_FROM)).addi("r12", "r12", lo(CH_INIT_FROM)).cmpw("r11", "r12")
    a.li("r0", 0).bne("latch_store")
    a.lis("r12", ha(pick)).lbz("r0", lo(pick), "r12")
    L("latch_store")
    a.lis("r12", ha(match)).stb("r0", lo(match), "r12")
    a.stwu("r1", -0x10, "r1")
    a.b(CH_INIT[0] + 4)


def stubs(base, msg, msg6, level6_addr, pick=None, match=None):
    """-> Asm at `base`: open5 (D1) then answer5 (D2), then Challenge's C1-C3 when `pick` / `match` are given."""
    a = Asm(base)
    L = a.label
    hi = (SLOT5 + 0x8000) >> 16
    lo0, lo1, lo2, lo3 = (SLOT5 + k - (hi << 16) for k in (0, 4, 8, 12))
    assert -0x8000 <= lo0 and lo3 < 0x8000 and SLOT6 == SLOT5 + 8
    assert 0 <= msg < 0x8000 and 0 <= msg6 < 0x8000
    assert 0x80000000 <= level6_addr < 0x81800000, f"level5_menu: LEVEL6 0x{level6_addr:08X} is not in MEM1"

    L("open5")                                  # D1: slots 5 and 6 on, open (the constructor copies them), then off
    a.stwu("r1", -0x10, "r1").mflr("r0").stw("r0", 0x14, "r1")
    a.lis("r12", hi).li("r11", CHOICE).stw("r11", lo0, "r12").li("r11", msg).stw("r11", lo1, "r12")
    a.li("r11", CHOICE6).stw("r11", lo2, "r12").li("r11", msg6).stw("r11", lo3, "r12")
    a.bl(POPUP_OPEN)
    a.lis("r12", hi).li("r11", -1).stw("r11", lo0, "r12").stw("r11", lo2, "r12")
    a.li("r11", 0).stw("r11", lo1, "r12").stw("r11", lo3, "r12")
    a.lwz("r0", 0x14, "r1").mtlr("r0").addi("r1", "r1", 0x10).blr()

    L("answer5")                                # D2: cr1 = cmpwi r0,0x16 (stock); uses only r0, r4, cr1
    a.blt("a5_low", cr=1)
    a.cmpwi("r0", CHOICE, cr=1).beq("a5_l5", cr=1)
    a.cmpwi("r0", CHOICE6, cr=1).bne("a5_out", cr=1)
    a.li("r0", 1).b("a5_set")                   # Level 6: LEVEL6 = 1
    L("a5_l5")
    a.li("r0", 0)                               # Level 5: LEVEL6 = 0
    L("a5_set")
    a.lis("r4", ha(level6_addr)).stb("r0", lo(level6_addr), "r4")
    a.lwz("r4", SETTINGS_R13, 13).li("r0", MARKER).stw("r0", LEVEL_OFF, "r4")
    L("a5_out")
    a.b(ANSWER_DONE)
    L("a5_low")
    a.b(ANSWER_LOW)
    if pick is not None:
        challenge_stubs(a, msg, msg6, pick, match)
    return a


def apply(dol, code, msg, msg6, level6_addr, pick=None, match=None):
    """Patch `dol`: D1 and D2, stubs placed in `code` (charbuild Space). msg / msg6 = the "Superstar Level" /
    "Legend Level" message indexes in dir 121 file 4 (add_message). level6_addr = the LEVEL6 byte (level5.FLAG + 1,
    in our data section; level5.alloc(data) first): D2 writes 0 there for Level 5, 1 for Level 6. pick / match =
    level5.chal_pick() / chal_match(): Challenge's dialog 0x74 gets the buttons too (C1-C3). Returns log lines."""
    check_stock(dol)
    base = code.here + (-len(code.blob) % 4)
    a = stubs(base, msg, msg6, level6_addr, pick, match)
    text = a.assemble()
    assert code.put(text, align=4) == base
    labels = a.labels
    _patch(dol, OPEN_SITE, Asm(OPEN_SITE).bl(POPUP_OPEN).assemble_word(),
           Asm(OPEN_SITE).bl(labels["open5"]).assemble_word())
    _patch(dol, ANSWER_SITE[0], ANSWER_SITE[1], Asm(ANSWER_SITE[0]).b(labels["answer5"]).assemble_word())
    more = []
    if pick is not None:
        _patch(dol, CH_OPEN_SITE, Asm(CH_OPEN_SITE).bl(POPUP_OPEN).assemble_word(),
               Asm(CH_OPEN_SITE).bl(labels["open_ch"]).assemble_word())
        _patch(dol, CH_MASK[0], CH_MASK[1], CH_MASK[2])
        _patch(dol, CH_ANSWER_SITE, Asm(CH_ANSWER_SITE).b(CH_ANSWER_DONE).assemble_word(),
               Asm(CH_ANSWER_SITE).b(labels["answer_ch"]).assemble_word())
        _patch(dol, CH_INIT[0], CH_INIT[1], Asm(CH_INIT[0]).b(labels["latch_ch"]).assemble_word())
        more = [f"level 5 menu: Challenge's level dialog 0x74 gets the same 5th / 6th buttons (all 6 enabled); "
                f"answer -> difficulty 3 and CHAL_PICK 0x{pick:08X} = 1 / 2, latched into CHAL_MATCH 0x{match:08X} "
                f"by FUN_802D9978 when FUN_801DCE08 starts the game"]
    return [f"level 5 menu: exhibition CPU level popup (dialog 0x71) gets a 5th button 0x{CHOICE:02X} (message "
            f"0x{msg:X}, art row 0x{ART_ROW:X}) and a 6th 0x{CHOICE6:02X} (message 0x{msg6:X}, art row "
            f"0x{ART_ROW6:X}) while exhibition opens it; answer -> settings+0x10 = {MARKER} and LEVEL6 byte "
            f"0x{level6_addr:08X} = 0 / 1; stubs 0x{len(text):x} B at 0x{base:08X} (open 0x{labels['answer5'] - base:x}, answer "
            f"0x{base + len(text) - labels['answer5']:x})"] + more


# ---------------- dir 121 file 4: the description line ----------------
def _language(text):
    return "fr" if "Niveau" in text else "es" if "Nivel" in text else "en"


def message_table(table):
    """A dir 121 file 4 copy -> (the copy with our two lines appended, the Level 5 line's index (Level 6's = + 1),
    the language)."""
    from dir121_messages import decode_message, encode_message
    assert table[:2] == b"\1\1", "not a message table"
    n = struct.unpack_from(">H", table, 2)[0]
    offs = list(struct.unpack_from(f">{n}I", table, 4))
    body = bytearray(table[4 + 4 * n:])
    assert max(STOCK_MSGS) < n
    allstar = bytes(body[2 * offs[STOCK_MSGS[-1]]:])
    prefix = b""
    while allstar[:2] >= b"\xe0\x00" and allstar[:2] < b"\xff\x00":    # leading control codes (<F000>), as stock
        prefix += allstar[:2]
        allstar = allstar[2:]
    lang = _language(decode_message(allstar))
    for texts in (TEXTS, TEXTS6):
        offs.append(len(body) // 2)
        body += prefix + encode_message(texts[lang], width=64)
    return b"\1\1" + struct.pack(f">H{len(offs)}I", len(offs), *offs) + bytes(body), n, lang


def add_message(dol, data, dir_ptrs, dat, cursor, pending):
    """Append "Superstar Level" then "Legend Level" (per language) to dir 121 file 4, every language copy,
    bench.add_message's way (it reads earlier edits of the file from `pending`, so it chains with bench's
    "Substitute" in either order). Returns (log, [(dt_na offset, bytes)], cursor, Level 5 message index, Level 6
    message index)."""
    import dtna_toc
    from char_names import _records

    def read(off, length):
        for at, blob in pending:
            if at <= off < at + len(blob):
                return blob[off - at:off - at + length]
        with open(dat, "rb") as fh:
            fh.seek(off)
            return fh.read(length)
    toc = dtna_toc.toc(dol)
    recs = _records(dol, data, dir_ptrs[MSG_DIR], len(toc[MSG_DIR]) * dtna_toc.FILE_RECORD)
    appended, placed, index, langs = [], {}, None, []
    for lang in range(3):
        at = MSG_FILE * dtna_toc.FILE_RECORD + lang * 16
        _, length, off, _ = struct.unpack_from(">4I", recs, at)
        if off not in placed:
            new, n, name = message_table(read(off, length))
            assert index in (None, n), "languages disagree on the message count"
            index = n
            langs.append(name)
            appended.append((cursor, new))
            placed[off] = (cursor, len(new))
            cursor += len(new) + (-len(new) % 32)
        new_off, new_len = placed[off]
        struct.pack_into(">III", recs, at + 4, new_len, new_off, new_len)
    dir_ptrs[MSG_DIR] = data.put(bytes(recs), align=4)
    return [f"level 5 menu: \"{TEXTS['en']}\" / \"{TEXTS6['en']}\" are dir {MSG_DIR} file {MSG_FILE} messages "
            f"0x{index:X} / 0x{index + 1:X} (copies: {', '.join(langs)})"], appended, cursor, index, index + 1


# ---------------- dir 119 file 4: the button picture ----------------
def layout_bytes(data, preview=None):
    """A dir 119 file 4 copy -> with the Level 5 picture as row ART_ROW and the Level 6 picture as row ART_ROW6, each
    on its own CI8 page (Level 5's added first, exactly as when it was the only one). preview: a path to save the new
    cells (and the stock Level 1-4 cells beside them) as a PNG."""
    import layout
    lay = layout.Layout(data)
    assert len(lay.rows) == ART_ROW, f"dir 119 file 4 has 0x{len(lay.rows):X} rows (expected 0x{ART_ROW:X})"
    cells = [cell(lay, data, r) for r in LEVEL_ROWS]
    src_page = struct.unpack_from(">H", lay.rows[LEVEL_ROWS[-1]], 0)[0]
    made, decoded = [], []
    for row, digit_row in ((ART_ROW, DIGIT5_ROW), (ART_ROW6, DIGIT6_ROW)):
        img = level5(cells, cell(lay, data, digit_row))
        image, palette, w, h = ci8(img)
        page = lay.add_texture(image, w, h, GX_CI8, template_page=src_page, palette=palette,
                               palette_format=PAL_RGB5A3)
        cw, ch = img.shape[1], img.shape[0]
        assert lay.add_row(page, 0.0, 0.0, cw / w, ch / h) == row
        made.append(img)
        decoded.append(decode_ci8(image, palette, w, h)[:ch, :cw])
    if preview:
        save_preview(preview, cells + made, *decoded)
    return lay.to_bytes()


def patch_layout(dol, dat_path, preview=None):
    """dir 119 file 4 rebuilt in the output's own dt_na.dat (dat_path), every language copy (dtna_toc.rebuild_file).
    preview: a folder for level5_preview_<copy>.png (Level 1-4, 5 and 6 as made, 5 and 6 as the game decodes them;
    optional)."""
    import dtna_toc
    from pathlib import Path
    done = []

    def rebuild(data):
        done.append(1)
        return layout_bytes(data, Path(preview) / f"level5_preview_{len(done) - 1}.png" if preview else None)
    n = dtna_toc.rebuild_file(dol, dat_path, ART_DIR, ART_FILE, rebuild)
    return [f"level 5 menu: dir {ART_DIR} file {ART_FILE} + the Level 5 / Level 6 pictures (rows 0x{ART_ROW:X} / "
            f"0x{ART_ROW6:X}, own CI8 pages), {n} copies appended"]


# ---------------- the art (made from the player's own dir 119 file 4 copy; nothing stock is shipped) ----------------
# The Level 1-4 cells are 82 x 82 on one shared 512 x 1024 CI8 atlas (a 256-colour RGB5A3 palette per page): a white
# "Level" (identical in all four above the digits) over a big white digit in the gold counter digits' rounded font:
# a grey-shaded white fill, a thin dark edge and a soft black shadow. The "5" / "6" is the gold counter "5" / "6"
# (row 0x07 / 0x08, 30 x 30, the same font) as a shape: upscaled, then painted with the level digits' own edge
# profile (grey value and alpha against the signed distance to the fill edge and the edge's direction, measured on
# Level 1-4), at the stock digits' height, top and centre.
SS = 4                                  # supersampling of the new digit's shape
PROFILE_D = (-8.0, 12.0, 0.5)           # signed distance bins (native px, + inside)
ANGLES = 8


def cell(lay, data, row):
    """A resource row's pixels (uint8 RGBA h x w) from a CI4 / CI8 page with an RGB5A3 palette."""
    import numpy as np
    import layout
    from icon_bank import rgb5a3_to_rgba
    page, _, v1, u1, v2, u2 = struct.unpack(">HH4f", lay.rows[row])
    d = lay.descs[page]
    img, pal, h, w = struct.unpack_from(">IIHH", d, 0)
    fmt, n, pf = d[0x17], struct.unpack_from(">H", d, 0x18)[0], d[0x1A]
    assert pf == PAL_RGB5A3, f"row 0x{row:X}: palette format {pf}"
    at = layout.TEX_BASE + img
    if fmt == GX_CI8:
        idx = np.frombuffer(data[at:at + w * h], np.uint8).reshape(h // 4, w // 8, 4, 8).transpose(0, 2, 1, 3)
    else:
        assert fmt == 8, f"row 0x{row:X}: texture format {fmt}"
        raw = np.frombuffer(data[at:at + w * h // 2], np.uint8)
        idx = np.stack([raw >> 4, raw & 15], -1).reshape(h // 8, w // 8, 8, 8).transpose(0, 2, 1, 3)
    idx = idx.reshape(h, w)
    palette = np.frombuffer(data[layout.TEX_BASE + pal:layout.TEX_BASE + pal + 2 * n], ">u2")
    y1, x1, y2, x2 = round(v1 * h), round(u1 * w), round(v2 * h), round(u2 * w)
    return rgb5a3_to_rgba(palette[idx[y1:y2, x1:x2]])


def _fill(c):
    """The white fill (letters and digit) of a level cell."""
    return (c[..., 3] == 255) & (c[..., :3].min(-1) >= 0x70)


WORD_REACH = 8                          # the word's edge and shadow end this far from its white fill (px)


def _split(cells):
    """-> (the word's white fill, [each cell's digit fill]). The word (Level / Niveau / Nivel: it differs per
    language copy, and Niveau arcs down beside the digit) = the fill components that every cell has."""
    import numpy as np
    from np_image import label
    fills = [_fill(c) for c in cells]
    common = np.logical_and.reduce(fills)
    word = np.zeros_like(common)
    for f in fills:
        lab, n = label(f)
        for j in range(1, n + 1):
            comp = lab == j
            if not (comp & ~common).any():
                word |= comp
    assert word.any(), "no word found above the level digits"
    return word, [f & ~word for f in fills]


def _signed_distance(mask):
    """+ inside, - outside, 0 on the edge (pixel units, the edge half-way between pixel centres)."""
    import numpy as np
    from np_image import distance_transform_edt as edt
    pad = np.pad(mask, 2)
    sd = np.where(pad, edt(pad) - 0.5, 0.5 - edt(~pad))
    return sd[2:-2, 2:-2]


def _angle(sd):
    import numpy as np
    gy, gx = np.gradient(sd)
    return np.arctan2(gy, gx)


def _profile(cells, digits, far):
    """[angle bin][distance bin] -> (grey, alpha) medians over the stock digits (pixels `far` from the word)."""
    import numpy as np
    lo, hi, step = PROFILE_D
    nd = int(round((hi - lo) / step)) + 1
    grey = np.full((ANGLES, nd), np.nan)
    alpha = np.full((ANGLES, nd), np.nan)
    ks, bs, gs, as_ = [], [], [], []
    for c, digit in zip(cells, digits):
        sd = _signed_distance(digit)
        ang = _angle(sd)
        sel = far & (sd >= lo) & (sd <= hi)
        bs.append(np.rint((sd[sel] - lo) / step).astype(int))
        ks.append(np.rint((ang[sel] + np.pi) / (2 * np.pi) * ANGLES).astype(int) % ANGLES)
        gs.append(c[..., 0][sel].astype(float))
        as_.append(c[..., 3][sel].astype(float))
    k, b, g, a = (np.concatenate(v) for v in (ks, bs, gs, as_))
    for j in range(nd):
        every = b == j
        for i in range(ANGLES):
            m = every & (k == i)
            if m.sum() < 6:
                m = every
            if m.any():
                grey[i, j], alpha[i, j] = np.median(g[m]), np.median(a[m])
    for arr in (grey, alpha):                         # empty bins: the nearest filled one
        for i in range(ANGLES):
            known = np.where(~np.isnan(arr[i]))[0]
            arr[i] = arr[i][known[np.abs(np.arange(nd)[:, None] - known[None]).argmin(1)]]
    alpha[:, 0] = 0                                   # far outside: clear
    return grey, alpha


def _shape(digit, height):
    """The gold digit's fill as a binary mask at SS x the native scale, `height` native px tall (its bbox)."""
    import numpy as np
    from PIL import Image
    r = digit[..., 0].astype(np.float64)
    cover = np.clip((r - 0x40) / (0x90 - 0x40), 0, 1) * (digit[..., 3] == 255)
    big = 16
    f = Image.fromarray((cover * 255).astype(np.uint8)).resize((digit.shape[1] * big, digit.shape[0] * big),
                                                                Image.BICUBIC)
    m = np.array(f) >= 128
    ys, xs = np.where(m)
    m = m[ys.min():ys.max() + 1, xs.min():xs.max() + 1]
    h_hi = round(height * SS)
    w_hi = round(m.shape[1] * h_hi / m.shape[0])
    soft = Image.fromarray(m.astype(np.uint8) * 255).resize((w_hi, h_hi), Image.BOX)
    return np.array(soft) >= 128


def level5(cells, digit):
    """The Level 5 (or 6) picture (uint8 RGBA, the cells' size) from the stock Level 1-4 cells and the gold "5" (or
    "6")."""
    import numpy as np
    from np_image import distance_transform_edt as edt
    h, w = cells[0].shape[:2]
    word_fill, digits = _split(cells)
    rows = [np.where(d.any(1))[0] for d in digits[1:]]               # Level 2-4's digits
    top = int(np.median([r.min() for r in rows]))
    height = float(np.median([r.max() + 1 - r.min() for r in rows]))
    cx = float(np.mean([(np.where(d.any(0))[0].min() + np.where(d.any(0))[0].max() + 1) / 2 for d in digits[1:]]))
    to_word = edt(~word_fill)

    # the word alone: each pixel from the cell whose digit is farthest from it, nothing past the word's reach
    stack = np.stack(cells)
    pick = np.stack([edt(~d) for d in digits]).argmax(0)
    word = np.take_along_axis(stack, pick[None, ..., None], 0)[0].copy()
    word[to_word > WORD_REACH] = 0

    # the "5": its shape at SS x, the signed distance per native pixel (the SS x SS block's mean)
    shape = _shape(digit, height)
    canvas = np.zeros((h * SS, w * SS), bool)
    y0, x0 = top * SS, int(round(cx * SS - shape.shape[1] / 2))
    canvas[y0:y0 + shape.shape[0], x0:x0 + shape.shape[1]] = shape
    sd = (_signed_distance(canvas) / SS).reshape(h, SS, w, SS).mean((1, 3))
    ang = _angle(sd)

    grey, alpha = _profile(cells, digits, to_word > WORD_REACH)
    lo, hi, step = PROFILE_D
    fb = np.clip((sd - lo) / step, 0, grey.shape[1] - 1)
    b0 = np.floor(fb).astype(int)
    b1 = np.minimum(b0 + 1, grey.shape[1] - 1)
    tb = fb - b0
    fk = (ang + np.pi) / (2 * np.pi) * ANGLES
    k0 = np.floor(fk).astype(int) % ANGLES
    k1 = (k0 + 1) % ANGLES
    tk = fk - np.floor(fk)

    def look(t):
        return (t[k0, b0] * (1 - tb) + t[k0, b1] * tb) * (1 - tk) + (t[k1, b0] * (1 - tb) + t[k1, b1] * tb) * tk
    g, a = look(grey), look(alpha)
    a[sd < lo] = 0

    # the digit over the word (premultiplied "over")
    da, wa = a / 255, word[..., 3] / 255
    oa = da + wa * (1 - da)
    rgb = (g[..., None] * da[..., None] + word[..., :3] * (wa * (1 - da))[..., None]) / np.maximum(oa, 1e-6)[..., None]
    out = np.zeros((h, w, 4), np.uint8)
    out[..., :3] = np.clip(np.rint(rgb), 0, 255)
    out[..., 3] = np.clip(np.rint(oa * 255), 0, 255)
    out[out[..., 3] == 0] = 0
    return out


def ci8(img):
    """uint8 RGBA -> (GX CI8 bytes, RGB5A3 palette bytes (256 entries), width, height), padded to 8 x 4 tiles."""
    import numpy as np
    from icon_bank import ci8 as quantize, rgba_to_rgb5a3, _tile_ci8
    h, w = img.shape[:2]
    W, H = w + (-w % 8), h + (-h % 4)
    tex = np.zeros((H, W), np.uint16)
    tex[:h, :w] = rgba_to_rgb5a3(img)
    idx, pal, _ = quantize(tex)
    return _tile_ci8(idx), pal.astype(">u2").tobytes(), W, H


def decode_ci8(image, palette, w, h):
    import numpy as np
    from icon_bank import rgb5a3_to_rgba, _untile_ci8
    return rgb5a3_to_rgba(np.frombuffer(palette, ">u2")[_untile_ci8(image, w, h)])


def save_preview(path, cells, *encoded, zoom=4):
    """Level 1-4, the new pictures (as made) and as the game will decode them, side by side on the popup's blue."""
    import numpy as np
    from PIL import Image
    tiles = [Image.fromarray(np.ascontiguousarray(c)) for c in list(cells) + list(encoded)]
    gap = 8
    sheet = Image.new("RGBA", (sum(t.width + gap for t in tiles) + gap, max(t.height for t in tiles) + 2 * gap),
                      (38, 62, 128, 255))
    x = gap
    for t in tiles:
        sheet.alpha_composite(t, (x, gap))
        x += t.width + gap
    sheet.resize((sheet.width * zoom, sheet.height * zoom), Image.NEAREST).save(path)
