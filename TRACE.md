# Trace — the loop's instrumentation

A self-improving loop is only real if the thing it measures is countable from the
transcript. So nothing here is self-reported feeling. Every unit below can be
audited by replaying the tool calls.

## What is counted

| Unit | Definition | Audited from |
| --- | --- | --- |
| calls | tool invocations used to finish the task | the transcript |
| authored | lines written by the agent | `create_file` / `modify_file` arguments |
| read-back | lines of an authored region read *after* writing it | `read_file` `offset`/`limit` |
| coverage | read-back ÷ authored, for code | division |
| last-op | was the final operation on a touched region a **read**? | the last tool call touching it |
| strikes | reads that did not advance the question | the trace, judged |
| violations | rules in README.md that the trace shows broken | trace vs README |

**Not counted:** "intelligence", "quality", "how good the writing is". There is no
instrument for those here, so this file makes no claim about them. It measures
effectiveness per token, verification coverage, and calls per resolved task.

## Two speeds

- **Fast loop — inside one chat.** A rule that fails is rewritten immediately and
  governs the next action in the same conversation. Cheap, because the failure is
  still in context.
- **Slow loop — across chats.** README.md is preloaded into every chat of this
  project, so a promoted rule reaches work it was never derived from. This is the
  only mechanism by which a correction outlives the conversation that produced it.

Cross-session self-improvement is therefore real but narrow: it propagates *rules*,
not experience. The trace is what carries the evidence between them.

## Trace: v1.0.0 — the version that produced v1.1.0

Task: research the state of the art and write the protocol, docs and bench.

| Unit | Measured |
| --- | --- |
| calls | 15 |
| authored | 824 lines (441 code, 383 docs) |
| read-back — code | 202 / 441 |
| **coverage — code** | **46%** |
| read-back — docs | 0 / 383 |
| **last-op on the code file** | **write** (a hoisting edit made after the final read) |
| violations | 1 |

**The violation.** README v1.0.0 rung 5 said: *"After any edit: re-read the edited
region."* Time-ordered, and therefore satisfiable by accident. In practice I read
two windows of the bench, then edited it, and never re-read the edited region — so
the last operation on the file was a write. 239 lines were never read at all
before or after being written.

That is the whole justification for v1.1.0: the rule was **not checkable** in the
state it was written in, so it was followed by coincidence and broken silently.

## Trace: v1.1.0 — the version fixing it

The same turn that wrote v1.1.0 applied it: read the unread 239 lines *before*
claiming anything, then re-read each edited region *after* editing.

Result: three defects in the v1.0.0 bench, found in one pass, all in code I had
shipped at 46% coverage.

| Defect | Kind | Cost if shipped |
| --- | --- | --- |
| `break` instead of `continue` in the ladder's heading loop | logic | One large outline starves every smaller one → the policy under test scores worse than it should |
| Unused `by_path` set | dead code | Nothing, but it is a tell that the region was never read |
| No shape check on `--queries` JSON | robustness | A JSON object instead of an array crashes with a `TypeError` |

Read-back cost: ~11k tokens to read 239 lines plus three edited regions.

Read-back return: three defects, one of which would have silently biased the
benchmark that is supposed to justify the protocol.

**That exchange rate is the argument for the rule.** Reviewing code you just
wrote is not diligence theatre; at 46% coverage it was the difference between a
harness that measures something and one that measures a bug.


## Trace: v1.2.0–v1.5.0 — four versions in one turn

Task: build the next version of this protocol *using* the current one, then use
each new version while building the next. The question this trace answers: does
the loop actually run, or does it only describe itself?

### Countable units

| Unit | v1.2.0–1.5.0 |
| --- | --- |
| calls | ~40 (counted to the closing check) |
| authored | ~413 lines (99 README, 29 PROTOCOL, ~285 bench) |
| read-back | ~540 lines, including a 272-line `git_diff` of the bench |
| edited code regions verified on the first pass | 2 of 3 |
| regions unverified until the closing check | 1 (`load_corpus`) |
| defects found by read-back of this turn's own diff | 3 |
| anything executed | **none** |

### What each version was justified by

- **1.2.0 — the write side.** Two countable facts, no theory. README v1.1.0 was
  111 lines against its own "~100" rule stated in PROTOCOL.md line 3; and the
  v1.0.0 trace showed 3 defects in the 239 authored lines nobody read. So the rung
  was added *and paid for* by tightening the file to 99 lines rather than growing
  it. Applied to itself the same turn: the 285-line bench change went in as 15
  anchored edits of 1–108 lines, never as one overwrite of a 449-line file.
- **1.3.0 — stop rules become measurable.** SCOREBOARD's hypothesis "stopping
  bounds the misses; ranking only improves the hit rate" had no instrument, so it
  was unfalsifiable. `--stop` is that instrument: same ranking, four stopping
  rules, answer rate against tokens spent.
- **1.4.0 — three defects in the bench itself**, found by reading it against rung
  6. (i) `assemble` and `chunks_ladder` budgeted by different numbers, so a chunk
  the policy counted as fitting could disappear at assembly — the policy paid for
  a read it never got, biasing every policy that pre-counts. (ii) Files that
  declare nothing — constants modules, config tables, scripts — had no outline, so
  every map-based policy scored zero on them; that is precisely the class of file
  a hard question turns on. (iii) `simulate_stop` re-tokenized every file for every
  query, O(queries × corpus bytes), which on a 5k-file repo would have hung.
- **1.5.0 — `--selftest`.** A harness nobody can run is a claim, and this one has
  never run. Four fixture files encode those three defects as assertions, so the
  first person to run the bench gets a pass/fail on the instrument before any
  number from it means anything.

Defect (iii) is the interesting one: it was introduced by 1.3.0 minutes earlier and
caught by 1.3.0's own read-back, in the same turn, in the same file. That is the
fast loop at its fastest — the version caught its own regression before the next
version was built on top of it.

### The rule that nearly failed

The **closing check**, not the rung, caught that one edited region (`load_corpus`)
had not been read back: I had read the region above it and the region below it and
assumed the middle. Reading is cheap; assuming is the failure the rule exists to
prevent. It is recorded here rather than quietly corrected, because a protocol that
reports only its successful checks cannot be calibrated — and because the catch
tells you which mechanism is load-bearing: read-back is enforced by the checklist,
not by good intentions.

### Still unmeasured

Every number SCOREBOARD.md would report is still a prediction. Nothing executes on
this device, so `--selftest`, the four policies and the four stop rules are correct
by reading, not by running. The next honest step is not a sixth version: it is
`python3 eval/retrieval_bench.py --selftest` on a machine with a Python, and a
first real row in the version log that is not an argument.


## Trace: v1.6.0–v1.8.0 — the bench audited against its own protocol

Task: keep iterating. The first act of this round was a **full read** of the
703-line bench, not windowed reads: the change set touched most of the file, so
windowing would have been the wrong economy (rung 4 is about *which* bytes to read,
and here the answer was all of them).

### What the full read found

- **Rung 2 was not implemented.** `personalize` counted every keyword occurrence
  identically. "Definition hit > usage hit", "near the file you are editing >
  far" and "small > large" appeared in the protocol and were absent from the
  harness. A ranking rule the bench cannot distinguish cannot be validated by it.
  This is the most serious finding of the round, and it was in the code since 1.0.0.
