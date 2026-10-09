"""Bench players (BN): up to NB characters per team who start off the field and can be subbed in for anyone but the
captain (docs/bench.md). A player subbed out during a game can't come back in (no re-entry).

The game's 9-slot structures never grow. The bench lives in our own tables; a sub swaps a 0x8E roster record with
a bench record, then reloads what the game has loaded for that slot.

Roster screen (Exhibition, Select::CExhiMemOrdTask):
  S1 pick-list init FUN_802c91e0: benches empty (or the preset: test builds; Start in a game, once), select mode on,
     bench invalid
  S2 FUN_8007372c wrapper (grid pick at 0x80073E08): a pick past a full 9 goes to the team's first empty bench slot
     (slot 9 + k), then the CPU team's, as the stock draft does for the 9
  S3 0x80073E30: slots 9.. store the pick in our bench entry (id, star flag)
  S4 FUN_80071abc (available?): bench characters are taken
  S5 the two Random buttons' FUN_800722ec calls re-roll the bench (full). The OK button's Random Fill and the
     "both ready" point leave benches alone (Nick: Random Fill gives neither team bench players)
  S7 the roster panels (FUN_800658a0): NB more Base + portrait widgets per team (slots 9..), drawn by the stock
     functions with the panel's pick-list pointer aimed at our list (layout: nodes 9.. of 0xB8 / 0xB9)
  S8 commit FUN_802c9280 epilogue: bench records from the master table (FUN_8046dd60), re-entry flags cleared
  S9 FUN_8046ddf0 (every mode's roster commit): bench invalid, so other modes never see a stale one
  S11 A with the pointer on one of your (or the CPU's) bench slots and nothing held: that player comes off the bench
      (the later ones move up) and is back on the grid (Nick: "it doesn't let you take them off")
  S10 Challenge mode's pick-list init (its vtable, 0x801893E4): select mode off
Batting order / positions screen (before the game; the field groups have group+0xC == 1):
  P1 the field cell loop builds 9 + (the team's bench count) cells; cells 9.. read our list (M7)
  P2 pointer: a field cell >= 9 is cursor index 0x28 + 5*team + k
  P3 FUN_80082428 (index valid?): bench indices follow the stock rules (own team, not confirmed, a filled slot)
  P4 the A dispatch lets indices >= 0x28 reach FUN_800828b4
  P5 FUN_800828b4 (A): picking up a bench player; bench <-> field / order slot / bench swaps (id and star; the slot
     keeps its position and batting spot); never the captain or a Mii
  P6 D-pad: bench slot 0 (the DH) sits at the field's bottom right: down from C / 1B into it, up to 1B, left to C;
     slots 1.. are a column left of the field: left from LF / SS / 3B into it, up / down along it, right back
  P7 the field groups' hover / held highlights for bench cells
Match:
  M1 voice groups (FUN_80386584): the per-team loop runs NB more slots, which read the bench
  M2 pause menu 0x5E (batting): "Substitute" (code 11, new dir 121 file 4 message) while the bench is valid
  M3 pause result 10 (Change the defense) / 11 (Substitute): our mode 1 / 2, then the stock defense state 0x1D
  M4 FUN_803176bc: mode 2 opens the defense screen (Gm2d_Bb::CGm2d_bb_KoutaiTask) for the batting team
  M5 the screen's constructor (after FUN_80320418): our list (bench k at position 9 + k), source map, bench count
  M6 FUN_80089840: 9 + bench count cells (element 0xB frames 10.. via the position -> frame table's padding)
  M7 the cell portrait / hand / star / chemistry widgets: for cells 9.. the group's entry pointer is our list
  M8 cursor bounds + NB (indices 11.. = bench cells); D-pad as P6
  M9 the A handler FUN_8031f9bc: bench swaps (never the captain, a Mii, or a player already subbed out);
     the batting team (mode 2) allows only those
  M10 the info balloon shows the hovered bench player
  M11 OK (FUN_803207c0 call): the records follow the source map, stamina reset, re-entry flags set; the fielding
      team asks for the stock model re-placement (lineup +0x83)
  M12 state 0x1D sub-state 6, after the stock re-placement: the changed slots' models are freed and reloaded (fielder by position; the batter
      and runners through the at-bat loaders), waiting for the loads, before the stock code fades back in
Designated hitter (bench slot 0 bats for one of the 9; docs/bench.md "Designated hitter"):
  S1 / S8 / S9 DHSEL reset to "the pitcher"; the commit resolves it to a roster slot (DHFOR, dh_slot); any commit clears it
  P9 the 10th batting-order slot (Nick: "add a tenth DH slot with a gap after 9 and let us swap in there"): per team,
     right of the order panel, "FO" beside it; whoever sits in it doesn't bat (the DH's target, or the DH himself =
     no DH). Its own Base + portrait widgets (slot 14 of the panel, node 14 of 0xB8 / 0xB9), cursor index SLOT10 +
     team, the pointer (P9: after the panel's hit test at 0x800803CC), the D-pad (right from slot 9), P3 / P5 / P7 /
     the info card. P5: slot 10 <-> an order slot / field player swaps who sits (DHSEL); slot 10 <-> bench slot k
     (k >= 1) brings a bench player in there; the DH cell <-> an order slot / field player swaps the DH in there
  P8 the batting-order panels (the stock Base / portrait draws FUN_80064234 / FUN_800643f0, entries hooked): on the
     positions screen the DH's target's order slot shows the DH (the panel's pick-list pointer aimed at bench slot 0
     for that one draw); the target's field cell stays the fielder's, greyed (M7 base)
  H1 0x80137598 FUN_80137554 (the sides flip, state 3) and H2 0x801372D8 FUN_801372c8 (match start / rematch): dh_sync(1),
     the batting team's DH record in the target's slot, the fielding team's back at bench slot 0; H2 also restores a
     captain slot (lineup + t*4) that a rematch's lineup rebuild lost while the DH sat in it
  H3 0x80152DE8 FUN_80152dd4 (winner scene, every frame): dh_sync(0), everyone fielding as picked for the results
  M9 / M11 the DH never takes the field; a new DH (fielding: from the bench; batting: a pinch hitter) puts the old one
     out; the batting team's DH cell (the player he bats for) is locked; a pinch hitter for the DH is allowed in the
     captain's slot while the DH bats for the captain
  M7 base (num_cell): the batting-order spot 1-9 on each defense-screen cell (Nick: double switches)
  M7 base (dh_cell): "DH" beside the DH's cell (dimmed at bench slot 0 while there is no DH), the player he bats for
     greyed
Pinch runners (docs/bench.md "Pinch runner"): a bench swap for a runner's slot on the batting team's screen; M12
  re-inits the runner object in place (FUN_80175630: id, speed, hand, size; his base and play state are not touched)
  and reloads model 9 + i. M7 base (run_cell): "1B" / "2B" / "3B" beside the field cell of each runner on base
"""
import struct

from ppc import Asm, x_form

NB = 5                               # bench slots per team
# data (offsets from the section base)
SEL_ON, VALID, MODE, STEP, NCHG, BD, TEAM, NBEN = 0, 1, 2, 3, 4, 5, 6, 7
CHG = 0x08                           # changed roster slots (9)
SRC = 0x18                           # the defense screen's source map: 9 slots + NB bench (who is here now)
OUT = 0x28                           # [team*NB + k]: bench slot k holds a player who was subbed out (no re-entry)
NOUT = 0x34                          # scratch for OUT (NB)
ON_ROSTER = 0x3C                     # 1 while the roster screen updates, 0 on the positions screen
FAKE = 0x40                          # per team: 9 x 0x10 pick-style entries, k < NB = bench slot k (+0xC = 9 + k)
SCR = FAKE + 2 * 0x90                # the defense screen's list (same shape, for its team)
REC = 0x200                          # [team*NB + k] 0x8E bench records (stride 0x90)
SCRATCH = REC + 2 * NB * 0x90        # 9 + NB record copies for OK
BUF = SCRATCH + (9 + NB) * 0x90      # random pool (u16 ids)
VT = BUF + 0x100                     # roster Base / portrait vtables
MENU_ON, MENU_OFF = VT + 0x20, VT + 0x48   # the batting pause menu's first 5 pairs with / without "Substitute"
BW = MENU_OFF + 0x28                 # [team*NB + k]: the roster screen's bench slot Base widgets (for the pointer)
# designated hitter (DH): bench slot 0 bats for one of the 9 (docs/bench.md, "Designated hitter")
DHSEL = BW + 8 * NB                  # [team] s16, positions screen: DH_PITCHER (bats for whoever is at P), DH_OFF, or
                                     # the character id he bats for
DHFOR = DHSEL + 4                    # [team] s8, match: the roster slot the DH bats for, or -1 (no DH)
DHIN = DHFOR + 2                     # [team] u8, match: 1 while the DH's record is in that slot (REC slot 0 = the
                                     # player he bats for)
DHDX = DHIN + 2                      # f32: the "DH" picture's x offset from its cell's centre (layout units)
# pinch runners: "1B" / "2B" / "3B" beside the field cell of each runner on base (the batting team's Substitute screen)
BASETXT = DHDX + 4                   # 3 x 8: "1B", "2B", "3B" (UTF-16, fullwidth, 0-terminated)
BASEDX = BASETXT + 3 * 8             # f32: their x offset from the cell's centre (right: "DH" is on the left)
# the 10th order slot (P9)
SLOT10W = BASEDX + 4                 # [team] its Base widget (the pointer's hit test)
SLOT10DX = SLOT10W + 8               # f32: its "DH" picture's x offset from the slot's centre (layout units)
NUMDX = SLOT10DX + 4                 # f32 0: the numbers' matrix offset (their keys hold NUM_XY)
PDONE = NUMDX + 4                    # u8: 1 once a commit (S8) has used a once-only preset (Start in a game's bench)
DATA_SIZE = PDONE + 1 + (-(PDONE + 1) % 32)
DH_PITCHER, DH_OFF = -2, -1          # DHSEL values besides a character id
DH_LABEL_DX = -34.0                  # left of the cell, clear of its rim (-26 hid the H: Nick, showcase-20): at the DH spot that's the open space between
                                     # C and the DH (right is the CPU's bench column on the positions screen, below
                                     # the panels); docs/bench.md "Where the DH sits"
# The "DH" picture (Nick: "take the DH letters from somewhere else in the game so they look better"): the D of
# "Distance King" and the H of "Nice-Hit King", the white-with-dark-outline style of the menu buttons' words, cut from
# the player's own dt_na dir 119 file 21 at build time (dh_art) into a new texture page + row + one-sprite element
# of file 19 (layout_bytes), drawn by the cell's disc draw at its matrix moved DH_LABEL_DX (label, ELEMENT_DRAW).
DH_ART_FILE = (119, 21)
DH_ART_GLYPHS = ((2, 1, 20), (1, 63, 82))  # (row, first column, end column) in the row's cell: D, H
DH_ART_CELLS = {1: (222, 324, 414, 353), 2: (222, 353, 414, 382)}   # the rows' pixel rects on page 6 (asserted)
DH_ART_PAGE = 6                      # 1024 x 1024 CI4, 16 IA8 colours
DH_ART_SIZE = (37, 29)               # D (19 wide) and H (19) overlapping by their 1-px outline column
DH_ART_SCALE = 0.8                   # the sprite key's scale (x the cell's: 0.75 on a bench cell)
# The DH on a field cell (the batting team's Substitute screen: the DH is in his target's slot, often P, so his face is
# in P's cell and the pitcher's is at cell 9, marked "FO" as the 10th order slot; Nick read the DH there as the
# pitcher: "NO THE DH LETTERS SHOULD BE BY THE DH NOT THE PITCHER"): "DH" left of
# the cell sat on the face (Nick: "The DH letters are in the wrong spot", DH_LABEL_DX = -34 left of a full-size P
# cell's 53-unit disc). There it goes above the face, centred, like a label: node 1 of DH_ELEMENT, its key at
# (0, DH_ABOVE_Y) (key y down, as NUM_XY). The picture is 30 x 23 units at DH_ART_SCALE, the disc ~46 tall: at -38 it
# spans y -50..-27 over the face's top at -23 (~4 px gap); above P (0, 8) that's y -42..-19, x -15..15, clear of 2B /
# SS (+-54, -17: discs from |x| 28) and CF (0, -73: down to -50, ~8 px). Node 0 (key at 0, 0) stays for cell 9.
DH_ABOVE_NODE, DH_ABOVE_Y = 1, -38
DH_ELEMENT = 204                     # file 19's element count: the new element's index (asserted in layout_bytes)
# "FO" (fielder only) beside the 10th order slot (Nick: "Can you use FO (Fielder only) instead of DR"; it read "DR"
# before): the F of "First-Catch King" (the D's file 21 page 6, row 9: the same font and 16-px cap as the D of
# "DH"; columns 0..16, its right cut outlined, the "i" starts at 18) and the O of the "O K" button (19/19 row 0xE7,
# page 92, cell (874, 693)-(991, 732): the button font, a 16-px white fill with a near-black outline, a little
# heavier than the D's; columns 30..49, rows 11..30 = its outline box, fill rows 13..28), its fill top on the F's (5)
FO_F_GLYPH = ((119, 21), 9, 0, 17, 6, (222, 556, 414, 585))
FO_O_GLYPH = ((119, 19), 0xE7, 30, 50, 92, (874, 693, 991, 732))
FO_O_ROWS = (11, 31)
FO_O_Y = 3                           # the O crop's top in the picture: its fill row 13 -> the F's 5
FO_O_OVERLAP = 1                     # the O's left outline over the F's cut column
FO_ART_SIZE = (17 - FO_O_OVERLAP + 20, 29)
# Batting-order numbers on the defense screen's field cells (Nick: "add little numbers to the icons in the substitution
# screen so I can easily do a double switch"): the stock outlined digits of the order panel (file 19 rows 0x119 "0"
# .. 0x122 "9", 20 x 22, the Dajun order slots' numbers), element NUM_ELEMENT with node i = digit i + 1, each key at
# NUM_XY (the cell's lower left, on the disc's rim) at NUM_SCALE, drawn by the cell's disc draw with its matrix.
NUM_ELEMENT = DH_ELEMENT + 1
FO_ELEMENT = NUM_ELEMENT + 1         # the "FO" picture
NUM_ROW0 = 0x119                     # the row of "0"
NUM_XY = (-17, 17)                   # (the face: the disc's middle; hand icon top left; "DH" left; "1B".. right)
NUM_SCALE = 0.55
BASE_LABEL_DX = 32.0                 # right of the cell, so a DH on base shows both [I: not seen yet]
WHITE = 0x3F800000
REC_STRIDE = 0x90
SECTION = 0x7000                     # code + data (0x5000 -> 0x6000 -> 0x7000 as the DH, the 10th slot, the numbers grew)

BENCH_CELL = 11                      # the defense screen's cursor index for bench slot 0 (2 + cell 9)
SLOT10 = 0x32                        # the positions screen's cursor index of team t's 10th order slot: SLOT10 + t
SLOT10_WIDGET = 9 + NB               # its panel slot number (widget +0xD4) = its node in 0xB8 / 0xB9
# Placement (Nick's showcase-19 crop of the positions screen, 1514 x 317 at 2.275 x the 865 x 448 screenshots: the
# order slots 58 px apart (65.25 layout units: 0.889 px per unit), slot 9 at px 600, the "P1" / "CPU" letters px
# 651-697, the panel's end px 737, free right of it to the screen's edge (865; the top panel's right side is clear
# above the logo, which starts at px y 90)): slot 10 at px 795, 219 units right of slot 9, full size (the cards are
# ~44 px wide: px 773-817); "FO" left of it, touching the card, in the gap after the panel (centre px 761, ~26 px wide).
SLOT10_DX_NODE = 219                 # node 14's x - node 8's (same y, scale 1)
SLOT10_LABEL_DX = -40.0              # the "FO" picture's x offset from slot 10's centre: touching the card (half ~25 units)
# Bench slot 0 (the DH) sits apart, at the field's bottom right (Nick: "DH should be bottom right, away from the
# bench"); slots 1.. are a column left of the field. D-pad: left from LF / SS / 3B reaches slot 1 / 2 / 3 (the last
# filled one if fewer), up / down along the column (never into the DH), right from slot k back to the position beside
# it; down from C / 1B reaches the DH, and from the DH up goes to 1B, left to C (right / down stay).
LEFT_COLUMN = ((6, 1), (5, 2), (4, 3))                     # (position, bench slot)
COLUMN_BACK = (None, 6, 5, 4, 4)                           # bench slot -> position (slot 0: the DH, see DH_*)
assert len(COLUMN_BACK) == NB
DH_FROM = (1, 2)                     # positions whose D-pad down reaches the DH cell (C, 1B)
DH_UP, DH_LEFT = 2, 1                # the DH cell's up (1B) and left (C)
GREY = 0x3F266666                    # 0.65: the colour multiplier of bench slots and cells (Nick: greyed out)
DARK = 0x3E99999A                    # 0.3: a bench player who was subbed out and can't come back in (Nick)
CARD = 0x14                          # the positions screen's info card: our entry for a bench index (one shot)
PRE_BENCH = 0x28                     # the positions screen's index for team t, bench k: 0x28 + NB*t + k
PRE_FIELD = (0x16, 0x1F)             # its field cells: base + position
BENCH_FRAME = 10                     # element 0xB frame for cell 9 (frames 0-8 positions, 9 the ground)
FRAME_TABLE = 0x8063CAF0             # position -> element 0xB frame (9 bytes; 0x8063CAF9..FF are padding)

# stock functions
MEMCPY, NEW, HEAP = 0x8000626C, 0x80521224, 0x803A57C4
SET_ENTRY = 0x8006345C               # FUN_8006345c(entry, id)
RANDOM = 0x80478BB4                  # FUN_80478bb4(lo, hi)
POOL = 0x800721A0                    # FUN_800721a0(obj, out, mask, team) -> count
TARGET, RANDOM_FILL = 0x8007372C, 0x800722EC
WIDGET_INIT, WIDGET_ADD = 0x8008E81C, 0x8051E688
RECORD = 0x8046DD60                  # FUN_8046dd60(roster, dst, id, star)
CAPTAIN = 0x802D9910                 # FUN_802d9910(setup, team) -> the captain's id
GAME = 0x801319BC
LINEUP_POS = 0x8015A96C              # (lineup, lineup team, slot) -> position
MAX_STAMINA = 0x8015C914
GROUP = 0x801519F0
FREE_A, FREE_B = 0x8014B8EC, 0x8014B588
FIELDER_MODEL, FIELDER_ANIM, PITCHER_GEAR, CATCHER_GEAR = 0x8014B3D8, 0x8014B83C, 0x8014B934, 0x8014B9C4
RUNNER_MODEL, BATTER_ANIM, RUNNER_ANIM = 0x80154774, 0x80154AE4, 0x80154A64
RUNNER_INIT = 0x80175630
BACKDROPS, BACKDROP_LOAD, BACKDROP_READY = 0x802C3C24, 0x802C3DC0, 0x802C3DC8
LOADING_A, LOADING_B = 0x80381CA4, 0x80381E84
RUNNERS = 0x807098C8
SWAP_FN, APPLY_FN, VPAD_FN, HPAD_FN = 0x8031F9BC, 0x803207C0, 0x8031FD38, 0x8031FEC8
BATTING_MENU = 0x806D2D38            # menu 0x5E: 7 {code, message} pairs; the first 5 are rewritten
MENU_STOCK = ((0, 0x5E), (8, 0x5F), (9, 0x60), (4, 0x61), (-1, 0))
JUMP_TABLE = 0x80643D44              # pause result -> case
DEFENSE_CASE, NOOP_CASE = 0x80134748, 0x80134990
SUB_CODE = 11
STATE_RETURN = 0x80134EEC
# positions screen
PRE_ENTRY = 0x80082684               # FUN_80082684(task, index, &team, &slot) -> found
PRE_HELD_ICON, PRE_CHANGED = 0x8006BF84, 0x802C946C
PRE_UP, PRE_DOWN, PRE_SIDE = 0x80082EBC, 0x800833A8, 0x8008388C
CHALLENGE_INIT = (0x8064AB78 + 0x10, 0x801893E4)   # Cm::CChallMemOrderItemSelTask vtable +0x10
ROSTER_UPDATE, POSITIONS_UPDATE = (0x8006F184, 0x9421FFA0), (0x80080010, 0x9421FFA0)   # entries
CELL_BASE = (0x80088D3C, 0x9421FFF0) # the field cells' Base widget draw (the cell's disc)
BALLOON = (0x8031CE10, 0x9421FFD0)   # FUN_8031ce10: the defense screen's stat card picks its characters
BALLOON_BOUND = (0x8031CEC0, 0x2C83000A)   # cmpwi cr1,r3,0xa: its cursor-index range
PRE_CARD_CALL, PRE_CARD_READ = 0x8007E81C, (0x8007E844, 0x808400C0)   # positions screen info card

# roster screen widget vtables (Dajun_local)
VT_KITEI, VT_BASE, VT_KAO = 0x8063A3B0, 0x8063A348, 0x8063A278
DRAW_BASE, DRAW_KAO = 0x80064234, 0x800643F0
P8 = ((DRAW_BASE, 0x9421FFE0), (DRAW_KAO, 0x9421FFC0))   # the panels' Base / portrait draws: entries (stwu r1)
P9 = 0x800803CC                      # positions screen pointer: bl FUN_800663b4 (the order panel's hit test)
PANEL_HIT = 0x800663B4

