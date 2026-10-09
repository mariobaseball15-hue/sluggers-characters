"""Our items as data. The presets (scripts/creators/presets/*.slgitem) are the one source of every item constant:
the item modules (koopa_items, ice_item, bullet_bill, lemmy_balls, wendy_rings, starbits_item, starbits_roulette)
read their values from here (docs/item-creator.md). A preset keeps today's item id (PRESET_IDS)."""
from pathlib import Path

from creators import blocks

PRESET_IDS = {"star-bits": 6, "ice": 7, "lemmy": 8, "bullet-bill": 9, "iggy": 10, "larry": 11, "wendy": 12,
              "ludwig": 13}
_presets = None


def preset(name):
    """Preset `name` (its file stem), checked."""
    global _presets
    if _presets is None:
        _presets = blocks.presets("item")
        assert set(_presets) == set(PRESET_IDS), f"item presets {sorted(_presets)} != {sorted(PRESET_IDS)}"
    return _presets[name]


def block(name, key):
    """Block `key` of preset `name` ({} when the preset has none)."""
    return preset(name)["blocks"].get(key) or {}


def hue(group):
    """A trail / icon hue group -> the item modules' form: a hue turn, or (hue turn, lighten) when it lightens."""
    return (group["hue"], group["lighten"]) if group.get("lighten") else group["hue"]


def color(c):
    return tuple(c)


# --- step 2: new items (docs/item-creator.md) ----------------------------------------------------------------
FIRST_CUSTOM = 14
POSITIONS = ("P", "C", "1B", "2B", "3B", "SS", "LF", "CF", "RF")   # the fielder slots 0..8 (bullet_bill FIELDER_ARRAYS)                # after the presets (6..13)
MAX_CUSTOM = 8                   # placeholder cap until the item section / disc / frame rate are measured
BASES = {"thrown-ball": 1, "lob": 3, "shell": 0, "bobomb": 2, "banana": 4, "boo": 5}   # the stock item it is at use
ICON_ROWS = {"shell": 0xF3, "fireball": 0xF5, "bobomb": 0xF4, "pow": 0xF7, "banana": 0xF8, "boo": 0xF6}
MODEL_BALLS = {"circus-ball": 3, "bullet-bill": 1}
SOUND_EVENTS = {"launch": "throw", "hit": "hit", "land": "landing"}
SOUND_CHASSIS = {"thrown-ball": ("launch", "hit", "land"), "shell": ("launch", "hit"), "lob": ("launch", "land")}   # else the throw only    # our ball models and how many balls each can dress


CLIP_SECONDS = 3.0                                   # = build_voices.ITEM_CLIP_SECONDS


def clip_problem(path):
    """What's wrong with an item's own sound file, in plain words, or None: a readable 16-bit .wav of at most
    CLIP_SECONDS (what build_voices takes)."""
    import wave
    try:
        with wave.open(str(path)) as w:
            if w.getsampwidth() != 2:
                return f"{Path(path).name} is {8 * w.getsampwidth()}-bit; it needs to be 16-bit"
            seconds = w.getnframes() / w.getframerate()
    except (wave.Error, EOFError, OSError) as e:
        return f"{Path(path).name} isn't a .wav the game can use ({e})"
    return f"{Path(path).name} is {seconds:.1f} s; at most {CLIP_SECONDS:g} s" if seconds > CLIP_SECONDS else None


# the Koopalings' six by what they are (the Characters Beta has no Koopalings: an edit of one is saved under this
# name, items_window.TITLES): a creation with one of these names edits that item too
ITEM_NAMES = {"lemmy": "Bouncing circus balls", "bullet-bill": "Bullet Bill", "iggy": "Fast green fireball",
              "larry": "Fast cyan fireball", "wendy": "Hopping rings", "ludwig": "Five fireballs"}


