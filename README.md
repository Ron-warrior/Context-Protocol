# Context Protocol

How an agent should spend tokens inside a codebase: the rules, the evidence behind
them (FINDINGS.md), the long form (PROTOCOL.md), and the loop that upgrades them
(TRACE.md records what each version measured and got wrong).

This is the root README on purpose. It is the only file loaded into every chat of
this project, so it is the only place a rule can live and actually take effect.
Everything else is loaded on demand — which is also rung 1.

Version: 2.15.0 — the objective is ordered: intelligence, then tokens, then speed

---

## Use it

**In a chat.** Paste this repository's URL. The agent reads [`SKILL.md`](SKILL.md) and
has the whole procedure — no install, no key, no build step. It works because the
ladder is a sequence of instructions, not an index: an agent with only grep and
read still gets the benefit.

**On a machine.**

```bash
pipx install git+https://github.com/Ron-warrior/Context-Protocol
ctx query . "how are errors handled"
```

No dependencies. Standard library only.

```bash
ctx ask "how are errors handled"     # path defaults to .
ctx query . "auth refresh" --explain # show why each file ranked
ctx path User Store                  # files mentioning both, with line numbers
ctx map .                            # file map with line sizes
ctx bench . --queries 25             # recall, then tokens, then ms
ctx plan                             # the ladder as a checklist
ctx selftest                         # fixtures; exit 0 means it works
```

Per-project defaults live in `.ctxrc` (`budget=6000`, `expand=off`); `.gitignore`
is honoured.

## Objective

Ordered, and the order is the point:

1. **Intelligence.** The answer must be in the context. A cheap answer that is
   wrong loses to an expensive one that is right.
2. **Token efficiency.** Spend the fewest tokens *subject to* (1).
3. **Speed.** Only once both of the above hold.

This is why `ctx query` emits the **enclosing function** of every match *before*
any signature map, and why `ctx bench` ranks by recall first and tokens second. A
metric that divides by tokens alone rewards answering nothing, cheaply — which is
exactly what a compression benchmark does.

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
   or `context_lines: 0` around a definition regex) to map the subsystem before
   reading any body.
4. **Scope.** Read one function body at a time. A 40-line window containing the
   answer beats a 900-line file containing it too.
5. **Write.** Author in units small enough to check: one function or one section,
   not one 400-line file. Past ~120 lines in a single write you will not re-read
   it, and what you did not re-read is where the defects are. Check before you
   extend.
6. **Verify.** Three checks, in this order:

   (a) **Read back.** Before you claim anything works, the **last operation you
   performed on that region** must be a read. For an edited file that read is
   usually `git_diff`, not the whole file: the delta is what changed and costs a
   fraction of the tokens. Read whole regions only when you created or reshaped
   them.

   (b) **Caller sweep.** `search_files` every caller of every symbol whose
   signature, name or behaviour changed. An unverified edit is a claim, not a
   change.

   (c) **Run it.** If the project runs, run it. Reading a line does not execute
   it — a `NameError` survived inside a region I had read. Coverage is not a test.

7. **Persist.** Write what you learned into the project so the next session does
   not pay for it again. A fact that lives only in a finished chat gets re-derived.

## Hard rules

- **Never read blind.** No whole-file read before a map step has told you why that
  file and not another.
- **Never whole-file when a window will do.** Read the smallest span that can
  contain the answer, then widen only if it did not.
- **Never trust a symbol you have not seen defined.** Find it with `search_files`,
  not with intuition about where it probably lives.
- **Never change a signature without grepping its callers.** All of them.
- **State what you did not verify.** "Could not run it" is a valid, required
  sentence — in this app nothing executes locally, so it is often the honest one.
- **No generated output, ever.** Edit the source that produces it.

## Stop rules

- **Budget cap.** ~4,000 tokens of retrieval per question as a soft ceiling. Past
  it, the problem is the question or the strategy, not the file count.
- **Two strikes.** Two reads that did not answer the question means the strategy is
  wrong. Change rung (usually: search for the *definition*, not the *usage*), do
  not read a third file hopefully.
- **Ambiguity is an answer.** If a name resolves to three candidates, say so and
  pick with a stated reason. Do not silently choose.

## The loop

- **Fast, within a chat.** A rule that fails here is rewritten here and governs the
  next action in the same conversation. The failure is the evidence.
- **Slow, across chats.** This file is preloaded into every chat, so a promoted
  rule reaches work it was not derived from.
- **Rules.** A version bumps only when a trace justifies it; a rule joins this file
  only under the promotion rule in PROTOCOL.md.

## Where things live

| File | What it is | Load it when |
| --- | --- | --- |
| `SKILL.md` | The agent-facing entry point: three modes, one of which needs no install at all | Pasting this URL into an agent |
| `ctx.py` | The CLI: map, query, ask, path, bench, plan, selftest. Stdlib only | Running it |
| `FINDINGS.md` | Why these rules, ranked against the alternatives, with numbers | Adding a tool |
| `TRACE.md` | Countable units and the measured trace behind each version | Bumping a version |
| `SCOREBOARD.md` | Measured results per version, and the promotion rule | Changing this file |
| `PROTOCOL.md` | Long form: per-situation playbook, budgets, memory schema | Unfamiliar task |
| `eval/retrieval_bench.py` | Research harness: recall per 1k, stop rules, ablation, self-test | Changing the method |
| `eval/compare_graphify.py` | Scores graphify's own query output on the same metric | Comparing against it |
