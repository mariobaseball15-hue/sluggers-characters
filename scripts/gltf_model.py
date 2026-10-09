"""Model blocks <-> glTF 2.0 binary (.glb), for character files people edit in Blender (git-f3's .slgmodel).

  python scripts/gltf_model.py <model block .bin> <out.glb>        one block (e.g. models/work/<x>/pack/high.bin)
  python scripts/gltf_model.py --check [--game DIR] [--data DIR]  the round trip on our characters + 3 stock ones
                                                                   (--data: where models/work is; a worktree without
                                                                   it gives the main checkout; needs wimgt, tools/szs)

block_to_glb(block, name, base_name) -> bytes. What Blender opens:
- One mesh per GPL submesh (named after it), one primitive per draw group (display-state group), each with one
  material: the texture bound on layer 0 (every texture is embedded as a PNG). Material names are
  "tex<k>_ds<state>" (or "untextured_ds<state>"), so the texture and draw group survive a Blender round trip; the
  primitive's extras say the same ({"sluggers": {"submesh", "state", "texture", "tag"}}).
- Game space is glTF space: both are Y-up and right-handed, so positions go in unchanged (Blender's importer turns
  them Z-up itself). glTF texture coordinates have their origin at the top left, like the game's, so UVs go in
  unchanged too; Blender's importer flips V, which gives the Blender / DAE convention (Blender V = 1 - game V,
  docs/custom-model-format.md).
- Triangles: game winding is the reverse of glTF's counter-clockwise fronts (WINDING_FLIP, measured against the
  vertex normals), so each triangle's last two corners are swapped.
- Skeleton: the ACT bone tree (refs/Sluggies-dat-tools/_docs/_docs_model_format/act_section.html: bone records
  and SRT pose blobs), one node per bone named "bone_<id>" with its pose as TRS, children under their parent (a
  bone not positioned relative to its parent is a top-level node).
- The skinned submesh (submesh 0 in player models, model-space positions) is skinned to every bone: JOINTS_0 /
  WEIGHTS_0 (and _1 past four influences) from the SKN section (mss_model.Skin.influences: SK1, SK2, SKAcc), with
  inverse bind matrices from the pose. Rigid submeshes, stored in their owner bone's space, are children of that
  bone's node (GEO id).
- Every primitive also carries _POSINDEX (the game position index of each vertex), so the game's shared positions
  come back exactly; a file without it (a Blender re-export may drop it) is welded by position and weights.
- Normals: the skinned mesh's normal array is interleaved with its positions (each entry's first three values).
- Vertex colors are left out (they are lighting data, and glTF multiplies them into the base color).

glb_to_mesh(glb) -> (objects, textures, info):
- objects: {mesh name: {"positions", "normals", "triangles", "uvs", "materials", "weights"}}, the shape
  scripts/blender/export_mesh_data.py writes and build_model.load_mesh reads: game-space positions and normals
  (per position), triangles in Blender (glTF) winding as position indices, raw game UVs per corner, a material name
  per triangle and {bone id: weight} per position. Positions are in the mesh's own space: model space for the
  skinned mesh, the owner bone's space for a rigid one.
- textures: {texture index: PIL RGBA image}, from the images named "tex<k>".
- info: {mesh name: {"submesh", "bone" (a rigid mesh's owner bone id, else None), "skinned"}} and "base" (the
  scene's base name).
"""
import io
import json
import math
import os
import struct
import sys

import numpy as np
from PIL import Image

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from mss_model import Model, u8, u16, u32  # noqa: E402

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
WINDING_FLIP = True        # game triangles are clockwise-front: swap two corners for glTF (measured, see check)
# The SRT quaternion (x, y, z, w) is the bone's rotation as stored (glTF's order). Measured: skinned vertices lie
# 0.2 / 0.37 / 0.55 units (Mario / Boo / Bowser) from their heaviest bone's bind position this way, 1.7 / 2.1 / 4.1
# with the conjugate (pose_score). Triangles: 99.6-100 % face their vertex normals after WINDING_FLIP (winding_score).
QUAT_CONJUGATE = False
FLOAT, USHORT, UINT = 5126, 5123, 5125
ARRAY_BUFFER, ELEMENT_ARRAY_BUFFER = 34962, 34963


