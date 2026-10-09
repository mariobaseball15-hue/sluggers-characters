"""A character's own voice clips, chosen in the character window's Voice page (Nick: "How would people edit them??").

A character we added (imported, a .sluggie, a recolor, a character file) has 12 voice moments, charpack.SLOTS /
build_voices.SLOTS (v1 v3 v4 v5 v6 v7 v8 v10 v11 v12 v13 v14; their roles are voice_sets.py's). The player may give
any of them a WAV of their own; the others keep the base's: the character's own voice set if it has one (ours in
models/work/sounds/sets/<voice>, an imported one's voice/ folder), else its template's stock clips.

  per-character key "voice_clips": {slot: path of a WAV made by convert()}   (the profile's "characters", like stats)

convert() takes any WAV (PCM 8 / 16 / 24 / 32-bit or float, any rate, any channels) and writes it the way our voice
sets are: mono, 22,050 Hz, 16-bit, at most 1.4 s (build_voices / charpack RATE and MAX_SECONDS). The files live in
the player's folder (charpack.default_dest()/voices/<name>/), not in the patcher's.

At patch time, prepare() gives each definition with "voice_clips" a voice set of its own: the chosen clips plus the
base's own set's for the rest, and for a stock base only the chosen ones (the other slots play the stock sounds
themselves: build_voices' "stock"). Its template's family voice file takes the new clips (build_voices'
"family_sound": the template's stock v1 sound, STOCK_VOICE). The sets go to build_voices as `extra`, like imported
characters' voices, and charbuild routes the character to its table ("voices" feature).
"""
import hashlib
import shutil
import struct
import sys
from pathlib import Path

import numpy as np

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))

SLOTS = ["v1", "v3", "v4", "v5", "v6", "v7", "v8", "v10", "v11", "v12", "v13", "v14"]   # build_voices.SLOTS
RATE, MAX_SECONDS = 22050, 1.4                                                          # charpack / voice_sets
KEY = "voice_clips"
# voice_sets.py's roles (Jbiscuit's sound guide, Extra Innings' Larry set), in plain words
MOMENTS = {"v1": "Short cheer", "v3": "Big effort (a strong swing or throw)", "v4": "Talking line",
           "v5": "Long cheer", "v6": "Hit by something", "v7": "Long cheer (another)", "v8": "Long cheer (a third)",
           "v10": "Stagger", "v11": "Small hurt", "v12": "Falling / disappointed",
           "v13": "Character select (their name call)", "v14": "Throw grunt"}
# a stock character's voice sounds in MY2.brsar are <prefix>_v1 ... (the 41 voice families); the first match of a
# name part wins (Baby Mario before Mario, Waluigi before Luigi, King Boo before Boo, Toadsworth before Toad)
STOCK_VOICE = [("Baby Mario", "b_mario"), ("Baby Luigi", "b_luigi"), ("Baby Peach", "babype"),
               ("Baby Daisy", "babyda"), ("Baby DK", "babydk"), ("Bowser Jr", "cuppa_jr"), ("Bowser", "cuppa"),
               ("King Boo", "k_teresa"), ("Boo", "teresa"), ("King K. Rool", "Kk"), ("Waluigi", "waluigi"),
               ("Wario", "wario"), ("Mario", "mario"), ("Luigi", "luigi"), ("Donkey Kong", "donkey"),
               ("Diddy", "diddy"), ("Dixie", "dicsy"), ("Funky", "funky"), ("Tiny", "tiny"), ("Peach", "peach"),
               ("Daisy", "daisy"), ("Yoshi", "yossy"), ("Paratroopa", "pata"), ("Koopa Troopa", "noko"),
               ("Toadsworth", "kinoji"), ("Toadette", "kinopico"), ("Toad", "kinopio"), ("Shy Guy", "heyho"),
               ("Birdo", "cather"), ("Monty Mole", "tyoropu"), ("Pianta", "monte"), ("Noki", "mare"),
               ("Hammer Bro", "h_bros"), ("Fire Bro", "h_bros"), ("Boomerang Bro", "h_bros"),
               ("Magikoopa", "kameku"), ("Petey", "b_pakkun"), ("Paragoomba", "p_kuribo"), ("Goomba", "kuribo"),
               ("Dry Bones", "karon"), ("Dark Bones", "karon"), ("Wiggler", "wiggler"), ("Blooper", "ges"),
               ("Kritter", "kurittar")]


