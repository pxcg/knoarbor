# API 说明

KnoArbor 暴露一组小而明确的 public alpha HTTP API，供本地管理界面、CLI 辅助命令、外部工作流工具和 AI 工具技能调用。API 是普通 JSON over HTTP，可以直接通过 Apifox、Postman、curl、Python 或任何 OpenAPI 客户端调用。

启动服务：

```bash
uv run knoar serve
```

基础地址：

```text
http://127.0.0.1:8000
```

交互入口：

- 管理界面：`GET /`
- Swagger/OpenAPI：`GET /docs`
- OpenAPI JSON：`GET /openapi.json`

## 兼容策略

本文档中的接口是 v0.x public alpha API。v0.x 期间，主流程路径和核心语义应保持稳定；在后续稳定版之前，响应 schema 仍可能增加可选字段。

- 路径、HTTP 方法、必填请求字段和核心响应字段语义在 v0.x alpha 阶段视为稳定。
- 小版本可以增加可选字段。
- 如果公开接口被废弃，会至少保留一个小版本。
- `/ui/api/*` 只服务本地管理界面，不作为稳定集成 API。
- 机器可读的兼容接口清单位于 `src/knoarbor/entrypoints/api_contract.py`；API surface 测试会直接读取这份契约。

v0.x 稳定公开接口范围：

| 领域 | 接口族 | 稳定性 |
| --- | --- | --- |
| 服务状态 | `GET /health`, `GET /doctor` | 稳定公开诊断接口 |
| 同步工作流 | `POST /ingest/*`, `POST /lint/run`, `POST /query/search` | 稳定公开流程接口 |
| 运行队列 | `POST /runs/*`, `GET /runs*`, `POST /runs/{run_id}/cancel`, `POST /runs/{run_id}/rerun-failed` | 稳定公开长任务接口 |
| 查询反馈 | `POST /query/feedback`, `GET /query/trends` | 稳定公开遥测接口 |
| Wiki 页面 | `GET /wiki/pages`, `GET /wiki/page`, `GET /wiki/backlinks` | 稳定公开页面读取接口 |
| 管理界面 | `GET /`, `GET /ui`, `/ui/api/*` | UI 入口公开；`/ui/api/*` 为内部接口 |

## 错误契约

公开 API 错误使用 KnoArbor 统一错误码目录。稳定查询键是 `error.code`；`error.category` 是供程序粗粒度处理的大类。

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

完整目录见 [错误码](ERROR_CODES.md)。

未预期的服务端异常也会转换为同一错误信封，并使用
`KA-INTERNAL-001`；公开 API 客户端不需要解析 Python traceback。

## 服务状态

```http
GET /health
```

返回服务是否可用。外部客户端在触发长任务前可以先调用该接口。

## 本地诊断

```http
GET /doctor
GET /doctor?config_path=/path/to/config.yaml&connector=markdown
```

只读检查配置加载、Wiki 目录结构、模型环境变量、来源连接器 discovery、可选文档预处理器和最近运行状态。该接口不会调用模型，也不会写入 Wiki 页面。

## 同步工作流接口

当调用方可以等待流程完成时，使用同步接口。

### 编译已配置来源

```http
POST /ingest/run
```

运行 `config.yaml` 中启用的输入来源，完成来源标准化、检查点判断、分段、Wiki 页面编译、报告写入和台账更新。

### 编译单个标准文档

```http
POST /ingest/document
```

处理单个 `source_document.v1`。适合外部适配器已经完成来源标准化的场景。

### 编译单个文件路径

```http
POST /ingest/file
```

处理一个本地文件路径。Markdown 文件直接进入编译；PDF、DOCX、PPTX 等富文档需要先配置 MinerU 等文档预处理器。

### 校验维护

```http
POST /lint/run
```

根据请求模式运行确定性校验，以及可选的语义结构维护或质量维护。

### 查询 Wiki 上下文

```http
POST /query/search
```

检索相关 Wiki 页面、摘录、关联上下文、trace 信息和可直接注入提示词的 context pack。KnoArbor 不负责生成最终聊天回答，宿主 AI 自行判断如何使用返回的证据。

请求体设置 `write_report: true` 时，会写入查询审计报告，并在响应的 `stats.query_report_path` 中返回路径，例如 `maintenance/query_report_20260527_120000_000000.md`。

响应包含显式契约版本：

```json
{
  "schema_version": "wiki_query.v1",
  "query": "agent loop",
  "retrieval_mode": "machine_hybrid_balanced",
  "results": [],
  "context_pack": "...",
  "trace": {
    "schema_version": "query_trace.v1",
    "initial_scope_dirs": ["concepts"],
    "expanded_scope_dirs": ["concepts", "entities", "sources"],
    "origin_counts": { "direct": 1, "related": 2 },
    "returned_paths": ["concepts/Agent-Loop.md"]
  }
}
```

`results` 是候选证据，不是最终引用清单。`match_kind` 说明页面是直接命中查询，还是通过 Wiki 链接图扩展进入结果。宿主 AI 应结合相关度、摘录、摘要和当前任务，自行判断哪些页面需要引用。

## 模型用量遥测

流程报告和运行指标会在模型供应商返回时记录这些字段：

