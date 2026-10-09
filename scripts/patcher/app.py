"""The player's patcher: Sluggers Patcher.exe runs this (docs/patcher.md, "Download").

  Sluggers Patcher.exe                       asks for the game, a profile and where to write the ISO
  Sluggers Patcher.exe --game ... [...]      the same arguments as patch.py
  Sluggers Patcher.exe --console             the questions below, even when the GUI (gui.py) is there
  Sluggers Patcher.exe --check               builds the whole window off-screen and exits (the release gate)

The first run asks three things:
  1. the clean Mario Super Sluggers (USA, RMBE01): an .iso or an extracted folder (drag it onto the window)
  2. a profile: one of scripts/patcher/profiles/*.json (its "about" line is shown), or a path to your own
  3. where to write the patched ISO (default: next to the game)
"""
import json, os, sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
sys.path.insert(0, str(HERE.parent))
import patch

PROFILES = HERE / "profiles"


def ask(prompt, default=None):
    answer = input(prompt + (f" [{default}]" if default else "") + ": ").strip().strip('"').strip("'")
    return answer or default


def pick_game():
    while True:
        p = ask("\n1. Drag your Mario Super Sluggers (USA) .iso or extracted game folder here, then press Enter")
        if p and Path(p).exists():
            return Path(p)
        print("   not found, try again")


def pick_profile():
    profiles = sorted(PROFILES.glob("*.json"))
    print("\n2. Pick what goes in:")
    for n, p in enumerate(profiles, 1):
        about = json.loads(p.read_text(encoding="utf8")).get("about", "")
        print(f"   {n}. {p.stem:14s} {about}")
    print("   or type the path to your own profile (.json)")
    while True:
        a = ask("   number or path", "1")
        if a.isdigit() and 1 <= int(a) <= len(profiles):
            return profiles[int(a) - 1]
        if Path(a).is_file():
            return Path(a)
        print("   not a number above or a file, try again")


def pick_iso(game, profile):
    default = game.parent / f"Sluggers ({profile.stem}).iso"
    n = 2
    while default.exists():
        default = default.with_name(f"Sluggers ({profile.stem}) {n}.iso")
        n += 1
    return Path(ask("\n3. Write the patched ISO to", str(default)))


def interactive():
    print("Mario Super Sluggers patcher\n"
          "It patches your own copy of the game; nothing of the game ships with it.")
    game, profile = pick_game(), pick_profile()
    iso = pick_iso(game, profile)
    print()
    patch.run(game, profile, iso=iso)
    print(f"\nDone. Play {iso} in Dolphin (or on your Wii).")


