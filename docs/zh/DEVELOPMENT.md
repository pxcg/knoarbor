# 开发说明

## 本地环境

```bash
uv sync
cd web
npm install
npm run build
```

## 常用检查

```bash
uv run --extra dev ruff check src tests scripts
uv run python scripts/check-doc-links.py
uv run --extra dev python -m unittest discover tests
cd web && npm run build
uv build
```

准备 release candidate 时，优先运行本地开发门禁脚本：

```bash
scripts/dev-check.sh
```

该脚本会按正确顺序运行前端构建、Ruff、文档链接检查、Python 单元测试、只读 `doctor` 诊断和 Python 包构建。最终 release candidate 运行完整发布门禁：

```bash
scripts/release-check.sh
```

`release-check.sh` 会按顺序执行 `dev-check.sh`、`release-readiness.py` 和 `clean-clone-smoke.sh`。`dev-check.sh` 包含前端 i18n 一致性检查、前端构建、前端依赖安全扫描、Playwright UI 冒烟测试、Ruff、文档链接检查、Python 单元测试、只读 `doctor` 和 Python 包构建。

当模型供应商可用时，运行真实 release candidate 冒烟测试：

```bash
set -a && source .env && set +a
scripts/live-release-candidate-smoke.sh
```

该脚本会创建临时知识库，依次运行 Markdown ingest、Codex 会话 ingest、结构维护、查询，以及一个非 Markdown 缺少预处理器时必须返回 `KA-DOC-001` 的负向检查。临时目录会自动删除。

完整测试矩阵和发布门禁边界见 [测试与质量门禁](TESTING.md)。

当前发布门禁包含 Python 单元测试、Ruff、文档链接检查、前端构建、前端依赖安全扫描、Playwright UI 冒烟测试、只读 `doctor` 诊断和 Python 包构建。类型检查和前端 lint 是目标门禁；在工具链正式加入 `pyproject.toml`、`web/package.json` 和 CI 之前，不应把它们写成当前必跑命令。

修改管理控制台导航、布局或 API 连接时，运行浏览器冒烟测试：

```bash
cd web
npx playwright install chromium
npm run test:e2e
```

Playwright 会在临时本地端口启动打包后的 FastAPI 应用并打开管理控制台，因此它验证的是 `knoar serve` 使用的同一套路由形态。

在同一个工作区本地运行检查时，应按顺序执行。前端构建会重写 `src/knoarbor/ui/dist/`，而 Python UI 测试会读取该目录，并行执行会产生短暂的资产 404。

其他发布辅助脚本：

```bash
scripts/prepare-release.py 0.5.2
scripts/release-readiness.py
scripts/clean-clone-smoke.sh
scripts/release-check.sh
```

`prepare-release.py` 会同步包版本元数据，并创建发布说明占位文件。它应在干净工作区中运行，随后再人工整理 `CHANGELOG.md` 和 `docs/releases/v<version>.md`。`release-readiness.py` 检查分支、dirty tree、必要公开文件和不应被追踪的本地运行路径。`clean-clone-smoke.sh` 会把当前仓库 clone 到临时目录，并在不调用模型 API 的情况下验证安装、前端构建、Python 测试、只读 `doctor`、包构建和基础 CLI 命令。`release-check.sh` 运行完整本地发布门禁序列。

`live-release-candidate-smoke.sh` 不放入默认 `release-check.sh`，因为它会调用真实模型供应商并需要 `DEEPSEEK_API_KEY`。

## 运行时数据隔离

测试脚本和发布脚本默认不得操作维护者本机的真实运行数据。

用户运行时数据包括：

- 项目根目录下的 `config.yaml` 和 `.env`。
- 项目根目录下的 `vaults/` 运行时知识库。
- 各类 connector 读取的来源目录，例如本地聊天记录、Markdown 笔记目录、原始文档目录或私有导出目录。
- 所有被 git ignore 的本地工作流导出、缓存和私有开发记录。

强制规则：

