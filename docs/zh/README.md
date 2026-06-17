# 文档中心

[English](../../README.md) | [简体中文](../../README.zh-CN.md)

这里是 KnoArbor 的中文文档入口。KnoArbor 是一个 AI 原生 Wiki 引擎，将多源信息编译成可追溯、可维护的知识网络，让零散的知识像树一样生长。

英文文档位于 [../](../)。本目录面向公开用户和贡献者。

## 入门

- [展示导览](SHOWCASE.md)：产品体验、端到端流程、演示路径和当前边界。
- [安装部署](INSTALLATION.md)：本地安装、服务启动、模型配置、前端构建和验证步骤。
- [快速开始](QUICKSTART.md)：初始化知识库、编译内置示例、打开本地控制台，并验证对话/查询。
- [配置说明](CONFIGURATION.md)：模型供应商、知识库目录、输入来源和运行限制。
- [命令行](CLI.md)：知识编译、校验维护、查询和服务启动命令。
- [接口说明](API.md)：本地 HTTP API 的用途和边界。
- [API 兼容性](API_COMPATIBILITY.md)：稳定 endpoint、schema version 和废弃策略。
- [路线图](ROADMAP.md)：从 1.0 公开版本到 2.0 长期兼容基线的发展路径。
- [能力地图](CAPABILITY_MAP.md)：跨功能的能力状态和职责归属。
- [错误码](ERROR_CODES.md)：CLI/API 的稳定错误码和排查建议。
- [故障排查](TROUBLESHOOTING.md)：配置、模型、UI、ingest 和运行时常见问题。
- [核心概念](CONCEPTS.md)：raw source、source digest、wiki page、ingest、lint、query。

## 架构

- [架构设计](ARCHITECTURE.md)：系统分层、流程边界和长期演进方向。
- [架构决策记录](../adr/README.md)：长期架构决策和 ADR 模板。
- [溯源设计](PROVENANCE_DESIGN.md)：原始资料、来源摘要和知识页面之间的证据链。
- [备份与恢复](BACKUP_AND_RECOVERY.md)：运行时知识库备份、git 恢复边界和索引重建。
- [功能规格](../../specs/README.md)：多步骤架构或契约变更的需求、设计、任务和验收记录。

## 参考

- [开发说明](DEVELOPMENT.md)：本地开发、测试、构建和发布流程。
- [维护者指南](MAINTAINERS.md)：长期分支、架构、兜底、兼容性和发布治理。
- [测试与质量门禁](TESTING.md)：单元测试、前端冒烟、发布检查和真实模型冒烟边界。
- [发布前审查清单](RELEASE_CHECKLIST.md)：公开发布前的仓库、隐私、测试、文档、UI 和发布门禁。
- [v1.3.0 发布说明](releases/v1.3.0.md)：Wiki 优先对话、页面级检索、多知识库工作区和模型配置版本说明。
- [v1.2.1 发布说明](../releases/v1.2.1.md)：模型端点检测和本地供应商配置版本说明。
- [v1.2.0 发布说明](../releases/v1.2.0.md)：多知识库配置和 Skill 集成版本说明。
- [v1.0.0 发布说明](../releases/v1.0.0.md)：第一个公开本地优先版本说明。
- [v0.9.0 发布说明](../releases/v0.9.0.md)：运行 endpoint、Skill 集成和可观测性版本说明。
- [v0.8.0 发布说明](../releases/v0.8.0.md)：API 合约与 token 可观测性版本说明。
- [v0.7.0 发布说明](../releases/v0.7.0.md)：UI 与知识库浏览版本说明。

## 推荐阅读顺序

普通使用者：

```text
展示导览 -> 安装部署 -> 快速开始 -> 配置说明 -> 故障排查 -> 命令行 -> 核心概念
```

贡献者：

```text
核心概念 -> 架构设计 -> 溯源设计 -> API 兼容性 -> 路线图 -> 功能规格 -> 开发说明 -> 维护者指南 -> 测试与质量门禁
```

发布准备：

```text
发布前审查清单 -> 测试与质量门禁 -> 备份与恢复 -> Changelog -> Release Notes -> Security
```
