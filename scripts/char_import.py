"""Import character, from one file or a whole folder (git-0a for Nick: "it would be sick if the import character file
could import everything like the portraits and voices ... if we could just import the character folder and it imports
everything"). Both patchers' Import character button comes here (character_window.import_any / add_sluggie /
import_model); the routes themselves stay sluggie.add_character and model_import.add_model.

  python scripts/char_import.py <file or folder> [--game extracted/clean] [--dest dir] [--donor NAME] [--scan]

What a folder is scanned for (find()):
  the model    one of: a .slgmodel (our character file); a .sluggie (+ its low-detail sibling and PNGs); a model file
               (.gpl.bin / .bin: a model block, with model.json when model_import.export_model wrote the folder);
               a .glb (a model edited in Blender); a texture pack (Dolphin's tex1_*.png). model.json beside model
               files makes them the model; otherwise that order. Nothing at the top: the one subfolder that has one.
  portraits    side.png / front.png (any picture whose name has "side" / "front"), else one picture named portrait,
               icon, select or face for both; any size (fitted to 48x51 as every import is).
  voice        voice/*.wav (or voices/, sounds/, audio/, or the folder itself): a file per clip slot, named by the slot
               as our exports write them (v1.wav ... v14.wav; "luma_v3.wav" works too). Any WAV (converted to mono
               22,050 Hz 16-bit, cut at 1.4 s); slots it has no clip for play the base's sounds.
  the name     the file's own (a .slgmodel's, the name our model.glb export embeds), character.json / model.json's,
               else the file's or the folder's name cleaned up ("luma_7" -> "Luma"); never the base's own name or a
               generic one ("Model (25)", "New folder"): then "New <base>" (a Sluggies model: "<base> (custom)").
A single file takes what's beside it the same way (luma.gpl.bin with side.png, front.png and voice/ next to it); what a
.slgmodel carries itself comes first. Nothing asks for a name: it stays editable in the character window.
"""
import io, json, re, sys, tempfile
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
sys.path.insert(0, str(HERE / "patcher"))
import sluggie  # noqa: E402
from sluggie import SluggieError  # noqa: E402

PICTURES = (".png", ".jpg", ".jpeg", ".bmp", ".gif", ".webp")
PORTRAIT_WORDS = ("portrait", "icon", "select", "face")
VOICE_DIRS = ("voice", "voices", "sounds", "sound", "audio")
NOT_MODEL = {".png", ".json", ".txt", ".jpg", ".jpeg", ".bmp", ".gif", ".webp", ".md", ".zip", ".wav", ".sluggie",
             ".slgmodel", ".glb", ".py", ".bat", ".exe", ".dll", ".ini", ".pdf", ".7z", ".rar"}
# a folder or file name that says nothing about who it is
GENERIC = re.compile(r"(new folder|downloads?|desktop|documents|temp|tmp|files?|characters?|models?|exports?|output|"
                     r"imports?|untitled|scene|mesh|object|armature|new character|imported model|voice|voices|"
                     r"sluggies|blender|edit|edited|character files?|mods?)( ?\(\d+\)| ?[._-]?\d+)?", re.I)
TRAILING = re.compile(r"^(\d+|edit|edited|export|exported|final|copy|new|backup|old|low|high|hi|l|v\d+|gpl|bin|"
                      r"model|slgmodel|sluggie|glb)$", re.I)


def slots():
    import charpack
    return charpack.SLOTS


# ---- names

def clean_name(text):
    """A file or folder name as a character's name: "luma_7" -> "Luma", "272147520_tiny_kong.gpl" -> "Tiny Kong",
    "Summer Kong" as it is. "" when nothing is left."""
    words = [w for w in re.split(r"[_\-\s.]+", str(text or "")) if w]
    while words and re.fullmatch(r"\d+", words[0]):            # Sluggies' "<offset>_name"
        words.pop(0)
    while words and TRAILING.fullmatch(words[-1]):
        words.pop()
    words = [w for w in words if not re.fullmatch(r"\(?\d+\)?", w)] if len(words) > 1 else words
    name = " ".join(words)
    if name and name == name.lower():
        name = name.title()
    return name


