# Agent Harness Recovery Lab

This lab maps the fail-closed external-effect contract onto nine agent/workflow harnesses, including Hermes Agent—the harness operating Biznomad's internal pilot. It does **not** claim that any framework is unsafe or that framework persistence alone provides exactly-once side effects.

## The distinction that matters

A harness can correctly save graph or conversation state while an external system has already accepted an email, payment, CRM update, publication, or deployment request. If the caller times out before receiving the result, replaying the node or activity can duplicate the external action.

The common contract in `recovery_contract.py` therefore requires:

1. explicit approval before an external intent;
2. a stable action identity across attempts;
3. a durable intent/effect record;
4. authoritative lookup after an ambiguous result;
5. no retry until absence is established;
6. a finite retry bound;
7. hard stop when evidence is invalid.
8. a non-empty trace with one stable framework identity throughout.

## 1. LangGraph

LangGraph checkpointers persist thread-scoped graph state, while stores hold application-defined data across threads.[1] Its interrupts pause execution, save state through the checkpointer, and resume through `Command` using the same thread identity.[7]

**Implementation mapping:** use a durable checkpointer for graph position, `interrupt()` before consequential tools, and a separate action journal/provider lookup for the external effect.

```python
# Framework sketch: optional dependency, not executed by this lab.
checkpointer = PostgresSaver.from_conn_string(DATABASE_URL)
graph = builder.compile(checkpointer=checkpointer)

def approval_node(state):
    approved = interrupt({"action_id": state["action_id"], "proposal": state["proposal"]})
    return {"approved": bool(approved)}

def effect_node(state):
    require_approved(state)
    journal.intent(state["action_id"], state["proposal_hash"])
    try:
        result = provider.execute(idempotency_key=state["action_id"])
    except TimeoutError:
        return reconcile_with_provider(state["action_id"])
    journal.confirm(state["action_id"], result.external_id)
    return {"external_id": result.external_id}
```

**Gap closed by this lab:** a checkpoint tells you where the graph was; the action journal and provider lookup tell you whether the outside effect happened.

## 2. OpenAI Agents SDK

The SDK can mark tools with `needs_approval`, surface pending calls as interruptions, serialize a paused `RunState`, record approve/reject decisions, and resume the original run.[2]

**Implementation mapping:** use SDK approval for permission, then place idempotency and reconciliation inside the tool implementation.

```python
@tool(needs_approval=True)
async def publish_draft(action_id: str, draft_hash: str) -> dict:
    journal.intent(action_id, draft_hash)
    try:
        result = await publisher.publish(idempotency_key=action_id)
    except TimeoutError:
        return await reconcile_with_publisher(action_id)
    journal.confirm(action_id, result.external_id)
    return {"external_id": result.external_id}

# Persist result.to_state() while awaiting approval; resume the same run state.
```

**Gap closed by this lab:** approval answers *may the tool run?*; it does not replace application-level proof of whether a timed-out external call took effect.

## 3. CrewAI Flows

CrewAI Flows provides structured/unstructured state and `@persist` at class or method level. Its documented default persistence uses SQLite and supports resume and fork semantics.[3]

**Implementation mapping:** separate preparation from execution so the action identity and approved payload are persisted before the effect method runs.

```python
@persist
class SafeFlow(Flow[ActionState]):
    @start()
    def prepare(self):
        self.state.action_id = stable_action_id(self.state.payload)
        self.state.status = "awaiting_approval"

    @listen(prepare)
    def execute_after_approval(self):
        require_approved(self.state)
        return execute_with_journal_and_lookup(
            action_id=self.state.action_id,
            payload=self.state.payload,
        )
```

**Gap closed by this lab:** persisted flow state is useful recovery context, but an external-effect wrapper must still prevent blind replay after an ambiguous call.

## 4. AutoGen AgentChat

AutoGen exposes `save_state()` and `load_state()` for agents and teams, and the documented state can be serialized to a file or database.[4]

