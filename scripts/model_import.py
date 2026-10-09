"""A whole custom character model as a NEW character on a donor's skeleton (git-92 for Nick: "someone would be able
to upload something and it imports the character"), in both patchers ("Import a model...").

  python scripts/model_import.py export <a mod's extracted game> <dt_na dir> -o <folder> [--name N] [--portraits ID]
  python scripts/model_import.py check <folder or a file in it> [--game extracted/clean]
  python scripts/model_import.py add <folder or a file in it> [--game extracted/clean] [--donor NAME] [--dest dir]

A model folder (what export writes, and what a player picks any file of):
  *.gpl.bin (or any file)  the character's model file(s) as the game stores them in dt_na.dat: a whole model block
                           (GPL geometry, ACT skeleton, TEX textures, SKN skinning), e.g. one of Extra Innings' custom
                           models, which are new blocks appended to its dt_na.dat keeping their donor's layout. Two
                           blocks: the larger is the model (file 0), the other its low-detail copy (file 1; a name
                           with "low" or "_L_" says so too); one block: both files, as Extra Innings ships its Luma.
  side.png, front.png      optional select-screen portraits (any size: fitted to 48x51)
  model.json               optional {"name": "...", "donor": "<stock character>", "author": "...", "from": "..."}
  voice/v1.wav ... v14.wav optional: its own voice clips (charpack.SLOTS; mono 22050 Hz 16-bit, <= 1.4 s), any of
                           the 12: the others play its donor's sounds

The donor (the stock character whose skeleton, animations and moves it uses) is found from the block itself: the
stock characters whose model has a byte-identical ACT (skeleton) section. With none (or several), the window asks.
Every block passes the model crash gate imports use (charpack.gate_lod against the donor's own), then the character
is stored like any added one (sluggie.store_character: "made_by": "player", its own square, model blocks as deltas
against the player's clean game).

Blender's route (a mesh fitted to a donor with scripts/build_character.py) needs Blender and our pipeline, which the
download doesn't ship: its result is a model block, which this imports.
"""
import argparse, json, re, sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
sys.path.insert(0, str(HERE / "patcher"))
import sluggie  # noqa: E402
from sluggie import SluggieError  # noqa: E402

MAX_BLOCK = 16 << 20                # charpack.MAX_FILE
MODEL_DIR_BASE = sluggie.MODEL_DIR_BASE


def _block_ok(data):
    try:
        from mss_model import Model
        Model(data)
        return True
    except Exception:
        return False


def read_model(path, game=None, base=None):
    """{"folder", "blocks": {0: bytes, 1: bytes}, "files": [names], "icons": {view: PIL image}, "meta": model.json,
    "voice": {slot: wav} or None} of the model folder at path (a folder, or any file in it), of a character file
    (.slgmodel: slgmodel.read, rebuilt from game), or of a bare .glb (a model edited in Blender: rebuilt onto base, a
    stock id, else the one its skeleton names; glb_base). SluggieError in plain words."""
    from PIL import Image
    path = Path(path)
    if path.suffix.lower() == ".glb":
        import game_source
        game = Path(game or game_source.root())
        glb = path.read_bytes()
        if base is None:
            base, _ = glb_base(glb, game)
        if base is None:
            raise SluggieError(f"pick the stock character {path.name} is built on (its skeleton doesn't say which)")
        import charpack
        with charpack.sources(game) as srcs:        # edited in place on the base's own model where it can (a scaled
            keep = {fi: charpack.stock_file(game, srcs, base, fi) for fi in sluggie.MODEL_FILES}   # mesh fits exactly)
        blocks, notes = rebuild_from_glb(glb, base, game, keep={k: v for k, v in keep.items() if v is not None})
        blocks.setdefault(1, blocks[0])
        return {"folder": path.parent, "blocks": blocks, "files": [path.name], "icons": {},
                "meta": {"name": _glb_name(path, glb), "donor": sluggie._name(base)}, "voice": None,
                "notes": ["a model from Blender: rebuilt onto its base's model"] + notes}
    if path.suffix.lower() == ".slgmodel":
        import slgmodel
        import game_source
        game = Path(game or game_source.root())
        c = slgmodel.read(path, game)
        blocks, notes = dict(c["blocks"]), list(c["meta"].get("left_out") or [])
        if c["glb_edited"]:                         # edited in Blender: rebuilt onto its base with our model writer
            base = _donor_id(c["meta"].get("base"))
            if base is None:
                raise SluggieError(f"{path.name} doesn't say which character it's built on")
            blocks, more = rebuild_from_glb(c["glb"], base, game, keep=blocks)
            notes = ["its model was edited in Blender: rebuilt from its model.glb"] + more + notes
        if 0 not in blocks:
            raise SluggieError(f"{path.name} has no model")
        blocks.setdefault(1, blocks[0])
        meta = {k: c["meta"].get(k) for k in ("name", "author", "from")}
        meta["donor"] = c["meta"].get("base")
        return {"folder": path.parent, "blocks": blocks, "files": [path.name], "icons": c["icons"], "meta": meta,
                "voice": c["voice"], "notes": notes}
    folder = path if path.is_dir() else path.parent
    found = []
    for p in sorted(folder.iterdir()) if folder.is_dir() else []:
        if not p.is_file() or p.suffix.lower() in (".png", ".json", ".txt", ".jpg", ".md", ".sluggie", ".zip"):
            continue
        if p.stat().st_size > MAX_BLOCK:
            continue
        data = p.read_bytes()
        if _block_ok(data):
            found.append((p, data))
    if not found:
        raise SluggieError(f"{folder.name} has no character model file (a model block from a game's dt_na.dat, e.g. "
                           f"what 'model_import.py export' writes)")
    if len(found) > 2:
        raise SluggieError(f"{folder.name} has {len(found)} model files: keep one model and, if it has one, its "
                           f"low-detail copy")
    low = [p for p, _ in found if re.search(r"(^|[_\-. ])(low|l)([_\-. ]|$)", p.stem, re.I)]
    if len(found) == 2:
        hi, lo = sorted(found, key=lambda f: (f[0] in low, -len(f[1])))
        blocks = {0: hi[1], 1: lo[1]}
    else:
        blocks = {0: found[0][1], 1: found[0][1]}
    icons = {}
    for view in ("side", "front"):
        p = next((q for q in sorted(folder.glob("*.png")) if view in q.stem.lower()), None)
        if p is not None:
            try:
                icons[view] = Image.open(p).convert("RGBA")
            except Exception:
                raise SluggieError(f"{p.name} can't be read as a picture")
    meta = {}
    if (folder / "model.json").exists():
        try:
            meta = json.loads((folder / "model.json").read_text(encoding="utf8"))
        except (OSError, ValueError):
            raise SluggieError("model.json isn't readable (it's JSON: {\"name\": ..., \"donor\": ...})")
    voice = None
    if (folder / "voice").is_dir():
        import charpack
        voice = {s: (folder / "voice" / f"{s}.wav").read_bytes() for s in charpack.SLOTS
                 if (folder / "voice" / f"{s}.wav").is_file()} or None   # any of the 12: the rest play the base's
    return {"folder": folder, "blocks": blocks, "files": [p.name for p, _ in found], "icons": icons, "meta": meta,
            "voice": voice, "notes": []}


