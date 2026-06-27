# 核心概念

KnoArbor 的目标不是保存聊天记录，而是把多源信息编译成长期可维护的 Wiki。

## Raw Source

Raw source 是原始资料层，保留输入的原貌，例如 Hermes 对话、Markdown 笔记、PDF 转换后的 Markdown、网页导出或其他文本。它是证据链的起点，不应被 LLM 改写。

## Source Digest

Source digest 是 `sources/` 下的来源摘要页面。它解释某个 raw source 的主题、范围和生成出的知识页面，让用户能从知识页面追溯回原始资料。

## Wiki Page

Wiki page 是真正面向查询和维护的知识页面。每个知识库使用固定目录：

- `wiki/pages/<slug>.md`：维护后的知识页面。
- `wiki/sources/<slug>.md`：来源摘要和审计页面。
- `raw/**`：原始资料或标准化后的资料。
- `maintenance/reports/**`：人类可读运行报告。
- `.knoarbor/index/**`：页面检索和图遍历使用的机器索引。
- 浏览视图由机器索引派生，并由 UI 渲染，不再写入物理目录。

知识页面不使用物理类型目录。页面的核心结构由正文 section 表达：
`Summary`、`Claims`、`Relations`、`Synthesis`、`Entities` 和 `Evidence`。

## Ingest

Ingest 是知识编译阶段：读取输入来源，标准化资料，规划页面操作，生成或更新 Wiki 页面，并记录运行报告。

## Lint

Lint 是校验维护阶段：扫描结构问题、链接问题、溯源问题和内容质量问题，并按风险等级自动应用通过评审的维护操作。

## Query

Query 是上下文检索阶段：从已维护的 Wiki 中返回相关页面、摘录、来源线索和上下文包，供 Hermes、Codex、OpenClaw、Claude Code、CLI 或其他宿主 AI 继续组织最终回答。
