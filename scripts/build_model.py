"""Pack a rigged custom model into a donor character's model blocks, keeping the donor's binary contract.

  python scripts/build_model.py <config.json> [--game <out dir>]

Input is the JSON from scripts/blender/export_mesh_data.py (one file per LOD: game-space positions, normals,
UVs, triangles, materials and weights on donor bone ids). For each LOD in config["pack"]["lods"] this starts
from the donor block and:

- GPL: rewrites submesh 0 (the skinned body) inside the region it already occupies: a new position buffer,
  color and UV arrays, and primitive lists. Every display state record is kept in place; only primitive
  pointers and sizes change. Draw groups the custom model does not use get a 32-byte list of GX NOPs.
  Other submeshes (e.g. Daisy's crown) keep their data, with their primitive bytes zeroed so they draw nothing.
- SKN: rebuilds skinning from the custom weights with the vanilla layout rules: SK1/SK2 destinations start on
  32-byte cache lines and never share one, sources mirror the position buffer at VAR_DATA_OFF + destination,
  every variable array is 32-byte aligned, 3-bone vertices are SK2 plus an SKAcc supplement.
- TEX: re-encodes configured texture slots in place at the slot's size and format (wimgt), and can rebind
  draw groups to a different slot.
- Facial poses: clears the header pointer; the donor's poses address the donor's vertices.

Section starts and the block length stay the donor's. Output: <out>/<lod>.bin and <out>/report.json.
With --game, <out dir> becomes a copy of config["pack"]["game"] (hard links, dt_na.dat copied) with the
blocks written over the donor's and quick boot in main.dol (scripts/quickboot.py; --no-quickboot skips it).
Quick boot stops at captain select unless config["pack"]["quickboot"] passes other quickboot.apply options,
e.g. {"mode": "game", "captains": ["Daisy", "Bowser"], "teams": [[...], [...]]} to start a game directly.
"""
import argparse
import json
import os
import shutil
import struct
import subprocess
import sys
import tempfile
from collections import Counter, defaultdict

from PIL import Image

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from mss_model import DS_DRAW, DS_TEXTURE, Model, act_bones, quant16, read_block  # noqa: E402

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
NOP_LIST = bytes(32)
MAX_TRIS_PER_PRIM = 0xFFFF // 3


def P(p):
    return os.path.join(ROOT, p)


def align(n, a=32):
    return (n + a - 1) & ~(a - 1)


def put32(buf, off, v):
    struct.pack_into(">I", buf, off, v)


def put16(buf, off, v):
    struct.pack_into(">H", buf, off, v)


# ---------------------------------------------------------------------------------------------- skinning

def quantize_weights(w, max_bones):
    """{bone: weight} -> [(bone, units)] with units summing to 256, largest first."""
    items = sorted(((v, int(k)) for k, v in w.items() if v > 0), reverse=True)[:max_bones]
    if not items:
        raise ValueError("vertex without weights")
    total = sum(v for v, _ in items)
    exact = [v / total * 256 for v, _ in items]
    units = [int(x) for x in exact]
    for i in sorted(range(len(units)), key=lambda i: exact[i] - units[i], reverse=True)[:256 - sum(units)]:
        units[i] += 1
    return sorted(((b, n) for (_, b), n in zip(items, units) if n), key=lambda t: -t[1])


# Entry shapes every vanilla model keeps (175 skinned models): SK1/SK2 entries have at least 3 vertices,
# and their source arrays fit the deformer's locked-cache buffers (SK1 <= 8180 bytes, SK2 <= 4088).
# Entries of 1-2 vertices crash the SK1 paired-single loop (invalid read past 0xE0000000).
MIN_ENTRY = 3
MAX_ENTRY_BYTES = {"sk1": 8180, "sk2": 4088}


def shape_entries(kind, members, stride):
    """Split an entry to the size cap, then pad short pieces with repeats of their first vertex (extra
    slots that carry the same bind data and weights; no primitive references them)."""
    cap = (MAX_ENTRY_BYTES[kind] - (stride - 4)) // stride    # worst-case vertex offset is stride - 4
    pieces = [members[i:i + cap] for i in range(0, len(members), cap)]
    return [p + [p[0]] * (MIN_ENTRY - len(p)) if len(p) < MIN_ENTRY else p for p in pieces]


