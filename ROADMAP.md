# Drawing2CAD — The Blueprint

**Goal:** PDFs, scans, photos, and CAD project files go in; proper, accurate
DWG-class files come out. Everything runs locally, no per-use costs.

## Guiding principle (adopted)

**Faithful reconstruction over intelligent reconstruction.
Preserve what exists. Never hallucinate. When confidence is low,
flag it rather than guess.**

The goal is not to repair or reinterpret drawings — it is to convert what
already exists into editable CAD while preserving every property that can
reasonably be recovered: vertical text stays vertical, rotated text keeps
its rotation, circles become circles, arcs become arcs, dashed lines stay
dashed, dimensions remain dimensions, symbols stay where they belong.
Better ten uncertain labels flagged for review than one confidently wrong
label in a legal survey. No silent "improvements" of the source.

## Development process (adopted)

One feature at a time: implement → benchmark → verify no regression →
commit → next. Measured speed targets sit alongside quality targets:
vector PDF under 10 s, large scan under 30 s, phone photo under 60 s.

This document is the honest engineering plan: what exists, what it takes to
get to the goal, and where the hard limits are. Written to be discussed —
with the owner, with other AI assistants, with anyone.

---

## 1. Where the program stands today

*Updated as capabilities land; run `python benchmark.py` for live numbers.*

| Capability | Status | Measured quality |
|---|---|---|
| Vector PDF input (CAD e-filings) | ✅ built | Exact — lines and text lifted, no guessing |
| Scanned PDF input | ✅ built | Native-resolution extraction, photo pipeline |
| Photo/scan input (JPG/PNG/TIFF) | ✅ built | 96.7% line coverage, 98.9% precision (benchmark) |
| Text reading | ✅ built (Tesseract + RapidOCR, both local/free) | 83% on benchmark; dimension tick reconstruction; strong on machine text, weak on hand lettering (fine-tune pending, see FINETUNE.md) |
| Auto-scale to real feet | ✅ built | Locks on 5/6 benchmark plans at ≤0.5% error; declines honestly when ambiguous |
| Layered DXF output | ✅ built | LINES / CURVES / TEXT / hidden TEXT_REVIEW / DIMENSIONS / HIDDEN |
| Scored benchmark harness | ✅ built | Every change graded; versioned; plus a `--hard` robustness stress tier |
| DWG / DGN output | ✅ built | Via the free ODA / LibreDWG converter (detected); clean DXF fall-back |
| CAD project files as *input* (DWG/DGN/DXF) | ✅ built | Translated via the same detected converter |
| Arcs/circles as true entities | ✅ built | Least-squares ARC/CIRCLE fits (5/6 benchmark, incl. wall-connected columns) |
| Dashed/dotted linetypes | ✅ built | Dash-rhythm recognition → single DASHED line on a HIDDEN layer (4/6 benchmark) |
| Editable DIMENSION entities | ✅ built | Label-on-line pairs become aligned DIMENSION entities |
| Line-weight preservation | ✅ built | Measured stroke width → thin/normal/thick DXF lineweights |
| Verification / drawing lint | ✅ built | Advisory, never auto-fixing; high-precision (0 actionable on clean) |
| Confidence + provenance | ✅ built | Every object carries 0–1 confidence + origin record |
| Semantic understanding (wall vs dimension vs symbol) | ◑ partial | Dimensions & dashed classified; deeper semantics deferred (deterministic-first) |

---

## 2. The physics: what "perfect" can and cannot mean

This is the most important section. Hold every promise — from me, from
ChatGPT, from any vendor — against it.

**Input quality sets a hard ceiling that no software can exceed.**

