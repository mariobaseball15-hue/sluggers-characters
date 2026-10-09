"""The patcher's window: pick your game, tick the features you want, patch (docs/patcher.md).

  python scripts/patcher/gui.py          (the download's exe opens it when started with no arguments: app.py)

Stdlib tkinter only (the download is PyInstaller). The feature list is patch.registry() (charbuild.FEATURES), grouped
like the notes page (notes_entries.json), with what each changes in the game in the patcher's own words
(features_text.json). A profile saved here is the patcher's JSON, so it works with patch.py --profile and the console flow.
The patch is patch.run in a worker thread with its output in the log; a refusal (SystemExit) is shown as it is.
"""
import json, queue, sys, tempfile, threading, traceback
import tkinter as tk
from tkinter import ttk, filedialog, messagebox
from tkinter.scrolledtext import ScrolledText
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
import patch
import fit
import style
import widgets
import leftout
import character_window             # one window per character, in both patchers (git-10)
import game_options                 # Game options (the beta's window) and the replay tweaks' boxes
# pages in their own modules (git-e2), each left out while its module isn't there yet (the tabs': _tab_module,
# listed in package.DYNAMIC_MODULES so the full download ships them)
try:
    import char_editor                  # one character's stats, chemistry and names (a Characters tab button)
except ModuleNotFoundError as e:
    if e.name != "char_editor":
        raise
    char_editor = None
try:
    import edition                      # a trimmed download (package.py --edition, git-dc): its name, tabs and profile
except ModuleNotFoundError as e:
    if e.name != "edition":
        raise
    edition = None
EDITION = edition.load() if edition else None      # None: the full patcher
HIDE_TABS = set(EDITION.get("hide_tabs", ())) if EDITION else set()


def _tab_module(name, tab):
    """A page's module, or None: left out while it isn't there yet, and never imported by an edition that hides its
    tab (Nick: "no code for features that are not in the beta"; package.py --edition ships only what's imported)."""
    if tab in HIDE_TABS:
        return None
    import importlib
    try:
        return importlib.import_module(name)
    except ModuleNotFoundError as e:
        if e.name != name:
            raise
        return None


create_tab = _tab_module("create_tab", "Create")            # Create: items, star swings and star pitches from blocks
stadiums_tab = _tab_module("stadiums_tab", "Stadiums")      # Stadiums: the stadium builder, the select map, hazards
abilities_tab = _tab_module("abilities_tab", "Abilities")   # Abilities: the game's fielding and baserunning abilities
cpu_tab = _tab_module("cpu_tab", "CPU levels")              # CPU levels: the level 5 / 6 CPU's numbers (cpu_settings)
SINGLE = bool(EDITION and EDITION.get("layout") == "single")   # one page, no tabs (the beta: beta_window.py, git-10)

ROOT = patch.ROOT
PROFILES = HERE / "profiles"
RECOLORS = ROOT / "recolors"        # the recolor editor writes its recipes here
# switches the player's picks turn on by themselves (a character, a recolor, a star pitch): never shown (git-92 for
# Nick: "Is this for debugging?"); ticked by needs / requires
AUTO_FOLLOWED = {"new-ids", "recolor-tool", "voices", "pitch-slots", "captains"}   # captains: the Captains tab
ONE_BOOT = {"boot-captain-select", "boot-game"}   # one start or the other (charbuild: the game wins)
TAB_OPTIONS = {"ability-edits", "cpu-settings"}   # switched on by a page's own option (the Abilities tab's
                                                 # options.ability_edits, the CPU levels tab's options.cpu-settings)
HIDDEN = {"stock-balance"}          # never offered, even if the registry lists it (Nick: no stock balance changes)

# groups as on the notes page (scripts/notes_entries.py writes it from wiki/index.html, which doesn't ship)
NOTES = json.loads((HERE / "notes_entries.json").read_text(encoding="utf8"))
GROUPS = [(g["id"], g["name"]) for g in NOTES["groups"]] + [("other", "More")]
GROUP_OF = {"toad-brigade": "characters", "voices": "characters", "immunities": "characters",   # not on the page
            "koopaling-items": "items", "item-engine": "items", "poltergust-dive": "fielding", "share-anim-banks": "gameplay",
            **{f: "gameplay" for f in ("level-5", "cpu-perfect-batting", "cpu-perfect-pitching",   # the CPU levels
                                       "cpu-perfect-fielding", "cpu-perfect-running", "cpu-pitching",   # tab's
                                       "cpu-charge-timing", "cpu-batter-track", "cpu-no-bunts", "cpu-cursed-ball", "cpu-star-swings",
                                       "cpu-no-star-pitches", "cpu-rundown", "cpu-items", "cpu-item-defense",
                                       "cpu-subs", "cpu-settings")},
            **{e["id"]: e["group"] for e in NOTES["entries"]}}
ORDER = [e["id"] for e in NOTES["entries"]]
# what each feature changes in the game, in the patcher's own words (not the notes page's)
TEXT = json.loads((HERE / "features_text.json").read_text(encoding="utf8"))["features"]
# where each feature's switch is shown (Nick: "the features screen needs a lot removed that is duplicated in the new
# tabs"; git-92's mapping). The ticks are the same everywhere (App.fvars); only where they're drawn differs. A tab
# calls app.feature_box(parent, home=...) for its "Our extras" box; a feature no tab places goes on Features.
FEATURE_HOMES = {
    "new": ("New characters & recolors", ["new-ids", "recolor-tool", "voices", "immunities", "toad-brigade",
                                          "poltergust-dive"]),
    "characters": ("Characters", ["item-ability", "fixed-items", "batter-star", "chance-cheer", "minimap-decoys",
                                  "new-ability-slot", "star-solo-toss", "clamber-solo-jump"]),
    "captains": ("Captains", ["captains", "cutin-backdrops"]),
    "stadiums": ("Stadiums", ["new-stadium", "day-night-scenes", "select-map-day-night", "moving-scenery",
                              "dimensions", "mansion-day", "walking-bobombs", "octoombas", "piranha-plants"]),
    "items": ("Create > Items", ["new-roulette-item", "item-variants", "freeze-on-hit", "knockback", "item-flight",
                                 "multi-shot", "homing", "reused-hazard-model", "field-hazard-items",
                                 "koopaling-items", "item-odds"]),
    "swings": ("Create > Star swings", ["custom-swings", "swing-path", "swing-items"]),
    "pitches": ("Create > Star pitches", ["pitch-slots", "pitch-path", "pitch-vanish", "pitch-items"]),
    "abilities": ("Abilities", []),    # ability-edits: ticked by the tab's own option (TAB_OPTIONS; git-92)
    "cpu": ("CPU levels", ["level-5", "cpu-perfect-batting", "cpu-perfect-pitching", "cpu-perfect-fielding",
                           "cpu-perfect-running", "cpu-pitching", "cpu-charge-timing", "cpu-batter-track",
                           "cpu-no-bunts", "cpu-cursed-ball", "cpu-star-swings", "cpu-no-star-pitches", "cpu-rundown",
                           "cpu-items",
                           "cpu-item-defense", "cpu-subs"]),   # the tab's Switches rows (Both / Level 5 / Level 6), not a
                                                                 # feature_box; cpu-settings: its own option (TAB_OPTIONS)
    "features": ("Features", ["menu-color", "bench", "fielder-spots", "batter-depth", "share-anim-banks",
                              "captain-faceoff", "no-replays", "replay-slow-motion", "replay-camera", "contact-freeze",
                              "inning-break-time"]),   # (the last five: the "Replays, contact freeze, box score..."
}                                                      # button, game_options)
STAR_PITCHES = {13: "Cosmic Pull", 14: "Launch Star", 15: "Bob-omb Drop", 16: "Vanishing Ball"}   # in-game names
# a recolor is a new character on a stock character's color wheel
RECOLOR_NEEDS = {"recolor-tool", "new-ids"}   # (the grid and wheels past 6: part of new-ids)
# per-character settings, on any character (stock, new or recolor): (label, profile key, kind of value)
CHAR_OPTIONS = [("Batting item (for the batter before them)", "batting_item", "items"),
                ("Always gets their batting item", "always_item", "bool"),
                ("Piranha Plants in the field", "piranha_plants", "bool"),
                ("A star when coming up to bat", "batter_star", "bool"),
                ("Custom Chance Cheer", "chance_cheer", "bool"),
                ("Star swing", "star swing", "swings"),
                ("Star pitch", "star pitch", "pitches"),
                ("Fielding ability", "fielding ability", "fielding"),
                ("Mini-map decoys", "minimap_decoys", "bool"),
                ("Item ability (card label)", "item_ability", "label"),
                ("Special ability (card label)", "special_ability", "label"),
                ("Hitting ability (card label)", "hitting_ability", "label"),
                ("Running ability (card label)", "running_ability", "label")]
LABEL_KEYS = ("item_ability", "special_ability", "hitting_ability", "running_ability")   # charbuild.STOCK_KEYS
ONE_OF = {"item_ability": "special_ability", "special_ability": "item_ability"}   # a card has one or the other
AS_IS = "As it is"
# what a setting does in a match, where the label can't say it all (widgets.tip)
OPTION_TIPS = {
    "batting_item": "The teammate batting just before this character gets this item: when this character is on deck, "
                    "the batter gets it (as with the game's own item carriers).",
    "always_item": "The batter gets it from this character even without good chemistry between them.",
}
# batting item names (batter_items.NAMES, koopa_items.NAMES) as players know them; any other name shows as it is
ITEM_TITLES = {"shell": "Shell", "fireball": "Fireballs", "bobomb": "Bob-omb", "pow": "POW", "banana": "Bananas",
               "boo": "Boo", "starbits": "Star Bits", "ice": "Ice ball", "bill": "Bullet Bill",
               "lemmy": "Lemmy's ball", "iggy": "Iggy's item", "larry": "Larry's item", "wendy": "Wendy's item",
               "ludwig": "Ludwig's item"}


def item_features(value):
    """The features a batting item needs (charbuild FEATURES "fixed-items": items 6+ need new-roulette-item, 7
    item-variants, 8+ koopaling-items)."""
    import batter_items
    if value in (None, False, "", "none"):
        return {"fixed-items"}
    try:
        i = batter_items.item_id(value)
    except (AssertionError, KeyError, ValueError):   # an item creation, by name (git-dc): a new item (ids 14+,
        return {"fixed-items", "item-engine"}             # git-f3: the item engine, not the Koopalings')
    return {"fixed-items"} | ({"new-roulette-item"} if i >= 6 else set()) | (
        {"item-variants"} if i == 7 else set()) | ({"koopaling-items"} if i >= 8 else set())


def option_features(key, value):
    """The features a per-character setting needs (none for off / none / a stock value)."""
    if value in (None, False, 0, "", "none"):
        return set()
    if key in LABEL_KEYS:
        return {"item-ability"}
    if key == "star pitch":
        if isinstance(value, str):               # by name (git-95): ours map to theirs; a brand-new one's feature
            import star_move_labels              # depends on its path, which its Create page's needs() gives
            value = {n: i for i, n in star_move_labels.PITCH_NAMES.items()}.get(value, 0)
        return {{13: "pitch-path", 14: "pitch-path", 15: "pitch-items", 16: "pitch-vanish"}.get(int(value))} - {None}
    if key == "batting_item":
        return item_features(value)
    if key == "star swing":
        if isinstance(value, str):               # a star swing creation, by name (git-95: creators.swings)
            return {"custom-swings"}
        return {13: {"custom-swings"}, 14: {"custom-swings"}, 15: {"custom-swings", "swing-items"}}.get(int(value), set())
    if key == "fielding ability":                # 13 Tantrum Toss, 14 Clamber Jump (git-a7 85fc933)
        return {{13: "star-solo-toss", 14: "clamber-solo-jump"}.get(int(value))} - {None}
    f = {"piranha_plants": "piranha-plants", "batter_star": "batter-star", "minimap_decoys": "minimap-decoys",
         "always_item": "fixed-items", "chance_cheer": "chance-cheer"}.get(key)
    return {f} if f else set()


# The build's own log lines (charbuild) -> what the player reads while it runs: (line starts with, plain step).
# patch.run's own steps come as "== ..." lines (git-dc). Each step shows once; the full log is under "details".
BUILD_STEPS = [
    ("table stats", "Adding the new characters' stats"),
    ("poltergust", "Giving Luigi the Poltergust dive"),
    ("stat edits", "Changing stock characters' stats (balance changes)"),
    ("chem edits", "Changing stock characters' chemistry (balance changes)"),
    ("selector", "Making room for the new characters in the game's tables"),
    ("EI icon bank", "Adding the new characters' icons"),
    ("stock model", "Giving the Toads their Toad Brigade models"),
    ("own cut-in backdrops", "Adding captains' own cut-in backdrops"),
    ("stadium 10", "Building the new stadium"),
    ("stadium map", "Adding the new stadium to the stadium-select map"),
    ("stadium 6", "Adding Luigi's Mansion by day"),
    ("names", "Adding the new characters' names"),
    ("bench", "Adding bench players"),
    ("star bits", "Adding Star Bits to the item roulette"),
    ("chemistry", "Setting the new characters' chemistry"),
    ("grid:", "Building the character-select grid"),
    ("wheel7", "Making the bigger color wheels hold up to 10 characters"),
    ("item ability", "Adding ability labels to the character cards"),
    ("hitting ability", "Adding ability labels to the character cards"),
    ("captain", "Adding the new captains"),
    ("pauline chance", "Adding the Custom Chance Cheer"),
    ("buddy clamber", "Adding Clamber Jump"),
    ("batting items", "Setting each character's batting item"),
    ("batter star", "Giving stars at bat"),
    ("cut-in backdrop", "Setting the Tantrum Toss backdrop"),
    ("star swings", "Adding the new star swings"),
    ("immunities", "Setting who the Heart swing and POW spare"),
    ("mini-map decoys", "Adding mini-map decoys"),
    ("voice", "Adding the new characters' voices"),
    ("ice item", "Adding the Ice ball item"),
    ("ludwig", "Adding the Koopalings' items"),
    ("koopa items", "Adding the Koopalings' items"),
    ("wendy rings", "Adding the Koopalings' items"),
    ("star shower", "Adding Star Shower's Star Bits"),
    ("batter depth", "Adding stepping up or back in the batter's box"),
    ("piranha plants", "Adding Piranha Plants"),
    ("octoombas", "Adding Octoombas to the new stadium"),
    ("bob-ombs", "Adding walking Bob-ombs to the new stadium"),
    ("dimensions", "Setting the new stadium's field sizes"),
    ("star throw", "Adding Star Solo Buddy Toss"),
    ("Tantrum Toss", "Adding Star Solo Buddy Toss"),
    ("star pitch 15", "Adding the Bob-omb Drop star pitch"),
    ("star pitch 16", "Adding the Vanishing Ball star pitch"),
    ("launch star", "Adding the Launch Star star pitch"),
    ("gravity well", "Adding the Gravity Well star pitch"),
    ("abilities", "Adding move names to the cards and captain select"),
    ("star moves", "Adding move names to the cards and captain select"),
    ("star swing row", "Adding move names to the cards and captain select"),
    ("star pitch row", "Adding move names to the cards and captain select"),
    ("baserunning row", "Adding move names to the cards and captain select"),
    ("quickboot", "Making the game start at captain select"),
    ("start at captain select", "Making the game start at captain select"),     # (charbuild's plain lines)
    ("start in a game", "Making the game start in a game"),
    ("CPU vs CPU", "Making Exhibition games CPU vs CPU"),
    ("menu background color", "Coloring the menu background"),
    ("icon bank", "Writing the character icons"),
    ("wrote", "Writing the patched game files"),
    ("dry run:", "Check finished: nothing was written"),
]


