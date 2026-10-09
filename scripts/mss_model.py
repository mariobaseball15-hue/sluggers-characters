"""Read and write Mario Super Sluggers model blocks (the GPL/ACT/TEX/SKN bundle inside dt_na.dat).

Layout follows the format notes in refs/Sluggies-dat-tools/_docs/_docs_model_format/. All multi-byte
values are big-endian. Offsets kept in this module are relative to the model block unless named `abs`.

  python scripts/mss_model.py <dt_na.dat> <block offset> [length]     # print a summary
"""
import struct
import sys

GPL_MAGIC = 0x00B749E0

# Display state types seen in player models.
DS_TEXTURE, DS_FORMAT, DS_DRAW = 1, 3, 7
# Vertex attributes in type-3 order; two setting bits each, after two bits for the matrix index.
ATTRS = ("position", "normal", "color0", "color1") + tuple(f"tex{i}" for i in range(8))


def u8(b, o): return b[o]
def u16(b, o): return struct.unpack_from(">H", b, o)[0]
def u32(b, o): return struct.unpack_from(">I", b, o)[0]


def comp_size(quant):
    """Bytes per component: formats 4, 7 and 0xA are floats, the rest 16-bit (per the format notes)."""
    return 4 if quant >> 4 in (4, 7, 0xA) else 2


def dequant(raw, quant, comps, count):
    """Raw array -> list of tuples of floats."""
    fmt, div = quant >> 4, float(1 << (quant & 0xF))
    if comp_size(quant) == 4:
        vals = struct.unpack_from(">%df" % (count * comps), raw)
    elif fmt == 2:
        vals = [v / div for v in struct.unpack_from(">%dH" % (count * comps), raw)]
    else:
        vals = [v / div for v in struct.unpack_from(">%dh" % (count * comps), raw)]
    return [tuple(vals[i * comps:(i + 1) * comps]) for i in range(count)]


def quant16(values, quant):
    """Floats -> big-endian s16 with the quantization's divisor, clamped."""
    div = 1 << (quant & 0xF)
    out = bytearray()
    for v in values:
        q = int(round(v * div))
        out += struct.pack(">h", max(-32768, min(32767, q)))
    return bytes(out)


def vertex_format(setting):
    """Type-3 setting -> [(attribute, index_size)] in stream order (immediate data is not used by player models)."""
    s, fmt = setting >> 2, []
    for name in ATTRS:
        bits = s & 3
        if bits == 1:
            raise ValueError(f"immediate {name} attribute not supported")
        if bits:
            fmt.append((name, 1 if bits == 2 else 2))
        s >>= 2
    return fmt


def parse_prims(data, fmt):
    """Primitive list -> [(prim_type, [vertex dicts])]; stops at the first zero (NOP) byte."""
    out, o, stride = [], 0, sum(n for _, n in fmt)
    while o < len(data) and data[o]:
        ptype, count = data[o], u16(data, o + 1)
        o += 3
        verts = []
        for _ in range(count):
            v = {}
            for name, n in fmt:
                v[name] = data[o] if n == 1 else u16(data, o)
                o += n
            verts.append(v)
        out.append((ptype, verts))
    return out, o


def prim_triangles(prims):
    """[(type, verts)] -> list of triangles as vertex-dict triples in the game's winding."""
    tris = []
    for ptype, vs in prims:
        if ptype == 0x90:
            tris += [tuple(vs[i:i + 3]) for i in range(0, len(vs) - 2, 3)]
        elif ptype == 0x98:
            for i in range(len(vs) - 2):
                tris.append((vs[i], vs[i + 1], vs[i + 2]) if i % 2 == 0 else (vs[i + 1], vs[i], vs[i + 2]))
        elif ptype == 0x80:
            for i in range(0, len(vs) - 3, 4):
                tris += [(vs[i], vs[i + 1], vs[i + 2]), (vs[i], vs[i + 2], vs[i + 3])]
        else:
            raise ValueError(f"primitive type {ptype:#x}")
    return tris


