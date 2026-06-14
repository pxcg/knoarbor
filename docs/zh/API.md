# API 参考

KnoArbor 提供一组精简的本地 HTTP API，供前端、CLI 包装器、工作流工具和 AI 工具技能调用。API 使用 JSON over HTTP，可通过 Swagger、Apifox、Postman、curl、Python 或任意 OpenAPI 客户端访问。

启动服务：

```bash
uv run knoar serve
```

基础地址：

```text
http://127.0.0.1:8000
```

交互入口：

- 前端：`GET /`
- Swagger/OpenAPI：`GET /docs`
- OpenAPI JSON：`GET /openapi.json`

## 设计原则

公开 API 按产品能力组织，不按内部工作流拆分。不同场景通过请求参数选择。

| 范围 | 端点 | 用途 |
| --- | --- | --- |
| 服务状态 | `GET /health` | 轻量服务心跳 |
| 运行上下文 | `GET /runtime` | 发现当前本地 API 地址、配置路径、知识库路径和 endpoint 文件 |
| 知识库注册表 | `GET /vaults` | 列出已配置知识库的 ID、名称、路径和可用状态 |
| 诊断 | `GET /doctor` | 只读运行前检查 |
| 资料来源 | `GET /sources` | 读取资料来源连接器能力清单 |
| 模型供应商 | `GET /models/providers`, `POST /models/discover`, `POST /models/probe`, `POST /models/apply-capabilities` | 列出模型供应商、发现运行时模型信息、执行小型模型探测，并显式写回能力配置 |
| 知识编译 | `POST /ingest` | 编译配置来源、标准文档、单个文件或文件夹，或恢复失败编译 |
| 校验维护 | `POST /lint` | 执行确定性、结构、质量或完整维护 |
| 知识查询 | `POST /query` | 为宿主 AI 检索 Wiki 上下文 |
| 对话 | `POST /chat` | 通过受限 KnoArbor Wiki Chat Agent 询问选中的知识库 |
| 查询反馈 | `POST /query/feedback`, `GET /query/trends` | 记录和查看查询反馈 |
| 运行报告 | `GET /reports`, `GET /reports/content` | 列出和读取流程报告 |
| 运行监控 | `GET /runs`, `GET /runs/{run_id}` | 查看队列、运行中和已完成任务 |
| 运行事件 | `GET /runs/{run_id}/events`, `GET /runs/{run_id}/stream`, `POST /runs/{run_id}/cancel` | 观察或取消运行 |
| Wiki 页面 | `GET /wiki/pages`, `GET /wiki/pages/content`, `GET /wiki/pages/links` | 读取生成后的 Wiki 页面 |

`/ui/api/*` 仅供本地管理界面使用，不作为稳定集成 API。

## 执行模式

`/ingest` 和 `/lint` 支持：

- `execution: "queued"`：立即返回 `run_id`，进度通过 `/runs` 查看。
- `execution: "direct"`：阻塞直到流程结束，并把业务结果放在 `result` 字段中。

默认是 `queued`，因为知识编译和语义维护可能调用模型并耗时较长。`/query` 保持同步只读，适合作为宿主 AI 的即时检索入口。

两个接口始终返回统一的 workflow envelope：

```json
{
  "schema_version": "workflow_response.v1",
  "flow": "ingest",
  "execution": "queued",
  "status": "queued",
  "run_id": "20260525_123456_abcdef",
  "run": { "schema_version": "run_record.v1" },
  "result": null
}
```

`schema_version` 是工作流响应的兼容性标记。客户端只需要根据
`execution` 判断读取 `run_id`/`run` 还是 `result`；两种模式的顶层字段
保持一致。`/query` 不使用工作流 envelope，它直接返回
`schema_version: "wiki_query.v1"` 的检索结果。

## 对话

```http
POST /chat
```

运行受限的 KnoArbor Wiki Chat Agent。Chat 支持两种执行方式：`agentic`
让强模型决定调用哪个 KnoArbor 工具；`retrieval_first` 由 KnoArbor 先检索
Wiki，再让模型只基于 evidence pack 综合回答。`auto` 会对本地 Ollama/vLLM
供应商使用 `retrieval_first`，对其他供应商使用 `agentic`。Chat 可以搜索
已维护 Wiki 页面、读取页面、查看报告和运行记录、列出资料来源，也可以在
用户明确要求时排队启动知识编译或校验维护。它不会暴露任意 shell、浏览器、
文件系统或网络工具。

