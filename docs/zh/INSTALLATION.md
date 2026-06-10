# 安装部署

KnoArbor 是本地优先的 Python 服务，并内置管理界面。首次部署通常包括：
克隆仓库、创建本地配置、启动 FastAPI 服务，并在浏览器中打开界面。

## 环境要求

- Python 3.12
- `uv`
- 一个 OpenAI 兼容模型供应商
- 可选：只有在重新构建前端时才需要 Node.js 20+

## 本地安装

```bash
git clone https://github.com/pxcg/knoarbor.git
cd knoarbor
uv sync
uv run knoar first-run --vault ./wiki
```

创建本地密钥和配置文件：

```bash
cp .env.example .env
```

编辑 `.env`，至少填写一个模型密钥，例如：

```bash
DEEPSEEK_API_KEY=your-key
```

加载环境变量：

```bash
set -a && source .env && set +a
```

运行只读诊断：

```bash
uv run knoar doctor
```

启动服务：

```bash
uv run knoar serve
```

服务会打印当前 UI 和 API 地址。如果 `8000` 已被占用，KnoArbor 会选择下一个
可用本地端口，并把运行端点写入 `.knoarbor/endpoint.json` 和
`~/.knoarbor/endpoint.json`。

## 验证安装

打开界面：

```text
http://127.0.0.1:8000
```

运行内置 Markdown 示例：

```bash
uv run knoar ingest --connector markdown --write
uv run knoar lint --mode structural
uv run knoar query "Agent Loop 是什么？"
```

生成的 Wiki 页面和报告会写入配置的 `wiki/` 目录。

## 模型供应商

模型供应商配置在 `config.yaml`；密钥保存在 `.env`。DeepSeek、OpenAI、
OpenRouter、Ollama、LM Studio、vLLM 和其他 OpenAI 兼容端点都使用同一种
provider 结构：

```yaml
models:
  default_provider: deepseek
  providers:
    deepseek:
      base_url: https://api.deepseek.com
      api_key_env: DEEPSEEK_API_KEY
      model: deepseek-v4-flash
```

Ollama 或 vLLM 等本地端点可以使用 `api_key_env: null`。启动本地模型端点后，
运行 `uv run knoar doctor --json`，确认配置中的模型已经暴露出来。本地模型还应配置
provider 级 `context_window` 和 `max_output_tokens`，例如 `context_window: 32768`、
`max_output_tokens: 8000`。

## 富文档处理

Markdown 文件会直接进入知识编译。PDF、DOCX、PPTX 等富文档需要配置
MinerU 兼容预处理服务。KnoArbor 不分发 MinerU 或模型权重；启用该适配器时，
用户需要自行安装并运行 MinerU。

## 重新构建前端

仓库已经包含构建后的 UI 资源。只有修改前端时才需要重新构建：

```bash
cd web
npm install
npm run build
cd ..
```

构建结果会复制到 `src/knoarbor/ui/dist/`，由 Python 服务提供。

## 常用检查

```bash
uv run knoar doctor
uv run knoar status
uv run knoar sources --catalog
uv run knoar runs
```

模型、界面、知识编译和运行端点问题见 [故障排查](TROUBLESHOOTING.md)。
