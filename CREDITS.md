# Credits

This patcher is a fan project, made possible by years of work from the Mario Super Sluggers modding community. Much
of what it does, someone in the community did first, as a Gecko code, a tool, a guide or a mod: we thank them below,
and we would rather thank too much than too little. docs/credits-map.md says, part by part, what each person's work
gave us.

Is something here your work, or did we miss you or get it wrong? Please tell us (the modding Discord) and we will
name you properly.

## The community

- **Jbiscuit**: Extra Innings, the first mod with new characters (Rosalina, Luma, Larry, Orange Toad), its patcher,
  the Custom Characters readme, the custom character sounds pipeline, the skin-toggle icon pipeline, and the Galaxy
  stadium. Extra Innings showed that all of this was possible.
- **Jaws** (Jaws-git): Sluggies-dat-tools, https://github.com/Jaws-git/Sluggies-dat-tools: model export and import,
  the icon bank and its source tables, the model validator, texture repacking, and the .sluggie format players edit
  models in (the patcher's "Add a model from Sluggies").
- **LlamaTrauma**: MSS-dat-tools, https://github.com/LlamaTrauma/MSS-dat-tools: reading dt_na.dat, model and stadium
  export and import; an early stat and chemistry editor; the Item Rain mod and several Gecko codes.
- **philenarion** (Phil): the Sluggers Stat Editor, https://philenarion.github.io/Sluggers-Stat-Editor/: the stat
  names, the stats layout, and the order of characters, star moves and abilities we use everywhere.
- **C²** (isThatC2): CPU vs CPU V2, the CPU closeplay, lineup and triple-take codes, Random Star Hits and Pitches,
  Day/Night Music Themes, the hitting power uncap code, the Sluggers Stat Tracker, and findings on fielding and model
  data.
- **LittleCoaks**: the original CPU vs CPU mod, Duplicate Captains, Captains Have Chemistry With Themselves, and
  Unlimited extra innings.
- **Becket**: the community modding guide and the mods and Gecko codes list, and Team Builder (with tyblinger).
- **Cuyler36**: the GameCube loader for Ghidra.
- **roeming**: MSSB-Export-Models and the Mario Sluggers model format documentation,
  https://thatsrightigame.com/sluggers/format_docs/.
- **Vasquez**: the CPU Star Pitch/Swing Editor and stat documentation.
- **benhub86**: Everybody Has Chemistry With Everyone.
- **TNTkryzt**: Reset Out Count, All Star Players, All MVPs, Unlock All Items and more codes.
- **Master Kirby**: Scale the Batter, Green Shell Size Modifier and more codes.
- **The Fun Guy**: the stats spreadsheet, and CPU Remove Precharge with philenarion.
- **STG** (STGtheOG) and **harrhy**: LogoTextGen, MSS-AutoTeam, the image editor and the autoteam picker.
- **Ethlitee**: the custom audio guide. **pavaldatsack**: the custom music steps in the guide.
- **Xeno9**: Afternoon on Mario Stadium.
- And everyone else in the Gecko codes list and the guide: **qwertyuiop**, **dementatino**, **ZPL**, **Kircher**,
  **tyblinger**, **JimmyKazakhstan**, **NibrocRock**, **Geno**, **MarioMorty**, **MachoManMal**, and the makers of the first CPU vs CPU code on Reddit
  and of the community's custom stadiums and texture packs, whose names we don't have.

## Thanks, part by part

A line per tab of the patcher window; the window shows each one on its tab. The code is ours; what these people made
showed us the way, gave us the research and formats to work from, or is used here under its licence.

- Features: Thanks to everyone in the community's Gecko codes list, kept by Becket: many of these features were someone's Gecko code first.
- New characters & recolors: Thanks to Jbiscuit's Extra Innings, which showed new characters could be done (its four characters are used under Apache-2.0), and to Jaws' Sluggies-dat-tools research.
- Import character: Thanks to Jaws and LlamaTrauma, whose model format research made shareable character files possible, and to Jbiscuit's Extra Innings.
- Add a model from Sluggies: Thanks to Jaws, whose Sluggies-dat-tools lets players export a character's model, edit it in Blender and export it back as a .sluggie; the patcher reads that file with its own code, and Jaws was happy for us to build on it.
- Characters: Thanks to philenarion, whose Sluggers Stat Editor mapped the stats and gave us the stat names and character order we use, and to LlamaTrauma for the first stat and chemistry editor.
- Captains: Thanks to LittleCoaks, whose Duplicate Captains code did it first.
- Abilities: Thanks to philenarion's Sluggers Stat Editor for the ability ids, and to C² (CPU Closeplay Overhaul) and dementatino (CPUs Can Dive and Jump in Outfield), whose Gecko codes worked on the same abilities first.
- Select grid: Thanks to the whole Sluggers modding community for years of findings about the game; the grid itself is our own work.
- Create: Thanks to Vasquez, C², LlamaTrauma and Master Kirby, whose star-move and item Gecko codes did this kind of thing first.
- Stadiums: Thanks to Jbiscuit's Galaxy stadium, the community's custom stadiums, LlamaTrauma's MSS-dat-tools research and STG's LogoTextGen; music is encoded with VGAudio (MIT).
- CPU vs CPU: Thanks to C² (CPU vs CPU V2) and LittleCoaks (the original CPU vs CPU mod), who did this first as Gecko codes.
- Voices: Thanks to Jbiscuit, whose custom character sounds guide showed how voices are routed; ours follows his method in our own code.
- Recolors: Thanks to Jbiscuit's skin-toggle icon guide and the community's texture packs, which showed the way.
- The patcher: Thanks to Jbiscuit, whose Extra Innings patcher first patched your own clean game this way, and to the whole Sluggers modding community.

## In the Characters Beta

What the Characters Beta's credits say (scripts/credits.py text(edition)): the sections above as they are, except these,
which take the place of "Thanks, part by part", "Extra Innings", "Models and sounds", "Music" and "Software", so the
beta names only what it has and ships. Everyone named anywhere above who isn't named in the beta's text is thanked in one line after them.

### Part by part

Characters, Select grid, Voices, Recolors, Import character, Captains, CPU vs CPU, Items = Create, The patcher

### Page

Thanks to Jbiscuit's Extra Innings (Rosalina, used under Apache-2.0), to Jaws and LlamaTrauma, whose model research made new characters possible, and to Jaws' Sluggies-dat-tools for Add a model from Sluggies.

### Extra Innings

Mario Super Sluggers: Extra Innings v0.0.8 by **Jbiscuit**, https://github.com/jackb54/mario-super-sluggers-extra-innings,
licensed under the Apache License 2.0 (a copy ships in this download's refs/ folder). Extra Innings was the first mod to
add new characters to the game, and this beta uses its Rosalina: her character data (her rows in the per-character
tables, her stats and chemistry) and her model directory's skeleton and animations, built on Daisy. We changed her model,
bat, portrait, name plate and voice, and straightened her animations.

### Models and sounds

Rosalina's model comes from Mario Kart 8 and her voice clips from The Sounds Resource: they are Nintendo's, shared by
rippers at The Models Resource and The Sounds Resource (The VG Resource), whose names we haven't recorded. Volcano Pianta
is made from your own game's Blue Pianta. If one of these is your rip, please tell us so we can name you.

### Software

- Wiimms ISO Tools (wit) and Wiimms SZS Tools (wimgt), by Dirk Clemens (Wiimm), GPL-2: https://wit.wiimm.de,
  https://szs.wiimm.de. Shipped unchanged with their licence.
- Python (Python Software Foundation), frozen with PyInstaller (GPL-2 with its bootloader exception); Pillow (MIT-CMU),
  NumPy (BSD-3-Clause), SciPy (BSD-3-Clause) and Tcl/Tk (BSD-style).
- Thanks to rdbende for Sun Valley (sv-ttk), the patcher window's theme, MIT:
  https://github.com/rdbende/Sun-Valley-ttk-theme. Shipped unchanged with its licence.
- Made with: Blender (Blender Foundation), Ghidra (NSA) with Cuyler36's GameCube loader, Dolphin (the Dolphin
  Emulator Project), Unicorn (Nguyen Anh Quynh and contributors).

## Extra Innings

Mario Super Sluggers: Extra Innings v0.0.8 by Jbiscuit,
https://github.com/jackb54/mario-super-sluggers-extra-innings, licensed under the Apache License 2.0 (a copy:
refs/extra-innings-v0.0.8/Mario_Super_Sluggers_Extra_Innings_v0.0.8_Patcher/LICENSE-APACHE-2.0.txt).