- 自动门禁可以读取 `config.example.yaml`，但需要配置文件时必须写入临时 config。
- 自动门禁如果需要知识库，必须在 `mktemp -d` 下创建临时 vault，并用 `trap` 清理。
- 自动门禁不得初始化、重写、lint、ingest 或清理项目根目录下的 `vaults/`、`config.yaml`、`.env`。
- 只有用户明确触发的产品命令，例如 `knoar init`、`knoar ingest`、API 调用或 UI 操作，才可以作用于用户配置的真实知识库。
- 仓库脚本不得对项目根目录下被 ignore 的运行时路径使用 `git clean -fdx` 或宽泛的 `rm -rf`。

安全脚本模式：

```bash
TMP_DIR="$(mktemp -d)"
trap 'rm -rf "$TMP_DIR"' EXIT

TEMP_CONFIG="$TMP_DIR/config.yaml"
TEMP_VAULT="$TMP_DIR/vault"

# 将 config.example.yaml 复制为 TEMP_CONFIG，把 vault.path 改到 TEMP_VAULT，
# 后续 CLI/API 检查只使用 TEMP_CONFIG。
```

唯一允许被跟踪的生成目录是 `src/knoarbor/ui/dist/`，因为它会被打包进 Python 包。所有运行时知识库内容都属于用户本地数据。

## 分支与发布模型

KnoArbor 使用小型发布分支模型。目标是在保持公开历史清晰的同时，允许日常开发快速推进。

分支职责：

- `main`：公开发布分支。它应该始终代表最新公开发布线，或处于可发布状态的文档更新。`main` 必须保持可构建、文档完整，并适合作为 tag 来源。`main` 的非平凡推进必须对应公开版本 tag 和 GitHub release。
- `dev`：下一个 minor 或 patch 版本的日常集成分支。功能变更先合入 `dev`。`dev` 可以比 `main` 更快，但推送前仍应通过常规开发门禁。
- `feature/*`：从 `dev` 切出的聚焦功能或架构分支。
- `fix/*`：从 `dev` 切出的聚焦修复分支；只有紧急公开热修才从 `main` 切出。
- `docs/*`：从 `dev` 切出的文档分支；只有修复公开发布文档时才直接面向 `main`。
- `release/*`：可选的短期 release candidate 稳定分支。当某次发布需要多轮验证时，从 `dev` 切出。

日常开发流程：

1. 新工作从 `dev` 开始，不从 `main` 开始。
2. 使用聚焦分支名，例如 `feature/source-segmentation` 或 `fix/query-context-pack`。
3. 每个提交尽量只处理一个架构问题或用户可感知问题。
4. 合入 `dev` 前运行相关本地检查。
5. 合并或 fast-forward 到 `dev`；不要从 `dev` 打 tag。

发布流程：

1. 在 `dev` 完成功能并通过测试。
2. 冻结 `dev` 作为 release candidate。如果稳定阶段需要多次提交，创建 `release/vX.Y.Z`。
3. 运行 Python 测试、前端构建、前端依赖安全扫描、Playwright UI 冒烟测试、包构建、clean-clone 冒烟测试，以及可用时的真实模型冒烟测试。
4. 运行 `scripts/prepare-release.py <version>`，再整理 `CHANGELOG.md` 和 `docs/releases/v<version>.md`。
5. 将 release candidate merge 或 fast-forward 到 `main`。
6. 只从 `main` 打 tag，例如 `v1.1.0`。
7. 只有 `main` 上的 tag 创建后，才发布包制品。
8. 如果 release notes、版本元数据或热修在 `main` 上变更，需要再把 `main` 合回 `dev`。

如果开发提交误推到上一个公开 tag 之后的 `main`，且当前内容可以发布，优先补齐缺失的版本 tag 和 release。除非提交包含密钥、私有运行时数据或其他发布阻断泄漏，不要重写公开历史。补 tag 后，继续开发回到 `dev`。

热修流程：

1. 只有已发布版本需要紧急修复时，才从 `main` 切出 `fix/<issue>`。
2. 保持改动最小，并运行与改动范围匹配的发布门禁。
3. 合入 `main`，打 patch 版本 tag，然后把 `main` 合回 `dev`。

硬性规则：

- 不要从 `dev`、功能分支或 dirty working tree 直接打发布 tag。
- 不要把运行时 wiki、私有配置、`.env`、本地工作流导出或维护者内部笔记推送到公开分支。
- 公开 release tag 发布后不要重写；只有在用户尚未消费制品前修复发布流程错误时才允许例外。
- `dev` 建立后，不再把 `main` 作为日常开发分支使用。
- 不要让 `main` 长期领先最新公开 tag；出现这种情况时必须做出明确发布决策。

