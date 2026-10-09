"""Fielding abilities: the stock ids, our new ones, and the game's tables indexed by ability id.
See docs/abilities.md.

A character's fielding ability is byte +10 of its stats row (STAT_FIELDS "fielding ability"; characters/*.json
set it under "stats"). In a match the fielder's vtable +0x3C (FUN_8012C134, vtable 0x806434E8) returns it from the
match copy: *(r13-0x2C8) + fielding team (game2+0x2B) * 0x4FE + roster slot (F+0x28) * 0x8E + 10.

Stock ids 0-12 (NAMES). Every gameplay reader compares the id with a constant (1-8 in the dive FUN_801225DC,
2 jump, 9 Clamber, 10 Ball Dash, 11 Laser Beam FUN_800DE7B4, 12 Quick Throw), so an id past 12 does nothing
there. The only tables indexed by the id are the ability-name label rows:
  LABEL_TABLES 0x8063AB80: u16 *[4] = star pitch, star swing, FIELDING, baserunning label rows (dir 119 file 19,
    the select layout). Read by the three copies of the status widget: FUN_8006E260 (character select,
    Member_local), FUN_8007F0FC (batting-order bubble, Order_local) and FUN_8031D81C (a third copy, screen not
    identified). The fielding table 0x806233F8 has 13 rows (0 = 0xFFFF, none) and 3 zero words of padding
    before the baserunning table (0x80623418): FIELDING_SLOTS = 16, so ids 13-15 get a row in place.
  0x80650E90: the same list for Challenge mode's layout (dir 119 file 12, FUN_801C0014). That screen only
    shows ids <= 0x4C (`cmplwi r0,0x4c` at 0x801C007C), so it never shows a new character: left alone.
There is no per-ability description text in the game (dt_na messages only mention abilities inside character
taglines and Challenge-mode prompts).

CLAMBER_JUMP (14, Nick 2026-09-26: "make clamber jump a different ability from clamber so people can give either"):
Clamber, plus the solo buddy jump off the wall (buddy_clamber_code.py: the fielder init lets 14 clamber as 9 does, the
wall hook jumps only for 14). Stock Clamber (9) is the stock game's again. Its label is drawn like Tantrum Toss's.

TANTRUM_TOSS (13, Nick's name): Boom Boom's star throw (boom_boom_star_throw.py) is gated on it. Its label
(label_image) is built like a stock one: the text from glyphs cut out of the stock label rows, the left margin
left empty for the widget's glove icon (the one Laser Beam shows), and the game's own star (row 0x146, the white
star with a dark outline) after the text, marking it as a star ability. recolour_labels makes the label widgets
show that star in its own colours (they used to paint every label black).
"""
import struct

NAMES = ("none", "Super Dive", "Super Jump", "Tongue Catch", "Suction Catch", "Magical Catch", "Piranha Catch",
         "Hammer Throw", "Keeper Catch", "Clamber", "Ball Dash", "Laser Beam", "Quick Throw")
STOCK_COUNT = len(NAMES)                     # ids 0..12
TANTRUM_TOSS = 13
CLAMBER_JUMP = 14                            # Clamber, plus the solo buddy jump off the wall (buddy_clamber_code.py)
CLAMBER = 9
NEW = {TANTRUM_TOSS: "Tantrum Toss", CLAMBER_JUMP: "Clamber Jump"}         # id -> label text
STAR = {TANTRUM_TOSS}                        # abilities that spend a star (a star after the label text)

GETTER, FIELDER_VTABLE = 0x8012C134, 0x806434E8    # vtable +0x3C
LABEL_TABLES, FIELDING_LABELS, FIELDING_SLOTS = 0x8063AB80, 0x806233F8, 16
BASERUNNING_LABELS = 0x80623418
STOCK_LABEL_ROWS = (0xFFFF, 0x1B0, 0x1AF) + tuple(range(0x1B1, 0x1BB))   # ids 0..12 (file 19 rows)

def valid(ability):
    return 0 <= ability < STOCK_COUNT or ability in NEW


DEFAULT_CHARS = {TANTRUM_TOSS: ()}           # this mod's Boom Boom (0x67) gets his from his definition's "stats"


