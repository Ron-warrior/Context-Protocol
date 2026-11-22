#!/usr/bin/env python3
"""ctx — the Context Protocol CLI. Standard library only, no dependencies.

Ranks files for a question, emits a signature map, then scoped windows around
the hits, all under a token budget. Unlike a graph dump, the output is chosen
against the question, and every claim about it is measured by `ctx bench` on
needle recall per 1k tokens.

Commands
    ctx map <path>                      file map with sizes
    ctx query <path> "<question>"       the ladder, under a budget
    ctx bench <path>                    read_all vs grep vs ladder, recall/1k
    ctx selftest                        fixtures; exit 0 means the tool works

Examples
    python3 ctx.py query . "how are errors handled"
    python3 ctx.py query . "auth token refresh" --budget 2000 --json
    python3 ctx.py bench . --queries 25
"""

from __future__ import annotations

import argparse
import json
import random
import re
import sys
import tempfile
from dataclasses import dataclass
from pathlib import Path

SKIP_DIRS = {
    ".git", "node_modules", "venv", ".venv", "dist", "build", "__pycache__",
    ".next", ".mypy_cache", ".pytest_cache", "target", "vendor", "Pods",
    ".tox", ".idea", ".vscode", ".gradle", "bin", "obj", "coverage", ".cache",
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
    "the", "and", "how", "does", "what", "where", "which", "that", "this",
    "from", "with", "into", "are", "was", "for", "not", "you", "its", "work",
    "return", "import", "public", "private", "static", "string", "number",
    "object", "module", "exports", "default", "function", "const", "class",
    "value", "result", "error", "false", "true", "null", "self",
}

DEF_RE = re.compile(
    r"^\s*(?:export\s+|pub\s+|public\s+|private\s+|protected\s+|static\s+"
    r"|async\s+|final\s+|abstract\s+|open\s+|override\s+|internal\s+)*"
    r"(?:class|def|function|func|fn|interface|struct|enum|trait|impl|type"
    r"|const|record|module|namespace|object)\s+([A-Za-z_$][\w$]*)"
)
IDENT_RE = re.compile(r"[A-Za-z_][A-Za-z0-9_]{5,}")


@dataclass
class Source:
    path: str
    text: str


