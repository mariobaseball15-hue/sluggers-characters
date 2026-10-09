"""The Characters Beta's window: one page, no tabs (Nick: "start on the select grid where you can move people around,
then let people edit characters by clicking on them from there. Model and character edits can be done in one window.
Have two buttons on the main page where you can create a new character or a recolor. Also just put progress at the
bottom, so no tabs needed.").

gui.App builds this page when the edition says "layout": "single" (editions/characters-beta.json). The App still makes
every tab, unshown, because their state is the profile (the features, which characters are in, the per-character
settings); this page puts on the screen what the beta needs:
  - the top bar (App's own: your game, where to save, a name) and the edition's intro;
  - New recolor / Import character (.sluggie, .slgmodel, .glb, model file, or folder: A file... / A folder...), and an "Add to the game" row for the beta's own characters
    that aren't in yet;
  - Game options... at the right of that row (the edition's CPU vs CPU, Start at captain select, Start in a game with
    your own teams, the menu background color: game_options.py, a small window with Save), Items... beside it (the
    edition's item features: roulette odds, speed and flight, the Ice ball, your own items; items_window.py), and CPU
    levels... (levels 5 and 6: cpu_tab.Window, the CPU levels tab in a window);
  - a scrolled part (Nick: "put the whole Captains editor on the main page"): first the character-select grid
    (git-f4's grid_editor.GridTab, always editable: drag squares, reorder wheels; a click on a character opens its
    character window), as tall as its rows of squares (no stretched empty space, Nick), then Captains (the full
    patcher's Captains tab, captain_editor.CaptainsTab beta=True: who the captains are, where they stand on captain
    select, team logos; each edit goes to the App as it's made, the page having no Save). The mouse wheel scrolls it
    over everything but the lists and drop-downs, which scroll themselves (the grid and the lineup only drag);
  - Progress, always visible, then App's pinned bar (Open / Save choices, Fix my Gecko codes: gecko_window.py, Check,
    Patch) and the credits link.
The character window is character_window.py, shared with the full patcher.
"""
import tkinter as tk
import style
from tkinter import filedialog, ttk
from tkinter.scrolledtext import ScrolledText

import character_window
import fit
import grid_editor
import widgets

HOW_TO = ["Pick your game at the top: the grid shows your game's characters.",
          "Drag a square onto another to move it. Click a square to see its color wheel.",
          "Click a character to open it: its stats, chemistry, names and model, all in one window.",
          "New recolor makes a new color of a character; Add a model from Sluggies adds a character from a model "
          "you edited. Both open in the same window.",
          "Patch writes a new copy of your game. Progress shows at the bottom."]
HOW_TO_SHARE = "Save choices... keeps everything in one file; Open choices... on another PC brings it back."
HOW_TO_REFUSED = "the line under the grid, or the character window, says what to change."
import game_options
GAME_OPTIONS = game_options.FEATURES
VIEW_MIN = 160          # the scrolled part asks for this much height: the window gives it what the bars leave
GRID_MIN = 150          # the grid never shorter than this (the lineup below scrolls into view)
WHEEL_TAG = "BetaPageWheel"


