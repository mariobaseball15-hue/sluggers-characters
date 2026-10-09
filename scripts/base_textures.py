"""Persistent stock/base character texture replacements for Characters Beta.

The editor stores only user-selected PNGs plus a small JSON map. During a patch, each selected stock character model
file is rebuilt in memory from the player's current game and written back at the same dt_na.dat offset and length.
Geometry, bones, animation data and the DOL table of contents are untouched.
"""
import json
from pathlib import Path
from PIL import Image

ROOT = Path(__file__).resolve().parents[1]
CONFIG = ROOT / "base_texture_edits.json"
ASSET_DIR = ROOT / "base_texture_edits"
MODEL_DIR_BASE = 0x12


def load():
    try:
        d = json.loads(CONFIG.read_text(encoding="utf-8"))
        return d if isinstance(d, dict) else {}
    except (OSError, ValueError):
        return {}


def save(data):
    if data:
        CONFIG.write_text(json.dumps(data, indent=2), encoding="utf-8")
    else:
        CONFIG.unlink(missing_ok=True)


def set_png(cid, file_index, tex_index, source):
    cid, file_index, tex_index = int(cid), int(file_index), int(tex_index)
    ASSET_DIR.mkdir(parents=True, exist_ok=True)
    dst = ASSET_DIR / f"char_{cid:02x}_file{file_index}_tex{tex_index}.png"
    Image.open(source).convert("RGBA").save(dst)
    data = load()
    char = data.setdefault(str(cid), {})
    char[f"{file_index}:{tex_index}"] = str(dst.relative_to(ROOT)).replace("\\", "/")
    save(data)
    return dst


def clear(cid, keys=None):
    cid = str(int(cid))
    data = load()
    char = data.get(cid, {})
    if keys is None:
        keys = list(char)
    for key in list(keys):
        rel = char.pop(str(key), None)
        if rel:
            try:
                (ROOT / rel).unlink(missing_ok=True)
            except OSError:
                pass
    if not char:
        data.pop(cid, None)
    save(data)


def replacements(cid):
    out = {}
    for key, rel in load().get(str(int(cid)), {}).items():
        try:
            fi, ti = map(int, str(key).split(":", 1))
            p = ROOT / rel
            if p.exists():
                out[(fi, ti)] = p
        except (ValueError, TypeError):
            pass
    return out


def apply(game_path, dat_path):
    """Apply configured stock model texture edits in-place to output dt_na.dat. Returns log lines."""
    data = load()
    if not data:
        return []
    import recolor
    game = recolor.Game(str(game_path))
    log = []
    with open(dat_path, "r+b") as out:
        for cid_s, entries in sorted(data.items(), key=lambda kv: int(kv[0])):
            try:
                cid = int(cid_s)
            except ValueError:
                continue
            grouped = {}
            for key, rel in entries.items():
                try:
                    fi, ti = map(int, key.split(":", 1))
                    grouped.setdefault(fi, {})[ti] = Image.open(ROOT / rel).convert("RGBA")
                except (OSError, ValueError, TypeError):
                    continue
            for fi, overrides in grouped.items():
                try:
                    original = game.file(cid + MODEL_DIR_BASE, fi)
                    changed, pairs = recolor.recolor_block(original, [], overrides)
                    off, length = game.toc[cid + MODEL_DIR_BASE][fi]
                    if len(changed) != length:
                        raise ValueError(f"rebuilt file changed size ({len(changed)} != {length})")
                    out.seek(off)
                    out.write(changed)
                    log.append(f"base textures: character 0x{cid:02X} file {fi}: {len(pairs)} texture(s) replaced")
                except Exception as e:
                    log.append(f"base textures: character 0x{cid:02X} file {fi}: skipped ({type(e).__name__}: {e})")
    return log
