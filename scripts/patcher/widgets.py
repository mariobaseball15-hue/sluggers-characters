"""Widgets the patcher's pages share (git-b6): the character editor, the creators, the Stadiums tab's pages (git-64's
stadium builder, git-9b's select map). Stdlib tkinter plus Pillow, like the rest of the window.

Every field shows its own problem under it in plain words, never a traceback, and calls on_change(value) after an
edit that leaves it valid. set() from code never calls on_change.
"""
import re, shutil
import tkinter as tk
from tkinter import ttk, filedialog, colorchooser, messagebox, simpledialog
from pathlib import Path

import style
GREY, RED, AMBER = style.GREY, style.RED, style.AMBER   # AMBER: a warning that still lets it through (the menu
GREEN, LINK = style.GREEN, style.LINK                   # color's); the colours read on the theme (style.py)


def fmt(v):
    """A number as a player would type it: 12, 0.5 (not 0.5000001 or 12.0)."""
    return str(int(v)) if float(v).is_integer() else f"{v:.4f}".rstrip("0").rstrip(".")


class NumberField(ttk.Frame):
    """A labelled number box (with a slider when slider=True), its range and stock value in grey, a "Stock" button
    when there is one, and its problem in red underneath. short: "0-150, stock 42" and a narrower Stock (two
    columns of them fit a 760-wide window: the character editor's Stats, git-f4). limit: (low, high, warning) when
    lo..hi is only what the field can hold and the game's own range is narrower: the grey note shows the game's
    range, and a value past it is kept with the warning in amber underneath (Nick: past the game's limit, but
    warned)."""

    def __init__(self, parent, label, lo, hi, *, stock=None, kind=int, step=1, unit="", slider=False,
                 on_change=None, width=7, show_label=True, short=False, limit=None, label_width=None):
        super().__init__(parent)
        self.label, self.lo, self.hi, self.stock, self.kind = label, lo, hi, stock, kind
        self.limit = limit
        self.unit, self.on_change, self.last = unit, on_change, stock
        self.var = tk.StringVar(value="" if stock is None else fmt(stock))
        self.name_label = None
        if show_label:                  # (off: a checkbox beside it carries the name)
            self.name_label = ttk.Label(self, text=label + ":")
            self.name_label.grid(row=0, column=0, sticky="w")
            if label_width:                 # (px: a column of them lines up)
                self.columnconfigure(0, minsize=label_width)
        arrows = (lo, hi) if abs(hi) < 1e9 or not limit else limit[:2]   # (a float's room: the arrows walk the game's)
        self.box = ttk.Spinbox(self, from_=arrows[0], to=arrows[1], increment=step, textvariable=self.var, width=width,
                               command=self._edited)
        self.box.grid(row=0, column=1, sticky="w", padx=(4, 2))
        for event in ("<KeyRelease>", "<FocusOut>", "<Return>"):
            self.box.bind(event, lambda e: self._edited())
        col = 2
        self.scale = None
        if slider:
            self.slide = tk.DoubleVar(value=lo if stock is None else stock)
            self.scale = ttk.Scale(self, from_=lo, to=hi, variable=self.slide, length=140, command=self._slid)
            self.scale.grid(row=0, column=col, padx=4)
            col += 1
        glo, ghi = limit[:2] if limit else (lo, hi)
        note = f"{fmt(glo)}{'-' if short else ' to '}{fmt(ghi)}{unit}" + ("" if stock is None else f", stock {fmt(stock)}")
        ttk.Label(self, text=note, style="Small.TLabel").grid(row=0, column=col, sticky="w", padx=2)
        if stock is not None:
            ttk.Button(self, text="Stock", style="Small.TButton", command=self.reset).grid(row=0, column=col + 1,
                                                                                          padx=2)
        self.problem = ttk.Label(self, text="", foreground=RED, wraplength=340 if short else 0)   # (short: half a
        self.problem.grid(row=1, column=0, columnspan=col + 2, sticky="w")                        # 724-wide tab)
        self.problem.grid_remove()

    def parse(self, text):
        """(value, None) or (None, the problem in plain words)."""
        text = text.strip()
        if not text:
            glo, ghi = self.limit[:2] if self.limit else (self.lo, self.hi)
            return None, f"{self.label}: type a number from {fmt(glo)} to {fmt(ghi)}."
        try:
            v = float(text)
        except ValueError:
            return None, f"{self.label}: \"{text}\" isn't a number."
        if self.kind is int:
            if not v.is_integer():
                return None, f"{self.label} takes whole numbers."
            v = int(v)
        if not self.lo <= v <= self.hi:
            if self.limit:                              # past what the field holds: it can't be written
                if abs(self.hi) >= 1e9:
                    return None, f"{self.label}: {fmt(v)} is too big for the game's data."
                return None, (f"Too big: this stat holds at most {fmt(self.hi)}{self.unit}." if v > self.hi else
                              f"Too small: this stat holds at least {fmt(self.lo)}{self.unit}.")
            return None, f"{self.label} goes from {fmt(self.lo)} to {fmt(self.hi)}{self.unit}."
        return v, None

    def warning(self, v):
        """The amber line for a value kept past the game's limit ("" within it)."""
        if self.limit is None or v is None or self.limit[0] <= v <= self.limit[1]:
            return ""
        return self.limit[2]

    def get(self):
        return self.parse(self.var.get())[0]

    def error(self):
        return self.parse(self.var.get())[1]

    def set(self, v):
        self.var.set("" if v is None else fmt(v))
        self.last = v
        if self.scale is not None and v is not None:
            self.slide.set(v)
        self._show(None, self.warning(v))

    def reset(self):
        self.set(self.stock)
        if self.on_change:
            self.on_change(self.stock)

    def _show(self, problem, warning=""):
        self.problem.configure(text=problem or warning or "", foreground=RED if problem else AMBER)
        (self.problem.grid if problem or warning else self.problem.grid_remove)()

    def _edited(self):
        v, problem = self.parse(self.var.get())
        self._show(problem, "" if problem else self.warning(v))
        if problem is None:
            if self.scale is not None:
                self.slide.set(v)
            if v != self.last:
                self.last = v
                if self.on_change:
                    self.on_change(v)

    def _slid(self, _):
        v = self.slide.get()
        v = int(round(v)) if self.kind is int else round(v, 4)
        if v != self.last:
            self.var.set(fmt(v))
            self._edited()


