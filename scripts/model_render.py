"""A small software renderer for model blocks (numpy only: no Blender, no GPU), for art made on the player's PC at
patch time from their own game (captain_art.model_art: a captain without captain art gets its portrait, lineup figure
and emblem rendered from its 3D model).

  python scripts/model_render.py <model block .bin | dir:file of the clean game, e.g. 0x21:0> <out.png> [view]

mesh(block) -> Mesh: the model in its bind pose, in model space (Y up, the character faces +Z): the skinned
submesh's positions as stored, rigid submeshes placed by their owner bone's world matrix (gltf_model.bones), one
texture (layer 0) per draw group, UVs (tex0) and normals per corner.
render(mesh, size, ...) -> RGBA PIL image: orthographic, a yaw / pitch turn, textured (bilinear, repeat, alpha-tested
at 0.5), a depth buffer, Lambert key + fill light and ambient, a rim, a highlight, darker grazing faces, levels
stretched to the stock art's (_tone), supersampled and filtered down. The rasterizer is
vectorized over triangles: every triangle's bounding box is sampled on a grid of its size class, the fragments that
fall inside are kept, and the nearest per pixel wins (a sort), so a 5 000-triangle model renders in well under a
second.
"""
import os
import sys

import numpy as np
from PIL import Image

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from mss_model import Model  # noqa: E402


class Mesh:
    """Triangles of a model: P (T, 3, 3) positions, N (T, 3, 3) normals, UV (T, 3, 2), tex (T,) texture index or -1,
    textures {index: float RGBA array (h, w, 4) 0..1}."""

    def __init__(self, P, N, UV, tex, textures):
        self.P, self.N, self.UV, self.tex, self.textures = P, N, UV, tex, textures
        self.shoulder = None

    def bounds(self):
        v = self.P.reshape(-1, 3)
        return v.min(0), v.max(0)


ARMS_DOWN = 62            # degrees a T-pose's arms are lowered by (arm_pose), about the front axis at the shoulder
ARMS_FORWARD = 12         # and swung forward, so the hands clear a wide body


def _rot(axis, deg, pivot):
    """4 x 4: a rotation by deg about axis (unit) through pivot."""
    a = np.radians(deg)
    x, y, z = axis
    c, s, C = np.cos(a), np.sin(a), 1 - np.cos(a)
    R = np.array([[c + x * x * C, x * y * C - z * s, x * z * C + y * s],
                  [y * x * C + z * s, c + y * y * C, y * z * C - x * s],
                  [z * x * C - y * s, z * y * C + x * s, c + z * z * C]])
    M = np.identity(4)
    M[:3, :3] = R
    M[:3, 3] = pivot - R @ pivot
    return M


def arm_pose(block, m, sk, down=ARMS_DOWN, forward=ARMS_FORWARD, pivots=None):
    """{bone id: 4 x 4 world-space transform} that lowers a T-pose's arms: per side, the chain from the bone that
    holds the model's outermost vertex up to the root; its first bone off the centre line is the clavicle (or the
    shoulder, when it's already far out), the next one the shoulder, which turns with everything under it. Only when
    the arm is level (a T-pose; an A-pose or no arms: nothing moves). Stock models and ours share the skeleton layout
    (spine, clavicle 20 / 56, shoulder 21 / 57); an import's is found the same way. pivots: a list the shoulders'
    positions (bind pose) are appended to, for an arm level or not."""
    if not m.skin or not m.submeshes or not m.submeshes[0].skinned or not down:
        return {}
    b = block
    by = {x["id"]: x for x in sk}
    kids = {}
    for x in sk:
        kids.setdefault(x["parent"], []).append(x["id"])
    pos = np.array(m.submeshes[0].position.values(b), dtype=np.float64)[:, :3]
    inf = m.skin.influences(b)
    at = lambda i: by[i]["world"][:3, 3]  # noqa: E731
    height = pos[:, 1].max() - pos[:, 1].min()
    out = {}
    for sign in (1, -1):
        v = int(np.argmax(pos[:, 0] * sign))
        if not inf.get(v):
            continue
        bone = max(inf[v].items(), key=lambda kv: kv[1])[0]
        chain = []
        while bone is not None and bone in by and bone not in chain:
            chain.append(bone)
            bone = by[bone]["parent"]
        chain.reverse()                                     # root -> hand
        reach = pos[v, 0] * sign
        k = next((i for i, c in enumerate(chain) if at(c)[0] * sign > 0.02 * height), None)
        if k is None or reach < 0.15 * height:
            continue
        if at(chain[k])[0] * sign < 0.2 * reach and k + 1 < len(chain):
            k += 1                                          # (a clavicle: the shoulder is the next one)
        pivot = at(chain[k])
        if pivots is not None:
            pivots.append(pivot)
        dx, dy = reach - pivot[0] * sign, pos[v, 1] - pivot[1]
        if dx <= 0 or abs(dy) > 0.35 * dx:                  # not a level arm: left as it is
            continue
        M = _rot(np.array([0, 1.0, 0]), -sign * forward, pivot) @ _rot(np.array([0, 0, 1.0]), -sign * down, pivot)
        # the shoulder and its siblings at the shoulder or further out (the stock arms' twist chains: DK's 22 / 26
        # and Mario's 23 / 27 hang off the clavicle beside the shoulder), each with everything under it
        parent = by[chain[k]]["parent"]
        todo = [c for c in kids.get(parent, [chain[k]]) if at(c)[0] * sign >= pivot[0] * sign - 0.01 * height]
        while todo:
            i = todo.pop()
            if i not in out:
                out[i] = M
                todo += kids.get(i, [])
    return out


