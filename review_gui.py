#!/usr/bin/env python3
"""review_gui - the text review/correction screen for Drawing2CAD.

Opens a .review.json sidecar written during conversion, shows each uncertain
label beside its magnified image crop, and lets the user confirm (Enter) or
fix the text. On finish it writes a corrected DXF (fixes moved off the red
review layer) and saves every confirmed/corrected label as a training pair
for the local OCR - the Phase C data flywheel.

Run standalone:  python review_gui.py drawing.review.json
"""

import os
import sys

import customtkinter as ctk
import tkinter as tk
from tkinter import filedialog, messagebox
from PIL import Image
import cv2
import numpy as np

import corrections

ACCENT = "#1A7FE8"; ACCENT2 = "#3D9BFF"
BG_DARK = "#0D0D0D"; BG_CARD = "#1E1E1E"; BG_INPUT = "#252525"
BORDER = "#2E2E2E"; TEXT = "#F0EDE8"; MUTED = "#888480"; GREEN = "#4CAF50"


class ReviewApp(ctk.CTkToplevel):
    def __init__(self, master, json_path):
        super().__init__(master)
        self.title("Review & correct text")
        self.geometry("640x520")
        self.configure(fg_color=BG_DARK)
        self.json_path = json_path
        self.image, words, self.meta = corrections.load_review(json_path)
        # least-certain first: flagged items sorted by ascending confidence,
        # then the confident ones (confirming good reads is training data too)
        flagged = sorted((w for w in words if w.get("review")),
                         key=lambda w: w.get("conf", 0))
        rest = sorted((w for w in words if not w.get("review")),
                      key=lambda w: w.get("conf", 0))
        self.words = flagged + rest
        self.only_flagged = flagged
        self.i = 0
        self.fixes = []      # (new_text, original_text)
        self.pairs = []      # (crop, text)
        self._build()
        self._show()

    def _build(self):
        ctk.CTkLabel(self, text="Fix what's wrong, press Enter to keep. "
                     "Each confirmed label trains the reader.",
                     text_color=MUTED, font=("Segoe UI", 12)).pack(pady=(12, 4))
        self.prog = ctk.CTkLabel(self, text="", text_color=MUTED,
                                 font=("Segoe UI", 12))
        self.prog.pack()
        self.canvas = ctk.CTkLabel(self, text="", fg_color=BG_CARD,
                                   corner_radius=10, width=560, height=200)
        self.canvas.pack(pady=12, padx=20)
        self.entry = ctk.CTkEntry(self, width=420, height=44,
                                  font=("Consolas", 22), fg_color=BG_INPUT,
                                  border_color=ACCENT, justify="center")
        self.entry.pack(pady=6)
        self.entry.bind("<Return>", lambda e: self._commit(keep=True))
        row = ctk.CTkFrame(self, fg_color=BG_DARK)
        row.pack(pady=10)
        ctk.CTkButton(row, text="Not text (delete)", width=140,
                      fg_color=BG_INPUT, hover_color=BORDER,
                      command=lambda: self._commit(delete=True)
                      ).pack(side="left", padx=6)
        ctk.CTkButton(row, text="Skip", width=90, fg_color=BG_INPUT,
                      hover_color=BORDER,
                      command=lambda: self._commit(skip=True)
                      ).pack(side="left", padx=6)
        ctk.CTkButton(row, text="Keep / Next  (Enter)", width=180,
                      fg_color=ACCENT, hover_color=ACCENT2,
                      command=lambda: self._commit(keep=True)
                      ).pack(side="left", padx=6)
        self.status = ctk.CTkLabel(self, text="", text_color=MUTED,
                                   font=("Segoe UI", 11))
        self.status.pack(side="bottom", pady=8)

    def _show(self):
        if self.i >= len(self.words):
            return self._finish()
        w = self.words[self.i]
        crop = corrections.crop_word(self.image, w)
        self._cur_crop = crop
        disp = self._fit(crop, 540, 190)
        self.canvas.configure(image=disp, text="")
        self.canvas.image = disp
        flagged = w.get("review")
        self.prog.configure(
            text=f"{self.i + 1} / {len(self.words)}   "
                 f"({len(self.only_flagged)} flagged)   "
                 f"{'UNCERTAIN' if flagged else 'confidence ok'}",
            text_color="#E85454" if flagged else GREEN)
        self.entry.delete(0, "end")
        self.entry.insert(0, w["text"])
        self.entry.focus_set()

    def _fit(self, crop, maxw, maxh):
        h, w = crop.shape
        s = min(maxw / max(w, 1), maxh / max(h, 1), 8.0)
        big = cv2.resize(crop, (max(1, int(w * s)), max(1, int(h * s))),
                         interpolation=cv2.INTER_NEAREST)
        rgb = cv2.cvtColor(big, cv2.COLOR_GRAY2RGB)
        return ctk.CTkImage(Image.fromarray(rgb),
                            size=(rgb.shape[1], rgb.shape[0]))

    def _commit(self, keep=False, skip=False, delete=False):
        w = self.words[self.i]
        orig = w["text"]
        if delete:
            self.fixes.append(("", orig))          # remove from drawing
        elif keep:
            new = self.entry.get().strip()
            if new:
                self.fixes.append((new, orig))
                self.pairs.append((self._cur_crop, new))
        # skip: record nothing
        self.i += 1
        self._show()

    def _finish(self):
        for crop, text in self.pairs:
            corrections.save_pair(crop, text)
        dxf = os.path.join(os.path.dirname(self.json_path), self.meta["dxf"])
        applied = 0
        if os.path.exists(dxf):
            fixes = [(0, t, o) for t, o in self.fixes]
            try:
                applied = corrections.apply_corrections(dxf, fixes)
            except Exception as exc:
                messagebox.showwarning("Review", f"Couldn't update DXF:\n{exc}")
        total = corrections.dataset_size()
        messagebox.showinfo(
            "Review complete",
            f"Updated {applied} labels in the drawing.\n"
            f"Saved {len(self.pairs)} training examples "
            f"({total} total collected).")
        self.destroy()


def _standalone(path):
    ctk.set_appearance_mode("dark")
    root = ctk.CTk()
    root.withdraw()
    app = ReviewApp(root, path)
    app.protocol("WM_DELETE_WINDOW", root.quit)
    root.mainloop()


if __name__ == "__main__":
    p = sys.argv[1] if len(sys.argv) > 1 else filedialog.askopenfilename(
        filetypes=[("Review sidecar", "*.review.json")])
    if p:
        _standalone(p)
