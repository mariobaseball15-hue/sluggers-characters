"""Small editor for direct PNG replacements on the game's stock/base character models."""
import io
import tkinter as tk
from tkinter import ttk, filedialog, messagebox
from pathlib import Path
from PIL import Image, ImageTk

import base_textures
from mss_model import Model
from recolor_block import decode
from sluggers_data import CHAR_NAMES

MODEL_DIR_BASE = 0x12


class Window:
    def __init__(self, parent, game):
        self.game = game
        self.win = tk.Toplevel(parent)
        self.win.title("Base textures — Sluggers Characters Beta")
        self.win.geometry("900x650")
        self.win.minsize(720, 500)
        top = ttk.Frame(self.win, padding=10); top.pack(fill="both", expand=True)
        ttk.Label(top, text="Edit stock/base model textures", font=("TkDefaultFont", 12, "bold")).pack(anchor="w")
        ttk.Label(top, text="Replaces only selected PNG textures in the stock model. Model structure, bones and animations stay unchanged.", wraplength=850).pack(anchor="w", pady=(2,8))
        row = ttk.Frame(top); row.pack(fill="x")
        ttk.Label(row, text="Character:").pack(side="left")
        self.names = [n.strip() for n in CHAR_NAMES if n.strip()]
        self.name = tk.StringVar(value=self.names[0])
        self.combo = ttk.Combobox(row, textvariable=self.name, values=self.names, state="readonly", width=28)
        self.combo.pack(side="left", padx=(6,12)); self.combo.bind("<<ComboboxSelected>>", lambda e:self.refresh())
        ttk.Button(row, text="Clear this character", command=self.clear_character).pack(side="left")
        mid = ttk.Frame(top); mid.pack(fill="both", expand=True, pady=(10,0))
        left = ttk.Frame(mid); left.pack(side="left", fill="y")
        ttk.Label(left, text="Textures (High + Low)").pack(anchor="w")
        self.list = tk.Listbox(left, selectmode="extended", width=38, exportselection=False)
        sb = ttk.Scrollbar(left, orient="vertical", command=self.list.yview); self.list.configure(yscrollcommand=sb.set)
        self.list.pack(side="left", fill="y", expand=True); sb.pack(side="left", fill="y")
        self.list.bind("<<ListboxSelect>>", lambda e:self.preview())
        right = ttk.Frame(mid); right.pack(side="left", fill="both", expand=True, padx=(14,0))
        ttk.Label(right, text="Preview").pack(anchor="w")
        self.preview_label = ttk.Label(right, anchor="center"); self.preview_label.pack(fill="both", expand=True)
        buttons = ttk.Frame(top); buttons.pack(fill="x", pady=(10,0))
        ttk.Button(buttons, text="Replace selected...", command=self.replace).pack(side="left")
        ttk.Button(buttons, text="Clear selected", command=self.clear_selected).pack(side="left", padx=(6,0))
        ttk.Button(buttons, text="Close", command=self.win.destroy).pack(side="right")
        self.rows=[]; self.photos=[]; self.refresh()

    def cid(self):
        want=self.name.get()
        for i,n in enumerate(CHAR_NAMES):
            if n.strip()==want: return i
        return 0

    def refresh(self):
        self.list.delete(0,"end"); self.rows=[]; self.photos=[]
        cid=self.cid(); edits=base_textures.replacements(cid)
        for fi,label in ((0,"High"),(1,"Low")):
            try:
                block=self.game.file(cid+MODEL_DIR_BASE,fi)
                model=Model(block)
            except Exception:
                continue
            for ti,tex in enumerate(model.textures):
                try:
                    img=decode(block,tex).convert("RGBA")
                    mark=" *" if (fi,ti) in edits else ""
                    self.rows.append((fi,ti,img))
                    self.list.insert("end",f"{label} texture {ti}  ({img.width}x{img.height}){mark}")
                except Exception:
                    pass
        if self.rows:
            self.list.selection_set(0); self.preview()
        else:
            self.preview_label.configure(image="", text="No readable High/Low model textures for this character.")

    def preview(self):
        sel=self.list.curselection()
        if not sel:return
        fi,ti,img=self.rows[sel[0]]
        p=base_textures.replacements(self.cid()).get((fi,ti))
        if p:
            try: img=Image.open(p).convert("RGBA")
            except OSError: pass
        img=img.copy(); img.thumbnail((430,430),Image.Resampling.LANCZOS)
        ph=ImageTk.PhotoImage(img); self.photos=[ph]; self.preview_label.configure(image=ph,text="")

    def replace(self):
        sel=list(self.list.curselection())
        if not sel:
            messagebox.showinfo("Base textures","Select one or more textures first.",parent=self.win); return
        files=list(filedialog.askopenfilenames(parent=self.win,title="Choose replacement PNG texture(s)",filetypes=[("PNG images","*.png")]))
        if not files:return
        if len(files) not in (1,len(sel)):
            messagebox.showwarning("Base textures","Choose one PNG for one selected texture, or the same number of PNGs as selected textures.",parent=self.win); return
        if len(files)==1 and len(sel)>1:
            files=files*len(sel)
        for idx,src in zip(sel,files):
            fi,ti,_=self.rows[idx]; base_textures.set_png(self.cid(),fi,ti,src)
        self.refresh()

    def clear_selected(self):
        keys=[]
        for idx in self.list.curselection():
            fi,ti,_=self.rows[idx]; keys.append(f"{fi}:{ti}")
        if keys: base_textures.clear(self.cid(),keys); self.refresh()

    def clear_character(self):
        if messagebox.askyesno("Base textures",f"Clear all base texture replacements for {self.name.get()}?",parent=self.win):
            base_textures.clear(self.cid()); self.refresh()


def open_window(parent, game):
    return Window(parent, game)
