# CHANGELOG

What changed, newest first. One entry per shipped increment. Keep it factual
and measurable — include the benchmark effect where there is one. This is the
project's memory of *what* happened; WORKLOG.md holds the *how* and DECISIONS.md
the *why* behind architectural choices.

Format: `YYYY-MM-DD — <engineer> — <summary>` then bullets.

---

## Unreleased

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