def preset_of(name):
    """The preset (file stem) a creation name edits, or None: our items' display names, their names by what they are
    (ITEM_NAMES) or stems, any case."""
    key = name.strip().lower()
    return next((p for p in PRESET_IDS if key in (p, preset(p)["name"].strip().lower(),
                                                  ITEM_NAMES.get(p, p).strip().lower())), None)


def values_text(s):
    """A customs spec's flight in a few words, for the build log: an edit's values (e.g. "speed x1.2, homes, 1 ball";
    what it leaves behind: "6 rings, wander 0.12 m a frame, hop 0.7 m")."""
    if "ground" in s:
        g = s["ground"]
        what = "rings" if g.get("wander") else "star bits"
        wander = f", wander {g['wander']['speed']} m a frame" if g.get("wander") else ""
        return f"{g['count']} {what}{wander}, hop {(g.get('hop') or {}).get('height')} m"
    path = ("homes" if s.get("home") else "bounces" if s.get("bounce") else "skims" if s.get("skim") else
            "level" if s.get("level") else "arc")
    n = s.get("count", 1)
    knock = f", knockback {s['slide'][0]:g} x {s['slide'][1]} frames" if s.get("slide") else ""
    return f"speed x{s.get('speed', 1.0):g}, {path}, {n} ball{'s' if n != 1 else ''}{knock}"


