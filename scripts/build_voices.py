"""Write the custom characters' voice sets (scripts/voice_sets.py) into Extra Innings' sound archive.

  python scripts/build_voices.py        # -> models/work/sounds/MY2.brsar, models/work/sounds/voice_tables.json
                                        #    and the clean base's models/work/sounds/clean/{MY2.brsar, voice_tables.json}
  python scripts/build_voices.py --base=ei|clean     only that one
  python scripts/build_voices.py --game=<clean RMBE01> --work=<work folder>  the player's game (the patcher):
                                        #    <work>/sounds/clean/{MY2.brsar, voice_tables.json} (build_for_game)

Every run writes both archives: the Extra Innings one (the build base today) and one from the clean game's archive
for charbuild --base=clean (docs/clean-base.md step 5), whose sound ids differ (no Extra Innings sounds before ours).
charbuild reads the clean ids from the voice_tables.json next to that archive, so the two always match.

Like Extra Innings' Rosalina / Luma / Larry: each character's gameplay clips (11) go into its template
family's voice file, which the game loads whenever that family plays, and its character-select call (v13)
goes into the shared select-voice file (file 160). Sounds are named zz<name>_v<N>.

voice_tables.json maps each character to its 12 sound INFO ids in the order of the voice-routing table
(Jbiscuit's sound guide: slots 0..11 = v1 v3 v4 v5 v6 v7 v8 v10 v11 v12 v13 v14), i.e. the 0x30-byte table a
character's exact-id hook selects (Extra Innings' Larry table is at 0x80660980). Routing the new ids to
their tables is charbuild's job (git-ea): the archive alone changes nothing in game.

After the voices it appends the stream sounds in STREAMS (Pauline's chance jingle, zzpauline_chance: a STRM sound
like jin_chance_ma whose external file is stream/zzpauline_chance.brstm, made by make_pauline_jingle.py), so they
never shift a voice id. The jingle's id goes to voice_tables.json top-level "pauline_chance" (an int), which
charbuild and pauline_chance.sound_id() read from the committed copy docs/voice-tables.json. The file entry records the .brstm's size, so rebuild the archive whenever the jingle is remade.
"""
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
from brsar import Brsar  # noqa: E402
from brsar_write import add_sounds, fill_cache  # noqa: E402
import game_source  # noqa: E402

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "models/work/sounds"
def bases():
    """Per base: (its voice archive, the output folder). "clean" is the player's game (game_source.root())."""
    return {"ei": (ROOT / "extracted/extra-innings/files/sound_NA/MY2.brsar", OUT),
            "clean": (game_source.root() / "files/sound_NA/MY2.brsar", OUT / "clean")}
SETS = OUT / "sets"
ENCODED = OUT / "encoded"   # our clips' encodings (brsar_write.encode_clip), our audio only: the patcher ships it
SLOTS = ["v1", "v3", "v4", "v5", "v6", "v7", "v8", "v10", "v11", "v12", "v13", "v14"]
SELECT_FILE = 160
FAMILY_SOUND = {  # template -> a stock sound in its family's gameplay voice file
    "Daisy": "daisy_v1", "Bowser": "cuppa_v1", "Bowser Jr": "cuppa_jr_v1", "King Boo": "k_teresa_v1",
    "Shy Guy": "heyho_v1", "Petey": "b_pakkun_v1", "Boo": "teresa_v1", "Wario": "wario_v1",
}
FAMILY_IDS = {"Shy Guy": (0x10, 0x2C, 0x2D, 0x2E, 0x2F),   # family keys that aren't one stock name: Red Shy Guy
              "Petey": (0x26,)}                            # and the colours ([I] they share heyho), Petey Piranha
