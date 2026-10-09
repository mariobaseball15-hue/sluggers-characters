"""Character-select grid order (Nick: players "edit the character select screen order"; patcher option "grid-order").

An order is every square of the grid in reading order (left to right, top to bottom), each square the list of the
characters on its color wheel:

  [["Mario"], ["Luigi"], ["Captain Toad", "Brigade Blue", "Brigade Pink"], ["Rosalina"], ["Luma", "Blue Luma"], ...]

Names are the ones the game shows (stock names, the renamed Toads, the definitions' names); ids work too. The grid's
shape still comes from the number of squares (gridcells.shape: 10 x 4 up to 12 x 5).

Two kinds of square:
- A stock square: one of the game's 41 (40 family squares and Luigi's). It holds its own character (the one the square
  shows: Mario, Captain Toad, Green Yoshi, ...), which can't leave it, and every stock square has to be in the order:
  the game keeps these 41 in its head list and its Random-team / CPU pools. Its wheel can be reordered, take new
  characters and recolors, and give its other stock characters to new squares. (It can't take another family's stock
  characters: those go on a new square.)
- A new square: any characters that aren't a stock square's own character, up to 10 (the color wheel's limit,
  wheel7.MEMBERS). At most 19 of them (60 cells, 12 x 5).

default_order(dol, chars) is today's grid (charbuild.GRID_SQUARES / GRID_LAYOUT, and every other new character on its
template's or "wheel"'s color wheel), plus a new square at the end for each character with no wheel color ("color",
e.g. an imported pack) while the grid has room. validate(order, dol, chars) lists problems in plain words for the
patcher window. to_tables(order, dol, chars) turns an order into what the build needs: gridcells' squares and layout,
each new character's wheel host, and the stock wheels whose order changed (charbuild step 3a). cells() and face() are
for the editor: where each square is drawn and the portrait it shows.
"""
import os
import struct
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import gridcells  # noqa: E402
from sluggers_data import CHAR_NAMES  # noqa: E402

SELECTOR, STOCK_IDS, STOCK_HEAD_COUNT = 0x80631550, 0x65, 41
MAX_SQUARES = gridcells.COLS * gridcells.ROWS                       # 60
MAX_NEW = MAX_SQUARES - STOCK_HEAD_COUNT                             # 19


def _members():
    import wheel7
    return wheel7.MEMBERS


def _renames():
    import char_names
    return char_names.stock_renames()


def _english(value):
    """A "rename" / name value (one string, or {"en", "es", "fr"}) -> the English name."""
    return value if isinstance(value, str) else (value.get("en") or next(iter(value.values())))


def display_name(cid, chars=()):
    """The name the game shows for a character id: a new character's, a stock entry's "rename" (the character
    editor's), our renames (the Toad Brigade), else the stock name."""
    for c in chars:
        if int(str(c["id"]), 0) == cid and (not c.get("stock") or c.get("rename")):
            return _english(c["rename"]) if c.get("stock") else c["name"]
    return _renames().get(cid) or CHAR_NAMES[cid].strip()


class Roster:
    """The game's stock squares and color families (from its main.dol) and the build's new characters."""

    def __init__(self, dol, chars=()):
        """chars: the build's new characters; stock entries ({"id", "stock": True, "rename"}) among them only
        rename (a stock character is known by its new name, and by its old one)."""
        self.dol = dol
        self.stock_names = {int(str(c["id"]), 0): _english(c["rename"]) for c in chars if c.get("stock") and c.get("rename")}
        self.chars = [dict(c, id=int(str(c["id"]), 0)) for c in chars if not c.get("stock")]
        self.sel = [dol.read(SELECTOR + i * 8, 8) for i in range(STOCK_IDS)]
        self.heads = list(dol.read(gridcells.HEAD_LIST, STOCK_HEAD_COUNT))
        self.by_name = {}
        for i in range(STOCK_IDS):
            if self.sel[i][6] or i in self.heads:
                for n in (CHAR_NAMES[i].strip(), _renames().get(i)):
                    if n:
                        self.by_name[n.lower()] = i
        for cid, n in self.stock_names.items():
            self.by_name[n.strip().lower()] = cid
        for c in self.chars:
            self.by_name[c["name"].strip().lower()] = c["id"]

    def id_of(self, m):
        """A name or id -> id, or None if the build has no such character."""
        if isinstance(m, int):
            return m if m < STOCK_IDS or any(c["id"] == m for c in self.chars) else None
        s = str(m).strip()
        if s.lower().startswith("0x") or s.isdigit():
            return self.id_of(int(s, 0))
        return self.by_name.get(s.lower())

    def name(self, cid):
        return self.stock_names.get(cid) or display_name(cid, self.chars)

    def family(self, cid):
        """A character's color family: stock ids from the selector, new ones from their wheel host."""
        if cid < STOCK_IDS:
            return self.sel[cid][2]
        c = next(c for c in self.chars if c["id"] == cid)
        from sluggers_data import char_id
        return self.sel[char_id(c.get("wheel", c["template"]))][2]

    def stock_members(self, head):
        """The stock characters on a stock square's wheel, in the game's order (id order, shown ones)."""
        fam = self.sel[self.heads[head]][2]
        return [i for i in range(STOCK_IDS) if self.sel[i][2] == fam and self.sel[i][6]]