def ability_of(entry):
    """An entry's "fielding ability" key: top-level (patcher profiles, stock entries) or under "stats"
    (characters/*.json); None when it has neither."""
    n = entry.get("fielding ability", entry.get("stats", {}).get("fielding ability"))
    return None if n is None else int(n)


def ids(entries, ability=TANTRUM_TOSS, defaults=True):
    """The character ids with the per-character key "fielding ability": `ability` (patcher profiles,
    characters/*.json, stock entries), on top of DEFAULT_CHARS[ability]; an entry with another ability leaves it
    (defaults=False: only the keys)."""
    out = list(DEFAULT_CHARS.get(ability, ())) if defaults else []
    for e in entries:
        n = ability_of(e)
        if n is None:
            continue
        cid = int(e["id"])
        if n == ability and cid not in out:
            out.append(cid)
        elif n != ability and cid in out:
            out.remove(cid)
    return tuple(out)


def label_rows(max_id):
    """{ability: dir 119 file 19 row} for NEW: after the name rows char_names.add_name_art adds for new ids."""
    import char_names
    first = char_names.NAME_ROW_BASE + max_id - char_names.FIRST_NEW + 1
    return {a: first + k for k, a in enumerate(sorted(NEW))}


def patch_labels(dol, max_id):
    """Write NEW's label rows into the fielding label table's padding slots. Returns log lines."""
    assert struct.unpack(">4I", dol.read(LABEL_TABLES, 16))[2] == FIELDING_LABELS, "label pointer table moved"
    stock = struct.unpack(f">{STOCK_COUNT}H", dol.read(FIELDING_LABELS, 2 * STOCK_COUNT))
    assert stock == STOCK_LABEL_ROWS, f"unexpected fielding label rows {[hex(r) for r in stock]}"
    assert FIELDING_LABELS + 2 * FIELDING_SLOTS == BASERUNNING_LABELS
    rows = label_rows(max_id)
    for a, row in rows.items():
        assert STOCK_COUNT <= a < FIELDING_SLOTS, f"ability {a}: no free label slot"
        at = FIELDING_LABELS + 2 * a
        assert dol.read(at, 2) == b"\0\0", f"label slot {a} is not free"
        dol.write(at, struct.pack(">H", row))
    return [f"abilities    fielding label slots: " + ", ".join(f"{a} {NEW[a]} -> row {r}" for a, r in rows.items())
            + " (0x806233F8 table, padding slots)"]




