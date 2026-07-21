#!/usr/bin/env python3
"""Drawing2CAD - Convert photos/scans of drawings into DXF for AutoCAD/MicroStation"""

import customtkinter as ctk
import tkinter as tk
from tkinter import filedialog, messagebox
import os, sys, threading, traceback

import scan2cad

# ── Drag-and-drop: subclass CTk with TkinterDnD BEFORE any window is created ──
try:
    from tkinterdnd2 import TkinterDnD, DND_FILES
    class _CTkDnD(ctk.CTk, TkinterDnD.DnDWrapper):
        def __init__(self, *args, **kwargs):
            super().__init__(*args, **kwargs)
            self.TkdndVersion = TkinterDnD._require(self)
    _BASE = _CTkDnD
    _DND_AVAILABLE = True
except Exception:
    _BASE = ctk.CTk
    _DND_AVAILABLE = False

ctk.set_appearance_mode("dark")
ctk.set_default_color_theme("dark-blue")

ACCENT  = "#1A7FE8"; ACCENT2 = "#3D9BFF"
BG_DARK = "#0D0D0D"; BG_MID  = "#161616"
BG_CARD = "#1E1E1E"; BG_INPUT= "#252525"
BORDER  = "#2E2E2E"; TEXT    = "#F0EDE8"
MUTED   = "#888480"; GREEN   = "#4CAF50"
YELLOW  = "#FFC107"; RED     = "#E85454"

IMAGE_EXTS = (".jpg", ".jpeg", ".png", ".tif", ".tiff", ".bmp", ".webp",
              ".pdf", ".dwg", ".dxf", ".dgn")


