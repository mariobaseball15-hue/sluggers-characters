"""The Characters Beta's Items window (the page's "Items..." button, beta_window.py): the item features the full
patcher has on its Features and Create tabs, in one window with Save at the bottom right (like game_options.py's):
  Roulette odds          how often each item comes up: the game's six, the Ice ball when it's in, our six ready-made
                         items (koopaling-items, ids 8-13: 0 by default, named by what they are: the beta has no
                         Koopalings), Star Bits (0 by default: the edition's never_rolled, unless given odds), and each of the player's own items (their creation's "Who gets it" weights)
  Item speed and flight  the Ice ball's, our ready-made six's and the player's own thrown items' speed and flight (an
                         arc, level, skimming along the ground, bouncing; homing for one-ball items); the rings' speed
                         (how fast they wander); and each thrown ball's / Shell's knockback (the knocked-down fielder's
                         slide: its speed, +0x130, and frames, +0x206: the item's effect block, slide_speed and
                         slide_frames); Reset puts one of ours back; the game's six keep theirs (their knockdown is the
                         game's shared one: new code). Star Bits: a row with Reset only (nothing of those to set)
  Item variants          the Ice ball (item-variants: a Fireball variant with blue balls that freezes)
  Make your own items    the Create tab's Items page itself (item_page.ItemPage, embedded: the same editor)
Only what the edition offers (editions/*.json "features" and "creators"); no "i"s or How tos (its no_help).

Where it's kept: the odds in the App's item-odds boxes (app.odds, the hidden Features tab's), the Ice ball as
item-variants with the Ice odds not "0", the player's items as the used creations of ItemsPart (the profile part the
beta has in place of the hidden Create tab; a hidden ItemPage, which the character window's Brings list also reads).
A speed or flight change of the Ice ball is an edit of our Ice (a creation named "Ice" in the player's creations
folder, creators.items.preset_of); of the player's own item, its file. The item engine (item-engine) that the
player's items and the Ice edit need brings the Ice ball's code with it, and Star Bits' (the edition's
"never_rolled": patch.edition_items keeps them out of the roulette); when the Ice ball isn't picked, its odds are 0.
Our ready-made items (koopaling-items) switch on only when one is given odds above 0 here or is a character's item
(Brings); a "0" is their default and is kept as an empty box. Each can be edited like the Ice ball: its speed and
flight here, or all its blocks on Make your own items (listed by what it is; Save as copy keeps it as the player's
version, named after the item, e.g. "Bullet Bill.slgitem" in the creations folder: edit_path). creators.items.preset_of
knows that name (ITEM_NAMES), so the build puts it in place of ours (same id, same roulette slot). It's in the game
(the part's used set: reconcile) only while its item is (odds above 0, a character brings it, or its own roulette
weights), so a version of an item nobody gets adds nothing; Reset (or deleting the file) puts ours back. Their models (models/work/ring, lemmy_ball; the Bullet
Bill cut from the player's game) and icons (drawn, or the Fireball's / POW's recoloured) are the item steps' own:
nothing comes from a Koopaling character.
Star Bits (Rosalina's) is ours the same way (OURS): an odds row (0 by default), on every character's Brings list, and
editable on Make your own items as "Star Bits.slgitem"; its version is in the game while Star Bits are (odds above 0, or
a character brings them: Rosalina by default).
sync(app) ticks exactly the item features the window's and the characters' picks need (the character window calls
it too), so an untouched profile has none of them.
"""
import json
import tkinter as tk
import style
from pathlib import Path
from tkinter import ttk

import fit
import widgets

TITLE = "Items"
STOCK = ("shell", "fireball", "bobomb", "pow", "banana", "boo")      # batter_items.NAMES' first six
ICE = "ice"
ICE_PRESET = "ice"                                                   # creators.items.PRESET_IDS
KOOPA = ("lemmy", "bill", "iggy", "larry", "wendy", "ludwig")        # batter_items.KOOPA_NAMES, ids 8..13
KOOPA_FEATURE = "koopaling-items"
# their names in the beta, by what they are (it has no Koopalings; gui.ITEM_TITLES names them by their owners)
TITLES = {"lemmy": "Bouncing circus balls", "bill": "Bullet Bill", "iggy": "Fast green fireball",
          "larry": "Fast cyan fireball", "wendy": "Hopping rings", "ludwig": "Five fireballs"}
STEMS = {"lemmy": "lemmy", "bill": "bullet-bill", "iggy": "iggy", "larry": "larry", "wendy": "wendy",
         "ludwig": "ludwig"}                # their presets (creators.items.PRESET_IDS; ITEM_NAMES: TITLES by preset)
STARBITS = "starbits"                       # Star Bits (id 6, Rosalina's): ours like the six (Nick: where are Star
OURS = KOOPA + (STARBITS,)                  # Bits?), in the game through new-roulette-item, not koopaling-items
NAMES = {**TITLES, STARBITS: "Star Bits"}
WINDOW = (860, 620)                         # the window's size (Nick's screen): above Save it scrolls
VIEW_MIN = 160                              # the scrolled part asks for this much: the window gives it the rest
PAGE_MIN = 380                              # Make your own items never shorter (its list and block editor)
WHEEL_TAG = "ItemsWindowWheel"
SELF_WHEEL = ("Listbox", "TCombobox", "Text", "Scrollbar", "TScrollbar")    # these keep their own wheel
STEM_OF = {**STEMS, STARBITS: "star-bits"}
# what an edit of each can't change (creators.items.customs' limits for them), said on Make your own items
CANT = {"lemmy": "The circus-ball model keeps its own size and height, and dresses at most 3 balls.",
        "bill": "The Bullet Bill model keeps its own size and height, and is one ball.",
        "iggy": "", "larry": "", "ludwig": "",
        "wendy": "How it's thrown can't change (a POW-style lob). The rings stay until the half-inning ends, trip "
                 "fielders up and don't hit runners; 1 to 12 of them.",
        STARBITS: "How it's thrown can't change (a POW-style lob). It leaves 4 star bits where it lands, which trip "
                  "fielders up and don't hit runners."}
# the item features the window and the character window switch (with what they need)
SWITCHES = ("item-odds", "new-roulette-item", "item-variants", "item-engine", "fixed-items", "item-ability",
            KOOPA_FEATURE)
ODDS_NOTE = ("Higher comes up more often; 0 takes an item out of the roulette. Leave a box empty to keep the game's "
             "odds. Three numbers like 20/15/15 set separate odds by score difference, as the game does.")