| Input | Best achievable outcome |
|---|---|
| CAD file (DWG/DXF/DGN) | **Perfect.** The data is already vectors; conversion is translation, not recovery. |
| Vector PDF | **Perfect geometry and text.** Layer names and entity types (dimension objects, blocks) are partially lost by the PDF format itself. |
| Clean 300+ DPI scan | **Near-perfect lines** (99%+), high text accuracy, correct scale. Small symbols and line-weight nuance degrade. |
| Phone photo | **Good.** Lens distortion, paper curl, lighting cost a few percent of geometry accuracy that correction can shrink but not erase. |
| Degraded photocopy / hand lettering | **Never perfect. Not by anyone.** Information destroyed at copy time no longer exists. Software can only guess — and on legal documents, confident guessing is worse than honest flagging. |

A converted survey or plan is also **not a certified document**. Geometry
recovered by any automatic process must be checked by a person before it's
used for filings, boundaries, or construction. That's what the review layer
is for, and it must stay.

---

## 3. The plan, in phases

### Phase A — CAD-file input and DWG output (translation tier)
*Closes: "cad saved project files" in, "dwg" out. Effort: days.*

- **DWG/DGN input:** accept them via the free ODA File Converter
  (Open Design Alliance) — a local, no-cost tool that converts DWG↔DXF on
  your machine. Like Tesseract: a one-time install the program detects.
  DXF input is trivial to add natively.
- **DWG output:** same tool in reverse — the program writes DXF (already
  perfect), then hands it to the local converter for a true .dwg.
- Point of contention: DWG is Autodesk's proprietary, closed format. No
  honest free library writes it perfectly from scratch; the ODA converter
  is the industry's standard answer, and it cannot legally be bundled
  inside our exe — the user installs it once, free.
- The converter backend stays **modular**: ODA today, LibreDWG or a
  commercial SDK swappable later without touching the rest of the app.

### Phase B — CAD-entity intelligence (raster tier grows up)
*Closes: arcs, linetypes, hatches, dimension entities. Effort: weeks.*

- **Arc/circle fitting:** detect when a traced polyline is actually an arc
  or circle and emit true ARC/CIRCLE entities (least-squares circle fits on
  curve chains — classical math, very doable).
- **Linetype recognition:** collinear dash chains become single lines with
  DASHED linetype instead of confetti; center/hidden line patterns detected.
- **Hatch detection:** regularly spaced parallel stroke fields become HATCH
  regions instead of hundreds of little lines.
- **Real dimension entities:** when a dimension string (extension lines +
  ticks + number) is recognized, emit a proper DIMENSION entity — the thing
  a drafter can grab and edit — not loose lines plus text.
- **Topology cleanup:** endpoint snapping, corner closure, T-junction
  healing, so walls meet exactly and rooms close.
- **Expanded scope (this phase gets priority over the AI tiers):** spline
  detection, repeated-block recognition, title-block extraction, room
  boundary detection, line-weight estimation, rotated-text preservation,
  automatic layer inference. A surprising amount of "intelligence" is
  deterministic geometry — faster, debuggable, predictable.

### Phase C — Better text, locally (the ML tier — this is where
"feeding it drawings" becomes real)
*Closes: hand lettering as far as physics allows. Effort: weeks + data.*

- **Swap-in stronger local models:** TrOCR-handwritten and PaddleOCR server
  models are free, open, and stronger than the current readers on hard
  text. Cost: bigger download, slower on CPU.
- **Stage 1 — synthetic pre-training:** generate large datasets from CAD
  renders (varied fonts, dimension styles, rotation, skew, blur, JPEG
  artifacts, photocopy degradation, stains, faded ink). The benchmark
  generator already produces exactly this kind of data; scaled up, it
  gives the recognizer a strong start before any human labels a thing.
- **Stage 2 — fine-tuning on drafting lettering, from user corrections:**
  1. A correction screen in the app: it shows each uncertain label next to
     the image crop; the user fixes the text with a keystroke.
  2. Every correction is saved as a training pair (image → truth).
  3. After a few hundred corrections, fine-tune the recognizer (one-time
     GPU job — rentable for a few dollars, or hours on a gaming PC) and
     ship the improved model inside the app.
  This loop is exactly how the tool "gets smarter from use" — and the
  labeled data has to come from a human. There is no shortcut.

