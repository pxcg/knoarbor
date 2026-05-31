# KnoArbor 系统架构

本文档是 KnoArbor 的公开架构概览，解释稳定系统边界，不展开内部规划细节。

KnoArbor 是一个 AI 原生 Wiki 引擎，将多源信息编译成可追溯、可维护的知识网络，让零散的知识像树一样生长。

```text
raw source -> source document -> ingest -> wiki pages -> lint -> query context
```

## 设计目标

KnoArbor 不是聊天记录归档，也不是原始文档搜索工具。

它围绕四个原则设计：

- 保持 raw source 不可变；
- 将有价值内容编译成稳定 Markdown Wiki 页面；
- 持续维护页面结构、链接、溯源和质量；
- 从维护后的 Wiki 中查询，而不是每次都重新推理原始文件。

核心运行模型是：

```text
一次编译，持续维护，从维护后的产物中查询
```

## 架构层级

新增能力应先归属到一个架构层级，避免工作流、模型调用、存储写入和运行观测互相泄漏。

| 层级 | 负责 | 不应负责 |
| --- | --- | --- |
| 入口层 | CLI、FastAPI、Web UI、Skill、外部工作流适配器。 | Prompt 契约、页面写入策略、来源分类或 vault 修改规则。 |
| Pipeline | `ingest`、`lint`、`query` 流程编排。 | 底层模型 HTTP 调用、文件渲染细节或 UI 状态。 |
| Connector / Source | 将 Markdown、聊天记录、文档和未来外部系统转换成 `SourceDocument`。 | Wiki 页面规划或页面生命周期治理。 |
| Document Processing | 在共享 ingest 前把富文档转换成 Markdown。 | 知识对象分类或 Wiki 写入。 |
| Semantic | 窄功能 LLM 契约、prompt、schema 校验和语义步骤。 | 读取本地文件、写页面、执行操作或管理进度。 |
| Model Client | OpenAI-compatible 调用、JSON mode、timeout、retry 和 token 指标。 | ingest/lint/query 的业务决策。 |
| Storage / Writer | Markdown 渲染、patch 应用、索引更新、checkpoint 和底层 vault 文件原语。 | 判断某个知识对象是否应该存在，或汇总报告。 |
| Retrieval / Index | 页面元数据、链接图谱、相关扩展、query context pack 和未来 BM25/vector provider。 | 修改 Wiki 页面。 |
| Maintenance | 确定性扫描、语义 lint 候选、operation 执行和验证。 | 原始来源摄入或审计制品归属。 |
| Runtime | 队列、run monitor、heartbeat、事件目录、取消、文件锁和日志。 | 业务语义，或 SemanticRunner 之外的重试决策。 |
| Config / Policy | 运行路径、模型供应商、connector、隐私、执行限制和功能开关。 | 配置不可见的隐藏行为。 |
| Report / Audit | 人可读报告、机器 ledger、失败运行报告、查询记录、运行摘要和报告渲染。 | 页面正文事实来源或维护操作决策。 |

## 系统层

### 来源层

来源层保留原始材料和来源派生的标准化文档。

常见运行目录：

- `wiki/raw/chats/`：Hermes、Codex、OpenClaw、Claude Code 等 AI 工具会话。
- `wiki/raw/notes/`：导入的 Markdown 笔记。
- `wiki/raw/articles/`：网页或文章导出。
- `wiki/raw/documents/originals/`：PDF、DOCX、PPTX、XLSX、手册、课程资料等富文档原件。
- `wiki/raw/documents/markdown/`：由 MinerU-compatible 等确定性预处理器生成的 Markdown。
- `wiki/raw/transcripts/`：会议、音频或视频转录。
- `wiki/raw/datasets/`：结构化数据集。
- `wiki/raw/media/`：原始图片和媒体。

规则：

- LLM 工作流不覆盖 raw source。
- 来源身份通过路径和内容哈希跟踪。
- 聊天来源通过 checkpoint window 只处理新增轮次。
- 富文档先转换为 Markdown，再进入共享 ingest 路径。

### 知识层

知识层保存维护后的 Wiki 页面：

- `sources/`：来源摘要页面。
- `entities/`：人物、组织、产品、项目、工具、标准、地点、数据集等命名对象。
- `concepts/`：方法、架构、模式、原则和技术实践。
- `comparisons/`：以比较为核心的页面。
- `queries/`：尚未成熟为稳定实体、概念或比较页面的留存问答。
- `claims/`：原子化、有证据支撑的声明。
- `timelines/`：事件序列。
- `workflows/`：可复用流程和操作指南。
- `maintenance/`：报告、checkpoint、ledger 和维护制品。

规则：

- 每个 Wiki 页面应代表一个稳定知识对象。
- 页面边界比保留原始来源形状更重要。
- 优先创建少量有用页面，而不是大量薄页面。
- `maintenance/` 不是常规知识目标。

### 索引层

索引层为智能体和查询流程提供路由与检索上下文。

当前实现：

- 生成的 `wiki/index.md` 作为人类可读路由目录和调试制品；
- 基于本地 Markdown 的标题、路径、标签、摘要、Key Points、标题层级、正文关键词和相关页做检索；
- 为宿主 AI 工具返回 query context pack。

