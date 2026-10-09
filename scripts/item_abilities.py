"""Item abilities and hitting abilities: extra rows on the character info cards and captain select, and the cards'
4-line layout. See docs/abilities.md.

A character definition names its item (or special) ability, and the card shows it as a row like the stock
skills: "item_ability": "Monkey Business" (the item they bat with) or "special_ability": "Piranha Patch" (a
non-item special). The name is only a label: gameplay does not read it. A "hitting_ability" (star_move_labels:
"Star Get", "Showstopper", "Piranha Patch") is a row of its own too, with the bat icon.

The card (docs/abilities.md "The card"). Three copies of one status widget draw it: FUN_8006E260 (character
select), FUN_8007F0FC (batting-order bubble) and FUN_8031D81C (the third screen). Each copies the character's
stats row, collects the nonzero skills as (category, id) pairs in stack slots at r1+0x20 (8 bytes each; r31 =
count) in the order star pitch (+8), star swing (+9), fielding (+10), baserunning (+11), and then draws
  - one skill: icon in pane 2, label in pane 5 (the middle line),
  - two skills: icons in panes 7-8, labels in panes 9-10 (two lines spaced out),
  - three: icons in panes 1.., labels in panes 4.. (three lines),
  - four (ours): icons in panes 14-17, labels in panes 18-21 (FOUR_PANES), new nodes of the card elements.
A pane is a node of the element the widget draws (file 19 element 0xC0; 0x59 has the same panes): the widget
writes (pane, row) into the draw's override list and draws that one node. The icon row is HEADERS[category], the
label row PTRS[category][id] (dir 119 file 19).

Two categories are appended after the four stock ones:
  4 item:    the "?" icon, ITEM_LABELS[ITEM_TABLE[id]]; appended last.
  5 hitting: the bat icon (0xD2), the star swing long table [HIT_TABLE[id]] (star_move_labels' slots 16..);
             inserted right after the star pitch / star swing entries, so the card reads pitch, swing, hitting,
             fielding, running, item. A character with a real star swing and a hitting ability (Luma: Star
             Shower and Star Get) shows both.
Per widget:
  +0x100 `cmpwi cr1,r31,1` (the join after the list is built, also reached when no character is shown) ->
         a branch to our block: if a character is shown (byte r1+0x8) and its id (s16 r1+0x14) is 0..max_id:
         insert (5, HIT_TABLE[id]) and append (4, ITEM_TABLE[id]) while fewer than MAX_SHOWN are listed; then
         r24 = HEADERS (our 6-entry icon table) and the replaced compare, back to +0x104.
  +0x154 `subi r24,r2,0x7fc0` (the stock 4-entry icon table) -> nop (r24 is set by our block).
  +0x1C8 / +0x1D0 `lis r26,0x8064` / `subi r26,r26,0x5480` (LABEL_TABLES) -> our 6-pointer table PTRS: the four
         stock pointers (copied, so other patches to those tables still apply), ITEM_LABELS, and the long star
         swing table (star_move_labels.SwingCard.patch sets entries 1 and 5).
  +0x140 `li r30,1` / +0x1C4 `li r30,4` (the 3-line icon / label panes) -> 14 / 18 when 4 are listed.
charbuild refuses a character whose lines would come to five (star_move_labels.apply), so the guard never
drops one in practice.

Captain select (FUN_802CA65C, file 18 element 0x17: icons panes 0-2, labels panes 3-5, one layout) does the same
(Card.patch_captain): its list (r1+0x8, r27 = count) gets the hitting and item rows at 0x802CA770, its icon table
(r2-0x60F0) and label pointers (0x806A17B8) are swapped for 6-entry copies, and the 4th line uses two new nodes
under the stock three (panes 6, 7). The labels are painted into file 18 (captain_layout_bytes).

The icon (ICON_PNG, draw_icon): a "?" block made from the game's own art: the gold block of dir 119 file 12 row
0x1B (the left half of a 9-slice box, mirrored to a square) and the white "?" of dir 119 file 11 row 0x1EE (the
"?" of the items list), its grey outline turned dark brown to read on gold; reduced to 17 x 17 in a 19 x 19
cell with the stock icons' dark 1-pixel edge. Specials use the same icon (ICONS[kind]; a distinct one would be one
more row). None now: Piranha Patch is a hitting ability, Shadow Clone a running one (star_move_labels).
The labels are abilities.label_image(text): the stock labels' own glyphs.
"""
import struct
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
ICON_PNG = ROOT / "captains/item_ability_icon.png"      # 19 x 19 RGBA, made by draw_icon()

WIDGETS = (0x8006E260, 0x8007F0FC, 0x8031D81C)          # character select, batting-order bubble, third screen
HOOK, R24_AT, LIS_AT, ADDI_AT = 0x100, 0x154, 0x1C8, 0x1D0
STOCK_WORDS = {HOOK: 0x2C9F0001,                         # cmpwi cr1,r31,0x1
               R24_AT: 0x3B028040,                       # subi r24,r2,0x7fc0
               LIS_AT: 0x3F408064,                       # lis r26,-0x7f9c
               ADDI_AT: 0x3B5AAB80}                      # subi r26,r26,0x5480
