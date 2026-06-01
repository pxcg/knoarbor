# 备份与恢复

KnoArbor 把运行时知识库视为用户自己的数据。项目仓库只保存源码和公开文档；本地的 `wiki/`、`config.yaml` 和 `.env` 默认被 git ignore。

本文说明哪些内容需要备份、哪些内容能从 git 恢复，以及测试/发布脚本绝不能覆盖哪些数据。

## 需要备份什么

如果你希望保留本地知识库，请备份：

```text
config.yaml
.env
wiki/
```

建议备份范围：

- `wiki/**/*.md`：维护后的 wiki 页面和运行报告。
- `wiki/.knoarbor/`：机器索引、台账、运行记录和锁文件。
- `wiki/raw/`：你选择保留的原始资料或标准化资料。
- `config.yaml`：知识库路径、输入来源、模型供应商名称和运行限制。
- `.env`：模型供应商 API Key 和本地密钥。

`.env` 应存放在密码管理器或加密备份中，不要发布。

## git 能恢复什么

git 只能恢复曾经被 git 跟踪过的文件。正常使用 KnoArbor 时，运行时知识库被 ignore，因此不能依赖 git 恢复。

git 可以帮助恢复：

- 曾经提交过、后来删除的文件；
- release tag 或分支中存在的旧版本；
- 有意提交的示例或测试 fixture。

git 不能恢复：

- 从未提交过的 ignored `wiki/` 运行页面；
- ignored `config.yaml` 或 `.env`；
- 仓库外部的本地输入来源；
- 没有文件系统备份的已删除文件。

## 从 git 安全恢复

尽量先恢复到临时目录：

```bash
mkdir -p .local-dev/recovered-wiki
git archive <commit> wiki | tar -x -C .local-dev/recovered-wiki
```

检查恢复内容后，再把需要的页面复制到当前运行知识库。

如果你明确决定直接恢复旧 tracked wiki 文件到当前知识库，可以使用：

```bash
git restore --source=<commit> --worktree -- wiki
uv run python - <<'PY'
from pathlib import Path
from knoarbor.storage import update_index
update_index(Path("wiki"))
PY
```

由于 `wiki/` 被 ignore，恢复后的文件仍然是本地运行数据，不应提交。

## 重建索引

如果 Markdown 页面存在，但 UI 或 query 看不到页面，重建人工索引和机器索引：

```bash
uv run python - <<'PY'
from pathlib import Path
from knoarbor.storage import update_index
update_index(Path("wiki"))
PY
```

然后检查：

```bash
uv run knoar --config config.yaml status --vault wiki
uv run knoar --config config.yaml query "agent loop" --json
```

## 运行时数据隔离规则

测试、发布检查、冒烟验证和开发门禁默认不得操作维护者真实运行知识库。

强制规则：

- 测试 vault 和测试 config 必须使用 `mktemp -d`。
- 以 `config.example.yaml` 为输入，再把路径改到临时目录。
- 用 `trap` 自动清理临时目录。
- 自动测试不得操作项目根目录的 `wiki/`、`config.yaml` 或 `.env`。
- 不得对项目根目录下的 ignored 运行路径使用 `git clean -fdx` 或宽泛 `rm -rf`。

只有用户明确触发的产品命令或 UI 操作，才应作用于真实配置的知识库。

## 推荐个人备份策略

本地使用：

- 用 Time Machine、Syncthing、云备份或其他私有备份保护 `wiki/`。
- 把 `.env` 放在密码管理器或加密保险库中。
- 大规模 ingest/lint 前手动导出快照。
- 不要依赖公开 git 仓库保存本地知识库。

团队使用：

- 共享运行知识库只应在隐私审查后放入私有仓库或私有对象存储。
- 私有原始资料应与公开项目代码分离。
- 明确谁能访问模型供应商日志和生成的 wiki 页面。
