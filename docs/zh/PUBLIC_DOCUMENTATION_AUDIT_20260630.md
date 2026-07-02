# 公开文档全面审计

日期：2026-06-30

本文记录 KnoArbor 公开文档在进入下一阶段开源推进前的全面审计结果。范围包括 README、`docs/` 文档中心、用户指南、参考文档、契约文档、路线图、展示截图、发布说明索引和中英文一致性。

## 审计方法

- 主线程检查 README、docs 索引、截图资产、CLI/API 实现和当前前端导航。
- 三个 subagent 分别审查：
  - 文档内容与代码/功能一致性；
  - README、Showcase 和截图展示资产；
  - 文档结构、分类、语气和归档边界。
- 结论以当前代码和公开发布线为准。历史 release note 和已归档治理文档允许保留历史表述，但不得作为当前行为说明。

## 总体结论

当前文档树的基础材料较完整，但公开入口仍混入历史阶段描述、维护者过程记录和过时截图。问题不在单个文档数量，而在公开阅读路径没有严格区分：

- 普通用户需要的安装、快速开始、桌面端/源码运行入口；
- 集成用户需要的 CLI/API/配置参考；
- 维护者需要的治理、测试、发布、spec 和专项审计记录；
- 历史版本记录。

公开文档应采用客观、当前时态、规范表达。过程性判断、阶段性治理结论和内部清理叙事应放入治理归档或维护者文档。

## P0：展示资产整体过时

审计时发现 `docs/assets/knoarbor-console-*.png` 仍展示旧 UI：

- 旧侧栏分组 `WORKSPACE / KNOWLEDGE / PIPELINES / INSIGHTS / SYSTEM`；
- 顶部 `EN/中文`、`Update Settings`、`API Docs`；
- 底部 `Docs / Project docs` 入口；
- 旧 Knowledge/Graph 页面布局。

当前前端已经收敛为：

- 主导航：Chat、Flows、Knowledge；
- 设置入口在侧栏底部；
- Docs 前端入口已删除；
- Graph 只展示页面关系。

这些旧截图会让用户误以为桌面端仍有文档入口和旧图谱/导航模型。README 和 Showcase 已替换为当前 Chat、Flows、Knowledge 图谱入口截图；旧截图资产不再作为当前公开展示资产保留。

## P0：README 当前状态描述不一致

审计时发现 README 徽章已是 `2.2.1 desktop release`，但 Current Status 仍写 `1.x local-first release line`。这会让用户无法判断当前版本阶段。

同时 README 的 Not included 部分列出 `Built-in chat answer generation`，但当前已有 Wiki Chat、`POST /chat`、`POST /chat/stream`、会话列表和重试等能力。治理后 README 已改为 `2.2 desktop-focused release line`，并移除该错误边界描述。

## P0：Showcase 演示命令无法安装内置示例

审计时发现 Showcase 用 `knoar init` 演示内置 Agent Loop 示例，但代码中只有 `knoar first-run` 会复制 `agent-loop.md`。如果用户按 Showcase 执行，随后 `ingest --connector markdown --write` 可能没有示例可读。

治理后 Showcase 使用 `first-run`，CLI 的 first-run 示例路径也与默认 Markdown inbox 保持一致。

## P1：API 文档和契约表不完整

审计时发现公开 API 总表只把 Chat 写成 `POST /chat`、`POST /chat/stream`，但稳定契约还包含：

- `GET /chat/sessions`
- `GET /chat/sessions/{session_id}`
- `PATCH /chat/sessions/{session_id}`
- `DELETE /chat/sessions/{session_id}`
- `POST /chat/sessions/{session_id}/ingest`
- `POST /chat/sessions/{session_id}/close`
- `POST /chat/sessions/{session_id}/retry`

英文 API 总表也漏列 `GET /models/image-providers`。此外，`api_contract.py` 注释写成 `stable across 1.x releases`，不符合当前公开 API 兼容边界。治理后 API 表和契约注释已更新。

