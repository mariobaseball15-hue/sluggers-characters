"""Add WAVE sounds (custom character voices) to a BRSAR, the way Extra Innings added Rosalina, Luma and Larry:
new clips go into an existing RWSD + RWAR file (the template family's voice file, or the character-select
voice file), and each gets a new sound entry. Returns the new sounds' INFO ids for the voice tables.

  from brsar_write import add_sounds
  ids = add_sounds("MY2.brsar", "out/MY2.brsar", [
      {"name": "zziggy_v1", "file": 40, "wav": "models/work/sounds/sets/iggy/v1.wav"}, ...],
      template_sound="cuppa_jr_v1")

What changes:
- RWAR of each touched file: rebuilt with the new RWAVs appended (DSP-ADPCM via brsar.dsp_encode, with
  the predictor coefficients of an existing wave in that file, at the clip's own sample rate).
- RWSD: rebuilt with one new DATA entry per clip, a byte copy of entry 0 (entries are contiguous blocks
  whose refs point inside themselves) relocated, with the new wave index in its note.
- INFO: new sound entries (copies of `template_sound`'s entry, detail and 3D-param blocks, file id and RWSD
  entry index changed) appended at the end, and the sound table moved to the end with the extra refs.
  File table sizes follow the new files.
- SYMB: names appended; the string table moves to the end. The name-lookup tries are not updated (the
  game plays voices by id).
- FILE: laid out again group by group (files, then wave data, 32-byte aligned); group and item offsets
  and sizes rewritten.

Streams (`streams=`, e.g. Pauline's chance jingle): each is a new STRM sound after the clips, a copy of a stock
stream sound's entry, detail ({start 0, 2 channels, track flags 1}) and 3D-param blocks, with a new file entry
the way stock streams have them: {size = the .brstm's length (the DVD stream clamps reads to it), wave size 0,
entry -1, ref to its external path "stream/<name>.brstm", ref to an empty position table}. The file table
moves to the end with the extra refs. No bytes go into FILE: the game opens the .brstm from sound_NA/stream,
so the build must ship it there.
"""
import hashlib
import struct
import sys
import wave
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path(__file__).parent))
from brsar import Brsar, dsp_encode, s16, u16, u32  # noqa: E402


def align(n, a=0x20):
    return (n + a - 1) & ~(a - 1)


def pad(b, a=0x20):
    return bytes(b) + bytes(align(len(b), a) - len(b))


def p32(v):
    return struct.pack(">I", v)


def read_wav(path):
    with wave.open(str(path)) as w:
        n, ch, rate, width = w.getnframes(), w.getnchannels(), w.getframerate(), w.getsampwidth()
        raw = w.readframes(n)
    assert width == 2, f"{path}: 16-bit WAV expected"
    x = np.frombuffer(raw, dtype="<i2").reshape(-1, ch).mean(axis=1)
    return rate, np.round(x).astype(np.int64)


# ---------------------------------------------------------------------------------------------- RWAR/RWAV

def rwar_split(w):
    """RWAR -> list of RWAV blobs."""
    tabl, data = u32(w, 0x10), u32(w, 0x18)
    n = u32(w, tabl + 8)
    out = []
    for i in range(n):
        e = tabl + 0xC + 12 * i
        off, size = u32(w, e + 4), u32(w, e + 8)
        out.append(w[data + off:data + off + size])
    return out


