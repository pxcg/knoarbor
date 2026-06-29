# 溯源设计

本文档解释 KnoArbor 的来源溯源模型。冻结的字段和目录契约记录在
[契约总览](CONTRACTS.md)；本文说明 raw source、source digest、知识页、
lint 维护和 query context 如何共享同一个“来源”语义。

## 设计目标

- 保留 raw source 作为不可变证据底座。
- 让每个生成页都能追溯到一个或多个来源。
- 让 source digest 成为 raw source 与知识页之间的人类可读摘要页。
- 使用正文中的结构化 Evidence 作为单来源和多来源页面的标准溯源模型。
- 让 lint 能检查 provenance 链路，而不是凭自然语言猜测来源。

## 来源层级

| 层级 | 目录/字段 | 职责 |
| --- | --- | --- |
| Raw Source | `raw/**` | 原始输入，原则上不可改写。 |
| Source Digest | `wiki/sources/*.md` | 单个 raw source 的来源审计页，连接原始资料与生成知识页。 |
| Knowledge Page | `wiki/pages/<slug>.md` | 面向复用的知识页面。Claims、Relations、Entities、Synthesis 和 Evidence 保存在页面正文与图索引中。 |

## 页面正文来源证据

当前页面在专门的正文结构中记录来源。知识页使用 `## Evidence`；source digest 使用 `## Source Identity`、`## Source Units`、`## Contribution Map` 与 `## Raw Source`。

```markdown
## Evidence

| Claim | Source | Range | Basis | Confidence |
|---|---|---|---|---|
| C1 | raw/inbox/notes/Agent.md | unit:0 | 原始资料描述了 Agent Loop 的控制循环。 | high |
```

职责：

- `## Evidence` 将每条 claim 绑定到 source、range、basis 和 confidence。它是知识页记录 raw source 的唯一正文来源表。
- 知识页依赖的每个 raw source 都有匹配的 source digest trace。
- source digest 通过 Contribution Map 和机器索引 trace 记录由同一 raw source 生成的知识页。
- 同一个 raw source 在同一批 ingest 中生成一个 source digest。长文档或长聊天被切分为多个 segment 时，重复的 source digest 草稿在写入前归并。
- ingest 将主题相似和弱候选匹配保留为 retrieval/index 信号，页面正文聚焦 claims、relations、entities、evidence 和 synthesis。

## 多来源模型

多来源页面通过多行 `## Evidence` 表达：

```markdown
## Evidence

| Claim | Source | Range | Basis | Confidence |
|---|---|---|---|---|
| C1 | raw/inbox/notes/Agent.md | unit:0 | Agent Loop 控制循环。 | high |
| C2 | raw/normalized/chats/session_20260505_173432_47d596.json | turn:4-6 | 生产环境记忆设计讨论。 | medium |
```

检索、lint 和关系判断以 `## Evidence` 与 source digest trace 为准。

## Lint 责任边界

Lint 负责：

- 检查 `## Evidence` 与 source digest trace 中的来源是否完整。
- 检查 raw source 是否存在。
- 检查 source digest 是否存在。
- 检查 source digest trace 与 Contribution Map 是否和生成页一致。
- 为缺失 source digest 和缺失 trace 记录生成维护候选。

Lint 范围外：

- 缺少结构化 Evidence、Source Identity、Raw Source 或 Contribution Map 证据时的来源猜测。
- 联网事实验证。
- 将普通 wiki 链接解释为 provenance source。
- 未更新结构化 Evidence 行且未通过 review 的多来源合并。

## 迁移策略

1. 将来源溯源保存在页面正文的证据章节中。
2. 从 Evidence、Source Identity、Raw Source 和 Contribution Map 校验来源引用。
3. frontmatter 仅保存创建时间、更新时间、内容哈希等页面身份元数据。
4. 自动来源修复只更新结构化 Evidence 与 source digest trace，不改写页面身份元数据。

## 后续实现点

- 在 scanner 中校验 Evidence、Source Identity、Raw Source 和 Contribution Map 的来源完整性。
- 在 source digest 关系检查中支持一页多来源。
- 在 query context pack 中暴露证据置信度与来源范围。
