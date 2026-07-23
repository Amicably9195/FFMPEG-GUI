# DECISIONS — Architecture Decision Record

The *why* behind the choices that shape this project. Read before proposing a
change that contradicts one — a decision here is settled until a new entry
supersedes it with the owner's sign-off. Each entry: context, the decision,
and the reason it beat the alternatives.

Format: `## NNN — Title` · Date · Status (Accepted / Superseded by NNN).

---

## 001 — Faithful reconstruction over intelligent reconstruction
*Accepted.* The founding doctrine.

**Context:** The tool converts legal-adjacent documents (surveys, floor
plans, DOB records). Early "smart" behavior (straightening, guessing text)
produced confident-but-wrong output that a professional cannot trust.

**Decision:** Reproduce the source exactly. Never invent. When confidence is
low, preserve what is known and flag it for review rather than guess.

**Reason:** On a legal survey, one confidently-wrong label is worse than ten
honestly-flagged uncertainties. Trust — not a headline accuracy number — is
the product. Every other decision defers to this one.

## 002 — Local and free-per-use only; no paid APIs
*Accepted.* Superseded the original paid-API reader.

**Context:** The first text reader called the Claude API. The owner's
constraint: *"cannot cost money like this."*

**Decision:** Everything runs locally at zero per-use cost. The paid reader
was removed and replaced with RapidOCR + Tesseract (both local, free).

**Reason:** A tool used per-drawing cannot carry a per-drawing bill. Optional
heavier local models (TrOCR, PaddleOCR, VLMs) are allowed as detected,
gracefully-absent add-ons — never as required paid services.

## 003 — DWG via detected external converter, never bundled
*Accepted.*

**Context:** DWG is Autodesk's proprietary, closed format. No free library
writes it perfectly; the ODA File Converter is the industry standard but
cannot legally be bundled in our exe.

**Decision:** Write DXF (full fidelity) always; produce DWG/DGN by handing
DXF to a *detected*, user-installed converter (ODA preferred, LibreDWG
fallback). Fall back cleanly to DXF when none is present. Backend is modular.

**Reason:** DXF is a full-fidelity equivalent AutoCAD and MicroStation open
natively, so no user is blocked. The converter is a one-time free install,
like Tesseract — detected, never shipped.

## 004 — Deterministic geometry before any AI
*Accepted.*

**Context:** "Intelligence" (wall vs dimension vs symbol, arc detection) is
tempting to hand to an ML model.

**Decision:** Exhaust geometry, topology, graph connectivity, symbol
libraries, and CAD heuristics before invoking any AI/ML model. AI is the last
resort for what deterministic methods cannot confidently classify.

**Reason:** Deterministic code is faster, debuggable, predictable, and free
on any CPU. A surprising amount of "understanding" is just classical
geometry. It also keeps behavior explainable — essential for trust.

## 005 — The benchmark is the guardrail; it is versioned
*Accepted.*

**Context:** One maintainer, multiple AI engineers, incremental change. Risk:
silent regressions, or gains that come from an easier benchmark rather than a
better algorithm.

**Decision:** `benchmark.py` grades every change. It is versioned
(`BENCHMARK_VERSION`), so a score improvement is always attributable to a
better algorithm, not a moved goalpost. No change ships on a regression
without an owner-approved trade recorded here.

**Reason:** With interchangeable engineers who start cold, the benchmark is
the only objective, shared definition of "better." "Looks better" is not
admissible evidence.

## 006 — Verification is advisory; it never auto-fixes
*Accepted.*

**Context:** The lint pass (`verify.py`) can detect doubled walls, dangling
lines, dimension mismatches.

**Decision:** Lint reports findings (location + severity) and never modifies
geometry. It is tuned high-precision: on clean input, *actionable*
(high+medium) findings stay ~0.

**Reason:** Auto-fixing is "intelligent reconstruction" that could destroy
faithful data (Decision 001). A report a human trusts beats a silent edit a
human can't see. Low precision (crying wolf) destroys the report's value, so
we optimize for the actionable few, not the noisy many.

## 007 — Curated + synthetic training data; never scrape the web
*Accepted. Implemented by `dataset_builder.py`.*

**Context:** The tool needs a large corpus to train the reader and to
benchmark real difficulty. Owner constraint: *"tell Claude not to randomly
scrape the web."*

**Decision:** Build a curated corpus from high-quality, legally usable
sources (US gov records, public CAD sample libraries, universities, open gov
engineering manuals) plus heavy synthetic generation, plus real user
corrections. `dataset_builder.py` downloads only from an approved-source
registry. No open-web scraping, ever.

**Reason:** Legal cleanliness and quality control. Scraped data carries
license risk and noise; curated + synthetic data is defensible, reproducible,
and lets us deliberately manufacture the hard cases we most need.

## 008 — Never lose information
*Accepted.*

**Context:** Pipelines that drop what they can't classify quietly destroy
source content.

**Decision:** An object that cannot be classified is preserved as geometry.
Unknown text → crop + geometry kept. Unknown linetype → original segments
kept. Provenance rides in a sidecar, not baked into the DXF.

**Reason:** Faithful reconstruction (001) means the output must contain
everything the input did, even the parts we don't understand yet. Graceful
degradation, never silent deletion.

## 009 — The repository is the shared brain
*Accepted.*

**Context:** Two AI engineers (Claude Code, ChatGPT Codex) work the same
project, each starting every session cold with no memory.

**Decision:** Every piece of project knowledge lives in the repo. Coordination
runs through AI_RULES / WORKFLOW / TASKS / CHANGELOG / DECISIONS / WORKLOG /
HANDOFF. Docs are updated in the same commit as the code. Engineers are
interchangeable; the repo, not any engineer's context, is authoritative.

**Reason:** If a fact lives only in an engineer's context window, it is lost
at the next reset. Durable, shared, written state is the only way two
memoryless engineers can hand off mid-task without redoing work.
