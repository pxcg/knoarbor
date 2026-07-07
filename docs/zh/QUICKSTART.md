# 快速开始

本页用于从一个新的本地仓库跑通第一次 KnoArbor 知识库对话。建议先使用内置
Markdown 示例，确认流程成功后，再添加自己的资料来源。

## 推荐首次路径

第一次运行时建议保持配置简单：

- 使用内置 `agent-loop.md` 示例；
- 使用一个模型供应商，例如 DeepSeek、OpenAI、OpenRouter、LM Studio、vLLM 或 Ollama 原生端点；
- 在语义流程前先运行 `doctor`；
- 最后在桌面端 Chat 验证结果；源码运行时也可以使用开发者控制台。

## 1. 安装依赖

需要：

- Python 3.12
- `uv`
- 一个模型供应商

安装依赖：

```bash
uv sync
```

## 2. 初始化知识库

创建本地配置、初始化默认知识库，并安装内置示例资料：

```bash
uv run knoar first-run --vault ./vaults/default
```

这会创建 `config.yaml`，初始化 `./vaults/default`，并把 `agent-loop.md` 示例复制到
`vaults/default/raw/inbox/notes/`。

编辑 `config.yaml` 或设置页，为一个模型供应商填写 `base_url`、`api_key` 和
`model`。

运行只读诊断：

```bash
uv run knoar doctor
```

`doctor` 会检查配置、知识库结构、模型供应商设置、来源连接器、可选文档预处理和最近运行状态。
它不会调用模型，也不会写入 Wiki 页面。

## 3. 编译内置示例

将内置 Markdown 来源编译成已维护 Wiki 页面：

```bash
uv run knoar ingest --connector markdown --write
```

运行结构维护：

```bash
uv run knoar lint --mode deterministic
```

生成后的 Wiki 页面位于：

```text
vaults/default/wiki/pages/
```

如果只希望在 Obsidian 中打开维护后的 Markdown Wiki，请打开这个 `wiki/pages/` 目录，
而不是整个运行时知识库目录。这样可以避开 raw、报告和机器状态文件。

## 4. 打开 Chat

桌面应用中，直接打开工作区并进入 **对话**。

源码运行时，先启动本地服务：

```bash
uv run knoar serve
```

如果 `8000` 已被占用，服务会自动选择下一个可用本地端口，并打印实际地址。

然后打开开发者控制台：

```text
http://127.0.0.1:8000
```

在 Chat 中：

1. 打开 **对话**。
2. 提问 `Agent Loop 是什么？`。
3. 展开回答下方的引用来源。
4. 点击引用，在对话中预览对应 Wiki 页面。

这条路径会验证主要用户体验：资料来源 -> 知识编译 -> 已维护 Wiki 页面 -> 带引用的对话回答。

## 5. 用 CLI 验证

也可以在终端查询生成后的 Wiki：

```bash
uv run knoar query "Agent Loop 是什么？"
```

如果更喜欢完整命令名，也可以使用 `knoarbor`：

```bash
uv run knoarbor --help
```

## 6. 添加自己的资料来源

内置示例跑通后，可以在 `config.yaml` 或桌面端设置中添加自己的来源目录，然后运行：

```bash
uv run knoar ingest --write
```

对于一个已经准备好的 `source_document.v1` JSON 文件：

```bash
uv run knoar ingest --source-document /path/to/source_document.json --write
```

## 7. 维护 Wiki

结构修复：

```bash
uv run knoar lint
```

质量审查：

```bash
uv run knoar lint --mode semantic
```

应用通过审查的语义维护操作：

```bash
uv run knoar lint --mode semantic --apply-reviewed
```

## 下一步文档

- [配置说明](CONFIGURATION.md)：模型供应商、知识库、输入来源和文档预处理。
- [命令行](CLI.md)：完整命令行参数。
- [故障排查](TROUBLESHOOTING.md)：常见配置、模型和运行时问题。