class Array:
    """One attribute array header (position, color, uv or normal)."""

    def __init__(self, b, hdr, base, kind):
        self.hdr, self.kind = hdr, kind
        self.ptr = base + u32(b, hdr) if u32(b, hdr) else None
        self.count, self.quant, self.comps = u16(b, hdr + 4), u8(b, hdr + 6), u8(b, hdr + 7)
        if kind == "uv":
            self.palette_name_ptr, self.palette_ptr = u32(b, hdr + 8), u32(b, hdr + 12)
        if kind == "normal":
            self.ambient = struct.unpack_from(">f", b, hdr + 8)[0]

    def element_size(self):
        if self.kind == "color":
            return {0: 2, 1: 3, 2: 4, 3: 2, 4: 3, 5: 4}.get(self.quant >> 4, 4) if self.comps else 4
        return comp_size(self.quant) * self.comps

    def values(self, b):
        if self.kind == "color":
            return [bytes(b[self.ptr + i * self.element_size():][:self.element_size()]) for i in range(self.count)]
        return dequant(b[self.ptr:self.ptr + self.count * self.element_size()], self.quant, self.comps, self.count)


class DisplayState:
    def __init__(self, b, off, base):
        self.off = off
        self.type, self.setting = u8(b, off), u32(b, off + 4)
        self.pad = bytes(b[off + 1:off + 4])
        p = u32(b, off + 8)
        self.prim_ptr = base + p if p else None
        self.prim_size = u32(b, off + 12)

    @property
    def tag(self):
        """Type-7 settings are four-character draw-group tags such as 'Spec', 'RhSp', 'LhSp'."""
        raw = struct.pack(">I", self.setting)
        return raw.decode("latin-1") if self.type == DS_DRAW and all(32 <= c < 127 for c in raw) else None

    @property
    def texture(self):
        """Type-1 settings: (texture index, layer)."""
        return (self.setting & 0x1FFF, (self.setting >> 13) & 7) if self.type == DS_TEXTURE else None


class Submesh:
    def __init__(self, b, gpl, idx, hdr):
        self.idx = idx
        self.layout = gpl + u32(b, hdr)
        self.name = bytes(b[gpl + u32(b, hdr + 4):]).split(b"\0", 1)[0].decode("utf-8", "replace")
        L = self.layout
        self.position = Array(b, L + u32(b, L), L, "position")
        self.color = Array(b, L + u32(b, L + 4), L, "color") if u32(b, L + 4) else None
        self.uv_channels = u8(b, L + 0x14)
        self.uvs = [Array(b, L + u32(b, L + 8) + 16 * i, L, "uv") for i in range(self.uv_channels)] if u32(b, L + 8) else []
        self.normal = Array(b, L + u32(b, L + 12), L, "normal") if u32(b, L + 12) else None
        dh = L + u32(b, L + 0x10)
        self.display_header = dh
        self.ds_array = L + u32(b, dh + 4)
        self.states = [DisplayState(b, self.ds_array + 16 * i, L) for i in range(u16(b, dh + 8))]

    @property
    def skinned(self):
        return self.position.comps == 6

    def groups(self, b):
        """Walk display states; yield (state index, draw tag, texture binds, vertex format, triangles)."""
        fmt, binds = None, {}
        for i, ds in enumerate(self.states):
            if ds.type == DS_FORMAT:
                fmt = vertex_format(ds.setting)
            elif ds.type == DS_TEXTURE:
                binds[ds.texture[1]] = ds.texture[0]
            if ds.prim_ptr is not None and ds.prim_size:
                prims, _ = parse_prims(b[ds.prim_ptr:ds.prim_ptr + ds.prim_size], fmt)
                yield i, ds.tag, dict(binds), fmt, prim_triangles(prims)


