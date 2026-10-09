"""The character window's Voice page (Nick: "How would people edit them??"): the 12 moments the game plays a
character's voice, one row each: what plays now (the player's clip, or the base's), Play, Choose WAV... and Use
base's. Characters we added only (imported, .sluggie, recolors, character files); a stock character has no page.

A chosen WAV is converted at once into the player's folder (voice_clips.take: mono, 22,050 Hz, 16-bit, cut to
1.4 s, said when it was cut) and kept in the character's per-character keys as "voice_clips" {slot: file}, in
app.extra_characters like the character editor's own edits, so the profile carries it and the patch gives the
character a voice set of its own (voice_clips.prepare). Choosing one ticks Voices. "Load a folder..." fills every
slot a folder has a clip for at once, matched by name as a new character's folder import does (char_import.voices:
voice/*.wav, v3.wav, luma_v3.wav, ...), and says which slots it filled.
"""
import tempfile
import tkinter as tk
from pathlib import Path
from tkinter import filedialog, ttk

import fit
import widgets

HEADLESS_PLAYS = []                 # (a test's Play: what would have played; nothing is played under headless)


def base_of(app, kind, d, depth=0):
    """(template name, the folder of the base's own full voice set or None) for a character of the window."""
    import voice_clips
    if kind == "recolor":
        import recolor
        base = d.get("base")
        other = next(((k, x) for n, k, x, _ in app.roster() if n == base and k in ("new", "imported", "recolor")),
                     None)
        if other and depth < 4:
            return base_of(app, other[0], other[1], depth + 1)
        return recolor.template_of(base), None
    if kind == "imported" and d.get("voice"):
        c = next((c for c in app.imported() if c["name"] == d["name"]), None)
        folder = Path(c["folder"]) / d["voice"] if c else None
        return d.get("template"), folder if folder and all((folder / f"{s}.wav").is_file()
                                                           for s in voice_clips.SLOTS) else None
    return d.get("template"), voice_clips.own_set(d)


def play(path):
    """Play a WAV without waiting (Windows' own player); a test records it instead."""
    if getattr(tk, "_headless", None) is not None:
        HEADLESS_PLAYS.append(str(path))
        return
    try:
        import winsound
        winsound.PlaySound(str(path), winsound.SND_FILENAME | winsound.SND_ASYNC)
    except (ImportError, RuntimeError):
        pass                        # (no sound device: nothing to play it on)


