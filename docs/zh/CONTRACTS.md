# 契约总览

本文是 KnoArbor 稳定跨层契约的索引，负责共享权威和数据流边界。HTTP、UI、
报告和溯源的详细规则由对应专项文档负责。

## 契约 Owner

| 契约 | Owner |
| --- | --- |
| 公开 HTTP 兼容性 | [API 兼容性](API_COMPATIBILITY.md)与[接口说明](API.md) |
| CLI 行为 | [命令行](CLI.md) |
| UI 表面和 adapter | [UI 契约](UI_CONTRACT.md) |
| 报告、台账和失败产物 | [报告契约](REPORT_CONTRACT.md) |
| 来源、evidence 和事实权威 | [溯源设计](PROVENANCE_DESIGN.md)与 [ADR 0004](../adr/0004-ingest-factual-authority.md) |
| Vault 路径 | `storage.vault_layout` 与规格 1.17 |
| Ingest runtime | 规格 1.37 |
| Ingest 语义链 | 规格 1.26 和 1.27 |
| Query 检索与 evidence resolution | 规格 1.38 与 ADR 0003 |

Feature spec 说明实现意图；本文和链接的 contract owner 描述当前支持边界。

## Vault Contract

桌面产品根目录包含 `config.yaml`、`vaults/`、`state/`、`logs/`、`cache/`
和 `tmp/`。唯一运行端点是 `state/endpoint.json`；顶层或用户主目录中的
`.knoarbor` 不能成为桌面运行权威。

```text
vault/
  raw/                    忠于来源的输入和确定性派生产物
  wiki/pages/             人工页面和可读来源投影
  artifacts/              用户可见生成文件
  maintenance/reports/    人类可读流程报告
  .knoarbor/
    ingest.sqlite         事务 ingest 与 active-head 权威
    facts/                不可变四文件事实 revision
    ingest_inputs/        不可变 workflow input
    index/                可重建机器索引 generation
    ledgers/ runs/         机器审计和运行展示
    locks/ logs/          本地协调与诊断
```

持久化和公开 payload 使用 vault-relative 路径。模型流程不会覆盖 raw source。

## 事实权威

已发布事实由 `.knoarbor/ingest.sqlite` 的 active source/session heads 与其可达的
`.knoarbor/facts/` 不可变 revision 共同定义。Revision 保存结构化
processing record、source units、带 evidence 的 entities/claims/relations、身份与
完整性 metadata，以及用于语义定位的 source synthesis。

`wiki/pages/*.md` projection 和 `.knoarbor/index/` 是可重建视图，不是第二套
事实权威。Legacy `wiki/sources/*.md` 可以继续读取，但当前 ingest 不依赖它。

## Evidence Contract

Raw evidence 和 source units 是事实回答材料。持久 evidence span 保存 source、
revision、source unit、excerpt 与完整性信息。模型调用中的数组位置只在该次请求
内有效，不进入事实 revision。

Claim 提取同时返回规范化 claim 与各 supporting source unit 中最小充分的逐字 quote。
编译器验证每个 quote 存在于对应 unit，映射回原始 source substring，并计算字符区间与
完整性 hash。重复和重叠 quote 均有效；同一文本重复出现时确定性选择原文中的第一次出现。
不存在的 quote 会拒绝本次提取，evidence 不会扩大为完整 source unit。持久 span 可以去重
excerpt 正文，并依据 source unit 与字符区间确定性恢复。

Entities、claims、relations 都携带 evidence；relation 还引用 supporting claim。
Wiki 页面和 atom summary 可以定位事实，但不会变成 raw evidence。

## Page Contract

`wiki/pages/` 同时保存：

- 使用 claims-first 结构的人工维护页面；
- 带 `schema_version`、`projection_kind`、`not_fact_material` 和 source/revision
  identity 的确定性来源投影。

页面类型由 metadata 和结构表达，不使用物理类型目录。Projection renderer 不
调用模型，并可从事实 revision 重建。

## Attachment 与 Machine Index

来源附件和确定性处理产物位于 `raw/derived/assets/**`，metadata 位于
`raw/derived/metadata/**` 或结构化 source record。公开引用使用已验证的
vault-relative 路径。

