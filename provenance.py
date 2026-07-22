#!/usr/bin/env python3
"""provenance - per-object confidence and origin records for Drawing2CAD.

Core principles this module serves:

  * Confidence everywhere - every recovered object carries a 0..1 confidence
    so the review screen can surface the least-certain items first.
  * Never lose information - even objects the software can't classify are
    recorded (as geometry) rather than dropped.
  * Provenance - every object remembers where it came from (source image
    coordinates), how it was reconstructed (method), how sure we are
    (confidence), and whether a human still needs to look (review status).

These records are debugging/training metadata written to a sidecar; they are
NOT baked into the DXF. They let us tell whether a future change actually
improved things, and they feed the correction flywheel.
"""

import json
import math
import os


def _line_conf(x1, y1, x2, y2):
    """Straight lines are deterministic geometry - high, length-scaled trust
    (a 4px nub is less certain than a 400px wall)."""
    length = math.hypot(x2 - x1, y2 - y1)
    return round(min(1.0, 0.85 + length / 400.0), 3)


def build_records(*, segments=(), dashed=(), rounds=(), curves=(),
                  words=(), dims=(), scale=1.0, units_feet=False,
                  scale_conf=None):
    """Assemble one provenance record per recovered object. Coordinates are
    image pixels (the source frame), so a record always points back to where
    it came from. Returns a list of dicts."""
    rec = []

    for x1, y1, x2, y2 in segments:
        rec.append({
            "type": "line", "method": "centerline",
            "confidence": _line_conf(x1, y1, x2, y2),
            "review": False,
            "at": [round(x1, 1), round(y1, 1), round(x2, 1), round(y2, 1)]})

    for x1, y1, x2, y2 in dashed:
        rec.append({
            "type": "dashed_line", "method": "dash-rhythm",
            "confidence": 0.9, "review": False,
            "at": [round(x1, 1), round(y1, 1), round(x2, 1), round(y2, 1)]})

    for ent in rounds:
        conf = float(ent[-1]) if isinstance(ent[-1], (int, float)) else 0.9
        if ent[0] == "circle":
            rec.append({"type": "circle", "method": "ring-fit",
                        "confidence": round(conf, 3), "review": conf < 0.75,
                        "at": [round(ent[1], 1), round(ent[2], 1)],
                        "r": round(ent[3], 1)})
        else:
            rec.append({"type": "arc", "method": "arc-fit",
                        "confidence": round(conf, 3), "review": conf < 0.75,
                        "at": [round(ent[1], 1), round(ent[2], 1)],
                        "r": round(ent[3], 1)})

    for points, closed in curves:
        # unclassified geometry - kept, never dropped, flagged for a look
        xs = [float(p[0]) for p in points]
        ys = [float(p[1]) for p in points]
        rec.append({
            "type": "polyline", "method": "traced-unclassified",
            "confidence": 0.5, "review": True,
            "at": [round(min(xs), 1), round(min(ys), 1),
                   round(max(xs), 1), round(max(ys), 1)],
            "closed": bool(closed), "vertices": len(points)})

    for w in words:
        c = float(w.get("conf", 0)) / 100.0
        rec.append({
            "type": "text", "method": "ocr",
            "text": w["text"], "confidence": round(c, 3),
            "review": bool(w.get("review")),
            "rotation": int(w.get("rotation", 0)),
            "at": [int(w["x"]), int(w["y"]), int(w["w"]), int(w["h"])]})

    for w, span in dims:
        c = float(w.get("conf", 0)) / 100.0
        # a dimension's trust blends its text read with scale agreement
        dc = c if scale_conf is None else 0.5 * c + 0.5 * float(scale_conf)
        rec.append({
            "type": "dimension", "method": "label-on-line",
            "text": w["text"], "confidence": round(dc, 3),
            "review": dc < 0.75,
            "at": [round(float(span[0]), 1), round(float(span[1]), 1),
                   round(float(span[2]), 1), round(float(span[3]), 1)]})

    return rec


def summarize(records):
    """Average confidence per object type, plus review counts - the numbers
    the review screen and health panel report."""
    by = {}
    for r in records:
        by.setdefault(r["type"], []).append(r["confidence"])
    out = {t: {"count": len(v), "avg_confidence": round(sum(v) / len(v), 3)}
           for t, v in by.items()}
    out["_review_items"] = sum(1 for r in records if r.get("review"))
    out["_total"] = len(records)
    return out


def export(records, dxf_path, scale=1.0, units_feet=False):
    """Write <dxf>.provenance.json next to the DXF."""
    base = os.path.splitext(dxf_path)[0]
    path = base + ".provenance.json"
    with open(path, "w") as f:
        json.dump({"units": "feet" if units_feet else "pixels",
                   "scale": scale,
                   "summary": summarize(records),
                   "objects": records}, f)
    return path
