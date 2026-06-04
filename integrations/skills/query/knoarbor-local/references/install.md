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

Copy the whole skill directory, including `scripts/knoarbor.py`, `references/`,
and `resources/`, into the host AI tool's skill directory.

Example for Codex:

```bash
mkdir -p ~/.codex/skills
cp -R knoarbor-local ~/.codex/skills/knoarbor-local
```

Restart the host AI tool after installation so it reloads `SKILL.md`.

## Runtime requirement

The bundled helper uses only the Python standard library and expects `python3`
to be available. It does not require the KnoArbor Python package to be installed
inside the host AI tool. Run helper commands from the skill directory, not from
the KnoArbor project directory.

If the host environment cannot run Python, use `references/http-api.md` to call
the local HTTP API directly with `curl` or the host tool's HTTP client.

## 3. Runtime discovery

The helper discovers the active local service from `config.yaml` and
`.knoarbor/endpoint.json` when those files are available.

For HTTP-only hosts, call `GET /runtime` after the base URL is known. The
response provides the active vault path. If the service selected a different
port and local files are readable, inspect `.knoarbor/endpoint.json` next to
`config.yaml`.

## 4. Test the skill

From the skill directory:

```bash
python3 scripts/knoarbor.py check
python3 scripts/knoarbor.py query "agent loop control patterns"
python3 scripts/knoarbor.py page read concepts/Agent-Loop-and-Control-Patterns.md
```

Use `example-request.json` and `response-example.json` when adapting the skill
to another host AI tool.
