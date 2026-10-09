"""One character, one window: its stats, chemistry and names (git-b6's char_editor.CharEditor, embedded) with its
model as one more page of the same notebook (a recolor: git-e2's recolor_editor.RecolorEditor; a new character: the
model it's built on), "In the game", and one Save. New recolor opens it for a recolor being made. There's no New
character (Nick: "The options are recolor or add a model from sluggies"): characters made with it before (his SUPER
DK) still open, edit and delete here.

Both patchers use it (git-92 for Nick: "one editor everywhere"): the full patcher's Select grid, New characters &
recolors (New recolor, a recolor's Edit) and the Characters tab's "Edit stats, chemistry and names...";
the Characters Beta's one page (beta_window.py). Open windows are kept on the App (app.char_windows), one per character.
"""
import json
import threading
import tkinter as tk
import style
from pathlib import Path
from tkinter import filedialog, messagebox, simpledialog, ttk

import fit
import widgets

PLAYER = {"made_by": "player"}          # what an edition offers besides its own list (edition.offers)

# "Add a model from Sluggies (.sluggie)..." (git-92, Beta 3 / Patcher 12): a model a player edited with Jaws'
# Sluggies-dat-tools as a new character (scripts/sluggie.py), in both patchers
SLUGGIE_BUTTON = "Add a model from Sluggies (.sluggie)..."     # (no button of its own now: IMPORT_BUTTON)
IMPORT_BUTTON = "Import character (.sluggie, .slgmodel, .glb, model file, or folder)"  # Nick's words: the one way
SLUGGIE_TITLE = "Add a model from Sluggies"


class Busy:
    """A small modal window over the patcher, "Adding <name>..." with an indeterminate bar, while a worker runs (Nick:
    "a loading icon between adding a sluggies model and opening the stat screen"). The window underneath stays
    responsive (redrawn), but takes no clicks until it closes."""

    def __init__(self, app, title, text):
        self.app = app
        self.win = win = tk.Toplevel(app.root)
        style.title(win, title)
        win.transient(app.root)
        win.resizable(False, False)
        win.protocol("WM_DELETE_WINDOW", lambda: None)     # (it closes itself when the work is done)
        self.label = ttk.Label(win, text=text, padding=(16, 14, 16, 6))
        self.label.pack()
        self.bar = ttk.Progressbar(win, mode="indeterminate", length=280)
        self.bar.pack(padx=16, pady=(0, 16))
        self.bar.start(12)
        if getattr(tk, "_headless", None) is None:     # (a test's windows stay withdrawn: headless.install)
            app.root.update_idletasks()
            x = app.root.winfo_rootx() + (app.root.winfo_width() - win.winfo_reqwidth()) // 2
            y = app.root.winfo_rooty() + (app.root.winfo_height() - win.winfo_reqheight()) // 3
            win.geometry(f"+{max(x, 0)}+{max(y, 0)}")
            try:
                win.grab_set()
            except tk.TclError:
                pass

    def say(self, text):
        self.label.configure(text=text)
        self.win.update_idletasks()

    def close(self):
        if self.win.winfo_exists():
            self.bar.stop()
            try:
                self.win.grab_release()
            except tk.TclError:
                pass
            self.win.destroy()


def busy_work(app, title, text, fn, then, error=None, keep=True):
    """Run fn() in a worker with a Busy window up, then then(result) on the window's thread. A result that's an
    exception (fn raised: error(e) turns it into the one then gets, default e itself) closes the Busy window first,
    so then can say why; otherwise it stays up while then works (e.g. opens the character window), then closes.
    keep=False: closed before then in any case (a check whose then asks the player something).
    The three ways to add a character use it: Add a model from Sluggies, Import character, Import a model."""
    busy = Busy(app, title, text)

    def run():
        try:
            r = fn()
        except Exception as e:                      # noqa: BLE001 (said in words, never a traceback in a dialog)
            r = error(e) if error else e
        app.q.put(("call", lambda: finish(r)))

    def finish(r):
        if isinstance(r, Exception) or not keep:
            busy.close()
        try:
            then(r)
        finally:
            busy.close()
    threading.Thread(target=run, daemon=True).start()
    return busy


