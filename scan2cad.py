#!/usr/bin/env python3
"""scan2cad - Convert photos/scans of technical drawings into layered DXF files.

Pipeline:
  1. Load photo/scan, flatten uneven lighting, auto-detect & straighten the page
  2. OCR text (horizontal + vertical passes) with Tesseract
  3. Mask text out of the image, then vectorize the remaining linework
     (straight segments via LSD, leftover curves as traced polylines)
  4. Write a DXF with LINES / CURVES / TEXT layers that opens in
     AutoCAD and MicroStation (MicroStation can save it as DGN)

Usable as a library (see convert()) or from the command line:
    python scan2cad.py drawing.jpg -o drawing.dxf
"""

import argparse
import math
import os
import re
import shutil
import sys

import cv2
import numpy as np

try:
    import pytesseract
    _HAS_TESS = True
except ImportError:
    _HAS_TESS = False

import ezdxf

# ── Tesseract binary resolution (Windows installs are rarely on PATH) ─────────

def find_tesseract():
    """Locate the tesseract binary; returns its path or None."""
    if not _HAS_TESS:
        return None
    env = os.environ.get("TESSERACT_CMD")
    if env and os.path.isfile(env):
        pytesseract.pytesseract.tesseract_cmd = env
        return env
    on_path = shutil.which("tesseract")
    if on_path:
        return on_path
    here = os.path.dirname(sys.executable if getattr(sys, "frozen", False)
                           else os.path.abspath(__file__))
    candidates = [
        os.path.join(here, "tesseract", "tesseract.exe"),
        os.path.join(here, "tesseract.exe"),
        r"C:\Program Files\Tesseract-OCR\tesseract.exe",
        r"C:\Program Files (x86)\Tesseract-OCR\tesseract.exe",
        os.path.expandvars(r"%LOCALAPPDATA%\Programs\Tesseract-OCR\tesseract.exe"),
    ]
    for c in candidates:
        if os.path.isfile(c):
            pytesseract.pytesseract.tesseract_cmd = c
            return c
    return None


# ── Image preparation ──────────────────────────────────────────────────────────

def load_gray(path):
    data = np.fromfile(path, dtype=np.uint8)  # np.fromfile handles unicode paths on Windows
    img = cv2.imdecode(data, cv2.IMREAD_COLOR)
    if img is None:
        raise ValueError(f"Could not read image: {path}")
    return cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)


def flatten_lighting(gray):
    """Divide out low-frequency shading so photos threshold like flat scans."""
    bg = cv2.GaussianBlur(gray, (0, 0), sigmaX=25)
    norm = cv2.divide(gray, bg, scale=255)
    return norm