def tokens(text: str) -> int:
    return max(1, len(text) // 4)


def words_of(question: str) -> list[str]:
    found = re.findall(r"[A-Za-z_][A-Za-z0-9_]{2,}", question.lower())
    return [w for w in dict.fromkeys(found) if w not in STOPWORDS] or found


def load(root: Path) -> list[Source]:
    files: list[Source] = []
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
        if text.strip():
            files.append(Source(str(rel), text))
    return files


def outline(source: Source) -> list[str]:
    lines = []
    for index, line in enumerate(source.text.splitlines()):
        if DEF_RE.match(line):
            lines.append(f"{index + 1}: {line.strip()[:120]}")
            if len(lines) >= MAX_OUTLINE_LINES:
                break
    return lines


def rank(files: list[Source], words: list[str]) -> list[Source]:
    """Definition hits beat usage hits; small files beat large ones."""
    scored = []
    for source in files:
        if not words:
            continue
        low = source.text.lower()
        hits = sum(low.count(word) for word in words)
        if not hits:
            continue
        definitions = sum(
            1
            for line in source.text.splitlines()
            if DEF_RE.match(line) and any(word in line.lower() for word in words)
        )
        score = (hits + 3 * definitions) / (1.0 + len(source.text) / 4000.0)
        scored.append((score, source.path, source))
    scored.sort(key=lambda item: (-item[0], item[1]))
    return [item[2] for item in scored]


def window(text: str, words: list[str], pad: int = 4, cap: int = 40) -> str:
    lines = text.splitlines()
    hits = [i for i, line in enumerate(lines) if any(w in line.lower() for w in words)]
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


def ladder(files: list[Source], words: list[str], budget: int, share: float = 0.4):
    """Rank -> signature map within `share` of the budget -> windows with the rest."""
    ranked = rank(files, words)
    head = max(1, int(budget * share))
    used = 0
    chunks: list[tuple[str, str]] = []

    for source in ranked:
        block = "\n".join(outline(source))
        if not block:
            continue
        cost = tokens(block)
        if used + cost > head:
            continue
        chunks.append((source.path, block))
        used += cost

    for source in ranked:
        if used >= budget:
            break
        snippet = window(source.text, words)
        if not snippet:
            continue
        cost = tokens(snippet)
        if used + cost > budget:
            continue
        chunks.append((f"{source.path} (excerpt)", snippet))
        used += cost

    body = "\n\n".join(f"### {path}\n{text}" for path, text in chunks)
    return body, used, len(chunks)


def recall_of(context: str, needles: list[str]) -> float:
    if not needles:
        return 0.0
    low = context.lower()
    return sum(1 for n in needles if n.lower() in low) / len(needles)


def auto_queries(files: list[Source], count: int, seed: int = 0) -> list[dict]:
    where: dict[str, set[str]] = {}
    for source in files:
        for ident in set(IDENT_RE.findall(source.text)):
            where.setdefault(ident, set()).add(source.path)
    rare = sorted(
        ident for ident, paths in where.items()
        if len(paths) <= 2 and ident.lower() not in STOPWORDS
    )
    if not rare:
        return []
    random.Random(seed).shuffle(rare)
    return [{"question": ident, "needles": [ident]} for ident in rare[:count]]


def cmd_map(args) -> int:
    files = load(Path(args.path))
    if not files:
        print("no source files", file=sys.stderr)
        return 1
    for source in sorted(files, key=lambda f: -len(f.text)):
        print(f"{len(source.text.splitlines()):6d}  {source.path}")
    print(f"\n{len(files)} files", file=sys.stderr)
    return 0


def cmd_query(args) -> int:
    files = load(Path(args.path))
    if not files:
        print("no source files", file=sys.stderr)
        return 1
    words = words_of(args.question)
    body, used, chunks = ladder(files, words, args.budget)

    if args.json:
        print(json.dumps({
            "question": args.question,
            "words": words,
            "tokens": used,
            "chunks": chunks,
            "context": body,
        }, indent=2))
        return 0

    print(body)
    print(f"\n-- {chunks} chunks, ~{used} tokens, {len(files)} files scanned", file=sys.stderr)
    return 0


def cmd_bench(args) -> int:
    files = load(Path(args.path))
    if not files:
        print("no source files", file=sys.stderr)
        return 1
    queries = auto_queries(files, args.queries, args.seed)
    if not queries:
        print("no queries generated", file=sys.stderr)
        return 1

    policies = {
        "read_all": lambda words: "\n\n".join(
            f"### {s.path}\n{s.text}" for s in files
        )[: args.budget * 4],
        "grep": lambda words: "\n\n".join(
            f"### {s.path}\n{s.text}"
            for s in files
            if any(w in s.text.lower() for w in words)
        )[: args.budget * 4],
        "ladder": lambda words: ladder(files, words, args.budget)[0],
    }

    print(f"corpus: {args.path}  files: {len(files)}  queries: {len(queries)}  budget: {args.budget}\n")
    print("| policy | recall | tokens | recall/1k |")
    print("| --- | --- | --- | --- |")
    for name, build in policies.items():
        total_recall = 0.0
        total_tokens = 0
        for query in queries:
            context = build(words_of(" ".join(query["needles"])))
            cost = min(tokens(context), args.budget)
            total_recall += recall_of(context, query["needles"])
            total_tokens += cost
        count = len(queries)
        mean_recall = total_recall / count
        mean_tokens = total_tokens / count
        per_1k = (mean_recall / (mean_tokens / 1000.0)) if mean_tokens else 0.0
        print(f"| {name} | {mean_recall:.3f} | {mean_tokens:.0f} | {per_1k:.3f} |")
    return 0


def cmd_selftest(_args) -> int:
    checks = 0

    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        (root / "alpha.py").write_text(
            "def refresh_token(user):\n    return user.token\n",
            encoding="utf-8",
        )
        (root / "beta.py").write_text(
            "import os\n\n\ndef unrelated_helper():\n    return os.getcwd()\n",
            encoding="utf-8",
        )

        files = load(root)
        assert len(files) == 2, f"expected 2 files, got {len(files)}"
        checks += 1

        assert tokens("abcd" * 10) == 10, "token estimate must be chars/4"
        checks += 1

        words = words_of("where is the refresh token")
        assert "refresh" in words and "the" not in words, f"stopwords leaked: {words}"
        checks += 1

        ranked = rank(files, ["refresh_token"])
        assert ranked and ranked[0].path == "alpha.py", "definition-bearing file must rank first"
        checks += 1

        snippet = window(files[0].text, ["refresh_token"])
        assert "def refresh_token" in snippet, "window must contain the hit"
        checks += 1

        body, used, chunks = ladder(files, words, 4000)
        assert "refresh_token" in body, "the ladder must surface the needle"
        assert used <= 4000, f"budget exceeded: {used}"
        assert chunks >= 1, "expected at least one chunk"
        checks += 1

        tight, tight_used, _ = ladder(files, words, 64)
        assert tight_used <= 64, f"budget exceeded on the tight run: {tight_used}"
        checks += 1

        assert recall_of(body, ["refresh_token"]) == 1.0, "recall must find a present needle"
        assert recall_of(body, ["absent_symbol"]) == 0.0, "recall must miss an absent needle"
        checks += 1

        queries = auto_queries(files, 5)
        assert isinstance(queries, list), "auto_queries must return a list"
        checks += 1

    print(f"PASS: {checks} checks")
    return 0


def main(argv: list[str] | None = None) -> int:
    # Console scripts call main() with no arguments; `python3 ctx.py` passes none
    # either. Only an explicit list is treated as the argument vector.
    if argv is None:
        argv = sys.argv[1:]
    parser = argparse.ArgumentParser(prog="ctx", description="Context Protocol CLI")
    sub = parser.add_subparsers(dest="command", required=True)

    p_map = sub.add_parser("map", help="file map with line counts")
    p_map.add_argument("path")
    p_map.set_defaults(func=cmd_map)

    p_query = sub.add_parser("query", help="build context for a question")
    p_query.add_argument("path")
    p_query.add_argument("question")
    p_query.add_argument("--budget", type=int, default=4000)
    p_query.add_argument("--json", action="store_true")
    p_query.set_defaults(func=cmd_query)

    p_bench = sub.add_parser("bench", help="score policies on recall per 1k tokens")
    p_bench.add_argument("path")
    p_bench.add_argument("--queries", type=int, default=25)
    p_bench.add_argument("--budget", type=int, default=4000)
    p_bench.add_argument("--seed", type=int, default=0)
    p_bench.set_defaults(func=cmd_bench)

    p_self = sub.add_parser("selftest", help="run fixtures")
    p_self.set_defaults(func=cmd_selftest)

    args = parser.parse_args(argv)
    return args.func(args)


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
