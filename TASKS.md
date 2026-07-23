# TASKS — Prioritized backlog

Prioritized work only. This is not a wishlist; it is the ordered queue an
engineer pulls from. Take the highest-priority item whose dependencies are
met, do exactly one, then update this file.

**Every task carries:** priority, dependencies, estimated effort, and the
benchmark metric it affects (so its success is measurable). A task with no
measurable effect on the benchmark needs a stated reason for existing.

Priorities: **P0** blocking / do next · **P1** high · **P2** normal ·
**P3** someday.

---

## In progress

_None. (When you start a task, move it here and note it in HANDOFF.md.)_

---

## Queue

### P0 — Wire curated fetchers + build the real regression suite
- **Why:** `dataset_builder.py` framework + synthetic pipeline now exist
  (see Done). What remains needs a network and human license confirmation:
  turn the documented approved sources into actual downloaders, pull a first
  batch, and stand up a real-drawing regression suite the benchmark can grade
  alongside the synthetic plans.
- **Scope:** for each entry in `APPROVED_SOURCES`, confirm terms + a stable
  path, add a `fetch` callable (lands in `dataset_builder.fetch`, never an
  ad-hoc scrape), run `fetch` → `split` → then extend `benchmark.py` to score
  the `benchmark` split per category. Also add an `ingest` command for
  manually-downloaded files.
- **Dependencies:** network access + per-source license confirmation
  (recorded in DECISIONS.md). **Blocked in the current sandbox** (no network).
- **Effort:** 1 session per few sources once connected.
- **Benchmark affected:** adds real-drawing categories to the benchmark
  (today: synthetic plans only).
- **Rule:** curated + synthetic only. **Never scrape the open web.**

### P1 — Text tier: synthetic pre-training
- **Why:** Reading is the biggest lever; most remaining misses are text.
- **Scope:** generate large synthetic training sets from CAD renders (varied
  fonts, dimension styles, rotation, skew, degradation) and pre-train / adapt
  the local reader before any human labeling.
- **Dependencies:** P0 synthetic degradation library.
- **Effort:** multi-session; free (CPU generation, modest training).
- **Benchmark affected:** OCR / text accuracy (currently 80%).

### P1 — Real DWG round-trip test
- **Why:** DWG/DGN paths are written to the ODA/LibreDWG CLIs but unverified
  without a converter installed.
- **Scope:** on a machine with ODA File Converter present, confirm
  DXF→DWG→DXF and DWG→DXF fidelity; add a guarded round-trip check.
- **Dependencies:** a converter installed (network/host gated — cannot be
  done in the current sandbox).
- **Effort:** <1 session once a converter is available.
- **Benchmark affected:** new CAD-I/O fidelity check (not yet in benchmark).

### P2 — Verification: open-polygon + impossible-intersection checks
- **Why:** extends the trustworthy lint pass; catches more real defects.
- **Scope:** add open-room-boundary detection and impossible-intersection
  checks to `verify.py`; keep them high-precision (actionable ~0 on clean
  input).
- **Dependencies:** none (`verify.py` shipped).
- **Effort:** <1 session.
- **Benchmark affected:** lint actionable/info columns; must not raise
  actionable count on clean plans.

### P2 — Text-tier fine-tune on correction-flywheel data
- **Why:** the real accuracy jump on drafting lettering.
- **Scope:** after a few hundred labeled correction pairs are collected,
  run a one-time fine-tune and ship the improved local model.
- **Dependencies:** collected corrections (human labeling via review screen)
  + one-time GPU.
- **Effort:** one focused session once data + GPU exist.
- **Benchmark affected:** OCR / text accuracy, especially handwriting.

### P3 — Deeper deterministic geometry
- **Why:** more true-CAD fidelity without any AI.
- **Scope:** splines, hatches, repeated-block recognition, title-block
  extraction, line-weight estimation, automatic layer inference.
- **Dependencies:** none.
- **Effort:** one increment each (pick the single highest-value one when
  this reaches the top).
- **Benchmark affected:** would need new metrics; add them with the feature.

### P3 — Plugin architecture formalization
- **Why:** OCR engines, CAD exporters, validators, drawing-type modules, and
  symbol libraries should each be swappable. The converter backend already
  works this way; generalize the pattern.
- **Dependencies:** none.
- **Effort:** one refactor increment.
- **Benchmark affected:** none directly (structural); must not regress any
  metric.

---

## Done (recent — full history in CHANGELOG.md)

- Dataset infrastructure framework: `dataset_builder.py` — approved-source
  registry (curated, never scraped), 11 category folders, synthetic
  degradation library (12 degradations + 7 real-world recipes),
  ground-truth-preserving synthetic generation (reuses `benchmark.py`),
  per-sample metadata, content-hash train/val/benchmark split with dedup.
- Multi-AI collaboration architecture (AI_RULES, WORKFLOW, TASKS, CHANGELOG,
  DECISIONS, WORKLOG, HANDOFF) — the repo as shared brain.
- Verification/lint pass (advisory, never auto-fix) — reviewer priority #2.
- Confidence scoring + provenance sidecar; versioned benchmark (v1.0).
- STATUS.md living doc + benchmark health panel.
- Data flywheel + review/correction screen.
- CAD-file input and DWG/DGN output (translation tier).
- True circles/arcs, dashed linetypes, dimension entities, junction healing.
- Free offline neural reader (RapidOCR), replacing the paid API.
