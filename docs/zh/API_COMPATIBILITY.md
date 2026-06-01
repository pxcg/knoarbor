# API 兼容策略

KnoArbor 尚未发布稳定 v1 API，因此预发布阶段优先保持公开接口清晰，而不是兼容早期原型路径。

## 公开 API

公开集成 API 保持精简：

- `GET /health`
- `GET /doctor`
- `POST /ingest`
- `POST /lint`
- `POST /query`
- `POST /query/feedback`
- `GET /query/trends`
- `GET /runs`
- `GET /runs/{run_id}`
- `GET /runs/{run_id}/events`
- `GET /runs/{run_id}/stream`
- `POST /runs/{run_id}/cancel`
- `GET /wiki/pages`
- `GET /wiki/pages/content`
- `GET /wiki/pages/links`

不同功能通过 `execution`、`kind`、`mode`、`context_format` 等请求字段选择。

## 移除的原型路径

以下原型路径不属于公开 API：

- `POST /ingest/run`
- `POST /ingest/document`
- `POST /ingest/file`
- `POST /runs/ingest`
- `POST /runs/ingest-file`
- `POST /runs/lint`
- `POST /runs/query`
- `GET /runs/active`
- `POST /runs/{run_id}/rerun-failed`
- `POST /lint/run`
- `POST /query/search`
- `POST /runs`
- `GET /wiki/page`
- `GET /wiki/backlinks`

请改用 `POST /ingest`、`POST /lint` 或 `POST /query`。`GET /runs*` 只用于运行监控。

## 变更规则

- 公开路径和必填字段变更必须同步更新本文档和 API 表面测试。
- 响应可以增加可选字段。
- `/ui/api/*` 是本地管理界面的内部接口，不作为稳定集成 API。