# ------------------------------------------------------------------------------------------------ the skeleton

def _quat_matrix(q):
    x, y, z, w = q
    return np.array([[1 - 2 * (y * y + z * z), 2 * (x * y - z * w), 2 * (x * z + y * w)],
                     [2 * (x * y + z * w), 1 - 2 * (x * x + z * z), 2 * (y * z - x * w)],
                     [2 * (x * z - y * w), 2 * (y * z + x * w), 1 - 2 * (x * x + y * y)]])


def trs_matrix(t, q, s):
    m = np.identity(4)
    m[:3, :3] = _quat_matrix(q) * np.array(s)
    m[:3, 3] = t
    return m


def bones(block):
    """[{"id", "parent" (bone id or None), "geo" (submesh index or None), "relative", "t", "r" (glTF x, y, z, w),
    "s", "world" (4x4)}] in table order, from the ACT section's bone records and SRT blobs."""
    b = block
    act = u32(b, 8)
    out, stack = [], [(u32(b, act + 0xC), None)]
    while stack:
        node, parent = stack.pop()
        while node:
            n = act + node
            srt = u32(b, n)
            t, q, s = (0.0, 0.0, 0.0), (0.0, 0.0, 0.0, 1.0), (1.0, 1.0, 1.0)
            if srt:
                s = struct.unpack_from(">3f", b, act + srt + 4)
                x, y, z, w = struct.unpack_from(">4f", b, act + srt + 0x10)
                q = (-x, -y, -z, w) if QUAT_CONJUGATE else (x, y, z, w)
                t = struct.unpack_from(">3f", b, act + srt + 0x20)
            norm = math.sqrt(sum(c * c for c in q)) or 1.0
            q = tuple(c / norm for c in q)
            geo = u16(b, n + 0x14)
            out.append(dict(id=u16(b, n + 0x16), parent=parent, geo=None if geo == 0xFFFF else geo,
                            relative=bool(u8(b, n + 0x18)), t=t, r=q, s=s))
            if u32(b, n + 0x10):
                stack.append((u32(b, n + 0x10), u16(b, n + 0x16)))
            node = u32(b, n + 0x8)
    by_id = {x["id"]: x for x in out}

    def world(x):
        if "world" not in x:
            local = trs_matrix(x["t"], x["r"], x["s"])
            p = by_id.get(x["parent"]) if x["relative"] else None
            x["world"] = world(p) @ local if p else local
        return x["world"]
    for x in out:
        world(x)
    return out


# ------------------------------------------------------------------------------------------------ block -> glb

class _Glb:
    def __init__(self):
        self.bin = bytearray()
        self.gltf = {"asset": {"version": "2.0", "generator": "sluggers gltf_model.py"}, "buffers": [],
                     "bufferViews": [], "accessors": []}

    def view(self, data, target=None):
        self.bin += bytes(-len(self.bin) % 4)
        v = {"buffer": 0, "byteOffset": len(self.bin), "byteLength": len(data)}
        if target:
            v["target"] = target
        self.bin += data
        self.gltf["bufferViews"].append(v)
        return len(self.gltf["bufferViews"]) - 1

    def accessor(self, arr, kind, ctype, target=ARRAY_BUFFER, minmax=False):
        arr = np.ascontiguousarray(arr)
        a = {"bufferView": self.view(arr.tobytes(), target), "componentType": ctype, "count": len(arr), "type": kind}
        if minmax:
            a["min"], a["max"] = [float(v) for v in arr.min(0)], [float(v) for v in arr.max(0)]
        self.gltf["accessors"].append(a)
        return len(self.gltf["accessors"]) - 1

    def glb(self):
        self.bin += bytes(-len(self.bin) % 4)
        self.gltf["buffers"] = [{"byteLength": len(self.bin)}]
        js = json.dumps(self.gltf, separators=(",", ":")).encode()
        js += b" " * (-len(js) % 4)
        return (struct.pack("<III", 0x46546C67, 2, 12 + 8 + len(js) + 8 + len(self.bin)) +
                struct.pack("<II", len(js), 0x4E4F534A) + js + struct.pack("<II", len(self.bin), 0x004E4942) +
                bytes(self.bin))