## 规格驱动开发流程

大于孤立修复的变更应使用 [`specs/`](../../specs/README.md)。当变更影响公开契约、架构边界、来源 connector、语义契约、流程行为、自动维护或发布关键体验时，需要创建或更新功能规格。

推荐流程：

1. 从路线图主题或用户问题出发。
2. 创建或更新 `specs/<feature>/requirements.md`。
3. 在 `specs/<feature>/design.md` 中定义所属层、契约、数据流和被拒绝的替代方案。
4. 在 `specs/<feature>/tasks.md` 中跟踪实现状态。
5. 在 `specs/<feature>/verification.md` 中定义自动检查和手动验收。
6. 按规格实现代码和测试。
7. 将稳定的用户可见行为沉淀到 `docs/` 和发布说明中。

规格不是第二套路线图，也不复制长期文档。它是 `docs/ROADMAP.md`、架构边界、代码实现和验证之间的实现桥梁。

## 目录结构

- `src/knoarbor/`：Python 核心服务、CLI、API 和流程实现。
- `web/`：React + Vite 管理控制台源码。
- `docs/`：公开文档。
- `integrations/skills/`：通用 AI 工具技能说明。
- `vaults/`：运行时知识库集合目录，默认不提交。

## 设计原则

项目内部工程规划文档不会进入公开发布包。公开贡献请遵循本文档、[CONTRIBUTING.md](../../CONTRIBUTING.md) 和 [架构设计](ARCHITECTURE.md) 中的边界约定。

简版原则：

- 优先通过清晰架构减少兜底策略。
- Ingest、Lint、Query 的输入输出边界应稳定。
- 语义智能体、执行器、writer、API、CLI 和 UI 不互相代偿职责。
- 自动维护操作必须保留报告和台账。
- 不提交 API Key、个人知识库内容或运行时 Wiki。

## Connector 开发检查表

新增资料来源 connector 属于来源层变更。如果 connector 会改变公开能力元数据或来源行为，需要使用当前 [1.3 Source Ecosystem 规格](../../specs/1.3-source-ecosystem/requirements.md)。

检查表：

1. 在 `SourceConnector` 协议后实现 `discover`、`fetch` 和 `to_document`。
2. 在 `connectors/registry.py` 注册 connector。
3. 通过 `capabilities()` 或默认推断声明能力元数据：
   - connector 名称和版本；
   - 输出的 `source_types`；
   - `settings_schema`；
   - checkpoint、分段提示和外部服务标志。
4. 来源特定解析留在 connector 内部。不要把 connector 分支写进 ingest 语义 prompt、页面 writer 或 API route。
5. 在 checkpoint、segmentation、relation planning 或 drafting 前输出标准 `SourceDocument`。
6. 为 discovery、normalization、能力元数据和异常输入添加 connector 测试。
7. 只有公开 connector 行为变化时，才更新 API/CLI/config 文档。

合入 connector 相关工作前，至少运行：

```bash
uv run python -m unittest tests.test_connector_contracts tests.test_source_pipeline tests.test_cli tests.test_api_surface
uv run python scripts/check-doc-links.py
```

## 前端设计基线

KnoArbor 控制台应该像成熟的知识工作台，而不是装饰性首页或原始管理后台。

UI 贡献应遵循这些规则：

- 保持界面安静、适合重复操作，并在长时间流程运行时保持视觉稳定。
- 优先使用白色内容面、克制的绿色强调、细边框和紧凑字体，避免营销式大面板。
- 卡片只用于离散对象，例如报告、运行记录、来源记录、页面预览和重复列表项。避免装饰性卡片嵌套。
- 页面头部保持紧凑。主要工作流内容应尽量出现在诊断和历史记录之前。
- 避免径向光斑背景、装饰性圆球、单色渐变主题和过大的 hero 字体。
- 修改全局 CSS 后应使用截图或 Playwright 冒烟检查。至少检查总览、运行监控、资料来源、知识库、运行报告和设置页。
- 不要把内部状态码作为主界面文案。应映射为用户可读标签，原始值只放在详情或报告里。
- 图标用于辅助扫描，风格保持一致。除非侧边栏折叠，否则图标不应替代必要文字标签。
