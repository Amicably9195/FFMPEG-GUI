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
- Added a hard-case stress tier: `benchmark.py --hard appearance_hard`
  (appearance-only degradation, same ground truth). Default run unchanged.

## Do this next

Run the standard session in `WORKFLOW.md`, then pick the highest-priority
*unblocked* task:

- **P2 (unblocked) — more lint checks or deeper deterministic geometry.**
  The circles pass is done (5/6). Remaining single circle miss is plan 0,
  whose ring is too merged for Hough to seed; not worth chasing (risk > 1/6).
  Options: (a) dashed-linetype recovery on dirty scans (4/6 → improve, same
  care as circles — never invent dashes); (b) a Phase-B deterministic feature
  (title-block extraction, line-weight estimation); (c) more `verify.py`
  checks. Whatever you pick: benchmark before/after, keep actionable lint 0.
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
