"""Replay and contact-freeze tweaks (Nick, 2026-09-28: "put the trivial ones in the patcher beta"). docs/replay.md.
Each is its own feature (Game options), all data words or one instruction in the clean DOL:

  no-replays          FUN_8016D42C (picks the replay kind, once a play) -> blr: the kind stays 0, no replay.
  replay-slow-motion  the one stock slow-motion replay (807A03D8, a close play at the plate): its `SPEED 2` and
                      `WAIT 50`. Options "speed" (the game runs 1/speed; 1 = no slow motion) and "frames" (real frames).
  replay-camera       the replays' shared "after contact" subroutine 8079FEF0 (RANDCALL: TV cameras or the chase
                      camera, at random): zeroing one target leaves the other (FUN_8036C8B0 picks among the non-zero).
                      Option "camera": "tv" or "chase".
  contact-freeze      the models' freeze on bat contact (M+0xA, FUN_800BD2F0): the 5 frame counts per 60 / 50 Hz row
                      (stock 60 Hz: 2, 2, 30, 2, 20) times option "percent" (0 = no freeze, 100 = stock).
"""
import struct

SLOW_SPEED, SLOW_FRAMES = 0x807A0430, 0x807A0438        # SPEED 2 / WAIT 50 words (the ops at +0x2C / +0x34)
AFTER_CONTACT = 0x8079FEF0                              # RANDCALL 28, TV (8079FF10), chase (8079FF18), 0, 0, 0
TV_TARGET, CHASE_TARGET = 0x8079FEF8, 0x8079FEFC
REPLAY_PICK = 0x8016D42C                                # FUN_8016D42C's first instruction (stwu r1,-0x30(r1))
FREEZE_ROWS = (0x806277B6, 0x806277B6 + 0x1A)           # 5 shorts each: 60 Hz, 50 Hz
BLR = 0x4E800020

CLEAN = {SLOW_SPEED - 4: 0x47E, SLOW_SPEED: 2, SLOW_FRAMES - 4: 0x3E8, SLOW_FRAMES: 50, AFTER_CONTACT: 0xD,
         TV_TARGET: 0x8079FF10, CHASE_TARGET: 0x8079FF18, REPLAY_PICK: 0x9421FFD0}
CAMERAS = {"tv": "TV cameras", "chase": "chase camera"}
LIMITS = {"speed": (1, 8), "frames": (1, 600), "percent": (0, 400)}
DEFAULTS = {"speed": 3, "frames": 90, "camera": "tv", "percent": 200}
FEATURES = ("no-replays", "replay-slow-motion", "replay-camera", "contact-freeze")


def check(name, value):
    """An option's value, checked: an int in LIMITS, or a CAMERAS key. Raises ValueError in plain words."""
    if name == "camera":
        v = str(value).strip().lower()
        if v not in CAMERAS:
            raise ValueError(f"replay camera: {value!r} isn't one of {', '.join(CAMERAS)}")
        return v
    lo, hi = LIMITS[name]
    try:
        v = int(str(value).strip(), 0)
    except ValueError:
        raise ValueError(f"replay {name}: {value!r} isn't a whole number") from None
    if not lo <= v <= hi:
        raise ValueError(f"replay {name}: {v} is outside {lo}..{hi}")
    return v


def _clean(dol, addr):
    got = dol.u32(addr)
    assert got == CLEAN[addr], f"0x{addr:08X} is 0x{got:08X}, not the clean 0x{CLEAN[addr]:08X}"


def apply(dol, on, speed=None, frames=None, camera=None, percent=None):
    """on: the feature ids (FEATURES) to apply; the options as check() returns them (None: DEFAULTS)."""
    log = []
    if "no-replays" in on:
        _clean(dol, REPLAY_PICK)
        dol.write(REPLAY_PICK, struct.pack(">I", BLR))
        log.append("No instant replays")
    if "replay-slow-motion" in on:
        speed = DEFAULTS["speed"] if speed is None else check("speed", speed)
        frames = DEFAULTS["frames"] if frames is None else check("frames", frames)
        for a in (SLOW_SPEED - 4, SLOW_SPEED, SLOW_FRAMES - 4, SLOW_FRAMES):
            _clean(dol, a)
        dol.write(SLOW_SPEED, struct.pack(">I", speed))
        dol.write(SLOW_FRAMES, struct.pack(">I", frames))
        log.append(f"Replay slow motion: 1/{speed} speed for {frames} frames (stock 1/2 for 50)")
    if "replay-camera" in on:
        camera = DEFAULTS["camera"] if camera is None else check("camera", camera)
        for a in (AFTER_CONTACT, TV_TARGET, CHASE_TARGET):
            _clean(dol, a)
        dol.write(CHASE_TARGET if camera == "tv" else TV_TARGET, b"\0\0\0\0")
        log.append(f"Replay camera after contact: always the {CAMERAS[camera]}")
    if "contact-freeze" in on:
        percent = DEFAULTS["percent"] if percent is None else check("percent", percent)
        rows = []
        for row in FREEZE_ROWS:
            old = struct.unpack(">5h", dol.read(row, 10))
            new = [min(0x7FFF, (n * percent + 50) // 100) for n in old]
            dol.write(row, struct.pack(">5h", *new))
            rows.append(f"{list(old)} -> {new}")
        log.append(f"Contact freeze {percent}%: 60 Hz {rows[0]}, 50 Hz {rows[1]}")
    return log
