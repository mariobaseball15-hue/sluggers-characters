"""Pack a textured OBJ into a rigid prop model block (the kind a character holds: bat, file 5 extra prop).

  python scripts/build_prop.py <config.json>

A prop block has one rigid submesh drawn by one bone, whose vertices are in the attach frame: for a held
prop (bat, Wario's Challenge magnet) the grip is at the origin and the prop runs along +Z. The block is
built fresh, sized to the model, from a template prop block (config "template", e.g. Luigi's bat):

- GPL: header, one GEO descriptor, a DOLayout with position (s16, config "pos_quant"), the template's
  color, two UV channels (both the atlas UVs, as in the bat), normals, the template's first draw group's
  display states (texture binds, format, draw) and one triangle list. Index size is 1 byte when every
  attribute has at most 255 entries, else 2.
- ACT: the template's, verbatim (its one bone owns submesh 0).
- TEX: the template's descriptors; texture 0 becomes the atlas (CMPR, config "atlas" size), the others keep
  their payloads (the bat's specular map).

The OBJ's materials are packed into one atlas (shelf packing, 2 px clamped borders). A material whose UVs
leave [0, 1] (tiling) is stretched to fit its tile once. OBJ space is Y-up like the game; config "grip"
(OBJ coordinates) moves to the origin, then "scale", then "rotate" ([["x", 90], ...], degrees, in order).
Normals are computed (angle threshold config "smooth_angle").

Output in config "out_dir": prop.bin (the block), entry.bin (the dt_na.dat file: 1-member container, block
at 0x20), atlas.png, report.json. The block passes Sluggies' BlockValidator.
"""
import json
import math
import os
import struct
import sys
from collections import defaultdict

import numpy as np
from PIL import Image

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from build_model import align, encode_texture, put16, put32, quant16, validate  # noqa: E402
from mss_model import DS_DRAW, Model, read_block  # noqa: E402

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
P = lambda p: os.path.join(ROOT, p)  # noqa: E731
NRM_QUANT = UV_QUANT = 0x3E  # s16, 14 fraction bits (as the bat)


def read_obj(path):
    """-> positions (n, 3), uvs (m, 2), faces [(material, [(v, vt), ...])], {material: texture path}."""
    v, vt, faces, mat = [], [], [], None
    mtl_file = None
    for line in open(path, encoding="utf8", errors="ignore"):
        s = line.split()
        if not s:
            continue
        if s[0] == "v":
            v.append(tuple(map(float, s[1:4])))
        elif s[0] == "vt":
            vt.append(tuple(map(float, s[1:3])))
        elif s[0] == "usemtl":
            mat = line.split(None, 1)[1].strip()
        elif s[0] == "mtllib":
            mtl_file = line.split(None, 1)[1].strip()
        elif s[0] == "f":
            corners = [(int(c.split("/")[0]) - 1, int(c.split("/")[1]) - 1) for c in s[1:]]
            for i in range(1, len(corners) - 1):  # fan
                faces.append((mat, [corners[0], corners[i], corners[i + 1]]))
    textures, cur = {}, None
    base = os.path.dirname(path)
    for line in open(os.path.join(base, mtl_file), encoding="utf8", errors="ignore"):
        s = line.split(None, 1)
        if not s:
            continue
        if s[0] == "newmtl":
            cur = s[1].strip()
        elif s[0] == "map_Kd":
            textures[cur] = os.path.join(base, s[1].strip().replace("\\", os.sep))
    return np.array(v), np.array(vt), faces, textures


def rotation(steps):
    r = np.eye(3)
    for axis, deg in steps:
        a = math.radians(deg)
        c, s = math.cos(a), math.sin(a)
        m = {"x": [[1, 0, 0], [0, c, -s], [0, s, c]],
             "y": [[c, 0, s], [0, 1, 0], [-s, 0, c]],
             "z": [[c, -s, 0], [s, c, 0], [0, 0, 1]]}[axis]
        r = np.array(m) @ r
    return r


