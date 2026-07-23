# HANDOFF — Start here

**The single most important thing right now:** the multi-AI collaboration
layer is now in place. The next task is the **P0 curated dataset +
benchmark-suite infrastructure** (`dataset_builder.py`). See TASKS.md.

This file is overwritten at the end of every session (and at each 20–30 min
checkpoint) with the current state, so the next engineer — Claude Code or
ChatGPT Codex, cold start — can continue without redoing work. If this file
disagrees with your memory, trust this file.

---

## In-flight task

**None.** The collaboration architecture is committed and pushed; the tree is
clean. You are free to start the next task cleanly.

## What just happened

Stood up the coordination docs: `AI_RULES.md`, `WORKFLOW.md`, `TASKS.md`,
`CHANGELOG.md`, `DECISIONS.md`, `WORKLOG.md`, and this file. No engine code
changed; benchmark unaffected (coverage 96.3%, precision 99.0%, corners
24/24).

## Do this next

1. Run the standard session in `WORKFLOW.md` (pull → read AI_RULES → this
   file → STATUS → TASKS → WORKLOG → baseline benchmark).
2. Start **P0 in TASKS.md — `dataset_builder.py`**. Build it in two
   increments:
   - **Increment 1:** the framework — approved-source registry, the
     benchmark-suite category folders, metadata schema, train/val/benchmark
     split, dedup. Downloads are network-gated; ship the registry + fetch
     code and *document* the approved sources rather than pulling data here.
   - **Increment 2:** the synthetic degradation library (rotation, skew,
     blur, scanner noise, JPEG, stains, folds, shadows, faded ink, low DPI,
     photocopy, perspective) with ground-truth metadata — fully local, no
     network.
3. Constraint (DECISIONS.md #7): **curated + synthetic only, never scrape the
   web.**

## Environment notes (save yourself the rediscovery)

- **Network is blocked in this sandbox.** External downloads, `apt`, and LoC
  fetches fail. Build frameworks and synthetic generation (both fully local);
  document network-dependent steps for a connected machine.
- `opencv-contrib-python-headless` is REQUIRED (ximgproc). RapidOCR pulls
  plain opencv which clobbers it — if you touch deps, reinstall contrib last.
- Real DWG round-trip and text-tier fine-tune are blocked here (need a
  converter installed / a GPU + collected corrections). Left in TASKS.md as
  P1/P2 for a capable host.
- Benchmark is synthetic plans only today; the P0 dataset work is what lets
  the benchmark grade real difficulty.

## Assigned branch

`claude/drawing-scan-to-cad-v1l3ff` — develop and push here; do not push
elsewhere without explicit permission.
