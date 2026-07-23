# AI_RULES — The Constitution

**Read this first, every session, before touching anything.** These rules
bind every engineer on this project — human or AI, Claude Code or ChatGPT
Codex. They do not change without an entry in `DECISIONS.md` and the owner's
sign-off.

The repository is the shared brain. You start every session cold: you know
nothing except what is written down here. Everything you need to work — and
everything the next engineer needs to continue — lives in these files. If a
fact is not in the repo, it does not exist.

---

## The six laws

1. **Never invent geometry.** Reproduce what the source contains. Do not
   straighten what is crooked, close what is open, or add what is implied.
   When you cannot recover something confidently, preserve what you have and
   flag it for review. A flagged uncertainty is a success; a confident
   fabrication is the one unforgivable failure. This is *faithful
   reconstruction over intelligent reconstruction*, and it is the whole
   project.

2. **Never reduce benchmark quality.** `benchmark.py` is the guardrail. No
   change ships if any metric regresses without an explicit, owner-approved
   trade recorded in `DECISIONS.md`. "It looks better" is not evidence; the
   benchmark is.

3. **One measurable feature per session.** Pick the single highest-priority
   task from `TASKS.md`. Do it. Measure it. Commit it. Resist the urge to
   fix five things at once — small, attributable, reversible changes are how
   trust is built and how regressions stay findable.

4. **Benchmark every change.** Run `python benchmark.py` before you start
   (to know the baseline) and after (to prove the effect). Record both
   numbers. A change with no measured effect on the benchmark needs a reason
   for existing, written down.

5. **Update documentation in the same commit as the code.** STATUS.md,
   CHANGELOG.md, WORKLOG.md, TASKS.md, and — if you made an architectural
   choice — DECISIONS.md. Documentation that lags the code is worse than no
   documentation, because it lies. The commit that changes behavior is the
   commit that updates the docs.

6. **Preserve trustworthiness over automation.** When forced to choose
   between a feature that does more automatically and one that is more
   honest about what it did, choose honesty. The review layer, the
   confidence scores, the honest scale decline, the advisory (never
   auto-fixing) lint — these are load-bearing. Any "improvement" that
   removes an honesty feature to look better on paper is a regression, even
   if the benchmark number rises.

---

## What this means in practice

- **Determinism first.** Before reaching for any AI/ML model, exhaust
  geometry, topology, graph connectivity, and CAD heuristics. Deterministic
  code is faster, debuggable, and predictable. AI is the last resort for
  what deterministic methods cannot confidently classify — never the first
  tool reached for.
- **Never lose information.** An object you cannot classify is kept as
  geometry, not dropped. Unknown text → crop + geometry kept. Unknown
  linetype → original segments kept. The system degrades gracefully; it
  never deletes or silently simplifies.
- **Confidence everywhere.** Every recovered object carries a 0–1
  confidence. The review screen surfaces the least-certain first.
- **No per-use cost.** Everything runs locally and free. No paid API calls,
  ever. (This rule already cost us one rewrite — see DECISIONS.md.)
- **Legal humility.** Converted surveys and plans are not certified
  documents. Nothing we do may quietly become the basis for a filing,
  boundary, or construction decision without a human check.

---

## Do not

- Do not scrape the open web for training data. Use curated, legally usable
  sources and synthetic generation only (see `dataset_builder.py` and
  DECISIONS.md).
- Do not bundle proprietary converters (ODA) inside the app. Detect them;
  never ship them.
- Do not push to a branch other than the one you were assigned without
  explicit permission.
- Do not commit large binaries, datasets, or build artifacts (see
  `.gitignore`).
