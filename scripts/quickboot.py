"""Quick boot: power on -> save file 1 -> Exhibition captain select (mode="captain", the default), or
straight into a game with chosen teams (mode="game").

  quickboot.apply(dol, code)                                   captain select
  quickboot.apply(dol, code, mode="game")                      a game with 16 of the new characters
                                                               (NEW_CHARACTERS[:16]), 8 per team
  quickboot.apply(dol, code, mode="game", group=1)             the rest (NEW_CHARACTERS[-16:]: the
                                                               last 16), so two builds cover up to 32
  quickboot.apply(dol, code, mode="game", captains=("Mario", "Bowser"),
                  teams=(["Pauline", "Boom Boom", ...], ["Ice Bro", ...]), stadium=0)
  quickboot.apply(dol, code, mode="game", p1_team=1, first_bat=0)      you field first
  quickboot.apply(dol, code, mode="game", skip_intro=False)             keep the walkout
  quickboot.apply(dol, code, mode="game", captains=("Rosalina", "Bowser"), lineup=(["Rosalina"], []))
      lineup: each team's first batters in order (its captain or players; None keeps that spot's automatic
      batter, e.g. [None, None, "Dino Piranha"] bats him 3rd; the rest keep the automatic order). A captain that isn't one of the 12 stock captains takes over a stock captain's slot in
      the captain table (0x806318A8) for this build.
  quickboot.apply(dol, code, mode="game", items=True)          items on, all six enabled
  quickboot.apply(dol, code, mode="game", infinite_outs=0)     team 0 bats forever (no outs)
  quickboot.apply(dol, code, mode="game", positions=({"Luigi": "CF"}, {}))
      positions: fielding positions (P C 1B 2B 3B SS LF CF RF, record +0xC 0..8, set by FUN_8006aea4 in
      the order task's constructor FUN_8007fc58); the named player swaps with whoever holds that spot.
      captains: stock captains of team 0 / team 1; teams: up to 8 names or ids per team (slots 2-9;
      slot 1 is the captain); stadium: setup +5 value (0 = Mario Stadium; STADIUMS: the stock ones and their day / night); p1_team: the team controller
      1 plays (0, 1, or None: CPU vs CPU); first_bat: the team that bats first (setup +8, which the
      Exhibition constructor sets by coin flip; the match init FUN_80133c38 turns it into the batting
      side).
  quickboot.apply(dol, code, mode="game", level=3)             CPU level Pro (LEVELS: 1 Rookie .. 4 All-Star; 5 / 6
      the CPU levels feature's Superstar / Legend, with level6_addr = level5.level6()); None: Veteran, as the captain
      select's own default and every build before this option

The front end is a chain of task state machines (each update is `switch (task->state)`; a state that
opens a child task waits for its result):
  Opening::COpeningTask   FUN_8045a3c4, state byte +0x09: 3 opening movie, 5 title, 7/8 file select
                          (Opening::CFileSelTask), 0xE -> scene 3 (the front end)
  Opening::CFileSelTask   FUN_802d6adc, state byte +0x1C: 6 idle (pick a file); A on a file with data
                          opens its menu (7), Start (0x1E) -> 0x19 loads slot *(r13-0xB04)
  Select::CSelectTask     FUN_804a6bbc, state byte +0x0C: 5 main menu (Select::CMainSelRootTask; its
                          stadium select writes setup +5 stadium, +6/+7 night), 10 -> Exhibition
  Select::CExhiMainTask   FUN_802cec18, state byte +0x18: 5 captain select, 7 the roster screen
setup = *(r13 - 0xB00). Captain select commits (0x802CCAD0-0x802CCBFC): +0x14 / +0x15 captain index
per team (into 0x806318A8), +0x16 / +0x17 controller leading each team (0xFF: CPU), +0x18..+0x1B team
of controller 0..3 (0xFF: not playing), +0x10 = 2.

Bench players (bench=, charbuild's Start in a game with a team's bench): quickboot only keeps them off the teams and
out of the filler (and in LAST_IDS); bench.apply(preset=..., dh=..., once=True) puts them on the benches (its roster
screen init S1, before the state 2 hook above fills the teams) and the commit (S8) builds their records and the DH.

The CPU level (level=): setup +0x10 (u32), what captain select's level popup (dialog 0x71) stores: Rookie 3, Veteran 2,
Pro 1, All-Star 0 (FUN_802cb688 case 6, stores at 0x802CCCB8..0x802CCCE8; a two-human game stores 2 at 0x802CCBF4), and
4 for level5_menu's Level 5 / Level 6 buttons, which also write the LEVEL6 byte (level5.level6(): 0 Level 5, 1 Level 6).
Who reads it: the CPU manager's constructor FUN_800C364C, `lwz r6,0x10(r7)` at 0x800C3678 (level5.HOOK), copies it to
both sides (manager +8 / +0xC; FUN_800C37D0 then sets a side with a controller to 1), and the batter / pitcher AI take
their level from there (docs/cpu-ai.md). It runs at match start (FUN_800C38CC, the manager's build), long after this
file's Exhibition-entry write. Every other writer of +0x10 (a register scan of the listing for stores through
*(r13-0xB00)): the Exhibition settings init FUN_802CEA84 (2, called by the CExhiMainTask constructor, before its update
runs our block), captain select (skipped), the pause menu FUN_800A291C (the player's own change during a game), and
other modes' inits (FUN_8038C5B4, FUN_804332FC, FUN_8046D9BC, FUN_804E902C) and the minigame select FUN_8042C8A4, none
on the way from Exhibition to its game. scripts/test_cpu_level_boot.py replays it in Unicorn (settings init -> our
block -> FUN_800C364C, with level5's hook for 5 / 6).

Four hooks (a branch to a block in the code section), each firing once per power-on (its flag is a
word inside its own block):
  strap screen, state 2        -> state 4 (Startup::CStrapJacketTask FUN_804b962c, state byte +0x2C:
                                  2 waits for a button, 4 removes the screen)
  Opening entry, state 3       -> state 7 (skips the movie and the title)
  file select, state 6         -> if save slot 0 has data (save buffer +0x19D48): slot 0, state 0x19
  CSelectTask entry, state 5   -> stadium 0 by day, controller 0 enabled as state 5 does, the loading
                                  screen closed as the main menu's state 1 does, state 10
The Exhibition task then opens captain select itself; every later visit runs the stock menus.

mode="game" adds (each once per power-on):
  CExhiMainTask entry, state 5  -> captains, controller 0 leads team 0, team 1 CPU, state 7 (skips
                                   captain select, writing what its commit 0x802CCAD0 writes)
  roster screen (FUN_8006f184, obj state +0x231), state 2 -> team slots 1..8 (obj +0x2B4 / +0x2B8:
                                   9 x 0x10 handles, FUN_8006345c(handle, id), +0xC = 0xFF, +0xD = 0),
                                   +0x234 = 1 (done), state 0xE (the screen's own finish path)
  order select (Select::COrderSelectTask FUN_80080010, state +0xB8), state 5 -> both teams' "order
                                   confirmed" bytes r13-0x1EA4 / -0x1EA3 = 1 (state 5 then ends with
                                   result 2: go on to the game settings)
  game settings (TSelect::CGameSettingTask FUN_800866fc, state +0x25), state 2 -> (items: the toggle
                                   r13-0x1E95, which state 2 commits to setup +0xC; the per-item flags
                                   *(r13-0x300)+0x202..+0x207) both "confirmed"
                                   bytes r13-0x1E9C / -0x1E9B = 1 (state 2 commits the settings, result 1:
                                   start the game)
"""
import struct, sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
from ppc import Asm, ha, lo


