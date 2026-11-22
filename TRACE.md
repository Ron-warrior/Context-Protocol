# Trace — the loop's instrumentation

A self-improving loop is only real if the thing it measures is countable from the
transcript. So nothing here is self-reported feeling. Every unit below can be
audited by replaying the tool calls.

## What is counted

| Unit | Definition | Audited from |
| --- | --- | --- |
| calls | tool invocations used to finish the task | the transcript |
| authored | lines written by the agent | `create_file` / `modify_file` arguments |
| read-back | lines of an authored region read *after* writing it | `read_file` `offset`/`limit` |
| coverage | read-back ÷ authored, for code | division |
| last-op | was the final operation on a touched region a **read**? | the last tool call touching it |
| strikes | reads that did not advance the question | the trace, judged |
| violations | rules in README.md that the trace shows broken | trace vs README |

**Not counted:** "intelligence", "quality", "how good the writing is". There is no
instrument for those here, so this file makes no claim about them. It measures
effectiveness per token, verification coverage, and calls per resolved task.

## Two speeds

- **Fast loop — inside one chat.** A rule that fails is rewritten immediately and
  governs the next action in the same conversation. Cheap, because the failure is
  still in context.
- **Slow loop — across chats.** README.md is preloaded into every chat of this
  project, so a promoted rule reaches work it was never derived from. This is the
  only mechanism by which a correction outlives the conversation that produced it.

Cross-session self-improvement is therefore real but narrow: it propagates *rules*,
not experience. The trace is what carries the evidence between them.

## Trace: v1.0.0 — the version that produced v1.1.0

Task: research the state of the art and write the protocol, docs and bench.

| Unit | Measured |
| --- | --- |
| calls | 15 |
| authored | 824 lines (441 code, 383 docs) |
| read-back — code | 202 / 441 |
| **coverage — code** | **46%** |
| read-back — docs | 0 / 383 |
| **last-op on the code file** | **write** (a hoisting edit made after the final read) |
| violations | 1 |

**The violation.** README v1.0.0 rung 5 said: *"After any edit: re-read the edited
region."* Time-ordered, and therefore satisfiable by accident. In practice I read
two windows of the bench, then edited it, and never re-read the edited region — so
the last operation on the file was a write. 239 lines were never read at all
before or after being written.

That is the whole justification for v1.1.0: the rule was **not checkable** in the
state it was written in, so it was followed by coincidence and broken silently.

## Trace: v1.1.0 — the version fixing it

The same turn that wrote v1.1.0 applied it: read the unread 239 lines *before*
claiming anything, then re-read each edited region *after* editing.

Result: three defects in the v1.0.0 bench, found in one pass, all in code I had
shipped at 46% coverage.

| Defect | Kind | Cost if shipped |
| --- | --- | --- |
| `break` instead of `continue` in the ladder's heading loop | logic | One large outline starves every smaller one → the policy under test scores worse than it should |
| Unused `by_path` set | dead code | Nothing, but it is a tell that the region was never read |
| No shape check on `--queries` JSON | robustness | A JSON object instead of an array crashes with a `TypeError` |

Read-back cost: ~11k tokens to read 239 lines plus three edited regions.

Read-back return: three defects, one of which would have silently biased the
benchmark that is supposed to justify the protocol.

**That exchange rate is the argument for the rule.** Reviewing code you just
wrote is not diligence theatre; at 46% coverage it was the difference between a
harness that measures something and one that measures a bug.
