# Where things are

For modders: where Mario Super Sluggers (USA, RMBE01) keeps the things people edit, in the **original game**, and
where the **Sluggers patcher moves them** in a patched game.

- Addresses are the game's memory addresses (what Dolphin's debugger, Gecko codes and Ghidra show), in the clean
  `sys/main.dol` unless a line says RAM. The only file offset given is dt_na.dat's directory table.
- `r13` = 0x807961C0 and `r2` = 0x8079EDC0 (the small-data bases). `*(r13-0x2C8)` means "the pointer stored at
  r13-0x2C8".
- "id" is the character id (0x00-0x64 in the stock game). A per-character table's row for a character is
  `table + id * row size`.
- "dt_na dir N file F" is a file inside `files/dt_na.dat`.
- The last column says how sure we are: **C** read in the game's code or data, **T** checked by a test or in the game,
  **I** inferred, **-** not marked. The file named there (in the Sluggers repo's `docs/`) has the details.
- Names like `FUN_8015c800` are Ghidra's. The patcher's "Modder files..." gives you a Dolphin map and Ghidra names
  for the game's classes (docs/ghidra-names.md).

**Before relying on an address, check it in your own game.** Several of these came from single notes, and a few docs
disagree (listed at the end).

# Part 1: the original game

Format: **what** — where — size / layout — how sure — doc. **(moves)** means the patcher can move or enlarge it:
see Part 2 for where it goes.

## Characters and stats

- **Stats table** — 0x806CE9A0 (8-byte header; rows at 0x806CE9A8 + id × 0x8E) — 41 stat bytes then 101 chemistry
  bytes per character — C — character-import.md, hitting-power-cap.md **(moves)**
  - row +5 unused, +7 captain flag, +8 star pitch, +9 star swing, +10 fielding ability, +0x0C / +0x0E slap / charge
    size (u16), +0x10 / +0x12 slap / charge power (u16) — C — star-swings.md, abilities.md, mystery-stat.md,
    character-editor.md
- **Stat limits** (u16 min at +8, max at +0xA) — 0x806318D8 + id × 0xC; maxima at 0x8063192A / 0x80631942 — C —
  hitting-power-cap.md
- **Team rosters in a match** (RAM) — `*(r13-0x2C8)` + team × 0x4FE + slot × 0x8E (object at 0x80795EF8, 0xA94 bytes)
  — C — mystery-stat.md, hitting-power-cap.md
- **Selector table** (wheel, captain id, model/voice family, is-captain, variant, icon) — 0x80631550, 8 bytes × 101 —
  character-ids.md **(moves)**
- **Wheel head ids** — 0x80631878, 43 bytes — character-ids.md **(moves)**
- **Grid cell → head** — 0x8062C258 — new-characters-feasibility.md
- **Per-character floats** (batter box x/z min/max, offsets, step, strike-zone height) — 0x806291D8 + id × 0x24 — C —
  hidden-stats.md, hit-by-pitch.md **(moves)**
- **Trajectory** (byte 0: 0 medium / 1 high / 2 low; byte 1: hit curve) — 0x8062A15C + id × 2 — C — hidden-stats.md
  **(moves)**
- **Size** (f32: draw scale; second f32 unknown) — 0x8062EB50 + id × 8 — C — hidden-stats.md **(moves)**
- **Body cylinder** (radius, height: fielding and item hits) — 0x8062BA08 + id × 8 — C — hidden-stats.md **(moves)**
- **Has own model** — 0x806B4970 + id, 1 byte — character-import.md **(moves)**
- **Unknown per-character rows** — 0x8062A00C (2 B), 0x8062A228 (5 B), 0x8062A424 (6 B), 0x8062B874 (4 B) — T (size)
  — char-limit-sites.md **(moves)**
- **Per-family speed tables** (43 rows) — 0x80625898, 0x80626208 — new-characters-feasibility.md
- **Unlocked characters** (save file `gamedata`, 0x6020 bytes, word-sum checksum) — unlock byte at +0x209 + id; per-id
  arrays cover ids 0x00-0x4C only — T — mod-tables.md, char-limit-sites.md; in RAM `*(*(r13-0x1224))` + 0xD + id
- **Fixed unlock list** — 0x8062C930 — T — char-limit-sites.md
- **Challenge-mode per-character tables** — 0x80651980, 0x80650EC0, 0x806570D8; lists at 0x8062C944 —
  char-limit-sites.md
- Every place the game assumes 101 characters: **char-limit-sites.md**.

## Chemistry

- **Chemistry** (0 bad / 1 neutral / 2 good) — the 101 bytes after the 41 stat bytes in each stats row — T —
  mod-tables.md
- **Chemistry check** — FUN_8015c800(team, slotA, slotB) — open-questions.md
- **Chemistry hit boost** (1.1 / 1.25 / 1.5) — 0x8062588C — C — hitting-power-cap.md

## Captains and star moves

- **Captain → default roster** — 0x806318A8 — bench.md **(moves)**
- **Star-swing launch angle** (0x14 per row, row = swing − 1, no bounds check) — 0x80626BF0 — C — star-swings.md
- **Star-swing launch speed** {low, high, spin} (0x1E per row) — 0x80627228 — C — star-swings.md
- **Star cost** (captain 50, others 50, flagged 100) — 0x8062BD40 — C — star-swings.md
- **Star gain per event** (12 teams × 41 s16) — 0x8062BD50 — C — star-swings.md, pauline-chance.md **(moves)**
- **Star-pitch paths** (13 rows × 12 bytes) — 0x80649C20 / 0x80649CBC — C — vanishing-ball.md, gravity-well.md
- **Pitch speeds** (0xE per row) — 0x806277DC — vanishing-ball.md
- **Cut-in camera** per swing — 0x8065D960 (pitches 0x8065D9C8); files in dt_na dir 0x7C — star-swings.md
- **Cut-in banner** — 0x8062CE3C (pitches 0x8062CE20) — star-swings.md
- **Star-move names** (label art rows): pitch 0x806233C0, swing 0x806233DC, fielding 0x806233F8, running 0x80623418 —
  T — star-swings.md, abilities.md
- **Captain-select labels** — 0x806A17B8 → four lists at 0x8062C9FC.. (dt_na dir 119 file 18) — T — abilities.md

## Fielding abilities

- **A character's ability** — stats row +10 — T — abilities.md
- **Dive / special catch reach** (abilities 3-8) — 0x80625DA8 — C — dive-catch.md
- **Buddy jump** (vy, gravity, horizontal, hang) — 0x80625BD8 — C — buddy-jump.md
- **Clamber / wall** — 0x80625E1C + mode × 0xA0 — buddy-jump.md
- **CPU ability use** — 0x80624A14 [class × 5 + level] — C — fielder-ai-state.md

## Items

- **Roulette odds** (6 bytes per row, by score difference) — 0x80630FB0 — C — items.md, batter-items.md
- **Item icons** — 0x8062CE10 + item — items.md
- **Item models** — dt_na dir 136 — items.md
- **Item classes** (vtables): Shell 0x806CC6B8, Fireball 0x806CC538, Bob-omb 0x806CC338, POW 0x806CC638, Banana
  0x806CC2E0, Boo 0x806CC760, Thunder 0x806CC7E8 — items.md
- **Item manager** (RAM) — `*(r13-0x354)` — items.md
- **Ice block size per character** — 0x806250E8 + id × 4 — C — hidden-stats.md **(moves)**
- **Stun times**: Fireball 0x80625F60, knockdown 0x80625F66 (+ mode × 0x68), slide 0x80625E74 —
  cpu-ai-weaknesses.md
- **CPU item aim** — radius 0x80630CA0, jitter 0x80630D58, lead 0x80630ED8 — C — cpu-ai-weaknesses.md

## Pitching and batting

- **Pitch windup** — 0x80628400 + id × 0xC — C (reader), I (meaning) — cpu-ai.md **(moves)**
- **Star pitch per character** — 0x806288BC + id — hidden-stats.md **(moves)**
- **Stamina** (s16, 30-100) — 0x80628924 + id × 2 — hidden-stats.md **(moves)**
- **Change-up** (f32 speed multiplier, f32 arc) — 0x80628EB0 + id × 8 — C — hidden-stats.md **(moves)**
- **Throw floats** (pitch steering at +8) — 0x806289F0 + id × 0xC — hidden-stats.md **(moves)**
- **Throw / catch animation** — 0x8062B678 + id × 5 — character-import.md **(moves)**
- **Charge effect sizes** — pitcher 0x80624F30, batter 0x80624D98, effects 0x80624C00 / 0x806252B0 (+ id × 4) —
  T (values), I (effect) — char-limit-sites.md **(moves)**
- **Catch range** — 0x8062A688 + id × 0x28 — character-import.md **(moves)**
- **Hit-by-pitch box** (per model family, 3 bytes, cm) — 0x8062A0D8 + family × 3 — C — hit-by-pitch.md
- **Strike zone** x ±0.55 at 0x80627A90 / 94; planes 0x80627A98 / 9C — C — hit-by-pitch.md
- **Hit power** — base rows 0x806270FC, pitch quality 0x80627A78, percent 0x80627558 — C — hitting-power-cap.md
- **Contact timing** — zones 0x80626480, window 0x80626460, swing frames 0x80626570, directions 0x80626628 —
  hitting-power-cap.md, pitch-model.md
- **Gravity** (per 50/60 Hz) — 0x80797958 — star-swings.md
- **Random numbers** — FUN_80165C14(`*(r13-0x1578)`); table 0x80623820 — rng.md

## CPU players and fielding

- **CPU level** (RAM) — `*(0x807956C0)` + 0x10 — C — cpu-ai.md
- **CPU batting and pitching constants** (guessing, aim error, timing, charge, bunts; curve, location, waits) —
  0x80624744-0x806249A8 and 0x807971C0-0x80797230 — C — cpu-ai.md lists each one
- **Pitcher change** (stamina ≥ 10) — 0x80627B98 — cpu-ai-weaknesses.md
- **Fielder AI states** {role, handler} — 0x80642DC0 — C — fielder-ai-state.md
- **Fielder reaction** — delay 0x806249E8, re-plan 0x80624A08, per position 0x80625AA8 — fielder-ai-state.md
- **Field positions** — bases 0x80625798, home spots 0x80627C90 + id × 8, infield 0x80627CD8, bunt 0x80628038,
  outfield 0x80628058 — C — fielder-ai-state.md
- **Base running** — bases 0x80626058, paths 0x80626078, leads 0x806260D8, overrun 0x80626148 — runners.md

## Stadiums

**stadium-id-sites.md** lists about 35 per-stadium tables. The main ones (all can move, Part 2):

- **Archive / collision** {dir, file × 3} — 0x806D99E0, 0x806D9980
- **Fences** (f32 × 10) — 0x80625770; ball impact 0x80625748; fielder targets 0x80625458
- **Music** (s32 × 10) — 0x8062E608; ambience 0x8062E5B8 — stadium-music.md
- **Objects** — 0x806467D0 / 0x80646820 / 0x806489E8
- **Time of day** — 0x806D9450; pre-game pages 0x806C9D20 / 0x806C8D38; result colours 0x80623D58
- **Lighting** (39 × 0x178) — 0x806B9E10 — stadium-lighting.md (not moved)
- **Files** — packages dt_na dir 136 file 3 + id × 2 + variant; stadium dirs 7-16; collision file format in
  stadium-dimensions.md
- **Stadium select** — markers 0x8062EF58, camera 0x806BEC38, availability 0x80631CF8 / 0x80631D0C, map models dir 122
  — stadium-select.md
- **Hazards** — controllers 0x806A3264-0x806A5790, models dt_na dir 137 — stadium-hazards.md

## Menus, sound and files

- **Menu text** — dt_na dir 121 (file 0 menus, file 4 popups) — stadium-select.md
- **Voice families** — 0x80631FC0 or 0x80631FD0 (docs disagree, see below) — character-ids.md
- **Sounds** — `files/sound_NA/MY2.brsar` — stadium-music.md
- **dt_na.dat directory table** (172 entries) — 0x806A0728 (file offset 0x69C828); character files 0x80680118 + id ×
  0x2D0 + file × 0x30 + language × 0x10; a character's directory is id + 0x12 — character-dat-entries.md **(moves)**
- **Per-character files 0-14** (body, props, animations) — character-dat-entries.md
- **Prop requests** (RAM) — 0x80709408 — dive-catch.md **(moves)**
- **Particles** — dt_na dir 161; portraits dir 119 file 2 — star-swings.md

## Memory at run time

- **Arena low** (where the game's heaps start) — stock 0x807B6E80 — new-characters-feasibility.md
- **Match settings** (RAM) — `*(r13-0xB00)`, 0x811F7698 in a clean game — charbuild.gecko_map notes
- **Replay** `*(0x80794C5C)`, **score** `*(0x80794C7C)` — replay.md

# Part 2: what the patcher moves

To make room for new characters and stadiums, the patcher copies some tables to bigger ones in new memory
(0x807F7000 and up) and points the game's code at the copies. **Where they end up depends on what you ticked**, so
every patched game has its own list:

- **`<your game> (patch details)/relocations.json`**, written next to every ISO the patcher makes. For each moved table: `old`,
  `length`, `new`, `name`, `row` (bytes per row) and, for per-character tables, `per_character`. The new tables keep
  the stock rows at the same offsets and add rows after them: **old address + offset → new address + same offset**.
- The same file's `changed` list gives every stock word the patcher changed that isn't in a moved table (code and
  data ranges, with the feature that changed them).
- `heap_shift`: how far the game's run-time memory moved up. The patcher raises arena low to make room, so RAM
  addresses past 0x807B6E80 (heaps, the match, players) sit this much higher than in a clean game. The table below
  is from a build with everything ticked: arena low 0x8087E200, a shift of 0xC9380.
- The patcher's **"Fix my Gecko codes..."** rewrites Gecko codes with this file.

The tables it can move. "Example new" is the everything build. Yours can differ, so read your relocations.json.

| Table | Original | Size | Layout | Example new |
|---|---|---|---|---|
| captain batting prefs | 0x80623428 | 0x18 | - | 0x80827388 |
| captain fielding prefs | 0x80623440 | 0x18 | - | 0x808273A4 |
| stadium result_layout | 0x80623C80 | 0x28 | 4 B rows | 0x80829C44 |
| stadium result_colour | 0x80623D58 | 0x1E | 3 B rows | 0x80829C70 |
| effectscale_c00 | 0x80624C00 | 0x194 | 4 B per character | 0x8080AA20 |
| batchargescale | 0x80624D98 | 0x194 | 4 B per character | 0x8080A620 |
| pitchchargescale | 0x80624F30 | 0x194 | 4 B per character | 0x8080A220 |
| icescale | 0x806250E8 | 0x194 | 4 B per character | 0x80805720 |
| effectscale_2b0 | 0x806252B0 | 0x194 | 4 B per character | 0x8080AE20 |
| stadium fieldpt | 0x80625458 | 0xA0 | 16 B rows | 0x808298D4 |
| stadium impact | 0x80625748 | 0x28 | 4 B rows | 0x80829984 |
| stadium fence | 0x80625770 | 0x28 | 4 B rows | 0x808298A8 |
| pitchwindup | 0x80628400 | 0x4BC | 12 B per character | 0x80800620 |
| starpitch | 0x806288BC | 0x65 | 1 B per character | 0x80801220 |
| stamina | 0x80628924 | 0xCA | 2 B per character | 0x80801320 |
| throwfloats | 0x806289F0 | 0x4BC | 12 B per character | 0x80808C20 |
| changeup | 0x80628EB0 | 0x328 | 8 B per character | 0x80801520 |
| charfloats | 0x806291D8 | 0xE34 | 36 B per character | 0x80805C20 |
| perid2 | 0x8062A00C | 0xCA | 2 B per character | 0x80808020 |
| traj | 0x8062A15C | 0xCA | 2 B per character | 0x80801D20 |
| perid5a | 0x8062A228 | 0x1F9 | 5 B per character | 0x80809820 |
| perid6 | 0x8062A424 | 0x25E | 6 B per character | 0x80808220 |
| catchrange | 0x8062A688 | 0xFC8 | 40 B per character | 0x80801F20 |
| throwvariant | 0x8062B678 | 0x1F9 | 5 B per character | 0x80809D20 |
| perid4 | 0x8062B874 | 0x194 | 4 B per character | 0x80808820 |
| hitbox | 0x8062BA08 | 0x328 | 8 B per character | 0x80804720 |
| captain star gains | 0x8062BD50 | 0x3D8 | - | 0x808273C0 |
| captain lineup frames | 0x8062C9F0 | 0xC | - | 0x8082733C |
| stadium snd_env | 0x8062E568 | 0x50 | 8 B rows | 0x808299B0 |
| stadium amb_pair | 0x8062E5B8 | 0x50 | 8 B rows | 0x80829A08 |
| stadium amb | 0x8062E608 | 0x28 | 4 B rows | 0x80829A60 |
| stadium setup_e940 | 0x8062E940 | 0xF0 | 24 B rows | 0x80829A8C |
| sizescale | 0x8062EB50 | 0x328 | 8 B per character | 0x80804F20 |
| selector | 0x80631550 | 0x328 | 8 B per character | 0x807F7000 |
| grid heads | 0x80631878 | 0x2B | 1 B rows | 0x80824E88 |
| captain table | 0x806318A8 | 0x30 | - | 0x808272F4 |
| captain portraits | 0x80631D30 | 0x30 | - | 0x80827350 |
| stadium pre_sound1 | 0x80631EC0 | 0x28 | 4 B rows | 0x80829C94 |
| stadium pre_sound2 | 0x80631EE8 | 0x28 | 4 B rows | 0x80829CC0 |
| stadium objlists | 0x806467D0 | 0x50 | 8 B rows | 0x80829824 |
| stadium objcounts | 0x80646820 | 0x28 | 4 B rows | 0x8082987C |
| stadium obj_instances | 0x806489E8 | 0x50 | 8 B rows | 0x80829E38 |
| stadium obj_inst_counts | 0x80648A38 | 0x24 | 4 B rows | 0x80829E90 |
| dt_na directories | 0x806A0728 | 0x2B0 | 4 B rows | 0x8081D9EC |
| hasmodel | 0x806B4970 | 0x65 | 1 B per character | 0x80805B20 |
| stadium options | 0x806C8D38 | 0x78 | 12 B rows | 0x80829BC0 |
| stadium hints | 0x806C9D20 | 0x28 | 4 B rows | 0x80829B94 |
| stats | 0x806CE9A0 | 0x380E | 142 B per character | 0x807F7800 |
| stadium tod_records | 0x806D9450 | 0x12C | 30 B rows | 0x80829CEC |
| stadium archive2 | 0x806D9980 | 0x50 | 8 B rows | 0x808297CC |
| stadium archive | 0x806D99E0 | 0x50 | 8 B rows | 0x80829774 |
| model handles | 0x80709408 | 0x4BC | 12 B rows | 0x8081E224 |

Names are the patcher's own (charbuild.py). `perid2`, `perid4`, `perid5a`, `perid6` and `throwvariant` are per-
character rows whose meaning isn't known yet. The patcher also adds its own code and data after the original game's
sections; that has no names in the modder files.

# Where our docs disagree

- **Stats table start:** rows start at 0x806CE9A8 (0x806CE9A0 is the header). new-characters-feasibility.md says
  0x806CE9A7, which is one byte off.
- **Voice families:** 0x80631FD0 in character-ids.md's text, 0x80631FC0 in its own table and in
  char-limit-sites.md.
- **Has own model:** 0x806B4970 in most docs, 0x806B49B8 in clean-base.md.
- **Out of date:** customization-inventory.md says items.md, star-swings.md and stadium-hazards.md lag behind the
  code in places.

# Location references in the repo

- **char-limit-sites.md**: every 101-character limit, per-character table and save-file site.
- **stadium-id-sites.md**: every per-stadium table.
- **mod-tables.md**: the table list and the patched game's memory layout.
- **table-refs.tsv**: the code references to each table.
- **character-ids.md**: the selector table's layout.