def build_atlas(faces, uvs, textures, size, pad=2, tile_scale=1):
    """tile_scale: each texture is enlarged by this (nearest) first, so tiny pixel-art textures keep crisp
    colors through CMPR's 4x4 blocks instead of blending across tiles."""
    """-> atlas image, {material: (x0, y0, w, h, (umin, vmin, umax, vmax))} (pixels; UV normalization)."""
    used = defaultdict(set)
    for mat, corners in faces:
        used[mat].update(t for _, t in corners)
    tiles = {}
    for mat, ts in used.items():
        img = Image.open(textures[mat]).convert("RGBA")
        if tile_scale > 1:
            img = img.resize((img.width * tile_scale, img.height * tile_scale), Image.NEAREST)
        u, v = uvs[list(ts), 0], uvs[list(ts), 1]
        rng = (min(0.0, u.min()), min(0.0, v.min()), max(1.0, u.max()), max(1.0, v.max()))
        tiles[mat] = (img, rng)
    order = sorted(tiles, key=lambda m: -tiles[m][0].height)
    atlas = Image.new("RGBA", (size, size))
    place, x, y, row_h = {}, 0, 0, 0
    for mat in order:
        img, rng = tiles[mat]
        w, h = img.width + 2 * pad, img.height + 2 * pad
        if x + w > size:
            x, y, row_h = 0, y + row_h, 0
        if y + h > size:
            raise ValueError(f"atlas {size}x{size} too small for {len(order)} textures")
        # clamped border: stretch the edge pixels into the padding
        big = img.resize((img.width + 2 * pad, img.height + 2 * pad), Image.NEAREST)
        big.paste(img, (pad, pad))
        for k in range(pad):
            big.paste(img.crop((0, 0, img.width, 1)).resize((img.width, 1)), (pad, k))
            big.paste(img.crop((0, img.height - 1, img.width, img.height)), (pad, pad + img.height + k))
        for k in range(pad):
            col = big.crop((pad, 0, pad + 1, big.height))
            big.paste(col, (k, 0))
            col = big.crop((pad + img.width - 1, 0, pad + img.width, big.height))
            big.paste(col, (pad + img.width + k, 0))
        atlas.paste(big, (x, y))
        place[mat] = (x + pad, y + pad, img.width, img.height, rng)
        x += w
        row_h = max(row_h, h)
    return atlas.convert("RGB").convert("RGBA"), place


def atlas_uv(uv, tile, size):
    """OBJ uv (V up) -> game atlas uv (V down), inset half a texel."""
    x0, y0, w, h, (umin, vmin, umax, vmax) = tile
    u = (uv[0] - umin) / (umax - umin)
    v = (uv[1] - vmin) / (vmax - vmin)
    px = x0 + 0.5 + u * (w - 1)
    py = y0 + 0.5 + (1 - v) * (h - 1)
    return px / size, py / size


def smooth_normals(pos, tris, angle):
    """Per-corner normals: area-weighted face normals of the faces at that position within `angle`."""
    fn = np.cross(pos[tris[:, 1]] - pos[tris[:, 0]], pos[tris[:, 2]] - pos[tris[:, 0]])
    area_n = fn
    unit = fn / np.maximum(np.linalg.norm(fn, axis=1, keepdims=True), 1e-12)
    at = defaultdict(list)
    for f, t in enumerate(tris):
        for p in t:
            at[p].append(f)
    cos_t = math.cos(math.radians(angle))
    out = np.zeros((len(tris), 3, 3))
    for f, t in enumerate(tris):
        for k, p in enumerate(t):
            acc = sum(area_n[g] for g in at[p] if unit[g] @ unit[f] >= cos_t)
            out[f, k] = acc / max(np.linalg.norm(acc), 1e-12)
    return out


class Indexer:
    def __init__(self):
        self.items, self.index = [], {}

    def __call__(self, key, value=None):
        if key not in self.index:
            self.index[key] = len(self.items)
            self.items.append(key if value is None else value)
        return self.index[key]