def add_sluggie(app, path=None, confirm=True):
    """Pick a .sluggie, check it against the player's game, confirm ("Adds '<name>', a new character built from
    <Template>'s model with your edits. <Template> stays as it is."), add it where imported packs go (sluggie.
    add_character; ticked, listed with the imported characters), then open its window. The checks and the add run
    in a worker (the add rebuilds the model against the game). app.last_sluggie: the add's result, when it's done."""
    import char_import, charpack, patch, sluggie
    if path is None:
        path = filedialog.askopenfilename(title=SLUGGIE_TITLE, filetypes=[     # a texture pack: any PNG in its folder
            ("Sluggies model or texture pack picture", "*.sluggie *.png"), ("Sluggies model", "*.sluggie"),
            ("Texture pack picture (Dolphin's tex1_...png)", "*.png")])
        if not path:
            return None
    path = Path(path)

    def names():
        ids, taken = app.taken()
        have = app.imported()
        return set(ids) | {c["id"] for c in have}, list(taken) + [c["name"] for c in have] + [
            n for _, n in getattr(app, "stock", [])]

    def worker(text, fn, then, keep=True):
        busy_work(app, SLUGGIE_TITLE, text, fn, then, error=lambda e: e if isinstance(e, sluggie.SluggieError) else
                  sluggie.SluggieError(f"{type(e).__name__}: {e}"), keep=keep)

    def with_game(folder):
        app.status.set(f"Checking {path.name} against your game ...")
        worker(f"Checking {path.name} against your game...", lambda: sluggie.describe(path, folder),
               lambda r: checked(r, folder), keep=False)

    def checked(r, folder):
        app.status.set("")
        problems = [str(r)] if isinstance(r, Exception) else r["problems"]
        if problems:
            messagebox.showwarning(SLUGGIE_TITLE, f"{path.name} can't be added: " + " ".join(
                p[:1].upper() + p[1:] + ("" if p.endswith(".") else ".") for p in problems))
            return
        ids, taken = names()
        template = r["template"]
        try:
            found = char_import.find(path)          # its name: a folder / file name, else "<Template> (custom)"
            name = (getattr(app, "_replacing", None) or {}).get("name") or charpack.free_name(
                char_import.name_of(found, template, f"{template} (custom)")[0], taken)
        except sluggie.SluggieError as e:
            messagebox.showwarning(SLUGGIE_TITLE, str(e))
            return
        except charpack.PackError as e:
            messagebox.showwarning(SLUGGIE_TITLE, str(e))
            return
        edits = ("\n\nYour edits: " + "; ".join(r["changes"]) + ".") if r["changes"] else \
            f"\n\nNote: it has no edits yet, so it looks just like {template}."
        if r.get("files") and len(r["files"]) > 1:
            edits += "\n\nFiles: " + ", ".join(r["files"]) + " (the model and its low-detail copy)."
        if r.get("notes"):
            edits += "\n\nNote: " + "\nNote: ".join(r["notes"])
        if confirm and not messagebox.askyesno(SLUGGIE_TITLE, f"Adds '{name}', a new character built from "
                                               f"{template}'s model with your edits. {template} stays as it is."
                                               + edits):
            return
        app.status.set(f"Adding {name} ...")
        keep = getattr(app, "_replacing", None) or {}      # Replace: the old name and id (recolors find it by name)
        worker(f"Adding {name}...", lambda: char_import.add(path, folder, dest=patch.IMPORTED_DEST, taken_ids=ids,
                                                            taken_names=taken, name=name, cid=keep.get("id")), added)

    def added(r):
        app.status.set("")
        if isinstance(r, Exception):
            messagebox.showwarning(SLUGGIE_TITLE, f"{path.name} can't be added: {r}")
            return
        app.refresh_imported(tick=[r["name"]])
        app.tick({"new-ids"}, why=r["name"])
        app.status.set(r["summary"] + " Ticked.")
        app.last_sluggie = r
        refresh(app)
        app.root.update_idletasks()
        open_character(app, r["name"])
    return app.with_game_folder(with_game, what="Adding a Sluggies model reads your clean game.")


MODEL_TITLE = "Import a character"


def ask_donor(app, choices, suggested, then):
    """A small dialog: which stock character the model is built on (a dropdown), then then(name) on OK."""
    win = tk.Toplevel(app.root)
    style.title(win, MODEL_TITLE)
    win.transient(app.root)
    body = ttk.Frame(win, padding=12)
    body.pack(fill="both", expand=True)
    fit.label(body, "Which character's skeleton, animations and moves does this model use? (The model's skeleton "
                    "didn't say for sure.)").pack(fill="x")
    var = tk.StringVar(value=suggested or (choices[0] if choices else ""))
    ttk.Combobox(body, textvariable=var, values=choices, state="readonly", width=28).pack(anchor="w", pady=6)

    def ok():
        win.destroy()
        if var.get():
            then(var.get())
    bar = ttk.Frame(body)
    bar.pack(fill="x")
    ttk.Button(bar, text="OK", command=ok).pack(side="right")
    ttk.Button(bar, text="Cancel", command=win.destroy).pack(side="right", padx=4)
    return win


