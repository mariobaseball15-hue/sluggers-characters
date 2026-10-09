"""A player's own 3D model for a thrown ball (creators/items.py: look.model "own", look.obj; Nick's imports).

The .obj (with its .mtl and textures, in the creation's files) is packed into a rigid prop block by build_prop.pack,
on the Shell item model's block (as Lemmy's circus ball): one bone, the textures in one CMPR atlas (128 px, or 64 px
when 128 doesn't fit), sized so its largest side is look.scale metres, its centre at the origin. The block goes in
item package slot 0x2A's unused tail after the Bill's block (starbits_model extra; dir 136's package is a
fixed-size resident file, so a model that fits costs no memory), is loaded and freed as model-set slot
FIRST_SLOT + k with one instance per ball (wendy_rings' LOAD / FREE) and drawn at each of the item's flying balls
(draw_code: lemmy_balls' drawing, for its ids), look.height above the ball (default half its size).

ROOM: what's free in the tail: about 18 KB, all own models together. build_prop's block is about 12.5 KB with a
128 px texture and a few dozen triangles (6 KB less at 64 px), plus about 1 KB per 45 triangles (MAX_TRIS / LIMITS:
measured). plan() tries 128 px, then 64 px, and refuses more in plain words with the numbers.
"""
import math
import os
import shutil
import sys
import tempfile
from pathlib import Path

from ppc import ha, lo

FIRST_SLOT, MAX_MODELS = 0x83, 2                     # model-set keys after the ring 0x80, Lemmy 0x81, the Bill 0x82
TAIL_START, TAIL_END = 0x21200, 0x25B40              # after the Bill's block (0x15800 + 0xB9E0), the slot's end
ROOM = TAIL_END - TAIL_START
ATLASES = (128, 64)
MAX_TRIS = 450                                       # refused before packing: more never fits ROOM
# measured (a sphere; BlockValidator: valid): 256 tris 17.0 KB at 128 px / 10.8 KB at 64 px; 400 tris 20.3 / 14.1 KB;
# 576 tris 31.1 / 25.0 KB (past 255 positions the indices take 2 bytes)
LIMITS = ("up to about 300 triangles with a 128 x 128 texture, or about 400 with 64 x 64, "
          f"{ROOM // 1024} KB for all your own models together")
TEMPLATE = {"offset": 652749312, "length": 154432}   # the Shell item model (dir 137 file 41 = package slot 0x29)
GET_MODEL, MODEL_SHOW, MODEL_POS, MODEL_ROT, MODEL_SCALE = 0x8037FD48, 0x80381E3C, 0x80381CAC, 0x80381CC4, 0x80381CE4
MANAGER, ACTIVE, FIREBALL = -0x354, 0x394, 1


class TooBig(ValueError):
    pass


def triangles(obj):
    """Triangles in an .obj (faces fanned)."""
    n = 0
    with open(obj, encoding="utf8", errors="replace") as f:
        for line in f:
            if line.startswith("f "):
                n += max(0, len(line.split()) - 3)
    return n


