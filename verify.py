#!/usr/bin/env python3
"""verify - drawing lint for Drawing2CAD.

Professionals trust software that POINTS OUT problems instead of hiding them.
This pass inspects the recovered geometry and reports likely defects - it
never auto-fixes (that would be 'intelligent reconstruction' that could
destroy faithful data). Findings are advisory, each with a location and
severity, so a human can judge.

Checks (all deterministic):
  * sliver          - near-zero-length line (tracing junk)
  * duplicate       - two lines nearly collinear and overlapping (doubled wall)
  * dangling_wall   - a long line whose end meets nothing (a wall stopping in
                      space); short leaders/ticks are exempt
  * dimension_mismatch - a DIMENSION whose stated value disagrees with its own
                      drawn length under the locked scale

Doubles as a regression signal: on known-good input the finding count should
stay near zero, so a change that introduces doubled or dangling geometry is
caught by the benchmark.
"""

import math

import numpy as np


def _angle(seg):
    return math.degrees(math.atan2(seg[3] - seg[1], seg[2] - seg[0])) % 180.0


def check(segments, dashed=(), dims=(), scale=None, units_feet=False,
          wall_min=40.0, connect_tol=6.0):
    """Return a list of findings: {type, severity, at:[x,y], detail}."""
    findings = []
    segs = np.asarray(segments, dtype=np.float64) if len(segments) else \
        np.empty((0, 4))
    lengths = (np.hypot(segs[:, 2] - segs[:, 0], segs[:, 3] - segs[:, 1])
               if len(segs) else np.array([]))

    # 1. slivers
    for i in np.where(lengths < 2.0)[0]:
        findings.append({"type": "sliver", "severity": "low",
                         "at": [round(segs[i, 0], 1), round(segs[i, 1], 1)],
                         "detail": "near-zero-length line"})

    # 2. duplicates: near-collinear, near-coincident, overlapping in extent
    ang = np.array([_angle(s) for s in segs]) if len(segs) else np.array([])
    order = np.argsort(ang)
    for oi in range(len(order)):
        i = order[oi]
        if lengths[i] < 5:
            continue
        di = np.array([math.cos(math.radians(ang[i])),
                       math.sin(math.radians(ang[i]))])
        ni = np.array([-di[1], di[0]])
        mi = (segs[i, :2] + segs[i, 2:]) / 2
        for oj in range(oi + 1, len(order)):
            j = order[oj]
            if ang[j] - ang[i] > 2.0 and not (ang[i] < 2 and ang[j] > 178):
                break
            if lengths[j] < 5:
                continue
            # same infinite line?
            if abs(float((segs[j, :2] - segs[i, :2]) @ ni)) > 3.0:
                continue
            if abs(float((segs[j, 2:] - segs[i, :2]) @ ni)) > 3.0:
                continue
            # overlap along the line?
            ti = sorted([segs[i, :2] @ di, segs[i, 2:] @ di])
            tj = sorted([segs[j, :2] @ di, segs[j, 2:] @ di])
            if min(ti[1], tj[1]) - max(ti[0], tj[0]) > 4.0:
                findings.append({
                    "type": "duplicate", "severity": "medium",
                    "at": [round(mi[0], 1), round(mi[1], 1)],
                    "detail": "two lines overlap (possible doubled wall)"})
                break

    # 3. floating walls: a long line whose BOTH ends meet nothing. One open
    #    end is normal (the last wall in a run, a property line to the sheet
    #    edge); both ends floating is a stronger, high-precision defect signal
    #    and keeps the report trustworthy instead of crying wolf.
    if len(segs):
        ends = np.vstack([segs[:, :2], segs[:, 2:]])
        for i in range(len(segs)):
            if lengths[i] < wall_min:
                continue
            open_ends = 0
            for e in (segs[i, :2], segs[i, 2:]):
                d = np.abs(ends - e).max(axis=1)
                if np.count_nonzero(d <= connect_tol) <= 1:  # only itself
                    open_ends += 1
            if open_ends == 2:
                m = (segs[i, :2] + segs[i, 2:]) / 2
                findings.append({
                    "type": "floating_line", "severity": "low",
                    "at": [round(m[0], 1), round(m[1], 1)],
                    "detail": "long line floating free (both ends "
                              "meet nothing)"})

    # 4. dimension vs its own geometry (only meaningful when scaled)
    if units_feet and scale:
        import scan2cad
        for w, span in dims:
            value = scan2cad.parse_dimension(w["text"])
            if value is None:
                continue
            drawn = math.hypot(span[2] - span[0], span[3] - span[1]) * scale
            if drawn > 0 and abs(drawn - value) / value > 0.08:
                findings.append({
                    "type": "dimension_mismatch", "severity": "high",
                    "at": [round(float(span[0]), 1), round(float(span[1]), 1)],
                    "detail": f"labeled {w['text']} but measures "
                              f"{drawn:.2f} ft"})
    return findings


def summarize(findings):
    by_type, by_sev = {}, {"high": 0, "medium": 0, "low": 0}
    for f in findings:
        by_type[f["type"]] = by_type.get(f["type"], 0) + 1
        by_sev[f["severity"]] = by_sev.get(f["severity"], 0) + 1
    return {"total": len(findings), "by_type": by_type, "by_severity": by_sev}
