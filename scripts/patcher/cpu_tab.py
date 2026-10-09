"""The patcher window's CPU levels tab (Nick, 2026-09-28: the level 5 and 6 CPU numbers players may change). Built
from cpu_settings.fields(), whatever it holds, so a setting added, retuned or removed there shows up here with no
edit: each section's settings with a Level 5 and a Level 6 box (one box for a setting both levels share), today's
value as each box's default and the game's level 4 value beside it. Only what a player changed goes in the profile,
as the option "cpu-settings" (patch.check_cpu_settings), with the feature ticked; a player who never touched a setting
gets its new default when we retune it. A set can be saved, shared and imported as a .slgcpu file (cpu_settings.save
/ load; settings a file has that this patcher doesn't are dropped and named).
SWITCHES (Nick: "per level switches, but make it easy to change both or one or the other"): the first section, a row
per CPU switch with Both, Level 5 and Level 6 boxes. Both ticks or unticks the two together; a level box alone makes it
that level only (the option's {switch: {"5": bool, "6": bool}}, only while exactly one level is on). A switch on at
neither level is unticked, so the build leaves its code out. The switches' only home is this tab (feature_home), and a
value box is greyed out at a level its switch is off.
LEVEL 5 ONLY (Nick, 2026-09-28, the Characters Beta: "can we only let them edit stats for level 5?"): an edition's
"cpu_levels_editable" (patch.cpu_levels_editable; the beta: [5]) shows only those levels' columns and switch boxes,
and an import or a profile loses its other-level values, said on the status line (cpu_settings.only_levels;
patch.check_cpu_settings drops them from a hand-edited profile too). Every setting has a value per level (Nick,
2026-09-29: "EVERYTHING in level 5 should be changeable"; cpu_settings split), so each one is editable there, in one
table: Setting | Level 5 (its box and Stock button); no Level 4 column ("why does it say level 4, we don't want to
modify that"; the full patcher keeps it). A switch shows its plain name with a line under it saying what it does
(cpu_settings.SWITCHES). A lock (cpu_settings.LOCKS: Never walk the batter) on at a level holds the settings it names
greyed at its value there.
OURS (Nick, 2026-09-29: "which fields are our custom ones and which are originally in the game"): a setting or switch
our own CPU code adds (cpu_settings fields()' "ours") has a grey "(ours)" after its name, as does the levels' own
switch; the rest are values the game's CPU already has. OURS_NOTE under the intro says so.
"""
import tkinter as tk
import style
from tkinter import ttk, messagebox, filedialog, simpledialog
from pathlib import Path

import fit
import patch
import widgets

FOLDER = patch.ROOT / "cpu"             # the player's saved sets (.slgcpu)
FEATURE, OPTION = "cpu-settings", "cpu-settings"
INTRO = ("Sets how the level 5 (Superstar) and level 6 (Legend) CPU plays: how well it reads and hits pitches, how its "
         "pitch model learns, how fast its fielders react, how it uses items, and more. Each box starts at the "
         "base value; change only what you want. Levels 1-4 are always the game's own.")
HOWTO = dict(
    steps=["Pick a section on the left; sections with changes are marked with *.",
           "Change a value in the Level 5 or Level 6 box. One box means both levels share it. The grey number is "
           "the game's level 4 value, where there is one.",
           "Stock puts one box back to its base value; Back to base values puts back everything.",
           "The line under the table says what's out of range, in plain words.",
           "The Switches section turns whole CPU behaviours on or off: Both for both levels, or tick just Level 5 "
           "or Level 6. A setting does nothing at a level its switch is off."],
    share="Save keeps this set under a name; Share... writes it to a file for others; Import... loads one someone "
          "sent you (it replaces your changes).",
    refused="a value out of range, a setting whose switch is off, or a file that isn't a set of CPU settings.")
OURS_TAG = "(ours)"
OURS_NOTE = ("(ours) marks a setting or switch the patcher adds with its own CPU code. The rest are values the game's "
             "own CPU already uses, set here for these levels.")
# an edition that changes level 5 only (the beta; its How to never shows there, but says the same)
INTRO_5 = ("Sets Level 4 (All-Star) game-native CPU values and Level 5 (Superstar) values. Every Level 4 game value "
           "starts at the stock number shown at right. Custom rows marked (ours) begin at Level 5 because the stock game "
           "has no Level 4 value for them. Level 6 (Legend) keeps its base values.")
