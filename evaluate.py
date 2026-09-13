from __future__ import annotations

import argparse
import hashlib
import json
import tempfile
import time
from pathlib import Path

from graph_demo import DemoGraph, PersistenceError, TransitionError

ROOT = Path(__file__).resolve().parent


def scenario_success(root: Path, iteration: int) -> None:
    graph = DemoGraph.create(root / f"success-{iteration}")
    for step in range(3):
        work = graph.current_work()
        graph.apply(work_key=work.work_key, outcome="success", event_id=f"success-{step}")
    assert graph.state["state"] == "complete"
    assert graph.state["sequence"] == 3


def scenario_retry_bound(root: Path, iteration: int) -> None:
    graph = DemoGraph.create(root / f"retry-{iteration}", max_attempts=2)
    for step in range(2):
        work = graph.current_work()
        graph.apply(work_key=work.work_key, outcome="retryable_failure", event_id=f"retry-{step}")
    assert graph.state["state"] == "hard_stop"
    assert graph.state["terminal_reason"] == "retry_exhausted"


def scenario_recovery(root: Path, iteration: int) -> None:
    graph = DemoGraph.create(root / f"recovery-{iteration}")
    work = graph.current_work()

    def fail_snapshot(_state: dict[str, object]) -> None:
        raise OSError("injected snapshot failure")

    graph._write_snapshot = fail_snapshot  # type: ignore[method-assign]
    try:
        graph.apply(work_key=work.work_key, outcome="success", event_id="journal-first")
    except OSError:
        pass
    else:
        raise AssertionError("fault injection did not fail")
    try:
        graph.apply(work_key=work.work_key, outcome="success", event_id="unsafe-retry")
    except PersistenceError:
        pass
    else:
        raise AssertionError("poisoned object accepted more work")
    recovered = DemoGraph.resume(graph.directory)
    assert recovered.state["state"] == "implement"
    assert recovered.state["sequence"] == 1


def scenario_tamper(root: Path, iteration: int) -> None:
    graph = DemoGraph.create(root / f"tamper-{iteration}")
    work = graph.current_work()
    graph.apply(work_key=work.work_key, outcome="success", event_id="original")
    line = json.loads(graph.receipt_path.read_text(encoding="utf-8"))
    line["event_id"] = "mutated"
    graph.receipt_path.write_text(json.dumps(line) + "\n", encoding="utf-8")
    try:
        DemoGraph.resume(graph.directory)
    except PersistenceError:
        return
    raise AssertionError("tampered receipt was accepted")


SCENARIOS = {
    "success_path": scenario_success,
    "retry_bound": scenario_retry_bound,
    "journal_ahead_recovery": scenario_recovery,
    "tamper_rejection": scenario_tamper,
}


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def main() -> int:
    parser = argparse.ArgumentParser(description="Run the deterministic graph-demo evaluation matrix.")
    parser.add_argument("--iterations", type=int, default=100)
    parser.add_argument("--output", type=Path)
    args = parser.parse_args()
    if args.iterations < 1 or args.iterations > 10000:
        parser.error("--iterations must be between 1 and 10000")

    started = time.perf_counter()
    counts: dict[str, dict[str, int]] = {}
    failures: list[dict[str, object]] = []
    with tempfile.TemporaryDirectory() as temporary:
        root = Path(temporary)
        for name, scenario in SCENARIOS.items():
            passed = 0
            for iteration in range(args.iterations):
                try:
                    scenario(root, iteration)
                    passed += 1
                except Exception as exc:  # surfaced in structured output
                    failures.append({"scenario": name, "iteration": iteration, "error": repr(exc)})
            counts[name] = {"passed": passed, "attempted": args.iterations}

    result = {
        "schema_version": 1,
        "artifact": "fail-closed-graph-demo",
        "python_standard_library_only": True,
        "iterations_per_scenario": args.iterations,
        "scenarios": counts,
        "total_passed": sum(item["passed"] for item in counts.values()),
        "total_attempted": args.iterations * len(SCENARIOS),
        "failures": failures,
        "elapsed_seconds": round(time.perf_counter() - started, 6),
        "source_sha256": sha256(ROOT / "graph_demo.py"),
        "test_sha256": sha256(ROOT / "test_graph_demo.py"),
    }
    text = json.dumps(result, indent=2, sort_keys=True) + "\n"
    if args.output:
        args.output.write_text(text, encoding="utf-8")
    print(text, end="")
    return 0 if not failures else 1


if __name__ == "__main__":
    raise SystemExit(main())
