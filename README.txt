Made possible by the Mario Super Sluggers modding community: see CREDITS.txt (Jbiscuit, Jaws, LlamaTrauma,
philenarion, C², LittleCoaks, Becket and many more).

Mario Super Sluggers patcher
============================

Beta 2.0 usability upgrade
--------------------------
- Import texture PNG(s): on the Characters page, choose an edited Dolphin texture dump (tex1_...png). The patcher
  also reads the other tex1_*.png files in the same folder and builds them as a character texture variant.
- Remove from game: select a non-stock character on a grid color wheel and click Remove from game. This switches the
  character out of the build, so grid refreshes no longer add it back. It remains installed and can be re-enabled.
- Grid refresh work avoids treating intentional roster removal as a temporary visual edit.


Run "Sluggers Patcher.exe". It asks for:
  1. your own clean Mario Super Sluggers (USA, RMBE01): the .iso, or an extracted game folder. Put your .iso in this
     folder and it's filled in for you, with "Save as" set to "<your game> - <this patcher>.iso" beside it
  2. a profile: which features and characters go in (the examples in scripts/patcher/profiles/, or your own)
  3. where to write the patched ISO
and writes a new ISO. Your game is never changed. Play the new ISO in Dolphin or on a Wii. Next to it, the
"<name> (patch details)" folder has what you picked (choices.json), the patcher's log (log.txt: send it to us if a
patch goes wrong) and relocations.json (for "Fix my Gecko codes..."); it's not a game, don't open it in Dolphin.

Nothing of Nintendo's is in this download: everything the patch copies from the game is read from your copy.
The first run rebuilds our files that sit on top of the game's (models, stadiums) from it. An .iso is extracted
once into cache/game next to the program (about 4.4 GB) and reused; delete that folder to get the space back. Keep
the patcher's folder somewhere you can write.

Your own profile (a .json file):
  {"features": ["batter-depth", "new-stadium", "walking-bobombs"],
   "options": {"menu-color": {"color": "teal"}},
   "new_characters": ["characters/0x66_pauline.json"],
   "recolors": ["recolors/purple-yoshi.json"]}
The feature ids are on the notes page. From a command prompt, "Sluggers Patcher.exe --list" lists them.

wit (Wiimms ISO Tools, https://wit.wiimm.de) and wimgt (Wiimms SZS Tools, https://szs.wiimm.de) are in tools/,
unchanged, with their licence (GPL-2); their source is at those sites. VGAudioCli (VGAudio, MIT,
https://github.com/Thealexbarney/VGAudio) is in tools/vgaudio with its licence; it needs .NET Framework 4.
