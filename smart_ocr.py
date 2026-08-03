#!/usr/bin/env python3
"""smart_ocr - free, offline neural text reading for Drawing2CAD.

Tesseract is good at FINDING text on a drawing but often misreads drawing
lettering. RapidOCR (an open-source deep-learning recognizer bundled with
the app - no account, no API, no cost, no internet) gets a second opinion
on every label Tesseract located. The smarter read only wins when it is
clearly more confident than Tesseract's, so it can rescue labels but never
degrade good ones.
"""

import re

import cv2
import numpy as np

# A feet-inches dimension whose tick marks the reader dropped or half-dropped:
# "7-0", "11-10\"", "7'-8", "45-9" ... The marks are optional in this pattern,
# and it requires TWO integer groups joined by a hyphen - so it can never match
# a room name ("BATH"), a bare callout number ("971"), or a note. That gate is
# what keeps the reconstruction faithful: we only re-punctuate something that
# is already, unambiguously, a two-part dimension.
_DIM_RE = re.compile(r"^(\d+)\s*['’´`]?\s*-\s*(\d+)\s*[\"”]?$")


def normalize_dimension(text):
    """Reconstruct canonical A'-B\" from a dimension whose feet/inch marks the
    reader dropped. Non-dimension text passes through untouched (no invention:
    bare numbers never gain a foot mark here - that needs drawing context)."""
    m = _DIM_RE.match("".join(text.split()))
    if m:
        return f"{m.group(1)}'-{m.group(2)}\""
    return text

try:
    from rapidocr_onnxruntime import RapidOCR
    _HAS_RAPID = True
except ImportError:
    _HAS_RAPID = False

_engine = None

REC_HEIGHT = 48          # recognizer sweet spot for line height
MIN_SCORE = 0.80         # below this the neural read is a guess too
WIN_MARGIN = 15.0        # neural read must beat tesseract by this much


def available():
    return _HAS_RAPID


def _get_engine():
    global _engine
    if _engine is None:
        _engine = RapidOCR()
    return _engine


def _crop_upright(gray, wd, pad=4):
    """Cut the word's box out of the image and rotate it to read left-right."""
    x0 = max(0, int(wd["x"]) - pad)
    y0 = max(0, int(wd["y"]) - pad)
    x1 = min(gray.shape[1], int(wd["x"] + wd["w"]) + pad)
    y1 = min(gray.shape[0], int(wd["y"] + wd["h"]) + pad)
    img = gray[y0:y1, x0:x1]
    if img.size == 0:
        return None
    if wd["rotation"] == 90:
        img = cv2.rotate(img, cv2.ROTATE_90_CLOCKWISE)
    elif wd["rotation"] == 270:
        img = cv2.rotate(img, cv2.ROTATE_90_COUNTERCLOCKWISE)
    if img.shape[0] < REC_HEIGHT:
        scale = REC_HEIGHT / float(img.shape[0])
        img = cv2.resize(img, (max(8, int(img.shape[1] * scale)), REC_HEIGHT))
    return img


def _normalize(text):
    """Map full-width punctuation/digits to ASCII; reject non-Latin output
    (a CJK guess on a survey label means the model saw noise)."""
    out = []
    for ch in text:
        o = ord(ch)
        if 0xFF01 <= o <= 0xFF5E:
            out.append(chr(o - 0xFEE0))
        elif o > 0x2FFF:
            return ""
        else:
            out.append(ch)
    return "".join(out).strip()


def refine_words(gray, words, log=print):
    """Second-opinion pass over every located label. Mutates word dicts in
    place when the neural read clearly beats Tesseract's confidence.
    Returns how many labels were improved."""
    engine = _get_engine()
    changed = 0
    for wd in words:
        crop = _crop_upright(gray, wd)
        if crop is None:
            continue
        try:
            res, _ = engine(crop, use_det=False, use_cls=False, use_rec=True)
        except Exception:
            continue
        if not res:
            continue
        text, score = res[0][0], float(res[0][1])
        text = normalize_dimension(_normalize(text))
        if not text or score < MIN_SCORE:
            continue
        if score * 100.0 >= wd["conf"] + WIN_MARGIN:
            if text != wd["text"]:
                changed += 1
            wd["text"] = text
            wd["conf"] = score * 100.0
    return changed
