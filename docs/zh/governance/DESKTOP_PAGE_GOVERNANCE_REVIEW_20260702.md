# 桌面端页面治理专项审查

日期：2026-07-02

## 结论

当前桌面端页面值得做一轮专项治理。主要问题不是单个组件行数过多，而是页面层、全局控制器、API 客户端、React Query 缓存和 Electron 桥接之间的职责边界不够清晰。后续维护桌面端时，问题定位容易在多个文件之间跳转，形成“局部修改能生效，但根因不清”的开发体验。

建议采用分阶段治理，不做一次性大拆。第一阶段优先收口全局状态、query key 和桌面桥接；第二阶段再拆运行页、配置页、会话页等高频页面；第三阶段整理 API 模块与大型展示组件。

## 审查范围

- 桌面主进程与 preload：`desktop/src/main/*`、`desktop/src/preload/*`
- 桌面实际承载的前端页面：`web/src/pages/*`
- 应用壳与侧栏：`web/src/components/AppShell.tsx`、`web/src/components/Sidebar*.tsx`
- 全局控制器与上下文：`web/src/useAppController.ts`、`web/src/appContext.ts`
- API 与缓存键：`web/src/api/*`、`web/src/queryKeys.ts`
- 运行、配置、报告、会话相关复合组件

## 主要发现

### 1. 全局控制器承担过多职责

`web/src/useAppController.ts` 目前集中处理：

- 顶层路由状态、语言、侧栏折叠、vault 选择
- health/config/providers/vaults/status/reports/runs/graph/pages/query trends 等查询
- vault 刷新、全局刷新、预加载、缓存写入
- 桌面菜单命令监听和服务重启
- 页面跳转意图，例如打开报告、打开 wiki、打开会话
- localStorage 持久化

这会让页面问题很容易牵连到全局控制器。建议将它拆成若干明确的 hook，并保持 `AppContext` 的对外形状稳定。

优先拆分方向：

- `useLanguagePreference`
- `useSidebarPreference`
- `useActiveVaultSelection`
- `useAppQueries`
- `useVaultRefresh`
- `useDesktopCommands`
- `useAppNavigationIntents`

### 2. 页面组件混合了业务编排和 UI 渲染

典型页面已经不只是“展示层”：

- `web/src/pages/RunPage.tsx` 同时处理 ingest/lint 表单状态、source catalog 查询、会话查询、桌面文件选择、运行触发、运行结果格式化、最近报告预览。
- `web/src/pages/ConfigPage.tsx` 同时处理配置表单加载、诊断查询、保存、密钥写入、桌面服务重启、模型发现和连通性检测。
- `web/src/pages/chat/useChatController.ts` 已经比页面组件更清晰，但仍同时处理会话恢复、流式生成、重试、消息选择、附件/引用预览、会话入库和侧栏缓存刷新。
- `web/src/pages/ReportsPage.tsx` 同时处理列表筛选、报告详情、运行事件和报告可读视图。
- `web/src/pages/SourcesPage.tsx`、`web/src/pages/TokensPage.tsx` 也有局部裸 query key 和页面级数据编排。

建议页面层只保留布局和事件绑定，将业务编排移入页面专属 hook 或 domain hook。

### 3. Query key 没有完全收口

`web/src/queryKeys.ts` 已经存在，但仍有裸数组 key 分散在页面和组件中，例如：

- `["config-form", context.configPath]`
- `["config-diagnostics", context.configPath]`
- `["models", "providers"]`
- `["run-chat-sessions", context.activeVaultId]`
- `["sidebar-chat-sessions", context.configPath, vaultKey]`
- `["source-knoarbor-chat-sessions", context.activeVaultId]`

这会增加刷新失效、缓存命中和跨组件同步的排查成本。建议所有跨组件、跨页面、可失效的 key 都进入 `queryKeys.ts`，局部临时 key 才允许留在组件内。

### 4. Electron 桥接在前端页面中分散使用

`window.knoarborDesktop` 直接出现在页面和组件中，包括：

- `web/src/useAppController.ts`
- `web/src/pages/RunPage.tsx`
- `web/src/pages/ConfigPage.tsx`
- `web/src/components/config/ConfigFormControls.tsx`
- `web/src/components/config/ConfigSettingsSections.tsx`
- `web/src/main.tsx`

这会让页面同时承担“是否桌面环境”“调用哪个 IPC”“失败怎么处理”的判断。建议新增前端侧桌面桥接层，例如：

- `web/src/desktop/desktopBridge.ts`
- `web/src/desktop/useDesktopBridge.ts`
- `web/src/desktop/useFilePicker.ts`
- `web/src/desktop/useDesktopService.ts`

页面只调用稳定函数，例如 `selectDirectory`、`selectFile`、`saveEnvSecretsAndRestart`、`openPath`。