def texture_images(block, m=None):
    """{texture index: PIL RGBA} (sluggie._decode: CMPR / RGB5A3 / ... and the paletted C4 / C8)."""
    import sluggie
    m = m or Model(block)
    out = {}
    for k, t in enumerate(m.textures):
        try:
            out[k] = sluggie._decode(block, t)
        except Exception:                               # a format neither decoder reads: a grey stand-in
            out[k] = Image.new("RGBA", (max(t.width, 1), max(t.height, 1)), (128, 128, 128, 255))
    return out


def block_to_glb(block, name="", base_name=""):
    b = bytes(block)
    m = Model(b)
    g = _Glb()
    gl = g.gltf
    sk = bones(b)
    order = sorted(sk, key=lambda x: x["id"])
    node_of = {x["id"]: i for i, x in enumerate(order)}
    gl["nodes"] = [{"name": f"bone_{x['id']}", "translation": [float(v) for v in x["t"]],
                    "rotation": [float(v) for v in x["r"]], "scale": [float(v) for v in x["s"]]} for x in order]
    roots = []
    for x in order:
        if x["relative"] and x["parent"] is not None:
            gl["nodes"][node_of[x["parent"]]].setdefault("children", []).append(node_of[x["id"]])
        else:
            roots.append(node_of[x["id"]])

    # textures and materials
    images = texture_images(b, m)
    gl["images"], gl["textures"], gl["samplers"] = [], [], [{"wrapS": 10497, "wrapT": 10497}]
    tex_of = {}
    for k, img in images.items():
        png = io.BytesIO()
        img.save(png, "PNG")
        gl["images"].append({"name": f"tex{k}", "mimeType": "image/png", "bufferView": g.view(png.getvalue())})
        gl["textures"].append({"source": len(gl["images"]) - 1, "sampler": 0})
        tex_of[k] = len(gl["textures"]) - 1
    gl["materials"], mat_of = [], {}

    def material(k, state):
        key = (k, state)
        if key not in mat_of:
            mat = {"name": f"tex{k}_ds{state}" if k is not None else f"untextured_ds{state}",
                   "pbrMetallicRoughness": {"metallicFactor": 0.0, "roughnessFactor": 1.0}}
            if k is not None and k in tex_of:
                mat["pbrMetallicRoughness"]["baseColorTexture"] = {"index": tex_of[k]}
                if min(images[k].getchannel("A").getextrema()) < 255:
                    mat["alphaMode"], mat["alphaCutoff"] = "MASK", 0.5
            gl["materials"].append(mat)
            mat_of[key] = len(gl["materials"]) - 1
        return mat_of[key]

    # skin
    skin_index = None
    influences = m.skin.influences(b) if m.skin else {}
    if any(s.skinned for s in m.submeshes):
        ibm = np.array([np.linalg.inv(x["world"]).T.reshape(-1) for x in order], dtype=np.float32)
        gl["skins"] = [{"joints": list(range(len(order))), "skeleton": roots[0] if roots else 0,
                        "inverseBindMatrices": g.accessor(ibm, "MAT4", FLOAT, target=None)}]
        skin_index = 0
    owner = {x["geo"]: x["id"] for x in sk if x["geo"] is not None}
    gl["meshes"], scene_nodes = [], list(roots)
    for s in m.submeshes:
        pos = s.position.values(b)
        nrm = s.normal.values(b) if s.normal else None
        uv0 = s.uvs[0].values(b) if s.uvs else None
        prims = []
        for state, tag, binds, fmt, tris in s.groups(b):
            if not tris:
                continue
            keys, index, corners = {}, [], []
            for tri in tris:
                tri = (tri[0], tri[2], tri[1]) if WINDING_FLIP else tri
                for v in tri:
                    key = (v.get("position"), v.get("normal"), v.get("tex0"))
                    if key not in keys:
                        keys[key] = len(keys)
                        corners.append(key)
                    index.append(keys[key])
            P = np.array([pos[p][:3] for p, _, _ in corners], dtype=np.float32)
            if nrm is not None:
                N = np.array([nrm[n][:3] if n is not None else (0, 1, 0) for _, n, _ in corners], dtype=np.float32)
            else:
                N = np.array([pos[p][3:6] if len(pos[p]) >= 6 else (0, 1, 0) for p, _, _ in corners], dtype=np.float32)
            N /= np.maximum(np.linalg.norm(N, axis=1, keepdims=True), 1e-9)
            attrs = {"POSITION": g.accessor(P, "VEC3", FLOAT, minmax=True), "NORMAL": g.accessor(N, "VEC3", FLOAT),
                     "_POSINDEX": g.accessor(np.array([p for p, _, _ in corners], dtype=np.float32), "SCALAR", FLOAT)}
            if uv0 is not None:
                attrs["TEXCOORD_0"] = g.accessor(np.array([uv0[t] if t is not None else (0, 0)
                                                           for _, _, t in corners], dtype=np.float32), "VEC2", FLOAT)
            if s.skinned and skin_index is not None:
                J, W = [], []
                for p, _, _ in corners:
                    w = sorted(influences.get(p, {}).items(), key=lambda kv: -kv[1])[:8] or [(order[0]["id"], 1.0)]
                    total = sum(v for _, v in w) or 1.0
                    w = [(node_of.get(bone, 0), v / total) for bone, v in w] + [(0, 0.0)] * 8
                    J.append([j for j, _ in w[:8]])
                    W.append([v for _, v in w[:8]])
                J, W = np.array(J, dtype=np.uint16), np.array(W, dtype=np.float32)
                attrs["JOINTS_0"] = g.accessor(J[:, :4], "VEC4", USHORT)
                attrs["WEIGHTS_0"] = g.accessor(W[:, :4], "VEC4", FLOAT)
                if W[:, 4:].any():
                    attrs["JOINTS_1"] = g.accessor(J[:, 4:], "VEC4", USHORT)
                    attrs["WEIGHTS_1"] = g.accessor(W[:, 4:], "VEC4", FLOAT)
            k = binds.get(0)
            prims.append({"attributes": attrs, "mode": 4, "material": material(k, state),
                          "indices": g.accessor(np.array(index, dtype=np.uint32), "SCALAR", UINT, ELEMENT_ARRAY_BUFFER),
                          "extras": {"sluggers": {"submesh": s.idx, "state": state, "texture": k, "tag": tag}}})
        if not prims:
            continue
        gl["meshes"].append({"name": s.name or f"submesh{s.idx}", "primitives": prims,
                             "extras": {"sluggers": {"submesh": s.idx, "skinned": s.skinned}}})
        node = {"name": s.name or f"submesh{s.idx}", "mesh": len(gl["meshes"]) - 1}
        gl["nodes"].append(node)
        ni = len(gl["nodes"]) - 1
        if s.skinned and skin_index is not None:
            node["skin"] = skin_index
            scene_nodes.append(ni)
        elif s.idx in owner:
            gl["nodes"][node_of[owner[s.idx]]].setdefault("children", []).append(ni)
        else:
            scene_nodes.append(ni)
    gl["scenes"] = [{"name": name or "model", "nodes": scene_nodes,
                     "extras": {"sluggers": {"base": base_name, "name": name}}}]
    gl["scene"] = 0
    return g.glb()


