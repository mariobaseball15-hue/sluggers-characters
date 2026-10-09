"""Read MY2.brsar (NintendoWare sound archive): sound names, their RWSD wave data, DSP-ADPCM decode to WAV.

  python scripts/brsar.py list <brsar> [regex]            # name, sound index, type, file id
  python scripts/brsar.py wav <brsar> <regex> <out dir>   # decode matching WAVE sounds to 16-bit WAVs

Layout (all big-endian; "refs" are {u8 is_offset, u8 type, u16, u32 value} relative to INFO+8):
- header: RSAR, then SYMB / INFO / FILE offsets and sizes at 0x10.
- SYMB: string table of names; INFO entries refer to names by index.
- INFO: refs to the sound, bank, player, file and group tables. A sound entry is {name, file id, player,
  3D-param ref, volume, priority, type (1 SEQ, 2 STRM, 3 WAVE), remote filter, detail ref, ...}; a WAVE
  sound's detail starts with the index of its entry in the RWSD's DATA section.
- A file's first group position says where its bytes are: group {name, entry, ext ref, offset, size,
  wave offset, wave size, item table ref}; an item is {file id, offset, size, wave offset, wave size}
  (offsets relative to the group's). RWSD bytes and wave bytes are stored apart.
- RWSD: DATA section (entries -> tracks -> notes -> wave index) and WAVE section (wave infos: format,
  loop, channels, rate, data offset into the wave bytes, channel infos with DSP-ADPCM coefficients).
"""
import re
import struct
import sys
import wave
from pathlib import Path


def u8(b, o): return b[o]
def u16(b, o): return struct.unpack_from(">H", b, o)[0]
def u32(b, o): return struct.unpack_from(">I", b, o)[0]
def s16(b, o): return struct.unpack_from(">h", b, o)[0]


class Brsar:
    def __init__(self, path):
        self.b = b = Path(path).read_bytes()
        assert b[:4] == b"RSAR"
        self.symb, _, self.info, _, self.file, _ = struct.unpack_from(">6I", b, 0x10)
        s = self.symb + 8
        st = u32(b, s)
        self.names = []
        for i in range(u32(b, s + st)):
            o = s + u32(b, s + st + 4 + 4 * i)
            self.names.append(b[o:b.index(b"\0", o)].decode("latin1"))
        self.base = self.info + 8

    def ref(self, o):
        return u32(self.b, o + 4)

    def table(self, which):
        t = self.base + self.ref(self.base + 8 * which)
        return [self.base + self.ref(t + 4 + 8 * i) for i in range(u32(self.b, t))]

    def sounds(self):
        b = self.b
        out = []
        for i, o in enumerate(self.table(0)):
            name = self.names[u32(b, o)] if u32(b, o) < len(self.names) else None
            out.append(dict(index=i, off=o, name=name, file=u32(b, o + 4), type=b[o + 0x16],
                            detail=self.base + self.ref(o + 0x18)))
        return out

    def file_bytes(self, file_id):
        """(RWSD bytes, wave bytes) of a file, from its first group position."""
        b = self.b
        fo = self.table(3)[file_id]
        pos_table = self.base + self.ref(fo + 0x14)
        pos = self.base + self.ref(pos_table + 4)
        group, index = u32(b, pos), u32(b, pos + 4)
        g = self.table(4)[group]
        g_off, g_wave = u32(b, g + 0x10), u32(b, g + 0x18)
        items = self.base + self.ref(g + 0x20)
        item = self.base + self.ref(items + 4 + 8 * index)
        fid, off, size, woff, wsize = struct.unpack_from(">5I", b, item)
        assert fid == file_id, (fid, file_id)
        return b[g_off + off:g_off + off + size], b[g_wave + woff:g_wave + woff + wsize]