def import_model(app, path=None, donor=None, confirm=True):
    """Import character... with a character file (.slgmodel) or a model folder's file (gui.import_file routes here;
    model_import.read_model: a model block from a game's dt_na.dat, e.g. one of Extra
    Innings' models, with optional side / front portraits and model.json), find its donor from its skeleton (asked with
    a dropdown when the skeleton doesn't say; donor= skips that), confirm, add it where imported packs go, then open
    its window. app.last_model: the add's result. A folder (gui.import_file, confirm=False): whatever char_import finds
    in it (model, portraits, voice, name), no questions (only the base when its skeleton doesn't say), and a plain
    summary after. Never asks for a name (Nick): the file's, model.json's, the file's or folder's, else "New <base>";
    it's editable in the character window."""
    import char_import, charpack, patch, sluggie
    if path is None:
        path = filedialog.askopenfilename(title=MODEL_TITLE, filetypes=[
            ("Character file, Blender model or model file", "*.slgmodel *.glb *.bin *.gpl"),
            ("All files", "*.*")])
        if not path:
            return None
    path = Path(path)
    words = lambda e: e if isinstance(e, sluggie.SluggieError) else sluggie.SluggieError(  # noqa: E731
        f"{type(e).__name__}: {e}")

    def with_game(folder):              # busy_work (git-10): the same loading window as the other two ways to add
        busy_work(app, MODEL_TITLE, f"Reading the model in {path.parent.name if path.is_file() else path.name} ...",
                  lambda: char_import.describe(path, folder), lambda r: described(r, folder), error=words, keep=False)

    def described(r, folder):
        problems = [str(r)] if isinstance(r, Exception) else r["problems"]
        if problems:
            messagebox.showwarning(MODEL_TITLE, "It can't be imported: " + " ".join(problems))
            return
        if donor is not None or r["donor"]:
            confirmed(r, folder, donor or r["donor"])
        else:
            stock = [n for _, n in getattr(app, "stock", []) if not n.lower().startswith(("unused", "mii"))]
            ask_donor(app, r["donors"] or stock, r["donors"][0] if r["donors"] else None,
                      lambda d: confirmed(r, folder, d))

    def confirmed(r, folder, d):
        ids, taken = app.taken()
        have = app.imported()
        taken = list(taken) + [c["name"] for c in have] + [n for _, n in getattr(app, "stock", [])]
        ids = set(ids) | {c["id"] for c in have}
        try:
            name = (getattr(app, "_replacing", None) or {}).get("name") or charpack.free_name(
                char_import.name_of(r["find"], d, f"{d} (custom)" if r.get("kind") in ("sluggie", "texture")
                                    else None)[0], taken)
        except charpack.PackError as e:
            messagebox.showwarning(MODEL_TITLE, str(e))
            return
        icons = ("with its own portraits" if len(r["icons"]) == 2 else
                 f"with its {r['icons'][0]} portrait (the other is {d}'s)" if r["icons"] else
                 f"with {d}'s portraits (add its own on its Model page)")
        voice = "its own voice" if r.get("voice") else f"{d}'s voice (it brings none of its own)"
        if confirm and not messagebox.askyesno(MODEL_TITLE, f"Adds '{name}', a new character with this model on "
                                               f"{d}'s skeleton, animations and moves, {icons} and {voice}. {d} "
                                               f"stays as it is.\n\nFiles: {', '.join(r['files'])}." +
                                               "".join(f"\nNote: {n}." for n in r.get("notes") or [])):
            return
        busy_work(app, MODEL_TITLE, f"Adding {name} ...",
                  lambda: char_import.add(path, folder, d, dest=patch.IMPORTED_DEST, taken_ids=ids,
                                          taken_names=taken, name=name,
                                          cid=(getattr(app, "_replacing", None) or {}).get("id")),
                  added, error=words)

    def added(r):
        if isinstance(r, Exception):
            messagebox.showwarning(MODEL_TITLE, f"It can't be imported: {r}")
            return
        app.refresh_imported(tick=[r["name"]])
        app.tick({"new-ids"}, why=r["name"])
        app.status.set(r["summary"] + " Ticked." + "".join(" " + w[:1].upper() + w[1:] + "." for w in r["warnings"]
                                                          if "no portraits of its own" not in w))
        app.last_model = r
        refresh(app)
        app.root.update_idletasks()
        open_character(app, r["name"])
    return app.with_game_folder(with_game, what="Importing a model reads your clean game (for its skeletons).")


def windows(app):
    return app.__dict__.setdefault("char_windows", {})


def open_character(app, name):
    """The character's window, or its open one brought forward."""
    w = windows(app).get(name)
    if w is not None and w.win.winfo_exists():
        if getattr(tk, "_headless", None) is None:  # (a test's windows stay withdrawn: headless.install)
            w.win.deiconify()
            w.win.lift()
        return w
    w = CharacterWindow(app, name)
    windows(app)[name] = w
    return w


def new_recolor(app):
    return CharacterWindow(app, None, new="recolor")


def refresh(app):
    """After a character goes in or out: the App's lists, and the beta page's "Not in the game yet" row."""
    app.refresh_soon()
    page = getattr(app, "beta", None)
    if page is not None:
        page.refresh_soon()


def entry(app, name):
    """(name, kind, definition or recipe, id, path, in-the-game var) of any character the window knows: stock, the
    new characters and recolors (in the game or not) and imported ones."""
    for p, d, _ in app.new_chars:
        if d["name"] == name:
            return name, "new", d, int(str(d["id"]), 0), p, app.cvars[p]
    for p, r in app.recipes:
        if r["name"] == name:
            return name, "recolor", r, int(str(r["id"]), 0) if "id" in r else None, p, app.rvars[p]
    for n, kind, d, cid in app.roster():
        if n == name:
            var = getattr(app, "ivars", {}).get(name) if kind == "imported" else None
            return name, kind, d, cid, None, var
    return None