STRAP_AT, OPENING, FILESEL_AT, SELECT = 0x804B9640, 0x8045A3C4, 0x802D6AF0, 0x804A6BBC
EXHI, ROSTER_AT, ORDER_AT, SETTINGS_AT = 0x802CEC18, 0x8006F1A8, 0x80080034, 0x80086710
REPLACED = {STRAP_AT: 0x8803002C, OPENING: 0x9421FFF0, FILESEL_AT: 0x8803001C, SELECT: 0x9421FFD0,
            EXHI: 0x9421FFA0, ROSTER_AT: 0x88030231, ORDER_AT: 0x880300B8, SETTINGS_AT: 0x88030025}
# Outs: count struct *(r13-0x1D38) +9. The three places a play adds an out (`lbz r3,9(..)`, then
# `addi r0,r3,1` here, `stb r0,9(..)`): FUN_8015e268, FUN_801639d8 and the runner-out path in FUN_80177d38.
# infinite_outs=T skips the add while team T bats (match *(r13-0x163C) +0x2A, as batter_items reads it).
OUT_ADDS = (0x8015E5AC, 0x80163B48, 0x80177DE4)
REPLACED.update({a: 0x38030001 for a in OUT_ADDS})
CAPTAIN_TABLE, N_CAPTAINS = 0x806318A8, 12      # captain index -> character id
HANDLE_SET = 0x8006345C                          # FUN_8006345c(handle, id)
# The opening walkout: match phase 5 (FUN_80132d58, match = *(r13-0x163C), phase +0x30, sub-state +0x33)
# runs the team introduction FUN_80151d6c (sub-state 1) and the walkout FUN_80151ecc (sub-state 3). Their
# own waits are resource loads (FUN_80381ca4 / FUN_80381e84 -> the loader's per-file flags, FUN_802c3dc8 the
# team intro's), so they stay: skipping them left everyone T-posing.
# The phase itself also waits on its camera scripts (the 0x85C object +0x58, set by FUN_80369d78): sub-state 2
# until the stadium flyover (mode 1) ends, sub-state 6 until the walkout camera (mode 2) sets +0x99 or a
# button skips (FUN_8012e0b8). skip_intro removes both waits (sub-state 6 then goes on as a skip does):
INTRO_TIMERS = ((0x80132E58, 0x40820188, 0x60000000),   # bne (flyover still running) -> nop
                (0x80132F0C, 0x418200D4, 0x60000000))   # beq (walkout camera not done) -> nop