def rwar_build(rwavs, version):
    n = len(rwavs)
    tabl = pad(b"TABL" + p32(0) + p32(n) + b"".join(bytes(12) for _ in range(n)))
    body = bytearray()
    entries = bytearray()
    cursor = 8                                        # RWAV offsets are relative to DATA start
    for rv in rwavs:
        cursor = align(cursor)
        entries += b"\x01\x00\x00\x00" + p32(cursor) + p32(len(rv))
        body += bytes(cursor - 8 - len(body)) + rv
        cursor += len(rv)
    tabl = bytearray(tabl)
    tabl[0xC:0xC + 12 * n] = entries
    struct.pack_into(">I", tabl, 4, len(tabl))
    data = pad(b"DATA" + p32(0) + bytes(body))
    data = bytearray(data)
    struct.pack_into(">I", data, 4, len(data))
    hdr = bytearray(0x20)
    hdr[0:4] = b"RWAR"
    struct.pack_into(">HH", hdr, 4, 0xFEFF, version)
    struct.pack_into(">IHH", hdr, 8, 0x20 + len(tabl) + len(data), 0x20, 2)
    struct.pack_into(">IIII", hdr, 0x10, 0x20, len(tabl), 0x20 + len(tabl), len(data))
    return bytes(hdr + tabl + data)


def rwav_layout(t):
    """A mono ADPCM RWAV's (wave info, channel info, ADPCM info) offsets."""
    info = u32(t, 0x10)
    wi = info + 8
    assert t[wi] == 2 and t[wi + 2] == 1, "template must be a mono ADPCM wave"
    chans = wi + u32(t, wi + 0x10)
    ci = wi + u32(t, chans)
    return wi, ci, wi + u32(t, ci + 4)


def rwav_coefs(template):
    """The template wave's 16 predictor coefficients."""
    adpcm = rwav_layout(template)[2]
    return [s16(template, adpcm + 2 * k) for k in range(16)]


def rwav_build(template, rate, samples):
    """New RWAV from an existing one's INFO layout, mono DSP-ADPCM of `samples`."""
    return rwav_from(template, rate, len(samples), dsp_encode(samples, rwav_coefs(template))[0])


