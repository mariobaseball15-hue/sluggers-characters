"""The few scipy.ndimage operations the patcher needs at patch time, in numpy, so the download can leave scipy out
(git-92: scipy is ~70 MB of every download). Each matches scipy.ndimage's default behaviour (a 3 x 3 cross, zero
outside the image) exactly on the images we use them on; test_np_image.py compares them with scipy where scipy is
installed.

  label(mask) -> (labels, n)              connected components, 4-connected, numbered in raster order
  binary_dilation / binary_erosion(mask, iterations=1)
  binary_closing / binary_opening(mask, iterations=1)
  binary_fill_holes(mask)                 background not 4-connected to the border becomes foreground
  distance_transform_edt(mask)            exact Euclidean distance from each nonzero pixel to the nearest zero
"""
import numpy as np


def _shift_or(m):
    """m OR its 4 neighbours (the cross), zero outside."""
    out = m.copy()
    out[1:] |= m[:-1]
    out[:-1] |= m[1:]
    out[:, 1:] |= m[:, :-1]
    out[:, :-1] |= m[:, 1:]
    return out


def binary_dilation(mask, iterations=1):
    m = np.asarray(mask, bool)
    for _ in range(iterations):
        m = _shift_or(m)
    return m


def binary_erosion(mask, iterations=1):
    m = np.asarray(mask, bool)
    for _ in range(iterations):
        p = np.pad(m, 1, constant_values=False)           # scipy's border_value=0: next to the outside erodes
        m = p[1:-1, 1:-1] & p[:-2, 1:-1] & p[2:, 1:-1] & p[1:-1, :-2] & p[1:-1, 2:]
    return m


def binary_closing(mask, iterations=1):
    return binary_erosion(binary_dilation(mask, iterations), iterations)


def binary_opening(mask, iterations=1):
    return binary_dilation(binary_erosion(mask, iterations), iterations)


def label(mask):
    """(int32 labels, n): 4-connected components of the nonzero pixels, numbered 1.. in raster order of their first
    pixel (as scipy.ndimage.label with its default structure)."""
    m = np.asarray(mask, bool)
    h, w = m.shape
    lab = np.zeros((h, w), np.int32)
    n = 0
    for y, x in zip(*np.nonzero(m)):
        if lab[y, x]:
            continue
        n += 1
        stack = [(y, x)]
        lab[y, x] = n
        while stack:
            cy, cx = stack.pop()
            for ny, nx in ((cy - 1, cx), (cy + 1, cx), (cy, cx - 1), (cy, cx + 1)):
                if 0 <= ny < h and 0 <= nx < w and m[ny, nx] and not lab[ny, nx]:
                    lab[ny, nx] = n
                    stack.append((ny, nx))
    return lab, n


def binary_fill_holes(mask):
    """The mask with every background region that doesn't touch the border (4-connected) filled."""
    m = np.asarray(mask, bool)
    lab, n = label(~m)
    edge = set(np.unique(np.concatenate([lab[0], lab[-1], lab[:, 0], lab[:, -1]]))) - {0}
    holes = (lab > 0) & ~np.isin(lab, list(edge))
    return m | holes


def distance_transform_edt(mask):
    """float64 exact Euclidean distance from each nonzero pixel to the nearest zero pixel (0 at zeros), as
    scipy.ndimage.distance_transform_edt(mask). Two exact passes: g = each pixel's distance to the nearest zero in its
    own row, then D^2(y, x) = min over rows y' of (y - y')^2 + g(y', x)^2, all in integers."""
    m = np.asarray(mask, bool)
    h, w = m.shape
    if m.all():
        return np.full((h, w), np.inf)
    big = h + w + 1                                          # farther than any real distance
    xs = np.arange(w)
    left = np.where(~m, xs, -big)                            # the last zero at or left of x
    left = np.maximum.accumulate(left, axis=1)
    right = np.where(~m, xs, 2 * big + w)                    # the next zero at or right of x
    right = np.minimum.accumulate(right[:, ::-1], axis=1)[:, ::-1]
    g = np.minimum(xs - left, right - xs).astype(np.int64)  # (big: no zero in the row)
    g2 = g * g
    best = np.full((h, w), np.iinfo(np.int64).max, np.int64)
    ys = np.arange(h)[:, None]
    for yy in range(h):
        best = np.minimum(best, (ys - yy) ** 2 + g2[yy][None, :])
    return np.sqrt(best.astype(np.float64)) * m


def kmeans2(data, k, iter=10, minit="++", seed=None):
    """(centroids (k, d), labels) as scipy.cluster.vq.kmeans2(data, k, iter, minit="++", seed=seed): k-means++
    seeding, then `iter` rounds of assigning each point to its nearest centroid (squared Euclidean) and moving each
    centroid to its points' mean; a centroid with no points keeps its place. The labels are those of the last
    assignment, as scipy returns them. Deterministic for a seed; not bit-identical to scipy's (its RNG draws differ)."""
    assert minit == "++", "only k-means++ seeding"
    x = np.asarray(data, float)
    if x.ndim == 1:
        x = x[:, None]
    rng = np.random.default_rng(seed)
    n = len(x)
    cent = np.empty((k, x.shape[1]))
    cent[0] = x[rng.integers(n)]
    d2 = ((x - cent[0]) ** 2).sum(1)
    for j in range(1, k):
        total = d2.sum()
        cent[j] = x[rng.choice(n, p=d2 / total)] if total > 0 else x[rng.integers(n)]
        d2 = np.minimum(d2, ((x - cent[j]) ** 2).sum(1))
    label = np.zeros(n, int)
    for _ in range(iter):
        label = np.empty(n, int)
        for s in range(0, n, 4096):                          # (chunks: n x k distances stay small)
            label[s:s + 4096] = ((x[s:s + 4096, None, :] - cent[None]) ** 2).sum(2).argmin(1)
        sums = np.zeros_like(cent)
        np.add.at(sums, label, x)
        count = np.bincount(label, minlength=k)
        has = count > 0
        cent[has] = sums[has] / count[has, None]
    return cent, label