# Every character not in the original game (characters/*.json; Extra Innings' four are 0x81-0x84); only the
# ones the build has are used.
NEW_CHARACTERS = tuple(range(0x66, 0x85))
# charbuild sets BUILT to the ids of the characters in the build (stock and new) around apply(): the teams, captains and
# lineups may name only these (a new id that isn't built has model directory 0: charbuild.check_ids), and the default
# teams come from them. None (a script on its own): characters/*.json. LAST_IDS: the character ids apply() put in the
# game (captains and teams), for charbuild.check_ids.
BUILT = None
LAST_IDS = ()
POSITIONS = ("P", "C", "1B", "2B", "3B", "SS", "LF", "CF", "RF")   # record +0xC values 0..8
SKIP = 0xFE                                         # lineup spot left to the automatic order (None)
LINEUP_BYTES = 60                                   # 20 batting order + 2 x 20 (id, position) pairs
# the stock Exhibition stadiums: setup +5 id -> (name, by day, at night). Ids are the select map's slots 0..8
# (docs/stadium-select.md; names as stadium_map.STOCK); day / night is the map's availability u8 0x80631CF8[id][night]
# in the clean main.dol (night_to_day.AVAIL): Bowser Castle and Luigi's Mansion are night only, Bowser Jr.'s Playroom
# day only, 9 (Toy Field) never on the map. Night writes 1 to +6 and +7 (docs/stadium-lighting.md: time of day 1).
STADIUMS = {0: ("Mario Stadium", True, True), 1: ("Bowser Castle", False, True), 2: ("Wario City", True, True),
            3: ("Yoshi Park", True, True), 4: ("Peach Ice Garden", True, True), 5: ("DK Jungle", True, True),
            6: ("Luigi's Mansion", False, True), 7: ("Daisy Cruiser", True, True),
            8: ("Bowser Jr. Playroom", True, False)}
# the CPU levels: level -> (name, setup +0x10, LEVEL6 byte or None). 1..4 the game's own; 5 / 6 level5_menu's buttons
# (the CPU levels feature, level-5). DEFAULT_LEVEL: what captain select's popup starts on and this file always wrote.
LEVELS = {1: ("Rookie", 3, None), 2: ("Veteran", 2, None), 3: ("Pro", 1, None), 4: ("All-Star", 0, None),
          5: ("Superstar", 4, 0), 6: ("Legend", 4, 1)}
DEFAULT_LEVEL = 2
STOCK_LEVELS = (1, 2, 3, 4)


def level_name(level):
    """'Pro' for 3 (LEVELS)."""
    return LEVELS[level][0]


def stadium_name(stadium, night=False):
    """'Wario City (night)' for a stock stadium (STADIUMS), else 'stadium N' (a test build's new stadium id)."""
    name = STADIUMS[stadium][0] if stadium in STADIUMS else f"stadium {stadium}"
    return name + (" (night)" if night else "")


def stadium_ok(stadium, night=False):
    """Whether a stock Exhibition offers this stadium at this time of day (STADIUMS)."""
    return stadium in STADIUMS and STADIUMS[stadium][2 if night else 1]
FILLER = ("Luigi", "Peach", "Daisy", "Green Yoshi", "Wario", "Waluigi", "Donkey Kong", "Diddy Kong",
          "Birdo", "Red Toad", "Green Koopa Troopa", "Boo", "King Boo", "Petey Piranha", "Gray Dry Bones",
          "Red Shy Guy")                        # pads a team that names fewer than 8 players
LOADING_CLOSE = 0x8008DF48           # FUN_8008df48(1): the main menu's state 1 closes the loading screen
SAVE_MGR, SAVE_BUF, SLOT0_USED = 0x80496660, 0x80496C7C, 0x19D48
PAD_MGR, PAD_MODE_A, PAD_MODE_B, PAD_APPLY, PAD_COUNT, PAD_ENABLE = (
    0x8045D834, 0x8045DDB8, 0x8045DDD0, 0x8045DDF0, 0x8045DDAC, 0x8045DDDC)


