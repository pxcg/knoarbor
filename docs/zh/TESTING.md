# 测试与质量门禁

本文列出当前测试门禁及其边界。目标是在不触碰用户运行时数据的前提下，让本地检查可预测。

## 默认改动验证

先运行 changed-file 规划器：

```bash
uv run python scripts/plan-affected-validation.py
```

当脏工作区同时包含多个任务时，应显式传入本任务文件，避免无关改动扩大验证范围：

```bash
uv run python scripts/plan-affected-validation.py --paths path/to/owner.py tests/test_owner.py
```

它输出基于路径的风险下限、可以机械确定的命令，以及仍需人工选择的 owner/direct-consumer
tests。检查公开、持久、语义、生命周期、打包或发布依赖闭包后，风险只能上调。可以使用
`--run` 执行机械子集，再补充该依赖闭包真正需要的 focused tests。

R3 不自动要求全量单元测试、`dev-check.sh`、桌面打包或真实模型测试。只有改动影响到
对应门禁，或进入发布/全链验收节点时才升级。

对于 Initiative，affected planner 为固定方法门禁目录提供依据，但不负责宣告完成。
`project-development-harness.py baseline` 冻结工作区并执行基线组合；
`run-gates --phase integration` 把 integration 绑定到同一组固定检查；`acceptance` 以相同
稳定 gate identity 重跑，并强制检查 `gate-delta` 与 `scope`。选中的 full-chain 或
live-model gate 只通过 `record-external-gate` 记录结果、证据 ID 和 SHA-256 digest，绝不保存
原始输出。完全相同的既有失败继续可见但不归因于本次
Initiative；新增或变化的硬门禁失败会阻断验收，软门禁失败必须记录 owner、确认和到期/
移除条件。

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
cd renderer
npm ci
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

renderer 产物属于本地构建输出；不要提交 `renderer/node_modules/` 或 `renderer/dist/`。

## 广覆盖开发门禁

```bash
scripts/dev-check.sh
```

当前范围：

- 前端构建；
- 前端依赖安全扫描；
- Playwright UI 冒烟；
- 桌面端类型/构建、更新仓库契约和生产依赖安全扫描；
- Ruff Python lint；
- 架构依赖与循环门禁；
- 文档治理与本地 Markdown 链接检查；
- Python 单元测试；
- 使用临时 config 和临时 vault 的 CLI 诊断；
- Python 包构建。

该脚本不得写入维护者真实的 `vaults/`、`config.yaml` 或 `.env`。它是广覆盖集成门禁，
不是每个本地改动的默认命令。

## 单项质量门禁

```bash
uv run --extra dev ruff check src tests scripts
uv run python scripts/check-architecture.py
uv run python scripts/check-doc-governance.py
uv run python scripts/check-doc-links.py
cd renderer && npm run check:i18n
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

干净克隆 smoke 会检出候选的精确 commit，并且只在临时 clone 内写入。

## 持续集成

推送到 `KnoArbor` 或面向该分支的合并请求会运行 Python lint/tests、架构与文档治理、
renderer build/Playwright、桌面契约和包构建。`knoarbor-v*` 标签只有在该精确标签上的
`release-check.sh` 通过后，才允许构建可发布桌面产物。

## 真实模型冒烟

```bash
set -a && source .env && set +a
scripts/live-release-candidate-smoke.sh
```

必需环境变量为 `KNOARBOR_LIVE_MODEL_API_KEY`、
`KNOARBOR_LIVE_MODEL_BASE_URL` 和 `KNOARBOR_LIVE_MODEL_NAME`。

覆盖范围：

- 临时 Markdown ingest；
- 临时 Codex 会话 ingest；
- 结构维护；
- 查询；
- 一条带已解析引用的 Raw-grounded Chat 回答；
- 一条由可信 no-match 进入、具有明确 provenance 且没有本地引用的通用知识回答；
- 非 Markdown 缺少预处理器的负向检查。

该测试会调用真实模型供应商，因此不放入默认发布门禁。它必须使用临时 vault 和临时 config。

## 长期真实资料基准

真实资料质量评估是可选流程，必须使用独立的本地基准知识库和可丢弃的执行知识库。
来源身份与人工复核的预期 evidence 应保持稳定，但产品生成的 Raw、投影、索引、
会话和报告不得成为 fixture 事实权威。

Raw/span 忠实度、错误 vault 泄漏、无支持的 grounded 命题和错误的通用知识路由
属于硬失败。检索、回答覆盖、延迟、token 和存储必须分别报告，不能用总分掩盖关键
失败。私有语料和供应商凭据不得提交到公开仓库。

## 人工发布审查

发布前还应遵循 [发布前审查清单](RELEASE_CHECKLIST.md)，覆盖隐私、协议、文档、UI、API/CLI 兼容性和长任务安全。

## 未来目标门禁

以下是目标门禁，但当前还不是必需发布门禁：

- 部分 Python 模块静态类型检查。
- 前端 lint。
- API schema snapshot 测试。
- 更长的真实模型回归 fixture。

在工具链和 CI job 真正存在之前，不要把它们写成当前必跑命令。
