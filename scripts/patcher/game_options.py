"""Game options: CPU vs CPU, Match seed, Start at captain select, Start in a game with your own teams, the replay
and contact-freeze tweaks (replay_tweaks.py, docs/replay.md), the box score's time between innings (inning_break.py)
and the menu background color, in one small window with Save at the bottom right (widgets.save_bar, like the beta's other
popups). A player
asked the Characters Beta for what the full patcher has: the beta page's "Game options..." opens it (beta_window.py);
the full patcher's Features tab has the same switches, and its "Start in a game" row opens this window for the teams.

The window edits copies: Save puts them in the App (fvars "cpu-vs-cpu", "match-seed", "boot-captain-select",
"boot-game", "menu-color"; app.color; app.seed; app.boot_game), Cancel drops them. Only the features the edition offers are shown.
app.boot_game: the profile's options["boot-game"], {"captains": [a, b], "teams": [[up to 8], [up to 8]], "stadium": 0,
"night": false} (names as the window shows them; charbuild.boot_game_args finds them in the build; quickboot fills
empty spots; the Stadium box offers the game's own Exhibition stadiums at the times of day they have, stadiums()), and
"level": the CPU level (the CPU level box, next to Stadium: Rookie .. All-Star, and Level 5 / Level 6 when the build
has the CPU levels, level-5: levels(); captain select asks it, and Start in a game skips captain select).
Start at captain select and Start in a game are one or the other (charbuild: the game wins).
Start at captain select has its own Stadium box (Nick: "start at captain select needs to let me pick a stadium"), the
same list as Start in a game's: app.boot_captain, the profile's options["boot-captain-select"], {"stadium": 0,
"night": false} (None: Mario Stadium by day, what it always played in). That path skips the main menu's stadium select,
so quickboot writes the pick where the stadium select would (setup +5..+7) and the game after captain select plays there.
Each team saves to and loads from its own file (Nick: "save and import teams, one team at a time"): a .slgteam, JSON
{"format": "sluggers-team", "version": 1, "captain": name, "players": [8 names, null for "filled for you"]}, by the
names the window shows; loading one keeps the spots whose character isn't in this game empty and says who.
Version 2 adds the lineup (Nick: "make the team files allow for lineup and positions setting"): "order", the 9 in
batting order (captain included; null for a "filled for you" spot), and "positions", {name: "P" | "C" | "1B" | ...}.
A version 1 file (or no "order" / "positions") keeps the game's own order and positions. Each team's column sets both
in place, by drag and drop (Nick: "Lineup should not be a separate window, it should be drag and drop"; build_board):
under the team's boxes, its 9 players in batting order (the captain too) with their positions; drag a player up or
down to move him in the order, onto another player's Plays box to swap their positions (or pick one in his own small
box: someone else's position swaps them, as the game's own screen does), or between the lineup and the bench to swap a
starter with a bench player. Automatic gives the order and positions back to the game.
The lineup is kept by team spot (captain, Player 2..9), so changing a player in a box keeps that spot's batting slot
and position. options["boot-game"] carries it as "lineups": [[9 names or null] or null, ...] and "positions":
[{name: pos}, {}] (charbuild.boot_game_args -> quickboot's lineup / positions).
Version 3 adds the bench (docs/bench.md): "bench", up to 5 names, the first the DH (bench slot 0), and "fo", who sits
for the DH (the positions screen's 10th lineup slot, "FO", fielder only; files from before the rename say "dr", still
read): one of the captain + 8 (the captain too), or the DH
himself for no DH; left out, the DH bats for whoever plays P. A file is version 3 only when it has a bench; versions
1 and 2 load with an empty bench. The team's bench rows (DH, then B2..B5, typed or picked; drag them to reorder) and its
"Fielder only (FO)" box set them; read_bench checks a file's (a name not in this game, on the team already, twice, past 5, a Mii, or an FO who
isn't on the team is left out, and the notes say so). options["boot-game"] carries them as "benches": [[names],
[names]] and "dr": [name or null, ...]; charbuild.boot_game_args turns them into bench.apply's preset and each team's
DHSEL, so the started game has the bench, the DH and the right player sitting (once per power-on, as the teams).
"""
import json
import tkinter as tk
import style
from pathlib import Path
from tkinter import filedialog, ttk

import fit
import widgets

TITLE = "Game options"
FEATURES = ("cpu-vs-cpu", "match-seed", "boot-captain-select", "boot-game", "no-replays", "replay-slow-motion",
            "replay-camera", "contact-freeze", "inning-break-time", "bench", "menu-color")
REPLAY_FEATURES = ("no-replays", "replay-slow-motion", "replay-camera", "contact-freeze",   # replay_tweaks.FEATURES,
                   "inning-break-time")                                                   # and inning_break.py's
LABELS = {"bench": "Bench players (up to 5 per team: substitutes and pinch runners)",
          "no-replays": "No instant replays",
          "replay-slow-motion": "Slower replay slow motion (the close play at the plate)",
          "replay-camera": "Replay camera after the hit",
          "contact-freeze": "Contact freeze (the pause when the bat meets the ball)",
          "inning-break-time": "Box score between innings: how long it shows",
          "cpu-vs-cpu": "CPU vs CPU (watch the computer play both sides)",
          "match-seed": "Match seed (type one to replay a CPU vs CPU game later; blank: a new game every match)",
          "boot-captain-select": "Start at captain select (skip the title and menus)",
          "boot-game": "Start in a game with these teams (once each time you turn the game on; then the "
                       "game's own menus)",
          "menu-color": "Menu background color"}
# each switch's thanks, right under it (Nick: "all thank yous need to be near the feature"): its CREDITS.md
# "Thanks, part by part" line (credits.tab_line)
THANKS = {"cpu-vs-cpu": "CPU vs CPU"}
ONE_BOOT = {"boot-captain-select", "boot-game"}     # one start or the other
# the game's 12 captains in its captain list's order (captains.STOCK_CAPTAIN_NAMES) with their ids: a captain who isn't
# one of them takes the first of these not picked (quickboot._ids' captain-list takeover)
STOCK_CAPTAINS = (("Mario", 0x00), ("Luigi", 0x01), ("Donkey Kong", 0x02), ("Diddy Kong", 0x03), ("Peach", 0x04),
                  ("Daisy", 0x05), ("Yoshi", 0x06), ("Bowser", 0x09), ("Wario", 0x0A), ("Waluigi", 0x0B),
                  ("Birdo", 0x11), ("Bowser Jr.", 0x13))
STOCK_PLAYERS = 0x47                    # stock ids 0..0x46 play (quickboot's filler: every stock player)
TEAM_SIZE = 8                           # besides the captain
AUTO = "(filled for you)"
DEFAULT = {"captains": ["Mario", "Bowser"], "teams": [[], []], "stadium": 0, "night": False, "level": 2}
CAPTAIN_DEFAULT = {"stadium": 0, "night": False}     # Start at captain select's stadium: Mario Stadium by day
# the CPU level box (quickboot.LEVELS): the game's four, then the CPU levels feature's two (level-5 ticked)
LEVEL_NAMES = {1: "Rookie", 2: "Veteran", 3: "Pro", 4: "All-Star", 5: "Level 5 (Superstar)", 6: "Level 6 (Legend)"}
CPU_LEVELS_FEATURE = "level-5"
TEAM_EXT = ".slgteam"
TEAM_FORMAT = "sluggers-team"
TEAMS_DIR = Path(__file__).resolve().parents[2] / "teams"     # beside the program (package.PLAYER_FOLDERS)
POSITIONS = ("P", "C", "1B", "2B", "3B", "SS", "LF", "CF", "RF")   # quickboot.POSITIONS (the game's record +0xC)
POS_AUTO = "auto"                       # a Plays box with no position: the game's pick
DRAG_OVER = "#cce4f7"                   # the lineup row a dragged player would drop on
BODY_HEIGHT = 640                       # the window's part above Save asks no more (it scrolls): 860 x 760 budget
BENCH_SIZE = 5                          # bench.NB: bench slot 0 (the first) is the DH
NO_BENCH = "(nobody)"
DR_P, DR_OFF = "Whoever plays P", "No DH (the DH sits)"    # the FO box's first two (dr None / "off")


