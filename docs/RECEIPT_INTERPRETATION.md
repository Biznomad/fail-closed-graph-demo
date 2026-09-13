# Verification receipt interpretation

`verify_release.py` emits `VERIFICATION_RECEIPT.json`. The receipt is an inspectable run record, not a signature, certificate, deployment receipt, or guarantee.

## Field guide

| Field | What it establishes when independently read back | What it does not establish |
|---|---|---|
| `schema_version` | The JSON uses the documented receipt shape version. | Backward compatibility or external standard compliance. |
| `artifact` | The verifier labeled the evaluated package `fail-closed-graph-demo`. | Repository identity, ownership, or provenance by itself. |
| `generated_at_utc` | The verifier recorded a UTC timestamp when it built the receipt. | Trusted time or protection against clock manipulation. |
| `passed` | Every check represented in this run evaluated true. | That every relevant behavior was tested. |
| `checks.compile` | Python compilation returned zero for the five named Python files. | Static analysis, type correctness, or runtime correctness. |
| `checks.unit_tests` | The test command returned zero and reported the expected seven tests. | Coverage completeness or absence of untested defects. |
| `checks.evaluation` | Four scenarios attempted the recorded iteration count, with totals and failures captured. | Real workloads, random fault coverage, production reliability, or statistical guarantees. |
| `environment` | Python implementation/version and operating-system family reported by the runtime. | Hardware, filesystem, kernel, container, or host identity. |
| `files.*.sha256` | Exact bytes of each evaluated Python file map to the recorded SHA-256. | Authorship, trust, malicious coherent rewriting, or a signed release. |
| `elapsed_seconds` | Approximate local elapsed time for this run. | A benchmark or performance claim. |
| `privacy` | The receipt is designed to omit username, hostname, absolute path, and environment variables. | A universal privacy or secret-leakage guarantee for every future change. |

## Required interpretation of a pass

Safe wording:

> On the recorded environment and timestamp, the verifier compiled the hashed checkout, observed seven expected passing unit tests, and passed the recorded synthetic scenario total.

Do not convert that statement into production safety, security certification, public CI, external human validation, adoption, uptime, revenue, customer impact, or general correctness.

## Integrity and provenance boundary

The file hashes bind the receipt's claims to source bytes, but the receipt is not self-authenticating. Preserve its SHA-256 in an independent review record, CI artifact record, or evidence ledger. A party able to rewrite both the files and all copies of the receipt can create a coherent replacement. A signed release or external transparency anchor would be required for a stronger provenance claim.

## Failure handling

- Nonzero process exit: classify as FAIL or SETUP-BLOCKED after reading stdout/stderr.
- Missing receipt: do not infer a result.
- Receipt says `passed: false`: do not summarize partial passes as overall success.
- File hash mismatch: rerun from the intended clean revision or classify the evidence as inconclusive.
- Expected test/scenario count mismatch: fail closed; investigate the changed test surface before updating any public number.
