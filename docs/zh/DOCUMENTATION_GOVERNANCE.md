# 文档治理规则

本文定义 KnoArbor 文档的分类、归属，以及什么时候应该合并、归档或删除文档。

## 文档类型

| 类型 | 当前位置 | 负责内容 | 不应包含 |
| --- | --- | --- | --- |
| 用户指南 | `docs/zh/QUICKSTART.md`、`docs/zh/INSTALLATION.md`、`docs/zh/CONFIGURATION.md`、`docs/zh/TROUBLESHOOTING.md`、`docs/zh/BACKUP_AND_RECOVERY.md` | 首次使用、日常运行、恢复、配置选择 | 内部实现争论或发布流程 |
| 产品导览 | `docs/zh/SHOWCASE.md`、根目录 `README.zh-CN.md` | 产品能做什么、演示时展示什么 | 完整 API/CLI 参考 |
| 参考文档 | `docs/zh/API.md`、`docs/zh/CLI.md`、`docs/zh/ERROR_CODES.md` | 稳定命令、接口、错误码查询 | 架构原因或路线图叙述 |
| 契约文档 | `docs/zh/CONTRACTS.md`、`docs/zh/API_COMPATIBILITY.md`、`docs/zh/UI_CONTRACT.md`、`docs/zh/REPORT_CONTRACT.md`、`docs/zh/PROVENANCE_DESIGN.md` | 运行时、API、UI、报告、溯源边界 | 临时实现笔记 |
| 架构文档 | `docs/zh/ARCHITECTURE.md`、`docs/zh/CAPABILITY_MAP.md`、`docs/zh/ROADMAP.md`、`docs/adr/` | 稳定边界、已接受决策、能力状态、长期方向 | sprint 记录或未定实验 |
| 维护与发布 | `docs/zh/DEVELOPMENT.md`、`docs/zh/MAINTAINERS.md`、`docs/zh/TESTING.md`、`docs/zh/RELEASE_CHECKLIST.md` | 本地开发、发布门禁、分支策略、质量门禁 | 从用户指南复制来的入门内容 |
| 发布历史 | `docs/releases/`、`CHANGELOG.md` | 特定版本变化 | 当前支持行为，除非明确说明是历史状态 |
| 专项治理 | `docs/zh/governance/` | 一次性项目治理分析和清理记录 | 公开用户说明或稳定契约 |

当前保持 `docs/` 根目录相对扁平。原因是 README、发布说明、包元数据和脚本已经大量引用这些稳定公开文档。后续如果要物理迁移目录，应作为一次单独、有计划的文档树迁移来做，而不是在功能治理中零散搬动。

## 清理规则

- 两份文档回答同一类读者的同一问题时，应合并到更权威的归属文档，另一份改为链接。
- 描述已删除脚本、已删除 UI 表面或本地运行产物的文档，应删除或改写，不保留兼容性叙述。
- 只有记录决策、迁移或发布状态且对维护者仍有价值的内容，才归档为历史材料。
- 发布说明保留历史准确性。除密钥、隐私或断链问题外，不为了贴合当前产品而重写旧 release note。
- 英文和中文公开文档中的用户可见行为应保持一致；内部专项治理记录可以只保留中文。
- `specs/` 是实现桥梁，不是公开文档。只有已经接受且稳定的行为才沉淀到 `docs/`。

## 当前策略

当前文档集遵循以下归属规则：

- 暂时不大规模移动公开文档，先用文档类型明确归属；
- 保持 specs 和公开 docs 分离；
- 一次性专项治理记录放入 `docs/zh/governance/`；
- 已删除的产品表面不继续保留用户文档入口；
- 优先更新权威归属文档，而不是复制同一段解释。