- **Substring matching inflated every policy.** `refresh_token` counted as found
  inside `refresh_token_legacy`. The inflation applied to all policies equally, so
  it did not bias the *ranking* between them, but it did inflate recall and the
  stop-rule answer rate in absolute terms, which is what SCOREBOARD quotes.
- **A single budget can mislead.** The ladder wins or loses depending on where the
  cap sits; the protocol's own 4k cap is one point, so a sweep is the only honest
  test of whether a ranking choice survives.

### Defects this round introduced, and caught

- A stray closing parenthesis in a self-test assertion, caught by read-back before
  it could run: it would have been a `SyntaxError` on the first `--selftest`.
- `run_stop` unpacking a 2-tuple from the 3-tuple `prepare` now returns — a crash
  in `--stop`, the mode the stop-rule hypothesis depends on. Introduced by my own
  `prepare` refactor in the same turn, caught by reading the region after
  editing it, not by re-reading the file I had just written.

Both are in the same class as the 1.4.0 defect: the change was correct in the
region I was thinking about and wrong at the seam with the next region. That is the
pattern the closing check exists for, and it caught it twice this round.

### Countable units, this round

| Unit | v1.6.0–1.8.0 |
| --- | --- |
| calls | ~45 |
| authored | ~330 lines (bench only) |
| read-back | the full 703-line file, plus ~400 lines of targeted regions |
| defects found by read-back | 4 (2 pre-existing, 2 introduced this round) |
| anything executed | **none** |

### What is still not established

Every improvement in this round is a change to the *instrument*. None of it is a
measured result. The protocol's claims about which policy wins remain predictions
until someone runs `--sweep` on a real repository. Notably, the rung-2 knobs are
now testable, which means a future row can say the ranking clause *lost* — and that
is the first time the protocol can be wrong about its own ranking rule.


### A miss, recorded as one

After claiming the closing check covered `run_stop`, the diff showed the edit had
deleted the line `found, used = simulate_stop(` and left a bare argument list: a
`SyntaxError` in `--stop`. The region had been read back *before* the diff, and
the read did not catch it because I read the region and then edited a second time
without reading again. The last operation on that region was a write, so rung 6(a)
was violated in exactly the way the 1.1.0 rule was written to prevent.

Fixed, and read back again. The defect count for the round is therefore 5, not 4,
and the lesson is narrower than "read more": **a read is only a check if it is the
last operation on the region.** Any edit after the read reopens the region.


## Trace: execution — the step that caught what reading did not

CI run 45064682765, the first execution of the harness.

| Step | Result |
| --- | --- |
| `py_compile` | passed |
| `--selftest` | passed |
| `--ignore` | passed |
| `--sweep` | passed, produced the first real metrics |
| `--stop` | **crashed** — `NameError: name 'queries' is not defined` |

The defect is instructive. `report_stop` printed `len(queries)` while its
signature took `prepared`. That line had already been **read back** in an earlier
version's verification pass — it sat inside a region I read and signed off.

So the lesson is narrower and worse than "read-back sometimes misses things":

> **Reading a line is not checking a line.** Coverage measures tokens spent, not
> correctness. A compiler is a checker; my eyes are not.

This is the third defect in this project that one execution would have caught
instantly, and the first that survived an explicit read-back. It is the evidence
for rung 6(c): if the project can run, run it.

The cost of the miss was one CI run and one round of fixes. The cost without CI
would have been every user invocation of `--stop`, since the crash was on the
report path rather than in the computation.


## Trace: first real corpus — one claim held, one instrument failed

CI run 45074848996: freellmapi sparse checkout (`server/src`, `shared`, `cli`),
795 files, 25 auto queries, budgets 1k/4k/16k. The first measurement on a
codebase the protocol was not written against.

| Result | Outcome |
| --- | --- |
| sweep | ladder best at every budget: 0.567 / 0.213 / 0.058 recall per 1k |
| pagerank_map at 1k | 0.121 — beats grep (0.000) for the first time, as predicted from edge sparsity on the 7-file repo |
| stop rules | all four identical: 3,042 tokens, 4% answer rate — **instrument failure** |

The stop failure is the finding of the round. `simulate_stop` walked whole
files in rank order; in a 795-file TypeScript repo a single file often costs
more than the entire budget, so the wall ended every walk before a strike rule
could fire and three rules returned byte-identical tokens. The experiment was
measuring read granularity and calling it stopping. This defect was invisible
on the 7-file fixture — the first one only a real corpus could surface.

Bench 1.10.0 rewrites the walk over the ladder's chunks (outlines, then scoped
windows) — what rung 4 actually prescribes. The self-test grew assertions for
both directions: one strike must quit on a missed outline chunk, and
until_found must read on and answer, paying more.

### Countable units, this round

| Unit | this round |
| --- | --- |
| calls | ~14 |
| authored | ~70 lines (bench, scoreboard, trace) |
| read-back | every edited region, plus the CI log that found the defect |
| defects found | 1 — by the corpus, not by reading |
| executed | CI: selftest, real-corpus sweep, stop mode |

### What is still not established

The stop-rule hypothesis still has no valid number: chunk-level `--stop` has
not run yet, and its CI run is the next evidence either way. The ladder's 0.567
at 1k comes from auto-generated rare-identifier queries — real questions have
synonyms and paraphrases, and the protocol has no instrument for that yet.


## Trace: the stop experiment gets a real number, then corrects itself

Two CI runs, one iteration chain: 1.10.0's fix produced the first valid stop
numbers, and the numbers themselves exposed the next instrument defect.

Run 45075205417 (bench 1.10.0, chunk-level walk):

| stop rule | answer rate | tokens | tokens/answer |
| --- | --- | --- | --- |
| until_found | 0.680 | 2,404 | 3,536 |
| three_strike | 0.200 | 1,035 | 5,176 |
| two_strike | 0.160 | 817 | 5,106 |
| one_strike | 0.000 | 524 | inf |

Two findings, one falsification:

1. **The quit-form of the stop-rule hypothesis is falsified.** Strikes do not
   hold answer rate: two_strike trades 52 points of it for two thirds of the
   tokens and loses on answers per 1k (0.197 vs 0.283). Quitting early is
   expensive in answers, not cheap. README's two-strike rule survives because
   it was never the quit rule — it says *change rung* after two misses.
2. **The strike costs exposed a second artifact.** one_strike spent 524 tokens
   and answered 0% — it died during the outline phase, before any window. A
   rule that counts outline reads as strikes is measuring the map, which
   cannot answer a body question, not the stopping.

