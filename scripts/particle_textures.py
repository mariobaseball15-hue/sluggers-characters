"""Decode the particle textures in a dt_na dir 0xA1 file (one per slot: 0xE0 header, texture at +0x80+[+0x84],
palette at +0x80+[+0x88], u16 w/h at +0x8C, GX format at +0x98, palette count/format at +0x9C) and
render a contact sheet: python scripts/particle_textures.py <file.bin> <sheet.png>. Slot 0x1A is a yellow star."""
import os, sys, struct
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))   # (not the main checkout's path: a worktree imported its modules)
from PIL import Image, ImageDraw
import cmpr

def rgb5a3(v):
    if v & 0x8000:
        return ((v >> 10 & 31) * 255 // 31, (v >> 5 & 31) * 255 // 31, (v & 31) * 255 // 31, 255)
    return ((v >> 8 & 15) * 17, (v >> 4 & 15) * 17, (v & 15) * 17, (v >> 12 & 7) * 255 // 7)

def rgb565(v):
    return ((v >> 11 & 31) * 255 // 31, (v >> 5 & 63) * 255 // 63, (v & 31) * 255 // 31, 255)

def ia8(v):
    return (v & 255, v & 255, v & 255, v >> 8)

TL = {0: ia8, 1: rgb565, 2: rgb5a3}
BLK = {0: (8, 8, 4), 1: (8, 4, 8), 2: (8, 4, 8), 3: (4, 4, 16), 4: (4, 4, 16), 5: (4, 4, 16), 8: (8, 8, 4), 9: (8, 4, 8)}

def decode(fmt, w, h, data, pal=None):
    if fmt == 0xE:
        return Image.frombytes("RGBA", (w, h), bytes(cmpr.decode(data, w, h))) if isinstance(cmpr.decode(data, w, h), (bytes, bytearray)) else cmpr.decode(data, w, h)
    bw, bh, bpp = BLK[fmt]
    img = Image.new("RGBA", (w, h))
    px = img.load(); pos = 0
    for by in range(0, h, bh):
        for bx in range(0, w, bw):
            for y in range(bh):
                for x in range(bw):
                    if bpp == 4:
                        v = data[pos // 2] >> (4 if pos % 2 == 0 else 0) & 15; pos += 1
                    elif bpp == 8:
                        v = data[pos // 2]; pos += 2
                    else:
                        v = struct.unpack(">H", data[pos // 2:pos // 2 + 2])[0]; pos += 4
                    if fmt == 0: c = (v * 17,) * 3 + (v * 17,)
                    elif fmt == 1: c = (v, v, v, v)
                    elif fmt == 2: c = ((v >> 4) * 17,) * 3 + ((v & 15) * 17,)
                    elif fmt == 3: c = ia8(v)
                    elif fmt == 4: c = rgb565(v)
                    elif fmt == 5: c = rgb5a3(v)
                    else: c = pal[v]
                    if bx + x < w and by + y < h: px[bx + x, by + y] = c
    return img

def slots(blob):
    offs = list(struct.unpack(">45I", blob[:180])) + [len(blob)]
    out = []
    for i in range(45):
        o = offs[i]
        if offs[i + 1] <= o: out.append(None); continue
        h = blob[o + 0x80:o + 0xA0]
        dofs, pofs = struct.unpack(">II", h[4:12]); w, hh = struct.unpack(">HH", h[12:16])
        fmt = struct.unpack(">I", h[0x18:0x1C])[0]; ncol, pfmt = struct.unpack(">HB", h[0x1C:0x1F])
        pal = None
        if fmt in (8, 9):
            pal = [TL.get(pfmt, rgb5a3)(struct.unpack(">H", blob[o + 0x80 + pofs + 2 * k:o + 0x80 + pofs + 2 * k + 2])[0]) for k in range(ncol)]
        try:
            size = {8: w * hh // 2, 9: w * hh, 0xE: w * hh // 2}.get(fmt, w * hh * BLK.get(fmt, (1, 1, 16))[2] // 8)
            img = decode(fmt, w, hh, blob[o + 0x80 + dofs:o + 0x80 + dofs + size], pal)
        except Exception as e:
            img = None
        out.append((i, fmt, w, hh, img))
    return out

if __name__ == "__main__":
    blob = open(sys.argv[1], "rb").read()
    sheet = Image.new("RGBA", (9 * 140, 5 * 160), (60, 60, 90, 255))
    dr = ImageDraw.Draw(sheet)
    for s in slots(blob):
        if not s: continue
        i, fmt, w, h, img = s
        x, y = (i % 9) * 140, (i // 9) * 160
        if img:
            bg = Image.new("RGBA", img.size, (60, 60, 90, 255)); bg.alpha_composite(img)
            sheet.paste(bg.resize((128, 128), Image.NEAREST), (x + 6, y + 22))
        dr.text((x + 6, y + 4), f"{i:#04x} f{fmt:x} {w}x{h}", fill=(255, 255, 255, 255))
    sheet.save(sys.argv[2])
