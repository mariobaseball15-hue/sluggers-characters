"""The patcher: write the features a player picks into their own copy of the clean game (docs/patcher.md).

  python scripts/patcher/patch.py --game <extracted RMBE01 | game.iso> --profile my-mod.json --out <new folder>
                                  [--iso out.iso] [--list]

  --list      print every feature id with its dependencies and whether the build can switch it yet

Profile (JSON; examples in scripts/patcher/profiles/):
  {"features": ["piranha-plants", "batter-depth", ...],        entry ids from the notes page
   "options": {"menu-color": {"color": "teal"}},                feature options
   "characters": {"Petey Piranha": {"piranha_plants": true}},  per-character options on stock characters
   "new_characters": ["characters/0x66_pauline.json"],          optional; wildcards work ("characters/*.json")
   "recolors": ["recolors/purple-yoshi.json"]}                  optional; wildcards work

Recolors are made from the player's own game (recolor.make into a work folder), so none of the recolored art ships.
Character definitions the recolor tool wrote (characters/* made from a recipe) are left out of new_characters: a
recipe goes under "recolors".

The build (git-ea) takes the features, the player's game (game=) and a work folder for the files made from it (work=,
charbuild.DERIVED). Stock overrides and a build with no new characters come in charbuild.SUPPORTS as they land;
until then the patcher refuses those profiles rather than silently ignoring part of them.
"""
import argparse, glob, hashlib, json, re, shutil, subprocess, sys, tempfile, threading
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[1]
sys.path.insert(0, str(ROOT / "scripts"))
sys.path.insert(0, str(HERE))              # edition.py and the patcher's other modules, also when run through runpy

# the clean USA game (RMBE01)
CLEAN_SHA1 = {"sys/main.dol": "08236f3164360f08075459f1f7a76b16e25fe734",
              "files/dt_na.dat": "b9a1e169421c310bf97e73a0ab39802881a9f727",
              "files/sound_NA/MY2.brsar": "a8c6bfe96ba97a24a1c4a287bd19074cde8ce258"}
ASSETS = ROOT / "assets.json"     # in the download only (package.py): our files that ship as deltas on the game
WIT = next(iter(sorted((ROOT / "tools/wit").glob("*/bin/wit.exe"))), None)

PROFILE_KEYS = {"about", "features", "options", "characters", "new_characters", "recolors", "char_defaults",
                "stadium", "stadium_2", "select_map", "imported", "creations"}   # stadium_2: the second (id 11)   # stadium: a preset name or a .slgstadium (git-64);
# select_map: {stadium: a look preset or a .slgmap} for the stadium-select map (git-9b's stadium_map)
# imported: true (every imported character pack) or [names] (git-a3's charpack; they live in IMPORTED_DEST)
# creations: creation files (.slghazard, ...: creators/blocks.py; relative to the repo, wildcards allowed)
IMPORTED_DEST = None        # None: charpack.default_dest() (%APPDATA%\Sluggers Patcher\characters)   # about: shown in the menu
# build features the patcher never offers or applies (the build keeps them for our own chars-N builds)
NOT_OFFERED = {"stock-balance": "our balance changes to stock characters' stats and chemistry aren't part of the "
                                "patcher (Nick): take \"stock-balance\" out of \"features\""}
# feature options: {feature: {option: charbuild build argument}}; WHOLE: the option is the whole value
OPTIONS = {"menu-color": {"color": "menu_color"}, "match-seed": {"seed": "seed"}, "bench": {"dh": "bench_dh"},
           "replay-slow-motion": {"speed": "replay_speed", "frames": "replay_frames"},   # (replay_tweaks.check)
           "replay-camera": {"camera": "replay_camera"}, "contact-freeze": {"percent": "freeze_percent"},
           "inning-break-time": {"seconds": "inning_seconds"}}                               # (inning_break.check)
REPLAY_OPTIONS = {"replay_speed": "speed", "replay_frames": "frames", "replay_camera": "camera",
                  "freeze_percent": "percent"}
WHOLE = {"item-odds": "item_odds",          # {item: weight} (git-a7, starbits_roulette.odds_ids)
         "captains": "captains_option",      # {"list": [...], "positions": {...}} (git-a7, captains.check at run time)
         "grid-order": "grid_order",         # [[names], ...] every square in reading order (git-d9, grid_order.validate)
         "ability-edits": "ability_edits",   # {ability name: {field: value}} or a .slgabilities path (git-a7)
         "boot-game": "boot_game",           # {"captains", "teams", "stadium", "night", "level"} (check_boot_game)
         "boot-captain-select": "boot_captain",   # {"stadium", "night"}: the game after it (check_boot_captain)
         "cpu-settings": "cpu_settings"}     # {setting: value or {"5": v, "6": v}} or a .slgcpu path (cpu_settings)
OPTION_FEATURE = {"grid-order": "new-ids"}   # options whose name isn't their feature's id
# the stock roulette's rows (score difference 0 / 1 / 2) for shell, fireball, bobomb, pow, banana, boo (0x80630FB0)
STOCK_ODDS = [[20, 20, 20, 10, 20, 10], [20, 15, 20, 15, 15, 15], [20, 15, 15, 20, 15, 15]]


def registry():
    """{feature id: {"requires": [...], "switch": ...}}: charbuild.FEATURES, and NOT_IN_BUILD (test switches the
    patched game never has; accepted and left out)."""
    import charbuild
    import edition
    allowed = (edition.load() or {}).get("features")        # a trimmed download (edition.py): only its features
    out = {k: dict(v, requires=v.get("requires", []), switch="build") for k, v in charbuild.FEATURES.items()
           if k not in NOT_OFFERED and (allowed is None or k in allowed)}
    for k in (HIDDEN | set((edition.load() or {}).get("follow_settings", ()))) & set(out):
        out[k]["hidden"] = True                     # the window doesn't list it (auto_features / edition_follow tick it)
    for k in DEFAULT_ON & set(out):
        out[k]["default"] = True                    # ticked in a fresh window; a saved profile keeps its own picks
    for k, why in getattr(charbuild, "NOT_IN_BUILD", {}).items():
        if allowed is None:
            out[k] = {"requires": [], "switch": "not in the patched game", "doc": why}
    return out


# features the window never shows: ticked by the patcher when something needs them (auto_features)
HIDDEN = {"item-engine"}     # the item machinery (git-f3 7f689ab): for item creations, and under koopaling-items
# features ticked in a fresh window (the registry's "default"): memory savers Nick tested (git-92)
DEFAULT_ON = {"share-anim-banks"}


def item_creation_count(patterns):
    """How many of the profile's creations are items (they need the item engine)."""
    if not patterns:
        return 0
    from creators import blocks
    n = 0
    for p in expand(patterns):
        try:
            n += blocks.load(p)["kind"] == "item"
        except ValueError:
            pass                                    # item_creations says what's wrong with it
    return n


def auto_features(profile, reg):
    """The hidden features the profile needs, ticked (with the features they need): item-engine for item creations
    and with koopaling-items. Returns (profile, notes)."""
    feats = list(profile.get("features", []))
    if "item-engine" not in reg or "item-engine" in feats:
        return profile, []
    if not ("koopaling-items" in feats or item_creation_count(profile.get("creations"))):
        return profile, []
    added, todo = [], ["item-engine"]
    while todo:                                     # item-engine and what it needs, transitively
        f = todo.pop()
        if f in feats or f not in reg:
            continue
        feats.append(f)
        added.append(f)
        todo += reg[f]["requires"]
    shown = [f for f in added if f not in HIDDEN]
    notes = [f"items you made need these, so they're ticked too: {', '.join(shown)}"] if shown else []
    return dict(profile, features=feats), notes


# our fielding abilities -> their features (charbuild.char_features); an edition's "follow_settings" among them are on
# exactly when a character has that ability (edition_follow)
FIELDING_FEATURE = {13: "star-solo-toss", 14: "clamber-solo-jump"}


def edition_follow(profile):
    """An edition's "follow_settings" features (the beta's Clamber Jump, never shown): on exactly when a character
    in the profile ends up with one, off otherwise (a stale tick changes nothing). A character without a fielding
    setting of their own has the patcher's default (charbuild.STOCK_DEFAULTS: the Kongs' Clamber Jump; Nick,
    2026-09-29: "Default the kongs to have clamber jump"), so the beta's Kongs have it unless the player picks
    something else for every one of them. Returns the profile."""
    import edition
    follow = set((edition.load() or {}).get("follow_settings", ()))
    if not follow:
        return profile
    chars = profile.get("characters") or {}
    field = lambda o: (o.get("fielding ability", (o.get("stats") or {}).get("fielding ability"))
                       if isinstance(o, dict) else None)
    values = [field(o) for o in chars.values()]
    if profile.get("char_defaults") is not False:       # the defaults of the characters without a setting
        import charbuild
        from sluggers_data import char_id
        set_ids = set()
        for k, o in chars.items():
            try:
                if field(o) is not None:
                    set_ids.add(char_id(k))
            except (KeyError, ValueError):
                pass
        values += [e.get("fielding ability") for e in charbuild.STOCK_DEFAULTS if e["id"] not in set_ids]
    used = {FIELDING_FEATURE.get(int(v)) for v in values if isinstance(v, int)} & follow
    feats = [f for f in profile.get("features", []) if f not in follow] + sorted(used)
    return dict(profile, features=feats)


# profile keys that need a feature (an edition without it drops them, with a note)
KEY_FEATURE = {"stadium": "new-stadium", "stadium_2": "new-stadium", "select_map": "new-stadium",
               "imported": "new-ids", "recolors": "recolor-tool", "new_characters": "new-ids"}


def edition_trim(profile):
    """The profile as this download's edition can build it: features it doesn't offer, their options and the profile
    keys that need them dropped (charbuild degrades the per-character keys), silently (Nick: "NO REFERENCES TO FUTURE
    FEATURES"; the notes it returns are always empty now). The full patcher: the profile as it is."""
    import edition
    ed = edition.load()
    if not ed:
        return profile, []
    allowed = set(ed["features"])
    out, notes = dict(profile), []
    dropped = sorted(set(profile.get("features", [])) - allowed)
    if dropped:
        out["features"] = [f for f in profile["features"] if f in allowed]
    opts = {f: v for f, v in (profile.get("options") or {}).items() if OPTION_FEATURE.get(f, f) in allowed}
    if profile.get("options") and len(opts) != len(profile["options"]):
        out["options"] = opts
    keys = [k for k, f in KEY_FEATURE.items() if profile.get(k) and f not in allowed]
    for k in keys:
        out.pop(k, None)
    kinds = set(ed.get("creators", ()))     # the creators a trimmed edition has (the Characters Beta: items only)
    if profile.get("creations"):
        from creators import blocks
        exts = {blocks.EXTENSIONS[k] for k in kinds if k in blocks.EXTENSIONS}
        try:
            kept = [str(p) for p in expand(profile["creations"]) if p.suffix.lower() in exts]
        except SystemExit:
            kept = []
        if kept:
            out["creations"] = kept
        else:
            out.pop("creations", None)
    return edition_items(out, ed), notes


def edition_items(profile, ed):
    """An edition's items it doesn't roll by default (editions/*.json "never_rolled": the Characters Beta's Star Bits,
    whose code its item engine and Ice need): out of the roulette (weight 0, through item-odds) whenever their code is
    in, unless the profile gives one odds of its own (the beta's Items window: Star Bits' Roulette odds)."""
    never = [i for i in ed.get("never_rolled", ()) if i]
    feats = set(profile.get("features", []))
    if not never or "item-odds" not in ed.get("features", ()) or not (
            {"new-roulette-item", "item-variants", "item-engine"} & feats or profile.get("creations")):
        return profile
    opts = dict(profile.get("options") or {})
    opts["item-odds"] = {**{i: 0 for i in never}, **(opts.get("item-odds") or {})}
    return dict(profile, options=opts, features=sorted(feats | {"item-odds"}))


def sha1(path):
    h = hashlib.sha1()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(1 << 22), b""):
            h.update(chunk)
    return h.hexdigest()


def extract_iso(iso, dest):
    if not WIT:
        sys.exit("reading an .iso needs wit, which should be in tools/wit next to the patcher; or extract the game "
                 "yourself (Dolphin: right-click the game, Properties, Filesystem, Extract Entire Disc) and pick that folder")
    print(f"== Extracting {Path(iso).name}")
    subprocess.run([str(WIT), "extract", "--psel", "data", "--quiet", str(iso), str(dest)], check=True)


