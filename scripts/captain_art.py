"""Captain-select art for a new captain: one 512x512 RGB5A3 texture page holding the big portrait, the
lineup figure, its highlight glow and the name plate, plus their pixel rectangles.

Stock art (dt_na.dat dir 119 file 18): lineup figures ~60-100 x 140-155 (C8), highlight glows are the
figure's soft white silhouette ~20 px larger (C4 / IA8), portraits ~300 x 370, name plates 164 x 31
(name left-aligned, light fill, dark outline). Our captains' renders come from scripts/blender/render_captain.py;
a captain without art gets it drawn from its own 3D model at patch time (model_art, below).
"""
import struct

import numpy as np

from PIL import Image, ImageDraw, ImageFilter, ImageFont

PAGE = 512
NAME_SIZE = (164, 31)
# A font we ship (scripts/fonts, OFL; drawn on the player's PC at patch time): Open Sans ExtraBold, as the card names
# (char_names). It was Segoe UI Black, Microsoft's, from C:/Windows/Fonts.
FONT = __file__.replace("captain_art.py", "fonts/OpenSans[wdth,wght].ttf")


def open_font(size):
    f = ImageFont.truetype(FONT, size)
    f.set_variation_by_axes([800, 100])
    return f
GX_RGB5A3 = 5


def glow(figure, pad=20, blur=7):
    """White silhouette of the figure, grown and blurred."""
    a = figure.getchannel("A").point(lambda v: 255 if v > 32 else 0)
    w, h = figure.size
    big = Image.new("L", (w + 2 * pad, h + 2 * pad))
    big.paste(a, (pad, pad))
    big = big.filter(ImageFilter.MaxFilter(9)).filter(ImageFilter.GaussianBlur(blur))
    out = Image.new("RGBA", big.size, (255, 255, 255, 0))
    out.putalpha(big)
    return out


