#!/usr/bin/env python3
"""dataset_builder - the curated benchmark + training corpus for Drawing2CAD.

Doctrine (see DECISIONS.md #7): we do NOT scrape the open web. Training and
benchmark data comes from three legally clean streams only:

  1. CURATED downloads from an approved-source registry (US gov records,
     public CAD sample libraries, universities, open gov engineering
     manuals). Each source is named, licensed, and pinned here.
  2. SYNTHETIC generation - the most important stream, because it is fully
     local, free, unlimited, and lets us manufacture the exact hard cases we
     need (faded ink, folds, photocopy grain, perspective, low DPI...).
  3. REAL user corrections from the review flywheel (collected by
     corrections.py), which are the highest-value pairs of all.

This module gives the project:
  * a category-organized benchmark SUITE on disk
  * a synthetic degradation library that turns one clean drawing into many
    realistic hard scans, each with ground-truth metadata
  * per-sample metadata (source, license, category, degradations applied)
  * a deterministic train / validation / benchmark split
  * de-duplication so the same drawing never lands in two splits

Everything except the curated download step runs offline. The download step
is network-gated and, on a sandbox with no network, is skipped with a clear
message - the framework and the synthetic pipeline still work.

CLI:
    python dataset_builder.py init                 # create the folder tree
    python dataset_builder.py sources              # list approved sources
    python dataset_builder.py degrade IMG [-n 8]   # make degraded variants
    python dataset_builder.py synth [-n 20]        # generate synthetic plans
    python dataset_builder.py fetch [--source ID]  # curated download (net)
    python dataset_builder.py split                # assign train/val/bench
    python dataset_builder.py stats                # corpus health
"""

import argparse
import hashlib
import json
import os
import time

import cv2
import numpy as np

# --------------------------------------------------------------------------
# Layout
# --------------------------------------------------------------------------

# Kept out of the repo by default (data is large and often licensed for use
# but not redistribution). Override with DRAWING2CAD_DATA.
ROOT = os.environ.get(
    "DRAWING2CAD_DATA",
    os.path.join(os.path.expanduser("~"), ".drawing2cad_dataset"))

# The benchmark suite: one folder per drawing kind, so quality can be graded
# per category and hard cases can be collected deliberately.
CATEGORIES = (
    "vector",         # born-digital CAD PDFs - the easy ceiling
    "clean_scans",    # 300+ DPI flatbed scans
    "poor_scans",     # low-DPI, skewed, or noisy scans
    "phone_photos",   # camera captures: perspective, curl, uneven light
    "surveys",        # property/boundary surveys (legal, high-stakes)
    "architectural",  # floor plans, building sections
    "site_plans",     # site/plot/grading plans
    "title_blocks",   # title-block crops (dense small text)
    "handwriting",    # hand-lettered notes and dimensions
    "dimensions",     # dimension strings + geometry
    "symbols",        # symbol-heavy sheets (doors, fixtures, north arrows)
)

SPLITS = ("train", "validation", "benchmark")

BENCHMARK_VERSION = "1.0"   # keep in step with benchmark.py


def _paths():
    return {c: os.path.join(ROOT, c) for c in CATEGORIES}


def init_tree():
    """Create the on-disk suite: <ROOT>/<category>/{raw,degraded,meta}."""
    made = []
    for c in CATEGORIES:
        for sub in ("raw", "degraded", "meta"):
            d = os.path.join(ROOT, c, sub)
            if not os.path.isdir(d):
                os.makedirs(d)
                made.append(d)
    reg = os.path.join(ROOT, "REGISTRY.json")
    if not os.path.exists(reg):
        with open(reg, "w") as f:
            json.dump({"version": BENCHMARK_VERSION, "samples": {}}, f,
                      indent=2)
    return made


# --------------------------------------------------------------------------
# Approved sources - CURATED, never scraped
# --------------------------------------------------------------------------
# Each entry: what it is, why it is legally usable, and the categories it
# feeds. `url` is the human landing page; a fetcher for a source is only
# added once its terms and a stable download path are confirmed. Absence of a
# `fetch` key means "documented, not yet wired" - deliberate, so nobody
# hard-codes a scrape.

