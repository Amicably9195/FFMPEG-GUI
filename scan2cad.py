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


def crop_to_page(gray):
    """Fallback page finder: crop to the largest bright (paper) region.
    Cuts away desks, keyboards and backdrop when the quad detector fails."""
    blur = cv2.GaussianBlur(gray, (0, 0), 5)
    _, bright = cv2.threshold(blur, 0, 255,
                              cv2.THRESH_BINARY + cv2.THRESH_OTSU)
    n, _, stats, _ = cv2.connectedComponentsWithStats(bright, connectivity=8)
    if n < 2:
        return gray, False
    i = 1 + int(np.argmax(stats[1:, 4]))
    x, y, w, h, area = stats[i]
    if area < 0.30 * gray.size or w * h > 0.97 * gray.size:
        return gray, False
    pad = 5
    y0, x0 = max(0, y - pad), max(0, x - pad)
    y1 = min(gray.shape[0], y + h + pad)
    x1 = min(gray.shape[1], x + w + pad)
    return gray[y0:y1, x0:x1], True


def speckle_ratio(ink):
    """Fraction of ink components that are tiny specks - a dirtiness score."""
    n, _, stats, _ = cv2.connectedComponentsWithStats(ink, connectivity=8)
    if n <= 1:
        return 0.0, 0
    areas = stats[1:, 4]
    return float((areas < 20).sum()) / len(areas), len(areas)


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