class CharacterWindow:
    """One character: its stats, chemistry and names and its model, in one notebook, with "In the game" and Save. new:
    "recolor" for New recolor (the recolor editor first; the rest opens once it's made)."""

    def __init__(self, app, name, new=None):
        self.app, self.new = app, new
        self.editor = self.recolor = self.voice = None
        self.win = win = tk.Toplevel(self.app.root)
        win.transient(self.app.root)
        win.geometry("820x600")                         # inside Nick's 860 x 620
        top = ttk.Frame(win, padding=(8, 6, 8, 0))
        top.pack(fill="x")
        self.title = ttk.Label(top, font="SluggersHeading")
        self.title.pack(side="left")
        self.in_game = None
        bottom = widgets.save_bar(win, self.done, win.destroy, padding=(8, 4, 8, 6))   # git-f4's Save bar, snug
        self.problems = widgets.status(ttk.Label(bottom, text="", foreground=widgets.RED, wraplength=600,
                                                 justify="left"))
        self.problems.pack(side="left", fill="x", expand=True)
        self.bottom = bottom
        self.body = ttk.Frame(win)
        self.body.pack(fill="both", expand=True, padx=8)
        if new == "recolor":
            self.set_title("New recolor")
            self.app.recolor_game(self.show_new_recolor, what="The recolor editor starts from each character's own "
                                                                "textures in your game.")
        else:
            self.show(name)

    def set_title(self, text):
        style.title(self.win, text)
        self.title.configure(text=text)

    # --- an existing character: the character editor with its model as one more page

    def show(self, name):
        e = entry(self.app, name)
        if e is None:
            self.set_title(name)
            self.problems.configure(text=f"{name} isn't one of this game's characters.")
            return
        name, kind, d, cid, path, var = e
        self.kind, self.path = kind, path
        what = {"stock": "", "new": " (new character)", "recolor": " (recolor)", "imported": " (imported)"}[kind]
        self.set_title(name + what)
        if kind != "stock":                             # (ours: it says to untick it instead)
            self.delete_button = ttk.Button(self.bottom, text="Delete...", command=lambda: delete(self.app, name))
            self.delete_button.pack(side="left", padx=(0, 8), before=self.problems)
        if var is not None:                             # the beta's own and imported: in the game or not
            self.in_game = ttk.Checkbutton(self.title.master, text="In the game", variable=var,
                                           command=lambda: self.toggled(var, kind, d))
            self.in_game.pack(side="left", padx=12)
        roster_entry = (name, "new" if kind == "imported" else kind, d, cid)

        def build(game):
            import char_editor
            self.editor = char_editor.CharEditor(self.body, self.app, roster_entry, game.dol, embedded=True,
                                                 head=self.title.master)   # its intro and How to here (git-f4)
            page = ttk.Frame(self.editor.tabs, padding=6)
            self.editor.tabs.add(page, text="Model")
            self.model_page(page, game, kind, d, path)
            if kind != "stock":                     # (Nick: "How would people edit them??"): ours only
                import voice_page
                page = ttk.Frame(self.editor.tabs, padding=6)
                self.editor.tabs.add(page, text="Voice")
                self.voice = voice_page.VoicePage(page, self.app, name, kind, d, game.path)
            return self
        self.app.recolor_game(build, what="The character window shows each character as it is in your game.")

    def model_page(self, page, game, kind, d, path):
        if kind == "recolor":
            import gui
            import recolor_editor
            self.recolor = recolor_editor.RecolorEditor(page, game, gui.RECOLORS, path=path, show_save=False,
                                                        id_folders=[gui.ROOT / "characters", gui.ROOT / "recolors"],
                                                        active_names={n for n, *_ in self.app.roster()})
            self.recolor.pack(fill="both", expand=True)
            return
        if kind == "stock":
            text = "The game's own model. To change its colors, make a recolor of it (New recolor on the main page)."
        else:
            base = d.get("template", "a stock character")
            own = "its own model" if d.get("model_blocks") else f"{base}'s model"
            text = f"Built on {base}'s skeleton and animations, with {own}."
        fit.label(page, text).pack(fill="x")
        if kind in ("new", "imported"):             # (ours, the player's and imported: stock and recolors have theirs)
            self.wheel_row(page, game, d["name"])
        if kind == "imported":
            self.base_row(page, d)
            self.portraits(page, d)

    OWN_SQUARE = "A square of its own"

    def wheel_row(self, page, game, name):
        """Color wheel: a square of its own, or a stock character's color wheel (a player's imported Dry Bowser as
        one of Bowser's colors, as the full build's Dry Bowser is). Picking one moves the character on the Select
        grid at once (GridTab.place, what Move to does there), no questions; the note beside it says where it is."""
        g = getattr(self.app, "grid_tab", None)
        if g is None or not hasattr(g, "place"):
            return
        if g.game is None:                              # (the full patcher before its Select grid tab was opened)
            g.game = game
        row = ttk.Frame(page)
        row.pack(fill="x", pady=(8, 0))
        ttk.Label(row, text="Color wheel:").pack(side="left")
        host = g.wheel_of(name)
        self.wheel_var = tk.StringVar(value=f"{host}'s color wheel" if host else self.OWN_SQUARE)
        self.wheel_box = ttk.Combobox(row, textvariable=self.wheel_var, state="readonly", width=28,
                                      values=[self.OWN_SQUARE] + [f"{h}'s color wheel" for h in g.wheels()])
        self.wheel_box.pack(side="left", padx=6)
        widgets.tip(self.wheel_box, "Where it is on character select: a square of its own, or one more color on a "
                                    "character's color wheel (like Dry Bowser on Bowser's). The grid shows it.")
        self.wheel_note = widgets.status(ttk.Label(row, text="", foreground=widgets.GREY))
        self.wheel_note.pack(side="left", padx=6)

        def say():
            now = g.wheel_of(name)
            self.wheel_note.configure(text=f"On {now}'s color wheel." if now else "On a square of its own.")

        def picked(*_):
            pick = self.wheel_var.get()
            to = None if pick == self.OWN_SQUARE else pick[:-len("'s color wheel")]
            why = g.place(name, to)
            if why:
                now = g.wheel_of(name)
                self.wheel_var.set(f"{now}'s color wheel" if now else self.OWN_SQUARE)
                self.wheel_note.configure(text=why)
            else:
                say()
        say()
        self.wheel_box.bind("<<ComboboxSelected>>", picked)
        self.pick_wheel = lambda pick: (self.wheel_var.set(pick), picked())   # (tests: a pick as a click makes it)

    def base_row(self, page, d):
        """An added character's base (git-92 for Nick: "switch the base character it is on"): every stock
        character in one plain list, a one-line note beside it when the picked one isn't the same skeleton or a
        similar body (Nick: "make it a note if it's not a similar base"), and Switch, which rebuilds its model on
        the picked base (model_import.switch_character) in the loading window."""
        import model_import
        from sluggers_data import char_id
        c = next((c for c in self.app.imported() if c["name"] == d["name"]), None)
        if c is None or not d.get("model_blocks"):
            return
        row = ttk.Frame(page)
        row.pack(fill="x", pady=(8, 0))
        ttk.Label(row, text="Built on:").pack(side="left")
        names = [n for _, n in getattr(self.app, "stock", []) if not n.lower().startswith(("unused", "mii"))]
        self.base_var = tk.StringVar(value=d.get("template", ""))
        box = ttk.Combobox(row, textvariable=self.base_var, values=names, state="readonly", width=22)
        box.pack(side="left", padx=6)
        self.switch_button = ttk.Button(row, text="Switch", state="disabled",
                                        command=lambda: self.switch_base(c, self.base_var.get()))
        self.switch_button.pack(side="left")
        ttk.Button(row, text="Export .slgmodel...", command=lambda: self.export_file(c)).pack(side="right")
        self.base_note = widgets.status(ttk.Label(page, text="", foreground=widgets.GREY))
        self.base_note.pack(anchor="w")
        blender = ttk.Frame(page)          # Nick: the Blender loop without unzipping and zipping by hand
        blender.pack(fill="x", pady=(4, 0))
        ttk.Label(blender, text="Edit in Blender:").pack(side="left")
        ttk.Button(blender, text="Save model.glb...", command=lambda: self.save_glb(c)).pack(side="left", padx=6)
        ttk.Button(blender, text="Load edited model.glb...", command=lambda: self.load_glb(c)).pack(side="left")

        def picked(*_):
            new = self.base_var.get()
            same = new == d.get("template")
            self.switch_button.configure(state="disabled" if same else "normal")
            self.base_note.configure(text="")
            if same:
                return

            def with_game(folder):
                try:
                    kind = model_import.similar_base(char_id(d["template"]), char_id(new), folder)
                except Exception:                   # noqa: BLE001 (only the note: Switch still says why)
                    kind = "different"
                if self.base_var.get() == new:
                    self.base_note.configure(text=model_import.NOT_SIMILAR if kind == "different" else "")
            self.app.with_game_folder(with_game, quiet=True)
        self.base_var.trace_add("write", picked)

    def export_file(self, c, out=None, then=None):
        """Export .slgmodel... (Nick: "export, edit in Blender, re-import or share"): an added character as a
        character file (model_import.export_character), with the Voice page's clips; out= skips the save dialog."""
        import charpack
        import model_import
        import sluggie
        if out is None:
            out = filedialog.asksaveasfilename(title="Export a character file", defaultextension=".slgmodel",
                                               initialfile=f"{charpack.slug(c['name'])}.slgmodel",
                                               filetypes=[("Character file", "*.slgmodel")])
            if not out:
                return None
        clips = (getattr(self.app, "extra_characters", {}).get(c["name"]) or {}).get("voice_clips")

        def with_game(folder):
            def done(r):
                if isinstance(r, Exception):
                    self.problems.configure(text=f"It can't be exported: {r}")
                    return
                self.app.status.set(f"Wrote {Path(r).name}: open its model.glb in Blender, or share the file.")
                if then:
                    then(r)
            busy_work(self.app, "Export", f"Writing {Path(out).name} ...",
                      lambda: model_import.export_character(c["definition"], out, folder, voice_clips=clips), done,
                      error=lambda e: e if isinstance(e, sluggie.SluggieError) else sluggie.SluggieError(
                          f"{type(e).__name__}: {e}"))
        return self.app.with_game_folder(with_game, what="Exporting reads your clean game (the model is stored as "
                                                         "changes to it).")

    def save_glb(self, c, out=None):
        """Save model.glb... (Edit in Blender): the character's model as a glTF to open in Blender
        (model_import.character_glb); out= skips the save dialog."""
        import charpack
        import model_import
        import sluggie
        if out is None:
            out = filedialog.asksaveasfilename(title="Save model.glb for Blender", defaultextension=".glb",
                                               initialfile=f"{charpack.slug(c['name'])}.glb",
                                               filetypes=[("glTF model (Blender)", "*.glb")])
            if not out:
                return None

        def with_game(folder):
            def done(r):
                if isinstance(r, Exception):
                    self.problems.configure(text=f"It can't be saved: {r}")
                    return
                self.app.status.set(f"Saved {Path(out).name}: edit it in Blender, export it as .glb (the defaults are "
                                    f"fine), then Load edited model.glb... here.")
            busy_work(self.app, "Edit in Blender", f"Writing {Path(out).name} ...",
                      lambda: Path(out).write_bytes(model_import.character_glb(c["definition"], folder)) and out,
                      done, error=lambda e: e if isinstance(e, sluggie.SluggieError) else sluggie.SluggieError(
                          f"{type(e).__name__}: {e}"))
        return self.app.with_game_folder(with_game, what="Saving the model reads your clean game.")

    def load_glb(self, c, path=None, then=None):
        """Load edited model.glb... (Edit in Blender): the character's model rebuilt from the glTF Blender exported
        (model_import.load_glb: the same checks as an import), then its window shown anew; Export .slgmodel then
        carries the edit. path= skips the open dialog."""
        import model_import
        import sluggie
        if path is None:
            path = filedialog.askopenfilename(title="Load the edited model.glb",
                                             filetypes=[("glTF model (Blender)", "*.glb"), ("All files", "*.*")])
            if not path:
                return None

        def with_game(folder):
            def done(r):
                if isinstance(r, Exception):
                    self.problems.configure(text=f"The edited model can't be used: {r}")
                    return
                self.app.status.set(f"{c['name']} now has the model from {Path(path).name}." + "".join(
                    " " + n[:1].upper() + n[1:] + "." for n in r))
                refresh(self.app)
                self.win.destroy()
                w = open_character(self.app, c["name"])
                if then:
                    then(w, r)
            busy_work(self.app, "Edit in Blender", f"Building {c['name']} from {Path(path).name} ...",
                      lambda: model_import.load_glb(c["definition"], path, folder), done,
                      error=lambda e: e if isinstance(e, sluggie.SluggieError) else sluggie.SluggieError(
                          f"{type(e).__name__}: {e}"))
        return self.app.with_game_folder(with_game, what="Loading the model reads your clean game.")

    def switch_base(self, c, new, then=None):
        """Rebuild the character's model on base `new` (the loading window), then show it anew."""
        import model_import
        import sluggie

        def with_game(folder):
            def done(r):
                if isinstance(r, Exception):
                    self.problems.configure(text=f"It can't be built on {new}: {r}")
                    return
                self.app.status.set(f"{c['name']} is now built on {r['template']}." + "".join(
                    " " + n[:1].upper() + n[1:] + "." for n in r["notes"]))
                refresh(self.app)
                self.win.destroy()
                w = open_character(self.app, c["name"])
                if then:
                    then(w, r)
            busy_work(self.app, "Switch base", f"Building {c['name']} on {new} ...",
                      lambda: model_import.switch_character(c["definition"], new, folder), done,
                      error=lambda e: e if isinstance(e, sluggie.SluggieError) else sluggie.SluggieError(
                          f"{type(e).__name__}: {e}"))
        return self.app.with_game_folder(with_game, what="Switching the base reads your clean game.")

    def portraits(self, page, d):
        """An added character's select-screen portraits (git-92 for Nick: "What about the icons?"): the two it shows,
        a Side / Front picture... each (any picture, fitted to 48x51: sluggie.set_portrait), and one line saying whose
        they are."""
        from PIL import Image, ImageTk
        import sluggie
        c = next((c for c in self.app.imported() if c["name"] == d["name"]), None)
        if c is None:
            return
        box = ttk.LabelFrame(page, text="Portraits (select screen)", padding=6)
        box.pack(fill="x", pady=(8, 0))
        row = ttk.Frame(box)
        row.pack(fill="x")
        self.portrait_labels, self._portrait_images = {}, {}
        for view in ("side", "front"):
            cell = ttk.Frame(row)
            cell.pack(side="left", padx=(0, 12))
            lab = ttk.Label(cell)
            lab.pack()
            self.portrait_labels[view] = lab
            ttk.Button(cell, text=f"{view.title()} picture...",
                       command=lambda v=view: self.pick_portrait(c["definition"], v)).pack(pady=(2, 0))
        self.portrait_note = widgets.status(ttk.Label(box, text="", foreground=widgets.GREY))
        self.portrait_note.pack(anchor="w", pady=(4, 0))

        def show(game_folder=None):
            dd = json.loads(Path(c["definition"]).read_text(encoding="utf8"))
            own = dd.get("icon")
            for view, lab in self.portrait_labels.items():
                img = None
                if own:
                    try:
                        img = Image.open(Path(c["folder"]) / own[view]).convert("RGBA")
                    except OSError:
                        img = None
                if img is None and game_folder is not None:
                    from sluggers_data import char_id
                    img = sluggie.template_portrait(game_folder, char_id(dd["template"]), view)
                if img is not None:
                    self._portrait_images[view] = ImageTk.PhotoImage(img.resize((96, 102), Image.NEAREST))
                    lab.configure(image=self._portrait_images[view])
            self.portrait_note.configure(text="Its own portraits." if own else
                                         f"No portraits of its own: it shows {dd['template']}'s. Pick a side or front "
                                         f"picture (any size; fitted to 48 x 51).")
        self.show_portraits = show
        show()
        if not json.loads(Path(c["definition"]).read_text(encoding="utf8")).get("icon"):
            self.app.with_game_folder(lambda folder: show(folder), quiet=True)

    def pick_portrait(self, definition, view, path=None):
        """A side / front portrait from a picture (path= skips the file dialog), saved with the character."""
        from PIL import Image
        import sluggie
        if path is None:
            path = filedialog.askopenfilename(title=f"{view.title()} portrait", filetypes=[
                ("Pictures", "*.png *.jpg *.jpeg *.bmp *.gif"), ("All files", "*.*")])
            if not path:
                return None

        def with_game(folder):
            try:
                sluggie.set_portrait(definition, view, Image.open(path), folder)
            except (OSError, sluggie.SluggieError) as e:
                self.problems.configure(text=f"That picture can't be used: {e}")
                return None
            self.show_portraits(folder)
            refresh(self.app)
            return True
        return self.app.with_game_folder(with_game, what="A portrait reads your game for the other one.")


    def toggled(self, var, kind, d):
        if var.get():
            import gui
            self.app.tick(gui.RECOLOR_NEEDS if kind == "recolor" else {"new-ids"}, why=d["name"])
        refresh(self.app)

    # --- New recolor: the recolor editor first; once saved, the whole character

    def show_new_recolor(self, game):
        import gui
        import recolor_editor
        self.recolor = recolor_editor.RecolorEditor(self.body, game, gui.RECOLORS, show_save=False,
                                                    id_folders=[gui.ROOT / "characters", gui.ROOT / "recolors"],
                                                    extra=dict(PLAYER),
                                                    active_names={n for n, *_ in self.app.roster()})
        self.recolor.pack(fill="both", expand=True)
        fit.label(self.body, grey=True, text="Save saves the recolor and puts it in the game; its stats, chemistry "
                  "and names open here next.").pack(fill="x", pady=4)
        return self

    # --- Done

    def done(self):
        app = self.app
        if self.recolor is not None:
            blocking, warnings = self.recolor.problems()
            if blocking:
                self.problems.configure(text=" ".join(blocking))
                return
            path = self.recolor.save()
            if not path:                                # (the editor said why, or couldn't write)
                self.problems.configure(text=" ".join(self.recolor.problems()[0]) or "The recolor couldn't be saved.")
                return
            app.recipe_saved(path)
            if self.new == "recolor":
                self.win.destroy()
                open_character(self.app, json.loads(Path(path).read_text(encoding="utf8"))["name"])
                return
        if self.editor is not None and self.editor.problems():
            self.problems.configure(text=self.editor.problems())
            return
        refresh(app)
        self.win.destroy()