# ------------------------------------------------------------------------------------------------ glb -> mesh

def read_glb(data):
    """GLB bytes -> (gltf dict, binary chunk)."""
    magic, _, _ = struct.unpack_from("<III", data, 0)
    assert magic == 0x46546C67, "not a .glb"
    o, js, binary = 12, None, b""
    while o < len(data):
        n, kind = struct.unpack_from("<II", data, o)
        chunk = data[o + 8:o + 8 + n]
        if kind == 0x4E4F534A:
            js = json.loads(chunk)
        elif kind == 0x004E4942:
            binary = bytes(chunk)
        o += 8 + n
    return js, binary


_NP = {5120: np.int8, 5121: np.uint8, 5122: np.int16, 5123: np.uint16, 5125: np.uint32, 5126: np.float32}
_N = {"SCALAR": 1, "VEC2": 2, "VEC3": 3, "VEC4": 4, "MAT4": 16}


def _read(gl, binary, i):
    a = gl["accessors"][i]
    n, dt = _N[a["type"]], np.dtype(_NP[a["componentType"]])
    if "bufferView" not in a:
        return np.zeros((a["count"], n) if n > 1 else a["count"], dt)
    v = gl["bufferViews"][a["bufferView"]]
    start = v.get("byteOffset", 0) + a.get("byteOffset", 0)
    stride = v.get("byteStride") or n * dt.itemsize
    raw = np.frombuffer(binary, np.uint8, count=stride * (a["count"] - 1) + n * dt.itemsize, offset=start)
    rows = np.lib.stride_tricks.as_strided(raw, (a["count"], n * dt.itemsize), (stride, 1))
    out = np.ascontiguousarray(rows).view(dt).reshape(a["count"], n)
    if a.get("normalized"):
        out = out.astype(np.float32) / np.iinfo(dt).max
    return out if n > 1 else out[:, 0]