def _squares_constants():
    import charbuild
    return charbuild.GRID_SQUARES, charbuild.GRID_LAYOUT


def stock_sequence(dol):
    """The stock grid's heads in reading order: its 40 squares (0x80623458), then Luigi, whom the stock grid shows in
    one captain's family square instead (FUN_8006e9c4's swap). A build with no new square keeps this grid unless the
    order differs from it (to_tables' "force_grid")."""
    return list(dol.read(gridcells.STOCK_MAP, gridcells.STOCK_SQUARES)) + [gridcells.LUIGI_HEAD]


def default_order(dol, chars, squares=None, layout=None):
    """Today's grid as an order (names), with the build's characters: GRID_SQUARES' characters on their squares, every
    other new character on its wheel host's square (after the stock ones, in id order, as the roster hook adds them),
    and one with no "color" on a new square at the end while there is room."""
    if squares is None:
        squares, layout = _squares_constants()
    r = Roster(dol, chars)
    import charbuild                                      # "own_square" (a .sluggie model, New character): its own;
    squares, layout, _ = charbuild.own_squares(r.chars, squares, layout)      # a recolor of an added character: on
    squares = charbuild.join_squares(squares, r.chars)    # its base's square
    grid = gridcells._order(dol, squares, r.chars, layout)
    resolved = gridcells._resolve_squares(squares, r.chars)
    on_square = {cid for sq in resolved for cid in sq}
    extra = [c for c in r.chars if c["id"] not in on_square and c.get("color") is None]
    extra = extra[:max(0, MAX_NEW - sum(1 for sq in resolved if sq))]
    wheel_chars = [c for c in r.chars if c["id"] not in on_square and c not in extra]
    if not any(resolved) and not extra:                 # no new square: the build keeps the stock grid
        grid = [("stock", h) for h in stock_sequence(dol)]
    out = []
    for kind, k in grid:
        if kind == "stock":
            fam = r.sel[r.heads[k]][2]
            ids = r.stock_members(k) + [c["id"] for c in wheel_chars if r.family(c["id"]) == fam]
            out.append([r.name(i) for i in ids])
        elif resolved[k]:
            out.append([r.name(i) for i in resolved[k]])
    return out + [[c["name"]] for c in extra]


def _parse(order, r):
    """[(kind, head or None, [ids], [unknown names])] per square."""
    out = []
    for sq in order:
        ids, unknown = [], []
        for m in sq:
            cid = r.id_of(m)
            (unknown.append(str(m)) if cid is None else ids.append(cid))
        head = next((r.heads.index(i) for i in ids if i in r.heads), None)
        out.append(("stock" if head is not None else "new", head, ids, unknown))
    return out


def validate(order, dol, chars):
    """Problems with an order, in plain words for the player ([] = fine)."""
    r = Roster(dol, chars)
    out = []
    if not isinstance(order, (list, tuple)) or not all(isinstance(sq, (list, tuple)) for sq in order):
        return ["The order has to be a list of squares, each a list of characters."]
    parsed = _parse(order, r)
    seen = {}
    for n, (kind, head, ids, unknown) in enumerate(parsed, 1):
        for u in unknown:
            out.append(f"Square {n}: there's no character called \"{u}\" in this game.")
        if not ids and not unknown:
            out.append(f"Square {n} is empty: give it a character or take it out.")
        for cid in ids:
            if cid in seen and seen[cid] != n:
                out.append(f"{r.name(cid)} is on two squares ({seen[cid]} and {n}).")
            seen.setdefault(cid, n)
        heads = [i for i in ids if i in r.heads]
        if len(heads) > 1:
            out.append(f"Square {n} has {' and '.join(r.name(i) for i in heads)}: each of them keeps a square of their own.")
        if len(ids) > _members():
            out.append(f"Square {n} has {len(ids)} characters; a color wheel holds at most {_members()}.")
        if kind == "stock":
            fam = r.sel[r.heads[head]][2]
            for cid in ids:
                if cid < STOCK_IDS and cid not in r.heads and r.sel[cid][2] != fam:
                    out.append(f"{r.name(cid)} can't join {r.name(r.heads[head])}'s color wheel: put them on a new square instead.")
    missing = [h for h in range(STOCK_HEAD_COUNT) if r.heads[h] not in seen]
    for h in missing:
        out.append(f"{r.name(r.heads[h])} needs their square: the game's own characters can't be taken off the grid.")
    new = sum(1 for kind, *_ in parsed if kind == "new")
    if STOCK_HEAD_COUNT + new > MAX_SQUARES:
        out.append(f"That's {STOCK_HEAD_COUNT + new} squares; the grid holds at most {MAX_SQUARES}. "
                   f"Put some characters on another character's color wheel.")
    for c in r.chars:
        if c["id"] not in seen:
            out.append(f"{c['name']} isn't on any square.")
    return out