GAME_CACHE = ROOT / "cache" / "game"      # an .iso's extracted game, kept for the next run and the recolor editor


NOT_CLEAN = {      # the files that have to be the clean game's: what to say when one isn't
    "sys/main.dol": "This game's code has been changed by another mod or patcher (for example Extra Innings); the "
                    "patcher needs a game whose code is clean. Model and texture mods are fine.",
    "files/sound_NA/MY2.brsar": "This game's sounds (sound_NA/MY2.brsar) have been changed by another mod; the "
                                "patcher needs the game's own sound file. Model and texture mods are fine."}


def check_game(folder):
    """Refuse a folder that isn't the USA game with clean code and sounds; returns the dt_na.dat files a model /
    texture mod changed (modded_game.changed: [(dir, file)], [] for the clean game). main.dol holds dt_na.dat's TOC,
    so a clean main.dol means the clean layout: the mod's changed files are built on as they are (docs/patcher.md)."""
    import modded_game
    for rel in CLEAN_SHA1:
        p = folder / rel
        if not p.exists():
            sys.exit(f"{p} is missing: pick the .iso, or the extracted game folder (the one holding sys and files)")
    boot = folder / "sys/boot.bin"
    if boot.exists() and boot.read_bytes()[:6] != b"RMBE01":
        sys.exit(f"this isn't the USA Mario Super Sluggers (RMBE01): the disc says "
                 f"{boot.read_bytes()[:6].decode('ascii', 'replace')}. The patcher needs the USA game.")
    for rel, why in NOT_CLEAN.items():
        if sha1(folder / rel) != CLEAN_SHA1[rel]:
            sys.exit(why)
    if sha1(folder / "files/dt_na.dat") == CLEAN_SHA1["files/dt_na.dat"]:
        modded_game.remember(folder, [])
        return []
    modded_game.forget(folder)                  # (hashed again: the folder's files may have changed since)
    try:
        return modded_game.changed(folder)
    except ValueError as e:
        sys.exit(str(e))


_GAME_LOCK = threading.Lock()


def game_folder(game):
    """A readable clean game folder (sys/, files/) for `game`: an extracted folder is checked and returned; an .iso
    is extracted once into GAME_CACHE (next to the patcher), checked, and reused while the .iso's path, size and
    modification time stay the same. Check, Patch and the recolor editor share it. Refuses with SystemExit. One at a
    time (Nick's Beta 3.6.1 empty grid: the window's grid was reading the ISO into GAME_CACHE when Patch started, and
    Patch's rmtree + extract pulled it out from under it): a second caller waits and reuses the first one's."""
    with _GAME_LOCK:
        return _game_folder(game)


def _game_folder(game):
    game = Path(game)
    if not game.exists():
        sys.exit(f"{game} doesn't exist")
    if game.is_dir():
        check_game(game)
        return game
    st = game.stat()
    key = {"iso": str(game.resolve()), "size": st.st_size, "mtime_ns": st.st_mtime_ns}
    stamp = GAME_CACHE / "source.json"
    import modded_game
    try:        # the stamp: the .iso it came from and the files its mod changed ("modded"; an older stamp has none:
        got = json.loads(stamp.read_text(encoding="utf8"))           # it was checked clean). Another .iso (a
        if {k: got.get(k) for k in key} == key and \
                all((GAME_CACHE / rel).exists() for rel in CLEAN_SHA1):       # clean one after a modded one, or
            modded_game.remember(GAME_CACHE, got.get("modded", []))           # the other way) is extracted anew
            return GAME_CACHE
    except (OSError, ValueError, AttributeError):
        pass
    shutil.rmtree(GAME_CACHE, ignore_errors=True)
    modded_game.forget(GAME_CACHE)
    extract_iso(game, GAME_CACHE)
    modded = check_game(GAME_CACHE)
    stamp.write_text(json.dumps(dict(key, modded=modded)), encoding="utf8")
    return GAME_CACHE


def expand(patterns):
    """Profile paths (relative to the repo, wildcards allowed) -> files, in order, each once."""
    out = []
    for pat in patterns:
        hits = sorted(glob.glob(str(ROOT / pat))) if glob.has_magic(pat) else [str(ROOT / pat)]
        if not hits:
            sys.exit(f"{pat}: matches nothing")
        out += [Path(h) for h in hits if Path(h) not in out]
    for p in out:
        if not p.exists():
            sys.exit(f"{p}: missing")
    return out


def check_profile(profile, reg):
    """Everything about the profile that can be checked without the game. Returns (features, build options, stock
    entries, new character definitions (with the profile's "characters" keys applied), recipe paths, notes,
    {recolor name: keys} for the recolors' definitions)."""
    extra = sorted(set(profile) - PROFILE_KEYS)
    if extra:
        sys.exit(f"profile: unknown keys {', '.join(extra)} (it takes {', '.join(sorted(PROFILE_KEYS))})")
    profile, edition_notes = edition_trim(profile)
    profile = edition_follow(profile)               # (the beta's Clamber Jump: follows its Fielding list)
    profile, auto_notes = auto_features(profile, reg)
    edition_notes = edition_notes + auto_notes
    want = resolve(profile, reg)
    options = check_options(profile.get("options", {}), want)
    if "captains" in want and "captains_option" not in options:   # Nick: the captain screen starts vanilla; our 14
        options["captains_option"] = {"list": []}                 # are an explicit options.captains (everything.json)
    chars, recolored = [], []
    import edition                      # an edition offers a short list (the beta): a wildcard takes only those
    for p in expand(profile.get("new_characters", [])):
        d = json.loads(p.read_text(encoding="utf8"))
        if d.get("_why", "").startswith("Recolor tool"):
            if edition.offers("characters", p):     # (one the edition doesn't offer isn't worth a note)
                recolored.append(d)
        elif edition.offers("characters", p):
            chars.append(d)
    notes = list(edition_notes)
    listed_recipes = expand(profile.get("recolors", []))
    recipes = [p for p in listed_recipes if edition.offers("recolors", p)]
    import recolor
    dropped = {}        # a listed recipe the edition doesn't offer: said so, never "isn't a character" (git-92, Nick)
    for p in listed_recipes:
        if p not in recipes:
            try:
                n = str(recolor.load_recipe(p).get("name") or p.stem)
            except Exception:
                n = p.stem
            dropped[n.lower()] = (f"your recolor {n!r} was left out because {(edition.load() or {}).get('name', 'this '
                                  'edition')} offers only its own recolors ({p.name} isn't one; make it with New "
                                  f"recolor... in this download)")
    notes += list(dropped.values())
    listed = {recolor.load_recipe(p)["name"].lower() for p in recipes}
    missing = [d["name"] for d in recolored if d["name"].lower() not in listed]
    if missing:     # a recolor's definition was listed without its recipe: say where it went
        notes.append(f"left out (made by the recolor tool; list their recipes under \"recolors\" instead): "
                     + ", ".join(missing))
    if profile.get("select_map") is not None:
        import stadium_map
        problems = stadium_map.check(profile["select_map"])
        if problems:
            sys.exit(" ".join(problems))
    imported = imported_list(profile.get("imported"))
    for have, name, need in ((imported, "imported", "new-ids"), (chars, "new_characters", "new-ids"),
                             (recipes, "recolors", "new-ids"),
                             (recipes, "recolors", "recolor-tool"), (profile.get("stadium"), "stadium", "new-stadium"),
                             (profile.get("stadium_2"), "stadium_2", "new-stadium")):
        if have and need not in want:
            sys.exit(f"profile: {name} needs \"{need}\" in features")
    ids = {}
    for d in chars:
        ids.setdefault(int(str(d["id"]), 0), []).append(d["name"])
    for p in recipes:
        r = recolor.load_recipe(p)
        if "id" not in r:
            sys.exit(f"{p.name} has no character id: open it in the recolor editor and save it again (that gives it the "
                     f"next free id)")
        ids.setdefault(int(str(r["id"]), 0), []).append(r["name"])
    clash = [f"0x{i:02X}: {' and '.join(n)}" for i, n in sorted(ids.items()) if len(n) > 1]
    if clash:
        sys.exit("two characters on one id: " + "; ".join(clash))
    items, left_items = item_creations(profile.get("creations", []), want)   # first: a swing's shower may drop one
    hazards, swings, left = creations(profile.get("creations", []), want, pitches := [], items)
    notes += left
    if hazards:
        options["hazards"] = hazards
    if swings:
        options["swings"] = swings
    if pitches:
        options["pitches"] = pitches
    characters, given_notes = given_to_characters(profile.get("characters", {}), items, want)   # old given.*
    notes += given_notes
    characters = swing_names(characters, swings, items)   # "star swing": a name -> its id
    characters = pitch_names(characters, pitches)          # "star pitch": a name -> its id
    folders = {Path(p).parent for p in listed_recipes + expand(profile.get("new_characters", []))}
    characters, left_chars = settings_in_build(characters, chars, [recolor.load_recipe(p) for p in recipes] + imported,
                                               dropped, folders)
    notes += left_chars
    stock, recolor_keys = character_keys(characters, chars,
                                         [recolor.load_recipe(p) for p in recipes] + imported, want, dropped)
    notes += left_items
    if items:
        options["items"] = items
    if edition.load():          # an edition says only what the player asked for and can act on: their own recolor
        notes = list(dropped.values()) + left_chars     # left out, and their saved settings this build skips
    return want, options, stock, chars, recipes, notes, recolor_keys


def given_to_characters(characters, items, want):
    """Old item creations' given.characters / given.always (deprecated, git-f3) moved onto the characters: each named
    character's "batting_item" (the creation's name; an edit of our preset: the item it replaces) and "always_item",
    unless the profile's "characters" already sets them. The build still honours given, and the same character maps
    to the same id, so nothing is given twice. Returns (characters, notes)."""
    if not items:
        return characters, []
    import creators.items as it
    keep_ours = "koopaling-items" not in want
    out = {k: (dict(v) if isinstance(v, dict) else v) for k, v in (characters or {}).items()}
    lower = {str(k).lower(): k for k in out}
    notes = []
    for c in items:
        given = (c.get("blocks") or {}).get("given") or {}
        names = list(given.get("characters") or [])
        if not names:
            continue
        ref = c["name"] if it.resolve(c["name"], items, keep_ours=keep_ours) is not None else \
            (c.get("blocks") or {}).get("replaces") or c.get("replaces")
        if not ref:
            continue
        moved = []
        for who in names:
            key = lower.get(str(who).lower(), who)
            opts = out.get(key) if isinstance(out.get(key), dict) else {}
            if "batting_item" in opts:
                continue
            opts = dict(opts, batting_item=ref)
            if given.get("always") and "always_item" not in opts:
                opts["always_item"] = True
            out[key] = opts
            lower[str(key).lower()] = key
            moved.append(str(who))
        if moved:
            notes.append(f"{c['name']}: now given through the batting item of {', '.join(moved)} (the batter before "
                         f"each of them gets it)")
    return out, notes


def swing_names(characters, swings, items=()):
    """The profile's "characters" with each "star swing" given by name (ours or a creation's) turned into its id;
    custom_swings takes the creations' ids from here on (creators.swings.configure, as the build does). No creations
    and no swing by name: as they are (the creators aren't loaded: a lean download, the Characters Beta, has none)."""
    if not swings and not any(isinstance(o, dict) and isinstance(o.get("star swing"), str) for o in characters.values()):
        return characters
    import creators.swings as sw
    import creators.pitches  # noqa: F401  (its blocks: a .slgpitch loads)
    sw.configure(swings, items)
    try:
        named = sw.ids(swings)
        return {who: (dict(opts, **{"star swing": sw.resolve(opts["star swing"], named)})
                      if isinstance(opts, dict) and isinstance(opts.get("star swing"), str) else opts)
                for who, opts in characters.items()}
    except sw.Invalid as e:
        sys.exit(f"characters: {e}")


def pitch_names(characters, pitches):
    """The profile's "characters" with each "star pitch" given by name (ours: Cosmic Pull 13 .. Vanishing Ball 16, or
    a creation's: a new one 17..20, creators.pitches.ids) turned into its id, top level or under "stats". No
    creations and no pitch by name: as they are (as swing_names)."""
    if not pitches and not any(isinstance(o, dict) and (isinstance(o.get("star pitch"), str) or isinstance(
            (o.get("stats") if isinstance(o.get("stats"), dict) else {}).get("star pitch"), str))
            for o in characters.values()):
        return characters
    import creators.pitches as cp
    try:
        named = cp.ids(pitches)
        out = {}
        for who, opts in characters.items():
            if isinstance(opts, dict):
                opts = dict(opts)
                if isinstance(opts.get("star pitch"), str):
                    opts["star pitch"] = cp.resolve(opts["star pitch"], named)
                if isinstance(opts.get("stats"), dict) and isinstance(opts["stats"].get("star pitch"), str):
                    opts["stats"] = dict(opts["stats"], **{"star pitch": cp.resolve(opts["stats"]["star pitch"], named)})
            out[who] = opts
        return out
    except cp.Invalid as e:
        sys.exit(f"characters: {e}")