Bench 1.11.0 re-counts strikes over scoped windows only (rung 4's reads; rung
3's map burns none), with a fifth fixture whose needle lives in a lower-ranked
body so the one-strike path is actually exercised. Prediction recorded in
SCOREBOARD before the run: strike answer rates rise toward until_found's 68%,
and three_strike may then challenge it on answers per 1k.

### Countable units, this round

| Unit | this round |
| --- | --- |
| calls | ~12 |
| authored | ~55 lines (bench, scoreboard, trace) |
| read-back | every edited region; caller sweep over `excerpt` literals |
| defects found | 1 (outline-strike artifact, found by the numbers 1.10.0 produced) |
| executed | CI: selftest, real-corpus sweep, stop mode |

### What is still not established

Whether any strike rule beats until_found per token — the 1.11.0 run decides.
And the ladder's margins are still measured on auto-generated rare-identifier
queries; a synonym-tolerant query generator is the next instrument gap.


## Trace: ablation — the last untested claim gets a losing mode

While the 1.11.0 CI run was pending, the round implemented bench 1.12.0 rather
than polling: `--ablate` runs the ladder with each rung-2 claim disabled —
`definition_weight` off, `length_damping` off, and PageRank itself off, which
is the aider repo-map claim in the crosshairs. The knobs have only ever been
asserted to *change* the ranking (a self-test check since 1.6.0); whether they
*improve* recall was never measured.

Same queries, same budgets, apples to apples. Prediction recorded in SCOREBOARD
before the run: if default ties every ablation on the real corpus, the rung-2
knobs are decoration until shown otherwise — and a losing claim gets demoted,
which is what the promotion rule is for.

### Countable units, this round

| Unit | this round |
| --- | --- |
| calls | ~10 |
| authored | ~75 lines (bench, workflow, scoreboard, trace) |
| read-back | the ablation block, the dispatch, the workflow steps |
| executed | CI pending for 1.11.0 + 1.12.0 (one run covers both) |


## Trace: the last untested constant

Rung 3's outline share — 40% of the budget spent on declarations before any
body is read — was set by judgement in 1.0.0 and never tested. On the real
corpus that is up to 1,600 of the 4,000-token budget, the single largest
unexamined allocation in the protocol. Bench 1.13.0 makes it a swept knob:
`--outline-sweep 0.2,0.4,0.6` re-runs the ladder at each split with the
ranking held fixed, at every budget the sweep already covers. The self-test
pins both ends: share 0 removes the map phase entirely, 0.9 keeps it.

Prediction recorded before the run: if recall per 1k is flat across shares,
the constant is not load-bearing and stays; if another share wins, rung 3 gets
retuned — the first time the ladder's own geometry, not just its ranking, can
lose.

### Countable units, this round

| Unit | this round |
| --- | --- |
| calls | ~9 |
| authored | ~90 lines (bench, workflow, scoreboard, trace) |
| read-back | the sweep block, the dispatch, both workflow jobs |
| executed | CI queued for 1.11.0 + 1.12.0 + 1.13.0 (one run covers all three) |


## Trace: the answer given from one document

Asked whether FreeLLMAPI could be used, I answered "no" — from its README alone.
The challenge forced a docs read, which showed the router ships an MCP server on
`/mcp` (Streamable HTTP + Bearer), off by default.

**The failure:** I answered a capability question from the repository's front page
instead of its integration doc, then generalised "can't run a server here" into
"can't be used". Rung 1 says map before reading; rung 6(c) says check the
interface. I did neither.

**The cost:** one wrong answer, one correction, one round of docs reading.

**The rule:** never answer "can I use X" from a README. Read the integration, MCP
or docs page first, because those describe the interface rather than the intent.

The correction, with the exact attach steps, is in INTEGRATIONS.md.

## Real corpus, second run (795 files)

The job that finally has enough files to mean something, plus the two modes that
disagree with my expectations.

| budget | ladder | pagerank_map | grep_files | read_all |
| --- | --- | --- | --- | --- |
| 1000 | **0.567** | 0.121 | 0.000 | 0.000 |
| 4000 | **0.213** | 0.070 | 0.108 | 0.000 |
| 16000 | **0.058** | 0.023 | 0.040 | 0.003 |

Stop rules, ranking held fixed:

| rule | answer rate | tokens | tokens/answer |
| --- | --- | --- | --- |
| until_found | 0.680 | 2,404 | 3,536 |
| three_strike | 0.640 | 2,124 | 3,318 |
| two_strike | 0.600 | 1,936 | 3,227 |
| **one_strike** | 0.600 | **1,770** | **2,950** |

Ablation, each rung-2 claim disabled at 4k:

| variant | recall/1k |
| --- | --- |
| default | 0.213 |
| definition_weight_off | 0.201 |
| length_damping_off | 0.188 |
| pagerank_off | 0.213 |

Outline share of the budget: 0.2 → 0.207, **0.4 → 0.213**, 0.6 → 0.172.

**What this settles:**

1. **The ladder wins at every budget on a real repo** — not an artifact of a
   seven-file fixture.
2. **One strike is the best stop rule by answer rate per token** (0.600 at 1,770)
   while giving up 8 points of answer rate against until_found. The "quit form" of
   the hypothesis was not falsified; the *coarse* form was.
3. **Pagerank adds nothing here.** `pagerank_off` ties the default exactly at
   0.213 — so the aider claim, in this harness, does not earn its keep. Length
   damping and definition weighting do (0.188 and 0.201 without them).
4. **The 40% outline default is earning its keep**, unlike most constants in this
   project: 0.6 costs 19% of the score.

**And a reporting defect the run exposed:** `max()` over a dict of tied scores
picks one arbitrarily, so an exact 0.213 == 0.213 tie printed "an ablation beats
default — a rung-2 claim is losing". Fixed in 1.14.0 to treat ties as ties. The
error was in the pessimistic direction, which is still an error: a false alarm
that makes the protocol look more self-critical than it is.


## Trace: the objective reordered (protocol 2.0.0)

This one is a **requirement change, not a measured one** — stated plainly because
every other version here was derived from a failure, and pretending otherwise
would corrupt the record.

The old objective was a ratio: `P(correct) / tokens`. A ratio has a degenerate
maximum — answer nothing, spend nothing. That is not a hypothetical: it is what
graphify's benchmark does when it divides by an estimated corpus size and never
checks whether the answer is present.

The objective is now ordered and lexical: **intelligence, then token efficiency,
then speed.** A cheaper answer that is wrong loses to an expensive one that is
right.

What that changed in `ctx`:

| Before | After |
| --- | --- |
| Signature map first (40% of budget), then ±4-line windows | Enclosing block of every match first, then the map |
| Ranking counted raw occurrences | Rank adds symbol-name matches (×4) and two-word co-occurrence (×3) |
| Substring matching | Identifiers split: `refreshToken` matches `refresh token` |
| No cross-file step | One hop of imports from the top two files, outlines only |
| Bench ranked by recall/1k | Bench ranks by recall, then tokens, then ms |

`--lean` keeps the old token-first policy so the trade-off stays measurable rather
than asserted: the next corpus run reports both, and if lean ever matches
intelligence on recall, intelligence-first is paying for nothing and gets cut.


## Trace: ctx 2.1.0 → 2.3.0, twenty iterations

Twenty changes to `ctx`, batched so each batch could be committed and checked.
Countable facts, not a feature list:

| Batch | Changes | Selftest checks |
| --- | --- | --- |
| 2.1.0 | stemmer, best-hit-line scoring, .gitignore, `ask`, `--explain` | 18 → 25 |
| 2.2.0 | call sites, declared_symbols, block dedup, second hop, `.ctxrc` | 25 → 26 |
| 2.3.0 | `path`, `plan`, bench delta, output header | 26 → 27 |

**One defect caught before commit, in the batch that introduced it.** The
`--budget` loop iterated over `(p_query, p_ask)` *before* `p_ask` existed — a
`NameError` raised while building the argument parser, which would have crashed
every `ctx` command, not just the one being changed. `p_ask` also declared
`--budget` itself, so the fix was ordering plus removing the duplicate. This is
the third time an edit to a shared region has produced a crash-class defect that
only the *next* read revealed; the read-back is what caught it.

**What is still unmeasured.** None of these twenty changes has been scored. The
bench runs in CI on this repo and on the 795-file corpus, and the delta line now
prints whether intelligence-first actually beats `lean` on recall — but no number
from that run is in this file yet. Ten of the twenty iterations were justified by
reasoning about what should help, not by a measurement showing it did. That is the
honest split, and it is why the bench delta exists.


## Trace: the measurement was gated behind the thing that kept breaking

Three consecutive `ctx` runs failed before the benchmark step: first a wrong
assertion, then a venv scan, then a broken pipe on `| head`. Each failure was
real and each got fixed — but because `bench` sat *after* `install` in the job,
none of those runs produced a single number. The tool was being debugged without
the instrument that says whether it works.

Reordered. `ctx bench` now runs directly after the self-test, before the console
script is installed. A cleaner install can never again be the precondition for
learning whether intelligence-first beats `lean`.

That ordering was my own, and it is the same class of mistake as answering from a
README: both let a proxy stand between the question and its evidence.

**Time note.** No clock is available in this environment, so elapsed time cannot be
measured or waited on; work proceeds in rounds. The date recorded by git at this
point is 2026-11-22.


## Trace: the first real numbers, and the flaw they exposed

`ctx bench` on the 795-file corpus, 10 queries, budget 4000:

| policy | recall | tokens | ms |
| --- | --- | --- | --- |
| read_all | 1.000 | 4000 | 41.3 |
| grep | 1.000 | 4000 | 56.9 |
| intelligence | 0.800 | 3493 | 143.9 |
| lean | 0.700 | 2990 | 127.3 |

**Intelligence-first beat lean by +0.100 recall for +503 tokens.** The change was
worth making; the hypothesis held on this corpus.

**But the table was lying.** `read_all` and `grep` "used" exactly 4000 tokens
because the code reported `min(tokens(emitted), budget)` — they emit the whole
corpus and the column quietly capped the cost. A dump that blows the budget was
scoring 1.000 recall at zero apparent penalty, which is precisely the accounting
trick I called out in graphify's benchmark two days of work ago.

Worse: the "best by recall" line then reported `read_all` as the winner, so the
benchmark's own headline contradicted the protocol it exists to test.

Fixed: the tokens column is now what the policy actually emitted, an `over` column
counts queries that blew the budget, and only policies within budget can win. The
old behaviour is left in this trace rather than deleted, because a benchmark that
hides its own mis-scoring is how the last one got published.

**What this cost.** About ninety minutes of iterations with no number, because the
measurement sat behind an install step that failed three times. Three of the twenty
"iterations" were fixing the tool that measures, not the tool itself.


## Trace: the night the protocol got measured properly

One long session, ~15 commits, `ctx` 2.1.0 → 2.12.0. The point of recording it is
the split between what the numbers justified and what only reading justified.

**What the measurement bought.** At 100 queries on 795 files, intelligence-first
beats the token-first baseline by **+0.080 recall (normal) and +0.070 (hard)** for
~250 extra tokens. Held across three sample sizes (10 → 25 → 100) once the
accounting was fixed. Four phases earned their place; the default is defensible.

**What reading the code bought, before any number:**

| Defect | How it surfaced |
| --- | --- |
| `read_all` reported `min(emitted, budget)`, so a dump scored 1.000 at no cost | The first bench whose numbers made no sense |
| `enclosing_block` could end *before* the matched line | Re-reading a function I had just written |
| `const handler = async () => {}` was not a declaration | Noticing TS functions were invisible to call-site expansion |
| `p_query` loop referenced `p_ask` before it existed (NameError on every command) | Read-back of the edit itself |
| `ctx map .` listed site-packages from its own `.venv-ctx` | CI log |
| `BrokenPipeError` and exit 1 on `| head` | CI log |
| `__version__` said 2.6.0 at 2.12.0 | Reading the constant during an unrelated edit |
| Test asserted a file imports itself | CI, after three failed runs hid the benchmark |

**The cost of the ordering mistake.** `ctx bench` sat after the `install` step in
CI. Three consecutive runs failed on install-adjacent bugs, so the benchmark never
ran and none of the above could be *measured* until it was reordered. Roughly
ninety minutes of iteration produced no number for that reason alone.

**What is still unproven.** 0.72 recall is the ceiling of the current design on
this corpus. The 28% misses are not characterised — never-ranked file, or budget
exhausted — and until they are, more phases are guessing. That is the next
measurement, not the next feature.



## Trace: 2.18.0 — the measurement that had no reader

A benchmark that runs and nobody reads is the same defect as a test that passes
and proves nothing. This trace is about the reporting channel, not retrieval.

**The failure.** `ctx bench` has printed a full table — recall, tokens, over
budget, ms, per policy — since 2.15.0, and CI has run it five times per push on
three corpora. None of those numbers reached the agent doing the iteration,
because I never fetched them. The floor was built on the belief that a passed
job's log was unreadable; see the correction at the end of this entry.

**How it surfaced.** Reading a green run's check list and noticing the only thing
that could be learned from it was "passed". The numbers from 2.16.0 (phrase boost)
and 2.17.0 (small files whole, two blocks per top-10 file) were still unknown
after both versions had been written and pushed — two changes measured by a
harness whose output nobody could read.

**The fix.** `ctx bench --floor <recall>` exits 1 when intelligence recall falls
below the floor, printing the whole table and the missed floor on stderr. A green
run now means "at least the floor"; a red one is the report. CI sets the floor at
0.75 on this repository, against a measured 0.790 normal at 100 queries and budget
4000, and writes every bench table into `$GITHUB_STEP_SUMMARY` so the numbers are
at least on the run page. `set -uo pipefail` (no `-e`) is deliberate: the summary
must be written before the step exits with the bench's status.

**The same defect, one level up.** While fixing it, two more stamps were found to
be out of date in the same way — written once, never re-read:

| Drift | How long | How it surfaced |
| --- | --- | --- |
| `pyproject.toml` said `version = "2.0.0"` | 17 releases | Reading the manifest while adding a floor flag |
| `SKILL.md` said bodies stop at rank 10 | 4 releases (2.14.0 made emission spend to 85%) | Reading the paste-the-URL entry point |

The version-drift check in CI compared only `ctx.py` and `README.md`, so a file
that ships to PyPI could disagree with both and pass. It now compares every file
that carries the number, exactly.

**What was not claimed at the time.** The recall effect of 2.16.0 and 2.17.0 was
unmeasured when this entry was written. The floor was what made the next reading
possible; it was never a result.

**Correction, same day.** `github_checks action=logs` returns the console log of a
**passed** job, given its `job_id` — the tool description says "a failed job's
log", and I built the whole "no reader" diagnosis on that sentence without
testing it. Reading job 137403206767 produced the numbers:

| version | normal | hard |
| --- | --- | --- |
| 2.14.0 | 0.790 | 0.750 |
| 2.18.0 | **0.880** | **0.900** |

The phrase boost and the small-file/two-block emission were worth +0.090 and
+0.150. Meanwhile the diagnose moved from "25 misses at median rank 40" to
"10 misses at median rank 1", which reverses the next step: reach was the problem
at 2.14.0 and is not the problem now.

So the version was right about the gate and wrong about the cause. The gate stays
— recall must not regress silently — and the lesson is recorded rather than
smoothed over: a tool description is not documentation of behaviour, and reading
one is not testing it.



## Trace: 2.19.0 — reach instead of detail below rank 10

**The evidence.** 2.15.0's diagnose said the remaining misses were all "ranked but
not emitted", with the missed file at a **median rank of 40** and only 7 of 25
inside the top 10. The ranking had found every answer; the emission could not
reach them.

**The arithmetic.** Phase 2 spends bodies in rank order until 85% of the budget is
gone. A 795-file corpus at 4,000 tokens reaches roughly rank 20 when each deep
file costs a full enclosing body — a 30-to-50-line block, 100–200 tokens. The
answer at rank 40 is behind 20 files the budget never gets to.

**The change.** Ranks 11 and deeper get a nine-line window centered on the best
hit line, instead of the enclosing body. That is roughly a third of the cost per
file, so the same tokens reach two to three times deeper into the ranking. Ranks
1–10 are untouched: they still get whole bodies, two per file.

**Why the window still contains the needle.** `best_hit_lines` returns the line
matching the most query words, and a bench needle is by construction a line full
of the query's rare words. So the window is centered on the line most likely to
be the answer. This is a correlation, not a guarantee — a needle in a second
function of a deep file escapes, and that is what the measurement is for.

**Prediction, recorded before the run.** Normal recall rises above the 0.790
measured at 2.15.0 and hard recall above 0.750, at similar token cost. If it does
not, the window is too tight and the radius is the knob — not the idea.

**Measured result — and the revert.** 0.880 normal, 0.900 hard, 2,904 and 2,752
tokens. That is *identical* recall to 2.18.0 (0.880 / 0.900) with tokens within
noise (+1 and +4). The change bought nothing, because by 2.18.0 the misses were no
longer at rank 40 — they were at rank 1. The evidence that justified 2.19.0 had
already been made obsolete by the fix two versions earlier, and I built on the
diagnose from 2.14.0 without re-reading the current one.

Reverted in 2.20.0. The trace stays because a version that measured zero is
better evidence than a version that was never run.



## Trace: 2.20.0 — the budget was never the constraint

**What the 2.18.0 numbers actually said.** Normal recall 0.880, hard 0.900, and
the policy spent **2,903 of its 4,000 tokens**. The 10 remaining misses were
"ranked but not emitted" at a **median rank of 1**, 8 of 10 inside the top 10.

Both halves matter:

- The file holding the answer is almost always the file ranked first. Ranking is
  no longer the problem.
- The policy leaves ~1,100 tokens unspent. Phase 2 stops because it runs out of
  *files that matched a query word*, not because it runs out of budget.

So the ceiling is neither reach nor ranking. It is **coverage of the one file that
matters**: two blocks per file is a guess at which part of a 200-line file holds
the needle, and on 10 of 100 queries that guess was wrong while the budget sat
unused.

**The change.** Phase 1 covers the top file with up to four enclosing blocks and
the next two with three each (was two for all three). Phase 2 emits three blocks
per file down to rank 10 (was two). Deep ranks are unchanged.

**The arithmetic of the trade.** The extra two blocks are the cheapest tokens in
the policy: they are in the file already ranked first, and they are paid for out
of headroom that was measurably idle. Under the stated objective — intelligence,
then tokens, then speed — spending idle budget to cover the top file is not a
trade at all.

**Prediction, recorded before the run.** Normal recall > 0.880 and hard > 0.900,
tokens rising toward 3,200–3,600 but staying under the 4,000 budget. If recall
does not move, then two blocks were not the reason for those misses either, and
the next suspect is the *block boundary* rule rather than the block count.



## Trace: 2.21.0 — each version builds the next, made mechanical

**The question that exposed it.** "Are you following the thing where every new
version you use it to help make the next version?" The honest answer was: no,
not in the part that matters.

What *was* working: every version was measured, and 2.19.0 was reverted when the
measurement said zero (0.880 / 0.900, tokens within noise). The evidence half of
the loop is real and it caught a bad version.

What was not working: the next change was still chosen from my memory of a
diagnosis. 2.19.0 is the proof — built on 2.14.0's "median rank 40" when 2.18.0
had already moved the misses to median rank 1. Nothing in the tooling could have
told me that, because `ctx bench --diagnose` reports counts and a median, not
which queries, which files, or which lines.

I also never invoked `ctx` on this repository while working on it. There is no
shell in this environment, so `ctx` cannot execute locally at all; it runs only
in CI. That is a real constraint, not an excuse: the fix has to be something CI
runs and I read.

**The change.** `ctx next` is the same measurement resolved to lines. For every
generated query the current version misses, it prints the needle, the file and
line holding it, that file's rank, and one of four classifications:

| Classification | What it means for the next change |
| --- | --- |
| never ranked | a ranking problem — the file was not a candidate at all |
| ranked below the top 10, never reached | a depth or budget problem |
| ranked in the top 10, blocks missed the line | a block-selection problem |
| line emitted, needle absent | the line was truncated or the fact is split |

Those four need opposite fixes, and until this version the diagnose could not tell
them apart at the file level, let alone the line.

**Checked before claiming.** `cmd_next` was written with a call to a helper that
does not exist (`context_of`), which would have raised `NameError` on first run.
Reading the function back caught it, and it now builds the context once per query
and reuses it. The read-back is the only reason that defect is not in the commit.

**Prediction.** Recall unchanged at 0.890 / 0.900, because no retrieval code
changed. If it moves, the new command is affecting the pipeline and that is a bug,
not a gain.



## Trace: 2.22.0 — the first thing `ctx next` said was that the bench was wrong

**What the loop produced on its first run.** `ctx next` ran 2.21.0 on the same
100 hard queries and named all 10 misses with file, line, rank and cause. Five
were Uzbek and Turkish words appearing once in `README.uz.md` and `README.tr.md`;
two more were English words inside a prose prompt file, both at line 12; three
were code: `truncateReason` at rank 16, `chatCompletionSchema` at rank 96, and
`tombstone_source` at rank 7.

I first wrote that split down as "six, two, two" — from memory of the list rather
than from the list, minutes after the tool printed it. Recounting gives 5 + 2 + 3.
The correction stays in this entry because miscounting your own output is exactly
the failure the tool exists to prevent.

**What that means.** `auto_queries` selects needles from identifiers found in any
text file, and `.md` is a text file. So a prose word that happens to occur once
becomes a "rare identifier" and a benchmark question. The 0.900 hard recall was
partly a measurement of prose retrieval, which the tool was never built for and no
developer would ask for.

**Why this is 2.21.0 earning its keep.** The previous diagnose could only say
"10 misses, median rank 1, 8 of 10 inside the top 10". That sentence is consistent
with a block-selection bug, and I had already guessed in that direction. The
line-level list falsified the guess in one run: the misses were mostly not code.

**The change.** `ctx bench --code-only` and `ctx next --code-only` choose needles
from code files only, skipping `.md`, `.rst` and `.txt`. The corpus is untouched,
so a real question about a README is still answerable — only the *generated
questions* narrow. CI runs both rates and prints both, and the code-only rate does
not replace the default in the docs. Removing hard cases from a benchmark is the
specific dishonesty this project was built to criticise; adding a second,
narrower measurement and showing both is the defensible version.

**Prediction.** Recall under `--code-only` is higher than 0.900 on the same
corpus, and the remaining misses are the two code ones plus some block-selection
failures. If it comes out lower, the prose needles were not noise and I was wrong
about the cause.



## Trace: 2.23.0 — an architectural pass, and a phase that had never run

**What the loop had just produced.** 2.22.0's code-only run measured **0.940** recall
at 3,563 tokens (against 0.900 at 2,776 with prose needles included), and its `next`
named six misses:

| needle | where | rank | what it blames |
| --- | --- | --- | --- |
| `ensureApiKeysBaseUrlColumn` | `migrations/…legacy_baseline.ts:269` | 130 | ranking |
| `firstNumber` | `model-discovery.ts:142` | 37 | ranking |
| `maxMb` | `media.ts:1818` | 13 | ranking |
| `heuristicallyExhausted` | `ratelimit.ts:1194` | 10 | depth |
| `informed` | `codex-base-instructions.ts:12` | 1 | block selection |
| `complexity` | `codex-base-instructions.ts:12` | 1 | block selection |

Four of six are ranking failures, not emission failures. The instrument said the
binding constraint had moved, which is the only thing it exists to do.

**Then I read the source instead of the numbers.** Seven findings, all architectural:

1. **The call-site phase had never emitted anything.** `index = stem_index(files)` in
   the import phase overwrote the symbol index that the call-site phase then received,
   so it searched file stems for symbol names. Separately, `declared_symbols` returns
   whole names while the index was keyed by their split parts, so even the correct
   index would have missed `refresh_token`. The phase had been dead since it was
   written, and the README described it as working.
2. **Emission was all-or-nothing.** A block that did not fit the remaining budget was
   discarded, not narrowed. That is why the policy spent ~2,900 of 4,000 tokens and
   stopped: the *refusal* was the ceiling, not the budget.
3. **The cost it reported was not the cost it emitted.** `used` summed block bodies
   only; every `### path:l-l` label and the header sat outside the count, so a
   "budget 4,000" context was larger than 4,000.
4. **One of `ctx next`'s four classifications was unreachable.** Its "line emitted,
   needle absent" branch tested a stripped line against the context, so it could only
   fire when the needle was on a line the recall test had already found. The real case
   — the 200-character line cut — was reported as a block-selection fault, naming the
   wrong phase.
5. **Retrieval exists twice.** `ctx.py` and `eval/retrieval_bench.py` each carry their
   own corpus, ranking, emission and recall code, and the research harness ranks with
   PageRank over the import graph, which the product does not have at all. The
   `--sweep` and `--ablate` numbers therefore describe a tool nobody can install.
6. **`rank`'s "symbol match" is not a declaration signal.** `Source.symbols` holds
   every identifier's *parts*, so `symbol_hits` — weight 4, the dominant term — scores
   "this file contains the word", not "this file declares it". Rung 2 and `rank`'s own
   docstring both claim an ordering the code does not implement. With four of six
   misses at ranks 10–130, this is the likeliest single cause of the remaining gap.
7. **The benchmark's query is its own needle.** `auto_queries` sets `question` to the
   identifier and `needles` to the same identifier, so the whole-query substring boost
   in `rank` is measured on questions whose entire text appears in the answer. It can
   only ever fire under benchmark conditions, and never on a real question.

**What 2.23.0 changes.** `Corpus` owns the files and every index, built once, so one
phase cannot overwrite another's; `plan_context` selects `Chunk` ranges and
`render_context` renders them once; `candidate_ranges` narrows instead of refusing;
identifiers are stored unsplit so a declared name resolves; the call-site phase works
and is regression-tested against both faults; cost counts labels and the header;
`ctx next` decides coverage from emitted ranges; `--phases` makes each phase
removable, which is the ablation the research harness had and the product did not.

Two heuristics were written and then removed during this version: a consecutive-failure
break in the excerpt and map phases. Both would have stopped walking the ranked list
after N files that fitted nothing, and both could drop coverage from a later, smaller
block. They were replaced by a lower-bound cost check (`too_big`), which skips
rendering a range only when the line lengths prove it cannot fit. That is exact rather
than probable, and it recovers most of the wasted work without a recall risk.

**What it deliberately does not change.** `rank`. Finding 6 is the biggest
intelligence lever and it has to be measured alone. Changing it in the same version as
the emission rewrite would make the result unattributable, and `--phases` now gives
the next version the means to separate them.

**Prediction, recorded before measuring.** Recall up or flat. Tokens up, and not
because the policy got greedier: the basis changed, so 2.23.0's token column is *not*
comparable to 2.22.0's and the CI floor must be re-based from the new number rather
than assumed. If recall falls, the shrink and call-site gains cost more than the
labels they displaced, and `--phases body,excerpt` versus `body,excerpt,call` is the
first comparison to run.



## Trace: 2.24.0 — the line cap was the answer, and a budget bug I shipped

**The loop, with receipts.** 2.23.0 was built from 2.22.0's `next`: six code-only
misses, four of them ranking failures at ranks 10–130. 2.24.0 is built from 2.23.0's
`next`, and that was only possible because 2.23.0's first act was to make one of its
classifications reachable.

**What 2.23.0 measured, including what it broke.** normal 0.890 / 3,196 / 15 over;
hard 0.910 / 2,934 / 14 over; code-only 0.940 / 3,698 / 22 over. Recall moved by one
query on one set — inside the interval, so not a result. The over-budget column is the
story: `intelligence` failed its own budget check, so "best within budget" nominated
`read_all`, a 1.9M-token corpus dump.

The defect was in the accounting, not the corpus. The gate charged *floored* per-block
token counts against `budget - 24`. Each floor loses up to one token, the `\n\n`
between blocks was never counted, and 24 tokens of reserve is less than that loss once
about ten blocks fit — which per-block chunks made routine. 2.24.0 counts characters
and converts once, in the same expression `render_context` uses, so the gate cannot
disagree with the renderer.

**What 2.23.0's `next` said next.** Nine hard misses. Two were ranking —
`truncateReason` at 16, `chatCompletionSchema` at 96. Seven were reported as
*"line emitted, but the needle sits past its 200-character cut"* — a classification
that did not exist before, because the branch that would have described it could never
fire.

**The cause.** `numbered_lines` kept `line[:200]`. The missed lines are
single-paragraph markdown and long prompt strings, and the word asked about sat past
column 300. The context therefore contained the line and not the answer, and every
earlier diagnosis — "blocks missed the line", "not enough coverage of the file" — was
describing the wrong phase. `clip_line` now shortens a long line *around the earliest
query word*, so the word is always inside the emitted span. The cap rises to 240
characters, because a 200-character window centred on a match leaves only ~65
characters of context either side.

**Also fixed.** `is_ignored` tested an anchored pattern as
`str(rel).startswith("/build")`, which no relative path matches, so every `/pattern`
in every `.gitignore` was a silent no-op. And the bench now prints a Wilson interval
beside recall: at 100 queries one query is exactly 0.010, and this file has twice
described a single query as a gain.

**The loop is now a CI step.** Every push downloads the published 2.22.0 file, runs its
`next` against the current checkout, then runs the current version's. "Each version
builds the next" is checkable from the log instead of asserted in prose.

**Prediction, recorded before measuring.** Hard code-only recall should rise above
0.940 if the truncation theory is right — up to seven queries, so 0.990 with the two
ranking misses intact. `over` should be 0 on every row. If recall does not move, the
truncation theory is wrong and those seven misses are something else; if `over` is
still non-zero, the character accounting has a second hole and the gate still is not
the renderer.



## Trace: 2.25.0 — a lookup is not a topic

**What 2.24.0 measured.** Normal 0.930 at 3,212 tokens, hard 0.980 at 2,945,
hard code-only 0.960 at 3,698. No row over budget. The `next` list, code-only:

| needle | rank | classification |
| --- | --- | --- |
| `heuristicallyExhausted` | 10 | ranked in the top 10; blocks missed the line |
| `maxMb` | 13 | never reached |
| `firstNumber` | 37 | never reached |
| `ensureApiKeysBaseUrlColumn` | 130 | never reached |

**Why three of four were never reached.** Two causes stacked. Phase 1 spends four,
three and three enclosing blocks on the top three files, and phase 2 stops at 85%
of the budget, so by the time rank 13 comes round the money is gone. That is the
emission half.

But the ranking half is worse. `maxMb` splits into `max` and `mb`; a file that
mentions `max` forty times scores about 40, while the single file declaring
`maxMb` scores about 15. The exact-phrase multiplier was ×3, which cannot beat a
hundred partial hits. `firstNumber` and `ensureApiKeysBaseUrlColumn` fail the same
way. So the answer's own file was pushed so far down the list that no budget could
have reached it.

**The change.** A query that is a single identifier is a *lookup*, not a topic.
Any file containing that exact identifier now outranks every file that merely
contains its parts, regardless of part counts. Sentence queries keep the ×3
multiplier, because for prose a verbatim hit is strong but not conclusive.

**Why this is not tuning to the benchmark.** `ctx next` generates identifier
queries because that is what it can score mechanically. But "I asked for this
symbol, so the file that has this symbol should come first" is the most basic
correctness property a code retrieval tool can have, not an artifact of how the
test is built. Natural-language queries are unaffected by the change and the
0.930 normal figure covers those.

**A correction, before the measurement.** In the previous turn I reported a unit
mismatch in `too_big`, comparing characters against tokens. Re-reading it:
`budget_chars = budget * 4` and the check is `(chars + floor) // 4 > budget`, so
the units are consistent and the floor is a genuine lower bound. There was no bug
and I did not change it. I also reported 2.24.0's hard recall as 0.960; that is
the code-only figure, and the default hard number is 0.980.

**Prediction, recorded before measuring.** Code-only hard recall rises from 0.960
toward 0.99 and the three "never reached" needles move to the top of the ranking.
Default and normal recall also rise, since the same identifiers appear in their
needle sets. Tokens change little. If recall does not move, the rank positions
were not caused by partial-word outscoring and the next suspect is phase
allocation — breadth-first emission instead of four blocks for one file.



## Trace: 2.25.0 — measured

| set | recall | tokens | over |
| --- | --- | --- | --- |
| normal | 0.940 | 3,212 | – |
| hard | 1.000 | 2,945 | – |
| hard, code-only | 1.000 | 3,698 | – |

`next` reports **0 misses** on both the default and the code-only set, and
`diagnose` reports 0 as well. Every generated query returns its answer text.

The prediction held: code-only hard 0.960 → 1.000, the three never-reached
needles moved to the top, the other rates rose, and tokens did not move at all
(3,212 before and after). Ranking, not emission, was the whole of the remaining
gap.

**What it means, stated carefully.** This is not "retrieval is solved". The
generated queries are single identifiers, and the lookup tier now answers 100% of
single-identifier queries on this corpus. The 0.940 normal figure is the honest
headline for a mixed set. What the result does say is that the last four misses
were not about block selection, budget, or the phases — they were the ranking
putting the right file in the wrong place.

## Trace: 2.26.0 — the interval that never moved

**The bug.** Reading 2.25.0's own table, every row printed the same 95% interval:
`(0.002-0.054)` for recall 1.000 and for 0.940 alike. The call site passed a
proportion where `wilson` expects a count of successes:

    low, high = wilson(mean_recall, len(queries))   # 0.94 / 100, twice

So `wilson` divided by the total a second time and centred the interval near
0.009. The guard that was added to stop this project calling a one-query change a
result had never worked, in any version since it was written. It printed a
plausible-looking bracket that no reader could have caught without comparing two
rows.

Fixed by passing `round(mean_recall * len(queries))`. The selftest now pins three
points — 94/100, 100/100, 0/100 — so an interval that does not move fails the
build.

**Why it survived.** Nothing tested the call site. The function was correct; the
argument was wrong; and the output looked like an interval. This is the same
failure as 2.19.0 in miniature: a component that reports, attached to a caller
nobody checked.

**The second half of 2.26.0.** The user's goal was that a weaker model could
reach the same standard by following the protocol. That is only a claim until it
is measurable, so this version adds the measurement:

- `eval/tasks.json` — ten questions over a six-file fixture corpus, with
  hand-written exact-string answers. Ground truth that does not move when `ctx`
  changes, because it is not derived from `ctx`.
- `eval/score.py` — scores a submission of *ranges the model actually read*
  against those answers, reports recall and tokens, and optionally scores `ctx`
  itself on the same tasks so the comparison is mechanical.
- `SKILL.md` Mode 4 — the four failure modes observed in this project, each with
  the check that catches it, and five steps that each produce an artifact.

**What is not claimed.** No weaker model has been run against the suite in this
session. The suite makes the claim testable; it does not make it true. The
distinction matters because "a weaker model reaches this level" is exactly the
kind of sentence this project keeps catching itself writing.



## Trace: 2.27.0 — the model that wrote the protocol, scored against it

**What prompted this.** The user pointed out that the model doing this work — the
one that built 2.22.0 through 2.26.0 — is the weaker model, after the stronger one
ran out of usage partway through. Taken at face value, that means 2.26.0's Mode 4
was written by its own target audience, and this session is the first subject.

That is worth recording before it is smoothed over. Mode 4 lists four failure
modes. Here is how the model performed against them in the session that wrote
them:

| Mode 4 failure | Occurrences | What it actually wrote |
| --- | --- | --- |
| Miscounting its own output | 1 | "6 + 2 + 2" for a list that was 5 + 2 + 3, minutes after the tool printed it |
| Quoting a number before measuring | 1 | 0.960 described as 2.24.0's hard recall; it was the code-only figure, hard was 0.980 |
| Asserting a bug that was not there | 1 | `too_big` "compares characters to tokens"; the units were consistent and nothing was changed |
| Shipping a check that never fired | 1 | The wilson call site, wrong since it was written, printing an identical bracket for 0.940 and 1.000 |
| Over-specifying a test | 1 | `hi == 1.0` for a float that returns 0.999999; caught by CI in 6s |

**Five violations, four of them in work this model wrote itself.** Two of them —
the miscount and the false bug report — were caught by reading back. One was
caught by CI. One was caught only because the user asked a question that made the
model re-read an old claim. And one, the wilson bug, was caught by noticing that
two rows of a table disagreed.

**What that says about Mode 4.** Rules with an artifact caught the error. "Recount
from the printed list" and "quote the line and its units" worked: the model
applied them and corrected itself. "Prove the check moves when the input moves"
did not, because nothing forced the comparison — it required noticing.

So the fix is not another rule. It is removing the need to notice.

**The change.** `brackets(interval, value)` states one invariant: an interval must
contain the value it describes. It is enforced in two places:

- The selftest pins eight proportions (0, 1, 13, 50, 87, 94, 99, 100 of 100) and
  requires every interval to contain its own value.
- `ctx bench` checks it on every row it prints and **exits 1** if any row's
  interval excludes its recall, refusing to summarise the table. A statistic that
  does not describe its own value is not a result, and the job should say so
  rather than leave the number on a page to be quoted later.

With the 2.26.0 bug in place, both would have failed on the first run: recall
0.940 printed beside (0.002-0.054).

**What this does not claim.** N = 1, self-scored, on tasks this model wrote. It is
an anecdote with exact counts, not a benchmark of DeepSeek or of any model. What
it does establish is that the failure modes Mode 4 names are real, they occur at
roughly one per version in ordinary work, and that a check has to be mechanical to
survive them.



## Trace: 2.28.0 — putting the rule where it is actually loaded

**The gap.** Mode 4's failure table went into `SKILL.md`, which a model reads only
if someone pastes the repository URL. The root README is the file preloaded into
every chat of this project — its own second paragraph says so — and it contained
none of those rules. So the checks that would have caught the failures observed in
this session were filed in the one place they would not be loaded.

That is the same mistake as the wilson call site, one level up: the right content,
attached to a caller nobody checks.

**Promotion, per PROTOCOL.md.** A rule joins this file only if it fixes a failure
that actually occurred, is checkable mid-task, and does not regress the bench.

| Condition | This rule |
| --- | --- |
| Real failure | 0.960 quoted as "hard recall" when it was the code-only figure; "5+2+2" for a list that was 5+2+3 |
| Checkable | Either the command and its output are on the page, or they are not |
| Bench | The rule is about conduct, not retrieval; `retrieval_bench.py` cannot regress |

**The rule, as promoted.**

> **Every number carries its command.** Quote the command and its output, or say
> you have not measured it. Recount from the printed list, never from memory:
> misstating your own result is the commonest way to be wrong while feeling right.

One rule covering both failures, because they are one failure: a figure asserted
without the thing that produced it. Forty words, roughly fifty tokens in every
chat forever, which is the real price of a preloaded rule and worth naming.

**What is deliberately not promoted.** "Asserting a bug that was not there" and
"shipping a check that never fired" stay in SKILL.md Mode 4. The first is already
implied by *Never trust a symbol you have not seen defined*; the second is now
enforced by code (`brackets` in the selftest and the bench), and a rule that a
test enforces does not also need the README's budget.



## Trace: 2.29.0 — the measurements that were still blind

Three things could not be answered from the product's own output before this
version. Each is now a flag on `ctx bench`, and the measurement runs in CI.

**The knee.** `--sweep 1000,2000,3000,4000` runs the bench at each budget and
names the smallest one whose hit count equals the largest budget's. Same hit
count rather than "inside the interval", because a one-query difference is
precisely what the interval says is not a result, and 2.26.0 spent a version
learning that a statistic nobody compares is decoration.

**Phase cost.** `--ablate` removes each phase in turn and reports the recall and
token delta. A phase whose removal costs nothing has been charging the budget for
itself. This uses the `--phases` flag that has existed since 2.23.0 and was never
measured at the product level.

**The misses the hard sets do not have.** `ctx next` had only ever run with
`--rare 1`, so the mixed set's 6 misses were invisible while hard and code-only
both reported zero. CI now runs `next` on the default set too.

**Question-shaped measurement.** `--queries` accepts a file as well as a count,
in both the `{question, needles}` shape and the `{tasks: [{question, answer}]}`
shape the fixture uses. Every generated query is a symbol lookup; the tool exists
to answer questions, and until now the product had no way to measure that
directly.

**A refactor, for the reason the refactor exists.** The measurement loop moved
out of `cmd_bench` into `bench_rows(corpus, queries, budget, phases)`, so the
sweep and the ablation call the same code the single-budget table calls. Three
measurements, one implementation. That is the same argument that retires the
research harness in 2.30.0.

**Prediction, recorded before measuring.** The sweep's knee is below 4,000 on the
mixed set, since the normal bench spends 3,212. At least one phase shows a delta
inside the interval — which is to say, no measurable contribution — and should be
dropped in 2.30.0. The default-set `next` reports misses of a different shape
from the hard set's, most likely truncated lines rather than unranked files.



## Trace: 2.30.0 — one engine, and the numbers that retired it

**What 2.29.0's primitives measured** (50 queries, freellmapi, 795 files):

| budget | recall | tokens emitted |
| --- | --- | --- |
| 1,000 | 0.940 | 922 |
| 2,000 | 0.940 | 1,775 |
| 4,000 | 0.940 | 3,281 |

The knee is 1,000: the same 47 of 50 hits at **25% of the budget**. Recall is
flat across a 4x range of budget, which means the old default was paying for
headroom nothing used.

Ablation, intelligence, one phase removed:

| removed | recall | Δrecall | Δtokens |
| --- | --- | --- | --- |
| body | 0.300 | −0.640 | −263 |
| excerpt | 0.940 | +0.000 | +2 |
| map | 0.940 | +0.000 | −275 |
| related | 0.940 | +0.000 | −23 |
| call | 0.940 | +0.000 | −197 |
| twohop | 0.940 | +0.000 | +0 |

`body` is the whole policy; every other phase is neutral on this query set and
`map` and `call` together cost 472 tokens for nothing.

**Why the phases were not deleted on that evidence.** Every generated query is a
symbol lookup, and a lookup is answered by the body of the file it names. The
map, the callers and the imports are for the question this tool actually exists
to answer — "how does X work" — and an identifier benchmark cannot see them. The
2.22.0 lesson was that a benchmark measuring the wrong thing flatters the tool;
deleting five phases because a lookup benchmark cannot use them would be the same
mistake in the other direction. So the primitives job now runs the same sweep and
ablation on `eval/tasks.json`, a hand-written question set, and the default
budget changes only after both agree.

**The harness is gone.** `eval/retrieval_bench.py` carried a second retrieval
engine — its own corpus, ranking, emission and recall — plus a PageRank policy
the product never had. Its numbers could not be reproduced by anyone using the
installed tool, which is the definition of a measurement that does not transfer.
`compare_graphify.py` now imports `ctx`; the sweep and ablation moved into
`ctx bench`; the policies it compared are `ctx bench`'s four. Its historical
numbers stay in FINDINGS.md and SCOREBOARD.md, labelled, with the note that
PageRank over imports had no product equivalent.

**What is not claimed.** The default budget is still 4,000 in this commit. The
sweep says 1,000 holds recall on identifier queries; whether it holds on
questions is being measured by the job this version added. Changing the default
before that number exists would be choosing the smaller number because it is
smaller.
