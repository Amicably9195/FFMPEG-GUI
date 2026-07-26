#!/usr/bin/env python3
"""diffview - "what did the reconstruction miss?" verification view.

The SVG overlay shows the recovered vectors over the source. This is its
complement (roadmap Phase E, "differences highlighted"): it rasterizes the
recovered geometry, compares it against the source ink, and highlights the
source ink that NO recovered entity captured - in red. It needs no ground
truth: the source drawing is the reference.

It also returns a `missed_fraction` - the share of source ink left uncaptured -
a per-drawing "how complete is this reconstruction?" number a professional can
trust without a benchmark. It never alters geometry; it only reports.
"""

import math

import cv2
import numpy as np


def _rasterize(shape, segments, curves, rounds, dashed, dims, thick=3):
    """Draw all recovered entities onto a blank mask (255 = recovered ink)."""
    got = np.zeros(shape, np.uint8)

    def line(a, b):
        cv2.line(got, (int(round(a[0])), int(round(a[1]))),
                 (int(round(b[0])), int(round(b[1]))), 255, thick)

    for s in (np.asarray(segments, float) if len(segments) else ()):
        line(s[:2], s[2:])
    for s in (np.asarray(dashed, float) if len(dashed) else ()):
        line(s[:2], s[2:])
    for pts, closed in curves:
        p = [(int(round(x)), int(round(y))) for x, y in pts]
        for a, b in zip(p, p[1:]):
            cv2.line(got, a, b, 255, thick)
        if closed and len(p) > 2:
            cv2.line(got, p[-1], p[0], 255, thick)
    for ent in rounds:
        c = (int(round(ent[1])), int(round(ent[2])))
        r = int(round(ent[3]))
        if ent[0] == "circle":
            cv2.circle(got, c, r, 255, thick)
        else:                                   # arc -> sample
            cx, cy, rr = ent[1], ent[2], ent[3]
            p1, p2, pm = ent[4], ent[5], ent[6]
            a1 = math.atan2(p1[1] - cy, p1[0] - cx)
            a2 = math.atan2(p2[1] - cy, p2[0] - cx)
            am = math.atan2(pm[1] - cy, pm[0] - cx)
            sweep = (a2 - a1) % (2 * math.pi)
            if (am - a1) % (2 * math.pi) > sweep:
                a1, sweep = a2, 2 * math.pi - sweep
            n = max(6, int(sweep / 0.15))
            prev = None
            for t in range(n + 1):
                a = a1 + sweep * t / n
                cur = (int(round(cx + rr * math.cos(a))),
                       int(round(cy + rr * math.sin(a))))
                if prev:
                    cv2.line(got, prev, cur, 255, thick)
                prev = cur
    for _wd, span in dims:
        line((span[0], span[1]), (span[2], span[3]))
    return got


def analyze(source_gray, segments=(), curves=(), words=(), rounds=(),
            dashed=(), dims=(), tolerance=3):
    """Return (missed_fraction, diff_rgb).

    missed_fraction: share of source ink not covered by any recovered entity
    (0 = everything captured). Text regions are excluded from the source ink
    so unrecovered *lettering* is not counted as missed *geometry*.
    diff_rgb: source ink in light grey, missed ink in red - a visual audit.
    """
    ink = cv2.threshold(source_gray, 0, 255,
                        cv2.THRESH_BINARY_INV + cv2.THRESH_OTSU)[1]
    # don't count text pixels as missed geometry - blank the word boxes
    for w in words:
        x, y = int(w.get("x", 0)), int(w.get("y", 0))
        bw, bh = int(w.get("w", 0)), int(w.get("h", 0))
        pad = 2
        ink[max(0, y - pad):y + bh + pad, max(0, x - pad):x + bw + pad] = 0

    got = _rasterize(ink.shape, segments, curves, rounds, dashed, dims)
    got_fat = cv2.dilate(got, np.ones((2 * tolerance + 1,) * 2, np.uint8))
    missed = cv2.bitwise_and(ink, cv2.bitwise_not(got_fat))

    ink_total = int(ink.sum() // 255)
    missed_total = int(missed.sum() // 255)
    frac = (missed_total / ink_total) if ink_total else 0.0

    diff = np.full((*ink.shape, 3), 255, np.uint8)
    diff[ink > 0] = (210, 210, 210)             # source ink: light grey
    diff[missed > 0] = (0, 0, 255)              # missed ink: red (BGR)
    return frac, diff


def write_diff(path, source_gray, **kw):
    """Write the missed-ink audit PNG; return the missed_fraction."""
    frac, diff = analyze(source_gray, **kw)
    cv2.imwrite(path, diff)
    return frac
