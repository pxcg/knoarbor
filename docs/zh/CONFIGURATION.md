# 配置说明

KnoArbor 的主要配置在 `config.yaml`，模型接口密钥也保存在本地
`config.yaml` 中。

桌面端设置页会直接写入应用数据目录下的 `config.yaml`，普通用户只需要理解
`base_url`、`api_key` 和 `model`。源码运行时也可以直接编辑同一组字段。因为
`config.yaml` 可能包含 API Key，请保持它为本地私有文件。

```text
macOS: ~/Library/Application Support/SieArbor/config.yaml
Windows: %APPDATA%/SieArbor/config.yaml
Linux: ~/.config/SieArbor/config.yaml
```

`config_version` 表示配置 schema 版本。第一版公开配置为：

```yaml
config_version: 1
```

后续如果出现不兼容配置变更，应提供迁移 helper，而不是静默改变行为。

配置加载顺序固定为：

```text
读取 YAML/JSON -> 迁移 schema -> 解析本地路径 -> 校验类型化配置
```

迁移 helper 只做结构迁移。它可以在未来 schema 中移动或重命名字段，但不能猜测用户意图、修复密钥或编造本地路径。如果配置文件版本高于当前 KnoArbor 支持的版本，程序会明确报错。

## 知识库目录

```yaml
vaults:
  default: default
  profiles:
    default:
      name: 我的知识库
      path: ./vaults/default

vault:
  path: ./vaults/default
```

`vaults.profiles` 是正式的多知识库配置。每个 profile 包含稳定 ID、显示名称和本地路径。`vaults.default` 选择当前默认知识库；CLI、API、前端和宿主 AI skill 在没有单次请求路径覆盖时都会使用该默认知识库。

`all` 是保留的虚拟查询范围，不应作为真实 profile ID。需要查询全部知识库时使用 `all_vaults: true` 或 `vault_id: "all"`；真实知识库建议使用 `default`、`personal`、`team` 等稳定 ID。

`vault.path` 是当前默认知识库解析后的路径，用于简单单知识库部署和内部请求默认值。当配置了 `vaults.profiles` 时，KnoArbor 会从 `vaults.default` 自动派生 `vault.path`。

知识库目录会包含 raw sources、Wiki 页面、运行报告、检查点和操作台账。该目录可能包含私人资料，默认不应提交到 git。

## 模型供应商

```yaml
models:
  default_provider: deepseek
  providers:
    deepseek:
      base_url: https://api.deepseek.com
      api_key:
      model: deepseek-v4-flash
      json_mode: true
      tls_ca_file:
      context_window:
      max_output_tokens:
```

推荐默认只配置一个模型供应商。需要备用模型、本地模型或特殊端点时，再添加新的 provider。
模型调用统一经过 `ModelGateway`。provider 默认使用 `openai_compatible` 适配器；Ollama 可以设置 `adapter: ollama`，直接调用原生 `/api/chat`。对于 Qwen 等 thinking 模型，原生 Ollama 适配器会默认发送 `think: false`，避免 OpenAI 兼容层出现 reasoning 很长、正文为空或返回过慢的问题。托管供应商通常需要 `api_key`，本地或内网端点（如 Ollama、vLLM）可以留空 `api_key`。
本地供应商启动后，运行 `uv run knoar doctor --json` 可以检查模型是否可用。OpenAI 兼容适配器会检查 `/models`；Ollama 原生适配器会检查 `/api/tags` 和 `/api/show`。Ollama、vLLM 等本地模型建议显式配置 `context_window` 和 `max_output_tokens`，例如 32K 上下文模型可以先设置为 `context_window: 32768`、`max_output_tokens: 8000`。运行时诊断会尝试从 vLLM `/v1/models` 元数据和 Ollama `/api/show` 自动探测上下文长度；探测不到时回退到配置中的 `context_window`。
单次 CLI/API 请求传入的 `max_tokens` 优先级最高；未传入时使用选中 provider 的 `max_output_tokens`；provider 未配置时再使用 `models.default_max_tokens`。
Ollama、vLLM 等本地模型建议先使用 `json_mode: false`，待该模型通过 KnoArbor 结构化流程验证后再开启 JSON mode。
Prompt caching 由模型供应商实现，不需要在 KnoArbor 中单独开启。KnoArbor 只保证语义契约 prompt 的稳定前缀，并在供应商返回缓存命中指标时写入运行指标和报告；未返回缓存字段的供应商会显示为未提供该遥测，而不是配置错误。
TLS 默认开启校验；内网 HTTPS 端点如果使用私有 CA，可以通过 `tls_ca_file`
指定 CA 证书文件。

