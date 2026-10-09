"""Modder files: names for the game's code, for modders (scripts/modder_files.py). From the pinned bar's
"Modder files..." (gui.App): a Dolphin symbol map and Ghidra names, made from the game picked at the top of the
window. Pick where the "Sluggers modder files" folder goes (default: next to the game), then Make files.
"""
import threading
import tkinter as tk
import style
from pathlib import Path
from tkinter import filedialog, ttk

import fit
import widgets

TITLE = "Modder files"
BUTTON = "Modder files..."
INTRO = ("For modders: names for the game's code, made from your game. A Dolphin symbol map (the debugger shows "
         "Select::CExhiMainTask::Update instead of 802cec18) and the same names for Ghidra. The folder's README "
         "says how to use them. Your game isn't changed.")
TIP = "Names for the game's code, for modders who use Dolphin's debugger or Ghidra. You don't need it to play."
WHAT = [
    "This is for people who make mods by reading the game's code. If you only want to play, you can skip it.",
    "The game keeps the names of its C++ classes. This uses them to name about 7,600 of the game's functions, so "
    "tools show Select::CExhiMainTask::Update (exhibition mode's setup screens) instead of the address 802cec18.",
    "RMBE01.map is for Dolphin's debugger. names.tsv and the ghidra folder are for Ghidra. The folder's README.txt "
    "says how to load them.",
    "Your game isn't changed, and nothing of the game is copied into the folder: only names and addresses.",
]


class Window:
    def __init__(self, app):
        self.app = app
        self.win = win = tk.Toplevel(app.root)
        style.title(win, TITLE)
        win.transient(app.root)
        win.geometry("640x300")
        self.bar = bar = widgets.save_bar(win, self.make, win.destroy, text="Make files")
        self.problem = widgets.status(ttk.Label(bar, text="", wraplength=440, justify="left"))
        self.problem.pack(side="left", fill="x", expand=True)
        body = ttk.Frame(win, padding=(12, 10, 12, 0))
        body.pack(fill="both", expand=True)
        fit.label(body, INTRO, grey=True).pack(fill="x", pady=(0, 4))
        widgets.HowTo(body, WHAT, key="modder-files", title="What is this?").pack(fill="x", pady=(0, 6))
        rows = ttk.Frame(body)
        rows.pack(fill="x")
        game = app.game.get().strip() if hasattr(app, "game") else ""
        self.game = tk.StringVar(value=game)
        self.dest = tk.StringVar(value=str(Path(game).parent) if game else "")
        for r, (label, var, pick) in enumerate((("Your game (.iso or folder):", self.game, self.pick_game),
                                                ("Put the folder in:", self.dest, self.pick_dest))):
            ttk.Label(rows, text=label).grid(row=r, column=0, sticky="w")
            ttk.Entry(rows, textvariable=var).grid(row=r, column=1, sticky="ew", padx=4, pady=1)
            ttk.Button(rows, text="Choose...", command=pick).grid(row=r, column=2)
        rows.columnconfigure(1, weight=1)

    def pick_game(self):
        p = filedialog.askopenfilename(title="Your Mario Super Sluggers (USA) .iso",
                                       filetypes=[("Game", "*.iso"), ("All", "*")])
        if p:
            self.game.set(p)
            if not self.dest.get().strip():
                self.dest.set(str(Path(p).parent))

    def pick_dest(self):
        p = filedialog.askdirectory(title="Where to put the Sluggers modder files folder")
        if p:
            self.dest.set(p)

    def say(self, text, ok=False):
        self.problem.configure(text=text, foreground=widgets.GREY if ok else widgets.RED)

    def make(self):
        game, dest = self.game.get().strip(), self.dest.get().strip()
        if not game or not Path(game).exists():
            return self.say("Pick your game: the clean USA .iso, or its extracted folder.")
        if not dest:
            return self.say("Pick where the folder goes.")
        self.bar.save.configure(state="disabled")
        self.say("Making the files (an .iso is read first, which takes a moment the first time)...", ok=True)
        result = {}

        def work():
            import modder_files
            try:
                result["out"] = modder_files.write(game, dest)
            except SystemExit as e:             # patch.game_folder's refusals (not the clean USA game, ...)
                result["error"] = str(e)
            except Exception as e:
                result["error"] = f"Couldn't make them: {e}"

        t = threading.Thread(target=work, daemon=True)
        t.start()

        def poll():
            if t.is_alive():
                return self.win.after(200, poll)
            if not self.win.winfo_exists():
                return
            self.bar.save.configure(state="normal")
            if "error" in result:
                return self.say(result["error"])
            self.app.status.set(f"Modder files written to {result['out']} (see its README.txt).")
            self.win.destroy()

        poll()


def open_window(app):
    """The window (one at a time: a second click brings the open one up)."""
    w = getattr(app, "modder_window", None)
    if w is not None and w.win.winfo_exists():
        w.win.lift()
        return w
    app.modder_window = Window(app)
    return app.modder_window