class Scrolled(ttk.Frame):
    """A frame that scrolls (self.inner holds the content; the wheel scrolls it while the pointer is over it). It asks
    for only `height` pixels and takes the room it's given (pack it to fill and expand): Nick's 860 x 620."""

    def __init__(self, parent, height=120, **kw):
        super().__init__(parent, **kw)
        self.canvas = tk.Canvas(self, highlightthickness=0, height=height, width=200)
        self.bar = ttk.Scrollbar(self, orient="vertical", command=self.canvas.yview)
        self.inner = ttk.Frame(self.canvas)
        self.inner.bind("<Configure>", lambda e: self.refit())
        self.win = self.canvas.create_window((0, 0), window=self.inner, anchor="nw")
        self.canvas.bind("<Configure>", lambda e: (self.canvas.itemconfigure(self.win, width=e.width), self.refit()))
        self.canvas.configure(yscrollcommand=self.bar.set)
        self.canvas.pack(side="left", fill="both", expand=True)
        self.bind("<Enter>", lambda e: self.bind_all("<MouseWheel>", self.wheel))
        self.bind("<Leave>", lambda e: self.unbind_all("<MouseWheel>"))

    def needs_scroll(self):
        shown = self.canvas.winfo_height() if self.canvas.winfo_height() > 1 else int(self.canvas.cget("height"))
        return self.inner.winfo_reqheight() > shown

    def refit(self):
        """A scrollbar only when the content is taller than the room (git-92's Patcher 10: no bar, no wheel, back to
        the top when it fits)."""
        self.canvas.configure(scrollregion=self.canvas.bbox("all"))
        if self.needs_scroll():
            if not self.bar.winfo_manager():    # before the canvas: packed after it, the expanding canvas has
                self.bar.pack(side="right", fill="y", before=self.canvas)   # all the room and the bar none (Nick)
        else:
            self.bar.pack_forget()
            self.canvas.yview_moveto(0)

    def wheel(self, e):
        if self.needs_scroll():
            self.canvas.yview_scroll(int(-e.delta / 120), "units")


def set_enabled(widget, on):
    """Every ttk widget under widget enabled or disabled (a preset shown read-only)."""
    for w in [widget] + list(all_children(widget)):
        if isinstance(w, (ttk.Entry, ttk.Button, ttk.Checkbutton, ttk.Radiobutton, ttk.Scale, ttk.Spinbox)):
            if isinstance(w, ttk.Combobox):
                w.configure(state="readonly" if on else "disabled")
            else:
                w.state(["!disabled"] if on else ["disabled"])


def all_children(widget):
    for w in widget.winfo_children():
        yield w
        yield from all_children(w)


def hexrgb(rgb):
    return "#%02x%02x%02x" % tuple(rgb)


