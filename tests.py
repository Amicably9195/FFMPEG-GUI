#!/usr/bin/env python3
"""tests - dependency-free regression tests for Drawing2CAD's deterministic core.

Run with:  python tests.py       (no pytest needed - works anywhere Codex or
CI runs, no installs, matching the project's local/free ethos).

These lock in the *faithfulness invariants* the whole project rests on, so an
interchangeable engineer (Claude Code or ChatGPT Codex) cannot silently break
them:

  * the reader's dimension re-punctuation NEVER edits non-dimension text
  * the lint pass NEVER mutates the geometry it inspects (advisory only)
  * lint stays high-precision (a clean closed plan yields 0 actionable)
  * dataset de-dup keeps a drawing's variants in ONE split (no leakage)

`benchmark.py` grades quality; this grades correctness of the pieces the
benchmark can't isolate. Both run before every push.
"""

import json
import math

import cv2
import numpy as np

_fails = []
_count = 0


def check(cond, msg):
    global _count
    _count += 1
    if not cond:
        _fails.append(msg)
        print(f"  FAIL: {msg}")
    else:
        print(f"  ok:   {msg}")


def eq(a, b, msg):
    check(a == b, f"{msg}  (got {a!r}, want {b!r})")


# --------------------------------------------------------------------------
# smart_ocr.normalize_dimension - faithful re-punctuation, never invention
# --------------------------------------------------------------------------

def test_normalize_dimension():
    import smart_ocr as s
    print("smart_ocr.normalize_dimension")
    # reconstructs dropped/partial feet-inch marks
    eq(s.normalize_dimension("7-0"), "7'-0\"", "both marks dropped")
    eq(s.normalize_dimension("11-10\""), "11'-10\"", "foot mark dropped")
    eq(s.normalize_dimension("7'-8"), "7'-8\"", "inch mark dropped")
    eq(s.normalize_dimension("45-9"), "45'-9\"", "bare hyphenated")
    eq(s.normalize_dimension("22'-10"), "22'-10\"", "trailing inch dropped")
    # NEVER touches non-dimensions (the invariant that keeps it faithful)
    for t in ("BATH", "NORTH", "971", "23", "V.I.F.", "SCALE", "12",
              "MASTER BR", "8'-0\"", "A-1", "1-1/2"):
        eq(s.normalize_dimension(t), t, f"untouched: {t!r}")


# --------------------------------------------------------------------------
# scan2cad.parse_dimension
# --------------------------------------------------------------------------

def test_parse_dimension():
    import scan2cad as c
    print("scan2cad.parse_dimension")
    check(abs(c.parse_dimension("40.00'") - 40.0) < 1e-6, "40.00' -> 40")
    check(abs(c.parse_dimension("100'") - 100.0) < 1e-6, "100' -> 100")
    check(abs(c.parse_dimension("5'-6\"") - 5.5) < 1e-6, "5'-6\" -> 5.5")
    check(c.parse_dimension("BATH") is None, "room name -> None")
    check(c.parse_dimension("26-2") is None, "bare grid ref -> None")
    check(c.parse_dimension("971") is None, "bare number -> None")


# --------------------------------------------------------------------------
# verify - advisory only, high precision
# --------------------------------------------------------------------------

def _types(findings):
    return {f["type"] for f in findings}


def test_verify_never_mutates():
    import verify
    print("verify.check - never mutates input (advisory only)")
    segs = [[0, 0, 100, 0], [0, 1, 100, 1]]
    before = json.dumps(segs)
    verify.check(segs)
    eq(json.dumps(segs), before, "input segments unchanged after check")


def test_verify_clean_plan():
    import verify
    print("verify.check - clean closed square is 0 actionable")
    square = [[0, 0, 100, 0], [100, 0, 100, 100],
              [100, 100, 0, 100], [0, 100, 0, 0]]
    f = verify.check(square)
    s = verify.summarize(f)
    eq(s["by_severity"]["high"] + s["by_severity"]["medium"], 0,
       "clean square: 0 high+medium findings")


