# 快速开始

本页用于从一个新的本地仓库启动 KnoArbor。

## 1. 安装依赖

需要：

- Python 3.12
- `uv`
- 一个 OpenAI 兼容模型供应商，例如 DeepSeek、OpenAI、OpenRouter、Ollama 或 LM Studio

安装依赖：

```bash
uv sync
```

## 2. 创建配置

```bash
cp config.example.yaml config.yaml
cp .env.example .env
```

在 `.env` 中填写至少一个模型密钥：

```bash
DEEPSEEK_API_KEY=your-key
```

运行语义流程前，将环境变量加载到当前 shell：

```bash
set -a && source .env && set +a
```

## 3. 初始化 Wiki 目录

```bash
uv run knoar init --vault ./wiki
```

`wiki/` 是运行时目录，默认不提交到 git。

运行只读诊断，确认配置、模型环境变量、来源连接器和 Wiki 目录是否可用：

```bash
uv run knoar doctor
```

`doctor` 不会调用模型，也不会写入 Wiki 页面。

## 4. 启动服务和控制台

```bash
uv run knoar serve
```

如果 `8000` 已被占用，服务会自动选择下一个可用本地端口，并打印实际地址。

打开：

```text
http://127.0.0.1:8000
```

## 5. 运行内置示例

把示例 Markdown 笔记复制到默认 raw notes 目录：

```bash
mkdir -p wiki/raw/notes
cp examples/agent-loop.md wiki/raw/notes/agent-loop.md
```

编译为 Wiki 页面：

```bash
uv run knoar ingest --connector markdown --write
```

运行结构维护：

```bash
uv run knoar lint-run --mode structural
```

查询生成后的 Wiki：

```bash
uv run knoar query "Agent Loop 是什么？"
```

## 6. 运行主要流程

知识编译：

```bash
uv run knoar ingest --write
```

校验维护：

```bash
uv run knoar lint-run
uv run knoar lint-run --mode quality
uv run knoar lint-run --mode full --apply-reviewed
```
