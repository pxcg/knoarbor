# KnoArbor

[English](README.md) | [简体中文](README.zh-CN.md)

<p align="center">
  <img src="docs/assets/knoarbor-logo.svg" alt="KnoArbor logo" width="112" height="112">
</p>

<p align="center">
  <a href="LICENSE"><img src="https://img.shields.io/badge/license-Apache--2.0-blue.svg" alt="License"></a>
  <img src="https://img.shields.io/badge/python-3.12%2B-3776AB.svg" alt="Python 3.12+">
  <img src="https://img.shields.io/badge/status-2.2.1%20desktop%20release-0f766e.svg" alt="2.2.1 desktop release status">
  <a href="docs/zh/QUICKSTART.md"><img src="https://img.shields.io/badge/docs-quickstart-111827.svg" alt="Quickstart"></a>
</p>

KnoArbor 是一个 AI 原生 Wiki 引擎，将多源信息编译成可追溯、可维护的知识网络，让零散的知识像树一样生长。

KnoArbor 提供一层长期知识基础设施，为 Hermes、Codex、Obsidian、本地 CLI 工作流和未来 AI 助手提供可积累、可维护、可查询的知识层。

```text
原始资料 -> 知识编译 -> Markdown Wiki -> 校验维护 -> 查询上下文
```

## 快速了解

| 模块 | KnoArbor 提供什么 |
| --- | --- |
| 输入 | Markdown 笔记、AI 聊天记录、通用聊天日志，以及可选 MinerU 预处理后的富文档 |
| 输出 | 本地 Markdown Wiki，包括维护后的知识页、来源审计页、raw 附件、运行报告、账本和图索引 |
| 使用方式 | 桌面应用、CLI、FastAPI、本地管理控制台，以及宿主 AI skill 模板 |
| 运行模型 | 本地优先、单用户、文件型多知识库，带队列、文件锁、断点和报告 |

## 为什么需要 KnoArbor

很多 AI 知识工作流要么反复搜索原始文件，要么让对话内容沉没在越来越长的聊天记录里。KnoArbor 采用不同的方式：

- 保留不可变的原始资料；
- 把有价值的内容编译成可维护的 Wiki 页面；
- 从生成页面追溯到来源摘要和原始资料；
- 对 Wiki 的结构、链接、来源链和质量进行校验维护；
- 查询已维护的 Wiki，为宿主 AI 返回证据和上下文。

这让 Wiki 成为可复用的知识产物，而不是一次性的检索结果。

## 功能特性

- **本地优先知识库**：生成页面存放在普通 Markdown 文件夹中，可以直接用 Obsidian 或编辑器打开。
- **知识编译流程**：把支持的来源转换为 `source_document.v1`，抽取知识、规划页面操作、评审草稿、写入页面并记录报告。
- **校验维护流程**：扫描确定性问题，诊断结构、溯源和质量问题，评审维护动作，并自动应用通过审核的修复。
- **知识查询流程**：返回排序页面、摘录、来源线索、图谱上下文和可供外部 AI 使用的上下文包。
- **Wiki 对话**：基于已维护 Wiki 页面生成带引用的回答，支持来源预览和会话历史。
- **来源溯源**：区分 raw source、source digest 和生成知识页面。
- **多知识库配置**：在一份配置中管理多个命名本地知识库，并支持单库或多库查询。
- **模型适配**：支持 DeepSeek、OpenAI、OpenRouter、LM Studio、vLLM 兼容端点，以及 Ollama 原生端点。
- **桌面应用、CLI、API 和本地控制台**：有发布包时优先使用桌面应用；源码运行时也可以通过终端、本地 HTTP API 或内置 Web 控制台使用。
- **Skill 集成**：提供通用本地 Wiki skill 模板，方便接入支持本地技能的 AI 工具。

## 产品导览

桌面应用内嵌同一套本地控制台。源码运行时，本地控制台也使用同样的核心工作区：Chat 用于向已维护 Wiki 提问，Flows 用于知识编译/校验/查询流程，Knowledge 用于页面和图谱检查。

### Chat

在桌面工作区中直接提问，将会话历史保存在本地 vault，并查看回答背后的引用证据。

<p align="center">
  <img src="docs/assets/knoarbor-desktop-chat.png" alt="KnoArbor 桌面端对话工作区" width="920">
</p>

### Flows

在同一个操作界面中启动和监控知识编译、校验维护、查询、报告和 token 分析流程。

<p align="center">
  <img src="docs/assets/knoarbor-desktop-flows.png" alt="KnoArbor 桌面端流程工作区" width="920">
</p>

### 知识图谱

以页面关系浏览已维护 Wiki，图谱边来自 Wiki 链接和语义页面邻域。

