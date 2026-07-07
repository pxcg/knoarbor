# 发布前审查清单

这份清单定义 KnoArbor 的发布门禁。它不只是测试命令，而是确认一个版本能从干净仓库安装、可以安全公开、并且新用户能理解如何使用。

每次公开打 tag 前都应使用这份清单。自动脚本只能覆盖一部分，其余内容需要维护者审查。

## 1. 仓库边界

确认 git 只跟踪源码、公开文档和明确需要发布的静态资源。

必跑检查：

```bash
git status --short
git ls-files | rg '(^vaults/|^dist/|node_modules|\.venv|\.uv-cache|\.pytest_cache|egg-info|knoarbor_logo_asset_kit|\.obsidian)' || true
```

预期结果：

- 打 tag 前 `git status --short` 为空。
- 运行时知识库、本地工作流导出、构建产物、虚拟环境、缓存和私有设计记录没有被跟踪。
- `src/knoarbor/ui/dist/` 允许被跟踪，因为它是 Python 包内置控制台资源。

运行时数据隔离：

- 审查所有引用 `wiki`、`config.yaml`、`.env`、本地资料目录或 connector 会话路径的脚本。
- 发布/测试脚本可以读取 `config.example.yaml`，但任何可写 config 或 vault 都必须放在 `mktemp -d` 创建的临时目录下。
- 如果任何自动门禁会写入项目根目录下的 `vaults/`、`config.yaml`、`.env` 或私有来源目录，应阻止发布。
- 唯一可接受例外是 clean-clone smoke 在临时克隆目录内写入 `vaults/`，不得写入维护者当前工作区。

## 2. 隐私和密钥审查

确认发布内容不包含个人数据、本地私有知识库、API Key、原始聊天记录或私有工作流导出。

必跑检查：

```bash
rg -n '/Users/|/home/|DEEPSEEK_API_KEY=|sk-[A-Za-z0-9_-]{12,}|api_key\s*:|apiKey\s*:' \
  README.md README.zh-CN.md docs src tests config.example.yaml .github pyproject.toml || true
```

可接受结果：

- 文档占位示例，例如 `DEEPSEEK_API_KEY=your-key`。
- 脱敏测试中故意出现的假密钥。
- 已脱敏路径，例如 `/Users/[REDACTED_USER]/...`。

如果发现真实绝对路径、密钥、token、原始私有聊天记录或内部工作流文件，应阻止发布。

## 3. 协议和第三方声明

确认开源协议明确，并且包含的资源与协议兼容。

必查内容：

- `LICENSE` 存在且为 Apache-2.0。
- `NOTICE` 存在。
- 如果包含第三方名称、图标或集成说明，`THIRD_PARTY_NOTICES.md` 应存在。
- README 应说明第三方标识归各自所有者。

如果新增 logo、截图、图标、数据集或内置解析器，需要判断是否需要署名，或是否应改为链接引用而不是打包。

## 4. 构建和测试门禁

运行开发门禁：

```bash
scripts/dev-check.sh
```

该门禁应覆盖：

- Ruff Python lint。
- 本地 Markdown 文档链接检查。
- Python 单元测试。
- 前端构建。
- 前端依赖安全扫描和 UI 冒烟测试。
- CLI smoke 检查。
- Python 包构建。

已知且可接受的 warning 应记录下来。非预期跳过、未捕获异常或构建失败会阻止发布。

## 5. 发布就绪脚本

运行：

```bash
scripts/release-readiness.py
```

预期结果：

- `ready: true`。
- 没有被跟踪的私有路径。
- 没有被跟踪的非预期生成产物。
- 必需公开文件齐全。

## 6. 干净克隆测试

运行干净克隆 smoke：

```bash
scripts/clean-clone-smoke.sh
```

这一步验证新用户可以从干净仓库安装项目，而不是依赖本地缓存或被 ignore 的文件。

## 7. 功能 smoke 矩阵

至少验证以下内容，不应依赖私有数据：

