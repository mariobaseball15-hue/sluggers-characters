"""The patcher window's Captains tab: who the captains are and where they stand on captain select (Nick: "choose who
they want to be captains, drag the models around on the captain select screen").

The lineup is drawn in the game's layout units: each captain's figure (the game's own art for a stock captain, read
from the player's game; ours or a placeholder for the rest) stands at its x / y, larger y in front. Drag a figure to
move it; the solid box is the screen a 4:3 TV shows (the game's 640 x 448 layout frame: each figure is drawn where and
as large as the game draws it), the dashed one what a widescreen TV shows. The list on the right is every captain: the
game's own (Remove takes one off captain select: the option's "remove") and the new ones (the option's list), each new
one added or replacing a stock one. 2 to 18 captains (Nick 2026-09-29). Everything captain-specific is git-a7's
scripts/captains.py editor API (canvas, figures, candidates, check, notes, default_positions, DEFAULT_OPTION); the
tab only edits the option, which the profile carries as "options": {"captains": ...}.

The Characters Beta has no tabs: the same editor is a section of its one page, under the grid (beta_window.py:
Page.add_captains; Nick: "put the whole Captains editor on the main page"). The page has no Save, so there every edit
goes to the App as it's made (apply): a changed option ticks "captains", one back to the stock 12 is None and unticks
it (nothing new is built), and the profile carries it like the grid's order. beta=True also leaves out what the beta
doesn't have: Use ours (captains it doesn't offer), the header's features box, How to and the "i"s, and it points at
the character window's Captain star moves for who can be a captain (captains.words(): the edition's "captain_words").

Team logo (Nick: "let us edit/add team logos"): the captain picked under Team logo (or clicked in the picture, or in
the list) shows its logo and emblem as the game will (captains.team_art: the game's, read from the player's game, the
player's, ours or the stand-in); Choose logo / emblem image... fits a PNG or JPG of any size keeping its shape
(captains.save_image: a PNG in the "logos" folder beside the program) and stores its path in the option: a new
captain's list entry "logo" / "emblem", a stock captain's under "art". Use the game's / Reset takes it out.
"""
import copy
import tkinter as tk
from tkinter import ttk

import fit
import widgets

NOBODY = "(no one: an extra captain)"
HOW_TO = ["The tab starts with the game's own 12 captains. Use ours adds ours (King Bob-omb and King Boo in Wario's "
          "and Waluigi's places, Rosalina and Luma); Back to stock undoes every change.",
          "To add a captain, pick a character under Add a captain and press Add. Only characters with a star swing are "
          "listed: give one a star swing on the Characters tab to add them.",
          "To have a new captain take a stock captain's place, pick them in the list and choose who they replace. "
          "Without that they're an extra captain.",
          "To take a captain off captain select, pick them in the list (or click them in the picture) and press "
          "Remove this captain: the game's own captains too. Add puts a removed one back. 2 to 18 captains.",
          "Drag a captain in the picture to move them; lower on the screen stands in front. Put everyone back in "
          "place undoes the moves.",
          "2 to 18 captains fit. More than 14 hasn't been played through yet, so the count warns you.",
          "Our characters bring their own captain art (portrait, lineup figure, name plate, logo). A character without "
          "any gets theirs drawn from their own 3D model when you patch (portrait, figure, emblem and team logo)."]
HOW_TO_SHARE = "the captains are saved with your choices (Save choices...), so sharing that file shares them."
HOW_TO_REFUSED = "the line under the picture says why in words, e.g. a character without a star swing, fewer than " \
                 "2 or more than 18 captains."
CANVAS_MIN = (460, 200)         # asked-for size: the window gives it more (fit.on_resize redraws to it)
# the Characters Beta's words (plain, short: no How to or "i"s there; Nick)
BETA_HEAD = ("Who the captains are and where each stands on captain select. 2 to 18 fit; 14 have been played "
             "through.")
BETA_HINT = ("Drag a captain to move them; lower on the screen stands in front. The solid box is the TV screen, the "
             "dashed one what a widescreen TV shows. A new captain is added, or takes a stock captain's place; any "
             "captain, the game's own too, can be removed (pick them, then Remove this captain). A character without "
             "captain art gets theirs drawn from their own 3D model when you patch.")
