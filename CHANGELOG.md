# Changelog

All notable changes to this public-safe reproduction are documented here.

## [Unreleased]

### Added

- Standard-library fail-closed graph reproduction.
- Seven unit tests covering persistence uncertainty, bounded retry, stale work, and tamper rejection.
- Four-scenario repeated evaluation harness.
- Cross-platform GitHub Actions matrix for Python 3.11–3.13 on Linux, Windows, and macOS.
- Explicit design boundaries, security policy, and MIT license.
- One-command verification receipt with source hashes and scoped environment data.
- Crash-consistency review rubric, fresh-clone intake, and receipt field guide.
- Two clean-copy mutation guards requiring structured failed receipts on tampered-receipt acceptance and deliberately failed evaluation.
- Comparative implementation mappings for LangGraph, OpenAI Agents SDK, CrewAI Flows, AutoGen AgentChat, Pydantic AI durable execution, Hermes Agent, Pi Agent, NVIDIA NeMo Agent Toolkit, and DeepSeek Harness.
- Framework-neutral external-effect recovery contract with twelve synthetic conformance and regression tests, including harness-specific persistence-versus-effect boundaries.
