# WORKFLOW — How every session runs

Claude Code and ChatGPT Codex are **interchangeable engineers** on this
project. Neither owns it; the repository does. Any engineer must be able to
pick up exactly where the last one stopped, mid-task, from a cold start,
using only what is written down. This document is that protocol.

---

## Running two engineers (Claude Code + Codex)

The two AIs never communicate directly. **They coordinate only through the
repository.** Neither remembers anything between sessions, so every fact and
every handoff lives in the tracked docs — not in a chat window.

**The turn-taking rule (do not break this):** on a given branch, **only one
engineer works at a time.** The other stays idle until the first has
committed and pushed. Two engineers editing the same files at once produces
merge conflicts and lost work — and neither AI can safely merge the other's
half-finished thoughts.

### The boot prompt

You do not re-explain the project. Give whichever engineer is up this single
line and let the repo do the rest:

> **Follow WORKFLOW.md. Read AI_RULES.md and HANDOFF.md first, then pick up
> the next task.**

That triggers the standard session below. Because both engineers obey the
same AI_RULES.md and this WORKFLOW.md, the work comes out interchangeable.

### The hand-off cycle (sequential — the default)

One branch, engineers take turns. Zero merge conflicts.

1. Engineer A boots, does one task, updates docs, commits, pushes, **stops.**
2. You point Engineer B at the repo with the boot prompt.
3. B pulls, reads HANDOFF.md, sees exactly where A stopped, does the next
   task, commits, pushes, stops.
4. Repeat. Either engineer can be A or B on any given turn.

If A's session is interrupted mid-task (context runs out), B resumes from
A's last HANDOFF.md checkpoint — that is what the 20–30 min checkpointing
rule guarantees.

### Parallel mode (optional — faster, more overhead)

Only when two tasks touch **different files** (e.g. one does `verify.py`
lint, the other does the text tier): give each engineer its **own branch**
and an independent task from TASKS.md, then you merge both into the main
branch yourself. If the tasks might touch the same code, use sequential mode
instead — it is slower but never conflicts.

### How you check progress without reading code

- `HANDOFF.md` — what just happened, what is next.
- `CHANGELOG.md` — the running list of shipped changes.
- `python benchmark.py` — proof the last change regressed nothing.

---

## The standard session

Follow these steps in order. Every session, every engineer.

### 1. Sync
```
git pull
```
Start from the latest shared state. Never work on a stale tree.

### 2. Read the state (in this order)
1. **AI_RULES.md** — the constitution. Re-read it; it binds this session.
2. **HANDOFF.md** — what the last engineer was in the middle of, and the
   single most important thing to know right now.
3. **STATUS.md** — the current state of the project and the priority list.
4. **TASKS.md** — the prioritized backlog with dependencies and effort.
5. **WORKLOG.md** (latest entries) — the recent play-by-play, so you don't
   repeat or undo work.

### 3. Establish the baseline
```
python benchmark.py
```
Record the numbers *before* you change anything. You cannot claim an
improvement — or prove you caused no regression — without this baseline.

### 4. Pick exactly one task
Take the highest-priority item from `TASKS.md` whose dependencies are met.
One. Not two. (See AI_RULES law #3.) If HANDOFF.md says a task is
in-progress, finish that one first before starting anything new.

### 5. Do the one measurable improvement
Implement it. Keep the change small and attributable. Obey every law in
AI_RULES.md while you work.

### 6. Prove it
```
python tests.py        # correctness invariants must stay green
python benchmark.py    # quality must not regress
```
`tests.py` (dependency-free, no pytest) guards the faithfulness invariants —
the reader never edits non-dimension text, lint never mutates geometry,
dataset dedup never leaks across splits. It must pass. Then compare the
benchmark to the baseline from step 3: the change must improve its target
metric and regress nothing else (or carry an owner-approved trade in
DECISIONS.md). CI runs `tests.py` before every build, so a red test blocks
the Windows exe.

### 7. Record and commit — in one commit
Update, in the same commit as the code:
- **CHANGELOG.md** — what changed, one entry.
- **WORKLOG.md** — the play-by-play, with before/after benchmark numbers.
- **TASKS.md** — move the finished task out; add any new tasks discovered.
- **STATUS.md** — if the state of the project changed.
- **DECISIONS.md** — only if you made an architectural choice.
- **HANDOFF.md** — overwrite with the current state for the next engineer.

Then:
```
git add -A && git commit && git push
```

---

## Checkpointing (every 20–30 minutes)

Long tasks get interrupted — context runs out, sessions end, the network
drops. Assume it will happen to you mid-thought. To survive it:

- Every 20–30 minutes of work, **update HANDOFF.md and WORKLOG.md** with
  where you are, even if the task is not done. Commit a checkpoint if the
  tree is in a coherent state (or use a `WIP:` commit message if not).
- HANDOFF.md must always answer: *if I vanished right now, what is the one
  thing the next engineer needs to know to continue without redoing my
  work?*
- Never leave the repository as the only record of your intent living inside
  your context window. If it's only in your head, it's already lost.

## Ending a session

Before you stop — whether finished or interrupted:
1. Update HANDOFF.md, WORKLOG.md, and CHANGELOG.md.
2. Move completed tasks out of TASKS.md; add newly discovered ones.
3. Commit and push. Leave the tree clean if at all possible.

## Resuming after an interruption

You may be a different engineer, or the same one after a context reset.
Either way: **do not trust memory, trust the repo.** Run the standard
session from step 1. HANDOFF.md tells you the in-flight task; WORKLOG.md
tells you how far it got. Re-establish the benchmark baseline before
assuming anything about current quality.

---

## The one-paragraph version

Pull. Read AI_RULES → HANDOFF → STATUS → TASKS → WORKLOG. Benchmark to get
the baseline. Pick one task. Do it. Benchmark to prove it. Update every doc
in the same commit. Push. Checkpoint HANDOFF.md every 20–30 minutes so the
next engineer — maybe you, maybe the other AI — can continue from a cold
start without losing a thing.