def rwsd_wave_index(r, entry):
    """RWSD (v1.3: DATA section only) entry -> wave index: entry {ref wsd info, ref tracks, ref notes};
    the first note's info starts with the wave index. Refs are relative to DATA+8."""
    assert r[:4] == b"RWSD"
    d = u32(r, 0x10) + 8
    e = d + u32(r, d + 4 + 8 * entry + 4)
    notes = d + u32(r, e + 0x14)
    note = d + u32(r, notes + 8)
    return u32(r, note)


def rwar_wave(w, index):
    """RWAR (TABL of {ref, size} to RWAV files) wave `index` -> (rate, [channel samples])."""
    assert w[:4] == b"RWAR"
    tabl = u32(w, 0x10)
    data = u32(w, 0x18)
    rv = data + u32(w, tabl + 0xC + 12 * index + 4)
    assert w[rv:rv + 4] == b"RWAV", w[rv:rv + 4]
    info = rv + u32(w, rv + 0x10)
    wdata = rv + u32(w, rv + 0x18)
    wi = info + 8
    fmt, nch = w[wi], w[wi + 2]
    rate = (w[wi + 3] << 16) | u16(w, wi + 4)
    loop_end = u32(w, wi + 0xC)
    chans = wi + u32(w, wi + 0x10)
    out = []
    for c in range(nch):
        ci = wi + u32(w, chans + 4 * c)
        start = wdata + 8 + u32(w, ci)
        adpcm = wi + u32(w, ci + 4)
        coefs = [s16(w, adpcm + 2 * k) for k in range(16)]
        out.append(dsp_decode(w, start, loop_end, coefs) if fmt == 2 else pcm16(w, start, loop_end))
    return rate, out