def build_gpl(tb, tm, positions, normals, uvs, tris, pos_quant, name):
    """GPL section bytes (section-relative offsets). tris: [((p, n, t) x3)] in game (clockwise) winding."""
    sm = tm.submeshes[0]
    gpl_base = tm.gpl
    lay_rel = 0x1C                       # DOLayout right after the GPL header and the GEO descriptor
    out = bytearray(0x1C + 0x18)
    L = gpl_base + lay_rel              # block offset of the DOLayout (for block-relative alignment)

    def here():                          # offset relative to the DOLayout
        return len(out) - lay_rel

    def pad_block(a):                    # pad so the next byte is aligned relative to the block
        while (L + here()) % a:
            out.append(0)

    def pad4():
        while len(out) % 4:
            out.append(0)

    # positions
    pos_hdr = here()
    out += bytes(8)
    pos_data = here()
    out += quant16(positions.reshape(-1), pos_quant)
    pad4()
    # color (template's single constant color)
    color_hdr = here()
    out += tb[sm.color.hdr:sm.color.hdr + 8]
    color_data = here()
    out += tb[sm.color.ptr:sm.color.ptr + max(4, sm.color.count * sm.color.element_size())]
    pad4()
    # two UV channels sharing one data array layout (the bat stores them separately; so do we)
    uv_hdr = here()
    out += bytes(32)
    uv_ptrs = []
    for _ in range(2):
        uv_ptrs.append(here())
        out += quant16(uvs.reshape(-1), UV_QUANT)
        pad4()
    normal_hdr = here()
    out += tb[sm.normal.hdr:sm.normal.hdr + 12]
    normal_data = here()
    out += quant16(normals.reshape(-1), NRM_QUANT)
    pad4()
    # display states: the template's states up to and including its first draw group
    states = []
    for ds in sm.states:
        states.append(ds)
        if ds.type == DS_DRAW:
            break
    disp_hdr = here()
    out += bytes(12)
    ds_arr = here()
    for ds in states:
        out += tb[ds.off:ds.off + 16]
    # vertex format and primitive list
    wide = max(len(positions), len(normals), len(uvs)) > 255
    size = 2 if wide else 1
    fmt_setting = 0x3C3C if wide else 0x2828
    prim = bytearray()
    prim += bytes([0x90]) + struct.pack(">H", 3 * len(tris))
    for tri in tris:
        for p, n, t in tri:
            for val in (p, n, t, t):
                prim += val.to_bytes(size, "big")
    prim += bytes(align(len(prim)) - len(prim))
    pad_block(32)
    prim_at = here()
    out += prim
    tpl_name = here()
    out += f"{name}.tpl".encode() + b"\0"
    mesh_name = len(out)
    out += name.encode() + b"\0"
    while len(out) % 32:
        out.append(0)

    rel = lambda a: a + lay_rel          # layout-relative -> section-relative  # noqa: E731
    # GPL header + GEO descriptor
    put32(out, 0, 0x00B749E0)
    put32(out, 0x0C, 1)
    put32(out, 0x10, 0x14)
    put32(out, 0x14, lay_rel)
    put32(out, 0x18, mesh_name)
    # DOLayout
    for k, a in enumerate((pos_hdr, color_hdr, uv_hdr, normal_hdr, disp_hdr)):
        put32(out, lay_rel + 4 * k, a)
    out[lay_rel + 0x14] = 2
    # array headers
    put32(out, rel(pos_hdr), pos_data)
    put16(out, rel(pos_hdr) + 4, len(positions))
    out[rel(pos_hdr) + 6], out[rel(pos_hdr) + 7] = pos_quant, 3
    put32(out, rel(color_hdr), color_data)
    for k in range(2):
        h = rel(uv_hdr) + 16 * k
        put32(out, h, uv_ptrs[k])
        put16(out, h + 4, len(uvs))
        out[h + 6], out[h + 7] = UV_QUANT, 2
        put32(out, h + 8, tpl_name)
        put32(out, h + 12, 0)
    put32(out, rel(normal_hdr), normal_data)
    put16(out, rel(normal_hdr) + 4, len(normals))
    out[rel(normal_hdr) + 6], out[rel(normal_hdr) + 7] = NRM_QUANT, 3
    put32(out, rel(disp_hdr), prim_at)
    put32(out, rel(disp_hdr) + 4, ds_arr)
    put16(out, rel(disp_hdr) + 8, len(states))
    for i, ds in enumerate(states):
        o = rel(ds_arr) + 16 * i
        if ds.type == 3:
            put32(out, o + 4, fmt_setting)
        if ds.type == DS_DRAW:
            put32(out, o + 8, prim_at)
            put32(out, o + 12, len(prim))
        else:
            put32(out, o + 8, 0)
            put32(out, o + 12, 0)
    return bytes(out), dict(positions=len(positions), normals=len(normals), uvs=len(uvs), tris=len(tris),
                            index_bytes=size, states=len(states))


