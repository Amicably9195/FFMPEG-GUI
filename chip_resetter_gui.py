#!/usr/bin/env python3
"""GUI front-end for the Epson waste-ink / chip counter tool (AdjProg style).

Mirrors the classic EPSON Adjustment Program layout: a model header, the
Sequential / Particular adjustment modes, and a Particular-mode screen with the
adjustment-item list on the left and a working panel on the right. The only
items wired to real hardware are the ones this tool can safely perform over
SNMP: Waste-ink pad counter (check / reset) and Printer information check.
"""

import threading
import tkinter as tk
from tkinter import messagebox

import customtkinter as ctk

from chip_resetter import EpsonPrinter, PrinterError, PRINTER_CONFIG

ctk.set_appearance_mode("light")
ctk.set_default_color_theme("blue")

# AdjProg-ish palette: pale green window, classic bordered controls.
BG      = "#DCE9DE"
PANEL   = "#FFFFFF"
FIELD   = "#F4F8F4"
BORDER  = "#9FB3A2"
INK      = "#12203A"      # the AdjProg blue title
TEXT    = "#1B1B1B"
MUTED   = "#5A6B5C"
BTN     = "#ECECE4"
BTN_HOV = "#DADAD0"
GREEN   = "#2E7D32"
RED     = "#C62828"
AMBER   = "#B26A00"

# The adjustment items shown in the reference screenshots. Only ``live`` items
# actually talk to the printer; the rest are shown for parity but disabled.
ADJUSTMENT_ITEMS = [
    ("---- Adjustment ----", None),
    ("EEPROM data copy", False),
    ("Initial setting", False),
    ("Head ID input", False),
    ("Bi-D adjustment", False),
    ("PW / First dot position adjustment", False),
    ("---- Maintenance ----", None),
    ("Head cleaning", False),
    ("Ink charge", False),
    ("Waste ink pad counter", True),
    ("Shipping setting", False),
    ("---- Appendix ----", None),
    ("Final check pattern print", False),
    ("Printer information check", True),
    ("Paper feed test", False),
]


def _mk_button(parent, text, cmd, width=190, color=BTN, hover=BTN_HOV,
               text_color=TEXT, **kw):
    return ctk.CTkButton(parent, text=text, command=cmd, width=width,
                         fg_color=color, hover_color=hover, text_color=text_color,
                         border_width=1, border_color=BORDER, corner_radius=3,
                         font=ctk.CTkFont(size=12), **kw)


