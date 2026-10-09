"""The patcher window's recolor editor: make or change a recolor without writing a recipe (Nick: "way easier to use
in gui and requiring no json"; redone for his "Purple Mario" screenshot: "redo the UI to make this make sense").

Layout (git-92's): at the top the character to start from (a stock one, or an added one: ours, imported or made),
the new name and the colour wheel's swatch. In the middle one row per colour recolor.base_colors finds in the base's
textures: the colour as it is, a switch, its own new colour (Pick a colour..., or hue / colourfulness / brightness)
and Stock; the first row is the main colour, ticked for a new recolor. "Add a colour row" picks a colour by a hue
range (one the grouping missed); an added row can be removed. Every ticked row is one rule of the recipe's
"recolor" ({"hue", "min_sat", "to_hue", "sat", "val", "textures"?}, recolor.rule_to). Below, the bat: on by default
for a new recolor, the same colour changes as the rows ("follow") or its own colour (rules), off = "keep"; a recipe
with no "bat" keeps its automatic meaning (recolor.own_bats) until the bat is changed. A bat the tool can't read is
a warning next to it, never a reason to refuse the save. On the right a before / after preview of every texture the
rules change, both portraits and the bat, made in a worker thread (debounced) so typing and sliding never wait.

A recipe opened and saved with nothing changed is written back as it was (its own keys, "_why" and all, and its
rules untouched); the editor's own choices go in "_editor" ({"colors": [rgb per rule], "bat", "bat_rgb"?}) only
once something is edited. Everything recolor-specific is recolor.py's editor API (bases, base_of, base_colors,
color_in, rule_to, target_of, color_name, preview_pairs, bat_rules, bat_problem, validate, DATA, SWATCH_RGB).

RecolorEditor(parent, game, recipe=None, on_save=None, on_change=None, show_save=True, folder=None, id_folders=())
is a ttk.Frame that can sit in any window (git-10's character window); open_window() is the patcher's own window.
"""
import base64, colorsys, io, json, queue, threading
import shutil
import tkinter as tk
import style
from tkinter import ttk, colorchooser, filedialog, messagebox
from pathlib import Path
from PIL import Image

import widgets


HOW_TO = ["Pick the character to recolor (stock or added) and name the new one.",
          "Each row is one of its colours: tick it and give it a new colour (Pick a colour... or the sliders). "
          "Stock puts it back.",
          "Change as many colours as you like, each to its own colour. Add a colour row for one that isn't listed.",
          "The bat takes the same changes unless you untick it or give it a colour of its own.",
          "Check the before / after, then Save recolor: it's added to the recolors and ticked."]
HOW_TO_SHARE = ("a recolor is a small file in the recolors folder with no game art in it: send it, or put one you "
                "get there.")
HOW_TO_REFUSED = ("the line next to Save says why (e.g. the wheel already has 10, or the name is taken). A bat the "
                  "tool can't recolor never stops a save.")
SLIDERS = (("Hue", 359, "Which colour, around the colour wheel: 0 red, 120 green, 240 blue (0 to 359)."),
           ("Colourful", 100, "Colourfulness: 0 is grey, 100 the full colour. Low with dark or light makes black or "
                              "white."),
           ("Bright", 100, "Brightness: 0 is black, 100 as bright as the colour goes. The shading stays."))
ROOM = (860, 620)                       # the patcher's smallest window (Nick's Patcher 8)
PREVIEW_BG = (40, 40, 48, 255)
MISSING = object()


def photo(img, zoom=2):
    """A PIL image -> a tk PhotoImage (through PNG: no ImageTk needed), zoomed."""
    buf = io.BytesIO()
    img.save(buf, "PNG")
    p = tk.PhotoImage(data=base64.b64encode(buf.getvalue()).decode("ascii"))
    return p.zoom(zoom) if zoom > 1 else p


def hexrgb(rgb):
    return "#%02x%02x%02x" % tuple(int(c) for c in rgb)


def swatch(parent, rgb, width=3, relief="ridge"):
    """A colour box (a label that is a colour on purpose: test_labels.py lets it have no text)."""
    lab = tk.Label(parent, width=width, bg=hexrgb(rgb), relief=relief, borderwidth=2)
    lab.swatch = True
    return lab


def data_fields():
    """{field id: what it changes in the game's data} for every field the editor edits (test_info_coverage.py)."""
    import recolor
    return {f"recolor.{k}": v for k, v in recolor.DATA.items()}


