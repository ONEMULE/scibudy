# Scibudy

[![CI](https://github.com/ONEMULE/scibudy/actions/workflows/ci.yml/badge.svg)](https://github.com/ONEMULE/scibudy/actions/workflows/ci.yml)
[![Docs](https://github.com/ONEMULE/scibudy/actions/workflows/docs.yml/badge.svg)](https://github.com/ONEMULE/scibudy/actions/workflows/docs.yml)
[![Release Check](https://github.com/ONEMULE/scibudy/actions/workflows/release-check.yml/badge.svg)](https://github.com/ONEMULE/scibudy/actions/workflows/release-check.yml)

Scibudy is a Codex-native scientific research expansion assistant for scholarly search, library management, full-text ingestion, and local semantic analysis.

Scibudy combines:

- a local MCP server for Codex
- a shell-first CLI
- a browser management UI
- a layered install system for CPU-first and GPU-extended deployments

中文简介：

Scibudy 是一个面向 Codex 的科研增强助手，提供学术检索、文献库管理、全文分析和本地高质量语义检索能力。它既可以作为 MCP 工具，也可以作为独立 CLI 和本地管理界面使用。

## Status

- License: Apache-2.0
- Release posture: stable `v0.x`
- Primary platforms: Linux and macOS
- Full local GPU path: Linux + NVIDIA first

## Quick links

- English docs: [docs/en/index.md](docs/en/index.md)
- 中文文档: [docs/zh/index.md](docs/zh/index.md)
- Prerequisites: [docs/en/prerequisites.md](docs/en/prerequisites.md) / [docs/zh/prerequisites.md](docs/zh/prerequisites.md)
- Codex MCP setup: [docs/en/codex-setup.md](docs/en/codex-setup.md) / [docs/zh/codex-setup.md](docs/zh/codex-setup.md)
- Usage examples: [docs/en/examples.md](docs/en/examples.md) / [docs/zh/examples.md](docs/zh/examples.md)
- Architecture: [docs/en/architecture.md](docs/en/architecture.md) / [docs/zh/architecture.md](docs/zh/architecture.md)
- Support matrix: [docs/en/support-matrix.md](docs/en/support-matrix.md) / [docs/zh/support-matrix.md](docs/zh/support-matrix.md)
- Contributing: [CONTRIBUTING.md](CONTRIBUTING.md)
- Security: [SECURITY.md](SECURITY.md)
- Support: [SUPPORT.md](SUPPORT.md)
- Roadmap: [ROADMAP.md](ROADMAP.md)
- Changelog: [CHANGELOG.md](CHANGELOG.md)

## Installation

### Before you install

For most new users, the real prerequisites are only:

- Node.js 18+
- Python 3.10+

Read more:

- English: [docs/en/prerequisites.md](docs/en/prerequisites.md)
- 中文: [docs/zh/prerequisites.md](docs/zh/prerequisites.md)

### Unified installer

```bash
npx scibudy-install --profile base
```

Profiles:

- `base`: search, library management, UI, Codex config
- `analysis`: base + analysis-oriented runtime conventions
- `gpu-local`: local GPU model environment and warm flow
- `full`: full bootstrap for a Linux GPU workstation

### Source install

```bash
git clone git@github.com:ONEMULE/scibudy.git
cd scibudy
python3 -m venv .venv
. .venv/bin/activate
python -m pip install -e .[dev]
scibudy bootstrap --profile base --install-codex
```

## Runtime commands

Primary command aliases:

- `scibudy`
- `scibudy-mcp`
- compatibility aliases: `research-cli`, `research-mcp`

Examples:

```bash
scibudy search "simulation-based calibration" --mode general
scibudy collect "simulation-based calibration" --target-dir ~/Desktop/sbc-library
scibudy analysis-settings
scibudy ingest-library <library_id>
scibudy search-evidence <library_id> calibration
scibudy profiles
scibudy synthesize-library <library_id> "causal inference robustness" --profile general
scibudy synthesize-library <library_id> "calibration in simulation-based inference" --profile sbi_calibration
scibudy ui --open
```

## Domain profiles

Domain profiles do **not** limit Scibudy's search scope or providers. Search remains general and multi-source by default.

Profiles only tune full-text synthesis: section weighting, evidence markers, unsupported-claim detection, and risk flags.

- `general`: default all-domain synthesis profile.
- `auto`: chooses a synthesis profile from the topic while preserving general search.
- `sbi_calibration`: an example preset for simulation-based inference calibration workflows.

For more examples and Codex prompt patterns:

- English: [docs/en/examples.md](docs/en/examples.md)
- 中文: [docs/zh/examples.md](docs/zh/examples.md)

## Local model stack

The highest-quality local retrieval path currently uses:

- `Qwen/Qwen3-Embedding-4B`
- `Qwen/Qwen3-Reranker-4B`

Recommended workflow:

```bash
scibudy install-local-models
scibudy warm-local-models --background
```

See:

- English: [docs/en/gpu-local.md](docs/en/gpu-local.md)
- 中文: [docs/zh/gpu-local.md](docs/zh/gpu-local.md)

## Repository layout

```text
research_mcp/   Python runtime, MCP server, CLI, analysis engine
web/            UI source and built assets
bin/            npm/bootstrap entrypoints
docs/           Bilingual project documentation
examples/       Copyable usage examples
scripts/        Release and smoke-check helpers
.github/        CI, templates, automation
```

## Open-source project standards

This repository is intentionally organized like a professional open-source library:

- documented install profiles
- release manifest and bootstrap state
- contributor and support policies
- issue/PR templates
- CI and packaging checks
- bilingual documentation for core user workflows

## Development

Core local checks:

```bash
make test
make build-ui
make package-check
make release-check
```

For deeper guidance:

- English: [docs/en/development.md](docs/en/development.md)
- 中文: [docs/zh/development.md](docs/zh/development.md)
