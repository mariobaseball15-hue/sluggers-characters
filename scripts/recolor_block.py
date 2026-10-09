"""Recolor one texture of a model block: color variants that share a model (Luma colors, like Yoshi's).

  python scripts/recolor_block.py <dt_na.dat> <block offset> <block length> <texture index> <hue> <out.bin>
      [--from-hue 60] [--hue-width 25] [--sat S] [--png preview.png] [--game base_folder out_folder]

Pixels whose hue is within --hue-width degrees of --from-hue (default yellow) and that are saturated are
moved to <hue> (degrees), keeping their brightness; --sat optionally sets their saturation (0-1);
--only-where-differs limits it to pixels that differ from a reference texture. The texture
is re-encoded in place, in its own format and size (scripts/build_model.py's wimgt encoder). With --game,
<out_folder> becomes a hard-linked copy of <base_folder> with the recolored block written over the original.
"""
import argparse
import colorsys
import os
import shutil
import sys
import tempfile

from PIL import Image

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from build_model import encode_texture, wimgt  # noqa: E402
from mss_model import Model, read_block  # noqa: E402
import subprocess  # noqa: E402


def decode(block, tex):
    """Texture -> RGBA image, via a TPL wrapper and wimgt."""
    tmp = tempfile.mkdtemp()
    try:
        payload = block[tex.image:tex.image + tex.payload_size()]
        # Minimal TPL: 1 image, header at 0x0C, image header at 0x20, data at 0x40.
        hdr = bytearray(0x40)
        hdr[0:4] = b"\x00\x20\xaf\x30"
        hdr[4:8] = (1).to_bytes(4, "big")
        hdr[8:12] = (0x0C).to_bytes(4, "big")
        hdr[0x0C:0x10] = (0x14).to_bytes(4, "big")
        hdr[0x14:0x16] = tex.height.to_bytes(2, "big")
        hdr[0x16:0x18] = tex.width.to_bytes(2, "big")
        hdr[0x18:0x1C] = tex.format.to_bytes(4, "big")
        hdr[0x1C:0x20] = (0x40).to_bytes(4, "big")
        tpl, png = os.path.join(tmp, "t.tpl"), os.path.join(tmp, "t.png")
        open(tpl, "wb").write(bytes(hdr[:0x14]) + bytes(hdr[0x14:0x40]) + payload)
        subprocess.run([wimgt(), "decode", "-q", "-o", "-d", png, tpl], check=True)
        return Image.open(png).convert("RGBA")
    finally:
        shutil.rmtree(tmp, ignore_errors=True)


def recolor(img, to_hue, from_hue, width, sat, only=None):
    px = img.load()
    mask = only.load() if only is not None else None
    for y in range(img.height):
        for x in range(img.width):
            r, g, b, a = px[x, y]
            if mask is not None:
                o = mask[x, y]
                if abs(o[0] - r) + abs(o[1] - g) + abs(o[2] - b) < 30:
                    continue  # same as the reference texture: not a team-color pixel
            h, s, v = colorsys.rgb_to_hsv(r / 255, g / 255, b / 255)
            d = abs((h * 360 - from_hue + 180) % 360 - 180)
            if s > 0.35 and d <= width:
                nr, ng, nb = colorsys.hsv_to_rgb(to_hue / 360, s if sat is None else sat, v)
                px[x, y] = (round(nr * 255), round(ng * 255), round(nb * 255), a)
    return img


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("dat")
    ap.add_argument("offset")
    ap.add_argument("length", type=int)
    ap.add_argument("texture", type=int)
    ap.add_argument("hue", type=float)
    ap.add_argument("out")
    ap.add_argument("--from-hue", type=float, default=60)
    ap.add_argument("--hue-width", type=float, default=25)
    ap.add_argument("--sat", type=float)
    ap.add_argument("--png")
    ap.add_argument("--only-where-differs", metavar="PNG",
                    help="recolor only pixels that differ from this texture (e.g. Hammer Bro's, to touch just "
                         "Fire Bro's team colors)")
    ap.add_argument("--game", nargs=2, metavar=("BASE", "OUT"))
    a = ap.parse_args()

    off = int(a.offset, 0)
    blk = bytearray(read_block(a.dat, off, a.length))
    m = Model(bytes(blk))
    t = m.textures[a.texture]
    ref = Image.open(a.only_where_differs).convert("RGBA") if a.only_where_differs else None
    img = recolor(decode(bytes(blk), t), a.hue, a.from_hue, a.hue_width, a.sat, ref)
    if a.png:
        os.makedirs(os.path.dirname(os.path.abspath(a.png)), exist_ok=True)
        img.save(a.png)
    blk[t.image:t.image + t.payload_size()] = encode_texture(img, t.format, t.payload_size())
    os.makedirs(os.path.dirname(os.path.abspath(a.out)), exist_ok=True)
    open(a.out, "wb").write(blk)
    print(f"RECOLOR tex {a.texture} ({t.width}x{t.height} fmt {t.format}) -> hue {a.hue}: {a.out}")

    if a.game:
        base, out = (os.path.abspath(p) for p in a.game)
        if os.path.exists(out):
            shutil.rmtree(out)
        for d, _, files in os.walk(base):
            rel = os.path.relpath(d, base)
            os.makedirs(os.path.join(out, rel), exist_ok=True)
            for f in files:
                s, dst = os.path.join(d, f), os.path.join(out, rel, f)
                (shutil.copyfile if (rel == "files" and f == "dt_na.dat") else os.link)(s, dst)
        with open(os.path.join(out, "files", "dt_na.dat"), "r+b") as f:
            f.seek(off)
            f.write(blk)
        print("GAME", out)


if __name__ == "__main__":
    main()