def glb_to_mesh(glb):
    gl, binary = read_glb(glb)
    names = [n.get("name", "") for n in gl.get("nodes", [])]
    parent = {c: i for i, n in enumerate(gl.get("nodes", [])) for c in n.get("children", [])}

    def bone_id(ni):
        nm = names[ni] if ni is not None else ""
        return int(nm[5:]) if nm.startswith("bone_") and nm[5:].isdigit() else None
    textures = {}
    for img in gl.get("images", []):
        nm = img.get("name", "")
        if nm.startswith("tex") and nm[3:].isdigit() and "bufferView" in img:
            v = gl["bufferViews"][img["bufferView"]]
            data = binary[v.get("byteOffset", 0):v.get("byteOffset", 0) + v["byteLength"]]
            textures[int(nm[3:])] = Image.open(io.BytesIO(data)).convert("RGBA")
    objects, info = {}, {}
    for ni, node in enumerate(gl.get("nodes", [])):
        if "mesh" not in node:
            continue
        mesh = gl["meshes"][node["mesh"]]
        name = mesh.get("name") or node.get("name") or f"mesh{ni}"
        joints = [bone_id(j) for j in gl["skins"][node["skin"]]["joints"]] if "skin" in node else None
        ex = mesh.get("extras", {}).get("sluggers", {})
        # welded positions: by _POSINDEX when present, else by position and weights
        slot_of, positions, normals, weights = {}, [], [], []
        tris, uvs, mats = [], [], []
        for prim in mesh["primitives"]:
            at = prim["attributes"]
            P = _read(gl, binary, at["POSITION"])
            N = _read(gl, binary, at["NORMAL"]) if "NORMAL" in at else np.zeros_like(P)
            T = _read(gl, binary, at["TEXCOORD_0"]) if "TEXCOORD_0" in at else np.zeros((len(P), 2), np.float32)
            PI = _read(gl, binary, at["_POSINDEX"]) if "_POSINDEX" in at else None
            W = {}
            if joints is not None:
                for jn, wn in (("JOINTS_0", "WEIGHTS_0"), ("JOINTS_1", "WEIGHTS_1")):
                    if jn in at:
                        J, Wt = _read(gl, binary, at[jn]), _read(gl, binary, at[wn])
                        for r in range(len(P)):
                            for j, w in zip(J[r], Wt[r]):
                                if w > 0:
                                    bone = joints[int(j)]
                                    W.setdefault(r, {})[bone] = W.get(r, {}).get(bone, 0.0) + float(w)
            local = []
            for r in range(len(P)):
                key = ("i", int(round(float(PI[r])))) if PI is not None else \
                      ("p", tuple(np.round(P[r], 5)), tuple(sorted((k, round(v, 4)) for k, v in W.get(r, {}).items())))
                if key not in slot_of:
                    slot_of[key] = len(positions)
                    positions.append([float(c) for c in P[r]])
                    normals.append([float(c) for c in N[r]])
                    weights.append({k: v for k, v in W.get(r, {}).items()})
                local.append(slot_of[key])
            idx = _read(gl, binary, prim["indices"]) if "indices" in prim else np.arange(len(P))
            mname = gl["materials"][prim["material"]].get("name", "") if "material" in prim else ""
            for t in range(0, len(idx) - 2, 3):
                c = [int(idx[t]), int(idx[t + 1]), int(idx[t + 2])]
                tris.append([local[k] for k in c])
                uvs.append([[float(T[k][0]), float(T[k][1])] for k in c])
                mats.append(mname)
        if PI is not None and all(k[0] == "i" for k in slot_of):   # the game's position order, as the block had it
            order = sorted(slot_of, key=lambda k: k[1])
            remap = {slot_of[k]: n for n, k in enumerate(order)}
            positions = [positions[slot_of[k]] for k in order]
            normals = [normals[slot_of[k]] for k in order]
            weights = [weights[slot_of[k]] for k in order]
            tris = [[remap[v] for v in t] for t in tris]
            info_pos = [k[1] for k in order]
        else:
            info_pos = None
        objects[name] = {"positions": positions, "normals": normals, "triangles": tris, "uvs": uvs,
                         "materials": mats, "weights": [{str(k): v for k, v in w.items()} for w in weights]}
        owner = parent.get(ni)
        info[name] = {"submesh": ex.get("submesh"), "skinned": joints is not None,
                      "bone": bone_id(owner) if joints is None else None, "position_index": info_pos}
    scene = gl.get("scenes", [{}])[gl.get("scene", 0)] if gl.get("scenes") else {}
    info["base"] = scene.get("extras", {}).get("sluggers", {}).get("base", "")
    return objects, textures, info


