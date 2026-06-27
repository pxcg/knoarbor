# 维护者指南

本文面向 KnoArbor 的长期维护者，补充 [开发说明](DEVELOPMENT.md)、[架构设计](ARCHITECTURE.md) 和 [发布前审查清单](RELEASE_CHECKLIST.md)。

目标是让功能增长保持可控：新能力通过清晰分层、稳定契约、测试和用户可见文档进入项目。

## 文档职责

决定文档归属时使用下表：

| 文档 | 负责内容 | 不应包含 |
| --- | --- | --- |
| `README.md` / `README.zh-CN.md` | 项目定位、截图、安装路径、常用用法 | 内部规划、实现争论、私有路线图细节 |
| `docs/QUICKSTART.md` | 第一次成功运行 | 完整架构或所有 CLI 参数 |
| `docs/CONFIGURATION.md` | 配置 schema、模型供应商、连接器、隐私设置 | 发布流程或代码结构 |
| `docs/CLI.md` | 公开命令行行为 | 未明确公开的内部辅助命令 |
| `docs/API.md` | 公开 HTTP API 契约 | `/ui/api/*` 内部接口或原型接口 |
| `docs/ARCHITECTURE.md` | 稳定分层、流程边界、模块职责 | 短期任务清单或未定设计争论 |
| `docs/PROVENANCE_DESIGN.md` | 来源链和证据模型 | 通用 ingest/lint 实现细节 |
| `docs/TESTING.md` | 质量门禁和测试边界 | 与发布清单重复的大段说明 |
| `docs/RELEASE_CHECKLIST.md` | 发布决策清单 | 功能路线图 |
| `docs/ROADMAP.md` | 从 1.0 到 2.0 的发展方向 | 每个提交的 changelog 或 sprint 任务 |
| `docs/CAPABILITY_MAP.md` | 跨功能能力状态和职责归属 | 详细功能设计或发布说明 |
| `docs/adr/*` | 长期架构决策 | 任务进度或实现流水 |
| `docs/MAINTAINERS.md` | 维护规则和长期治理 | 用户入门教程 |
| `specs/<feature>/*` | 功能级需求、设计、任务状态和验收计划 | 稳定用户文档、发布说明，或与该功能无关的私有设计争论 |
| `CHANGELOG.md` 和 `docs/releases/*` | 版本变更 | 未来规划 |

功能行为变化时，只更新拥有该行为的最小文档集合。避免把同一段解释复制到多个文件；优先链接到单一权威文档。

## 文档写作风格

长期项目文档描述当前已经接受的系统设计。采用直接、客观、规范的表达方式：

- 定义当前职责、边界、输入、输出和验证路径；
- 使用“负责”“通过……进入”“由……表示”“由……验证”等表达职责归属；
- 迁移历史、调试过程和每日执行记录放入发布说明、提交信息或维护记录；
- 公开文档聚焦用户和贡献者可以依赖的稳定行为。

推荐使用当前状态表达：

| 推荐表达 | 适合放入本地记录的表达 |
| --- | --- |
| “Query 层为宿主 AI 工具返回 context pack。” | 和聊天助手定位的对比记录。 |
| “Source segmentation 归属 pipeline 层。” | 设计讨论中的归属对比记录。 |
| “UI adapter 调用稳定 API service。” | adapter 策略修正记录。 |
| “Runtime 负责队列、心跳、取消和恢复状态。” | 按时间线记录的调试过程。 |

历史对比适合放在 ADR 的 alternatives、发布说明和迁移记录中。稳定文档优先呈现当前接受的设计。

## 规格驱动开发

KnoArbor 对影响架构、公开契约、来源 connector、语义契约、流程行为或发布关键体验的变更，使用轻量规格驱动开发。

规格文件位于 [`specs/`](../../specs/README.md)。它们负责把路线图主题连接到实现、测试和发布说明。长期公开文档保留稳定的用户和贡献者视角：

- `docs/ROADMAP.md` 负责产品方向和版本主题。
- `docs/ARCHITECTURE.md` 负责稳定分层和边界。
- `docs/API.md`、`docs/CLI.md` 和 `docs/CONFIGURATION.md` 负责公开契约。
- `specs/<feature>/` 负责该功能的需求、设计、任务和验收记录。

以下变更需要创建或更新功能规格：

- 新增或显著修改公开 API、CLI、配置字段、报告 schema 或 Skill 操作；
- 新增或显著修改来源 connector、source type、文档预处理或长资料切分行为；
- 调整架构层或跨层契约；
- 调整语义 prompt/schema 契约；
- 调整自动维护、验证、重试或恢复行为。

拼写修正、孤立 UI 文案、小版本依赖补丁和单文件 bug 修复可以引用现有规格，也可以不单独创建规格。

实现规则：如果代码实现证明原设计需要调整，应在同一次变更中更新规格，并让实现与规格保持一致。规格应说明接受的设计和候选方案，帮助后续维护者直接理解决策背景。

### 路线图规格管理策略

1.3 到 1.7 的路线图主题使用不同管理策略：