def to_tables(order, dol, chars, squares=None, layout=None):
    """An order (valid: see validate) -> {"squares": [[ids]], "layout": [ids], "wheels": {id: host id},
    "family_order": {family: [ids]}} for charbuild: gridcells' new squares (in GRID_SQUARES order where a square
    keeps its first character, so today's order gives today's bytes) and layout (each square's first character in
    reading order), each new character's wheel host on a stock square, and the stock wheels whose order is not the
    game's (stock ids in id order, then new ones in id order). "force_grid": no new square, but the squares are
    not in the stock grid's order (stock_sequence): the build makes our grid anyway (gridcells.plan(force=), 11 x 4
    with Luigi on a square of his own), since the stock grid's order is fixed."""
    problems = validate(order, dol, chars)
    assert not problems, "; ".join(problems)
    if squares is None:
        squares, layout = _squares_constants()
    r = Roster(dol, chars)
    parsed = _parse(order, r)
    known = [gridcells._resolve_squares([sq], r.chars)[0] for sq in squares]
    rank = {sq[0]: k for k, sq in enumerate(known) if sq}
    new = [ids for kind, _, ids, _ in parsed if kind == "new"]
    new_sorted = sorted(new, key=lambda ids: (rank.get(ids[0], len(rank)), new.index(ids)))
    wheels, family_order = {}, {}
    for kind, head, ids, _ in parsed:
        if kind != "stock":
            continue
        host = r.heads[head]
        fam = r.sel[host][2]
        for cid in ids:
            if cid >= STOCK_IDS:
                wheels[cid] = host
        natural = sorted(i for i in ids if i < STOCK_IDS) + sorted(i for i in ids if i >= STOCK_IDS)
        if ids != natural:
            family_order[fam] = list(ids)
    heads = [head for kind, head, _, _ in parsed if kind == "stock"]
    return {"squares": new_sorted, "layout": [ids[0] for _, _, ids, _ in parsed], "wheels": wheels,
            "family_order": family_order, "force_grid": not new and heads != stock_sequence(dol)}


# --- the editor -------------------------------------------------------------------------------------------------

def room(order, dol, chars):
    """The editor's readout: {"squares_left": new squares the grid still has room for, "wheels": [(characters,
    limit)] per square in order}. A stock square's count includes its stock characters that are still on it."""
    r = Roster(dol, chars)
    parsed = _parse(order, r)
    new = sum(1 for kind, *_ in parsed if kind == "new")
    return {"squares_left": max(0, MAX_NEW - new), "wheels": [(len(ids), _members()) for _, _, ids, _ in parsed]}



def cells(game, n_squares):
    """[(x, y)] of each cell of a grid with n_squares squares (41..60), in reading order: the square's node in the
    select layout (dt_na dir 119 file 19, element 0xBA, as gridcells rebuilds it), with the roster screen's shift
    (gridcells.screen_dx): the game's 2D layout units, about a screen pixel each, y down (rows 48 apart at 12 x 5,
    squares ~46 px, 49 apart). Scale them to the editor's canvas from their min / max."""
    import recolor
    n_new = n_squares - STOCK_HEAD_COUNT
    assert 0 <= n_new <= MAX_NEW, f"{n_squares} squares"
    g = _game(game)
    data = g.file(gridcells.LAYOUT_DIR, gridcells.LAYOUT_FILE)
    if n_new == 0:
        cols, rows, empty, dx = 10, 4, (), 0
    else:
        cols, rows = gridcells.shape(n_new)
        empty = tuple(range(n_squares, cols * rows))
        dx = gridcells.screen_dx((cols, rows, empty))
        data = gridcells._rebuild_element(data, empty, cols, rows)
    c = struct.unpack_from(">I", data, 4)[0]
    e = c + 0x14 + struct.unpack_from(">I", data, c + 0x1C + 4 * gridcells.GRID_ELEMENT)[0]
    n = struct.unpack_from(">I", data, e + 4)[0]
    offs = struct.unpack_from(f">{n}I", data, e + 12)[1:]
    child = 4                                                   # a node's frame: {u16, u16, children}; the first's x, y
    return [(struct.unpack_from(">h", data, e + f + child + gridcells.CHILD_XY[0])[0] + dx,
             struct.unpack_from(">h", data, e + f + child + gridcells.CHILD_Y[0])[0]) for f in offs[:n_squares]]


