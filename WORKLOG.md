# WORKLOG — Session play-by-play

The running narrative of who did what, when, and what the benchmark said.
Append newest entries at the top. This is where checkpoints land during long
tasks (every 20–30 min) so an interrupted session can be resumed from the
repo alone. Keep entries short and factual: task, steps, before/after
numbers, state at stop.

---

## 2026-07-23 — Claude Code — Lint: open-polygon + impossible-intersection

**Task:** TASKS.md P2 — extend `verify.py` with two deterministic checks.

**Baseline:** actionable lint 0 / info 24; coverage 96.3%, precision 99.0%,
corners 24/24.

**Did:** added `open_polygon` (two long walls whose free ends nearly meet at
a corner but leave a gap; angle required so door gaps aren't flagged) and
`impossible_intersection` (two long walls crossing with no shared vertex).
Updated verify.py docstring.

**After:** actionable 0 / info 24 unchanged; coverage 96.3%, precision 99.0%,
corners 24/24 unchanged — both checks are high-precision (0 false positives
across all 6 synthetic plans, clean and dirty).

**State at stop:** committed and pushed; tree clean.

---

## 2026-07-23 — Claude Code — Dataset infrastructure (TASKS.md P0, part 1)

**Task:** Build `dataset_builder.py` — the curated benchmark + training
corpus framework and synthetic degradation pipeline (owner's dataset-strategy
request; DECISIONS.md #7).

**Baseline benchmark (before):** coverage 96.3%, precision 99.0%, corners
24/24, actionable lint 0. (dataset_builder is a new standalone tool; the
numeric benchmark does not exercise it.)

**Did:**
- Wrote `dataset_builder.py`: approved-source registry (8 curated sources,
  never-scrape), 11-category on-disk suite, synthetic degradation library (12
  degradations → 7 recipes), ground-truth-preserving synthetic generation
  (reuses `benchmark.generate_plan`/`render`), per-sample metadata,
  content-hash train/val/benchmark split with dedup, CLI.
- Fixes during build: matched `generate_plan`'s `(segs,labels,dims,circles,
  dashes)` signature and its python-`random`-vs-numpy-rng split; added a
  `_jsonable` numpy→python sanitizer for metadata dumps.
- Tested end-to-end in scratchpad (`DRAWING2CAD_DATA` override): init → synth
  8 → degrade 6 → split → stats all pass; ground truth (15 segs / 1 circ / 1
  dash) and split assignment verified; degraded variants correctly inherit
  their parent drawing's split (no cross-split leakage).

**After benchmark:** unchanged — coverage 96.3%, precision 99.0%, corners
24/24, actionable lint 0.

**State at stop:** committed and pushed; tree clean. Framework + synthetic
done. Remaining P0 (wiring real curated fetchers + real regression suite) is
network-gated — blocked in this sandbox, queued in TASKS.md.

---

## 2026-07-23 — Claude Code — Collaboration architecture

**Task:** Stand up the multi-AI coordination layer so Claude Code and
ChatGPT Codex are interchangeable engineers (TASKS.md P-setup, from owner's
request).

**Baseline benchmark (before):** coverage 96.3%, precision 99.0%, OCR 80.0%,
dimensions 10/12, circles/arcs 3/6, dashed 4/6, corners 24/24, scale 5/6
(avg err 0.26%). Lint actionable 0 / info 24 on clean plans.

**Did:**
- Created `AI_RULES.md` (six binding laws), `WORKFLOW.md` (standard session +
  checkpointing + resume protocol), `TASKS.md` (prioritized backlog with
  priority/deps/effort/benchmark-affected), `CHANGELOG.md`, `DECISIONS.md`
  (9 decisions reconstructed from project history), this `WORKLOG.md`, and
  `HANDOFF.md`.
- No engine code touched.

**After benchmark:** unchanged (docs-only change) — coverage 96.3%,
precision 99.0%, corners 24/24.

**State at stop:** committed and pushed; tree clean. Next task is the P0
dataset infrastructure (`dataset_builder.py` + benchmark-suite folders +
synthetic degradation library) — see TASKS.md and DECISIONS.md #7.

---

## Earlier work (pre-worklog, from git history)

Concise reconstruction; full detail in CHANGELOG.md and git log.

- **Verification/lint** — `verify.py` advisory lint; benchmark split into
  actionable vs info; actionable stays 0 on clean plans. Benchmark held.
- **Confidence + provenance** — per-object 0–1 confidence; `provenance.py`
  sidecar; benchmark versioned v1.0; health panel added.
- **Data flywheel + review screen** — `corrections.py`, `review_gui.py`;
  local training pairs from user fixes.
- **CAD I/O** — `cad_io.py`; DWG/DGN via detected converter, DXF fallback.
- **Geometry maturity** — true circles/arcs, dashed linetypes, dimension
  entities, junction healing (corners 24/24).
- **Free reader** — RapidOCR + Tesseract replacing the paid API.
- **Foundations** — benchmark harness, PDF input, single-centerline
  vectorizer, layered DXF, Windows CI build.
