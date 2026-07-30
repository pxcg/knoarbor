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
| 模型供应商 | `GET /models/providers`, `GET /models/image-providers`, `POST /models/discover`, `POST /models/apply-capabilities` | 列出文本和图片模型供应商、检查运行时模型信息，并显式写回选定配置 |
| 知识编译 | `POST /ingest` | 编译配置来源、标准文档、单个文件或文件夹，或恢复失败编译 |
| 校验维护 | `POST /lint` | 执行确定性、结构、质量或完整维护 |
| 知识查询 | `POST /query` | 为宿主 AI 检索 claim-backed active raw evidence 与 trace |
| 对话 | `POST /chat`, `POST /chat/stream`, `GET /chat/sessions`, `GET/PATCH/DELETE /chat/sessions/{session_id}`, `POST /chat/sessions/{session_id}/ingest`, `POST /chat/sessions/{session_id}/close`, `POST /chat/sessions/{session_id}/retry` | 询问选中的知识库、流式回答、管理会话、将会话入库、关闭会话并重试失败回答 |
| 查询反馈 | `POST /query/feedback`, `GET /query/trends` | 记录和查看查询反馈 |
| 运行报告 | `GET /reports`, `GET /reports/content` | 列出和读取流程报告 |
| 运行监控 | `GET /runs`, `GET /runs/{run_id}` | 查看队列、运行中和已完成任务 |
| 运行事件 | `GET /runs/{run_id}/events`, `GET /runs/{run_id}/stream`, `POST /runs/{run_id}/cancel` | 观察或取消运行 |
| Wiki 页面 | `GET /wiki/pages`, `GET /wiki/pages/content`, `GET /wiki/pages/relations` | 读取生成后的 Wiki 页面 |

桌面本地 renderer 端点仅供打包后的桌面应用使用，不作为稳定集成 API。

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
`schema_version: "wiki_query.v4"` 的检索结果。

## 对话

```http
POST /chat
```

通过 KnoArbor Wiki Chat Agent 询问选中的知识库。Chat 先执行统一的 active Raw
检索；存在候选时只基于已验证 Raw 证据回答。只有检索得到可信
`no_match` 且随包质量门禁已通过时，才进入物理隔离的
模型通用知识回答路径。每个完成的轮次都会持久化最终来源证明。

请求示例：

```json
{
  "schema_version": "chat_request.v4",
  "request_id": "req_01",
  "execution_id": "exec_01",
  "config_path": "/path/to/config.yaml",
  "vault_id": "personal",
  "message": {"message_id": "msg_01", "role": "user", "content": "Agent Loop 是什么？"},
  "include_trace": true
}
```

响应示例：

```json
{
  "schema_version": "chat_response.v4",
  "request_id": "req_01",
  "execution_id": "exec_01",
  "session_id": "chat_01",
  "session_revision": 1,
  "turn_id": "turn_01",
  "answer": "Agent Loop 是...",
  "answer_provenance": {
    "mode": "knowledge_grounded",
    "query_outcome": "candidates",
    "chat_outcome": "sufficient"
  },
  "citations": [
    {"kind": "raw_evidence", "evidence_id": "evh:01", "raw_revision_id": "rawrev:01", "source_unit_id": "unit:01"}
  ],
  "tool_trace": [
    {"tool": "retrieve_knowledge_batch", "status": "ok", "summary": "已返回 active Raw 证据。"}
  ],
  "run_links": [],
  "memory_used": [],
  "memory_candidates": [],
  "memory_writes": [],
  "stats": {"retrieval_strategy": "fast_unified_recall", "model_calls": 1, "tool_calls": 2},
  "warnings": []
}
```

当需要 KnoArbor 在控制台内综合回答时使用 `/chat`。系统可先调用一次带会话
上下文的知识树导航模型，选择目录中已有的来源或章节节点，再将不变的原始问题
与代码编译的树作用域放入同一个 Query 批次；编号章节直接提供 Active Raw
子树候选，不再执行第二次标题检索，也不会拼接或改写用户问题。当另一个宿主 AI 需要拿到证据
并自行生成最终回答时使用 `/query`。写入和维护工作流应直接调用 `/ingest`
与 `/lint`。

继续已有会话时，请同时提交持久化的 `session_id` 与最新
`expected_session_revision`。过期 revision 会返回存储冲突；重复
`request_id` 会返回已持久化轮次，不会追加重复记录。

候选与 typed `no_match` 都进入同一个统一 Final Answer 模型。该模型接收原始
用户问题、纯对话历史、检索结果与当前 Raw 证据，并为整轮选择 Raw 依据、通用知识
或知识缺口。代码校验支撑并派生 provenance，不再使用 no-match 门禁或本地材料
关键词路由。普通完成的知识问答最多包含 Retrieval Planner 与 Final Answer 两个
语义阶段，不计配置内重试和可选生图调用。

