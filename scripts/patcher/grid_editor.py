"""The patcher window's Select grid tab: the order of the character-select grid (Nick: players "edit the character
select screen order").

The grid is drawn where the game draws it (git-d9's grid_order.cells), each square with the face of its first
character and how many are on its color wheel. Drag a square onto another to swap them. Pick a square to see its
wheel: move a character up or down it, or to another square or a new square of its own. A stock square keeps its own
character (Mario, Captain Toad, ...); git-d9's validate says so in words, as it does for the other rules (10 on a
wheel, 19 new squares). Everything grid-specific is scripts/grid_order.py (default_order, validate, room, cells,
face); the tab only edits the order, which the profile carries as "options": {"grid-order": [[names], ...]}.
"""
import copy
import tkinter as tk
from tkinter import ttk

import fit
import widgets

NEW_SQUARE = "(a new square of its own)"
HOW_TO = ["Tick \"Change the character-select order\".",
          "Drag a square onto another to swap them.",
          "Click a square to see its colour wheel on the right: Up and Down reorder it, and Move to puts a character on "
          "another square or a new square of its own.",
          "The game's own squares keep their first character (Mario stays on Mario's square): the game's random "
          "teams and the CPU's picks count on them. Everyone else can move.",
          "The grid holds 60 squares, 19 of them new, and a wheel holds 10 characters. The line at the top says how "
          "many squares are left."]
HOW_TO_SHARE = "the order is saved with your choices (Save choices...), so sharing that file shares it."
HOW_TO_REFUSED = "the line under the grid says what to change, e.g. a wheel with 11 characters or a square that " \
                 "lost its own character."
CELL = 46                       # a square's size in the game's layout units (they're 49 apart)
CANVAS_MIN = (460, 200)         # asked-for size before the grid is drawn; then it asks for the grid's own height
MIN_SCALE = 0.55                # smaller than this, the canvas scrolls instead
MAX_SCALE = 1.85                # use more of a wide window while keeping the complete grid visible
SIZE_EVENT = "<<GridSize>>"     # on the tab's frame when the canvas asks for a new height (the beta page refits)


def data_fields():
    """{field id: data} for git-92's "i" layer (test_info_coverage.py): git-d0's grid_order.DATA, as it is."""
    import grid_order
    return dict(grid_order.DATA)


def added_base_face(game, recipe):
    """A recolor of an ADDED base (e.g. Rosalina): the path of a PNG of the base's own side portrait with the
    recipe's rules applied (cached by content in the temp folder), for its square before it's built; None for a
    stock base (face() recolors the stock portrait itself) or when the base can't be read."""
    import hashlib, json, tempfile
    from pathlib import Path
    import recolor
    try:
        base = recolor.base_of(game, recipe["base"])
        if not base.added:
            return None
        key = hashlib.sha1(json.dumps([str(base.key), recipe.get("recolor", [])], sort_keys=True,
                                      default=str).encode()).hexdigest()[:16]
        path = Path(tempfile.gettempdir()) / "sluggers-grid-faces" / f"{key}.png"
        if not path.exists():
            path.parent.mkdir(parents=True, exist_ok=True)
            recolor.apply_rules(base.portrait("side"), recipe.get("recolor", []), portrait=True).save(path)
        return str(path)
    except (AssertionError, KeyError, OSError, ValueError):
        return None


def recolor_template(base):
    """A recipe's base as a stock template (an added base, e.g. Rosalina: its definition's template)."""
    import recolor
    return recolor.template_of(base)


