# 错误码

KnoArbor 的 CLI 和公开 HTTP API 会返回结构化错误。错误码是面向用户、日志、前端提示和支持排查的稳定查询键。

## 错误结构

HTTP 错误结构：

```json
{
  "error": {
    "code": "KA-INPUT-001",
    "category": "user_input_error",
    "message": "Request validation failed.",
    "retryable": false,
    "hint": "Check the command arguments or request payload and retry."
  },
  "detail": "Request validation failed."
}
```

CLI 错误使用同一套目录：

```text
knoarbor: error: [KA-CFG-001] user_input_error: Config file does not exist: /path/config.yaml
hint: Create config.yaml from config.example.yaml or pass --config with a valid path.
```

## 错误码表

| 错误码 | 大类 | HTTP | 可重试 | 含义 | 常见处理 |
| --- | --- | ---: | --- | --- | --- |
| `KA-INPUT-001` | `user_input_error` | 400/422 | 否 | 请求、命令参数、枚举值或 schema 校验失败。 | 检查命令/API payload、必填字段、路径和选项值。 |
| `KA-INPUT-002` | `user_input_error` | 400 | 否 | 必需的本地文件或路径不存在。 | 创建文件，修正配置路径，或对缺失的 vault 先运行 `knoar init`。 |
| `KA-CFG-001` | `user_input_error` | 400 | 否 | 必需的 KnoArbor 配置文件不存在。 | 创建配置文件，传入 `--config`，或运行 `knoar init`。 |
| `KA-CFG-002` | `user_input_error` | 400 | 否 | 配置内容格式错误、扩展名不支持，或配置项组合不一致。 | 修正 YAML/JSON 结构、文件扩展名或无效配置组合。 |
| `KA-VAULT-001` | `user_input_error` | 400 | 否 | vault 路径、wiki 页面路径、checkpoint 路径或 ledger 路径无效，或逃逸出 vault。 | 使用配置 vault 内部路径，避免绝对路径或上级目录穿越写入 wiki。 |
| `KA-SRC-001` | `user_input_error` | 400 | 否 | 来源连接器配置或来源引用无效。 | 检查 connector settings、source ref、file URI 元数据和启用的连接器名称。 |
| `KA-SRC-002` | `user_input_error` | 400 | 否 | 配置的来源目录、来源文件或聊天会话文件不存在。 | 修正来源路径或连接器配置后再运行 ingest。 |
| `KA-DOC-001` | `user_input_error` | 400 | 否 | 非 Markdown 文档需要预处理，但文档处理器不可用或配置不完整。 | 启用并配置文档处理器，或先提供已转换的 Markdown。 |
| `KA-EXT-001` | `external_service_error` | 502 | 是 | 外部服务失败，例如模型端点或文档预处理器不可用。 | 检查服务状态、凭证、端点 URL、超时时间，然后重试。 |
| `KA-MODEL-001` | `model_output_error` | 502 | 是 | 模型输出不是合法 JSON，或不符合结构化契约。 | 重试、缩小输入，或切换到更稳定的模型/供应商。 |
| `KA-SEM-001` | `model_output_error` | 502 | 是 | 语义契约、提示词契约或模型响应结构无效。 | 重试，检查契约名称/schema，或切换到更稳定的模型/供应商。 |
| `KA-POLICY-001` | `policy_rejection` | 422 | 否 | 生成的操作或草稿被 KnoArbor 策略拒绝。 | 查看报告，并调整来源内容、提示词契约或策略。 |
| `KA-STORAGE-001` | `storage_conflict` | 409 | 是 | vault 写入冲突、旧 hash 或文件锁冲突阻止了安全写入。 | 等其他进程完成后重试，或刷新页面/索引状态。 |
| `KA-RUN-001` | `user_input_error` | 400 | 否 | 请求的运行监控记录不存在。 | 刷新运行列表，或使用有效的 run id。 |
| `KA-RUNTIME-001` | `internal_error` | 500 | 否 | 本地运行时能力不可用，例如当前平台不支持文件锁。 | 在受支持的平台运行，或带上环境信息提交 issue。 |
| `KA-INTERNAL-001` | `internal_error` | 500 | 否 | 未预期的内部错误。 | 保留运行报告和日志，带上堆栈和复现步骤提交 issue。 |

## 设计规则

- 新的公开错误必须进入错误码表，不允许散落临时字符串。
- `code` 是稳定查询键；`message` 可以随着版本变得更清晰。
- `category` 用于粗粒度程序处理，一个大类可以包含多个错误码。
- `retryable=true` 只表示适合自动重试，不保证重试一定成功。
- API 客户端应展示 `message` 和 `hint`，记录 `code/category/retryable`，并保留 `details` 用于排查。
- 运行监控记录、运行事件、语义重试事件和 ingest 报告在操作失败时，都应携带同一组 `code/category/retryable/hint` 字段。
