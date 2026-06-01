# API 兼容性策略

KnoArbor 提供本地 HTTP API，供内置控制台、CLI 辅助命令、外部工作流工具和 AI 工具技能使用。本文定义 v0.x 阶段哪些内容稳定，以及破坏性变更应如何处理。

## 公开稳定接口

公开 v0.x API 面由 [接口说明](API.md) 记录，并由 `src/knoarbor/entrypoints/api_contract.py` 跟踪。

稳定接口族：

- `GET /health`
- `GET /doctor`
- `POST /ingest/run`
- `POST /ingest/document`
- `POST /ingest/file`
- `POST /lint/run`
- `POST /query/search`
- `POST /query/feedback`
- `GET /query/trends`
- `POST /runs/ingest`
- `POST /runs/ingest-file`
- `POST /runs/lint`
- `POST /runs/query`
- `GET /runs`
- `GET /runs/active`
- `GET /runs/{run_id}`
- `GET /runs/{run_id}/events`
- `GET /runs/{run_id}/stream`
- `POST /runs/{run_id}/cancel`
- `POST /runs/{run_id}/rerun-failed`
- `GET /wiki/pages`
- `GET /wiki/page`
- `GET /wiki/backlinks`

## 内部 UI 接口

`/ui/api/*` 只服务内置 Web 控制台，后续会随着 UI 演进变化。外部工具应使用上面的公开接口。

`GET /` 是主要控制台入口。`GET /ui` 是兼容别名。

## 兼容性规则

v0.x alpha 阶段：

- Endpoint 路径和 HTTP 方法应保持稳定。
- 必需请求字段不应被删除或静默改变含义。
- 核心响应字段含义应保持稳定。
- 可以新增可选请求字段。
- 可以新增响应字段。
- 错误响应必须使用统一错误 envelope 和稳定错误码。
- 已废弃公开 endpoint 至少保留一个 minor 版本，除非它本身不安全。

破坏性变更必须包含：

1. Changelog 条目。
2. Release note 迁移说明。
3. API 文档更新。
4. 契约测试更新。
5. 尽可能提供替代路径。

## Schema Version

如果响应结构会被外部工具长期消费，应包含 `schema_version` 字段。

示例：

- `wiki_query.v1`
- `query_trace.v1`
- `run_record.v1`
- `source_document.v1`

新增字段不需要变更 schema version。删除字段或改变字段含义则需要。

## 测试要求

API 兼容性应由以下内容守护：

- `api_contract.py` 中的契约列表；
- 稳定 endpoint 存在性单元测试；
- OpenAPI 公开路由检查；
- 发布前 API/CLI 兼容性审查。

发布前检查：

```bash
uv run python -m unittest discover tests
scripts/release-readiness.py
```