Ollama 原生适配器示例：

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
      tls_ca_file:
      context_window: 262144
      max_output_tokens: 8000
      extra_body:
        think: false
```

模型能力检查也可以通过稳定 API 执行：

- `GET /models/providers`：列出已配置的供应商，不访问模型运行时。
- `GET /models/image-providers`：列出已配置的图片生成供应商，不访问图片生成运行时。
- `POST /models/discover`：读取模型端点元数据，检查模型列表接口，并尽量探测上下文长度，不触发生成。
- `POST /models/apply-capabilities`：显式把 `context_window`、`max_output_tokens` 和 `json_mode` 写回 `config.yaml`。

发现不会自动修改配置。建议先查看检查结果，再在确认模型能力后写回配置。

图片生成供应商和聊天/编译模型供应商分开配置。Chat、ingest、lint 和 query 使用
`models`；图片生成使用 `image_generation`，只有当 chat planning 选择
`generate_image` 工具时才会调用。

```yaml
image_generation:
  default_provider: sensenova
  request_timeout_seconds: 120
  providers:
    sensenova:
      adapter: sensenova_image
      base_url: https://token.sensenova.cn/v1
      endpoint_path: /images/generations
      api_key:
      model: sensenova-u1-fast
      resolution: "2720*1536"
      num_inference_steps: 20
      guidance: 4
```

## 对话入库

KnoArbor 自己的 Chat 会话保存在当前知识库的 `.knoarbor/chat/`。它们默认
不是已维护 Wiki 页面。用户可以在控制台或 API 中手动把某个会话排队进入
标准 ingest 流程。

关闭会话时也可以按策略自动触发入库：

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

自动路径会把关闭后的会话转换为 `knoarbor_chat` `SourceDocument`，随后复用
与其他 document 输入相同的分段、语义编译、写入、报告和断点链路。

## 对话记忆

对话记忆保存 Wiki Chat Agent 使用的长期交互偏好。它与 Wiki 页面和 Source Digest 分离：

```yaml
memory:
  enabled: true
  auto_write_explicit_low_risk: true
  max_recalled_records: 12
```

记忆文件保存在当前知识库的 `.knoarbor/memory/`：

- `records.jsonl`：用于召回的记忆记录；
- `candidates.jsonl`：候选或自动写入的记忆；
- `events.jsonl`：召回和写入审计事件。

第一版只捕获用户明确表达的低风险偏好，例如“请记住……”“以后默认……”。它不会保存任意聊天全文，也不会把 Wiki 正文复制成记忆。

## 输入来源

当前稳定入口以 Markdown 和标准化 source document 为主。默认启用 `markdown`，可选启用 `hermes`、`codex`、`openclaw`、`claude_code` 和 `generic_chat`。聊天记录和个人文件都属于一等来源，是否重要由内容决定，不由来源类型决定。

启用 Codex 需要本地存在 Codex JSONL 会话目录：

```yaml
connectors:
  codex:
    enabled: true
    settings:
      sessions_dir: ~/.codex/sessions
      pattern: "rollout-*.jsonl"
      recursive: true
      raw_output_dir: ./vaults/default/raw/inbox/chats
```

启用 Hermes 需要本地存在 Hermes 会话目录：

```yaml
connectors:
  hermes:
    enabled: true
    settings:
      sessions_dir: ~/.hermes/sessions
      raw_output_dir: ./vaults/default/raw/inbox/chats
```

启用 OpenClaw 需要本地存在 OpenClaw 会话目录。该 connector 只读取主会话 `.jsonl`，默认排除 `.trajectory.jsonl` 运行轨迹文件。

```yaml
connectors:
  openclaw:
    enabled: true
    settings:
      sessions_dir: ~/.openclaw/agents/main/sessions
      pattern: "*.jsonl"
      recursive: false
      raw_output_dir: ./vaults/default/raw/inbox/chats
```

启用 Claude Code 需要本地存在 Claude Code 项目会话目录：

```yaml
connectors:
  claude_code:
    enabled: true
    settings:
      sessions_dir: ~/.claude/projects
      pattern: "*.jsonl"
      recursive: true
      raw_output_dir: ./vaults/default/raw/inbox/chats
