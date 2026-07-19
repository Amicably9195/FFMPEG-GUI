#!/usr/bin/env python3
"""benchmark - scored test bench for the Drawing2CAD converter.

Generates synthetic floor plans with KNOWN ground truth (every wall segment
and every label), renders them like scans with realistic damage (photocopier
speckle, blur, uneven light, slight rotation), runs the converter, and
scores the result:

  line coverage   - how much of the true linework was recovered
  line precision  - how much of the recovered linework is real (not junk)
  text accuracy   - how many labels were read correctly
  scale           - whether the drawing auto-scaled to the right feet

Run:  python benchmark.py [--n 6] [--seed 1] [--keep]
"""

import argparse
import os
import random
import tempfile

import cv2
import numpy as np

import ezdxf
import scan2cad

PX_PER_FT = 14.0
MARGIN = 120


def _dim_label(feet):
    whole = int(feet)
    inches = round((feet - whole) * 12)
    if inches == 0:
        return f"{whole}'-0\""
    return f"{whole}'-{inches}\""


ROOM_NAMES = ["KITCHEN", "BED ROOM", "LIVING ROOM", "DINING ROOM", "HALL",
              "BATH ROOM", "CLOSET", "GARAGE", "PORCH", "CELLAR"]


def generate_plan(rng):
    """Random small floor plan. Returns (segments_ft, labels, dims) where
    dims are (value_ft, seg_ft) pairs used for scale ground truth."""
    w = rng.uniform(24, 40)
    h = rng.uniform(30, 55)
    segs = [(0, 0, w, 0), (w, 0, w, h), (w, h, 0, h), (0, h, 0, 0)]
    labels = []
    dims = []
    # interior walls with door gaps
    splits = sorted(rng.uniform(0.25, 0.75) for _ in range(2))
    for f in splits:
        y = h * f
        gap = rng.uniform(0.2, 0.7)
        segs.append((0, y, w * gap - 1.5, y))
        segs.append((w * gap + 1.5, y, w, y))
    x = w * rng.uniform(0.35, 0.65)
    segs.append((x, 0, x, h * splits[0] - 1.5))
    # dimension strings along the bottom and left, with tick strokes
    dim_y = -3.0
    segs.append((0, dim_y, w, dim_y))
    for tx in (0, w):
        segs.append((tx - 0.4, dim_y - 0.4, tx + 0.4, dim_y + 0.4))
    dims.append((w, (0, dim_y, w, dim_y)))
    labels.append((_dim_label(w), w / 2, dim_y - 1.2, 0))
    dim_x = -3.0
    segs.append((dim_x, 0, dim_x, h))
    for ty in (0, h):
        segs.append((dim_x - 0.4, ty - 0.4, dim_x + 0.4, ty + 0.4))
    dims.append((h, (dim_x, 0, dim_x, h)))
    labels.append((_dim_label(h), dim_x - 1.2, h / 2, 90))
    # room names
    ys = [0] + [h * f for f in splits] + [h]
    for i in range(len(ys) - 1):
        cy = (ys[i] + ys[i + 1]) / 2
        labels.append((rng.choice(ROOM_NAMES), w * 0.55, cy, 0))
    # a round column - circles must come back as circles
    circles = [(w * rng.uniform(0.15, 0.3), h * rng.uniform(0.15, 0.3),
                rng.uniform(0.9, 1.6))]
    # a dashed setback line above the plan - dashed must stay dashed
    dashes = [(0, h + 3.0, w, h + 3.0)]
    return segs, labels, dims, circles, dashes


