# KnoArbor Skills

This directory contains generic host-AI skills for querying a local KnoArbor service.

## Codex Local Install

Copy the query skill into Codex's local skills directory:

```bash
mkdir -p ~/.codex/skills/knoarbor-local
rsync -a --delete integrations/skills/query/knoarbor-local/ ~/.codex/skills/knoarbor-local/
```

Restart Codex so the skill list is reloaded.

The skill calls the local query API only. KnoArbor returns bounded context and evidence; the host AI remains responsible for the final answer.

## Runtime Configuration

The bundled helper script resolves settings in this order:

1. Command arguments: `--base-url`, `--vault`, `--config`.
2. Environment variables: `KNOARBOR_BASE_URL`, `KNOARBOR_VAULT_PATH`, `KNOARBOR_CONFIG_PATH`.
3. `config.yaml` in the current working directory.
4. `~/Projects/KnoArbor/config.yaml`.

Example:

```bash
python3 ~/.codex/skills/knoarbor-local/scripts/query.py \
  "Agent Loop 和控制模式是什么？" \
  --mode balanced \
  --max-results 6
```
