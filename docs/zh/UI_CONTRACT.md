# UI 契约

本文档冻结当前本地 Web 控制台和桌面壳的 UI 表面。它描述每个表面展示什么，以及消费哪一类数据契约。

## 表面模型

KnoArbor 使用对话优先的界面，并提供辅助工作区。

| 表面 | 用途 | 主要数据 |
| --- | --- | --- |
| Chat | 询问已维护的 Wiki 页面并延续会话 | chat sessions、evidence packs、citations |
| Flows | 运行和检查流程 | runs、reports、ingest/lint/query requests |
| Knowledge | 浏览维护后的页面和图谱视图 | wiki pages、graph index、page content |
| Docs | 阅读项目文档 | bundled docs |
| Settings | 配置知识库、输入、预处理、模型、运行参数 | config form、diagnostics、models |

## Chat

Chat 展示：

- 全局会话列表；
- 知识库范围内的会话分组；
- 当前会话；
- 当前模型；
- 当前消息的知识库范围；
- 回答正文、正文引用、引用控件和后续追问建议。

全局 Chat 使用全部已配置知识库作为检索范围。知识库会话使用单个知识库作为检索范围，并将会话存储在该知识库的运行时 chat 状态中。

Chat 消费 chat 服务契约：

```text
session -> turns -> tool trace -> evidence pack -> answer -> citations
```

## Flows

Flows 汇总流程页面：

- 运行监控；
- 知识编译；
- 校验维护；
- 知识查询；
- 运行报告；
- Token 分析。

流程页面以 run records 和 reports 为事实来源。页面可以内联展示最近结果，持久记录存储在 `maintenance/reports/**` 和 `.knoarbor/runs/**`。

## Knowledge

Knowledge 汇总：

- 来自 `wiki/pages` 的维护后 Wiki 页面；
- 明确进入来源或溯源视图时展示的 `wiki/sources` 来源审计页；
- 从 `.knoarbor/index/graph_index.json` 派生的图谱视图。

默认页面浏览器展示维护后的 Wiki 页面。Source digest 通过溯源/来源审计视图、图谱侧栏、报告和引用展示。

图谱视图：

- 实体图：节点是知识对象，边是 claims 支撑的 relations。
- 页面图：节点是 wiki/source 页面，边是链接或贡献关系。

## Docs

Docs 展示公开项目文档。内部 specs 是开发者参考资料，不作为主要用户文档表面。

## Settings

Settings 配置：

- 知识库 profiles；
- 输入来源；
- 文档预处理；
- 模型供应商和探测；
- 运行限制；
- 诊断；
- 高级 YAML。

设置变更通过配置服务写入。UI 组件调用 API 或服务适配器，不直接写配置文件。

## UI 专用 API 适配器

`/ui/api/*` 下的路由是打包 UI 适配器。它们可以聚合公开 API、配置、本地资产服务和文档辅助能力。

外部集成使用 `docs/API_COMPATIBILITY.md` 中的公开 API。

## 渲染规则

- Wiki 页面按冻结页面章节顺序渲染。
- Source digest 页面按审计章节顺序渲染。
- 附件表格对长文本自动换行，并使用可读标签。
- 默认页面渲染隐藏 raw asset 路径和 parser metadata；审计/来源详情视图可以展示这些信息。