FLIGHT_NOTE = ("Speed is times the game's Fireball (the rings: times ours). Knockback: how fast a fielder the item "
               "knocks down slides away (0 to 3; 0.3 is the game's) and for how many frames (0 to 120, 60 a second); "
               "empty: it doesn't knock down (it stuns or freezes), fill both to make it knock down. Reset puts ours "
               "back. The game's six keep their speed and knockback: the Shell's and the Bob-omb's knockdown is the "
               "game's own, shared, and changing it needs new code.")
KNOCK_SPEED, KNOCK_FRAMES = (0.0, 3.0), (0, 120)   # creators/blocks.py effect.slide_speed / slide_frames
STOCK_KNOCK = (0.3, 40)                     # the game's own knockdown slide (FUN_80128b48; koopa_items): a Shell's
STARBITS_TEXT = "leaves 4 star bits: no speed or knockback (change it under Make your own items)"
RINGS_TEXT = "how fast the rings wander (they stay until the half-inning ends)"
KOOPA_NOTE = ("The circus balls, Bullet Bill and fireballs come up only while the Fireballs are on in the game's item "
              "settings, the rings only while the POW is.")
ICE_TEXT = "Ice ball: a Fireball with blue balls that freezes the fielder it hits, in the roulette with the others"
# a thrown ball's flight: (label, launch values, move block)
FLIGHTS = [("An arc, as thrown", {"level": False, "gravity": None}, {"path": "straight"}),
           ("Level, no drop", {"level": True, "gravity": 0.0}, {"path": "straight"}),
           ("Skims along the ground", {"level": True, "gravity": 0.1}, {"path": "skim"}),
           ("Bounces", {"level": False, "gravity": None}, {"path": "bounce", "bounce": {"factor": 0.8,
                                                                                       "min_hop": 0.35}})]
HOME = ("Homes in on a fielder", {"level": True, "gravity": 0.0},
        {"path": "home", "home": {"turn_deg": 1.5, "spawn_dist": 60.0}})   # the Bullet Bill's (bullet_bill TURN_DEG,
#                                                                            SPAWN_DIST); one-ball items only
OWN_FLIGHT = "Its own (set below)"          # a flight the list doesn't name (its own gravity, bounce): left as it is
SPEED = (0.5, 3.0)                          # creators/blocks.py launch.speed


def offered(app):
    """The edition's item features (the registry: the edition's)."""
    return {f for f in SWITCHES if f in app.reg}


def has_items(app):
    """Whether this window has anything to show (the Items... button)."""
    return bool({"item-odds", "item-variants", "item-engine"} & offered(app))


def part(app):
    return next((pt for pt in getattr(app, "parts", []) if isinstance(pt, ItemsPart)), None)


def offer_preset(stem):
    """Ours on the beta's item list: the Ice ball, our ready-made six listed by what they are (TITLES), and Star
    Bits."""
    return stem == ICE_PRESET or next((NAMES[n] for n, st in STEM_OF.items() if st == stem), False)


def ours_offered(app):
    """Ours (OURS) this edition has: the six with koopaling-items, Star Bits with new-roulette-item."""
    reg = getattr(app, "reg", {})
    return (KOOPA if KOOPA_FEATURE in reg else ()) + ((STARBITS,) if "new-roulette-item" in reg else ())


def offer_for(app):
    """offer_preset, less what the edition hasn't (ours_offered)."""
    have = {STEM_OF[n] for n in ours_offered(app)}
    return lambda stem: (stem == ICE_PRESET or stem in have) and offer_preset(stem)


def edit_path(folder, n):
    """Where the player's version of our item n goes: <folder>/<its name>.slgitem (e.g. Bullet Bill, Star Bits)."""
    return Path(folder) / f"{NAMES[n]}.slgitem"


def ours_copy(n):
    """Our item n as the player's version: its preset, named by what it is, from that preset."""
    import creators.items as it
    c = json.loads(json.dumps(it.preset(STEM_OF[n])))
    c.update(name=NAMES[n], **{"from": STEM_OF[n]})
    return c


def koopa_edit(folder, n):
    """The player's version of item n (edit_path: an item creation named after it, which edits it), or None."""
    path = edit_path(folder, n)
    if not path.is_file():
        return None
    import creators.items as it
    from creators import blocks
    try:
        c = json.loads(path.read_text(encoding="utf8"))
    except (OSError, ValueError):
        return None
    if not isinstance(c, dict) or c.get("kind") != "item" or not isinstance(c.get("name"), str) \
            or it.preset_of(c["name"]) != STEM_OF[n] or blocks.problems(c):
        return None
    return c


def char_items(app):
    """[(name, key, value)]: the App's character settings (char_settings), and the new characters' own batting item,
    "always" and card label (their definitions: Rosalina's Star Bits, the Koopalings' items) where no setting here
    replaces them."""
    out = list(app.char_settings())
    have = {(n, k) for n, k, _ in out}
    for name, kind, d, _ in app.roster():
        if kind in ("new", "imported"):
            out += [(name, k, d[k]) for k in ("batting_item", "always_item", "item_ability")
                    if (name, k) not in have and d.get(k) not in (None, False, "", "none")]
    return out


def chosen(app):
    """Our items in the game: odds above 0 (the App's boxes), a character brings it (a setting, or a new character's
    definition: Rosalina's Star Bits), or the player's version of one of the six has roulette weights of its own
    (Star Bits' own are the preset's 15s, which the edition never rolls: its odds decide)."""
    out = set(koopa_odds(app, OURS))
    out |= {v for _, key, v in app.char_settings() if key == "batting_item" and v in OURS}
    settings = getattr(app, "settings", {})
    for name, _, d, _ in (app.roster() if hasattr(app, "roster") else ()):
        v = (settings.get(name) or {}).get("batting_item", d.get("batting_item") if isinstance(d, dict) else None)
        if v in OURS:
            out.add(v)
    pt = part(app)
    for n in KOOPA if pt is not None else ():
        c = koopa_edit(pt.items.folder, n)
        if c and any((c["blocks"].get("given") or {}).get("roulette") or [0]):
            out.add(n)
    return out


