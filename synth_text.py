#!/usr/bin/env python3
"""synth_text - synthetic drafting-text corpus for the reader (Phase C, Stage 1).

Reading is the biggest lever on quality (OCR ~80% on the benchmark). Before
any human labels a thing, we can pre-train / adapt the local reader on
UNLIMITED synthetic drafting text: dimensions, room names, notes, scales -
rendered in drafting-style fonts and put through the same degradation recipes
real scans suffer (blur, photocopy grain, faded ink, low DPI, skew...).

Two jobs, both fully local and free:
  * `gen`     - write labeled (crop -> text) pairs in the EXACT format the
                correction flywheel uses (corrections.save_pair), so synthetic
                pre-training data and real user corrections share one pipeline.
  * `measure` - run the current reader over fresh synthetic crops and report
                exact-match and character accuracy. This turns "text is the
                ceiling" into a concrete, repeatable number - measurable NOW,
                with no training and no GPU.

CLI:
    python synth_text.py gen -n 500 [--out DIR]
    python synth_text.py measure -n 200 [--engine rapid|tesseract]
"""

import argparse
import os
import random

import cv2
import numpy as np

import dataset_builder

ROOM_NAMES = ["KITCHEN", "BEDROOM", "BATH", "LIVING", "DINING", "CLOSET",
              "HALL", "OFFICE", "GARAGE", "LAUNDRY", "PANTRY", "FOYER",
              "MASTER BR", "UTILITY", "STORAGE", "PORCH", "DECK", "STAIR"]

NOTES = ["NORTH", "TYP.", "SCALE", "PLAN", "SECTION", "DETAIL", "ELEV.",
         "EXIST.", "NEW", "REF.", "NO SCALE", "SIM.", "V.I.F.", "R.O."]

# Drafting-style faces cv2 can render (Hershey set); real drafting lettering
# is closest to the simplex/duplex/triplex faces.
FONTS = [cv2.FONT_HERSHEY_SIMPLEX, cv2.FONT_HERSHEY_DUPLEX,
         cv2.FONT_HERSHEY_TRIPLEX, cv2.FONT_HERSHEY_COMPLEX,
         cv2.FONT_HERSHEY_COMPLEX_SMALL]

# Degradation recipes that make sense for a small TEXT crop (no folds/stains
# that would swallow a tiny label).
TEXT_RECIPES = ["clean_flatbed", "office_scan", "old_photocopy", "faxed",
                "bad_light_photo"]


def _dimension(rng):
    """A realistic feet-inches dimension string."""
    ft = rng.randint(1, 60)
    inch = rng.choice([0, 0, 0, 3, 4, 6, 8, 9, 10])
    if rng.random() < 0.15:                       # bare feet
        return f"{ft}'"
    return f"{ft}'-{inch}\""


def sample_text(rng):
    """One drawing-text token, weighted toward what a plan actually contains."""
    r = rng.random()
    if r < 0.45:
        return _dimension(rng)
    if r < 0.75:
        return rng.choice(ROOM_NAMES)
    if r < 0.9:
        return rng.choice(NOTES)
    return str(rng.randint(1, 999))               # room numbers, callouts


def render_text(text, rng):
    """Render `text` to a tight grayscale crop (black on white)."""
    font = rng.choice(FONTS)
    scale = rng.uniform(0.7, 1.5)
    thick = rng.choice([1, 2, 2, 3])
    (tw, th), base = cv2.getTextSize(text, font, scale, thick)
    pad = int(6 + rng.uniform(0, 6))
    img = np.full((th + base + 2 * pad, tw + 2 * pad), 255, np.uint8)
    cv2.putText(img, text, (pad, th + pad), font, scale, 0, thick,
                cv2.LINE_AA)
    return img


def make_sample(rng, npr):
    """Return (crop, truth_text). `rng` is python Random, `npr` numpy rng."""
    text = sample_text(rng)
    crop = render_text(text, rng)
    recipe = rng.choice(TEXT_RECIPES)
    crop, _ = dataset_builder.degrade(crop, npr, recipe=recipe)
    return crop, text


