# KnoArbor 系统架构

本文档是 KnoArbor 的公开架构概览，解释稳定系统边界，不展开内部规划细节。

KnoArbor 是一个 AI 原生 Wiki 引擎，将多源信息编译成可追溯、可维护的知识网络，让零散的知识像树一样生长。

```text
raw source -> ingest canonical facts -> indexes/projections -> lint integrity -> raw-grounded query/chat
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
| Connector / Source | 将 Markdown、聊天记录、文档和未来外部系统转换成 `SourceDocument`。 | 语义提取、事实发布、投影或页面生命周期治理。 |
| Document Processing | 在共享 ingest 前把富文档转换成 Markdown。 | 知识对象分类或 Wiki 写入。 |
| Semantic | 窄功能 LLM 契约、prompt、schema 校验和语义步骤。 | 读取本地文件、写页面、执行操作或管理进度。 |
| Model Gateway | 稳定模型边界、ProviderAdapter 选择、OpenAI 兼容调用、Ollama 原生调用、JSON mode、端点检测、retry 和 token 指标。 | ingest/lint/query 的业务决策。 |
| Storage / Writer | 不可变事实 revision、SQLite source head/cursor、物化、索引更新和底层 vault 文件原语。 | 判断某个知识对象是否应该存在，或汇总报告。 |
| Retrieval / Index | 知识 atom 排序、claim 解析、精确 source-unit evidence 解析、导航索引和 query context pack。 | 修改 Wiki 页面，或把投影当作事实权威。 |
| Maintenance | canonical 完整性扫描、只读语义发现、自动所有者修复、修复后验证与审计。 | 绕过所有者流程直接修改 raw/facts 或编写生成页内容。 |
| Runtime | 队列、run monitor、heartbeat、事件目录、取消、文件锁和日志。 | 业务语义，或 SemanticRunner 之外的重试决策。 |
| Config / Policy | 运行路径、模型供应商、connector、隐私、执行限制和功能开关。 | 配置不可见的隐藏行为。 |
| Report / Audit | 人可读报告、机器 ledger、失败运行报告、查询记录、运行摘要和报告渲染。 | 页面正文事实来源或维护操作决策。 |
| Wiki Chat Agent | 受限的控制台对话循环，围绕 KnoArbor 工具、引用和流程入口回答问题。 | 通用 shell、浏览器、文件、网络自动化或隐藏工作流策略。 |
| Memory | 长期对话偏好、vault 级交互约定、显式记忆候选、召回上下文和记忆事件。 | Wiki 知识页面、raw source 归档、source record 或任意聊天全文存储。 |

实现说明：

- CLI 保持 `cli.py` 作为入口和统一错误边界。命令注册位于 `cli_commands/parser.py`，命令行为位于 `cli_commands/handlers.py`。
- UI 配置的请求/响应模型位于 `services/ui_config_models.py`；`services/ui_config.py` 负责配置读写、表单转换和诊断。
- 维护验证的编排位于 `maintenance/operation_verification.py`；具体 action 的验证规则位于 `maintenance/operation_verifiers.py`。
- 报告模块通过 `audit/report_formatting.py` 共享基础 Markdown 格式化工具；ingest 和 lint 报告仍各自负责工作流专属摘要。

粒度规则：

- 当一个模块混合多个架构层、包含可单独测试的策略，或迫使调用方引入无关依赖时，应该拆分。
- 当一个模块本质上是内聚的 registry、命令处理集合、验证规则集合或报告渲染器时，可以保持聚合；文件偏长本身不是继续拆分的充分理由。
- 架构门禁检查 core、storage、runtime、pipelines 和 renderer 领域模块的依赖方向。文件行数可以触发职责复审，但不会自动判错或要求拆分。只有行为存在独立所有者、契约、依赖集合、生命周期或可独立测试的策略时才拆分模块。
- 相比大量微小文件，优先保留一个职责清楚、局部 helper 可读的文件。
- 新增子包应表达稳定概念，而不是只为了隐藏一个长函数。

## 系统层

### 来源层

来源层保留原始材料和来源派生的标准化文档。

常见运行目录：

- `vaults/default/raw/inbox/notes/`：用户提供的 Markdown 笔记。
- `vaults/default/raw/inbox/documents/`：PDF、DOCX、PPTX、XLSX、手册、课程资料等富文档原件。
- `vaults/default/raw/inbox/media/`：原始图片和媒体文件。
- `vaults/default/raw/inbox/chats/`：Hermes、Codex、OpenClaw、Claude Code 等 AI 工具会话的标准化结果。
- `vaults/default/raw/derived/markdown/`：由 MinerU-compatible 等确定性预处理器生成的 Markdown。
- `vaults/default/raw/derived/excerpts/`：用户手动选中的短摘录。
- `vaults/default/raw/derived/assets/`：解析出的图片、表格、页面切片和媒体附件。
- `vaults/default/raw/derived/metadata/`：不作为 Wiki 页面渲染的来源辅助元数据。
- `vaults/default/artifacts/`：Chat 或工具生成的用户可见产物，例如生成图片。

规则：

- LLM 工作流不覆盖 raw source。
- 来源身份通过路径和内容哈希跟踪。
- 聊天来源通过 checkpoint window 只处理新增轮次。
- 富文档先转换为 Markdown，再进入共享 ingest 路径。

### 知识层

知识层保存维护后的 Wiki 页面，物理位置是 `vaults/default/wiki/`。
当你希望在 Obsidian 中打开干净的知识库时，应打开 `vaults/default/wiki`，而不是整个 `vaults/default` 运行时工作区：

- `wiki/pages/<slug>.md`：人工维护页面和确定性可读来源投影。
- `.knoarbor/facts/<source>/<revision>/`：由 SQLite source head 选择的不可变
  source、knowledge、diagnostics 与 integrity 文件。
- `.knoarbor/ingest.sqlite`：task、attempt lease、source head/cursor、entity
  contribution 与 vault materialization 的持久权威。
- UI 浏览视图由 `.knoarbor/index/CURRENT` 选择的已验证 machine-index generation
  派生，不作为 wiki fact 写入物理目录。

知识页面的结构写在页面内部：identity、summary、claims、entities、relations、evidence 和 synthesis。物理目录不再承担知识类型分类。

人类可读报告保存在 `vaults/default/maintenance/reports/`。运行状态、ledger、source cursor、lock 和机器索引保存在 `vaults/default/.knoarbor/`。
可审计声明和类型化关系是页面内部结构，并进入机器索引，不再作为独立页面目录。

规则：

- 每个 Wiki 页面应代表一个稳定知识对象。
- 页面边界比保留原始来源形状更重要。
- 优先创建少量有用页面，而不是大量薄页面。
- `maintenance/`、`raw/` 和 `.knoarbor/` 不是常规知识目标。

### 索引层

索引层为智能体和查询流程提供路由与检索上下文。

当前实现：

- 在 `vaults/default/.knoarbor/index/generations/` 下生成不可变机器索引 generation，由 `.knoarbor/index/CURRENT` 原子选择已验证的 active generation；
- 保留 `pages.json`、`links.json`、`sources.json`、`search.json` 等导航 payload，供 UI 浏览使用；
- 对 active claim、entity、relation atom 与 Raw locator document 做字段加权 BM25；
- 在 canonical entity ID 上维护一份已验证的跨来源关系邻接，每条边都经全部 supporting claims 闭合到 active Raw；
- 为宿主 AI 工具返回 query context pack。

持久化 generation 格式可以在相同发布与查询契约之后演进：

```text
active atom batches + processing records
  -> deterministic index generation
  -> verified CURRENT snapshot
  -> lexical recall + optional bounded relation traversal + exact evidence resolution