LIST_READS = {0x40: 0x88010008,                          # lbz r0,0x8(r1): a character is shown
              0x54: 0xA8010014,                          # lha r0,0x14(r1): its id
              0x74: 0x88010048}                          # lbz r0,0x48(r1): stats row +8 (star pitch)
R2 = 0x8079EDC0
STOCK_ICONS_AT, STOCK_ICONS = R2 - 0x7FC0, (0xD0, 0xD2, 0xD3, 0xD4)
CATEGORY, HIT_CATEGORY, MAX_SHOWN = 4, 5, 4
CATEGORIES = 6                                          # pitch, swing, fielding, running, item, hitting
BAT_ICON = STOCK_ICONS[1]                               # the hitting row's icon: the star swing's bat (0xD2)
# the 4-line layout: the 3-line pane choice `li r30,1` (icons) / `li r30,4` (labels) -> FOUR_PANES when 4 are listed
ICON_PANE_AT, LABEL_PANE_AT = 0x140, 0x1C4
PANE_WORDS = {ICON_PANE_AT: 0x3BC00001, LABEL_PANE_AT: 0x3BC00004}
FOUR_PANES = (14, 18)                                   # first icon / label pane of 4 lines (element 0xC0 has 14 nodes)

KINDS = {"item_ability": "item", "special_ability": "special"}
ICONS = {"item": "item", "special": "item"}             # kind -> icon (one icon for both, for now)
# Names defined for a character that has none yet (so their glyphs are checked).
SPARE = ()
# Stock characters (no characters/*.json) with an item ability: id -> (character name, kind, ability name).
STOCK = {0x34: ("Fire Bro", "item", "Freaky Flames"),   # his item is Fireballs (batter_items FIXED_ITEM); Nick's name
         0x25: ("King Boo", "item", "Boo Crew"),         # always Boo (batter_items FIXED_ITEM); placeholder, Nick names it
         0x09: ("Bowser", "item", "Freaky Flames")}      # always Fireballs (batter_items FIXED_ITEM); Fire Bro's name (Nick)


def with_stock(chars):
    """chars (normalized) plus a minimal entry per STOCK id no definition covers, in id order like labels(): the
    list apply's tables, Card and the art all use (star_move_labels still gets charbuild's chars)."""
    import abilities
    have = {c["id"] for c in chars}
    out = list(chars)
    for cid, (name, kind, ability) in STOCK.items():
        if cid not in have:
            abilities.text_alpha(ability)               # asserts every letter has a stock glyph, as of() does
            out.append(dict(id=cid, name=name, item_ability=(kind, ability)))
    return sorted(out, key=lambda c: c["id"])


def of(c):
    """normalize: (kind, name) of a definition's item / special ability, or None. The name must be drawable
    from the stock label glyphs (abilities.text_alpha)."""
    import abilities
    got = [(KINDS[k], c[k]) for k in KINDS if c.get(k) is not None]
    assert len(got) <= 1, f"{c.get('name')}: both item_ability and special_ability"
    if not got:
        return None
    kind, name = got[0]
    assert isinstance(name, str) and name and name.strip() == name, f"{c.get('name')}: bad ability name {name!r}"
    abilities.text_alpha(name)                          # asserts every letter has a stock glyph
    return kind, name


def labels(chars):
    """[name, ...] in the order of first use by id: index k + 1 of ITEM_LABELS."""
    out = []
    for c in sorted(chars, key=lambda c: c["id"]):
        if c.get("item_ability") and c["item_ability"][1] not in out:
            out.append(c["item_ability"][1])
    return out


def rows(first_row, chars):
    """{"item": icon row, name: label row, ...}: the icon row, then one label row per labels(chars)."""
    out = {ICONS["item"]: first_row}
    for k, name in enumerate(labels(chars)):
        out[name] = first_row + 1 + k
    return out


# --- the DOL ---------------------------------------------------------------------------------------------------
def hit_slots(chars):
    """{character id: star swing label slot} of every hitting ability (star_move_labels.more_names' slots 16..)."""
    import star_move_labels
    slot = {n: s for s, n in star_move_labels.more_names(chars).items() if s >= star_move_labels.FIRST_HITTING}
    return {c["id"]: slot[c["hitting_ability"]] for c in chars if c.get("hitting_ability")}


def lines(skills4, item, hitting):
    """How many lines a card shows: the nonzero stats skills, the item row, the hitting row."""
    return sum(1 for b in skills4 if b) + bool(item) + bool(hitting)