def creations(patterns, want, pitches=None, items=()):
    """The profile's "creations" -> (hazard creations for build(hazards=), star swing creations for build(swings=),
    notes). Each file is checked by the shared loader (creators/blocks.py); a hazard replaces our preset of its kind
    (creators/hazards.py: one per kind); a star swing gets an id after ours (creators/swings.py). One whose feature is
    off is left out with a note, as a character key's is. Items: item_creations. Star pitches: not in the build yet (noted)."""
    if not patterns:
        return [], [], []
    from creators import blocks
    if all(p.suffix.lower() == blocks.EXTENSIONS["item"] for p in expand(patterns)):
        return [], [], []                           # items only (item_creations): no other creator is loaded (a lean
    import creators.hazards as hz                   # download, the Characters Beta, has only the item one)
    import creators.swings as sw
    import creators.pitches  # noqa: F401  (its blocks: a .slgpitch loads)
    import charbuild
    out, swings, notes, seen = [], [], [], {}
    for p in expand(patterns):
        try:
            c = blocks.load(p)
        except ValueError as e:                     # blocks.Invalid (plain words), or a file that isn't JSON
            sys.exit(f"{p.name}: {e}")
        if c["kind"] == "item":                     # item_creations
            continue
        for snd in (c["blocks"].get("cutin_sound") or {}).get("sounds") or ():   # a star move's own cut-in clips,
            if snd.get("clip"):                                                    # next to the file too
                snd["clip"] = str(Path(p).parent / snd["clip"])
        for pic in (c["blocks"].get("backdrop") or {}).get("pictures") or ():     # and its backdrop pictures
            if pic.get("png"):
                pic["png"] = str(Path(p).parent / pic["png"])
        if c["kind"] == "pitch":
            import creators.pitches as cp
            feature = cp.FEATURES[cp.PRESET_IDS.get(c["name"]) or cp.PATH_ID[c["blocks"]["pitch"]["path"]]]
            if feature not in want:
                notes.append(f"left out {c['name']}: \"{feature}\" isn't in features")
            elif pitches is not None:
                pitches.append(c)
            continue
        if c["kind"] == "swing":
            if "custom-swings" not in want:
                notes.append(f"left out {c['name']}: \"custom-swings\" isn't in features")
            else:
                swings.append(c)
            continue
        if c["kind"] != "hazard":
            notes.append(f"left out {c['name']} (a {c['kind']} creation: not in the build yet)")
            continue
        ch = hz.chassis_of(c)
        if ch in seen:
            sys.exit(f"creations: {seen[ch]} and {c['name']} are both {ch} hazards (one of each kind per game)")
        seen[ch] = c["name"]
        feature = charbuild.HAZARD_FEATURES[ch]
        if feature not in want:
            notes.append(f"left out {c['name']}: \"{feature}\" isn't in features")
            continue
        need = sorted(hz.needs(c) - want)
        if need:
            sys.exit(f"{c['name']}: its {c['blocks']['effect']['kind']} needs \"{', '.join(need)}\" in features")
        out.append(c)
    try:
        sw.ids(swings)                              # the limits: names, how many
        sw.configure(swings, items)()               # and whether their hook code fits (put back: the build sets it)
    except sw.Invalid as e:
        sys.exit(f"creations: {e}")
    return out, swings, notes


def item_creations(patterns, want):
    """The profile's "creations" -> (new items for build(items=), notes). Items need the item engine (item-engine,
    or koopaling-items, which implies it); without it they are left out with a note. One the build can't make yet (creators.items.customs:
    plain words) stops the patch."""
    if not patterns:
        return [], []
    from creators import blocks
    import creators.items
    if any(p.suffix.lower() != blocks.EXTENSIONS["item"] for p in expand(patterns)):
        import creators.hazards, creators.swings, creators.pitches  # noqa: F401  (every kind's blocks: a file loads)
    out = []
    for p in expand(patterns):
        try:
            c = blocks.load(p)
        except ValueError as e:                     # blocks.Invalid (plain words), or a file that isn't JSON
            sys.exit(f"{p.name}: {e}")
        if c["kind"] == "item":
            icon = c["blocks"].get("look", {}).get("icon") or {}
            if icon.get("png"):                     # a picture next to the creation file
                icon["png"] = str(Path(p).parent / icon["png"])
            look = c["blocks"].get("look") or {}
            if look.get("obj"):                     # its own model (own_models), next to the file too
                look["obj"] = str(Path(p).parent / look["obj"])
            sound = c["blocks"].get("sound") or {}
            for ev in ("launch", "hit", "land"):    # its own sounds, next to the file too
                if sound.get(ev + "_clip"):
                    sound[ev + "_clip"] = str(Path(p).parent / sound[ev + "_clip"])
            out.append(c)
    if out and not {"item-engine", "koopaling-items"} & set(want):
        return [], [f"left out {c['name']}: new items need \"item-engine\" in features" for c in out]
    try:
        creators.items.customs(out)
    except blocks.Invalid as e:
        sys.exit(f"creations: {e}")
    return out, []


def check_options(options, want):
    """{feature: {option: value}} -> {build argument: value}."""
    kw = {}
    for f, opts in options.items():
        if f in WHOLE:
            if OPTION_FEATURE.get(f, f) not in want:
                sys.exit(f"options: {f} needs \"{OPTION_FEATURE.get(f, f)}\" in \"features\"")
            kw[WHOLE[f]] = check_odds(opts, want) if f == "item-odds" else                 check_ability_edits(opts) if f == "ability-edits" else                 check_boot_game(opts, want) if f == "boot-game" else                 check_boot_captain(opts) if f == "boot-captain-select" else                 check_cpu_settings(opts, want) if f == "cpu-settings" else opts
            continue
        if f not in OPTIONS:
            sys.exit(f"options: {f} has no options (features with options: {', '.join(list(OPTIONS) + list(WHOLE))})")
        if f not in want:
            sys.exit(f"options: {f} isn't in \"features\"")
        for k, v in opts.items():
            if k not in OPTIONS[f]:
                sys.exit(f"options: {f} takes {', '.join(OPTIONS[f])}, not {k!r}")
            kw[OPTIONS[f][k]] = v
    if "seed" in kw:                                   # match-seed: a number, or blank (the clock)
        import match_seed
        try:
            kw["seed"] = match_seed.parse(kw["seed"])
        except ValueError as e:
            sys.exit(f"options: match-seed: {e}")
    if any(k in kw for k in REPLAY_OPTIONS):
        import replay_tweaks
        for k, name in REPLAY_OPTIONS.items():
            if k in kw:
                try:
                    kw[k] = replay_tweaks.check(name, kw[k])
                except ValueError as e:
                    sys.exit(f"options: {e}")
    if "inning_seconds" in kw:                         # inning-break-time: 0.5..30 seconds, or stock
        import inning_break
        try:
            kw["inning_seconds"] = inning_break.check(kw["inning_seconds"])
        except ValueError as e:
            sys.exit(f"options: {e}")
    if "menu_color" in kw:
        import menu_purple
        try:
            menu_purple.colors(kw["menu_color"])
        except ValueError as e:
            sys.exit(f"options: {e}")
        w = menu_purple.warning(kw["menu_color"])
        if w:
            print("note: " + w)
    return kw


def check_ability_edits(value):
    """options.ability-edits: {ability name: {field: value}}, or a .slgabilities file (the window's page), checked with
    ability_edits.check (git-a7). Returns the edits for build(ability_edits=)."""
    import ability_edits
    if isinstance(value, str):
        p = Path(value) if Path(value).is_file() else ROOT / value
        try:
            _, value = ability_edits.load(p)
        except (OSError, ValueError) as e:
            sys.exit(f"options: ability-edits: {e}")
    problems = ability_edits.check(value or {})
    if problems:
        sys.exit("options: ability-edits: " + " ".join(problems))
    return value or None


def cpu_levels_editable():
    """The CPU levels a player may change: the edition's "cpu_levels_editable" (the Characters Beta: [5]), else both."""
    import cpu_settings
    import edition
    return [int(x) for x in (edition.load() or {}).get("cpu_levels_editable", cpu_settings.LEVELS)]


def check_cpu_settings(value, want):
    """options.cpu-settings: {setting: value or {"5": v, "6": v}}, or a .slgcpu file (the CPU levels tab), checked
    with cpu_settings.check against the build's features (a setting whose CPU feature is off is refused, so it can't
    look applied). Settings a .slgcpu file has that this patcher doesn't are dropped with a note. An edition with
    "cpu_levels_editable" (the Characters Beta: [5]) builds the other levels with today's values: their values (and
    the settings both levels share) are dropped with a note (cpu_settings.only_levels), so a hand-edited profile
    can't change them. Returns the edits for build(cpu_settings=)."""
    import cpu_settings
    if isinstance(value, str):
        p = Path(value) if Path(value).is_file() else ROOT / value
        try:
            _, value, dropped = cpu_settings.load(p)
        except (OSError, ValueError) as e:
            sys.exit(f"options: cpu-settings: {e}")
        if dropped:
            print("note: cpu-settings: this patcher has no " + ", ".join(dropped) + " (left out)")
    if isinstance(value, dict) and set(value) & set(cpu_settings.RETIRED):
        gone = [cpu_settings.RETIRED[k] for k in value if k in cpu_settings.RETIRED]
        value = {k: v for k, v in value.items() if k not in cpu_settings.RETIRED}
        print("note: cpu-settings: taken out of the patcher, so not used: " + ", ".join(gone))
    levels = cpu_levels_editable()
    if isinstance(value, dict) and set(levels) != set(cpu_settings.LEVELS):
        value, dropped = cpu_settings.only_levels(value, levels)
        if dropped:
            print(f"note: cpu-settings: only CPU level {', '.join(map(str, levels))} can be changed here, so these "
                  "were not used (they stay at their base values): " + ", ".join(dropped))
    problems = cpu_settings.check(value or {}, set(want))
    if problems:
        sys.exit("options: cpu-settings: " + " ".join(problems))
    return value or None


def stadium_choices():
    """What a stadium option can be, in words: the stock Exhibition stadiums at the times of day they have."""
    import quickboot
    return "stadium / night is one of " + ", ".join(
        f"{i}{' night' if n else ''} ({quickboot.stadium_name(i, n)})"
        for i in quickboot.STADIUMS for n in (False, True) if quickboot.stadium_ok(i, n))


def check_boot_captain(value):
    """options.boot-captain-select: {"stadium": 0, "night": false}, where the game after captain select is played
    (quickboot.STADIUMS; left out: Mario Stadium by day, as before the option). Returns it for build(boot_captain=)."""
    import quickboot
    if not isinstance(value, dict) or set(value) - {"stadium", "night"}:
        sys.exit("options: boot-captain-select takes {\"stadium\": 0, \"night\": false}")
    stadium, night = value.get("stadium", 0), value.get("night", False)
    if not isinstance(night, bool) or not isinstance(stadium, int) or isinstance(stadium, bool) \
            or not quickboot.stadium_ok(stadium, night):
        sys.exit("options: boot-captain-select: " + stadium_choices())
    return {"stadium": stadium, "night": night}