### Phase D — Local semantic understanding (the "it knows what it's
looking at" tier)
*Closes: wall vs dimension vs symbol; contextual text correction. Effort:
weeks; **hardware required**.*

- Open-weight vision-language models (e.g. Qwen-VL class) can run fully
  locally and genuinely understand drawings — read hand lettering in
  context, classify regions ("this is a title block", "this is a door
  swing"), sanity-check dimensions.
- **The point of contention:** local + free-per-use + frontier-smart is a
  pick-two triangle. Datacenter AI costs pennies per drawing; local AI of
  comparable understanding costs a **one-time GPU purchase** (a used RTX
  3060 12GB, roughly $200–300, runs the useful sizes). On a CPU-only
  machine, this tier is minutes-per-drawing slow or unavailable.
- The program should treat this tier like Tesseract: optional, detected,
  gracefully absent.
- **Deterministic-first hierarchy:** before asking any AI model whether
  something is a wall, exhaust graph connectivity, geometric constraints,
  symbol libraries, topology analysis, and CAD heuristics. AI is the
  last resort for what deterministic methods cannot confidently classify,
  never the first tool reached for.

### Phase E — Verification as a first-class feature
*Closes: "perfect" where it can't be automatic — by making human checking fast.*

- Side-by-side overlay: original image under the recovered vectors,
  differences highlighted.
- The dimension cross-check generalized: every recognized dimension
  verified against its measured geometry; disagreements flagged with both
  numbers shown.
- One-key review flow for flagged text (feeds Phase C's data loop).
- **Drawing lint:** flag disconnected walls, duplicate geometry,
  impossible intersections, missing extension lines, open polygons,
  inconsistent scales, impossible room boundaries, and geometry that
  disagrees with its annotation. Professionals trust software that
  points out problems instead of hiding them.
- Expanded benchmark: more plan styles, curved geometry, real annotated
  scans as they accumulate.

---

## 4. Concerns, hesitations, points of contention — stated plainly

1. **"Perfect" from raster is a physics violation.** Vector PDFs and CAD
   files: yes, perfect. Photos and degraded copies: asymptotically good,
   never perfect. Any plan (or any AI) promising otherwise is selling
   something. Judge progress by the benchmark numbers, not adjectives.
2. **DWG is a legal minefield.** Writing it natively means reverse-
   engineered libraries (imperfect) or licensed SDKs (money). The local
   free answer is the ODA converter as an install-once companion. DXF
   remains a full-fidelity equivalent that both AutoCAD and MicroStation
   treat as native.
3. **Local + powerful needs hardware.** Phases A–B run on any PC. Phase C
   training and Phase D understanding want a GPU. One-time cost versus the
   rejected per-use cost — a decision only the owner can make.
4. **The ML tier runs on labeled data, and labeling is human work.** The
   correction-screen flywheel makes it nearly free per drawing, but
   somebody still does it. A few hundred corrections before the first
   fine-tune pays off.
5. **Liability.** Auto-converted surveys/plans must not silently become
   the basis for legal or construction decisions. The tool's honesty
   features (review layer, declining ambiguous scales) are load-bearing;
   any "improvement" that removes honesty to look better is a regression.
6. **Scope discipline.** Architectural plans and surveys first. Mechanical,
   electrical, and piping drawings each have their own symbol languages —
   different vocabularies, different projects.
7. **One maintainer.** The benchmark is the guardrail that makes iteration
   safe. Any proposed change — wherever the idea comes from — gets graded
   by it before it ships.

## 5. Definition of done (measurable)

| Tier | Target |
|---|---|
| CAD file / vector PDF in → DWG/DXF out | 100% geometry and text fidelity |
| Clean scan | ≥99% line coverage, ≥98% precision, ≥95% machine text, scale ≤0.5% |
| Photo | ≥95% coverage, ≥95% precision, ≥85% machine text, scale ≤1.5% or honest decline |
| Degraded/hand-lettered | ≥90% linework; text best-effort + 100% of uncertainties flagged for review |

All measured by `benchmark.py`, which ships in this repo and grades every
change.