<p align="center">
  <img src="docs/assets/knoarbor-desktop-graph.png" alt="KnoArbor 桌面端知识图谱" width="920">
</p>

## 安装

需要：

- Python 3.12
- [uv](https://docs.astral.sh/uv/)
- 一个 OpenAI 兼容模型供应商，或 Ollama 原生端点

```bash
git clone https://github.com/pxcg/knoarbor.git
cd knoarbor
uv sync
```

完整本地安装部署步骤见 [安装部署](docs/zh/INSTALLATION.md)。

## 快速开始

创建本地配置并初始化知识库：

```bash
uv run knoar first-run --vault ./vaults/default
```

这会创建 `config.yaml`，初始化 `./vaults/default`，并把内置 Markdown 示例复制到
`vaults/default/raw/inbox/notes/agent-loop.md`。

打开 `config.yaml` 或设置页，配置一个模型供应商的 `base_url`、`api_key` 和
`model`。

运行只读诊断：

```bash
uv run knoar doctor
```

将内置示例编译成 Wiki 页面，并运行结构维护：

```bash
uv run knoar ingest --connector markdown --write
uv run knoar lint --mode deterministic
```

启动本地服务：

```bash
uv run knoar serve
```

打开本地控制台：

```text
http://127.0.0.1:8000
```

在控制台中打开对话并提问：

```text
Agent Loop 是什么？
```

也可以从终端查询已维护的 Wiki：

```bash
uv run knoar query "Agent Loop 是什么？"
```

完整命令 `knoarbor` 也可以使用：

```bash
uv run knoarbor --help
```

## 核心概念

KnoArbor 把知识库组织为三层：

```text
vaults/
└── default/
    ├── wiki/
    │   ├── pages/    # 维护后的知识页面
    │   └── sources/  # 来源摘要和溯源审计页面
    ├── raw/
    │   ├── inbox/       # 用户放入的原始资料
    │   ├── normalized/  # 连接器/文档预处理后的标准化结果
    │   ├── assets/      # 提取出的图片、媒体、页面切片和表格
    │   └── sidecars/    # 附件清单和处理器元数据
    ├── maintenance/  # 可读运行报告
    └── .knoarbor/    # 机器状态、索引、账本、锁和运行记录
```

运行时 `vaults/` 目录默认不提交到 git，因为它可能包含私人笔记、原始文档、生成页面和运行记录。只需要在 Obsidian 中查看维护后的 Wiki 时，建议打开 `vaults/default/wiki/pages`。
知识页面统一存放在扁平的 `wiki/pages/` 命名空间。页面含义由正文结构表达：`Summary`、带编号的 `Claims`、`Entities`、三元组 `Relations`、`Evidence`、`Synthesis` 和可选 `Attachments`。来源摘要审计页保存在 `wiki/sources/`；浏览视图由机器索引派生，并由 UI 渲染，不再作为额外 wiki 目录写入。

## 常用命令

### 编译资料

查看已配置来源：

```bash
uv run knoar sources --connector codex --json
```

运行所有已启用来源：

```bash
uv run knoar ingest --write
```

运行单一来源：

```bash
uv run knoar ingest --connector markdown --write
uv run knoar ingest --connector hermes --write
uv run knoar ingest --connector openclaw --write
```

处理单个文件或文件夹：

```bash
uv run knoar ingest --input /path/to/note.md --write
uv run knoar ingest --input /path/to/paper.pdf --write
uv run knoar ingest --input /path/to/folder --write
```

Markdown 文件会直接进入编译流程。文件夹输入默认递归发现 Markdown 文件。PDF、DOCX、PPTX 等非 Markdown 文件需要配置 MinerU 兼容预处理器；如果没有配置或服务不可用，流程会明确失败并提示配置问题。KnoArbor 不重新分发 MinerU 或其模型权重。

### 维护 Wiki

结构化维护：

```bash
uv run knoar lint --mode deterministic
```

语义维护：

```bash
uv run knoar lint --mode semantic
```

语义维护默认会应用通过评审的操作。如需只评审不写入，可加 `--no-apply-reviewed`。

```bash
uv run knoar lint --mode semantic
```

### 查询上下文

```bash
uv run knoar query "Agent Loop 是什么？"
uv run knoar query --json "Agent Loop control patterns"
```

Query 只负责检索上下文和证据，供宿主 AI 使用。需要 KnoArbor 在应用内基于证据生成回答时，请使用 Wiki Chat。

## 当前状态

KnoArbor 处于 2.2 桌面端优先版本线。桌面端壳、源码本地服务、CLI、稳定 HTTP API、内置控制台、多知识库配置和宿主 AI skill 模板，目标是作为单用户本地知识引擎一起使用。

已经实现：

- Markdown、Hermes、Codex、OpenClaw、Claude Code 和通用聊天记录来源连接器。
- 可选的 MinerU 兼容文档预处理。
- Python Core 中的 ingest、lint、query 流程。
- Wiki Chat，支持基于证据的回答、引用、会话历史、重试和会话入库。
- FastAPI 服务和 CLI 入口。
- 随 Python 包分发的本地 React 控制台。
- 运行时 Wiki 初始化、机器索引、队列、文件锁、账本、报告和断点。
- 多知识库配置、查询、运行/报告列表和 skill drilldown。

当前本地优先版本暂不包含：

- 托管 SaaS 部署。
- 内置向量数据库。
- 内置 MinerU 模型或运行时。
- 打包好的外部工作流模板。

## 配置

模型供应商配置在 `config.yaml`：

```yaml
models:
  default_provider: deepseek
  default_max_tokens: 30000
  request_timeout_seconds: 600
  providers:
    deepseek:
      base_url: https://api.deepseek.com
      api_key:
      model: deepseek-v4-flash
```

当前模型供应商通过 ModelGateway 使用 OpenAI 兼容 Chat Completions API。本地 Ollama 或 vLLM 端点可以留空 `api_key`。更多配置见 [配置说明](docs/zh/CONFIGURATION.md)。

## 架构

KnoArbor 是一个工作流优先的系统，语义智能体保持窄职责边界：

```text
Connectors
  -> Source Pipeline
  -> Semantic Contracts
  -> Write Pipeline
  -> Lint Maintenance
  -> Query Retrieval
```

主要包结构：

```text
src/knoarbor/
├── entrypoints/       # FastAPI app 和 routers
├── services/          # API 到 pipeline 的适配层
├── pipelines/         # ingest、lint、query、write 编排
├── connectors/        # 来源发现和转换
├── semantic/          # prompts、contracts、模型客户端
├── storage/           # vault、index、paths、ledgers、writer
├── retrieval/         # search、links、Markdown 提取
├── maintenance/       # lint scan 和操作执行
├── presenters/        # API/CLI/skill 响应整理
└── core/              # schemas、config、redaction、通用规则
```

详细设计见 [架构设计](docs/zh/ARCHITECTURE.md) 和 [溯源设计](docs/zh/PROVENANCE_DESIGN.md)。

## 文档

- [展示导览](docs/zh/SHOWCASE.md)
- [快速开始](docs/zh/QUICKSTART.md)
- [配置说明](docs/zh/CONFIGURATION.md)
- [命令行](docs/zh/CLI.md)
- [接口说明](docs/zh/API.md)
- [API 兼容性](docs/zh/API_COMPATIBILITY.md)
- [核心概念](docs/zh/CONCEPTS.md)
- [故障排查](docs/zh/TROUBLESHOOTING.md)
- [备份与恢复](docs/zh/BACKUP_AND_RECOVERY.md)
- [架构设计](docs/zh/ARCHITECTURE.md)
- [溯源设计](docs/zh/PROVENANCE_DESIGN.md)
- [路线图](docs/zh/ROADMAP.md)
- [测试与质量门禁](docs/zh/TESTING.md)
- [开发说明](docs/zh/DEVELOPMENT.md)
- [贡献指南](CONTRIBUTING.md)
- [支持说明](SUPPORT.md)
- [更新日志](CHANGELOG.md)
- [安全说明](SECURITY.md)

## 开发

运行当前必需检查：

```bash
scripts/dev-check.sh
```

发布候选版本使用：

```bash
scripts/release-check.sh
```

当真实 DeepSeek 兼容供应商可用时，也运行：

```bash
scripts/live-release-candidate-smoke.sh
```

## 安全与隐私

KnoArbor 面向本地优先使用。原始资料和生成页面可能包含私人信息，不要提交运行时知识库数据。

默认忽略：

- `config.yaml`
- `config.local.yaml`
- `wiki/`
- `.local-dev/`
- `.venv/`
- `.uv-cache/`

安全问题请参考 [SECURITY.md](SECURITY.md)。

## Star History

<a href="https://www.star-history.com/#pxcg/knoarbor&Date">
  <img src="https://api.star-history.com/svg?repos=pxcg/knoarbor&type=Date" alt="KnoArbor star history" />
</a>

## License

KnoArbor 使用 [Apache License 2.0](LICENSE)。

```text
Copyright 2026 KnoArbor contributors
```

见 [NOTICE](NOTICE) 和 [THIRD_PARTY_NOTICES.md](THIRD_PARTY_NOTICES.md) 了解归属、第三方图标和项目标识说明。Apache-2.0 许可证不授予 KnoArbor 名称的商标权。
