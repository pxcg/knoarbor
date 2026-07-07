# 安装部署

KnoArbor 是桌面端优先的本地知识引擎，底层由 Python runtime 服务承载。公开发布包是普通用户的默认路径；源码安装仍是贡献者和希望直接运行本地服务 API 的用户的参考路径。

## 环境要求

- Python 3.12
- `uv`
- 一个模型供应商，可以是 OpenAI 兼容端点或 Ollama 原生端点
- 可选：只有在重新构建桌面 renderer 时才需要 Node.js 20+

## 本地安装

```bash
git clone https://github.com/pxcg/knoarbor.git
cd knoarbor
uv sync
uv run knoar first-run --vault ./vaults/default
```

创建本地配置文件：

```bash
cp config.example.yaml config.yaml
```

编辑 `config.yaml` 或设置页，为模型供应商填写 `base_url`、`api_key` 和
`model`。

运行只读诊断：

```bash
uv run knoar doctor
```

为源码开发启动服务：

```bash
uv run knoar serve
```

服务会打印当前本地 API 和开发者控制台地址。如果 `8000` 已被占用，KnoArbor 会选择下一个
可用本地端口，并把运行端点写入 `.knoarbor/endpoint.json` 和
`~/.knoarbor/endpoint.json`。

## 验证安装

源码开发时可以打开开发者控制台：

```text
http://127.0.0.1:8000
```

运行内置 Markdown 示例：

```bash
uv run knoar ingest --connector markdown --write
uv run knoar lint --mode deterministic
uv run knoar query "Agent Loop 是什么？"
```

生成的 Wiki 页面和报告会写入配置的 vault 目录，例如 `vaults/default/`。

如果 Windows 没有启用长路径支持，建议把项目和 vault 放在较短路径下，例如
`C:\knoarbor` 或 `%USERPROFILE%\knoarbor`。

## 模型供应商

模型供应商配置在 `config.yaml`。DeepSeek、OpenAI、
OpenRouter、LM Studio、vLLM 和其他 OpenAI 兼容端点都使用同一种 provider
结构。Ollama 可以使用 OpenAI 兼容层，也可以使用 KnoArbor 的原生
`adapter: ollama`：

```yaml
models:
  default_provider: deepseek
  providers:
    deepseek:
      base_url: https://api.deepseek.com
      api_key:
      model: deepseek-v4-flash
```

Ollama 或 vLLM 等本地端点可以留空 `api_key`。启动本地模型端点后，
运行 `uv run knoar doctor --json`，确认配置中的模型已经暴露出来。本地模型还应配置
provider 级 `context_window` 和 `max_output_tokens`，例如 `context_window: 32768`、
`max_output_tokens: 8000`。

Ollama 原生示例：

```yaml
models:
  default_provider: ollama
  providers:
    ollama:
      adapter: ollama
      base_url: http://127.0.0.1:11434
      api_key:
      model: qwen3.6:27b-q4_K_M
      json_mode: true
      context_window: 262144
      max_output_tokens: 8000
```

## 富文档处理

Markdown 文件会直接进入知识编译。PDF、DOCX、PPTX 等富文档需要配置
MinerU 兼容预处理服务。KnoArbor 不分发 MinerU 或模型权重；启用该适配器时，
用户需要自行安装并运行 MinerU。

如果使用本地 MinerU 源码仓库，可以这样启动兼容 API：

```bash
cd /path/to/MinerU
.venv/bin/mineru-api --host 127.0.0.1 --port 18000
```

然后将 `document_processing.mineru.endpoint` 配置为
`http://127.0.0.1:18000/file_parse`。如果 MinerU 写出了图片资源，KnoArbor 会
把它们记录为 Markdown sidecar 附件，并在 source digest 审计页中展示。

聊天来源默认路径如 `~/.codex/sessions`、`~/.claude/projects` 和
`~/.hermes/sessions` 会展开到当前用户主目录。Windows 下对应路径通常位于
`%USERPROFILE%`，例如 `C:\Users\Alice\.codex\sessions`。

## 重新构建 renderer

仓库已经包含构建后的 renderer 资源。只有修改桌面 renderer 时才需要重新构建：

```bash
cd renderer
npm install
npm run build
cd ..
```

构建结果写入 `renderer/dist/`。源码开发时 Python 开发者控制台读取该目录；桌面打包会把它复制到 `desktop/resources/renderer/`。

## 常用检查

```bash
uv run knoar doctor
uv run knoar status
uv run knoar sources --catalog
uv run knoar runs
```

模型、界面、知识编译和运行端点问题见 [故障排查](TROUBLESHOOTING.md)。