def test_verify_detects_defects():
    import verify
    print("verify.check - detects real defects")
    # doubled wall
    dup = verify.check([[0, 0, 100, 0], [0, 1, 100, 1]])
    check("duplicate" in _types(dup), "doubled wall -> duplicate")
    # impossible intersection (cross with no shared vertex)
    x = verify.check([[0, 50, 100, 50], [50, 0, 50, 100]])
    check("impossible_intersection" in _types(x),
          "crossing walls -> impossible_intersection")
    # open corner (two long walls nearly meet, angled, with a gap)
    op = verify.check([[0, 0, 0, 100], [8, 100, 100, 100]])
    check("open_polygon" in _types(op), "gapped corner -> open_polygon")
    # dimension mismatch: 100px line at 1 ft/px = 100 ft, labeled 50'
    w = {"text": "50'"}
    dm = verify.check([[0, 0, 100, 0]], dims=[(w, [0, 0, 100, 0])],
                      scale=1.0, units_feet=True)
    check("dimension_mismatch" in _types(dm),
          "label disagrees with geometry -> dimension_mismatch")
    check(any(f["severity"] == "high" for f in dm
              if f["type"] == "dimension_mismatch"),
          "dimension_mismatch is high severity")


# --------------------------------------------------------------------------
# scan2cad._enhance_faded_ocr - clean scans must pass through untouched
# --------------------------------------------------------------------------

def test_enhance_faded_ocr_gate():
    import scan2cad as c
    print("scan2cad._enhance_faded_ocr - clean untouched, faded enhanced")
    rng = np.random.default_rng(0)
    # clean scan: white ground with true-black strokes -> must be UNTOUCHED
    clean = np.full((80, 120), 255, np.uint8)
    cv2.line(clean, (10, 40), (110, 40), 0, 3)
    cv2.putText(clean, "24'-0\"", (20, 30), cv2.FONT_HERSHEY_SIMPLEX, 0.6, 0, 2)
    out = c._enhance_faded_ocr(clean)
    check(np.array_equal(out, clean),
          "clean (true-black) scan passes through byte-identical")
    # faded scan: darkest strokes are gray -> enhancer engages and changes it
    faded = np.clip(clean.astype(np.float32) * 0.4 + 150, 0, 255).astype(np.uint8)
    out2 = c._enhance_faded_ocr(faded)
    check(not np.array_equal(out2, faded), "faded scan is contrast-restored")
    check(out2.shape == faded.shape, "shape preserved")


# --------------------------------------------------------------------------
# scan2cad._verify_ring - the gate that keeps circle recovery faithful
# --------------------------------------------------------------------------

def test_verify_ring_gate():
    import scan2cad as c
    print("scan2cad._verify_ring - accepts real rings, rejects non-rings")
    ink = np.zeros((120, 120), np.uint8)
    cv2.circle(ink, (60, 60), 30, 255, 2)          # a full drawn ring
    conf = c._verify_ring(ink, 60, 60, 30, 8, 300)
    check(conf is not None and conf > 0, "full ring accepted")
    # an L of two walls meeting at a corner is NOT a ring
    corner = np.zeros((120, 120), np.uint8)
    cv2.line(corner, (60, 60), (110, 60), 255, 2)
    cv2.line(corner, (60, 60), (60, 110), 255, 2)
    check(c._verify_ring(corner, 60, 60, 30, 8, 300) is None,
          "wall corner rejected (not a full turn)")
    # a rectangular room is not a ring at the inscribed radius either
    room = np.zeros((120, 120), np.uint8)
    cv2.rectangle(room, (30, 30), (90, 90), 255, 2)
    check(c._verify_ring(room, 60, 60, 30, 8, 300) is None,
          "rectangular room rejected")


# --------------------------------------------------------------------------
# dataset_builder - split determinism, dedup, json safety
# --------------------------------------------------------------------------

def test_dataset_split_deterministic():
    import dataset_builder as d
    print("dataset_builder split + dedup")
    sha = "deadbeef" * 5
    eq(d._split_for(sha), d._split_for(sha), "same hash -> same split")
    check(d._split_for(sha) in d.SPLITS, "split is a valid split name")


