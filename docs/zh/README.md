# 文档中心

[English](../../README.md) | [简体中文](../../README.zh-CN.md)

这里是 KnoArbor 的中文文档入口。KnoArbor 是一个 AI 原生 Wiki 引擎，将多源信息编译成可追溯、可维护的知识网络，让零散的知识像树一样生长。

英文文档位于 [../](../)。本目录面向公开用户和贡献者。

## 入门

- [展示导览](SHOWCASE.md)：产品体验、端到端流程、演示路径和当前边界。
- [快速开始](QUICKSTART.md)：安装、配置、初始化知识库、启动服务和运行查询。
- [配置说明](CONFIGURATION.md)：模型供应商、知识库目录、输入来源和运行限制。
- [命令行](CLI.md)：知识编译、校验维护、查询和服务启动命令。
- [错误码](ERROR_CODES.md)：CLI/API 的稳定错误码和排查建议。
- [核心概念](CONCEPTS.md)：raw source、source digest、wiki page、ingest、lint、query。

## 架构

- [架构设计](ARCHITECTURE.md)：系统分层、流程边界和长期演进方向。
- [溯源设计](PROVENANCE_DESIGN.md)：原始资料、来源摘要和知识页面之间的证据链。

## 参考

- [接口说明](API.md)：本地 HTTP API 的用途和边界。
- [开发说明](DEVELOPMENT.md)：本地开发、测试、构建和发布流程。
- [v0.7.0 发布说明](../releases/v0.7.0.md)：UI 与知识库浏览版本说明。

## 推荐阅读顺序

普通使用者：

```text
展示导览 -> 快速开始 -> 配置说明 -> 命令行 -> 核心概念
```

贡献者：

```text
核心概念 -> 架构设计 -> 溯源设计 -> 开发说明
```