如果前端或集成工具需要在检索和生成过程中展示进度，可以使用流式入口：

```http
POST /chat/stream
```

`/chat/stream` 接收与 `/chat` 相同的请求体，返回 `text/event-stream`。
它在同一条 Chat 主线运行期间持续输出进度事件，并在最后输出一个 `final`
事件；该事件的 `response` 字段与 `POST /chat` 返回的 `chat_response.v4`
完全一致。

事件类型：

- `stage`：Chat 进入语义改写、检索或回答生成阶段。
- `tool`：受限 KnoArbor 工具开始或完成调用。
- `source`：生成前由代码选择的临时回答来源路径。
- `answer_delta`：模型适配器返回的最终回答增量文本。
- `final`：最终回答、引用、trace、token 指标和持久化会话信息。
- `error`：共享 KnoArbor 错误 envelope。

引用预览通过 `POST /chat/citations/resolve` 按需解析，不在 Chat 会话中保存 Raw
摘录。请求携带知识库选择器和仅含定位符的引用；一个 Raw 引用可包含多个精确
`spans`，响应按请求顺序返回对应的临时 `texts` 和首个 `text`。解析器只读取指定的
不可变 source unit，不重新 ingest，也不调用模型。来源缺失时返回
`status: "unavailable"`，客户端打开 Raw 但不进行猜测高亮。

Chat 会话默认保存在已维护 Wiki 页面之外。当某次对话需要沉淀为持久 Wiki
知识时，调用会话入库入口：

`GET /chat/sessions` 支持 `limit`（每页最多 200 条）和 `offset`。响应包含
`total_count`、规范化后的 `offset`/`limit` 与 `has_more`，客户端可继续读取旧会话
摘要，而不会加载完整会话正文。

如果需要重命名已保存的 Chat 会话：

```http
PATCH /chat/sessions/{session_id}
```

```json
{
  "config_path": "/path/to/config.yaml",
  "vault_id": "personal",
  "expected_session_revision": 8,
  "title": "Agent Loop 架构讨论"
}
```

如果需要重新生成当前会话的最后一条 assistant 回答：

```http
POST /chat/sessions/{session_id}/retry
```

该入口使用不含目标回答的会话快照重新执行，并在单次 session revision 提交中
原子替换目标轮次。失败、取消或崩溃都不会改动上一版回答。

请求体必须携带稳定的 `target_turn_id` 与 `expected_session_revision`。删除轮次使用
`DELETE /chat/sessions/{session_id}/turns/{turn_id}`，删除轮次、删除整个会话、
重命名和会话入库都使用相同的 revision compare-and-swap 约束；会话入库可通过
`turn_ids` 选择稳定轮次，不再使用数组下标。

```http
POST /chat/sessions/{session_id}/ingest
```

该入口会把已保存会话转换为 `knoarbor_chat` `SourceDocument`，然后排队进入
标准 `/ingest` document 流程，包括分段、页面评审、写入/报告生成，以及在
ingest 配置启用时执行局部 lint。响应结构与其他长任务 ingest 请求一致，都是
queued workflow envelope。

```json
{
  "config_path": "/path/to/config.yaml",
  "vault_id": "personal",
  "expected_session_revision": 8,
  "write": true,
  "write_report": true,
  "append_ledger": true
}
```

如果需要结束会话并按配置策略决定是否自动入库：

```http
POST /chat/sessions/{session_id}/close
```

关闭入口会在 session 上记录可沉淀候选摘要。除非显式启用
`chat.auto_ingest.enabled` 且满足配置策略，否则关闭会话不会写入 Wiki 页面。
手动 `/ingest` 某个 chat session 始终可用。

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
  "endpoint_path": "/path/to/state/endpoint.json",
  "errors": []
}
```

集成工具需要发现当前知识库路径时，应使用该接口，而不是调用桌面本地
renderer 端点。如果服务启动时自动切换端口，`knoar serve` 会原子更新
活动 `config.yaml` 同级唯一的 `state/endpoint.json` 权威文件。

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
GET /reports/content?vault_path=/path/to/vault&path=maintenance/reports/ingest/ingest_report_YYYYMMDD_HHMMSS.md
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
GET /models/image-providers
POST /models/image-probe
POST /models/discover
POST /models/apply-capabilities
```

模型接口用于在长流程运行前检查供应商配置和模型列表，可由 Swagger、Apifox、脚本或本地前端调用。

`GET /models/providers` 只读取当前模型配置，不访问模型运行时。返回内容会隐藏 API Key，只标注已配置的密钥是否可用。

`GET /models/image-providers` 读取图片生成供应商配置。图片生成供应商和聊天/编译模型供应商分离，供 chat 的 `generate_image` 工具使用。