class ChipResetterApp(ctk.CTk):
    def __init__(self):
        super().__init__()
        self.title("EPSON Adjustment Program")
        self.geometry("760x560")
        self.configure(fg_color=BG)
        self.resizable(False, False)

        self.model_var = ctk.StringVar(value="WF-7840")
        self.host_var = ctk.StringVar(value="192.168.1.100")
        self.community_var = ctk.StringVar(value="public")
        self.port_var = ctk.StringVar(value="161")
        self._custom_read_key = None
        self._custom_write_key = None
        self._busy = False

        self._build_header()
        self._build_body()
        self._select_item(9)   # default to "Waste ink pad counter"
        self.log("Ready. Set the printer IP, then use Particular adjustment mode.")
        self._refresh_verification_banner()

    # ── header ────────────────────────────────────────────────────────────────
    def _build_header(self):
        head = ctk.CTkFrame(self, fg_color=PANEL, border_width=1,
                            border_color=BORDER, corner_radius=4)
        head.pack(fill="x", padx=12, pady=(12, 6))

        ctk.CTkLabel(head, text="EPSON Adjustment Program",
                     font=ctk.CTkFont(size=20, weight="bold"),
                     text_color=INK).grid(row=0, column=0, columnspan=4,
                                          sticky="w", padx=14, pady=(10, 6))

        grid = [("Model:", self.model_var), ("Dest:", None),
                ("Port:", self.port_var), ("Community:", self.community_var)]
        ctk.CTkLabel(head, text="Model:", text_color=MUTED,
                     font=ctk.CTkFont(size=12)).grid(row=1, column=0, sticky="w",
                                                     padx=(14, 4), pady=3)
        ctk.CTkOptionMenu(head, variable=self.model_var,
                          values=list(PRINTER_CONFIG.keys()),
                          command=lambda _: self._refresh_verification_banner(),
                          width=140, fg_color=FIELD, text_color=TEXT,
                          button_color=BTN, button_hover_color=BTN_HOV,
                          dropdown_fg_color=PANEL, dropdown_text_color=TEXT
                          ).grid(row=1, column=1, sticky="w", pady=3)

        ctk.CTkLabel(head, text="IP address:", text_color=MUTED,
                     font=ctk.CTkFont(size=12)).grid(row=1, column=2, sticky="e",
                                                     padx=(16, 4), pady=3)
        ctk.CTkEntry(head, textvariable=self.host_var, width=150, fg_color=FIELD,
                     text_color=TEXT, border_color=BORDER
                     ).grid(row=1, column=3, sticky="w", padx=(0, 14), pady=3)

        ctk.CTkLabel(head, text="Language: English   |   Port:",
                     text_color=MUTED, font=ctk.CTkFont(size=12)
                     ).grid(row=2, column=0, columnspan=2, sticky="w",
                            padx=(14, 4), pady=(0, 8))
        ctk.CTkEntry(head, textvariable=self.port_var, width=60, fg_color=FIELD,
                     text_color=TEXT, border_color=BORDER
                     ).grid(row=2, column=2, sticky="e", padx=(16, 4), pady=(0, 8))
        _mk_button(head, "Keys…", self._edit_keys, width=90
                   ).grid(row=2, column=3, sticky="w", padx=(0, 14), pady=(0, 8))

        self.banner = ctk.CTkLabel(self, text="", font=ctk.CTkFont(size=12),
                                   text_color=AMBER, anchor="w")
        self.banner.pack(fill="x", padx=16)

    # ── body: item list (left) + panel (right) + log ──────────────────────────
    def _build_body(self):
        body = ctk.CTkFrame(self, fg_color=BG)
        body.pack(fill="both", expand=True, padx=12, pady=6)

        left = ctk.CTkFrame(body, fg_color=PANEL, border_width=1,
                            border_color=BORDER, corner_radius=4, width=300)
        left.pack(side="left", fill="y")
        left.pack_propagate(False)
        ctk.CTkLabel(left, text="Particular adjustment mode",
                     font=ctk.CTkFont(size=12, weight="bold"), text_color=INK
                     ).pack(anchor="w", padx=10, pady=(8, 4))

        self.listbox = tk.Listbox(left, activestyle="none", highlightthickness=0,
                                  bd=0, font=("Segoe UI", 11), width=34,
                                  selectbackground="#3A6EA5",
                                  selectforeground="#FFFFFF", fg=TEXT, bg=PANEL)
        self.listbox.pack(fill="both", expand=True, padx=10, pady=(0, 10))
        for label, live in ADJUSTMENT_ITEMS:
            self.listbox.insert("end", label)
            idx = self.listbox.size() - 1
            if live is None:
                self.listbox.itemconfig(idx, fg=MUTED)          # section header
            elif not live:
                self.listbox.itemconfig(idx, fg="#9AA59B")       # not implemented
        self.listbox.bind("<<ListboxSelect>>",
                          lambda e: self._on_select(self.listbox.curselection()))

        self.panel = ctk.CTkFrame(body, fg_color=PANEL, border_width=1,
                                  border_color=BORDER, corner_radius=4)
        self.panel.pack(side="left", fill="both", expand=True, padx=(10, 0))

        # bottom: log + Quit
        bottom = ctk.CTkFrame(self, fg_color=BG)
        bottom.pack(fill="x", padx=12, pady=(0, 10))
        self.logbox = tk.Text(bottom, height=6, bd=1, relief="solid", wrap="word",
                              font=("Consolas", 10), bg="#101810", fg="#B7F0B7")
        self.logbox.pack(side="left", fill="both", expand=True)
        self.logbox.configure(state="disabled")
        _mk_button(bottom, "Quit", self.destroy, width=90, color="#E6D6D6",
                   hover="#D8C4C4").pack(side="right", padx=(8, 0), anchor="s")

    # ── panel content ─────────────────────────────────────────────────────────
    def _clear_panel(self):
        for w in self.panel.winfo_children():
            w.destroy()

    def _on_select(self, sel):
        if sel:
            self._select_item(sel[0])

    def _select_item(self, idx):
        label = ADJUSTMENT_ITEMS[idx][0]
        live = ADJUSTMENT_ITEMS[idx][1]
        self.listbox.selection_clear(0, "end")
        self.listbox.selection_set(idx)
        self._clear_panel()
        if label == "Waste ink pad counter":
            self._panel_waste()
        elif label == "Printer information check":
            self._panel_info()
        else:
            ctk.CTkLabel(self.panel, text=label.strip("- ").strip() or "—",
                         font=ctk.CTkFont(size=15, weight="bold"), text_color=INK
                         ).pack(anchor="w", padx=16, pady=(18, 6))
            msg = ("Section header." if live is None else
                   "This service item is not available in this tool.\n"
                   "Only the waste-ink pad counter and printer information "
                   "check talk to the printer.")
            ctk.CTkLabel(self.panel, text=msg, text_color=MUTED, justify="left",
                         font=ctk.CTkFont(size=12)).pack(anchor="w", padx=16)

    def _panel_info(self):
        ctk.CTkLabel(self.panel, text="Printer information check",
                     font=ctk.CTkFont(size=15, weight="bold"), text_color=INK
                     ).pack(anchor="w", padx=16, pady=(16, 4))
        ctk.CTkLabel(self.panel,
                     text="Reads the printer identity over SNMP.\n"
                          "Works without model keys — use it to confirm the IP.",
                     text_color=MUTED, justify="left",
                     font=ctk.CTkFont(size=12)).pack(anchor="w", padx=16)
        _mk_button(self.panel, "Check", lambda: self._run(self._do_identify)
                   ).pack(anchor="w", padx=16, pady=14)

    def _panel_waste(self):
        ctk.CTkLabel(self.panel, text="Waste ink pad counter",
                     font=ctk.CTkFont(size=15, weight="bold"), text_color=INK
                     ).pack(anchor="w", padx=16, pady=(16, 4))
        ctk.CTkLabel(self.panel,
                     text="Check reads the current pad usage. Initialization "
                          "resets it to 0 —\nonly do this after replacing the "
                          "waste pad / maintenance box.",
                     text_color=MUTED, justify="left",
                     font=ctk.CTkFont(size=12)).pack(anchor="w", padx=16)

        self.counter_box = tk.Text(self.panel, height=6, bd=1, relief="solid",
                                   wrap="word", font=("Consolas", 11),
                                   bg=FIELD, fg=TEXT)
        self.counter_box.pack(fill="x", padx=16, pady=12)
        self.counter_box.insert("1.0", "Counters not read yet.")
        self.counter_box.configure(state="disabled")

        row = ctk.CTkFrame(self.panel, fg_color=PANEL)
        row.pack(anchor="w", padx=16, pady=(0, 8))
        _mk_button(row, "Check", lambda: self._run(self._do_check_waste),
                   width=150).pack(side="left")
        _mk_button(row, "Initialization (reset)",
                   lambda: self._run(self._do_reset_waste), width=200,
                   color="#F0D9D9", hover="#E6C6C6", text_color=RED
                   ).pack(side="left", padx=10)

    # ── verification banner ───────────────────────────────────────────────────
    def _refresh_verification_banner(self):
        model = self.model_var.get()
        cfg = PRINTER_CONFIG.get(model, {})
        has_keys = bool(cfg.get("read_key")) or self._custom_read_key
        if cfg.get("verified") is True:
            self.banner.configure(
                text=f"✔ {model}: verified profile — counter read/reset enabled.",
                text_color=GREEN)
        elif has_keys:
            self.banner.configure(
                text=f"● {model}: using custom keys you supplied (at your own risk).",
                text_color=AMBER)
        else:
            self.banner.configure(
                text=(f"⚠ {model}: no public key material. Printer info works; "
                      "counter read/reset needs verified keys via 'Keys…'."),
                text_color=AMBER)

    # ── keys dialog ───────────────────────────────────────────────────────────
    def _edit_keys(self):
        dlg = ctk.CTkToplevel(self)
        dlg.title("Model keys")
        dlg.geometry("440x300")
        dlg.configure(fg_color=BG)
        dlg.transient(self)
        ctk.CTkLabel(dlg, text=f"Keys for {self.model_var.get()}",
                     font=ctk.CTkFont(size=14, weight="bold"), text_color=INK
                     ).pack(anchor="w", padx=16, pady=(14, 4))
        ctk.CTkLabel(dlg, justify="left", text_color=MUTED,
                     font=ctk.CTkFont(size=11),
                     text="Supply these ONLY from a source you trust. Wrong values\n"
                          "can render the printer inoperable. Read key = two numbers\n"
                          "(e.g. 101,0). Write key = the password text (e.g. Sasanqua)."
                     ).pack(anchor="w", padx=16)
        rk = ctk.StringVar(value=",".join(map(str, self._custom_read_key))
                           if self._custom_read_key else "")
        wk = ctk.StringVar(value=(self._custom_write_key or b"").decode("latin-1")
                           if self._custom_write_key else "")
        ctk.CTkLabel(dlg, text="Read key (n,n):", text_color=TEXT).pack(
            anchor="w", padx=16, pady=(12, 0))
        ctk.CTkEntry(dlg, textvariable=rk, width=200, fg_color=FIELD,
                     text_color=TEXT).pack(anchor="w", padx=16)
        ctk.CTkLabel(dlg, text="Write key (text):", text_color=TEXT).pack(
            anchor="w", padx=16, pady=(8, 0))
        ctk.CTkEntry(dlg, textvariable=wk, width=200, fg_color=FIELD,
                     text_color=TEXT).pack(anchor="w", padx=16)

        def save():
            try:
                rkey = [int(x) for x in rk.get().replace(" ", "").split(",")
                        if x != ""] if rk.get().strip() else None
                if rkey is not None and len(rkey) != 2:
                    raise ValueError("Read key needs exactly two numbers.")
                self._custom_read_key = rkey
                self._custom_write_key = wk.get().encode("latin-1") or None \
                    if wk.get().strip() else None
                self._refresh_verification_banner()
                self.log("Custom keys stored for this session.")
                dlg.destroy()
            except ValueError as e:
                messagebox.showerror("Invalid key", str(e), parent=dlg)

        _mk_button(dlg, "Save", save, width=100).pack(anchor="e", padx=16, pady=16)

    # ── worker plumbing ───────────────────────────────────────────────────────
    def _printer(self):
        return EpsonPrinter(self.host_var.get().strip(), self.model_var.get(),
                            community=self.community_var.get().strip() or "public",
                            port=int(self.port_var.get() or 161),
                            read_key=self._custom_read_key,
                            write_key=self._custom_write_key)

    def _run(self, fn):
        if self._busy:
            return
        self._busy = True
        threading.Thread(target=self._wrap, args=(fn,), daemon=True).start()

    def _wrap(self, fn):
        try:
            fn()
        except (PrinterError, OSError, ValueError) as e:
            self.after(0, self.log, f"ERROR: {e}")
        finally:
            self._busy = False

    def _do_identify(self):
        self.log(f"Querying {self.host_var.get()} …")
        ident = self._printer().identify()
        self.log(f"Printer: {ident}")

    def _do_check_waste(self):
        self.log("Reading waste ink pad counters …")
        p = self._printer()
        counters = p.read_waste_counters()
        lines = []
        for label, (raw, pct) in counters.items():
            lines.append(f"{label}: {pct}% (raw {raw})")
        try:
            serial = p.read_serial()
            if serial:
                lines.append(f"Serial: {serial}")
        except PrinterError:
            pass
        self.after(0, self._show_counters, "\n".join(lines))
        for ln in lines:
            self.log(ln)

    def _do_reset_waste(self):
        if not messagebox.askyesno(
                "Reset waste counter",
                "Reset the waste-ink pad counter to 0?\n\n"
                "Only do this after physically replacing the waste pad or "
                "maintenance box. The printer must be ON and idle.",
                icon="warning"):
            return
        self.log("Resetting waste ink pad counters …")
        n = self._printer().reset_waste_counters()
        self.log(f"Reset complete: {n} cells written. "
                 "Power-cycle the printer to finish.")

    # ── ui helpers ────────────────────────────────────────────────────────────
    def _show_counters(self, text):
        self.counter_box.configure(state="normal")
        self.counter_box.delete("1.0", "end")
        self.counter_box.insert("1.0", text or "No counters returned.")
        self.counter_box.configure(state="disabled")

    def log(self, msg):
        self.logbox.configure(state="normal")
        self.logbox.insert("end", msg + "\n")
        self.logbox.see("end")
        self.logbox.configure(state="disabled")


def main():
    ChipResetterApp().mainloop()


if __name__ == "__main__":
    main()
