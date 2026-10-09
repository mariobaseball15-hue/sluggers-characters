"""The patcher's look, in one place (Nick: "make the patcher's UI look professional"): the Sun Valley light theme,
one font scale, the named styles every window uses, the app icon and the window titles.

  apply(root)          once per Tk root, before any widget (gui.App does it): the theme, the fonts, the styles, the
                       icon (every Toplevel inherits it)
  title(win, name)     "<name> - <app>" on a window that isn't the main one ("Game options - Sluggers Characters Beta")
  APP_NAME             the edition's name ("Sluggers Characters Beta"), or "Sluggers Patcher" (the full patcher)

The theme is Sun Valley (sv-ttk 2.6.1 by rdbende, MIT: theme/sun-valley/ holds its Tcl and sprites unchanged, and its
LICENSE, which the download ships). Without it (the files missing) the window falls back to Tk's own theme and says so
in THEME (app.py --check fails on that: the release gate).

The fonts (Segoe UI, Windows' own UI size): body 9, small 8 (a field's range and stock), section titles semibold 9,
headings semibold 12, the log Consolas 9. Styles: Heading.TLabel, Section.TLabel, Hint.TLabel (grey), Problem.TLabel (red), Warning.TLabel (amber),
Link.TLabel (the accent blue), Accent.TButton (Patch, Save), Big.TButton (the beta's add buttons), Slim.TButton (the
beta's small option buttons), Small.TButton (a field's Stock), Icon.Toolbutton (an "i"), Compact.TEntry.
The colours that carry meaning (widgets.GREY / RED / AMBER / GREEN / LINK) are picked to read on the theme's #fafafa.
"""
import sys
import tkinter as tk
from tkinter import ttk
from pathlib import Path

HERE = Path(__file__).resolve().parent
THEME_FILE = HERE / "theme" / "sun-valley" / "sv.tcl"
ICON_PNG = HERE / "app_icon.png"
ICON_ICO = HERE / "app_icon.ico"
THEME_NAME = "sun-valley-light"


def _app_name():
    try:
        import edition
        return (edition.load() or {}).get("name") or "Sluggers Patcher"
    except Exception:
        return "Sluggers Patcher"


APP_NAME = _app_name()
DASH = "—"                    # the em dash between a window's name and the app's

FAMILY, SEMIBOLD, MONO = "Segoe UI", "Segoe UI Semibold", "Consolas"
BODY, SMALL, HEADING = 9, 8, 12
PAD = 8                            # a window's edge and the gap between sections
GAP = 4                            # between a label and its field, and between buttons in a row

# the colours that carry meaning, readable on the theme's #fafafa (contrast 4.5:1 or more)
GREY = "#5c5c5c"                   # hints, ranges, "stock"
RED = "#c42b1c"                    # a problem that stops Save / Patch
AMBER = "#9d5d00"                  # a warning that still lets it through
GREEN = "#0f7b0f"                  # done
LINK = "#005fb8"                   # a link (the theme's accent)

THEME = None                       # the theme in use after apply(): THEME_NAME, or Tk's own when it couldn't load


def fonts():
    """The named fonts (after apply): {"body", "small", "section", "heading", "mono"} -> font name."""
    return {"body": "TkDefaultFont", "small": "SluggersSmall", "section": "SluggersSection",
            "heading": "SluggersHeading", "mono": "SluggersMono"}


def _font(root, name, family, size, weight="normal"):
    try:
        root.tk.call("font", "create", name, "-family", family, "-size", size, "-weight", weight)
    except tk.TclError:           # (made already in this interpreter)
        root.tk.call("font", "configure", name, "-family", family, "-size", size, "-weight", weight)