| 版本线 | 策略 | 编码前必须先更新的内容 |
| --- | --- | --- |
| 1.3 资料来源生态 | Connector 契约治理 | 来源能力、settings schema、connector 检查表、来源行为变化。 |
| 1.4 机器索引层 | 架构契约设计 | Index provider 边界、持久索引存储、rebuild/freshness API 或 CLI。 |
| 1.5 知识治理 | Operation taxonomy 与审计设计 | Lint operation 名称、风险/审查策略、executor 支持、报告/diff schema。 |
| 1.6 控制台产品化 | 产品交互与 UI 架构 | 导航、加载策略、报告视图、共享组件、UI adapter 边界。 |
| 1.7 CLI/API/Skill 闭环 | 兼容性与入口一致性 | 公开 endpoint 名称、CLI 参数、response envelope、Skill 操作。 |

编码前先使用对应规格。如果一个变更跨多个版本主题，只更新真正拥有该契约的最小规格集合，并避免把同一解释复制进长期文档。

## 分支纪律

遵循 [开发说明](DEVELOPMENT.md#分支与发布模型) 中的分支模型。

简要规则：

- 日常工作从 `dev` 开始；
- 聚焦变更使用 `feature/*`、`fix/*` 或 `docs/*`；
- release tag 只从 `main` 创建；
- 紧急热修可以从 `main` 切分支，但必须合回 `dev`；
- 公开 release tag 被用户消费后保持稳定。

如果因为文档或发布元数据直接修改了 `main`，继续功能开发前需要把 `main` 合回 `dev`。

`main` 不应长期领先最新公开 tag。如果发生这种情况，且内容可以发布，优先补齐缺失的版本 tag 和 release notes，而不是重写公开历史。只有出现密钥、私有运行时数据或其他无法安全发布的泄漏时，才考虑重写 `main`。

## 架构变更流程

新增或移动能力前，先判断其归属层：

- **来源层**：connector、文档预处理、source normalization。
- **知识层**：Wiki 页面、vault 路径、source digest、页面渲染。
- **索引层**：人类可读 index 和机器检索索引。
- **治理层**：lint、review、维护操作、验证。
- **运行层**：队列、监控、日志、锁、生命周期报告。
- **语义层**：prompt contract、模型网关、结构化 schema。
- **适配层**：CLI、API、UI、npm launcher、skills。

新行为应放在职责最强的一层。跨层补偿不进入实现路径。例如 API route 负责 transport 和请求校验；模型输出修复归属 semantic runner；文件锁和 checkpoint 策略归属 runtime 与 pipeline 层。

架构变更通常需要包含：

1. commit message 或 PR 描述中的简短设计决策；
2. 所属层的测试；
3. 边界移动时更新 `ARCHITECTURE.md`；
4. 公开契约变化时更新 CLI/API/config 文档。

## 兜底和重试策略

KnoArbor 优先使用明确的可靠性机制。

可以接受的可靠性机制：

- 模型供应商错误通过 model gateway 重试；
- semantic runner 内部的结构化输出重试；
- 基于运行元数据和 checkpoint 的显式恢复；
- 本地 vault 写入使用文件锁；
- 页面写入前后的确定性验证；
- ingest/lint 失败时生成用户可见失败报告。

避免：

- 静默从一个来源路径 fallback 到另一个路径；
- 吞掉错误模型输出并编造替代内容；
- source batch 失败后仍写入部分页面；
- 对确定性的配置、路径或策略错误重试；
- 添加与 CLI/API 状态不一致的 UI-only 状态。

如果确实需要兜底，应记录触发条件、所属模块、报告入口和证明其边界的测试。

## 数据安全规则

运行时 vault 是用户数据。自动测试和发布脚本必须使用临时目录。

自动门禁不得写入：

- 项目根目录 `vaults/`；
- 项目根目录 `config.yaml`；
- 项目根目录 `.env`；
- 私有 connector 来源目录；
- 维护者本地规划文件夹。

任何会写入 vault、config、report、ledger、checkpoint 或生成页面的命令，都应使用 `mktemp -d` 或等价测试 fixture。

## 兼容性规则

公开契约：

- `docs/CLI.md` 中记录的 CLI 命令；
- `docs/API.md` 中记录的 HTTP route；
- `docs/CONFIGURATION.md` 中记录的配置字段；
- `docs/CONCEPTS.md` 和 `docs/PROVENANCE_DESIGN.md` 中记录的 vault 页面语义；
- `docs/ERROR_CODES.md` 中记录的错误码。

内部契约：

- `/ui/api/*` route；
- semantic prompt 内部结构；
- 私有 service method；
- UI 组件结构；
- 未写入公开文档的维护脚本。

修改公开契约时，同步更新文档和测试。修改内部契约时，应保持公开适配层行为稳定。

## 发布就绪

打 tag 前：

1. 运行常规开发门禁；
2. 运行 release readiness 检查；
3. 运行 clean-clone smoke 检查；
4. 可访问模型供应商时运行真实模型 smoke；
5. 检查隐私和 tracked-file 边界；
6. 更新 release notes 和 changelog；
7. 只从 `main` 打 tag。

发布决策基于 [发布前审查清单](RELEASE_CHECKLIST.md)。

## 长期路线图维护

路线图描述稳定产品结果。具体实现记录放在 issue、PR 或公开发布树之外的本地维护者笔记中。

路线图事项完成后，只有公开方向发生变化时才更新 [路线图](ROADMAP.md)。不要把路线图变成 changelog。
