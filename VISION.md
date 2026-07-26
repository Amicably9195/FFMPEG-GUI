# Drawing2CAD — Vision & Architecture (north star)

> **What this is.** The target the project is built toward. It describes the
> full system — including tiers not yet built. For **what actually works
> today**, see `STATUS.md` (living state) and `ROADMAP.md` §1 (the phased
> status table); for the rules every change obeys, see `AI_RULES.md`. This
> document is aspirational by design; it must never be read as a claim that
> every capability below already exists. Build status is called out at the end.

## Objective

An offline, benchmark-driven CAD reconstruction system that converts scanned
architectural, engineering, and survey drawings into clean, editable CAD files
(DWG/DXF). Personal and professional use, completely local — no cloud
inference, no token-based APIs, no recurring cost. The primary objective is
**faithful reconstruction, not artificial enhancement**: preserve the source
as accurately as possible while clearly identifying uncertainty for human
review.

## Core design principles

- Offline-first architecture
- Deterministic-first, AI-assisted design
- No dependency on OpenAI, Anthropic, or cloud inference
- Zero recurring API or token costs
- Privacy-preserving (all processing stays local)
- Modular, replaceable components
- Benchmark-driven development
- Human-in-the-loop verification
- Professional-quality CAD output
- Trustworthiness over automation

## Engineering philosophy

Treat the application as a CAD reconstruction **pipeline inspired by compiler
design**, not a simple raster-to-vector converter. The software should:

1. Recover all information determinable through deterministic algorithms.
2. Use AI only where semantic interpretation gives a *measurable* improvement.
3. Preserve geometry, dimensions, orientation, symbols, and annotations
   whenever they can be confidently recovered.
4. Never invent geometry or silently alter the source drawing.
5. Flag uncertainty for human review instead of guessing.
6. Produce structured, editable CAD entities suitable for professional work.

The objective is not to "redraw" the document but to reconstruct it faithfully
while preserving its engineering intent.

## Supported input types

CAD files (DWG, DXF, DGN) · Vector PDF · Scanned PDF · Historical blueprints ·
Building-department drawings · Survey plats · Site plans · Floor plans ·
Architectural drawings · Structural drawings · PNG · JPEG · TIFF ·
Screenshots · Camera photographs.

## Desired output formats

DWG · DXF · SVG (optional) · Layered CAD drawings · Fully editable geometry ·
Editable dimensions · Preserved annotations · Preserved text orientation ·
Title-block metadata · Confidence metadata (internal sidecar).

## High-level processing pipeline

Each stage is independent and replaceable:

1. Document import
2. Image normalization — perspective correction, deskewing, noise reduction,
   contrast enhancement
3. Scale estimation
4. Text detection & OCR
5. Primitive geometry extraction
6. Geometry cleanup
7. AI-assisted semantic interpretation
8. Constraint solving
9. Layer classification
10. CAD reconstruction
11. Validation
12. Human review
13. CAD export

## Deterministic engine responsibilities

Deterministic algorithms do the work before AI is introduced — these are
predictable, measurable, benchmarkable:

Image preprocessing · edge detection · skeletonization · vectorization · line
merging · arc fitting · circle fitting · endpoint snapping · orthogonality
enforcement · coordinate transforms · CAD entity generation · layer creation ·
line-weight estimation · DWG/DXF export · geometric validation.

## AI-assisted responsibilities

AI assists **only where semantic understanding adds value beyond deterministic
algorithms**, and never replaces geometry processing:

Wall / door / window / stair recognition · structural & survey symbol
recognition · dimension interpretation · room-boundary inference · title-block
interpretation · layer inference · context-aware OCR correction · confidence
estimation.

## Modular architecture

Independent, replaceable modules: Image Processing Engine · OCR Engine ·
Geometry Engine · Vectorization Engine · Semantic Recognition Engine ·
Constraint Solver · CAD Reconstruction Engine · Validation Engine · DWG/DXF
Export Engine · User Review Interface. Each is replaceable without affecting
the rest of the pipeline.

## Human review workflow

The user reviews only the uncertain portions. Every reconstructed entity
carries a confidence score, surfaced as a traffic-light tier:

- **Green** — high confidence, minimal review.
- **Yellow** — moderate confidence, recommended review.
- **Red** — low confidence, manual verification required.

The objective is to *reduce* review time, not eliminate human oversight.

## Benchmark & dataset

A curated benchmark spanning vector CAD, vector PDFs, clean scans, historical
blueprints, survey plats, site plans, architectural drawings, camera photos,
poor photocopies, and hand-annotated drawings. Each item carries: original
source, expected CAD output, accuracy metrics, processing time, and regression
history. **Every algorithmic change is benchmarked before it is accepted.**

## Trustworthiness

The software shall never invent geometry; never silently modify dimensions;
preserve orientation, scale, and topology; preserve all recoverable
information; report confidence for every reconstructed entity; preserve
uncertain objects for review rather than deleting or altering them; and prefer
explicit uncertainty over confident errors. Professionals trust it because it
faithfully reproduces the source and clearly communicates what needs
attention.

## Long-term vision

Not merely raster-to-vector conversion, but a **semantic CAD reconstruction
platform** that understands engineering drawings and reconstructs editable,
standards-compliant CAD while minimizing manual drafting. Defining
characteristics: local execution · modular architecture · benchmark-driven
development · deterministic-first engineering · AI-assisted semantic
understanding · faithful reconstruction · professional trustworthiness. The
goal is a system professionals rely on because it preserves what it sees,
measures its own performance, communicates uncertainty honestly, and improves
through benchmarked, incremental development rather than opaque AI behavior.

---

## Build status today (honesty check — see STATUS.md / ROADMAP.md for detail)

**Built and benchmarked (deterministic-first):** offline pipeline; DXF always
+ DWG/DGN via a detected converter; CAD/vector-PDF/scan/photo input; centerline
vectorization; true LINE/ARC/CIRCLE (incl. wall-connected columns);
dashed→HIDDEN layer; editable DIMENSION entities; junction healing;
line-weight estimation; auto-scale to feet with honest decline; free offline
OCR (Tesseract+RapidOCR) with dimension tick reconstruction; layered output;
verification lint (advisory, high-precision); confidence + provenance;
correction flywheel; green/yellow/red review tiers (sidecar, DXF layers, SVG);
an optional SVG preview export; a versioned benchmark + `--hard` robustness tier.

**Planned / deferred (aspirational above):** the AI-assisted semantic tier
(wall/door/window/stair/symbol recognition, room-boundary inference); the
constraint solver; title-block metadata extraction;
perspective-correction hardening; the local reader fine-tune (see
`FINETUNE.md`, needs a one-time GPU). These are targets, not current
capabilities — deterministic-first means they arrive only where they beat
deterministic methods on the benchmark.