class Texture:
    def __init__(self, b, off, tex):
        self.off = off
        self.image = tex + u32(b, off)
        self.palette = tex + u32(b, off + 4) if u32(b, off + 4) else None
        self.height, self.width = u16(b, off + 8), u16(b, off + 10)
        self.format = u8(b, off + 0x17)

    def payload_size(self):
        bpp = {0: 4, 1: 8, 2: 8, 3: 16, 4: 16, 5: 16, 6: 32, 8: 4, 9: 8, 10: 16, 14: 4}[self.format]
        bw, bh = {4: (8, 8), 8: (8, 4), 16: (4, 4), 32: (4, 4)}[bpp]
        if self.format == 14:
            bw, bh = 8, 8
        w, h = -(-self.width // bw) * bw, -(-self.height // bh) * bh
        return w * h * bpp // 8


class Skin:
    """SKN section. Destinations are byte offsets into submesh 0's position array."""

    def __init__(self, b, skn):
        self.off = skn
        n1, n2, na = u16(b, skn), u16(b, skn + 2), u16(b, skn + 4)
        self.quant = u8(b, skn + 6)
        self.stride = comp_size(self.quant) * 6
        self.memclr_ptr, self.memclr_size = u32(b, skn + 0x14), u32(b, skn + 0x18)
        self.flush = [u16(b, skn + u32(b, skn + 0x1C) + 2 * i) for i in range(u32(b, skn + 0x20))]
        a1, a2, aa = skn + u32(b, skn + 8), skn + u32(b, skn + 12), skn + u32(b, skn + 16)
        self.sk1 = [dict(src=u32(b, e + 0x30), dest=u32(b, e + 0x34), bone=u16(b, e + 0x38),
                         count=u16(b, e + 0x3A), voff=u8(b, e + 0x3C)) for e in (a1 + 0x40 * i for i in range(n1))]
        self.sk2 = [dict(src=u32(b, e + 0x60), weights=u32(b, e + 0x64), dest=u32(b, e + 0x68),
                         bones=(u16(b, e + 0x6C), u16(b, e + 0x6E)), count=u16(b, e + 0x70), voff=u8(b, e + 0x72))
                    for e in (a2 + 0x74 * i for i in range(n2))]
        self.acc = [dict(src=u32(b, e + 0x30), dest_idx=u32(b, e + 0x34), dest=u32(b, e + 0x38),
                         weights=u32(b, e + 0x3C), bone=u16(b, e + 0x40), count=u16(b, e + 0x42))
                    for e in (aa + 0x44 * i for i in range(na))]
        self.struct_end = aa + 0x44 * na - skn

    def write_end(self, b):
        """End of the bytes skinning writes each frame, relative to submesh 0's position data. It can run
        past the stored positions (memClr and accumulation slots), so nothing else may be placed before it."""
        ends = [self.memclr_ptr + self.memclr_size] if self.memclr_size else []
        # SK1/SK2 results go back by DMA in whole 32-byte lines (FUN_80597bec / FUN_80597b28).
        ends += [e["dest"] + (e["voff"] + e["count"] * self.stride + 31) // 32 * 32 for e in self.sk1 + self.sk2]
        for e in self.acc:
            if e["count"]:
                top = max(u16(b, self.off + e["dest_idx"] + 2 * k) for k in range(e["count"]))
                ends.append(e["dest"] + (top + 1) * self.stride)
        return max(ends, default=0)

    def influences(self, b):
        """Vertex slot -> {bone: weight/256}, from all entries."""
        out = {}
        for e in self.sk1:
            first = (e["dest"] + e["voff"]) // self.stride
            for k in range(e["count"]):
                out.setdefault(first + k, {})[e["bone"]] = 1.0
        for e in self.sk2:
            first = (e["dest"] + e["voff"]) // self.stride
            w = self.off + e["weights"]
            for k in range(e["count"]):
                d = out.setdefault(first + k, {})
                for j, bone in enumerate(e["bones"]):
                    d[bone] = d.get(bone, 0) + b[w + 2 * k + j] / 256
        for e in self.acc:
            base = e["dest"] // self.stride
            for k in range(e["count"]):
                slot = base + u16(b, self.off + e["dest_idx"] + 2 * k)
                d = out.setdefault(slot, {})
                d[e["bone"]] = d.get(e["bone"], 0) + b[self.off + e["weights"] + k] / 256
        return out


def act_bones(b, act):
    """ACT bone tree -> {bone id: (parent bone id or None, GEO id or None)}. Node pointers are ACT-relative."""
    out, stack = {}, [(u32(b, act + 0xC), None)]
    while stack:
        node, parent = stack.pop()
        while node:
            n = act + node
            bone, geo = u16(b, n + 0x16), u16(b, n + 0x14)
            out[bone] = (parent, None if geo == 0xFFFF else geo)
            if u32(b, n + 0x10):
                stack.append((u32(b, n + 0x10), bone))
            node = u32(b, n + 0x8)
    return out


class Model:
    def __init__(self, block):
        b = self.b = bytes(block)
        self.sections = dict(zip(("gpl", "act", "tex", "skn", "p5", "facial", "p7"),
                                 (u32(b, 4 * i) for i in range(1, 8))))
        g = self.gpl = self.sections["gpl"]
        assert u32(b, g) == GPL_MAGIC, "not a model block"
        self.user_data = bytes(b[g + u32(b, g + 8):][:u32(b, g + 4)])
        mh = g + u32(b, g + 0x10)
        self.submeshes = [Submesh(b, g, i, mh + 8 * i) for i in range(u32(b, g + 0xC))]
        t = self.sections["tex"]
        self.textures = [Texture(b, t + 4 + 0x20 * i, t) for i in range(u16(b, t))] if t else []
        self.skin = Skin(b, self.sections["skn"]) if self.sections["skn"] else None

    def section_spans(self):
        """Section name -> (start, end) using the next section start (or block end) as the end."""
        starts = sorted((v, k) for k, v in self.sections.items() if v)
        return {k: (v, starts[i + 1][0] if i + 1 < len(starts) else len(self.b)) for i, (v, k) in enumerate(starts)}


def read_block(dat_path, offset, length=None):
    with open(dat_path, "rb") as f:
        f.seek(offset)
        return f.read(length or 0x200000)


def summary(m):
    print("sections:", {k: f"{s:#x}-{e:#x} ({e - s})" for k, (s, e) in m.section_spans().items()})
    print("gpl user data:", m.user_data.hex(" ", 2))
    for s in m.submeshes:
        print(f"submesh {s.idx} {s.name}: layout {s.layout:#x} pos {s.position.count}x{s.position.comps} "
              f"q{s.position.quant:#x} @{s.position.ptr:#x}; uv {[(u.count, hex(u.quant)) for u in s.uvs]}; "
              f"color {s.color.count if s.color else 0}; normal {s.normal.count if s.normal else 0}"
              f"{' @%#x' % s.normal.ptr if s.normal else ''}")
        for i, tag, binds, fmt, tris in s.groups(m.b):
            print(f"   ds{i:<2} {tag} tex{binds} {len(tris)} tris {[f'{n}:{k}' for n, k in fmt]}")
        for i, ds in enumerate(s.states):
            print(f"   state {i:<2} type {ds.type} pad {ds.pad.hex()} setting {ds.setting:08x} "
                  f"prim {ds.prim_ptr and hex(ds.prim_ptr)} {ds.prim_size}")
    for i, t in enumerate(m.textures):
        print(f"tex {i}: {t.width}x{t.height} fmt {t.format} @{t.image:#x} ({t.payload_size()} bytes)")
    if m.skin:
        k = m.skin
        print(f"skin: {len(k.sk1)} SK1, {len(k.sk2)} SK2, {len(k.acc)} SKAcc, quant {k.quant:#x}, "
              f"memclr {k.memclr_ptr}+{k.memclr_size}, flush {len(k.flush)}, structs end {k.struct_end:#x}")


if __name__ == "__main__":
    dat, off = sys.argv[1], int(sys.argv[2], 0)
    blk = read_block(dat, off, int(sys.argv[3], 0) if len(sys.argv) > 3 else None)
    summary(Model(blk))
