#!/usr/bin/env python3
"""svg_export - a browser-viewable preview of a reconstruction.

The DXF/DWG is the deliverable; this is a quick visual check that needs no CAD
software - open the .svg in any browser. It draws the SAME recovered entities
(lines, dashed lines, circles, arcs, curves, text) the DXF gets, colored by
their role and, for text, by the green/yellow/red review tier - so a glance
shows what was recovered and what needs a human look.

Modular by design (VISION.md): it consumes the geometry the pipeline already
produced and touches nothing else.
"""

import math
from xml.sax.saxutils import escape

import numpy as np

try:
    import provenance
    _tier = provenance.tier
except Exception:                                   # pragma: no cover
    def _tier(conf, review=False):
        return "red" if review or conf < 0.4 else \
               "yellow" if conf < 0.75 else "green"

# role -> stroke colour (matches the DXF layer intent)
_LINE = "#111111"       # solid linework
_HIDDEN = "#cc2222"     # dashed / hidden
_CURVE = "#1b6fb3"      # curves, circles, arcs
_DIM = "#7a3fb3"        # dimensions (line + value)
_TIER_FILL = {"green": "#1f9d3a", "yellow": "#c79a00", "red": "#cc2222"}


def _arc_polyline(cx, cy, r, p1, p2, pm):
    """Sample an arc (the sweep passing through pm) as points, in pixel space."""
    def ang(p):
        return math.atan2(p[1] - cy, p[0] - cx)
    a1, a2, am = ang(p1), ang(p2), ang(pm)
    sweep = (a2 - a1) % (2 * math.pi)
    if (am - a1) % (2 * math.pi) > sweep:           # go the other way
        a1, a2 = a2, a1
        sweep = 2 * math.pi - sweep
    n = max(6, int(sweep / 0.15))
    return [(cx + r * math.cos(a1 + sweep * t / n),
             cy + r * math.sin(a1 + sweep * t / n)) for t in range(n + 1)]


def write_svg(path, img_w, img_h, segments=(), curves=(), words=(),
              rounds=(), dashed=(), dims=(), min_len_px=6.0):
    """Write an SVG preview in source-image pixel coordinates (y-down)."""
    out = [f'<svg xmlns="http://www.w3.org/2000/svg" width="{img_w}" '
           f'height="{img_h}" viewBox="0 0 {img_w} {img_h}">',
           f'<rect width="{img_w}" height="{img_h}" fill="white"/>']

    seg = np.asarray(segments, dtype=float) if len(segments) else \
        np.empty((0, 4))
    for x1, y1, x2, y2 in seg:
        if math.hypot(x2 - x1, y2 - y1) < min_len_px:
            continue
        out.append(f'<line x1="{x1:.1f}" y1="{y1:.1f}" x2="{x2:.1f}" '
                   f'y2="{y2:.1f}" stroke="{_LINE}" stroke-width="1.5"/>')

    for x1, y1, x2, y2 in (dashed if len(dashed) else ()):
        out.append(f'<line x1="{x1:.1f}" y1="{y1:.1f}" x2="{x2:.1f}" '
                   f'y2="{y2:.1f}" stroke="{_HIDDEN}" stroke-width="1.5" '
                   f'stroke-dasharray="8 5"/>')

    for points, closed in curves:
        pts = " ".join(f"{float(px):.1f},{float(py):.1f}" for px, py in points)
        tag = "polygon" if closed else "polyline"
        out.append(f'<{tag} points="{pts}" fill="none" stroke="{_CURVE}" '
                   f'stroke-width="1.5"/>')

    for ent in rounds:
        if ent[0] == "circle":
            out.append(f'<circle cx="{ent[1]:.1f}" cy="{ent[2]:.1f}" '
                       f'r="{ent[3]:.1f}" fill="none" stroke="{_CURVE}" '
                       f'stroke-width="1.5"/>')
        else:                                       # arc -> sampled polyline
            pts = _arc_polyline(ent[1], ent[2], ent[3], ent[4], ent[5], ent[6])
            s = " ".join(f"{x:.1f},{y:.1f}" for x, y in pts)
            out.append(f'<polyline points="{s}" fill="none" stroke="{_CURVE}" '
                       f'stroke-width="1.5"/>')

    for wd, span in dims:
        x1, y1, x2, y2 = (float(span[0]), float(span[1]),
                          float(span[2]), float(span[3]))
        out.append(f'<line x1="{x1:.1f}" y1="{y1:.1f}" x2="{x2:.1f}" '
                   f'y2="{y2:.1f}" stroke="{_DIM}" stroke-width="1.2"/>')
        mx, my = (x1 + x2) / 2, (y1 + y2) / 2
        out.append(f'<text x="{mx:.1f}" y="{my - 3:.1f}" font-size="11" '
                   f'font-family="Arial, sans-serif" fill="{_DIM}" '
                   f'text-anchor="middle">'
                   f'{escape(str(wd.get("text", "")))}</text>')

    for wd in words:
        px, py = wd.get("insert", (wd.get("x", 0), wd.get("y", 0)))
        h = max(6.0, 0.9 * float(wd.get("cap", 8)))
        fill = _TIER_FILL[_tier(float(wd.get("conf", 0)) / 100.0,
                                bool(wd.get("review")))]
        rot = wd.get("rotation", 0)
        transform = (f' transform="rotate({-rot} {px:.1f} {py:.1f})"'
                     if rot else "")
        out.append(f'<text x="{px:.1f}" y="{py:.1f}" font-size="{h:.1f}" '
                   f'font-family="Arial, sans-serif" fill="{fill}"'
                   f'{transform}>{escape(str(wd.get("text", "")))}</text>')

    out.append("</svg>")
    with open(path, "w", encoding="utf-8") as f:
        f.write("\n".join(out))
    return path