def usable(name, base):
    """A found name worth using: not generic, not the base's own name, fits the game's name box."""
    import charpack
    n = str(name or "").strip()
    if not n or GENERIC.fullmatch(n) or (base and n.lower() == str(base).lower()):
        return False
    try:
        return charpack.name_fits(n)
    except Exception:                               # noqa: BLE001 (no font data: any name)
        return len(n) <= 24


def pick_name(names, base, fallback):
    """The first usable of names ([(name, where from)]) -> (name, where from); else (fallback, "")."""
    for n, where in names:
        if usable(n, base):
            return n.strip(), where
    return fallback, ""


def _json_name(folder):
    for f in ("character.json", "model.json"):
        p = Path(folder) / f
        if p.is_file():
            try:
                n = str(json.loads(p.read_text(encoding="utf8")).get("name") or "").strip()
            except (OSError, ValueError, AttributeError):
                continue
            if n:
                return n, f
    return None


def _embedded_name(path, kind):
    """The name the file carries itself: a .slgmodel's character.json, our model.glb export's scene extras."""
    try:
        if kind == "slgmodel":
            import zipfile
            with zipfile.ZipFile(path) as z:
                return str(json.loads(z.read("character.json").decode("utf8")).get("name") or "").strip()
        if kind == "glb":
            import gltf_model
            gl, _ = gltf_model.read_glb(Path(path).read_bytes())
            return str(((gl.get("scenes") or [{}])[0].get("extras") or {}).get("sluggers", {}).get("name")
                       or "").strip()
    except Exception:                               # noqa: BLE001 (the route says what's wrong with the file)
        return ""
    return ""


# ---- what a folder has

def model_files(folder):
    """[(path, bytes)] of the model blocks directly in folder (model_import's model files: any file that parses as a
    character model, pictures / JSON / our other kinds left out)."""
    import model_import
    out = []
    for p in sorted(Path(folder).iterdir()) if Path(folder).is_dir() else []:
        if not p.is_file() or p.suffix.lower() in NOT_MODEL or p.name.lower().endswith(".slgchar"):
            continue
        try:
            if p.stat().st_size > model_import.MAX_BLOCK:
                continue
            data = p.read_bytes()
        except OSError:
            continue
        if model_import._block_ok(data):
            out.append((p, data))
    return out


def portraits(folder):
    """{"side" / "front": picture path} in folder (and its portraits/ or icons/): a name with side / front, else one
    picture named portrait / icon / select / face for both. Dolphin texture dumps and previews aren't portraits."""
    folder = Path(folder)
    pics = []
    for d in (folder, folder / "portraits", folder / "icons"):
        if d.is_dir():
            pics += [p for p in sorted(d.iterdir()) if p.is_file() and p.suffix.lower() in PICTURES
                     and not sluggie.DUMP_NAME.match(p.name)]
    out = {}
    for view in ("side", "front"):
        p = next((q for q in pics if view in q.stem.lower()), None)
        if p is not None:
            out[view] = p
    if len(out) < 2:
        alt = [q for q in pics if any(w in q.stem.lower() for w in PORTRAIT_WORDS) and q not in out.values()]
        if len(alt) == 1:
            for view in ("side", "front"):
                out.setdefault(view, alt[0])
    return out


def slot_of(stem):
    """The voice slot a WAV's name says ("v3", "luma_v3", "V3 ") or None."""
    m = re.search(r"(?:^|[^a-z0-9])(v\d+)$", stem.strip().lower())
    return m.group(1) if m and m.group(1) in slots() else None


def voices(folder):
    """({slot: wav path}, [names that aren't a clip slot]) of folder's voice/ (or voices/, sounds/, audio/), else of
    the folder itself."""
    folder = Path(folder)
    for d in [folder / n for n in VOICE_DIRS] + [folder]:
        if not d.is_dir():
            continue
        wavs = [p for p in sorted(d.iterdir()) if p.is_file() and p.suffix.lower() == ".wav"]
        if not wavs:
            continue
        got, other = {}, []
        for p in wavs:
            s = slot_of(p.stem)
            if s and s not in got:
                got[s] = p
            else:
                other.append(p.name)
        return got, other
    return {}, []