**Implementation mapping:** persist team state for conversational/team continuity, but keep consequential tool effects in a separate durable action ledger.

```python
team_state = await team.save_state()
await state_store.atomic_write(run_id, team_state)

async def consequential_tool(action_id: str, payload: dict) -> dict:
    require_approval(action_id, payload)
    return await execute_with_journal_and_lookup(action_id, payload)

# On restart: load team state and reconcile unresolved action IDs before run_stream().
```

**Gap closed by this lab:** manually saved team state does not by itself establish the ordering or outcome of an external side effect.

## 5. Pydantic AI durable execution

Pydantic AI Harness is the capability package around Pydantic AI, including broader agent capabilities.[5] Its Temporal integration separates deterministic workflows from I/O-performing activities; the documentation warns that an activity failing part-way through is restarted from the beginning.[6]

**Implementation mapping:** make every consequential activity use a stable action ID and reconcile externally before allowing an activity retry to repeat the effect.

```python
@activity.defn
async def execute_effect(command: EffectCommand) -> EffectReceipt:
    journal.intent(command.action_id, command.payload_hash)
    existing = await provider.lookup(command.action_id)
    if existing:
        return journal.confirm(command.action_id, existing.external_id)
    result = await provider.execute(
        command.payload,
        idempotency_key=command.action_id,
    )
    return journal.confirm(command.action_id, result.external_id)
```

**Gap closed by this lab:** durable replay recovers workflow progress; idempotent activities and authoritative lookup protect non-repeatable external effects.

## 6. Hermes Agent

Hermes persists resumable session history in SQLite.[10] Its Cron subsystem stores durable job records and execution attempts, performs pre-dispatch validation, and distinguishes execution from delivery status.[8] Hermes Kanban is a durable SQLite task board with atomic claims, crash/stale-worker recovery, bounded retries, blocking/unblocking, human comments, and an append-only task event trail.[9]

**Implementation mapping:** use Hermes sessions for conversational continuity, Cron for durable scheduling, and Kanban for durable work ownership and recovery. Wrap every consequential tool with a Biznomad application-level action journal that binds the approved payload hash to a stable action ID. After an ambiguous result or reclaimed worker, query the external provider before permitting a retry.

```python
# Hermes integration sketch: the Kanban card owns workflow progress;
# the action journal owns evidence about the external effect.
def consequential_tool(task_id: str, action_id: str, payload: dict) -> dict:
    require_task_approval(task_id, action_id, payload_hash(payload))
    journal.intent(action_id, payload_hash(payload))
    existing = provider.lookup(action_id)
    if existing:
        return journal.confirm(action_id, existing.external_id)
    try:
        result = provider.execute(payload, idempotency_key=action_id)
    except TimeoutError:
        return reconcile_or_block(task_id, action_id)
    return journal.confirm(action_id, result.external_id)
```

**Gap closed by this lab:** Hermes can durably remember the session, schedule, task, claim, run, and recovery history. Those records do not by themselves prove exactly-once execution of arbitrary email, payment, publication, deployment, or third-party API effects. Stable action identities, payload-bound approval, provider-side lookup, and durable effect receipts remain application controls.

## 7. Pi Agent

Pi stores sessions as JSONL trees with stable entry and parent IDs, supports resume/fork/import, and allows extensions to persist custom state.[11] Extensions can intercept tool calls and ask the user for confirmation, but run with the launching process's permissions.[12]

**Implementation mapping:** implement a Pi extension that blocks consequential tool calls until a payload-bound approval record exists, persists action-journal entries with `appendEntry()`, and performs provider lookup before any replay. Keep the authoritative effect journal in transactional storage when JSONL append semantics are insufficient.

**Boundary:** Pi's session history and extension state preserve agent context; they do not establish the outcome of an external effect.

## 8. NVIDIA NeMo Agent Toolkit

