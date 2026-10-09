"""A player model edited with Jaws' Sluggies-dat-tools (a .sluggie file) as a NEW character (git-92, Beta 3 /
Patcher 12): the stock character it came from stays as it is.

  python scripts/sluggie.py check <file.sluggie> [--game extracted/clean]
  python scripts/sluggie.py add <file.sluggie> [--game extracted/clean] [--dest dir]

Our own reader, written from the format's schema and docs (refs/Sluggies-dat-tools: sluggieschema.json, _docs/, the
README); none of Sluggies' code is copied or run here (Sluggies has no licence; Jaws approved building on it). Thanks
to Jaws, whose Sluggies-dat-tools lets players export, edit in Blender and re-export the game's player models.

A .sluggie is JSON: {"SluggiesModel": {ChunkNumber (the dt_na dir: a player's model dir is stock id + 0x12),
FileIndex (0 = the model, 1 = its low-detail copy), ModelOffset / ModelLength (the file in dt_na.dat), every buffer
of the model with its absolute dt_na offset and original bytes, and the Blender exporter's "...Edited" copies}}. Its
PNGs are in the tex/ folder beside it. apply() writes each edit into the clean block at offset - ModelOffset:
  - Submeshes[].VertexBuffer.VertexBufferDataEdited (positions; 6-component skinned buffers carry their normals)
  - UVChannels[].UVChannelDataEdited, ColorChannels[].ColorChannelDataEdited, NormalBuffer.NormalBufferDataEdited
    (the same size, or Hammerspace mode's one entry per face corner folded back onto the original entries)
  - DisplayStates[].DisplayStateParamBytesEdited (3 bytes at DisplayStateParamBytesFieldOffset)
  - SkinData SK1s / SK2s / SKAccs BindPoseDataEdited (at VertexArrAbsolutePtr + VertexOffset), WeightDataEdited;
    SkinDataEdited when its entries match SkinData's one for one
  - FacialPoseDataEdited (each pose at the object's PoseAbsoluteOffsets[PoseIndex])
  - RootBoneScaleEdited (3 floats at the main root bone's SRTOffset + 4)
  - tex/<TextureFileName> PNGs that differ from the clean texture (by more than an --untangle export's one 4x4
    block): the changed 4x4 blocks (a tile, for tiled
    formats) re-encoded in the texture's own format and size (wimgt through build_model.encode_texture), the rest
    kept byte for byte (so an untangled export's texture only changes where it was untangled)
What would change the model's shape (faces, vertex count, bones, skinning groups, added textures or submeshes:
Sluggies' Hammerspace mode) is refused in plain words; a Hammerspace export whose edits fit in place is applied.
"""
import argparse, base64, hashlib, json, math, os, re, shutil, struct, sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
sys.path.insert(0, str(HERE / "patcher"))

MODEL_DIR_BASE = 0x12               # charbuild.MODEL_DIR_BASE
PLAYABLE = 0x47                     # charpack.PLAYABLE: stock ids a template may be
MODEL_FILES = (0, 1)
SUFFIX = ".sluggie"
MAX_FILE = 64 << 20                 # a .sluggie is ~1 MB per model; refuse anything absurd before json.load
ENCODABLE = {14: "CMPR", 5: "RGB5A3", 4: "RGB565", 6: "RGBA8"}     # build_model.WIMGT_TARGETS
TILES = {14: (8, 8, 32), 5: (4, 4, 32), 4: (4, 4, 32), 6: (4, 4, 64)}   # tile w, h, bytes
UNTANGLED = 1                       # 4x4 blocks: Sluggies' --untangle export changes one block of a texture shared
                                    # with another model (every player texture: 0 or 1, measured); not an edit
HOW = ("Export it from Blender again with \"Use Hammerspace\" off: the patcher adds models whose edits keep the "
       "original vertices, faces, bones and textures in place")

DATA = dict(                        # the window's "i" (widgets.data_text keys; git-92's modder layer)
    file="dt_na.dat: the new character's own copy of its model file (file 0 of the dir its template's id + 0x12 "
         "points at: charbuild gives an added character a model dir of its own)",
    where="each edited buffer at its .sluggie offset minus ModelOffset: vertex positions (6-component skinned "
          "buffers carry their normals), UVs, vertex colours, normals, the SKN bind pose and weights, facial poses, "
          "material settings, the root bone's scale (then the skinned bind pose scaled with it); a repainted "
          "picture's changed 4x4 blocks re-encoded in its own format",
    text="The stock character's files are untouched. The new character is kept with the imported ones (the "
         "Sluggers Patcher folder in your AppData), its model as a delta against your clean game.",
    source="scripts/sluggie.py (our own reader of Jaws' .sluggie format, from its schema and docs)")


class SluggieError(Exception):
    """A .sluggie that can't be added; the text is for the player."""


# ---- reading

class Sluggie:
    """A .sluggie file: .m (the SluggiesModel dict), .dir / .index (its dt_na file), .template (the stock id),
    .offset / .length (its dt_na span), .tex (the tex/ folder beside it)."""

    def __init__(self, path):
        self.path = Path(path)
        if self.path.is_dir() or self.path.suffix.lower() == ".png":
            raise SluggieError(f"{self.path.name} has no .sluggie file and no texture-pack pictures (Dolphin's "
                               f"tex1_..._<hash>_<format>.png) that fit a character's model")
        try:
            if self.path.stat().st_size > MAX_FILE:
                raise SluggieError(f"{self.path.name} is too big to be a .sluggie")
            doc = json.loads(self.path.read_text(encoding="utf8"))
        except (OSError, UnicodeDecodeError, ValueError):
            raise SluggieError(f"{self.path.name} isn't a .sluggie file (Sluggies-dat-tools' export) or is damaged")
        m = doc.get("SluggiesModel") if isinstance(doc, dict) else None
        if not isinstance(m, dict) or not all(k in m for k in ("ChunkNumber", "FileIndex", "ModelOffset",
                                                                "ModelLength", "Submeshes")):
            raise SluggieError(f"{self.path.name} isn't a .sluggie file (Sluggies-dat-tools' export) or is damaged")
        self.m = m
        self.dir, self.index = int(m["ChunkNumber"]), int(m["FileIndex"])
        self.template = self.dir - MODEL_DIR_BASE
        self.offset, self.length = num(m["ModelOffset"]), int(m["ModelLength"])
        self.tex = self.path.parent / "tex"

    @property
    def player_model(self):
        return 0 <= self.template < PLAYABLE and self.index in MODEL_FILES


def read(path):
    return Sluggie(path)


