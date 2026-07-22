#!/usr/bin/env python3
"""corrections - the review/correction flywheel for Drawing2CAD (Phase C data).

The converter flags uncertain text on a hidden red layer. This module turns
that into a fast human pass that ALSO collects training data:

  1. During conversion, export_review() writes a sidecar (the processed
     image + every word's box/guess/confidence) next to the DXF.
  2. A review screen shows each uncertain label beside its image crop; the
     user confirms or fixes it in a keystroke.
  3. Each fix is saved as a (crop image -> true text) training pair, and the
     corrected text is written back into the DXF (moved off the review
     layer). After a few hundred pairs the local OCR can be fine-tuned on
     real drafting lettering - the honest "learns from drawings" loop.

The GUI is thin; the testable logic lives here.
"""

import csv
import hashlib
import json
import os
import time

import cv2
import numpy as np

DATASET_DIR = os.path.expanduser("~/.drawing2cad_dataset")


# ── sidecar export (called by the converter) ─────────────────────────────────

def export_review(image, words, dxf_path):
    """Write <dxf>.review.json + <dxf>.review.png so a review screen can crop
    each word from the exact frame the boxes index into. `image` is the
    processed gray image OCR ran on."""
    base = os.path.splitext(dxf_path)[0]
    png = base + ".review.png"
    cv2.imencode(".png", image)[1].tofile(png)
    rows = []
    for w in words:
        rows.append({
            "text": w["text"], "conf": float(w["conf"]),
            "x": int(w["x"]), "y": int(w["y"]),
            "w": int(w["w"]), "h": int(w["h"]),
            "rotation": int(w["rotation"]),
            "review": bool(w.get("review")),
        })
    meta = {"image": os.path.basename(png), "dxf": os.path.basename(dxf_path),
            "words": rows}
    with open(base + ".review.json", "w") as f:
        json.dump(meta, f)
    return base + ".review.json"


def load_review(json_path):
    """Load a sidecar; returns (image ndarray, list of word dicts)."""
    with open(json_path) as f:
        meta = json.load(f)
    png = os.path.join(os.path.dirname(json_path), meta["image"])
    data = np.fromfile(png, dtype=np.uint8)
    image = cv2.imdecode(data, cv2.IMREAD_GRAYSCALE)
    return image, meta["words"], meta


def crop_word(image, w, pad=3):
    """Upright crop of one word for display / training."""
    x0 = max(0, w["x"] - pad)
    y0 = max(0, w["y"] - pad)
    x1 = min(image.shape[1], w["x"] + w["w"] + pad)
    y1 = min(image.shape[0], w["y"] + w["h"] + pad)
    crop = image[y0:y1, x0:x1]
    if crop.size == 0:
        return np.full((10, 10), 255, np.uint8)
    if w["rotation"] == 90:
        crop = cv2.rotate(crop, cv2.ROTATE_90_CLOCKWISE)
    elif w["rotation"] == 270:
        crop = cv2.rotate(crop, cv2.ROTATE_90_COUNTERCLOCKWISE)
    return crop


# ── training-pair dataset ────────────────────────────────────────────────────

def save_pair(crop, text, dataset_dir=DATASET_DIR):
    """Append one (image -> text) training pair. De-duplicated by crop hash so
    re-reviewing the same drawing doesn't inflate the set."""
    os.makedirs(dataset_dir, exist_ok=True)
    ok, buf = cv2.imencode(".png", crop)
    if not ok:
        return None
    raw = buf.tobytes()
    h = hashlib.sha1(raw + text.encode("utf-8")).hexdigest()[:16]
    img_path = os.path.join(dataset_dir, h + ".png")
    if not os.path.exists(img_path):
        with open(img_path, "wb") as f:
            f.write(raw)
    labels = os.path.join(dataset_dir, "labels.tsv")
    seen = set()
    if os.path.exists(labels):
        with open(labels, newline="") as f:
            seen = {r[0] for r in csv.reader(f, delimiter="\t") if r}
    if h + ".png" not in seen:
        with open(labels, "a", newline="") as f:
            csv.writer(f, delimiter="\t").writerow(
                [h + ".png", text, f"{time.time():.0f}"])
    return img_path


def dataset_size(dataset_dir=DATASET_DIR):
    labels = os.path.join(dataset_dir, "labels.tsv")
    if not os.path.exists(labels):
        return 0
    with open(labels, newline="") as f:
        return sum(1 for r in csv.reader(f, delimiter="\t") if r)


# ── write corrections back into the DXF ──────────────────────────────────────

def apply_corrections(dxf_path, fixes, out_path=None):
    """fixes: list of (word_index, corrected_text, original_text). Update the
    matching TEXT entity's string and move it from TEXT_REVIEW onto TEXT
    (it's now confirmed). Matching is by original text + position order.
    Returns number of entities updated."""
    import ezdxf
    doc = ezdxf.readfile(dxf_path)
    msp = doc.modelspace()
    by_text = {}
    for e in msp:
        if e.dxftype() == "TEXT":
            by_text.setdefault(e.dxf.text, []).append(e)
    n = 0
    for _, new_text, orig in fixes:
        bucket = by_text.get(orig)
        if not bucket:
            continue
        e = bucket.pop(0)
        e.dxf.text = new_text
        if e.dxf.layer == "TEXT_REVIEW":
            e.dxf.layer = "TEXT"
        n += 1
    doc.saveas(out_path or dxf_path)
    return n