```

工作流代码依赖稳定 retrieval payload 和已验证 snapshot，而不是没有生产调用方的
provider class 或人工维护的 `index.md`。

retrieval snapshot 是规范化的派生状态：每个 evidence identity 的父 Raw
`rerank_text` 只存一份，locator row 仅保留检索与 active resolution 所需元数据。
一次 Query batch 对每个 vault 只验证一份不可变 snapshot，并在所有表达式与证据读取间
共享；完整 Raw 与语义事实仍由索引之外的既有权威保存。

### Query Evidence 选择层

默认 query 融合 claim/atom 与 Raw lexical recall。代码判定为关系意图时，再确定性
枚举最多两条 active relation edge 的简单路径，并将每条边的全部 supporting claims
解析到 active Raw。它不把页面排序并入事实证据排序。投影路径只作为可选导航元数据；完整 source unit
是 query 与 chat context 中唯一的事实材料。

### 治理层

治理层记录 Wiki 为什么发生变化。

包括：

- SQLite source cursor 与 task 状态；
- ingest report；
- lint report；
- failed-run report；
- operation ledger；
- quality 和 verification 输出。

自动维护必须可检查。一次页面更新应能看到来源、理由、风险信号和执行结果。

失败运行同样是审计事件。如果 ingest、lint 或 query 在正常结果生成前失败，只要能确定 vault 路径，service 层就应该写入失败报告和 ledger。Runtime queue 只记录运行状态；Audit 层负责用户可读的失败制品。

### 记忆层

记忆层保存 Wiki Chat Agent 使用的长期交互偏好。Memory 与 Wiki 页面、Source Record 分离：

- Wiki 页面记录稳定知识对象；
- Source Record 记录来源摘要和溯源；
- Memory Record 指导对话界面如何按用户或 vault 偏好使用知识。

记忆文件保存在 `vaults/default/.knoarbor/memory/`：

- `records.jsonl`：append-only 记忆记录；
- `candidates.jsonl`：候选或自动写入的记忆；
- `events.jsonl`：召回和写入事件；
- `profile.md`：可选的人类可读画像摘要。

第一版在模型调用前召回记忆，并只捕获用户明确表达的低风险偏好。推断型会话总结、全局记忆和人工候选审查属于后续扩展。

## 主流程

### Ingest / 知识编译

目标：把新增或变化的来源材料提交为不可变事实 revision，再生成可重建投影。

```text
connector discovery
  -> source normalization
  -> privacy redaction
  -> checkpoint window
  -> source segmentation
  -> semantic atom extraction
  -> deterministic validation, merge, and entity linking
  -> immutable factual revision and active-head commit
  -> deterministic source projection and machine-index materialization
  -> report and ledger
