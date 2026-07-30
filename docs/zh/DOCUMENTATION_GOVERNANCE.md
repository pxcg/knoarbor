# 文档治理规则

本文定义 KnoArbor 文档的分类、归属，以及什么时候应该合并、归档或删除文档。

## 文档类型

| 类型 | 当前位置 | 负责内容 | 不应包含 |
| --- | --- | --- | --- |
| 用户指南 | `docs/zh/QUICKSTART.md`、`docs/zh/INSTALLATION.md`、`docs/zh/CONFIGURATION.md`、`docs/zh/TROUBLESHOOTING.md`、`docs/zh/BACKUP_AND_RECOVERY.md`、`docs/zh/CONCEPTS.md` | 首次使用、日常运行、恢复、配置选择和稳定概念 | 内部实现争论或发布流程 |
| 产品导览 | `docs/zh/SHOWCASE.md`、根目录 `README.zh-CN.md` | 产品能做什么、演示时展示什么 | 完整 API/CLI 参考 |
| 参考文档 | `docs/zh/API.md`、`docs/zh/CLI.md`、`docs/zh/ERROR_CODES.md` | 稳定命令、接口、错误码查询 | 架构原因或路线图叙述 |
| 契约文档 | `docs/zh/CONTRACTS.md`、`docs/zh/API_COMPATIBILITY.md`、`docs/zh/UI_CONTRACT.md`、`docs/zh/REPORT_CONTRACT.md`、`docs/zh/PROVENANCE_DESIGN.md` | 运行时、API、UI、报告、溯源边界 | 临时实现笔记 |
| 架构文档 | `docs/zh/ARCHITECTURE.md`、`docs/zh/CAPABILITY_MAP.md`、`docs/zh/ROADMAP.md`、`docs/adr/` | 稳定边界、已接受决策、能力状态、长期方向 | sprint 记录或未定实验 |
| 维护与发布 | `docs/zh/DEVELOPMENT.md`、`docs/zh/MAINTAINERS.md`、`docs/zh/TESTING.md`、`docs/zh/RELEASE_CHECKLIST.md` | 本地开发、发布门禁、分支策略、质量门禁 | 从用户指南复制来的入门内容 |
| 发布历史 | `docs/releases/`、`CHANGELOG.md` | 特定版本变化 | 当前支持行为，除非明确说明是历史状态 |
| 功能规格 | `specs/<feature>/` | 功能需求、接受的设计、实现状态和验收 | 稳定公开契约或重复路线图内容 |
| 规格生命周期注册表 | `specs/registry.json` | 每个规格目录的生命周期、owner domain 和后继关系 | 设计正文或任务细节 |

当前保持 `docs/` 根目录相对扁平。原因是 README、发布说明、包元数据和脚本已经大量引用这些稳定公开文档。后续如果要物理迁移目录，应作为一次单独、有计划的文档树迁移来做，而不是在功能治理中零散搬动。

## 清理规则

- 当前公开正文统一使用 **KnoArbor** 作为产品与公司仓库名称。`knoarbor` Python
  包、`.knoarbor` 数据目录、schema 和 `knoar` CLI 等小写技术标识继续保留；不要仅为
  更新品牌而改写历史版本发布说明。
- 两份文档回答同一类读者的同一问题时，应合并到更权威的归属文档，另一份改为链接。
- 描述已删除脚本、已删除 UI 表面或本地运行产物的文档，应删除或改写，不保留兼容性叙述。
- 只有记录决策、迁移或发布状态且对维护者仍有价值的内容，才归档为历史材料。
- 发布说明保留历史准确性。除密钥、隐私或断链问题外，不为了贴合当前产品而重写旧 release note。
- 英文和中文公开文档中的用户可见行为应保持一致；内部专项治理记录可以只保留中文。
- `specs/` 是实现桥梁，不是公开文档。只有已经接受且稳定的行为才沉淀到 `docs/`。
- `specs/registry.json` 是规格生命周期和后继关系的唯一权威；规格正文中的状态必须与注册表一致。
- `Proposed`、`Accepted`、`Implemented` 规格必须保留四个核心文件；历史和已取代规格保留原始形态，不补造缺失文档。
- 只有在当前没有规格拥有目标契约时才新建规格，否则更新最小 owner 集合。
- Accepted ADR 除状态和后继链接外保持不可变；长期决策变化时使用新的 ADR 取代。
- 版本发布说明以英文为权威；中文公开指南、参考、契约、架构和维护文档保持成对。

## 当前策略

当前文档集遵循以下归属规则：

- 暂时不大规模移动公开文档，先用文档类型明确归属；
- 保持 specs 和公开 docs 分离；
- 一次性治理审查的有效结论进入 owner contract、ADR 或维护规则后删除审查快照；
- 已删除的产品表面不继续保留用户文档入口；
- 优先更新权威归属文档，而不是复制同一段解释。
- 本地与发布门禁执行 `scripts/check-doc-governance.py` 和 `scripts/check-doc-links.py`。