`.knoarbor/index/` 保存版本化页面、图、来源、链接和检索视图。完整 generation
验证后原子发布 `CURRENT`；删除 machine index 不会删除事实知识。同一份已验证
retrieval SQLite 同时保存 lexical documents 和 canonical-entity 关系邻接；每条发布
关系边必须通过全部 supporting claims 闭合到 active facts。
派生 locator storage 对每个 evidence identity 只保存一份父 Raw rerank text，且不重复
完整不可变语义 evidence。一次 Query batch 对每个选中 vault 只验证一份 snapshot，
并在表达式和 active evidence 读取间共享。

## Ingest Contract

```text
source request -> immutable input -> SourceDocument -> source units/segments
  -> semantic candidates -> deterministic compile/link -> factual revision
  -> deterministic materialization -> report/ledger
```

模型生成语义候选；代码负责引用验证、evidence、ID、hash、路径、linking、发布、
projection、diagnostics 和 recovery。事实提交与 materialization health 分别可见。
Projection rebuild 读取已提交事实，不调用模型。

语义 metadata 在内容单元边界保持原文语言。同一来源中的中文和英文单元可以同时生成
中文与英文的 entity、claim、predicate 和 locator topic；文档级语言提示不得强制将
全部输出翻译成一种语言。这属于 extraction prompt 规范，不是确定性 ingest 门禁；
发布不会使用字符比例语言检测来拒绝已有 Raw grounding 的 metadata。

## Raw Revision Edit Contract

Raw 编辑不会原地修改 active factual revision。系统使用相同 source identity 创建新的
不可变 SourceDocument，并提交到标准 queued ingest coordinator。模型提取、确定性编译校验、
事实发布、投影、索引、报告、取消和恢复都复用正常 ingest 契约。

请求携带打开编辑器时的 revision，发布时会再次校验 parent revision，避免过期任务覆盖
较新的 active head。成功 ingest 后会依据新 Raw 重新生成 synthesis、claims、entities、
relations 和 evidence；旧 Raw revision 上的投影编辑不会自动带入新 revision。

## Query 与 Chat

Query 是 model-free 检索：active Claim、Entity、Relation 与 active Raw locator
window 进入同一不可变检索 generation；Relation 命中通过批次内
`source_claim_ids` 回到 Claim 和 active Raw。
FTS5 与字段加权 BM25 负责 lexical 准入和通道内排序，RRF 负责父 Raw 融合排序；
Chat batch 的每个区域组在原问题与区域改写之间共同保留前 12 个父候选，按 vault-scoped Raw identity 去重后
全局保留前 16 个，再做精确 span 结构选择。这些结果窗口不是语义置信度、字符预算
或用户设置。
同一区域内的原问题与改写是替代表达；每个父 Raw 只保留最佳排名贡献，不因同时命中
两种表达而重复加票。只有被选中 Raw 单元实际引用的图片附件才进入 Chat，且同一附件
每个回答只出现一次。
`wiki_query.v4` 返回 typed QueryOutcome、vault-scoped evidence handles、独立 evidence
reads、channel status、gaps、stats 和 trace。

Chat 读取从 active source processing 与 atom records 派生的 locator-only 文档/一级章节
目录及其材料语言提示。每个文档节点包含该文档完整的 source-level synthesis，使一次
对话感知的 Retrieval Planner 即使在标题和章节用词没有命中问题时也能识别相关文档。
Planner 选择其中确切存在的 `region_id` 并为每个区域生成一条独立检索表达，再与未改写
原问题组成共享区域组送入一个 Query-owned batch。空或不可用规划回退为一次无区域限制
的原问题检索。区域只在融合与准入前过滤本表达式的 active
source units，不能生成或授权 Raw。除文档级 synthesis 定位信息外，目录不包含 Raw、
单条 Claim/Entity/Relation、attachment、内部 revision/evidence 身份或其他投影正文，
本身不是事实材料。

