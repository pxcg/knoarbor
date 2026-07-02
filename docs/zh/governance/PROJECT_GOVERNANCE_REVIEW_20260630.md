# KnoArbor 项目治理专项分析

日期：2026-06-30

归档说明：本文是进入桌面端下一阶段前的历史专项分析记录。文中列出的若干 P0/P1 问题已经在后续治理中完成收口；当前状态以 `docs/zh/DOCUMENTATION_GOVERNANCE.md`、`docs/zh/ARCHITECTURE.md`、`docs/zh/UI_CONTRACT.md` 和代码实现为准。

本文档用于进入下一阶段开发前的代码治理决策。分析范围聚焦三件事：项目解耦设计、残留/冗余设计、测试治理。结论来自主线程代码扫描和三个独立 subagent 的只读分析，本文只给出治理判断和执行路线，不包含具体代码修改。

## 总体判断

当前项目的部署边界基本清晰：

- Python 后端负责核心业务、API、管线、检索、会话、配置和存储。
- `web/` 负责桌面端 renderer 源码和本地 UI bundle。
- `desktop/` 负责 Electron 外壳、本地服务托管、IPC 和打包。

真正的问题不在“目录有没有分层”，而在几个增长过快的业务编排点已经承担了多个变化原因。下一阶段如果继续直接叠功能，最容易变复杂的是 chat、ingest、前端应用状态、UI 配置、测试夹具。

本次治理建议采用三步顺序：

1. 先清残留：移除已经被产品方向淘汰、但仍在后端/契约/文案/构建产物中存在的入口。
2. 再拆职责：优先拆 chat 和前端应用状态这类后续还会高频变动的中心模块。
3. 最后整理测试：先搬迁归类和沉淀 fixture，再做参数化和重复断言清理。

## 一、项目解耦设计

### P0：Chat 工作流需要优先拆出编排边界

核心文件：

- `src/knoarbor/services/chat_agent.py`
- `src/knoarbor/entrypoints/routers/chat.py`
- `src/knoarbor/services/chat_tools.py`

问题不是单纯行数，而是职责叠加。`chat_agent.py` 同时处理会话目标解析、模型 client 创建、上下文构建、工具规划、多轮工具执行、答案合成、事件记录、memory、token ledger 和持久化协调。`_ChatLoop.run()` 已经是 agent 状态机、观测记录和统计持久化的混合体。

建议拆分方向：

- `ChatOrchestrator`：只负责 plan -> execute tools -> synthesize answer 的状态机。
- `ChatPlanningContextBuilder`：负责 planner 输入、当前 evidence context、topic anchor 上下文组装。
- `ChatTelemetry` 或 `ChatEventPublisher`：统一处理 `ChatEvent`、usage、call records、日志。
- `ChatPersistenceCoordinator`：统一负责 session persist、ledger append、memory 写入。
- `ChatToolExecutor` 保留 facade，但将工具实现拆成 `chat_tools/wiki.py`、`chat_tools/image.py`、`chat_tools/vaults.py`、`chat_tools/reuse.py`，并引入统一 `ToolContext`。

`entrypoints/routers/chat.py` 也需要变薄。目前 HTTP 路由里混有 SSE 编码、close/retry/ingest、auto-ingest 策略。建议新增：

- `ChatStreamAdapter`：SSE payload、错误事件、stream 编码。
- `ChatSessionWorkflowService`：close、retry、ingest、auto-ingest 决策。

### P1：前端应用状态和 API client 需要按领域拆分

核心文件：

- `web/src/useAppController.ts`
- `web/src/api/client.ts`
- `web/src/api/types.ts`
- `web/src/i18n/data.ts`

`useAppController.ts` 是当前前端事实上的应用内核，同时管理路由视图、语言、本地存储、React Query、vault 选择、刷新策略、桌面命令、跨页面导航意图和缓存写入。它已经不是普通 hook，而是所有页面耦合点。

建议拆分方向：

