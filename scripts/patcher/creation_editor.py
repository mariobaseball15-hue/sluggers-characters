"""Creations in the patcher window (git-b6): an editor for any creation kind, driven by the shared schema in
scripts/creators/blocks.py (git-f3; git-95's hazard, swing and pitch blocks register there too), and a page with
our versions as read-only presets and the player's own creations as files.

Nobody sees JSON: every block is a labelled box of fields in plain words, each field shows its range and unit, and
blocks.problems(creation) shows under the editor as you go. A creation is saved as you change it. The pages that use
this: hazards_page.py (Stadiums > Hazards, git-b6) and create_tab.py (items, star swings and pitches, git-f4).
"""
import json
import tkinter as tk
from tkinter import ttk, messagebox
from pathlib import Path

import fit
import patch
import widgets
from creators import blocks

ROOT = patch.ROOT
FOLDER = ROOT / "creations"             # the player's creations (patch.py: profile "creations", relative to the repo)


def default(field):
    """A new value for a field: its default, else the plainest valid value."""
    if field.default is not None:
        return json.loads(json.dumps(field.default))
    if field.optional:
        return None
    t = field.type
    if t in ("float", "int"):
        v = field.lo if field.lo is not None else 0
        return float(v) if t == "float" else int(v)
    return {"bool": False, "text": "", "color": [255, 255, 255]}.get(t) if t in ("bool", "text", "color") else (
        field.choices[0] if t == "enum" else
        [default(field.of) for _ in range(field.length or 0)] if t == "list" else
        {k: default(f) for k, f in field.fields.items()} if t == "group" else
        new_block(field.block))


def new_block(btype):
    return {"type": btype, **{k: default(f) for k, f in blocks.BLOCKS[btype].fields.items()}}


def new_creation(kind, name, blocks_=()):
    return {"kind": kind, "format": blocks.FORMAT, "name": name, "from": None, "files": [],
            "blocks": {t: new_block(t) for t in blocks_}}


# ---------------------------------------------------------------------------------------------------- help

FIRST = ["Pick one of ours or yours on the left (New starts a fresh one).",
         "Change it on the right: each box is one part of it (how it moves, what a hit does, how it looks). Hover a "
         "setting to see what it does; Add a block or Remove this block changes which parts it has.",
         "Changing one of ours marks it \"(edited, not saved)\": Save as copy keeps your version under a new name "
         "(ours never changes), Revert to ours undoes it. Yours are saved as you go.",
         "The line under the editor says what's missing or out of range, and \"Ready to use.\" when it's done."]
SHARE = "Share... saves one of yours for others to use; Import... adds one someone sent you."
HOWTOS = {   # per kind: the How to on its page (git-92 for Nick: 3-6 steps, a share line, the usual refusals)
    "item": dict(steps=FIRST + [
        "Tick \"Use in my game\": the roulette hands it out (Roulette weight). To have a character bring it, pick "
        "it in the character editor's Star moves and abilities (Always brings) or the Characters tab's Batting item: the "
        "teammate batting just before them gets it. Check ticks what a new item needs."],
        share=SHARE, refused="a setting out of range or a part that doesn't fit what the item is built on (the line "
        "under the editor names it), more new items than the game has room for, or Koopaling items not ticked."),
    "swing": dict(steps=FIRST + [
        "Tick \"Use in my game\", then give it to a captain on the Characters tab (Star swing). Only captains use "
        "star swings."], share=SHARE, refused="a setting out of range (the line under the editor says which), more "
        "swings than the game has room for, or New star swing slots not ticked."),
    "pitch": dict(steps=FIRST + [
        "Star pitches you make are kept and can be shared, but the patcher doesn't put them in the game yet."],
        share=SHARE, refused="a setting out of range (the line under the editor says which)."),
    "hazard": dict(steps=FIRST + [
        "Tick \"Use in my game\": it takes the place of ours of its kind. For a stadium of your own, also tick it in "
        "the Stadium builder's Hazards box."],
        share=SHARE, refused="a setting out of range, a part a hazard of that kind doesn't use, two of one kind "
        "ticked (one of each kind a game), or its feature not ticked on Stadiums (Check offers to tick it)."),
}
TIPS = {     # (block type, field): what a value does in the game, beyond its label, range and unit
    ("fuse", "frames"): "How long the fuse burns before it blows up.",
    ("fuse", "radius"): "A fielder this close lights the fuse.",
    ("fuse", "blast"): "How far the blast reaches.",
    ("walkers", "respawn"): "How long before one that blew up walks back in.",
    ("shot", "speed"): "How fast the shot flies (the stock Bullet Bill is 0.3).",
    ("shot", "windup"): "How long it winds up before firing.",
    ("launch", "speed"): "How fast it's thrown, compared with the item it's built on (1 = the same).",
    ("given", "roulette"): "How often the item roulette gives it: one number when your team is behind by 6 or more, "
                           "one for 3 to 5, one for 0 to 2. 0 = never.",
    ("given", "characters"): "Characters who carry this item hand it to the teammate batting just before them: when "
                             "one of them is on deck, the batter gets it (as with the game's own item carriers).",
    ("given", "always"): "The batter gets it from their on-deck teammate even without good chemistry between them.",
    ("effect", "slide_frames"): "How long a knocked-down fielder slides.",
    ("ghosts", "chance"): "How likely a ghost comes, out of 101.",
}