APPROVED_SOURCES = {
    "loc_habs_haer": {
        "name": "Library of Congress - HABS/HAER/HALS",
        "what": "Historic American Buildings/Engineering measured drawings",
        "license": "US Government work - public domain",
        "url": "https://www.loc.gov/pictures/collection/hh/",
        "categories": ["architectural", "surveys", "dimensions", "symbols"],
    },
    "usgs_topo": {
        "name": "USGS Historical Topographic Maps",
        "what": "Surveyed maps with legends, scales, and dimension text",
        "license": "US Government work - public domain",
        "url": "https://www.usgs.gov/programs/national-geospatial-program/"
               "historical-topographic-maps-collection",
        "categories": ["site_plans", "surveys", "symbols"],
    },
    "gsa_pbs": {
        "name": "GSA Public Buildings Service reference drawings",
        "what": "Federal building plans and standards",
        "license": "US Government work - public domain",
        "url": "https://www.gsa.gov/real-estate/design-and-construction",
        "categories": ["architectural", "title_blocks", "dimensions"],
    },
    "nps_technical": {
        "name": "National Park Service preservation drawings",
        "what": "Measured architectural and site drawings",
        "license": "US Government work - public domain",
        "url": "https://www.nps.gov/subjects/hdp/index.htm",
        "categories": ["architectural", "site_plans", "surveys"],
    },
    "oda_samples": {
        "name": "Open Design Alliance sample DWG/DGN files",
        "what": "Reference CAD files for the DWG/DGN converter tier",
        "license": "Vendor sample files - check per-file terms before use",
        "url": "https://www.opendesign.com/",
        "categories": ["vector"],
    },
    "ezdxf_samples": {
        "name": "ezdxf example DXF files",
        "what": "Small, permissively licensed DXF fixtures",
        "license": "MIT (ezdxf project)",
        "url": "https://github.com/mozman/ezdxf",
        "categories": ["vector", "dimensions", "symbols"],
    },
    "university_courseware": {
        "name": "University drafting courseware (open)",
        "what": "Teaching plates: floor plans, sections, dimensioning",
        "license": "Per-institution open-courseware terms - verify per item",
        "url": "https://ocw.mit.edu/",
        "categories": ["architectural", "dimensions", "handwriting"],
    },
    "gpo_engineering_manuals": {
        "name": "US GPO / USACE engineering manuals",
        "what": "Army Corps of Engineers manuals with plates and details",
        "license": "US Government work - public domain",
        "url": "https://www.publications.usace.army.mil/",
        "categories": ["site_plans", "dimensions", "symbols"],
    },
}


def list_sources():
    for sid, s in APPROVED_SOURCES.items():
        wired = "fetch" in s
        print(f"  [{sid}]  {s['name']}")
        print(f"       {s['what']}")
        print(f"       license: {s['license']}")
        print(f"       feeds:   {', '.join(s['categories'])}")
        print(f"       fetch:   {'wired' if wired else 'documented only'}")
        print()


def fetch(source_id=None):
    """Curated download from approved sources. Network-gated.

    No source is wired with an automatic downloader yet - each needs its
    terms and a stable path confirmed first (that confirmation is a human
    decision, recorded in DECISIONS.md, not something to guess at). This
    function is the single sanctioned entry point so that when a fetcher is
    added it lands here, inside the approved registry, and never as an
    ad-hoc scrape elsewhere in the codebase.
    """
    ids = [source_id] if source_id else list(APPROVED_SOURCES)
    for sid in ids:
        s = APPROVED_SOURCES.get(sid)
        if not s:
            print(f"  unknown source: {sid}")
            continue
        if "fetch" not in s:
            print(f"  [{sid}] documented, no wired fetcher yet - download "
                  f"manually from {s['url']} into "
                  f"{os.path.join(ROOT, s['categories'][0], 'raw')} and run "
                  f"`ingest`.")
            continue
        try:
            s["fetch"](ROOT)          # pragma: no cover - net-gated
        except Exception as e:        # pragma: no cover
            print(f"  [{sid}] fetch failed ({e}). Skipping - this is expected "
                  f"offline; the synthetic pipeline does not need it.")