# --- the label art (docs/abilities.md "Label") ---------------------------------------------------------------------
# Every ability label is a 112 x 15 row of dir 119 file 19: rows 0x197..0x1C1 (star pitch, star swing, fielding,
# baserunning), all on page 125 (CI4 + a 16-entry IA8 palette: white at 16 alphas), and page 125 holds nothing
# else. The status widgets draw the row with 20 sprite keys (ref 0x197; elements 86, 89, 98 and 192) whose vertex
# colour is black. GX multiplies the texel by it, so every label shows black whatever its colours (the old gold
# label came out as a black blob). The category icon (the glove for fielding, row 0xD3) is its own key, drawn
# over the row's x 0..18: the text starts at x 21 and our rows leave that margin empty, so Tantrum Toss shows
# the same glove as Laser Beam.
# recolour_labels swaps the two: page 125's palette becomes black at the same alphas and the 20 keys white. The
# stock labels look exactly as before, and our rows keep their colours (the white star).
LABEL_ROWS, LABEL_PAGE, LABEL_KEYS = range(0x197, 0x1C2), 125, 20
KEY_COLOUR, BLACK4, WHITE4 = 0x40, b"\0\0\0\xff" * 4, b"\xff" * 16      # sprite key +0x40: four RGBA
CELL, TEXT_X = (112, 15), 21
MIN_TEXT_X = 20                 # the stock labels start at x 20-22 (Anger Dive 20): a text 1 px too wide starts at 20
LABEL_ALPHA = (0x00, 0x10, 0x20, 0x30, 0x40, 0x50, 0x65, 0x80, 0x90, 0xA0, 0xB0, 0xC0, 0xD0, 0xE0, 0xF0, 0xFF)  # page 125
# The text: glyphs cut out of the stock label rows. char: (stock row, x in that row, 15 rows of page-125 CI4
# indices). test_abilities checks each one against the English file.
GLYPHS = {
    "T": (0x199, 21, "00000000/00000000/BBBBBBB8/FFFFFFFB/004FF000/004FF000/004FF000/004FF000/004FF000/004FF000/"
                     "004FF000/004FF000/00000000/00000000/00000000"),                          # Tornado Ball
    "a": (0x19D, 30, "00000000/00000000/00000000/00000000/00144000/19FFFE50/2EF9EFB0/0547EFB0/09FFDFB0/4FF65FB0/"
                     "6FE8EFF6/2EFFF9FA/01441022/00000000/00000000"),                          # Banana Ball
    "n": (0x19D, 38, "00000000/00000000/00000000/00000000/00014200/4FCFFF90/4FFEDFF4/4FD21DF7/4FB00BF7/4FB00BF7/"
                     "4FB00BF7/4FB00BF7/00000000/00000000/00000000"),                          # Banana Ball
    "t": (0x1BB, 45, "00000/00000/02420/07F70/07F70/7FFF7/4BFB4/07F70/07F70/07F70/07FC7/04EFD/00143/00000/00000"),
    "r": (0x199, 38, "00000/00000/00000/00000/00041/FFEF5/FFF94/FF400/FF000/FF000/FF000/FF000/00000/00000/00000"),
    "u": (0x1AF, 71, "00000000/00000000/00000000/00000000/00000000/7F700FF4/7F700FF4/7F700FF4/7F700FF4/7FC13FF4/"
                     "6FFDFFF4/1CFFBDF4/00430000/00000000/00000000"),                          # Super Jump
    "m": (0x1AF, 80, "0000000000/0000000000/0000000000/0000000000/0002000310/FDBFB5BFE3/FFCFFFDFF9/FF16FD18FB/"
                     "FF04FB04FB/FF04FB04FB/FF04FB04FB/FF04FB04FB/0000000000/0000000000/0000000000"),  # Super Jump
    "o": (0x199, 29, "00000000/00000000/00000000/00000000/00044000/06EFFE70/2FF98FF4/7FA008FA/7F7004FB/7F9008FA/"
                     "3FF88EF6/06EFFF80/00144100/00000000/00000000"),                          # Tornado Ball
    "s": (0x1B8, 68, "0000000/0000000/0000000/0000000/0024300/1BFFFD3/5FE8DF5/4FE8530/08FFFE3/0625CFA/6FE8EFA/"
                     "3CFFFE3/0034400/0000000/0000000"),                                       # Ball Dash
    # item abilities (item_abilities.py): cut the same way, from a stock row where the letter stands alone
    # or touches a neighbour least (d: its first column, Tornado's a, left out)
    "A": (0x1BD, 20, "00000000000/00000000000/0000DFE0000/0003FFF5000/0008FEFA000/000EF5FF100/005FD0CF600/009FA4AFA00/"
                     "00EFFFFFF10/05FD777DF60/09F80006FA0/1FF30002FF2/14400000441/00000000000/00000000000"),  # Anger Dive
    "B": (0x1A6, 22, "00000000/00000000/BBBBB910/FFBDFFC0/FF019FF0/FF009FF0/FFFFFF60/FFBBFFE3/"
                     "FF005EF9/FF0008FB/FFBBCFF6/FFFFFF80/00000000/00000000/00000000"),                    # Breath Swing
    "C": (0x1B1, 73, "000000000/000000000/003BFFFA1/03EFFDFFC/0BFC206E9/2FF500010/4FF000000/4FF000000/"
                     "3FF300000/0DFA003C6/05FFD9FFE/006EFFFE5/000144400/000000000/000000000"),             # Tongue Catch
    "D": (0x1B0, 65, "000000000/000000000/6BBBBB600/7FFFFFF90/7FB006FF5/7FB0009FA/7FB0005FB/7FB0004FB/"
                     "7FB0008FB/7FB003EF6/7FEBBFFC1/7FFFFF910/000000000/000000000/000000000"),             # Super Dive
    "E": (0x1A4, 22, "0000000/0000000/FFFFFFB/FFFFFFB/FF00000/FF00000/FFFFFF4/FFBBBB3/"
                     "FF00000/FF00000/FFBBBBB/FFFFFFF/4444444/0000000/0000000"),                           # Egg Swing
    "F": (0x1A2, 22, "0000000/0000000/FFFFFF7/FFFFFF7/FF40000/FF40000/FFCBBB0/FFFFFF0/"
                     "FF64440/FF40000/FF40000/FF40000/0000000/0000000/0000000"),                           # Flower Swing
    "G": (0x1AD, 21, "0000000000/0000000000/005DFFF910/06FFDBEFC0/1EF9001C80/5FE0000100/7FB0077772/7FB00FFFF4/"
                     "6FD0044CF4/2FF6001CF4/08FF98EFF3/008FFFFE60/0002444100/0000000000/0000000000"),      # Graffiti Ball
    "H": (0x19F, 22, "00000000/00000000/FF4004FF/FF4004FF/FF4004FF/FF4004FF/FFFFFFFF/FFCBBCFF/"
                     "FF4004FF/FF4004FF/FF4004FF/FF4004FF/00000000/00000000/00000000"),                    # Heart Ball
    "M": (0x1B3, 22, "0000000000/0000000000/BB90006BB3/FFF200DFF4/FFF602FFF4/FFFA06FFF4/FBFE0AFAF4/FBAF4EE7F4/"
                     "FB6FBFA7F4/FB2FEF67F4/FB0DFF27F4/FB08FD07F4/0000000000/0000000000/0000000000"),      # Magical Catch
    "P": (0x1B4, 22, "0000000/0000000/FFFFB70/FFFFFF8/FF006FF/FF000FF/FF006FF/FFFFFF8/"
                     "FFBBB71/FF00000/FF00000/FF00000/4400000/0000000/0000000"),                           # Piranha Catch
    "R": (0x1A3, 22, "000000000/000000000/BBBBBA200/FFFFFFE10/FF019FF40/FF006FF40/FF78FFF21/FFFFFE600/"
                     "FF46FE200/FF00BF904/FF004FF44/FF000BFB1/000000000/000000000/000000000"),             # Rainbow Ball
    "S": (0x1AB, 21, "00000000/00000000/03BFFF91/0DFDDFF9/3FF218E4/2FFC2000/09FFFC60/006AFFF8/"
                     "021019FF/5F9002FF/4FFB7CFD/06FFFFE3/00144400/00000000/00000000"),                    # Suction Ball
    "b": (0x197, 47, "0000000/0000000/BB30000/FF40000/FF42300/FFBFFD3/FFFADFA/FF902FF/"
                     "FF000FF/FF202FF/FFE8CFB/FDAFFD3/0002400/0000000/0000000"),                           # Fireball
    "c": (0x1AB, 38, "00000000/00000000/00000000/00000000/00024200/03BFFFB1/0CFD8DE1/4FE10030/"
                     "4FB00000/4FE10030/0DFC7DF2/03DFFFC2/00034300/00000000/00000000"),                    # Suction Ball
    "d": (0x199, 59, "00000000/00000000/000008B3/00000BF4/00140BF4/07FFDEF4/4FF8DFF4/9F901AF4/"
                     "BF6007F4/9F803EF4/6FF8EFF4/09FFD8F4/00240000/00000000/00000000"),                    # Tornado Ball
    "e": (0x1A5, 42, "0000000/0000000/0000000/0000000/0024200/1AFFFB1/7FC8FF7/DF56CFD/"
                     "FFFFFFB/EF94062/8FFADFA/1BFFFD3/0034400/0000000/0000000"),                           # Killer Ball
    "g": (0x1A4, 30, "0000000/0000000/0000000/0000000/0034100/1BFFEEF/9FD8EFF/DF402FF/"
                     "FF000FF/CF609FF/6FFCFFF/06BB6FF/45306FE/6FFFFF8/279B850"),                           # Egg Swing
    "h": (0x1B3, 104, "0000000/0000000/8B30000/BF40000/BF43400/BFEFFD3/BFFBFF9/BF609FB/"
                     "BF404FB/BF404FB/BF404FB/BF404FB/0000000/0000000/0000000"),                           # Magical Catch
    "i": (0x197, 30, "00/00/BB/FF/44/FF/FF/FF/"
                     "FF/FF/FF/FF/44/00/00"),                                                              # Fireball
    "k": (0x1BC, 34, "00000000/00000000/3B800000/4FB00000/4FB00000/4FB0AFA0/4FB9FC10/4FEFC100/"
                     "4FFFE100/4FEBFA00/4F72EF60/4F705FE2/00000000/00000000/00000000"),                    # Ink Dive
    "l": (0x199, 98, "00/00/BB/FF/FF/FF/FF/FF/"
                     "FF/FF/FF/FF/00/00/00"),                                                              # Tornado Ball
    "p": (0x1AF, 39, "0000000/0000000/0000000/0000000/0002300/FF8FFC1/FFFADF9/FF904FF/"
                     "FF000FF/FF103FF/FFE8CFA/FFDFFD2/FF03400/FF00000/7700000"),                           # Super Jump
    "v": (0x1B0, 78, "00000000/00000000/00000000/00000000/00000000/9F900AF6/3FE11FF1/0DF66FA0/"
                     "07FAAF60/02FFFE00/00BFF900/006FF400/00000000/00000000/00000000"),                    # Super Dive
    "w": (0x1A8, 75, "00000000000/00000000000/00000000000/00000000000/00000000000/2FE04FF40FF/0DF37FF74FB/09F6BFFA6F6/"
                     "06FAFCDEAF3/01FEF89FED0/00CFF56FF90/008FF23FF60/00000000000/00000000000/00000000000"),  # Phony Swing
    # (w: Phony Swing's, empty columns on both sides; Rainbow Ball's x 66 carried its o's right edge, 3/4/3 in rows 7-9)
    "L": (0x1A9, 22, "0000000/0000000/BB30000/FF40000/FF40000/FF40000/FF40000/FF40000/"
                     "FF40000/FF40000/FFCBBB6/FFFFFF7/0000000/0000000/0000000"),                           # Liar Ball
    "y": (0x1A7, 55, "00000000/00000000/00000000/00000000/00000000/CF600FF1/6FD05FA0/0EF49F60/"
                     "08F9DF10/02FEFA00/00AFF600/005FF100/02AFA000/6FFF4000/1B720000"),                    # Phony Ball
    "J": (0x1AF, 64, "000000/000000/0008B6/000BF7/000BF7/000BF7/000BF7/000BF7/"
                     "000BF7/001DF7/59CFF6/4FFFD1/144400/000000/000000"),                                  # Super Jump
}
# Letters no stock label has, derived from stock glyphs: q = p mirrored (the font's bowl and stem are
# symmetric), ' = rows 2-5 of l (a stem as tall as the caps' top, as in the name font's apostrophe).
# V = v stretched from the x-height to the cap height ("Vanishing Ball").
# No W: no stock label has one, and M upside down reads as an upside-down M (Nick, labels-7: "is there no W"), so a
# name with a W is renamed instead. missing_glyphs / text_alpha refuse any letter not here or in GLYPHS.
DERIVED = {"q": ("p", "mirror"), "'": ("l", (2, 5))}
DERIVED["V"] = ("v", "cap")
DERIVED["-"] = ("e", (8, 8))            # hyphen = the crossbar row of e (the x-height middle; "Bob-omb Drop")
# Empty columns between two glyphs: the stock pairs (T-o in Tornado, a-n in Banana, r-n in Tornado for r-u, u-m in
# Jump), 1 otherwise (as o-r, s-h, t-e). SPACE: empty columns for a space (stock 6; 3 in the squeezed Hammer Throw).
KERN = {("T", "a"): 0, ("T", "o"): 0, ("a", "n"): 0, ("r", "u"): 0,
        ("r", "a"): 0, ("R", "o"): 0, ("y", "a"): 0,     # r-a as in Piranha; R-o, y-a: their arms overhang
        ("o", "w"): 0, ("S", "w"): 0}                    # o-w as in Rainbow, S-w as in Swing (w's first column is its gap)