def _flag(a):
    """r12 = address of a zero word inside this code (LR preserved)."""
    a.mflr("r11").bl("flag_end").word(0)
    a.label("flag_end")
    a.mflr("r12").mtlr("r11")


def _once(a, state_off, state):
    """Continue only if the flag is clear and the task (r3) is in `state`; then set the flag."""
    _flag(a)
    a.lwz("r11", 0, "r12").cmpwi("r11", 0).bne("go")
    a.lbz("r11", state_off, "r3").cmpwi("r11", state).bne("go")
    a.li("r11", 1).stw("r11", 0, "r12")


def _call(a, addr):
    a.lis("r12", addr >> 16).ori("r12", "r12", addr & 0xFFFF).mtctr("r12").bctrl()


def _frame(a):
    a.stwu("r1", -0x20, "r1").mflr("r0").stw("r0", 0x24, "r1")
    a.stw("r31", 0x1C, "r1").stw("r30", 0x18, "r1").mr("r31", "r3")


def _unframe(a):
    a.mr("r3", "r31").lwz("r30", 0x18, "r1").lwz("r31", 0x1C, "r1")
    a.lwz("r0", 0x24, "r1").mtlr("r0").addi("r1", "r1", 0x20)


def _rlwinm(a, ra, rs, sh, mb, me):
    a.word((21 << 26) | (int(rs[1:]) << 21) | (int(ra[1:]) << 16) | (sh << 11) | (mb << 6) | (me << 1))


