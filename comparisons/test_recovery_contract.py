from __future__ import annotations

import copy
import unittest

from comparisons.recovery_contract import TraceBuilder, record_hash, validate_trace


FRAMEWORKS = (
    "langgraph",
    "openai-agents-sdk",
    "crewai-flows",
    "autogen-agentchat",
    "pydantic-ai-durable",
    "hermes-agent",
    "pi-agent",
    "nvidia-nemo-agent-toolkit",
    "deepseek-harness",
)


def confirmed_after_timeout(framework: str) -> list[dict[str, object]]:
    return (
        TraceBuilder(framework)
        .add("approval", "send-42")
        .add("intent", "send-42", attempt=1)
        .add("effect_unknown", "send-42", attempt=1)
        .add("lookup_confirmed", "send-42", attempt=1)
        .add("projection", "send-42", attempt=1)
        .records
    )


def rehash(records: list[dict[str, object]]) -> None:
    previous = "0" * 64
    for sequence, record in enumerate(records, 1):
        record["sequence"] = sequence
        record["previous_hash"] = previous
        body = dict(record)
        body.pop("record_hash", None)
        record["record_hash"] = record_hash(body)
        previous = str(record["record_hash"])


class FrameworkBlueprintTests(unittest.TestCase):
    def test_each_framework_blueprint_satisfies_common_contract(self) -> None:
        for framework in FRAMEWORKS:
            with self.subTest(framework=framework):
                self.assertEqual(validate_trace(confirmed_after_timeout(framework)), [])
        self.assertIn("trace must contain", " ".join(validate_trace([])))
        mixed = confirmed_after_timeout("langgraph")
        mixed[2]["framework"] = "openai-agents-sdk"
        rehash(mixed)
        self.assertIn("framework changed", " ".join(validate_trace(mixed)))

    def test_hermes_reclaim_reconciles_before_external_retry(self) -> None:
        """A reclaimed Hermes task must resolve an uncertain effect before retry."""
        trace = (
            TraceBuilder("hermes-agent")
            .add("approval", "publish-77")
            .add("intent", "publish-77", attempt=1)
            .add("effect_unknown", "publish-77", attempt=1)
            .add("lookup_confirmed", "publish-77", attempt=1)
            .add("projection", "publish-77", attempt=1)
            .records
        )
        self.assertEqual(validate_trace(trace), [])

    def test_pi_extension_state_reconciles_uncertain_effect(self) -> None:
        self.assertEqual(validate_trace(confirmed_after_timeout("pi-agent")), [])

    def test_nvidia_instrumentation_does_not_replace_effect_receipt(self) -> None:
        trace = TraceBuilder("nvidia-nemo-agent-toolkit").add("intent", "deploy-8", attempt=1).records
        self.assertIn("external intent lacks approval", " ".join(validate_trace(trace)))

    def test_deepseek_session_event_requires_external_reconciliation(self) -> None:
        trace = (
            TraceBuilder("deepseek-harness")
            .add("approval", "write-99")
            .add("intent", "write-99", attempt=1)
            .add("effect_unknown", "write-99", attempt=1)
            .records
        )
        self.assertIn("unresolved uncertain effect", " ".join(validate_trace(trace)))

    def test_authoritative_absence_allows_one_bounded_retry(self) -> None:
        trace = (
            TraceBuilder("langgraph")
            .add("approval", "write-7")
            .add("intent", "write-7", attempt=1)
            .add("effect_unknown", "write-7", attempt=1)
            .add("lookup_absent", "write-7", attempt=1)
            .add("retry", "write-7", attempt=2)
            .add("effect_confirmed", "write-7", attempt=2)
            .add("projection", "write-7", attempt=2)
            .records
        )
        self.assertEqual(validate_trace(trace, max_attempts=2), [])


class FailClosedRegressionTests(unittest.TestCase):
    def test_missing_approval_fails(self) -> None:
        trace = TraceBuilder("autogen-agentchat").add("intent", "send-1", attempt=1).records
        self.assertIn("external intent lacks approval", " ".join(validate_trace(trace)))

    def test_blind_retry_after_unknown_effect_fails(self) -> None:
        trace = (
            TraceBuilder("crewai-flows")
            .add("approval", "send-2")
            .add("intent", "send-2", attempt=1)
            .add("effect_unknown", "send-2", attempt=1)
            .add("retry", "send-2", attempt=2)
            .records
        )
        errors = " ".join(validate_trace(trace))
        self.assertIn("blind retry", errors)
        self.assertIn("authoritative absence", errors)

    def test_retry_budget_is_enforced(self) -> None:
        trace = (
            TraceBuilder("pydantic-ai-durable")
            .add("approval", "send-3")
            .add("intent", "send-3", attempt=1)
            .add("effect_unknown", "send-3", attempt=1)
            .add("lookup_absent", "send-3", attempt=1)
            .add("retry", "send-3", attempt=2)
            .records
        )
        self.assertIn("retry exceeds bound", " ".join(validate_trace(trace, max_attempts=1)))

    def test_tampered_record_fails(self) -> None:
        trace = confirmed_after_timeout("openai-agents-sdk")
        tampered = copy.deepcopy(trace)
        tampered[2]["action_id"] = "different-action"
        self.assertIn("record hash mismatch", " ".join(validate_trace(tampered)))

    def test_invalid_evidence_must_hard_stop(self) -> None:
        trace = (
            TraceBuilder("langgraph")
            .add("evidence_invalid", "send-4")
            .add("projection", "send-4")
            .records
        )
        errors = " ".join(validate_trace(trace))
        self.assertIn("invalid evidence must hard-stop", errors)
        self.assertIn("invalid evidence did not reach hard_stop", errors)

    def test_unresolved_unknown_effect_fails(self) -> None:
        trace = (
            TraceBuilder("openai-agents-sdk")
            .add("approval", "send-5")
            .add("intent", "send-5", attempt=1)
            .add("effect_unknown", "send-5", attempt=1)
            .records
        )
        self.assertIn("unresolved uncertain effect", " ".join(validate_trace(trace)))


if __name__ == "__main__":
    unittest.main()