Query 返回的 EvidenceSet 将 locator 与事实材料分开。代码先枚举 active Raw 中
精确的句子和结构行支撑片段，Grounded 综合只选择本次请求内的片段 ID；代码拥有
由此产生的回答引用 span 与顺序。检索命中 span 与投影页面只保留为定位上下文。
一个公开引用编号对应一个已选择的 Raw 单元，其紧凑定位符保留该单元内全部精确范围。
重叠或相接的范围可以合并；互不相邻的范围保持独立，不能用最小/最大坐标扩成包含
中间未使用内容的大范围。持久化 Chat 引用只保存这些定位符。预览时按需从引用的
不可变 source unit 解析回答实际选择的全部文本，解析文本只存在于内存。source unit
局部坐标不得切完整 Raw，定位失败也不能生成猜测高亮。
Chat 只准备一次该证据投影：模型接收读者可见来源标签、支撑文本与 ID、本轮临时
visual reference、原文图题和处理器提取的图片内容；文件名、持久化
attachment/revision identity、字符 offset、文件系统路径、重复 citation projection 与
附件 Markdown 留在代码中。
Answer Decision 只返回 `mode`、`spans`、`visuals`、`gap` 和
`generated_image_prompt`。非空提示词同时表示明确生图授权并提供调用输入，不再
保留重复的布尔字段。代码校验后先调用生图提供方，再按 Raw 所有权生成本轮
`material_id`，每份 material
只包含代码拥有的读者可见来源标签、按原文位置排序的已选 Raw 文本和已选图片语义。
Response Composer 同时接收原始问题和保留实质内容的对话历史；代码注入的引用编号、
来源图/生成图 Markdown 与生成图标识会先从模型历史投影中移除。

Response Composer 输出有序文字项、来源图片项和成功生成的图片项。一个文字项可使用自然的多块
Markdown，其 material 映射覆盖整个文字项；只有支撑材料集合变化时才需要拆项。
代码拒绝正文中的内部 material identity 和独立的伪引用标记，但不因普通代码、公式、
语法示例、索引写法或技术路径的表面形状而拒绝回答。每张已选来源图必须且只能出现一次；单图或
连续图片组放在覆盖组内全部图片所属 material 的文字项之后。完整或部分知识缺口必须
由 Response Composer 写入最终回答，代码不再对其具体措辞增加二次语义门禁。
回答正文遵循当前用户消息的语言构成：中文、英文以及真实的中英混合问题可以保持各自
形式；原文名称、技术术语、代码、公式和直接引文默认保持原样，除非用户明确要求翻译。
Chat 不重排、过滤或截断 Query 证据，不获得任意 shell、browser、filesystem 或
network tool，也不直接写 Wiki Markdown。

每个 Raw 依据回答都会收到当前 Raw 证据实际引用的来源图片语义。来源附件不存在
独立的生图意图：只要存在原文图题或处理器提取内容，可渲染图片就获得本轮临时引用。
Answer Decision 只能选择带有同一 Raw 支撑的来源图片；Response Composer 只能把
已选图片以单图或连续图片组放到所属材料文字块之后，不能自行输出图片 Markdown。
未知、重复、
位置不属于所选 Raw、跨 Raw、未选择以及图题和提取内容均为空的图片不展示。
Answer Decision 只有在用户语义上明确请求创建新图片且能力可用时才返回非空
`generated_image_prompt`；代码在 Response Composer 之前执行生图，后者统一安排
成功生成图片的位置。请求来源原图不构成生成替代图的许可，生成图片由代码添加
清晰的“非知识库证据”可见标识。

Answer Decision 是整轮 Raw 依据、通用知识或知识缺口选择的唯一语义所有者；
Response Composer 只组织已锁定材料，不能重判相关性。候选与 typed `no_match`
都经过这两个固定阶段。代码根据已校验的支撑选择派生 provenance，不再使用固定 gold 门禁或
本地材料关键词规则进行语义路由。会话变更使用稳定
request/message/turn identity 与 compare-and-swap
`session_revision`；选择性入库使用 `turn_ids`，不得使用数组位置。

## Operational Contracts

- Error 与 response envelope 见[错误码](ERROR_CODES.md)和[API 兼容性](API_COMPATIBILITY.md)。
- 报告与台账 schema 见[报告契约](REPORT_CONTRACT.md)。
- UI 只展示 service 决策，不重建 workflow policy；见 [UI 契约](UI_CONTRACT.md)。
- Runtime events 和 diagnostics 是运行审计，不是知识事实。