def compose(pairs, size):
    """[(label, before, after)] -> one RGBA picture of `size`: each pair before | after with its label under it, in
    as many columns as makes them biggest (at most 128 px a picture, nearest-neighbour: texels stay sharp)."""
    from PIL import Image, ImageDraw
    W, H = max(size[0], 60), max(size[1], 60)
    out = Image.new("RGBA", (W, H), PREVIEW_BG)
    if not pairs:
        return out
    pad, cap, gap = 6, 12, 3
    best = (0, 1)
    for cols in range(1, len(pairs) + 1):
        rows = -(-len(pairs) // cols)
        cell = min((W - pad * (cols + 1)) / cols / 2 - gap, (H - pad * (rows + 1)) / rows - cap)
        if cell > best[0]:
            best = (cell, cols)
    cell, cols = int(min(best[0], 128)), best[1]
    if cell < 8:
        return out
    draw = ImageDraw.Draw(out)
    for n, (label, before, after) in enumerate(pairs):
        x = pad + (n % cols) * (2 * cell + 2 * gap + pad)
        y = pad + (n // cols) * (cell + cap + pad)
        for k, img in enumerate((before, after)):
            t = img.copy()
            f = min(cell / t.width, cell / t.height)
            t = t.resize((max(1, int(t.width * f)), max(1, int(t.height * f))), Image.NEAREST)
            out.alpha_composite(t, (x + k * (cell + 2 * gap) + (cell - t.width) // 2, y + (cell - t.height) // 2))
        draw.text((x, y + cell + 1), label, fill=(200, 200, 210, 255))
    return out


class ColorRow:
    """One colour of the base: `color` (a base_colors / color_in entry), its new colour `target`, on or off, and the
    recipe's own rule it came from (kept as it is until the row is edited)."""

    def __init__(self, ed, color, target=None, on=False, rule=None, added=False):
        self.ed, self.color, self.rule, self.added = ed, color, rule, added
        self.target = tuple(target or color["rgb"])
        self.edited = False
        self.on = tk.BooleanVar(value=on)
        h, s, v = colorsys.rgb_to_hsv(*(c / 255 for c in self.target))
        self.vars = [tk.IntVar(value=round(h * 359)), tk.IntVar(value=round(s * 100)), tk.IntVar(value=round(v * 100))]
        self.lo, self.hi = tk.IntVar(value=color["hue"][0]), tk.IntVar(value=color["hue"][1])
        self.frame = None

    def title(self, index):
        rc = self.ed.rc
        name = rc.color_name(self.color["rgb"])
        pct = f"{round(self.color['share'] * 100)}%"
        if self.added:
            return f"Hues {self.color['hue'][0]}-{self.color['hue'][1]}: {name}, {pct}"
        return (f"Main colour: {name}, {pct}" if index == 0 else f"{name.capitalize()}, {pct}")

    def build(self, parent, index):
        f = self.frame = ttk.Frame(parent, padding=(0, 2, 0, 4))
        line = ttk.Frame(f)
        line.pack(fill="x")
        widgets.tip(swatch(line, self.color["rgb"]), "The colour as it is now (its average in the "
                                                     "character's textures).").pack(side="left")
        self.check = ttk.Checkbutton(line, text=self.title(index), variable=self.on, command=self.toggled, width=26)
        self.check.pack(side="left", padx=(4, 0))
        ttk.Label(line, text="→").pack(side="left")
        self.box = widgets.tip(swatch(line, self.target, relief="sunken"), "Its new colour.")
        self.box.pack(side="left", padx=(2, 4))
        ttk.Button(line, text="Pick a colour...", command=self.pick).pack(side="left")
        widgets.tip(ttk.Button(line, text="Stock", width=6, command=self.stock),
                    "Back to this colour as it is: the row is unticked and nothing changes it.").pack(side="left",
                                                                                                    padx=(4, 0))
        if self.added:
            ttk.Button(line, text="Remove", width=7, command=lambda: self.ed.remove_row(self)).pack(side="left",
                                                                                                   padx=(4, 0))
        sl = ttk.Frame(f)
        sl.pack(fill="x", padx=(34, 0))
        for (label, hi, tip), var in zip(SLIDERS, self.vars):
            widgets.tip(ttk.Label(sl, text=label), tip).pack(side="left", padx=(0, 2))
            widgets.tip(ttk.Scale(sl, from_=0, to=hi, variable=var, length=78, command=lambda v: self.slid()),
                        tip).pack(side="left", padx=(0, 6))
        if self.added:
            hr = ttk.Frame(f)
            hr.pack(fill="x", padx=(34, 0), pady=(2, 0))
            tip = ("Which of the character's colours this row picks: every texel whose hue is in this range (0 to "
                   "360; from more than to wraps past red), with a little colour in it.")
            widgets.tip(ttk.Label(hr, text="Picks hues from"), tip).pack(side="left")
            for k, var in enumerate((self.lo, self.hi)):
                if k:
                    ttk.Label(hr, text="to").pack(side="left", padx=4)
                sp = ttk.Spinbox(hr, from_=0, to=360, increment=5, width=4, textvariable=var,
                                 command=self.range_changed)
                sp.bind("<FocusOut>", lambda e: self.range_changed())
                sp.bind("<Return>", lambda e: self.range_changed())
                sp.pack(side="left", padx=(4, 0))
        return f

    def rgb_from_vars(self):
        h, s, v = (var.get() for var in self.vars)
        return tuple(round(c * 255) for c in colorsys.hsv_to_rgb(h / 359, s / 100, v / 100))

    def set_target(self, rgb, edit=True):
        self.target = tuple(int(c) for c in rgb)
        h, s, v = colorsys.rgb_to_hsv(*(c / 255 for c in self.target))
        for var, x in zip(self.vars, (round(h * 359), round(s * 100), round(v * 100))):
            var.set(x)
        if self.frame is not None:
            self.box.configure(bg=hexrgb(self.target))
        if edit:
            self.edited = True
            self.on.set(True)
            self.ed.row_edited(self)

    def slid(self):
        self.target = self.rgb_from_vars()
        self.box.configure(bg=hexrgb(self.target))
        self.edited = True
        self.on.set(True)
        self.ed.row_edited(self)

    def pick(self):
        rgb, _ = colorchooser.askcolor(color=hexrgb(self.target), parent=self.ed.winfo_toplevel(),
                                       title="The new colour")
        if rgb:
            self.set_target(rgb)

    def stock(self):
        self.set_target(self.color["rgb"], edit=False)
        self.edited = True
        self.on.set(False)
        self.ed.row_edited(self)

    def toggled(self):
        self.edited = True
        self.ed.row_edited(self)

    def range_changed(self):
        try:
            lo, hi = int(self.lo.get()) % 361, int(self.hi.get()) % 361
        except (tk.TclError, ValueError):
            return
        if [lo, hi] == list(self.color["hue"]):
            return
        self.color = self.ed.rc.color_in(self.ed.game, self.ed.base_ref(), [lo, hi], self.color.get("min_sat", 0.25),
                                         defs=self.ed.defs)
        self.edited = True
        self.on.set(True)
        self.check.configure(text=self.title(1))
        self.ed.row_edited(self)

    def rule_out(self):
        """The recipe rule of this row: the recipe's own until the row is edited."""
        if self.rule is not None and not self.edited:
            return self.rule
        r = self.ed.rc.rule_to(self.color, self.target)
        for k in ("region", "portraits"):
            if self.rule is not None and k in self.rule:
                r[k] = self.rule[k]
        return r


def offered_defs(defs):
    """defs ({id: (file, definition)}) limited to what this download's edition offers (edition.offers: a character by
    its characters/ file, a recolor tool definition by its recipe in recolors/), plus anything the player made
    ("made_by": "player"); every one when there's no edition. The Characters Beta ships all our files but offers a
    few, so counting the rest made wheels look full (git-10: Green Yoshi "10 of 10" in the beta)."""
    import json
    import recolor
    try:
        import edition
    except ImportError:
        return defs
    if not edition.load():
        return defs

    def player_made(path):
        try:
            return json.loads(Path(path).read_text(encoding="utf8")).get("made_by") == "player"
        except (OSError, ValueError):
            return False
    out = {}
    for cid, (f, d) in defs.items():
        if f is None:
            out[cid] = (f, d)
            continue
        if str(d.get("_why", "")).startswith("Recolor tool"):
            recipe = Path(recolor.ROOT) / "recolors" / f"{recolor.slug(d['name'])}.json"
            ok = edition.offers("recolors", recipe) or player_made(recipe)
        else:
            ok = edition.offers("characters", f) or player_made(f)
        if ok:
            out[cid] = (f, d)
    return out


class RecolorEditor(ttk.Frame):
    """The editor, a frame for any window (the patcher's own: open_window; git-10's character window):

        RecolorEditor(parent, game, folder=None, path=None, recipe=None, on_save=None, on_change=None,
                      show_save=True, id_folders=(), extra=None)

    game: the recolor.Game of the player's game (gui.App.recolor_game). folder: where recipes are saved (default:
    the recipe's own folder, else recolors/). path: a recipe file to edit (None: a new recolor); recipe: a recipe
    dict to start from instead. on_save(path): after a save. on_change(recipe): debounced, after each edit.
    show_save: False for a host with its own Save (no Save button or reason line). id_folders: more folders of
    definitions / recipes whose ids a new recolor avoids. extra: keys merged into the recipe (e.g. {"made_by":
    "player"}). Every key of an edited recipe the editor doesn't control is kept as it is.
    .recipe(): the recipe dict; .set_recipe(d, path=None): load one; .problems(): (what stops a save, warnings that
    don't); .save(): what Save recolor does, the saved path or None."""

    def __init__(self, parent, game, folder=None, path=None, recipe=None, on_save=None, on_change=None,
                 show_save=True, id_folders=(), extra=None, own_window=False, active_names=None, **kw):
        super().__init__(parent, padding=8, **kw)
        import recolor
        if isinstance(folder, dict):                # (a recipe dict as the third argument)
            folder, recipe = None, folder
        elif folder is not None and Path(folder).is_file():     # (a recipe file as the third argument)
            folder, path = None, folder
        self.rc, self.game, self.on_save, self.on_change = recolor, game, on_save, on_change
        self.show_save, self.own_window, self.extra = show_save, own_window, dict(extra or {})
        self.active_names = {str(n).lower() for n in active_names} if active_names is not None else None
        path = Path(path) if path else None
        self.folder = Path(folder) if folder else (path.parent if path else Path(recolor.ROOT) / "recolors")
        self.id_folders = [self.folder] + [Path(f) for f in id_folders]
        self._new_id = None
        self.defs = offered_defs(recolor.definitions())   # the added characters a recolor can start from (ours;
        # imported below); in an edition only what it offers, so wheel counts match its build (git-10)
        self.imported, self._materialized = {}, None
        self.rows, self.clusters = [], []
        self._job = self._poll_job = self._pending = None
        self._busy, self._gen, self._shown_gen, self._q = False, 0, 0, queue.Queue()
        self.images, self._closed = [], False
        self.texture_overrides = {}     # {(model file 0/1, texture index): selected PNG path}
        self.bat_texture_overrides = {} # {bat texture index: selected PNG path}
        self.glove_texture_overrides = {} # {(model file 3/4, texture index): selected PNG path}
        self.portrait_overrides = {}    # {"side"/"front": selected PNG path}
        self.bat_pairs, self._ready = 0, False
        self.build()
        self.set_recipe(json.loads(path.read_text(encoding="utf8")) if path else (recipe or {}), path)

    # --- the widgets

    def build(self):
        rc = self.rc
        head = ttk.Frame(self)
        head.pack(fill="x")
        line = widgets.credit("Recolors")
        self.credit_label = None
        if line:
            self.credit_label = ttk.Label(head, text=line, foreground=widgets.GREY, wraplength=640, justify="left")
            self.credit_label.pack(side="left", fill="x", expand=True, padx=(8, 0))
        top = ttk.Frame(self, padding=(0, 4, 0, 4))
        top.pack(fill="x")
        # the How to's button in the head row; its steps open across the editor, above the fields
        self.howto = widgets.HowTo(head, HOW_TO, share=HOW_TO_SHARE, refused=HOW_TO_REFUSED, key="recolor editor",
                                   body_in=self, before=top)
        self.howto.button.configure(command=lambda: (self.howto.toggle(), self.fit()))
        for lab in self.howto.body.winfo_children():    # they wrap at the editor's width (fit, rewrap), not their own
            lab.unbind("<Configure>")
        self.bind("<Configure>", lambda e: self.rewrap(e.width))
        self.howto.pack(side="left", anchor="n", **({"before": self.credit_label} if self.credit_label else {}))
        self.base, self.name, self.swatch_var = tk.StringVar(), tk.StringVar(), tk.StringVar()
        ttk.Label(top, text="Recolor of:").grid(row=0, column=0, sticky="w")
        self.base_cb = ttk.Combobox(top, textvariable=self.base, state="readonly", width=26, height=24)
        self.base_cb.grid(row=0, column=1, sticky="w", padx=(4, 0))
        self.base_cb.bind("<<ComboboxSelected>>", lambda e: self.base_changed())
        widgets.tip(self.base_cb, "The character to copy: its stats, voice and animations stay; its colours change. "
                                  "Added characters (ours, imported or made) are after the stock ones.")
        self._info(top, "The character to start from", "base").grid(row=0, column=2, padx=(2, 12))
        ttk.Label(top, text="New name:").grid(row=0, column=3, sticky="w")
        ttk.Entry(top, textvariable=self.name, width=22).grid(row=0, column=4, sticky="w", padx=(4, 0))
        self.name.trace_add("write", lambda *a: self.changed())
        self._info(top, "The new character's name", "name").grid(row=0, column=5, padx=(2, 0))
        ttk.Label(top, text="Wheel swatch:").grid(row=1, column=0, sticky="w", pady=(4, 0))
        sw = ttk.Frame(top)
        sw.grid(row=1, column=1, sticky="w", padx=(4, 0), pady=(4, 0))
        cb = ttk.Combobox(sw, textvariable=self.swatch_var, values=list(rc.SWATCH_RGB), state="readonly", width=10)
        cb.pack(side="left")
        cb.bind("<<ComboboxSelected>>", lambda e: self.swatch_picked_now())
        widgets.tip(cb, "The little colour dot for this character on the character-select colour wheel. It follows "
                        "the main new colour until you choose one here.")
        self.swatch_box = swatch(sw, (128, 128, 128), width=2)
        self.swatch_box.pack(side="left", padx=(4, 0))
        self._info(top, "The colour wheel's swatch", "swatch").grid(row=1, column=2, padx=(2, 12), pady=(4, 0))
        self.wheel_label = widgets.status(ttk.Label(top, text="The colour wheel: ...", foreground=widgets.GREY))
        self.wheel_label.grid(row=1, column=3, columnspan=3, sticky="w", pady=(4, 0))

        if self.show_save:
            foot = widgets.save_bar(self, self.save, self.close if self.own_window else None, padding=(0, 6, 0, 0),
                                    text="Save" if self.own_window else "Save recolor")   # (Nick: Save, bottom right)
            self.save_button = foot.save
            self.problems_label = widgets.status(ttk.Label(foot, text="...", wraplength=560, justify="left"))
            self.problems_label.pack(side="left", fill="x", expand=True)
        else:
            self.save_button = self.problems_label = None
        widgets.InfoPanel(self)             # the "i"s show here, inside the editor

        body = ttk.Frame(self)
        body.pack(fill="both", expand=True)
        left = ttk.Frame(body)
        left.pack(side="left", fill="y")
        self.build_bat(left)
        self.build_gloves(left)
        colors = ttk.LabelFrame(left, text="Colours that change", padding=(6, 2, 6, 4))
        colors.pack(fill="both", expand=True)
        intro = ttk.Frame(colors)
        intro.pack(fill="x")
        self.intro = widgets.status(ttk.Label(intro, text="...", foreground=widgets.GREY, wraplength=430, justify="left"))
        self.intro.pack(side="left", fill="x", expand=True)
        self._info(intro, "The colours that change", "colors").pack(side="right", anchor="n")
        add = ttk.Frame(colors)
        add.pack(side="bottom", fill="x", pady=(2, 0))
        widgets.tip(ttk.Button(add, text="Add a colour row", command=self.add_row),
                    "For a colour that isn't listed: the new row picks every colour in a hue range you set.").pack(
            side="left")
        self.rows_box = widgets.Scrolled(colors, height=120)
        self.rows_box.pack(fill="both", expand=True)

        right = ttk.LabelFrame(body, text="Before / after", padding=4)
        right.pack(side="left", fill="both", expand=True, padx=(8, 0))
        texbar = ttk.Frame(right)
        texbar.pack(side="bottom", fill="x", pady=(4, 0))
        ttk.Label(texbar, text="Direct PNG:").pack(side="left")
        texlist = ttk.Frame(texbar)
        texlist.pack(side="left", fill="both", expand=True, padx=4)
        self.texture_list = tk.Listbox(texlist, selectmode="extended", exportselection=False, height=7, width=25)
        self.texture_list.pack(side="left", fill="both", expand=True)
        texscroll = ttk.Scrollbar(texlist, orient="vertical", command=self.texture_list.yview)
        texscroll.pack(side="right", fill="y")
        self.texture_list.configure(yscrollcommand=texscroll.set)
        ttk.Button(texbar, text="Replace selected...", command=self.pick_texture_overrides).pack(side="left")
        ttk.Button(texbar, text="Clear", command=self.clear_texture_overrides).pack(side="left", padx=(4, 0))
        widgets.tip(self.texture_list, "Every readable texture in both the high- and low-detail body models is listed. "
                                     "Select one or more, then choose the same number of PNG files; only the files you pick are used.")
        portraits = ttk.Frame(right)
        portraits.pack(side="bottom", fill="x", pady=(4, 0))
        ttk.Label(portraits, text="Portraits:").pack(side="left")
        self.side_portrait_button = ttk.Button(portraits, text="Replace side...",
                                               command=lambda: self.pick_portrait_override("side"))
        self.side_portrait_button.pack(side="left", padx=(4, 0))
        self.front_portrait_button = ttk.Button(portraits, text="Replace front...",
                                                command=lambda: self.pick_portrait_override("front"))
        self.front_portrait_button.pack(side="left", padx=(4, 0))
        ttk.Button(portraits, text="Clear portraits", command=self.clear_portrait_overrides).pack(side="left", padx=(4, 0))
        self.preview_note = widgets.status(ttk.Label(right, text="Left of each pair: now. Right: the recolor.",
                                                     foreground=widgets.GREY, wraplength=300, justify="left"))
        self.preview_note.pack(side="bottom", fill="x")
        self.canvas = tk.Canvas(right, width=300, height=200, highlightthickness=0, background=hexrgb(PREVIEW_BG[:3]))
        self.canvas.pack(fill="both", expand=True)
        self._canvas_size = None
        self._room_seen, self._room_job = None, None
        if not self.own_window:         # in another window (git-10's character window): fit again to the room it
            self.master.bind("<Configure>", lambda e: self._room_changed(), add="+")   # really gives, once it has one
        self.canvas.bind("<Configure>", lambda e: self._canvas_resized())
        widgets.tip(self.canvas, "Every model texture is shown, including textures that are not currently changing, plus "
                                 "both portraits and the bat: now on the left, result on the right.")

    def build_bat(self, parent):
        bat = ttk.LabelFrame(parent, text="The bat", padding=(6, 2, 6, 4))
        bat.pack(side="bottom", fill="x", pady=(6, 0))
        self.bat_frame = bat
        self.bat_on, self.bat_mode = tk.BooleanVar(value=True), tk.StringVar(value="follow")
        self.bat_rgb, self.bat_hand = None, None
        line = ttk.Frame(bat)
        line.pack(fill="x")
        self.bat_check = ttk.Checkbutton(line, text="Also recolor the bat", variable=self.bat_on,
                                         command=self.bat_changed)
        self.bat_check.pack(side="left")
        self._info(line, "The bat", "bat").pack(side="right")
        modes = ttk.Frame(bat)
        modes.pack(fill="x", padx=(20, 0))
        self.bat_follow = ttk.Radiobutton(modes, text="The same colour changes", variable=self.bat_mode,
                                          value="follow", command=self.bat_changed)
        self.bat_follow.pack(side="left")
        self.bat_own = ttk.Radiobutton(modes, text="A colour of its own:", variable=self.bat_mode, value="own",
                                       command=self.bat_changed)
        self.bat_own.pack(side="left", padx=(10, 0))
        self.bat_box = widgets.tip(swatch(modes, (60, 60, 60), relief="sunken"), "The bat's own colour.")
        self.bat_box.pack(side="left", padx=4)
        self.bat_pick = ttk.Button(modes, text="Pick a colour...", command=self.pick_bat_color)
        self.bat_pick.pack(side="left")
        direct = ttk.Frame(bat)
        direct.pack(fill="x", padx=(20, 0), pady=(3, 1))
        ttk.Label(direct, text="Direct PNG:").pack(side="left")
        self.bat_texture_list = tk.Listbox(direct, selectmode="extended", exportselection=False, height=4, width=18)
        self.bat_texture_list.pack(side="left", fill="x", expand=True, padx=4)
        ttk.Button(direct, text="Replace selected...", command=self.pick_bat_texture_overrides).pack(side="left")
        ttk.Button(direct, text="Clear", command=self.clear_bat_texture_overrides).pack(side="left", padx=(4, 0))
        widgets.tip(self.bat_texture_list, "Select one or more bat textures and then exactly the PNG files you want. Nothing adjacent is imported.")
        self.bat_note = widgets.status(ttk.Label(bat, text="...", foreground=widgets.GREY, wraplength=440, justify="left"))
        self.bat_note.pack(fill="x")

    def build_gloves(self, parent):
        gloves = ttk.LabelFrame(parent, text="The gloves", padding=(6, 2, 6, 4))
        self.glove_frame = gloves
        ttk.Label(gloves, text="Direct PNG:").pack(anchor="w")
        row = ttk.Frame(gloves)
        row.pack(fill="x")
        box = ttk.Frame(row)
        box.pack(side="left", fill="both", expand=True)
        self.glove_texture_list = tk.Listbox(box, selectmode="extended", exportselection=False, height=5, width=28)
        self.glove_texture_list.pack(side="left", fill="both", expand=True)
        scroll = ttk.Scrollbar(box, orient="vertical", command=self.glove_texture_list.yview)
        scroll.pack(side="right", fill="y")
        self.glove_texture_list.configure(yscrollcommand=scroll.set)
        buttons = ttk.Frame(row)
        buttons.pack(side="left", padx=(4, 0), anchor="n")
        ttk.Button(buttons, text="Replace selected...", command=self.pick_glove_texture_overrides).pack(fill="x")
        ttk.Button(buttons, text="Clear", command=self.clear_glove_texture_overrides).pack(fill="x", pady=(4, 0))
        widgets.tip(self.glove_texture_list, "Fielding gloves are separate character model files. Left and right glove "
                                             "textures are listed independently when that character has readable glove models.")

    def _info(self, parent, title, key):
        icon = widgets.info(parent, title, self.rc.DATA.get(key))
        return icon if icon is not None else ttk.Frame(parent)

    # --- the base list (stock, then added: ours from characters/, then the player's imported ones)

    def load_bases(self, want=None):
        entries = self.rc.bases(self.game, self.defs)
        try:
            import edition              # a trimmed download offers its own characters only (the beta: Rosalina)
            offered = {i for i, (p, _) in self.defs.items() if p is None or edition.offers("characters", p)}
        except ImportError:
            offered = set(self.defs)
        self.base_info, labels = {}, []
        for b in entries:
            if b["added"] and b["id"] not in offered:
                continue
            label = b["name"] if not b["added"] else f"{b['name']} (added)"
            self.base_info[label] = b
            if self.active_names is None or b["name"].lower() in self.active_names:
                labels.append(label)
        stock = sorted(l for l in labels if not self.base_info[l]["added"])
        added = sorted(l for l in labels if self.base_info[l]["added"])
        imported = []
        try:
            import charpack
            for item in charpack.list_imported_quiet():
                label = f"{item['name']} (imported)"
                if label not in self.base_info and not any(self.base_info[l]["name"].lower() == item["name"].lower()
                                                           for l in labels):
                    self.imported[label] = item
                    self.base_info[label] = {"id": item["id"], "name": item["name"], "wheel": None, "added": True,
                                             "imported": True}
                    if self.active_names is None or item["name"].lower() in self.active_names:
                        imported.append(label)
        except Exception:
            pass                        # no imported characters to offer
        values = stock + added + sorted(imported)
        if want is not None and not any(self.base_info[l]["name"].lower() == str(want).lower() for l in values):
            self.base_info[str(want)] = {"id": None, "name": str(want), "wheel": None, "added": True}
            values.append(str(want))    # a base that isn't here (removed?): shown, and refused in plain words
        self.base_cb.configure(values=values)

    def label_for(self, name):
        name = str(name).strip().lower()
        for label, b in self.base_info.items():
            if b["name"].lower() == name:
                return label
        try:
            cid = self.rc.char_id(name)
            return next((l for l, b in self.base_info.items() if b["id"] == cid), None)
        except AssertionError:
            return None

    def base_ref(self):
        """The base as a recipe names it."""
        b = self.base_info.get(self.base.get())
        return b["name"] if b else self.base.get()

    def base_name(self):
        return self.base_ref()

    def ensure_imported(self):
        """An imported base's definition, readable (charpack.materialize into a scratch folder), in self.defs."""
        b = self.base_info.get(self.base.get(), {})
        if not b.get("imported") or any(d.get("name", "").lower() == b["name"].lower() for _, d in self.defs.values()):
            return
        if self._materialized is None:
            import charpack, tempfile
            work = Path(tempfile.gettempdir()) / "sluggers-recolor-bases"
            try:
                self._materialized = charpack.materialize(charpack.default_dest(create=False), self.game.path, work)
            except Exception:
                self._materialized = []
        for d in self._materialized:
            if d["name"].lower() == b["name"].lower():
                cid = int(str(d["id"]), 0)
                key = cid if cid not in self.defs else 0x1000 + len(self.defs)
                self.defs[key] = (None, d)

    # --- state

    def set_recipe(self, d, path=None):
        """Load a recipe dict (path: its file, when it's edited in place)."""
        rc = self.rc
        self._ready = False             # no checks while it loads
        self.original = json.loads(json.dumps(d or {}))
        self.path = Path(path) if path else None
        self.texture_overrides = {}
        for k, value in (self.original.get("texture_overrides") or {}).items():
            try:
                q = Path(value)
                if not q.is_absolute():
                    q = Path(self.rc.ROOT) / "recolors" / q
                key = str(k)
                if ":" in key:
                    file_s, tex_s = key.split(":", 1)
                    self.texture_overrides[(int(file_s), int(tex_s))] = str(q)
                else:
                    # Upgrade 4 and older applied an unscoped texture index to both high and low models.
                    # Mirror it into both rows so opening/saving an old recolor keeps the same visible result.
                    self.texture_overrides[(0, int(key))] = str(q)
                    self.texture_overrides[(1, int(key))] = str(q)
            except (ValueError, TypeError):
                pass
        self.bat_texture_overrides = {}
        for k, value in (self.original.get("bat_texture_overrides") or {}).items():
            try:
                q = Path(value)
                if not q.is_absolute():
                    q = Path(self.rc.ROOT) / "recolors" / q
                self.bat_texture_overrides[int(k)] = str(q)
            except (ValueError, TypeError):
                pass
        self.glove_texture_overrides = {}
        for k, value in (self.original.get("glove_texture_overrides") or {}).items():
            try:
                file_s, tex_s = str(k).split(":", 1)
                q = Path(value)
                if not q.is_absolute():
                    q = Path(self.rc.ROOT) / "recolors" / q
                self.glove_texture_overrides[(int(file_s), int(tex_s))] = str(q)
            except (ValueError, TypeError):
                pass
        self.portrait_overrides = {}
        for view, value in (self.original.get("portrait_overrides") or {}).items():
            if view not in ("side", "front"):
                continue
            try:
                q = Path(value)
                if not q.is_absolute():
                    q = Path(self.rc.ROOT) / "recolors" / q
                self.portrait_overrides[view] = str(q)
            except (ValueError, TypeError):
                pass
        self._new_id = None
        r, ed = self.original, self.original.get("_editor", {})
        style.title(self.winfo_toplevel(), "Edit recolor" if self.path else "New recolor") if self.own_window else None
        self.load_bases(r.get("base"))
        label = self.label_for(r["base"]) if r.get("base") is not None else None
        if label is None:
            label = "Green Yoshi" if "Green Yoshi" in self.base_info else sorted(self.base_info)[0]
        self.base.set(label)
        self.name.set(r.get("name", ""))
        self.swatch_picked = bool(r.get("swatch"))
        self.swatch_var.set(r.get("swatch") or "")
        self.ensure_imported()
        self.load_clusters()
        rules, colors = r.get("recolor") or [], ed.get("colors") or []
        rows, used = [], set()
        for k, rule in enumerate(rules):
            match = next((i for i, c in enumerate(self.clusters) if i not in used and list(c["hue"]) ==
                          list(rule.get("hue", [])) and c["min_sat"] == rule.get("min_sat", 0.25) and
                          list(c.get("textures") or []) == list(rule.get("textures") or [])), None)
            if match is not None:
                used.add(match)
                color = self.clusters[match]
            else:
                color = self.safe(lambda: rc.color_in(self.game, self.base_ref(), list(rule["hue"]),
                                                      rule.get("min_sat", 0.25), rule.get("textures"),
                                                      defs=self.defs)) or {
                    "hue": list(rule.get("hue", [0, 0])), "min_sat": rule.get("min_sat", 0.25), "rgb": (128, 128, 128),
                    "share": 0}
            target = colors[k] if k < len(colors) else ed.get("rgb") or rc.target_of(color, rule)
            rows.append(ColorRow(self, color, target, on=True, rule=rule, added=match is None))
        rows += [ColorRow(self, c) for i, c in enumerate(self.clusters) if i not in used]
        self.rows = rows
        self.touched = not self.original              # a new recolor: its choices are the editor's
        # Do not force a colour row on. A PNG/portrait-only recolor must stay colour-neutral, and reopening it
        # must not silently tick the first row and change the model on the next save.
        # the bat
        bat = r.get("bat", MISSING)
        self.bat_orig, self.bat_edited = bat, False
        self.bat_explicit = not self.original         # a new recolor's bat is on and says so ("follow")
        mode = ed.get("bat")
        self.bat_rgb = tuple(ed["bat_rgb"]) if ed.get("bat_rgb") else None
        self.bat_hand = None
        if bat is MISSING:
            self.bat_on.set(True if not self.original else self.auto_bat())
            self.bat_mode.set("follow")
        elif bat == "follow":
            self.bat_on.set(True), self.bat_mode.set("follow")
        elif bat == "keep" or not bat:
            self.bat_on.set(False), self.bat_mode.set("follow")
        else:
            self.bat_on.set(True), self.bat_mode.set("own")
            if not (mode in ("custom", "own") and self.bat_rgb):
                self.bat_hand = list(bat)             # a hand-made recipe's bat rules, kept as they are
        self.show_bat_color()
        self.show_rows()
        self.refresh_texture_list()
        self.refresh_bat_texture_list()
        self.refresh_glove_texture_list()
        self.refresh_portrait_buttons()
        self.base_checked()
        self.color_follow()
        self._ready = True
        self.changed()

    def safe(self, fn):
        try:
            return fn()
        except Exception:
            return None

    def default_main(self):
        """A new recolor: the main colour ticked, turning to the opposite side of the colour wheel."""
        row = self.rows[0]
        h, s, v = colorsys.rgb_to_hsv(*(c / 255 for c in row.color["rgb"]))
        row.set_target(tuple(round(c * 255) for c in colorsys.hsv_to_rgb((h + 0.5) % 1, max(s, 0.6), max(v, 0.6))),
                       edit=False)
        row.on.set(True)

    def load_clusters(self):
        top = self.winfo_toplevel()
        try:
            top.configure(cursor="watch")
            top.update_idletasks()
        except tk.TclError:
            pass
        self.unreadable = None
        try:
            self.clusters = self.rc.base_colors(self.game, self.base_ref(), defs=self.defs)
        except AssertionError:          # a base that isn't here: no colours (validate says why)
            self.clusters = []
        except Exception as e:          # textures the tool can't decode
            self.clusters, self.unreadable = [], type(e).__name__
        finally:
            try:
                top.configure(cursor="")
            except tk.TclError:
                pass

    def show_rows(self):
        for w in self.rows_box.inner.winfo_children():
            w.destroy()
        for i, row in enumerate(self.rows):
            row.build(self.rows_box.inner, i).pack(fill="x")
        if not self.rows:
            ttk.Label(self.rows_box.inner, foreground=widgets.GREY, wraplength=420, justify="left",
                      text=f"The tool can't read {self.base_ref()}'s textures, so it can't recolor it." if
                      self.unreadable else "No colours found in this character's textures: add a colour row.").pack(
                anchor="w")
        base = self.base_ref()
        self.intro.configure(text=f"The colours in {base}'s textures, largest first. Tick a colour to change it and "
                                  f"give it its own new colour.")
        self.fit()

    def fit(self):
        """The rows list as tall as its rows, within the room the editor has (its own window: 860 x 620; in another
        window, what that gives it); it scrolls only when they don't fit."""
        try:
            self.update_idletasks()
        except tk.TclError:
            return
        W, H = self.room()
        for lab in self.howto.body.winfo_children():     # the How to's lines wrap at the width they'll have
            lab.configure(wraplength=W - 40)
        if self.credit_label is not None:
            self.credit_label.configure(wraplength=W - 110)
        if self.problems_label is not None:
            self.problems_label.configure(wraplength=max(200, W - 220))
        c, pc = self.rows_box.canvas, self.canvas
        c.configure(width=self.rows_box.inner.winfo_reqwidth())
        pc.configure(width=140)
        self.preview_note.configure(wraplength=140)
        self.update_idletasks()
        other_w = self.winfo_reqwidth() - 140
        width = max(140, min(360, W - other_w))
        pc.configure(width=width)
        self.preview_note.configure(wraplength=width)
        self.update_idletasks()
        other = self.winfo_reqheight() - int(c.cget("height"))
        c.configure(height=max(40, min(self.rows_box.inner.winfo_reqheight(), H - other)))
        self.update_idletasks()
        self.rows_box.refit()

    def rewrap(self, width):
        """The How to's lines and the credit line wrap at the editor's own width (when it's resized)."""
        if width > 200:
            for lab in self.howto.body.winfo_children():
                lab.configure(wraplength=width - 40)
            if self.credit_label is not None:
                self.credit_label.configure(wraplength=width - 110)

    def room(self):
        if self.own_window:
            return ROOM
        m = self.master
        w, h = m.winfo_width(), m.winfo_height()
        if w <= 1 or h <= 1:
            try:
                w, h = int(m.cget("width")), int(m.cget("height"))
            except (tk.TclError, ValueError):
                w = h = 0
        return (w if w > 1 else ROOM[0]), (h if h > 1 else ROOM[1])

    def auto_bat(self):
        """The automatic choice (a recipe with no "bat"): True when the bat follows the recolor."""
        try:
            return bool(self.rc.base_of(self.game, self.base_ref(), self.defs).own_bats())
        except Exception:
            return False

    def base_checked(self):
        """The bat's state for this base: greyed out with its reason when the tool can't recolor it."""
        try:
            self.bat_why = self.rc.bat_problem(self.game, self.rc.base_of(self.game, self.base_ref(), self.defs))
        except AssertionError:
            self.bat_why = None
        widgets.set_enabled(self.bat_frame, not self.bat_why)

    def base_changed(self):
        before = [r.target for r in self.rows if r.on.get()]
        self.ensure_imported()
        self.load_clusters()
        self.rows = [ColorRow(self, c) for c in self.clusters]
        if self.rows and before:
            self.rows[0].set_target(before[0], edit=False)
            self.rows[0].on.set(True)
        self.texture_overrides = {}
        self.bat_texture_overrides = {}
        self.glove_texture_overrides = {}
        self.portrait_overrides = {}
        self.refresh_texture_list()
        self.refresh_bat_texture_list()
        self.refresh_glove_texture_list()
        self.refresh_portrait_buttons()
        self.touched = True
        if not self.bat_edited and self.bat_orig is MISSING and not self.bat_explicit:
            self.bat_on.set(self.auto_bat())
        self.show_rows()
        self.base_checked()
        self.refresh_texture_list()
        self.refresh_bat_texture_list()
        self.refresh_glove_texture_list()
        self.color_follow()
        self.changed()

    def row_edited(self, row):
        self.touched = True
        if self.bat_mode.get() == "own" and self.bat_hand is None and self.bat_rgb is not None:
            self.bat_edited = True      # the bat's own colour follows which colours are ticked
        self.color_follow()
        self.changed()

    def add_row(self):
        taken = [r.color["hue"] for r in self.rows]
        lo = next((h for h in range(0, 360, 20) if not any(
            (a <= h <= b) if a <= b else (h >= a or h <= b) for a, b in taken)), 0)
        color = self.safe(lambda: self.rc.color_in(self.game, self.base_ref(), [lo, (lo + 20) % 360], 0.25,
                                                   defs=self.defs)) or {"hue": [lo, lo + 20], "min_sat": 0.25,
                                                                        "rgb": (128, 128, 128), "share": 0}
        row = ColorRow(self, color, added=True)
        row.edited = True
        self.rows.append(row)
        self.show_rows()
        self.touched = True
        self.changed()
        return row

    def remove_row(self, row):
        self.rows.remove(row)
        self.show_rows()
        self.row_edited(row)

    def swatch_picked_now(self):
        self.swatch_picked = True
        self.color_follow()
        self.changed()

    def color_follow(self):
        """The swatch follows the first ticked row's new colour until one is chosen."""
        on = [r for r in self.rows if r.on.get()]
        if not self.swatch_picked:
            self.swatch_var.set(self.rc.nearest_swatch(on[0].target) if on else "")
        rgb = self.rc.SWATCH_RGB.get(self.swatch_var.get())
        self.swatch_box.configure(bg=hexrgb(rgb or (128, 128, 128)))

    # --- direct texture PNG replacements

    def _model_texture_rows(self):
        """[(model file, texture index, image)] for every readable body texture in files 0 and 1."""
        out = []
        for file_index in (0, 1):
            try:
                textures = self.rc._textures_for_block(self.game, self.base_ref(), file_index, self.defs)
            except Exception:
                textures = []
            for i, img in textures:
                out.append((file_index, i, img))
        return out

    def refresh_texture_list(self):
        """Show all high + low body textures; a * means this recipe replaces that exact texture with a PNG."""
        if not hasattr(self, "texture_list"):
            return
        self.texture_list.delete(0, "end")
        self._texture_row_keys = []
        names = {0: "High", 1: "Low"}
        for file_index, i, img in self._model_texture_rows():
            key = (file_index, i)
            mark = " *" if key in self.texture_overrides else ""
            self.texture_list.insert("end", f"{names[file_index]} texture {i} ({img.width}x{img.height}){mark}")
            self._texture_row_keys.append(key)

    def pick_texture_overrides(self):
        picks = list(self.texture_list.curselection())
        if not picks:
            messagebox.showinfo("Replace texture PNG", "Select one or more textures in the Direct PNG list first.",
                                parent=self.winfo_toplevel())
            return
        files = list(filedialog.askopenfilenames(title="Choose replacement PNG texture(s)",
                                                filetypes=[("PNG pictures", "*.png"), ("All files", "*.*")]))
        if not files:
            return
        if len(files) != len(picks):
            messagebox.showwarning("Replace texture PNG",
                                   f"Select {len(picks)} PNG file(s), one for each selected texture. You chose {len(files)}.",
                                   parent=self.winfo_toplevel())
            return
        for row, filename in zip(picks, files):
            try:
                key = self._texture_row_keys[row]
                Image.open(filename).verify()
                self.texture_overrides[key] = filename
            except (OSError, ValueError, IndexError) as e:
                messagebox.showwarning("Replace texture PNG", f"{Path(filename).name} can't be used: {e}",
                                       parent=self.winfo_toplevel())
                return
        self.touched = True
        self.refresh_texture_list()
        self.changed()

    def clear_texture_overrides(self):
        picks = list(self.texture_list.curselection())
        if picks:
            for row in picks:
                try:
                    self.texture_overrides.pop(self._texture_row_keys[row], None)
                except IndexError:
                    pass
        else:
            self.texture_overrides.clear()
        self.touched = True
        self.refresh_texture_list()
        self.changed()

    def refresh_portrait_buttons(self):
        """Mark portrait buttons when this recolor has an explicit replacement PNG."""
        if hasattr(self, "side_portrait_button"):
            self.side_portrait_button.configure(text="Side replaced *" if "side" in self.portrait_overrides else "Replace side...")
        if hasattr(self, "front_portrait_button"):
            self.front_portrait_button.configure(text="Front replaced *" if "front" in self.portrait_overrides else "Replace front...")

    def pick_portrait_override(self, view):
        filename = filedialog.askopenfilename(title=f"Choose replacement {view} portrait PNG",
                                              filetypes=[("PNG pictures", "*.png"), ("All files", "*.*")])
        if not filename:
            return
        try:
            Image.open(filename).verify()
        except OSError as e:
            messagebox.showwarning("Replace portrait PNG", f"{Path(filename).name} can't be used: {e}",
                                   parent=self.winfo_toplevel())
            return
        self.portrait_overrides[view] = filename
        self.touched = True
        self.refresh_portrait_buttons()
        self.changed()

    def clear_portrait_overrides(self):
        self.portrait_overrides.clear()
        self.touched = True
        self.refresh_portrait_buttons()
        self.changed()

    def refresh_glove_texture_list(self):
        if not hasattr(self, "glove_texture_list"):
            return
        self.glove_texture_list.delete(0, "end")
        self._glove_row_keys = []
        for file_index, side in self.rc.GLOVE_FILES:
            try:
                textures = self.rc._textures_for_block(self.game, self.base_ref(), file_index, self.defs)
            except Exception:
                textures = []
            for i, img in textures:
                key = (file_index, i)
                mark = " *" if key in self.glove_texture_overrides else ""
                self.glove_texture_list.insert("end", f"{side.capitalize()} glove {i} ({img.width}x{img.height}){mark}")
                self._glove_row_keys.append(key)
        if self._glove_row_keys:
            if hasattr(self, "glove_frame") and not self.glove_frame.winfo_manager():
                self.glove_frame.pack(side="bottom", fill="x", pady=(6, 0))
        elif hasattr(self, "glove_frame"):
            self.glove_frame.pack_forget()

    def pick_glove_texture_overrides(self):
        picks = [r for r in self.glove_texture_list.curselection() if r < len(getattr(self, "_glove_row_keys", []))]
        if not picks:
            messagebox.showinfo("Replace glove PNG", "Select one or more glove textures first.",
                                parent=self.winfo_toplevel())
            return
        files = list(filedialog.askopenfilenames(title="Choose replacement glove PNG texture(s)",
                                                filetypes=[("PNG pictures", "*.png"), ("All files", "*.*")]))
        if not files:
            return
        if len(files) != len(picks):
            messagebox.showwarning("Replace glove PNG",
                                   f"Select {len(picks)} PNG file(s), one for each selected glove texture. You chose {len(files)}.",
                                   parent=self.winfo_toplevel())
            return
        for row, filename in zip(picks, files):
            try:
                key = self._glove_row_keys[row]
                Image.open(filename).verify()
                self.glove_texture_overrides[key] = filename
            except (OSError, ValueError, IndexError) as e:
                messagebox.showwarning("Replace glove PNG", f"{Path(filename).name} can't be used: {e}",
                                       parent=self.winfo_toplevel())
                return
        self.touched = True
        self.refresh_glove_texture_list()
        self.changed()

    def clear_glove_texture_overrides(self):
        picks = [r for r in self.glove_texture_list.curselection() if r < len(getattr(self, "_glove_row_keys", []))]
        if picks:
            for row in picks:
                self.glove_texture_overrides.pop(self._glove_row_keys[row], None)
        else:
            self.glove_texture_overrides.clear()
        self.touched = True
        self.refresh_glove_texture_list()
        self.changed()

    def refresh_bat_texture_list(self):
        if not hasattr(self, "bat_texture_list"):
            return
        self.bat_texture_list.delete(0, "end")
        try:
            b = self.rc.base_of(self.game, self.base_ref(), self.defs)
            entry = b.bat_entry()
            member = self.rc.bat_block(entry)
            textures = list(enumerate(self.rc.Model(bytes(entry[member:])).textures))
        except Exception:
            textures = []
        for i, tex in textures:
            try:
                img = self.rc.decode(bytes(entry[member:]), tex)
                size = f"{img.width}x{img.height}"
            except Exception:
                size = "?"
            mark = " *" if i in self.bat_texture_overrides else ""
            self.bat_texture_list.insert("end", f"Bat texture {i} ({size}){mark}")

    def pick_bat_texture_overrides(self):
        picks = list(self.bat_texture_list.curselection())
        if not picks:
            messagebox.showinfo("Replace bat PNG", "Select one or more bat textures first.", parent=self.winfo_toplevel())
            return
        files = list(filedialog.askopenfilenames(title="Choose replacement bat PNG texture(s)",
                                                filetypes=[("PNG pictures", "*.png"), ("All files", "*.*")]))
        if not files:
            return
        if len(files) != len(picks):
            messagebox.showwarning("Replace bat PNG", f"Select {len(picks)} PNG file(s), one for each selected bat texture. You chose {len(files)}.", parent=self.winfo_toplevel())
            return
        for row, filename in zip(picks, files):
            try:
                index = int(self.bat_texture_list.get(row).split()[2])
                Image.open(filename).verify()
                self.bat_texture_overrides[index] = filename
            except (OSError, ValueError, IndexError) as e:
                messagebox.showwarning("Replace bat PNG", f"{Path(filename).name} can't be used: {e}", parent=self.winfo_toplevel())
                return
        self.bat_on.set(True)
        self.touched = True
        self.refresh_bat_texture_list()
        self.changed()

    def clear_bat_texture_overrides(self):
        picks = list(self.bat_texture_list.curselection())
        if picks:
            for row in picks:
                try:
                    index = int(self.bat_texture_list.get(row).split()[2])
                    self.bat_texture_overrides.pop(index, None)
                except (ValueError, IndexError):
                    pass
        else:
            self.bat_texture_overrides.clear()
        self.touched = True
        self.refresh_bat_texture_list()
        self.changed()

    # --- the bat

    def pick_bat_color(self):
        rgb, _ = colorchooser.askcolor(color=hexrgb(self.bat_rgb or (60, 60, 60)), parent=self.winfo_toplevel(),
                                       title="The bat's colour")
        if rgb:
            self.set_bat_color(rgb)

    def set_bat_color(self, rgb):
        self.bat_rgb, self.bat_hand = tuple(round(c) for c in rgb), None
        self.bat_on.set(True)
        self.bat_mode.set("own")
        self.bat_changed()

    def bat_changed(self):
        self.bat_edited = True
        if self.bat_mode.get() == "own" and self.bat_rgb is None and self.bat_hand is None:
            on = [r for r in self.rows if r.on.get()]
            self.bat_rgb = on[0].target if on else (60, 60, 60)
        self.show_bat_color()
        self.changed()

    def show_bat_color(self):
        rgb = self.bat_rgb
        if rgb is None and self.bat_hand:
            rgb = self.rc.target_of({"rgb": (128, 128, 128)}, self.bat_hand[0])
        self.bat_box.configure(bg=hexrgb(rgb or (60, 60, 60)))

    def bat_value(self):
        """The recipe's "bat" as the bat row stands (MISSING: none, its automatic meaning)."""
        if not self.bat_edited and not self.bat_explicit:
            return self.bat_orig
        if not self.bat_on.get():
            return "keep"
        if self.bat_mode.get() == "follow":
            return "follow"
        if self.bat_hand is not None:
            return self.bat_hand
        return [{k: v for k, v in self.rc.rule_to(r.color, self.bat_rgb or (60, 60, 60)).items()
                 if k not in ("textures", "region")} for r in self.rows if r.on.get()]

    def show_bat_note(self, r):
        base = self.base_ref()
        if self.bat_why:
            text = f"{base}'s bat can't be recolored ({self.bat_why}): it stays as it is. This doesn't stop the save."
        elif not self.bat_on.get():
            text = f"{base}'s bat stays as it is."
            if self.bat_value() is MISSING:
                text = f"Automatic, as {base}'s own colours do: they share one bat, so it stays as it is."
        else:
            try:
                rules = self.rc.bat_rules(r, self.game, self.rc.base_of(self.game, base, self.defs))
            except Exception:
                rules = []
            auto = self.bat_value() is MISSING
            if not rules:
                text = f"{base}'s bat stays as it is."
            elif self.bat_pairs == 0 and self._shown_gen:
                text = f"None of these colours are on {base}'s bat, so it stays as it is."
            elif self.bat_mode.get() == "own":
                text = f"The ticked colours on {base}'s bat turn this colour."
            else:
                text = f"{base}'s bat takes the same colour changes."
            if auto:
                text = f"Automatic, as {base}'s own colours do. " + text
        self.bat_note.configure(text=text)
        for w in (self.bat_follow, self.bat_own, self.bat_pick):
            w.state(["!disabled"] if self.bat_on.get() and not self.bat_why else ["disabled"])

    # --- the recipe

    def recipe(self):
        """The recipe as the editor stands (a dict; the recipe's own keys kept, and as they were where unedited)."""
        r = dict(self.original)
        r["name"] = self.name.get().strip()
        same = self.original.get("base") is not None and self.label_for(self.original["base"]) == self.base.get()
        r["base"] = self.original["base"] if same else self.base_ref()     # as the recipe wrote it (e.g. an id)
        r["swatch"] = self.swatch_var.get()
        if "id" in self.original and self.target() == self.path:   # renamed: a new recolor beside the old one
            r["id"] = self.original["id"]
        else:                           # the patcher needs every recipe's id (Nick: Patch refused one without)
            r["id"] = f"0x{self.new_id():02X}"
        r["recolor"] = [row.rule_out() for row in self.rows if row.on.get()]
        if self.texture_overrides:
            r["texture_overrides"] = {f"{file_index}:{i}": str(path)
                                      for (file_index, i), path in sorted(self.texture_overrides.items())}
        else:
            r.pop("texture_overrides", None)
        if self.glove_texture_overrides:
            r["glove_texture_overrides"] = {f"{file_index}:{i}": str(path)
                                            for (file_index, i), path in sorted(self.glove_texture_overrides.items())}
        else:
            r.pop("glove_texture_overrides", None)
        if self.bat_texture_overrides:
            r["bat_texture_overrides"] = {str(i): str(path) for i, path in sorted(self.bat_texture_overrides.items())}
        else:
            r.pop("bat_texture_overrides", None)
        if self.portrait_overrides:
            r["portrait_overrides"] = {view: str(path) for view, path in sorted(self.portrait_overrides.items())}
        else:
            r.pop("portrait_overrides", None)
        r.update(self.extra)
        bat = self.bat_value()
        if bat is MISSING:
            r.pop("bat", None)
        else:
            r["bat"] = bat
        if self.touched or self.bat_edited:
            on = [row for row in self.rows if row.on.get()]
            mode = "auto" if bat is MISSING else "keep" if bat == "keep" else "follow" if bat == "follow" else \
                "own" if self.bat_hand is None else "hand"
            r["_editor"] = {"colors": [list(row.target) for row in on], "bat": mode,
                            **({"bat_rgb": list(self.bat_rgb)} if mode == "own" and self.bat_rgb else {})}
        return r

    def new_id(self):
        """A new recolor's character id: one past every id in the id folders (characters, recolors) and the imported
        characters, so none is reused. Picked once per recipe."""
        if self._new_id is None:
            ids = [0x65]                # the last stock id: new characters start at 0x66
            for folder in self.id_folders:
                for p in Path(folder).glob("*.json"):
                    try:
                        i = json.loads(p.read_text(encoding="utf8")).get("id")
                        if i is not None:
                            ids.append(int(str(i), 0))
                    except (OSError, ValueError, AttributeError):
                        pass            # not a definition: no id to avoid
            ids += [int(b["id"]) for b in self.base_info.values() if b.get("imported") and b.get("id") is not None]
            ids += [i for i in self.defs if i < 0x1000]    # the build's characters (ours)
            self._new_id = max(ids) + 1
        return self._new_id

    def target(self):
        return self.folder / f"{self.rc.slug(self.name.get().strip() or 'recolor')}.json"

    def problems(self):
        """(what stops a save, warnings that don't): plain sentences."""
        r = self.recipe()
        out, warn = [], []
        if not r["name"]:
            out.append("Give the new character a name.")
        elif self.target() != self.path and self.target().exists():
            out.append(f"There's already a recolor named {r['name']}; pick another name.")
        if self.unreadable:
            out.append(f"The tool can't read {self.base_ref()}'s textures: pick another character.")
        elif not r["recolor"] and not r.get("texture_overrides") and not r.get("bat_texture_overrides") and not r.get("glove_texture_overrides") and not r.get("portrait_overrides"):
            out.append("Tick at least one colour to change, or replace at least one model/bat/glove texture or portrait PNG.")
        if r["name"] and (r["recolor"] or r.get("texture_overrides") or r.get("bat_texture_overrides") or r.get("glove_texture_overrides") or r.get("portrait_overrides")):
            out += self.rc.validate(r, self.game, defs=self.defs, warnings=warn)
        if self.bat_why and self.bat_on.get():
            line = f"{self.base_ref()}'s bat stays as it is: {self.bat_why}."
            if line not in warn:
                warn.append(line)
        return out, warn

    def check(self):
        """What stops a save ([] = it can be saved)."""
        return self.problems()[0]

    # --- after each edit

    def changed(self):
        if not self._ready:
            return
        b = self.base_info.get(self.base.get())
        place = None
        if b:
            try:                                            # the base's square (an added base) or its wheel (git-f3)
                place = self.rc.placement(self.game, b["name"], defs=self.defs, recipe=self.recipe())
            except (AssertionError, KeyError, ValueError, OSError):
                place = None
        if place:                                           # (count leaves this recolor out: it adds one)
            self.wheel_label.configure(text=f"{place['label']}: {place['count']} of {place['max']} "
                                            f"(this makes {place['count'] + 1})")
        else:
            self.wheel_label.configure(text="Its colour wheel: made when the character is.")
        r = self.recipe()
        blocking, warn = self.problems()
        if self.save_button is not None:
            self.save_button.state(["disabled"] if blocking else ["!disabled"])
            if blocking:
                self.problems_label.configure(text="Can't save yet: " + " ".join(blocking), foreground=widgets.RED)
            else:
                self.problems_label.configure(text="Ready to save." + (" " + " ".join(warn) if warn else ""),
                                              foreground=widgets.GREEN if not warn else widgets.AMBER)
        self.show_bat_note(r)
        self.schedule()

    def _room_changed(self):
        size = (self.master.winfo_width(), self.master.winfo_height())
        if size[0] > 1 and size != self._room_seen and not self._closed:
            self._room_seen = size
            if self._room_job:
                self.after_cancel(self._room_job)
            self._room_job = self.after(60, self._refit_room)

    def _refit_room(self):
        self._room_job = None
        if not self._closed:
            self.fit()

    def schedule(self):
        if self._job:
            self.after_cancel(self._job)
        self._job = self.after(250, self._kick)

    def _canvas_resized(self):
        size = (self.canvas.winfo_width(), self.canvas.winfo_height())
        if size != self._canvas_size:
            self._canvas_size = size
            self.schedule()

    def canvas_size(self):
        w, h = self.canvas.winfo_width(), self.canvas.winfo_height()
        if w <= 1 or h <= 1:
            w, h = int(self.canvas.cget("width")), int(self.canvas.cget("height"))
        return w, h

    def _kick(self):
        """The debounced part of an edit: on_change, and a preview made in a worker thread."""
        self._job = None
        if self._closed:
            return
        r = self.recipe()
        if self.on_change:
            self.on_change(r)
        self._gen += 1
        req = (self._gen, dict(r, name=r["name"] or "Preview", swatch=r["swatch"] or "red"), self.canvas_size(),
               dict(self.defs))
        if self._busy:
            self._pending = req
        else:
            self._start(req)

    def _start(self, req):
        self._busy = True
        threading.Thread(target=self._work, args=(req,), daemon=True).start()
        if self._poll_job is None:
            self._poll_job = self.after(30, self._poll)

    def _work(self, req):
        gen, r, size, defs = req
        try:
            pairs = self.rc.preview_pairs(r, self.game, bat=True, defs=defs)
            self._q.put((gen, compose(pairs, size), sum(1 for p in pairs if str(p[0]).startswith("bat")), None))
        except Exception as e:          # the preview is a help, never a blocker
            self._q.put((gen, None, 0, f"{type(e).__name__}: {e}"))

    def _poll(self):
        self._poll_job = None
        if self._closed:
            return
        try:
            gen, img, bats, err = self._q.get_nowait()
        except queue.Empty:
            self._poll_job = self.after(30, self._poll)
            return
        self._busy = False
        if self._pending is not None:
            req, self._pending = self._pending, None
            self._start(req)
        if gen != self._gen:
            return                      # an older edit's picture: the newer one is coming
        self._shown_gen = gen
        self.bat_pairs = bats
        self.canvas.delete("all")
        if img is None:
            self.images = []
            self.preview_note.configure(text=f"No preview: {err}")
        else:
            self.images = [photo(img, zoom=1)]
            self.canvas.create_image(0, 0, image=self.images[0], anchor="nw")
            self.preview_note.configure(text="Left of each pair: now. Right: the recolor.")
        self.show_bat_note(self.recipe())

    def wait_preview(self, timeout=60):
        """Until the preview is up to date (tests)."""
        import time
        t = time.time()
        while (self._job or self._busy or self._pending) and time.time() - t < timeout:
            if self._job:
                self.after_cancel(self._job)
                self._kick()
            self.update()
            time.sleep(0.02)
        return self._shown_gen == self._gen

    # --- save

    def save(self):
        """What Save recolor does: the recipe written into the folder (as it was, when nothing changed), on_save
        called; the saved path, or None when something stops it."""
        blocking, _ = self.problems()
        if blocking:
            if self.show_save:
                messagebox.showwarning("Recolor", "\n".join(blocking), parent=self.winfo_toplevel())
            return None
        r = self.recipe()
        target = self.target()
        target.parent.mkdir(parents=True, exist_ok=True)
        if self.texture_overrides:
            slug = self.rc.slug(r["name"] or "recolor")
            asset_dir = target.parent / "texture-overrides" / slug
            asset_dir.mkdir(parents=True, exist_ok=True)
            saved = {}
            for (file_index, i), source in sorted(self.texture_overrides.items()):
                source = Path(source)
                dest = asset_dir / f"model-{file_index}-texture-{i}.png"
                if source.resolve() != dest.resolve():
                    shutil.copy2(source, dest)
                saved[f"{file_index}:{i}"] = dest.relative_to(target.parent).as_posix()
            r["texture_overrides"] = saved
            self.texture_overrides = {}
            for key, rel in saved.items():
                file_s, tex_s = key.split(":", 1)
                self.texture_overrides[(int(file_s), int(tex_s))] = str(target.parent / rel)
        if self.glove_texture_overrides:
            slug = self.rc.slug(r["name"] or "recolor")
            asset_dir = target.parent / "texture-overrides" / slug / "gloves"
            asset_dir.mkdir(parents=True, exist_ok=True)
            saved = {}
            for (file_index, i), source in sorted(self.glove_texture_overrides.items()):
                source = Path(source)
                dest = asset_dir / f"glove-{file_index}-texture-{i}.png"
                if source.resolve() != dest.resolve():
                    shutil.copy2(source, dest)
                saved[f"{file_index}:{i}"] = dest.relative_to(target.parent).as_posix()
            r["glove_texture_overrides"] = saved
            self.glove_texture_overrides = {}
            for key, rel in saved.items():
                file_s, tex_s = key.split(":", 1)
                self.glove_texture_overrides[(int(file_s), int(tex_s))] = str(target.parent / rel)
        if self.bat_texture_overrides:
            slug = self.rc.slug(r["name"] or "recolor")
            asset_dir = target.parent / "texture-overrides" / slug / "bat"
            asset_dir.mkdir(parents=True, exist_ok=True)
            saved = {}
            for i, source in sorted(self.bat_texture_overrides.items()):
                source = Path(source)
                dest = asset_dir / f"texture-{i}.png"
                if source.resolve() != dest.resolve():
                    shutil.copy2(source, dest)
                saved[str(i)] = dest.relative_to(target.parent).as_posix()
            r["bat_texture_overrides"] = saved
            self.bat_texture_overrides = {int(i): str(target.parent / rel) for i, rel in saved.items()}
        if self.portrait_overrides:
            slug = self.rc.slug(r["name"] or "recolor")
            asset_dir = target.parent / "texture-overrides" / slug / "portraits"
            asset_dir.mkdir(parents=True, exist_ok=True)
            saved = {}
            for view, source in sorted(self.portrait_overrides.items()):
                source = Path(source)
                dest = asset_dir / f"{view}.png"
                if source.resolve() != dest.resolve():
                    shutil.copy2(source, dest)
                saved[view] = dest.relative_to(target.parent).as_posix()
            r["portrait_overrides"] = saved
            self.portrait_overrides = {view: str(target.parent / rel) for view, rel in saved.items()}
        if not (target == self.path and r == self.original and target.exists()):   # unchanged: left as it is
            target.write_text(json.dumps(r, indent=1) + "\n", encoding="utf8")
        if self.on_save:
            self.on_save(target)
        if self.own_window:
            self.close()
        else:
            self.original, self.path, self.touched, self.bat_edited = json.loads(json.dumps(r)), target, False, False
            self.bat_orig, self.bat_explicit = r.get("bat", MISSING), False
            for row in self.rows:
                row.rule, row.edited = (row.rule_out() if row.on.get() else None), False
        return target

    def close(self):
        self._closed = True
        for job in (self._job, self._poll_job):
            if job:
                try:
                    self.after_cancel(job)
                except tk.TclError:
                    pass
        self._job = self._poll_job = None
        try:
            (self.winfo_toplevel() if self.own_window else self).destroy()
        except tk.TclError:
            pass


def open_window(win, game, folder, path=None, on_save=None, id_folders=()):
    """The patcher's recolor window: `win` (a Toplevel) holding a RecolorEditor with Save and Cancel."""
    ed = RecolorEditor(win, game, folder, path=path, on_save=on_save, id_folders=id_folders, own_window=True)
    ed.pack(fill="both", expand=True)
    win.protocol("WM_DELETE_WINDOW", ed.close)
    return ed
