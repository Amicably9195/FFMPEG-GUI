#!/usr/bin/env python3
"""FFmpeg GUI v2 - Full-featured standalone media converter"""

import customtkinter as ctk
import tkinter as tk
from tkinter import filedialog, messagebox
import subprocess, threading, json, os, sys, re, shutil, tempfile
from pathlib import Path

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

ACCENT  = "#E8441A"; ACCENT2 = "#FF6B3D"
BG_DARK = "#0D0D0D"; BG_MID  = "#161616"
BG_CARD = "#1E1E1E"; BG_INPUT= "#252525"
BORDER  = "#2E2E2E"; TEXT    = "#F0EDE8"
MUTED   = "#888480"; GREEN   = "#4CAF50"
YELLOW  = "#FFC107"

# ── FFmpeg binary resolution ───────────────────────────────────────────────────
_ffmpeg_dir = None

def _get_ffmpeg_dir():
    global _ffmpeg_dir
    if _ffmpeg_dir:
        return _ffmpeg_dir

    # 1 — PyInstaller bundle: extract to temp dir to avoid path/permission issues
    if hasattr(sys, "_MEIPASS"):
        mei = sys._MEIPASS
        ff  = os.path.join(mei, "ffmpeg.exe")
        fp  = os.path.join(mei, "ffprobe.exe")
        if os.path.isfile(ff) and os.path.isfile(fp):
            tmp = os.path.join(tempfile.gettempdir(), "ffmpeg_gui_bins")
            os.makedirs(tmp, exist_ok=True)
            for src, name in [(ff,"ffmpeg.exe"), (fp,"ffprobe.exe")]:
                dst = os.path.join(tmp, name)
                if not os.path.isfile(dst):
                    shutil.copy2(src, dst)
            _ffmpeg_dir = tmp
            return _ffmpeg_dir

    # 2 — Same folder as exe/script
    here = os.path.dirname(sys.executable if getattr(sys,"frozen",False)
                           else os.path.abspath(__file__))
    if os.path.isfile(os.path.join(here, "ffmpeg.exe")):
        _ffmpeg_dir = here
        return _ffmpeg_dir

    return None  # fall back to PATH


def _bin(name):
    d = _get_ffmpeg_dir()
    if d:
        full = os.path.join(d, name)
        # Use Windows short path to avoid spaces
        if sys.platform == "win32":
            try:
                import ctypes
                buf = ctypes.create_unicode_buffer(512)
                ctypes.windll.kernel32.GetShortPathNameW(full, buf, 512)
                short = buf.value
                if short and os.path.isfile(short):
                    return short
            except:
                pass
        return full
    return name


def _NO_WINDOW():
    return subprocess.CREATE_NO_WINDOW if sys.platform == "win32" else 0


def ffmpeg_available():
    try:
        r = subprocess.run([_bin("ffmpeg"), "-version"],
                           capture_output=True, timeout=10,
                           creationflags=_NO_WINDOW())
        return r.returncode == 0
    except:
        return False


def probe_file(path):
    try:
        r = subprocess.run(
            [_bin("ffprobe"), "-v", "quiet", "-print_format", "json",
             "-show_streams", "-show_format", path],
            capture_output=True, text=True, timeout=30,
            encoding="utf-8", errors="replace",
            creationflags=_NO_WINDOW())
        if r.returncode == 0:
            return json.loads(r.stdout)
    except:
        pass
    return None