# --------------------------------------------------------------------------
# Real downloaders for approved public-domain sources
# --------------------------------------------------------------------------
# Network-gated: these run on a CONNECTED machine (the dev sandbox has no
# network). Stdlib only (urllib - no extra dependency); polite (a descriptive
# User-Agent, rate-limited, capped); and they pull ONLY from the named
# public-domain collection via its official API, recording per-file license
# and provenance. This is curated fetch (DECISIONS.md #7), never a scrape.
#
# NOTE: the Library of Congress JSON shape (results[].image_url) matches the
# documented API; confirm on the first live run and adjust the two marked
# lines if LoC changes it.

import time as _time
import urllib.request as _ureq

_UA = ("Drawing2CAD-dataset-builder/1.0 "
       "(personal research; public-domain Library of Congress content)")


def _http_json(url, timeout=30):
    req = _ureq.Request(url, headers={"User-Agent": _UA,
                                      "Accept": "application/json"})
    with _ureq.urlopen(req, timeout=timeout) as r:
        return json.load(r)


def _download(url, path, timeout=60):
    req = _ureq.Request(url, headers={"User-Agent": _UA})
    with _ureq.urlopen(req, timeout=timeout) as r, open(path, "wb") as f:
        f.write(r.read())


def fetch_loc(root, collection="historic-american-buildings-survey",
              category="architectural", count=25, delay=2.0):
    """Download measured drawings from a Library of Congress collection via its
    public JSON API. US Government work - public domain. Polite and capped.

    collection examples: 'historic-american-buildings-survey' (HABS),
    'historic-american-engineering-record' (HAER)."""
    init_tree()
    raw = os.path.join(root, category, "raw")
    meta = os.path.join(root, category, "meta")
    got, page = 0, 1
    while got < count:
        api = (f"https://www.loc.gov/collections/{collection}/"
               f"?fo=json&at=results&c=25&sp={page}"
               f"&fa=online-format:image")
        try:
            data = _http_json(api)
        except Exception as e:
            print(f"  LoC page {page} failed ({e}) - stopping.")
            break
        results = data.get("results") or []         # <-- confirm shape
        if not results:
            break
        for item in results:
            if got >= count:
                break
            urls = item.get("image_url") or []       # <-- confirm shape
            if not urls:
                continue
            img_url = urls[-1]                        # largest offered
            if img_url.startswith("//"):
                img_url = "https:" + img_url
            name = f"loc_{collection[:10]}_{got:04d}.jpg"
            try:
                _download(img_url, os.path.join(raw, name))
            except Exception as e:
                print(f"  skip {name}: {e}")
                continue
            rec = {"source": "loc_habs_haer",
                   "license": "US Government work - public domain",
                   "collection": collection,
                   "loc_url": item.get("id") or item.get("url"),
                   "title": (item.get("title") or "")[:200],
                   "image_url": img_url, "category": category,
                   "created": _now()}
            with open(os.path.join(meta, name + ".json"), "w") as f:
                json.dump(_jsonable(rec), f, indent=2)
            got += 1
            print(f"  [{got}/{count}] {name}")
            _time.sleep(delay)                        # be kind to the API
        page += 1
    print(f"  LoC: downloaded {got} drawing(s) into {raw}")
    return got


def _fetch_loc_habs(root):
    return fetch_loc(root, "historic-american-buildings-survey",
                     "architectural", count=25)


# attach the wired downloader to its approved-source entry
APPROVED_SOURCES["loc_habs_haer"]["fetch"] = _fetch_loc_habs


# --------------------------------------------------------------------------
# Synthetic degradation library - fully local, the core of the corpus
# --------------------------------------------------------------------------
# Each degradation takes (img_gray, rng, **p) -> img_gray and returns a
# realistic hard version of a clean drawing. Every applied degradation is
# recorded in the sample's metadata so a training target is never ambiguous
# about what was done to it. Geometry is NOT moved by pixel-space noise
# degradations; the ones that move geometry (rotate, skew, perspective)
# return the transform so ground-truth coordinates can be mapped too.


def deg_rotate(img, rng, deg=None):
    deg = rng.uniform(-4, 4) if deg is None else deg
    h, w = img.shape[:2]
    M = cv2.getRotationMatrix2D((w / 2, h / 2), deg, 1.0)
    out = cv2.warpAffine(img, M, (w, h), flags=cv2.INTER_LINEAR,
                         borderValue=255)
    return out, {"deg": round(float(deg), 2), "matrix": M.tolist()}