# field cell widgets whose draw finds "the entry at this cell" (Kao, Hand, Star, Aishou)
CELL_DRAWS = ((0x80088E50, 0x9421FFD0), (0x8008915C, 0x9421FF50), (0x800892E0, 0x9421FFE0),
              (0x800893F8, 0x9421FF40))
BOUNDS = ((0x8031E5B4, 0x2C1E000B), (0x8031E600, 0x2C03000B), (0x8031E70C, 0x2C00000A),
          (0x8031E8C0, 0x2C03000A), (0x8031E8EC, 0x2C04000A), (0x8031E924, 0x2C04000A))

# hook sites: (address, stock word)
S1 = (0x802C91E0, 0x9421FFD0)
S2 = 0x80073E08                      # bl 0x8007372c
S3 = (0x80073E30, 0x40840074)        # bge cr1,0x80073ea4
S4 = (0x80071ABC, 0x9421FFD0)
S5_REROLL, S5_KEEP = (0x8006F5D0, 0x8006FC24), (0x8006FA58, 0x8006FB44)
S6 = (0x80070344, 0x38600001)
S7 = (0x80066124, 0x81CD00D8)
S8 = (0x802C9458, 0xBA810010)
S9 = (0x8046DDF0, 0x9421FFE0)
S11 = (0x8006F560, 0x801902D8)       # roster screen, A pressed: lwz r0,0x2d8(r25) (r30 screen, r22 team, r23 ctrl)
S11_SKIP = 0x8006FD38                # the "A not pressed" path (the other buttons)
HIT = 0x8008E478                     # FUN_8008e478(x f1, y f2, widget) -> the pointer is on the widget
SOUND, SOUND_CANCEL = 0x804B2714, 0x50
P2 = (0x8008042C, 0x7EA32214)        # add r21,r3,r4
P3 = (0x80082428, 0x2C050003)        # cmpwi r5,3
P4 = (0x80080544, 0x40800190)        # bge 0x800806d4 -> 0x800806b8
P4_TO = 0x800806B8
P5 = (0x800828B4, 0x9421FFB0)
P6 = ((0x80080908, PRE_UP), (0x80080968, PRE_DOWN), (0x800809CC, PRE_SIDE), (0x80080A30, PRE_SIDE))
P7 = (0x80081698, 0x38800000)        # li r4,0 (r30 = task)
M1_COUNT = (0x80386904, 0x881E000F)
M1_ID = (0x803868A0, 0x7C0402AE)
M2 = (0x801346D0, 0x80010030)
M4 = (0x803176D4, 0x8863002B)
M5 = (0x8032029C, 0x83ADF860)
M6 = (0x80089F44, 0x2C120009)
M9 = 0x8031E718
M10 = (0x8031EAD8, 0x381B0090)
M8_V, M8_H = (0x8031E800, 0x8031E818), (0x8031E830, 0x8031E848)
M11 = 0x80320B30
# state 0x1D sub-state 6, after the stock re-placement (`bl 0x801519F0` once FUN_801536cc is done or not needed):
# our reloads free and load at the slots' new positions, so they must follow the stock move of the old models
M12 = (0x80134E60, 0x4801CB91)
# DH swaps: dh_sync(1) where the sides flip and at match start; dh_sync(0) in the winner scene
H1 = (0x80137598, 0x80630044)        # FUN_80137554 (state 3 sub-state 2) after the +0x2A..0x2D XORs: lwz r3,0x44(r3)
H2 = (0x801372D8, 0x7C7A1B78)        # FUN_801372c8 (match start / rematch reads from the roster): or r26,r3,r3
H3 = (0x80152DE8, 0x88030003)        # FUN_80152dd4 (winner-scene director, states 9 / 0x1B, every frame): lbz r0,3(r3)
TEXT = 0x8043D62C                    # FUN_8043d62c(str, -1, 1, 0, layout, +0xBC, 0, element; stack: mtx, colour, ...)
ELEMENT_DRAW = 0x8051892C            # FUN_8051892c(layout, time, element, mtx, colour, node a, node b, +0xBC) (a < 0: all
                                     # nodes), as FUN_8051c9fc (every widget's draw) calls it with the widget's own
DH_TEXT_ELEMENT = 0x0E               # a text box at (0, 0) of the screen's layout (FUN_8031de78 draws with it)


def extsb(ra, rs): return x_form(rs, ra, 0, 954)
def extsh(ra, rs): return x_form(rs, ra, 0, 922)
def lhax(rt, ra, rb): return x_form(rt, ra, rb, 343)


class A(Asm):
    def extsb(self, ra, rs): return self.word(extsb(ra, rs))
    def extsh(self, ra, rs): return self.word(extsh(ra, rs))
    def lhax(self, rt, ra, rb): return self.word(lhax(rt, ra, rb))
    def stwx(self, rs, ra, rb): return self.word(x_form(rs, ra, rb, 151))
    def xor(self, ra, rs, rb): return self.word(x_form(rs, ra, rb, 316))

    def label(self, name):                     # a label defined twice silently moved every branch to it
        assert name not in self.labels, f"bench: label {name!r} defined twice"
        super().label(name)

    @staticmethod
    def frame(n):
        return max(0x40, (0x28 + 4 * n + 15) & ~15)

    def enter(self, n):
        """A frame saving LR and r31..r(32-n) at its top; locals at 0x08..0x27."""
        assert n <= 8
        f = self.frame(n)
        self.stwu("r1", -f, "r1").mflr("r0").stw("r0", f + 4, "r1")
        for i in range(n):
            self.stw(31 - i, f - 4 - 4 * i, "r1")
        return self

    def leave(self, n):
        f = self.frame(n)
        for i in range(n):
            self.lwz(31 - i, f - 4 - 4 * i, "r1")
        return self.lwz("r0", f + 4, "r1").mtlr("r0").addi("r1", "r1", f).blr()

    def grey(self, w, tmp, value=GREY):
        """Widget w's base colour (+0x90: vtable, r, g, b, a; copied to its draw colour +0xA4 every frame) grey."""
        self.lis(tmp, value >> 16).ori(tmp, tmp, value & 0xFFFF)
        return self.stw(tmp, 0x94, w).stw(tmp, 0x98, w).stw(tmp, 0x9C, w)

    def group(self, dst, w, tmp):
        """dst = the widget group object of widget `w` (*(*(*(r13+0xd8)+0x10)) + w[8]*4)."""
        self.lwz(tmp, 0xD8, 13).lwz(tmp, 0x10, tmp).lwz(tmp, 0, tmp)
        return self.lbz(dst, 8, w).slwi(dst, dst, 2).lwzx(dst, tmp, dst)