def customs(creations, keep_ours=False):
    """Item creations (checked, in the profile's order) -> specs for the build. A creation named like one of ours
    (preset_of) edits it: it keeps that item's id and gets "replaces": the preset (one edit per item; an edit equal
    to the preset changes nothing and is dropped). Any other is a new item, ids FIRST_CUSTOM.. . Spec: {id, name,
    replaces, base, chassis, count, speed, level, gravity, bounce, skim, home, effect, slide, dodge, trail, model,
    icon, roulette, characters, always}; an edit of Star Bits / Wendy (lob-hazards) also has "ground": its spawn
    values. Raises blocks.Invalid, in plain words, for anything the build can't make yet."""
    out, problems = [], []
    names, edited = set(), set()
    for c in creations:
        blocks.check(c)
        if c["kind"] != "item":
            continue
        b, name = c["blocks"], c["name"]
        say = lambda text: problems.append(f"{name}: {text}")  # noqa: E731
        key = name.strip().lower()
        ours = preset_of(name)
        if ours:
            if ours in edited:
                say("is edited twice (one change of each of our items per game)")
            edited.add(ours)
            if b == preset(ours)["blocks"] and not keep_ours:
                continue                                    # unchanged: ours as it is (keep_ours: the build has
                #                                             the Koopalings' items off, and this one was chosen)
        elif key in names or key in {"shell", "fireball", "bobomb", "pow", "banana", "boo", "starbits", "ice", "lemmy",
                                     "bill", "iggy", "larry", "wendy", "ludwig"}:
            say("another item already has this name")
        names.add(key)
        chassis = b["item"]["chassis"]
        was = preset(ours)["blocks"]["item"]["chassis"] if ours else None
        if chassis == "lob-hazards" and was != "lob-hazards" and (b.get("spawn") or {}).get("what") != "rings":
            say("a new item can leave rings behind, but not star bits (the game has one star-bit pool: change "
                "Star Bits instead)")
            continue
        if was == "lob-hazards" and chassis != "lob-hazards":
            say(f"stays an item that leaves {'star bits' if ours == 'star-bits' else 'rings'} behind")
            continue
        launch, move, eff, hit = b.get("launch") or {}, b.get("move") or {}, b.get("effect") or {}, b.get("hit") or {}
        look = b.get("look") or {}
        sound, sounds = b.get("sound") or {}, {}
        for ev, word in SOUND_EVENTS.items():
            game_id, clip = sound.get(ev), sound.get(ev + "_clip")
            if game_id is None and not clip:
                continue
            if ev not in SOUND_CHASSIS.get(b["item"]["chassis"], ("launch",)):
                say(f"the {word} sound of an item built on {b['item']['chassis']} can't change yet")
            elif game_id is not None and clip:
                say(f"the {word} has one sound: a game sound or your own clip")
            elif clip and not str(clip).lower().endswith(".wav"):
                say(f"its own {word} sound is a .wav file")
            elif clip and Path(clip).name not in [Path(f).name for f in c.get("files", [])]:
                say(f"its own {word} sound has to travel with it (list it in its files)")
            elif game_id is not None and not 0 <= game_id < 1050:
                say(f"{word} sound {game_id} isn't one of the game's (0 to 1049)")
            elif clip and Path(clip).is_file() and clip_problem(clip):   # (the patcher has put its path next to
                say(f"its own {word} sound: {clip_problem(clip)}")       # the creation file by now)
            else:
                sounds[ev] = ("clip", clip) if clip else ("id", game_id)
        given = b.get("given") or {}
        spec = {"id": PRESET_IDS[ours] if ours else FIRST_CUSTOM + sum(1 for s in out if not s.get("replaces")),
                "name": name, "replaces": ours, "chassis": chassis, "sounds": sounds, "runners": runners(b),
                "roulette": list(given.get("roulette") or [0, 0, 0]), "characters": list(given.get("characters") or []),
                "always": bool(given.get("always"))}
        if chassis == "lob-hazards":
            spec.update(ground(ours, b, say))
            if not ours:                                 # a new ring item: its own pool (wendy_rings pools)
                g = spec["ground"]
                if g["height"] not in (None, block("wendy", "spawn")["look"]["height"]):
                    say("its rings are drawn at the ring model's own height")
                spec.update(base=BASES["lob"], effect=None, slide=None, dodge=None, trail=None, freeze_frames=None,
                            spin_frames=None, count=1, model="ring", speed=1.0)
            out.append(spec)
            continue
        count = launch.get("count", 3) if chassis == "thrown-ball" else 1
        if chassis == "shell":
            spec.update(speed=float(launch.get("speed", 1.0)), size=float(look.get("scale", 1.0)))
        model = look.get("model") or {"thrown-ball": "fireball", "lob": "pow"}.get(chassis, chassis)
        if chassis == "thrown-ball" and model not in ("fireball", "own") + tuple(MODEL_BALLS):
            say(f"a thrown ball can look like a fireball, {', '.join(MODEL_BALLS)} or your own model")
        if chassis == "lob" and model != "pow":
            say("a lob looks like a POW for now")
        if model == "own":                               # the player's .obj (own_models)
            obj = look.get("obj")
            if chassis != "thrown-ball":
                say("only a thrown ball can have its own model for now")
            elif not obj or not str(obj).lower().endswith(".obj"):
                say("its own model is an .obj file (Look: Your own model)")
            elif Path(obj).name not in [Path(f).name for f in c.get("files", [])]:
                say("its own model has to travel with it (list the .obj, its .mtl and textures in its files)")
            elif Path(obj).is_file():                    # (the patcher has put its path next to the creation)
                import own_models
                n = own_models.triangles(obj)
                if n > own_models.MAX_TRIS:
                    say(f"its own model has {n} triangles; {own_models.LIMITS}")
            spec["obj"] = obj
            spec["model_size"] = float(look.get("scale", 1.0))
            spec["model_height"] = look.get("height")
        if model in MODEL_BALLS and count > MODEL_BALLS[model]:
            say(f"the {model} model has {MODEL_BALLS[model]} to go round: throw at most {MODEL_BALLS[model]}")
        if model in MODEL_BALLS:
            own = block({"circus-ball": "lemmy", "bullet-bill": "bullet-bill"}[model], "look")
            if (look.get("scale", 1.0), look.get("height")) != (own.get("scale", 1.0), own.get("height")):
                say(f"the {model} model keeps its own size and height for now")
        path = move.get("path", "straight") if chassis == "thrown-ball" else None
        kind = eff.get("kind") if eff else {"thrown-ball": "stun", "lob": "quake", "shell": "knockdown"}.get(chassis)
        if chassis == "lob" and kind != "quake":
            say("a lob quakes (the POW's own burst)")
        if eff.get("freeze_frames") is not None and kind != "freeze":
            say("only a freeze lasts a number of frames")
        if eff.get("spin_frames") is not None and kind != "spin":
            say("only a spin lasts a number of spin frames")
        trail = look.get("trail")
        spec.update({
            "base": BASES[chassis], "count": count, "speed": float(spec.get("speed", launch.get("speed", 1.0))),
            "level": bool(launch.get("level")), "gravity": launch.get("gravity"),
            "bounce": (move["bounce"]["factor"], move["bounce"]["min_hop"]) if path == "bounce" else None,
            "skim": path == "skim", "home": (move["home"]["turn_deg"], move["home"]["spawn_dist"])
            + ((POSITIONS.index(move["home"]["target"]),) if move["home"].get("target", "nearest") != "nearest" else ())
            if path == "home" else None,
            "effect": kind, "slide": (eff["slide_speed"], eff["slide_frames"])
            if kind == "knockdown" and eff.get("slide_speed") is not None else None,
            "freeze_frames": eff.get("freeze_frames") if kind == "freeze" else None,
            "spin_frames": (eff.get("spin_frames") or 90) if kind == "spin" else None,
            "dodge": hit.get("dodge_height"),
            # trail: None = no trail; a hue turn (or (turn, lighten)) = recoloured; {"hue": 0, "lighten": 0} = stock
            "trail": None if trail is None else "stock" if not (trail["hue"] or trail.get("lighten")) else hue(trail),
            "model": model, "icon": look.get("icon") or {"from": {"thrown-ball": "fireball", "lob": "pow"}.get(chassis,
                                                                                                            chassis)},
        })
        blast, peels = b.get("blast") or {}, b.get("peels") or {}   # the stock item's own table (item_params)
        params = {k: v for k, v in (("radius", hit.get("radius")), ("quake_radius", eff.get("quake_radius")),
                                    ("fuse_frames", blast.get("fuse_frames")), ("blast_radius", blast.get("radius")),
                                    ("blast_height", blast.get("height")), ("peel_spread", peels.get("spread")))
                  if v is not None}
        spec["peels"] = peels.get("count") if chassis == "banana" else None
        spec["slip_frames"] = eff.get("slip_frames") if chassis in ("banana", "lob") else None
        spec["boo_frames"] = (b.get("boo") or {}).get("frames") if chassis == "boo" else None
        spec["burn"] = burns(b) if chassis == "thrown-ball" else True
        spec["params"] = params if chassis in ("thrown-ball", "bobomb", "banana", "lob") else {}
        if spec["model"] != "fireball" and spec["trail"] not in (None,):
            say("a model item has no flame trail (set the trail to none)")
        out.append(spec)
    rings = [s for s in out if "ground" in s and not s["replaces"]]
    if len(rings) > 3:
        problems.append(f"at most 3 new ring items in one game ({len(rings)} given)")
    wendy = next((s["ground"]["count"] for s in out if s["replaces"] == "wendy"), block("wendy", "spawn")["count"])
    if rings and wendy + sum(s["ground"]["count"] for s in rings) > 24:
        problems.append("at most 24 rings in one game, Wendy's included")
    new = sum(1 for s in out if not s.get("replaces"))
    if new > MAX_CUSTOM:
        problems.append(f"at most {MAX_CUSTOM} new items in one game for now ({new} given)")
    if problems:
        raise blocks.Invalid("; ".join(problems))
    return out