- `semantic_calls`
- `total_tokens`
- `tokens_per_second`
- `prompt_cached_tokens`
- `prompt_cache_hit_tokens`
- `prompt_cache_miss_tokens`

Prompt caching 是模型供应商能力，不需要在 `config.yaml` 中单独开启。KnoArbor 会保持语义契约 prompt 的稳定前缀，并只在模型 API 返回缓存字段时记录缓存命中数据。缺少缓存字段表示供应商没有返回该遥测，不代表运行失败。

### 查询反馈

```http
POST /query/feedback
```

记录检索结果是否有用，为后续排序优化提供数据。

### 查询趋势

```http
GET /query/trends?obsidian_vault_path=/path/to/wiki&limit=100
```

从 query ledger 返回最近的无结果和低置信查询趋势。该接口只读，用于前端看板和后续维护规划。

## 异步运行接口

长任务建议使用 `/runs/*`。这是 UI、Apifox 测试和外部工作流系统的推荐入口，因为它能提供队列状态、心跳、事件、取消、指标和最终摘要。

### 启动任务

```http
POST /runs/ingest
POST /runs/ingest-file
POST /runs/lint
POST /runs/query
```

返回示例：

```json
{
  "run_id": "20260525_123456_abcdef",
  "status": "queued",
  "run": {
    "schema_version": "run_record.v1",
    "flow": "ingest",
    "stage": "queued"
  }
}
```

### 查询任务

```http
GET /runs?vault_path=/path/to/wiki&active_only=false&limit=50
GET /runs/active?vault_path=/path/to/wiki&limit=20
GET /runs/{run_id}?vault_path=/path/to/wiki
GET /runs/{run_id}/events?vault_path=/path/to/wiki&after=0&limit=200
GET /runs/{run_id}/stream?vault_path=/path/to/wiki&after=0
```

`/stream` 使用 Server-Sent Events。Apifox 可以直接测试非流式 JSON 接口；curl 可以跟随 SSE：

```bash
curl -N "http://127.0.0.1:8000/runs/RUN_ID/stream?vault_path=/absolute/wiki/path"
```

### 取消任务

```http
POST /runs/{run_id}/cancel?vault_path=/path/to/wiki
```

取消是协作式取消。正在进行的模型请求可能会先完成，随后流程在下一个检查点停止。

### 恢复 ingest 任务

```http
POST /runs/{run_id}/rerun-failed?vault_path=/path/to/wiki
```

恢复会基于上一轮运行元数据创建新的 ingest run。KnoArbor 仍以 source/window checkpoint 作为事实来源，因此成功且未变化的 source 会被跳过，失败或变化的 source 会重新进入处理。

恢复操作不会修改旧运行。调用方应使用返回的新 `run_id` 继续查询
`GET /runs/{run_id}` 和 `GET /runs/{run_id}/events`。启用 ingest recovery
时，source 级执行记录会写入 `maintenance/ingest_execution_ledger.jsonl`。

## 并行模型

KnoArbor 当前采用本地单机队列：

- 同一个 Wiki vault 内的任务串行执行，用来保护页面写入、台账、检查点和索引更新。
- 不同 vault 的任务可以独立执行。
- DeepSeek/OpenAI-compatible 模型接口技术上可以并发请求。KnoArbor 对 dry-run/preflight ingest 暴露受控 source 级并发，但同一个 vault 内的写入型 ingest 仍保持串行。
- 后续如果引入写入型 source/segment 并发，必须先汇总草稿和审核结果，再统一写入，并且只有完整 source 成功后才提交检查点。

第一版优先保证正确性、可复现和写入一致性，而不是追求最大吞吐量。

## Wiki 页面接口

这些接口用于从 UI、Skill、CLI 包装器或外部工具中查看已经生成的 Wiki 页面。

```http
GET /wiki/pages?vault_path=/path/to/wiki
GET /wiki/page?vault_path=/path/to/wiki&path=concepts/Agent-Loop.md
GET /wiki/backlinks?vault_path=/path/to/wiki&path=concepts/Agent-Loop.md
```

`/wiki/pages` 返回页面摘要和链接元数据。`/wiki/page` 返回单个 Markdown 页面、元数据和摘要字段。`/wiki/backlinks` 返回链接到当前页面的其他页面。

这些路由是稳定公开读取 API。本地 UI 也使用这些接口；外部工具应依赖 `/wiki/*`，不要依赖 `/ui/api/*`。

## 管理界面接口

管理界面入口：

```http
GET /
GET /ui
```

`/ui/api/*` 是本地控制台内部接口，后续会随前端演进调整，不建议外部工具依赖。

## 已移除的底层接口

早期原型暴露过 connector、页面读取、草稿写入、扫描和操作执行等底层 HTTP 路由。这些接口不再作为公开 API。

请改用高层工作流接口：

- 来源发现和标准化：`POST /ingest/run`
- 单文档编译：`POST /ingest/document`
- 文件路径编译：`POST /ingest/file`
- 校验维护：`POST /lint/run`
- AI 工具检索：`POST /query/search`

## 架构边界

FastAPI 是 Python Core 的适配层，不负责 prompt 契约、模型路由、页面渲染规则或 vault 策略。这些逻辑分别属于 core、semantic、pipeline、storage 和 runtime 层。
