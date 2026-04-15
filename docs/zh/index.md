# Scibudy 文档

Scibudy 是一个面向 Codex 的科研扩展助手，提供学术检索、文献库管理、全文分析和本地语义检索能力。

## 核心入口

- CLI：`scibudy`
- MCP 服务：`scibudy-mcp`
- 安装器：`scibudy-install`
- 本地界面：`scibudy ui --open`

## 文档导航

- [前置条件](prerequisites.md)
- [安装](installation.md)
- [快速开始](quickstart.md)
- [Codex MCP 接入](codex-setup.md)
- [CLI 与 MCP](cli-and-mcp.md)
- [使用示例](examples.md)
- [配置说明](configuration.md)
- [本地 GPU 模型](gpu-local.md)
- [文献库工作流](library-workflow.md)
- [故障排查](troubleshooting.md)
- [开发指南](development.md)
- [发布指南](releasing.md)

## 架构概览

Scibudy 采用 Python 主运行时：

- `research_mcp/`：MCP 服务、CLI、分析引擎
- `web/`：UI 源码与构建产物
- `bin/scibudy-install.mjs`：npm 安装器包装层
- 用户运行状态默认写入 app home，而不是源码目录