def check_window():
    """Build the whole window withdrawn and off-screen (never on the desktop: Nick's rule), with the everything profile
    loaded and every tab and page of every notebook selected (pages that build when shown), then destroy it. An
    exception, a Tk callback error or an error dialog fails it. Returns the exit code (0 ok)."""
    import importlib, traceback
    import tkinter as tk
    from tkinter import ttk, messagebox

    class OffScreen(tk.Toplevel):             # every window the pages make, like the window tests (git-b6)
        def __init__(self, *a, **k):
            super().__init__(*a, **k)
            self.withdraw()
            self.geometry("+-10000+-10000")
            self.attributes("-alpha", 0.0)
    tk.Toplevel = OffScreen
    errors, dialogs = [], []
    messagebox.showerror = lambda title, msg, **k: errors.append(f"error dialog: {title}: {msg}")
    for name in ("showinfo", "showwarning"):
        setattr(messagebox, name, lambda title, msg, name=name, **k: dialogs.append(f"{name}: {msg}"))
    messagebox.askyesno = lambda *a, **k: False
    messagebox.askyesnocancel = lambda *a, **k: None
    root = None
    try:
        sweep = not os.environ.get("SLUGGERS_NO_SWEEP")   # (package.py's module trace: only what the window imports)
        for m in sorted(p.stem for p in HERE.glob("*.py") if sweep and p.stem not in ("app", "launcher", "package")):
            importlib.import_module(m)
        import charpack  # noqa: F401            (Import character...)
        root = tk.Tk()
        root.withdraw()
        root.geometry("+-10000+-10000")
        root.attributes("-alpha", 0.0)
        root.report_callback_exception = lambda *exc: errors.append("".join(traceback.format_exception(*exc)))
        import gui
        app = gui.App(root)
        import style                           # the look ships with it (style.py): the theme's files loaded
        if style.THEME != style.THEME_NAME:
            errors.append(f"the window's theme didn't load: {style.THEME_FILE} (Tk's {style.THEME} instead)")
        if not getattr(root, "_icon_set", False):   # and the app icon (style.set_icon)
            errors.append(f"the window's icon didn't load: {style.ICON_ICO}")
        app.load(str(HERE / gui.EDITION["profile"] if gui.EDITION else HERE / "profiles" / "everything.json"))
        root.update()
        tabs, seen = 0, set()

        def walk(w):
            nonlocal tabs
            for child in w.winfo_children():
                if isinstance(child, ttk.Notebook) and str(child) not in seen:
                    seen.add(str(child))
                    for t in child.tabs():
                        child.select(t)
                        root.update()
                        tabs += 1
                walk(child)
        walk(root)
        walk(root)                             # notebooks a selected page built
        if gui.SINGLE:                         # the one-page beta: its Credits dialog and a character window
            app.beta.show_credits().destroy()
            if getattr(app.beta, "items_button", None) is not None:   # Items... (items_window.py)
                w = app.beta.items()
                root.update()
                tabs += len(w.sections)
                w.win.destroy()
            g = app.game.get().strip()
            if g and Path(g).is_dir():         # (with no game the window would first ask for one)
                w = app.beta.open_character(app.stock[0][1])
                root.update()
                tabs += len(w.editor.tabs.tabs()) if w.editor else 0
                w.win.destroy()
    except Exception:
        errors.append(traceback.format_exc())
    finally:
        if root is not None:
            try:
                root.destroy()
            except tk.TclError:
                pass
    if errors:
        print("check FAILED:\n" + "\n".join(errors))
        return 1
    import style
    print(f"check ok: the window built ({style.THEME}, app icon) with the {'edition' if gui.EDITION else 'everything'} profile, {len(seen)} notebooks, {tabs} tabs and pages "
          f"shown off-screen" + (f"; {len(dialogs)} info dialogs" if dialogs else ""))
    return 0


def check_sluggie(path, game):
    """The release gate's .sluggie smoke test (git-92: 3.5's Add a model from Sluggies failed on a module the trim
    left out): check and add the file (into a temporary folder) with this download's own code. 0 or 1."""
    import tempfile, traceback
    try:
        import sluggie
        r = sluggie.describe(path, game)
        added = sluggie.add_character(path, game, dest=Path(tempfile.mkdtemp()))
        print(f"check-sluggie ok: {added['name']} from {r['template']}")
        return 0
    except Exception:
        traceback.print_exc()
        return 1


def check_model(path, game):
    """The release gate's "Import a model..." smoke test: describe and add the model (into a temporary folder) with this
    download's own code. 0 or 1."""
    import tempfile, traceback
    try:
        import model_import
        r = model_import.describe(path, game)
        added = model_import.add_model(path, game, dest=Path(tempfile.mkdtemp()))
        print(f"check-model ok: {added.get('name')} ({r.get('template', r.get('donor', '?'))})")
        return 0
    except Exception:
        traceback.print_exc()
        return 1


def main():
    if sys.argv[1:2] == ["--check-model"]:          # the release gate: a model folder imports with this download's code
        sys.exit(check_model(sys.argv[2], sys.argv[3]))
    if sys.argv[1:] == ["--check"]:                 # the release gate: the whole window builds, never shown
        sys.exit(check_window())
    if sys.argv[1:2] == ["--check-sluggie"]:        # the release gate: a .sluggie imports with this download's code
        sys.exit(check_sluggie(sys.argv[2], sys.argv[3]))
    console = sys.argv[1:] == ["--console"]         # the questions in the console, even with the GUI there
    if len(sys.argv) > 1 and not console:
        return patch.main()
    if not console and (HERE / "gui.py").exists():   # the checkbox GUI (git-f4), when it's there
        import gui
        return gui.main()
    try:
        interactive()
    except SystemExit as e:
        if e.code not in (None, 0):
            print(f"\nStopped: {e.code}")
    except KeyboardInterrupt:
        print("\nStopped.")
    except Exception as e:                  # keep the window open so the player can read (and send) it
        import traceback
        traceback.print_exc()
        print(f"\nSomething went wrong: {e}")
    input("\nPress Enter to close.")


if __name__ == "__main__":
    main()