def rwav_from(template, rate, n, enc):
    """New RWAV from an existing one's INFO layout and n samples already encoded with its coefficients (enc)."""
    t = bytearray(template)
    info = u32(t, 0x10)
    wi, ci, adpcm = rwav_layout(t)
    nibbles = (n // 14) * 16 + ((n % 14) + 2 if n % 14 else 0)
    t[wi + 1] = 0                                     # no loop
    t[wi + 3] = (rate >> 16) & 0xFF
    struct.pack_into(">H", t, wi + 4, rate & 0xFFFF)
    struct.pack_into(">II", t, wi + 8, 0, nibbles)    # loop start, loop end (end of sound, in nibbles)
    struct.pack_into(">H", t, adpcm + 0x22, enc[0])   # initial predictor/scale
    struct.pack_into(">hh", t, adpcm + 0x24, 0, 0)    # history
    info_end = info + u32(t, 0x14)
    head = bytes(t[:info_end])
    data = pad(b"DATA" + p32(0) + enc)
    data = bytearray(data)
    struct.pack_into(">I", data, 4, len(data))
    head = bytearray(pad(head))
    struct.pack_into(">II", head, 0x18, len(head), len(data))
    struct.pack_into(">I", head, 8, len(head) + len(data))
    # channel data offset is relative to the DATA section's data (after its 8-byte header)
    struct.pack_into(">I", head, ci, 0)
    return bytes(head + data)


def rwav_error(rv, x):
    """Squared error of an RWAV's decoded samples against the source."""
    from brsar import dsp_decode
    info = u32(rv, 0x10)
    wi = info + 8
    ci = wi + u32(rv, wi + u32(rv, wi + 0x10))
    adpcm = wi + u32(rv, ci + 4)
    coefs = [s16(rv, adpcm + 2 * k) for k in range(16)]
    start = u32(rv, 0x18) + 8
    y = np.array(dsp_decode(rv, start, u32(rv, wi + 0xC), coefs)[:len(x)])
    return float(((x[:len(y)] - y) ** 2).sum())


# ---------------------------------------------------------------------------------------------- RWSD

def is_ref(b, o, lo, hi):
    return b[o] == 1 and b[o + 2:o + 4] == b"\0\0" and lo <= u32(b, o + 4) < hi


def rwsd_add_entries(r, wave_indexes):
    """Append one entry per wave index, each a copy of entry 0 pointing at that wave."""
    assert r[:4] == b"RWSD"
    ver = u16(r, 6)
    data = u32(r, 0x10)
    d = data + 8
    n = u32(r, d)
    starts = [u32(r, d + 4 + 8 * i + 4) for i in range(n)]
    ends = starts[1:] + [u32(r, data + 4) - 8]
    body_start = 4 + 8 * n
    blocks = [bytes(r[d + s:d + e]) for s, e in zip(starts, ends)]
    template, t0 = blocks[0], starts[0]
    note_off = u32(r, d + u32(r, d + t0 + 0x14) + 8)  # entry -> note table -> first note (DATA+8-relative)
    # refs inside the template block
    ref_pos = [k for k in range(0, len(template) - 7, 4) if is_ref(template, k, t0, t0 + len(template))]
    new_n = n + len(wave_indexes)
    shift = 8 * len(wave_indexes)
    out_blocks, table = [], []
    cursor = 4 + 8 * new_n
    for s, blk in zip(starts, blocks):
        delta = cursor - s
        blk = bytearray(blk)
        for k in range(0, len(blk) - 7, 4):
            if is_ref(blk, k, s, s + len(blk)):
                struct.pack_into(">I", blk, k + 4, u32(blk, k + 4) + delta)
        table.append(cursor)
        out_blocks.append(bytes(blk))
        cursor += len(blk)
    for wi in wave_indexes:
        delta = cursor - t0
        blk = bytearray(template)
        for k in ref_pos:
            struct.pack_into(">I", blk, k + 4, u32(blk, k + 4) + delta)
        struct.pack_into(">I", blk, note_off - t0, wi)
        table.append(cursor)
        out_blocks.append(bytes(blk))
        cursor += len(blk)
    assert shift >= 0
    sec = bytearray(b"DATA" + p32(0) + p32(new_n))
    for off in table:
        sec += b"\x01\x00\x00\x00" + p32(off)
    for blk in out_blocks:
        sec += blk
    sec = bytearray(pad(sec))
    struct.pack_into(">I", sec, 4, len(sec))
    hdr = bytearray(r[:0x20])
    struct.pack_into(">I", hdr, 8, 0x20 + len(sec))
    struct.pack_into(">II", hdr, 0x10, 0x20, len(sec))
    return bytes(hdr + sec), list(range(n, new_n))


# ---------------------------------------------------------------------------------------------- whole archive

# The encoded-clip cache (add_sounds(cache=)): encoding is the slow part (dsp_encode, pure Python, 6 candidates a clip),
# so a patch reuses our clips' encodings. A cache file holds only our audio: which candidate won (0..5) and its
# DSP-ADPCM bytes. Its name is a hash of everything the encoding depends on: ENCODER, the clip's samples (after
# drive) and rate, and the candidates' coefficients (read from the player's archive), so a changed clip or game
# re-encodes. The RWAV headers, stock waves and RWAR/RWSD layout are always rebuilt from the player's archive.
ENCODER = b"brsar.dsp_encode exhaustive 8x16; best of the file's first 6 mono waves by rwav_error; v1"
CANDIDATES = 6


def clip_key(rate, x, coefs):
    h = hashlib.sha256(ENCODER)
    h.update(struct.pack(">II", rate, len(x)) + np.asarray(x, ">i4").tobytes())
    for c in coefs:
        h.update(struct.pack(">16h", *c))
    return h.hexdigest()


def encode_clip(cands, rate, x, cache=None):
    """The RWAV of a clip: the candidate template whose coefficients reproduce it best (first on a tie). With a cache
    folder, a hit skips the encoding and a miss is written there ("<key>.dsp": u8 candidate, then the bytes)."""
    path = Path(cache) / f"{clip_key(rate, x, [rwav_coefs(t) for t in cands])}.dsp" if cache else None
    if path and path.is_file():
        b = path.read_bytes()
        return rwav_from(cands[b[0]], rate, len(x), b[1:])
    encs = [dsp_encode(x, rwav_coefs(t))[0] for t in cands]
    built = [rwav_from(t, rate, len(x), e) for t, e in zip(cands, encs)]
    k = min(range(len(built)), key=lambda i: rwav_error(built[i], x))
    if path:
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(bytes([k]) + encs[k])
    return built[k]


def candidates(rwavs):
    """A file's candidate templates for new clips: its first CANDIDATES mono waves."""
    return [rv for rv in rwavs if rv[u32(rv, 0x10) + 8] == 2 and rv[u32(rv, 0x10) + 10] == 1][:CANDIDATES]


def clip_samples(c):
    """A clip's (rate, samples) as they are encoded."""
    rate, x = read_wav(c["wav"])
    if c.get("drive"):   # louder without a higher peak: gain into a soft clip back to full scale
        x = np.round(32000 * np.tanh(c["drive"] * x / 32000) / np.tanh(c["drive"])).astype(np.int64)
    return rate, x


def _encode_job(job):
    encode_clip(*job)


def fill_cache(src, clips, cache, workers=None):
    """Encode the clips missing from the cache folder in parallel (processes), so add_sounds(cache=) only splices.
    Returns (clips, encoded)."""
    from concurrent.futures import ProcessPoolExecutor
    a = Brsar(src)
    cands = {f: candidates(rwar_split(a.file_bytes(f)[1])) for f in {c["file"] for c in clips}}
    jobs = []
    for c in clips:
        rate, x = clip_samples(c)
        key = clip_key(rate, x, [rwav_coefs(t) for t in cands[c["file"]]])
        if not (Path(cache) / f"{key}.dsp").is_file():
            jobs.append((cands[c["file"]], rate, x, cache))
    if jobs:
        with ProcessPoolExecutor(workers) as pool:
            list(pool.map(_encode_job, jobs))
    return len(clips), len(jobs)


def add_sounds(src, dst, clips, template_sound, streams=(), cache=None):
    """clips: [{name, file, wav, [volume], [drive], [template]}] WAVE sounds (template: a stock WAVE sound whose
    entry this clip's copies, else template_sound); streams: [{name, path ("stream/x.brstm"), size,
    template (a stock STRM sound's name)}]. Appends only: new sounds get ids after every existing one (clips,
    then streams) and new files ids after every existing file. Returns {name: sound id}.
    cache: a folder of encoded clips (encode_clip), else every clip is encoded."""
    a = Brsar(src)
    b = bytearray(a.b)
    sounds = {s["name"]: s for s in a.sounds()}
    tmpl = sounds[template_sound]

    # 1. Files: group positions and blobs
    files = a.table(3)
    groups = a.table(4)
    file_pos = {}                                      # file id -> [(group, item index)]
    for fid, fo in enumerate(files):
        pt = a.base + a.ref(fo + 0x14)
        file_pos[fid] = [(u32(b, a.base + a.ref(pt + 4 + 8 * i)), u32(b, a.base + a.ref(pt + 4 + 8 * i) + 4))
                         for i in range(u32(b, pt))]
    blobs = {}
    for fid in range(len(files)):
        if file_pos[fid]:
            blobs[fid] = list(a.file_bytes(fid))

    # 2. New clips into their files
    by_file = {}
    for c in clips:
        by_file.setdefault(c["file"], []).append(c)
    entry_of = {}
    for fid, cs in by_file.items():
        r, w = blobs[fid]
        rwavs = rwar_split(w)
        first = len(rwavs)
        cands = candidates(rwavs)
        for c in cs:
            # predictor coefficients from whichever stock wave of this file reproduces the clip best
            rwavs.append(encode_clip(cands, *clip_samples(c), cache))
        w = rwar_build(rwavs, u16(w, 6))
        r, entries = rwsd_add_entries(r, list(range(first, first + len(cs))))
        blobs[fid] = [r, w]
        for c, e in zip(cs, entries):
            entry_of[c["name"]] = (fid, e)

    # 3. SYMB: names appended, string table moved to the end
    symb, symb_size = u32(b, 0x10), u32(b, 0x14)
    s0 = symb + 8
    st = u32(b, s0)
    names = list(a.names)
    new_name_idx = {}
    for c in list(clips) + list(streams):
        new_name_idx[c["name"]] = len(names)
        names.append(c["name"])
    sym = bytearray(b[symb:symb + symb_size])
    str_off = {}
    for i, nm in enumerate(names[len(a.names):], start=len(a.names)):
        str_off[i] = len(sym) - 8
        sym += nm.encode("latin1") + b"\0"
    while len(sym) % 4:
        sym.append(0)
    new_table = len(sym) - 8
    sym += p32(len(names))
    for i in range(len(names)):
        sym += p32(u32(b, s0 + st + 4 + 4 * i) if i < len(a.names) else str_off[i])
    struct.pack_into(">I", sym, 8, new_table)
    sym = bytearray(pad(sym))
    struct.pack_into(">I", sym, 4, len(sym))

    # 4. INFO: new sound entries + relocated sound table
    info, info_size = u32(b, 0x18), u32(b, 0x1C)
    inf = bytearray(b[info:info + info_size])
    base = 8                                            # refs relative to INFO+8
    def tmpl_offs(t):
        return t["off"] - info, t["detail"] - info, a.base + a.ref(t["off"] + 0xC) - info
    entry_len, detail_len, p3d_len = 0x2C, 0x14, 0x0C
    new_refs = []
    for c in clips:
        t_entry, t_detail, t_3d = tmpl_offs(sounds[c["template"]] if c.get("template") else tmpl)
        fid, e = entry_of[c["name"]]
        while len(inf) % 4:
            inf.append(0)
        p3 = len(inf)
        inf += inf[t_3d:t_3d + p3d_len]
        det = len(inf)
        inf += inf[t_detail:t_detail + detail_len]
        struct.pack_into(">I", inf, det, e)
        ent = len(inf)
        inf += inf[t_entry:t_entry + entry_len]
        struct.pack_into(">II", inf, ent, new_name_idx[c["name"]], fid)
        if "volume" in c:                               # sound volume byte (stock voices: 0x6B)
            inf[ent + 0x14] = c["volume"]
        struct.pack_into(">I", inf, ent + 0xC + 4, p3 - base)
        struct.pack_into(">I", inf, ent + 0x18 + 4, det - base)
        new_refs.append(ent - base)
    # streams: sound entry + detail + 3D params (copies of a stock stream's) and a new external file entry
    old_files = u32(inf, base + 3 * 8 + 4)
    n_files = u32(inf, base + old_files)
    new_file_refs = []
    for k, st in enumerate(streams):
        ts = sounds[st["template"]]
        assert ts["type"] == 2, f"{st['template']} is not a stream sound"
        assert st["path"].startswith("stream/") and len(st["path"]) < 0x80, st["path"]
        while len(inf) % 4:
            inf.append(0)
        path_at = len(inf)
        inf += st["path"].encode("ascii") + bytes(1)
        while len(inf) % 4:
            inf.append(0)
        pos_at = len(inf)
        inf += p32(0)                                   # no group positions: an external file
        fent = len(inf)
        inf += struct.pack(">IIi", st["size"], 0, -1)
        inf += bytes([1, 0, 0, 0]) + p32(path_at - base) + bytes([1, 0, 0, 0]) + p32(pos_at - base)
        new_file_refs.append(fent - base)
        te, td = ts["off"] - info, ts["detail"] - info
        t3 = a.base + a.ref(ts["off"] + 0xC) - info
        p3 = len(inf)
        inf += inf[t3:t3 + p3d_len]
        det = len(inf)
        inf += inf[td:td + 0xC]                          # STRM detail: start position, channels, track flags
        ent = len(inf)
        inf += inf[te:te + entry_len]
        struct.pack_into(">II", inf, ent, new_name_idx[st["name"]], n_files + k)
        struct.pack_into(">I", inf, ent + 0xC + 4, p3 - base)
        struct.pack_into(">I", inf, ent + 0x18 + 4, det - base)
        new_refs.append(ent - base)
    if streams:                                         # file table moved to the end with the new refs
        while len(inf) % 4:
            inf.append(0)
        ft = len(inf)
        inf += p32(n_files + len(streams)) + bytes(inf[base + old_files + 4:base + old_files + 4 + 8 * n_files])
        for r_ in new_file_refs:
            inf += bytes([1, 0, 0, 0]) + p32(r_)
        struct.pack_into(">I", inf, base + 3 * 8 + 4, ft - base)
    old_t = u32(inf, base + 4)
    old_n = u32(inf, base + old_t)
    while len(inf) % 4:
        inf.append(0)
    new_t = len(inf)
    inf += p32(old_n + len(new_refs)) + bytes(inf[base + old_t + 4:base + old_t + 4 + 8 * old_n])
    for r_ in new_refs:
        inf += b"\x01\x00\x00\x00" + p32(r_)
    struct.pack_into(">I", inf, base + 4, new_t - base)
    # file table sizes
    for fid in by_file:
        fo = files[fid] - info
        struct.pack_into(">II", inf, fo, len(blobs[fid][0]), len(blobs[fid][1]))
    inf = bytearray(pad(inf))
    struct.pack_into(">I", inf, 4, len(inf))

    # 5. FILE: lay out groups again
    fsec_hdr = bytearray(b"FILE" + bytes(0x1C))
    body = bytearray()
    file_start = 0x40 + len(sym) + len(inf)
    file_start = align(file_start)
    body_base = file_start + len(fsec_hdr)
    order = sorted(range(len(groups)), key=lambda g: u32(b, groups[g] + 0x10))
    for g in order:
        go = groups[g] - info
        items = base + u32(inf, go + 0x24)
        n_items = u32(inf, items)
        item_offs = [base + u32(inf, items + 4 + 8 * i + 4) for i in range(n_items)]
        g_off = body_base + len(body)
        for io in item_offs:
            fid = u32(inf, io)
            r = blobs[fid][0]
            while len(body) % 0x20:
                body.append(0)
            struct.pack_into(">II", inf, io + 4, body_base + len(body) - g_off, len(r))
            body += r
        while len(body) % 0x20:
            body.append(0)
        g_size = body_base + len(body) - g_off
        w_off = body_base + len(body)
        for io in item_offs:
            fid = u32(inf, io)
            w = blobs[fid][1]
            while len(body) % 0x20:
                body.append(0)
            struct.pack_into(">II", inf, io + 12, body_base + len(body) - w_off, len(w))
            body += w
        while len(body) % 0x20:
            body.append(0)
        struct.pack_into(">IIII", inf, go + 0x10, g_off, g_size, w_off, body_base + len(body) - w_off)
    fsec = fsec_hdr + body
    struct.pack_into(">I", fsec, 4, len(fsec))

    # 6. Header
    hdr = bytearray(b[:0x40])
    sym_off = 0x40
    inf_off = sym_off + len(sym)
    hdr_fields = (sym_off, len(sym), inf_off, len(inf), file_start, len(fsec))
    struct.pack_into(">6I", hdr, 0x10, *hdr_fields)
    out = hdr + sym + inf + bytes(file_start - inf_off - len(inf)) + fsec
    struct.pack_into(">I", out, 8, len(out))
    Path(dst).write_bytes(bytes(out))
    first_id = old_n
    return {c["name"]: first_id + i for i, c in enumerate(list(clips) + list(streams))}