def mesh(block, textures=None, pose=True):
    """block: a model block (bytes). textures: {index: PIL image} over the block's own (default: decoded from it).
    pose: lower a T-pose's arms (arm_pose)."""
    import gltf_model
    b = bytes(block)
    m = Model(b)
    sk = gltf_model.bones(b)
    pivots = []
    moved = arm_pose(b, m, sk, down=ARMS_DOWN if pose else 0, pivots=pivots)
    world = {x["id"]: moved.get(x["id"], np.identity(4)) @ x["world"] for x in sk}
    owner = {x["geo"]: x["id"] for x in sk if x["geo"] is not None}
    imgs = gltf_model.texture_images(b, m) if textures is None else textures
    P, N, UV, T = [], [], [], []
    for s in m.submeshes:
        pos = np.array(s.position.values(b), dtype=np.float64)
        if not len(pos):
            continue
        xyz = pos[:, :3]
        nrm = np.array(s.normal.values(b), dtype=np.float64)[:, :3] if s.normal else (
            pos[:, 3:6] if pos.shape[1] >= 6 else None)
        uv0 = np.array(s.uvs[0].values(b), dtype=np.float64) if s.uvs else None
        blend = None                                        # skinned and posed: a 3 x 3 per position (normals)
        if not s.skinned and s.idx in owner:                # rigid: stored in its owner bone's space
            M = world[owner[s.idx]]
            xyz = xyz @ M[:3, :3].T + M[:3, 3]
            if nrm is not None:
                nrm = nrm @ np.linalg.inv(M[:3, :3])        # (normals by the inverse transpose)
        elif s.skinned and moved:                           # linear blend skinning of the moved bones
            Mv = np.tile(np.identity(4), (len(xyz), 1, 1))
            for v, ws in m.skin.influences(b).items():
                if v < len(xyz):
                    total = sum(ws.values()) or 1.0
                    for bone, w in ws.items():
                        if bone in moved:
                            Mv[v] += (w / total) * (moved[bone] - np.identity(4))
            xyz = np.einsum("vij,vj->vi", Mv[:, :3, :3], xyz) + Mv[:, :3, 3]
            blend = Mv[:, :3, :3]
        for _, _, binds, _, tris in s.groups(b):
            if not tris:
                continue
            pi = np.array([[v.get("position", 0) for v in t] for t in tris])
            P.append(xyz[pi])
            if nrm is not None and all("normal" in v for v in tris[0]):
                ni = np.array([[v["normal"] for v in t] for t in tris])
                n = nrm[np.minimum(ni, len(nrm) - 1)]
            elif nrm is not None and len(nrm) == len(xyz):
                n = nrm[pi]
            else:
                n = np.zeros((len(tris), 3, 3))
            if blend is not None:
                n = np.einsum("tcij,tcj->tci", blend[np.minimum(pi, len(blend) - 1)], n)
            N.append(n)
            if uv0 is not None and all("tex0" in v for v in tris[0]):
                ti = np.array([[v["tex0"] for v in t] for t in tris])
                UV.append(uv0[np.minimum(ti, len(uv0) - 1)][:, :, :2])
            else:
                UV.append(np.zeros((len(tris), 3, 2)))
            k = binds.get(0)
            T.append(np.full(len(tris), k if k is not None and k in imgs else -1))
    P, N, UV, T = (np.concatenate(a) for a in (P, N, UV, T))
    # a normal missing (or zero): the face's own, facing the game's front (the winding is clockwise-front)
    face = np.cross(P[:, 2] - P[:, 0], P[:, 1] - P[:, 0])
    face /= np.maximum(np.linalg.norm(face, axis=1, keepdims=True), 1e-12)
    ln = np.linalg.norm(N, axis=2, keepdims=True)
    N = np.where(ln > 1e-6, N / np.maximum(ln, 1e-12), face[:, None, :])
    used = sorted({int(k) for k in T if k >= 0})
    tex = {k: np.asarray(imgs[k].convert("RGBA"), dtype=np.float32) / 255.0 for k in used}
    out = Mesh(P, N, UV, T, tex)
    out.shoulder = np.mean(pivots, 0) if pivots else None      # (model space; None: no arms found)
    return out