SPACE = 4
# The star: row 0x146, the game's white star with a dark outline (page 121: the same CI4 atlas as the labels with
# its own IA8 palette; row 0x145 is the gold one, the status card's corner star), 19 x 18. Scaled to STAR_H rows
# (its white body about the text's cap height) and put STAR_GAP columns after the text.
STAR_ROW, STAR_PAGE = 0x146, 121
STAR_PAL = (0x00FF, 0x0300, 0x1500, 0x3600, 0x5100, 0x6B00, 0x8800, 0xA902, 0xC41F, 0xD442, 0xDE58, 0xEE80,
            0xF9AC, 0xFED4, 0xFFED, 0xFFFF)                                  # IA8: alpha << 8 | intensity
STAR_PIXELS = ("0000000135310000000/000000036A630000000/000000259F952000000/00000036CFD73100000/"
               "0001225AFFFA6221000/1345667DFFFD7665431/368ABCDFFFFFDCBA863/5AFFFFFFFFFFFFFFFA5/"
               "36AFFFFFFFFFFFFFA63/136BFFFFFFFFFFFB641/0146BFFFFFFFFFB6410/00147DFFFFFFFE74100/"
               "00047FFFFFFFFF74000/00148FFFFFFFFF94100/00159FFFDBDFFFA5100/0015AFDA767ADFB5100/"
               "0015A975323579A5100/0003553200023553000")
