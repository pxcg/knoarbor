# Configuration

KnoArbor uses two local files:

- `config.yaml`: non-secret local settings.
- `.env`: secrets and tokens.

Both files are ignored by git. Copy the examples before running:

```bash
cp config.example.yaml config.yaml
cp .env.example .env
set -a && source .env && set +a
```

The CLI/API reads secrets from process environment variables. Loading `.env` is a shell step for source-based usage. The packaged desktop app stores its runtime files under the app data directory and loads its own `.env` automatically when starting the managed local service:

```text
macOS: ~/Library/Application Support/KnoArbor/.env
Windows: %APPDATA%/KnoArbor/.env
Linux: ~/.config/KnoArbor/.env
```

The desktop settings page writes API keys to that `.env` file and keeps `config.yaml` limited to environment variable names such as `DEEPSEEK_API_KEY`.

`config_version` identifies the configuration schema. The first public schema is:

```yaml
config_version: 1
```

Future incompatible configuration changes should ship with migration helpers instead of silently changing behavior.

Config loading follows a fixed order:

```text
read YAML/JSON -> migrate schema -> resolve local paths -> validate typed config
```

Migration helpers are structural only. They may move or rename fields in a future schema, but they do not guess user intent, repair secrets, or invent local paths. Config files newer than the running KnoArbor build fail explicitly.

## Vault

```yaml
vaults:
  default: default
  profiles:
    default:
      name: My Knowledge Base
      path: ./vaults/default

vault:
  path: ./vaults/default
```

`vaults.profiles` is the formal multi-vault registry. Each profile has a stable
ID, a display name, and a local path. `vaults.default` selects the active vault
used by CLI, API, UI, and host-AI skill calls when no request-specific path is
provided.

`all` is reserved as a virtual query scope. Do not create a real profile with
ID `all`; use `all_vaults: true` or `vault_id: "all"` when a query should search
every configured concrete vault.

`vault.path` is the resolved active vault path kept for simple one-vault
deployments and internal request defaults. When `vaults.profiles` is present,
KnoArbor derives `vault.path` from `vaults.default`.

Vault directories are runtime Markdown knowledge bases. They are ignored by git
because they can contain private notes, source documents, generated pages,
checkpoints, ledgers, and reports.

## Models

The default configuration uses one model provider for all semantic workflows:

```yaml
models:
  default_provider: deepseek
  default_max_tokens: 30000
  request_timeout_seconds: 600
  retry:
    enabled: true
    max_attempts: 2
    backoff_seconds: 2
    retry_on_invalid_output: true
    retryable_error_codes:
      - KA-EXT-001
      - KA-MODEL-001
      - KA-SEM-001
      - KA-STORAGE-001
  providers:
    deepseek:
      base_url: https://api.deepseek.com
      api_key_env: DEEPSEEK_API_KEY
      model: deepseek-v4-flash
      json_mode: true
      verify_tls: true
      tls_ca_file:
      context_window:
      max_output_tokens:
```

Model calls pass through the `ModelGateway` boundary. Providers use the `openai_compatible` adapter by default. Ollama can use `adapter: ollama` to call the native `/api/chat` endpoint; this is recommended for Ollama thinking models because KnoArbor can send `think: false` and avoid reasoning-only responses. Hosted providers usually need `api_key_env`; local or private endpoints such as Ollama and vLLM may set `api_key_env: null`.

`default_max_tokens` and `request_timeout_seconds` are intentionally generous. Ingest and lint are wiki compilation tasks, not short chat replies; page planning, page drafting, and maintenance review often need longer outputs and more time. A provider can override the global output limit with `max_output_tokens`. `context_window` records the model's usable context window for diagnostics and budget checks. Runtime diagnostics try to detect context length from vLLM `/v1/models` metadata and Ollama `/api/show`; when detection is unavailable, KnoArbor falls back to the configured `context_window`.

Configuration design follows the common shape used by AI workflow projects:

- One global default model for most users.
- A provider registry for users who need to switch between DeepSeek, OpenAI-compatible gateways, Ollama native, local servers, or hosted providers.
- Secrets referenced by environment variable name instead of being stored in YAML.
- Runtime limits such as output tokens and request timeout exposed as first-class configuration.
- Prompt caching remains provider-owned and does not require a KnoArbor config switch. KnoArbor keeps semantic contract prompts stable and puts dynamic source/wiki payloads in later user-message content. It also records provider cache usage when returned by the API.
- TLS verification is provider-scoped. Keep `verify_tls: true` for hosted APIs. For an internal HTTPS endpoint with a private CA, set `tls_ca_file` to the CA bundle path. Use `verify_tls: false` only for a trusted endpoint you control.

