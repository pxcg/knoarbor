# API 兼容策略

KnoArbor 尚未发布稳定 v1 API，因此预发布阶段优先保持公开接口清晰，而不是兼容早期原型路径。

## 公开 API

公开集成 API 保持精简：

- `GET /health`
- `GET /runtime`
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
- `GET /vaults/all/pages`
- `GET /vaults/all/pages/content`
- `GET /vaults/all/pages/links`

不同功能通过 `execution`、`kind`、`mode` 等请求字段选择。

## 原型路径

早期原型路径已经在公开 v1 API 前移除。新的工作流变体应该通过精简公开 API
上的请求字段表达，而不是继续增加顶层路径。

## 变更规则

- 公开路径和必填字段变更必须同步更新本文档和 API 表面测试。
- 响应可以增加可选字段。
- `/ui/api/*` 是本地管理界面的内部接口，不作为稳定集成 API。
