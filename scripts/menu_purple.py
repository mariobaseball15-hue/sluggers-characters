"""Menu background color (Nick, 2026-09-25: "change the background color of the character select to purple just for
fun"; the patcher lets the player pick the color, feature id "menu-color").

The blue behind the front-end menus is one untextured full-screen quad: dt_na dir 119 file 1 (the shared front-end
layout), element 9, node 11, two type-1 keys (stride 0x58, four RGBA vertex colours at +0x48, order bottom, top,
top, bottom): (8, 50, 157) at the bottom, (4, 73, 190) at the top. The dot pattern, glow and giant letters above it
are white, so they follow. Element 9 is the generic blue version (0x10 / 0x11 are green / gold copies), so every
menu that draws it turns the new color, not only character select.

The color is a preset name (PRESETS) or "#RRGGBB" for the top edge; the bottom edge is the top at BOTTOM_SHADE, like
the presets. No color = purple (the build's default output). "blue" is the stock look.

charbuild runs layout_bytes on file 1 through captains.patch_layouts (which rebuilds that file) when captains is on,
else on its own (patch_layout): the colour needs no new characters (Nick), so a clean game with only a menu colour
gets dir 119 file 1 with only the colour changed.
"""
import re
import struct

from layout import Layout

ELEMENT, NODE = 9, 11
FILE = 1                 # dt_na dir 119 file 1 (captains.FILE_LOGO)
STOCK = bytes.fromhex("08329dff0449beff0449beff08329dff")
# (bottom, top) RGB. purple is a muted one (Nick: the saturated (90, 8, 157) / (106, 4, 190) was "yelling"), halfway
# between the lighter (56, 44, 104) / (80, 66, 138) and the darker (34, 24, 68) / (52, 40, 94) tries ("somewhere in
# between"); the others are about as bright, so the white pattern and letters read the same on all of them
PRESETS = {
    "purple": ((45, 34, 86), (66, 53, 116)),
    "blue":   ((8, 50, 157), (4, 73, 190)),          # stock
    "red":    ((90, 28, 34), (122, 42, 48)),
    "green":  ((30, 76, 40), (44, 104, 56)),
    "orange": ((110, 56, 20), (146, 80, 30)),
    "pink":   ((104, 38, 76), (138, 56, 102)),
    "teal":   ((20, 74, 80), (30, 102, 110)),
    "black":  ((14, 14, 18), (30, 30, 38)),
}
DEFAULT = "purple"
BOTTOM_SHADE = 0.72
TOO_LIGHT = 170          # max channel of the top color above which the white pattern and letters stop reading


def colors(color=None):
    """(bottom, top) RGB for a preset name or "#RRGGBB" (the top edge). Raises ValueError on anything else."""
    color = (color or DEFAULT).strip().lower()
    if color in PRESETS:
        return PRESETS[color]
    m = re.fullmatch(r"#?([0-9a-f]{6})", color)
    if not m:
        raise ValueError(f"menu color {color!r}: a preset ({', '.join(PRESETS)}) or #RRGGBB")
    top = tuple(bytes.fromhex(m.group(1)))
    return tuple(round(c * BOTTOM_SHADE) for c in top), top


def warning(color):
    """A note for a color that will look bad (None if fine)."""
    top = colors(color)[1]
    if max(top) > TOO_LIGHT:
        return f"menu color {color}: very light; the white dot pattern, glow and letters will be hard to see"
    return None


def layout_bytes(data, color=None):
    bottom, top = (bytes(c) + b"\xff" for c in colors(color))
    L = Layout(data)
    e = L.elements[ELEMENT]
    keys = L.nodes(ELEMENT)[NODE]
    assert len(keys) == 2, f"background node has {len(keys)} keys"
    for key in keys:
        assert e[key + 4] == 1 and e[key + 0x48:key + 0x58] == STOCK, "the background quad's colours changed"
        e[key + 0x48:key + 0x58] = bottom + top + top + bottom
    return L.to_bytes()


def layout_for(color=None):
    """layout_bytes with the color bound, for captains.patch_layouts' extra map."""
    return lambda data: layout_bytes(data, color)


def patch_layout(dol, dat_path, color=None):
    """Without captains: dir 119 file 1 with only the colour changed, each language's copy appended to the output's own
    dt_na.dat (dat_path) and its record repointed (dtna_toc.rebuild_file, as captains.patch_layouts does)."""
    import dtna_toc
    n = dtna_toc.rebuild_file(dol, dat_path, 119, FILE, layout_for(color))
    top = "#%02X%02X%02X" % colors(color)[1]
    return [f"menu color: dir 119 file {FILE} rebuilt with the background {color or DEFAULT} ({top}), "
            f"{n} copies appended"]