请求示例：

```json
{
  "schema_version": "chat_request.v1",
  "config_path": "/path/to/config.yaml",
  "vault_id": "personal",
  "messages": [
    {"role": "user", "content": "Agent Loop 是什么？"}
  ],
  "mode": "balanced",
  "execution_mode": "auto",
  "max_turns": 6,
  "include_trace": true
}
```

响应示例：

```json
{
  "schema_version": "chat_response.v1",
  "answer": "Agent Loop 是...",
  "citations": [
    {"kind": "page", "path": "concepts/Agent-Loop.md", "title": "Agent Loop"}
  ],
  "tool_trace": [
    {"tool": "search_wiki", "status": "ok", "summary": "Found 3 wiki result(s)."}
  ],
  "run_links": [],
  "memory_used": [],
  "memory_candidates": [],
  "memory_writes": [],
  "stats": {"execution_mode": "retrieval_first", "model_calls": 1, "tool_calls": 1, "memory_used": 0, "memory_writes": 0, "total_tokens": 1200},
  "warnings": []
}
```

当需要 KnoArbor 在控制台内综合回答时使用 `/chat`；当另一个宿主 AI
需要拿到证据并自行生成最终回答时使用 `/query`。

## 知识库选择

知识库是 KnoArbor 的一等知识空间。公开集成应优先使用
`config_path + vault_id`，因为 ID 在本地路径变化时更稳定；`vault_path`
主要用于一次性自动化或临时知识库。

选择知识库前可以先读取注册表：

```http
GET /vaults?config_path=/path/to/config.yaml
```

响应会返回默认知识库，以及每个 profile 的 `id`、显示名称、解析后的路径、
是否为当前默认知识库和路径是否可用。`POST /query` 还支持跨知识库检索：
传入 `all_vaults: true` 或 `vault_id: "all"` 查询全部已配置真实知识库，
也可以传入 `vault_ids: [...]` 查询指定知识库。返回结果会标注 `vault_id`、
`vault_name` 和 `vault_path`。`all` 是保留的虚拟范围，不是可写入的真实知识库。

```http
POST /query
GET /wiki/pages?vault_id=personal
GET /reports?vault_id=personal
GET /runs?vault_id=personal
```

如果需要从非默认配置文件解析 `vault_id`，同时传入 `config_path`。

## 错误格式

公开 API 错误统一使用 KnoArbor 错误目录。稳定判断字段是 `error.code`，粗分类字段是 `error.category`。

```json
{
  "error": {
    "code": "KA-INPUT-001",
    "category": "user_input_error",
    "message": "Request validation failed.",
    "retryable": false
  },
  "detail": "Request validation failed."
}
```

完整错误码见 [错误码](ERROR_CODES.md)。

## 服务状态

```http
GET /health
```

返回服务是否可用。触发长任务前可先调用该接口。

## 运行上下文

```http
GET /runtime
```

返回宿主 AI、脚本和 HTTP-only 集成需要的当前本地运行上下文：

```json
{
  "schema_version": "runtime_context.v1",
  "service_online": true,
  "base_url": "http://127.0.0.1:8000",
  "config_path": "/path/to/config.yaml",
  "vault_path": "/path/to/vault",
  "vault_id": "personal",
  "vault_name": "我的知识库",
  "vaults": [
    {
      "id": "personal",
      "name": "我的知识库",
      "path": "/path/to/vault"
    }
  ],
  "endpoint_path": "/path/to/.knoarbor/endpoint.json",
  "user_endpoint_path": "~/.knoarbor/endpoint.json",
  "errors": []
}
```

集成工具需要发现当前知识库路径时，应使用该接口，而不是调用
`/ui/api/*`。如果服务启动时自动切换端口，`knoar serve` 也会把实际
运行地址写入用户级 `.knoarbor/endpoint.json`，并同步写入
`config.yaml` 同级的项目级 `.knoarbor/endpoint.json`。

## 知识库注册表

