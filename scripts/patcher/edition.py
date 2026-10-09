"""The download's edition: a trimmed patcher (e.g. "Sluggers Characters Beta", git-10 / git-92), or the full one.

package.py --edition <name> copies scripts/patcher/editions/<name>.json to the download's root as edition.json:
  {"name": "Sluggers Characters Beta", "features": [allowed feature ids], "hide_tabs": [...], "intro": "...",
   "profile": "profiles/<the edition's own profile>.json",
   "characters": [characters/ stems it offers], "recolors": [recolors/ stems]}   (optional; absent: all of them)
  "follow_settings": [feature ids]: offered but never shown, on exactly when a character setting needs one (the
   beta's Clamber Jump: its Fielding list; patch.edition_follow)
  "cpu_levels_editable": [5]: the CPU levels its CPU levels window may change (the beta: level 5 only; level 6 always
   builds with today's values; cpu_tab, patch.check_cpu_settings). Absent: both (5 and 6).
  "creators": ["item"]: the creation kinds it offers (the beta's Items window, items_window.py: make your own items);
   a profile's other creations are dropped (patch.edition_trim), and creators/blocks.py loads no other kind.
  "trace_profiles": [profiles relative to scripts/patcher]: built and traced too by package.py --trace, for the files
   of features its own profile has off (the beta's items: editions/characters-beta-items.trace.json)
  "never_rolled": ["starbits"]: items whose code comes in with the item features it offers but that it doesn't roll
   by default: weight 0 through item-odds (patch.edition_items) unless the profile gives it odds (the beta's Items
   window lists Star Bits with its odds 0 by default, items_window.OURS).
load() returns that dict, or None for the full patcher (no edition.json: the repo, and the full download).
SLUGGERS_EDITION=<name> loads editions/<name>.json instead (package.py --trace runs the window as the edition).
"""
import json, os
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
EDITIONS = Path(__file__).resolve().parent / "editions"


def load():
    if os.environ.get("SLUGGERS_EDITION"):
        return named(os.environ["SLUGGERS_EDITION"])
    p = ROOT / "edition.json"
    return json.loads(p.read_text(encoding="utf8")) if p.exists() else None


def named(name):
    """An edition from scripts/patcher/editions/ by name (package.py)."""
    return json.loads((EDITIONS / f"{name}.json").read_text(encoding="utf8"))


def offers(kind, path):
    """Whether this download offers the character ("characters") or recolor ("recolors") at path. The short list only
    limits OUR files (git-92): anything outside the download (an import) is the player's, and in a download every
    recipe under recolors/ is too, since package.py --edition ships only the offered ones (edition_files). A file the
    player made in the window ("made_by": "player": the single page's New character / New recolor, git-10) is theirs
    wherever it is."""
    ed = load() or {}
    if kind not in ed:
        return True
    p = Path(path).resolve()
    if p.stem in ed[kind] or ROOT not in p.parents:
        return True
    if kind == "recolors" and (ROOT / "edition.json").exists():
        return True
    try:
        return json.loads(p.read_text(encoding="utf8")).get("made_by") == "player"
    except (OSError, ValueError):
        return False


# words that are ours but never the beta's (Nick: "NO REFERENCES TO FUTURE FEATURES"), besides feature ids, the tabs an
# edition hides and the characters / recolors it doesn't offer
FUTURE_WORDS = ("full patcher", "coming soon", "coming later", "come with", "comes with", "items", "item", "stadium",
                "stadiums", "hazard", "hazards", "star pitch", "star pitches", "star swing", "star swings",
                "star moves", "captain select", "captains", "abilities")


# the item features an edition may offer (the Characters Beta's Items window): with any of them, "item(s)" is its word
ITEM_FEATURES = ("item-odds", "item-variants", "item-engine", "fixed-items", "item-ability")


# Nick, 2026-09-28 ("Allow the words here"): the beta's CPU levels window (cpu_tab.Window) names the game's own items
# and star moves (the CPU's item use, star swings, star pitches); FUTURE_WORDS stay for every other text.
def unoffered_words(ed):
    """What an edition's texts may never name: the features it doesn't have, the tabs it hides, the characters and
    recolors it doesn't offer (a player's own are theirs) and FUTURE_WORDS. The full patcher (ed None): nothing."""
    if not ed:
        return []
    import charbuild
    import recolor
    words = [f for f in charbuild.FEATURES if f not in set(ed.get("features", ()))]
    words += list(getattr(charbuild, "NOT_IN_BUILD", {})) + list(ed.get("hide_tabs", ())) + list(FUTURE_WORDS)
    if {"boot-captain-select", "boot-game"} & set(ed.get("features", ())):   # the game's own screen, which its
        words.remove("captain select")                                      # game options name (Start at ...)
    if "captains" in ed.get("features", ()):         # offered (the beta page's Captains section), even with its tab hidden
        words = [w for w in words if w.lower() not in ("captains", "captain select")]
    if set(ITEM_FEATURES) & set(ed.get("features", ())):   # the beta's Items window (items_window.py), which sets
        words = [w for w in words if w.lower() not in ("item", "items", "knockback")]   # items' knockback too
    for p in sorted((ROOT / "characters").glob("*.json")) + sorted((ROOT / "recolors").glob("*.json")):
        try:
            d = json.loads(p.read_text(encoding="utf8"))
        except (OSError, ValueError):
            continue
        if not d.get("name") or d.get("made_by") == "player":
            continue
        tool = p.parent.name == "recolors" or str(d.get("_why", "")).startswith("Recolor tool")
        kind, stem = ("recolors", recolor.slug(d["name"])) if tool else ("characters", p.stem)
        if kind in ed and stem not in ed[kind]:
            words.append(d["name"])
    return sorted(set(words), key=len, reverse=True)


def mentions(text, ed=None, skip=("The community",)):
    """The lines of text (an edition's credits, intro, ...) naming something the edition doesn't offer
    (unoffered_words), skipping the sections titled `skip` (CREDITS.md's "The community": people and their own mods
    stay as they are, git-92). ed: the edition dict (default: this download's). The release gate and credits.py's
    tests use it."""
    import re
    ed = load() if ed is None else ed
    words = unoffered_words(ed)
    if not words:
        return []
    bad = re.compile(r"(?<![\w-])(" + "|".join(re.escape(w) for w in words) + r")(?![\w-])", re.I)
    heads = set()
    source = ROOT / "CREDITS.md"
    if source.exists():
        heads = {l[3:].strip() for l in source.read_text(encoding="utf8").splitlines() if l.startswith("## ")}
    out, section = [], None
    for line in text.splitlines():
        s = line.strip().lstrip("#").strip()
        if s in heads:
            section = s
        elif section not in skip and bad.search(line):
            out.append(line.strip())
    return out
