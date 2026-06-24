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
| Model Gateway | 稳定模型边界、ProviderAdapter 选择、OpenAI 兼容调用、Ollama 原生调用、JSON mode、端点检测、retry 和 token 指标。 | ingest/lint/query 的业务决策。 |
| Storage / Writer | Markdown 渲染、patch 应用、索引更新、checkpoint 和底层 vault 文件原语。 | 判断某个知识对象是否应该存在，或汇总报告。 |
| Retrieval / Index | 页面元数据、字段加权 BM25 排序、链接图谱、相关扩展、query context pack 和未来持久/vector provider。 | 修改 Wiki 页面。 |
| Maintenance | 确定性扫描、语义 lint 候选、operation 执行和验证。 | 原始来源摄入或审计制品归属。 |
| Runtime | 队列、run monitor、heartbeat、事件目录、取消、文件锁和日志。 | 业务语义，或 SemanticRunner 之外的重试决策。 |
| Config / Policy | 运行路径、模型供应商、connector、隐私、执行限制和功能开关。 | 配置不可见的隐藏行为。 |
| Report / Audit | 人可读报告、机器 ledger、失败运行报告、查询记录、运行摘要和报告渲染。 | 页面正文事实来源或维护操作决策。 |
| Wiki Chat Agent | 受限的控制台对话循环，围绕 KnoArbor 工具、引用和流程入口回答问题。 | 通用 shell、浏览器、文件、网络自动化或隐藏工作流策略。 |
| Memory | 长期对话偏好、vault 级交互约定、显式记忆候选、召回上下文和记忆事件。 | Wiki 知识页面、raw source 归档、source digest 或任意聊天全文存储。 |

实现说明：

- CLI 保持 `cli.py` 作为入口和统一错误边界。命令注册位于 `cli_commands/parser.py`，命令行为位于 `cli_commands/handlers.py`。
- UI 配置的请求/响应模型位于 `services/ui_config_models.py`；`services/ui_config.py` 负责配置读写、表单转换和诊断。
- 维护验证的编排位于 `maintenance/operation_verification.py`；具体 action 的验证规则位于 `maintenance/operation_verifiers.py`。
- 报告模块通过 `audit/report_formatting.py` 共享基础 Markdown 格式化工具；ingest 和 lint 报告仍各自负责工作流专属摘要。

粒度规则：

- 当一个模块混合多个架构层、包含可单独测试的策略，或迫使调用方引入无关依赖时，应该拆分。
- 当一个模块本质上是内聚的 registry、命令处理集合、验证规则集合或报告渲染器时，可以保持聚合；文件偏长本身不是继续拆分的充分理由。
- 相比大量微小文件，优先保留一个职责清楚、局部 helper 可读的文件。
- 新增子包应表达稳定概念，而不是只为了隐藏一个长函数。

## 系统层

### 来源层

来源层保留原始材料和来源派生的标准化文档。

常见运行目录：

- `vaults/default/raw/chats/`：Hermes、Codex、OpenClaw、Claude Code 等 AI 工具会话。
- `vaults/default/raw/notes/`：导入的 Markdown 笔记。
- `vaults/default/raw/articles/`：网页或文章导出。
- `vaults/default/raw/documents/originals/`：PDF、DOCX、PPTX、XLSX、手册、课程资料等富文档原件。
- `vaults/default/raw/documents/markdown/`：由 MinerU-compatible 等确定性预处理器生成的 Markdown。
- `vaults/default/raw/transcripts/`：会议、音频或视频转录。
- `vaults/default/raw/datasets/`：结构化数据集。
- `vaults/default/raw/media/`：原始图片和媒体。

规则：

- LLM 工作流不覆盖 raw source。
- 来源身份通过路径和内容哈希跟踪。
- 聊天来源通过 checkpoint window 只处理新增轮次。
- 富文档先转换为 Markdown，再进入共享 ingest 路径。

### 知识层