# the replay tweaks' option boxes: {feature: [(option, label, choices or None: a number box, note)]}
# (replay_tweaks.LIMITS / CAMERAS; the values are App.replay's StringVars, or the window's copies)
REPLAY_ROWS = {"replay-slow-motion": [("speed", "Speed: 1 /", None, "(stock 2)"),
                                      ("frames", "for", None, "frames (stock 50; 60 = one second)")],
               "replay-camera": [("camera", "Always the", "camera", "(stock: one of the two at random)")],
               "contact-freeze": [("percent", "Length:", None, "% of stock (0 = no freeze, 100 = stock)")],
               "inning-break-time": [("seconds", "Box score between innings:", None,
                                      "seconds (0.5 to 30; stock: one camera pass, about 3.4 to 7.7 seconds by "
                                      "stadium; A skips it either way)")]}
SECONDS_STOCK = "stock"                 # inning_break.STOCK: the seconds box's default (builds nothing new)
CAMERA_WORDS = {"tv": "TV cameras", "chase": "chase camera"}


def _defaults():
    """replay_tweaks.DEFAULTS and inning-break-time's "seconds" (stock)."""
    import replay_tweaks
    return dict(replay_tweaks.DEFAULTS, seconds=SECONDS_STOCK)


def replay_vars():
    """{option: StringVar} at replay_tweaks.DEFAULTS and "seconds": stock (App.replay; the camera as its words)."""
    return {k: tk.StringVar(value=CAMERA_WORDS[v] if k == "camera" else str(v)) for k, v in _defaults().items()}


def replay_value(fid, variables):
    """(True, {option: value} for the profile) or (False, what's wrong), for one replay feature."""
    import replay_tweaks
    out = {}
    for name, *_ in REPLAY_ROWS.get(fid, ()):
        v = variables[name].get().strip()
        if name == "camera":
            v = {w: k for k, w in CAMERA_WORDS.items()}.get(v, v)
        if name == "seconds":                                   # inning_break.check: 0.5..30, or stock
            import inning_break
            try:
                n = inning_break.check(v)
            except ValueError:
                return False, ("Box score between innings: type a number of seconds from 0.5 to 30, or stock.")
            out[name] = SECONDS_STOCK if n is None else (int(n) if n == int(n) else n)
            continue
        try:
            out[name] = replay_tweaks.check(name, v)
        except ValueError as e:
            lo, hi = replay_tweaks.LIMITS.get(name, (None, None))
            return False, (f"{LABELS[fid].split(' (')[0]}: type a whole number from {lo} to {hi}." if lo is not None
                           else str(e))
    return True, out


def set_replay(variables, fid, opts):
    """A profile's options[fid] into the StringVars (missing ones: the defaults)."""
    for name, *_ in REPLAY_ROWS.get(fid, ()):
        v = (opts or {}).get(name, _defaults()[name])
        v = SECONDS_STOCK if name == "seconds" and v is None else v
        variables[name].set(CAMERA_WORDS.get(v, v) if name == "camera" else str(v))


def replay_row(parent, fid, variables):
    """The option boxes under a replay feature's tick; returns (row, the boxes to enable / disable)."""
    row = ttk.Frame(parent, padding=(24, 2, 0, 0))
    row.pack(anchor="w")
    boxes = []
    for name, label, choices, note in REPLAY_ROWS[fid]:
        ttk.Label(row, text=label).pack(side="left", padx=(0, 4))
        if choices == "camera":
            box = ttk.Combobox(row, textvariable=variables[name], values=list(CAMERA_WORDS.values()), width=14,
                               state="readonly")
        else:
            box = ttk.Entry(row, textvariable=variables[name], width=5)
        box.pack(side="left")
        ttk.Label(row, text=note, foreground=widgets.GREY).pack(side="left", padx=(4, 10))
        boxes.append(box)
    return row, boxes


def team_file(captain, team, order=None, pos=None, bench=None, dr=None):
    """A team as the .slgteam file's JSON (players: 8 spots, None for "filled for you"). order: the 9 team spots
    (0 = captain, 1..8 = Player 2..9) in batting order, or None (the game's); pos: {spot: "P", ...}. With either:
    version 2, "order" / "positions" by name. bench: up to 5 names (the first the DH); dr: who sits for the DH, a team
    spot, "off" (the DH sits: no DH) or None (whoever plays P). With a bench: version 3, "bench" and "fo" by name."""
    team = [n if n and n != AUTO else None for n in team][:TEAM_SIZE]
    team = team + [None] * (TEAM_SIZE - len(team))
    out = {"format": TEAM_FORMAT, "version": 1, "captain": captain, "players": team}
    who = [captain] + team
    if order or pos:
        out["version"] = 2
        out["order"] = [who[k] for k in (order or range(TEAM_SIZE + 1))]
        out["positions"] = {who[k]: p for k, p in sorted((pos or {}).items(), key=lambda kp: POSITIONS.index(kp[1]))
                            if who[k]}
    bench = [n for n in (bench or []) if n and n != NO_BENCH][:BENCH_SIZE]
    if bench:
        out["version"] = 3
        out["bench"] = bench
        sits = dr_name(dr, who, bench)
        if sits:
            out["fo"] = sits
    return out


def dr_name(dr, who, bench):
    """Who sits for the DH by name (None: whoever plays P): dr a team spot of who (captain + 8, None / AUTO for empty
    spots), "off" (the DH himself) or None."""
    if not bench or dr is None:
        return None
    if dr == "off":
        return bench[0]
    n = who[dr] if isinstance(dr, int) and 0 <= dr < len(who) else None
    return n if n and n != AUTO else None


def is_mii(name):
    """A Mii's name (the game's "Red Mii (M)" ...): never on the bench (docs/bench.md, Known limits)."""
    return " mii (" in f" {str(name).strip().lower()}"


