# 命令行

KnoArbor 提供 `knoarbor` 和简写命令 `knoar`，推荐使用简写命令：

```bash
uv run knoar --help
```

## 全局参数

```bash
uv run knoar --config ./config.yaml <command>
```

如果省略 `--config`，CLI 会优先查找 `config.yaml`，否则回退到
`config.example.yaml`。

## 首次运行

创建本地 `config.yaml`、初始化 Wiki 知识库，并运行只读诊断：

```bash
uv run knoar first-run
uv run knoar first-run --vault ./wiki
uv run knoar first-run --no-example
uv run knoar first-run --json
```

该命令不会调用模型，也不会写入 Wiki 页面。它只准备本地运行环境并提示下一步命令。默认情况下，它会把一个小型 Markdown 示例复制到
`raw/notes/agent-loop.md`，新用户可以直接测试首个页面流程：

```bash
uv run knoar ingest --connector markdown --write
uv run knoar query "Agent Loop 是什么？"
```

## 初始化

```bash
uv run knoar init --vault ./wiki
```

如果 `config.yaml` 不存在，`init` 会先从内置默认配置创建本地配置，再初始化
知识库。已有本地配置不会被覆盖。

## 启动服务

```bash
uv run knoar serve
```

如果配置端口已被占用，KnoArbor 会自动切换到下一个可用本地端口，并在终端
打印实际 UI/API 地址。当前运行端点会同时写入用户级
`~/.knoarbor/endpoint.json` 和 `config.yaml` 同级的项目级
`.knoarbor/endpoint.json`，供本地 skill 或其他集成工具自动发现。

## 本地诊断

`doctor` 是只读诊断命令，用于首次运行或排查问题。它检查配置文件、Wiki
目录、默认模型供应商、API Key 环境变量、来源连接器、可选文档预处理器和最近运行状态；不会调用模型，也不会写入 Wiki。

```bash
uv run knoar doctor
uv run knoar doctor --connector markdown
uv run knoar doctor --json
```

## 资料预检

语义知识编译前，可以先检查配置的来源连接器：

```bash
uv run knoar sources
uv run knoar sources --catalog
uv run knoar sources --connector codex --json
uv run knoar sources --connector codex --json --include-content
```

使用 `--catalog` 可以只打印资料来源连接器能力清单，不扫描本地文件。它会展示
连接器名称、版本、输出的 `source_type`、是否支持断点和分段提示；JSON 输出
还包含轻量 settings schema。

`sources --json` 默认输出紧凑 preflight 元数据。只有需要完整标准化
`SourceDocument.content` 时，才使用 `--include-content`。

## 知识编译

`ingest` 是唯一推荐的知识编译入口。

从已启用来源编译：

```bash
uv run knoar ingest --write
uv run knoar ingest --connector markdown --write
uv run knoar ingest --vault-id personal --connector markdown --write
```

一次性处理文件或文件夹。Markdown 直接进入知识编译；PDF、DOCX、PPTX 等富文档需要先在配置中启用 MinerU-compatible 预处理器：

```bash
uv run knoar ingest --input /path/to/note.md --write
uv run knoar ingest --input /path/to/paper.pdf --write
uv run knoar ingest --input /path/to/folder --write
uv run knoar ingest --input /path/to/paper.pdf --write --no-follow
```

当 `--input` 是文件夹时，KnoArbor 默认递归发现 Markdown 文件。文件夹中的富文档会先通过已配置的
MinerU-compatible 预处理器转换为 Markdown。

处理一个标准化 source document：

```bash
uv run knoar ingest --source-document /path/to/source_document.json --write
```

从失败或部分失败的 ingest 运行恢复：

```bash
uv run knoar ingest --recover-run-id RUN_ID --write
uv run knoar ingest --vault-id personal --recover-run-id RUN_ID --write
```

`ingest` 属于长任务。面向人的 CLI 输出默认会进入本地运行队列并跟随进度，
持续打印事件和心跳状态。需要纯机器可解析输出时使用 `--json`；需要同步摘要
输出时使用 `--no-follow`。

如果配置了多个知识库，知识编译每次只写入一个知识库。使用
`--vault-id <id>` 选择已配置知识库，或使用 `--vault /path/to/wiki` 指定路径。

## 校验维护

`lint` 是唯一推荐的维护入口。

```bash
uv run knoar lint
uv run knoar lint --vault-id personal
uv run knoar lint --mode deterministic
uv run knoar lint --mode structural
uv run knoar lint --mode quality
uv run knoar lint --mode full --profile deep
```

模式说明：

- `deterministic`：只做确定性扫描和安全修复。
- `structural`：结构和溯源维护，必要时进入语义评审。
- `quality`：页面质量诊断和评审维护。
- `full`：结构维护和质量维护一起执行。

`lint` 默认跟随进度；使用 `--json` 输出结构化结果，或用 `--no-follow`
获取同步摘要。

如果配置了多个知识库，校验维护每次只维护一个知识库。使用
`--vault-id <id>` 选择已配置知识库，或使用 `--vault /path/to/wiki` 指定路径。

## 查询

```bash
uv run knoar query "检索主题"
uv run knoar query --mode deep "Agent Loop 是什么？"
uv run knoar query --context-format full "Agent Loop 是什么？"
uv run knoar query --write-report "Agent Loop 是什么？"
uv run knoar query --vault-id personal "Agent Loop 是什么？"
```

查询阶段返回的是本地 Wiki 上下文，不负责替代宿主 AI 生成最终聊天回答。

记录一次查询反馈：

```bash
uv run knoar query-feedback "Agent Loop 是什么？" --useful --selected-path concepts/Agent-Loop.md
```

## 运行监控

长任务可以通过 run 命令查看进度、事件和取消状态。

```bash
uv run knoar runs --vault ./wiki
uv run knoar runs --vault-id personal
uv run knoar runs list --vault ./wiki
uv run knoar runs --active --vault ./wiki
uv run knoar runs events RUN_ID --vault ./wiki
uv run knoar runs events RUN_ID --follow --vault ./wiki
uv run knoar runs cancel RUN_ID --vault ./wiki
```

## 开发诊断

以下命令用于提示词和 schema 调试，不是普通使用入口。

```bash
uv run knoar contracts
uv run knoar run-contract source_normalize --input /path/to/input.json
uv run knoar lint-plan --mode structural
```
