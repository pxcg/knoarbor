# 1.15 桌面端开发需求

## 问题

KnoArbor 当前以 Python 包、本地 FastAPI 服务和 React 控制台为主要形态。
这对开发者和高级用户足够清晰，但还不是完整桌面软件：

- 用户需要先在终端启动服务；
- 端口、日志和服务失败主要依赖终端观察；
- Python 和 `uv` 仍然出现在普通用户路径中；
- 内网更新、本地数据目录和应用生命周期还没有产品化；
- macOS/Windows 用户更期待双击打开、原生菜单和应用数据目录。

桌面端应该改善产品体验，而不是重写知识引擎。KnoArbor 的核心价值仍然在 Python 侧的 ingest、lint、query、chat、vault、model、report 和 index 层。Electron 负责承载和管理核心服务。

## 目标

- 提供一等 Electron 桌面应用。
- 将 Chat 作为桌面端首页。
- 桌面端布局优先服务桌面使用，而不是沿用仪表盘式控制台。
- 保留 Python/FastAPI 作为核心运行时。
- 复用当前 React 控制台，不另起一套 UI。
- 由桌面端启动、停止、重启和观测本地 KnoArbor 服务。
- 正式桌面包内置轻量 Python core 和依赖。
- MinerU、Ollama、vLLM、本地模型、VLM/OCR 模型文件作为外部可选服务。
- 使用系统应用数据目录保存配置、知识库、日志、运行状态和更新状态。
- 支持通过内网静态更新源发布版本。
- 保留 CLI、API 和宿主 AI Skill 给开发者和自动化流程使用。
- 桌面原生能力只通过受控 preload bridge 暴露。

## 非目标

- 不把 KnoArbor 核心引擎迁移到 Node.js。
- 不把 MinerU、vLLM、Ollama 或大型模型文件放入主桌面包。
- 不让 renderer 直接访问 Node.js。
- 不用 Electron IPC 替代公开 HTTP API。
- 不让自动更新修改用户知识库、`.env` 或 API Key。

## 验收标准

- 桌面端 SDD 包含需求、设计、任务和验证。
- Electron 被定义为桌面 surface 层，不重复实现核心流程。
- Chat 是桌面端首页，设置以弹窗为主要入口。
- 服务管理器支持 packaged managed service 和 external development service。
- 启动契约包含命令、环境变量、配置路径、端口选择、health wait、日志和关闭策略。
- renderer 继续通过 HTTP API 调用业务流程。
- preload IPC 只暴露桌面原生能力，例如诊断、打开日志、目录选择和服务生命周期。
- macOS、Windows 和 Linux 的应用数据目录规则清晰。
- 打包边界排除开发依赖、仓库历史、测试、运行时知识库、临时文件和重型模型服务。
- 内网更新设计包含 manifest、安装包、签名、回滚和运行中任务处理。
