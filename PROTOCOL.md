# Protocol — the long form

README.md is the version that is always loaded and must stay under ~100 lines.
This is the same protocol with the decision table, the budgets, the memory schema
and the anti-patterns.

## Decision table

| Situation | Do this | Budget | Stop when |
| --- | --- | --- | --- |
| Unfamiliar repo, "how does X work" | Glob the tree → outline the 3–5 highest-ranked files → read one full file max | 4–6k | You can name the entry point, the data shape and the one surprising coupling |
| Bug report, "it shows the wrong value" | grep the user-visible string → trace the producer of that value backwards → read only the producer | 3–4k | You can point at the line that computes it and say why it is wrong |
| Add a feature | Find the closest existing instance of the same shape → read it whole → copy its seams | 4k | You know every registration point the new code must touch |
| Rename / signature change | `search_files` the symbol project-wide *before* editing → group callers by file → edit all, then re-grep to confirm zero stale hits | 2k | Zero remaining references to the old name |
| Cross-repo | Map each repo separately; never hold two trees in context at once; pass findings as a short written note, not as recalled detail | 2k per repo | The interface between them is described in ≤5 lines |
| Library / API question | Docs first (or a docs MCP), source only to resolve a contradiction | 1–2k | The call signature and the one gotcha are known |
| "Where is this string/number from" | grep the literal; if it appears once, that is the answer; if 40 times, grep a narrower sibling token | 1k | One authoritative definition, not many usages |

## Budget arithmetic

- Rough cost of a token: 4 characters. A 900-line source file is ~9k tokens.
- A 40-line window is ~400 tokens. You can afford ~10 windows for the price of one
  file, and they will usually beat it, because they are *chosen*.
- Soft ceiling per question: **4,000 tokens of retrieval**. A third of a context
  window buys you the answer to most questions if the ranking is honest.
- Outlines are the cheapest useful unit: one line per declaration, ~10–15 tokens,
  and they tell you which file is worth a window.

## Write side

Retrieval is the cheap half. The v1.0.0 trace spent 824 lines authoring against 202
lines of read-back and shipped three defects in the part nobody read, so the rules
govern writes too:

- **One unit per write.** A function, a section, a table — not a 400-line file.
  Past ~120 lines in a single write, defects stop being findable: you will not
  re-read it, and asking a reviewer to is another 4k tokens.
- **Check before extending.** Before the next write to the same file, verify the
  last one. The check is cheaper than the defect it catches.
- **Read the diff, not the file.** For an edit to an existing file, `git_diff`
  shows exactly what changed at a fraction of the tokens of re-reading the file.
  For a new file, or one whose shape changed, read the region itself — a diff
  against nothing shows you everything as added and tells you nothing about order.
- **Arithmetic.** 120 lines is ~1.2k tokens to write and ~1.2k to read back, so
  verifying a unit costs about what writing it did. Skipping the check saves half
  the cost and returns defects at the rate measured in TRACE.md: three in the 441
  lines of the first bench, all in the 239 lines never read.

The asymmetry that makes this a rung rather than a preference: a retrieval mistake
costs tokens and is caught by the next question; a write mistake ships, and the
cheapest time to find it is before the file is closed.

## Memory schema

Persist in the project, not in the chat. Four files, four jobs:

- `README.md` — rules that must apply before any work starts. Short, imperative,
  versioned. Grows only by the promotion rule.
- `FINDINGS.md` — durable knowledge: what this codebase does, what was tried, what
  was rejected and why. Append-only in spirit; it is the thing that stops session
  N+1 from re-deriving session N.
- `SCOREBOARD.md` — measurements and the upgrade log. If a change is not on the
  scoreboard it did not happen.

- `TRACE.md` — the countable trace behind each version bump: calls, lines
  authored, lines read back, coverage, and which rules the trace shows broken.
  A version without a trace entry is a preference, not an upgrade.

What belongs in memory: decisions with reasons, invariants ("all writes go through
`Store.apply`"), gotchas ("the ID is a string here but an int in Postgres"),
commands that work. What does not: narrating what you just did, restating file
contents, or anything derivable in one cheap grep.

## Anti-patterns

- **Reading to feel productive.** If the frame line is missing, you are reading to
  avoid deciding.
- **Whole-file reads "for context".** Context is the thing you are trying to
  conserve.
- **Traversing a graph you did not rank.** A community graph is a map of the
  corpus, not of your question.
- **Trusting an inferred edge.** `INFERRED` means a resolver guessed. Verify by
  reading the definition, or mark the claim as unverified.
- **Editing by string replace.** It wins until two identical strings exist.
- **Silent ambiguity.** Three candidates for one name is information: report it.
- **Instruction bloat.** Every rule added dilutes the others. 100 lines of checkable
  rules beat 600 lines of aspirational ones.

## Worked micro-example

> "Why does the settings screen show a stale avatar?"

Bad: read `Settings.swift`, then `AvatarView.swift`, then `ProfileStore.swift`,
then the whole networking layer. ~25k tokens, no answer, context now polluted.

Protocol: grep `avatar` → 6 files; rank by definition-hit → `ProfileStore` (declares
`avatarURL`) first; outline it (12 declarations, 150 tokens); window ±10 lines
around `avatarURL` (250 tokens); see it is cached and never invalidated on
`profileUpdated`; grep `profileUpdated` → 3 callers, one of which forgets to
refresh. ~900 tokens, answer found, and the fix has its caller list already.

## Promotion rule

A rule moves into README.md only if all three hold:

1. It fixes a failure that actually occurred, described in one line.
2. It is checkable — an agent can tell, mid-task, whether it is following it.
3. It does not regress `eval/retrieval_bench.py` on a real repository.

Otherwise it stays here, or in FINDINGS.md as an observation, or nowhere.

## Closing a version

A version is closed when, and only when, all four are true:

1. **Read-back done.** The last operation on every region you edited was a read in
   this turn, after the edit — a `git_diff` of the file counts, and costs a
   fraction of re-reading it. Not "I looked at it earlier".
2. **Caller sweep done.** Every symbol whose signature, name or behaviour changed
   has had its callers grepped since the change.
3. **Trace written.** TRACE.md has a row: calls, authored, read-back, coverage, and
   any rule the trace shows you breaking.
4. **Scoreboard row written.** SCOREBOARD.md says what changed, the evidence, and
   whether it was kept.

Skip any of the four and the version is a draft, however finished it looks. This
matters more for code than prose: prose that is wrong costs a reader a minute,
code that is wrong costs a benchmark its validity.