def deg_skew(img, rng, k=None):
    k = rng.uniform(-0.06, 0.06) if k is None else k
    h, w = img.shape[:2]
    M = np.float32([[1, k, 0], [0, 1, 0]])
    out = cv2.warpAffine(img, M, (w, h), borderValue=255)
    return out, {"shear": round(float(k), 3), "matrix": M.tolist()}


def deg_perspective(img, rng, amount=None):
    amount = rng.uniform(0.02, 0.08) if amount is None else amount
    h, w = img.shape[:2]
    d = amount * min(h, w)
    src = np.float32([[0, 0], [w, 0], [w, h], [0, h]])
    j = lambda: rng.uniform(-d, d)
    dst = np.float32([[j(), j()], [w + j(), j()],
                      [w + j(), h + j()], [j(), h + j()]])
    M = cv2.getPerspectiveTransform(src, dst)
    out = cv2.warpPerspective(img, M, (w, h), borderValue=255)
    return out, {"amount": round(float(amount), 3), "matrix": M.tolist()}


def deg_blur(img, rng, k=None):
    k = int(rng.choice([3, 5, 7])) if k is None else k
    return cv2.GaussianBlur(img, (k, k), 0), {"kernel": k}


def deg_scanner_noise(img, rng, density=None):
    density = rng.uniform(0.004, 0.02) if density is None else density
    n = rng.random(img.shape)
    out = img.copy()
    out[n < density] = 0
    out[n > 1 - density] = 255
    return out, {"density": round(float(density), 4)}


def deg_jpeg(img, rng, quality=None):
    quality = int(rng.integers(25, 60)) if quality is None else quality
    ok, buf = cv2.imencode(".jpg", img,
                           [cv2.IMWRITE_JPEG_QUALITY, quality])
    out = cv2.imdecode(buf, cv2.IMREAD_GRAYSCALE) if ok else img
    return out, {"quality": quality}


