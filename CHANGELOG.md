# Changelog

Three eras, three arguments. The detail lives in `TRACE.md` (why each version
exists, what it measured, what it got wrong) and `SCOREBOARD.md` (the numbers,
per version). This file is the map.

## 3.x — a finished product

The version number stops describing a research project and starts describing a
tool. What that means concretely:

- **One engine.** `eval/retrieval_bench.py` is gone. It carried a second
  retrieval implementation, so its numbers described something nobody could
  install. Sweep, ablation and question-file measurement are `ctx bench` flags.
- **Everything measured is measured by the product.** A hand-written question set
  (`eval/tasks.json`) and a scorer (`eval/score.py`) sit beside the generated
  identifier queries, because a lookup benchmark cannot see the phases that
  answer "how does X work".
- **The default budget follows the evidence**, not the habit. The 2.29.0 sweep
  put the knee at 1,000 tokens against a 4,000 default.
- **The root README is within its own stated budget** (under ~100 lines), which
  `PROTOCOL.md` has required since 1.0.0 and the file had drifted past.
- **3.0.1 — `complete` became the metric**, so a context holding two of three
  facts is scored as the unanswerable context it is rather than as an average.
- **3.0.2 — the empty repository** says which failure it is: a missing path, or a
  project with no code yet, where the useful rungs are 0, 5, 6 and 7.
- **3.1.0 — the declarative half.** HTML, CSS, XML and Gradle files are now part
  of the corpus. A clean-room JS rewrite's entry point, an Android manifest and
  a Gradle build rule were previously invisible to every command.

## 2.x — measurement

Fifteen minor versions spent turning claims into numbers, and repeatedly finding
that the number was measuring the wrong thing.

- **2.1.0–2.13.0** — the harness. Policies, stop rules, ablations, sweeps.
- **2.14.0** — emission spends the budget instead of stopping at an arbitrary
  rank. Recall 0.720 → 0.790.
- **2.16.0–2.17.0** — the phrase boost and top-file coverage. 0.790 → 0.880.
- **2.18.0** — `--floor`, so a regression fails the build instead of passing
  silently. Also the version where the log turned out to be readable on a
  passing job, which corrected the premise it was built on.
- **2.19.0 — reverted.** Built on a diagnosis two versions out of date; measured
  0.880 → 0.880 and bought nothing.
- **2.20.0–2.22.0** — coverage of the top file, then the discovery that 5 of 10
  remaining "misses" were translated-README prose. `--code-only` split the
  measurement in two rather than deleting the hard cases.
- **2.23.0–2.25.0** — one index owner, working call sites, cost that equals the
  emitted cost, clipping around the query word, and a lookup tier that took
  hard code-only recall from 0.960 to 1.000.
- **2.26.0–2.27.0** — the wilson interval that had never worked, and the
  invariant that catches it: an interval must contain the value it describes.
- **2.28.0–2.30.0** — the rule promoted to the always-loaded file, the last blind
  measurements, and the harness retired.

## 1.x — the rules

Where the ladder came from: a ranked synthesis of aider's repo map, Serena,
Anthropic's context engineering and graphify's own benchmarks, then three
corrections the rules made to themselves.

- **1.0.0** — ladder, hard rules, stop rules, persist.
- **1.1.0** — rung 5 rewritten from a time rule to a state rule, after the
  protocol's own read-back requirement caught 441 lines shipped unread.
- **1.2.0** — rung 5 *Write* added: author in units small enough to check.
- **1.3.0–1.13.0** — the bench grew its own version track; a protocol bump needs
  a rule that changed, and none did.
