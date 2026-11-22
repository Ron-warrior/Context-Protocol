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
python3 eval/retrieval_bench.py .                    # auto-generate queries from rare identifiers
python3 eval/retrieval_bench.py . --budget 4000      # tighter budget
python3 eval/retrieval_bench.py . --queries q.json   # your own questions
python3 eval/retrieval_bench.py . --stop             # stopping rules, ranking held fixed
python3 eval/retrieval_bench.py --selftest           # prove the harness, then trust it
```

Policies compared, in one pass, at the same budget:

1. `read_all` — every source file whole (what graphify's 71.5x is measured against)
2. `grep_files` — whole files containing a keyword
3. `pagerank_map` — signature outline ranked by personalized PageRank over the
   import graph (the aider repo-map idea)
4. `ladder` — this protocol: rank → outline under 40% of budget → scoped windows

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

Corpus: freellmapi, 795 files, **100 queries**, budget 4000 tokens. Real emission.

**Normal** — needles that appear in at most two files:

| policy | recall | tokens | over budget | ms |
| --- | --- | --- | --- | --- |
| read_all | 1.000 | 1,960,580 | 100/100 | 59.6 |
| grep | 0.990 | 736,338 | 95/100 | 75.1 |
| **intelligence** | **0.720** | **2,876** | – | 78.4 |
| lean (`--lean`) | 0.640 | 2,621 | – | 113.1 |

**Hard** — needles that exist in exactly one file, so there is no second chance:

| policy | recall | tokens | over budget |
| --- | --- | --- | --- |
| grep | 1.000 | 704,380 | 92/100 |
| read_all | 1.000 | 1,960,580 | 100/100 |
| **intelligence** | **0.750** | **2,748** | – |
| lean | 0.650 | 2,503 | – |

### The fix that moved it

2.14.0 replaced the arbitrary rank-10 cut with "keep emitting bodies until 85% of
the budget is spent". Measured effect on the same 100 hard queries:

| | before 2.14.0 | after |
| --- | --- | --- |
| normal | 0.720 | **0.790** |
| hard | 0.710 | **0.750** |
| margin over lean | +0.08 / +0.07 | **+0.150 / +0.100** |

The diagnosis was "29 of 29 misses were ranked but not emitted, with 30% of the
budget unspent". The fix used the budget. Recall rose by 7 points; the margin over
the token-first baseline more than doubled. That is the loop working as designed:
measure where the failure is, fix that, measure again.

25 misses remain, still all "ranked but not emitted", so budget was not the whole
story — 2.15.0's diagnose reports the *rank position* of each missed file to
separate a phase bug from a cutoff.

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

Every number above was produced by a harness whose output nothing in the loop
could read. Green jobs print to a run page; the iteration happens in a chat. So
the measurement existed and the feedback did not.

`ctx bench --floor <recall>` closes that: recall below the floor exits 1 and
prints the table and the shortfall on stderr, which *is* readable. CI runs the
self-bench at 0.75 against a measured 0.790, and every bench table now also lands
in the job summary.

Consequence for this file: a green CI run is now evidence of a floor, not of a
number, and a red one is how a number arrives. Recall is no longer allowed to
move down silently between versions.

Two documentation stamps were found stale while wiring it — `pyproject.toml` at
2.0.0 for 17 releases, `SKILL.md` describing the pre-2.14.0 emission order. Both
are fixed, and the drift check now compares all three files that carry the
version.

**Unmeasured as of this entry:** the recall effect of 2.16.0 and 2.17.0. The floor
was added precisely because those two versions were shipped without a readable
result.
