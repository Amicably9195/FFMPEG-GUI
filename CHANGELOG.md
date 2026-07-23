# CHANGELOG

What changed, newest first. One entry per shipped increment. Keep it factual
and measurable — include the benchmark effect where there is one. This is the
project's memory of *what* happened; WORKLOG.md holds the *how* and DECISIONS.md
the *why* behind architectural choices.

Format: `YYYY-MM-DD — <engineer> — <summary>` then bullets.

---

## Unreleased

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
