# API 兼容策略

KnoArbor 1.x 已经面向 CLI、前端控制台、Skill 和外部工具暴露本地公开 API。
1.x 阶段优先保持接口精简清晰，并继续向 2.0 长期兼容基线收敛。

## 公开 API

公开集成 API 保持精简：

- `GET /health`
- `GET /doctor`
- `POST /ingest`
- `POST /lint`
- `GET /models/providers`
- `POST /models/discover`
- `POST /models/probe`
- `POST /models/apply-capabilities`
- `POST /chat`
- `POST /chat/stream`
- `GET /chat/sessions`
- `GET /chat/sessions/{session_id}`
- `PATCH /chat/sessions/{session_id}`
- `DELETE /chat/sessions/{session_id}`
- `POST /chat/sessions/{session_id}/ingest`
- `POST /chat/sessions/{session_id}/close`
- `POST /chat/sessions/{session_id}/retry`
- `POST /query`
- `POST /query/feedback`
- `GET /query/trends`
- `GET /reports`
- `GET /reports/content`
- `GET /runtime`
- `GET /sources`
- `GET /vaults`
- `GET /runs`
- `GET /runs/{run_id}`
- `GET /runs/{run_id}/events`
- `GET /runs/{run_id}/stream`
- `POST /runs/{run_id}/cancel`
- `GET /wiki/pages`
- `GET /wiki/pages/content`
- `GET /wiki/pages/links`

不同功能通过 `execution`、`kind`、`mode` 等请求字段选择。

## 原型路径

早期原型路径已经在公开 v1 API 前移除。新的工作流变体应该通过精简公开 API
上的请求字段表达，而不是继续增加顶层路径。

## 变更规则

- 公开路径和必填字段变更必须同步更新本文档和 API 表面测试。
- 响应可以增加可选字段。
- `/ui/api/*` 是本地管理界面的内部接口，不作为稳定集成 API。