def num(v):
    """An offset: an int, or Sluggies' hex string ("0x5e52b60")."""
    return int(v, 16) if isinstance(v, str) else int(v)


def data(v):
    """A buffer: base64 (UseBase64), a hex string (DisplayStateParamBytes), or a list of byte values (--debug)."""
    if v is None:
        return None
    if isinstance(v, list):
        return bytes(v)
    try:
        return base64.b64decode(v, validate=True)
    except ValueError:
        return bytes.fromhex(v)


def u16s(v):
    b = data(v) or b""
    return list(struct.unpack(f">{len(b) // 2}H", b[:len(b) // 2 * 2]))


# ---- the edits

class Edits:
    """What apply() writes: [(block offset, bytes, what)], the problems that stop it, and plain-words notes."""

    def __init__(self, s, clean):
        self.s, self.clean = s, clean
        self.writes, self.problems, self.changes, self.mismatch = [], [], [], []
        self.scale = None               # RootBoneScaleEdited, when it changes the size (_scale_skin)
        self.notes = []                 # plain words for the window, not problems

    def rel(self, absolute, n, what):
        r = num(absolute) - self.s.offset
        if not 0 <= r <= len(self.clean) - n:
            self.problems.append(f"{what} is outside the model")
            return None
        return r

    def original(self, absolute, orig, what):
        """The block offset of an original buffer, checking the clean game has the same bytes there."""
        if orig is None:
            return None
        r = self.rel(absolute, len(orig), what)
        if r is not None and self.clean[r:r + len(orig)] != orig:
            self.mismatch.append(what)
        return r

    def write(self, r, new, what):
        if r is not None and self.clean[r:r + len(new)] != new:
            self.writes.append((r, bytes(new), what))
            return True
        return False


def _fold(orig, orig_idx, new, new_idx, what):
    """An edited buffer as the original's entries: the same size as it is, or (Hammerspace mode) one entry per face
    corner (new_idx: which of `new`'s entries each corner uses; absent: corner k uses entry k) folded back onto the
    entries the original's corners use (orig_idx). Returns (bytes, problem)."""
    if new_idx is None and len(new) == len(orig):
        return new, None
    loops = len(orig_idx)
    if not loops or new_idx is not None and len(new_idx) != loops:
        return None, f"{what} changed size (vertices or faces were added or removed)"
    n_new = len(new_idx) and max(new_idx) + 1 if new_idx is not None else loops
    if len(new) % n_new:
        return None, f"{what} changed size (vertices or faces were added or removed)"
    size = len(new) // n_new
    if not size or len(orig) % size or max(orig_idx) >= len(orig) // size:
        return None, f"{what} changed size (vertices or faces were added or removed)"
    out, seen = bytearray(orig), {}
    for k, o in enumerate(orig_idx):
        j = new_idx[k] if new_idx is not None else k
        v = new[j * size:(j + 1) * size]
        if seen.setdefault(o, v) != v:
            return None, f"{what} splits a point the original shares (a new UV seam or split normal)"
        out[o * size:(o + 1) * size] = v
    return bytes(out), None


def _submesh(e, k, sm):
    name = f"{sm.get('MeshName') or 'submesh'} ({k})"
    faces, faces_new = data(sm.get("FacesData")), data(sm.get("FacesDataEdited"))
    if sm.get("FacesCountEdited") is not None and int(sm["FacesCountEdited"]) != int(sm.get("FacesCount", -1)) or \
            faces_new is not None and faces_new != faces:
        e.problems.append(f"{name}: its faces changed. {HOW}")
        return
    for key, orig_key in (("FaceTextureIndicesEdited", "FaceTextureIndices"), ("FaceSurfaceIdsEdited", None)):
        if sm.get(key) is not None and (orig_key is None or data(sm[key]) != data(sm.get(orig_key))):
            e.problems.append(f"{name}: its faces use other materials or textures now. {HOW}")
            return
    vb = sm.get("VertexBuffer") or {}
    vorig = data(vb.get("VertexBufferData"))
    vr = e.original(vb.get("VertexBufferOffset", 0), vorig, f"{name} vertices")
    vnew = data(vb.get("VertexBufferDataEdited"))
    if vnew is not None and vorig is not None:
        if len(vnew) != len(vorig):
            e.problems.append(f"{name}: vertices were added or removed. {HOW}")
        elif e.write(vr, vnew, f"{name} vertices"):
            e.changes.append(f"moved vertices on {name}")
    for ch in sm.get("UVChannels") or []:
        _channel(e, name, "UVs", ch, "UVChannelOffset", "UVChannelData", "UVFacesData", "UVFacesDataEdited")
    for ch in sm.get("ColorChannels") or []:
        _channel(e, name, "vertex colors", ch, "ColorChannelOffset", "ColorChannelData", "ColorFacesData",
                 "ColorFacesDataEdited")
    nb = sm.get("NormalBuffer")
    if nb:
        inside = vorig is not None and vr is not None and nb.get("NormalBufferOffset") is not None and \
            0 < num(nb["NormalBufferOffset"]) - num(vb["VertexBufferOffset"]) < len(vorig)
        stride = None
        if inside:                      # a 6-component (skinned) buffer: normals sit between the positions
            from mss_model import comp_size
            stride = comp_size(int(vb.get("VertexBufferQuantizeInfo", 0))) * int(vb.get("VertexBufferCompCount", 6))
        _channel(e, name, "normals", nb, "NormalBufferOffset", "NormalBufferData", "NormalFacesData",
                 "NormalFacesDataEdited", stride=stride, vertex_edit=vnew is not None)
    for ds in sm.get("DisplayStates") or sm.get("DrawStates") or []:
        mode = _fourcc(ds.get("ShaderMode"))
        if mode is not None and ds.get("ShaderModeFieldOffset") is not None:     # written as it is (Blender's
            what = f"{name} material {ds.get('SurfaceId', '')}".rstrip()           # material settings)
            if e.write(e.rel(ds["ShaderModeFieldOffset"], 4, what), mode, what):
                e.changes.append(f"changed the look of {what}")
        new = ds.get("DisplayStateParamBytesEdited")
        if new is None:
            continue
        orig, new = data(ds.get("DisplayStateParamBytes")), data(new)
        what = f"{name} material {ds.get('SurfaceId', '')}".rstrip()
        if orig is None or len(new) != len(orig):
            e.problems.append(f"{what}: its settings can't be read")
            continue
        r = e.original(ds["DisplayStateParamBytesFieldOffset"], orig, what)
        if e.write(r, new, what):
            e.changes.append(f"changed the shine of {what}")


def _fourcc(v):
    """ShaderMode: a FourCC ("TOON") or 8 hex digits -> 4 bytes (None: unreadable)."""
    if not isinstance(v, str):
        return None
    if len(v) == 8:
        try:
            return bytes.fromhex(v)
        except ValueError:
            pass
    return v.encode("latin-1") if len(v) == 4 else None


def _channel(e, name, label, ch, off_key, data_key, idx_key, idx_new_key, stride=None, vertex_edit=False):
    orig = data(ch.get(data_key))
    new = data(ch.get(data_key + "Edited"))
    what = f"{name} {label}"
    r = e.original(ch.get(off_key, 0), orig, what)
    if new is None or orig is None:
        return
    new_idx = u16s(ch[idx_new_key]) if ch.get(idx_new_key) is not None else None
    if new_idx is not None and new_idx == u16s(ch.get(idx_key)) and len(new) == len(orig):
        new_idx = None
    folded, problem = _fold(orig, u16s(ch.get(idx_key)), new, new_idx, what)
    if problem:
        e.problems.append(f"{problem}. {HOW}")
        return
    if stride:                          # normals between the positions (stride: one vertex): only their own half of
        if vertex_edit:                 # each vertex is this channel's, and an edited vertex buffer carries them
            return
        out = bytearray(e.clean[r:r + len(orig)])
        for k in range(0, len(orig) - stride // 2 + 1, stride):
            out[k:k + stride // 2] = folded[k:k + stride // 2]
        folded = bytes(out)
    if e.write(r, folded, what):
        e.changes.append(f"changed the {label} of {name}")


def _skin(e):
    sk = e.s.m.get("SkinData") or {}
    for kind in ("SK1s", "SK2s", "SKAccs"):
        for k, ent in enumerate(sk.get(kind) or []):
            what = f"skinning {kind[:-1]} {k}"
            bind = data(ent.get("BindPoseData"))
            r = e.original(ent.get("VertexArrAbsolutePtr", 0), bind, what)
            vo = int(ent.get("VertexOffset") or 0)
            new = data(ent.get("BindPoseDataEdited"))
            if new is not None and bind is not None:     # today's exporter: no VertexOffset prefix; older ones
                at = {len(bind) - vo: vo, len(bind): 0}.get(len(new))    # (the community's mods): with it
                if at is None:
                    e.problems.append(f"{what}: vertices were added or removed. {HOW}")
                elif e.write(r + at if r is not None else None, new, what):
                    e.changes.append("moved skinned vertices")
            w = data(ent.get("WeightData"))
            wr = e.original(ent.get("WeightArrAbsolutePtr", 0), w, what + " weights")
            wnew = data(ent.get("WeightDataEdited"))
            if wnew is not None and w is not None:
                if len(wnew) != len(w):
                    e.problems.append(f"{what}: its bone weights changed size. {HOW}")
                elif e.write(wr, wnew, what + " weights"):
                    e.changes.append("changed bone weights")
    edited = e.s.m.get("SkinDataEdited")
    if not edited:
        return
    same = all(len(sk.get(kind) or []) == len(edited.get(kind) or []) for kind in ("SK1s", "SK2s", "SKAccs")) and \
        all(int(a.get(f, -1)) == int(b.get(f, -1)) for kind in ("SK1s", "SK2s", "SKAccs")
            for a, b in zip(sk.get(kind) or [], edited.get(kind) or [])
            for f in ("BoneIndex", "BoneIndex1", "BoneIndex2", "VertexCnt") if f in a or f in b)
    if not same:
        e.problems.append(f"the skinning changed (vertices moved to other bones). {HOW}")
        return
    for kind in ("SK1s", "SK2s", "SKAccs"):
        for k, (a, b) in enumerate(zip(sk.get(kind) or [], edited.get(kind) or [])):
            what = f"skinning {kind[:-1]} {k}"
            vo = int(a.get("VertexOffset") or 0)
            for key, ptr, skip in (("BindPoseData", "VertexArrAbsolutePtr", vo), ("WeightData", "WeightArrAbsolutePtr",
                                                                                    0),
                                   ("DestIndexData", "DestArrAbsolutePtr", 0)):
                new, orig = data(b.get(key)), data(a.get(key))
                if new is None or a.get(ptr) is None:
                    continue
                n = len(orig) - skip if orig is not None else len(new)
                if len(new) != n:
                    e.problems.append(f"{what}: the skinning changed size. {HOW}")
                    continue
                r = e.rel(num(a[ptr]) + skip, n, what)
                if orig is not None and r is not None and e.clean[r:r + n] != orig[skip:]:
                    e.mismatch.append(what)
                if e.write(r, new, what):
                    e.changes.append("changed the skinning")


def _faces(e):
    fp = e.s.m.get("FacialPoseData") or {}
    objs = {int(o.get("ObjectIndex", i)): o for i, o in enumerate(fp.get("Objects") or [])}
    for o in objs.values():
        pos = o.get("Position") or {}
        for k, (off, orig) in enumerate(zip(pos.get("PoseAbsoluteOffsets") or [], pos.get("PoseData") or [])):
            e.original(off, data(orig), f"facial pose {k}")
    for oe in (e.s.m.get("FacialPoseDataEdited") or {}).get("Objects") or []:
        o = objs.get(int(oe.get("ObjectIndex", -1)))
        pos = (o or {}).get("Position") or {}
        for pe in oe.get("PositionPoseEdits") or []:
            i = int(pe.get("PoseIndex", -1))
            offs, poses = pos.get("PoseAbsoluteOffsets") or [], pos.get("PoseData") or []
            what = f"facial expression {i}"
            if not 0 <= i < min(len(offs), len(poses)):
                e.problems.append(f"{what} isn't one of the model's")
                continue
            new, orig = data(pe.get("PoseData")), data(poses[i])
            if len(new) != len(orig):
                e.problems.append(f"{what} changed size. {HOW}")
            elif e.write(e.rel(offs[i], len(new), what), new, what):
                e.changes.append("changed facial expressions")


def _bones(e):
    m = e.s.m
    bones = m.get("BoneHierarchy") or []
    if m.get("BoneHierarchyEdited") is not None:
        a = [(b.get("BoneId"), b.get("ParentBoneId"), b.get("GeoId")) for b in bones]
        b = [(x.get("BoneId"), x.get("ParentBoneId"), x.get("GeoId")) for x in m["BoneHierarchyEdited"]]
        moved = any(any(abs(float(p) - float(q)) > 1e-4 for key in ("Translation", "Scale", "Quaternion")
                        for p, q in zip(x.get(key) or [], y.get(key) or []))
                    for x, y in zip(bones, m["BoneHierarchyEdited"]))
        if a != b or moved or any(x.get("UserAdded") for x in m["BoneHierarchyEdited"]):
            e.problems.append(f"the bones changed. {HOW}")
    for b in bones:                     # a bone's mesh (GeoIdRaw), written as it is
        if b.get("GeoIdFieldOffset") is not None and b.get("GeoIdRaw") is not None:
            what = f"bone {b.get('BoneId')}"
            if e.write(e.rel(b["GeoIdFieldOffset"], 2, what), struct.pack(">H", int(b["GeoIdRaw"]) & 0xFFFF), what):
                e.problems.append(f"{what} draws another part now. {HOW}")
    scale = m.get("RootBoneScaleEdited")
    if scale is None or [float(v) for v in scale] == [1.0, 1.0, 1.0]:
        return
    if len(scale) != 3 or not all(math.isfinite(float(v)) and 0 < float(v) < 100 for v in scale):
        e.problems.append("the model's scale isn't three positive numbers")
        return
    roots = [b for b in bones if b.get("ParentBoneId") is None and b.get("SRTOffset") is not None]
    roots.sort(key=lambda b: (b.get("MirrorRole") != 1, b.get("BoneId", 0)))
    if not roots:
        e.problems.append("the model's scale changed, but its root bone has no scale to change")
        return
    r = e.rel(num(roots[0]["SRTOffset"]) + 4, 12, "the root bone's scale")
    if e.write(r, struct.pack(">3f", *map(float, scale)), "the root bone's scale"):
        e.changes.append("changed the model's size")
        e.scale = [float(v) for v in scale]
        from mss_model import comp_size
        if comp_size(int((m.get("SkinData") or {}).get("QuantizeInfo", 0))) != 2:
            e.problems.append("the model's size changed, but its skinning is stored in a way the patcher can't "
                              "scale yet")


def _scale_skin(e, out):
    """The skinned vertices' bind pose scaled with the root bone (Sluggies' in-place patcher does the same: the
    root's scale alone leaves skinned parts their old size): each entry's positions (x, y, z of the 6 components;
    normals kept) times the scale (the .sluggie's numbers, not float32), rounded half to even, as they are after the
    other edits."""
    sk = e.s.m.get("SkinData") or {}
    for kind in ("SK1s", "SK2s", "SKAccs"):
        for ent in sk.get(kind) or []:
            r = num(ent["VertexArrAbsolutePtr"]) - e.s.offset + int(ent.get("VertexOffset") or 0)
            for v in range(int(ent.get("VertexCnt") or 0)):
                for c in range(3):
                    o = r + v * 12 + c * 2
                    x = struct.unpack_from(">h", out, o)[0] * e.scale[c]
                    struct.pack_into(">h", out, o, max(-32768, min(32767, round(x))))    # (half to even)


def _surface_textures(clean):
    """{SurfaceId: the texture bound on layer 0 when that display state runs} (the clean model)."""
    from mss_model import Model, DS_TEXTURE
    out = {}
    for k, sm in enumerate(Model(clean).submeshes):
        binds = {}
        for i, ds in enumerate(sm.states):
            if ds.type == DS_TEXTURE:
                binds[ds.texture[1]] = ds.texture[0]
            out[f"sm{k}_ds{i}"] = binds.get(0)
    return out


def _extras(e):
    m = e.s.m
    if m.get("CustomSubmeshes"):
        e.problems.append(f"it adds new parts (submeshes). {HOW}")
    if m.get("AdditionalTextureDescriptors"):
        e.problems.append(f"it adds new textures. {HOW}")
    want = m.get("DesiredTextureAssignments") or {}
    if want:
        try:
            have = _surface_textures(e.clean)
        except Exception:
            have = {}
        if any(have.get(sid) != int(t) for sid, t in want.items()):
            e.problems.append(f"it puts other textures on its materials. {HOW}")


DUMP_NAME = re.compile(r"tex1_(\d+)x(\d+)_.*_(\d+)\.png$", re.I)     # Dolphin's texture dump names


def _pngs(e, descs, texs):
    """[(texture index, PNG path, descriptor)]: each descriptor's TextureFileName in tex/ or beside the .sluggie;
    a file without names (older exports, the community's mods) by Dolphin's dump name tex1_<w>x<h>_<hash>_<format>
    .png beside it or in tex/: the texture of that size and format (several: the one whose clean picture is closest)."""
    import numpy as np
    from PIL import Image
    dirs = [d for d in (e.s.tex, e.s.path.parent) if d.is_dir()]
    if any(d.get("TextureFileName") for d in descs):
        out = []
        for k, d in enumerate(descs):
            name = d.get("TextureFileName")
            png = next((x / name for x in dirs if name and Path(name).name == name and (x / name).is_file()), None)
            if png is not None:
                out.append((int(d.get("TextureIndex", k)), png, d))
        return out
    out = []
    for png in sorted({p for x in dirs for p in x.glob("tex1_*.png")}):
        mt = DUMP_NAME.match(png.name)
        if not mt:
            continue
        w, h, f = map(int, mt.groups())
        cands = [i for i, t in enumerate(texs) if (t.width, t.height, t.format) == (w, h, f)
                 and i not in {o[0] for o in out}]         # one picture per texture
        if not cands:
            e.notes.append(f"{png.name} isn't one of this model's pictures (another of the character's files, e.g. "
                           f"the bat or a glove): left out")
            continue
        if len(cands) > 1:
            try:
                img = np.asarray(Image.open(png).convert("RGBA")).astype(int)
                cands.sort(key=lambda i: abs(np.asarray(_decode(e.clean, texs[i], descs[i] if i < len(descs) else
                                                                None)).astype(int) - img).mean())
            except Exception:
                pass
        if cands:
            out.append((cands[0], png, descs[cands[0]] if cands[0] < len(descs) else {}))
    return out


def _textures(e):
    """Each PNG (tex/ or beside the .sluggie) against the clean texture: the changed blocks re-encoded, the rest
    kept."""
    from mss_model import Model
    descs = e.s.m.get("TextureDescriptors") or []
    try:
        texs = Model(e.clean).textures
    except Exception:
        texs = []
    if not texs:
        return
    for i, png, d in _pngs(e, descs, texs):
        name = png.name
        what = f"texture {i} ({name})"
        if not 0 <= i < len(texs) or d.get("ImageDataOffset") is not None and                 texs[i].image != num(d["ImageDataOffset"]) - e.s.offset:
            e.mismatch.append(what)
            continue
        payload, problem, note = _repaint(e.clean, texs[i], png, d)
        if note:
            e.notes.append(note)
        if problem:
            e.problems.append(f"{what} {problem}")
        elif payload is not None and e.write(texs[i].image, payload, what):
            e.changes.append(f"repainted {what}")


def _repaint(block, t, png, d=None):
    """A PNG as texture t of block -> (payload or None when it's unchanged, a problem ("..." after the texture's name)
    or None, a note or None): the changed 4x4 blocks re-encoded, the rest kept; a Dolphin texture pack's 2x / 4x
    picture scaled to fit; a difference of one block (--untangle) isn't an edit."""
    import numpy as np
    from PIL import Image
    d = d or {}
    name, note = png.name, None
    try:
        img = Image.open(png)
        img.load()
        img = img.convert("RGBA")
    except Exception:
        return None, "can't be read as a picture", None
    k = img.width // t.width if t.width else 0             # a Dolphin texture pack's larger picture (2x, 4x): scaled
    if DUMP_NAME.match(name) and k > 1 and (img.width, img.height) == (t.width * k, t.height * k):      # to fit
        note = f"{name} is {img.width}x{img.height} (a texture pack's {k}x picture): scaled to {t.width}x{t.height}"
        img = img.resize((t.width, t.height), Image.LANCZOS)
    if (img.width, img.height) != (t.width, t.height):
        return None, f"is {img.width}x{img.height}; it has to stay {t.width}x{t.height}. {HOW}", note
    new = np.asarray(img)
    before = np.asarray(_decode(block, t, d))
    diff = (before != new).any(axis=2)
    if len({(y // 4, x // 4) for y, x in zip(*np.nonzero(diff))}) <= UNTANGLED:
        return None, None, note
    if t.palette is not None or t.format not in ENCODABLE:
        return None, "was repainted, but it uses a palette the patcher can't write yet: leave that picture as it was", note
    if int(d.get("AdditionalMipCount") or 0):
        return None, ("was repainted, but it has smaller copies (mipmaps) the patcher can't write yet: leave that "
                      "picture as it was"), note
    size = t.payload_size()
    return _splice(block[t.image:t.image + size], before, new, t.format, t.width, t.height), None, note


def _decode(block, tex, desc=None):
    """A clean texture -> RGBA (wimgt; a paletted one here: C4 / C8 with an IA8 / RGB565 / RGB5A3 palette)."""
    if tex.palette is None:
        from recolor_block import decode
        return decode(bytes(block), tex).convert("RGBA")
    from PIL import Image
    fmt, pal_fmt = tex.format, int((desc or {}).get("PaletteFormat", 2))
    n = int((desc or {}).get("PaletteEntries") or (16 if fmt == 8 else 256))
    pal = [_color(v, pal_fmt) for v in struct.unpack_from(f">{n}H", block, tex.palette)]
    if fmt not in (8, 9):
        raise SluggieError(f"texture format {fmt} can't be read")
    tw, th = (8, 8) if fmt == 8 else (8, 4)
    tiles_x = -(-tex.width // tw)
    img = Image.new("RGBA", (tex.width, tex.height))
    px = img.load()
    for y in range(tex.height):
        for x in range(tex.width):
            k = (y // th * tiles_x + x // tw) * 32
            i = (y % th) * tw + x % tw
            if fmt == 9:
                v = block[tex.image + k + i]
            else:
                v = block[tex.image + k + i // 2] >> (0 if i % 2 else 4) & 15
            px[x, y] = pal[v] if v < n else (0, 0, 0, 0)
    return img


def _color(v, fmt):
    """A palette entry -> RGBA, channels scaled to 0-255 and rounded (as wimgt's PNGs have them)."""
    c = lambda x, top: (x * 255 * 2 + top) // (2 * top)  # noqa: E731
    if fmt == 2:                                                    # RGB5A3
        if v & 0x8000:
            return c(v >> 10 & 31, 31), c(v >> 5 & 31, 31), c(v & 31, 31), 255
        return (v >> 8 & 15) * 17, (v >> 4 & 15) * 17, (v & 15) * 17, c(v >> 12 & 7, 7)
    if fmt == 1:                                                    # RGB565
        return c(v >> 11 & 31, 31), c(v >> 5 & 63, 63), c(v & 31, 31), 255
    return v & 255, v & 255, v & 255, v >> 8                        # IA8


def _splice(clean, before, after, fmt, width, height):
    """The texture payload with only the blocks whose pixels changed re-encoded (CMPR: 4x4 blocks; the other
    formats: whole tiles)."""
    import numpy as np
    from PIL import Image
    from build_model import encode_texture
    enc = encode_texture(Image.fromarray(np.ascontiguousarray(after), "RGBA"), fmt, len(clean))
    out = bytearray(clean)
    tw, th, tb = TILES[fmt]
    tiles_x = -(-width // tw)
    if fmt == 14:
        import cmpr
        for by in range(-(-height // 4)):
            for bx in range(-(-width // 4)):
                y, x = by * 4, bx * 4
                if not np.array_equal(before[y:y + 4, x:x + 4], after[y:y + 4, x:x + 4]):
                    o = cmpr._block_offset(tiles_x * 8, bx, by)
                    out[o:o + 8] = enc[o:o + 8]
        return bytes(out)
    for ty in range(-(-height // th)):
        for tx in range(tiles_x):
            y, x = ty * th, tx * tw
            if not np.array_equal(before[y:y + th, x:x + tw], after[y:y + th, x:x + tw]):
                o = (ty * tiles_x + tx) * tb
                out[o:o + tb] = enc[o:o + tb]
    return bytes(out)


def edits(s, clean):
    """The Edits of Sluggie s against the clean block."""
    e = Edits(s, clean)
    for k, sm in enumerate(s.m.get("Submeshes") or []):
        _submesh(e, k, sm)
    _skin(e)
    _faces(e)
    _bones(e)
    _extras(e)
    if not e.mismatch:
        _textures(e)
    spans = sorted(e.writes)
    for (a, x, wa), (b, y, wb) in zip(spans, spans[1:]):
        if b < a + len(x):
            n = min(a + len(x), b + len(y)) - b
            if x[b - a:b - a + n] != y[:n]:
                e.problems.append(f"{wa} and {wb} change the same bytes differently")
    return e


# ---- against the player's game

def clean_block(s, game):
    """The template's stock file from the player's (clean) game, or SluggieError."""
    import charpack
    with charpack.sources(game) as srcs:
        try:
            block = charpack.stock_file(game, srcs, s.template, s.index)
        except charpack.PackError as e:
            raise SluggieError(str(e))
    return block


def _name(tid):
    from sluggers_data import CHAR_NAMES
    return CHAR_NAMES[tid].strip()


def check(path, game):
    """Plain-words problems ([] = it can be added): not a player model, the original data doesn't match the player's
    clean game, an edit we can't apply yet (a texture pack: no picture matches a character's)."""
    if is_texture_pack(path):
        return describe(path, game)["problems"]
    try:
        return _checked(path, game)[2]
    except SluggieError as e:
        return [str(e)]


def _checked(path, game):
    s = read(path)
    if not s.player_model:
        what = "a player's model" if 0 <= s.template < PLAYABLE else "a character's model"
        return s, None, [f"{s.path.name} isn't {what} (it's file {s.index} of dt_na folder {s.dir}): pick the "
                         f".sluggie of a character's body model (its first file, e.g. 98904928_daisy.gpl.sluggie)"]
    tname = _name(s.template)
    block = clean_block(s, Path(game))
    if block is None or len(block) != s.length:
        return s, None, [f"{s.path.name} doesn't match {tname}'s model in your game: export it again from your clean "
                         f"(unpatched) game"]
    e = edits(s, block)
    if e.mismatch:
        return s, e, [f"{s.path.name}'s original model data doesn't match {tname}'s model in your clean game "
                      f"({', '.join(e.mismatch[:3])}{'...' if len(e.mismatch) > 3 else ''}): export it with "
                      f"Sluggies-dat-tools from your clean (unpatched) game, then edit it again"]
    return s, e, e.problems


def apply(path, game):
    """{file index: new block bytes}: the template's clean block with every edit written in. SluggieError (every
    problem, plain words) when it can't be applied."""
    return _apply(*_checked(path, game))


def _apply(s, e, problems):
    if problems:
        raise SluggieError("; ".join(problems))
    out = bytearray(e.clean)
    for r, b, _ in e.writes:
        out[r:r + len(b)] = b
    if e.scale:
        _scale_skin(e, out)
    return {s.index: bytes(out)}


def siblings(path):
    """[path, then the other model file's .sluggie beside it]: a character's two models (file 0 and its low-detail
    file 1) are exported side by side (the community's mods ship both); picking either adds both."""
    path = Path(path)
    try:
        s = read(path)
    except SluggieError:
        return [path]
    out = [path]
    if not s.player_model:
        return out
    for p in sorted(path.parent.glob("*" + SUFFIX)) + sorted(path.parent.glob("*/*" + SUFFIX)):
        if p.resolve() == path.resolve():
            continue
        try:
            o = read(p)
        except SluggieError:
            continue
        if o.dir == s.dir and o.index in MODEL_FILES and o.index not in {read(q).index for q in out}:
            out.append(p)
    return sorted(out, key=lambda p: read(p).index)          # the model first, then its low-detail copy


def _checked_all(path, game):
    """_checked for path and its siblings: [(s, e, problems)]."""
    return [_checked(p, game) for p in siblings(path)]


def describe(path, game):
    """{"template": name, "index", "files": [names], "changes": [plain words], "problems": [...], "notes": [...]} for
    the window: the picked file and its sibling (siblings()), or a texture pack (a folder or a PNG in it)."""
    if is_texture_pack(path):
        try:
            tid, blocks, changes, problems, notes = _texture_pack_blocks(path, game)
        except SluggieError as err:
            return {"problems": [str(err)], "changes": [], "notes": []}
        folder = Path(path) if Path(path).is_dir() else Path(path).parent
        return {"template": _name(tid), "template_id": tid, "index": min(blocks, default=0),
                "files": [folder.name], "changes": changes, "problems": problems, "notes": notes, "pack": True}
    try:
        group = _checked_all(path, game)
    except SluggieError as err:
        return {"problems": [str(err)], "changes": [], "notes": []}
    s = group[0][0]
    many = len(group) > 1
    tag = lambda x: ("low-detail model: " if x.index == 1 else "model: ") if many else ""  # noqa: E731
    return {"template": _name(s.template) if s.player_model else None, "template_id": s.template, "index": s.index,
            "files": [x.path.name for x, _, _ in group],
            "changes": list(dict.fromkeys(tag(x) + c for x, e, _ in group if e for c in e.changes)),
            "problems": [(x.path.name + ": " if many else "") + p for x, _, ps in group for p in ps],
            "notes": list(dict.fromkeys(n for _, e, _ in group if e for n in e.notes))}


# ---- a texture pack (Beta 3.5, Nick: Shantaeni Kong): a character's pictures as Dolphin dumps them, no .sluggie

_M64 = (1 << 64) - 1
_P = (11400714785074694791, 14029467366897019727, 1609587929392839161, 9650029242287828579, 2870177450012600261)


def xxh64(data, seed=0):
    """XXH64 (the public xxHash algorithm), which Dolphin names its texture dumps by (tex1_<w>x<h>_<hash>_<fmt>.png:
    the hash of the texture's data as the game has it)."""
    p1, p2, p3, p4, p5 = _P
    rotl = lambda x, r: ((x << r) | (x >> (64 - r))) & _M64  # noqa: E731
    rnd = lambda acc, lane: rotl((acc + lane * p2) & _M64, 31) * p1 & _M64  # noqa: E731
    n, i = len(data), 0
    if n >= 32:
        v = [(seed + p1 + p2) & _M64, (seed + p2) & _M64, seed, (seed - p1) & _M64]
        lanes = struct.unpack_from(f"<{n // 32 * 4}Q", data)
        for k in range(0, len(lanes), 4):
            v = [rnd(v[0], lanes[k]), rnd(v[1], lanes[k + 1]), rnd(v[2], lanes[k + 2]), rnd(v[3], lanes[k + 3])]
        i = n // 32 * 32
        h = (rotl(v[0], 1) + rotl(v[1], 7) + rotl(v[2], 12) + rotl(v[3], 18)) & _M64
        for x in v:
            h = ((h ^ rnd(0, x)) * p1 + p4) & _M64
    else:
        h = (seed + p5) & _M64
    h = (h + n) & _M64
    while i + 8 <= n:
        h = (rotl(h ^ rnd(0, struct.unpack_from("<Q", data, i)[0]), 27) * p1 + p4) & _M64
        i += 8
    if i + 4 <= n:
        h = (rotl(h ^ (struct.unpack_from("<I", data, i)[0] * p1 & _M64), 23) * p2 + p3) & _M64
        i += 4
    while i < n:
        h = rotl(h ^ (data[i] * p5 & _M64), 11) * p1 & _M64
        i += 1
    h ^= h >> 33
    h = h * p2 & _M64
    h ^= h >> 29
    h = h * p3 & _M64
    return h ^ (h >> 32)


_TEXTURES = {}


def texture_index(game):
    """{Dolphin texture hash (16 hex digits): [(stock id, model file 0 / 1, texture index)]} of every playable
    character's models in the player's clean game (once per game)."""
    import charpack
    from mss_model import Model
    key = str(Path(game).resolve())
    if key not in _TEXTURES:
        out = {}
        with charpack.sources(game) as srcs:
            for cid in range(PLAYABLE):
                for fi in MODEL_FILES:
                    b = charpack.stock_file(game, srcs, cid, fi)
                    try:
                        texs = Model(b).textures if b else []
                    except Exception:
                        texs = []
                    for k, t in enumerate(texs):
                        h = f"{xxh64(b[t.image:t.image + t.payload_size()]):016x}"
                        out.setdefault(h, []).append((cid, fi, k))
        _TEXTURES[key] = out
    return _TEXTURES[key]


def is_texture_pack(path):
    """A folder (or a PNG in it) with Dolphin-dump-named pictures and no .sluggie: a texture pack."""
    path = Path(path)
    folder = path if path.is_dir() else path.parent
    if path.is_file() and path.suffix.lower() != ".png":
        return False
    return not any(folder.glob("*" + SUFFIX)) and any(DUMP_NAME.match(p.name) for p in folder.glob("*.png"))


def texture_pack(path, game):
    """{"template": stock id, "folder", "files": {model file: [(texture index, PNG)]}, "notes"}: the pack's pictures
    matched to a stock character's textures by their Dolphin hashes (the character most of them belong to; a picture
    several characters share counts less). SluggieError in plain words when none matches."""
    path = Path(path)
    folder = path if path.is_dir() else path.parent
    pngs = sorted(p for p in folder.glob("*.png") if DUMP_NAME.match(p.name))
    idx = texture_index(game)
    hits = {p: idx.get(p.name.split("_")[2].lower(), []) for p in pngs}
    score = {}
    for p, hs in hits.items():
        who = {c for c, _, _ in hs}
        for c in who:
            score[c] = score.get(c, 0) + 1 / len(who)
    if not score:
        raise SluggieError(f"none of the pictures in {folder.name} is one of a character's model textures in your "
                           f"game (Dolphin names each picture by the texture it replaces): it may be for another "
                           f"part of the game, or made from a changed copy of the game")
    best = max(score.values())
    tops = sorted(c for c, v in score.items() if v == best)
    tid, notes, files = tops[0], [], {}
    if len(tops) > 1:
        notes.append(f"these pictures fit {', '.join(_name(c) for c in tops)} alike: it's built on {_name(tid)}")
    for p, hs in hits.items():
        mine = [(fi, k) for c, fi, k in hs if c == tid]
        for fi, k in mine:
            files.setdefault(fi, []).append((k, p))
        if not mine:
            notes.append(f"{p.name} isn't one of {_name(tid)}'s model pictures: left out")
    return {"template": tid, "folder": folder, "files": files, "notes": notes}


def _texture_pack_blocks(path, game):
    """(template id, {file index: block}, changes, problems, notes) of a texture pack. A picture that can't be written
    (a palette, mipmaps, another size) is left out with a note; the rest are kept."""
    import charpack
    from mss_model import Model
    tp = texture_pack(path, game)
    tid, blocks, changes, problems, notes = tp["template"], {}, [], [], list(tp["notes"])
    with charpack.sources(game) as srcs:
        for fi, lst in sorted(tp["files"].items()):
            clean = charpack.stock_file(game, srcs, tid, fi)
            texs = Model(clean).textures
            out = bytearray(clean)
            for k, png in lst:
                payload, problem, note = _repaint(clean, texs[k], png)
                if note:
                    notes.append(note)
                if problem:
                    notes.append(f"{png.name} {problem.split(': leave')[0].split('. Export')[0]}: left out")
                elif payload is not None:
                    out[texs[k].image:texs[k].image + len(payload)] = payload
                    changes.append(f"{'low-detail model: ' if fi == 1 else ''}repainted texture {k} ({png.name})")
            if bytes(out) != clean:
                blocks[fi] = bytes(out)
    if not blocks:
        problems.append(f"the pictures in {tp['folder'].name} are {_name(tid)}'s as they are in the game: nothing "
                        f"to add")
    return tid, blocks, changes, problems, list(dict.fromkeys(notes))


# ---- a new character

def add_character(path, game, dest=None, taken_ids=(), taken_names=(), name=None, cid=None, icons=None, voice=None):
    """The .sluggie as a new character, stored where imported packs go (charpack.default_dest(): both windows list it
    and it's the player's own): template = the model's stock character, a free id, "<Template> (custom)" (then
    " (2)"...), model_blocks = the edited block as a delta against the clean game (charpack.materialize rebuilds it
    at patch time), after the model crash gate imports use (charpack.gate_lod). Returns {"definition", "id", "name",
    "template", "changes", "warnings"}; SluggieError."""
    import charpack
    game = Path(game)
    if is_texture_pack(path):                       # a texture pack: the matched character's model, repainted
        template, blocks, pack_changes, problems, _ = _texture_pack_blocks(path, game)
        if problems:
            raise SluggieError("; ".join(problems))
        s, group = None, []
        source_name = (Path(path) if Path(path).is_dir() else Path(path).parent).name
    else:
        group = _checked_all(path, game)
        s = group[0][0]
        problems = [(x.path.name + ": " if len(group) > 1 else "") + p for x, _, ps in group for p in ps]
        if problems:
            raise SluggieError("; ".join(problems))
        blocks = {}
        for x, ex, px in group:
            blocks.update(_apply(x, ex, px))
        template, source_name, pack_changes = s.template, s.path.name, []
    with charpack.sources(game) as srcs:           # the import's model crash gate (check_models)
        for i, block in blocks.items():
            try:
                charpack.gate_lod(block, game, srcs, template, i)
            except charpack.PackError as err:
                raise SluggieError(f"{source_name}: the edited {err}")
    changes = list(dict.fromkeys([c for _, ex, _ in group for c in ex.changes] + pack_changes))
    meta = {"file": source_name, "files": [x.path.name for x, _, _ in group] or [source_name],
            "sha1": hashlib.sha1(s.path.read_bytes()).hexdigest() if s else None, "folder": None, "changes": changes}
    r = store_character(game, blocks, template, dest, taken_ids, taken_names, meta={"_sluggie": meta}, name=name,
                        cid=cid, icons=icons, voice=voice)      # (portraits / clips found beside it: char_import)
    r["changes"] = changes
    r["warnings"] = [] if changes else [f"{source_name} has no edits yet: {r['name']} looks just like "
                                        f"{r['template']}"]
    return r


PORTRAIT = (48, 51)                 # charbuild.ICON_ART / charpack.ICON_SIZE: a side or front select portrait


def fit_portrait(img):
    """Any picture -> a 48x51 RGBA portrait: scaled to fit (aspect kept), centred on transparency."""
    from PIL import Image
    img = img.convert("RGBA")
    k = min(PORTRAIT[0] / img.width, PORTRAIT[1] / img.height)
    small = img.resize((max(1, round(img.width * k)), max(1, round(img.height * k))), Image.LANCZOS)
    out = Image.new("RGBA", PORTRAIT, (0, 0, 0, 0))
    out.paste(small, ((PORTRAIT[0] - small.width) // 2, (PORTRAIT[1] - small.height) // 2))
    return out


def template_portrait(game, template, view):
    """The stock character's own side / front portrait from the player's game (48x51), or None."""
    import recolor
    try:
        return fit_portrait(recolor.Game(str(game)).portrait(template, view))
    except Exception:
        return None


def store_character(game, blocks, template, dest=None, taken_ids=(), taken_names=(), name=None, meta=None,
                    icons=None, voice=None, cid=None):
    """A new character where imported packs go (charpack.default_dest(): both windows list it, it's the player's own):
    template (a stock id), a free id, name (default "<Template> (custom)"; taken: " (2)"...), "made_by": "player",
    "own_square", model_blocks = {file index: block} as deltas against the clean game (charpack.materialize rebuilds
    them), meta (extra definition keys, e.g. "_sluggie"), icons = {"side" / "front": PIL image} (any size: fitted to
    48x51; one alone: the template's for the other), voice = {slot: wav bytes} (all 12, charpack's checks: its own
    voice, "voice": "voice", as an imported pack's). Returns {"definition", "id", "name", "template"}."""
    import charpack, delta
    game = Path(game)
    dest = Path(dest) if dest else charpack.default_dest()
    have = charpack.list_imported(dest)
    tname = _name(template)
    taken = set(taken_ids) | {c["id"] for c in have} | charpack.reserved_ids()
    try:
        cid = charpack.free_id(cid, taken)          # cid: kept when free (a Replace keeps the old id, git-a3)
        name = charpack.free_name(name or f"{tname} (custom)", [*taken_names, *(c["name"] for c in have)])
    except charpack.PackError as err:
        raise SluggieError(str(err))
    stem = f"0x{cid:02x}_{charpack.slug(name)}"
    folder, defn = dest / stem, dest / "characters" / f"{stem}.json"
    tmp = dest / f".{stem}.part"
    shutil.rmtree(tmp, ignore_errors=True)
    (tmp / "models").mkdir(parents=True)
    idx = charpack.index(game)
    model_blocks = {}
    for i, block in sorted(blocks.items()):
        (tmp / "models" / f"{i}.slgd").write_bytes(delta.make(block, idx)[0])
        model_blocks[str(i)] = f"models/{i}.slgd"
    d = {"id": f"0x{cid:02x}", "name": name, "template": tname, "made_by": "player", "own_square": True, "stats": {},
         "model_blocks": model_blocks, **(meta or {})}
    if icons:
        (tmp / "icons").mkdir()
        for view in ("side", "front"):
            img = icons.get(view)
            img = fit_portrait(img) if img is not None else template_portrait(game, template, view)
            if img is None:
                break
            img.save(tmp / "icons" / f"{view}.png")
        else:
            d["icon"] = {"side": "icons/side.png", "front": "icons/front.png"}
    if voice:                               # all 12, or some: the others play the base's (charpack.materialize)
        try:
            charpack.check_voice(sorted(voice), "the voice", partial=True)
            for slot in voice:
                charpack.check_clip(voice[slot], f"voice clip {slot}")
        except charpack.PackError as err:
            shutil.rmtree(tmp, ignore_errors=True)
            raise SluggieError(str(err))
        (tmp / "voice").mkdir()
        for slot in voice:
            (tmp / "voice" / f"{slot}.wav").write_bytes(voice[slot])
        d["voice"] = "voice"
    for v in d.values():
        if isinstance(v, dict) and "folder" in v:
            v["folder"] = stem
    shutil.rmtree(folder, ignore_errors=True)
    os.replace(tmp, folder)
    defn.parent.mkdir(parents=True, exist_ok=True)
    defn.write_text(json.dumps(d, indent=1, ensure_ascii=False), encoding="utf8")
    return {"definition": defn, "id": cid, "name": name, "template": tname, "folder": folder}


def set_portrait(definition, view, img, game):
    """An added character's side / front portrait from any picture (fitted to 48x51), saved in its folder
    (icons/<view>.png) and named in its definition; the other view, if it has none yet, the template's."""
    definition = Path(definition)
    d = json.loads(definition.read_text(encoding="utf8"))
    folder = definition.parent.parent / definition.stem
    (folder / "icons").mkdir(parents=True, exist_ok=True)
    fit_portrait(img).save(folder / "icons" / f"{view}.png")
    other = "front" if view == "side" else "side"
    if not (folder / "icons" / f"{other}.png").exists():
        from sluggers_data import char_id
        t = template_portrait(game, char_id(d["template"]), other)
        if t is None:
            raise SluggieError(f"the {other} portrait of {d['template']} can't be read from your game: add a {other} "
                               f"picture too")
        t.save(folder / "icons" / f"{other}.png")
    d["icon"] = {"side": "icons/side.png", "front": "icons/front.png"}
    definition.write_text(json.dumps(d, indent=1, ensure_ascii=False), encoding="utf8")
    return d["icon"]


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    ap.add_argument("what", choices=["check", "add"])
    ap.add_argument("sluggie")
    ap.add_argument("--game", default=None, help="the extracted clean game (default: game_source.root())")
    ap.add_argument("--dest", default=None)
    a = ap.parse_args(argv)
    import game_source
    game = Path(a.game or game_source.root())
    if a.what == "check":
        r = describe(a.sluggie, game)
        for p in r["problems"]:
            print("problem:", p)
        for c in r["changes"]:
            print("edit:", c)
        print("ok" if not r["problems"] else "can't be added")
        return 0 if not r["problems"] else 1
    try:
        r = add_character(a.sluggie, game, a.dest)
    except SluggieError as e:
        print(e)
        return 1
    print(f"added {r['name']} (0x{r['id']:02X}) on {r['template']}'s model: {r['definition']}")
    for w in r["warnings"]:
        print("note:", w)
    return 0


if __name__ == "__main__":
    sys.exit(main())
