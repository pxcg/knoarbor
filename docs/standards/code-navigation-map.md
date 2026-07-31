# Code Navigation Map

Use this map to find the smallest current owner before editing.

| Concern | Formal code host | Stable contract | Focused evidence |
| --- | --- | --- | --- |
| Source ingestion and publication | `src/knoarbor/services/ingest_coordinator.py`, `src/knoarbor/storage/source_revisions.py` | `docs/CONTRACTS.md`, spec 1.26 | `tests/test_ingest*.py`, full-chain ingest cases |
| Query evidence | `src/knoarbor/pipelines/query.py`, `src/knoarbor/retrieval/` | `docs/CONTRACTS.md`, spec 1.38 | `tests/test_query*.py` |
| Chat decision and composition | `src/knoarbor/services/chat_session_workflow.py`, `chat_answer_decision.py`, `chat_response_composer.py` | `docs/CONTRACTS.md`, ADRs 0019-0021 | `tests/test_chat*.py` |
| Runtime lifecycle and recovery | `src/knoarbor/runtime/` | `docs/ARCHITECTURE.md`, `docs/CONTRACTS.md` | runtime and ingest recovery tests |
| Public HTTP boundary | `src/knoarbor/entrypoints/api_contract.py`, `api.py` | `docs/API.md`, `docs/API_COMPATIBILITY.md` | API contract tests |
| Renderer | `renderer/src/` | `docs/UI_CONTRACT.md` | renderer typecheck and Playwright |
| Desktop lifecycle | `desktop/src/main/` | `docs/ARCHITECTURE.md`, desktop specs | desktop tests, packaging smoke |
| Documentation and SDD | `docs/`, `specs/` | `docs/DOCUMENTATION_GOVERNANCE.md`, `specs/README.md` | documentation governance and link checks |
| Development Harness | `harness/`, `.codex/skills/` | spec 1.41 and these standards | Harness Core check, Adapter typecheck/tests, bootstrap journey |

`harness/rules/semantic-hosts.json` is a machine-readable projection of the
stable contracts above. It cannot introduce an owner or responsibility not
declared in those contracts.