# (block type, field) -> fn(the block's values, the creation's kind): shown only while it applies (hidden, it keeps
# its value); the schema's rules say the same in words (creators/blocks.py _item_rules, creators/hazards.py _rules)
APPLIES = {
    ("effect", "slide_speed"): lambda v, kind: kind != "hazard" and v.get("kind") == "knockdown",
    ("effect", "slide_frames"): lambda v, kind: kind != "hazard" and v.get("kind") == "knockdown",
    ("effect", "delta"): lambda v, kind: kind != "hazard" and v.get("kind") == "meter",
    ("effect", "spin_frames"): lambda v, kind: kind != "hazard" and v.get("kind") == "spin",
    ("effect", "freeze_frames"): lambda v, kind: kind != "hazard" and v.get("kind") == "freeze",
    ("move", "bounce"): lambda v, kind: v.get("path") == "bounce",
    ("move", "home"): lambda v, kind: v.get("path") == "home",
    ("move", "hop"): lambda v, kind: v.get("path") == "ground",
    ("move", "wander"): lambda v, kind: v.get("path") == "ground",
    ("move", "orbit"): lambda v, kind: v.get("path") == "ground",
    ("spawn", "item"): lambda v, kind: v.get("what") == "item",
    # who brings an item is the characters' now (Nick: the character editor's Special moves / the Characters tab's
    # Batting item); an old file keeps these, and they're moved onto the characters when it's opened (git-dc)
    ("given", "characters"): lambda v, kind: False,
    ("given", "always"): lambda v, kind: False,
    ("shooters", "inside_wall"): lambda v, kind: v.get("at") == "track",
    ("shooters", "angle"): lambda v, kind: v.get("at") == "track",
    ("shooters", "points"): lambda v, kind: v.get("at") == "points",
    ("volley", "play_radius"): lambda v, kind: v.get("when") == "in_play",
    ("volley", "rearm_radius"): lambda v, kind: v.get("when") == "in_play",
    ("volley", "delay"): lambda v, kind: v.get("when") == "in_play",
    ("volley", "gap"): lambda v, kind: v.get("when") == "in_play",
    ("volley", "interval"): lambda v, kind: v.get("when") == "always",
    ("volley", "first_delay"): lambda v, kind: v.get("when") == "always",
}


# (block type, field): what each row of a fixed-length list is (not "1:", "2:"), and the field's shown title
ROWS = {("given", "roulette"): ("Roulette weight", ["Behind by 6 or more", "Behind by 3 to 5",
                                                   "Behind by 0 to 2, or ahead"])}   # starbits_roulette: d >= 6 / 3-5 / < 3


def field_tip(field, block=None, key=None):
    """A field's tooltip: what it does (TIPS), its range and unit, and what leaving it out means."""
    out = [TIPS.get((block, key), "")]
    if field.type in ("float", "int") and field.lo is not None:
        unit = f" {field.unit}" if field.unit else ""
        out.append(f"From {fmt_num(field.lo)} to {fmt_num(field.hi)}{unit}.")
        if "frame" in field.unit:
            out.append("60 frames = 1 second.")
    elif field.type == "enum" and field.unit:
        out.append(f"In {field.unit}." + (" 60 frames = 1 second." if "frame" in field.unit else ""))
    return " ".join(t for t in out if t)


def fmt_num(v):
    return widgets.fmt(v) if isinstance(v, (int, float)) else str(v)


# ---------------------------------------------------------------------------------------------------- fields

class Value(ttk.Frame):
    """A field's widget: get() / set(value); calls changed() after an edit."""

    def __init__(self, parent, field, changed):
        super().__init__(parent)
        self.field, self.changed = field, changed


class Number(Value):
    def __init__(self, parent, field, changed, label=None, bare=False):
        super().__init__(parent, field, changed)
        kind = float if field.type == "float" else int
        step = 1 if kind is int else max(0.001, round((field.hi - field.lo) / 100, 3))
        self.w = widgets.NumberField(self, label or field.label, field.lo, field.hi, kind=kind, step=step,
                                     unit=(" " + field.unit) if field.unit else "", on_change=lambda v: changed(),
                                     show_label=not bare)
        self.w.pack(anchor="w")

    def get(self):
        return self.w.get()

    def set(self, v):
        self.w.set(v)


