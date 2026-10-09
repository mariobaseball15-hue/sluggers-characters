"""Layout helpers for the patcher window's pages (git-f4): text that wraps to the width it's given, and canvases
that draw to the size they're given (Nick's Patcher 8 screenshot: fixed widths clipped at 860 x 620)."""
from tkinter import ttk


def label(parent, text, bold=False, grey=False, wrap=300, **kw):
    """A left-aligned line that wraps to its own width (pack or grid it to fill x). bold: a section's line
    (style.py's semibold), grey: a hint. wrap: the width it asks for before it's laid out (it takes what it's
    given and wraps there)."""
    import style
    opts = {"font": "SluggersSection"} if bold else {}
    if grey:
        opts["foreground"] = style.GREY
    lab = ttk.Label(parent, text=text, justify="left", anchor="w", wraplength=wrap, **{**opts, **kw})
    pad = kw.get("padding", 0)                  # (its own padding: the text wraps inside it)
    pad = [pad] if isinstance(pad, int) else list(pad)
    side = (pad[0] + pad[2 if len(pad) > 2 else 0]) if pad else 0
    lab.bind("<Configure>", lambda e: lab.configure(wraplength=max(100, e.width - 4 - side)))
    return lab


def on_resize(canvas, redraw, delay=60):
    """redraw() after the canvas changes size (once per burst of <Configure> events)."""
    state = {"job": None, "size": None}

    def configured(e):
        if (e.width, e.height) == state["size"]:
            return
        state["size"] = (e.width, e.height)
        if state["job"]:
            canvas.after_cancel(state["job"])
        state["job"] = canvas.after(delay, done)

    def done():
        state["job"] = None
        redraw()
    canvas.bind("<Configure>", configured)


def size(canvas):
    """The canvas's drawing size: as laid out, else as asked for (before it's shown, or in a hidden test window)."""
    w, h = canvas.winfo_width(), canvas.winfo_height()
    if w <= 1 or h <= 1:
        w, h = int(canvas.cget("width")), int(canvas.cget("height"))
    return w, h
