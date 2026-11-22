#!/usr/bin/env python3
"""Measure context-selection policies instead of arguing about them.

Four ways an agent can decide what to put in front of the model, at one fixed
token budget, scored on whether the deciding fact actually reached the context.

Policies
    read_all      every source file, whole. The baseline that "71.5x fewer
                  tokens" is measured against.
    grep_files    whole files whose text contains a query keyword.
    pagerank_map  signature outline of all files, ranked by personalized
                  PageRank over the import graph (the aider repo-map idea).
    ladder        this project's protocol: rank, outline under 40% of the
                  budget, then scoped windows around keyword hits.

Metrics
    recall              fraction of needles present in the assembled context
    tokens              estimated tokens (chars / 4)
    recall_per_1k       recall / (tokens / 1000) -- effectiveness, per README

Usage
    python3 eval/retrieval_bench.py .
    python3 eval/retrieval_bench.py . --budget 4000 --auto 30
    python3 eval/retrieval_bench.py . --queries q.json

Queries file:
    [{"question": "where is the token refreshed", "needles": ["refresh_token"]}]

Auto mode picks rare identifiers (present in at most two files), which is the
shape of a real lookup: the fact exists in few places and the agent has to find
it without reading everything. Deterministic for a given --seed.

Nothing here needs a network, a model, or an API key.
"""

from __future__ import annotations

import argparse
import json
import random
import re
import sys
from dataclasses import dataclass, field
from pathlib import Path

SKIP_DIRS = {
    ".git", "node_modules", "venv", ".venv", "dist", "build", "__pycache__",
    ".next", ".mypy_cache", ".pytest_cache", ".ruff_cache", "target", "vendor",
    "Pods", ".tox", ".idea", ".vscode", ".gradle", "bin", "obj", "coverage",
    "graphify-out", ".terraform", ".cache",
}

TEXT_EXT = {
    ".py", ".js", ".jsx", ".mjs", ".ts", ".tsx", ".go", ".rs", ".java", ".kt",
    ".rb", ".cs", ".php", ".swift", ".c", ".h", ".cc", ".cpp", ".hpp", ".m",
    ".mm", ".scala", ".sh", ".lua", ".ex", ".exs", ".erl", ".hs", ".ml",
    ".clj", ".sql", ".vue", ".svelte", ".dart", ".zig", ".md", ".rst", ".txt",
    ".toml", ".yaml", ".yml", ".json",
}

MAX_FILE_BYTES = 400_000
MAX_OUTLINE_LINES = 60

STOPWORDS = {
    "return", "import", "public", "private", "static", "string", "number",
    "object", "module", "exports", "default", "function", "const", "class",
    "value", "result", "error", "false", "true", "null", "undefined", "self",
}

OUTLINE_RE = re.compile(
    r"^\s*(?:export\s+|pub\s+|public\s+|private\s+|protected\s+|static\s+"
    r"|async\s+|final\s+|abstract\s+|open\s+|override\s+|internal\s+)*"
    r"(?:class|def|function|func|fn|interface|struct|enum|trait|impl|type"
    r"|const|record|module|namespace|object)\s+([A-Za-z_$][\w$]*)"
)

IMPORT_RES = [
    re.compile(r"^\s*import\s+([\w.]+)", re.MULTILINE),
    re.compile(r"^\s*from\s+([\w.]+)\s+import", re.MULTILINE),
    re.compile(r"""^\s*import\s+[^'"]*?from\s+['"]([^'"]+)['"]""", re.MULTILINE),
    re.compile(r"""require\(\s*['"]([^'"]+)['"]\s*\)"""),
    re.compile(r"^\s*using\s+([\w.]+)", re.MULTILINE),
    re.compile(r"^\s*uses\s+([\w:]+)", re.MULTILINE),
    re.compile(r"""^\s*#include\s*[<"]([^>"]+)[>"]""", re.MULTILINE),
]