```

当没有专用 connector 时，可以使用 `generic_chat` 读取常见 `role`/`content` 结构的本地 JSONL 或 SQLite 聊天导出：

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
      raw_output_dir: ./vaults/default/raw/inbox/chats
```

Markdown 是默认稳定入口。可以把笔记放入 `./vaults/default/raw/inbox/notes`，也可以添加自己的 Markdown 目录：

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

富文档应先由外部解析器或 MinerU adapter 转换成 Markdown，再进入同一条知识编译链路。MinerU 属于 `document_processing` 预处理器，不是 source connector。

如果已经自部署 MinerU 兼容服务，可以这样启用。以 MinerU 3.x 源码安装为例，先用一个不和 KnoArbor 冲突的端口启动 API：

```bash
cd /path/to/MinerU
.venv/bin/mineru-api --host 127.0.0.1 --port 18000
```

然后配置 KnoArbor：

```yaml
document_processing:
  mineru:
    enabled: true
    endpoint: http://127.0.0.1:18000/file_parse
    input_dir: ./vaults/default/raw/inbox/documents
    output_dir: ./vaults/default/raw/derived/markdown
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

MinerU 只负责把 PDF/DOCX/PPTX 等富文档转换为 Markdown；最终仍由 `markdown` 输入来源读取转换结果并进入知识编译。

当 MinerU 输出图片时，KnoArbor 会在生成的 Markdown 旁边写入
`*.attachments.json` 附件清单。Markdown connector 也会扫描正文里的图片链接，
例如 `![figure](images/a.png)`。进入 ingest 后，这些附件会写入 source
digest 审计页的 `## Attachments` 章节，并以紧凑表格展示 topic、description
和 path。MIME type、内容 hash、页码、bbox、MinerU 原始图片解析结果等完整审计字段保留在 sidecar metadata 中。图片二进制不会发送给语义模型。
当维护后的 Wiki 页面需要引用附件时，页面正文只保留 topic/description
附件行；文件路径保留在来源审计页和 sidecar metadata 中。

管理界面默认只展示 MinerU 服务地址。只有当你的 MinerU 部署需要切换
`pipeline`、`vlm-engine`、`hybrid-engine`、`vlm-http-client`、`hybrid-http-client` 等后端、调整
`parse_method`、文件匹配规则或额外 multipart 字段时，再展开高级配置修改。

KnoArbor 不内置、不分发 MinerU 运行时、模型权重或素材。如果启用该 adapter，需要用户自行安装并运行 MinerU，同时遵守 MinerU 自身的许可和署名要求。KnoArbor 这里只与 MinerU 兼容 HTTP 端点交互。

## 长内容切分

长文档、长笔记和长聊天记录会在标准 `SourceDocument` 之后进入统一切分层。切分只控制单次模型输入大小，不改变最终 Wiki 页面边界。

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

当前策略：Markdown 按标题切分，Codex/Hermes/OpenClaw/Claude Code 按完整 turn group 切分，解析文档按章节/页段切分，普通文本按段落切分。checkpoint 仍在 source/window 层提交，避免部分 segment 成功后误标记整份来源已完成。

`recovery` 会写入机器可读的 source/segment 执行账本，用于运行恢复和排障。`concurrency.max_concurrent_sources` 只作用于 dry-run/preflight ingest；写入型 ingest 在同一个 vault 内保持串行，以保护页面写入和 checkpoint。

## 运行限制

```yaml
models:
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
```

长文档编译、质量审查和多页面维护需要更长超时时间。建议根据模型供应商的实际速度调整。

语义模型重试是 `SemanticRunner` 的显式运行策略，不是下游节点的兜底清洗。它只重试可重试的供应商错误和结构化输出不符合契约的情况；页面写入仍然必须等完整 source 或已审核维护批次通过后才执行，因此重试不会绕过 ingest/lint 的写入边界。

`retryable_error_codes` 是公开的重试白名单，应保持收敛。外部服务错误、模型输出/语义契约错误、存储冲突适合重试；确定性的输入、配置和策略拒绝应先修复原因，而不是自动重试。

## 隐私脱敏

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

`redact_source_paths_in_pages` 会保留 checkpoint 使用的真实来源路径，但写入 Wiki 页面时使用脱敏后的来源标识，避免把本机用户名和绝对路径沉淀到知识库页面里。