def _game_blocks(out, captains, ids, p1_team, first_bat, lineup, items=None, infinite_outs=None, level=DEFAULT_LEVEL,
                 level6_addr=None):
    """ids: 16 bytes, team 0 slots 1..8 then team 1 slots 1..8 (0xFF: keep the slot)."""
    a = Asm(0)                                           # Exhibition: captain select -> roster
    _once(a, 0x18, 5)
    a.lwz("r12", -0xB00, "r13")
    a.li("r11", LEVELS[level][1]).stw("r11", 0x10, "r12")   # +0x10: the CPU level (LEVELS; Veteran 2 by default)
    a.li("r11", captains[0]).stb("r11", 0x14, "r12")
    a.li("r11", captains[1]).stb("r11", 0x15, "r12")
    lead = [0xFF, 0xFF]                                  # controller leading each team (0xFF: CPU)
    if p1_team is not None:
        lead[p1_team] = 0
    for off, v in ((0x16, lead[0]), (0x17, lead[1]), (0x18, 0xFF if p1_team is None else p1_team),
                   (0x19, 0xFF), (0x1A, 0xFF), (0x1B, 0xFF), (0x08, first_bat)):
        a.li("r11", v if v < 0x80 else v - 0x100).stb("r11", off, "r12")   # +0x18: controller 0's team
    a.li("r11", 7).stb("r11", 0x18, "r3")                # +0x08: team batting first (the ctor's coin flip)
    if LEVELS[level][2] is not None:                     # Level 5 / 6: LEVEL6 as level5_menu's answer stub writes it
        a.lis("r12", ha(level6_addr)).li("r11", LEVELS[level][2]).stb("r11", lo(level6_addr), "r12")
    out[EXHI] = a

    a = Asm(0)                                           # roster: fill slots 1..8 of both teams, finish
    _once(a, 0x231, 2)
    a.stwu("r1", -0x20, "r1").mflr("r0").stw("r0", 0x24, "r1")
    a.stw("r31", 0x1C, "r1").stw("r30", 0x18, "r1").stw("r29", 0x14, "r1").stw("r28", 0x10, "r1")
    a.mr("r31", "r3")
    a.bl("table_end")
    for k in range(0, 16, 4):
        a.word(int.from_bytes(bytes(ids[k:k + 4]), "big"))
    a.label("table_end")
    a.mflr("r30").li("r29", 0)                           # r30 = ids, r29 = team * 8 + slot - 1
    a.label("slot")
    a.lbzx("r4", "r30", "r29").cmplwi("r4", 0xFF).beq("next")
    _rlwinm(a, "r5", "r29", 31, 27, 29)                  # r5 = (r29 >> 3) * 4
    a.add("r5", "r31", "r5").lwz("r5", 0x2B4, "r5")      # the team's slot handles
    _rlwinm(a, "r6", "r29", 4, 25, 27)                   # r6 = (r29 & 7) * 0x10
    a.add("r28", "r5", "r6").addi("r28", "r28", 0x10)    # slot (r29 & 7) + 1
    a.mr("r3", "r28")
    _call(a, HANDLE_SET)
    a.li("r0", 0xFF).stb("r0", 0x0C, "r28").li("r0", 0).stb("r0", 0x0D, "r28")
    a.label("next")
    a.addi("r29", "r29", 1).cmpwi("r29", 16).blt("slot")
    a.li("r0", 1).stw("r0", 0x234, "r31").li("r0", 0x0E).stb("r0", 0x231, "r31")
    a.mr("r3", "r31").lwz("r28", 0x10, "r1").lwz("r29", 0x14, "r1").lwz("r30", 0x18, "r1").lwz("r31", 0x1C, "r1")
    a.lwz("r0", 0x24, "r1").mtlr("r0").addi("r1", "r1", 0x20)
    out[ROSTER_AT] = a

    a = Asm(0)                                           # order select: batting orders and positions, confirm
    _once(a, 0xB8, 5)
    a.li("r11", 1).stb("r11", -0x1EA4, "r13").stb("r11", -0x1EA3, "r13")
    if any(b != 0xFF for b in lineup):
        a.stwu("r1", -0x20, "r1").mflr("r0").stw("r0", 0x24, "r1")
        a.stw("r31", 0x1C, "r1").stw("r30", 0x18, "r1").stw("r29", 0x14, "r1").stw("r28", 0x10, "r1")
        a.mr("r31", "r3")
        a.bl("lineup_end")                               # team 0 order at 0, team 1 at 9 (0xFF: end); then
        for k in range(0, LINEUP_BYTES, 4):              # (id, position) pairs, team t at 20 + 20 * t
            a.word(int.from_bytes(bytes(lineup[k:k + 4]), "big"))
        a.label("lineup_end")
        a.mflr("r30").li("r29", 0)                       # r29 = team
        a.label("team")
        _rlwinm(a, "r3", "r29", 2, 0, 29)                # r3 = team * 4
        a.add("r3", "r31", "r3").lwz("r28", 0xC0, "r3")  # r28 = the team's 9 slot records (batting order)
        a.cmpwi("r28", 0).beq("team_next")
        a.mulli("r4", "r29", 9).add("r4", "r30", "r4")   # r4 = this team's wanted order
        a.li("r5", 0)                                    # r5 = batting position i
        a.label("pos")
        a.lbzx("r6", "r4", "r5").cmplwi("r6", 0xFF).beq("fielding")
        a.cmplwi("r6", SKIP).beq("pos_next")             # this spot keeps the automatic order
        a.li("r7", 0)                                    # r7 = j: find the wanted player anywhere (the
                                                         # spots set before i hold other wanted players)
        a.label("find")
        a.slwi("r8", "r7", 4).add("r8", "r28", "r8").lha("r9", 0, "r8")
        a.cmpw("r9", "r6").beq("found")
        a.addi("r7", "r7", 1).cmpwi("r7", 9).blt("find")
        a.b("pos_next")                                  # not on this team: leave the order
        a.label("found")
        a.slwi("r10", "r5", 4).add("r10", "r28", "r10")  # swap records i (r10) and j (r8)
        for w in range(0, 0x10, 4):
            a.lwz("r11", w, "r10").lwz("r12", w, "r8").stw("r12", w, "r10").stw("r11", w, "r8")
        a.label("pos_next")
        a.addi("r5", "r5", 1).cmpwi("r5", 9).blt("pos")
        a.label("fielding")                              # record +0xC = fielding position (0 P .. 8 RF)
        a.mulli("r4", "r29", 20).add("r4", "r30", "r4").addi("r4", "r4", 20)
        a.label("pair")
        a.lbz("r6", 0, "r4").cmplwi("r6", 0xFF).beq("team_next").lbz("r7", 1, "r4")
        a.li("r5", 0).li("r8", 0).li("r10", 0)           # r8: the player's record, r10: the position's
        a.label("scan")
        a.slwi("r9", "r5", 4).add("r9", "r28", "r9")
        a.lha("r11", 0, "r9").cmpw("r11", "r6").bne("scan_pos").mr("r8", "r9")
        a.label("scan_pos")
        a.lbz("r11", 0xC, "r9").cmpw("r11", "r7").bne("scan_next").mr("r10", "r9")
        a.label("scan_next")
        a.addi("r5", "r5", 1).cmpwi("r5", 9).blt("scan")
        a.cmpwi("r8", 0).beq("pair_next").cmpwi("r10", 0).beq("pair_next")
        a.lbz("r11", 0xC, "r8").lbz("r12", 0xC, "r10").stb("r12", 0xC, "r8").stb("r11", 0xC, "r10")   # swap
        a.label("pair_next")
        a.addi("r4", "r4", 2).b("pair")
        a.label("team_next")
        a.addi("r29", "r29", 1).cmpwi("r29", 2).blt("team")
        a.mr("r3", "r31").lwz("r28", 0x10, "r1").lwz("r29", 0x14, "r1").lwz("r30", 0x18, "r1").lwz("r31", 0x1C, "r1")
        a.lwz("r0", 0x24, "r1").mtlr("r0").addi("r1", "r1", 0x20)
    out[ORDER_AT] = a

    a = Asm(0)                                           # game settings: both confirm
    _once(a, 0x25, 2)
    a.li("r11", 1).stb("r11", -0x1E9C, "r13").stb("r11", -0x1E9B, "r13")
    if items is not None:                                # the items toggle, committed to setup +0xC
        a.li("r11", int(items)).stb("r11", -0x1E95, "r13")
        if items:                                        # and every item enabled (settings +0x202..+0x207)
            a.lwz("r12", -0x300, "r13")
            for k in range(6):
                a.stb("r11", 0x202 + k, "r12")
    out[SETTINGS_AT] = a

    if infinite_outs is not None:                        # no out while that team bats
        for at in OUT_ADDS:
            a = Asm(0)
            a.lwz("r12", -0x163C, "r13").lbz("r12", 0x2A, "r12").cmpwi("r12", infinite_outs).bne("go")
            a.addi("r3", "r3", -1)                       # r0 = outs + 0 (r3 is reloaded after each site)
            out[at] = a