BETA_ADD_TIP = "Characters with captain star moves who aren't captains yet (stock, new, recolors or imported)."
BETA_OTHERS = ("Characters with captain star moves are at the top of the list. The rest can be captains too, with the "
               "generic star swing and pitch; to give one their own, click them on the grid and set Captain star moves "
               "to Yes.")
TITLE = "Captains"
LOGO_NOTE = "Portrait and lineup art control captain select; logo and emblem show on menus and in games. Mario Stadium's own signs keep the game's logos."
KIND_WORDS = {"game": "the game's", "yours": "yours", "ours": "ours", "drawn": "drawn from their 3D model",
              "stand-in": "a plain stand-in"}
IMAGE_TYPES = [("Pictures", "*.png *.jpg *.jpeg"), ("All files", "*.*")]


def data_fields():
    """{field id: data} for git-92's "i" layer (test_info_coverage.py): git-a7's captains.DATA."""
    import captains
    return {"captains.list": captains.DATA.get("list"), "captains.positions": captains.DATA.get("positions")}


def build_chars(app):
    """What captains.py needs to know who can be a captain: the characters the build has besides the stock ones
    (the ticked new characters' definitions, the recolors, the imported characters: app.roster), and every
    character's settings (a star swing makes a character eligible; the beta's Captain star moves Yes gives one),
    as the patch will have them. A recolor has no star moves of its own (recolor.VARIANT_STATS) until a setting
    gives it some."""
    defs = {}
    for name, kind, d, cid in app.roster():
        if kind == "stock" or cid is None:
            continue
        defs[name] = (dict(d, id=f"0x{cid:02X}") if kind in ("new", "imported") and d
                      else {"id": f"0x{cid:02X}", "name": name})
        if kind == "recolor" and d:                 # (its captain art is drawn from its recoloured model)
            defs[name]["_recolor"] = d
    stock_ids = {n: i for i, n in app.stock}
    stock = {}
    for name, key, value in app.char_settings():
        if name in defs:
            defs[name][key] = value
        elif name in stock_ids:
            stock.setdefault(name, {"id": stock_ids[name], "name": name, "stock": True})[key] = value
    return list(defs.values()) + list(stock.values())


