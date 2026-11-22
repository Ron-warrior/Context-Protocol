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

Stop-rule mode (--stop)
    Selection policy decides *which* tokens; a stop rule decides *when to give up*.
    They are independent, and the second one is cheaper to get wrong: a good
    ranking with no stop rule still burns the budget on a question the corpus
    cannot answer. --stop holds the ranking fixed, reads in rank order, and
    compares four stopping rules on answer rate against tokens spent.

Usage
    python3 eval/retrieval_bench.py .
    python3 eval/retrieval_bench.py . --budget 4000 --auto 30
    python3 eval/retrieval_bench.py . --queries q.json
    python3 eval/retrieval_bench.py . --sweep 1000,4000,16000
    python3 eval/retrieval_bench.py . --focus src/app.py
    python3 eval/retrieval_bench.py . --stop
    python3 eval/retrieval_bench.py --selftest

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
import tempfile
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
FALLBACK_OUTLINE_LINES = 12

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
IDENT_LIKE_RE = re.compile(r"^[A-Za-z_][\w.]*$")

# A line that declares something. Used to tell a definition hit from a usage hit,
# which rung 2 ranks differently and which nothing here could distinguish before
# 1.6.0: every occurrence counted the same.
DEF_RE = re.compile(
    r"^\s*(?:export\s+|pub\s+|public\s+|private\s+|protected\s+|static\s+"
    r"|async\s+|final\s+|abstract\s+|open\s+|override\s+|internal\s+|readonly\s+)*"
    r"(?:class|def|function|func|fn|interface|struct|enum|trait|impl|type|let"
    r"|const|var|record|module|namespace|object)\b"
)


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
    cost: dict[str, int] = field(default_factory=dict)
    imported_by: dict[str, set[str]] = field(default_factory=dict)
    scan: dict[str, tuple[list[str], list[bool]]] = field(default_factory=dict)


@dataclass
class Ranking:
    """The knobs behind rung 2, one per clause of it.

    Each default *is* the protocol's claim, and each one is a flag so the claim can
    lose rather than be assumed. Before 1.6.0 all three clauses were simply not
    implemented -- `personalize` counted every occurrence the same way -- which
    meant this bench could not test the ranking rule it was built to test. A
    harness that cannot fail the thing it measures is decoration.
    """

    focus: str | None = None          # "near the file you are editing > far"
    focus_weight: float = 3.0
    definition_weight: float = 4.0    # "definition hit > usage hit"; 1.0 disables
    length_damping: float = 0.5       # "small > large"; 0.0 disables


def scan_text(text: str) -> tuple[list[str], list[bool]]:
    """Lowercase lines and their declaration flags, computed once per file.

    Cached on the Corpus because a sweep re-ranks per query per budget; without the
    cache the same file would be lowercased and regex-matched dozens of times.
    """
    lines = text.splitlines()
    return [line.lower() for line in lines], [bool(DEF_RE.match(line)) for line in lines]


def weighted_hits(
    scan: tuple[list[str], list[bool]], keywords: list[str], definition_weight: float
) -> float:
    """Occurrences, with a hit on a declaration line counted `definition_weight` times."""
    if not keywords:
        return 0.0
    low_lines, is_definition = scan
    score = 0.0
    for index, low in enumerate(low_lines):
        weight = definition_weight if is_definition[index] else 1.0
        for keyword in keywords:
            found = low.count(keyword)
            if found:
                score += found * weight
    return score


def mentions(text: str, needle: str) -> bool:
    """Does `text` mention `needle` as a token, not as part of a longer one?

    The substring test this replaces counted `refresh_token` as present in
    `refresh_token_legacy`, so both recall and the stop-rule answer rate credited
    partial matches. Every policy inflated in the same direction, which is exactly
    why it survived three versions: it looked fair.
    """
    if IDENT_LIKE_RE.match(needle):
        pattern = r"(?<![A-Za-z0-9_])" + re.escape(needle) + r"(?![A-Za-z0-9_])"
        return re.search(pattern, text, re.IGNORECASE) is not None
    return needle.lower() in text.lower()


def resolve_focus(corpus: Corpus, focus: str | None) -> str | None:
    """Exact path, else a unique suffix match; None when it is not in the corpus."""
    if not focus:
        return None
    wanted = focus.strip().lstrip("./")
    known = {source.path for source in corpus.files}
    if wanted in known:
        return wanted
    matches = sorted(path for path in known if path.endswith("/" + wanted))
    return matches[0] if len(matches) == 1 else None