```http
GET /vaults
GET /vaults?config_path=/path/to/config.yaml
```

返回已配置的知识库 profile：

```json
{
  "schema_version": "vaults.v1",
  "config_path": "/path/to/config.yaml",
  "default_vault_id": "personal",
  "vaults": [
    {
      "id": "personal",
      "name": "个人知识库",
      "path": "/path/to/vault",
      "active": true,
      "exists": true
    }
  ]
}
```

当集成工具需要先确定可用知识库，或把用户提到的知识库名称转换为稳定
`vault_id` 时使用该接口。`path` 仍然返回给本地检查和一次性自动化使用，
但公开客户端在条件允许时应优先使用 `vault_id`。

## 运行报告

```http
GET /reports?vault_path=/path/to/vault
GET /reports/content?vault_path=/path/to/vault&path=maintenance/ingest_report_YYYYMMDD_HHMMSS.md
```

列出或读取知识库 `maintenance/` 目录下的 Markdown 流程报告。报告属于公开集成 API，
因为宿主 AI 经常需要解释一次运行写入了哪些页面、为什么失败、修改了什么。
`GET /reports` 也支持配合 `config_path` 传入 `all_vaults=true` 或重复的
`vault_ids`。返回的每条报告会包含 `vault_id`、`vault_name` 和 `vault_path`。
读取单个报告仍然需要明确一个知识库。

## 运行诊断

```http
GET /doctor
GET /doctor?config_path=/path/to/config.yaml&connector=markdown
GET /doctor?check_model_runtime=false&check_connector_runtime=false
```

执行只读诊断，包括配置加载、知识库目录、模型环境、资料来源发现、可选文档预处理器和最近运行状态。该接口不会写入 Wiki 页面。运行时检查由查询参数控制：

- `check_model_runtime`：为 `true` 时测试已配置模型端点和结构化输出能力。
- `check_connector_runtime`：为 `true` 时运行资料来源发现，并返回发现的资料数量。

页面加载类检查建议传 `false`，显式就绪测试再传 `true`。

## 资料来源

```http
GET /sources
GET /sources?config_path=/path/to/config.yaml&connector=markdown
```

返回资料来源连接器能力清单，但不会扫描本地文件。外部工具可以用它了解
KnoArbor 支持哪些来源、每个连接器会产生哪些 `source_type`，以及是否支持断点和分段提示。

每个连接器也会返回轻量 `settings_schema`，描述支持的配置字段，例如
`roots`、`sessions_dir`、`session_files`、`pattern` 和 `recursive`。

传入 `config_path` 时，每个连接器会额外标注：

- `configured`：该连接器是否出现在配置文件中。
- `enabled`：该连接器是否在配置文件中启用。

实际文件发现仍由 `GET /doctor` 的运行时检查和 `knoar sources` 预检命令负责。

## 模型供应商

```http
GET /models/providers
POST /models/discover
POST /models/probe
POST /models/apply-capabilities
```

模型接口用于在长流程运行前检查供应商配置和模型能力，可由 Swagger、Apifox、脚本或本地前端调用。

`GET /models/providers` 只读取当前模型配置，不访问模型运行时。返回内容会隐藏 API Key，只标注环境变量是否已配置。

`POST /models/discover` 调用供应商的模型列表接口，例如 OpenAI 兼容的 `/models`。对于 Ollama 风格端点，KnoArbor 还会尝试 `/api/show` 探测上下文长度。该接口不触发模型生成，因此不消耗生成 token。

```json
{
  "config_path": "/path/to/config.yaml",
  "provider": "vllm"
}
```

`POST /models/probe` 会发起一个很小的生成请求。`level: "minimal"` 用于验证 Chat Completions 连通性；`level: "structured"` 用于验证模型是否能满足 KnoArbor agent 需要的结构化 JSON 契约。

```json
{
  "config_path": "/path/to/config.yaml",
  "provider": "deepseek",
  "level": "structured"
}
```

`POST /models/apply-capabilities` 是唯一会写配置的模型接口。它显式保存 `context_window`、`max_output_tokens` 和 `json_mode` 等字段；发现和探测接口只返回建议值，不自动修改 `config.yaml`。

