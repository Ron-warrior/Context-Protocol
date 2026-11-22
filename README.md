# Context Protocol

How an agent should spend tokens inside a codebase — plus the evidence behind each
rule (FINDINGS.md), the long form (PROTOCOL.md), and the loop that upgrades it
(TRACE.md records what each version measured and got wrong).

This is the root README on purpose. In FreeMilk the root README is the only file
loaded into every chat of a project, so it is the one place a rule can live and
actually take effect on behaviour. Everything else is loaded on demand — which is
also this protocol's first principle.

Version: 1.1.0 — supersedes 1.0.0 (TRACE.md says what it got wrong)

---

## The metric

**Effectiveness = P(correct answer) per token spent.**

Not recall. Not graph size. Not "we indexed the repo". Attention is O(n²) over
context tokens and degrades with length, so every token pays twice: once to be
read, once to dilute everything else. The goal is the smallest set of high-signal
tokens that decides the next action — not the largest set you can afford.

## The ladder

Climb one rung at a time. Never start below the rung you can justify.

0. **Frame.** Before touching files, write one line saying what would count as the
   answer. If you cannot, you are about to read files to feel productive.

1. **Map, don't read.** Locate candidates with cheap whole-corpus operations
   (`search_files` with `output_mode: files_with_matches`, `list_files` globs).
   One line per file, not one screen per file.

2. **Rank.** Order by signal, not tree order: definition hit > usage hit; near the
   file you are editing > far; small > large; hand-written > generated > vendored.
   Never enter `node_modules`, `dist`, `build`, `Pods`, `vendor`, lockfiles.

3. **Outline.** Read declarations only (signature lines, `offset`/`limit` windows,
   or `context_lines: 0` around a definition regex) to build a local repo map of
   the subsystem before reading any body.

4. **Scope.** Read one function body at a time. A 40-line window that contains the
   answer beats a 900-line file that contains it too.

5. **Verify.** Two checks, in this order:

   (a) **read-back:** before you claim anything works, the **last operation you
   performed on that region** must be a read — not a read from ten minutes ago.
   Editing after reading is exactly how a file ships unverified.

   (b) **caller sweep:** `search_files` every caller of every symbol whose
   signature, name or behaviour changed. An unverified edit is a claim, not a
   change.

6. **Persist.** Write what you learned into this project (findings, decisions,
   gotchas) so the next session does not pay for it again. A fact that lives only
   in a finished chat gets re-derived at full price.

## Hard rules

- **Never read blind.** No whole-file read before a map step has told you why that
  file and not another.
- **Never whole-file when a window will do.** Read the smallest span that can
  contain the answer, then widen only if it did not.
- **Never trust a symbol you have not seen defined.** Find the definition with
  `search_files`, not with intuition about where it probably lives.
- **Never change a signature without grepping its callers.** All of them.
- **State what you did not verify.** "Could not run it" is a valid, required
  sentence — in this app nothing executes locally, so it is often the honest one.
- **No generated output, ever.** Edit the source that produces it.

## Stop rules

- **Budget cap.** ~4,000 tokens of retrieval per question as a soft ceiling. Past
  it, the problem is the question or the strategy, not the file count.
- **Two strikes.** Two reads that did not answer the question means the strategy
  is wrong. Change rung (usually: search for the *definition*, not the *usage*),
  do not read a third file hopefully.
- **Ambiguity is an answer.** If a name resolves to three candidates, say so and
  pick with a stated reason. Do not silently choose.

## The loop

Two speeds, both real:

- **Fast, within a chat.** A rule that fails here is rewritten here and governs the
  next action in the same conversation. The failure is the evidence.
- **Slow, across chats.** This file is preloaded into every chat of this project,
  so a promoted rule reaches work it was not derived from.
- **Rules.** Every version reads back what it wrote before claiming it works; a
  version bumps only when TRACE.md holds the trace that justifies it; a reverted
  change stays in SCOREBOARD.md with the number that killed it.

## Where things live

| File | What it is | Load it when |
| --- | --- | --- |
| `FINDINGS.md` | Why these rules, ranked against the alternatives, with numbers | Deciding whether to add a tool |
| `TRACE.md` | Countable units, and the measured trace behind each version bump | Bumping a version |
| `SCOREBOARD.md` | Measured results per version, and the promotion rule | Before changing this file |
| `PROTOCOL.md` | Long form: per-situation playbook, budgets, memory schema | Unfamiliar task shape |
| `eval/retrieval_bench.py` | Harness: recall per 1k tokens for four selection policies | After changing this file |

## Changing this file

A rule earns a place only if it fixes a failure that actually occurred, is written
as a check the agent can run mid-task, and shows no regression on the bench.
Otherwise it is a preference, and preferences are how instruction files rot into
600-line blobs the model ignores.
