# HANDOFF — Start here

**The single most important thing right now:** the dataset infrastructure
*framework* and *synthetic pipeline* are built and tested (`dataset_builder.py`).
What remains of the P0 dataset work — wiring real curated downloaders and a
real-drawing regression suite — is **network-gated and blocked in this
sandbox**. The next unblocked task is **P2 in TASKS.md: open-polygon +
impossible-intersection lint checks** in `verify.py`.

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
- Built `dataset_builder.py`: curated approved-source registry (never-scrape),
  11-category benchmark suite, synthetic degradation library (12 degradations
  → 7 real-world recipes), ground-truth-preserving synthetic generation
  (reuses `benchmark.py`), per-sample metadata, content-hash train/val/bench
  split with dedup, CLI (init/sources/synth/degrade/fetch/split/stats).
  Tested end-to-end in scratchpad. Numeric benchmark unaffected.

## Do this next

Run the standard session in `WORKFLOW.md` (pull → read AI_RULES → this file →
STATUS → TASKS → WORKLOG → baseline benchmark), then pick the highest-priority
*unblocked* task:

- **P0 (blocked here):** wire curated fetchers + real regression suite —
  needs network + per-source license confirmation. Do this on a connected
  machine. Each fetcher must land inside `dataset_builder.fetch` (the single
  sanctioned entry point), never as an ad-hoc scrape.
- **P2 (unblocked, good next increment):** add open-polygon and
  impossible-intersection checks to `verify.py`; keep them high-precision so
  actionable lint stays ~0 on clean plans.
- **P1 (partly unblocked):** text-tier synthetic pre-training can now use
  `dataset_builder.synth` / the degradation library to generate training data
  locally.

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