def blocks(mode="captain", stadium=0, captains=(0, 7), ids=bytes([0xFF]) * 16, p1_team=0, first_bat=0,
           lineup=bytes([0xFF]) * LINEUP_BYTES, items=None, infinite_outs=None, night=False, level=DEFAULT_LEVEL,
           level6_addr=None):
    out = {}
    a = Asm(0)                                           # strap screen: skip the wait for a button
    _once(a, 0x2C, 2)
    a.li("r11", 4).stb("r11", 0x2C, "r3")
    out[STRAP_AT] = a

    a = Asm(0)                                           # Opening: movie -> file select
    _once(a, 0x09, 3)
    a.li("r11", 7).stb("r11", 0x09, "r3")
    out[OPENING] = a

    a = Asm(0)                                           # file select: load slot 0 if it has data
    _once(a, 0x1C, 6)
    _frame(a)
    _call(a, SAVE_MGR)
    _call(a, SAVE_BUF)
    hi = (SLOT0_USED + 0x8000) >> 16
    a.word((15 << 26) | (3 << 21) | (3 << 16) | hi)      # addis r3,r3,hi
    a.lbz("r0", SLOT0_USED - (hi << 16), "r3").cmpwi("r0", 0).beq("empty")
    a.li("r0", 0).stw("r0", -0xB04, "r13")
    a.li("r0", 0x19).stb("r0", 0x1C, "r31")
    a.label("empty")
    _unframe(a)
    out[FILESEL_AT] = a

    a = Asm(0)                                           # front end: main menu -> Exhibition
    _once(a, 0x0C, 5)
    _frame(a)
    a.li("r0", 10).stb("r0", 0x0C, "r31").li("r0", 0).stb("r0", 0x0D, "r31")
    a.lwz("r12", -0xB00, "r13")
    a.li("r0", int(night)).stb("r0", 6, "r12").stb("r0", 7, "r12")   # +6 / +7 night, as the stadium map writes
    a.li("r0", stadium).stb("r0", 5, "r12")
    _call(a, PAD_MGR)                                    # as state 5: controller 0 on
    a.mr("r30", "r3").li("r4", 1)
    _call(a, PAD_MODE_A)
    a.mr("r3", "r30").li("r4", 1)
    _call(a, PAD_MODE_B)
    a.mr("r3", "r30")
    _call(a, PAD_APPLY)
    a.mr("r3", "r30")
    _call(a, PAD_COUNT)
    a.cmplwi("r3", 0).beq("pads_done")
    a.mr("r3", "r30").li("r4", 0).li("r5", 2)
    _call(a, PAD_ENABLE)
    a.label("pads_done")
    a.li("r3", 1)                                        # close the loading screen, as the menu does
    _call(a, LOADING_CLOSE)
    _unframe(a)
    out[SELECT] = a

    if mode == "game":
        _game_blocks(out, captains, ids, p1_team, first_bat, lineup, items, infinite_outs, level, level6_addr)
    for addr, a in out.items():                          # every block ends with the replaced instruction
        a.label("go")
        a.word(REPLACED[addr])
    return out


