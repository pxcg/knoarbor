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

## 2. 首次运行

```bash
uv run knoar first-run --vault ./wiki
```

这会创建 `config.yaml`，初始化 `./wiki`，并把 `agent-loop.md` 示例复制到
`wiki/raw/notes/`。

创建 `.env` 并填写至少一个模型密钥：

```bash
cp .env.example .env
DEEPSEEK_API_KEY=your-key
```

运行语义流程前，将环境变量加载到当前 shell：

```bash
set -a && source .env && set +a
```

运行只读诊断，确认配置、模型环境变量、来源连接器和 Wiki 目录是否可用：

```bash
uv run knoar doctor
```

`doctor` 不会调用模型，也不会写入 Wiki 页面。

## 3. 启动服务和控制台

```bash
uv run knoar serve
```

如果 `8000` 已被占用，服务会自动选择下一个可用本地端口，并打印实际地址。

打开：

```text
http://127.0.0.1:8000
```

## 4. 运行内置示例

编译为 Wiki 页面：

```bash
uv run knoar ingest --connector markdown --write
```

运行结构维护：

```bash
uv run knoar lint --mode structural
```

查询生成后的 Wiki：

```bash
uv run knoar query "Agent Loop 是什么？"
```

## 5. 运行主要流程

知识编译：

```bash
uv run knoar ingest --write
```

校验维护：

```bash
uv run knoar lint
uv run knoar lint --mode quality
uv run knoar lint --mode full --apply-reviewed
```
