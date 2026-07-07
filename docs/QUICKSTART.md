# Quickstart

This guide gets a fresh KnoArbor clone to a first successful local wiki chat.
It uses the bundled Markdown example first. After that works, add your own
sources in the same vault.

## Recommended First Path

For the first run, keep the setup narrow:

- use the bundled `agent-loop.md` example;
- use one OpenAI-compatible provider such as DeepSeek, OpenAI, OpenRouter, LM Studio, or vLLM, or native Ollama;
- run `doctor` before semantic workflows;
- verify the result in desktop Chat, or in the developer console when running from source.

## 1. Install

Requirements:

- Python 3.12
- `uv`
- one model provider

Install dependencies:

```bash
uv sync
```

## 2. Initialize A Vault

Create local configuration, initialize the default vault, and install the
bundled example source:

```bash
uv run knoar first-run --vault ./vaults/default
```

This creates `config.yaml`, initializes `./vaults/default`, and copies
`agent-loop.md` into `vaults/default/raw/inbox/notes/`.

Edit `config.yaml` or Settings and set one model provider with `base_url`,
`api_key`, and `model`.

Run the read-only readiness check:

```bash
uv run knoar doctor
```

`doctor` checks config loading, vault structure, model provider settings,
enabled connectors, optional document preprocessing, and recent run state
without calling the model or writing wiki pages.

## 3. Compile The Example

Compile the bundled Markdown source into maintained wiki pages:

```bash
uv run knoar ingest --connector markdown --write
```

Run structural maintenance:

```bash
uv run knoar lint --mode deterministic
```

The generated wiki pages are written under:

```text
vaults/default/wiki/pages/
```

Open this `wiki/pages/` directory in Obsidian when you only want the maintained
Markdown wiki, without raw sources, reports, or machine state.

## 4. Open Chat

For the desktop app, open the workspace and use **Chat** directly.

When running from source, start the local service:

```bash
uv run knoar serve
```

If port `8000` is already in use, the server chooses the next available local
port and prints the actual URL.

Then open the developer console:

```text
http://127.0.0.1:8000
```

In Chat:

1. Open **Chat**.
2. Ask `Agent Loop 是什么？`.
3. Expand the answer sources.
4. Click a citation to preview the wiki page without leaving the chat.

This verifies the main user path: source -> ingest -> maintained wiki page ->
cited chat answer.

## 5. Verify From CLI

You can also query the generated wiki from the terminal:

```bash
uv run knoar query "Agent Loop 是什么？"
```

Use `knoarbor` instead of `knoar` if you prefer the full command name:

```bash
uv run knoarbor --help
```

## 6. Add Your Own Sources

After the bundled example works, add your own source roots in `config.yaml` or
desktop Settings, then run:

```bash
uv run knoar ingest --write
```

For one prepared `source_document.v1` JSON file:

```bash
uv run knoar ingest --source-document /path/to/source_document.json --write
```

## 7. Maintain The Wiki

Structural repair:

```bash
uv run knoar lint
```

Quality review:

```bash
uv run knoar lint --mode semantic
```

Apply reviewed semantic maintenance operations:

```bash
uv run knoar lint --mode semantic --apply-reviewed
```

## Next Documents

- [Configuration](CONFIGURATION.md): model providers, vaults, inputs, and document preprocessing.
- [CLI Reference](CLI.md): full command-line options.
- [Troubleshooting](TROUBLESHOOTING.md): common setup, model, and runtime issues.