def rotation(yaw, pitch):
    """World -> view rotation: turn the model by yaw (degrees, about Y: positive shows its left side... its right
    cheek to the camera) and tilt the camera down by pitch (degrees)."""
    a, p = np.radians(yaw), np.radians(pitch)
    ry = np.array([[np.cos(a), 0, np.sin(a)], [0, 1, 0], [-np.sin(a), 0, np.cos(a)]])
    rx = np.array([[1, 0, 0], [0, np.cos(p), -np.sin(p)], [0, np.sin(p), np.cos(p)]])
    return rx @ ry


def project(mesh, yaw=0.0, pitch=0.0):
    """View-space triangles (T, 3, 3): x right, y up, z toward the camera (larger z is nearer)."""
    return mesh.P @ rotation(yaw, pitch).T


def _sample(tex, uv):
    """Bilinear, repeat-wrapped. tex (h, w, 4), uv (n, 2) with the game's top-left origin -> (n, 4)."""
    h, w = tex.shape[:2]
    x = uv[:, 0] * w - 0.5
    y = uv[:, 1] * h - 0.5
    x0, y0 = np.floor(x), np.floor(y)
    fx, fy = (x - x0)[:, None], (y - y0)[:, None]
    x0, y0 = x0.astype(np.int64), y0.astype(np.int64)
    x1, y1 = (x0 + 1) % w, (y0 + 1) % h
    x0, y0 = x0 % w, y0 % h
    return ((tex[y0, x0] * (1 - fx) + tex[y0, x1] * fx) * (1 - fy)
            + (tex[y1, x0] * (1 - fx) + tex[y1, x1] * fx) * fy)


LIGHT_KEY = np.array([-0.45, 0.55, 0.70])          # view space: from the upper left, in front
LIGHT_FILL = np.array([0.6, 0.1, 0.5])
LIGHT_RIM = np.array([0.55, 0.45, -0.70])          # from behind, upper right: a bright edge on the far side
# The game shows a portrait at about half strength (it sits under captain select's translucent panel: the stock
# Mario's pixels come out 0.53 x his art + 0.47 x the panel, test on captain-art-1's frames), so a flat render turns
# into a pale ghost there while the stock art (studio renders: deep shading, highlights) still reads. Hence shading
# with depth (less ambient, a strong key, a rim, a highlight, darker grazing faces) and tone() on the result.
AMBIENT, KEY, FILL, RIM = 0.30, 0.85, 0.22, 0.45
SPECULAR, SHINE = 0.22, 24.0
EDGE_DARK = 0.45                                   # grazing faces (the silhouette's edge) darken by up to this much