```

职责：

- connector 将来源特定材料标准化为共享 `SourceDocument`。
- source input 区分发现引用（`SourceRef`）、原始状态（`RawSource`）、标准化内容（`SourceDocument`）、处理身份（`SourceFingerprint`）和 checkpoint window；即使来源字节未变化，connector 或 parser 版本变化也会重新进入处理。
- 长来源切分位于 `SourceDocument` 标准化之后，按 source units 规划 segment，
  再在 source/window 边界确定性聚合。
- 模型只产生语义候选；代码负责 evidence binding、身份、校验、entity linking、
  publication、projection 与 diagnostics。
- 结构化 processing record 与 evidence-backed atom batch 进入不可变 source
  revision，并由 SQLite source head 原子发布。
- `wiki/pages/` 的 source projection 是 model-free 可重建定位视图，不是事实权威。
- ingest 不持久化宽泛词面导航链接；弱主题联系只作为 retrieval signal。
- `ingest --input` 是一次性本地输入边界：Markdown 文件和文件夹直接进入共享 ingest；非 Markdown 必须先经过已配置的 MinerU-compatible 预处理器，缺少预处理器时显式失败。

实现边界：

- `services.ingest_coordinator` 是公开 submit/recovery 边界。
- `services.ingest_input_resolver` 解析请求并冻结 immutable input generation。
- `runtime.transactional_ingest` 负责 task/attempt、source heads、cursor、entity contribution 和 materialization epoch。
- `storage.revision_integrity` 负责不可变事实 revision manifest 与文件完整性校验，
  不导入 lifecycle store。
- `storage.index_snapshot` 负责不可变 machine-index generation 查找与完整性校验，
  不导入 index writer 或 runtime lifecycle owner。
- `runtime.ingest_executor` 执行一个持久本地任务并协调 provider admission、事实处理与 materialization。
- `runtime.ingest_session` 是 pipeline 用于 lease renewal 和事实发布的 port。
- `pipelines/source_segmentation.py` 负责分段计划和 source-window 切分边界。
- `pipelines/ingest_metrics.py` 负责 source/segment 指标、脱敏统计聚合和语义 token 统计。
- `pipelines/ingest_auto.py` 负责 redaction、unitization、条件 segmentation、语义 metadata extraction、单一确定性 compiler-integrity 边界和 source 结果。
- `storage.source_revisions` 负责不可变事实 revision 发布。
- `storage.materialization` 负责 source projection 和 immutable machine-index generation 发布。
- `storage.wiki_projection` 负责可读 source projection rendering。

### Lint / 校验维护

目标：校验 raw 到 projection 的依赖链，而不成为第二套知识写入器。

```text
canonical collection
  -> deterministic integrity scan
  -> optional read-only semantic diagnosis/review
  -> owner-routed rebuild, reingest, or report requests
  -> report and ledger