def read_bench(data, captain, team, names=None):
    """(bench: up to 5 names, the first the DH; dr: a team spot, "off" or None; [notes]) from a .slgteam's "bench"
    and "fo" (or "dr", its name before the FO rename; version 3; others: ([], None, [])), matched to captain + team (the 8 as loaded, AUTO for empty spots).
    names: who can play in this game (players()); None: not checked (the profile's own, which problems() checks).
    A name not in the game, on the team already, twice, past 5 or a Mii is left off the bench; an FO who isn't the DH
    or one of the team (the captain too) leaves the DH batting for whoever plays P. The notes say so."""
    given = data.get("bench") if isinstance(data, dict) else None
    if not isinstance(given, list) or not given:
        return [], None, []
    who = [str(n).strip().lower() if n and n != AUTO else None for n in [captain] + list(team)]
    canon = {str(n).strip().lower(): n for n in names} if names is not None else None
    bench, notes = [], []
    off = {"a Mii": [], "not in your game": [], "on the team already": [], "twice": [], f"more than {BENCH_SIZE}": []}
    for n in given:
        if n in (None, "", NO_BENCH):
            continue
        key = str(n).strip().lower()
        why = ("a Mii" if is_mii(n) else "not in your game" if canon is not None and key not in canon
               else "on the team already" if key in who else "twice" if key in [b.lower() for b in bench]
               else f"more than {BENCH_SIZE}" if len(bench) >= BENCH_SIZE else None)
        if why:
            off[why].append(str(n))
        else:
            bench.append(canon[key] if canon is not None else str(n).strip())
    for why, gone in off.items():
        if gone:
            notes.append(f"Bench: left off ({why}): " + ", ".join(gone) + ".")
    dr, sits = None, data.get("fo", data.get("dr"))
    if bench and sits not in (None, ""):
        key = str(sits).strip().lower()
        if key == bench[0].lower():
            dr = "off"
        elif key in who:
            dr = who.index(key)
        else:
            notes.append(f"Fielder only (FO): {sits} isn't on this team or its DH; the DH bats for whoever plays P.")
    return bench, dr, notes


def read_lineup(data, captain, team):
    """(order: the 9 spots in batting order or None, {spot: position}, [notes]) from a .slgteam's "order" and
    "positions", matched by name to captain + team (the 8 names as loaded, AUTO for empty spots; a null in the order
    is the next empty spot). A name twice or not on the team is left out and the spots left over fill the rest in the
    team's order; a position twice keeps the first (the notes say so). A version 1 file: (None, {}, [])."""
    who = [str(n).strip().lower() if n and n != AUTO else None for n in [captain] + list(team)]
    notes = []
    order = None
    want = data.get("order") if isinstance(data, dict) else None
    if isinstance(want, list) and want:
        order, left = [], list(range(TEAM_SIZE + 1))
        gone = []
        for n in want[:TEAM_SIZE + 1]:
            key = str(n).strip().lower() if n else None
            k = next((k for k in left if who[k] == key), None)
            if k is None:
                if key:
                    gone.append(str(n))
                continue
            left.remove(k)
            order.append(k)
        if left:
            notes.append("Batting order: " + (("not on this team: " + ", ".join(gone) + "; ") if gone else "")
                         + f"{len(left)} spot{'s' if len(left) > 1 else ''} filled in the team's order.")
        order += left
    pos = {}
    given = data.get("positions") if isinstance(data, dict) else None
    if isinstance(given, dict):
        twice, off = [], []
        for n, p in given.items():
            p = str(p).strip().upper()
            k = next((k for k in range(TEAM_SIZE + 1) if who[k] and who[k] == str(n).strip().lower()), None)
            if p not in POSITIONS or k is None:
                off.append(str(n))
            elif p in pos.values():
                twice.append(f"{n} ({p})")
            else:
                pos[k] = p
        if off:
            notes.append("Positions left to the game for: " + ", ".join(off) + ".")
        if twice:
            notes.append("Position picked twice, left to the game: " + ", ".join(twice) + ".")
    return order, pos, notes


def read_team(data, caps, names):
    """(captain or None, 8 player names with AUTO for empty spots, [names not in this game]) from a .slgteam's JSON.
    Raises ValueError with a plain message for a file that isn't a team."""
    if not isinstance(data, dict) or data.get("format") != TEAM_FORMAT or not isinstance(data.get("players"), list):
        raise ValueError("That file isn't a saved team (.slgteam).")
    missing = []
    cap = data.get("captain")
    if cap not in caps:
        missing += [f"{cap} (captain)"] if cap else []
        cap = None
    team = []
    for n in list(data["players"])[:TEAM_SIZE] + [None] * (TEAM_SIZE - len(data["players"])):
        if n and n not in names:
            missing.append(n)
        team.append(n if n and n in names else AUTO)
    return cap, team, missing


def stadiums():
    """{"Wario City (night)": (2, True), ...}: the game's own Exhibition stadiums by day and at night, in the select
    map's order, only the times of day each has (quickboot.STADIUMS; imported here: it ships with boot-game)."""
    import quickboot
    return {quickboot.stadium_name(i, n): (i, n) for i in quickboot.STADIUMS for n in (False, True)
            if quickboot.stadium_ok(i, n)}


def has_cpu_levels(app):
    """Whether the build has CPU levels 5 and 6 (the level-5 feature offered and ticked)."""
    return CPU_LEVELS_FEATURE in app.fvars and app.fvars[CPU_LEVELS_FEATURE].get()


def levels(app):
    """{"Pro": 3, ...}: the CPU levels Start in a game can use in this build (levels 5 and 6 with the CPU levels)."""
    return {n: lv for lv, n in LEVEL_NAMES.items() if lv <= 4 or has_cpu_levels(app)}


def players(app):
    """[(name, id)] of who can play: the stock players, then the characters ticked into the build that have their
    own id (new characters, recolors, imports; app.roster)."""
    return [(n, i) for n, kind, _, i in app.roster() if i is not None and (kind != "stock" or i < STOCK_PLAYERS)]


def captains(app):
    """[(name, id)]: the game's 12 captains, then the new characters ticked into the build (a new captain takes a
    stock captain's spot in the captain list: replaced()). With the captains changed (the Captains tab, or the beta's
    Captains section: options.captains), this build's captains in their captain-list order (charbuild then gives
    quickboot their own indices: captain_index="captains")."""
    tab = getattr(app, "captains_tab", None)
    option = tab.current() if tab is not None and "captains" in app.picked() else None
    if option is not None:
        import captains as cap
        import captain_editor
        p = cap.plan(option, captain_editor.build_chars(app), None, swings=False)
        if not p["errors"]:
            names = {i: n for n, _, _, i in app.roster() if i is not None}
            names.update({i: n for n, i in STOCK_CAPTAINS})
            return [(names.get(cid, f"0x{cid:02X}"), cid) for cid in p["table"]]
    return list(STOCK_CAPTAINS) + [(n, i) for n, kind, _, i in app.roster() if kind == "new" and i is not None]


def replaced(caps):
    """{new captain's id: the stock captain whose spot it takes} for two captain ids (quickboot._ids' order)."""
    spare = [n for n, i in STOCK_CAPTAINS if i not in caps]
    stock = {i for _, i in STOCK_CAPTAINS}
    return {c: spare.pop(0) for c in caps if c not in stock}


def problems(app, option):
    """What stops the teams, in words ([] when fine): a character picked twice, or not in the build."""
    ids = {n.strip().lower(): i for n, i in captains(app) + players(app)}
    picked = [c for c in option["captains"]] + [c for t in option["teams"] for c in t] \
        + [c for b in option.get("benches") or () for c in b]
    out = []
    if (option.get("stadium", 0), bool(option.get("night"))) not in stadiums().values():
        import quickboot
        where, night = option.get("stadium"), bool(option.get("night"))
        name = quickboot.stadium_name(where, night) + ("" if night or where not in quickboot.STADIUMS else " by day")
        out.append(f"The game has no {name}: pick a stadium from the list.")
    level = option.get("level", DEFAULT["level"])
    if level not in levels(app).values():
        out.append(f"{LEVEL_NAMES.get(level, f'CPU level {level}')} isn't in your game (it needs the CPU levels): "
                   "pick a CPU level from the list.")
    gone = [c for c in picked if str(c).strip().lower() not in ids]
    if gone:
        out.append("Not in your game now: " + ", ".join(gone) + ". Pick someone else.")
    caps = {n.strip().lower() for n, _ in captains(app)}
    off = [c for c in option["captains"] if str(c).strip().lower() in ids and str(c).strip().lower() not in caps]
    if off:                                             # (e.g. a stock captain another one replaced)
        out.append("Not a captain in your game now: " + ", ".join(off) + ". Pick a captain from the list.")
    seen, twice = set(), []
    for c in picked:
        i = ids.get(str(c).strip().lower())
        if i is not None and i in seen and c not in twice:
            twice.append(c)
        seen.add(i)
    if twice:
        out.append("Picked twice: " + ", ".join(twice) + ". Each character can play once (the benches too).")
    miis = [c for b in option.get("benches") or () for c in b if is_mii(c)]
    if miis:
        out.append("A Mii can't be on the bench: " + ", ".join(miis) + ".")
    return out