def _act(block):
    from mss_model import Model
    a, e = Model(block).section_spans()["act"]
    return bytes(block[a:e])


_SKELETONS = {}


def donors(block, game):
    """Stock ids whose model file 0 or 1 has this block's skeleton (ACT) byte for byte, in id order."""
    import charpack
    key = str(Path(game).resolve())
    if key not in _SKELETONS:
        out = {}
        with charpack.sources(game) as srcs:
            for cid in range(sluggie.PLAYABLE):
                for fi in sluggie.MODEL_FILES:
                    b = charpack.stock_file(game, srcs, cid, fi)
                    try:
                        out.setdefault(_act(b), set()).add(cid)
                    except Exception:
                        continue
        _SKELETONS[key] = out
    try:
        return sorted(_SKELETONS[key].get(_act(block), ()))
    except Exception:
        return []


def _donor_id(ref):
    from sluggers_data import char_id
    try:
        cid = char_id(ref)
    except (KeyError, ValueError, TypeError):
        return None
    return cid if cid is not None and 0 <= cid < sluggie.PLAYABLE else None


def default_name(m):
    n = str(m["meta"].get("name") or "").strip()
    if n:
        return n
    words = re.sub(r"[_\-]+", " ", m["folder"].name).strip()
    return words.title() if words else "Imported model"


def describe(path, game):
    """{"name", "files", "donor": the stock character it goes on (name) or None (ask), "donors": the skeleton
    matches (names), "icons": [views it brings], "problems"} for the window."""
    if Path(path).suffix.lower() == ".glb":
        return _describe_glb(Path(path), Path(game))
    try:
        m = read_model(path, game)
    except SluggieError as e:
        return {"problems": [str(e)], "donors": [], "donor": None, "files": [], "icons": [], "name": None}
    found = [sluggie._name(c) for c in donors(m["blocks"][0], game)]
    hint = _donor_id(m["meta"].get("donor")) if m["meta"].get("donor") else None
    donor = sluggie._name(hint) if hint is not None else (found[0] if len(found) == 1 else None)
    return {"name": name_for(default_name(m), donor), "files": m["files"], "donor": donor, "donors": found,
            "icons": sorted(m["icons"]), "voice": bool(m["voice"]), "notes": m["notes"], "problems": []}


def add_model(path, game, donor=None, dest=None, taken_ids=(), taken_names=(), name=None, cid=None, icons=None,
              voice=None):
    """The model folder as a new character on donor (a stock name or id; default: describe()'s). icons / voice: what
    char_import found beside it ({view: PIL image}, {slot: clip bytes}); a .slgmodel's own come first, a model
    folder's are the same files (char_import's, converted, win). Returns store_character's result plus "warnings",
    "files", "own_icons", "own_voice"; SluggieError in plain words."""
    import charpack
    game = Path(game)
    r = describe(path, game)
    if r["problems"]:
        raise SluggieError(" ".join(r["problems"]))
    donor = donor if donor is not None else r["donor"]
    tid = _donor_id(donor) if donor is not None else None
    if tid is None:
        raise SluggieError("pick the stock character it's built on (its skeleton, animations and moves)")
    m = read_model(path, game, base=tid)
    warnings = []
    if r["donors"] and sluggie._name(tid) not in r["donors"]:
        warnings.append(f"its skeleton is {', '.join(r['donors'])}'s, not {sluggie._name(tid)}'s: it may not move right")
    elif not r["donors"]:
        warnings.append(f"its skeleton isn't any stock character's: on {sluggie._name(tid)}'s animations it may not "
                        f"move right")
    with charpack.sources(game) as srcs:
        for i, block in m["blocks"].items():
            try:
                charpack.gate_lod(block, game, srcs, tid, i)
            except charpack.PackError as err:
                raise SluggieError(f"{m['folder'].name}: the {err}")
    picked = Path(path) if Path(path).is_file() else None           # (its sha1: the window's replace-or-add)
    meta = {"_model": {"folder": None, "files": m["files"], "from": m["meta"].get("from"),
                       "sha1": charpack.sha1(picked.read_bytes()) if picked else None,
                       "author": m["meta"].get("author")}}
    own = Path(path).suffix.lower() == ".slgmodel"
    icons = {**(icons or {}), **m["icons"]} if own else {**m["icons"], **(icons or {})}
    voice = {**(voice or {}), **(m["voice"] or {})} if own else {**(m["voice"] or {}), **(voice or {})}
    out = sluggie.store_character(game, m["blocks"], tid, dest, taken_ids, taken_names,
                                  name=name or name_for(r["name"], sluggie._name(tid)),
                                  meta=meta, icons=icons or None, voice=voice or None, cid=cid)
    out["files"], out["own_icons"] = m["files"], sorted(icons)
    out["own_voice"] = [s for s in charpack.SLOTS if s in voice]
    if not icons:
        warnings.append(f"it has no portraits of its own: it shows {sluggie._name(tid)}'s on the select screen (add "
                        f"them on its Model page)")
    out["warnings"] = warnings
    return out


# ---- export an added character as a character file (the window's "Export .slgmodel...")

