# 开发说明

## 本地环境

```bash
uv sync
cd renderer
npm install
npm run build
```

## 常用检查

```bash
uv run python scripts/plan-affected-validation.py
```

使用 `--run` 执行机械选择的子集，再依据实际依赖闭包补充 owner 与 direct-consumer
focused tests。`scripts/dev-check.sh` 是广覆盖集成/发布节点，不是每个改动的默认命令。
涉及模块所有权或跨层依赖时，运行 `uv run python scripts/check-architecture.py`。

测试命令和层次由[测试与质量门禁](TESTING.md)负责；发布决策使用
[发布前审查清单](RELEASE_CHECKLIST.md)。本文不复制单项门禁。

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

renderer 构建产物位于被忽略的本地目录 `renderer/dist`。所有运行时知识库内容都属于用户本地数据。

## 分支与发布模型

`main` 是公共集成与发布分支，所有可复用能力优先在这里落地。私有
`SieArbor` 产品线只在下游吸收已接受的公共变更，不能反向合入公共历史。

- 聚焦工作从最新 `main` 开始，需要隔离时使用 `codex/*`、`feature/*`、
  `fix/*` 或 `docs/*` 分支。
- 每个提交只处理一个 owner 或用户可见问题，affected validation 通过后再合回
  `main`。
- 生产 tag 只能从干净的 `main` checkout 创建，使用 `vX.Y.Z` 命名空间。
- 发布候选先运行 `scripts/release-check.sh`，准备 changelog 与
  `docs/releases/vX.Y.Z.md`，再按桌面生命周期和发布流程完成构建、签名与打包。
- 紧急修复从已发布的 `main` commit 分支，并在 patch release 后回到 `main`。

不得重写已被用户消费的 release tag，也不得推送运行时 vault、私有配置、`.env`、
本地工作流导出或维护者内部笔记。Dirty working tree 不能作为发布来源。

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

## 开发方法

实质性改动使用 [`specs/README.md`](../../specs/README.md) 定义的最轻有效 SDD：
先定位已接受 owner，跨层契约变更先更新规格，再在 owning boundary 实现，最后用测试、
文档和连贯提交收口。

`integrations/skills` 只保存可分发的 Host AI 产品集成 Skill。

## Web Console

当前前端位于 `renderer/`。使用其 npm scripts 完成开发启动、构建、i18n key
校验和 Playwright smoke。页面通过 typed API client 调用本地 Python service，
不在组件中重写业务策略。

## Package Build

Python 包使用 `uv build`；桌面包由 `desktop/` 的构建脚本组合 renderer 和
Python runtime。构建产物不提交源码树，发布前通过 clean-clone smoke 验证。

首次构建桌面端前，需要分别安装 renderer 和 desktop 依赖：

```bash
cd renderer && npm install && cd ..
cd desktop && npm install && cd ..
```

打包或安装前必须盘点已安装副本、运行进程、用户资料、外部知识库和构建残留。
构建清理、替换应用、本地资料重置和外部知识库删除必须作为相互独立、明确选择的操作。

完成盘点后，可在仓库根目录构建未签名的 macOS 桌面应用：

```bash
npm run pack:mac
```

桌面打包命令是自包含入口：每次都会先删除旧的可再生打包产物，再重新构建
renderer、内置 Python service、Electron main/preload，最后调用桌面打包器。
该流程不依赖已有构建产物；新产物保留在已忽略的构建目录中，不进入 Git。打包不隐含
删除资料或安装应用；系统中只应保留一个经过明确验证的
`/Applications/KnoArbor.app`。

## 目录结构

- `src/knoarbor/`：Python 核心服务、CLI、API 和流程实现。
- `renderer/`：React + Vite 桌面 renderer 源码。
- `docs/`：公开文档。
- `.codex/skills/`：项目开发和维护 Skill 的唯一权威目录。
- `integrations/skills/`：可分发的 Host AI 产品集成 Skill。
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
5. 在 immutable input admission、segmentation、semantic extraction 或事实发布前输出标准 `SourceDocument`。
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

## Release Notes

版本发布说明位于 `docs/releases/v<version>.md`，历史版本保持当时行为，不按
当前实现重写。开发 checkout 的包版本可以领先于最近公开 release；完成
CHANGELOG、release note 和发布门禁后才视为已发布版本。