长期方向：

```text
IndexProvider
  -> MarkdownIndexProvider
  -> BM25 / SQLite FTS provider
  -> Vector provider
  -> Hybrid provider
```

工作流代码应依赖稳定 retrieval payload，而不是依赖 `index.md` 的物理格式。

### 治理层

治理层记录 Wiki 为什么发生变化。

包括：

- checkpoint；
- ingest report；
- lint report；
- failed-run report；
- operation ledger；
- quality 和 verification 输出。

自动维护必须可检查。一次页面更新应能看到来源、理由、风险信号和执行结果。

失败运行同样是审计事件。如果 ingest、lint 或 query 在正常结果生成前失败，只要能确定 vault 路径，service 层就应该写入失败报告和 ledger。Runtime queue 只记录运行状态；Audit 层负责用户可读的失败制品。

## 主流程

### Ingest / 知识编译

目标：把新增或变化的来源材料转换成协调的 Wiki 页面操作。

```text
connector discovery
  -> source normalization
  -> privacy redaction
  -> checkpoint window
  -> source segmentation
  -> source normalize agent
  -> candidate page retrieval
  -> relation planning
  -> candidate page materialization
  -> draft compilation
  -> draft review
  -> deterministic quality gate
  -> ingest write policy
  -> wiki write
  -> scoped deterministic lint
  -> checkpoint commit
  -> report and ledger
```

职责：

- connector 将来源特定材料标准化为共享 `SourceDocument`。
- ingest 只决定当前 source 如何进入 Wiki。
- ingest 支持 `create`、`update`、`skip`。
- merge、archive、delete、rename 和跨页面生命周期治理属于 lint/maintenance。
- 长来源切分位于 `SourceDocument` 标准化之后、语义 ingest 之前。
- 分段来源按 segment 处理，再在 source/window 边界聚合写入、报告和提交 checkpoint。
- `IngestWritePolicy` 在写入前执行 source/window 级不变量：同一 raw source 在同一批 ingest 中最多创建一个 source digest。
- ingest 默认不做宽泛词面 Related Pages 扫描，只保留 source digest 与同源生成页面之间的确定性 provenance 链接。
- `ingest-file` 是单文件边界：Markdown 直接进入共享 ingest；非 Markdown 必须先经过已配置的 MinerU-compatible 预处理器，缺少预处理器时显式失败。

实现边界：

- `pipelines/ingest.py` 是编排外壳：connector 执行、segment 执行、写入/scoped lint/report 协调和 checkpoint 提交。
- `pipelines/ingest_checkpoint.py` 负责 checkpoint 计划和提交载荷。
- `pipelines/source_segmentation.py` 负责分段计划和 source-window 切分边界。
- `pipelines/ingest_context.py` 负责候选页面检索和 materialization。
- `pipelines/ingest_metrics.py` 负责 source/segment 指标、脱敏统计聚合和语义 token 统计。
- `pipelines/ingest_lifecycle.py` 负责从 checkpoint 状态生成 missing/moved source 生命周期候选。
- `pipelines/ingest_quality.py` 与 `pipelines/ingest_write_policy.py` 负责写入前校验和写入不变量。

### Lint / 校验维护

目标：维护已经生成的 Wiki 页面。

```text
scan
  -> diagnose
  -> review / policy
  -> execute
  -> verify / rescan
  -> report and ledger
```

职责：

- 扫描页面结构、链接、溯源和契约问题。
- 诊断结构、溯源、质量、freshness 和图谱候选。
- 审核必要性、正确性、完整性、风险、置信度和执行器适配性。
- 只执行已审核 operation。
- 高风险 refresh、merge/split、conflict 和外部事实工作保持 queue/report-only，除非已有明确审核执行器支持。

实现边界：

- `lint_collection` 负责页面收集、wikilink lookup、图谱健康度和 scoped page 扩展。
- `lint_scanners` 负责确定性扫描规则和 issue 生成。
- `lint_candidates` 负责 scan page 预览、质量候选和 freshness 候选评分。
- `wiki_lint` 是公开编排门面，只保留 scan、candidate selection、safe fixes 和旧版 lint report 入口。

用户可见模式：

- `structural`：结构、链接和溯源维护。
- `quality`：聚焦语义质量审查。
- `full`：在一次运行中组合结构和质量维护。

### Query / 知识查询

目标：为宿主 AI 返回 Wiki 上下文，不生成最终聊天回答。

```text
query
  -> page retrieval
  -> related expansion
  -> excerpts and source pointers
  -> context pack
  -> trace and gap signals
```

职责：

- 返回排序页面、摘录、来源指针、相关上下文和有界 context pack。
- 通过匹配原因、关键词和 trace 解释检索过程。
- 不修改 Wiki 页面。
- 不声称 related 页面比 direct 页面更弱或更强；`match_kind` 只解释检索来源。

## 本地运行基础设施

KnoArbor 是本地优先的 Wiki 引擎，但仍需要明确运行时基础设施。