def check_boot_game(value, want=()):
    """options.boot-game: {"captains": [2 characters], "teams": [[up to 8], [up to 8]], "stadium": 0, "night": false,
    "level": 2}, its shape (charbuild.boot_game_args finds the names in the build; quickboot fills the empty slots).
    level: the CPU level, 1 Rookie .. 4 All-Star (quickboot.LEVELS; left out: Veteran), 5 / 6 only with "level-5" in
    the features (want). Optional "lineups": [[9 names in batting order, null = filled for you] or null, x2],
    "positions": [{name: "CF"}, x2], "benches": [[up to 5 names, the first the DH], x2] and "dr": [who sits for the
    DH: one of the team's captain + 8, or the DH himself = no DH; null = whoever plays P, x2]. Returns it for
    build(boot_game=)."""
    if not isinstance(value, dict) or set(value) - {"captains", "teams", "stadium", "night", "level", "lineups",
                                                  "positions", "benches", "dr"}:
        sys.exit("options: boot-game takes {\"captains\": [two characters], \"teams\": [[up to 8], [up to 8]], "
                 "\"stadium\": 0, \"night\": false, \"level\": 2}")
    caps = value.get("captains") or ["Mario", "Bowser"]
    teams = [[c for c in t if c not in (None, "")] for t in (value.get("teams") or [[], []])]
    if len(caps) != 2 or len(teams) != 2 or any(len(t) > 8 for t in teams):
        sys.exit("options: boot-game: two captains and two teams of up to 8 players each")
    benches = value.get("benches") or [[], []]         # (game_options: each team's bench rows, the DH first)
    if not isinstance(benches, list) or len(benches) != 2 or any(not isinstance(b, list) or len(b) > 5
                                                                 or any(c in (None, "") for c in b) for b in benches):
        sys.exit("options: boot-game: benches is [team 1's bench, team 2's], up to 5 names each (the first is the DH)")
    everyone = [str(c).strip().lower() for c in caps + teams[0] + teams[1] + benches[0] + benches[1]]
    twice = sorted({c for c in everyone if everyone.count(c) > 1})
    if twice:
        sys.exit(f"options: boot-game: picked twice: {', '.join(twice)} (each character can play once)")
    import quickboot                                   # the stock Exhibition stadiums and their times of day
    stadium, night = value.get("stadium", 0), value.get("night", False)
    if not isinstance(night, bool) or not isinstance(stadium, int) or isinstance(stadium, bool) \
            or not quickboot.stadium_ok(stadium, night):
        sys.exit("options: boot-game: " + stadium_choices())
    level = value.get("level", quickboot.DEFAULT_LEVEL)
    levels = [lv for lv in quickboot.LEVELS if lv in quickboot.STOCK_LEVELS or "level-5" in want]
    if not isinstance(level, int) or isinstance(level, bool) or level not in levels:
        sys.exit("options: boot-game: level (the CPU level) is one of " + ", ".join(
            f"{lv} ({quickboot.level_name(lv)})" for lv in levels)
            + ("" if "level-5" in want or level not in quickboot.LEVELS else
               "; 5 and 6 need \"level-5\" (the CPU levels) in \"features\""))
    rosters = [[str(c).strip().lower() for c in [caps[t]] + teams[t]] for t in range(2)]
    lineups = value.get("lineups") or [None, None]      # (game_options: each team's 9 in batting order, null filled)
    positions = value.get("positions") or [{}, {}]      # ({player: "P" | "C" | "1B" ...})
    if not isinstance(lineups, list) or len(lineups) != 2 or not isinstance(positions, list) or len(positions) != 2:
        sys.exit("options: boot-game: lineups is [team 1's batting order, team 2's] and positions "
                 "[{player: position}, {...}]")
    for t in range(2):
        order, pos = lineups[t], positions[t] or {}
        if order is not None:
            named = [str(c).strip().lower() for c in order if c not in (None, "")] if isinstance(order, list) else None
            if named is None or len(order) > 9 or len(set(named)) != len(named) \
                    or any(c not in rosters[t] for c in named):
                sys.exit(f"options: boot-game: team {t + 1}'s batting order names each of its players once "
                         "(up to 9, null for a player filled for you)")
        if not isinstance(pos, dict) or any(str(c).strip().lower() not in rosters[t] for c in pos) \
                or any(str(p).upper() not in quickboot.POSITIONS for p in pos.values()) \
                or len({str(p).upper() for p in pos.values()}) != len(pos):
            sys.exit(f"options: boot-game: team {t + 1}'s positions: its players, each position once ("
                     + " ".join(quickboot.POSITIONS) + ")")
    drs = value.get("dr") or [None, None]
    if not isinstance(drs, list) or len(drs) != 2:
        sys.exit("options: boot-game: dr is [who sits for team 1's DH, team 2's] (null: whoever plays P)")
    for t in range(2):
        if drs[t] not in (None, "") and str(drs[t]).strip().lower() not in \
            rosters[t] + [str(c).strip().lower() for c in benches[t][:1]]:
            sys.exit(f"options: boot-game: team {t + 1}'s dr ({drs[t]}) is one of its players, or its DH (the first "
                     "on its bench) for no DH")
    return dict(value, captains=list(caps), teams=teams)


def check_odds(odds, want):
    """options.item-odds, checked against the items this build rolls (git-a7): shell..boo, + starbits with
    new-roulette-item, + ice with item-variants, + the Koopalings' items (ids 8-13) with koopaling-items. Without new-roulette-item the stock roulette is edited, whose rows
    may total at most starbits_roulette.STOCK_MAX_TOTAL."""
    import starbits_roulette
    new = "new-roulette-item" in want
    n = 6 if not new else 14 if "koopaling-items" in want else 8 if "item-variants" in want else 7
    try:
        ids = starbits_roulette.odds_ids(odds, n)
    except (AssertionError, KeyError, ValueError, TypeError) as e:
        sys.exit(f"options: {e}")
    if not new:
        for r, row in enumerate(STOCK_ODDS):
            total = sum(ids[i][r] if i in ids else w for i, w in enumerate(row))
            if total > starbits_roulette.STOCK_MAX_TOTAL:
                sys.exit(f"options: item-odds: the weights in row {r} add up to {total}; without the new roulette item "
                         f"they may add up to at most {starbits_roulette.STOCK_MAX_TOTAL}")
    return odds


STAT_KEYS = {"star pitch", "fielding ability"}     # under "stats" in a character definition
# the character editor's keys (docs/character-editor.md), beside STOCK_KEYS
EDITOR_KEYS = {"name", "chemistry", "table_stats", "scale", "voice_clips"}   # voice_clips: the Voice page's
LANGUAGES = {"en": "English", "es": "Spanish", "fr": "French"}
CHEMISTRY = {"bad": 0, "neutral": 1, "good": 2}
STAT_RANGES = {   # (low, high, plain name)
    "pitching arm": (0, 1, "pitching arm"), "batting arm": (0, 1, "batting arm"),
    "character class": (0, 3, "class"), "weight": (0, 4, "weight"), "captain": (0, 1, "captain"),
    "star pitch": (0, 20, "star pitch"), "star swing": (0, 12, "star swing"),
    "fielding ability": (0, 14, "fielding ability"), "baserunning ability": (0, 7, "baserunning ability"),
    "slap size": (0, 150, "slap size"), "charge size": (0, 150, "charge size"),
    "slap power": (0, 150, "slap power"), "charge power": (0, 150, "charge power"),
    "bunting": (0, 200, "bunting"), "speed": (0, 200, "speed"), "outfield throwing": (0, 200, "throwing"),
    "fielding": (0, 200, "fielding"), "displayed pitching": (0, 10, "card pitching"),
    "displayed batting": (0, 10, "card batting"), "displayed fielding": (0, 10, "card fielding"),
    "dis speed": (0, 10, "card speed"), "curveball speed": (70, 200, "curveball speed"),
    "charge pitch speed": (70, 200, "charge pitch speed"), "curve": (0, 200, "curve"),
    "curse ball": (0, 100, "curse ball")}
TABLE_RANGES = {
    "hit trajectory": (0, 2, int), "hit curve": (0, 1, int), "star pitch type": (0, 3, int),
    "changeup speed mult": (0.5, 1.5, float), "changeup arc height": (10, 40, float),
    "pitch steering": (0.9, 1.6, float), "catch normal": (30, 450, float), "catch any direction": (30, 450, float),
    "catch centered": (30, 450, float), "catch max height": (30, 450, float), "catch dive": (30, 450, float),
    "strike zone height": (0.15, 1.3, float), "stamina": (20, 100, int),
    "body radius": (18, 179, float), "body height": (120, 390, float),   # the stock game's (Paratroopa .. Bowser)
    "windup charge frames": (5, 33, int)}   # (a float in the game; the stock values are whole frames: Toadette 5 ..)
# Past the game's limit (Nick: "allow people to set stats past the game limit BUT warn them"): STAT_RANGES /
# TABLE_RANGES are the game's own ranges; a plain number may go past them up to what its field holds (stat_room),
# with a warning (check_character's warnings, the editor's amber line). These keep the game's range as a hard limit,
# because the game uses the value to pick an entry from a table or a list (one past the end reads whatever follows:
# a crash or garbage), or it's a yes / no flag:
HARD_LIMITS = {
    "pitching arm", "batting arm", "captain",       # flags: 0 / 1 (left / right, captain star moves)
    "character class",                              # indexes the per-class tables (the CPU's guess weights
                                                    # 0x806248DC, docs/cpu-ai.md; the card's class icon)
    "weight",                                       # a 0-4 class, not a number the game scales by (mapped nowhere)
    "star pitch", "star swing", "fielding ability", "baserunning ability",   # move ids: index the moves' tables
    "hit trajectory", "hit curve", "star pitch type"}   # table values that pick a trajectory / curve / pitch kind
CARD_STATS = {"displayed pitching", "displayed batting", "displayed fielding", "dis speed"}


def stat_room(field):
    """(low, high) a stat or table value can be at all: what its field holds (a stats-row byte 0-255, a u16
    0-65535; a table's byte, s16 or float; the windup, a float the game keeps as an s16), or the game's own range for HARD_LIMITS. Past it the value can't be
    written: refused."""
    if field in HARD_LIMITS:
        lo, hi = (STAT_RANGES.get(field) or TABLE_RANGES[field])[:2]
        return lo, hi
    import charbuild                                # (the build's own rooms: it refuses the same, never wraps)
    if field in STAT_RANGES:
        return charbuild.stat_row_room(field)
    return charbuild.table_room(field)


def past_limit_note(field):
    """What going past the game's limit may do, in plain words (the editor's amber line and the patcher's
    warning)."""
    lo, hi = (STAT_RANGES.get(field) or TABLE_RANGES[field])[:2]
    s = f"past the game's limit ({lo}-{hi}): it may look or play oddly, or crash"
    if field in CARD_STATS:
        s += "; the select card may show it oddly"
    elif hi == 150:
        s += "; the game caps it at 150 on every pitch, so more does nothing"
    return s + "."


PITCH_FEATURES = {13: "pitch-path", 14: "pitch-path", 15: "pitch-items", 16: "pitch-vanish"}