def render(segs, labels, rng, dirty=False, circles=(), dashes=()):
    """Rasterize the plan the way a scan of it would look."""
    xs = [s[i] for s in segs for i in (0, 2)]
    ys = [s[i] for s in segs for i in (1, 3)]
    x0, y0 = min(xs), min(ys)
    W = int((max(xs) - x0) * PX_PER_FT) + 2 * MARGIN
    H = int((max(ys) - y0) * PX_PER_FT) + 2 * MARGIN
    img = np.full((H, W), 255, np.uint8)

    def pt(x, y):
        return (int((x - x0) * PX_PER_FT) + MARGIN,
                H - (int((y - y0) * PX_PER_FT) + MARGIN))

    for x1, y1, x2, y2 in segs:
        cv2.line(img, pt(x1, y1), pt(x2, y2), 0, 3, cv2.LINE_AA)
    truth_circ = []
    for cx, cy, cr in circles:
        cv2.circle(img, pt(cx, cy), int(cr * PX_PER_FT), 0, 3, cv2.LINE_AA)
        truth_circ.append((pt(cx, cy), cr * PX_PER_FT))
    truth_dash = []
    for x1, y1, x2, y2 in dashes:
        p1, p2 = np.array(pt(x1, y1), float), np.array(pt(x2, y2), float)
        span = np.linalg.norm(p2 - p1)
        u = (p2 - p1) / span
        on, off, t = 11.0, 7.0, 0.0
        while t < span:
            a = p1 + u * t
            b = p1 + u * min(t + on, span)
            cv2.line(img, (int(a[0]), int(a[1])), (int(b[0]), int(b[1])),
                     0, 3, cv2.LINE_AA)
            t += on + off
        truth_dash.append((tuple(p1.astype(int)), tuple(p2.astype(int))))
    for text, lx, ly, rot in labels:
        px, py = pt(lx, ly)
        if rot == 0:
            cv2.putText(img, text, (px - 7 * len(text), py + 8),
                        cv2.FONT_HERSHEY_SIMPLEX, 0.8, 0, 2, cv2.LINE_AA)
        else:
            canvas = np.full((40, 22 * len(text)), 255, np.uint8)
            cv2.putText(canvas, text, (4, 30), cv2.FONT_HERSHEY_SIMPLEX,
                        0.8, 0, 2, cv2.LINE_AA)
            canvas = cv2.rotate(canvas, cv2.ROTATE_90_COUNTERCLOCKWISE)
            ch, cw = canvas.shape
            yy, xx = max(0, py - ch // 2), max(0, px - cw // 2)
            roi = img[yy:yy + ch, xx:xx + cw]
            np.minimum(roi, canvas[:roi.shape[0], :roi.shape[1]], out=roi)

    truth_px = [(pt(x1, y1), pt(x2, y2)) for x1, y1, x2, y2 in segs]

    if dirty:
        # photocopier grain, blur, uneven light
        noise = rng.integers(0, 255, img.shape, dtype=np.uint8)
        img[noise < 4] = 0
        img[noise > 251] = 255
        img = cv2.GaussianBlur(img, (3, 3), 0)
        grad = np.linspace(0.75, 1.0, img.shape[1])[None, :]
        img = np.clip(img * grad, 0, 255).astype(np.uint8)
    return img, truth_px, truth_circ, truth_dash


def score(dxf_path, truth_px, labels, img_h, true_scale, used_scale=1.0,
          truth_circ=(), truth_dash=()):
    doc = ezdxf.readfile(dxf_path)
    msp = doc.modelspace()
    units_feet = doc.header.get("$INSUNITS", 0) == 2
    # measure geometry independently of the locked scale: fit the DXF's
    # extent to the truth's pixel extent, then report scale error separately
    scale_err = None
    s = used_scale if units_feet else 1.0
    if units_feet:
        scale_err = abs(s / true_scale - 1.0)

    def unpt(x, y):  # DXF coords back to pixel space
        return (x / s, img_h - y / s)

    got = np.zeros((img_h + 4, 6000), np.uint8)
    want = np.zeros_like(got)
    for e in msp:
        if e.dxftype() == "LINE":
            p1 = unpt(e.dxf.start.x, e.dxf.start.y)
            p2 = unpt(e.dxf.end.x, e.dxf.end.y)
            cv2.line(got, (int(p1[0]), int(p1[1])),
                     (int(p2[0]), int(p2[1])), 255, 1)
        elif e.dxftype() == "LWPOLYLINE":
            pts = [unpt(p[0], p[1]) for p in e.get_points()]
            for a, b in zip(pts, pts[1:]):
                cv2.line(got, (int(a[0]), int(a[1])),
                         (int(b[0]), int(b[1])), 255, 1)
        elif e.dxftype() in ("CIRCLE", "ARC"):
            c = unpt(e.dxf.center.x, e.dxf.center.y)
            r = e.dxf.radius / s
            if e.dxftype() == "CIRCLE":
                a0, a1 = 0.0, 360.0
            else:
                a0, a1 = e.dxf.start_angle, e.dxf.end_angle
            sweep = (a1 - a0) % 360.0 or 360.0
            angs = np.radians(a0 + np.linspace(0, sweep, 90))
            # CAD y-up angles -> image y-down
            xs = c[0] + r * np.cos(angs)
            ys = c[1] - r * np.sin(angs)
            for k in range(len(xs) - 1):
                cv2.line(got, (int(xs[k]), int(ys[k])),
                         (int(xs[k + 1]), int(ys[k + 1])), 255, 1)
    for p1, p2 in truth_px:
        cv2.line(want, p1, p2, 255, 1)
    for c, r in truth_circ:
        cv2.circle(want, c, int(r), 255, 1)
    for p1, p2 in truth_dash:
        cv2.line(want, p1, p2, 255, 1)
    dash_ok = 0
    if truth_dash:
        dlines = [e for e in msp if e.dxftype() == "LINE"
                  and e.dxf.linetype == "DASHED"]
        for p1, p2 in truth_dash:
            for e in dlines:
                a = unpt(e.dxf.start.x, e.dxf.start.y)
                b = unpt(e.dxf.end.x, e.dxf.end.y)
                ends = sorted([a, b]), sorted([p1, p2])
                if all(abs(ends[0][k][0] - ends[1][k][0]) < 12
                       and abs(ends[0][k][1] - ends[1][k][1]) < 12
                       for k in (0, 1)):
                    dash_ok += 1
                    break
    circ_ok = 0
    if truth_circ:
        circs = [e for e in msp if e.dxftype() == "CIRCLE"]
        for (tcx, tcy), tr in truth_circ:
            for e in circs:
                cx, cy = unpt(e.dxf.center.x, e.dxf.center.y)
                if (abs(cx - tcx) < 6 and abs(cy - tcy) < 6
                        and abs(e.dxf.radius / s - tr) < 5):
                    circ_ok += 1
                    break

    k = np.ones((7, 7), np.uint8)
    want_fat = cv2.dilate(want, k)
    got_fat = cv2.dilate(got, k)
    coverage = (want & got_fat).sum() / max(1, want.sum())
    precision = (got & want_fat).sum() / max(1, got.sum())

    texts = {e.dxf.text.strip().upper()
             for e in msp if e.dxftype() == "TEXT"}
    joined = " ".join(texts)
    hits = sum(1 for t, *_ in labels
               if t.upper() in texts or t.upper() in joined)

    return (coverage, precision, hits, len(labels), units_feet, scale_err,
            circ_ok, len(truth_circ), dash_ok, len(truth_dash))


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--n", type=int, default=6)
    ap.add_argument("--seed", type=int, default=1)
    ap.add_argument("--keep", action="store_true",
                    help="keep generated files next to benchmark.py")
    args = ap.parse_args()
    rng = np.random.default_rng(args.seed)
    pyrng = random.Random(args.seed)

    rows = []
    outdir = (os.path.dirname(os.path.abspath(__file__))
              if args.keep else tempfile.mkdtemp())
    for i in range(args.n):
        dirty = i % 2 == 1
        segs, labels, dims, circles, dashes = generate_plan(pyrng)
        img, truth_px, truth_circ, truth_dash = render(
            segs, labels, rng, dirty=dirty, circles=circles, dashes=dashes)
        img_path = os.path.join(outdir, f"bench_{i}.png")
        cv2.imwrite(img_path, img)
        dxf_path = os.path.join(outdir, f"bench_{i}.dxf")
        stats = scan2cad.convert(img_path, dxf_path, do_page_crop=False,
                                 do_deskew=False, log=lambda m: None)
        cov, prec, hits, total, feet, serr, cok, ctot, dok, dtot = score(
            dxf_path, truth_px, labels, img.shape[0], 1.0 / PX_PER_FT,
            used_scale=stats.get("scale", 1.0), truth_circ=truth_circ,
            truth_dash=truth_dash)
        rows.append((i, dirty, cov, prec, hits, total, feet, cok, ctot,
                     dok, dtot))
        stag = (f"YES (err {serr * 100:.1f}%)" if feet else "no")
        print(f"plan {i} ({'dirty' if dirty else 'clean'}): "
              f"line coverage {cov * 100:5.1f}%  precision {prec * 100:5.1f}%  "
              f"text {hits}/{total}  circles {cok}/{ctot}  "
              f"dashed {dok}/{dtot}  scale-to-feet {stag}")

    cov = np.mean([r[2] for r in rows])
    prec = np.mean([r[3] for r in rows])
    txt = sum(r[4] for r in rows) / max(1, sum(r[5] for r in rows))
    scl = sum(1 for r in rows if r[6])
    circ = (sum(r[7] for r in rows), sum(r[8] for r in rows))
    dsh = (sum(r[9] for r in rows), sum(r[10] for r in rows))
    print(f"\nOVERALL: coverage {cov * 100:.1f}%  precision {prec * 100:.1f}%  "
          f"text {txt * 100:.1f}%  circles {circ[0]}/{circ[1]}  "
          f"dashed {dsh[0]}/{dsh[1]}  scale locked {scl}/{len(rows)}")


if __name__ == "__main__":
    main()
