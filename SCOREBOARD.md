# Scoreboard

The recursion lives here: what changed, what it was measured against, what was
kept and what was reverted. A protocol that cannot show its own numbers is a
preference file.

## Metrics

| Metric | Definition | Why it and not something else |
| --- | --- | --- |
| **recall@budget** | Fraction of deciding facts present in the assembled context under a token budget | The only thing that matters: did the answer reach the model |
| **tokens** | Estimated tokens of assembled context (chars / 4) | The cost side of the ratio |
| **recall per 1k tokens** | `recall / (tokens / 1000)` | Effectiveness as defined in README — correct per token, not per corpus |
| **stale-hit rate** | Search results referring to code that no longer exists | What pre-built indexes quietly accumulate |

Not metrics: number of nodes, graph size, index build time, lines of rules.

## Running it

```bash
ctx bench .                          # recall, tokens and ms, four policies at once
ctx bench . --budget 2000            # a tighter budget
ctx bench . --sweep 1000,2000,4000   # recall per budget, and the knee
ctx bench . --ablate                 # what each phase costs in recall and tokens
ctx bench . --queries tasks.json     # your own questions, with known answers
ctx selftest                         # fixtures; exit 0 means it works
```

Policies compared, in one pass, at the same budget:

1. `read_all` — every source file whole (what graphify's 71.5x is measured against)
2. `grep` — whole files containing a keyword
3. `lean` — the token-first baseline: map first, then short windows
4. `intelligence` — this protocol: rank, bodies before maps, phases under a budget

The PageRank-over-imports policy and the stop-rule experiments lived in
`eval/retrieval_bench.py`, which was retired in 2.30.0: it carried a second
retrieval engine whose numbers no user of the installed tool could reproduce. Its
measurements are kept below, labelled historical, with the command that produced
them.

## Version log

| Version | Change | Evidence | Kept? |
| --- | --- | --- | --- |
| 1.0.0 | Initial protocol: ladder, hard rules, stop rules, persist step | Ranked synthesis of aider repo map, Serena, Anthropic context engineering, and graphify's own self-reported benchmarks (see FINDINGS.md) | — |
| 1.1.0 | Rung 5 rewritten from a time rule ("re-read after any edit") to a state rule ("the last operation on the region must be a read"); read-back required before a version bump; trace instrumentation added | The 1.0.0 trace: 441 lines of bench shipped at 0% read-back coverage (46% after partial reads), last operation on the file was a write. The rule as written was not checkable, so it was broken without noticing (TRACE.md) | Kept |
| 1.1.1 | Bench: `break`→`continue` in the ladder's heading loop; removed dead `by_path`; validate `--queries` JSON shape | Found by the 1.1.0 read-back of the 239 lines 1.0.0 never read — the same pass that justified 1.1.0 | Kept |
| 1.2.0 | Rung 5 **Write** added (≤120 lines per write, verify before extending); rung 6 verifies edits by `git_diff` rather than whole-file re-read; PROTOCOL gains "Write side" with the arithmetic; README cut from 111 to 99 lines | The write-side hypothesis queued below, plus a countable violation: README at 111 lines against the ~100 stated in PROTOCOL.md. Applied to itself the same turn — 285 bench lines as 15 anchored edits, no overwrite | Kept |
| 1.3.0 | `--stop`: four stopping rules (`until_found`, `three_strike`, `two_strike`, `one_strike`) scored on answer rate per token with the ranking held fixed | The stop-rule hypothesis below was unfalsifiable with no instrument. Now it has one; the numbers are still unrun | Kept |
| 1.4.0 | Bench: one `chunk_cost` shared by both budget paths; outline fallback for declaration-less files; per-file cost cached on `Corpus` | Reading 1.1.1's bench against rung 6. The cost-cache defect was introduced by 1.3.0 minutes earlier and caught by 1.3.0's own read-back | Kept |
| 1.5.0 | `--selftest`: 12 fixture assertions encoding the three defects 1.4.0 fixed | A harness that has never run cannot be evidence. The fixture makes the first run a test of the instrument, not of the repo | Kept |
| 1.6.0 | Rung 2 implemented: `Ranking` knobs for focus, definition-over-usage and length damping, each a flag so it can lose; whole-token matching replaces substring matching in recall and in stop-rule answers; five new self-test assertions (17 total) | Re-reading the bench against rung 2 found all three ranking clauses were **not implemented** — every occurrence weighed the same. Substring matching credited `refresh_token` inside `refresh_token_legacy` in every policy alike | Kept |
| 1.7.0 | `--sweep 1000,4000,16000`: recall per 1k at several budgets, and whether the winner holds | One budget is one point. A policy that wins at 4k can lose at 16k, and the protocol's budget-cap rule is only justified if the ranking holds across the cap | Kept |
| 1.8.0 | Bench: `run_stop` unpacked a 2-tuple from the 3-tuple `prepare` now returns (would have crashed `--stop`); `--queries` load errors reported cleanly; `--sweep` and `--focus` validated in `main` | Read-back of the 1.6.0 region after the edit found the crash. Caller sweep then covered every changed signature | Kept |
| 1.9.0 | `report_stop` printed an undefined `queries` (crash on `--stop`); `tokens_per_answer` reports `inf` instead of a flattering `0` when a rule answers nothing; CI workflow compiles, self-tests and smoke-runs every mode | CI run 45064682765. The undefined name had survived an explicit read-back of its own region — reading a line is not checking a line | Kept |
| 1.10.0 | Bench: `--stop` walks the ladder's scoped chunks (outlines, then windows) instead of whole files; a miss is one chunk read without the needle; three new self-test assertions (20 total) | Real-corpus run 45074848996 (795 files): three of four stop rules returned identical tokens (3,042 per query) at a 4% answer rate — whole-file reads hit the 4k wall before any strike rule could fire, so the experiment measured read granularity, not stopping. Chunk-level reads are what rung 4 prescribes | Kept |
| 1.11.0 | Bench: strikes count only scoped windows, not outlines — rung 4's reads govern the stop rule, rung 3's map burns none; fifth fixture whose needle lives in a lower-ranked body; three self-test assertions rewritten for the new semantics (20 total) | Run 45075205417: until_found 68% at 2,404 tokens (best answers/1k, 0.283); strike rules died in the outline phase (one_strike 524 tokens, 0% — the map cannot answer a body question). Falsifiable prediction: strike answer rates rise toward until_found; three_strike may then challenge it per token | Pending |
| 1.12.0 | `--ablate`: the ladder with each rung-2 claim disabled (definition weight, length damping, PageRank itself), same queries, same budgets, smoke-run added to CI | The knobs were asserted to change the ranking (self-test) but never shown to improve recall — a knob that never moves recall per 1k is decoration. Prediction recorded before the run: if default ties every ablation on the real corpus, the rung-2 knobs are decoration until shown otherwise | Pending |
| 1.13.0 | `--outline-sweep`: rung 3's 40%-of-budget outline share becomes a swept knob (0 = mapless, 1 = map only), ranking held fixed; self-test pins both ends; smoke-run added to CI | The 40% constant was set by judgement and never tested; on the real corpus the map phase can spend 1,600 of a 4,000-token budget. Prediction recorded before the run: if recall per 1k is flat across shares the constant is not load-bearing; if another share wins, rung 3 gets retuned | Pending |

## First measured results

CI, this repository, 7 files, 10 auto queries, budget 4,000 tokens. The first
numbers the harness has ever produced.

| policy | recall | tokens | recall/1k |
| --- | --- | --- | --- |
| read_all | 0.500 | 3,552 | 0.141 |
| grep_files | 0.900 | 2,188 | 0.411 |
| pagerank_map | 0.100 | 1,659 | 0.060 |
| **ladder** | **1.000** | **1,611** | **0.621** |

At a 1,000-token budget: ladder 1.864, pagerank_map 0.119, grep_files 0.000,
read_all 0.000. Ladder won at every budget tried.

What this does and does not say:

- **The ladder's own claim survives its first test** — 4.4x grep per token, and
  the only policy at full recall.
- **The "outlines first" hypothesis is falsified.** `pagerank_map` is outline-only
  and ranks worst, below grep. A signature map alone does not reach the answer;
  the ladder's scoped windows do the work. Struck through in the hypothesis list,
  not deleted.
- **Seven files is not a corpus.** The auto queries come from this repo's own rare
  identifiers and one file is 930 lines of the bench itself. The ranking claim
  needs 50+ files before it counts as evidence about real codebases.

## First real corpus

CI run 45074848996: [freellmapi](https://github.com/tashfeenahmed/freellmapi),
sparse checkout of `server/src`, `shared` and `cli` — 795 files, 25 auto
queries. The first numbers from a codebase this protocol was not written against.

recall per 1k tokens, by budget:

| policy | 1,000 | 4,000 | 16,000 |
| --- | --- | --- | --- |
| read_all | 0.000 | 0.000 | 0.003 |
| grep_files | 0.000 | 0.108 | 0.040 |
| pagerank_map | 0.121 | 0.070 | 0.023 |
| **ladder** | **0.567** | **0.213** | **0.058** |

What this says:

- **The ranking claim survives its first real test.** Ladder best at 1k, 4k and
  16k — 5x grep at 1k, 2x at 4k. The winner did not change with the budget, so
  it is not a one-point artifact.
- **The `pagerank_map` recovery prediction was half right.** At 1k it beats grep
  (0.121 vs 0.000), which it never did on seven files — that import graph was
  too sparse for PageRank to say anything. But it still loses to the ladder at
  every budget: a map narrows the search, the scoped windows win it.
- **The first valid stop-rule numbers** (bench 1.10.0, chunk-level walk, 25
  queries, budget 4k):

  | stop rule | answer rate | tokens | tokens/answer |
  | --- | --- | --- | --- |
  | until_found | 0.680 | 2,404 | 3,536 |
  | three_strike | 0.200 | 1,035 | 5,176 |
  | two_strike | 0.160 | 817 | 5,106 |
  | one_strike | 0.000 | 524 | inf |

  `until_found` wins answers per 1k (0.283). The quit-form of the stop-rule
  hypothesis is **falsified**: strikes do not hold answer rate, they trade 52
  points of it for 2/3 of the tokens and lose on both ratios. But the strike
  costs themselves expose a second instrument artifact — one_strike at 524
  tokens means it quit *during the outline phase*, and the map cannot answer a
  body question. Counting outline misses as strikes measured the map, not the
  stopping. Bench 1.11.0 counts strikes over scoped windows only.

Later versions append a row. Reverted changes stay in the table, marked reverted,
with the number that killed them. Deleting a failed change hides the only thing
worth learning from it.

## Upgrade loop

Each time the protocol is used on real work:

1. **Record the trace.** Question, rungs used, tokens spent, whether the answer was
   found, and — the important one — the first wrong turn.
2. **Name the failure.** "Read three files because I assumed the handler was in
   the router" is a failure. "The repo is big" is not.
3. **Propose one change.** One, as a check the agent can run mid-task.
4. **Test it.** Bench on a real repo, or at minimum a re-run of the failing trace.
5. **Promote or drop** by the promotion rule in PROTOCOL.md. Bump the version.

## Open hypotheses

Queued, not yet tested. Cheap to test, so test them rather than arguing:

- ~~**Outlines first always beat windows first** on files ranked 1–3.~~ **Falsified**
  on the first measured run: outline-only `pagerank_map` scored 0.060 recall/1k,
  the worst of four policies and below plain grep. A signature map alone does not
  reach the answer — the windows do the work. Kept struck through, because a
  deleted failed hypothesis teaches nothing.
- **A two-strike stop rule cuts tokens more than better ranking does.** Ranking
  improves the hit rate; stopping bounds the misses. The bound may be worth more.
- **The expensive part is authoring, not retrieving.** 824 lines authored, 202 read
  back, 3 defects in the part never read. **Promoted to rung 5 in 1.2.0**, with the
  checkable form: no write over ~120 lines, verify before extending the file. What
  is still unmeasured is whether that cuts defects per 1k authored lines — 1.2.0's
  own trace is the first data point, not the proof.
- **Verify by diff beats verify by re-read.** A `git_diff` of an edit is ~5–15% of
  the tokens of re-reading the file it changed, and it shows exactly what changed
  rather than asking the reader to spot it. Adopted in rung 6 on arithmetic, not on
  measurement: testable by replaying a trace both ways and counting defects found
  per 1k tokens. If it loses, it goes.
- **The stop rule may matter more than the ranking.** Second real-corpus run
  (795 files, chunk-level, 1.11.0): until_found 0.680 at 2,404 tokens;
  three_strike 0.640 at 2,124; two_strike 0.600 at 1,936; **one_strike 0.600 at
  1,770** — best answer rate per 1k of the four. One strike gives up 0.08 recall
  for 26% fewer tokens. The quit-form is therefore not falsified at window
  granularity; it is a real trade, and a defensible one.
- **Persisted notes beat a rebuilt index** for repos under ~50k LOC, because
  re-derivation is cheap there and index staleness is not. Unchanged.
- **Cross-file rename is where text-level tools lose hardest** — the one case where
  an LSP-backed tool (Serena) would pay for its install cost outright. Unchanged.



## Real corpus (freellmapi, 795 files)

First numbers from a repository that is not this one. `--sweep`, `--stop`,
`--ablate` and `--outline-sweep` all run against it in CI.

- **Ladder wins every budget**: 0.567 / 0.213 / 0.058 recall per 1k at 1k / 4k / 16k.
- **PageRank earns nothing here**: `pagerank_off` ties the default exactly at
  0.213. Length damping and definition weighting both earn their keep (0.188 and
  0.201 without them). The aider claim does not survive in this harness.
- **The 40% outline share is load-bearing**: 0.6 costs 19% of the score, which is
  rare for a constant in this project.

Full tables and the reading of each: TRACE.md.

**Versioning note.** The protocol (README.md) is at 1.3.0 — rung 6(c) ("if the
project runs, run it") was added after the `NameError` CI run caught a defect
that survived a read-back. The bench has its own version track from 1.4.0 on,
because it changed and the protocol did not. Rows 1.6.0–1.10.0 are bench
versions; they do not bump the protocol, and no rule in README.md changed to
justify one. A protocol bump needs a rule that changed.


## Product numbers (`ctx`, not the research harness)

Corpus: freellmapi, 795 files, **100 queries**, budget 4000 tokens. Real emission,
not `min(emitted, budget)`.

### Current — measured at 2.18.0

| policy | normal recall | normal tokens | hard recall | hard tokens | ms |
| --- | --- | --- | --- | --- | --- |
| **intelligence** | **0.880** | **2,903** | **0.900** | **2,748** | 79 |
| lean (`--lean`) | 0.740 | 2,620 | 0.770 | 2,503 | 106 |
| grep | 0.990 | 736,338 | 1.000 | 704,380 | 75 |
| read_all | 1.000 | 1,960,580 | 1.000 | 1,960,580 | 64 |

Margin over the token-first baseline: **+0.140 normal, +0.130 hard**, for 283 and
244 extra tokens. `grep` and `read_all` reach 1.000 only by emitting 175x and 490x
the budget — which is the accounting error this project exists to not make.

### How it got there

| version | change | normal | hard |
| --- | --- | --- | --- |
| 2.13.0 | arbitrary cut at rank 10 | 0.720 | 0.710 |
| 2.14.0 | keep emitting bodies until 85% of the budget is spent | 0.790 | 0.750 |
| 2.16.0 | exact-phrase boost in ranking | — | — |
| 2.17.0 | small files emitted whole; two blocks per top-10 file | — | — |
| 2.18.0 | no retrieval change — the measurement itself | **0.880** | **0.900** |

2.16.0 and 2.17.0 have no row of their own because their runs were never read.
Their combined effect is the 0.790 → 0.880 / 0.750 → 0.900 step, measured at the
next run that was actually inspected. That gap is the reason 2.18.0 added a floor:
a measurement nobody reads is not a measurement.

### Where the misses went

At 2.14.0: 25 misses, all "ranked but not emitted", median **rank 40** — a budget
and reach problem.

At 2.18.0: **10 misses**, still all "ranked but not emitted", but median **rank 1**
and 8 of 10 inside the top 10. The ranking now finds the right file almost every
time; what is left is a *phase* problem — the file is included, and the needle's
part of it is not. That is a different fix, and it is the next one.

### What this settles

**Intelligence-first beats lean at 100 queries, on both difficulty settings:**
+0.080 normal, +0.070 hard, for 235–255 extra tokens. The direction held across
three sample sizes (10, 25, 100 queries) and the magnitude settled around 7–8
points rather than the 10 first measured. The extra phases — enclosing bodies,
call sites, co-occurrence ranking, stemming — buy roughly 7% more answers for
about 10% more tokens. Under the stated objective that is the correct trade, and
it is now evidenced rather than argued.

**The absolute numbers stay humbling.** Best-in-budget recall is 0.72. More than a
quarter of single-file facts are still missed by a policy that fits the budget.
`grep` reaches 0.99–1.00 only by emitting 700k+ tokens — 175x the budget — and
`read_all` reaches 1.000 at 490x. The honest framing: a bounded policy gets about
72% of the answers, and the last 28% costs two orders of magnitude.

**Where to look next**: the 28% misses, not more features. A needle is missed when
its file is never ranked (so no body is emitted) or when the budget ends before
its phase. Distinguishing those two is the next measurement.

`lean` also ran *slower* here (113ms vs 78ms), which makes no sense for a
cheaper policy and is probably noise on a shared runner. Noted, not acted on.





## 2.18.0 — the bench becomes a regression test

Every number above was produced by a harness whose output I never read. Green
jobs print to a run page; I assumed the log was only available for failures and
did not try. So the measurement existed and the feedback did not.

`ctx bench --floor <recall>` closes that regardless: recall below the floor exits
1 and prints the table and the shortfall on stderr. CI runs the self-bench at
0.75 and every bench table now also lands in the job summary. The floor earns its
keep as a regression gate — recall cannot move down silently.

**Correction, the same day.** `github_checks action=logs` returns the full log of
a *passed* job when given its `job_id`. I assumed otherwise from the tool
description and never tested it until after this version shipped. Reading job
137403206767 that way produced the 0.880 / 0.900 numbers above. The floor stands
as a gate; the claim that green runs were unreadable does not.

Two documentation stamps were found stale while wiring it — `pyproject.toml` at
2.0.0 for 17 releases, `SKILL.md` describing the pre-2.14.0 emission order. Both
are fixed, and the drift check now compares all three files that carry the
version.

**Unmeasured as of this entry:** the recall effect of 2.16.0 and 2.17.0. The floor
was added precisely because those two versions were shipped without a readable
result.



## 2.19.0 — nine-line windows below rank 10 (reverted)

Predicted, on 2.14.0's diagnose, that emission could not reach the missed answers
at median rank 40. Ranks 11+ got a nine-line window instead of a full body.

**Measured: 0.880 normal, 0.900 hard, 2,904 and 2,752 tokens — identical recall
to 2.18.0, tokens within noise.** The premise was stale: by 2.18.0 the median
missed rank was **1**, not 40. Reverted in 2.20.0.

The lesson is about which diagnosis an iteration is built on. 2.14.0's number was
correct when it was written and had been obsolete for two versions before I reused
it. A diagnosis is evidence with a timestamp, not a standing fact.

Also in this version: CI now executes the install command the README tells people
to use (`pip install "git+https://github.com/<repo>.git@<sha>"`) from outside the
checkout, so the public path a stranger takes is the one that gets tested.

## 2.20.0 — cover the top file, not more files

At 2.18.0 the policy spent 2,903 of 4,000 tokens, and its 10 misses sat at median
rank **1**. Neither budget nor ranking was binding; coverage of the right file was.

Ranks 1–3 now get four, three and three enclosing blocks; ranks 4–10 get three.
Prediction recorded before measuring: normal recall above 0.880, hard above 0.900,
tokens rising to 3,200–3,600 and staying inside the budget.




## 2.20.0 — measured

0.890 normal, 0.900 hard, 2,938 and 2,776 tokens. One query gained over 2.18.0's
0.880 for about 35 more tokens; hard is unchanged. The diagnose still reports 10
misses at median rank 1, so covering more of the top file moved the smallest
possible amount — one answer — and the rest of those misses are somewhere else.

Kept: it is a gain, not a loss, and it spends idle budget rather than new budget.
But it is a one-query result and should not be described as a fix.

## 2.21.0 — `ctx next`, so a version builds the next one

The loop this project exists to be was only half real. Versions were *measured*,
and 2.19.0 was reverted on the measurement — that half works. But each new
version's change was still chosen from my memory of a diagnosis rather than from
the current version's own output, and 2.19.0 proves the cost of that: it was
built on 2.14.0's "median rank 40" after that number had been obsolete for two
versions.

`ctx next` closes it: it runs the same generated queries as the bench, keeps only
the misses, and prints each one as `needle`, `file:line`, the file's rank, and a
classification — never ranked, ranked below the top 10 and never reached, ranked
in the top 10 but the chosen blocks missed the line, or the line emitted and the
needle still absent. The next change starts from those lines.

No retrieval behaviour changed in this version, so recall must stay at 0.890 /
0.900. That is itself the check: a tooling version that moves the numbers is a
tooling version with a bug.



## 2.22.0 — `ctx next` found a flaw in the benchmark, not in retrieval

The first real run of 2.21.0's `ctx next`, on the same 100 hard queries, named
all 10 remaining misses:

| needle | where | rank | classification |
| --- | --- | --- | --- |
| `truncateReason` | `services/fusion.ts:688` | 16 | never reached |
| `chatCompletionSchema` | `routes/proxy.ts:793` | 96 | never reached |
| `klientdan` | `README.uz.md:145` | 1 | blocks missed the line |
| `zincirler` | `README.tr.md:160` | 1 | blocks missed the line |
| `greetings` | `codex-base-instructions.ts:12` | 1 | blocks missed the line |
| `qismidan` | `README.uz.md:175` | 1 | blocks missed the line |
| `tiriyorsan` | `README.tr.md:525` | 1 | blocks missed the line |
| `tombstone_source` | `routes/fallback.ts:169` | 7 | blocks missed the line |
| `recapping` | `codex-base-instructions.ts:12` | 1 | blocks missed the line |
| `kuyruklu` | `README.tr.md:157` | 1 | blocks missed the line |

Recounting them exactly: **five** are Uzbek and Turkish words from translated
READMEs, **two** are English words inside a prose prompt file
(`codex-base-instructions.ts:12`), and **three** are real code identifiers —
`truncateReason`, `chatCompletionSchema`, `tombstone_source`.

(The first version of this table said "six from READMEs, two more, two code".
That was a miscount — 5 + 2 + 3 — written from memory of the list instead of from
the list. Corrected here rather than silently.)

`auto_queries` builds needles from identifiers in *every* text file, and `.md` is
in the corpus. A word that appears once in a translated README therefore qualifies
as a "rare identifier", even though no one would query a codebase for it. The
benchmark was scoring prose recall and calling it code retrieval.

`ctx bench --code-only` chooses needles from code files only; the corpus is
unchanged, so a real question about a README is still answerable. Both rates are
reported, because dropping hard cases quietly is how a benchmark flatters itself —
the exact thing this project exists to argue against.

The honest consequence: the headline 0.900 may be measuring six queries that were
never code questions. The code-only rate is the one to trust for the tool's stated
purpose, and it is measured in CI alongside the old one rather than replacing it.



## 2.22.0 — measured, code-only

The prediction was that code-only recall would beat 0.900. It measured **0.940 at
3,563 tokens**, against 0.900 at 2,776 with prose needles included. Normal (rare≤2)
0.890 / 2,938; hard 0.900 / 2,776; `lean` 0.740 and 0.770. So the prose needles were
noise for this tool's stated purpose — and excluding them from question generation
costs ~790 tokens, so it is not a free lunch either.

The six remaining misses, each blaming a different part of the pipeline:

| needle | rank | blames |
| --- | --- | --- |
| `ensureApiKeysBaseUrlColumn` | 130 | ranking |
| `firstNumber` | 37 | ranking |
| `maxMb` | 13 | ranking |
| `heuristicallyExhausted` | 10 | depth |
| `informed` | 1 | block selection |
| `complexity` | 1 | block selection |

Four of six are ranking failures. Whatever else is true, emission is no longer the
binding constraint and the next intelligence change belongs in `rank`.

## 2.23.0 — measured, and it broke its own budget

| | recall | tokens | over budget |
| --- | --- | --- | --- |
| normal | 0.890 | 3,196 | 15/100 |
| hard | 0.910 | 2,934 | 14/100 |
| hard, code-only | 0.940 | 3,698 | 22/100 |

Recall moved by one query on the hard set and not at all elsewhere — inside the
interval, so not a result. `lean` moved the same way and overshot the same way
(5/6/10 of 100).

**The regression.** `intelligence` exceeded its own budget on 14–22% of queries, so
the bench's "best within budget" line no longer contained it and nominated
`read_all` — a 1.9M-token corpus dump — as the winner. A policy that can win by
failing its own budget check is precisely the failure mode this project exists to
criticise, and I introduced it here.

Cause: the gate charged each block a *floored* token count against `budget - 24`.
Each floor loses up to one token, the `\n\n` separators between blocks were never
counted at all, and a 24-token reserve is smaller than that loss once more than about
ten blocks fit — which is exactly what per-block chunks caused. 2.24.0 counts
characters and converts once.

**The finding that mattered.** `ctx next` reclassified 7 of the 9 hard misses as
"the line was emitted, and the needle sits past its 200-character cut". The blocks had
been right for several versions; the per-line cap was discarding the word. Every
earlier theory about block selection was chasing the wrong phase.

## 2.24.0 — the line cap, and accounting that cannot drift

Two fixes from 2.23.0's own instrument, and one methodological change:

- **`clip_line` keeps the word, not the head of the line.** A long line is shortened
  *around the earliest query word* instead of at column 200. Seven of nine hard
  misses were that cut. Cap raised 200 → 240 characters, with `…` marking each cut.
- **Budget accounting in characters.** The gate and `render_context` compute the same
  expression, so a policy cannot report a size it did not emit. `over` should return
  to 0 on every row.
- **Wilson intervals in the bench.** At 100 queries one query is worth 0.010 recall,
  and this project twice called a single query a result. The interval now prints
  beside recall, so a one-query change is visibly inside it.
- **`.gitignore` anchored patterns actually match.** `/build` was tested as
  `str(rel).startswith("/build")`, which no relative path matches; every anchored
  pattern was silently a no-op.
- **The loop is enforced in CI.** Each run downloads the published 2.22.0 file and
  runs its `next` on the current checkout, so "this version was built from the last
  one's misses" is checkable rather than claimed.

Not changed, on purpose: `rank`. Four of the six remaining code-only misses are still
ranking failures at ranks 10–130, and that change has to be measured on its own.




## 2.24.0 — measured

| set | recall | tokens | over |
| --- | --- | --- | --- |
| normal | 0.930 | 3,212 | – |
| hard | 0.980 | 2,945 | – |
| hard, code-only | 0.960 | 3,698 | – |

No row over budget, which was 2.23.0's regression. The truncation theory held:
clipping around the earliest query word instead of at the head of the line
recovered the answers that sat past column 200.

**Corrected here:** the previous entry described 0.960 as the hard figure. It is
the code-only one; default hard is 0.980.

## 2.25.0 — a lookup is not a topic

`next` at 2.24.0 left four code-only misses, three of them "never reached" at
ranks 13, 37 and 130. Ranking, not emission, put them there: an identifier query
splits into common words, and a file repeating one of those words beats the file
that contains the identifier.

A single-identifier query is now a lookup: files containing that exact identifier
outrank files containing only its parts, whatever the part counts say. Sentence
queries keep the ×3 verbatim multiplier.

Prediction recorded before measuring: code-only hard recall from 0.960 toward
0.99, the three needles at the top of the ranking, other rates up, tokens roughly
flat.



## 2.25.0 — measured

| set | recall | tokens | over |
| --- | --- | --- | --- |
| normal | 0.940 | 3,212 | – |
| hard | 1.000 | 2,945 | – |
| hard, code-only | 1.000 | 3,698 | – |

`next`: 0 misses on both sets. The lookup tier took code-only hard from 0.960 to
1.000 and moved the three "never reached" needles to the top, at exactly the same
token cost (3,212 before and after) — the whole remaining gap was ranking
position, not budget or block selection.

Caveat worth keeping: the generated queries are identifiers, so 1.000 says every
single-identifier lookup on this corpus is answered. The mixed set's 0.940 is the
honest headline.

## 2.26.0 — the interval that never moved, and a suite a weaker model can fail

**Bug fixed.** The 95% interval printed identically for recall 1.000 and 0.940 —
`(0.002-0.054)` every row. The call site passed a proportion where `wilson`
expects a success count, so it divided by the query total twice and centred the
interval near 0.009. The guard against calling a one-query change a result had
never actually worked. The selftest now pins 94/100, 100/100 and 0/100.

**Added.** `eval/tasks.json` and `eval/score.py`: ten hand-written questions over
a six-file fixture corpus, scored against *the ranges a model actually read*, with
`ctx` scored on the same tasks for comparison. `SKILL.md` Mode 4 states the four
failure modes observed in this project — miscounting your own output, quoting a
number before measuring, asserting a bug that is not there, shipping a check that
never fires — each with the check that catches it.

**Not claimed.** No weaker model has been run against the suite. The suite makes
the claim testable; it does not make it true.



## 2.27.0 — the check has to be mechanical

The model that built 2.22.0–2.26.0 is the weaker one, switched in when the
stronger model ran out of usage. So Mode 4 was written by its own target audience,
and this session is the first subject. Scored against Mode 4's own four failure
modes:

| Failure | Count | Example |
| --- | --- | --- |
| Miscounted its own output | 1 | "6+2+2" for a list that was 5+2+3 |
| Quoted a number before measuring | 1 | 0.960 called hard recall; it was code-only |
| Asserted a bug that was not there | 1 | `too_big` units, which were consistent |
| Shipped a check that never fired | 1 | wilson call site, wrong for several versions |
| Over-specified a test | 1 | `hi == 1.0` on 0.999999 |

Five in one session. Two were caught by read-back, one by CI, one by the user
asking a question, one by noticing two rows differed. Only the last kind is
unreliable, and it is the kind that mattered most.

**Change.** `brackets(interval, value)` — an interval must contain the value it
describes — enforced in the selftest over eight proportions, and in `ctx bench` on
every printed row, where a violation exits 1 and refuses to summarise the table.

**Not claimed.** N = 1, self-scored, on tasks this model wrote. Exact counts of an
anecdote, not a benchmark.



## 2.28.0 — the rule where it is loaded

Mode 4's failure table was written into `SKILL.md`, which is read only when
someone pastes the URL. The README is preloaded into every chat and had none of
it — so the checks for the failures observed in this project were filed where they
would not be loaded.

Promoted one rule under the PROTOCOL.md test (real failure, checkable, no bench
regression):

> **Every number carries its command.** Quote the command and its output, or say
> you have not measured it. Recount from the printed list, never from memory.

It covers both the unmeasured claim (0.960 called hard recall) and the miscount
(5+2+3 read as 6+2+2) because they are the same defect: a figure with nothing
behind it. Cost: ~50 tokens in every chat, which is the honest price of a
preloaded rule.

Two failures stay out of the README on purpose — the false bug report is already
covered by "never trust a symbol you have not seen defined", and the check that
never fired is now enforced by `brackets()` in code, so it does not also need
prose.



## 2.29.0 — the last blind measurements

Three questions had no answer from the product before this version, and each is
now a flag that CI runs:

| Flag | The question it answers |
| --- | --- |
| `--sweep 1000,2000,3000,4000` | What is the smallest budget that holds recall? |
| `--ablate` | Which phases cost tokens without buying recall? |
| `--queries <file>` | Does it work on questions, or only on symbol lookups? |

Plus one CI fix: `ctx next` now runs on the **default** (rare≤2) set. It had only
ever run with `--rare 1`, so the mixed set's 6 misses were invisible while hard
and code-only reported zero.

The knee is defined as the smallest budget with the same **hit count** as the
largest budget — not "within the interval", because a one-query difference is
exactly what the interval says is not a result. `knee_budget()` is a pure
function with three selftest cases, so the definition cannot drift.

The measurement loop moved into `bench_rows(corpus, queries, budget, phases)`, so
the single-budget table, the sweep and the ablation all run the same code. That
is the same one-implementation argument that retires the research harness next.

**Prediction recorded before measuring:** the knee is below 4,000 on the mixed
set; at least one phase shows a delta inside the interval and should be dropped;
the default-set misses are a different shape from the hard set's.