def test_dataset_degrade_records():
    import dataset_builder as d
    print("dataset_builder.degrade records what it did")
    img = np.full((60, 120), 255, np.uint8)
    rng = np.random.default_rng(0)
    out, rec = d.degrade(img, rng, recipe="office_scan")
    eq(rec["recipe"], "office_scan", "recipe recorded")
    check(len(rec["degradations"]) > 0, "degradations listed")
    check(out.shape == img.shape, "shape preserved by office_scan")
    # a geometry-moving recipe records its transforms for ground-truth mapping
    out2, rec2 = d.degrade(img, np.random.default_rng(1),
                           recipe="archived_survey")
    check(len(rec2["geometry_transforms"]) > 0,
          "rotate/skew recipe records geometry transforms")


def test_dataset_jsonable():
    import dataset_builder as d
    print("dataset_builder._jsonable makes numpy json-safe")
    obj = {"i": np.int64(3), "f": np.float64(1.5),
           "a": np.arange(3), "nested": [np.int32(7)]}
    clean = d._jsonable(obj)
    try:
        json.dumps(clean)
        ok = True
    except TypeError:
        ok = False
    check(ok, "sanitized object is json-serializable")
    eq(clean["i"], 3, "int64 -> python int")


# --------------------------------------------------------------------------
# verify.summarize
# --------------------------------------------------------------------------

def test_verify_summarize():
    import verify
    print("verify.summarize - severity/type tallies")
    findings = [
        {"type": "duplicate", "severity": "medium", "at": [0, 0]},
        {"type": "sliver", "severity": "low", "at": [1, 1]},
        {"type": "sliver", "severity": "low", "at": [2, 2]},
    ]
    s = verify.summarize(findings)
    eq(s["total"], 3, "total counted")
    eq(s["by_type"]["sliver"], 2, "by_type tallies slivers")
    eq(s["by_severity"]["low"], 2, "by_severity tallies low")
    eq(s["by_severity"]["medium"], 1, "by_severity tallies medium")
    eq(verify.summarize([])["total"], 0, "empty -> 0 total")


# --------------------------------------------------------------------------
# provenance - never lose information
# --------------------------------------------------------------------------

def test_provenance_never_loses_information():
    import provenance
    print("provenance.build_records - never lose information")
    # one of every kind of input, incl. an UNCLASSIFIED curve
    segments = [(0, 0, 10, 0)]
    curves = [([(1, 1), (2, 2), (3, 1)], False)]     # unknown geometry
    rounds = [("circle", 5, 5, 4, 0.30)]             # low-confidence circle
    words = [{"text": "BATH", "conf": 90, "x": 0, "y": 0, "w": 5, "h": 5,
              "rotation": 0, "review": False}]
    rec = provenance.build_records(segments=segments, curves=curves,
                                   rounds=rounds, words=words)
    eq(len(rec), 4, "one record per input object (nothing dropped)")
    poly = [r for r in rec if r["type"] == "polyline"]
    eq(len(poly), 1, "unclassified curve is KEPT as a polyline")
    check(poly[0]["review"] is True,
          "unclassified geometry is flagged for review, not deleted")
    circ = [r for r in rec if r["type"] == "circle"][0]
    check(circ["review"] is True, "low-confidence circle flagged for review")


def test_provenance_tiers():
    import provenance
    print("provenance.tier - green/yellow/red review tiers")
    eq(provenance.tier(0.95), "green", "high confidence -> green")
    eq(provenance.tier(0.6), "yellow", "moderate confidence -> yellow")
    eq(provenance.tier(0.2), "red", "low confidence -> red")
    eq(provenance.tier(0.99, review=True), "red",
       "flagged-for-review is always red, however high the score")
    # tiers stamped on records and counted in the summary
    rec = provenance.build_records(
        segments=[(0, 0, 400, 0)],                    # long line -> green
        words=[{"text": "?", "conf": 20, "x": 0, "y": 0, "w": 5, "h": 5,
                "rotation": 0, "review": True}])       # flagged -> red
    tiers = {r["type"]: r["tier"] for r in rec}
    eq(tiers["line"], "green", "confident long line stamped green")
    eq(tiers["text"], "red", "flagged text stamped red")
    s = provenance.summarize(rec)
    eq(s["_tiers"]["green"], 1, "summary counts one green")
    eq(s["_tiers"]["red"], 1, "summary counts one red")


