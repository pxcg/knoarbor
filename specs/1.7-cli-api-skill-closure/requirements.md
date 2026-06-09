# 1.7 CLI, API, And Skill Closure Requirements

## Problem

KnoArbor exposes the same core capabilities through CLI, HTTP API, UI, and host
AI skills. As the project approaches a long-term compatibility baseline, these
entry points need to feel like consistent front doors into the same system.

The 1.7 line should close gaps between CLI, API, and skill surfaces before the
2.0 compatibility freeze.

## Goals

- Keep the public API small and capability-oriented.
- Preserve response envelopes and schema versions.
- Keep CLI human-readable by default and machine-readable with `--json`.
- Keep skill behavior focused on context retrieval and stable workflow calls.
- Ensure skill operations map cleanly to public APIs, not `/ui/api/*`.
- Provide enough examples for host AI tools to use query, page reads, reports,
  sources, ingest, lint, and diagnostics naturally.

## Non-Goals

- Do not turn the skill into a separate agent runtime.
- Do not make query call an answer-generation model.
- Do not expose every internal UI endpoint publicly.
- Do not preserve prototype compatibility during active pre-2.0 development.

## User Scenarios

### Use From Terminal

As a CLI user, I can run ingest, lint, query, sources, reports, and diagnostics
with consistent flags and readable output.

Acceptance criteria:

- `--json` returns machine-readable output.
- Long-running commands follow run progress by default unless disabled.
- Errors use stable error codes.

### Use From HTTP Clients

As an automation user, I can call a compact API from curl, Apifox, Postman, or
an AI tool.

Acceptance criteria:

- Public endpoints are documented.
- Workflow endpoints use stable response envelopes.
- `/ui/api/*` is clearly internal.

### Use From Host AI Skills

As a host-AI user, I can query context, inspect pages/reports/runs/sources, and
trigger supported workflows through the skill without learning internal paths.

Acceptance criteria:

- Skill discovers runtime context through the public runtime endpoint file/API.
- Skill operations use public APIs.
- Skill docs include natural-language-to-operation examples.

## Current Status

Implemented:

- Stable API families for health, runtime, doctor, sources, ingest, lint, query,
  reports, runs, and wiki pages.
- CLI commands for core workflows.
- Local skill template with query, page, report, run, source, ingest, and lint
  operations.
- Runtime endpoint discovery.

Still in scope for 1.7:

- Audit CLI/API/skill parity.
- Freeze command/endpoint names approaching 2.0.
- Improve skill operation examples and error guidance.
- Ensure all public surfaces report the same run/report/page concepts.
