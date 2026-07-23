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

### P0 — Curated dataset + benchmark-suite infrastructure
- **Why:** Reading and hard-case handling are the ceiling on everything.
  We need a large, legally clean, categorized corpus and a synthetic
  degradation pipeline to train and to benchmark against real difficulty.
- **Scope:** `dataset_builder.py` — approved-source registry (US gov records,
  public CAD sample libraries, universities, open gov engineering manuals),
  category folders (`benchmark/vector/`, `clean_scans/`, `poor_scans/`,
  `phone_photos/`, `surveys/`, `architectural/`, `site_plans/`,
  `title_blocks/`, `handwriting/`, `dimensions/`, `symbols/`), a synthetic
  degradation library (rotation, skew, blur, scanner noise, JPEG, stains,
  folds, shadows, faded ink, low DPI, photocopy, perspective), metadata per
  sample, train/validation/benchmark split, dedup.
- **Dependencies:** none for the framework + synthetic generation (fully
  local). Actual downloads are network-gated and happen on a connected
  machine; ship the registry + fetch code, document the sources.
- **Effort:** 1–2 sessions (framework first, degradation library second).
- **Benchmark affected:** enables a real regression-image suite; expands
  what `benchmark.py` can grade (currently synthetic plans only).
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

- Verification/lint pass (advisory, never auto-fix) — reviewer priority #2.
- Confidence scoring + provenance sidecar; versioned benchmark (v1.0).
- STATUS.md living doc + benchmark health panel.
- Data flywheel + review/correction screen.
- CAD-file input and DWG/DGN output (translation tier).
- True circles/arcs, dashed linetypes, dimension entities, junction healing.
- Free offline neural reader (RapidOCR), replacing the paid API.