```

职责：

- 校验 projection contract、canonical atom 引用、evidence identity 和 machine index 发布。
- 只通过确定性 publication 代码重建派生机器索引。
- canonical 提取问题路由为 `reingest_request`。
- 生成视图漂移路由为 `projection_rebuild_request`。
- 歧义、外部事实、隐私、merge 和图策略问题保持 report-only。
- 语义诊断保持只读：模型只生成有证据的发现，不生成页面草稿或替代事实。

实现边界：

- `lint_collection` 负责页面收集、wikilink lookup、图谱健康度和 scoped page 扩展。
- `lint_scanners` 负责确定性扫描规则和 issue 生成。
- `lint_candidates` 负责证据约束的质量与时间敏感信号选择，不使用固定页面长度或候选数量截断。
- `WikiLintPipeline` 负责扫描、可选语义复审、修复编排、修复后复扫和审计制品。
- `lint_execution` 对修复动作去重并调用 ingest 或 materialization，不直接 patch 页面正文。

用户可见模式：

- `deterministic`：完整性扫描、自动派生状态修复和复扫。
- `semantic`：相同修复语义，加只读模型诊断与复审；通过审查的 canonical 质量问题自动触发 reingest。

### Query / 知识查询

目标：为 Chat 或宿主 AI 返回 claim-backed active raw evidence，不生成最终聊天回答。

```text
query
  -> knowledge atom retrieval
  -> claim resolution
  -> exact active source-unit resolution
  -> complete raw source-unit evidence selection
  -> factual context plus navigation locators
  -> trace and gap signals
```

职责：

- 返回 atom/claim trace、来源指针、raw evidence、可选投影定位和 context pack。
- 通过匹配 atom、claim 解析和 evidence edge trace 解释检索过程。
- 不修改 Wiki 页面。
- 不声称 related 页面比 direct 页面更弱或更强；`match_kind` 只解释检索来源。

检索信号：

- 对 active claims、entities、relations 与 Raw locator documents 执行字段加权
  BM25；只移除问句骨架，保留架构、框架、组件、技术、方法、设置、位置、主题、
  效果等内容名词。
- 普通 entity/relation 命中通过批次内 `source_claim_ids` 解析到 claim，再回到
  active Raw；不存在单独的图遍历通道。
- claim 仅通过显式 `source_unit_id` evidence edge 解析 active raw unit。
- Raw locator window 保留独立 lexical 排序以找回抽取遗漏；投影页面不参与事实排序。
- Chat batch 的每个区域表达式消费 BM25/RRF 排名前 12 个父 Raw 候选，按
  vault-scoped Raw identity 去重后全局保留前 16 个，再做精确 span 结构校验；
  这些窗口不是置信度或字符预算。
- context pack 中完整 source units 提供事实，atom 和投影信息仅解释定位。

### Wiki Chat Agent / 对话

目标：让控制台用户用自然语言询问当前知识库，同时把所有动作限制在
KnoArbor 自有边界内。

```text
chat request
  -> 从 active source processing 与 atom records 派生 locator-only 文档/一级章节目录
     （每篇文档含一份完整的 source-level synthesis）
  -> 一次对话感知的 Retrieval Planner（区域 + 区域检索表达）
  -> 原问题与区域表达在每个选中区域组成共享组，执行一次 unified active-Raw Query batch
  -> 一次 Answer Decision（Raw / 通用知识 / 缺口 + 支撑 + 生图提示词）
  -> 可选的生图提供方调用
  -> 一次 Response Composer（表达、结构、引用块与所有图片位置）
  -> 支撑片段与引用校验
  -> provenance-bearing turn persistence