class Flag(Value):
    def __init__(self, parent, field, changed):
        super().__init__(parent, field, changed)
        self.var = tk.BooleanVar()
        ttk.Checkbutton(self, text=field.label, variable=self.var, command=changed).pack(anchor="w")

    def get(self):
        return self.var.get()

    def set(self, v):
        self.var.set(bool(v))


def words(v):
    return str(v).replace("_", " ").replace("-", " ") if isinstance(v, str) else str(v)


class Choice(Value):
    def __init__(self, parent, field, changed, bare=False):
        super().__init__(parent, field, changed)
        if not bare:
            ttk.Label(self, text=field.label + ":").pack(side="left")
        self.labels = [words(c) for c in field.choices]
        self.var = tk.StringVar()
        box = ttk.Combobox(self, textvariable=self.var, values=self.labels, state="readonly",
                           width=max(8, max(map(len, self.labels)) + 2))
        box.pack(side="left", padx=4)
        box.bind("<<ComboboxSelected>>", lambda e: changed())
        if field.unit:
            ttk.Label(self, text=field.unit, foreground=widgets.GREY).pack(side="left")

    def get(self):
        return self.field.choices[self.labels.index(self.var.get())] if self.var.get() in self.labels else None

    def set(self, v):
        self.var.set(words(v) if v in self.field.choices else "")


class Text(Value):
    def __init__(self, parent, field, changed, bare=False):
        super().__init__(parent, field, changed)
        if not bare:
            ttk.Label(self, text=field.label + ":").pack(side="left")
        self.var = tk.StringVar()
        e = ttk.Entry(self, textvariable=self.var, width=28)
        e.pack(side="left", padx=4)
        e.bind("<KeyRelease>", lambda ev: changed())

    def get(self):
        return self.var.get()

    def set(self, v):
        self.var.set(v or "")


class Color(Value):
    def __init__(self, parent, field, changed, bare=False):
        super().__init__(parent, field, changed)
        self.alpha = None
        self.w = widgets.ColorField(self, field.label, on_change=lambda rgb: changed(), show_label=not bare)
        self.w.pack(anchor="w")

    def get(self):
        return list(self.w.get()) + ([self.alpha] if self.alpha is not None else [])

    def set(self, v):
        v = v or [255, 255, 255]
        self.alpha = v[3] if len(v) == 4 else None
        self.w.set(v[:3])