def _extras(a, list_off, count, id_off, max_id, item_table, hit_table, done):
    """Emit: id (s16 at r1+id_off) in 0..max_id -> insert (HIT_CATEGORY, HIT_TABLE[id]) after the entries of
    category <= 1 and append (CATEGORY, ITEM_TABLE[id]), each while fewer than MAX_SHOWN are listed. The list: 8-byte
    (category, id) entries at r1+list_off, count in register count. Uses r0, r3, r10-r12."""
    a.lha("r3", id_off, "r1").cmpwi("r3", 0).blt(done)
    a.cmpwi("r3", max_id).bgt(done)
    a.load_addr("r12", hit_table).lbzx("r0", "r12", "r3")
    a.cmpwi("r0", 0).beq("item")
    a.cmpwi(count, MAX_SHOWN).bge("item")
    a.li("r10", 0)                                                # r10 = where: the first entry of category > 1
    a.label("find")
    a.cmpw("r10", count).bge("found")
    a.slwi("r12", "r10", 3).addi("r12", "r12", list_off).lwzx("r11", "r1", "r12")
    a.cmpwi("r11", 1).bgt("found")
    a.addi("r10", "r10", 1).b("find")
    a.label("found")
    a.mr("r11", count)                                            # move entries where..count-1 up one
    a.label("shift")
    a.cmpw("r11", "r10").ble("put")
    a.slwi("r12", "r11", 3).addi("r12", "r12", list_off - 8).add("r12", "r12", "r1")
    a.lwz("r3", 0, "r12").stw("r3", 8, "r12").lwz("r3", 4, "r12").stw("r3", 12, "r12")
    a.addi("r11", "r11", -1).b("shift")
    a.label("put")
    a.slwi("r12", "r10", 3).addi("r12", "r12", list_off).add("r12", "r12", "r1")
    a.li("r3", HIT_CATEGORY).stw("r3", 0, "r12").stw("r0", 4, "r12")
    a.addi(count, count, 1)
    a.lha("r3", id_off, "r1")
    a.label("item")
    a.load_addr("r12", item_table).lbzx("r0", "r12", "r3")
    a.cmpwi("r0", 0).beq(done)
    a.cmpwi(count, MAX_SHOWN).bge(done)
    a.slwi("r12", count, 3).addi("r12", "r12", list_off).add("r12", "r12", "r1")
    a.li("r3", CATEGORY).stw("r3", 0, "r12").stw("r0", 4, "r12")
    a.addi(count, count, 1)


def _branch(dol, at, word, target):
    """Replace the stock word at `at` (checked) with a branch to target."""
    from ppc import Asm
    assert dol.u32(at) == word, f"0x{at:08X}: {dol.u32(at):08X}, expected {word:08X}"
    dol.w32(at, Asm(at).b(target).assemble_word())