```

职责：

- 在管理控制台内综合回答。
- 通过与 `/query` 相同的 Query 所有者契约执行
  `retrieve_knowledge_batch`。
- 每个选中区域组都保留未改写原问题；检索规划模型选择目录中已经可见的文档或章节
  `region_id`，并结合对话和材料语言生成一条独立区域检索表达。
- 区域只限定对应表达式的 active source units，不能直接生成或准入 Raw。
- 所有选中区域只执行一次 Query batch；每条路径都经过同一 Query
  BM25/RRF 结果窗口与结构证据选择。Chat 不再进行第二轮检索、
  排序、截断或逐候选模型判断。
- Answer Decision 接收原始问题、纯对话历史、typed 检索结果与当前 Raw 证据；
  Retrieval Planner 的改写只用于定位，不进入最终回答输入。
- Answer Decision 为整轮语义选择 Raw 依据、通用知识或知识缺口之一；代码只校验
  支撑、图片归属并派生 provenance，不再用关键词或 no-match 门禁做语义路由。
- 当前不允许一轮中混合 Raw 依据块与通用知识块。
- Answer Decision 读取完整 active Raw unit 及代码签发的句子/结构行支撑片段，
  验证所选片段 ID 并映射为公开引用 span；检索命中 span 只作为定位元数据。
- Response Composer 只接收已选材料：代码拥有的读者可见来源标签、按原文位置排序的
  Raw 文本和已选附件语义；revision identity、offset、文件系统路径与附件 Markdown
  留在代码中。它可按同一 material 映射组织自然多块 Markdown，并把每张已选来源图
  以单图或连续图片组放在覆盖其所属 material 的文字块之后。
- 所有语义阶段接收保留实质文字的完整对话；代码渲染的引用编号、来源图/生成图
  Markdown 和生成图标识不进入模型历史。历史只用于指代和表达，不是事实依据。
- 向前端展示引用和证据轨迹。
- 生图请求不再绕过主链；只有 Answer Decision 返回非空
  `generated_image_prompt` 才能在 Response Composer 之前调用生图工具。成功生成的
  图片以本轮引用交给 Response Composer 统一确定位置。
- 按轮次保存每个助手回答自己的引用、工具轨迹、事件、记忆元数据和
  统计信息。
- 把用户明确选择的已保存会话转换为 `knoarbor_chat` source document，
  并通过共享 run manager 排队进入 ingest。

边界：

- `/query` 仍然是面向宿主 AI 的无模型证据检索。
- Chat orchestration 只接收 memory、session、tool、execution 和 ingest workflow
  所需能力，不依赖完整 application service container。
- conversation message 身份与 merge 规则统一由 `services.chat_messages` 负责，
  context assembly 和 persistence 复用该 owner。
- Chat 不获得任意 shell、浏览器、文件系统或网络工具。
- Chat 不直接写入 Wiki Markdown。
- 工作流行为仍由 ingest/lint service 和 run manager 管理。

## 本地运行基础设施

KnoArbor 是本地优先的 Wiki 引擎，但仍需要明确运行时基础设施。

- **机器索引层**：面向程序读取的页面、关系、链接、来源和检索元数据。持久边界是由 `.knoarbor/index/CURRENT` 选择的一套完整且已验证 generation；`index.md` 只是可选导出视图，不是 source of truth。默认知识查询使用 active atom 与显式 claim evidence edge；页面和 graph artifact 服务 UI 导航。后续 provider 可持久化同一 atom/edge 契约。
- **本地 ingest operation**：`TransactionalIngestStore` 保存 task/attempt、取消、恢复、source head 和 materialization state；桌面进程通过 `LocalOperationScheduler` 提交一次，CLI 可以在前台执行同一个持久任务，SQLite claim fencing 只允许一个 owner。
- **运行生命周期**：Pipeline 通过 execution port 更新持久状态；RunMonitor 文件和事件是展示/审计投影，不是恢复权威。
- **运行事件**：长流程使用结构化事件记录阶段、模型调用、重试、页面写入、查询结果和失败。UI、CLI、报告和 skill 读取同一事件流，不从临时日志中重建进度。
- **恢复机制**：语义恢复在不可变 command 和 input generation 下创建新 attempt；materialization 恢复只读取已提交事实，不调用模型。
- **运行日志**：诊断日志写入 `.knoarbor/logs/knoarbor.log`，与用户报告、ledger 和 run events 分离。
- **文件锁**：本地 vault 修改使用 `.knoarbor/locks/vault.write.lock`，保护页面、索引、日志、SQLite 发布、ledger 和维护写入。
- **语义重试策略**：模型重试属于 `SemanticRunner`，不散落在 ingest、lint、API route 或 prompt 专用清洗逻辑中。runner 只重试配置在错误码白名单中的错误。
- **受控并发**：provider 请求和 segment 调用使用配置的有界并发；所有事实与 materialization 修改仍经过跨进程 vault write lock 和事务发布边界。
- **事件模型**：run events 是进度事实，冻结事件目录位于 `knoarbor.runtime.events`。
- **应用缓存**：第一版不需要独立应用缓存层；后续页面解析、图谱和 query index 可以缓存，但 source cursor、lint decision、ledger 和 report 不能被缓存替代。
- **供应商 prompt cache**：prompt caching 由模型供应商负责。`SemanticRunner` 会把每次调用构造成 `SemanticPromptPackage`：稳定执行器指令和稳定契约文本放在前缀，动态 source/wiki payload 放在最后。runner 不应把时间戳、run id、本地路径等易变内容注入稳定前缀。供应商返回 cached prompt tokens 或 DeepSeek cache hit/miss tokens 时，KnoArbor 会记录到运行指标中，并记录 prompt package 的稳定/动态规模用于后续成本分析。
- **Docker**：Docker 是部署适配层，不是核心架构层。

## 读取 API 边界

生成后的 Wiki 页面拥有独立稳定的读取边界：

```text
storage / retrieval metadata
  -> WikiPagesService
  -> /wiki/pages, /wiki/pages/content, /wiki/pages/relations
  -> UI, skills, CLI wrappers, external clients