class Page:
    wheel_tag = WHEEL_TAG               # (on the widgets the page's wheel scrolls: tag_wheel)

    def __init__(self, app):
        self.app, root = app, app.root
        self.frame = ttk.Frame(root, padding=(8, 0, 8, 0))
        self.frame.pack(fill="both", expand=True)
        self.credit_row()                              # under the intro, like every full-patcher tab's line
        actions = ttk.Frame(self.frame)
        actions.pack(fill="x", pady=(0, 4))
        # the ways to add a character, one row of same-size buttons (Nick: "just two buttons": New recolor and one
        # Import character that takes every kind; no New character)
        adds = ttk.Frame(actions)
        adds.pack(side="left")
        self.add_buttons = []

        def place(button):
            button.grid(row=0, column=len(self.add_buttons), sticky="ew", padx=(0, 6))
            adds.columnconfigure(len(self.add_buttons), uniform="add")
            self.add_buttons.append(button)
        place(ttk.Button(adds, text="New recolor", style="Big.TButton", command=self.new_recolor))
        place(ttk.Button(adds, text=character_window.IMPORT_BUTTON.replace(" (", "\n(", 1), style="Big.TButton",
                         command=lambda: app.import_dialog()))
        place(ttk.Button(adds, text="Archive...", style="Big.TButton", command=self.open_archive))
        place(ttk.Button(adds, text="Base textures...", style="Big.TButton", command=self.base_textures))
        self.howto = widgets.HowTo(actions, HOW_TO, share=HOW_TO_SHARE, refused=HOW_TO_REFUSED, key="beta page",
                                   body_in=self.frame)
        self.howto.pack(side="left", padx=8)
        # the edition's game options (CPU vs CPU, how the game starts, the menu color: game_options.py), at the
        # right of the same row; the button counts the ones on (finish() keeps it current). CPU levels..., Game
        # options... and Items... (the edition's item features, items_window.py) side by side on one line (Nick)
        opts = ttk.Frame(actions)
        opts.pack(side="right")
        self.options_button = None
        if any(f in app.reg for f in GAME_OPTIONS):     # (the registry: the edition's features)
            self.options_button = ttk.Button(opts, text="Game options...", command=self.game_options,
                                             style="Slim.TButton", width=0)
            self.options_button.grid(row=0, column=1, sticky="ew")
        self.items_button = None
        import items_window                             # odds, speed and flight, the Ice ball, your own items
        if items_window.has_items(app):
            self.items_button = ttk.Button(opts, text="Items...", command=self.items, style="Slim.TButton", width=0)
            self.items_button.grid(row=0, column=2, sticky="ew", padx=(4, 0))   # one row (Nick)
        self.cpu_button = None
        if "level-5" in app.reg:                      # the CPU levels (cpu_tab.Window, on App's unshown tab)
            self.cpu_button = ttk.Button(opts, text="CPU levels...", command=self.cpu_levels,
                                         style="Slim.TButton", width=0)
            self.cpu_button.grid(row=0, column=0, sticky="ew", padx=(0, 4))
        self.missing = ttk.Frame(self.frame)            # kept for compatibility; archived characters live in Archive
        # the scrolled part: the grid, then Captains (add_captains). It asks for little height (the window gives it
        # what the bars leave) and for its content's width (fit_width: the window stays as wide as the page needs)
        scroll = ttk.Frame(self.frame)
        scroll.pack(fill="both", expand=True)
        self.view = tk.Canvas(scroll, highlightthickness=0, width=200, height=VIEW_MIN, yscrollincrement=20)
        self.bar = ttk.Scrollbar(scroll, orient="vertical", command=self.view.yview)
        self.bar.pack(side="right", fill="y")
        self.view.pack(side="left", fill="both", expand=True)
        self.view.configure(yscrollcommand=self.bar.set)
        self.inner = ttk.Frame(self.view)
        self.inner_item = self.view.create_window((0, 0), window=self.inner, anchor="nw")
        self.inner.bind("<Configure>", lambda e: self.view.configure(scrollregion=self.view.bbox("all")))
        self.view.bind("<Configure>", lambda e: (self.view.itemconfigure(self.inner_item, width=e.width),
                                                 self.fit_grid(e.height)))
        self.grid_parent = ttk.Frame(self.inner)        # its height is set (fit_grid): the grid's own height
        self.grid_parent.pack_propagate(False)
        self.grid_parent.pack(fill="x")
        self.captains_section = None
        root.bind_class(WHEEL_TAG, "<MouseWheel>", self.wheel)
        self.progress_parent = ttk.Frame(root, padding=(8, 4, 8, 0))   # (Progress: one row, a stage line and a bar)

    def add_captains(self):
        """The Captains section under the grid (App builds it once the characters it reads are made): a heading, then
        the full patcher's Captains editor (captain_editor.CaptainsTab, beta=True). None when the edition doesn't
        offer captains."""
        if "captains" not in self.app.fvars:
            return None
        import captain_editor
        box = self.captains_section = ttk.Frame(self.inner, padding=(0, 6, 0, 0))
        box.pack(fill="x")
        ttk.Separator(box).pack(fill="x")
        self.captains_heading = ttk.Label(box, text=captain_editor.TITLE, font="SluggersHeading", padding=(0, 4, 0, 0))
        self.captains_heading.pack(anchor="w")
        return captain_editor.CaptainsTab(box, self.app, beta=True)

    def fit_grid(self, height=None):
        """Give the embedded grid its full requested height.

        The grid canvas changes its requested height after it knows how many rows it has.  Tk can report the old
        frame request for one layout pass, which used to leave the lower rows clipped in a short/wide window.
        Flush geometry first and derive the wrapper height from the canvas request plus the grid's non-canvas chrome.
        The outer page still scrolls when the complete grid + Captains section is taller than the window.
        """
        tab = getattr(self.app, "grid_tab", None)
        if tab is None:
            self.grid_parent.configure(height=GRID_MIN)
            return
        tab.frame.update_idletasks()
        canvas_h = max(int(tab.canvas.cget("height")), tab.canvas.winfo_reqheight())
        frame_h = tab.frame.winfo_reqheight()
        # Everything other than the canvas (top line, wheel controls, padding).  Never let a stale canvas request
        # make this negative.
        chrome = max(0, frame_h - tab.canvas.winfo_reqheight())
        wanted = max(GRID_MIN, canvas_h + chrome)
        self.grid_parent.configure(height=wanted)
        self.inner.update_idletasks()
        self.view.configure(scrollregion=self.view.bbox("all"))

    def peek(self):
        """How much of the scrolled part's height the Captains heading takes under the grid (0: no Captains)."""
        if self.captains_section is None:
            return 0
        return self.captains_heading.winfo_reqheight() + 8

    def fit_width(self):
        """The scrolled part asks for its content's width (the grid's frame doesn't pass it on: its height is set)."""
        widths = [self.app.grid_tab.frame.winfo_reqwidth()]
        if self.captains_section is not None:
            widths.append(self.captains_section.winfo_reqwidth())
        self.view.configure(width=max(widths))

    def tag_wheel(self, w=None):
        """The page's wheel on every widget in the scrolled part but the ones that scroll themselves (a list, a
        drop-down): the grid's canvas and the lineup only drag, so the wheel over them scrolls the page."""
        w = w or self.view
        if w.winfo_class() not in ("Listbox", "TCombobox", "Text", "Scrollbar", "TScrollbar"):
            tags = w.bindtags()
            if WHEEL_TAG not in tags:
                w.bindtags(tags + (WHEEL_TAG,))
        for c in w.winfo_children():
            self.tag_wheel(c)

    def wheel(self, e):
        self.view.yview_scroll(int(-e.delta / 120) or (-1 if e.delta > 0 else 1), "units")

    def show_captains(self):
        """Scroll the page to the Captains section."""
        if self.captains_section is not None:
            self.view.update_idletasks()
            total = max(1, self.inner.winfo_reqheight())
            self.view.yview_moveto(self.captains_section.winfo_y() / total)

    def credit_row(self):
        """The page's credit line (CREDITS.md "In the Characters Beta" / "### Page", credits.page_line; Nick: "This
        needs to have credits") and a Credits link, in grey under the intro."""
        try:
            import credits
            line = credits.page_line()
        except (ImportError, OSError):
            line = None
        if not line:
            return
        row = ttk.Frame(self.frame)
        row.pack(fill="x", pady=(0, 4))
        fit.label(row, line, grey=True, wrap=760).pack(side="left", fill="x", expand=True)   # (760: about the
        link = ttk.Label(row, text="Credits", style="Link.TLabel", cursor="hand2")          # width it gets)
        link.pack(side="left", padx=(8, 0))
        link.bind("<Button-1>", lambda e: self.show_credits())
        self.credit_label = line

    def finish(self):
        """After App has built everything: Progress above the pinned bar, the page taking what's left, the grid on the
        player's game, and the "Add to the game" row kept current."""
        app = self.app
        self.progress_parent.pack(side="bottom", fill="x", padx=8, after=app.bottom_bar)
        self.frame.pack_forget()                        # packed last: a short window shrinks the grid, not the bars
        self.frame.pack(fill="both", expand=True)
        for v in list(app.cvars.values()) + list(app.rvars.values()):
            v.trace_add("write", lambda *a: self.refresh_soon())
        for f in GAME_OPTIONS:
            if f in app.fvars:
                app.fvars[f].trace_add("write", lambda *a: self.refresh_soon())
        app.game.trace_add("write", lambda *a: self.load_grid())
        self.fit_grid(VIEW_MIN)                         # (until the window lays out: its <Configure> sets it)
        app.grid_tab.frame.bind(grid_editor.SIZE_EVENT, lambda e: self.fit_grid())   # the grid's rows changed
        self.fit_width()
        self.tag_wheel()
        self.load_grid()
        self._refresh()                                 # the "Add to the game" row and the Game options count
        app.status.set("Click a character to edit it, or make one with New recolor or a Sluggies model. Then Patch.")

    # --- the grid and the characters not in the game yet

    def load_grid(self):
        g = self.app.game_path()
        if g is not None and g.exists():
            self.app.grid_tab.load_game()               # quiet: the grid says "pick your game" until then
            if self.captains_section is not None:       # the stock captains' own figures, from the player's game
                self.app.captains_tab.load_game_figures()

    def refresh_soon(self):
        if not getattr(self, "_queued", False):
            self._queued = True
            self.app.root.after_idle(self._refresh)

    def _refresh(self):
        self._queued = False
        self.refresh_missing()
        self.tag_wheel()                                # (widgets made since: the wheel on them too)
        if self.options_button is not None:             # "Game options (2 on)..."
            import game_options
            self.options_button.configure(text=game_options.summary(self.app))

    def offered(self):
        """[(name, kind, path, var)] of the beta's characters and recolors, in the game or not."""
        app = self.app
        return ([(d["name"], "new", p, app.cvars[p]) for p, d, _ in app.new_chars] +
                [(r["name"], "recolor", p, app.rvars[p]) for p, r in app.recipes])

    def refresh_missing(self):
        """Archived/off characters are managed in the separate Archive window, not as buttons on the main page."""
        return

    def open_archive(self):
        """Manage characters that are installed in the tool but currently left out of the game."""
        win = tk.Toplevel(self.app.root)
        win.transient(self.app.root)
        style.title(win, "Character archive")
        win.geometry("520x360")
        body = ttk.Frame(win, padding=10)
        body.pack(fill="both", expand=True)
        ttk.Label(body, text="Archived characters", font="SluggersHeading").pack(anchor="w")
        fit.label(body, "Characters removed from the grid stay here. Restore adds them back without making a clone; "
                        "Delete permanently removes any non-stock archived character, including the built-in added characters.", grey=True, wrap=480).pack(fill="x",
                                                                                                           pady=(2, 8))
        box = tk.Listbox(body, exportselection=False)
        box.pack(fill="both", expand=True)
        status = ttk.Label(body, text="", foreground=widgets.GREY)
        status.pack(fill="x", pady=(4, 0))

        def rows():
            return [(n, k, p, v) for n, k, p, v in self.offered() if not v.get()]

        def refill(select_name=None):
            data = rows()
            box.delete(0, "end")
            for n, k, _, _ in data:
                box.insert("end", f"{n}  [{k}]")
            if select_name:
                for i, (n, *_rest) in enumerate(data):
                    if n == select_name:
                        box.selection_set(i)
                        box.see(i)
                        break
            status.configure(text=f"{len(data)} archived character{'s' if len(data) != 1 else ''}.")

        def selected():
            pick = box.curselection()
            data = rows()
            return data[pick[0]] if pick and pick[0] < len(data) else None

        def restore():
            item = selected()
            if item is None:
                return
            name, kind, _, var = item
            var.set(True)
            import gui
            self.app.tick(gui.RECOLOR_NEEDS if kind == "recolor" else {"new-ids"}, why=name)
            g = getattr(self.app, "grid_tab", None)
            if g is not None:
                g.fit_to_roster()
                g.redraw()
            character_window.refresh(self.app)
            self.app.status.set(f"Restored {name} from the archive.")
            refill()

        def delete_selected():
            item = selected()
            if item is None:
                return
            name = item[0]
            if character_window.delete(self.app, name):
                refill()

        bar = ttk.Frame(body)
        bar.pack(fill="x", pady=(8, 0))
        ttk.Button(bar, text="Restore", command=restore).pack(side="left")
        ttk.Button(bar, text="Delete...", command=delete_selected).pack(side="left", padx=4)
        ttk.Button(bar, text="Close", command=win.destroy).pack(side="right")
        box.bind("<Double-1>", lambda e: restore())
        refill()
        return win


    # --- windows

    def show_credits(self):
        """The credits (CREDITS.md through credits.py): Nick wants clear credit, one click away."""
        import gui
        win = tk.Toplevel(self.app.root)
        win.transient(self.app.root)
        style.title(win, "Credits")
        win.geometry("640x480")
        fit.label(win, gui.CREDITS_TOP, bold=True, padding=(8, 8, 8, 4)).pack(fill="x")
        box = ScrolledText(win, wrap="word", font="SluggersSmall")
        try:
            import credits
            box.insert("1.0", credits.text(gui.EDITION))   # the edition's own (no feature it lacks)
        except (ImportError, OSError) as e:
            box.insert("1.0", f"The credits couldn't be read here ({e}).")
        box.configure(state="disabled")
        box.pack(fill="both", expand=True, padx=8)
        ttk.Button(win, text="Close", command=win.destroy).pack(anchor="e", padx=8, pady=8)
        return win

    def game_options(self):
        """The Game options window (game_options.py): CPU vs CPU, how the game starts, the menu color."""
        import game_options
        return game_options.open_window(self.app)

    def items(self):
        """The Items window (items_window.py): roulette odds, speed and flight, the Ice ball, your own items."""
        import items_window
        return items_window.open_window(self.app)

    def cpu_levels(self):
        """The CPU levels window (cpu_tab.Window): levels 5 and 6, their switches and values."""
        import cpu_tab
        return cpu_tab.open_window(self.app)

    def open_character(self, name):
        return character_window.open_character(self.app, name)

    def base_textures(self):
        """Direct PNG editing for the stock/base character model textures."""
        import base_texture_editor
        def show(game):
            base_texture_editor.open_window(self.frame, game)
        return self.app.recolor_game(show, what="Base texture editing reads the stock character models from your game.")

    def new_recolor(self):
        return character_window.new_recolor(self.app)

    def import_texture_png(self):
        """Import an edited Dolphin texture PNG as a character variant. All tex1_*.png files beside the picked
        picture are considered, so a multi-texture recolor only needs one selection."""
        path = filedialog.askopenfilename(title="Import character texture PNG", filetypes=[
            ("Dolphin texture PNG", "tex1_*.png"), ("PNG picture", "*.png"), ("All files", "*.*")])
        if path:
            return self.app.import_file(path)
        return None

    @property
    def windows(self):
        return character_window.windows(self.app)

    def entry(self, name):
        return character_window.entry(self.app, name)
