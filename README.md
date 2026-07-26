# Drawing2CAD

Turn photos, scans, PDFs, and CAD files of technical drawings (surveys, floor
plans, DOB records) into **editable CAD** — DXF always, DWG/DGN when a free
local converter is present. Everything runs **locally, at no per-use cost.**

> **Doctrine: faithful reconstruction over intelligent reconstruction.**
> Reproduce the source exactly. Never invent geometry. When confidence is low,
> preserve what's known and flag it for review. **Trustworthiness is the
> point** — professionals trust output that faithfully preserves what it sees
> and clearly marks what it's unsure of, even when it asks for a human check.

---

## For users

Start with **[README_Drawing2CAD.md](README_Drawing2CAD.md)** — install, the
GUI, the command line, the review-and-correct screen, and tips for good
results.

Quick start:
```
pip install -r requirements.txt
pip uninstall -y opencv-python opencv-python-headless
pip install --force-reinstall --no-deps opencv-contrib-python-headless   # contrib LAST — RapidOCR clobbers it otherwise
python drawing2cad_gui.py
```
See `requirements.txt` for why the opencv-contrib step is separate.

---

## For engineers (human or AI)

This repository is worked by **interchangeable engineers** — Claude Code and
ChatGPT Codex — who each start every session cold and coordinate *only*
through the repo. If you are one of them, read these first, in order:

1. **[AI_RULES.md](AI_RULES.md)** — the six binding laws. Non-negotiable.
2. **[HANDOFF.md](HANDOFF.md)** — what's in flight and what to do next.
3. **[WORKFLOW.md](WORKFLOW.md)** — the standard session and how two engineers
   take turns without colliding.
4. **[STATUS.md](STATUS.md)** · **[ROADMAP.md](ROADMAP.md)** — where the
   project stands and the phased plan.
5. **[VISION.md](VISION.md)** — the north star (target architecture; aspirational).
   **[FINETUNE.md](FINETUNE.md)** — the runbook for the text-tier GPU fine-tune.

Then: `git pull` → read the above → `python tests.py && python benchmark.py`
for the baseline → pick the top task in **[TASKS.md](TASKS.md)** → make one
measurable improvement → prove it → update the docs in the same commit → push.

### Prove every change
```
python tests.py       # faithfulness invariants (no pytest needed) — must stay green
python benchmark.py   # scored quality — must not regress
```
CI runs `tests.py` before it builds the Windows exe, so a red test blocks the
build.

### Coordination docs
| File | Purpose |
|---|---|
| AI_RULES.md | The six binding laws (the constitution) |
| WORKFLOW.md | Standard session, checkpointing, running two engineers |
| TASKS.md | Prioritized backlog (priority, deps, effort, benchmark affected) |
| CHANGELOG.md | What changed, newest first |
| DECISIONS.md | The *why* behind settled architecture decisions |
| WORKLOG.md | Session play-by-play with before/after numbers |
| HANDOFF.md | Cold-start handoff, overwritten each session |

---

## Module map

**Pipeline**
- `scan2cad.py` — the core engine: raster → centerline → true CAD entities
  (LINE / ARC / CIRCLE / LWPOLYLINE / DIMENSION), dimension parsing, scale
  lock, review flagging, DXF export.
- `pdf2cad.py` — PDF input: exact vector lift for CAD PDFs; native-resolution
  handling for scanned PDFs.
- `smart_ocr.py` — free offline neural second-opinion reader (RapidOCR) +
  dimension tick reconstruction; only overrides Tesseract when clearly better.
- `cad_io.py` — DWG/DGN in and out via a detected converter (ODA / LibreDWG),
  graceful DXF fallback.
- `svg_export.py` — optional browser-viewable `.svg` preview of the recovered
  geometry (`--svg`), text coloured by review tier.
- `drawing2cad_gui.py` — the desktop GUI.

**Trust & review**
- `verify.py` — advisory drawing lint (slivers, doubled walls, floating lines,
  open polygons, impossible intersections, dimension mismatches). Never
  auto-fixes.
- `provenance.py` — per-object records (source coords, method, confidence,
  review status) in a sidecar; never loses information.
- `corrections.py` + `review_gui.py` — the correction flywheel: fix uncertain
  text, patch the DXF, and save a local training pair.

**Measurement & data**
- `benchmark.py` — scored synthetic-plan benchmark + project health panel
  (versioned, `BENCHMARK_VERSION`). The guardrail against silent regressions.
- `tests.py` — dependency-free correctness suite for the faithfulness
  invariants.
- `dataset_builder.py` — the curated benchmark + training corpus: approved
  public sources (never scraped), 11 category folders, a synthetic degradation
  library, metadata, and a dedup-safe train/val/benchmark split.
- `synth_text.py` — unlimited synthetic drafting text for the reader
  (flywheel-format pairs) and a `measure` command that scores the reader.

---

## What it can and can't do

CAD files and vector PDFs convert near-perfectly (it's translation, not
recovery). Clean scans recover geometry at 96%+ line coverage. On degraded
photocopies and hand lettering, **geometry still recovers well** but the
*handwriting* wants a human pass — which is what the review screen is for.
A converted survey is **not a certified document**; a person must check it
before any filing, boundary, or construction decision. See
[ROADMAP.md](ROADMAP.md) §2 for the physics of what "perfect" can mean.

Out of scope for now: mechanical drawings, electrical schematics, P&ID
diagrams, freehand sketches, color-coded layer recovery.
