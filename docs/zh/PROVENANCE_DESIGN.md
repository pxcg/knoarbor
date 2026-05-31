# 溯源设计

本文档冻结 KnoArbor 的来源溯源模型。它约束 ingest、lint、query 和后续 refresh 的共同数据语义，避免在 writer、lint agent 或查询层各自发明来源表达。

## 设计目标

- 保留 raw source 作为不可变证据底座。
- 让每个生成页都能追溯到一个或多个来源。
- 让 source digest 成为 raw source 与知识页之间的人类可读摘要页。
- 支持未来多来源合成页面，但不破坏当前单 `source` 字段页面。
- 让 lint 能检查 provenance 链路，而不是凭自然语言猜测来源。

## 来源层级

| 层级 | 目录/字段 | 职责 |
| --- | --- | --- |
| Raw Source | `raw/**` | 原始输入，原则上不可改写。 |
| Source Digest | `sources/*.md` | 对单个 raw source 的可读摘要、重点和生成页反向链接。 |
| Knowledge Page | `entities/`, `concepts/`, `comparisons/`, `queries/`, `claims/`, `timelines/`, `workflows/` | 面向复用的知识对象页面。 |

## 当前兼容字段

当前页面仍使用单值字段：

```yaml
source: raw/notes/Agent.md
```

约束：

- `source` 表示 primary source。
- `## Source` section 必须与 `source` 同步。
- 单来源页面必须有匹配 source digest，知识页也应在 Related Pages 中链接到该 digest。
- source digest 的 Related Pages 应链接回由同一 raw source 生成的知识页。
- 同一个 raw source 在同一批 ingest 中只能生成一个 source digest。长文档或长聊天被切分为多个 segment 时，重复的 source digest 草稿必须在写入前归并。
- ingest 阶段的 Related Pages 优先表达 provenance 关系。泛主题相似、弱相关或候选召回页不应自动沉淀为 Related Pages；这类关系由 lint 或 query 阶段再评估。

## 多来源目标模型

多来源页面不应把多个来源塞进自然语言段落。目标 frontmatter：

```yaml
source: raw/notes/Agent.md
sources:
  - path: raw/notes/Agent.md
    role: primary
  - path: raw/chats/session_20260505_173432_47d596.json
    role: supporting
```

角色语义：

- `primary`：页面主要依据。
- `supporting`：补充事实、例子、解释或上下文。
- `derived_from`：页面从另一个 source digest 或知识页整理迁移而来。

`source` 继续保留为兼容字段，等价于 `sources[0].path`。新的检索、lint 和关系判断在支持后应优先读取 `sources[]`。

## Lint 责任边界

Lint 可以：

- 检查 `source` 与 `## Source` 是否一致。
- 检查 raw source 是否存在。
- 检查 source digest 是否存在。
- 检查 source digest 与知识页是否互链。
- 为缺失 source digest、缺失互链、source 字段不一致生成维护候选。

Lint 不可以：

- 在没有结构化 `source_file` 或 `sources[]` 证据时猜测来源。
- 联网重新验证事实。
- 把普通 related page 链接当作 provenance source。
- 为多来源页面自动合并来源，除非操作显式携带 `sources[]` 参数并通过 review。

## 迁移策略

1. 保持当前单 `source` 运行路径稳定。
2. 先在 schema、文档和 lint 诊断中识别多来源需求。
3. 后续新增 `sources[]` 写入和读取能力时，只在 storage/retrieval/provenance 层扩展，不在 agent prompt 中用自然语言兜底。
4. 多来源页面的自动修复必须走 reviewed operation 或 draft write，并由 post-fix verification 检查 frontmatter 与 Source section。

## 后续实现点

- 在页面 schema 中加入可选 `sources[]`。
- 在 scanner 中识别 `sources[]` 与 `source` 的一致性。
- 在 source digest 关系检查中支持一页多来源。
- 在 query context pack 中暴露 primary/supporting source。
