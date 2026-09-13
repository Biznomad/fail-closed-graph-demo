from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

from graph_demo import DemoGraph, PersistenceError, TransitionError, digest


class DemoGraphTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temporary = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporary.cleanup)
        self.root = Path(self.temporary.name)

    def test_success_path_finishes_with_valid_chain(self) -> None:
        graph = DemoGraph.create(self.root / "success")
        visited = [graph.state["state"]]
        for index in range(3):
            work = graph.current_work()
            graph.apply(work_key=work.work_key, outcome="success", event_id=f"ok-{index}")
            visited.append(graph.state["state"])
        self.assertEqual(["plan", "implement", "verify", "complete"], visited)
        self.assertEqual(3, len(graph.receipts))
        self.assertEqual(graph.receipts[-1]["receipt_hash"], graph.state["last_hash"])
        with self.assertRaisesRegex(TransitionError, "terminal"):
            graph.current_work()

    def test_retry_exhaustion_stops_at_finite_bound(self) -> None:
        graph = DemoGraph.create(self.root / "retry", max_attempts=2)
        first = graph.current_work()
        graph.apply(work_key=first.work_key, outcome="retryable_failure", event_id="retry-1")
        second = graph.current_work()
        receipt = graph.apply(work_key=second.work_key, outcome="retryable_failure", event_id="retry-2")
        self.assertEqual("hard_stop", graph.state["state"])
        self.assertEqual("retry_exhausted", receipt["terminal_reason"])
        self.assertEqual(2, len(graph.receipts))

    def test_stale_work_identity_is_rejected_without_append(self) -> None:
        graph = DemoGraph.create(self.root / "stale")
        stale = graph.current_work()
        graph.apply(work_key=stale.work_key, outcome="success", event_id="advance")
        with self.assertRaisesRegex(TransitionError, "current work"):
            graph.apply(work_key=stale.work_key, outcome="success", event_id="stale")
        self.assertEqual(1, len(graph.receipts))

    def test_journal_ahead_failure_poisoning_and_resume(self) -> None:
        graph = DemoGraph.create(self.root / "recovery")
        work = graph.current_work()
        real_write = graph._write_snapshot

        def fail_snapshot(_state: dict[str, object]) -> None:
            raise OSError("injected snapshot failure")

        graph._write_snapshot = fail_snapshot  # type: ignore[method-assign]
        with self.assertRaisesRegex(OSError, "injected"):
            graph.apply(work_key=work.work_key, outcome="success", event_id="journal-first")
        graph._write_snapshot = real_write  # type: ignore[method-assign]

        self.assertEqual(0, graph.state["sequence"])
        self.assertEqual(1, len(graph.receipt_path.read_text(encoding="utf-8").splitlines()))
        with self.assertRaisesRegex(PersistenceError, "resume is required"):
            graph.apply(work_key=work.work_key, outcome="success", event_id="unsafe-retry")

        recovered = DemoGraph.resume(self.root / "recovery")
        self.assertEqual(1, recovered.state["sequence"])
        self.assertEqual("implement", recovered.state["state"])
        self.assertEqual(1, len(recovered.receipts))

    def test_tampered_receipt_is_rejected(self) -> None:
        graph = DemoGraph.create(self.root / "tamper")
        work = graph.current_work()
        graph.apply(work_key=work.work_key, outcome="success", event_id="before-tamper")
        record = json.loads(graph.receipt_path.read_text(encoding="utf-8"))
        record["event_id"] = "changed-after-write"
        graph.receipt_path.write_text(json.dumps(record) + "\n", encoding="utf-8")
        with self.assertRaisesRegex(PersistenceError, "integrity hash mismatch"):
            DemoGraph.resume(self.root / "tamper")

    def test_receipt_hash_is_independently_recomputable(self) -> None:
        graph = DemoGraph.create(self.root / "hash")
        work = graph.current_work()
        receipt = graph.apply(work_key=work.work_key, outcome="success", event_id="hash-check")
        claimed = receipt["receipt_hash"]
        unhashed = dict(receipt)
        unhashed.pop("receipt_hash")
        self.assertEqual(claimed, digest(unhashed))

    def test_snapshot_tamper_is_rejected_even_when_last_hash_is_preserved(self) -> None:
        graph = DemoGraph.create(self.root / "snapshot-tamper")
        work = graph.current_work()
        graph.apply(work_key=work.work_key, outcome="success", event_id="before-tamper")
        snapshot = json.loads(graph.state_path.read_text(encoding="utf-8"))
        snapshot["state"] = "verify"
        graph.state_path.write_text(json.dumps(snapshot) + "\n", encoding="utf-8")
        with self.assertRaisesRegex(PersistenceError, "snapshot and receipt journal disagree"):
            DemoGraph.resume(self.root / "snapshot-tamper")


if __name__ == "__main__":
    unittest.main()