def _ids(dol, captains, teams, lineup=None, group=0, positions=None, captain_index=None, bench=None):
    """Captain indices (into CAPTAIN_TABLE), the 16 team slot ids, the filled teams, the 20 lineup bytes
    (team 0 at 0, team 1 at 9, 0xFF-terminated) and captain-table writes for non-stock captains. bench: (team 0 ids,
    team 1 ids) on the benches (bench.apply's preset): never on a team, never the filler."""
    import json
    from sluggers_data import char_id as stock_id
    defs = [json.loads(p.read_text(encoding="utf8"))
            for p in (Path(__file__).resolve().parents[1] / "characters").glob("*.json")]
    new_names = {d["name"].strip().lower(): stock_id(d["id"]) for d in defs}

    def char_id(c):                                      # stock names/ids, or a new character's name
        return new_names[c.strip().lower()] if isinstance(c, str) and c.strip().lower() in new_names else stock_id(c)
    table = [dol.u32(CAPTAIN_TABLE + 4 * i) for i in range(N_CAPTAINS)]
    cap = [char_id(c) for c in captains]
    assert cap[0] != cap[1], "the captains must differ"
    table_writes = []                                    # a non-stock captain takes over a captain slot
    spare = [i for i, c in enumerate(table) if c not in cap]
    for c in ([] if captain_index else cap):             # captain_index: indices given, table left alone
        if c not in table:
            i = spare.pop(0)
            table_writes.append((CAPTAIN_TABLE + 4 * i, c))
            table[i] = c
    if teams is None:                                    # 16 new characters, 8 per team
        built = set(new_names.values()) if BUILT is None else set(BUILT)
        new = [c for c in NEW_CHARACTERS if c in built]
        new = [c for c in (new[:16] if group == 0 else new[-16:]) if c not in cap]
        teams = (new[:8], new[8:16])
    teams = [[char_id(c) for c in t] for t in teams]
    assert len(teams) == 2 and all(len(t) <= 8 for t in teams), "two teams, 8 players each besides the captain"
    benched = [char_id(c) for b in (bench or ()) for c in b]
    used = set(cap) | {c for t in teams for c in t} | set(benched)
    assert len(used) == len(cap) + sum(len(t) for t in teams) + len(benched), "a character is picked twice"
    order = list(map(char_id, FILLER)) + list(range(0x47))   # preferred names, then every stock player
    filler = [c for c in dict.fromkeys(order) if c not in used]
    teams = [t + [filler.pop(0) for _ in range(8 - len(t))] for t in teams]
    order = bytearray([0xFF]) * LINEUP_BYTES
    for t, want in enumerate(lineup or ((), ())):
        want = [SKIP if c is None else char_id(c) for c in want]
        named = [c for c in want if c != SKIP]
        roster = [cap[t]] + teams[t]
        assert len(want) <= 9 and len(set(named)) == len(named), f"team {t}: lineup has at most 9 different players"
        assert all(c in roster for c in named), f"team {t}: lineup names a player who is not on the team"
        order[t * 9:t * 9 + len(want)] = bytes(want)
    for t, want in enumerate(positions or ({}, {})):
        pairs = [(char_id(c), POSITIONS.index(str(pos).upper())) for c, pos in want.items()]
        assert len({p for _, p in pairs}) == len(pairs), f"team {t}: two players at one position"
        assert all(c in [cap[t]] + teams[t] for c, _ in pairs), f"team {t}: positions name a player not on the team"
        order[20 + 20 * t:20 + 20 * t + 2 * len(pairs)] = bytes(b for pr in pairs for b in pr)
    if captain_index == "captains":                      # captains.py's indices in this build (captains.index_of)
        import captains
        captain_index = [captains.index_of(c) for c in cap]
    idx = list(captain_index) if captain_index else [table.index(c) for c in cap]
    global LAST_IDS
    LAST_IDS = tuple(cap) + tuple(teams[0] + teams[1]) + tuple(benched)
    if BUILT is not None:
        stray = sorted({c for c in [*cap, *teams[0], *teams[1], *benched] if c not in BUILT})
        assert not stray, "quick boot: no character in this build: " + ", ".join(f"0x{c:02X}" for c in stray)
    return idx, bytes(teams[0] + teams[1]), teams, bytes(order), table_writes


