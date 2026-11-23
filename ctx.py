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
import math
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

PROSE_EXT = {".md", ".rst", ".txt"}

MAX_FILE_BYTES = 400_000
MAX_OUTLINE_LINES = 60
MAX_BODY_LINES = 80
__version__ = "2.26.0"

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
    # Whole identifiers, unsplit. `symbols` holds their parts, which is what
    # ranking wants; a declared name can only be found by its whole form.
    identifiers: set[str] = field(default_factory=set)
    lines: list[str] = field(default_factory=list)
    lowered: list[str] = field(default_factory=list)
    low: str = ""

    def __post_init__(self) -> None:
        # Split and lowercase once per file rather than once per query: ranking and
        # the hit scanners touch every line of every file on every question.
        if not self.lines:
            self.lines = self.text.splitlines()
        if not self.low:
            self.low = self.text.lower()
        if not self.lowered:
            self.lowered = [line.lower() for line in self.lines]
        if not self.identifiers:
            self.identifiers = {ident.lower() for ident in IDENT_RE.findall(self.text)}


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
    text = str(rel)
    for pattern in patterns:
        anchored = pattern.startswith("/")
        stripped = pattern.lstrip("/")
        if not stripped:
            continue
        if anchored:
            # `.gitignore` reads `/build` as "the root", but the old code tested
            # `str(rel).startswith("/build")`, which no relative path ever matches.
            # Every anchored pattern in every .gitignore was silently a no-op.
            if text == stripped or text.startswith(stripped + "/"):
                return True
            continue
        if "/" in stripped:
            if text.startswith(stripped) or ("/" + stripped) in text:
                return True
            continue
        if stripped in parts or stripped == name:
            return True
        if stripped.startswith("*.") and name.endswith(stripped[1:]):
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
        identifiers: set[str] = set()
        for ident in IDENT_RE.findall(text):
            identifiers.add(ident.lower())
            for part in split_identifier(ident):
                if len(part) > 2:
                    symbols.add(part)
        files.append(Source(str(rel), text, symbols, identifiers))
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
    for index, low_line in enumerate(source.lowered):
        if any(word in low_line for word in words):
            hits.append(index)
    return hits


def best_hit_lines(source: Source, words: list[str], limit: int = 2) -> list[int]:
    """The most informative lines, not the first ones.

    A line carrying three query words says more about the answer than a line
    carrying one, and a declaration line more than a mention. Deterministic:
    ties fall back to the earlier line.
    """
    scored: list[tuple[int, int, int]] = []
    for index, low_line in enumerate(source.lowered):
        distinct = sum(1 for word in words if word in low_line)
        if not distinct:
            continue
        bonus = 2 if declaration_name(source.lines[index]) else 0
        scored.append((distinct + bonus, -index, index))
    scored.sort(reverse=True)
    return [index for _score, _neg, index in scored[:limit]]


def block_bounds(lines: list[str], hit: int) -> tuple[int, int]:
    """The function or block containing `hit`, from its declaration down past it.

    Intelligence-first: a fixed +-4 window cuts the answer off whenever the
    question is about what a function *does* rather than which line matches.
    Takes the already-split lines so callers that hold a `Source` do not split the
    whole file again for every hit.
    """
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


def enclosing_block(text: str, hit: int) -> tuple[int, int]:
    """`block_bounds` for a caller holding text rather than a `Source`."""
    return block_bounds(text.splitlines(), hit)


LINE_CAP = 240
ELLIPSIS = "…"


