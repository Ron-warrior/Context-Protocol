"""Score what a model actually put in front of itself, on a fixed task set.

The protocol's claim is "the answer must be in the context", so the thing worth
scoring is not the model's prose but the text it chose to read. A submission is
the set of file ranges the model assembled; this script checks whether each
task's answer string is inside that set and what it cost.

No model judges anything. Ground truth is hand-written in `tasks.json`, which is
why it stays valid when `ctx` changes: the answers live in a fixture corpus, not
in the tool being measured.

Usage:
    python3 eval/score.py --submission mine.json
    python3 eval/score.py --submission mine.json --baseline

A submission is either ranges or whole files:

    {"ranges": [{"path": "service/auth.py", "start": 1, "end": 20}]}
    {"files": ["service/auth.py"]}

Line numbers are 1-based and inclusive, because that is how a reader counts.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))


def tokens(text: str) -> int:
    return max(1, len(text) // 4)


def load_tasks(path: Path) -> dict:
    data = json.loads(path.read_text(encoding="utf-8"))
    if "tasks" not in data or not isinstance(data["tasks"], list):
        raise SystemExit(f"{path} must hold a 'tasks' list")
    return data


def selected_text(corpus: Path, submission: dict) -> tuple[str, int]:
    """The text the model assembled, and the number of spans it took."""
    pieces: list[str] = []
    spans = 0
    for entry in submission.get("ranges", []):
        path = corpus / str(entry.get("path", ""))
        if not path.is_file():
            print(f"  skip (no such file): {entry.get('path')}", file=sys.stderr)
            continue
        lines = path.read_text(encoding="utf-8", errors="replace").splitlines()
        start = max(1, int(entry.get("start", 1)))
        end = min(len(lines), int(entry.get("end", len(lines))))
        if end < start:
            continue
        pieces.append("\n".join(lines[start - 1:end]))
        spans += 1
    for name in submission.get("files", []):
        path = corpus / str(name)
        if not path.is_file():
            print(f"  skip (no such file): {name}", file=sys.stderr)
            continue
        pieces.append(path.read_text(encoding="utf-8", errors="replace"))
        spans += 1
    return "\n".join(pieces), spans


def score(text: str, tasks: list[dict]) -> tuple[float, list[dict]]:
    low = text.lower()
    rows: list[dict] = []
    for task in tasks:
        found = task["answer"].lower() in low
        rows.append({
            "question": task["question"],
            "answer": task["answer"],
            "found": found,
        })
    hits = sum(1 for row in rows if row["found"])
    return (hits / len(tasks) if tasks else 0.0), rows


def report(label: str, produced: str, used: int, spans: int, tasks: list[dict]) -> float:
    recall, rows = score(produced, tasks)
    per_1k = recall / (used / 1000.0) if used else 0.0
    print(f"\n{label}")
    print(f"  recall {recall:.3f}   tokens {used}   spans {spans}   recall/1k {per_1k:.3f}")
    missed = [row for row in rows if not row["found"]]
    for row in missed:
        print(f"  missed: {row['answer']!r} ({row['question']})")
    return recall


def baseline(corpus: Path, tasks: list[dict], budget: int) -> None:
    """What `ctx` itself scores, for comparison on the same tasks."""
    try:
        import ctx
    except ImportError:
        print("\nbaseline: ctx.py not importable, skipped", file=sys.stderr)
        return
    files = ctx.load(corpus)
    if not files:
        print("\nbaseline: corpus empty, skipped", file=sys.stderr)
        return
    chunks = []
    for task in tasks:
        words = ctx.words_of(task["question"])
        produced, _used, _chunks = ctx.build_context(
            ctx.Corpus(files), words, budget, phrase=task["question"]
        )
        chunks.append(produced)
    text = "\n".join(chunks)
    # Measured the same way as a submission's text, so the two rows are
    # comparable. ctx's own figure would be a second measuring stick.
    report("baseline: ctx default, one query per task", text, tokens(text), len(chunks), tasks)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--submission", required=True, help="JSON of the ranges or files chosen")
    parser.add_argument("--tasks", default=str(ROOT / "eval" / "tasks.json"))
    parser.add_argument("--corpus", default=None, help="override the corpus path in tasks.json")
    parser.add_argument("--budget", type=int, default=4000, help="budget for the baseline")
    parser.add_argument("--baseline", action="store_true", help="also score ctx's own default")
    args = parser.parse_args()

    data = load_tasks(Path(args.tasks))
    corpus = Path(args.corpus) if args.corpus else ROOT / data["corpus"]
    if not corpus.is_dir():
        raise SystemExit(f"corpus not found: {corpus}")

    submission = json.loads(Path(args.submission).read_text(encoding="utf-8"))
    produced, spans = selected_text(corpus, submission)
    if not produced.strip():
        raise SystemExit("submission selected no text")

    recall = report("your submission", produced, tokens(produced), spans, data["tasks"])

    if args.baseline:
        baseline(corpus, data["tasks"], args.budget)

    hit = sum(1 for task in data["tasks"] if task["answer"].lower() in produced.lower())
    print(f"\n{hit} of {len(data['tasks'])} answers present, recall {recall:.3f}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
