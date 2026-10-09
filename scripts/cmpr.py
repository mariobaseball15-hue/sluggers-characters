"""GX CMPR (S3TC/DXT1 in 8x8 tiles of four 4x4 blocks) encode/decode for icon pages.

Layout: 8x8 tiles in raster order; each tile holds four 8-byte blocks (TL, TR, BL, BR); a block is
u16 color0, u16 color1 (RGB565, big-endian) and 16 2-bit indices, MSB first, row by row. color0 >
color1 gives 4 opaque colors; otherwise 3 colors and index 3 = transparent.
"""
import struct
from PIL import Image


def _565(c):
    return ((c >> 11) & 31) * 255 // 31, ((c >> 5) & 63) * 255 // 63, (c & 31) * 255 // 31


def _to565(r, g, b):
    return ((r * 31 + 127) // 255) << 11 | ((g * 63 + 127) // 255) << 5 | ((b * 31 + 127) // 255)


def _palette(c0, c1):
    a, b = _565(c0), _565(c1)
    if c0 > c1:
        return [a + (255,), b + (255,),
                tuple((2 * x + y) // 3 for x, y in zip(a, b)) + (255,),
                tuple((x + 2 * y) // 3 for x, y in zip(a, b)) + (255,)]
    return [a + (255,), b + (255,), tuple((x + y) // 2 for x, y in zip(a, b)) + (255,), (0, 0, 0, 0)]


def _block_offset(width, bx, by):
    """Byte offset of the 4x4 block at block coords (bx, by)."""
    tx, ty = bx // 2, by // 2
    return ((ty * (width // 8) + tx) * 4 + (by % 2) * 2 + (bx % 2)) * 8


def decode(data, width, height):
    img = Image.new("RGBA", (width, height))
    px = img.load()
    for by in range(height // 4):
        for bx in range(width // 4):
            o = _block_offset(width, bx, by)
            c0, c1, bits = struct.unpack_from(">HHI", data, o)
            pal = _palette(c0, c1)
            for i in range(16):
                px[bx * 4 + i % 4, by * 4 + i // 4] = pal[(bits >> (30 - 2 * i)) & 3]
    return img


def _encode_block(pixels):
    """pixels: 16 RGBA tuples -> 8 bytes."""
    opaque = [p[:3] for p in pixels if p[3] >= 128]
    if not opaque:
        return struct.pack(">HHI", 0, 0, 0xFFFFFFFF)
    lum = lambda c: 299 * c[0] + 587 * c[1] + 114 * c[2]
    hi, lo_ = max(opaque, key=lum), min(opaque, key=lum)
    c_hi, c_lo = _to565(*hi), _to565(*lo_)
    transparent = len(opaque) < 16
    if transparent:            # 3-color mode needs color0 <= color1
        c0, c1 = min(c_hi, c_lo), max(c_hi, c_lo)
    else:
        c0, c1 = max(c_hi, c_lo), min(c_hi, c_lo)
        if c0 == c1:           # flat block: 3-color mode with both endpoints equal is still opaque
            c0, c1 = c1, c0
    pal = _palette(c0, c1)
    bits = 0
    for i, p in enumerate(pixels):
        if p[3] < 128:
            idx = 3
        else:
            choices = range(3) if c0 <= c1 else range(4)
            idx = min(choices, key=lambda k: sum((a - b) ** 2 for a, b in zip(p[:3], pal[k][:3])))
        bits |= idx << (30 - 2 * i)
    return struct.pack(">HHI", c0, c1, bits)


def encode_region(data, width, img, x0, y0):
    """Encode `img` (RGBA, size a multiple of 8 and placed on an 8-pixel boundary) into the page
    bytes `data` (bytearray) at (x0, y0)."""
    assert x0 % 8 == 0 and y0 % 8 == 0 and img.width % 8 == 0 and img.height % 8 == 0
    px = img.convert("RGBA").load()
    for by in range(img.height // 4):
        for bx in range(img.width // 4):
            block = [px[bx * 4 + i % 4, by * 4 + i // 4] for i in range(16)]
            o = _block_offset(width, x0 // 4 + bx, y0 // 4 + by)
            data[o:o + 8] = _encode_block(block)