HOWTO_5 = dict(HOWTO, steps=[
    "Pick a section on the left; sections with changes are marked with *.",
    "Change a value in the Level 4 or Level 5 box. Level 4 boxes exist for game-native rows; (ours) rows have no stock Level 4 implementation.",
    "Stock puts one box back to its base value; Back to base values puts back everything.",
    "The line under the table says what's out of range, in plain words.",
    "The Switches section turns whole CPU behaviours on or off at level 5. A setting does nothing while its switch "
    "is off."])


def _num(x):
    return int(x) if float(x).is_integer() else x


class CpuTab:
    def __init__(self, notebook, app, folder=FOLDER, embedded=False):
        """notebook: the patcher's tabs; embedded: a plain parent instead (the beta's CPU levels window)."""
        import cpu_settings
        self.cs, self.app, self.folder = cpu_settings, app, Path(folder)
        self.info = {f["key"]: f for f in cpu_settings.fields()}
        self.sections = cpu_settings.SECTIONS
        self.edits = {}                         # {key: value}: only what differs from today's values
        self.levels = patch.cpu_levels_editable()     # the levels a player may change (the beta: [5])
        self.all_levels = set(self.levels) == set(cpu_settings.LEVELS)
        self.note = ""                          # what an import / a profile lost (other levels), on the status line
        self.current = None
        self.frame = ttk.Frame(notebook, padding=6)
        if embedded:
            self.frame.pack(fill="both", expand=True)
        else:
            notebook.add(self.frame, text="CPU levels")
        fit.label(self.frame, INTRO if self.all_levels else INTRO_5, grey=True).pack(fill="x")
        fit.label(self.frame, OURS_NOTE, grey=True).pack(fill="x", pady=(2, 0))
        body = ttk.Frame(self.frame)
        body.pack(fill="both", expand=True, pady=(4, 0))
        left = ttk.Frame(body)
        left.pack(side="left", fill="y")
        self.tree = ttk.Treeview(left, show="tree", selectmode="browse", height=11)
        self.tree.column("#0", width=170)
        self.tree.pack(side="left", fill="y")
        for sec in self.sections:
            self.tree.insert("", "end", iid=sec, text=sec)
        self.tree.bind("<<TreeviewSelect>>", lambda e: self.picked())
        right = ttk.Frame(body, padding=(10, 0, 0, 0))
        right.pack(side="left", fill="both", expand=True)
        top = ttk.Frame(right)
        top.pack(fill="x")
        self.title = ttk.Label(top, text="Pick a section on the left.", font="SluggersSection")
        self.title.pack(side="left")
        self.scroll = widgets.Scrolled(right, height=150)
        self.scroll.pack(fill="both", expand=True)
        self.howto = widgets.HowTo(top, key="cpu", body_in=right, before=self.scroll,
                                   **(HOWTO if self.all_levels else HOWTO_5))
        self.howto.pack(side="right")
        self.problems = fit.label(right, self.no_changes())
        self.problems.pack(fill="x")
        buttons = ttk.Frame(right)
        buttons.pack(fill="x", pady=(4, 0))
        ttk.Button(buttons, text="Back to base values", command=self.reset_all).pack(side="left")
        ttk.Button(buttons, text="Import...", command=self.import_file).pack(side="right")
        ttk.Button(buttons, text="Share...", command=self.share).pack(side="right", padx=4)
        ttk.Button(buttons, text="Save as...", command=self.save).pack(side="right")   # (a named set; the window's own Save keeps it)
        self.switch_ids = [k for k, f in self.info.items() if f["kind"] == "switch"]
        fv, home = getattr(app, "fvars", {}), getattr(app, "feature_home", None)
        for fid in ["level-5"] + self.switch_ids:          # their one place in the window
            if fid in fv and home is not None and fid not in home:
                home[fid] = "CPU levels"
                fv[fid].trace_add("write", lambda *a: self.switches_changed())
        self._redraw = None
        self.tree.selection_set(self.sections[0])
        self.picked()

    # --- the page

    def picked(self):
        sel = self.tree.selection()
        sec = sel[0] if sel and sel[0] in self.sections else None
        self.current = sec
        for w in self.scroll.inner.winfo_children():
            w.destroy()
        if sec is None:
            self.title.configure(text="Pick a section on the left.")
            return
        self.title.configure(text=sec)
        grid = ttk.Frame(self.scroll.inner)
        grid.pack(anchor="w", fill="x")
        if sec == "Switches":
            self.draw_switches(grid)
            return
        heads = ["Setting"] + [f"Level {lvl}" for lvl in self.levels] + ["Stock data"]
        game_col = len(heads) - 1
        for c, head in enumerate(heads):
            ttk.Label(grid, text=head, style="Hint.TLabel").grid(row=0, column=c, sticky="w",
                                                                 padx=(0, style.PAD), pady=(0, style.GAP))
        r = 1
        for key, f in self.info.items():
            if f["section"] != sec:
                continue
            mine = [lvl for lvl in f["levels"] if lvl in self.levels]
            if not mine:                               # a setting only at a level this edition doesn't change
                continue
            locked = self.locked(f)
            cell = ttk.Frame(grid)
            cell.grid(row=r, column=0, sticky="w", padx=(0, style.PAD), pady=1)
            name = ttk.Label(cell, text=f["label"] + (f" ({f['unit']})" if f["unit"] else ""))
            name.pack(side="left")
            self.ours(cell, f["ours"])
            widgets.tip(name, f["tip"] + ("" if f["feature"] in self.on_features() else
                                          f" (needs the \"{f['feature']}\" switch on)"))
            for lvl in ["both"] if f["shared"] else mine:
                col = 1 if lvl == "both" else 1 + self.levels.index(lvl)
                held = None if lvl == "both" else self.held(key, lvl)
                w = self.box(grid, key, f, lvl, locked=locked, held=held)
                w.grid(row=r, column=col, columnspan=len(self.levels) if lvl == "both" else 1, sticky="w",
                       padx=(0, style.PAD))
            if f["levels"] == [5] and 6 in self.levels:
                ttk.Label(grid, text="no error at level 6", style="Hint.TLabel").grid(
                    row=r, column=1 + self.levels.index(6), sticky="w")
            game = f["game"]
            stock_text = "vanilla: not present" if game is None else str(game)
            ttk.Label(grid, text=stock_text, style="Hint.TLabel").grid(row=r, column=game_col, sticky="w")
            r += 1

    @staticmethod
    def ours(parent, yes):
        """A grey "(ours)" after a name: a setting / switch our own CPU code adds (OURS)."""
        if yes:
            ttk.Label(parent, text=OURS_TAG, style="Hint.TLabel").pack(side="left", padx=(4, 0))

    def locked(self, f):
        """A setting both levels share while this edition changes only one of them (none since 2026-09-29: every
        setting has a value per level): shown at today's value, greyed."""
        return f["shared"] and not set(f["levels"]) <= set(self.levels)

    def held(self, key, lvl):
        """The value a lock that's on at this level holds `key` at (cpu_settings.LOCKS: Never walk the batter holds
        the 3-ball rates at 0), or None."""
        for lock, (keys, v) in self.cs.LOCKS.items():
            if key in keys and lock in self.info and self.value(lock, lvl, self.info[lock]["default"][lvl]):
                return v
        return None

    # --- switches

    def levels_on(self, fid):
        """{4/5/6: on} for a switch. Level 4 custom systems default off; levels 5/6 default on."""
        fv = getattr(self.app, "fvars", {})
        if fid in fv and not fv[fid].get():
            return {lvl: False for lvl in self.cs.LEVELS}
        m = self.cs.mask(self.edits, fid)
        return {4: bool(m & 4), 5: bool(m & 1), 6: bool(m & 2)}

    def draw_switches(self, grid):
        fv = getattr(self.app, "fvars", {})
        titles, what = getattr(self.app, "titles", {}), getattr(self.app, "what", {})
        if "level-5" in fv:
            row = ttk.Frame(grid)
            row.grid(row=0, column=0, columnspan=6, sticky="w", pady=(0, 6))
            cb = ttk.Checkbutton(row, text=titles.get("level-5", "CPU levels 5 and 6"), variable=fv["level-5"],
                                 command=lambda: self.app.toggled("level-5"))
            cb.pack(side="left")
            self.ours(row, True)
            widgets.tip(cb, what.get("level-5", ""))
        top = 1
        if not self.all_levels:
            hidden = [lvl for lvl in self.cs.LEVELS if lvl not in self.levels]
            if hidden:
                ttk.Label(grid, text="Editable here: " + ", ".join(f"Level {x}" for x in self.levels) +
                          ". " + ", ".join(f"Level {x}" for x in hidden) + " keeps its base values.",
                          foreground=widgets.GREY).grid(row=1, column=0, columnspan=6, sticky="w", pady=(0, 6))
                top = 2
        switch_levels = [lvl for lvl in self.levels if lvl in self.cs.LEVELS]
        heads = ["Switch"] + [f"Level {lvl}" for lvl in switch_levels] + ["Stock"]
        for c, head in enumerate(heads):
            ttk.Label(grid, text=head, style="Hint.TLabel").grid(row=top, column=c, sticky="w",
                                                                 padx=(0, style.PAD), pady=(0, style.GAP))
        self.switch_vars = {}
        for i, fid in enumerate(self.switch_ids):
            r = top + 1 + i
            cell = ttk.Frame(grid)
            cell.grid(row=r, column=0, sticky="w", padx=(0, style.PAD), pady=(0, style.GAP))
            head = ttk.Frame(cell); head.pack(anchor="w")
            ttk.Label(head, text=self.info[fid]["label"]).pack(side="left")
            self.ours(head, self.info[fid]["ours"])
            ttk.Label(cell, text=self.info[fid]["tip"], style="Hint.TLabel", wraplength=430).pack(anchor="w")
            state = self.levels_on(fid)
            vars_for = {}
            for col, lvl in enumerate(switch_levels, start=1):
                var = tk.BooleanVar(value=state[lvl]); vars_for[lvl] = var
                cmd = lambda fid=fid, vars_for=vars_for: self.set_levels(fid, {k: v.get() for k, v in vars_for.items()})
                b = ttk.Checkbutton(grid, variable=var, command=cmd); b.var = var
                b.grid(row=r, column=col, sticky="nw", padx=(0, style.PAD))
            self.switch_vars[fid] = vars_for
            stock = "off" if self.info[fid]["ours"] else "game's level 4"
            ttk.Label(grid, text=stock, style="Hint.TLabel").grid(row=r, column=1+len(switch_levels), sticky="nw")

    def set_levels(self, fid, shown):
        """Save per-level switch choices. Unshown levels retain their base defaults."""
        defaults = {4: False, 5: True, 6: True}
        values = dict(defaults)
        values.update({int(k): bool(v) for k, v in shown.items()})
        changed = {str(lvl): values[lvl] for lvl in self.cs.LEVELS if values[lvl] != defaults[lvl]}
        if changed:
            self.edits[fid] = changed
        else:
            self.edits.pop(fid, None)
        fv = getattr(self.app, "fvars", {})
        if any(values.values()):
            self.app.tick({fid}, why=f"the CPU levels tab turns on {fid}")
        elif fid in fv:
            fv[fid].set(False)
        if self.edits:
            self.app.tick({FEATURE}, why="the CPU levels tab changes a CPU value")
        self.refresh(); self.later_redraw()

    def switches_changed(self):
        """A switch ticked or unticked anywhere (a profile, Tick everything, a requirement): an unticked switch drops
        its per-level choice, and the page follows."""
        fv = getattr(self.app, "fvars", {})
        for fid in self.switch_ids:
            if fid in fv and not fv[fid].get():
                self.edits.pop(fid, None)
        self.refresh()
        self.later_redraw()

    def later_redraw(self):
        if self._redraw is None:                   # once, after the click that changed it has finished
            self._redraw = self.frame.after_idle(self._do_redraw)

    def _do_redraw(self):
        self._redraw = None
        self.picked()

    def box(self, parent, key, f, lvl, locked=False, held=None):
        """locked: a shared value this edition can't change (today's value, greyed); held: a lock holds it at this
        value (greyed)."""
        today = f["default"][5 if lvl == "both" else lvl]
        now = today if locked else self.value(key, lvl, today)
        if held is not None:
            now, locked = held, True
        level_state = self.levels_on(f["feature"])
        live = any(level_state.values()) if lvl == "both" else level_state.get(lvl, True)
        if f["boolean"]:
            var = tk.BooleanVar(value=bool(now))
            w = ttk.Checkbutton(parent, text="on", variable=var,
                                command=lambda: self.edited(key, lvl, int(var.get()), today))
            w.var = var
            w.locked = locked
            if not live or locked:
                w.state(["disabled"])
            return w
        w = widgets.NumberField(parent, f["label"], f["min"], f["max"], stock=today,
                                kind=int if f["integer"] else float, step=f["step"] or 1, show_label=False, short=True,
                                on_change=lambda v: self.edited(key, lvl, v, today))
        w.set(now)
        w.locked = locked
        if not live or locked:                     # its switch is off at this level: the value does nothing there
            w.box.state(["disabled"])
        if locked:                                 # (its Stock button too)
            for c in w.winfo_children():
                if c.winfo_class() == "TButton":
                    c.state(["disabled"])
        return w

    def no_changes(self):
        return "No changes: Level 4 uses stock/vanilla behavior and Level 5 uses its base values."      # (Nick: not "today's values")

    def value(self, key, lvl, today):
        v = self.edits.get(key)
        if v is None:
            return today
        if isinstance(v, dict):
            return v.get(str(lvl), today)
        return v

    def edited(self, key, lvl, v, today):
        """One box: kept only while it differs from today's value."""
        f = self.info[key]
        if v is None or self.locked(f) or lvl != "both" and (lvl not in self.levels or self.held(key, lvl) is not None):
            return
        v = _num(v)
        if f["shared"] or f["levels"] == [5]:
            if v == today:
                self.edits.pop(key, None)
            else:
                self.edits[key] = v
        else:
            per = dict(self.edits.get(key) or {})
            if v == today:
                per.pop(str(lvl), None)
            else:
                per[str(lvl)] = v
            if per:
                self.edits[key] = per
            else:
                self.edits.pop(key, None)
        if self.edits:
            self.app.tick({FEATURE}, why="the CPU levels tab changes a CPU value")
        self.refresh()
        if key in self.cs.LOCKS:                   # the settings it holds follow
            self.later_redraw()

    def on_features(self):
        fv = getattr(self.app, "fvars", {})
        return {k for k, v in fv.items() if v.get()} if fv else {f["feature"] for f in self.info.values()}

    def refresh(self):
        changed = {self.info[k]["section"] for k in self.edits if k in self.info}
        for sec in self.sections:
            self.tree.item(sec, text=sec + ("  *" if sec in changed else ""))
        found = self.cs.check(self.edits, self.on_features() | {"level-5"} if getattr(self.app, "fvars", None)
                              else None)
        n = len(self.edits)
        self.problems.configure(
            text="\n".join(found) if found else
            (f"{n} setting{'s' if n != 1 else ''} changed." if n else
             self.no_changes()) + (f"\n{self.note}" if self.note else ""),
            foreground=widgets.RED if found else widgets.GREY)
        return found

    def reset_all(self):
        self.edits, self.note = {}, ""
        self.picked()
        self.refresh()

    # --- files

    def save(self):
        if not self.edits:
            messagebox.showinfo("CPU levels", "There are no changes to save yet.")
            return
        name = simpledialog.askstring("Save", "Name for this set of CPU settings:", initialvalue="My CPU")
        if not name or not widgets.file_name(name):
            return
        self.folder.mkdir(parents=True, exist_ok=True)
        path = self.cs.save(self.edits, widgets.file_name(name), self.folder)
        self.problems.configure(text=f"Saved as {Path(path).name}.", foreground=widgets.GREY)

    def share(self):
        if not self.edits:
            messagebox.showinfo("CPU levels", "There are no changes to share yet.")
            return
        dest = filedialog.asksaveasfilename(title="Share these CPU settings", defaultextension=self.cs.EXTENSION,
                                            filetypes=[("CPU settings", "*" + self.cs.EXTENSION)])
        if dest:
            self.cs.save(self.edits, Path(dest).stem, Path(dest).parent)
            messagebox.showinfo("CPU levels", f"Saved {Path(dest).name}. Anyone with the patcher can Import... it.")

    def import_file(self, src=None):
        src = src or filedialog.askopenfilename(title="Import CPU settings", initialdir=str(self.folder),
                                                filetypes=[("CPU settings", "*" + self.cs.EXTENSION),
                                                           ("All files", "*.*")])
        if not src:
            return
        try:
            _, edits, dropped = self.cs.load(src)
        except ValueError as e:
            messagebox.showwarning("Import", str(e))
            return
        self.edits, self.note = self.trim(edits, Path(src).name)
        if self.edits:
            self.app.tick({FEATURE}, why="the CPU levels tab changes a CPU value")
        self.picked()
        self.refresh()
        if dropped:
            messagebox.showinfo("Import", "This patcher doesn't have these settings, so they were left out: "
                                + ", ".join(dropped))

    def trim(self, edits, where):
        """(edits, status note): only the levels this edition changes (cpu_settings.only_levels); the note names what
        was left out, in plain words ("" if nothing)."""
        if self.all_levels:
            return dict(edits), ""
        edits, lost = self.cs.only_levels(edits, self.levels)
        if not lost:
            return edits, ""
        others = ", ".join(str(lvl) for lvl in self.cs.LEVELS if lvl not in self.levels)
        return edits, (f"Left out of {where}, since only level {', '.join(map(str, self.levels))} can be changed "
                       f"here (level {others} keeps its base values): " + ", ".join(lost) + ".")

    # --- the profile

    def to_profile(self):
        fv = getattr(self.app, "fvars", {})
        edits = {k: v for k, v in self.edits.items()      # a per-level choice only for a switch that's ticked
                 if not (k in self.switch_ids and k in fv and not fv[k].get())}
        return {"options": {OPTION: edits}} if edits else {}

    def load(self, profile):
        value = (profile.get("options") or {}).get(OPTION) or {}
        getattr(self.app, "extra_options", {}).pop(OPTION, None)     # this tab keeps it
        if isinstance(value, str):
            try:
                _, value, _ = self.cs.load(patch.ROOT / value if not Path(value).is_absolute() else value)
            except ValueError:
                value = {}
        self.edits, self.note = self.trim({k: v for k, v in value.items() if k in self.info}
                                          if isinstance(value, dict) else {}, "the profile")
        self.picked()
        self.refresh()

    def needs(self):
        return [({FEATURE}, "CPU values are changed on the CPU levels tab", self.reset_all)] if self.edits else []