def _field_data():
    """{field: {"file", "where", "field", "hook"?, "notes"?, "source"}} for the character editor's "i" icons (git-b6;
    Nick: "explain what is changed in the data, so people can learn"), made from the build's own tables so the
    addresses can't drift: sluggers_data.STAT_FIELDS for the stats row, charbuild.TABLES / TABLE_STATS for the rest."""
    import edition
    if (edition.load() or {}).get("no_help"):     # an edition without the "i"s never shows it, so it imports none of
        return {}                                  # the features' modules for it (Nick: a lean beta)
    import charbuild
    from sluggers_data import STAT_FIELDS, CHEM_BASE
    tables = {t[0]: t for t in charbuild.TABLES}
    _, s_addr, s_row, s_head = tables["stats"]
    moved = ("with new characters in the patch, the build copies the table into its own data and repoints every "
             "reference to it (charbuild.TABLES), so look it up there instead")
    stats_where = (f"the stats table at 0x{s_addr:08X} ({s_head}-byte header, then 0x{s_row:X} bytes per character id: "
                   f"Mario 0, Luigi 1, ...); {moved}")
    out = {}
    for name, (lo, hi, plain) in STAT_RANGES.items():
        off, width = STAT_FIELDS[name]
        out[name] = {"file": "main.dol", "where": stats_where,
                     "field": f"+0x{off:02X}: {'a big-endian u16' if width == 2 else 'a byte'}, {lo} to {hi}",
                     "source": "scripts/sluggers_data.py (STAT_FIELDS), scripts/charbuild.py (stock_rows)"}
    out["captain"]["notes"] = ("A star pitch or star swing only works with this set; the patcher sets it for you when "
                               "a character gets one.")
    for n in ("slap size", "charge size", "slap power", "charge power"):
        out[n]["notes"] = "The game caps it at 150 on every pitch, so higher values do nothing."
    for n in ("displayed pitching", "displayed batting", "displayed fielding", "dis speed"):
        out[n]["notes"] = "Only what the select card shows; the real stats are the other fields."
    kinds = {"B": "a byte", "f": "a big-endian float", "h": "a big-endian signed 16-bit number"}
    for name in TABLE_RANGES:
        table, off, kind = charbuild.TABLE_STATS[name]
        _, addr, size, head = tables[table]
        lo, hi, _ = TABLE_RANGES[name]
        out[name] = {"file": "main.dol",
                     "where": f"the \"{table}\" table at 0x{addr:08X} ({head}-byte header, then {size} bytes per "
                              f"character id); {moved}",
                     "field": f"+0x{off:X}: {kinds.get(kind, kind)}, {lo} to {hi}",
                     "source": "scripts/charbuild.py (TABLES, TABLE_STATS, stock_rows)"}
    import batter_star, pompom_decoys                              # the per-character keys' own data (git-d0)
    out["batter_star"], out["minimap_decoys"] = batter_star.DATA, pompom_decoys.DATA
    import dino_piranhas                                            # (git-95: Dino's plants)
    out["piranha_plants"] = dino_piranhas.DATA
    out["stamina"]["notes"] = "The most a pitcher has; fatigue counts it down (FUN_80166858 reads it)."
    out["windup charge frames"]["notes"] = ("Frames the windup counts down before the ball leaves the hand "
                                            "(FUN_8015cd34 loads it, FUN_8015dc38 counts it). 7 or less: the CPU "
                                            "batter starts charging before the pitcher moves (precharge, FUN_800c4ff4).")
    out["precharge"] = dict(out["windup charge frames"], notes=(
        "Not a value of its own: Yes sets the windup charge frames to 7 or less (the CPU batter charges while the "
        "countdown is under 8: 0x8062818C), No to more."))
    out["strike zone height"]["notes"] = "In model units times the size; the build recomputes it when the size changes."
    _, z_addr, z_size, z_head = tables["sizescale"] if "sizescale" in tables else (None, 0, 0, 0)
    out["scale"] = {"file": "main.dol",
                    "where": (f"the \"sizescale\" table at 0x{z_addr:08X} ({z_head}-byte header, then {z_size} bytes "
                              f"per character id)") if z_addr else "the character's size-scale row (charbuild.TABLES)",
                    "field": "its floats, multiplied (0.75 to 1.7); the skeleton and the strike zone follow",
                    "notes": "New characters only: a stock character's size isn't changed by the patcher.",
                    "source": "scripts/charbuild.py (normalize: \"scale\")"}
    out["chemistry"] = {"file": "main.dol",
                        "where": (f"each character's stats row, 101 bytes from +0x{CHEM_BASE:02X}: one per other "
                                  f"character id (0 bad, 1 neutral, 2 good); {moved}"),
                        "field": "a stock pair is written into both characters' rows, so it works both ways",
                        "hook": ("the chemistry lookup at 0x8015C880 is replaced: a pair with a new character comes "
                                 "from that character's own row, two new characters from a table of their own"),
                        "source": "scripts/charbuild.py (stock_rows, new_chemistry)"}
    out["name"] = {"file": "files/dt_na.dat",
                   "where": "directory 121 file 5: a message table per language (English, Spanish, French), "
                            "message N is character id N's name",
                   "field": "plain UTF-16 text; the patcher writes a table for each language that needs its own",
                   "notes": ("The name plate on the character select screen (directory 119 file 19) and the "
                             "pitching-change banner (directory 119 file 1) are drawn from the English name."),
                   "source": "scripts/char_names.py, scripts/name_telop.py"}
    # items (git-f3): batter_items' two hooks in the batting setup FUN_80455598, and the roulette
    on_deck = ("the character ON DECK decides (the next batter slot, r28): this character's item goes to the batter "
               "just before them")
    out["batting_item"] = {"file": "main.dol",
                           "where": ("the batting setup FUN_80455598, right after the roulette pick FUN_804583c4: "
                                     "mr r30,r3 at 0x80455678; the on-deck character id is read from the runtime "
                                     "roster *(r13-0x2C8) + team * 0x4FE + slot * 0x8E"),
                           "field": "the item id that replaces the roulette's pick (0-5 stock, 6 Star Bits, 7 Ice, "
                                    "8-13 the Koopalings', 14+ your items)",
                           "hook": "0x80455678 branches to a list of (character id, item) compares in our code; " + on_deck,
                           "notes": "The stock game has none; Koopas / Paratroopas bring Shells, Boos Boos, Fire Bro "
                                    "and Bowser Fireballs by default (batter_items.FIXED_ITEM).",
                           "source": "scripts/batter_items.py (item_hook), scripts/charbuild.py"}
    out["always_item"] = {"file": "main.dol",
                          "where": ("the batting setup FUN_80455598: the chemistry result's first use, subi r0,r3,0x2 "
                                    "at 0x8045564C (an item is given only with good chemistry, 2)"),
                          "field": "on: the result becomes 2 (an item every time), whatever the chemistry",
                          "hook": "0x8045564C branches to a list of character id compares in our code; " + on_deck,
                          "notes": "Items must be on in the game's settings. Wario and Waluigi have it by default "
                                   "(batter_items.ALWAYS_ITEM).",
                          "source": "scripts/batter_items.py (hook)"}
    out["item-odds"] = {"file": "main.dol",
                        "where": ("the roulette weights at 0x80630FB0: 3 rows (the batting team behind by 6 or more, "
                                  "3 to 5, 0 to 2 or ahead) of 6 bytes (Shell, Fireball, Bob-omb, POW, Banana, Boo); "
                                  "with the new items, our copy with a column per item"),
                        "field": "a byte 0-255 per item and row: its weight in the pick",
                        "hook": ("without new items the stock table is edited in place (each row's total at most "
                                 "starbits_roulette.STOCK_MAX_TOTAL); with them the pick FUN_804583c4 branches to our "
                                 "copy"),
                        "source": "scripts/starbits_roulette.py (weight_table, stock_odds)"}
    import pauline_chance as pc, pauline_chance_tuning as pct, pauline_chance_hold as pch      # (git-e2's modules)
    out["chance_cheer"] = {
        "file": "main.dol, and files/sound_NA/MY2.brsar for the jingle",
        "where": (f"the at-bat decision at 0x{pc.TRIGGER:08X}, and the chance table at 0x{pc.TABLE:08X} "
                  f"({pc.ROW} bytes a row, one per captain), which the build copies into its own data with one more "
                  "row for the cheer"),
        "field": ("the cheer's row: its jingle (a 32 kHz PCM stream the patcher adds to MY2.brsar), tempo, beats a "
                  "bar and clap pattern; a flag in our data is set while a character with this key bats"),
        "hook": (f"0x{pc.TRIGGER:08X}: the chance is forced when a human on the batting team can clap and the star "
                 f"meter isn't full; 0x{pct.PICK:08X}: one of {len(pct.POOL)} clap patterns is picked for each cheer; "
                 f"0x{pch.HOLD:08X}: the at-bat intro waits for the jingle to end (at most {pch.MAX_HOLD} frames)"),
        "notes": ("Worth one star, and every clap has to land; the banner says STAR CHANCE!. Pauline has it "
                  "without the key."),
        "source": ("scripts/pauline_chance.py (ids, the row, the trigger), pauline_chance_fixes.py, "
                   "pauline_chance_tuning.py (the patterns, the banner), pauline_chance_hold.py")}
    # the card's extra rows (item / special / hitting / running abilities) and the menu colour (git-a7)
    import item_abilities as ia, star_move_labels as sml, menu_purple as mp
    card = ("the character card's skill list, drawn by the status widgets "
            + ", ".join(f"0x{w:08X}" for w in ia.WIDGETS)
            + " (character select, the batting-order bubble, a third screen) from directory 119 file 19")
    label = ("the label is new art on a page added to directory 119 file 19, drawn from the stock labels' own "
             "letters (abilities.label_image)")
    out["item_ability"] = {"file": "main.dol, files/dt_na.dat",
                           "where": f"{card}: at each widget's +0x{ia.HOOK:X} (`cmpwi cr1,r31,1`) a hook appends a row "
                                    f"of category {ia.CATEGORY} (the \"?\" block icon) for this character",
                           "field": f"a byte per character id in a table of our own (the label to show); {label}",
                           "hook": ", ".join(f"0x{w + ia.HOOK:08X}" for w in ia.WIDGETS),
                           "notes": "A label only: play doesn't read it. Captain select (FUN_802CA65C, directory 119 "
                                    "file 18) shows it too. A card has room for four lines.",
                           "source": "scripts/item_abilities.py"}
    out["special_ability"] = dict(out["item_ability"],
                                  notes="The same row as an item ability (the \"?\" icon), for a special that isn't "
                                        "an item. A label only: play doesn't read it.")
    out["hitting_ability"] = {"file": "main.dol, files/dt_na.dat",
                              "where": f"{card}: the same hook inserts a row of category {ia.HIT_CATEGORY} (the star "
                                       f"swing's bat icon, row 0x{ia.BAT_ICON:X}) right after the star pitch / star "
                                       f"swing lines",
                              "field": f"a byte per character id in a table of our own: its slot in the star swing "
                                       f"label table, which moves to a longer copy (our names from slot 16); {label}",
                              "hook": ", ".join(f"0x{w + ia.HOOK:08X}" for w in ia.WIDGETS),
                              "notes": "A label only: play doesn't read it.",
                              "source": "scripts/item_abilities.py, scripts/star_move_labels.py"}
    out["running_ability"] = {"file": "main.dol, files/dt_na.dat",
                              "where": f"{card}: the baserunning line (the shoe icon); the baserunning label table "
                                       f"0x{sml.BASERUNNING_LABELS:08X} ({sml.STOCK_RUN_SLOTS} slots: none, then "
                                       f"Scatter Dive to Enlarge) moves to a longer copy, our names from slot "
                                       f"{sml.FIRST_RUNNING}",
                              "field": "a byte per character id in a table of our own, put into the card's copy of "
                                       "the stats row +11 as the widgets read it, only for a character with no "
                                       f"baserunning ability of its own; {label}",
                              "notes": "A label only: close plays use the character's real baserunning ability "
                                       "(stats +11), which stays as it is.",
                              "source": "scripts/star_move_labels.py"}
    out["menu-color"] = {"file": "files/dt_na.dat",
                         "where": f"directory 119 file 1 (the menus), element {mp.ELEMENT} node {mp.NODE}: the "
                                  f"full-screen background quad behind the front-end menus",
                         "field": "its two keys' four RGBA vertex colours at key +0x48 (bottom, top, top, bottom); "
                                  "the stock blue is (8, 50, 157) at the bottom and (4, 73, 190) at the top",
                         "notes": "The white dots, glow and giant letters over it are drawn on top of it, so they "
                                  "keep reading on any colour. Elements 0x10 / 0x11 are the green and gold copies "
                                  "some menus use, and are left alone.",
                         "source": "scripts/menu_purple.py"}
    return out


def __getattr__(attr):                    # patch.FIELD_DATA, made on first use (it needs charbuild)
    if attr == "FIELD_DATA":
        globals()["FIELD_DATA"] = _field_data()
        return globals()["FIELD_DATA"]
    raise AttributeError(attr)


def name_fits(text):
    """True if a name fits the select screen's name plate (char_names: 115 px, shrunk from 14 pt to 9 pt at least)."""
    from PIL import Image, ImageDraw, ImageFont
    import char_names
    draw = ImageDraw.Draw(Image.new("RGBA", char_names.NAME_CELL))
    font = char_names.name_font(9) if hasattr(char_names, "name_font") else ImageFont.truetype(char_names.NAME_FONT, 9)
    return draw.textbbox((0, 0), text, font=font)[2] <= char_names.NAME_CELL[0] - 2   # (the drawn weight: git-a7)


