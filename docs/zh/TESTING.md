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
npm run check:i18n
npm run build
npm run test:e2e
```

覆盖范围：

- 中英文 UI 翻译 key 一致性；
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

该脚本不得写入维护者真实的 `vaults/`、`config.yaml` 或 `.env`。

## 单项质量门禁

```bash
uv run --extra dev ruff check src tests scripts
uv run python scripts/check-doc-links.py
cd web && npm run check:i18n
```

这些检查已经纳入 `scripts/dev-check.sh` 和 CI。修改 Python 代码、公开文档或前端文案时，可以单独运行。

## 测试分层

KnoArbor 将快速本地检查与真实模型检查分开：

- **单元测试**覆盖纯函数、schema、检索评分、报告渲染和 pipeline policy，不访问网络或用户真实 vault。
- **契约测试**覆盖 API、CLI、skill helper、semantic schema 和 model gateway 边界，使用 fake client 或临时 vault。
- **Golden 测试**固定代表性的 ingest、lint、query 和 semantic 输出形态，避免用户可见报告和 context pack 静默漂移。
- **UI 冒烟测试**覆盖页面加载、导航和打包控制台集成。
- **真实模型冒烟**为可选测试，只能使用临时 vault。

新增测试应说明保护的架构层。真实模型测试不得进入默认本地单元门禁。

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

## RAG 基线对比

KnoArbor 可以用同一套对话 fixture 和传统 chunk 检索做对比。默认本地基线不启动数据库或外部 RAG 产品，只读取 raw 文件、切块、执行 BM25 检索，并可选调用已配置模型基于检索到的 chunk 回答。所有输出都写入 `tmp/rag-baselines/`。

```bash
uv run python scripts/eval/rag_lite_baseline.py --retrieval-only
```

如需包含模型回答：

```bash
uv run python scripts/eval/rag_lite_baseline.py --provider deepseek
```

当已有 WeKnora 服务运行，并且目标是和完整外部 RAG 产品对比时，可以使用 WeKnora 基线脚本。

## 人工发布审查

发布前还应遵循 [发布前审查清单](RELEASE_CHECKLIST.md)，覆盖隐私、协议、文档、UI、API/CLI 兼容性和长任务安全。

## 未来目标门禁

以下是目标门禁，但当前还不是必需发布门禁：

- 部分 Python 模块静态类型检查。
- 前端 lint。
- API schema snapshot 测试。
- 更长的真实模型回归 fixture。

在工具链和 CI job 真正存在之前，不要把它们写成当前必跑命令。
