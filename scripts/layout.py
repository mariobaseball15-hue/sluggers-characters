"""Menu layout files in dt_na.dat (dir 119: the select screens): a texture bank followed by a layout
container. Parse, edit, write back.

File:      +0x00 u32 0x20, +0x04 u32 container offset, +0x20 u16 texture count, texture descriptors
           (0x20 bytes) from +0x24, then image / palette data up to the container, then a short tail.
Descriptor: u32 image offset, u32 palette offset, u16 height, u16 width, +0x17 u8 GX format,
           +0x18 u16 palette entries, +0x1A u8 palette format. Image and palette offsets count from
           +0x20 (TEX_BASE), not the file start: the stock files' lowest palette offset is data_start - 4
           (dir 119 file 8: 0x1F20, file 19: 0x1800), i.e. the 32-aligned first data byte.
Container: u16 width 640, u16 height 448, u32 0x3C240002, u32 0x14, u32 resource rows (from the
           container), u32 end (from the container), u32 element count, u32 resource rows (from +0x14),
           one u32 per element (from +0x14), the elements back to back, the resource rows.
Element:   u32 flags, u32 n, u32 size, n u32 offsets from the element: a 0x10-byte header, then nodes.
Node:      u16 key count, u16 key stride, keys. Key: u16 flags, u16 time, u8 type (3 = element,
           4 = sprite), u8, u16 ref, s16 x, y (also at +0x18 and +0x1C), ...; type 3: +0x2C RGBA,
           +0x34 f32 scale x, y; type 4: +0x28 four s16 (x, y) corner offsets from the key (the stock sprites: -w/2, -h/2),
           +0x38 f32 scale x, y, +0x40 four RGBA (vertex colours).
Resource row: u16 texture page, u16 0, f32 v1, u1, v2, u2 (0x14 bytes).
"""
import struct

DESC, ROW = 0x20, 0x14
TEX_BASE = 0x20                  # descriptor image / palette offsets are relative to this
XY = (0x08, 0x18, 0x1C)