# The fielder-spots controls, exactly as they play (fielder_spots.py; checked in Dolphin 2026-09-29: both screens, B then A
# and A then B). Start in a game skips the positions screen on its first game, so the in-game way is spelled out too.
FIELDERS_NOTE = ("You can also move where your fielders start (not the pitcher or catcher): point the Wii Remote at a "
                 "fielder, hold A and B together and move the pointer; let go to drop him there (drop him back on his "
                 "own spot to undo). Before a game: on the batting order and positions screen (Start in a game skips "
                 "it). During a game, when your team is fielding: press + before a pitch, pick Change the defense "
                 "(the second icon), drag him, then OK.")


class Window:
    def __init__(self, app):
        self.app = app
        self.shown = [f for f in FEATURES if f in app.fvars]
        self.win = win = tk.Toplevel(app.root)
        style.title(win, TITLE)
        win.transient(app.root)
        bar = widgets.save_bar(win, self.save, win.destroy)
        self.problem = widgets.status(ttk.Label(bar, text="", foreground=widgets.RED, wraplength=460, justify="left"))
        self.problem.pack(side="left", fill="x", expand=True)
        self.scroll = widgets.Scrolled(win, height=BODY_HEIGHT)    # (the teams' lineups make it tall: it scrolls)
        self.scroll.pack(fill="both", expand=True)
        body = ttk.Frame(self.scroll.inner, padding=(12, 10, 12, 0))
        body.pack(fill="both", expand=True)
        self.body = body
        self.on = {f: tk.BooleanVar(value=app.fvars[f].get()) for f in self.shown}
        self.checks = {}
        for f in self.shown:
            self.checks[f] = ttk.Checkbutton(body, text=LABELS[f], variable=self.on[f],
                                             command=lambda f=f: self.toggled(f))
            self.checks[f].pack(anchor="w", pady=(4, 0))
            if f in THANKS:
                import credits
                line = credits.tab_line(THANKS[f])
                if line:
                    fit.label(body, line, grey=True, padding=(24, 0, 0, 0)).pack(fill="x")
            if f == "match-seed":
                self.build_seed(body)
            if f == "boot-captain-select":
                self.build_captain_stadium(body)
            if f == "boot-game":                        # (Nick: the fielders note right under this option)
                self.fielders_note(body)
                self.build_teams(body)
            if f == "menu-color":
                self.build_color(body)
            if f == "bench":                            # (Nick: bench and DH on / off, and say fielders can move)
                self.dh = tk.BooleanVar(value=app.bench_dh.get())
                self.dh_box = ttk.Checkbutton(body, text="Designated hitter (the first bench player bats for the pitcher)",
                                              variable=self.dh)
                self.dh_box.pack(anchor="w", padx=(24, 0), pady=(2, 0))
                if "boot-game" not in self.shown:       # (else it's under Start in a game)
                    self.fielders_note(body)
            if f in REPLAY_ROWS:
                if not hasattr(self, "replay"):         # copies of App.replay (Save puts them back)
                    self.replay = replay_vars()
                    for k, v in app.replay.items():
                        self.replay[k].set(v.get())
                    self.replay_boxes = {}
                self.replay_boxes[f] = replay_row(body, f, self.replay)[1]
        self.toggled(None)
        win.update_idletasks()                          # as wide as the options, as tall as they are up to the budget
        self.scroll.canvas.configure(width=body.winfo_reqwidth(), height=min(body.winfo_reqheight(), BODY_HEIGHT))

    def fielders_note(self, body):
        fit.label(body, FIELDERS_NOTE, grey=True,
                  padding=(24, 0, 0, 0)).pack(fill="x")

    # --- Start at captain select's stadium

    def build_captain_stadium(self, parent):
        """The Stadium box under Start at captain select: the game after captain select plays there."""
        opt = dict(CAPTAIN_DEFAULT, **(getattr(self.app, "boot_captain", None) or {}))
        self.captain_where = opt["stadium"], bool(opt["night"])      # (kept as it is when not listed)
        row = ttk.Frame(parent, padding=(24, 2, 0, 0))
        row.pack(anchor="w")
        ttk.Label(row, text="Stadium").pack(side="left", padx=(0, 6))
        import quickboot
        places = list(stadiums())
        self.captain_stadium = tk.StringVar(value=quickboot.stadium_name(*self.captain_where))
        self.captain_box = ttk.Combobox(row, textvariable=self.captain_stadium, values=places, width=24)
        typeahead(self.captain_box, places)
        self.captain_box.pack(side="left")
        fit.label(parent, "The game you start after picking the teams is played here.", grey=True,
                  padding=(24, 0, 0, 0)).pack(fill="x")

    def captain_option(self):
        """Start at captain select's stadium as the profile's options["boot-captain-select"] (None: the default,
        Mario Stadium by day)."""
        stadium, night = stadiums().get(self.captain_stadium.get(), self.captain_where)
        out = {"stadium": stadium, "night": night}
        return None if out == CAPTAIN_DEFAULT else out

    # --- the teams

    def build_teams(self, parent):
        app = self.app
        opt = dict(DEFAULT, **(getattr(app, "boot_game", None) or {}))
        self.stadium, self.night = opt.get("stadium", 0), bool(opt.get("night"))   # (kept as they are when not listed)
        where = ttk.Frame(parent, padding=(24, 4, 0, 0))                # the stadium, above the teams
        where.pack(anchor="w")
        ttk.Label(where, text="Stadium").pack(side="left", padx=(0, 6))
        import quickboot
        places = list(stadiums())
        self.stadium_var = tk.StringVar(value=quickboot.stadium_name(self.stadium, self.night))
        sb = ttk.Combobox(where, textvariable=self.stadium_var, values=places, width=24)
        typeahead(sb, places)
        sb.pack(side="left")
        self.level = opt.get("level", DEFAULT["level"])                  # (kept as it is when not listed)
        ttk.Label(where, text="CPU level").pack(side="left", padx=(14, 6))
        names = list(levels(app))
        self.level_var = tk.StringVar(value=LEVEL_NAMES.get(self.level, f"level {self.level}"))
        lb = ttk.Combobox(where, textvariable=self.level_var, values=names, width=18)
        typeahead(lb, names)
        lb.pack(side="left")
        box = ttk.Frame(parent, padding=(24, 2, 0, 0))
        box.pack(anchor="w", fill="x")
        self.teams_box = box
        caps = [n for n, _ in captains(app)]
        names = [AUTO] + [n for n, _ in players(app)]
        self.captain_vars, self.team_vars, self.team_heads, self.team_widgets = [], [], [], [sb, lb]
        self.lineups, self.boards, self.drag = [], [], None   # per team: {"order": 9 spots or None, "pos": {spot: "CF"}, "bench", "dr"}
        for t in range(2):
            col = ttk.Frame(box)
            col.grid(row=0, column=t, sticky="nw", padx=(0, 18))
            head = ttk.Label(col, font="SluggersSection")
            head.grid(row=0, column=0, columnspan=2, sticky="w")
            self.team_heads.append(head)
            ttk.Label(col, text="Captain").grid(row=1, column=0, sticky="w", padx=(0, 6))
            cv = tk.StringVar(value=(list(opt["captains"]) + ["Mario", "Bowser"])[t])
            cb = ttk.Combobox(col, textvariable=cv, values=caps, width=20)
            typeahead(cb, caps)
            cb.grid(row=1, column=1, sticky="w", pady=1)
            self.captain_vars.append(cv)
            self.team_widgets.append(cb)
            team = list((list(opt["teams"]) + [[], []])[t])
            vs = []
            for k in range(TEAM_SIZE):
                ttk.Label(col, text=f"Player {k + 2}").grid(row=2 + k, column=0, sticky="w", padx=(0, 6))
                v = tk.StringVar(value=team[k] if k < len(team) and team[k] else AUTO)
                pb = ttk.Combobox(col, textvariable=v, values=names, width=20)
                typeahead(pb, names, empty=AUTO)
                pb.grid(row=2 + k, column=1, sticky="w", pady=1)
                vs.append(v)
                self.team_widgets.append(pb)
                v.trace_add("write", lambda *a: self.teams_changed())
            cv.trace_add("write", lambda *a: self.teams_changed())
            self.team_vars.append(vs)
            self.lineups.append(lineup_from_option(opt, t, [cv.get()] + [v.get() for v in vs]))
            self.boards.append(self.build_board(col, t, 2 + TEAM_SIZE))
            files = ttk.Frame(col)
            files.grid(row=3 + TEAM_SIZE, column=0, columnspan=2, sticky="w", pady=(4, 0))
            for text, cmd in (("Automatic", self.automatic), ("Save team...", self.save_team),
                              ("Load team...", self.load_team)):
                b = ttk.Button(files, text=text, command=lambda cmd=cmd, t=t: cmd(t))
                b.pack(side="left", padx=(0, 4))
                self.team_widgets.append(b)
        self.team_msg = widgets.status(ttk.Label(box, text="", foreground=widgets.AMBER, wraplength=460, justify="left"))
        self.team_msg.grid(row=2, column=0, columnspan=2, sticky="w", pady=(2, 0))
        self.teams_note = fit.label(box, "", grey=True)
        self.teams_note.grid(row=1, column=0, columnspan=2, sticky="ew", pady=(4, 0))
        self.stadium_var.trace_add("write", lambda *a: self.teams_changed())
        self.level_var.trace_add("write", lambda *a: self.teams_changed())
        self.teams_changed()

    # --- each team's lineup, in place (Nick: "Lineup should not be a separate window, it should be drag and drop")

    def build_board(self, parent, t, row):
        """Team t's lineup under its boxes: 9 rows in batting order (the captain too), each with its slot (Bats), the
        player and his position (Plays: a small box); then the bench (DH first, typed or picked like the team's boxes)
        and who sits for the DH (FO). Drag a player up or down to move him in the order, onto another's Plays box to
        swap their positions, or between the lineup and the bench to swap a starter with a bench player; drag bench
        rows to reorder the bench. Rows ~22 px."""
        st = ttk.Style()
        st.configure("Lineup.TLabel", relief="groove", padding=(4, 2))
        st.configure("LineupOver.TLabel", relief="groove", padding=(4, 2), background=DRAG_OVER)
        st.configure("Slim.TMenubutton", padding=(4, 0))
        st.configure("Slim.TCombobox", padding=0)
        f = ttk.Frame(parent)
        f.grid(row=row, column=0, columnspan=2, sticky="w", pady=(6, 0))
        b = {"frame": f, "rows": [], "bench": [], "targets": {}, "sources": {}}
        for c, text in ((0, "Bats"), (1, "Batting order (drag to move)"), (2, "Plays")):
            ttk.Label(f, text=text, foreground=widgets.GREY).grid(row=0, column=c, sticky="w", padx=(0, 4))

        def source(w, what):
            b["sources"][str(w)] = what
            b["targets"][str(w)] = what
            w.configure(cursor="fleur")
            w.bind("<ButtonPress-1>", lambda e: self.drag_start(t, what))
            w.bind("<B1-Motion>", lambda e: self.drag_over(t, e))
            w.bind("<ButtonRelease-1>", lambda e: self.drag_end(t, e))

        def target(w, what):
            b["targets"][str(w)] = what
            w.bind("<ButtonRelease-1>", lambda e: self.drag_end(t, e), add="+")

        for r in range(TEAM_SIZE + 1):
            num = ttk.Label(f, width=3, anchor="center")
            num.grid(row=1 + r, column=0, sticky="w")
            name = ttk.Label(f, width=22, style="Lineup.TLabel")
            name.grid(row=1 + r, column=1, sticky="w", padx=(0, 4), pady=0)
            var = tk.StringVar()
            pos = ttk.Menubutton(f, textvariable=var, width=4, style="Slim.TMenubutton")   # (a small dropdown)
            menu = tk.Menu(pos, tearoff=0)
            for p in (POS_AUTO, *POSITIONS):
                menu.add_radiobutton(label=p, value=p, variable=var, command=lambda r=r, p=p: self.pick(t, r, p))
            pos.configure(menu=menu)
            pos.grid(row=1 + r, column=2, sticky="w", pady=0)
            source(num, ("row", r))
            source(name, ("row", r))
            target(pos, ("pos", r))
            b["rows"].append({"num": num, "name": name, "var": var, "pos": pos})
        top = 2 + TEAM_SIZE
        ttk.Label(f, text="Bench (the first is the DH)", foreground=widgets.GREY).grid(
            row=top, column=0, columnspan=3, sticky="w", pady=(4, 0))
        names = [NO_BENCH] + [n for n, _ in players(self.app)]
        bench = list(self.lineups[t].get("bench") or [])
        for k in range(BENCH_SIZE):
            lab = ttk.Label(f, text="DH" if k == 0 else f"B{k + 1}", width=3, anchor="center")
            lab.grid(row=top + 1 + k, column=0, sticky="w")
            v = tk.StringVar(value=bench[k] if k < len(bench) else NO_BENCH)
            box = ttk.Combobox(f, textvariable=v, values=names, width=20, style="Slim.TCombobox")
            typeahead(box, names, empty=NO_BENCH)
            box.grid(row=top + 1 + k, column=1, columnspan=2, sticky="w", pady=0)
            source(lab, ("bench", k))
            target(box, ("bench", k))
            v.trace_add("write", lambda *a: self.bench_edited(t))
            self.team_widgets.append(box)
            b["bench"].append({"label": lab, "var": v, "box": box})
        fo = ttk.Frame(f)
        fo.grid(row=top + 1 + BENCH_SIZE, column=0, columnspan=3, sticky="w", pady=(2, 0))
        ttk.Label(fo, text="Fielder only (FO)").pack(side="left", padx=(0, 4))
        b["dr_var"] = tk.StringVar()
        b["dr_box"] = ttk.Combobox(fo, textvariable=b["dr_var"], width=18, state="readonly", style="Slim.TCombobox")
        b["dr_box"].pack(side="left")
        b["dr_box"].bind("<<ComboboxSelected>>", lambda e: self.pick_dr(t))
        b["note"] = widgets.status(fit.label(f, "", grey=True, wrap=260))
        b["note"].grid(row=top + 2 + BENCH_SIZE, column=0, columnspan=3, sticky="ew", pady=(2, 0))
        b["said"] = ""                                  # the last drop's message (a swap that can't be done)
        return b

    def order(self, t):
        return list(self.lineups[t]["order"] or range(TEAM_SIZE + 1))

    def refresh(self, t):
        """Team t's board from its lineup and boxes."""
        if t >= len(getattr(self, "boards", [])):
            return
        b, lu, who = self.boards[t], self.lineups[t], self.team_names(t)
        on = self.game_on()
        for r, k in enumerate(self.order(t)):
            row = b["rows"][r]
            named = bool(who[k]) and who[k] != AUTO
            row["num"].configure(text="-" if lu["order"] is None else str(r + 1))
            row["name"].configure(text=who[k] if named else AUTO,
                                  foreground="" if named else widgets.GREY, style="Lineup.TLabel")
            row["var"].set(lu["pos"].get(k, POS_AUTO) if named else POS_AUTO)
            row["pos"].configure(state="normal" if named and on else "disabled")
        bench = self.bench(t)
        named = [n for n in who if n and n != AUTO]
        b["dr_box"].configure(values=[DR_P, DR_OFF] + named, state="readonly" if bench and on else "disabled")
        dr = lu.get("dr")
        if isinstance(dr, int) and not (who[dr] and who[dr] != AUTO):
            lu["dr"] = dr = None                        # (his spot went back to "filled for you")
        b["dr_var"].set(DR_P if dr is None or not bench else DR_OFF if dr == "off" else who[dr])
        filled = [row["var"].get() not in ("", NO_BENCH) for row in b["bench"]]
        gap = any(filled[k + 1] and not filled[k] for k in range(len(filled) - 1))
        text = ("Batting order: the game's own (drag a player to set it)." if lu["order"] is None
                else "Batting order: as listed.") \
            + ("" if len(lu["pos"]) == len(POSITIONS) else " Positions not picked: the game's own.") \
            + (" No bench: no DH, everyone bats." if not bench else
               f" {bench[0]} is the DH" + (" but sits: everyone else bats." if dr == "off" else
                                           f", batting for {who[dr]}." if isinstance(dr, int) else
                                           ", batting for whoever plays P.")) \
            + (" The bench fills from the top: the empty rows close up." if gap else "") \
            + (" " + b["said"] if b["said"] else "")
        b["note"].configure(text=text, foreground=widgets.AMBER if b["said"] else widgets.GREY)

    def bench(self, t):
        """Team t's bench as picked, from the top (empty rows close up): the first is the DH."""
        rows = self.boards[t]["bench"] if t < len(getattr(self, "boards", [])) else []
        return [row["var"].get() for row in rows if row["var"].get() and row["var"].get() != NO_BENCH]

    def bench_edited(self, t):
        self.lineups[t]["bench"] = self.bench(t)
        self.teams_changed()

    def set_bench(self, t, names):
        names = list(names or [])
        for k, row in enumerate(self.boards[t]["bench"]):
            row["var"].set(names[k] if k < len(names) else NO_BENCH)

    def pick_dr(self, t, choice=None):
        """Who sits for the DH: DR_P (whoever plays P), DR_OFF (the DH: no DH) or one of the 9 by name."""
        v = choice if choice is not None else self.boards[t]["dr_var"].get()
        who = self.team_names(t)
        self.lineups[t]["dr"] = None if v == DR_P else "off" if v == DR_OFF else \
            next((k for k, n in enumerate(who) if n == v and n != AUTO), None)
        self.teams_changed()

    def pick(self, t, r, position=None):
        """The player batting r-th plays position (his Plays box's value when None: its menu sets it); whoever had it takes his old
        one (as the game's own positions screen does)."""
        lu = self.lineups[t]
        k = self.order(t)[r]
        p = position if position is not None else self.boards[t]["rows"][r]["var"].get()
        old = lu["pos"].get(k)
        if p not in POSITIONS:
            lu["pos"].pop(k, None)
        else:
            other = next((j for j, q in lu["pos"].items() if q == p and j != k), None)
            lu["pos"][k] = p
            if other is not None:
                if old:
                    lu["pos"][other] = old
                else:
                    del lu["pos"][other]
        self.boards[t]["said"] = ""
        self.teams_changed()

    def automatic(self, t):
        """The game's own batting order and positions (the bench stays)."""
        self.lineups[t]["order"] = None
        self.lineups[t]["pos"] = {}
        self.boards[t]["said"] = ""
        self.teams_changed()

    # dragging: a press on a row (or a bench row's DH / B2.. label) starts it, the row under the pointer lights up,
    # and the release drops it there. Tk sends the release to the pressed widget: the drop target is the widget under
    # the pointer (one that's released on itself, as a test's event_generate does, is its own target).

    def drag_start(self, t, what):
        self.drag = (t, what) if self.game_on() else None

    def target_of(self, t, e):
        b = self.boards[t]
        w = e.widget
        if str(w) in b["sources"] and b["sources"][str(w)] == (self.drag or (None, None))[1]:
            try:
                w = e.widget.winfo_containing(e.x_root, e.y_root)
            except (tk.TclError, KeyError):
                w = None
        return b["targets"].get(str(w)) if w is not None else None

    def drag_over(self, t, e):
        if self.drag is None or self.drag[0] != t:
            return
        over = self.target_of(t, e)
        for r, row in enumerate(self.boards[t]["rows"]):
            row["name"].configure(style="LineupOver.TLabel" if over == ("row", r) and over != self.drag[1]
                                  else "Lineup.TLabel")

    def drag_end(self, t, e):
        if self.drag is None:
            return None
        st, what = self.drag
        where = self.target_of(t, e) if st == t else None
        self.drag = None
        for row in self.boards[st]["rows"]:
            row["name"].configure(style="Lineup.TLabel")
        if where is not None and where != what:
            self.drop(t, what, where)
        return None

    def drop(self, t, what, where):
        """A drag of what onto where, both ("row", r) (the r-th batter), ("pos", r) (his Plays box) or ("bench", k):
        a batter onto a batter moves him to that slot; onto a Plays box swaps their positions; a batter and a bench
        player swap (the bench player takes the batter's slot and position); two bench rows swap."""
        lu, b = self.lineups[t], self.boards[t]
        b["said"] = ""
        (a, i), (z, j) = what, where
        order = self.order(t)
        if a == "row" and z == "row":
            order.insert(j, order.pop(i))
            lu["order"] = order
        elif a == "row" and z == "pos":
            k, q = order[i], order[j]
            who = self.team_names(t)
            if AUTO in (who[k], who[q]) or not who[k] or not who[q]:
                b["said"] = "An empty spot's position is the game's pick: choose his player first."
            else:
                pk, pq = lu["pos"].get(k), lu["pos"].get(q)
                for spot, p in ((k, pq), (q, pk)):
                    if p:
                        lu["pos"][spot] = p
                    else:
                        lu["pos"].pop(spot, None)
        elif a == "bench" and z == "bench":
            vi, vj = b["bench"][i]["var"], b["bench"][j]["var"]
            x, y = vi.get(), vj.get()
            vi.set(y)
            vj.set(x)
        else:                                           # a batter and a bench player
            r, k = (i, j) if a == "row" else (j, i)
            self.swap_bench(t, order[r], k)
        self.teams_changed()

    def swap_bench(self, t, spot, k):
        """The player in team spot `spot` (0 the captain, 1..8 Player 2..9) and bench row k trade places: the bench
        player takes the spot's box, batting slot and position."""
        b = self.boards[t]
        who = self.team_names(t)
        starter, sub = who[spot], b["bench"][k]["var"].get()
        starter = starter if starter and starter != AUTO else None
        sub = sub if sub and sub != NO_BENCH else None
        if not starter and not sub:
            return
        if spot == 0:
            b["said"] = "The captain stays in the lineup: pick another captain in the Captain box."
        elif starter and is_mii(starter):
            b["said"] = "A Mii can't sit on the bench."
        else:
            b["bench"][k]["var"].set(starter or NO_BENCH)
            self.team_vars[t][spot - 1].set(sub or AUTO)

    def team_names(self, t):
        """Captain + the 8 player boxes of team t (AUTO for empty spots)."""
        return [self.captain_vars[t].get()] + [v.get() for v in self.team_vars[t]]

    def save_team(self, t, path=None):
        TEAMS_DIR.mkdir(exist_ok=True)
        cap = self.captain_vars[t].get()
        if path is None:
            path = filedialog.asksaveasfilename(parent=self.win, title=f"Save Team {t + 1}", initialdir=TEAMS_DIR,
                                                initialfile=f"{cap} team{TEAM_EXT}", defaultextension=TEAM_EXT,
                                                filetypes=[("Saved team", f"*{TEAM_EXT}")])
        if not path:
            return
        lu = self.lineups[t]
        data = team_file(cap, [v.get() for v in self.team_vars[t]], lu["order"], lu["pos"], lu.get("bench"),
                         lu.get("dr"))
        Path(path).write_text(json.dumps(data, indent=1), encoding="utf8")
        self.team_msg.configure(text=f"Saved Team {t + 1} to {Path(path).name}.", foreground=widgets.GREY)

    def load_team(self, t, path=None):
        if path is None:
            path = filedialog.askopenfilename(parent=self.win, title=f"Load a team into Team {t + 1}",
                                              initialdir=TEAMS_DIR if TEAMS_DIR.is_dir() else None,
                                              filetypes=[("Saved team", f"*{TEAM_EXT}"), ("All files", "*.*")])
            if not path:
                return
        try:
            data = json.loads(Path(path).read_text(encoding="utf8"))
            cap, team, missing = read_team(data, [n for n, _ in captains(self.app)],
                                           [n for n, _ in players(self.app)])
        except (OSError, ValueError) as e:
            msg = str(e) if isinstance(e, ValueError) and "saved team" in str(e) else                 f"Couldn't read {Path(path).name}: it isn't a saved team (.slgteam)."
            self.team_msg.configure(text=msg, foreground=widgets.RED)
            return
        if cap:
            self.captain_vars[t].set(cap)
        for v, n in zip(self.team_vars[t], team):
            v.set(n)
        order, pos, notes = read_lineup(data, self.captain_vars[t].get(), team)
        bench, dr, more = read_bench(data, self.captain_vars[t].get(), team, [n for n, _ in players(self.app)])
        notes += more
        self.lineups[t] = {"order": order, "pos": pos, "bench": bench, "dr": dr}
        self.boards[t]["said"] = ""
        self.set_bench(t, bench)                            # (the board's bench rows; lineups[t]["bench"] follows)
        msg = f"Loaded {Path(path).name} into Team {t + 1}" + (" with its lineup" if order or pos else "") \
            + ((" and bench." if order or pos else " with its bench.") if bench else ".")
        if missing:
            msg += " Not in your game now, left for you to fill: " + ", ".join(missing) + "."
        msg += "".join(" " + n for n in notes)
        self.team_msg.configure(text=msg, foreground=widgets.AMBER if missing or notes else widgets.GREY)
        self.teams_changed()

    def teams_option(self):
        """This window's teams, stadium and CPU level as the profile's options["boot-game"] (a stadium or level not in
        the list, e.g. an old profile's, stays as it was, and problems() names it)."""
        stadium, night = stadiums().get(self.stadium_var.get(), (self.stadium, self.night))
        out = {"captains": [v.get() for v in self.captain_vars],
               "teams": [[v.get() for v in vs if v.get() and v.get() != AUTO] for vs in self.team_vars],
               "stadium": stadium, "night": night, "level": levels(self.app).get(self.level_var.get(), self.level)}
        lineups, positions = [], []                         # (by name; an empty spot's player is quickboot's filler)
        for t, lu in enumerate(self.lineups):
            who = [n if n and n != AUTO else None for n in self.team_names(t)]
            lineups.append([who[k] for k in lu["order"]] if lu["order"] else None)
            positions.append({who[k]: p for k, p in sorted(lu["pos"].items(), key=lambda kp: POSITIONS.index(kp[1]))
                              if who[k]})
        if any(lineups):
            out["lineups"] = lineups
        if any(positions):
            out["positions"] = positions
        benches = [list(lu.get("bench") or []) for lu in self.lineups]
        if any(benches):                                    # (the DH first; who sits by name, None: whoever plays P)
            out["benches"] = benches
            drs = [dr_name(lu.get("dr"), [n if n and n != AUTO else None for n in self.team_names(t)], benches[t])
                   for t, lu in enumerate(self.lineups)]
            if any(drs):
                out["dr"] = drs
        return out

    def teams_changed(self):
        if not hasattr(self, "teams_note"):
            return
        cpu = "cpu-vs-cpu" in self.on and self.on["cpu-vs-cpu"].get()
        for t, head in enumerate(self.team_heads):
            head.configure(text=f"Team {t + 1}" + ("" if cpu or t else " (you play this one)"))
        ids = dict(captains(self.app))
        caps = [ids.get(v.get()) for v in self.captain_vars]
        note = "Empty spots are filled for you. It uses save file 1, which must have data."
        if "captains" not in self.app.picked():             # (the Captains tab's list differs)
            for c, stock in replaced([c for c in caps if c is not None]).items():
                who = next(n for n, i in captains(self.app) if i == c)
                note += f" {who} takes {stock}'s spot at captain select in this game."
        self.teams_note.configure(text=note)
        for t in range(len(getattr(self, "boards", []))):           # each team's lineup follows the team boxes
            self.refresh(t)
        self.problem.configure(text=" ".join(problems(self.app, self.teams_option())) if self.game_on() else "")

    def game_on(self):
        return "boot-game" in self.on and self.on["boot-game"].get()

    # --- the menu color (the full patcher's Features tab's box: menu_purple's presets or a #hex, and a swatch)

    def build_seed(self, parent):
        row = ttk.Frame(parent, padding=(24, 2, 0, 0))
        row.pack(anchor="w")
        self.seed = tk.StringVar(value=self.app.seed.get().strip())
        ttk.Label(row, text="Seed:").pack(side="left")
        self.seed_box = ttk.Entry(row, textvariable=self.seed, width=14)
        self.seed_box.pack(side="left", padx=4)
        fit.label(parent, "The same seed, teams and stadium replay the same CPU vs CPU game. Blank: a new game every "
                          "match.", grey=True, padding=(24, 0, 0, 0)).pack(fill="x")

    def seed_ok(self):
        import match_seed
        try:
            match_seed.parse(self.seed.get())
            return True, ""
        except ValueError as e:
            return False, str(e)

    def build_color(self, parent):
        import menu_purple
        self.menu_purple = menu_purple
        row = ttk.Frame(parent, padding=(24, 2, 0, 0))
        row.pack(anchor="w")
        self.color = tk.StringVar(value=self.app.color.get().strip() or menu_purple.DEFAULT)
        ttk.Label(row, text="Color:").pack(side="left")
        self.color_box = ttk.Combobox(row, textvariable=self.color, values=list(menu_purple.PRESETS), width=12)
        self.color_box.pack(side="left", padx=4)
        self.swatch = widgets.status(tk.Label(row, width=4, relief="sunken"))   # a colour, no words
        self.swatch.pack(side="left", padx=4)
        self.color_note = widgets.status(ttk.Label(row, text="", foreground=widgets.AMBER))
        self.color_note.pack(side="left", padx=4)
        fit.label(parent, "Pick one from the list, or type a color like #2080C0.", grey=True,
                  padding=(24, 0, 0, 0)).pack(fill="x")
        self.color.trace_add("write", lambda *a: self.color_changed())
        self.color_changed(tick=False)

    def color_ok(self):
        """(ok, message), as App.color_ok."""
        try:
            top = self.menu_purple.colors(self.color.get())[1]
        except ValueError:
            return False, "Not a color: pick one from the list or type #RRGGBB."
        self.swatch.configure(bg="#%02x%02x%02x" % tuple(top))
        return True, ("Very light: the white pattern and letters will be hard to see."
                      if self.menu_purple.warning(self.color.get()) else "")

    def color_changed(self, tick=True):
        ok, msg = self.color_ok()
        self.color_note.configure(text=msg, foreground=widgets.AMBER if ok else widgets.RED)
        if tick and ok and "menu-color" in self.on and self.menu_purple.colors(self.color.get()) != \
                self.menu_purple.colors(None):
            self.on["menu-color"].set(True)                 # (a color picked: ticked, as the Features tab does)
            self.toggled(None)

    # --- ticks and Save

    def toggled(self, f):
        if f in ONE_BOOT and self.on[f].get():              # one start or the other
            for g in ONE_BOOT - {f}:
                if g in self.on:
                    self.on[g].set(False)
        if hasattr(self, "team_widgets"):
            for w in self.team_widgets:
                w.configure(state="normal" if self.game_on() else "disabled")
            self.teams_changed()
        if hasattr(self, "captain_box"):
            self.captain_box.configure(state="normal" if self.on["boot-captain-select"].get() else "disabled")
        if hasattr(self, "color_box"):
            self.color_box.configure(state="normal" if self.on["menu-color"].get() else "disabled")
        if hasattr(self, "dh_box"):
            self.dh_box.configure(state="normal" if self.on["bench"].get() else "disabled")
        if hasattr(self, "seed_box"):
            self.seed_box.configure(state="normal" if self.on["match-seed"].get() else "disabled")
        for g, boxes in getattr(self, "replay_boxes", {}).items():
            for b in boxes:
                b.configure(state=("readonly" if isinstance(b, ttk.Combobox) else "normal") if self.on[g].get()
                            else "disabled")

    def save(self):
        app = self.app
        if self.game_on():
            wrong = problems(app, self.teams_option())
            if wrong:
                self.problem.configure(text=" ".join(wrong))
                return
        if "menu-color" in self.on and self.on["menu-color"].get() and not self.color_ok()[0]:
            self.problem.configure(text=self.color_ok()[1])
            return
        if "match-seed" in self.on and self.on["match-seed"].get() and not self.seed_ok()[0]:
            self.problem.configure(text=self.seed_ok()[1])
            return
        for f in getattr(self, "replay_boxes", {}):
            ok, why = replay_value(f, self.replay)
            if self.on[f].get() and not ok:
                self.problem.configure(text=why)
                return
        for f in self.shown:
            app.fvars[f].set(self.on[f].get())
        if hasattr(self, "replay"):
            for k, v in self.replay.items():
                app.replay[k].set(v.get())
        if hasattr(self, "seed"):
            app.seed.set(self.seed.get().strip())
        if hasattr(self, "dh"):
            app.bench_dh.set(self.dh.get())
        if hasattr(self, "captain_vars"):
            app.boot_game = self.teams_option()
        if hasattr(self, "captain_stadium"):
            app.boot_captain = self.captain_option()
        if hasattr(self, "color"):
            app.color.set(self.color.get().strip())
        on = [LABELS[f].split(" (")[0] for f in self.shown if self.on[f].get()]
        app.status.set("Game options: " + (", ".join(on) if on else "none") + ".")
        self.win.destroy()


