# 能力地图

本文档记录 KnoArbor 的稳定能力边界和当前实现状态。它和路线图、功能规格的关系如下：

- `docs/zh/ROADMAP.md` 负责长期版本方向。
- `specs/<feature>/` 负责功能级需求、设计、任务和验收。
- 本文档负责跨功能的能力状态。

## 状态说明

| 状态 | 含义 |
| --- | --- |
| 已冻结 | 边界已经接受，后续通过该边界扩展。 |
| 已实现 | 已有可运行基线，并有测试或发布检查覆盖。 |
| 部分实现 | 方向已经接受，实现或验证仍需补齐。 |
| 计划中 | 已进入后续路线图。 |
| 暂缓 | 能力有价值，属于更后期的产品范围。 |

## 核心能力

| 能力 | 状态 | 当前边界 | 负责文档/规格 |
| --- | --- | --- | --- |
| 资料连接器 | 已实现 | 连接器把外部材料转换为 `SourceDocument`；来源特定解析归属连接器或文档预处理代码。 | [1.3 Source Ecosystem](../../specs/1.3-source-ecosystem/requirements.md), [配置说明](CONFIGURATION.md) |
| 资料来源目录 | 已实现 | `/sources`、`knoar sources --catalog` 和控制台展示连接器元数据、设置 schema 和运行配置状态。 | [1.3 Source Ecosystem](../../specs/1.3-source-ecosystem/requirements.md), [接口说明](API.md), [命令行](CLI.md) |
| 文档预处理 | 部分实现 | 富文档先转换为 Markdown，再进入共享 ingest；MinerU 兼容服务作为文档预处理适配器。 | [架构设计](ARCHITECTURE.md), [配置说明](CONFIGURATION.md) |
| 资料分段 | 已实现 | 长资料在标准化和 checkpoint window 之后分段，并在 source/window 边界聚合后提交。 | [架构设计](ARCHITECTURE.md), [1.3 Source Ecosystem](../../specs/1.3-source-ecosystem/requirements.md) |
| 知识编译 | 已实现 | Ingest 负责资料标准化、分段语义处理、写入策略、局部 lint、checkpoint commit 和报告输出。 | [架构设计](ARCHITECTURE.md), [核心概念](CONCEPTS.md) |
| 校验治理 | 已实现 | Lint 负责确定性扫描、语义候选、评审后操作执行、验证和维护报告。 | [1.5 Knowledge Governance](../../specs/1.5-knowledge-governance/requirements.md), [架构设计](ARCHITECTURE.md) |
| Wiki 上下文检索 | 已实现 | Query 返回字段加权 BM25 排序页面、页面角色（`primary`、`supporting`、`source`）、答案范围、答案集合、覆盖信号、摘录、来源线索、trace 数据、图谱相关性信号和供宿主 AI 使用的 context pack。 | [1.7 CLI/API/Skill Closure](../../specs/1.7-cli-api-skill-closure/requirements.md), [接口说明](API.md) |
| 运行队列与监控 | 已实现 | Runtime 负责排队执行、运行状态、心跳、取消、恢复元数据和 active/recent run 视图。 | [架构设计](ARCHITECTURE.md), [接口说明](API.md) |
| 报告与审计层 | 已实现 | Audit 负责 ingest、lint、query、token 和失败报告，以及机器可读 ledger。 | [架构设计](ARCHITECTURE.md), [测试与质量门禁](TESTING.md) |
| 模型网关 | 已实现 | 模型调用经过 provider adapter、OpenAI-compatible transport、结构化输出处理、usage metrics 和 endpoint 检查。 | [架构设计](ARCHITECTURE.md), [配置说明](CONFIGURATION.md) |
| 多知识库配置 | 已实现 | 配置支持命名知识库和 active vault 选择；相关公开 API 支持 vault selection 参数。 | [配置说明](CONFIGURATION.md), [接口说明](API.md) |
| Web 控制台 | 部分实现 | 控制台提供资料来源、知识编译、校验维护、查询、知识库浏览、图谱、报告、运行、设置和 token 分析。 | [1.6 Productized Console](../../specs/1.6-productized-console/requirements.md), [展示导览](SHOWCASE.md) |
| 前端 i18n 约束 | 已实现 | UI 文案集中在 `web/src/i18n/` 下；前端构建前检查中英文 key 一致性。 | [测试与质量门禁](TESTING.md) |
| CLI 入口 | 已实现 | CLI 为用户提供默认可读输出，并通过 JSON 输出支持自动化。 | [1.7 CLI/API/Skill Closure](../../specs/1.7-cli-api-skill-closure/requirements.md), [命令行](CLI.md) |
| 公开 API | 已实现 | 公开 endpoint family 保持小集合：health、doctor、sources、ingest、lint、query、runs、reports、wiki pages 和 runtime metadata。 | [接口说明](API.md), [API 兼容性](API_COMPATIBILITY.md) |
| 宿主 AI Skill | 已实现 | Skill 调用本地 API 完成 query、页面读取、source catalog、runs、reports、ingest 和 lint 操作。 | [1.7 CLI/API/Skill Closure](../../specs/1.7-cli-api-skill-closure/requirements.md) |
| 机器索引层 | 部分实现 | 检索已经使用 index provider 边界和页面级 BM25 排序；本地持久索引、重建状态和 freshness 诊断仍在规划中。 | [1.4 Machine Index Layer](../../specs/1.4-machine-index-layer/requirements.md) |
| 可选向量检索 | 暂缓 | 向量检索作为 index contract 后面的可选 provider。 | [1.4 Machine Index Layer](../../specs/1.4-machine-index-layer/requirements.md) |
| 托管多用户服务 | 暂缓 | 本地优先单用户使用是当前产品基线。 | [路线图](ROADMAP.md) |

## 能力完成规则

能力进入“已实现”状态时，需要满足：

- 公开或内部契约已经文档化；
- 架构文档或功能规格标明 owning layer；
- 自动化测试或发布门禁覆盖核心路径；
- 公开能力同步到用户文档；
- 涉及 vault 修改或模型调用的能力，在报告、ledger 或 trace 中保留诊断证据。

“已冻结”表示边界状态。一个已冻结边界内部仍然可以包含计划中或部分实现的能力。
