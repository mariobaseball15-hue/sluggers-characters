"""A player's game with model / texture mods (Sluggies-dat-tools in-place edits, retextures): which of dt_na.dat's
files the mod changed, told apart from the clean game by a table of the clean files' hashes (clean_dtna.json: hashes
only, none of the game's bytes).

  python scripts/patcher/modded_game.py make [extracted/clean]     # writes clean_dtna.json (once; the game is fixed)
  python scripts/patcher/modded_game.py show <game folder>         # the changed files, in plain words

dt_na.dat's table of contents is in main.dol (dtna_toc.py), and the patcher refuses a changed main.dol, so a game it
accepts has the clean layout: every file at its clean offset and length. A mod that moved or resized files had to
change main.dol too (Extra Innings), so it's refused with it. What's left to tell is which files' bytes changed:
changed(game) hashes each of the clean TOC's byte ranges (every language's copy, each distinct range once) and the
bytes between them, and compares them with the table. The build copies the player's dt_na.dat and appends to it, so
a changed file the build doesn't repoint is simply kept; the ones it rebuilds (icon bank, name table, a new
character's copies of its template's files, a recolor's base model) are rebuilt from the player's (modded) bytes.
Only our files shipped as deltas on the clean game (delta.py: the download's assets, imported character packs) need
clean bytes: delta.apply's sha1 says whether the bytes a delta copies were still clean, and conflicts() names the
changed files it copies from when they weren't.
"""
import hashlib, json, mmap, struct, sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parent))
TABLE = HERE / "clean_dtna.json"
HASH = 16                       # hex digits of sha1 kept per range (64 bits: plenty to tell a changed file)
MODEL_DIR_BASE = 0x12           # charbuild.MODEL_DIR_BASE: stock character i's files are dt_na dir 0x12 + i
STOCK_IDS = 101
# what a character directory's files are (docs/custom-model-format.md; files 6-14: animation banks)
CHAR_FILES = {0: "model", 1: "low-detail model", 2: "bat"}
OTHER = {(119, 1): "captain / menu art", (119, 2): "character icons", (119, 3): "menu layouts",
         (119, 8): "HUD icons", (121, 0): "menu text", (121, 5): "character names"}   # heap_budget.NAMES and more
GAPS = "bytes between dt_na.dat's files"

_seen = {}                      # {resolved game folder: changed(...)}: patch.game_folder fills it (the cached .iso's
                                # result comes from its stamp), so a run hashes the 700 MB file once
_last = [None]                  # the game last checked (patch.game_folder: the one the patcher and its window read)


def ranges(dol):
    """{(offset, length): [(dir, file), ...]} for every language's copy in main.dol's dt_na TOC (empty files left
    out), in offset order."""
    import dtna_toc
    ptrs = dtna_toc.dir_pointers(dol)
    ends = sorted(set(ptrs + [dtna_toc.RECORDS_END]))
    out = {}
    for d, p in enumerate(ptrs):
        for f, rec in enumerate(range(p, ends[ends.index(p) + 1], dtna_toc.FILE_RECORD)):
            w = struct.unpack(">12I", dol.read(rec, 48))
            for lang in range(3):
                length, off = w[1 + 4 * lang], w[2 + 4 * lang]
                if length and (d, f) not in out.setdefault((off, length), []):
                    out[(off, length)].append((d, f))
    return dict(sorted(out.items()))


def _gaps(spans, size):
    """The byte ranges of [0, size) no span covers (spans: (offset, length), offset order)."""
    out, at = [], 0
    for off, length in spans:
        if off > at:
            out.append((at, min(off, size)))
        at = max(at, off + length)
    if at < size:
        out.append((at, size))
    return [(a, b) for a, b in out if a < b]