def reconcile(app, picked=None):
    """The player's versions of our ready-made items in the game (the part's used set) exactly while their item is
    (chosen) and their file is there."""
    import creation_editor as ce
    pt = part(app)
    if pt is None or not ours_offered(app):
        return
    picked = chosen(app) if picked is None else picked
    for n in ours_offered(app):
        key = ce.rel(edit_path(pt.items.folder, n))
        if n in picked and koopa_edit(pt.items.folder, n) is not None:
            pt.items.used.add(key)
        else:
            pt.items.used.discard(key)


def title(name):
    import gui
    return TITLES.get(name) or gui.ITEM_TITLES.get(name, name)


def zero(w):
    """An odds value that keeps the item out (0, or 0/0/0)."""
    return w == 0 or (isinstance(w, list) and not any(w))


def koopa_odds(app, names=KOOPA):
    """{name: odds} of our ready-made items (or names) the App's boxes give odds above 0 (a bad box: left out)."""
    out = {}
    for n in names:
        v = getattr(app, "odds", {}).get(n)
        try:
            w = parse_odds(v.get()) if v is not None else None
        except ValueError:
            continue
        if w is not None and not zero(w):
            out[n] = w
    return out


def parse_odds(text):
    """"20" or "20/15/15" -> 20 or [20, 15, 15]; "" -> None; anything else raises ValueError."""
    t = text.strip()
    if not t:
        return None
    parts = [x.strip() for x in t.replace(",", "/").split("/")]
    if not all(x.isdigit() for x in parts) or len(parts) not in (1, 3) or any(int(x) > 255 for x in parts):
        raise ValueError("a number from 0 to 255, or three like 20/15/15")
    return int(parts[0]) if len(parts) == 1 else [int(x) for x in parts]


def odds_text(w):
    return "" if w is None else "/".join(map(str, w)) if isinstance(w, list) else str(w)


def flights_for(b):
    """The flights a thrown ball's row offers: FLIGHTS, and homing for a one-ball item (the homing locks one fielder
    a throw: bullet_bill.homing)."""
    return FLIGHTS + ([HOME] if (b.get("launch") or {}).get("count", 3) == 1 else [])


def flight_of(b):
    """A creation's blocks -> its FLIGHTS (or HOME) label, or OWN_FLIGHT."""
    launch, move = b.get("launch") or {}, b.get("move") or {}
    for label, lv, mv in FLIGHTS + [HOME]:
        if (bool(launch.get("level")) == lv["level"] and launch.get("gravity") == lv["gravity"]
                and move.get("path", "straight") == mv["path"]
                and (mv["path"] != "bounce" or move.get("bounce") == mv["bounce"])
                and (mv["path"] != "home" or move.get("home") == mv["home"])):
            return label
    return OWN_FLIGHT


def ring_speed(b, ours):
    """A ring item's wander speed as times ours (its row's speed)."""
    w = (((b.get("spawn") or {}).get("move") or {}).get("wander") or {}).get("speed")
    o = ours["spawn"]["move"]["wander"]["speed"]
    return round(w / o, 3) if w is not None and o else 1.0


def set_ring_speed(b, ours, speed):
    """Blocks with the rings wandering speed x ours, in place (rings without wandering: left as they are)."""
    wander = (((b.get("spawn") or {}).get("move") or {}).get("wander"))
    if wander:
        wander["speed"] = round(ours["spawn"]["move"]["wander"]["speed"] * float(speed), 4)
    return b


def set_flight(b, label, speed):
    """Blocks with that flight (a FLIGHTS label; OWN_FLIGHT leaves it) and speed, in place."""
    launch = b.setdefault("launch", {"type": "launch"})
    if speed is not None:
        launch["speed"] = float(speed)
    for name, lv, mv in FLIGHTS + [HOME]:
        if name == label:
            launch.update(lv)
            b["move"] = {"type": "move", **json.loads(json.dumps(mv))}
    return b


def knock_of(b, ch):
    """A thrown ball's / Shell's knockback (slide speed, frames) as its effect block has it, or None (it doesn't knock
    down, or a Shell's knockdown with the game's own slide)."""
    eff = b.get("effect") or {}
    kind = eff.get("kind") if eff else {"shell": "knockdown"}.get(ch)
    if kind != "knockdown" or eff.get("slide_speed") is None:
        return None
    return float(eff["slide_speed"]), int(eff["slide_frames"])


def knock_text(knock):
    return ("", "") if knock is None else (f"{knock[0]:g}", str(knock[1]))


def set_knock(b, ch, knock):
    """Blocks with that knockback, in place: (slide speed, frames) knocks down with that slide (a stun or freeze
    becomes a knockdown); None: a Shell's own knockdown with the game's slide (others: left as they are)."""
    eff = dict(b.get("effect") or {"type": "effect", "kind": {"shell": "knockdown"}.get(ch, "stun")})
    if knock is None:
        if ch == "shell":
            eff.pop("slide_speed", None)
            eff.pop("slide_frames", None)
            b["effect"] = eff
        return b
    for k in ("freeze_frames", "spin_frames"):
        eff.pop(k, None)
    eff.update(type="effect", kind="knockdown", slide_speed=round(float(knock[0]), 3), slide_frames=int(knock[1]))
    b["effect"] = eff
    return b


def ice_chosen(app):
    """The Ice ball is picked: item-variants on and its odds not the "0" that keeps it out."""
    return bool("item-variants" in app.fvars and app.fvars["item-variants"].get()
                and getattr(app, "odds", {}).get(ICE) is not None and app.odds[ICE].get().strip() != "0")


def sync(app, ice=None):
    """Tick exactly the item features the picks need: the Ice ball (ice: picked or not; None: as the App has it), the
    player's items and our Ice edited (item-engine), the odds set (item-odds), and the characters' batting items and
    card labels (gui.option_features); and what they need. The Ice ball's code without the Ice ball picked (the engine
    needs it): its odds 0."""
    import gui
    have = offered(app)
    if not have:
        return
    ice = ice_chosen(app) if ice is None else ice
    want = {"item-variants"} if ice else set()
    koopas = koopa_odds(app) if KOOPA_FEATURE in have else {}
    stars = koopa_odds(app, (STARBITS,)) if "new-roulette-item" in have else {}
    picked = chosen(app) if KOOPA_FEATURE in have or "new-roulette-item" in have else set()
    reconcile(app, picked)                          # the player's versions of ours: in while their item is
    pt = part(app)
    if pt is not None and pt.items.used:
        want.add("item-engine")
    for _, key, value in char_items(app):
        want |= gui.option_features(key, value)
    odds = getattr(app, "odds", {})
    if picked & set(KOOPA):
        want.add(KOOPA_FEATURE)
    if stars:                                       # Star Bits given odds: its roulette (Rosalina's brings it too)
        want.add("new-roulette-item")
    for n in OURS:                                  # their default, 0: an empty box (no item-odds for it)
        if n in odds and n not in koopas and n not in stars and odds[n].get():
            odds[n].set("")
    need = set().union(*(app.closure(f) for f in want)) if want else set()
    if ICE in odds:
        if "item-variants" in need and not ice:
            odds[ICE].set("0")
        elif "item-variants" not in need or (ice and odds[ICE].get().strip() == "0"):
            odds[ICE].set("")
    if any(v.get().strip() for n, v in odds.items() if n in STOCK + (ICE,)) or koopas or stars:
        need.add("item-odds")
    for f in have:
        if f in app.fvars:
            app.fvars[f].set(f in need)


