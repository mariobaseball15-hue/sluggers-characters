"""Fix my Gecko codes: the player's Dolphin codes for this patcher's game (gecko_fix.py). A player: "some gecko codes
still work, others don't". The patched game keeps some tables and its run-time memory somewhere else, so codes that
write there miss; codes that hook what the patcher changed fight with it.

A small window from the pinned bar's "Fix my Gecko codes..." (gui.App, the full patcher and the Characters Beta alike):
  - Your Dolphin codes: RMBE01.ini (Dolphin's GameSettings; the first of gecko_fix.dolphin_inis, or Choose...: a
    portable Dolphin keeps it in its own User folder);
  - Your patched game: the ISO (its relocations.json, which every patch writes into "<name> (patch details)" beside
    it, or an older build's <name>.relocations.json; the last ISO this
    window's patcher wrote, or the newest one beside it);
  - the report, per code (fixed / works as it is / turned off and why);
  - Save at the bottom right: the codes file is copied to RMBE01.ini.before-fix first (a numbered name when that
    exists), then the fixed one is written. Nothing is written before Save.
"""
import tkinter as tk
import style
from pathlib import Path
from tkinter import filedialog, ttk
from tkinter.scrolledtext import ScrolledText

import fit
import gecko_fix
import widgets

TITLE = "Fix my Gecko codes"
BUTTON = "Fix my Gecko codes..."
INTRO = ("To make room for new characters, the patched game keeps some of the game's tables and memory somewhere "
         "else, so a Gecko code that writes there does nothing. This points your codes at the new places, and turns "
         "off the ones that would fight with what the patcher already changes. Nothing is written until you click "
         "Save, and your codes file is backed up first.")


def backup_path(ini):
    """RMBE01.ini.before-fix, or .before-fix-2, -3, ... (never over an earlier backup)."""
    ini = Path(ini)
    p, n = ini.with_name(ini.name + ".before-fix"), 2
    while p.exists():
        p, n = ini.with_name(f"{ini.name}.before-fix-{n}"), n + 1
    return p


def map_file(path):
    """The relocations file for what the player picked: the file itself, or an ISO's."""
    if not path:
        return None
    p = Path(path)
    if p.name.endswith("relocations.json"):         # <name>.relocations.json, or a details folder's relocations.json
        return p if p.exists() else None
    return gecko_fix.relocation_file(p)


