# 前置条件

## 必需

- Node.js 18+，用于运行统一安装器
- Python 3.10+，用于 Scibudy 运行时
- 可联网，用于 provider API、包安装和模型下载

## 推荐

- 如果你要接入 Codex MCP，建议本机已安装 Codex
- 如果你要源码安装，建议有 Git

## 可选

- conda、Linux、NVIDIA GPU，仅在需要本地高质量 GPU 检索时才需要

## Base profile 不需要全部条件

对于大多数第一次安装用户，`base` profile 只需要：

- Node.js
- Python

GPU、conda 和本地大模型只在 `gpu-local` 或 `full` 时需要。
