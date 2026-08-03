#!/usr/bin/env python3
"""pdf2cad - Convert PDF drawings to DXF.

Two kinds of PDF, handled automatically per page:
  * Vector PDFs (exported from CAD, most DOB e-filings): the lines and text
    are real vector data inside the file - they are lifted out exactly.
    No OCR, no tracing: perfect geometry, perfect text.
  * Scanned PDFs (paper fed through a scanner): the page is rendered at
    300 DPI and sent through the scan2cad photo pipeline.

Multi-page PDFs produce one DXF per page (name_p1.dxf, name_p2.dxf, ...).
"""

import math
import os
import tempfile

import numpy as np

try:
    import pymupdf as fitz
except ImportError:
    import fitz

import scan2cad

# a page with at least this many vector paths is treated as CAD-exported
VECTOR_MIN_PATHS = 10


def _sample_bezier(p0, p1, p2, p3, n=12):
    t = np.linspace(0.0, 1.0, n)[:, None]
    pts = ((1 - t) ** 3 * p0 + 3 * (1 - t) ** 2 * t * p1 +
           3 * (1 - t) * t ** 2 * p2 + t ** 3 * p3)
    return pts


def _extract_vectors(page):
    """Exact linework from a vector page: (segments Nx4, polylines)."""
    segments, polylines = [], []
    for path in page.get_drawings():
        for item in path["items"]:
            kind = item[0]
            if kind == "l":
                p1, p2 = item[1], item[2]
                segments.append((p1.x, p1.y, p2.x, p2.y))
            elif kind == "re":
                r = item[1]
                pts = np.array([[r.x0, r.y0], [r.x1, r.y0],
                                [r.x1, r.y1], [r.x0, r.y1]], dtype=np.float64)
                polylines.append((pts, True))
            elif kind == "qu":
                q = item[1]
                pts = np.array([[q.ul.x, q.ul.y], [q.ur.x, q.ur.y],
                                [q.lr.x, q.lr.y], [q.ll.x, q.ll.y]],
                               dtype=np.float64)
                polylines.append((pts, True))
            elif kind == "c":
                p0 = np.array([item[1].x, item[1].y])
                p1 = np.array([item[2].x, item[2].y])
                p2 = np.array([item[3].x, item[3].y])
                p3 = np.array([item[4].x, item[4].y])
                polylines.append((_sample_bezier(p0, p1, p2, p3), False))
    segs = np.array(segments) if segments else np.empty((0, 4))
    return segs, polylines


def _extract_text(page):
    """Exact text spans as scan2cad-style word dicts (confidence 100)."""
    words = []
    for block in page.get_text("dict")["blocks"]:
        if block.get("type") != 0:
            continue
        for line in block["lines"]:
            dx, dy = line["dir"]
            # PDF y goes down; CAD rotation is counter-clockwise
            rot = round(math.degrees(math.atan2(-dy, dx))) % 360
            for span in line["spans"]:
                text = span["text"].strip()
                if not text:
                    continue
                x0, y0, x1, y1 = span["bbox"]
                ox, oy = span["origin"]
                words.append(dict(
                    text=text, conf=100.0,
                    x=x0, y=y0, w=x1 - x0, h=y1 - y0,
                    cap=span["size"], rotation=rot,
                    insert=(ox, oy)))
    return words


def _vector_page_to_dxf(page, out_path, auto_scale=True, flag_review=True,
                        log=print):
    segs, polylines = _extract_vectors(page)
    words = _extract_text(page)
    log(f"  vector page: {len(segs)} lines, {len(polylines)} curves, "
        f"{len(words)} text spans lifted exactly (no OCR needed).")

    scale, units_feet = 1.0, False
    for w in words:
        w["dim"] = scan2cad.parse_dimension(w["text"])
    n_dims = sum(1 for w in words if w["dim"])
    if auto_scale and n_dims:
        ftpt = scan2cad.estimate_scale(words, segs)
        if ftpt:
            scale, units_feet = ftpt, True
            bad = [w for w in words if w.get("dim_ok") is False]
            if flag_review:
                for w in bad:
                    w["review"] = True
            log(f"  scale verified from {n_dims} dimensions: "
                f"DXF output is in FEET"
                + (f" ({len(bad)} contradicting labels flagged)." if bad
                   else "."))
        else:
            log("  dimensions present but no consistent scale - "
                "output in PDF points (1 pt = 1/72 inch); scale once in CAD.")

    n = scan2cad.write_dxf(out_path, page.rect.height, segs, polylines,
                           words, scale=scale, min_len_px=0.0,
                           units_feet=units_feet)
    return dict(output=out_path, lines=n, curves=len(polylines),
                words=len(words), units="feet" if units_feet else "points")


def convert_pdf(input_path, output_path=None, log=print, **opts):
    """Convert every page of a PDF. Returns the stats dict of the last page
    with 'output' listing all written files."""
    doc = fitz.open(input_path)
    base = os.path.splitext(output_path or input_path)[0]
    outputs, stats = [], {}
    for i, page in enumerate(doc):
        suffix = "" if doc.page_count == 1 else f"_p{i + 1}"
        out = base + suffix + ".dxf"
        log(f"Page {i + 1}/{doc.page_count}:")
        if len(page.get_drawings()) >= VECTOR_MIN_PATHS:
            stats = _vector_page_to_dxf(
                page, out,
                auto_scale=opts.get("auto_scale", True),
                flag_review=opts.get("flag_review", True), log=log)
        else:
            with tempfile.TemporaryDirectory() as tmp:
                img = os.path.join(tmp, f"page{i + 1}.png")
                embedded = page.get_images()
                if len(embedded) == 1:
                    # scanner PDFs wrap one image per page: extract it at
                    # native resolution instead of re-rendering
                    info = doc.extract_image(embedded[0][0])
                    img = os.path.join(tmp, f"page{i + 1}.{info['ext']}")
                    with open(img, "wb") as f:
                        f.write(info["image"])
                    log(f"  scanned page - extracted embedded "
                        f"{info['width']}x{info['height']} scan ...")
                else:
                    log("  scanned page - rendering at 300 DPI ...")
                    page.get_pixmap(dpi=300).save(img)
                stats = scan2cad.convert(img, out, log=log, **opts)
        outputs.append(out)
        log(f"  -> {out}")
    doc.close()
    stats["output"] = "; ".join(outputs)
    return stats
