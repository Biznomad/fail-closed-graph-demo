from __future__ import annotations

import json
import shutil
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent
COPY_FILES = (
    "graph_demo.py",
    "test_graph_demo.py",
    "evaluate.py",
    "verify_release.py",
    "test_verifier_guards.py",
    "comparisons/__init__.py",
    "comparisons/recovery_contract.py",
    "comparisons/test_recovery_contract.py",
)


class VerifierGuardTests(unittest.TestCase):
    """Black-box mutation checks kept separate from the expected seven unit tests."""

    def make_copy(self) -> Path:
        temporary = tempfile.TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        root = Path(temporary.name)
        for name in COPY_FILES:
            destination = root / name
            destination.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(ROOT / name, destination)
        return root

    def run_verifier(self, root: Path) -> subprocess.CompletedProcess[str]:
        return subprocess.run(
            [
                sys.executable,
                "verify_release.py",
                "--iterations",
                "1",
                "--output",
                "mutation-receipt.json",
            ],
            cwd=root,
            text=True,
            capture_output=True,
            check=False,
        )

    def assert_clean_failure(
        self,
        result: subprocess.CompletedProcess[str],
        root: Path,
        failed_check: str,
    ) -> None:
        self.assertNotEqual(0, result.returncode, result.stdout + result.stderr)
        receipt_path = root / "mutation-receipt.json"
        self.assertTrue(receipt_path.exists(), "verifier did not emit a failure receipt")
        receipt = json.loads(receipt_path.read_text(encoding="utf-8"))
        self.assertIs(receipt["passed"], False)
        self.assertIs(receipt["checks"][failed_check]["passed"], False)

    def test_verifier_is_nonzero_when_tampered_receipt_is_accepted(self) -> None:
        root = self.make_copy()
        implementation = root / "graph_demo.py"
        text = implementation.read_text(encoding="utf-8")
        original = '                if digest(record) != claimed:\n                    raise PersistenceError("receipt integrity hash mismatch")'
        mutant = '                if False and digest(record) != claimed:\n                    raise PersistenceError("receipt integrity hash mismatch")'
        self.assertIn(original, text)
        implementation.write_text(text.replace(original, mutant, 1), encoding="utf-8")

        result = self.run_verifier(root)

        self.assert_clean_failure(result, root, "unit_tests")

    def test_verifier_is_nonzero_for_deliberately_failed_scenario(self) -> None:
        root = self.make_copy()
        evaluator = root / "evaluate.py"
        text = evaluator.read_text(encoding="utf-8")
        original = '    assert graph.state["state"] == "complete"'
        mutant = '    assert graph.state["state"] == "hard_stop"'
        self.assertIn(original, text)
        evaluator.write_text(text.replace(original, mutant, 1), encoding="utf-8")

        result = self.run_verifier(root)

        self.assert_clean_failure(result, root, "evaluation")


if __name__ == "__main__":
    unittest.main()
