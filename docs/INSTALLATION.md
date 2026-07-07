# Installation

KnoArbor is a desktop-first local knowledge engine backed by a Python runtime
service. Public release builds are the normal path for end users; source
installation remains the reference path for contributors and for users who want
to run the local service API directly.

## Requirements

- Python 3.12
- `uv`
- One model provider, either OpenAI-compatible or native Ollama
- Optional: Node.js 20+ only when rebuilding the desktop renderer from source

## Local Installation

```bash
git clone https://github.com/pxcg/knoarbor.git
cd knoarbor
uv sync
uv run knoar first-run --vault ./vaults/default
```

Create local config files:

```bash
cp config.example.yaml config.yaml
```

Edit `config.yaml` or the Settings page and configure a model provider with
`base_url`, `api_key`, and `model`.

Run a read-only readiness check:

```bash
uv run knoar doctor
```

Start the service for source development:

```bash
uv run knoar serve
```

The server prints the active local API and developer-console addresses. If port
`8000` is already in use, KnoArbor selects the next available local port and
writes the runtime endpoint to `.knoarbor/endpoint.json` and
`~/.knoarbor/endpoint.json`.

## Verify The Installation

For source development, open the developer console:

```text
http://127.0.0.1:8000
```

Run the bundled Markdown example:

```bash
uv run knoar ingest --connector markdown --write
uv run knoar lint --mode deterministic
uv run knoar query "Agent Loop 是什么？"
```

Generated wiki pages and reports are written under the configured vault
directory, such as `vaults/default/`.

Windows users should keep the project and vault directories in a short path,
such as `C:\knoarbor` or `%USERPROFILE%\knoarbor`, when Windows long path
support is disabled.

## Model Providers

Model providers are configured in `config.yaml`.
DeepSeek, OpenAI, OpenRouter, LM Studio, vLLM, and other OpenAI-compatible
endpoints can use the same provider shape. Ollama can either use its OpenAI
compatibility layer or KnoArbor's native `adapter: ollama`:

```yaml
models:
  default_provider: deepseek
  providers:
    deepseek:
      base_url: https://api.deepseek.com
      api_key:
      model: deepseek-v4-flash
```

Local providers such as Ollama or vLLM may leave `api_key` empty. Run
`uv run knoar doctor --json` after starting a local model endpoint to confirm
that the configured model is visible. For local models, set provider-level
`context_window` and `max_output_tokens` to match the model runtime, for example
`context_window: 32768` and `max_output_tokens: 8000`.

Native Ollama example:

```yaml
models:
  default_provider: ollama
  providers:
    ollama:
      adapter: ollama
      base_url: http://127.0.0.1:11434
      api_key:
      model: qwen3.6:27b-q4_K_M
      json_mode: true
      context_window: 262144
      max_output_tokens: 8000
```

## Rich Document Processing

Markdown files are ingested directly. PDF, DOCX, PPTX, and other rich documents
require a configured MinerU-compatible preprocessing service. KnoArbor does not
redistribute MinerU or model weights; users who enable that adapter install and
run MinerU separately.

For a local MinerU source checkout, the compatible API can be started with:

```bash
cd /path/to/MinerU
.venv/bin/mineru-api --host 127.0.0.1 --port 18000
```

Configure `document_processing.mineru.endpoint` as
`http://127.0.0.1:18000/file_parse`. If MinerU writes image assets, KnoArbor
records them as Markdown-sidecar attachments and exposes them in the source
digest audit page.

Chat source defaults such as `~/.codex/sessions`, `~/.claude/projects`, and
`~/.hermes/sessions` expand to the current user's home directory. On Windows,
the equivalent resolved paths are under `%USERPROFILE%`, for example
`C:\Users\Alice\.codex\sessions`.

## Rebuilding The Renderer

The repository ships built renderer assets. Rebuild them only when changing the
desktop renderer:

```bash
cd web
npm install
npm run build
cd ..
```

During the transition, the build still copies assets into
`src/knoarbor/ui/dist/` for the Python developer console. The desktop package is
the target product surface.

## Common Checks

```bash
uv run knoar doctor
uv run knoar status
uv run knoar sources --catalog
uv run knoar runs
```

See [Troubleshooting](TROUBLESHOOTING.md) for model, UI, ingest, and runtime
issues.
