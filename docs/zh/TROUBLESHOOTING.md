# 故障排查

本文聚焦首次运行和本地运行时常见问题。稳定错误码请查看 [错误码](ERROR_CODES.md)。

## 首先检查

运行：

```bash
uv run knoar doctor
uv run knoar status --vault vaults/default
```

`doctor` 是只读检查，会检查配置、知识库结构、模型环境变量、输入来源、文档预处理设置和最近运行状态。

## 配置文件不存在

现象：

```text
[KA-CFG-001] Config file does not exist
```

修复：

```bash
cp config.example.yaml config.yaml
cp .env.example .env
```

然后编辑 `config.yaml` 并加载密钥：

```bash
set -a && source .env && set +a
uv run knoar doctor
```

## API Key 或模型供应商缺失

现象：

- `doctor` 报告模型环境变量缺失。
- ingest 或 lint 在等待模型时失败。
- query 可用，但语义流程失败。

修复：

1. 确认 `config.yaml` 中的 `models.default_provider`。
2. 如果使用托管供应商，确认该 provider 配置了 `api_key_env`。
3. 确认运行 KnoArbor 的 shell 中已经导出对应环境变量。
4. 如果使用 Ollama/vLLM 等本地或内网端点，将 `api_key_env` 设置为 `null`，并确认服务已启动。

示例：

```bash
export DEEPSEEK_API_KEY=...
uv run knoar doctor
```

## UI 打开但没有页面

常见原因：

- 当前知识库还没有生成页面。
- 机器索引过期。
- UI 指向了另一个 vault 路径。

修复：

```bash
uv run knoar --config config.yaml status --vault vaults/default
uv run python - <<'PY'
from pathlib import Path
from knoarbor.storage import update_index
update_index(Path("vaults/default"))
PY
```

然后刷新控制台。

## Ingest 跳过资料

如果 source checkpoint hash 没有变化，跳过通常是预期行为。

检查：

- `vaults/default/maintenance/` 下的 ingest report。
- `config.yaml` 中的 connector roots。
- `uv run knoar sources --connector markdown --json`。

如果确实需要重新处理某个已变化文件，先备份，再只清理相关 checkpoint。不要为了强制 ingest 删除整个知识库。

## PDF 或 Office 文件无法 ingest

Markdown 文件可以直接处理。PDF、DOCX、PPTX、XLSX 等富文档需要配置文档预处理器。

如果没有配置 MinerU，非 Markdown ingest 应返回：

```text
KA-DOC-001
```

修复：

- 启动兼容 MinerU 的服务。
- 配置 `document_processing.mineru.endpoint`。
- 运行 `uv run knoar doctor` 检查预处理器。

## 运行看起来卡住

长语义流程可能正在等待模型调用。查看运行监控：

```bash
uv run knoar runs --vault vaults/default
uv run knoar runs events <run_id> --vault vaults/default
```

需要取消时：

```bash
uv run knoar runs cancel <run_id> --vault vaults/default
```

取消是协作式的。正在进行的模型调用可能会先完成，流程随后在下一个检查点停止。

## 恢复的页面无法搜索

如果手动恢复了 Markdown 页面，需要重建索引：

```bash
uv run python - <<'PY'
from pathlib import Path
from knoarbor.storage import update_index
update_index(Path("vaults/default"))
PY
```

更多恢复说明见 [备份与恢复](BACKUP_AND_RECOVERY.md)。

## 前端构建或 UI 资源问题

修改 UI 源码后运行：

```bash
cd web
npm install
npm run build
```

构建产物会复制到 `src/knoarbor/ui/dist/`，并由 `uv run knoar serve` 提供服务。

## 仍然无法解决

提交 issue 时请包含：

- KnoArbor 版本或 commit。
- 使用的命令或接口。
- 脱敏后的配置片段。
- 脱敏后的错误输出。
- 问题是否能在临时 vault 中复现。

不要包含 API Key、私人笔记、原始文档或完整本地聊天记录。