We keep Extra Innings' four characters as new characters: Rosalina (0x81), Orange Toad (0x82), Larry (0x83) and
Luma (0x84). From Extra Innings we use their character data (their rows in the per-character tables, their stats
and chemistry) and their model directories (skeleton layouts and animations). scripts/ei_characters.py lists exactly
what is taken. We changed their models, bats, portraits, name plates, voices, stats and chemistry, and straightened
Rosalina's animations. We left out Extra Innings' team stat boost, Cloud Mario skin toggle, Galaxy stadium and music.
Details: docs/clean-base.md and docs/stock-slot-migration.md.

## Models and sounds

The models and voices of our new characters come from other Mario games: they are Nintendo's. We didn't rip them
ourselves; thank you to the rippers who shared them.

- Dry Bowser (Mario Kart 8): ripped by **Mystie** of The VG Resource, with thanks to **Random Talking Bush**'s BFRES
  importing script.
- Lubba (Super Mario Galaxy 2): ripped by **DJ_Fox11**, The Models Resource.
- The Chimp (Super Mario Galaxy 2), Pom Pom (Super Mario Party), Iggy Koopa (Mario Kart 8; first ripped by
  **Ray Koopa**): ripped by **DogToon64**.
- Boom Boom (New Super Mario Bros. U): ripped by **BzarrTehAxolotl**.
- Bob-omb, Bouldergeist, Dino Piranha, Gearmo, the Good Egg Galaxy, Honey Queen, Luma, Octoomba, Penguru, Star Bits
  and the Toad Brigade (Super Mario Galaxy); Larry, Lemmy, Ludwig, Morton, Roy, Wendy and Rosalina (Mario Kart 8);
  Pauline (Mario Kart 8 Deluxe); Bob-omb Battlefield (Super Mario 64); the Poltergust 3000: from The Models Resource
  (The VG Resource). Ripper not recorded.