class Card:
    """What apply placed: the row tables, filled in by layout_bytes once the rows exist; patch_captain does captain
    select (after star_move_labels' captain tables are final)."""
    def __init__(self, dol, chars, item_labels, headers, ptrs, item_table, hit_table, max_id, space):
        self.dol, self.chars, self.item_labels, self.headers = dol, chars, item_labels, headers
        self.ptrs = ptrs                                 # the 6-pointer label table (star_move_labels: categories 1, 5)
        self.item_table, self.hit_table, self.max_id = item_table, hit_table, max_id
        self.first_row = None
        # captain select's tables and stubs, placed now (the item section is closed after apply)
        n_hit = max(hit_slots(chars).values(), default=0) + 1
        self.cap_item_labels = space.put(bytes(2 * (1 + len(labels(chars)))), 4)
        self.cap_hit_labels = space.put(bytes(2 * n_hit), 4)
        self.cap_headers = space.put(bytes(2 * CATEGORIES), 4)
        self.cap_ptrs = space.put(bytes(4 * CATEGORIES), 4)
        self.cap_stubs = _captain_stubs(space, max_id, item_table, hit_table, self.cap_headers)

    def set_rows(self, first_row):
        r = rows(first_row, self.chars)
        self.dol.write(self.item_labels, struct.pack(f">{1 + len(labels(self.chars))}H", 0xFFFF,
                                                     *(r[n] for n in labels(self.chars))))
        self.dol.write(self.headers + 2 * CATEGORY, struct.pack(">H", r[ICONS["item"]]))

    def layout_bytes(self, data):
        """One language's dir 119 file 19 (after every other step that adds rows) -> with the icon and label rows
        appended and the 4-line nodes of the card elements; the DOL tables point at the rows (the same rows in every
        language: asserted)."""
        import layout
        lay = layout.Layout(data)
        first = add_art(lay, self.chars)
        add_four_lines(lay)
        assert self.first_row in (None, first), f"item ability rows at {first} here, {self.first_row} in another copy"
        self.first_row = first
        self.set_rows(first)
        return lay.to_bytes()

    def captain_layout_bytes(self, data):
        """One language's dir 119 file 18, after star_move_labels.captain_layout_bytes: the icon, item and hitting
        label rows (captain_rows) and the 4th line's nodes of element 0x17."""
        import layout
        lay = layout.Layout(data)
        add_captain_art(lay, self.chars)
        add_captain_lines(lay)
        return lay.to_bytes()

    def patch_captain(self, dol):
        """Captain select: the tables (the four pointers of 0x806A17B8 as they stand now, star_move_labels' long
        pitch / swing copies included) and the hooks. Returns log lines."""
        from ppc import Asm
        import star_move_labels as sml
        r = captain_rows(self.chars)
        names = labels(self.chars)
        dol.write(self.cap_item_labels, struct.pack(f">{1 + len(names)}H", 0xFFFF, *(r[n] for n in names)))
        hits = hit_slots(self.chars)
        n_hit = max(hits.values(), default=0) + 1
        hit_names = sml.more_names(self.chars)
        table = [0xFFFF] * n_hit
        for s in set(hits.values()):
            table[s] = r[hit_names[s]]
        dol.write(self.cap_hit_labels, struct.pack(f">{n_hit}H", *table))
        stock_icons = struct.unpack(">4H", dol.read(CAPTAIN_ICONS_AT, 8))
        assert stock_icons == CAPTAIN_ICONS, f"captain icon rows {[hex(i) for i in stock_icons]}"
        dol.write(self.cap_headers, struct.pack(f">{CATEGORIES}H", *stock_icons, r[ICONS["item"]], stock_icons[1]))
        dol.write(self.cap_ptrs, dol.read(CAPTAIN_TABLES, 16) + struct.pack(">2I", self.cap_item_labels, self.cap_hit_labels))
        for at, word in CAPTAIN_WORDS.items():
            assert dol.u32(at) == word, f"0x{at:08X}: {dol.u32(at):08X}, expected {word:08X}"
        hook, icons, pane_icon, pane_label = self.cap_stubs
        _branch(dol, CAPTAIN_HOOK, CAPTAIN_WORDS[CAPTAIN_HOOK], hook)
        _branch(dol, CAPTAIN_ICONS_SET, CAPTAIN_WORDS[CAPTAIN_ICONS_SET], icons)
        _branch(dol, CAPTAIN_ICON_PANE, CAPTAIN_WORDS[CAPTAIN_ICON_PANE], pane_icon)
        dol.w32(CAPTAIN_ICON_PANE_STH, STH_R7)                     # sth r28,0(r4) -> sth r7,0(r4) (the pane stub's r7)
        _branch(dol, CAPTAIN_LABEL_PANE, CAPTAIN_WORDS[CAPTAIN_LABEL_PANE], pane_label)
        p = self.cap_ptrs
        dol.w32(CAPTAIN_LIS, Asm(0).lis("r25", (p + 0x8000) >> 16).assemble_word())
        dol.w32(CAPTAIN_ADDI, Asm(0).addi("r25", "r25", (p & 0xFFFF) - 0x10000 if p & 0x8000 else p & 0xFFFF).assemble_word())
        return [f"captain select: hitting / item rows and a 4th line (FUN_802CA65C; pointer table 0x{p:08X}, file 18 "
                f"rows {min(r.values())}..{max(r.values())}, element 0x{CAPTAIN_ELEMENT:X} 4-line panes {CAPTAIN_FOUR_PANES[0]}.. / {CAPTAIN_FOUR_PANES[1]}..)"]


# captain select (FUN_802CA65C): its list at r1+0x8 (r27 = count), stats copy at r1+0x28 (first u16 = the id)
CAPTAIN_TABLES = 0x806A17B8                             # u16 *[4], star_move_labels.CAPTAIN_LABEL_TABLES
CAPTAIN_ICONS_AT, CAPTAIN_ICONS = R2 - 0x60F0, (0x5, 0x7, 0x8, 0x9)   # file 18 rows: ball, bat, glove, shoe
CAPTAIN_HOOK = 0x802CA770                               # cmpwi r27,1: the join after the list
CAPTAIN_LIS, CAPTAIN_ADDI = 0x802CA790, 0x802CA79C      # lis r25,0x806A / addi r25,r25,0x17B8
CAPTAIN_ICONS_SET = 0x802CA7A8                          # subi r31,r2,0x60f0
CAPTAIN_ICON_PANE, CAPTAIN_ICON_PANE_STH = 0x802CA7B0, 0x802CA7CC   # stb r28,0x2c(r26) / sth r28,0(r4): icon pane i
CAPTAIN_LABEL_PANE = 0x802CA7E8                         # addi r6,r28,3: label pane i + 3
CAPTAIN_WORDS = {CAPTAIN_HOOK: 0x2C1B0001, CAPTAIN_LIS: 0x3F20806A, CAPTAIN_ADDI: 0x3B3917B8,
                 CAPTAIN_ICONS_SET: 0x3BE29F10, CAPTAIN_ICON_PANE: 0x9B9A002C, CAPTAIN_ICON_PANE_STH: 0xB3840000,
                 CAPTAIN_LABEL_PANE: 0x38DC0003}
STH_R7 = 0xB0E40000                                     # sth r7,0(r4)
CAPTAIN_ELEMENT, CAPTAIN_FOUR_PANES = 0x17, (6, 10)     # 4 lines: icons panes 6-9, labels 10-13 (new nodes)


