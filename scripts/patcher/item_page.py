"""The Create tab's Items page (create_tab.py; git-f4, git-f3's creators/items.py): the player's own batting items
from building blocks, on git-b6's creation_editor.CreationPage. Its own module so that the Characters Beta's Items
window (items_window.py) embeds the same page without the star swing and pitch creators (a lean download ships none
of them). offer(preset stem) -> whether one of our presets is listed (the beta: Ice only); credit: the page's own
"Create" thanks line (the beta's window shows it once, at its top).
"""
import json
import tkinter as tk
from tkinter import ttk, messagebox, filedialog

import creation_editor as ce
import fit
import widgets
from creators import blocks
import creators.items as items


def copy_of(kind, preset, name):
    """A new creation: a copy of one of ours, renamed and not tied to it."""
    c = json.loads(json.dumps(blocks.presets(kind)[preset]))
    c.update(name=name, **{"from": None})
    return c


class ItemPage(ce.CreationPage):
    def __init__(self, notebook, app, folder=ce.FOLDER, offer=None, credit=True):
        super().__init__(notebook, app, "item", "Items", folder=folder, offer=offer, credit=credit,
                         template=lambda name: copy_of("item", "ice", name),
                         needs=lambda c: {"item-engine"},     # custom items' machinery (git-f3 7f689ab)
                         intro="A new item starts as a copy of our Ice ball. Pick how it's thrown (the chassis), then "
                               "how it moves, what a hit does, and how it looks. Up to 8 new items.",
                         order=["item", "given", "launch", "move", "hit", "effect", "spawn", "look", "label", "sound"])

        self.chassis_note = widgets.status(fit.label(self.use.master, "", grey=True))   # what the item is built on can do (git-f3)
        self.chassis_note.pack(fill="x", after=self.use, pady=(2, 4))
        row = ttk.Frame(self.use.master)     # the player's own sounds (git-f3: which events a chassis takes)
        row.pack(anchor="w", after=self.chassis_note)
        ttk.Label(row, text="Your own sound for the:").pack(side="left")
        self.sound_event = tk.StringVar(value="throw")
        self.sound_events = ttk.Combobox(row, textvariable=self.sound_event, state="readonly", width=9)
        self.sound_events.pack(side="left", padx=4)
        ttk.Button(row, text="Pick a .wav...", command=self.pick_sound).pack(side="left")

    def pick_sound(self):
        """The player's own sound for the event picked (git-f3's sound.<event>_clip): the .wav is checked
        (creators.items.clip_problem), copied next to the item's file, listed in its "files", and
        creators.items.customs runs on the item."""
        if self.path is None or self.editor.readonly:
            messagebox.showinfo(self.title, "Copy one of ours to edit first (Copy to edit), or make a New one: then "
                                            "you can give it your own sound.", parent=self)
            return
        word = self.sound_event.get() or "throw"
        src = filedialog.askopenfilename(title=f"{word.capitalize()} sound", filetypes=[("WAV sound", "*.wav")],
                                         parent=self)
        if src:
            self.set_sound(src, {w: e for e, w in items.SOUND_EVENTS.items()}[word])

    def set_sound(self, src, event="launch"):
        """The player's .wav as the item's sound for one event (launch = the throw, hit, land = the landing)."""
        import shutil
        from pathlib import Path
        src = Path(src)
        problem = items.clip_problem(src)
        if problem:
            messagebox.showwarning(self.title, f"That sound can't be used: {problem}", parent=self)
            return False
        dst = self.path.parent / f"{self.path.stem} {items.SOUND_EVENTS[event]}{src.suffix.lower()}"
        if src.resolve() != dst.resolve():
            shutil.copyfile(src, dst)
        c = json.loads(json.dumps(self.editor.get()))
        sound = c["blocks"].setdefault("sound", {"type": "sound"})
        sound.pop(event, None)                   # one or the other: a game sound id, or the player's clip
        old = sound.get(f"{event}_clip")
        sound[f"{event}_clip"] = dst.name
        c["files"] = [f for f in c.get("files", []) if f != old] + [dst.name]
        try:
            items.customs([c])
        except blocks.Invalid as e:
            messagebox.showwarning(self.title, f"That sound can't be used: {e}", parent=self)
            return False
        self.editor.set(c)
        self.flush()
        self.status.configure(text=f"{items.SOUND_EVENTS[event].capitalize()} sound: {dst.name} (saved next to "
                                   f"{self.path.name}).")
        return True

    def show_chassis(self, c):
        ch = ((c or {}).get("blocks", {}).get("item") or {}).get("chassis")
        note = blocks.schema()["chassis"].get(ch, {}).get("notes", "") if ch else ""
        self.chassis_note.configure(text=f"Built on {ch}: {note}" if note else "")
        words = [items.SOUND_EVENTS[e] for e in items.SOUND_CHASSIS.get(ch, ("launch",))]
        self.sound_events.configure(values=words)
        if self.sound_event.get() not in words:
            self.sound_event.set(words[0])

    def selected(self, *a, **k):
        super().selected(*a, **k)
        self.show_chassis(self.editor.get())

    def edited(self, c):
        self.show_chassis(c)
        super().edited(c)

    def use_toggled(self):
        """Also the build's own limits (creators.items.customs: plain words) before an item is used."""
        if self.use_var.get() and self.path is not None:
            self.flush()
            here = ce.rel(self.path)
            used = [c for k, c in self.used_creations() if k != here] + [self.editor.get()]
            try:
                items.customs(used)
            except blocks.Invalid as e:
                messagebox.showwarning(self.title, f"{self.editor.get()['name']} can't go in the game yet: {e}",
                                       parent=self)
                self.use_var.set(False)
                return
        super().use_toggled()