def clip_bytes(path):
    """(the clip as charpack takes it, note or None): a WAV of any kind converted (voice_clips.convert)."""
    import charpack
    data = Path(path).read_bytes()
    try:
        charpack.check_clip(data, "clip")
        return data, None
    except charpack.PackError:
        pass
    import voice_clips
    with tempfile.TemporaryDirectory() as t:
        out = Path(t) / "clip.wav"
        r = voice_clips.convert(path, out)
        return out.read_bytes(), (f"{Path(path).name} was cut to {voice_clips.MAX_SECONDS} s" if r["cut"] else None)


def _model_in(folder):
    """(kind, path, [others not used]) of the character model directly in folder, or None."""
    folder = Path(folder)
    files = [p for p in sorted(folder.iterdir()) if p.is_file()] if folder.is_dir() else []
    of = lambda ext: [p for p in files if p.name.lower().endswith(ext)]  # noqa: E731
    slg, slu, glb = of(".slgmodel"), of(".sluggie"), of(".glb")
    blocks = model_files(folder)
    cands = []
    if blocks and (folder / "model.json").is_file():
        cands.append(("model", folder, [p for p, _ in blocks]))
    if slg:
        cands.append(("slgmodel", slg, slg))
    if slu:
        cands.append(("sluggie", slu, slu))
    if blocks:
        cands.append(("model", folder, [p for p, _ in blocks]))
    if glb:
        keep = [p for p in glb if not re.search(r"backup|old|copy", p.stem, re.I)] or glb
        cands.append(("glb", keep, glb))
    if sluggie.is_texture_pack(folder):
        cands.append(("texture", folder, [p for p in files if sluggie.DUMP_NAME.match(p.name)]))
    if not cands:
        return None
    kind, pick, _ = cands[0]
    if kind in ("slgmodel", "glb") and len(pick) > 1:
        named = [p for p in pick if p.stem.lower() in ("model", "character")]
        if len(named) != 1:
            raise SluggieError(f"{folder.name} has {len(pick)} {pick[0].suffix} files ("
                               f"{', '.join(p.name for p in pick)}): import one of them")
        pick = named
    if kind == "sluggie":
        pick = [sluggie.siblings(pick[0])[0]]       # the model, not its low-detail copy (added with it)
        groups = {sluggie.siblings(p)[0] for p in slu}
        if len(groups) > 1:
            raise SluggieError(f"{folder.name} has Sluggies files of {len(groups)} different models: import one")
    used = {p.resolve() for k, _, ps in cands[:1] for p in ps}
    others = [p.name for _, _, ps in cands[1:] for p in ps if p.resolve() not in used]
    path = pick[0] if isinstance(pick, list) else pick
    if kind == "model":                             # the model file itself (its sha1: replace-or-add)
        path = cands[0][2][0] if len(cands[0][2]) == 1 else folder
    return kind, path, list(dict.fromkeys(others))


