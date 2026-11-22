#!/usr/bin/env python3
"""ctx — the Context Protocol CLI. Standard library only, no dependencies.

Objective, in strictly this order:

  1. INTELLIGENCE      — put the answer in front of the model. Emit the enclosing
                         block of every match before spending anything on maps.
  2. TOKEN EFFICIENCY  — spend as few tokens as possible *subject to* (1).
  3. SPEED             — one pass, precompiled regexes, no index to build.

A cheap answer that is wrong loses to an expensive one that is right. That is the
opposite of a compression benchmark, and it is why `ctx bench` reports recall
first, tokens second, and time third.

Commands
    ctx map <path>                        file map with line counts
    ctx query <path> "<question>"         intelligence-first context, budgeted
    ctx bench <path>                      recall / tokens / ms per policy
    ctx selftest                          fixtures; exit 0 means it works
"""

from __future__ import annotations

import argparse
import json
import random
import re
import sys
import tempfile
import time
from dataclasses import dataclass, field
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
MAX_BODY_LINES = 80

STOPWORDS = {
    "the", "and", "how", "does", "what", "where", "which", "that", "this",
    "from", "with", "into", "are", "was", "for", "not", "you", "its", "work",
    "return", "import", "public", "private", "static", "string", "number",
    "object", "module", "exports", "default", "function", "const", "class",
    "value", "result", "error", "false", "true", "null", "self", "used", "use",
}

DEF_RE = re.compile(
    r"^\s*(?:export\s+|pub\s+|public\s+|private\s+|protected\s+|static\s+"
    r"|async\s+|final\s+|abstract\s+|open\s+|override\s+|internal\s+)*"
    r"(?:class|def|function|func|fn|interface|struct|enum|trait|impl|type"
    r"|const|record|module|namespace|object)\s+([A-Za-z_$][\w$]*)"
)
IDENT_RE = re.compile(r"[A-Za-z_][A-Za-z0-9_]{2,}")
SPLIT_RE = re.compile(r"[_\W]+|(?<=[a-z])(?=[A-Z])")
IMPORT_RES = (
    re.compile(r"^\s*import\s+([\w.]+)", re.MULTILINE),
    re.compile(r"^\s*from\s+([\w.]+)\s+import", re.MULTILINE),
    re.compile(r"""^\s*import\s+[^'"]*?from\s+['"]([^'"]+)['"]""", re.MULTILINE),
    re.compile(r"""require\(\s*['"]([^'"]+)['"]\s*\)"""),
    re.compile(r"^\s*using\s+([\w.]+)", re.MULTILINE),
    re.compile(r"^\s*use\s+([\w:]+)", re.MULTILINE),
)


@dataclass
class Source:
    path: str
    text: str
    symbols: set[str] = field(default_factory=set)