class ItemsPart:
    """The player's own items in a download without the Create tab (the Characters Beta): a profile part (to_profile,
    load, needs, as create_tab.CreateTab) holding the Create tab's Items page, built unshown in the App's notebook,
    which the beta never shows. The Items window embeds a page of its own and hands its used set back on Save."""

    def __init__(self, notebook, app):
        import creation_editor as ce
        self.app = app
        self.items = page_class()(notebook, app, folder=ce.FOLDER, offer=offer_for(app), credit=False)

    def to_profile(self):
        import creation_editor as ce
        self.items.used -= {ce.rel(edit_path(self.items.folder, n)) for n in OURS    # (a version of ours deleted
                            if koopa_edit(self.items.folder, n) is None}             # since: ours again)
        return self.items.to_profile()

    def load(self, profile):
        self.items.load(profile)

    def needs(self):
        return self.items.needs()


_PAGE = []


def page_class():
    """The beta's Make your own items page: item_page.ItemPage with our ready-made six listed and opened by what they
    are (never a Koopaling's name), where Save as copy of one keeps it as the player's version of it (edit_path), not
    a new item. Their "Use in my game" follows their item (reconcile), so it isn't clicked."""
    if _PAGE:
        return _PAGE[0]
    from tkinter import messagebox
    import creation_editor as ce
    from creators import blocks
    from item_page import ItemPage

    class BetaItemPage(ItemPage):
        koopa = None                                # which of our ready-made six is in the editor, or None

        def ours_of(self, path):
            """Item n that path is (its preset, or the player's version of it), or None."""
            if path is None:
                return None
            path = Path(path)
            for n in OURS:
                if (path.parent.resolve() == blocks.PRESETS.resolve() and path.stem == STEM_OF[n]) or \
                        (path.parent.resolve() == self.folder.resolve() and path.name == f"{NAMES[n]}.slgitem"):
                    return n
            return None

        def read(self, path):
            c = super().read(path)
            n = self.ours_of(path)
            if n is not None and isinstance(c, dict):
                c["name"] = NAMES[n]                # by what it is, never a Koopaling's name
            return c

        def selected(self, name, path, preset):
            super().selected(name, path, preset)
            self.koopa = n = self.ours_of(path)
            if n is not None:
                self.editor.name_entry.state(["disabled"])   # its name is what makes it ours, edited
                t = NAMES[n]
                said = (f"Ours: change anything, then Save as copy: it's kept as your {t}, which the game uses in "
                        f"place of ours." if preset else
                        f"Your {t}: the game uses it in place of ours whenever the {t} comes up (Roulette odds above "
                        f"0, or a character brings it). Saved as you change it; Reset under Item speed and flight, "
                        f"or Delete, puts ours back.")
                self.status.configure(text=said + (" " + CANT[n] if CANT[n] else ""))
            self.buttons()

        def buttons(self):
            super().buttons()
            if self.koopa is not None:              # in the game with its item (reconcile)
                self.use.state(["disabled"])

        def save_as_copy(self, then_open=True):
            n = self.ours_of(self.preset) if self.preset is not None else None
            if n is None:
                return super().save_as_copy(then_open)
            dst = edit_path(self.folder, n)
            if dst.exists() and not messagebox.askyesno(self.title, f"You already have your own {NAMES[n]}. "
                                                        "Replace it?", parent=self):
                return None
            ce.write(dst, dict(self.editor.get(), name=NAMES[n], **{"from": STEM_OF[n]}))
            self.dirty = False
            if then_open:
                self.list.refresh(select=dst)
            else:
                self.list.refresh()
            return dst

    _PAGE.append(BetaItemPage)
    return BetaItemPage


class _Host(ttk.Frame):
    """Where the embedded page goes: CreationPage adds itself to a notebook; here it's packed to fill."""

    def add(self, child, text=None):
        child.pack(fill="both", expand=True)


