"""Recolored bats for the custom characters: each is a stock bat (characters/*.json "bat" source) with its
main texture (texture 0) edited to the character's colors. Shine maps (the other textures) are kept.

  python scripts/bat_recolors.py [name ...]    # -> models/work/bats/<name>.bin (+ <name>.png texture preview)

Recipes are small image operations on texture 0 in PIL coordinates (x right, y down):
  hue(from, to, width[, sat, box])   move saturated pixels near hue `from` to `to` (inside box, fractions)
  tint(r, g, b[, box])               multiply
  fill_where(pred, rgb, box)         set pixels matching pred(r, g, b) to rgb
  remap_hue(fn[, box, min_s])        each saturated pixel's hue h (degrees) becomes fn(h)
  gradient(top, bottom[, box])       paint a vertical two-color gradient over the box
  star(cx, cy, r, rgb[, ...])        draw an antialiased five-point star (pixel coordinates) with an
                                     optional rim; a star centered on a mirrored UV edge (x = 0, as on
                                     Daisy's bat) shows as one whole star on the bat
  ellipse / sparkle                  antialiased filled ellipse (eyes) / four-point twinkle
A recipe is one function (texture 0) or a dict {texture index: function} to paint other textures too,
such as the 8x8 handle color of Mario/Peach/Daisy-shaped bats. Sources are clean-game dirs only.
charbuild installs the .bin as the character's file 2 ("bat": {"file": ...}).
"""
import colorsys
import math
import os
import sys

from PIL import Image, ImageDraw

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from build_model import encode_texture  # noqa: E402
from dtna_reads import toc  # noqa: E402
from mss_model import Model, comp_size, quant16  # noqa: E402
from recolor_block import decode  # noqa: E402

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
OUT = os.path.join(ROOT, "models/work/bats")


def pixels(img, box):
    w, h = img.size
    x0, y0, x1, y1 = box or (0, 0, 1, 1)
    for y in range(int(y0 * h), int(y1 * h)):
        for x in range(int(x0 * w), int(x1 * w)):
            yield x, y


def hue(img, frm, to, width, sat=None, box=None, min_s=0.25):
    px = img.load()
    for x, y in pixels(img, box):
        r, g, b, a = px[x, y]
        h, s, v = colorsys.rgb_to_hsv(r / 255, g / 255, b / 255)
        if s >= min_s and abs((h * 360 - frm + 180) % 360 - 180) <= width:
            nr, ng, nb = colorsys.hsv_to_rgb(to / 360, s if sat is None else sat, v)
            px[x, y] = (round(nr * 255), round(ng * 255), round(nb * 255), a)


def tint(img, r_, g_, b_, box=None):
    px = img.load()
    for x, y in pixels(img, box):
        r, g, b, a = px[x, y]
        px[x, y] = (min(255, round(r * r_)), min(255, round(g * g_)), min(255, round(b * b_)), a)


def fill_where(img, pred, rgb, box=None):
    px = img.load()
    for x, y in pixels(img, box):
        r, g, b, a = px[x, y]
        if pred(r, g, b):
            px[x, y] = (*rgb, a)


