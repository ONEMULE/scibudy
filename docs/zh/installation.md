# 安装

## 推荐方式

使用统一安装器：

```bash
npx scibudy-install --profile base
```

如果你是第一次接触这个工具，建议先看 [前置条件](prerequisites.md)。

## 安装 profile

- `base`：MCP、CLI、UI、Codex 配置
- `analysis`：补充分析工作流
- `gpu-local`：本地 GPU 模型环境
- `full`：完整安装

## 源码安装

```bash
git clone git@github.com:ONEMULE/scibudy.git
cd scibudy
python3 -m venv .venv
. .venv/bin/activate
python -m pip install -e .[dev]
scibudy bootstrap --profile base --install-codex
```

## Codex MCP 接入

推荐直接在 bootstrap 时完成：

```bash
scibudy bootstrap --profile base --install-codex
```

或者后续手动执行：

```bash
scibudy install-codex
codex mcp get research
```

## 平台支持

- Linux：一等支持
- macOS：支持 base + analysis
- Windows：`v0.x` 暂不作为一等目标
