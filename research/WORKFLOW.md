# Research Workflow: Theory ⇄ Experiment Loop

This document defines how two Claude sessions — a **theory session** (Claude desktop app, repo folder connected) and an **experiment session** (Claude Code) — collaborate on one research problem through shared files in this repository. Both sessions must read this file before acting.

## 1. Roles and ownership

| File | Owner (only writer) | Reader | Purpose |
|---|---|---|---|
| `research/THEORY.md` | Theory session | Experiment session | Authoritative statement of the problem, results, open questions, and experiments to run next. |
| `research/FINDINGS.md` | Experiment session | Theory session | Append-only log of empirical results and their implications for the theory. |
| `research/WORKFLOW.md` | Human | Both | This protocol. |
| `CLAUDE.md` | Human | Experiment session | Standing instructions for Claude Code (see §7). |

Ownership is strict. The experiment session never edits `THEORY.md`; the theory session never edits `FINDINGS.md`. If a session believes the other file is wrong, it records that in its own file and the human decides.

The human reviews both files at every commit. They are deliberately short; they are the only place where a silent divergence between the prototype and the theory can be caught.

## 2. `THEORY.md` structure

```
# <Project title>   (version vN, YYYY-MM-DD)

## 1. Problem statement, notation, assumptions
   Define every symbol. State the setting and all standing assumptions.

## 2. Results
   Each result has an ID (R-<n>) and a tag FINAL or PROVISIONAL, with the
   derivation inline or a pointer to the file holding it.
   - FINAL: established; safe to build on; may be exported to other projects.
   - PROVISIONAL: may change; experiments may be pending.

## 3. Open questions and conjectures

## 4. Rejected approaches and why

## 5. What to test next
   Ordered list. Each item:
   - ID: T-<n>
   - Hypothesis (one sentence, falsifiable)
   - Tests result: R-<n>, or "new"
   - What to vary / what to hold fixed
   - Confirms if: ...   Refutes if: ...
   - Starting point: <script/notebook path>, or "new"

## 6. Changelog
   vN, YYYY-MM-DD — what changed and why (reference FINDINGS entries by date).
```

## 3. `FINDINGS.md` structure

A header with the entry template, then entries in chronological order. Entries are never edited or deleted; a correction is a new entry that references the one it supersedes.

```
### YYYY-MM-DD HH:MM — <short title>
- Tests: T-<n>  (or "unplanned")
- Hypothesis: <restated from THEORY.md>
- Setup: script/notebook, parameters, data, seed, commit hash
- Result: numbers, tables, artifact paths (plots, CSVs)
- Criterion from THEORY.md: <criterion> → met / not met
- Implication for theory: <one sentence a mathematician can act on>
- Flag: CONFIRMS | CONTRADICTS | SUGGESTS-NEW-PATH | UNVERIFIED
- Supersedes: <entry date>, if any
```

Flag meanings:
- **CONFIRMS** — criterion met; candidate for retagging the result FINAL.
- **CONTRADICTS** — criterion not met. Include enough detail to diagnose theory vs. experiment design vs. implementation.
- **SUGGESTS-NEW-PATH** — an unplanned observation. Logged with evidence; **not pursued** by the experiment session on its own.
- **UNVERIFIED** — numbers reconstructed from existing files (notebook outputs, old CSVs) rather than reproduced by a run. Must be rerun and re-flagged.

## 4. The loop

One cycle = one theory → experiment → theory round trip. A cycle can take an hour or a week.

### Step 1 — Theory → experiment spec (theory session)
Work the math. When something is ready to test:

> Update THEORY.md: record the new result as PROVISIONAL and add an item to "What to test next" with hypothesis, variables, confirm/refute criteria, and the script to start from. Bump the version and add a changelog entry.

Commit.

### Step 2 — Experiment (experiment session)
Start a fresh Claude Code session (sessions are disposable; state lives in the files):

> Read research/WORKFLOW.md and research/THEORY.md. Take item T-<n> from "What to test next" and run it. Before writing code, restate the hypothesis and the pass/fail criterion. Log the result to FINDINGS.md using the template, with commit hash and flag. Stop before starting the next item.

The human reviews the entry: did the experiment test what the theory claimed? Commit.

Batching is fine: run several items in one session, one entry per item.

### Step 3 — Findings → theory (theory session)

> Read FINDINGS.md entries after <date/version> against THEORY.md. For each entry: does it confirm, contradict, or extend the theory? For CONTRADICTS, diagnose whether the theory, the experiment design, or the implementation is at fault before changing anything. Update THEORY.md: revise affected results, retag FINAL/PROVISIONAL, rewrite "What to test next", add a changelog entry.

Commit. Return to Step 1.

Do Step 3 once per batch of experiments, not once per experiment.

## 5. Side paths

- **Unplanned discovery.** The experiment session logs SUGGESTS-NEW-PATH with evidence and continues with the planned items. The theory session decides in Step 3 whether to promote it into THEORY.md. Direction stays with the theory side.
- **Contradiction caused by a bug.** The experiment session fixes the code, reruns, and appends a new entry with `Supersedes:` pointing to the old one. History is never rewritten.
- **Result graduates.** When an experiment confirms a PROVISIONAL result, Step 3 retags it FINAL.
- **Reproducibility check.** The first real Claude Code session after setup reruns all UNVERIFIED entries and re-flags them. Stale notebook outputs are the most common source of false contradictions.
- **Fork to a new project.** At any Step 3 point, ask the theory session for a *results export*: THEORY.md filtered to FINAL results plus the interfaces another project would consume, saved as `research/export_<project>_vN.md`. The new project treats it as given input; corrections flow back here, never the other way.
- **Long theory chat.** When the desktop chat gets long, do a final Step 3, then start a new chat with the folder connected and THEORY.md as its entry point. The old chat remains available for reference.

## 6. Bootstrap mid-project

If the repo already has code and results when this protocol is adopted:

1. **Theory session** writes `THEORY.md` v1 from the research chat, self-contained, including experiments that would validate results already believed FINAL.
2. **Experiment session** backfills `FINDINGS.md` from git log, notebooks (with outputs), scripts, and result files — one entry per identifiable experiment, flagged UNVERIFIED where not reproduced — and adds a "Gaps" section: theory results with no experiment, and experiments testing nothing in the theory.
3. **Theory session** reconciles: resolves Gaps into "What to test next" or marks them out of scope; produces THEORY.md v2.
4. Add the `CLAUDE.md` block below. Commit everything.

## 7. `CLAUDE.md` block (experiment session)

```
## Research protocol
Read research/WORKFLOW.md and research/THEORY.md before any experiment.
THEORY.md is the authoritative statement of the problem and current results.
After every experiment that produces a result, append an entry to
research/FINDINGS.md using the template there, including the commit hash.
Never edit THEORY.md. If a theoretical result appears wrong, log it in
FINDINGS.md as CONTRADICTS with evidence. Do not pursue SUGGESTS-NEW-PATH
items; log them and continue with the planned items.
```

## 8. Conventions

- Commit after every file change by either session; commit message prefix `theory:` or `findings:`.
- Dates in ISO format; times in the human's local timezone.
- Notation in FINDINGS.md follows THEORY.md §1 exactly. If a symbol is missing, the experiment session says so in the entry rather than inventing one.
- Plots and tables referenced in FINDINGS.md live under `research/artifacts/<date>-<title>/`.
