from __future__ import annotations

import argparse
import hashlib
import json
import platform
import subprocess
import sys
import tempfile
import time
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parent
PYTHON_FILES = (
    "graph_demo.py",
    "test_graph_demo.py",
    "evaluate.py",
    "verify_release.py",
    "test_verifier_guards.py",
    "comparisons/__init__.py",
    "comparisons/recovery_contract.py",
    "comparisons/test_recovery_contract.py",
)


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def run(command: list[str]) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        command,
        cwd=ROOT,
        text=True,
        capture_output=True,
        check=False,
    )


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Run the release-candidate checks and emit a privacy-safe JSON receipt."
    )
    parser.add_argument("--iterations", type=int, default=100)
    parser.add_argument("--output", type=Path, default=ROOT / "VERIFICATION_RECEIPT.json")
    args = parser.parse_args()
    if args.iterations < 1 or args.iterations > 10000:
        parser.error("--iterations must be between 1 and 10000")

    started = time.perf_counter()
    checks: dict[str, dict[str, object]] = {}

    compile_result = run([sys.executable, "-m", "py_compile", *PYTHON_FILES])
    checks["compile"] = {
        "passed": compile_result.returncode == 0,
        "return_code": compile_result.returncode,
    }

    unit_result = run([sys.executable, "-m", "unittest", "-v", "test_graph_demo.py"])
    unit_output = unit_result.stdout + unit_result.stderr
    checks["unit_tests"] = {
        "passed": unit_result.returncode == 0 and "Ran 7 tests" in unit_output,
        "return_code": unit_result.returncode,
        "expected_tests": 7,
        "reported_expected_count": "Ran 7 tests" in unit_output,
    }

    comparison_result = run(
        [sys.executable, "-m", "unittest", "-v", "comparisons/test_recovery_contract.py"]
    )
    comparison_output = comparison_result.stdout + comparison_result.stderr
    checks["comparison_contract_tests"] = {
        "passed": comparison_result.returncode == 0 and "Ran 12 tests" in comparison_output,
        "return_code": comparison_result.returncode,
        "expected_tests": 12,
        "reported_expected_count": "Ran 12 tests" in comparison_output,
    }

    with tempfile.TemporaryDirectory() as temporary:
        evaluation_path = Path(temporary) / "evaluation.json"
        evaluation_result = run(
            [
                sys.executable,
                "evaluate.py",
                "--iterations",
                str(args.iterations),
                "--output",
                str(evaluation_path),
            ]
        )
        evaluation: dict[str, object] = {}
        if evaluation_path.exists():
            evaluation = json.loads(evaluation_path.read_text(encoding="utf-8"))
        expected_total = args.iterations * 4
        evaluation_passed = (
            evaluation_result.returncode == 0
            and evaluation.get("total_attempted") == expected_total
            and evaluation.get("total_passed") == expected_total
            and evaluation.get("failures") == []
        )
        checks["evaluation"] = {
            "passed": evaluation_passed,
            "return_code": evaluation_result.returncode,
            "iterations_per_scenario": args.iterations,
            "total_attempted": evaluation.get("total_attempted"),
            "total_passed": evaluation.get("total_passed"),
            "failures": evaluation.get("failures"),
        }

    passed = all(bool(check["passed"]) for check in checks.values())
    receipt = {
        "schema_version": 1,
        "artifact": "fail-closed-graph-demo",
        "generated_at_utc": datetime.now(timezone.utc).isoformat(),
        "passed": passed,
        "checks": checks,
        "environment": {
            "python": platform.python_version(),
            "implementation": platform.python_implementation(),
            "operating_system": platform.system(),
        },
        "files": {name: {"sha256": sha256(ROOT / name)} for name in PYTHON_FILES},
        "elapsed_seconds": round(time.perf_counter() - started, 6),
        "privacy": "Receipt excludes username, hostname, absolute path, and environment variables.",
    }
    text = json.dumps(receipt, indent=2, sort_keys=True) + "\n"
    output = args.output if args.output.is_absolute() else ROOT / args.output
    output.write_text(text, encoding="utf-8")
    print(text, end="")
    return 0 if passed else 1


if __name__ == "__main__":
    raise SystemExit(main())