def _captain_stubs(space, max_id, item_table, hit_table, headers):
    """(hook, icon table, icon pane, label pane) stubs for FUN_802CA65C."""
    from ppc import Asm
    a = Asm(space.here)
    a.cmpwi("r27", 1).blt("done")                               # nothing listed: no character (or no skills)
    _extras(a, 0x8, "r27", 0x28, max_id, item_table, hit_table, "done")
    a.label("done")
    a.cmpwi("r27", 1)                                           # the replaced instruction
    a.b(CAPTAIN_HOOK + 4)
    hook = space.put(a.assemble(), 4)
    a = Asm(space.here)
    a.load_addr("r31", headers).b(CAPTAIN_ICONS_SET + 4)
    icons = space.put(a.assemble(), 4)
    a = Asm(space.here)                                         # r7 = icon pane: i, or 6 + i with 4 lines
    a.mr("r7", "r28").cmpwi("r27", MAX_SHOWN).bne("set").addi("r7", "r28", CAPTAIN_FOUR_PANES[0])
    a.label("set")
    a.stb("r7", 0x2C, "r26").b(CAPTAIN_ICON_PANE + 4)
    pane_icon = space.put(a.assemble(), 4)
    a = Asm(space.here)                                         # r6 = label pane: i + 3, or 10 + i with 4 lines
    a.addi("r6", "r28", 3).cmpwi("r27", MAX_SHOWN).bne("set").addi("r6", "r28", CAPTAIN_FOUR_PANES[1])
    a.label("set")
    a.b(CAPTAIN_LABEL_PANE + 4)
    pane_label = space.put(a.assemble(), 4)
    return hook, icons, pane_icon, pane_label


def apply(dol, space, chars, max_id, skills):
    """Tables and the three widget hooks (space: a charbuild.Space in a text section). chars: normalized
    (c["item_ability"] = (kind, name) or None, c["hitting_ability"]); skills(id) -> the 4 stats bytes +8..+11.
    Returns (log lines, Card or None). The item label rows are 0xFFFF (nothing drawn) until Card.layout_bytes has
    run; the hitting labels come from star_move_labels' long star swing table (SwingCard.patch)."""
    from ppc import Asm
    import abilities
    chars = with_stock(chars)
    names = labels(chars)
    hits = hit_slots(chars)
    if not names and not hits:
        return [], None
    size = max_id + 1 + (-(max_id + 1) % 4)
    table, hit_table = bytearray(size), bytearray(size)
    for c in chars:
        shown = lines(skills(c["id"]), c.get("item_ability"), c.get("hitting_ability"))
        assert shown <= MAX_SHOWN, (f"{c['name']}: the card would need {shown} lines (it shows at most {MAX_SHOWN} of "
                                    f"star pitch, star swing, hitting, fielding, baserunning, item)")
        if c.get("item_ability"):
            table[c["id"]] = 1 + names.index(c["item_ability"][1])
    for cid, s in hits.items():
        hit_table[cid] = s
    stock_ptrs = struct.unpack(">4I", dol.read(abilities.LABEL_TABLES, 16))
    icons = struct.unpack(">4H", dol.read(STOCK_ICONS_AT, 8))
    assert icons == STOCK_ICONS, f"unexpected icon rows {[hex(i) for i in icons]}"
    item_labels = space.put(struct.pack(f">{1 + len(names)}H", *([0xFFFF] * (1 + len(names)))), 4)
    headers = space.put(struct.pack(f">{CATEGORIES}H", *icons, 0xFFFF, BAT_ICON), 4)
    ptrs = space.put(struct.pack(f">{CATEGORIES}I", *stock_ptrs, item_labels, stock_ptrs[1]), 4)   # [5]: SwingCard.patch
    item_table = space.put(bytes(table), 4)
    hit_at = space.put(bytes(hit_table), 4)
    for base in WIDGETS:
        for off, word in {**STOCK_WORDS, **LIST_READS, **PANE_WORDS}.items():
            assert dol.u32(base + off) == word, f"0x{base + off:08X}: {dol.u32(base + off):08X}, expected {word:08X}"
        a = Asm(space.here)
        a.lbz("r0", 0x8, "r1").cmpwi("r0", 0).beq("done")           # no character shown
        _extras(a, 0x20, "r31", 0x14, max_id, item_table, hit_at, "done")
        a.label("done")
        a.load_addr("r24", headers)
        a.cmpwi("r31", 1, cr=1)                                     # the replaced instruction
        a.b(base + HOOK + 4)
        stub = space.put(a.assemble(), 4)
        dol.w32(base + HOOK, Asm(base + HOOK).b(stub).assemble_word())
        dol.w32(base + R24_AT, 0x60000000)
        lo = ptrs & 0xFFFF
        dol.w32(base + LIS_AT, Asm(0).lis("r26", (ptrs + 0x8000) >> 16).assemble_word())
        dol.w32(base + ADDI_AT, Asm(0).addi("r26", "r26", lo - 0x10000 if lo & 0x8000 else lo).assemble_word())
        for at, first in zip((ICON_PANE_AT, LABEL_PANE_AT), FOUR_PANES):   # r30 = the first pane: 4 lines -> ours
            a = Asm(space.here)
            a.li("r30", PANE_WORDS[at] & 0xFFFF).cmpwi("r31", MAX_SHOWN).bne("back").li("r30", first)
            a.label("back")
            a.b(base + at + 4)
            dol.w32(base + at, Asm(base + at).b(space.put(a.assemble(), 4)).assemble_word())
    card = Card(dol, chars, item_labels, headers, ptrs, item_table, hit_at, max_id, space)
    who = ", ".join(f"{c['name']} {c['item_ability'][1]!r}" for c in chars if c.get("item_ability"))
    hwho = ", ".join(f"{c['name']} {c['hitting_ability']!r}" for c in chars if c.get("hitting_ability"))
    return [f"item ability: category 4 on the info cards (3 widgets, tables 0x{item_labels:08X}..): {who}",
            f"hitting ability: category 5 (bat icon) on the info cards: {hwho}; up to {MAX_SHOWN} lines "
            f"(4 lines: panes {FOUR_PANES[0]}.. / {FOUR_PANES[1]}..)"], card