# --------------------------------------------------------------------------
# gen: write flywheel-format training pairs
# --------------------------------------------------------------------------

def gen(n=500, out_dir=None, seed=0):
    import corrections
    out_dir = out_dir or os.path.join(dataset_builder.ROOT, "synth_text")
    os.makedirs(out_dir, exist_ok=True)
    for i in range(n):
        rng = random.Random(seed + i)
        npr = np.random.default_rng(seed + i)
        crop, text = make_sample(rng, npr)
        corrections.save_pair(crop, text, dataset_dir=out_dir)
    return corrections.dataset_size(dataset_dir=out_dir), out_dir


# --------------------------------------------------------------------------
# measure: score the current reader on synthetic drafting text
# --------------------------------------------------------------------------

def _norm(s):
    return "".join(s.split()).upper()


def _char_acc(truth, pred):
    """1 - normalized edit distance (Levenshtein), on normalized strings."""
    a, b = _norm(truth), _norm(pred)
    if not a:
        return 1.0 if not b else 0.0
    prev = list(range(len(b) + 1))
    for i, ca in enumerate(a, 1):
        cur = [i]
        for j, cb in enumerate(b, 1):
            cur.append(min(prev[j] + 1, cur[j - 1] + 1,
                           prev[j - 1] + (ca != cb)))
        prev = cur
    return max(0.0, 1.0 - prev[-1] / len(a))


def _read_rapid(crop):
    import smart_ocr
    engine = smart_ocr._get_engine()
    res, _ = engine(crop, use_det=False, use_cls=False, use_rec=True)
    if not res:
        return ""
    return smart_ocr._normalize(res[0][0])


def _read_tesseract(crop):
    import pytesseract
    if crop.shape[0] < 32:
        s = 32.0 / crop.shape[0]
        crop = cv2.resize(crop, (max(8, int(crop.shape[1] * s)), 32))
    return pytesseract.image_to_string(
        crop, config="--psm 7").strip()


def measure(n=200, seed=10000, engine="rapid"):
    reader = _read_rapid if engine == "rapid" else _read_tesseract
    exact, char_sum = 0, 0.0
    misses = []
    for i in range(n):
        rng = random.Random(seed + i)
        npr = np.random.default_rng(seed + i)
        crop, truth = make_sample(rng, npr)
        try:
            pred = reader(crop)
        except Exception:
            pred = ""
        ca = _char_acc(truth, pred)
        char_sum += ca
        if _norm(pred) == _norm(truth):
            exact += 1
        elif len(misses) < 12:
            misses.append((truth, pred))
    return {"n": n, "engine": engine,
            "exact_pct": 100.0 * exact / n,
            "char_pct": 100.0 * char_sum / n,
            "misses": misses}


def _print_measure(r):
    print(f"reader: {r['engine']}   samples: {r['n']}")
    print(f"  exact-match accuracy : {r['exact_pct']:.1f}%")
    print(f"  character accuracy   : {r['char_pct']:.1f}%")
    if r["misses"]:
        print("  sample misses (truth -> read):")
        for t, p in r["misses"]:
            print(f"    {t!r:14s} -> {p!r}")


def main(argv=None):
    ap = argparse.ArgumentParser(
        description=__doc__,
        formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = ap.add_subparsers(dest="cmd", required=True)
    g = sub.add_parser("gen", help="write flywheel-format training pairs")
    g.add_argument("-n", type=int, default=500)
    g.add_argument("--out", default=None)
    g.add_argument("--seed", type=int, default=0)
    m = sub.add_parser("measure", help="score the current reader")
    m.add_argument("-n", type=int, default=200)
    m.add_argument("--seed", type=int, default=10000)
    m.add_argument("--engine", choices=["rapid", "tesseract"], default="rapid")

    args = ap.parse_args(argv)
    if args.cmd == "gen":
        size, out = gen(n=args.n, out_dir=args.out, seed=args.seed)
        print(f"corpus now holds {size} labeled pairs at {out}")
    else:
        _print_measure(measure(n=args.n, seed=args.seed, engine=args.engine))


if __name__ == "__main__":
    main()