def deg_stain(img, rng, n=None):
    n = int(rng.integers(1, 4)) if n is None else n
    h, w = img.shape[:2]
    out = img.copy().astype(np.float32)
    marks = []
    for _ in range(n):
        cx, cy = int(rng.integers(0, w)), int(rng.integers(0, h))
        r = int(rng.integers(min(h, w) // 12, min(h, w) // 5))
        darkness = rng.uniform(0.5, 0.85)
        mask = np.zeros((h, w), np.float32)
        cv2.circle(mask, (cx, cy), r, 1.0, -1)
        mask = cv2.GaussianBlur(mask, (0, 0), r / 2.5)
        out *= (1 - mask * (1 - darkness))
        marks.append({"c": [cx, cy], "r": r})
    return np.clip(out, 0, 255).astype(np.uint8), {"stains": marks}


def deg_fold(img, rng, n=None):
    n = int(rng.integers(1, 3)) if n is None else n
    h, w = img.shape[:2]
    out = img.astype(np.float32)
    lines = []
    for _ in range(n):
        horizontal = bool(rng.integers(0, 2))
        pos = int(rng.integers(int(0.2 * (h if horizontal else w)),
                               int(0.8 * (h if horizontal else w))))
        band = np.zeros((h, w), np.float32)
        if horizontal:
            band[max(0, pos - 1):pos + 2, :] = 1.0
        else:
            band[:, max(0, pos - 1):pos + 2] = 1.0
        band = cv2.GaussianBlur(band, (0, 0), 2.0)
        out *= (1 - band * rng.uniform(0.15, 0.35))
        lines.append({"horizontal": horizontal, "pos": pos})
    return np.clip(out, 0, 255).astype(np.uint8), {"folds": lines}


def deg_shadow(img, rng):
    h, w = img.shape[:2]
    gx = rng.uniform(0.55, 0.9)
    axis = int(rng.integers(0, 2))
    ramp = np.linspace(gx, 1.0, w if axis else h)
    grad = np.tile(ramp, (h, 1)) if axis else np.tile(ramp[:, None], (1, w))
    out = np.clip(img.astype(np.float32) * grad, 0, 255).astype(np.uint8)
    return out, {"min_gain": round(float(gx), 2), "axis": axis}


def deg_faded_ink(img, rng, amount=None):
    amount = rng.uniform(0.25, 0.55) if amount is None else amount
    # lift the blacks toward gray -> faded lines
    out = (img.astype(np.float32) * (1 - amount) + 255 * amount)
    return np.clip(out, 0, 255).astype(np.uint8), \
        {"amount": round(float(amount), 2)}


def deg_low_dpi(img, rng, factor=None):
    factor = rng.uniform(0.35, 0.6) if factor is None else factor
    h, w = img.shape[:2]
    small = cv2.resize(img, (max(1, int(w * factor)), max(1, int(h * factor))),
                       interpolation=cv2.INTER_AREA)
    out = cv2.resize(small, (w, h), interpolation=cv2.INTER_LINEAR)
    return out, {"factor": round(float(factor), 2)}


def deg_photocopy(img, rng):
    # high-contrast threshold with grain - the classic Nth-generation copy
    n = rng.integers(0, 255, img.shape, dtype=np.uint8)
    out = img.copy()
    out[n < 6] = 0
    thr = int(rng.integers(150, 200))
    out = np.where(out > thr, 255, out).astype(np.uint8)
    out = cv2.GaussianBlur(out, (3, 3), 0)
    return out, {"threshold": thr}


# name -> (function, moves_geometry?)
DEGRADATIONS = {
    "rotate": (deg_rotate, True),
    "skew": (deg_skew, True),
    "perspective": (deg_perspective, True),
    "blur": (deg_blur, False),
    "scanner_noise": (deg_scanner_noise, False),
    "jpeg": (deg_jpeg, False),
    "stain": (deg_stain, False),
    "fold": (deg_fold, False),
    "shadow": (deg_shadow, False),
    "faded_ink": (deg_faded_ink, False),
    "low_dpi": (deg_low_dpi, False),
    "photocopy": (deg_photocopy, False),
}

# Realistic combinations that mimic named real-world conditions. A variant
# picks one recipe so the corpus spans the failure modes we actually see.
RECIPES = {
    "clean_flatbed": [],
    "office_scan": ["skew", "scanner_noise", "jpeg"],
    "old_photocopy": ["photocopy", "faded_ink", "fold"],
    "phone_capture": ["perspective", "shadow", "blur", "jpeg"],
    "faxed": ["low_dpi", "photocopy", "scanner_noise"],
    "archived_survey": ["rotate", "stain", "fold", "faded_ink"],
    "bad_light_photo": ["perspective", "shadow", "blur"],
    # appearance-only (no geometry move): degrades scan QUALITY while leaving
    # every pixel's coordinate put, so ground-truth geometry stays valid. Used
    # by the hard-case benchmark tier to measure robustness without needing to
    # transform the truth.
    "appearance_hard": ["faded_ink", "scanner_noise", "low_dpi", "photocopy"],
}

# Recipes that move no geometry - safe to score against untransformed truth.
APPEARANCE_ONLY = ("clean_flatbed", "old_photocopy", "faxed",
                   "appearance_hard")


def degrade(img, rng, recipe=None):
    """Apply one recipe (or a random one). Return (image, record).

    record["degradations"] lists each step and its params; record["geometry_
    transforms"] chains the affine/perspective matrices so caller can map
    ground-truth coordinates through them.
    """
    if img.ndim == 3:
        img = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)
    if recipe is None:
        recipe = str(rng.choice(list(RECIPES)))
    steps = RECIPES.get(recipe, [])
    applied, transforms = [], []
    out = img
    for name in steps:
        fn, moves = DEGRADATIONS[name]
        out, params = fn(out, rng)
        applied.append({"name": name, "params": params})
        if moves and "matrix" in params:
            transforms.append({"name": name, "matrix": params["matrix"]})
    return out, {"recipe": recipe, "degradations": applied,
                 "geometry_transforms": transforms}


def degrade_file(path, n=8, seed=0, category="poor_scans"):
    """Make `n` degraded variants of one image, with metadata sidecars."""
    img = cv2.imread(path, cv2.IMREAD_GRAYSCALE)
    if img is None:
        raise SystemExit(f"cannot read image: {path}")
    init_tree()
    out_dir = os.path.join(ROOT, category, "degraded")
    meta_dir = os.path.join(ROOT, category, "meta")
    base = os.path.splitext(os.path.basename(path))[0]
    src_hash = _sha(img)
    recipes = list(RECIPES)
    written = []
    for i in range(n):
        rng = np.random.default_rng(seed + i)
        recipe = recipes[i % len(recipes)]      # cover recipes evenly
        out, rec = degrade(img, rng, recipe=recipe)
        name = f"{base}__{recipe}__{i:02d}.png"
        cv2.imwrite(os.path.join(out_dir, name), out)
        rec.update({"source_image": os.path.basename(path),
                    "source_sha": src_hash, "category": category,
                    "variant": i, "created": _now()})
        with open(os.path.join(meta_dir, name + ".json"), "w") as f:
            json.dump(_jsonable(rec), f, indent=2)
        written.append(name)
    return written


# --------------------------------------------------------------------------
# Synthetic ground-truth drawings (reuses benchmark.py's generator)
# --------------------------------------------------------------------------

def synth(n=20, seed=100):
    """Generate synthetic plans WITH ground truth, then degrade each.

    Leans on benchmark.generate_plan/render so the synthetic training data
    matches the synthetic benchmark exactly - one generator, no drift.
    """
    import random
    try:
        import benchmark
    except Exception as e:
        raise SystemExit(f"need benchmark.py for synthetic generation: {e}")
    init_tree()
    raw_dir = os.path.join(ROOT, "architectural", "raw")
    meta_dir = os.path.join(ROOT, "architectural", "meta")
    recipes = list(RECIPES)
    scale = 1.0 / benchmark.PX_PER_FT      # ground-truth ft per pixel
    made = []
    for i in range(n):
        # generate_plan wants a python Random; render wants a numpy rng.
        pyrng = random.Random(seed + i)
        rng = np.random.default_rng(seed + i)
        segs, labels, dims, circles, dashes = benchmark.generate_plan(pyrng)
        dirty = bool(i % 2)
        img, truth_px, truth_circ, truth_dash = benchmark.render(
            segs, labels, rng, dirty=dirty, circles=circles, dashes=dashes)
        recipe = recipes[i % len(recipes)]
        dimg, rec = degrade(img, rng, recipe=recipe)
        name = f"synth_{i:03d}__{recipe}.png"
        cv2.imwrite(os.path.join(raw_dir, name), dimg)
        truth = {
            "segments_px": [[list(a), list(b)] for a, b in truth_px],
            "circles_px": [[list(c), r] for c, r in truth_circ],
            "dashes_px": [[list(a), list(b)] for a, b in truth_dash],
            "labels": [{"text": t, "rot": r} for t, _, _, r in labels],
            "scale_ft_per_px": scale,
        }
        rec.update({"category": "architectural", "synthetic": True,
                    "ground_truth": truth, "source_sha": _sha(dimg),
                    "created": _now()})
        with open(os.path.join(meta_dir, name + ".json"), "w") as f:
            json.dump(_jsonable(rec), f, indent=2)
        made.append(name)
    return made


# --------------------------------------------------------------------------
# De-dup + deterministic split
# --------------------------------------------------------------------------

def _jsonable(o):
    """Recursively convert numpy scalars/arrays to plain Python for json."""
    if isinstance(o, dict):
        return {k: _jsonable(v) for k, v in o.items()}
    if isinstance(o, (list, tuple)):
        return [_jsonable(v) for v in o]
    if isinstance(o, np.generic):
        return o.item()
    if isinstance(o, np.ndarray):
        return o.tolist()
    return o


def _sha(img):
    return hashlib.sha1(np.ascontiguousarray(img)).hexdigest()


def _now():
    return time.strftime("%Y-%m-%dT%H:%M:%S")


def _split_for(sha):
    """Deterministic, dedup-safe split from a content hash.

    Hashing content (not filename) means the same drawing always lands in the
    same split - it can never leak between train and benchmark, which would
    silently inflate scores.
    """
    v = int(sha[:8], 16) % 100
    if v < 70:
        return "train"
    if v < 85:
        return "validation"
    return "benchmark"


def split():
    """Walk every meta sidecar, assign a split by content hash, dedup."""
    seen, assign = {}, {s: [] for s in SPLITS}
    dupes = 0
    for c in CATEGORIES:
        meta_dir = os.path.join(ROOT, c, "meta")
        if not os.path.isdir(meta_dir):
            continue
        for fn in sorted(os.listdir(meta_dir)):
            if not fn.endswith(".json"):
                continue
            p = os.path.join(meta_dir, fn)
            with open(p) as f:
                rec = json.load(f)
            sha = rec.get("source_sha")
            if not sha:
                continue
            if sha in seen:
                dupes += 1
                rec["split"] = seen[sha]
                rec["duplicate_of"] = sha
            else:
                sp = _split_for(sha)
                seen[sha] = sp
                rec["split"] = sp
                assign[sp].append(fn)
            with open(p, "w") as f:
                json.dump(_jsonable(rec), f, indent=2)
    manifest = os.path.join(ROOT, "SPLIT.json")
    with open(manifest, "w") as f:
        json.dump({"counts": {s: len(assign[s]) for s in SPLITS},
                   "duplicates_merged": dupes, "created": _now()}, f, indent=2)
    return assign, dupes


def stats():
    """Print corpus health per category and split."""
    if not os.path.isdir(ROOT):
        print(f"no corpus yet at {ROOT} - run `init` then `synth`/`degrade`.")
        return
    print(f"corpus: {ROOT}   (benchmark v{BENCHMARK_VERSION})")
    print("-" * 52)
    total = 0
    for c in CATEGORIES:
        raw = _count(os.path.join(ROOT, c, "raw"))
        deg = _count(os.path.join(ROOT, c, "degraded"))
        total += raw + deg
        if raw or deg:
            print(f"  {c:14s}  raw {raw:4d}   degraded {deg:4d}")
    print("-" * 52)
    print(f"  total images: {total}")
    sp = os.path.join(ROOT, "SPLIT.json")
    if os.path.exists(sp):
        with open(sp) as f:
            s = json.load(f)
        print(f"  split: {s['counts']}   dedup merged: "
              f"{s['duplicates_merged']}")
    else:
        print("  split: not assigned yet - run `split`.")


def _count(d):
    if not os.path.isdir(d):
        return 0
    return sum(1 for f in os.listdir(d)
               if f.lower().endswith((".png", ".jpg", ".jpeg", ".tif",
                                      ".tiff")))


# --------------------------------------------------------------------------
# CLI
# --------------------------------------------------------------------------

def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = ap.add_subparsers(dest="cmd", required=True)
    sub.add_parser("init", help="create the folder tree")
    sub.add_parser("sources", help="list approved curated sources")
    sub.add_parser("stats", help="corpus health")
    sub.add_parser("split", help="assign train/validation/benchmark")

    d = sub.add_parser("degrade", help="make degraded variants of an image")
    d.add_argument("image")
    d.add_argument("-n", type=int, default=8)
    d.add_argument("--category", default="poor_scans", choices=CATEGORIES)
    d.add_argument("--seed", type=int, default=0)

    s = sub.add_parser("synth", help="generate synthetic plans + ground truth")
    s.add_argument("-n", type=int, default=20)
    s.add_argument("--seed", type=int, default=100)

    f = sub.add_parser("fetch", help="curated download (network-gated)")
    f.add_argument("--source", default=None)

    args = ap.parse_args(argv)
    if args.cmd == "init":
        made = init_tree()
        print(f"corpus root: {ROOT}")
        print(f"created {len(made)} folders" if made else "already initialized")
    elif args.cmd == "sources":
        list_sources()
    elif args.cmd == "degrade":
        w = degrade_file(args.image, n=args.n, seed=args.seed,
                         category=args.category)
        print(f"wrote {len(w)} degraded variants to "
              f"{os.path.join(ROOT, args.category, 'degraded')}")
    elif args.cmd == "synth":
        m = synth(n=args.n, seed=args.seed)
        print(f"generated {len(m)} synthetic drawings with ground truth")
    elif args.cmd == "fetch":
        fetch(args.source)
    elif args.cmd == "split":
        assign, dupes = split()
        print(f"split: " + ", ".join(f"{k} {len(v)}"
                                     for k, v in assign.items())
              + f"   (dedup merged {dupes})")
    elif args.cmd == "stats":
        stats()


if __name__ == "__main__":
    main()
