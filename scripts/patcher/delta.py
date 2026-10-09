"""Copy-aware deltas against the player's game: how the download carries a file we made from a game file without
carrying the game's bytes.

Most of our binaries are a game file with our data written over it (a model block on its donor's skeleton, a
stadium archive on Mario Stadium's, the voice archive with our clips). make() turns such a file into COPY ops
(offset and length in one of the clean game's files) and LITERAL ops (our bytes); apply() rebuilds it from the
player's game. A run shorter than BLOCK isn't found (one under 2 * BLOCK - 1 may not be), so the literals keep only short fragments of game data (headers
next to our edits).

Delta file: zlib of  b"SLGD1" | u32 length | sha1 (20) | ops
  op 0: COPY     varint source index, varint offset, varint length    (sources: SOURCES order)
  op 1: LITERAL  varint length, bytes
"""
import hashlib, struct, zlib
import numpy as np

MAGIC = b"SLGD1"
BLOCK = 32                      # bytes per indexed source block (aligned); a run of 2 * BLOCK - 1 is always found
W = BLOCK // 8                  # uint64 words per block
SOURCES = ["sys/main.dol", "files/dt_na.dat", "files/sound_NA/MY2.brsar"]    # in the clean game folder
_MIX = np.array([0x9E3779B97F4A7C15, 0xC2B2AE3D27D4EB4F, 0x165667B19E3779F9, 0xD6E8FEB86659FD93,
                 0xFF51AFD7ED558CCD, 0xC4CEB9FE1A85EC53, 0x94D049BB133111EB, 0xBF58476D1CE4E5B9], np.uint64)


def _hashes(buf, start, stop):
    """Hash of the BLOCK bytes at every offset in [start, stop) (as uint64), offsets in order."""
    n = stop - start
    out = np.empty(n, np.uint64)
    for s in range(8):
        first = start + s
        count = (n - s + 7) // 8
        if count <= 0:
            continue
        words = np.frombuffer(buf, np.uint64, count + W - 1, first)      # W words from each offset
        win = np.lib.stride_tricks.sliding_window_view(words, W)[:count]
        with np.errstate(over="ignore"):
            out[s::8] = (win * _MIX[:W]).sum(axis=1, dtype=np.uint64)
    return out


class Index:
    """Every aligned BLOCK of the sources, by hash."""

    def __init__(self, sources):
        self.sources = sources                      # [bytes]
        keys, where = [], []
        for i, src in enumerate(sources):
            n = len(src) // BLOCK
            if not n:
                continue
            words = np.frombuffer(src, np.uint64, n * W).reshape(n, W)
            with np.errstate(over="ignore"):
                keys.append((words * _MIX[:W]).sum(axis=1, dtype=np.uint64))
            where.append((np.full(n, i, np.int64) << 40) | (np.arange(n, dtype=np.int64) * BLOCK))
        keys, where = np.concatenate(keys), np.concatenate(where)
        order = np.argsort(keys, kind="stable")
        self.keys, self.where = keys[order], where[order]


def _run(a, i, b, j, limit):
    """How many bytes a[i:] and b[j:] share (up to limit)."""
    n, step = 0, 4096
    while n < limit:
        k = min(step, limit - n)
        x = np.frombuffer(a, np.uint8, k, i + n)
        y = np.frombuffer(b, np.uint8, k, j + n)
        diff = np.flatnonzero(x != y)
        if diff.size:
            return n + int(diff[0])
        n += k
    return n


def _back(a, i, lo, b, j):
    """How many bytes before a[i] and b[j] match, going back no further than a[lo] / b[0]."""
    n = 0
    while i - n > lo and j - n > 0 and a[i - n - 1] == b[j - n - 1]:
        n += 1
    return n


def _varint(n):
    out = bytearray()
    while True:
        b, n = n & 0x7F, n >> 7
        out.append(b | (0x80 if n else 0))
        if not n:
            return bytes(out)


def make(target, index, chunk=1 << 22):
    """target (bytes) -> delta file bytes."""
    ops, pos, lit_start = bytearray(), 0, 0
    copied = 0
    n = len(target)
    scan = 0
    while scan + BLOCK <= n:
        stop = min(n - BLOCK + 1, scan + chunk)
        h = _hashes(target, scan, stop)
        at = np.searchsorted(index.keys, h)
        at[at == len(index.keys)] = 0
        hit = np.flatnonzero(index.keys[at] == h)
        q = 0
        while q < len(hit):
            k = hit[q]
            i = scan + int(k)
            q += 1
            if i < pos:
                q = int(np.searchsorted(hit, pos - scan))
                continue
            w = int(index.where[at[k]])
            src_i, j = w >> 40, w & ((1 << 40) - 1)
            src = index.sources[src_i]
            if target[i:i + BLOCK] != src[j:j + BLOCK]:
                continue
            fwd = _run(target, i, src, j, min(n - i, len(src) - j))
            back = _back(target, i, pos, src, j)
            i, j, length = i - back, j - back, fwd + back
            if i > lit_start:
                ops += b"\x01" + _varint(i - lit_start) + target[lit_start:i]
            ops += b"\x00" + _varint(src_i) + _varint(j) + _varint(length)
            copied += length
            pos = lit_start = i + length
        scan = max(stop, pos)
    if n > lit_start:
        ops += b"\x01" + _varint(n - lit_start) + target[lit_start:]
    head = MAGIC + struct.pack(">I", n) + hashlib.sha1(target).digest()
    return zlib.compress(head + bytes(ops), 9), copied


def info(delta):
    raw = zlib.decompress(delta)
    assert raw[:5] == MAGIC, "not a delta"
    return struct.unpack(">I", raw[5:9])[0], raw[9:29].hex()


def copied(delta, source):
    """[(start, end)] of source index `source` that the delta's COPY ops read (modded_game.conflicts: which of a
    modded game's changed files a delta that didn't rebuild needed)."""
    raw = zlib.decompress(delta)
    assert raw[:5] == MAGIC, "not a delta"
    out, p = [], 29

    def varint():
        nonlocal p
        v = shift = 0
        while True:
            b = raw[p]
            p += 1
            v |= (b & 0x7F) << shift
            shift += 7
            if not b & 0x80:
                return v
    while p < len(raw):
        op = raw[p]
        p += 1
        if op == 0:
            s, off, length = varint(), varint(), varint()
            if s == source:
                out.append((off, off + length))
        else:
            length = varint()               # (not `p += varint()`: that adds to p as it was before the varint)
            p += length
    return out


def apply(delta, sources):
    """delta file bytes + the player's game files (SOURCES order, as bytes or memoryviews) -> the file."""
    raw = zlib.decompress(delta)
    assert raw[:5] == MAGIC, "not a delta"
    n, sha = struct.unpack(">I", raw[5:9])[0], raw[9:29]
    out, p = bytearray(), 29

    def varint():
        nonlocal p
        v = shift = 0
        while True:
            b = raw[p]
            p += 1
            v |= (b & 0x7F) << shift
            shift += 7
            if not b & 0x80:
                return v
    while p < len(raw):
        op = raw[p]
        p += 1
        if op == 0:
            s, off, length = varint(), varint(), varint()
            out += sources[s][off:off + length]
        else:
            length = varint()
            out += raw[p:p + length]
            p += length
    out = bytes(out)
    if len(out) != n or hashlib.sha1(out).digest() != sha:
        raise ValueError("rebuilt file doesn't match: the game isn't the clean one this was made from")
    return out