def binarize(gray, sensitivity=15):
    """Return ink mask: 255 where there is ink, 0 for paper.
    Lower sensitivity catches fainter lines (and more noise)."""
    thr = cv2.adaptiveThreshold(gray, 255, cv2.ADAPTIVE_THRESH_GAUSSIAN_C,
                                cv2.THRESH_BINARY_INV, 35, sensitivity)
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
    Words on the same OCR line are grouped into one label (a drafter writes
    'LOWER CONCRETE YARD' as one clean label, not three stacked words);
    dimension values stay solo so they can be verified individually.
    Each label: dict(text, conf, x, y, w, h  [orig frame px],
                     insert (px point), rotation [deg CAD])."""
    h0, w0 = gray.shape
    img = gray if rotate_code is None else cv2.rotate(gray, rotate_code)
    data = pytesseract.image_to_data(img, config="--psm 11",
                                     output_type=pytesseract.Output.DICT)
    raw = []
    for i, text in enumerate(data["text"]):
        text = text.strip()
        conf = float(data["conf"][i])
        if not text or conf < 0:
            continue
        if not any(ch.isalnum() for ch in text):
            continue
        x, y = data["left"][i], data["top"][i]
        w, h = data["width"][i], data["height"][i]
        if h < 6 or h > 200 or w < 3:
            continue
        raw.append((
            (data["block_num"][i], data["par_num"][i], data["line_num"][i]),
            data["word_num"][i], x, y, w, h, text, conf))
    raw.sort(key=lambda r: (r[0], r[1]))

    groups, run, run_key = [], [], None
    for key, _, x, y, w, h, text, conf in raw:
        is_dim = parse_dimension(text) is not None
        gap = run and (x - (run[-1][0] + run[-1][2])) > 1.5 * max(h, run[-1][3])
        if run and (key != run_key or is_dim or run[-1][6] or gap):
            groups.append(run)
            run = []
        run.append((x, y, w, h, text, conf, is_dim))
        run_key = key
    if run:
        groups.append(run)

    words = []
    for g in groups:
        conf = min(m[5] for m in g)
        if conf < min_conf:
            continue
        text = " ".join(m[4] for m in g)
        x = min(m[0] for m in g)
        y = min(m[1] for m in g)
        w = max(m[0] + m[2] for m in g) - x
        h = max(m[1] + m[3] for m in g) - y
        cap = float(np.median([m[3] for m in g]))
        # Map box and reading-orientation baseline point back to the
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
        words.append(dict(text=text, conf=conf, x=bx, y=by, w=bw, h=bh,
                          insert=insert, rotation=cad_rotation, cap=cap))
    return words


def _overlap(a, b):
    ix = max(0, min(a["x"] + a["w"], b["x"] + b["w"]) - max(a["x"], b["x"]))
    iy = max(0, min(a["y"] + a["h"], b["y"] + b["h"]) - max(a["y"], b["y"]))
    inter = ix * iy
    union = a["w"] * a["h"] + b["w"] * b["h"] - inter
    return inter / union if union else 0.0


def ocr_words(gray, min_conf=30, vertical=True):
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
        if inches > 12 and "." in m.group(1):
            # 40.00" is a misread foot mark - nobody writes 40 inches
            # with two decimals on a drawing
            return inches
        return inches / 12.0 if inches > 0 else None
    # 26-2" is a feet-inches label whose foot mark the OCR dropped, and
    # 26'-2 is one whose inch mark was dropped. Exactly one mark missing is
    # unambiguously feet-inches; bare "26-2" (a grid/room ref) is not
    # touched - one mark must survive.
    m = re.fullmatch(r"[±+\-]?(\d{1,3})(['!]?)-(\d{1,2}(?:\.\d+)?)(\"?)", t)
    if m and (m.group(2) or m.group(4)):
        inches = float(m.group(3))
        if inches < 12:  # a real inches field is 0-11
            return float(m.group(1)) + inches / 12.0
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


def estimate_scale(words, segs, tolerance=0.06, extra_segs=None,
                   img_shape=None):
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
    if len(dims) < 2 or len(segs) < 1:
        return None
    # measurement geometry: the merged display lines plus edge-detected
    # segments (which see bold property lines as single pieces). The pool
    # must stay SPARSE - with too many candidate spans every label matches
    # any scale and the consensus is meaningless.
    meas = segs
    if extra_segs is not None and len(extra_segs):
        meas = np.vstack([meas, extra_segs]) if len(meas) else extra_segs
    if len(meas) == 0:
        return None
    mlen = np.hypot(meas[:, 2] - meas[:, 0], meas[:, 3] - meas[:, 1])
    if img_shape is not None:
        # the sheet border frame is not drawing geometry - long lines
        # hugging the image edge must not pair with dimension labels
        h, w = img_shape[:2]
        mx = (meas[:, 0] + meas[:, 2]) / 2
        my = (meas[:, 1] + meas[:, 3]) / 2
        near_edge = ((mx < 0.04 * w) | (mx > 0.96 * w) |
                     (my < 0.04 * h) | (my > 0.96 * h))
        keep = ~(near_edge & (mlen > 0.5 * min(h, w)))
        meas, mlen = meas[keep], mlen[keep]
    if len(meas) == 0:
        return None
    mang = np.degrees(np.arctan2(meas[:, 3] - meas[:, 1],
                                 meas[:, 2] - meas[:, 0])) % 180.0

    cands = []  # (word index, implied ft/px, distance to line)
    per_label = []
    for wi, w in enumerate(dims):
        cx, cy = w["x"] + w["w"] / 2.0, w["y"] + w["h"] / 2.0
        c = np.array([cx, cy])
        vertical = w["rotation"] in (90, 270)
        # the measured line is always longer than the label describing it -
        # a leftover text stroke must never pass as the measured span
        reading_len = w["h"] if vertical else w["w"]
        for i in range(len(meas)):
            if mlen[i] < max(30, 1.2 * reading_len):
                continue
            ang_ok = (70 < mang[i] < 110) if vertical else \
                     (mang[i] < 20 or mang[i] > 160)
            if not ang_ok:
                continue
            # a dimension label sits centered on the span it measures:
            # require the label over the middle of the span and close to it
            a = meas[i, :2]
            d = (meas[i, 2:] - a) / mlen[i]
            n = np.array([-d[1], d[0]])
            # the label must sit somewhere along the span (corner labels sit
            # right at the end, so allow slight overhang)
            frac = float((c - a) @ d) / mlen[i]
            if not -0.10 <= frac <= 1.10:
                continue
            # surveys often write the value well off the measured line, so
            # allow real offset
            perp = abs(float((c - a) @ n))
            if perp > max(8.0 * w["cap"], 150.0):
                continue
            per_label.append((wi, w["dim"] / mlen[i], perp,
                              float(mlen[i]), float(mang[i])))
    # fragments of one broken line must not vote alongside the full line:
    # per label, keep only the longest candidate among collinear ones
    # (same orientation, same offset from the label)
    per_label.sort(key=lambda t: -t[3])
    kept = []
    for cand in per_label:
        dup = any(k[0] == cand[0]
                  and abs(k[2] - cand[2]) <= 10.0
                  and min(abs(k[4] - cand[4]),
                          180.0 - abs(k[4] - cand[4])) < 3.0
                  for k in kept)
        if not dup:
            kept.append(cand)
    cands = [(wi, s, perp) for wi, s, perp, _, _ in kept]
    if not cands:
        return None

    # densest cluster of implied scales; rank by total feet of evidence
    # first - the principal lot lines (40' + 100') must outweigh any
    # coincidental cluster of small offset labels - then by supporting
    # word count and proximity
    clusters = []
    for _, s0, _ in cands:
        members = [c for c in cands if abs(c[1] / s0 - 1.0) <= tolerance]
        support = {c[0] for c in members}
        if len(support) < 2:
            continue
        feet = sum(dims[i]["dim"] for i in support)
        score = (feet, len(support), -min(c[2] for c in members))
        clusters.append((score, s0, members))
    if not clusters:
        return None
    clusters.sort(key=lambda t: t[0], reverse=True)
    best_score, best_s0, best_members = clusters[0]
    # honesty check: if a second, scale-incompatible cluster has comparable
    # evidence, the drawing is ambiguous - better no scale than a wrong one
    for score, s0, _ in clusters[1:]:
        if abs(s0 / best_s0 - 1.0) > 3 * tolerance and \
                score[0] >= 0.7 * best_score[0]:
            return None
    support = {c[0] for c in best_members}
    feet = sum(dims[i]["dim"] for i in support)
    if len(support) < 3 and feet < 60:
        return None
    scale = float(np.median([c[1] for c in best_members]))

    for wi, w in enumerate(dims):
        mine = [c for c in cands if c[0] == wi]
        if mine:
            w["dim_ok"] = any(abs(c[1] / scale - 1.0) <= 1.5 * tolerance
                              for c in mine)
    return scale


def _collinear_groups(segs, angle_tol=3.0, offset_tol=4.0):
    """Group segments that lie on the same infinite line (a dimension line
    broken by its own text is several collinear pieces). Yields
    (indices, endpoint_a, endpoint_b, direction) for each group's full span."""
    n = len(segs)
    ang = np.degrees(np.arctan2(segs[:, 3] - segs[:, 1],
                                segs[:, 2] - segs[:, 0])) % 180.0
    used = np.zeros(n, dtype=bool)
    order = np.argsort(ang)
    groups = []

    def emit(band):
        band = band[~used[band]]
        if len(band) == 0:
            return
        a = math.radians(np.median(np.where(ang[band] > 170,
                                            ang[band] - 180, ang[band])))
        d = np.array([math.cos(a), math.sin(a)])
        nvec = np.array([-d[1], d[0]])
        mid = (segs[band][:, :2] + segs[band][:, 2:]) / 2
        rho = mid @ nvec
        o = np.argsort(rho)
        k = 0
        while k < len(o):
            m = k
            while m + 1 < len(o) and rho[o[m + 1]] - rho[o[m]] < offset_tol:
                m += 1
            grp = band[o[k:m + 1]]
            k = m + 1
            used[grp] = True
            t = np.concatenate([segs[grp][:, :2] @ d, segs[grp][:, 2:] @ d])
            r = float(np.mean(rho[np.searchsorted(band, grp)])) \
                if False else float(np.mean((segs[grp][:, :2]
                                             + segs[grp][:, 2:]) / 2 @ nvec))
            base = r * nvec
            pa = base + t.min() * d
            pb = base + t.max() * d
            groups.append((grp, pa, pb, d))

    i = 0
    while i < len(order):
        a0 = ang[order[i]]
        j = i
        while j < len(order) and ang[order[j]] - a0 <= angle_tol:
            j += 1
        emit(order[i:j])
        i = j
    wrap = np.where((ang < angle_tol) | (ang > 180 - angle_tol))[0]
    if len(wrap):
        emit(wrap)
    return groups