# --- Delete (Nick: a way to delete a new character or recolor the player made or imported; ours only leave out)

def shipped():
    """Repo-relative paths of the characters and recipes we ship: the download's assets.json, or in the repo the traced
    manifests. A file listed there is ours: it can be left out, never deleted."""
    import patch
    if patch.ASSETS.exists():
        return set(json.loads(patch.ASSETS.read_text(encoding="utf8")))
    out = set()
    for m in Path(__file__).resolve().parent.glob("manifest*.txt"):
        out |= {line.strip() for line in m.read_text(encoding="utf8").splitlines() if line and not line.startswith("#")}
    return out


def owned_by_player(app, name):
    """(True, kind, path, definition) when the player made or imported `name` (New recolor, New character before it
    went, a recipe of their own, an imported pack), (False, kind, path, definition) for ours or a stock character, None if unknown."""
    import gui
    e = entry(app, name)
    if e is None:
        return None
    name, kind, d, cid, path, var = e
    if kind == "stock":
        return False, kind, path, d
    if kind == "imported":
        return True, kind, path, d
    if (d or {}).get("made_by") == "player":
        return True, kind, path, d
    try:
        rel = Path(path).resolve().relative_to(Path(gui.ROOT).resolve()).as_posix()
    except ValueError:
        return True, kind, path, d                  # outside the patcher's folder: the player's
    return rel not in shipped(), kind, path, d