class VoiceError(Exception):
    """Said to the player as it is."""


# --- a WAV of any kind -> ours

def read_wav(path):
    """(rate, mono float samples in -1..1) of a RIFF WAVE: PCM 8 / 16 / 24 / 32-bit, float 32 / 64, extensible."""
    b = Path(path).read_bytes()
    if len(b) < 12 or b[:4] != b"RIFF" or b[8:12] != b"WAVE":
        raise VoiceError(f"{Path(path).name} isn't a WAV file")
    fmt = data = None
    o = 12
    while o + 8 <= len(b):
        cid, size = b[o:o + 4], struct.unpack_from("<I", b, o + 4)[0]
        body = b[o + 8:o + 8 + size]
        if cid == b"fmt ":
            fmt = body
        elif cid == b"data":
            data = body
        o += 8 + size + (size & 1)
    if fmt is None or data is None:
        raise VoiceError(f"{Path(path).name} has no sound in it")
    tag, channels, rate = struct.unpack_from("<HHI", fmt, 0)
    bits = struct.unpack_from("<H", fmt, 14)[0]
    if tag == 0xFFFE and len(fmt) >= 26:                 # extensible: the sub-format's first two bytes
        tag = struct.unpack_from("<H", fmt, 24)[0]
    width = bits // 8
    if channels < 1 or width < 1 or rate < 1000:
        raise VoiceError(f"{Path(path).name} isn't a sound this can read")
    n = len(data) // (width * channels)
    raw = data[:n * width * channels]
    if tag == 1 and width == 1:
        x = (np.frombuffer(raw, np.uint8).astype(np.float64) - 128) / 128
    elif tag == 1 and width == 2:
        x = np.frombuffer(raw, "<i2").astype(np.float64) / 32768
    elif tag == 1 and width == 3:
        a = np.frombuffer(raw, np.uint8).reshape(-1, 3).astype(np.int32)
        v = a[:, 0] | (a[:, 1] << 8) | (a[:, 2] << 16)
        x = np.where(v >= 1 << 23, v - (1 << 24), v).astype(np.float64) / (1 << 23)
    elif tag == 1 and width == 4:
        x = np.frombuffer(raw, "<i4").astype(np.float64) / (1 << 31)
    elif tag == 3 and width in (4, 8):
        x = np.frombuffer(raw, "<f4" if width == 4 else "<f8").astype(np.float64)
    else:
        raise VoiceError(f"{Path(path).name} is a kind of WAV this can't read (format {tag}, {bits}-bit): save it "
                         f"as a plain 16-bit WAV")
    return rate, x.reshape(-1, channels).mean(axis=1)


def convert(src, dest):
    """Any WAV -> ours at dest (mono, RATE, 16-bit, at most MAX_SECONDS). Returns {"seconds": its length before,
    "cut": True when it was longer than MAX_SECONDS}. VoiceError in plain words."""
    rate, x = read_wav(src)
    if not len(x):
        raise VoiceError(f"{Path(src).name} has no sound in it")
    seconds = len(x) / rate
    if rate != RATE:
        t = np.arange(int(round(seconds * RATE))) / RATE
        x = np.interp(t, np.arange(len(x)) / rate, x)
    cut = len(x) > int(MAX_SECONDS * RATE)
    x = x[:int(MAX_SECONDS * RATE)]
    write(dest, np.clip(np.round(x * 32767), -32768, 32767).astype("<i2"))
    return {"seconds": seconds, "cut": cut}


def write(dest, samples, rate=RATE):
    import wave
    Path(dest).parent.mkdir(parents=True, exist_ok=True)
    with wave.open(str(dest), "wb") as w:
        w.setnchannels(1)
        w.setsampwidth(2)
        w.setframerate(rate)
        w.writeframes(np.asarray(samples, "<i2").tobytes())


# --- where the player's clips live

def folder(name, dest=None):
    """The player's clips for a character: <imported characters' folder>/voices/<name>/ (AppData, theirs)."""
    import charpack
    import re
    base = Path(dest) if dest else charpack.default_dest()
    return base / "voices" / (re.sub(r"[^a-z0-9]+", "-", str(name).lower()).strip("-") or "character")


def take(src, name, slot, dest=None):
    """A WAV the player chose for `slot`, converted into their folder. Returns (path, convert()'s result)."""
    src = Path(src)
    tag = hashlib.sha1(src.read_bytes()).hexdigest()[:8]
    out = folder(name, dest) / f"{slot}-{tag}.wav"
    return out, convert(src, out)