def ground(ours, b, say):
    """An edit of Star Bits / Wendy (the only users of their pools): their spawn values, as the modules' constants."""
    sp, look = b.get("spawn") or {}, b.get("look") or {}
    mv, eff = sp.get("move") or {}, sp.get("effect") or {}
    want = "bits" if ours == "star-bits" else "rings"          # (a new one: rings, customs checked)
    if sp.get("what") != want:
        say(f"still leaves {'star bits' if want == 'bits' else 'rings'} behind")
    if want == "rings" and not 1 <= sp.get("count", 0) <= 12:
        say("leaves 1 to 12 rings")
    if want == "rings" and sp.get("lifetime", 0):
        say("rings stay for the half-inning for now (lifetime 0)")
    if (eff.get("kind") or "slip") != "slip":
        say("what's left behind trips fielders up (slip) for now")
    for need in ("hop",) + (("wander",) if want == "rings" else ("orbit",)):
        if not mv.get(need):
            say(f"what's left behind needs its {need} settings")
    colors = (sp.get("look") or {}).get("colors") or []
    if want == "bits" and len(colors) != 4:
        say("star bits come in 4 colours")
    if want == "rings" and not colors:
        say("rings need at least one colour")
    return {"ground": {"count": sp.get("count"), "lifetime": sp.get("lifetime", 0), "spread": sp.get("spread"),
                       "hop": mv.get("hop"), "wander": mv.get("wander"), "orbit": mv.get("orbit"),
                       "radius": (sp.get("hit") or {}).get("radius"), "colors": [tuple(c) for c in colors],
                       "scale": (sp.get("look") or {}).get("scale"), "height": (sp.get("look") or {}).get("height"),
                       "thrower_scale": look.get("scale")},
            "icon": look.get("icon") or {"draw": "star-bits" if want == "bits" else "ring"}}