def step_of(line):
    """The plain step a log line belongs to (None: detail only). "== " lines are patch.run's own steps."""
    if line.startswith("== "):
        return line[3:].strip()
    return next((text for start, text in BUILD_STEPS if line.startswith(start)), None)


# the progress bar (build_progress_tab): patch.run's "== " lines, each a stage with its short name, where the bar stands
# when it starts and where the stage ends (0-1). While a stage runs the bar creeps toward its end (never there), so it
# moves through a long stage (the build, the ISO write); Done fills it. {rest}: the line's text after the prefix.
STAGES = [
    ("Checking your game", "Checking your game", 0.0, 0.12),
    ("Extracting", "Extracting your game", 0.02, 0.10),
    ("Rebuilding", "Preparing files (first run only)", 0.10, 0.12),
    ("Reading the stadium", "Reading the stadium", 0.12, 0.14),
    ("Adding", "Adding {rest}", 0.12, 0.25),
    ("Recoloring", "Recoloring {rest}…", 0.14, 0.25),
    ("Making the voices", "Making the voices", 0.25, 0.40),
    ("Building", "Building", 0.40, 0.78),
    ("Checking memory", "Checking memory", 0.78, 0.80),
    ("Writing the ISO", "Writing the ISO", 0.80, 1.0),
    ("Done", "Done", 1.0, 1.0),
]


def stage_of(line, dry=False):
    """(short name, start 0-1, end 0-1) for a patch.run "== " line, or None (not a stage). A check (dry) writes no
    ISO: its build runs to the end."""
    if not line.startswith("== "):
        return None
    text = line[3:].strip()
    for prefix, name, start, end in STAGES:
        if text.startswith(prefix):
            rest = text[len(prefix):].strip(" :")
            if prefix == "Adding":
                rest = rest.replace(" (imported)", "").split(":")[0]
            return name.format(rest=rest), start, (1.0 if dry and prefix == "Building" else end)
    return None


def rel(p):
    p = Path(p).resolve()
    return p.relative_to(ROOT).as_posix() if p.is_relative_to(ROOT) else str(p)


class Writer:
    """stdout for the worker thread: whole lines go to the window's queue."""
    def __init__(self, q):
        self.q, self.buf = q, ""

    def write(self, s):
        self.buf += s
        *lines, self.buf = self.buf.split("\n")
        for line in lines:
            self.q.put(("log", line))

    def flush(self):
        if self.buf:
            self.q.put(("log", self.buf))
            self.buf = ""


# each tab's first line: what it changes in the game and what it can't do (Nick: the patcher says exactly what it does)
INTRO = {
    "features": "Tick what you want in your game; each line says what it changes. The patcher writes a new copy of "
                "your game and never changes your own. Stock characters' balance isn't changed.",
    "new": "Adds our new characters and recolors to character select, each on a stock character's color wheel. The "
           "grid holds 60 squares (19 new), and a wheel holds 10. Recolors are made from your own game's textures. "
           "Import character... adds one someone else made.",
    "characters": "Changes any character, stock or new: batting item, star swing and pitch, fielding ability, card "
                  "labels, and (Edit stats, chemistry and names...) stats, chemistry and names. A stock character's "
                  "size, and different names per language, aren't in the patcher yet.",
    "progress": "What the patcher is doing. Check runs every step and writes nothing; Patch writes the new game.",
}
INTRO.update((EDITION or {}).get("intros", {}))    # an edition's own wording for the tabs it trims


HOW_TO_NEW = ["Tick the new characters you want. Their own parts (voice, items, star moves) are switched on for you "
              "(you'll see them in the check before patching).",
              "Tick recolors to add them to their stock character's colour wheel. New recolor... makes your own; "
              "Edit changes one.",
              "The Characters tab then lists them, to change their settings.",
              "Import character... adds a character someone else made."]
HOW_TO_NEW_SHARE = "your recolors are small files in the recolors folder: send one to share it, and put one you get " \
                   "there. Characters are shared as character files (.slgmodel; Import character)."
HOW_TO_NEW_REFUSED = "anything your picks need goes on by itself when you patch (Progress says what it turned on)."
HOW_TO_IMPORT = ["Get a character file (.slgmodel) from the player who made it, a model edited with Jaws' Sluggies "
                 "(.sluggie, or a texture pack's PNG), or a model file from a game or mod.",
                 "Press Import character and pick it (A file...), or pick the whole folder it came in (A "
                 "folder...): its portraits (side.png, front.png) and voice clips (voice/v1.wav ...) come too. The "
                 "patcher checks it against your own game: the files carry no game data, so their models are rebuilt "
                 "from your game's files.",
                 "If it's fine, you see who made it, the character it's built on and any notes (a name that's taken "
                 "gets \"(2)\"). Press Yes to import it.",
                 "Tick it to put it in your game; it then shows on the Characters tab like our new characters.",
                 "Imported characters live in your own folder (Open folder), so a new patcher keeps them. Remove "
                 "deletes one."]
HOW_TO_IMPORT_SHARE = "a character file (.slgmodel) is one file: send it, and the other player imports it."
HOW_TO_IMPORT_REFUSED = "the check says why in words, e.g. a picture of the wrong size, sounds in the wrong format, " \
                        "or a name the game's font can't show."


CREDITS_TOP = ("This patcher is made possible by years of community work. Is something here yours, or missing? Tell us on the "
               "modding Discord.")


def data_fields():
    """{field id: what it changes in the game's data, or None} for the fields this window edits itself (git-92's "i"
    layer; test_info_coverage.py). The data is each owner's (patch.FIELD_DATA: git-dc), never written here."""
    fd = getattr(patch, "FIELD_DATA", {})
    out = {f"characters.{key}": fd.get(key) for _, key, _ in CHAR_OPTIONS}
    out.update({"features.menu-color": fd.get("menu-color"), "features.item-odds": fd.get("item-odds")})
    return out


def credit_line(parent, key):
    """A tab's grey "Thanks to ..." line (scripts/credits.py, from CREDITS.md; git-10 / git-92), as it is, or None
    when it has none. Packed by the caller."""
    try:
        import credits
        line = credits.tab_line(key)
    except (ImportError, OSError):
        return None
    return fit.label(parent, line, grey=True) if line else None


def intro(parent, key, **pack):
    """A tab's first line (INTRO), packed at the top."""
    import fit
    label = fit.label(parent, INTRO[key], bold=True)
    label.pack(fill="x", pady=(0, 4), **pack)
    return label


class Scrolled(ttk.Frame):
    """A frame that scrolls (self.inner holds the content) only when it has to: the scrollbar shows, and the mouse
    wheel scrolls, while the content is taller than the room it's given (Nick, Patcher 10: "Features is scrolling even
    though it fits"); re-checked when either changes size (a box opened, the window resized)."""
    def __init__(self, parent):
        super().__init__(parent)
        self.canvas = tk.Canvas(self, highlightthickness=0, width=200, height=160)   # asks for little: the window
        # gives it the room (pack fill / expand)
        self.bar = ttk.Scrollbar(self, orient="vertical", command=self.canvas.yview)
        self.inner = ttk.Frame(self.canvas)
        win = self.canvas.create_window((0, 0), window=self.inner, anchor="nw")
        self.height = None              # the room the canvas was last given (its <Configure>)
        self.inner.bind("<Configure>", lambda e: self.refit())
        self.canvas.bind("<Configure>", lambda e: (self.canvas.itemconfigure(win, width=e.width), self.refit(e.height)))
        self.canvas.configure(yscrollcommand=self.bar.set)
        self.canvas.pack(side="left", fill="both", expand=True)
        self.bind("<Enter>", lambda e: self.bind_all("<MouseWheel>", self.wheel))
        self.bind("<Leave>", lambda e: self.unbind_all("<MouseWheel>"))
        self.scrolls = False

    def refit(self, height=None):
        """Scroll only when the content is taller than the room (height: what the canvas was given, else as laid
        out): else no scrollbar, back to the top."""
        import fit
        if height is not None:
            self.height = height
        self.canvas.configure(scrollregion=self.canvas.bbox("all"))
        self.scrolls = self.inner.winfo_reqheight() > (self.height or fit.size(self.canvas)[1]) + 1
        if self.scrolls and not self.bar.winfo_manager():
            self.bar.pack(side="right", fill="y", before=self.canvas)
        elif not self.scrolls and self.bar.winfo_manager():
            self.bar.pack_forget()
        if not self.scrolls:
            self.canvas.yview_moveto(0)

    def wheel(self, e):
        if self.scrolls:
            self.canvas.yview_scroll(int(-e.delta / 120), "units")


def imported_definition(c):
    """An imported character's definition (charpack.list_imported's item) with its icons' paths made whole: they're
    relative to its own folder (icons/side.png), as charpack.materialize reads them for the build (Nick's Beta 3.6.4:
    Luma's grid square showed her name, not her portrait)."""
    d = json.loads(Path(c["definition"]).read_text(encoding="utf8"))
    if isinstance(d.get("icon"), dict):
        d["icon"] = {view: str(Path(c["folder"]) / rel) for view, rel in d["icon"].items()}
    return d


class LazyLists(dict):
    """App.choice_lists: {kind: {label: value}}, with the lists named in `later` made on first use."""

    def __init__(self, lists, **later):
        super().__init__(lists)
        self.later = later

    def __missing__(self, kind):
        if kind not in self.later:
            raise KeyError(kind)
        self[kind] = self.later.pop(kind)()
        return self[kind]

    def ready(self, kind):
        return kind in self


LAST_GAME = Path.home() / ".sluggers-patcher-game.txt"   # the game the player last patched with (one line)


def is_game(p):
    """p is the USA disc (RMBE01): an .iso, or an extracted folder (sys/boot.bin), and not one this patcher wrote
    (those have a "(patch details)" folder, or an older build's .profile.json, beside them)."""
    p = Path(p)
    if (p.with_name(p.stem + " (patch details)").is_dir() or p.with_name(p.name + ".profile.json").exists()
            or p.with_suffix(".profile.json").exists()):
        return False
    head = p / "sys/boot.bin" if p.is_dir() else p
    try:
        with open(head, "rb") as f:
            return f.read(6) == b"RMBE01"
    except OSError:
        return False


def find_game_iso():
    """The game for the Your game box on first start: the last one used, else an .iso (or extracted folder) in the
    program's folder, the folder it was started from, the two folders above, Downloads, Desktop or Documents (and one
    level of subfolders in each). Nick: "there is no iso by default"."""
    try:
        last = LAST_GAME.read_text(encoding="utf-8").strip()
        if last and is_game(last):
            return Path(last)
    except OSError:
        pass
    home, root = Path.home(), Path(ROOT)
    folders = [root, Path.cwd(), root.parent, root.parent.parent, home / "Downloads", home / "Desktop",
               home / "OneDrive/Desktop", home / "Documents", home / "OneDrive/Documents"]
    for folder in dict.fromkeys(folders):
        try:
            subs = [folder] + sorted(d for d in folder.iterdir() if d.is_dir())
        except OSError:
            continue
        for d in subs:
            try:
                isos = sorted(d.glob("*.iso"), key=lambda q: q.stat().st_size, reverse=True)
                kids = [k for k in d.iterdir() if k.is_dir()] if d != folder else []
            except OSError:
                continue
            for cand in isos + ([d] if d != folder else []) + kids:
                if is_game(cand):
                    return cand
    return None


def remember_game(game):
    try:
        LAST_GAME.write_text(str(game), encoding="utf-8")
    except OSError:
        pass