class Picks(Value):
    """A list of choices (or of whole numbers in a short range) as tick boxes: "Hits: fielder, ball"."""

    def __init__(self, parent, field, changed):
        super().__init__(parent, field, changed)
        of = field.of
        self.options = list(of.choices) if of.type == "enum" else list(range(of.lo, of.hi + 1))
        ttk.Label(self, text=field.label + ":").grid(row=0, column=0, columnspan=12, sticky="w")
        self.vars = {}
        for i, o in enumerate(self.options):
            self.vars[o] = tk.BooleanVar()
            ttk.Checkbutton(self, text=words(o), variable=self.vars[o], command=changed).grid(
                row=1 + i // 12, column=i % 12, sticky="w")

    def get(self):
        return [o for o in self.options if self.vars[o].get()]

    def set(self, v):
        for o, var in self.vars.items():
            var.set(o in (v or []))


class Names(Value):
    """A list of text as one line, commas between."""

    def __init__(self, parent, field, changed):
        super().__init__(parent, field, changed)
        ttk.Label(self, text=field.label + ":").pack(side="left")
        self.var = tk.StringVar()
        e = ttk.Entry(self, textvariable=self.var, width=36)
        e.pack(side="left", padx=4)
        e.bind("<KeyRelease>", lambda ev: changed())
        ttk.Label(self, text="commas between", foreground=widgets.GREY).pack(side="left")

    def get(self):
        return [t.strip() for t in self.var.get().split(",") if t.strip()]

    def set(self, v):
        self.var.set(", ".join(v or []))


class Numbers(Value):
    """A list of a fixed number of numbers on one line (the roulette's three weights, a spot's x and z)."""

    def __init__(self, parent, field, changed):
        super().__init__(parent, field, changed)
        self.title = ttk.Label(self, text=field.label + ":")
        self.title.pack(anchor="w")
        self.items = [Number(self, field.of, changed, label=f"{i + 1}") for i in range(field.length)]
        for w in self.items:
            w.pack(anchor="w", padx=(12, 0))

    def get(self):
        return [w.get() for w in self.items]

    def set(self, v):
        for w, x in zip(self.items, v or [None] * len(self.items)):
            w.set(x)

    def name_rows(self, title, rows):
        """Each row by what it is (Nick: not "1:", "2:", "3:"), under a plain title."""
        self.title.configure(text=title + ":")
        for w, text in zip(self.items, rows):
            if w.w.name_label is not None:
                w.w.name_label.configure(text=text + ":")


class Rows(Value):
    """Any other list: a row per item, with Add and Remove."""

    def __init__(self, parent, field, changed):
        super().__init__(parent, field, changed)
        head = ttk.Frame(self)
        head.pack(fill="x")
        ttk.Label(head, text=field.label + ":").pack(side="left")
        self.add_button = ttk.Button(head, text="Add", width=6, command=self.add)
        self.add_button.pack(side="left", padx=4)
        self.body = ttk.Frame(self)
        self.body.pack(fill="x", padx=(12, 0))
        self.rows = []

    def add(self, value=None):
        if self.field.max_len is not None and len(self.rows) >= self.field.max_len:
            messagebox.showinfo(self.field.label, f"{self.field.label}: {self.field.max_len} at most.", parent=self)
            return
        row = ttk.Frame(self.body)
        row.pack(fill="x", pady=1)
        w = make(row, self.field.of, self.changed)
        w.pack(side="left")
        ttk.Button(row, text="Remove", width=8, command=lambda: self.remove(row)).pack(side="left", padx=4)
        w.set(default(self.field.of) if value is None else value)
        self.rows.append((row, w))
        if value is None:
            self.changed()

    def remove(self, row):
        self.rows = [(r, w) for r, w in self.rows if r is not row]
        row.destroy()
        self.changed()

    def get(self):
        return [w.get() for _, w in self.rows]

    def set(self, v):
        for r, _ in self.rows:
            r.destroy()
        self.rows = []
        for x in v or []:
            self.add(x)


class Fields(ttk.Frame):
    """A group's or a block's fields, one under another."""

    def __init__(self, parent, fields, changed, block=None, kind=None):
        super().__init__(parent)
        self.values, self.loaded, self.block, self.kind = {}, set(), block, kind

        def edited():
            self.arrange()
            changed()
        self.rows = {}
        for k, f in fields.items():
            row = ttk.Frame(self)               # the field, and its "i" when its owner described its data
            w = make(row, f, edited)
            w.pack(side="left", anchor="w", fill="x", expand=True)
            widgets.info(row, f.label, getattr(f, "data", None)) and row.winfo_children()[-1].pack(side="right",
                                                                                                    anchor="n")
            if (block, k) in ROWS and isinstance(w, Numbers):
                w.name_rows(*ROWS[(block, k)])
            widgets.tip(w, field_tip(f, block, k))
            self.values[k], self.rows[k] = w, row
        self.arrange()

    def arrange(self):
        """Show the fields that apply to the current choices (APPLIES), in order."""
        now = {k: w.get() for k, w in self.values.items()}
        for row in self.rows.values():
            row.pack_forget()
        for k, w in self.values.items():
            rule = APPLIES.get((self.block, k))
            if getattr(w.field, "deprecated", None):      # kept in old files, not offered (git-f3's schema)
                continue
            if rule is None or rule(now, self.kind):
                self.rows[k].pack(anchor="w", fill="x", pady=1)

    def get(self):
        """The values; a key the loaded settings had stays (even null), another only when it says something its
        absence doesn't (an untouched creation saves as it was)."""
        out = {}
        for k, w in self.values.items():
            v, d = w.get(), w.field.default
            if k in self.loaded or (v is None and d is not None) or (v is not None and v != d):
                out[k] = v
        return out

    def set(self, v):
        v = v or {}
        self.loaded = set(v)
        for k, w in self.values.items():
            w.set(v.get(k, w.field.default))
        self.arrange()


class Group(Value):
    def __init__(self, parent, field, changed):
        super().__init__(parent, field, changed)
        box = ttk.LabelFrame(self, text=field.label, padding=4)
        box.pack(fill="x")
        self.inner = Fields(box, field.fields, changed)
        self.inner.pack(fill="x")

    def get(self):
        return self.inner.get()

    def set(self, v):
        self.inner.set(v)


class Nested(Value):
    """A block inside a block (what a thing left behind does)."""

    def __init__(self, parent, field, changed):
        super().__init__(parent, field, changed)
        b = blocks.BLOCKS[field.block]
        box = ttk.LabelFrame(self, text=field.label, padding=4)
        box.pack(fill="x")
        self.inner = Fields(box, b.fields, changed, block=field.block)
        self.inner.pack(fill="x")

    def get(self):
        return {"type": self.field.block, **self.inner.get()}

    def set(self, v):
        self.inner.set(v or new_block(self.field.block))


class Optional(Value):
    """An optional field: ticked, it has a value; unticked, it's left out (the chassis's own, or none). Its checkbox
    always carries the field's name (never a blank checkbox: Nick)."""

    def __init__(self, parent, field, changed):
        super().__init__(parent, field, changed)
        self.var = tk.BooleanVar()
        big = field.type in ("group", "block", "list")
        self.tick = ttk.Checkbutton(self, text=field.label + ("" if big else ":"), variable=self.var,
                                    command=self.toggled)
        self.tick.pack(side="top" if big else "left", anchor="w")
        self.w = make(self, field, changed, optional=False, bare=not big)
        self.big = big

    def toggled(self):
        self.show()
        if self.var.get() and self.w.get() is None:
            self.w.set(default(_required(self.field)))
        self.changed()

    def show(self):
        if self.var.get():             # (unticked: just its tick, no "uses what it's built on": Nick)
            self.w.pack(side="top" if self.big else "left", anchor="w", fill="x",
                        padx=(16, 0) if self.big else 0)
        else:
            self.w.pack_forget()

    def get(self):
        return self.w.get() if self.var.get() else None

    def set(self, v):
        self.var.set(v is not None)
        self.w.set(v if v is not None else default(_required(self.field)))
        self.show()


def _required(field):
    """The same field, not optional (for a value when it's ticked)."""
    f = blocks.Field.__new__(blocks.Field)
    f.__dict__.update(field.__dict__, optional=False)
    return f


def make(parent, field, changed, optional=True, bare=False):
    if optional and field.optional:
        return Optional(parent, field, changed)
    t = field.type
    if t in ("float", "int"):
        return Number(parent, field, changed, bare=bare)
    if t == "bool":
        return Flag(parent, field, changed)
    if t == "enum":
        return Choice(parent, field, changed, bare=bare)
    if t == "text":
        return Text(parent, field, changed, bare=bare)
    if t == "color":
        return Color(parent, field, changed, bare=bare)
    if t == "group":
        return Group(parent, field, changed)
    if t == "block":
        return Nested(parent, field, changed)
    of = field.of
    if of.type == "enum" or (of.type == "int" and of.lo is not None and of.hi - of.lo < 32 and not field.length):
        return Picks(parent, field, changed)
    if of.type == "text":
        return Names(parent, field, changed)
    if field.length and of.type in ("int", "float"):
        return Numbers(parent, field, changed)
    return Rows(parent, field, changed)


# ---------------------------------------------------------------------------------------------------- editor

class CreationEditor(ttk.Frame):
    """One creation: its name, its blocks (add the ones its kind takes, remove any), and what's wrong with it."""

    def __init__(self, parent, kind, *, on_change=None, order=None):
        super().__init__(parent)
        self.kind, self.on_change = kind, on_change
        self.order = order or sorted(blocks.KIND_BLOCKS[kind], key=lambda t: blocks.BLOCKS[t].label)
        self.creation, self.readonly, self.filling = None, False, False
        top = ttk.Frame(self)
        top.pack(fill="x")
        ttk.Label(top, text="Name:").pack(side="left")
        self.name = tk.StringVar()
        self.name_entry = ttk.Entry(top, textvariable=self.name, width=30)
        self.name_entry.pack(side="left", padx=4)
        self.name_entry.bind("<KeyRelease>", lambda e: self.changed())
        self.note = ttk.Label(top, text="", foreground=widgets.GREY)     # shown only with a note
        self.scroll = widgets.Scrolled(self, height=100)     # asks for little, takes what it's given (860 x 620)
        self.scroll.pack(fill="both", expand=True, pady=4)
        add = ttk.Frame(self)
        add.pack(fill="x")
        ttk.Label(add, text="Add a block:").pack(side="left")
        self.add_var = tk.StringVar()
        self.add_box = ttk.Combobox(add, textvariable=self.add_var, state="readonly", width=24)
        self.add_box.pack(side="left", padx=4)
        self.add_button = ttk.Button(add, text="Add", command=self.add_block)
        self.add_button.pack(side="left")
        self.problems = fit.label(self, "Pick one on the left.")
        self.problems.pack(fill="x", pady=(4, 0))
        self.info_panel = widgets.InfoPanel(self)       # what an "i" says, inside the editor (git-92)
        self.frames = {}

    def set(self, creation, readonly=False, note=""):
        """Show a creation (a copy: get() gives the edited one). readonly: ours, shown to look at or copy."""
        self.filling = True
        self.creation = json.loads(json.dumps(creation))
        self.readonly = readonly
        self.name.set(self.creation.get("name", ""))
        self.note.configure(text=note)
        (self.note.pack if note else self.note.pack_forget)(**({"side": "left", "padx": 8} if note else {}))
        for f in self.frames.values():
            f[0].destroy()
        self.frames = {}
        for key, blk in (self.creation.get("blocks") or {}).items():
            self.show_block(key, blk)
        self.refresh_add()
        widgets.set_enabled(self, not readonly)
        self.filling = False
        self.show_problems()

    def show_block(self, key, blk):
        t = blk.get("type") if isinstance(blk, dict) else None
        if t not in blocks.BLOCKS:
            return                      # blocks.problems names it
        box = ttk.LabelFrame(self.scroll.inner, text=blocks.BLOCKS[t].label, padding=6)
        box.pack(fill="x", pady=3, padx=2)
        fields = Fields(box, blocks.BLOCKS[t].fields, self.changed, block=t, kind=self.kind)
        fields.pack(fill="x")
        foot = ttk.Frame(box)
        foot.pack(fill="x")
        ttk.Button(foot, text="Remove this block", command=lambda: self.remove_block(key)).pack(side="right")
        icon = widgets.info(foot, blocks.BLOCKS[t].label, getattr(blocks.BLOCKS[t], "data", None))
        if icon is not None:
            icon.pack(side="right", padx=4)
        fields.set(blk)
        self.frames[key] = (box, fields, t)

    def refresh_add(self):
        have = {t for _, _, t in self.frames.values()}
        self.addable = [t for t in self.order if t not in have]
        self.add_box.configure(values=[blocks.BLOCKS[t].label for t in self.addable])
        self.add_var.set("")

    def add_block(self):
        label = self.add_var.get()
        t = next((t for t in self.addable if blocks.BLOCKS[t].label == label), None)
        if t is None:
            return
        self.show_block(t, new_block(t))
        self.refresh_add()
        self.changed()

    def remove_block(self, key):
        self.frames.pop(key)[0].destroy()
        self.refresh_add()
        self.changed()

    def get(self):
        if self.creation is None:
            return None
        c = dict(self.creation)
        c["name"] = self.name.get().strip()
        c["blocks"] = {key: {"type": t, **fields.get()} for key, (_, fields, t) in self.frames.items()}
        return c

    def show_problems(self):
        c = self.get()
        found = blocks.problems(c) if c else []
        self.problems.configure(text="\n".join(found) if found else "Ready to use.",
                                foreground=widgets.RED if found else widgets.GREY)
        return found

    def changed(self):
        if self.filling or self.readonly:
            return
        self.show_problems()
        if self.on_change:
            self.on_change(self.get())


# ---------------------------------------------------------------------------------------------------- page

KIND_MODULES = {"hazard": "creators.hazards", "swing": "creators.swings", "pitch": "creators.pitches",
                "item": "creators.items"}      # each registers its kind's blocks and rules in creators/blocks.py


def ours(kind):
    """([(name, preset file)], [file names that can't be read]): our presets of a kind, with its blocks registered
    first; one this patcher can't read is left out and named, so the window still opens."""
    import importlib
    try:
        importlib.import_module(KIND_MODULES[kind])
    except (KeyError, ModuleNotFoundError):
        pass
    out, broken = [], []
    for path in sorted(blocks.PRESETS.glob("*" + blocks.EXTENSIONS[kind])):
        try:
            out.append((blocks.load(path)["name"], path))
        except (blocks.Invalid, OSError, ValueError):
            broken.append(path.name)
    return out, broken


def rel(path):
    try:
        return Path(path).resolve().relative_to(ROOT).as_posix()
    except ValueError:
        return str(path)


class CreationPage(ttk.Frame):
    """Our versions (presets, edited in place and kept as the player's copy: Save as copy; ours never change) and the
    player's creations of one kind, the editor, and "Use in my game".

    template(name) -> a new creation for New. needs(creation) -> {features} a used creation needs. used_changed() is
    called when the used set changes. offer(preset file stem) -> whether one of ours is listed (None: all of them; a
    string: listed under that name);
    credit: False leaves out the page's thanks line (its host shows it). The page's profile part is
    {"creations": [the used files]}."""

    usable = True                               # False: a kind the build doesn't take yet (star pitches)

    def __init__(self, notebook, app, kind, title, *, folder=FOLDER, template=None, needs=None, intro="",
                 order=None, on_used=None, offer=None, credit=True):
        super().__init__(notebook, padding=6)
        self.app, self.kind, self.title, self.folder = app, kind, title, Path(folder)
        self.suffix = blocks.EXTENSIONS[kind]
        self.template = template or (lambda name: new_creation(kind, name))
        self.needs_of, self.on_used = needs or (lambda c: set()), on_used
        self.used, self.path, self.save_job = set(), None, None
        self.preset, self.dirty = None, False       # one of ours in the editor, and whether it's been changed
        notebook.add(self, text=title)
        if intro:
            fit.label(self, intro, grey=True).pack(fill="x", pady=(0, 2))
        line = widgets.credit("Stadiums" if kind == "hazard" else "Create") if credit else None   # git-10's credits
        if line:
            fit.label(self, line, grey=True).pack(fill="x", pady=(0, 4))
        body = ttk.Frame(self)
        body.pack(fill="both", expand=True)
        presets, broken = ours(kind)
        if offer is not None:                   # an edition's short list of ours (the Characters Beta: Ice and
            listed = []                         # the ready-made six); a name offer gives is the one listed
            for n, p in presets:
                o = offer(Path(p).stem)
                if o:
                    listed.append((o if isinstance(o, str) else n, p))
            presets = listed
        self.list = widgets.PresetList(body, presets, self.folder, self.suffix, on_select=self.selected,
                                       make_new=self.make_new, copy=self.copy, check=self.import_problem,
                                       title="Ours and yours", copy_button=False)
        self.list.pack(side="left", fill="y")
        right = ttk.Frame(body, padding=(10, 0, 0, 0))
        right.pack(side="left", fill="both", expand=True)
        self.use_var = tk.BooleanVar()
        row = ttk.Frame(right)                  # "Use in my game" and the How to button share a row (860 x 620)
        row.pack(fill="x")
        self.use = ttk.Checkbutton(row, text="Use in my game", variable=self.use_var, command=self.use_toggled)
        self.use.pack(side="left")
        self.save_copy = ttk.Button(row, text="Save as copy", command=self.save_as_copy)
        self.save_copy.pack(side="left", padx=(8, 0))
        self.revert = ttk.Button(row, text="Revert to ours", command=self.revert_to_ours)
        self.revert.pack(side="left", padx=4)
        self.editor = CreationEditor(right, kind, on_change=self.edited, order=order)
        self.editor.pack(fill="both", expand=True)
        if kind in HOWTOS:                      # its steps open above the editor
            self.howto = widgets.HowTo(row, key=f"creations:{kind}", body_in=right, before=self.editor,
                                       **HOWTOS[kind])
            self.howto.pack(side="right")
        self.status = fit.label(right, "Pick one of ours or yours to change." +
                                (f" Left out, because this patcher can't read them: {', '.join(broken)}." if broken
                                 else ""), grey=True)
        self.status.pack(fill="x")
        self.buttons()

    # --- files

    def read(self, path):
        """A creation file for the editor: checked when it can be, else as it is (the editor says what's wrong)."""
        try:
            return blocks.load(path)
        except blocks.Invalid:
            return json.loads(Path(path).read_text(encoding="utf8"))

    def make_new(self, path):
        write(path, self.template(path.stem))

    def copy(self, src, dst):
        c = self.read(src)
        c["from"] = c.get("from") or (Path(src).stem if Path(src).parent == blocks.PRESETS else None)
        c["name"] = dst.stem
        write(dst, c)

    def import_problem(self, path):
        if path.suffix.lower() != self.suffix:
            return f"{path.name} isn't a {self.title.lower()} file ({self.suffix})."
        try:
            c = json.loads(path.read_text(encoding="utf8"))
        except (OSError, ValueError):
            return f"{path.name} can't be read as a creation."
        if not isinstance(c, dict) or c.get("kind") != self.kind:
            return f"{path.name} isn't a {self.title.lower()} creation."
        return None

    # --- the list and the editor

    def selected(self, name, path, preset):
        if self.dirty and self.preset is not None:       # leaving an edit of ours that isn't saved
            if messagebox.askyesno(self.title, f"Your changes to {self.editor.get()['name']} aren't saved. Save them "
                                   "as a copy?", parent=self):
                self.save_as_copy(then_open=False)
        self.flush()
        try:
            c = self.read(path)
        except (OSError, ValueError):
            self.status.configure(text=f"{Path(path).name} can't be read.")
            return
        self.path, self.preset, self.dirty = (None, Path(path), False) if preset else (Path(path), None, False)
        self.editor.set(c, note="ours" if preset else "")
        self.use_var.set(rel(path) in self.used)
        self.status.configure(text="Ours: change anything, then Save as copy to keep it. As it is, Use in my game "
                              "puts ours in." if preset else "Saved as you change it.")
        self.buttons()

    def buttons(self):
        have = self.editor.creation is not None
        self.use.state(["!disabled"] if have and self.usable else ["disabled"])
        self.save_copy.state(["!disabled"] if have else ["disabled"])
        self.revert.state(["!disabled"] if self.preset is not None and self.dirty else ["disabled"])

    def edited(self, c):
        if self.preset is not None:                     # one of ours: marked, never written
            if not self.dirty:
                self.dirty = True
                self.editor.note.configure(text="ours (edited, not saved)")
                self.editor.note.pack(side="left", padx=8)
                if rel(self.preset) in self.used:       # the game would get ours, not these changes
                    self.unuse(rel(self.preset))
                    self.status.configure(text="Your changes aren't in the game until you Save as copy and use it.")
                self.buttons()
            return
        if self.path is None:
            return
        if self.save_job:
            self.after_cancel(self.save_job)
        self.save_job = self.after(400, self.flush)

    def save_as_copy(self, then_open=True):
        """The editor's creation into the player's creations under a name they give (prefilled "<name> copy"); then
        the copy is the one being edited. Returns its path, or None."""
        c = self.editor.get()
        if c is None:
            return None
        dst = self.list._target(f"{c['name']} copy", "Name for your copy:")
        if dst is None:
            return None
        c = dict(c, name=dst.stem)
        c["from"] = c.get("from") or (self.preset.stem if self.preset is not None else None)
        write(dst, c)
        self.dirty = False
        if then_open:
            self.list.refresh(select=dst)               # selected(): the copy, editable and saved as you go
        else:
            self.list.refresh()
        return dst

    def revert_to_ours(self):
        if self.preset is None:
            return
        self.dirty = False
        self.editor.set(self.read(self.preset), note="ours")
        self.status.configure(text="Back to ours.")
        self.buttons()

    def flush(self):
        """Write the edited creation now (edits are saved shortly after each change)."""
        if self.save_job:
            self.after_cancel(self.save_job)
            self.save_job = None
        if self.path is None or self.editor.creation is None or self.editor.readonly:
            return
        try:
            write(self.path, self.editor.get())
        except OSError as e:
            self.status.configure(text=f"Couldn't save {self.path.name}: {e.strerror or e}.")

    # --- used in the game

    def use_toggled(self):
        if self.path is None and self.preset is None:
            self.use_var.set(False)
            return
        if self.path is None and self.dirty and self.use_var.get():     # an unsaved edit of ours
            if not messagebox.askyesno(self.title, "Your changes aren't saved. Save them as a copy and use that? "
                                       "(No leaves it as it is.)", parent=self) or self.save_as_copy() is None:
                self.use_var.set(False)
                return
            self.use_var.set(True)
        key = rel(self.path if self.path is not None else self.preset)
        if self.use_var.get():
            self.flush()
            found = self.editor.show_problems()
            if found:
                messagebox.showwarning(self.title, f"{self.editor.get()['name']} can't go in the game yet:\n\n  " +
                                       "\n  ".join(found), parent=self)
                self.use_var.set(False)
                return
            self.used.add(key)
        else:
            self.used.discard(key)
        if self.on_used:
            self.on_used(self, key, self.use_var.get())

    def used_creations(self):
        """[(path key, creation)] for the used files that are still there."""
        out = []
        for key in sorted(self.used):
            p = ROOT / key if not Path(key).is_absolute() else Path(key)
            try:
                out.append((key, self.read(p)))
            except (OSError, ValueError):
                pass
        return out

    def to_profile(self):
        self.flush()
        return {"creations": sorted(self.used)} if self.used else {}

    def load(self, profile):
        self.used = set()
        self.after_idle(self.bring_on_characters) if self.kind == "item" else None
        for pattern in profile.get("creations", []):
            try:
                paths = patch.expand([pattern])
            except SystemExit:
                continue
            self.used |= {rel(p) for p in paths if Path(p).suffix.lower() == self.suffix}
        s = self.list.selected()
        self.use_var.set(bool(s and rel(s[1]) in self.used))

    def bring_on_characters(self):
        """An old item file naming the characters who bring it (given.characters / always): onto those characters'
        Batting item (the Characters tab's store), unless they have one set already (git-dc does the same in the
        patch)."""
        settings = getattr(self.app, "settings", None)
        if settings is None:
            return
        for _, c in self.used_creations():
            given = (c.get("blocks") or {}).get("given") or {}
            for who in given.get("characters") or []:
                name = self.app.char_name(who) if hasattr(self.app, "char_name") else who
                if name and "batting_item" not in settings.get(name, {}):
                    settings.setdefault(name, {})["batting_item"] = c["name"]
                    if given.get("always"):
                        settings[name]["always_item"] = True
        if hasattr(self.app, "refresh_char_list"):
            self.app.refresh_char_list()

    def needs(self):
        return [(self.needs_of(c), f"{c.get('name', key)} is used on {self.title}",
                 lambda key=key: self.unuse(key)) for key, c in self.used_creations() if self.needs_of(c)]

    def unuse(self, key):
        self.used.discard(key)
        s = self.list.selected()
        if s and rel(s[1]) == key:
            self.use_var.set(False)


def write(path, creation):
    Path(path).parent.mkdir(parents=True, exist_ok=True)
    Path(path).write_text(json.dumps(creation, indent=1, ensure_ascii=False) + "\n", encoding="utf8")