def delete(app, name):
    """Delete a character the player made or imported: its files, its settings (and chemistry pairs naming it), its
    place on the grid, its window. Ours: a message to untick it instead. Returns True when it was deleted."""
    from tkinter import messagebox
    own = owned_by_player(app, name)
    if own is None:
        return False
    mine, kind, path, d = own
    if not mine and kind == "stock":
        messagebox.showinfo("Delete", f"{name} is a stock game character, so it can't be deleted from the patcher.")
        return False
    warning = (f"Deletes {name} and its files. This can't be undone." if mine else
               f"Deletes the patcher's built-in {name} character from this copy of the tool. "
               f"You would need to reinstall/replace the tool files to get it back. Continue?")
    if not messagebox.askyesno(f"Delete {name}", warning):
        return False
    if kind == "imported":
        import charpack
        import patch
        c = next((c for c in app.imported() if c["name"] == name), None)
        if c is not None:
            charpack.remove(c["id"], patch.IMPORTED_DEST)
    else:
        Path(path).unlink(missing_ok=True)
        store = app.rvars if kind == "recolor" else app.cvars
        var = store.pop(path, None)
        box = app.recolor_box if kind == "recolor" else getattr(app, "character_box", None)
        for row in (box.winfo_children() if box is not None else []):   # its row on New characters & recolors
            if var is not None and any(str(c.cget("variable")) == str(var) for c in row.winfo_children()
                                       if c.winfo_class() == "TCheckbutton"):
                row.destroy()
        if kind == "recolor":
            app.recipes[:] = [(p, r) for p, r in app.recipes if p != path]
            getattr(app, "recolor_rows", {}).pop(path, None)
        else:
            app.new_chars[:] = [it for it in app.new_chars if it[0] != path]
    forget(app, name)
    import shutil
    import patch
    import voice_clips                              # its own voice clips (the Voice page), in the player's folder
    shutil.rmtree(voice_clips.folder(name, patch.IMPORTED_DEST), ignore_errors=True)
    w = windows(app).pop(name, None)
    if w is not None and w.win.winfo_exists():
        w.win.destroy()
    if kind == "imported":
        app.refresh_imported()
    refresh(app)
    app.status.set(f"Deleted {name}.")
    return True


