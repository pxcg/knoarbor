# KnoArbor Skills

This directory contains generic host-AI skills for operating a local KnoArbor service.

## Codex Local Install

Copy the local skill into Codex's local skills directory:

```bash
mkdir -p ~/.codex/skills/knoarbor-local
rsync -a --delete integrations/skills/query/knoarbor-local/ ~/.codex/skills/knoarbor-local/
```

Restart Codex so the skill list is reloaded.

The skill calls KnoArbor's stable local API. It can query, read pages, trigger requested ingest/lint runs, inspect reports, and check runtime state. The host AI remains responsible for final answers and user-facing judgment.

## Runtime Configuration

The bundled helper script resolves settings in this order:

1. Command arguments: `--base-url`, `--vault`, `--config`.
2. Environment variables: `KNOARBOR_BASE_URL`, `KNOARBOR_VAULT_PATH`, `KNOARBOR_CONFIG_PATH`.
3. `.knoarbor/endpoint.json` next to `config.yaml`.
4. `config.yaml` in the current working directory.
5. `~/Projects/KnoArbor/config.yaml`.

Example:

```bash
python3 ~/.codex/skills/knoarbor-local/scripts/knoarbor.py query \
  "Agent Loop 和控制模式是什么？" \
  --mode balanced \
  --max-results 6
```

Read a returned page path:

```bash
python3 ~/.codex/skills/knoarbor-local/scripts/knoarbor.py page read \
  concepts/Agent-Loop-and-Control-Patterns.md
```