def export_character(definition, out, game, voice_clips=None):
    """An added character (its definition in the import folder) as a .slgmodel at out: its model (file 0, and file 1
    when it has its own low-detail copy) with model.glb for Blender, its portraits, name and base, and only the
    player's own voice clips: the character's stored clips, then the Voice page's (voice_clips {slot: path}) over
    them; every other slot says "base". Returns out."""
    import charpack
    import gltf_model
    import slgmodel
    definition = Path(definition)
    d = json.loads(definition.read_text(encoding="utf8"))
    folder = definition.parent.parent / definition.stem
    game = Path(game)
    blocks = {}
    with charpack.sources(game) as srcs:
        for i in (0, 1):
            rel = (d.get("model_blocks") or {}).get(str(i))
            if rel:
                blocks[i] = charpack.rebuild((folder / rel).read_bytes(), srcs, f"its model file {i}")
    if 0 not in blocks:
        raise SluggieError(f"{d['name']} has no model of its own to export")
    if blocks.get(1) == blocks[0]:
        del blocks[1]
    icons = {v: (folder / p).read_bytes() for v, p in (d.get("icon") or {}).items() if (folder / p).is_file()}
    voice = {}
    if d.get("voice"):
        for s in charpack.SLOTS:
            p = folder / d["voice"] / f"{s}.wav"
            if p.is_file():
                voice[s] = p.read_bytes()
    for s, p in (voice_clips or {}).items():
        if s in charpack.SLOTS and Path(p).is_file():
            voice[s] = Path(p).read_bytes()
    glb = gltf_model.block_to_glb(blocks[0], name=d["name"], base_name=d["template"])
    meta = d.get("_model") or d.get("_sluggie") or d.get("_pack") or {}
    return slgmodel.write(out, game, name=d["name"], base=d["template"], blocks=blocks, glb=glb, icons=icons,
                          voice=voice or None, author=str(meta.get("author") or ""),
                          source=str(meta.get("from") or meta.get("file") or ""),
                          left_out=["its moves and animations: they are its base's"])


# ---- Edit in Blender (Nick: no unzipping and zipping by hand): an added character's model.glb out, the edited one back

def _character(definition, game):
    """(definition dict, its folder, {file index: block}) of an added character in the import folder."""
    import charpack
    definition = Path(definition)
    d = json.loads(definition.read_text(encoding="utf8"))
    folder = definition.parent.parent / definition.stem
    blocks = {}
    with charpack.sources(Path(game)) as srcs:
        for i in (0, 1):
            rel = (d.get("model_blocks") or {}).get(str(i))
            if rel:
                blocks[i] = charpack.rebuild((folder / rel).read_bytes(), srcs, f"its model file {i}")
    if 0 not in blocks:
        raise SluggieError(f"{d['name']} has no model of its own")
    return d, folder, blocks


def character_glb(definition, game):
    """The Model page's Save model.glb...: the character's model (file 0) as a glTF for Blender (gltf_model), the
    same model.glb Export .slgmodel writes."""
    import gltf_model
    d, _, blocks = _character(definition, game)
    return gltf_model.block_to_glb(blocks[0], name=d["name"], base_name=d["template"])


def load_glb(definition, glb, game):
    """The Model page's Load edited model.glb...: the character's model rebuilt from the edited glTF (bytes or a
    path) with rebuild_from_glb (only the changed parts on its own model where it can), checked like an import
    (charpack.gate_lod) and stored in place of its model files; Export .slgmodel then carries the edit. Returns
    [notes]. SluggieError in plain words."""
    import charpack, delta
    from sluggers_data import char_id
    definition = Path(definition)
    game = Path(game)
    d, folder, blocks = _character(definition, game)
    data = glb if isinstance(glb, (bytes, bytearray)) else Path(glb).read_bytes()
    base = char_id(d["template"])
    new, notes = rebuild_from_glb(bytes(data), base, game, keep=blocks)
    new.setdefault(1, new[0])
    with charpack.sources(game) as srcs:
        for i, b in new.items():
            try:
                charpack.gate_lod(b, game, srcs, base, i)
            except charpack.PackError as err:
                raise SluggieError(f"the {err}")
    idx = charpack.index(game)
    for i, b in new.items():
        (folder / "models" / f"{i}.slgd").write_bytes(delta.make(b, idx)[0])
    d["model_blocks"] = {str(i): f"models/{i}.slgd" for i in sorted(new)}
    definition.write_text(json.dumps(d, indent=1, ensure_ascii=False), encoding="utf8")
    return notes


# ---- a bare .glb (Import character): its base from its skeleton

_GLB_SKELETONS = {}


def _glb_name(path, glb=None):
    """The name our export wrote in its scene (extras "sluggers"), else its file's."""
    import gltf_model
    try:
        gl, _ = gltf_model.read_glb(bytes(glb if glb is not None else Path(path).read_bytes()))
        named = str(((gl.get("scenes") or [{}])[0].get("extras") or {}).get("sluggers", {}).get("name") or "")
    except Exception:                               # noqa: BLE001 (describe says what's wrong with the file)
        named = ""
    if named.strip():
        return named.strip()
    words = re.sub(r"[_\-]+", " ", Path(path).stem).strip()
    return words.title() if words else "Imported model"


GENERIC_NAME = re.compile(r"(model|untitled|scene|mesh|object|armature|character|new character|imported model|"
                          r"export(ed)?( model)?)( ?\(\d+\)| ?[._-]?\d+)?", re.I)


def name_for(name, donor):
    """The name an import gets: its own, or "New <base>" when all it has is a generic file name ("Model (25)": a
    browser's second copy of model.glb, NSL's video)."""
    name = str(name or "").strip()
    if donor and (not name or GENERIC_NAME.fullmatch(name)):
        return f"New {donor}"
    return name or "Imported model"


def _glb_bones(gl):
    """{bone id: (parent bone id or None, rest translation)} of a glTF's "bone_<id>" nodes (our export names them so,
    and Blender keeps the names and the hierarchy, not the order)."""
    nodes = gl.get("nodes", [])
    parent = {c: i for i, n in enumerate(nodes) for c in n.get("children", ())}
    ident = {i: int(m.group(1)) for i, n in enumerate(nodes)
             if (m := re.fullmatch(r"bone_(\d+)", str(n.get("name", "")).split(".")[0]))}
    return {b: (ident.get(parent.get(i)), tuple(float(v) for v in nodes[i].get("translation", (0, 0, 0))))
            for i, b in ident.items()}


