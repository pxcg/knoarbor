# UI 契约

本文档冻结当前桌面 renderer 的 UI 产品表面。由 Python 托管的浏览器控制台在桌面优先过渡期只是开发辅助入口。本文档描述每个表面展示什么，以及消费哪一类数据契约。

## 表面模型

KnoArbor 使用对话优先的界面，并提供辅助工作区。

| 表面 | 用途 | 主要数据 |
| --- | --- | --- |
| Chat | 询问已维护的 Wiki 页面并延续会话 | chat sessions、evidence packs、citations |
| Flows | 运行和检查流程 | runs、reports、ingest/lint/query requests |
| Knowledge | 浏览维护后的页面和图谱视图 | wiki pages、graph index、page content |
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
- 从 wiki index provider 派生的页面图谱视图。

默认页面浏览器展示维护后的 Wiki 页面。Source digest 通过溯源/来源审计视图、图谱侧栏、报告和引用展示。

图谱视图：

- 页面图：节点是 wiki/source 页面，边是页面链接或 index provider 暴露的语义邻近页面边。

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

在桌面应用中，设置持久化通过 Electron desktop bridge 完成，避免配置内容经浏览器 `fetch` 发送。浏览器/开发模式在相关路由退休前仍可使用 HTTP 配置适配器。

## UI 专用 API 适配器

Python 托管的 `/ui` 静态控制台只是过渡期开发者入口。Renderer 所需的运行时数据通过业务本地端点暴露，例如 `/vaults/status`、`/wiki/graph`、`/tokens` 和 `/vault-assets/*`。打包后的桌面端设置写入使用 Electron bridge，而不是浏览器 HTTP。

外部集成使用 `docs/API_COMPATIBILITY.md` 中的公开 API。

## 渲染规则

- Wiki 页面按冻结页面章节顺序渲染。
- Source digest 页面按审计章节顺序渲染。
- 附件表格对长文本自动换行，并使用可读标签。
- 默认页面渲染隐藏 raw asset 路径和 parser metadata；审计/来源详情视图可以展示这些信息。
