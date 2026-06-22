# 展示导览

KnoArbor 会把 Markdown 笔记、AI 对话记录和已解析文档编译成本地 Markdown Wiki，让这些内容可以被查看、维护，并被其他 AI 工具查询复用。

它不是另一个聊天入口，而是一个知识引擎：

```text
资料来源 -> 知识编译 -> 可维护 Wiki -> 校验维护 -> 查询上下文 -> 宿主 AI
```

## 产品快照

本地控制台用于查看运行就绪状态、启动流程、浏览报告和探索页面关系。

### 总览

![KnoArbor 控制台总览](../assets/knoarbor-console-overview.png)

在启动流程前查看服务就绪状态、知识库健康度、页面数量和推荐下一步。

### 资料来源

![资料来源页面](../assets/knoarbor-console-sources.png)

查看已启用的来源连接器，并理解 raw 输入如何进入统一的知识编译流程。

### 运行监控

![运行监控页面](../assets/knoarbor-console-runs.png)

跟踪长时间运行的知识编译、校验维护和查询流程，包括队列状态、心跳、取消和近期运行记录。

### 知识库浏览

![知识库浏览页面](../assets/knoarbor-console-wiki.png)

浏览生成后的 Wiki 页面，查看 frontmatter 元数据、出站链接、反向链接，并从运行结果直接打开相关页面。

### 知识查询

![知识查询页面](../assets/knoarbor-console-query.png)

检索 Wiki 页面、摘录、来源线索和上下文包，供宿主 AI 继续生成最终回答。

### 运行报告与知识图谱

![运行报告页面](../assets/knoarbor-console-reports.png)

查看可读的运行报告。

![知识图谱页面](../assets/knoarbor-console-graph.png)

检查生成后的知识网络。

## 它会生成什么

KnoArbor 会把页面写入一个普通的本地 Markdown 工作区：

- `pages/`：面向 Obsidian 的干净 Wiki 根目录。需要在 Obsidian 中查看时，打开这个目录。
- `pages/sources/`：来源摘要页面，说明某个原始资料贡献了什么内容。
- `pages/<slug>.md`：维护后的知识页面。页面身份元数据记录 `page_kind`、`role`、`facets`、`canonical_path` 和 `legacy_paths`。
- `pages/_views/`：按概念、实体、流程、对比、开放问题和来源审计生成的浏览视图。
- `raw/`：不可变的原始资料或标准化后的资料副本。
- `maintenance/`：人类可读的运行报告。
- `.knoarbor/`：机器状态、索引、账本、锁和运行记录。

`pages/concepts/` 等旧 typed 目录在迁移期仍可读取，但新知识页面写入统一页面命名空间。最终结果是一个可追溯的知识网络：知识页面连接来源摘要，来源摘要指向原始资料，查询阶段返回可供宿主 AI 使用的证据。

## 端到端流程

### 1. 连接资料来源

当前支持：

- Markdown 笔记。
- Codex JSONL 会话。
- Hermes 会话。
- OpenClaw 会话。
- Claude Code 对话记录。
- 本地通用 JSONL 或 SQLite 聊天记录。
- 通过用户自配 MinerU 兼容预处理器处理的非 Markdown 文件。

连接器只负责把输入标准化为 `SourceDocument`，不会决定页面类型，也不会直接写 Wiki。

### 2. 编译知识

Ingest 会对长资料分段，抽取稳定知识，规划页面操作，生成草稿，评审草稿，写入通过审核的页面，并记录报告。

这样可以避免长对话或大文档被压成一个过大的页面。

### 3. 维护 Wiki

Lint 会检查结构、链接、来源链、图谱健康度和内容质量候选项。它可以自动应用通过评审的确定性和语义维护操作，并保留报告和验证结果。

### 4. 供宿主 AI 查询

Query 会返回排序后的页面、摘录、关联上下文、来源线索、追踪信息和上下文包。KnoArbor 不负责生成最终聊天回答；Codex、Hermes、OpenClaw、Claude Code 或本地 CLI 可以自行决定如何使用这些证据。

## 它和普通 RAG 有什么不同

普通 RAG 往往在回答时检索原始切块。KnoArbor 会先把资料编译成可长期维护的 Wiki 页面，再进行查询。

| 维度 | 普通 RAG | KnoArbor |
| --- | --- | --- |
| 主要产物 | 切块索引 | 可维护 Markdown Wiki |
| 来源处理 | 检索原始切块 | 保留 raw source 和 source digest |
| 知识形态 | 查询时片段 | 有类型、有链接的稳定页面 |
| 维护方式 | 通常隐式 | 显式 lint、报告和验证 |
| 人类可检查性 | 依赖应用 | 可直接用编辑器或 Obsidian 打开 `pages/` |

后续仍然可以引入 RAG 作为检索后端。KnoArbor 的第一目标是让知识本身可检查、可维护。

## 演示时可以展示什么

可以用内置 Agent Loop 示例做一次短演示：

```bash
uv run knoar init --vault ./vaults/default
mkdir -p vaults/default/raw/notes
cp examples/agent-loop.md vaults/default/raw/notes/agent-loop.md
uv run knoar ingest --connector markdown --write
uv run knoar lint --mode structural
uv run knoar query "Agent Loop 是什么？"
uv run knoar serve
```

然后打开：

```text
http://127.0.0.1:8000
```

建议展示：

- 总览：运行状态和推荐下一步。
- 资料来源：已启用输入来源。
- 运行：实时流程状态和心跳。
- 运行报告：可读的 ingest、lint、query 报告。
- 知识图谱：页面之间的链接关系。
- 知识查询：返回的证据和上下文包。

## 当前边界

KnoArbor 目前聚焦本地优先、单用户使用：

- 不提供托管 SaaS。
- 不强制依赖数据库。
- 不内置 MinerU 或文档解析模型权重。
- 不替代宿主 AI 的最终回答生成。
- 小规模个人知识库不强制使用向量检索。

这些边界让第一个公开版本更容易理解、复现和在个人电脑上运行。