知识层保存维护后的 Wiki 页面，物理位置是 `vaults/default/pages/`。
当你希望在 Obsidian 中打开干净的知识库时，应打开 `vaults/default/pages`，而不是整个 `vaults/default` 运行时工作区：

- `pages/<slug>.md`：维护后的知识页面。
- `sources/*.md`：来源摘要和溯源审计页面。
- UI 浏览视图由 `.knoarbor/index/manifest.json` 和 `.knoarbor/index/graph_index.json` 派生，不再作为 wiki fact 写入物理目录。

知识页面的类型由页面身份元数据和索引 facets 表达：

- `page_kind`：concept、entity、workflow、comparison、timeline、query、note 或 source digest。
- `role`：knowledge page、source digest、generated view 或 report。
- `facets`：用于检索和浏览的多标签，例如 `agent_architecture`、`workflow_pattern`、`claims`、`relations`。
- `canonical_path` 与 `legacy_paths`：迁移期间保持稳定解析的路径身份。

`pages/concepts/`、`pages/entities/` 等旧 typed 目录在迁移期仍可读取，但新知识页写入统一的 flat namespace。来源摘要页仍保留在 `sources/`。

迁移状态：

- 读取路径：flat 页面和旧 typed 页面都可读取。
- 写入路径：新知识页写入 `pages/<slug>.md`。
- 迁移路径：`knoar vaults migrate-namespace` 默认 dry-run，只有显式 `--apply` 才移动旧 typed 页面。
- 安全路径：迁移会先报告冲突，执行后写入带 rollback notes 的维护报告。

人类可读报告保存在 `vaults/default/maintenance/`。运行状态、ledger、checkpoint、lock 和机器索引保存在 `vaults/default/.knoarbor/`。
可审计声明和类型化关系是页面内部结构，并进入机器索引，不再作为独立页面目录。

规则：

- 每个 Wiki 页面应代表一个稳定知识对象。
- 页面边界比保留原始来源形状更重要。
- 优先创建少量有用页面，而不是大量薄页面。
- `maintenance/`、`raw/` 和 `.knoarbor/` 不是常规知识目标。

### 索引层

索引层为智能体和查询流程提供路由与检索上下文。

当前实现：

- 在 `vaults/default/.knoarbor/index/` 下生成机器索引，其中 `manifest.json` 和 `graph_index.json` 是持久图索引边界；
- 保留 `pages.json`、`links.json`、`sources.json`、`search.json` 等兼容 retrieval payload，供当前 UI/query 服务使用；
- 基于本地 Markdown 的标题、路径、entities、summary、claims、relations、标题层级和正文做字段加权 BM25 检索；
- 通过 claim-backed relations、出站 wikilink、反向链接和来源关系做图谱扩展；
- 为宿主 AI 工具返回 query context pack。

长期方向：

```text
IndexProvider
  -> MarkdownIndexProvider
  -> SQLite FTS provider
  -> Vector provider
  -> Hybrid provider
```

工作流代码应依赖稳定 retrieval payload 和 graph index artifact，而不是依赖人工维护的 `index.md`。

### 答案页面选择层

答案页面选择层把已排序的页面候选转换为回答计划。它选择主答案页面、
补充页面、来源页面、延伸阅读和被排除的候选，并记录原因。该层是确定性
逻辑，不调用模型。

选择器位于页面级 BM25/链接扩展之后、context pack 或 chat evidence pack
之前。它是避免 RAG 式噪声的关键边界：召回可以适度放宽，但默认回答只由
被选中的答案承载页面构成。

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

### 记忆层

记忆层保存 Wiki Chat Agent 使用的长期交互偏好。Memory 与 Wiki 页面、Source Digest 分离：

- Wiki 页面记录稳定知识对象；
- Source Digest 记录来源摘要和溯源；
- Memory Record 指导对话界面如何按用户或 vault 偏好使用知识。

记忆文件保存在 `vaults/default/.knoarbor/memory/`：

