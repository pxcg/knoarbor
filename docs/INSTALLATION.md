# Installation

KnoArbor is a local-first Python service with a bundled management UI. A first
installation usually means cloning the repository, creating local config files,
starting the FastAPI service, and opening the UI in a browser.

## Requirements

- Python 3.12
- `uv`
- One OpenAI-compatible model provider
- Optional: Node.js 20+ only when rebuilding the web UI from source

## Local Installation

```bash
git clone https://github.com/pxcg/knoarbor.git
cd knoarbor
uv sync
uv run knoar first-run --vault ./wiki
```

Create local secret/config files:

```bash
cp .env.example .env
```

Edit `.env` and set at least one model key, for example:

```bash
DEEPSEEK_API_KEY=your-key
```

Load the environment variables:

```bash
set -a && source .env && set +a
```

Run a read-only readiness check:

```bash
uv run knoar doctor
```

Start the service:

```bash
uv run knoar serve
```

The server prints the active UI and API addresses. If port `8000` is already in
use, KnoArbor selects the next available local port and writes the runtime
endpoint to `.knoarbor/endpoint.json` and `~/.knoarbor/endpoint.json`.

## Verify The Installation

Open the UI:

```text
http://127.0.0.1:8000
```

Run the bundled Markdown example:

```bash
uv run knoar ingest --connector markdown --write
uv run knoar lint --mode structural
uv run knoar query "Agent Loop 是什么？"
```

The generated wiki pages and reports are written under the configured `wiki/`
directory.

## Model Providers

Model providers are configured in `config.yaml`; secrets stay in `.env`.
DeepSeek, OpenAI, OpenRouter, Ollama, LM Studio, vLLM, and other
OpenAI-compatible endpoints can use the same provider shape:

```yaml
models:
  default_provider: deepseek
  providers:
    deepseek:
      base_url: https://api.deepseek.com
      api_key_env: DEEPSEEK_API_KEY
      model: deepseek-v4-flash
```

Local providers such as Ollama or vLLM may use `api_key_env: null`. Run
`uv run knoar doctor --json` after starting a local model endpoint to confirm
that the configured model is visible. For local models, set provider-level
`context_window` and `max_output_tokens` to match the model runtime, for example
`context_window: 32768` and `max_output_tokens: 8000`.

## Rich Document Processing

Markdown files are ingested directly. PDF, DOCX, PPTX, and other rich documents
require a configured MinerU-compatible preprocessing service. KnoArbor does not
redistribute MinerU or model weights; users who enable that adapter install and
run MinerU separately.

## Rebuilding The UI

The repository ships built UI assets. Rebuild them only when changing the
frontend:

```bash
cd web
npm install
npm run build
cd ..
```

The build copies assets into `src/knoarbor/ui/dist/`, where the Python service
serves them.

## Common Checks

```bash
uv run knoar doctor
uv run knoar status
uv run knoar sources --catalog
uv run knoar runs
```

See [Troubleshooting](TROUBLESHOOTING.md) for model, UI, ingest, and runtime
issues.