def find(path):
    """What an import of path (a file or a folder) takes: {"kind": "slgmodel" / "sluggie" / "texture" / "model" /
    "glb", "path": what the route reads, "folder", "portraits": {view: path}, "voice": {slot: path}, "not_voice":
    [wav names], "names": [(name, where from)], "unused": [other model files left], "picked": "file" / "folder"}.
    SluggieError in plain words."""
    path = Path(path)
    if path.is_dir():
        folder, got = path, _model_in(path)
        if got is None:                             # a character one folder down (a zip unpacked into a folder)
            subs = [d for d in sorted(path.iterdir()) if d.is_dir() and d.name.lower() not in VOICE_DIRS
                    and d.name.lower() not in ("portraits", "icons")]
            found = [(d, g) for d in subs for g in [_safe_model_in(d)] if g]
            if len(found) > 1:
                raise SluggieError(f"{path.name} has {len(found)} characters in it ("
                                   f"{', '.join(d.name for d, _ in found)}): import one of its folders")
            if not found:
                raise SluggieError(f"{path.name} has no character in it: no .slgmodel, .sluggie, .glb, model file "
                                   f"(.gpl.bin) or texture pack")
            folder, got = found[0]
        kind, model, unused = got
        picked = "folder"
    else:
        if not path.is_file():
            raise SluggieError(f"{path.name} isn't there")
        folder, picked, unused = path.parent, "file", []
        suf = path.suffix.lower()
        kind = ("slgmodel" if suf == ".slgmodel" else "sluggie" if suf == ".sluggie" else "glb" if suf == ".glb"
                else "texture" if suf == ".png" else "pack" if suf == ".slgchar" else "model")
        model = path
    pics = portraits(folder)
    clips, other = voices(folder)
    if picked == "folder" and path != folder:       # the top folder's own pictures / clips fill what's missing
        for v, p in portraits(path).items():
            pics.setdefault(v, p)
        if not clips:
            clips, other = voices(path)
    names = []
    if kind in ("slgmodel", "glb"):
        n = _embedded_name(model, kind)
        if n:
            names.append((n, "its file"))
    for d in dict.fromkeys([folder, path if path.is_dir() else folder]):
        j = _json_name(d)
        if j:
            names.append(j)
    folders = [(clean_name(d.name), "folder name") for d in dict.fromkeys([folder, path if path.is_dir() else folder])]
    if Path(model).is_file() and kind not in ("texture",):
        stem = Path(model).name
        for ext in (".slgmodel", ".sluggie", ".glb", ".bin", ".gpl"):
            stem = re.sub(re.escape(ext) + "$", "", stem, flags=re.I)
        file = [(clean_name(stem), "file name")]
        names += folders + file if picked == "folder" else file + folders   # what was picked names it first
    else:
        names += folders
    return {"kind": kind, "path": Path(model), "folder": folder, "portraits": pics, "voice": clips,
            "not_voice": other, "names": names, "unused": unused, "picked": picked}


def _safe_model_in(d):
    try:
        return _model_in(d)
    except SluggieError:
        return None


def _load_extras(f):
    """({view: PIL image}, {slot: clip bytes}, [notes]) of find()'s portraits and voice."""
    from PIL import Image
    icons, clips, notes = {}, {}, []
    for view, p in f["portraits"].items():
        try:
            icons[view] = Image.open(p).convert("RGBA")
        except Exception:                           # noqa: BLE001
            notes.append(f"{p.name} can't be read as a picture: left out")
    for s, p in f["voice"].items():
        try:
            clips[s], note = clip_bytes(p)
            if note:
                notes.append(note)
        except Exception as e:                      # noqa: BLE001 (a bad clip leaves its slot to the base)
            notes.append(f"{p.name} left out ({e})")
    return icons, clips, notes


# ---- the import

def describe(path, game):
    """{"kind", "name", "donor" (a stock name or None: ask), "donors", "problems", "files", "notes", "find"} for the
    window, before adding."""
    import model_import
    game = Path(game)
    try:
        f = find(path)
    except SluggieError as e:
        return {"problems": [str(e)], "donor": None, "donors": [], "files": [], "notes": [], "name": None}
    if f["kind"] in ("sluggie", "texture"):
        r = sluggie.describe(f["path"], game)
        base = r.get("template")
        out = {"donor": base, "donors": [base] if base else [], "files": r.get("files", []),
               "problems": r["problems"], "notes": r.get("notes", []), "changes": r.get("changes", [])}
        fallback = f"{base} (custom)"
    elif f["kind"] == "pack":
        return {"problems": [], "donor": None, "donors": [], "files": [f["path"].name], "notes": [], "name": None,
                "find": f}
    else:
        r = model_import.describe(f["path"], game)
        base = r.get("donor")
        out = {k: r.get(k) for k in ("donor", "donors", "files", "problems", "notes")}
        fallback = None
    out["find"] = f
    out["kind"] = f["kind"]
    out["name"] = name_of(f, base, fallback)[0] if base else None
    out["icons"] = sorted(set(r.get("icons") or []) | set(f["portraits"]))
    out["voice"] = bool(f["voice"]) or bool(r.get("voice"))
    return out


def name_of(f, base, fallback=None):
    """(name, where from) for find()'s f on base (a stock name)."""
    return pick_name(f["names"], base, fallback or f"New {base}")