# ------------------------------------------------------------------------------------------------ the check

def validate_glb(glb):
    """[problems] against the glTF 2.0 rules this writer relies on (no validator in the download): the GLB header,
    accessors inside their buffer views, POSITION min / max, indices and joints in range, weights summing to 1, one
    inverse bind matrix per joint, a tree of nodes (each child once, no cycles, the skinned node a scene root)."""
    out = []
    gl, binary = read_glb(glb)
    if gl.get("asset", {}).get("version") != "2.0":
        out.append("asset.version is not 2.0")
    views = gl.get("bufferViews", [])
    for i, v in enumerate(views):
        if v.get("byteOffset", 0) + v["byteLength"] > len(binary):
            out.append(f"bufferView {i} runs past the buffer")
    sizes = {5120: 1, 5121: 1, 5122: 2, 5123: 2, 5125: 4, 5126: 4}
    for i, a in enumerate(gl.get("accessors", [])):
        v = views[a["bufferView"]]
        if a.get("byteOffset", 0) + a["count"] * _N[a["type"]] * sizes[a["componentType"]] > v["byteLength"]:
            out.append(f"accessor {i} runs past its bufferView")
    children = [c for n in gl.get("nodes", []) for c in n.get("children", [])]
    if len(children) != len(set(children)):
        out.append("a node is the child of two nodes")
    roots = gl["scenes"][gl.get("scene", 0)]["nodes"]
    if set(roots) & set(children):
        out.append("a scene root is also a child")
    if len(set(roots) | set(children)) != len(gl.get("nodes", [])):
        out.append("a node is in no tree")
    for skin in gl.get("skins", []):
        if gl["accessors"][skin["inverseBindMatrices"]]["count"] != len(skin["joints"]):
            out.append("inverse bind matrices != joints")
    for ni, n in enumerate(gl.get("nodes", [])):
        if "mesh" not in n:
            continue
        if "skin" in n and ni not in roots:
            out.append(f"skinned node {ni} is not a scene root")
        for p in gl["meshes"][n["mesh"]]["primitives"]:
            at = p["attributes"]
            count = gl["accessors"][at["POSITION"]]["count"]
            pa = gl["accessors"][at["POSITION"]]
            if "min" not in pa or "max" not in pa:
                out.append("POSITION without min / max")
            if any(gl["accessors"][a]["count"] != count for a in at.values()):
                out.append("attributes of different lengths")
            idx = _read(gl, binary, p["indices"])
            if len(idx) % 3 or (len(idx) and idx.max() >= count):
                out.append("indices out of range")
            if "JOINTS_0" in at:
                nj = len(gl["skins"][n["skin"]]["joints"])
                total = np.zeros(count)
                for jn, wn in (("JOINTS_0", "WEIGHTS_0"), ("JOINTS_1", "WEIGHTS_1")):
                    if jn in at:
                        if _read(gl, binary, at[jn]).max() >= nj:
                            out.append("a joint index past the skin's joints")
                        total += _read(gl, binary, at[wn]).sum(1)
                if np.abs(total - 1).max() > 1e-3:
                    out.append("weights don't sum to 1")
    return sorted(set(out))