def _digests(dat, dol, size):
    """[hash of each TOC range, in ranges() order], hash of the gaps (everything else in the first `size` bytes)."""
    spans = list(ranges(dol))
    with open(dat, "rb") as f, mmap.mmap(f.fileno(), 0, access=mmap.ACCESS_READ) as m:
        view = memoryview(m)
        try:
            each = [hashlib.sha1(view[off:off + length]).hexdigest()[:HASH] for off, length in spans]
            rest = hashlib.sha1()
            for a, b in _gaps(spans, size):
                rest.update(view[a:b])
        finally:
            view.release()
    return each, rest.hexdigest()[:HASH]


def _toc_key(dol):
    return hashlib.sha1(json.dumps(list(ranges(dol))).encode()).hexdigest()[:HASH]


def make(game):
    """clean_dtna.json from the clean game (hashes and sizes only)."""
    from dol import Dol
    game = Path(game)
    dol = Dol(game / "sys/main.dol")
    size = (game / "files/dt_na.dat").stat().st_size
    each, rest = _digests(game / "files/dt_na.dat", dol, size)
    TABLE.write_text(json.dumps({"_why": "dt_na.dat of the clean USA game (RMBE01): the first 16 hex digits of the "
                                         "sha1 of each byte range its main.dol TOC names (modded_game.ranges order) "
                                         "and of the bytes between them; hashes only",
                                 "size": size, "toc": _toc_key(dol), "gaps": rest, "ranges": each}) + "\n",
                     encoding="utf8")
    return len(each)


def changed(game):
    """The dt_na.dat files a mod changed in `game` (its main.dol must be the clean one: patch.check_game checks it
    first): [(dir, file), ...] in order, plus (-1, -1) when bytes between files changed. ValueError (plain words)
    when dt_na.dat is shorter than the clean one (cut short: a broken copy, or a mod the patcher can't build on)."""
    key = str(Path(game).resolve())
    if key in _seen:
        return _seen[key]
    from dol import Dol
    t = json.loads(TABLE.read_text(encoding="utf8"))
    dat = Path(game) / "files/dt_na.dat"
    dol = Dol(Path(game) / "sys/main.dol")
    if dat.stat().st_size < t["size"]:
        raise ValueError(f"this game's dt_na.dat is shorter than the USA game's ({dat.stat().st_size} bytes, not "
                         f"{t['size']}): the copy is broken or cut short. Extract the game again")
    assert _toc_key(dol) == t["toc"], "main.dol's dt_na TOC isn't the clean one (check main.dol first)"
    each, rest = _digests(dat, dol, t["size"])
    out = []
    for (span, owners), got, want in zip(ranges(dol).items(), each, t["ranges"]):
        if got != want:
            out += [o for o in owners if o not in out]
    out = sorted(out) + ([(-1, -1)] if rest != t["gaps"] else [])
    _seen[key] = out
    _last[0] = Path(game)
    return out


def remember(game, entries):
    """changed(game)'s result from elsewhere (the cached .iso's stamp)."""
    _seen[str(Path(game).resolve())] = [tuple(e) for e in entries]
    _last[0] = Path(game)


def forget(game):
    """Drop what's known about `game` (the .iso cache, about to hold another game)."""
    _seen.pop(str(Path(game).resolve()), None)


def name(entry):
    """A changed file in plain words: "Tiny Kong's model", "the character icons", "dt_na.dat folder 150 file 3"."""
    d, f = entry
    if d < 0:
        return GAPS
    if MODEL_DIR_BASE <= d < MODEL_DIR_BASE + STOCK_IDS:
        from sluggers_data import CHAR_NAMES
        who = CHAR_NAMES[d - MODEL_DIR_BASE].strip()
        what = CHAR_FILES.get(f, "animations" if 6 <= f <= 14 else f"file {f}")
        return f"{who}'s {what}"
    if (d, f) in OTHER:
        return f"the {OTHER[(d, f)]}"
    return f"dt_na.dat folder {d} file {f}"


def names(entries):
    """Plain names, each once, in order ("Tiny Kong's model, Tiny Kong's low-detail model")."""
    return list(dict.fromkeys(name(e) for e in entries))


