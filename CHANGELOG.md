# CHANGELOG

What changed, newest first. One entry per shipped increment. Keep it factual
and measurable — include the benchmark effect where there is one. This is the
project's memory of *what* happened; WORKLOG.md holds the *how* and DECISIONS.md
the *why* behind architectural choices.

Format: `YYYY-MM-DD — <engineer> — <summary>` then bullets.

---

## Unreleased

### 2026-07-23 — Claude Code — Line-weight estimation (Phase B)
- `scan2cad.estimate_lineweights`: measures each centerline's true stroke
  width from the ink distance transform and buckets it — relative to the
  drawing's own median — into thin / normal / thick DXF lineweights (0.18 /
  0.25 / 0.50 mm), so the lineweight hierarchy a drafter relies on (bold
  walls, fine dimension/leader lines) survives conversion. `write_dxf` applies
  them and sets `$LWDISPLAY`.
- Faithful + safe by construction: it measures what is drawn and **returns
  None when the drawing has no real width variation**, so a uniform-width
  drawing (like every synthetic benchmark plan) is left untouched — the
  benchmark is byte-identical (96.7/98.9, OCR 83.3, circ 5/6, corners 24/24,
  lint 0). `tests.py` +5 → 69 (bold→thick, fine→thin, uniform→None).

### 2026-07-23 — Claude Code — `benchmark.py --hard all` robustness table
- `--hard all` sweeps every appearance-only recipe (clean, old_photocopy,
  faxed, appearance_hard) and prints a one-look robustness table showing how
  each metric holds as scans degrade. `main()` refactored into a reusable
  `_run()`; the default and single-recipe paths are behavior-identical
  (guardrail byte-for-byte unchanged).
- First full reading: geometry is robust across all conditions (circles
  5–6/6, corners 24/24 except appearance_hard 23/24), while OCR/scale/dashed
  fall off sharply; `old_photocopy` also drives actionable lint to 6 (the lint
  honestly flagging that degraded output needs review) and precision to 85%.

### 2026-07-23 — Claude Code — Dashed linework on its own HIDDEN layer
- `scan2cad.write_dxf`: dashed lines now go on a dedicated `HIDDEN` layer
  (color 1) instead of being mixed into `LINES` — drafting convention, so a
  drafter can toggle hidden/setback linework independently in AutoCAD or
  MicroStation. (Phase-B "automatic layer inference", first step.)
- Safe by construction: scoring reads dashed by `linetype`, not layer, so the
  benchmark is byte-identical (dashed 4/6, all metrics unchanged). `tests.py`
  +2 → 64 (solid → LINES, dashed → HIDDEN).

### 2026-07-23 — Claude Code — Test the correction flywheel end-to-end
- `tests.py` (+5 → 62): an end-to-end test of `corrections.apply_corrections`
  — build a DXF with a misread label on TEXT_REVIEW, apply the fix, and verify
  the text is corrected, the entity is promoted onto the TEXT layer, and an
  untouched good label is left alone. Locks in the trust-critical human loop.
- Also verified (scratchpad) the pipeline handles degenerate inputs (blank,
  all-ink, tiny, noise-only, single-line) without crashing — no fix needed.

### 2026-07-23 — Claude Code — Faded-scan OCR contrast recovery
- `scan2cad._enhance_faded_ocr`: on a faded/photocopied scan (darkest strokes
  gray, not black), lift the copier grain off the letters with an
  edge-preserving bilateral filter, then stretch levels so text reads
  black-on-white. **Gated by the 2nd-percentile intensity** so a clean scan
  (true-black strokes) passes through byte-identical — it can never alter a
  normal drawing's OCR.
- Found by experiment: a plain contrast stretch (CLAHE) *amplifies* the grain
  and made stress OCR worse (40% → 30%); bilateral denoise-then-stretch is the
  right tool (raw Tesseract recall on stress 17% → 43%).
- **Measured:** stress tier (`--hard appearance_hard`) OCR **40% → 50%**,
  precision 95.5% → 96.9%. **Guardrail byte-identical** (OCR 83.3%, coverage
  96.7%, precision 98.9%, circ 5/6, corners 24/24, lint 0). `tests.py` +3 → 57
  (clean scan proven untouched; faded scan restored).