STAR_H, STAR_Y, STAR_GAP = 12, 1, 1


def cells(s):
    return [[int(c, 16) for c in line] for line in s.split("/")]


def star_image(height=STAR_H):
    """Row 0x146's star (RGBA), scaled to height rows (premultiplied Lanczos, so the outline keeps its shade)."""
    from PIL import Image
    rows = cells(STAR_PIXELS)
    img = Image.new("RGBA", (len(rows[0]), len(rows)))
    img.putdata([(STAR_PAL[i] & 255,) * 3 + (STAR_PAL[i] >> 8,) for line in rows for i in line])
    if height == img.size[1]:
        return img
    width = round(img.size[0] * height / img.size[1])
    return img.convert("RGBa").resize((width, height), Image.LANCZOS).convert("RGBA")


class MissingGlyph(AssertionError):
    """A label text with a letter no stock label has (not in GLYPHS or DERIVED). Raised, never an assert statement
    (python -O strips those); an AssertionError so the callers that refuse bad names catch it as before."""


def missing_glyphs(text):
    """The letters of text with no glyph (GLYPHS / DERIVED), sorted; [] when every one renders."""
    return sorted({c for c in text if c != " " and c not in GLYPHS and c not in DERIVED})


def check_glyphs(text):
    """Raise MissingGlyph unless every letter of text has a glyph (a raise, not an assert: python -O keeps it)."""
    missing = missing_glyphs(text)
    if missing:
        raise MissingGlyph(f"{text!r}: no stock glyph for {missing}: cut one into abilities.GLYPHS or rename it")


