# 文档治理规则

本文件是 [英文权威规则](../DOCUMENTATION_GOVERNANCE.md) 的中文说明。英文文件定义
文档分类、唯一事实源、生命周期和自动门禁；两者出现冲突时以英文规则为准。

## 保留范围

版本库只保留：

1. 当前有效的产品、架构、能力、操作和验证契约；
2. 理解这些契约仍需要的稳定局部说明；
3. 具有独立决策或审计价值的历史材料。

TaskPlan、RoleTask、Stage、Gate 输出、进度日志和普通 handoff 留在 Harness/Git，
不进入长期契约。

## 事实源

```text
产品结果
  -> Capability Map
  -> Architecture / Active Contract
  -> Supporting Contract
  -> 实现和测试
  -> Verification Protocol / Evidence
```

- `docs/CAPABILITY_MAP.md` 负责稳定能力 ID、四维成熟度、边界和唯一 owner。
- `docs/ARCHITECTURE.md` 负责分层、依赖方向和 Formal Host 规则。
- `docs/CONTRACTS.md` 及专门契约负责 authority、生命周期、恢复和发布边界。
- `harness/rules/semantic-hosts.json` 只是契约的机器投影，不能新增 authority。
- `specs/registry.json` 是规格生命周期唯一权威。
- Harness/Git 负责当前开发执行状态。

公开英文文档继续保持扁平路径，避免破坏既有链接；目录形状不决定 authority。

## 生命周期

| 动作 | 条件 |
| --- | --- |
| Keep | 当前唯一 owner，内容新鲜且可验证 |
| Update | owner 正确，但边界、锚点或证据过期 |
| Merge | 内容属于另一个 owner，或拆分提高了查找成本 |
| Archive | 已非当前状态，但仍有独立历史/审计价值 |
| Delete | 已吸收、重复、临时，且 Git 足以追溯 |

删除前必须迁移稳定契约和有效 code/test/verification anchors，更新索引与链接，并确认
没有操作入口只存在于被删文档。

## 新增与外部参考

新增文件前必须声明类型、唯一 owner 或 Active Parent、读者、代码/验证锚点和删除条件。
现有 owner 能承载时直接更新。

外部文章、会话或项目只能在 owning spec 中标记为 `adopt`、`adapt`、`reject` 或
`defer`，同时记录目标 owner、验证和清理条件；外部资料不能形成平行当前状态文档族。

## 自动门禁

`scripts/check-doc-governance.py` 检查规格注册表、必需标准、能力表、Formal Host 投影、
Skill 元数据和已退休 Harness authority；`scripts/check-doc-links.py` 检查 Markdown
链接。用户可见行为变化时，中文公开指南和契约仍需与英文权威文档同步。