def layout_skin(weights, stride):
    """Assign position-buffer slots. weights: per vertex [(bone, units)].

    Returns (slot per vertex, number of slots, SK entries in destination order, SKAcc supplements by bone).
    Each entry's "slots" lists (slot, vertex) for every slot it writes, padding repeats included.
    """
    sk1, sk2, acc = defaultdict(list), defaultdict(list), defaultdict(list)
    for vi, w in enumerate(weights):
        if len(w) == 1:
            sk1[w[0][0]].append((vi,))
            continue
        (b1, w1), (b2, w2) = sorted(w[:2])
        sk2[(b1, b2)].append((vi, w1, w2))
        for b, n in w[2:]:
            acc[b].append((vi, n))
    entries = [("sk1", b, piece) for b, m in sorted(sk1.items()) for piece in shape_entries("sk1", m, stride)]
    entries += [("sk2", p, piece) for p, m in sorted(sk2.items()) for piece in shape_entries("sk2", m, stride)]
    slot, cursor, placed = [None] * len(weights), 0, []
    for kind, key, members in entries:
        line = align(cursor)                    # each entry owns its cache lines
        first = -(-line // stride)              # first whole vertex slot at or after the line start
        for k, m in enumerate(members):
            if slot[m[0]] is None:
                slot[m[0]] = first + k
        placed.append(dict(kind=kind, key=key, dest=line, voff=first * stride - line, first=first, members=members,
                           slots=[(first + k, m[0]) for k, m in enumerate(members)]))
        cursor = (first + len(members)) * stride
    return slot, cursor // stride, placed, acc


def flush_indices(acc_slots, stride):
    """One vertex index per cache line that SKAcc writes into: the first slot starting in that line."""
    lines = sorted({ln for s in acc_slots for ln in range(s * stride // 32, (s * stride + stride - 1) // 32 + 1)})
    return [-(-(ln * 32) // stride) for ln in lines]


def build_skin(quant, stride, placed, acc, slot, pos_bytes):
    """SKN section bytes."""
    n1 = sum(e["kind"] == "sk1" for e in placed)
    n2 = len(placed) - n1
    acc_bones = sorted(acc)
    a1 = 0x24
    a2 = a1 + 0x40 * n1
    aa = a2 + 0x74 * n2
    var = align(aa + 0x44 * len(acc_bones))
    buf = bytearray(var)
    buf += pos_bytes + bytes(align(len(pos_bytes)) - len(pos_bytes))   # source mirror of the position buffer

    def array(data):
        off = len(buf)
        buf.extend(data + bytes(align(len(data)) - len(data)))
        return off

    acc_slots = [slot[vi] for b in acc_bones for vi, _ in acc[b]]
    flush = flush_indices(acc_slots, stride)
    flush_ptr = array(b"".join(struct.pack(">H", i) for i in flush)) if flush else 0

    i1 = i2 = 0
    for e in placed:
        if e["kind"] == "sk1":
            o = a1 + 0x40 * i1
            i1 += 1
            put32(buf, o + 0x30, var + e["dest"])
            put32(buf, o + 0x34, e["dest"])
            put16(buf, o + 0x38, e["key"])
            put16(buf, o + 0x3A, len(e["members"]))
            buf[o + 0x3C] = e["voff"]
        else:
            o = a2 + 0x74 * i2
            i2 += 1
            w = array(bytes(x for _, w1, w2 in e["members"] for x in (w1, w2)))
            put32(buf, o + 0x60, var + e["dest"])
            put32(buf, o + 0x64, w)
            put32(buf, o + 0x68, e["dest"])
            put16(buf, o + 0x6C, e["key"][0])
            put16(buf, o + 0x6E, e["key"][1])
            put16(buf, o + 0x70, len(e["members"]))
            buf[o + 0x72] = e["voff"]
    for i, bone in enumerate(acc_bones):
        o = aa + 0x44 * i
        members = acc[bone]
        src = array(b"".join(pos_bytes[slot[vi] * stride:(slot[vi] + 1) * stride] for vi, _ in members))
        dst = array(b"".join(struct.pack(">H", slot[vi]) for vi, _ in members))
        wts = array(bytes(n for _, n in members))
        put32(buf, o + 0x30, src)
        put32(buf, o + 0x34, dst)
        put32(buf, o + 0x38, 0)
        put32(buf, o + 0x3C, wts)
        put16(buf, o + 0x40, bone)
        put16(buf, o + 0x42, len(members))

    put16(buf, 0, n1)
    put16(buf, 2, n2)
    put16(buf, 4, len(acc_bones))
    buf[6] = quant
    put32(buf, 0x08, a1)
    put32(buf, 0x0C, a2)
    put32(buf, 0x10, aa)
    put32(buf, 0x14, 0)          # memClr: no accumulation-only slots, every vertex has an SK1/SK2 entry
    put32(buf, 0x18, 0)
    put32(buf, 0x1C, flush_ptr)
    put32(buf, 0x20, len(flush))
    return bytes(buf)


# ---------------------------------------------------------------------------------------------- geometry

def donor_groups(m, sm):
    """Draw state index -> {tag, texture bind state index for layer 0, dominant color index, vertex format}."""
    out, bind_state = {}, None
    for i, ds in enumerate(sm.states):
        if ds.type == DS_TEXTURE and ds.texture[1] == 0:
            bind_state = i
    groups = {i: (tag, fmt, tris) for i, tag, _, fmt, tris in sm.groups(m.b)}
    bind_state = None
    for i, ds in enumerate(sm.states):
        if ds.type == DS_TEXTURE and ds.texture[1] == 0:
            bind_state = i
        if i in groups:
            tag, fmt, tris = groups[i]
            colors = Counter(v.get("color0") for t in tris for v in t)
            out[i] = dict(tag=tag, fmt=fmt, bind=bind_state, color=colors.most_common(1)[0][0], tris=tris)
    return out


def hand_bones(m, groups, draw_index):
    """Bones whose donor vertices are mostly drawn by this group (dominant bone per vertex)."""
    infl = m.skin.influences(m.b)
    dom = {s: max(w.items(), key=lambda x: x[1])[0] for s, w in infl.items()}
    total, inside = Counter(), Counter()
    for i, g in groups.items():
        slots = {v["position"] for t in g["tris"] for v in t}
        for s in slots:
            if s in dom:
                total[dom[s]] += 1
                if i == draw_index:
                    inside[dom[s]] += 1
    return {b for b in inside if inside[b] / total[b] >= 0.5}


def strips(tris):
    """Triangles of corner keys (game winding) -> [[corner, ...], ...] triangle strips, greedily: a strip grows while
    an unused triangle shares its last edge with the winding the strip's parity needs (GX strips alternate). Every
    triangle ends up in exactly one strip; a lone one is a 3-corner strip."""
    from collections import defaultdict
    by_edge = defaultdict(list)
    for k, t in enumerate(tris):
        for a, b in ((0, 1), (1, 2), (2, 0)):
            by_edge[(t[a], t[b])].append(k)            # directed edge a->b in this triangle's winding
    used = [False] * len(tris)
    out = []
    for k, t in enumerate(tris):
        if used[k]:
            continue
        used[k] = True
        s = [t[0], t[1], t[2]]
        while True:
            # triangle n of a strip is (s[n], s[n+1], s[n+2]) for even n, (s[n+1], s[n], s[n+2]) for odd n; the next
            # one (n = len(s) - 2) needs the directed edge (s[-1], s[-2]) if n is odd... i.e. its first two corners
            n = len(s) - 2
            a, b = (s[-2], s[-1]) if n % 2 == 0 else (s[-1], s[-2])
            nxt = None
            for j in by_edge.get((a, b), ()):
                if not used[j]:
                    nxt = j
                    break
            if nxt is None:
                break
            tj = tris[nxt]
            i = next(i for i in range(3) if (tj[i], tj[(i + 1) % 3]) == (a, b))
            used[nxt] = True
            s.append(tj[(i + 2) % 3])
        out.append(s)
    return out


def prim_list(tris, fmt, color, use_strips=False):
    """Triangles of (slot, uv index) corners, in game winding -> 32-byte padded GX list. use_strips: triangle strips
    (0x98, as the game's own parts are packed: about half the bytes; model_import's rebuilds), else one triangle
    list (0x90; build_model's configs, unchanged)."""
    def corner(slot, uv):
        v = bytearray()
        for name, size in fmt:
            val = {"position": slot, "normal": slot, "color0": color}.get(name)
            if val is None and name.startswith("tex"):
                val = uv
            if val is None or val >= 1 << (8 * size):
                raise ValueError(f"cannot encode {name}={val} in {size} byte(s)")
            v += val.to_bytes(size, "big")
        return bytes(v)
    out = bytearray()
    if use_strips:
        for s in strips([tuple(t) for t in tris]):
            for start in range(0, len(s) - 2, 0xFFF0):
                part = s[start:start + 0xFFF0 + 2]
                if start % 2:                          # (never: 0xFFF0 is even, so each part keeps its parity)
                    raise ValueError("strip split on an odd triangle")
                out += bytes([0x98]) + struct.pack(">H", len(part))
                for slot, uv in part:
                    out += corner(slot, uv)
        return bytes(out) + bytes(align(len(out)) - len(out))
    for start in range(0, len(tris), MAX_TRIS_PER_PRIM):
        chunk = tris[start:start + MAX_TRIS_PER_PRIM]
        out += bytes([0x90]) + struct.pack(">H", 3 * len(chunk))
        for tri in chunk:
            for slot, uv in tri:
                out += corner(slot, uv)
    return bytes(out) + bytes(align(len(out)) - len(out))


def region_end(m, start):
    """First structure after `start` that belongs to something else (next submesh, names, user data, ACT)."""
    b, g = m.b, m.gpl
    mh = g + struct.unpack_from(">I", b, g + 0x10)[0]
    cands = [s.layout for s in m.submeshes] + [m.gpl + struct.unpack_from(">I", b, g + 8)[0], m.sections["act"]]
    cands += [g + struct.unpack_from(">I", b, mh + 8 * i + 4)[0] for i in range(len(m.submeshes))]
    return min(c for c in cands if c > start)


def build_body(m, sm, pos_bytes, nslots, uv_data, group_lists, rebinds, write_end):
    """Rewrite submesh 0's region in `blk`: returns (region bytes, region start, report).

    write_end: end of the skinning write window relative to the position data. The arrays after the
    positions start at or after it, and never earlier than the donor's own next array."""
    b, L = m.b, sm.layout
    end = region_end(m, L)
    out = bytearray(0x18)

    def here():
        return L + len(out)

    def pad_to(a):
        out.extend(bytes(align(here(), a) - here()))

    pos_hdr = here()
    out += b[sm.position.hdr:sm.position.hdr + 8]
    pad_to(32)
    pos_data = here()
    out += pos_bytes
    # Skinning writes (and clears) past the stored positions; the donor leaves that space empty.
    donor_next = min(a for a in (sm.color and sm.color.hdr, sm.uvs[0].hdr if sm.uvs else None, sm.normal.hdr)
                     if a is not None) - sm.position.ptr
    gap = max(pos_data + write_end, pos_data + (donor_next if nslots == sm.position.count else 0)) - here()
    out += bytes(max(0, gap))
    color_hdr = color_data = None
    if sm.color:
        color_hdr = here()
        out += b[sm.color.hdr:sm.color.hdr + 8]
        color_data = here()
        out += b[sm.color.ptr:sm.color.ptr + sm.color.count * sm.color.element_size()]
    pad_to(4)                                      # headers are word aligned, as in vanilla
    uv_hdr = here()
    for u in sm.uvs:
        out += b[u.hdr:u.hdr + 16]
    uv_ptrs = []
    for _ in sm.uvs:
        uv_ptrs.append(here())
        out += uv_data
    pad_to(4)
    normal_hdr = here()
    out += b[sm.normal.hdr:sm.normal.hdr + 12]
    disp_hdr = here()
    out += b[sm.display_header:sm.display_header + 12]
    ds_arr = here()
    out += b[sm.ds_array:sm.ds_array + 16 * len(sm.states)]
    prim_ptrs = {}
    pad_to(32)
    nop = here()
    out += NOP_LIST
    for i, data in sorted(group_lists.items()):
        pad_to(32)
        prim_ptrs[i] = (here(), len(data))
        out += data
    pal_name_src = L + sm.uvs[0].palette_name_ptr
    name = b[pal_name_src:b.index(b"\0", pal_name_src) + 1]
    pal_name = here()
    out += name
    pad_to(4)
    if here() > end:
        raise ValueError(f"submesh 0 needs {here() - L:#x} bytes, region has {end - L:#x}")

    rel = lambda a: a - L  # noqa: E731
    reg = lambda a: a - L  # offset inside `out`  # noqa: E731
    for k, a in enumerate((pos_hdr, color_hdr, uv_hdr, normal_hdr, disp_hdr)):
        put32(out, 4 * k, rel(a) if a else 0)
    out[0x14:0x18] = b[L + 0x14:L + 0x18]
    put32(out, reg(pos_hdr), rel(pos_data))
    put16(out, reg(pos_hdr) + 4, nslots)
    if color_hdr:
        put32(out, reg(color_hdr), rel(color_data))
    uv_count = len(uv_data) // 4
    for k in range(len(sm.uvs)):
        h = reg(uv_hdr) + 16 * k
        put32(out, h, rel(uv_ptrs[k]))
        put16(out, h + 4, uv_count)
        put32(out, h + 8, rel(pal_name))
    put32(out, reg(normal_hdr), rel(pos_data) + 6)       # skinned: normals interleaved after each position
    put16(out, reg(normal_hdr) + 4, nslots)
    first_prim = min((p for p, _ in prim_ptrs.values()), default=nop)
    put32(out, reg(disp_hdr), rel(first_prim))
    put32(out, reg(disp_hdr) + 4, rel(ds_arr))
    for i, ds in enumerate(sm.states):
        o = reg(ds_arr) + 16 * i
        if i in prim_ptrs:
            put32(out, o + 8, rel(prim_ptrs[i][0]))
            put32(out, o + 12, prim_ptrs[i][1])
        elif ds.prim_ptr is not None and ds.prim_size:
            put32(out, o + 8, rel(nop))
            put32(out, o + 12, len(NOP_LIST))
        if i in rebinds:
            put32(out, o + 4, (ds.setting & ~0x1FFF) | rebinds[i])
    used = here() - L
    out += bytes(end - here())
    return bytes(out), L, dict(region=[hex(L), hex(end)], used=used, free=end - L - used, uv_count=uv_count)


def build_rigid(m, sm, positions, normals, uv_data, group_lists):
    """Rewrite a rigid (one-bone) submesh's region, e.g. Daisy's crown or a Koopa's shell (model_import: a model edited
    in Blender): its positions (3 components, in its bone's space, the donor's quantization), its own normal array
    (one normal per position), UVs and primitive lists; the donor's color array, display states and names are kept.
    Returns (region bytes, region start); ValueError when it doesn't fit its region."""
    from mss_model import comp_size
    b, L = m.b, sm.layout
    end = region_end(m, L)
    out = bytearray(0x18)

    def here():
        return L + len(out)

    def pad_to(a):
        out.extend(bytes(align(here(), a) - here()))

    def pack(values, quant):
        if comp_size(quant) == 4:
            return struct.pack(f">{len(values)}f", *values)
        return quant16(values, quant)
    pos_hdr = here()
    out += b[sm.position.hdr:sm.position.hdr + 8]
    pad_to(32)
    pos_data = here()
    for p in positions:
        out += pack(list(p)[:3], sm.position.quant)
    color_hdr = color_data = None
    if sm.color:
        pad_to(4)
        color_hdr = here()
        out += b[sm.color.hdr:sm.color.hdr + 8]
        color_data = here()
        out += b[sm.color.ptr:sm.color.ptr + sm.color.count * sm.color.element_size()]
    pad_to(4)
    uv_hdr = here()
    for u in sm.uvs:
        out += b[u.hdr:u.hdr + 16]
    uv_ptrs = [here()] * len(sm.uvs)            # one copy the channels share (they hold the same UVs; read-only)
    out += uv_data
    pad_to(4)
    normal_hdr = here()
    out += b[sm.normal.hdr:sm.normal.hdr + 12]
    pad_to(4)
    normal_data = here()
    for n in normals:
        out += pack(list(n)[:3], sm.normal.quant)
    pad_to(4)
    disp_hdr = here()
    out += b[sm.display_header:sm.display_header + 12]
    ds_arr = here()
    out += b[sm.ds_array:sm.ds_array + 16 * len(sm.states)]
    prim_ptrs = {}
    pad_to(32)
    nop = here()
    out += NOP_LIST
    for i, data in sorted(group_lists.items()):
        pad_to(32)
        prim_ptrs[i] = (here(), len(data))
        out += data
    pal_name = None
    if sm.uvs:
        src = L + sm.uvs[0].palette_name_ptr
        pal_name = here()
        out += b[src:b.index(b"\0", src) + 1]
    pad_to(4)
    if here() > end:
        raise ValueError(f"part {sm.name!r} needs {here() - L:#x} bytes, its region has {end - L:#x}")
    rel = lambda a: a - L  # noqa: E731
    for k, a in enumerate((pos_hdr, color_hdr, uv_hdr, normal_hdr, disp_hdr)):
        put32(out, 4 * k, rel(a) if a else 0)
    out[0x14:0x18] = b[L + 0x14:L + 0x18]
    put32(out, rel(pos_hdr), rel(pos_data))
    put16(out, rel(pos_hdr) + 4, len(positions))
    if color_hdr:
        put32(out, rel(color_hdr), rel(color_data))
    uv_count = len(uv_data) // (2 * (comp_size(sm.uvs[0].quant) if sm.uvs else 2))
    for k in range(len(sm.uvs)):
        h = rel(uv_hdr) + 16 * k
        put32(out, h, rel(uv_ptrs[k]))
        put16(out, h + 4, uv_count)
        if pal_name is not None:
            put32(out, h + 8, rel(pal_name))
    put32(out, rel(normal_hdr), rel(normal_data))
    put16(out, rel(normal_hdr) + 4, len(normals))
    first_prim = min((p for p, _ in prim_ptrs.values()), default=nop)
    put32(out, rel(disp_hdr), rel(first_prim))
    put32(out, rel(disp_hdr) + 4, rel(ds_arr))
    for i, ds in enumerate(sm.states):
        o = rel(ds_arr) + 16 * i
        if i in prim_ptrs:
            put32(out, o + 8, rel(prim_ptrs[i][0]))
            put32(out, o + 12, prim_ptrs[i][1])
        elif ds.prim_ptr is not None and ds.prim_size:
            put32(out, o + 8, rel(nop))
            put32(out, o + 12, len(NOP_LIST))
    out += bytes(end - here())
    return bytes(out), L


# ---------------------------------------------------------------------------------------------- textures

def wimgt():
    for d, _, files in os.walk(P("tools/szs")):
        if "wimgt.exe" in files:
            return os.path.join(d, "wimgt.exe")
    return shutil.which("wimgt") or sys.exit("wimgt not found (tools/szs)")


WIMGT_TARGETS = {0xE: "TPL.CMPR", 0x5: "TPL.RGB5A3", 0x4: "TPL.RGB565", 0x6: "TPL.RGBA8"}


def encode_texture(img, fmt, size):
    """PIL image -> raw GX payload of `size` bytes via a single-image TPL from wimgt."""
    with tempfile.TemporaryDirectory() as tmp:
        png, tpl = os.path.join(tmp, "t.png"), os.path.join(tmp, "t.tpl")
        img.save(png)
        subprocess.run([wimgt(), "encode", "-q", "-o", "-x", WIMGT_TARGETS[fmt], "-d", tpl, png], check=True)
        data = open(tpl, "rb").read()
    assert struct.unpack_from(">I", data, 0)[0] == 0x0020AF30, "not a TPL"
    img_hdr = struct.unpack_from(">I", data, struct.unpack_from(">I", data, 8)[0])[0]
    h, w, f, off = struct.unpack_from(">HHII", data, img_hdr)
    assert (w, h, f) == (img.width, img.height, fmt), (w, h, f)
    payload = data[off:off + size]
    assert len(payload) == size
    return payload


def compose_texture(spec, width, height):
    """Texture slot spec -> RGB(A) image of the slot's size."""
    if "image" in spec:
        img = Image.open(P(spec["image"])).convert("RGBA").resize((width, height), Image.LANCZOS)
    else:  # expression strip: square cells side by side, then a fill color for the rest
        cell = height
        img = Image.new("RGBA", (width, height))
        for k, f in enumerate(spec["strip"]):
            img.paste(Image.open(P(f)).convert("RGBA").resize((cell, cell), Image.LANCZOS), (k * cell, 0))
        src = Image.open(P(spec["fill_from"])).convert("RGB")
        border = [src.getpixel((x, y)) for x in range(0, src.width, 4) for y in (2, src.height - 3)]
        fill = tuple(sum(c[i] for c in border) // len(border) for i in range(3)) + (255,)
        img.paste(Image.new("RGBA", (width - len(spec["strip"]) * cell, height), fill), (len(spec["strip"]) * cell, 0))
    if not spec.get("alpha", False):
        img = img.convert("RGB").convert("RGBA")
    return img


# ---------------------------------------------------------------------------------------------- per LOD

def load_mesh(pack, lod):
    """Mesh input -> list of objects {positions, normals, weights {bone id: w}, tris [(verts, raw uvs, role)]}
    plus fixed binary slots per vertex (or None).

    Two inputs: scripts/blender/export_mesh_data.py (per object; UVs already raw, materials by name) and the
    slot packer's export/<level>/mesh.json (one object; UVs in Blender V; triangles tagged with a texture slot),
    whose slots_report.json gives the donor slot of each vertex."""
    mesh = json.load(open(P(lod["mesh"])))
    if "triangles" in mesh and mesh["triangles"] and isinstance(mesh["triangles"][0], dict):
        roles = pack["tex_roles"]
        obj = dict(positions=mesh["positions"], normals=mesh["normals"],
                   weights=[{int(k.removeprefix("bone_")): v for k, v in w.items()} for w in mesh["weights"]],
                   tris=[(t["verts"], [[u, 1.0 - v] for u, v in t["uvs"]], roles[str(t["slot"])])
                         for t in mesh["triangles"]])
        slots = None
        if lod.get("slots"):
            slots = json.load(open(P(lod["slots"])))["binary_slot_of_vertex"]
        return [obj], slots
    objs = []
    for o in mesh.values():
        objs.append(dict(positions=o["positions"], normals=o["normals"],
                         weights=[{int(k): v for k, v in w.items()} for w in o["weights"]],
                         tris=[(t, uvs, pack["materials"][mat])
                               for t, uvs, mat in zip(o["triangles"], o["uvs"], o["materials"])]))
    return objs, None


def patch_donor_skin(m, blk, slots, pos, nrm, stride):
    """Keep the donor's SKN: write bind positions/normals into the source arrays that feed each slot."""
    k, b = m.skin, m.b
    at = defaultdict(list)                      # slot -> block offsets of its source records
    for e in k.sk1 + k.sk2:
        first = (e["dest"] + e["voff"]) // stride
        for j in range(e["count"]):
            at[first + j].append(k.off + e["src"] + e["voff"] + j * stride)
    for e in k.acc:
        base = e["dest"] // stride
        for j in range(e["count"]):
            idx = struct.unpack_from(">H", b, k.off + e["dest_idx"] + 2 * j)[0]
            at[base + idx].append(k.off + e["src"] + j * stride)
    missing = [s for s in slots if s not in at]
    if missing:
        raise ValueError(f"slots without skin records: {missing[:10]}")
    for vi, s in enumerate(slots):
        data = quant16(list(pos[vi]) + list(nrm[vi]), k.quant)
        for o in at[s]:
            blk[o:o + stride] = data


def build_lod(cfg, pack, lod_name, lod, textures):
    blk = bytearray(read_block(P(pack["dat"]), int(lod["offset"], 0), lod["length"]))
    m = Model(blk)
    sm = m.submeshes[0]
    assert sm.skinned, "submesh 0 must be the skinned body"
    stride = sm.position.element_size()
    groups = donor_groups(m, sm)
    roles = pack["groups"]
    hands = {r: hand_bones(m, groups, roles[r]) for r in ("hand_right", "hand_left") if r in roles}
    objs, fixed_slots = load_mesh(pack, lod)
    keep_skin = pack.get("skin") == "donor"
    if keep_skin and fixed_slots is None:
        raise ValueError("skin 'donor' needs fixed slots (lod 'slots')")

    # Rebuilt skins only use bones the donor's own skin at this LOD uses. Other bones (mesh-owning accessory
    # bones such as Bowser's 22/27/67/72/92/99, which mostly have no animation track) gave invisible or
    # misplaced models in game; their weight moves to the nearest ancestor that the stock skin uses.
    remapped = Counter()
    if not keep_skin:
        k = m.skin
        allowed = {e["bone"] for e in k.sk1 + k.acc} | {x for e in k.sk2 for x in e["bones"]}
        tree = act_bones(m.b, m.sections["act"])

        def to_allowed(bone):
            b0 = bone
            while bone is not None and bone not in allowed:
                bone = tree.get(bone, (None, None))[0]
            if bone is None:
                raise ValueError(f"bone {b0} has no ancestor in the donor's skinned set")
            return bone

        for obj in objs:
            new = []
            for w in obj["weights"]:
                merged = defaultdict(float)
                for bone, v in w.items():
                    target = to_allowed(bone)
                    if target != bone:
                        remapped[f"{bone}->{target}"] += 1
                    merged[target] += v
                new.append(dict(merged))
            obj["weights"] = new

    # Vertices of all objects in one list; triangles sorted into draw groups.
    weights, pos, nrm, tris_by_group = [], [], [], defaultdict(list)
    uv_index, uv_list = {}, []
    uvq = sm.uvs[0].quant
    for obj in objs:
        base = len(pos)
        pos += obj["positions"]
        nrm += obj["normals"]
        weights += [quantize_weights(w, pack.get("max_influences", 3)) for w in obj["weights"]]
        for t, uvs, role in obj["tris"]:
            if role == "face" and "face_uv" in pack:
                xform = pack["face_uv"]
                uvs = [[u * xform["scale"][0] + xform["offset"][0], v * xform["scale"][1] + xform["offset"][1]]
                       for u, v in uvs]
            if role == "face" and "face" not in roles:
                cx = sum(pos[base + i][0] for i in t) / 3
                group = roles["face_right"] if cx < 0 else roles["face_left"]   # character's right is -x
            elif role == "face":
                group = roles["face"]
            else:
                group = roles[role] if role in roles else roles["body"]     # (a glTF's own draw group: model_import)
                for side in hands:
                    doms = {max(weights[base + i], key=lambda bw: bw[1])[0] for i in t}
                    if doms <= hands[side]:
                        group = roles[side]
            corners = []
            for i, uv in zip(t, uvs):
                key = quant16(uv, uvq)
                if key not in uv_index:
                    uv_index[key] = len(uv_list)
                    uv_list.append(key)
                corners.append((base + i, uv_index[key]))
            tris_by_group[group].append((corners[0], corners[2], corners[1]))   # Blender CCW -> game CW

    if keep_skin:
        slot, nslots, placed, acc = fixed_slots, sm.position.count, [], {}
        pos_bytes = bytearray(m.b[sm.position.ptr:sm.position.ptr + nslots * stride])
    else:
        slot, nslots, placed, acc = layout_skin(weights, stride)
        pos_bytes = bytearray(nslots * stride)
    occupied = enumerate(slot) if keep_skin else ((vi, s) for e in placed for s, vi in e["slots"])
    for vi, s in occupied:
        pos_bytes[s * stride:(s + 1) * stride] = quant16(list(pos[vi]) + list(nrm[vi]), sm.position.quant)
    pos_bytes = bytes(pos_bytes)

    group_lists = {}
    for g, tris in tris_by_group.items():
        tris = [tuple((slot[vi], uv) for vi, uv in t) for t in tris]
        group_lists[g] = prim_list(tris, groups[g]["fmt"], groups[g]["color"], use_strips=pack.get("strips", False))
    rebinds = {}
    for g, tex in pack.get("rebind", {}).items():
        rebinds[groups[roles[g]]["bind"]] = tex

    if keep_skin:
        write_end = m.skin.write_end(m.b)
    else:
        write_end = max(e["dest"] + align(e["voff"] + len(e["members"]) * stride) for e in placed)  # DMA lines
    region, start, body_report = build_body(m, sm, pos_bytes, nslots, b"".join(uv_list), group_lists, rebinds,
                                            write_end)
    blk[start:start + len(region)] = region

    # Other submeshes draw nothing: zero their primitive bytes (GX NOPs), keeping pointers and sizes.
    for other in m.submeshes[1:]:
        for ds in other.states:
            if ds.prim_ptr is not None and ds.prim_size:
                blk[ds.prim_ptr:ds.prim_ptr + ds.prim_size] = bytes(ds.prim_size)

    # Skinning, then facial poses off.
    skn = m.sections["skn"]
    skn_end = min([v for v in m.sections.values() if v > skn and v != m.sections["facial"]] + [len(blk)])
    if keep_skin:
        patch_donor_skin(m, blk, slot, pos, nrm, stride)
        skin = b""
    else:
        skin = build_skin(m.skin.quant, stride, placed, acc, slot, pos_bytes)
        if skn + len(skin) > skn_end:
            raise ValueError(f"skin needs {len(skin)} bytes, {skn_end - skn} available")
        blk[skn:skn_end] = skin + bytes(skn_end - skn - len(skin))
    put32(blk, 0x18, 0)

    # Textures live in the block that has a TEX section.
    for idx, img in textures.items():
        if not m.textures:
            continue
        t = m.textures[int(idx)]
        blk[t.image:t.image + t.payload_size()] = encode_texture(img(t.width, t.height), t.format, t.payload_size())

    written = Model(blk)
    body = written.submeshes[0]
    window = body.position.ptr + written.skin.write_end(written.b)
    for a in (body.color, *body.uvs, body.normal):
        if a is not None and a is not body.normal and window > a.hdr >= body.position.ptr:
            raise ValueError(f"{a.kind} header at {a.hdr:#x} is inside the skinning window (ends {window:#x})")
    for kind, entries in (("sk1", written.skin.sk1), ("sk2", written.skin.sk2)):
        for e in entries:
            if not MIN_ENTRY <= e["count"] or e["voff"] + e["count"] * stride > MAX_ENTRY_BYTES[kind]:
                raise ValueError(f"{kind} entry of {e['count']} vertices is outside the vanilla shape")
    validation = validate(bytes(blk))

    counts = Counter(len(w) for w in weights)
    report = dict(vertices=len(pos), slots=nslots, donor_slots=sm.position.count, uvs=len(uv_list),
                  influences={str(k): v for k, v in sorted(counts.items())},
                  sk1=sum(e["kind"] == "sk1" for e in placed), sk2=sum(e["kind"] == "sk2" for e in placed),
                  skacc=len(acc), skin_bytes=len(skin), skin_budget=skn_end - skn,
                  groups={str(g): dict(tag=groups[g]["tag"], tris=len(t), donor_tris=len(groups[g]["tris"]))
                          for g, t in sorted(tris_by_group.items())},
                  hand_bones={k: sorted(v) for k, v in hands.items()}, body=body_report,
                  remapped_bones=dict(remapped),
                  skin_window_end=hex(window), validator_warnings=validation["warnings"])
    return bytes(blk), report


def validate(block):
    """Hard gate: Sluggies-dat-tools' BlockValidator (refs/, run in place; the repo has no license, so it is
    not vendored here)."""
    tools = P("refs/Sluggies-dat-tools/SluggiesTools")
    if not os.path.isdir(tools):            # the patcher's download (no refs/): charpack.gate_lod's own checks follow
        return {"valid": True, "warnings": ["Sluggies' BlockValidator isn't here: our own crash checks only"]}
    for p in (tools, os.path.join(tools, "Hammerspace")):
        if p not in sys.path:
            sys.path.insert(0, p)
    from BlockValidator import validate_model_block
    result = validate_model_block(block)
    if not result["valid"]:
        raise ValueError("BlockValidator rejected the block:\n  " + "\n  ".join(map(str, result["errors"])))
    return result


# Quick boot (scripts/quickboot.py) needs a code section; same place and arena handling as charbuild.py.
QB_CODE = 0x807B7000
ARENA_SITES = ((0x80595FC4, 0x80595FC8, 0x6E80), (0x8059606C, 0x80596070, 0x6E80), (0x80596014, 0x80596018, 0x4E80))


def quickboot_dol(src, dst, options=None):
    """main.dol with quick boot (power on -> save file 1 -> Exhibition captain select); the OS arena low
    moves above the new code section so the heap never overlaps it."""
    from dol import Dol
    from ppc import ha, lo
    import quickboot
    dol = Dol(src)
    code = _Space(QB_CODE)
    options = dict(options or {})           # pack "quickboot": e.g. {"mode": "game", "captains": [...]}
    if options.get("mode") == "game":
        options.setdefault("teams", [[], []])   # stock players; quickboot's own default is every new id
    log = quickboot.apply(dol, code, **options)
    new_lo = align(code.here)
    for lis, addi, old in ARENA_SITES:
        assert dol.u32(addi) & 0xFFFF == old and dol.u32(lis) & 0xFFFF == 0x807B, "unexpected arena code"
        dol.w32(lis, (dol.u32(lis) & 0xFFFF0000) | ha(new_lo))
        dol.w32(addi, (dol.u32(addi) & 0xFFFF0000) | lo(new_lo))
    dol.add_section("text", QB_CODE, code.blob)
    dol.save(dst)
    return log + [f"quick boot code 0x{len(code.blob):x} B at 0x{QB_CODE:08X}, arena low 0x{new_lo:08X}"]


class _Space:
    """The allocator interface quickboot.apply expects (charbuild.Space)."""
    def __init__(self, base):
        self.base, self.blob = base, bytearray()

    @property
    def here(self):
        return self.base + len(self.blob)

    def put(self, data, align_to=32):
        self.blob += bytes(-len(self.blob) % align_to)
        addr = self.here
        self.blob += data
        return addr


def make_game(pack, blocks, out_dir, quick_boot=True):
    """Hard-link copy of the base game folder with dt_na.dat patched (and main.dol with quick boot)."""
    src = P(pack["game"])
    if os.path.exists(out_dir):     # it may be open in Dolphin: always build into a new folder
        raise SystemExit(f"{out_dir} exists; pick a new folder name (keep at most 3 of your own builds)")
    for d, _, files in os.walk(src):
        rel = os.path.relpath(d, src)
        os.makedirs(os.path.join(out_dir, rel), exist_ok=True)
        for f in files:
            s, t = os.path.join(d, f), os.path.join(out_dir, rel, f)
            if rel == "files" and f == "dt_na.dat":
                shutil.copyfile(s, t)
            elif rel == "sys" and f == "main.dol" and quick_boot:
                for line in quickboot_dol(s, t, pack.get("quickboot")):   # new file, never via the hard link
                    print(line)
            else:
                os.link(s, t)
    with open(os.path.join(out_dir, "files", "dt_na.dat"), "r+b") as f:
        for off, data in blocks:
            f.seek(off)
            f.write(data)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("config")
    ap.add_argument("--game", help="write a bootable game folder here")
    ap.add_argument("--no-quickboot", action="store_true", help="--game: keep the stock boot sequence")
    a = ap.parse_args()
    cfg = json.load(open(a.config))
    pack = cfg["pack"]
    out = P(pack["out_dir"])
    os.makedirs(out, exist_ok=True)
    textures = {k: (lambda w, h, s=s: compose_texture(s, w, h)) for k, s in pack.get("textures", {}).items()}
    report, blocks = {}, []
    for name, lod in pack["lods"].items():
        data, report[name] = build_lod(cfg, pack, name, lod, textures)
        open(os.path.join(out, name + ".bin"), "wb").write(data)
        blocks.append((int(lod["offset"], 0), data))
        print(f"{name}: {report[name]['vertices']} vertices in {report[name]['slots']} slots "
              f"(donor {report[name]['donor_slots']}), skin {report[name]['skin_bytes']}/{report[name]['skin_budget']} "
              f"bytes, body region {report[name]['body']['used']} used, {report[name]['body']['free']} free")
    json.dump(report, open(os.path.join(out, "report.json"), "w"), indent=1)
    if a.game:
        make_game(pack, blocks, os.path.abspath(a.game), quick_boot=not a.no_quickboot)
        print("game folder:", os.path.abspath(a.game))


if __name__ == "__main__":
    main()