# --- the 4-line layout (file 19 elements 0xC0 / 0x59, file 18 element 0x17) ------------------------------------------
# The card (0xC0, and 0x59 with the same panes): the frame's inner area is y -40..27 in 0xC0 (the name bar's band
# from y 28), 3 lines at a 19-px pitch (-25, -6, 13) with 19-px icons. Four at that pitch would not fit, so the 4-line
# layout is 15 px apart with the icons at 0.75 (14 px), as the stock element 0x56 draws its 3 lines 14 px apart with
# 0.7 icons: labels unscaled (the text keeps its size), no two label cells overlapping, centred on the 3-line block
# (-6). 0x59: the same, centred on its 3 lines (37).
FOUR_Y = {0xC0: (-29, -14, 1, 16), 0x59: (15, 30, 45, 60)}
FOUR_ICON_SCALE = 0.75
CARD_NODES = {0xC0: 14, 0x59: 13}                       # stock node counts
STOCK_LINES = {0xC0: ((-25, -6, 13), (-25, -6, 13)),      # the 3-line nodes' y: icons (1-3), labels (4-6)
               0x59: ((17, 37, 57), (18, 37, 56))}
KEY_XY = (0x08, 0x18, 0x1C)                             # a key's x, y (three copies)
KEY_SCALE = 0x38                                        # type 4: f32 scale x, y


def _key_node(blob, y, scale=None):
    """A one-key node blob (u16 count, u16 stride, key) with the key moved to y (and scaled)."""
    b = bytearray(blob)
    cnt, stride = struct.unpack_from(">HH", b, 0)
    assert cnt == 1, "expected a one-key node"
    for o in KEY_XY:
        struct.pack_into(">h", b, 4 + o + 2, y)
    if scale is not None:
        struct.pack_into(">ff", b, 4 + KEY_SCALE, scale, scale)
    return bytes(b)


def key_info(lay, k, node):
    """(ref, x, y, scale) of node's first key in element k."""
    e = lay.elements[k]
    o = lay.nodes(k)[node][0]
    return (struct.unpack_from(">H", e, o + 6)[0], *struct.unpack_from(">hh", e, o + 8),
            struct.unpack_from(">f", e, o + KEY_SCALE)[0])


def add_four_lines(lay):
    """File 19: nodes FOUR_PANES[0]..+3 (icons) and FOUR_PANES[1]..+3 (labels) in each card element (FOUR_Y); 0x59
    first gets a copy of its icon node 1 as node 13, a pane nothing draws, so both elements have the same panes."""
    for k, ys in FOUR_Y.items():
        blobs = lay.node_blobs(k)
        assert len(blobs) == CARD_NODES[k], f"element 0x{k:X}: {len(blobs)} nodes"
        for i, (y, ly) in enumerate(zip(*STOCK_LINES[k])):
            assert key_info(lay, k, 1 + i)[0] == 0xD0 and key_info(lay, k, 1 + i)[2] == y, f"element 0x{k:X} icon {i}"
            assert key_info(lay, k, 4 + i)[0] == 0x197 and key_info(lay, k, 4 + i)[2] == ly, f"element 0x{k:X} label {i}"
        blobs = list(blobs)
        while len(blobs) < FOUR_PANES[0]:
            blobs.append(blobs[1])
        blobs += [_key_node(blobs[1], y, FOUR_ICON_SCALE) for y in ys]
        blobs += [_key_node(blobs[4], y) for y in ys]
        lay.set_nodes(k, blobs)


# Captain select (file 18 element 0x17, drawn at y 102 of the screen's element 0x2E): 3 lines at an 18-px pitch
# (labels y -1, 17, 35, their cells' tops; icons y 6, 24, 42, 19 px) on a light rounded backdrop that ends at about
# y 70 (its left edge curving in below ~60). A 4th line at 18 px would hang its icon off that edge, so 4 lines are
# 15 px apart from the stock top (labels -1, 14, 29, 44: the last ends at 59), icons at 0.75 as on the cards.
CAPTAIN_FOUR_Y = (-1, 14, 29, 44)                       # label cell tops; the icon centres are 7 lower, as stock


