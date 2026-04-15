# Scibudy Documentation

Scibudy is a Codex-native research expansion assistant for literature search, library management, full-text analysis, and local semantic retrieval.

## Core surfaces

- CLI: `scibudy`
- MCP server: `scibudy-mcp`
- Installer: `scibudy-install`
- UI: `scibudy ui --open`

## Documentation map

- [Prerequisites](prerequisites.md)
- [Installation](installation.md)
- [Quickstart](quickstart.md)
- [Codex MCP setup](codex-setup.md)
- [CLI and MCP](cli-and-mcp.md)
- [Examples](examples.md)
- [Configuration](configuration.md)
- [GPU local models](gpu-local.md)
- [Library workflow](library-workflow.md)
- [Troubleshooting](troubleshooting.md)
- [Development](development.md)
- [Releasing](releasing.md)

## Architecture summary

Scibudy is Python-first:

- `research_mcp/` contains the runtime, MCP server, CLI, and analysis stack
- `web/` contains the UI source and distributable build artifacts
- `bin/scibudy-install.mjs` is the npm/bootstrap wrapper
- user runtime state is stored under the app home, not in the source tree

## Product model

- `base` profile: CPU-safe runtime and Codex integration
- `analysis` profile: full-text analysis workflow
- `gpu-local` profile: local model environment
- `full` profile: all layers together