def build_notes(chars, recipes, entries, toads=False):
    """What the mod means for the patch's own characters, in plain words: a recolor of a modded stock character is
    made from its modded model (recolor.make reads the player's game); a new character copies its template's files
    that it doesn't bring itself (charbuild: every file of the template's directory but its model_blocks / bat), so
    modded ones come along; the Toad Brigade's own models replace the Toads' (charbuild.STOCK_MODELS)."""
    if not entries:
        return []
    from sluggers_data import CHAR_NAMES, char_id
    mine = lambda cid, skip=(): [e for e in entries if e[0] == MODEL_DIR_BASE + cid and e[1] not in skip]  # noqa: E731
    out = []
    if recipes:
        import recolor
        for p in recipes:
            r = recolor.load_recipe(p)
            try:
                base = char_id(r["base"])
            except (KeyError, ValueError):
                continue                            # an added base: its model is its own, not the game's
            if base < STOCK_IDS and mine(base):
                out.append(f"{r['name']} is recolored from your game's {CHAR_NAMES[base].strip()}, which your mod "
                           f"changed ({', '.join(names(mine(base)))}): it gets the modded look")
    for c in chars:
        if str(c.get("_why", "")).startswith("Recolor tool"):
            continue                                # (said above, from its recipe)
        try:
            t = char_id(c["template"])
        except (KeyError, ValueError):
            continue
        own = {int(i) for i in (c.get("model_blocks") or {})} | ({2} if c.get("bat") else set())
        if t < STOCK_IDS and mine(t, own):
            out.append(f"{c['name']} is built on {CHAR_NAMES[t].strip()} and uses these from your game, modded: "
                       + ", ".join(names(mine(t, own))))
    if toads:
        import charbuild
        replaced = [e for sid, blocks in charbuild.STOCK_MODELS.items() for e in mine(sid) if e[1] in blocks]
        if replaced:
            out.append("the Toad Brigade's own models replace your modded " + ", ".join(names(replaced)))
    return out


def conflicts(delta_bytes, entries, game):
    """The changed files (entries: changed(game)) a delta copies dt_na.dat bytes from: why it didn't rebuild."""
    import delta
    from dol import Dol
    spans = [(span, owners) for span, owners in ranges(Dol(Path(game) / "sys/main.dol")).items()
             if any(o in entries for o in owners)]
    hit = []
    copied = delta.copied(delta_bytes, delta.SOURCES.index("files/dt_na.dat"))
    for a, b in copied:
        for (off, length), owners in spans:
            if a < off + length and off < b:
                hit += [o for o in owners if o in entries and o not in hit]
    if (-1, -1) in entries and not hit:     # nothing else explains it: the bytes between files
        hit.append((-1, -1))
    return sorted(hit)


def why_not_rebuilt(delta_bytes):
    """For a delta that didn't rebuild from the game last checked (charpack.rebuild: an imported character's files):
    "it copies parts of <the modded files> ..." when that game has model / texture mods, else ""."""
    game = _last[0]
    entries = _seen.get(str(game.resolve()), []) if game else []
    if not entries:
        return ""
    try:
        hit = conflicts(delta_bytes, entries, game)
    except Exception:                               # (a damaged delta: charpack says so)
        return ""
    return (f"it's made from parts of the game that your model or texture mod changed ({', '.join(names(hit))}): "
            f"use a clean copy of the game for it") if hit else ""


def main():
    import argparse
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    ap.add_argument("what", choices=["make", "show"])
    ap.add_argument("game", nargs="?", default=str(HERE.parents[1] / "extracted/clean"))
    args = ap.parse_args()
    if args.what == "make":
        print(f"{TABLE}: {make(args.game)} ranges")
    else:
        got = changed(args.game)
        print("\n".join(f"{d:4} {f:3}  {name((d, f))}" for d, f in got) or "clean")


if __name__ == "__main__":
    main()
