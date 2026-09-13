"""Public-safe, standard-library demonstration of fail-closed state persistence.

This is a standalone reproduction artifact. It records
bounded state transitions in a hash-chained JSONL journal, then atomically replaces
a snapshot. If persistence becomes uncertain, the live object refuses more work
until it is reopened from durable evidence.
"""

from __future__ import annotations

import hashlib
import json
import os
import tempfile
from dataclasses import dataclass
from pathlib import Path

ZERO_HASH = "0" * 64
STATES = ("plan", "implement", "verify", "complete")


class PersistenceError(RuntimeError):
    """Persisted evidence is invalid or the live object must be reopened."""


class TransitionError(RuntimeError):
    """A requested transition is stale, invalid, or exceeds a bound."""


def canonical(data: object) -> bytes:
    return json.dumps(
        data,
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=True,
        allow_nan=False,
    ).encode("utf-8")


def digest(data: object) -> str:
    return hashlib.sha256(canonical(data)).hexdigest()


@dataclass(frozen=True)
class WorkItem:
    state: str
    attempt: int
    work_key: str


class DemoGraph:
    """Single-writer demo graph with finite retries and receipt-first persistence."""

    def __init__(
        self,
        directory: Path,
        state: dict[str, object],
        receipts: list[dict[str, object]],
    ) -> None:
        self.directory = directory
        self.state_path = directory / "state.json"
        self.receipt_path = directory / "receipts.jsonl"
        self.state = state
        self.receipts = receipts
        self._poisoned = False

    @classmethod
    def create(cls, directory: str | os.PathLike[str], *, max_attempts: int = 2) -> "DemoGraph":
        if isinstance(max_attempts, bool) or not isinstance(max_attempts, int) or max_attempts < 1:
            raise ValueError("max_attempts must be a positive integer")
        root = Path(directory).resolve()
        state_path = root / "state.json"
        receipt_path = root / "receipts.jsonl"
        if state_path.exists() or receipt_path.exists():
            raise FileExistsError("demo persistence already exists")
        root.mkdir(parents=True, exist_ok=True)
        state: dict[str, object] = {
            "schema": 1,
            "state": STATES[0],
            "attempt": 1,
            "sequence": 0,
            "last_hash": ZERO_HASH,
            "max_attempts": max_attempts,
            "terminal_reason": None,
        }
        graph = cls(root, state, [])
        graph._write_snapshot(state)
        return graph

    @classmethod
    def resume(cls, directory: str | os.PathLike[str]) -> "DemoGraph":
        root = Path(directory).resolve()
        state_path = root / "state.json"
        if not state_path.exists():
            raise PersistenceError("state snapshot is missing")
        try:
            state = json.loads(state_path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError) as exc:
            raise PersistenceError("state snapshot is unreadable") from exc
        cls._validate_state(state)
        receipts = cls._read_and_validate_receipts(root / "receipts.jsonl")
        if receipts:
            latest = receipts[-1]
            snapshot_sequence = int(state["sequence"])
            journal_sequence = int(latest["sequence"])
            if snapshot_sequence > journal_sequence:
                raise PersistenceError("snapshot is ahead of receipt journal")
            if snapshot_sequence < journal_sequence:
                state = {
                    "schema": 1,
                    "state": latest["to_state"],
                    "attempt": latest["next_attempt"],
                    "sequence": latest["sequence"],
                    "last_hash": latest["receipt_hash"],
                    "max_attempts": latest["max_attempts"],
                    "terminal_reason": latest["terminal_reason"],
                }
                graph = cls(root, state, receipts)
                graph._write_snapshot(state)
                return graph
            expected_state = {
                "schema": 1,
                "state": latest["to_state"],
                "attempt": latest["next_attempt"],
                "sequence": latest["sequence"],
                "last_hash": latest["receipt_hash"],
                "max_attempts": latest["max_attempts"],
                "terminal_reason": latest["terminal_reason"],
            }
            if state != expected_state:
                raise PersistenceError("snapshot and receipt journal disagree")
        elif int(state["sequence"]) != 0 or state["last_hash"] != ZERO_HASH:
            raise PersistenceError("nonempty snapshot has no receipt journal")
        return cls(root, state, receipts)

    def current_work(self) -> WorkItem:
        if self.state["state"] in ("complete", "hard_stop"):
            raise TransitionError("run is terminal")
        state = str(self.state["state"])
        attempt = int(self.state["attempt"])
        return WorkItem(state, attempt, digest({"state": state, "attempt": attempt}))

    def apply(self, *, work_key: str, outcome: str, event_id: str) -> dict[str, object]:
        if self._poisoned:
            raise PersistenceError("persistence is uncertain; resume is required")
        if not event_id or len(event_id) > 80:
            raise ValueError("event_id must contain 1 to 80 characters")
        work = self.current_work()
        if work_key != work.work_key:
            raise TransitionError("event does not match current work")
        if outcome not in ("success", "retryable_failure", "hard_failure"):
            raise ValueError("unsupported outcome")

        current = work.state
        attempt = work.attempt
        max_attempts = int(self.state["max_attempts"])
        terminal_reason: str | None = None
        if outcome == "hard_failure":
            target, next_attempt, terminal_reason = "hard_stop", 0, "hard_failure"
        elif outcome == "retryable_failure":
            if attempt >= max_attempts:
                target, next_attempt, terminal_reason = "hard_stop", 0, "retry_exhausted"
            else:
                target, next_attempt = current, attempt + 1
        else:
            target = STATES[STATES.index(current) + 1]
            next_attempt = 0 if target == "complete" else 1

        sequence = int(self.state["sequence"]) + 1
        receipt: dict[str, object] = {
            "schema": 1,
            "sequence": sequence,
            "from_state": current,
            "to_state": target,
            "attempt": attempt,
            "next_attempt": next_attempt,
            "outcome": outcome,
            "event_id": event_id,
            "work_key": work_key,
            "previous_receipt_hash": self.state["last_hash"],
            "max_attempts": max_attempts,
            "terminal_reason": terminal_reason,
        }
        receipt["receipt_hash"] = digest(receipt)
        next_state: dict[str, object] = {
            "schema": 1,
            "state": target,
            "attempt": next_attempt,
            "sequence": sequence,
            "last_hash": receipt["receipt_hash"],
            "max_attempts": max_attempts,
            "terminal_reason": terminal_reason,
        }

        self._poisoned = True
        self._append_receipt(receipt)
        self._write_snapshot(next_state)
        self.receipts.append(receipt)
        self.state = next_state
        self._poisoned = False
        return receipt

    def _append_receipt(self, receipt: dict[str, object]) -> None:
        with self.receipt_path.open("ab") as handle:
            handle.write(canonical(receipt) + b"\n")
            handle.flush()
            os.fsync(handle.fileno())

    def _write_snapshot(self, state: dict[str, object]) -> None:
        self.directory.mkdir(parents=True, exist_ok=True)
        fd, temporary = tempfile.mkstemp(prefix="state-", suffix=".tmp", dir=self.directory)
        temporary_path = Path(temporary)
        try:
            with os.fdopen(fd, "wb") as handle:
                handle.write(canonical(state) + b"\n")
                handle.flush()
                os.fsync(handle.fileno())
            os.replace(temporary_path, self.state_path)
        finally:
            temporary_path.unlink(missing_ok=True)

    @staticmethod
    def _validate_state(state: object) -> None:
        required = {"schema", "state", "attempt", "sequence", "last_hash", "max_attempts", "terminal_reason"}
        if not isinstance(state, dict) or set(state) != required:
            raise PersistenceError("state snapshot has an unexpected schema")
        if state["schema"] != 1 or state["state"] not in (*STATES, "hard_stop"):
            raise PersistenceError("state snapshot contains invalid values")
        if not isinstance(state["sequence"], int) or int(state["sequence"]) < 0:
            raise PersistenceError("state sequence is invalid")
        if not isinstance(state["attempt"], int) or int(state["attempt"]) < 0:
            raise PersistenceError("state attempt is invalid")
        if not isinstance(state["max_attempts"], int) or int(state["max_attempts"]) < 1:
            raise PersistenceError("state retry bound is invalid")
        if not isinstance(state["last_hash"], str) or len(state["last_hash"]) != 64:
            raise PersistenceError("state receipt hash is invalid")

    @staticmethod
    def _read_and_validate_receipts(path: Path) -> list[dict[str, object]]:
        if not path.exists():
            return []
        receipts: list[dict[str, object]] = []
        previous = ZERO_HASH
        try:
            lines = path.read_text(encoding="utf-8").splitlines()
            for sequence, line in enumerate(lines, 1):
                record = json.loads(line)
                claimed = record.pop("receipt_hash")
                if sequence != record["sequence"]:
                    raise PersistenceError("receipt sequence is not contiguous")
                if record["previous_receipt_hash"] != previous:
                    raise PersistenceError("receipt hash chain is broken")
                if digest(record) != claimed:
                    raise PersistenceError("receipt integrity hash mismatch")
                record["receipt_hash"] = claimed
                receipts.append(record)
                previous = claimed
        except (OSError, json.JSONDecodeError, KeyError, TypeError) as exc:
            raise PersistenceError("receipt journal is invalid") from exc
        return receipts