- `records.jsonl`：append-only 记忆记录；
- `candidates.jsonl`：候选或自动写入的记忆；
- `events.jsonl`：召回和写入事件；
- `profile.md`：可选的人类可读画像摘要。

第一版在模型调用前召回记忆，并只捕获用户明确表达的低风险偏好。推断型会话总结、全局记忆和人工候选审查属于后续扩展。

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
  -> source digest audit projection + atom extraction
  -> source-level aggregation
  -> candidate page retrieval
  -> page planning
  -> claim / relation / evidence closure
  -> deterministic page assembly
  -> page-local prose generation
  -> deterministic write gate
  -> conditional semantic draft review
  -> ingest write policy
  -> wiki write
  -> machine index + atom index
  -> scoped deterministic lint
  -> checkpoint commit
  -> report and ledger
```

职责：

- connector 将来源特定材料标准化为共享 `SourceDocument`。
- source input 区分发现引用（`SourceRef`）、原始状态（`RawSource`）、标准化内容（`SourceDocument`）、处理身份（`SourceFingerprint`）和 checkpoint window；即使来源字节未变化，connector 或 parser 版本变化也会重新进入处理。
- ingest 只决定当前 source 如何进入 Wiki。
- ingest 支持 `create`、`update`、`skip`。
- merge、archive、delete、rename 和跨页面生命周期治理属于 lint/maintenance。
- 长来源切分位于 `SourceDocument` 标准化之后、语义 ingest 之前。
- 分段来源按 segment 处理，再在 source/window 边界聚合写入、报告和提交 checkpoint。
- `IngestWritePolicy` 在写入前执行 source/window 级不变量：同一 raw source 在同一批 ingest 中最多创建一个 source digest。
- source digest 页面是 provenance 审计视图，由 source units、已选择 atoms、写入结果、warning 和 raw 指针生成。它不是普通知识页，也不由页面 draft agent 撰写。
- 普通知识页采用 claims-first 结构：已选择 claims 决定 entities、relations、evidence 和可读 synthesis。
- ingest 默认不做宽泛词面 Related Pages 扫描，只保留 source digest 与同源生成页面之间的确定性 provenance 链接。
- `ingest --input` 是一次性本地输入边界：Markdown 文件和文件夹直接进入共享 ingest；非 Markdown 必须先经过已配置的 MinerU-compatible 预处理器，缺少预处理器时显式失败。

实现边界：

- `pipelines/ingest.py` 是编排外壳：connector 执行、segment 执行、写入/scoped lint/report 协调和 checkpoint 提交。
- `pipelines/ingest_checkpoint.py` 负责 checkpoint 计划和提交载荷。
- `pipelines/source_segmentation.py` 负责分段计划和 source-window 切分边界。
- `pipelines/ingest_semantic.py` 负责语义 ingest 链路：source normalization、atom extraction、候选检索、page planning、page-local prose generation 和 conditional draft review。
- `pipelines/ingest_context.py` 负责候选页面检索和 materialization。
- `pipelines/ingest_postprocess.py` 负责 approval 之后的确定性写入/report/index 边界：写入已批准页面、记录生成页面、更新 atom index，并按配置运行 source-scoped deterministic lint。
- `pipelines/ingest_metrics.py` 负责 source/segment 指标、脱敏统计聚合和语义 token 统计。
- `pipelines/ingest_lifecycle.py` 负责从 checkpoint 状态生成 missing/moved source 生命周期候选。
- `pipelines/ingest_write_gate.py` 与 `pipelines/ingest_write_policy.py` 负责持久化前校验和写入不变量。

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
- 将已审核决策路由到明确执行链路：
  - `supported_by_wiki_operation` -> `WikiOperationPipeline` -> 验证。
  - `supported_by_draft_write` -> 草稿编译 -> `WikiWritePipeline` -> 验证。
  - `supported_by_report_only` -> 携带更完整页面上下文的 deferred retry -> 证据充分后转为 wiki operation 或 draft write；仍不足则保留在报告队列。
  - `supported_by_refresh_request` -> provenance refresh -> 创建 source digest 或修复 source/knowledge 双向链接 -> 复扫。

实现边界：

- `lint_collection` 负责页面收集、wikilink lookup、图谱健康度和 scoped page 扩展。
- `lint_scanners` 负责确定性扫描规则和 issue 生成。
- `lint_candidates` 负责 scan page 预览、质量候选和 freshness 候选评分。
- `WikiLintPipeline` 是内部确定性维护管线，负责 scan、candidate selection、safe fixes 和 lint report 生成。公开调用通过统一 `/lint` API 或 CLI `lint` 命令进入。
- `lint_execution` 负责把审核决策路由到具体执行器，不直接实现 source 解析或页面渲染。
- `provenance_refresh` 负责执行 refresh-request。它只处理 vault 内可解析的本地 raw source，并修复 raw source -> source digest -> generated page 链路。缺失或有歧义的来源继续保留在队列并写入 warning。

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
  -> answer-bearing page bodies plus provenance structure
  -> page-first context pack
  -> trace and gap signals
```

