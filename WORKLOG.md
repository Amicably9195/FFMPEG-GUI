# WORKLOG — Session play-by-play

The running narrative of who did what, when, and what the benchmark said.
Append newest entries at the top. This is where checkpoints land during long
tasks (every 20–30 min) so an interrupted session can be resumed from the
repo alone. Keep entries short and factual: task, steps, before/after
numbers, state at stop.

---

## 2026-07-23 — Claude Code — VISION.md + green/yellow/red tiers

**Task:** owner shared a refined vision/architecture doc. Assessed it against
reality (most of it already our doctrine + shipped; genuinely new:
compiler-pipeline framing, G/Y/R tiers; aspirational: semantic-AI tier,
constraint solver, title-block, SVG). Adopted it honestly.

**Did:** (1) `VISION.md` — the doc as canonical north star with a preamble +
"build status today" section separating vision from shipped, so it can't be
read as overclaiming. (2) `provenance.tier()` — 0..1 confidence → green/yellow/
red (flagged→red always); stamped on every record, counted in summarize,
surfaced in the benchmark panel (green 487 / yellow 0 / red 15).

**Result:** guardrail byte-identical; tests +8 → 77. README points at
VISION/FINETUNE.

**State at stop:** committed and pushed; tree clean.

---

## 2026-07-23 — Claude Code — Line-weight estimation (Phase B, autonomous)

**Task:** owner away, "everything is a yes" — took the Phase-B line-weight
feature I'd flagged as needing approval.

**Did:** `estimate_lineweights(ink, segments)` — samples each centerline's
stroke width from the distance transform (interior only; junctions inflate
ends), buckets relative to the drawing's median into thin/normal/thick DXF
lineweights. `write_dxf` applies them + sets $LWDISPLAY.

**Safe by construction:** returns None when there's no real width variation,
so uniform drawings (all benchmark plans) are untouched → benchmark
byte-identical. Verified.

**Validation path:** direct unit test (bold width-9 → 50, fine width-3 → 18,
uniform → None) after tuning bucket thresholds (first pass put bold walls on
normal because equal thick/thin populations sit the median between them;
loosened to 0.8×/1.25×med). +5 tests → 69. Benchmark unchanged.

**State at stop:** committed and pushed; tree clean.

---

## 2026-07-23 — Claude Code — Robustness table + HIDDEN layer

**Two small safe increments (deterministic fruit mostly picked):**

1. Dashed linework → its own `HIDDEN` layer (drafting convention; scoring
   reads dashed by linetype not layer, so benchmark byte-identical). +2 tests.

2. `benchmark.py --hard all`: refactored `main()` into a reusable `_run()`
   and added an all-recipe sweep printing a robustness table. Default and
   single-recipe paths verified behavior-identical.

**First full robustness reading:**
```
recipe           cover  prec   OCR    dim   circ dash corner scale act
clean            96.7% 98.9% 83.3% 10/12  5/6  4/6  24/24  5/6   0
old_photocopy    97.1% 85.0% 80.0%  7/12  5/6  3/6  24/24  4/6   6
faxed            95.3% 96.8% 40.0%  3/12  6/6  1/6  24/24  0/6   1
appearance_hard  93.1% 96.9% 50.0%  2/12  5/6  0/6  23/24  0/6   0
```
Geometry robust everywhere (circles 5-6/6); text/scale/dashed fall off;
old_photocopy raises actionable lint to 6 (honest flagging of degraded output).

**State at stop:** both committed and pushed; tree clean; 64 tests green.

---

## 2026-07-23 — Claude Code — Faded-scan OCR contrast recovery

**Task:** attack the stress tier's weakest point (OCR 40%) safely.

**Process:** designed a gate (2nd-percentile intensity) that cleanly
separates clean (p2 0-18) from faded (p2 121-128) scans, so clean OCR is
untouched by construction. First tried CLAHE — it AMPLIFIED photocopy grain
and made stress OCR worse (40% → 30%); reverted. Prototyped denoise modes in
scratchpad: bilateral (edge-preserving) doubled raw Tesseract recall
(17% → 43%). Shipped bilateral denoise + level stretch.

**Measured:** stress OCR 40% → 50%, precision 95.5% → 96.9%. Guardrail
byte-identical (OCR 83.3%, all metrics unchanged). tests +3 → 57 (clean scan
proven byte-identical through the enhancer; faded scan restored).

**Note:** stress scale/dims still 0 — text recall rose but dimension reads
aren't yet clean enough to lock scale under heavy degradation (GPU fine-tune
territory).

**State at stop:** committed and pushed; tree clean.

---

## 2026-07-23 — Claude Code — Hard-case benchmark stress tier

**Task:** the user's explicit priority — deliberately measure hard cases.
First ruled out pushing dimension/scale (5/6): plan 4's honest scale *decline*
is correct trustworthy behavior; forcing a lock risks a WRONG scale on a legal
survey (doctrine forbids). So built a safe, additive robustness tier instead.