# Rosalina (0x81, template Daisy) and the four Lumas (0x84 Luma, 0x71-0x73 Blue/Green/Red, template Boo) are normal
# new characters (docs/stock-slot-migration.md): their clips go into Daisy's and Boo's family files, no longer
# Mario's file 14 where Extra Innings' stock-slot Rosalina / Luma (voice family 0) kept theirs.
CHARACTERS = {  # voice set -> template (the donor each model is built on)
    "pauline": "Daisy", "boomboom": "Bowser", "dry-bowser": "Bowser", "dino-piranha": "Bowser",
    "bouldergeist": "King Boo", "gearmo": "Shy Guy", "honey-queen": "Petey", "lubba": "Boo", "penguru": "Wario",
    "pompom": "Bowser Jr", "iggy": "Bowser Jr", "lemmy": "Bowser Jr", "ludwig": "Bowser Jr",
    "king-bobomb": "Wario",
    "morton": "Bowser Jr", "roy": "Bowser Jr", "wendy": "Bowser Jr",
    "luma-blue": "Boo", "luma-green": "Boo", "luma-red": "Boo",
    "rosalina": "Daisy", "larry": "Bowser Jr", "luma": "Boo",   # last: appending keeps earlier ids
}
# Sound-name tags where zz<name> would repeat Extra Innings' own names (zzrosalina_*, zzlarry_*, zzluma_*)
TAGS = {"rosalina": "zzsrosalina", "larry": "zzslarry", "luma": "zzsluma"}
LOUD = {  # quiet in game (Nick): full sound volume (stock 0x6B) and a soft-clip drive on the waves
    "dry-bowser": {"volume": 127, "drive": 2.5}, "honey-queen": {"volume": 127, "drive": 2.0},
}
# Each set adds ~125 KB to its family's voice file, which loads whole whenever that family plays; Bowser Jr's file carries
# every Koopaling, so it only gets the sets of characters that are actually in the build. Boo's file carries the four
# Lumas and Lubba (clean base 2026-09-25: ~800 KB of wave data, Bowser Jr's ~1.16 MB, Daisy's ~390 KB).
STREAMS = [  # appended after every voice: {name, path (joined with /sound_NA/), source .brstm, template STRM sound}
    {"name": "zzpauline_chance", "path": "stream/zzpauline_chance.brstm", "source": OUT / "zzpauline_chance.brstm",
     "template": "jin_chance_ma"},
]


ITEM_TEMPLATE = "bb_ojitem_shot"   # the items' throw sound (SE 0xAE): items' own clips go in its file, as it is
ITEM_CLIP_SECONDS = 3.0   # = creators.items.CLIP_SECONDS


def build_for_game(work, game=None, cache=ENCODED, extra=None, item_clips=None, only=None):
    """The patcher's voices: the player's clean game (game, else game_source.root()) + our clips and streams, into
    <work>/sounds/clean/{MY2.brsar, voice_tables.json}, where charbuild.build(work=) reads them (charbuild.DERIVED).
    Our clips come pre-encoded from cache (ENCODED); a clip missing there is encoded (in parallel) and added to it.
    extra: imported characters' voice sets (build's `extra`); only: build's. Returns (brsar, tables) paths."""
    out = Path(work) / "sounds/clean"
    build(Path(game or game_source.root()) / "files/sound_NA/MY2.brsar", out, cache, extra, item_clips, only)
    return out / "MY2.brsar", out / "voice_tables.json"


def main():
    arg = {a.split("=", 1)[0]: a.split("=", 1)[1] for a in sys.argv[1:] if "=" in a}
    if "--game" in arg or "--work" in arg:
        assert "--game" in arg and "--work" in arg, "--game and --work go together"
        print(*build_for_game(arg["--work"], arg["--game"]), sep="\n")
        return
    only = arg.get("--base")
    for base, (src, out) in bases().items():
        if only in (None, base):
            print(f"{base}: {src}")
            build(src, out)


def _wav_len(path):
    import wave
    with wave.open(str(path)) as w:
        assert w.getsampwidth() == 2, f"{Path(path).name}: a 16-bit .wav is needed"
        return w.getframerate(), w.getnframes()


def family(template):
    """The FAMILY_SOUND key of a template (a name or id, "Bowser Jr." or 0x13), or None: only those families' voice
    files take new clips."""
    from sluggers_data import CHAR_NAMES, char_id

    def cid(ref):                                    # names match with or without a final "." ("Bowser Jr")
        if isinstance(ref, str) and not ref.strip().lower().startswith("0x") and not ref.strip().isdigit():
            key = ref.strip().lower().rstrip(".")
            return next((i for i, n in enumerate(CHAR_NAMES) if n.strip().lower().rstrip(".") == key), None)
        try:
            return char_id(ref)
        except (KeyError, ValueError):
            return None
    if template in FAMILY_SOUND:
        return template
    tid = cid(template)
    return next((f for f in FAMILY_SOUND if tid is not None and tid in FAMILY_IDS.get(f, (cid(f),))), None)