def _game(game):
    """A recolor.Game, from one or from a game folder (str or Path)."""
    import recolor
    return game if isinstance(game, recolor.Game) else recolor.Game(os.fspath(game))


def face(member, game, chars=()):
    """The side portrait (PIL RGBA, 48 x 51) a square shows for its first character: the game's own for a stock
    character, the definition's icon for a new one. A recolor stand-in without an icon ({"id", "name", "template":
    base, ...}, from the patcher window's recipes) gets its base's portrait with the recipe's "recolor" rules applied
    if it carries them, else the base's."""
    import recolor
    from PIL import Image
    g = _game(game)
    r = Roster(g.dol, chars)
    cid = r.id_of(member)
    assert cid is not None, f"no character {member!r}"
    if cid < STOCK_IDS:
        return g.portrait(cid, "side")
    c = next(c for c in r.chars if c["id"] == cid)
    if not c.get("icon"):
        base = g.portrait(recolor.char_id(c["template"]), "side")
        return recolor.apply_rules(base, c["recolor"], portrait=True) if c.get("recolor") else base
    path = c["icon"]["side"]
    return Image.open(path if os.path.isabs(str(path)) else os.path.join(recolor.ROOT, path)).convert("RGBA")


# --- the build: reordered stock wheels (charbuild step 3a) -----------------------------------------------------------

def family_table(family_order):
    """{family: [ids]} -> {u8 family, ids, 0xFF}..., 0xFF."""
    return b"".join(bytes([fam]) + bytes(ids) + b"\xFF" for fam, ids in sorted(family_order.items())) + b"\xFF"


def family_reorder(a, table, scratch):
    """Emit, at the end of charbuild's roster hook (r31 = the roster struct X, after the game's lists and the new
    characters are in): each listed family's list X+0x76+family*10 (count X+0x4D+family) becomes the listed ids that
    are in it, in that order, then the rest as they were. scratch: 10 bytes. Uses r0, r4-r11."""
    a.load_addr("r6", table).load_addr("r11", scratch)
    a.label("fam")
    a.lbz("r0", 0, "r6").cmplwi("r0", 0xFF).beq("fams_done")
    a.add("r10", "r31", "r0").lbz("r4", 0x4D, "r10")                        # r4 = count
    a.mulli("r5", "r0", 10).add("r5", "r31", "r5").addi("r5", "r5", 0x76)   # r5 = the family's list
    a.li("r7", 0)
    a.label("copy")                                                         # scratch = the list
    a.cmpw("r7", "r4").bge("copied")
    a.lbzx("r0", "r5", "r7").stbx("r0", "r11", "r7").addi("r7", "r7", 1).b("copy")
    a.label("copied")
    a.li("r8", 0)                                                           # r8 = the next slot written
    a.label("want")
    a.addi("r6", "r6", 1).lbz("r9", 0, "r6").cmplwi("r9", 0xFF).beq("rest")  # the next listed id
    a.li("r7", 0)
    a.label("find")
    a.cmpw("r7", "r4").bge("want")
    a.lbzx("r0", "r11", "r7").cmpw("r0", "r9").bne("find_next")
    a.stbx("r9", "r5", "r8").addi("r8", "r8", 1)
    a.li("r0", 0x65).stbx("r0", "r11", "r7").b("want")                      # taken (0x65: no character)
    a.label("find_next")
    a.addi("r7", "r7", 1).b("find")
    a.label("rest")                                                         # the rest, as they were
    a.li("r7", 0)
    a.label("rest_loop")
    a.cmpw("r7", "r4").bge("fam_next")
    a.lbzx("r0", "r11", "r7").cmplwi("r0", 0x65).beq("rest_next")
    a.stbx("r0", "r5", "r8").addi("r8", "r8", 1)
    a.label("rest_next")
    a.addi("r7", "r7", 1).b("rest_loop")
    a.label("fam_next")
    a.addi("r6", "r6", 1).b("fam")
    a.label("fams_done")
    return a