def pair_dimensions(words, segs, scale=None, tol=0.10):
    """Recognize real dimension strings: a parsed dimension label sitting ON
    the line it annotates. The line is a COLLINEAR GROUP, so a dimension
    line broken by its own text still pairs. When a scale is known the
    pairing must also agree with it. Returns [(word, (x1,y1,x2,y2))] -
    anything not confidently paired stays plain line + text (no guessing)."""
    if len(segs) == 0:
        return []
    groups = _collinear_groups(segs)
    spans = []
    for grp, pa, pb, d in groups:
        span = float(np.hypot(*(pb - pa)))
        ang = math.degrees(math.atan2(d[1], d[0])) % 180.0
        spans.append((grp, pa, pb, d, span, ang))
    pairs = []
    used_groups = set()
    for w in words:
        if not _verifiable(w):
            continue
        c = np.array([w["x"] + w["w"] / 2.0, w["y"] + w["h"] / 2.0])
        vertical = w["rotation"] in (90, 270)
        reading_len = w["h"] if vertical else w["w"]
        best = None
        for gi, (grp, pa, pb, d, span, ang) in enumerate(spans):
            if gi in used_groups or span < max(30.0, 1.05 * reading_len):
                continue
            ang_ok = (70 < ang < 110) if vertical else (ang < 20 or ang > 160)
            if not ang_ok:
                continue
            n = np.array([-d[1], d[0]])
            frac = float((c - pa) @ d) / span
            perp = abs(float((c - pa) @ n))
            if not 0.12 <= frac <= 0.88 or perp > max(2.5 * w["cap"], 18.0):
                continue
            if scale and abs((w["dim"] / span) / scale - 1.0) > tol:
                continue
            if best is None or perp < best[0]:
                best = (perp, gi, pa, pb)
        if best is not None:
            _, gi, pa, pb = best
            used_groups.add(gi)
            pairs.append((w, (float(pa[0]), float(pa[1]),
                              float(pb[0]), float(pb[1])),
                          [int(k) for k in spans[gi][0]]))
    return pairs


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

_NB = ((-1, -1), (0, -1), (1, -1), (-1, 0), (1, 0), (-1, 1), (0, 1), (1, 1))


def _trace_skeleton(skel):
    """Walk a 1-px skeleton into pixel paths, breaking at junctions so every
    stroke centerline becomes one path with shared junction endpoints."""
    ys, xs = np.nonzero(skel)
    pts = set(zip(xs.tolist(), ys.tolist()))

    def nbrs(p):
        x, y = p
        return [(x + dx, y + dy) for dx, dy in _NB if (x + dx, y + dy) in pts]

    neighbors = {p: nbrs(p) for p in pts}
    nodes = {p for p, nb in neighbors.items() if len(nb) != 2}
    visited = set()
    paths = []

    def walk(start, nxt):
        path = [start, nxt]
        visited.add((start, nxt))
        visited.add((nxt, start))
        prev, cur = start, nxt
        while cur not in nodes:
            steps = [q for q in neighbors[cur]
                     if q != prev and (cur, q) not in visited]
            if not steps:
                break
            q = steps[0]
            visited.add((cur, q))
            visited.add((q, cur))
            path.append(q)
            prev, cur = cur, q
        return path

    for n in nodes:
        for m in neighbors[n]:
            if (n, m) not in visited:
                paths.append(walk(n, m))
    # closed loops with no junctions (circles): walk from any leftover pixel
    for p in pts:
        if len(neighbors[p]) == 2 and \
                all((p, q) not in visited for q in neighbors[p]):
            paths.append(walk(p, neighbors[p][0]))
    return paths


def _fit_circle(pts):
    """Least-squares circle fit (Kasa). Returns (cx, cy, r, max_residual)."""
    a = np.c_[2.0 * pts[:, 0], 2.0 * pts[:, 1], np.ones(len(pts))]
    b = (pts ** 2).sum(axis=1)
    try:
        sol, *_ = np.linalg.lstsq(a, b, rcond=None)
    except np.linalg.LinAlgError:
        return None
    cx, cy = float(sol[0]), float(sol[1])
    r2 = float(sol[2]) + cx * cx + cy * cy
    if r2 <= 0:
        return None
    r = math.sqrt(r2)
    resid = np.abs(np.hypot(pts[:, 0] - cx, pts[:, 1] - cy) - r)
    return cx, cy, r, float(resid.max())