def lineup_from_option(opt, t, who):
    """Team t's {"order", "pos"} from options["boot-game"]'s "lineups" / "positions" (names), by the spots' names
    who (captain + 8, AUTO for empty spots)."""
    order, pos, _ = read_lineup({"order": (list(opt.get("lineups") or []) + [None, None])[t],
                                 "positions": (list(opt.get("positions") or []) + [{}, {}])[t]}, who[0], who[1:])
    bench, dr, _ = read_bench({"bench": (list(opt.get("benches") or []) + [[], []])[t],
                               "dr": (list(opt.get("dr") or []) + [None, None])[t]}, who[0], who[1:])
    return {"order": order, "pos": pos, "bench": bench, "dr": dr}


# the team boxes take typing (Nick: "type and autofill"): the list narrows to the names holding what's typed (those
# starting with it first), the rest of the first such name is filled in selected, and leaving the box (Tab, Enter,
# a click elsewhere) settles on that name; an emptied player box goes back to AUTO, an unknown captain to the last one
NAV = {"BackSpace", "Delete", "Left", "Right", "Up", "Down", "Home", "End", "Tab", "Return", "Escape",
       "Shift_L", "Shift_R", "Control_L", "Control_R"}


def matches(text, values):
    t = text.strip().lower()
    if not t:
        return list(values)
    starts = [v for v in values if v.lower().startswith(t)]
    return starts + [v for v in values if t in v.lower() and v not in starts]