# --- data info (the patcher window's "i": what the grid order changes in the game's data; git-92 / git-b6) -----------

_SRC = "scripts/grid_order.py, scripts/gridcells.py (add_grid_square), scripts/charbuild.py (steps 1c and 3a)"
DATA = {
    "square order": {
        "file": "main.dol",
        "where": "The square to head table. The select screen's constructor FUN_8006e9c4 copies it into its screen "
                 "object with an 8-byte loop: lis r3 / addi r3 at 0x8006EB74 / 0x8006EB80 give the table's address "
                 "(stock 0x80623458, 40 bytes) and li r0 at 0x8006EB78 the number of passes. The build puts a new "
                 "table in its data section and points those two instructions at it.",
        "field": "One byte per cell in reading order (columns x rows cells), the head shown there: heads 0 to 40 are "
                 "the game's squares, 43 on are the new squares, then one per hidden cell. In the screen object it "
                 "lives at +0x67C (stock +0x238; 19 loads and stores move with it), followed by 0xFF padding and "
                 "the per-head flag and wheel index arrays at +0x6BC and +0x6FC.",
        "hook": "The stock captain swap that gave Luigi a captain's square (stb at 0x8006ECF4) is turned off: every "
                "head has a cell of its own.",
        "notes": "grid-order",
        "source": _SRC},
    "heads": {
        "file": "main.dol",
        "where": "The head list at 0x80631878: 43 bytes, head number to character id. Its 20 references are moved "
                 "to a longer copy in the build's data section.",
        "field": "One byte per head: the stock 43, then each new square's first character (the face it shows), then "
                 "head 0's character for each hidden cell.",
        "notes": "grid-order",
        "source": _SRC},
    "new squares": [
        {"file": "main.dol",
         "where": "A member table in the build's data section: one row per new square, up to 10 character ids then "
                  "0xFF (rows of 8 bytes while every square holds 6 or fewer, as before).",
         "hook": "FUN_80071bb0 (the characters on the wheel that holds an id) starts with a branch to a stub: an id "
                 "on a new square lists that square's row, keeping the characters FUN_80071abc calls available; any "
                 "other id takes the stock path.",
         "notes": "grid-order",
         "source": _SRC},
        {"file": "main.dol",
         "hook": "At 0x80071EAC (cmpwi cr1,r29,0) a character on a new square is skipped on its family's wheel. At "
                 "0x8006E868 heads 43 and up answer that they have members. At 0x80073C34 the cursor finds a new "
                 "square character's own square.",
         "text": "Other screens keep the game's family wheels, so a character moved to a new square is still on "
                 "its family's wheel there.",
         "source": _SRC}],
    "wheel order": [
        {"file": "main.dol",
         "where": "The roster struct's family lists: family f's count at +0x4D + f, its ids at +0x76 + f x 10 (10 "
                  "per family). FUN_8006ba6c fills them in character id order.",
         "hook": "The build's roster hook at 0x8006BD58 (it replaces mr r3,r31) adds the new characters, then, for "
                 "each family the order changes, rewrites that family's list: the listed ids that are in it first, "
                 "in the order given, then the rest as they were. Its table is family byte, ids, 0xFF, repeated, "
                 "ending in 0xFF, with a 10-byte scratch copy.",
         "notes": "grid-order",
         "source": _SRC},
        {"file": "main.dol",
         "where": "The character selector table (stock 0x80631550, 8 bytes per character id; the build moves it "
                  "to its data section).",
         "field": "A new character put on a family's square copies bytes 0 to 2 (wheel group, main id, family) "
                  "from that family's own character, and byte 5 is its slot after the family's members.",
         "source": _SRC}],
    "grid size": {
        "file": "main.dol and dt_na.dat (dir 119 file 19)",
        "where": "The grid is 10 x 4 in the stock game. With new squares, or with the game's squares in another "
                 "order, the build makes the smallest of 11 x 4, 12 x 4, 10 x 5, 11 x 5 and 12 x 5 that holds "
                 "every square.",
        "field": "Element 0xBA of the select layout gets one node per cell, 49 px apart and, at 5 rows, rows 48 "
                 "apart; hidden cells go off screen. The square count in FUN_80067ef4 (0x800680B0, 0x80068750), "
                 "the grid's per-square arrays (moved to +0x430, room for 72), both screen objects' sizes and the "
                 "D-pad's row and column arithmetic follow the shape.",
        "text": "With no new square and the game's own order, the stock grid stays exactly as it was.",
        "notes": "grid-order",
        "source": _SRC},
}
