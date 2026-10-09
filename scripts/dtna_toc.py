"""dt_na.dat table of contents, as main.dol holds it.

A pointer table (RAM 0x806A0728, 172 entries) lists each directory's first file record; a
directory is a run of 48-byte file records, one 16-byte entry per language (en, sp, fr):
{u32 name ptr, u32 length, u32 offset, u32 length}. FUN_802c5fd0(dir, file) returns
dirs[dir] + (file * 3 + lang) * 16. Directories are contiguous, so a directory's file count is the
distance to the next one; the last runs to the end of the records block.
"""
import struct

DIR_TABLE, N_DIRS = 0x806A0728, 172
RECORDS_END = 0x806A0728     # the records block ends where the pointer table starts
FILE_RECORD = 48


def dir_pointers(dol, table=DIR_TABLE, n=N_DIRS):
    return list(struct.unpack(f">{n}I", dol.read(table, 4 * n)))


def toc(dol):
    """[[(offset, length), ...] per directory] (the English entry; the other languages agree)."""
    ptrs = dir_pointers(dol)
    ends = sorted(set(ptrs + [RECORDS_END]))
    out = []
    for p in ptrs:
        end = ends[ends.index(p) + 1]
        files = []
        for rec in range(p, end, FILE_RECORD):
            _, length, off, _ = struct.unpack(">4I", dol.read(rec, 16))
            files.append((off, length))
        out.append(files)
    return out


def rebuild_file(dol, dat_path, directory, index, rebuild):
    """Rebuild dt_na dir `directory` file `index` in the output's own dt_na.dat (dat_path): each language's copy
    (copies the languages share are rebuilt once) goes through rebuild(bytes) -> bytes, is appended (32-aligned) and
    the index record repointed. Returns the number of copies appended."""
    import os
    rec = dir_pointers(dol)[directory] + index * FILE_RECORD
    w = list(struct.unpack(">12I", dol.read(rec, 48)))
    placed = {}
    with open(dat_path, "r+b") as f:
        for lang in range(3):
            off, length = w[2 + 4 * lang], w[1 + 4 * lang]
            if off not in placed:
                f.seek(off)
                new = rebuild(f.read(length))
                end = os.path.getsize(dat_path)
                at = end + (-end % 32)
                f.seek(at)
                f.write(new)
                placed[off] = (at, len(new))
            at, n = placed[off]
            w[1 + 4 * lang], w[2 + 4 * lang], w[3 + 4 * lang] = n, at, n
    dol.write(rec, struct.pack(">12I", *w))
    return len(placed)


def locate(dol, ranges):
    """Map byte ranges of dt_na.dat to {(dir, file): (file_offset, file_length)}."""
    hits = {}
    for d, files in enumerate(toc(dol)):
        for f, (off, length) in enumerate(files):
            if any(a < off + length and off < b for a, b in ranges):
                hits[(d, f)] = (off, length)
    return hits
