# WORKLOG — Session play-by-play

The running narrative of who did what, when, and what the benchmark said.
Append newest entries at the top. This is where checkpoints land during long
tasks (every 20–30 min) so an interrupted session can be resumed from the
repo alone. Keep entries short and factual: task, steps, before/after
numbers, state at stop.

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