def _textures_fit(src_obj, work, atlas):
    """A copy of the .obj, its .mtl and textures in `work`, each texture scaled down to fit the atlas together."""
    from PIL import Image
    src = Path(src_obj)
    shutil.copy(src, work / src.name)
    maps = []
    for line in open(src, encoding="utf8", errors="replace"):
        if line.startswith("mtllib "):
            mtl = src.parent / line.split(None, 1)[1].strip()
            shutil.copy(mtl, work / mtl.name)
            for ml in open(mtl, encoding="utf8", errors="replace"):
                if ml.split()[:1] == ["map_Kd"]:
                    maps.append(ml.split(None, 1)[1].strip())
    per = max(1, math.ceil(math.sqrt(len(maps) or 1)))
    side = max(8, (atlas - 4 * per) // per)
    for m in maps:
        im = Image.open(src.parent / m)
        im.thumbnail((side, side))
        (work / m).parent.mkdir(parents=True, exist_ok=True)
        im.save(work / m)
    return work / src.name


def validator():
    """Whether Sluggies' BlockValidator is where build_model.validate imports it from (refs/, dev machines; it doesn't
    ship with the patcher: no license). build_prop's own layout is what the patcher packs either way."""
    root = Path(__file__).resolve().parents[1]
    return (root / "refs/Sluggies-dat-tools/SluggiesTools/Hammerspace/BlockValidator.py").is_file()


def pack(obj, size, game, atlas=128):
    """.obj -> (prop block, report): largest side `size` metres, centred, textures in an atlas of `atlas` px."""
    sys.path.insert(0, str(Path(__file__).parent))
    import build_prop
    import numpy as np
    with tempfile.TemporaryDirectory() as t:
        work = Path(t)
        src = _textures_fit(obj, work, atlas)
        pos = build_prop.read_obj(str(src))[0]
        lo_, hi_ = pos.min(0), pos.max(0)
        extent = float((hi_ - lo_).max()) or 1.0
        cfg = {"name": Path(obj).stem[:24], "source": str(src),
               "template": dict(TEMPLATE, dat=str(Path(game) / "files/dt_na.dat")),
               "grip": ((lo_ + hi_) / 2).tolist(), "scale": size / extent, "rotate": [], "atlas": atlas,
               "smooth_angle": 35, "pos_quant": 61, "out_dir": str(work / "out"), "validate": validator()}
        return build_prop.pack(cfg)


def plan(specs, game):
    """[(spec, model-set slot, offset in the slot, block)] for the items with an own model, packed and placed; raises
    TooBig in plain words."""
    own = [s for s in specs if s.get("model") == "own"]
    if len(own) > MAX_MODELS:
        raise TooBig(f"at most {MAX_MODELS} items with their own model in one game ({len(own)} given)")
    out, at = [], TAIL_START
    for k, s in enumerate(own):
        n = triangles(s["obj"])
        if n > MAX_TRIS:
            raise TooBig(f"{s['name']}: its model has {n} triangles; {LIMITS}")
        left = TAIL_END - at
        for atlas in ATLASES:
            block, report = pack(s["obj"], s["model_size"], game, atlas)
            if len(block) <= left:
                break
        else:
            raise TooBig(f"{s['name']}: its model takes {len(block) // 1024} KB even with a 64 x 64 texture and "
                         f"{left // 1024} KB are left ({n} triangles); {LIMITS}")
        out.append((s, FIRST_SLOT + k, at, block))
        at += len(block) + (-len(block) % 32)
    return out


def draw_code(a, flag, arr, consts, ids, slot, n, tag):
    """lemmy_balls.draw_code for model-set slot `slot` (n instances, one per ball), drawn for the variants `ids`,
    labels prefixed `tag`. Emitted inside wendy_rings' DRAW stub (r30 = model set, r31 = hide all; r26-r28 free).
    consts: 3 floats: height above the ball, 0.0, 1.0 (data)."""
    L = lambda s: f"{tag}_{s}"  # noqa: E731
    a.mr(3, 30).li(4, slot).bl(GET_MODEL).mr(27, 3)
    a.cmpwi(27, -1).beq(L("done"))
    a.li(26, 0)
    a.label(L("loop"))
    a.mr(3, 30).mr(4, 27).li(5, 0).mr(6, 26).bl(MODEL_SHOW)                  # hide
    a.cmpwi(31, 0).bne(L("next"))
    a.lis(12, ha(flag)).lbz(12, lo(flag), 12)
    for vid in ids:
        a.cmpwi(12, vid).beq(L("mine"))
    a.b(L("next"))
    a.label(L("mine"))
    a.lwz(28, MANAGER, 13).cmpwi(28, 0).beq(L("next"))
    a.lwz(0, ACTIVE, 28).cmpwi(0, FIREBALL).bne(L("next"))
    a.load_addr(28, arr).slwi(0, 26, 6).add(28, 28, 0)
    a.lbz(0, 0x3C, 28).cmpwi(0, 2).bne(L("next"))                             # flying
    a.bl(L("place"))
    a.label(L("next"))
    a.addi(26, 26, 1).cmpwi(26, n).blt(L("loop"))
    a.b(L("done"))
    a.label(L("place"))                                                      # own frame
    a.stwu(1, -0x40, 1).mflr(0).stw(0, 0x44, 1)
    a.mr(3, 30).mr(4, 27).li(5, 1).mr(6, 26).bl(MODEL_SHOW)
    a.load_addr(11, consts)
    a.lfs(0, 4, 28).stfs(0, 0x2C, 1)
    a.lfs(0, 8, 28).lfs(1, 0, 11).fadds(0, 0, 1).stfs(0, 0x30, 1)
    a.lfs(0, 0xC, 28).fneg(0, 0).stfs(0, 0x34, 1)
    a.lfs(0, 4, 11).stfs(0, 0x20, 1).stfs(0, 0x24, 1).stfs(0, 0x28, 1)
    a.lfs(0, 8, 11).stfs(0, 0x14, 1).stfs(0, 0x18, 1).stfs(0, 0x1C, 1)
    for fn, sp in ((MODEL_POS, 0x2C), (MODEL_ROT, 0x20), (MODEL_SCALE, 0x14)):
        a.mr(3, 30).mr(4, 27).addi(5, 1, sp).mr(6, 26).bl(fn)
    a.lwz(0, 0x44, 1).mtlr(0).addi(1, 1, 0x40).blr()
    a.label(L("done"))