class Layout:
    def __init__(self, data):
        d = bytes(data)
        self.c = c = struct.unpack_from(">I", d, 4)[0]
        n_tex = struct.unpack_from(">H", d, 0x20)[0]
        self.head = bytearray(d[:0x24])
        self.descs = [bytearray(d[0x24 + i * DESC:0x24 + (i + 1) * DESC]) for i in range(n_tex)]
        self.data_start = 0x24 + n_tex * DESC
        self.data = bytearray(d[self.data_start:c])              # images and palettes
        hdr = struct.unpack_from(">7I", d, c)
        assert hdr[1] == 0x3C240002 and hdr[2] == 0x14, "not a layout container"
        base = c + 0x14
        count, rows_rel = hdr[5], hdr[6]
        offs = struct.unpack_from(f">{count}I", d, c + 0x1C)
        assert offs[0] == 8 + 4 * count and list(offs) == sorted(offs), "unexpected element table"
        self.chead = bytearray(d[c:c + 8])
        self.elements = []
        for k in range(count):
            size = struct.unpack_from(">I", d, base + offs[k] + 8)[0]
            end = offs[k + 1] if k + 1 < count else rows_rel
            assert offs[k] + size == end, f"gap after element 0x{k:X}"
            self.elements.append(bytearray(d[base + offs[k]:base + end]))
        n_rows, rows_len = struct.unpack_from(">II", d, base + rows_rel)
        assert rows_len == 8 + n_rows * ROW and base + rows_rel + rows_len == c + hdr[4]
        self.rows = [bytearray(d[base + rows_rel + 8 + i * ROW:base + rows_rel + 8 + (i + 1) * ROW])
                     for i in range(n_rows)]
        self.tail = bytes(d[c + hdr[4]:])

    # --- textures -----------------------------------------------------------------------------
    def add_texture(self, image, width, height, gx_format, template_page=0, palette=b"", palette_format=0):
        """Append a texture page; returns its page number. palette (u16 entries, big-endian) for the CI formats
        8 / 9 (palette_format 0 IA8, 1 RGB565, 2 RGB5A3), stored after the image."""
        desc = bytearray(self.descs[template_page])
        struct.pack_into(">IIHH", desc, 0, 0, 0, height, width)       # offsets fixed in to_bytes()
        desc[0x17] = gx_format
        struct.pack_into(">H", desc, 0x18, len(palette) // 2)
        desc[0x1A] = palette_format if palette else 0
        self.descs.append(desc)
        self.data += b"\0" * (-(self.data_start + len(self.data)) % 32)
        desc_data = len(self.data)
        self.data += image
        self._new_images = getattr(self, "_new_images", {})
        self._new_images[len(self.descs) - 1] = desc_data
        if palette:
            self.data += b"\0" * (-(self.data_start + len(self.data)) % 32)
            self._new_palettes = getattr(self, "_new_palettes", {})
            self._new_palettes[len(self.descs) - 1] = len(self.data)
            self.data += palette
        return len(self.descs) - 1

    def add_palette_page(self, page, palette, palette_format=None):
        """Another page over `page`'s image with its own palette (the stock atlases' way: one CI image, a palette per
        page). `page` must be one add_texture added. Returns the new page number."""
        new = getattr(self, "_new_images", {})
        assert page in new, "add_palette_page: the image must be one add_texture added"
        desc = bytearray(self.descs[page])
        struct.pack_into(">H", desc, 0x18, len(palette) // 2)
        if palette_format is not None:
            desc[0x1A] = palette_format
        self.descs.append(desc)
        k = len(self.descs) - 1
        new[k] = new[page]
        self.data += b"\0" * (-(self.data_start + len(self.data)) % 32)
        self._new_palettes = getattr(self, "_new_palettes", {})
        self._new_palettes[k] = len(self.data)
        self.data += palette
        return k

    def palette(self, page):
        """(offset of page's palette in self.data, entry count)."""
        pal, n = struct.unpack_from(">I", self.descs[page], 4)[0], struct.unpack_from(">H", self.descs[page], 0x18)[0]
        assert pal and n, f"page {page} has no palette"
        return TEX_BASE + pal - self.data_start, n

    def add_row(self, page, u1, v1, u2, v2):
        self.rows.append(bytearray(struct.pack(">HH4f", page, 0, v1, u1, v2, u2)))
        return len(self.rows) - 1

    # --- elements -----------------------------------------------------------------------------
    def nodes(self, k):
        """[[key offset in element k, ...] per node]."""
        e = self.elements[k]
        n = struct.unpack_from(">I", e, 4)[0]
        out = []
        for fo in struct.unpack_from(f">{n}I", e, 12)[1:]:
            cnt, stride = struct.unpack_from(">HH", e, fo)
            out.append([fo + 4 + j * stride for j in range(cnt)])
        return out

    def key_ref(self, k, key):
        return struct.unpack_from(">H", self.elements[k], key + 6)[0]

    def set_key_ref(self, k, key, ref):
        struct.pack_into(">H", self.elements[k], key + 6, ref)

    def move_key(self, k, key, dx, dy=0):
        e = self.elements[k]
        for o in XY:
            x, y = struct.unpack_from(">hh", e, key + o)
            struct.pack_into(">hh", e, key + o, x + dx, y + dy)

    def set_nodes(self, k, nodes):
        """Rebuild element k from node blobs (each: u16 count, u16 stride, keys); keeps its header."""
        e = self.elements[k]
        flags, n = struct.unpack_from(">II", e, 0)
        sub_off = struct.unpack_from(">I", e, 12)[0]
        sub = bytes(e[sub_off:sub_off + 0x10])
        head = 12 + 4 * (1 + len(nodes))
        offs, pos = [head], head + 0x10
        for blob in nodes:
            offs.append(pos)
            pos += len(blob)
        out = struct.pack(">III", flags, len(offs), pos) + struct.pack(f">{len(offs)}I", *offs) + sub
        self.elements[k] = bytearray(out + b"".join(nodes))

    def node_blobs(self, k):
        e = self.elements[k]
        n = struct.unpack_from(">I", e, 4)[0]
        offs = list(struct.unpack_from(f">{n}I", e, 12)) + [len(e)]
        return [bytes(e[offs[i]:offs[i + 1]]) for i in range(1, n)]

    def add_element(self, blob):
        self.elements.append(bytearray(blob))
        return len(self.elements) - 1

    # --- write --------------------------------------------------------------------------------
    def to_bytes(self):
        n_tex = len(self.descs)
        data_start = 0x24 + n_tex * DESC
        shift = data_start - self.data_start
        new = getattr(self, "_new_images", {})
        new_pal = getattr(self, "_new_palettes", {})
        descs = []
        for i, desc in enumerate(self.descs):
            desc = bytearray(desc)
            img, pal = struct.unpack_from(">II", desc, 0)
            if i in new:
                img = data_start + new[i] - TEX_BASE
                pal = data_start + new_pal[i] - TEX_BASE if i in new_pal else 0
            else:
                img, pal = img + shift if img else 0, pal + shift if pal else 0
            struct.pack_into(">II", desc, 0, img, pal)
            descs.append(bytes(desc))
        body = bytes(self.data) + b"\0" * (-(data_start + len(self.data)) % 32)
        c = data_start + len(body)
        count = len(self.elements)
        offs, pos = [], 8 + 4 * count
        for e in self.elements:
            offs.append(pos)
            pos += len(e)
        rows_rel = pos
        rows = struct.pack(">II", len(self.rows), 8 + len(self.rows) * ROW) + b"".join(self.rows)
        end = 0x14 + rows_rel + len(rows)
        cont = bytes(self.chead) + struct.pack(">5I", 0x14, 0x14 + rows_rel, end, count, rows_rel)
        cont += struct.pack(f">{count}I", *offs) + b"".join(self.elements) + rows
        head = bytearray(self.head)
        struct.pack_into(">I", head, 4, c)
        struct.pack_into(">H", head, 0x20, n_tex)
        return bytes(head) + b"".join(descs) + body + cont + self.tail


# CI8 atlas cells (dir 119 file 8's item icons, file 18's captain figures): koopa_items / starbits_roulette / captains
# (here, not in koopa_items: a build without the Koopalings' items still reads a stock captain's figure)
def ci8_cell(blob, rows_page, x, y, width=1024):
    """File offset of CI8 pixel (x, y) in an atlas whose descriptor image offset is rows_page."""
    tile = (y // 4) * (width // 8) + x // 8
    return 0x20 + rows_page + tile * 32 + (y % 4) * 8 + x % 8


def stock_icon(blob, row):
    """A stock item icon (dir 119 file 8 row 0xF3..0xF9: a 27 x 29 cell of a 1024 x 1024 CI8 atlas with
    its own RGB5A3 palette) -> RGBA image."""
    from PIL import Image
    lay = Layout(blob)
    page, _, v1, u1, v2, u2 = struct.unpack(">HH4f", lay.rows[row])
    desc = lay.descs[page]
    img_off, pal_off = struct.unpack_from(">II", desc, 0)
    h, w = struct.unpack_from(">HH", desc, 8)
    assert (w, h, desc[0x17], desc[0x1A]) == (1024, 1024, 9, 2), f"row 0x{row:X} is not a CI8 atlas cell"
    x0, y0, x1, y1 = (round(v * 1024) for v in (u1, v1, u2, v2))
    pal = struct.unpack_from(">256H", blob, 0x20 + pal_off)

    def rgba(v):
        if v & 0x8000:
            return ((v >> 10 & 31) * 255 // 31, (v >> 5 & 31) * 255 // 31, (v & 31) * 255 // 31, 255)
        return ((v >> 8 & 15) * 17, (v >> 4 & 15) * 17, (v & 15) * 17, (v >> 12 & 7) * 255 // 7)
    out = Image.new("RGBA", (x1 - x0, y1 - y0))
    px = out.load()
    for y in range(y0, y1):
        for x in range(x0, x1):
            px[x - x0, y - y0] = rgba(pal[blob[ci8_cell(blob, img_off, x, y)]])
    return out
