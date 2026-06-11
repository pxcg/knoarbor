# Quickstart

This guide gets a local KnoArbor vault running from a fresh clone.

## 1. Install

Requirements:

- Python 3.12
- `uv`
- One OpenAI-compatible model provider, such as DeepSeek, OpenAI, OpenRouter, Ollama, LM Studio, or vLLM

Install dependencies:

```bash
uv sync
```

## 2. First Run

Create local configuration, initialize the vault, and install the bundled
example source:

```bash
uv run knoar first-run --vault ./vaults/all
```

This creates `config.yaml`, initializes `./vaults/all`, and copies
`agent-loop.md` into `vaults/all/raw/notes/`.

Create `.env` and set at least one model key:

```bash
cp .env.example .env
DEEPSEEK_API_KEY=your-key
```

Load the variables into the current shell before running semantic commands:

```bash
set -a && source .env && set +a
```

Edit `config.yaml` if needed:

```yaml
vault:
  path: ./vaults/all

models:
  default_provider: deepseek
```

Run the read-only readiness check:

```bash
uv run knoar doctor
```

`doctor` checks config loading, vault structure, model environment variables,
enabled connectors, optional document preprocessing, and recent run state
without calling the model or writing wiki pages.

## 3. Run The API

```bash
uv run knoar serve
```

If port `8000` is already in use, the server will choose the next available
local port and print the actual URL.

Health check:

```bash
curl http://127.0.0.1:8000/health
```

Open the local management console:

```text
http://127.0.0.1:8000
```

## 4. Run The Built-In Example

Compile it into wiki pages:

```bash
uv run knoar ingest --connector markdown --write
```

Run structural maintenance:

```bash
uv run knoar lint --mode structural
```

Query the generated wiki:

```bash
uv run knoar query "Agent Loop 是什么？"
```

## 5. Ingest Your Own Sources

For connector-based ingest:

```bash
uv run knoar ingest --write
```

For one prepared `source_document.v1` JSON file:

```bash
uv run knoar ingest --source-document /path/to/source_document.json --write
```

## 6. Run Lint

Structural repair:

```bash
uv run knoar lint
```

Quality review:

```bash
uv run knoar lint --mode quality
```

Apply reviewed semantic maintenance operations:

```bash
uv run knoar lint --mode full --apply-reviewed
```