def dsp_decode(b, start, nibbles, coefs):
    samples, h1, h2 = [], 0, 0
    n = nibbles - (nibbles + 15) // 16 * 2              # frames: 1 header byte (2 nibbles) + 14 samples
    o = start
    while len(samples) < n:
        ps = b[o]
        pred, scale = ps >> 4, 1 << (ps & 0xF)
        c1, c2 = coefs[2 * pred], coefs[2 * pred + 1]
        for k in range(14):
            byte = b[o + 1 + k // 2]
            nib = (byte >> 4) if k % 2 == 0 else (byte & 0xF)
            if nib >= 8:
                nib -= 16
            v = ((nib * scale) << 11) + 1024 + c1 * h1 + c2 * h2
            v = max(-32768, min(32767, v >> 11))
            samples.append(v)
            h2, h1 = h1, v
            if len(samples) >= n:
                break
        o += 8
    return samples


def pcm16(b, start, n):
    return [s16(b, start + 2 * k) for k in range(n)]


def write_wav(path, rate, chans):
    with wave.open(str(path), "wb") as w:
        w.setnchannels(len(chans))
        w.setsampwidth(2)
        w.setframerate(rate)
        frames = bytearray()
        for i in range(len(chans[0])):
            for ch in chans:
                frames += struct.pack("<h", ch[i])
        w.writeframes(bytes(frames))


def main():
    cmd, path = sys.argv[1], sys.argv[2]
    a = Brsar(path)
    pat = re.compile(sys.argv[3]) if len(sys.argv) > 3 else None
    if cmd == "list":
        for s in a.sounds():
            if s["name"] and (pat is None or pat.search(s["name"])):
                print(s["index"], s["name"], "type", s["type"], "file", s["file"])
    elif cmd == "wav":
        out = Path(sys.argv[4])
        out.mkdir(parents=True, exist_ok=True)
        for s in a.sounds():
            if s["type"] == 3 and s["name"] and pat.search(s["name"]):
                r, wb = a.file_bytes(s["file"])
                idx = rwsd_wave_index(r, u32(a.b, s["detail"]))
                rate, chans = rwar_wave(wb, idx)
                write_wav(out / f"{s['name']}.wav", rate, chans)
                print(f"WAV {s['name']}: wave {idx}, {rate} Hz, {len(chans[0]) / rate:.2f} s")


if __name__ == "__main__":
    main()


def dsp_encode(samples, coefs):
    """16-bit samples -> (DSP-ADPCM bytes, final history). Per 14-sample frame, picks the predictor pair
    and scale with the least squared error (exhaustive over 8 x 16 scales, 2^0..2^15; the first on a tie), tracking the
    decoder's own history so errors don't accumulate. Returns bytes padded to whole 8-byte frames. All 128 candidates
    run at once in numpy, sample by sample (byte-identical to the per-candidate loop it replaced, about 2.5x faster;
    so brsar_write.ENCODER, the cache key, stays)."""
    import numpy as np
    x = np.asarray(samples, dtype=np.int64)
    n = len(x)
    nf = (n + 13) // 14
    xp = np.zeros(nf * 14, np.int64)
    xp[:n] = x
    c1 = np.repeat(np.array(coefs[0::2], np.int64), 16)            # candidate k = p * 16 + s
    c2 = np.repeat(np.array(coefs[1::2], np.int64), 16)
    scale = np.tile(np.int64(1) << np.arange(16, dtype=np.int64), 8)
    fscale = scale.astype(np.float64)
    out = bytearray()
    h1 = h2 = 0
    for f in range(nf):
        frame = xp[f * 14:f * 14 + 14]
        a1 = np.full(128, h1, np.int64)
        a2 = np.full(128, h2, np.int64)
        err = np.zeros(128, np.int64)
        nibs = np.empty((14, 128), np.int64)
        for i in range(14):
            t = frame[i]
            base = c1 * a1 + c2 * a2
            pred = (base + 1024) >> 11
            q = np.clip(np.round((t - pred) / fscale), -8, 7).astype(np.int64)
            v = np.clip((((q * scale) << 11) + 1024 + base) >> 11, -32768, 32767)
            err += (t - v) ** 2
            nibs[i] = q & 0xF
            a2, a1 = a1, v
        k = int(np.argmin(err))
        p, s = divmod(k, 16)
        out.append((p << 4) | s)
        col = nibs[:, k]
        for j in range(0, 14, 2):
            out.append(int((col[j] << 4) | col[j + 1]))
        h1, h2 = int(a1[k]), int(a2[k])
    return bytes(out), (h1, h2)


# ---------------------------------------------------------------------------------------------- DSP-ADPCM streams
# Coefficient training, a searching encoder and an RSTM (.brstm) writer / reader for stream sounds (Pauline's
# chance jingle, make_pauline_jingle.py). dsp_encode above stays as it is for the voices (brsar_write).

def _dsp_analyze_ranges(mtx, idx):
    recips = [0.0] * 3
    for x in (1, 2):
        val = max(abs(mtx[x][1]), abs(mtx[x][2]))
        if val < 2.220446049250313e-16:
            return True
        recips[x] = 1.0 / val
    max_index = 0
    for i in (1, 2):
        for x in range(1, i):
            tmp = mtx[x][i]
            for y in range(1, x):
                tmp -= mtx[x][y] * mtx[y][i]
            mtx[x][i] = tmp
        val = 0.0
        for x in range(i, 3):
            tmp = mtx[x][i]
            for y in range(1, i):
                tmp -= mtx[x][y] * mtx[y][i]
            mtx[x][i] = tmp
            tmp = abs(tmp) * recips[x]
            if tmp >= val:
                val, max_index = tmp, x
        if max_index != i:
            for y in (1, 2):
                mtx[max_index][y], mtx[i][y] = mtx[i][y], mtx[max_index][y]
            recips[max_index] = recips[i]
        idx[i] = max_index
        if mtx[i][i] == 0.0:
            return True
        if i != 2:
            tmp = 1.0 / mtx[i][i]
            for x in range(i + 1, 3):
                mtx[x][i] *= tmp
    lo = min(abs(mtx[1][1]), abs(mtx[2][2]))
    hi = max(abs(mtx[1][1]), abs(mtx[2][2]))
    return lo / hi < 1.0e-10


def _dsp_bidirectional_filter(mtx, idx, v):
    x = 0
    for i in (1, 2):
        index = idx[i]
        tmp = v[index]
        v[index] = v[i]
        if x != 0:
            for y in range(x, i):
                tmp -= v[y] * mtx[i][y]
        elif tmp != 0.0:
            x = i
        v[i] = tmp
    for i in (2, 1):
        tmp = v[i]
        for y in range(i + 1, 3):
            tmp -= v[y] * mtx[i][y]
        v[i] = tmp / mtx[i][i]
    v[0] = 1.0


def _dsp_quadratic_merge(v):
    v2 = v[2]
    tmp = 1.0 - v2 * v2
    if tmp == 0.0:
        return True
    v0 = (v[0] - v2 * v2) / tmp
    v1 = (v[1] - v[1] * v2) / tmp
    v[0], v[1] = v0, v1
    return abs(v1) > 1.0


def _dsp_finish_record(v, out):
    for z in (1, 2):
        if v[z] >= 1.0:
            v[z] = 0.9999999999
        elif v[z] <= -1.0:
            v[z] = -0.9999999999
    out[0] = 1.0
    out[1] = v[2] * v[1] + v[1]
    out[2] = v[2]


def _dsp_matrix_filter(src, dst):
    mtx = [[0.0] * 3 for _ in range(3)]
    mtx[2][0] = 1.0
    for i in (1, 2):
        mtx[2][i] = -src[i]
    for i in (2, 1):
        val = 1.0 - mtx[i][i] * mtx[i][i]
        for y in range(1, i + 1):
            mtx[i - 1][y] = (mtx[i][i] * mtx[i][y] + mtx[i][y]) / val
    dst[0] = 1.0
    for i in (1, 2):
        dst[i] = 0.0
        for y in range(1, i + 1):
            dst[i] += mtx[i][y] * dst[i - y]


def _dsp_merge_finish_record(src, dst):
    tmp = [0.0] * 3
    val = src[0]
    dst[0] = 1.0
    for i in (1, 2):
        v2 = 0.0
        for y in range(1, i):
            v2 += dst[y] * src[i - y]
        dst[i] = -(v2 + src[i]) / val if val > 0.0 else 0.0
        tmp[i] = dst[i]
        for y in range(1, i):
            dst[y] += dst[i] * dst[i - y]
        val *= 1.0 - dst[i] * dst[i]
    _dsp_finish_record(tmp, dst)


def _dsp_contrast(s1, s2):
    val = (s2[2] * s2[1] - s2[1]) / (1.0 - s2[2] * s2[2])
    val1 = s1[0] * s1[0] + s1[1] * s1[1] + s1[2] * s1[2]
    val2 = s1[0] * s1[1] + s1[1] * s1[2]
    val3 = s1[0] * s1[2]
    return val1 + 2.0 * val * val2 + 2.0 * (-s2[1] * val - s2[2]) * val3


def _dsp_filter_records(best, exp, records):
    for _ in range(2):
        counts = [0] * exp
        acc = [[0.0] * 3 for _ in range(exp)]
        buf = [0.0] * 3
        for rec in records:
            index, value = 0, 1.0e30
            for i in range(exp):
                t = _dsp_contrast(best[i], rec)
                if t < value:
                    value, index = t, i
            counts[index] += 1
            _dsp_matrix_filter(rec, buf)
            for i in range(3):
                acc[index][i] += buf[i]
        for i in range(exp):
            if counts[i] > 0:
                for y in range(3):
                    acc[i][y] /= counts[i]
        for i in range(exp):
            _dsp_merge_finish_record(acc[i], best[i])


def dsp_correlate_coefs(samples):
    """16-bit samples -> 16 DSP-ADPCM coefficients (8 predictor pairs c1, c2 in 1/2048) fitted to the signal:
    Nintendo's DSPADPCM training (DSPCorrelateCoefs, as ported by gc-dspadpcm-encode and VGAudio). Per
    14-sample frame, a 2nd-order predictor from the frame's autocorrelation (the previous frame as history),
    then 3 rounds of split-and-cluster (1 -> 2 -> 4 -> 8 centroids). Gives VGAudio's coefficients bit for bit
    on the Pauline jingle."""
    x = [int(v) for v in samples]
    records, prev = [], [0] * 14
    for blk in range(0, len(x), 0x3800):                 # the reference walks 0x3800-sample blocks
        chunk = x[blk:blk + 0x3800]
        m = len(chunk)
        chunk = chunk + [0] * 14                         # a partial last frame is zero-padded
        for i in range(0, m, 14):
            cur = chunk[i:i + 14]
            h = prev + cur
            prev = cur
            v = [-float(sum(h[14 + k - j] * h[14 + k] for k in range(14))) for j in range(3)]
            if abs(v[0]) > 10.0:
                mtx = [[0.0] * 3 for _ in range(3)]
                for a in (1, 2):
                    for b in (1, 2):
                        mtx[a][b] = float(sum(h[14 + k - a] * h[14 + k - b] for k in range(14)))
                idx = [0] * 3
                if not _dsp_analyze_ranges(mtx, idx):
                    _dsp_bidirectional_filter(mtx, idx, v)
                    if not _dsp_quadratic_merge(v):
                        rec = [0.0] * 3
                        _dsp_finish_record(v, rec)
                        records.append(rec)
    best = [[0.0] * 3 for _ in range(8)]
    v, tmp = [1.0, 0.0, 0.0], [0.0] * 3
    for rec in records:
        _dsp_matrix_filter(rec, tmp)
        v[1] += tmp[1]
        v[2] += tmp[2]
    for y in (1, 2):
        v[y] /= max(len(records), 1)
    _dsp_merge_finish_record(v, best[0])
    exp = 1
    for w in range(3):
        for i in range(exp):
            best[exp + i] = [best[i][0], best[i][1] - 0.01, best[i][2]]
        exp = 1 << (w + 1)
        _dsp_filter_records(best, exp, records)
    out = []
    for z in range(8):
        for k in (1, 2):
            d = -best[z][k] * 2048.0
            r = int(abs(d) + 0.5) * (1 if d >= 0 else -1)   # C lround: half away from zero
            out.append(max(-32768, min(32767, r)))
    return out


def dsp_encode_search(samples, coefs, beam=4, h1=0, h2=0):
    """16-bit samples -> (DSP-ADPCM bytes, decoder history (h1, h2) at the start of every 14-sample frame).
    Per frame it tries all 8 predictors x 16 scales, closed loop on the decoder's own history, keeping the
    `beam` best nibble paths per candidate (a nibble moves the next predictions, so rounding each sample to
    nearest is not optimal). The frame's pick has the least squared error; padding past the end counts for
    nothing. Bytes are whole 8-byte frames."""
    import numpy as np
    x = np.asarray(samples, dtype=np.int64)
    n = len(x)
    nf = (n + 13) // 14
    xp = np.zeros(nf * 14, np.int64)
    xp[:n] = x
    c1 = np.repeat(np.array(coefs[0::2], np.int64), 16)[:, None]
    c2 = np.repeat(np.array(coefs[1::2], np.int64), 16)[:, None]
    sc = (1 << np.tile(np.arange(16), 8)).astype(np.int64)[:, None, None]
    rows = np.arange(128)[:, None]
    out, hist = bytearray(), []
    for f in range(nf):
        hist.append((h1, h2))
        fr = xp[f * 14:f * 14 + 14]
        a1 = np.full((128, 1), h1, np.int64)
        a2 = np.full((128, 1), h2, np.int64)
        err = np.zeros((128, 1), np.int64)
        nibs = np.zeros((128, 1, 0), np.int64)
        for t in range(14):
            live = int(f * 14 + t < n)
            pn = c1 * a1 + c2 * a2
            q = np.rint((fr[t] - ((pn + 1024) >> 11))[..., None] / sc).astype(np.int64)
            if beam > 1:
                q = np.concatenate([q - 1, q, q + 1], -1)
            q = np.clip(q, -8, 7)
            v = np.clip((((q * sc) << 11) + 1024 + pn[..., None]) >> 11, -32768, 32767)
            e = err[..., None] + (fr[t] - v) ** 2 * live
            k = q.shape[1] * q.shape[2]
            j = q.shape[2]
            e, v, q = e.reshape(128, k), v.reshape(128, k), q.reshape(128, k)
            na2 = np.repeat(a1, j, axis=1)
            nn = np.concatenate([np.repeat(nibs, j, axis=1), q[..., None]], -1)
            if k > beam:
                keep = np.argsort(e, axis=1, kind="stable")[:, :beam]
                e, v, na2, nn = e[rows, keep], v[rows, keep], na2[rows, keep], nn[rows, keep]
            err, a2, a1, nibs = e, na2, v, nn
        c, b = divmod(int(np.argmin(err)), err.shape[1])
        p, s = divmod(c, 16)
        qs = nibs[c, b]
        h1, h2 = int(a1[c, b]), int(a2[c, b])
        out.append((p << 4) | s)
        for k in range(0, 14, 2):
            out.append(((int(qs[k]) & 15) << 4) | (int(qs[k + 1]) & 15))
    return bytes(out), hist


RSTM_BLOCK = 0x2000                  # bytes per channel per block, as in every stock stream
RSTM_BLOCK_SAMPLES = RSTM_BLOCK // 8 * 14


def rstm_build(channels, rate, codec="adpcm", beam=4):
    """[16-bit samples per channel] -> non-looping .brstm bytes (RSTM v1.0, 8192-byte blocks interleaved by
    channel, the last block padded to 32 bytes per channel).

    codec "adpcm" (codec byte 2), the stock layout: HEAD 0x100 (stream info, 1 track, channel infos with each
    channel's own trained coefficients), ADPC = the decoder history at each block start, 14336 samples per block;
    the last block holds its bytes up to the last sample's nibble.
    codec "pcm16" (codec byte 1): big-endian 16-bit samples, 4096 per block, lossless. No stock stream uses it, so
    the layout is VGAudio's (the common Wii tool): 2 chunks, HEAD 0xA0 whose channel infos point at no ADPCM info
    (the game reads coefficients only for codec 2, 0x80558284), no ADPC chunk (read only for ADPCM, 0x8055944c)."""
    nch, n = len(channels), len(channels[0])
    assert nch in (1, 2) and all(len(c) == n for c in channels) and rate < 0x10000 and codec in ("adpcm", "pcm16")
    adpcm = codec == "adpcm"
    if adpcm:
        enc = []
        for ch in channels:
            coefs = dsp_correlate_coefs(ch)
            enc.append((coefs,) + dsp_encode_search(ch, coefs, beam))
        per_block = RSTM_BLOCK_SAMPLES
    else:
        enc = [(None, struct.pack(f">{n}h", *(int(v) for v in ch)), None) for ch in channels]
        per_block = RSTM_BLOCK // 2
    blocks = (n + per_block - 1) // per_block
    last_samples = n - (blocks - 1) * per_block
    if adpcm:
        last_size = last_samples // 14 * 8 + ((last_samples % 14 + 1) // 2 + 1 if last_samples % 14 else 0)
    else:
        last_size = last_samples * 2
    last_padded = (last_size + 31) // 32 * 32
    head_size = 0x100 if adpcm else 0xA0
    adpc_size = (8 + blocks * nch * 4 + 31) // 32 * 32 if adpcm else 0
    data_off = 0x40 + head_size + adpc_size
    head = bytearray(head_size)
    head[0:4] = b"HEAD"
    struct.pack_into(">I", head, 4, head_size)
    base = 8                                            # refs are relative to HEAD + 8
    for k, ref in enumerate((0x18, 0x4C, 0x64)):
        struct.pack_into(">BBHI", head, base + 8 * k, 1, 0, 0, ref)
    struct.pack_into(">BBBBHH", head, base + 0x18, 2 if adpcm else 1, 0, nch, 0, rate, 0)    # no loop
    interval, entry = (per_block, 4) if adpcm else (0, 0)
    struct.pack_into(">11I", head, base + 0x20, 0, n, data_off + 0x20, blocks, RSTM_BLOCK, per_block,
                     last_size, last_samples, last_padded, interval, entry)
    struct.pack_into(">BBH", head, base + 0x4C, 1, 1, 0)                       # 1 track, type 1
    struct.pack_into(">BBHI", head, base + 0x50, 1, 1, 0, 0x58)                 # ref type 1, as stock
    struct.pack_into(">BBHIB", head, base + 0x58, 0x7F, 0x40, 0, 0, nch)      # volume, pan, its channels
    head[base + 0x61:base + 0x61 + nch] = bytes(range(nch))
    head[base + 0x64] = nch
    for c, (coefs, data, hist) in enumerate(enc):
        info = 0x78 + (0x38 if adpcm else 8) * c
        struct.pack_into(">BBHI", head, base + 0x68 + 8 * c, 1, 0, 0, info)
        struct.pack_into(">BBHI", head, base + info, 1, 0, 0, info + 8 if adpcm else 0)
        if adpcm:
            struct.pack_into(">16h", head, base + info + 8, *coefs)
            struct.pack_into(">HHhhHhh", head, base + info + 0x28, 0, data[0], 0, 0, data[0], 0, 0)
    adpc = bytearray(adpc_size)
    if adpcm:
        adpc[0:4] = b"ADPC"
        struct.pack_into(">I", adpc, 4, adpc_size)
        for k in range(blocks):
            for c, (_, _, hist) in enumerate(enc):
                struct.pack_into(">hh", adpc, 8 + 4 * (k * nch + c), *hist[k * per_block // 14])
    body = bytearray()
    for k in range(blocks):
        size, padded = (last_size, last_padded) if k == blocks - 1 else (RSTM_BLOCK, RSTM_BLOCK)
        for _, data, _ in enc:
            chunk = data[k * RSTM_BLOCK:k * RSTM_BLOCK + size]
            assert len(chunk) == size, (k, len(chunk), size)
            body += chunk + bytes(padded - size)
    dat = bytearray(0x20)
    dat[0:4] = b"DATA"
    struct.pack_into(">II", dat, 4, 0x20 + len(body), 0x18)
    dat += body
    hdr = bytearray(0x40)
    hdr[0:4] = b"RSTM"
    struct.pack_into(">HHIHH6I", hdr, 4, 0xFEFF, 0x0100, data_off + len(dat), 0x40, 2,
                     0x40, head_size, 0x40 + head_size if adpcm else 0, adpc_size, data_off, len(dat))
    return bytes(hdr + head + adpc + dat)


def rstm_parse(b):
    """.brstm -> {info: HEAD stream info, channels: [{coefs, gain, ps, h1, h2, lps, lh1, lh2}] (ADPCM only, else
    [{}] per channel), adpc: [[(h1, h2) per channel] per block] (None without an ADPC chunk), blocks: [[bytes per
    channel] per block]}."""
    assert b[:4] == b"RSTM" and u16(b, 4) == 0xFEFF
    head, _, adpc, adpc_size, data, _ = struct.unpack_from(">6I", b, 0x10)
    base = head + 8
    si = base + u32(b, base + 4)
    keys = ("codec loop channels rate loop_start samples data_offset blocks block_size block_samples "
            "last_block_size last_block_samples last_block_padded adpc_interval adpc_bytes").split()
    info = dict(zip(keys, (b[si], b[si + 1], b[si + 2], u16(b, si + 4)) + struct.unpack_from(">11I", b, si + 8)))
    ct = base + u32(b, base + 0x14)
    chans = []
    for c in range(b[ct]):
        if info["codec"] != 2:
            chans.append({})
            continue
        ao = base + u32(b, base + u32(b, ct + 4 + 8 * c + 4) + 4)
        rest = struct.unpack_from(">HHhhHhh", b, ao + 32)
        chans.append(dict(coefs=[s16(b, ao + 2 * k) for k in range(16)], gain=rest[0], ps=rest[1], h1=rest[2],
                          h2=rest[3], lps=rest[4], lh1=rest[5], lh2=rest[6]))
    nch, nb = info["channels"], info["blocks"]
    hist = None
    if adpc and adpc_size:
        assert b[adpc:adpc + 4] == b"ADPC"
        hist = [[(s16(b, adpc + 8 + 4 * (k * nch + c)), s16(b, adpc + 10 + 4 * (k * nch + c))) for c in range(nch)]
                for k in range(nb)]
    d = info["data_offset"]
    assert d == data + 0x20 and b[data:data + 4] == b"DATA"
    blocks = []
    for k in range(nb):
        last = k == nb - 1
        stride = info["last_block_padded"] if last else info["block_size"]
        size = info["last_block_size"] if last else info["block_size"]
        o = d + k * info["block_size"] * nch
        blocks.append([b[o + c * stride:o + c * stride + size] for c in range(nch)])
    return dict(info=info, channels=chans, adpc=hist, blocks=blocks)


def _dsp_decode_from(b, n, coefs, h1, h2):
    out, o = [], 0
    while len(out) < n:
        ps = b[o]
        c1, c2, scale = coefs[2 * (ps >> 4)], coefs[2 * (ps >> 4) + 1], 1 << (ps & 0xF)
        for k in range(14):
            if len(out) >= n:
                break
            nib = (b[o + 1 + k // 2] >> 4) if k % 2 == 0 else (b[o + 1 + k // 2] & 0xF)
            nib = nib - 16 if nib >= 8 else nib
            v = max(-32768, min(32767, (((nib * scale) << 11) + 1024 + c1 * h1 + c2 * h2) >> 11))
            out.append(v)
            h2, h1 = h1, v
        o += 8
    return out, h1, h2


def rstm_decode(b, blockwise=True):
    """.brstm -> ([samples per channel], [(channel, block, decoder state, ADPC entry) where they differ]).
    blockwise=True starts every block from its own ADPC history (what a player does when it seeks to or refills
    from a block start); False carries the history across blocks (one continuous decode)."""
    r = rstm_parse(b)
    i = r["info"]
    out, diff = [], []
    if i["codec"] == 1:                                  # PCM16: big-endian samples, nothing carried between blocks
        for c in range(i["channels"]):
            samples = []
            for k, blk in enumerate(r["blocks"]):
                n = i["last_block_samples"] if k == i["blocks"] - 1 else i["block_samples"]
                assert len(blk[c]) == 2 * n, (k, len(blk[c]), n)
                samples += struct.unpack(f">{n}h", blk[c])
            out.append(samples)
        return out, diff
    assert i["codec"] == 2, f"codec {i['codec']}"
    for c, ch in enumerate(r["channels"]):
        h1, h2, samples = ch["h1"], ch["h2"], []
        for k, blk in enumerate(r["blocks"]):
            if (h1, h2) != r["adpc"][k][c]:
                diff.append((c, k, (h1, h2), r["adpc"][k][c]))
            if blockwise:
                h1, h2 = r["adpc"][k][c]
            n = i["last_block_samples"] if k == i["blocks"] - 1 else i["block_samples"]
            s, h1, h2 = _dsp_decode_from(blk[c], n, ch["coefs"], h1, h2)
            samples += s
        out.append(samples)
    return out, diff