# --- read-back: what a built game does with each item (for end-to-end checks; nothing is added to the game) -----
def _s16(v):
    return v - 0x10000 if v & 0x8000 else v


def _chain(dol, stub, reg=12, end=400):
    """{variant id: its block's address} from a koopa_items stub: each `cmpwi rREG, id` + `beq block` up to the
    stub's first unconditional branch."""
    out, pc = {}, stub
    for _ in range(end):
        w = dol.u32(pc)
        op = w >> 26
        if op == 11 and (w >> 16) & 0x1F == reg and (w >> 21) & 0x1F == 0:           # cmpwi crf0, rREG, imm
            nxt = dol.u32(pc + 4)
            if nxt >> 26 == 16 and (nxt >> 21) & 0x1F == 12 and (nxt >> 16) & 0x1F == 2:   # beq
                out.setdefault(_s16(w & 0xFFFF), pc + 4 + _s16(nxt & 0xFFFC))
        elif op == 18 and not w & 1:                                                  # b (not bl): the chain ends
            break
        pc += 4
    return out


def _float_at(dol, block, freg):
    """The float a stub block loads into freg: `lis r12, hi; addi r12, r12, lo; lfs fREG, d(r12)`."""
    import struct
    hi = lo_ = None
    for pc in range(block, block + 40, 4):
        w = dol.u32(pc)
        op, rt = w >> 26, (w >> 21) & 0x1F
        if op == 15 and rt == 12:
            hi = _s16(w & 0xFFFF)
        elif op == 14 and rt == 12:
            lo_ = _s16(w & 0xFFFF)
        elif op == 48 and rt == freg and hi is not None and lo_ is not None:
            return round(struct.unpack(">f", dol.read(((hi << 16) + lo_ + _s16(w & 0xFFFF)) & 0xFFFFFFFF, 4))[0], 6)
    return None