class CaptainsTab:
    def __init__(self, parent, app, beta=False, option=None):
        """parent: the full patcher's notebook (a tab), else a frame to fill (the beta page's Captains section). beta: the
        Characters Beta's editor (see the module's doc). option: the captains option to start from (None: the stock 12)."""
        import captains
        self.cap, self.app, self.beta = captains, app, beta
        self.option = copy.deepcopy(option)  # None: the stock game's 12 captains (Nick: "defaults on captain screen
        # should be vanilla"; patch.py builds them from {"list": []}); ours come with Use ours
        self.game_folder = None         # the player's game, for the stock captains' own figures
        self.images, self.items, self.drag = [], {}, None
        self.frame = frame = ttk.Frame(parent, padding=6)
        if isinstance(parent, ttk.Notebook):
            parent.add(frame, text="Captains")
        else:
            frame.pack(fill="both", expand=True)
        if beta:
            fit.label(frame, BETA_HEAD, bold=True).pack(fill="x", pady=(0, 4))
        else:
            app.header(frame, "Who the captains are (up to 18; 14 have been played through) and where each stands on "
                       "captain select. A character needs a star swing to be a captain.", "captains").pack(
                fill="x", pady=(0, 4))
        import gui
        line = gui.credit_line(frame, "Captains")      # its thanks, by the feature (Nick)
        if line is not None:
            line.pack(fill="x")
        self.credit = line
        top = ttk.Frame(frame)
        top.pack(fill="x")
        if not beta:                    # (ours: King Bob-omb, King Boo, Luma, whom the beta doesn't offer)
            ttk.Button(top, text="Use ours", command=self.use_ours).pack(side="left")
        self.count = widgets.status(ttk.Label(top, text="", foreground=widgets.GREY))
        self.count.pack(side="left", padx=12)
        self.howto_row = top
        ttk.Button(top, text="Put everyone back in place", command=self.reset_positions).pack(side="right")
        ttk.Button(top, text="Back to stock", command=self.reset_all).pack(side="right", padx=4)
        hint = fit.label(frame, grey=True, text=BETA_HINT if beta else "Drag a captain to move them; lower on the "
                         "screen stands in front. The solid box is the TV screen, the dashed one what a widescreen "
                         "TV shows. Any captain, the game's own too, can be removed: 2 to 18 captains.")
        hint.pack(fill="x", pady=(4, 2))
        self.problems = widgets.status(fit.label(frame, text="", foreground=widgets.RED))
        self.problems.pack(side="bottom", fill="x", pady=4)
        data = data_fields()
        if not beta:                    # (the beta: no How to or "i"s)
            self.howto = widgets.HowTo(top, HOW_TO, share=HOW_TO_SHARE, refused=HOW_TO_REFUSED, key="captains",
                                       body_in=frame, before=hint)
            self.howto.pack(side="left", padx=(4, 0), after=self.count)
            widgets.InfoPanel(frame)            # the "i"s show here
            icon = widgets.info(top, "Where captains stand", data["captains.positions"])
            if icon is not None:
                icon.pack(side="left", padx=(4, 0), after=self.count)

        body = ttk.Frame(frame)
        body.pack(fill="both", expand=True)
        side = ttk.LabelFrame(body, text="Captains", padding=6)   # two columns: short enough for 860 x 620
        self.list_info = None if beta else widgets.info(side, "Who the captains are", data["captains.list"])
        if self.list_info is not None:
            self.list_info.grid(row=0, column=2, sticky="ne")
        side.pack(side="right", fill="y", padx=(8, 0))
        left = ttk.Frame(side)
        left.grid(row=0, column=0, sticky="n")
        self.entries = tk.Listbox(left, height=8, width=24, exportselection=False)
        self.rows = []                  # the list's rows: ("stock", stock index) or ("new", list entry index)
        self.entries.pack(fill="x")
        self.entries.bind("<<ListboxSelect>>", lambda e: self.entry_picked())
        ttk.Button(left, text="Remove this captain", command=self.remove).pack(anchor="w", pady=4)
        right = ttk.Frame(side, padding=(8, 0, 0, 0))
        right.grid(row=0, column=1, sticky="n")
        ttk.Label(right, text="Replaces:").pack(anchor="w")
        self.replaces = tk.StringVar()
        self.replaces_cb = ttk.Combobox(right, textvariable=self.replaces, state="disabled", width=22)
        self.replaces_cb.pack(anchor="w")
        widgets.tip(self.replaces_cb, "A new captain can take a stock captain's place: that captain leaves captain "
                                      "select and loses their captain star moves. \"No one\" adds an extra captain.")
        self.replaces_cb.bind("<<ComboboxSelected>>", lambda e: self.set_replaces())
        ttk.Label(right, text="Add a captain:").pack(anchor="w", pady=(8, 0))
        self.add_name = tk.StringVar()
        self.add_cb = ttk.Combobox(right, textvariable=self.add_name, state="readonly", width=22)
        self.add_cb.pack(anchor="w", pady=2)
        widgets.tip(self.add_cb, BETA_ADD_TIP if beta else "Characters with a star swing who aren't captains yet "
                                                           "(stock, new or imported).")
        ttk.Button(right, text="Add", command=self.add).pack(anchor="w")
        self.add_note = widgets.status(ttk.Label(side, text="", foreground=widgets.GREY, wraplength=330))
        self.add_note.grid(row=1, column=0, columnspan=2, sticky="w", pady=(4, 0))
        self.logo_frame(side).grid(row=2, column=0, columnspan=3, sticky="we", pady=(8, 0))

        self.canvas = tk.Canvas(body, width=CANVAS_MIN[0], height=CANVAS_MIN[1], background="#20283a",
                                highlightthickness=0)
        self.canvas.pack(side="left", fill="both", expand=True)
        self.canvas.bind("<ButtonPress-1>", self.press)
        self.canvas.bind("<B1-Motion>", self.motion)
        self.canvas.bind("<ButtonRelease-1>", self.release)
        fit.on_resize(self.canvas, self.redraw)
        self.redraw()

    # --- the option

    def chars(self):
        """What captains.py needs to know who can be a captain (build_chars)."""
        return build_chars(self.app)

    def current(self):
        """The captains option the profile gets: None (untouched: the stock captains), else the player's."""
        return self.option

    def shown(self):
        """The option drawn: the stock 12 ({"list": []}) until the player changes something."""
        return self.option if self.option is not None else {"list": []}

    def edit(self):
        """The option to change: from the stock captains when untouched."""
        if self.option is None:
            self.option = {"list": [], "positions": {}}
            if not self.beta:           # (the beta ticks it once the edit is made: apply)
                self.app.tick({"captains"}, why="the Captains tab")
        self.option.setdefault("positions", {})
        return self.option

    def use_ours(self):
        """Our captains (King Bob-omb and King Boo in Wario's and Waluigi's places, Rosalina and Luma added) in our
        lineup."""
        self.option = {"list": copy.deepcopy(self.cap.DEFAULT_OPTION["list"]), "positions": {}}
        self.app.tick({"captains"}, why="our captains")
        self.redraw()

    def set_option(self, option):
        """From an opened profile (None: the stock captains)."""
        self.option = copy.deepcopy(option) if option is not None else None
        self.redraw()

    def reset_all(self):
        self.option = None
        self.changed()

    def reset_positions(self):
        if self.option:
            self.option["positions"] = {}
        self.changed()

    def changed(self):
        """An edit made: the beta's to the App at once (apply), then the lineup, list and logo drawn again."""
        if self.beta:
            self.apply()
        self.redraw()

    def apply(self):
        """The beta page's edit to the App as it's made (no Save): the option the profile gets (current()), with the
        "captains" feature ticked; back to the stock 12 (nothing moved, added or pictured) it's None and unticked, so
        nothing new is built. A problem stays on the red line under the lineup (and Patch says it) until it's fixed."""
        app = self.app
        if is_stock(self.option):
            self.option = None
            if "captains" in app.fvars and app.fvars["captains"].get():
                app.fvars["captains"].set(False)
            app.status.set("Captains: the game's own 12.")
            return
        if not app.tick({"captains"}, why="the captains"):
            names = [self.entry_name(e) for e in self.option.get("list") or []]
            app.status.set("Captains: " + (", ".join(names) + " in" if names else "changed") + ".")

    def entry_name(self, e):
        return e if isinstance(e, str) else e.get("character", "?")

    # --- the list

    def fill_list(self):
        """Every captain: the game's own still on captain select, then the new ones (the option's list)."""
        keep = [self.rows[i] for i in self.entries.curselection() if i < len(self.rows)]
        self.entries.delete(0, "end")
        opt = self.shown()
        p = self.cap.plan(opt, self.chars(), None, swings=False)
        gone = set(p.get("removed", ())) | {self.cap.STOCK_TABLE.index(c["replaces"]) for c in p["captains"]
                                            if c.get("replaces") is not None}
        names = p["stock_names"]
        self.rows = [("stock", i) for i in range(self.cap.STOCK) if i not in gone]
        self.rows += [("new", k) for k in range(len(opt["list"]))]
        for kind, i in self.rows:
            if kind == "stock":
                self.entries.insert("end", f"{names[i]}  (the game's)")
                continue
            e = opt["list"][i]
            rep = None if isinstance(e, str) else e.get("replaces")
            self.entries.insert("end", self.entry_name(e) + (f"  (replaces {rep})" if rep else "  (added)"))
        for r in keep:
            if r in self.rows:
                self.entries.selection_set(self.rows.index(r))
        cands = self.cap.candidates(self.shown(), self.chars())
        ok = [c["name"] for c in cands if c["eligible"]]
        self.add_cb.configure(values=ok)
        no_swing = [c["name"] for c in cands if c["eligible"] and not c.get("stars", True)]
        self.add_note.configure(text=(BETA_OTHERS if self.beta else "Characters with a star swing are at the top of "
                                      "the list. The rest can be captains too, with the generic star swing; give one "
                                      "a star swing on the Characters tab.") if no_swing else "")
        self.show_entry()

    def logo_frame(self, parent):
        """Team logo: whose, their logo and emblem, and the buttons that change them."""
        box = ttk.LabelFrame(parent, text="Captain art", padding=6)
        row = ttk.Frame(box)
        row.pack(fill="x")
        ttk.Label(row, text="Captain:").pack(side="left")
        self.logo_who = tk.StringVar()
        self.logo_cb = ttk.Combobox(row, textvariable=self.logo_who, state="readonly", width=22)
        self.logo_cb.pack(side="left", padx=4)
        self.logo_cb.bind("<<ComboboxSelected>>", lambda e: self.show_logo())
        self.logo_view = tk.Canvas(box, width=259, height=96, background="#20283a", highlightthickness=0)
        self.logo_view.pack(anchor="w", pady=4)
        self.logo_kind = widgets.status(ttk.Label(box, text="", foreground=widgets.GREY))
        self.logo_kind.pack(anchor="w")
        row = ttk.Frame(box)
        row.pack(fill="x", pady=(4, 0))
        self.logo_buttons = [ttk.Button(row, text="Choose logo image...", command=lambda: self.choose("logo")),
                             ttk.Button(row, text="Choose emblem image...", command=lambda: self.choose("emblem"))]
        for b in self.logo_buttons:
            b.pack(side="left", padx=(0, 4))
        artrow = ttk.Frame(box)
        artrow.pack(fill="x", pady=(4, 0))
        self.figure_buttons = [ttk.Button(artrow, text="Choose captain portrait...", command=lambda: self.choose("portrait")),
                               ttk.Button(artrow, text="Choose lineup figure...", command=lambda: self.choose("lineup"))]
        for b in self.figure_buttons:
            b.pack(side="left", padx=(0, 4))
        self.logo_reset = ttk.Button(box, text="Use the game's", command=self.reset_logo)
        self.logo_reset.pack(anchor="w", pady=(4, 0))
        fit.label(box, LOGO_NOTE, grey=True).pack(fill="x", pady=(4, 0))
        self.logo_art, self.logo_images = None, []
        return box

    def logo_names(self, figs):
        """The captains the Team logo box offers: the lineup, left to right."""
        names = [f["name"] for f in sorted(figs, key=lambda f: f["x"])]
        self.logo_cb.configure(values=names)
        if self.logo_who.get() not in names:
            self.logo_who.set(names[0] if names else "")
        self.show_logo()

    def pick_logo(self, name):
        """Show a captain in the Team logo box (a list entry or figure clicked)."""
        if name and name in self.logo_cb.cget("values"):
            self.logo_who.set(name)
            self.show_logo()

    def show_logo(self):
        name, cv = self.logo_who.get(), self.logo_view
        cv.delete("all")
        self.logo_images = []
        self.logo_art = None
        errors = self.cap.check(self.shown(), self.chars()) if name else ["-"]
        state = "disabled" if errors else "normal"
        for b in self.logo_buttons + [self.logo_reset]:
            b.configure(state=state)
        if errors:
            for b in getattr(self, "figure_buttons", []):
                b.configure(state="disabled")
            self.logo_kind.configure(text="")
            return
        a = self.logo_art = self.cap.team_art(self.shown(), self.chars(), name, self.game_folder)
        if a is None:
            for b in getattr(self, "figure_buttons", []):
                b.configure(state="disabled")
            return
        # Portrait / lineup replacement is supported for custom captains (including Rosalina and imported captains).
        # Stock captain art still comes from the game's own captain-select file.
        fig_state = "normal" if not a.get("stock") else "disabled"
        for b in getattr(self, "figure_buttons", []):
            b.configure(state=fig_state)
        from recolor_editor import photo
        for key, (x, y) in (("logo", (2, 21)), ("emblem", (166, 3))):
            p = photo(a[key], zoom=1)
            self.logo_images.append(p)
            cv.create_image(x, y, image=p, anchor="nw")
        k = a["kinds"]
        entry = self.logo_entry(create=False) or {}
        extra = []
        if not a["stock"]:
            extra.append("Portrait: yours" if entry.get("portrait") else "Portrait: character art")
            extra.append("Lineup: yours" if entry.get("lineup") else "Lineup: character art")
        self.logo_kind.configure(text=f"Logo: {KIND_WORDS[k['logo']]}. Emblem: {KIND_WORDS[k['emblem']]}."
                                      + (("  " + ". ".join(extra) + ".") if extra else ""))
        entry = self.logo_entry(create=False) or {}
        has_player_art = any(entry.get(key) for key in self.cap.PLAYER_ART)
        self.logo_reset.configure(text="Use the game's" if a["stock"] else "Reset",
                                  state="normal" if "yours" in k.values() or has_player_art else "disabled")

    def logo_entry(self, create=True):
        """The option's dict holding the picked captain's pictures: its list entry (a new captain) or its "art" entry
        (a stock one, by its stock name); None when there is none (create=False)."""
        a = self.logo_art
        if a is None:
            return None
        opt = self.edit() if create else self.shown()
        if a["stock"]:
            stock = self.cap.STOCK_CAPTAIN_NAMES[a.get("stock_index", a["index"])]
            if not create:
                return (opt.get("art") or {}).get(stock)
            return opt.setdefault("art", {}).setdefault(stock, {})
        p = self.cap.plan(opt, self.chars(), None, swings=False)
        k = next(k for k, c in enumerate(p["captains"]) if c["index"] == a["index"])
        e = opt["list"][k]
        if isinstance(e, str):
            e = opt["list"][k] = {"character": e}
        return e

    def choose(self, key):
        from tkinter import filedialog
        path = filedialog.askopenfilename(title=f"A picture for {self.logo_who.get()}'s {key}",
                                          filetypes=IMAGE_TYPES, parent=self.frame)
        if path:
            self.set_image(key, path)

    def set_image(self, key, path):
        """A picture (PNG / JPG, any size) for one captain-art part: fitted, saved beside the program,
        and its path stored in the captain option."""
        if self.logo_art is None:
            return
        try:
            saved = self.cap.save_image(path, key, self.cap.STOCK_CAPTAIN_NAMES[self.logo_art.get(
                "stock_index", self.logo_art["index"])]
                                        if self.logo_art["stock"] else self.logo_art["name"])
        except OSError as e:
            self.logo_kind.configure(text=f"That picture didn't open: {e}")
            return
        self.logo_entry()[key] = saved
        self.changed()

    def reset_logo(self):
        """The picked captain's own logo and emblem again (the game's, ours or the stand-in)."""
        e = self.logo_entry(create=False)
        if not e:
            return
        for key in self.cap.PLAYER_ART:
            e.pop(key, None)
        art = self.option.get("art") or {}
        for name in [n for n, v in art.items() if not v]:
            art.pop(name)
        if "art" in self.option and not art:
            self.option.pop("art")
        self.changed()

    def selected_row(self):
        """The list's picked row: ("stock", stock index) or ("new", list entry index), or None."""
        sel = self.entries.curselection()
        return self.rows[sel[0]] if sel and sel[0] < len(self.rows) else None

    def selected(self):
        """The picked new captain's list entry index (None: none, or a stock captain picked)."""
        row = self.selected_row()
        opt = self.shown()
        return row[1] if row and row[0] == "new" and row[1] < len(opt["list"]) else None

    def select_row(self, row):
        self.entries.selection_clear(0, "end")
        if row in self.rows:
            self.entries.selection_set(self.rows.index(row))
            self.entries.see(self.rows.index(row))

    def show_entry(self):
        i = self.selected()
        if i is None:
            self.replaces_cb.configure(state="disabled")
            self.replaces.set("")
            return
        opt = self.shown()
        e = opt["list"][i]
        taken = {x.get("replaces") for j, x in enumerate(opt["list"]) if j != i and isinstance(x, dict)}
        taken |= set(opt.get("remove") or ())           # (a removed captain has no place to take)
        self.replaces_cb.configure(state="readonly", values=[NOBODY] + [n for n in self.cap.STOCK_CAPTAIN_NAMES
                                                                        if n not in taken])
        self.replaces.set((None if isinstance(e, str) else e.get("replaces")) or NOBODY)

    def entry_picked(self):
        """A list entry clicked: its Replaces, and its team logo."""
        self.show_entry()
        row = self.selected_row()
        if row and row[0] == "stock":
            self.pick_logo(self.cap.plan(self.shown(), self.chars(), None, swings=False)["stock_names"][row[1]])
        elif self.selected() is not None:
            self.pick_logo(self.entry_captain(self.selected()))

    def entry_captain(self, i):
        """The name list entry i shows as on the lineup."""
        p = self.cap.plan(self.shown(), self.chars(), None, swings=False)
        return p["captains"][i]["name"] if not p["errors"] and i < len(p["captains"]) else None

    def set_replaces(self):
        i = self.selected()
        if i is None:
            return
        opt = self.edit()
        e = opt["list"][i]
        e = {"character": e} if isinstance(e, str) else dict(e)
        if self.replaces.get() == NOBODY:
            e.pop("replaces", None)
        else:
            e["replaces"] = self.replaces.get()
            (opt.get("art") or {}).pop(e["replaces"], None)    # (that stock captain's logo has nowhere to show)
            if "art" in opt and not opt["art"]:
                opt.pop("art")
        opt["list"][i] = e
        self.changed()

    def count_now(self):
        """How many captains the option has now (None while it has a problem)."""
        p = self.cap.plan(self.shown(), self.chars(), None, swings=False)
        return None if p["errors"] else len(p["table"])

    def refuse(self, words):
        """Say why an edit wasn't made (the red line under the picture; the next redraw clears it)."""
        self.problems.configure(text=words, foreground=widgets.RED)
        self.app.status.set("Captains: " + words)

    def row_of(self, name):
        """The list row of a captain by the name the picture shows, or None."""
        opt = self.shown()
        p = self.cap.plan(opt, self.chars(), None, swings=False)
        for row in self.rows:
            if row[0] == "stock" and p["stock_names"][row[1]] == name:
                return row
            if row[0] == "new" and name in (self.entry_name(opt["list"][row[1]]), self.entry_captain(row[1])):
                return row
        return None

    def remove(self):
        """Take the picked captain off captain select: a new one leaves the list, one of the game's own goes in the
        option's "remove". Nothing picked in the list: the captain picked under Team logo (clicked in the picture).
        At least 2 stay."""
        row = self.selected_row() or self.row_of(self.logo_who.get())
        if row is None:
            self.refuse("Pick a captain in the list (or click them in the picture), then Remove this captain.")
            return
        n = self.count_now()
        opt = self.shown()
        if n is not None and n <= self.cap.MIN_CAPTAINS and not (row[0] == "new" and isinstance(
                opt["list"][row[1]], dict) and opt["list"][row[1]].get("replaces")):
            self.refuse(f"Captain select needs at least {self.cap.MIN_CAPTAINS} captains, so this one stays.")
            return
        p = self.cap.plan(opt, self.chars(), None, swings=False)
        opt = self.edit()
        if row[0] == "new":
            e = opt["list"].pop(row[1])
            for name in {self.entry_name(e), e.get("name") if isinstance(e, dict) else None} - {None}:
                opt["positions"].pop(name, None)
        else:
            stock = self.cap.STOCK_CAPTAIN_NAMES[row[1]]
            opt.setdefault("remove", []).append(stock)
            for name in {stock, p["stock_names"][row[1]]}:
                opt["positions"].pop(name, None)
            (opt.get("art") or {}).pop(stock, None)            # (their logo has nowhere to show)
            if "art" in opt and not opt["art"]:
                opt.pop("art")
        self.entries.selection_clear(0, "end")
        self.changed()

    def add(self):
        """Add the character picked under Add a captain: a removed stock captain goes back, anyone else is a new
        captain. At most 18."""
        name = self.add_name.get()
        if not name:
            return
        n = self.count_now()
        if n is not None and n >= self.cap.MAX_CAPTAINS:
            self.refuse(f"{self.cap.MAX_CAPTAINS} captains is the most captain select fits: remove one first.")
            return
        opt = self.edit()
        cand = next((c for c in self.cap.candidates(opt, self.chars()) if c["name"] == name), None)
        self.add_name.set("")
        if cand is not None and cand.get("removed"):              # one of the game's own, back in their place
            i = self.cap.STOCK_TABLE.index(cand["id"])
            names = self.cap._names(self.chars())
            opt["remove"] = [r for r in opt.get("remove") or [] if (self.cap._resolve(r, names) or (None,))[0]
                             != cand["id"]]
            if not opt["remove"]:
                opt.pop("remove")
            self.changed()
            self.select_row(("stock", i))
        else:
            opt["list"].append({"character": name})
            self.changed()
            self.select_row(("new", len(opt["list"]) - 1))
        self.show_entry()

    # --- the lineup

    def redraw(self):
        opt, chars = self.shown(), self.chars()
        errors = self.cap.check(opt, chars)
        notes = self.cap.notes(opt, chars)
        self.problems.configure(text="\n".join(errors + notes), foreground=widgets.RED if errors else widgets.AMBER)
        self.fill_list()
        if errors:
            self.canvas.delete("all")
            self.images, self.items, self.drag = [], {}, None
            W, H = fit.size(self.canvas)
            self.canvas.create_text(W // 2, H // 2, fill="#ccc", width=W - 20, justify="center",
                                    text="Fix the problem below to see the lineup.")
            self.count.configure(text="")
            self.show_logo()
            return
        figs = self.cap.figures(opt, chars, self.game_folder)
        c = self.cap.canvas()
        self.count.configure(text=f"{len(figs)} captains of {c['max_captains']}"
                                  + (f" (more than {c['tested']} hasn't been played yet)" if len(figs) > c["tested"]
                                     else ""))
        self.draw(figs, c)
        self.logo_names(figs)

    def draw(self, figs, c):
        """The game's screen in its layout units: the 4:3 frame (solid) and the widescreen width (dashed), each figure
        stretched over the box the game draws it in (captains.figures), larger y in front."""
        (x0, x1), (fx0, fy0, fx1, fy1) = c["view_x"], c["frame"]
        x0 = min([x0] + [f["box"][0] for f in figs]) - 4
        x1 = max([x1] + [f["box"][2] for f in figs]) + 4
        y0 = min([fy0] + [f["box"][1] for f in figs]) - 4
        y1 = max([fy1] + [f["box"][3] for f in figs]) + 4
        W, H = fit.size(self.canvas)
        self.s = min((W - 12) / (x1 - x0), (H - 12) / (y1 - y0))
        self.ox, self.oy = (W - (x1 - x0) * self.s) / 2 - x0 * self.s, (H - (y1 - y0) * self.s) / 2 - y0 * self.s
        cv = self.canvas
        cv.delete("all")
        self.images, self.items = [], {}
        cv.create_rectangle(*self.to_canvas(c["view_x"][0], fy0), *self.to_canvas(c["view_x"][1], fy1), outline="#667",
                            dash=(4, 3))
        cv.create_rectangle(*self.to_canvas(fx0, fy0), *self.to_canvas(fx1, fy1), outline="#889")
        from recolor_editor import photo
        for f in sorted(figs, key=lambda f: f["y"]):             # larger y is drawn in front
            bx0, by0 = self.to_canvas(*f["box"][:2])
            bx1, by1 = self.to_canvas(*f["box"][2:])
            img = f["image"].resize((max(1, round(bx1 - bx0)), max(1, round(by1 - by0))))
            p = photo(img, zoom=1)
            self.images.append(p)
            cx, cy = self.to_canvas(f["x"], f["y"])
            tag = f"fig{f['index']}"
            cv.create_image(round(bx0), round(by0), image=p, anchor="nw", tags=(tag, "fig", f"img{f['index']}"))
            cv.create_text(cx, by1 + 6, text=f["name"], fill="#eee" if f["kind"] != "placeholder" else "#fb6",
                           font=("", 8), tags=(tag, "fig"))
            self.items[tag] = f

    def to_canvas(self, x, y):
        return self.ox + x * self.s, self.oy + y * self.s

    def press(self, e):
        hit = [t for i in self.canvas.find_overlapping(e.x, e.y, e.x, e.y)
               for t in self.canvas.gettags(i) if t in self.items]
        self.drag = (hit[-1], e.x, e.y) if hit else None

    def motion(self, e):
        if self.drag:
            tag, x, y = self.drag
            self.canvas.move(tag, e.x - x, e.y - y)
            self.canvas.tag_raise(tag)
            self.drag = (tag, e.x, e.y)
            self.drag_total = getattr(self, "drag_total", (0, 0))
            self.drag_total = (self.drag_total[0] + e.x - x, self.drag_total[1] + e.y - y)

    def release(self, e):
        if not self.drag:
            return
        tag = self.drag[0]
        dx, dy = getattr(self, "drag_total", (0, 0))
        self.drag, self.drag_total = None, (0, 0)
        if (dx, dy) == (0, 0):                  # a click: that captain's team logo, and their row in the list
            self.pick_logo(self.items[tag]["name"])
            row = self.row_of(self.items[tag]["name"])
            if row is not None:
                self.select_row(row)
                self.show_entry()
            return
        self.move(self.items[tag]["name"], dx / self.s, dy / self.s)

    def move(self, name, dx, dy):
        """Move a captain by (dx, dy) layout units (y only when it really moved up or down)."""
        f = next(f for f in self.items.values() if f["name"] == name)
        pos = dict(self.edit()["positions"].get(name, {}))
        pos["x"] = round(f["x"] + dx)
        if abs(dy) >= 2 or "y" in pos:
            pos["y"] = round(f["y"] + dy)
        self.option["positions"][name] = pos
        self.changed()

    # --- the game's figures

    def load_game_figures(self):
        """The stock captains' own figures from the player's game (placeholders until then)."""
        def got(folder):
            self.game_folder = folder
            self.redraw()
        self.app.with_game_folder(got, quiet=True)


def is_stock(option):
    """An option that changes nothing: the stock 12 where they stand with their own logos (None, or no list, moves or
    pictures)."""
    return option is None or not (option.get("list") or option.get("positions") or option.get("art")
                                  or option.get("remove"))

