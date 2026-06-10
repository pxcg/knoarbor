# 1.7 CLI, API, And Skill Closure Tasks

## Surface Parity

- [done] Audit CLI/API/skill operation parity.
- [done] Record intentional differences in this spec.
- [later] Add tests that compare public API families with CLI and skill docs.

## Skill Maturity

- [done] Normalize the bundle path as `integrations/skills/knoarbor-local`.
- [done] Expand natural-language-to-operation examples.
- [done] Add clearer error guidance and recovery examples.
- [done] Verify runtime discovery across changed ports and multiple vaults.

## API Closure

- [done] Recheck public endpoint list before 2.0.
- [done] Ensure response envelopes are stable across direct and queued modes.
- [done] Keep `/ui/api/*` internal and absent from skill docs.

## CLI Closure

- [done] Add read-only page and report drilldown commands.
- [done] Ensure every stable workflow has human and JSON output.
- [done] Normalize flag names across vault selection, config, provider, and execution.
- [done] Update shell examples before release.

## Deferred

- [deferred] MCP server package.
- [deferred] Standalone hosted skill service.
- [deferred] npm replacement for the Python runtime.
