#!/usr/bin/env python3
"""Head-to-head: graphify's query output vs this protocol's ladder, same needles.

graphify's own benchmark (graphify/benchmark.py) measures one thing: the size of
what `query_graph` returns, divided by an *estimated* corpus size
(`number_of_nodes() * 50` words). It never checks whether the returned text
contains the answer.

A tiny answer that is wrong is not efficient. It is cheap.

This script scores graphify's real query output the same way the ladder is
scored: needle recall, and recall per 1k tokens. Same questions, same needles,
same corpus. Requires graphify to be installed; exits 0 with a note if it is
not, so it never breaks a run that only has the ladder.

Usage
    python3 eval/compare_graphify.py <corpus> <graph_json> [--queries 25]
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
import ctx  # noqa: E402


def main(argv: list[str]) -> int:
    parser = argparse.ArgumentParser(description="Score graphify query output on recall per token.")
    parser.add_argument("corpus", help="repository the graph was built from")
    parser.add_argument("graph_json", help="graphify's graph.json")
    parser.add_argument("--queries", type=int, default=25, help="how many auto queries")
    parser.add_argument("--budget", type=int, default=4000, help="token budget per query")
    parser.add_argument("--seed", type=int, default=0)
    args = parser.parse_args(argv)

    try:
        from graphify.serve import _query_graph_text, _read_graph
    except ImportError as exc:
        print(f"graphify not importable ({exc}); skipping the head-to-head", file=sys.stderr)
        return 0

    graph_path = Path(args.graph_json)
    if not graph_path.exists():
        print(f"no graph at {graph_path}", file=sys.stderr)
        return 2

    files = ctx.load(Path(args.corpus))
    if not files:
        print(f"no source files under {args.corpus}", file=sys.stderr)
        return 1

    queries = ctx.auto_queries(files, args.queries, args.seed)
    if not queries:
        print("no queries generated", file=sys.stderr)
        return 1

    graph = _read_graph(str(graph_path))

    recall_total = 0.0
    tokens_total = 0
    empty = 0
    for query in queries:
        needles = query.get("needles", [])
        question = " ".join(needles) or query.get("question", "")
        text = _query_graph_text(graph, question, mode="bfs", depth=3, token_budget=args.budget)
        if not text or text == "No matching nodes found.":
            empty += 1
            text = ""
        recall_total += ctx.recall_of(text, needles)
        tokens_total += ctx.tokens(text) if text else 0

    count = len(queries)
    mean_recall = recall_total / count
    mean_tokens = tokens_total / count
    per_1k = (mean_recall / (mean_tokens / 1000.0)) if mean_tokens else 0.0

    print(f"corpus: {args.corpus}  files: {len(files)}  queries: {count}")
    print(f"graphify graph: {graph.number_of_nodes()} nodes, {graph.number_of_edges()} edges")
    print()
    print("| policy | recall | tokens | recall/1k |")
    print("| --- | --- | --- | --- |")
    print(f"| graphify query | {mean_recall:.3f} | {mean_tokens:.0f} | {per_1k:.3f} |")
    if empty:
        print(f"\n{empty}/{count} queries returned no matching nodes at all")
    print("\nFor the same corpus the ladder's numbers come from `ctx bench --sweep`.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