def round_trip(block, name=""):
    """block -> glb -> mesh; [problems] comparing positions, UVs, triangles and weights with the block's own."""
    b = bytes(block)
    m = Model(b)
    glb = block_to_glb(b, name)
    objects, textures, info = glb_to_mesh(glb)
    problems = validate_glb(glb)
    influences = m.skin.influences(b) if m.skin else {}
    for s in m.submeshes:
        oname = s.name or f"submesh{s.idx}"
        want = [t for _, _, _, _, tris in s.groups(b) for t in tris]
        if not want:
            continue
        o, meta = objects.get(oname), info.get(oname)
        if o is None:
            problems.append(f"{oname}: missing")
            continue
        pos = s.position.values(b)
        slots = meta["position_index"]
        got_pos = {slots[i]: p for i, p in enumerate(o["positions"])}
        if any(max(abs(a - c) for a, c in zip(got_pos[k], pos[k][:3])) > 1e-4 for k in got_pos):
            problems.append(f"{oname}: positions differ")
        uv0 = s.uvs[0].values(b) if s.uvs else None
        want_c = sorted((tuple(v["position"] for v in (t[0], t[2], t[1]) if WINDING_FLIP) if WINDING_FLIP else
                         tuple(v["position"] for v in t)) for t in want)
        got_c = sorted(tuple(slots[v] for v in t) for t in o["triangles"])
        if want_c != got_c:
            problems.append(f"{oname}: triangles differ ({len(got_c)} / {len(want_c)})")
        if uv0 is not None:
            wu = sorted(tuple(round(c, 5) for v in ((t[0], t[2], t[1]) if WINDING_FLIP else t) for c in uv0[v["tex0"]])
                        for t in want)
            gu = sorted(tuple(round(c, 5) for corner in uv for c in corner) for uv in o["uvs"])
            if wu != gu:
                problems.append(f"{oname}: UVs differ")
        if meta["skinned"]:
            for i, w in enumerate(o["weights"]):
                ref = influences.get(slots[i], {})
                tot = sum(ref.values()) or 1.0
                ref = {k: v / tot for k, v in sorted(ref.items(), key=lambda kv: -kv[1])[:8]}
                tot = sum(ref.values()) or 1.0
                if any(abs(float(w.get(str(k), 0.0)) - v / tot) > 2e-3 for k, v in ref.items()):
                    problems.append(f"{oname}: weights differ at position {slots[i]}")
                    break
    if len(textures) != len(m.textures):
        problems.append(f"textures {len(textures)} / {len(m.textures)}")
    return problems, glb


def winding_score(block):
    """Fraction of triangles whose face normal (after the flip) points the way their vertex normals do."""
    b = bytes(block)
    m = Model(b)
    agree = total = 0
    for s in m.submeshes:
        pos = s.position.values(b)
        nrm = s.normal.values(b) if s.normal else None
        for _, _, _, fmt, tris in s.groups(b):
            for t in tris:
                t = (t[0], t[2], t[1]) if WINDING_FLIP else t
                a, c, d = (np.array(pos[v["position"]][:3]) for v in t)
                fn = np.cross(c - a, d - a)
                vn = sum(np.array(nrm[v["normal"]][:3]) if nrm is not None and v.get("normal") is not None
                         else np.array(pos[v["position"]][3:6]) for v in t)
                if np.linalg.norm(fn) > 1e-9 and np.linalg.norm(vn) > 1e-9:
                    total += 1
                    agree += float(np.dot(fn, vn)) > 0
    return agree / max(total, 1)


def pose_score(block):
    """Mean distance from each skinned vertex to its heaviest bone's bind position (smaller is the right pose)."""
    b = bytes(block)
    m = Model(b)
    if not m.skin:
        return None
    world = {x["id"]: x["world"] for x in bones(b)}
    pos = m.submeshes[0].position.values(b)
    d = [np.linalg.norm(np.array(pos[slot][:3]) - world[max(w, key=w.get)][:3, 3])
         for slot, w in m.skin.influences(b).items() if slot < len(pos) and max(w, key=w.get) in world]
    return float(np.mean(d)) if d else None


