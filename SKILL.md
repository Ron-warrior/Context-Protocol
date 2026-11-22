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
4. **Scope.** Read ±40 lines around the best hit. Widen only if it missed.
5. **Verify.** Re-read the edited region; grep every caller of a changed symbol.
6. **Persist.** Write what you learned into the repo, not just the chat.

Stop: ~4k tokens of retrieval per question. Two misses means the strategy is
wrong — search for the *definition*, not the *usage* — not that you need a fourth
file.

## Mode 2 — the CLI

```bash
ctx map .                                  # file map with line counts
ctx query . "how are errors handled"       # the ladder, ranked and budgeted
ctx query . "auth refresh" --budget 1500 --json
ctx bench . --queries 25                   # read_all vs grep vs ladder
ctx selftest                               # fixtures; exit 0 means it works
```

`ctx query` prints three things: a signature map of the ranked files, scoped
windows around the matched lines, and a one-line footer with chunks/tokens/files
scanned. It never reads a file it has no reason to read.

## Mode 3 — measure before you trust

```bash
python3 eval/retrieval_bench.py <repo> --auto 25 --sweep 1000,4000,16000
python3 eval/retrieval_bench.py <repo> --auto 25 --ablate
python3 eval/compare_graphify.py <repo> <graph.json>     # head-to-head
```

Recall per 1k tokens, at several budgets, with each ranking claim switchable off
so it can lose. Current numbers on a 795-file corpus and the failures behind them
are in `TRACE.md` and `SCOREBOARD.md`.

## Rules that are not negotiable

- An unverified edit is a claim, not a change.
- If the project runs, run it. Reading a line does not execute it.
- State what you did not verify. "Could not run it" is a valid sentence.
- Never answer "can I use X" from a README — read its integration doc.
