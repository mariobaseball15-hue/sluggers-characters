"""Minimal DOL image: read/write by RAM address and add sections."""
import struct
import sys
from pathlib import Path

HELPERS = {"patch_word", "relocate"}                            # shared writers: Dol.trace names their caller


class Dol:
    # {word address: who}: which module (charbuild: its function and line) last wrote each word, for the Gecko map
    # (charbuild.gecko_map: a player's code on a word we changed conflicts with that step); None = not recorded
    trace = None

    def __init__(self, path):
        self.data = bytearray(Path(path).read_bytes())
        h = self.data
        self.offs = list(struct.unpack(">18I", h[0x00:0x48]))
        self.addrs = list(struct.unpack(">18I", h[0x48:0x90]))
        self.sizes = list(struct.unpack(">18I", h[0x90:0xD8]))

    def _loc(self, addr, n=1):
        for o, a, s in zip(self.offs, self.addrs, self.sizes):
            if s and a <= addr and addr + n <= a + s:
                return o + addr - a
        raise KeyError(f"0x{addr:08X} (+{n}) not in any DOL section")

    def read(self, addr, n):
        o = self._loc(addr, n)
        return bytes(self.data[o:o + n])

    def u32(self, addr):
        return struct.unpack(">I", self.read(addr, 4))[0]

    def write(self, addr, blob):
        o = self._loc(addr, len(blob))
        self.data[o:o + len(blob)] = blob
        if self.trace is not None:
            f = sys._getframe(1)
            while f.f_code.co_filename == __file__ or f.f_code.co_name in HELPERS:   # (w32 -> write, charbuild's
                f = f.f_back                                    # patch_word / relocate: the step that called them)
            mod = Path(f.f_code.co_filename).stem
            who = f"{mod}.{f.f_code.co_name}:{f.f_lineno}" if mod == "charbuild" else mod
            for a in range(addr & ~3, addr + len(blob), 4):
                self.trace[a] = who

    def w32(self, addr, value):
        self.write(addr, struct.pack(">I", value & 0xFFFFFFFF))

    def add_section(self, kind, addr, blob):
        """Append a text or data section (kind 'text'/'data') loaded at addr."""
        slots = range(0, 7) if kind == "text" else range(7, 18)
        slot = next(i for i in slots if self.sizes[i] == 0)
        blob = bytes(blob) + b"\0" * (-len(blob) % 32)
        off = len(self.data) + (-len(self.data) % 32)
        self.data += b"\0" * (off - len(self.data)) + blob
        self.offs[slot], self.addrs[slot], self.sizes[slot] = off, addr, len(blob)
        return slot

    def merge_sections(self, slots, kind="text"):
        """Replace these sections with one covering their whole address range (their bytes at the same
        addresses, zeros in the gaps between them), freeing the other slots. The old bytes stay in the file,
        unreferenced. Returns the new section's slot."""
        spans = sorted((self.addrs[i], self.offs[i], self.sizes[i]) for i in slots)
        lo, hi = spans[0][0], max(a + n for a, _, n in spans)
        blob = bytearray(hi - lo)
        for a, o, n in spans:
            blob[a - lo:a - lo + n] = self.data[o:o + n]
        for i in slots:
            self.offs[i] = self.addrs[i] = self.sizes[i] = 0
        return self.add_section(kind, lo, bytes(blob))

    def save(self, path):
        self.data[0x00:0x48] = struct.pack(">18I", *self.offs)
        self.data[0x48:0x90] = struct.pack(">18I", *self.addrs)
        self.data[0x90:0xD8] = struct.pack(">18I", *self.sizes)
        Path(path).write_bytes(self.data)