def estimate_tokens(text: str) -> int:
    """Rough but consistent: ~4 characters per token."""
    return max(1, len(text) // 4)


def chunk_cost(path: str, text: str) -> int:
    """Cost of a chunk as assembled, header included.

    Both `assemble` and `chunks_ladder` budget with this. While they budgeted
    separately they disagreed by the header's ~9 tokens, so a chunk the policy
    had counted as fitting could be dropped at assembly -- the policy then paid
    for a read it never got. One function, one number.
    """
    return estimate_tokens(f"### {path}\n{text}")


def outline_lines(text: str) -> list[str]:
    """Declaration lines if the file declares anything, else its first real lines.

    The fallback is load-bearing. Constants modules, config tables, scripts and
    data files declare nothing, so without it they were invisible to every
    map-based policy -- and a file that holds one crucial constant is exactly the
    case a question turns on. A map that omits them is not a smaller map, it is a
    wrong one.
    """
    lines = text.splitlines()
    out: list[str] = []
    for index, line in enumerate(lines):
        if OUTLINE_RE.match(line):
            out.append(f"{index + 1}: {line.strip()[:120]}")
            if len(out) >= MAX_OUTLINE_LINES:
                return out
    if out:
        return out
    for index, line in enumerate(lines):
        stripped = line.strip()
        if not stripped or stripped.startswith(("#", "//", "*", "/*", "--")):
            continue
        out.append(f"{index + 1}: {stripped[:120]}")
        if len(out) >= FALLBACK_OUTLINE_LINES:
            break
    return out


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
        corpus.imported_by.setdefault(source.path, set())
        for target in corpus.edges.get(source.path, ()):
            corpus.imported_by.setdefault(target, set()).add(source.path)

    for source in corpus.files:
        corpus.cost[source.path] = chunk_cost(source.path, source.text)
        corpus.outline[source.path] = outline_lines(source.text)
        corpus.scan[source.path] = scan_text(source.text)

    return corpus


def personalize(
    corpus: Corpus, keywords: list[str], rank: Ranking | None = None
) -> dict[str, float]:
    """Query- and chat-conditioned prior: one term per clause of rung 2.

    focus -> the file and its import neighbours start higher
    definition_weight -> a declaration outranks a usage
    length_damping -> a small file outranks a large one at equal hits
    """
    rank = rank or Ranking()
    focus = resolve_focus(corpus, rank.focus)

    boost: dict[str, float] = {}
    if focus:
        boost[focus] = rank.focus_weight
        for target in corpus.edges.get(focus, ()):
            boost[target] = max(boost.get(target, 0.0), rank.focus_weight / 2.0)
        for importer in corpus.imported_by.get(focus, ()):
            boost[importer] = max(boost.get(importer, 0.0), rank.focus_weight / 3.0)

    weights: dict[str, float] = {}
    for source in corpus.files:
        lines, is_definition = corpus.scan.get(source.path) or scan_text(source.text)
        hits = weighted_hits((lines, is_definition), keywords, rank.definition_weight)
        damping = max(1.0, len(lines)) ** rank.length_damping
        weights[source.path] = (hits / damping + 1.0) * (1.0 + boost.get(source.path, 0.0))

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
        cost = chunk_cost(source.path, body)
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
        cost = chunk_cost(f"{source.path} (excerpt)", snippet)
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
        cost = chunk_cost(path, text)
        if used + cost > budget:
            continue
        parts.append(f"### {path}\n{text}")
        used += cost
    return "\n\n".join(parts), used


def recall_of(context: str, needles: list[str]) -> float:
    if not needles:
        return 0.0
    return sum(1 for needle in needles if mentions(context, needle)) / len(needles)


# --- stop rules -------------------------------------------------------------
#
# The second experiment. Selection policy answers "which tokens"; a stopping rule
# answers "when to give up". They are independent: a perfect ranking with no stop
# rule still spends the whole budget on a question the corpus cannot answer.
#
# Files are read whole, in rank order, because the only variable here is *when to
# stop*, not how to slice each read. Every rule is additionally bounded by the
# token budget, so "never stop" is still finite and comparable.

STOP_RULES: dict[str, int | None] = {
    "until_found": None,
    "three_strike": 3,
    "two_strike": 2,
    "one_strike": 1,
}


def files_holding(corpus: Corpus, needles: list[str]) -> set[str]:
    """Files mentioning every needle: reading one of these answers the query."""
    if not needles:
        return set()
    return {
        source.path
        for source in corpus.files
        if all(mentions(source.text, needle) for needle in needles)
    }


def simulate_stop(
    corpus: Corpus,
    ranked: dict[str, float],
    needles: list[str],
    budget: int,
    max_misses: int | None,
) -> tuple[bool, int]:
    """Read in rank order until answered, out of misses, or out of budget."""
    holders = files_holding(corpus, needles)
    order = sorted(corpus.files, key=lambda source: -ranked.get(source.path, 0.0))
    used = 0
    misses = 0
    for source in order:
        cost = corpus.cost[source.path]
        if used + cost > budget:
            break
        used += cost
        if source.path in holders:
            return True, used
        misses += 1
        if max_misses is not None and misses >= max_misses:
            break
    return False, used


def run_stop(
    corpus: Corpus,
    prepared: list[tuple[dict, list[str], dict[str, float]]],
    budget: int,
) -> dict[str, dict]:
    """Cost of each stopping rule, with the ranking held fixed."""
    results: dict[str, dict] = {}
    for rule, max_misses in STOP_RULES.items():
        answered = 0
        total_tokens = 0
        for query, _keywords, ranked in prepared:
            found, used = simulate_stop(
                corpus, ranked, query.get("needles", []), budget, max_misses
            )
            answered += 1 if found else 0
            total_tokens += used
        count = len(prepared) or 1
        rate = answered / count
        mean_tokens = total_tokens / count
        results[rule] = {
            "answer_rate": rate,
            "tokens": mean_tokens,
            "tokens_per_answer": (mean_tokens / rate) if rate else 0.0,
            "answer_per_1k": (rate / (mean_tokens / 1000.0)) if mean_tokens else 0.0,
        }
    return results


def report_stop(
    corpus: Corpus,
    prepared: list[tuple[dict, list[str], dict[str, float]]],
    budget: int,
    as_json: bool,
) -> int:
    results = run_stop(corpus, prepared, budget)
    if as_json:
        print(json.dumps(results, indent=2))
        return 0
    print(f"files: {len(corpus.files)}  queries: {len(queries)}  budget: {budget} tokens\n")
    print("| stop rule | answer rate | tokens | tokens/answer |")
    print("| --- | --- | --- | --- |")
    for name, metrics in results.items():
        print(
            f"| {name} | {metrics['answer_rate']:.3f} | "
            f"{metrics['tokens']:.0f} | {metrics['tokens_per_answer']:.0f} |"
        )
    best = max(results.items(), key=lambda item: item[1]["answer_per_1k"])
    print(f"\nbest answer rate per 1k tokens: {best[0]}")
    return 0


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


def prepare(
    corpus: Corpus, queries: list[dict], rank: Ranking | None = None
) -> list[tuple[dict, list[str], dict[str, float]]]:
    """Rank once per query. A budget is not an input, which is what makes a sweep cheap."""
    rank = rank or Ranking()
    prepared = []
    for query in queries:
        keywords = keywords_for(query)
        prepared.append(
            (query, keywords, pagerank(corpus, personalize(corpus, keywords, rank)))
        )
    return prepared


POLICIES = {
    "read_all": lambda corpus, ranked, keywords, budget: chunks_read_all(corpus),
    "grep_files": lambda corpus, ranked, keywords, budget: chunks_grep(corpus, keywords),
    "pagerank_map": lambda corpus, ranked, keywords, budget: chunks_pagerank_map(
        corpus, ranked
    ),
    "ladder": chunks_ladder,
}


def run(
    corpus: Corpus,
    prepared: list[tuple[dict, list[str], dict[str, float]]],
    budget: int,
) -> dict[str, dict]:
    results: dict[str, dict] = {}
    for name, build in POLICIES.items():
        total_recall = 0.0
        total_tokens = 0
        for query, keywords, ranked in prepared:
            context, used = assemble(build(corpus, ranked, keywords, budget), budget)
            total_recall += recall_of(context, query.get("needles", []))
            total_tokens += used
        count = len(prepared) or 1
        mean_recall = total_recall / count
        mean_tokens = total_tokens / count
        results[name] = {
            "recall": mean_recall,
            "tokens": mean_tokens,
            "recall_per_1k": (mean_recall / (mean_tokens / 1000.0)) if mean_tokens else 0.0,
        }
    return results


def parse_budgets(spec: str) -> list[int]:
    budgets = []
    for part in spec.replace(" ", "").split(","):
        if not part:
            continue
        if not part.isdigit() or int(part) <= 0:
            raise ValueError(f"not a token budget: {part}")
        budgets.append(int(part))
    if not budgets:
        raise ValueError("--sweep needs at least one budget")
    return budgets


def report_sweep(
    corpus: Corpus,
    prepared: list[tuple[dict, list[str], dict[str, float]]],
    budgets: list[int],
    as_json: bool,
) -> int:
    """One budget is one point, and the winner there can lose at four times the size."""
    table = {budget: run(corpus, prepared, budget) for budget in budgets}
    if as_json:
        print(json.dumps({str(budget): row for budget, row in table.items()}, indent=2))
        return 0
    print(f"files: {len(corpus.files)}  queries: {len(prepared)}\n")
    print("recall per 1k tokens, by budget\n")
    print("| policy | " + " | ".join(str(b) for b in budgets) + " |")
    print("| --- |" + " --- |" * len(budgets))
    for name in table[budgets[0]]:
        cells = " | ".join(f"{table[budget][name]['recall_per_1k']:.3f}" for budget in budgets)
        print(f"| {name} | {cells} |")
    print()
    for budget in budgets:
        best = max(table[budget].items(), key=lambda item: item[1]["recall_per_1k"])
        print(f"  budget {budget:>6}: best recall per 1k = {best[0]}")
    winners = {
        max(table[budget].items(), key=lambda item: item[1]["recall_per_1k"])[0]
        for budget in budgets
    }
    if len(winners) > 1:
        print(f"\nthe winner changes with the budget: {', '.join(sorted(winners))}")
    else:
        print(f"\n{next(iter(winners))} wins at every budget tried -- not an artifact of one")
    return 0


def main(argv: list[str]) -> int:
    parser = argparse.ArgumentParser(description="Benchmark context-selection policies.")
    parser.add_argument("root", nargs="?", default=".", help="repository to scan")
    parser.add_argument("--budget", type=int, default=4000, help="token budget")
    parser.add_argument("--queries", help="JSON file of questions and needles")
    parser.add_argument("--auto", type=int, default=25, help="auto-generate N queries")
    parser.add_argument("--seed", type=int, default=0, help="shuffle seed for auto mode")
    parser.add_argument("--json", action="store_true", help="emit JSON instead of a table")
    parser.add_argument(
        "--stop",
        action="store_true",
        help="compare stopping rules instead of selection policies",
    )
    parser.add_argument(
        "--sweep",
        help="comma-separated budgets, e.g. 1000,4000,16000: the winner per budget",
    )
    parser.add_argument(
        "--focus",
        help="path of the file being edited; ranking favours it and its neighbours",
    )
    parser.add_argument(
        "--selftest",
        action="store_true",
        help="run the built-in fixture checks and exit",
    )
    args = parser.parse_args(argv)

    if args.selftest:
        return selftest()

    root = Path(args.root).resolve()
    if not root.is_dir():
        print(f"not a directory: {root}", file=sys.stderr)
        return 2

    try:
        budgets = parse_budgets(args.sweep) if args.sweep else [args.budget]
    except ValueError as error:
        print(str(error), file=sys.stderr)
        return 2

    corpus = load_corpus(root)
    if not corpus.files:
        print(f"no source files found under {root}", file=sys.stderr)
        return 1

    if args.queries:
        try:
            loaded = json.loads(Path(args.queries).read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError) as error:
            print(f"cannot read --queries: {error}", file=sys.stderr)
            return 2
        if not isinstance(loaded, list):
            print("--queries must hold a JSON array", file=sys.stderr)
            return 2
        queries = [item for item in loaded if isinstance(item, dict)]
    else:
        queries = auto_queries(corpus, args.auto, args.seed)

    if not queries:
        print("no queries: pass --queries or use a corpus with distinctive identifiers", file=sys.stderr)
        return 1

    rank = Ranking(focus=args.focus)
    if args.focus and resolve_focus(corpus, args.focus) is None:
        print(f"--focus {args.focus!r} does not name exactly one file in the corpus", file=sys.stderr)
        return 2

    prepared = prepare(corpus, queries, rank)

    if args.stop:
        return report_stop(corpus, prepared, budgets[0], args.json)

    if args.sweep:
        return report_sweep(corpus, prepared, budgets, args.json)

    results = run(corpus, prepared, budgets[0])

    if args.json:
        print(json.dumps(results, indent=2))
        return 0

    print(f"corpus: {root}")
    print(f"files: {len(corpus.files)}  queries: {len(queries)}  budget: {budgets[0]} tokens\n")
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


# --- self-test --------------------------------------------------------------
#
# Four files, chosen to cover the defects this harness actually had: a
# declaration-less file (invisible to the map before 1.4.0), a needle in exactly
# one file, an import edge, and a file with nothing to do with anything.

SELFTEST_FILES = {
    "core.py": """
class WidgetStore:
    def refresh_token(self):
        return "ZxqvNeedleToken"
""",
    "constants.py": """
FIRST_LIMIT = 12
WIDGET_ALPHA_TOKEN = "WqzmConstantToken"
""",
    "main.py": """
from core import WidgetStore


def run():
    return WidgetStore()
""",
    "noise.py": """
def unrelated_thing():
    return 0
""",
}


def selftest() -> int:
    """Prove the harness before trusting its numbers on a real repository."""
    checks: list[tuple[str, bool]] = []
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        for name, body in SELFTEST_FILES.items():
            (root / name).write_text(body.strip() + "\n", encoding="utf-8")
        corpus = load_corpus(root)

        checks.append(("loads every fixture", len(corpus.files) == len(SELFTEST_FILES)))
        checks.append(("token estimate floors at 1", estimate_tokens("a") == 1))
        checks.append(
            (
                "chunk cost includes its header",
                chunk_cost("x.py", "abc") > estimate_tokens("abc"),
            )
        )
        checks.append(
            (
                "needle resolves to one file",
                files_holding(corpus, ["ZxqvNeedleToken"]) == {"core.py"},
            )
        )
        checks.append(
            (
                "declaration-less file gets an outline",
                bool(corpus.outline.get("constants.py")),
            )
        )

        flat = {source.path: 1.0 for source in corpus.files}
        mapped = dict(chunks_pagerank_map(corpus, flat))
        checks.append(("map includes the constants file", "constants.py" in mapped))

        ranked = pagerank(corpus, personalize(corpus, ["WqzmConstantToken"]))
        text, used = assemble(chunks_ladder(corpus, ranked, ["wqzmconstanttoken"], 300), 300)
        checks.append(("ladder stays inside the budget", used <= 300))
        checks.append(("ladder reaches the needle", "WqzmConstantToken" in text))

        _, small = assemble(chunks_read_all(corpus), 40)
        checks.append(("read_all cannot exceed a small budget", small <= 40))

        found, _ = simulate_stop(corpus, ranked, ["WqzmConstantToken"], 100_000, None)
        checks.append(("unstoppable rule answers", found))
        walled, _ = simulate_stop(corpus, ranked, ["WqzmConstantToken"], 1, None)
        checks.append(("a budget wall stops even that rule", not walled))

        window = window_around(SELFTEST_FILES["core.py"], ["refresh_token"])
        checks.append(("window shows the hit line", "refresh_token" in window))

        checks.append(
            (
                "needle does not match a longer identifier",
                not mentions("def refresh_token_legacy(): pass", "refresh_token"),
            )
        )
        checks.append(
            (
                "definition outranks usage at equal hits",
                weighted_hits(
                    (["def refresh_token():", "x = refresh_token"], [True, False]),
                    ["refresh_token"],
                    4.0,
                )
                > weighted_hits(
                    (["x = refresh_token", "y = refresh_token"], [False, False]),
                    ["refresh_token"],
                    4.0,
                ),
            )
        )
        plain = personalize(corpus, ["wqzmconstanttoken"], Ranking(definition_weight=1.0, length_damping=0.0))
        tuned = personalize(corpus, ["wqzmconstanttoken"], Ranking(definition_weight=4.0))
        checks.append(("ranking knobs change the prior", plain != tuned))
        focused = personalize(corpus, [], Ranking(focus="core.py"))
        checks.append(("focus raises the focused file", focused["core.py"] > focused["noise.py"]))
        checks.append(("unknown focus resolves to nothing", resolve_focus(corpus, "nope.py") is None))

    failed = 0
    for label, passed in checks:
        print(("PASS  " if passed else "FAIL  ") + label)
        failed += 0 if passed else 1
    print(f"\n{len(checks) - failed}/{len(checks)} checks passed")
    return 0 if failed == 0 else 1


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
