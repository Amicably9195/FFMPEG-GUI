#!/usr/bin/env python3
"""cad_io - CAD file input/output for Drawing2CAD (Phase A: translation tier).

CAD project files (DWG, DGN) and DXF are already vector data, so converting
them is TRANSLATION, not tracing - and translation can be faithful/exact.

  * DXF in/out is native (ezdxf), always available.
  * DWG/DGN in, and DWG out, need a local converter. The backend is modular
    and auto-detected:
      - ODA File Converter (free, best fidelity; handles DWG + DGN)
      - LibreDWG's dwg2dxf / dxf2dwg (free/open; DWG only)
    Neither can be bundled in the app - the user installs one once, like
    Tesseract - so everything degrades gracefully when none is present:
    DWG output falls back to DXF (which AutoCAD and MicroStation open
    natively) with a clear message.

A new backend (a commercial SDK, a future library) drops in by adding one
entry to _BACKENDS without touching the rest of the app.
"""

import os
import shutil
import subprocess
import sys
import tempfile

CAD_INPUT_EXTS = (".dwg", ".dgn", ".dxf")


# ── backend discovery ────────────────────────────────────────────────────────

def _find_oda():
    """Locate the ODA File Converter binary, or None."""
    env = os.environ.get("ODA_CONVERTER")
    if env and os.path.isfile(env):
        return env
    for name in ("ODAFileConverter", "ODAFileConverter.exe"):
        p = shutil.which(name)
        if p:
            return p
    candidates = [
        r"C:\Program Files\ODA\ODAFileConverter\ODAFileConverter.exe",
        r"C:\Program Files\ODA\ODAFileConverter 25.4.0\ODAFileConverter.exe",
        "/usr/bin/ODAFileConverter",
        "/opt/ODAFileConverter/ODAFileConverter",
    ]
    for base in ("C:\\Program Files\\ODA",):
        if os.path.isdir(base):
            for d in os.listdir(base):
                candidates.append(os.path.join(base, d,
                                                "ODAFileConverter.exe"))
    for c in candidates:
        if os.path.isfile(c):
            return c
    return None


def _find_libredwg():
    """Locate LibreDWG's dwg2dxf/dxf2dwg pair, or None."""
    d2x = shutil.which("dwg2dxf") or shutil.which("dwg2dxf.exe")
    x2d = shutil.which("dxf2dwg") or shutil.which("dxf2dwg.exe")
    if d2x or x2d:
        return {"dwg2dxf": d2x, "dxf2dwg": x2d}
    return None


def detect_backend():
    """Return (name, handle) for the best available converter, or (None, None).
    ODA is preferred (higher fidelity, DGN support)."""
    oda = _find_oda()
    if oda:
        return "oda", oda
    lib = _find_libredwg()
    if lib:
        return "libredwg", lib
    return None, None


def backend_name():
    return detect_backend()[0]


# ── ODA File Converter (folder-based Qt app) ─────────────────────────────────

def _run_oda(exe, in_dir, out_dir, out_type, out_ver="ACAD2018",
             in_filter="*.*"):
    # ODAFileConverter "in" "out" version type recurse audit [filter]
    cmd = [exe, in_dir, out_dir, out_ver, out_type, "0", "1", in_filter]
    if sys.platform.startswith("linux") and shutil.which("xvfb-run"):
        cmd = ["xvfb-run", "-a"] + cmd  # headless: it's a Qt GUI app
    subprocess.run(cmd, check=True, timeout=300,
                   stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)


def _oda_convert(exe, src, dst, out_type):
    """Convert one file via ODA by staging it in a temp folder pair."""
    with tempfile.TemporaryDirectory() as tin, \
            tempfile.TemporaryDirectory() as tout:
        staged = os.path.join(tin, os.path.basename(src))
        shutil.copy2(src, staged)
        ext = os.path.splitext(src)[1] or ".dwg"
        _run_oda(exe, tin, tout, out_type, in_filter="*" + ext)
        base = os.path.splitext(os.path.basename(src))[0]
        produced = os.path.join(tout, base + "." + out_type.lower())
        if not os.path.isfile(produced):
            hits = [f for f in os.listdir(tout)
                    if f.lower().endswith("." + out_type.lower())]
            if not hits:
                raise RuntimeError("ODA File Converter produced no output")
            produced = os.path.join(tout, hits[0])
        shutil.move(produced, dst)
    return dst


# ── public API ───────────────────────────────────────────────────────────────

def to_dxf(input_path, out_dxf, log=print):
    """Bring any CAD file to DXF. DXF is normalized through ezdxf; DWG/DGN go
    through the detected backend. Raises RuntimeError with a clear message
    when a backend is required but absent."""
    ext = os.path.splitext(input_path)[1].lower()
    if ext == ".dxf":
        import ezdxf
        ezdxf.readfile(input_path).saveas(out_dxf)  # validate + normalize
        return out_dxf
    name, handle = detect_backend()
    if name == "oda":
        log(f"Converting {ext.upper()[1:]} -> DXF via ODA File Converter ...")
        return _oda_convert(handle, input_path, out_dxf, "DXF")
    if name == "libredwg" and ext == ".dwg" and handle["dwg2dxf"]:
        log("Converting DWG -> DXF via LibreDWG ...")
        subprocess.run([handle["dwg2dxf"], "-o", out_dxf, input_path],
                       check=True, timeout=300,
                       stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        return out_dxf
    raise RuntimeError(
        f"Reading {ext.upper()[1:]} files needs a local CAD converter. "
        "Install the free ODA File Converter "
        "(https://www.opendesign.com/guestfiles/oda_file_converter) and "
        "restart, or set ODA_CONVERTER to its path.")


def from_dxf(dxf_path, out_path, log=print, out_ver="ACAD2018"):
    """Write out_path from a DXF. .dxf is a copy; .dwg needs a backend and
    returns False (with the DXF left in place) if none is available so the
    caller can fall back gracefully. .dgn needs ODA."""
    ext = os.path.splitext(out_path)[1].lower()
    if ext == ".dxf":
        if os.path.abspath(dxf_path) != os.path.abspath(out_path):
            shutil.copy2(dxf_path, out_path)
        return True
    name, handle = detect_backend()
    if ext == ".dwg":
        if name == "oda":
            log("Converting DXF -> DWG via ODA File Converter ...")
            _oda_convert(handle, dxf_path, out_path, "DWG")
            return True
        if name == "libredwg" and handle["dxf2dwg"]:
            log("Converting DXF -> DWG via LibreDWG ...")
            subprocess.run([handle["dxf2dwg"], "-o", out_path, dxf_path],
                           check=True, timeout=300,
                           stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
            return True
        return False  # no backend - caller keeps the DXF
    if ext == ".dgn":
        if name == "oda":
            log("Converting DXF -> DGN via ODA File Converter ...")
            _oda_convert(handle, dxf_path, out_path, "DGN")
            return True
        return False
    return False