`DELETE /chat/sessions/{session_id}/turns/{turn_index}` 存在于 router，但未在稳定契约中。后续应明确它是 UI/internal 还是 public stable。

## P1：UI/Graph 契约描述需要收口

审计时发现 UI Contract 写 Graph 从 `.knoarbor/index/graph_index.json` 派生，并描述 `link or contribution relations`。当前 UI 图谱服务读取 index provider 的 page/link 视图，返回 page graph，边类型是 `wikilink` 或 `semantic`。治理后 UI Contract 已改为页面图谱和 index-provider 口径。

## P1：docs 首页面向普通用户的信息层级过重

审计时发现 `docs/README.md` 和 `docs/zh/README.md` 把用户文档、维护者文档、文档治理、spec、release checklist、历史版本说明放在同一公开入口中。普通用户打开文档中心时，应优先看到：

- 安装/快速开始；
- 配置；
- CLI/API；
- 故障排查；
- 核心概念；
- 备份恢复。

治理后 docs 首页已按用户指南、参考、契约、架构、贡献者与维护者、发布历史重新分组；维护者、spec、治理和发布门禁内容已单独标注。

## P1：release 索引过时

审计时发现 `docs/releases/v2.2.1.md` 已存在，但 docs 首页最新 release 只列到 `v2.0.0`。中文 release 策略也不清楚：只有 `docs/zh/releases/v1.3.0.md` 是中文版本，其余链接回英文 release。

治理后 docs 首页已列入 `v2.2.1`。短期策略是 release notes 以英文为准，中文文档中心链接英文最新版本；如要做中文 mirror，应补齐最新版本。

## P2：文档治理与维护者指南存在重复权威

`DOCUMENTATION_GOVERNANCE.md` 和 `MAINTAINERS.md` 都维护文档归属表。长期会产生漂移。建议后续收敛为：

- 文档治理文件负责文档类型、清理规则、归档规则；
- 维护者指南引用治理文件，只保留执行规则和维护流程。

## P2：README 首屏信息密度偏高

审计时发现 README 在安装入口前放置大量概念、功能和多张截图。对开源用户来说，首屏应该更快回答：

- 项目是什么；
- 适合谁；
- 桌面端如何使用；
- 源码如何启动；
- 最短验证路径是什么。

治理后 README 的产品导览已从七张旧截图收敛为当前 Chat、Flows、Knowledge Graph 三张截图。后续可继续把完整流程说明下沉到 Showcase/Concepts。

## P2：社交预览和截图文案口径旧

审计时发现 `docs/assets/knoarbor-social-preview.png` 仍写 `LLM-native knowledge arbor for structured wiki building`。当前主口径是 `AI-native wiki engine`、`traceable knowledge network` 和桌面端发布线。该资产未被公开文档引用，治理后不再保留。

## 修复顺序

1. 替换或删除所有旧 UI 截图，至少提供当前 Chat、Flows、Knowledge/Graph 三类截图。
2. 修正 README 当前状态、Not included、首屏入口和桌面端/源码运行口径。
3. 修正 Showcase 演示命令，使用 `first-run`。
4. 修正 API 总表、API 契约注释、UI/Graph 契约。
5. 重构 docs 首页信息层级，降低维护者/治理/spec 内容在普通用户入口中的权重。
6. 更新 release 索引和中文 release 策略说明。
7. 去重文档治理与维护者指南的归属表。

## 验收标准

- README 和 Showcase 不再引用旧 UI 截图。
- 公开文档不再描述已删除的 Docs 前端入口。
- 公开文档不再把实体图谱作为当前 UI 能力。
- README 不再出现 `1.x release line` 或 `Built-in chat answer generation` 的错误状态。
- `first-run`、Showcase、Quickstart 和默认 Markdown 根目录一致。
- API 文档和 `api_contract.py` 的稳定路由口径一致，或明确标注 UI/internal 路由。
- 文档链接检查通过。