def build(src, out, cache=None, extra=None, item_clips=None, only=None):
    """extra: imported characters' voice sets, {voice name: {"dir": folder with the 12 SLOTS .wav, "template": the
    character's template (name or id)}} (charpack.materialize's "voice" / "voice_dir"). Appended after ours, so our
    sound ids don't move. A set whose template isn't a FAMILY_SOUND family is skipped (printed): that character
    keeps its template's voices, as charbuild does for a voice with no table. A player's set (voice_clips.prepare,
    the character window's Voice page) may also have "stock": {slot: a stock sound's name}, slots that play that stock
    sound (no clip, no .wav), and "family_sound": a stock sound in the family voice file its clips go in, for a
    template outside FAMILY_SOUND.
    item_clips: [{"name": item name, "event": "launch" | "hit" | "land", "wav": path}]: items' own sounds
    (creators.items, sound.*_clip), after the voices, in ITEM_TEMPLATE's file with its entry; their ids go to
    voice_tables.json "items" {name: {event: id}}.
    only: the voice set names to build (an edition: its characters' voices, so the download ships only those sets;
    Nick: a lean beta); None = every set. The ids are this build's own (voice_tables.json), so a set left out moves
    none of the others' routing."""
    out.mkdir(parents=True, exist_ok=True)
    a = Brsar(src)
    sounds = {s["name"]: s for s in a.sounds()}
    sets = {name: (template, SETS / name) for name, template in CHARACTERS.items() if only is None or name in only}
    family_sound = {name: FAMILY_SOUND[t] for name, (t, _) in sets.items()}
    stock = {}                                      # {set: {slot: stock sound name}}: no clip of its own there
    for name, e in (extra or {}).items():
        fam = family(e["template"])
        assert name not in sets, f"imported voice {name!r} has the name of one of ours"
        own = FAMILY_SOUND[fam] if fam else e.get("family_sound") if e.get("family_sound") in sounds else None
        if own is None:
            print(f"voice {name}: template {e['template']!r} has no voice family we add to "
                  f"({', '.join(FAMILY_SOUND)}): it keeps its template's voices")
            continue
        stock[name] = {s: n for s, n in (e.get("stock") or {}).items() if s in SLOTS}
        assert all(n in sounds for n in stock[name].values()), f"voice {name}: unknown stock sounds {stock[name]}"
        missing = [s for s in SLOTS if s not in stock[name] and not (Path(e["dir"]) / f"{s}.wav").is_file()]
        assert not missing, f"voice {name}: {e['dir']} has no {', '.join(m + '.wav' for m in missing)}"
        sets[name] = (fam or e["template"], Path(e["dir"]))
        family_sound[name] = own
    clips = []
    for name, (template, folder) in sets.items():
        family_file = sounds[family_sound[name]]["file"]
        tag = TAGS.get(name, "zz" + name.replace("-", ""))
        for slot in SLOTS:
            if slot in stock.get(name, {}):
                continue
            clips.append({"name": f"{tag}_{slot}", "file": SELECT_FILE if slot == "v13" else family_file,
                          "wav": folder / f"{slot}.wav", **LOUD.get(name, {})})
    items_at = {}
    for k, c in enumerate(item_clips or ()):
        rate, n = _wav_len(c["wav"])
        assert n / rate <= ITEM_CLIP_SECONDS, f"{c['name']}: its sound is {n / rate:.1f} s (at most {ITEM_CLIP_SECONDS} s)"
        tag = f"zzitem{k}"
        items_at.setdefault(c["name"], {})[c.get("event", "launch")] = tag
        clips.append({"name": tag, "file": sounds[ITEM_TEMPLATE]["file"], "wav": Path(c["wav"]),
                      "template": ITEM_TEMPLATE})
    streams = [dict(s, size=Path(s["source"]).stat().st_size) for s in STREAMS]
    if cache:
        print("encoded clips: %d, newly encoded: %d" % fill_cache(src, clips, cache))
    ids = add_sounds(src, out / "MY2.brsar", clips, template_sound="cuppa_jr_v1", streams=streams, cache=cache)
    tables = {name: [sounds[stock[name][slot]]["index"] if slot in stock.get(name, {}) else
                     ids[f"{TAGS.get(name, 'zz' + name.replace('-', ''))}_{slot}"] for slot in SLOTS] for name in sets}
    more = {"items": {name: {ev: ids[tag] for ev, tag in tags.items()} for name, tags in items_at.items()}} \
        if items_at else {}
    json.dump({"slots": SLOTS, "tables": tables, "templates": {name: t for name, (t, _) in sets.items()}, **more,
               "pauline_chance": ids["zzpauline_chance"]}, open(out / "voice_tables.json", "w"), indent=1)
    b = Brsar(out / "MY2.brsar")
    grown = {f: (len(a.file_bytes(f)[1]), len(b.file_bytes(f)[1]))
             for f in sorted({c["file"] for c in clips})}
    for f, (old, new) in grown.items():
        print(f"file {f}: wave data {old // 1024} KB -> {new // 1024} KB")
    print(f"BRSAR {len(a.b) // 1024} KB -> {len(b.b) // 1024} KB, {len(clips)} sounds, ids {min(ids.values())}.."
          f"{max(ids.values())}; streams: " + ", ".join(f"{s['name']} {ids[s['name']]} ({s['size']} B)" for s in streams))


if __name__ == "__main__":
    main()