def glyph_cells(c):
    """c's 15 rows of page-125 indices (GLYPHS, or DERIVED from one); MissingGlyph for any other letter."""
    if c not in GLYPHS and c not in DERIVED:
        raise MissingGlyph(f"no stock glyph for {c!r}")
    if c in GLYPHS:
        return cells(GLYPHS[c][2])
    src, how = DERIVED[c]
    rows = cells(GLYPHS[src][2])
    if how == "mirror":
        return [line[::-1] for line in rows]
    if how == "cap":                                    # x-height rows 5..11 stretched to the cap rows 2..11
        return rows[:2] + [rows[5 + (y * 7) // 10] for y in range(10)] + rows[12:]
    return [line if how[0] <= y <= how[1] else [0] * len(line) for y, line in enumerate(rows)]


def text_alpha(text):
    """The text's alpha (an "L" image as wide as the text) from GLYPHS, KERN and SPACE."""
    from PIL import Image, ImageChops
    check_glyphs(text)                                  # every label path goes through here
    parts, x, prev = [], 0, None
    for c in text:
        if c == " ":
            x, prev = x + SPACE, None
            continue
        if prev:
            x += KERN.get((prev, c), 1)
        rows = glyph_cells(c)
        g = Image.new("L", (len(rows[0]), CELL[1]))
        g.putdata([LABEL_ALPHA[i] for line in rows for i in line])
        parts.append((x, g))
        x, prev = x + g.size[0], c
    out = Image.new("L", (x, CELL[1]))
    for gx, g in parts:
        box = (gx, 0, gx + g.size[0], CELL[1])
        out.paste(ImageChops.lighter(out.crop(box), g), box)
    return out


def snap_alpha(a):
    """The nearest of the stock labels' 16 alphas."""
    return min(LABEL_ALPHA, key=lambda v: abs(v - a))


def label_image(text, star=False):
    """A label row (RGBA 112 x 15) like the stock ones: black text from the stock glyphs at x 21 (black is what
    the labels show once recolour_labels has run), the margin before it empty for the widget's category icon,
    and with star, row 0x146's star after the text. When text + star is wider than the row, the text is
    squeezed horizontally to fit (the stock art squeezes long names too, e.g. Hammer Throw)."""
    from PIL import Image
    alpha = text_alpha(text)
    st = star_image() if star else None
    room = CELL[0] - TEXT_X - (st.size[0] + STAR_GAP if st else 0)
    x0 = TEXT_X
    if not st and room < alpha.size[0] <= room + TEXT_X - MIN_TEXT_X:
        x0 = CELL[0] - alpha.size[0]                # 1 px too wide: start at x 20 (as Anger Dive), not squeezed
    elif alpha.size[0] > room:
        alpha = alpha.resize((room, CELL[1]), Image.LANCZOS)
    ink = Image.new("RGBA", alpha.size)
    ink.putdata([(0, 0, 0, snap_alpha(a)) for a in alpha.getdata()])
    img = Image.new("RGBA", CELL, (0, 0, 0, 0))
    img.paste(ink, (x0, 0))
    if st:
        img.alpha_composite(st, (x0 + alpha.size[0] + STAR_GAP, STAR_Y))
    return img


def label_keys(lay):
    """[(element, key offset)] of the sprite keys that show an ability label row (layout.Layout of file 19)."""
    out = []
    for k in range(len(lay.elements)):
        e = lay.elements[k]
        for node in lay.nodes(k):
            out += [(k, o) for o in node if e[o + 4] == 4 and struct.unpack_from(">H", e, o + 6)[0] in LABEL_ROWS]
    return out


def recolour_labels(lay):
    """File 19 (layout.Layout): page 125's palette -> black at the same alphas, the 20 label keys' vertex colour
    black -> white. The stock labels render as before; label texels now show in their own colours."""
    assert {struct.unpack_from(">H", lay.rows[r])[0] for r in LABEL_ROWS} == {LABEL_PAGE}, "labels moved"
    assert not [r for r, row in enumerate(lay.rows) if r not in LABEL_ROWS
                and struct.unpack_from(">H", row)[0] == LABEL_PAGE], f"page {LABEL_PAGE} holds more than the labels"
    at, n = lay.palette(LABEL_PAGE)
    assert struct.unpack_from(f">{n}H", lay.data, at) == tuple(a << 8 | 0xFF for a in LABEL_ALPHA), \
        "unexpected label palette"
    struct.pack_into(f">{n}H", lay.data, at, *(a << 8 for a in LABEL_ALPHA))
    keys = label_keys(lay)
    assert len(keys) == LABEL_KEYS and all(lay.elements[k][o + KEY_COLOUR:o + KEY_COLOUR + 16] == BLACK4
                                           for k, o in keys), "unexpected label keys"
    for k, o in keys:
        lay.elements[k][o + KEY_COLOUR:o + KEY_COLOUR + 16] = WHITE4
    return len(keys)


def label_page(images):
    """Label rows (RGBA, CELL) -> (CI8 bytes, IA8 palette bytes, width, height): one page, row k at y 16 k.
    Palette: black at LABEL_ALPHA first (the stock text levels), then each other (grey, alpha) the rows use."""
    w, h = 128, 16
    while h < 16 * len(images):
        h *= 2
    pal = [a << 8 for a in LABEL_ALPHA]
    index = {(0, a): i for i, a in enumerate(LABEL_ALPHA)}
    pix = [[0] * w for _ in range(h)]
    for k, img in enumerate(images):
        assert img.size == CELL, img.size
        px = img.load()
        for y in range(CELL[1]):
            for x in range(CELL[0]):
                r, g, b, a = px[x, y]
                assert r == g == b, f"label art must be grey: {(r, g, b)}"
                key = (r if a else 0, a)
                if key not in index:
                    index[key] = len(pal)
                    pal.append(a << 8 | r)
                pix[16 * k + y][x] = index[key]
    assert len(pal) <= 256, f"{len(pal)} colours"
    data = bytearray()
    for ty in range(0, h, 4):                                 # CI8: 8 x 4 tiles
        for tx in range(0, w, 8):
            for y in range(ty, ty + 4):
                data += bytes(pix[y][tx:tx + 8])
    return bytes(data), struct.pack(f">{len(pal)}H", *pal), w, h
