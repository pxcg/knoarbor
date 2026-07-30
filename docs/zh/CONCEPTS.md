# 核心概念

KnoArbor 把多来源资料编译为可检索、可追溯和可维护的本地知识。由 SQLite
active heads 选择的不可变 source/knowledge revision 是事实权威；Markdown Wiki
页面和机器索引是面向人和工具的可重建投影。

## Raw Source

Raw source 是用户提供的原始资料或确定性预处理产物，是事实链的起点。LLM
流程不会覆盖 raw source。

## SourceDocument

Connector 将 Markdown、聊天、文档转换结果等来源标准化为共享
`SourceDocument`。它保存来源身份、正文、附件、fingerprint 和 checkpoint
window；来源特定解析属于 connector 或 document processor。

## Vault 权威与投影

- `wiki/pages/*.md` 保存人工维护页面和确定性来源投影。
- `.knoarbor/facts/` 保存不可变 source/knowledge revision。
- `.knoarbor/ingest.sqlite` 选择 active source revision。
- `raw/**` 保存事实输入，`maintenance/reports/**` 保存人类可读诊断。

旧 vault 可能仍包含 `wiki/sources/*.md` source-record audit 页面；当前 ingest
使用结构化 processing record，不把这些 Markdown 作为事实权威。

## Ingest

Ingest 冻结输入，建立 source units，提取并验证语义元数据，原子提交 source
revision，再确定性生成 Wiki 和机器索引投影。事实提交后的投影失败通过
materialization 重建，不重复模型调用。

## Lint

Lint 扫描页面、链接、结构、溯源和内容质量问题，生成结构化维护候选，并按
风险与评审策略执行和复验。Lint 不改写 raw source。

## Query

Query 是 model-free 检索层。它排序 active atoms、选择可回答 claim，再沿显式
evidence edge 解析完整 active source units。页面只提供导航定位；`raw_evidence`
才是 Chat 或宿主 AI 的事实材料。

## Runtime Vaults

每个 vault 拥有独立的 raw、wiki、maintenance 和 `.knoarbor` 状态。API、CLI
和桌面界面显式携带 vault identity；跨 vault 查询不会依赖进程全局目录。