def code(base, D, flags_off, preset, msg, dh=None, once=False):
    """The whole module at `base` (after the data block at `D`). Returns the Asm (labels in .labels). preset / dh /
    once: apply()'s."""
    a = A(base)
    L = a.label
    n = [0]

    def uniq(s):
        n[0] += 1
        return f"{s}_{n[0]}"

    def fake(dst, team, k=None, kreg=None):
        """dst = our pick-style entry for (team register, bench slot k / k register). Uses r12 (r11 when dst is
        r12) for the address: never r0, which addi reads as 0."""
        tmp = "r11" if dst == "r12" else "r12"
        assert tmp not in (team, kreg), "fake(): scratch register clash"
        a.mulli(dst, team, 0x90).load_addr(tmp, D + FAKE).add(dst, dst, tmp)
        if kreg is not None:
            a.slwi("r0", kreg, 4).add(dst, dst, "r0")
        elif k:
            a.addi(dst, dst, 0x10 * k)

    def is_cpu(team, tmp, not_cpu):
        a.lwz(tmp, -0xB00, 13).add(tmp, tmp, team).lbz(tmp, 0x16, tmp).extsb(tmp, tmp).cmpwi(tmp, 0).bge(not_cpu)

    def count(dst, team, tmp, tmp2):
        """dst = the number of filled bench slots of `team` (they fill from slot 0)."""
        top, done = uniq("cnt"), uniq("cnt_done")
        a.mulli(tmp, team, 0x90).load_addr(tmp2, D + FAKE).add(tmp, tmp, tmp2).li(dst, 0)
        L(top)
        a.cmpwi(dst, NB).bge(done).lha(tmp2, 0, tmp).cmpwi(tmp2, 0).blt(done)
        a.addi(dst, dst, 1).addi(tmp, tmp, 0x10).b(top)
        L(done)

    # ================= roster screen =================
    L("fill")                                   # fill(obj r3, team r4): random picks for the empty bench slots
    a.enter(5).mr("r31", "r3").mr("r30", "r4").load_addr("r29", D)
    a.lbz("r0", SEL_ON, "r29").cmpwi("r0", 0).beq("fill_out")
    a.li("r28", 0)
    L("fill_loop")
    a.cmpwi("r28", NB).bge("fill_out")
    fake("r27", "r30", kreg="r28")
    a.lha("r0", 0, "r27").cmpwi("r0", 0).bge("fill_next")
    a.mr("r3", "r31").addi("r4", "r29", BUF).li("r5", 0).mr("r6", "r30").bl(POOL)
    a.cmpwi("r3", 0).ble("fill_out")
    a.addi("r4", "r3", -1).li("r3", 0).bl(RANDOM)
    a.slwi("r3", "r3", 1).addi("r4", "r29", BUF).lhax("r4", "r4", "r3")
    a.mr("r3", "r27").bl(SET_ENTRY)
    a.li("r0", 0).stb("r0", 0xD, "r27")
    L("fill_next")
    a.addi("r28", "r28", 1).b("fill_loop")
    L("fill_out")
    a.leave(5)

    def s1_fill(ids, sel):
        """The benches' pick entries (ids: per team, None = empty) and DHSEL (sel: per team)."""
        for t in range(2):
            for k in range(9):
                e = FAKE + 0x90 * t + 0x10 * k
                pid = ids[t][k] if ids and k < len(ids[t]) and k < NB else -1
                a.li("r12", pid).sth("r12", e, "r11")
                a.li("r12", 0).stw("r12", e + 4, "r11").stw("r12", e + 8, "r11").stb("r12", e + 0xD, "r11")
                a.li("r12", 9 + k if k < NB else -1).stb("r12", e + 0xC, "r11")
        a.li("r12", sel[0]).sth("r12", DHSEL, "r11").li("r12", sel[1]).sth("r12", DHSEL + 2, "r11")

    L("s1")                                     # pick-list init: benches empty (or the preset), select mode on
    a.load_addr("r11", D)
    sel = tuple(dh) if dh else (DH_PITCHER, DH_PITCHER)     # a new roster: DH for the P (or the preset's DHSEL)
    if preset and once:                         # Start in a game: the preset until a commit has used it, then the
        a.lbz("r12", PDONE, "r11").cmpwi("r12", 0).bne("s1_plain")      # game's own (empty benches, DH for the P)
        s1_fill(preset, sel)
        a.b("s1_rest")
        L("s1_plain")
        s1_fill(None, (DH_PITCHER, DH_PITCHER))
        L("s1_rest")
    else:
        s1_fill(preset, sel)
    a.li("r12", 1).stb("r12", SEL_ON, "r11").li("r12", 0).stb("r12", VALID, "r11")
    for i in range(2 * NB):
        a.stw("r12", BW + 4 * i, "r11")
    a.word(S1[1]).b(S1[0] + 4)

    L("first_empty")                            # r3 = team -> r3 = its first empty bench slot, or -1 (leaf)
    fake("r12", "r3")
    a.li("r3", 0)
    L("fe_loop")
    a.cmpwi("r3", NB).bge("fe_none").lha("r0", 0, "r12").cmpwi("r0", 0).blt("fe_out")
    a.addi("r3", "r3", 1).addi("r12", "r12", 0x10).b("fe_loop")
    L("fe_none")
    a.li("r3", -1)
    L("fe_out")
    a.blr()

    L("s2")                                     # FUN_8007372c(obj, team, &t, &slot) wrapper
    a.enter(4).mr("r31", "r3").mr("r30", "r4").mr("r29", "r5").mr("r28", "r6")
    a.bl(TARGET)
    a.lwz("r0", 0, "r29").cmpwi("r0", 0).bge("s2_out")
    a.load_addr("r12", D).lbz("r0", SEL_ON, "r12").cmpwi("r0", 0).beq("s2_out")
    a.mr("r3", "r30").bl("first_empty").cmpwi("r3", 0).blt("s2_other")
    a.stw("r30", 0, "r29").addi("r3", "r3", 9).stw("r3", 0, "r28").b("s2_out")
    L("s2_other")                               # the other team, if it is a CPU's
    a.li("r10", 1).subf("r10", "r30", "r10")
    is_cpu("r10", "r9", "s2_out")
    a.mr("r3", "r10").bl("first_empty").cmpwi("r3", 0).blt("s2_out")
    a.li("r10", 1).subf("r10", "r30", "r10").stw("r10", 0, "r29").addi("r3", "r3", 9).stw("r3", 0, "r28")
    L("s2_out")
    a.leave(4)

    L("s3")                                     # 0x80073E30: cr1 = slot vs 9
    a.blt("s3_lt", cr=1)
    a.lwz("r0", 8, "r1").cmpwi("r0", 9 + NB).bge("s3_ne")
    a.lwz("r3", 0xC, "r1").lwz("r4", 8, "r1").addi("r4", "r4", -9)
    fake("r3", "r3", kreg="r4")
    a.mr("r4", "r26").bl(SET_ENTRY)
    a.lwz("r3", 0xC, "r1").lwz("r4", 8, "r1").addi("r4", "r4", -9)
    fake("r3", "r3", kreg="r4")
    a.extsb("r0", "r31").add("r4", "r27", "r0").lbz("r0", flags_off, "r4").stb("r0", 0xD, "r3")
    a.b(0x80073F64)
    L("s3_lt")
    a.b(0x80073E34)
    L("s3_ne")
    a.b(0x80073EA4)

    L("s4")                                     # FUN_80071abc(obj, handle): bench characters are taken
    a.lha("r0", 0, "r4").cmpwi("r0", 0).blt("s4_orig")
    a.load_addr("r12", D).lbz("r11", SEL_ON, "r12").cmpwi("r11", 0).beq("s4_orig")
    a.addi("r12", "r12", FAKE).li("r10", 18)
    L("s4_loop")
    a.lha("r11", 0, "r12").cmpw("r0", "r11").beq("s4_no")
    a.addi("r12", "r12", 0x10).addi("r10", "r10", -1).cmpwi("r10", 0).bne("s4_loop")
    L("s4_orig")
    a.word(S4[1]).b(S4[0] + 4)
    L("s4_no")
    a.li("r3", 0).blr()

    for name, reroll in (("s5_keep", False), ("s5_reroll", True)):
        L(name)                                 # FUN_800722ec(obj, team), then the bench
        a.enter(2).mr("r31", "r3").mr("r30", "r4").bl(RANDOM_FILL)
        if reroll:                              # Random: a new full bench
            fake("r12", "r30")
            for k in range(NB):
                a.li("r0", -1).sth("r0", 0x10 * k, "r12")
        else:                                   # OK's auto-fill: only a CPU team's bench
            is_cpu("r30", "r9", f"{name}_out")
        a.mr("r3", "r31").mr("r4", "r30").bl("fill")
        L(f"{name}_out")
        a.leave(2)

    L("s6")                                     # both teams ready (r30 = screen object): CPU benches filled
    for t in range(2):
        a.li("r10", t)
        is_cpu("r10", "r9", f"s6_h{t}")
        a.mr("r3", "r30").li("r4", t).bl("fill")
        L(f"s6_h{t}")
    a.word(S6[1]).b(S6[0] + 4)

    L("s7")                                     # after the panel's 9-slot widget loop
    a.mr("r3", "r27").mr("r4", "r29").mr("r5", "r28").bl("mkw")
    a.word(S7[1]).b(S7[0] + 4)

    L("mkw")                                    # mkw(panel, layout, r5 arg): slots 9.. Base + portrait widgets
    a.enter(6).mr("r31", "r3").mr("r30", "r4").mr("r29", "r5")
    a.load_addr("r12", D).lbz("r0", SEL_ON, "r12").cmpwi("r0", 0).beq("mkw_out")
    a.li("r28", 9)
    L("mkw_loop")
    a.cmpwi("r28", SLOT10_WIDGET + 1).bge("mkw_out")
    for i, kind in enumerate((3, 4)):
        a.li("r3", 3).bl(HEAP).mr("r4", "r3").li("r3", 0xDC).bl(NEW)
        a.cmpwi("r3", 0).beq(f"mkw_skip{i}").mr("r26", "r3")
        a.li("r3", 3).bl(HEAP).mr("r10", "r3")
        a.li("r0", 1).stw("r0", 8, "r1").stw("r28", 0xC, "r1")
        a.mr("r3", "r26").li("r4", 0).mr("r5", "r30").li("r6", -1).li("r7", kind).li("r8", 0).mr("r9", "r29")
        a.bl(WIDGET_INIT)
        a.load_addr("r11", VT_KITEI).stw("r11", 0xC, "r26")
        a.li("r0", 0).stw("r0", 0xD8, "r26").li("r0", 6).stw("r0", 0xC8, "r26").stw("r0", 0xCC, "r26")
        a.lwz("r3", 0x24, "r26").lwz("r3", 0, "r3").li("r0", 0xA6).sth("r0", 0x2C, "r3")
        a.li("r0", 0).stb("r0", 0x2E, "r3").stb("r0", 0x2F, "r3")
        a.lwz("r3", 0x24, "r26").lwz("r3", 0, "r3").li("r0", 0xB7).sth("r0", 0x44, "r3")
        a.li("r0", 2).stb("r0", 0x46, "r3").li("r0", 0).stb("r0", 0x47, "r3")
        a.load_addr("r11", D + VT + 0x10 * i).stw("r11", 0xC, "r26")
        a.grey("r26", "r11")
        if kind == 3:
            a.li("r0", 8).stw("r0", 0xC8, "r26").stw("r0", 0xCC, "r26")
        a.lwz("r3", 0xD8, 13).mr("r4", "r26").lbz("r5", 6, "r31").li("r6", 0).bl(WIDGET_ADD)
        if kind == 3:                           # the slot's Base widget, for take()'s / P9's pointer test
            s10, done = uniq("mkw_s10"), uniq("mkw_bw")
            a.cmpwi("r28", SLOT10_WIDGET).beq(s10)
            a.lbz("r11", 7, "r31").mulli("r11", "r11", NB).add("r11", "r11", "r28").addi("r11", "r11", -9)
            a.slwi("r11", "r11", 2).load_addr("r12", D + BW).stwx("r26", "r12", "r11").b(done)
            L(s10)
            a.lbz("r11", 7, "r31").slwi("r11", "r11", 2).load_addr("r12", D + SLOT10W).stwx("r26", "r12", "r11")
            L(done)
        L(f"mkw_skip{i}")
    a.addi("r28", "r28", 1).b("mkw_loop")
    L("mkw_out")
    a.leave(6)

    for name, draw in (("draw_base", "p8_base_o"), ("draw_kao", "p8_kao_o")):
        L(name)                                 # slots 9..: the panel's pick list aimed so slot 9 + k is our entry k
        a.lwz("r0", 0xD4, "r3").cmpwi("r0", SLOT10_WIDGET).beq(f"{name}_s10")
        a.load_addr("r12", D).lbz("r0", ON_ROSTER, "r12").cmpwi("r0", 0).bne(f"{name}_on")
        a.li("r3", 0).blr()                     # the positions screen shows the bench on the fields instead
        L(f"{name}_on")
        a.enter(3).mr("r31", "r3")
        a.group("r30", "r31", "r12")
        a.lwz("r29", 8, "r30")
        a.lbz("r3", 7, "r30")
        fake("r12", "r3")
        a.addi("r12", "r12", -0x90).stw("r12", 8, "r30")
        for k in range(NB):                     # the panel's per-slot byte +0x24 + slot: saved, zeroed, restored
            a.lbz("r0", 0x2D + k, "r30").stb("r0", 0x10 + k, "r1")
        a.li("r0", 0)
        for k in range(NB):
            a.stb("r0", 0x2D + k, "r30")
        a.mr("r3", "r31").bl(draw)
        a.stw("r29", 8, "r30")
        for k in range(NB):
            a.lbz("r0", 0x10 + k, "r1").stb("r0", 0x2D + k, "r30")
        a.leave(3)
        # the 10th order slot (positions screen only; none while bench slot 0 is empty): whoever sits, i.e. the DH's
        # target (his pick entry) or, with no DH, the DH himself (bench slot 0); the Base draw adds "FO" beside it
        L(f"{name}_s10")
        a.load_addr("r12", D).lbz("r0", ON_ROSTER, "r12").cmpwi("r0", 0).bne(f"{name}_s10_no")
        a.lbz("r0", SEL_ON, "r12").cmpwi("r0", 0).beq(f"{name}_s10_no")
        a.enter(4).mr("r31", "r3")
        a.group("r30", "r31", "r12")
        a.lwz("r29", 8, "r30")
        a.lbz("r3", 7, "r30")
        fake("r12", "r3")
        a.lha("r0", 0, "r12").cmpwi("r0", 0).blt(f"{name}_s10_out")
        a.mr("r3", "r29").lbz("r4", 7, "r30").bl("s10_entry")                # r3 = the entry shown
        a.addi("r3", "r3", -0x10 * SLOT10_WIDGET).stw("r3", 8, "r30")
        a.lbz("r28", 0x24 + SLOT10_WIDGET, "r30").li("r0", 0).stb("r0", 0x24 + SLOT10_WIDGET, "r30")
        a.mr("r3", "r31").bl(draw)
        a.stw("r29", 8, "r30").stb("r28", 0x24 + SLOT10_WIDGET, "r30")
        if name == "draw_base":
            a.lbz("r0", 0xC2, "r31").cmpwi("r0", 0).beq(f"{name}_s10_out")
            a.load_addr("r12", D).lfs("f1", SLOT10DX, "r12").li("r4", 0).lis("r5", WHITE >> 16).mr("r3", "r31")
            a.li("r6", FO_ELEMENT).li("r7", -1).bl("label")
        L(f"{name}_s10_out")
        a.li("r3", 0).leave(4)
        L(f"{name}_s10_no")
        a.li("r3", 0).blr()

    L("s10_entry")                              # s10_entry(pick list r3, team r4) -> r3 = the entry in slot 10
    a.enter(3).mr("r31", "r3").mr("r30", "r4")
    a.bl("dh_slot").cmpwi("r3", 0).blt("s10e_dh")
    a.slwi("r3", "r3", 4).add("r3", "r3", "r31").b("s10e_out")
    L("s10e_dh")
    fake("r3", "r30")
    L("s10e_out")
    a.leave(3)

    L("s11")                                    # roster screen, A pressed
    a.mr("r3", "r30").mr("r4", "r22").mr("r5", "r18").mr("r6", "r19").mr("r7", "r23").bl("take")
    a.cmpwi("r3", 0).beq("s11_o").b(S11_SKIP)
    L("s11_o")
    a.word(S11[1]).b(S11[0] + 4)

    L("take")                                   # take(screen, team, ctrl*4, ctrl*8, ctrl) -> 1: a bench player came off
    a.enter(6).mr("r31", "r3").mr("r30", "r4").mr("r27", "r7").load_addr("r29", D)
    a.lbz("r0", SEL_ON, "r29").cmpwi("r0", 0).beq("take_no")
    a.slwi("r0", "r30", 2).add("r9", "r31", "r0").lwz("r0", 0x2E0, "r9").cmpwi("r0", 0).bge("take_no")   # held
    a.lwz("r9", -0x2BC, 13).add("r10", "r9", "r5").lwz("r0", 0x94, "r10").andi_("r0", "r0", 2).beq("take_no")
    a.addi("r9", "r9", 0x34).add("r9", "r9", "r6").lfs("f0", 0, "r9").stfs("f0", 0x10, "r1")
    a.lfs("f0", 4, "r9").stfs("f0", 0x14, "r1")
    for pass_ in range(2):                      # own team, then the other if it is a CPU's
        if pass_ == 0:
            a.mr("r28", "r30")
        else:
            a.li("r28", 1).subf("r28", "r30", "r28")
            is_cpu("r28", "r9", "take_no")
        a.li("r26", 0)
        L(f"take_k{pass_}")
        a.cmpwi("r26", NB).bge(f"take_next{pass_}")
        a.mulli("r11", "r28", NB).add("r11", "r11", "r26").slwi("r11", "r11", 2).add("r11", "r11", "r29")
        a.lwz("r3", BW, "r11").cmpwi("r3", 0).beq(f"take_skip{pass_}")
        fake("r11", "r28", kreg="r26")
        a.lha("r0", 0, "r11").cmpwi("r0", 0).blt(f"take_skip{pass_}")
        a.lfs("f1", 0x10, "r1").lfs("f2", 0x14, "r1").bl(HIT).cmpwi("r3", 0).bne("take_hit")
        L(f"take_skip{pass_}")
        a.addi("r26", "r26", 1).b(f"take_k{pass_}")
        L(f"take_next{pass_}")
    L("take_no")
    a.li("r3", 0).b("take_out")
    L("take_hit")                               # slot r26 of team r28: the later ones move up, the last empties
    fake("r11", "r28", kreg="r26")
    L("take_shift")
    a.addi("r26", "r26", 1).cmpwi("r26", NB).bge("take_last")
    a.lha("r0", 0x10, "r11").sth("r0", 0, "r11").lbz("r0", 0x1D, "r11").stb("r0", 0xD, "r11")
    a.addi("r11", "r11", 0x10).b("take_shift")
    L("take_last")
    a.li("r0", -1).sth("r0", 0, "r11").li("r0", 0).stb("r0", 0xD, "r11")
    a.lwz("r3", -0x158, 13).addi("r3", "r3", 0x33C).addi("r4", "r31", 0x678).li("r5", SOUND_CANCEL).mr("r6", "r27")
    a.bl(SOUND)
    a.li("r3", 1)
    L("take_out")
    a.leave(6)

    L("s8")                                     # commit epilogue: bench records, re-entry flags cleared, valid
    a.load_addr("r31", D)
    for t in range(2):
        for k in range(NB):
            e, r = FAKE + 0x90 * t + 0x10 * k, REC + REC_STRIDE * (t * NB + k)
            a.li("r0", -1).sth("r0", r, "r31").li("r0", 0).stb("r0", OUT + t * NB + k, "r31")
            a.lha("r5", e, "r31").cmpwi("r5", 0).blt(f"s8_skip{t}{k}")
            a.lwz("r3", -0x2C8, 13).addi("r4", "r31", r).lbz("r6", e + 0xD, "r31").bl(RECORD)
            a.li("r0", 1).stb("r0", VALID, "r31")
            L(f"s8_skip{t}{k}")
    for t in range(2):                          # the DH's roster slot (r26 = the task; its pick lists at +0x28)
        a.addi("r3", "r26", 0x28 + 0x90 * t).li("r4", t).bl("dh_slot").stb("r3", DHFOR + t, "r31")
        a.li("r0", 0).stb("r0", DHIN + t, "r31")
    if preset and once:                         # the preset's game has started: later rosters are the game's own
        a.li("r0", 1).stb("r0", PDONE, "r31")
    a.li("r0", 0).stb("r0", SEL_ON, "r31")
    a.word(S8[1]).b(S8[0] + 4)

    L("s9")                                     # any roster commit: bench invalid until ours sets it again, no DH
    a.load_addr("r12", D).li("r0", 0).stb("r0", VALID, "r12").sth("r0", DHIN, "r12")
    a.li("r0", -1).stb("r0", DHFOR, "r12").stb("r0", DHFOR + 1, "r12")
    a.word(S9[1]).b(S9[0] + 4)

    for name, (site, first), on_roster in (("r_on", ROSTER_UPDATE, 1), ("r_off", POSITIONS_UPDATE, 0)):
        L(name)
        a.load_addr("r12", D).li("r0", on_roster).stb("r0", ON_ROSTER, "r12")
        a.word(first).b(site + 4)

    L("s10")                                    # Challenge mode's pick-list init: select mode off
    a.load_addr("r12", D).li("r0", 0).stb("r0", SEL_ON, "r12")
    a.b(CHALLENGE_INIT[1])

    # ================= positions screen (before the game) =================
    def classify(x, team, kind, tmp):
        """team / kind of positions-screen index x: kind 0 order slot, 1 field, 3 bench, 4 the 10th order slot, -1
        other (team -1)."""
        done = uniq("cl")
        a.li(team, -1).li(kind, -1)
        a.cmpwi(x, 4).blt(done)
        for lo, hi, t, k in ((4, 0xD, 0, 0), (0xD, 0x16, 1, 0), (0x16, 0x1F, 0, 1), (0x1F, 0x28, 1, 1),
                             (PRE_BENCH, PRE_BENCH + NB, 0, 3), (PRE_BENCH + NB, PRE_BENCH + 2 * NB, 1, 3),
                             (SLOT10, SLOT10 + 1, 0, 4), (SLOT10 + 1, SLOT10 + 2, 1, 4)):
            nxt = uniq("cl")
            a.cmpwi(x, hi).bge(nxt).li(team, t).li(kind, k).b(done)
            L(nxt)
        L(done)

    L("p2")                                     # pointer on field cell r3 of group t (8(r1)), base r4
    a.cmpwi("r3", 9).blt("p2_o")
    a.lwz("r12", 8, "r1").mulli("r12", "r12", NB).addi("r12", "r12", PRE_BENCH - 9).add("r21", "r3", "r12")
    a.b(P2[0] + 4)
    L("p2_o")
    a.word(P2[1]).b(P2[0] + 4)

    L("p3")                                     # FUN_80082428(task, p, index): valid cursor target?
    a.load_addr("r12", D).lbz("r0", SEL_ON, "r12").cmpwi("r0", 0).beq("p3_orig")
    a.slwi("r11", "r4", 2).add("r11", "r11", "r3").lwz("r10", 0x160, "r11")   # r10 = held
    a.cmpwi("r5", PRE_BENCH).bge("p3_ours").cmpwi("r10", PRE_BENCH).bge("p3_ours")
    L("p3_orig")
    a.word(P3[1]).b(P3[0] + 4)
    L("p3_ours")
    a.cmpwi("r5", SLOT10 + 2).bge("p3_no")
    classify("r5", "r6", "r7", "r0")            # r6 = team, r7 = kind of the index
    a.cmpwi("r7", 0).blt("p3_no")
    a.addi("r9", 13, -0x1EA4).lbzx("r0", "r9", "r4").cmpwi("r0", 0).bne("p3_no")   # confirmed
    a.lbz("r0", 0x20, "r3").cmpwi("r0", 0).beq("p3_n20").cmpwi("r6", 1).beq("p3_no")
    L("p3_n20")
    a.cmpwi("r7", 4).beq("p3_k0")               # the 10th order slot: there while bench slot 0 is filled
    a.cmpwi("r7", 3).bne("p3_filled")           # a bench index: that slot must be filled
    a.mulli("r8", "r6", NB).subf("r8", "r8", "r5").addi("r8", "r8", -PRE_BENCH)   # k
    a.b("p3_k")
    L("p3_k0")
    a.li("r8", 0)
    L("p3_k")
    fake("r9", "r6", kreg="r8")
    a.lha("r0", 0, "r9").cmpwi("r0", 0).blt("p3_no")
    L("p3_filled")
    a.cmpwi("r10", 0).bge("p3_held")
    a.li("r9", 1).subf("r9", "r4", "r9").cmpw("r6", "r9").bne("p3_yes")   # not the other team ...
    is_cpu("r9", "r8", "p3_no")                 # ... unless it is a CPU's
    a.b("p3_yes")
    L("p3_held")                                # something held: same team, a field / order / bench index
    classify("r10", "r8", "r9", "r0")
    a.cmpw("r8", "r6").bne("p3_no").cmpwi("r9", 0).blt("p3_no")
    L("p3_yes")
    a.li("r3", 1).blr()
    L("p3_no")
    a.li("r3", 0).blr()

    def mii(reg, yes):
        """Branch to `yes` when character id `reg` is a Mii (0x4D..0x64)."""
        no = uniq("mii")
        a.cmpwi(reg, 0x4D).blt(no).cmpwi(reg, 0x64).ble(yes)
        L(no)

    L("dh_slot")                                # dh_slot(pick list r3, team r4) -> r3 = the slot the DH bats for / -1
    a.enter(5).mr("r31", "r3").mr("r30", "r4").load_addr("r29", D)
    fake("r9", "r30")                           # the DH = bench slot 0: someone, and not a Mii
    a.lha("r0", 0, "r9").cmpwi("r0", 0).blt("dh_none")
    mii("r0", "dh_none")
    a.slwi("r9", "r30", 1).add("r9", "r9", "r29").lha("r28", DHSEL, "r9")
    a.cmpwi("r28", DH_OFF).beq("dh_none")
    a.li("r27", 0)
    L("dh_id")                                  # the chosen player, if he is still among the 9 ...
    a.cmpwi("r28", 0).blt("dh_p")
    a.slwi("r9", "r27", 4).lhax("r0", "r31", "r9").cmpw("r0", "r28").beq("dh_check")
    a.addi("r27", "r27", 1).cmpwi("r27", 9).blt("dh_id")
    L("dh_p")                                   # ... else whoever is at P
    a.li("r27", 0)
    L("dh_ploop")
    a.slwi("r9", "r27", 4).add("r9", "r9", "r31").lbz("r0", 0xC, "r9").cmpwi("r0", 0).beq("dh_check")
    a.addi("r27", "r27", 1).cmpwi("r27", 9).blt("dh_ploop")
    a.b("dh_none")
    L("dh_check")                               # anyone but a Mii, the captain too (docs/bench.md, "The captain")
    a.slwi("r9", "r27", 4).lhax("r28", "r31", "r9")
    mii("r28", "dh_none")
    a.mr("r3", "r27").b("dh_out")
    L("dh_none")
    a.li("r3", -1)
    L("dh_out")
    a.leave(5)

    L("dh_card")                                # dh_card(task r3, index r4) -> r3 = the index, or the DH cell's
    a.enter(3).mr("r31", "r3").mr("r30", "r4")  # when it is the order slot showing the DH (the DH's spot)
    a.cmpwi("r4", 4).blt("dcard_same").cmpwi("r4", 0x16).bge("dcard_same")
    a.li("r29", 0).cmpwi("r4", 0xD).blt("dcard_t0").li("r29", 1)
    L("dcard_t0")
    a.slwi("r0", "r29", 2).add("r3", "r31", "r0").lwz("r3", 0xC0, "r3").mr("r4", "r29").bl("dh_slot")
    a.cmpwi("r3", 0).blt("dcard_same")
    a.mulli("r9", "r29", 9).subf("r9", "r9", "r30").addi("r9", "r9", -4).cmpw("r3", "r9").bne("dcard_same")   # slot (not r0: addi)
    a.mulli("r3", "r29", NB).addi("r3", "r3", PRE_BENCH).b("dcard_out")
    L("dcard_same")
    a.mr("r3", "r30")
    L("dcard_out")
    a.leave(3)

    L("p5")                                     # FUN_800828b4(task, p): A
    a.load_addr("r12", D).lbz("r0", SEL_ON, "r12").cmpwi("r0", 0).beq("p5_tramp")
    a.enter(8).mr("r31", "r3").mr("r30", "r4").load_addr("r27", D)
    a.slwi("r0", "r30", 2).add("r26", "r31", "r0")      # r26 = task + p*4
    a.lwz("r29", 0x158, "r26").lwz("r28", 0x160, "r26")  # cursor, held
    a.li("r0", 0).stw("r0", 0x24, "r1")                  # 0x24: DHSEL to set to the id in r25's entry after a swap
    # the order card that shows the DH (P8: the DH's spot) acts as the DH (his cell), not as the sitter under it
    a.stw("r29", 0x08, "r1").stw("r28", 0x0C, "r1")    # the raw indices (the DH cell vs the DH's card)
    a.mr("r3", "r31").mr("r4", "r29").bl("dh_card").mr("r29", "r3")
    a.cmpwi("r28", 0).blt("p5_mapped")
    a.mr("r3", "r31").mr("r4", "r28").bl("dh_card").mr("r28", "r3")
    L("p5_mapped")
    a.cmpwi("r28", 0).bge("p5_held")
    a.cmpwi("r29", PRE_BENCH).blt("p5_stock")
    # pick up a bench player or the 10th order slot's
    classify("r29", "r6", "r7", "r0")
    a.stw("r29", 0x160, "r26")
    a.cmpwi("r7", 4).beq("p5_pick10")
    a.mulli("r8", "r6", NB).subf("r8", "r8", "r29").addi("r8", "r8", -PRE_BENCH)
    fake("r9", "r6", kreg="r8")
    a.b("p5_icon")
    L("p5_pick10")
    a.slwi("r0", "r6", 2).add("r3", "r31", "r0").lwz("r3", 0xC0, "r3").mr("r4", "r6").bl("s10_entry").mr("r9", "r3")
    L("p5_icon")
    a.stw("r9", 0x10, "r1")
    a.mulli("r0", "r30", 0x14).add("r3", "r31", "r0").addi("r3", "r3", 0x16C).lha("r4", 0, "r9").bl(SET_ENTRY)
    a.lwz("r9", 0x10, "r1").lbz("r0", 0xD, "r9").cmpwi("r0", 0).beq("p5_s0").li("r0", 1)
    L("p5_s0")
    a.mulli("r3", "r30", 0x14).add("r3", "r3", "r31").stb("r0", 0x178, "r3")
    a.addi("r3", "r31", 0x1A8).mr("r4", "r30").bl(PRE_HELD_ICON)
    a.li("r3", 1).b("p5_out")
    L("p5_held")
    a.cmpwi("r28", PRE_BENCH).bge("p5_hb").cmpwi("r29", PRE_BENCH).blt("p5_stock")
    classify("r29", "r6", "r7", "r0")           # an order slot / field player held, A on ...
    a.mr("r4", "r28").cmpwi("r7", 4).beq("p5_s10p")                     # ... the 10th order slot
    a.cmpwi("r29", PRE_BENCH).beq("p5_dhin").cmpwi("r29", PRE_BENCH + NB).beq("p5_dhin")   # ... the DH cell
    a.mr("r4", "r28").mr("r5", "r29").b("p5_pair")      # r4 = the other index, r5 = the bench index
    L("p5_hb")
    a.cmpw("r28", "r29").beq("p5_drop")
    classify("r28", "r6", "r7", "r0")
    a.cmpwi("r7", 4).beq("p5_held10")
    a.cmpwi("r29", PRE_BENCH).blt("p5_hb_player")
    classify("r29", "r6", "r7", "r0")           # a bench player held, A on the 10th order slot / another bench slot
    a.mr("r4", "r28").cmpwi("r7", 4).beq("p5_s10b")
    a.b("p5_bb")
    L("p5_hb_player")                           # a bench player held, A on an order slot / field player
    a.mr("r4", "r29")                           # the DH cell held: swap the DH in there
    a.cmpwi("r28", PRE_BENCH).beq("p5_dhin").cmpwi("r28", PRE_BENCH + NB).beq("p5_dhin")
    a.b("p5_hb_pair")
    L("p5_held10")                              # the 10th order slot held, A on ...
    a.mr("r4", "r29").cmpwi("r29", PRE_BENCH).blt("p5_s10p")           # ... an order slot / field player
    a.b("p5_s10b")                              # ... a bench slot (the other team's: P3 refuses)
    L("p5_hb_pair")
    a.mr("r4", "r29").mr("r5", "r28")
    L("p5_pair")                                 # bench index r5 <-> order slot / field cell r4
    a.stw("r5", 0x14, "r1")
    a.mr("r3", "r31").addi("r5", "r1", 0x18).addi("r6", "r1", 0x1C).bl(PRE_ENTRY)
    a.cmpwi("r3", 0).beq("p5_fail")
    a.lwz("r0", 0x18, "r1").slwi("r0", "r0", 2).add("r9", "r31", "r0").lwz("r9", 0xC0, "r9")
    a.lwz("r0", 0x1C, "r1").slwi("r0", "r0", 4).add("r25", "r9", "r0")     # r25 = the pick-list entry
    a.lwz("r5", 0x14, "r1")
    classify("r5", "r6", "r7", "r0")
    a.mulli("r8", "r6", NB).subf("r8", "r8", "r5").addi("r8", "r8", -PRE_BENCH)
    fake("r24", "r6", kreg="r8")                                             # r24 = our entry
    a.b("p5_swap")
    L("p5_bb")                                   # two bench slots
    classify("r28", "r6", "r7", "r0")
    a.mulli("r8", "r6", NB).subf("r8", "r8", "r28").addi("r8", "r8", -PRE_BENCH)
    fake("r25", "r6", kreg="r8")
    classify("r29", "r6", "r7", "r0")
    a.mulli("r8", "r6", NB).subf("r8", "r8", "r29").addi("r8", "r8", -PRE_BENCH)
    fake("r24", "r6", kreg="r8")
    a.b("p5_swap2")
    L("p5_swap")                                 # r25 <-> r24: never the captain or a Mii
    a.lwz("r3", -0xB00, 13).lwz("r4", 0x18, "r1").bl(CAPTAIN)
    a.lha("r0", 0, "r25").extsh("r3", "r3").cmpw("r0", "r3").beq("p5_fail")
    for reg in ("r25", "r24"):
        ok = uniq("p5_mii")
        a.lha("r0", 0, reg).cmpwi("r0", 0x4D).blt(ok).cmpwi("r0", 0x64).ble("p5_fail")
        L(ok)
    L("p5_swap2")
    a.lha("r0", 0, "r25").sth("r0", 0x20, "r1").lbz("r0", 0xD, "r25").stb("r0", 0x22, "r1")
    a.mr("r3", "r25").lha("r4", 0, "r24").bl(SET_ENTRY).lbz("r0", 0xD, "r24").stb("r0", 0xD, "r25")
    a.mr("r3", "r24").lha("r4", 0x20, "r1").bl(SET_ENTRY).lbz("r0", 0x22, "r1").stb("r0", 0xD, "r24")
    a.lwz("r9", 0x24, "r1").cmpwi("r9", 0).beq("p5_swapped")   # a bench player into the 10th slot: he sits
    a.lha("r0", 0, "r25").sth("r0", 0, "r9")
    L("p5_swapped")
    a.bl(PRE_CHANGED)
    L("p5_drop")
    a.li("r0", -1).stw("r0", 0x160, "r26")
    a.mulli("r0", "r30", 0x14).add("r3", "r31", "r0").addi("r3", "r3", 0x16C).li("r4", -1).bl(SET_ENTRY)
    a.li("r3", 1).b("p5_out")
    # the 10th order slot <-> order slot / field player r4 (entry s): who sits changes. The DH in slot 10 (no DH):
    # he bats in s's spot, s sits. Player T sits: s = T (his own spot / cell) -> the DH off, T bats; otherwise the
    # whole pick entries of s and T swap (each keeps his fielding position) and s, now in the DH's spot T, sits.
    L("p5_s10p")
    a.mr("r3", "r31").addi("r5", "r1", 0x18).addi("r6", "r1", 0x1C).bl(PRE_ENTRY)
    a.cmpwi("r3", 0).beq("p5_fail")
    a.lwz("r0", 0x18, "r1").slwi("r0", "r0", 2).add("r9", "r31", "r0").lwz("r25", 0xC0, "r9")   # r25 = pick list
    a.lwz("r0", 0x1C, "r1").slwi("r0", "r0", 4).add("r24", "r25", "r0")                        # r24 = s's entry
    a.mr("r3", "r25").lwz("r4", 0x18, "r1").bl("dh_slot")                                     # r3 = T
    a.cmpwi("r3", 0).blt("p5_s10p_on")
    a.lwz("r0", 0x1C, "r1").cmpw("r3", "r0").bne("p5_s10p_swap")
    a.li("r0", DH_OFF).b("p5_s10p_store")
    L("p5_s10p_swap")
    a.lha("r0", 0, "r24")
    mii("r0", "p5_fail")
    a.slwi("r3", "r3", 4).add("r3", "r3", "r25")                                            # r3 = T's entry
    for off in range(0, 0x10, 4):
        a.lwz("r10", off, "r24").lwz("r11", off, "r3").stw("r11", off, "r24").stw("r10", off, "r3")
    a.lha("r0", 0, "r3").b("p5_s10p_store")
    L("p5_s10p_on")
    a.lha("r0", 0, "r24")
    mii("r0", "p5_fail")
    L("p5_s10p_store")
    a.lwz("r9", 0x18, "r1").slwi("r9", "r9", 1).add("r9", "r9", "r27").sth("r0", DHSEL, "r9")
    a.bl(PRE_CHANGED).b("p5_drop")
    # the DH cell <-> order slot / field player r4 (entry s): swap the DH in: he bats in s's spot and s sits (the
    # 10th slot); whoever sat there bats again in his own spot. s already sitting (the DH's spot): nothing to do.
    L("p5_dhin")
    # the DH's FIELD cell <-> a field cell (Nick, showcase-23: "DH SWAPPING FROM FIELDING NEEDS TO MOVE WHO THE DH
    # IS"): swap the two characters (id, star): the fielder becomes the DH, the old DH takes his place (slot,
    # position, batting spot). Who sits doesn't change: DHSEL follows the spot (the fielder was the sitter -> the old
    # DH, now in that slot). Only the lineup (order cards, FO) chooses who sits.
    a.lwz("r5", 0x08, "r1").lwz("r6", 0x0C, "r1").cmpw("r4", "r6").bne("p5_dhin_side").mr("r6", "r5")
    L("p5_dhin_side")                           # r6 = the DH side's raw index
    a.cmpwi("r6", PRE_BENCH).blt("p5_dhin_lineup")      # the DH's card: the lineup rule
    classify("r4", "r7", "r8", "r0")
    a.cmpwi("r8", 1).bne("p5_dhin_lineup")      # an order card: the lineup rule
    a.mr("r3", "r31").addi("r5", "r1", 0x18).addi("r6", "r1", 0x1C).bl(PRE_ENTRY)
    a.cmpwi("r3", 0).beq("p5_fail")
    a.lwz("r0", 0x18, "r1").slwi("r0", "r0", 2).add("r9", "r31", "r0").lwz("r25", 0xC0, "r9")
    a.lwz("r0", 0x1C, "r1").slwi("r0", "r0", 4).add("r25", "r25", "r0")                        # r25 = his entry
    a.lwz("r6", 0x18, "r1")
    fake("r24", "r6")                                                                       # r24 = the DH
    a.slwi("r9", "r6", 1).add("r9", "r9", "r27").lha("r0", DHSEL, "r9").lha("r11", 0, "r25").cmpw("r0", "r11")
    a.bne("p5_swap")                            # he sat (DHSEL = his id): the old DH sits in his slot now
    a.addi("r9", "r9", DHSEL).stw("r9", 0x24, "r1").b("p5_swap")
    L("p5_dhin_lineup")
    a.mr("r3", "r31").addi("r5", "r1", 0x18).addi("r6", "r1", 0x1C).bl(PRE_ENTRY)
    a.cmpwi("r3", 0).beq("p5_fail")
    a.lwz("r0", 0x18, "r1").slwi("r0", "r0", 2).add("r9", "r31", "r0").lwz("r25", 0xC0, "r9")   # r25 = pick list
    a.lwz("r0", 0x1C, "r1").slwi("r0", "r0", 4).add("r24", "r25", "r0")                        # r24 = s's entry
    a.mr("r3", "r25").lwz("r4", 0x18, "r1").bl("dh_slot").lwz("r0", 0x1C, "r1").cmpw("r3", "r0").beq("p5_fail")
    a.lha("r0", 0, "r24")                       # (the sitter's own cell: he already sits; the error sound, not "done")
    mii("r0", "p5_fail")
    a.b("p5_s10p_store")
    # the 10th order slot <-> bench slot index r4 (the DH, cell or card: the DH off): the DH there (no DH) -> the two
    # bench slots swap (a new DH, still off); player T there -> bench k's player takes T's pick entry (as any bench
    # swap: never the captain or a Mii) and sits in his place
    L("p5_s10b")
    classify("r4", "r6", "r7", "r0")
    a.mulli("r8", "r6", NB).subf("r8", "r8", "r4").addi("r8", "r8", -PRE_BENCH)
    a.stw("r6", 0x18, "r1").stw("r8", 0x1C, "r1")
    a.slwi("r0", "r6", 2).add("r9", "r31", "r0").lwz("r25", 0xC0, "r9")
    a.mr("r3", "r25").mr("r4", "r6").bl("dh_slot")                                         # r3 = T
    a.lwz("r6", 0x18, "r1").lwz("r8", 0x1C, "r1")
    a.cmpwi("r8", 0).bne("p5_s10b_k")           # the DH (his cell or card): the sitter bats again, the DH sits
    a.cmpwi("r3", 0).blt("p5_fail")             # (he already sits: nothing to swap)
    a.li("r0", DH_OFF).b("p5_s10p_store")
    L("p5_s10b_k")
    fake("r24", "r6", kreg="r8")                                                            # r24 = bench k
    a.cmpwi("r3", 0).bge("p5_s10b_player")
    fake("r25", "r6")                                                                       # r25 = the DH
    a.b("p5_swap2")
    L("p5_s10b_player")
    a.slwi("r3", "r3", 4).add("r25", "r25", "r3")                                           # r25 = T's entry
    a.slwi("r9", "r6", 1).add("r9", "r9", "r27").addi("r9", "r9", DHSEL).stw("r9", 0x24, "r1")
    a.b("p5_swap")
    L("p5_fail")
    a.li("r3", 0).b("p5_out")
    L("p5_stock")
    a.mr("r3", "r31").mr("r4", "r30").bl("p5_tramp")
    L("p5_out")
    a.leave(8)
    L("p5_tramp")
    a.word(P5[1]).b(P5[0] + 4)

    # D-pad (r3 = task, r4 = p, r5 = -1 / +1 for left / right); -> non-zero if the cursor moved. Bench slot 0 (the
    # DH) is at the field's bottom right: down from C / 1B into it, up to 1B, left to C. Slots 1.. are a column left
    # of the field: left from LF / SS / 3B into it, up / down along it, right back to the field.
    def pre_team_count(team_reg):
        count("r12", team_reg, "r10", "r11")    # r12 = bench count

    def field_pos(dst, x, team):
        """dst = the position of field index x of `team` (dst may be x)."""
        t0 = uniq("fp")
        if dst != x:
            a.mr(dst, x)
        a.cmpwi(team, 0).beq(t0).addi(dst, dst, PRE_FIELD[0] - PRE_FIELD[1])
        L(t0)
        a.addi(dst, dst, -PRE_FIELD[0])

    def team_ok(team, no):
        """Branch to `no` unless `team` is the player's (r4) or a CPU's."""
        own = uniq("own")
        a.cmpw(team, "r4").beq(own)
        is_cpu(team, "r10", no)
        L(own)

    for name, stock in (("p6_up", PRE_UP), ("p6_down", PRE_DOWN), ("p6_side", PRE_SIDE)):
        L(name)
        a.load_addr("r12", D).lbz("r0", SEL_ON, "r12").cmpwi("r0", 0).beq(f"{name}_stock")
        a.slwi("r9", "r4", 2).add("r9", "r9", "r3").lwz("r8", 0x158, "r9")      # r8 = cursor, r9 = task+p*4
        classify("r8", "r6", "r7", "r0")
        a.cmpwi("r7", 4).beq(f"{name}_s10")
        a.cmpwi("r7", 3).bne(f"{name}_field")
        a.mulli("r0", "r6", NB).subf("r7", "r0", "r8").addi("r7", "r7", -PRE_BENCH)   # r7 = k
        if name == "p6_side":
            a.cmpwi("r7", 0).bne("p6_side_col")
            a.cmpwi("r5", 0).bge("p6_side_stay").li("r7", DH_LEFT).b("p6_side_set")   # the DH: left to C
            L("p6_side_col")
            a.cmpwi("r5", 0).blt("p6_side_stay")        # left from the column: stay
            for k in range(1, NB):                      # right: the position beside slot k
                nxt = uniq("back")
                a.cmpwi("r7", k).bne(nxt).li("r7", COLUMN_BACK[k]).b("p6_side_set")
                L(nxt)
            a.b("p6_side_stay")
            L("p6_side_set")                            # r7 = position of team r6: the cursor there (not r0:
            #                                             addi reads r0 as 0)
            a.cmpwi("r6", 0).beq("p6_side_t0").addi("r7", "r7", PRE_FIELD[1] - PRE_FIELD[0])
            L("p6_side_t0")
            a.addi("r7", "r7", PRE_FIELD[0]).stw("r7", 0x158, "r9").li("r3", 1).blr()
            L("p6_side_stay")
            a.li("r3", 0).blr()
        else:                                   # the DH: up to 1B; the column: up / down along it
            a.cmpwi("r7", 0).bne(f"{name}_col")
            if name == "p6_up":
                a.li("r7", DH_UP).b("p6_side_set")
            else:
                a.b(f"{name}_no")
            L(f"{name}_col")
            a.addi("r7", "r7", -1 if name == "p6_up" else 1).cmpwi("r7", 1).blt(f"{name}_no")
            pre_team_count("r6")
            a.cmpw("r7", "r12").bge(f"{name}_no")
            a.addi("r8", "r8", -1 if name == "p6_up" else 1).stw("r8", 0x158, "r9").li("r3", 1).blr()
            L(f"{name}_no")
            a.li("r3", 0).blr()
        # the 10th order slot: left back to slot 9, right stays; up / down move as from slot 9 (stays if they don't)
        L(f"{name}_s10")
        a.mulli("r7", "r6", 9).addi("r7", "r7", 4 + 8)                    # r7 = the team's slot 9 index
        if name == "p6_side":
            a.cmpwi("r5", 0).bge("p6_side_stay")
            a.stw("r7", 0x158, "r9").li("r3", 1).blr()
        else:
            a.stwu("r1", -0x20, "r1").mflr("r0").stw("r0", 0x24, "r1").stw("r9", 0x10, "r1").stw("r8", 0x14, "r1")
            a.stw("r7", 0x158, "r9").bl(stock).cmpwi("r3", 0).bne(f"{name}_s10_out")
            a.lwz("r9", 0x10, "r1").lwz("r8", 0x14, "r1").stw("r8", 0x158, "r9")
            L(f"{name}_s10_out")
            a.lwz("r0", 0x24, "r1").mtlr("r0").addi("r1", "r1", 0x20).blr()
        L(f"{name}_field")
        if name == "p6_side":                   # right from order slot 9 -> the 10th (while bench slot 0 is filled)
            a.cmpwi("r5", 0).blt("p6_side_left").cmpwi("r7", 0).bne("p6_side_stock")
            a.mulli("r10", "r6", 9).addi("r10", "r10", 4 + 8).cmpw("r8", "r10").bne("p6_side_stock")
            team_ok("r6", "p6_side_stock")
            fake("r11", "r6")
            a.lha("r0", 0, "r11").cmpwi("r0", 0).blt("p6_side_stock")
            a.addi("r7", "r6", SLOT10).stw("r7", 0x158, "r9").li("r3", 1).blr()
            L("p6_side_left")                   # left from LF / SS / 3B -> the column, if the team has one
            a.cmpwi("r7", 1).bne("p6_side_stock")
            field_pos("r8", "r8", "r6")
            for pos, k in LEFT_COLUMN:
                nxt = uniq("lc")
                a.cmpwi("r8", pos).bne(nxt).li("r7", k).b("p6_side_k")
                L(nxt)
            a.b("p6_side_stock")
            L("p6_side_k")
            team_ok("r6", "p6_side_stock")      # the other team's bench only if it is a CPU's
            pre_team_count("r6")
            a.cmpwi("r12", 2).blt("p6_side_stock")     # no column (at most the DH)
            a.cmpw("r7", "r12").blt("p6_side_in").addi("r7", "r12", -1)
            L("p6_side_in")
            a.mulli("r0", "r6", NB).add("r7", "r7", "r0").addi("r7", "r7", PRE_BENCH).stw("r7", 0x158, "r9")
            a.li("r3", 1).blr()
        elif name == "p6_down":                 # down from C / 1B -> the DH, if the team has a bench
            a.cmpwi("r7", 1).bne("p6_down_stock")
            field_pos("r8", "r8", "r6")
            for pos in DH_FROM:
                a.cmpwi("r8", pos).beq("p6_down_dh")
            a.b("p6_down_stock")
            L("p6_down_dh")
            team_ok("r6", "p6_down_stock")
            pre_team_count("r6")
            a.cmpwi("r12", 0).beq("p6_down_stock")
            a.mulli("r7", "r6", NB).addi("r7", "r7", PRE_BENCH).stw("r7", 0x158, "r9").li("r3", 1).blr()
        L(f"{name}_stock")
        a.b(stock)

    L("p7")                                     # highlights (r30 = task): bench cursors / held on the field groups
    a.load_addr("r12", D).lbz("r0", SEL_ON, "r12").cmpwi("r0", 0).beq("p7_o")
    for p in range(2):
        for field, (hl, held) in ((0x158, (0x28, False)), (0x160, (0x29, True))):
            nxt = uniq("p7")
            a.lwz("r8", field + 4 * p, "r30")
            classify("r8", "r6", "r7", "r0")
            s10 = uniq("p7_s10")
            a.cmpwi("r7", 4).beq(s10)
            a.cmpwi("r7", 3).bne(nxt)
            a.mulli("r0", "r6", NB).subf("r7", "r0", "r8").addi("r7", "r7", -PRE_BENCH)
            a.mulli("r10", "r6", 0x30).add("r10", "r10", "r30").addi("r10", "r10", 0xCC)   # the team's group
            a.addi("r0", "r7", 9).stb("r0", hl, "r10")
            if held:
                a.li("r0", 1).stb("r0", 0x2E, "r10")
                fake("r11", "r6", kreg="r7")
                a.lha("r0", 0, "r11").sth("r0", 0x2A, "r10")
            a.b(nxt)
            L(s10)                              # the order panel (*(task+0x1C) + team * 0x174)
            a.lwz("r10", 0x1C, "r30").mulli("r0", "r6", 0x174).add("r10", "r10", "r0")
            a.li("r0", SLOT10_WIDGET).stb("r0", 0x166 if held else 0x165, "r10")
            L(nxt)
    L("p7_o")
    a.word(P7[1]).b(P7[0] + 4)

    # P8: the batting-order panels' Base / portrait draws (widget r3). On the positions screen, the order slot of the
    # DH's target draws bench slot 0's entry instead: the panel's pick list (group+8) aimed so that slot reads it.
    for name, (fn, first) in zip(("p8_base", "p8_kao"), P8):
        L(name)
        a.load_addr("r12", D).lbz("r0", SEL_ON, "r12").cmpwi("r0", 0).beq(f"{name}_o")
        a.lbz("r0", ON_ROSTER, "r12").cmpwi("r0", 0).bne(f"{name}_o")
        a.lwz("r0", 0xD8, "r3").cmpwi("r0", 0).bne(f"{name}_o")       # (+0xD8: another source list)
        a.lwz("r0", 0xD4, "r3").cmplwi("r0", 9).bge(f"{name}_o")      # the 9 order slots
        a.enter(4).mr("r31", "r3")
        a.group("r30", "r31", "r12")
        a.lwz("r3", 8, "r30").lbz("r4", 7, "r30").bl("dh_slot")
        a.lwz("r28", 0xD4, "r31").cmpw("r3", "r28").bne(f"{name}_plain")
        a.lwz("r29", 8, "r30").lbz("r3", 7, "r30")
        fake("r12", "r3")
        a.slwi("r0", "r28", 4).subf("r12", "r0", "r12").stw("r12", 8, "r30")    # entry[slot] = bench slot 0
        a.mr("r3", "r31").bl(f"{name}_o")
        a.stw("r29", 8, "r30").b(f"{name}_out")
        L(f"{name}_plain")
        a.mr("r3", "r31").bl(f"{name}_o")
        L(f"{name}_out")
        a.leave(4)
        L(f"{name}_o")                           # the stock draw
        a.word(first).b(fn + 4)

    # P9 (bl at 0x800803CC; caller's 8(r1) = team, f31 / f30 = the pointer): FUN_800663b4(panel) -> order slot or
    # -1; on a miss, the 10th slot's Base widget is tested (FUN_8008e478) and a hit returns the value the caller
    # turns into SLOT10 + team (it adds 4 / 0xD)
    L("p9")
    a.stwu("r1", -0x20, "r1").mflr("r0").stw("r0", 0x24, "r1")
    a.lwz("r0", 0x28, "r1").stw("r0", 0x10, "r1")
    a.bl(PANEL_HIT).cmpwi("r3", 0).bge("p9_out")
    a.load_addr("r12", D).lbz("r0", SEL_ON, "r12").cmpwi("r0", 0).beq("p9_miss")
    a.lbz("r0", ON_ROSTER, "r12").cmpwi("r0", 0).bne("p9_miss")
    a.lwz("r11", 0x10, "r1")
    fake("r10", "r11")
    a.lha("r0", 0, "r10").cmpwi("r0", 0).blt("p9_miss")
    a.slwi("r11", "r11", 2).load_addr("r12", D + SLOT10W).lwzx("r3", "r12", "r11").cmpwi("r3", 0).beq("p9_miss")
    a.fmr("f1", "f31").fmr("f2", "f30").bl(HIT).cmpwi("r3", 0).beq("p9_miss")
    a.lwz("r0", 0x10, "r1").cmpwi("r0", 0).bne("p9_t1")
    a.li("r3", SLOT10 - 4).b("p9_out")
    L("p9_t1")
    a.li("r3", SLOT10 + 1 - 0xD).b("p9_out")
    L("p9_miss")
    a.li("r3", -1)
    L("p9_out")
    a.lwz("r0", 0x24, "r1").mtlr("r0").addi("r1", "r1", 0x20).blr()

    L("card")                                   # the info card's FUN_80082684(task, index, &t, &slot)
    a.load_addr("r12", D).lbz("r0", SEL_ON, "r12").cmpwi("r0", 0).beq("card_o")
    a.cmpwi("r4", PRE_BENCH).blt("card_order").cmpwi("r4", PRE_BENCH + 2 * NB).bge("card_s10")
    classify("r4", "r9", "r10", "r0")
    a.mulli("r0", "r9", NB).subf("r10", "r0", "r4").addi("r10", "r10", -PRE_BENCH)
    fake("r11", "r9", kreg="r10")
    a.lha("r0", 0, "r11").cmpwi("r0", 0).blt("card_none")
    a.stw("r9", 0, "r5").li("r0", 0).stw("r0", 0, "r6")
    a.load_addr("r12", D).stw("r11", CARD, "r12").li("r3", 1).blr()   # the read below takes our entry
    L("card_none")
    a.li("r3", 0).blr()
    L("card_s10")                               # the 10th order slot: whoever sits there (his entry, or the DH's)
    a.cmpwi("r4", SLOT10 + 2).bge("card_o")
    a.enter(4).mr("r31", "r5").mr("r30", "r6").addi("r29", "r4", -SLOT10).mr("r28", "r3")
    fake("r11", "r29")
    a.lha("r0", 0, "r11").cmpwi("r0", 0).blt("card_s10_none")
    a.slwi("r0", "r29", 2).add("r3", "r28", "r0").lwz("r3", 0xC0, "r3").mr("r4", "r29").bl("dh_slot")
    a.stw("r29", 0, "r31").cmpwi("r3", 0).blt("card_s10_dh")
    a.stw("r3", 0, "r30").li("r3", 1).b("card_s10_out")
    L("card_s10_dh")
    fake("r11", "r29")
    a.li("r0", 0).stw("r0", 0, "r30").load_addr("r12", D).stw("r11", CARD, "r12").li("r3", 1).b("card_s10_out")
    L("card_s10_none")
    a.li("r3", 0)
    L("card_s10_out")
    a.leave(4)
    L("card_order")                             # an order slot (4..0x15): the DH's target's shows the DH's card, as
    a.cmpwi("r4", 4).blt("card_o").cmpwi("r4", 0x16).bge("card_o")    # P8 shows him there
    a.enter(4).mr("r31", "r5").mr("r30", "r6").mr("r29", "r3")
    a.bl(PRE_ENTRY).mr("r28", "r3").cmpwi("r3", 0).beq("card_order_out")
    a.lwz("r4", 0, "r31").slwi("r0", "r4", 2).add("r3", "r29", "r0").lwz("r3", 0xC0, "r3").bl("dh_slot")
    a.lwz("r0", 0, "r30").cmpw("r3", "r0").bne("card_order_out")
    a.lwz("r3", 0, "r31")
    fake("r11", "r3")
    a.load_addr("r12", D).stw("r11", CARD, "r12").li("r0", 0).stw("r0", 0, "r30")   # entry 0 of our list
    L("card_order_out")
    a.mr("r3", "r28").leave(4)
    L("card_o")
    a.b(PRE_ENTRY)

    L("card_read")                              # 0x8007E844: lwz r4,0xc0(r4) = the team's pick list
    a.load_addr("r12", D).lwz("r11", CARD, "r12").cmpwi("r11", 0).beq("card_read_o")
    a.mr("r4", "r11").li("r0", 0).stw("r0", CARD, "r12").b(PRE_CARD_READ[0] + 4)
    L("card_read_o")
    a.word(PRE_CARD_READ[1]).b(PRE_CARD_READ[0] + 4)

    # ================= match =================
    L("m1_count")                               # voice loop: NB more slots per team while the bench is valid
    a.word(M1_COUNT[1])
    a.load_addr("r12", D).lbz("r12", VALID, "r12").cmpwi("r12", 0).beq("m1c_out")
    a.li("r12", NB).add("r0", "r0", "r12")      # not addi: addi with rA = r0 reads 0 (the count became NB, not + NB)
    L("m1c_out")
    a.b(M1_COUNT[0] + 4)

    L("m1_id")                                  # r4 = slot * 0x8E, r0 = team's roster; slots 9.. = the bench
    a.lbz("r12", 0x10, "r30").extsb("r12", "r12").cmpwi("r12", 9).blt("m1i_norm")
    a.lbz("r11", 0xE, "r30").extsb("r11", "r11").mulli("r11", "r11", NB).add("r12", "r12", "r11")
    a.addi("r12", "r12", -9).mulli("r12", "r12", REC_STRIDE).load_addr("r11", D + REC).lhax("r12", "r11", "r12")
    a.cmpwi("r12", 0).blt("m1i_slot0").mr("r0", "r12").b("m1i_out")
    L("m1i_slot0")                              # an empty bench slot: slot 0's character again
    a.li("r4", 0)
    L("m1i_norm")
    a.word(M1_ID[1])
    L("m1i_out")
    a.b(M1_ID[0] + 4)

    L("m2")                                     # pause menu (r4 = menu): the batting menu, "Substitute" second
    a.cmpwi("r4", 0x5E).bne("m2_o")
    a.load_addr("r12", D).lbz("r11", VALID, "r12").cmpwi("r11", 0)
    a.addi("r12", "r12", MENU_ON).bne("m2_copy").addi("r12", "r12", MENU_OFF - MENU_ON)
    L("m2_copy")
    a.load_addr("r11", BATTING_MENU)
    for i in range(0, 0x28, 4):
        a.lwz("r0", i, "r12").stw("r0", i, "r11")
    L("m2_o")
    a.word(M2[1]).b(M2[0] + 4)

    for name, mode in (("m3_def", 1), ("m3_sub", 2)):
        L(name)                                 # pause result 10 / 11 -> our mode, then the defense state
        a.load_addr("r12", D).li("r11", mode).stb("r11", MODE, "r12").li("r11", 0)
        a.stb("r11", NCHG, "r12").stb("r11", STEP, "r12").stb("r11", BD, "r12")
        a.b(DEFENSE_CASE)

    L("m4")                                     # FUN_803176bc: the screen's team (r3 = game)
    a.load_addr("r12", D).lbz("r12", MODE, "r12").cmpwi("r12", 2).beq("m4_bat")
    a.lbz("r3", 0x2B, "r3").b(M4[0] + 4)
    L("m4_bat")
    a.lbz("r3", 0x2A, "r3").b(M4[0] + 4)

    L("m5")                                     # the defense task constructor (r28 = task)
    a.load_addr("r12", D).lwz("r11", 8, "r28").stb("r11", TEAM, "r12")
    for i in range(9 + NB):
        a.li("r0", i).stb("r0", SRC + i, "r12")
    for i in range(9):
        e = SCR + 0x10 * i
        a.li("r0", -1).sth("r0", e, "r12").stb("r0", e + 0xC, "r12")
        a.li("r0", 0).stw("r0", e + 4, "r12").stw("r0", e + 8, "r12").stb("r0", e + 0xD, "r12")
    a.li("r0", 0).stb("r0", NBEN, "r12")
    a.lbz("r0", VALID, "r12").cmpwi("r0", 0).beq("m5_o")
    a.lbz("r0", MODE, "r12").cmpwi("r0", 0).beq("m5_o")
    a.lbz("r11", TEAM, "r12").mulli("r11", "r11", NB * REC_STRIDE).add("r11", "r11", "r12").addi("r11", "r11", REC)
    a.addi("r10", "r12", SCR).li("r9", 0)
    L("m5_loop")
    a.cmpwi("r9", NB).bge("m5_o")
    a.lha("r0", 0, "r11").cmpwi("r0", 0).blt("m5_o")
    a.sth("r0", 0, "r10").addi("r0", "r9", 9).stb("r0", 0xC, "r10").lbz("r0", 0x8D, "r11").stb("r0", 0xD, "r10")
    a.addi("r9", "r9", 1).stb("r9", NBEN, "r12")
    a.addi("r10", "r10", 0x10).addi("r11", "r11", REC_STRIDE).b("m5_loop")
    L("m5_o")
    a.word(M5[1]).b(M5[0] + 4)

    L("m6")                                     # the cell loop (r15 = group, r18 = cell)
    a.load_addr("r12", D).lbz("r11", 0xC, "r15").cmpwi("r11", 0).beq("m6_match")
    a.lbz("r11", SEL_ON, "r12").cmpwi("r11", 0).beq("m6_9")           # positions screen: the team's bench
    a.lbz("r9", 7, "r15")
    count("r11", "r9", "r10", "r12")
    a.addi("r11", "r11", 9).cmpw("r18", "r11").b(M6[0] + 4)
    L("m6_match")
    a.lbz("r11", VALID, "r12").cmpwi("r11", 0).beq("m6_9")
    a.lbz("r11", MODE, "r12").cmpwi("r11", 0).beq("m6_9")
    a.lbz("r11", NBEN, "r12").addi("r11", "r11", 9).cmpw("r18", "r11").b(M6[0] + 4)
    L("m6_9")
    a.word(M6[1]).b(M6[0] + 4)

    for i, (fn, first) in enumerate(CELL_DRAWS):
        L(f"m7_{i}")                            # cell >= 9: the group's entries are our list
        a.lwz("r12", 0xD4, "r3").cmpwi("r12", 9).bge(f"m7_{i}_swap")
        a.word(first).b(fn + 4)
        L(f"m7_{i}_swap")
        a.enter(3).mr("r31", "r3")
        a.bl("cellgrey")
        a.group("r30", "r31", "r12")
        a.lwz("r29", 8, "r30")
        a.lbz("r0", 0xC, "r30").cmpwi("r0", 0).beq(f"m7_{i}_scr")
        a.lbz("r3", 7, "r30")                   # the positions screen: the team's bench list
        fake("r12", "r3")
        a.b(f"m7_{i}_set")
        L(f"m7_{i}_scr")
        a.load_addr("r12", D + SCR)
        L(f"m7_{i}_set")
        a.stw("r12", 8, "r30")
        a.mr("r3", "r31").bl(f"m7_{i}_tramp")
        a.stw("r29", 8, "r30")
        a.leave(3)
        L(f"m7_{i}_tramp")
        a.word(first).b(fn + 4)

    def on_bench(reg, no, tmp, dreg):
        """Branch to `no` unless cursor index `reg` is a bench cell of the defense screen (dreg = D)."""
        a.cmpwi(reg, BENCH_CELL).blt(no).lbz(tmp, NBEN, dreg).addi(tmp, tmp, BENCH_CELL).cmpw(reg, tmp).bge(no)

    L("cellgrey")                               # leaf: widget r3 of cell >= 9 -> grey, or dark if subbed out
    a.group("r11", "r3", "r12")
    a.lbz("r0", 0xC, "r11").cmpwi("r0", 0).bne("cg_grey")            # positions screen: nobody is out
    a.load_addr("r12", D).lwz("r10", 0xD4, "r3").add("r10", "r10", "r12").lbz("r10", SRC, "r10")   # SRC[cell]
    a.cmpwi("r10", 9).blt("cg_grey")            # a field player benched this visit: not out until OK
    a.lbz("r9", TEAM, "r12").mulli("r9", "r9", NB).add("r9", "r9", "r10").add("r9", "r9", "r12")
    a.lbz("r0", OUT - 9, "r9").cmpwi("r0", 0).beq("cg_grey")
    a.grey("r3", "r12", DARK).blr()
    L("cg_grey")
    a.grey("r3", "r12").blr()

    # dh_cell(cell widget r3) -> r3 = 0, 1 (the DH's target, who doesn't bat: grey), 2 ("DH" beside it: the DH), 3
    # ("DH" dimmed: bench slot 0 while there is no DH, so the slot is always marked) or 4 ("FO" beside it: the batting
    # team's cell 9, where the target waits while the DH bats in his slot)
    L("dh_cell")
    a.enter(4).mr("r31", "r3").load_addr("r29", D)
    a.group("r30", "r31", "r12")
    a.lwz("r28", 0xD4, "r31")                   # r28 = cell (= position below 9)
    a.lbz("r0", 0xC, "r30").cmpwi("r0", 0).beq("dhc_match")
    a.lbz("r0", SEL_ON, "r29").cmpwi("r0", 0).beq("dhc_none")      # the positions screen: the team's choice
    a.lwz("r3", 8, "r30").lbz("r4", 7, "r30").bl("dh_slot").mr("r27", "r3")
    a.cmpwi("r28", 9).bne("dhc_pfield")         # cell 9 exists only while bench slot 0 is filled
    a.cmpwi("r27", 0).blt("dhc_off").b("dhc_dh")
    L("dhc_pfield")
    a.cmpwi("r27", 0).blt("dhc_none").b("dhc_target")
    L("dhc_match")                              # the defense screen: fielding (mode 1) or batting (mode 2) team
    a.lbz("r0", VALID, "r29").cmpwi("r0", 0).beq("dhc_none")
    a.lbz("r0", MODE, "r29").cmpwi("r0", 0).beq("dhc_none")
    a.lbz("r9", TEAM, "r29").add("r9", "r9", "r29").lbz("r27", DHFOR, "r9").extsb("r27", "r27")
    a.cmpwi("r27", 0).bge("dhc_on")
    a.cmpwi("r28", 9).beq("dhc_off").b("dhc_none")  # no DH: cell 9 (bench slot 0) dimmed
    L("dhc_on")
    a.lbz("r0", MODE, "r29").cmpwi("r0", 1).bne("dhc_bat")
    a.cmpwi("r28", 9).beq("dhc_dh")             # fielding: the DH sits at cell 9
    L("dhc_target")                             # the target slot's cell: grey
    a.cmpwi("r28", 9).bge("dhc_none")
    a.lwz("r9", 8, "r30").slwi("r0", "r27", 4).add("r9", "r9", "r0").lbz("r0", 0xC, "r9").extsb("r0", "r0")
    a.cmpw("r0", "r28").bne("dhc_none").li("r3", 1).b("dhc_out")
    L("dhc_bat")                                # batting: the DH is in the target's slot, at the target's cell
    a.cmpwi("r28", 9).beq("dhc_fo").bgt("dhc_none")   # cell 9: the target (bench record 0), sitting: "FO"
    a.lwz("r9", 8, "r30").slwi("r0", "r27", 4).add("r9", "r9", "r0").lbz("r0", 0xC, "r9").extsb("r0", "r0")
    a.cmpw("r0", "r28").bne("dhc_none")
    L("dhc_dh")
    a.li("r3", 2).b("dhc_out")
    L("dhc_off")
    a.li("r3", 3).b("dhc_out")
    L("dhc_fo")
    a.li("r3", 4).b("dhc_out")
    L("dhc_none")
    a.li("r3", 0)
    L("dhc_out")
    a.leave(4)

    # num_cell(cell widget r3) -> r3 = the batting-order spot 1..9 of whoever is at this cell of the defense screen,
    # or 0: the slot whose entry sits at the cell (the screen's list is indexed by roster slot, so a sub or a move
    # during the visit shows where he will bat), its spot in the batting team's lineup (L = *(r13-0x15A8), lineup
    # team = TEAM ^ G+0x29, L+0xC+T*0x28+k*4 = slot). The DH (fielding team: cell 9) shows his target's spot, the
    # target (who sits) and bench cells none; on the batting team's screen the DH is in the target's slot anyway.
    L("num_cell")
    a.enter(4).mr("r31", "r3").load_addr("r29", D)
    a.group("r30", "r31", "r12")
    a.lbz("r0", 0xC, "r30").cmpwi("r0", 0).bne("nc_none")          # the positions screen: none
    a.lbz("r0", VALID, "r29").cmpwi("r0", 0).beq("nc_none")
    a.lbz("r0", MODE, "r29").cmpwi("r0", 0).beq("nc_none")
    a.lbz("r9", TEAM, "r29").add("r9", "r9", "r29").lbz("r27", DHFOR, "r9").extsb("r27", "r27")   # r27 = DHFOR
    a.lwz("r10", 0xD4, "r31").cmpwi("r10", 9).blt("nc_field")
    a.bne("nc_none")                            # bench cells 10..: none
    a.lbz("r0", MODE, "r29").cmpwi("r0", 1).bne("nc_none")          # cell 9 on the fielding screen: the DH
    a.cmpwi("r27", 0).blt("nc_none").mr("r28", "r27").b("nc_slot")
    L("nc_field")
    a.lwz("r11", 8, "r30").li("r28", 0)
    L("nc_find")
    a.lbz("r0", 0xC, "r11").extsb("r0", "r0").cmpw("r0", "r10").beq("nc_found")
    a.addi("r11", "r11", 0x10).addi("r28", "r28", 1).cmpwi("r28", 9).blt("nc_find").b("nc_none")
    L("nc_found")
    a.lbz("r0", MODE, "r29").cmpwi("r0", 1).bne("nc_slot")          # fielding: the DH's target doesn't bat
    a.cmpw("r28", "r27").beq("nc_none")
    L("nc_slot")                                # r28 = roster slot
    a.bl(GAME).lbz("r4", 0x29, "r3").lbz("r0", TEAM, "r29").xor("r4", "r4", "r0")
    a.mulli("r4", "r4", 0x28).lwz("r9", -0x15A8, 13).add("r9", "r9", "r4").addi("r9", "r9", 0xC).li("r3", 0)
    L("nc_loop")
    a.lha("r0", 0, "r9").cmpw("r0", "r28").beq("nc_hit")
    a.addi("r9", "r9", 4).addi("r3", "r3", 1).cmpwi("r3", 9).blt("nc_loop").b("nc_none")
    L("nc_hit")
    a.addi("r3", "r3", 1).b("nc_out")
    L("nc_none")
    a.li("r3", 0)
    L("nc_out")
    a.leave(4)

    L("run_cell")                               # leaf: run_cell(cell widget r3) -> r3 = 1..3, the base of the runner
    a.lwz("r10", 0xD4, "r3").cmpwi("r10", 9).bge("rc_none")      # in this field cell's slot, or 0 (the batting
    a.group("r11", "r3", "r12")                                    # team's defense screen only)
    a.lbz("r0", 0xC, "r11").cmpwi("r0", 0).bne("rc_none")          # the positions screen: nobody on base
    a.load_addr("r12", D).lbz("r0", VALID, "r12").cmpwi("r0", 0).beq("rc_none")
    a.lbz("r0", MODE, "r12").cmpwi("r0", 2).bne("rc_none")
    a.lwz("r11", 8, "r11").li("r9", 0)          # the slot whose entry sits at this cell (list index = roster slot)
    L("rc_find")
    a.lbz("r0", 0xC, "r11").extsb("r0", "r0").cmpw("r0", "r10").beq("rc_slot")
    a.addi("r11", "r11", 0x10).addi("r9", "r9", 1).cmpwi("r9", 9).blt("rc_find").b("rc_none")
    L("rc_slot")
    a.load_addr("r12", RUNNERS).li("r3", 1)
    L("rc_loop")                                # runners 1..3 = on 1st..3rd; +0x176 == 1 on base, +0x28 his slot
    a.slwi("r0", "r3", 2).lwzx("r11", "r12", "r0").cmpwi("r11", 0).beq("rc_next")
    a.lbz("r0", 0x176, "r11").cmpwi("r0", 1).bne("rc_next")
    a.lha("r0", 0x28, "r11").cmpw("r0", "r9").beq("rc_out")
    L("rc_next")
    a.addi("r3", "r3", 1).cmpwi("r3", 4).blt("rc_loop")
    L("rc_none")
    a.li("r3", 0)
    L("rc_out")
    a.blr()

    # label(cell widget r3, UTF-16 text r4 (0: a picture: element r6, nodes r7 .. r7 or all if -1), x offset f1,
    # colour r5): the text / picture beside the cell, with the cell's matrix (its scale too) and alpha
    MTX, COL, WS, LF = 0x20, 0x50, 0x68, 0x80   # locals: the label's matrix (0x30), colour (vtable, r, g, b, a),
    #                                             the widescreen flags saved
    L("label")
    a.stwu("r1", -LF, "r1").mflr("r0").stw("r0", LF + 4, "r1").stw("r31", LF - 4, "r1").stw("r30", LF - 8, "r1")
    a.mr("r31", "r3").mr("r30", "r4").stw("r6", WS + 8, "r1").stw("r7", WS + 12, "r1")
    for i in range(0, 0x30, 4):                 # the cell's matrix, moved by f1
        a.lwz("r0", 0x60 + i, "r31").stw("r0", MTX + i, "r1")
    a.lfs("f0", MTX + 0xC, "r1").fadds("f0", "f0", "f1").stfs("f0", MTX + 0xC, "r1")
    a.lwz("r0", 0xA4, "r31").stw("r0", COL, "r1")
    a.stw("r5", COL + 4, "r1").stw("r5", COL + 8, "r1").stw("r5", COL + 0xC, "r1")
    a.lwz("r0", 0xB4, "r31").stw("r0", COL + 0x10, "r1")
    a.addi("r0", "r1", MTX).stw("r0", 8, "r1").addi("r0", "r1", COL).stw("r0", 0xC, "r1")
    a.li("r0", 0).stw("r0", 0x10, "r1").stw("r0", 0x1C, "r1").li("r0", -1).stw("r0", 0x14, "r1")
    a.lbz("r0", 0xC3, "r31").stw("r0", 0x18, "r1")
    a.cmpwi("r30", 0).beq("label_pic")
    a.mr("r3", "r30").li("r4", -1).li("r5", 1).li("r6", 0)
    a.lwz("r7", 0xB8, "r31").lwz("r8", 0xBC, "r31").li("r9", 0).li("r10", DH_TEXT_ELEMENT).bl(TEXT)
    a.b("label_out")
    L("label_pic")                              # one key at time 0: any time draws it
    # The widgets' draw (FUN_8008e6c0) turns on the layout's widescreen x fit around its element draw when the
    # widget has it (+0xC3, set by that draw this frame): r13-0x244C = 1, layout+0x28 = 1, layout+0x20 = the r2
    # constant; FUN_8050a5ac then squeezes x (4:3 in 16:9). Without it the picture landed at 4/3 x its place from
    # the screen's left edge, 4/3 wide (Nick's showcase-19 crop: "DH is written too far away"). The text path gets
    # the same from its +0xC3 argument.
    a.lwz("r3", 0xB8, "r31")
    a.lbz("r0", -0x244C, 13).stb("r0", WS, "r1").lbz("r0", 0x28, "r3").stb("r0", WS + 1, "r1")
    a.lwz("r0", 0x20, "r3").stw("r0", WS + 4, "r1")
    a.lbz("r0", 0xC3, "r31").cmpwi("r0", 0).beq("label_ws")
    a.li("r0", 1).stb("r0", -0x244C, 13).stb("r0", 0x28, "r3").lwz("r0", -0x7F50, 2).stw("r0", 0x20, "r3")
    L("label_ws")
    a.li("r4", 0).lwz("r5", WS + 8, "r1").addi("r6", "r1", MTX).addi("r7", "r1", COL)
    a.lwz("r8", WS + 12, "r1").mr("r9", "r8").lwz("r10", 0xBC, "r31").bl(ELEMENT_DRAW)
    a.lwz("r3", 0xB8, "r31")
    a.lbz("r0", WS, "r1").stb("r0", -0x244C, 13).lbz("r0", WS + 1, "r1").stb("r0", 0x28, "r3")
    a.lwz("r0", WS + 4, "r1").stw("r0", 0x20, "r3")
    L("label_out")
    a.lwz("r31", LF - 4, "r1").lwz("r30", LF - 8, "r1").lwz("r0", LF + 4, "r1").mtlr("r0")
    a.addi("r1", "r1", LF).blr()

    # the cell's disc: grey (dark if out) for cells 9..; the DH's target grey; "DH" beside the DH's cell; "1B" / "2B" /
    # "3B" beside a runner's cell on the batting team's screen (pinch runners)
    L("m7_base")
    a.stwu("r1", -0x20, "r1").mflr("r0").stw("r0", 0x24, "r1").stw("r31", 0x1C, "r1").stw("r30", 0x18, "r1")
    a.mr("r31", "r3").bl("dh_cell").mr("r30", "r3")
    a.lwz("r0", 0xD4, "r31").cmpwi("r0", 9).blt("m7b_field")
    a.mr("r3", "r31").bl("cellgrey").b("m7b_draw")
    L("m7b_field")                              # cells 0..8: grey the target; undo our grey (only ours) otherwise
    a.cmpwi("r30", 1).bne("m7b_white")
    a.grey("r31", "r12").b("m7b_draw")
    L("m7b_white")
    a.lwz("r0", 0x94, "r31").lis("r12", GREY >> 16).ori("r12", "r12", GREY & 0xFFFF).cmpw("r0", "r12").bne("m7b_draw")
    a.grey("r31", "r12", WHITE)
    L("m7b_draw")
    a.mr("r3", "r31").bl("m7_base_o")
    a.lbz("r0", 0xC2, "r31").cmpwi("r0", 0).beq("m7b_out")          # the group is shown
    a.cmpwi("r30", 4).beq("m7b_fo")
    a.cmpwi("r30", 2).blt("m7b_run")            # "DH": white while he is the DH, grey while there is none
    a.lis("r5", WHITE >> 16).beq("m7b_dh")
    a.lis("r5", GREY >> 16).ori("r5", "r5", GREY & 0xFFFF)
    L("m7b_dh")                                 # the "DH" picture: cell 9 (a bench cell) DHDX left of it, node 0
    a.load_addr("r12", D).lfs("f1", DHDX, "r12").li("r7", 0)
    a.lwz("r0", 0xD4, "r31").cmpwi("r0", 9).bge("m7b_dhdraw")
    a.lfs("f1", NUMDX, "r12").li("r7", DH_ABOVE_NODE)    # a field cell (the DH at bat): above the face, centred
    L("m7b_dhdraw")
    a.li("r4", 0).mr("r3", "r31").li("r6", DH_ELEMENT).bl("label")
    a.b("m7b_run")
    L("m7b_fo")                                 # the batting team's cell 9: the target, who doesn't bat: "FO"
    a.load_addr("r12", D).lfs("f1", DHDX, "r12").li("r4", 0).lis("r5", WHITE >> 16).mr("r3", "r31")
    a.li("r6", FO_ELEMENT).li("r7", -1).bl("label")
    L("m7b_run")
    a.mr("r3", "r31").bl("run_cell").cmpwi("r3", 0).beq("m7b_num")
    a.slwi("r3", "r3", 3).load_addr("r4", D + BASETXT - 8).add("r4", "r4", "r3")
    a.load_addr("r12", D).lfs("f1", BASEDX, "r12").lis("r5", WHITE >> 16).mr("r3", "r31").bl("label")
    L("m7b_num")                                # the batting-order number (defense screen)
    a.mr("r3", "r31").bl("num_cell").cmpwi("r3", 0).beq("m7b_out")
    a.addi("r7", "r3", -1).li("r6", NUM_ELEMENT).li("r4", 0).lis("r5", WHITE >> 16).mr("r3", "r31")
    a.load_addr("r12", D).lfs("f1", NUMDX, "r12").bl("label")
    L("m7b_out")
    a.li("r3", 0).lwz("r31", 0x1C, "r1").lwz("r30", 0x18, "r1").lwz("r0", 0x24, "r1").mtlr("r0")
    a.addi("r1", "r1", 0x20).blr()
    L("m7_base_o")
    a.word(CELL_BASE[1]).b(CELL_BASE[0] + 4)

    L("balloon")                                # FUN_8031ce10(widget, ...): a bench index searches our list
    a.load_addr("r12", D).lbz("r11", VALID, "r12").cmpwi("r11", 0).beq("balloon_o")
    a.lbz("r11", MODE, "r12").cmpwi("r11", 0).beq("balloon_o")
    a.group("r10", "r3", "r11").cmpwi("r10", 0).beq("balloon_o").addi("r10", "r10", -8)   # r10 = order task
    a.lwz("r11", 0x8C, "r10").lwz("r0", 0xCC, "r3").cmpwi("r11", 0).bge("balloon_held")
    a.cmpwi("r0", 0).bne("balloon_o").lwz("r11", 0x88, "r10").b("balloon_idx")
    L("balloon_held")
    a.cmpwi("r0", 0).beq("balloon_idx").lwz("r11", 0x88, "r10")
    L("balloon_idx")
    on_bench("r11", "balloon_o", "r9", "r12")
    a.enter(2).mr("r31", "r10").lwz("r30", 0x24, "r31")
    a.load_addr("r12", D + SCR).stw("r12", 0x24, "r31")
    a.bl("balloon_o")
    a.stw("r30", 0x24, "r31").leave(2)
    L("balloon_o")
    a.word(BALLOON[1]).b(BALLOON[0] + 4)

    L("m8_v")                                   # D-pad up / down (r3 = order task, r4 = -1 up / +1 down)
    a.load_addr("r12", D).lbz("r11", VALID, "r12").cmpwi("r11", 0).beq("m8v_o")
    a.lbz("r11", MODE, "r12").cmpwi("r11", 0).beq("m8v_o")
    a.lwz("r11", 0x88, "r3")
    on_bench("r11", "m8v_field", "r10", "r12")
    a.cmpwi("r11", BENCH_CELL).bne("m8v_col")   # the DH: up to 1B, down stays
    a.cmpwi("r4", 0).bge("m8v_stay").li("r11", DH_UP + 2).b("m8v_set")
    L("m8v_col")                                # the column (cells 1..): along it
    a.add("r11", "r11", "r4").cmpwi("r11", BENCH_CELL + 1).blt("m8v_stay").cmpw("r11", "r10").bge("m8v_stay")
    L("m8v_set")
    a.stw("r11", 0x88, "r3")
    L("m8v_stay")
    a.li("r0", 0).stb("r0", 0x7C, "r3").blr()
    L("m8v_field")                              # down from C / 1B -> the DH
    a.cmpwi("r4", 0).blt("m8v_o").lbz("r10", NBEN, "r12").cmpwi("r10", 0).beq("m8v_o")
    for pos in DH_FROM:
        a.cmpwi("r11", pos + 2).beq("m8v_dh")
    a.b("m8v_o")
    L("m8v_dh")
    a.li("r11", BENCH_CELL).b("m8v_set")
    L("m8v_o")
    a.b(VPAD_FN)

    L("m8_h")                                   # D-pad left / right (r4 = -1 / +1)
    a.load_addr("r12", D).lbz("r11", VALID, "r12").cmpwi("r11", 0).beq("m8h_o")
    a.lbz("r11", MODE, "r12").cmpwi("r11", 0).beq("m8h_o")
    a.lwz("r11", 0x88, "r3")
    on_bench("r11", "m8h_field", "r10", "r12")
    a.cmpwi("r11", BENCH_CELL).bne("m8h_col")   # the DH: left to C, right stays
    a.cmpwi("r4", 0).bge("m8h_stay").li("r0", DH_LEFT + 2).b("m8h_set")
    L("m8h_col")
    a.cmpwi("r4", 0).blt("m8h_stay")            # left from the column: stay; right: back beside it
    a.addi("r11", "r11", -BENCH_CELL)
    for k in range(1, NB):
        nxt = uniq("m8b")
        a.cmpwi("r11", k).bne(nxt).li("r0", COLUMN_BACK[k] + 2).b("m8h_set")
        L(nxt)
    a.b("m8h_stay")
    L("m8h_field")                              # left from LF / SS / 3B -> the column (bench cells 1..)
    a.cmpwi("r4", 0).bge("m8h_o").lbz("r10", NBEN, "r12").cmpwi("r10", 2).blt("m8h_o")
    for pos, k in LEFT_COLUMN:
        nxt = uniq("m8l")
        a.cmpwi("r11", pos + 2).bne(nxt).li("r11", k).b("m8h_bench")
        L(nxt)
    a.b("m8h_o")
    L("m8h_bench")                              # (r11, not r0: addi reads r0 as 0)
    a.cmpw("r11", "r10").blt("m8h_in").addi("r11", "r10", -1)
    L("m8h_in")
    a.addi("r0", "r11", BENCH_CELL)
    L("m8h_set")
    a.stw("r0", 0x88, "r3")
    L("m8h_stay")
    a.li("r0", 0).stb("r0", 0x7C, "r3").blr()
    L("m8h_o")
    a.b(HPAD_FN)

    L("m9")                                     # A on a cell (r3 = order task): bench swaps
    a.enter(6).mr("r31", "r3").load_addr("r28", D)
    a.lbz("r0", VALID, "r28").cmpwi("r0", 0).beq("m9_orig")
    a.lbz("r0", MODE, "r28").cmpwi("r0", 0).beq("m9_orig")
    a.lwz("r30", 0x88, "r31").lwz("r29", 0x8C, "r31")
    # DH rules (DHFOR[TEAM] >= 0): 0x1C(r1) = 1 on the fielding team's screen (the DH is at cell 9), 2 on the
    # batting team's (cell 9 holds the player he bats for, who is locked), 0 without a DH
    a.lbz("r11", TEAM, "r28").add("r11", "r11", "r28").lbz("r0", DHFOR, "r11").extsb("r0", "r0")
    a.li("r11", 0).cmpwi("r0", 0).blt("m9_dhs").lbz("r11", MODE, "r28")
    L("m9_dhs")
    a.stw("r11", 0x1C, "r1")
    a.cmpwi("r11", 2).bne("m9_nolock")
    a.cmpwi("r30", BENCH_CELL).beq("m9_fail").cmpwi("r29", BENCH_CELL).beq("m9_fail")
    L("m9_nolock")
    a.cmpwi("r29", 0).bge("m9_picked")
    on_bench("r30", "m9_orig", "r10", "r28")    # nothing held: pick up a bench player
    a.stw("r30", 0x8C, "r31").addi("r0", "r30", -BENCH_CELL).slwi("r0", "r0", 4).add("r9", "r28", "r0")
    a.addi("r3", "r31", 0x94).lha("r4", SCR, "r9").bl(SET_ENTRY)
    a.li("r0", 0).stb("r0", 0xA0, "r31").li("r3", 1).b("m9_out")
    L("m9_picked")
    a.cmpwi("r29", BENCH_CELL).blt("m9_p2")
    a.cmpw("r29", "r30").beq("m9_drop")                 # the same bench slot again: put him back
    a.cmpwi("r30", BENCH_CELL).bge("m9_bb")
    a.mr("r27", "r29").b("m9_swap")                     # r27 = bench cell, r30 = the player's cell
    L("m9_p2")
    a.cmpwi("r30", BENCH_CELL).blt("m9_both")
    a.mr("r27", "r30").mr("r30", "r29").b("m9_swap")
    L("m9_both")
    a.lbz("r0", MODE, "r28").cmpwi("r0", 2).beq("m9_fail")   # the batting team keeps its positions
    a.b("m9_orig")
    L("m9_bb")                                          # two bench slots: just their order
    a.lwz("r0", 0x1C, "r1").cmpwi("r0", 1).bne("m9_bb_go")   # fielding with a DH: who moves to the DH cell?
    a.cmpwi("r29", BENCH_CELL).bne("m9_bb_h").mr("r9", "r30").b("m9_bb_new")
    L("m9_bb_h")
    a.cmpwi("r30", BENCH_CELL).bne("m9_bb_go").mr("r9", "r29")
    L("m9_bb_new")                                      # the new DH: a bench player who never left the game
    a.addi("r9", "r9", 9 - BENCH_CELL).add("r9", "r9", "r28").lbz("r0", SRC, "r9")
    a.cmpwi("r0", 9).blt("m9_fail").beq("m9_bb_go")     # a fielder benched this visit can't; the DH himself can
    a.lbz("r11", TEAM, "r28").mulli("r11", "r11", NB).add("r11", "r11", "r0").add("r11", "r11", "r28")
    a.lbz("r0", OUT - 9, "r11").cmpwi("r0", 0).bne("m9_fail")
    L("m9_bb_go")
    a.addi("r26", "r29", -BENCH_CELL).addi("r27", "r30", -BENCH_CELL)
    a.slwi("r9", "r26", 4).add("r9", "r9", "r28").slwi("r10", "r27", 4).add("r10", "r10", "r28")
    a.lha("r0", SCR, "r9").lha("r11", SCR, "r10").sth("r11", SCR, "r9").sth("r0", SCR, "r10")
    a.lbz("r0", SCR + 0xD, "r9").lbz("r11", SCR + 0xD, "r10").stb("r11", SCR + 0xD, "r9").stb("r0", SCR + 0xD, "r10")
    a.add("r9", "r28", "r26").add("r10", "r28", "r27")
    a.lbz("r0", SRC + 9, "r9").lbz("r11", SRC + 9, "r10").stb("r11", SRC + 9, "r9").stb("r0", SRC + 9, "r10")
    a.b("m9_drop")
    L("m9_swap")                                        # bench cell r27 <-> the player at cell r30
    a.addi("r27", "r27", -BENCH_CELL)                   # r27 = bench slot k
    a.lwz("r0", 0x1C, "r1").cmpwi("r0", 1).bne("m9_nodh")   # fielding with a DH: the DH cell <-> a fielder swaps
    a.cmpwi("r27", 0).beq("m9_fresh")                   # them (a position swap, Nick); the DH moved down the
    a.add("r9", "r28", "r27").lbz("r0", SRC + 9, "r9").cmpwi("r0", 9).beq("m9_fail")   # bench doesn't take the field
    L("m9_nodh")
    a.add("r9", "r28", "r27").lbz("r0", SRC + 9, "r9").cmpwi("r0", 9).blt("m9_fresh")
    a.lbz("r11", TEAM, "r28").mulli("r11", "r11", NB).add("r11", "r11", "r0").add("r11", "r11", "r28")
    a.lbz("r0", OUT - 9, "r11").cmpwi("r0", 0).bne("m9_fail")   # subbed out earlier: no re-entry
    L("m9_fresh")
    a.addi("r26", "r30", -2).lwz("r10", 0x24, "r31").li("r9", 0)
    L("m9_find")
    a.cmpwi("r9", 9).bge("m9_fail")
    a.lbz("r0", 0xC, "r10").extsb("r0", "r0").cmpw("r0", "r26").beq("m9_found")
    a.addi("r10", "r10", 0x10).addi("r9", "r9", 1).b("m9_find")
    L("m9_found")                                       # r9 = roster slot, r10 = its entry
    a.lwz("r11", -0x15A8, 13).lbz("r0", TEAM, "r28").slwi("r0", "r0", 2).lwzx("r0", "r11", "r0")
    a.cmpw("r0", "r9").bne("m9_notcap")                 # the captain stays, except while the DH bats in his
    a.lwz("r0", 0x1C, "r1").cmpwi("r0", 2).bne("m9_fail")   # slot (batting screen with a DH, and this slot is
    a.lbz("r11", TEAM, "r28").add("r11", "r11", "r28").lbz("r0", DHFOR, "r11").extsb("r0", "r0")   # the DH's
    a.cmpw("r0", "r9").bne("m9_fail")                   # target): then it's a pinch hitter for the DH
    L("m9_notcap")
    a.lha("r0", 0, "r10").cmpwi("r0", 0x4D).blt("m9_ok").cmpwi("r0", 0x64).ble("m9_fail")   # no Miis
    L("m9_ok")
    a.stw("r9", 0x10, "r1").stw("r10", 0x14, "r1")
    a.lha("r0", 0, "r10").sth("r0", 0x18, "r1").lbz("r0", 0xD, "r10").stb("r0", 0x1A, "r1")
    a.slwi("r26", "r27", 4).add("r26", "r26", "r28")    # r26 = D + k*0x10 (SCR entry k at +SCR)
    a.mr("r3", "r10").lha("r4", SCR, "r26").bl(SET_ENTRY)
    a.lwz("r10", 0x14, "r1").lbz("r0", SCR + 0xD, "r26").stb("r0", 0xD, "r10")
    a.lha("r0", 0x18, "r1").sth("r0", SCR, "r26").lbz("r0", 0x1A, "r1").stb("r0", SCR + 0xD, "r26")
    a.lwz("r9", 0x10, "r1").add("r11", "r28", "r9").add("r12", "r28", "r27")
    a.lbz("r0", SRC, "r11").lbz("r10", SRC + 9, "r12").stb("r10", SRC, "r11").stb("r0", SRC + 9, "r12")
    L("m9_drop")
    a.li("r0", -1).stw("r0", 0x8C, "r31").addi("r3", "r31", 0x94).li("r4", -1).bl(SET_ENTRY)
    a.li("r3", 1).b("m9_out")
    L("m9_fail")
    a.li("r3", 0).b("m9_out")
    L("m9_orig")
    a.mr("r3", "r31").bl(SWAP_FN)
    L("m9_out")
    a.leave(6)

    L("m10")                                    # info balloon: the hovered bench player (r27 = order task)
    a.load_addr("r12", D).lwz("r11", 0x88, "r27")
    on_bench("r11", "m10_o", "r10", "r12")
    a.lwz("r10", 0x8C, "r27").cmpwi("r10", 0).bge("m10_o")
    a.addi("r11", "r11", -BENCH_CELL).slwi("r11", "r11", 4).add("r11", "r11", "r12")
    a.lha("r11", SCR, "r11").sth("r11", 0x5A, "r27")
    L("m10_o")
    a.word(M10[1]).b(M10[0] + 4)

    L("m11")                                    # OK: stock position replay, then the records (r3 = task)
    a.enter(6).mr("r31", "r3").bl(APPLY_FN)
    a.load_addr("r30", D)
    a.lbz("r0", VALID, "r30").cmpwi("r0", 0).beq("m11_o")
    a.lbz("r0", MODE, "r30").cmpwi("r0", 0).beq("m11_o")
    a.lbz("r29", TEAM, "r30")
    a.lwz("r28", -0x2C8, 13).mulli("r0", "r29", 0x4FE).add("r28", "r28", "r0")
    a.li("r27", 0)
    L("m11_snap")                               # SCRATCH[i] = record i (roster slot i < 9, bench slot i - 9)
    a.cmpwi("r27", 9 + NB).bge("m11_apply")
    a.cmpwi("r27", 9).bge("m11_snapb")
    a.mulli("r4", "r27", 0x8E).add("r4", "r4", "r28").b("m11_snapc")
    L("m11_snapb")
    a.mulli("r4", "r29", NB).add("r4", "r4", "r27").addi("r4", "r4", -9).mulli("r4", "r4", REC_STRIDE)
    a.addi("r4", "r4", REC).add("r4", "r4", "r30")
    L("m11_snapc")
    a.mulli("r3", "r27", REC_STRIDE).addi("r3", "r3", SCRATCH).add("r3", "r3", "r30").li("r5", 0x8E).bl(MEMCPY)
    a.addi("r27", "r27", 1).b("m11_snap")
    L("m11_apply")
    a.li("r27", 0).li("r26", 0)
    L("m11_ap")
    a.cmpwi("r27", 9).bge("m11_bench")
    a.add("r11", "r30", "r27").lbz("r4", SRC, "r11").cmpw("r4", "r27").beq("m11_next")
    a.mulli("r4", "r4", REC_STRIDE).addi("r4", "r4", SCRATCH).add("r4", "r4", "r30")
    a.mulli("r3", "r27", 0x8E).add("r3", "r3", "r28").li("r5", 0x8E).bl(MEMCPY)
    a.add("r11", "r30", "r26").stb("r27", CHG, "r11").addi("r26", "r26", 1)
    a.lbz("r0", MODE, "r30").cmpwi("r0", 1).bne("m11_ph")      # fielding with a DH: a record from the 9 or the DH
    a.add("r11", "r30", "r29").lbz("r0", DHFOR, "r11").extsb("r0", "r0").cmpwi("r0", 0).blt("m11_fresh")
    a.add("r11", "r30", "r27").lbz("r0", SRC, "r11").cmpwi("r0", 9).ble("m11_next")   # (a swap: no one left the game)
    a.b("m11_fresh")
    L("m11_ph")
    a.lbz("r0", MODE, "r30").cmpwi("r0", 2).bne("m11_fresh")   # a pinch hitter for the DH: the slot's stamina
    a.add("r11", "r30", "r29").lbz("r0", DHFOR, "r11").extsb("r0", "r0")   # and flags are the fielder's (he
    a.cmpw("r0", "r27").beq("m11_next")                                      # sits at bench slot 0 till the swap back)
    L("m11_fresh")
    a.mr("r3", "r29").mr("r4", "r27").bl(MAX_STAMINA)          # fresh stamina for the new player
    a.lwz("r11", -0x1570, 13).mulli("r0", "r29", 0x120).add("r11", "r11", "r0")
    a.slwi("r0", "r27", 5).add("r11", "r11", "r0").sth("r3", 0x358, "r11")
    a.lwz("r11", -0x163C, 13).mulli("r0", "r29", 0x12).add("r11", "r11", "r0")
    a.slwi("r0", "r27", 1).add("r11", "r11", "r0").li("r0", 0).sth("r0", 0x60, "r11")
    L("m11_next")
    a.addi("r27", "r27", 1).b("m11_ap")
    L("m11_bench")                              # bench slot k: its record, and whether he was subbed out
    a.cmpwi("r27", 9 + NB).bge("m11_out_copy")
    a.add("r11", "r30", "r27").lbz("r4", SRC, "r11")
    a.addi("r12", "r27", NOUT - 9).li("r0", 1).cmpwi("r4", 9).bge("m11_bold")
    a.cmpwi("r27", 9).bne("m11_setout")         # bench slot 0 from the 9 on the fielding screen with a DH: the
    a.lbz("r10", MODE, "r30").cmpwi("r10", 1).bne("m11_setout")     # DH swapped with a fielder (a new DH, not out)
    a.add("r10", "r30", "r29").lbz("r10", DHFOR, "r10").extsb("r10", "r10").cmpwi("r10", 0).blt("m11_setout")
    a.li("r0", 0).b("m11_setout")
    L("m11_bold")
    a.mulli("r10", "r29", NB).add("r10", "r10", "r4").add("r10", "r10", "r30").lbz("r0", OUT - 9, "r10")
    L("m11_setout")
    a.stbx("r0", "r30", "r12")
    a.cmpw("r4", "r27").beq("m11_bnext")
    a.mulli("r4", "r4", REC_STRIDE).addi("r4", "r4", SCRATCH).add("r4", "r4", "r30")
    a.mulli("r3", "r29", NB).add("r3", "r3", "r27").addi("r3", "r3", -9).mulli("r3", "r3", REC_STRIDE)
    a.addi("r3", "r3", REC).add("r3", "r3", "r30").li("r5", 0x8E).bl(MEMCPY)
    L("m11_bnext")
    a.addi("r27", "r27", 1).b("m11_bench")
    L("m11_out_copy")
    a.add("r11", "r30", "r29").lbz("r0", DHFOR, "r11").extsb("r0", "r0").cmpwi("r0", 0).blt("m11_nodh")
    a.lbz("r0", MODE, "r30").cmpwi("r0", 1).bne("m11_nodh")
    a.lbz("r0", SRC + 9, "r30").cmpwi("r0", 9).beq("m11_nodh")
    for k in range(1, NB):                      # a new DH: the old one is out for the game, wherever he sits
        nxt = uniq("m11_dh")
        a.lbz("r0", SRC + 9 + k, "r30").cmpwi("r0", 9).bne(nxt).li("r0", 1).stb("r0", NOUT + k, "r30")
        L(nxt)
    L("m11_nodh")
    a.mulli("r11", "r29", NB).add("r11", "r11", "r30")
    for k in range(NB):
        a.lbz("r0", NOUT + k, "r30").stb("r0", OUT + k, "r11")
    a.stb("r26", NCHG, "r30").cmpwi("r26", 0).beq("m11_o")
    a.lbz("r0", MODE, "r30").cmpwi("r0", 1).bne("m11_o")
    a.lwz("r11", -0x15A8, 13).li("r0", 1).stb("r0", 0x83, "r11")   # stock re-placement + pitcher backdrop
    L("m11_o")
    a.leave(6)
    L("m12")                                    # state 0x1D sub-state 6, the stock re-placement done
    a.lwz("r3", -0x15A8, 13).li("r0", 0).stb("r0", 0x83, "r3")   # it restarts if called again while we wait
    a.bl("step").cmpwi("r3", 0).bne("m12_busy")
    a.bl(GROUP).b(M12[0] + 4)                   # the displaced `bl 0x801519F0`
    L("m12_busy")
    a.b(STATE_RETURN)

    L("dh_sync")                                # r3 = 1: the batting team's DH bats, the other's sits; 0: both sit
    a.enter(4).mr("r30", "r3").load_addr("r31", D)
    a.lbz("r0", VALID, "r31").cmpwi("r0", 0).beq("dhs_out")
    a.li("r29", -1).cmpwi("r30", 0).beq("dhs_teams")
    a.bl(GAME).lbz("r29", 0x2A, "r3")           # the batting roster team
    L("dhs_teams")
    for t in range(2):
        nxt, want = uniq("dhs"), uniq("dhs_w")
        a.lbz("r28", DHFOR + t, "r31").extsb("r28", "r28").cmpwi("r28", 0).blt(nxt)
        a.li("r0", 0).cmpwi("r29", t).bne(want).li("r0", 1)
        L(want)
        a.lbz("r11", DHIN + t, "r31").cmpw("r11", "r0").beq(nxt)
        a.stb("r0", DHIN + t, "r31")
        # swap bench record 0 and the slot's roster record (stamina, flags and stats stay with the slot)
        a.mulli("r28", "r28", 0x8E).lwz("r0", -0x2C8, 13).add("r28", "r28", "r0").addi("r28", "r28", 0x4FE * t)
        rec = REC + REC_STRIDE * t * NB
        a.addi("r3", "r31", SCRATCH).addi("r4", "r31", rec).li("r5", 0x8E).bl(MEMCPY)
        a.addi("r3", "r31", rec).mr("r4", "r28").li("r5", 0x8E).bl(MEMCPY)
        a.mr("r3", "r28").addi("r4", "r31", SCRATCH).li("r5", 0x8E).bl(MEMCPY)
        L(nxt)
    L("dhs_out")
    a.leave(4)

    L("h1")                                     # the sides have flipped (r3 = r31 = G; r7-r12 may be live)
    a.stwu("r1", -0x30, "r1").mflr("r0").stw("r0", 0x34, "r1")
    for i, r in enumerate(range(7, 13)):
        a.stw(r, 8 + 4 * i, "r1")
    a.li("r3", 1).bl("dh_sync")
    for i, r in enumerate(range(7, 13)):
        a.lwz(r, 8 + 4 * i, "r1")
    a.lwz("r0", 0x34, "r1").mtlr("r0").addi("r1", "r1", 0x30)
    a.lwz("r3", 0x44, "r31").b(H1[0] + 4)       # the displaced lwz r3,0x44(r3) (r3 was r31)

    for name, (site, word), on in (("h2", H2, 1), ("h3", H3, 0)):
        L(name)                                 # match start (r3 = G) / winner scene (r3 = the director)
        a.stwu("r1", -0x20, "r1").mflr("r0").stw("r0", 0x24, "r1").stw("r3", 8, "r1")
        a.li("r3", on).bl("dh_sync")
        if on:                                  # a pause-quit rematch rebuilds the lineup (FUN_8015a7b0, by the
            a.bl("dh_captain")                  # captain id) before this, maybe with the DH in the captain slot
        a.lwz("r3", 8, "r1").lwz("r0", 0x24, "r1").mtlr("r0").addi("r1", "r1", 0x20)
        a.word(word).b(site + 4)

    L("dh_captain")                             # leaf: a team with a DH whose captain slot (L + t*4) is lost (-1):
    a.load_addr("r12", D).lwz("r11", -0x15A8, 13).cmpwi("r11", 0).beq("dhk_out")   # the captain sat at bench slot
    for t in range(2):                          # 0 for the DH's target at the rebuild, so that slot is his
        nxt = uniq("dhk")
        a.lwz("r0", 4 * t, "r11").cmpwi("r0", 0).bge(nxt)
        a.lbz("r0", DHFOR + t, "r12").extsb("r0", "r0").cmpwi("r0", 0).blt(nxt).stw("r0", 4 * t, "r11")
        L(nxt)
    L("dhk_out")
    a.blr()

    L("step")                                   # -> 1 while our reloads run
    a.enter(6).load_addr("r31", D)
    a.lbz("r0", MODE, "r31").cmpwi("r0", 0).beq("st_zero")
    a.lbz("r0", NCHG, "r31").cmpwi("r0", 0).beq("st_done")
    a.lbz("r0", STEP, "r31").cmpwi("r0", 0).bne("st_wait")
    a.li("r0", 1).stb("r0", STEP, "r31").li("r30", 0)
    L("st_loop")
    a.lbz("r0", NCHG, "r31").cmpw("r30", "r0").bge("st_busy")
    a.add("r11", "r31", "r30").lbz("r29", CHG, "r11").lbz("r28", TEAM, "r31")
    a.lbz("r0", MODE, "r31").cmpwi("r0", 1).bne("st_bat")
    # fielding team: the slot's position; free that actor; load the new fielder; his animations / gear
    a.bl(GAME).lbz("r4", 0x2D, "r3").lwz("r3", -0x15A8, 13).mr("r5", "r29").bl(LINEUP_POS).extsh("r27", "r3")
    a.li("r3", 0).mr("r4", "r27").bl(FREE_A).li("r3", 0).mr("r4", "r27").bl(FREE_B)
    a.bl(GROUP).addi("r26", "r3", 8)
    a.mr("r3", "r26").mr("r4", "r28").mr("r5", "r29").bl(FIELDER_MODEL)
    a.mr("r3", "r26").mr("r4", "r27").bl(FIELDER_ANIM)
    a.cmpwi("r27", 0).bne("st_f1").mr("r3", "r26").bl(PITCHER_GEAR)
    L("st_f1")
    a.cmpwi("r27", 1).bne("st_next").mr("r3", "r26").bl(CATCHER_GEAR)
    a.b("st_next")
    L("st_bat")                                 # batting team: the batter at the plate
    a.lwz("r3", -0x1D78, 13).cmpwi("r3", 0).bne("st_hb").lwz("r3", -0x1D7C, 13)
    L("st_hb")
    a.cmpwi("r3", 0).beq("st_runners")
    a.lha("r0", 0x28, "r3").cmpw("r0", "r29").bne("st_runners")
    a.stw("r3", 0x10, "r1")
    a.load_addr("r11", RUNNERS).lwz("r3", 0, "r11").cmpwi("r3", 0).beq("st_nb0")
    a.mr("r4", "r28").mr("r5", "r29").bl(RUNNER_INIT)
    L("st_nb0")
    a.li("r3", 0).li("r4", 9).bl(FREE_A).li("r3", 0).li("r4", 9).bl(FREE_B)
    a.bl(GROUP).addi("r26", "r3", 0xC)
    a.mr("r3", "r26").li("r4", 0).bl(RUNNER_MODEL)
    a.mr("r3", "r26").bl(BATTER_ANIM)
    a.bl(BACKDROPS).lwz("r11", 0x10, "r1").lha("r4", 0x2A, "r11").li("r5", 1).bl(BACKDROP_LOAD)
    a.li("r0", 1).stb("r0", BD, "r31")
    L("st_runners")                             # ... and a runner on base
    a.li("r27", 1)
    L("st_rl")
    a.cmpwi("r27", 4).bge("st_next")
    a.load_addr("r11", RUNNERS).slwi("r0", "r27", 2).lwzx("r3", "r11", "r0").cmpwi("r3", 0).beq("st_rn")
    a.lha("r0", 0x28, "r3").cmpw("r0", "r29").bne("st_rn")
    a.lbz("r0", 0x176, "r3").cmpwi("r0", 1).bne("st_rn")
    a.mr("r4", "r28").mr("r5", "r29").bl(RUNNER_INIT)
    a.li("r3", 0).addi("r4", "r27", 9).bl(FREE_A).li("r3", 0).addi("r4", "r27", 9).bl(FREE_B)
    a.bl(GROUP).addi("r26", "r3", 0xC)
    a.mr("r3", "r26").mr("r4", "r27").bl(RUNNER_MODEL)
    a.mr("r3", "r26").mr("r4", "r27").bl(RUNNER_ANIM)
    L("st_rn")
    a.addi("r27", "r27", 1).b("st_rl")
    L("st_next")
    a.addi("r30", "r30", 1).b("st_loop")
    L("st_wait")
    a.lwz("r3", -0x898, 13).bl(LOADING_A).cmpwi("r3", 0).bne("st_busy")
    a.lwz("r3", -0x898, 13).bl(LOADING_B).cmpwi("r3", 0).bne("st_busy")
    a.lbz("r0", BD, "r31").cmpwi("r0", 0).beq("st_done")
    a.bl(BACKDROPS).li("r4", 1).bl(BACKDROP_READY).extsh("r3", "r3").cmpwi("r3", 0).beq("st_busy")
    L("st_done")
    a.li("r0", 0).stb("r0", MODE, "r31").stb("r0", NCHG, "r31").stb("r0", STEP, "r31").stb("r0", BD, "r31")
    L("st_zero")
    a.li("r3", 0).b("st_out")
    L("st_busy")
    a.li("r3", 1)
    L("st_out")
    a.leave(6)
    return a




