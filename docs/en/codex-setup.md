# Codex MCP Setup

## Recommended path

Let Scibudy manage the MCP config for you:

```bash
scibudy install-codex
```

or during bootstrap:

```bash
scibudy bootstrap --profile base --install-codex
```

## What this does

It updates the managed `research` MCP block in:

```text
~/.codex/config.toml
```

## Verify

```bash
codex mcp get research
```

You should see:

- transport `stdio`
- command path to `research-mcp` or `scibudy-mcp`
- enabled analysis and library tools

## If you do not want automatic Codex changes

Use:

```bash
scibudy bootstrap --profile base --no-install-codex
```

Then add the MCP config later with:

```bash
scibudy install-codex
```
