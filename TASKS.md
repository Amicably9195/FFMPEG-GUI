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

### P1 — Text tier: recover bare-feet marks from drawing context (unblocked)
- **Why:** after tick reconstruction, the only remaining dimension miss is
  bare feet (`23'` → `23`) — a foot mark that can't be added context-free
  without corrupting callout numbers. But the pipeline KNOWS which labels are
  dimensions (they pair with dimension geometry), so it can safely restore
  the mark there.
- **Scope:** in `scan2cad`, for words matched to dimension lines, apply a
  dimension-context normalizer (bare integer → `N'`); keep it off
  non-dimension text. Verify plan-benchmark dimension accuracy rises without
  OCR/text regressing.
- **Dependencies:** none (dimension pairing already exists).
- **Effort:** <1 session.
- **Benchmark affected:** dimension accuracy (10/12) and OCR/text (83.3%).

### P2 — Text tier: run the synthetic pre-training fine-tune
- **Why:** the corpus generator exists; scaling it + a one-time fine-tune is
  the deeper win on hand/degraded lettering.
- **Scope:** `synth_text.py gen -n <large>` → fine-tune the local recognizer
  → ship the improved model; re-measure.
- **Dependencies:** a GPU (one-time). **Blocked in this sandbox.**
- **Effort:** one focused session on a GPU host.
- **Benchmark affected:** OCR / text accuracy, especially degraded lettering.

### P1 — Real DWG round-trip test
- **Why:** DWG/DGN paths are written to the ODA/LibreDWG CLIs but unverified
  without a converter installed.
- **Scope:** on a machine with ODA File Converter present, confirm
  DXF→DWG→DXF and DWG→DXF fidelity; add a guarded round-trip check.
- **Dependencies:** a converter installed (network/host gated — cannot be
  done in the current sandbox).
- **Effort:** <1 session once a converter is available.
- **Benchmark affected:** new CAD-I/O fidelity check (not yet in benchmark).

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

- Hard-case benchmark stress tier (`benchmark.py --hard RECIPE`) — geometry
  robust under degradation, text/scale fragile (OCR 40%); guardrail unchanged.
- Circles: recover wall-connected columns (`_recover_connected_circles`,
  Hough + `_verify_ring` gate) — circles 3/6 → 5/6, coverage 96.3 → 96.7%
  (recorded 0.1% precision trade, DECISIONS.md #10).
- Benchmark health panel: per-object confidence + review-count readout.
- Test suite `tests.py` (now 54 checks, no pytest) guarding the faithfulness
  invariants; CI `test` job gates the Windows build.
- Text tier: dimension tick reconstruction (`smart_ocr.normalize_dimension`)
  — synthetic drafting text 88.3% → 96.7% exact; plan OCR 80.0% → 83.3%.
- Text tier: `synth_text.py` — synthetic drafting-text corpus (flywheel
  format) + measured reader baseline (RapidOCR 88.3% exact / 97.2% char).
- Lint: `open_polygon` + `impossible_intersection` checks in `verify.py`,
  high-precision (benchmark actionable stays 0).
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