def fmt_dur(s):
    try:
        s=float(s); h=int(s//3600); m=int((s%3600)//60); sec=int(s%60)
        return f"{h}:{m:02d}:{sec:02d}" if h else f"{m}:{sec:02d}"
    except:
        return "?"


def fmt_sz(path):
    try:
        sz = os.path.getsize(path)
        for u in ["B","KB","MB","GB"]:
            if sz < 1024: return f"{sz:.1f} {u}"
            sz /= 1024
        return f"{sz:.1f} TB"
    except:
        return "?"


# ── Widget helpers ─────────────────────────────────────────────────────────────
def mk_om(parent, var, values, width=110, cmd=None):
    kw = dict(fg_color=BG_INPUT, button_color=ACCENT,
               button_hover_color=ACCENT2, dropdown_fg_color=BG_CARD)
    if cmd: kw["command"] = cmd
    return ctk.CTkOptionMenu(parent, variable=var, values=values, width=width, **kw)


def mk_lbl(parent, text, row, col, padx=(0,8), pady=(0,3), colspan=1):
    ctk.CTkLabel(parent, text=text, font=ctk.CTkFont(size=11), text_color=MUTED
                  ).grid(row=row, column=col, columnspan=colspan,
                          sticky="w", padx=padx, pady=pady)


def mk_entry(parent, var=None, ph="", width=None, **kw):
    kwargs = dict(fg_color=BG_INPUT, border_color=BORDER, text_color=TEXT)
    kwargs.update(kw)
    if var:    kwargs["textvariable"] = var
    if ph:     kwargs["placeholder_text"] = ph
    if width:  kwargs["width"] = width
    return ctk.CTkEntry(parent, **kwargs)


# ── Per-stream track row ───────────────────────────────────────────────────────
class TrackRow(ctk.CTkFrame):
    def __init__(self, master, stream_type, label, **kw):
        super().__init__(master, fg_color=BG_CARD, corner_radius=8,
                         border_width=1, border_color=BORDER, **kw)
        self.stream_type = stream_type
        self.stream_label = label
        badge_bg = {"video":"#1A3A5C","audio":"#1A3A2A","subtitle":"#3A2A1A"}
        badge_tx = {"video":"V","audio":"A","subtitle":"S"}
        ctk.CTkLabel(self, text=badge_tx.get(stream_type,"?"),
                      width=28, height=28,
                      fg_color=badge_bg.get(stream_type, BG_CARD),
                      text_color=TEXT, font=ctk.CTkFont("Courier",11,"bold"),
                      corner_radius=6).grid(row=0, column=0, padx=(10,8), pady=10)
        ctk.CTkLabel(self, text=label, font=ctk.CTkFont(size=11),
                      text_color=TEXT, anchor="w",
                      wraplength=200).grid(row=0, column=1, sticky="ew", padx=(0,12))
        if stream_type == "video":      self._build_video()
        elif stream_type == "audio":    self._build_audio()
        elif stream_type == "subtitle": self._build_subtitle()

    def _build_video(self):
        ctk.CTkLabel(self,text="Codec",font=ctk.CTkFont(size=10),text_color=MUTED).grid(row=0,column=2,padx=(0,4))
        self.vcodec_var = ctk.StringVar(value="copy")
        mk_om(self, self.vcodec_var,
              ["copy","h264","h265","vp9","av1","mpeg4"], width=100
              ).grid(row=0, column=3, sticky="ew", padx=(0,10))
        ctk.CTkLabel(self,text="Res",font=ctk.CTkFont(size=10),text_color=MUTED).grid(row=0,column=4,padx=(0,4))
        self.res_var = ctk.StringVar(value="Original")
        mk_om(self, self.res_var,
              ["Original","3840x2160","1920x1080","1280x720","854x480","640x360"], width=120
              ).grid(row=0, column=5, sticky="ew", padx=(0,10))
        ctk.CTkLabel(self,text="CRF",font=ctk.CTkFont(size=10),text_color=MUTED).grid(row=0,column=6,padx=(0,4))
        self.crf_var = ctk.StringVar(value="23")
        mk_entry(self, self.crf_var, width=50).grid(row=0, column=7, sticky="ew", padx=(0,12))

    def _build_audio(self):
        ctk.CTkLabel(self,text="Codec",font=ctk.CTkFont(size=10),text_color=MUTED).grid(row=0,column=2,padx=(0,4))
        self.acodec_var = ctk.StringVar(value="copy")
        mk_om(self, self.acodec_var,
              ["copy","aac","mp3","flac","opus","pcm_s16le","vorbis","ac3"], width=100
              ).grid(row=0, column=3, sticky="ew", padx=(0,10))
        ctk.CTkLabel(self,text="Vol%",font=ctk.CTkFont(size=10),text_color=MUTED).grid(row=0,column=4,padx=(0,4))
        self.vol_var = ctk.StringVar(value="100")
        mk_entry(self, self.vol_var, width=55).grid(row=0, column=5, sticky="ew", padx=(0,10))
        ctk.CTkLabel(self,text="Delay(ms)",font=ctk.CTkFont(size=10),text_color=MUTED).grid(row=0,column=6,padx=(0,4))
        self.delay_var = ctk.StringVar(value="0")
        mk_entry(self, self.delay_var, width=60).grid(row=0, column=7, sticky="ew", padx=(0,10))
        ctk.CTkLabel(self,text="Lang",font=ctk.CTkFont(size=10),text_color=MUTED).grid(row=0,column=8,padx=(0,4))
        self.lang_var = ctk.StringVar(value="")
        mk_entry(self, self.lang_var, ph="eng", width=55).grid(row=0, column=9, sticky="ew", padx=(0,12))

    def _build_subtitle(self):
        ctk.CTkLabel(self,text="Lang",font=ctk.CTkFont(size=10),text_color=MUTED).grid(row=0,column=2,padx=(0,4))
        self.lang_var = ctk.StringVar(value="")
        mk_entry(self, self.lang_var, ph="eng", width=55).grid(row=0, column=3, sticky="ew", padx=(0,10))
        ctk.CTkLabel(self,text="Delay(ms)",font=ctk.CTkFont(size=10),text_color=MUTED).grid(row=0,column=4,padx=(0,4))
        self.delay_var = ctk.StringVar(value="0")
        mk_entry(self, self.delay_var, width=60).grid(row=0, column=5, sticky="ew", padx=(0,10))
        self.burn_var = ctk.BooleanVar(value=False)
        ctk.CTkCheckBox(self, text="Burn in", variable=self.burn_var,
                         text_color=TEXT, fg_color=ACCENT, hover_color=ACCENT2, width=80
                         ).grid(row=0, column=6, padx=(0,12))

    def get_stream_index(self):
        m = re.match(r"#(\d+)", self.stream_label)
        return int(m.group(1)) if m else None


# ── Conversion row (one per file) ──────────────────────────────────────────────
class ConversionRow(ctk.CTkFrame):
    ALL_FMTS = ["mp4","mkv","avi","mov","webm","flv","ts","m4v","wmv",
                "mp4 (h265)","mkv (h265)","mp4 (av1)","mkv (av1)",
                "mp3","aac","flac","wav","ogg","m4a","opus","ac3","gif"]
    NAME_TMPLS = ["{name}_converted","{name}_output","{name}_{ext}",
                  "{name}_{date}","converted_{name}","output_{index}"]

    def __init__(self, master, filepath, on_remove, job_index=0, **kw):
        super().__init__(master, fg_color=BG_MID, corner_radius=12,
                         border_width=1, border_color=BORDER, **kw)
        self.filepath   = filepath
        self.on_remove  = on_remove
        self.job_index  = job_index
        self.probe_data = None
        self.track_rows = []
        self.grid_columnconfigure(0, weight=1)
        self._build()

    def _build(self):
        # ── File header ────────────────────────────────────────────────────────
        hdr = ctk.CTkFrame(self, fg_color=BG_CARD, corner_radius=8)
        hdr.grid(row=0, column=0, sticky="ew", padx=12, pady=(12,0))
        hdr.grid_columnconfigure(1, weight=1)
        ext = Path(self.filepath).suffix.upper().lstrip(".")
        ctk.CTkLabel(hdr, text=ext or "?", width=52, height=52, fg_color=ACCENT,
                      text_color=TEXT, font=ctk.CTkFont("Courier",13,"bold"),
                      corner_radius=8).grid(row=0,column=0,rowspan=2,padx=(12,10),pady=12,sticky="ns")
        ctk.CTkLabel(hdr, text=Path(self.filepath).name, anchor="w",
                      font=ctk.CTkFont(size=13,weight="bold"), text_color=TEXT
                      ).grid(row=0,column=1,sticky="ew",padx=(0,8),pady=(12,2))
        self.lbl_meta = ctk.CTkLabel(hdr, text="Probing file…", anchor="w",
                                      font=ctk.CTkFont(size=11), text_color=MUTED)
        self.lbl_meta.grid(row=1,column=1,sticky="ew",padx=(0,8),pady=(0,12))
        ctk.CTkButton(hdr, text="✕", width=28, height=28, fg_color="transparent",
                       hover_color="#3A1A1A", text_color=MUTED,
                       command=lambda: self.on_remove(self)
                       ).grid(row=0,column=2,rowspan=2,padx=(0,10))

        # ── Output settings ────────────────────────────────────────────────────
        of = ctk.CTkFrame(self, fg_color="transparent")
        of.grid(row=1, column=0, sticky="ew", padx=12, pady=(10,0))
        of.grid_columnconfigure((1,3), weight=1)

        mk_lbl(of,"Output Container",0,0)
        self.fmt_var = ctk.StringVar(value="mp4")
        mk_om(of, self.fmt_var, self.ALL_FMTS, width=150
              ).grid(row=1,column=0,sticky="ew",padx=(0,12))

        mk_lbl(of,"Filename Template",0,1)
        tf = ctk.CTkFrame(of, fg_color="transparent")
        tf.grid(row=1,column=1,sticky="ew",padx=(0,12)); tf.grid_columnconfigure(0,weight=1)
        self.tmpl_var = ctk.StringVar(value="{name}_converted")
        mk_entry(tf, self.tmpl_var).grid(row=0,column=0,sticky="ew",padx=(0,4))
        mk_om(tf, self.tmpl_var, self.NAME_TMPLS, width=30).grid(row=0,column=1)

        mk_lbl(of,"Output Folder",0,2)
        ff2 = ctk.CTkFrame(of, fg_color="transparent")
        ff2.grid(row=1,column=2,sticky="ew"); ff2.grid_columnconfigure(0,weight=1)
        self.out_folder_var = ctk.StringVar(value=str(Path(self.filepath).parent))
        mk_entry(ff2, self.out_folder_var).grid(row=0,column=0,sticky="ew",padx=(0,4))
        ctk.CTkButton(ff2,text="…",width=30,height=28,fg_color=BG_CARD,
                       hover_color=BORDER,text_color=TEXT,
                       command=self._browse_folder).grid(row=0,column=1)

        # ── Trim + extra flags ─────────────────────────────────────────────────
        tf2 = ctk.CTkFrame(self, fg_color="transparent")
        tf2.grid(row=2, column=0, sticky="ew", padx=12, pady=(8,0))
        tf2.grid_columnconfigure((0,1,2), weight=1)

        mk_lbl(tf2,"Trim Start",0,0)
        self.trim_start = mk_entry(tf2, ph="HH:MM:SS or seconds")
        self.trim_start.grid(row=1,column=0,sticky="ew",padx=(0,10))

        mk_lbl(tf2,"Trim End",0,1)
        self.trim_end = mk_entry(tf2, ph="HH:MM:SS or seconds (optional)")
        self.trim_end.grid(row=1,column=1,sticky="ew",padx=(0,10))

        mk_lbl(tf2,"Extra ffmpeg Flags",0,2)
        self.extra_flags = mk_entry(tf2, ph="-movflags +faststart  -metadata title=MyTitle")
        self.extra_flags.grid(row=1,column=2,sticky="ew")

        # ── Streams section ────────────────────────────────────────────────────
        ctk.CTkLabel(self, text="STREAMS", font=ctk.CTkFont(size=10,weight="bold"),
                      text_color=ACCENT).grid(row=3,column=0,sticky="w",padx=16,pady=(14,2))

        self.tracks_frame = ctk.CTkFrame(self, fg_color="transparent")
        self.tracks_frame.grid(row=4, column=0, sticky="ew", padx=12, pady=(0,4))
        self.tracks_frame.grid_columnconfigure(0, weight=1)

        # Manual override row
        mf = ctk.CTkFrame(self.tracks_frame, fg_color=BG_CARD, corner_radius=8,
                           border_width=1, border_color=BORDER)
        mf.grid(row=0, column=0, sticky="ew", pady=(0,6))
        mf.grid_columnconfigure((1,3,5,7), weight=1)

        ctk.CTkLabel(mf, text="Manual Track Indices (override auto-detect):",
                      font=ctk.CTkFont(size=11), text_color=MUTED
                      ).grid(row=0,column=0,columnspan=8,sticky="w",padx=12,pady=(8,4))

        fields = [("Video","0","manual_video"),("Audio","1","manual_audio"),
                  ("Subtitle","2","manual_sub")]
        for i,(lbl_text,ph,attr) in enumerate(fields):
            ctk.CTkLabel(mf,text=lbl_text,font=ctk.CTkFont(size=10),text_color=MUTED
                          ).grid(row=1,column=i*2,sticky="w",padx=(12 if i==0 else 6,4))
            var = ctk.StringVar()
            setattr(self, attr+"_var", var)
            mk_entry(mf, var, ph=ph, width=100).grid(row=1,column=i*2+1,sticky="ew",padx=(0,8),pady=(0,10))

        # Ext subtitle
        ctk.CTkLabel(mf,text="External Subtitle File",font=ctk.CTkFont(size=10),text_color=MUTED
                      ).grid(row=1,column=6,sticky="w",padx=(6,4))
        self.manual_ext_sub_var = ctk.StringVar()
        ext_row = ctk.CTkFrame(mf, fg_color="transparent")
        ext_row.grid(row=1,column=7,sticky="ew",padx=(0,12),pady=(0,10))
        ext_row.grid_columnconfigure(0,weight=1)
        mk_entry(ext_row, self.manual_ext_sub_var, ph="path to .srt/.ass"
                  ).grid(row=0,column=0,sticky="ew",padx=(0,4))
        ctk.CTkButton(ext_row,text="…",width=28,height=26,fg_color=BG_MID,
                       hover_color=BORDER,text_color=TEXT,
                       command=self._browse_ext_sub).grid(row=0,column=1)

        self.no_video_var = ctk.BooleanVar(value=False)
        ctk.CTkCheckBox(mf,text="No video (audio-only output)",variable=self.no_video_var,
                         text_color=TEXT,fg_color=ACCENT,hover_color=ACCENT2
                         ).grid(row=2,column=0,columnspan=4,sticky="w",padx=12,pady=(0,10))

        # Auto-detected streams list
        self.track_list_frame = ctk.CTkFrame(self.tracks_frame, fg_color="transparent")
        self.track_list_frame.grid(row=1,column=0,sticky="ew")
        self.track_list_frame.grid_columnconfigure(0,weight=1)
        self.probe_lbl = ctk.CTkLabel(self.track_list_frame, text="⏳ Probing streams…",
                                       font=ctk.CTkFont(size=11), text_color=MUTED)
        self.probe_lbl.grid(row=0,column=0,sticky="w",padx=4,pady=4)

        threading.Thread(target=self._probe_and_build, daemon=True).start()

    def _probe_and_build(self):
        import time; time.sleep(0.05)
        data = probe_file(self.filepath)
        self.probe_data = data
        if data:
            fmt     = data.get("format",{})
            streams = data.get("streams",[])
            v   = sum(1 for s in streams if s["codec_type"]=="video")
            a   = sum(1 for s in streams if s["codec_type"]=="audio")
            sub = sum(1 for s in streams if s["codec_type"]=="subtitle")
            meta = f"{fmt_sz(self.filepath)}  ·  {fmt_dur(fmt.get('duration',0))}  ·  {v}V / {a}A / {sub}S"
            self.after(0, lambda: self.lbl_meta.configure(text=meta, text_color=MUTED))
            self.after(0, lambda: self._build_track_rows(streams))
        else:
            self.after(0, lambda: self.lbl_meta.configure(
                text="⚠ Could not probe — set tracks manually above", text_color=YELLOW))
            self.after(0, lambda: self.probe_lbl.configure(
                text="No stream info available — use manual indices above", text_color=YELLOW))

    def _build_track_rows(self, streams):
        for w in self.track_list_frame.winfo_children():
            w.destroy()
        self.track_rows.clear()
        row_i = 0
        for s in streams:
            stype = s.get("codec_type","")
            if stype not in ("video","audio","subtitle"): continue
            tags  = s.get("tags",{})
            lang  = tags.get("language","")
            title = tags.get("title","")
            codec = s.get("codec_name","?")
            idx   = s.get("index","?")
            label = f"#{idx} {codec}"
            if lang:  label += f" [{lang}]"
            if title: label += f' "{title}"'
            if stype == "audio":
                label += f"  {s.get('channels','?')}ch"
            tr = TrackRow(self.track_list_frame, stype, label)
            tr.grid(row=row_i, column=0, sticky="ew", pady=(0,5))
            self.track_rows.append(tr)
            row_i += 1

    def _browse_folder(self):
        p = filedialog.askdirectory(initialdir=self.out_folder_var.get())
        if p: self.out_folder_var.set(p)

    def _browse_ext_sub(self):
        p = filedialog.askopenfilename(title="Select subtitle file",
            filetypes=[("Subtitle files","*.srt *.ass *.ssa *.vtt *.sub"),("All files","*.*")])
        if p: self.manual_ext_sub_var.set(p)

    def get_output_path(self):
        import datetime
        tmpl   = self.tmpl_var.get().strip() or "{name}_converted"
        src    = Path(self.filepath)
        raw    = self.fmt_var.get()
        ext    = raw.split()[0]   # strip "(h265)" etc.
        name   = (tmpl
                  .replace("{name}", src.stem)
                  .replace("{ext}", ext)
                  .replace("{date}", datetime.date.today().strftime("%Y%m%d"))
                  .replace("{index}", str(self.job_index)))
        folder = self.out_folder_var.get().strip() or str(src.parent)
        return str(Path(folder) / f"{name}.{ext}")

    def _sub_codec_for(self, out_ext):
        """Right subtitle codec for the output container."""
        return "mov_text" if out_ext.lower() in {"mp4","m4v","mov"} else "copy"

    def build_cmd(self):
        raw        = self.fmt_var.get()
        out_ext    = raw.split()[0].lower()
        force_h265 = "h265" in raw
        force_av1  = "av1"  in raw
        sub_codec  = self._sub_codec_for(out_ext)

        cmd = [_bin("ffmpeg"), "-y"]

        ts = self.trim_start.get().strip()
        te = self.trim_end.get().strip()
        if ts: cmd += ["-ss", ts]

        cmd += ["-i", self.filepath]

        ext_sub       = self.manual_ext_sub_var.get().strip()
        ext_sub_valid = bool(ext_sub and os.path.isfile(ext_sub))
        if ext_sub_valid:
            cmd += ["-i", ext_sub]

        if te: cmd += ["-to", te]

        # ── Video ──────────────────────────────────────────────────────────
        if self.no_video_var.get():
            cmd += ["-vn"]
        else:
            mv = self.manual_video_var.get().strip()
            if mv:
                cmd += ["-map", f"0:{mv}", "-c:v", "copy"]
            else:
                vrows = [r for r in self.track_rows if r.stream_type=="video"]
                if vrows:
                    vi  = vrows[0].get_stream_index()
                    vc  = vrows[0].vcodec_var.get()
                    res = vrows[0].res_var.get()
                    crf = vrows[0].crf_var.get().strip()
                    if force_h265: vc = "libx265"
                    if force_av1:  vc = "libaom-av1"
                    if vi is not None: cmd += ["-map", f"0:{vi}"]
                    cmd += ["-c:v", vc]
                    if vc != "copy":
                        if crf: cmd += ["-crf", crf]
                        cmd += ["-preset", "medium"]
                        if res != "Original": cmd += ["-vf", f"scale={res}"]
                else:
                    if force_h265:
                        cmd += ["-c:v","libx265","-crf","28","-preset","medium"]
                    elif force_av1:
                        cmd += ["-c:v","libaom-av1","-crf","30"]
                    else:
                        cmd += ["-c:v","copy"]

        # ── Audio ──────────────────────────────────────────────────────────
        ma = self.manual_audio_var.get().strip()
        if ma:
            cmd += ["-map", f"0:{ma}", "-c:a", "copy"]
        else:
            arows = [r for r in self.track_rows if r.stream_type=="audio"]
            if arows:
                for i, ar in enumerate(arows):
                    ai  = ar.get_stream_index()
                    ac  = ar.acodec_var.get()
                    vol = ar.vol_var.get().strip()
                    dly = ar.delay_var.get().strip()
                    lng = ar.lang_var.get().strip()
                    if ai is not None: cmd += ["-map", f"0:{ai}"]
                    cmd += ["-c:a", ac]
                    if vol and vol != "100":
                        cmd += [f"-filter:a:{i}", f"volume={vol}/100"]
                    if dly and dly != "0":
                        try: cmd += ["-itsoffset", str(float(dly)/1000)]
                        except: pass
                    if lng: cmd += [f"-metadata:s:a:{i}", f"language={lng}"]
            else:
                cmd += ["-c:a","copy"]

        # ── Subtitles ──────────────────────────────────────────────────────
        # Key rules:
        #   - MP4/MOV: SRT must be converted to mov_text; burn-in is safest
        #   - MKV/TS:  copy is fine
        #   - Never auto-map ALL subtitle streams (causes failures)
        #   - Only include subs if user explicitly picks one (manual index,
        #     external file, or burn-in checkbox)

        ms = self.manual_sub_var.get().strip()
        if ms:
            cmd += ["-map", f"0:{ms}", "-c:s", sub_codec]

        elif ext_sub_valid:
            srows = [r for r in self.track_rows if r.stream_type=="subtitle"]
            burn  = srows[0].burn_var.get() if srows else False
            if burn:
                esc = ext_sub.replace("\\", "/")
                cmd += ["-vf", f"subtitles='{esc}'"]
            else:
                cmd += ["-map", "1:0", "-c:s", sub_codec]

        else:
            srows = [r for r in self.track_rows if r.stream_type=="subtitle"]
            sub_out_idx = 0
            for sr in srows:
                si   = sr.get_stream_index()
                burn = sr.burn_var.get()
                dly  = sr.delay_var.get().strip()
                lng  = sr.lang_var.get().strip()
                if si is None:
                    continue
                if burn:
                    esc = self.filepath.replace("\\", "/")
                    cmd += ["-vf", f"subtitles='{esc}':si={si}"]
                    # burned in = don't also map as a stream
                else:
                    # For MKV/TS pass through; skip for MP4 (incompatible codec)
                    if out_ext in ("mkv","ts","webm","matroska"):
                        cmd += ["-map", f"0:{si}", "-c:s", sub_codec]
                        if dly and dly != "0":
                            try: cmd += ["-itsoffset", str(float(dly)/1000)]
                            except: pass
                        if lng: cmd += [f"-metadata:s:s:{sub_out_idx}", f"language={lng}"]
                        sub_out_idx += 1
                    # MP4: only burn-in works reliably; stream copy needs mov_text
                    # which ffmpeg can't auto-convert from srt — skip silently

        # ── Extra flags ────────────────────────────────────────────────────
        extra = self.extra_flags.get().strip()
        if extra:
            try:
                import shlex
                cmd += shlex.split(extra)
            except:
                cmd += extra.split()

        cmd.append(self.get_output_path())
        return cmd

# ── Log window ─────────────────────────────────────────────────────────────────
class LogWindow(ctk.CTkToplevel):
    def __init__(self, master):
        super().__init__(master)
        self.title("Conversion Log"); self.geometry("820x520")
        self.configure(fg_color=BG_DARK)
        self.grid_rowconfigure(0,weight=1); self.grid_columnconfigure(0,weight=1)
        self.tb = ctk.CTkTextbox(self, fg_color=BG_MID, text_color=TEXT,
                                  font=ctk.CTkFont("Courier",11),
                                  border_color=BORDER, border_width=1)
        self.tb.grid(row=0,column=0,sticky="nsew",padx=16,pady=(16,8))
        ctk.CTkButton(self,text="Copy Log",width=100,height=28,
                       fg_color=BG_CARD,hover_color=BORDER,text_color=TEXT,
                       command=self._copy).grid(row=1,column=0,pady=(0,12))

    def log(self, t):
        self.tb.insert("end", t); self.tb.see("end"); self.update_idletasks()

    def _copy(self):
        self.clipboard_clear(); self.clipboard_append(self.tb.get("1.0","end"))


# ── Main App ───────────────────────────────────────────────────────────────────
class App(_BASE):
    def __init__(self):
        super().__init__()
        self.title("FFmpeg GUI  v2")
        self.geometry("1020x800"); self.minsize(860,600)
        self.configure(fg_color=BG_DARK)
        self.rows = []
        self._build_ui()
        # DnD: wait for window to be fully drawn then register
        self.after(800, self._setup_dnd)

    def _build_ui(self):
        self.grid_rowconfigure(2,weight=1); self.grid_columnconfigure(0,weight=1)

        hdr = ctk.CTkFrame(self,fg_color=BG_MID,corner_radius=0,height=58)
        hdr.grid(row=0,column=0,sticky="ew"); hdr.grid_propagate(False)
        hdr.grid_columnconfigure(1,weight=1)
        ctk.CTkFrame(hdr,width=8,height=32,fg_color=ACCENT,corner_radius=4
                      ).grid(row=0,column=0,padx=(20,10),pady=13)
        ctk.CTkLabel(hdr,text="FFmpeg GUI",text_color=TEXT,
                      font=ctk.CTkFont(size=18,weight="bold")).grid(row=0,column=1,sticky="w")
        ctk.CTkLabel(hdr,text="v2  ·  full track control  ·  standalone",
                      text_color=MUTED,font=ctk.CTkFont(size=11)).grid(row=0,column=2,padx=20)

        # Drop zone — store as instance var so DnD can register on it
        self.drop_zone = ctk.CTkFrame(self,fg_color=BG_MID,corner_radius=14,
                                       border_width=2,border_color=BORDER,height=90)
        self.drop_zone.grid(row=1,column=0,sticky="ew",padx=20,pady=(14,8))
        self.drop_zone.grid_propagate(False)
        self.drop_zone.grid_rowconfigure(0,weight=1); self.drop_zone.grid_columnconfigure(0,weight=1)
        inner = ctk.CTkFrame(self.drop_zone,fg_color="transparent"); inner.grid(row=0,column=0)
        ctk.CTkLabel(inner,text="⬇  Drop files here  or",text_color=MUTED,
                      font=ctk.CTkFont(size=14)).grid(row=0,column=0,padx=8)
        ctk.CTkButton(inner,text="Browse Files",width=120,height=32,
                       fg_color=ACCENT,hover_color=ACCENT2,text_color=TEXT,
                       font=ctk.CTkFont(size=13,weight="bold"),
                       command=self._browse).grid(row=0,column=1)

        self.scroll = ctk.CTkScrollableFrame(self,fg_color="transparent",
                                              scrollbar_button_color=BORDER,
                                              scrollbar_button_hover_color=ACCENT)
        self.scroll.grid(row=2,column=0,sticky="nsew",padx=20)
        self.scroll.grid_columnconfigure(0,weight=1)

        bot = ctk.CTkFrame(self,fg_color=BG_MID,corner_radius=0,height=56)
        bot.grid(row=3,column=0,sticky="ew"); bot.grid_propagate(False)
        bot.grid_columnconfigure(1,weight=1)
        self.status_lbl = ctk.CTkLabel(bot,text="Ready",text_color=MUTED,font=ctk.CTkFont(size=12))
        self.status_lbl.grid(row=0,column=0,padx=20,pady=16,sticky="w")
        self.progress = ctk.CTkProgressBar(bot,height=6,fg_color=BORDER,progress_color=ACCENT)
        self.progress.grid(row=0,column=1,sticky="ew",padx=16); self.progress.set(0)
        ctk.CTkButton(bot,text="Clear All",width=90,height=32,
                       fg_color="transparent",border_width=1,border_color=BORDER,
                       hover_color=BG_CARD,text_color=MUTED,
                       command=self._clear).grid(row=0,column=2,padx=(0,8))
        self.convert_btn = ctk.CTkButton(bot,text="▶  Convert All",width=130,height=36,
                                          fg_color=ACCENT,hover_color=ACCENT2,text_color=TEXT,
                                          font=ctk.CTkFont(size=13,weight="bold"),
                                          command=self._convert)
        self.convert_btn.grid(row=0,column=3,padx=(0,16))

        if not ffmpeg_available():
            self.status_lbl.configure(text="⚠  ffmpeg not found — check installation",text_color=YELLOW)
            self.convert_btn.configure(state="disabled")

    def _setup_dnd(self):
        """Register DnD on the root window and drop zone."""
        if not _DND_AVAILABLE:
            return
        try:
            self.drop_target_register(DND_FILES)
            self.dnd_bind("<<Drop>>", self._on_drop)
            self.drop_zone.drop_target_register(DND_FILES)
            self.drop_zone.dnd_bind("<<Drop>>", self._on_drop)
            self.drop_zone.configure(border_color=ACCENT)
        except Exception:
            pass

    def _on_drop(self, event):
        raw = event.data.strip()
        # paths wrapped in {} if they contain spaces
        paths = re.findall(r'\{([^}]+)\}', raw)
        remainder = re.sub(r'\{[^}]+\}', '', raw).strip()
        if remainder:
            paths += remainder.split()
        for p in paths:
            p = p.strip().strip('"')
            if p and os.path.isfile(p):
                self._add(p)


    def _browse(self):
        paths = filedialog.askopenfilenames(
            title="Select media files",
            filetypes=[("Media files",
                        "*.mp4 *.mkv *.avi *.mov *.webm *.flv *.ts "
                        "*.m4v *.mp3 *.aac *.flac *.wav *.ogg *.m4a *.opus *.wmv"),
                       ("All files","*.*")])
        for p in paths:
            self._add(p)

    def _add(self, path):
        if any(r.filepath == path for r in self.rows): return
        row = ConversionRow(self.scroll, path, self._rm, job_index=len(self.rows)+1)
        row.grid(row=len(self.rows), column=0, sticky="ew", pady=(0,12))
        self.rows.append(row)
        self.status_lbl.configure(text=f"{len(self.rows)} file(s) loaded", text_color=MUTED)

    def _rm(self, row):
        row.destroy(); self.rows.remove(row)
        for i,r in enumerate(self.rows): r.grid(row=i,column=0,sticky="ew",pady=(0,12))
        self.status_lbl.configure(text=f"{len(self.rows)} file(s) loaded", text_color=MUTED)

    def _clear(self):
        for r in self.rows[:]: r.destroy()
        self.rows.clear(); self.progress.set(0)
        self.status_lbl.configure(text="Ready", text_color=MUTED)

    def _convert(self):
        if not self.rows:
            messagebox.showinfo("No files","Add some files first!"); return
        self.convert_btn.configure(state="disabled")
        log = LogWindow(self); log.focus()

        def _worker():
            total = len(self.rows)
            for idx, row in enumerate(self.rows, 1):
                cmd  = row.build_cmd()
                name = Path(row.filepath).name
                self.after(0, lambda n=name,i=idx,t=total:
                    self.status_lbl.configure(text=f"Converting {i}/{t}: {n}",text_color=ACCENT2))
                log.log(f"\n{'─'*70}\n[{idx}/{total}] {name}\n")
                log.log("CMD: " + " ".join(f'"{c}"' if " " in c else c for c in cmd) + "\n\n")
                try:
                    proc = subprocess.Popen(
                        cmd, stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
                        text=True, encoding="utf-8", errors="replace",
                        creationflags=_NO_WINDOW())
                    for line in proc.stdout: log.log(line)
                    proc.wait()
                    ok = proc.returncode == 0
                    log.log(f"\n{'✓ Done' if ok else '✗ Failed'} (exit {proc.returncode})\n")
                except Exception as e:
                    log.log(f"\nError launching ffmpeg: {e}\n")
                self.after(0, self.progress.set, idx/total)
            self.after(0, lambda: self.status_lbl.configure(text=f"✓ All {total} done",text_color=GREEN))
            self.after(0, lambda: self.convert_btn.configure(state="normal"))

        threading.Thread(target=_worker, daemon=True).start()


# ── Entry point ────────────────────────────────────────────────────────────────
if __name__ == "__main__":
    _get_ffmpeg_dir()

    app = App()
    app.mainloop()