def _try_arc(pts, closed):
    """If the traced path is faithfully a circle or arc, return the entity:
    ('circle', cx, cy, r) or ('arc', cx, cy, r, p_start, p_end, p_mid).
    Faithful reconstruction only - a sloppy fit returns None."""
    if len(pts) < 8:
        return None
    fit = _fit_circle(pts.astype(np.float64))
    if fit is None:
        return None
    cx, cy, r, resid = fit
    lim = max(2.0, 0.035 * r)
    if not 6.0 <= r <= 3000.0 or resid > lim:
        return None
    # confidence: how tightly the traced pixels fit the ideal circle
    conf = float(max(0.0, min(1.0, 1.0 - resid / lim)))
    ang = np.unwrap(np.arctan2(pts[:, 1] - cy, pts[:, 0] - cx))
    span = math.degrees(abs(float(ang[-1] - ang[0])))
    if closed or span >= 355.0:
        return ("circle", cx, cy, r, conf)
    if span < 40.0:
        return None  # too shallow to assert an arc faithfully
    return ("arc", cx, cy, r, tuple(pts[0]), tuple(pts[-1]),
            tuple(pts[len(pts) // 2]), conf)


def detect_circles(ink, min_r=8, max_r=300):
    """Find isolated drawn circles deterministically: a circle standing on
    its own is a single connected ink component whose pixels all sit at one
    radius from one center, covering (almost) the full turn. Every test is
    against the actual pixels - no candidate voting, no guessing.
    Returns (circle entities, ink with those components erased)."""
    n, comp, stats, _ = cv2.connectedComponentsWithStats(ink, connectivity=8)
    accepted = []
    out = ink.copy()
    for i in range(1, n):
        x, y, w, h, area = stats[i]
        if (w < 2 * min_r - 4 or h < 2 * min_r - 4
                or w > 2 * max_r or h > 2 * max_r):
            continue
        if not 0.75 <= w / float(h) <= 1.33:
            continue
        ys, xs = np.nonzero(comp[y:y + h, x:x + w] == i)
        pts = np.column_stack([xs, ys]).astype(np.float64)
        fit = _fit_circle(pts)
        if fit is None:
            continue
        cx, cy, r, _ = fit
        if not min_r <= r <= max_r:
            continue
        dist = np.hypot(pts[:, 0] - cx, pts[:, 1] - cy)
        # a ring, not a disk or a glyph: nearly all pixels at one radius
        p95 = np.percentile(np.abs(dist - r), 95)
        ring_lim = max(3.5, 0.10 * r)
        if p95 > ring_lim:
            continue
        # nearly the full turn present
        ang = np.arctan2(pts[:, 1] - cy, pts[:, 0] - cx)
        filled = len(np.unique((ang // (2 * np.pi / 36)).astype(int)))
        if filled < 33:
            continue
        # confidence: ring tightness x completeness of the turn
        conf = float(max(0.0, 1.0 - p95 / ring_lim) * (filled / 36.0))
        accepted.append(("circle", cx + x, cy + y, r, conf))
        out[comp == i] = 0
    return accepted, out


def _arc_span(arc):
    """Angular coverage (deg) of an ('arc', cx, cy, r, p1, p2, pm, conf)."""
    cx, cy, p1, p2, pm = arc[1], arc[2], arc[4], arc[5], arc[6]

    def ang(p):
        return math.degrees(math.atan2(p[1] - cy, p[0] - cx)) % 360.0
    a1, a2, am = ang(p1), ang(p2), ang(pm)
    sweep = (a2 - a1) % 360.0
    if (am - a1) % 360.0 > sweep:
        sweep = 360.0 - sweep
    return sweep


def _merge_rounds(rounds):
    """A circle traced as two half-arcs must come back as ONE circle:
    arcs sharing a center and radius whose spans cover most of the turn
    merge into a circle entity. Tiny letter-scrap arcs are dropped."""
    out = [r for r in rounds if r[0] == "circle" and r[3] >= 8.0]
    arcs = [r for r in rounds if r[0] == "arc"]
    used = [False] * len(arcs)
    for i, a in enumerate(arcs):
        if used[i]:
            continue
        group = [a]
        used[i] = True
        for j in range(i + 1, len(arcs)):
            b = arcs[j]
            if (not used[j] and abs(a[1] - b[1]) < 6 and abs(a[2] - b[2]) < 6
                    and abs(a[3] - b[3]) < 4):
                group.append(b)
                used[j] = True
        radius = float(np.mean([g[3] for g in group]))
        if (len(group) > 1 and radius >= 8.0
                and sum(_arc_span(g) for g in group) > 300.0):
            out.append(("circle",
                        float(np.mean([g[1] for g in group])),
                        float(np.mean([g[2] for g in group])), radius,
                        float(min(g[7] for g in group))))
            continue
        for g in group:
            # a faithful arc entity must be big enough to not be a glyph
            if g[3] >= 12.0 and g[3] * math.radians(_arc_span(g)) >= 45.0:
                out.append(g)
    return out


def _dominant_straight(pts, tol):
    """Longest contiguous run of polyline vertices that is collinear within
    tol. Returns (i, j) inclusive, or None. Catches a straight line carrying
    a small tick/arrow hook at one end (dimension and leader lines)."""
    n = len(pts)
    best = None
    for i in range(n - 1):
        for j in range(n - 1, i, -1):
            a, b = pts[i], pts[j]
            chord = np.hypot(*(b - a))
            if chord < 1:
                continue
            d = (b - a) / chord
            nv = np.array([-d[1], d[0]])
            if np.max(np.abs((pts[i:j + 1] - a) @ nv)) <= tol:
                if best is None or chord > best[0]:
                    best = (chord, i, j)
                break
    return None if best is None else (best[1], best[2])


def vectorize_centerlines(ink, min_len=6.0, epsilon=1.4):
    """Thin ink to 1-px skeletons and trace single centerlines: one stroke on
    paper -> one LINE / one polyline, no doubled edges, no outlines.
    Circles and arcs are recognized and returned as true entities.
    Returns (segments Nx4, polylines [(points Nx2, closed)], round_entities)."""
    skel = cv2.ximgproc.thinning(ink)
    segments, polys, rounds = [], [], []
    for path in _trace_skeleton(skel):
        if len(path) < 2:
            continue
        arr = np.asarray(path, dtype=np.int32).reshape(-1, 1, 2)
        closed = path[0] == path[-1] and len(path) > 3
        approx = cv2.approxPolyDP(arr, epsilon, closed).reshape(-1, 2)
        if closed and len(approx) >= 3:
            ent = _try_arc(arr.reshape(-1, 2), True)
            if ent:
                rounds.append(ent)
            else:
                polys.append((approx.astype(np.float64), True))
            continue
        if len(approx) == 2:
            (x1, y1), (x2, y2) = approx
            segments.append((float(x1), float(y1), float(x2), float(y2)))
        elif len(approx) > 2:
            # near-straight paths become dead-straight lines: these drawings
            # came out of CAD, so a long stroke bowed slightly by paper curl
            # or lens distortion is meant to be straight
            p1, p2 = approx[0].astype(np.float64), approx[-1].astype(np.float64)
            chord = np.linalg.norm(p2 - p1)
            dev = 0.0
            if chord > 1:
                d = (p2 - p1) / chord
                n = np.array([-d[1], d[0]])
                dev = float(np.max(np.abs((approx - p1) @ n)))
            straight_tol = max(2.5, 0.015 * chord)
            if chord >= min_len and dev <= straight_tol:
                segments.append((p1[0], p1[1], p2[0], p2[1]))
            else:
                ent = _try_arc(arr.reshape(-1, 2), False)
                if ent:
                    rounds.append(ent)
                    continue
                # a long straight run carrying only a SMALL end tick/arrow
                # (dimension and leader lines): emit the straight run as a
                # LINE and keep the small hook faithfully. Only fires when
                # the leftover ends are tick-sized - real geometry is never
                # trimmed, so wall corners are untouched.
                run = _dominant_straight(approx.astype(np.float64),
                                         straight_tol)
                emitted = False
                if run is not None:
                    i0, j0 = run
                    ra = approx[i0].astype(np.float64)
                    rb = approx[j0].astype(np.float64)
                    ends = [approx[:i0 + 1], approx[j0:]]
                    end_len = max(
                        (np.hypot(*(e[-1] - e[0])) if len(e) > 1 else 0.0)
                        for e in ends)
                    tick_max = max(14.0, 0.06 * chord)
                    if (np.hypot(*(rb - ra)) >= max(min_len, 0.85 * chord)
                            and 0 < end_len <= tick_max):
                        segments.append((ra[0], ra[1], rb[0], rb[1]))
                        for head, tail in ((0, i0), (j0, len(approx) - 1)):
                            if tail - head >= 1 and np.hypot(
                                    *(approx[tail] - approx[head])) >= min_len:
                                polys.append(
                                    (approx[head:tail + 1].astype(np.float64),
                                     False))
                        emitted = True
                if not emitted:
                    polys.append((approx.astype(np.float64), False))
    return ((np.array(segments) if segments else np.empty((0, 4))),
            polys, _merge_rounds(rounds))


def _feature_size(points):
    lo = points.min(axis=0)
    hi = points.max(axis=0)
    return float(np.hypot(*(hi - lo)))


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


def detect_dashed(segs, min_run=4, max_dash=45.0, max_gap=35.0):
    """Recognize dashed lines: a run of short collinear segments with a
    regular dash/gap rhythm becomes ONE line carrying the DASHED linetype.
    Irregular clusters are left untouched - no rhythm, no claim.
    Returns (dashed Nx4, remaining solid segs)."""
    if len(segs) == 0:
        return np.empty((0, 4)), segs
    dx = segs[:, 2] - segs[:, 0]
    dy = segs[:, 3] - segs[:, 1]
    ang = np.degrees(np.arctan2(dy, dx)) % 180.0
    used = np.zeros(len(segs), dtype=bool)
    dashed = []

    def scan_band(band):
        band = band[~used[band]]
        if len(band) < min_run:
            return
        a = math.radians(np.median(np.where(ang[band] > 170,
                                            ang[band] - 180, ang[band])))
        d = np.array([math.cos(a), math.sin(a)])
        nvec = np.array([-d[1], d[0]])
        p1 = segs[band][:, :2]
        p2 = segs[band][:, 2:]
        rho = ((p1 + p2) / 2) @ nvec
        t1, t2 = p1 @ d, p2 @ d
        tmin, tmax = np.minimum(t1, t2), np.maximum(t1, t2)
        order = np.argsort(rho)
        k = 0
        while k < len(order):
            m = k
            while m + 1 < len(order) and rho[order[m + 1]] - rho[order[m]] < 3.0:
                m += 1
            grp = band[order[k:m + 1]]
            gt = np.argsort(tmin[order[k:m + 1]])
            idx = grp[gt]
            k = m + 1
            # walk runs of dash-like members
            run = []
            def flush():
                if len(run) >= min_run:
                    lens = [tmax_of[j] - tmin_of[j] for j in run]
                    gaps = [tmin_of[run[j + 1]] - tmax_of[run[j]]
                            for j in range(len(run) - 1)]
                    if (np.std(lens) <= 0.7 * max(1.0, np.mean(lens))
                            and np.std(gaps) <= 0.7 * max(1.0, np.mean(gaps))):
                        r = float(np.mean([rho_of[j] for j in run]))
                        s0, s1 = tmin_of[run[0]], tmax_of[run[-1]]
                        dashed.append(np.concatenate([r * nvec + s0 * d,
                                                      r * nvec + s1 * d]))
                        for j in run:
                            used[j] = True
                run.clear()
            tmin_of = {j: float(min(segs[j][0] * d[0] + segs[j][1] * d[1],
                                    segs[j][2] * d[0] + segs[j][3] * d[1]))
                       for j in idx}
            tmax_of = {j: float(max(segs[j][0] * d[0] + segs[j][1] * d[1],
                                    segs[j][2] * d[0] + segs[j][3] * d[1]))
                       for j in idx}
            rho_of = {j: float(((segs[j][:2] + segs[j][2:]) / 2) @ nvec)
                      for j in idx}
            for j in idx:
                seg_len = tmax_of[j] - tmin_of[j]
                if seg_len > max_dash:
                    flush()
                    continue
                if run:
                    gap = tmin_of[j] - tmax_of[run[-1]]
                    if not 2.0 <= gap <= max_gap:
                        flush()
                run.append(j)
            flush()

    order = np.argsort(ang)
    i = 0
    while i < len(order):
        a0 = ang[order[i]]
        j = i
        while j < len(order) and ang[order[j]] - a0 <= 2.0:
            j += 1
        scan_band(order[i:j])
        i = j
    wrap = np.where((ang < 2.0) | (ang > 178.0))[0]
    if len(wrap):
        scan_band(wrap)
    solid = segs[~used]
    return (np.array(dashed) if dashed else np.empty((0, 4))), solid


def snap_topology(segs, tol=4.0):
    """Heal junction gaps left by skeleton thinning: endpoints that belong
    together meet exactly. Two passes - (1) endpoint clusters within tol
    merge to their centroid (L-corners), (2) remaining endpoints within tol
    of another line's interior are projected onto it (T-joints). Endpoints
    only ever move by <= tol, and never more than a third of their own
    segment's length, so geometry is corrected, not redrawn."""
    n = len(segs)
    if n == 0:
        return segs
    pts = np.vstack([segs[:, :2], segs[:, 2:]]).astype(np.float64)
    seg_of = np.concatenate([np.arange(n), np.arange(n)])
    seg_len = np.hypot(segs[:, 2] - segs[:, 0], segs[:, 3] - segs[:, 1])
    max_move = np.minimum(tol, seg_len[seg_of] / 3.0)

    # pass 1: corner clustering via grid hash
    cell = {}
    for i, (x, y) in enumerate(pts):
        cell.setdefault((int(x // tol), int(y // tol)), []).append(i)
    snapped = pts.copy()
    clustered = np.zeros(len(pts), dtype=bool)
    done = np.zeros(len(pts), dtype=bool)
    for i in range(len(pts)):
        if done[i]:
            continue
        x, y = pts[i]
        kx, ky = int(x // tol), int(y // tol)
        group = [j for dx in (-1, 0, 1) for dy in (-1, 0, 1)
                 for j in cell.get((kx + dx, ky + dy), [])
                 if not done[j]
                 and abs(pts[j, 0] - x) <= tol and abs(pts[j, 1] - y) <= tol]
        if len(group) > 1:
            c = pts[group].mean(axis=0)
            for j in group:
                if np.hypot(*(pts[j] - c)) <= max_move[j]:
                    snapped[j] = c
                    clustered[j] = True
                done[j] = True
        else:
            done[i] = True

    # pass 2: T-joints - project leftover endpoints onto nearby interiors
    a = snapped[:n]
    b = snapped[n:]
    ab = np.hstack([b - a])
    l2 = np.maximum((ab ** 2).sum(axis=1), 1e-9)
    todo = np.where(~clustered)[0]
    for start in range(0, len(todo), 512):
        idx = todo[start:start + 512]
        p = snapped[idx]
        diff = p[:, None, :] - a[None, :, :]
        t = (diff * ab[None, :, :]).sum(-1) / l2[None, :]
        q = a[None, :, :] + t[..., None] * ab[None, :, :]
        d = np.linalg.norm(p[:, None, :] - q, axis=-1)
        bad = (t < 0.08) | (t > 0.92)
        d[bad] = 1e9
        d[np.arange(len(idx)), seg_of[idx]] = 1e9
        j = d.argmin(axis=1)
        dm = d[np.arange(len(idx)), j]
        ok = dm <= np.minimum(tol, max_move[idx])
        snapped[idx[ok]] = q[np.arange(len(idx))[ok], j[ok]]

    return np.hstack([snapped[:n], snapped[n:]])


def snap_lines_to_polylines(segs, polys, tol=4.0):
    """Close line-to-polyline junctions: a line endpoint within tol of a
    polyline vertex snaps onto that vertex (a wall meeting a curved/traced
    boundary). Endpoints move at most tol, and never past a third of their
    own segment - correction, not redrawing. Mutates segs in place."""
    if len(segs) == 0 or not polys:
        return segs
    verts = np.vstack([p for p, _ in polys]) if polys else np.empty((0, 2))
    if len(verts) == 0:
        return segs
    seg_len = np.hypot(segs[:, 2] - segs[:, 0], segs[:, 3] - segs[:, 1])
    for i in range(len(segs)):
        cap = min(tol, seg_len[i] / 3.0)
        for e0, e1 in ((0, 2), (2, 0)):  # each endpoint; e1 is the far end
            p = segs[i, [e0, e0 + 1]]
            dv = np.abs(verts - p).max(axis=1)
            j = int(np.argmin(dv))
            if dv[j] <= cap and np.hypot(*(verts[j] - p)) <= cap:
                segs[i, [e0, e0 + 1]] = verts[j]
    return segs


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
              min_len_px=6.0, units_feet=False, rounds=(), dashed=(),
              dims=()):
    doc = ezdxf.new("R2010", setup=True)
    doc.layers.add("LINES", color=7)
    doc.layers.add("CURVES", color=4)
    doc.layers.add("TEXT", color=3)
    # uncertain text lives on a hidden layer: the drawing opens clean, and
    # turning TEXT_REVIEW on shows the red marks for proofreading
    doc.layers.add("TEXT_REVIEW", color=1).off()
    if dims:
        doc.layers.add("DIMENSIONS", color=2)
    if units_feet:
        doc.header["$INSUNITS"] = 2  # feet
    # a real font instead of the default stick font
    doc.styles.add("D2CAD", font="arial.ttf")
    msp = doc.modelspace()

    def pt(x, y):
        return (x * scale, (img_h - y) * scale)

    n_lines = 0
    for x1, y1, x2, y2 in segments:
        if math.hypot(x2 - x1, y2 - y1) < min_len_px:
            continue
        msp.add_line(pt(x1, y1), pt(x2, y2), dxfattribs={"layer": "LINES"})
        n_lines += 1

    if len(dashed):
        # make the dash pattern visible at this drawing's size
        doc.header["$LTSCALE"] = max(0.5, 20.0 * scale)
        for x1, y1, x2, y2 in dashed:
            msp.add_line(pt(x1, y1), pt(x2, y2),
                         dxfattribs={"layer": "LINES",
                                     "linetype": "DASHED"})

    for points, closed in curves:
        msp.add_lwpolyline([pt(x, y) for x, y in points], close=closed,
                           dxfattribs={"layer": "CURVES"})

    for ent in rounds:
        center = pt(ent[1], ent[2])
        radius = ent[3] * scale
        if ent[0] == "circle":
            msp.add_circle(center, radius, dxfattribs={"layer": "CURVES"})
        else:  # arc: pick the sweep that passes through the traced midpoint
            def angle(p):
                x, y = pt(p[0], p[1])
                return math.degrees(math.atan2(y - center[1],
                                               x - center[0])) % 360.0
            a1, a2, am = angle(ent[4]), angle(ent[5]), angle(ent[6])
            if not ((a2 - a1) % 360.0) >= ((am - a1) % 360.0):
                a1, a2 = a2, a1
            msp.add_arc(center, radius, a1, a2,
                        dxfattribs={"layer": "CURVES"})

    for wd, seg in dims:
        h = max(0.5 * scale, 0.72 * wd["cap"] * scale)
        dim = msp.add_aligned_dim(
            p1=pt(seg[0], seg[1]), p2=pt(seg[2], seg[3]), distance=0.0,
            text=wd["text"],
            override={"dimtxt": h, "dimasz": 0.6 * h, "dimgap": 0.25 * h,
                      "dimexo": 0.3 * h, "dimexe": 0.3 * h},
            dxfattribs={"layer": "DIMENSIONS"})
        dim.render()

    for wd in words:
        height = max(0.5 * scale, 0.72 * wd["cap"] * scale)
        layer = "TEXT_REVIEW" if wd.get("review") else "TEXT"
        msp.add_text(wd["text"], dxfattribs={
            "layer": layer,
            "style": "D2CAD",
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
            deep_clean=True,
            smart_read=True,
            review_out=False,
            do_verify=True,
            review_conf=70,
            min_line_px=6.0,
            speck_px=8,
            ocr_min_conf=30,
            log=print):
    """Run the whole image -> DXF pipeline. Returns a stats dict.
    PDFs are routed to pdf2cad: vector pages are lifted exactly,
    scanned pages come back through this pipeline at 300 DPI."""
    import cad_io
    if input_path.lower().endswith(cad_io.CAD_INPUT_EXTS):
        # CAD files are already vector data - translate, don't trace
        if output_path is None:
            output_path = os.path.splitext(input_path)[0] + "_out.dxf"
        out_ext = os.path.splitext(output_path)[1].lower()
        if out_ext not in (".dxf", ".dwg", ".dgn"):
            output_path = os.path.splitext(output_path)[0] + ".dxf"
            out_ext = ".dxf"
        tmp_dxf = (output_path if out_ext == ".dxf"
                   else os.path.splitext(output_path)[0] + ".dxf")
        cad_io.to_dxf(input_path, tmp_dxf, log=log)
        if out_ext != ".dxf":
            if not cad_io.from_dxf(tmp_dxf, output_path, log=log):
                log(f"No CAD converter found - kept {out_ext.upper()[1:]} "
                    f"as DXF: {tmp_dxf}")
                output_path = tmp_dxf
        import ezdxf
        doc = ezdxf.readfile(tmp_dxf)
        n = sum(1 for _ in doc.modelspace())
        log(f"Translated {os.path.basename(input_path)} -> "
            f"{os.path.basename(output_path)} ({n} entities, exact).")
        return dict(output=output_path, entities=n, units="cad",
                    translated=True)

    if input_path.lower().endswith(".pdf"):
        import pdf2cad
        return pdf2cad.convert_pdf(
            input_path, output_path, log=log, scale=scale,
            do_page_crop=do_page_crop, do_deskew=do_deskew, do_ocr=do_ocr,
            do_curves=do_curves, ortho_snap=ortho_snap,
            auto_scale=auto_scale, flag_review=flag_review,
            deep_clean=deep_clean, smart_read=smart_read,
            review_out=review_out, do_verify=do_verify,
            review_conf=review_conf,
            min_line_px=min_line_px, speck_px=speck_px,
            ocr_min_conf=ocr_min_conf)
    if output_path is None:
        output_path = os.path.splitext(input_path)[0] + ".dxf"
    # DWG/DGN output: vectorize to a sibling DXF, convert at the end
    final_output = output_path
    out_ext = os.path.splitext(output_path)[1].lower()
    if out_ext in (".dwg", ".dgn"):
        output_path = os.path.splitext(output_path)[0] + ".dxf"

    log(f"Reading {os.path.basename(input_path)} ...")
    gray = load_gray(input_path)

    if do_page_crop:
        quad = find_page_quad(gray)
        warped = warp_to_page(gray, quad) if quad is not None else None
        if warped is not None:
            gray = warped
            log("Page detected - cropped and perspective-corrected.")
        else:
            gray, cropped = crop_to_page(gray)
            if cropped:
                log("Cropped to the paper region.")

    gray = flatten_lighting(gray)

    if do_deskew:
        angle = estimate_skew(gray)
        if abs(angle) > 0.1:
            gray = rotate_bound(gray, angle)
            log(f"Deskewed by {angle:+.2f} degrees.")

    gray_ocr = gray  # OCR always reads the sharp image; median filtering
    # below is for linework only and would soften the letters
    ink = binarize(gray)
    if deep_clean:
        # dirty scans (old photocopies, blueprints): salt-and-pepper grain
        # shows up as thousands of tiny ink specks - median-filter it away
        # and raise the noise floors before vectorizing
        for ksize in (3, 5):
            ratio, ncomp = speckle_ratio(ink)
            if ratio < 0.55 or ncomp < 1500:
                break
            log(f"Dirty scan detected ({ncomp} specks) - "
                f"deep cleaning (median {ksize}x{ksize}) ...")
            gray = cv2.medianBlur(gray, ksize)
            # median filtering killed the grain, so we can afford a more
            # sensitive threshold that keeps faint/faded linework
            ink = binarize(gray, sensitivity=9)
            speck_px = max(speck_px, 24)
            min_line_px = max(min_line_px, 12.0)
    ink = remove_specks_and_blobs(ink, min_area=speck_px)

    words = []
    if do_ocr:
        if find_tesseract():
            log("Running OCR (horizontal + vertical passes) ...")
            words = ocr_words(gray_ocr, min_conf=ocr_min_conf)
            log(f"OCR found {len(words)} words.")
        else:
            log("WARNING: Tesseract not found - skipping OCR. "
                "Install it or set TESSERACT_CMD.")
        if words and smart_read:
            try:
                import smart_ocr
                if smart_ocr.available():
                    log("Smart text reading (free, offline) - second "
                        "opinion on every label ...")
                    n = smart_ocr.refine_words(gray_ocr, words, log=log)
                    log(f"Smart reader improved {n} labels.")
            except Exception as exc:
                log(f"Smart text reading failed ({exc}) - "
                    f"keeping Tesseract text.")

    line_img = mask_words(ink, words) if words else ink

    log("Tracing stroke centerlines ...")
    rounds, line_img = detect_circles(line_img)
    try:
        segs, curves, arcs = vectorize_centerlines(line_img,
                                                   min_len=min_line_px)
        rounds = rounds + arcs
    except (AttributeError, cv2.error):
        # opencv build without ximgproc thinning: fall back to edge-based
        # detection (noticeably worse - doubled lines). The install must
        # keep opencv-contrib-python-headless as the winning cv2.
        log("WARNING: opencv-contrib missing - using lower-quality "
            "edge tracing. Reinstall opencv-contrib-python-headless.")
        segs = detect_segments(line_img)
        width = stroke_width(line_img)
        curves = residual_curves(line_img, segs, width) if do_curves else []
    log(f"  {len(segs)} strokes, {len(curves)} curved paths, "
        f"{len(rounds)} circles/arcs.")
    if ortho_snap and len(segs):
        segs = snap_orthogonal(segs)
    dashed = np.empty((0, 4))
    if len(segs):
        segs = merge_segments(segs, gap_tol=6.0)
        dashed, segs = detect_dashed(segs)
        # heal junctions so corners and T-joints meet exactly
        both = np.vstack([segs, dashed]) if len(dashed) else segs
        both = snap_topology(both)
        segs, dashed = both[:len(segs)], both[len(segs):]
        log(f"  {len(segs)} lines after merging"
            + (f", {len(dashed)} dashed lines recognized." if len(dashed)
               else "."))
    if not do_curves:
        curves = []
    # unreadable letter-sized squiggles render as confetti in CAD - drop them
    # (closed loops get a lower bar: small circles are real symbols)
    curves = [c for c in curves
              if _feature_size(c[0]) >= (18.0 if c[1] else 50.0)]
    if len(segs) and curves:
        segs = snap_lines_to_polylines(segs, curves)

    # dimension parsing, junk filtering, scale verification, review flagging
    units_feet = False
    scale_conf = None
    for wd in words:
        wd["dim"] = parse_dimension(wd["text"])
        if flag_review and wd["conf"] < review_conf:
            wd["review"] = True
    # words below this confidence are 90% noise unless they parse as a
    # dimension - they were still masked out of the linework above, but
    # they don't belong in the drawing as text
    words = [w for w in words
             if w["dim"] or (w["conf"] >= 55 and
                             not (len(w["text"]) == 1 and w["conf"] < 70))]
    n_dims = sum(1 for w in words if w["dim"])
    if n_dims:
        log(f"Parsed {n_dims} dimension labels "
            f"({', '.join(w['text'] for w in words if w['dim'])}).")
    if auto_scale and n_dims:
        try:
            lsd_segs = detect_segments(line_img)
        except cv2.error:
            lsd_segs = None
        meas_segs = np.vstack([segs, dashed]) if len(dashed) else segs
        ftpx = estimate_scale(words, meas_segs, extra_segs=lsd_segs,
                              img_shape=gray.shape)
        checked = [w for w in words if "dim_ok" in w]
        bad = [w for w in checked if not w["dim_ok"]]
        if flag_review:
            for w in bad:
                w["review"] = True
        if ftpx:
            scale = ftpx
            units_feet = True
            # scale confidence = fraction of checked dimensions that agreed
            if checked:
                scale_conf = (len(checked) - len(bad)) / len(checked)
            log(f"Scale verified against drawn lines: 1 px = {ftpx:.5f} ft "
                f"-> DXF output is in FEET. "
                f"{len(checked) - len(bad)} dimensions agree"
                + (f", {len(bad)} contradict and were flagged." if bad
                   else "."))
        else:
            log("Dimensions found but no consistent scale - "
                "output stays in pixel units.")
    # dimensions remain dimensions: label-on-line pairs become true
    # DIMENSION entities; everything else stays line + text
    dim_pairs = []
    if words and len(segs):
        pairs = pair_dimensions(words, segs,
                                scale=scale if units_feet else None)
        if pairs:
            drop = sorted({i for _, _, idxs in pairs for i in idxs},
                          reverse=True)
            dim_pairs = [(w, np.asarray(span, dtype=np.float64))
                         for w, span, _ in pairs]
            segs = np.delete(segs, drop, axis=0)
            for w, _ in dim_pairs:
                w["as_dim"] = True
            log(f"{len(dim_pairs)} dimension entities recognized.")
        words = [w for w in words if not w.get("as_dim")]

    n_review = sum(1 for w in words if w.get("review"))
    if n_review:
        log(f"{n_review} uncertain text items moved to red TEXT_REVIEW layer "
            f"(boxed on the drawing) - double-check those by hand.")

    n_lines = write_dxf(output_path, gray.shape[0], segs, curves, words,
                        scale=scale, min_len_px=min_line_px,
                        units_feet=units_feet, rounds=rounds, dashed=dashed,
                        dims=dim_pairs)
    log(f"Wrote {output_path}  ({n_lines} lines, {len(dashed)} dashed, "
        f"{len(curves)} polylines, {len(rounds)} circles/arcs, "
        f"{len(dim_pairs)} dimensions, {len(words)} text entities)")
    if review_out:
        # sidecar for the review/correction screen (Phase C data flywheel)
        try:
            import corrections
            if words:
                corrections.export_review(gray_ocr, words + [
                    w for w, _ in dim_pairs], output_path)
        except Exception as exc:
            log(f"(review export skipped: {exc})")
        # provenance: every recovered object with confidence + origin
        try:
            import provenance
            records = provenance.build_records(
                segments=segs, dashed=dashed, rounds=rounds, curves=curves,
                words=words, dims=dim_pairs, scale=scale,
                units_feet=units_feet, scale_conf=scale_conf)
            provenance.export(records, output_path, scale=scale,
                              units_feet=units_feet)
        except Exception as exc:
            log(f"(provenance export skipped: {exc})")

    if do_verify:
        # drawing lint: flag likely defects (never auto-fix). Check only the
        # geometry that was actually written (write_dxf drops sub-min lines),
        # so lint reflects the output, not intermediate fragments.
        try:
            import verify, json as _json
            written = np.asarray(
                [s for s in segs
                 if math.hypot(s[2] - s[0], s[3] - s[1]) >= min_line_px],
                dtype=np.float64) if len(segs) else segs
            findings = verify.check(written, dashed=dashed, dims=dim_pairs,
                                    scale=scale, units_feet=units_feet)
            s = verify.summarize(findings)
            if findings:
                sev = s["by_severity"]
                log(f"Lint: {s['total']} advisory finding(s) "
                    f"({sev['high']} high, {sev['medium']} medium, "
                    f"{sev['low']} low) - see .lint.json")
            with open(os.path.splitext(output_path)[0] + ".lint.json",
                      "w") as f:
                _json.dump({"summary": s, "findings": findings}, f)
        except Exception as exc:
            log(f"(lint skipped: {exc})")

    if final_output != output_path:  # DWG/DGN requested
        import cad_io
        if cad_io.from_dxf(output_path, final_output, log=log):
            output_path = final_output
        else:
            log(f"No CAD converter found - saved DXF instead "
                f"(opens in AutoCAD & MicroStation): {output_path}")
    return dict(output=output_path, lines=n_lines, curves=len(curves),
                words=len(words), review=n_review, scale=scale,
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
    ap.add_argument("input", help="input image (jpg/png/tif...) or PDF")
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
    ap.add_argument("--no-clean", action="store_true",
                    help="don't auto deep-clean dirty scans")
    ap.add_argument("--no-smart", action="store_true",
                    help="don't re-read labels with the offline neural "
                         "reader")
    ap.add_argument("--review", action="store_true",
                    help="write a .review.json sidecar for the text "
                         "correction screen (python review_gui.py ...)")
    ap.add_argument("--no-verify", action="store_true",
                    help="skip the drawing-lint pass (.lint.json)")
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
            deep_clean=not args.no_clean,
            smart_read=not args.no_smart,
            review_out=args.review,
            do_verify=not args.no_verify,
            review_conf=args.review_conf,
            min_line_px=args.min_line,
            speck_px=args.speck)
    if args.preview:
        render_preview(args.output or
                       os.path.splitext(args.input)[0] + ".dxf", args.preview)
        print(f"Preview saved to {args.preview}")


if __name__ == "__main__":
    main()
