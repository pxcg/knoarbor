# UI 契约

本文档冻结当前本地 Web 控制台和桌面壳的 UI 表面。它描述每个表面展示什么，以及消费哪一类数据契约。

## 表面模型

KnoArbor 使用对话优先的界面，并提供辅助工作区。

| 表面 | 用途 | 主要数据 |
| --- | --- | --- |
| Chat | 询问已维护的 Wiki 页面并延续会话 | chat sessions、evidence packs、citations |
| Flows | 运行和检查流程 | runs、reports、ingest/lint/query requests |
| Knowledge | 浏览维护后的页面和图谱视图 | wiki pages、graph index、page content |
| Settings 弹窗 | 配置知识库、输入、预处理、模型、运行参数 | config form、diagnostics、models |

## Chat

Chat 展示：

- 全局会话列表；
- 可滚动查看完整历史记录的知识库会话分组，包括通过摘要分页取得的旧会话；
- 当前会话；
- 当前模型；
- 当前消息的知识库范围；
- 回答正文、正文引用、引用控件和后续追问建议。

全局 Chat 使用全部已配置知识库作为检索范围。知识库会话使用单个知识库作为检索范围，并将会话存储在该知识库的运行时 chat 状态中。

Chat 消费 chat 服务契约：

```text
session -> turns -> tool trace -> evidence pack -> answer -> citations
```

引用预览归当前选中的会话所有。新建或打开另一个会话时关闭原预览；前一会话较晚
返回的来源读取结果会被忽略，不得显示到新会话。

## Flows

Flows 汇总流程页面：

- 运行监控；
- 知识编译；
- 校验维护；
- 知识查询；
- 运行报告；
- Token 分析。

导入资料支持本地文件与文件夹、配置来源、已保存会话和可编辑摘录。手动输入与
Chat 选中内容共用一个摘录编辑器，在提交前统一编辑标题、正文和目标知识库，
随后提交公开的 `kind=excerpt` 请求。完整的已保存会话仍是会话范围操作，继续使用
chat-session 契约。

流程页面以 run records 和 reports 为事实来源。页面可以内联展示最近结果，持久记录存储在 `maintenance/reports/**` 和 `.knoarbor/runs/**`。

运行、配置、查询、对话和知识浏览的反馈由对应页面在自身内容区展示。应用壳不提供
跨页面全局通知；运行状态只由运行监控和报告展示。校验维护对用户提供一个统一入口，
内部先执行确定性扫描，再按发现决定模型诊断、修复和复验。

导入运行进入终态后，应用按运行所属知识库失效页面、图谱和查询缓存，不依赖
active-run 数量变化。Wiki 导航目标直接交给后端页面解析器；只有权威 404 才显示
页面已删除。`materialization_pending` 表示事实已经保存，但页面、图谱和检索视图
仍等待重建，界面必须显示为可恢复的视图状态，不能伪装成页面删除。

## Knowledge

Knowledge 汇总：

- 来自 `wiki/pages` 的维护后 Wiki 页面；
- 明确进入来源或溯源视图时展示的结构化 processing record 来源审计详情；
- 从 wiki index provider 派生的页面图谱视图。

默认页面浏览器以冻结 input generation 中的标准化原文作为 Raw 视图，并以
`wiki/pages` 下的确定性 source projection 作为“提取结果”视图。提取结果只用于
检查 synthesis、claims、entities、relations 和 attachments；claim evidence 按需
通过紧凑折叠按钮展开 evidence 预览卡，不显示 source/unit 内部坐标；点击 evidence
卡片后跳转到 Raw 对应位置并短时高亮。Raw 作为连续 Markdown 阅读，不按投影章节
拆成卡片，也不展示关联页面。
Source units 只提供 evidence 坐标，不用于重新拼装原文。标题操作区提供原文与
提取结果的单一切换按钮；桌面端可以在 Finder 中定位本机来源文件，但不显示来源
绝对路径。

面向读者的 Markdown 共用一套随应用打包的 GFM 与 KaTeX 渲染管线。行内
`$...$` 和块级 `$$...$$` 公式在 Raw、Wiki、报告、引用预览与 Chat 中保持一致，
不加载远程资源，也不因此启用任意 HTML。

Chat 只展示一组引用来源，不另设重复的原文证据列表。引用仅包含回答实际选择的
支撑片段；正文中一个编号对应一个 Raw 单元，其紧凑定位符保留全部精确范围。来源
列表按文档分组并同时显示文档数与片段数。点击文档后，右侧打开冻结的 Raw 并标黄
该文档内全部已引用范围；点击 Raw 引用时滚动到首个范围，同时保留其余高亮。互不
相邻的引用范围保持独立，未被回答选择的检索候选不会作为引用展示。高亮持续到用户
关闭预览或选择另一条引用。
引用记录只保存紧凑定位符。打开来源时，渲染器向 Chat 引用解析器请求临时高亮文本；
解析器从对应的不可变 source unit 读取原文，不把文本写入会话。source unit 局部坐标
不得直接作用于完整 Raw；定位符失效时只打开原文而不进行猜测高亮。

`source_index` 编辑器只呈现结构化可编辑字段：synthesis、现有 claim 文本、
entities 和 relations；claim evidence 只作为只读上下文。生成后的 Markdown、身份、
来源、附件和 evidence 坐标不会进入编辑表单或保存请求。保存时以打开编辑器时的
revision 为并发边界，提交 canonical projection-edit revision。
该操作不进入 ingest，且只作用于当前 Raw revision；新 Raw revision 使用重新提取的投影。

Raw 视图提供独立的 Raw revision 编辑器。保存前 UI 明确说明将调用当前模型重新提取，
并由新结果替换当前投影。保存会提交标准 queued ingest 并进入现有运行监控，不覆盖旧
input generation。

图谱视图：

- 页面图：节点是 wiki/source 页面，边是页面链接或 index provider 暴露的语义邻近页面边。

## Settings 弹窗

Settings 配置：

- 知识库 profiles；
- 输入来源；
- 文档预处理；
- 模型供应商和探测；
- 运行限制；
- 诊断；
- 高级 YAML。

设置变更通过配置服务写入。UI 组件调用 API 或服务适配器，不直接写配置文件。
Settings 不提供独立保留路由，只作为工作区弹窗打开。

产品不提供独立的“资料来源”工作区：Settings 负责 connector 配置与诊断，Ingest
负责选择已配置来源并启动运行，Knowledge 负责 Raw 原文与溯源检查。

## UI 专用 API 适配器

机器可读的 `UI_PUBLIC_ROUTES` 集合管理打包 UI 适配器，例如 `/config`、
`/config/form`、`/config/diagnostics`、`/vaults/status`、`/wiki/graph`、
`/tokens` 和 `/vault-assets/*`。这些路由可以聚合配置、本地资产服务、诊断
和展示辅助能力，但具体路径不属于稳定的外部集成 API。

外部集成使用 `docs/API_COMPATIBILITY.md` 中的公开 API。

## 渲染规则

- Raw 视图按冻结的标准化原文渲染，不从 source units 重建正文。
- 提取结果按 synthesis、claims、relations、entities、attachments 的稳定顺序渲染。
- Claims 默认展示断言正文，原文 evidence 折叠后按需展开。
- Source record 页面按审计章节顺序渲染。
- 附件表格对长文本自动换行，并使用可读标签。
- 默认页面渲染隐藏 raw asset 路径和 parser metadata；审计/来源详情视图可以展示这些信息。