```

UI 不应拥有另一套页面读取逻辑。UI 可以拥有配置表单、本地资产、诊断摘要、报告列表渲染等界面专用适配器；但 Wiki 页面列表、页面详情和反向链接属于 `wiki` API/service 边界。

## 智能体边界

KnoArbor 使用窄功能语义契约，而不是自治多智能体团队。

- Index Metadata Extract Agent：为 raw-grounded ingest 抽取 `entities`、`relations`、`claims` 和 `synthesis`。
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
- UI 是配置、运行、报告、Wiki 浏览和图谱检查的管理控制台，不是独立工作流引擎。

## 前端边界

Web UI 是建立在公开 API 和 UI 专用 HTTP 适配器之上的本地管理控制台。它需要提供清晰的产品交互，但不应成为后端业务逻辑的第二套实现。

职责：

- 展示配置、来源状态、运行任务、报告、Wiki 页面和图谱数据；
- 通过稳定核心 API 运行流程、读取运行状态、查询上下文和 Wiki 页面；
- 只在配置表单、诊断摘要、本地资产和展示摘要等界面专用场景调用机器可读的
  `UI_PUBLIC_ROUTES` 适配器集合；
- 使用可复用本地组件渲染 Markdown、diff、报告和图谱。
- 维护 UI 侧的 Vault Runtime 状态，用于当前知识库选择、按知识库分区的缓存 key，以及多知识库展示状态。
- `api/client.ts` 只作为 domain client 的组合入口；HTTP/SSE transport 与错误边界保持单一实现。
- Renderer 通过 type-only import 消费 Electron preload 拥有的 IPC 类型契约。
- 页面与功能模块只接收明确的 application capability slice；完整 AppContext 只在 controller 与 route composition root 可见。

不负责：

- 来源发现、source cursor、分段、投影编辑、lint 执行、重试策略、vault 写入和报告生成；
- 在已有核心 `/wiki/*` 页面读取 API 时，再实现一套 UI 专用页面解析逻辑；
- 静默修复本应由 Python Core 校验的异常 API payload。

Vault Runtime 是前端状态边界，不是存储层。它把配置中的知识库 profiles 映射为稳定的 UI 身份，用 `vaultId` 分区 React Query 缓存，并在 API 调用时传入解析后的 vault path。这样 UI 可以在不清空无关页面状态的情况下切换当前知识库，也为后续在一个页面并排展示多个知识库摘要打基础。

当前 renderer 保留轻量本地组件体系，不引入完整 UI 组件框架。如果表单、菜单、弹窗、表格和报告视图继续膨胀，下一步应有意识地抽取共享 UI primitives，或正式引入小型组件库，而不是继续追加页面级样式补丁。

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