TITLE = "CPU levels"


class Window:
    """The Characters Beta's CPU levels window (Nick, 2026-09-28: the CPU levels in the beta; its words allowed here,
    edition.py): the tab in a window of its own, like the beta's Game options... . It edits the patcher's CPU levels (the
    unshown tab, app.cpu, whose state is the profile) on a copy: Save keeps the values and switches as set, Cancel (or
    closing the window) puts both back as they were."""

    def __init__(self, app):
        self.app, self.hidden = app, app.cpu
        self.keep_edits = dict(app.cpu.edits)
        fv = getattr(app, "fvars", {})
        self.keep_ticks = {f: fv[f].get() for f in ["level-5", FEATURE] + app.cpu.switch_ids if f in fv}
        self.win = win = tk.Toplevel(app.root)
        style.title(win, TITLE)
        win.transient(app.root)
        win.geometry("980x680")
        widgets.save_bar(win, self.save, self.cancel)
        self.tab = CpuTab(win, app, embedded=True)
        self.tab.edits = dict(self.keep_edits)
        self.tab.note = app.cpu.note               # (what a loaded profile lost: other levels)
        self.tab.picked()
        self.tab.refresh()
        win.protocol("WM_DELETE_WINDOW", self.cancel)

    def save(self):
        if self.tab.refresh():                     # its problems line says what to change
            return
        self.hidden.edits = dict(self.tab.edits)
        self.hidden.refresh()
        self.win.destroy()

    def cancel(self):
        fv = getattr(self.app, "fvars", {})
        for f, v in self.keep_ticks.items():
            fv[f].set(v)
        self.hidden.edits = dict(self.keep_edits)
        self.hidden.refresh()
        self.win.destroy()


def open_window(app):
    return Window(app)


def add_tab(notebook, app):
    app.cpu = CpuTab(notebook, app)
    return app.cpu
