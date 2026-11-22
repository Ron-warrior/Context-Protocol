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

- **Outlines first always beat windows first** on files ranked 1–3, because you
  cannot choose a window without knowing which declaration you are aiming at.
- **A two-strike stop rule cuts tokens more than better ranking does.** Ranking
  improves the hit rate; stopping bounds the misses. The bound may be worth more.
- **Persisted notes beat a rebuilt index** for any repo smaller than ~50k LOC,
  because re-derivation is cheap there and index staleness is not.
- **Cross-file rename is where text-level tools lose hardest**, which is the one
  case where an LSP-backed tool (Serena) would pay for its install cost outright.
- **The trace says the expensive part is authoring, not retrieving.** 824 lines
  authored, 202 read back, then 3 defects in the part never read. So the ladder is
  missing a rung on the write side: author in small verified units — write a
  function, read it back, then write the next — instead of writing one large file
  and hoping. Untested prediction: it cuts defects found per 1k authored lines far
  more than any retrieval improvement would.