def _stock_bones(game):
    """{stock id: {bone id: (parent, translation)}} of every playable character's model file 0 (cached per game)."""
    import charpack
    import gltf_model
    key = str(Path(game).resolve())
    if key not in _GLB_SKELETONS:
        out = {}
        with charpack.sources(game) as srcs:
            for cid in range(sluggie.PLAYABLE):
                try:
                    bs = gltf_model.bones(charpack.stock_file(game, srcs, cid, 0))
                except Exception:
                    continue
                out[cid] = {x["id"]: (x["parent"], tuple(float(v) for v in x["t"])) for x in bs}
        _GLB_SKELETONS[key] = out
    return _GLB_SKELETONS[key]


def glb_base(glb, game):
    """(the stock id a glTF is built on, or None when unclear; [candidate ids]): its scene's "sluggers" base when it
    kept it (our own export; Blender drops it), else the characters with its skeleton's bones and parents, narrowed
    to the ones whose rest pose matches too (within 1%)."""
    import gltf_model
    gl, _ = gltf_model.read_glb(bytes(glb))
    named = ((gl.get("scenes") or [{}])[0].get("extras") or {}).get("sluggers", {}).get("base")
    if named and _donor_id(named) is not None:
        return _donor_id(named), [_donor_id(named)]
    mine = _glb_bones(gl)
    if not mine:
        return None, []
    shape = {b: p for b, (p, _) in mine.items()}
    same = [cid for cid, bs in _stock_bones(game).items() if {b: p for b, (p, _) in bs.items()} == shape]

    def off(cid):
        bs = _stock_bones(game)[cid]
        worst = 0.0
        for b, (_, t) in mine.items():
            ref = bs[b][1]
            scale = max(1e-3, max(abs(v) for v in ref))
            worst = max(worst, max(abs(a - c) for a, c in zip(t, ref)) / scale)
        return worst
    close = [cid for cid in same if off(cid) <= 0.01]
    pick = close if close else same
    return (pick[0] if len(pick) == 1 else None), pick


def _describe_glb(path, game):
    """describe() of a bare .glb: checked (a skinned body) and its base found, without rebuilding it yet."""
    import gltf_model
    out = {"name": _glb_name(path), "files": [path.name], "icons": [], "voice": False, "problems": [],
           "notes": ["a model from Blender: rebuilt onto its base's model"], "donor": None, "donors": []}
    try:
        glb = path.read_bytes()
        objs, _, info = gltf_model.glb_to_mesh(glb)
    except Exception as e:                          # noqa: BLE001 (said in words)
        out["problems"] = [f"{path.name} can't be read as a glTF model ({type(e).__name__}: {e})"]
        return out
    if not any(info.get(n, {}).get("skinned") for n in objs):
        out["problems"] = [f"{path.name} has no skinned body (a mesh rigged to the base's bones): export it from the "
                           f"model.glb this patcher saved, with its armature"]
        return out
    base, cands = glb_base(glb, game)
    out["donor"] = sluggie._name(base) if base is not None else None
    out["donors"] = [sluggie._name(c) for c in cands]
    out["name"] = name_for(_glb_name(path, glb), out["donor"])
    return out


# ---- export: a model folder from a game (a mod's extracted game, e.g. Extra Innings)

def export_model(game, directory, out, name=None, portraits=None, author="", source="", voice=None):
    """Write directory's model file 0 (and file 1 when it differs) of game as a model folder at out, with the select
    portraits of character id `portraits` from that game's icon bank, the 12 clips of the folder `voice` (voice/),
    and model.json."""
    import dtna_toc
    from dol import Dol
    import recolor
    game, out = Path(game), Path(out)
    toc = dtna_toc.toc(Dol(game / "sys/main.dol"))
    with open(game / "files/dt_na.dat", "rb") as f:
        def file(i):
            o, n = toc[directory][i]
            f.seek(o)
            return f.read(n)
        high, low = file(0), file(1)
    if not _block_ok(high):
        raise SluggieError(f"dt_na folder {directory} file 0 isn't a character model")
    out.mkdir(parents=True, exist_ok=True)
    tag = re.sub(r"[^a-z0-9]+", "_", (name or f"dir{directory}").lower()).strip("_")
    (out / f"{tag}.gpl.bin").write_bytes(high)
    written = [f"{tag}.gpl.bin"]
    if low != high and _block_ok(low):
        (out / f"{tag}_low.gpl.bin").write_bytes(low)
        written.append(f"{tag}_low.gpl.bin")
    if portraits is not None:
        g = recolor.Game(str(game))
        for view in ("side", "front"):
            g.portrait(portraits, view).save(out / f"{view}.png")
            written.append(f"{view}.png")
    if voice is not None:
        import charpack
        (out / "voice").mkdir(exist_ok=True)
        for s in charpack.SLOTS:
            (out / "voice" / f"{s}.wav").write_bytes((Path(voice) / f"{s}.wav").read_bytes())
        written.append("voice/ (12 clips)")
    meta = {"name": name or tag, "from": source or f"{game.name}: dt_na folder {directory}"}
    if author:
        meta["author"] = author
    (out / "model.json").write_text(json.dumps(meta, indent=1), encoding="utf8")
    return written + ["model.json"]


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    ap.add_argument("what", choices=["export", "check", "add"])
    ap.add_argument("path")
    ap.add_argument("dir", nargs="?", type=lambda v: int(v, 0))
    ap.add_argument("-o", "--out")
    ap.add_argument("--name")
    ap.add_argument("--portraits", type=lambda v: int(v, 0))
    ap.add_argument("--from", dest="source", default="")
    ap.add_argument("--voice", help="export: a folder with the 12 voice clips (v1.wav ... v14.wav)")
    ap.add_argument("--game")
    ap.add_argument("--donor")
    ap.add_argument("--dest")
    a = ap.parse_args(argv)
    try:
        if a.what == "export":
            print("wrote", ", ".join(export_model(a.path, a.dir, a.out, a.name, a.portraits, source=a.source,
                                                  voice=a.voice)))
            return 0
        import game_source
        game = Path(a.game or game_source.root())
        if a.what == "check":
            print(json.dumps(describe(a.path, game), indent=1))
            return 0
        r = add_model(a.path, game, a.donor, a.dest)
        print(f"added {r['name']} (0x{r['id']:02X}) on {r['template']}: {r['definition']}")
        for w in r["warnings"]:
            print("note:", w)
        return 0
    except SluggieError as e:
        print(e)
        return 1