def forget(app, name):
    """A deleted character out of the window's choices: its settings, chemistry pairs naming it, the grid order."""
    low = name.lower()
    for store in (getattr(app, "settings", {}), getattr(app, "extra_characters", {})):
        for k in [k for k in store if str(k).lower() == low]:
            store.pop(k)
        for opts in store.values():
            chem = opts.get("chemistry") if isinstance(opts, dict) else None
            if isinstance(chem, dict):
                for k in [k for k in chem if str(k).lower() == low]:
                    chem.pop(k)
    g = getattr(app, "grid_tab", None)
    if g is not None and g.order:
        g.order = [sq for sq in ([m for m in sq if str(m).lower() != low] for sq in g.order) if sq]
        if g.game is not None:
            g.redraw()


# --- right-click: Open / Delete, on the grid and the lists

def menu(app, name, event=None):
    """A small menu for a character: Open..., Delete... (Delete greyed out for ours and stock)."""
    own = owned_by_player(app, name)
    m = tk.Menu(app.root, tearoff=0)
    m.add_command(label=f"Open {name}...", command=lambda: open_character(app, name))
    m.add_command(label="Delete...", command=lambda: delete(app, name),
                  state="normal" if own and own[0] else "disabled")
    if event is not None:
        m.tk_popup(event.x_root, event.y_root)
    return m


