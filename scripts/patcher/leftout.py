"""What the player's picks need that's off, and what a patch left out (git-b6; Nick's name.iso: a new character came
out without its voice, because nothing ticked Voices and the patch only logged it).

character_needs asks the build itself: charbuild.degrade is what leaves a character's keys out when their feature is
off, so each feature the character loses something without is found by running degrade with only that feature off.
The window ticks those with the character, lists them in its pre-run prompt when they're off, and repeats the patch's
left-out lines at the end of Progress (left_out).
"""
import copy

# degrade's key names, in the window's words
WORDS = {"voice": "voice", "piranha_plants": "Piranha Plants", "minimap_decoys": "mini-map decoys",
         "batting_item": "batting item", "always_item": "always gets their item", "item_ability": "item card label",
         "hitting_ability": "hitting card label", "running_ability": "running card label",
         "batter_star": "star when coming up to bat", "chance_cheer": "chance cheer", "chance cheer": "chance cheer",
         "star pitch": "star pitch", "fielding ability": "Tantrum Toss", "star swing": "star swing"}


def _what(line):
    """degrade's "left out    Name: voice (voices), star pitch 14 (pitch-path): feature off" -> ["voice", ...]."""
    body = line.split(": ", 1)[1].rsplit(": feature off", 1)[0]
    out = []
    for part in body.split(", "):
        key = part.split(" (", 1)[0]
        key = next((k for k in sorted(WORDS, key=len, reverse=True) if key == k or key.startswith(k + " ")), key)
        out.append(WORDS.get(key, key.replace("_", " ")))
    return out


def character_needs(definitions, features):
    """{character name: {feature: [what it loses without it, in plain words]}} for definitions (characters/*.json
    form), over the feature ids `features` (the patcher's registry)."""
    import charbuild
    out = {}
    try:
        normalized = charbuild.normalize([copy.deepcopy(d) for d in definitions])
    except Exception:                   # the build refuses it later, with its own message
        return out
    for c in normalized:
        need = {}
        for f in features:
            lines = charbuild.degrade(copy.deepcopy(c), on=lambda g, f=f: g != f)
            if lines:
                need[f] = _what(lines[0])
        out[c["name"]] = need
    return out


def left_out(log):
    """The lines of a patch's output the player should see at the end: its notes and each character's left-out
    keys (not the build's own defaults for characters that aren't in this patch)."""
    out = []
    for line in log.splitlines():
        s = line.strip()
        if s.startswith("note: "):
            out.append(s[len("note: "):])
        elif s.startswith("left out ") and s.endswith(": feature off"):
            name = s[len("left out"):].split(":", 1)[0].strip()
            out.append(f"{name}: {', '.join(_what(s))} left out (its feature isn't ticked)")
    return list(dict.fromkeys(out))