### 5. API 客户端和类型文件偏重

`web/src/api/client.ts` 和 `web/src/api/types.ts` 都已经承担多个领域的接口。随着桌面端页面继续扩展，单文件 API 会导致查找成本上升。

建议按领域拆分：

- `web/src/api/config.ts`
- `web/src/api/runs.ts`
- `web/src/api/chat.ts`
- `web/src/api/wiki.ts`
- `web/src/api/reports.ts`
- `web/src/api/sources.ts`
- `web/src/api/tokens.ts`
- `web/src/api/system.ts`

类型也可以按领域迁移到 `web/src/api/types/*`，或放在对应 API 模块旁边。考虑到项目目前倾向于减少历史兼容，可以不长期保留一个巨大的兼容 re-export 层，但拆分过程应保持一次改动可验证。

### 6. 若干复合组件存在二次拆分价值

以下文件不只是“行数大”，而是内部有多个自然职责：

- `web/src/components/config/ConfigModelProvidersSection.tsx`
  - 文本模型 provider
  - 图像模型 provider
  - adapter 设置
  - api key 状态
  - discover/probe 操作
- `web/src/components/config/ConfigSettingsSections.tsx`
  - 基础目录
  - 输入源
  - 预处理
  - 运行时参数
  - 桌面路径打开/选择
- `web/src/components/runs/RunPanels.tsx`
  - 阶段模型
  - 时间线
  - 事件列表
  - 运行诊断
  - flow guide
- `web/src/components/report/ReportReadableView.tsx`
  - 报告解析结果展示
  - 页面 artifact 展示
  - inline page preview
  - 旧报告字段兼容展示

建议先拆数据/行为，再拆视觉组件。只按行数拆文件会让 prop 传递更复杂。

## 建议治理顺序

### Phase 1：收口根边界

目标是降低后续排查成本，风险较低。

- 将裸 query key 迁入 `queryKeys.ts`
- 新增 `web/src/desktop/*` 桥接层，页面不直接访问 `window.knoarborDesktop`
- 从 `useAppController.ts` 中抽出偏基础的 hook：
  - 语言偏好
  - 侧栏偏好
  - vault 选择
  - 桌面菜单命令
  - 全局刷新和 vault 刷新
- 保持 `AppContext` 外部合同基本不变

### Phase 2：治理高频页面

优先处理最容易造成局部修补的页面。

- `RunPage`
  - `useRunLauncher`
  - `RunInputForm`
  - `LintLaunchPanel`
  - `RunOutputPanel`
  - `LatestWorkflowReport`
- `ConfigPage`
  - `useConfigFormController`
  - `useConfigModelActions`
  - `ConfigSaveActions`
  - `ConfigDiagnosticsSection`
- `ChatPage/useChatController`
  - `useChatSessionLifecycle`
  - `useChatStreaming`
  - `useChatSelectionIngest`
  - `useCitationPreview`

### Phase 3：整理 API 与类型归属

目标是让页面查 API 时能按领域定位。

- 按领域拆分 `web/src/api/client.ts`
- 按领域拆分或搬迁 `web/src/api/types.ts`
- 清理页面对 API 的大包导入
- 让每个页面主要依赖自己的 domain API

### Phase 4：拆分大型展示组件

目标是提升长期可维护性，不影响核心行为。

- 拆分配置 provider section
- 拆分运行面板
- 拆分报告可读视图的预览与 artifact 展示
- 对 wiki/graph/chat 的模型层继续保持纯函数优先

## 验收标准

建议本轮页面治理完成时满足以下标准：

- `useAppController.ts` 只负责组装顶层 context，不直接容纳大段业务编排。
- 页面组件以布局和事件绑定为主，页面级 hook 承担数据和行为。
- 除 `web/src/desktop/*` 和 `web/src/main.tsx` 外，页面组件不直接访问 `window.knoarborDesktop`。
- 跨页面 query key 全部来自 `queryKeys.ts`。
- 运行页、配置页、会话页的问题定位可以先进入对应 hook，而不是先进入全局 controller。
- API 按功能领域可定位，避免所有页面都从一个大 `client.ts` 中找接口。
- 每个阶段完成后执行 `npm --prefix web run build`，涉及行为变更时补充或运行相关测试。

## 建议先做的代码修改

第一轮实现建议只做低风险收口：

1. 扩展 `queryKeys.ts`，替换页面中的裸 query key。
2. 新增前端桌面桥接层，迁移文件选择、路径打开、密钥保存、服务重启调用。
3. 从 `useAppController.ts` 抽出偏独立的 preference 和 desktop command hooks。

这一轮不会改变桌面端功能，但会让后续治理 `RunPage`、`ConfigPage`、`ChatPage` 时根因更容易定位。
