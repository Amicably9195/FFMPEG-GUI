# HANDOFF — Start here

**The single most important thing right now:** the text-tier data generator
`synth_text.py` is built, and it gives a measured reader baseline on drafting
text — **RapidOCR 88.3% exact / 97.2% char**, misses dominated by dropped
feet/inch tick marks. The next unblocked task is **P1 in TASKS.md: fix the
dropped tick marks** in `smart_ocr` post-processing (no GPU needed) — the
cheapest large text win, measurable with `synth_text.py measure`.

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
  a measured reader baseline (RapidOCR 88.3% exact / 97.2% char). Misses are
  dropped feet/inch tick marks.

## Do this next

Run the standard session in `WORKFLOW.md`, then pick the highest-priority
*unblocked* task:

- **P1 (unblocked, best next increment):** fix dropped feet/inch tick marks
  in `smart_ocr` post-processing (dimension-aware `'`/`"` reconstruction).
  Measure before/after with `python synth_text.py measure` (baseline: 88.3%
  exact). No GPU.
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
