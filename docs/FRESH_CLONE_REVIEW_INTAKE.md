# Fresh-clone review intake

**Status: staged template — do not use for external review until a public repository and immutable revision exist.**

This template is for an independent usability or crash-consistency review after a public repository and immutable revision exist. Repository publication and reviewer contact remain owner-approved external actions.

## Consent and attribution

- Reviewer role (avoid unnecessary personal data):
- Permission to retain these private review notes: **yes / no**
- Permission to identify reviewer publicly: **none / role only / named exact wording**
- Permission to quote findings publicly: **none / anonymous / named exact wording**
- Permission to treat feedback as a testimonial: **no unless separately and explicitly granted**

If note-retention permission is **no**, stop substantive note-taking and retain only the minimum consent/outcome receipt allowed by the reviewer.

## Clean-room setup

1. Start from a new clone or clean copied directory; do not reuse the author's virtual environment or generated files.
2. Record the immutable commit SHA or archive SHA-256.
3. Confirm Python 3.11 or newer.
4. From the repository root, run:

```text
python verify_release.py --iterations 100 --output VERIFICATION_RECEIPT.audit.json
```

5. Record the shell exit code. Do not infer success from the presence of a JSON file.
6. Preserve the receipt and record its SHA-256 outside the repository receipt.

No third-party package, provider credential, network access, model, or service configuration should be required after the source is obtained.

## Environment capture

- Review date/time and timezone:
- Operating system:
- Python implementation/version:
- Commit/archive identifier:
- Exact command:
- Exit code:
- Receipt SHA-256:

Do not record username, hostname, home-directory path, environment variables, credentials, customer data, or private repository names.

## Expected evidence

A passing run must independently show all of the following:

- compilation passed;
- exactly seven expected unit tests were reported and passed;
- four named scenarios ran 100 times each;
- total evaluation result is 400/400 with an empty failure list;
- the receipt records the environment and SHA-256 for the five evaluated Python files;
- the process returned exit code `0`.

A mismatch, omitted check, or nonzero exit means the run is not a pass even if other checks succeeded.

## Confusion log

Record each undocumented or ambiguous step before asking the author for help.

| Step | Expected | Observed | Exact error/output | Assistance needed? |
|---|---|---|---|---|
| | | | | |

## Defect template

- Short title:
- Rubric invariant/window:
- Starting revision and environment:
- Minimal reproduction commands:
- Expected result:
- Actual result:
- Exit code:
- Relevant file/receipt hashes:
- Does a fresh retry reproduce it? **yes / no / not attempted**
- Severity within this demo: **blocking / material / minor**
- Scope caveat:

## Final disposition

Select one: **PASS / FAIL / INCONCLUSIVE / SETUP-BLOCKED**

Evidence summary:

Contradictions or confusing setup:

Suggested next falsification test:

The disposition is technical feedback, not permission to publish the reviewer's identity, words, or endorsement.