**Did:** `benchmark.py --hard RECIPE` degrades each plan with a
`dataset_builder` appearance-only recipe (no geometry move → same ground truth
scores it); default run unchanged. Added `appearance_hard` recipe +
`APPEARANCE_ONLY` registry to dataset_builder.

**First reading (appearance_hard):** geometry robust (cover 94.1%, prec 95.5%,
circles 5/6, corners 23/24); text/scale fragile (OCR 40%, scale 0/6, dashed
0/6). Actionable lint 0 — graceful degradation, honest scale decline. Also
validated the new circle recovery holds under heavy degradation.

**Guardrail:** default `python benchmark.py` byte-identical (96.7/98.9, OCR
83.3, circ 5/6, corners 24/24, lint 0). tests green.

**State at stop:** committed and pushed; tree clean.

---

## 2026-07-23 — Claude Code — Recover wall-connected circles (3/6 → 5/6)

**Task:** the circles/arcs (3/6) opportunity, done safely with real diagnosis.

**Diagnosis (scratchpad, mirroring the benchmark's shared RNG):** the missed
circles (plans 0/3/5) are columns whose ring is electrically connected to the
wall network → one giant component (e.g. 371×722) → the lone-component test
can't isolate them. The ring is fully drawn; recovering it invents nothing.

**Prototyped before touching the engine:** Hough + a strict `_verify_ring`
gate (≥33/36 sectors inked). Swept `param2`: 16 recovers plans 3 & 5 with
ZERO false positives (wall corners/rooms fail the fill test). Plan 0's ring is
too merged for Hough even when pushed — accepted 5/6 rather than risk FPs.

**Shipped:** `_verify_ring`, `_refit_ring` (least-squares sharpen), and
`_recover_connected_circles` as a second pass in `detect_circles`; erase the
recovered ring so it isn't re-traced. Added a ring-gate test (54 checks).

**Measured:** circles 3/6 → 5/6, coverage 96.3% → 96.7%; precision 99.0% →
98.9% and info-lint +1 (hairline wall gap) — a deliberate trade recorded in
DECISIONS.md #10. Corners 24/24, actionable lint 0, all else held.

**State at stop:** committed and pushed; tree clean.

---

## 2026-07-23 — Claude Code — Confidence readout in health panel

**Task:** make per-object confidence visible in the guardrail ("confidence
everywhere" / trust is the point).

**Did:** `benchmark.py` reads the `.provenance.json` sidecar and prints two
display-only panel lines — Confidence (avg) per type, Flagged for review
total. Benchmark now passes `review_out=True` so sidecars exist (no
production change). Fixed the aggregation to skip meta keys (`_total`,
`_review_items`).

**Result:** additive; every score unchanged (96.3/99.0, OCR 83.3, circ 3/6,
corners 24/24, lint 0/24). New readout: circle 0.22 (honestly low),
dimension 0.95, text 0.92, polyline 0.50; 13 flagged for review. tests green.

**State at stop:** committed and pushed; tree clean.

---

## 2026-07-23 — Claude Code — Extend test coverage

**Task:** harden the safety net the two-engineer workflow depends on. First
re-examined the circles/arcs metric (3/6) and **decided against** chasing it:
on a broken ring, emitting an arc/nothing is the faithful behavior — forcing a
full circle would invent the missing arc (violates AI_RULES #1), and loosening
thresholds risks phantom circles at corners (precision). Wrong direction.

**Did instead:** extended `tests.py` 37 → 51 checks covering `verify.summarize`,
`provenance` never-lose-information + summarize, and `corrections.save_pair`
dedup. Ran the new modules through their contracts.

**Result:** PASSED all 51 checks; no production bug found. Benchmark untouched.

**State at stop:** committed and pushed; tree clean.

---

## 2026-07-23 — Claude Code — Top-level README

**Task:** give the growing repo (13 modules + 7 coordination docs) one entry
point for users and for interchangeable AI engineers.

**Did:** wrote `README.md` — doctrine, user quick-start (→ README_Drawing2CAD),
engineer onboarding order + prove-every-change commands, coordination-doc
table, module map, honest can/can't. Considered chasing the circles/arcs
dirty-scan metric (3/6) but declined: it's a geometry-threshold change with
real false-positive regression risk I couldn't fully validate in budget —
"never reduce benchmark quality" wins over a gamble.

**Result:** docs only; `tests.py` green, benchmark untouched.

**State at stop:** committed and pushed; tree clean.

---

## 2026-07-23 — Claude Code — Test suite + CI gate

**Task:** protect every shipped increment for interchangeable engineers — a
dependency-free correctness suite the benchmark can't isolate.

**Did:** wrote `tests.py` (37 checks, no pytest): faithfulness invariants
(reader never edits non-dimension text; `verify.check` never mutates input,
0 actionable on a clean square, still catches every defect type;
`parse_dimension` accept/decline; dataset split determinism + dedup; degrade
transform recording; `_jsonable`). Added a `test` job to the CI workflow and
made the Windows `build` job `needs: test`. WORKFLOW.md step 6 now runs
`python tests.py` before the benchmark.

**Result:** `python tests.py` → PASSED all 37 checks. Benchmark untouched
(no engine change): 96.3% / 99.0% / 24-24, OCR 83.3%.

**State at stop:** committed and pushed; tree clean.

---

## 2026-07-23 — Claude Code — Text tier: dimension tick reconstruction

**Task:** TASKS.md P1 — fix the dropped feet/inch tick marks the baseline
exposed.

**Baseline:** RapidOCR 88.3% exact / 97.2% char on synthetic drafting text;
plan-benchmark OCR 80.0%.

**Did:** added `smart_ocr.normalize_dimension` — regex-gated (`^\d+'?-\d+"?$`)
reconstruction of `A'-B"`; passes non-dimensions through untouched (no
invention). Wired into `refine_words` (live pipeline) and both `synth_text`
readers. Sanity-checked it leaves BATH/NORTH/971/23 unchanged.

**After (measured, same seed/n):** RapidOCR 88.3% → **96.7% exact**,
97.2% → 98.9% char; Tesseract 73.3% → 78.3%. Full plan benchmark: OCR
80.0% → **83.3%**, all else held (coverage 96.3%, precision 99.0%, dims
10/12, corners 24/24, scale 5/6, actionable lint 0). No regression.

**Remaining:** bare-feet (`23'`→`23`) need drawing context (dimension
geometry) to recover — left honestly, queued as next text increment.

**State at stop:** committed and pushed; tree clean.

---

## 2026-07-23 — Claude Code — Text tier: synthetic corpus + reader baseline

**Task:** TASKS.md P1 — text-tier synthetic pre-training. Training is
GPU-gated; the unblocked increment is the data generator + a measured
baseline of the current reader on drafting text.

**Did:** wrote `synth_text.py` — synthetic drafting-text generator
(dimensions/room names/notes, drafting fonts, `dataset_builder` degradation
recipes). `gen` writes pairs via `corrections.save_pair` (identical flywheel
format). `measure` scores the current reader (exact-match + Levenshtein char
accuracy). Reused smart_ocr / pytesseract; no pipeline code touched.

**Measured (new baseline, repeatable):** on synthetic drafting text —
RapidOCR 88.3% exact / 97.2% char; Tesseract 73.3% / 93.5%. Misses are
dominated by dropped feet/inch tick marks (`7'-0"` → `7-0`).

**Numeric plan benchmark:** unaffected (standalone tool) — 96.3% / 99.0% /
24-24.

**State at stop:** committed and pushed; tree clean. Next: either scale the
corpus + run the GPU fine-tune (GPU-gated), or attack the tick-mark weakness
in reader post-processing (unblocked).

---

## 2026-07-23 — Claude Code — Lint: open-polygon + impossible-intersection

**Task:** TASKS.md P2 — extend `verify.py` with two deterministic checks.

**Baseline:** actionable lint 0 / info 24; coverage 96.3%, precision 99.0%,
corners 24/24.

**Did:** added `open_polygon` (two long walls whose free ends nearly meet at
a corner but leave a gap; angle required so door gaps aren't flagged) and
`impossible_intersection` (two long walls crossing with no shared vertex).
Updated verify.py docstring.

**After:** actionable 0 / info 24 unchanged; coverage 96.3%, precision 99.0%,
corners 24/24 unchanged — both checks are high-precision (0 false positives
across all 6 synthetic plans, clean and dirty).

**State at stop:** committed and pushed; tree clean.

---

## 2026-07-23 — Claude Code — Dataset infrastructure (TASKS.md P0, part 1)

**Task:** Build `dataset_builder.py` — the curated benchmark + training
corpus framework and synthetic degradation pipeline (owner's dataset-strategy
request; DECISIONS.md #7).

**Baseline benchmark (before):** coverage 96.3%, precision 99.0%, corners
24/24, actionable lint 0. (dataset_builder is a new standalone tool; the
numeric benchmark does not exercise it.)

**Did:**
- Wrote `dataset_builder.py`: approved-source registry (8 curated sources,
  never-scrape), 11-category on-disk suite, synthetic degradation library (12
  degradations → 7 recipes), ground-truth-preserving synthetic generation
  (reuses `benchmark.generate_plan`/`render`), per-sample metadata,
  content-hash train/val/benchmark split with dedup, CLI.
- Fixes during build: matched `generate_plan`'s `(segs,labels,dims,circles,
  dashes)` signature and its python-`random`-vs-numpy-rng split; added a
  `_jsonable` numpy→python sanitizer for metadata dumps.
- Tested end-to-end in scratchpad (`DRAWING2CAD_DATA` override): init → synth
  8 → degrade 6 → split → stats all pass; ground truth (15 segs / 1 circ / 1
  dash) and split assignment verified; degraded variants correctly inherit
  their parent drawing's split (no cross-split leakage).

**After benchmark:** unchanged — coverage 96.3%, precision 99.0%, corners
24/24, actionable lint 0.

**State at stop:** committed and pushed; tree clean. Framework + synthetic
done. Remaining P0 (wiring real curated fetchers + real regression suite) is
network-gated — blocked in this sandbox, queued in TASKS.md.

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
