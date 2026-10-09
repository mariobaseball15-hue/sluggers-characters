"""Offline gate for custom character model blocks: run before anything goes to Dolphin.

  python scripts/check_models.py                 # every models/configs/*_pack.json with built blocks
  python scripts/check_models.py <pack.json> ...

For each LOD block of each pack config (<pack out_dir>/<lod>.bin, the files charbuild installs), checks
what has crashed or broken the game before:

- Sluggies' BlockValidator (alignment, SKN source mirror, primitive lists, ...);
- block length equals the donor's (the dt_na entry is not resized);
- array headers are word aligned (docs/model-writer.md rule 2);
- SK1 and SK2 entries have at least 3 vertices: the skinning loops (FUN_80523e0c) run CTR = count - 1
  through bdnz, so a 1-vertex entry wraps to 2^32 iterations and reads past the locked cache
  ("Invalid read from 0xe0040000, PC 0x80523ec4"). Vanilla minimum is 3;
- SK1 entries fit 8180 source bytes and SK2 4088 (the 8 KB / 4 KB locked-cache buffers, vanilla maxima);
- no array header or data starts inside a skin entry's DMA write-back: FUN_80597bec copies the locked-cache
  buffer back in whole 32-byte lines ((bytes + 31) >> 5), so an entry writes up to the next line boundary,
  not just its vertices. A header there is overwritten each frame ("Invalid read from 0x00000000,
  PC = 0x8052ec90" in FUN_8052e99c, Pom Pom in chars-19);
- the skin only uses bones the donor's own skin uses at that LOD (with the donor block from
  extracted/clean): the other bones own rigid accessory meshes (GEO ids) or aren't in the low skin, and
  their palette matrices are not skinning matrices (invisible and misplaced models in chars-23).

Prints one line per block and exits non-zero if any block fails.
"""
import glob
import json
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from build_model import validate  # noqa: E402
from mss_model import Model, read_block  # noqa: E402

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
MIN_COUNT, SK1_MAX, SK2_MAX = 3, 8180, 4088


def skin_bones(m):
    k = m.skin
    out = {e["bone"] for e in k.sk1 + k.acc}
    for e in k.sk2:
        out.update(e["bones"])
    return out


def validator_available():
    """Sluggies' BlockValidator (refs/, unlicensed, never shipped) can be imported here."""
    try:
        validate(b"")
    except ImportError:
        return False
    except Exception:
        return True
    return True


def check_block(blk, donor_len, donor=None, validator=True):
    """Problems with a block ([] = passes). validator=False skips Sluggies' BlockValidator (the patcher's download
    has no refs/): the rest are our own checks of every crash seen so far."""
    problems = []
    if len(blk) != donor_len:
        problems.append(f"length {len(blk)} != donor {donor_len}")
    if validator:
        try:
            validate(blk)
        except ValueError as e:
            problems.append(str(e).splitlines()[0] + " " + " ".join(str(e).splitlines()[1:3]))
    m = Model(blk)
    for sm in m.submeshes:
        for a in [sm.position, sm.color, sm.normal] + list(sm.uvs):
            if a is not None and a.hdr % 4:
                problems.append(f"{sm.name}: array header at {a.hdr:#x} not word aligned")
    k = m.skin
    if k and donor is not None and Model(donor).skin:
        extra = sorted(skin_bones(m) - skin_bones(Model(donor)))
        if extra:
            problems.append(f"skin uses bones the donor's skin doesn't: {extra}")
    if k:
        sm = m.submeshes[0]
        P = sm.position.ptr
        line_end = max([e["dest"] + ((e["voff"] + e["count"] * k.stride + 31) & ~31) for e in k.sk1 + k.sk2],
                       default=0)
        starts = [a.hdr for a in [sm.color, sm.normal] + list(sm.uvs) if a is not None and a.hdr > P]
        # (skinned normals are interleaved in the position buffer, so the normal data pointer is not checked)
        starts += [a.ptr for a in [sm.color] + list(sm.uvs) if a is not None and a.ptr > P]
        inside = [s_ - P for s_ in starts if s_ < P + line_end]
        if inside:
            problems.append(f"skin DMA write-back runs to +{line_end:#x}, over data starting at "
                            f"+{min(inside):#x} of the positions")
        for kind, entries, cap in (("SK1", k.sk1, SK1_MAX), ("SK2", k.sk2, SK2_MAX)):
            small = [e["count"] for e in entries if e["count"] < MIN_COUNT]
            big = [e["voff"] + e["count"] * k.stride for e in entries if e["voff"] + e["count"] * k.stride > cap]
            if small:
                problems.append(f"{kind}: {len(small)} entries under {MIN_COUNT} vertices")
            if big:
                problems.append(f"{kind}: {len(big)} entries over {cap} bytes (max {max(big)})")
    return problems


def main():
    """Checks each pack config's built blocks (<pack out_dir>/<lod>.bin, what charbuild installs) against
    the stock donor block at that lod's offset. Prints the config name (e.g. "lemmy") in column 2."""
    args = sys.argv[1:]
    configs = [os.path.abspath(a) for a in args] or sorted(glob.glob(os.path.join(ROOT, "models/configs/*_pack.json")))
    failed = 0
    for pj in configs:
        name = os.path.basename(pj)[:-len("_pack.json")]
        pack = json.load(open(pj))["pack"]
        for lod_name, lod in pack["lods"].items():
            path = os.path.join(ROOT, pack["out_dir"], f"{lod_name}.bin")
            if not os.path.exists(path):
                continue                                # not built (not in the roster yet)
            off, length = int(lod["offset"], 0), lod["length"]
            blk = open(path, "rb").read()
            donor = read_block(os.path.join(ROOT, pack["dat"]), off, length)
            problems = check_block(blk, length, donor)
            k = Model(blk).skin
            shape = f"SK1 min {min((e['count'] for e in k.sk1), default='-')}, SK2 min "                     f"{min((e['count'] for e in k.sk2), default='-')}" if k else "no skin"
            status = "OK  " if not problems else "FAIL"
            failed += bool(problems)
            print(f"{status} {name:32} {lod_name:4} ({shape})" +
                  ("" if not problems else ": " + "; ".join(problems)), flush=True)
    sys.exit(1 if failed else 0)


if __name__ == "__main__":
    main()