def fill_enclosed_red(img, box=None, white=200):
    """On each row, red pixels between the row's leftmost and rightmost white pixel become white: erases a
    red emblem drawn on a white disc (Mario's "M") and leaves the disc's outline."""
    px = img.load()
    w, h = img.size
    x0, y0, x1, y1 = box or (0, 0, 1, 1)
    whites = [px[x, y][:3] for y in range(h) for x in range(w) if min(px[x, y][:3]) >= white]
    fill = tuple(sorted(c[k] for c in whites)[len(whites) // 2] for k in range(3)) if whites else (238, 238, 238)
    for y in range(int(y0 * h), int(y1 * h)):
        xs = [x for x in range(int(x0 * w), int(x1 * w)) if min(px[x, y][:3]) >= white]
        if len(xs) < 2:
            continue
        for x in range(xs[0], xs[-1] + 1):
            r, g, b, a = px[x, y]
            if r - max(g, b) > 20:     # red, and the pinkish anti-aliased edge of the emblem
                px[x, y] = (*fill, a)
    # and down each column, for strokes where the disc runs off the texture's side edge
    for x in range(int(x0 * w), int(x1 * w)):
        ys = [y for y in range(int(y0 * h), int(y1 * h)) if min(px[x, y][:3]) >= white]
        if len(ys) < 2:
            continue
        for y in range(ys[0], ys[-1] + 1):
            r, g, b, a = px[x, y]
            if r - max(g, b) > 20:     # red, and the pinkish anti-aliased edge of the emblem
                px[x, y] = (*fill, a)


def remap_hue(img, fn, box=None, min_s=0.25):
    px = img.load()
    for x, y in pixels(img, box):
        r, g, b, a = px[x, y]
        h, s, v = colorsys.rgb_to_hsv(r / 255, g / 255, b / 255)
        if s >= min_s:
            nr, ng, nb = colorsys.hsv_to_rgb((fn(h * 360) % 360) / 360, s, v)
            px[x, y] = (round(nr * 255), round(ng * 255), round(nb * 255), a)


def gradient(img, top, bottom, box=None):
    px = img.load()
    h = img.size[1]
    for x, y in pixels(img, box):
        t = y / max(1, h - 1)
        px[x, y] = (*(round(a + (b - a) * t) for a, b in zip(top, bottom)), px[x, y][3])


SS = 4   # supersampling for drawn shapes


def _overlay(img, draw_fn):
    """Draw at SS x resolution on a transparent layer, downsample, composite; img keeps its alpha."""
    layer = Image.new("RGBA", (img.width * SS, img.height * SS), (0, 0, 0, 0))
    draw_fn(ImageDraw.Draw(layer))
    layer = layer.resize(img.size, Image.LANCZOS)
    alpha = img.getchannel("A")
    img.alpha_composite(layer)
    img.putalpha(alpha)


def star_points(cx, cy, r, inner=0.45, rot=0.0):
    """Five-point star, first point up (toward -y), in supersampled coordinates."""
    pts = []
    for k in range(10):
        a = math.radians(rot - 90 + 36 * k)
        rr = r if k % 2 == 0 else r * inner
        pts.append(((cx + rr * math.cos(a)) * SS, (cy + rr * math.sin(a)) * SS))
    return pts


def star(img, cx, cy, r, rgb, inner=0.45, rim=None, width=0, rot=0.0):
    """Star at pixel (cx, cy) with outer radius r; with rim, a star `width` px larger goes under it."""
    def draw(d):
        if rim:
            d.polygon(star_points(cx, cy, r + width, inner, rot), fill=(*rim, 255))
        d.polygon(star_points(cx, cy, r, inner, rot), fill=(*rgb, 255))
    _overlay(img, draw)


def ellipse(img, cx, cy, rx, ry, rgb):
    _overlay(img, lambda d: d.ellipse([(cx - rx) * SS, (cy - ry) * SS, (cx + rx) * SS, (cy + ry) * SS],
                                      fill=(*rgb, 255)))


def sparkle(img, cx, cy, r, rgb):
    """Four-point twinkle."""
    t = r * 0.22
    pts = [(cx, cy - r), (cx + t, cy - t), (cx + r, cy), (cx + t, cy + t),
           (cx, cy + r), (cx - t, cy + t), (cx - r, cy), (cx - t, cy - t)]
    _overlay(img, lambda d: d.polygon([(x * SS, y * SS) for x, y in pts], fill=(*rgb, 255)))


def rosalina_wand(im):
    """Daisy's bat (64x128, U mirrored about x = 0): the flower becomes a silver star with a pale-gold
    heart, on a light-blue barrel with white twinkles. Flat colors: the barrel's ends sample this texture
    too, at other V, so a gradient would show as bands."""
    gradient(im, (104, 198, 222), (104, 198, 222))
    star(im, 0, 60, 40, (132, 148, 174), rim=(255, 255, 255), width=4)   # white rim, silver edge
    star(im, 0, 60, 35, (226, 232, 242))                                 # silver face
    star(im, 0, 60, 15, (255, 238, 150), inner=0.5)                      # glowing heart
    for x, y, r in ((44, 16, 7), (54, 104, 6), (30, 116, 4), (52, 40, 3)):
        sparkle(im, x, y, r, (255, 255, 255))


def silver(im):
    gradient(im, (200, 208, 220), (176, 186, 200))


def luma_star(im):
    """Peach's bat (128x128 crown sticker): a Luma star sticker, eyes and all, on a golden barrel."""
    gradient(im, (240, 184, 36), (240, 184, 36))          # flat: see rosalina_wand
    star(im, 64, 68, 50, (214, 132, 22), inner=0.5, rim=(255, 255, 255), width=5)
    star(im, 64, 68, 45, (255, 222, 64), inner=0.5)
    star(im, 61, 63, 26, (255, 240, 150), inner=0.5)                     # highlight
    for ex in (55, 73):
        ellipse(im, ex, 70, 4.5, 8, (24, 20, 20))
        ellipse(im, ex - 1, 66, 1.5, 2, (255, 255, 255))


def larry_brush(im):
    """Bowser Jr.'s paintbrush (256x256 atlas): rainbow paint -> Larry's teal-to-blue bands, yellow
    handle strip -> royal blue, yellow emblem -> light teal. The silver ferrule is kept."""
    remap_hue(im, lambda h: 172 + h / 360 * 55, box=(0.0, 0.5, 0.5, 1.0), min_s=0.2)
    hue(im, 55, 222, 35, sat=0.85, box=(0.8, 0.0, 1.0, 1.0), min_s=0.2)
    hue(im, 55, 185, 35, sat=0.7, box=(0.3, 0.0, 0.8, 0.5), min_s=0.2)


def is_red(r, g, b):
    return r > 110 and r > g * 1.8 and r > b * 1.8


# Magikoopa's scepter: gold top half, red orb in the lower-left quarter, white lower-right.
ORB = (0.0, 0.5, 0.5, 1.0)
RECIPES = {
    "iggy": (51, lambda im: hue(im, 5, 110, 40, box=ORB)),                 # green orb
    "lemmy": (51, lambda im: (hue(im, 5, 30, 40, sat=1.0, box=ORB), tint(im, 1.25, 1.25, 1.0, box=ORB))),  # orange orb
    "ludwig": (51, lambda im: hue(im, 5, 220, 40, box=ORB)),               # blue orb
    "morton": (51, lambda im: (hue(im, 5, 25, 40, sat=0.6, box=ORB), tint(im, 0.7, 0.7, 0.7, box=ORB))),  # brown orb
    "roy": (51, lambda im: hue(im, 5, 285, 40, box=ORB)),                  # purple orb
    "wendy": (51, lambda im: hue(im, 5, 330, 40, box=ORB)),                # pink orb
    "pompom": (71, lambda im: (hue(im, 0, 330, 40), tint(im, 1.0, 0.82, 0.9))),   # pink boomerang
    # Mario's bat: red with an "M" on a white disc; the M's red strokes inside the disc become white.
    "pauline": (18, lambda im: fill_enclosed_red(im)),
    "orange-toad": (31, lambda im: hue(im, 0, 26, 25, min_s=0.25)),      # Red Toad's bat, red -> Orange Toad
    "penguru": (46, lambda im: hue(im, 30, 215, 35, min_s=0.2)),           # brown cane -> penguin blue
    "dino-piranha": (39, lambda im: hue(im, 40, 105, 25, sat=0.45, box=(0.0, 0.0, 0.5, 1.0), min_s=0.08)),
    "bouldergeist": (76, lambda im: tint(im, 1.9, 1.8, 1.7, box=(0.0, 0.0, 1.0, 1.0))),   # stone gray
    # Our Luma bat (Peach's bat with a Luma star sticker; Luma 0x84), and each colored Luma's hue
    # shift of it (the same shifts the Luma models use).
    "luma": (22, luma_star),
    "luma-green": (22, lambda im: (luma_star(im), hue(im, 50, 120, 35, min_s=0.2))),
    "luma-blue": (22, lambda im: (luma_star(im), hue(im, 50, 205, 35, min_s=0.2))),
    "luma-red": (22, lambda im: (luma_star(im), hue(im, 50, 355, 35, min_s=0.2))),
    "rosalina": (23, {0: rosalina_wand, 1: silver}),                     # star wand; Rosalina 0x81
    "larry": (37, larry_brush),                                         # Larry 0x83
    "king-bobomb": (80, lambda im: (hue(im, 180, 0, 30, box=(0.5, 0.0, 1.0, 0.25)),
                                    hue(im, 120, 0, 30, box=(0.5, 0.0, 1.0, 0.25)))),     # gems -> red
}


# Bats scale with the character's json "scale" (the sizescale row scales the whole character). When a size pass
# changes that scale, the bat is shrunk about its grip to keep its old size in the world (as make_bat.py --scale).
# King Bob-omb 1.17 -> 1.34 and Bouldergeist 0.83 -> 1.57 (their models now fill the template's skeleton).
SCALES = {"king-bobomb": 1.17 / 1.34, "bouldergeist": 0.83 / 1.57,
          # Lumas (Peach's 0.97-long bat) swing with Boo's animations: reach Boo's own bat (1.42) at their 0.88
          # scale, 1.42 / (0.97 * 0.88) (Nick: the Luma bat doesn't even reach the plate)
          **{n: 1.423 / (0.968 * 0.88) for n in ("luma", "luma-blue", "luma-green", "luma-red")}}


def scale_positions(block, k):
    done = set()
    for sm in Model(bytes(block)).submeshes:
        p = sm.position
        if p.ptr in done:
            continue
        done.add(p.ptr)
        assert comp_size(p.quant) == 2 and p.quant >> 4 != 2, "scale: signed 16-bit positions expected"
        vals = [c * k for v in p.values(block) for c in v]
        block[p.ptr:p.ptr + p.count * p.element_size()] = quant16(vals, p.quant)


def build(name):
    src_dir, recipe = RECIPES[name]
    game = "clean"
    rec = {(d, f): (o, l) for d, f, o, l in toc(os.path.join(ROOT, f"extracted/{game}/sys/main.dol"))}
    off, length = rec[(src_dir, 2)]
    with open(os.path.join(ROOT, f"extracted/{game}/files/dt_na.dat"), "rb") as f:
        f.seek(off)
        entry = bytearray(f.read(length))
    member = int.from_bytes(entry[4:8], "big")
    block = bytearray(entry[member:])
    if name in SCALES:
        scale_positions(block, SCALES[name])
    textures = Model(bytes(block)).textures
    os.makedirs(OUT, exist_ok=True)
    for i, fn in (recipe if isinstance(recipe, dict) else {0: recipe}).items():
        tex = textures[i]
        img = decode(bytes(block), tex)
        fn(img)
        block[tex.image:tex.image + tex.payload_size()] = encode_texture(img, tex.format, tex.payload_size())
        img.save(os.path.join(OUT, f"{name}.png" if i == 0 else f"{name}_tex{i}.png"))
        print(f"BAT {name}: dir {src_dir} file 2, texture {i} {tex.width}x{tex.height} recolored")
    entry[member:] = block
    open(os.path.join(OUT, f"{name}.bin"), "wb").write(bytes(entry))


if __name__ == "__main__":
    for n in sys.argv[1:] or list(RECIPES):
        build(n)
