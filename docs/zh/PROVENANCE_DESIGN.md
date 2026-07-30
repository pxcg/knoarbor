# 溯源设计

本文定义 ingest、检索、Chat、投影和维护共同使用的稳定溯源语义。字段级契约见[契约总览](CONTRACTS.md)，事实权威见
[ADR 0004](../adr/0004-ingest-factual-authority.md)。

## 溯源链

```text
原始资料
  -> 标准化 source units
  -> 不可变 source revision
  -> 带证据的知识元数据
  -> 可读投影和机器投影
  -> raw-grounded 检索
```

## 权威边界

| 层 | 角色 | 权威范围 |
| --- | --- | --- |
| Raw source | 用户资料或确定性标准化产物 | 事实输入 |
| Source unit | Source revision 内的稳定证据坐标 | 可用于回答的证据 |
| Source revision | Processing record、source units、knowledge atoms 和 manifest | 已发布事实记录 |
| SQLite source head | 选择当前 revision 和 session window | 发布权威 |
| Wiki source projection | 可读 synthesis、claims、entities 和 relations | 可重建定位视图 |
| Machine index | 搜索、图、页面、来源和链接记录 | 可重建检索视图 |
| Run/report artifacts | 执行、失败、Token 和恢复诊断 | 仅运行审计 |

`.knoarbor/ingest.sqlite` 中的 active source heads 与其可达的
`.knoarbor/facts/` 不可变 revision 共同定义已发布事实。
Wiki Markdown 和机器索引不会重新定义事实。

## Evidence

每个接受的 entity、claim 或 relation 都指向由稳定 source unit 构造的
evidence。Evidence 保存来源、revision、unit、excerpt 和完整性信息。模型
请求中的数组位置只在该次调用内有效，不属于持久溯源。

Query 和 Chat 可以利用 Wiki 页面与 atom metadata 定位相关事实。事实性回答
使用 raw evidence 或 source units，遵循 [ADR 0003](../adr/0003-raw-grounded-answering.md)。
Wiki 页面提供导航和 synthesis，但页面文字不会因为由 ingest 生成就自动成为
raw evidence。

## Projection

事务 ingest 为每个 active replaceable source 在 `wiki/pages/` 生成一份可读
source projection；增量 session 生成合并投影。这些页面标记为投影材料，并可在
不调用模型的情况下重建。

`wiki/sources/` 属于早期 source-record Markdown 设计。已有文件可以继续读取，
但当前 ingest 不要求也不生成它们作为溯源权威。

## 维护边界

维护流程可以检查 revision/source-unit 引用、evidence 完整性、原始资料缺失、
投影 freshness、来源导航和机器索引 generation 一致性。维护流程不会从普通 Wiki
链接推断溯源，不会改写 raw source，也不会把运行诊断当作知识事实。

## 恢复与备份

备份应保护 raw material、`.knoarbor/ingest.sqlite` 和可达 source revision
generations。Wiki projections 与 machine indexes 可以重建。事实提交后发生的投影
失败通过 materialization 恢复，不重复模型调用。