def install(app):
    """Right-click menus on the Select grid and the Characters tab's list (and on each New characters & recolors row as
    it's made: bind_row). Called once the App has built them."""
    g = getattr(app, "grid_tab", None)
    if g is not None and hasattr(g, "canvas"):
        def on_grid(e):
            i = g.square_at(e.x, e.y)
            order = g.order or (g.default() if g.game is not None else None)
            if i is not None and order and i < len(order) and order[i]:
                menu(app, order[i][0], e)
        g.canvas.bind("<Button-3>", on_grid, add="+")
    lb = getattr(app, "char_list", None)
    if lb is not None:
        def on_list(e):
            i = lb.nearest(e.y)
            if 0 <= i < len(getattr(app, "list_names", [])):
                menu(app, app.list_names[i], e)
        lb.bind("<Button-3>", on_list, add="+")


def bind_row(app, widget, path, recolor):
    """Right-click on a New characters & recolors row: the menu for that character (by its name as it is now)."""
    def name():
        if recolor:
            return next((r["name"] for p, r in app.recipes if p == path), None)
        return next((d["name"] for p, d, _ in app.new_chars if p == path), None)

    def on_row(e):
        n = name()
        if n:
            menu(app, n, e)
    widget.bind("<Button-3>", on_row, add="+")