IDENT_RE = re.compile(r"[A-Za-z_][A-Za-z0-9_]{5,}")
SPLIT_RE = re.compile(r"[_\W]+|(?<=[a-z])(?=[A-Z])")


@dataclass
class SourceFile:
    path: str
    text: str


@dataclass
class Corpus:
    files: list[SourceFile] = field(default_factory=list)
    edges: dict[str, set[str]] = field(default_factory=dict)
    outline: dict[str, list[str]] = field(default_factory=dict)
    stems: dict[str, list[str]] = field(default_factory=dict)


def estimate_tokens(text: str) -> int:
    """Rough but consistent: ~4 characters per token."""
    return max(1, len(text) // 4)


def load_corpus(root: Path) -> Corpus:
    corpus = Corpus()
    for path in sorted(root.rglob("*")):
        if not path.is_file():
            continue
        rel = path.relative_to(root)
        if any(part in SKIP_DIRS for part in rel.parts[:-1]):
            continue
        if path.suffix.lower() not in TEXT_EXT:
            continue
        try:
            if path.stat().st_size > MAX_FILE_BYTES:
                continue
            text = path.read_text(encoding="utf-8", errors="replace")
        except OSError:
            continue
        if not text.strip():
            continue
        corpus.files.append(SourceFile(str(rel), text))

    for source in corpus.files:
        key = Path(source.path).stem.lower()
        corpus.stems.setdefault(key, []).append(source.path)

    for source in corpus.files:
        targets: set[str] = set()
        for pattern in IMPORT_RES:
            for ref in pattern.findall(source.text):
                tail = re.split(r"[.:/\\]", ref.rstrip("/"))[-1]
                tail = Path(tail).stem.lower()
                if not tail or len(tail) < 2:
                    continue
                for candidate in corpus.stems.get(tail, ()):
                    if candidate != source.path:
                        targets.add(candidate)
        corpus.edges[source.path] = targets

    for source in corpus.files:
        lines = []
        for index, line in enumerate(source.text.splitlines()):
            if OUTLINE_RE.match(line):
                lines.append(f"{index + 1}: {line.strip()[:120]}")
                if len(lines) >= MAX_OUTLINE_LINES:
                    break
        corpus.outline[source.path] = lines

    return corpus


def personalize(corpus: Corpus, keywords: list[str]) -> dict[str, float]:
    """Query-conditioned prior: files that mention the question more, start higher."""
    weights: dict[str, float] = {}
    for source in corpus.files:
        low = source.text.lower()
        hits = sum(low.count(keyword) for keyword in keywords) if keywords else 0
        weights[source.path] = float(hits) + 1.0
    total = sum(weights.values()) or 1.0
    return {path: weight / total for path, weight in weights.items()}


def pagerank(
    corpus: Corpus,
    personal: dict[str, float],
    damping: float = 0.85,
    iterations: int = 20,
) -> dict[str, float]:
    nodes = [source.path for source in corpus.files]
    if not nodes:
        return {}
    known = set(nodes)
    outgoing = {
        node: [target for target in corpus.edges.get(node, ()) if target in known]
        for node in nodes
    }
    count = len(nodes)
    scores = {node: 1.0 / count for node in nodes}

    for _ in range(iterations):
        updated = {node: (1.0 - damping) * personal.get(node, 0.0) for node in nodes}
        dangling = 0.0
        for node in nodes:
            targets = outgoing[node]
            if not targets:
                dangling += scores[node]
                continue
            share = damping * scores[node] / len(targets)
            for target in targets:
                updated[target] += share
        spill = damping * dangling
        for node in nodes:
            updated[node] += spill * personal.get(node, 0.0)
        scores = updated

    return scores


def chunks_read_all(corpus: Corpus) -> list[tuple[str, str]]:
    return [(source.path, source.text) for source in corpus.files]


def chunks_grep(corpus: Corpus, keywords: list[str]) -> list[tuple[str, str]]:
    if not keywords:
        return []
    scored = []
    for source in corpus.files:
        low = source.text.lower()
        hits = sum(low.count(keyword) for keyword in keywords)
        if hits:
            scored.append((hits, source.path, source.text))
    scored.sort(key=lambda item: (-item[0], len(item[2])))
    return [(path, text) for _, path, text in scored]


def chunks_pagerank_map(
    corpus: Corpus, ranked: dict[str, float]
) -> list[tuple[str, str]]:
    ordered = sorted(corpus.files, key=lambda source: -ranked.get(source.path, 0.0))
    blocks = []
    for source in ordered:
        body = "\n".join(corpus.outline.get(source.path, []))
        if body:
            blocks.append((source.path, body))
    return blocks


def window_around(text: str, keywords: list[str], pad: int = 4, cap: int = 40) -> str:
    """Numbered windows around keyword hits, spans merged, capped in lines."""
    if not keywords:
        return ""
    lines = text.splitlines()
    hits = [i for i, line in enumerate(lines) if any(k in line.lower() for k in keywords)]
    if not hits:
        return ""

    spans: list[list[int]] = []
    for index in hits:
        low, high = max(0, index - pad), min(len(lines), index + pad + 1)
        if spans and low <= spans[-1][1]:
            spans[-1][1] = max(spans[-1][1], high)
        else:
            spans.append([low, high])

    out: list[str] = []
    for low, high in spans:
        for index in range(low, high):
            if len(out) >= cap:
                return "\n".join(out)
            out.append(f"{index + 1}: {lines[index][:200]}")
    return "\n".join(out)


def chunks_ladder(
    corpus: Corpus,
    ranked: dict[str, float],
    keywords: list[str],
    budget: int,
) -> list[tuple[str, str]]:
    """Rank -> outline within 40% of the budget -> scoped windows with the rest."""
    ordered = sorted(corpus.files, key=lambda source: -ranked.get(source.path, 0.0))
    heading_budget = max(1, int(budget * 0.4))
    used = 0
    chunks: list[tuple[str, str]] = []

    for source in ordered:
        body = "\n".join(corpus.outline.get(source.path, []))
        if not body:
            continue
        cost = estimate_tokens(body)
        # continue, not break: a large outline must not starve every smaller one
        if used + cost > heading_budget:
            continue
        chunks.append((source.path, body))
        used += cost

    for source in ordered:
        if used >= budget:
            break
        snippet = window_around(source.text, keywords)
        if not snippet:
            continue
        cost = estimate_tokens(snippet)
        if used + cost > budget:
            continue
        chunks.append((f"{source.path} (excerpt)", snippet))
        used += cost

    return chunks


def assemble(chunks: list[tuple[str, str]], budget: int) -> tuple[str, int]:
    """Strict budget: a chunk that does not fit is skipped, not truncated."""
    parts: list[str] = []
    used = 0
    for path, text in chunks:
        if not text.strip():
            continue
        cost = estimate_tokens(text)
        if used + cost > budget:
            continue
        parts.append(f"### {path}\n{text}")
        used += cost
    return "\n\n".join(parts), used


def recall_of(context: str, needles: list[str]) -> float:
    if not needles:
        return 0.0
    low = context.lower()
    return sum(1 for needle in needles if needle.lower() in low) / len(needles)


def auto_queries(corpus: Corpus, count: int, seed: int = 0) -> list[dict]:
    where: dict[str, set[str]] = {}
    for source in corpus.files:
        for ident in set(IDENT_RE.findall(source.text)):
            where.setdefault(ident, set()).add(source.path)

    rare = sorted(
        ident
        for ident, paths in where.items()
        if len(paths) <= 2 and ident.lower() not in STOPWORDS
    )
    if not rare:
        return []

    rng = random.Random(seed)
    rng.shuffle(rare)

    queries = []
    for ident in rare[:count]:
        words = [word for word in SPLIT_RE.split(ident) if len(word) > 2]
        keywords = [ident.lower()] + [word.lower() for word in words]
        queries.append(
            {
                "question": ident,
                "needles": [ident],
                "keywords": sorted(set(keywords)),
            }
        )
    return queries


def keywords_for(query: dict) -> list[str]:
    if query.get("keywords"):
        return [keyword.lower() for keyword in query["keywords"]]
    words = [word.lower() for word in SPLIT_RE.split(query.get("question", "")) if len(word) > 3]
    needles = [needle.lower() for needle in query.get("needles", [])]
    return sorted(set(words + needles)) or [query.get("question", "").lower()]


def run(corpus: Corpus, queries: list[dict], budget: int) -> dict[str, dict]:
    policies = {
        "read_all": lambda c, r, k, b: chunks_read_all(c),
        "grep_files": lambda c, r, k, b: chunks_grep(c, k),
        "pagerank_map": lambda c, r, k, b: chunks_pagerank_map(c, r),
        "ladder": chunks_ladder,
    }
    results: dict[str, dict] = {}

    # Rank once per query, not once per policy: the ranking is the expensive part.
    prepared = []
    for query in queries:
        keywords = keywords_for(query)
        prepared.append((query, keywords, pagerank(corpus, personalize(corpus, keywords))))

    for name, build in policies.items():
        total_recall = 0.0
        total_tokens = 0
        for query, keywords, ranked in prepared:
            context, used = assemble(build(corpus, ranked, keywords, budget), budget)
            total_recall += recall_of(context, query.get("needles", []))
            total_tokens += used
        count = len(queries) or 1
        mean_recall = total_recall / count
        mean_tokens = total_tokens / count
        results[name] = {
            "recall": mean_recall,
            "tokens": mean_tokens,
            "recall_per_1k": (mean_recall / (mean_tokens / 1000.0)) if mean_tokens else 0.0,
        }

    return results


def main(argv: list[str]) -> int:
    parser = argparse.ArgumentParser(description="Benchmark context-selection policies.")
    parser.add_argument("root", nargs="?", default=".", help="repository to scan")
    parser.add_argument("--budget", type=int, default=4000, help="token budget")
    parser.add_argument("--queries", help="JSON file of questions and needles")
    parser.add_argument("--auto", type=int, default=25, help="auto-generate N queries")
    parser.add_argument("--seed", type=int, default=0, help="shuffle seed for auto mode")
    parser.add_argument("--json", action="store_true", help="emit JSON instead of a table")
    args = parser.parse_args(argv)

    root = Path(args.root).resolve()
    if not root.is_dir():
        print(f"not a directory: {root}", file=sys.stderr)
        return 2

    corpus = load_corpus(root)
    if not corpus.files:
        print(f"no source files found under {root}", file=sys.stderr)
        return 1

    if args.queries:
        loaded = json.loads(Path(args.queries).read_text(encoding="utf-8"))
        if not isinstance(loaded, list):
            print("--queries must hold a JSON array", file=sys.stderr)
            return 2
        queries = [item for item in loaded if isinstance(item, dict)]
    else:
        queries = auto_queries(corpus, args.auto, args.seed)

    if not queries:
        print("no queries: pass --queries or use a corpus with distinctive identifiers", file=sys.stderr)
        return 1

    results = run(corpus, queries, args.budget)

    if args.json:
        print(json.dumps(results, indent=2))
        return 0

    print(f"corpus: {root}")
    print(f"files: {len(corpus.files)}  queries: {len(queries)}  budget: {args.budget} tokens\n")
    print("| policy | recall | tokens | recall/1k |")
    print("| --- | --- | --- | --- |")
    for name, metrics in results.items():
        print(
            f"| {name} | {metrics['recall']:.3f} | "
            f"{metrics['tokens']:.0f} | {metrics['recall_per_1k']:.3f} |"
        )

    best = max(results.items(), key=lambda item: item[1]["recall_per_1k"])
    print(f"\nbest recall per 1k tokens: {best[0]}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