- `useVaultController`：vault options、active vault、overview/status 查询。
- `useAppQueries`：health、config、doctor、runs、reports、pages、graph、queryTrend。
- `useNavigationIntents`：openWikiPage、openChat、openReport、focused state。
- `useDesktopCommands`：`window.knoarborDesktop` 命令监听、service restart。
- `usePersistedPreferences`：language、sidebar、chatProvider、modelProbeResults。

`api/client.ts` 同时包含 config、models、vaults、wiki、reports、runs、ingest、lint、query、chat 和 SSE。建议按领域拆：

- `web/src/api/config.ts`
- `web/src/api/vaults.ts`
- `web/src/api/runs.ts`
- `web/src/api/wiki.ts`
- `web/src/api/chat.ts`
- `web/src/api/ingest.ts`
- `web/src/api/sse.ts`
- `web/src/api/vaultSelector.ts`

拆分时应保持导出兼容，可以先让 `client.ts` 作为 re-export 门面，降低一次性迁移风险。

### P1：UI 配置服务需要拆出读写、映射、诊断、副作用

核心文件：

- `src/knoarbor/services/ui_config.py`
- `src/knoarbor/services/ui_config_models.py`
- `desktop/src/main/config.ts`

`ui_config.py` 当前同时处理 YAML 读写、表单 DTO 映射、诊断、默认配置、vault 初始化、source count refresh、provider credential readiness。桌面侧也有自己的 app-data、legacy 迁移和默认 config 生成。

建议拆分方向：

- `ui_config_repository.py`：读写、解析、路径解析。
- `ui_config_mapper.py`：config <-> form。
- `ui_config_diagnostics.py`：connector/provider/path diagnostics。
- `ui_config_bootstrap.py`：vault 初始化和配置创建副作用。

桌面侧后续可进一步拆为：

- `desktop-bootstrap.ts`
- `desktop-state-store.ts`
- `service-process.ts`
- `service-health.ts`

### P1：Ingest 顶层仍是长流程总控

核心文件：

- `src/knoarbor/pipelines/ingest.py`
- `src/knoarbor/pipelines/ingest_semantic.py`
- `src/knoarbor/pipelines/ingest_postprocess.py`
- `src/knoarbor/pipelines/ingest_checkpoint.py`

ingest 已经拆出不少模块，但 `IngestSourceExecutor` 仍直接编排 checkpoint、ignore、redaction、unitization、semantic、gate、write、scoped lint、monitor/observer、metrics。建议等 chat 和残留清理之后再做，避免同时动两个高风险管线。

建议拆分方向：

- `IngestSourceRunner`：单源生命周期。
- `SegmentedIngestRunner`：分段、聚合、source-level planning。
- `IngestResultBuilder`：metrics、error、touched pages、scoped lint payload。
- `IngestEventPublisher`：统一 monitor/observer 事件。

### P2：图谱页、provider 配置页可后置

核心文件：

- `web/src/pages/GraphPage.tsx`
- `web/src/components/config/ConfigModelProvidersSection.tsx`

这些文件有职责混合，但不属于当前最大风险。建议等前端应用状态拆分后再做局部组件化。

## 二、残留、冗余和重复设计

### P0/P1：文档入口链路没有收干净

前端文档入口已经删除，但后端和契约仍保留：

- `src/knoarbor/entrypoints/routers/ui.py` 仍有 `/ui/api/docs/{doc_path:path}` 和 `/ui/api/docs-assets/{asset_path:path}`。
- `src/knoarbor/entrypoints/api_contract.py` 仍记录 `/ui/api/docs/{doc_path}`。
- `web/src/i18n/data.ts` 仍保留 `docsLoading`、`docsLoadingCopy`、`docsDirectory` 等文案，其中 `docsDirectory` 被设置页复用。
- `src/knoarbor/ui/dist` 的旧构建产物仍包含历史 DocsPage chunk，发布前需要重新构建并清理 dist。

建议下一步优先做：

