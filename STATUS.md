# Drawing2CAD — State of the Project

*Kept current as the project evolves. For the phased engineering plan see
ROADMAP.md; for measured numbers run `python benchmark.py`. For how sessions
are run by interchangeable AI engineers, see WORKFLOW.md and AI_RULES.md.*

> **New here (human or AI)?** Read `AI_RULES.md` (the constitution) and
> `HANDOFF.md` (what's in flight right now) first, then follow `WORKFLOW.md`.
> The repository is the shared brain — every fact lives in these docs.

---

## The vision

**Faithful reconstruction over intelligent reconstruction.** Reproduce the
source drawing as accurately as possible — preserving geometry, dimensions,
orientation, symbols, and text. Never invent information. When confidence is
low, preserve what is known and flag the uncertainty for review instead of
guessing.

Everything runs **locally, with no per-use cost.**

**Trustworthiness is the point.** If the software faithfully reproduces what
it sees — orientation, dimensions, symbols, geometry — without inventing or
"fixing" things on its own, it earns trust even when it asks for human
review. That trust is worth more than a claim of perfect accuracy.

---

## What works today

**Inputs:** phone photos, scans, PDFs (vector *and* scanned), and CAD project
files — DXF natively, DWG/DGN via the free ODA File Converter.

**Outputs:** DXF always; DWG/DGN when the converter is installed, with a
clean fall-back to DXF (which AutoCAD and MicroStation open natively) when
it isn't.

**Geometry:** clean centerline tracing, true LINE / ARC / CIRCLE entities,
dashed-linetype preservation, editable DIMENSION entities, precise corner
closure, endpoint snapping, and topology cleanup that preserves the original
drawing rather than reinterpreting it.

**Text & scale:** free offline neural text reading (Tesseract + RapidOCR);
auto-scale to real feet when dimensions agree, an honest "can't tell"
otherwise; uncertain text isolated on a hidden red review layer.

**Correction flywheel:** a review screen shows each uncertain label beside a
magnified crop; a keystroke confirms or fixes it. Every fix updates the
drawing *and* saves a labeled example locally for future model training
(the software does not retrain itself on each edit — it collects the data a
one-time fine-tune will use). Nothing leaves the machine.

**Verification (lint):** an advisory pass flags likely defects — doubled
walls, dimension-vs-geometry disagreements, floating lines — with location
and severity, never auto-fixing. Trustworthy by design: it reports the
actionable few, not hundreds of false alarms.

**Guardrail:** a scored benchmark grades every change so quality can't
silently regress.

### Current benchmark (synthetic plans, `python benchmark.py`)

| Metric | Value |
|---|---|
| Line coverage | 96.3% |
| Line precision | 99.0% |
| OCR / text | 80.0% |
| Dimension accuracy | 10/12 (83%) |
| Circles / arcs | 3/6 (50%, dirty-scan declines) |
| Dashed linetypes | 4/6 (67%, dirty-scan declines) |
| Corner closure | 24/24 (100%) |
| Scale locked | 5/6 (83%), avg err 0.26% |
| Processing time | ~2s avg on synthetic plans |

One benchmark reports the whole health of the program; every commit is
checked against it.

---

## Performance goals

Speed matters almost as much as accuracy once the tool is usable. Targets on
a typical machine:

| Input | Target |
|---|---|
| Vector PDF | under 10 s |
| Large scan | under 30 s |
| Phone photo | under 60 s |

---

## What's next (priority order)

1. **Text tier — the biggest lever.** Reading is the ceiling on everything
   now; most remaining misses trace back to it. A measured baseline exists:
   on synthetic drafting text (`python synth_text.py measure`) the neural
   reader scores **88.3% exact / 97.2% char**, and the dominant miss is
   *dropped feet/inch tick marks* (`7'-0"` → `7-0`) — a specific, fixable
   weakness. Path: (a) dimension-aware tick reconstruction in post-processing
   (free, next), then (b) synthetic pre-training + fine-tune the local reader
   on the correction-flywheel data (**one-time GPU**). `synth_text.py`
   generates unlimited labeled pairs in the flywheel format for both.
2. **Verification / lint** *(first pass shipped).* `verify.py` flags doubled
   walls (duplicate geometry), dimensions that disagree with their own drawn
   length, and long lines floating free — advisory only, never auto-fixed,
   each with a location and severity in a `.lint.json` sidecar. The benchmark
   tracks *actionable* findings (should stay ~0 on clean input), so it now
   also guards against a change introducing junk geometry. Still to add:
   open-polygon and impossible-intersection checks.
3. **Real DWG round-trip test.** The DWG/DGN paths are written to the ODA /
   LibreDWG CLIs but unverified without a converter installed — confirm on a
   machine that has one.
4. **Deeper geometry (deterministic, no AI).** Splines, hatches, repeated-
   block recognition, title-block extraction, line-weight estimation,
   automatic layer inference.

---

## Core engineering principles

These are structural — they define *how* trust is built, not just claimed.

- **Success is defined by user trust, not a headline accuracy number.** The
  goal is not "99.5% OCR"; it is *professionals trust the output because the
  software faithfully preserves what it sees, clearly communicates
  uncertainty, and never invents information.* Accuracy is one measurement of
  that trust, not the whole of it.
- **Confidence everywhere.** Every recovered object carries a 0–1 confidence
  (text, circle, arc, dimension, dashed line, scale, …), so the review screen
  surfaces the least-certain items first and human review is fast.
- **Never lose information.** Even an object the software cannot classify is
  preserved — unknown symbol → kept as geometry, unknown text → crop + geometry
  kept, unknown linetype → original segments kept. The system degrades
  gracefully; it never deletes or silently simplifies.
- **Provenance.** Every object remembers where it came from: source image
  coordinates, confidence, reconstruction method, review status. This metadata
  rides in a sidecar (not baked into the DXF) and is invaluable for debugging
  and for judging whether a change actually helped.
- **Detection is separate from reconstruction.** Detection answers *what
  exists?*; reconstruction answers *how should it be represented in CAD?*
  Keeping them independent keeps future improvements clean.

## Architecture: a staged pipeline

The program is organized as a pipeline, not a bag of features, so any stage
can be swapped for a better implementation without touching the rest:

```
Input → Preprocessing → Geometry Detection → Text Detection →
Classification → CAD Reconstruction → Verification → Review → Export
```

A **plugin-friendly** direction is planned early: OCR engines, CAD exporters,
validators, drawing-type modules, and symbol libraries should each be
swappable. The converter backend (ODA / LibreDWG) already works this way.

## Development philosophy

Every feature is developed incrementally:

1. implement one capability
2. benchmark it (the benchmark is **versioned** — currently v1.0 — so a gain
   is always attributable to a better algorithm, not a changed benchmark)
3. verify no regressions
4. commit
5. move to the next capability

Small, measurable improvements are preferred over large rewrites. A permanent
**visual regression library** (best case, average scan, poor scan, folded,
faded survey, skewed photo, rotated scan, blueprint copy, dense sheet) is
planned alongside the numeric benchmark so every release is checked against
the same real drawings.

---

## The honest limit

Machine-drawn inputs and CAD files convert to near-perfect results. On
degraded photocopies and hand-lettering, **geometry generally recovers
well** (lines, circles, arcs, dimensions, topology), but the *handwriting*
still needs a human pass — which is exactly what the review screen is for —
until the local reader is trained on drafting lettering. No free offline
tool does better than that today.

**Fastest path to results you can trust:** feed clean scans or vector PDFs,
use DWG output, and run every drawing through the review screen — it fixes
the drawing now and teaches the reader for later.

---

## Not yet supported

These drawing types are out of scope for now; they have their own symbol
languages and need dedicated work:

- Mechanical drawings
- Electrical schematics
- Piping / P&ID diagrams
- Freehand sketches
- Color-coded layer recovery