class ColorField(ttk.Frame):
    """A swatch, "Change..." (the colour chooser) and "Stock". get() / set() are (r, g, b), 0-255."""

    def __init__(self, parent, label, *, stock=(255, 255, 255), on_change=None, show_label=True):
        super().__init__(parent)
        self.stock, self.on_change, self.rgb = tuple(stock), on_change, tuple(stock)
        if show_label:
            ttk.Label(self, text=label + ":").pack(side="left")
        self.swatch = tk.Label(self, width=4, relief="solid", borderwidth=1, background=hexrgb(self.rgb))
        self.swatch.swatch = True               # a colour, not a missing label
        self.swatch.pack(side="left", padx=4)
        ttk.Button(self, text="Change...", command=self.choose).pack(side="left")
        ttk.Button(self, text="Stock", style="Small.TButton", command=self.reset).pack(side="left", padx=2)
        self.note = ttk.Label(self, text="", foreground=GREY)
        self.note.pack(side="left", padx=4)
        self.set(self.rgb)

    def get(self):
        return self.rgb

    def set(self, rgb):
        self.rgb = tuple(int(c) for c in rgb)
        self.swatch.configure(background=hexrgb(self.rgb))
        self.note.configure(text="stock" if self.rgb == self.stock else f"{hexrgb(self.rgb)} (stock "
                                                                         f"{hexrgb(self.stock)})")

    def choose(self):
        picked = colorchooser.askcolor(color=hexrgb(self.rgb), parent=self)[0]
        if picked:
            self._changed(tuple(int(round(c)) for c in picked))

    def reset(self):
        self._changed(self.stock)

    def _changed(self, rgb):
        self.set(rgb)
        if self.on_change:
            self.on_change(self.rgb)