def initial_data(dol, labels, msg):
    blob = bytearray(DATA_SIZE)
    stock = struct.unpack(">10i", dol.read(BATTING_MENU, 0x28))
    assert stock == sum(MENU_STOCK, ()), f"batting pause menu changed: {stock}"
    on = (MENU_STOCK[0], (SUB_CODE, msg)) + MENU_STOCK[1:4]
    struct.pack_into(">10i", blob, MENU_ON, *sum(on, ()))
    struct.pack_into(">10i", blob, MENU_OFF, *stock)
    for t in range(2):
        for k in range(9):
            e = FAKE + 0x90 * t + 0x10 * k
            struct.pack_into(">h", blob, e, -1)
            blob[e + 0xC] = 9 + k if k < NB else 0xFF
        for k in range(NB):
            struct.pack_into(">h", blob, REC + REC_STRIDE * (t * NB + k), -1)
    for i in range(9):
        struct.pack_into(">h", blob, SCR + 0x10 * i, -1)
        blob[SCR + 0x10 * i + 0xC] = 0xFF
    struct.pack_into(">hhbb", blob, DHSEL, DH_PITCHER, DH_PITCHER, -1, -1)
    struct.pack_into(">f", blob, DHDX, DH_LABEL_DX)
    for i in range(3):                  # fullwidth digit 1..3, fullwidth B
        struct.pack_into(">3H", blob, BASETXT + 8 * i, 0xFF11 + i, 0xFF22, 0)
    struct.pack_into(">f", blob, BASEDX, BASE_LABEL_DX)
    struct.pack_into(">f", blob, SLOT10DX, SLOT10_LABEL_DX)
    for i, (stock_vt, fn) in enumerate(((VT_BASE, "draw_base"), (VT_KAO, "draw_kao"))):
        struct.pack_into(">IIII", blob, VT + 0x10 * i, dol.u32(stock_vt), 0, labels[fn], dol.u32(stock_vt + 0xC))
    return bytes(blob)


