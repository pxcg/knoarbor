# 文档中心

[English](../../README.md) | [简体中文](../../README.zh-CN.md)

这里是 KnoArbor 的中文文档入口。KnoArbor 是一个 AI 原生 Wiki 引擎，将多源信息编译成可追溯、可维护的知识网络，让零散的知识像树一样生长。

英文文档位于 [../](../)。本目录面向公开用户和贡献者。

## 文档分类

- 用户指南：安装、快速开始、配置、故障排查、备份恢复。
- 参考文档：CLI、API、错误码查询。
- 契约文档：API、UI、报告、溯源和运行时边界。
- 架构文档：系统边界、能力归属、路线图和 ADR。
- 维护与发布：开发、测试、发布和长期治理。
- 发布历史：CHANGELOG 和版本发布说明。
- 专项治理：一次性项目治理分析和清理记录。

分类和清理规则见 [文档治理规则](DOCUMENTATION_GOVERNANCE.md)。

## 用户指南

- [展示导览](SHOWCASE.md)：产品体验、端到端流程、演示路径和当前边界。
- [安装部署](INSTALLATION.md)：本地安装、服务启动、模型配置、前端构建和验证步骤。
- [快速开始](QUICKSTART.md)：初始化知识库、编译内置示例，并在桌面端或开发者控制台验证对话/查询。
- [配置说明](CONFIGURATION.md)：模型供应商、知识库目录、输入来源和运行限制。
- [故障排查](TROUBLESHOOTING.md)：配置、模型、UI、ingest 和运行时常见问题。
- [备份与恢复](BACKUP_AND_RECOVERY.md)：运行时知识库备份、git 恢复边界和索引重建。
- [核心概念](CONCEPTS.md)：raw source、source digest、wiki page、ingest、lint、query。

## 参考文档

- [命令行](CLI.md)：知识编译、校验维护、查询和服务启动命令。
- [接口说明](API.md)：本地 HTTP API 的用途和边界。
- [API 兼容性](API_COMPATIBILITY.md)：稳定 endpoint、schema version 和废弃策略。
- [错误码](ERROR_CODES.md)：CLI/API 的稳定错误码和排查建议。

## 契约文档

- [契约总览](CONTRACTS.md)：目录、Wiki 页面、Source Digest、索引、Ingest、Query、Chat、API 和 UI 契约。
- [UI 契约](UI_CONTRACT.md)：对话优先控制台表面、UI 专用适配器和渲染边界。
- [报告契约](REPORT_CONTRACT.md)：报告、台账、失败产物和 Token 分析边界。
- [溯源设计](PROVENANCE_DESIGN.md)：原始资料、来源摘要和知识页面之间的证据链。

## 架构

- [架构设计](ARCHITECTURE.md)：系统分层、流程边界和长期演进方向。
- [架构决策记录](../adr/README.md)：长期架构决策和 ADR 模板。
- [路线图](ROADMAP.md)：桌面端优先的当前方向和后续产品边界。
- [能力地图](CAPABILITY_MAP.md)：跨功能的能力状态和职责归属。

## 贡献者与维护者

- [开发说明](DEVELOPMENT.md)：本地开发、测试、构建和发布流程。
- [维护者指南](MAINTAINERS.md)：长期分支、架构、兜底、兼容性和发布治理。
- [测试与质量门禁](TESTING.md)：单元测试、前端冒烟、发布检查和真实模型冒烟边界。
- [发布前审查清单](RELEASE_CHECKLIST.md)：公开发布前的仓库、隐私、测试、文档、UI 和发布门禁。
- [文档治理规则](DOCUMENTATION_GOVERNANCE.md)：面向维护者的文档分类、归属、清理和归档规则。
- [功能规格](../../specs/README.md)：多步骤架构或契约变更的实现记录。
- [桌面端规格](../../specs/1.15-desktop-app/requirements.zh-CN.md)：Electron 桌面壳、内置 Python 服务、应用数据目录、日志和内网更新架构。
- [贡献指南](../../CONTRIBUTING.md)：贡献流程、分支模型、测试和隐私规则。
- [安全说明](../../SECURITY.md)：漏洞报告和密钥处理。
- [支持说明](../../SUPPORT.md)：提问和提交有效报告的方式。
- [行为准则](../../CODE_OF_CONDUCT.md)：贡献者行为约定。

## 发布历史

- [CHANGELOG](../../CHANGELOG.md)：公开版本变更记录。
- [v2.2.1 发布说明](../releases/v2.2.1.md)：桌面端证据、图片默认参数、会话刷新和 Windows 打包补丁版本说明。
- [v2.0.0 发布说明](../releases/v2.0.0.md)：桌面端和 ingest 升级版本说明。
- [v1.3.0 发布说明](releases/v1.3.0.md)：Wiki 优先对话、页面级检索、多知识库工作区和模型配置版本说明。
- [v1.2.1 发布说明](../releases/v1.2.1.md)：模型端点检测和本地供应商配置版本说明。
- [v1.2.0 发布说明](../releases/v1.2.0.md)：多知识库配置和 Skill 集成版本说明。
- [v1.0.0 发布说明](../releases/v1.0.0.md)：第一个公开本地优先版本说明。
- [v0.9.0 发布说明](../releases/v0.9.0.md)：运行 endpoint、Skill 集成和可观测性版本说明。
- [v0.8.0 发布说明](../releases/v0.8.0.md)：API 合约与 token 可观测性版本说明。
- [v0.7.0 发布说明](../releases/v0.7.0.md)：UI 与知识库浏览版本说明。

历史发布说明保留对应版本当时的接口名称、命令示例和运行假设。当前支持的表面以接口说明、契约总览和 API 兼容性文档为准。

## 推荐阅读顺序

普通使用者：

```text
展示导览 -> 安装部署 -> 快速开始 -> 配置说明 -> 故障排查 -> 命令行 -> 核心概念
```

贡献者：

```text
核心概念 -> 架构设计 -> 契约总览 -> 溯源设计 -> API 兼容性 -> 路线图 -> 功能规格 -> 开发说明 -> 维护者指南 -> 测试与质量门禁
```

发布准备：

```text
发布前审查清单 -> 测试与质量门禁 -> 备份与恢复 -> Changelog -> Release Notes -> Security
```