def add_captain_lines(lay):
    """File 18 element 0x17: nodes 6-9 (icons, 0.75) and 10-13 (labels) for 4 lines (CAPTAIN_FOUR_Y)."""
    blobs = lay.node_blobs(CAPTAIN_ELEMENT)
    assert len(blobs) == CAPTAIN_FOUR_PANES[0], f"file 18 element 0x17: {len(blobs)} nodes"
    for i, (iy, ly) in enumerate(((6, -1), (24, 17), (42, 35))):
        assert key_info(lay, CAPTAIN_ELEMENT, i)[:3:2] == (5, iy) and key_info(lay, CAPTAIN_ELEMENT, 3 + i)[:3:2] == (0x66, ly), \
            f"file 18 element 0x17 line {i}"
    lay.set_nodes(CAPTAIN_ELEMENT, list(blobs) + [_key_node(blobs[0], y + 7, FOUR_ICON_SCALE) for y in CAPTAIN_FOUR_Y]
                  + [_key_node(blobs[3], y) for y in CAPTAIN_FOUR_Y])


# --- captain select's rows (dir 119 file 18) ----------------------------------------------------------------------
CAPTAIN_EXTRA_SIZE = (128, 512)                         # one CI4 page: 32 cells of 112 x 15 at a 16-px pitch


def captain_names(chars):
    """The file-18 label names in row order: the item labels (labels()), then the hitting names (slot order)."""
    import star_move_labels as sml
    hit = sml.more_names(chars)
    return labels(chars) + [hit[s] for s in sorted(set(hit_slots(chars).values()))]


def captain_rows(chars):
    """{"item": icon row, name: row}: after star_move_labels' captain rows (Clamber Jump the last)."""
    import star_move_labels as sml
    first = max(sml.captain_fielding_rows().values()) + 1
    out = {ICONS["item"]: first}
    for k, n in enumerate(captain_names(chars)):
        out[n] = first + 1 + k
    return out


def add_captain_art(lay, chars, icon=None):
    """File 18: the icon (its own RGB5A3 page, template: the ball icon's page) and the item / hitting labels
    (captain_grid on a CI4 page with page 46's palette, like the other captain labels)."""
    from PIL import Image
    import star_move_labels as sml
    from captain_art import rgb5a3
    from char_names import GX_RGB5A3
    r = captain_rows(chars)
    assert len(lay.rows) == r[ICONS["item"]], f"captain item rows: row {len(lay.rows)}, expected {r[ICONS['item']]}"
    icon = icon or Image.open(ICON_PNG).convert("RGBA")
    page_img = Image.new("RGBA", ICON_PAGE, (0, 0, 0, 0))
    page_img.paste(icon, (0, 0))
    w, h = ICON_PAGE
    template = struct.unpack_from(">H", lay.rows[CAPTAIN_ICONS[0]])[0]
    page = lay.add_texture(rgb5a3(page_img), w, h, GX_RGB5A3, template_page=template)
    lay.add_row(page, 0, 0, ICON_CELL[0] / w, ICON_CELL[1] / h)
    names = captain_names(chars)
    assert 16 * len(names) <= CAPTAIN_EXTRA_SIZE[1], f"{len(names)} captain labels"
    lpage = sml.add_extra_page(lay, sml.CAPTAIN_PAGE, CAPTAIN_EXTRA_SIZE)
    for k, n in enumerate(names):
        assert len(lay.rows) == r[n]
        sml._paint(lay, lpage, sml.extra_cell(k), captain_grid(n))


def captain_grid(name):
    """name's label as 15 rows of 112 page-46 palette indices (hex strings): the cards' label_image (the same art,
    squeezed the same way: Monkey Business at 77 %, more than star_move_labels.text_grid allows), its alphas as
    indices."""
    import abilities
    img = abilities.label_image(name).getchannel("A")
    return tuple("".join("0123456789abcdef"[abilities.LABEL_ALPHA.index(img.getpixel((x, y)))]
                         for x in range(abilities.CELL[0])) for y in range(abilities.CELL[1]))


# --- the art ---------------------------------------------------------------------------------------------------
ICON_CELL = (19, 19)
BLOCK_SRC, QMARK_SRC = (12, 0x1B), (11, 0x1EE)        # (dir 119 file, row)
QMARK_EDGE = (70, 35, 0)                                # the "?"'s outline: grey -> dark brown
EDGE = (24, 16, 40, 200)                                # the stock icons' dark edge


def _premul_resize(img, size):
    from PIL import Image
    return img.convert("RGBa").resize(size, Image.LANCZOS).convert("RGBA")