`POST /models/image-probe` 会在用户明确操作时执行一次真实生图，只返回受限的状态信息。该操作会耗费正常生图时间并可能产生供应商用量，不返回生成图片内容或原始响应。

`POST /models/discover` 调用适配器对应的模型列表接口。OpenAI 兼容供应商使用 `/models`；Ollama 原生供应商使用 `/api/tags` 和 `/api/show` 探测模型可用性与上下文长度。该接口不发送对话生成请求，因此不消耗生成 token。供应商返回模型 ID 时，响应会包含 `model_ids`，前端可以让用户继续保留手动填写的模型，也可以从发现到的模型中选择一个。

```json
{
  "config_path": "/path/to/config.yaml",
  "provider": "vllm"
}
```

`POST /models/apply-capabilities` 是唯一会写配置的模型接口。它显式保存用户选定的 `context_window`、`max_output_tokens` 和 `json_mode` 等字段；发现接口不会自动修改 `config.yaml`。

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
- `excerpt`：编译用户选中的短文本，例如一句金句、一个 insight，或一组被选中的聊天消息。
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

可编辑摘录（手动输入或从 Chat 选中的内容）：

```json
{
  "execution": "queued",
  "kind": "excerpt",
  "config_path": "./config.yaml",
  "vault_id": "personal",
  "excerpt_title": "知识通过关系生长",
  "excerpt_text": "知识不是记忆的堆积，而是关系的生长。",
  "excerpt_context": {
    "source_app": "knoarbor_chat",
    "session_id": "chat_123",
    "message_ids": ["assistant:4"]
  },
  "write": true
}
```

摘录导入既支持用户手动输入，也支持从 Chat 选择内容后继续编辑。UI 在提交前收集
标题和目标知识库，API 统一使用 `kind=excerpt` 契约。摘录仍复用标准 document
ingest 路径：来源标准化、atom 抽取与确定性校验、事实 revision 发布、
projection/index materialization 和报告生成。

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

若只需从已提交事实重建确定性的来源投影和机器索引，而不重新运行语义抽取：

```http
POST /ingest/materialization/rebuild
```

请求通过 query 参数选择一个知识库，并提交空 JSON body。响应会返回完成协调后的
materialization epoch 以及当前 fact/index generation。

## 校验维护

```http
POST /lint
```

对单个知识库执行自动完整性治理。`mode` 控制是否在同一确定性扫描与自动修复上增加只读语义诊断：

- `deterministic`
- `semantic`

Lint 不直接 patch raw、canonical facts、provenance 或生成页正文。通过审查
的发现由所属 ingest 或 materialization 流程自动执行，随后复扫知识库。
修复计划统一使用 `reingest_request`、`index_rebuild_request`、
`projection_rebuild_request` 或 `report_only`。
可以直接传 `vault_path`，也可以传 `config_path` 加 `vault_id` 选择知识库。

示例：

```json
{
  "execution": "queued",
  "config_path": "./config.yaml",
  "vault_id": "personal",
  "mode": "semantic",
  "scope": {
    "scope_id": "manual:api",
    "trigger": "manual",
    "source": { "kind": "api" },
    "changed_pages": [],
    "recommended_lint_modes": ["semantic"],
    "reason": "Manual maintenance run."
  }
}
```

## 知识查询

```http
POST /query
```

检索 claim-backed active raw evidence、定位元数据、缺口、trace 数据和可直接交给
宿主 AI 使用的 context pack。KnoArbor 在 `/query` 中不生成最终聊天回答。

`wiki_query.v4` 在不可变 active retrieval snapshot 上同时执行 atom/claim 与直接
Raw 检索；代码判定为关系意图时，还会确定性枚举最多两条边的跨来源关系路径。
这些信号融合成带 vault 身份的 `evidence_handles`，并保留为完整的轻量候选集。
Query 确定性准入本轮回答证据，只通过 active resolver 将已准入 handle 读取为完整
`raw_evidence`；未准入的低排名 handle 仍可达，但不会加载其 Raw 正文。ranked
`results` 仅用于可选导航；通道状态、
typed outcome、缺口、警告与 trace 独立保留。Wiki 页面正文和 atom summary
不提供事实材料。


```json
{
  "vault_path": "/path/to/vault",
  "query": "agent loop"
}
```

查询全部已配置知识库：

```json
{
  "config_path": "/path/to/config.yaml",
  "query": "agent loop",
  "all_vaults": true
}
```

查询指定知识库：

```json
{
  "config_path": "/path/to/config.yaml",
  "query": "agent loop",
  "vault_ids": ["personal", "team"]
}
```

