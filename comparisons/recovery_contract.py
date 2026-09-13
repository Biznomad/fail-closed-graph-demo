"""Framework-neutral fail-closed external-effect trace contract.

This module does not wrap or certify any agent framework. It validates the
application-level evidence that a framework integration must emit before a
workflow may retry or continue after an external side effect.
"""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass, field
from typing import Any

ZERO_HASH = "0" * 64
ALLOWED_KINDS = {
    "approval",
    "intent",
    "effect_confirmed",
    "effect_unknown",
    "lookup_absent",
    "lookup_confirmed",
    "retry",
    "projection",
    "evidence_invalid",
    "escalate",
    "hard_stop",
}


def canonical(value: object) -> bytes:
    return json.dumps(
        value,
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=True,
        allow_nan=False,
    ).encode("utf-8")


def record_hash(record_without_hash: dict[str, Any]) -> str:
    return hashlib.sha256(canonical(record_without_hash)).hexdigest()


@dataclass
class TraceBuilder:
    """Build deterministic hash-chained test traces."""

    framework: str
    records: list[dict[str, Any]] = field(default_factory=list)

    def add(self, kind: str, action_id: str, *, attempt: int = 0) -> "TraceBuilder":
        previous = self.records[-1]["record_hash"] if self.records else ZERO_HASH
        record: dict[str, Any] = {
            "schema": 1,
            "sequence": len(self.records) + 1,
            "framework": self.framework,
            "kind": kind,
            "action_id": action_id,
            "attempt": attempt,
            "previous_hash": previous,
        }
        record["record_hash"] = record_hash(record)
        self.records.append(record)
        return self


def validate_trace(records: list[dict[str, Any]], *, max_attempts: int = 2) -> list[str]:
    """Return every contract violation; an empty list is a PASS."""

    errors: list[str] = []
    if isinstance(max_attempts, bool) or not isinstance(max_attempts, int) or max_attempts < 1:
        return ["max_attempts must be a positive integer"]
    if not records:
        return ["trace must contain at least one record"]

    previous = ZERO_HASH
    expected_framework: str | None = None
    approved: set[str] = set()
    started_attempt: dict[str, int] = {}
    confirmed: set[str] = set()
    uncertain: dict[str, int] = {}
    absent: dict[str, int] = {}
    invalid_evidence = False
    terminal = False

    for expected_sequence, original in enumerate(records, 1):
        if not isinstance(original, dict):
            errors.append(f"record {expected_sequence}: not an object")
            continue
        record = dict(original)
        claimed_hash = record.pop("record_hash", None)
        if record.get("sequence") != expected_sequence:
            errors.append(f"record {expected_sequence}: noncontiguous sequence")
        if record.get("previous_hash") != previous:
            errors.append(f"record {expected_sequence}: broken hash link")
        calculated = record_hash(record)
        if claimed_hash != calculated:
            errors.append(f"record {expected_sequence}: record hash mismatch")
        previous = claimed_hash if isinstance(claimed_hash, str) else calculated

        kind = record.get("kind")
        framework = record.get("framework")
        action_id = record.get("action_id")
        attempt = record.get("attempt")
        if not isinstance(framework, str) or not framework:
            errors.append(f"record {expected_sequence}: missing framework")
        elif expected_framework is None:
            expected_framework = framework
        elif framework != expected_framework:
            errors.append(f"record {expected_sequence}: framework changed within trace")
        if kind not in ALLOWED_KINDS:
            errors.append(f"record {expected_sequence}: unknown kind")
            continue
        if not isinstance(action_id, str) or not action_id:
            errors.append(f"record {expected_sequence}: missing action_id")
            continue
        if not isinstance(attempt, int) or isinstance(attempt, bool) or attempt < 0:
            errors.append(f"record {expected_sequence}: invalid attempt")
            continue
        if terminal:
            errors.append(f"record {expected_sequence}: event after terminal decision")
            continue
        if invalid_evidence and kind != "hard_stop":
            errors.append(f"record {expected_sequence}: invalid evidence must hard-stop")

        if kind == "approval":
            approved.add(action_id)
        elif kind == "intent":
            if action_id not in approved:
                errors.append(f"record {expected_sequence}: external intent lacks approval")
            if action_id in uncertain:
                errors.append(f"record {expected_sequence}: new intent while effect is uncertain")
            if attempt < 1 or attempt > max_attempts:
                errors.append(f"record {expected_sequence}: intent exceeds retry bound")
            started_attempt[action_id] = attempt
        elif kind == "effect_unknown":
            if started_attempt.get(action_id) != attempt:
                errors.append(f"record {expected_sequence}: unknown effect lacks matching intent")
            uncertain[action_id] = attempt
        elif kind == "lookup_absent":
            if uncertain.get(action_id) != attempt:
                errors.append(f"record {expected_sequence}: absence lookup lacks uncertain effect")
            uncertain.pop(action_id, None)
            absent[action_id] = attempt
        elif kind == "lookup_confirmed":
            if uncertain.get(action_id) != attempt:
                errors.append(f"record {expected_sequence}: confirmation lookup lacks uncertain effect")
            uncertain.pop(action_id, None)
            confirmed.add(action_id)
        elif kind == "retry":
            if action_id in uncertain:
                errors.append(f"record {expected_sequence}: blind retry after uncertain effect")
            prior = absent.get(action_id)
            if prior is None or attempt != prior + 1:
                errors.append(f"record {expected_sequence}: retry lacks authoritative absence proof")
            if attempt > max_attempts:
                errors.append(f"record {expected_sequence}: retry exceeds bound")
            started_attempt[action_id] = attempt
            absent.pop(action_id, None)
        elif kind == "effect_confirmed":
            if started_attempt.get(action_id) != attempt:
                errors.append(f"record {expected_sequence}: confirmed effect lacks matching intent")
            if action_id in confirmed:
                errors.append(f"record {expected_sequence}: duplicate confirmed effect")
            confirmed.add(action_id)
        elif kind == "projection":
            if action_id not in confirmed:
                errors.append(f"record {expected_sequence}: projection precedes confirmed effect")
        elif kind == "evidence_invalid":
            invalid_evidence = True
        elif kind in {"escalate", "hard_stop"}:
            terminal = True

    for action_id in sorted(uncertain):
        errors.append(f"unresolved uncertain effect: {action_id}")
    if invalid_evidence and not terminal:
        errors.append("invalid evidence did not reach hard_stop")
    return errors
