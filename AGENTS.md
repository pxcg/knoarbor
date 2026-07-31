# AGENTS.md

Project-level instructions for KnoArbor agent sessions.

## Project

- KnoArbor is a local-first Python knowledge runtime with renderer and desktop
  adapters.
- Route behavior through the owning Python contract; renderer and desktop code
  consume public API or IPC contracts and do not merge domain truth.
- Reusable changes land on public `main` before flowing to the private
  downstream.

## Development

- Classify work with `docs/standards/development-workflow.md`.
- Invoke `development-harness-controller` only for an admitted Patterned
  Harness Initiative.
- Use `development-workflow` for Direct Maintenance and Direct SDD.
- Read the owning spec and stable contract before implementation.
- Run focused owner checks before the affected closure.
- Never store credentials, raw model output, private source content, or
  machine-local paths in tracked Harness evidence.