def plate_style(stock):
    """A stock captain's name plate (RGBA, NAME_SIZE) -> (its fill colour per line, its outline colour): the light
    letters' average colour on each line (their gradient: Daisy's cream to yellow, Luigi's green...), and the dark
    outline's."""
    px = stock.load()
    w, h = stock.size
    lum = lambda p: 0.3 * p[0] + 0.59 * p[1] + 0.11 * p[2]           # noqa: E731
    ramp = []
    for y in range(h):
        fill = [px[x, y] for x in range(w) if px[x, y][3] >= 250 and lum(px[x, y]) >= 110]
        ramp.append(tuple(sum(p[i] for p in fill) // len(fill) for i in range(3)) if fill else None)
    known = [y for y, c in enumerate(ramp) if c]
    assert known, "no light letters on the stock plate"
    ramp = [ramp[y] or ramp[min(known, key=lambda k: abs(k - y))] for y in range(h)]
    dark = sorted((p for x in range(w) for y in range(h) for p in [px[x, y]] if p[3] >= 250 and lum(p) < 60), key=lum)
    outline = dark[len(dark) // 2][:3] if dark else (24, 24, 32)
    return ramp, outline


def name_plate(text, style=None):
    """text on a NAME_SIZE plate. style: plate_style(a stock plate): that captain's colours and a drop shadow, as the
    stock plates (a renamed stock captain); None: our custom captains' light grey."""
    if style is not None:
        return _styled_plate(text, *style)
    img = Image.new("RGBA", NAME_SIZE, (0, 0, 0, 0))
    draw = ImageDraw.Draw(img)
    size = 25                                  # shrink long names to fit the plate
    while size > 12 and draw.textbbox((3, 0), text, font=open_font(size), stroke_width=2)[2] > NAME_SIZE[0] - 2:
        size -= 1
    font = open_font(size)
    draw.text((3, -2 + (25 - size) // 2), text, font=font, fill=(236, 240, 244, 255), stroke_width=2, stroke_fill=(24, 24, 32, 255))
    return img


def _styled_plate(text, ramp, outline):
    w, h = NAME_SIZE
    probe = ImageDraw.Draw(Image.new("L", NAME_SIZE))
    size = 25
    while size > 12 and probe.textbbox((3, 0), text, font=open_font(size), stroke_width=2)[2] > w - 4:
        size -= 1
    font = open_font(size)
    x0, _, x1, _ = probe.textbbox((0, 0), text, font=font, stroke_width=2)
    at = ((w - (x1 - x0)) // 2 - x0, -2 + (25 - size) // 2)       # centred, as every stock plate (ink centre ~82)
    letters, edge = Image.new("L", NAME_SIZE), Image.new("L", NAME_SIZE)
    ImageDraw.Draw(letters).text(at, text, font=font, fill=255)
    ImageDraw.Draw(edge).text(at, text, font=font, fill=255, stroke_width=2, stroke_fill=255)
    shadow = Image.new("L", NAME_SIZE)
    shadow.paste(edge, (2, 2))                                    # the stock plates' soft shadow, down and right
    shadow = shadow.filter(ImageFilter.GaussianBlur(1)).point(lambda v: v * 6 // 10)
    img = Image.new("RGBA", NAME_SIZE, (0, 0, 0, 0))
    img.paste(Image.new("RGBA", NAME_SIZE, tuple(outline) + (255,)), (0, 0), shadow)
    img.paste(Image.new("RGBA", NAME_SIZE, tuple(outline) + (255,)), (0, 0), edge)
    fill = Image.new("RGBA", NAME_SIZE)
    fill.putdata([tuple(ramp[y]) + (255,) for y in range(h) for _ in range(w)])
    img.paste(fill, (0, 0), letters)
    return img


def rgb5a3(img):
    """GX RGB5A3, 4x4 tiles."""
    w, h = img.size
    px = img.load()
    out = bytearray()
    for ty in range(0, h, 4):
        for tx in range(0, w, 4):
            for y in range(ty, ty + 4):
                for x in range(tx, tx + 4):
                    r, g, b, a = px[x, y]
                    if a >= 0xE0:
                        v = 0x8000 | (r >> 3) << 10 | (g >> 3) << 5 | b >> 3
                    else:
                        v = (a >> 5) << 12 | (r >> 4) << 8 | (g >> 4) << 4 | b >> 4
                    out += struct.pack(">H", v)
    return bytes(out)


FIT = {"portrait": (300, 370), "lineup": (100, 150), "logo": (153, 54), "emblem": (90, 90)}


def fit(img, key):
    """Scale art down (keeping its shape) to the stock size for its kind: portrait 300 x 370, lineup
    figure 100 x 150; logo and emblem are placed at exactly 153 x 54 / 90 x 90."""
    w, h = FIT[key]
    if key in ("logo", "emblem"):
        return img if img.size == (w, h) else img.resize((w, h), Image.LANCZOS)
    if img.width <= w and img.height <= h:
        return img
    s = min(w / img.width, h / img.height)
    return img.resize((max(1, round(img.width * s)), max(1, round(img.height * s))), Image.LANCZOS)


def fit_pad(img, key):
    """A player's picture as a logo (153 x 54) or emblem (90 x 90): scaled to fit, keeping its shape, centred on
    transparent padding (fit() stretches ours, which are drawn at those sizes)."""
    w, h = FIT[key]
    img = img.convert("RGBA")
    if img.size == (w, h):
        return img
    s = min(w / img.width, h / img.height)
    small = img.resize((max(1, round(img.width * s)), max(1, round(img.height * s))), Image.LANCZOS)
    out = Image.new("RGBA", (w, h), (0, 0, 0, 0))
    out.paste(small, ((w - small.width) // 2, (h - small.height) // 2))
    return out


def placeholder(name, key):
    """Stand-in art until the real art is in captains/<art>/: a labelled shape at the stock size."""
    w, h = FIT[key]
    img = Image.new("RGBA", (w, h), (0, 0, 0, 0))
    d = ImageDraw.Draw(img)
    fill, line = (90, 110, 150, 255), (240, 240, 250, 255)
    if key == "emblem":
        d.ellipse((2, 2, w - 3, h - 3), fill=fill, outline=line, width=4)
        text, size = name[0], 48
    elif key == "lineup":
        d.ellipse((w // 2 - 22, 4, w // 2 + 22, 48), fill=fill, outline=line, width=3)
        d.rounded_rectangle((w // 2 - 34, 50, w // 2 + 34, h - 4), 16, fill=fill, outline=line, width=3)
        text, size = name[0], 40
    else:
        d.rounded_rectangle((1, 1, w - 2, h - 2), 12, fill=fill, outline=line, width=3)
        text, size = name, 22 if key == "logo" else 34
    font = open_font(size)
    box = d.textbbox((0, 0), text, font=font, stroke_width=2)
    tw, th = box[2] - box[0], box[3] - box[1]
    cy = h // 2 if key != "lineup" else 50 + (h - 54) // 2
    d.text((w // 2 - tw // 2 - box[0], cy - th // 2 - box[1]), text, font=font, fill=line,
           stroke_width=2, stroke_fill=(24, 24, 32, 255))
    return img


def build_page(portrait, lineup, name, size=(PAGE, PAGE)):
    """-> (page image bytes, {"portrait" | "lineup" | "glow" | "name": (x0, y0, x1, y1)}, page image).
    captains.py uses 512 x 384: the portrait column, then lineup, glow and name plate in a second one."""
    W, H = size
    page = Image.new("RGBA", size, (0, 0, 0, 0))
    parts, rects = {"portrait": portrait, "lineup": lineup, "glow": glow(lineup), "name": name_plate(name)}, {}
    x, y, col_w = 0, 0, 0
    for key in ("portrait", "lineup", "glow", "name"):          # simple column packing
        img = parts[key]
        if y + img.height > H:
            x, y, col_w = x + col_w + 4, 0, 0
        assert x + img.width <= W and img.height <= H, f"{key} does not fit the page"
        page.paste(img, (x, y))
        rects[key] = (x, y, x + img.width, y + img.height)
        y += img.height + 4
        col_w = max(col_w, img.width)
    return rgb5a3(page), rects, page


# ------------------------------------------------------------------------------------ art drawn from a 3D model
# A captain without captain art (a stock non-captain, a recolor, an import) gets its art drawn from its own model block
# on the player's PC when they patch (model_render: numpy, no Blender), so nothing of the game's ships: the portrait
# (upper body, a three-quarter view), the lineup figure (full body), the emblem (the head in a coloured ring) and the
# team logo (the name on a band of the character's own main colour, the emblem at its left).
VIEW_YAW, VIEW_PITCH = 24, 7          # degrees: the character turned to its right a little, the camera a little above
PORTRAIT_BELOW = 0.6                  # the portrait shows down to this much of the head-and-neck height under the
#                                       shoulders (Mario: to his belt; a Toad, all of it)
SLATE = (84, 98, 128)                 # the band's colour when a character has no strong colour (Boo, Dry Bones)


def _window(V, frame, top_anchor, cut=None, margin=0.04):
    """A view-space window (x0, y0, x1, y1) of the frame's shape around the vertices V (n, 3) at or above cut."""
    fw, fh = frame
    keep = V[:, 1] >= (cut if cut is not None else -np.inf)
    xs, ys = V[keep, 0], V[keep, 1]
    top, bottom = ys.max(), (cut if cut is not None else ys.min())
    w, h = (xs.max() - xs.min()) * (1 + 2 * margin), (top - bottom) * (1 + 2 * margin)
    if w / h > fw / fh:
        h = w * fh / fw
    else:
        w = h * fw / fh
    cx = (xs.max() + xs.min()) / 2
    if top_anchor:
        y1 = top + (top - bottom) * margin
        return cx - w / 2, y1 - h, cx + w / 2, y1
    y0 = bottom - (top - bottom) * margin
    return cx - w / 2, y0, cx + w / 2, y0 + h


def _view(mesh, yaw, pitch):
    import model_render
    R = model_render.rotation(yaw, pitch)
    V = model_render.project(mesh, yaw, pitch).reshape(-1, 3)
    sh = None if mesh.shoulder is None else float((R @ mesh.shoulder)[1])
    return V, sh


def portrait_of(mesh):
    """The portrait (FIT["portrait"], RGBA): the head and upper body, top-anchored; a character without arms (Luma,
    Boo) whole, standing on the bottom edge as King Boo's and Luma's."""
    import model_render
    V, sh = _view(mesh, VIEW_YAW, VIEW_PITCH)
    size = FIT["portrait"]
    if sh is None:
        win = _window(V, size, top_anchor=False)
    else:
        top = V[:, 1].max()
        win = _window(V, size, top_anchor=True, cut=max(V[:, 1].min(), sh - PORTRAIT_BELOW * (top - sh)))
    return model_render.render(mesh, size, VIEW_YAW, VIEW_PITCH, win, ss=2)


def lineup_of(mesh):
    """The lineup figure (FIT["lineup"], RGBA): the whole body standing on the bottom edge, centred."""
    import model_render
    yaw, pitch = VIEW_YAW - 6, VIEW_PITCH - 2
    V, _ = _view(mesh, yaw, pitch)
    return model_render.render(mesh, FIT["lineup"], yaw, pitch, _window(V, FIT["lineup"], top_anchor=False,
                                                                        margin=0.02), ss=3)


def head_of(mesh, size):
    """The head, filling a square of `size` px (RGBA): above the shoulders (a character without arms: all of it)."""
    import model_render
    yaw, pitch = VIEW_YAW - 8, VIEW_PITCH
    V, sh = _view(mesh, yaw, pitch)
    top = V[:, 1].max()
    if sh is None:
        win = _window(V, (1, 1), top_anchor=False, margin=0.03)
    else:
        head = V[V[:, 1] >= sh + 0.12 * (top - sh)]              # the head's width, without the shoulders
        x0, x1 = head[:, 0].min(), head[:, 0].max()
        bottom = sh - 0.1 * (top - sh)
        side = max(x1 - x0, top - bottom) * 1.04
        cx = (x0 + x1) / 2
        win = (cx - side / 2, top + 0.02 * side - side, cx + side / 2, top + 0.02 * side)
    return model_render.render(mesh, (size, size), yaw, pitch, win, ss=3)


def main_colour(img):
    """A character's own colour from its render (RGBA): its most common strong hue's average, made a band colour
    (full, mid-dark); SLATE when it has none."""
    import colorsys
    a = np.asarray(img.convert("RGBA"), dtype=np.float32) / 255.0
    px = a[a[:, :, 3] > 0.9][:, :3]
    if not len(px):
        return SLATE
    mx, mn = px.max(1), px.min(1)
    sat = np.where(mx > 0, (mx - mn) / np.maximum(mx, 1e-6), 0)
    strong = (sat > 0.4) & (mx > 0.3)
    if strong.sum() < 0.04 * len(px):
        return SLATE
    hsv = np.array([colorsys.rgb_to_hsv(*p) for p in px[strong][::max(1, int(strong.sum()) // 4000)]])
    bins = (hsv[:, 0] * 24).astype(int) % 24
    w = np.bincount(bins, weights=hsv[:, 1] * hsv[:, 2], minlength=24)
    w = w + 0.5 * (np.roll(w, 1) + np.roll(w, -1))              # (a hue split over two bins)
    top = int(np.argmax(w))
    sel = hsv[np.isin(bins, [(top - 1) % 24, top, (top + 1) % 24])]
    h = float(np.angle(np.exp(2j * np.pi * sel[:, 0]).mean()) / (2 * np.pi)) % 1.0
    s = min(1.0, max(0.62, float(sel[:, 1].mean())))
    v = min(0.78, max(0.5, float(sel[:, 2].mean()) * 0.85))
    return tuple(int(round(c * 255)) for c in colorsys.hsv_to_rgb(h, s, v))


def _shade(rgb, k):
    return tuple(max(0, min(255, int(round(c * k)))) for c in rgb)


def emblem_of(head, colour, size=90):
    """The emblem (size x size, RGBA): a ring in the character's colour with its head in it, the top of the head
    over the ring (as the stock crowns)."""
    ss = 4
    S = size * ss
    c, r = S / 2, S * 0.47
    ring_w, edge = S * 0.045, S * 0.02
    yy, xx = np.mgrid[0:S, 0:S].astype(np.float32) + 0.5
    d = np.hypot(xx - c, yy - c)
    t = np.clip((yy - (c - r)) / (2 * r), 0, 1)[:, :, None]     # a top-to-bottom gradient inside
    inner = np.array(_shade(colour, 1.35), np.float32) * (1 - t) + np.array(_shade(colour, 0.8), np.float32) * t
    out = np.zeros((S, S, 4), np.float32)
    fill = d <= r - ring_w - edge
    ring = (d <= r - edge) & ~fill
    outline = (d <= r) & ~fill & ~ring
    out[fill, :3], out[fill, 3] = np.minimum(inner[fill], 255), 255
    out[ring, :3], out[ring, 3] = (245, 245, 250), 255
    out[outline, :3], out[outline, 3] = (24, 24, 32), 255
    base = Image.fromarray(out.astype(np.uint8), "RGBA").resize((size, size), Image.LANCZOS)
    face = head.resize((round(size * 0.84), round(size * 0.84)), Image.LANCZOS)
    layer = Image.new("RGBA", (size, size), (0, 0, 0, 0))
    layer.paste(face, ((size - face.width) // 2, size - face.height - round(size * 0.1)))
    # inside the ring, and anything above its middle (the top of the head may pass over the ring)
    m = Image.new("L", (S, S), 0)
    k = r - ring_w - edge
    ImageDraw.Draw(m).ellipse((c - k, c - k, c + k, c + k), fill=255)
    ImageDraw.Draw(m).rectangle((0, 0, S, c), fill=255)
    m = m.resize((size, size), Image.LANCZOS)
    alpha = Image.fromarray((np.asarray(layer.getchannel("A"), np.float32) * np.asarray(m, np.float32) / 255)
                            .astype(np.uint8))
    layer.putalpha(alpha)
    shadow = Image.new("RGBA", (size, size), (0, 0, 0, 0))     # a soft dark edge so the head reads over the ring
    shadow.putalpha(alpha.filter(ImageFilter.MaxFilter(3)).filter(ImageFilter.GaussianBlur(1.2))
                    .point(lambda v: v * 7 // 10))
    base.alpha_composite(shadow)
    base.alpha_composite(layer)
    return base


def logo_of(name, emblem, colour):
    """The team logo (FIT["logo"], RGBA): the name in capitals on a band of the character's colour, its emblem at the
    left."""
    w, h = FIT["logo"]
    ss = 3
    band = Image.new("RGBA", (w * ss, h * ss), (0, 0, 0, 0))
    x0, y0, x1, y1 = 30 * ss, 9 * ss, (w - 2) * ss, (h - 9) * ss
    ImageDraw.Draw(band).rounded_rectangle((x0, y0, x1, y1), 12 * ss, fill=(24, 24, 32, 255))
    gw, gh = x1 - x0 - 4 * ss, y1 - y0 - 4 * ss
    top, bottom = np.array(_shade(colour, 1.3), np.float32), np.array(_shade(colour, 0.75), np.float32)
    t = np.linspace(0, 1, gh)[:, None]
    rows = np.minimum(top * (1 - t) + bottom * t, 255).astype(np.uint8)
    grad = Image.fromarray(np.concatenate([np.repeat(rows[:, None, :], gw, 1),
                                           np.full((gh, gw, 1), 255, np.uint8)], 2), "RGBA")
    m = Image.new("L", (gw, gh), 0)
    ImageDraw.Draw(m).rounded_rectangle((0, 0, gw - 1, gh - 1), 10 * ss, fill=255)
    band.paste(grad, (x0 + 2 * ss, y0 + 2 * ss), m)
    band = band.resize((w, h), Image.LANCZOS)
    words = name.upper().split()
    options = [[" ".join(words)]]
    if len(words) > 1:                                          # or two lines, split nearest the middle
        k = min(range(1, len(words)), key=lambda k: abs(len(" ".join(words[:k])) - len(" ".join(words[k:]))))
        options.append([" ".join(words[:k]), " ".join(words[k:])])
    room_w, room_h, left = w - 5 - 52, 34, 52                   # the text box: right of the emblem, in the band
    probe = ImageDraw.Draw(Image.new("L", (1, 1)))

    def boxes(lines, size):
        f = open_font(size)
        return f, [probe.textbbox((0, 0), s, font=f, stroke_width=2) for s in lines]

    def best(lines):
        size = 20
        while size > 7:
            _, bs = boxes(lines, size)
            if max(b[2] - b[0] for b in bs) <= room_w and sum(b[3] - b[1] for b in bs) <= room_h:
                break
            size -= 1
        return size
    sizes = [best(o) for o in options]
    lines = options[0] if len(options) == 1 or sizes[0] + 2 >= sizes[1] else options[1]
    font, bs = boxes(lines, best(lines))
    y = h / 2 - sum(b[3] - b[1] for b in bs) / 2
    d = ImageDraw.Draw(band)
    for s, b in zip(lines, bs):
        d.text((left + room_w / 2 - (b[2] - b[0]) / 2 - b[0], y - b[1]), s, font=font, fill=(250, 250, 252, 255),
               stroke_width=2, stroke_fill=(24, 24, 32, 255))
        y += b[3] - b[1]
    out = Image.new("RGBA", (w, h), (0, 0, 0, 0))
    out.alpha_composite(band)
    out.alpha_composite(emblem.resize((h, h), Image.LANCZOS), (0, 0))
    return out


def model_art(mesh, name):
    """{"portrait", "lineup", "emblem", "logo"}: a captain's art drawn from its model (model_render.mesh)."""
    portrait = portrait_of(mesh)
    colour = main_colour(portrait)
    emblem = emblem_of(head_of(mesh, 76), colour)
    return {"portrait": portrait, "lineup": lineup_of(mesh), "emblem": emblem, "logo": logo_of(name, emblem, colour)}