- Voice clips (Super Mario Galaxy 1 and 2, Mario Kart 8 and 8 Deluxe, Mario Tennis Aces, Mario Golf: Super Rush,
  Super Mario 3D Land, Super Mario Party): from The Sounds Resource (The VG Resource). Ripper not recorded.

If one of these is your rip, please tell us so we can name you.

## Music

Stadium music is openly licensed (CC0): "Snow Globe" by **bobjt** and "Children's March Theme" by **Cleyton Kauffman**, both
from OpenGameArt; details in stadiums/music/CREDITS.txt.

The chance cheer plays a short snippet of "Jump Up, Super Star!" (composed by **Koji Kondo**, Nintendo), in **The Living
Tombstone**'s remix (2017). It is not openly licensed; it is included as a small fan-project use, with thanks to both,
and will be removed on request.

## Fonts

- Orbitron, The Orbitron Project Authors, SIL Open Font License 1.1: the new characters' names in the pitching-change
  banner. scripts/fonts/, with its licence.
- Open Sans, Copyright 2020 The Open Sans Project Authors (https://github.com/googlefonts/opensans), SIL Open Font
  License 1.1, from google/fonts: the character-select name labels and the captain-select name plates.
  scripts/fonts/, with its licence.

## Software

- Wiimms ISO Tools (wit) and Wiimms SZS Tools (wimgt), by Dirk Clemens (Wiimm), GPL-2: https://wit.wiimm.de,
  https://szs.wiimm.de. Shipped unchanged with their licence.
- VGAudio (VGAudioCli), by Alex Barney, MIT: https://github.com/Thealexbarney/VGAudio. Shipped with its licence.
- Python (Python Software Foundation), frozen with PyInstaller (GPL-2 with its bootloader exception); Pillow (MIT-CMU),
  NumPy (BSD-3-Clause), SciPy (BSD-3-Clause) and Tcl/Tk (BSD-style).
- Thanks to rdbende for Sun Valley (sv-ttk), the patcher window's theme, MIT:
  https://github.com/rdbende/Sun-Valley-ttk-theme. Shipped unchanged with its licence.
- Made with: Blender (Blender Foundation), Ghidra (NSA) with Cuyler36's GameCube loader, Dolphin (the Dolphin
  Emulator Project), Unicorn (Nguyen Anh Quynh and contributors), xdelta3 (Josh MacDonald).

## Thank you

The Mario Super Sluggers modding community on Discord: for years of findings, questions and answers.