职责：

- 返回排序页面、答案相关页面正文、来源指针、相关上下文和页面优先 context pack。
- 通过匹配原因、关键词和 trace 解释检索过程。
- 不修改 Wiki 页面。
- 不声称 related 页面比 direct 页面更弱或更强；`match_kind` 只解释检索来源。

检索信号：

- title、path、tags、summary、key points、headings 和正文的字段加权 BM25 页面排序。
- 尽量保留技术标识符和中文短语片段作为查询信号。
- 通过出站 wikilink、反向链接、来源关系和图谱邻近度进行相关页扩展。
- 对同源页面和同类型页面给予可解释的图谱相关性加权。
- 面向宿主 AI 组装页面优先 context pack：primary/supporting 页面保留已维护正文，source 页面保留结构化摘要和溯源信息。

### Wiki Chat Agent / 对话

目标：让控制台用户用自然语言询问当前知识库，同时把所有动作限制在
KnoArbor 自有边界内。

```text
chat request
  -> bounded evidence planning loop
  -> guarded KnoArbor tool execution
  -> canonical evidence packages
  -> answer synthesis
  -> answer with citations and evidence trace
```

职责：

- 在管理控制台内综合回答。
- 规划并执行受限的 KnoArbor 工具，例如 `query_wiki`、`read_wiki_page`、
  `reuse_context`、`answer_directly` 和 `finish_answer`。
- 当证据覆盖较弱、缺少主页面或已知页面需要全文细节时，在 `max_turns`
  边界内继续收集证据。
- 通过代码层守卫确保知识类问题使用 Wiki 证据。
- 在模型综合前构建页面优先的标准 evidence pack。
- 向前端展示引用和证据轨迹。
- 按轮次保存每个助手回答自己的引用、工具轨迹、事件、记忆元数据和
  统计信息。
- 把用户明确选择的已保存会话转换为 `knoarbor_chat` source document，
  并通过共享 run manager 排队进入 ingest。

边界：

- `/query` 仍然是面向宿主 AI 的无模型证据检索。
- Chat 不获得任意 shell、浏览器、文件系统或网络工具。
- Chat 不直接写入 Wiki Markdown。
- 工作流行为仍由 ingest/lint service 和 run manager 管理。

## 本地运行基础设施

KnoArbor 是本地优先的 Wiki 引擎，但仍需要明确运行时基础设施。

