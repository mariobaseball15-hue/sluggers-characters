"""Modder files: names for the game's code, made from the player's own game (docs/ghidra-names.md).

The patcher's "Modder files..." (patcher/modder_window.py) and `patch.py --game <game> --modder-files <folder>`
write a "Sluggers modder files" folder:
  RMBE01.map     a Dolphin symbol map: the debugger shows Select::CExhiMainTask::Update, not 802cec18
  names.tsv      the same names for Ghidra, applied by ghidra/ApplyNames.java
  ghidra/        ApplyNames.java and the export scripts
  README.txt     how to use them
  Where things are.md   where the game keeps what people edit, and what the patcher moves (docs/where-things-are.md)

Everything is read from the player's main.dol (scripts/ghidra/build_names.py: the game's RTTI and vtables) plus
our names and function sizes (scripts/ghidra/dol_symbols.txt). Nothing of Nintendo's ships.
"""
import shutil, sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts" / "ghidra"))
import build_names

FOLDER = "Sluggers modder files"
GHIDRA_SCRIPTS = ["ApplyNames.java", "ExportDecomp.java", "ExportListing.java", "ExportSome.java"]

README = """\
Sluggers modder files
=====================

Names for Mario Super Sluggers' (USA, RMBE01) code, made by the Sluggers patcher from your own copy of the game.
The game keeps the names of its C++ classes (RTTI). These files use them to name about 7,600 functions, the
vtables and the classes' type info.

How to read the names
---------------------
- Select::CExhiMainTask::Update: a class's function. Update, constructors (CExhiMainTask) and destructors
  (~CExhiMainTask) are named by what they are.
- Captain_local::CS2d_Face::vf0C: a virtual function whose meaning we don't know yet. 0C is its slot in the
  class's vtable, so vf0C is the same slot in a class and in every class built on it.
- Functions outside classes keep no name, apart from a few runtime ones.
- Addresses are the clean game's. A game from the Sluggers patcher keeps the game's own functions where they
  are; the patcher's added code has no names.

Where things are
----------------
"Where things are.md" lists where the game keeps what people edit (stats, chemistry, star moves, items,
stadiums, CPU players, files), and which tables the patcher moves. A patched game's own
relocations.json, in the "(patch details)" folder next to the ISO, has the exact new addresses.

Dolphin (debugger)
------------------
1. Copy RMBE01.map into Dolphin's Maps folder: Documents\\Dolphin Emulator\\Maps (a portable Dolphin: User\\Maps
   next to Dolphin.exe).
2. Turn on the debugger: Options > Configuration > Interface > Show Debugging UI.
3. Start the game, then Symbols > Load Symbol Map. (Or Symbols > Load Other Map File... and pick RMBE01.map
   wherever it is.)

Ghidra
------
1. Import the game's sys/main.dol with a GameCube/Wii loader and let Ghidra analyze it.
2. Put the ghidra folder's scripts where Ghidra looks for scripts (Script Manager > Manage Script Directories),
   then run ApplyNames.java and pick names.tsv. It also sets r2 and r13 (the small-data base registers), so
   globals show up as addresses instead of "unaff_r13 + 0x5a0".
3. ExportDecomp.java writes every function's decompiled C to one text file, ExportSome.java just the ones you ask
   for (addresses joined with +).

Headless, from Ghidra's support folder:
  analyzeHeadless <project folder> <project> -process main.dol -noanalysis -scriptPath <this ghidra folder>
      -postScript ApplyNames.java names.tsv
"""


def write(game, dest):
    """Make the modder files for `game` (an .iso or extracted folder: patch.game_folder checks it is the clean USA
    game) in dest / FOLDER. Returns that folder."""
    sys.path.insert(0, str(ROOT / "scripts" / "patcher"))
    import patch
    folder = patch.game_folder(game)
    out = Path(dest) / FOLDER
    out.mkdir(parents=True, exist_ok=True)
    print("== Naming the game's code")
    rows = build_names.build(folder / "sys" / "main.dol")
    build_names.write_tsv(rows, out / "names.tsv")
    funcs, labels = build_names.write_map(rows, out / "RMBE01.map")
    (out / "ghidra").mkdir(exist_ok=True)
    for name in GHIDRA_SCRIPTS:
        shutil.copyfile(ROOT / "scripts" / "ghidra" / name, out / "ghidra" / name)
    (out / "README.txt").write_text(README, encoding="utf-8")
    shutil.copyfile(ROOT / "docs" / "where-things-are.md", out / "Where things are.md")
    print(f"== Done: {funcs} functions and {labels} labels named, in {out}")
    return out


if __name__ == "__main__":
    if len(sys.argv) != 3:
        sys.exit("python scripts/modder_files.py <game .iso or folder> <where to put the folder>")
    write(sys.argv[1], sys.argv[2])