def check_character(name, keys, want=None, warnings=None):
    """The character editor's checks for one character's profile keys: a list of plain sentences (empty when fine).
    want: the profile's features, for the moves that need one (None: not checked). warnings: a list that gets a line
    for each value past the game's limit but within what its field holds (allowed: stat_room)."""
    out = []
    if warnings is None:
        warnings = []
    stats = dict(keys.get("stats") or {})
    for k in STAT_KEYS:
        if keys.get(k) is not None:
            stats[k] = keys[k]
    for field, v in stats.items():
        if v is None:
            continue
        if field not in STAT_RANGES:
            out.append(f"{name}: there's no stat called {field!r}.")
            continue
        lo, hi, plain = STAT_RANGES[field]
        if field == "star pitch" and isinstance(v, str) and v.strip():
            continue                                  # a star pitch by name (ours or a creation's): pitch_names
        room = stat_room(field)
        if not isinstance(v, int) or isinstance(v, bool) or not room[0] <= v <= room[1]:
            out.append(f"{name}: {plain} {v!r} is out of range ({room[0]}-{room[1]}" +
                       (")." if field in HARD_LIMITS else ", what the game's data holds)."))
        elif not lo <= v <= hi:
            warnings.append(f"{name}'s {plain} {v} is " + past_limit_note(field))
    pitch = stats.get("star pitch")
    if pitch and stats.get("captain") == 0:
        out.append(f"{name}: a star pitch needs captain star moves; set Captain star moves to Yes or pick no star pitch.")
    if keys.get("star swing") and stats.get("captain") == 0:      # (the build sets Captain for a swing or pitch
        out.append(f"{name}: a star swing needs captain star moves; set Captain star moves to Yes or pick no star swing.")   # unless told 0)
    if want is not None:
        if pitch in PITCH_FEATURES and PITCH_FEATURES[pitch] not in want:
            out.append(f"{name}: star pitch {pitch} needs the feature {PITCH_FEATURES[pitch]}.")
        if stats.get("fielding ability") == 13 and "star-solo-toss" not in want:     # charbuild.char_features
            out.append(f"{name}: Tantrum Toss needs the feature star-solo-toss.")
        if stats.get("fielding ability") == 14 and "clamber-solo-jump" not in want:
            out.append(f"{name}: Clamber Jump needs the feature clamber-solo-jump.")
        swing = keys.get("star swing")
        if isinstance(swing, int) and swing >= 13 and "custom-swings" not in want:
            out.append(f"{name}: star swing {swing} needs the feature custom-swings.")
    if keys.get("item_ability") and keys.get("special_ability"):
        out.append(f"{name}: pick an item ability or a special ability, not both.")
    for other, v in (keys.get("chemistry") or {}).items():
        if v is not None and v not in CHEMISTRY and v not in (0, 1, 2):
            out.append(f"{name}: chemistry with {other} is good, neutral or bad (not {v!r}).")
        if str(other).lower() == str(name).lower():
            out.append(f"{name}: a character's chemistry with themselves is always neutral.")
    for field, v in (keys.get("table_stats") or {}).items():
        if v is None:
            continue
        if field not in TABLE_RANGES:
            out.append(f"{name}: there's no table value called {field!r}.")
            continue
        lo, hi, kind = TABLE_RANGES[field]
        room = stat_room(field)
        if not isinstance(v, (int, float)) or isinstance(v, bool) or (kind is int and v != int(v)) or                 not room[0] <= v <= room[1]:
            out.append(f"{name}: {field} {v!r} is out of range ({lo}-{hi})." if field in HARD_LIMITS else
                       f"{name}: {field} {v!r} doesn't fit in the game's data." if kind is float else
                       f"{name}: {field} {v!r} is out of range ({room[0]}-{room[1]}, what the game's data holds).")
        elif not lo <= v <= hi:
            warnings.append(f"{name}'s {field} {v} is " + past_limit_note(field))
    scale = keys.get("scale")
    if scale is not None and (not isinstance(scale, (int, float)) or not 0.75 <= scale <= 1.7):
        out.append(f"{name}: size {scale!r} is out of range (0.75-1.7).")
    nm = keys.get("name")
    if nm is not None:
        names = {"en": nm} if isinstance(nm, str) else nm if isinstance(nm, dict) else None
        if names is None or not all(isinstance(t, str) for t in names.values()):
            out.append(f"{name}: a name is text, or one per language ({', '.join(LANGUAGES)}).")
        else:
            for lang in names:
                if lang not in LANGUAGES:
                    out.append(f"{name}: names are in {', '.join(LANGUAGES.values())} ({', '.join(LANGUAGES)}), not {lang!r}.")
            for lang, t in names.items():
                if not t.strip():
                    out.append(f"{name}: the {LANGUAGES.get(lang, lang)} name is empty.")
            if names.get("en") and not name_fits(names["en"]):
                out.append(f"{name}: the name {names['en']!r} is too wide for the name plate; shorten it.")
    return out


def _definition_keys(keys):
    """Editor keys in a definition's own form: chemistry words -> 0/1/2, a name per language -> the build's one name."""
    out = dict(keys)
    if isinstance(out.get("chemistry"), dict):
        out["chemistry"] = {k: (CHEMISTRY.get(v, v) if v is not None else None) for k, v in out["chemistry"].items()}
    nm = out.get("name")
    if isinstance(nm, dict):                     # one per language: "name" is the English, "names" all of them
        names = {k: v for k, v in nm.items() if v}
        out["name"] = names.get("en") or next(iter(names.values()), None)
        out["names"] = names
    return out


def set_keys(definition, keys):
    """A profile's per-character keys onto a definition: "star pitch" / "fielding ability" under stats, a "stats" dict
    merged field by field; null clears."""
    for k, v in keys.items():
        if k in ("stats", "chemistry", "table_stats") and isinstance(v, dict):   # merged field by field (null clears)
            sub = definition.setdefault(k, {})
            for f, x in v.items():
                if x is None:
                    sub.pop(f, None)
                else:
                    sub[f] = x
            continue
        if k.startswith("stats:"):
            target, k = definition.setdefault("stats", {}), k[6:]
        else:
            target = definition.setdefault("stats", {}) if k in STAT_KEYS else definition
        if v is None:
            target.pop(k, None)
        else:
            target[k] = v
    stats = keys.get("stats") if isinstance(keys.get("stats"), dict) else {}
    move = keys.get("star pitch") or stats.get("star pitch") or keys.get("star swing")
    if move and "captain" not in keys and "captain" not in stats:   # a star move needs the captain flag; a
        definition.setdefault("stats", {})["captain"] = 1          # definition lists "captain": 0 (git-b6)


def known_characters(folders=()):
    """{name (lower case): id or None} of every character this patcher knows besides the stock ones, in the build or
    not: the definitions in characters/, the recipes in recolors/ (and in `folders`: where the profile's own files
    are), and the imported packs."""
    import recolor
    out = {}
    char_dirs = [ROOT / "characters"] + [Path(f) for f in folders if Path(f).name == "characters"]
    recipe_dirs = [ROOT / "recolors"] + [Path(f) for f in folders if Path(f).name != "characters"]
    for p in sorted({q for d in char_dirs for q in Path(d).glob("*.json")}):
        try:
            d = json.loads(p.read_text(encoding="utf8"))
            out[str(d["name"]).lower()] = int(str(d.get("id", "-1")), 0)
        except (OSError, ValueError, KeyError):
            continue
    for p in sorted({q for d in recipe_dirs for q in Path(d).glob("*.json")}):
        try:
            r = recolor.load_recipe(p)
            out[str(r["name"]).lower()] = int(str(r["id"]), 0) if "id" in r else None
        except Exception:
            continue
    try:
        import charpack
        have = charpack.list_imported(IMPORTED_DEST) if IMPORTED_DEST else charpack.list_imported_quiet()
        out.update({str(c["name"]).lower(): c.get("id") for c in have})
    except Exception:
        pass
    return out


def settings_in_build(characters, chars, recipes, dropped=None, folders=()):
    """The profile's "characters" settings without those for a new character or recolor this build leaves out
    (unticked, or not offered): they stay saved in the profile, only this build skips them (Nick's "wabluigi": he
    unticked his recolor and Patch stopped on its saved stats). Chemistry pairs naming one are skipped too. A name that
    is no character at all is still an error (character_keys). Returns (settings, notes)."""
    from sluggers_data import CHAR_NAMES
    in_build = {n.strip().lower() for n in CHAR_NAMES if n.strip()}
    in_build |= {str(d["name"]).lower() for d in list(chars) + list(recipes)}
    ids = {int(str(d["id"]), 0) for d in list(chars) + list(recipes) if d.get("id") is not None}
    known = known_characters(folders)
    known.update({k: None for k in (dropped or {})})
    absent = {n for n in known if n not in in_build}

    def is_absent(ref):
        r = str(ref).strip()
        if r.lower() in absent:
            return True
        if r.lower().startswith("0x"):
            try:
                cid = int(r, 0)
            except ValueError:
                return False
            return cid > 0x65 and cid not in ids and cid in set(known.values())
        return False
    out, left = {}, []
    for name, opts in characters.items():
        if is_absent(name):
            left.append(str(name))
            continue
        chem = opts.get("chemistry") if isinstance(opts, dict) else None
        if chem and any(is_absent(o) for o in chem):
            gone = [str(o) for o in chem if is_absent(o)]
            left += [f"{name}'s chemistry with {o}" for o in gone]
            opts = dict(opts, chemistry={o: v for o, v in chem.items() if not is_absent(o)})
        out[name] = opts
    notes = [f"saved settings for characters that aren't in this build, left out of it (they stay in your choices): "
             + ", ".join(left)] if left else []
    return out, notes


def character_keys(characters, chars, recipes, want=None, dropped=None):
    """Profile "characters" ({name or id: keys}, any character: stock, new or recolor). New characters get the keys
    written into their definitions (chars, in place); recolors' keys are returned for their definitions
    (make_recolors); stock characters become the build's stock entries {"id", "name", "stock": True, keys}.
    Returns (stock entries, {recolor name (lower case): keys})."""
    import charbuild
    from sluggers_data import CHAR_NAMES, char_id
    keys = set(charbuild.STOCK_KEYS) | {"stats"} | EDITOR_KEYS
    new = {}
    for d in chars:
        new[d["name"].lower()] = new[int(str(d["id"]), 0)] = d
    rec = {}
    for r in recipes:
        rec[r["name"].lower()] = rec[int(str(r["id"]), 0)] = r["name"]
    stock, recolor_keys = [], {}
    for name, opts in characters.items():
        ref = str(name).strip()
        cid = int(ref, 0) if ref.lower().startswith("0x") or ref.isdigit() else None
        bad = sorted(set(opts) - keys)
        if bad:
            sys.exit(f"characters: {name}: unknown keys {', '.join(bad)} (keys: {', '.join(sorted(keys))})")
        if cid is None:
            try:
                cid = char_id(ref)
            except KeyError:
                cid = None
        target = new.get(ref.lower() if cid is None or cid >= 0x65 else None) or new.get(cid)
        warned = []
        problems = check_character(name, opts, want, warnings=warned)
        for w in warned:                                # allowed past the game's limit, but said (Nick)
            print(f"warning: {w}")
        if opts.get("voice_clips") is not None:
            import voice_clips
            problems = list(problems) + voice_clips.check(opts["voice_clips"], name)
        if problems:
            sys.exit("characters: " + " ".join(problems))
        if opts.get("star swing") is not None:
            import custom_swings
            try:
                custom_swings.stats_of(opts["star swing"], cid)
            except (AssertionError, TypeError) as e:
                sys.exit(f"characters: {name}: {e}")
        if target is not None:
            set_keys(target, _definition_keys(opts))
        elif (ref.lower() if cid is None or cid >= 0x65 else None) in rec or (cid is not None and cid in rec):
            recolor_keys[(rec.get(ref.lower()) or rec[cid]).lower()] = _definition_keys(opts)
        elif cid is not None and 0 <= cid < 0x65:
            missing = sorted(k for k in set(opts) & EDITOR_KEYS - {"name"} if k not in charbuild.STOCK_KEYS)
            if missing:
                sys.exit(f"characters: changing a stock character's {' / '.join(missing)} isn't supported yet (coming "
                         f"soon); take it out for {name}")
            entry = _definition_keys(opts)
            if entry.pop("name", None) is not None:      # a stock character's new name (the build's "rename")
                entry.pop("names", None)
                entry["rename"] = opts["name"]
            chem = {}
            for other, v in (entry.pop("chemistry", None) or {}).items():   # a pair with a new character or recolor
                o = str(other).strip()                                       # goes in that character's definition
                oid = int(o, 0) if o.lower().startswith("0x") or o.isdigit() else None
                if oid is None:
                    try:
                        oid = char_id(o)
                    except KeyError:
                        oid = None
                if oid is not None and 0 <= oid < 0x65:
                    if v is not None:
                        chem[CHAR_NAMES[oid].strip()] = v
                elif (new.get(o.lower()) or new.get(oid)) is not None:
                    set_keys(new.get(o.lower()) or new.get(oid), {"chemistry": {CHAR_NAMES[cid].strip(): v}})
                elif o.lower() in rec or oid in rec:
                    rk = recolor_keys.setdefault((rec.get(o.lower()) or rec[oid]).lower(), {})
                    rk.setdefault("chemistry", {})[CHAR_NAMES[cid].strip()] = v
                elif o.lower() in (dropped or {}):
                    sys.exit(f"characters: {name}: chemistry with {other!r}: {dropped[o.lower()]}")
                else:
                    sys.exit(f"characters: {name}: chemistry with {other!r}, who isn't a stock character or one of "
                             f"the profile's new characters or recolors")
            if chem:
                entry["chemistry"] = chem
            stock.append({"id": cid, "name": CHAR_NAMES[cid].strip(), "stock": True,
                          **{k: v for k, v in entry.items() if v is not None}})
        elif ref.lower() in (dropped or {}):
            sys.exit(f"characters: {dropped[ref.lower()]}")
        else:
            import difflib
            names = [n.strip() for n in CHAR_NAMES if n.strip()] + [d["name"] for d in chars] + \
                [r["name"] for r in recipes]
            near = difflib.get_close_matches(ref, names, n=3, cutoff=0.5)
            sys.exit(f"characters: {name!r} isn't a stock character or one of the profile's new characters or "
                     f"recolors" + (f"; did you mean {', '.join(near)}?" if near else ""))
    return stock, recolor_keys