def apply(root):
    """The theme, fonts, styles and icon on root (once). Returns the theme's name."""
    global THEME
    if getattr(root, "_sluggers_style", None):
        return root._sluggers_style
    style = ttk.Style(root)
    theme = style.theme_use()
    if THEME_FILE.is_file():
        try:
            root.tk.call("source", str(THEME_FILE))
            style.theme_use(THEME_NAME)
            theme = THEME_NAME
        except tk.TclError as e:
            print(f"note: the window's theme didn't load ({e}); Tk's own is used")
    THEME = theme
    if theme == THEME_NAME:          # the spinboxes' arrows narrower (Sun Valley's are 34 px each: a stat field's
        try:                         # column in the character editor wouldn't fit two to a page)
            for arrow in ("up", "down"):
                img = root.tk.eval(f"set ttk::theme::sv_light::I({arrow})")
                root.tk.call("ttk::style", "element", "create", f"Narrow.{arrow}arrow", "image", img, "-width", 16,
                             "-height", 16, "-sticky", "")
            # the notebook's tabs narrower (16 px a side each: the full patcher's 11 tabs clipped at 860 px)
            root.tk.eval("ttk::style element create Narrow.tab image [list $ttk::theme::sv_light::I(tab-rest) "
                         "selected $ttk::theme::sv_light::I(tab-selected) active $ttk::theme::sv_light::I(tab-hover)] "
                         "-border 13 -padding {7 10 7 4} -height 28")
            root.tk.eval("ttk::style layout TNotebook.Tab {Narrow.tab -sticky nswe -children {Notebook.padding "
                         "-side top -sticky nswe -children {Notebook.focus -side top -sticky nswe -children "
                         "{Notebook.label -side top -sticky {}}}}}")
            root.tk.eval("ttk::style layout TSpinbox {Spinbox.field -side top -sticky we -children {"
                         "Narrow.downarrow -side right -sticky ns Narrow.uparrow -side right -sticky ns "
                         "Spinbox.padding -sticky nswe -children {Spinbox.textarea -sticky nsew}}}")
        except tk.TclError:
            pass
    # one font scale: Sun Valley's own names (its entries, headings, labelled frames use them) and Tk's
    for name, family, size, weight in (("SunValleyCaptionFont", FAMILY, SMALL, "normal"),
                                       ("SunValleyBodyFont", FAMILY, BODY, "normal"),
                                       ("SunValleyBodyStrongFont", SEMIBOLD, BODY, "normal"),
                                       ("SunValleyBodyLargeFont", FAMILY, HEADING, "normal"),
                                       ("SunValleySubtitleFont", SEMIBOLD, HEADING + 2, "normal"),
                                       ("SunValleyTitleFont", SEMIBOLD, HEADING + 6, "normal"),
                                       ("TkDefaultFont", FAMILY, BODY, "normal"),
                                       ("TkTextFont", FAMILY, BODY, "normal"),
                                       ("TkMenuFont", FAMILY, BODY, "normal"),
                                       ("TkHeadingFont", SEMIBOLD, BODY, "normal"),
                                       ("TkCaptionFont", SEMIBOLD, BODY, "normal"),
                                       ("TkTooltipFont", FAMILY, SMALL, "normal"),
                                       ("SluggersSmall", FAMILY, SMALL, "normal"),
                                       ("SluggersSection", SEMIBOLD, BODY, "normal"),
                                       ("SluggersHeading", SEMIBOLD, HEADING, "normal"),
                                       ("SluggersMono", MONO, BODY, "normal")):
        _font(root, name, family, size, weight)
    style.configure(".", font="TkDefaultFont")
    style.configure("TLabelframe.Label", font="SluggersSection")
    style.configure("Heading.TLabel", font="SluggersHeading")
    style.configure("Section.TLabel", font="SluggersSection")
    style.configure("Hint.TLabel", foreground=GREY)
    style.configure("Small.TLabel", foreground=GREY, font="SluggersSmall")
    style.configure("Problem.TLabel", foreground=RED)
    style.configure("Warning.TLabel", foreground=AMBER)
    style.configure("Link.TLabel", foreground=LINK)
    style.configure("Big.TButton", font="SluggersSection", padding=(6, 2), justify="center")
    style.configure("Slim.TButton", padding=(8, 0, 8, 1))
    style.configure("Icon.Toolbutton", padding=(1, 0, 1, 1))                   # a field's "i"
    style.configure("Small.TButton", font="SluggersSmall", padding=(2, -1, 2, 0))    # a field's Stock
    style.configure("Compact.TEntry", padding=(4, 0, 4, 0))             # a column of short boxes (odds)
    style.configure("Stage.TLabel", font="SluggersSection")               # Progress: the stage line
    style.configure("StageDone.TLabel", font="SluggersSection", foreground=GREEN)
    style.configure("StageProblem.TLabel", font="SluggersSection", foreground=RED)
    # the classic Tk widgets (lists, text boxes) in the same font and colours
    root.option_add("*Listbox.font", "TkDefaultFont")
    root.option_add("*Listbox.relief", "flat")
    root.option_add("*Listbox.highlightThickness", 1)
    root.option_add("*Listbox.highlightColor", "#c0c0c0")
    root.option_add("*Listbox.highlightBackground", "#d9d9d9")
    root.option_add("*Listbox.selectBackground", "#cfe0f5")
    root.option_add("*Listbox.selectForeground", "#1c1c1c")
    root.option_add("*Text.font", "TkDefaultFont")
    root.option_add("*Text.relief", "flat")
    root.option_add("*Text.highlightThickness", 1)
    root.option_add("*Text.highlightColor", "#c0c0c0")
    root.option_add("*Text.highlightBackground", "#d9d9d9")
    set_icon(root)
    root._sluggers_style = theme
    return theme


def set_icon(root):
    """The app icon (app_icon.ico / .png, make_app_icon.py) on root and every window made after it. True when set."""
    try:
        if sys.platform == "win32" and ICON_ICO.is_file():
            root.iconbitmap(default=str(ICON_ICO))      # every Toplevel after it too (the .ico holds 16 to 256 px)
            root._icon_set = True
            return True
        if ICON_PNG.is_file():
            root._icon_image = tk.PhotoImage(master=root, file=str(ICON_PNG))
            root.iconphoto(True, root._icon_image)
            root._icon_set = True
            return True
    except tk.TclError:
        pass
    return False


def background(root):
    """The window's background colour (a Text or Canvas that should look like the page)."""
    return "#fafafa" if THEME == THEME_NAME else root.cget("background")


def title(win, name=None):
    """A window's title: the app's own name for the main window (name None), else "<name> - <app>"."""
    win.title(APP_NAME if not name else f"{name} {DASH} {APP_NAME}")
    return win


def window_name(win):
    """A window's own name from its title (the part before " - <app>")."""
    return str(win.title()).split(f" {DASH} ")[0]
