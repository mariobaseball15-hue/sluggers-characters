"""A shareable character file, <name>.slgmodel (git-92 for Nick: "all of our custom characters to be files that I
share ... easily editable by people in blender ... switch the base character"). Not shipped in the build: Nick shares
the files; "Import a model..." imports them (model_import.py).

A zip:
  character.json   {"format": 1, "name", "base": the stock character it's built on, "author", "from", "notes",
                    "left_out": [what the file doesn't carry, in words], "glb_sha1": model.glb's hash when exported,
                    "blocks": [file indexes], "voice": true / false}
  models/<N>.slgd  the game model: file 0 (and its low-detail copy 1) as a delta against the clean game (delta.py; no
                   game bytes, as character packs), rebuilt from the player's game on import
  model.glb        the same model as glTF 2.0, rigged to the base's skeleton, textures as PNGs (gltf_model.py): what
                   people open and edit in Blender. Unchanged (its hash matches), the game model is used as it is.
  side.png, front.png   the select-screen portraits (48x51)
  voice/<slot>.wav the clips the character has of its own (any of charpack.SLOTS); character.json's "voice_slots"
                   says "own" or "base" per slot: "base" plays the base character's sounds (never stock audio in a
                   file, git-92)
Only the model and its basics: no stats or chemistry (they come from the base, edited in the patcher), no items, star
moves, custom animations or behaviours.
"""
import hashlib, io, json, sys, zipfile
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
sys.path.insert(0, str(HERE / "patcher"))
from sluggie import SluggieError  # noqa: E402

FORMAT = 1
SUFFIX = ".slgmodel"
MAX_FILE = 64 << 20


def sha1(b):
    return hashlib.sha1(b).hexdigest()


def write(out, game, *, name, base, blocks, glb=None, icons=None, voice=None, author="", source="", notes="",
          left_out=()):
    """Write out (<name>.slgmodel). blocks: {file index: bytes} (0, and 1 when it has its own low-detail copy);
    icons: {"side" / "front": PNG bytes}; voice: {slot: wav bytes} (all 12) or None."""
    import charpack, delta
    idx = charpack.index(game)
    files = {}
    for i, b in sorted(blocks.items()):
        files[f"models/{int(i)}.slgd"] = delta.make(b, idx)[0]
    if glb is not None:
        files["model.glb"] = glb
    for view, data in (icons or {}).items():
        files[f"{view}.png"] = data
    for slot, data in (voice or {}).items():
        files[f"voice/{slot}.wav"] = data
    meta = {"format": FORMAT, "name": name, "base": base, "author": author, "from": source, "notes": notes,
            "left_out": list(left_out), "glb_sha1": sha1(glb) if glb is not None else None,
            "blocks": sorted(int(i) for i in blocks), "voice": bool(voice),
            "voice_slots": {s: "own" if s in (voice or {}) else "base" for s in _slots()}}
    out = Path(out)
    out.parent.mkdir(parents=True, exist_ok=True)
    with zipfile.ZipFile(out, "w", zipfile.ZIP_DEFLATED) as z:
        z.writestr("character.json", json.dumps(meta, indent=1, ensure_ascii=False))
        for n, data in files.items():
            z.writestr(n, data)
    return out


def _slots():
    import charpack
    return charpack.SLOTS


def read(path, game):
    """{"meta", "blocks": {file index: bytes} (rebuilt from the player's game), "glb": bytes or None, "glb_edited",
    "icons": {view: PIL image}, "voice": {slot: bytes} or None}. SluggieError in plain words."""
    import charpack
    from PIL import Image
    path = Path(path)
    try:
        if path.stat().st_size > MAX_FILE:
            raise SluggieError(f"{path.name} is too big to be a character file")
        z = zipfile.ZipFile(path)
        names = set(z.namelist())
        if sum(i.file_size for i in z.infolist()) > MAX_FILE:
            raise SluggieError(f"{path.name} is too big to be a character file")
        meta = json.loads(z.read("character.json").decode("utf8"))
    except (OSError, zipfile.BadZipFile, KeyError, ValueError):
        raise SluggieError(f"{path.name} isn't a character file (.slgmodel) or is damaged")
    if meta.get("format") != FORMAT:
        raise SluggieError(f"{path.name} is a newer character file than this patcher reads: get the latest patcher")
    blocks = {}
    with charpack.sources(game) as srcs:
        for i in meta.get("blocks", []):
            n = f"models/{int(i)}.slgd"
            if n not in names:
                raise SluggieError(f"{path.name} is damaged (no {n})")
            try:
                blocks[int(i)] = charpack.rebuild(z.read(n), srcs, f"its model file {i}")
            except charpack.PackError as e:
                raise SluggieError(str(e))
    glb = z.read("model.glb") if "model.glb" in names else None
    icons = {}
    for view in ("side", "front"):
        if f"{view}.png" in names:
            try:
                icons[view] = Image.open(io.BytesIO(z.read(f"{view}.png"))).convert("RGBA")
            except Exception:
                raise SluggieError(f"its {view} portrait can't be read as a picture")
    voice = {n[6:-4]: z.read(n) for n in names if n.startswith("voice/") and n.endswith(".wav")} or None
    return {"meta": meta, "blocks": blocks, "glb": glb,
            "glb_edited": glb is not None and meta.get("glb_sha1") not in (None, sha1(glb)),
            "icons": icons, "voice": voice}