MADE = ("recolor/", "sounds/clean/")      # DERIVED folders the patcher makes from the player's game; the rest are copied


def copied_derived():
    """The models/work files make_work copies into the work folder (DERIVED less MADE)."""
    import charbuild
    return sorted(p for prefix in charbuild.DERIVED if prefix not in MADE
                  for p in (ROOT / "models/work" / prefix).rglob("*") if p.is_file())


def renamed_new(characters, chars):
    """{original name (lower case): new name} for the new characters, recolors and imports the profile's "characters"
    block renames: the window's other tabs (Select grid, Captains) keep naming them by their original name."""
    out = {}
    names = {d["name"].lower(): d["name"] for d in chars}
    for key, opts in (characters or {}).items():
        nm = opts.get("name") if isinstance(opts, dict) else None
        new = (nm.get("en") or next(iter(nm.values()), None)) if isinstance(nm, dict) else nm
        if new and str(key).lower() != new.lower() and new.lower() in names:
            out[str(key).lower()] = names[new.lower()]
    return out


def rename_refs(value, names):
    """An option naming characters (grid-order, captains) with renamed characters' original names swapped for the new
    ones: every string, list item and dict key equal to an original name (any case)."""
    if isinstance(value, str):
        return names.get(value.lower(), value)
    if isinstance(value, list):
        return [rename_refs(v, names) for v in value]
    if isinstance(value, dict):
        return {rename_refs(k, names): rename_refs(v, names) for k, v in value.items()}
    return value


def make_work(game, work, imported=(), items=(), swings=(), pitches=(), voices=None):
    """The build's work folder (build(work=), charbuild.DERIVED: the files made from the game): the voices made from
    the player's MY2.brsar (build_voices.build_for_game, our clips pre-encoded), the recolors by make_recolors, the
    rest copied from models/work, which in the download unpack_assets rebuilt from the player's game."""
    import build_voices, charbuild
    build_voices.build_for_game(work, game, extra={d["voice"]: {"dir": d["voice_dir"], "template": d["template"],
                                                                **({"stock": d["voice_stock"]} if d.get("voice_stock")
                                                                   else {}),
                                                                **({"family_sound": d["voice_family"]}
                                                                   if d.get("voice_family") else {})}
                                                   for d in imported if d.get("voice_dir")} or None,
                                item_clips=[{"name": c["name"], "event": ev, "wav": c["blocks"]["sound"][ev + "_clip"]}
                                            for c in items for ev in ("launch", "hit", "land")
                                            if (c["blocks"].get("sound") or {}).get(ev + "_clip")]
                                + move_clips(swings, pitches) or None, only=voices)
    for prefix in charbuild.DERIVED:
        src = ROOT / "models/work" / prefix
        if prefix not in MADE and src.is_dir():
            shutil.copytree(src, Path(work) / prefix, dirs_exist_ok=True)


def move_clips(swings=(), pitches=()):
    """Star swing / pitch creations' own cut-in clips for build_voices (creators.cutin_sounds.clips: "swing:<name>" /
    "pitch:<name>", events "cutin0"..; their ids come back in voice_tables.json "items")."""
    if not swings and not pitches:                  # (none: the creators aren't loaded)
        return []
    from creators import cutin_sounds
    return cutin_sounds.clips("swing", swings) + cutin_sounds.clips("pitch", pitches)


def make_recolors(recipes, game, chars, work, keys=None):
    """Each recipe made from the player's game into `work`; returns their definitions, with the profile's
    per-character keys for them ({recolor name (lower case): keys}) applied."""
    if not recipes:
        return []
    import recolor
    g = recolor.Game(str(game))
    defs = {int(str(d["id"]), 0): (None, d) for d in chars}
    out = []
    for p in recipes:
        print(f"== Recoloring {recolor.load_recipe(p)['name']}")
        for line in recolor.make(str(p), g, work=work, defs=defs):
            print("recolor: " + line)
        r = recolor.load_recipe(p)
        made = Path(work) / "characters" / f"0x{int(str(r['id']), 0):02x}_{recolor.slug(r['name']).replace('-', '_')}.json"
        d = json.loads(made.read_text(encoding="utf8"))
        defs[int(str(d["id"]), 0)] = (made.name, d)
        set_keys(d, (keys or {}).get(d["name"].lower(), {}))
        out.append(d)
    return out


UNBUILT = {}        # {asset rel: the modded files it copies from}: unpack_assets couldn't rebuild it from this game


def unpack_assets(game):
    """The download's files that ship as deltas (package.py, delta.py) rebuilt from the player's game, once. On a
    game with model / texture mods (modded_game) a delta that copies bytes the mod changed can't be rebuilt: it's
    left out (UNBUILT; an older copy removed, so it never stands in) and the patch stops only if the build reads it
    (unbuilt_stop). The deltas copy runs of 32+ bytes from anywhere in the game, but a mod rarely changes the very
    runs they copy (Summer Kong: every Patcher 12 asset still rebuilt). Once rebuilt (from a clean game or not) they're
    kept, so a later modded game never needs them again."""
    UNBUILT.clear()
    if not ASSETS.exists():
        return
    import delta, mmap
    todo = {}
    for rel, a in json.loads(ASSETS.read_text(encoding="utf8")).items():
        if a["delta"] and not ((ROOT / rel).exists() and sha1(ROOT / rel) == a["sha1"]):
            todo[rel] = a
    if not todo:
        return
    print(f"== Rebuilding {len(todo)} files from your game (first run only)")
    files = [open(game / rel, "rb") for rel in delta.SOURCES]
    try:
        sources = [mmap.mmap(f.fileno(), 0, access=mmap.ACCESS_READ) for f in files]
        for rel in todo:
            d = (ROOT / (rel + ".slgd")).read_bytes()
            try:
                data = delta.apply(d, sources)
            except ValueError:
                import modded_game
                entries = modded_game.changed(game)
                if not entries:             # the clean game: the download is damaged
                    raise
                (ROOT / rel).unlink(missing_ok=True)
                UNBUILT[rel] = modded_game.names(modded_game.conflicts(d, entries, game))
                continue
            (ROOT / rel).parent.mkdir(parents=True, exist_ok=True)
            (ROOT / rel).write_bytes(data)
        for m in sources:
            m.close()
    finally:
        for f in files:
            f.close()


def unbuilt_stop(e):
    """A FileNotFoundError for one of UNBUILT's files (or make_work's copy of it): stop, saying which of the mod's
    changes it needed. Anything else: re-raised."""
    got = str(Path(e.filename or "")).replace("\\", "/").lower()
    for rel, mods in UNBUILT.items():
        tail = rel.removeprefix("models/work/").lower()
        if got.endswith("/" + tail):
            sys.exit(f"this patch needs {rel}, which is made from parts of your game that your model or texture mod "
                     f"changed ({', '.join(mods)}). Patch a clean copy of the game once (the rebuilt file is kept, "
                     f"and then modded games work too), or leave out the character or feature that uses it.")
    raise e


def imported_list(value):
    """The profile's "imported" packs as [{"id", "name"}] (charpack.list_imported), [] when absent."""
    if not value:
        return []
    import charpack
    have = charpack.list_imported(IMPORTED_DEST) if IMPORTED_DEST else charpack.list_imported_quiet()
    if value is True:
        return [{"id": h["id"], "name": h["name"]} for h in have]
    names = {h["name"].lower(): h for h in have}
    missing = [n for n in value if str(n).lower() not in names]
    if missing:
        sys.exit(f"imported: no imported character called {', '.join(map(str, missing))} (imported: "
                 f"{', '.join(h['name'] for h in have) or 'none'})")
    return [{"id": names[str(n).lower()]["id"], "name": names[str(n).lower()]["name"]} for n in value]


def make_imported(value, game, work, chars, keys):
    """The profile's imported character packs as definitions made from the player's game (charpack.materialize), with
    the profile's per-character keys for them applied."""
    import charpack
    wanted = {i["name"].lower() for i in imported_list(value)}
    defs = charpack.materialize(IMPORTED_DEST or charpack.default_dest(), game, work,
                                taken_ids=[int(str(d["id"]), 0) for d in chars], taken_names=[d["name"] for d in chars])
    out = []
    for d in defs:
        original = d["name"]
        if value is not True and original.lower() not in wanted and not any(
                original.lower().startswith(w) for w in wanted):
            continue
        print(f"== Adding {d['name']} (imported)" + (f": {d.pop('_note')}" if d.get("_note") else ""))
        set_keys(d, keys.get(d["name"].lower(), {}))
        out.append(d)
    return out


def stadium_source(value):
    """A profile's "stadium": a .slgstadium path (relative to the patcher folder, or absolute) or a preset name."""
    p = Path(value)
    for cand in (p, ROOT / p):
        if cand.is_file():
            return cand
    return value


def resolve(profile, reg):
    want = set(profile.get("features", []))
    for f in sorted(want & set(NOT_OFFERED)):
        sys.exit(f"features: {NOT_OFFERED[f]}")
    unknown = sorted(want - set(reg))
    if unknown:
        sys.exit("unknown features: " + ", ".join(unknown) + " (python scripts/patcher/patch.py --list)")
    missing = sorted({f"{f} needs {r}" for f in want for r in reg[f]["requires"] if r not in want})
    if missing:
        sys.exit("missing dependencies: " + "; ".join(missing))
    return want


def check_memory(folder):
    """git-95's heap estimate for the patched game at a batter change (Nick's hazards-1 crash): prints the progress
    line and returns the warning sentence ("" when the game has room)."""
    import heap_budget
    free_kb, ok, sentence = heap_budget.check(folder)
    print(f"== Checking memory: about {free_kb} KB free at a batter change")
    return "" if ok else sentence


def details_dir(iso):
    """Where run() puts an ISO's log.txt, choices.json and relocations.json: "<name> (patch details)" beside it."""
    import gecko_fix
    return gecko_fix.details_dir(iso)


def iso_path(iso):
    """The output ISO's path, always ending in .iso (Nick typed "newitem" and got a file with no extension)."""
    iso = Path(iso)
    return iso if iso.suffix.lower() == ".iso" else iso.with_name(iso.name + ".iso")


# a build line an edition never shows, besides the ones naming a feature or character it doesn't offer (edition_quiet)
QUIET = ("left out", "not in this build", "feature off", "full patcher", "coming soon", "coming later",
         "cut-in backdrop", "clamber jump", "batter star", "chance cheer", "star pitch", "star swing", "item code",
         "pauline chance", "zzpauline_chance", "items", "stadium", "hazard", "captains",
         # the game options' technical lines (the build's plain ones follow them: "start at captain select",
         # "start in a game", "CPU vs CPU", "menu background color")
         "quick boot", "confirmed draft", "rebuilt with the background")


def edition_quiet():
    """In an edition (Nick: "NO REFERENCES TO FUTURE FEATURES"): keep(line) -> the line to print, or None. Lines about
    what the build leaves out, and any naming a feature or a character / recolor the edition doesn't offer, aren't
    shown or logged; "features: n of m (off: ...)" keeps only its count. The full patcher: None (every line)."""
    import edition
    ed = edition.load()
    if not ed:
        return None
    words = edition.unoffered_words(ed) + list(QUIET)      # the same words the release gate checks
    if "clamber-solo-jump" in ed.get("features", ()):       # offered (the beta's Fielding list): its build line shows
        words.remove("clamber jump")
    if "captains" in ed.get("features", ()):                # offered (the beta page's Captains): its lines show
        words = [w for w in words if w.lower() != "captains"]
    bad = re.compile(r"(?<![\w-])(" + "|".join(re.escape(w) for w in sorted(set(words), key=len, reverse=True)) +
                     r")(?![\w-])", re.I)

    def keep(line):
        if line.startswith("note: "):               # check_profile's: in an edition only the player's own
            return line
        if line.startswith("features: "):
            return line.split(" of ", 1)[0].split(" (off:", 1)[0]
        test = line                                 # a character in this build is the player's to see, even named
        for n in sorted(BUILD_NAMES, key=len, reverse=True):   # like one of ours the edition leaves out (their
            test = re.sub(r"(?<![\w-])" + re.escape(n) + r"(?![\w-])", "", test, flags=re.I)   # own Dry Bowser)
        return None if bad.search(test) else line
    return keep


