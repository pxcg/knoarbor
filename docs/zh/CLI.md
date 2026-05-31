# 命令行

KnoArbor 提供 `knoarbor` 和简写命令 `knoar`。

## 初始化

```bash
uv run knoar init --vault ./wiki
```

## 启动服务

```bash
uv run knoar serve
```

启动后访问：

```text
http://127.0.0.1:8000
```

## 本地诊断

`doctor` 是只读诊断命令，用于首次运行或排查问题。它检查配置文件、Wiki
目录、默认模型供应商、API Key 环境变量、来源连接器、可选文档预处理器和最近运行状态；不会调用模型，也不会写入 Wiki。

```bash
uv run knoar doctor
uv run knoar doctor --connector markdown
uv run knoar doctor --json
```

## 知识编译

语义知识编译前，可以先检查配置的来源连接器：

```bash
uv run knoar sources --connector codex --json
```

`sources --json` 默认输出紧凑的 preflight 元数据。只有需要完整标准化
`SourceDocument.content` 时，才使用 `--include-content`。

```bash
uv run knoar ingest --write
uv run knoar ingest --connector markdown --write
```

`ingest` 属于长任务。面向人的 CLI 输出默认会进入本地运行队列并跟随进度，
持续打印事件和心跳状态。需要纯机器可解析输出时使用 `--json`；需要同步摘要
输出时使用 `--no-follow`。

处理一个标准化 source document：

```bash
uv run knoar ingest-document --input /path/to/source_document.json --write
```

处理一个本地文件路径。Markdown 直接进入知识编译；PDF、DOCX、PPTX 等富文档需要先在配置中启用 MinerU-compatible 预处理器。

```bash
uv run knoar ingest-file --input /path/to/note.md --write
uv run knoar ingest-file --input /path/to/paper.pdf --write
uv run knoar ingest-file --input /path/to/paper.pdf --write --no-follow
```

## 校验维护

```bash
uv run knoar lint-run
uv run knoar lint-run --mode quality
uv run knoar lint-run --mode full --apply-reviewed
```

`lint-run` 同样默认跟随进度；使用 `--json` 输出结构化结果，或用
`--no-follow` 获取同步摘要。

## 查询

```bash
uv run knoar query "检索主题"
uv run knoar query --write-report "Agent Loop 是什么？"
```

查询阶段返回的是本地 Wiki 上下文，不负责替代宿主 AI 生成最终聊天回答。使用 `--write-report` 时，会在 `maintenance/query_report_*.md` 写入一次查询报告。

## 异步运行

长任务可以通过 run 命令查看进度、事件和取消状态。

```bash
uv run knoar runs --vault ./wiki
uv run knoar run-events RUN_ID --vault ./wiki
uv run knoar run-cancel RUN_ID --vault ./wiki
```

## 调试语义契约

```bash
uv run knoar contracts
uv run knoar run-contract source_normalize --input /path/to/input.json
```