def apply(dol, code, mode="captain", stadium=0, captains=("Mario", "Bowser"), teams=None, p1_team=0,
          first_bat=0, skip_intro=True, lineup=None, group=0, positions=None, items=None,
          infinite_outs=None, night=False, captain_index=None, level=None, level6_addr=None, bench=None):
    """mode "captain": stop at captain select. mode "game": captains and teams, then straight into a game;
    p1_team: the team controller 1 plays (0, 1 or None for CPU vs CPU); first_bat: the team batting first;
    skip_intro: skip the opening team introduction and walkout (every game in this build); lineup:
    (team 0 order, team 1 order), the first batters in order (names; the rest keep the automatic order);
    group: without teams, 0 = NEW_CHARACTERS' first 16, 1 = its last 16 (the two cover up to 32);
    positions: (team 0 {player: "CF", ...}, team 1 {...}), POSITIONS; each player swaps positions with
    whoever the automatic assignment put there; items: True turns items on (all six enabled), False off,
    None keeps the saved setting; infinite_outs: team 0 or 1 never makes an out while batting (its half
    inning never ends), None: normal; night: a night game (setup +6 / +7); captain_index: (team 0, team 1)
    captain indices to use as they are, for captains another step adds (captains.py: King Bob-omb 8,
    King Boo 9, Rosalina 0x81 12, Luma 0x84 13 in a full roster), or "captains": the captains' own indices in this
    build (captains.index_of: Luma is 12 without Rosalina); the captain table is then not touched; level: the CPU level
    1..6 (LEVELS; None: Veteran, byte for byte as before); 5 and 6 need the level-5 feature's hook and its LEVEL6 byte
    (level6_addr = level5.level6()); bench: (team 0 ids, team 1 ids) the build's bench preset puts on the benches
    (bench.apply(preset=..., once=True); names or ids): kept off the teams and out of the filler."""
    global LAST_IDS
    assert isinstance(stadium, int) and 0 <= stadium < 0x100, f"quick boot: stadium {stadium!r} is not a setup +5 byte"
    assert mode in ("captain", "game") and p1_team in (0, 1, None) and first_bat in (0, 1) and group in (0, 1)
    LAST_IDS = ()
    lvl = DEFAULT_LEVEL if level is None else level
    assert lvl in LEVELS, f"quick boot: CPU level {level!r} is not one of 1..6"
    assert LEVELS[lvl][2] is None or level6_addr is not None, \
        f"quick boot: CPU level {lvl} ({level_name(lvl)}) needs the CPU levels feature (level5.level6())"
    if mode == "game":
        cap_idx, ids, filled, order, table_writes = _ids(dol, captains, teams, lineup, group, positions, captain_index,
                                                                bench)
        for addr, cid in table_writes:                   # non-stock captain: replaces a stock one in this build
            dol.w32(addr, cid)
    else:
        cap_idx, ids, filled, order, table_writes = (0, 7), bytes([0xFF]) * 16, None, bytes([0xFF]) * LINEUP_BYTES, []
    """Branch each hooked instruction to its block (which ends with that instruction) + `b` back."""
    from ppc import branch
    for addr, a in blocks(mode, stadium, cap_idx, ids, p1_team, first_bat, order, items, infinite_outs, night,
                          lvl, level6_addr).items():
        got = dol.u32(addr)
        assert got == REPLACED[addr], f"0x{addr:08X}: expected {REPLACED[addr]:08X}, found {got:08X}"
        blob = a.assemble()                              # position independent
        at = code.here + (-len(code.blob) % 4)
        blob += struct.pack(">I", branch(at + len(blob), addr + 4))
        assert code.put(blob, 4) == at
        dol.w32(addr, branch(addr, at))
    if mode == "game" and skip_intro:
        from ppc import branch
        for at, stock, new in INTRO_TIMERS:
            assert dol.u32(at) == stock, f"0x{at:08X}: expected {stock:08X}, found {dol.u32(at):08X}"
            dol.w32(at, new)
    if mode == "game":
        who = "CPU vs CPU" if p1_team is None else f"P1 on team {p1_team}"
        return [f"quick boot: power on -> save file 1 -> a game ({stadium_name(stadium, night)}, CPU level "
                f"{level_name(lvl)}, {who}, team {first_bat} bats "
                f"first): captains {list(captains)}, "
                f"teams {[[f'0x{c:02X}' for c in t] for t in filled]}"
                + (f", lineups {lineup}" if lineup else "") + (f", positions {positions}" if positions else "")
                + ("" if items is None else f", items {'on' if items else 'off'}")
                + ("" if infinite_outs is None else f", infinite outs for team {infinite_outs}")
                + (f", benches {[[f'0x{c:02X}' if isinstance(c, int) else str(c) for c in b] for b in bench]}"
                   if bench and any(bench) else "")
                + "".join(f"; captain 0x{c:02X} replaces captain slot {(a - CAPTAIN_TABLE) // 4}"
                          for a, c in table_writes)]
    return [f"quick boot: power on -> save file 1 -> captain select ({stadium_name(stadium, night)})"]