def read_back(game):
    """A built game (folder with sys/main.dol, or a Dol) -> {item id: {"speed": x stock, "gravity": per frame or None
    (stock), "bounce": (factor, minimum hop) or None (stock)}} for the thrown-ball items the item hooks know (our
    Koopalings' and Bill's, and new or edited ones), read from the hooks' own constants. Items the hooks don't list
    (the stock six, Ice unless edited) aren't in it."""
    import sys
    from pathlib import Path
    sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
    from dol import Dol
    import koopa_items as k
    dol = game if isinstance(game, Dol) else Dol(Path(game) / "sys/main.dol")

    def stub(site):
        w = dol.u32(site)
        assert w >> 26 == 18, f"0x{site:08X} isn't patched (no item hooks in this build)"
        off = w & 0x03FFFFFC
        return (site + (off - 0x04000000 if off & 0x02000000 else off)) & 0xFFFFFFFF
    speed = {v: _float_at(dol, b, 0) for v, b in _chain(dol, stub(k.SPEED)).items()}
    gravity = {v: _float_at(dol, b, 1) for v, b in _chain(dol, stub(k.GRAVITY)).items()}
    bounce = {v: (_float_at(dol, b, 2), _float_at(dol, b, 0)) for v, b in _chain(dol, stub(k.BOUNCE_AT)).items()}
    ids = sorted(set(speed) | set(gravity) | set(bounce))
    return {v: {"speed": speed.get(v) or 1.0, "gravity": gravity.get(v), "bounce": bounce.get(v)} for v in ids}


# --- items from a star move (git-95's star swings: star_shower.SHOWERS) -------------------------------------------
STAR_DROPS = {"star-bits": "the star-bit pool (star_shower's 36 swing bits, starbits_item.LAYOUT['drop'])"}


def star_spawn(item, spots, height, start, every, stay, when="contact", at="landing_forecast"):
    """A star move's shower of `item` (a creation or a customs spec) -> a star_shower.SHOWERS row: {spots, height,
    start, every, stay, drop}, drop a STAR_DROPS key for drop_address(). What the pool can hold without new code:
    star bits, with this build's Star Bits values (ours, or Star Bits edited: the pool shares one set of values).
    Anything else (rings, thrown balls, a star-bit item with values of its own) needs a second pool: refused, in
    plain words."""
    name = item.get("name", "")
    ours = preset_of(name)
    rings = ring_values(item)
    if rings:                                            # a ring item's rings (Wendy's, or a new ring item's)
        if when != "contact" or at != "landing_forecast":
            raise blocks.Invalid(f"{name}: a shower starts at contact, around where the ball will land, for now")
        return {"spots": [tuple(p) for p in spots], "height": height, "start": start, "every": every, "stay": stay,
                "drop": f"rings:{name}", "pool": dict(rings, count=len(spots))}
    if ours != "star-bits":
        chassis = ((item.get("blocks") or {}).get("item") or {}).get("chassis") or item.get("chassis")
        what = "star bits" if chassis == "lob-hazards" else "that item"
        raise blocks.Invalid(f"{name or 'this item'}: a star move can drop Star Bits for now, or a ring item's rings; {what} from a star move "
                             f"needs a pool of its own (to change what the shower drops, edit Star Bits)")
    if when != "contact" or at != "landing_forecast":
        raise blocks.Invalid(f"{name}: a shower starts at contact, around where the ball will land, for now")
    return {"spots": [tuple(p) for p in spots], "height": height, "start": start, "every": every, "stay": stay,
            "drop": "star-bits"}


def ring_values(item):
    """A ring item's pool values (Wendy's, edited or not, or a new ring item's), or None for any other item."""
    b = item.get("blocks") or {}
    ch = (b.get("item") or {}).get("chassis") or item.get("chassis")
    ours = preset_of(item.get("name", ""))
    if item.get("ground") and "wander" in item["ground"] and item["ground"].get("wander"):
        g = item["ground"]                               # a customs spec (its values already checked)
    elif ours == "wendy" or (ch == "lob-hazards" and (b.get("spawn") or {}).get("what") == "rings"):
        problems = []
        g = ground("wendy", b if b else preset("wendy")["blocks"], problems.append)["ground"]
        if problems:
            raise blocks.Invalid(f"{item.get('name')}: " + "; ".join(problems))
    else:
        return None
    return {"speed": g["wander"]["speed"], "wander": g["wander"]["range"], "twist": g["wander"]["twist"],
            "hop": g["hop"]["height"], "frames": g["hop"]["frames"],
            "radius": g["radius"] if g["radius"] is not None else block("wendy", "spawn")["hit"]["radius"],
            "colors": g["colors"]}


