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

KnoArbor 不对外暴露大量细分 API。不同运行方式通过请求参数选择，而不是通过新增多个路径区分。

| 范围 | 端点 | 用途 |
| --- | --- | --- |
| 服务状态 | `GET /health` | 轻量服务心跳 |
| 诊断 | `GET /doctor` | 只读运行前检查 |
| 知识编译 | `POST /ingest` | 编译配置来源、单个标准文档或单个文件 |
| 校验维护 | `POST /lint/run` | 执行确定性、结构、质量或完整维护 |
| 知识查询 | `POST /query/search` | 为宿主 AI 检索 Wiki 上下文 |
| 查询反馈 | `POST /query/feedback`, `GET /query/trends` | 记录和查看查询反馈 |
| 运行队列 | `POST /runs`, `GET /runs`, `GET /runs/{run_id}` | 启动和查看长任务 |
| 运行事件 | `GET /runs/{run_id}/events`, `GET /runs/{run_id}/stream`, `POST /runs/{run_id}/cancel` | 观察或取消运行 |
| Wiki 页面 | `GET /wiki/pages`, `GET /wiki/page`, `GET /wiki/backlinks` | 读取生成后的 Wiki 页面 |

`/ui/api/*` 仅供本地管理界面使用，不作为稳定集成 API。

## 兼容策略

本文档中的端点是 v0.x 公开 alpha API。路径、方法、必填字段和核心响应语义在 v0.x 内保持稳定；响应可增加可选字段。

机器可读契约位于 `src/knoarbor/entrypoints/api_contract.py`，API 表面测试会直接读取该契约。

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

## 知识编译

```http
POST /ingest
```

同步执行知识编译。通过 `kind` 选择输入形态：

```json
{ "kind": "connectors", "config_path": "./config.yaml", "connector_names": ["markdown"], "write": true }
```

```json
{ "kind": "file", "config_path": "./config.yaml", "input_path": "/path/to/file.pdf", "write": true }
```

```json
{ "kind": "document", "source_document": { "schema_version": "source_document.v1" }, "write": true }
```

Markdown 文件会直接处理。PDF/DOCX/PPTX 等富文档需要配置 MinerU 等文档预处理器。

## 校验维护

```http
POST /lint/run
```

执行确定性校验，并可按 `mode` 启用结构或质量维护：

- `deterministic`
- `semantic_structural`
- `semantic_quality`
- `semantic_full`

## 知识查询

```http
POST /query/search
```

返回相关 Wiki 页面、摘录、关联上下文、追踪信息和可交给宿主 AI 使用的上下文包。KnoArbor 不生成最终聊天答案。

默认返回压缩后的 `compact` 上下文包；如果调用方需要完整命中页面正文，可设置 `context_format: "full"`。

## 运行队列

```http
POST /runs
```

启动一个队列任务。通过 `flow` 选择工作流。

知识编译：

```json
{
  "flow": "ingest",
  "ingest": { "kind": "connectors", "config_path": "./config.yaml", "write": true }
}
```

校验维护：

```json
{
  "flow": "lint",
  "lint": {
    "obsidian_vault_path": "/path/to/wiki",
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
}
```

知识查询：

```json
{
  "flow": "query",
  "query": { "obsidian_vault_path": "/path/to/wiki", "query": "agent loop" }
}
```

恢复失败的知识编译：

```json
{
  "flow": "ingest",
  "vault_path": "/path/to/wiki",
  "recovery_of_run_id": "20260525_123456_abcdef",
  "recovery": { "write": true }
}
```

查看运行：

```http
GET /runs?vault_path=/path/to/wiki&active_only=false&limit=50
GET /runs/{run_id}?vault_path=/path/to/wiki
GET /runs/{run_id}/events?vault_path=/path/to/wiki&after=0&limit=200
GET /runs/{run_id}/stream?vault_path=/path/to/wiki&after=0
POST /runs/{run_id}/cancel?vault_path=/path/to/wiki
```

## Wiki 页面

```http
GET /wiki/pages?vault_path=/path/to/wiki
GET /wiki/page?vault_path=/path/to/wiki&path=concepts/Agent-Loop.md
GET /wiki/backlinks?vault_path=/path/to/wiki&path=concepts/Agent-Loop.md
```

`/wiki/pages` 返回页面摘要和链接元数据。`/wiki/page` 返回单个 Markdown 页面及其元数据。`/wiki/backlinks` 返回指向目标页面的页面。

## 移除的原型端点

原型期的连接器、草稿写入、扫描、操作执行和拆分工作流端点都不再公开。请使用 `POST /ingest`、`POST /lint/run`、`POST /query/search` 和 `POST /runs`。