def add(path, game, donor=None, dest=None, taken_ids=(), taken_names=(), name=None, cid=None):
    """Import path (a file or a folder): the model by its route, with every portrait and voice clip found, named
    without asking (name= overrides: a Replace keeps the old one). Returns the route's result plus "summary" (plain
    words), "portraits" ([views]), "voice" ([own slots]), "name_from", "kind"."""
    import charpack, model_import
    game = Path(game)
    f = find(path)
    icons, clips, notes = _load_extras(f)
    if f["kind"] == "pack":
        raise SluggieError("a character pack (.slgchar) imports on its own")
    if f["kind"] in ("sluggie", "texture"):
        base = sluggie._name(sluggie.read(f["path"]).template) if f["kind"] == "sluggie" else \
            sluggie._name(sluggie.texture_pack(f["path"], game)["template"])
        chosen, where = (name, "") if name else name_of(f, base, f"{base} (custom)")
        r = sluggie.add_character(f["path"], game, dest=dest, taken_ids=taken_ids, taken_names=taken_names,
                                  name=chosen, cid=cid, icons=icons or None, voice=clips or None)
        own_icons, own_voice = sorted(icons), sorted(clips, key=slots().index)
        files = [f["path"].name] if f["kind"] == "sluggie" else [f"{f['folder'].name}'s texture pictures"]
    else:
        d = describe(f["path"], game) if donor is None else None
        donor = donor if donor is not None else (d or {}).get("donor")
        if donor is None:
            raise SluggieError("pick the stock character it's built on (its skeleton, animations and moves)")
        base = sluggie._name(model_import._donor_id(donor))
        chosen, where = (name, "") if name else name_of(f, base)
        r = model_import.add_model(f["path"], game, donor, dest=dest, taken_ids=taken_ids, taken_names=taken_names,
                                   name=chosen, cid=cid, icons=icons, voice=clips)
        own_icons, own_voice = r.get("own_icons", sorted(icons)), r.get("own_voice", sorted(clips))
        files = r.get("files") or [f["path"].name]
    r["kind"], r["portraits"], r["voice"], r["name_from"] = f["kind"], own_icons, own_voice, where
    r["summary"] = summary(r["name"], files, r["template"], own_icons, own_voice,
                           notes + [f"not used: {', '.join(f['unused'])}"] * bool(f["unused"]))
    return r


def summary(name, files, base, icons, voice, notes=()):
    """"Imported Luma: model (from luma.gpl.bin, base Boo), side and front portraits, 9 of 12 voice clips (the rest
    use Boo's).\""""
    n = len(slots())
    pics = ("side and front portraits" if len(icons) >= 2 else
            f"{icons[0]} portrait ({base}'s {'front' if icons[0] == 'side' else 'side'})" if icons else
            f"no portraits ({base}'s)")
    clips = (f"all {n} voice clips" if len(voice) >= n else
             f"{len(voice)} of {n} voice clips (the rest use {base}'s)" if voice else f"no voice clips ({base}'s voice)")
    text = f"Imported {name}: model (from {', '.join(files)}, base {base}), {pics}, {clips}."
    if voice and len(voice) < n:
        text += f" Its own: {' '.join(voice)}."
    return text + "".join(f" {x[:1].upper()}{x[1:]}." for x in notes)


def main(argv=None):
    import argparse
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    ap.add_argument("path")
    ap.add_argument("--game")
    ap.add_argument("--dest")
    ap.add_argument("--donor")
    ap.add_argument("--scan", action="store_true", help="only say what it would take")
    a = ap.parse_args(argv)
    try:
        if a.scan:
            f = find(a.path)
            print(json.dumps({k: (str(v) if isinstance(v, Path) else v) for k, v in f.items()}, indent=1,
                             default=str))
            return 0
        import game_source
        r = add(a.path, Path(a.game or game_source.root()), donor=a.donor, dest=a.dest)
        print(r["summary"])
        print(f"  definition: {r['definition']}")
        return 0
    except SluggieError as e:
        print(e)
        return 1


if __name__ == "__main__":
    sys.exit(main())