def find_page_quad(gray):
    """Find the sheet of paper as a convex quadrilateral, or None."""
    h, w = gray.shape
    small = cv2.resize(gray, (w // 4, h // 4))
    blur = cv2.GaussianBlur(small, (5, 5), 0)
    edges = cv2.Canny(blur, 40, 120)
    edges = cv2.dilate(edges, np.ones((3, 3), np.uint8), iterations=2)
    contours, _ = cv2.findContours(edges, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
    if not contours:
        return None
    biggest = max(contours, key=cv2.contourArea)
    if cv2.contourArea(biggest) < 0.35 * small.size:
        return None
    peri = cv2.arcLength(biggest, True)
    approx = cv2.approxPolyDP(biggest, 0.02 * peri, True)
    if len(approx) != 4 or not cv2.isContourConvex(approx):
        return None
    return approx.reshape(4, 2).astype(np.float64) * 4.0


def warp_to_page(gray, quad):
    """Perspective-correct the page quad to an axis-aligned rectangle."""
    # Order corners: top-left, top-right, bottom-right, bottom-left
    s = quad.sum(axis=1)
    d = np.diff(quad, axis=1).ravel()
    tl, br = quad[np.argmin(s)], quad[np.argmax(s)]
    tr, bl = quad[np.argmin(d)], quad[np.argmax(d)]
    wid = int(max(np.linalg.norm(br - bl), np.linalg.norm(tr - tl)))
    hei = int(max(np.linalg.norm(tr - br), np.linalg.norm(tl - bl)))
    if wid < 200 or hei < 200:
        return None
    src = np.array([tl, tr, br, bl], dtype=np.float32)
    dst = np.array([[0, 0], [wid - 1, 0], [wid - 1, hei - 1], [0, hei - 1]],
                   dtype=np.float32)
    m = cv2.getPerspectiveTransform(src, dst)
    return cv2.warpPerspective(gray, m, (wid, hei),
                               flags=cv2.INTER_LINEAR,
                               borderMode=cv2.BORDER_REPLICATE)


def estimate_skew(gray):
    """Dominant rotation (deg) of the linework away from horizontal/vertical."""
    edges = cv2.Canny(gray, 50, 150)
    lines = cv2.HoughLinesP(edges, 1, np.pi / 360, threshold=120,
                            minLineLength=gray.shape[1] // 8, maxLineGap=6)
    if lines is None:
        return 0.0
    devs, weights = [], []
    for x1, y1, x2, y2 in lines.reshape(-1, 4):
        ang = math.degrees(math.atan2(y2 - y1, x2 - x1))
        dev = ((ang + 45) % 90) - 45  # deviation from nearest 0/90 axis
        if abs(dev) < 12:
            devs.append(dev)
            weights.append(math.hypot(x2 - x1, y2 - y1))
    if not devs:
        return 0.0
    order = np.argsort(devs)
    cum = np.cumsum(np.asarray(weights, dtype=np.float64)[order])
    median = np.asarray(devs)[order][np.searchsorted(cum, cum[-1] / 2)]
    return float(median)


def rotate_bound(gray, angle):
    """Rotate image by angle (deg) expanding the canvas so nothing is cut off."""
    h, w = gray.shape
    m = cv2.getRotationMatrix2D((w / 2, h / 2), angle, 1.0)
    cos, sin = abs(m[0, 0]), abs(m[0, 1])
    nw, nh = int(h * sin + w * cos), int(h * cos + w * sin)
    m[0, 2] += nw / 2 - w / 2
    m[1, 2] += nh / 2 - h / 2
    return cv2.warpAffine(gray, m, (nw, nh),
                          flags=cv2.INTER_LINEAR, borderMode=cv2.BORDER_REPLICATE)


def binarize(gray):
    """Return ink mask: 255 where there is ink, 0 for paper."""
    thr = cv2.adaptiveThreshold(gray, 255, cv2.ADAPTIVE_THRESH_GAUSSIAN_C,
                                cv2.THRESH_BINARY_INV, 35, 15)
    return thr


def remove_specks_and_blobs(ink, min_area=8):
    """Drop tiny specks (dust, halftone dots) and solid edge-touching blobs
    (binder clips, shadows at the paper edge)."""
    n, labels, stats, _ = cv2.connectedComponentsWithStats(ink, connectivity=8)
    h, w = ink.shape
    keep = np.zeros(n, dtype=bool)
    for i in range(1, n):
        x, y, bw, bh, area = stats[i]
        if area < min_area:
            continue
        touches_edge = x <= 1 or y <= 1 or x + bw >= w - 1 or y + bh >= h - 1
        solidity = area / float(bw * bh)
        if touches_edge and solidity > 0.35 and area > 400:
            continue  # solid blob at the border: clip / shadow, not linework
        keep[i] = True
    return np.where(keep[labels], np.uint8(255), np.uint8(0))


def stroke_width(ink):
    """Median stroke width of the linework in pixels."""
    dist = cv2.distanceTransform(ink, cv2.DIST_L2, 3)
    vals = dist[ink > 0]
    if vals.size == 0:
        return 2.0
    return max(1.5, 2.0 * float(np.median(vals)))


# ── OCR ────────────────────────────────────────────────────────────────────────

def _ocr_pass(gray, rotate_code, cad_rotation, min_conf):
    """One tesseract pass; boxes mapped back to the un-rotated frame.
    Each word: dict(text, conf, x, y, w, h  [orig frame px],
                    insert (px point), rotation [deg CAD])."""
    h0, w0 = gray.shape
    img = gray if rotate_code is None else cv2.rotate(gray, rotate_code)
    data = pytesseract.image_to_data(img, config="--psm 11",
                                     output_type=pytesseract.Output.DICT)
    words = []
    for i, text in enumerate(data["text"]):
        text = text.strip()
        conf = float(data["conf"][i])
        if not text or conf < min_conf:
            continue
        if not any(ch.isalnum() for ch in text):
            continue
        x, y = data["left"][i], data["top"][i]
        w, h = data["width"][i], data["height"][i]
        if h < 6 or h > 200 or w < 3:
            continue
        # Map box corners and reading-orientation baseline point back to the
        # original frame.
        if rotate_code is None:
            bx, by, bw, bh = x, y, w, h
            insert = (x, y + h)
        elif rotate_code == cv2.ROTATE_90_CLOCKWISE:
            # orig (X,Y) -> rotated (H0-1-Y, X);  inverse: X = y', Y = H0-1-x'
            bx, by, bw, bh = y, h0 - 1 - x - w, h, w
            insert = (y + h, h0 - 1 - x)
        else:  # ROTATE_90_COUNTERCLOCKWISE
            # orig (X,Y) -> rotated (Y, W0-1-X);  inverse: X = W0-1-y', Y = x'
            bx, by, bw, bh = w0 - 1 - y - h, x, h, w
            insert = (w0 - 1 - y - h, x)
        # cap height is always the box height in reading orientation (h)
        words.append(dict(text=text, conf=conf, x=bx, y=by, w=bw, h=bh,
                          insert=insert, rotation=cad_rotation, cap=h))
    return words


def _overlap(a, b):
    ix = max(0, min(a["x"] + a["w"], b["x"] + b["w"]) - max(a["x"], b["x"]))
    iy = max(0, min(a["y"] + a["h"], b["y"] + b["h"]) - max(a["y"], b["y"]))
    inter = ix * iy
    union = a["w"] * a["h"] + b["w"] * b["h"] - inter
    return inter / union if union else 0.0


def ocr_words(gray, min_conf=45, vertical=True):
    """OCR horizontal text plus (optionally) both vertical orientations,
    de-duplicated by box overlap keeping the higher-confidence read."""
    words = _ocr_pass(gray, None, 0, min_conf)
    if vertical:
        words += _ocr_pass(gray, cv2.ROTATE_90_CLOCKWISE, 90, min_conf)
        words += _ocr_pass(gray, cv2.ROTATE_90_COUNTERCLOCKWISE, 270, min_conf)
    words.sort(key=lambda d: -d["conf"])
    kept = []
    for cand in words:
        if all(_overlap(cand, k) < 0.3 for k in kept):
            kept.append(cand)
    if kept:
        # clamp runaway boxes (merged multi-line reads) to a sane text height
        med = float(np.median([w["cap"] for w in kept]))
        for w in kept:
            w["cap"] = min(w["cap"], 3.0 * med)
    return kept


# ── Dimension parsing & scale verification ────────────────────────────────────

_QUOTE_MAP = str.maketrans({"’": "'", "‘": "'", "`": "'", "′": "'",
                            "“": '"', "”": '"', "″": '"'})


def parse_dimension(text):
    """Parse dimension text into feet, or None if it isn't a dimension.
    Handles 40.00'  100'  5'-6"  9.8'  6"  ±15' plus survey offsets like
    2.3'N. OCR often reads the foot mark as '!', so accept that too."""
    t = text.strip().translate(_QUOTE_MAP).strip("()[]{},;:").replace(" ", "")
    m = re.fullmatch(r"[±+\-]?(\d{1,4}(?:\.\d{1,3})?)['!]"
                     r"(?:-?(\d{1,2}(?:\.\d+)?)\")?[NSEWnsew]?", t)
    if m:
        feet = float(m.group(1))
        if m.group(2):
            feet += float(m.group(2)) / 12.0
        return feet if feet > 0 else None
    m = re.fullmatch(r"[±+\-]?(\d{1,3}(?:\.\d+)?)\"[NSEWnsew]?", t)
    if m:
        inches = float(m.group(1))
        return inches / 12.0 if inches > 0 else None
    return None


def _verifiable(w):
    """Only real span dimensions can be checked against drawn lines: compass
    offsets (2.3'N) and tiny values aren't drawn to a measurable length."""
    return w.get("dim") and w["dim"] >= 5.0 and \
        not w["text"].strip().upper().endswith(("N", "S", "E", "W"))


def _point_seg_dist(px, py, seg):
    x1, y1, x2, y2 = seg
    dx, dy = x2 - x1, y2 - y1
    l2 = dx * dx + dy * dy
    if l2 == 0:
        return math.hypot(px - x1, py - y1)
    t = max(0.0, min(1.0, ((px - x1) * dx + (py - y1) * dy) / l2))
    return math.hypot(px - (x1 + t * dx), py - (y1 + t * dy))


def estimate_scale(words, segs, tolerance=0.10):
    """Cross-check parsed dimensions against nearby drawn lines.

    Each dimension label paired with the line it measures implies a scale
    (feet per pixel); on a consistent drawing they all agree.  The consensus
    is the scale cluster supported by the most independent dimensions
    (minimum 3).  Returns the consensus scale (ft/px) or None, and sets
    per-word:
      dim_ok = True   dimension agrees with the consensus scale
      dim_ok = False  dimension contradicts it -> needs human review
    """
    dims = [w for w in words if _verifiable(w)]
    if len(dims) < 3 or len(segs) < 1:
        return None
    # measurement geometry: re-merge with a generous gap so lines broken by
    # crossings (a walk cutting a lot line in two) read as their full length
    meas = merge_segments(segs, gap_tol=40.0)
    if len(meas) == 0:
        return None
    mlen = np.hypot(meas[:, 2] - meas[:, 0], meas[:, 3] - meas[:, 1])
    mang = np.degrees(np.arctan2(meas[:, 3] - meas[:, 1],
                                 meas[:, 2] - meas[:, 0])) % 180.0

    cands = []  # (word index, implied ft/px, distance to line)
    for wi, w in enumerate(dims):
        cx, cy = w["x"] + w["w"] / 2.0, w["y"] + w["h"] / 2.0
        vertical = w["rotation"] in (90, 270)
        radius = 4.0 * w["cap"] + max(w["w"], w["h"])
        for i in range(len(meas)):
            if mlen[i] < 30:
                continue
            ang_ok = (70 < mang[i] < 110) if vertical else \
                     (mang[i] < 20 or mang[i] > 160)
            if not ang_ok:
                continue
            d = _point_seg_dist(cx, cy, meas[i])
            if d > radius:
                continue
            cands.append((wi, w["dim"] / mlen[i], d))
    if not cands:
        return None

    # densest cluster of implied scales, ranked by distinct supporting words
    best_score, best_members = None, None
    for _, s0, _ in cands:
        members = [c for c in cands if abs(c[1] / s0 - 1.0) <= tolerance]
        support = len({c[0] for c in members})
        score = (support, -min(c[2] for c in members))
        if best_score is None or score > best_score:
            best_score, best_members = score, members
    if len({c[0] for c in best_members}) < 3:
        return None
    scale = float(np.median([c[1] for c in best_members]))

    for wi, w in enumerate(dims):
        mine = [c for c in cands if c[0] == wi]
        if mine:
            w["dim_ok"] = any(abs(c[1] / scale - 1.0) <= 1.5 * tolerance
                              for c in mine)
    return scale


def mask_words(ink, words, pad=2):
    """Blank OCRed word boxes out of the ink mask so text isn't vectorized."""
    out = ink.copy()
    for wd in words:
        x0 = max(0, wd["x"] - pad)
        y0 = max(0, wd["y"] - pad)
        x1 = min(ink.shape[1], wd["x"] + wd["w"] + pad)
        y1 = min(ink.shape[0], wd["y"] + wd["h"] + pad)
        out[y0:y1, x0:x1] = 0
    return out


# ── Vectorization ──────────────────────────────────────────────────────────────

def detect_segments(ink):
    """Straight line segments (N x 4 array of x1,y1,x2,y2) from the ink mask."""
    inverted = cv2.bitwise_not(ink)  # LSD expects dark strokes on light ground
    try:
        lsd = cv2.createLineSegmentDetector()
        lines = lsd.detect(inverted)[0]
        if lines is None:
            return np.empty((0, 4))
        return lines.reshape(-1, 4).astype(np.float64)
    except cv2.error:
        lines = cv2.HoughLinesP(ink, 1, np.pi / 360, threshold=40,
                                minLineLength=12, maxLineGap=3)
        if lines is None:
            return np.empty((0, 4))
        return lines.reshape(-1, 4).astype(np.float64)


def snap_orthogonal(segs, tol_deg=1.5):
    """Rotate near-horizontal/vertical segments about their midpoints to exact."""
    out = segs.copy()
    dx = segs[:, 2] - segs[:, 0]
    dy = segs[:, 3] - segs[:, 1]
    ang = np.degrees(np.arctan2(dy, dx)) % 180.0
    length = np.hypot(dx, dy)
    mx = (segs[:, 0] + segs[:, 2]) / 2
    my = (segs[:, 1] + segs[:, 3]) / 2
    horiz = (ang < tol_deg) | (ang > 180 - tol_deg)
    vert = np.abs(ang - 90) < tol_deg
    out[horiz] = np.stack([mx[horiz] - length[horiz] / 2, my[horiz],
                           mx[horiz] + length[horiz] / 2, my[horiz]], axis=1)
    out[vert] = np.stack([mx[vert], my[vert] - length[vert] / 2,
                          mx[vert], my[vert] + length[vert] / 2], axis=1)
    return out


def merge_segments(segs, angle_tol=2.0, offset_tol=2.5, gap_tol=4.0):
    """Merge collinear, overlapping/nearly-touching segments (LSD reports each
    stroke edge separately and breaks lines at junctions)."""
    if len(segs) == 0:
        return segs
    dx = segs[:, 2] - segs[:, 0]
    dy = segs[:, 3] - segs[:, 1]
    ang = np.degrees(np.arctan2(dy, dx)) % 180.0
    merged = []
    used = np.zeros(len(segs), dtype=bool)
    order = np.argsort(ang)
    i = 0
    while i < len(order):
        # take a band of similar angles (handle 0/180 wrap by two passes below)
        a0 = ang[order[i]]
        j = i
        while j < len(order) and ang[order[j]] - a0 <= angle_tol:
            j += 1
        band = order[i:j]
        i = j
        _merge_band(segs, band, ang, offset_tol, gap_tol, merged, used)
    # wraparound band: angles near 0 and near 180 are the same direction
    wrap = np.where((ang < angle_tol) | (ang > 180 - angle_tol))[0]
    wrap = wrap[~used[wrap]] if len(wrap) else wrap
    if len(wrap):
        _merge_band(segs, wrap, ang, offset_tol, gap_tol, merged, used)
    return np.array(merged) if merged else np.empty((0, 4))


def _merge_band(segs, band, ang, offset_tol, gap_tol, merged, used):
    band = band[~used[band]]
    if len(band) == 0:
        return
    used[band] = True
    a = math.radians(np.median(np.where(ang[band] > 170,
                                        ang[band] - 180, ang[band])))
    d = np.array([math.cos(a), math.sin(a)])
    n = np.array([-d[1], d[0]])
    p1 = segs[band][:, :2]
    p2 = segs[band][:, 2:]
    rho = ((p1 + p2) / 2) @ n
    t1 = p1 @ d
    t2 = p2 @ d
    tmin, tmax = np.minimum(t1, t2), np.maximum(t1, t2)
    order = np.argsort(rho)
    k = 0
    while k < len(order):
        m = k
        while m + 1 < len(order) and rho[order[m + 1]] - rho[order[m]] < offset_tol:
            m += 1
        group = order[k:m + 1]
        k = m + 1
        r = float(np.mean(rho[group]))
        ivs = sorted(zip(tmin[group], tmax[group]))
        cs, ce = ivs[0]
        for s, e in ivs[1:]:
            if s - ce <= gap_tol:
                ce = max(ce, e)
            else:
                merged.append(np.concatenate([r * n + cs * d, r * n + ce * d]))
                cs, ce = s, e
        merged.append(np.concatenate([r * n + cs * d, r * n + ce * d]))


def residual_curves(ink, segs, width, min_area=40, epsilon=1.8):
    """Trace whatever ink the straight segments didn't explain (curves, circles,
    symbols) as polylines. Returns list of (points Nx2, closed)."""
    canvas = ink.copy()
    thick = max(3, int(round(width * 1.5)) + 2)
    for x1, y1, x2, y2 in segs:
        cv2.line(canvas, (int(round(x1)), int(round(y1))),
                 (int(round(x2)), int(round(y2))), 0, thick)
    canvas = cv2.morphologyEx(canvas, cv2.MORPH_OPEN, np.ones((2, 2), np.uint8))
    contours, _ = cv2.findContours(canvas, cv2.RETR_LIST, cv2.CHAIN_APPROX_SIMPLE)
    polys = []
    for c in contours:
        if cv2.contourArea(c) < min_area and cv2.arcLength(c, True) < 60:
            continue
        approx = cv2.approxPolyDP(c, epsilon, True)
        if len(approx) < 2:
            continue
        polys.append((approx.reshape(-1, 2).astype(np.float64), True))
    return polys


# ── DXF output ─────────────────────────────────────────────────────────────────

def write_dxf(path, img_h, segments, curves, words, scale=1.0,
              min_len_px=6.0, units_feet=False):
    doc = ezdxf.new("R2010", setup=True)
    doc.layers.add("LINES", color=7)
    doc.layers.add("CURVES", color=4)
    doc.layers.add("TEXT", color=3)
    doc.layers.add("TEXT_REVIEW", color=1)  # red: uncertain, check by hand
    if units_feet:
        doc.header["$INSUNITS"] = 2  # feet
    msp = doc.modelspace()

    def pt(x, y):
        return (x * scale, (img_h - y) * scale)

    n_lines = 0
    for x1, y1, x2, y2 in segments:
        if math.hypot(x2 - x1, y2 - y1) < min_len_px:
            continue
        msp.add_line(pt(x1, y1), pt(x2, y2), dxfattribs={"layer": "LINES"})
        n_lines += 1

    for points, closed in curves:
        msp.add_lwpolyline([pt(x, y) for x, y in points], close=closed,
                           dxfattribs={"layer": "CURVES"})

    for wd in words:
        height = max(0.5 * scale, 0.72 * wd["cap"] * scale)
        layer = "TEXT_REVIEW" if wd.get("review") else "TEXT"
        msp.add_text(wd["text"], dxfattribs={
            "layer": layer,
            "height": height,
            "rotation": wd["rotation"],
            "insert": pt(*wd["insert"]),
        })
        if wd.get("review"):
            # box the spot so a human can find and double-check it
            x, y, w, h = wd["x"], wd["y"], wd["w"], wd["h"]
            msp.add_lwpolyline(
                [pt(x, y), pt(x + w, y), pt(x + w, y + h), pt(x, y + h)],
                close=True, dxfattribs={"layer": "TEXT_REVIEW"})

    doc.saveas(path)
    return n_lines


# ── Full pipeline ──────────────────────────────────────────────────────────────

def convert(input_path, output_path=None, *,
            scale=1.0,
            do_page_crop=True,
            do_deskew=True,
            do_ocr=True,
            do_curves=True,
            ortho_snap=True,
            auto_scale=True,
            flag_review=True,
            review_conf=70,
            min_line_px=6.0,
            speck_px=8,
            ocr_min_conf=45,
            log=print):
    """Run the whole image -> DXF pipeline. Returns a stats dict."""
    if output_path is None:
        output_path = os.path.splitext(input_path)[0] + ".dxf"

    log(f"Reading {os.path.basename(input_path)} ...")
    gray = load_gray(input_path)

    if do_page_crop:
        quad = find_page_quad(gray)
        if quad is not None:
            warped = warp_to_page(gray, quad)
            if warped is not None:
                gray = warped
                log("Page detected - cropped and perspective-corrected.")

    gray = flatten_lighting(gray)

    if do_deskew:
        angle = estimate_skew(gray)
        if abs(angle) > 0.1:
            gray = rotate_bound(gray, angle)
            log(f"Deskewed by {angle:+.2f} degrees.")

    ink = binarize(gray)
    ink = remove_specks_and_blobs(ink, min_area=speck_px)

    words = []
    if do_ocr:
        if find_tesseract():
            log("Running OCR (horizontal + vertical passes) ...")
            words = ocr_words(gray, min_conf=ocr_min_conf)
            log(f"OCR found {len(words)} words.")
        else:
            log("WARNING: Tesseract not found - skipping OCR. "
                "Install it or set TESSERACT_CMD.")

    line_img = mask_words(ink, words) if words else ink

    log("Detecting line segments ...")
    segs = detect_segments(line_img)
    log(f"  {len(segs)} raw segments.")
    width = stroke_width(line_img)
    if ortho_snap and len(segs):
        segs = snap_orthogonal(segs)
    if len(segs):
        # offset tolerance ~ stroke width so the two edges of one pen stroke
        # collapse into a single centerline
        segs = merge_segments(segs, offset_tol=max(2.5, width + 1.0))
        log(f"  {len(segs)} after merging.")

    curves = []
    if do_curves and len(segs):
        curves = residual_curves(line_img, segs, width)
        log(f"  {len(curves)} curve/symbol outlines traced.")

    # dimension parsing, scale verification and review flagging
    units_feet = False
    for wd in words:
        wd["dim"] = parse_dimension(wd["text"])
        if flag_review and wd["conf"] < review_conf:
            wd["review"] = True
    n_dims = sum(1 for w in words if w["dim"])
    if n_dims:
        log(f"Parsed {n_dims} dimension labels "
            f"({', '.join(w['text'] for w in words if w['dim'])}).")
    if auto_scale and n_dims:
        ftpx = estimate_scale(words, segs)
        checked = [w for w in words if "dim_ok" in w]
        bad = [w for w in checked if not w["dim_ok"]]
        if flag_review:
            for w in bad:
                w["review"] = True
        if ftpx:
            scale = ftpx
            units_feet = True
            log(f"Scale verified against drawn lines: 1 px = {ftpx:.5f} ft "
                f"-> DXF output is in FEET. "
                f"{len(checked) - len(bad)} dimensions agree"
                + (f", {len(bad)} contradict and were flagged." if bad
                   else "."))
        else:
            log("Dimensions found but no consistent scale - "
                "output stays in pixel units.")
    n_review = sum(1 for w in words if w.get("review"))
    if n_review:
        log(f"{n_review} uncertain text items moved to red TEXT_REVIEW layer "
            f"(boxed on the drawing) - double-check those by hand.")

    n_lines = write_dxf(output_path, gray.shape[0], segs, curves, words,
                        scale=scale, min_len_px=min_line_px,
                        units_feet=units_feet)
    log(f"Wrote {output_path}  ({n_lines} lines, {len(curves)} polylines, "
        f"{len(words)} text entities)")
    return dict(output=output_path, lines=n_lines, curves=len(curves),
                words=len(words), review=n_review,
                units="feet" if units_feet else "pixels", size=gray.shape)


def render_preview(dxf_path, png_path, dpi=150):
    """Render the DXF to a PNG for a quick visual check (needs matplotlib)."""
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    from ezdxf.addons.drawing import RenderContext, Frontend
    from ezdxf.addons.drawing.matplotlib import MatplotlibBackend

    doc = ezdxf.readfile(dxf_path)
    fig = plt.figure()
    ax = fig.add_axes([0, 0, 1, 1])
    ctx = RenderContext(doc)
    Frontend(ctx, MatplotlibBackend(ax)).draw_layout(doc.modelspace(),
                                                     finalize=True)
    fig.savefig(png_path, dpi=dpi, facecolor="black")
    plt.close(fig)


def main():
    ap = argparse.ArgumentParser(
        description="Convert a photo/scan of a drawing to a layered DXF.")
    ap.add_argument("input", help="input image (jpg/png/tif...)")
    ap.add_argument("-o", "--output", help="output .dxf path")
    ap.add_argument("--scale", type=float, default=1.0,
                    help="drawing units per pixel (default 1.0)")
    ap.add_argument("--no-crop", action="store_true",
                    help="skip page detection / perspective correction")
    ap.add_argument("--no-deskew", action="store_true", help="skip deskewing")
    ap.add_argument("--no-ocr", action="store_true", help="skip text OCR")
    ap.add_argument("--no-curves", action="store_true",
                    help="straight lines only, skip curve tracing")
    ap.add_argument("--no-ortho", action="store_true",
                    help="don't snap near-horizontal/vertical lines to axis")
    ap.add_argument("--no-autoscale", action="store_true",
                    help="don't verify dimensions / auto-scale output to feet")
    ap.add_argument("--no-review", action="store_true",
                    help="don't flag uncertain text on the TEXT_REVIEW layer")
    ap.add_argument("--review-conf", type=float, default=70,
                    help="OCR confidence below this is flagged (default 70)")
    ap.add_argument("--min-line", type=float, default=6.0,
                    help="drop lines shorter than this many pixels")
    ap.add_argument("--speck", type=int, default=8,
                    help="remove ink specks smaller than this area (px)")
    ap.add_argument("--preview", metavar="PNG",
                    help="also render a PNG preview of the DXF")
    args = ap.parse_args()

    convert(args.input, args.output,
            scale=args.scale,
            do_page_crop=not args.no_crop,
            do_deskew=not args.no_deskew,
            do_ocr=not args.no_ocr,
            do_curves=not args.no_curves,
            ortho_snap=not args.no_ortho,
            auto_scale=not args.no_autoscale,
            flag_review=not args.no_review,
            review_conf=args.review_conf,
            min_line_px=args.min_line,
            speck_px=args.speck)
    if args.preview:
        render_preview(args.output or
                       os.path.splitext(args.input)[0] + ".dxf", args.preview)
        print(f"Preview saved to {args.preview}")


if __name__ == "__main__":
    main()
