# 备份与恢复

桌面端使用一个平台本地数据根目录，其中包含 `config.yaml`、`vaults/`、
`state/`、`logs/`、`cache/` 和 `tmp/`。备份只按应用拥有的规范路径排除缓存
与临时数据；用户资料中名为 `Cache`、`logs` 或 `tmp` 的目录仍会被保留。

KnoArbor 把运行时知识库视为用户自己的数据。项目仓库只保存源码和公开文档；本地的 `vaults/`、`config.yaml` 和 `.env` 默认被 git ignore。

本文说明哪些内容需要备份、哪些内容能从 git 恢复，以及测试/发布脚本绝不能覆盖哪些数据。

## 需要备份什么

如果你希望保留本地知识库，请备份：

```text
config.yaml
.env
vaults/
```

建议备份范围：

- `vaults/default/wiki/`：维护后的页面与可读 source projection。
- `vaults/default/raw/`：复制输入、标准化 Markdown、来源附件和来源元数据。
- `vaults/default/artifacts/`：Chat 生成图片和其他用户可见工具产物。
- `vaults/default/maintenance/`：面向用户的流程报告和归档。
- `vaults/default/.knoarbor/ingest.sqlite` 与 `.knoarbor/facts/`：事务 source
  head、attempt、cursor 和不可变 raw-grounded 事实 revision；两者必须一起备份。
- `vaults/default/.knoarbor/chat/`、`.knoarbor/memory/`、`.knoarbor/ledgers/`
  和 `.knoarbor/runs/`：如需保留聊天历史、审计历史和运行诊断，可作为可选备份。
  增量 ingest 游标已经包含在 `ingest.sqlite` 中。
- `state/electron/`、`state/chat/sessions/`、`state/artifacts/` 和
  `state/ledgers/`：桌面偏好、跨全部知识库
  Chat 会话的可选连续性、用户可见产物与审计数据。
- `config.yaml`：知识库路径、输入来源、模型供应商名称、API Key 和运行限制。
- `.env`：不属于模型设置的本地开发环境变量和其他本地密钥。

`.knoarbor/index/`、`.knoarbor/locks/`、`.knoarbor/tmp/`、
应用 `cache/`、应用 `tmp/`，以及 `state/electron/`、`state/chat/sessions/`、
`state/artifacts/` 和 `state/ledgers/` 之外的应用 `state/` 目录可以重建或属于运行态，
不是知识备份核心。

当 `config.yaml` 或 `.env` 包含密钥时，应放在密码管理器或加密备份中，不要发布。

## git 能恢复什么

git 只能恢复曾经被 git 跟踪过的文件。正常使用 KnoArbor 时，运行时知识库被 ignore，因此不能依赖 git 恢复。

git 可以帮助恢复：

- 曾经提交过、后来删除的文件；
- release tag 或分支中存在的旧版本；
- 有意提交的示例或测试 fixture。

git 不能恢复：

- 从未提交过的 ignored `vaults/` 运行页面；
- ignored `config.yaml` 或 `.env`；
- 仓库外部的本地输入来源；
- 没有文件系统备份的已删除文件。

## 从 git 安全恢复

尽量先恢复到临时目录：

```bash
mkdir -p .local-dev/recovered-wiki
git archive <commit> vaults | tar -x -C .local-dev/recovered-wiki
```

检查恢复内容后，再把需要的页面复制到当前运行知识库。

如果你明确决定直接恢复旧 tracked wiki 文件到当前知识库，可以使用：

```bash
git restore --source=<commit> --worktree -- vaults
uv run knoar ingest --vault vaults/default --rebuild-materialization
```

由于 `vaults/` 被 ignore，恢复后的文件仍然是本地运行数据，不应提交。

## 重建索引

如果 Markdown 页面存在，但 UI 或 query 看不到页面，重建人工索引和机器索引：

```bash
uv run knoar ingest --vault vaults/default --rebuild-materialization
```

然后检查：

```bash
uv run knoar --config config.yaml status --vault vaults/default
uv run knoar --config config.yaml query "agent loop" --json
```

## 运行时数据隔离规则

测试、发布检查、冒烟验证和开发门禁默认不得操作维护者真实运行知识库。

强制规则：

- 测试 vault 和测试 config 必须使用 `mktemp -d`。
- 以 `config.example.yaml` 为输入，再把路径改到临时目录。
- 用 `trap` 自动清理临时目录。
- 自动测试不得操作项目根目录的 `vaults/`、`config.yaml` 或 `.env`。
- 不得对项目根目录下的 ignored 运行路径使用 `git clean -fdx` 或宽泛 `rm -rf`。

只有用户明确触发的产品命令或 UI 操作，才应作用于真实配置的知识库。

## 推荐个人备份策略

本地使用：

- 用 Time Machine、Syncthing、云备份或其他私有备份保护 `vaults/`。
- 把 `.env` 放在密码管理器或加密保险库中。
- 大规模 ingest/lint 前手动导出快照。
- 不要依赖公开 git 仓库保存本地知识库。

团队使用：

- 共享运行知识库只应在隐私审查后放入私有仓库或私有对象存储。
- 私有原始资料应与公开项目代码分离。
- 明确谁能访问模型供应商日志和生成的 wiki 页面。
