# Install KnoArbor Local Skill

This skill is a thin client for a local KnoArbor service. It does not include
the KnoArbor server. It can query, read pages, trigger ingest/lint runs, and
inspect reports through the stable local API.

## 1. Install or clone KnoArbor

Follow the KnoArbor project README, then start the service:

```bash
uv run knoar serve
```

## 2. Install the skill

Copy the whole skill directory, including `scripts/`, `references/`, and
`resources/`, into the host AI tool's skill directory.

Example for Codex:

```bash
mkdir -p ~/.codex/skills
cp -R knoarbor-local ~/.codex/skills/knoarbor-local
```

Restart the host AI tool after installation so it reloads `SKILL.md`.

## 3. Configure discovery

The helper can usually discover the local service from `config.yaml` and
`.knoarbor/endpoint.json`. If needed, set explicit environment variables:

```bash
export KNOARBOR_BASE_URL=http://127.0.0.1:8000
export KNOARBOR_VAULT_PATH=/absolute/path/to/wiki
```

See `example.env`.

## 4. Test the skill

From the skill directory:

```bash
python3 scripts/knoarbor.py check
python3 scripts/knoarbor.py query "agent loop control patterns"
python3 scripts/knoarbor.py page read concepts/Agent-Loop-and-Control-Patterns.md
```

Use `example-request.json` and `response-example.json` when adapting the skill
to another host AI tool.