class Drawing2CADApp(_BASE):
    def __init__(self):
        super().__init__()
        self.title("Drawing2CAD — scan / photo to DXF")
        self.geometry("860x680")
        self.minsize(760, 600)
        self.configure(fg_color=BG_DARK)
        self.files = []
        self.busy = False
        self._build_ui()
        self._check_tesseract()

    # ── UI ─────────────────────────────────────────────────────────────────
    def _build_ui(self):
        head = ctk.CTkFrame(self, fg_color=BG_DARK)
        head.pack(fill="x", padx=16, pady=(14, 4))
        ctk.CTkLabel(head, text="Drawing2CAD",
                     font=("Segoe UI", 24, "bold"),
                     text_color=TEXT).pack(side="left")
        ctk.CTkLabel(head,
                     text="photo / scan  →  DXF  (AutoCAD & MicroStation)",
                     font=("Segoe UI", 13), text_color=MUTED
                     ).pack(side="left", padx=12, pady=(6, 0))

        # file area
        card = ctk.CTkFrame(self, fg_color=BG_CARD, corner_radius=10,
                            border_width=1, border_color=BORDER)
        card.pack(fill="x", padx=16, pady=6)
        row = ctk.CTkFrame(card, fg_color=BG_CARD)
        row.pack(fill="x", padx=10, pady=(10, 4))
        ctk.CTkButton(row, text="+  Add images", command=self._pick_files,
                      fg_color=ACCENT, hover_color=ACCENT2, width=130
                      ).pack(side="left")
        ctk.CTkButton(row, text="Clear", command=self._clear_files,
                      fg_color=BG_INPUT, hover_color=BORDER, width=70
                      ).pack(side="left", padx=8)
        hint = "or drag & drop image files here" if _DND_AVAILABLE else ""
        ctk.CTkLabel(row, text=hint, text_color=MUTED,
                     font=("Segoe UI", 12)).pack(side="left", padx=10)

        self.file_box = tk.Listbox(card, height=5, bg=BG_INPUT, fg=TEXT,
                                   selectbackground=ACCENT, relief="flat",
                                   highlightthickness=0,
                                   font=("Consolas", 10))
        self.file_box.pack(fill="x", padx=10, pady=(4, 10))
        if _DND_AVAILABLE:
            for widget in (self, self.file_box):
                widget.drop_target_register(DND_FILES)
                widget.dnd_bind("<<Drop>>", self._on_drop)

        # options
        opts = ctk.CTkFrame(self, fg_color=BG_CARD, corner_radius=10,
                            border_width=1, border_color=BORDER)
        opts.pack(fill="x", padx=16, pady=6)
        orow1 = ctk.CTkFrame(opts, fg_color=BG_CARD)
        orow1.pack(fill="x", padx=10, pady=(10, 2))
        self.v_crop   = tk.BooleanVar(value=True)
        self.v_deskew = tk.BooleanVar(value=True)
        self.v_ocr    = tk.BooleanVar(value=True)
        self.v_curves = tk.BooleanVar(value=True)
        self.v_ortho  = tk.BooleanVar(value=True)
        self.v_autoscale = tk.BooleanVar(value=True)
        self.v_review = tk.BooleanVar(value=True)
        self.v_clean = tk.BooleanVar(value=True)
        for label, var in [("Auto-crop page", self.v_crop),
                           ("Straighten (deskew)", self.v_deskew),
                           ("OCR text", self.v_ocr),
                           ("Trace curves", self.v_curves),
                           ("Snap lines to axis", self.v_ortho),
                           ("Auto-scale to feet", self.v_autoscale),
                           ("Flag uncertain text", self.v_review),
                           ("Deep-clean dirty scans", self.v_clean)]:
            ctk.CTkCheckBox(orow1, text=label, variable=var,
                            fg_color=ACCENT, hover_color=ACCENT2,
                            font=("Segoe UI", 12)).pack(side="left", padx=8)

        orow2 = ctk.CTkFrame(opts, fg_color=BG_CARD)
        orow2.pack(fill="x", padx=10, pady=(4, 10))

        def entry(parent, label, default, width=64):
            ctk.CTkLabel(parent, text=label, text_color=MUTED,
                         font=("Segoe UI", 12)).pack(side="left", padx=(10, 4))
            e = ctk.CTkEntry(parent, width=width, fg_color=BG_INPUT,
                             border_color=BORDER)
            e.insert(0, default)
            e.pack(side="left")
            return e

        self.e_scale = entry(orow2, "Units per pixel", "1.0")
        self.e_minline = entry(orow2, "Min line (px)", "6")
        self.e_speck = entry(orow2, "Remove specks < (px²)", "8")

        orow3 = ctk.CTkFrame(opts, fg_color=BG_CARD)
        orow3.pack(fill="x", padx=10, pady=(0, 10))
        self.v_smart = tk.BooleanVar(value=True)
        ctk.CTkCheckBox(orow3,
                        text="Smart text reading (free, runs on this PC)",
                        variable=self.v_smart, fg_color=ACCENT,
                        hover_color=ACCENT2,
                        font=("Segoe UI", 12)).pack(side="left", padx=8)
        ctk.CTkLabel(orow3, text="Output:", text_color=MUTED,
                     font=("Segoe UI", 12)).pack(side="left", padx=(18, 4))
        self.v_fmt = tk.StringVar(value="DXF")
        ctk.CTkOptionMenu(orow3, values=["DXF", "DWG", "DGN"],
                          variable=self.v_fmt, width=80, fg_color=BG_INPUT,
                          button_color=ACCENT, button_hover_color=ACCENT2
                          ).pack(side="left")
        ctk.CTkLabel(orow3, text="(DWG/DGN need the free ODA converter)",
                     text_color=MUTED, font=("Segoe UI", 11)
                     ).pack(side="left", padx=8)

        # convert
        self.btn = ctk.CTkButton(self, text="Convert to DXF",
                                 command=self._convert,
                                 fg_color=ACCENT, hover_color=ACCENT2,
                                 font=("Segoe UI", 15, "bold"), height=42)
        self.btn.pack(fill="x", padx=16, pady=8)

        # log
        self.log_box = ctk.CTkTextbox(self, fg_color=BG_MID, text_color=TEXT,
                                      font=("Consolas", 11), wrap="word")
        self.log_box.pack(fill="both", expand=True, padx=16, pady=(0, 8))
        self.log_box.configure(state="disabled")

        self.status = ctk.CTkLabel(self, text="Ready", text_color=MUTED,
                                   font=("Segoe UI", 12), anchor="w")
        self.status.pack(fill="x", padx=18, pady=(0, 10))

    # ── helpers ────────────────────────────────────────────────────────────
    def _log(self, msg):
        def put():
            self.log_box.configure(state="normal")
            self.log_box.insert("end", msg + "\n")
            self.log_box.see("end")
            self.log_box.configure(state="disabled")
        self.after(0, put)

    def _set_status(self, msg, color=MUTED):
        self.after(0, lambda: self.status.configure(text=msg, text_color=color))

    def _check_tesseract(self):
        if scan2cad.find_tesseract() is None:
            self._log("NOTE: Tesseract OCR was not found, so text will be "
                      "skipped.\nInstall it from "
                      "https://github.com/UB-Mannheim/tesseract/wiki "
                      "(Windows) and restart,\nor un-check 'OCR text'. "
                      "Lines still convert fine without it.\n")

    def _pick_files(self):
        paths = filedialog.askopenfilenames(
            title="Choose drawing photos / scans / PDFs",
            filetypes=[("Drawings", " ".join("*" + e for e in IMAGE_EXTS)),
                       ("All files", "*.*")])
        self._add_files(paths)

    def _on_drop(self, event):
        self._add_files(self.tk.splitlist(event.data))

    def _add_files(self, paths):
        for p in paths:
            if os.path.splitext(p)[1].lower() in IMAGE_EXTS and p not in self.files:
                self.files.append(p)
                self.file_box.insert("end", p)
        self._set_status(f"{len(self.files)} file(s) queued")

    def _clear_files(self):
        self.files = []
        self.file_box.delete(0, "end")
        self._set_status("Ready")

    def _float(self, widget, default):
        try:
            return float(widget.get())
        except ValueError:
            return default

    # ── conversion ─────────────────────────────────────────────────────────
    def _convert(self):
        if self.busy:
            return
        if not self.files:
            messagebox.showinfo("Drawing2CAD", "Add at least one image first.")
            return
        self.busy = True
        self.btn.configure(state="disabled", text="Converting ...")
        threading.Thread(target=self._worker, daemon=True).start()

    def _worker(self):
        ok, failed = 0, 0
        for path in list(self.files):
            self._log(f"\n=== {os.path.basename(path)} ===")
            self._set_status(f"Converting {os.path.basename(path)} ...", YELLOW)
            try:
                ext = "." + self.v_fmt.get().lower()
                out = os.path.splitext(path)[0] + "_cad" + ext \
                    if os.path.splitext(path)[1].lower() in (
                        ".dwg", ".dxf", ".dgn") \
                    else os.path.splitext(path)[0] + ext
                stats = scan2cad.convert(
                    path, out,
                    scale=self._float(self.e_scale, 1.0),
                    do_page_crop=self.v_crop.get(),
                    do_deskew=self.v_deskew.get(),
                    do_ocr=self.v_ocr.get(),
                    do_curves=self.v_curves.get(),
                    ortho_snap=self.v_ortho.get(),
                    auto_scale=self.v_autoscale.get(),
                    flag_review=self.v_review.get(),
                    deep_clean=self.v_clean.get(),
                    smart_read=self.v_smart.get(),
                    min_line_px=self._float(self.e_minline, 6.0),
                    speck_px=int(self._float(self.e_speck, 8)),
                    log=self._log)
                ok += 1
                self._log(f"DONE -> {stats['output']}")
            except Exception:
                failed += 1
                self._log("ERROR:\n" + traceback.format_exc())
        color = GREEN if failed == 0 else RED
        self._set_status(f"Finished: {ok} converted, {failed} failed. "
                         f"DXF saved next to each image.", color)
        self.after(0, lambda: self.btn.configure(state="normal",
                                                 text="Convert to DXF"))
        self.busy = False


if __name__ == "__main__":
    app = Drawing2CADApp()
    app.mainloop()
