# HANDOFF — Start here

**The single most important thing right now:** faded-scan OCR recovery just
landed (`_enhance_faded_ocr`, bilateral denoise + stretch, gated so clean
scans are byte-identical) — stress OCR **40% → 50%**, guardrail unchanged. Use
the stress tier `python benchmark.py --hard appearance_hard` to measure text
work. Remaining stress weak points: scale 0/6 and dashed 0/6 (dimension reads
under heavy degradation aren't clean enough to lock scale — likely GPU
fine-tune territory). Tree clean, pushed, 57 tests green.

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
- Recovered wall-connected circles (3/6 → 5/6, coverage → 96.7%, recorded
  0.1% precision trade in DECISIONS.md #10).
- Added a hard-case stress tier: `benchmark.py --hard appearance_hard`.
- Faded-scan OCR contrast recovery (`_enhance_faded_ocr`): stress OCR 40→50%,
  clean guardrail byte-identical.
- Tests → 62 (added correction-flywheel end-to-end, ring gate, faded gate);
  requirements.txt; .gitignore covers generated sidecars + dataset.

## Do this next

Run the standard session in `WORKFLOW.md`. **Most of the safe, deterministic
fruit is now picked** — the honest state of the remaining gaps:

- **Text under heavy degradation (stress OCR 50%, scale 0/6, dims 2/12)** is
  the biggest remaining lever, but the deep jump needs the **GPU fine-tune**
  (P2, blocked here): `synth_text.py gen -n <large>` → train → re-measure with
  `benchmark.py --hard appearance_hard`. Safe CPU-side wins here are largely
  exhausted (CLAHE hurt; bilateral already shipped).
- **Deliberately-declined as unsafe/not-worth-it (do NOT redo without a new
  idea):** dashed 4/6 — plan 1 is detected but ends 14px short (2px past the
  benchmark tolerance; extending it = inventing a dash), plan 3's rhythm is
  destroyed. scale 5/6 — plan 4's honest *decline* is correct; forcing a lock
  risks a wrong scale on a survey. circle 6th (plan 0) — ring too merged for
  Hough to seed. bare-feet (`23'`→`23`) — unmeasurable on this benchmark.
- **Still genuinely open + safe:** a Phase-B deterministic feature with its own
  new benchmark metric (title-block extraction, line-weight estimation, more
  automatic layer inference beyond the HIDDEN layer already added); more
  high-precision `verify.py` checks; wiring the curated dataset fetchers (P0,
  needs network).
- **Investigated, working-as-intended (do NOT "fix"):** `benchmark.py --hard
  old_photocopy` shows 6 *actionable* lint findings, all `open_polygon`. These
  are legitimate — `open_polygon` requires an angle >20° (collinear breaks are
  excluded), so they are real near-miss corners the photocopy broke, correctly
  flagged for human review. Clean input stays 0. The lint is honest under
  degradation, not a false-positive bug.
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
