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
__version__ = "2.6.0"

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
# TypeScript and modern JS declare most functions as `const name = ...`, which
# DEF_RE does not see. Without this, enclosing blocks and call-site expansion
# skip the dominant form in the corpus we test against.
CONST_RE = re.compile(r"^\s*(?:export\s+)?(?:const|let|var)\s+([A-Za-z_$][\w$]*)\s*=")


def declaration_name(line: str) -> str | None:
    """The name this line declares, if any: class/def/func… or const name =."""
    match = DEF_RE.match(line) or CONST_RE.match(line)
    return match.group(1) if match else None


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
    lines: list[str] = field(default_factory=list)
    low: str = ""

    def __post_init__(self) -> None:
        # Split and lowercase once per file rather than once per query: ranking
        # touches every file, and speed is the third objective but it is free here.
        if not self.lines:
            self.lines = self.text.splitlines()
        if not self.low:
            self.low = self.text.lower()


def tokens(text: str) -> int:
    return max(1, len(text) // 4)


def split_identifier(token: str) -> list[str]:
    """refreshToken / refresh_token / RefreshToken -> ['refresh', 'token']."""
    return [part.lower() for part in SPLIT_RE.split(token) if part]


def stem(word: str) -> str:
    """Crude suffix stripping so 'errors' finds 'error' and 'handled' finds 'handle'.

    Deliberately not a real stemmer: no dependency, no dictionary, and every rule
    only ever shortens, so it can widen a match but never invent one.
    """
    for suffix in ("ing", "ed", "es", "s"):
        if len(word) > len(suffix) + 3 and word.endswith(suffix):
            return word[: -len(suffix)]
    return word


def words_of(question: str) -> list[str]:
    found: list[str] = []
    for token in IDENT_RE.findall(question):
        for part in split_identifier(token):
            if len(part) > 1 and part not in STOPWORDS:
                for form in (part, stem(part)):
                    if form and form not in found:
                        found.append(form)
    return found


def ignore_patterns(root: Path) -> list[str]:
    """Directory names, file names and *.ext patterns from the project's .gitignore.

    Simple on purpose: no negation, no globstar. A wrong include costs tokens; a
    wrong exclude costs the answer, so only patterns that are unambiguous here are
    honoured.
    """
    path = root / ".gitignore"
    if not path.is_file():
        return []
    try:
        lines = path.read_text(encoding="utf-8", errors="replace").splitlines()
    except OSError:
        return []
    patterns: list[str] = []
    for line in lines:
        text = line.strip()
        if not text or text.startswith("#") or text.startswith("!"):
            continue
        patterns.append(text.rstrip("/"))
    return patterns


def is_ignored(rel: Path, patterns: list[str]) -> bool:
    if not patterns:
        return False
    parts = rel.parts
    name = rel.name
    for pattern in patterns:
        if "/" in pattern:
            if str(rel).startswith(pattern):
                return True
            continue
        if pattern in parts:
            return True
        if pattern == name:
            return True
        if pattern.startswith("*.") and name.endswith(pattern[1:]):
            return True
    return False


def load(root: Path) -> list[Source]:
    files: list[Source] = []
    ignores = ignore_patterns(root)
    for path in sorted(root.rglob("*")):
        if not path.is_file():
            continue
        rel = path.relative_to(root)
        # `.venv-ctx`, `.venv312`, `venv`, `env` … any of these is the tool's own
        # environment, not the user's code. Scanning it produced a file map of
        # site-packages in CI.
        if any(
            part in SKIP_DIRS or part.startswith(".venv") or part == "site-packages"
            for part in rel.parts[:-1]
        ):
            continue
        if is_ignored(rel, ignores):
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
    for number, line in enumerate(source.lines, start=1):
        if declaration_name(line):
            lines.append(f"{number}: {line.strip()[:120]}")
            if len(lines) >= MAX_OUTLINE_LINES:
                break
    return lines


def hit_lines(source: Source, words: list[str]) -> list[int]:
    hits: list[int] = []
    for index, line in enumerate(source.lines):
        low = line.lower()
        if any(word in low for word in words):
            hits.append(index)
    return hits


def best_hit_lines(source: Source, words: list[str], limit: int = 2) -> list[int]:
    """The most informative lines, not the first ones.

    A line carrying three query words says more about the answer than a line
    carrying one, and a declaration line more than a mention. Deterministic:
    ties fall back to the earlier line.
    """
    scored: list[tuple[int, int, int]] = []
    for index, line in enumerate(source.lines):
        low = line.lower()
        distinct = sum(1 for word in words if word in low)
        if not distinct:
            continue
        bonus = 2 if DEF_RE.match(line) else 0
        scored.append((distinct + bonus, -index, index))
    scored.sort(reverse=True)
    return [index for _score, _neg, index in scored[:limit]]


def enclosing_block(text: str, hit: int) -> tuple[int, int]:
    """The function or block containing `hit`, from its declaration down past it.

    Intelligence-first: a fixed +-4 window cuts the answer off whenever the
    question is about what a function *does* rather than which line matches.
    """
    lines = text.splitlines()
    start = None
    for index in range(min(hit, len(lines) - 1), -1, -1):
        if declaration_name(lines[index]):
            start = index
            break
    if start is None:
        start = max(0, hit - 6)
    end = min(len(lines), max(hit + 8, start + 8))
    if end - start > MAX_BODY_LINES:
        # Never cut the matched line out of its own block. Capping from the
        # declaration alone drops the hit whenever it sits deep in a long
        # function, which is exactly when the block was worth including.
        start = max(start, hit - MAX_BODY_LINES // 2)
        end = min(end, start + MAX_BODY_LINES)
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
        if not any(word in source.low for word in words):
            continue
        hits = 0
        co_occur = 0
        for line in source.lines:
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


def declared_symbols(source: Source, limit: int = 6) -> list[str]:
    """Names this file declares, lowercased, longest first.

    Longest first because `refresh_token` is a better search key than `get`.
    """
    names: list[str] = []
    for line in source.lines:
        name = declaration_name(line)
        if not name:
            continue
        lowered = name.lower()
        if len(lowered) > 3 and lowered not in names:
            names.append(lowered)
    names.sort(key=len, reverse=True)
    return names[:limit]


def call_sites(files: list[Source], symbols: list[str], skip: set[str], limit: int = 4):
    """Where the declared names are used, outside the files already included.

    The answer to "how does X work" is often half in the definition and half in
    the caller that decides when it runs.
    """
    found: list[tuple[str, int, int]] = []
    if not symbols:
        return found
    for source in files:
        if source.path in skip:
            continue
        low = source.text.lower()
        if not any(symbol in low for symbol in symbols):
            continue
        for hit in hit_lines(source, symbols)[:1]:
            start = max(0, hit - 6)
            end = min(len(source.text.splitlines()), hit + 7)
            found.append((source.path, start, end))
            if len(found) >= limit:
                return found
    return found


def build_context(files: list[Source], words: list[str], budget: int, expand: bool = True):
    """Intelligence first, then cost. Returns (text, tokens_used, chunks)."""
    ranked = rank(files, words)
    if not ranked:
        return "", 0, 0

    used = 0
    chunks: list[tuple[str, str]] = []
    seen: set[tuple[str, int, int]] = set()
    seen_text: set[str] = set()

    def add(label: str, block: str) -> bool:
        nonlocal used
        stripped = block.strip()
        if not stripped or stripped in seen_text:
            return False
        cost = tokens(block)
        if used + cost > budget:
            return False
        chunks.append((label, block))
        seen_text.add(stripped)
        used += cost
        return True

    # Phase 1 — the answer itself: the enclosing block of the best matches.
    for _score, source in ranked[:3]:
        for hit in best_hit_lines(source, words):
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
        for hit in best_hit_lines(source, words, 1):
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

    # Phase 5 — who calls what was found. The definition says how; the caller says
    # when and why, and that is usually what the question is really asking.
    if expand:
        symbols: list[str] = []
        for _score, source in ranked[:2]:
            for name in declared_symbols(source):
                if name not in symbols:
                    symbols.append(name)
        included = {source.path for _score, source in ranked[:3]}
        for path, start, end in call_sites(files, symbols, included):
            add(f"{path}:{start + 1}-{end} (call site)", numbered(
                next(f for f in files if f.path == path).text, start, end))

    # Phase 6 — only if the budget is still mostly unspent, go one hop further.
    # Cheap-in, high-signal-out, and never at the expense of phases 1-5.
    if expand and used < int(budget * 0.6):
        by_path = {source.path: source for source in files}
        index = stem_index(files)
        for _score, source in ranked[:1]:
            for first in related(source, index)[:3]:
                middle = by_path.get(first)
                if not middle:
                    continue
                for second in related(middle, index)[:2]:
                    other = by_path.get(second)
                    if not other or other.path == source.path:
                        continue
                    block = "\n".join(outline(other))
                    if block:
                        add(f"{second} (two hops from {source.path})", block)

    body = "\n\n".join(f"### {label}\n{block}" for label, block in chunks)
    header = f"# context ({len(chunks)} chunks, ~{used} tokens)\n"
    return header + body, used, len(chunks)


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


def load_rc(root: Path) -> dict[str, str]:
    """`.ctxrc` in the scan root: key=value, one per line, # comments.

    Only two keys are honoured. A project that wants a bigger default budget can
    say so once instead of on every invocation.
    """
    path = root / ".ctxrc"
    if not path.is_file():
        return {}
    out: dict[str, str] = {}
    try:
        for line in path.read_text(encoding="utf-8", errors="replace").splitlines():
            text = line.strip()
            if not text or text.startswith("#") or "=" not in text:
                continue
            key, _, value = text.partition("=")
            out[key.strip()] = value.strip()
    except OSError:
        return {}
    return out


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
    if getattr(args, "explain", False):
        print("rank (score  path)", file=sys.stderr)
        for score, source in rank(files, words)[:5]:
            print(f"{score:8.2f}  {source.path}", file=sys.stderr)
    started = time.perf_counter()
    rc = load_rc(Path(args.path))
    budget = args.budget if args.budget is not None else int(rc.get("budget", "4000"))
    expand = args.expand
    if rc.get("expand", "").lower() in {"off", "false", "0", "no"}:
        expand = False
    if args.lean:
        body, used, chunks = build_context_lean(files, words, budget)
    else:
        body, used, chunks = build_context(files, words, budget, expand=expand)
    elapsed = (time.perf_counter() - started) * 1000

    if not body.strip():
        print(
            f"no match for {args.question!r} in {len(files)} files",
            file=sys.stderr,
        )
        return 0

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


def cmd_path(args) -> int:
    """Files that mention both symbols, and the lines that connect them.

    The cheapest structural answer there is: if a file mentions A and B, that
    file is where the relationship lives. No graph needed.
    """
    files = load(Path(args.path))
    if not files:
        print("no source files", file=sys.stderr)
        return 1
    first, second = args.a.lower(), args.b.lower()
    found = 0
    for source in files:
        low = source.text.lower()
        if first not in low or second not in low:
            continue
        lines_a = hit_lines(source, [first])[:1]
        lines_b = hit_lines(source, [second])[:1]
        if not lines_a or not lines_b:
            continue
        found += 1
        print(f"{source.path}")
        print(f"  {args.a}: {lines_a[0] + 1}")
        print(f"  {args.b}: {lines_b[0] + 1}")
    if not found:
        print(f"no file mentions both {args.a!r} and {args.b!r}", file=sys.stderr)
        return 1
    return 0


LADDER = (
    "0. Frame        one line: what would count as the answer",
    "1. Map          grep -rl for the question's keywords; files, not contents",
    "2. Rank         definition hit > usage hit; near > far; small > large",
    "3. Outline      signatures only, to choose a body before reading one",
    "4. Scope        read the enclosing block of the best hit, not a +-4 window",
    "5. Write        small verified units; past ~120 lines you will not re-read it",
    "6. Verify       read back, sweep callers, and run it if it runs",
    "7. Persist      write what you learned into the repo, not just the chat",
)


def cmd_plan(_args) -> int:
    """The ladder as a checklist, for agents with no shell and no install."""
    print("Context Protocol -- objective: intelligence, then tokens, then speed.\n")
    for rung in LADDER:
        print(f"  [ ] {rung}")
    print("\nStop: ~4k tokens per question. Two misses means change rung, not read a third file.")
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
        return body, tokens(body)

    def grep(words):
        body = "\n\n".join(
            f"### {s.path}\n{s.text}" for s in files
            if any(w in s.text.lower() for w in words)
        )
        return body, tokens(body)

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
    print("objective: recall first, tokens second, speed third")
    print("tokens is what the policy ACTUALLY emitted; over = it blew the budget\n")
    print("| policy | recall | tokens | over | ms |")
    print("| --- | --- | --- | --- | --- |")

    rows = []
    for name, build in policies.items():
        total_recall = 0.0
        total_tokens = 0
        over = 0
        started = time.perf_counter()
        for query in queries:
            context, used = build(words_of(query["needles"][0]))
            total_tokens += used
            if used > args.budget:
                over += 1
            total_recall += recall_of(context, query["needles"])
        elapsed = (time.perf_counter() - started) * 1000
        count = len(queries)
        rows.append((total_recall / count, total_tokens / count, over, elapsed / count, name))

    # Only policies that respect the budget can win: a dump that blows it is not
    # comparable, and scoring it as if it fit is how a compression benchmark lies.
    within = [row for row in rows if row[2] == 0] or rows
    within.sort(key=lambda row: (-row[0], row[1], row[3]))
    rows.sort(key=lambda row: (-row[0], row[1], row[3]))

    for mean_recall, mean_tokens, over, mean_ms, name in rows:
        flag = f"{over}/{len(queries)}" if over else "-"
        print(f"| {name} | {mean_recall:.3f} | {mean_tokens:.0f} | {flag} | {mean_ms:.1f} |")

    print(f"\nbest within budget (recall, then tokens, then ms): {within[0][4]}")

    by_name = {row[4]: row for row in rows}
    if "intelligence" in by_name and "lean" in by_name:
        ai = by_name["intelligence"]
        ln = by_name["lean"]
        print(
            f"intelligence vs lean: recall {ai[0] - ln[0]:+.3f}, "
            f"tokens {ai[1] - ln[1]:+.0f}"
        )
        if ai[0] <= ln[0] and ai[1] >= ln[1]:
            print("lean wins on both -- intelligence-first is paying for nothing here")
    return 0


def cmd_selftest(_args) -> int:
    checks = 0

    assert split_identifier("refreshToken") == ["refresh", "token"], "camelCase split"
    assert split_identifier("refresh_token") == ["refresh", "token"], "snake_case split"
    checks += 2

    assert declaration_name("const handler = async () => {}") == "handler", "const declaration"
    assert declaration_name("function go() {}") == "go", "function declaration"
    assert declaration_name("  const MAX = 10") == "MAX", "const constant"
    checks += 3

    assert stem("errors") == "error", "plural stem"
    assert stem("handled") == "handl", "past-tense stem"
    checks += 2

    assert is_ignored(Path("build/x.py"), ["build"]), "ignore a directory"
    assert not is_ignored(Path("src/x.py"), ["build"]), "keep an unrelated path"
    checks += 2

    sample = Source("f.py", "x\nrefresh token here\nrefresh\n")
    assert best_hit_lines(sample, ["refresh", "token"])[0] == 1, "the two-word line ranks first"
    checks += 1

    decls = declared_symbols(Source("g.py", "def refresh_token():\n    pass\ndef go():\n    pass\n"))
    assert decls[0] == "refresh_token", "longest declared name first"
    checks += 1

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

        # A venv inside the scan root is the tool's environment, not the corpus.
        venv = root / ".venv-ctx" / "lib" / "site-packages"
        venv.mkdir(parents=True)
        (venv / "installed.py").write_text("def leaked_name():\n    pass\n", encoding="utf-8")
        assert len(load(root)) == 2, "a .venv-ctx directory must not be scanned"
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

        # A hit deep inside a long function must still be inside the block.
        long_body = Source(
            "long.py",
            "def big():\n" + "\n".join(f"    x{i} = {i}" for i in range(200)) + "\n    needle_here()\n",
        )
        deep = long_body.lines.index("    needle_here()")
        lo, hi = enclosing_block(long_body.text, deep)
        assert lo <= deep < hi, f"hit at {deep} fell outside block {lo}-{hi}"
        assert hi - lo <= MAX_BODY_LINES, "block must respect the cap"
        checks += 2

        body, used, chunks = build_context(files, ["refresh", "token"], 4000)
        assert "refresh_token" in body, "the context must surface the needle"
        assert "value.strip()" in body, "the enclosing body must be complete, not a +-4 window"
        assert body.startswith("# context ("), "the context must say what it is"
        assert used <= 4000, f"budget exceeded: {used}"
        assert chunks >= 1, "expected at least one chunk"
        checks += 4

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
        beta = next(f for f in files if f.path == "beta.py")
        assert "alpha.py" in related(beta, index), "beta imports alpha, resolved by stem"
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
    parser.add_argument("--version", action="version", version=f"ctx {__version__}")
    sub = parser.add_subparsers(dest="command", required=True)

    p_map = sub.add_parser("map", help="file map with line counts")
    p_map.add_argument("path")
    p_map.set_defaults(func=cmd_map)

    p_query = sub.add_parser("query", help="build intelligence-first context")
    p_query.add_argument("path")
    p_query.add_argument("question")
    p_query.add_argument("--lean", action="store_true", help="token-first baseline")
    p_query.add_argument("--no-expand", dest="expand", action="store_false")
    p_query.add_argument("--explain", action="store_true", help="print the ranking")
    p_query.add_argument("--json", action="store_true")
    p_query.set_defaults(func=cmd_query)

    p_ask = sub.add_parser("ask", help="query, with the path defaulting to .")
    p_ask.add_argument("question")
    p_ask.add_argument("path", nargs="?", default=".")
    p_ask.add_argument("--lean", action="store_true", help="token-first baseline")
    p_ask.add_argument("--no-expand", dest="expand", action="store_false")
    p_ask.add_argument("--explain", action="store_true", help="print the ranking")
    p_ask.add_argument("--json", action="store_true")
    p_ask.set_defaults(func=cmd_query)

    # Both query forms share the budget flag; default None so .ctxrc can win.
    for parser_ in (p_query, p_ask):
        parser_.add_argument(
            "--budget", type=int, default=None, help="default: .ctxrc, else 4000"
        )

    p_bench = sub.add_parser("bench", help="recall, then tokens, then time")
    p_bench.add_argument("path")
    p_bench.add_argument("--queries", type=int, default=25)
    p_bench.add_argument("--budget", type=int, default=4000)
    p_bench.add_argument("--seed", type=int, default=0)
    p_bench.set_defaults(func=cmd_bench)

    p_self = sub.add_parser("selftest", help="run fixtures")
    p_self.set_defaults(func=cmd_selftest)

    p_path = sub.add_parser("path", help="files mentioning two symbols")
    p_path.add_argument("a")
    p_path.add_argument("b")
    p_path.add_argument("path", nargs="?", default=".")
    p_path.set_defaults(func=cmd_path)

    p_plan = sub.add_parser("plan", help="the ladder as a checklist")
    p_plan.set_defaults(func=cmd_plan)

    args = parser.parse_args(argv)
    try:
        return args.func(args)
    except BrokenPipeError:
        # Console scripts call main() directly, so the __main__ guard never runs.
        # A closed pipe is a normal pipeline ending, not a failure.
        return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main(sys.argv[1:]))
    except BrokenPipeError:
        # `ctx map . | head` closes stdout early. That is a normal shell pipeline,
        # not an error, so exit 0 without a traceback.
        sys.stderr.close()
        raise SystemExit(0)