class App:
    # batter_items, koopa_items, custom_swings and menu_purple load when a list or the feature is first shown, so an
    # edition that shows none of them never imports them (git-92, the lean Beta 3.6: git-dc's beta_module_gate)
    @property
    def menu_purple(self):
        import menu_purple
        return menu_purple

    @property
    def swings(self):
        """{label: id} of our star swings (custom_swings.SWINGS)."""
        if "_swings" not in self.__dict__:
            import custom_swings
            self._swings = {f"{s['name']} ({i})": i for i, s in sorted(custom_swings.SWINGS.items())}
        return self._swings

    @property
    def items(self):
        """{label: name} of the batting items (batter_items.NAMES, KOOPA_NAMES)."""
        if "_items" not in self.__dict__:
            import batter_items
            names = list(batter_items.NAMES) + [n for n in batter_items.KOOPA_NAMES.values()
                                                if n not in batter_items.NAMES]
            self._items = {"No item": "none", **{ITEM_TITLES.get(n, n): n for n in names}}
        return self._items

    def __init__(self, root):
        import charbuild
        from sluggers_data import CHAR_NAMES
        self.root = root
        style.apply(root)               # the theme, fonts, styles and app icon (style.py), before any widget
        if "report_callback_exception" not in root.__dict__:   # (app.py --check and tests collect their own)
            root.report_callback_exception = self.callback_error
        style.title(root)                   # the edition's name, or "Sluggers Patcher" (style.APP_NAME)
        root.geometry("900x760")
        self.reg = patch.registry()
        # not checkboxes: HIDDEN, and the options a tab of this window sets (charbuild NOT_IN_BUILD: "an option set by
        # the patcher window's ... tab": grid-order, the creators, ...)
        self.not_offered = HIDDEN | {f for f, r in self.reg.items() if "patcher window" in str(r.get("doc", ""))
                                     or r.get("switch") == "not in the patched game"}   # (Nick: never shown)
        self.supports = getattr(charbuild, "SUPPORTS", set())
        self.stock = [(i, CHAR_NAMES[i].strip()) for i in range(min(0x65, len(CHAR_NAMES))) if CHAR_NAMES[i].strip()]
        self.q = queue.Queue()
        self.running = False
        self.extra_characters = {}      # a loaded profile's per-character keys this window has no picker for
        self.extra_options = {}         # and options
        self.odds = {}                  # item-odds: {item name: its box}, when the build has the feature
        self.color = tk.StringVar()     # menu-color's box (made again with the feature's row, menu_purple.DEFAULT;
        # an edition without the feature has none)
        self.boot_game = None           # boot-game's teams (options["boot-game"]; game_options.py), None: Mario vs Bowser
        self.boot_captain = None        # boot-captain-select's stadium (options["boot-captain-select"]: {"stadium",
        # "night"}; game_options.py), None: Mario Stadium by day
        self.bench_dh = tk.BooleanVar(value=True)   # bench's DH (options["bench"]["dh"]; Game options)
        self.seed = tk.StringVar()      # match-seed's seed (options["match-seed"]["seed"]), blank: the clock
        self.replay = game_options.replay_vars()   # the replay tweaks' options (options["replay-slow-motion"], ...)
        self.new_chars, self.recipes = self.find_characters(charbuild)

        top = ttk.Frame(root, padding=(style.PAD, style.PAD, style.PAD, style.GAP))
        top.pack(fill="x")
        self.game, self.iso, self.about = tk.StringVar(), tk.StringVar(), tk.StringVar()
        if (charbuild.SRC / "sys/main.dol").exists():
            self.game.set(str(charbuild.SRC))
        else:                                           # (Nick: your own ISO next to the program, found for you)
            found = find_game_iso()
            if found:
                self.game.set(str(found))
        self.auto_iso = ""                              # the Save as we filled in (kept in step with the game)
        self.game.trace_add("write", lambda *a: self.default_iso())
        self.default_iso()
        # two rows, the labels in one column (the room goes to the grid: Nick's 860 x 620)
        widgets.tip(ttk.Label(top, text="Your game:"), "The USA disc (RMBE01): an .iso or the extracted folder. "
                    "Model and texture mods are fine.").grid(row=0, column=0, sticky="w")
        ttk.Entry(top, textvariable=self.game).grid(row=0, column=1, columnspan=3, sticky="ew", padx=style.GAP)
        game_buttons = ttk.Frame(top)
        game_buttons.grid(row=0, column=4, sticky="e")
        ttk.Button(game_buttons, text="ISO file...", command=self.pick_iso_in).pack(side="left")
        ttk.Button(game_buttons, text="Folder...", command=self.pick_folder_in).pack(side="left", padx=(style.GAP, 0))
        ttk.Label(top, text="Save as:").grid(row=1, column=0, sticky="w", pady=(style.GAP, 0))
        ttk.Entry(top, textvariable=self.iso).grid(row=1, column=1, sticky="ew", padx=style.GAP, pady=(style.GAP, 0))
        ttk.Button(top, text="Choose...", command=self.pick_iso_out).grid(row=1, column=2, sticky="w",
                                                                         pady=(style.GAP, 0))
        widgets.tip(ttk.Label(top, text="Name for these choices:"), "Saved with Save choices... (its about line)."
                    ).grid(row=1, column=3, sticky="e", padx=(style.PAD * 2, 0), pady=(style.GAP, 0))
        ttk.Entry(top, textvariable=self.about, width=22).grid(row=1, column=4, sticky="ew", padx=(style.GAP, 0),
                                                              pady=(style.GAP, 0))
        top.columnconfigure(1, weight=1)

        if EDITION and EDITION.get("intro"):           # what this download is (a trimmed edition of the patcher)
            fit.label(root, EDITION["intro"], bold=not SINGLE, grey=SINGLE, padding=(8, 0, 8, 4)).pack(fill="x")

        self.tabs = ttk.Notebook(root)
        if SINGLE:                      # the tabs are built (their state is the profile) but never shown
            import beta_window
            self.beta = beta_window.Page(self)
        else:
            self.tabs.pack(fill="both", expand=True, padx=8)
        self.build_features_tab()
        import char_names               # the Toads' names follow the Toad Brigade tick (git-92: never in the beta)

        def toads(*a):
            char_names.TOADS = bool("toad-brigade" in self.fvars and self.fvars["toad-brigade"].get())
            if getattr(self, "grid_tab", None) is not None:
                self.grid_tab.redraw()
        toads()
        if "toad-brigade" in self.fvars:
            self.fvars["toad-brigade"].trace_add("write", toads)
        self.build_characters_tab()
        self.build_settings_tab()
        self.captains_tab = None
        if "Captains" not in HIDE_TABS:
            import captain_editor
            self.captains_tab = captain_editor.CaptainsTab(self.tabs, self)
        elif SINGLE:                    # the beta: the Captains section under its page's grid (None: not offered)
            self.captains_tab = self.beta.add_captains()
        import grid_editor
        if SINGLE:                      # the page's middle: the grid, click a character to edit it
            self.grid_tab = grid_editor.GridTab(self.beta.grid_parent, self, always_on=True,
                                                on_open=self.beta.open_character)
        else:
            self.grid_tab = grid_editor.GridTab(self.tabs, self,         # a click opens the character's window
                                                on_open=lambda name: character_window.open_character(self, name))
        self.tabs.bind("<<NotebookTabChanged>>", lambda e: self.tab_changed())
        # a page module's add_tab gives its part of the profile: to_profile() -> {key: value}, load(profile)
        self.parts = [m.add_tab(self.tabs, self) for m, tab in ((create_tab, "Create"), (stadiums_tab, "Stadiums"),
                                                                (abilities_tab, "Abilities"), (cpu_tab, "CPU levels"))
                      if m and tab not in HIDE_TABS]
        if EDITION and "Create" in HIDE_TABS and "item" in EDITION.get("creators", ()):   # the beta's own items
            import items_window                         # (its Items window; the part holds them, unshown)
            self.parts.append(items_window.ItemsPart(self.tabs, self))
        self.place_the_rest()           # a feature no (shown) tab placed goes on Features: always reachable
        self.build_credits_tab()
        self.defaults = {f for f, r in self.reg.items() if r.get("default") and f in self.fvars}
        for f in self.defaults:         # on unless the player unticks it (patch.registry "default"; a saved profile
            self.fvars[f].set(True)     # keeps its own picks)
        self.build_progress_tab(self.beta.progress_parent if SINGLE else None)

        bottom = ttk.Frame(root, padding=(style.PAD, style.GAP, style.PAD, style.PAD))
        bottom.pack(side="bottom", fill="x")      # pinned: packed before the tabs (below), so a small window shrinks
        # the tabs, never the Check / Patch buttons (Nick: "the Patch button needs the window to be big enough")
        ttk.Button(bottom, text="Open choices...", command=self.load_dialog).pack(side="left")
        ttk.Button(bottom, text="Save choices...", command=self.save_dialog).pack(side="left", padx=(style.GAP, 0))
        import gecko_window         # the player's Dolphin codes for the patched game (gecko_fix.py; imported here, so
        self.gecko_button = ttk.Button(bottom, text=gecko_window.BUTTON,   # an edition's trace ships it)
                                       command=lambda: gecko_window.open_window(self))
        self.gecko_button.pack(side="left", padx=(style.PAD * 2, 0))
        import modder_window            # names for the game's code, for modders (modder_files.py; the beta too, Nick)
        widgets.tip(ttk.Button(bottom, text=modder_window.BUTTON, command=lambda: modder_window.open_window(self)),
                    modder_window.TIP).pack(side="left", padx=(style.GAP, 0))
        self.patch_button = ttk.Button(bottom, text="Patch", style="Accent.TButton", width=10,
                                       command=lambda: self.start(dry=False))
        self.patch_button.pack(side="right")
        self.check_button = ttk.Button(bottom, text="Check (writes nothing)", command=lambda: self.start(dry=True))
        self.check_button.pack(side="right", padx=style.GAP)
        # the status line, with the window's own credit at its right ("The patcher", costing no height: a link to
        # Credits; hover: the line)
        status_row = ttk.Frame(root, padding=(style.PAD, style.GAP, style.PAD, 0))
        status_row.pack(side="bottom", fill="x", before=bottom)
        try:
            import credits
            patcher_line = credits.tab_line("The patcher")
        except (ImportError, OSError):
            patcher_line = None
        if patcher_line:
            link = ttk.Label(status_row, text="Thanks to the community (Credits)", style="Link.TLabel", cursor="hand2")
            link.pack(side="right", padx=(style.PAD, 0))
            link.bind("<Button-1>", lambda e: self.beta.show_credits() if SINGLE else self.tabs.select(self.credits_frame))
            widgets.tip(link, patcher_line)
            self.credit_link = link
        self.status = tk.StringVar()
        self.status_label = ttk.Label(status_row, textvariable=self.status, style="Hint.TLabel")
        self.status_label.pack(side="left", fill="x", expand=True)
        self.status_row = status_row
        if not SINGLE:
            self.tabs.pack_forget()             # the tabs take what's left, after the bars
            self.tabs.pack(fill="both", expand=True, padx=8)
        self.bottom_bar = bottom
        self.status.set(("Only the defaults are ticked (" + ", ".join(self.titles[f] for f in sorted(self.defaults)) +
                         "). " if self.defaults else "Nothing is ticked yet. ") +
                        "Tick what you want, or \"Start from everything\" on the Features tab.")
        if "Features" in HIDE_TABS:     # an edition with fixed features (the beta, Nick: "Features tab is irrelevant")
            self.tabs.hide(self.features_frame)     # hidden, not gone: its switches still hold the edition's features
            self.load(HERE / EDITION["profile"])
            self.status.set("Pick what to add on New characters & recolors, then Patch.")
        if SINGLE:
            self.beta.finish()
        character_window.install(self)          # right-click Open... / Delete... on the grid and the lists
        root.after(100, self.poll)

    # --- the game's characters and recolors

    def find_characters(self, charbuild):
        """([(path, definition, needs)], [(path, recipe)]): characters/*.json (the recolor tool's definitions go with
        their recipes) and recolors/*.json. needs: the features a definition needs (charbuild.char_features)."""
        defs = []
        for p in sorted((ROOT / "characters").glob("*.json")):
            if edition and not edition.offers("characters", p):     # an edition's own short list (the beta)
                continue
            d = json.loads(p.read_text(encoding="utf8"))
            if not d.get("_why", "").startswith("Recolor tool"):
                defs.append((p, d))
        needs = {}
        try:
            for c in charbuild.normalize([d for _, d in defs]):
                needs[int(c["id"])] = set(charbuild.char_features(c))
        except Exception:           # the build refuses it later, with its message
            pass
        # and every part of a character the build leaves out without its feature (its voice, Piranha Plants, ...;
        # Nick's name.iso came out without the voices): leftout asks charbuild.degrade
        self.char_parts = leftout.character_needs([d for _, d in defs], set(self.reg))
        for _, d in defs:                   # its star moves stay what it needs (unticking one unticks it)
            hard = needs.setdefault(int(str(d["id"]), 0), set())
            parts = self.char_parts.setdefault(d["name"], {})
            for f in [f for f in parts if f in hard]:
                del parts[f]
            hard.update(parts)
        chars = [(p, d, needs.get(int(str(d["id"]), 0), set())) for p, d in defs]
        recipes = [(p, json.loads(p.read_text(encoding="utf8"))) for p in sorted(RECOLORS.glob("*.json"))
                   if not edition or edition.offers("recolors", p)]
        return chars, recipes

    # --- features

    def build_features_tab(self):
        frame = self.features_frame = ttk.Frame(self.tabs)
        self.tabs.add(frame, text="Features")
        intro(frame, "features", padx=4)
        line = credit_line(frame, "Features")
        if line is not None:
            line.pack(fill="x", padx=4)
        bar = ttk.Frame(frame)
        bar.pack(fill="x", pady=4)
        ttk.Button(bar, text="Tick everything", command=self.tick_everything).pack(side="left")
        ttk.Button(bar, text="Untick everything", command=self.untick_everything).pack(side="left", padx=4)
        everything = HERE / EDITION["profile"] if EDITION else PROFILES / "everything.json"   # (an edition's own)
        if everything.exists():
            ttk.Button(bar, text="Start from everything", command=lambda: self.load(everything)).pack(side="left")
        self.others = widgets.status(ttk.Label(frame, text="", foreground=widgets.AMBER, padding=(2, 0)))
        self.others.pack(fill="x")
        ttk.Label(bar, text="Ticking a feature also ticks what it needs.").pack(side="left", padx=8)
        self.describe = tk.StringVar(value="Point at a feature to see what it does.")
        fit.label(frame, "", textvariable=self.describe, padding=6, relief="groove"
                  ).pack(side="bottom", fill="x", pady=4)
        box = Scrolled(frame)
        box.pack(fill="both", expand=True)
        self.features_scroll = box

        # every feature's tick, whichever tab shows it
        self.fvars, self.titles, self.what, self.feature_home = {}, {}, {}, {}
        for fid in self.reg:
            if fid in self.not_offered:
                continue
            t = TEXT.get(fid, {"title": fid, "text": self.reg[fid].get("doc", "")})
            self.fvars[fid], self.titles[fid], self.what[fid] = tk.BooleanVar(), t["title"], t["text"]
        self.features_inner = box.inner
        for fid in self.fvars:          # internal features (e.g. item-engine): ticked by what needs them, never shown
            if (self.reg[fid].get("hidden") or str(self.reg[fid].get("doc", "")).startswith("Internal")
                    or fid in TAB_OPTIONS or fid in AUTO_FOLLOWED):   # ticked by needs / requires, never shown
                self.feature_home[fid] = "internal"
        replays = [f for f in game_options.REPLAY_FEATURES if f in self.fvars]   # their ticks and boxes live in the
        for f in replays:                                                       # Game options window (one button:
            self.feature_home[f] = "features"                                   # the Features tab is full)
        lf = self.feature_group(box.inner, "Game options", FEATURE_HOMES["features"][1], "features", self.describe)
        if replays:
            if lf is None:
                lf = ttk.LabelFrame(box.inner, text="Game options", padding=6)
                lf.pack(fill="x", padx=4, pady=3)
            ttk.Button(lf, text="Replays, contact freeze, box score...", command=lambda: game_options.open_window(self)
                       ).pack(anchor="w", pady=(2, 0))
        self.feature_group(box.inner, "Testing", [f for f in self.fvars if GROUP_OF.get(f) == "testing"
                                                  and f not in FEATURE_HOMES["features"][1]], "features",
                           self.describe)

    def feature_check(self, parent, fid, home, describe):
        """A feature's checkbox (its one place in the window), with its extras (the menu color, the item odds)."""
        assert fid not in self.feature_home, f"{fid} is already on {self.feature_home[fid]}"
        self.feature_home[fid] = home
        title, what = self.titles[fid], self.what[fid]
        cb = ttk.Checkbutton(parent, text=title, variable=self.fvars[fid], command=lambda f=fid: self.toggled(f))
        cb.pack(anchor="w")
        cb.bind("<Enter>", lambda e: describe.set(f"{title}: {what}"))
        if fid == "menu-color":
            self.build_menu_color(parent)
        if fid == "item-odds":
            self.build_item_odds(parent)
        if fid == "match-seed":         # its seed box
            row = ttk.Frame(parent)
            row.pack(anchor="w", padx=24, pady=(0, 4))
            ttk.Label(row, text="Seed:").pack(side="left")
            ttk.Entry(row, textvariable=self.seed, width=14).pack(side="left", padx=4)
            ttk.Label(row, text="blank: a new game every match", foreground=widgets.GREY).pack(side="left", padx=4)
        if fid == "boot-captain-select":   # its stadium: the Game options window (game_options.py)
            ttk.Button(parent, text="Pick the stadium...", command=lambda: game_options.open_window(self)
                       ).pack(anchor="w", padx=24, pady=(0, 4))
        if fid == "boot-game":          # its captains and teams: the Game options window (game_options.py)
            ttk.Button(parent, text="Pick the teams...", command=lambda: game_options.open_window(self)
                       ).pack(anchor="w", padx=24, pady=(0, 4))

    def feature_group(self, parent, name, ids, home, describe):
        ids = [f for f in ids if f in self.fvars and f not in self.feature_home]
        if not ids:
            return None
        lf = ttk.LabelFrame(parent, text=name, padding=6)
        lf.pack(fill="x", padx=4, pady=3)
        order = {f: n for n, f in enumerate(ORDER)}
        for fid in sorted(ids, key=lambda f: order.get(f, 999)):
            self.feature_check(lf, fid, home, describe)
        return lf

    def feature_box(self, parent, home, title="Our extras"):
        """A tab's box of the switches for our versions of what it shows (FEATURE_HOMES[home]), collapsed to one line
        ("Our extras: 1 of 3 on"): a one-line checkbox each, its explanation in a tooltip; the same ticks as
        everywhere (fvars), so needs, prompts and profiles don't change. Returns the frame for the tab to pack or
        grid."""
        ids = [f for f in FEATURE_HOMES[home][1] if f in self.fvars and f not in self.feature_home]
        box = ttk.Frame(parent)
        if not ids:
            return box
        shown = tk.BooleanVar(value=False)
        head = ttk.Button(box)
        head.pack(anchor="w")
        body = ttk.Frame(box, padding=(12, 2, 0, 4))
        describe = tk.StringVar()           # (the Features tab's hover line; here each has a tooltip instead)
        order = {f: n for n, f in enumerate(ORDER)}
        for fid in sorted(ids, key=lambda f: order.get(f, 999)):
            self.feature_check(body, fid, FEATURE_HOMES[home][0], describe)
            widgets.tip(body.pack_slaves()[-1], self.what[fid])

        def count(*_):
            on = sum(self.fvars[f].get() for f in ids)
            head.configure(text=f"{title}: {on} of {len(ids)} on  ({'hide' if shown.get() else 'show'})")

        def toggle():
            shown.set(not shown.get())
            body.pack(fill="x") if shown.get() else body.pack_forget()
            count()
        head.configure(command=toggle)
        for f in ids:
            self.fvars[f].trace_add("write", count)
        count()
        box.body, box.toggle = body, toggle
        return box

    def header(self, parent, text, home, bold=True, grey=False):
        """A tab's first line with its "Our extras" box at the right end of the same row (so it costs no
        height while it's collapsed). Returns the row frame, to pack or grid."""
        row = ttk.Frame(parent)
        fit.label(row, text, bold=bold, grey=grey).grid(row=0, column=0, sticky="new")
        self.feature_box(row, home).grid(row=0, column=1, sticky="ne", padx=(8, 0))
        row.columnconfigure(0, weight=1)
        return row

    def place_the_rest(self):
        """Features no tab placed (a new registry entry, a tab that isn't there) stay reachable: on Features."""
        rest = [f for f in self.fvars if f not in self.feature_home]
        self.feature_group(self.features_inner, "More", rest, "features", self.describe)
        if self.odds and "koopaling-items" in self.fvars:     # the Koopalings' odds show with their feature
            self.fvars["koopaling-items"].trace_add("write", lambda *a: self.show_koopa_odds())

    def replay_problem(self):
        """What's wrong with a ticked replay tweak's boxes, or None."""
        return next((game_options.replay_value(f, self.replay)[1] for f in game_options.REPLAY_ROWS
                     if f in self.picked() and not game_options.replay_value(f, self.replay)[0]), None)

    def seed_value(self):
        """(True, match-seed's seed or None: blank) or (False, what's wrong)."""
        import match_seed
        try:
            return True, match_seed.parse(self.seed.get())
        except ValueError as e:
            return False, str(e)

    def build_menu_color(self, parent):
        row = ttk.Frame(parent)
        row.pack(anchor="w", padx=24, pady=(0, 4))
        self.color = tk.StringVar(value=self.menu_purple.DEFAULT)
        ttk.Label(row, text="Color:").pack(side="left")
        cb = ttk.Combobox(row, textvariable=self.color, values=list(self.menu_purple.PRESETS), width=12)
        cb.pack(side="left", padx=4)
        self.swatch = widgets.status(tk.Label(row, width=4, relief="sunken"))   # a colour, no words
        self.swatch.pack(side="left", padx=4)
        self.color_note = widgets.status(ttk.Label(row, text="", foreground=widgets.AMBER))
        self.color_note.pack(side="left", padx=4)
        ttk.Label(parent, text="Pick one from the list, or type a color like #2080C0.", foreground=widgets.GREY
                  ).pack(anchor="w", padx=24)
        self.color.trace_add("write", lambda *a: self.color_changed())
        self.color_changed(tick=False)

    def build_item_odds(self, parent):
        """A box per item the roulette rolls (batter_items.NAMES), showing the game's odds (git-a7's
        starbits_roulette.weight_table)."""
        import batter_items, ice_item, starbits_roulette
        table = starbits_roulette.weight_table(extra=[ice_item.EXTRA])
        n = len(table) // 3
        import koopa_items

        def boxes(frame, items):
            for k, (name, iid) in enumerate(items):
                default = "/".join(str(table[r * n + iid]) for r in range(3)) if iid < n else "0"   # never rolled
                v = tk.StringVar()
                self.odds[name] = v
                row, col = divmod(k, 2)
                ttk.Label(frame, text=ITEM_TITLES.get(name, name) + ":").grid(row=row, column=col * 3, sticky="w",
                                                                             padx=(0, 4))
                ttk.Entry(frame, textvariable=v, width=10).grid(row=row, column=col * 3 + 1)
                ttk.Label(frame, text=f"(game: {default})", foreground=widgets.GREY).grid(row=row, column=col * 3 + 2,
                                                                                   sticky="w", padx=(4, 16))
                v.trace_add("write", lambda *a, name=name: self.odds_changed(name))
        grid = ttk.Frame(parent)
        grid.pack(anchor="w", padx=24, pady=(0, 4))
        boxes(grid, sorted(batter_items.NAMES.items(), key=lambda e: e[1]))
        # the Koopalings' items (git-a7, a778dfd): in the roulette only with Koopaling items on
        self.koopa_odds = ttk.Frame(parent)
        ttk.Label(self.koopa_odds, wraplength=740, foreground=widgets.GREY, text="The Koopalings' items (with Koopaling "
                  "items on). In a game, Wendy's rings come up only while the POW is on in the item settings, "
                  "the others only while the Fireball is.").grid(row=0, column=0, columnspan=6, sticky="w")
        koopa = ttk.Frame(self.koopa_odds)
        koopa.grid(row=1, column=0, columnspan=6, sticky="w")
        boxes(koopa, sorted(((name, iid) for iid, name in koopa_items.NAMES.items()), key=lambda e: e[1]))
        self.odds_note = widgets.status(ttk.Label(parent, text="", foreground=widgets.RED))
        self.odds_note.pack(anchor="w", padx=24)
        ttk.Label(parent, wraplength=760, foreground=widgets.GREY, text="Higher comes up more often; 0 takes an item out "
                  "of the roulette. Leave a box empty to keep the game's odds. Three numbers like 20/15/15 set "
                  "separate odds by score difference, as the game does.").pack(anchor="w", padx=24)

    def show_koopa_odds(self):
        on = "koopaling-items" in self.fvars and self.fvars["koopaling-items"].get()
        if on and not self.koopa_odds.winfo_manager():
            self.koopa_odds.pack(anchor="w", padx=24, pady=(0, 4), before=self.odds_note)
        elif not on and self.koopa_odds.winfo_manager():
            self.koopa_odds.pack_forget()

    def odds_value(self, strict=True):
        """The "item-odds" option ({item: weight}) from the boxes. strict: raise ValueError on a bad box, else
        leave it out."""
        import starbits_roulette
        out = {}
        for name, v in self.odds.items():
            t = v.get().strip()
            if not t:
                continue
            parts = [x.strip() for x in t.replace(",", "/").split("/")]
            w = (int(parts[0]) if len(parts) == 1 else [int(x) for x in parts]) if all(
                x.isdigit() for x in parts) else None
            try:
                assert w is not None
                starbits_roulette.odds_ids({name: w})
            except AssertionError:
                if strict:
                    raise ValueError(f"{ITEM_TITLES.get(name, name)} odds: a number from 0 to 255, or three like "
                                     f"20/15/15")
                continue
            out[name] = w
        return out

    def odds_changed(self, name):
        try:
            self.odds_value()
            self.odds_note.configure(text="")
        except ValueError as e:
            self.odds_note.configure(text=str(e))
            return
        if self.odds[name].get().strip():
            self.tick(self.odds_features(), why="the item odds")

    def odds_features(self):
        """item-odds, and what the items given odds need (Star Bits: new-roulette-item; Ice: item-variants)."""
        items = self.odds_value(strict=False)
        return ({"item-odds"} if items else set()) | set().union(
            *(item_features(n) - {"fixed-items"} for n in items))

    def color_ok(self):
        """(ok, message) for the menu color."""
        try:
            top = self.menu_purple.colors(self.color.get())[1]
        except ValueError:
            return False, "Not a color: pick one from the list or type #RRGGBB."
        self.swatch.configure(bg="#%02x%02x%02x" % tuple(top))
        w = self.menu_purple.warning(self.color.get())
        return True, ("Very light: the white pattern and letters will be hard to see." if w else "")

    def color_changed(self, tick=True):
        ok, msg = self.color_ok()
        self.color_note.configure(text=msg, foreground=widgets.AMBER if ok else widgets.RED)
        default = self.menu_purple.colors(None)
        if (tick and ok and "menu-color" in self.fvars and not self.fvars["menu-color"].get()
                and self.menu_purple.colors(self.color.get()) != default):
            self.tick({"menu-color"})

    def recolor_needs(self):
        return set().union(*(self.closure(f) for f in RECOLOR_NEEDS))

    def closure(self, fid):
        out, todo = set(), [fid]
        while todo:
            g = todo.pop()
            if g not in out and g in self.reg:
                out.add(g)
                todo += self.reg[g]["requires"]
        return out

    def tick(self, features, why=None):
        """Tick features and what they need; says what it added."""
        add = sorted({g for f in features if f for g in self.closure(f)} - self.picked() - self.not_offered)
        for g in add:
            self.fvars[g].set(True)
        if add:
            self.status.set(("Also ticked" + (f" for {why}" if why else "") + ": ") +
                            ", ".join(self.titles[g] for g in add))
        return add

    def picked(self):
        return {f for f, v in self.fvars.items() if v.get()}

    def hard_needs(self, d, needs):
        """What a new character can't go in without: new-ids and its star moves' features, not the parts the build
        leaves out without their feature (its voice, ...: the pre-run prompt and Progress say those)."""
        return {"new-ids"} | (needs - set(self.char_parts.get(d["name"], {})))

    def needed_by(self, fid):
        """What that's ticked needs fid: feature titles, characters and stock character options."""
        out = [self.titles[f] for f in sorted(self.picked()) if f != fid and fid in self.closure(f)]
        for p, d, needs in self.new_chars:
            if self.cvars[p].get() and any(fid in self.closure(n) for n in self.hard_needs(d, needs)):
                out.append(d["name"])
        if any(self.rvars[p].get() for p, _ in self.recipes) and fid in self.recolor_needs():
            out.append("the recolors you picked")
        if "item-odds" in self.picked() and any(fid in self.closure(f) for f in self.odds_features()):
            out.append("the item odds")
        for name, key, value in self.char_settings():
            if any(fid in self.closure(f) for f in option_features(key, value)):
                out.append(f"{name}'s {key.replace('_', ' ')}")
        return out

    def toggled(self, fid):
        if fid in ONE_BOOT and self.fvars[fid].get():      # start at captain select, or in a game: one of them
            for g in ONE_BOOT - {fid}:
                if g in self.fvars:
                    self.fvars[g].set(False)
        if self.fvars[fid].get():
            self.tick({fid}, why=self.titles[fid])
            return
        users = self.needed_by(fid)
        if not users:
            return
        # unticking goes through, with what needs it (never a question: Nick, "IF I DO SOMETHING THEN IT SHOULD
        # WORK"); the status line says what went with it
        for f in self.picked():
            if fid in self.closure(f):
                self.fvars[f].set(False)
        for p, d, needs in self.new_chars:
            if any(fid in self.closure(n) for n in self.hard_needs(d, needs)):
                self.cvars[p].set(False)
        if fid in self.recolor_needs():
            for v in self.rvars.values():
                v.set(False)
        for name, v in self.odds.items():
            if v.get().strip() and any(fid in self.closure(f) for f in item_features(name) - {"fixed-items"}):
                v.set("")
        for name, key, value in self.char_settings():
            if any(fid in self.closure(f) for f in option_features(key, value)):
                self.set_setting([name], key, AS_IS)
        self.status.set(f"Also unticked with {self.titles[fid]}: " + ", ".join(users))

    def untick_everything(self):
        """Untick every feature; with characters, recolors or character settings picked on the other tabs, ask
        whether they go too (they need features of their own)."""
        others = self.other_picks()
        if others and messagebox.askyesno("Untick everything", f"Also untick {others} on the other tabs? (No "
                                          "unticks only the features here.)"):
            for v in list(self.cvars.values()) + list(self.rvars.values()):
                v.set(False)
            self.settings = {}
            for v in self.odds.values():
                v.set("")
            self.refresh_char_list()
        for v in self.fvars.values():
            v.set(False)
        self.show_others()

    def other_picks(self):
        """What's picked on the other tabs, in words ("" for nothing)."""
        n_new = sum(v.get() for v in self.cvars.values())
        n_rec = sum(v.get() for v in self.rvars.values())
        n_set = len({n for n, _, _ in self.char_settings()})
        parts = [f"{n} {w}{'s' if n != 1 else ''}" for n, w in ((n_new, "new character"), (n_rec, "recolor"),
                                                                    (n_set, "character with settings")) if n]
        return ", ".join(parts)

    def show_others(self):
        if hasattr(self, "others"):
            o = self.other_picks()
            self.others.configure(text=f"Also picked: {o} (New characters & recolors, and Characters tabs). "
                                       f"They need some features of their own." if o else "")

    def needs_with_why(self):
        """{feature: [(why, undo)]}: the features the picks on the other tabs need, each with the pick that needs
        it and how to untick that pick."""
        out = {}

        def add(features, why, undo):
            for f in features:
                for g in self.closure(f) - self.not_offered:
                    out.setdefault(g, []).append((why, undo))
        for p, d, needs in self.new_chars:
            if self.cvars[p].get():
                parts = self.char_parts.get(d["name"], {})
                add({"new-ids"} | (needs - set(parts)), f"{d['name']} is ticked on New characters & recolors",
                    lambda v=self.cvars[p]: v.set(False))
                for f, what in parts.items():      # the character still goes in without it (left out, said)
                    add({f}, f"{d['name']}'s {', '.join(what)}", lambda: None)
        for p, r in self.recipes:
            if self.rvars[p].get():
                add(RECOLOR_NEEDS, f"the recolor {r['name']} is ticked", lambda v=self.rvars[p]: v.set(False))
        for n, v in getattr(self, "ivars", {}).items():
            if v.get():
                add({"new-ids"}, f"the imported {n} is ticked", lambda v=v: v.set(False))
                for f, what in self.imported_parts(n).items():
                    add({f}, f"{n}'s {', '.join(what)}", lambda: None)
        for name, key, value in self.char_settings():
            label = next((o[0] for o in CHAR_OPTIONS if o[1] == key), key).lower()
            add(option_features(key, value), f"{name}'s {label} is set on the Characters tab",
                lambda n=name, k=key: self.set_setting([n], k, AS_IS))
        if self.captains_tab and self.captains_tab.current() is not None:
            add({"captains"}, "the Captains tab changes the captains", self.captains_tab.reset_all)
        if self.grid_tab.current() is not None:
            add({"new-ids"}, "the Select grid tab changes the order", self.grid_tab.reset)
        for part in getattr(self, "parts", []):   # pages in their own modules (Create, Stadiums): needs() ->
            for features, why, undo in getattr(part, "needs", lambda: [])():   # [(features, why, undo)]
                add(features, why, undo)
        if "item-odds" in self.picked():
            add(self.odds_features() - {"item-odds"}, "the item odds give odds to an item that needs it",
                lambda: [v.set("") for n, v in self.odds.items()
                         if item_features(n) - {"fixed-items"} - self.picked()])
        return out

    def missing_with_why(self):
        """The features the picks need that aren't ticked: [(feature, [(why, undo)])]."""
        picked = self.picked()
        return sorted(((f, whys) for f, whys in self.needs_with_why().items() if f not in picked),
                      key=lambda e: self.titles.get(e[0], e[0]))

    def tick_everything(self):
        self.tick({f for f in self.fvars if GROUP_OF.get(f) != "testing"})   # never the test switches (CPU vs CPU)

    # --- new characters and recolors

    def build_characters_tab(self):
        frame = ttk.Frame(self.tabs, padding=4)
        self.tabs.add(frame, text="New characters & recolors")
        top = ttk.Frame(frame)
        top.grid(row=0, column=0, columnspan=3, sticky="ew", pady=(0, 4))
        head = self.header(top, INTRO["new"], "new")
        head.pack(fill="x")
        line = credit_line(top, "New characters & recolors")
        if line is not None:
            line.pack(fill="x")
        self.new_howto = widgets.HowTo(head, HOW_TO_NEW, share=HOW_TO_NEW_SHARE, refused=HOW_TO_NEW_REFUSED,
                                       key="new characters", body_in=top)
        self.new_howto.grid(row=1, column=0, sticky="w")
        self.cvars, self.rvars, self.recolor_rows = {}, {}, {}
        for col, (title, items, store, label) in enumerate([
                ("New characters", self.new_chars, self.cvars, lambda it: f"{it[1]['name']}"),
                ("Recolors of stock characters", self.recipes, self.rvars,
                 lambda it: f"{it[1]['name']}" + (f"  (from {it[1]['base']})" if it[1].get("base") else ""))]):
            side = ttk.LabelFrame(frame, text=title, padding=4)
            side.grid(row=1, column=col, sticky="nsew", padx=4)
            bar = ttk.Frame(side)
            bar.pack(fill="x")
            box = Scrolled(side)
            if col == 1:
                self.recolor_box, self.recolor_label = box.inner, label
            else:
                self.character_box, self.character_label = box.inner, label
            for it in items:
                self.add_list_row(box.inner, it, store, label, recolor=col == 1)
            ttk.Button(bar, text="All", command=lambda s=store, rc=col == 1: self.set_all(s, True, rc)).pack(side="left")
            ttk.Button(bar, text="None", command=lambda s=store: [v.set(False) for v in s.values()]
                       ).pack(side="left", padx=4)
            if col == 1:                # (no New character: a recolor or a Sluggies model, Nick)
                ttk.Button(bar, text="New recolor...", command=lambda: character_window.new_recolor(self)
                           ).pack(side="right")
            box.pack(fill="both", expand=True)
        self.build_imported(frame)
        frame.columnconfigure(0, weight=1)
        frame.columnconfigure(1, weight=1)
        frame.columnconfigure(2, weight=1)
        frame.rowconfigure(1, weight=1)

    # --- imported characters (git-a3's character packs, scripts/charpack.py; patch.py's "imported")

    def build_imported(self, frame):
        side = ttk.LabelFrame(frame, text="Imported characters", padding=4)
        side.grid(row=1, column=2, sticky="nsew", padx=4)
        bar = ttk.Frame(side)
        bar.pack(fill="x")
        ttk.Button(bar, text=character_window.IMPORT_BUTTON.replace(" (", "\n("), command=self.import_dialog
                   ).pack(side="left")          # every kind (import_file), its text on two lines: a narrow column
        bar2 = ttk.Frame(side)
        bar2.pack(fill="x", pady=(2, 0))
        ttk.Button(bar2, text="Open folder", command=self.open_imported_folder).pack(side="left", padx=(0, 4))
        self.import_howto = widgets.HowTo(bar2, HOW_TO_IMPORT, share=HOW_TO_IMPORT_SHARE, refused=HOW_TO_IMPORT_REFUSED,
                                          key="import character", body_in=side)
        self.import_howto.pack(side="left")
        self.ivars = {}                 # {imported character's name: ticked}
        try:                            # a narrow column: a fixed wrap, not the tab's width
            import credits
            text = credits.tab_line("Import character")
        except (ImportError, OSError):
            text = None
        if text:
            ttk.Label(side, text=text, foreground=widgets.GREY, wraplength=240,
                      justify="left").pack(fill="x", pady=(2, 0))
        box = Scrolled(side)
        box.canvas.configure(height=110)          # asks for less (two rows of buttons above): it scrolls, gets the room
        box.pack(fill="both", expand=True)
        self.imported_box = box.inner
        self.import_howto.before = box          # its steps open above the list
        self.imported_note = widgets.status(ttk.Label(side, text="", foreground=widgets.GREY, wraplength=260))
        self.imported_note.pack(anchor="w")
        self.refresh_imported()

    def imported(self):
        """charpack.list_imported of the patcher's import folder (never creating it just to look)."""
        import charpack
        return charpack.list_imported(patch.IMPORTED_DEST) if patch.IMPORTED_DEST else charpack.list_imported_quiet()

    def imported_parts(self, name):
        """{feature: [what]} an imported character loses without the feature (leftout.character_needs)."""
        cache = self.__dict__.setdefault("_imported_parts", {})
        if name not in cache:
            c = next((c for c in self.imported() if c["name"] == name), None)
            try:
                d = json.loads(Path(c["definition"]).read_text(encoding="utf8")) if c else None
            except (OSError, ValueError, KeyError):
                d = None
            cache[name] = leftout.character_needs([d], set(self.reg)).get(d["name"], {}) if d else {}
        return cache[name]

    def refresh_imported(self, tick=()):
        was = {n for n, v in self.ivars.items() if v.get()} | set(tick)
        for w in self.imported_box.winfo_children():
            w.destroy()
        self.ivars = {}
        have = self.imported()
        for c in have:
            v = tk.BooleanVar(value=c["name"] in was)
            v.trace_add("write", lambda *a: self.refresh_soon())
            self.ivars[c["name"]] = v
            row = ttk.Frame(self.imported_box)
            row.pack(fill="x")
            ttk.Checkbutton(row, text=c["name"] + (f"  (by {c['author']})" if c.get("author") else ""), variable=v,
                            command=lambda v=v, n=c["name"]: v.get() and self.tick(
                                {"new-ids"} | set(self.imported_parts(n)), why=n)
                            ).pack(side="left")
            ttk.Button(row, text="Remove", width=8, command=lambda c=c: self.remove_imported(c)).pack(side="right",
                                                                                                   padx=(0, 4))
        self.imported_note.configure(text="" if have else "Characters other players share come as .slgmodel files: "
                                     "Import character adds one here.")
        self.refresh_soon()

    def taken(self):
        """The ids and names this patcher's own characters and recolors use (an import avoids them)."""
        ids = {int(str(d["id"]), 0) for _, d, _ in self.new_chars} | {int(str(r["id"]), 0) for _, r in self.recipes
                                                                       if "id" in r}
        names = [d["name"] for _, d, _ in self.new_chars] + [r["name"] for _, r in self.recipes]
        return ids, names

    def import_dialog(self, pick=None):
        """Import character (.sluggie, .slgmodel, .glb, model file, or folder): every kind of character file, one button
        (Nick: "just two buttons", New recolor and this), by type (import_file). A file or a whole folder (git-0a for
        Nick: "just import the character folder and it imports everything"): tk can't pick both in one dialog, so a
        small menu first, "A file..." / "A folder..." (pick= "file" / "folder" skips it). Nick: only .slgmodel is
        shared now; an older .slgchar still imports (import_file), unmentioned."""
        if pick is None:
            menu = tk.Menu(self.root, tearoff=False)
            menu.add_command(label="A file...", command=lambda: self.import_dialog("file"))
            menu.add_command(label="A folder...", command=lambda: self.import_dialog("folder"))
            x, y = self.root.winfo_pointerxy()
            try:
                menu.tk_popup(x, y)
            finally:
                menu.grab_release()
            return
        if pick == "folder":
            path = filedialog.askdirectory(title="Import a character folder", mustexist=True)
        else:
            path = filedialog.askopenfilename(title="Import a character", filetypes=[
                ("All character files", "*.sluggie *.slgmodel *.glb *.png *.bin *.gpl"),
                ("Character file (model, portraits, voice)", "*.slgmodel"), ("Model edited with Sluggies", "*.sluggie"),
                ("Model edited in Blender (.glb)", "*.glb"),
                ("Texture pack picture (Dolphin's tex1_...png)", "*.png"),
                ("Model file from a game (e.g. a mod's)", "*.bin *.gpl"), ("All files", "*.*")])
        if path:
            self.import_file(path)

    def already_imported(self, path):
        """The imported characters made from this very file (the sha1 their definition keeps: "_pack", "_sluggie",
        "_model"): Nick had five Lumas from importing the same pack again (git-a3 / git-92)."""
        import charpack
        try:
            h = charpack.sha1(Path(path).read_bytes())
        except OSError:
            return []
        out = []
        for c in self.imported():
            try:
                d = json.loads(Path(c["definition"]).read_text(encoding="utf8"))
            except (OSError, ValueError):
                continue
            if any((d.get(k) or {}).get("sha1") == h for k in ("_pack", "_sluggie", "_model")):
                out.append(c)
        return out

    def import_file(self, path, again=None):
        """By type: a folder (anything char_import finds in it): character_window.import_model, no questions; a
        .sluggie or a texture pack's PNG: character_window.add_sluggie; a character pack (.slgchar): import_pack; a
        character file (.slgmodel) or a model file: character_window.import_model. Each takes the portraits and
        voice beside the file too (char_import). All
        through the same loading window (busy_work). The same file imported before: "Replace it or add another?"
        (again: "replace" / "add" answers it without asking); Replace removes the old one first, so the new one
        takes its id."""
        import charpack
        self._replacing = None                  # {"name", "id"} of the one a Replace takes the place of
        same = self.already_imported(path) if Path(path).is_file() else []
        if same:
            # Re-importing a character that is merely archived/off restores it instead of creating "Name (2)".
            archived = [c for c in same if c["name"] in self.ivars and not self.ivars[c["name"]].get()]
            if archived and len(archived) == len(same):
                c = archived[0]
                self.ivars[c["name"]].set(True)
                self.tick({"new-ids"} | set(self.imported_parts(c["name"])), why=c["name"])
                g = getattr(self, "grid_tab", None)
                if g is not None:
                    g.fit_to_roster()
                    g.redraw()
                self.status.set(f"Restored {c['name']} from the archive; no duplicate was created.")
                self.refresh_soon()
                return character_window.open_character(self, c["name"])
            names = ", ".join(c["name"] for c in same)
            if again is None:
                answer = messagebox.askyesnocancel(
                    "Import character", f"{names} {'is' if len(same) == 1 else 'are'} already imported from "
                    f"{Path(path).name}.\n\nYes: replace {'it' if len(same) == 1 else 'them'} with this file.\n"
                    f"No: add another one.\nCancel: import nothing.")
                again = None if answer is None else "replace" if answer else "add"
            if again is None:
                return None
            if again == "replace":
                self._replacing = {"name": same[0]["name"], "id": same[0]["id"]}
                for c in same:
                    charpack.remove(c["id"], patch.IMPORTED_DEST)
                self.refresh_imported()
        suffix = Path(path).suffix.lower()
        if Path(path).is_dir():                 # a whole folder: model, portraits, voice and name, no questions
            return character_window.import_model(self, path, confirm=False)
        if suffix == ".slgchar":
            return self.import_pack(path)
        if suffix == ".sluggie" or suffix == ".png":
            return character_window.add_sluggie(self, path)
        return character_window.import_model(self, path)

    def import_pack(self, path, confirm=True):
        """Check the pack against the player's game, show what it is, and import it (in a worker: it rebuilds the
        pack's models from the game to check them)."""
        import charpack

        def with_game(folder):
            self.status.set(f"Checking {Path(path).name} against your game ...")
            character_window.busy_work(       # (Nick: a loading window, as Add a model from Sluggies has)
                self, "Import character", f"Checking {Path(path).name} against your game...",
                lambda: charpack.check(path, folder, dest=patch.IMPORTED_DEST), lambda r: checked(r, folder),
                error=lambda e: {"ok": False, "error": f"{type(e).__name__}: {e}"}, keep=False)

        def checked(r, folder):
            self.status.set("")
            if not r.get("ok"):
                messagebox.showwarning("Import character", f"{Path(path).name} can't be imported: {r.get('error')}")
                return
            about = (f"{r.get('name')}" + (f" by {r['author']}" if r.get("author") else "") +
                     (f", built on {r['template']}" if r.get("template") else "") + "." +
                     (f"\n\n{r['notes']}" if r.get("notes") else "") +
                     ("\n\nNote: " + "\nNote: ".join(r["warnings"]) if r.get("warnings") else ""))
            if confirm and not messagebox.askyesno("Import character", about + "\n\nImport it?"):
                return
            ids, names = self.taken()
            self.status.set(f"Importing {r.get('name')} ...")
            character_window.busy_work(       # in a worker: it rebuilds the pack's models from the game
                self, "Import character", f"Importing {r.get('name')}...",
                lambda: charpack.import_pack(path, folder, dest=patch.IMPORTED_DEST, taken_ids=ids, taken_names=names,
                                             name=(getattr(self, "_replacing", None) or {}).get("name"),
                                             cid=(getattr(self, "_replacing", None) or {}).get("id")),
                imported)                       # (Replace: the old name and id, git-a3's charpack overrides)

        def imported(done):
            self.status.set("")
            if isinstance(done, Exception):
                messagebox.showwarning("Import character", str(done) if isinstance(done, charpack.PackError) else
                                       f"{Path(path).name} can't be imported: {type(done).__name__}: {done}")
                return
            self.refresh_imported(tick=[done["name"]])
            self.tick({"new-ids"}, why=done["name"])
            self.status.set(f"Imported {done['name']} and ticked it." + (" " + " ".join(
                w[:1].upper() + w[1:] + "." for w in done["warnings"]) if done["warnings"] else ""))
            self.last_import = done
            character_window.refresh(self)
            self.root.update_idletasks()
            character_window.open_character(self, done["name"])   # its window next, as a Sluggies model's
        return self.with_game_folder(with_game)

    def remove_imported(self, c):
        import charpack
        if not messagebox.askyesno("Remove", f"Remove the imported character {c['name']}? You can import its pack "
                                             f"again later."):
            return
        charpack.remove(c["id"], patch.IMPORTED_DEST)
        self.settings.pop(c["name"], None)
        self.refresh_imported()

    def open_imported_folder(self):
        import charpack, os
        folder = Path(patch.IMPORTED_DEST) if patch.IMPORTED_DEST else charpack.default_dest()
        folder.mkdir(parents=True, exist_ok=True)
        os.startfile(folder)

    def add_list_row(self, parent, it, store, label, recolor):
        """A ticked-or-not row for a new character or recolor (a recolor also gets Edit)."""
        v = store.get(it[0]) or tk.BooleanVar()
        v.trace_add("write", lambda *a: self.refresh_soon())
        store[it[0]] = v
        row = ttk.Frame(parent)
        row.pack(fill="x")
        cb = ttk.Checkbutton(row, text=label(it), variable=v,
                             command=lambda it=it, v=v: self.character_toggled(it, v, recolor))
        cb.pack(side="left", anchor="w")
        character_window.bind_row(self, cb, it[0], recolor)     # right-click: Open... / Delete...
        if recolor:
            ttk.Button(row, text="Edit", width=5, command=lambda p=it[0]: self.edit_recolor(p)
                       ).pack(side="right", padx=(0, 4))
            self.recolor_rows[it[0]] = (row, cb)

    # --- the character window (character_window.py): one editor for stats, chemistry, names and the model

    def edit_characters(self, names):
        """The Characters tab's "Edit stats, chemistry and names...": the window on the one picked character."""
        if len(names) != 1:
            messagebox.showinfo("Edit a character", "Pick one character on the left, then Edit stats, chemistry and "
                                                    "names.")
            return None
        return character_window.open_character(self, names[0])

    def edit_recolor(self, path):
        """A recolor row's Edit: its window (by the recipe's name as it is now: an edit can rename it)."""
        recipe = next((r for p, r in self.recipes if p == path), None)
        return character_window.open_character(self, recipe["name"]) if recipe else None

    # --- the recolor editor (recolor_editor.py, on git-d9's recolor.py editor API)

    def with_game_folder(self, then, quiet=False, what=None):
        """Call then(folder) with the player's game as a readable folder: a folder at once; an ISO through
        patch.game_folder (git-dc: extracted once into the patcher's cache, the same one Check and Patch use), in a
        worker thread. quiet: no message when there's no game yet (the Captains tab's figures just wait). what: what
        the page reads from the game, one sentence, for the "choose your game" dialog (Nick: say what's opening);
        choosing a game there goes on to open it."""
        g = self.game_path()
        if g is None or not g.exists():
            if not quiet:
                before = self.game.get()
                if widgets.ask_for_game(self.root, what or "This reads your game.",
                                        [("Choose ISO file...", self.pick_iso_in),
                                         ("Choose folder...", self.pick_folder_in)]) and self.game.get() != before:
                    return self.with_game_folder(then, quiet, what)
            return None
        cached = getattr(self, "_game_folder", None)
        if cached and cached[0] == g:
            return then(cached[1])
        if (g / "sys/main.dol").exists():
            self._game_folder = (g, g)
            return then(g)
        reads = self.__dict__.setdefault("_game_reads", {})    # one read of an ISO at a time: later callers wait on it
        if g in reads:
            reads[g].append((then, quiet))
            return None
        reads[g] = [(then, quiet)]
        self.status.set("Reading your game from the ISO (only the first time; this takes a minute) ...")
        self.root.configure(cursor="watch")

        def work():
            try:
                folder = Path(patch.game_folder(g))
                self.q.put(("call", lambda: opened(folder)))
            except SystemExit as e:         # (the message now: e is gone when the queue runs the call, git-10)
                self.q.put(("call", lambda msg=str(e.code): failed(msg)))
            except Exception as e:
                self.q.put(("call", lambda msg=f"{type(e).__name__}: {e}": failed(msg)))

        def opened(folder):
            self.root.configure(cursor="")
            self.status.set("")
            self._game_folder = (g, folder)
            for fn, _ in reads.pop(g, []):
                fn(folder)

        def failed(msg):
            self.root.configure(cursor="")
            waiting = reads.pop(g, [])
            # said on the status line even for a quiet caller (the grid): never an empty grid with no reason
            self.status.set(f"Couldn't read your game: {msg}")
            if not all(q for _, q in waiting):
                messagebox.showwarning("Your game", f"Couldn't read your game: {msg}")

        threading.Thread(target=work, daemon=True).start()
        return None

    def game_path(self):
        """The "Your game" entry as a Path (None if empty); a relative one (e.g. isos/original-RMBE01.iso) from the
        patcher's folder when it isn't found from where the window was started."""
        s = self.game.get().strip().strip('"')
        if not s:
            return None
        p = Path(s)
        return ROOT / p if not p.is_absolute() and not p.exists() and (ROOT / p).exists() else p

    def recolor_game(self, then, what=None):
        """Call then(recolor.Game) on the player's game (with_game_folder; what: what the page reads)."""
        import recolor

        def got(folder):
            cached = getattr(self, "_recolor_game", None)
            if not (cached and cached[0] == folder):
                self._recolor_game = (folder, recolor.Game(str(folder)))
            return then(self._recolor_game[1])
        return self.with_game_folder(got, what=what)

    def open_recolor_editor(self, path=None, win=None):
        """The editor on the player's game: returned at once for a game folder; for an ISO it opens once the game is
        read (self.last_editor)."""
        import recolor_editor

        def show(game):
            w = win or tk.Toplevel(self.root)
            w.transient(self.root)
            self.last_editor = recolor_editor.open_window(w, game, RECOLORS, path=path, on_save=self.recipe_saved,
                                                          id_folders=[ROOT / "characters", ROOT / "recolors"])
            return self.last_editor
        return self.recolor_game(show, what="The recolor editor starts from each character's own textures in your "
                                            "game.")

    def recipe_saved(self, path):
        """A recipe the editor wrote: listed (or its row updated) and ticked."""
        path = Path(path)
        recipe = json.loads(path.read_text(encoding="utf8"))
        known = [p for p, _ in self.recipes]
        if path in known:
            self.recipes[known.index(path)] = (path, recipe)
            self.recolor_rows[path][1].configure(text=self.recolor_label((path, recipe)))
        else:
            self.recipes.append((path, recipe))
            self.add_list_row(self.recolor_box, (path, recipe), self.rvars, self.recolor_label, recolor=True)
        self.rvars[path].set(True)
        self.tick(RECOLOR_NEEDS, why=recipe["name"])
        self.status.set(f"Saved the recolor {recipe['name']} ({path.name}) and ticked it.")

    def tab_changed(self):
        """The Captains tab reads the stock captains' figures from the player's game when it's first shown."""
        if (self.captains_tab and self.tabs.select() == str(self.captains_tab.frame)
                and self.captains_tab.game_folder is None):
            self.captains_tab.load_game_figures()
        if self.tabs.select() == str(self.grid_tab.frame) and self.grid_tab.game is None:
            self.grid_tab.load_game()

    def refresh_soon(self):
        """Refresh the Characters tab's list once, after a batch of ticks."""
        if not getattr(self, "_refresh_queued", False):
            self._refresh_queued = True
            self.root.after_idle(self._refresh_now)

    def _refresh_now(self):
        self._refresh_queued = False
        self.refresh_char_list()
        if getattr(self, "captains_tab", None):
            self.captains_tab.redraw()      # new characters ticked or not: who can be a captain
        if hasattr(self, "grid_tab"):
            self.grid_tab.redraw()          # and who is on the grid
        self.show_others()

    def character_toggled(self, it, v, recolor):
        if v.get():
            self.tick(RECOLOR_NEEDS if recolor else {"new-ids"} | it[2], why=it[1]["name"])

    def set_all(self, store, on, recolor):
        for v in store.values():
            v.set(on)
        if on and store:
            self.tick(RECOLOR_NEEDS if recolor else {"new-ids"}.union(*(n for _, _, n in self.new_chars)))

    # --- per-character settings, on any character

    def build_settings_tab(self):
        """Characters: every stock character, and the new characters and recolors that are ticked. Select one or
        more and set any character setting on them; a new character's own settings show as they are."""
        import abilities
        frame = ttk.Frame(self.tabs, padding=6)
        self.tabs.add(frame, text="Characters")
        self.header(frame, INTRO["characters"], "characters").pack(fill="x", pady=(0, 4))
        line = credit_line(frame, "Characters")
        if line is not None:
            line.pack(fill="x")
        self.settings = {}              # {character name: {profile key: value}}
        fit.label(frame, "Pick one or more characters (Ctrl or Shift to pick several), then "
                  "change their settings on the right. \"As it is\" keeps what the character already has."
                  ).pack(fill="x")
        if "stock" not in self.supports:
            fit.label(frame, foreground=widgets.AMBER, text="Settings on stock characters aren't in the "
                      "patcher yet: you can save them with your choices, but patching with them stops with a message "
                      "until it lands.").pack(fill="x", pady=2)
        body = ttk.Frame(frame)
        body.pack(fill="both", expand=True, pady=4)
        left = ttk.Frame(body)
        left.pack(side="left", fill="y")
        self.char_filter = tk.StringVar()
        ttk.Entry(left, textvariable=self.char_filter).pack(fill="x")
        self.char_filter.trace_add("write", lambda *a: self.refresh_char_list())
        lb_frame = ttk.Frame(left)
        lb_frame.pack(fill="y", expand=True, pady=4)
        self.char_list = tk.Listbox(lb_frame, selectmode="extended", width=32, exportselection=False)
        bar = ttk.Scrollbar(lb_frame, orient="vertical", command=self.char_list.yview)
        self.char_list.configure(yscrollcommand=bar.set)
        self.char_list.pack(side="left", fill="y", expand=True)
        bar.pack(side="left", fill="y")
        self.char_list.bind("<<ListboxSelect>>", lambda e: self.show_settings())
        ttk.Label(left, text="* has settings changed here", foreground=widgets.GREY).pack(anchor="w")

        scroll = Scrolled(body)         # the settings scroll when the window is short
        scroll.pack(side="left", fill="both", expand=True, padx=(12, 0))
        right = scroll.inner
        self.picked_label = ttk.Label(right, text="Pick a character on the left.", font="SluggersSection")
        self.picked_label.grid(row=0, column=0, columnspan=3, sticky="w", pady=(0, 8))
        self.choice_lists = LazyLists({
            "bool": {"On": True, "Off": False},
            "pitches": {"None (0)": 0, **{f"{n} ({i})": i for i, n in STAR_PITCHES.items()}},
            "fielding": {f"{n} ({i})": i for i, n in enumerate(list(abilities.NAMES) + [
                abilities.NEW[k] for k in sorted(abilities.NEW)])},
            "label": {"None": None, **{n: n for n in self.known_labels()}}},
            items=lambda: dict(self.items), swings=lambda: {"None (0)": 0, **self.swings})
        self.setting_vars, self.now_labels = {}, {}
        widgets.InfoPanel(frame)            # where an "i" shows what a setting changes in the game's data
        data = data_fields()
        shown = not (EDITION and EDITION.get("hide_character_settings"))   # (an edition without their features)
        for row, (label, key, kind) in enumerate(CHAR_OPTIONS, start=1):
            if shown:
                widgets.tip(ttk.Label(right, text=label + ":"), OPTION_TIPS.get(key)).grid(row=row, column=0, sticky="w",
                                                                                        pady=2)
            v = tk.StringVar(value=AS_IS)
            cb = ttk.Combobox(right, textvariable=v, width=26, state="disabled")
            self.set_values(cb, kind)
            if shown:
                cb.grid(row=row, column=1, sticky="w", padx=6)
            cb.bind("<<ComboboxSelected>>", lambda e, key=key: self.setting_picked(key))
            if kind == "label":         # typed: a label of the player's own
                cb.bind("<Return>", lambda e, key=key: self.setting_picked(key))
                cb.bind("<FocusOut>", lambda e, key=key: self.setting_picked(key, typed=True))
            now = widgets.status(ttk.Label(right, text="", foreground=widgets.GREY))   # "has: ..." when it has one
            icon = widgets.info(right, label, data.get(f"characters.{key}"))
            if icon is not None:
                icon.grid(row=row, column=3, sticky="w", padx=(4, 0))
            if shown:
                now.grid(row=row, column=2, sticky="w")
            self.setting_vars[key], self.now_labels[key] = (v, cb), now
        if shown:
            ttk.Button(right, text="Reset the picked characters to as they are",
                       command=self.reset_settings).grid(row=len(CHAR_OPTIONS) + 1, column=0, columnspan=2,
                                                         sticky="w", pady=10)
        if char_editor:
            ttk.Button(right, text="Edit stats, chemistry and names...",
                       command=lambda: self.edit_characters(self.selected_chars())
                       ).grid(row=len(CHAR_OPTIONS) + 2, column=0, columnspan=2, sticky="w")
        self.list_names = []
        self.refresh_char_list()

    def known_labels(self):
        """Card labels already in use (new characters' definitions, the stock ones): suggestions."""
        import item_abilities
        out = {d[k] for _, d, _ in self.new_chars for k in LABEL_KEYS if isinstance(d.get(k), str)}
        return sorted(out | {label for _, _, label in item_abilities.STOCK.values()})

    def roster(self):
        """[(name, kind, definition or recipe or None, id)]: stock characters, then the ticked new characters and
        recolors."""
        out = [(n, "stock", None, i) for i, n in self.stock]
        out += [(d["name"], "new", d, int(str(d["id"]), 0)) for p, d, _ in self.new_chars if self.cvars[p].get()]
        out += [(r["name"], "recolor", r, int(str(r["id"]), 0) if "id" in r else None)
                for p, r in self.recipes if self.rvars[p].get()]
        if getattr(self, "ivars", None):
            out += [(c["name"], "imported", imported_definition(c), c["id"])
                    for c in self.imported() if self.ivars.get(c["name"]) and self.ivars[c["name"]].get()]
        return out

    def refresh_char_list(self):
        if not hasattr(self, "char_list"):
            return
        keep = set(self.selected_chars())
        f = self.char_filter.get().strip().lower()
        self.list_names = []
        self.char_list.delete(0, "end")
        for name, kind, _, _ in self.roster():
            if f and f not in name.lower():
                continue
            mark = " *" if self.settings.get(name) else ""
            tag = {"new": "  (new)", "recolor": "  (recolor)", "imported": "  (imported)"}.get(kind, "")
            self.char_list.insert("end", name + tag + mark)
            self.list_names.append(name)
            if name in keep:
                self.char_list.selection_set("end")
        self.show_settings()

    def selected_chars(self):
        return [self.list_names[i] for i in self.char_list.curselection()] if hasattr(self, "char_list") else []

    def select_chars(self, names):
        self.char_list.selection_clear(0, "end")
        for i, n in enumerate(self.list_names):
            if n in names:
                self.char_list.selection_set(i)
        self.show_settings()

    def builtin(self, name, key):
        """(value, where from) a character has without any setting here, or (None, None)."""
        entry = next((e for e in self.roster() if e[0] == name), None)
        if entry is None:
            return None, None
        _, kind, d, cid = entry
        if kind in ("new", "imported"):
            if key in ("star pitch", "fielding ability"):
                if key in d.get("stats", {}):
                    return d["stats"][key], "its definition"
            elif key in d:
                return d[key], "its definition"
        if key == "star swing":
            if EDITION and "custom-swings" not in EDITION.get("features", ()):
                return None, None       # (the build gives them the template's: 4bb2c7f; no custom_swings import)
            import custom_swings        # (each only for its own key: the lean beta, git-92)
            sid = next((s for s, ids in custom_swings.DEFAULT_CHARS.items() if cid in ids), None)
            return (sid, "the game's defaults") if sid else (None, None)
        if kind == "stock":
            import charbuild            # the patcher's own defaults for stock characters (King Boo's pitch 16,
            d = next((e for e in getattr(charbuild, "STOCK_DEFAULTS", ()) if e.get("id") == cid), {})   # the Kongs'
            if key in d:                # Clamber Jump, ...)
                return d[key], "the patcher's defaults"
            if key == "batting_item":
                import batter_items, koopa_items
                fixed = {**batter_items.FIXED_ITEM, **koopa_items.STOCK_FIXED}
                names = {i: n for n, i in batter_items.NAMES.items()} | dict(koopa_items.NAMES)
                return (names.get(fixed[cid], fixed[cid]), "the game's defaults") if cid in fixed else (None, None)
            if key == "always_item":
                import batter_items
                return (True, "the game's defaults") if cid in batter_items.ALWAYS_ITEM else (None, None)
            if key == "batter_star":
                import batter_star
                return (True, "the game's defaults") if cid in batter_star.STAR_CHARS else (None, None)
            if key in ("item_ability", "special_ability"):
                import item_abilities
                _, kind_, label = item_abilities.STOCK.get(cid, (None, None, None))
                return (label, "the game's defaults") if kind_ == key.split("_")[0] else (None, None)
        return None, None

    def value_label(self, kind, value):
        if kind == "label":
            return "None" if value is None else str(value)
        return next((label for label, v in self.choice_lists[kind].items() if v == value and type(v) is type(value)),
                    str(value))

    def refresh_choices(self):
        """The Batting item, Star swing and Star pitch lists as the character editor has them (char_editor's
        item_choices / swing_choices / pitch_choices: ours, the stock ones and the player's saved creations on Create,
        "(yours)"), so the two can't differ; a pick of the player's is used on Create (use_creation)."""
        self.choice_paths = getattr(self, "choice_paths", {})
        if char_editor is None:
            return
        for kind, fn in (("items", char_editor.item_choices), ("swings", char_editor.swing_choices),
                         ("pitches", char_editor.pitch_choices)):
            try:
                rows = fn(self)
            except Exception:           # the editor's lists are a help; the tab's own stay
                continue
            self.choice_lists[kind] = {label: value for label, value, _ in rows}
            self.choice_paths.update({(kind, label): path for label, _, path in rows if path is not None})
        for label, key, kind in CHAR_OPTIONS:
            if kind in ("items", "swings", "pitches"):
                self.set_values(self.setting_vars[key][1], kind)

    def set_values(self, cb, kind):
        """A setting's list: now, or (a list not made yet: items, swings) when it's opened."""
        if self.choice_lists.ready(kind):
            cb.configure(values=[AS_IS] + list(self.choice_lists[kind]))
        else:
            cb.configure(values=[AS_IS], postcommand=lambda: cb.configure(values=[AS_IS] + list(self.choice_lists[kind])))

    def use_creation(self, key, path):
        """The player's swing / pitch / item picked here goes in the game: its Create page's Use in my game, through
        the page's own checks. True when it's used (as the character editor does)."""
        page = char_editor.create_page(self, {"star swing": "swings", "star pitch": "pitches",
                                              "batting_item": "items"}[key]) if char_editor else None
        if page is None:
            return False
        import creation_editor as ce
        if ce.rel(path) in page.used:
            return True
        page.list.refresh(select=path)
        page.use_var.set(True)
        page.use_toggled()
        return ce.rel(path) in page.used

    def show_settings(self):
        names = self.selected_chars()
        hidden = EDITION and EDITION.get("hide_character_settings")   # (their lists are never seen: not made)
        if not hidden and not getattr(self, "_choices_fresh", False):
            self._choices_fresh = True          # (once per showing: the lists read the Create pages' files)
            self.refresh_choices()
            self.after_refresh = self.root.after_idle(lambda: setattr(self, "_choices_fresh", False))
        self.picked_label.configure(text=(names[0] if len(names) == 1 else f"{len(names)} characters: " +
                                          ", ".join(names[:4]) + (" ..." if len(names) > 4 else ""))
                                    if names else "Pick a character on the left.")
        for label, key, kind in CHAR_OPTIONS:
            v, cb = self.setting_vars[key]
            cb.configure(state=("normal" if kind == "label" else "readonly") if names else "disabled")
            vals = {repr(self.settings.get(n, {}).get(key, AS_IS)) for n in names}
            cur = self.settings.get(names[0], {}).get(key, AS_IS) if names else AS_IS
            v.set("(several)" if len(vals) > 1 else AS_IS if cur == AS_IS else self.value_label(kind, cur))
            now = ""
            if len(names) == 1:
                b, where = self.builtin(names[0], key)
                if b not in (None, False, 0):
                    now = f"has: {self.value_label(kind, b)} ({where})"
            self.now_labels[key].configure(text=now)

    def setting_picked(self, key, typed=False):
        kind = next(o[2] for o in CHAR_OPTIONS if o[1] == key)
        label = self.setting_vars[key][0].get().strip()
        names = self.selected_chars()
        if label == "(several)" or not names:
            return
        if kind != "label":
            path = getattr(self, "choice_paths", {}).get((kind, label))
            if path is not None and not self.use_creation(key, path):
                self.show_settings()            # Create said why (its own message); the setting stays as it was
                return
            self.set_setting(names, key, AS_IS if label == AS_IS else self.choice_lists[kind][label])
            return
        value = AS_IS if label in ("", AS_IS) else None if label == "None" else label
        current = {repr(self.settings.get(n, {}).get(key, AS_IS)) for n in names}
        if typed and current == {repr(value)}:
            return                      # focus left without a change
        if isinstance(value, str) and value != AS_IS:
            import abilities
            try:
                abilities.text_alpha(value)
            except AssertionError:
                missing = []
                for ch in dict.fromkeys(value):
                    try:
                        abilities.text_alpha(ch)
                    except AssertionError:
                        missing.append(ch)
                messagebox.showwarning("Card label", f"The game's card font has no {' '.join(missing)}, so it can't "
                                                     f"show {value!r}. Try other letters.")
                self.show_settings()
                return
            other = ONE_OF.get(key)
            if other:                   # a card shows an item ability or a special one, not both
                for n in names:
                    if self.builtin(n, other)[0] or self.settings.get(n, {}).get(other) not in (None, AS_IS):
                        self.settings.setdefault(n, {})[other] = None
        self.set_setting(names, key, value)

    def set_setting(self, names, key, value):
        """Give every named character the setting (AS_IS: leave it as the character has it)."""
        for n in names:
            if value == AS_IS:
                self.settings.get(n, {}).pop(key, None)
                if n in self.settings and not self.settings[n]:
                    del self.settings[n]
            else:
                self.settings.setdefault(n, {})[key] = value
        if value != AS_IS and names:
            self.tick(option_features(key, value), why=f"{', '.join(names[:3])}'s {key.replace('_', ' ')}")
        self.refresh_char_list()

    def reset_settings(self):
        for n in self.selected_chars():
            self.settings.pop(n, None)
        self.refresh_char_list()

    def char_settings(self):
        """[(name, key, value)] for the characters in the roster (stock, and ticked new characters and recolors)."""
        listed = {e[0] for e in self.roster()}
        return [(n, k, v) for n, opts in self.settings.items() if n in listed for k, v in opts.items()]

    def pickable(self, key, value):
        """A per-character key and value the Characters tab can show (anything else is kept as it is)."""
        kind = next((o[2] for o in CHAR_OPTIONS if o[1] == key), None)
        if kind == "label":
            return value is None or isinstance(value, str)
        return kind is not None and any(v == value and type(v) is type(value)
                                        for v in self.choice_lists[kind].values())


    # --- profiles

    def to_profile(self):
        p = {}
        if self.about.get().strip():
            p["about"] = self.about.get().strip()
        p["features"] = sorted(self.picked())
        options = dict(self.extra_options)
        if "menu-color" in p["features"]:
            options["menu-color"] = {"color": self.color.get().strip()}
        if "boot-game" in p["features"] and self.boot_game:
            options["boot-game"] = dict(self.boot_game)
        if "boot-captain-select" in p["features"] and self.boot_captain:
            options["boot-captain-select"] = dict(self.boot_captain)
        if "bench" in p["features"] and not self.bench_dh.get():
            options["bench"] = {"dh": False}
        if "match-seed" in p["features"] and self.seed_value()[0] and self.seed_value()[1] is not None:
            options["match-seed"] = {"seed": self.seed_value()[1]}
        for f in game_options.REPLAY_ROWS:
            if f in p["features"] and game_options.replay_value(f, self.replay)[0]:
                options[f] = game_options.replay_value(f, self.replay)[1]
        if "item-odds" in p["features"] and self.odds_value(strict=False):
            options["item-odds"] = self.odds_value(strict=False)
        if self.captains_tab and self.captains_tab.current() is not None:
            options["captains"] = self.captains_tab.current()
        if self.grid_tab.current() is not None:
            options["grid-order"] = self.grid_tab.current()
        if options:
            p["options"] = options
        chars = {name: dict(opts) for name, opts in self.extra_characters.items()}
        for name, key, value in self.char_settings():
            chars.setdefault(name, {})[key] = value
        known = {d["name"] for _, d, _ in self.new_chars} | {r["name"] for _, r in self.recipes} | set(self.ivars)
        for name, opts in self.settings.items():  # an unticked one keeps its edits saved (the build leaves them out:
            if name in known and name not in chars:   # patch.settings_in_build; Nick's "wabluigi")
                chars[name] = dict(opts)
        if chars:
            p["characters"] = chars
        imported = [n for n, v in self.ivars.items() if v.get()]
        if imported:
            p["imported"] = imported
        for key, store, folder in (("new_characters", self.cvars, "characters"), ("recolors", self.rvars, "recolors")):
            on = [path for path, v in store.items() if v.get()]
            if on:
                p[key] = [f"{folder}/*.json"] if len(on) == len(store) else [rel(path) for path in on]
        for part in self.parts:
            for k, v in part.to_profile().items():     # lists (e.g. "creations") from several parts add up, dicts
                p[k] = (p[k] + v if isinstance(v, list) and isinstance(p.get(k), list) else   # ("options") join
                        {**p[k], **v} if isinstance(v, dict) and isinstance(p.get(k), dict) else v)
        return p

    def load(self, path):
        profile = json.loads(Path(path).read_text(encoding="utf8"))
        unknown = sorted(set(profile.get("features", [])) - set(self.fvars))
        for f, v in self.fvars.items():
            v.set(f in profile.get("features", []))
        self.about.set(profile.get("about", ""))
        options = profile.get("options", {})
        if "menu-color" in self.fvars:  # (no menu_purple for an edition without it)
            self.color.set(options.get("menu-color", {}).get("color", self.menu_purple.DEFAULT))
        odds = options.get("item-odds", {}) if self.odds else {}
        for name, v in self.odds.items():
            w = odds.get(name)
            v.set("" if w is None else "/".join(map(str, w)) if isinstance(w, list) else str(w))
        self.boot_game = options.get("boot-game") if "boot-game" in self.fvars else None
        self.boot_captain = options.get("boot-captain-select") if "boot-captain-select" in self.fvars else None
        self.bench_dh.set(bool(options.get("bench", {}).get("dh", True)))
        seed = options.get("match-seed", {}).get("seed") if "match-seed" in self.fvars else None
        self.seed.set("" if seed is None else str(seed))
        for f in game_options.REPLAY_ROWS:
            game_options.set_replay(self.replay, f, options.get(f) if f in self.fvars else None)
        self.extra_options = {k: v for k, v in options.items() if k not in ("menu-color", "captains", "grid-order",
                                                                            "boot-game", "boot-captain-select",
                                                                            "match-seed", "bench",
                                                                            *game_options.REPLAY_ROWS) and not (
            k == "item-odds" and self.odds)}
        if self.captains_tab:
            self.captains_tab.set_option(options.get("captains"))
        self.grid_tab.set_option(options.get("grid-order"))
        self.refresh_imported()
        have = list(self.ivars)
        want = have if profile.get("imported") is True else [str(n) for n in profile.get("imported") or []]
        for n, v in self.ivars.items():
            v.set(n.lower() in {w.lower() for w in want})
        missing_imports = [n for n in want if n.lower() not in {h.lower() for h in have}]
        self.settings, self.extra_characters = {}, {}
        for ref, opts in profile.get("characters", {}).items():
            name = self.char_name(ref)
            for k, v in opts.items():
                if k == "batting_item" and v is False:
                    v = "none"
                if name and self.pickable(k, v):
                    self.settings.setdefault(name, {})[k] = v
                else:
                    self.extra_characters.setdefault(ref, {})[k] = v
        for key, store in (("new_characters", self.cvars), ("recolors", self.rvars)):
            try:
                on = {p.resolve() for p in patch.expand(profile.get(key, []))}
            except SystemExit as e:
                messagebox.showwarning("Opening choices", str(e))
                on = set()
            for p, v in store.items():
                v.set(p.resolve() in on)
        for part in self.parts:
            part.load(profile)
        dropped = [f for f in unknown if f in HIDDEN]
        unknown = [f for f in unknown if f not in self.not_offered]   # (a tab's own option: set on that tab)
        self.show_others()
        if missing_imports:
            messagebox.showwarning("Opening choices", "These imported characters aren't here, so they're left "
                                   "out: " + ", ".join(missing_imports) + ". Import their packs to use them.")
        self.status.set(f"Opened {Path(path).name}." + (f" Not in this patcher: {', '.join(unknown)}." if unknown else "")
                        + (f" Left out (no longer offered): {', '.join(dropped)}." if dropped else ""))

    def char_name(self, ref):
        """A profile's character reference (a stock, new or recolor name, or an id) -> the name, or None."""
        names = {n.lower(): n for _, n in self.stock}
        names.update({d["name"].lower(): d["name"] for _, d, _ in self.new_chars})
        names.update({r["name"].lower(): r["name"] for _, r in self.recipes})
        names.update({n.lower(): n for n in getattr(self, "ivars", {})})
        ids = dict((i, n) for i, n in self.stock)
        ids.update({int(str(d["id"]), 0): d["name"] for _, d, _ in self.new_chars})
        ids.update({int(str(r["id"]), 0): r["name"] for _, r in self.recipes if "id" in r})
        if isinstance(ref, int) or str(ref).strip().lower().startswith("0x") or str(ref).strip().isdigit():
            try:
                return ids.get(int(str(ref), 0))
            except ValueError:
                return None
        return names.get(str(ref).strip().lower())

    def load_dialog(self):
        path = filedialog.askopenfilename(title="Open choices", initialdir=PROFILES, filetypes=[("Choices", "*.json")])
        if path:
            try:
                self.load(path)
            except (OSError, ValueError, KeyError) as e:
                messagebox.showerror("Opening choices", f"Couldn't read {path}: {e}")

    def save_dialog(self):
        path = filedialog.asksaveasfilename(title="Save choices", initialdir=PROFILES, defaultextension=".json",
                                            filetypes=[("Choices", "*.json")])
        if path:
            Path(path).write_text(json.dumps(self.to_profile(), indent=1), encoding="utf8")
            self.status.set(f"Saved {Path(path).name}.")

    # --- the game

    def pick_iso_in(self):
        p = filedialog.askopenfilename(title="Your game", filetypes=[("Wii disc image", "*.iso *.wbfs"), ("All", "*")])
        if p:
            self.game.set(p)

    def pick_folder_in(self):
        p = filedialog.askdirectory(title="Your game, extracted (the folder with sys and files in it)")
        if p:
            self.game.set(p)

    def default_iso(self):
        """Save as: "Sluggers Mod.iso" (the edition's iso_name) beside the game (the program's folder for an extracted game), " (2)" etc.
        when taken; follows the game until the player types their own."""
        if self.iso.get().strip() not in ("", self.auto_iso):
            return
        g = self.game.get().strip().strip('"')
        if not g:
            return
        gp = Path(g)
        folder = gp.parent if gp.suffix.lower() in (".iso", ".wbfs") else Path(ROOT)
        name = (EDITION or {}).get("iso_name") or (EDITION or {}).get("name", "Sluggers")   # short (Nick)
        out, n = folder / f"{name}.iso", 2
        while out.exists():
            out, n = folder / f"{name} ({n}).iso", n + 1
        self.auto_iso = str(out)
        self.iso.set(self.auto_iso)

    def pick_iso_out(self):
        p = filedialog.asksaveasfilename(title="Save the patched game as", defaultextension=".iso",
                                         filetypes=[("Wii disc image", "*.iso")], confirmoverwrite=False)
        if p:
            self.iso.set(str(patch.iso_path(p)))   # always .iso (git-dc: Nick typed "newitem")

    # --- running

    def start(self, dry):
        if self.running:
            return
        game, iso = self.game.get().strip(), self.iso.get().strip()
        if iso:                         # a typed name ends in .iso too, and "already exists" checks that file
            iso = str(patch.iso_path(iso))
            self.iso.set(iso)
        problem = ("Pick your game first (an ISO file or the extracted folder)." if not game else
                   "Choose where to save the patched game." if not dry and not iso else
                   f"{iso} already exists. Choose a new name: the patcher never overwrites a file."
                   if not dry and Path(iso).exists() else
                   self.color_ok()[1] if "menu-color" in self.picked() and not self.color_ok()[0] else
                   self.seed_value()[1] if "match-seed" in self.picked() and not self.seed_value()[0] else
                   self.replay_problem() if self.replay_problem() else
                   self.odds_note.cget("text") if "item-odds" in self.picked() and self.odds_note.cget("text")
                   else None)
        if problem:
            messagebox.showwarning("Patch", problem)
            return
        # what the picks need goes on by itself, never a question (Nick: "IF I DO SOMETHING THEN IT SHOULD WORK")
        turned_on = self.tick({f for f, _ in self.missing_with_why()})
        notes = [n for part in getattr(self, "parts", []) for n in getattr(part, "notes", lambda: [])()]
        if notes and not messagebox.askokcancel(
                "Patch", "Before patching:\n\n  " + "\n  ".join(notes) +
                "\n\nOK: patch anyway.\nCancel: go back and change it."):
            return
        f = tempfile.NamedTemporaryFile("w", suffix=".json", delete=False, encoding="utf8")
        json.dump(self.to_profile(), f)
        f.close()
        self.running = True
        for b in (self.patch_button, self.check_button):
            b.state(["disabled"])
        self.progress["dry"] = dry
        self.clear_log()
        if turned_on:
            self.append_log("turned on: " + ", ".join(self.titles.get(g, g) for g in turned_on) + "\n")
        if not SINGLE:                  # (the single page shows Progress all the time)
            self.tabs.select(self.progress_frame)
        self.status.set("Checking..." if dry else "Patching... this takes a minute or two.")
        remember_game(game.strip('"'))
        threading.Thread(target=self.work, args=(game, f.name, None if dry else iso, dry), daemon=True).start()

    def work(self, game, profile, iso, dry):
        old = sys.stdout, sys.stderr
        sys.stdout = sys.stderr = Writer(self.q)
        try:
            patch.run(game, profile, iso=iso, dry_run=dry)
            sys.stdout.flush()
            self.q.put(("done", "Check passed: this patch works with your game. Nothing was written." if dry
                        else f"Done: your patched game is {iso}."))
        except SystemExit as e:
            self.q.put(("stopped", str(e.code) if e.code not in (None, 0) else "Stopped."))
        except Exception as e:
            traceback.print_exc()
            sys.stdout.flush()
            self.q.put(("error", f"{type(e).__name__}: {e}"))
        finally:
            sys.stdout, sys.stderr = old
            Path(profile).unlink(missing_ok=True)

    def poll(self):
        try:
            while True:
                kind, text = self.q.get_nowait()
                if kind == "log":
                    self.log_line(text)
                    continue
                if kind == "call":              # a worker's result, handled on the window's thread
                    try:
                        text()
                    except Exception as e:      # (one failed result never stops the queue: the log and Patch)
                        self.status.set(f"Something went wrong: {type(e).__name__}: {e}")
                    continue
                self.running = False
                for b in (self.patch_button, self.check_button):
                    b.state(["!disabled"])
                self.status.set(text if kind == "done" else "Stopped. See the log.")
                self.set_stage(("Check passed" if self.progress["dry"] else "Done") if kind == "done" else
                               "Stopped: " + (text.strip().splitlines() or [""])[0][:80],
                               1.0 if kind == "done" else self.progress["value"], kind=kind)
                self.add_step(text if kind == "done" else f"Stopped: {text}", final=kind)
                self.left = leftout.left_out(self.log.get("1.0", "end")) if kind == "done" else []
                for line in self.left:
                    self.add_step(f"Left out: {line}", final="stopped")
                if self.left:
                    text += "\n\nLeft out:\n  " + "\n  ".join(self.left)
                if kind != "done":              # a refusal or an error: said plainly, the details open
                    self.show_details()
                self.append_log(("\n" + text + "\n") if kind == "done" else f"\nStopped: {text}\n")
                if SINGLE and self.grid_tab.game is None:   # the grid, if it couldn't read the game before
                    self.beta.load_grid()
                {"done": messagebox.showinfo, "stopped": messagebox.showwarning}.get(kind, messagebox.showerror)(
                    "Patch", text if kind != "error" else
                    f"Something went wrong:\n\n{text}\n\nThe log has the details (please send it to us).")
        except queue.Empty:
            pass
        if self.running:
            self.creep()
        self.root.after(100, self.poll)

    def build_credits_tab(self):
        """Credits: the whole of CREDITS.md (scripts/credits.py), read-only, under git-92's line."""
        frame = ttk.Frame(self.tabs, padding=6)
        self.tabs.add(frame, text="Credits")
        fit.label(frame, CREDITS_TOP, bold=True).pack(fill="x", pady=(0, 4))
        box = ScrolledText(frame, wrap="word", height=10, font="SluggersSmall")
        try:
            import credits
            box.insert("1.0", credits.text(EDITION))        # an edition's own (None: the whole file)
        except (ImportError, OSError) as e:
            box.insert("1.0", f"The credits couldn't be read here ({e}).")
        box.configure(state="disabled")
        box.pack(fill="both", expand=True)
        self.credits_frame = frame

    def build_progress_tab(self, parent=None):
        """Progress: a stage line and a progress bar (stage_of: patch.run's steps), the plain steps of the run, and
        the full log behind "Show details" (collapsed; an error opens it). parent: a frame to build it in instead of
        a tab (the single page: one row, the steps in the details too)."""
        frame = ttk.Frame(parent or self.tabs, padding=6 if parent is None else 0)
        if parent is None:
            self.tabs.add(frame, text="Progress")
            intro(frame, "progress")
        else:
            frame.pack(fill="both", expand=True)
        self.progress_frame = frame
        head = ttk.Frame(frame)
        head.pack(fill="x")
        self.stage = tk.StringVar(value="Ready")
        self.stage_label = ttk.Label(head, textvariable=self.stage, style="Stage.TLabel", width=30)
        self.stage_label.pack(side="left")
        self.details = tk.BooleanVar(value=False)
        self.details_button = ttk.Checkbutton(head, text="Show details", variable=self.details,
                                              command=self.toggle_details, style="Switch.TCheckbutton")
        self.details_button.pack(side="right", padx=(style.PAD, 0))
        self.bar = ttk.Progressbar(head, mode="determinate", maximum=1000)
        self.bar.pack(side="left", fill="x", expand=True, padx=(style.GAP, 0))
        self.progress = {"value": 0.0, "next": 0.0, "dry": False}
        self.steps = tk.Text(frame, height=14 if parent is None else 3, wrap="word", state="disabled",
                             relief="flat", highlightthickness=0, background=style.background(self.root),
                             font="TkDefaultFont")
        self.steps.tag_configure("now", font="SluggersSection")
        self.steps.tag_configure("done", foreground=style.GREEN, font="SluggersSection")
        self.steps.tag_configure("stopped", foreground=style.RED, font="SluggersSection")
        self.single_progress = parent is not None
        if parent is None:              # the tab: the steps always shown, the log under them
            self.steps.pack(fill="both", expand=True, pady=(style.PAD, 0))
        self.log = ScrolledText(frame, height=12 if parent is None else 6, wrap="word", state="disabled",
                                font="SluggersMono")
        self.seen_steps = set()

    def toggle_details(self):
        if self.details.get():
            if self.single_progress:
                self.steps.pack(fill="x", pady=(style.GAP, 0))
            self.log.pack(fill="both", expand=True, pady=(style.GAP, 0))
        else:
            self.log.pack_forget()
            if self.single_progress:
                self.steps.pack_forget()

    def show_details(self):
        """Open the details for a refusal or an error (folded again when the next run starts)."""
        if not self.details.get():
            self.details.set(True)
            self.toggle_details()
            self.progress["opened"] = True

    def set_stage(self, text, value=None, next_=None, kind=None):
        """The stage line and the bar (value, next_: 0-1; kind "done" / "stopped" / "error" colours the line)."""
        self.stage.set(text)
        self.stage_label.configure(style={"done": "StageDone.TLabel", "stopped": "StageProblem.TLabel",
                                          "error": "StageProblem.TLabel"}.get(
            kind, "Stage.TLabel"))
        p = self.progress
        if value is not None:
            p["value"] = max(p["value"], value) if kind is None else value
        if next_ is not None:
            p["next"] = next_
        self.bar.configure(value=round(p["value"] * 1000))

    def creep(self, rate=0.004):
        """While a stage runs: the bar a little closer to the next stage's start (never there)."""
        p = self.progress
        room = p["next"] - 0.01 - p["value"]
        if room > 0:
            p["value"] += room * rate
            self.bar.configure(value=round(p["value"] * 1000))

    def log_line(self, line):
        self.append_log(line + "\n")
        stage = stage_of(line, self.progress["dry"])
        if stage:
            self.set_stage(*stage)
        else:
            self.creep(0.02)            # (the build's lines: the bar moves with them)
        step = step_of(line)
        if step and step not in self.seen_steps:
            self.seen_steps.add(step)
            self.add_step(step)

    def add_step(self, text, final=None):
        self.steps.configure(state="normal")
        self.steps.tag_remove("now", "1.0", "end")
        tag = {"done": "done", "stopped": "stopped", "error": "stopped"}.get(final, "now")
        self.steps.insert("end", ("" if final else "\u2022 ") + text + "\n", tag)
        self.steps.see("end")
        self.steps.configure(state="disabled")

    def callback_error(self, exc, value, tb):
        """An error in a button or other callback: in the log and a plain message, never silently (git-92: in 3.6.6
        Import a model... did nothing, its ImportError lost in Tk's callback)."""
        text = "".join(traceback.format_exception(exc, value, tb))
        try:
            sys.stderr.write(text)
        except Exception:
            pass
        try:
            self.append_log("\n" + text)
        except Exception:                   # (before the log exists)
            pass
        messagebox.showerror("Something went wrong", f"Something went wrong: {exc.__name__}: {value}. Please send "
                                                     f"this to the patcher's makers.")

    def append_log(self, s):
        self.log.configure(state="normal")
        self.log.insert("end", s)
        self.log.see("end")
        self.log.configure(state="disabled")

    def clear_log(self):
        for w in (self.log, self.steps):
            w.configure(state="normal")
            w.delete("1.0", "end")
            w.configure(state="disabled")
        self.seen_steps = set()
        self.progress.update(value=0.0, next=0.0)
        if self.progress.pop("opened", False) and self.details.get():   # (opened by a stop, not by the player)
            self.details.set(False)
            self.toggle_details()
        self.set_stage("Starting", 0.0, 0.02, kind="new")


def main():
    root = tk.Tk()
    App(root)
    root.mainloop()


if __name__ == "__main__":
    main()