def render(mesh, size, yaw=0.0, pitch=0.0, window=None, ss=3, tone=True):
    """-> RGBA PIL image of `size` (w, h). window: (x0, y0, x1, y1) of view space to show (x right, y up; the
    image's aspect: it is stretched otherwise), default: the whole model with a margin. ss: supersampling. tone:
    stretch the levels to the stock art's (_tone)."""
    W, H = size[0] * ss, size[1] * ss
    V = project(mesh, yaw, pitch)
    R = rotation(yaw, pitch)
    if window is None:
        lo, hi = V.reshape(-1, 3).min(0), V.reshape(-1, 3).max(0)
        window = (lo[0], lo[1], hi[0], hi[1])
    x0, y0, x1, y1 = window
    # to pixels (pixel centres at +0.5), y down
    X = (V[:, :, 0] - x0) / (x1 - x0) * W
    Y = (y1 - V[:, :, 1]) / (y1 - y0) * H
    Z = V[:, :, 2]
    # keep triangles that touch the image and have area
    area = (X[:, 1] - X[:, 0]) * (Y[:, 2] - Y[:, 0]) - (X[:, 2] - X[:, 0]) * (Y[:, 1] - Y[:, 0])
    bx0, bx1 = np.floor(X.min(1)), np.ceil(X.max(1))
    by0, by1 = np.floor(Y.min(1)), np.ceil(Y.max(1))
    keep = (np.abs(area) > 1e-9) & (bx1 >= 0) & (bx0 < W) & (by1 >= 0) & (by0 < H)
    bx0, by0 = np.maximum(bx0, 0), np.maximum(by0, 0)          # (clipped: a box never starts off the image)
    bx1, by1 = np.minimum(bx1, W), np.minimum(by1, H)
    idx = np.nonzero(keep)[0]
    # size classes: a grid of sx x sy samples (powers of two) covers every triangle whose box fits it
    cx = np.ceil(np.log2(np.maximum(bx1 - bx0, 1)[idx])).astype(int)
    cy = np.ceil(np.log2(np.maximum(by1 - by0, 1)[idx])).astype(int)
    alpha = {k for k, t in mesh.textures.items() if t[:, :, 3].min() < 0.5}
    tested = np.isin(mesh.tex, list(alpha)) if alpha else np.zeros(len(mesh.tex), bool)
    frags = []
    for kx, ky in sorted(set(zip(cx.tolist(), cy.tolist()))):
        t = idx[(cx == kx) & (cy == ky)]
        sx, sy = 1 << kx, 1 << ky
        for chunk in np.array_split(t, len(t) * sx * sy // 1_000_000 + 1):
            f = _raster(chunk, sx, sy, X, Y, Z, area, bx0, by0, W, H)
            if f is not None:
                frags.append(f)
    out = np.zeros((H * W, 4), dtype=np.float32)
    if frags:
        pix, z, tri, b = (np.concatenate(v) for v in zip(*frags))
        at = tested[tri]                                # alpha test (hair ends, lashes) before the depth test
        if at.any():
            ok = np.ones(len(tri), bool)
            ok[at] = _shade_rgba(mesh, tri[at], b[at])[:, 3] >= 0.5
            pix, z, tri, b = pix[ok], z[ok], tri[ok], b[ok]
        order = np.lexsort((-z, pix))                   # per pixel, nearest first
        pix, first = np.unique(pix[order], return_index=True)
        win = order[first]
        tri, b = tri[win], b[win]
        rgba = _shade_rgba(mesh, tri, b)
        Nv = mesh.N[tri] @ R.T
        n = (Nv * b[:, :, None]).sum(1)
        n /= np.maximum(np.linalg.norm(n, axis=1, keepdims=True), 1e-9)
        n = np.where(n[:, 2:3] < 0, -n, n)              # a back face seen: lit as its front
        k = LIGHT_KEY / np.linalg.norm(LIGHT_KEY)
        f = LIGHT_FILL / np.linalg.norm(LIGHT_FILL)
        r = LIGHT_RIM / np.linalg.norm(LIGHT_RIM)
        facing = np.clip(n[:, 2], 0, 1)                 # 1: faces the camera, 0: grazing
        light = (AMBIENT + KEY * np.clip(n @ k, 0, 1) + FILL * np.clip(n @ f, 0, 1))             * (1 - EDGE_DARK * (1 - facing) ** 2)
        rim = RIM * np.clip(n @ r, 0, 1) * (1 - facing) ** 1.5
        hv = k + np.array([0, 0, 1.0])
        spec = SPECULAR * np.clip(n @ (hv / np.linalg.norm(hv)), 0, 1) ** SHINE
        out[pix, :3] = np.clip(rgba[:, :3] * (light + rim)[:, None] + spec[:, None], 0, 1)
        out[pix, 3] = 1.0
    img = out.reshape(H, W, 4)
    if tone:
        img = _tone(img)
    return _downsample(img, ss)


TONE_LOW, TONE_HIGH = 0.03, 0.98     # where the body's 2nd / 98th luminance percentiles go (the stock portraits':
#                                      p5 0.01-0.37, p95 0.56-1.00; the flat renders' were 0.14-0.36 / 0.43-0.81)
TONE_GAIN = (0.8, 2.2)               # (a dark character stays darker than a light one: the stretch is limited)
SATURATION = 1.3
TONE_GAMMA = 1.3                     # mid-tones deepened (the stock art's shading reaches black; highlights kept)


def _tone(img):
    """(H, W, 4) straight alpha: the opaque body's levels stretched to the stock art's range (a model's textures
    are made for the game's lights, often dark and flat: a yellow Luma came out olive) and its colour a little more
    saturated, hue kept."""
    a = img[:, :, 3] > 0.5
    if a.sum() < 16:
        return img
    rgb = img[:, :, :3]
    lum = rgb @ np.array([0.299, 0.587, 0.114], dtype=np.float32)
    lo, hi = np.percentile(lum[a], [2, 98])
    gain = float(np.clip((TONE_HIGH - TONE_LOW) / max(hi - lo, 1e-3), *TONE_GAIN))
    off = TONE_LOW - lo * gain
    out = np.clip(rgb * gain + off, 0, 1)
    lum2 = out @ np.array([0.299, 0.587, 0.114], dtype=np.float32)
    out = out * (np.power(np.clip(lum2, 1e-4, 1), TONE_GAMMA) / np.maximum(lum2, 1e-4))[:, :, None]
    grey = (out @ np.array([0.299, 0.587, 0.114], dtype=np.float32))[:, :, None]
    out = grey + (out - grey) * SATURATION
    res = img.copy()
    res[:, :, :3] = np.where(a[:, :, None], np.clip(out, 0, 1), rgb)
    return res


def _shade_rgba(mesh, tri, b):
    """Texture colour (RGBA 0..1) of fragments: triangle indices and barycentrics (f, 3)."""
    uv = (mesh.UV[tri] * b[:, :, None]).sum(1)
    rgba = np.full((len(tri), 4), (0.8, 0.8, 0.8, 1.0), dtype=np.float32)
    k = mesh.tex[tri]
    for key, tex in mesh.textures.items():
        m = k == key
        if m.any():
            rgba[m] = _sample(tex, uv[m])
    return rgba


def _raster(t, sx, sy, X, Y, Z, area, bx0, by0, W, H):
    """Fragments of triangles t (their boxes fit sx x sy): (pixel index, depth, triangle, barycentrics)."""
    gx, gy = np.meshgrid(np.arange(sx, dtype=np.float32), np.arange(sy, dtype=np.float32))
    px = bx0[t, None].astype(np.float32) + gx.reshape(1, -1) + 0.5          # (n, sx*sy) sample centres
    py = by0[t, None].astype(np.float32) + gy.reshape(1, -1) + 0.5
    xa, xb, xc = (X[t, i, None].astype(np.float32) for i in range(3))
    ya, yb, yc = (Y[t, i, None].astype(np.float32) for i in range(3))
    inv = (1.0 / area[t, None]).astype(np.float32)
    w0 = ((xb - px) * (yc - py) - (xc - px) * (yb - py)) * inv
    w1 = ((xc - px) * (ya - py) - (xa - px) * (yc - py)) * inv
    inside = (w0 >= -1e-5) & (w1 >= -1e-5) & (w0 + w1 <= 1 + 1e-5) & (px < W) & (py < H)
    ti, si = np.nonzero(inside)
    if not len(ti):
        return None
    b0, b1 = w0[ti, si], w1[ti, si]
    b = np.stack([b0, b1, 1.0 - b0 - b1], 1)
    tri = t[ti]
    z = (Z[tri] * b).sum(1)
    pix = py[ti, si].astype(np.int64) * W + px[ti, si].astype(np.int64)
    return pix, z, tri, b


def _downsample(img, ss):
    """(H, W, 4) straight alpha -> PIL RGBA, box-filtered by ss with premultiplied colour."""
    H, W = img.shape[:2]
    pre = img[:, :, :3] * img[:, :, 3:4]
    a = img[:, :, 3].reshape(H // ss, ss, W // ss, ss).mean((1, 3))
    c = pre.reshape(H // ss, ss, W // ss, ss, 3).mean((1, 3))
    c = np.where(a[:, :, None] > 0, c / np.maximum(a[:, :, None], 1e-9), 0)
    out = np.concatenate([c, a[:, :, None]], 2)
    return Image.fromarray(np.clip(out * 255 + 0.5, 0, 255).astype(np.uint8), "RGBA")


if __name__ == "__main__":
    src, dst = sys.argv[1], sys.argv[2]
    yaw = float(sys.argv[3]) if len(sys.argv) > 3 else 0.0
    if os.path.exists(src):
        blk = open(src, "rb").read()
    else:
        import recolor
        import game_source
        d, f = (int(v, 0) for v in src.split(":"))
        blk = recolor.Game(str(game_source.root())).file(d, f)
    import time
    t0 = time.time()
    me = mesh(blk)
    t1 = time.time()
    render(me, (300, 400), yaw=yaw, pitch=8).save(dst)
    print(f"{len(me.P)} triangles, mesh {t1 - t0:.2f}s, render {time.time() - t1:.2f}s -> {dst}")