Semantic model retries are an explicit runner policy, not a hidden downstream fallback. `SemanticRunner` may retry retryable provider failures and invalid structured model output before the result reaches ingest or lint. Page writes still happen only after a full source or reviewed maintenance batch is approved, so a retried model call cannot partially commit a page by itself.

`retryable_error_codes` is the public retry allowlist. Keep it narrow: external service failures, model output/semantic contract failures, and storage conflicts are safe to retry; deterministic input/config/policy failures should be fixed rather than retried.

Common examples:

```yaml
models:
  default_provider: deepseek
  providers:
    deepseek:
      base_url: https://api.deepseek.com
      api_key_env: DEEPSEEK_API_KEY
      model: deepseek-v4-flash
    openai:
      base_url: https://api.openai.com/v1
      api_key_env: OPENAI_API_KEY
      model: gpt-4.1
    openrouter:
      base_url: https://openrouter.ai/api/v1
      api_key_env: OPENROUTER_API_KEY
      model: deepseek/deepseek-chat-v3.1
    ollama:
      adapter: ollama
      base_url: http://localhost:11434
      api_key_env:
      model: qwen3.6:27b-q4_K_M
      json_mode: true
      verify_tls: true
      tls_ca_file:
      context_window: 262144
      max_output_tokens: 8000
      extra_body:
        think: false
    ollama-openai-compatible:
      base_url: http://localhost:11434/v1
      api_key_env:
      model: qwen3:14b
      json_mode: true
      context_window: 32768
      max_output_tokens: 8000
    vllm:
      base_url: http://localhost:8001/v1
      api_key_env:
      model: Qwen/Qwen3-32B-Instruct
      json_mode: false
      context_window: 32768
      max_output_tokens: 8000
```

`max_tokens` passed from CLI or API has the highest priority for a single run. If it is omitted, KnoArbor uses the selected provider's `max_output_tokens`; if that is also omitted, it uses `models.default_max_tokens`.

For local providers, run `uv run knoar doctor --json` after starting the
runtime. Doctor checks the adapter-specific discovery endpoint: OpenAI-compatible
providers use `/models`, while native Ollama uses `/api/tags` and `/api/show`.
Keep `json_mode: false` until the local model has been verified with structured
KnoArbor workflows; hosted providers and verified Ollama models with stable JSON
object output can keep `json_mode: true`.

Model capability checks are also available through the stable API:

- `GET /models/providers` lists configured providers without contacting the model runtime.
- `GET /models/image-providers` lists configured image-generation providers without contacting the image runtime.
- `POST /models/discover` reads provider model metadata and tries to detect context length without generating tokens.
- `POST /models/probe` runs a bounded generation check; use `minimal` for connectivity and `structured` for JSON contract support.
- `POST /models/apply-capabilities` explicitly writes detected or selected `context_window`, `max_output_tokens`, and `json_mode` back to `config.yaml`.

Discovery and probes never mutate configuration by themselves. This keeps local
model experiments reversible: inspect the result first, then apply capabilities
only when the detected values match the model you intend to use.

Image-generation providers are configured separately from chat/completion
providers. Chat, ingest, lint, and query use `models`; image generation uses
`image_generation` and is invoked only when chat planning selects the
`generate_image` tool.

```yaml
image_generation:
  default_provider: sensenova
  request_timeout_seconds: 120
  providers:
    sensenova:
      adapter: sensenova_image
      base_url: https://token.sensenova.cn/v1
      endpoint_path: /images/generations
      api_key_env: SN_API_KEY
      model: sensenova-u1-fast
      resolution: "2720*1536"
      num_inference_steps: 20
      guidance: 4
```

Temporary CLI override:

```bash
uv run knoar ingest --provider openrouter --write
uv run knoar lint --provider deepseek --mode quality
```

## Chat Session Ingest

KnoArbor chat sessions are stored under `.knoarbor/chat/` in the selected
vault. They are not maintained wiki pages by default. A session can be
manually queued into the normal ingest pipeline from the console or API.