# ---- a model edited in Blender (a character file's model.glb) -> game blocks on its base

def rebuild_from_glb(glb, base, game, keep=None):
    """{file index: block}, [notes]: the glTF (gltf_model.glb_to_mesh: git-d0's reader, which also takes Blender's
    re-export) written onto the base's own stock blocks with our model writer (build_model.build_lod: the skinned
    body rebuilt, its skin rebuilt from the model's weights, textures re-encoded at the base's slot sizes). Each
    triangle goes in the base's draw group its material names ("tex<k>_ds<state>"); a material Blender added goes in
    the base's largest group. keep: the character's {file index: block} an edit goes on in place (_edit_in_place).
    Where the low-detail block can't hold the edited model, the detailed block is the far-away one too (a note says
    so)."""
    import tempfile
    import build_model
    import charpack
    import gltf_model
    from mss_model import Model
    game = Path(game)
    notes = []
    if keep and 0 in keep:                  # only what changed, on the character's own block (the rest byte-exact)
        try:
            done = _edit_in_place(glb, keep[0], keep.get(1), notes)
        except ValueError as e:
            raise SluggieError(f"the edited model doesn't fit {sluggie._name(base)}'s model: {e}")
        if done is not None:
            return done, notes
    objs, textures, info = gltf_model.glb_to_mesh(glb)
    body = {n: o for n, o in objs.items() if info.get(n, {}).get("skinned")}
    if not body:
        raise SluggieError("its model.glb has no skinned body (the mesh rigged to the base's bones)")
    toc = charpack._toc(game, None)[base + MODEL_DIR_BASE]
    blocks = {}
    tmp = Path(tempfile.mkdtemp(prefix="glb-rebuild-"))
    try:
        with charpack.sources(game) as srcs:
            for fi in sluggie.MODEL_FILES:
                stock = charpack.stock_file(game, srcs, base, fi)
                if stock is None:
                    continue
                m = Model(stock)
                groups = build_model.donor_groups(m, m.submeshes[0])
                biggest = max(groups, key=lambda g: len(groups[g]["tris"]))
                mats = {}
                for o in body.values():
                    for name in o["materials"]:
                        st = re.search(r"ds(\d+)", str(name))
                        st = int(st.group(1)) if st else None
                        mats[name] = f"ds{st if st in groups else biggest}"
                pack = {"dat": str(game / "files/dt_na.dat"), "groups": {"body": biggest, **{f"ds{g}": g for g in groups}},
                        "materials": mats, "tex_roles": {}, "max_influences": 3, "strips": True}
                mesh = tmp / f"{fi}.json"
                mesh.write_text(json.dumps(body), encoding="utf8")
                off, length = toc[fi]
                lod = {"offset": hex(off), "length": length, "mesh": str(mesh)}
                tex = {k: (lambda w, h, img=img: img.convert("RGBA").resize((w, h))) for k, img in textures.items()
                       if k < len(m.textures)}
                try:
                    blocks[fi], _ = build_model.build_lod({}, pack, str(fi), lod, tex)
                    blocks[fi] = _write_rigid(blocks[fi], objs, info, notes if fi == 0 else [])   # crown, shell
                except (ValueError, AssertionError) as e:
                    if fi == 1 and 0 in blocks:     # (keep[1], the old or the base's own, showed it from far away)
                        blocks[1] = blocks[0]
                        notes.append("the far-away model is the detailed one (it doesn't fit the base's low-detail "
                                     "model)")
                    else:
                        raise SluggieError(f"the edited model doesn't fit {sluggie._name(base)}'s model ({e}): give it "
                                           f"fewer triangles, or build it on another base")
    finally:
        import shutil
        shutil.rmtree(tmp, ignore_errors=True)
    if 1 not in blocks and 0 in blocks:
        blocks[1] = blocks[0]
    return blocks, notes


# ---- switching the base (git-92 for Nick: "switch the base character it is on"): re-rig onto another skeleton

def _skeleton(block):
    """({bone id: joint position (numpy xyz)}, the bones the model's skin uses, (foot point, height))."""
    import numpy as np
    import gltf_model
    from mss_model import Model
    joints = {b["id"]: np.array(b["world"])[:3, 3] if np.array(b["world"]).shape == (4, 4) else
              np.array(b["world"])[12:15] for b in gltf_model.bones(block)}
    k = Model(block).skin
    used = ({e["bone"] for e in k.sk1 + k.acc} | {x for e in k.sk2 for x in e["bones"]}) if k else set(joints)
    pts = np.array([joints[b] for b in used if b in joints] or [np.zeros(3)])
    foot = np.array([0.0, pts[:, 1].min(), 0.0])
    return joints, used, (foot, max(1e-6, float(pts[:, 1].max() - pts[:, 1].min())))


def _stock(game, base, index=0):
    import charpack
    with charpack.sources(game) as srcs:
        return charpack.stock_file(game, srcs, base, index)