def test_provenance_summarize():
    import provenance
    print("provenance.summarize - per-type averages + review count")
    rec = [
        {"type": "line", "confidence": 0.9, "review": False},
        {"type": "line", "confidence": 0.7, "review": False},
        {"type": "text", "confidence": 0.5, "review": True},
    ]
    s = provenance.summarize(rec)
    eq(s["line"]["count"], 2, "line count")
    check(abs(s["line"]["avg_confidence"] - 0.8) < 1e-6, "line avg confidence")
    eq(s["_review_items"], 1, "review items counted")


# --------------------------------------------------------------------------
# corrections - training-pair dedup (one drawing's fix saved once)
# --------------------------------------------------------------------------

def test_corrections_dedup():
    import tempfile
    import corrections
    print("corrections.save_pair - dedup")
    crop = np.full((20, 40), 200, np.uint8)
    with tempfile.TemporaryDirectory() as d:
        corrections.save_pair(crop, "KITCHEN", dataset_dir=d)
        corrections.save_pair(crop, "KITCHEN", dataset_dir=d)   # same pair
        eq(corrections.dataset_size(dataset_dir=d), 1,
           "identical (crop,text) saved once")
        corrections.save_pair(crop, "BEDROOM", dataset_dir=d)   # new label
        eq(corrections.dataset_size(dataset_dir=d), 2,
           "different label saved as a new pair")


def test_estimate_lineweights():
    import scan2cad as c
    print("scan2cad.estimate_lineweights - width hierarchy + uniform gate")
    # three bold strokes (width 9) + three fine strokes (width 3)
    ink = np.zeros((300, 600), np.uint8)
    segs = []
    for y in (40, 70, 100):
        cv2.line(ink, (40, y), (560, y), 255, 9)
        segs.append((40, y, 560, y))
    for y in (180, 210, 240):
        cv2.line(ink, (40, y), (560, y), 255, 3)
        segs.append((40, y, 560, y))
    lw = c.estimate_lineweights(ink, np.array(segs, float))
    check(lw is not None, "varied-width drawing gets lineweights")
    check(all(v == c._LW_THICK for v in lw[:3]), "bold strokes -> thick")
    check(all(v == c._LW_THIN for v in lw[3:]), "fine strokes -> thin")
    check(c._LW_THICK > c._LW_THIN, "thick weight > thin weight")
    # a uniform-width drawing must get nothing (no fabricated hierarchy)
    uni = np.zeros((300, 600), np.uint8)
    us = []
    for y in (40, 70, 100, 130):
        cv2.line(uni, (40, y), (560, y), 255, 4)
        us.append((40, y, 560, y))
    check(c.estimate_lineweights(uni, np.array(us, float)) is None,
          "uniform-width drawing gets no lineweights (nothing invented)")


def test_write_dxf_layers():
    import os
    import tempfile
    import ezdxf
    import scan2cad as c
    print("scan2cad.write_dxf - semantic layer assignment")
    segs = [(0, 0, 100, 0)]
    dashed = [(0, 50, 100, 50)]
    with tempfile.TemporaryDirectory() as d:
        path = os.path.join(d, "layers.dxf")
        c.write_dxf(path, 200, segs, curves=[], words=[], dashed=dashed)
        doc = ezdxf.readfile(path)
        msp = doc.modelspace()
        solid = [e for e in msp if e.dxftype() == "LINE"
                 and e.dxf.linetype != "DASHED"]
        hidden = [e for e in msp if e.dxftype() == "LINE"
                  and e.dxf.linetype == "DASHED"]
        eq(solid[0].dxf.layer, "LINES", "solid linework on LINES layer")
        eq(hidden[0].dxf.layer, "HIDDEN",
           "dashed linework moved to its own HIDDEN layer")