class ImagePreview(ttk.Frame):
    """A fixed-size canvas showing a PIL image scaled to fit (aspect kept, never enlarged past 4x), on a checkerboard
    so transparency shows."""

    def __init__(self, parent, size=(200, 100)):
        super().__init__(parent)
        self.size = size
        self.canvas = tk.Canvas(self, width=size[0], height=size[1], highlightthickness=1,
                                highlightbackground="#999")
        self.canvas.pack()
        self.photo = None
        self.set(None)

    def set(self, image):
        from PIL import Image, ImageTk
        w, h = self.size
        board = Image.new("RGBA", (w, h), (204, 204, 204, 255))
        light = Image.new("RGBA", (8, 8), (240, 240, 240, 255))
        for y in range(0, h, 8):
            for x in range((y // 8) % 2 * 8, w, 16):
                board.paste(light, (x, y))
        if image is not None:
            im = image.convert("RGBA")
            k = min(w / im.width, h / im.height, 4)
            im = im.resize((max(1, round(im.width * k)), max(1, round(im.height * k))),
                           Image.NEAREST if k >= 1 else Image.LANCZOS)
            board.alpha_composite(im, ((w - im.width) // 2, (h - im.height) // 2))
        self.photo = ImageTk.PhotoImage(board, master=self)
        self.canvas.delete("all")
        self.canvas.create_image(0, 0, anchor="nw", image=self.photo)


class FileField(ttk.Frame):
    """A file picked by the player: its name, "Choose..." and "Clear". check(path) returns a problem in plain words
    or None; a file with a problem isn't kept."""

    def __init__(self, parent, label, kinds=(("Pictures", "*.png"),), *, check=None, on_change=None):
        super().__init__(parent)
        self.kinds, self.check, self.on_change, self.path = list(kinds), check, on_change, None
        ttk.Label(self, text=label + ":").grid(row=0, column=0, sticky="w")
        self.name = ttk.Label(self, text="(none)", foreground=GREY, width=30)
        self.name.grid(row=0, column=1, sticky="w", padx=4)
        ttk.Button(self, text="Choose...", command=self.choose).grid(row=0, column=2)
        ttk.Button(self, text="Clear", command=self.clear).grid(row=0, column=3, padx=2)
        self.problem = ttk.Label(self, text="", foreground=RED, wraplength=420)
        self.problem.grid(row=1, column=0, columnspan=4, sticky="w")
        self.problem.grid_remove()          # shown only with a problem

    def get(self):
        return self.path

    def set(self, path):
        """Show a file from code (a loaded creation): (True, None) or (False, its problem)."""
        path = Path(path) if path else None
        problem = self.problem_with(path) if path else None
        self.path = None if problem else path
        self.name.configure(text=self.path.name if self.path else "(none)")
        self.problem.configure(text=problem or "")
        (self.problem.grid if problem else self.problem.grid_remove)()
        return problem is None, problem

    def problem_with(self, path):
        if not path.is_file():
            return f"{path.name} isn't there any more."
        return self.check(path) if self.check else None

    def choose(self):
        picked = filedialog.askopenfilename(parent=self, filetypes=self.kinds + [("All files", "*.*")])
        if picked:
            ok, _ = self.set(picked)
            if ok and self.on_change:
                self.on_change(self.path)

    def clear(self):
        self.set(None)
        if self.on_change:
            self.on_change(None)


def fit(image, size):
    """The image scaled to fit size (aspect kept) and centred on a transparent size x size canvas."""
    from PIL import Image
    im = image.convert("RGBA")
    k = min(size[0] / im.width, size[1] / im.height)
    im = im.resize((max(1, round(im.width * k)), max(1, round(im.height * k))), Image.LANCZOS)
    out = Image.new("RGBA", size, (0, 0, 0, 0))
    out.alpha_composite(im, ((size[0] - im.width) // 2, (size[1] - im.height) // 2))
    return out


class ImageField(ttk.Frame):
    """A picture for the game: a picker, the picture fitted to size, a thumbnail and a line saying what was done.
    preview(fitted) -> image is what the thumbnail shows (git-9b: the game's colour loss); note replaces the "fitted
    to" line; check(path, fitted) returns a problem in plain words or None; thumb=(w, h) shows the thumbnail smaller than
    the fitted size (git-64's 640 x 448 loading picture)."""

    def __init__(self, parent, label, size, *, min_size=None, check=None, preview=None, note=None,
                 on_change=None, kinds=(("Pictures", "*.png"),), thumb=None):
        super().__init__(parent)
        self.size, self.min_size, self.check, self.preview = tuple(size), min_size, check, preview
        self.note_text, self.on_change, self.image = note, on_change, None
        self.file = FileField(self, label, kinds, check=self._problem, on_change=self._picked)
        self.file.grid(row=0, column=0, sticky="w")
        self.thumb = ImagePreview(self, tuple(thumb) if thumb else self.size)
        self.thumb.grid(row=1, column=0, sticky="w", pady=2)
        self.note = status(ttk.Label(self, text="", foreground=GREY, wraplength=420))   # blank until a picture
        self.note.grid(row=2, column=0, sticky="w")

    def _problem(self, path):
        from PIL import Image
        try:
            with Image.open(path) as im:
                im.load()
                image = im.copy()
        except Exception:
            return f"{path.name} isn't a picture the patcher can open. PNG files work."
        if self.min_size and (image.width < self.min_size[0] or image.height < self.min_size[1]):
            return (f"{path.name} is {image.width} x {image.height}; it needs to be at least "
                    f"{self.min_size[0]} x {self.min_size[1]}.")
        fitted = fit(image, self.size)
        problem = self.check(path, fitted) if self.check else None
        if problem is None:
            self._pending = fitted
        return problem

    def _show(self):
        shown = self.image
        if self.image is not None and self.preview:
            try:
                shown = self.preview(self.image)
            except Exception:
                shown = self.image
        self.thumb.set(shown)
        if self.image is None:
            self.note.configure(text="")
        else:
            self.note.configure(text=self.note_text or
                                f"Fitted to {self.size[0]} x {self.size[1]}, transparent edges kept.")

    def _picked(self, path):
        self.image = getattr(self, "_pending", None) if path else None
        self._pending = None
        self._show()
        if self.on_change:
            self.on_change(self.image)

    def get(self):
        return self.image

    def path(self):
        return self.file.get()

    def set(self, path):
        ok, problem = self.file.set(path)
        self.image = getattr(self, "_pending", None) if ok and path else None
        self._pending = None
        self._show()
        return ok, problem

    def clear(self):
        self.file.clear()


class DayNightSwitch(ttk.Frame):
    """Day / Night: which time of day a page's edits are for."""

    def __init__(self, parent, on_change=None):
        super().__init__(parent)
        self.var = tk.StringVar(value="day")
        for value, text in (("day", "Day"), ("night", "Night")):
            ttk.Radiobutton(self, text=text, value=value, variable=self.var, style="Toolbutton",
                            command=lambda: on_change and on_change(self.var.get())).pack(side="left")

    def get(self):
        return self.var.get()

    def set(self, value):
        assert value in ("day", "night"), value
        self.var.set(value)


def file_name(name):
    """A player's name for a creation as a file name (Windows' reserved characters dropped), or ""."""
    return re.sub(r'[<>:"/\\|?*\x00-\x1f]', "", name).strip().rstrip(".")


class PresetList(ttk.Frame):
    """Ours (presets, read-only, grey) and the player's own creations (folder/*suffix), with Copy to edit, New,
    Import..., Share... and Delete.

    presets: [(name, path)]. on_select(name, path, is_preset). make_new(path) writes a new creation there.
    copy(src, dst) makes a player's copy of a preset or creation (default: the file as it is). share(name, path)
    -> the file to hand out (default: the creation itself); import_(src) -> the creation's new path in folder
    (default: the file copied in); check(path) -> a problem with an imported file in plain words, or None."""

    def __init__(self, parent, presets, folder, suffix, *, on_select, make_new=None, copy=None, share=None,
                 import_=None, check=None, title="Presets", height=8, copy_button=True):
        super().__init__(parent)
        self.presets, self.folder, self.suffix = list(presets), Path(folder), suffix
        self.on_select, self.make_new, self.copy_fn = on_select, make_new, copy
        self.share_fn, self.import_fn, self.check = share, import_, check
        ttk.Label(self, text=title, font="SluggersSection").pack(anchor="w")
        box = ttk.Frame(self)
        box.pack(fill="both", expand=True)
        self.list = tk.Listbox(box, height=height, width=26, exportselection=False)
        bar = ttk.Scrollbar(box, orient="vertical", command=self.list.yview)
        self.list.configure(yscrollcommand=bar.set)
        self.list.pack(side="left", fill="both", expand=True)
        bar.pack(side="left", fill="y")
        self.list.bind("<<ListboxSelect>>", lambda e: self._selected())
        buttons = ttk.Frame(self)
        buttons.pack(fill="x", pady=2)
        self.copy_button = ttk.Button(buttons, text="Copy to edit", command=self.copy_selected)
        if copy_button:                         # (a page that edits ours in place and saves a copy has none)
            self.copy_button.grid(row=0, column=0, sticky="ew")
        if make_new:
            ttk.Button(buttons, text="New", command=self.new).grid(row=0, column=1, sticky="ew", padx=2)
        ttk.Button(buttons, text="Import...", command=self.import_file).grid(row=1, column=0, sticky="ew")
        self.share_button = ttk.Button(buttons, text="Share...", command=self.share)
        self.share_button.grid(row=1, column=1, sticky="ew", padx=2)
        self.delete_button = ttk.Button(buttons, text="Delete", command=self.delete)
        self.delete_button.grid(row=1, column=2, sticky="ew")
        self.rows = []
        self.refresh()

    def own(self):
        return sorted(self.folder.glob("*" + self.suffix), key=lambda p: p.stem.lower()) if self.folder.is_dir() \
            else []

    def refresh(self, select=None):
        """Re-read the folder; select=path picks that row."""
        keep = self.selected()
        want = Path(select) if select else keep and keep[1]
        self.list.delete(0, "end")
        self.rows = [(n, Path(p), True) for n, p in self.presets] + [(p.stem, p, False) for p in self.own()]
        for i, (name, path, preset) in enumerate(self.rows):
            self.list.insert("end", f"{name}  (ours)" if preset else name)
            if preset:
                self.list.itemconfigure(i, foreground=GREY)
            if want and path == want:
                self.list.selection_set(i)
                self.list.see(i)
        self._buttons()
        if select:
            self._selected()

    def selected(self):
        sel = self.list.curselection()
        return self.rows[sel[0]] if sel else None

    def _buttons(self):
        s = self.selected()
        self.copy_button.state(["!disabled"] if s else ["disabled"])
        for b in (self.share_button, self.delete_button):
            b.state(["!disabled"] if s and not s[2] else ["disabled"])

    def _selected(self):
        self._buttons()
        s = self.selected()
        if s:
            self.on_select(*s)

    def _target(self, suggested, prompt):
        """A new file in folder named by the player, or None (cancelled, or a name that can't be a file)."""
        name = simpledialog.askstring("Name", prompt, initialvalue=suggested, parent=self)
        if name is None:
            return None
        stem = file_name(name)
        if not stem:
            messagebox.showwarning("Name", "That name has no letters a file name can use. Try another.", parent=self)
            return None
        path = self.folder / (stem + self.suffix)
        if path.exists() and not messagebox.askyesno("Name", f"You already have {stem}. Replace it?", parent=self):
            return None
        self.folder.mkdir(parents=True, exist_ok=True)
        return path

    def copy_selected(self):
        s = self.selected()
        if not s:
            return
        dst = self._target(f"{s[0]} copy", "Name for your copy:")
        if dst:
            self._write(lambda: (self.copy_fn or shutil.copyfile)(s[1], dst), dst)

    def new(self):
        dst = self._target("New", "Name for the new one:")
        if dst:
            self._write(lambda: self.make_new(dst), dst)

    def _write(self, do, dst):
        try:
            do()
        except OSError as e:
            messagebox.showwarning("Save", f"Couldn't write {dst.name}: {e.strerror or e}.", parent=self)
            return
        self.refresh(select=dst)

    def import_file(self):
        src = filedialog.askopenfilename(parent=self, filetypes=[("Creations", "*" + self.suffix),
                                                                 ("All files", "*.*")])
        if not src:
            return
        src = Path(src)
        problem = self.check(src) if self.check else None
        if problem:
            messagebox.showwarning("Import", problem, parent=self)
            return
        try:
            if self.import_fn:
                dst = Path(self.import_fn(src))
            else:
                dst = self.folder / (src.stem + self.suffix)
                if dst.exists() and not messagebox.askyesno("Import", f"You already have {dst.stem}. Replace it?",
                                                            parent=self):
                    return
                self.folder.mkdir(parents=True, exist_ok=True)
                shutil.copyfile(src, dst)
        except OSError as e:
            messagebox.showwarning("Import", f"Couldn't import {src.name}: {e.strerror or e}.", parent=self)
            return
        except ValueError as e:         # an import_ function's plain-words refusal
            messagebox.showwarning("Import", str(e), parent=self)
            return
        self.refresh(select=dst)

    def share(self):
        s = self.selected()
        if not s or s[2]:
            return
        try:
            made = Path(self.share_fn(s[0], s[1])) if self.share_fn else s[1]
        except (OSError, ValueError) as e:
            messagebox.showwarning("Share", f"Couldn't make the file to share: {getattr(e, 'strerror', None) or e}.",
                                   parent=self)
            return
        dest = filedialog.asksaveasfilename(parent=self, initialfile=s[0] + made.suffix,
                                            defaultextension=made.suffix, filetypes=[("Creation", "*" + made.suffix)])
        if not dest:
            return
        try:
            if Path(dest).resolve() != made.resolve():
                shutil.copyfile(made, dest)
        except OSError as e:
            messagebox.showwarning("Share", f"Couldn't save {Path(dest).name}: {e.strerror or e}.", parent=self)
            return
        messagebox.showinfo("Share", f"Saved {Path(dest).name}. Anyone with the patcher can use Import... on it.",
                            parent=self)

    def delete(self):
        s = self.selected()
        if not s or s[2]:
            return
        if messagebox.askyesno("Delete", f"Delete {s[0]}? This can't be undone.", parent=self):
            try:
                s[1].unlink()
            except OSError as e:
                messagebox.showwarning("Delete", f"Couldn't delete {s[1].name}: {e.strerror or e}.", parent=self)
            self.refresh()


def ask_needs(parent, needs, title="Patch", intro="Your other picks need these features, which aren't ticked:",
              no="untick those picks instead and go on"):
    """needs: [(feature title, why)], e.g. ("Tantrum Toss", "Boom Boom is ticked on New characters & recolors").
    Never a question any more (Nick: "STOP WITH THE TICKS - IF I DO SOMETHING THEN IT SHOULD WORK"): always True,
    tick them, with no window; the caller ticks what's needed (gui.App.start does the same at Patch / Check)."""
    return True


# ---------------------------------------------------------------------------------------------------- help

class Tooltip:
    """Hover text on a widget and everything in it (a field's unit, range and what it does in the game). Only for
    detail: nothing a player needs lives only in a tooltip."""

    def __init__(self, widget, text, delay=500):
        self.widget, self.text, self.delay, self.job, self.tip = widget, text, delay, None, None
        for w in [widget] + list(all_children(widget)):
            w.bind("<Enter>", self.enter, add="+")
            w.bind("<Leave>", self.leave, add="+")
            w.bind("<ButtonPress>", self.leave, add="+")

    def enter(self, e=None):
        self.cancel()
        self.job = self.widget.after(self.delay, self.show)

    def leave(self, e=None):
        self.cancel()
        self.hide()

    def cancel(self):
        if self.job:
            self.widget.after_cancel(self.job)
            self.job = None

    def show(self):
        self.job = None
        if self.tip is not None or not self.text:
            return
        x = self.widget.winfo_pointerx() + 14
        y = self.widget.winfo_pointery() + 16
        self.tip = tk.Toplevel(self.widget)
        self.tip.wm_overrideredirect(True)
        self.tip.wm_geometry(f"+{x}+{y}")
        tk.Label(self.tip, text=self.text, justify="left", wraplength=320, background="#ffffff", foreground="#1c1c1c",
                 relief="solid", borderwidth=1, padx=8, pady=4, font="TkTooltipFont").pack()

    def hide(self):
        if self.tip is not None:
            self.tip.destroy()
            self.tip = None


def tip(widget, text):
    """widget with a Tooltip (None or "" text: none); returns the widget."""
    if text:
        widget._tooltip = Tooltip(widget, text)
    return widget


HOWTO_OPEN = {}                        # key -> open, for this session (each page remembers its How to)


def _no_help():
    """An edition without the "i"s and How tos (editions/*.json "no_help"; Nick: "The i's and how tos are terrible.
    Let's just get rid of those all for this beta"). The full patcher: False."""
    try:
        import edition
        return bool((edition.load() or {}).get("no_help"))
    except Exception:
        return False


NO_HELP = _no_help()


class HowTo(ttk.Frame):
    """A page's "How to": collapsed to one button by default, one click opens it; open or not is remembered per page
    (key) for the session. steps: 3-6 short sentences, numbered here; share: how to share or import; refused: the
    usual reasons it's refused. body_in: a frame to open the steps into (the button can sit on another row);
    before: a widget in that frame the steps open above."""

    def __init__(self, parent, steps, *, share=None, refused=None, key=None, title="How to", body_in=None,
                 before=None):
        super().__init__(parent)
        import fit
        self.key, self.title, self.before = key or title, title, before
        self.lines = []
        if NO_HELP:                                 # (an edition without How tos: nothing drawn, no space kept)
            self.button, self.body = ttk.Button(self), ttk.Frame(self)      # (never packed; callers may touch them)
            self.pack = self.grid = self.place = lambda *a, **k: None
            self.show = lambda open_: None
            return
        self.button = ttk.Button(self, style="Toolbutton", command=self.toggle)
        self.button.pack(anchor="w")
        self.body = ttk.Frame(body_in or self, padding=(12, 2, 0, 4))
        self.lines = [f"{i}. {s}" for i, s in enumerate(steps, 1)]
        if share:
            self.lines.append(f"Sharing: {share}")
        if refused:
            self.lines.append(f"If it's refused: {refused}")
        for line in self.lines:
            fit.label(self.body, line).pack(fill="x", anchor="w")
        self.show(HOWTO_OPEN.get(self.key, False))

    def show(self, open_):
        HOWTO_OPEN[self.key] = open_
        arrow = "▾" if open_ else "▸"
        self.button.configure(text=f"{self.title} {arrow}")
        if open_:
            self.body.pack(fill="x", anchor="w", **({"before": self.before} if self.before else {}))
        else:
            self.body.pack_forget()
            holder = self.body.master
            if not holder.pack_slaves() and not holder.grid_slaves():   # Tk keeps an emptied frame's last size
                holder.configure(width=1, height=1)                     # (git-9b): let it shrink back

    def toggle(self):
        self.show(not HOWTO_OPEN.get(self.key, False))

    def is_open(self):
        return HOWTO_OPEN.get(self.key, False)


def status(label):
    """Mark a label as a status line: blank until something happens, by design (test_labels.py lets it be empty,
    while a blank checkbox or an unlabelled box still fails). Returns the label."""
    label.status = True
    return label


GAME_CONTROLS = 'the "ISO file..." or "Folder..." button next to "Your game" at the top of the window'


def save_bar(parent, on_save, on_cancel=None, text="Save", padding=8):
    """Nick: "add a save button to the bottom right of all popup windows". A row pinned to the bottom of parent (packed
    before its other children, like the main window's Patch bar, so a small window never hides it): Save at the far
    right, Cancel just left of it when the window can discard (on_cancel). on_save does everything (what closing did,
    then close). Returns the row: row.save / row.cancel are the buttons; pack a problems line or more buttons into it
    side="left"."""
    row = ttk.Frame(parent, padding=padding)
    first = parent.pack_slaves()
    row.pack(side="bottom", fill="x", **({"before": first[0]} if first else {}))
    row.save = ttk.Button(row, text=text, command=on_save, style="Accent.TButton", width=max(8, len(text)))
    row.save.pack(side="right")
    row.cancel = None
    if on_cancel is not None:
        row.cancel = ttk.Button(row, text="Cancel", command=on_cancel, width=8)
        row.cancel.pack(side="right", padx=(0, 6))
    return row


def save_placement(win):
    """For the tests (headless windows don't lay out): where a window's Save is, as (at the far right of its row, the
    row packed at the bottom, the row packed before everything that expands beside it), or None with no Save."""
    for row in all_children(win):
        if not isinstance(row, (tk.Frame, ttk.Frame)) or not row.winfo_manager() == "pack":
            continue
        slaves = row.pack_slaves()
        save = next((b for b in slaves if isinstance(b, ttk.Button) and b.cget("text") == "Save"), None)
        if save is None:
            continue
        sibs = row.master.pack_slaves()
        grow = [s for s in sibs if str(s.pack_info().get("expand")) in ("1", "True", "true")]
        return (slaves[0] is save and save.pack_info()["side"] == "right", row.pack_info()["side"] == "bottom",
                all(sibs.index(row) < sibs.index(s) for s in grow))
    return None


def ask_for_game(parent, what, choosers):
    """No game picked yet: says what this page reads from the game (what, one sentence) and where the game is chosen,
    with a button per way to choose it (choosers: [(button text, fn() that shows the picker)]) and OK to go back.
    Returns True once a game was chosen. In a test (headless.install) it only records the call and returns False."""
    text = f"{what} Choose your game first: {GAME_CONTROLS}, or a button below."
    if getattr(tk, "_headless", None) is not None:
        tk._headless.append(("ask_for_game", "Your game", text))
        return False
    win = tk.Toplevel(parent)
    style.title(win, "Your game")
    win.transient(parent)
    win.resizable(False, False)
    body = ttk.Frame(win, padding=12)
    body.pack(fill="both", expand=True)
    ttk.Label(body, text=text, wraplength=420, justify="left").pack(anchor="w")
    chose = {"yes": False}

    def run(fn):
        fn()
        chose["yes"] = True
        win.destroy()
    row = ttk.Frame(body)
    row.pack(anchor="e", pady=(12, 0))
    for label, fn in choosers:
        ttk.Button(row, text=label, command=lambda fn=fn: run(fn)).pack(side="left", padx=(0, 6))
    ttk.Button(row, text="OK", command=win.destroy).pack(side="left")
    win.bind("<Escape>", lambda e: win.destroy())
    win.grab_set()
    win.wait_window()
    return chose["yes"]


# ---------------------------------------------------------------------------------------------------- data info (modders)

DATA_KEYS = (("file", "File"), ("where", "Where"), ("field", "Field"), ("hook", "Hook"), ("text", None),
             ("notes", "See also: notes page"), ("source", "See also: source"))


def data_text(data):
    """A setting's "data" (from its owner's schema: git-92's modder layer) as plain lines. data: a sentence, a dict
    with file / where / field / hook / text / notes / source (each a sentence), or a list of those (several sites)."""
    if not data:
        return ""
    if isinstance(data, str):
        return data
    if isinstance(data, (list, tuple)):
        return "\n\n".join(data_text(d) for d in data)
    lines = []
    for key, title in DATA_KEYS:
        v = data.get(key)
        if v:
            lines.append(f"{title}: {v}" if title else str(v))
    return "\n".join(lines)


class InfoPanel(ttk.Frame):
    """A page's panel for what a setting changes in the game's data: hidden until an "i" is clicked, read-only text
    that can be selected and copied (addresses), and Close. Inside the window, never a pop-up."""

    def __init__(self, parent, height=5):
        super().__init__(parent, padding=(0, 4, 0, 0))
        head = ttk.Frame(self)
        head.pack(fill="x")
        self.title = ttk.Label(head, text="", font="SluggersSection")
        self.title.pack(side="left")
        ttk.Button(head, text="Close", style="Toolbutton", command=self.hide).pack(side="right")
        self.text = tk.Text(self, height=height, wrap="word", relief="flat", background="#f4f4f4", borderwidth=0,
                            font="SluggersSmall")
        self.text.pack(fill="x")
        self.text.bind("<Key>", lambda e: None if (e.state & 4 and e.keysym.lower() in ("c", "a")) else "break")
        self.shown_for = None
        parent._info_panel = self            # an "i" under this frame shows here

    def show(self, title, data):
        self.title.configure(text=f"In the game's data: {title}")
        self.text.delete("1.0", "end")
        self.text.insert("1.0", data_text(data))
        self.shown_for = title
        if not self.winfo_manager():
            self.pack(fill="x", side="bottom")

    def hide(self):
        self.shown_for = None
        self.pack_forget()


def info_panel_for(widget):
    """The InfoPanel of the nearest frame above widget that has one."""
    w = widget
    while w is not None:
        p = getattr(w, "_info_panel", None)
        if p is not None:
            return p
        w = w.master
    return None


class InfoIcon(ttk.Button):
    """A small "i" beside a field, a block or a section: shows what it changes in the game's data in the nearest
    InfoPanel (git-92 for Nick: "so people can learn and make their own")."""

    def __init__(self, parent, title, data):
        super().__init__(parent, text="i", width=2, style="Icon.Toolbutton", command=self.clicked)
        self.title, self.data = title, data
        tip(self, "What this changes in the game's data")

    def clicked(self):
        panel = info_panel_for(self)
        if panel is not None:
            if panel.shown_for == self.title and panel.winfo_manager():
                panel.hide()
            else:
                panel.show(self.title, self.data)


def info(parent, title, data):
    """An InfoIcon when there's data, else None (a field its owner hasn't described yet gets none)."""
    return InfoIcon(parent, title, data) if data and not NO_HELP else None


def credit(key):
    """The credit line for a tab (git-10's scripts/credits.py: a whole "Thanks to ..." sentence), or None."""
    try:
        import credits
        line = credits.tab_line(key)
    except (ImportError, OSError):
        return None
    if not line:
        return None
    return line