def _patch(dol, addr, expect, new):
    got = dol.u32(addr)
    assert expect is None or got == expect, f"bench: 0x{addr:08X} expected {expect:08X}, found {got:08X}"
    dol.w32(addr, new)


def _bl_site(dol, site, old_target, new_target):
    _patch(dol, site, Asm(site).bl(old_target).assemble_word(), Asm(site).bl(new_target).assemble_word())


def apply(dol, region, msg, grid=True, preset=None, dh=None, once=False):
    """Patch `dol`; code and data go into `region` (charbuild Space). msg = the "Substitute" message index in dir
    121 file 4. grid: the 12x5 select grid is on (per-head flags at obj+0x6BC). preset = ([team 0 ids], [team 1
    ids]) for builds that skip the roster screen (quickboot's game mode; up to NB each, the first the DH), put in the
    benches' pick entries by the roster screen's init (S1), so the commit (S8) builds the bench records, VALID and
    DHFOR exactly as after picks on the screen. dh = (team 0 DHSEL, team 1 DHSEL): DH_PITCHER (the default), DH_OFF
    or the character id the DH bats for, set by S1 with the preset (as the positions screen's 10th slot would).
    once: the preset only until the first commit (PDONE; Start in a game: once per power-on, then the game's own
    rosters); without it every roster screen starts with the preset (test builds)."""
    import gridcells
    assert not preset or all(len(ids) <= NB and all(not 0x4D <= i <= 0x64 for i in ids) for ids in preset), \
        f"bench preset: up to {NB} per team, no Mii"
    assert dh is None or all(v in (DH_PITCHER, DH_OFF) or (0 <= v < 0x100 and not 0x4D <= v <= 0x64) for v in dh), \
        "bench DH: DH_PITCHER, DH_OFF or a character id (not a Mii)"
    D = region.here + (-len(region.blob) % 32)
    base = D + DATA_SIZE
    flags_off = gridcells.FLAGS if grid else 0x260
    a = code(base, D, flags_off, preset, msg, dh=dh, once=once)
    text = a.assemble()
    labels = a.labels
    assert region.put(initial_data(dol, labels, msg) + text) == D
    assert region.here <= region.limit, f"bench: 0x{len(text) + DATA_SIZE:x} B > section 0x{SECTION:x}"
    br = lambda site, lab: Asm(site).b(labels[lab]).assemble_word()

    # roster screen
    _patch(dol, S1[0], S1[1], br(S1[0], "s1"))
    _bl_site(dol, S2, TARGET, labels["s2"])
    _patch(dol, S3[0], S3[1], br(S3[0], "s3"))
    _patch(dol, S4[0], S4[1], br(S4[0], "s4"))
    for site in S5_REROLL:
        _bl_site(dol, site, RANDOM_FILL, labels["s5_reroll"])
    _patch(dol, S7[0], S7[1], br(S7[0], "s7"))
    _patch(dol, S8[0], S8[1], br(S8[0], "s8"))
    _patch(dol, S9[0], S9[1], br(S9[0], "s9"))
    _patch(dol, S11[0], S11[1], br(S11[0], "s11"))
    _patch(dol, CHALLENGE_INIT[0], CHALLENGE_INIT[1], labels["s10"])
    _patch(dol, ROSTER_UPDATE[0], ROSTER_UPDATE[1], br(ROSTER_UPDATE[0], "r_on"))
    _patch(dol, POSITIONS_UPDATE[0], POSITIONS_UPDATE[1], br(POSITIONS_UPDATE[0], "r_off"))
    # positions screen
    _patch(dol, P2[0], P2[1], br(P2[0], "p2"))
    _patch(dol, P3[0], P3[1], br(P3[0], "p3"))
    _patch(dol, P4[0], P4[1], Asm(P4[0]).bge(P4_TO).assemble_word())
    _patch(dol, P5[0], P5[1], br(P5[0], "p5"))
    for (site, stock), name in zip(P6, ("p6_up", "p6_down", "p6_side", "p6_side")):
        _bl_site(dol, site, stock, labels[name])
    _patch(dol, P7[0], P7[1], br(P7[0], "p7"))
    for (site, first), name in zip(P8, ("p8_base", "p8_kao")):
        _patch(dol, site, first, br(site, name))
    _bl_site(dol, P9, PANEL_HIT, labels["p9"])
    # match
    _patch(dol, M1_COUNT[0], M1_COUNT[1], br(M1_COUNT[0], "m1_count"))
    _patch(dol, M1_ID[0], M1_ID[1], br(M1_ID[0], "m1_id"))
    _patch(dol, M2[0], M2[1], br(M2[0], "m2"))
    _patch(dol, JUMP_TABLE + 10 * 4, DEFENSE_CASE, labels["m3_def"])
    _patch(dol, JUMP_TABLE + SUB_CODE * 4, NOOP_CASE, labels["m3_sub"])
    _patch(dol, M4[0], M4[1], br(M4[0], "m4"))
    _patch(dol, M5[0], M5[1], br(M5[0], "m5"))
    _patch(dol, M6[0], M6[1], br(M6[0], "m6"))
    frame = dol.read(FRAME_TABLE, 16)
    assert frame[:9] == bytes((4, 3, 0, 1, 2, 5, 6, 7, 8)) and not any(frame[9:9 + NB]), "position -> frame table"
    dol.write(FRAME_TABLE + 9, bytes(range(BENCH_FRAME, BENCH_FRAME + NB)))
    for i, (fn, first) in enumerate(CELL_DRAWS):
        _patch(dol, fn, first, br(fn, f"m7_{i}"))
    _patch(dol, CELL_BASE[0], CELL_BASE[1], br(CELL_BASE[0], "m7_base"))
    _patch(dol, BALLOON[0], BALLOON[1], br(BALLOON[0], "balloon"))
    _patch(dol, BALLOON_BOUND[0], BALLOON_BOUND[1], BALLOON_BOUND[1] + NB)
    _bl_site(dol, PRE_CARD_CALL, PRE_ENTRY, labels["card"])
    _patch(dol, PRE_CARD_READ[0], PRE_CARD_READ[1], br(PRE_CARD_READ[0], "card_read"))
    for site, word in BOUNDS:
        _patch(dol, site, word, word + NB)
    for site in M8_V:
        _bl_site(dol, site, VPAD_FN, labels["m8_v"])
    for site in M8_H:
        _bl_site(dol, site, HPAD_FN, labels["m8_h"])
    _bl_site(dol, M9, SWAP_FN, labels["m9"])
    _patch(dol, M10[0], M10[1], br(M10[0], "m10"))
    _bl_site(dol, M11, APPLY_FN, labels["m11"])
    _patch(dol, M12[0], M12[1], br(M12[0], "m12"))
    for site, name in ((H1, "h1"), (H2, "h2"), (H3, "h3")):
        _patch(dol, site[0], site[1], br(site[0], name))
    return ([f"bench: {NB} per team, code+data 0x{DATA_SIZE + len(text):x} B at 0x{D:08X} (data) / 0x{base:08X} "
             f"(code), \"Substitute\" = dir 121 file 4 message {msg}"
             + (f", test preset {preset}" if preset and not once else "")]
            + ([f"bench: preset (once per power-on) {preset_words(preset, dh)}"] if preset and once else []))