Closing a chat session can also trigger ingest automatically when the policy is
enabled:

```yaml
chat:
  auto_ingest:
    enabled: false
    trigger: on_session_close
    min_user_turns: 2
    write: true
    write_report: true
    append_ledger: true
```

The automatic path converts the closed session into a `knoarbor_chat`
`SourceDocument`, then uses the same segmentation, semantic ingest, write,
report, and checkpoint pipeline as other document inputs.

## Chat Memory

Chat memory stores durable interaction preferences for the Wiki Chat Agent. It
is separate from wiki pages and source digests:

```yaml
memory:
  enabled: true
  auto_write_explicit_low_risk: true
  max_recalled_records: 12
```

Memory files are stored under `.knoarbor/memory/` inside the selected vault:

- `records.jsonl`: memory records used for recall;
- `candidates.jsonl`: proposed or automatically written candidates;
- `events.jsonl`: recall and write audit events.

The first implementation captures only explicit low-risk preferences such as
“remember this”, “以后默认……”, or “prefer ...”. It does not store arbitrary chat
transcripts or turn raw wiki content into memory.

## Ingest Segmentation

Long source segmentation is part of the core ingest pipeline. It runs after a
connector has produced a standard `SourceDocument` and after chat checkpoints
have selected the new message window.

```yaml
ingest:
  segmentation:
    enabled: true
    max_chars_per_segment: 18000
    soft_chars_per_segment: 12000
    max_segments_per_source: 20
    min_segment_chars: 1000
  recovery:
    enabled: true
    execution_ledger_path: .knoarbor/ledgers/ingest_execution.jsonl
  concurrency:
    max_concurrent_sources: 1
```

The first implementation uses character budgets instead of tokenizer-specific
token counts. Markdown is split by headings, Codex/Hermes/OpenClaw/Claude Code sessions by turn
groups, parsed documents by sections/pages, and plain text by paragraphs.
Checkpoint commits still happen at the source/window level after all segments
finish, so a partially processed long source is not marked complete.

`recovery` writes a machine-readable source/segment execution ledger for run recovery and debugging. `concurrency.max_concurrent_sources` applies only to dry-run/preflight ingest; write-capable ingest remains serial inside one vault to protect page writes and checkpoints.

## Connectors

Connectors convert external sources into the shared source pipeline.

```yaml
connectors:
  markdown:
    enabled: true
    settings:
      roots:
        - ./vaults/default/raw/inbox/notes
        - ./vaults/default/raw/normalized/markdown
      recursive: true
      raw_output_dir: ./vaults/default/raw/inbox/notes
      preserve_relative_paths: true
```

Supported connector categories in the current codebase:

- `codex`: Codex JSONL session files.
- `hermes`: Hermes TUI session files.
- `openclaw`: OpenClaw JSONL session files.
- `claude_code`: Claude Code JSONL transcript files.
- `generic_chat`: custom local JSONL or SQLite chat transcripts with common `role`/`content`-style fields.
- `markdown`: local Markdown notes.

Enable Codex only when the local Codex session directory exists:

```yaml
connectors:
  codex:
    enabled: true
    settings:
      sessions_dir: ~/.codex/sessions
      pattern: "rollout-*.jsonl"
      recursive: true
      raw_output_dir: ./vaults/default/raw/normalized/chats
```

Enable Hermes only when the local Hermes session directory exists:

```yaml
connectors:
  hermes:
    enabled: true
    settings:
      sessions_dir: ~/.hermes/sessions
      raw_output_dir: ./vaults/default/raw/normalized/chats
```

Enable OpenClaw only when the local OpenClaw session directory exists. The
connector reads the main session `.jsonl` files and intentionally excludes
`.trajectory.jsonl` runtime traces.

```yaml
connectors:
  openclaw:
    enabled: true
    settings:
      sessions_dir: ~/.openclaw/agents/main/sessions
      pattern: "*.jsonl"
      recursive: false
      raw_output_dir: ./vaults/default/raw/normalized/chats
```

Enable Claude Code only when the local Claude Code project transcript directory exists:

```yaml
connectors:
  claude_code:
    enabled: true
    settings:
      sessions_dir: ~/.claude/projects
      pattern: "*.jsonl"
      recursive: true
      raw_output_dir: ./vaults/default/raw/normalized/chats
```

Use `generic_chat` for custom local chat exports only when no dedicated connector exists:

```yaml
connectors:
  generic_chat:
    enabled: true
    settings:
      roots:
        - /path/to/chat/exports
      patterns:
        - "*.jsonl"
        - "*.sqlite"
        - "*.db"
      recursive: true
      raw_output_dir: ./vaults/default/raw/normalized/chats
```

Markdown is the default stable input path. Put notes under a configured root, such as `./vaults/default/raw/inbox/notes`, or add another root:

```yaml
connectors:
  markdown:
    enabled: true
    settings:
      roots:
        - ./vaults/default/raw/inbox/notes
        - /path/to/your/markdown-notes
      recursive: true
```

Optional document processors live under `document_processing`, not under
`connectors`. For example, `document_processing.mineru` can call a user-managed
MinerU-compatible HTTP service and write Markdown into
`vaults/default/raw/normalized/markdown/`; the normal `markdown` connector then ingests that
directory.

Enable MinerU preprocessing only if you already run a compatible service. For a
local source install of MinerU 3.x, start the API with a port that does not
conflict with KnoArbor:

```bash
cd /path/to/MinerU
.venv/bin/mineru-api --host 127.0.0.1 --port 18000
```

Then configure KnoArbor:

```yaml
document_processing:
  mineru:
    enabled: true
    endpoint: http://127.0.0.1:18000/file_parse
    input_dir: ./vaults/default/raw/inbox/documents
    output_dir: ./vaults/default/raw/normalized/markdown
    mode: auto
    timeout_seconds: 600
    patterns:
      - "*.pdf"
      - "*.docx"
      - "*.pptx"
    recursive: true
    file_field: files
    mode_field: parse_method
    extra_fields:
      backend: pipeline
      lang_list: ch
      formula_enable: true
      table_enable: true
      start_page_id: 0
      end_page_id: 99999
      return_md: true
      return_middle_json: false
      return_model_output: false
      return_content_list: false
      return_images: true
      response_format_zip: false
```

MinerU is intentionally not listed as a source connector. It prepares Markdown;
the source connector that compiles the result is still `markdown`.

When MinerU outputs images, KnoArbor records them as source attachments next to
the generated Markdown using a `*.attachments.json` sidecar. The Markdown
connector also scans Markdown image links such as `![figure](images/a.png)`.
During ingest, those attachments are copied into the source digest audit page
under `## Attachments` as a compact readable table with topic, description, and
path. Full audit fields such as MIME type, content hash, page index, bounding
box, and raw MinerU image extraction remain in the sidecar metadata. Image bytes
are not sent to the semantic model.
When a maintained wiki page uses an attachment, the page body keeps only
topic/description attachment rows; retained file paths stay in the source audit
and sidecar metadata.

The management UI keeps only the endpoint visible by default. Use the folded
advanced section when your MinerU deployment needs a different backend such as
`pipeline`, `vlm-engine`, `hybrid-engine`, `vlm-http-client`, or
`hybrid-http-client`, a different
`parse_method`, custom file patterns, or extra multipart fields.

KnoArbor does not vendor or redistribute the MinerU runtime, model weights, or
assets. If you enable this adapter, install and run MinerU separately and review
MinerU's own license and attribution requirements. KnoArbor only interoperates
with a MinerU-compatible HTTP endpoint.

For one-off file or folder input, `ingest --input` chooses the path automatically:

- `.md` / `.markdown` files go directly to the Markdown ingest path;
- folders discover Markdown files recursively by default;
- non-Markdown files call the configured MinerU adapter first;
- if MinerU is disabled, missing, or unreachable, the run stops with an explicit
  configuration error instead of silently skipping or falling back.

Future connectors belong in the roadmap until they are implemented. They should
not be added to `config.example.yaml` ahead of working code, because that makes
the deployable surface ambiguous.

## Privacy

Privacy redaction runs before semantic model calls. Raw sources remain unchanged; the model receives a redacted copy.

```yaml
privacy:
  redaction_enabled: true
  redact_emails: true
  redact_phone_numbers: true
  redact_api_keys: true
  redact_private_keys: true
  redact_local_paths: true
  redact_source_paths_in_pages: true
  redact_private_ips: false
```

`redact_source_paths_in_pages` keeps internal checkpoints on the real source path, but writes a redacted path into generated wiki pages. Use local models or private endpoints for sensitive personal or company data.