### 2026-07-23 — Claude Code — Hard-case benchmark stress tier
- `benchmark.py --hard RECIPE`: degrade every plan with a `dataset_builder`
  appearance-only recipe (`appearance_hard`, `faxed`, `old_photocopy`) before
  converting. Geometry isn't moved, so the same ground truth scores it. The
  default guardrail run is byte-identical (unchanged).
- `dataset_builder`: added the `appearance_hard` recipe
  (faded_ink + scanner_noise + low_dpi + photocopy) and an `APPEARANCE_ONLY`
  registry of recipes safe to score against untransformed truth.
- **First stress-tier reading** (`appearance_hard`): geometry is robust —
  coverage 94.1%, precision 95.5%, **circles still 5/6** (the new recovery
  holds under heavy degradation), corners 23/24 — while **text and scale are
  the fragile points**: OCR 40%, scale 0/6, dashed 0/6. Actionable lint stays
  0: under stress the tool degrades gracefully and honestly declines scale
  rather than inventing a wrong one. Confirms text as the biggest lever and
  points future robustness work precisely.

### 2026-07-23 — Claude Code — Recover wall-connected circles (3/6 → 5/6)
- `scan2cad`: a column whose ring touches a wall merges into one connected
  component and was dropped by the lone-component circle test. New second pass
  `_recover_connected_circles` re-finds it — Hough proposes, `_refit_ring`
  sharpens by least-squares on the actual ring pixels, and `_verify_ring`
  accepts ONLY rings genuinely present (≥33/36 sectors inked, tight residual).
  The recovered ring is erased so it isn't re-traced as loose arcs. Invents
  nothing: it re-finds a fully-drawn circle, never completes a broken one.
- `tests.py` (+3 → 54 checks): `_verify_ring` accepts a full ring, rejects a
  wall corner and a rectangular room — the gate that keeps recovery faithful.