def build_tex(tb, tm, atlas_payload, atlas_size):
    """TEX section: template descriptors, texture 0 = atlas; payloads re-laid on 32-byte boundaries."""
    t0 = tm.sections["tex"]
    n = struct.unpack_from(">H", tb, t0)[0]
    out = bytearray(tb[t0:t0 + 4 + 0x20 * n])
    while len(out) % 32:
        out.append(0)
    for i, t in enumerate(tm.textures):
        d = 4 + 0x20 * i
        payload = atlas_payload if i == 0 else tb[t.image:t.image + t.payload_size()]
        put32(out, d, len(out))
        if i == 0:
            put16(out, d + 8, atlas_size)
            put16(out, d + 10, atlas_size)
            out[d + 0x17] = 0x0E
        out += payload
        while len(out) % 32:
            out.append(0)
    return bytes(out)


def main():
    pack(json.load(open(os.path.abspath(sys.argv[1]))))


def pack(cfg):
    """The config -> (block, report); writes the outputs to cfg["out_dir"] (main; own_models calls it too)."""
    out_dir = P(cfg["out_dir"])
    os.makedirs(out_dir, exist_ok=True)
    t = cfg["template"]
    tb = read_block(P(t["dat"]), t["offset"], t["length"])
    tm = Model(tb)

    pos, vt, faces, textures = read_obj(P(cfg["source"]))
    atlas_size = cfg.get("atlas", 128)
    k = cfg.get("tile_scale", 1)
    atlas, place = build_atlas(faces, vt, textures, atlas_size, pad=cfg.get("pad", 2), tile_scale=k)
    atlas.save(os.path.join(out_dir, "atlas.png"))

    r = rotation(cfg.get("rotate", []))
    gpos = ((pos - np.array(cfg["grip"])) * cfg.get("scale", 1.0)) @ r.T
    tri_idx = np.array([[c[0] for c in corners] for _, corners in faces])
    corner_n = smooth_normals(gpos, tri_idx, cfg.get("smooth_angle", 50))

    nrm_ix, uv_ix = Indexer(), Indexer()
    tris = []
    for f, (mat, corners) in enumerate(faces):
        tri = []
        for k, (p, tix) in enumerate(corners):
            n = tuple(np.round(corner_n[f, k], 4))
            uv = atlas_uv(vt[tix], place[mat], atlas_size)
            tri.append((p, nrm_ix(n), uv_ix(tuple(round(c, 5) for c in uv))))
        tris.append((tri[0], tri[2], tri[1]))    # OBJ counter-clockwise -> game clockwise
    used = sorted({p for tri in tris for p, _, _ in tri})
    remap = {p: i for i, p in enumerate(used)}
    tris = [tuple((remap[p], n, u) for p, n, u in tri) for tri in tris]
    positions = gpos[used]
    lim = 32767 / (1 << (cfg.get("pos_quant", 0x3B) & 0xF))
    if np.abs(positions).max() > lim:
        raise ValueError(f"positions reach {np.abs(positions).max():.2f}, quantization limit {lim:.2f}")

    gpl, gpl_report = build_gpl(tb, tm, positions, np.array(nrm_ix.items), np.array(uv_ix.items), tris,
                                cfg.get("pos_quant", 0x3B), cfg["name"])
    act = tb[tm.sections["act"]:tm.sections["tex"]]
    tex = build_tex(tb, tm, encode_texture(atlas, 0x0E, atlas_size * atlas_size // 2), atlas_size)
    header = bytearray(0x20)
    gpl_at = 0x20
    act_at = gpl_at + len(gpl)
    tex_at = align(act_at + len(act))
    put32(header, 4, gpl_at)
    put32(header, 8, act_at)
    put32(header, 12, tex_at)
    block = bytes(header) + gpl + act + bytes(tex_at - act_at - len(act)) + tex
    result = validate(block) if cfg.get("validate", True) else {}   # own_models: only where the validator is
    Model(block)  # parses back

    entry = struct.pack(">II", 1, 0x20) + bytes(0x18) + block
    open(os.path.join(out_dir, "prop.bin"), "wb").write(block)
    open(os.path.join(out_dir, "entry.bin"), "wb").write(entry)
    bounds = [positions.min(0).round(3).tolist(), positions.max(0).round(3).tolist()]
    report = dict(block_bytes=len(block), entry_bytes=len(entry), gpl=gpl_report, bounds=bounds,
                  atlas=atlas_size, validator=result.get("facts", {}).get("alignment"))
    json.dump(report, open(os.path.join(out_dir, "report.json"), "w"), indent=1, default=str)
    print(f"PROP {cfg['name']}: {len(block)} bytes, {gpl_report}, bounds {bounds}")
    return block, report


if __name__ == "__main__":
    main()
