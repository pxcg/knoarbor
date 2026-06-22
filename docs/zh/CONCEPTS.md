# 核心概念

KnoArbor 的目标不是保存聊天记录，而是把多源信息编译成长期可维护的 Wiki。

## Raw Source

Raw source 是原始资料层，保留输入的原貌，例如 Hermes 对话、Markdown 笔记、PDF 转换后的 Markdown、网页导出或其他文本。它是证据链的起点，不应被 LLM 改写。

## Source Digest

Source digest 是 `sources/` 下的来源摘要页面。它解释某个 raw source 的主题、范围和生成出的知识页面，让用户能从知识页面追溯回原始资料。

## Wiki Page

Wiki page 是真正面向查询和维护的知识页面。维护后的页面位于 `pages/`：

- `pages/<slug>.md`：普通知识页面。
- `pages/sources/`：来源摘要页面。
- `pages/_views/`：自动生成的浏览视图。

页面类型不再依赖必须存在的物理类型目录，而是由页面身份元数据表达：

- `page_kind`：概念、实体、流程、对比、时间线、问答、笔记或来源摘要。
- `role`：知识页、来源摘要、生成视图或报告。
- `facets`：用于检索和浏览的多标签。
- `canonical_path`：当前稳定路径。
- `legacy_paths`：迁移前旧路径，仍可解析。

`concepts/`、`entities/` 等旧目录在迁移期可以继续读取，但不是新的页面类型模型。

## Ingest

Ingest 是知识编译阶段：读取输入来源，标准化资料，规划页面操作，生成或更新 Wiki 页面，并记录运行报告。

## Lint

Lint 是校验维护阶段：扫描结构问题、链接问题、溯源问题和内容质量问题，并按风险等级自动应用通过评审的维护操作。

## Query

Query 是上下文检索阶段：从已维护的 Wiki 中返回相关页面、摘录、来源线索和上下文包，供 Hermes、Codex、OpenClaw、Claude Code、CLI 或其他宿主 AI 继续组织最终回答。