```json
{
  "config_path": "/path/to/config.yaml",
  "provider": "vllm",
  "context_window": 32768,
  "max_output_tokens": 8000,
  "json_mode": false
}
```

## 知识编译

```http
POST /ingest
```

通过 `kind` 选择输入形态：

- `connectors`：运行已配置的资料来源连接器。
- `file`：编译一个本地输入文件。
- `folder`：一次性编译一个本地文件夹，不修改持久配置。
- `document`：编译一个已经标准化的 `source_document`。
- `recovery`：重试上一次知识编译中失败的项目。

知识编译是写入流程，每次请求只作用于一个知识库。可以直接传
`vault_path`，也可以传 `config_path` 加 `vault_id` 来选择已配置知识库。
它不支持 `all_vaults=true`；如果需要编译多个知识库，应分别启动多个运行。

配置来源：

```json
{
  "execution": "queued",
  "kind": "connectors",
  "config_path": "./config.yaml",
  "vault_id": "personal",
  "connector_names": ["markdown"],
  "write": true
}
```

单个本地文件：

```json
{
  "execution": "queued",
  "kind": "file",
  "config_path": "./config.yaml",
  "vault_id": "personal",
  "input_path": "/path/to/file.pdf",
  "write": true
}
```

本地文件夹：

```json
{
  "execution": "queued",
  "kind": "folder",
  "config_path": "./config.yaml",
  "vault_id": "personal",
  "input_path": "/path/to/folder",
  "recursive": true,
  "write": true
}
```

文件夹编译会直接发现 Markdown 文件。文件夹中的非 Markdown 文件需要已配置的 MinerU-compatible
预处理器；如果未启用预处理或处理失败，流程会明确失败，而不会静默跳过。

标准化资料对象：

```json
{
  "execution": "queued",
  "kind": "document",
  "config_path": "./config.yaml",
  "vault_id": "personal",
  "source_document": { "schema_version": "source_document.v1" },
  "write": true
}
```

恢复失败的知识编译：

```json
{
  "execution": "queued",
  "kind": "recovery",
  "config_path": "./config.yaml",
  "vault_id": "personal",
  "recovery_of_run_id": "20260525_123456_abcdef",
  "write": true
}
```

`kind: "recovery"` 只支持 `execution: "queued"`，因为它依赖既有运行记录，且可能重放多个失败项目。

