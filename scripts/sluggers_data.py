"""Names and field layouts for Mario Super Sluggers (RMBE01) character data.

Character names follow Phil's stat editor (refs/stat-editor/editor.py, charList, id order; copied below): stock ids only.
Extra Innings' Rosalina, Orange Toad, Larry and Luma are definitions with new ids (characters/*.json, 0x81-0x84),
so a name that is not a stock one resolves through the definitions or fails loudly.
Stats-row layout: the row is 0x8E bytes: u16 id, 40 bytes of stats, 101 chemistry bytes (column =
other character id; 0 bad, 1 neutral, 2 good), 1 byte of padding. Stat offsets come from the
editor's getStatOffset(j) minus one (its base address is one byte before the row).
"""
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
# charList and statsList[:26] of Phil's editor (refs/stat-editor/editor.py), copied here so a build (and the
# patcher's download) doesn't need the editor
CHAR_NAMES = [
    'Mario', 'Luigi', 'Donkey Kong', 'Diddy Kong', 'Peach', 'Daisy', 'Green Yoshi', 'Baby Mario', 'Baby Luigi',
    'Bowser', 'Wario', 'Waluigi', 'Green Koopa Troopa', 'Red Toad', 'Boo', 'Toadette', 'Red Shy Guy', 'Birdo',
    'Monty Mole', 'Bowser Jr.', 'Red Koopa Paratroopa', 'Blue Pianta', 'Red Pianta', 'Yellow Pianta', 'Blue Noki',
    'Red Noki', 'Green Noki', 'Hammer Bro', 'Toadsworth', 'Blue Toad', 'Yellow Toad', 'Green Toad', 'Purple Toad',
    'Blue Magikoopa', 'Red Magikoopa', 'Green Magikoopa', 'Yellow Magikoopa', 'King Boo', 'Petey Piranha',
    'Dixie Kong', 'Goomba', 'Paragoomba', 'Red Koopa Troopa', 'Green Koopa Paratroopa', 'Blue Shy Guy',
    'Yellow Shy Guy', 'Green Shy Guy', 'Gray Shy Guy', 'Gray Dry Bones', 'Green Dry Bones', 'Dark Bones',
    'Blue Dry Bones', 'Fire Bro', 'Boomerang Bro', 'Wiggler', 'Blooper', 'Funky Kong', 'Tiny Kong', 'Green Kritter',
    'Blue Kritter', 'Red Kritter', 'Brown Kritter', 'King K. Rool', 'Baby Peach', 'Baby Daisy', 'Baby DK',
    'Red Yoshi', 'Blue Yoshi', 'Yellow Yoshi', 'Light Blue Yoshi', 'Pink Yoshi', 'Unused Yoshi 2', 'Unused Yoshi',
    'Unused Toad', 'Unused Pianta', 'Unused Kritter', 'Unused Koopa', 'Red Mii (M)', 'Orange Mii (M)',
    'Yellow Mii (M)', 'Light Green Mii (M)', 'Green Mii (M)', 'Blue Mii (M)', 'Light Blue Mii (M)', 'Pink Mii (M)',
    'Purple Mii (M)', 'Brown Mii (M)', 'White Mii (M)', 'Black Mii (M)', 'Red Mii (F)', 'Orange Mii (F)',
    'Yellow Mii (F)', 'Light Green Mii (F)', 'Green Mii (F)', 'Blue Mii (F)', 'Light Blue Mii (F)', 'Pink Mii (F)',
    'Purple Mii (F)', 'Brown Mii (F)', 'White Mii (F)', 'Black Mii (F)',
]
STAT_NAMES = [
    'pitching arm', 'batting arm', 'character class', '???', 'weight', 'captain', 'star pitch', 'star swing',
    'fielding ability', 'baserunning ability', 'slap size', 'charge size', 'slap power', 'charge power', 'bunting',
    'speed', 'outfield throwing', 'fielding', 'displayed pitching', 'displayed batting', 'displayed fielding',
    'dis speed', 'curveball speed', 'charge pitch speed', 'curve', 'curse ball',
]
TWO_BYTE = {10, 11, 12, 13, 14, 15, 16, 17, 22, 23, 24, 25}
CHEM_BASE = 0x28
BAD, NEUTRAL, GOOD = 0, 1, 2


def _offset(j):
    if j < 11:
        o = j + 3
    elif j < 19:
        o = 2 * j - 7
    elif j < 23:
        o = j + 11
    else:
        o = 2 * j - 11
    return o - 1


STAT_FIELDS = {name: (_offset(j), 2 if j in TWO_BYTE else 1) for j, name in enumerate(STAT_NAMES)}


def char_id(ref):
    """Accept an id (int, '0x48', '72') or a character name (case-insensitive)."""
    if isinstance(ref, int):
        return ref
    s = str(ref).strip()
    if re.fullmatch(r"0x[0-9a-fA-F]+|\d+", s):
        return int(s, 0)
    names = {n.strip().lower(): i for i, n in enumerate(CHAR_NAMES)}
    return names[s.lower()]