class Window:
    def __init__(self, app):
        import creation_editor as ce
        self.app, self.ce = app, ce
        self.part = part(app)
        have = offered(app)
        self.win = win = tk.Toplevel(app.root)
        style.title(win, TITLE)
        win.transient(app.root)
        high = min(WINDOW[1], win.winfo_screenheight() - 80)     # Nick's 860 x 620 (or a smaller screen)
        win.geometry(f"{min(WINDOW[0], win.winfo_screenwidth())}x{high}")
        bar = widgets.save_bar(win, self.save, self.cancel)     # pinned at the bottom right: the rest scrolls
        self.problem = widgets.status(ttk.Label(bar, text="", foreground=widgets.RED, wraplength=560, justify="left"))
        self.problem.pack(side="left", fill="x", expand=True)
        # the scrolled part (Nick: "items page is not scrollable"): everything above Save, a scrollbar at the right;
        # the wheel scrolls it anywhere over it but on what scrolls itself (lists, drop-downs, the block editor
        # while its blocks don't fit: tag_wheel / wheel), like the beta page's
        scroll = ttk.Frame(win)
        scroll.pack(fill="both", expand=True)
        self.view = tk.Canvas(scroll, highlightthickness=0, width=200, height=VIEW_MIN, yscrollincrement=20)
        self.bar = ttk.Scrollbar(scroll, orient="vertical", command=self.view.yview)
        self.bar.pack(side="right", fill="y")
        self.view.pack(side="left", fill="both", expand=True)
        self.view.configure(yscrollcommand=self.bar.set)
        body = ttk.Frame(self.view, padding=(10, 8, 10, 0))
        self.body = body
        self.body_item = self.view.create_window((0, 0), window=body, anchor="nw")
        body.bind("<Configure>", lambda e: self.refit())
        self.view.bind("<Configure>", lambda e: self.refit())
        win.bind_class(WHEEL_TAG, "<MouseWheel>", self.wheel)
        try:
            import credits
            line = credits.tab_line("Create")       # the thanks near the feature (Nick; CREDITS.md "Create")
        except (ImportError, OSError):
            line = None
        if line:
            self.credit_label = fit.label(body, line, grey=True)
            self.credit_label.pack(fill="x", pady=(0, 4))
        top = ttk.Frame(body)
        top.pack(fill="x")
        self.ice = tk.BooleanVar(value=ice_chosen(app))
        self.koopas = KOOPA_FEATURE in have          # our ready-made items' odds rows (0 by default)
        self.stars = "new-roulette-item" in have     # Star Bits' odds row (0 by default) and its own row
        self.odds, self.odds_start = {}, {}         # {item name or creation key: StringVar}, as opened
        self.flights, self.flights_start = {}, {}   # {"ice", one of KOOPA or a creation key: (speed, flight var)}
        self.knocks, self.knocks_start = {}, {}     # {the same keys (thrown balls, Shells): (slide speed, frames var)}
        self.reset = set()                          # rows of ours put back (Reset): ours again on Save
        self.sections = {}
        self.odds_box = self.flight_box = None
        if "item-odds" in have:
            self.odds_box = ttk.LabelFrame(top, text="Roulette odds", padding=6)
            self.odds_box.grid(row=0, column=0, rowspan=2, sticky="nsew", padx=(0, 8))
            self.sections["Roulette odds"] = self.odds_box
        right = ttk.Frame(top)
        right.grid(row=0, column=1, sticky="nsew")
        top.columnconfigure(0, weight=1)
        top.columnconfigure(1, weight=1)
        if "item-engine" in have:
            self.flight_box = ttk.LabelFrame(right, text="Item speed and flight", padding=6)
            self.flight_box.pack(fill="x")
            self.sections["Item speed and flight"] = self.flight_box
        if "item-variants" in have:
            box = ttk.LabelFrame(right, text="Item variants", padding=6)
            box.pack(fill="x", pady=(6, 0))
            self.ice_check = ttk.Checkbutton(box, text=ICE_TEXT.split(":")[0], variable=self.ice,
                                             command=self.refresh_rows)
            self.ice_check.pack(anchor="w")
            fit.label(box, ICE_TEXT.split(": ", 1)[1][0].upper() + ICE_TEXT.split(": ", 1)[1][1:] + ".",
                      grey=True, padding=(20, 0, 0, 0)).pack(fill="x")
            self.sections["Item variants"] = box
        self.page = None
        if self.part is not None:
            box = ttk.LabelFrame(body, text="Make your own items", padding=(4, 2))
            box.pack(fill="both", expand=True, pady=(6, 0))
            self.sections["Make your own items"] = box
            host = _Host(box)
            host.pack(fill="both", expand=True)
            self.page = page_class()(host, app, offer=offer_for(app), credit=False, folder=self.part.items.folder)
            self.page.used = set(self.part.items.used)
            self.page.on_used = lambda page, key, on: self.refresh_rows()
            self.page.list.refresh()
            inner = self.page.editor.scroll       # the block editor: all its blocks shown (no scroller of its own,
            inner.inner.bind("<Configure>", lambda e: self.refit(), add="+")    # Nick: "so small it is impossible
        self.refresh_rows()                                                     # to use"): the window scrolls them
        self.refit()

    # --- the scrolled part

    def refit(self):
        """The content as wide as the window's room and at least as tall (Make your own items takes the rest, never
        under PAGE_MIN: below that it scrolls); the block editor as tall as its blocks (the window scrolls them, not
        a little box of its own); every widget made since gets the wheel (tag_wheel)."""
        if self.page is not None:
            inner = self.page.editor.scroll
            want = max(PAGE_MIN // 3, inner.inner.winfo_reqheight())
            if int(inner.canvas.cget("height")) != want:
                inner.canvas.configure(height=want)
        room_w, room_h = self.view.winfo_width(), self.view.winfo_height()
        need = self.body.winfo_reqheight()
        if self.page is not None:
            box = self.sections["Make your own items"]
            need += max(0, PAGE_MIN - box.winfo_reqheight())
        self.view.itemconfigure(self.body_item, width=max(room_w, 1), height=max(room_h, need))
        self.view.configure(scrollregion=(0, 0, max(room_w, 1), max(room_h, need)))
        self.tag_wheel()

    def tag_wheel(self, w=None):
        """The window's wheel on every widget in the scrolled part but the ones that scroll themselves."""
        w = w or self.view
        if w.winfo_class() not in SELF_WHEEL:
            tags = w.bindtags()
            if WHEEL_TAG not in tags:
                w.bindtags(tags + (WHEEL_TAG,))
        for c in w.winfo_children():
            self.tag_wheel(c)

    def wheel(self, e):
        """Scroll the part, unless the pointer is in a scrolled box (the block editor) that has more to show: that
        one scrolls instead (its own wheel)."""
        w = e.widget if not isinstance(e.widget, str) else None
        while w is not None and w is not self.view:
            if isinstance(w, widgets.Scrolled) and w.needs_scroll():
                return
            w = w.master
        self.view.yview_scroll(int(-e.delta / 120) or (-1 if e.delta > 0 else 1), "units")

    # --- the player's items

    def used(self):
        """[(key, creation)]: the player's own items used in the game (the page's), without ours edited (the Ice
        ball, the ready-made six)."""
        if self.page is None:
            return []
        import creators.items as it
        return [(k, c) for k, c in self.page.used_creations() if it.preset_of(c.get("name", "")) is None]

    def folder(self):
        """The player's creations folder (the page's)."""
        return self.page.folder if self.page is not None else self.part.items.folder

    def ice_edit(self):
        """(key, creation) of the used edit of our Ice (a creation named "Ice"), or None."""
        if self.page is None:
            return None
        import creators.items as it
        return next(((k, c) for k, c in self.page.used_creations() if it.preset_of(c.get("name", "")) == ICE_PRESET),
                    None)

    # --- the rows

    def refresh_rows(self):
        """The odds and flight rows for what's in the game now: the six, the Ice ball when ticked, the player's used
        items. A row's box keeps what was typed in it."""
        typed = {k: v.get() for k, v in self.odds.items()}
        flown = {k: (s.get(), f.get()) for k, (s, f) in self.flights.items()}
        knocked = {k: (s.get(), f.get()) for k, (s, f) in self.knocks.items()}
        if self.odds_box is not None:
            for w in self.odds_box.winfo_children():
                w.destroy()
            import ice_item
            import starbits_roulette
            table = starbits_roulette.weight_table(extra=[ice_item.EXTRA])
            n = len(table) // 3
            rows = [(name, title(name), "/".join(str(table[r * n + i]) for r in range(3)))
                    for i, name in enumerate(STOCK)]
            if self.ice.get():
                rows.append((ICE, title(ICE), "/".join(str(table[r * n + ice_item.ICE]) for r in range(3))))
            if self.koopas:
                rows += [(name, title(name), "0") for name in KOOPA]    # never rolled unless given odds
            if self.stars:
                rows.append((STARBITS, title(STARBITS), "0"))            # (the edition's never_rolled: 0 unless given)
            for key, c in self.used():
                w = ((c.get("blocks") or {}).get("given") or {}).get("roulette") or [0, 0, 0]
                rows.append((key, c["name"], None))
                if key not in self.odds_start:
                    self.odds_start[key] = odds_text(w[0] if len(set(w)) == 1 else list(w))
            for r, (key, label, game) in enumerate(rows):
                v = self.odds.get(key) or tk.StringVar()
                if key not in self.odds_start:          # the App's box, as it is
                    self.odds_start[key] = self.app.odds[key].get() if key in getattr(self.app, "odds", {}) else ""
                    if key == ICE and self.odds_start[key].strip() == "0":
                        self.odds_start[key] = ""
                v.set(typed.get(key, self.odds_start[key]))
                self.odds[key] = v
                ttk.Label(self.odds_box, text=label + ":").grid(row=r, column=0, sticky="w", padx=(0, 4))
                ttk.Entry(self.odds_box, textvariable=v, width=8, style="Compact.TEntry").grid(row=r, column=1,
                                                                                               sticky="w")
                hint = f"(game: {game})" if key in STOCK else f"(default: {game})" if game else "(yours)"
                if key == "wendy":                      # (Nick: say the rings stay for the half-inning)
                    hint += " - the rings stay until the half-inning ends"
                ttk.Label(self.odds_box, text=hint, style="Small.TLabel").grid(row=r, column=2, sticky="w",
                                                                                  padx=(4, 0))
            self.odds = {k: v for k, v in self.odds.items() if k in {r[0] for r in rows}}
            note = ODDS_NOTE + (" " + KOOPA_NOTE if self.koopas else "")
            fit.label(self.odds_box, note, grey=True).grid(row=len(rows), column=0, columnspan=3, sticky="ew",
                                                           pady=(4, 0))
            self.odds_box.columnconfigure(2, weight=1)
        if self.flight_box is not None:
            for w in self.flight_box.winfo_children():
                w.destroy()
            rows = []                                   # (key, label, blocks, chassis, ours' blocks or None)
            import creators.items as it
            if self.ice.get():
                edit = self.ice_edit()
                rows.append((ICE, title(ICE), (edit[1] if edit else it.preset(ICE_PRESET))["blocks"], "thrown-ball",
                             it.preset(ICE_PRESET)["blocks"]))
            if self.koopas and (self.page is not None or self.part is not None):
                for n in KOOPA:                         # our ready-made six: the player's version, or ours
                    b = (koopa_edit(self.folder(), n) or ours_copy(n))["blocks"]
                    rows.append((n, title(n), b, b["item"]["chassis"], it.preset(STEMS[n])["blocks"]))
            for key, c in self.used():
                ch = c["blocks"]["item"]["chassis"]
                if ch in ("thrown-ball", "shell"):
                    rows.append((key, c["name"], c["blocks"], ch, None))
            r = 0
            for key, label, b, ch, ours in rows:
                if key not in self.flights_start:
                    self.flights_start[key] = self.row_values(b, ch, ours)
                s, f = self.flights.get(key) or (tk.StringVar(), tk.StringVar())
                start = flown.get(key, self.flights_start[key])
                s.set(start[0])
                f.set(start[1])
                self.flights[key] = (s, f)
                if ch in ("thrown-ball", "shell"):      # its knockback: on the line below its speed and flight
                    if key not in self.knocks_start:
                        self.knocks_start[key] = knock_text(knock_of(b, ch))
                    ks, kf = self.knocks.get(key) or (tk.StringVar(), tk.StringVar())
                    kstart = knocked.get(key, self.knocks_start[key])
                    ks.set(kstart[0])
                    kf.set(kstart[1])
                    self.knocks[key] = (ks, kf)
                    ttk.Label(self.flight_box, text="knockback").grid(row=r + 1, column=1, sticky="w")
                    ttk.Entry(self.flight_box, textvariable=ks, width=5).grid(row=r + 1, column=2, sticky="w", padx=2,
                                                                              pady=1)
                    ttk.Label(self.flight_box, text="for").grid(row=r + 1, column=3, sticky="w")
                    line = ttk.Frame(self.flight_box)
                    line.grid(row=r + 1, column=4, columnspan=2, sticky="w", padx=(6, 0))
                    ttk.Entry(line, textvariable=kf, width=5).pack(side="left")
                    eff = (b.get("effect") or {}).get("kind") or {"shell": "knockdown"}.get(ch, "stun")
                    hint = ("frames" if eff == "knockdown" and knock_of(b, ch) else
                            f"frames (empty: the game's, {STOCK_KNOCK[0]:g} for {STOCK_KNOCK[1]})" if ch == "shell" else
                            f"frames (empty: none, it {'freezes' if eff == 'freeze' else 'spins' if eff == 'spin' else 'stuns'})")
                    ttk.Label(line, text=hint, style="Small.TLabel").pack(side="left", padx=(4, 0))
                ttk.Label(self.flight_box, text=label + ":").grid(row=r, column=0, sticky="w", padx=(0, 4))
                ttk.Label(self.flight_box, text="speed").grid(row=r, column=1, sticky="w")
                ttk.Entry(self.flight_box, textvariable=s, width=5).grid(row=r, column=2, sticky="w", padx=2, pady=1)
                ttk.Label(self.flight_box, text="x").grid(row=r, column=3, sticky="w")
                if ch == "thrown-ball":
                    names = [x[0] for x in flights_for(b)]
                    names += [x for x in (start[1], self.flights_start[key][1]) if x and x not in names]
                    ttk.Combobox(self.flight_box, textvariable=f, values=names, state="readonly", width=21
                                 ).grid(row=r, column=4, sticky="w", padx=(6, 0))
                elif ch == "lob-hazards":
                    ttk.Label(self.flight_box, text=RINGS_TEXT, foreground=widgets.GREY).grid(row=r, column=4,
                                                                                            sticky="w", padx=(6, 0))
                if ours is not None:
                    ttk.Button(self.flight_box, text="Reset", style="Small.TButton",
                               command=lambda k=key, b0=ours, c0=ch: self.put_back(k, b0, c0)
                               ).grid(row=r, column=5, sticky="e", padx=(4, 0))
                r += 2 if key in self.knocks else 1
            self.flights = {k: v for k, v in self.flights.items() if k in {x[0] for x in rows}}
            self.knocks = {k: v for k, v in self.knocks.items() if k in {x[0] for x in rows}}
            if self.stars and (self.page is not None or self.part is not None):   # Star Bits: nothing to set here
                ttk.Label(self.flight_box, text=title(STARBITS) + ":").grid(row=r, column=0, sticky="w", padx=(0, 4))
                ttk.Label(self.flight_box, text=STARBITS_TEXT, foreground=widgets.GREY).grid(
                    row=r, column=1, columnspan=4, sticky="w")
                ttk.Button(self.flight_box, text="Reset", style="Small.TButton",
                           command=lambda: self.reset.add(STARBITS)).grid(row=r, column=5, sticky="e", padx=(4, 0))
                r += 1
            fit.label(self.flight_box, FLIGHT_NOTE if rows else FLIGHT_NOTE + " Tick the Ice ball or use one of your "
                      "items to set one.", grey=True).grid(row=r, column=0, columnspan=6, sticky="ew", pady=(4, 0))
            self.flight_box.columnconfigure(4, weight=1)

    @staticmethod
    def row_values(b, ch, ours=None):
        """A flight row's (speed text, flight label) for these blocks (rings: their wander speed x ours)."""
        if ch == "lob-hazards":
            return (f"{ring_speed(b, ours):g}" if ours else "1", "")
        return (str((b.get("launch") or {}).get("speed", 1.0)), flight_of(b) if ch == "thrown-ball" else "")

    def put_back(self, key, ours, ch):
        """Reset: the row as ours; on Save the player's version goes (ours again)."""
        s, f = self.flights[key]
        speed, label = self.row_values(ours, ch, ours)
        s.set(speed)
        f.set(label)
        if key in self.knocks:
            ks, kf = self.knocks[key]
            ks.set(knock_text(knock_of(ours, ch))[0])
            kf.set(knock_text(knock_of(ours, ch))[1])
        self.reset.add(key)

    # --- checks and Save

    def values(self):
        """({row key: odds}, {row key: (speed, flight)}) from the boxes; raises ValueError in plain words."""
        odds, flights = {}, {}
        names = {k: title(k) for k in STOCK + (ICE,) + OURS}
        names.update({k: c["name"] for k, c in self.used()})
        for k, v in self.odds.items():
            try:
                odds[k] = parse_odds(v.get())
            except ValueError as e:
                raise ValueError(f"{names.get(k, k)} odds: {e}.")
        for k, (s, f) in self.flights.items():
            try:
                speed = float(s.get().strip())
            except ValueError:
                raise ValueError(f"{names.get(k, k)} speed: a number from {SPEED[0]} to {SPEED[1]}.")
            if not SPEED[0] <= speed <= SPEED[1]:
                raise ValueError(f"{names.get(k, k)} speed: from {SPEED[0]} to {SPEED[1]} (1 = the item it's built "
                                 f"on).")
            flights[k] = (speed, f.get())
        return odds, flights

    def knock_values(self):
        """{row key: (slide speed, frames) or None (empty: no knockback of its own)} from the knockback boxes; raises
        ValueError in plain words."""
        names = {k: title(k) for k in (ICE,) + KOOPA}
        names.update({k: c["name"] for k, c in self.used()})
        out = {}
        for k, (s, f) in self.knocks.items():
            name, t = names.get(k, k), (s.get().strip(), f.get().strip())
            if t == ("", ""):
                if self.knocks_start.get(k, ("", "")) != ("", "") and k not in self.shells():
                    raise ValueError(f"{name} knockback: it knocks down, so it needs a slide speed and frames "
                                     f"(Reset puts ours back).")
                out[k] = None
                continue
            try:
                speed, frames = float(t[0]), int(t[1])
            except ValueError:
                raise ValueError(f"{name} knockback: a slide speed from {KNOCK_SPEED[0]:g} to {KNOCK_SPEED[1]:g} and "
                                 f"frames from {KNOCK_FRAMES[0]} to {KNOCK_FRAMES[1]}, or both empty.")
            if not (KNOCK_SPEED[0] <= speed <= KNOCK_SPEED[1] and KNOCK_FRAMES[0] <= frames <= KNOCK_FRAMES[1]):
                raise ValueError(f"{name} knockback: a slide speed from {KNOCK_SPEED[0]:g} to {KNOCK_SPEED[1]:g} and "
                                 f"frames from {KNOCK_FRAMES[0]} to {KNOCK_FRAMES[1]}.")
            out[k] = (speed, frames)
        return out

    def shells(self):
        """The row keys of the player's items built on the Shell (an empty knockback: the game's own slide)."""
        return {k for k, c in self.used() if c["blocks"]["item"]["chassis"] == "shell"}

    def changed_flight(self, key, value):
        start = self.flights_start.get(key)
        return start is None or (float(start[0]), start[1]) != value

    def changed_knock(self, key, value):
        start = self.knocks_start.get(key, ("", ""))
        return (None if start == ("", "") else (float(start[0]), int(start[1]))) != value

    def save(self):
        import patch
        import creators.items as it
        from creators import blocks
        app, ce = self.app, self.ce
        try:
            odds, flights = self.values()
            knocks = self.knock_values()
        except ValueError as e:
            self.problem.configure(text=str(e))
            return False
        if self.page is not None:
            self.page.flush()
        used = set(self.page.used) if self.page is not None else set()
        writes = {}                                 # {path: creation} to write once every check passed
        for key, c in self.used():
            c = json.loads(json.dumps(c))
            w = odds.get(key)                       # (an emptied box keeps the item's own weights)
            if w is not None and odds_text(w) != self.odds_start.get(key, ""):
                g = c["blocks"].setdefault("given", {"type": "given"})
                g["roulette"] = list(w) if isinstance(w, list) else [w] * 3
                writes[key] = c
            if key in flights and self.changed_flight(key, flights[key]):
                speed, label = flights[key]
                set_flight(c["blocks"], label if c["blocks"]["item"]["chassis"] == "thrown-ball" else OWN_FLIGHT, speed)
                writes[key] = c
            if key in knocks and self.changed_knock(key, knocks[key]):
                set_knock(c["blocks"], c["blocks"]["item"]["chassis"], knocks[key])
                writes[key] = c
        ice_key = None
        if ICE in flights and self.ice.get() and (ICE in self.reset or self.changed_flight(ICE, flights[ICE])
                                                  or (ICE in knocks and self.changed_knock(ICE, knocks[ICE]))):
            edit = self.ice_edit()
            c = json.loads(json.dumps(edit[1] if edit and ICE not in self.reset else it.preset(ICE_PRESET)))
            c.update(name=c.get("name") or "Ice", **{"from": c.get("from") or ICE_PRESET})
            set_flight(c["blocks"], flights[ICE][1], flights[ICE][0])
            if ICE in knocks and (knocks[ICE] != knock_of(c["blocks"], "thrown-ball")):
                set_knock(c["blocks"], "thrown-ball", knocks[ICE])
            ice_key = edit[0] if edit else ce.rel(self.part.items.folder / "Ice.slgitem")
            if c["blocks"] == it.preset(ICE_PRESET)["blocks"]:
                used.discard(ice_key)               # back to ours: nothing to edit
            else:
                writes[ice_key] = c
                used.add(ice_key)
        elif not self.ice.get():                    # no Ice ball: no edit of it either
            edit = self.ice_edit()
            if edit:
                used.discard(edit[0])
        ours_writes, ours_gone = {}, []             # our ready-made six: the player's versions (edit_path)
        for n in KOOPA:
            if n not in flights or (n not in self.reset and not self.changed_flight(n, flights[n])
                                    and not (n in knocks and self.changed_knock(n, knocks[n]))):
                continue
            path, ours = edit_path(self.folder(), n), it.preset(STEMS[n])["blocks"]
            c = json.loads(json.dumps((None if n in self.reset else koopa_edit(self.folder(), n)) or ours_copy(n)))
            if self.changed_flight(n, flights[n]):
                speed, label = flights[n]
                ch = c["blocks"]["item"]["chassis"]
                if ch == "lob-hazards":
                    set_ring_speed(c["blocks"], ours, speed)
                else:
                    set_flight(c["blocks"], label if ch == "thrown-ball" else OWN_FLIGHT, speed)
            if n in knocks and knocks[n] != knock_of(c["blocks"], c["blocks"]["item"]["chassis"]):
                set_knock(c["blocks"], c["blocks"]["item"]["chassis"], knocks[n])
            if c["blocks"] == ours:
                ours_gone.append(path)              # ours again: no version of it
                used.discard(ce.rel(path))
            else:
                ours_writes[ce.rel(path)] = c
        if STARBITS in self.reset:                  # Star Bits' Reset: ours again (its version goes)
            ours_gone.append(edit_path(self.folder(), STARBITS))
            used.discard(ce.rel(edit_path(self.folder(), STARBITS)))
        try:
            now = {k: c for k, c in self.page.used_creations()} if self.page is not None else {}
            now.update(writes)
            now.update(ours_writes)
            it.customs([now[k] for k in sorted(used | set(ours_writes)) if k in now])
            for c in list(writes.values()) + list(ours_writes.values()):
                blocks.check(c)
        except blocks.Invalid as e:
            self.problem.configure(text=f"That can't go in the game yet: {e}")
            return False
        koopas = {k: w for k, w in odds.items() if k in KOOPA and w is not None and not zero(w)}
        stars = {k: w for k, w in odds.items() if k == STARBITS and w is not None and not zero(w)}
        want = set()                                # what the features will be: the stock roulette's limits apply
        if self.ice.get():                          # without the new roulette (patch.check_odds)
            want |= app.closure("item-variants")
        if used:
            want |= app.closure("item-engine")
        if koopas:
            want |= app.closure(KOOPA_FEATURE)
        if stars:
            want |= app.closure("new-roulette-item")
        for _, key, value in app.char_settings():
            import gui
            for f in gui.option_features(key, value):
                want |= app.closure(f)
        stock_odds = {k: w for k, w in odds.items() if k in STOCK + (ICE,) and w is not None}
        stock_odds.update(koopas)
        stock_odds.update(stars)
        try:
            patch.check_odds(stock_odds, want)
        except SystemExit as e:
            self.problem.configure(text=str(e).replace("options: item-odds: ", "Roulette odds: "))
            return False
        for key, c in list(writes.items()) + list(ours_writes.items()):
            ce.write(Path(key) if Path(key).is_absolute() else ce.ROOT / key, c)
        for path in ours_gone:
            path.unlink(missing_ok=True)
        for k in STOCK + (ICE,):
            if k in getattr(app, "odds", {}):
                app.odds[k].set(odds_text(odds.get(k)) if k in odds else "" if k == ICE else app.odds[k].get())
        for k in OURS:                              # (0, their default: an empty box)
            if k in getattr(app, "odds", {}) and k in odds:
                app.odds[k].set(odds_text({**koopas, **stars}[k]) if k in {**koopas, **stars} else "")
        if self.part is not None:
            self.part.items.used = used
            self.part.items.list.refresh()
        sync(app, ice=self.ice.get())
        mine = len(self.used())
        said = ([f"odds for {len(stock_odds)}"] if stock_odds else []) + (["the Ice ball"] if self.ice.get() else [])
        said += [f"{mine} of your own"] if mine else []
        edited = sum(koopa_edit(self.folder(), n) is not None for n in ours_offered(app))
        said += [f"{edited} of ours changed"] if edited else []
        app.status.set("Items: " + (", ".join(said) if said else "as in the game") + ".")
        self.win.destroy()
        return True

    def cancel(self):
        if self.page is not None:
            self.page.flush()                       # (an edit in the editor is kept, as on the Create tab)
        self.win.destroy()


def open_window(app):
    """The Items window (one at a time: a second click brings the open one up)."""
    w = getattr(app, "items_window", None)
    if w is not None and w.win.winfo_exists():
        w.win.lift()
        return w
    app.items_window = Window(app)
    return app.items_window
