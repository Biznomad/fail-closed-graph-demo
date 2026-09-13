# Release checklist

**Target repository:** `Biznomad/fail-closed-graph-demo`  
**State:** locally staged; external creation and push require owner approval.

## Verified locally

- [x] Unit tests pass on the release candidate (7/7 on 2026-09-09, Windows/CPython 3.12.5).
- [x] Repeated evaluation passes 400/400 scenarios (2026-09-09, Windows/CPython 3.12.5).
- [x] Python compilation passes.
- [x] Recorded source and test hashes match current bytes.
- [x] One-command release verifier compiles the checkout, requires seven reported tests, runs 400 scenarios, and emits a privacy-safe receipt.
- [x] Verification receipts carry a UTC generation timestamp; CI preserves each OS/Python receipt pair as an artifact.
- [x] Two clean-copy mutation guards prove the verifier returns nonzero if tampered receipts are accepted or an evaluation scenario is deliberately broken.
- [x] Crash-consistency rubric, fresh-clone intake, and receipt-interpretation documents define review evidence and limitations.
- [x] Identifier, credential, private-path, bot-name, IP-address, and customer-data scan produced no sensitive-value finding; its only two keyword matches were the safety-policy/checklist wording itself.
- [x] `__pycache__` and generated local state are excluded by `.gitignore`.

## External release steps — approval gated

1. Create a public GitHub repository named `fail-closed-graph-demo` under `Biznomad`.
2. Push only the contents of this directory.
3. Confirm the default branch and repository visibility by API readback.
4. Confirm the CI matrix completes on Linux, Windows, and macOS.
5. From a fresh clone, run `python verify_release.py --iterations 100 --output VERIFICATION_RECEIPT.audit.json` and `python -m unittest -v test_verifier_guards.py`; require process exit `0`, receipt field `passed: true`, seven behavioral tests, twelve comparative contract tests, 400/400 scenarios, and two structured-failure mutation guards before preserving the non-manifest receipt and reviewer findings.
6. Confirm README, LICENSE, SECURITY, and limitations render correctly.
7. Record the public URL, commit SHA, release tag, CI run URL, and fresh-clone receipt hash in the evidence ledger.
8. Publish no social post until the repository URL returns 200 and the claim scan is repeated against the public bytes.

## Representation contract

Permitted: “A public-safe Python reproduction passed seven unit tests and 400/400 repeated synthetic scenarios on the dated local release candidate.”

Not permitted: claims of production deployment, production reliability, security certification, customer adoption, uptime, revenue, or business impact.