只有查询计划要求的全部通道都完成后，响应中的 `exhausted` 才为 `true`（普通查询
为两个 lexical 通道）。如果先触发
资源安全边界，状态为 `resource_exhausted`，已完成的 handles 仍保留在响应中，
`continuation_cursor` 则保存与查询、知识库和 snapshot generation 绑定的不透明
续查位置。单知识库续查时原样传回该游标：

```json
{
  "vault_path": "/path/to/vault",
  "query": "agent loop",
  "continuation_cursor": "retrieval_cursor.v1..."
}
```

多知识库查询使用以 vault ID 为键的 `continuation_cursors`。查询、知识库或
active snapshot generation 发生变化时，旧游标会被拒绝。该游标只用于资源安全
续查，不是 top-k 或相关性截断。

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
`.knoarbor/ledgers/token.jsonl`，分别标记为 `flow=ingest`、`flow=lint`
或 `flow=chat`。Token 分析页面会读取这份账本，按流程、智能体、来源、页面、供应商和模型分析用量。

## Wiki 页面

```http
GET /wiki/pages?vault_path=/path/to/vault
GET /wiki/pages/content?vault_path=/path/to/vault&path=Agent-Loop.md
GET /wiki/pages/relations?vault_path=/path/to/vault&path=Agent-Loop.md
PATCH /wiki/pages/content
DELETE /wiki/pages/content
PATCH /wiki/pages/raw
```

`/wiki/pages` 返回页面摘要和链接元数据。`/wiki/pages/content` 返回单个
Markdown 页面及其元数据。`/wiki/pages/relations` 返回所选页面的入站和出站页面关系。
页面路径是相对于 Wiki 内容根目录的路径。当前知识与 source projection 使用
`Agent-Loop.md` 这样的 flat path；旧 vault 可能仍保留历史 `sources/...` 路径。

这些接口也支持同时传入 `config_path` 和 `vault_id`。当用户选择跨知识库
`/query` 返回的某个结果时，应使用该结果的 `vault_id` 读取页面正文或链接，
确保后续查看仍然落在同一个知识库。

对于可编辑的 `source_index` 页面，`GET /wiki/pages/content` 会返回可选的
`editable_projection` 结构。`PATCH /wiki/pages/content` 只接收其中的结构化可编辑
字段和 `base_revision_id`，不接收生成后的 Markdown 或 evidence 内容。保存会提交新的
canonical revision，并重新生成投影与索引。可编辑范围为 synthesis、现有 claim
文本、entities 和 relations；claim identity 与 evidence mapping 仍由 ingest 管理。
若 `base_revision_id` 已过期，保存会被拒绝，不覆盖较新的 ingest。后续 raw ingest
会生成新的投影，不自动携带旧 Raw revision 上的用户编辑字段。

`DELETE /wiki/pages/content` 在 JSON body 中接收同样的单知识库选择器和相对
页面路径。删除操作经过页面 service，以保持 canonical source facts 与确定性
materialization 协调一致。

`GET /wiki/pages/content` 还会为可编辑的来源投影返回 `editable_raw`。
`PATCH /wiki/pages/raw` 接收 `raw_revision_edit.v1`，其中包含打开编辑器时的
`base_revision_id` 与修订后的标准化 Raw 文本。该操作不运行语义 ingest extractor，
而是把修订后的 SourceDocument 提交给标准 queued ingest coordinator，并设置
`force_reprocess=true`。响应为 `workflow_response.v1`，客户端使用返回的 `run_id`
进入统一运行监控。该 ingest 会调用已配置模型，重新生成 synthesis、claims、entities、
relations、evidence、投影和索引。发布时再次校验 parent revision，避免过期编辑覆盖
较新的 active head。

## 移除的原型端点

原型期的连接器、草稿写入、扫描、操作执行、拆分工作流端点和通用 run-start 端点都不再公开。请使用 `POST /ingest`、`POST /lint`、`POST /query` 以及上述运行监控端点。

## Query 遥测

Query 响应的 `stats` 提供检索策略、候选数、raw evidence 数量和耗时等确定性
遥测。遥测用于诊断，不改变 answer set 或事实证据策略。

## 并发模型

读取请求可以并行。Ingest provider/segment 请求使用配置的有界并发；事实发布
和 materialization 修改仍经过 SQLite fencing 与 vault write lock。API route
不维护第二套队列或并发策略。

## Desktop-Local Endpoints

打包桌面 renderer 使用 `UI_PUBLIC_ROUTES` 管理的配置、图谱摘要、token
摘要和 vault 资产等内部适配器，并通过 preload IPC 访问文件选择等桌面能力。
这些具体适配器不属于稳定公共 API。兼容范围见
[API 兼容性](API_COMPATIBILITY.md)。

## Architecture Boundary

Route 负责 HTTP 解析与 response envelope；service/coordinator 负责 use case；
runtime/storage 负责持久状态和发布。Route 不直接实现恢复、事实提交或
materialization policy。