- **机器索引层**：面向程序读取的页面、链接、来源和检索元数据，区别于人类可读的 `index.md`。
- **单机队列**：`LocalRunQueue` 是第一版队列后端，按 vault 串行化运行，避免写入重叠。恢复失败项时创建新的 run，而不是修改已完成 run。
- **运行日志**：诊断日志写入 `.knoarbor/logs/knoarbor.log`，与用户报告、ledger 和 run events 分离。
- **文件锁**：本地 vault 修改使用 `.knoarbor/locks/vault.write.lock`，保护页面、索引、日志、checkpoint、ledger 和维护写入。
- **语义重试策略**：模型重试属于 `SemanticRunner`，不散落在 ingest、lint、API route 或 prompt 专用清洗逻辑中。runner 只重试配置在错误码白名单中的错误。
- **受控并发**：dry-run/preflight ingest 可以有界并发处理 source；写入型 ingest 在同一个 vault 内保持串行，确保页面写入和 checkpoint 一致。
- **事件模型**：run events 是进度事实，冻结事件目录位于 `knoarbor.runtime.events`。
- **应用缓存**：第一版不需要独立应用缓存层；后续页面解析、图谱和 query index 可以缓存，但 checkpoint、lint decision、ledger 和 report 不能被缓存替代。
- **供应商 prompt cache**：prompt caching 由模型供应商负责。语义契约把长且稳定的指令和输出 schema 放在 system message，动态 source/wiki payload 放在后续 user message。runner 不应在稳定契约 prompt 前注入时间戳、run id、本地路径等易变内容。供应商返回 cached prompt tokens 或 DeepSeek cache hit/miss tokens 时，KnoArbor 会记录到运行指标中。
- **Docker**：Docker 是部署适配层，不是核心架构层。

## 读取 API 边界

生成后的 Wiki 页面拥有独立稳定的读取边界：

```text
storage / retrieval metadata
  -> WikiPagesService
  -> /wiki/pages, /wiki/page, /wiki/backlinks
  -> UI, skills, CLI wrappers, external clients
```

UI 不应拥有另一套页面读取逻辑。UI 可以拥有配置表单、项目文档预览、报告列表渲染等界面专用适配器；但 Wiki 页面列表、页面详情和反向链接属于 `wiki` API/service 边界。

## 智能体边界

KnoArbor 使用窄功能语义契约，而不是自治多智能体团队。

- Source Normalize Agent：把 `SourceDocument` 转换成 `knowledge_extract.v1`。
- Relation Agent：规划页面级 create/update/skip 操作。
- Draft Compile Agent：为已规划操作生成协调草稿和 patch。
- Ingest Draft Review Agent：在 ingest 写入前审查写入安全。
- Lint Diagnose Agents：把扫描和质量证据转换为维护候选。
- Maintenance Review Agent：批准、推迟或拒绝维护候选。
- Query 以检索为主，当前不使用回答生成智能体。

智能体不读文件、不写页面、不执行 operation，也不修复畸形上游输出。Python Core 负责编排、写入、ledger 和报告。

## API 与适配器边界

- Python Core 是长期执行路径。
- FastAPI 是 Python Core 的 HTTP 适配器。
- CLI 是同一批 pipeline 的执行适配器。
- 外部工作流工具是可选适配器，应调用稳定 pipeline API。
- UI 是配置、运行、报告、文档和图谱检查的管理控制台，不是独立工作流引擎。

## 前端边界

Web UI 是建立在公开 API 和 UI 专用 HTTP 适配器之上的本地管理控制台。它需要提供清晰的产品交互，但不应成为后端业务逻辑的第二套实现。

职责：

- 展示配置、来源状态、运行任务、报告、Wiki 页面、图谱数据和项目文档；
- 通过稳定核心 API 运行流程、读取运行状态、查询上下文和 Wiki 页面；
- 只在配置表单、诊断摘要、内置文档和报告预览等界面专用场景调用 `/ui/api/*`；
- 使用可复用本地组件渲染 Markdown、diff、报告和图谱。

不负责：

- 来源发现、checkpoint、分段、页面 operation 规划、lint 执行、重试策略、vault 写入和报告生成；
- 在已有核心 `/wiki/*` 页面读取 API 时，再实现一套 UI 专用页面解析逻辑；
- 静默修复本应由 Python Core 校验的异常 API payload。

v0.x 阶段，KnoArbor 暂时保留轻量本地组件体系，不引入完整 UI 组件框架。如果表单、菜单、弹窗、表格和报告视图继续膨胀，下一步应有意识地抽取共享 UI primitives，或正式引入小型组件库，而不是继续追加页面级样式补丁。

## 可靠性原则

- 在拥有该行为的层级修复根因。
- 优先使用 schema、契约、validator 和显式 executor，而不是兜底逻辑。
- 不在 writer、router、API、CLI 或 UI 层推断缺失业务决策。
- 自动写入必须进入报告和 ledger。
- 只有 evidence、参数、executor 支持和 verification 清晰时，才新增 operation。

## 相关文档

- [核心概念](CONCEPTS.md)
- [溯源设计](PROVENANCE_DESIGN.md)
- [配置说明](CONFIGURATION.md)
- [开发说明](DEVELOPMENT.md)