_SIZING = []


def sizing():
    """A context in which drop_address gives a placeholder for any key: for measuring hook code before a build
    (creators.swings.hook_bytes; addresses only change constants, not sizes)."""
    from contextlib import contextmanager

    @contextmanager
    def ctx():
        _SIZING.append(1)
        try:
            yield
        finally:
            _SIZING.pop()
    return ctx()


def runners(b):
    """Whether an item (its blocks) knocks runners down: "runner" in its hit targets, else as its chassis
    (blocks.DEFAULT_TARGETS; runner_hits.py)."""
    targets = (b.get("hit") or {}).get("targets")
    return "runner" in (blocks.DEFAULT_TARGETS[b["item"]["chassis"]] if targets is None else targets)


def ids(creations, keep_ours=False):
    """{new item name (lower case): its id} as the build gives them (customs: in the profile's order, from
    FIRST_CUSTOM; ours edited keep theirs and aren't listed): what a character's "batting_item" may name."""
    return {s["name"].strip().lower(): s["id"] for s in customs(creations, keep_ours) if not s["replaces"]}


def resolve(name, creations, keep_ours=False):
    """A character's "batting_item" naming a new item -> its id (None: not one of these creations)."""
    return ids(creations, keep_ours).get(str(name).strip().lower())


def burns(b):
    """Whether a thrown ball's hit shows the Fireball's burning look: look.burn, else only with the Fireball look."""
    look = b.get("look") or {}
    return look["burn"] if look.get("burn") is not None else (look.get("model") or "fireball") == "fireball"


def burn_off(customs=(), skip=frozenset()):
    """Thrown-ball item ids hit without the burning look: our presets that don't look like a Fireball (Lemmy's
    circus ball, the Bullet Bill), less those edited (skip), and the specs'."""
    ours = {PRESET_IDS[p] for p in PRESET_IDS if PRESET_IDS[p] not in skip
            and preset(p)["blocks"]["item"]["chassis"] == "thrown-ball" and not burns(preset(p)["blocks"])}
    return sorted(ours | {s["id"] for s in customs if s.get("chassis") == "thrown-ball" and not s.get("burn", True)})


def runners_off(customs=(), skip=frozenset()):
    """Item ids that don't hit runners: our items as their presets have it (the Bullet Bill), less those edited
    (skip: their ids; their specs say), and the specs' (runner_hits.apply's off)."""
    return sorted({PRESET_IDS[p] for p in PRESET_IDS if PRESET_IDS[p] not in skip and not runners(preset(p)["blocks"])}
                  | {s["id"] for s in customs if not s["runners"]})


def drop_address(key):
    """A SHOWERS row's drop routine in this build (after starbits_item.apply): r3 = bit index, f1..f4 = x, y, z,
    ground."""
    if _SIZING:
        return 0x80800000
    import sys
    sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
    if key.startswith("rings:"):                         # a ring shower pool (wendy_rings, after its apply)
        import wendy_rings
        fn = next((p.get("drop_fn") for p in wendy_rings.LAYOUT.get("pools", ()) if p.get("drop") == key), None)
        assert fn, f"no ring pool for {key!r} in this build (ring showers need the Koopalings' items on)"
        return fn
    assert key in STAR_DROPS, f"star drop {key!r} (one of {sorted(STAR_DROPS)} or rings:<item>)"
    import starbits_item
    assert starbits_item.LAYOUT.get("drop"), "star bits aren't in this build (new-roulette-item)"
    return starbits_item.LAYOUT["drop"]
