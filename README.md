# Context Protocol

How an agent should spend tokens inside a codebase: rank the files for the
question, read the block that answers it, and measure whether the answer arrived.
Evidence in FINDINGS.md, the trace in TRACE.md, the numbers in SCOREBOARD.md.

Version: 3.0.0 — intelligence first, then tokens, then speed

---

## Use it

**In a chat.** Paste this repository's URL. The agent reads [`SKILL.md`](SKILL.md):
three modes, none needing an install.

**On a machine.**

```bash
pipx install git+https://github.com/Ron-warrior/Context-Protocol
ctx query . "how are errors handled"
```

Standard library only, no dependencies.

```bash
ctx ask "how are errors handled"       # path defaults to .
ctx query . "auth refresh" --explain   # why each file ranked
ctx path User Store                    # files mentioning both
ctx map .                              # file map with line counts
ctx bench . --queries 100              # recall, then tokens, then ms
ctx bench . --sweep 1000,2000,4000     # recall per budget, and the knee
ctx bench . --ablate                   # what each phase costs
ctx bench . --queries eval/tasks.json  # question-shaped, not only lookups
ctx next . --queries 100               # the misses, resolved to file:line
ctx plan                               # the ladder as a checklist
ctx selftest                           # fixtures; exit 0 means it works
```

`.ctxrc` holds per-project defaults (`budget=`, `expand=off`); `.gitignore` is honoured.

## Objective

1. **Intelligence** — the answer must be in the context.
2. **Token efficiency** — fewest tokens *subject to* (1).
3. **Speed** — only once both hold.

A metric that divides by tokens alone rewards answering nothing, cheaply.

## The ladder

One rung at a time; never start below the rung you can justify.

0. **Frame.** One line: what would count as the answer.
1. **Map.** Cheap whole-corpus searches. Files, not contents.
2. **Rank.** Definition hit > usage hit; near > far; small > large. Never enter `node_modules`, `dist`, `build`, `Pods`, `vendor`, lockfiles.
3. **Outline.** Declarations only, before reading a body.
4. **Scope.** One function body at a time. A 40-line window holding the answer beats a 900-line file that also holds it.
5. **Write.** One function or section per write. Past ~120 lines you will not re-read it, and that is where the defects are.
6. **Verify.** (a) Read back — the last operation on the region you edited must be a read, usually the diff, not the whole file. (b) Sweep every caller of every symbol you changed. (c) Run it — reading a line does not execute it.
7. **Persist.** Write what you learned into the repo, not just the chat.

## Hard rules

- **Never read blind** — no whole-file read before a map step says why that file.
- **Never whole-file when a window will do** — widen only after a narrow read missed.
- **Never trust a symbol you have not seen defined** — find it, do not assume.
- **Never change a signature without grepping its callers.** All of them.
- **State what you did not verify.** "Could not run it" is a required sentence.
- **Every number carries its command.** Quote the command and its output, or say you have not measured it. Recount from the printed list, never from memory.
- **No generated output** — edit the source that produces it.

## Stop rules

- **Budget cap.** ~1,000 tokens of retrieval per question — the measured knee on two corpora; past it the problem is the question or the strategy, not the file count.
- **Two strikes.** Two reads that missed mean change rung, not read a third file.
- **Ambiguity is an answer.** Say a name resolves to three candidates, and why you picked one.

## The loop

- **Within a chat.** A rule that fails here is rewritten here and governs the next action; the failure is the evidence.
- **Each version builds the next.** `ctx next` turns this version's misses into named files and lines.
- **Across chats.** This file is preloaded into every chat, so a promoted rule reaches work it was not derived from.
- **A version bumps only when a trace justifies it**, under the promotion rule in PROTOCOL.md.

## Where things live

| File | What it is | Load it when |
| --- | --- | --- |
| `SKILL.md` | Agent entry point: three modes, one needing no install | Pasting this URL |
| `ctx.py` | The CLI: map, query, ask, path, bench, next, plan, selftest | Running it |
| `FINDINGS.md` | Why these rules, ranked against the alternatives | Adding a tool |
| `TRACE.md` | What each version measured and got wrong | Bumping a version |
| `SCOREBOARD.md` | Measured results per version, and the promotion rule | Changing this file |
| `PROTOCOL.md` | Long form: playbooks, budgets, memory schema | Unfamiliar task |
| `CHANGELOG.md` | The map: three eras, one paragraph each | Orientating |
| `eval/tasks.json` | Ten questions over a fixture corpus, with answers | Measuring questions |
| `eval/score.py` | Scores the ranges a model actually read | Checking a model |
| `eval/compare_graphify.py` | graphify's output on the same metric | Comparing against it |