Markdown 文件会直接处理。PDF/DOCX/PPTX 等富文档需要配置 MinerU 等文档预处理器。
接口响应始终使用[执行模式](#执行模式)中的统一 workflow envelope。

## 校验维护

```http
POST /lint
```

执行确定性校验，并可按 `mode` 启用结构或质量维护：

- `deterministic`
- `semantic_structural`
- `semantic_quality`
- `semantic_full`

校验维护同样是可能写入页面的流程，每次请求只作用于一个知识库。
可以直接传 `vault_path`，也可以传 `config_path` 加 `vault_id` 选择已配置知识库。
跨知识库汇总请使用 `/reports` 和 `/runs`；真正的维护运行应按知识库分别启动。

示例：

```json
{
  "execution": "queued",
  "config_path": "./config.yaml",
  "vault_id": "personal",
  "mode": "semantic_structural",
  "scope": {
    "scope_id": "manual:api",
    "trigger": "manual",
    "source": { "kind": "api" },
    "changed_pages": [],
    "recommended_lint_modes": ["semantic_structural"],
    "reason": "Manual maintenance run."
  }
}
```

## 知识查询

```http
POST /query
```

检索相关 Wiki 页面、摘录、关联上下文、trace 数据和可直接交给宿主 AI
使用的 context pack。KnoArbor 在 `/query` 中不生成最终聊天回答，宿主 AI
决定如何使用返回的证据。

Query 采用页面优先的检索语义，而不是 chunk 优先语义。返回页面仍然按相关性
放在 `results` 中，每个结果会带有 `role`：

- `primary`：最直接回答问题的已维护 Wiki 页面。
- `supporting`：补充实现细节、限制、对比或延伸阅读的相关页面。
- `source`：用于溯源的来源摘要页面。

响应会同时把这些结果分组为 `primary_pages`、`supporting_pages` 和
`source_pages`。调用方可以自由引用任意返回页面；普通回答通常应优先基于
primary 页面的结构化内容，再按需要使用 supporting/source 页面。

返回的 context pack 是页面优先，而不是 chunk 优先：它会保留 primary
页面的正文作为主要答案单元，同时把 supporting/source 页面作为结构化摘要、
Key Points、摘录和来源线索返回。调用方需要读取某个辅助页面全文时，使用
`/wiki/pages/content`。

响应还会包含：

- `answer_scope`：标记查询是窄问题、广泛问题还是探索问题，并记录本次检索
  使用的知识库和目录范围。
- `answer_set`：按路径组织的推荐答案集合。窄问题通常以一个主页面为核心；
  广泛问题可以包含多个补充页面，因为 Wiki 页面本身就是已维护的知识单元。
- `evidence_coverage`：用 strong、adequate 或 weak 表示本地页面对问题的
  覆盖程度。

```json
{
  "vault_path": "/path/to/vault",
  "query": "agent loop",
  "mode": "balanced"
}
```

查询全部已配置知识库：

```json
{
  "config_path": "/path/to/config.yaml",
  "query": "agent loop",
  "all_vaults": true,
  "mode": "balanced"
}
```

查询指定知识库：

```json
{
  "config_path": "/path/to/config.yaml",
  "query": "agent loop",
  "vault_ids": ["personal", "team"],
  "mode": "balanced"
}
```

## 运行监控

```http
GET /runs?vault_path=/path/to/vault&active_only=false&limit=50
GET /runs/{run_id}?vault_path=/path/to/vault
GET /runs/{run_id}/events?vault_path=/path/to/vault&after=0&limit=200
GET /runs/{run_id}/stream?after=0
POST /runs/{run_id}/cancel
```

`GET /runs` 也支持配合 `config_path` 传入 `all_vaults=true` 或重复的
`vault_ids`。返回的每条运行记录会包含 `vault_id`、`vault_name` 和
`vault_path`。读取单个运行、事件、流式事件和取消运行仍然需要明确一个知识库，
因为 run_id 是知识库局部标识。

`/stream` 使用 Server-Sent Events。取消是协作式的，正在进行的模型请求可能会在下一个检查点前先完成。

## 模型用量遥测

当所选模型供应商返回用量信息时，流程报告和运行指标会包含以下字段：

- `semantic_calls`
- `total_tokens`
- `tokens_per_second`
- `prompt_cached_tokens`
- `prompt_cache_hit_tokens`
- `prompt_cache_miss_tokens`

提示词缓存由模型供应商实现。KnoArbor 会保持长语义契约提示词稳定，并且只在模型 API 返回缓存字段时记录缓存遥测。

知识编译、校验维护和对话中的模型调用也会写入
`maintenance/token_ledger.jsonl`，分别标记为 `flow=ingest`、`flow=lint`
或 `flow=chat`。Token 分析页面会读取这份账本，按流程、智能体、来源、页面、供应商和模型分析用量。

## Wiki 页面

```http
GET /wiki/pages?vault_path=/path/to/vault
GET /wiki/pages/content?vault_path=/path/to/vault&path=concepts/Agent-Loop.md
GET /wiki/pages/links?vault_path=/path/to/vault&path=concepts/Agent-Loop.md
```

`/wiki/pages` 返回页面摘要和链接元数据。`/wiki/pages/content` 返回单个
Markdown 页面及其元数据。`/wiki/pages/links` 返回指向目标页面的页面。
页面路径是相对于 Wiki 内容根目录的路径，例如 API 使用
`concepts/Agent-Loop.md`。在文件系统中，新版工作区会把同一页面存放在
`vaults/all/pages/concepts/Agent-Loop.md`。

这些接口也支持同时传入 `config_path` 和 `vault_id`。当用户选择跨知识库
`/query` 返回的某个结果时，应使用该结果的 `vault_id` 读取页面正文或链接，
确保后续查看仍然落在同一个知识库。

## 移除的原型端点

原型期的连接器、草稿写入、扫描、操作执行、拆分工作流端点和通用 run-start 端点都不再公开。请使用 `POST /ingest`、`POST /lint`、`POST /query` 以及上述运行监控端点。
