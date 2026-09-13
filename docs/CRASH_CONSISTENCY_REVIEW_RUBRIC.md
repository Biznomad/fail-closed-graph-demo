# Crash-consistency review rubric

Use this rubric to review the narrow persistence claim in this repository. It is not a security, production-readiness, or distributed-systems assessment.

## Review verdict

Return exactly one verdict and cite the evidence used:

- **PASS** — every in-scope invariant is demonstrated and no contradiction was found.
- **FAIL** — an in-scope invariant is contradicted by a reproducible observation.
- **INCONCLUSIVE** — the available evidence cannot distinguish safe recovery from unsafe continuation.
- **SETUP-BLOCKED** — the documented clean-room procedure could not be completed; record the exact command, exit code, and error.

## In-scope invariants

1. A transition is accepted only for the current `work_key`.
2. Retryable failure cannot exceed `max_attempts`.
3. The receipt is appended and synced before snapshot replacement is attempted.
4. The live object is poisoned before persistence begins and refuses more work while persistence is uncertain.
5. Resume rejects a malformed, noncontiguous, hash-inconsistent, or snapshot-conflicting durable record.
6. When the journal is one or more valid records ahead of the snapshot, resume reconstructs and rewrites the snapshot from the latest validated receipt.
7. A successful verification receipt names the exact checks, environment, and hashes for the files it evaluated.

## Five crash windows

| Window | Interruption point | Known evidence | Safe review question | Expected disposition |
|---|---|---|---|---|
| 1 | Before the intended external action | Intent may exist; no action acknowledgment or local receipt | Is there evidence the action was attempted? | Stop or query; do not infer execution from intent. |
| 2 | After request, before acknowledgment | Request may have crossed the boundary; outcome is unknown | Can the authoritative external system be queried by an idempotency/event key? | Query or escalate; blind retry is out of scope and unsafe to assume. |
| 3 | After acknowledgment, before durable local receipt | External effect may be confirmed; local evidence is absent | Can acknowledgment be recovered independently? | Reconcile or escalate; do not claim this demo solves it. |
| 4 | After durable receipt, before snapshot replacement | Journal may be ahead of snapshot | Does the live object refuse work, and does resume rebuild from the validated journal? | Reload from durable evidence; this is the repository's primary demonstrated window. |
| 5 | After snapshot replacement, before in-memory confirmation | Durable snapshot may be ahead of the live object | Is the live object still poisoned until the method completes, or must the process reopen? | Stop/reopen if completion is uncertain. |

Windows 1–3 describe tool-using workflows but are not implemented as external actions in this repository. The executable reproduction directly exercises local receipt/snapshot ordering and recovery, especially windows 4–5.

## Evidence to collect

- Exact repository revision or archive hash.
- Python implementation/version and operating system.
- Command, exit code, and unedited stdout/stderr.
- Generated verification receipt and its SHA-256 recorded outside the receipt.
- Any changed files and their hashes.
- Minimal reproduction for each contradiction.

## Counterexample prompts

Try to establish one of these rather than seeking confirmation:

1. Can the same stale `work_key` append a second transition?
2. Can a third retry occur when `max_attempts=2`?
3. Can an object accept work after receipt append succeeds but snapshot replacement fails?
4. Can a valid journal-ahead state resume to the stale snapshot instead of the latest receipt?
5. Can an edited receipt be accepted while an unchanged later record or snapshot still anchors the old hash?
6. Can a snapshot ahead of the journal be accepted?
7. Can the verifier return zero when compilation, the expected seven-test report, or any evaluation scenario fails?

For a FAIL, include the smallest reproducible sequence. For INCONCLUSIVE, identify the missing observation that would decide the issue.

## Explicitly out of scope

- Power-loss durability guarantees of a particular filesystem, disk controller, or storage service.
- Directory-entry durability after `os.replace` on every platform.
- Multiple writers, process locking, distributed consensus, or cross-host replication.
- A malicious actor who can coherently rewrite the journal, snapshot, code, and external hash record.
- External API idempotency, acknowledgment recovery, model behavior, tool permissions, or sandboxing.
- Production safety, security certification, uptime, customer impact, adoption, or business outcomes.

## Acceptance gate

A review is complete only when the verdict, environment, command, receipt/hash, and any contradiction are recorded. Silence, a screenshot without command output, or a general endorsement is not a review result.