def retarget(objs, info, src_block, dst_block):
    """The mesh (gltf_model.glb_to_mesh objects) moved from src_block's skeleton to dst_block's: each source bone
    maps to the nearest bone the destination's skin uses (skeletons scaled to the same height and stood on the same
    feet), its weights move there, and each vertex follows its bones' joint offsets. Returns (objects,
    {"mean": mean mapped distance / height, "worst": the worst, "ratio": height ratio})."""
    import numpy as np
    sj, _, (sfoot, sh) = _skeleton(src_block)
    tj, tused, (tfoot, th) = _skeleton(dst_block)
    k = th / sh
    targets = [b for b in tused if b in tj]
    tpts = np.array([tj[b] for b in targets])
    norm = {b: (p - sfoot) * k + tfoot for b, p in sj.items()}
    cache, dists, counts = {}, {}, {}

    def to(b):
        if b not in cache:
            p = norm.get(b)
            if p is None:
                cache[b] = (targets[0], np.zeros(3), 1.0)
            else:
                d = np.linalg.norm(tpts - p, axis=1)
                i = int(d.argmin())
                cache[b] = (targets[i], tpts[i] - p, float(d[i]) / th)
        return cache[b]
    out = {}
    for name, o in objs.items():
        o = dict(o)
        if info.get(name, {}).get("skinned"):
            pos, wts = [], []
            for p, w in zip(o["positions"], o["weights"]):
                p = (np.array(p) - sfoot) * k + tfoot
                moved, nw = np.zeros(3), {}
                tot = sum(w.values()) or 1.0
                for b, v in w.items():
                    c, off, d = to(int(b))
                    moved += off * (v / tot)
                    nw[str(c)] = nw.get(str(c), 0.0) + v
                    dists[int(b)] = d
                    counts[int(b)] = counts.get(int(b), 0) + 1
                pos.append((p + moved).tolist())
                wts.append(nw)
            o["positions"], o["weights"] = pos, wts
        out[name] = o
    n = sum(counts.values()) or 1
    fit = {"mean": sum(dists[b] * counts[b] for b in counts) / n, "worst": max(dists.values(), default=0.0),
           "ratio": th / sh}
    return out, fit


SIMILAR = {"ratio": (0.45, 1.8), "mean": 0.08, "worst": 0.25}    # set from the stock pairs (similar_base): Mario
# with Luigi, Baby Mario; Daisy with Peach, Waluigi similar; Mario with Wario, Bowser, Boo, Yoshi, DK, Petey not


def similar_base(src_base, dst_base, game, src_block=None):
    """"same" (the identical skeleton), "similar" or "different": what the base list's note says (Nick: a note only
    when it's not a similar base)."""
    import model_import
    src_block = src_block if src_block is not None else _stock(game, src_base)
    if dst_base in model_import.donors(src_block, game):
        return "same"
    import gltf_model
    objs, _, info = gltf_model.glb_to_mesh(gltf_model.block_to_glb(src_block))
    _, fit = retarget(objs, info, _stock(game, src_base), _stock(game, dst_base))
    lo, hi = SIMILAR["ratio"]
    ok = lo <= fit["ratio"] <= hi and fit["mean"] <= SIMILAR["mean"] and fit["worst"] <= SIMILAR["worst"]
    return "similar" if ok else "different"


NOT_SIMILAR = "Not a similar body: it may bend oddly."


def _pair_groups(objs, info, dst):
    """Each source draw state (a material's "ds<n>") and texture -> a destination draw group, and source texture ->
    destination texture: by size (the most-used source texture to the destination's biggest group's texture...)."""
    import build_model
    from mss_model import Model
    m = Model(dst)
    groups = build_model.donor_groups(m, m.submeshes[0])
    tex_of_group = {}
    for g, d in groups.items():
        ds = m.submeshes[0].states[d["bind"]] if d["bind"] is not None else None
        tex_of_group[g] = ds.texture[0] if ds is not None else None
    use = {}
    for name, o in objs.items():
        if not info.get(name, {}).get("skinned"):
            continue
        for mat in o["materials"]:
            t = re.search(r"tex(\d+)", str(mat))
            key = int(t.group(1)) if t else None
            use[key] = use.get(key, 0) + 1
    src_tex = sorted(use, key=lambda t: -use[t])
    dst_groups, seen = [], set()
    for g in sorted(groups, key=lambda g: -len(groups[g]["tris"])):
        if tex_of_group[g] not in seen:
            seen.add(tex_of_group[g])
            dst_groups.append(g)
    tex_map, group_of, notes = {}, {}, []
    for i, t in enumerate(src_tex):
        g = dst_groups[min(i, len(dst_groups) - 1)]
        group_of[t] = g
        if i < len(dst_groups) and t is not None and tex_of_group[g] is not None:
            tex_map[t] = tex_of_group[g]
    if len(src_tex) > len(dst_groups):
        notes.append("the new base has fewer picture slots than the model uses: some parts share a picture")
    mats = {}
    for o in objs.values():
        for mat in o["materials"]:
            t = re.search(r"tex(\d+)", str(mat))
            mats[mat] = f"ds{group_of[int(t.group(1)) if t else None]}"
    return mats, tex_map, notes, groups


def rebuild_on(objs, info, textures, base, game, src_block=None):
    """{file index: block}, [notes]: a mesh (moved to base's skeleton already, or its own) written onto base's stock
    blocks, draw groups and texture slots paired by size (_pair_groups). The low-detail block: the same mesh when it
    fits, else the detailed block for both (as Extra Innings ships its Luma)."""
    import tempfile, shutil
    import build_model
    import charpack
    from mss_model import Model
    game = Path(game)
    body = {n: o for n, o in objs.items() if info.get(n, {}).get("skinned")}
    toc = charpack._toc(game, None)[base + MODEL_DIR_BASE]
    blocks, notes = {}, []
    tmp = Path(tempfile.mkdtemp(prefix="base-switch-"))
    try:
        high = _stock(game, base, 0)
        mats, tex_map, more, _ = _pair_groups(body, info, high)
        notes += more
        for fi in sluggie.MODEL_FILES:
            stock = _stock(game, base, fi)
            if stock is None:
                continue
            m = Model(stock)
            groups = build_model.donor_groups(m, m.submeshes[0])
            biggest = max(groups, key=lambda g: len(groups[g]["tris"]))
            lod_mats = {k: (v if int(v[2:]) in groups else f"ds{biggest}") for k, v in mats.items()}
            pack = {"dat": str(game / "files/dt_na.dat"), "materials": lod_mats, "tex_roles": {},
                    "groups": {"body": biggest, **{f"ds{g}": g for g in groups}}, "max_influences": 3,
                    "strips": True}
            mesh = tmp / f"{fi}.json"
            mesh.write_text(json.dumps(body), encoding="utf8")
            off, length = toc[fi]
            tex = {dk: (lambda w, h, img=textures[sk]: img.convert("RGBA").resize((w, h)))
                   for sk, dk in tex_map.items() if sk in textures and dk < len(m.textures)}
            try:
                blocks[fi], _ = build_model.build_lod({}, pack, str(fi), {"offset": hex(off), "length": length,
                                                                            "mesh": str(mesh)}, tex)
                blocks[fi] = _write_rigid(blocks[fi], objs, info, notes if fi == 0 else [])   # (same skeleton)
            except (ValueError, AssertionError) as e:
                if fi == 1 and 0 in blocks:
                    blocks[1] = blocks[0]
                    notes.append("the far-away model is the detailed one (it doesn't fit the base's low-detail "
                                 "model)")
                else:
                    mt = re.search(r"needs (0x[0-9a-f]+) bytes, region has (0x[0-9a-f]+)", str(e))
                    more = (f" (it needs about {round(100 * (1 - int(mt.group(2), 16) / int(mt.group(1), 16)))}% "
                            f"fewer triangles)") if mt else f" ({e})"
                    raise SluggieError(f"the model is too detailed for {sluggie._name(base)}'s{more}: pick a bigger "
                                       f"base, or simplify it in Blender")
    finally:
        shutil.rmtree(tmp, ignore_errors=True)
    blocks.setdefault(1, blocks[0])
    return blocks, notes