class VoicePage:
    def __init__(self, page, app, name, kind, d, game_folder):
        import voice_clips
        self.vc, self.app, self.name, self.game_folder = voice_clips, app, name, game_folder
        self.template, self.base_set = base_of(app, kind, d)
        self.rows = {}
        ok, why = voice_clips.can_have_own({"template": self.template})
        whose = "its own voice's" if self.base_set else f"{self.template}'s"
        fit.label(page, ("The 12 moments the game plays this character's voice. Choose a WAV for any of them "
                         f"(any WAV: it's made mono, 22,050 Hz and at most 1.4 s long); the others play {whose}.")
                  if ok else f"No voice to change: {why}.").pack(fill="x", pady=(0, 4))
        bar = ttk.Frame(page)
        bar.pack(fill="x", pady=(0, 2))
        self.folder_button = ttk.Button(bar, text="Load a folder...", command=self.load_folder)
        self.folder_button.pack(side="left")
        ttk.Label(bar, text="WAVs named by slot (v1.wav ... v14.wav, or name_v3.wav) fill their slots at once.",
                  foreground=widgets.GREY).pack(side="left", padx=6)
        if not ok:
            self.folder_button.state(["disabled"])
        self.note = widgets.status(ttk.Label(page, text="", foreground=widgets.GREY, wraplength=680, justify="left"))
        self.note.pack(fill="x")
        box = widgets.Scrolled(page)
        box.pack(fill="both", expand=True)
        for i, slot in enumerate(voice_clips.SLOTS):
            ttk.Label(box.inner, text=voice_clips.MOMENTS[slot] + ":").grid(row=i, column=0, sticky="w", pady=1)
            now = ttk.Label(box.inner, text="", foreground=widgets.GREY, width=30)
            now.grid(row=i, column=1, sticky="w", padx=6)
            b_play = ttk.Button(box.inner, text="Play", width=6, command=lambda s=slot: self.play(s))
            b_play.grid(row=i, column=2)
            b_pick = ttk.Button(box.inner, text="Choose WAV...", command=lambda s=slot: self.choose(s))
            b_pick.grid(row=i, column=3, padx=4)
            b_base = ttk.Button(box.inner, text="Use base's", command=lambda s=slot: self.use_base(s))
            b_base.grid(row=i, column=4)
            if not ok:
                for b in (b_play, b_pick, b_base):
                    b.state(["disabled"])
            self.rows[slot] = (now, b_base)
            self.show(slot)

    def clips(self):
        return self.app.extra_characters.get(self.name, {}).get(self.vc.KEY, {})

    def show(self, slot):
        now, b_base = self.rows[slot]
        mine = self.clips().get(slot)
        now.configure(text=f"Yours: {Path(mine).name}" if mine else ("Its own" if self.base_set else
                                                                     f"{self.template}'s"))
        b_base.state(["!disabled"] if mine else ["disabled"])

    def play(self, slot):
        mine = self.clips().get(slot)
        if mine:
            return play(mine)
        if self.base_set:
            return play(self.base_set / f"{slot}.wav")
        out = Path(tempfile.gettempdir()) / "sluggers-voices" / f"{self.vc.stock_prefix(self.template)}_{slot}.wav"
        try:
            got = out if out.is_file() else self.vc.stock_clip(self.game_folder, self.template, slot, out)
        except Exception as e:      # noqa: BLE001 (said in words)
            self.note.configure(text=f"Couldn't read {self.template}'s clip from your game: {type(e).__name__}: {e}")
            return None
        if got is None:
            self.note.configure(text=f"{self.template} has no clip for this in your game.")
            return None
        return play(got)

    def take(self, slot, path):
        """(the converted clip, voice_clips.take's report) kept for slot; raises VoiceError / OSError."""
        import patch
        out, r = self.vc.take(path, self.name, slot, patch.IMPORTED_DEST)
        e = self.app.extra_characters.setdefault(self.name, {})
        e[self.vc.KEY] = dict(e.get(self.vc.KEY) or {}, **{slot: str(out)})
        self.show(slot)
        return out, r

    def choose(self, slot, path=None):
        path = path or filedialog.askopenfilename(title=f"{self.name}: {self.vc.MOMENTS[slot]}",
                                                  filetypes=[("Sound (WAV)", "*.wav"), ("All", "*")])
        if not path:
            return None
        try:
            out, r = self.take(slot, path)
        except (self.vc.VoiceError, OSError) as e:
            self.note.configure(text=str(e))
            return None
        self.app.tick({"voices"}, why=f"{self.name}'s voice")
        self.note.configure(text=f"{Path(path).name}: cut to {self.vc.MAX_SECONDS} s (it was {r['seconds']:.1f} s)."
                            if r["cut"] else f"{Path(path).name} is in: {self.vc.MOMENTS[slot]}.")
        return out

    def load_folder(self, folder=None):
        """A folder of WAVs into the slots its names say (char_import.voices, as a character folder's import); the
        note says which slots were filled. {slot: converted clip} of those filled."""
        folder = folder or filedialog.askdirectory(title=f"{self.name}: a folder of voice clips")
        if not folder:
            return None
        import char_import
        clips, other = char_import.voices(folder)
        filled, failed, cut = {}, [], []
        for slot in self.vc.SLOTS:
            if slot not in clips:
                continue
            try:
                out, r = self.take(slot, str(clips[slot]))
            except (self.vc.VoiceError, OSError) as e:
                failed.append(f"{clips[slot].name} ({e})")
                continue
            filled[slot] = out
            if r["cut"]:
                cut.append(clips[slot].name)
        name = Path(folder).name
        if filled:
            self.app.tick({"voices"}, why=f"{self.name}'s voice")
            text = (f"From {name}: filled {len(filled)} of {len(self.vc.SLOTS)} slots: "
                    + ", ".join(f"{s} {self.vc.MOMENTS[s]}" for s in filled) + ".")
            rest = [s for s in self.vc.SLOTS if s not in filled]
            if rest:
                text += f" The others are as they were ({' '.join(rest)})."
        else:
            text = f"No voice clips in {name}: name the WAVs by slot (v1.wav, v3.wav ... v14.wav, or luma_v3.wav)."
        if cut:
            text += f" Cut to {self.vc.MAX_SECONDS} s: {', '.join(cut)}."
        if failed:
            text += f" Not used: {'; '.join(failed)}."
        if other:
            text += f" Not a clip slot: {', '.join(other[:6])}{' ...' if len(other) > 6 else ''}."
        self.note.configure(text=text)
        return filled

    def use_base(self, slot):
        e = self.app.extra_characters.get(self.name, {})
        clips = dict(e.get(self.vc.KEY) or {})
        clips.pop(slot, None)
        if clips:
            e[self.vc.KEY] = clips
        else:
            e.pop(self.vc.KEY, None)
        self.note.configure(text="")
        self.show(slot)
