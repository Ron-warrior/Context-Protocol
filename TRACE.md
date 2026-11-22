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
three corpora. None of those numbers ever reached the agent doing the iteration.
`github_checks` shows the console log of a *failed* job only; a green job's output
is visible to whoever opens the run page on GitHub, which is not the loop that
decides the next version. So every green bench was, functionally, a bench that
did not happen.

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

**What is not claimed.** The recall effect of 2.16.0 and 2.17.0 is still unmeasured
as of this entry. The floor is what makes the next reading possible; it is not a
result. The 2.17.0 run was still executing when this was written.



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

**Measured result.** Pending CI. The 2.18.0 floor (0.75 on this repository, 100
queries, budget 4000) is what turns this into a pass or a number.