class Window:
    def __init__(self, app):
        self.app = app
        self.codes = self.text = None
        self.win = win = tk.Toplevel(app.root)
        style.title(win, TITLE)
        win.transient(app.root)
        win.geometry("760x560")
        self.bar = bar = widgets.save_bar(win, self.save, win.destroy)
        bar.save.configure(state="disabled")
        self.problem = widgets.status(ttk.Label(bar, text="", wraplength=520, justify="left"))
        self.problem.pack(side="left", fill="x", expand=True)
        body = ttk.Frame(win, padding=(12, 10, 12, 0))
        body.pack(fill="both", expand=True)
        fit.label(body, INTRO, grey=True).pack(fill="x", pady=(0, 6))
        rows = ttk.Frame(body)
        rows.pack(fill="x")
        found = gecko_fix.dolphin_inis()
        self.ini = tk.StringVar(value=str(found[0]) if found else "")
        iso = app.iso.get().strip() if hasattr(app, "iso") else ""
        own = map_file(iso)
        self.game = tk.StringVar(value=str(own) if own else iso)
        for r, (label, var, pick) in enumerate((("Your Dolphin codes (RMBE01.ini):", self.ini, self.pick_ini),
                                                ("Your patched game (the ISO):", self.game, self.pick_game))):
            ttk.Label(rows, text=label).grid(row=r, column=0, sticky="w")
            ttk.Entry(rows, textvariable=var).grid(row=r, column=1, sticky="ew", padx=4, pady=1)
            ttk.Button(rows, text="Choose...", command=pick).grid(row=r, column=2)
        rows.columnconfigure(1, weight=1)
        check = ttk.Frame(body)
        check.pack(fill="x", pady=(6, 4))
        ttk.Button(check, text="Check my codes", command=self.check).pack(side="left")
        self.box = ScrolledText(body, wrap="word", font="SluggersSmall", height=18)
        self.box.pack(fill="both", expand=True)
        self.show("Pick your codes file and your patched game, then Check my codes.")
        if self.ini.get() and map_file(self.game.get()):
            self.check()

    def show(self, text):
        self.box.configure(state="normal")
        self.box.delete("1.0", "end")
        self.box.insert("1.0", text)
        self.box.configure(state="disabled")

    def pick_ini(self):
        p = filedialog.askopenfilename(title="Your Dolphin codes (GameSettings/RMBE01.ini)",
                                       filetypes=[("Dolphin game settings", "*.ini"), ("All", "*")])
        if p:
            self.ini.set(p)
            self.check()

    def pick_game(self):
        p = filedialog.askopenfilename(title="Your patched game", filetypes=[
            ("Patched game", "*.iso relocations.json *.relocations.json"), ("All", "*")])
        if p:
            self.game.set(p)
            self.check()

    def where(self):
        """Where the player turns on what the patcher has built in (CPU vs CPU)."""
        import gui
        return "Game options" if gui.SINGLE else "on the Features tab"

    def check(self):
        """Read both files, fix the codes (nothing written), show the report; Save only when something changes."""
        self.codes = self.text = None
        self.bar.save.configure(state="disabled")
        ini, game = self.ini.get().strip(), self.game.get().strip()
        if not ini or not Path(ini).exists():
            return self.say("Pick your Dolphin codes file (RMBE01.ini in Dolphin's GameSettings folder).")
        found = map_file(game)
        if found is None:
            return self.say("Pick the patched game (the ISO this patcher made). The \"(patch details)\" folder next to "
                            "it must have relocations.json: games patched before this version don't have one, so "
                            "patch again.")
        try:
            text = Path(ini).read_text(encoding="utf-8-sig", errors="replace")
            m = gecko_fix.Map.load(found)
        except (OSError, ValueError) as e:
            return self.say(f"Couldn't read it: {e}")
        codes = gecko_fix.fix(text, m, offered=set(getattr(self.app, "reg", {})) or None, where=self.where())
        if not codes:
            return self.say("There are no Gecko codes in that file.")
        self.codes, self.text = codes, text
        changes = [c for c in codes if c.status in ("fixed", "unsure") or c.status in gecko_fix.OFF]
        self.show(gecko_fix.report(codes))
        if changes:
            self.bar.save.configure(state="normal")
            self.say(f"{len(changes)} of {len(codes)} codes change. Save writes them (your file is backed up first).",
                     ok=True)
        else:
            self.say("Nothing to change: your codes work with this game as they are.", ok=True)

    def say(self, text, ok=False):
        self.problem.configure(text=text, foreground=widgets.GREY if ok else widgets.RED)

    def save(self):
        if not self.codes:
            return self.check()
        ini = Path(self.ini.get().strip())
        try:
            now = ini.read_text(encoding="utf-8-sig", errors="replace")
            if now != self.text:                        # (Dolphin changed it meanwhile: check again first)
                self.check()
                return self.say("Your codes file changed since the check: check the new report, then Save.")
            back = backup_path(ini)
            back.write_bytes(ini.read_bytes())
            ini.write_text(gecko_fix.fixed_text(self.text, self.codes), encoding="utf8")
        except OSError as e:
            return self.say(f"Couldn't save: {e}")
        self.app.status.set(f"Gecko codes fixed in {ini.name} (the old one is {back.name}). Restart the game in "
                            "Dolphin to use them.")
        self.win.destroy()


def open_window(app):
    """The window (one at a time: a second click brings the open one up)."""
    w = getattr(app, "gecko_window", None)
    if w is not None and w.win.winfo_exists():
        w.win.lift()
        return w
    app.gecko_window = Window(app)
    return app.gecko_window
