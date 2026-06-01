# 测试与质量门禁

本文列出当前测试门禁及其边界。目标是在不触碰用户运行时数据的前提下，让本地检查可预测。

## 本地单元测试

```bash
uv run --extra dev python -m unittest discover -s tests
```

覆盖范围：

- core schema 和 config；
- connector 与 source normalization；
- ingest、lint、query 流程行为；
- storage、index 和 report 工具；
- 已覆盖的 API route 契约。

单元测试不得依赖真实模型供应商凭证。

## 前端构建和 UI 冒烟

```bash
cd web
npm install
npm run build
npm run test:e2e
```

覆盖范围：

- TypeScript 构建；
- Vite production bundle；
- 针对打包后 FastAPI 控制台的导航冒烟；
- 基础 UI/API 连接。

前端会被打包到 `src/knoarbor/ui/dist/`；不要提交 `web/node_modules/` 或 `web/dist/`。

## 开发门禁

```bash
scripts/dev-check.sh
```

当前范围：

- 前端构建；
- 前端依赖安全扫描；
- Playwright UI 冒烟；
- Ruff Python lint；
- 本地 Markdown 文档链接检查；
- Python 单元测试；
- 使用临时 config 和临时 vault 的 CLI 诊断；
- Python 包构建。

该脚本不得写入维护者真实的 `wiki/`、`config.yaml` 或 `.env`。

## 单项质量门禁

```bash
uv run --extra dev ruff check src tests scripts
uv run python scripts/check-doc-links.py
```

这两项已经纳入 `scripts/dev-check.sh` 和 CI。修改 Python 代码或公开文档时，可以单独运行。

## 发布门禁

```bash
scripts/release-check.sh
```

当前范围：

- 开发门禁；
- 发布就绪检查；
- 干净克隆 smoke。

干净克隆 smoke 只在临时 clone 内写入。

## 真实模型冒烟

```bash
set -a && source .env && set +a
scripts/live-release-candidate-smoke.sh
```

覆盖范围：

- 临时 Markdown ingest；
- 临时 Codex 会话 ingest；
- 结构维护；
- 查询；
- 非 Markdown 缺少预处理器的负向检查。

该测试会调用真实模型供应商，因此不放入默认发布门禁。它必须使用临时 vault 和临时 config。

## 人工发布审查

发布前还应遵循 [发布前审查清单](RELEASE_CHECKLIST.md)，覆盖隐私、协议、文档、UI、API/CLI 兼容性和长任务安全。

## 未来目标门禁

以下是目标门禁，但当前还不是必需发布门禁：

- 部分 Python 模块静态类型检查。
- 前端 lint。
- API schema snapshot 测试。
- 更长的真实模型回归 fixture。

在工具链和 CI job 真正存在之前，不要把它们写成当前必跑命令。
