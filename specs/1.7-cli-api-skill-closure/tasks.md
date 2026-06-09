# 1.7 CLI, API, And Skill Closure Tasks

## Surface Parity

- [next] Audit CLI/API/skill operation parity.
- [next] Record intentional differences in this spec.
- [later] Add tests that compare public API families with CLI and skill docs.

## Skill Maturity

- [next] Expand natural-language-to-operation examples.
- [later] Add clearer error guidance and recovery examples.
- [later] Verify runtime discovery across changed ports and multiple vaults.

## API Closure

- [later] Recheck public endpoint list before 2.0.
- [later] Ensure response envelopes are stable across direct and queued modes.
- [later] Keep `/ui/api/*` internal and absent from skill docs.

## CLI Closure

- [later] Ensure every stable workflow has human and JSON output.
- [later] Normalize flag names across vault selection, config, provider, and execution.
- [later] Update shell examples before release.

## Deferred

- [deferred] MCP server package.
- [deferred] Standalone hosted skill service.
- [deferred] npm replacement for the Python runtime.
