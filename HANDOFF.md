# HANDOFF — Start here

**The single most important thing right now:** a long, clean session shipped
10 committed increments (coordination layer, dataset_builder, synth_text +
reader tooling, dimension tick reconstruction → plan OCR **80.0% → 83.3%**,
two new lint checks, a 51-check test suite + CI gate, README, confidence
readout). Tree is clean, all pushed, tests green. The best next task is a
**focused session on circles/arcs (3/6)** — see "Do this next".

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
- Added `tests.py` (now 51 checks, no pytest) guarding the faithfulness
  invariants — reader, verify, provenance (never-lose-information),
  corrections dedup, dataset split/dedup. Wired into CI (build `needs: test`)
  and WORKFLOW step 6. Run `python tests.py` before every push.
- Note for the next engineer: the circles/arcs metric (3/6) was examined and
  deliberately NOT chased — forcing full circles from broken rings would
  invent geometry (AI_RULES #1). If you revisit it, only recover circles
  whose full ring is genuinely present (e.g. a column touching a wall that
  the component-merge currently drops), and prove precision stays 99%.
- Added top-level `README.md` — the landing page for users and engineers
  (doctrine, onboarding order, module map, coordination-doc table).
- Benchmark health panel now shows per-type average confidence + review count
  (from the provenance sidecar). Honest: circle avg confidence 0.22 mirrors
  the 3/6 circle recovery.

## Do this next

Run the standard session in `WORKFLOW.md`, then pick the highest-priority
*unblocked* task:

- **P1 (unblocked, best next increment) — circles/arcs 3/6, safely.** The
  failure: `detect_circles` (scan2cad ~L702) only accepts a circle that is
  its own isolated connected component; a column whose ring TOUCHES a wall
  merges into one component and is dropped (even on clean plan 0). Recovering
  it invents nothing — the full ring is present in the ink. Approach: for
  components rejected as lone circles, search for a ring within them
  (e.g. `cv2.HoughCircles` constrained to `[min_r, max_r]`), then accept ONLY
  if it passes the SAME ring test detect_circles already uses (p95 residual +
  ≥33/36 sectors filled). That gate is your precision protection. **Prove
  precision stays ≥99% and coverage/corners hold** before keeping it; if a
  wall corner sneaks a false circle, tighten or revert. Do NOT force full
  circles from broken rings — that is invention (AI_RULES #1).
  - *Note:* bare-feet recovery (`23'`→`23`) was considered and deprioritized —
    the plan benchmark's dimensions are always `N'-M"`, so it can't be
    measured there, and blind recovery risks corrupting callout numbers.
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