| 区域 | 检查项 | 是否阻止发布 |
| --- | --- | --- |
| CLI | `uv run knoar --help` 和 `uv run knoar doctor` | 是 |
| 服务 | `uv run knoar serve` 可以启动并打印 UI 地址 | 是 |
| UI | `/` 打开控制台，`/docs` 打开接口文档 | 是 |
| 查询 | 对示例或现有知识库返回结构化查询结果 | 是 |
| 知识编译 | 小型 Markdown 来源能写入临时知识库 | 是 |
| 校验维护 | 确定性 lint 能扫描临时知识库并写入报告 | 是 |
| 报告 | 知识编译、校验维护和查询报告能在控制台阅读 | 是 |

当缺少凭证或网络不可用时，可以跳过真实模型调用，但发布决策中必须注明。

当前自动和人工测试边界见 [测试与质量门禁](TESTING.md)。

## 8. API 和 CLI 兼容性

发布前审查所有公开入口：

- `docs/CLI.md` 中记录的 CLI 命令。
- `docs/API.md` 中记录的 HTTP 接口。
- `docs/API_COMPATIBILITY.md` 中记录的兼容性规则。
- `docs/ERROR_CODES.md` 中记录的稳定错误码。
- `docs/CONFIGURATION.md` 中记录的配置字段。

破坏性变更必须写入 changelog，并提供迁移说明。

## 9. 文档审查

同时审查英文和中文公开文档：

- `README.md`
- `README.zh-CN.md`
- `docs/README.md`
- `docs/zh/README.md`
- `docs/QUICKSTART.md`
- `docs/zh/QUICKSTART.md`
- `docs/CONFIGURATION.md`
- `docs/zh/CONFIGURATION.md`
- `docs/API.md`
- `docs/zh/API.md`
- `docs/API_COMPATIBILITY.md`
- `docs/zh/API_COMPATIBILITY.md`
- `docs/CLI.md`
- `docs/zh/CLI.md`
- `docs/TROUBLESHOOTING.md`
- `docs/zh/TROUBLESHOOTING.md`
- `docs/BACKUP_AND_RECOVERY.md`
- `docs/zh/BACKUP_AND_RECOVERY.md`
- `docs/TESTING.md`
- `docs/zh/TESTING.md`
- `SUPPORT.md`
- `CODE_OF_CONDUCT.md`

文档应说明：

- KnoArbor 是什么。
- KnoArbor 不是什么。
- 如何安装和运行。
- 如何配置模型供应商。
- 知识编译、校验维护、知识查询如何配合。
- 哪些数据会写入本地。
- 当前公开版本边界。

## 10. UI 审查

打开本地控制台并检查：

- 导航顺序和文案。
- 资料来源设置。
- 知识编译、校验维护、知识查询运行页。
- 运行监控。
- 运行报告。
- 知识库浏览。
- 图谱页面。
- 设置页面。
- 中英文文案。

如果 UI 无法加载、核心动作隐藏、报告链接断裂，或生成页面无法查看，应阻止发布。

## 11. 性能和长任务安全

确认长任务流程暴露：

- 队列状态。
- 心跳。
- 可取消的运行句柄。
- 进度事件。
- 报告写入，包括失败报告。
- 写入文件锁。

当前版本不要求分布式队列、数据库或多用户 session，但单机行为必须可预测。

## 12. 发布说明和打 tag

打 tag 前：

- 更新 `CHANGELOG.md`。
- 新增或更新 `docs/releases/vX.Y.Z.md`。
- 确认 `pyproject.toml` 版本。
- 提交所有发布相关变更。

公开发布 tag 应从 `main` 创建：

```bash
git tag -a vX.Y.Z -m "KnoArbor vX.Y.Z"
git push origin main --tags
```

GitHub Release 应包含：

- 简短定位。
- 主要用户可见变化。
- 验证摘要。
- 已知限制。
- 升级说明。

## 发布决策模板

```text
版本：
提交：
日期：

自动门禁：
- dev-check：
- release-readiness：
- clean-clone-smoke：
- frontend build：

人工门禁：
- 隐私：
- 协议：
- 文档：
- UI：
- 功能 smoke：
- API/CLI 兼容性：

已知限制：
- ...

结论：
- release / hold
```
