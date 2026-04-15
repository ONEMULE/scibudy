# Codex MCP 接入

## 推荐方式

让 Scibudy 自动帮你写入 Codex MCP 配置：

```bash
scibudy install-codex
```

或者在 bootstrap 时直接完成：

```bash
scibudy bootstrap --profile base --install-codex
```

## 它会做什么

它会更新：

```text
~/.codex/config.toml
```

中的受管 `research` MCP 配置块。

## 验证

```bash
codex mcp get research
```

你应当看到：

- `stdio` transport
- 指向 `research-mcp` 或 `scibudy-mcp` 的命令路径
- 已启用的检索、文献库和分析工具

## 如果你不想自动改 Codex 配置

```bash
scibudy bootstrap --profile base --no-install-codex
```

之后再手动执行：

```bash
scibudy install-codex
```