BUILD_NAMES = set()     # this build's characters' names (_run_build, once they're known): edition_quiet shows them


class _Quiet:
    """sys.stdout through an edition's keep(line): whole lines only."""

    def __init__(self, stream, keep):
        self.stream, self.keep, self.part = stream, keep, ""

    def write(self, text):
        *lines, self.part = (self.part + text).split("\n")
        for line in lines:
            kept = self.keep(line)
            if kept is not None:
                self.stream.write(kept + "\n")
        return len(text)

    def flush(self):
        self.stream.flush()


class _Tee:
    """sys.stdout that also goes to a log file."""

    def __init__(self, stream, log):
        self.stream, self.log = stream, log

    def write(self, text):
        self.log.write(text)
        return self.stream.write(text)

    def flush(self):
        self.log.flush()
        self.stream.flush()


def run(game, profile_path, out=None, iso=None, dry_run=False):
    """Patch `game` (extracted folder or .iso) with the profile. out: the patched folder (default: a temporary one
    next to the game, removed once the ISO is written); iso: also write it as an ISO; only the ISO
    goes there, the rest into details_dir(iso), "<name> (patch details)" beside it (Nick opened the old side-by-side
    <name>.relocations.json in Dolphin: with extensions hidden they all looked like the ISO): choices.json and log.txt
    (what was picked and everything the patcher said, also when it stops), and once it's written relocations.json (what
    the build moved and changed: gecko_fix.py fixes the player's Gecko codes with it)."""
    if out is None and iso is None and not dry_run:
        sys.exit("give an output folder or an ISO to write")
    if not iso or dry_run:
        return _run(game, profile_path, out, iso, dry_run)
    iso = iso_path(iso)
    if iso.exists():
        sys.exit(f"{iso} already exists: pick a new name (the patcher never writes over a file)")
    details = details_dir(iso)
    details.mkdir(parents=True, exist_ok=True)
    shutil.copyfile(profile_path, details / "choices.json")
    for key, name in (("stadium", "stadium.slgstadium"), ("stadium_2", "stadium 2.slgstadium")):  # a shared ISO's
        stadium = json.loads(Path(profile_path).read_text(encoding="utf8")).get(key)            # setup can be rebuilt
        if stadium and isinstance(stadium_source(stadium), Path):
            shutil.copyfile(stadium_source(stadium), details / name)
    with open(details / "log.txt", "w", encoding="utf8") as log:
        log.write(f"game: {game}\nprofile: {profile_path}\niso: {iso}\n\n")
        stdout, sys.stdout = sys.stdout, _Tee(sys.stdout, log)
        try:
            return _run(game, profile_path, out, iso, dry_run)
        except SystemExit as e:
            if e.code not in (None, 0):
                log.write(f"\nstopped: {e.code}\n")
            raise
        except BaseException:
            import traceback
            log.write("\n" + traceback.format_exc())
            raise
        finally:
            sys.stdout = stdout


def _run(game, profile_path, out, iso, dry_run):
    BUILD_NAMES.clear()                         # (this build's, once they're known: _run_build)
    keep = edition_quiet()
    if keep is None:
        return _run_build(game, profile_path, out, iso, dry_run)
    was = sys.stdout
    sys.stdout = _Quiet(was, keep)
    try:
        return _run_build(game, profile_path, out, iso, dry_run)
    finally:
        if sys.stdout.part:
            sys.stdout.write("\n")
        sys.stdout = was


def _run_build(game, profile_path, out, iso, dry_run):
    reg = registry()
    profile = json.loads(Path(profile_path).read_text(encoding="utf8"))
    want, options, stock, chars, recipes, notes, recolor_keys = check_profile(profile, reg)
    profile = edition_follow(edition_trim(profile)[0])   # what this edition builds (check_profile noted drops)
    import charbuild
    supports = getattr(charbuild, "SUPPORTS", set())      # what the build can do beyond today's (git-ea)
    renamed = [e["name"] for e in stock if e.get("rename")]
    if renamed and ("new-ids" not in want or not (chars or recipes or profile.get("imported"))):
        sys.exit("renaming a stock character needs at least one new character or recolor for now (the names are "
                 "built with them): tick one on New characters & recolors")
    if stock and "stock" not in supports:
        sys.exit("options on stock characters aren't supported yet (coming soon); take them out of \"characters\"")
    if not (chars or recipes) and "no-new-characters" not in supports:
        sys.exit("a patch with no new characters isn't supported yet (coming soon); pick at least one new character "
                 "or recolor")
    left_out = sorted(f for f in want if reg[f]["switch"] == "not in the patched game")
    if left_out:
        notes.append("test switches, not in a patched game: " + ", ".join(left_out))
    want -= set(left_out)
    import char_names                  # the Toad Brigade's names only with its feature, as the build does (git-92)
    char_names.TOADS = "toad-brigade" in want
    if out is not None and Path(out).exists() and not dry_run:
        sys.exit(f"{out} exists: the patcher only writes a new folder")
    temps = []
    try:
        print("== Checking your game")
        game = game_folder(game)
        import modded_game
        modded = modded_game.changed(game)          # (game_folder's result: not hashed again)
        if modded:                                  # the player's model / texture mods: built on as they are
            print("== Your game has model or texture mods: the patched game keeps them")
            print("note: kept from your game (modded): " + ", ".join(modded_game.names(modded)))
        unpack_assets(game)
        kw = dict(options, features=want, game=game)
        if profile.get("char_defaults") is False:   # a profile-only roster: no built-in character defaults
            kw["char_defaults"] = False
        for n in notes:
            print("note: " + n)
        if out is None:     # beside the game: the build hard-links the game's files, so it has to be the same drive
            out = Path(tempfile.mkdtemp(prefix=".sluggers-build-", dir=game.parent)) / "game"
            temps.append(out.parent)
        work = Path(tempfile.mkdtemp(prefix="sluggers-work-"))
        temps.append(work)
        if profile.get("stadium") or profile.get("stadium_2"):
            from creators import stadium as st
            print("== Reading the stadium" + ("s" if profile.get("stadium_2") else ""))
            try:
                first = (Path(st.definition_file(stadium_source(profile["stadium"]), work / "stadium"))
                         if profile.get("stadium") else ROOT / "stadiums/stadium10.json")   # the build's default
                kw["stadium"] = first
                if profile.get("stadium_2"):                                            # id 11 (git-64)
                    kw["stadium"] = [first, Path(st.definition_file(stadium_source(profile["stadium_2"]),
                                                                   work / "stadium_2"))]
                loaded = [st.load(stadium_source(profile[k]), unpack=work / f"{k}-notes")
                          for k in ("stadium", "stadium_2") if profile.get(k)]
                for n in st.hazard_notes(loaded, kw.get("hazards") or []):   # a hazard creation with nowhere to go
                    print("note: " + n)
            except st.Invalid as e:
                sys.exit(str(e))
        if profile.get("select_map") is not None:     # applied after a .slgstadium's own map block, so it wins
            import stadium_map
            kw["select_map"] = stadium_map.prepare(profile["select_map"], work)
        imported = make_imported(profile["imported"], game, work, chars, recolor_keys) if profile.get("imported") else []
        chars += imported                        # before the recolors: a recolor can be of an imported character
        chars += make_recolors(recipes, game, chars, work, recolor_keys)   # (its base found in chars, git-a3)
        BUILD_NAMES.clear()                     # (an edition's log shows them: edition_quiet)
        BUILD_NAMES.update(c["name"] for c in chars if not c.get("stock") and c.get("name"))
        for n in modded_game.build_notes(chars, recipes, modded, toads="toad-brigade" in want):
            print("note: " + n)
        print("== Making the voices")
        import edition                        # an edition: only its characters' voice sets (a lean download)
        import voice_clips                    # the player's own clips (the Voice page): sets of their own
        voiced, voice_notes = voice_clips.prepare(chars, game, work)
        for n in voice_notes:
            print("note: " + n)
        if voiced and "voices" not in want:
            print("note: your characters' own voice clips need Voices, which isn't ticked: they keep their voices")
            voiced = []
            for c in chars:                   # (their "voice" / "voice_dir" set by prepare would be routed anyway)
                if str(c.get("voice", "")).startswith("pv"):
                    c.pop("voice", None), c.pop("voice_dir", None), c.pop("voice_stock", None)
        voices = {c["voice"] for c in chars if c.get("voice")} if edition.load() else None
        make_work(game, work, list(imported) + [d for d in voiced if d not in imported], kw.get("items") or (), kw.get("swings") or (), kw.get("pitches") or (),
                  voices)   # after the imports: their voice sets go in
        kw["work"] = work
        names = renamed_new(profile.get("characters"), chars)
        for arg in ("grid_order", "captains_option", "boot_game"):   # these name characters as the window
            if names and kw.get(arg) is not None:       # shows them: originals
                kw[arg] = rename_refs(kw[arg], names)
        if kw.get("grid_order") is not None:         # the whole roster again (git-d9)
            import grid_order
            from dol import Dol
            problems = grid_order.validate(kw["grid_order"], Dol(Path(game) / "sys/main.dol"), stock + chars)
            if problems:
                sys.exit("select grid: " + " ".join(problems))
        if kw.get("captains_option") is not None:    # needs the whole roster, so checked once the recolors exist
            import captains
            defaults = profile.get("char_defaults") is not False
            problems = captains.check(kw["captains_option"], stock + chars, defaults=defaults)
            if problems:
                sys.exit("captains: " + " ".join(problems))
            for n in captains.notes(kw["captains_option"], stock + chars, defaults=defaults):
                print("note: " + n)
        print(f"== Building: {len(chars) - len(recipes)} new characters, {len(recipes)} recolors, {len(stock)} stock "
              f"characters changed, {len(want)} features")
        try:
            for line in charbuild.build(stock + chars, out, dry_run=dry_run, **kw):
                print(line)
            warning = "" if dry_run else check_memory(out)
        except (AssertionError, ValueError) as e:     # a combination the build can't make: say so, not a traceback
            sys.exit(f"the build stopped: {e}. Try it with fewer changes, and send us log.txt from the "
                     f"\"(patch details)\" folder next to your ISO.")
        if iso and not dry_run:
            if not WIT:
                sys.exit("writing an ISO needs wit, which should be in tools/wit next to the patcher")
            print("== Writing the ISO")
            subprocess.run([str(WIT), "copy", str(out), str(iso)], check=True)
            if charbuild.LAST_GECKO_MAP:            # what moved, for the player's Gecko codes (gecko_fix.py)
                details_dir(iso).mkdir(parents=True, exist_ok=True)
                (details_dir(iso) / "relocations.json").write_text(json.dumps(charbuild.LAST_GECKO_MAP),
                                                                   encoding="utf8")
            print(f"== Done: {iso}")
        if not dry_run and warning:                  # last, so it's what the player reads (git-95, git-92)
            print(f"== WARNING: {warning}")
    except FileNotFoundError as e:                  # a file unpack_assets couldn't rebuild from a modded game
        unbuilt_stop(e)
    finally:
        for t in temps:
            shutil.rmtree(t, ignore_errors=True)


def main():
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("--game")
    ap.add_argument("--profile")
    ap.add_argument("--out")
    ap.add_argument("--iso")
    ap.add_argument("--list", action="store_true")
    ap.add_argument("--dry-run", action="store_true", help="run every build step and write nothing")
    ap.add_argument("--modder-files", metavar="FOLDER",
                    help="with --game: write the modder files (Dolphin symbol map, Ghidra names) into FOLDER")
    args = ap.parse_args()
    if args.modder_files:
        if not args.game:
            ap.error("--modder-files needs --game")
        import modder_files
        modder_files.write(args.game, args.modder_files)
        return
    if args.list:
        for i, r in registry().items():
            print(f"{i:22s} {r['switch']:22s} needs: {', '.join(r['requires']) or '-'}")
        return
    if not (args.game and args.profile and (args.out or args.iso or args.dry_run)):
        ap.error("--game, --profile and --out or --iso are required (or --list)")
    run(args.game, args.profile, args.out, args.iso, args.dry_run)


if __name__ == "__main__":
    main()
