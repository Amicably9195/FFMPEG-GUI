# HANDOFF — Start here

**The single most important thing right now:** dimension tick reconstruction
just landed (`smart_ocr.normalize_dimension`) — synthetic drafting text is up
to **96.7% exact** and the plan-benchmark OCR rose **80.0% → 83.3%** with no
regression. The next unblocked task is **P1 in TASKS.md: recover bare-feet
marks using drawing context** (`23'` → `23`) inside `scan2cad`, where the
pipeline already knows which labels are dimensions.

This file is overwritten at the end of every session (and at each 20–30 min
checkpoint) with the current state, so the next engineer — Claude Code or
ChatGPT Codex, cold start — can continue without redoing work. If this file
disagrees with your memory, trust this file.

---

## In-flight task

**None.** Both the collaboration architecture and the dataset-infrastructure
framework are committed and pushed; the tree is clean.

## What just happened

- Built the multi-AI coordination layer (AI_RULES / WORKFLOW / TASKS /
  CHANGELOG / DECISIONS / WORKLOG / HANDOFF).
- Built `dataset_builder.py`: curated registry (never-scrape), 11-category
  suite, synthetic degradation library (12 degradations → 7 recipes),
  ground-truth synthetic generation, split + dedup, CLI.
- Added `open_polygon` + `impossible_intersection` lint checks to `verify.py`
  (high-precision; actionable stays 0).
- Built `synth_text.py`: synthetic drafting-text corpus in flywheel format +
  a measured reader baseline.
- Added `smart_ocr.normalize_dimension` (dimension tick reconstruction):
  synthetic drafting text 88.3% → 96.7% exact; plan OCR 80.0% → 83.3%. No
  regression. Non-dimension text is provably untouched.

## Do this next

Run the standard session in `WORKFLOW.md`, then pick the highest-priority
*unblocked* task:

- **P1 (unblocked, best next increment):** recover bare-feet marks
  (`23'` → `23`) inside `scan2cad`, using the dimension-geometry pairing that
  already exists to know which labels are dimensions (so callout numbers
  stay untouched). Verify plan-benchmark dimension accuracy rises without
  OCR/text regressing.
- **P0 (blocked here):** wire curated fetchers + real regression suite —
  needs network + per-source license confirmation. Each fetcher must land in
  `dataset_builder.fetch`, never as an ad-hoc scrape.
- **P2 (blocked here):** the synthetic-corpus fine-tune needs a GPU —
  `synth_text.py gen -n <large>` then train. Deeper deterministic geometry
  (P3) is fully unblocked if you want a non-text increment.

## Using dataset_builder.py

- Data lives at `~/.drawing2cad_dataset` by default; override with the
  `DRAWING2CAD_DATA` env var (used for tests so it never pollutes home).
- `python dataset_builder.py init` then `synth -n 20`, or `degrade IMG -n 8`,
  then `split`, then `stats`.
- `fetch` is documented-only until a human confirms each source's terms
  (record that in DECISIONS.md before wiring a downloader).

## Environment notes (save yourself the rediscovery)

- **Network is blocked in this sandbox.** External downloads, `apt`, LoC
  fetches fail. Build frameworks + synthetic generation (fully local);
  document network-dependent steps for a connected machine.
- `opencv-contrib-python-headless` is REQUIRED (ximgproc). RapidOCR pulls
  plain opencv which clobbers it — if you touch deps, reinstall contrib last.
- Real DWG round-trip and text-tier fine-tune are blocked here (need a
  converter installed / a GPU + collected corrections). Queued in TASKS.md.
- `dataset_builder.py` is a dev/data tool — intentionally NOT in the
  PyInstaller spec (the shipped GUI never imports it).

## Assigned branch

`claude/drawing-scan-to-cad-v1l3ff` — develop and push here; do not push
elsewhere without explicit permission.