1. 删除 UI router 中 project docs API、docs asset resolver、`UiProjectDoc`、`_project_docs_root()`。
2. 从 `api_contract.py` 删除 UI docs route。
3. 把设置页复用的 `docsDirectory` 改成 `settingsDirectory` 或 `settingsSections`。
4. 发布前重新生成 `src/knoarbor/ui/dist`，确保旧 DocsPage chunk 不再随包分发。

### P1：图谱前端已改页面关系，后端默认仍偏实体关系

前端图谱已经收敛为页面关系，但 `src/knoarbor/entrypoints/routers/ui.py` 中 `/ui/api/graph` 默认参数仍是 `view=entity`，并且会把非 page 映射回 entity。

建议下一步改为：

- 后端默认 `view="page"`。
- 非 page 输入也回落到 page。
- 如果实体图谱能力暂时不作为产品面，则不再从 UI API 暴露实体默认行为。

### P1：Chat-first / Desktop-first 与旧多页面工作台并行

当前侧栏已经收缩为 Chat / Flows / Knowledge，但二级导航仍保留大量旧控制台页面。README 也仍把 CLI/API/本地控制台作为并列产品面。

建议先不贸然删除所有页面，而是明确页面等级：

- 长期主入口：Chat、Knowledge、Settings。
- 桌面诊断/流程页：Runs、Ingest、Lint、Reports、Tokens。
- 待评估是否隐藏：Overview、Sources、Query。

如果目标是更彻底的桌面端产品，应进一步把诊断页放到“高级/开发者”区域，而不是主产品导航。

### P2：Vault 选择兼容层散落

相关位置：

- `web/src/vaultRuntime.ts`
- `web/src/api/client.ts`
- `src/knoarbor/core/vault_selection.py`
- `src/knoarbor/core/vaults.py`
- `src/knoarbor/services/chat_context.py`

当前同时支持 `vault_id`、`vault_path`、虚拟 `all`、默认 vault，多层都有选择逻辑。建议建立唯一 vault selector 契约：

- 前端只提交 `{ vault_id }` 或 `{ scope: "all" }`。
- 后端统一解析为 `VaultSelection` / `VaultTarget`。
- 除迁移和资产 URL 外，业务请求尽量不直接传绝对 `vault_path`。

### P2：配置发现和 legacy 迁移需要定期收口

`ui_config.py` 和 `desktop/src/main/config.ts` 都保留了配置兜底、示例配置推断、legacy app data 迁移。当前它们能保护用户升级，但会增加后续行为分歧。

建议定义 2.x 内唯一配置发现顺序，并将 legacy 迁移标记为有时限逻辑，后续版本移除。

## 三、测试治理

### P0：没有立即破坏覆盖的测试问题

未发现必须立刻处理的测试 P0。`__pycache__` 已被 `.gitignore` 忽略，不是版本污染；只是本地统计和阅读时会造成干扰。

### P1：大测试文件职责混杂，需要按功能域拆分

优先拆分对象：

- `tests/test_lint_pipeline.py`：混有 deterministic scan、candidate scoring、semantic maintenance、write/apply/rescan、trend report。
- `tests/test_ingest_pipeline.py`：混有 source connector、segmentation、document processing、write gate、ledger/report、checkpoint/lifecycle。
- `tests/test_chat_agent.py`：混有 planning、retrieval、session persistence、API stream、image generation、memory。
- `tests/test_api_surface.py`：混有 OpenAPI 契约、vault/profile、query/reports/runs、queued ingest/lint、wiki pages。
- `tests/test_ui_api.py`：混有 UI 资产、config form、diagnostics、status、graph API。

建议目标结构：

- `tests/core/`
- `tests/storage/`
- `tests/retrieval/`
- `tests/semantic/`
- `tests/pipelines/ingest/`
- `tests/pipelines/lint/`
- `tests/services/chat/`
- `tests/api/`
- `tests/cli/`
- `tests/integrations/`
- `tests/contracts/`
- `tests/evals/`

第一阶段只搬迁，不改断言，避免重构测试本身引入噪音。

### P1：重复 fixture 应沉淀到 harness

重复明显的 fixture：