def test_svg_export():
    import os
    import tempfile
    import xml.etree.ElementTree as ET
    import svg_export
    print("svg_export.write_svg - valid SVG, tier-coloured text")
    words = [{"text": "KITCHEN", "conf": 92, "cap": 8, "rotation": 0,
              "insert": (50, 50), "review": False},           # green
             {"text": "8ATH", "conf": 30, "cap": 8, "rotation": 90,
              "insert": (80, 120), "review": True}]            # red
    with tempfile.TemporaryDirectory() as d:
        p = os.path.join(d, "t.svg")
        dims = [({"text": "24'-0\""}, [10, 200, 200, 200])]
        svg_export.write_svg(p, 400, 300, segments=[(10, 10, 200, 10)],
                             curves=[], words=words,
                             rounds=[("circle", 100, 100, 20, 0.9)],
                             dashed=[(10, 50, 200, 50)], dims=dims)
        root = ET.parse(p).getroot()          # must be valid XML
        tags = [e.tag.split("}")[-1] for e in root]
        check(tags.count("line") == 3, "solid + dashed + dimension lines emitted")
        check(tags.count("circle") == 1, "circle emitted")
        texts = {e.text: e.get("fill") for e in root if e.tag.endswith("text")}
        eq(texts.get("KITCHEN"), svg_export._TIER_FILL["green"],
           "confident text drawn green")
        eq(texts.get("8ATH"), svg_export._TIER_FILL["red"],
           "flagged text drawn red")
        check("24'-0\"" in texts, "dimension value drawn in the preview")
        # overlay: a background image embeds as a faint <image>
        p2 = os.path.join(d, "bg.svg")
        bg = np.full((60, 120), 255, np.uint8)
        svg_export.write_svg(p2, 120, 60, segments=[(5, 30, 115, 30)],
                             background=bg)
        imgs = [e for e in ET.parse(p2).getroot() if e.tag.endswith("image")]
        check(len(imgs) == 1 and imgs[0].get("opacity") == "0.30",
              "background embedded as a faint overlay image")


def test_diffview_missed_ink():
    import diffview
    print("diffview.analyze - flags uncaptured source ink, not captured ink")
    src = np.full((120, 300), 255, np.uint8)
    cv2.line(src, (20, 40), (280, 40), 0, 3)     # captured line
    cv2.line(src, (20, 90), (280, 90), 0, 3)     # NOT given to the analyzer
    # only the first line is "recovered"
    frac_full, _ = diffview.analyze(
        src, segments=[(20, 40, 280, 40), (20, 90, 280, 90)])
    check(frac_full < 0.05, "all ink captured -> near-zero missed fraction")
    frac_half, diff = diffview.analyze(src, segments=[(20, 40, 280, 40)])
    check(frac_half > 0.3, "an uncaptured line shows up as missed ink")
    check(diff.shape == (120, 300, 3), "diff image is RGB, source-sized")
    check((diff == (0, 0, 255)).all(axis=2).any(),
          "missed ink is painted red")


def test_convert_stats_summary():
    import os
    import tempfile
    import scan2cad
    print("convert() - returns an enriched summary dict")
    img = np.full((160, 220), 255, np.uint8)
    cv2.rectangle(img, (30, 30), (190, 130), 0, 3)
    with tempfile.TemporaryDirectory() as d:
        p = os.path.join(d, "s.png")
        cv2.imwrite(p, img)
        st = scan2cad.convert(p, os.path.join(d, "s.dxf"), do_page_crop=False,
                              do_deskew=False, do_ocr=False, log=lambda m: None)
        for k in ("lines", "curves", "dimensions", "circles", "dashed",
                  "words", "review", "scale", "units"):
            check(k in st, f"summary has '{k}'")
        check(isinstance(st["dimensions"], int) and st["dimensions"] >= 0,
              "dimensions is a count")


def test_convert_svg_out_end_to_end():
    import os
    import tempfile
    import xml.etree.ElementTree as ET
    import scan2cad
    print("convert(svg_out=True) - writes a valid SVG alongside the DXF")
    img = np.full((160, 220), 255, np.uint8)
    cv2.rectangle(img, (30, 30), (190, 130), 0, 3)      # a simple room
    with tempfile.TemporaryDirectory() as d:
        p = os.path.join(d, "room.png")
        cv2.imwrite(p, img)
        dxf = os.path.join(d, "room.dxf")
        scan2cad.convert(p, dxf, do_page_crop=False, do_deskew=False,
                         do_ocr=False, svg_out=True, log=lambda m: None)
        svg = os.path.join(d, "room.svg")
        check(os.path.exists(svg), "SVG written next to the DXF")
        root = ET.parse(svg).getroot()                  # valid XML
        geom = [e for e in root if e.tag.split("}")[-1]
                in ("line", "polyline", "polygon")]
        check(len(geom) >= 1, "recovered geometry appears in the preview")