def without_posindex(glb):
    """The same .glb with every _POSINDEX dropped (as a re-export may do), to test the welding path."""
    gl, binary = read_glb(glb)
    for mesh in gl.get("meshes", []):
        for p in mesh["primitives"]:
            p["attributes"].pop("_POSINDEX", None)
    js = json.dumps(gl, separators=(",", ":")).encode()
    js += b" " * (-len(js) % 4)
    return (struct.pack("<III", 0x46546C67, 2, 12 + 8 + len(js) + 8 + len(binary)) + struct.pack("<II", len(js), 0x4E4F534A)
            + js + struct.pack("<II", len(binary), 0x004E4942) + binary)


def weld_check(block):
    """[problems] of the welding path: without _POSINDEX, each mesh gets back one vertex per distinct position (and
    weights), the same triangles and the same positions."""
    b = bytes(block)
    m = Model(b)
    objects, _, _ = glb_to_mesh(without_posindex(block_to_glb(b)))
    out = []
    for s in m.submeshes:
        o = objects.get(s.name or f"submesh{s.idx}")
        tris = [t for _, _, _, _, tt in s.groups(b) for t in tt]
        if o is None or not tris:
            continue
        pos = s.position.values(b)
        used = {v["position"] for t in tris for v in t}
        want = {tuple(round(c, 5) for c in pos[i][:3]) for i in used}
        got = {tuple(round(c, 5) for c in p) for p in o["positions"]}
        if got != want or len(o["triangles"]) != len(tris):
            out.append(f"{s.name}: welded {len(o['positions'])} positions ({len(want)} distinct in the block), "
                       f"{len(o['triangles'])} / {len(tris)} triangles")
        wt = sorted(tuple(sorted(tuple(round(c, 5) for c in o["positions"][v]) for v in t)) for t in o["triangles"])
        bt = sorted(tuple(sorted(tuple(round(c, 5) for c in pos[v["position"]][:3]) for v in t)) for t in tris)
        if wt != bt:
            out.append(f"{s.name}: welded triangles differ")
    return out


def check(game=None, out_dir=None, data=None):
    """The round trip on every characters/*.json with model_blocks and on stock Mario, Boo and Bowser; one .glb per
    model under analysis/glb-check/. data: the folder models/work and analysis/ are in (default the repo; a worktree
    without them passes the main checkout). Returns [(name, problems)]; a missing block is a problem."""
    import glob
    import recolor
    data = data or ROOT
    game = game or os.path.join(data, "extracted/clean")
    out_dir = out_dir or os.path.join(data, "analysis/glb-check")
    os.makedirs(out_dir, exist_ok=True)
    blocks, out = [], []
    for p in sorted(glob.glob(os.path.join(ROOT, "characters/*.json"))):
        d = json.load(open(p, encoding="utf8"))
        path = (d.get("model_blocks") or {}).get("0")
        if path:
            full = path if os.path.isabs(path) else os.path.join(data, path)
            if os.path.exists(full):
                blocks.append((d["name"], open(full, "rb").read()))
            else:
                out.append((d["name"], [f"no block at {path}"]))
    g = recolor.Game(game)
    for cid, name in ((0x00, "Mario"), (0x0E, "Boo"), (0x09, "Bowser")):
        blocks.append((name, g.file(cid + 0x12, 0)))
        out.append((f"{name} (welded, no _POSINDEX)", weld_check(blocks[-1][1])))
    for name, blk in blocks:
        problems, glb = round_trip(blk, name)
        with open(os.path.join(out_dir, f"{name.lower().replace(' ', '-')}.glb"), "wb") as f:
            f.write(glb)
        out.append((name, problems))
    return out


if __name__ == "__main__":
    if sys.argv[1:2] == ["--check"]:
        arg = lambda k: sys.argv[sys.argv.index(k) + 1] if k in sys.argv else None  # noqa: E731
        results = check(arg("--game"), data=arg("--data"))
        for name, problems in results:
            print(("ok  " if not problems else "FAIL") + f" {name}" + ("" if not problems else ": " + "; ".join(problems)))
        sys.exit(1 if any(p for _, p in results) else 0)
    with open(sys.argv[1], "rb") as f:
        data = block_to_glb(f.read(), os.path.splitext(os.path.basename(sys.argv[1]))[0])
    with open(sys.argv[2], "wb") as f:
        f.write(data)
    print(f"wrote {sys.argv[2]} ({len(data)} bytes)")