def preset_words(preset, dh=None):
    """The log's words for a bench preset: "team 1: DH 0x66, bench 0x67; bats for the pitcher | team 2: ..."."""
    out = []
    for t, ids in enumerate(preset):
        if not ids:
            continue
        sel = (dh or (DH_PITCHER, DH_PITCHER))[t]
        who = "the pitcher" if sel == DH_PITCHER else "no one (no DH)" if sel == DH_OFF else f"0x{sel:02X}"
        out.append(f"team {t + 1}: DH 0x{ids[0]:02X}" + (", bench " + ", ".join(f"0x{i:02X}" for i in ids[1:])
                                                        if ids[1:] else "") + f"; the DH bats for {who}")
    return " | ".join(out)


# ---------------- dt_na text and layout ----------------
MSG_DIR, MSG_FILE, MSG_TEXT = 121, 4, "Substitute"


def add_message(dol, data, dir_ptrs, dat, cursor, pending):
    """Append "<F000>Substitute" to dir 121 file 4 (every language; after char_names.rename_text).
    Returns (log, [(dt_na offset, bytes)], cursor, message index)."""
    import dtna_toc
    from char_names import _records
    from dir121_messages import encode_message

    def read(off, length):
        for at, blob in pending:
            if at <= off < at + len(blob):
                return blob[off - at:off - at + length]
        with open(dat, "rb") as fh:
            fh.seek(off)
            return fh.read(length)
    toc = dtna_toc.toc(dol)
    recs = _records(dol, data, dir_ptrs[MSG_DIR], len(toc[MSG_DIR]) * dtna_toc.FILE_RECORD)
    appended, placed, index = [], {}, None
    text = b"\xf0\x00" + encode_message(MSG_TEXT)
    for lang in range(3):
        at = MSG_FILE * dtna_toc.FILE_RECORD + lang * 16
        _, length, off, _ = struct.unpack_from(">4I", recs, at)
        if off not in placed:
            table = read(off, length)
            assert table[:2] == b"\1\1", "not a message table"
            n = struct.unpack_from(">H", table, 2)[0]
            offs = list(struct.unpack_from(f">{n}I", table, 4))
            body = bytearray(table[4 + 4 * n:])
            offs.append(len(body) // 2)
            body += text
            new = b"\1\1" + struct.pack(f">H{len(offs)}I", len(offs), *offs) + bytes(body)
            assert index in (None, n), "languages disagree on the message count"
            index = n
            appended.append((cursor, new))
            placed[off] = (cursor, len(new))
            cursor += len(new) + (-len(new) % 32)
        new_off, new_len = placed[off]
        struct.pack_into(">III", recs, at + 4, new_len, new_off, new_len)
    dir_ptrs[MSG_DIR] = data.put(bytes(recs), align=4)
    return [f"bench: \"{MSG_TEXT}\" is dir {MSG_DIR} file {MSG_FILE} message {index} (every language)"], appended, \
        cursor, index


def _element(data, k):
    c = struct.unpack_from(">I", data, 4)[0]
    base = c + 0x14
    count = struct.unpack_from(">I", data, base)[0]
    offs = list(struct.unpack_from(f">{count}I", data, c + 0x1C))
    return c, base, count, offs


def _append_nodes(data, k, nodes):
    """Element k with `nodes` (raw node bytes) appended; the container grows like gridcells._rebuild_element."""
    data = bytearray(data)
    c, base, count, offs = _element(data, k)
    e = base + offs[k]
    flags, n, size = struct.unpack_from(">III", data, e)
    fo = list(struct.unpack_from(f">{n}I", data, e + 12))
    body = bytes(data[e + 12 + 4 * n:e + size])
    shift = 4 * len(nodes)
    new_fo = [o + shift for o in fo]
    tail = 12 + 4 * (n + len(nodes)) + len(body)
    for node in nodes:
        new_fo.append(tail)
        tail += len(node)
    elem = struct.pack(">III", flags, n + len(nodes), tail) + struct.pack(f">{len(new_fo)}I", *new_fo) + body \
        + b"".join(nodes)
    elem += b"\0" * (-len(elem) % 4)
    elem = elem[:8] + struct.pack(">I", len(elem)) + elem[12:]
    grow = len(elem) - size
    assert grow > 0 and grow % 4 == 0
    old_e = offs[k]
    offs = [o + grow if o > old_e else o for o in offs]
    struct.pack_into(f">{count}I", data, c + 0x1C, *offs)
    rows_rel, = struct.unpack_from(">I", data, c + 0x18)
    assert rows_rel > old_e
    struct.pack_into(">I", data, c + 0x18, rows_rel + grow)
    for field in (0x0C, 0x10):
        v, = struct.unpack_from(">I", data, c + field)
        struct.pack_into(">I", data, c + field, v + grow)
    data[e:e + size] = elem
    return bytes(data)


def _node(data, k, i):
    c, base, count, offs = _element(data, k)
    e = base + offs[k]
    n = struct.unpack_from(">I", data, e + 4)[0]
    fo = struct.unpack_from(f">{n}I", data, e + 12)
    at = e + fo[1 + i]
    cnt, stride = struct.unpack_from(">HH", data, at)
    return at, bytes(data[at:at + 4 + cnt * stride])


def _moved(node, dx, dy):
    node = bytearray(node)
    cnt, stride = struct.unpack_from(">HH", node, 0)
    for j in range(cnt):
        key = 4 + j * stride
        for o, d in ((8, dx), (0x18, dx), (0x1C, dx), (0xA, dy), (0x1A, dy), (0x1E, dy)):
            struct.pack_into(">h", node, key + o, struct.unpack_from(">h", node, key + o)[0] + d)
    return bytes(node)


def _x(node):
    return struct.unpack_from(">h", node, 4 + 8)[0]




ROSTER_ROWS = (0xB8, 0xB9)           # roster slot positions (bottom / top team), one node per slot
DEFENSE_CELLS = 0xB                  # field cell positions (node = frame), both the positions and defense screens
# Placement, measured on Nick's screenshots (2026-09-25, 865x448): roster rows px = 0.91 * x + 142 (the 9 slots at
# x -27..495, the team bar ends at px 625, the Mario Fireballs logo spans y 90-290); fields px = centre + 0.93 * x,
# y 1.03 per unit (centres: P1 (263, 215), CPU (485, 215); LF cell's left edge px 170, the gap between the two
# fields px 356-390).
# Roster screen: 5 bench slots at 75 % right of the team bar, px 650-810 (x 559 + 44 k), on the row's y.
ROSTER_BENCH = dict(x0=535, step=44, dy=0, scale=0.75)   # x0 before the screen shift (+gridcells.SCREEN_DX)
# Fields (Nick: "DH should be bottom right, away from the bench"; docs/bench.md "Where the DH sits"): the DH (bench
# slot 0) at (84, 84), below-right of 1B (69, 38) and right of C (0, 66): P1 px (341, 302), CPU px (563, 302); its
# disc (75 %, ~15 px radius) spans px y 287-317, above the batting-order panels (px y 324), and P1's stays left of the
# gap between the fields (px 356-390, the CPU's bench column). Slots 1..4: a column at x -121 (P1 px 150, CPU px
# 372), y -72 .. 48 (from level with LF down; its bottom stays clear of the other field's DH corner), cells at 75 %.
FIELD_BENCH = dict(x=-121, y0=-72, step=40, scale=0.75, dh=(84, 84))


def field_bench_xy(k, field=FIELD_BENCH):
    """Layout position (x, y) of bench slot k's cell (element 0xB frame BENCH_FRAME + k)."""
    if k == 0:
        return field["dh"]
    return field["x"], field["y0"] + (k - 1) * field["step"]


def _scaled(node, s):
    node = bytearray(node)
    cnt, stride = struct.unpack_from(">HH", node, 0)
    for j in range(cnt):
        key = 4 + j * stride
        if stride >= 0x3C:
            sx, sy = struct.unpack_from(">ff", node, key + 0x34)
            struct.pack_into(">ff", node, key + 0x34, sx * s, sy * s)
    return bytes(node)


# The roster screen's stat card (element 0xBF, placed by 0xB5 top / 0xB4 bottom at x 591 = px 680, spanning px
# 628-732) sat over the bench slots (Nick's screenshots 20:11 / 20:41). Moved to the far left (Nick) at 88 %: the
# card's left edge (57 units left of its anchor) at the screen edge (x -153), its right edge meeting the team bar.
# (0xBD / 0xBE, moved by mistake in 97a0456, are left alone again.)
STAT_CARDS = dict(elements=(0xB5, 0xB4), anchor=567, new_anchor=-103, scale=0.88)   # anchor before the shift


def _card_moved(data, k, cfg, screen_dx):
    data = bytearray(data)
    c, base, count, offs = _element(data, k)
    e = base + offs[k]
    n = struct.unpack_from(">I", data, e + 4)[0]
    s = cfg["scale"]
    for fo in struct.unpack_from(f">{n}I", data, e + 12)[1:]:
        cnt, stride = struct.unpack_from(">HH", data, e + fo)
        assert stride >= 0x3C
        for j in range(cnt):
            key = e + fo + 4 + j * stride
            anchor = cfg["anchor"] + screen_dx                    # the card stays in the corner whatever the shift
            assert struct.unpack_from(">h", data, key + 8)[0] == anchor, "the stat card moved"
            for o in (8, 0x18, 0x1C):
                x = struct.unpack_from(">h", data, key + o)[0]
                struct.pack_into(">h", data, key + o, round(cfg["new_anchor"] + (x - anchor) * s))
            sx, sy = struct.unpack_from(">ff", data, key + 0x34)
            struct.pack_into(">ff", data, key + 0x34, sx * s, sy * s)
    return bytes(data)


def _glyph(root, cache, spec):
    """One letter cut from a stock word (PIL RGBA, the row's cell height): spec = ((dir, file), row, first column, end
    column, page, the row's pixel rect on the page (asserted)); the page must be the stock CI4 with 16 IA8 colours.
    The cut columns get the dark outline colour where the letter has ink (the words' letters touch)."""
    import dtna_toc, layout
    from PIL import Image
    from dol import Dol
    (d, f), row, c0, c1, page_no, want = spec
    if (d, f) not in cache:
        off, length = dtna_toc.toc(Dol(root / "sys/main.dol"))[d][f]
        with open(root / "files/dt_na.dat", "rb") as fh:
            fh.seek(off)
            blob = fh.read(length)
        cache[(d, f)] = blob, layout.Layout(blob)
    blob, lay = cache[(d, f)]
    desc = lay.descs[page_no]
    img, pal = struct.unpack_from(">II", desc, 0)
    h, w = struct.unpack_from(">HH", desc, 8)
    assert (w, h, desc[0x17], desc[0x1A], struct.unpack_from(">H", desc, 0x18)[0]) == (1024, 1024, 8, 0, 16), \
        f"glyph {d}/{f} page {page_no}: not the stock CI4 / IA8 page"
    colours = []
    for i in range(16):                         # IA8: alpha high, intensity low
        v = struct.unpack_from(">H", blob, layout.TEX_BASE + pal + 2 * i)[0]
        colours.append((v & 0xFF,) * 3 + (v >> 8,))
    page, _, v1, u1, v2, u2 = struct.unpack(">HH4f", lay.rows[row])
    rect = tuple(round(v * 1024) for v in (u1, v1, u2, v2))
    assert page == page_no and rect == want, f"glyph {d}/{f} row 0x{row:X} moved ({page}, {rect})"
    glyph = Image.new("RGBA", (c1 - c0, rect[3] - rect[1]))
    px = glyph.load()
    for y in range(glyph.height):
        for x in range(glyph.width):
            gx, gy = rect[0] + c0 + x, rect[1] + y
            b = blob[layout.TEX_BASE + img + ((gy // 8) * (w // 8) + gx // 8) * 32 + (gy % 8) * 4 + (gx % 8) // 2]
            c = colours[b >> 4 if gx % 2 == 0 else b & 15]
            if x in (0, glyph.width - 1) and c[3]:
                c = (20, 22, 28, 255)           # the cut edge: outline
            px[x, y] = c
    return glyph


def _root(game):
    from pathlib import Path
    import game_source
    return Path(game) if game else game_source.root()


def dh_art(game=None):
    """The "DH" picture (PIL RGBA, DH_ART_SIZE): cut from the player's own game (dt_na DH_ART_FILE; game: its
    extracted folder, default game_source.root()), so none of the art ships."""
    from PIL import Image
    root, cache = _root(game), {}
    out = Image.new("RGBA", DH_ART_SIZE)
    x_at = 0
    for row, c0, c1 in DH_ART_GLYPHS:
        glyph = _glyph(root, cache, (DH_ART_FILE, row, c0, c1, DH_ART_PAGE, DH_ART_CELLS[row]))
        out.alpha_composite(glyph, (x_at, 0))
        x_at += glyph.width - 1
    assert x_at + 1 == DH_ART_SIZE[0]
    return out


def fo_art(game=None):
    """The "FO" (fielder only) picture for the 10th order slot: FO_F_GLYPH's F and FO_O_GLYPH's O on the D's cap
    line, cut from the player's own game (none of the art ships)."""
    from PIL import Image
    root, cache = _root(game), {}
    f = _glyph(root, cache, FO_F_GLYPH)
    o = _glyph(root, cache, FO_O_GLYPH).crop((0, FO_O_ROWS[0], FO_O_GLYPH[3] - FO_O_GLYPH[2], FO_O_ROWS[1]))
    px = o.load()                               # its counter is see-through; the D's is filled dark: the same here
    for y in range(o.height):
        ink = [x for x in range(o.width) if px[x, y][3] > 128]
        for x in range(ink[0], ink[-1] + 1) if ink else ():
            if px[x, y][3] < 128:
                px[x, y] = (20, 22, 28, 255)
    out = Image.new("RGBA", FO_ART_SIZE)
    out.alpha_composite(f, (0, 0))
    out.alpha_composite(o, (f.width - FO_O_OVERLAP, FO_O_Y))
    assert f.width - FO_O_OVERLAP + o.width == FO_ART_SIZE[0]
    return out


def _add_dh_picture(data, art, size=DH_ART_SIZE, element=DH_ELEMENT):
    """File 19 + the "DH" picture: an RGB5A3 page, its row, and element DH_ELEMENT (a copy of 0xA8, one sprite key at
    (0, 0), centred like the cells' own sprites) showing it at DH_ART_SCALE."""
    import layout
    from captain_art import rgb5a3, GX_RGB5A3
    from PIL import Image
    lay = layout.Layout(data)
    assert len(lay.elements) == element, f"file 19 has {len(lay.elements)} elements (expected {element})"
    w, h = (-(-n // 4) * 4 for n in size)
    page_img = Image.new("RGBA", (w, h))
    page_img.alpha_composite(art.convert("RGBA"), (0, 0))
    page = lay.add_texture(rgb5a3(page_img), w, h, GX_RGB5A3, template_page=0)
    row = lay.add_row(page, 0.0, 0.0, size[0] / w, size[1] / h)
    elem = bytearray(lay.elements[0xA8])
    fo = struct.unpack_from(">I", elem, 12 + 4)[0]              # node 0
    cnt, stride = struct.unpack_from(">HH", elem, fo)
    key = fo + 4
    assert (cnt, stride, elem[key + 4], struct.unpack_from(">hh", elem, key + 8)) == (1, 0x50, 4, (0, 0)), \
        "element 0xA8 is not a one-sprite element"
    struct.pack_into(">H", elem, key + 6, row)
    w, h = size                                                  # the sprite's corner offset from its key: centred
    struct.pack_into(">8h", elem, key + 0x28, *[-(w // 2), -(h // 2)] * 4)   # (0xA8's: (-18, -12) for 36 x 24)
    struct.pack_into(">4I", elem, key + 0x40, *[0xFFFFFFFF] * 4)       # vertex colours: white
    struct.pack_into(">ff", elem, key + 0x38, DH_ART_SCALE, DH_ART_SCALE)
    assert lay.add_element(bytes(elem)) == element
    if element != DH_ELEMENT:
        return lay.to_bytes()
    above = bytearray(elem[fo:fo + 4 + stride])                 # node DH_ABOVE_NODE: the same, above a field cell
    for o in (8, 0x18, 0x1C):
        struct.pack_into(">hh", above, 4 + o, 0, DH_ABOVE_Y)
    return _append_nodes(lay.to_bytes(), element, [bytes(above)])


def _add_numbers(data):
    """File 19 + element NUM_ELEMENT: 9 nodes, node i the stock digit i + 1 (rows NUM_ROW0 + 1 ..), each a copy of
    0xA8's sprite key at NUM_XY, centred, white, scale NUM_SCALE."""
    import layout
    lay = layout.Layout(data)
    assert len(lay.elements) == NUM_ELEMENT, f"file 19 has {len(lay.elements)} elements (expected {NUM_ELEMENT})"
    keys = []
    for i in range(9):
        row = NUM_ROW0 + 1 + i
        page, _, v1, u1, v2, u2 = struct.unpack(">HH4f", lay.rows[row])
        ph, pw = struct.unpack_from(">HH", lay.descs[page], 8)
        w, h = round((u2 - u1) * pw), round((v2 - v1) * ph)
        assert (w, h) == (20, 22), f"digit row 0x{row:X} is {w} x {h}"
        elem = bytearray(lay.elements[0xA8])
        fo = struct.unpack_from(">I", elem, 12 + 4)[0]
        key = fo + 4
        assert struct.unpack_from(">HH", elem, fo) == (1, 0x50) and elem[key + 4] == 4
        struct.pack_into(">H", elem, key + 6, row)
        for o in (8, 0x18, 0x1C):
            struct.pack_into(">hh", elem, key + o, *NUM_XY)
        struct.pack_into(">8h", elem, key + 0x28, *[-(w // 2), -(h // 2)] * 4)
        struct.pack_into(">ff", elem, key + 0x38, NUM_SCALE, NUM_SCALE)
        struct.pack_into(">4I", elem, key + 0x40, *[0xFFFFFFFF] * 4)
        if i == 0:
            assert lay.add_element(bytes(elem)) == NUM_ELEMENT
        keys.append(bytes(elem[fo:fo + 4 + 0x50]))
    data = lay.to_bytes()
    return _append_nodes(data, NUM_ELEMENT, keys[1:])


def layout_bytes(data, roster=ROSTER_BENCH, field=FIELD_BENCH, cards=STAT_CARDS, screen_dx=None, art=None,
                 fo=None):
    """dir 119 file 19 (after gridcells and the other rows): NB roster slots per team (nodes 9.. of 0xB8 / 0xB9),
    NB bench cell frames on element 0xB (frames 10..) and the "DH" picture (element DH_ELEMENT). screen_dx: the
    roster screen's shift (gridcells.screen_dx of the build's grid; None: gridcells.SCREEN_DX, the 12 x 5 grid's).
    art: the picture (default dh_art(), from the player's game)."""
    import gridcells
    screen_dx = gridcells.SCREEN_DX if screen_dx is None else screen_dx
    assert None not in roster.values() and None not in field.values(), "bench placement not set"
    for k in ROSTER_ROWS:
        last = _node(data, k, 8)[1]
        y = struct.unpack_from(">h", last, 4 + 0xA)[0]
        nodes = []
        for i in range(NB):
            x = round(roster["x0"] + screen_dx + i * roster["step"])
            dy = roster["dy"] if k == 0xB9 else -roster["dy"]      # toward the grid: down for the top row
            nodes.append(_scaled(_moved(last, x - _x(last), dy), roster["scale"]))
        nodes.append(_moved(last, SLOT10_DX_NODE, 0))              # node 14: the 10th order slot (positions screen)
        data = _append_nodes(data, k, nodes)
    for k in cards["elements"]:
        data = _card_moved(data, k, cards, screen_dx)
    catcher = _node(data, DEFENSE_CELLS, 3)[1]           # frame 3 = C (0, 66)
    c, base, _, offs = _element(data, DEFENSE_CELLS)
    frames = struct.unpack_from(">I", data, base + offs[DEFENSE_CELLS] + 4)[0] - 1
    assert frames == BENCH_FRAME, f"element 0xB has {frames} frames (expected {BENCH_FRAME})"
    cx, cy = _x(catcher), struct.unpack_from(">h", catcher, 4 + 0xA)[0]
    nodes = []
    for k in range(NB):
        x, y = field_bench_xy(k, field)
        nodes.append(_scaled(_moved(catcher, x - cx, y - cy), field["scale"]))
    data = _append_nodes(data, DEFENSE_CELLS, nodes)
    data = _add_dh_picture(data, dh_art() if art is None else art)
    data = _add_numbers(data)
    return _add_dh_picture(data, fo_art() if fo is None else fo, FO_ART_SIZE, FO_ELEMENT)
