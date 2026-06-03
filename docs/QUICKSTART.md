# Quickstart

This guide gets a local KnoArbor vault running from a fresh clone.

## 1. Install

Requirements:

- Python 3.12
- `uv`
- One OpenAI-compatible model provider, such as DeepSeek, OpenAI, OpenRouter, Ollama, or LM Studio

Install dependencies:

```bash
uv sync
```

## 2. Configure

Create local config files:

```bash
cp config.example.yaml config.yaml
cp .env.example .env
```

Edit `.env` and set at least one model key:

```bash
DEEPSEEK_API_KEY=your-key
```

Load the variables into the current shell before running semantic commands:

```bash
set -a && source .env && set +a
```

Edit `config.yaml` if needed:

```yaml
vault:
  path: ./wiki

models:
  default_provider: deepseek
```

## 3. Initialize A Vault

```bash
uv run knoar init --vault ./wiki
```

This creates the runtime wiki structure. The `wiki/` directory is intentionally ignored by git.

Run the read-only readiness check:

```bash
uv run knoar doctor
```

`doctor` checks config loading, vault structure, model environment variables,
enabled connectors, optional document preprocessing, and recent run state
without calling the model or writing wiki pages.

## 4. Run The API

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

## 5. Run The Built-In Example

Copy the example Markdown note into the default raw notes directory:

```bash
mkdir -p wiki/raw/notes
cp examples/agent-loop.md wiki/raw/notes/agent-loop.md
```

Compile it into wiki pages:

```bash
uv run knoar ingest --connector markdown --write
```

Run structural maintenance:

```bash
uv run knoar lint-run --mode structural
```

Query the generated wiki:

```bash
uv run knoar query "Agent Loop 是什么？"
```

## 6. Ingest Your Own Sources

For connector-based ingest:

```bash
uv run knoar ingest --write
```

For one prepared `source_document.v1` JSON file:

```bash
uv run knoar ingest-document --input /path/to/source_document.json --write
```

## 7. Run Lint

Structural repair:

```bash
uv run knoar lint-run
```

Quality review:

```bash
uv run knoar lint-run --mode quality
```

Apply reviewed semantic maintenance operations:

```bash
uv run knoar lint-run --mode full --apply-reviewed
```
