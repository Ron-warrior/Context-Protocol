# Findings: what is actually more effective than graphify, and why

**Why this project exists.** To replace graphify with something measurably better —
judged on answers per token, not tokens alone. That difference is not a matter of
taste: it is visible in graphify's own benchmark source, below.

Short version: **graphify's real invention is the cheap, deterministic map. Its
weakness is that it stops there.** It builds a graph and hands you a browser; it
never spends the graph on the one thing that decides effectiveness — choosing
which tokens go into the next turn under a budget. That ranking step is where the
state of the art is better, and it is the step this project's protocol takes.

## What graphify is

A `/graphify` skill (Claude Code, Cursor, Codex, Gemini, ~20 more) that turns a
folder into a knowledge graph: tree-sitter AST for ~40 languages, no LLM for
code, Leiden communities, every edge tagged `EXTRACTED` / `INFERRED` /
`AMBIGUOUS`, `graph.json` + `graph.html` + `GRAPH_REPORT.md`, then `query` /
`path` / `explain` against it, plus an MCP server and git hooks.

Genuinely good, and worth keeping:

- **Deterministic code parsing.** No embeddings, no vector store, no drift. A file
  parses the same way twice, offline, for free.
- **Explained edges.** `EXTRACTED` vs `INFERRED` is the right answer to "the graph
  is wrong sometimes" — it tells you which edges you may trust.
- **A shared artifact.** The graph is a file your team and your agents can both
  read, versionable in git.
- **Multimodal ingestion.** PDFs, images, video into the same graph.

## Where it loses

1. **The 71.5x is measured against a strawman.** The baseline is "reading the raw
   files" — a 52-file mixed corpus read whole. No competent agent does that; it
   greps, then reads three files. Against an agent that already maps before it
   reads, the multiplier collapses toward the low single digits. Token savings
   measured against the worst possible baseline flatter the method.
2. **Retrieval quality has a hard ceiling.** Self-reported LOCOMO (n=300):
   graphify `recall@10 = 0.497`. Under half of relevant items surface in the top
   ten. For a *reading* tool that is fine. For an agent whose correctness depends
   on not missing the one relevant fact, 0.497 is a coin flip on the edge cases.
3. **It loses on answers to a system with no graph at all.** Same table: QA
   accuracy 45.3% for graphify vs 49.7% for supermemory, 27.3% for mem0. The graph
   wins retrieval and loses answering — i.e. the graph is not where the accuracy
   is.
4. **The graph is static and query-agnostic.** Communities are computed once per
   build and mostly reflect *the corpus*, not *your question*. You pay for the
   whole structure and then grep it. Nothing in it is conditioned on the task at
   hand or on the token budget you have left.
5. **Install cost and staleness.** Python 3.11.5+, uv/pipx, a rebuild step, hooks.
   Anything that can go stale gets trusted after it is stale.

## The four real upgrades, ranked

### 1. Rank under a budget, don't just index — aider's repo map

Aider sends a map of the repo (files + signatures + the lines that define them)
and chooses what to include with a **graph ranking algorithm over a file
dependency graph, optimized to fit an active token budget** — 1k tokens by
default, widened only when the chat has no files attached yet.

Why this beats a static community graph: it is *query- and state-conditioned* and
it is *budget-first*. Instead of "here is everything, go look", it answers "given
~1,000 tokens and this conversation, which declarations are most likely needed".
That is exactly the utility-per-token optimisation graphify omits. Same input
(AST + dependency edges), better use of it.

Cheap to imitate without any install: rank candidate files by definition hits,
import proximity and size, then emit signatures only. That is rung 3 of the
ladder.

### 2. Get precise instead of getting big — Serena (LSP, symbol level)

Serena exposes IDE-grade semantic tools over MCP: `find_symbol`, symbol overview,
`find_referencing_symbols`, rename, symbol-scoped edits, diagnostics.

- **Pro:** acts on symbols, not line numbers or text patterns — so a cross-file
  rename is one atomic call instead of 8–12 read/edit/verify steps. Symbol-scoped
  edits are far less token-hungry and far less error-prone than search-and-replace.
  Its own agent-run evaluation has Opus/GPT agents independently calling it the
  most impactful addition to their toolkit on large codebases.
- **Con:** needs a language server per language and a **local process** behind it
  (stdio, or HTTP served from your own machine), so it cannot be installed from
  this app, which only reaches remote MCP servers over https. GPL-3.0.
- **Takeaway to steal:** precision beats coverage. A tool that returns the one
  referrer list is worth more than a graph you have to traverse to find it.

### 3. Just-in-time retrieval beats pre-indexing, for code — Anthropic's own position