def switch_base(block, from_base, to_base, game):
    """A character's model block (on from_base) moved to to_base: {file index: block}, [notes], the note for the base
    list ("" / NOT_SIMILAR). SluggieError in plain words."""
    import gltf_model
    objs, textures, info = gltf_model.glb_to_mesh(gltf_model.block_to_glb(block))
    kind = similar_base(from_base, to_base, game, src_block=block)
    if kind != "same":
        objs = _fold_rigid(objs, info, block)      # one-bone parts into the body: the new base has no place for them
        objs, _ = retarget(objs, info, _stock(game, from_base), _stock(game, to_base))
    blocks, notes = rebuild_on(objs, info, textures, to_base, game)
    return blocks, notes, "" if kind != "different" else NOT_SIMILAR


def switch_character(definition, to_base, game):
    """An added character (its definition in the import folder) moved onto another base: its model rebuilt there,
    the definition's template and model blocks replaced. Returns {"template", "notes", "note"}."""
    import charpack, delta
    from sluggers_data import char_id
    definition = Path(definition)
    d = json.loads(definition.read_text(encoding="utf8"))
    folder = definition.parent.parent / definition.stem
    game = Path(game)
    with charpack.sources(game) as srcs:
        block = charpack.rebuild((folder / d["model_blocks"]["0"]).read_bytes(), srcs, "its model")
    to_id = _donor_id(to_base)
    if to_id is None:
        raise SluggieError(f"{to_base} isn't a stock character")
    blocks, notes, note = switch_base(block, char_id(d["template"]), to_id, game)
    with charpack.sources(game) as srcs:
        for i, b in blocks.items():
            try:
                charpack.gate_lod(b, game, srcs, to_id, i)
            except charpack.PackError as err:
                raise SluggieError(f"on {sluggie._name(to_id)}, the {err}")
    idx = charpack.index(game)
    for i, b in blocks.items():
        (folder / "models" / f"{i}.slgd").write_bytes(delta.make(b, idx)[0])
    d["model_blocks"] = {str(i): f"models/{i}.slgd" for i in sorted(blocks)}
    d["template"] = sluggie._name(to_id)
    definition.write_text(json.dumps(d, indent=1, ensure_ascii=False), encoding="utf8")
    return {"template": d["template"], "notes": notes, "note": note}


# ---- one-bone parts (a crown, a shell, a mask; git-92: "an edited Rosalina keeps her crown")

def _write_rigid(block, objs, info, notes):
    """The block with every rigid (one-bone) object of the mesh written back into the base's submesh of its name
    (Blender keeps mesh names; ".001" suffixes dropped), else its submesh index: build_model.build_rigid. A part the
    base has no submesh for is left out, and a note says so. ValueError when a part doesn't fit its region."""
    from collections import defaultdict
    import build_model
    from mss_model import Model, quant16
    blk = bytearray(block)
    m = Model(bytes(blk))
    by_name = {sm.name.lower(): sm for sm in m.submeshes if not sm.skinned}
    for name, o in objs.items():
        if info.get(name, {}).get("skinned") or not o.get("triangles"):
            continue
        sm = by_name.get(re.sub(r"\.\d+$", "", name).lower())
        k = info.get(name, {}).get("submesh")
        if sm is None and isinstance(k, int) and 0 <= k < len(m.submeshes) and not m.submeshes[k].skinned:
            sm = m.submeshes[k]
        if sm is None:
            notes.append(f"its part {name!r} has no place on this base: left out")
            continue
        groups = build_model.donor_groups(m, sm)
        if not groups:
            notes.append(f"its part {name!r}: the base's {sm.name} draws nothing: left out")
            continue
        biggest = max(groups, key=lambda g: len(groups[g]["tris"]))
        uvq = sm.uvs[0].quant if sm.uvs else 0x3E
        uv_index, uv_list, tris_by = {}, [], defaultdict(list)
        for t, uvs, mat in zip(o["triangles"], o["uvs"], o["materials"]):
            st = re.search(r"ds(\d+)", str(mat))
            g = int(st.group(1)) if st and int(st.group(1)) in groups else biggest
            corners = []
            for i, uv in zip(t, uvs):
                key = quant16(uv, uvq)
                if key not in uv_index:
                    uv_index[key] = len(uv_list)
                    uv_list.append(key)
                corners.append((i, uv_index[key]))
            tris_by[g].append((corners[0], corners[2], corners[1]))       # Blender CCW -> game CW
        try:
            lists = {g: build_model.prim_list(tris, groups[g]["fmt"], groups[g]["color"], use_strips=True)
                     for g, tris in tris_by.items()}
        except ValueError:
            raise ValueError(f"its part {name!r} has too many points for the base's {sm.name}")
        region, start = build_model.build_rigid(m, sm, o["positions"], o["normals"], b"".join(uv_list), lists)
        blk[start:start + len(region)] = region
    return bytes(blk)


