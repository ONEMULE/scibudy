# 配置说明

## 密钥

用户密钥保存在 app home 的 `.env` 文件中。

常见变量：

- `OPENALEX_API_KEY`
- `CROSSREF_MAILTO`
- `SEMANTIC_SCHOLAR_API_KEY`
- `NCBI_API_KEY`
- `UNPAYWALL_EMAIL`
- `CORE_API_KEY`
- `OPENAI_API_KEY`

## 分析配置

```bash
scibudy analysis-settings
scibudy analysis-update --analysis-mode hybrid --compute-backend local
```

重要项：

- `analysis_mode`
- `compute_backend`
- `chunk_size`
- `chunk_overlap`
- `forum_source_profile`
- 本地 embedding / reranker 配置

## Domain profiles

Domain profile 只影响全文 synthesis，不会限制 `search_literature` 的检索源或学科范围。

当前内置：

- `general`：默认全领域证据抽取 profile。
- `auto`：根据 topic 自动解析 profile，并在 synthesis payload 中记录 requested/resolved profile。
- `sbi_calibration`：SBI calibration 的示例 preset，不是 Scibudy 的默认领域。

用法：

```bash
scibudy profiles
scibudy synthesize-library <library_id> "causal inference robustness" --profile general
scibudy synthesize-library <library_id> "calibration in simulation-based inference" --profile sbi_calibration
```

## 运行目录

app home 中默认包括：

- `.env`
- `state/`
- `analysis/`
- `library/`
- `ui/dist/`
