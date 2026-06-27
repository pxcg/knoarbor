# KnoArbor Skills

This directory contains generic host-AI skills for operating a local KnoArbor service.

## Codex Local Install

Copy the local skill into Codex's local skills directory:

```bash
mkdir -p ~/.codex/skills/knoarbor-local
rsync -a --delete integrations/skills/knoarbor-local/ ~/.codex/skills/knoarbor-local/
```

Restart Codex so the skill list is reloaded.

The skill calls KnoArbor's stable local API. It can query, read pages, trigger requested ingest/lint runs, inspect reports, and check runtime state. The host AI remains responsible for final answers and user-facing judgment.

## Runtime Discovery

The bundled helper discovers the active local service from the user-level
runtime endpoint written by `knoar serve`, then from project-local `config.yaml`
and `.knoarbor/endpoint.json` when those files are available. HTTP-only hosts
should call `GET /runtime` after the service URL is known.

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
  Agent-Loop-and-Control-Patterns.md
```
