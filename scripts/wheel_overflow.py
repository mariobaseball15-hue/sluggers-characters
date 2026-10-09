"""Characters whose colour wheel is full get their own grid square instead (git-92; charbuild step 1c calls this).

A new character not on a grid square joins its host's colour wheel (charbuild.extended_rows, selector byte 5: after
the family's shown stock members and the earlier new ones), and a wheel holds wheel7.MEMBERS (10). The recolors
fill 10 family wheels to 10 (Yoshi, Toad, Koopa Troopa, Paratroopa, Pianta, Noki, Hammer Bro, Magikoopa, Dry Bones,
Kritter; 2026-09-26), so an imported character on one of those hosts would stop the build there. wheel_overflow
walks the characters as extended_rows will (id order, the same count) and moves each one that would overflow onto a
new square of its own, at the end of the grid's new squares, with a note:
    "<host>'s colour wheel is full, so <name> gets their own square".
The grid holds gridcells.N_NEW_SQUARES new squares (12 x 5 = 60 cells: 40 stock + 41st onward), and the default
grid already uses all 19. With no square left, the character goes on the wheel of a NEW character's square with room
(git-92 / git-dc, 2026-09-26): its family's own new square if there is one (a square whose characters share its
host's family), else the least-full one (the first on a tie), under wheel7.MEMBERS, with the note
    "The character select screen is full, so <name> is on <square's first character>'s colour wheel. Move them in
     Select grid."
Stock family wheels are never used for this. WheelFull (plain words) only when every new square's wheel is full too.
A square's names are its wheel (charbuild: a character on a square gets selector byte 5 = 0, its wheel from the
square), so a join is only its name appended to that square.

    extra, joins, notes = wheel_overflow.place(chars, grid_squares, dol)
    grid_squares = [list(sq) for sq in grid_squares]
    for i, name in joins: grid_squares[i].append(name)
    grid_squares += extra                      # and each extra square's first name at the end of the grid layout

Test: python scripts/test_wheel_overflow.py
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
from sluggers_data import CHAR_NAMES  # noqa: E402

SELECTOR, ROW, STOCK_IDS = 0x80631550, 8, 0x65      # charbuild TABLES "selector", STOCK_IDS
FAMILY, SLOT, SHOWN = 2, 5, 6                        # selector bytes: family, wheel slot, shown on the wheel


class WheelFull(ValueError):
    """No square left for a character whose wheel is full (plain words)."""


def _members():
    import wheel7
    return wheel7.MEMBERS


def _max_squares():
    import gridcells
    return gridcells.N_NEW_SQUARES


def _square_ids(chars, squares):
    """Ids of the new characters on `squares` (names or ids, as charbuild.resolve_squares)."""
    by_name = {c["name"].lower(): c["id"] for c in chars}
    out = set()
    for sq in squares:
        for n in sq:
            cid = n if isinstance(n, int) else by_name.get(str(n).lower())
            if cid is not None and cid > STOCK_IDS:
                out.add(cid)
    return out


def place(chars, grid_squares, dol, members=None, max_squares=None):
    """-> (extra: new squares [[name, ...]] to append, joins: [(index into grid_squares, name)], notes). chars:
    charbuild's character dicts ("id", "name", "wheel": the host's stock id); grid_squares: this build's new squares
    (charbuild.GRID_SQUARES or grid_order's), not changed. Raises WheelFull when every new square's wheel is full."""
    members = _members() if members is None else members
    max_squares = _max_squares() if max_squares is None else max_squares
    rows = [dol.read(SELECTOR + i * ROW, ROW) for i in range(STOCK_IDS)]
    by_name = {c["name"].lower(): c for c in chars}
    squares = [list(sq) for sq in grid_squares]            # working copy: original squares, then the extra ones
    n_orig = len(squares)
    on_square = _square_ids(chars, squares)
    joins, notes, counted = [], [], {}

    def member(n):
        return by_name.get(str(n).lower()) if not isinstance(n, int) else next((c for c in chars if c["id"] == n), None)

    def family_of(sq):
        fams = {rows[m["wheel"]][FAMILY] for m in map(member, sq) if m}
        return fams.pop() if len(fams) == 1 else None

    for c in sorted(chars, key=lambda c: c["id"]):
        if c["id"] in on_square:
            continue
        family = rows[c["wheel"]][FAMILY]
        stock = max([r[SLOT] for r in rows if r[FAMILY] == family and r[SHOWN]] or [-1])
        slot = 1 + stock + counted.get(family, 0)
        if slot < members:
            counted[family] = counted.get(family, 0) + 1
            continue
        host = CHAR_NAMES[c["wheel"]].strip()
        if sum(1 for sq in squares if sq) < max_squares:
            squares.append([c["name"]])
            notes.append(f"{host}'s colour wheel is full, so {c['name']} gets their own square")
        else:
            room = [k for k, sq in enumerate(squares) if sq and len(sq) < members and member(sq[0])]
            if not room:
                raise WheelFull(f"The character select screen is full and so is every new character's colour wheel, "
                                f"so {c['name']} can't be added: leave out a character or a recolor built on {host}")
            own = [k for k in room if family_of(squares[k]) == family]
            k = own[0] if own else min(room, key=lambda k: len(squares[k]))
            squares[k].append(c["name"])
            if k < n_orig:
                joins.append((k, c["name"]))
            notes.append(f"The character select screen is full, so {c['name']} is on {member(squares[k][0])['name']}'s "
                         f"colour wheel. Move them in Select grid.")
        on_square.add(c["id"])
    return squares[n_orig:], joins, notes


def wheel_overflow(chars, grid_squares, dol, members=None, max_squares=None):
    """The first contract, (extra squares, notes), for charbuild until it calls place(): own squares only, WheelFull
    where place() would join a square's wheel."""
    extra, joins, notes = place(chars, grid_squares, dol, members, max_squares)
    if joins:
        raise WheelFull(notes[len(notes) - len(joins)].replace(" Move them in Select grid.", "") +
                        " (this build doesn't support that yet)")
    return extra, notes