def _fold_rigid(objs, info, src_block):
    """The mesh with its rigid (one-bone) parts folded into the skinned body: positions and normals through their
    bone's bind matrix into model space, each point weighted wholly to that bone (a base switch: the new base has no
    submesh for them)."""
    import numpy as np
    import gltf_model
    world = {b["id"]: np.array(b["world"]) for b in gltf_model.bones(src_block)}
    body_name = next((n for n in objs if info.get(n, {}).get("skinned")), None)
    if body_name is None:
        return objs
    body = {k: list(v) for k, v in objs[body_name].items()}
    for name, o in objs.items():
        bone = info.get(name, {}).get("bone")
        if name == body_name or not o.get("triangles") or bone not in world:
            continue
        w = world[bone]
        base = len(body["positions"])
        for p, n in zip(o["positions"], o["normals"]):
            body["positions"].append((w @ np.array(list(p)[:3] + [1.0]))[:3].tolist())
            nn = w[:3, :3] @ np.array(list(n)[:3])
            body["normals"].append((nn / (np.linalg.norm(nn) or 1.0)).tolist())
            body["weights"].append({str(bone): 1.0})
        body["triangles"] += [[i + base for i in t] for t in o["triangles"]]
        body["uvs"] += list(o["uvs"])
        body["materials"] += list(o["materials"])
    out = {n: o for n, o in objs.items() if info.get(n, {}).get("skinned") and n != body_name}
    out[body_name] = body
    return out


def _signature(o):
    """A mesh object's look: its triangles (positions and UVs, to 1/1000) and, per position, its weights (to 1/100)."""
    import numpy as np
    P = np.round(np.array(o["positions"] or [[0, 0, 0]], dtype=float), 3)
    tris = frozenset((tuple(sorted(tuple(P[i]) for i in t)), tuple(sorted(tuple(np.round(u, 3)) for u in uv)))
                     for t, uv in zip(o["triangles"], o["uvs"]))
    w = frozenset((tuple(P[i]), tuple(sorted((str(b), round(v, 2)) for b, v in ws.items())))
                  for i, ws in enumerate(o.get("weights") or []) if ws)
    return tris, w


def changed_parts(glb, block):
    """What an edited glb changes against the block it was exported from: ({object names whose shape, UVs or
    weights differ, or that are new}, {texture index: edited picture}), and the glb's (objects, textures, info)."""
    import numpy as np
    import gltf_model
    objs, textures, info = gltf_model.glb_to_mesh(glb)
    o2, t2, i2 = gltf_model.glb_to_mesh(gltf_model.block_to_glb(block))
    def key(n):
        return re.sub(r"\.\d+$", "", n).lower()
    was = {key(n): o for n, o in o2.items()}
    changed = {n for n, o in objs.items() if key(n) not in was or not _same(o, was[key(n)])}
    tex = {k: img for k, img in textures.items()
           if k not in t2 or img.size != t2[k].size or not np.array_equal(np.asarray(img.convert("RGBA")),
                                                                       np.asarray(t2[k].convert("RGBA")))}
    return changed, tex, (objs, textures, info)


def _edit_in_place(glb, block, low, notes):
    """The same base, and the body unchanged: the character's own block with only the changed one-bone parts and
    pictures rewritten (everything else byte for byte). None when the body changed (a full rebuild is needed)."""
    import build_model
    from mss_model import Model
    changed, tex, (objs, textures, info) = changed_parts(glb, block)
    if any(info.get(n, {}).get("skinned") for n in changed):
        return None
    blk = _write_rigid(block, {n: objs[n] for n in changed}, info, notes)
    m = Model(blk)
    blk = bytearray(blk)
    for k, img in tex.items():
        if k < len(m.textures):
            t = m.textures[k]
            blk[t.image:t.image + t.payload_size()] = build_model.encode_texture(
                img.convert("RGBA").resize((t.width, t.height)), t.format, t.payload_size())
    if not changed and not tex:
        notes.append("its model.glb has no changes the patcher can see: the model is as it was exported")
        return {0: bytes(blk), 1: low if low is not None else bytes(blk)}
    # the low-detail block has its own parts and pictures: left as it was, it showed the old look (on a bare .glb,
    # the base's) from far away (NSL's video). The edited block stands in for it.
    return {0: bytes(blk), 1: bytes(blk)}


def _same(new, old, tol=1e-3):
    """Whether a mesh object is unchanged within tolerance (Blender's re-export moves floats by ~1e-6): every position
    has one within tol in the other, the triangles are the same (by matched positions), their UVs within tol and the
    weights within 0.02."""
    import numpy as np
    pn, po = np.array(new["positions"] or [], float), np.array(old["positions"] or [], float)
    if len(new["triangles"]) != len(old["triangles"]) or not len(pn) or not len(po):
        return len(new["triangles"]) == len(old["triangles"]) == 0
    d = np.sqrt(((pn[:, None, :3] - po[None, :, :3]) ** 2).sum(-1)) if len(pn) * len(po) <= 25_000_000 else None
    if d is None:
        return False
    near = d.argmin(1)
    if d[np.arange(len(pn)), near].max() > tol:
        return False
    back = d.min(0)
    if back.max() > tol:
        return False

    def tri_uvs(o, idx):
        out = {}
        for t, uv in zip(o["triangles"], o["uvs"]):
            key = tuple(sorted(int(idx[i]) for i in t))
            out.setdefault(key, []).append(sorted(tuple(u) for u in uv))
        return out
    a = tri_uvs(new, near)
    b = tri_uvs(old, np.arange(len(po)))
    if a.keys() != b.keys():
        return False
    for k in a:
        for ua, ub in zip(sorted(a[k]), sorted(b[k])):
            if np.abs(np.array(ua) - np.array(ub)).max() > tol:
                return False
    wn, wo = new.get("weights") or [], old.get("weights") or []
    for i, w in enumerate(wn):
        j = int(near[i])
        if j < len(wo):
            keys = set(map(str, w)) | set(map(str, wo[j]))
            if any(abs(float(w.get(k, w.get(int(k), 0) if k.isdigit() else 0)) -
                       float(wo[j].get(k, wo[j].get(int(k), 0) if k.isdigit() else 0))) > 0.02 for k in keys):
                return False
    return True


if __name__ == "__main__":
    sys.exit(main())