- **机器索引层**：面向程序读取的页面、关系、链接、来源和检索元数据。默认持久边界是 `.knoarbor/index/manifest.json` 与 `.knoarbor/index/graph_index.json`；`index.md` 只是后续可选导出视图，不是 source of truth。当前实现使用 Markdown 扫描、graph index artifact、兼容 retrieval payload 和页面级 BM25 排序；后续 provider 可以在同一 `IndexProvider` 边界后面落地 SQLite FTS 或向量索引。
- **单机队列**：`LocalRunQueue` 是第一版队列后端，按 vault 串行化运行，避免写入重叠。恢复失败项时创建新的 run，而不是修改已完成 run。
- **运行生命周期**：排队、运行、心跳、取消、恢复元数据和事件记录属于 Runtime 层。Pipeline 只通过该边界上报进度，不直接写 run-state 文件。
- **运行事件**：长流程使用结构化事件记录阶段、模型调用、重试、页面写入、查询结果和失败。UI、CLI、报告和 skill 读取同一事件流，不从临时日志中重建进度。
- **恢复机制**：可恢复运行由已保存的运行元数据和报告推导。恢复会创建新的 scoped run，不会原地修改已经完成的 run 记录。
- **运行日志**：诊断日志写入 `.knoarbor/logs/knoarbor.log`，与用户报告、ledger 和 run events 分离。
- **文件锁**：本地 vault 修改使用 `.knoarbor/locks/vault.write.lock`，保护页面、索引、日志、checkpoint、ledger 和维护写入。
- **语义重试策略**：模型重试属于 `SemanticRunner`，不散落在 ingest、lint、API route 或 prompt 专用清洗逻辑中。runner 只重试配置在错误码白名单中的错误。
- **受控并发**：dry-run/preflight ingest 可以有界并发处理 source；写入型 ingest 在同一个 vault 内保持串行，确保页面写入和 checkpoint 一致。
- **事件模型**：run events 是进度事实，冻结事件目录位于 `knoarbor.runtime.events`。
- **应用缓存**：第一版不需要独立应用缓存层；后续页面解析、图谱和 query index 可以缓存，但 checkpoint、lint decision、ledger 和 report 不能被缓存替代。
- **供应商 prompt cache**：prompt caching 由模型供应商负责。`SemanticRunner` 会把每次调用构造成 `SemanticPromptPackage`：稳定执行器指令和稳定契约文本放在前缀，动态 source/wiki payload 放在最后。runner 不应把时间戳、run id、本地路径等易变内容注入稳定前缀。供应商返回 cached prompt tokens 或 DeepSeek cache hit/miss tokens 时，KnoArbor 会记录到运行指标中，并记录 prompt package 的稳定/动态规模用于后续成本分析。
- **Docker**：Docker 是部署适配层，不是核心架构层。

## 读取 API 边界

生成后的 Wiki 页面拥有独立稳定的读取边界：

```text
storage / retrieval metadata
  -> WikiPagesService
  -> /vaults/default/pages, /vaults/default/pages/content, /vaults/default/pages/links
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
- Query 以检索为主，不使用回答生成智能体。
- Wiki Chat Agent 是控制台内受限的 KnoArbor 工具回答智能体。

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
- 维护 UI 侧的 Vault Runtime 状态，用于当前知识库选择、按知识库分区的缓存 key，以及多知识库展示状态。

不负责：

- 来源发现、checkpoint、分段、页面 operation 规划、lint 执行、重试策略、vault 写入和报告生成；
- 在已有核心 `/wiki/*` 页面读取 API 时，再实现一套 UI 专用页面解析逻辑；
- 静默修复本应由 Python Core 校验的异常 API payload。

Vault Runtime 是前端状态边界，不是存储层。它把配置中的知识库 profiles 映射为稳定的 UI 身份，用 `vaultId` 分区 React Query 缓存，并在 API 调用时传入解析后的 vault path。这样 UI 可以在不清空无关页面状态的情况下切换当前知识库，也为后续在一个页面并排展示多个知识库摘要打基础。

1.x 阶段，KnoArbor 暂时保留轻量本地组件体系，不引入完整 UI 组件框架。如果表单、菜单、弹窗、表格和报告视图继续膨胀，下一步应有意识地抽取共享 UI primitives，或正式引入小型组件库，而不是继续追加页面级样式补丁。

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