def clip_line(line: str, words: list[str] = ()) -> str:
    """One line, shortened to LINE_CAP characters *around the query*, not at its head.

    2.23.0's own `next` found this and nothing else could have. Nine hard misses,
    seven of them reported as "line emitted, but the needle sits past its
    200-character cut": the blocks were correct, and the line cap was discarding
    the word. The lines in question are single-paragraph markdown and long prompt
    strings, so the answer sat at column 300 of a line whose first 200 characters
    are kept. Keeping the head of a long line is the wrong end to keep.
    """
    if len(line) <= LINE_CAP:
        return line
    lowered = line.lower()
    at = -1
    for word in words:
        index = lowered.find(word)
        if index >= 0 and (at < 0 or index < at):
            at = index
    if at < 0:
        return line[: LINE_CAP - 1] + ELLIPSIS
    start = max(0, at - LINE_CAP // 3)
    end = min(len(line), start + LINE_CAP)
    start = max(0, end - LINE_CAP)
    piece = line[start:end]
    if start:
        piece = ELLIPSIS + piece
    if end < len(line):
        piece = piece + ELLIPSIS
    return piece


def numbered_lines(
    lines: list[str], start: int, end: int, words: list[str] = ()
) -> str:
    return "\n".join(
        f"{start + i + 1}: {clip_line(line, words)}"
        for i, line in enumerate(lines[start:end])
    )


def rank(
    files: list[Source], words: list[str], phrase: str = ""
) -> list[tuple[float, Source]]:
    """Score by evidence the answer is here, not by how cheap the file is.

    - lookup: the query is one identifier and the file contains it verbatim (a tier,
      above everything else)
    - exact phrase: the whole query string appears verbatim (strongest signal)
    - symbol match: a query word is part of an identifier somewhere in the file
    - co-occurrence: two distinct query words on one line (the relation asked about)
    - raw hits: how often the words appear at all
    Length damping stays as a weak prior: a huge file mentioning a word once is
    usually not the answer.

    The phrase boost exists because diagnosis showed missed answers sitting at a
    median rank of 40: their files matched the *parts* of an identifier but were
    outscored by files full of generic occurrences of one part.
    """
    if not words:
        return []
    phrase_low = (phrase or "").strip().lower()
    use_phrase = len(phrase_low) > 3
    # A query that is a single identifier is a lookup, not a topic. Any file that
    # contains that exact identifier outranks every file that merely contains its
    # parts, whatever the part counts say. 2.24.0 ranked three needles that live in
    # exactly one file at 13, 37 and 130 for this reason: `maxMb` and
    # `ensureApiKeysBaseUrlColumn` split into common words, and a file mentioning
    # `max` forty times outscored the one file holding the answer. A x3 multiplier
    # cannot beat a hundred partial hits; a tier can.
    lookup = (
        bool(phrase_low)
        and len(phrase_low) > 3
        and not any(character.isspace() for character in phrase_low)
    )
    scored: list[tuple[float, bool, Source]] = []
    for source in files:
        if not any(word in source.low for word in words):
            continue
        hits = 0
        co_occur = 0
        for low_line in source.lowered:
            present = sum(1 for word in words if word in low_line)
            if present:
                hits += present
                if present >= 2:
                    co_occur += 1
        symbol_hits = sum(1 for word in words if word in source.symbols)
        score = (hits + 4 * symbol_hits + 3 * co_occur) / (1.0 + len(source.text) / 4000.0)
        has_phrase = use_phrase and phrase_low in source.low
        if has_phrase and not lookup:
            # A sentence that happens to appear verbatim is strong but not decisive.
            score *= 3.0
        scored.append((score, has_phrase, source))
    scored.sort(key=lambda item: (not item[1], -item[0], item[2].path))
    return [(score, source) for score, _has_phrase, source in scored]


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


@dataclass
class Corpus:
    """The files once, and every index over them, built once.

    These indexes used to be rebuilt into local names inside the phase that
    wanted one, and `index = stem_index(files)` in the import phase overwrote the
    symbol index that the call-site phase was about to use. That phase therefore
    searched file stems for symbol names and emitted nothing at all, for every
    query, from the moment it was written. One owner removes the possibility.
    """

    files: list[Source]
    by_path: dict[str, Source] = field(default_factory=dict)
    by_stem: dict[str, str] = field(default_factory=dict)
    by_ident: dict[str, list[str]] = field(default_factory=dict)

    def __post_init__(self) -> None:
        for source in self.files:
            self.by_path.setdefault(source.path, source)
            for ident in source.identifiers:
                self.by_ident.setdefault(ident, []).append(source.path)
        self.by_stem = stem_index(self.files)

    def paths_with(self, name: str) -> list[str]:
        """Files containing this exact identifier, unsplit.

        A declaration is snake_case or camelCase while `Source.symbols` holds its
        parts, so looking `refresh_token` up by whole name in a parts index misses
        however correct that index is — the second reason the call-site phase was
        empty. This is the index that can answer it.
        """
        return self.by_ident.get(name, [])


SMALL_FILE_LINES = 60
# Narrower views of the same hit, tried in order when the better one will not fit.
SHRINK_SPANS = (24, 14, 8, 4)


def candidate_ranges(source: Source, hit: int) -> list[tuple[int, int]]:
    """Ranges for one hit, best first: the whole small file, its block, windows.

    A block that did not fit the remaining budget used to be discarded outright,
    so the last few hundred tokens of every query bought nothing at all — the
    policy spent ~2,900 of 4,000 and stopped. Each alternative after the first is
    strictly narrower, so falling through can only add coverage the refusal
    threw away, never displace coverage that already fit.
    """
    total = len(source.lines)
    ranges: list[tuple[int, int]] = []
    if total <= SMALL_FILE_LINES:
        ranges.append((0, total))
    start, end = block_bounds(source.lines, hit)
    if (start, end) not in ranges:
        ranges.append((start, end))
    for span in SHRINK_SPANS:
        if span >= end - start:
            continue
        low = max(0, min(hit - span // 2, total - span))
        high = min(total, low + span)
        if low <= hit < high and (low, high) not in ranges:
            ranges.append((low, high))
    return ranges


PHASES = ("body", "excerpt", "map", "related", "call", "twohop")


@dataclass
class Chunk:
    """One range chosen for the context, before it becomes text.

    Selection and rendering used to be the same expression, which made three
    things impossible at once: saying what a phase contributed, saying whether a
    missed line was inside an emitted range, and charging for the label the model
    actually reads.
    """

    path: str
    start: int
    end: int
    kind: str
    label: str
    text: str


def make_chunk(
    source: Source, start: int, end: int, kind: str, words: list[str] = ()
) -> Chunk:
    label = f"{source.path}:{start + 1}-{end} ({kind})"
    return Chunk(
        source.path, start, end, kind, label,
        numbered_lines(source.lines, start, end, words),
    )


def outline_chunk(source: Source, label: str) -> Chunk | None:
    block = "\n".join(outline(source))
    if not block:
        return None
    return Chunk(source.path, 0, 0, "map", label, block)


def plan_context(
    corpus: Corpus,
    words: list[str],
    budget: int,
    expand: bool = True,
    phrase: str = "",
    phases: set[str] | None = None,
) -> list[Chunk]:
    """Choose ranges under the budget. Rendering happens afterwards, in one place.

    Phases run in a fixed order because the order is the objective: the answer's
    own blocks, then every other ranked match, then the map, then one hop out,
    then callers, then two hops. `phases` makes any of them removable, which is
    what lets a version be blamed on one phase instead of on the whole policy.
    """
    active = set(PHASES) if phases is None else set(phases) & set(PHASES)
    if not expand:
        active -= {"related", "call", "twohop"}
    ranked = rank(corpus.files, words, phrase)
    if not ranked or not active:
        return []

    budget_chars = budget * 4
    chars = 0
    chunks: list[Chunk] = []
    ranges: set[tuple[str, int, int]] = set()
    mapped: set[str] = set()
    seen_text: set[str] = set()

    def total_chars() -> int:
        count = max(1, len(chunks))
        return chars + 2 * (count - 1) + len(f"# context ({count} chunks)\n")

    def spent() -> int:
        return total_chars() // 4

    def contains_known(path: str, start: int, end: int) -> bool:
        """True when this range is nested in, or wraps, one already emitted.

        Partially overlapping functions of one file are allowed; a block that
        merely repeats a range already in the context is not.
        """
        for name, low, high in ranges:
            if name != path:
                continue
            if (low <= start and end <= high) or (start <= low and high <= end):
                return True
        return False

    def take(chunk: Chunk) -> bool:
        """Gate on the exact rendered size, never on a per-block estimate.

        2.23.0 reserved a flat 24 tokens for the header and charged each block with
        its own floored token count. Floors lose up to one token per block and the
        "\\n\\n" separators between blocks were never counted at all, so a context of
        ~30 small blocks overshot by ~30 tokens: the bench reported 15 of 100
        queries over budget, and because `intelligence` then failed its own budget
        check the "best within budget" line picked `read_all` — a 1.9M-token dump.
        Counting characters and converting once, against the same expression
        `render_context` uses, cannot drift.
        """
        nonlocal chars
        stripped = chunk.text.strip()
        if not stripped or stripped in seen_text:
            return False
        extra = len(f"### {chunk.label}\n") + len(chunk.text)
        count = len(chunks) + 1
        if chars + extra + 2 * (count - 1) + len(f"# context ({count} chunks)\n") > budget_chars:
            return False
        chunks.append(chunk)
        seen_text.add(stripped)
        chars += extra
        return True

    def too_big(source: Source, start: int, end: int) -> bool:
        """True only when the range provably cannot fit; a cheap pre-check.

        The floor ignores the label and the line-number gutter, so it is a genuine
        lower bound: it can only skip a range that `take` would have refused anyway.
        """
        span = source.lines[start:end]
        if not span:
            return True
        floor = sum(1 + min(len(line), LINE_CAP) for line in span)
        return (chars + floor) // 4 > budget

    def emit(source: Source, hit: int, kind: str) -> bool:
        """The best range for this hit that the remaining budget can pay for."""
        for start, end in candidate_ranges(source, hit):
            if too_big(source, start, end):
                continue
            if contains_known(source.path, start, end):
                continue
            if take(make_chunk(source, start, end, kind, words)):
                ranges.add((source.path, start, end))
                return True
        return False

    def emit_outline(source: Source, label: str) -> bool:
        if source.path in mapped:
            return False
        chunk = outline_chunk(source, label)
        if chunk is None or not take(chunk):
            return False
        mapped.add(source.path)
        return True

    # Phase 1 — the answer itself: the best matches of the files that ranked first.
    # 2.18.0's diagnose found the remaining misses inside the top 10, so the top of
    # the list is where coverage is bought rather than further down it.
    if "body" in active:
        for position, (_score, source) in enumerate(ranked[:3]):
            limit = 4 if position == 0 else 3
            for hit in best_hit_lines(source, words, limit):
                emit(source, hit, "body")

    # Phase 2 — every other ranked match, spending the budget rather than stopping
    # at an arbitrary rank. The ranking had already found the file; refusing to
    # emit it was the measured failure ("ranked but not emitted").
    if "excerpt" in active:
        reserve = int(budget * 0.15)
        for position, (_score, source) in enumerate(ranked[3:], start=4):
            if spent() > budget - reserve:
                break
            per_file = 3 if position <= 10 else 1
            for hit in best_hit_lines(source, words, per_file):
                emit(source, hit, "excerpt")

    # Phase 3 — the map: signatures, so the model knows what else exists. Every
    # ranked file is tried: an outline is small, so a later one can still fit after
    # an earlier one did not, and cutting the loop short would drop that coverage.
    if "map" in active:
        for _score, source in ranked:
            emit_outline(source, source.path)

    # Phase 4 — one hop out: what the top file imports. Often where the
    # definition lives, and cheap because it is outlines only.
    if "related" in active:
        for _score, source in ranked[:2]:
            for target in related(source, corpus.by_stem)[:4]:
                other = corpus.by_path.get(target)
                if other:
                    emit_outline(other, f"{target} (related to {source.path})")

    # Phase 5 — who calls what was found. The definition says how; the caller says
    # when and why. This phase emitted nothing at all before 2.23.0, for two
    # separate reasons: the import phase overwrote the symbol index with the stem
    # index, and a declared name was looked up whole in an index keyed by its
    # split parts. Both are regression-tested in `selftest`.
    if "call" in active:
        symbols: list[str] = []
        for _score, source in ranked[:2]:
            for name in declared_symbols(source):
                if name not in symbols:
                    symbols.append(name)
        included = {source.path for _score, source in ranked[:3]}
        made = 0
        for symbol in symbols:
            for path in corpus.paths_with(symbol):
                if path in included:
                    continue
                other = corpus.by_path.get(path)
                if other is None:
                    continue
                hits = hit_lines(other, [symbol])[:1]
                if not hits:
                    continue
                if emit(other, hits[0], "call"):
                    included.add(path)
                    made += 1
                if made >= 4:
                    break
            if made >= 4:
                break

    # Phase 6 — only if the budget is still mostly unspent, go one hop further.
    # Cheap-in, high-signal-out, and never at the expense of phases 1-5.
    if "twohop" in active and spent() < int(budget * 0.6):
        for _score, source in ranked[:1]:
            for first in related(source, corpus.by_stem)[:3]:
                middle = corpus.by_path.get(first)
                if middle is None:
                    continue
                for second in related(middle, corpus.by_stem)[:2]:
                    other = corpus.by_path.get(second)
                    if other is None or other.path == source.path:
                        continue
                    emit_outline(other, f"{second} (two hops from {source.path})")

    return chunks


def render_context(chunks: list[Chunk]) -> tuple[str, int]:
    """Text and its exact cost.

    This is the expression the budget gate in `plan_context` mirrors, character
    for character: the header, every label, every line-number gutter and the
    "\\n\\n" between blocks. If the two ever diverge, a policy reports a number it
    did not emit, which is the defect 2.23.0 shipped.
    """
    body = "\n\n".join(f"### {chunk.label}\n{chunk.text}" for chunk in chunks)
    header = f"# context ({len(chunks)} chunks)\n"
    text = header + body
    return text, tokens(text)


def build_context(
    corpus: Corpus,
    words: list[str],
    budget: int,
    expand: bool = True,
    phrase: str = "",
    phases: set[str] | None = None,
):
    """Intelligence first, then cost. Returns (text, tokens_used, chunks)."""
    chunks = plan_context(corpus, words, budget, expand, phrase, phases)
    if not chunks:
        return "", 0, 0
    text, used = render_context(chunks)
    return text, used, len(chunks)


def build_context_lean(
    corpus: Corpus, words: list[str], budget: int, phrase: str = ""
):
    """Token-first baseline: map within 40% of the budget, then short windows.

    Charged in characters against the exact rendered size, the same way
    `build_context` is. The previous version charged floored per-block token
    counts against `budget - 24` and reported 6 of 100 hard queries over budget;
    a baseline that overshoots is not a baseline.
    """
    ranked = rank(corpus.files, words, phrase)
    map_limit = max(1, int(budget * 0.4)) * 4
    budget_chars = budget * 4
    chunks: list[tuple[str, str]] = []
    chars = 0
    mapped = 0

    def take(label: str, text: str, limit: int) -> bool:
        nonlocal chars
        extra = len(f"### {label}\n") + len(text)
        count = len(chunks) + 1
        total = chars + extra + 2 * (count - 1) + len(f"# context ({count} chunks)\n")
        if total > limit:
            return False
        chunks.append((label, text))
        chars += extra
        return True

    for _score, source in ranked:
        block = "\n".join(outline(source))
        if not block:
            continue
        extra = len(f"### {source.path}\n") + len(block)
        if mapped + extra > map_limit:
            continue
        if take(source.path, block, budget_chars):
            mapped += extra

    for _score, source in ranked:
        hits = hit_lines(source, words)[:1]
        if not hits:
            continue
        start = max(0, hits[0] - 4)
        end = min(len(source.lines), hits[0] + 5)
        take(
            f"{source.path} (excerpt)",
            numbered_lines(source.lines, start, end, words),
            budget_chars,
        )

    body = "\n\n".join(f"### {label}\n{text}" for label, text in chunks)
    header = f"# context ({len(chunks)} chunks)\n"
    return header + body, tokens(header + body), len(chunks)


def recall_of(context: str, needles: list[str]) -> float:
    if not needles:
        return 0.0
    low = context.lower()
    return sum(1 for needle in needles if needle.lower() in low) / len(needles)


def wilson(successes: float, total: int, z: float = 1.96) -> tuple[float, float]:
    """The 95% interval for a proportion, so a one-query change is not called a gain.

    At 100 queries each one is worth exactly 0.010 recall, and this project has
    twice described a single query as a result. The interval says how much of a
    difference the sample cannot distinguish; the lower bound is the number that
    deserves to be quoted.
    """
    if total <= 0:
        return 0.0, 0.0
    p = successes / total
    denominator = 1.0 + z * z / total
    centre = (p + z * z / (2.0 * total)) / denominator
    spread = z * math.sqrt(p * (1.0 - p) / total + z * z / (4.0 * total * total))
    margin = spread / denominator
    return max(0.0, centre - margin), min(1.0, centre + margin)


def auto_queries(
    files: list[Source], count: int, seed: int = 0, rare: int = 2, code_only: bool = False
) -> list[dict]:
    """Questions built from identifiers that appear in at most `rare` files.

    rare=1 is the hard case and the realistic one: a fact that exists in exactly
    one place. rare=2 is easier, because a second mention is a second chance.

    `code_only` skips prose when *choosing* the identifier, not when searching.
    A word that appears once in a translated README qualifies as a rare
    identifier and is not a fact anyone would query a codebase for; 5 of the 10
    remaining misses were exactly that. The corpus still contains those files, so
    a real question about them is still answerable — only the generated questions
    get narrower. Reported alongside the default rate rather than replacing it,
    because quietly dropping hard cases is how a benchmark flatters itself.
    """
    where: dict[str, set[str]] = {}
    for source in files:
        if code_only and Path(source.path).suffix.lower() in PROSE_EXT:
            continue
        for ident in set(IDENT_RE.findall(source.text)):
            where.setdefault(ident, set()).add(source.path)
    candidates = sorted(
        ident for ident, paths in where.items()
        if len(paths) <= rare and ident.lower() not in STOPWORDS
    )
    if not candidates:
        return []
    random.Random(seed).shuffle(candidates)
    return [{"question": ident, "needles": [ident]} for ident in candidates[:count]]


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


def phases_of(spec: str | None) -> set[str] | None:
    """`--phases body,call` -> that set, or None for all of them.

    Naming an unknown phase is an error rather than a silent no-op: a run that
    measures nothing because of a typo is worse than one that refuses to start.
    """
    if not spec:
        return None
    wanted = {part.strip().lower() for part in spec.split(",") if part.strip()}
    unknown = wanted - set(PHASES)
    if unknown:
        raise SystemExit(
            f"unknown phase(s): {', '.join(sorted(unknown))}; "
            f"known: {', '.join(PHASES)}"
        )
    return wanted


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
    corpus = Corpus(load(Path(args.path)))
    files = corpus.files
    if not files:
        print("no source files", file=sys.stderr)
        return 1
    words = words_of(args.question)
    if getattr(args, "rank_only", False):
        # The ranking without the content: for an agent that wants to choose its
        # own reads, or a human checking that the question is even landing.
        ranked = rank(files, words, args.question)
        if not ranked:
            print(f"no match for {args.question!r} in {len(files)} files", file=sys.stderr)
            return 0
        for score, source in ranked:
            print(f"{score:8.2f}  {source.path}")
        print(f"\n{len(ranked)} of {len(files)} files matched", file=sys.stderr)
        return 0

    if getattr(args, "explain", False):
        print("rank (score  path)", file=sys.stderr)
        for score, source in rank(files, words, args.question)[:5]:
            print(f"{score:8.2f}  {source.path}", file=sys.stderr)
    started = time.perf_counter()
    rc = load_rc(Path(args.path))
    budget = args.budget if args.budget is not None else int(rc.get("budget", "4000"))
    expand = args.expand
    if rc.get("expand", "").lower() in {"off", "false", "0", "no"}:
        expand = False
    phases = phases_of(getattr(args, "phases", None))
    if args.lean:
        body, used, chunks = build_context_lean(corpus, words, budget, args.question)
    else:
        body, used, chunks = build_context(
            corpus, words, budget, expand=expand, phrase=args.question,
            phases=phases,
        )
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
    corpus = Corpus(load(Path(args.path)))
    files = corpus.files
    if not files:
        print("no source files", file=sys.stderr)
        return 1
    queries = auto_queries(
        files, args.queries, args.seed, args.rare, code_only=args.code_only
    )
    if not queries:
        print("no queries generated", file=sys.stderr)
        return 1

    # The whole corpus is the same string for every question, so it is built once.
    # 100 queries were each rebuilding two million tokens of text for a number that
    # cannot change between them.
    whole: list[tuple[str, int]] = []

    def read_all(_words, _phrase):
        if not whole:
            body = "\n\n".join(f"### {s.path}\n{s.text}" for s in files)
            whole.append((body, tokens(body)))
        return whole[0]

    def grep(words, _phrase):
        body = "\n\n".join(
            f"### {s.path}\n{s.text}" for s in files
            if any(word in s.low for word in words)
        )
        return body, tokens(body)

    def lean(words, phrase):
        return build_context_lean(corpus, words, args.budget, phrase)[:2]

    phases = phases_of(getattr(args, "phases", None))

    def intelligence(words, phrase):
        return build_context(
            corpus, words, args.budget, phrase=phrase, phases=phases
        )[:2]

    policies = {
        "read_all": read_all,
        "grep": grep,
        "lean": lean,
        "intelligence": intelligence,
    }

    scope = " (code-only)" if getattr(args, "code_only", False) else ""
    print(f"corpus: {args.path}  files: {len(files)}  queries: {len(queries)}  "
          f"budget: {args.budget}{scope}")
    print("objective: recall first, tokens second, speed third")
    print("tokens is what the policy ACTUALLY emitted; over = it blew the budget")
    print("recall is a proportion of the queries, so its 95% interval follows it:")
    print("a one-query difference sits inside that bracket and is not a result\n")
    print("| policy | recall | tokens | over | ms |")
    print("| --- | --- | --- | --- | --- |")
    rows = []
    for name, build in policies.items():
        total_recall = 0.0
        total_tokens = 0
        over = 0
        started = time.perf_counter()
        for query in queries:
            needles = query["needles"]
            context, used = build(words_of(needles[0]), needles[0])
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
        # `mean_recall` is a proportion; `wilson` wants a count of successes and
        # divides by the total itself. Passing the proportion made it divide by
        # 100 twice, so every row printed an interval centred near 0.009 — the
        # same (0.002-0.054) for recall 1.000 and 0.940 — which silently disabled
        # the guard against calling one query a result.
        low, high = wilson(round(mean_recall * len(queries)), len(queries))
        print(
            f"| {name} | {mean_recall:.3f} ({low:.3f}-{high:.3f}) | "
            f"{mean_tokens:.0f} | {flag} | {mean_ms:.1f} |"
        )

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

    if getattr(args, "diagnose", False):
        # Where do the misses come from? A needle whose file was never ranked is a
        # ranking problem; one whose file ranked but whose content never reached
        # the context is a budget or phase-order problem. Different fixes, so they
        # are counted apart instead of guessed at.
        missed = 0
        not_ranked = 0
        not_emitted = 0
        missing_file = 0
        positions: list[int] = []
        for query in queries:
            needles = query["needles"]
            words = words_of(needles[0])
            context, _used = intelligence(words, needles[0])
            if recall_of(context, needles) >= 1.0:
                continue
            missed += 1
            holders = [s.path for s in files if needles[0] in s.text]
            if not holders:
                missing_file += 1
                continue
            ranked_list = [source.path for _score, source in rank(files, words, needles[0])]
            ranked_paths = set(ranked_list)
            hit = [path for path in holders if path in ranked_paths]
            if not hit:
                not_ranked += 1
            else:
                not_emitted += 1
                # Which rank did the file holding the answer sit at? A file inside
                # the top ranks that still never surfaced is a phase bug, not a
                # budget one, and the two need opposite fixes.
                positions.append(min(ranked_list.index(path) for path in hit) + 1)
        detail = ""
        if positions:
            positions.sort()
            inside = sum(1 for p in positions if p <= 10)
            detail = (
                f" (rank of the missed file: median {positions[len(positions) // 2]}, "
                f"within top 10: {inside}/{len(positions)})"
            )
        print(
            f"\ndiagnose: {missed} misses -- never ranked: {not_ranked}, "
            f"ranked but not emitted: {not_emitted}, absent from corpus: {missing_file}{detail}"
        )

    if getattr(args, "json", False):
        print(json.dumps({
            "corpus": args.path,
            "files": len(files),
            "queries": len(queries),
            "budget": args.budget,
            "policies": {
                name: {
                    "recall": round(recall, 3),
                    "tokens": round(tokens_, 0),
                    "over_budget": over,
                    "ms": round(ms, 1),
                }
                for recall, tokens_, over, ms, name in rows
            },
        }, indent=2))

    # A measurement nobody reads is a claim. CI shows a green job's console output
    # to nobody who is deciding, and the failure log is the only channel that
    # reaches back. So a floor turns the bench into a regression test: above it,
    # nothing happened; below it, the numbers are forced back into view.
    floor = getattr(args, "floor", None)
    if floor is not None:
        recall_by_name = {name: recall for recall, _t, _o, _m, name in rows}
        got = recall_by_name.get("intelligence", 0.0)
        if got < floor:
            print(
                f"\nFLOOR MISSED: intelligence recall {got:.3f} < {floor:.3f} "
                f"on {args.path} ({len(queries)} queries, budget {args.budget})",
                file=sys.stderr,
            )
            return 1
        print(f"\nfloor held: intelligence recall {got:.3f} >= {floor:.3f}")
    return 0


def cmd_next(args) -> int:
    """What this version still misses, named precisely enough to fix.

    `ctx bench` says how many answers were missed and that they sit at median rank
    1. It does not say which query, which file, or whether the needle's line was
    inside an emitted range — and without those the next change is a guess again.

    Coverage is decided by the ranges `plan_context` actually chose, not by
    searching the rendered text for a line. The old check could only fire when a
    line had been emitted *and* still failed the recall test, which cannot happen
    while the needle is on that line, so the branch was unreachable and its real
    case — the line cut at 200 characters — was reported as a block-selection
    fault. That named the wrong phase to fix.
    """
    corpus = Corpus(load(Path(args.path)))
    if not corpus.files:
        print("no source files", file=sys.stderr)
        return 1
    queries = auto_queries(
        corpus.files, args.queries, args.seed, args.rare, code_only=args.code_only
    )
    if not queries:
        print("no queries generated", file=sys.stderr)
        return 1

    phases = phases_of(getattr(args, "phases", None))
    misses: list[dict] = []
    for query in queries:
        needle = query["needles"][0]
        words = words_of(needle)
        chunks = plan_context(
            corpus, words, args.budget, phrase=needle, phases=phases
        )
        context = render_context(chunks)[0] if chunks else ""
        if recall_of(context, query["needles"]) >= 1.0:
            continue
        holders = [source for source in corpus.files if needle in source.text]
        if not holders:
            continue
        ranked_paths = [
            source.path for _score, source in rank(corpus.files, words, needle)
        ]
        for holder in holders:
            hits = hit_lines(holder, [needle.lower()])
            if not hits:
                continue
            line = hits[0]
            position = (
                ranked_paths.index(holder.path) + 1
                if holder.path in ranked_paths else 0
            )
            covering = [
                chunk for chunk in chunks
                if chunk.path == holder.path and chunk.kind != "map"
                and chunk.start <= line < chunk.end
            ]
            if covering:
                # Reachable only when the block covering this line still does not
                # contain the needle in its rendered text. The previous version
                # also had a "line emitted but needle absent" branch, which cannot
                # fire while the needle is on that line — an unreachable
                # classification is worse than none, so it is gone.
                why = "the block covering this line omits the needle after clipping"
            elif position == 0:
                why = "file never ranked"
            elif position <= 10:
                why = "ranked in the top 10; the chosen blocks missed the line"
            else:
                why = f"ranked {position}; never reached"
            misses.append({
                "needle": needle,
                "path": holder.path,
                "line": line + 1,
                "rank": position,
                "why": why,
            })

    if getattr(args, "json", False):
        print(json.dumps({
            "corpus": args.path,
            "queries": len(queries),
            "rare": args.rare,
            "budget": args.budget,
            "misses": misses,
        }, indent=2))
        return 0

    scope = " (code-only)" if getattr(args, "code_only", False) else ""
    print(f"next: {len(misses)} misses on {args.path} "
          f"({len(queries)} queries, rare<={args.rare}, budget {args.budget}){scope}")
    for number, miss in enumerate(misses, 1):
        where = f"rank {miss['rank']}" if miss["rank"] else "never ranked"
        print(f"{number}. {miss['needle']}")
        print(f"   {miss['path']}:{miss['line']} ({where}) -- {miss['why']}")
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
    assert is_ignored(Path("build/x.py"), ["/build"]), "an anchored pattern matches at the root"
    assert not is_ignored(Path("src/build/x.py"), ["/build"]), "an anchored pattern stays shallow"
    checks += 4

    far = "x" * 400 + " needle " + "y" * 400
    assert "needle" in clip_line(far, ["needle"]), "a long line must keep the word asked about"
    assert "needle" not in far[:LINE_CAP], "the head clip is exactly what used to lose it"
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
        corpus = Corpus(files)
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

        # The interval has to move with the value, or it is decoration. 94 of 100
        # is reported around 0.88-0.97, and a perfect score is still not certain.
        lo, hi = wilson(94, 100)
        assert 0.87 < lo < 0.91 and 0.96 < hi < 0.99, f"wilson(94,100) gave {lo:.3f}-{hi:.3f}"
        lo, hi = wilson(100, 100)
        assert 0.94 < lo < 0.99 and hi > 0.99, f"wilson(100,100) gave {lo:.3f}-{hi:.3f}"
        lo, hi = wilson(0, 100)
        assert lo == 0.0 and hi < 0.05, f"wilson(0,100) gave {lo:.3f}-{hi:.3f}"
        checks += 3

        ranked = rank(files, ["refresh", "token"])
        assert ranked and ranked[0][1].path == "alpha.py", "definition-bearing file must rank first"
        checks += 1

        # A lookup, not a topic: the file holding the identifier verbatim beats a
        # file that only repeats its parts. Forty mentions of `max` score ~40; the
        # single `maxMb` declaration scores ~15. Without the tier the noisy file
        # wins, which is how 2.24.0 left three needles at ranks 13, 37 and 130.
        noisy = Source("noise.py", "max = 1\n" * 40)
        holder = Source("answer.py", "def maxMb(limit):\n    return min(limit, maxMb)\n")
        lookup_ranked = rank([noisy, holder], words_of("maxMb"), "maxMb")
        assert lookup_ranked[0][1].path == "answer.py", \
            "an identifier lookup must outrank a file that only repeats its parts"
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

        body, used, chunks = build_context(corpus, ["refresh", "token"], 4000)
        assert "refresh_token" in body, "the context must surface the needle"
        assert "value.strip()" in body, "the enclosing body must be complete, not a +-4 window"
        assert body.startswith("# context ("), "the context must say what it is"
        assert used <= 4000, f"budget exceeded: {used}"
        assert chunks >= 1, "expected at least one chunk"
        checks += 4

        _tight, tight_used, _ = build_context(corpus, ["refresh", "token"], 64)
        assert tight_used <= 64, f"budget exceeded on the tight run: {tight_used}"
        checks += 1

        _lean_body, lean_used, _ = build_context_lean(
            corpus, ["refresh", "token"], 4000
        )
        assert lean_used <= 4000, "lean budget exceeded"
        checks += 1

        assert recall_of(body, ["refresh_token"]) == 1.0, "recall must find a present needle"
        assert recall_of(body, ["absent_symbol"]) == 0.0, "recall must miss an absent needle"
        checks += 2

        index = stem_index(files)
        beta = next(f for f in files if f.path == "beta.py")
        assert "alpha.py" in related(beta, index), "beta imports alpha, resolved by stem"
        checks += 1

        # 2.23.0 — the call-site phase had never emitted a single chunk. It looked a
        # declared name up whole in an index keyed by its split parts, and the phase
        # before it had overwritten that index anyway. Both faults are pinned here.
        leader = Source(
            "leader.py",
            "def refresh_token():\n"
            "    refresh token refresh token refresh token\n"
            "    return 1\n",
        )
        followers = [
            Source(
                f"follower{i}.py",
                "def use_leader():\n    return leader.refresh_token()\n",
            )
            for i in range(5)
        ]
        call_body, _call_used, _call_n = build_context(
            Corpus([leader] + followers), ["refresh", "token"], 4000, phases={"call"}
        )
        assert "follower" in call_body, f"call sites must reach the context: {call_body!r}"
        checks += 1

        # A block that does not fit must narrow, not vanish: the old emitter threw
        # away the last few hundred tokens of every query rather than shrinking.
        huge = Source(
            "huge.py",
            "def giant():\n"
            + "\n".join(f"    step_{i} = {i}" for i in range(200))
            + "\n    needle_here()\n",
        )
        shrunk, shrunk_used, _ = build_context(Corpus([huge]), ["needle", "here"], 120)
        assert "needle_here()" in shrunk, f"a block that does not fit must narrow: {shrunk!r}"
        assert shrunk_used <= 120, f"narrowing must respect the budget: {shrunk_used}"
        checks += 2

        # The reported cost is the cost: labels and header are inside the count.
        assert used == tokens(body), f"reported {used} but emitted {tokens(body)}"
        checks += 1

        # Many small blocks is the shape that exposed the overshoot: charging each
        # block a floored token count lost a fraction per block and the separators
        # were never counted, so 2.23.0 reported 15 of 100 queries over budget.
        many = [
            Source(f"tiny{i}.py", f"def handler():\n    refresh token\n    return {i}\n")
            for i in range(40)
        ]
        tiny_text, tiny_used, tiny_n = build_context(
            Corpus(many), ["refresh", "token"], 200
        )
        assert tiny_used <= 200, f"budget overshot: {tiny_used} > 200"
        assert tiny_used == tokens(tiny_text), "reported cost must be the emitted cost"
        assert tiny_n > 5, f"expected several chunks through the budget, got {tiny_n}"
        checks += 3

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
        parser_.add_argument(
            "--rank-only", dest="rank_only", action="store_true",
            help="print the ranked files and scores, no content",
        )
        parser_.add_argument(
            "--phases", default=None,
            help="comma-separated phases to run: " + ",".join(PHASES)
                 + " (default all); naming one is how its contribution is measured",
        )

    p_bench = sub.add_parser("bench", help="recall, then tokens, then time")
    p_bench.add_argument("path")
    p_bench.add_argument("--queries", type=int, default=25)
    p_bench.add_argument("--budget", type=int, default=4000)
    p_bench.add_argument("--seed", type=int, default=0)
    p_bench.add_argument(
        "--rare", type=int, default=2,
        help="needles appear in at most this many files; 1 is the hard case",
    )
    p_bench.add_argument(
        "--diagnose", action="store_true",
        help="classify the misses: never ranked vs ranked but not emitted",
    )
    p_bench.add_argument("--json", action="store_true", help="machine-readable results")
    p_bench.add_argument(
        "--code-only", action="store_true",
        help="choose needles from code files only, skipping prose (README, .txt)",
    )
    p_bench.add_argument(
        "--floor", type=float, default=None,
        help="exit 1 when intelligence recall falls below this; makes the bench a "
             "regression test CI can enforce, and a failure the only report that "
             "reaches the agent",
    )
    p_bench.add_argument(
        "--phases", default=None,
        help="comma-separated phases to run: " + ",".join(PHASES) + " (default all)",
    )
    p_bench.set_defaults(func=cmd_bench)

    p_next = sub.add_parser(
        "next",
        help="what the current version still misses, for the next version to fix",
    )
    p_next.add_argument("path")
    p_next.add_argument("--queries", type=int, default=25)
    p_next.add_argument("--budget", type=int, default=4000)
    p_next.add_argument("--seed", type=int, default=0)
    p_next.add_argument(
        "--rare", type=int, default=1,
        help="needles appear in at most this many files; 1 is the hard case",
    )
    p_next.add_argument(
        "--code-only", action="store_true",
        help="choose needles from code files only, skipping prose (README, .txt)",
    )
    p_next.add_argument(
        "--phases", default=None,
        help="comma-separated phases to run: " + ",".join(PHASES) + " (default all)",
    )
    p_next.add_argument("--json", action="store_true", help="machine-readable misses")
    p_next.set_defaults(func=cmd_next)

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