Their context-engineering guidance is explicit: agents should keep lightweight
identifiers (paths, queries, links) and load data *at runtime* with tools, using a
hybrid — a small always-on instruction file, plus `glob`/`grep` for everything
else — "effectively bypassing the issues of stale indexing and complex syntax
trees".

That is a direct argument against pre-building a structure you then trust. It is
also why this protocol is a ladder of local operations rather than a build step:
nothing to install, nothing to go stale, correctness tied to the files as they
are right now.

Same document supplies the rest of the discipline: **compaction** (summarise, keep
the decisions and the open bugs, drop raw tool output), **structured note-taking**
(persist outside the context window; a `NOTES.md` is a memory system), and
**sub-agents** (explore wide in a clean context, return 1–2k tokens). Persisting
notes is rung 6 for exactly this reason.

### 4. The thing nobody sells: a stop rule

Every tool above optimises *finding*. None optimises *stopping*. The failure mode
that actually burns an agent's context is not a bad index — it is the fourth and
fifth hopeful read after the first two missed. A stated budget and a two-strike
rule are free, and worth more than most of the software in this document.

## Ranked verdict

| Approach | Mechanism | Wins on | Loses on | Verdict |
| --- | --- | --- | --- | --- |
| **Ranked map under budget** (aider) | tree-sitter + PageRank over deps + token budget | Utility per token; no server; 1k tokens default | No doc/semantic understanding; unverified edges | **Best single idea. Adopted as rungs 2–3.** |
| **Symbol-level retrieval** (Serena) | LSP symbols, referrers, atomic refactors | Precision; correctness of edits | Needs a local process; per-language servers; GPL | **Best idea you cannot install here. Adopted as rules 3–5.** |
| **Just-in-time + notes** (Anthropic) | grep/glob/read, compaction, NOTES, subagents | Never stale; zero install; cheap | No global view; slower; wanders without stop rules | **The substrate. Adopted as rungs 0–1 and 6.** |
| **graphify** | AST + Leiden communities + static graph | Deterministic, free, explained, shareable, multimodal | Static, query-agnostic, `recall@10 0.497`, loses QA to supermemory | **Keep as the map layer, not the retrieval layer.** |
| **Vector RAG / mem0 / supermemory** | embeddings over chunks | Recall of fuzzy facts (`0.149` / `0.048` @10) | Structure and exactness; chunk boundaries; staleness | **Worst fit for code. Skip.** |

## Measured since this document was written

Every number above is someone else's self-report. The bench (`eval/retrieval_bench.py`)
now measures the claims on a real repository (freellmapi, 795 files, 25
rare-identifier auto queries, CI run 45074848996), and two verdicts gained nuance:

**The repo-map idea, measured.** `pagerank_map` is this project's implementation
of the aider claim — signature outlines ranked by personalized PageRank over the
import graph, nothing else. Recall per 1k tokens:

| policy | 1,000 | 4,000 | 16,000 |
| --- | --- | --- | --- |
| read_all | 0.000 | 0.000 | 0.003 |
| grep_files | 0.000 | 0.108 | 0.040 |
| pagerank_map | 0.121 | 0.070 | 0.023 |
| **ladder** (map + scoped windows) | **0.567** | **0.213** | **0.058** |