NeMo Agent Toolkit is primarily a framework-agnostic integration, observability, profiling, and evaluation layer that works beside existing agent frameworks.[13]

**Implementation mapping:** use NeMo telemetry and evaluation to observe the common recovery events, while the underlying framework or application owns durable execution, approval state, effect receipts, reconciliation, and retry limits.

**Boundary:** tracing an attempted tool call is evidence about execution flow, not authoritative proof that a remote side effect committed. This row is intentionally qualified rather than implying NeMo supplies a general workflow checkpoint engine.

## 9. DeepSeek Harness

DeepSeek Harness is an experimental, plugin-composed agent runtime.[14][17]

Its architecture includes an append-only session event log, persistence plugins, resumable sessions, and an awaited session durability flush.[15][16]

**Implementation mapping:** add a plugin that intercepts consequential tools, requires approval tied to a payload hash, writes a stable action intent, reconciles uncertain outcomes with the provider, and appends only the reconciled result to session history.

**Boundary:** reversible plugin registration concerns harness composition, and durable session events concern agent history. Neither automatically makes an arbitrary third-party effect reversible or exactly-once.

## Executable conformance contract

Run without framework dependencies or API keys:

```bash
python -m unittest -v comparisons/test_recovery_contract.py
```

The test suite validates a conforming integration blueprint for every named framework and rejects:

- an external intent without approval;
- blind retry after an uncertain effect;
- retry beyond the configured bound;
- a modified hash-chained record;
- continuation after invalid evidence;
- an unresolved ambiguous effect.
- an empty trace or a mid-trace framework-identity change, even when hashes are recomputed.

These are synthetic contract tests—not tests of the upstream frameworks, provider APIs, production storage, or exactly-once delivery.

## What should be public

Publish the framework matrix, framework-neutral validator, synthetic tests, and integration sketches. Do not copy upstream implementation code. Link to official documentation, retain upstream names and trademarks accurately, and keep the repository's MIT license scoped to original Biznomad material.

## Sources

[1] https://docs.langchain.com/oss/python/langgraph/persistence — LangGraph Persistence
[2] https://openai.github.io/openai-agents-python/human_in_the_loop — OpenAI Agents SDK Human-in-the-loop
[3] https://docs.crewai.com/v1.15.20/en/concepts/flows.md — CrewAI Flows
[4] https://microsoft.github.io/autogen/stable/user-guide/agentchat-user-guide/tutorial/state.html — AutoGen Managing State
[5] https://pydantic.dev/docs/ai/harness/overview — Pydantic AI Harness Overview
[6] https://ai.pydantic.dev/integrations/durable_execution/temporal — Pydantic AI Durable Execution with Temporal
[7] https://docs.langchain.com/oss/python/langgraph/interrupts — LangGraph Interrupts
[8] https://hermes-agent.nousresearch.com/docs/user-guide/features/cron — Hermes Agent Scheduled Tasks (Cron)
[9] https://hermes-agent.nousresearch.com/docs/user-guide/features/kanban — Hermes Agent Kanban — Multi-Agent Profile Collaboration
[10] https://hermes-agent.nousresearch.com/docs/user-guide/sessions — Hermes Agent Sessions
[11] https://pi.dev/docs/latest/session — Pi Session File Format
[12] https://pi.dev/docs/latest/extensions — Pi Extensions
[13] https://github.com/NVIDIA/NeMo-Agent-Toolkit — NVIDIA NeMo Agent Toolkit Overview
[14] https://github.com/deepseek-ai/deepseek-harness — DeepSeek Harness
[15] https://github.com/deepseek-ai/deepseek-harness/blob/master/docs/architecture.md — DeepSeek Harness Architecture
[16] https://github.com/deepseek-ai/deepseek-harness/blob/master/docs/subsystems/session.md — DeepSeek Harness Sessions
[17] https://github.com/deepseek-ai/deepseek-harness/blob/master/SAFETY.md — DeepSeek Harness Safety