- **Measured:** circles **3/6 → 5/6 (83%)**, line coverage **96.3% → 96.7%**.
  Trade (recorded, DECISIONS.md #10): line precision **99.0% → 98.9%** and
  info-lint +1, from the hairline gap where an erased ring crosses a wall.
  Corner closure 24/24 and actionable lint 0 held; OCR/dims/dashed/scale held.

### 2026-07-23 — Claude Code — Confidence readout in the benchmark health panel
- `benchmark.py` reads the `.provenance.json` sidecar and adds two
  display-only lines to the health panel: **Confidence (avg)** per object type
  and **Flagged for review** total — making "confidence everywhere" visible in
  the guardrail. Honest by construction: circles average **0.22** (the tool
  is genuinely unsure of them, matching 3/6 recovery) while dimensions 0.95
  and text 0.92 are high.
- Additive only — no score changes. All metrics held: coverage 96.3%,
  precision 99.0%, OCR 83.3%, dims 10/12, circ 3/6, dash 4/6, corners 24/24,
  scale 5/6, actionable lint 0. Benchmark now runs convert with
  `review_out=True` so the sidecars exist to read (no production change).

### 2026-07-23 — Claude Code — Extend tests to more faithfulness invariants
- `tests.py` grows from 37 to 51 checks, now covering: `verify.summarize`
  tallies; `provenance.build_records` **never loses information** (an
  unclassified curve is kept as a polyline and flagged for review, low-conf
  circles are flagged); `provenance.summarize` per-type averages + review
  count; `corrections.save_pair` de-dup (an identical fix is stored once, a
  new label is a new pair). No production bug surfaced — the contracts hold.

### 2026-07-23 — Claude Code — Top-level README (landing page)
- `README.md`: single entry point orienting both users and the AI engineers —
  the doctrine, a user quick-start (pointing at README_Drawing2CAD.md), the
  engineer onboarding order (AI_RULES → HANDOFF → WORKFLOW → STATUS/ROADMAP),
  the prove-every-change commands, the coordination-doc table, a full module
  map, and the honest can/can't summary. Docs only.

### 2026-07-23 — Claude Code — Test suite guarding the faithfulness invariants
- `tests.py`: a dependency-free regression suite (no pytest — `python
  tests.py`), 37 checks locking in the invariants the project rests on:
  `normalize_dimension` never edits non-dimension text; `verify.check` never
  mutates the geometry it inspects and stays high-precision (clean square →
  0 actionable); it still detects duplicate/open_polygon/impossible_
  intersection/dimension_mismatch; `parse_dimension` accepts/declines
  correctly; dataset split is deterministic and dedup-safe; degrade records
  its transforms; `_jsonable` makes numpy json-safe.
- CI: `.github/workflows/build-drawing2cad.yml` gains a `test` job that runs
  `tests.py`; the Windows build now `needs: test`, so a red test blocks the
  exe. WORKFLOW.md step 6 runs tests before the benchmark.

### 2026-07-23 — Claude Code — Text tier: dimension tick reconstruction
- `smart_ocr.normalize_dimension`: reconstructs canonical `A'-B"` from a
  dimension whose feet/inch tick marks the reader dropped (`7-0`, `11-10"`,
  `45-9` → `7'-0"`, `11'-10"`, `45'-9"`). Regex-gated to a two-integer
  hyphen pattern, so it can NEVER touch a room name, note, or bare callout
  number — faithful re-punctuation, not invention. Wired into
  `smart_ocr.refine_words` (the live pipeline) and `synth_text` measurement.
- **Measured gains, no regression:**
  - Synthetic drafting text (RapidOCR): 88.3% → **96.7% exact**,
    97.2% → 98.9% char. Tesseract: 73.3% → 78.3% exact.
  - Plan benchmark OCR/text: **80.0% → 83.3%.** Everything else held:
    coverage 96.3%, precision 99.0%, dimensions 10/12, corners 24/24, scale
    5/6, actionable lint 0.
  - Remaining misses are bare-feet values (`23'` → `23`) that need drawing
    context to recover safely — deliberately left, not invented.

### 2026-07-23 — Claude Code — Text tier: synthetic corpus + reader baseline
- `synth_text.py` (Phase C, Stage 1 — TASKS.md P1): unlimited synthetic
  drafting text (dimensions, room names, notes, callouts) in drafting-style
  fonts, put through the same degradation recipes real scans suffer.
  - `gen` writes labeled (crop → text) pairs in the EXACT flywheel format
    (`corrections.save_pair`), so synthetic pre-training data and real user
    corrections share one pipeline.
  - `measure` scores the current reader on fresh synthetic crops — turns
    "text is the ceiling" into a repeatable number, no training/GPU needed.
- **Measured reader baseline on synthetic drafting text** (new, repeatable):
  - RapidOCR (neural, what the app uses): **88.3% exact / 97.2% char**.
  - Tesseract: 73.3% exact / 93.5% char.
  - Dominant failure mode: dropped feet/inch tick marks (`7'-0"` → `7-0`) —
    a specific, fixable weakness the fine-tune targets.
- Standalone tool; numeric plan benchmark unaffected (coverage 96.3%,
  precision 99.0%, corners 24/24).

### 2026-07-23 — Claude Code — Lint: open-polygon + impossible-intersection
- `verify.py` gains two deterministic checks (TASKS.md P2):
  - `open_polygon` — two long walls whose free ends nearly meet at a corner
    but leave a gap (unclosed room boundary); requires an angle, so collinear
    door gaps are not flagged.
  - `impossible_intersection` — two long walls that cross in their interiors
    with no shared vertex (unhealed overlap).
- Both tuned high-precision: benchmark actionable lint stays 0 across all 6
  plans (info 24); coverage 96.3%, precision 99.0%, corners 24/24 unchanged.

### 2026-07-23 — Claude Code — WORKFLOW: how to run two engineers
- Added a "Running two engineers (Claude Code + Codex)" section to
  `WORKFLOW.md`: the turn-taking rule (one engineer per branch at a time),
  the one-line boot prompt, the sequential hand-off cycle, optional parallel
  mode (separate branches for non-overlapping tasks), and how to check
  progress without reading code. Docs only.

### 2026-07-23 — Claude Code — Dataset infrastructure (framework + synthetic)
- `dataset_builder.py`: the curated benchmark + training corpus, curated +
  synthetic only (DECISIONS.md #7 — never scrape the web).
  - Approved-source registry: 8 named, licensed public sources (LoC HABS/HAER,
    USGS, GSA, NPS, ODA/ezdxf CAD samples, university courseware, USACE
    manuals); `fetch` is the single sanctioned download entry point,
    documented-only until per-source terms are confirmed.
  - Benchmark suite on disk: 11 category folders (vector, clean_scans,
    poor_scans, phone_photos, surveys, architectural, site_plans,
    title_blocks, handwriting, dimensions, symbols), each raw/degraded/meta.
  - Synthetic degradation library: 12 degradations (rotate, skew, perspective,
    blur, scanner_noise, jpeg, stain, fold, shadow, faded_ink, low_dpi,
    photocopy) composed into 7 real-world recipes (office_scan, old_photocopy,
    phone_capture, faxed, archived_survey, ...); geometry-moving degradations
    record their transform matrices so ground truth maps through.
  - Synthetic drawing generation reuses `benchmark.generate_plan`/`render`
    (one generator, no drift) and stores full pixel-space ground truth.
  - Per-sample metadata sidecars; deterministic content-hash
    train/validation/benchmark split with de-dup (variants of one drawing can
    never leak across splits).
  - CLI: init / sources / synth / degrade / fetch / split / stats.
- Numeric benchmark unchanged (new standalone tool): coverage 96.3%,
  precision 99.0%, corners 24/24, actionable lint 0.

### 2026-07-23 — Claude Code — Multi-AI collaboration architecture
- Added the coordination layer that makes Claude Code and ChatGPT Codex
  interchangeable engineers working out of the repository:
  - `AI_RULES.md` — the six binding laws (never invent geometry, never reduce
    benchmark quality, one feature per session, benchmark every change, update
    docs in the same commit, trustworthiness over automation).
  - `WORKFLOW.md` — the standard session (pull → read state → baseline
    benchmark → one task → prove → record → push), 20–30 min checkpointing,
    and resume-from-repo protocol.
  - `TASKS.md` — prioritized backlog; every task carries priority,
    dependencies, effort, and the benchmark metric it affects.
  - `CHANGELOG.md`, `DECISIONS.md`, `WORKLOG.md`, `HANDOFF.md` — memory,
    rationale, play-by-play, and cold-start handoff.
- No engine code changed; benchmark unaffected (coverage 96.3%, precision
  99.0%, corners 24/24).

---

## History (pre-changelog, reconstructed from git)

### 2026 — Verification / lint pass (reviewer priority #2)
- `verify.py`: advisory drawing lint — slivers, duplicate (doubled-wall)
  geometry, floating lines (both ends open), dimension-vs-geometry mismatch.
  Never auto-fixes. Findings carry location + severity in a `.lint.json`
  sidecar.
- Benchmark splits lint into *actionable* (high+medium, stays ~0 on clean
  input) vs *info* (low), making it a trustworthy regression signal.
- Benchmark held: coverage 96.3%, precision 99.0%, corners 24/24.

### 2026 — Confidence + provenance; versioned benchmark
- Per-object 0–1 confidence across text, circle, arc, dimension, dashed,
  scale. `provenance.py` sidecar records source coords, method, confidence,
  review status; never loses information (unclassified geometry kept).
- Benchmark versioned (`BENCHMARK_VERSION = "1.0"`); added project health
  panel.

### 2026 — Data flywheel + review/correction screen
- `corrections.py` + `review_gui.py`: review screen shows each uncertain
  label beside a magnified crop, sorted least-certain first; fixes patch the
  drawing and save local training pairs (deduped). Nothing leaves the machine.

### 2026 — CAD-file input + DWG/DGN output (translation tier)
- `cad_io.py`: DWG/DGN in and out via detected ODA File Converter (LibreDWG
  fallback), graceful DXF fall-back when absent. Modular backend.

### 2026 — Geometry maturity (Phase B increments)
- True LINE/ARC/CIRCLE entities (least-squares circle fit); dashed linetypes
  preserved; editable DIMENSION entities; junction healing so corners and
  T-joints meet exactly (corner closure 24/24).

### 2026 — Free offline neural reader
- Replaced the paid Claude API text reader with RapidOCR (local, free),
  combined with Tesseract. See DECISIONS.md #1.

### 2026 — Foundations
- Scored benchmark harness; PDF input (vector + scanned); single-centerline
  vectorizer; layered DXF output; GitHub Actions Windows build.