class GridTab:
    def __init__(self, notebook, app, always_on=False, on_open=None):
        """notebook: a ttk.Notebook (the tab is added) or a plain frame (packed into it). always_on: the order is
        always editable, no checkbox (git-10's single-page Characters Beta). on_open(name): called on a click that
        doesn't drag, with the square's shown character, and on a double-click on a wheel member."""
        import grid_order
        self.go, self.app = grid_order, app
        self.always_on, self.on_open = always_on, on_open
        self.order = None               # None: the patcher's own order (no option)
        self.game = None                # recolor.Game of the player's game (the DOL and the portraits)
        self.images, self.cells, self.drag, self.sel = [], [], None, None
        self.face_cache = {}             # portrait decoding is expensive; keep PIL faces between UI redraws
        self.photo_cache = {}            # resized Tk images by character/size; avoids re-encoding on every redraw
        self._resize_job, self._resize_width = None, None
        self.frame = frame = ttk.Frame(notebook, padding=6)
        if isinstance(notebook, ttk.Notebook):
            notebook.add(frame, text="Select grid")
        else:
            frame.pack(fill="both", expand=True)
        if not always_on:               # (the single page's own How to says it: the room goes to the grid, git-10)
            fit.label(frame, bold=True, text="The order of the character-select grid: up to 60 squares, 19 of them "
                      "new, and 10 characters on a square's color wheel. The game's own squares keep their first "
                      "character.").pack(fill="x", pady=(0, 4))
        import gui
        line = None if always_on else gui.credit_line(frame, "Select grid")   # (the page has a Credits link)
        if line is not None:
            line.pack(fill="x")
        self.enabled = tk.BooleanVar(value=always_on)
        top = ttk.Frame(frame)
        top.pack(fill="x")
        if not always_on:
            ttk.Checkbutton(top, text="Change the character-select order", variable=self.enabled,
                            command=self.toggled).pack(side="left")
        self.room_label = widgets.status(ttk.Label(top, text="", style="Hint.TLabel"))
        self.room_label.pack(side="left", padx=12)
        ttk.Button(top, text="Back to the patcher's order", command=self.reset).pack(side="right")
        hint = fit.label(frame, grey=True, text="Drag a square onto another to swap them. Click a square to see its "
                         "color wheel and move characters around.")
        if not always_on:
            hint.pack(fill="x", pady=(4, 2))
        self.howto = widgets.HowTo(top, HOW_TO[1:] if always_on else HOW_TO, share=HOW_TO_SHARE, refused=HOW_TO_REFUSED, key="select grid",
                                   body_in=frame, before=None if always_on else hint)
        self.howto.pack(side="left", padx=(4, 0), after=self.room_label)
        self.problems = widgets.status(fit.label(frame, text="", foreground=widgets.RED))
        self.problems_shown = False     # packed only while it says something (Nick: no empty labels)
        widgets.InfoPanel(frame)            # the "i"s show here
        data = data_fields()
        for key, title in (("square order", "The order of the squares"), ("grid size", "How big the grid is")):
            icon = widgets.info(top, title, data.get(key))
            if icon is not None:
                icon.pack(side="left", padx=(4, 0), after=self.room_label)
        self.body = body = ttk.Frame(frame)
        body.pack(fill="both", expand=True)
        if always_on:
            self.howto.before = body    # (the hint it opens above isn't shown)

        side = ttk.LabelFrame(body, text="Color wheel", padding=6)
        side.pack(side="right", fill="y", padx=(8, 0))
        row_i = ttk.Frame(side)
        row_i.pack(fill="x")
        for key, title in (("wheel order", "A color wheel's order"), ("new squares", "New squares")):
            icon = widgets.info(row_i, title, data.get(key))
            if icon is not None:
                icon.pack(side="left", padx=(0, 4))
        self.members = tk.Listbox(side, height=6, width=20, exportselection=False)
        self.members.pack(fill="x")
        self.members.bind("<Double-1>", self.member_opened)
        row = ttk.Frame(side)
        row.pack(fill="x", pady=4)
        ttk.Button(row, text="Up", width=6, command=lambda: self.shift(-1)).pack(side="left")
        ttk.Button(row, text="Down", width=6, command=lambda: self.shift(1)).pack(side="left", padx=4)
        ttk.Button(row, text="Remove from game", command=self.remove_member).pack(side="left", padx=(4, 0))
        ttk.Label(side, text="Move to:").pack(anchor="w", pady=(2, 0))
        move = ttk.Frame(side)              # (the box and its button on one row: the grid keeps the height)
        move.pack(fill="x")
        self.dest = tk.StringVar()
        self.dest_cb = ttk.Combobox(move, textvariable=self.dest, state="readonly", width=18)
        self.dest_cb.pack(side="left", fill="x", expand=True)
        widgets.tip(self.dest_cb, "Another square (by its first character), or a new square of its own. A square's "
                                  "own character can't leave it.")
        ttk.Button(move, text="Move", command=self.move_member).pack(side="left", padx=(4, 0))

        area = ttk.Frame(body)          # (as tall as the grid's rows, not the window: Nick, no empty dark space)
        area.pack(side="left", fill="both", expand=True, anchor="n")
        self.canvas = tk.Canvas(area, width=CANVAS_MIN[0], height=CANVAS_MIN[1], background="#20283a",
                                highlightthickness=0)
        self.xbar = ttk.Scrollbar(area, orient="horizontal", command=self.canvas.xview)
        self.ybar = ttk.Scrollbar(area, orient="vertical", command=self.canvas.yview)
        self.canvas.configure(xscrollcommand=self.xbar.set, yscrollcommand=self.ybar.set)
        self.canvas.grid(row=0, column=0, sticky="nsew")
        area.rowconfigure(0, weight=1)
        area.columnconfigure(0, weight=1)
        self.canvas.bind("<ButtonPress-1>", self.press)
        self.canvas.bind("<B1-Motion>", self.motion)
        self.canvas.bind("<ButtonRelease-1>", self.release)
        self.canvas.bind("<Configure>", self._canvas_configured)
        self.redraw()

    def _canvas_configured(self, e):
        """Redraw only when the grid width changes, and debounce heavily while the window is being dragged/resized.

        The grid chooses its own height, so reacting to height Configure events used to create needless redraw loops.
        """
        if e.width == self._resize_width:
            return
        self._resize_width = e.width
        if self._resize_job:
            try:
                self.canvas.after_cancel(self._resize_job)
            except tk.TclError:
                pass
        self._resize_job = self.canvas.after(180, self._finish_resize)

    def _finish_resize(self):
        self._resize_job = None
        if self.canvas.winfo_exists():
            self.redraw()

    # --- the order

    def chars(self):
        """The characters the patch will have past the stock roster: the ticked new characters, imported ones and
        recolors (a recolor as a stand-in definition: its id, name, base, swatch and rules; face() shows the
        base's portrait recolored with them)."""
        out = [d for _, kind, d, _ in self.app.roster() if kind in ("new", "imported")]
        for name, kind, r, cid in self.app.roster():
            if kind == "recolor" and cid is not None:
                d = {"id": r["id"], "name": r["name"], "template": recolor_template(r["base"]),
                     "color": r.get("swatch"),
                     "recolor": r.get("recolor", []), **({"wheel": r["wheel"]} if r.get("wheel") else {})}
                face = added_base_face(self.game, r)
                if face:                                    # an added base (Rosalina): its own face, recolored,
                    d["icon"] = {"side": face, "front": face}   # which face() uses as it is (git-d0)
                    d.pop("recolor")
                out.append(d)
        return out

    def default(self):
        return self.go.default_order(self.game.dol, self.chars())

    def current(self):
        return self.order if self.enabled.get() else None

    def edit(self):
        if self.order is None or not self.enabled.get():
            self.order = self.order or copy.deepcopy(self.default())
            self.enabled.set(True)
        return self.order

    def set_option(self, order):
        self.order = copy.deepcopy(order) if order else None
        self.enabled.set(self.always_on or order is not None)
        self.redraw()

    def toggled(self):
        if self.enabled.get():
            if self.game is None:
                self.enabled.set(False)
                self.load_game(then=self.toggled)
                return
            self.edit()
        self.redraw()

    def reset(self):
        self.order, self.sel = None, None
        self.enabled.set(self.always_on)
        self.redraw()

    def fit_to_roster(self):
        """After characters are ticked or unticked: names the patch no longer has leave the order (an emptied new
        square goes), and new ones join the square the patcher would give them."""
        if not self.order or self.game is None:
            return
        default = self.default()
        known = {n for sq in default for n in sq}
        order = [[n for n in sq if n in known] for sq in self.order]
        order = [sq for sq in order if sq]
        have = {n for sq in order for n in sq}
        for sq in default:
            for n in sq:
                if n in have:
                    continue
                host = next((o for o in order if set(o) & set(sq)), None)   # a square with its wheel-mates
                if host is not None:
                    host.insert(min(sq.index(n), len(host)), n)
                else:
                    order.append([n])
                have.add(n)
        self.order = order

    # --- the wheel of the picked square

    def fill_members(self):
        self.members.delete(0, "end")
        order = self.current() or (self.default() if self.game else [])
        if self.sel is None or self.sel >= len(order):
            self.dest_cb.configure(values=[])
            return
        for n in order[self.sel]:
            self.members.insert("end", n)
        self.dest_cb.configure(values=[f"{i + 1}: {sq[0]}" for i, sq in enumerate(order) if i != self.sel]
                               + [NEW_SQUARE])

    def remove_member(self):
        """Turn the selected non-stock character off instead of merely deleting its grid entry.

        The old behavior could not support a persistent manual deletion: fit_to_roster() correctly re-added every
        enabled character, and grid_order.validate() requires every enabled new character to have a square. Turning
        its roster variable off makes removal persistent across redraws, saves and reloads. Stock characters cannot
        be removed because the game's 41 stock heads are structurally required.
        """
        from tkinter import messagebox
        order = self.current() or (self.default() if self.game else [])
        if self.sel is None or self.sel >= len(order):
            return
        picked = self.members.curselection()
        index = picked[0] if picked else 0
        if not order[self.sel] or index >= len(order[self.sel]):
            return
        name = order[self.sel][index]
        try:
            import character_window
            e = character_window.entry(self.app, name)
        except Exception:
            e = None
        if e is None or e[1] == "stock" or e[5] is None:
            messagebox.showinfo("Remove from game", f"{name} is a stock character and can't be removed from the "
                                "character-select roster. New, recolored and imported characters can be removed.")
            return
        if not messagebox.askyesno("Remove from game", f"Remove {name} from this build?\n\n"
                                   "It will stay installed in the tool, but it will no longer appear on the grid. "
                                   "You can add it back later from 'Not in the game yet'."):
            return
        e[5].set(False)
        self.fit_to_roster()
        self.sel = min(self.sel, len(self.order or []) - 1) if self.order else None
        self.fill_members()
        self.redraw()

    def shift(self, d):
        m = self.members.curselection()
        if self.sel is None or not m:
            return
        sq = self.edit()[self.sel]
        i, j = m[0], m[0] + d
        if 0 <= j < len(sq):
            sq[i], sq[j] = sq[j], sq[i]
            self.redraw()
            self.members.selection_set(j)

    def move_member(self):
        m = self.members.curselection()
        if self.sel is None or not m or not self.dest.get():
            return
        order = self.edit()
        name = order[self.sel].pop(m[0])
        if self.dest.get() == NEW_SQUARE:
            order.append([name])
        else:
            order[int(self.dest.get().split(":")[0]) - 1].append(name)
        if not order[self.sel]:
            order.pop(self.sel)
            self.sel = None
        self.dest.set("")
        self.redraw()

    # --- a character's color wheel, from its window (the character window's "Color wheel" pick: a player's
    #     imported Dry Bowser onto Bowser's wheel without finding Move to here)

    def wheels(self):
        """The stock squares a new character can join, by their own character (Mario, Bowser, ...), in grid order."""
        if self.game is None:
            return []
        r = self.go.Roster(self.game.dol, self.chars())
        order = self.current() or self.default()
        return [r.name(r.heads[head]) for kind, head, _, _ in self.go._parse(order, r) if kind == "stock"]

    def wheel_of(self, name):
        """The stock square's character whose wheel `name` is on, None on a square of its own (or not in the game)."""
        order = (self.current() or self.default()) if self.game is not None else []
        hosts = set(self.wheels())
        low = str(name).strip().lower()
        sq = next((sq for sq in order if any(str(m).strip().lower() == low for m in sq)), None)
        return sq[0] if sq and sq[0] in hosts and str(sq[0]).strip().lower() != low else None

    def place(self, name, host=None):
        """Put `name` on `host`'s color wheel (a stock square's own character), or with host None on a new square
        of its own, as Move to does. Returns None when done, else why not in plain words."""
        if self.game is None:
            return "Pick your game first."
        order = self.edit()
        low = lambda v: str(v).strip().lower()  # noqa: E731
        at = next((i for i, sq in enumerate(order) if any(low(m) == low(name) for m in sq)), None)
        if at is None:
            return f"{name} isn't in the game: tick In the game first."
        to = next((i for i, sq in enumerate(order) if host is not None and low(sq[0]) == low(host)), None)
        if host is not None and to is None:
            return f"There's no {host} square on the grid."
        if to == at or (host is None and len(order[at]) == 1 and low(order[at][0]) == low(name)):
            return None                                     # there already
        if to is not None and len(order[to]) >= self.go._members():
            return (f"{host}'s color wheel is full ({self.go._members()} characters): move one of them first.")
        if to is None and sum(1 for sq in order if sq) >= self.go.MAX_SQUARES:
            return f"The grid is full ({self.go.MAX_SQUARES} squares): put {name} on a color wheel instead."
        m = next(m for m in order[at] if low(m) == low(name))
        order[at].remove(m)
        if to is not None:
            order[to].append(m)
        else:
            order.append([m])
            to = len(order) - 1
        if not order[at]:
            order.pop(at)
            to -= to > at
        self.sel = to
        self.redraw()
        return None

    # --- the grid

    def redraw(self):
        cv = self.canvas
        cv.delete("all")
        self.images, self.cells = [], []
        W, H = fit.size(cv)
        if self.game is None:
            self.ask_height(CANVAS_MIN[1])
            cv.create_text(W // 2, H // 2, fill="#ccc", width=W - 20, justify="center",
                           text="Pick your game at the top: the grid is drawn from it.")
            self.room_label.configure(text="")
            self.say_problems([])
            self.fill_members()
            return
        self.fit_to_roster()
        order, chars = self.current() or self.default(), self.chars()
        problems = self.go.validate(order, self.game.dol, chars)
        self.say_problems(problems)
        try:
            room = self.go.room(order, self.game.dol, chars)
            self.room_label.configure(text=f"{len(order)} squares of {self.go.MAX_SQUARES}"
                                           f" ({room['squares_left']} left)")
        except AssertionError:
            self.room_label.configure(text=f"{len(order)} squares of {self.go.MAX_SQUARES}")
        if not self.go.STOCK_HEAD_COUNT <= len(order) <= self.go.MAX_SQUARES:
            self.fill_members()
            return
        cells = self.go.cells(self.game, len(order))
        x0, y0 = min(x for x, _ in cells), min(y for _, y in cells)
        span_x = max(x for x, _ in cells) - x0 + CELL
        span_y = max(y for _, y in cells) - y0 + CELL
        # Size from the available WIDTH and then ask for exactly enough height for every row.  The beta page itself
        # scrolls vertically, so the grid does not need to crush its portraits just because the canvas happened to
        # start 200 px tall.  This keeps the whole grid visible with no grid scrollbars while using much more of a
        # large window.  A narrow window can still shrink the cells enough to fit horizontally.
        avail_w = max(80, W - 8)
        k = min(avail_w / span_x, MAX_SCALE)
        k = max(0.24, k)
        self.q = q = max(12, round(CELL * k))
        wide, tall = 8 + span_x * k, 8 + span_y * k
        wanted_h = max(CANVAS_MIN[1], int(round(tall)))
        H = self.ask_height(wanted_h)
        cv.configure(scrollregion=(0, 0, max(W, int(round(wide))), max(H, wanted_h)))
        self.xbar.grid_remove()
        # Normally the beta page grows to the complete grid height.  If the window manager/layout temporarily clips
        # it anyway, keep every row reachable instead of silently hiding the bottom of the grid.
        if H + 4 < wanted_h:
            self.ybar.grid(row=0, column=1, sticky="ns")
        else:
            self.ybar.grid_remove()
        from recolor_editor import photo
        fh = max(8, round(q - 4))
        fw = max(8, round(fh * 48 / 51))
        for i, ((x, y), sq) in enumerate(zip(cells, order)):
            cx, cy = 4 + round((x - x0) * k), 4 + round((y - y0) * k)
            cache_key = str(sq[0]).strip().lower()
            img = self.face_cache.get(cache_key)
            if img is None:
                try:
                    img = self.go.face(sq[0], self.game, chars)
                except (AssertionError, KeyError, OSError, StopIteration):
                    img = self.face_of_base(sq[0])
                if img is not None:
                    self.face_cache[cache_key] = img
            tag = f"sq{i}"
            outline = "#ffd84a" if i == self.sel else "#556"
            cv.create_rectangle(cx, cy, cx + q, cy + q, outline=outline, width=2, tags=(tag, "sq"))
            if img is not None:
                pkey = (cache_key, fw, fh)
                p = self.photo_cache.get(pkey)
                if p is None:
                    p = photo(img.resize((fw, fh)), zoom=1)
                    self.photo_cache[pkey] = p
                self.images.append(p)
                cv.create_image(cx + q / 2, cy + q / 2, image=p, anchor="center", tags=(tag, "sq"))
            else:
                cv.create_text(cx + q / 2, cy + q / 2, text=sq[0], fill="#eee", width=q, font=("", 7),
                               tags=(tag, "sq"))
            if len(sq) > 1:
                cv.create_text(cx + q - 2, cy + q - 2, text=f"x{len(sq)}", fill="#fff", anchor="se",
                               font=("", 8, "bold"), tags=(tag, "sq"))
            self.cells.append((tag, cx, cy))
        self.fill_members()

    def ask_height(self, h):
        """The canvas asks for h px of height; a change tells the page (SIZE_EVENT). Returns the height it draws to:
        what it's laid out at, else h."""
        if int(self.canvas.cget("height")) != h:
            self.canvas.configure(height=h)
            self.frame.event_generate(SIZE_EVENT, when="tail")
        got = self.canvas.winfo_height()
        return got if got > 1 else h

    def say_problems(self, problems):
        self.problems.configure(text="\n".join(problems))
        if problems and not self.problems_shown:
            self.problems.pack(side="bottom", fill="x", pady=4, before=self.body)
        elif not problems and self.problems_shown:
            self.problems.pack_forget()
        self.problems_shown = bool(problems)

    def face_of_base(self, name):
        """A square whose own face can't be read: a recolor before it's made, its base's face; a new or imported
        character (its icon missing or unreadable), its template's portrait, never just its name (Nick's Luma)."""
        e = next(((k, d) for n, k, d, _ in self.app.roster() if n == name), None)
        try:
            if e and e[0] == "recolor":
                return self.go.face(e[1]["base"], self.game, self.chars())
            if e and e[0] in ("new", "imported") and e[1].get("template") is not None:
                import recolor
                return self.game.portrait(recolor.char_id(e[1]["template"]), "side")
        except (AssertionError, KeyError, OSError, StopIteration, ValueError):
            pass
        return None

    def square_at(self, x, y):
        x, y = self.canvas.canvasx(x), self.canvas.canvasy(y)
        for i, (tag, cx, cy) in enumerate(self.cells):
            if cx <= x <= cx + self.q and cy <= y <= cy + self.q:
                return i
        return None

    def press(self, e):
        i = self.square_at(e.x, e.y)
        self.drag = (i, e.x, e.y, e.x, e.y) if i is not None else None

    def motion(self, e):
        if self.drag:
            i, sx, sy, x, y = self.drag
            self.canvas.move(self.cells[i][0], e.x - x, e.y - y)
            self.canvas.tag_raise(self.cells[i][0])
            self.drag = (i, sx, sy, e.x, e.y)

    def release(self, e):
        if not self.drag:
            return
        i, sx, sy = self.drag[:3]
        self.drag = None
        if abs(e.x - sx) + abs(e.y - sy) < 6:       # a click: pick the square
            self.sel = i
            self.redraw()
            order = self.current() or self.default()
            if self.on_open is not None and i < len(order):
                self.on_open(order[i][0])
            return
        j = self.square_at(e.x, e.y)
        if j is None or j == i:
            self.redraw()
            return
        self.swap(i, j)

    def member_opened(self, e=None):
        m = self.members.curselection()
        if self.on_open is not None and m:
            self.on_open(self.members.get(m[0]))

    def swap(self, i, j):
        order = self.edit()
        order[i], order[j] = order[j], order[i]
        self.sel = j
        self.redraw()

    # --- the game

    def load_game(self, then=None):
        self.face_cache.clear()
        self.photo_cache.clear()
        import recolor

        def got(folder):
            self.game = recolor.Game(str(folder))
            self.redraw()
            if then:
                then()
        self.app.with_game_folder(got, quiet=then is None)