def tokens(text: str) -> int:
    return max(1, len(text) // 4)


def split_identifier(token: str) -> list[str]:
    """refreshToken / refresh_token / RefreshToken -> ['refresh', 'token']."""
    return [part.lower() for part in SPLIT_RE.split(token) if part]


def words_of(question: str) -> list[str]:
    found: list[str] = []
    for token in IDENT_RE.findall(question):
        for part in split_identifier(token):
            if len(part) > 1 and part not in STOPWORDS and part not in found:
                found.append(part)
    return found


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
        if not text.strip():
            continue
        symbols: set[str] = set()
        for ident in IDENT_RE.findall(text):
            for part in split_identifier(ident):
                if len(part) > 2:
                    symbols.add(part)
        files.append(Source(str(rel), text, symbols))
    return files


def stem_index(files: list[Source]) -> dict[str, str]:
    index: dict[str, str] = {}
    for source in files:
        index.setdefault(Path(source.path).stem.lower(), source.path)
    return index


def related(source: Source, index: dict[str, str]) -> list[str]:
    """Files this one imports, resolved by stem. One hop, outlines only."""
    found: list[str] = []
    for pattern in IMPORT_RES:
        for ref in pattern.findall(source.text):
            tail = re.split(r"[.:/\\]", ref.rstrip("/"))[-1]
            target = index.get(Path(tail).stem.lower())
            if target and target != source.path and target not in found:
                found.append(target)
    return found


def outline(source: Source) -> list[str]:
    lines: list[str] = []
    for number, line in enumerate(source.text.splitlines(), start=1):
        if DEF_RE.match(line):
            lines.append(f"{number}: {line.strip()[:120]}")
            if len(lines) >= MAX_OUTLINE_LINES:
                break
    return lines


def hit_lines(source: Source, words: list[str]) -> list[int]:
    hits: list[int] = []
    for index, line in enumerate(source.text.splitlines()):
        low = line.lower()
        if any(word in low for word in words):
            hits.append(index)
    return hits


def enclosing_block(text: str, hit: int) -> tuple[int, int]:
    """The function or block containing `hit`, from its declaration down past it.

    Intelligence-first: a fixed +-4 window cuts the answer off whenever the
    question is about what a function *does* rather than which line matches.
    """
    lines = text.splitlines()
    start = None
    for index in range(min(hit, len(lines) - 1), -1, -1):
        if DEF_RE.match(lines[index]):
            start = index
            break
    if start is None:
        start = max(0, hit - 6)
    end = min(len(lines), max(hit + 8, start + 8))
    if end - start > MAX_BODY_LINES:
        end = start + MAX_BODY_LINES
    return start, end


def numbered(text: str, start: int, end: int) -> str:
    lines = text.splitlines()[start:end]
    return "\n".join(f"{start + i + 1}: {line[:200]}" for i, line in enumerate(lines))


def rank(files: list[Source], words: list[str]) -> list[tuple[float, Source]]:
    """Score by evidence the answer is here, not by how cheap the file is.

    - symbol match: a query word is part of a declared name (strongest signal)
    - co-occurrence: two distinct query words on one line (the relation asked about)
    - raw hits: how often the words appear at all
    Length damping stays as a weak prior: a huge file mentioning a word once is
    usually not the answer.
    """
    if not words:
        return []
    scored: list[tuple[float, Source]] = []
    for source in files:
        low = source.text.lower()
        if not any(word in low for word in words):
            continue
        hits = 0
        co_occur = 0
        for line in source.text.splitlines():
            low_line = line.lower()
            present = sum(1 for word in words if word in low_line)
            if present:
                hits += present
                if present >= 2:
                    co_occur += 1
        symbol_hits = sum(1 for word in words if word in source.symbols)
        score = (hits + 4 * symbol_hits + 3 * co_occur) / (1.0 + len(source.text) / 4000.0)
        scored.append((score, source))
    scored.sort(key=lambda item: (-item[0], item[1].path))
    return scored


def build_context(files: list[Source], words: list[str], budget: int, expand: bool = True):
    """Intelligence first, then cost. Returns (text, tokens_used, chunks)."""
    ranked = rank(files, words)
    if not ranked:
        return "", 0, 0

    used = 0
    chunks: list[tuple[str, str]] = []
    seen: set[tuple[str, int, int]] = set()

    def add(label: str, block: str) -> bool:
        nonlocal used
        if not block.strip():
            return False
        cost = tokens(block)
        if used + cost > budget:
            return False
        chunks.append((label, block))
        used += cost
        return True

    # Phase 1 — the answer itself: the enclosing block of the best matches.
    for _score, source in ranked[:3]:
        for hit in hit_lines(source, words)[:2]:
            start, end = enclosing_block(source.text, hit)
            if (source.path, start, end) in seen:
                continue
            seen.add((source.path, start, end))
            add(f"{source.path}:{start + 1}-{end} (body)", numbered(source.text, start, end))

    # Phase 2 — the map: signatures, so the model knows what else exists.
    for _score, source in ranked:
        block = "\n".join(outline(source))
        if block:
            add(source.path, block)

    # Phase 3 — blocks in files that matched but were not the top three.
    for _score, source in ranked[3:]:
        pieces: list[str] = []
        for hit in hit_lines(source, words)[:1]:
            start, end = enclosing_block(source.text, hit)
            if (source.path, start, end) in seen:
                continue
            seen.add((source.path, start, end))
            pieces.append(numbered(source.text, start, end))
        if pieces:
            add(f"{source.path} (excerpt)", "\n".join(pieces))

    # Phase 4 — one hop out: what the top file imports. Often where the
    # definition lives, and cheap because it is outlines only.
    if expand:
        by_path = {source.path: source for source in files}
        index = stem_index(files)
        for _score, source in ranked[:2]:
            for target in related(source, index)[:4]:
                other = by_path.get(target)
                if not other:
                    continue
                block = "\n".join(outline(other))
                if block:
                    add(f"{target} (related to {source.path})", block)

    body = "\n\n".join(f"### {label}\n{block}" for label, block in chunks)
    return body, used, len(chunks)


def build_context_lean(files: list[Source], words: list[str], budget: int):
    """Token-first baseline: map within 40% of the budget, then short windows."""
    ranked = rank(files, words)
    head = max(1, int(budget * 0.4))
    used = 0
    chunks: list[tuple[str, str]] = []

    for _score, source in ranked:
        block = "\n".join(outline(source))
        if not block:
            continue
        cost = tokens(block)
        if used + cost > head:
            continue
        chunks.append((source.path, block))
        used += cost

    for _score, source in ranked:
        if used >= budget:
            break
        hits = hit_lines(source, words)[:1]
        if not hits:
            continue
        start = max(0, hits[0] - 4)
        end = min(len(source.text.splitlines()), hits[0] + 5)
        block = numbered(source.text, start, end)
        cost = tokens(block)
        if used + cost > budget:
            continue
        chunks.append((f"{source.path} (excerpt)", block))
        used += cost

    body = "\n\n".join(f"### {label}\n{block}" for label, block in chunks)
    return body, used, len(chunks)


def recall_of(context: str, needles: list[str]) -> float:
    if not needles:
        return 0.0
    low = context.lower()
    return sum(1 for needle in needles if needle.lower() in low) / len(needles)


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
    started = time.perf_counter()
    if args.lean:
        body, used, chunks = build_context_lean(files, words, args.budget)
    else:
        body, used, chunks = build_context(files, words, args.budget, expand=args.expand)
    elapsed = (time.perf_counter() - started) * 1000

    if args.json:
        print(json.dumps({
            "question": args.question,
            "words": words,
            "tokens": used,
            "chunks": chunks,
            "ms": round(elapsed, 1),
            "context": body,
        }, indent=2))
        return 0

    print(body)
    print(
        f"\n-- {chunks} chunks, ~{used} tokens, {len(files)} files, {elapsed:.0f} ms",
        file=sys.stderr,
    )
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

    def read_all(_words):
        body = "\n\n".join(f"### {s.path}\n{s.text}" for s in files)
        return body, min(tokens(body), args.budget)

    def grep(words):
        body = "\n\n".join(
            f"### {s.path}\n{s.text}" for s in files
            if any(w in s.text.lower() for w in words)
        )
        return body, min(tokens(body), args.budget)

    def lean(words):
        return build_context_lean(files, words, args.budget)[:2]

    def intelligence(words):
        return build_context(files, words, args.budget)[:2]

    policies = {
        "read_all": read_all,
        "grep": grep,
        "lean": lean,
        "intelligence": intelligence,
    }

    print(f"corpus: {args.path}  files: {len(files)}  queries: {len(queries)}  budget: {args.budget}")
    print("objective: recall first, tokens second, speed third\n")
    print("| policy | recall | tokens | ms |")
    print("| --- | --- | --- | --- |")

    rows = []
    for name, build in policies.items():
        total_recall = 0.0
        total_tokens = 0
        started = time.perf_counter()
        for query in queries:
            context, used = build(words_of(query["needles"][0]))
            total_tokens += used
            total_recall += recall_of(context, query["needles"])
        elapsed = (time.perf_counter() - started) * 1000
        count = len(queries)
        rows.append((total_recall / count, total_tokens / count, elapsed / count, name))

    rows.sort(key=lambda row: (-row[0], row[1], row[2]))
    for mean_recall, mean_tokens, mean_ms, name in rows:
        print(f"| {name} | {mean_recall:.3f} | {mean_tokens:.0f} | {mean_ms:.1f} |")
    print(f"\nbest by recall, then tokens, then ms: {rows[0][3]}")
    return 0


def cmd_selftest(_args) -> int:
    checks = 0

    assert split_identifier("refreshToken") == ["refresh", "token"], "camelCase split"
    assert split_identifier("refresh_token") == ["refresh", "token"], "snake_case split"
    checks += 2

    words = words_of("where is the refresh token")
    assert "refresh" in words and "the" not in words, f"stopwords leaked: {words}"
    checks += 1

    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        (root / "alpha.py").write_text(
            "def refresh_token(user):\n"
            "    value = user.token\n"
            "    value = value.strip()\n"
            "    return value\n",
            encoding="utf-8",
        )
        (root / "beta.py").write_text(
            "import alpha\n\n\ndef unrelated_helper():\n    return 1\n",
            encoding="utf-8",
        )

        files = load(root)
        assert len(files) == 2, f"expected 2 files, got {len(files)}"
        checks += 1

        assert tokens("abcd" * 10) == 10, "token estimate must be chars/4"
        checks += 1

        ranked = rank(files, ["refresh", "token"])
        assert ranked and ranked[0][1].path == "alpha.py", "definition-bearing file must rank first"
        checks += 1

        alpha = next(f for f in files if f.path == "alpha.py")
        start, end = enclosing_block(alpha.text, 0)
        assert start == 0, "block must start at the declaration"
        checks += 1

        body, used, chunks = build_context(files, ["refresh", "token"], 4000)
        assert "refresh_token" in body, "the context must surface the needle"
        assert "value.strip()" in body, "the enclosing body must be complete, not a +-4 window"
        assert used <= 4000, f"budget exceeded: {used}"
        assert chunks >= 1, "expected at least one chunk"
        checks += 3

        _tight, tight_used, _ = build_context(files, ["refresh", "token"], 64)
        assert tight_used <= 64, f"budget exceeded on the tight run: {tight_used}"
        checks += 1

        _lean_body, lean_used, _ = build_context_lean(files, ["refresh", "token"], 4000)
        assert lean_used <= 4000, "lean budget exceeded"
        checks += 1

        assert recall_of(body, ["refresh_token"]) == 1.0, "recall must find a present needle"
        assert recall_of(body, ["absent_symbol"]) == 0.0, "recall must miss an absent needle"
        checks += 2

        index = stem_index(files)
        assert "alpha.py" in related(alpha, index), "import must resolve by stem"
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

    p_query = sub.add_parser("query", help="build intelligence-first context")
    p_query.add_argument("path")
    p_query.add_argument("question")
    p_query.add_argument("--budget", type=int, default=4000)
    p_query.add_argument("--lean", action="store_true", help="token-first baseline")
    p_query.add_argument("--no-expand", dest="expand", action="store_false")
    p_query.add_argument("--json", action="store_true")
    p_query.set_defaults(func=cmd_query)

    p_bench = sub.add_parser("bench", help="recall, then tokens, then time")
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