def row_image(file_bytes, row):
    """RGBA crop of one resource row of a dir 119 layout file (CI4/CI8 with a palette, or direct formats)."""
    import layout
    from particle_textures import decode, rgb5a3, TL
    lay = layout.Layout(file_bytes)
    page, _, v1, u1, v2, u2 = struct.unpack(">HH4f", lay.rows[row])
    d = lay.descs[page]
    io, po, h, w = struct.unpack_from(">IIHH", d, 0)
    fmt, n, pf = d[0x17], struct.unpack_from(">H", d, 0x18)[0], d[0x1A]
    bpp = {0: 4, 1: 8, 2: 8, 3: 16, 4: 16, 5: 16, 6: 32, 8: 4, 9: 8, 0xE: 4}[fmt]
    pal = ([TL.get(pf, rgb5a3)(struct.unpack_from(">H", file_bytes, layout.TEX_BASE + po + 2 * k)[0])
            for k in range(n)] if fmt in (8, 9) else None)
    img = decode(fmt, w, h, file_bytes[layout.TEX_BASE + io:layout.TEX_BASE + io + w * h * bpp // 8], pal)
    return img.crop((round(u1 * w), round(v1 * h), round(u2 * w), round(v2 * h))).convert("RGBA")


def draw_icon(block, qmark):
    """The item icon (RGBA ICON_CELL) from the game's block (file 12 row 0x1B) and "?" (file 11 row 0x1EE)."""
    from PIL import Image, ImageFilter, ImageOps
    half = block.crop((0, 0, 29, 58))                     # the rounded left half of the 45 x 59 box piece
    box = Image.new("RGBA", (58, 58))
    box.paste(half, (0, 0))
    box.paste(ImageOps.mirror(half), (29, 0))
    big = Image.new("RGBA", (76, 76))                     # drawn at 4x
    big.alpha_composite(_premul_resize(box, (66, 66)), (5, 5))
    q = qmark.crop(qmark.getchannel("A").getbbox())
    px = q.load()
    for y in range(q.size[1]):
        for x in range(q.size[0]):
            r, g, b, a = px[x, y]
            t = max(0.0, min(1.0, (r - 120) / 120))       # 0 = the grey outline, 1 = the white body
            px[x, y] = tuple(int(QMARK_EDGE[i] * (1 - t) + 255 * t) for i in range(3)) + (a,)
    q = _premul_resize(q, (round(q.size[0] * 56 / q.size[1]), 56))
    big.alpha_composite(q, ((76 - q.size[0]) // 2 + 1, (76 - q.size[1]) // 2 + 1))
    icon = Image.new("RGBA", ICON_CELL)
    icon.alpha_composite(_premul_resize(big, (17, 17)), (1, 1))
    ring = icon.getchannel("A").filter(ImageFilter.MaxFilter(3)).point(lambda v: min(EDGE[3], v))
    out = Image.new("RGBA", ICON_CELL, EDGE[:3] + (0,))
    out.putalpha(ring)
    out.alpha_composite(icon)
    return out


def icon_from_game(dol_path, dat_path):
    import dtna_toc
    from dol import Dol
    toc = dtna_toc.toc(Dol(dol_path))
    parts = []
    with open(dat_path, "rb") as fh:
        for f, row in (BLOCK_SRC, QMARK_SRC):
            off, length = toc[119][f]
            fh.seek(off)
            parts.append(row_image(fh.read(length), row))
    return draw_icon(*parts)


ICON_PAGE, ICON_TEMPLATE = (32, 32), 0x53               # the icon's own RGB5A3 page (template: the glove's page 83)


def label_images(chars):
    import abilities
    return [abilities.label_image(n) for n in labels(chars)]


def add_art(lay, chars, icon=None):
    """Append the icon row and one label row per labels(chars) to a file-19 layout.Layout (after its last row).
    The icon: its own RGB5A3 page (ICON_PNG at (0, 0)); the labels: their own CI8 / IA8 page like the other
    ability labels (abilities.label_page: black text, the label keys are white after recolour_labels).
    Returns the first row."""
    from PIL import Image
    import abilities
    from captain_art import rgb5a3
    from char_names import GX_RGB5A3, GX_CI8, GX_TL_IA8
    icon = icon or Image.open(ICON_PNG).convert("RGBA")
    assert icon.size == ICON_CELL
    page_img = Image.new("RGBA", ICON_PAGE, (0, 0, 0, 0))
    page_img.paste(icon, (0, 0))
    w, h = ICON_PAGE
    page = lay.add_texture(rgb5a3(page_img), w, h, GX_RGB5A3, template_page=ICON_TEMPLATE)
    first = lay.add_row(page, 0, 0, ICON_CELL[0] / w, ICON_CELL[1] / h)
    image, palette, lw, lh = abilities.label_page(label_images(chars))
    lpage = lay.add_texture(image, lw, lh, GX_CI8, template_page=abilities.LABEL_PAGE, palette=palette,
                            palette_format=GX_TL_IA8)
    for k in range(len(labels(chars))):
        lay.add_row(lpage, 0, 16 * k / lh, abilities.CELL[0] / lw, (16 * k + abilities.CELL[1]) / lh)
    return first