def typeahead(cb, values, empty=None):
    last = {"ok": cb.get()}

    def typed(e):
        if e.keysym in NAV:
            if e.keysym in ("BackSpace", "Delete"):
                cb.configure(values=matches(cb.get(), values))
            return
        text = cb.get()[:cb.index("insert")]
        hits = matches(text, values)
        cb.configure(values=hits or list(values))
        if hits and hits[0].lower().startswith(text.lower()) and text:
            cb.set(hits[0])                                   # the rest of the name, selected: typing goes on over it
            cb.icursor(len(text))
            cb.selection_range(len(text), "end")

    def settle(e=None):
        text = cb.get().strip()
        hits = [v for v in values if v.lower() == text.lower()] or matches(text, values)
        if not text and empty is not None:
            cb.set(empty)
        elif text and hits:
            cb.set(hits[0])
        else:
            cb.set(last["ok"])
        last["ok"] = cb.get()
        cb.configure(values=list(values))
        cb.selection_clear()

    cb.bind("<KeyRelease>", typed, add="+")
    cb.bind("<FocusOut>", settle, add="+")
    cb.bind("<Return>", settle, add="+")
    cb.bind("<<ComboboxSelected>>", lambda e: (last.update(ok=cb.get()), cb.configure(values=list(values))), add="+")


def open_window(app):
    """The Game options window (one at a time: a second click brings the open one up)."""
    w = getattr(app, "game_options_window", None)
    if w is not None and w.win.winfo_exists():
        w.win.lift()
        return w
    app.game_options_window = Window(app)
    return app.game_options_window


def summary(app):
    """How many game options are on, for the page's button ("Game options (2 on)...")."""
    n = sum(app.fvars[f].get() for f in FEATURES if f in app.fvars)
    return f"{TITLE} ({n} on)..." if n else f"{TITLE}..."