# --- the base's clips

def stock_prefix(template):
    """The stock voice family prefix (e.g. "cuppa_jr") of a stock character (name or id), or None (a Mii)."""
    from sluggers_data import CHAR_NAMES, char_id
    try:
        name = CHAR_NAMES[char_id(template)].strip()
    except (KeyError, ValueError, IndexError, AssertionError):
        name = str(template)
    return next((p for part, p in STOCK_VOICE if part.lower() in name.lower()), None)


def own_set(d):
    """The folder of a definition's own full voice set (an imported one's voice_dir, ours in sounds/sets), or None."""
    if d.get("voice_dir"):
        return Path(d["voice_dir"])
    if d.get("voice"):
        import build_voices
        p = build_voices.SETS / d["voice"]
        if all((p / f"{s}.wav").is_file() for s in SLOTS):
            return p
    return None


def stock_clip(game, template, slot, dest):
    """The template's stock clip for `slot`, decoded from the player's game (MY2.brsar) to dest. None if it has
    none."""
    import brsar
    prefix = stock_prefix(template)
    if prefix is None:
        return None
    a = _archive(game)
    s = next((s for s in a.sounds() if s["name"] == f"{prefix}_{slot}" and s["type"] == 3), None)
    if s is None:
        return None
    r, wb = a.file_bytes(s["file"])
    rate, chans = brsar.rwar_wave(wb, brsar.rwsd_wave_index(r, brsar.u32(a.b, s["detail"])))
    write(dest, np.asarray(chans[0], "<i2"), rate)
    return Path(dest)


_ARCHIVES = {}


def _archive(game):
    import brsar
    p = Path(game) / "files/sound_NA/MY2.brsar"
    if p not in _ARCHIVES:
        _ARCHIVES[p] = brsar.Brsar(p)
    return _ARCHIVES[p]


def can_have_own(d):
    """(True, "") when this character's clips can go in the game, else (False, why in plain words)."""
    import build_voices
    t = d.get("template")
    if build_voices.family(t) is not None or stock_prefix(t) is not None:
        return True, ""
    return False, f"characters built on {t} have no voice in the game (the Miis are silent), so there's none to change"


# --- patch time

def check(clips, name):
    """Problems ([] = fine) with a profile's "voice_clips" for `name`."""
    if not isinstance(clips, dict):
        return [f"{name}: voice_clips must be {{slot: WAV file}}"]
    out = [f"{name}: voice_clips has {s!r}, which isn't one of the 12 moments ({' '.join(SLOTS)})"
           for s in clips if s not in SLOTS]
    out += [f"{name}: its voice clip for {MOMENTS.get(s, s)} ({p}) isn't there any more: choose it again in its "
            f"Voice page" for s, p in clips.items() if s in SLOTS and not Path(str(p)).is_file()]
    return out


def prepare(chars, game, work):
    """Each definition in chars with "voice_clips": a voice set of its own in <work>/voices/<name>/, and the
    definition's "voice" (the set's name), "voice_dir", "voice_stock" (slots left to the stock sounds) and
    "voice_family" set for build_voices (patch.make_work passes them as `extra`). Returns (the voiced definitions,
    notes in plain words)."""
    import build_voices
    voiced, notes = [], []
    for d in chars:
        clips = d.pop(KEY, None)
        if not clips:
            continue
        ok, why = can_have_own(d)
        if not ok:
            notes.append(f"{d['name']}'s voice clips were left out: {why}")
            continue
        base = own_set(d)
        name = f"pv{int(str(d['id']), 0):02x}"
        out = Path(work) / "voices" / name
        out.mkdir(parents=True, exist_ok=True)
        stock = {}
        for s in SLOTS:
            if s in clips:
                shutil.copyfile(clips[s], out / f"{s}.wav")
            elif base is not None:
                shutil.copyfile(base / f"{s}.wav", out / f"{s}.wav")
            else:
                stock[s] = f"{stock_prefix(d['template'])}_{s}"
        d["voice"], d["voice_dir"] = name, str(out)
        if stock:
            d["voice_stock"] = stock
        if build_voices.family(d["template"]) is None:
            d["voice_family"] = f"{stock_prefix(d['template'])}_v1"
        voiced.append(d)
    return voiced, notes