- 临时 vault/config 创建。
- `vaults/all` 目录结构。
- wiki page 写入，如 `wiki/pages/Agent.md`。
- `KnoArborConfig + ConnectorConfig` 测试配置。
- fake semantic workflow / scripted chat client / fake services。

建议在 `tests/harness/` 中补齐：

- `vaults.py`：创建临时 vault、默认 config、初始化 wiki。
- `pages.py`：写入标准页面、source digest、raw assets。
- `chat.py`：fake chat services、scripted planner、image provider。
- `pipelines.py`：fake ingest/lint semantic workflow。

### P2：历史测试和新增回归测试需要归位

应保留但归位：

- `REMOVED_PROTOTYPE_ROUTES`：迁到 `tests/contracts/test_removed_routes_contract.py`。
- chat archive fixture：迁到 `tests/evals/test_chat_fixtures.py`。
- chat memory / retrieval policy：迁到 `tests/services/chat/test_memory.py` 和 `tests/services/chat/test_retrieval_policy.py`。
- chat image generation 回归：迁到 `tests/services/chat/test_image_tool.py`，并与 `tests/test_image_generation.py` 保持层级区分。
- vault scope 回归：按 API、CLI、integration 分别归位。
- ingest write gate / lifecycle：迁到 `tests/pipelines/ingest/test_write_gate.py` 和 `tests/pipelines/ingest/test_lifecycle.py`。

已发现一个机械重复断言：

- `tests/test_ingest_pipeline.py` 中连续两次断言 `missing_operation_claim_trace`，后续清理时应去重或改成真实预期。

## 建议执行顺序

### 第一轮：残留收口，低风险高收益

目标：清掉已经确定不再暴露的文档入口和实体图谱默认行为。

建议修改：

- 删除后端 docs API 和 docs asset resolver。
- 删除 UI contract 中 docs route。
- 重命名 settings 复用文案，移除 docs 文案残留。
- 后端 graph 默认改为 page-only。
- 重新构建并确认 dist 中没有 DocsPage chunk。

验证：

- `npm --prefix web run check:i18n`
- `npm --prefix web run build`
- `npm --prefix desktop run typecheck`
- `python -m pytest tests/test_ui_api.py tests/test_api_surface.py`

### 第二轮：Chat 结构拆分

目标：降低后续对话、附件、生图、memory、工具调用继续叠加时的复杂度。

建议修改：

- 提取 `ChatOrchestrator`。
- 提取 planner context builder。
- 提取 telemetry/event publisher。
- 提取 persistence coordinator。
- 拆 `chat_tools.py` 为工具 handler 目录。
- router 中提取 SSE adapter 和 session workflow service。

验证：

- chat 相关测试全量。
- image generation 回归。
- chat session persistence 回归。
- stream API 回归。

### 第三轮：前端控制器和 API client 拆分

目标：把桌面 renderer 从“全局 hook 中心化”改成领域 hook。

建议修改：

- 拆 `useAppController.ts`。
- 拆 `api/client.ts`。
- 保留 re-export 门面，逐步迁移页面 import。

验证：

- `npm --prefix web run build`
- 关键页面手测：Chat、Knowledge、Runs、Settings。
- 桌面 typecheck。

### 第四轮：测试目录治理

目标：让测试文件能按功能域定位，减少新增回归继续堆到大文件。

建议修改：

- 建立测试目录结构。
- 先搬迁大文件中的独立 test case。
- 沉淀 harness。
- 最后做参数化和重复断言清理。

验证：

- 每次迁移后跑被迁移子集。
- 最后跑后端测试全量。

## 暂不建议立即做的事

- 不建议一次性删除所有 Web UI 页面。当前它们仍是桌面端调试和流程可视化的主要承载，应先分级隐藏或改为高级入口。
- 不建议同时大拆 chat 和 ingest。两者都是高价值、高风险编排层，应分轮处理。
- 不建议先大规模改测试断言。先搬迁归类，再抽 fixture，最后再减少重复断言。
- 不建议为了行数而拆文件。拆分标准应是“变化原因”和“职责边界”，不是固定行数阈值。