def test_write_dxf_text_tiers():
    import os
    import tempfile
    import ezdxf
    import scan2cad as c
    print("scan2cad.write_dxf - text routed to green/yellow/red layers")
    words = [
        {"text": "KITCHEN", "conf": 92, "cap": 8, "rotation": 0,
         "insert": (50, 50), "x": 50, "y": 40, "w": 60, "h": 10,
         "review": False},                                 # green -> TEXT
        {"text": "CLObET", "conf": 55, "cap": 8, "rotation": 0,
         "insert": (50, 90), "x": 50, "y": 80, "w": 60, "h": 10,
         "review": False},                                 # yellow -> TEXT_CHECK
        {"text": "8ATH", "conf": 30, "cap": 8, "rotation": 0,
         "insert": (50, 130), "x": 50, "y": 120, "w": 60, "h": 10,
         "review": True},                                  # red -> TEXT_REVIEW
    ]
    with tempfile.TemporaryDirectory() as d:
        path = os.path.join(d, "text.dxf")
        c.write_dxf(path, 400, segments=[], curves=[], words=words)
        by = {e.dxf.text: e.dxf.layer for e in ezdxf.readfile(path).modelspace()
              if e.dxftype() == "TEXT"}
        eq(by.get("KITCHEN"), "TEXT", "confident text -> green TEXT layer")
        eq(by.get("CLObET"), "TEXT_CHECK",
           "moderate text -> yellow TEXT_CHECK layer")
        eq(by.get("8ATH"), "TEXT_REVIEW", "flagged text -> red TEXT_REVIEW")


def test_corrections_apply_end_to_end():
    import os
    import tempfile
    import ezdxf
    import corrections
    print("corrections.apply_corrections - patch text + promote off review")
    with tempfile.TemporaryDirectory() as d:
        path = os.path.join(d, "drawing.dxf")
        doc = ezdxf.new()
        doc.layers.add("TEXT")
        doc.layers.add("TEXT_REVIEW", color=1)
        msp = doc.modelspace()
        msp.add_text("8ATH", dxfattribs={"layer": "TEXT_REVIEW"})   # a misread
        msp.add_text("KITCHEN", dxfattribs={"layer": "TEXT"})       # a good one
        doc.saveas(path)
        n = corrections.apply_corrections(path, [(0, "BATH", "8ATH")])
        eq(n, 1, "one entity updated")
        out = ezdxf.readfile(path)
        texts = {e.dxf.text: e.dxf.layer for e in out.modelspace()
                 if e.dxftype() == "TEXT"}
        check("BATH" in texts, "misread text was corrected")
        check("8ATH" not in texts, "old misread text is gone")
        eq(texts.get("BATH"), "TEXT", "corrected label promoted off review")
        eq(texts.get("KITCHEN"), "TEXT", "untouched good label stays put")


def main():
    tests = [
        test_normalize_dimension,
        test_parse_dimension,
        test_verify_never_mutates,
        test_verify_clean_plan,
        test_verify_detects_defects,
        test_verify_summarize,
        test_provenance_never_loses_information,
        test_provenance_tiers,
        test_provenance_summarize,
        test_corrections_dedup,
        test_estimate_lineweights,
        test_write_dxf_layers,
        test_write_dxf_text_tiers,
        test_svg_export,
        test_diffview_missed_ink,
        test_convert_stats_summary,
        test_convert_svg_out_end_to_end,
        test_corrections_apply_end_to_end,
        test_enhance_faded_ocr_gate,
        test_verify_ring_gate,
        test_dataset_split_deterministic,
        test_dataset_degrade_records,
        test_dataset_jsonable,
    ]
    for t in tests:
        t()
    print("=" * 52)
    if _fails:
        print(f"FAILED {len(_fails)} of {_count} checks:")
        for m in _fails:
            print(f"  - {m}")
        raise SystemExit(1)
    print(f"PASSED all {_count} checks.")


if __name__ == "__main__":
    main()