- On seven files the map ranked *worst*, below grep — an artifact of a corpus
  with almost no import edges. On the real corpus it recovers at 1k (0.121 vs
  grep's 0.000), which is the first evidence that PageRank over dependencies
  buys anything at all. The "best single idea" verdict stands, narrowed: **the
  map narrows the search, the scoped windows win it.** Map alone loses to the
  full ladder at every budget, 4.7x at 1k.
- The stop-rule experiment measured the other half of finding 4. Chunk-level
  reads, ranking fixed (run 45075205417): `until_found` answers 68% of queries
  at 2,404 tokens; `two_strike` answers 16% at 817. **Quitting early is
  expensive in answers, not cheap** — 0.197 answers per 1k against 0.283. The
  two-strike rule survives only in its original form: two misses mean *change
  rung* (search for the definition, not the usage), not *give up*.

Both results are one corpus and one query shape (rare identifiers). They are
the first measured evidence in this document, not the last word.

## The composition nobody ships

graphify's extracted edges are precisely the input a PageRank needs. It builds the
graph; nothing in it applies the ranking. That is the whole gap:

> **A knowledge graph is a data structure. It becomes effective only when a
> ranking function spends it against a token budget, per query.**

So the correct use of graphify is not `/graphify` then browse. It is: extract
once, then rank with the current question, take the top of the map under budget,
descend into exactly those bodies, persist what you learned. Which is what this
project does, with no install and no rebuild.

## Sources

- graphify — repo, README, self-reported benchmarks: `github.com/Graphify-Labs/graphify`
- aider repository map (PageRank + token budget): `aider.chat/docs/repomap.html`
- Serena — LSP-backed semantic retrieval over MCP: `github.com/oraios/serena`
- Anthropic, *Effective context engineering for AI agents* — just-in-time
  retrieval, compaction, note-taking, sub-agents: `anthropic.com/engineering/effective-context-engineering-for-ai-agents`


## The 71.5x, read from source

Cloned `Graphify-Labs/graphify` at `3671f31` (release v0.9.115) and read
`graphify/benchmark.py`. The headline token-reduction number is computed like this:

```python
# graphify/benchmark.py:75-79
if corpus_words is None:
    # Rough estimate: each node label is ~3 words, plus source context
    corpus_words = G.number_of_nodes() * 50

corpus_tokens = corpus_words * 100 // 75  # words → tokens
```

and then, at line 92:

```python
reduction_ratio = round(corpus_tokens / avg_query_tokens, 1)
```

So "71.5x fewer tokens per query" is:

> *(node count × 50 × 4/3)* ÷ *the token count of `query_graph`'s own output*

The numerator is an **estimate invented from the graph's node count**, not the
measured size of the corpus. The denominator is the tool's own output. Two numbers
from the same artifact, divided.

**And nothing in the file checks whether the answer is in that output.** The only
filter is `if qt > 0` — non-empty. A query that returns four hundred confident
tokens of the wrong nodes scores exactly as well as one that returns the answer.

That is the flaw this project is built against:

> **A tiny answer that is wrong is not efficient. It is cheap.**

Compression is a property of the output. Effectiveness is whether the output
contains what was asked for. graphify measures the first and reports it as if it
were the second — and the baseline it beats is itself an estimate, so neither side
of the ratio is a measurement of retrieval.

### What we measure instead

`eval/retrieval_bench.py` scores **needle recall per 1k tokens**: does the returned
context contain the fact that decides the question, per token spent. That metric can
*disagree* with compression — a policy can win on tokens and lose on recall — which
is exactly what makes it useful.

`eval/compare_graphify.py` applies the same metric to graphify's real
`query_graph` output, on the same corpus and the same needles. No estimation, no
proxy: the number graphify's own benchmark cannot produce, computed against the
thing it actually returns.

### What would falsify us

If graphify's query output beats the ladder on recall per 1k on the corpus, then the
claim in this file is wrong and the protocol loses honestly. The comparison script
prints both; it does not assume which wins.


## The head-to-head, measured

Same corpus (freellmapi, 795 files), same question generator (identifiers appearing
in at most two files), same needles. graphify 0.9.115 built its own graph:
**6,260 nodes, 19,435 edges, 209 communities**, from 782 code files, in its own
pipeline. Then each tool was scored on the same metric — is the answer in what it
returned, per token spent.

| tool | recall | tokens | recall per 1k |
| --- | --- | --- | --- |
| graphify `query` | **0.320** | 2,269 | 0.141 |
| `ctx` (intelligence-first) | **0.720** | 2,876 | 0.250 |

**`ctx` retrieves 2.25x as many answers for 27% more tokens.** On the same run,
**13 of 25 graphify queries returned no matching nodes at all** — 52% of questions
answered with nothing.

That last number is the important one, not the ratio. The needles were
*identifiers*: `keylessDecisionProvider`, `normalizeGroupLabel`. A keyword-seeded
BFS over a 6,260-node graph is being asked to find a node whose name it was handed.
That is graphify's home turf, and it returns nothing more than half the time.

### And the claim it publishes

graphify's own benchmark on this corpus, from the same run:

```
Corpus: 313,000 words -> ~417,333 tokens (naive)
Graph:  6,260 nodes, 19,435 edges
Avg query cost: ~1,618 tokens
Reduction: 257.9x fewer tokens per query
```

257.9x. Against a corpus size **estimated as `node_count * 50` words** (see
`graphify/benchmark.py:77`), divided by the size of its own output, with no check
that the answer is in it. A query that returns `"No matching nodes found."` scores
a perfect 257.9x reduction, because an empty answer is maximally compressed.

That is the whole argument, in one pair of numbers: **257.9x compression, 32%
recall.** The compression was never the thing that mattered.

### Caveats, stated

- 25 queries, one corpus, auto-generated questions. Directional, not settled.
- `ctx` used 27% more tokens. Under intelligence-first that is the correct trade;
  under a pure compression metric graphify wins by construction.
- graphify was run `--code-only` with `GRAPHIFY_BACKEND=none`, which is its
  documented offline path. The semantic pass over docs would not help it find a
  code identifier.
- Both tools were scored by *my* metric. That is a real bias, which is why the
  metric is published above and the harness (`eval/compare_graphify.py`) is in the
  repo for anyone to run differently.
