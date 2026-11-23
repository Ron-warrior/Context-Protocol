---
name: context-protocol
description: Use when reading a codebase, answering "how does X work", tracing a bug, or choosing what files to put in context. Ranks files for the question, maps signatures, then reads scoped windows under a token budget - and measures itself on answers per token rather than tokens alone.
---

# Context Protocol

A retrieval procedure for agents working in a codebase. Three ways to use it,
in decreasing order of setup:

1. **No install at all** — follow the ladder below with the tools you already have.
2. **CLI** — `pipx install git+https://github.com/Ron-warrior/Context-Protocol`
3. **Bench** — measure any policy on recall per 1k tokens before trusting it.

## Objective, in order

1. **Intelligence** — the answer must be in the context.
2. **Token efficiency** — fewest tokens *subject to* (1).
3. **Speed** — only once both hold.

Never trade (1) for (2). A short context that omits the answer is not efficient.
When in doubt, read the enclosing function, not a window around the match.

## Why this exists

Indexes answer "what is in this corpus". They do not answer "what should go in
front of the model for *this* question, under *this* budget". graphify's default
benchmark (`graphify/benchmark.py:77`) estimates the corpus as
`number_of_nodes() * 50` and divides by the size of its own query output, so both
sides of its ratio come from the same artifact, and nothing checks whether the
returned text contains the answer.

This protocol measures the thing that decides correctness: **is the needed fact
in the context, per token spent.**

## Mode 1 — no install (works in any agent)

Climb one rung at a time. Do not skip to a lower rung you cannot justify.

0. **Frame.** One line: what would count as the answer. If you cannot write it, you
   are about to read files to feel productive.
1. **Map.** `grep -rl` / glob the question's keywords. Files, not contents.
2. **Rank.** Definition hit > usage hit. Near what you are editing > far. Small >
   large. Never enter `node_modules`, `dist`, `build`, `vendor`, `.git`.
3. **Outline.** Read declarations only (`grep -nE '^\s*(class|def|function|func|fn|interface|struct|impl|type)\s'`).
   Build a local map before reading a body.
4. **Scope.** Read the enclosing function of the best hit, not a ±40 window. A block
   that will not fit the budget is narrowed, never dropped — so widen only after a
   narrow read missed.
5. **Write.** One function or one section per write, not one 400-line file. Past ~120
   lines in a single write you will not re-read it, and the defects live exactly
   where you did not re-read.
6. **Verify.** Read back the last operation on that region — for an edit that is
   usually the diff, not the whole file; grep every caller of a changed symbol; and
   if the project runs, run it.
7. **Persist.** Write what you learned into the repo, not just the chat.

Stop: ~4k tokens of retrieval per question. Two misses means the strategy is
wrong — search for the *definition*, not the *usage* — not that you need a fourth
file.

## Mode 2 — the CLI

```bash
ctx ask "how are errors handled"     # path defaults to cwd
ctx query . "auth refresh" --explain # score and path for the top five files
ctx query . "auth refresh" --budget 1500 --lean   # token-first baseline
ctx path User Store                  # files mentioning both, with line numbers
ctx map .                            # file map with line counts
ctx bench . --queries 25             # recall, then tokens, then ms
ctx bench . --queries 100 --floor .75 # exit 1 rather than pass silently
ctx next . --queries 100             # the misses, resolved to file:line
ctx plan                             # the ladder as a checklist, no install needed
ctx selftest                         # fixtures; exit 0 means it works
```

`ctx query` emits, in this order: up to four enclosing blocks of the best-ranked
file and three each for the next two, then every other ranked match until 85% of
the budget is spent, then a signature map of every ranked file, then one hop of
imports, then call sites of what it found. Blocks before maps, because an outline
tells you a name exists while a body answers the question. A block that does not
fit the remaining room is narrowed to a smaller window around the same hit rather
than dropped, so the last few hundred tokens still buy coverage instead of nothing.
A line longer than 240 characters is shortened **around the word you asked about**,
not at its start — the head of a long paragraph is the wrong end to keep.
Cost is measured on the text actually emitted, labels and header included, so the
`~N tokens` figure is the size of what you received. `--phases body,call` runs a
subset of the phases, which is how a change is attributed to one of them. It never
reads a file it has no reason to read, and `.gitignore` plus `.ctxrc` (`budget=`,
`expand=off`) are honoured.

## Mode 3 — measure before you trust

```bash
python3 eval/retrieval_bench.py <repo> --auto 25 --sweep 1000,4000,16000
python3 eval/retrieval_bench.py <repo> --auto 25 --ablate
python3 eval/compare_graphify.py <repo> <graph.json>     # head-to-head
```

Recall per 1k tokens, at several budgets, with each ranking claim switchable off
so it can lose. Current numbers on a 795-file corpus and the failures behind them
are in `TRACE.md` and `SCOREBOARD.md`.

## Mode 4 — prove it (read this first if you skip steps)

A weaker model does not fail because it knows less. It fails by skipping a step
and then describing the skip as a result. This protocol was built by a model that
did exactly that, in the session that wrote this section:

| Failure | What it looked like here | The check that catches it |
| --- | --- | --- |
| Miscounting its own output | "5 + 2 + 2" for a list that was 5, 2 and 3 | Recount from the printed list, never from memory |
| Quoting a number before measuring | A recall figure from an older run, presented as this one's | Every number needs its command and output beside it |
| Asserting a bug that was not there | "this compares characters to tokens", without quoting the line | Quote the line and its units before calling it a bug |
| Shipping a check that never fired | An interval printed identically for 0.94 and 1.00 | Prove the check moves when the input moves |

Five rules, in order. Each has an artifact, so "did I do it" is a file, not a
feeling.

1. **Write the question as one line, before searching.** If you cannot say what
   the answer would look like, you are about to read files to feel productive.
2. **One search, then one read.** `grep -rl` for the keywords, pick the definition
   over the usage, then read the enclosing block of the best hit. A second search
   is allowed only after the first read missed, and you must say what it missed.
3. **Every claim carries its evidence on the same line.** Not "tests pass" but
   the command and its exit code. Not "recall improved" but the two tables. If
   you cannot paste it, do not write it.
4. **Submit what you read, not what you concluded.** A conclusion is not
   checkable; a range is.
5. **Score it, and compare against the tool.**

```bash
python3 eval/score.py --submission mine.json --baseline
```

A submission is the ranges you actually put in front of yourself:

```json
{"ranges": [{"path": "service/auth.py", "start": 1, "end": 20}]}
```

Lines are 1-based and inclusive. The scorer checks the hand-written answers in
`eval/tasks.json` against your text and reports recall, tokens and recall per
1k, then does the same for `ctx` itself so the comparison is not a feeling.

**Do not tune to the tasks.** Ten questions over six files is a smoke test for
method, not a benchmark of a corpus. If you find yourself reading `tasks.json`
before `service/auth.py`, you have inverted the exercise.

## Rules that are not negotiable

- An unverified edit is a claim, not a change.
- If the project runs, run it. Reading a line does not execute it.
- State what you did not verify. "Could not run it" is a valid sentence.
- Never answer "can I use X" from a README — read its integration doc.
